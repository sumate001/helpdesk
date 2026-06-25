"""add bot_messages table

Revision ID: 0002_bot_messages
Revises: 0001_initial
Create Date: 2026-06-25

เก็บ message id ที่บอทส่ง เพื่อรู้ว่า user quote-reply ข้อความบอทในกลุ่มหรือไม่.
"""
import sqlalchemy as sa
from alembic import op

revision = "0002_bot_messages"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "bot_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("line_message_id", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_bot_messages_line_message_id",
        "bot_messages",
        ["line_message_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_bot_messages_line_message_id", table_name="bot_messages")
    op.drop_table("bot_messages")
