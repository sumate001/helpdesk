from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class BotMessage(Base):
    """message id ที่บอทส่งออกไป — ใช้เช็คว่า user quote-reply ข้อความบอทหรือไม่."""

    __tablename__ = "bot_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    line_message_id: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
