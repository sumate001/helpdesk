from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import settings
from app.core.database import Base


class KbChunk(Base):
    """Knowledge base chunk สำหรับ RAG — ความรู้ระบบ/นโยบาย IT ภายในบริษัท.

    1 หัวข้อ/1 chunk (เช่น "การขอใช้ VPN", "การ join domain ด้วย AD") เก็บ embedding
    ไว้ค้นแบบ semantic. category map เข้ากับ category ของ ticket ได้เพื่อช่วย classify.
    """

    __tablename__ = "kb_chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str | None] = mapped_column(String(255))
    content: Mapped[str] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(String(50))
    source: Mapped[str | None] = mapped_column(String(255))  # ที่มา ไว้ debug
    embedding: Mapped[list[float]] = mapped_column(Vector(settings.EMBED_DIM))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # ฟอร์มที่ผูกกับความรู้นี้ — RAG เจอ chunk นี้แล้วบอทยื่นปุ่มเปิดฟอร์มให้ (optional)
    form_id: Mapped[int | None] = mapped_column(
        ForeignKey("service_forms.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime)
