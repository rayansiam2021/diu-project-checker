"""
services/pdf_report.py — Beautiful Turnitin-style PDF report generator.

Design inspired by Turnitin's actual report layout:
- Dark navy header with score circles
- Clean white content pages
- Color-coded similarity bands
- Source attribution table
- Full document with inline highlights
- Improvement guide on final page
"""
from __future__ import annotations

import datetime
import io
import json
import textwrap

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import inch, mm
from reportlab.pdfgen import canvas
from reportlab.platypus import Table, TableStyle

from database import ReportCheck, User
from services.reasoning import compute_guidelines, confidence_badge

# ── Brand colors (Turnitin-inspired) ────────────────────────────────────────
NAVY        = colors.HexColor("#0D1B2A")
NAVY_LIGHT  = colors.HexColor("#1A2E45")
ACCENT_BLUE = colors.HexColor("#1565C0")
WHITE       = colors.white
OFF_WHITE   = colors.HexColor("#F8F9FA")
LIGHT_GRAY  = colors.HexColor("#E9ECEF")
MID_GRAY    = colors.HexColor("#6C757D")
DARK_GRAY   = colors.HexColor("#343A40")

SIM_LOW     = colors.HexColor("#2E7D32")   # green
SIM_MID     = colors.HexColor("#F57C00")   # orange
SIM_HIGH    = colors.HexColor("#C62828")   # red

AI_LOW      = colors.HexColor("#1565C0")   # blue
AI_MID      = colors.HexColor("#6A1B9A")   # purple
AI_HIGH     = colors.HexColor("#AD1457")   # deep pink

HL_PLAG     = colors.HexColor("#FFCDD2")   # light red highlight
HL_AI       = colors.HexColor("#BBDEFB")   # light blue highlight
HL_POSSIBLE = colors.HexColor("#FFE0B2")   # light orange highlight

SOURCE_PALETTE = [
    colors.HexColor("#C62828"),
    colors.HexColor("#1565C0"),
    colors.HexColor("#2E7D32"),
    colors.HexColor("#F57C00"),
    colors.HexColor("#6A1B9A"),
    colors.HexColor("#00838F"),
    colors.HexColor("#AD1457"),
    colors.HexColor("#4527A0"),
]

W, H = A4   # 595 x 842 pts
MARGIN = 0.75 * inch
CONTENT_W = W - 2 * MARGIN


# ── Utilities ────────────────────────────────────────────────────────────────

def _wrap(s: str, width: int) -> list[str]:
    return textwrap.wrap(str(s), width) or [""]


def _sim_color(pct: float):
    if pct < 20: return SIM_LOW
    if pct < 40: return SIM_MID
    return SIM_HIGH


def _ai_color(pct: float):
    if pct < 20: return AI_LOW
    if pct < 50: return AI_MID
    return AI_HIGH


def _sim_label(pct: float) -> str:
    if pct < 20: return "Low"
    if pct < 40: return "Moderate"
    return "High"


def _page_footer(c: canvas.Canvas, page_num: int, report_id: int):
    c.saveState()
    c.setFillColor(LIGHT_GRAY)
    c.rect(0, 0, W, 0.45 * inch, fill=1, stroke=0)
    c.setFillColor(MID_GRAY)
    c.setFont("Helvetica", 8)
    c.drawString(MARGIN, 0.16 * inch, f"DIU Project Checker  •  Report #{report_id}  •  Generated {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    c.drawRightString(W - MARGIN, 0.16 * inch, f"Page {page_num}")
    c.restoreState()


def _section_header(c: canvas.Canvas, y: float, title: str, subtitle: str = "") -> float:
    c.setFillColor(NAVY)
    c.roundRect(MARGIN, y - 0.08 * inch, CONTENT_W, 0.42 * inch, 4, fill=1, stroke=0)
    c.setFillColor(WHITE)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(MARGIN + 10, y + 0.18 * inch, title)
    if subtitle:
        c.setFont("Helvetica", 9)
        c.setFillColor(LIGHT_GRAY)
        c.drawRightString(W - MARGIN - 8, y + 0.18 * inch, subtitle)
    c.setFillColor(colors.black)
    return y - 0.55 * inch


def _score_donut(c: canvas.Canvas, cx: float, cy: float, r: float,
                 pct: float, color, label: str, sublabel: str = ""):
    """Draw a filled circle score indicator (Turnitin style)."""
    # Outer ring
    c.setStrokeColor(LIGHT_GRAY)
    c.setLineWidth(3)
    c.circle(cx, cy, r, stroke=1, fill=0)

    # Filled circle
    c.setFillColor(color)
    c.setLineWidth(0)
    c.circle(cx, cy, r - 3, stroke=0, fill=1)

    # Percentage text
    c.setFillColor(WHITE)
    font_size = 22 if pct < 100 else 18
    c.setFont("Helvetica-Bold", font_size)
    c.drawCentredString(cx, cy - 4, f"{int(round(pct))}%")

    # Labels below
    c.setFillColor(DARK_GRAY)
    c.setFont("Helvetica-Bold", 10)
    c.drawCentredString(cx, cy - r - 16, label)
    if sublabel:
        c.setFont("Helvetica", 8)
        c.setFillColor(MID_GRAY)
        c.drawCentredString(cx, cy - r - 27, sublabel)
    c.setFillColor(colors.black)
    c.setLineWidth(1)


def _progress_bar(c: canvas.Canvas, x: float, y: float, w: float, h: float,
                  pct: float, fill_color, bg_color=LIGHT_GRAY, radius: float = 3):
    pct = max(0.0, min(100.0, float(pct)))
    c.setFillColor(bg_color)
    c.roundRect(x, y, w, h, radius, fill=1, stroke=0)
    if pct > 0:
        c.setFillColor(fill_color)
        c.roundRect(x, y, w * (pct / 100.0), h, radius, fill=1, stroke=0)
    c.setFillColor(colors.black)


def _pill(c: canvas.Canvas, x: float, y: float, w: float, h: float,
          fill, text: str, text_color=WHITE, font_size: int = 9):
    c.setFillColor(fill)
    c.roundRect(x, y, w, h, h / 2, fill=1, stroke=0)
    c.setFillColor(text_color)
    c.setFont("Helvetica-Bold", font_size)
    c.drawCentredString(x + w / 2, y + h / 2 - font_size / 2 + 1, text)
    c.setFillColor(colors.black)


def _info_row(c: canvas.Canvas, x: float, y: float, label: str, value: str,
              label_w: float = 1.4 * inch) -> float:
    c.setFont("Helvetica-Bold", 9)
    c.setFillColor(MID_GRAY)
    c.drawString(x, y, label.upper())
    c.setFont("Helvetica", 10)
    c.setFillColor(DARK_GRAY)
    c.drawString(x + label_w, y, value)
    return y - 0.22 * inch


def _top_sources_from_spans(spans: list[dict], max_items: int = 8) -> list[dict]:
    agg: dict[str, dict] = {}
    total = 0
    for sp in spans:
        if not isinstance(sp, dict) or sp.get("type") != "plagiarism":
            continue
        s, e = int(sp.get("start") or 0), int(sp.get("end") or 0)
        if e <= s:
            continue
        total += (e - s)
        src   = sp.get("source") if isinstance(sp.get("source"), dict) else {}
        link  = src.get("link") or ""
        title = src.get("title") or link or "Unknown source"
        key   = link or title
        agg.setdefault(key, {"title": title, "link": link, "chars": 0, "count": 0})
        agg[key]["chars"]  += (e - s)
        agg[key]["count"]  += 1
    rows = sorted(agg.values(), key=lambda x: x["chars"], reverse=True)
    return [
        {
            "rank":         i,
            "title":        r["title"],
            "link":         r["link"],
            "contribution": round(r["chars"] / total * 100, 2) if total else 0.0,
            "matches":      r["count"],
        }
        for i, r in enumerate(rows[:max_items], start=1)
    ]


# ── PAGE 1: Cover ────────────────────────────────────────────────────────────

def _page_cover(c: canvas.Canvas, r: ReportCheck, u: User,
                plag: float, ai: float, badge: str, limit: float, page: int):

    # Full navy header band
    c.setFillColor(NAVY)
    c.rect(0, H - 2.2 * inch, W, 2.2 * inch, fill=1, stroke=0)

    # Institution name top-left
    c.setFillColor(colors.HexColor("#90CAF9"))
    c.setFont("Helvetica", 9)
    c.drawString(MARGIN, H - 0.35 * inch, "DAFFODIL INTERNATIONAL UNIVERSITY")

    # Report title
    c.setFillColor(WHITE)
    c.setFont("Helvetica-Bold", 22)
    c.drawString(MARGIN, H - 0.72 * inch, "Similarity Report")
    c.setFont("Helvetica", 11)
    c.setFillColor(colors.HexColor("#90CAF9"))
    c.drawString(MARGIN, H - 0.97 * inch, "Academic integrity analysis — DIU Project Checker")

    # Score circles (right side of header)
    _score_donut(c, W - 1.5 * inch, H - 1.25 * inch, 0.52 * inch,
                 plag, _sim_color(plag), "Similarity", _sim_label(plag))
    _score_donut(c, W - 3.0 * inch, H - 1.25 * inch, 0.52 * inch,
                 ai, _ai_color(ai), "AI Writing", "")

    # Divider line under header
    c.setStrokeColor(ACCENT_BLUE)
    c.setLineWidth(2)
    c.line(0, H - 2.2 * inch, W, H - 2.2 * inch)
    c.setLineWidth(1)

    # ── Submission details card ──
    card_y = H - 2.5 * inch
    card_h = 2.6 * inch
    c.setFillColor(OFF_WHITE)
    c.roundRect(MARGIN, card_y - card_h, CONTENT_W, card_h, 8, fill=1, stroke=0)
    c.setStrokeColor(LIGHT_GRAY)
    c.setLineWidth(0.5)
    c.roundRect(MARGIN, card_y - card_h, CONTENT_W, card_h, 8, fill=0, stroke=1)
    c.setLineWidth(1)

    c.setFillColor(NAVY)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(MARGIN + 14, card_y - 0.28 * inch, "Submission Details")

    # Left column
    lx = MARGIN + 14
    ly = card_y - 0.58 * inch
    ly = _info_row(c, lx, ly, "Student", u.name or "")
    ly = _info_row(c, lx, ly, "ID", u.student_id or "")
    ly = _info_row(c, lx, ly, "Department", u.department or "")
    ly = _info_row(c, lx, ly, "Level", getattr(u, "level", "") or "Undergraduate")
    ly = _info_row(c, lx, ly, "Document", (r.filename or "Uploaded document")[:55])

    # Right column
    rx = MARGIN + CONTENT_W / 2 + 10
    ry = card_y - 0.58 * inch
    ry = _info_row(c, rx, ry, "Report ID", f"#{r.id}")
    ry = _info_row(c, rx, ry, "Submitted", r.timestamp.strftime("%d %b %Y, %H:%M UTC"))
    ry = _info_row(c, rx, ry, "Generated", datetime.datetime.utcnow().strftime("%d %b %Y, %H:%M UTC"))
    ry = _info_row(c, rx, ry, "Plag. limit", f"{int(limit)}% ({getattr(u, 'level', 'UG') or 'UG'})")
    ry = _info_row(c, rx, ry, "AI limit", f"{int(limit)}%")

    # ── Score summary cards ──
    sy = card_y - card_h - 0.35 * inch
    card_configs = [
        ("Similarity", plag, _sim_color(plag), _sim_label(plag) + " similarity"),
        ("AI Writing", ai,   _ai_color(ai),    "Content AI likelihood"),
        ("Footer",     100 if r.footer_ok else 0, SIM_LOW if r.footer_ok else SIM_HIGH,
         "Detected" if r.footer_ok else "Not found"),
        ("Prelim. Pages", 100 if r.prelim_ok else 0, SIM_LOW if r.prelim_ok else SIM_HIGH,
         "Detected" if r.prelim_ok else "Not found"),
    ]
    sw = (CONTENT_W - 0.24 * inch) / 4
    for i, (label, val, col, sublabel) in enumerate(card_configs):
        cx_card = MARGIN + i * (sw + 0.08 * inch)
        c.setFillColor(WHITE)
        c.roundRect(cx_card, sy - 1.0 * inch, sw, 1.0 * inch, 6, fill=1, stroke=0)
        c.setStrokeColor(LIGHT_GRAY)
        c.setLineWidth(0.5)
        c.roundRect(cx_card, sy - 1.0 * inch, sw, 1.0 * inch, 6, fill=0, stroke=1)
        c.setLineWidth(1)

        # Colored top accent
        c.setFillColor(col)
        c.roundRect(cx_card, sy - 0.06 * inch, sw, 0.06 * inch, 3, fill=1, stroke=0)

        # Value
        c.setFillColor(col)
        c.setFont("Helvetica-Bold", 20)
        disp = f"{int(round(val))}%" if label in ("Similarity", "AI Writing") else ("✓" if val == 100 else "✗")
        c.drawCentredString(cx_card + sw / 2, sy - 0.45 * inch, disp)

        # Label
        c.setFillColor(DARK_GRAY)
        c.setFont("Helvetica-Bold", 9)
        c.drawCentredString(cx_card + sw / 2, sy - 0.65 * inch, label)
        c.setFont("Helvetica", 8)
        c.setFillColor(MID_GRAY)
        c.drawCentredString(cx_card + sw / 2, sy - 0.80 * inch, sublabel)

    # ── Overall badge ──
    badge_col = SIM_LOW if "Low" in badge else (SIM_MID if "Moderate" in badge else SIM_HIGH)
    by = sy - 1.25 * inch
    _pill(c, MARGIN, by, 2.0 * inch, 0.34 * inch, badge_col, badge, WHITE, 10)

    c.setFont("Helvetica", 9)
    c.setFillColor(MID_GRAY)
    c.drawString(MARGIN + 2.2 * inch, by + 0.10 * inch,
                 "Overall risk indicator based on similarity and AI writing scores.")

    _page_footer(c, page, r.id)


# ── PAGE 2: Overview / Score breakdown ──────────────────────────────────────

def _page_overview(c: canvas.Canvas, r: ReportCheck, plag: float, ai: float,
                   limit: float, page: int):

    y = H - MARGIN

    # Title
    c.setFillColor(NAVY)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(MARGIN, y, "Score Overview")
    c.setFont("Helvetica", 10)
    c.setFillColor(MID_GRAY)
    c.drawString(MARGIN, y - 0.22 * inch, "Detailed breakdown of similarity and AI writing indicators")
    y -= 0.55 * inch

    # ── Score circles row ──
    circle_y = y - 0.65 * inch
    _score_donut(c, MARGIN + 0.85 * inch, circle_y, 0.65 * inch,
                 plag, _sim_color(plag), "Similarity Score", _sim_label(plag))
    _score_donut(c, MARGIN + 2.65 * inch, circle_y, 0.65 * inch,
                 ai, _ai_color(ai), "AI Writing Score", "")

    # Score interpretation box
    ix = MARGIN + 3.8 * inch
    iw = CONTENT_W - 3.8 * inch
    c.setFillColor(OFF_WHITE)
    c.roundRect(ix, circle_y - 0.75 * inch, iw, 1.55 * inch, 6, fill=1, stroke=0)
    c.setFillColor(NAVY)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(ix + 10, circle_y + 0.65 * inch, "Score bands")
    bands = [
        (SIM_LOW,  "< 20%  Low — generally acceptable"),
        (SIM_MID,  "20–39%  Moderate — review citations"),
        (SIM_HIGH, "≥ 40%  High — significant rewriting needed"),
    ]
    by2 = circle_y + 0.40 * inch
    for col, text in bands:
        c.setFillColor(col)
        c.roundRect(ix + 10, by2 - 1, 10, 10, 2, fill=1, stroke=0)
        c.setFillColor(DARK_GRAY)
        c.setFont("Helvetica", 9)
        c.drawString(ix + 26, by2, text)
        by2 -= 0.22 * inch

    y = circle_y - 1.0 * inch

    # ── Progress bars ──
    y = _section_header(c, y, "Score Breakdown", "vs. safe limit")
    y -= 0.15 * inch

    bar_configs = [
        ("Plagiarism / Similarity", plag, _sim_color(plag)),
        ("AI-Generated Content",    ai,   _ai_color(ai)),
    ]
    for label, val, col in bar_configs:
        c.setFont("Helvetica-Bold", 10)
        c.setFillColor(DARK_GRAY)
        c.drawString(MARGIN, y, label)
        c.setFont("Helvetica-Bold", 10)
        c.setFillColor(col)
        c.drawRightString(W - MARGIN, y, f"{val:.2f}%")
        y -= 0.18 * inch

        _progress_bar(c, MARGIN, y, CONTENT_W, 0.22 * inch, val, col)

        # Safe limit marker
        lx_mark = MARGIN + CONTENT_W * (limit / 100)
        c.setStrokeColor(NAVY)
        c.setLineWidth(1.5)
        c.setDash(4, 2)
        c.line(lx_mark, y - 2, lx_mark, y + 0.26 * inch)
        c.setDash()
        c.setLineWidth(1)
        c.setFont("Helvetica", 7)
        c.setFillColor(NAVY)
        c.drawCentredString(lx_mark, y - 0.12 * inch, f"Limit {int(limit)}%")

        # Status pill
        status    = val <= limit
        pill_text = "Within limit" if status else "Above limit"
        pill_col  = SIM_LOW if status else SIM_HIGH
        _pill(c, W - MARGIN - 1.1 * inch, y - 0.18 * inch,
              1.1 * inch, 0.22 * inch, pill_col, pill_text, WHITE, 8)

        y -= 0.55 * inch

    # ── Format checks ──
    y = _section_header(c, y, "Format Checks")
    y -= 0.12 * inch

    checks = [
        ("Footer / Page numbering", r.footer_ok),
        ("Preliminary pages (title, abstract, TOC)", r.prelim_ok),
    ]
    for label, ok in checks:
        icon_col = SIM_LOW if ok else SIM_HIGH
        c.setFillColor(icon_col)
        c.circle(MARGIN + 7, y + 4, 6, fill=1, stroke=0)
        c.setFillColor(WHITE)
        c.setFont("Helvetica-Bold", 9)
        c.drawCentredString(MARGIN + 7, y + 1, "✓" if ok else "✗")
        c.setFillColor(DARK_GRAY)
        c.setFont("Helvetica", 10)
        c.drawString(MARGIN + 20, y, label)
        c.setFillColor(MID_GRAY)
        c.setFont("Helvetica", 9)
        c.drawRightString(W - MARGIN, y, "Detected" if ok else "Not detected — action required")
        y -= 0.3 * inch

    _page_footer(c, page, r.id)


# ── PAGE 3: Matched Sources ──────────────────────────────────────────────────

def _page_sources(c: canvas.Canvas, r: ReportCheck, plag: float,
                  top_sources: list[dict], plag_sources: list[dict], page: int):

    y = H - MARGIN

    c.setFillColor(NAVY)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(MARGIN, y, "Matched Sources")
    c.setFont("Helvetica", 10)
    c.setFillColor(MID_GRAY)
    c.drawString(MARGIN, y - 0.22 * inch,
                 "Web sources where similar text was detected (ranked by contribution)")
    y -= 0.55 * inch

    if top_sources:
        y = _section_header(c, y, "Top Sources", f"{len(top_sources)} sources found")
        y -= 0.1 * inch

        for row in top_sources[:8]:
            if y < 1.5 * inch:
                break
            rank    = int(row.get("rank") or 0)
            col_idx = (rank - 1) % len(SOURCE_PALETTE)
            col     = SOURCE_PALETTE[col_idx]
            contrib = float(row.get("contribution") or 0.0)
            title   = str(row.get("title") or "Unknown")[:90]
            link    = str(row.get("link") or "")[:100]
            matches = int(row.get("matches") or 0)

            # Source row background
            c.setFillColor(OFF_WHITE)
            c.roundRect(MARGIN, y - 0.55 * inch, CONTENT_W, 0.6 * inch, 4, fill=1, stroke=0)

            # Rank circle
            c.setFillColor(col)
            c.circle(MARGIN + 0.22 * inch, y - 0.22 * inch, 0.16 * inch, fill=1, stroke=0)
            c.setFillColor(WHITE)
            c.setFont("Helvetica-Bold", 9)
            c.drawCentredString(MARGIN + 0.22 * inch, y - 0.25 * inch, str(rank))

            # Title + link
            c.setFillColor(DARK_GRAY)
            c.setFont("Helvetica-Bold", 10)
            c.drawString(MARGIN + 0.5 * inch, y - 0.12 * inch, title)
            c.setFont("Helvetica", 8)
            c.setFillColor(ACCENT_BLUE)
            c.drawString(MARGIN + 0.5 * inch, y - 0.28 * inch, link[:95])

            # Contribution bar (right side)
            bx = W - MARGIN - 1.8 * inch
            c.setFillColor(MID_GRAY)
            c.setFont("Helvetica", 8)
            c.drawString(bx, y - 0.12 * inch, f"{contrib:.1f}%  •  {matches} match{'es' if matches != 1 else ''}")
            _progress_bar(c, bx, y - 0.32 * inch, 1.7 * inch, 0.10 * inch, contrib, col)

            y -= 0.68 * inch

    if plag_sources:
        if y < 2.5 * inch:
            c.showPage()
            _page_footer(c, page + 1, r.id)
            y = H - MARGIN

        y = _section_header(c, y, "Sentence-level Matches",
                             f"{len(plag_sources)} matched sentences")
        y -= 0.12 * inch

        for idx, item in enumerate(plag_sources[:8]):
            if y < 1.8 * inch:
                break
            sentence = str(item.get("sentence") or item.get("match") or "")[:220]
            srcs     = item.get("sources") or []
            conf     = item.get("confidence") or "Possible"

            conf_col = SIM_HIGH if conf == "Exact" else (SIM_MID if conf == "Paraphrase" else MID_GRAY)

            c.setFillColor(OFF_WHITE)
            box_h = 0.9 * inch
            c.roundRect(MARGIN, y - box_h, CONTENT_W, box_h, 4, fill=1, stroke=0)
            c.setStrokeColor(conf_col)
            c.setLineWidth(2)
            c.line(MARGIN, y - box_h, MARGIN, y)
            c.setLineWidth(1)

            _pill(c, MARGIN + 8, y - 0.18 * inch, 0.9 * inch, 0.20 * inch, conf_col, conf, WHITE, 8)

            c.setFont("Helvetica", 9)
            c.setFillColor(DARK_GRAY)
            tx = c.beginText(MARGIN + 8, y - 0.35 * inch)
            tx.setFont("Helvetica", 9)
            tx.setLeading(12)
            for line in _wrap(sentence, 90):
                tx.textLine(line)
                if tx.getY() < y - box_h + 0.05 * inch:
                    break
            c.drawText(tx)

            if srcs:
                s0    = srcs[0]
                s_ttl = str(s0.get("title") or "")[:70]
                c.setFont("Helvetica", 8)
                c.setFillColor(ACCENT_BLUE)
                c.drawString(MARGIN + 8, y - box_h + 0.1 * inch, f"→ {s_ttl}")

            y -= box_h + 0.12 * inch

    elif not top_sources:
        c.setFont("Helvetica", 11)
        c.setFillColor(MID_GRAY)
        c.drawString(MARGIN, y - 0.3 * inch, "No web sources were recorded for this report.")

    _page_footer(c, page, r.id)


# ── PAGE 4: Highlighted Excerpts ─────────────────────────────────────────────

def _page_excerpts(c: canvas.Canvas, r: ReportCheck,
                   plag_matches: list, ai_flagged: list, page: int):

    y = H - MARGIN

    c.setFillColor(NAVY)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(MARGIN, y, "Highlighted Excerpts")
    c.setFont("Helvetica", 10)
    c.setFillColor(MID_GRAY)
    c.drawString(MARGIN, y - 0.22 * inch,
                 "Sample sentences flagged for similarity or AI-like writing")
    y -= 0.55 * inch

    # ── Plagiarism examples ──
    y = _section_header(c, y, "Similarity Examples",
                         f"{len(plag_matches)} sample(s)")
    y -= 0.12 * inch

    if not plag_matches:
        c.setFont("Helvetica", 10)
        c.setFillColor(MID_GRAY)
        c.drawString(MARGIN, y, "No high-confidence matches captured in this check.")
        y -= 0.4 * inch
    else:
        for idx, sent in enumerate(plag_matches[:6], 1):
            if y < 2.5 * inch:
                break
            lines   = _wrap(str(sent), 92)
            box_h   = max(0.55 * inch, len(lines) * 0.155 * inch + 0.25 * inch)

            c.setFillColor(HL_PLAG)
            c.roundRect(MARGIN, y - box_h, CONTENT_W, box_h, 4, fill=1, stroke=0)
            c.setStrokeColor(SIM_HIGH)
            c.setLineWidth(1.5)
            c.line(MARGIN, y - box_h, MARGIN, y)
            c.setLineWidth(1)

            c.setFillColor(SIM_HIGH)
            c.setFont("Helvetica-Bold", 9)
            c.drawString(MARGIN + 8, y - 0.16 * inch, f"#{idx}")

            c.setFillColor(DARK_GRAY)
            c.setFont("Helvetica", 9)
            tx = c.beginText(MARGIN + 24, y - 0.16 * inch)
            tx.setLeading(13)
            for line in lines:
                tx.textLine(line)
                if tx.getY() < y - box_h + 0.05 * inch:
                    break
            c.drawText(tx)
            y -= box_h + 0.1 * inch

    # ── AI examples ──
    if y < 3.0 * inch:
        c.showPage()
        _page_footer(c, page, r.id)
        y = H - MARGIN

    y = _section_header(c, y, "AI Writing Examples",
                         f"{len(ai_flagged)} sample(s)")
    y -= 0.12 * inch

    if not ai_flagged:
        c.setFont("Helvetica", 10)
        c.setFillColor(MID_GRAY)
        c.drawString(MARGIN, y, "No strongly AI-like sentences flagged.")
        y -= 0.4 * inch
    else:
        for idx, item in enumerate(ai_flagged[:6], 1):
            if y < 1.8 * inch:
                break
            sent  = item.get("sentence") if isinstance(item, dict) else str(item)
            prob  = item.get("aiProb")   if isinstance(item, dict) else None
            lines = _wrap(str(sent)[:280], 88)
            box_h = max(0.55 * inch, len(lines) * 0.155 * inch + 0.25 * inch)

            c.setFillColor(HL_AI)
            c.roundRect(MARGIN, y - box_h, CONTENT_W, box_h, 4, fill=1, stroke=0)
            c.setStrokeColor(AI_MID)
            c.setLineWidth(1.5)
            c.line(MARGIN, y - box_h, MARGIN, y)
            c.setLineWidth(1)

            c.setFillColor(AI_MID)
            c.setFont("Helvetica-Bold", 9)
            c.drawString(MARGIN + 8, y - 0.16 * inch, f"#{idx}")

            if prob is not None:
                _pill(c, W - MARGIN - 1.0 * inch, y - 0.22 * inch,
                      1.0 * inch, 0.20 * inch, AI_MID, f"{prob:.1f}% AI", WHITE, 8)

            c.setFillColor(DARK_GRAY)
            c.setFont("Helvetica", 9)
            tx = c.beginText(MARGIN + 24, y - 0.16 * inch)
            tx.setLeading(13)
            for line in lines:
                tx.textLine(line)
                if tx.getY() < y - box_h + 0.05 * inch:
                    break
            c.drawText(tx)
            y -= box_h + 0.1 * inch

    _page_footer(c, page, r.id)


# ── PAGE 5+: Full document with highlights ───────────────────────────────────

def _page_document(c: canvas.Canvas, r: ReportCheck, doc_text: str,
                   all_spans: list[dict], src_rank: dict[str, int],
                   page_start: int) -> int:

    if not doc_text.strip():
        return page_start

    page = page_start
    margin_x   = MARGIN
    margin_top = 0.75 * inch
    margin_bot = 0.65 * inch
    font_name  = "Courier"
    font_size  = 8.5
    line_h     = 12
    char_w     = 6.0
    chars_per_line = int(CONTENT_W / char_w)

    def new_doc_page(pg: int) -> float:
        c.setFillColor(NAVY)
        c.setFont("Helvetica-Bold", 14)
        c.drawString(margin_x, H - margin_top + 0.1 * inch, "Submitted Document")
        c.setFont("Helvetica", 9)
        c.setFillColor(MID_GRAY)
        c.drawString(margin_x, H - margin_top - 0.08 * inch,
                     "Red = similarity match  •  Blue = AI-like  •  Orange = possible match  •  Source numbers [n] indicate matched source")
        _page_footer(c, pg, r.id)
        return H - margin_top - 0.32 * inch

    y = new_doc_page(page)

    def _span_fill(sp: dict):
        if sp.get("type") == "ai":
            return HL_AI
        conf = (sp.get("confidence") or "").lower()
        if "possible" in conf:
            return HL_POSSIBLE
        return HL_PLAG

    txt = doc_text.replace("\r\n", "\n").replace("\r", "\n")
    idx = 0

    for para in txt.split("\n"):
        if y < margin_bot:
            c.showPage()
            page += 1
            y = new_doc_page(page)

        if para.strip() == "":
            y -= line_h * 0.6
            idx += 1
            continue

        off = 0
        while off < len(para):
            chunk     = para[off: off + chars_per_line]
            c_start   = idx + off
            c_end     = c_start + len(chunk)

            overlaps = [
                (max(int(sp.get("start") or 0), c_start),
                 min(int(sp.get("end")   or 0), c_end),
                 sp)
                for sp in all_spans
                if not (int(sp.get("end") or 0) <= c_start or
                        int(sp.get("start") or 0) >= c_end)
            ]

            for s, e, sp in overlaps:
                a = s - c_start
                b = e - c_start
                c.setFillColor(_span_fill(sp))
                c.rect(margin_x + a * char_w, y - 2,
                       max(1, (b - a) * char_w), line_h, fill=1, stroke=0)
                if sp.get("type") == "plagiarism" and "possible" not in str(sp.get("confidence", "")).lower():
                    src = sp.get("source") if isinstance(sp.get("source"), dict) else {}
                    key = (src.get("link") or src.get("title") or "").strip()
                    sid = int(src_rank.get(key, 0) or 0)
                    if sid > 0:
                        col_idx = (sid - 1) % len(SOURCE_PALETTE)
                        c.setFillColor(SOURCE_PALETTE[col_idx])
                        c.setFont("Helvetica-Bold", 6)
                        c.drawString(margin_x + a * char_w + 1, y + 3, f"[{sid}]")

            c.setFillColor(DARK_GRAY)
            c.setFont(font_name, font_size)
            c.drawString(margin_x, y, chunk)
            y -= line_h
            off += len(chunk)

            if y < margin_bot:
                c.showPage()
                page += 1
                y = new_doc_page(page)

        idx += len(para) + 1

    return page


# ── FINAL PAGE: How to improve ───────────────────────────────────────────────

def _page_improve(c: canvas.Canvas, r: ReportCheck, plag: float, ai: float,
                  plag_matches: list, ai_flagged: list, page: int):

    y = H - MARGIN

    c.setFillColor(NAVY)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(MARGIN, y, "How to Improve Your Report")
    c.setFont("Helvetica", 10)
    c.setFillColor(MID_GRAY)
    c.drawString(MARGIN, y - 0.22 * inch,
                 "Actionable guidance based on your scores")
    y -= 0.55 * inch

    guidelines = compute_guidelines(
        plag, ai, bool(r.footer_ok), bool(r.prelim_ok), plag_matches, ai_flagged
    )

    level_colors = {
        "High Risk": SIM_HIGH,
        "Medium":    SIM_MID,
        "Low":       SIM_LOW,
        "Action":    ACCENT_BLUE,
        "Tip":       MID_GRAY,
    }
    tag_colors = {
        "Similarity": SIM_HIGH,
        "AI":         AI_MID,
        "Format":     ACCENT_BLUE,
    }

    for g in guidelines[:12]:
        if y < 1.5 * inch:
            c.showPage()
            _page_footer(c, page + 1, r.id)
            y = H - MARGIN

        level   = g.get("level", "Tip")
        tag     = g.get("tag", "")
        message = g.get("message", "")
        lines   = _wrap(message, 85)
        box_h   = max(0.62 * inch, len(lines) * 0.165 * inch + 0.32 * inch)
        lv_col  = level_colors.get(level, MID_GRAY)
        tg_col  = tag_colors.get(tag, NAVY)

        c.setFillColor(OFF_WHITE)
        c.roundRect(MARGIN, y - box_h, CONTENT_W, box_h, 4, fill=1, stroke=0)
        c.setStrokeColor(lv_col)
        c.setLineWidth(2)
        c.line(MARGIN, y - box_h, MARGIN, y)
        c.setLineWidth(1)

        _pill(c, MARGIN + 8, y - 0.20 * inch,
              0.85 * inch, 0.20 * inch, lv_col, level, WHITE, 8)
        _pill(c, MARGIN + 1.0 * inch, y - 0.20 * inch,
              0.75 * inch, 0.20 * inch, tg_col, tag, WHITE, 8)

        c.setFillColor(DARK_GRAY)
        c.setFont("Helvetica", 10)
        tx = c.beginText(MARGIN + 8, y - 0.38 * inch)
        tx.setLeading(14)
        for line in lines:
            tx.textLine(line)
            if tx.getY() < y - box_h + 0.08 * inch:
                break
        c.drawText(tx)
        y -= box_h + 0.12 * inch

    _page_footer(c, page, r.id)


# ── Main entry point ─────────────────────────────────────────────────────────

def generate_pdf(r: ReportCheck, u: User) -> io.BytesIO:
    plag  = float(r.plagiarism or 0.0)
    ai    = float(r.ai_score   or 0.0)
    level = (getattr(u, "level", "") or "").lower()
    limit = 25.0 if level.startswith("grad") else 35.0
    badge, _ = confidence_badge(plag, ai)

    try:
        plag_matches = json.loads(r.plag_matches_json or "[]")
        plag_sources = json.loads(getattr(r, "plag_sources_json", None) or "[]")
        plag_spans   = json.loads(getattr(r, "plag_spans_json",  None) or "[]")
        ai_spans     = json.loads(getattr(r, "ai_spans_json",    None) or "[]")
        ai_flagged   = json.loads(r.ai_flagged_json or "[]")
    except Exception:
        plag_matches = plag_sources = plag_spans = ai_spans = ai_flagged = []

    doc_text    = getattr(r, "doc_text", None) or ""
    top_sources = _top_sources_from_spans(plag_spans)
    src_rank    = {
        (row.get("link") or row.get("title") or "Unknown").strip(): int(row.get("rank") or (i + 1))
        for i, row in enumerate(top_sources)
    }

    all_spans = sorted(
        [sp for sp in (plag_spans + ai_spans)
         if isinstance(sp, dict) and int(sp.get("end") or 0) > int(sp.get("start") or 0)],
        key=lambda x: int(x.get("start") or 0),
    )

    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    c.setTitle(f"DIU Similarity Report — {u.name} — #{r.id}")
    c.setAuthor("DIU Project Checker")
    c.setSubject("Academic integrity report")

    page = 1

    # Page 1 — Cover
    _page_cover(c, r, u, plag, ai, badge, limit, page)
    c.showPage(); page += 1

    # Page 2 — Overview
    _page_overview(c, r, plag, ai, limit, page)
    c.showPage(); page += 1

    # Page 3 — Sources
    _page_sources(c, r, plag, top_sources, plag_sources, page)
    c.showPage(); page += 1

    # Page 4 — Excerpts
    _page_excerpts(c, r, plag_matches, ai_flagged, page)
    c.showPage(); page += 1

    # Pages 5+ — Full document
    if doc_text.strip():
        page = _page_document(c, r, doc_text, all_spans, src_rank, page)
        c.showPage(); page += 1

    # Final page — How to improve
    _page_improve(c, r, plag, ai, plag_matches, ai_flagged, page)

    c.save()
    buffer.seek(0)
    return buffer
