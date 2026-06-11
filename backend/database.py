"""
database.py — SQLAlchemy models and DB session factory.
"""
from __future__ import annotations

import datetime
import os
import sqlite3
from contextlib import contextmanager

from sqlalchemy import (
    Boolean, Column, DateTime, Float,
    ForeignKey, Integer, String, Text, create_engine,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker

DATABASE_URL = "sqlite:///./reports.db"

# pool_pre_ping — detects stale connections automatically
# Use NullPool for SQLite to avoid thread/connection leaks
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=0,      # no overflow — forces proper session closing
    pool_timeout=20,
    pool_recycle=300,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


@contextmanager
def get_db():
    """Context manager that always closes the session — use with 'with get_db() as db:'"""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


class User(Base):
    __tablename__ = "users"

    id            = Column(Integer, primary_key=True, index=True)
    student_id    = Column(String, unique=True, index=True)
    name          = Column(String)
    department    = Column(String)
    level         = Column(String, default="Undergraduate")
    photo_base64  = Column(Text, nullable=True)
    password      = Column(String)
    signup_date   = Column(DateTime, default=datetime.datetime.utcnow)

    reports = relationship("ReportCheck", back_populates="owner")


class ReportCheck(Base):
    __tablename__ = "report_checks"

    id          = Column(Integer, primary_key=True, index=True)
    student_id  = Column(Integer, ForeignKey("users.id"))
    filename    = Column(String, nullable=True)
    plagiarism  = Column(Float)
    ai_score    = Column(Float)
    footer_ok   = Column(Boolean)
    prelim_ok   = Column(Boolean)

    plag_matches_json = Column(Text, nullable=True)
    ai_flagged_json   = Column(Text, nullable=True)
    plag_sources_json = Column(Text, nullable=True)
    doc_text          = Column(Text, nullable=True)
    plag_spans_json   = Column(Text, nullable=True)
    ai_spans_json     = Column(Text, nullable=True)

    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    owner     = relationship("User", back_populates="reports")


Base.metadata.create_all(bind=engine)


def _migrate_sqlite() -> None:
    db_file = DATABASE_URL.replace("sqlite:///./", "")
    if not os.path.exists(db_file):
        return
    conn = sqlite3.connect(db_file)
    cur  = conn.cursor()
    try:
        cur.execute("PRAGMA table_info(users);")
        ucols = {row[1] for row in cur.fetchall()}
        if "level" not in ucols:
            cur.execute("ALTER TABLE users ADD COLUMN level VARCHAR;")
        if "photo_base64" not in ucols:
            cur.execute("ALTER TABLE users ADD COLUMN photo_base64 TEXT;")

        cur.execute("PRAGMA table_info(report_checks);")
        rcols = {row[1] for row in cur.fetchall()}
        new_cols = [
            ("filename",          "VARCHAR"),
            ("plag_matches_json", "TEXT"),
            ("ai_flagged_json",   "TEXT"),
            ("plag_sources_json", "TEXT"),
            ("doc_text",          "TEXT"),
            ("plag_spans_json",   "TEXT"),
            ("ai_spans_json",     "TEXT"),
        ]
        for col, typ in new_cols:
            if col not in rcols:
                cur.execute(f"ALTER TABLE report_checks ADD COLUMN {col} {typ};")
        conn.commit()
    finally:
        conn.close()


_migrate_sqlite()
