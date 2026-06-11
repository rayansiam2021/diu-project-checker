import datetime
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import auth, reports, users, quota, clearance

log = logging.getLogger("uvicorn.error")
app = FastAPI(title="DIU Project Checker API", version="6.2")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(reports.router)
app.include_router(quota.router)
app.include_router(clearance.router)

@app.on_event("startup")
def _startup_check():
    from config import GOOGLE_API_KEY, GOOGLE_CX
    from services.quota_tracker import get_status
    status = get_status()
    if GOOGLE_API_KEY and GOOGLE_CX:
        log.info(f"✅ Google Search — Quota: {status['used']}/{status['limit']} used, {status['remaining']} remaining.")
    else:
        log.warning("⚠️  GOOGLE_API_KEY or GOOGLE_CX missing.")

@app.get("/health")
def health():
    from config import GOOGLE_API_KEY, GOOGLE_CX
    from services.quota_tracker import get_status
    return {"ok": True, "time": datetime.datetime.utcnow().isoformat(), "googleSearchConfigured": bool(GOOGLE_API_KEY and GOOGLE_CX), "quota": get_status()}