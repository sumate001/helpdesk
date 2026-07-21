"""add tickets.staff_progress_ping_at

บอทตามถามความคืบหน้าจากช่างที่รับงาน (in_progress) ทาง LINE ทุก STAFF_PROGRESS_MINUTES
นาที — คอลัมน์นี้เก็บเวลา ping ล่าสุดเพื่อเว้นจังหวะไม่ให้ถามถี่เกินไป

Revision ID: 0012_staff_progress_ping
Revises: 0011_line_user_employee
Create Date: 2026-07-21
"""
import sqlalchemy as sa
from alembic import op

revision = "0012_staff_progress_ping"
down_revision = "0011_line_user_employee"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tickets", sa.Column("staff_progress_ping_at", sa.DateTime(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("tickets", "staff_progress_ping_at")
