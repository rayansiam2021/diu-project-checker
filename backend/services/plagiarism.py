"""
services/plagiarism.py — Turnitin-style plagiarism detection v5
================================================================
Chapter-aware deep scan. Never returns 0% if real matches exist.
- Fixes joined PDF words: haswitnessed→has witnessed, ofthe→of the
- Fixes split PDF words: dau nting→daunting, sig-\nnificant→significant
- Relaxed sentence filter: messy PDF text still yields valid sentences
- Query uses 10 clean content words — avoids broken text in Google queries
- 20 queries max → ~5 reports per 100 daily quota
- All sentences in each chapter checked against every found source
"""
from __future__ import annotations
import re, time
from collections import Counter
import requests
from config import GOOGLE_API_KEY, GOOGLE_CX

# ---------------------------------------------------------------------------
# Known common English words used for joined-word detection
# ---------------------------------------------------------------------------
_COMMON_WORDS = frozenset("""
the and has have had was were are been being is it its this that these those
for from with into onto upon about above after before between within without
which when where what who how why all any both each some more most only just
also very even such many much few less than then not but can could would
should will shall may might must on in at to of by as an or so up do if we
my our they them their you your watch management system website project
application user users data digital industry growth significant provides
allows enables features include research literature review methodology
implementation analysis design based using used make made take given shows
study studies found information important development process approach
solution problem
""".split())

# ---------------------------------------------------------------------------
# PDF / text cleaning
# ---------------------------------------------------------------------------

# Explicit lookup table for the most common joined-word patterns in DIU PDFs
_JOINED_PATTERNS = [
    # preposition + "the"
    (r'\bofthe\b', 'of the'), (r'\binthe\b', 'in the'), (r'\bonthe\b', 'on the'),
    (r'\btothe\b', 'to the'), (r'\bforthe\b', 'for the'), (r'\bbythe\b', 'by the'),
    (r'\batthe\b', 'at the'), (r'\bandthe\b', 'and the'), (r'\bwiththe\b', 'with the'),
    (r'\bfromthe\b', 'from the'), (r'\bwithout the\b', 'without the'),
    # auxiliary + verb / word
    (r'\bcanbe\b', 'can be'), (r'\bcanhave\b', 'can have'), (r'\bcanoperate\b', 'can operate'),
    (r'\bcanuse\b', 'can use'), (r'\bcanhelp\b', 'can help'), (r'\bcanmake\b', 'can make'),
    (r'\bcantrack\b', 'can track'), (r'\bhaswitnessed\b', 'has witnessed'),
    (r'\bhasbeen\b', 'has been'), (r'\bhadto\b', 'had to'),
    (r'\bisused\b', 'is used'), (r'\bisthe\b', 'is the'), (r'\bisone\b', 'is one'),
    (r'\bisimportant\b', 'is important'), (r'\bisessential\b', 'is essential'),
    (r'\bisalso\b', 'is also'), (r'\bismost\b', 'is most'), (r'\bisdesigned\b', 'is designed'),
    (r'\bareused\b', 'are used'), (r'\barebeing\b', 'are being'), (r'\baredone\b', 'are done'),
    (r'\bbeused\b', 'be used'), (r'\bbeimplemented\b', 'be implemented'),
    (r'\bbeapplied\b', 'be applied'), (r'\bbedesigned\b', 'be designed'),
    (r'\bbeconsidered\b', 'be considered'), (r'\bbeachieved\b', 'be achieved'),
    # "to" + verb
    (r'\btouse\b', 'to use'), (r'\btomake\b', 'to make'), (r'\btobe\b', 'to be'),
    (r'\btodo\b', 'to do'), (r'\btotake\b', 'to take'), (r'\btowork\b', 'to work'),
    (r'\btogive\b', 'to give'), (r'\btokeep\b', 'to keep'), (r'\btofind\b', 'to find'),
    (r'\btoshow\b', 'to show'), (r'\btosee\b', 'to see'), (r'\btoensure\b', 'to ensure'),
    (r'\btoallow\b', 'to allow'), (r'\btoenable\b', 'to enable'), (r'\btoaccess\b', 'to access'),
    (r'\btoprovide\b', 'to provide'), (r'\btosupport\b', 'to support'),
    (r'\btoassess\b', 'to assess'), (r'\btoaddress\b', 'to address'),
    (r'\btomanage\b', 'to manage'), (r'\btotrack\b', 'to track'), (r'\btostore\b', 'to store'),
    (r'\btobuy\b', 'to buy'), (r'\btosell\b', 'to sell'), (r'\btohelp\b', 'to help'),
    (r'\btoachieve\b', 'to achieve'), (r'\btoidentify\b', 'to identify'),
    (r'\btodevelop\b', 'to develop'), (r'\btodesign\b', 'to design'),
    # preposition + noun
    (r'\bonproblem\b', 'on problem'), (r'\bonsystem\b', 'on system'), (r'\bonuser\b', 'on user'),
    (r'\bforuser\b', 'for user'), (r'\bforwatch\b', 'for watch'), (r'\bfordata\b', 'for data'),
    (r'\bforall\b', 'for all'), (r'\bforeasy\b', 'for easy'), (r'\bforany\b', 'for any'),
    # conjunctions
    (r'\banddata\b', 'and data'), (r'\banduser\b', 'and user'), (r'\bandsystem\b', 'and system'),
    (r'\banddiversification\b', 'and diversification'), (r'\bandorganizing\b', 'and organizing'),
    (r'\baswell\b', 'as well'), (r'\bsothat\b', 'so that'),
    # entity + verb
    (r'\busercan\b', 'user can'), (r'\buserhas\b', 'user has'), (r'\buserneeds\b', 'user needs'),
    (r'\bdatacan\b', 'data can'), (r'\bdatais\b', 'data is'), (r'\bsystemcan\b', 'system can'),
    (r'\bsystemis\b', 'system is'), (r'\bsystemhas\b', 'system has'),
    (r'\bwebsitecan\b', 'website can'), (r'\bwebsiteis\b', 'website is'),
    (r'\bwebsitehas\b', 'website has'),
    # more auxiliary joins
    (r'\bcanhave\b',       'can have'),
    (r'\bcanoperate\b',    'can operate'),
    (r'\bhaswitnessed\b',  'has witnessed'),
    (r'\bhasgrown\b',      'has grown'),
    (r'\bbeimplemented\b', 'be implemented'),
    (r'\bbeachieved\b',    'be achieved'),
    (r'\btoensure\b',      'to ensure'),
    (r'\bonproblem\b',     'on problem'),
    (r'\bonproviding\b',   'on providing'),
    (r'\binthesystem\b',   'in the system'),
    (r'\binthis\b',        'in this'),
    (r'\binthose\b',       'in those'),
    (r'\bfortheir\b',      'for their'),
    (r'\bforthem\b',       'for them'),
    (r'\bforthis\b',       'for this'),
    (r'\binthefield\b',    'in the field'),
    # more patterns from logs
    (r'\bcanhappen\b',     'can happen'),
    (r'\bcannotbe\b',      'cannot be'),
    (r'\btostart\b',       'to start'),
    (r'\btostop\b',        'to stop'),
    (r'\btoface\b',        'to face'),
    (r'\btofollow\b',      'to follow'),
    (r'\bbeuser\b',        'be user'),
    (r'\bbeimplemented\b', 'be implemented'),
    (r'\bbefriendly\b',    'be friendly'),
    (r'\bbyusing\b',       'by using'),
    (r'\bbysaying\b',      'by saying'),
    (r'\bbyproviding\b',   'by providing'),
    (r'\bhowgrateful\b',   'how grateful'),
    (r'\bhowever\b',       'however'),
    (r'\bareobserved\b',    'are observed'),
    (r'\bareassessed\b',    'are assessed'),
    (r'\baremeasured\b',    'are measured'),
    (r'\barerecorded\b',    'are recorded'),
    (r'\bareanalyzed\b',    'are analyzed'),
    (r'\beimplemented\b',   'be implemented'),
]


def _clean_extracted_text(text: str) -> str:
    """Fix PDF extraction artifacts — both split and joined words."""
    # Fix hyphenated line breaks: "sig-\nnificant" → "significant"
    text = re.sub(r'(\w)-[ \t]*\n[ \t]*(\w)', r'\1\2', text)
    # Fix spaced hyphens: "data - driven" → "data-driven"
    text = re.sub(r'(\w)\s+-\s*(\w)', r'\1-\2', text)
    text = re.sub(r'(\w)\s*-\s+(\w)', r'\1-\2', text)
    # Fix camelCase PDF artifacts: "watchManagement" → "watch Management"
    text = re.sub(r'([a-z])([A-Z])', r'\1 \2', text)
    # Fix joined words using explicit lookup table
    for pattern, replacement in _JOINED_PATTERNS:
        text = re.sub(pattern, replacement, text, flags=re.I)
    # Fix split words (short prefix + rest joined): "dau nting" → "daunting"
    def _maybe_join(m: re.Match) -> str:
        a, b = m.group(1).lower(), m.group(2).lower()
        # Use _STOP which has all auxiliaries: be, is, has, can, are, was, etc.
        # If left half is a real English word, the space is correct — don't join
        if a in _STOP or a in _COMMON_WORDS:
            return m.group(0)
        skip = {('to','the'),('in','the'),('on','the'),('of','the'),('at','the'),
                ('be','the'),('is','the'),('as','the')}
        if (a, b) in skip:
            return m.group(0)
        joined = a + b
        if len(a) <= 3 and len(joined) <= 14 and joined not in _COMMON_WORDS:
            return joined
        return m.group(0)
    text = re.sub(r'\b([a-z]{2,3}) ([a-z]{4,})\b', _maybe_join, text)
    # Collapse spaces
    text = re.sub(r'[ \t]+', ' ', text)
    return text


# ---------------------------------------------------------------------------
# Stop words & stamps
# ---------------------------------------------------------------------------
_STOP = frozenset(
    "the a an and or but in on at to of for with by is are was were be been "
    "being have has had do does did will would could should may might shall "
    "this that these those it its we our they their you your i my".split()
)
_UNI_STAMP = re.compile(r'daffodil international university', re.I)

# ---------------------------------------------------------------------------
# Skip-section patterns
# ---------------------------------------------------------------------------
_SKIP_SECTIONS = re.compile(
    r'^(acknowledgements?|acknowledgment|table\s+of\s+contents?|'
    r'list\s+of\s+(figures?|tables?|abbreviations?)|'
    r'references?|bibliography|works\s+cited|'
    r'appendix|appendices|dedication|declaration|'
    r'certificate|approval|supervisor|daffodil)\b', re.I
)
_TOC_DOTS = re.compile(r'[.]{4,}')

# ---------------------------------------------------------------------------
# Chapter heading detection
# ---------------------------------------------------------------------------
_HEADING_RE = re.compile(
    r'^(?:'
    r'(?:chapter|CHAPTER)\s+\d+[\s:\-\u2013.]*(.+)'
    r'|(\d+(?:\.\d+)*)\s*[.\-:)]\s*(.+)'
    r')$', re.MULTILINE
)


def _extract_chapters(body: str) -> list[dict]:
    lines = body.split('\n')
    chapters: list[dict] = []
    current_title, current_level = 'Preamble', 1
    current_lines: list[str] = []

    for line in lines:
        stripped = line.strip()
        m = _HEADING_RE.match(stripped)
        if m and not _TOC_DOTS.search(stripped):
            sect = '\n'.join(current_lines).strip()
            if sect:
                chapters.append({'title': current_title, 'text': sect, 'level': current_level})
            current_title = stripped
            current_level = 1 if m.group(1) else (m.group(2) or '').count('.') + 1
            current_lines = []
        else:
            current_lines.append(line)

    sect = '\n'.join(current_lines).strip()
    if sect:
        chapters.append({'title': current_title, 'text': sect, 'level': current_level})

    result = []
    for ch in chapters:
        t = ch['title'].strip()
        if _TOC_DOTS.search(t):
            continue
        if _SKIP_SECTIONS.match(t):
            continue
        if len(re.findall(r'\b[a-zA-Z]{2,}\b', ch['text'])) < 80:
            continue
        result.append(ch)
    return result


# ---------------------------------------------------------------------------
# Sentence splitting — relaxed for messy PDF text
# ---------------------------------------------------------------------------

def _split_sentences(text: str) -> list[str]:
    """Extract usable sentences. Relaxed rules so PDF text yields results."""
    chunks: list[str] = []
    for line in re.split(r'[\n\r]+', text):
        line = line.strip()
        if not line:
            continue
        for part in re.split(r'(?<=[.!?])\s+(?=[A-Z])', line):
            part = part.strip()
            if part:
                chunks.append(part)

    sentences: list[str] = []
    seen: set[str] = set()
    for s in chunks:
        # Trim to last sentence-ending punctuation
        if s and s[-1] not in '.!?':
            for ch in reversed(s):
                if ch in '.!?':
                    s = s[:s.rfind(ch)+1]
                    break
        if len(s) < 35:
            continue
        if sum(c.isdigit() for c in s) / max(len(s),1) > 0.35:
            continue
        if _UNI_STAMP.search(s):
            continue
        words = re.findall(r'[a-zA-Z]{3,}', s.lower())
        if len(set(words) - _STOP) < 5:
            continue
        key = re.sub(r'\s+', ' ', s.lower())[:120]
        if key in seen:
            continue
        seen.add(key)
        sentences.append(s)
    return sentences


# ---------------------------------------------------------------------------
# Query builder — extract 10 clean content words
# ---------------------------------------------------------------------------

def _build_query(sentence: str) -> str:
    """
    Build a Google search query from a sentence.
    CRITICAL: Send the sentence AS-IS (first 10 words), NOT stripped of stop words.
    Google needs natural phrase structure to find matching web pages.
    Stripping stop words turns "The watch industry has witnessed significant growth"
    into "watch industry witnessed significant growth" which Google cannot match.
    """
    # Use first 10 words of the sentence in their natural order
    words = sentence.split()[:10]
    query = ' '.join(words)
    # Remove trailing punctuation from last word
    query = re.sub(r'[,;:]+$', '', query).strip()
    return query


# ---------------------------------------------------------------------------
# Sentence scoring & query picker
# ---------------------------------------------------------------------------

def _sentence_score(s: str) -> float:
    """
    Score a sentence for use as a Google search query.
    Prefer:
    - Sentences that start with a capital letter (complete sentence)
    - Medium length (12-20 words) — short enough for Google, long enough to be unique
    - Low digit ratio (not a numbered list item)
    - Has a natural ending (.)
    """
    words   = re.findall(r'[a-zA-Z]{3,}', s.lower())
    content = [w for w in words if w not in _STOP]
    total_w = len(s.split())

    # Prefer sentences 10-20 words long
    length_score = 1.0 if 10 <= total_w <= 20 else max(0.3, 1.0 - abs(total_w - 15) * 0.05)
    vocab_score  = min(len(set(content)) / 8.0, 1.0)
    digit_pen    = max(0, 1 - sum(c.isdigit() for c in s) / max(len(s),1) * 4)
    # Bonus: starts uppercase (complete sentence)
    case_bonus   = 0.15 if s and s[0].isupper() else 0.0
    # Bonus: ends with period (complete sentence)
    end_bonus    = 0.1 if s.rstrip().endswith('.') else 0.0
    return 0.35 * length_score + 0.35 * vocab_score + 0.2 * digit_pen + case_bonus + end_bonus


def _pick_queries_for_chapter(sentences: list[str], n_queries: int) -> list[str]:
    """
    Pick n_queries sentences spread across the chapter.
    Prefer sentences that:
    - Are in the middle length range (10-20 words) — specific enough for Google
    - Start with capital letter (complete sentences)
    - Are about technical/domain concepts, not personal opinions
    - Are spread from different parts of the chapter (beginning/middle/end)
    """
    if not sentences:
        return []
    n_queries = max(1, n_queries)
    if len(sentences) <= n_queries:
        return sentences

    # Personal/opinion sentence patterns to deprioritize
    _PERSONAL = re.compile(
        r'^(I |We |My |Our |This project |This report |In this |The author)',
        re.I
    )

    def score(s: str) -> float:
        base = _sentence_score(s)
        # Penalize personal sentences (less likely to be copied text)
        if _PERSONAL.match(s):
            base -= 0.2
        return base

    seg_size = max(1, len(sentences) // n_queries)
    chosen: list[str] = []
    seen_wsets: list[set] = []
    for i in range(n_queries):
        start = i * seg_size
        end   = start + seg_size if i < n_queries - 1 else len(sentences)
        seg   = sentences[start:end]
        for s in sorted(seg, key=score, reverse=True):
            ws = set(re.findall(r'[a-z]{3,}', s.lower()))
            if not any(len(ws & w2)/max(len(ws|w2),1) > 0.5 for w2 in seen_wsets):
                chosen.append(s)
                seen_wsets.append(ws)
                break
    return chosen


# ---------------------------------------------------------------------------
# Text / matching helpers
# ---------------------------------------------------------------------------

def _strip_html(html: str) -> str:
    html = re.sub(r'(?is)<(script|style|noscript).*?>.*?</\1>', ' ', html)
    html = re.sub(r'(?is)<br\s*/?>', '\n', html)
    html = re.sub(r'(?is)</p\s*>', '\n', html)
    html = re.sub(r'(?is)<[^>]+>', ' ', html)
    html = html.replace('&nbsp;',' ').replace('&amp;','&').replace('&lt;','<').replace('&gt;','>')
    html = re.sub(r'[ \t\r\f\v]+', ' ', html)
    return re.sub(r'\n{2,}', '\n', html).strip()


def _fetch_page(url: str, cache: dict) -> str | None:
    if url in cache:
        return cache[url]
    try:
        r = requests.get(url, headers={'User-Agent':'Mozilla/5.0 (DIUChecker/5.0)'}, timeout=8)
        if r.status_code >= 400:
            cache[url] = None
            return None
        txt = _strip_html(r.text)[:600_000]
        cache[url] = txt
        return txt
    except Exception:
        cache[url] = None
        return None


def _tokenize(s: str, limit: int = 15000) -> list[str]:
    return [m.group(0).lower() for m in re.finditer(r"\b[\w'-]+\b", s or '')][:limit]


def _jaccard2(a: list[str], b: list[str]) -> float:
    if len(a) < 2 or len(b) < 2: return 0.0
    A = {(a[i],a[i+1]) for i in range(len(a)-1)}
    B = {(b[i],b[i+1]) for i in range(len(b)-1)}
    return len(A&B)/max(1,len(A|B))


def _cosine(a: list[str], b: list[str]) -> float:
    ca, cb = Counter(a), Counter(b)
    if not ca or not cb: return 0.0
    dot = sum(v*cb.get(k,0) for k,v in ca.items())
    return dot / max((sum(v*v for v in ca.values())**0.5 * sum(v*v for v in cb.values())**0.5), 1e-9)


def _best_window(qw: list[str], sw: list[str]) -> tuple[float, float, float]:
    if not qw or not sw: return 0.0, 0.0, 0.0
    qlen = len(qw)
    best = (0.0, 0.0, 0.0)
    step = max(1, qlen//3)
    for wlen in range(max(6, qlen-3), min(len(sw)+1, qlen+6)):
        for pos in range(0, len(sw)-wlen+1, step):
            win = sw[pos:pos+wlen]
            j2  = _jaccard2(qw, win)
            cos = _cosine(qw, win)
            sc  = 0.55*j2 + 0.45*cos
            if sc > best[0]:
                best = (sc, j2, cos)
    return best


def _classify(j2: float, cos: float) -> str | None:
    if j2 >= 0.50 and cos >= 0.65: return 'exact'
    if j2 >= 0.35 and cos >= 0.50: return 'paraphrase'
    if cos >= 0.70:                 return 'paraphrase'
    return None


def _match_chapter_sentences(sentences: list[str], source_items: list[dict], page_cache: dict) -> list[dict]:
    sources = []
    for it in source_items[:4]:
        url = it.get('link','')
        if url:
            pg = _fetch_page(url, page_cache)
            if pg:
                sources.append((it, pg))
    if not sources:
        return []

    matches = []
    for sent in sentences:
        best: dict | None = None
        bscore = 0.0
        for it, pg in sources:
            url  = it.get('link','')
            norm = re.sub(r'\s+',' ', sent[:100].lower())
            if norm in re.sub(r'\s+',' ', pg.lower()):
                best   = {'sentence':sent,'confidence':'Exact',
                          'source_title':(it.get('title') or url)[:140],
                          'source_url':url,'source_snippet':(it.get('snippet') or '')[:300],'score':1.0}
                bscore = 1.0
                break
            qw = _tokenize(sent, 40)
            sw = _tokenize(pg, 12000)
            sc, j2, cos = _best_window(qw, sw)
            mode = _classify(j2, cos)
            if mode and sc > bscore:
                bscore = sc
                best   = {'sentence':sent,
                          'confidence':'Exact' if mode=='exact' else 'Paraphrase',
                          'source_title':(it.get('title') or url)[:140],
                          'source_url':url,'source_snippet':(it.get('snippet') or '')[:300],'score':sc}
        if best:
            matches.append(best)
    return matches


# ---------------------------------------------------------------------------
# Google Custom Search — 1 quota per call
# ---------------------------------------------------------------------------

def _google_search(query: str, num: int = 3) -> dict | None:
    try:
        from services.quota_tracker import get_active_pair, record_queries as _rec
        key_idx, api_key, cx = get_active_pair()
        if not api_key or not cx:
            api_key, cx = GOOGLE_API_KEY, GOOGLE_CX
            key_idx = 0
        def _record(n):
            try: _rec(n, key_index=key_idx)
            except Exception: pass
    except Exception:
        api_key, cx = GOOGLE_API_KEY, GOOGLE_CX
        _record = lambda n: None

    if not api_key or not cx:
        return None

    num   = max(1, min(int(num), 5))
    q_str = ' '.join(re.sub(r'\s+',' ',(query or '').strip()).split()[:12])
    params = {'key':api_key,'cx':cx,'q':f'"{q_str}"','num':num}
    try:
        r = requests.get('https://www.googleapis.com/customsearch/v1', params=params, timeout=12)
        _record(1)
        if r.status_code == 429:
            return {'total':0,'items':[],'quota_exhausted':True}
        if r.status_code == 400:
            params['q'] = q_str
            r = requests.get('https://www.googleapis.com/customsearch/v1', params=params, timeout=12)
        if r.status_code != 200:
            return {'total':0,'items':[]}
        data  = r.json() or {}
        total = int(data.get('searchInformation',{}).get('totalResults',0) or 0)
        items = [{'title':(it.get('title') or '')[:140],
                  'link':it.get('link') or '',
                  'snippet':(it.get('snippet') or '')[:300]}
                 for it in (data.get('items') or [])[:num] if it.get('link')]
        return {'total':total,'items':items}
    except Exception:
        return {'total':0,'items':[]}


# ---------------------------------------------------------------------------
# Query budget allocator
# ---------------------------------------------------------------------------

def _allocate_queries(chapters: list[dict], max_total: int = 20) -> list[tuple[dict, int]]:
    """
    Allocate search queries across chapters.
    Every chapter gets exactly 1 query minimum.
    Extra queries go to larger chapters (more words = more content to check).
    If chapters > max_total, only the largest chapters get queries.
    """
    counts = [len(re.findall(r'\b[a-zA-Z]{2,}\b', ch['text'])) for ch in chapters]
    n = len(chapters)

    if n == 0:
        return []

    if n >= max_total:
        # More chapters than queries — give 1 query each to the largest chapters
        indexed = sorted(enumerate(counts), key=lambda x: -x[1])
        raw = [0] * n
        for i, _ in indexed[:max_total]:
            raw[i] = 1
        return list(zip(chapters, raw))

    # Start: 1 query per chapter
    raw = [1] * n
    remaining = max_total - n

    # Distribute remaining queries proportionally to word count
    total = max(sum(counts), 1)
    for _ in range(remaining):
        # Give next query to the chapter with highest words-per-query ratio
        ratios = [counts[i] / max(raw[i], 1) for i in range(n)]
        best = ratios.index(max(ratios))
        if raw[best] < 3:  # max 3 queries per chapter
            raw[best] += 1
        else:
            # All large chapters capped, give to next best
            eligible = [(ratios[i], i) for i in range(n) if raw[i] < 3]
            if not eligible:
                break
            raw[eligible[0][1]] += 1

    return list(zip(chapters, raw))


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

MAX_QUERIES           = 20
_TURNITIN_BOOST       = 1.45
_TURNITIN_FLOOR_EXACT = 3.0
_TURNITIN_FLOOR_PARA  = 1.5


def compute_plagiarism(text: str) -> dict:
    """Chapter-aware plagiarism detection v5. Never returns 0% if real matches exist."""
    import sys

    if not text or len(text.strip()) < 30:
        return {'available':False,'message':'No usable text.',
                'percentage':0.0,'checked':0,'found':0,'matches':[],'sources':[],'spans':[]}

    # Step 1: Clean PDF artifacts
    text = _clean_extracted_text(text)

    # Step 2: Strip bibliography
    bib_m = re.search(r'(\n|\A)\s*(references?|bibliography|works\s+cited)\s*(\n|$)', text, re.I)
    body  = text[:bib_m.start()] if bib_m else text

    body_words_total = len(re.findall(r'\b[a-zA-Z]{2,}\b', body))
    if body_words_total < 40:
        return {'available':False,'message':'Document too short.',
                'percentage':0.0,'checked':0,'found':0,'matches':[],'sources':[],'spans':[]}

    # Step 3: Detect chapters
    chapters = _extract_chapters(body)
    if not chapters:
        chapters = [{'title':'Full Document','text':body,'level':1}]

    print(f'[PLAG v5] body_words={body_words_total}, chapters={len(chapters)}', file=sys.stderr)
    for ch in chapters:
        wc = len(re.findall(r'\b[a-zA-Z]{2,}\b', ch['text']))
        print(f'[PLAG v5]   {ch["title"][:60]!r} ({wc} words)', file=sys.stderr)

    # Step 4: Allocate queries
    allocations = _allocate_queries(chapters, max_total=MAX_QUERIES)
    print(f'[PLAG v5] queries allocated: {sum(n for _,n in allocations)}', file=sys.stderr)

    # Step 5: Process each chapter
    page_cache: dict = {}
    all_matches:     list[dict] = []
    sources_bundle:  list[dict] = []
    spans:           list[dict] = []
    matches_preview: list[str]  = []
    found_exact = found_para = 0
    total_sentences_checked = total_queries_used = 0
    quota_exhausted = False

    for chapter, n_queries in allocations:
        if quota_exhausted or total_queries_used >= MAX_QUERIES:
            break

        ch_title = chapter['title']
        ch_text  = chapter['text']
        ch_sents = _split_sentences(ch_text)

        if not ch_sents:
            print(f'[PLAG v5] {ch_title[:40]!r}: no valid sentences', file=sys.stderr)
            continue

        total_sentences_checked += len(ch_sents)
        query_sents = _pick_queries_for_chapter(ch_sents, n_queries)
        print(f'[PLAG v5] {ch_title[:40]!r}: {len(ch_sents)} sentences, {n_queries} queries',
              file=sys.stderr)

        chapter_sources: list[dict] = []
        seen_urls: set[str] = set()

        for q_sent in query_sents:
            if total_queries_used >= MAX_QUERIES:
                break
            query_str = _build_query(q_sent)
            print(f'[PLAG v5]   query #{total_queries_used+1}: {query_str!r}', file=sys.stderr)

            res = _google_search(query_str, num=3)
            total_queries_used += 1

            if res is None:
                print('[PLAG v5] Google API failure', file=sys.stderr)
                break
            if res.get('quota_exhausted'):
                print(f'[PLAG v5] quota exhausted at #{total_queries_used}', file=sys.stderr)
                quota_exhausted = True
                break

            items = [it for it in (res.get('items') or []) if it.get('link')]
            print(f'[PLAG v5]     → total={res.get("total",0)}, urls={len(items)}', file=sys.stderr)

            for it in items:
                url = it.get('link','')
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    chapter_sources.append(it)

            time.sleep(0.35)

        if not chapter_sources:
            print(f'[PLAG v5]   no sources found for chapter', file=sys.stderr)
            continue

        # Step 6: Match ALL chapter sentences against all found sources
        ch_matches = _match_chapter_sentences(ch_sents, chapter_sources, page_cache)
        print(f'[PLAG v5]   matched {len(ch_matches)}/{len(ch_sents)} sentences', file=sys.stderr)

        for m in ch_matches:
            conf, sent = m['confidence'], m['sentence']
            if conf == 'Exact': found_exact += 1
            else:               found_para  += 1
            all_matches.append(m)
            if len(matches_preview) < 20:
                matches_preview.append(sent[:260])
            if len(sources_bundle) < 30:
                sources_bundle.append({'match':sent[:260],'confidence':conf,'chapter':ch_title,
                    'sources':[{'title':m['source_title'],'link':m['source_url'],
                                'snippet':m['source_snippet']}]})
            try:
                idx = body.find(sent[:60])
                if idx >= 0:
                    spans.append({'start':idx,'end':idx+len(sent),'type':'plagiarism',
                        'confidence':conf,'source':{'title':m['source_title'],'link':m['source_url']}})
            except Exception:
                pass

    # Step 7: Compute percentage
    matched_wt = sum(
        len(re.findall(r'\b[a-zA-Z]{2,}\b', m['sentence'])) * (1.0 if m['confidence']=='Exact' else 0.75)
        for m in all_matches
    )
    raw_pct    = (matched_wt / max(body_words_total, 1)) * 100
    calibrated = raw_pct * _TURNITIN_BOOST
    if found_exact >= 1: calibrated = max(calibrated, _TURNITIN_FLOOR_EXACT)
    elif found_para >= 1: calibrated = max(calibrated, _TURNITIN_FLOOR_PARA)
    pct = round(min(calibrated, 99.0), 2)

    print(f'[PLAG v5] FINAL: queries={total_queries_used}, sentences={total_sentences_checked}, '
          f'exact={found_exact}, para={found_para}, '
          f'matched_wt={matched_wt:.1f}, body_words={body_words_total}, '
          f'raw={raw_pct:.2f}%, calibrated={pct}%', file=sys.stderr)

    return {
        'available': True, 'percentage': pct,
        'checked': total_sentences_checked, 'found': found_exact + found_para,
        'matches': matches_preview, 'sources': sources_bundle, 'spans': spans,
        'method': 'chapter_aware_v5',
        'meta': {
            'totalBodyWords': body_words_total, 'chaptersDetected': len(chapters),
            'sentencesChecked': total_sentences_checked, 'queriesUsed': total_queries_used,
            'matchedWeighted': round(matched_wt, 2), 'foundExact': found_exact,
            'foundParaphrase': found_para, 'maxQueries': MAX_QUERIES,
            'turnitinBoost': _TURNITIN_BOOST, 'excludeBibliography': bib_m is not None,
        },
    }
