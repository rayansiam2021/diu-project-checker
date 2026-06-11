"""
routers/quota.py — Quota monitoring endpoints.
"""
from fastapi import APIRouter
from services.quota_tracker import get_status, history, can_run_check, DAILY_FREE_LIMIT_PER_KEY

router = APIRouter(tags=["quota"])
QUERIES_PER_REPORT = 20


@router.get("/quota")
def quota_status():
    status = get_status()
    ok, reason = can_run_check(queries_needed=QUERIES_PER_REPORT)
    status["can_run_full_check"] = ok
    status["block_reason"]       = reason if not ok else ""
    status["queries_per_report"] = QUERIES_PER_REPORT
    status["reports_remaining"]  = int(status["remaining"] // QUERIES_PER_REPORT)
    return status


@router.get("/quota/history")
def quota_history(days: int = 7):
    days = max(1, min(int(days), 30))
    return {
        "days":               history(days),
        "daily_limit_per_key": DAILY_FREE_LIMIT_PER_KEY,
        "total_daily_limit":  get_status()["limit"],
        "queries_per_report": QUERIES_PER_REPORT,
        "cost_per_query":     0.0,
    }
