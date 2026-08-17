from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class DepartmentApprover(Base):
    """ผังผู้อนุมัติตามแผนก — Employee DB ไม่มีสายบังคับบัญชา เราจึง map เอง.

    เติมได้ 2 ทาง: IT กรอกในหน้า "การอนุมัติ" หรือระบบเสนอให้อัตโนมัติเมื่อผู้ขอเลือก
    หัวหน้าเอง (is_confirmed=False จนกว่า IT จะกดยืนยัน) → ตารางค่อยๆ เต็มจากการใช้จริง
    """

    __tablename__ = "department_approvers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    department: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    approver_emp_code: Mapped[str] = mapped_column(String(20))
    approver_name: Mapped[str | None] = mapped_column(String(100))
    approver_email: Mapped[str | None] = mapped_column(String(100))
    # ผู้อนุมัติสำรอง ใช้เมื่อคนหลักไม่ผูก LINE / ไม่ตอบจนหมดเวลา
    backup_emp_code: Mapped[str | None] = mapped_column(String(20))
    backup_name: Mapped[str | None] = mapped_column(String(100))
    # False = ระบบเดาให้จากที่ผู้ขอเลือก ยังรอ IT ยืนยัน
    is_confirmed: Mapped[bool] = mapped_column(Boolean, default=True)
    # ตัวผู้อนุมัติเองกด "ยอมรับ" บทบาทแล้วหรือยัง (แจ้งทาง LINE ตอนถูกเพิ่ม)
    accepted: Mapped[bool | None] = mapped_column(Boolean, default=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime)
    notified_at: Mapped[datetime | None] = mapped_column(DateTime)
    # ถ้ามาจากผู้ขอแจ้งเอง เก็บไว้ว่าใครแจ้ง (ไว้ตรวจย้อนหลัง)
    proposed_by_line_user_id: Mapped[str | None] = mapped_column(String(100))
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime)


class ApprovalRequest(Base):
    """คำขออนุมัติหนึ่งใบ ผูกกับ ticket — 1 ticket มีได้หลายขั้น (step 1, 2, ...).

    เฟสแรกอนุมัติผ่าน LINE (ปุ่ม postback → รู้ userId ผู้กดแน่นอน ปลอมไม่ได้)
    คอลัมน์ token_hash/expires_at/channel เตรียมไว้ให้ช่องทางอีเมลในเฟสถัดไป
    ใช้ได้เลยโดยไม่ต้อง migrate ซ้ำ
    """

    __tablename__ = "approval_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id", ondelete="CASCADE"), index=True)
    step: Mapped[int] = mapped_column(Integer, default=1)

    # ผู้อนุมัติ — เก็บ snapshot ไว้ ไม่อ้าง map สดเพราะผังอาจถูกแก้ทีหลัง
    approver_emp_code: Mapped[str | None] = mapped_column(String(20))
    approver_name: Mapped[str | None] = mapped_column(String(100))
    approver_email: Mapped[str | None] = mapped_column(String(100))
    approver_line_user_id: Mapped[str | None] = mapped_column(String(100), index=True)
    # ผู้ขอเลือกหัวหน้าเอง (ไม่ได้มาจากผังที่ IT ยืนยัน) → ให้ IT เห็นว่าควรตรวจ
    approver_from_requester: Mapped[bool] = mapped_column(Boolean, default=False)

    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    # pending | approved | rejected | expired | cancelled | no_approver
    channel: Mapped[str] = mapped_column(String(10), default="line")  # line | email | manual
    comment: Mapped[str | None] = mapped_column(Text)  # เหตุผล (โดยเฉพาะตอนไม่อนุมัติ)
    # ปฏิเสธแล้วบอทถามเหตุผลต่อ 1 ข้อความ — ธงนี้บอกว่ากำลังรอข้อความนั้นอยู่
    awaiting_reason: Mapped[bool] = mapped_column(Boolean, default=False)

    # เตรียมไว้สำหรับอนุมัติผ่านอีเมล (เฟสถัดไป): ลิงก์ใช้ครั้งเดียว มีวันหมดอายุ
    token_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime)

    decided_by_line_user_id: Mapped[str | None] = mapped_column(String(100))
    decided_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))  # IT ตัดสินแทน
    decided_at: Mapped[datetime | None] = mapped_column(DateTime)
    reminded_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime)

    ticket = relationship("Ticket")
