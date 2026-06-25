"""add group_sessions table

Revision ID: 0003_group_sessions
Revises: 0002_bot_messages
Create Date: 2026-06-25

session ชั่วคราวต่อ (กลุ่ม, ผู้ใช้) — ผูกรูปที่ส่งตามมาในกลุ่มเข้ากับ ticket.
"""
import sqlalchemy as sa
from alembic import op

revision = "0003_group_sessions"
down_revision = "0002_bot_messages"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "group_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_id", sa.String(length=100), nullable=False),
        sa.Column("line_user_id", sa.String(length=100), nullable=False),
        sa.Column("ticket_id", sa.Integer(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["ticket_id"], ["tickets.id"]),
        sa.UniqueConstraint("source_id", "line_user_id"),
    )


def downgrade() -> None:
    op.drop_table("group_sessions")
