"""จัดการ group session — หลังเรียกบอทในกลุ่ม รูปที่ส่งตามมาในช่วงเวลาหนึ่งถือว่าคุยกับบอท."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.group_session import GroupSession


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def touch(
    db: Session, source_id: str, line_user_id: str, ticket_id: int | None = None
) -> None:
    """เปิด/ต่ออายุ session ของ (กลุ่ม, ผู้ใช้). ถ้ามี ticket_id ก็ผูกไว้ด้วย."""
    now = _now()
    expires = now + timedelta(minutes=settings.GROUP_SESSION_MINUTES)
    session = (
        db.query(GroupSession)
        .filter(
            GroupSession.source_id == source_id,
            GroupSession.line_user_id == line_user_id,
        )
        .one_or_none()
    )
    if session is None:
        session = GroupSession(source_id=source_id, line_user_id=line_user_id)
        db.add(session)
    session.expires_at = expires
    session.updated_at = now
    if ticket_id is not None:
        session.ticket_id = ticket_id
    db.commit()


def get_active(
    db: Session, source_id: str, line_user_id: str
) -> GroupSession | None:
    """คืน session ที่ยังไม่หมดอายุ — ถ้าหมดอายุคืน None (และลบของเก่าทิ้ง)."""
    db.execute(delete(GroupSession).where(GroupSession.expires_at < _now()))
    db.commit()
    session = (
        db.query(GroupSession)
        .filter(
            GroupSession.source_id == source_id,
            GroupSession.line_user_id == line_user_id,
        )
        .one_or_none()
    )
    if session is None or _aware(session.expires_at) < _now():
        return None
    return session
