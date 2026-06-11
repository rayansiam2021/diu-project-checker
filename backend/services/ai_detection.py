"""
services/ai_detection.py — AI-generated text detection using a HuggingFace pipeline.
"""
from __future__ import annotations

from services.text_extraction import split_sentences

MODEL_NAME = "openai-community/roberta-base-openai-detector"

_CLASSIFIER = None  # Lazy-loaded singleton


def _load_model() -> None:
    global _CLASSIFIER
    if _CLASSIFIER is not None:
        return
    try:
        from transformers import pipeline
        _CLASSIFIER = pipeline("text-classification", model=MODEL_NAME, truncation=True)
    except Exception:
        _CLASSIFIER = None


def compute_ai_score(text: str) -> dict:
    """
    Estimate AI-generated content probability.

    Returns average AI probability over sampled sentences and a list of
    sentences that look most AI-like (useful for student feedback).
    """
    _load_model()
    if _CLASSIFIER is None:
        return {
            "available": False,
            "message": "AI model not available on this machine.",
            "percentage": 0.0,
            "flagged": [],
        }

    sents = split_sentences(text, max_sentences=60) or [text[:1200]]
    scored: list[tuple[float, str]] = []

    for chunk in sents:
        try:
            out = _CLASSIFIER(chunk[:1200])[0]
            label = (out.get("label") or "").lower()
            score = float(out.get("score") or 0.0)
            ai_prob = score if any(k in label for k in ["fake", "ai", "gpt", "generated"]) else (1.0 - score)
            scored.append((ai_prob, chunk.strip()))
        except Exception:
            continue

    if not scored:
        return {
            "available": False,
            "message": "AI classification failed for this document.",
            "percentage": 0.0,
            "flagged": [],
        }

    probs = [p for p, _ in scored]
    avg = sum(probs) / len(probs)

    THRESH = 0.70
    flagged = [
        {"sentence": s[:320], "aiProb": round(p * 100, 1)}
        for p, s in sorted(scored, key=lambda x: x[0], reverse=True)
        if p >= THRESH and len(s) >= 30
    ][:8]

    return {
        "available": True,
        "percentage": round(avg * 100, 2),
        "flagged": flagged,
        "threshold": round(THRESH * 100, 0),
    }
