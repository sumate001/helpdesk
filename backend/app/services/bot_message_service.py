"""เก็บ / เช็ค message id ที่บอทส่ง — ใช้ดูว่า user quote-reply ข้อความบอทไหม."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models.bot_message import BotMessage

RETENTION_DAYS = 30


def record(db: Session, message_ids: list[str]) -> None:
    """บันทึก message id ที่บอทเพิ่งส่ง (ข้าม id ที่ซ้ำ) + ล้างของเก่าทิ้ง."""
    if not message_ids:
        return
    db.execute(
        insert(BotMessage)
        .values([{"line_message_id": mid} for mid in message_ids])
        .on_conflict_do_nothing(index_elements=["line_message_id"])
    )
    cutoff = datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)
    db.execute(delete(BotMessage).where(BotMessage.created_at < cutoff))
    db.commit()


def is_bot_message(db: Session, message_id: str | None) -> bool:
    if not message_id:
        return False
    return (
        db.query(BotMessage.id)
        .filter(BotMessage.line_message_id == message_id)
        .first()
        is not None
    )
