"""Follow-up scheduler jobs (L1 flow).

T+10m : ถ้า user ยังไม่ตอบ → ส่งข้อความถามซ้ำ
T+30m : ถ้ายังไม่ตอบ → escalate เป็น L2 + แจ้ง IT Group
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.line_user import LineUser
from app.models.ticket import Ticket
from app.models.ticket_followup import TicketFollowup
from app.services import line_service, ticket_service

logger = logging.getLogger(__name__)

FOLLOWUP_TEXT = "สวัสดีครับ 👋 ขอติดตามเรื่องที่แจ้งไว้นะครับ\nดำเนินการได้แล้วหรือยังครับ?"


def schedule_l1_followup(db: Session, ticket: Ticket) -> TicketFollowup:
    """สร้าง followup tracking record ตอนเปิด L1 ticket."""
    fu = TicketFollowup(ticket_id=ticket.id)
    db.add(fu)
    db.commit()
    db.refresh(fu)
    return fu


def mark_responded(db: Session, ticket_id: int) -> None:
    fu = (
        db.query(TicketFollowup)
        .filter(TicketFollowup.ticket_id == ticket_id)
        .order_by(TicketFollowup.id.desc())
        .first()
    )
    if fu:
        fu.user_responded = True
        db.commit()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def run_followup_tick() -> None:
    """เรียกโดย scheduler ทุกนาที — ตรวจ followup ที่ถึงเวลา."""
    db = SessionLocal()
    try:
        _process_followups(db)
        _process_escalations(db)
    except Exception:  # noqa: BLE001
        logger.exception("followup tick error")
    finally:
        db.close()


def _process_followups(db: Session) -> None:
    threshold = _now() - timedelta(minutes=settings.FOLLOWUP_DELAY_MINUTES)
    pending = (
        db.query(TicketFollowup, Ticket, LineUser)
        .join(Ticket, Ticket.id == TicketFollowup.ticket_id)
        .join(LineUser, LineUser.id == Ticket.line_user_id)
        .filter(
            TicketFollowup.user_responded.is_(False),
            TicketFollowup.escalated.is_(False),
            TicketFollowup.followup_sent_at.is_(None),
            Ticket.created_at <= threshold,
        )
        .all()
    )
    for fu, ticket, lu in pending:
        asyncio.run(line_service.push(lu.line_user_id, FOLLOWUP_TEXT, with_quick_reply=True))
        fu.followup_sent_at = _now()
        db.commit()
        logger.info("followup sent for ticket %s", ticket.ticket_no)


def _process_escalations(db: Session) -> None:
    threshold = _now() - timedelta(minutes=settings.ESCALATE_DELAY_MINUTES)
    pending = (
        db.query(TicketFollowup, Ticket, LineUser)
        .join(Ticket, Ticket.id == TicketFollowup.ticket_id)
        .join(LineUser, LineUser.id == Ticket.line_user_id)
        .filter(
            TicketFollowup.user_responded.is_(False),
            TicketFollowup.escalated.is_(False),
            Ticket.created_at <= threshold,
        )
        .all()
    )
    for fu, ticket, lu in pending:
        ticket.type = "L2"
        ticket.status = "open"
        fu.escalated = True
        fu.escalated_at = _now()
        db.commit()
        db.refresh(ticket)

        escalate_text = (
            f"ทีม IT จะติดตามเรื่องนี้ให้นะครับ 🔧\nหมายเลข Ticket: {ticket.ticket_no}"
        )
        asyncio.run(line_service.push(lu.line_user_id, escalate_text))
        asyncio.run(line_service.notify_group(ticket_service.group_notify_text(ticket)))
        logger.info("escalated ticket %s to L2", ticket.ticket_no)
