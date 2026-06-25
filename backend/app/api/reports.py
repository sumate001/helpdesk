"""Dashboard stats / analytics."""
from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.ticket import Ticket
from app.models.user import User

router = APIRouter(prefix="/api/reports", tags=["reports"])


def _counts_by(db: Session, column) -> dict:
    rows = db.query(column, func.count(Ticket.id)).group_by(column).all()
    return {str(k): v for k, v in rows}


@router.get("/summary")
def summary(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    total = db.query(func.count(Ticket.id)).scalar()
    return {
        "total": total,
        "by_status": _counts_by(db, Ticket.status),
        "by_category": _counts_by(db, Ticket.category),
        "by_priority": _counts_by(db, Ticket.priority),
        "by_type": _counts_by(db, Ticket.type),
    }


@router.get("/sla")
def sla_report(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    total = db.query(func.count(Ticket.id)).scalar() or 0
    breached = (
        db.query(func.count(Ticket.id))
        .filter(Ticket.sla_breached.is_(True))
        .scalar()
        or 0
    )
    rate = round(breached / total * 100, 2) if total else 0.0
    return {"total": total, "breached": breached, "breach_rate_pct": rate}


@router.get("/top-issues")
def top_issues(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    rows = (
        db.query(Ticket.category, func.count(Ticket.id).label("c"))
        .group_by(Ticket.category)
        .order_by(func.count(Ticket.id).desc())
        .limit(10)
        .all()
    )
    return [{"category": str(cat), "count": c} for cat, c in rows]


@router.get("/resolution-time")
def resolution_time(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    avg_seconds = (
        db.query(
            func.avg(
                func.extract("epoch", Ticket.resolved_at)
                - func.extract("epoch", Ticket.created_at)
            )
        )
        .filter(Ticket.resolved_at.isnot(None))
        .scalar()
    )
    avg_minutes = round((avg_seconds or 0) / 60, 1)
    return {"avg_resolution_minutes": avg_minutes}
