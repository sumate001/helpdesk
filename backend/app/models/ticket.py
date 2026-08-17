from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Ticket(Base):
    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticket_no: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    line_user_id: Mapped[int | None] = mapped_column(ForeignKey("line_users.id"))
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(String(50))
    type: Mapped[str | None] = mapped_column(String(5))  # L1 | L2
    priority: Mapped[str | None] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(30), default="open")
    assigned_to: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    ai_response: Mapped[str | None] = mapped_column(Text)
    # เลขเคสในระบบ itamtv ที่เปิดคู่ขนานไว้ — ใช้สั่งปิด/อัปเดตสถานะทีหลัง
    itamtv_job_no: Mapped[str | None] = mapped_column(String(30))
    # ระดับ SLA (Level 1-4) ที่ AI ประเมินจากอาการ → itamtv ddllv (1=30น. 2=2ชม. 3=1วัน 4=Open)
    itamtv_level: Mapped[str | None] = mapped_column(String(1))
    # ครั้งล่าสุดที่บอทตามถามความคืบหน้าจากช่างที่รับงาน (in_progress) ทาง LINE —
    # scheduler ใช้เว้นจังหวะทุก STAFF_PROGRESS_MINUTES นาที
    staff_progress_ping_at: Mapped[datetime | None] = mapped_column(DateTime)
    # ผู้แจ้งเคส phone-in (staff เปิดแทนทางโทรศัพท์) — ไม่มี line_user จึงเก็บชื่อ/รายละเอียด
    # ผู้แจ้งไว้ตรงนี้เพื่อโชว์ในรายการเคส/แจ้งกลุ่ม/get_ticket
    reporter_name: Mapped[str | None] = mapped_column(String(100))
    reporter_detail: Mapped[str | None] = mapped_column(String(255))  # แผนก · ตึก-ชั้น · เบอร์
    sla_policy_id: Mapped[int | None] = mapped_column(ForeignKey("sla_policies.id"))
    sla_response_due_at: Mapped[datetime | None] = mapped_column(DateTime)
    sla_resolve_due_at: Mapped[datetime | None] = mapped_column(DateTime)
    sla_breached: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime)

    line_user = relationship("LineUser")
    assignee = relationship("User")
    comments = relationship(
        "TicketComment", back_populates="ticket", cascade="all, delete-orphan"
    )
    attachments = relationship(
        "TicketAttachment", back_populates="ticket", cascade="all, delete-orphan"
    )
    followups = relationship(
        "TicketFollowup", back_populates="ticket", cascade="all, delete-orphan"
    )
    equipment_request = relationship(
        "EquipmentRequest",
        back_populates="ticket",
        uselist=False,
        cascade="all, delete-orphan",
    )
