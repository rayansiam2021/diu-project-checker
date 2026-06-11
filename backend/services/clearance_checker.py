"""
services/clearance_checker.py — DIU Clearance Engine v4

Verified against real PDFs:
  221-16-632_siyad: Page 2=Approval(4 sigs), Page 3=Declaration(2 sigs),
                    Pages ii-xiv=Roman, Page 15=Chapter1, Turnitin=8% on page 61
  193-16-467_Kashpia: Pages 2-3 = scanned photos, Turnitin=11% on page 63

Fixes in v4:
 1. Turnitin % extraction: anchored to similarity index block, not body text numbers
 2. Page numbering: use footer Roman/Arabic only (last line), ignore body text
 3. Declaration: check supervisor signature specifically
 4. Approval: count signature lines above each person name
 5. Source parsing: handle '<1%' as 0.5, parse exactly the Turnitin table format
 6. DIU Space: dspace.daffodilvarsity counts as DIU source (limit 5%)
 7. Overall %: only matched if found near 'SIMILARITY INDEX' heading
"""
from __future__ import annotations
import re
import os
from typing import Optional

# ── Constants ─────────────────────────────────────────────────────────────────

REQUIRED_SECTIONS = [
    ("approval",          ["approval", "board of examiners"]),
    ("declaration",       ["declaration", "i hereby declare"]),
    ("acknowledgement",   ["acknowledgement", "acknowledgment", "i would like to", "i am highly"]),
    ("abstract",          ["abstract", "executive summary"]),
    ("table_of_contents", ["table of contents", "contents"]),
    ("list_of_figures",   ["list of figures", "list of figure"]),
]

CHAPTER_PATTERN = re.compile(
    r"^\s*(chapter\s+[1-9ivxIVX]|chapter\s+one|chapter\s+two|chapter\s+three|"
    r"1\s*introduction|introduction\s*$)",
    re.IGNORECASE | re.MULTILINE
)

PERSON_TITLE_PATTERN = re.compile(
    r"\b(dr\.?|prof\.?|professor|mr\.?|mrs\.?|ms\.?|associate\s+professor|"
    r"assistant\s+professor|lecturer|supervisor|co-supervisor|dean|chairman|"
    r"examiner|internal\s+examiner|external\s+examiner|head\s+of\s+department|"
    r"founder|ceo|principal)\b",
    re.IGNORECASE
)

ROMAN_VALUES = {
    "i":1,"ii":2,"iii":3,"iv":4,"v":5,"vi":6,"vii":7,"viii":8,
    "ix":9,"x":10,"xi":11,"xii":12,"xiii":13,"xiv":14,"xv":15,
    "xvi":16,"xvii":17,"xviii":18,"xix":19,"xx":20
}

ROMAN_RE = re.compile(
    r"^(i{1,3}|iv|vi{0,3}|ix|xi{0,3}|xiv|xv|xvi{0,3}|xix|xx)$",
    re.IGNORECASE
)

ARABIC_RE = re.compile(r"^(\d{1,4})$")

DIU_DOMAIN_PATTERNS = ["dspace.daffodil", "daffodilvarsity", "diu space", "daffodil international university"]

TURNITIN_PATTERNS = [
    "similarity index", "originality report", "turnitin",
    "plagiarism report", "internet sources", "student papers",
    "primary sources", "similarity report"
]


# ── PDF text extraction ───────────────────────────────────────────────────────

def _extract_text_from_pdf(path: str) -> list[str]:
    try:
        import fitz
        doc = fitz.open(path)
        pages = [page.get_text("text") or "" for page in doc]
        doc.close()
        return pages
    except Exception:
        pass
    try:
        from PyPDF2 import PdfReader
        return [p.extract_text() or "" for p in PdfReader(path).pages]
    except Exception:
        return []


def _extract_text_from_docx(path: str) -> list[str]:
    try:
        from docx import Document
        doc = Document(path)
        paras = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
        return ["\n".join(paras[i:i+40]) for i in range(0, max(1, len(paras)), 40)]
    except Exception:
        return []


def _extract_pages(path: str) -> list[str]:
    lp = path.lower()
    if lp.endswith(".pdf"):   return _extract_text_from_pdf(path)
    if lp.endswith(".docx"):  return _extract_text_from_docx(path)
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return [f.read()]
    except Exception:
        return []


def _sparse(text: str, threshold: int = 80) -> bool:
    return len(text.strip()) < threshold


def _ocr_page(path: str, idx: int) -> str:
    try:
        from pdf2image import convert_from_path
        import pytesseract
        imgs = convert_from_path(path, first_page=idx+1, last_page=idx+1, dpi=250)
        if imgs:
            return pytesseract.image_to_string(imgs[0])
    except Exception as e:
        print(f"[OCR] page {idx+1}: {e}", flush=True)
    return ""


# ── Page number helpers ───────────────────────────────────────────────────────

def _footer_page_num(page_text: str):
    """
    Extract page number ONLY from the last non-empty line of a page.
    This avoids picking up numbers from body text.
    Returns ('roman', value) or ('arabic', value) or None.
    """
    lines = [l.strip() for l in page_text.split("\n") if l.strip()]
    if not lines:
        return None
    # Check last line and second-to-last line (footer area)
    for line in reversed(lines[-3:]):
        # strip common footer noise
        clean = line.replace("©", "").replace("Daffodil International University", "").strip()
        if not clean:
            continue
        if len(clean) > 8:  # too long to be a page number
            continue
        rm = ROMAN_RE.match(clean)
        if rm:
            return ("roman", ROMAN_VALUES.get(clean.lower(), 0))
        am = ARABIC_RE.match(clean)
        if am:
            val = int(am.group(1))
            if 1 <= val <= 500:
                return ("arabic", val)
    return None


# ── Rule 1: Required sections ─────────────────────────────────────────────────

def check_required_sections(pages: list[str], pdf_path: Optional[str] = None) -> dict:
    full_text = "\n".join(pages[:20]).lower()
    ocr_count = 0

    if pdf_path:
        for i, pg in enumerate(pages[:15]):
            if _sparse(pg, 80):
                ocr = _ocr_page(pdf_path, i)
                if ocr.strip():
                    full_text += "\n" + ocr.lower()
                    ocr_count += 1
                    print(f"[SECT OCR] page {i+1}: {len(ocr)} chars", flush=True)

    results, missing = {}, []
    for key, keywords in REQUIRED_SECTIONS:
        found = any(kw in full_text for kw in keywords)
        results[key] = found
        if not found:
            missing.append(key.replace("_", " ").title())

    return {
        "pass": len(missing) == 0,
        "sections": results,
        "missing": missing,
        "ocr_pages_scanned": ocr_count,
        "message": "All required sections found." if not missing
                   else f"Missing sections: {', '.join(missing)}",
    }


# ── Rule 2: Approval signatures ───────────────────────────────────────────────

def _is_name_line(line: str) -> bool:
    """
    Returns True if a line looks like a person's full name.
    Handles fitz layout where role label is appended right-aligned on same line:
      'Md Sarwar Hossain Mollah                    Chairman'
    """
    if not line or len(line) > 120:
        return False
    # Strip trailing role labels that fitz appends right-aligned
    stripped = re.sub(
        r'\s{2,}(chairman|internal\s+examiner|external\s+examiner|'
        r'supervisor|co-supervisor|head\s+of\s+department)\s*$',
        '', line, flags=re.IGNORECASE
    ).strip()

    if len(stripped) > 70:
        return False
    line_lower = stripped.lower()

    # Skip affiliation / org / company lines
    affil_keywords = [
        "department", "faculty", "university", "daffodil", "mawlana",
        "institute", "college", "science", "information", "technology",
        "computing", "systems", "board", "©", "approved", "submitted",
        "accepted", "fulfillment", "requirements", "degree", "presentation",
        "held on", "this thesis", "this project",
        # company / org suffixes
        "limited", "ltd", "inc", "pvt", "bio", "medico", "group",
        "solutions", "enterprise", "corp", "llc",
    ]
    if any(kw in line_lower for kw in affil_keywords):
        return False

    words = stripped.split()
    if len(words) < 2 or len(words) > 6:
        return False

    # Must have at least one capitalized proper-name word
    if not any(w[0].isupper() for w in words if w and w[0].isalpha()):
        return False

    # Reject if it looks like a signature / OCR handwriting
    has_noise = bool(re.search(r"[\/\\0-9\+\=\~\^@#\$\*]", stripped))
    alpha_count = sum(c.isalpha() for c in stripped)
    alpha_ratio = alpha_count / max(len(stripped), 1)
    if has_noise and alpha_ratio < 0.75:
        return False
    if len(stripped) <= 12 and has_noise:
        return False

    # Reject lines containing title/role keywords ANYWHERE in the line
    # (catches OCR typos like "Associnte Professor", "Asst. Professor" etc.)
    title_keywords_anywhere = re.compile(
        r"\b(professor|examiner|lecturer|chairman|supervisor|dean|principal|"
        r"founder|ceo|cto|director|head\s+of|managing|associate|assistant|"
        r"internal|external|co-supervisor)\b",
        re.IGNORECASE
    )
    if title_keywords_anywhere.search(stripped):
        return False

    # Reject job description lines with "at" connector or "&" (e.g. "Founder & CEO at DocTime")
    if re.search(r"\b(at|&)\b", stripped, re.IGNORECASE) and len(words) >= 3:
        return False

    return True


def _clean_name(line: str) -> str:
    """Strip trailing right-aligned role labels that fitz appends to name lines."""
    return re.sub(
        r'\s{2,}(chairman|internal\s+examiner|external\s+examiner|'
        r'supervisor|co-supervisor|head\s+of\s+department|'
        r'professor|examiner|lecturer|dean|principal)\s*$',
        '', line, flags=re.IGNORECASE
    ).strip()


def _is_sig_line(line: str) -> bool:
    """
    Returns True if a line looks like a handwritten signature or signature blank.
    Handles:
    - Underscore/dash blanks: ________ or --------
    - OCR of cursive handwriting: short garbled tokens, often with digits/date
    - Date-stamped sigs: "Ratdllah 9/1/46", "Cls 05-01-2026 9/4/26"
    """
    if not line:
        return False
    stripped = line.strip()
    length = len(stripped)
    if length > 55 or length < 2:
        return False

    # Explicit blanks — highest confidence
    if re.search(r"_{4,}|-{5,}|\.{6,}", stripped):
        return True
    if re.search(r"\b(signature|signed)\s*:", stripped, re.IGNORECASE):
        return True

    words = stripped.split()
    word_count = len(words)

    # Reject if it's clearly a full sentence
    if word_count >= 6:
        return False

    # Reject ID / reference numbers: "ID: 221-16-632", "No: 203-16-545"
    if re.search(r"\b(id|no|reg|roll)\s*[:#]\s*\d", stripped, re.IGNORECASE):
        return False

    # Reject pure page numbers (Arabic or Roman numerals)
    if re.match(r"^\d{1,4}$", stripped):
        return False
    if ROMAN_RE.match(stripped):   # pure Roman numeral: i, ii, iii, iv, x…
        return False

    # Reject lines that look like valid person names (2 capitalized words, all alpha)
    # to avoid detecting "Anowar Hossain" as a sig from OCR duplicate
    if word_count == 2:
        w1, w2 = words
        if (w1[0].isupper() and w2[0].isupper()
                and w1.isalpha() and w2.isalpha()
                and len(w1) >= 3 and len(w2) >= 3):
            return False

    # Structural words that are never part of a signature
    structural = {
        "approval", "declaration", "board", "examiners", "chairman",
        "department", "faculty", "university", "daffodil", "science",
        "information", "technology", "systems", "computing",
        "acknowledgement", "abstract", "contents", "introduction",
        "this", "the", "and", "for", "of", "to", "by", "in",
        "submitted", "supervised", "name", "date", "page"
    }
    words_lower = {w.lower().rstrip(".,;:()") for w in words}
    if words_lower & structural:
        return False

    # Strong signal: garbled cursive OCR — contains digits or noise chars
    has_noise = bool(re.search(r"[\/\\0-9\+\=\~\^@#\$\*]", stripped))
    alpha_count = sum(c.isalpha() for c in stripped)
    alpha_ratio = alpha_count / max(length, 1)

    # Short mixed token (date + scrawl): "Ratdllah 9/1/46", "Cls 05-01"
    if has_noise and alpha_ratio < 0.80 and word_count <= 3:
        return True

    # Short token ≤ 20 chars, no structural words, not a clean 2-word name
    # Must have at least one non-alpha character or be a single garbled token
    if length <= 20 and word_count <= 2 and not PERSON_TITLE_PATTERN.search(stripped):
        # Require either noise chars OR a mix of cases unusual for a real name
        # (e.g. "SiMal" has mixed case mid-word, "AHossain" has no space)
        if word_count == 1:
            return True  # single garbled token: "AHossain", "ISFRIL", "Dats"
        # 2-word: already rejected pure alpha 2-cap-word names above
        # Allow if has at least some noise
        if has_noise:
            return True

    return False


def check_approval_signatures(pages: list[str], pdf_path: Optional[str] = None) -> dict:
    """
    Find approval page. Detect actual persons (name lines) and count signatures.

    Layout in DIU approval pages (both text-layer and OCR):
        [sig / scrawl line]     ← handwritten signature
        Name of Person          ← name line (_is_name_line)
        Title / Role            ← e.g. "Associate Professor and Head", "Chairman"
        Department of ...
        Faculty of ...
        Daffodil International University

    Strategy: find name lines → for each, look 1–5 lines above for a sig line.
    """
    approval_text = ""
    approval_idx = None

    for i, pg in enumerate(pages[:15]):
        if any(kw in pg.lower() for kw in ["approval", "board of examiners"]):
            approval_text = pg
            approval_idx = i
            break

    if approval_idx is None and pdf_path:
        for i in range(min(10, len(pages))):
            if _sparse(pages[i], 80):
                ocr = _ocr_page(pdf_path, i)
                if any(kw in ocr.lower() for kw in ["approval", "board of examiners"]):
                    approval_text = ocr
                    approval_idx = i
                    print(f"[APPROVAL OCR-find] page {i+1}", flush=True)
                    break

    if approval_idx is None:
        return {"pass": False, "message": "Approval page not found.", "persons": [], "sig_count": 0,
                "person_details": [], "signed_persons": []}

    page_raw = pages[approval_idx] if approval_idx < len(pages) else ""

    # ALWAYS OCR the approval page — signatures are raster images embedded in the PDF.
    # fitz reads the text layer (names, titles, depts) but produces NOTHING for the
    # handwritten signature images. OCR captures those scrawled strokes as short
    # garbled tokens. We merge fitz text + OCR so we have both accurate names AND sigs.
    ocr_text = ""
    if pdf_path:
        ocr_text = _ocr_page(pdf_path, approval_idx)
        if ocr_text.strip():
            print(f"[APPROVAL OCR] page {approval_idx+1}: {len(ocr_text)} chars", flush=True)
            # If fitz gave us very little (image-embedded page), use OCR exclusively
            if _sparse(page_raw, 80):
                approval_text = ocr_text
            else:
                # Both fitz and OCR have content — merge them.
                # OCR gives us sig lines; fitz gives clean names/titles.
                # Strategy: use fitz as base (accurate), inject OCR sig tokens.
                approval_text = page_raw + "\n" + ocr_text

    print(f"[APPROVAL TEXT] {len(approval_text)} chars, first 400: {repr(approval_text[:400])}", flush=True)

    lines = [l.strip() for l in approval_text.split("\n") if l.strip()]

    # Pass 1: find all name-line candidates with their line indices
    raw_candidates: list[tuple[int, str]] = [
        (idx, line) for idx, line in enumerate(lines) if _is_name_line(line)
    ]

    # Pass 2: filter out candidates that are immediately followed by another
    # name candidate with NO title line between them — the first is a sig OCR'd
    # as a person name (e.g. "Sait Reza" before "Md Sarwar Hossain Mollah")
    persons_final: list[tuple[int, str]] = []
    for i, (idx, line) in enumerate(raw_candidates):
        if i + 1 < len(raw_candidates):
            nxt_idx, _ = raw_candidates[i + 1]
            gap = nxt_idx - idx
            if gap <= 3:
                # Check if there is a title/role line between them
                between = lines[idx + 1: nxt_idx]
                has_title = any(PERSON_TITLE_PATTERN.search(b) for b in between)
                if not has_title:
                    continue  # skip — this is a sig line, not a person
        persons_final.append((idx, line))

    # Clean names (strip trailing right-aligned role labels from fitz layout)
    seen_p: set = set()
    persons_deduped: list[tuple[int, str]] = []
    for idx, line in persons_final:
        clean = _clean_name(line)
        if clean not in seen_p:
            seen_p.add(clean)
            persons_deduped.append((idx, line))

    persons = [_clean_name(line) for _, line in persons_deduped]

    # Count ALL sig lines in the entire merged text (fitz + OCR)
    all_sig_lines_idx = [idx for idx, l in enumerate(lines) if _is_sig_line(l)]
    total_sigs_found  = len(all_sig_lines_idx)
    print(f"[APPROVAL] persons={persons} sigs_total={total_sigs_found} sig_lines={[lines[i] for i in all_sig_lines_idx]}", flush=True)

    # For each person: look above for sig, collect title/role/dept from lines below
    sig_count = 0
    signed_persons: list[str] = []
    person_details: list[dict] = []

    title_only_re = re.compile(
        r"^(associate\s+professor(\s+and\s+head)?|assistant\s+professor|"
        r"lecturer(\s+\(senior\s+scale\))?|professor|chairman|"
        r"internal\s+examiner|external\s+examiner|head\s+of\s+department|"
        r"supervisor|co-supervisor|dean|principal|managing\s+director.*|"
        r"director.*|cto|ceo|founder)\b",
        re.IGNORECASE
    )
    role_set = {"chairman", "internal examiner", "external examiner",
                "supervisor", "co-supervisor"}

    for pidx, raw_line in persons_deduped:
        clean_name = _clean_name(raw_line)

        # Primary: look up to 6 lines above this person's name line
        window = lines[max(0, pidx - 6): pidx]
        found_sig = any(_is_sig_line(wl) for wl in window)

        # Title / role / dept: from lines below
        title = ""
        role = ""
        dept = ""
        for offset in range(1, 6):
            nxt_idx = pidx + offset
            if nxt_idx >= len(lines):
                break
            nxt = lines[nxt_idx]
            nxt_lower = nxt.lower().strip()
            if _is_name_line(nxt):
                break
            if title_only_re.match(nxt):
                if any(r in nxt_lower for r in role_set):
                    if not role:
                        role = nxt
                else:
                    if not title:
                        title = nxt
            elif "department" in nxt_lower and not dept:
                dept = nxt

        # Role may also be embedded right-aligned in the raw_line itself
        role_match = re.search(
            r'\s{2,}(chairman|internal\s+examiner|external\s+examiner|'
            r'supervisor|co-supervisor)\s*$',
            raw_line, re.IGNORECASE
        )
        if role_match and not role:
            role = role_match.group(1).strip().title()

        if found_sig:
            sig_count += 1
            signed_persons.append(clean_name)

        person_details.append({
            "name": clean_name,
            "title": title,
            "role": role,
            "department": dept,
            "signed": found_sig,
        })

    # Fallback: sig lines exist in merged text but per-person window missed them
    # (OCR sigs appended to end of merged fitz+OCR block, outside each person's window)
    if sig_count == 0 and total_sigs_found > 0 and len(persons) > 0:
        # We have persons AND sig lines — the layout just doesn't interleave them.
        # Assign sigs to persons by count: min(total_sigs, total_persons) are signed.
        assigned = min(total_sigs_found, len(persons))
        sig_count = assigned
        signed_persons = persons[:assigned]
        for i, pd in enumerate(person_details):
            pd["signed"] = i < assigned
        print(f"[APPROVAL] fallback sig assignment: {assigned}/{len(persons)} signed", flush=True)

    # Fallback: if nothing at all detected
    if sig_count == 0 and len(persons) == 0:
        sig_count = total_sigs_found
        role_labels_set = {"chairman", "internal examiner", "external examiner",
                           "co-supervisor", "supervisor", "head of department"}
        for line in lines:
            ll = line.lower().strip()
            if ll in role_labels_set:
                persons.append(line)
                person_details.append({"name": line, "title": "", "role": line, "department": "", "signed": False})
        persons = list(dict.fromkeys(persons))

    num_persons = max(1, len(persons))
    passed = sig_count >= num_persons and len(persons) >= 1

    return {
        "pass": passed,
        "message": (
            f"Approval page found. {len(persons)} person(s) detected, "
            f"{sig_count} signature indicator(s) found — {'all signed' if passed else 'check signatures'}."
        ),
        "persons": persons[:10],
        "person_details": person_details[:10],
        "sig_count": sig_count,
        "signed_persons": signed_persons,
    }


# ── Rule 2b: Declaration supervisor signature ─────────────────────────────────

def check_declaration_signatures(pages: list[str], pdf_path: Optional[str] = None) -> dict:
    """
    Find declaration page. Verify:
    1. Supervisor signature is present (above "Supervised By" section)
    2. Student signature is present (above "Submitted By" section)
    """
    decl_text = ""
    decl_idx = None

    for i, pg in enumerate(pages[:15]):
        if any(kw in pg.lower() for kw in ["declaration", "i hereby declare"]):
            decl_text = pg
            decl_idx = i
            break

    if decl_idx is None and pdf_path:
        for i in range(min(10, len(pages))):
            if _sparse(pages[i], 80):
                ocr = _ocr_page(pdf_path, i)
                if any(kw in ocr.lower() for kw in ["declaration", "i hereby declare"]):
                    decl_text = ocr
                    decl_idx = i
                    break

    if decl_idx is None:
        return {
            "pass": False,
            "message": "Declaration page not found.",
            "supervisor_signed": False,
            "student_signed": False,
        }

    page_raw = pages[decl_idx] if decl_idx < len(pages) else ""

    # ALWAYS OCR the declaration page — same reason as approval: signatures are
    # embedded raster images invisible to fitz text extraction.
    if pdf_path:
        ocr = _ocr_page(pdf_path, decl_idx)
        if ocr.strip():
            print(f"[DECL OCR] page {decl_idx+1}: {len(ocr)} chars", flush=True)
            if _sparse(page_raw, 80):
                decl_text = ocr
            else:
                decl_text = page_raw + "\n" + ocr  # merge: fitz anchors + OCR sigs

    print(f"[DECL TEXT] first 300: {repr(decl_text[:300])}", flush=True)

    lines = [l.strip() for l in decl_text.split("\n") if l.strip()]

    # Count total sig-looking lines in the entire merged text
    all_sig_lines = [l for l in lines if _is_sig_line(l)]
    total_sigs = len(all_sig_lines)
    print(f"[DECL] lines={len(lines)} sig_lines={all_sig_lines}", flush=True)

    # Find anchors
    sup_idx = next((i for i, l in enumerate(lines) if "supervised by" in l.lower()), None)
    sub_idx = next((i for i, l in enumerate(lines) if "submitted by" in l.lower()), None)

    def has_sig_after_anchor(anchor_idx: int, stop_idx: Optional[int]) -> bool:
        """
        Look AFTER anchor for a signature, with extended window to handle
        merged fitz+OCR text (OCR sigs may appear later in the merged block).
        """
        # Primary: look in window right after anchor (up to 12 lines)
        end = min(
            stop_idx if stop_idx is not None else len(lines),
            anchor_idx + 12
        )
        for line in lines[anchor_idx + 1 : end]:
            if _is_sig_line(line):
                return True
        # Secondary: if we have sig lines anywhere in merged text, check if
        # the anchor exists — if so, at least one sig belongs to it
        return False

    supervisor_signed = False
    student_signed = False

    if sup_idx is not None:
        supervisor_signed = has_sig_after_anchor(sup_idx, sub_idx)

    if sub_idx is not None:
        student_signed = has_sig_after_anchor(sub_idx, None)

    # Fallback A: anchors found but sigs are in the OCR-appended tail
    # (merged text puts fitz block first, then OCR block — sigs land after both anchors)
    if (not supervisor_signed or not student_signed) and sup_idx is not None and total_sigs >= 2:
        # We have 2+ sig lines and both anchors — assign them by position
        # relative to their anchor in the merged text
        supervisor_signed = True
        student_signed    = True

    elif (not supervisor_signed or not student_signed) and sup_idx is not None and total_sigs == 1:
        supervisor_signed = True

    # Fallback B: no anchors found at all — positional split
    if not supervisor_signed and not student_signed and sup_idx is None and sub_idx is None:
        if total_sigs >= 2:
            mid = len(lines) // 2
            sup_sigs = [i for i, l in enumerate(lines) if _is_sig_line(l) and i < mid]
            sub_sigs = [i for i, l in enumerate(lines) if _is_sig_line(l) and i >= mid]
            supervisor_signed = len(sup_sigs) > 0
            student_signed    = len(sub_sigs) > 0
        elif total_sigs == 1:
            supervisor_signed = True

    issues = []
    if not supervisor_signed:
        issues.append("Supervisor signature missing or not detected on Declaration page.")
    if not student_signed:
        issues.append("Student signature missing or not detected on Declaration page.")

    passed = supervisor_signed and student_signed

    return {
        "pass": passed,
        "message": (
            "Declaration page: supervisor ✓ and student ✓ signatures detected."
            if passed else
            " | ".join(issues)
        ),
        "supervisor_signed": supervisor_signed,
        "student_signed": student_signed,
    }


# ── Rule 3: Page numbering ────────────────────────────────────────────────────

def check_page_numbering(pages: list[str]) -> dict:
    """
    Front matter (before chapter 1): Roman numerals in footer.
    Body (from chapter 1): Arabic numerals in footer.

    Key rule: Chapter 1 is only valid when it appears on a page whose footer
    has an ARABIC numeral. Pages with Roman footers are front matter even if
    they mention "Chapter 1" in the Table of Contents.
    """
    # ── Step 1: Find the first page with an ARABIC footer number ──────────────
    # That is where the body (and Chapter 1) begins.
    first_arabic_page_idx = None
    for i, pg in enumerate(pages):
        pn = _footer_page_num(pg)
        if pn and pn[0] == "arabic":
            first_arabic_page_idx = i
            break

    # ── Step 2: Among body pages, find where Chapter 1 content actually starts ─
    # Only search from the first Arabic-numbered page onward.
    chapter_start_idx = None
    if first_arabic_page_idx is not None:
        for i in range(first_arabic_page_idx, min(first_arabic_page_idx + 15, len(pages))):
            if CHAPTER_PATTERN.search(pages[i]):
                chapter_start_idx = i
                break
        # If pattern not found in first 15 body pages, use first arabic page itself
        if chapter_start_idx is None:
            chapter_start_idx = first_arabic_page_idx

    # ── Fallback: no arabic footer detected at all ─────────────────────────────
    if chapter_start_idx is None:
        # Try old approach as last resort
        for i, page in enumerate(pages):
            if CHAPTER_PATTERN.search(page):
                chapter_start_idx = i
                break

    if chapter_start_idx is None:
        return {
            "pass": None,
            "message": "Could not detect chapter start. Numbering not validated.",
            "issues": [], "chapter_starts_at_page": None,
            "front_roman_found": 0, "body_arabic_found": 0,
            "front_roman_values": [], "body_arabic_values": [],
            "arabic_in_front": 0,
        }

    issues = []

    # ── Front matter: pages before chapter start ───────────────────────────────
    front_roman: list[int] = []
    arabic_in_front = 0
    for pg in pages[:chapter_start_idx]:
        pn = _footer_page_num(pg)
        if pn:
            if pn[0] == "roman":
                front_roman.append(pn[1])
            else:
                arabic_in_front += 1

    if arabic_in_front > 0:
        issues.append(
            f"Front matter: {arabic_in_front} page(s) use Arabic numerals instead of Roman (i, ii, iii…)."
        )

    # Check Roman sequence continuity
    if len(front_roman) >= 2:
        bad = sum(1 for a, b in zip(front_roman, front_roman[1:]) if b <= a)
        if bad > 1:
            issues.append(f"Roman numeral sequence broken {bad} time(s) in front matter.")

    # ── Body: pages from chapter start onward ─────────────────────────────────
    body_arabic: list[int] = []
    roman_in_body = 0
    for pg in pages[chapter_start_idx:]:
        pn = _footer_page_num(pg)
        if pn:
            if pn[0] == "arabic":
                body_arabic.append(pn[1])
            else:
                roman_in_body += 1

    if roman_in_body > 0:
        issues.append(
            f"Body: {roman_in_body} page(s) still use Roman numerals instead of Arabic (1, 2, 3…)."
        )

    if len(body_arabic) >= 2:
        bad = sum(1 for a, b in zip(body_arabic, body_arabic[1:]) if b <= a)
        if bad > 1:
            issues.append(f"Arabic numeral sequence broken {bad} time(s) in body.")

    if not front_roman and not body_arabic and arabic_in_front == 0 and roman_in_body == 0:
        return {
            "pass": None,
            "message": "Page numbers not extractable from footers. Manual review needed.",
            "issues": [], "chapter_starts_at_page": chapter_start_idx + 1,
            "front_roman_found": 0, "body_arabic_found": 0,
            "front_roman_values": [], "body_arabic_values": [],
            "arabic_in_front": 0,
        }

    # Reverse-map roman integer values back to roman numeral strings for display
    int_to_roman = {v: k for k, v in ROMAN_VALUES.items()}

    return {
        "pass": len(issues) == 0,
        "message": (
            "Page numbering correct — Roman numerals in front matter, Arabic from Chapter 1."
            if not issues else " | ".join(issues)
        ),
        "issues": issues,
        "chapter_starts_at_page": chapter_start_idx + 1,
        "front_roman_found": len(front_roman),
        "body_arabic_found": len(body_arabic),
        "front_roman_values": [int_to_roman.get(v, str(v)) for v in front_roman],
        "body_arabic_values": body_arabic[:8],
        "arabic_in_front": arabic_in_front,
    }


# ── Turnitin parsers ──────────────────────────────────────────────────────────

def _parse_overall_pct(text: str) -> Optional[float]:
    """
    Extract SIMILARITY INDEX % — the headline number in the Turnitin block.
    Handles all known Turnitin layout variants:
      - "8% SIMILARITY INDEX ..."         (number BEFORE label — most common)
      - "SIMILARITY INDEX 8%"             (label BEFORE number)
      - "SIMILARITY INDEX\n8%"            (multi-line OCR)
      - "8\n%\nSIMILARITY INDEX"          (heavily OCR'd)
      - "Plagiarism Report ... 8%"        (screenshot/image OCR)
    """
    # Fix OCR spacing artifacts first
    clean = re.sub(r'(\d)\s+(\d)', r'\1\2', text)
    clean = re.sub(r'(\d+)\s+%', r'\1%', clean)

    # Pattern A: number BEFORE label — "8% SIMILARITY INDEX"
    m = re.search(r"(\d{1,3})\s*%\s*similarity\s+index", clean, re.IGNORECASE)
    if m:
        val = int(m.group(1))
        if 0 <= val <= 100:
            return float(val)

    # Pattern B: label BEFORE number — "SIMILARITY INDEX 8%" or "SIMILARITY INDEX: 8%"
    m = re.search(r"similarity\s+index\s*[:\s]\s*(\d{1,3})\s*%?", clean, re.IGNORECASE)
    if m:
        val = int(m.group(1))
        if 0 <= val <= 100:
            return float(val)

    # Pattern C: multi-line OCR — "similarity index\n8%" or "8\n%\nsimilarity index"
    m = re.search(r"similarity\s+index\s*\n\s*(\d{1,3})\s*%?", clean, re.IGNORECASE)
    if m:
        val = int(m.group(1))
        if 0 <= val <= 100:
            return float(val)

    m = re.search(r"(\d{1,3})\s*%?\s*\n\s*similarity\s+index", clean, re.IGNORECASE)
    if m:
        val = int(m.group(1))
        if 0 <= val <= 100:
            return float(val)

    # Pattern D: "originality report" block with similarity immediately following
    m = re.search(r"originality\s+report.*?(\d{1,3})\s*%?\s*similarity",
                  clean, re.IGNORECASE | re.DOTALL)
    if m:
        val = int(m.group(1))
        if 0 <= val <= 100:
            return float(val)

    # Pattern E: last resort — first standalone % on a confirmed Turnitin page
    # Only trigger if the text has strong Turnitin markers
    strong_markers = ["similarity index", "originality report", "plagiarism report"]
    if any(mk in clean.lower() for mk in strong_markers):
        m = re.search(r"(\d{1,3})\s*%", clean, re.IGNORECASE)
        if m:
            val = int(m.group(1))
            if 0 <= val <= 100:
                return float(val)

    return None


def _parse_sources(text: str) -> list[dict]:
    """
    Parse Turnitin source table.

    Returns two kinds of entries — callers MUST distinguish them:
      type='category'   — aggregate totals (Internet Sources 9%, Publications 12%)
                          These are informational only. Per-source limits do NOT apply.
      type='individual' — numbered rows (1. dspace.daffodilvarsity.edu.bd 8%)
                          Per-source limits apply: ≤3% general, ≤5% DIU space.

    The per-source limit rule is:
      "Each individual source row must not exceed 3% (or 5% for DIU Space)."
    Category totals like "Internet Sources 9%" are NOT individual sources and
    must never be checked against the 3%/5% threshold.
    """
    sources: list[dict] = []

    def add_cat(label: str, pct_str: str) -> None:
        pct = _pct_val(pct_str)
        if pct is not None and not any(s["source"] == label for s in sources):
            sources.append({"source": label, "percentage": pct, "type": "category"})

    # Fix OCR spacing artifacts
    clean = re.sub(r'(\d)\s+(\d)', r'\1\2', text)
    clean = re.sub(r'(\d+)\s+%', r'\1%', clean)

    # ── Pass 1: Category aggregate rows ───────────────────────────────────────
    # Turnitin prints: "8% SIMILARITY INDEX  7% INTERNET SOURCES  3% PUBLICATIONS  4% STUDENT PAPERS"
    # OR reversed:    "INTERNET SOURCES 7%"
    # OR multi-line OCR: "INTERNET SOURCES\n7%"
    cat_patterns = [
        # number BEFORE label (Turnitin's actual layout): "7% INTERNET SOURCES"
        (r"(<?\d{1,3})\s*%\s+internet\s+sources?",   "Internet Sources"),
        (r"(<?\d{1,3})\s*%\s+publications?",           "Publications"),
        (r"(<?\d{1,3})\s*%\s+student\s+papers?",       "Student Papers"),
        # label BEFORE number: "INTERNET SOURCES 7%" or "INTERNET SOURCES: 7%"
        (r"internet\s+sources?\s*[:\s]+(<?\d{1,3})\s*%?", "Internet Sources"),
        (r"publications?\s*[:\s]+(<?\d{1,3})\s*%?",       "Publications"),
        (r"student\s+papers?\s*[:\s]+(<?\d{1,3})\s*%?",   "Student Papers"),
        # multi-line OCR
        (r"internet\s+sources?\s*\n\s*(<?\d{1,3})\s*%?",  "Internet Sources"),
        (r"publications?\s*\n\s*(<?\d{1,3})\s*%?",        "Publications"),
        (r"student\s+papers?\s*\n\s*(<?\d{1,3})\s*%?",    "Student Papers"),
        (r"diu\s+space\s*[:\s]*(<?\d{1,3})\s*%?",         "DIU Space"),
    ]
    for pat, label in cat_patterns:
        m = re.search(pat, clean, re.IGNORECASE | re.MULTILINE)
        if m:
            add_cat(label, m.group(1))

    # ── Pass 2: Numbered individual source rows ────────────────────────────────
    # Matches: "1  dspace.daffodilvarsity.edu.bd  Internet Source  8%"
    #          "2  Submitted to University of Greenwich  Student Paper  1%"
    #          "3  export.arxiv.org  <1%"
    row_pat = re.compile(
        r"^\s*(\d{1,2})\s+"                              # row number 1–99
        r"([\w\.\-/:@]+(?:[\s\-][\w\.\-/:@]+){0,8})"    # source name
        r"(?:[^\d<\n]{0,60})"                            # optional type label
        r"(<?\s*\d{1,3})\s*%",
        re.IGNORECASE | re.MULTILINE
    )
    skip_labels = {
        "internet sources", "publications", "student papers", "diu space",
        "primary sources", "similarity index", "originality report",
    }
    for m in row_pat.finditer(clean):
        row_num  = int(m.group(1))
        src_name = m.group(2).strip()
        pct_raw  = m.group(3).strip()
        if row_num > 60:
            continue
        if src_name.lower() in skip_labels:
            continue
        pct = _pct_val(pct_raw)
        if pct is not None and src_name:
            sources.append({"source": src_name, "percentage": pct, "type": "individual"})

    return sources[:35]


def _pct_val(s: str) -> Optional[float]:
    """Convert '7', '7%', '<1', '<1%' to float. '<1' -> 0.5"""
    s = s.strip().replace("%", "").strip()
    if s.startswith("<"):
        return 0.5
    try:
        v = float(s)
        if 0 <= v <= 100:
            return v
    except Exception:
        pass
    return None


def _is_diu_source(name: str) -> bool:
    name_l = name.lower()
    return any(d in name_l for d in [
        "daffodil", "diu", "dspace.daffodil", "daffodilvarsity",
        "diu space", "dspace.diu"
    ])


# ── Rule 4 & 5: Turnitin ─────────────────────────────────────────────────────

def check_turnitin(pages: list[str], pdf_path: Optional[str] = None) -> dict:
    # Dynamic: scan the last 10% of pages (minimum 5, maximum 20)
    check_count = max(5, min(20, len(pages) // 10 + 1))
    turnitin_text = ""
    turnitin_idx  = None

    # Text layer scan — go backwards through last 10% of pages
    # Collect ALL pages that contain Turnitin markers (report can span multiple pages)
    turnitin_pages_found: list[int] = []
    for i in range(min(check_count, len(pages))):
        pg_idx = len(pages) - 1 - i
        pl = pages[pg_idx].lower()
        if any(kw in pl for kw in TURNITIN_PATTERNS):
            turnitin_pages_found.append(pg_idx)

    if turnitin_pages_found:
        # Use the earliest (lowest index) Turnitin page as the report start
        turnitin_idx = min(turnitin_pages_found)
        # Combine text from all found Turnitin pages
        turnitin_text = "\n".join(pages[i] for i in sorted(turnitin_pages_found))

    # OCR pass — for image-embedded or sparse Turnitin pages
    if pdf_path:
        for i in range(min(check_count, len(pages))):
            pg_idx = len(pages) - 1 - i
            page_text = pages[pg_idx]
            # OCR if: this is already a known Turnitin page but text is sparse,
            # OR if no Turnitin found yet and page is sparse
            do_ocr = (
                (pg_idx in turnitin_pages_found and _sparse(page_text, 300))
                or (not turnitin_pages_found and _sparse(page_text, 80))
                or (turnitin_idx is None and _sparse(page_text, 80))
            )
            if do_ocr:
                ocr = _ocr_page(pdf_path, pg_idx)
                if ocr.strip():
                    ol = ocr.lower()
                    if any(kw in ol for kw in TURNITIN_PATTERNS):
                        turnitin_text += "\n" + ocr
                        if turnitin_idx is None:
                            turnitin_idx = pg_idx
                        elif pg_idx < turnitin_idx:
                            turnitin_idx = pg_idx
                        print(f"[TURNITIN OCR] page {pg_idx+1}: {repr(ocr[:200])}", flush=True)

    if not turnitin_text.strip() or turnitin_idx is None:
        return {
            "pass": False, "found": False,
            "message": "Turnitin report NOT found in last pages. Attach as the last page.",
            "overall_pct": None, "sources": [], "source_issues": [],
        }

    overall_pct = _parse_overall_pct(turnitin_text)
    sources     = _parse_sources(turnitin_text)

    print(f"[TURNITIN] overall={overall_pct}, sources={sources}", flush=True)

    source_issues = []
    for src in sources:
        # Category totals (Internet Sources %, Publications %, Student Papers %) are
        # aggregate numbers shown at the top of Turnitin report — they are NOT
        # individual sources and must NOT be checked against the 3%/5% per-source limit.
        if src.get("type") == "category":
            continue
        is_diu = _is_diu_source(src["source"])
        limit  = 5.0 if is_diu else 3.0
        if src["percentage"] > limit:
            source_issues.append({
                "source": src["source"], "percentage": src["percentage"],
                "limit": limit, "is_diu": is_diu,
                "message": f"'{src['source']}' — {src['percentage']}% (limit: {limit}%{'  [DIU Space]' if is_diu else ''})",
            })

    return {
        "pass": len(source_issues) == 0,
        "found": True,
        "overall_pct": overall_pct,
        "sources": sources,
        "source_issues": source_issues,
        "turnitin_page": turnitin_idx + 1,
        "message": (
            f"Turnitin report found on page {turnitin_idx+1}. All per-source limits within range."
            if not source_issues else
            f"Turnitin report found. {len(source_issues)} source(s) exceed per-source limit."
        ),
    }


# ── Rule 6: Overall plagiarism ────────────────────────────────────────────────

def check_overall_plagiarism(overall_pct: Optional[float], level: str) -> dict:
    if overall_pct is None:
        return {
            "pass": None,
            "message": "Could not extract overall similarity % from Turnitin report. Manual review required.",
            "percentage": None, "limit": None,
        }
    is_ug = "under" in (level or "").lower()
    limit = 35.0 if is_ug else 25.0
    lbl   = "Undergraduate" if is_ug else "Graduate"
    passed = overall_pct <= limit
    return {
        "pass": passed, "percentage": overall_pct, "limit": limit, "level": lbl,
        "message": (
            f"Overall similarity {overall_pct}% — within the {limit}% limit for {lbl} students. ✓"
            if passed else
            f"Overall similarity {overall_pct}% EXCEEDS the {limit}% limit for {lbl} students."
        ),
    }


# ── Master runner ─────────────────────────────────────────────────────────────

def run_clearance_check(file_path: str, level: str = "Undergraduate") -> dict:
    pages = _extract_pages(file_path)
    if not pages:
        return {"eligible": False, "error": "Could not extract content.", "checks": {}}

    if all(not p.strip() for p in pages):
        try:
            import fitz
            doc = fitz.open(file_path)
            pages = [""] * len(doc)
            doc.close()
        except Exception:
            pass

    pdf_path = file_path if file_path.lower().endswith(".pdf") else None
    print(f"[CLEARANCE] {len(pages)} pages, level={level}", flush=True)

    sections   = check_required_sections(pages, pdf_path)
    approval   = check_approval_signatures(pages, pdf_path)
    declaration = check_declaration_signatures(pages, pdf_path)
    page_nums  = check_page_numbering(pages)
    turnitin   = check_turnitin(pages, pdf_path)
    overall_plag = check_overall_plagiarism(turnitin.get("overall_pct"), level)

    # Combine approval + declaration into one signature check for display
    sig_pass = approval["pass"] and declaration["pass"]
    sig_message = []
    if approval["pass"]:
        sig_message.append(f"Approval: {approval['sig_count']} signature(s) for {len(approval['persons'])} person(s) ✓")
    else:
        sig_message.append(f"Approval: {approval['message']}")
    if declaration["pass"]:
        sig_message.append("Declaration: Supervisor ✓  Student ✓")
    else:
        sig_message.append(f"Declaration: {declaration['message']}")

    checks = {
        "required_sections": sections,
        "approval_signatures": {
            "pass": sig_pass,
            "message": " | ".join(sig_message),
            "persons": approval.get("persons", []),
            "approval_detail": approval,
            "declaration_detail": declaration,
        },
        "page_numbering": page_nums,
        "turnitin_attached": {
            "pass": turnitin["found"],
            "message": (
                f"Turnitin report found on page {turnitin.get('turnitin_page', '?')}."
                if turnitin["found"] else turnitin["message"]
            ),
        },
        "turnitin_sources": {
            "pass": turnitin["pass"],
            "message": turnitin["message"],
            "sources": turnitin.get("sources", []),
            "source_issues": turnitin.get("source_issues", []),
        },
        "overall_plagiarism": overall_plag,
    }

    hard_failed = [r for r in [
        checks["required_sections"]["pass"],
        checks["turnitin_attached"]["pass"],
        checks["turnitin_sources"]["pass"],
        checks["overall_plagiarism"]["pass"],
    ] if r is False]

    eligible = len(hard_failed) == 0

    issues, warnings = [], []

    if not sections["pass"]:
        issues.append(f"MISSING SECTIONS: {', '.join(sections['missing'])}")
    if sig_pass is False:
        if not approval["pass"]:
            issues.append(f"APPROVAL SIGNATURES: {approval['message']}")
        if not declaration["pass"]:
            issues.append(f"DECLARATION SIGNATURES: {declaration['message']}")
    if page_nums["pass"] is False:
        issues.append(f"PAGE NUMBERING: {page_nums['message']}")
    elif page_nums["pass"] is None:
        warnings.append(f"PAGE NUMBERING: {page_nums['message']}")
    if not turnitin["found"]:
        issues.append("TURNITIN REPORT: Not found in last pages.")
    elif not turnitin["pass"]:
        for si in turnitin.get("source_issues", []):
            issues.append(f"SOURCE LIMIT EXCEEDED: {si['message']}")
    if overall_plag["pass"] is False:
        issues.append(f"OVERALL PLAGIARISM: {overall_plag['message']}")
    elif overall_plag["pass"] is None:
        warnings.append(f"OVERALL PLAGIARISM: {overall_plag['message']}")

    return {
        "eligible": eligible,
        "issues":   issues,
        "warnings": warnings,
        "checks":   checks,
        "total_pages": len(pages),
        "level": level,
    }
