from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class LineUser(Base):
    __tablename__ = "line_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    line_user_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(100))
    # ชื่อ-นามสกุลที่ผู้แจ้งบอกบอทเอง — ต่างจาก display_name ที่เป็นชื่อเล่นใน LINE
    # (โดน profile ทับทุกข้อความ) และต่างจาก emp_name ที่ยืนยันกับ Employee DB แล้ว
    self_name: Mapped[str | None] = mapped_column(String(100))
    picture_url: Mapped[str | None] = mapped_column(Text)
    department: Mapped[str | None] = mapped_column(String(100))
    position: Mapped[str | None] = mapped_column(String(100))
    # เบอร์ติดต่อที่ผู้แจ้งบอกบอทไว้ (itamtv บังคับช่องนี้ และ Employee DB มักไม่มี)
    phone: Mapped[str | None] = mapped_column(String(30))
    # ผูกกับ Amarin Employee DB (ลงทะเบียนด้วยรหัสพนักงาน/อีเมล — lookup สด ไม่ cache)
    employee_id: Mapped[int | None] = mapped_column(Integer)
    emp_code: Mapped[str | None] = mapped_column(String(20))
    emp_email: Mapped[str | None] = mapped_column(String(100))
    emp_name: Mapped[str | None] = mapped_column(String(100))
    building: Mapped[str | None] = mapped_column(String(100))
    floor: Mapped[str | None] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    @property
    def known_name(self) -> str | None:
        """ชื่อที่ดีที่สุดเท่าที่มี: ยืนยันกับ Employee DB > ที่ผู้แจ้งบอกเอง > ชื่อเล่นใน LINE

        ใช้ได้เฉพาะตอน "แสดงผล" — ห้ามใช้ระบุตัวคนข้ามระบบ (เช่น dropdown ผู้แจ้งของ
        itamtv) เพราะ display_name เป็นชื่อเล่นที่ผู้ใช้ตั้งเองใน LINE
        """
        return self.emp_name or self.self_name or self.display_name
