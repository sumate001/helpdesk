"""Ticket business logic — ticket_no generation, create, line user upsert."""
from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.line_user import LineUser
from app.models.ticket import Ticket
from app.services import sla_service


def generate_ticket_no(db: Session) -> str:
    """TK-YYYYMMDD-XXXX โดย XXXX คือ running ของวันนั้น.

    ใช้ค่า max ของเลข running ที่มีอยู่ (ไม่ใช่ count แถว) — count จะออกเลขซ้ำ
    ทันทีที่มี ticket ถูกลบระหว่างวัน. เลข zero-pad ความกว้างคงที่ ทำให้ max
    เชิง string เท่ากับ max เชิงตัวเลข.
    """
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    prefix = f"TK-{today}-"
    last = db.query(func.max(Ticket.ticket_no)).filter(
        Ticket.ticket_no.like(f"{prefix}%")
    ).scalar()
    running = int(last.rsplit("-", 1)[1]) + 1 if last else 1
    return f"{prefix}{running:04d}"


def upsert_line_user(db: Session, line_user_id: str, profile: dict | None = None) -> LineUser:
    user = (
        db.query(LineUser)
        .filter(LineUser.line_user_id == line_user_id)
        .one_or_none()
    )
    profile = profile or {}
    if user is None:
        user = LineUser(
            line_user_id=line_user_id,
            display_name=profile.get("displayName"),
            picture_url=profile.get("pictureUrl"),
        )
        db.add(user)
        db.flush()
    elif profile.get("displayName"):
        user.display_name = profile.get("displayName")
        user.picture_url = profile.get("pictureUrl") or user.picture_url
    return user


def create_ticket(
    db: Session,
    *,
    title: str,
    description: str | None = None,
    category: str | None = None,
    ticket_type: str = "L2",
    priority: str = "medium",
    status: str = "open",
    line_user_id: int | None = None,
    ai_response: str | None = None,
    resolved: bool = False,
) -> Ticket:
    ticket = Ticket(
        ticket_no=generate_ticket_no(db),
        title=title,
        description=description,
        category=category,
        type=ticket_type,
        priority=priority,
        status="resolved" if resolved else status,
        line_user_id=line_user_id,
        ai_response=ai_response,
    )
    if resolved:
        ticket.resolved_at = datetime.now(timezone.utc)
    db.add(ticket)
    db.flush()  # ให้ได้ created_at + id
    db.refresh(ticket)
    sla_service.apply_sla(db, ticket)
    db.commit()
    db.refresh(ticket)
    return ticket


def _brief(text: str, limit: int = 500) -> str:
    """ตัดรายละเอียดให้พอดีกับ notify — ตัดเฉพาะเมื่อยาวเกินจริง + ใส่ … บอกว่ามีต่อ."""
    text = text or ""
    return text if len(text) <= limit else text[:limit].rstrip() + "…"


def group_notify_text(ticket: Ticket) -> str:
    lu = ticket.line_user
    who = lu.display_name if lu else "-"
    dept = (lu.department or "-") if lu else "-"
    loc = ""
    if lu and (lu.building or lu.floor):
        loc = f" ({lu.building or ''}-{lu.floor or ''})"
    return (
        f"🎫 Ticket ใหม่: {ticket.ticket_no}\n"
        f"👤 ผู้แจ้ง: {who} ({dept}){loc}\n"
        f"📂 หมวด: {ticket.category}\n"
        f"🔴 Priority: {ticket.priority}\n"
        f"📝 {_brief(ticket.description or ticket.title)}"
    )
