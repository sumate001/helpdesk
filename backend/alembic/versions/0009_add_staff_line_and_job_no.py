"""add users.line_user_id (map ช่างเข้ากับ LINE) + tickets.itamtv_job_no

- users.line_user_id: LINE userId ของ IT staff — ใช้ push แจ้งเตือน + ยืนยันตัวตน
  ตอนกดปุ่มปิดเคสจาก LINE
- tickets.itamtv_job_no: เลขเคสในระบบ itamtv ที่เปิดคู่ขนานไว้ — เก็บไว้เพื่อไปสั่ง
  ปิด/อัปเดตสถานะทีหลัง

Revision ID: 0009_staff_line_and_job_no
Revises: 0008_conversation_followup
Create Date: 2026-07-16
"""
import sqlalchemy as sa
from alembic import op

revision = "0009_staff_line_and_job_no"
down_revision = "0008_conversation_followup"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("line_user_id", sa.String(100), nullable=True))
    op.create_unique_constraint("uq_users_line_user_id", "users", ["line_user_id"])
    op.add_column("tickets", sa.Column("itamtv_job_no", sa.String(30), nullable=True))


def downgrade() -> None:
    op.drop_column("tickets", "itamtv_job_no")
    op.drop_constraint("uq_users_line_user_id", "users", type_="unique")
    op.drop_column("users", "line_user_id")
