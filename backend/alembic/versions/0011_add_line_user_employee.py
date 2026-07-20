"""ผูก line_users เข้ากับ Amarin Employee DB (exact lookup — ไม่ cache)

- employee_id: id ของพนักงานใน Employee DB (ใช้ยิง /api/employees/{id}/assets ตรง)
- emp_code / emp_email: key ที่ใช้ lookup — เก็บไว้ยิง /api/employees/lookup สดทุกครั้ง
- emp_name: ชื่อจริงจาก Employee DB (display_name โดน LINE profile เขียนทับได้ตลอด)

Revision ID: 0011_line_user_employee
Revises: 0010_staff_itamtv_creds
Create Date: 2026-07-20
"""
import sqlalchemy as sa
from alembic import op

revision = "0011_line_user_employee"
down_revision = "0010_staff_itamtv_creds"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("line_users", sa.Column("employee_id", sa.Integer(), nullable=True))
    op.add_column("line_users", sa.Column("emp_code", sa.String(20), nullable=True))
    op.add_column("line_users", sa.Column("emp_email", sa.String(100), nullable=True))
    op.add_column("line_users", sa.Column("emp_name", sa.String(100), nullable=True))


def downgrade() -> None:
    op.drop_column("line_users", "emp_name")
    op.drop_column("line_users", "emp_email")
    op.drop_column("line_users", "emp_code")
    op.drop_column("line_users", "employee_id")
