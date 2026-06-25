"""APScheduler setup — follow-up / SLA / escalation jobs.

ใช้ SQLAlchemy jobstore เพื่อให้ survive restart.
"""
import logging

from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.background import BackgroundScheduler

from app.core.config import settings

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler(
    jobstores={"default": SQLAlchemyJobStore(url=settings.DATABASE_URL)},
    timezone="UTC",
)


def _followup_job() -> None:
    from app.services.followup_service import run_followup_tick

    run_followup_tick()


def _sla_job() -> None:
    from app.core.database import SessionLocal
    from app.services.sla_service import check_breaches

    db = SessionLocal()
    try:
        check_breaches(db)
    finally:
        db.close()


def start_scheduler() -> None:
    if scheduler.running:
        return
    scheduler.add_job(
        _followup_job,
        "interval",
        minutes=1,
        id="followup_tick",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        _sla_job,
        "interval",
        minutes=1,
        id="sla_check",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    logger.info("scheduler started")


def shutdown_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
