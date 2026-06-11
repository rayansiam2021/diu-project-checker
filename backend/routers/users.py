"""
routers/users.py — User profile and password management routes.
"""
from __future__ import annotations

import bcrypt
from fastapi import APIRouter, Form, HTTPException
from database import User, get_db

router = APIRouter(tags=["users"])


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


@router.get("/profile/{user_id}")
def profile(user_id: int):
    with get_db() as db:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        return {
            "id":          user.id,
            "student_id":  user.student_id,
            "name":        user.name,
            "department":  user.department,
            "level":       getattr(user, "level", None),
            "photo":       getattr(user, "photo_base64", None),
            "signup_date": user.signup_date.strftime("%Y-%m-%d %H:%M:%S"),
        }


@router.post("/update_password")
def update_password(
    user_id:      int = Form(...),
    old_password: str = Form(...),
    new_password: str = Form(...),
):
    with get_db() as db:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return {"success": False, "message": "User not found"}
        if not _verify_password(old_password, user.password or ""):
            return {"success": False, "message": "Old password incorrect"}
        user.password = _hash_password(new_password)
        db.add(user)

    return {"success": True, "message": "Password updated"}
