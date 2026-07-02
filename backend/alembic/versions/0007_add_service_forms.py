"""add service_forms + link kb_chunks.form_id

Revision ID: 0007_service_forms
Revises: 0006_app_settings
Create Date: 2026-06-29

แบบฟอร์มขอใช้บริการแบบ dynamic (กรอกผ่าน LIFF) + ผูกกับ KB chunk เพื่อให้บอท
ยื่นปุ่มฟอร์มอัตโนมัติเมื่อ RAG เจอความรู้ที่เกี่ยวข้อง. seed ฟอร์ม VPN ตั้งต้นไว้ด้วย.
"""
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op

revision = "0007_service_forms"
down_revision = "0006_app_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "service_forms",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("category", sa.String(length=50), nullable=True),
        sa.Column("priority", sa.String(length=20), nullable=False, server_default="low"),
        sa.Column("fields", sa.JSON(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("slug", name="uq_service_forms_slug"),
    )
    op.add_column("kb_chunks", sa.Column("form_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_kb_chunks_form_id",
        "kb_chunks",
        "service_forms",
        ["form_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # seed ฟอร์ม VPN ตั้งต้น (slug=vpn) ให้เริ่มใช้ได้ทันที
    now = datetime.now(timezone.utc)
    forms = sa.table(
        "service_forms",
        sa.column("name", sa.String),
        sa.column("slug", sa.String),
        sa.column("description", sa.Text),
        sa.column("category", sa.String),
        sa.column("priority", sa.String),
        sa.column("fields", sa.JSON),
        sa.column("is_active", sa.Boolean),
        sa.column("created_at", sa.DateTime),
        sa.column("updated_at", sa.DateTime),
    )
    op.bulk_insert(
        forms,
        [
            {
                "name": "ขอใช้งาน VPN",
                "slug": "vpn",
                "description": "กรอกข้อมูลเพื่อส่งคำขอใช้ VPN ให้ทีม IT พิจารณา",
                "category": "service_request",
                "priority": "low",
                "fields": [
                    {"key": "full_name", "label": "ชื่อ-นามสกุล", "type": "text", "required": True},
                    {"key": "building", "label": "อาคาร", "type": "text", "required": True},
                    {"key": "floor", "label": "ชั้น", "type": "text", "required": True},
                    {
                        "key": "duration",
                        "label": "ระยะเวลาที่ขอใช้",
                        "type": "select",
                        "required": True,
                        "options": ["ชั่วคราว", "ถาวร"],
                    },
                    {
                        "key": "reason",
                        "label": "เหตุผล / ลักษณะการใช้งาน",
                        "type": "textarea",
                        "required": True,
                    },
                ],
                "is_active": True,
                "created_at": now,
                "updated_at": now,
            }
        ],
    )


def downgrade() -> None:
    op.drop_constraint("fk_kb_chunks_form_id", "kb_chunks", type_="foreignkey")
    op.drop_column("kb_chunks", "form_id")
    op.drop_table("service_forms")
