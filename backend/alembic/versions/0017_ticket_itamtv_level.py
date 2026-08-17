"""tickets.itamtv_level — ระดับ SLA (Level 1-4) ที่ AI ประเมินตอนเปิดเคส

itamtv มี ddllv (Level 1-6) เป็นกรอบเวลา SLA แต่ตั้งได้เฉพาะหน้า display (ตอนช่างรับงาน)
จึงให้ AI ประเมินตั้งแต่เปิดเคส เก็บไว้ แล้วส่งเข้า itamtv ตอน mirror/รับงาน

Revision ID: 0017_ticket_level
Revises: 0016_line_user_phone
Create Date: 2026-07-23
"""
import sqlalchemy as sa
from alembic import op

revision = "0017_ticket_level"
down_revision = "0016_line_user_phone"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tickets", sa.Column("itamtv_level", sa.String(1), nullable=True))


def downgrade() -> None:
    op.drop_column("tickets", "itamtv_level")
