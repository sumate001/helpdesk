"""add users.itamtv_token + users.itamtv_emp_code — สิทธิ์ปิดเคสในระบบ itamtv

- itamtv_token: token ส่วนตัวของช่างใน itamtv (ปลดล็อกช่องสถานะ/ผู้รับผิดชอบ)
- itamtv_emp_code: emp code ของช่างใน itamtv (ddlpeople/ddlforemp) — ใช้ระบุผู้รับผิดชอบ
  ตอนปิดงาน

Revision ID: 0010_staff_itamtv_creds
Revises: 0009_staff_line_and_job_no
Create Date: 2026-07-16
"""
import sqlalchemy as sa
from alembic import op

revision = "0010_staff_itamtv_creds"
down_revision = "0009_staff_line_and_job_no"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("itamtv_token", sa.String(100), nullable=True))
    op.add_column("users", sa.Column("itamtv_emp_code", sa.String(20), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "itamtv_emp_code")
    op.drop_column("users", "itamtv_token")
