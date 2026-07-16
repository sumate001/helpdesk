from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(100))
    # LINE userId ของช่าง — ใช้ push แจ้งเตือน + ยืนยันตัวตนตอนกดปุ่มปิดเคสจาก LINE
    line_user_id: Mapped[str | None] = mapped_column(String(100), unique=True)
    # สิทธิ์ปิดเคสในระบบ itamtv: token ส่วนตัวช่าง + emp code (ผู้รับผิดชอบ)
    itamtv_token: Mapped[str | None] = mapped_column(String(100))
    itamtv_emp_code: Mapped[str | None] = mapped_column(String(20))
    role: Mapped[str] = mapped_column(String(20), default="staff")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
