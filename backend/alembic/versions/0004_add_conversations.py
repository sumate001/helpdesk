"""add conversations, drop group_sessions

Revision ID: 0004_conversations
Revises: 0003_group_sessions
Create Date: 2026-06-25

multi-turn intake แทนที่ group_sessions — เก็บ transcript + รูปที่รอผูก ticket
ใช้ทั้งแชต 1-1 และกลุ่ม. group_sessions ถูกแทนที่ทั้งหมดจึง drop ทิ้ง.
"""
import sqlalchemy as sa
from alembic import op

revision = "0004_conversations"
down_revision = "0003_group_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "conversations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("channel", sa.String(length=10), nullable=False),
        sa.Column("source_id", sa.String(length=100), nullable=True),
        sa.Column("line_user_id", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("transcript", sa.Text(), nullable=False),
        sa.Column("pending_images", sa.Text(), nullable=False),
        sa.Column("ticket_id", sa.Integer(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["ticket_id"], ["tickets.id"]),
    )
    op.create_index(
        "ix_conversations_line_user_id", "conversations", ["line_user_id"]
    )
    op.drop_table("group_sessions")


def downgrade() -> None:
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
    op.drop_index("ix_conversations_line_user_id", table_name="conversations")
    op.drop_table("conversations")
