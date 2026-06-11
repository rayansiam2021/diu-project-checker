"""
routers/reports.py — Document checking, history, and PDF download routes.
"""
from __future__ import annotations

import json
import os
import tempfile

from fastapi import APIRouter, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse

from database import ReportCheck, User, get_db
from services.ai_detection import compute_ai_score
from services.pdf_report import generate_pdf
from services.plagiarism import compute_plagiarism
from services.quota_tracker import can_run_check, get_status
from services.reasoning import build_reasoning
from services.text_extraction import extract_text

router = APIRouter(tags=["reports"])

QUERIES_PER_REPORT = 8   # minimum queries needed to start a meaningful check (partial runs allowed)


@router.post("/check")
async def check_report(studentId: int = Form(...), report: UploadFile = None):
    if not report:
        return JSONResponse({"error": "No file uploaded"}, status_code=400)

    filename = report.filename or "report"
    suffix   = os.path.splitext(filename)[-1].lower() or ".tmp"

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(await report.read())
        tmp_path = tmp.name

    try:
        text = extract_text(tmp_path)
    finally:
        try:
            os.remove(tmp_path)
        except Exception:
            pass

    if not text or len(text.strip()) < 30:
        return JSONResponse({"error": "Could not extract text or document is too short."}, status_code=400)

    # ── Check quota BEFORE running plagiarism search ──────────────────────
    quota_ok, quota_reason = can_run_check(queries_needed=QUERIES_PER_REPORT)
    quota_status = get_status()

    ai_res = compute_ai_score(text)

    if quota_ok:
        plag_res = compute_plagiarism(text)
    else:
        # Quota exhausted — skip plagiarism, return clear message
        plag_res = {
            "available":   False,
            "quota_block": True,
            "message":     quota_reason,
            "percentage":  None,   # None = unavailable (not 0%)
            "checked":     0,
            "found":       0,
            "matches":     [],
            "sources":     [],
            "spans":       [],
            "resets_at":   quota_status.get("resets_at_utc", ""),
            "remaining":   quota_status.get("remaining", 0),
        }

    lower_text = text.lower()
    footer_ok  = ("footer" in lower_text) or ("diu" in lower_text and "department" in lower_text)
    prelim_ok  = ("preliminary" in lower_text) or ("abstract" in lower_text)

    ai_val   = float(ai_res.get("percentage")  or 0.0) if ai_res.get("available") else 0.0
    # Use None for plagiarism when unavailable — frontend will show warning instead of 0%
    plag_pct = plag_res.get("percentage")
    plag_val = float(plag_pct) if (plag_res.get("available") and plag_pct is not None) else None

    plag_matches = plag_res.get("matches", []) or []
    plag_sources = plag_res.get("sources", []) or []
    plag_spans   = plag_res.get("spans",   []) or []
    ai_flagged   = ai_res.get("flagged",   []) or []

    ai_spans: list[dict] = []
    for item in ai_flagged:
        if not isinstance(item, dict):
            continue
        s = (item.get("sentence") or "").strip()
        if not s:
            continue
        pos = text.find(s)
        if pos != -1:
            ai_spans.append({"start": int(pos), "end": int(pos + len(s)),
                             "type": "ai", "aiProb": item.get("aiProb")})

    # Store None as -1 in DB so we can distinguish "unavailable" from "0%"
    plag_db_val = float(plag_val) if plag_val is not None else -1.0

    with get_db() as db:
        new = ReportCheck(
            student_id        = studentId,
            filename          = filename,
            plagiarism        = plag_db_val,
            ai_score          = ai_val,
            footer_ok         = bool(footer_ok),
            prelim_ok         = bool(prelim_ok),
            plag_matches_json = json.dumps(plag_matches[:12], ensure_ascii=False),
            plag_sources_json = json.dumps(plag_sources[:12], ensure_ascii=False),
            ai_flagged_json   = json.dumps(ai_flagged[:12],   ensure_ascii=False),
            doc_text          = text,
            plag_spans_json   = json.dumps(plag_spans[:400],  ensure_ascii=False),
            ai_spans_json     = json.dumps(ai_spans[:400],    ensure_ascii=False),
        )
        db.add(new)
        db.flush()
        report_id = new.id

        user  = db.query(User).filter(User.id == studentId).first()
        level = (getattr(user, "level", "") or "").lower()
        limit = 35.0 if level.startswith("under") else 25.0
        limits = {"level": getattr(user, "level", None), "plagiarismLimit": limit, "aiLimit": limit}

    plag_available = plag_res.get("available", False)
    flags = {
        "plagiarismStatus": ("UNAVAILABLE" if not plag_available
                             else ("OK" if (plag_val or 0) <= limit else "ABOVE_LIMIT")),
        "aiStatus": "OK" if ai_val <= limit else "ABOVE_LIMIT",
    }
    reasoning = build_reasoning(plag_res, ai_res)

    return {
        "reportId":           report_id,
        "plagiarism":         plag_val,           # None if unavailable
        "plagiarismAvailable": plag_available,
        "ai":                 ai_val,
        "limits":             limits,
        "status":             flags,
        "plagSources":        plag_sources,
        "plagSpans":          plag_spans,
        "aiSpans":            ai_spans,
        "footerOk":           bool(footer_ok),
        "prelimOk":           bool(prelim_ok),
        "reasoning":          reasoning,
        "highlights": {
            "plagiarismSentences": plag_matches,
            "aiSentences":         ai_flagged,
        },
        "plagMessage":   plag_res.get("message", "") if not plag_available else "",
        "plagResetAt":   plag_res.get("resets_at", ""),
        "quotaRemaining": quota_status.get("remaining", 0),
        "aiMessage":     "" if ai_res.get("available") else ai_res.get("message", ""),
    }


@router.get("/history/{student_id}")
def history(student_id: int):
    with get_db() as db:
        rows = (
            db.query(ReportCheck)
            .filter(ReportCheck.student_id == student_id)
            .order_by(ReportCheck.timestamp.asc())
            .all()
        )
        result = [
            {
                "id":         r.id,
                "filename":   r.filename or "Uploaded Document",
                # -1 means plagiarism check was unavailable (quota)
                "plagiarism": None if float(r.plagiarism or 0) < 0 else float(r.plagiarism or 0.0),
                "plagiarismAvailable": float(r.plagiarism or 0) >= 0,
                "ai":         float(r.ai_score or 0.0),
                "footerOk":   bool(r.footer_ok),
                "prelimOk":   bool(r.prelim_ok),
                "timestamp":  r.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                "topSources": [
                    (sp.get("source") or {}).get("link") or (sp.get("source") or {}).get("title")
                    for sp in (json.loads(r.plag_spans_json or "[]") if r.plag_spans_json else [])[:3]
                    if isinstance(sp, dict) and sp.get("type") == "plagiarism"
                ],
            }
            for r in rows
        ]
    return result


@router.get("/report_pdf/{report_id}")
def report_pdf(report_id: int, student_id: int = None):
    with get_db() as db:
        r = db.query(ReportCheck).filter(ReportCheck.id == report_id).first()
        if not r:
            raise HTTPException(status_code=404, detail="Report not found")

        # Try to find user by student_id FK
        u = db.query(User).filter(User.id == r.student_id).first()

        # Fallback: if student_id query param provided, try that
        if not u and student_id:
            u = db.query(User).filter(User.id == student_id).first()

        # Final fallback: create a placeholder user object so PDF still generates
        if not u:
            class _FallbackUser:
                id         = r.student_id or 0
                name       = "Student"
                student_id = str(r.student_id or "")
                department = "Department"
                level      = "Undergraduate"
                photo_base64 = None
            u = _FallbackUser()

        buffer = generate_pdf(r, u)

    headers = {"Content-Disposition": f"attachment; filename=DIU_report_{report_id}.pdf"}
    return StreamingResponse(buffer, media_type="application/pdf", headers=headers)