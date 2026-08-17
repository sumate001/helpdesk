"""Follow-up scheduler jobs — เกาะกับ conversation intake (ผู้ใช้เงียบกลางบทสนทนา).

T+10m : บอทถามอะไรไว้แล้วผู้ใช้เงียบ → ส่งข้อความถามซ้ำ (quick reply แก้ได้แล้ว/ยังไม่ได้)
T+30m : ยังเงียบต่อ → เปิด ticket L2 จาก transcript + แจ้ง IT Group + ปิด conversation

เปิด/ปิดทั้ง flow ได้สดๆ ผ่าน setting FOLLOWUP_ENABLED (หน้า Settings — ไม่ต้อง restart).
"""
import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.conversation import Conversation
from app.models.line_user import LineUser
from app.models.ticket import Ticket
from app.models.ticket_attachment import TicketAttachment
from app.models.ticket_followup import TicketFollowup
from app.models.user import User
from app.services import line_service, settings_service, ticket_service

logger = logging.getLogger(__name__)

FOLLOWUP_TEXT = "แวะมาตามเรื่องที่คุยกันไว้ครับ 👋 พอจะได้ลองหรือยัง เป็นยังไงบ้าง?"


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


def _push_target(conv: Conversation) -> str:
    """กลุ่ม → push เข้ากลุ่มเดิม, 1-1 → push หาผู้ใช้ตรงๆ."""
    return conv.source_id if conv.channel == "group" else conv.line_user_id


def run_followup_tick() -> None:
    """เรียกโดย scheduler ทุกนาที — ตรวจ conversation ที่ผู้ใช้เงียบเกินกำหนด."""
    if not settings_service.get("FOLLOWUP_ENABLED"):
        return
    db = SessionLocal()
    try:
        _process_followups(db)
        _process_escalations(db)
    except Exception:  # noqa: BLE001
        logger.exception("followup tick error")
    finally:
        db.close()


def run_staff_progress_tick() -> None:
    """เรียกโดย scheduler ทุกนาที — ตามถามความคืบหน้าจากช่างที่รับงานค้างไว้.

    เคย in_progress + มีผู้รับผิดชอบที่ผูก LINE + ครบ STAFF_PROGRESS_MINUTES นาที
    ตั้งแต่ ping ล่าสุด (หรือตั้งแต่รับงานถ้ายังไม่เคย ping) → push การ์ดถามคืบหน้า
    พร้อมปุ่มปิดเคส. เสร็จแล้ว staff กดปุ่มปิด/บอกบอทให้ปิดได้เลย.

    เปิด/ปิดทั้ง flow ได้สดๆ ผ่าน setting STAFF_PROGRESS_ENABLED (หน้า Settings).
    """
    if not settings_service.get("STAFF_PROGRESS_ENABLED"):
        return
    db = SessionLocal()
    try:
        _process_staff_progress(db)
    except Exception:  # noqa: BLE001
        logger.exception("staff progress tick error")
    finally:
        db.close()


def _process_staff_progress(db: Session) -> None:
    threshold = _now() - timedelta(minutes=settings.STAFF_PROGRESS_MINUTES)
    rows = (
        db.query(Ticket, User)
        .join(User, Ticket.assigned_to == User.id)
        .filter(
            Ticket.status == "in_progress",
            User.is_active.is_(True),
            User.line_user_id.isnot(None),
        )
        .all()
    )
    for ticket, staff in rows:
        # เทียบกับ ping ล่าสุด — ยังไม่เคย ping ให้อิงเวลา updated_at (ตอนเปลี่ยนเป็น in_progress)
        last = ticket.staff_progress_ping_at or ticket.updated_at
        if last and last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        if last and last > threshold:
            continue
        flex = line_service.progress_case_flex(
            ticket.ticket_no, ticket.id, ticket.title or ticket.description or "-"
        )
        asyncio.run(line_service.push_flex(staff.line_user_id, flex))
        ticket.staff_progress_ping_at = _now()
        db.commit()
        logger.info("staff progress ping sent for %s → %s", ticket.ticket_no, staff.username)


def _silent_conversations(db: Session, minutes: int, followed_up: bool) -> list[Conversation]:
    """conversation ที่ยัง active, ยังไม่มี ticket และผู้ใช้เงียบมาแล้ว >= minutes."""
    threshold = _now() - timedelta(minutes=minutes)
    q = (
        db.query(Conversation)
        .filter(
            Conversation.status == "active",
            Conversation.channel.in_(("user", "group")),  # กัน channel="staff" (ผู้ช่วย IT) โดนเปิด ticket
            Conversation.ticket_id.is_(None),
            Conversation.updated_at <= threshold,
        )
    )
    if followed_up:
        q = q.filter(Conversation.followup_sent_at.isnot(None))
    else:
        q = q.filter(Conversation.followup_sent_at.is_(None))
    return q.all()


def _last_role(conv: Conversation) -> str | None:
    try:
        transcript = json.loads(conv.transcript or "[]")
    except json.JSONDecodeError:
        return None
    return transcript[-1]["role"] if transcript else None


def _process_followups(db: Session) -> None:
    for conv in _silent_conversations(db, settings.FOLLOWUP_DELAY_MINUTES, followed_up=False):
        # ตามเฉพาะเคสที่บอทถาม/แนะนำไว้แล้วผู้ใช้เงียบ — ถ้าจบที่ฝั่งผู้ใช้แปลว่าบอทยังไม่ตอบ
        if _last_role(conv) != "assistant":
            continue
        asyncio.run(line_service.push(_push_target(conv), FOLLOWUP_TEXT, with_quick_reply=True))
        conv.followup_sent_at = _now()
        # ต่ออายุ conversation ให้อยู่ถึงรอบ escalate — คำตอบของผู้ใช้จะยังเข้าบทสนทนาเดิม
        conv.expires_at = _now() + timedelta(
            minutes=settings.ESCALATE_DELAY_MINUTES - settings.FOLLOWUP_DELAY_MINUTES + 5
        )
        db.commit()
        logger.info("followup sent for conversation %s", conv.id)


def _transcript_description(conv: Conversation) -> str:
    """สรุป transcript เป็น description ให้ช่างอ่านต่อได้ (ผู้ใช้เงียบ AI สรุปเองไม่ได้แล้ว)."""
    try:
        transcript = json.loads(conv.transcript or "[]")
    except json.JSONDecodeError:
        transcript = []
    lines = [
        f"{'ผู้แจ้ง' if m['role'] == 'user' else 'บอท'}: {m['content']}"
        for m in transcript
    ]
    header = "เปิดอัตโนมัติ: ผู้ใช้ไม่ตอบกลับหลังบอทติดตาม — บทสนทนาที่คุยไว้:\n"
    return header + "\n".join(lines)


def _first_user_message(conv: Conversation) -> str:
    try:
        transcript = json.loads(conv.transcript or "[]")
    except json.JSONDecodeError:
        transcript = []
    for m in transcript:
        if m["role"] == "user" and m["content"].strip():
            return m["content"].strip()
    return "ปัญหาที่แจ้งผ่าน Line"


def _process_escalations(db: Session) -> None:
    for conv in _silent_conversations(db, settings.ESCALATE_DELAY_MINUTES, followed_up=True):
        lu = (
            db.query(LineUser)
            .filter(LineUser.line_user_id == conv.line_user_id)
            .one_or_none()
        )
        ticket = ticket_service.create_ticket(
            db,
            title=_first_user_message(conv)[:255],
            description=_transcript_description(conv),
            category="other",
            ticket_type="L2",
            priority="medium",
            status="open",
            line_user_id=lu.id if lu else None,
        )
        # ผูกรูปที่ค้างอยู่ระหว่าง intake เข้า ticket
        for img in json.loads(conv.pending_images or "[]"):
            db.add(
                TicketAttachment(
                    ticket_id=ticket.id,
                    file_name=f"{img['message_id']}.jpg",
                    file_path=img["object_path"],
                    mime_type="image/jpeg",
                    file_size=img["size"],
                    line_message_id=img["message_id"],
                )
            )
        # เก็บ record ไว้ทำสถิติ + รองรับปุ่ม quick reply ที่ผู้ใช้อาจกดทีหลัง
        db.add(
            TicketFollowup(
                ticket_id=ticket.id,
                followup_sent_at=conv.followup_sent_at,
                escalated=True,
                escalated_at=_now(),
            )
        )
        conv.status = "closed"
        conv.ticket_id = ticket.id
        conv.updated_at = _now()
        db.commit()
        db.refresh(ticket)

        escalate_text = (
            f"เห็นว่าเงียบไป ผมส่งเรื่องให้ทีม IT ตามต่อให้แล้วนะครับ จะได้ไม่ค้าง 🔧\nเลขที่เคส {ticket.ticket_no}"
        )
        asyncio.run(line_service.push(_push_target(conv), escalate_text))
        asyncio.run(line_service.notify_group(*ticket_service.group_notify(ticket)))
        # ไม่ mirror ไป itamtv ตรงนี้ — รอช่างกดรับงานแล้วเปิดด้วย token ของช่างคนนั้น
        logger.info("escalated conversation %s → ticket %s", conv.id, ticket.ticket_no)
