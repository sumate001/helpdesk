"""ผู้อนุมัติต้องกด "ยอมรับ" บทบาทก่อน + เก็บว่าใครแจ้งเข้ามา

ถูกตั้งเป็นผู้อนุมัติแล้วไม่รู้ตัว = คำขอไปจ่ออยู่ที่คนที่ไม่รู้ว่าตัวเองต้องกด
จึงแจ้งทาง LINE พร้อมปุ่มยอมรับ/ปฏิเสธตั้งแต่ตอนถูกเพิ่ม

Revision ID: 0015_approver_accept
Revises: 0014_approvals
Create Date: 2026-07-22
"""
import sqlalchemy as sa
from alembic import op

revision = "0015_approver_accept"
down_revision = "0014_approvals"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("department_approvers", sa.Column("accepted", sa.Boolean(), nullable=True))
    op.add_column("department_approvers", sa.Column("accepted_at", sa.DateTime(), nullable=True))
    op.add_column("department_approvers", sa.Column("notified_at", sa.DateTime(), nullable=True))
    op.add_column("department_approvers",
                  sa.Column("proposed_by_line_user_id", sa.String(100), nullable=True))
    # แถวที่มีอยู่ก่อน (ตั้งมือโดย IT) ถือว่ายังไม่ได้กดยอมรับ → จะถูกแจ้งเมื่อแก้/ส่งซ้ำ
    op.execute("UPDATE department_approvers SET accepted = false WHERE accepted IS NULL")


def downgrade() -> None:
    op.drop_column("department_approvers", "proposed_by_line_user_id")
    op.drop_column("department_approvers", "notified_at")
    op.drop_column("department_approvers", "accepted_at")
    op.drop_column("department_approvers", "accepted")
