"""
services/quota_tracker.py — Per-pair quota tracking with validation.
Each key+CX pair is from a different Google account = independent quota.

FIXES applied:
- Use UTC everywhere (consistent date key, no PST vs UTC mismatch)
- can_run_check: allow run if ANY key has enough quota, not all-or-nothing
- record_queries: auto-select the active key instead of always key0
- QUERIES_PER_REPORT reduced to 20 (conservative but realistic)
- Partial quota: if remaining < full run, still allow a partial run
"""
from __future__ import annotations
import json
import requests
from datetime import datetime, timezone, timedelta
from pathlib import Path
from threading import Lock

DAILY_FREE_LIMIT_PER_KEY = 100
RESET_HOUR_UTC           = 8
_STORAGE_FILE = Path(__file__).resolve().parent.parent / "quota_usage.json"
_lock         = Lock()

# Cache validated pairs so we don't re-test every request
_validated_pairs: dict[int, bool] = {}


def _today_utc() -> str:
    """Always use UTC date as the key so there's no PST/UTC mismatch."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _load() -> dict:
    try:
        if _STORAGE_FILE.exists():
            with open(_STORAGE_FILE, "r") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def _save(data: dict) -> None:
    try:
        with open(_STORAGE_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass


def _next_reset() -> str:
    now = datetime.now(timezone.utc)
    rd  = now.date() if now.hour < RESET_HOUR_UTC else (now + timedelta(days=1)).date()
    return datetime(rd.year, rd.month, rd.day, RESET_HOUR_UTC, 0, 0,
                    tzinfo=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _get_pairs() -> list[tuple[str, str]]:
    try:
        from config import GOOGLE_KEY_CX_PAIRS
        return GOOGLE_KEY_CX_PAIRS
    except Exception:
        return []


def _validate_pair(key: str, cx: str) -> bool:
    try:
        r = requests.get(
            "https://www.googleapis.com/customsearch/v1",
            params={"key": key, "cx": cx, "q": "test", "num": 1},
            timeout=8
        )
        return r.status_code in (200, 429)
    except Exception:
        return False


def _get_valid_pairs() -> list[tuple[int, str, str]]:
    """Return list of (index, key, cx) for validated working pairs."""
    pairs = _get_pairs()
    valid = []
    for i, (key, cx) in enumerate(pairs):
        if i not in _validated_pairs:
            _validated_pairs[i] = _validate_pair(key, cx)
        if _validated_pairs[i]:
            valid.append((i, key, cx))
    return valid


def get_status() -> dict:
    with _lock:
        today      = _today_utc()
        data       = _load()
        all_pairs  = _get_pairs()
        valid      = _get_valid_pairs()
        num_valid  = max(1, len(valid))
        total_lim  = DAILY_FREE_LIMIT_PER_KEY * num_valid
        used       = sum(int(data.get(f"{today}_key{i}", 0)) for i, _, _ in valid) if valid else 0
        remaining  = max(0, total_lim - used)

        key_status = []
        for i, (key, cx) in enumerate(all_pairs):
            ku  = int(data.get(f"{today}_key{i}", 0))
            key_status.append({
                "key_index": i + 1,
                "used":      ku,
                "remaining": max(0, DAILY_FREE_LIMIT_PER_KEY - ku),
                "exhausted": ku >= DAILY_FREE_LIMIT_PER_KEY,
                "valid":     _validated_pairs.get(i),
            })

        return {
            "date":           today,
            "num_keys":       len(all_pairs),
            "num_valid_keys": num_valid,
            "used":           used,
            "limit":          total_lim,
            "remaining":      remaining,
            "percent_used":   round(used / total_lim * 100, 1) if total_lim else 0,
            "exhausted":      remaining == 0,
            "resets_at_utc":  _next_reset(),
            "warning":        remaining < 20,
            "keys":           key_status,
        }


def get_active_pair() -> tuple[int, str, str]:
    """Return (index, key, cx) for the valid pair with most remaining quota."""
    valid = _get_valid_pairs()
    if not valid:
        pairs = _get_pairs()
        if pairs:
            return (0, pairs[0][0], pairs[0][1])
        return (0, "", "")

    with _lock:
        today = _today_utc()
        data  = _load()
        best  = valid[0]
        best_left = -1
        for i, key, cx in valid:
            left = DAILY_FREE_LIMIT_PER_KEY - int(data.get(f"{today}_key{i}", 0))
            if left > best_left:
                best_left = left
                best = (i, key, cx)
        return best


def record_queries(n: int, key_index: int | None = None) -> dict:
    """Record n queries used. If key_index is None, auto-select the active key."""
    if key_index is None:
        active = get_active_pair()
        key_index = active[0]
    if _validated_pairs.get(key_index) is False:
        return get_status()
    with _lock:
        today = _today_utc()
        data  = _load()
        kf = f"{today}_key{key_index}"
        data[kf] = int(data.get(kf, 0)) + max(0, int(n))
        # Also update the legacy non-keyed total for backwards compat
        data[today] = int(data.get(today, 0)) + max(0, int(n))
        cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d")
        data   = {k: v for k, v in data.items() if k.split("_key")[0] >= cutoff}
        _save(data)
    return get_status()


def can_run_check(queries_needed: int = 20) -> tuple[bool, str]:
    """
    Return (True, "") if at least one key has enough remaining quota.
    If no key has full quota but at least one has some, still allow a partial run
    (the plagiarism engine will stop early when quota is exhausted mid-run).
    """
    valid = _get_valid_pairs()
    if not valid:
        return False, "No valid API key+CX pairs configured."
    with _lock:
        today = _today_utc()
        data  = _load()
        max_left = 0
        for i, key, cx in valid:
            left = DAILY_FREE_LIMIT_PER_KEY - int(data.get(f"{today}_key{i}", 0))
            if left > max_left:
                max_left = left

    # Allow run if at least MIN_QUERIES_TO_START remain (meaningful partial check)
    MIN_QUERIES_TO_START = 8
    if max_left >= MIN_QUERIES_TO_START:
        return True, ""

    status = get_status()
    return False, (
        f"Remaining: {status['remaining']} queries (need at least {MIN_QUERIES_TO_START}). "
        f"Resets at {status['resets_at_utc']}."
    )


def history(days: int = 7) -> list[dict]:
    valid     = _get_valid_pairs()
    num_valid = max(1, len(valid))
    total_lim = DAILY_FREE_LIMIT_PER_KEY * num_valid
    with _lock:
        data = _load()
    result = []
    for i in range(days - 1, -1, -1):
        day  = (datetime.now(timezone.utc) - timedelta(days=i)).strftime("%Y-%m-%d")
        used = sum(int(data.get(f"{day}_key{ki}", 0)) for ki, _, _ in valid) if valid else int(data.get(day, 0))
        result.append({"date": day, "used": used, "remaining": max(0, total_lim - used), "limit": total_lim})
    return result
