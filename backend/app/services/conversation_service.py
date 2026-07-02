"""จัดการ conversation intake — multi-turn state เก็บ transcript + รูปที่รอผูก ticket."""
import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.conversation import Conversation


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _expiry() -> datetime:
    return _now() + timedelta(minutes=settings.CONVERSATION_MINUTES)


def get_active(
    db: Session, channel: str, source_id: str | None, line_user_id: str
) -> Conversation | None:
    """คืน conversation ที่ยัง active และไม่หมดอายุ — ที่หมดอายุจะปิดทิ้ง."""
    # ปิด conversation ที่หมดอายุก่อน
    db.execute(
        update(Conversation)
        .where(Conversation.status == "active", Conversation.expires_at < _now())
        .values(status="closed")
    )
    db.commit()
    return (
        db.query(Conversation)
        .filter(
            Conversation.status == "active",
            Conversation.channel == channel,
            Conversation.source_id.is_(source_id) if source_id is None
            else Conversation.source_id == source_id,
            Conversation.line_user_id == line_user_id,
        )
        .order_by(Conversation.id.desc())
        .first()
    )


def start(
    db: Session, channel: str, source_id: str | None, line_user_id: str
) -> Conversation:
    now = _now()
    conv = Conversation(
        channel=channel,
        source_id=source_id,
        line_user_id=line_user_id,
        status="active",
        transcript="[]",
        pending_images="[]",
        created_at=now,
        updated_at=now,
        expires_at=_expiry(),
    )
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return conv


def get_transcript(conv: Conversation) -> list[dict]:
    return json.loads(conv.transcript or "[]")


def append_message(
    db: Session, conv: Conversation, role: str, content: str, needs_confirm: bool = False
) -> None:
    """needs_confirm: เทิร์น assistant ที่ขึ้นปุ่มยืนยันเปิด ticket — เก็บ marker ไว้ใน
    transcript เพื่อให้เทิร์นถัดไปตรวจได้ว่า "ผ่านการขอยืนยันมาแล้ว" ก่อนยอมเปิด ticket."""
    history = get_transcript(conv)
    entry: dict = {"role": role, "content": content}
    if needs_confirm:
        entry["needs_confirm"] = True
    history.append(entry)
    conv.transcript = json.dumps(history, ensure_ascii=False)
    conv.updated_at = _now()
    conv.expires_at = _expiry()
    db.commit()


def get_pending_images(conv: Conversation) -> list[dict]:
    return json.loads(conv.pending_images or "[]")


def add_pending_image(
    db: Session, conv: Conversation, message_id: str, object_path: str, size: int
) -> None:
    imgs = get_pending_images(conv)
    imgs.append({"message_id": message_id, "object_path": object_path, "size": size})
    conv.pending_images = json.dumps(imgs, ensure_ascii=False)
    conv.updated_at = _now()
    conv.expires_at = _expiry()
    db.commit()


def close(db: Session, conv: Conversation, ticket_id: int | None = None) -> None:
    conv.status = "closed"
    if ticket_id is not None:
        conv.ticket_id = ticket_id
    conv.updated_at = _now()
    db.commit()
