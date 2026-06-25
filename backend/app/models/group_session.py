from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class GroupSession(Base):
    """session ชั่วคราวต่อ (กลุ่ม, ผู้ใช้) — หลังเรียกบอทในกลุ่ม รูปที่ส่งตามมาในช่วงนี้
    ถือว่าเป็นของบทสนทนากับบอท แล้วผูกเข้า ticket ที่เปิดไว้."""

    __tablename__ = "group_sessions"
    __table_args__ = (UniqueConstraint("source_id", "line_user_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[str] = mapped_column(String(100))  # groupId หรือ roomId
    line_user_id: Mapped[str] = mapped_column(String(100))  # LINE userId ของผู้แจ้ง
    ticket_id: Mapped[int | None] = mapped_column(ForeignKey("tickets.id"))
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime)
