"""เก็บชื่อ-นามสกุลที่ผู้แจ้งบอกบอทเอง (line_users.self_name)

เดิมชื่อที่เก็บได้ตอน intake ถูกเขียนลง display_name ซึ่ง (1) โดน LINE profile ทับทุกข้อความ
และ (2) แยกไม่ออกจาก "ชื่อเล่นใน LINE" → บอทนึกว่ารู้ชื่อจริงแล้วเลยไม่ถาม และชื่อเล่น
ไหลไปถึง dropdown ผู้แจ้งของ itamtv จนเปิดเคสไม่ผ่าน

Revision ID: 0018_line_user_self_name
Revises: 0017_ticket_level
Create Date: 2026-08-11
"""
import sqlalchemy as sa
from alembic import op

revision = "0018_line_user_self_name"
down_revision = "0017_ticket_level"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("line_users", sa.Column("self_name", sa.String(100), nullable=True))


def downgrade() -> None:
    op.drop_column("line_users", "self_name")
