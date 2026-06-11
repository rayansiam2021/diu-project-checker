"""
services/reasoning.py — Rule-based guidelines and result reasoning engine.
"""
from __future__ import annotations


def compute_guidelines(
    plagiarism_pct: float,
    ai_pct: float,
    footer_ok: bool,
    prelim_ok: bool,
    plag_sentences: list,
    ai_sentences: list,
) -> list[dict]:
    """Defense-friendly, explainable rule-based guidance."""
    guidelines: list[dict] = []

    # Similarity bands (Turnitin-style)
    if plagiarism_pct >= 40:
        guidelines.append({"level": "High Risk", "tag": "Similarity", "message": "High similarity detected. Rewrite the highlighted red sentences and add proper citations (author, year, page)."})
    elif plagiarism_pct >= 20:
        guidelines.append({"level": "Medium", "tag": "Similarity", "message": "Moderate similarity detected. Paraphrase and cite sources for the highlighted red parts."})
    else:
        guidelines.append({"level": "Low", "tag": "Similarity", "message": "Low similarity. Keep citing sources where needed and maintain originality."})

    # AI bands
    if ai_pct >= 60:
        guidelines.append({"level": "High Risk", "tag": "AI", "message": "AI-likeness is high. Add personal reasoning, examples, and vary sentence structure. Rewrite blue-highlighted sentences in your own voice."})
    elif ai_pct >= 30:
        guidelines.append({"level": "Medium", "tag": "AI", "message": "Some AI-like patterns detected. Improve natural flow: add transitions, reduce repetitive phrasing, and include project-specific details."})
    else:
        guidelines.append({"level": "Low", "tag": "AI", "message": "Low AI-likeness. Ensure writing style stays consistent and original."})

    # Formatting
    if not footer_ok:
        guidelines.append({"level": "Action", "tag": "Format", "message": "Footer format is missing/incorrect. Add the required footer text and page numbering as per DIU guidelines."})
    if not prelim_ok:
        guidelines.append({"level": "Action", "tag": "Format", "message": "Preliminary pages appear incomplete. Ensure title page, declaration, abstract, table of contents are included (if required)."})

    # Tips
    if len(plag_sentences) == 0:
        guidelines.append({"level": "Tip", "tag": "Similarity", "message": "No strong web matches found for sampled sentences. Still verify citations for any quoted material."})
    if len(ai_sentences) >= 6:
        guidelines.append({"level": "Tip", "tag": "AI", "message": "Many sentences look AI-like. Consider adding diagrams, screenshots, calculations, and implementation details to make the report uniquely yours."})

    return guidelines


def confidence_badge(plag_pct: float, ai_pct: float) -> tuple[str, str]:
    """Returns (label, Bootstrap color class)."""
    risk = max(plag_pct, ai_pct)
    if risk < 20:
        return ("Low Risk", "success")
    if risk < 40:
        return ("Moderate Risk", "info")
    if risk < 60:
        return ("High Risk", "warning")
    return ("Very High Risk", "danger")


def build_reasoning(plag_res: dict, ai_res: dict) -> dict:
    plag = float(plag_res.get("percentage") or 0.0)
    ai   = float(ai_res.get("percentage")   or 0.0)

    badge, badge_color = confidence_badge(plag, ai)

    if plag_res.get("available"):
        checked = plag_res.get("checked", 0)
        found   = plag_res.get("found", 0)
        plag_text = (
            f"Similarity score is estimated by checking {checked} representative sentence samples against the "
            f"web. {found} samples returned matches. References and quoted text are excluded."
        )
    else:
        plag_text = f"Plagiarism check unavailable: {plag_res.get('message', 'Unavailable')}."

    ai_text = (
        "AI content score is estimated by running an AI-text detector on multiple sentences and averaging the probability."
        if ai_res.get("available")
        else f"AI check unavailable: {ai_res.get('message', 'Unavailable')}."
    )

    rec: list[str] = []
    if plag >= 30:
        rec.append("Paraphrase the highlighted parts, and add proper citations for any borrowed text.")
    if plag >= 50:
        rec.append("Run a manual citation audit and rewrite sections that match online sources too closely.")
    if ai >= 40:
        rec.append("Add more personal analysis, project-specific results, and references to reduce AI-like patterns.")
    if ai >= 70:
        rec.append("Rewrite key sections in your own voice and ensure methodology/results are clearly original.")
    if not rec:
        rec = ["Your report looks acceptable. Still double-check citations and formatting before final submission."]

    return {
        "badge":                  badge,
        "badgeColor":             badge_color,
        "plagiarismExplanation":  plag_text,
        "aiExplanation":          ai_text,
        "matchExamples":          plag_res.get("matches", []) or [],
        "recommendations":        rec,
    }
