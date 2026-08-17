"""approval workflow: department_approvers + approval_requests + form approval rules

ระบบขออนุมัติสำหรับคำขอใช้ทรัพยากร (WiFi/VPN/อุปกรณ์) — เงื่อนไข "ต้องอนุมัติไหม/ใครอนุมัติ"
ย้ายจากข้อความใน KB มาเป็นโครงสร้างบน service_forms ที่โค้ดบังคับได้จริง

Revision ID: 0014_approvals
Revises: 0013_ticket_reporter
Create Date: 2026-07-22
"""
import sqlalchemy as sa
from alembic import op

revision = "0014_approvals"
down_revision = "0013_ticket_reporter"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "department_approvers",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("department", sa.String(100), nullable=False, unique=True, index=True),
        sa.Column("approver_emp_code", sa.String(20), nullable=False),
        sa.Column("approver_name", sa.String(100)),
        sa.Column("approver_email", sa.String(100)),
        sa.Column("backup_emp_code", sa.String(20)),
        sa.Column("backup_name", sa.String(100)),
        sa.Column("is_confirmed", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("note", sa.Text),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "approval_requests",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("ticket_id", sa.Integer,
                  sa.ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("step", sa.Integer, nullable=False, server_default="1"),
        sa.Column("approver_emp_code", sa.String(20)),
        sa.Column("approver_name", sa.String(100)),
        sa.Column("approver_email", sa.String(100)),
        sa.Column("approver_line_user_id", sa.String(100), index=True),
        sa.Column("approver_from_requester", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending", index=True),
        sa.Column("channel", sa.String(10), nullable=False, server_default="line"),
        sa.Column("comment", sa.Text),
        sa.Column("awaiting_reason", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("token_hash", sa.String(64), index=True),
        sa.Column("expires_at", sa.DateTime),
        sa.Column("decided_by_line_user_id", sa.String(100)),
        sa.Column("decided_by_user_id", sa.Integer, sa.ForeignKey("users.id")),
        sa.Column("decided_at", sa.DateTime),
        sa.Column("reminded_at", sa.DateTime),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )

    # กฎอนุมัติผูกกับ "ฟอร์ม" (โครงสร้าง) ไม่ใช่ข้อความใน KB
    op.add_column("service_forms", sa.Column(
        "requires_approval", sa.Boolean, nullable=False, server_default=sa.false()))
    op.add_column("service_forms", sa.Column(
        "approver_rule", sa.String(20), nullable=False, server_default="supervisor"))
    # ตำแหน่งที่อนุมัติตัวเองได้ เช่น ["ผู้จัดการ", "ผู้อำนวยการ"] (match แบบ contains)
    op.add_column("service_forms", sa.Column("self_approve_positions", sa.JSON))
    # ผู้อนุมัติตายตัว ใช้เมื่อ approver_rule = "fixed"
    op.add_column("service_forms", sa.Column("fixed_approver_emp_code", sa.String(20)))


def downgrade() -> None:
    op.drop_column("service_forms", "fixed_approver_emp_code")
    op.drop_column("service_forms", "self_approve_positions")
    op.drop_column("service_forms", "approver_rule")
    op.drop_column("service_forms", "requires_approval")
    op.drop_table("approval_requests")
    op.drop_table("department_approvers")
