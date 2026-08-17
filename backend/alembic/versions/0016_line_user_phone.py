"""เก็บเบอร์ติดต่อของผู้แจ้ง (line_users.phone)

itamtv บังคับช่องเบอร์โทร แต่ Employee DB ไม่มีเบอร์ของพนักงานหลายคน → เดิมส่ง "-"
ทำให้ช่างโทรกลับไม่ได้. เก็บเบอร์ที่ผู้แจ้งบอกบอทไว้ใช้ซ้ำ (ถามครั้งเดียว)

Revision ID: 0016_line_user_phone
Revises: 0015_approver_accept
Create Date: 2026-07-22
"""
import sqlalchemy as sa
from alembic import op

revision = "0016_line_user_phone"
down_revision = "0015_approver_accept"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("line_users", sa.Column("phone", sa.String(30), nullable=True))


def downgrade() -> None:
    op.drop_column("line_users", "phone")
