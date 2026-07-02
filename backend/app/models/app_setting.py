from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AppSetting(Base):
    """Runtime settings ที่แก้ได้จาก UI (override ค่า default ใน .env).

    เก็บแบบ key-value (value เป็น text เสมอ — service จะ coerce ตาม type ที่กำหนด).
    ใช้กับค่าที่อยากปรับสดๆ ไม่ต้อง restart เช่น OLLAMA_MODEL, RAG params.
    """

    __tablename__ = "app_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime)
