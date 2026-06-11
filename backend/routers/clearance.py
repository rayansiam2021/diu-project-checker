"""
routers/clearance.py — Clearance check endpoint
POST /check-clearance
"""
from __future__ import annotations

import json
import os
import tempfile

from fastapi import APIRouter, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from database import User, get_db
from services.clearance_checker import run_clearance_check

router = APIRouter(tags=["clearance"])


@router.post("/check-clearance")
async def check_clearance(studentId: int = Form(...), report: UploadFile = None):
    if not report:
        return JSONResponse({"error": "No file uploaded"}, status_code=400)

    filename = report.filename or "report"
    suffix = os.path.splitext(filename)[-1].lower() or ".tmp"

    if suffix not in (".pdf", ".docx", ".doc", ".txt"):
        return JSONResponse(
            {"error": "Unsupported file type. Please upload PDF, DOCX, or DOC."},
            status_code=400,
        )

    # Get student level for plagiarism threshold
    level = "Undergraduate"
    try:
        with get_db() as db:
            user = db.query(User).filter(User.id == studentId).first()
            if user:
                level = getattr(user, "level", "Undergraduate") or "Undergraduate"
    except Exception:
        pass

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(await report.read())
        tmp_path = tmp.name

    try:
        result = run_clearance_check(tmp_path, level=level)
    except Exception as exc:
        import traceback
        traceback.print_exc()
        return JSONResponse({"error": f"Clearance check failed: {str(exc)}"}, status_code=500)
    finally:
        try:
            os.remove(tmp_path)
        except Exception:
            pass

    return {
        "filename": filename,
        "level": level,
        **result,
    }
