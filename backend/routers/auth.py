"""
routers/auth.py — Authentication routes: /signup, /login.
"""
from __future__ import annotations

import base64
import bcrypt

from fastapi import APIRouter, File, Form, UploadFile
from database import User, get_db

router = APIRouter(tags=["auth"])


def _hash_password(plain: str) -> str:
    try:
        return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()
    except Exception:
        return plain


def _verify_password(plain: str, stored: str) -> bool:
    try:
        if stored.startswith("$2"):
            return bcrypt.checkpw(plain.encode(), stored.encode())
    except Exception:
        pass
    return plain == stored


@router.post("/signup")
def signup(
    student_id: str = Form(...),
    name: str = Form(...),
    department: str = Form(...),
    level: str = Form(...),
    password: str = Form(...),
    photo: UploadFile | None = File(default=None),
):
    photo_b64 = None
    if photo is not None:
        try:
            content = photo.file.read()
            if content:
                mime = photo.content_type or "image/png"
                photo_b64 = f"data:{mime};base64," + base64.b64encode(content).decode("utf-8")
        except Exception:
            photo_b64 = None

    with get_db() as db:
        if db.query(User).filter(User.student_id == student_id).first():
            return {"success": False, "message": "Student ID already exists."}
        u = User(
            student_id   = student_id,
            name         = name,
            department   = department,
            level        = level,
            photo_base64 = photo_b64,
            password     = _hash_password(password),
        )
        db.add(u)
        db.flush()
        uid = u.id

    return {"success": True, "message": "Signup successful", "user_id": uid}


@router.post("/login")
def login(student_id: str = Form(...), password: str = Form(...)):
    with get_db() as db:
        user = db.query(User).filter(User.student_id == student_id).first()
        if not user or not _verify_password(password, user.password or ""):
            return {"success": False, "message": "Invalid credentials"}
        return {"success": True, "message": "Login successful", "user_id": user.id}
