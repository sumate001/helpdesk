"""add tickets.reporter_name + reporter_detail (phone-in cases)

เคสที่ staff เปิดแทนทางโทรศัพท์ไม่มี line_user — เก็บชื่อ/รายละเอียดผู้แจ้งไว้ตรงนี้
เพื่อโชว์ในรายการเคส/แจ้งกลุ่ม/get_ticket

Revision ID: 0013_ticket_reporter
Revises: 0012_staff_progress_ping
Create Date: 2026-07-21
"""
import sqlalchemy as sa
from alembic import op

revision = "0013_ticket_reporter"
down_revision = "0012_staff_progress_ping"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tickets", sa.Column("reporter_name", sa.String(100), nullable=True))
    op.add_column("tickets", sa.Column("reporter_detail", sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column("tickets", "reporter_detail")
    op.drop_column("tickets", "reporter_name")
