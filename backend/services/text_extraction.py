"""
services/text_extraction.py — Extract plain text from DOCX, PDF, and TXT files.
"""
import re

from docx import Document as DocxDocument
from PyPDF2 import PdfReader


def extract_text_from_docx(path: str) -> str:
    doc = DocxDocument(path)
    parts = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
    return "\n".join(parts)


def extract_text_from_pdf(path: str) -> str:
    reader = PdfReader(path)
    texts = []
    for page in reader.pages:
        try:
            t = (page.extract_text() or "").strip()
            if t:
                texts.append(t)
        except Exception:
            continue
    return "\n".join(texts)


def extract_text(path: str) -> str:
    lp = path.lower()
    if lp.endswith(".docx"):
        return extract_text_from_docx(path)
    if lp.endswith(".pdf"):
        return extract_text_from_pdf(path)
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    except Exception:
        return ""


def split_sentences(text: str, max_sentences: int = 35) -> list[str]:
    chunks = re.split(r"[\n\r]+|(?<=[.!?])\s+", text)
    cleaned = [c.strip() for c in chunks if len(c.strip()) > 25]
    return cleaned[:max_sentences]
