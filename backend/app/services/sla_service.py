"""SLA calculation + breach check."""
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.sla_policy import SLAPolicy
from app.models.ticket import Ticket

DEFAULT_SLA = {
    "critical": (15, 60),
    "high": (30, 240),
    "medium": (120, 1440),
    "low": (240, 4320),
}


def seed_default_policies(db: Session) -> None:
    for priority, (resp, resolve) in DEFAULT_SLA.items():
        existing = (
            db.query(SLAPolicy).filter(SLAPolicy.priority == priority).one_or_none()
        )
        if existing is None:
            db.add(
                SLAPolicy(
                    priority=priority,
                    response_time_minutes=resp,
                    resolve_time_minutes=resolve,
                )
            )
    db.commit()


def apply_sla(db: Session, ticket: Ticket) -> None:
    """กำหนด sla_policy + due dates ให้ ticket ตาม priority (เริ่มนับจาก created_at)."""
    policy = (
        db.query(SLAPolicy).filter(SLAPolicy.priority == ticket.priority).one_or_none()
    )
    if policy is None:
        return
    base = ticket.created_at or datetime.now(timezone.utc)
    ticket.sla_policy_id = policy.id
    ticket.sla_response_due_at = base + timedelta(minutes=policy.response_time_minutes)
    ticket.sla_resolve_due_at = base + timedelta(minutes=policy.resolve_time_minutes)


def check_breaches(db: Session) -> int:
    """mark breach สำหรับ ticket ที่เกิน due และยังไม่ resolved. คืนจำนวนที่ mark."""
    now = datetime.now(timezone.utc)
    open_tickets = (
        db.query(Ticket)
        .filter(
            Ticket.status.notin_(["resolved", "closed"]),
            Ticket.sla_breached.is_(False),
        )
        .all()
    )
    count = 0
    for t in open_tickets:
        due = t.sla_resolve_due_at
        if due is not None:
            if due.tzinfo is None:
                due = due.replace(tzinfo=timezone.utc)
            if due < now:
                t.sla_breached = True
                count += 1
    if count:
        db.commit()
    return count
