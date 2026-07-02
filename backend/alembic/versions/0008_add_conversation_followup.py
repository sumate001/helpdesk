"""add conversations.followup_sent_at — follow-up flow เกาะกับบทสนทนา intake

Revision ID: 0008_conversation_followup
Revises: 0007_service_forms
Create Date: 2026-07-02
"""
import sqlalchemy as sa
from alembic import op

revision = "0008_conversation_followup"
down_revision = "0007_service_forms"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "conversations",
        sa.Column("followup_sent_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("conversations", "followup_sent_at")
