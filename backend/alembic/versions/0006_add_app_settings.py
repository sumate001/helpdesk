"""add app_settings for runtime AI config

Revision ID: 0006_app_settings
Revises: 0005_kb_chunks
Create Date: 2026-06-28

runtime settings ที่แก้ได้จาก UI (override .env) — model, RAG params ฯลฯ
เก็บแบบ key-value, override ค่า default ที่ตั้งไว้ใน .env
"""
import sqlalchemy as sa
from alembic import op

revision = "0006_app_settings"
down_revision = "0005_kb_chunks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "app_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("key", sa.String(length=100), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("key", name="uq_app_settings_key"),
    )


def downgrade() -> None:
    op.drop_table("app_settings")
