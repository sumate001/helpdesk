"""add kb_chunks for RAG (pgvector)

Revision ID: 0005_kb_chunks
Revises: 0004_conversations
Create Date: 2026-06-25

knowledge base สำหรับ RAG — ความรู้ระบบ/นโยบาย IT ภายในบริษัท เก็บ embedding ด้วย pgvector
ต้องใช้ Postgres image ที่มี extension vector (เช่น pgvector/pgvector:pg15)
"""
import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

from app.core.config import settings

revision = "0005_kb_chunks"
down_revision = "0004_conversations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "kb_chunks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("category", sa.String(length=50), nullable=True),
        sa.Column("source", sa.String(length=255), nullable=True),
        sa.Column("embedding", Vector(settings.EMBED_DIM), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    # HNSW index สำหรับ cosine distance — ค้น semantic เร็ว
    op.execute(
        "CREATE INDEX ix_kb_chunks_embedding ON kb_chunks "
        "USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.drop_index("ix_kb_chunks_embedding", table_name="kb_chunks")
    op.drop_table("kb_chunks")
