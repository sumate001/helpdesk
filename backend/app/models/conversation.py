from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Conversation(Base):
    """บทสนทนา intake แบบ multi-turn — บอทแก้ปัญหาเบื้องต้น/เก็บข้อมูลก่อนเปิด ticket.

    ใช้ทั้งแชต 1-1 (channel='user', source_id=NULL) และกลุ่ม (channel='group',
    source_id=groupId/roomId). ขณะ active ข้อความถัดมาของผู้ใช้คนเดิมถือว่าอยู่ในบทสนทนานี้.
    """

    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    channel: Mapped[str] = mapped_column(String(10))  # user | group
    source_id: Mapped[str | None] = mapped_column(String(100))  # groupId/roomId (NULL ถ้า 1-1)
    line_user_id: Mapped[str] = mapped_column(String(100), index=True)
    status: Mapped[str] = mapped_column(String(10), default="active")  # active | closed
    transcript: Mapped[str] = mapped_column(Text, default="[]")  # JSON list ของ {role, content}
    pending_images: Mapped[str] = mapped_column(Text, default="[]")  # JSON list รูปที่รอผูก ticket
    ticket_id: Mapped[int | None] = mapped_column(ForeignKey("tickets.id"))
    # follow-up: ส่งข้อความถามซ้ำไปแล้วเมื่อไหร่ (NULL = ยังไม่ส่ง) — ใช้กันส่งซ้ำ
    followup_sent_at: Mapped[datetime | None] = mapped_column(DateTime)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime)
