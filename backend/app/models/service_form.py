from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ServiceForm(Base):
    """แบบฟอร์มขอใช้บริการที่ user กรอกผ่าน LIFF — นิยาม field แบบ dynamic เก็บเป็น JSON.

    ผูกกับ KB chunk ได้ (kb_chunks.form_id) → เมื่อ RAG เจอ chunk ที่มีฟอร์ม บอทจะยื่นปุ่ม
    เปิดฟอร์มนั้นให้อัตโนมัติ. fields = [{"key","label","type","required","options"}, ...]
    type: text | textarea | select | number
    """

    __tablename__ = "service_forms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255))            # ชื่อฟอร์ม เช่น "ขอใช้งาน VPN"
    slug: Mapped[str] = mapped_column(String(100), unique=True)  # ใช้ใน URL/LIFF เช่น "vpn"
    description: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(String(50))  # map เข้ากับ category ticket
    priority: Mapped[str] = mapped_column(String(20), default="low")
    fields: Mapped[list] = mapped_column(JSON, default=list)
    # กฎอนุมัติ — บังคับด้วยโค้ด ไม่ใช่ข้อความใน KB (KB อธิบายให้คนอ่าน ระบบตัดสินเอง)
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=False)
    approver_rule: Mapped[str] = mapped_column(String(20), default="supervisor")  # supervisor|fixed
    self_approve_positions: Mapped[list | None] = mapped_column(JSON)  # ตำแหน่งที่อนุมัติตัวเองได้
    fixed_approver_emp_code: Mapped[str | None] = mapped_column(String(20))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime)
