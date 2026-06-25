import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, kb, reports, tickets, users, webhook
from app.core.config import settings
from app.core.database import SessionLocal
from app.core.scheduler import shutdown_scheduler, start_scheduler
from app.services import sla_service, storage_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # schema จัดการด้วย Alembic — รัน `alembic upgrade head` ก่อน start แอป
    db = SessionLocal()
    try:
        sla_service.seed_default_policies(db)
    finally:
        db.close()
    try:
        storage_service.ensure_bucket()
    except Exception:  # noqa: BLE001
        logger.warning("MinIO not ready at startup")
    start_scheduler()
    yield
    shutdown_scheduler()


app = FastAPI(title="Line IT Ticket System", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_URL, "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(webhook.router)
app.include_router(tickets.router)
app.include_router(users.router)
app.include_router(reports.router)
app.include_router(kb.router)


@app.get("/health")
def health():
    return {"status": "ok"}
