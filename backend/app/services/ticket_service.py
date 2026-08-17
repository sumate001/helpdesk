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


STATUS_LABELS_TH = {
    "open": "รอทีม IT รับเรื่อง",
    "pending_approval": "รออนุมัติ",
    "in_progress": "ทีม IT กำลังดำเนินการ",
    "resolved": "แก้ไขเสร็จแล้ว",
    "closed": "ปิดเคสแล้ว",
    "ai_answered": "แก้ได้จากคำแนะนำเบื้องต้น",
}


def recent_tickets(db: Session, line_user_db_id: int, limit: int = 5) -> list[dict]:
    """ticket ล่าสุดของผู้แจ้งคนนี้ → ป้อนเข้า system prompt ให้ AI ตอบเรื่องสถานะได้เอง.

    เอาทุกสถานะ (รวม closed) เพราะผู้ใช้มักถามถึงเคสที่เพิ่งปิดไปด้วย.
    """
    rows = (
        db.query(Ticket)
        .filter(Ticket.line_user_id == line_user_db_id)
        .order_by(Ticket.id.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "ticket_no": t.ticket_no,
            "title": t.title,
            "status": t.status,
            "status_th": STATUS_LABELS_TH.get(t.status, t.status),
            "assignee": t.assignee.display_name if t.assignee else None,
            "created_at": t.created_at.strftime("%d/%m/%Y %H:%M") if t.created_at else None,
            "resolved_at": t.resolved_at.strftime("%d/%m/%Y %H:%M") if t.resolved_at else None,
        }
        for t in rows
    ]


def _ticket_dict(t: Ticket) -> dict:
    """สรุป ticket หนึ่งใบเป็น dict ให้ staff assistant อ่าน (มีชื่อผู้แจ้ง/ผู้ดูแล)."""
    lu = t.line_user
    # ผู้แจ้ง: LINE user ถ้ามี, ไม่งั้น fallback ผู้แจ้ง phone-in ที่ staff เปิดแทน
    reporter = lu.known_name if lu else t.reporter_name
    department = (lu.department if lu else None) or (t.reporter_detail if not lu else None)
    return {
        "ticket_no": t.ticket_no,
        "title": t.title,
        "category": t.category,
        "priority": t.priority,
        "status": t.status,
        "status_th": STATUS_LABELS_TH.get(t.status, t.status),
        "reporter": reporter,
        "department": department,
        "assignee": t.assignee.display_name if t.assignee else None,
        "description": _brief(t.description or t.title or "", 300),
        "created_at": t.created_at.strftime("%d/%m/%Y %H:%M") if t.created_at else None,
        "resolved_at": t.resolved_at.strftime("%d/%m/%Y %H:%M") if t.resolved_at else None,
    }


def search_tickets(
    db: Session,
    status: str | None = None,
    assignee_id: int | None = None,
    query: str | None = None,
    limit: int = 10,
) -> list[dict]:
    """ค้น ticket ให้โหมดผู้ช่วย staff — filter สถานะ/ผู้ดูแล/คำค้น (title+description+เลขเคส)."""
    q = db.query(Ticket)
    if status:
        q = q.filter(Ticket.status == status)
    if assignee_id is not None:
        q = q.filter(Ticket.assigned_to == assignee_id)
    if query:
        like = f"%{query.strip()}%"
        q = q.filter(
            Ticket.title.ilike(like)
            | Ticket.description.ilike(like)
            | Ticket.ticket_no.ilike(like)
        )
    rows = q.order_by(Ticket.id.desc()).limit(limit).all()
    return [_ticket_dict(t) for t in rows]


def get_by_no(db: Session, ticket_no: str) -> Ticket | None:
    return (
        db.query(Ticket)
        .filter(Ticket.ticket_no.ilike(ticket_no.strip()))
        .one_or_none()
    )


def _brief(text: str, limit: int = 500) -> str:
    """ตัดรายละเอียดให้พอดีกับ notify — ตัดเฉพาะเมื่อยาวเกินจริง + ใส่ … บอกว่ามีต่อ."""
    text = text or ""
    return text if len(text) <= limit else text[:limit].rstrip() + "…"


def group_notify_text(ticket: Ticket) -> str:
    return group_notify(ticket)[0]


def group_notify(ticket: Ticket) -> tuple[str, dict[str, str]]:
    """ข้อความแจ้งกลุ่ม IT + mentions ({label → LINE userId}) สำหรับ @ เรียกผู้รับมอบหมาย.

    ผู้รับมอบหมายที่ยังไม่ผูก LINE (หรือยังไม่มอบหมาย) → ไม่มี mention, ขึ้นข้อความชวน
    ให้ทีมกดรับงานแทน.
    """
    lu = ticket.line_user
    # เคส phone-in ไม่มี line_user → ใช้ชื่อ/รายละเอียดผู้แจ้งที่ staff กรอกไว้แทน
    who = (lu.known_name if lu else ticket.reporter_name) or "-"
    dept = ((lu.department or "-") if lu else (ticket.reporter_detail or "-")) or "-"
    loc = ""
    if lu and (lu.building or lu.floor):
        loc = f" ({lu.building or ''}-{lu.floor or ''})"

    assignee = ticket.assignee
    mentions: dict[str, str] = {}
    ping = ""
    if assignee is not None:
        name = assignee.display_name or assignee.username
        owner = f"👷 ผู้รับผิดชอบ: {name}\n"
        # บรรทัด ping ท้ายข้อความ — @ ไว้เรียกใน LINE group (ชื่อในรายละเอียดคงรูปเดิม)
        if assignee.line_user_id:
            label = f"@{name}"
            mentions[label] = assignee.line_user_id
            ping = f"\n\n🔔 {label} รับเรื่องด้วยครับ"
    else:
        owner = "👷 ผู้รับผิดชอบ: ยังไม่มอบหมาย — ใครสะดวกกดรับงานได้เลยครับ\n"

    text = (
        f"🎫 Ticket ใหม่: {ticket.ticket_no}\n"
        f"👤 ผู้แจ้ง: {who} ({dept}){loc}\n"
        f"📂 หมวด: {ticket.category}\n"
        f"🔴 Priority: {ticket.priority}\n"
        f"{owner}"
        f"📝 {_brief(ticket.description or ticket.title)}"
        f"{ping}"
    )
    return text, mentions
