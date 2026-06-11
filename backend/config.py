"""
config.py — Single Google API key + CX setup.

Add to backend/.env:
    GOOGLE_API_KEY=your_key
    GOOGLE_CX=your_cx

One key = 100 free queries/day = ~2 full reports/day (45 queries each).
"""
import os
from pathlib import Path
from dotenv import load_dotenv

_BASE = Path(__file__).resolve().parent
for _env_file in (_BASE / ".env", _BASE / ".env.example"):
    if _env_file.exists():
        load_dotenv(dotenv_path=_env_file, override=False)
        break

GOOGLE_API_KEY: str = os.getenv("GOOGLE_API_KEY", "").strip()
GOOGLE_CX:      str = os.getenv("GOOGLE_CX",      "").strip()

# Keep these for quota_tracker compatibility
GOOGLE_KEY_CX_PAIRS: list[tuple[str, str]] = (
    [(GOOGLE_API_KEY, GOOGLE_CX)] if (GOOGLE_API_KEY and GOOGLE_CX) else []
)
GOOGLE_API_KEYS: list[str] = [GOOGLE_API_KEY] if GOOGLE_API_KEY else []

DAILY_FREE_LIMIT_PER_KEY = 100
TOTAL_DAILY_LIMIT        = DAILY_FREE_LIMIT_PER_KEY

if not GOOGLE_API_KEY or not GOOGLE_CX:
    import warnings
    warnings.warn("No GOOGLE_API_KEY or GOOGLE_CX set — plagiarism will return 0%.", stacklevel=2)
