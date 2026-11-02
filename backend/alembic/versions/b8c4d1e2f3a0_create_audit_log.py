"""create audit log table

Revision ID: b8c4d1e2f3a0
Revises: a3f1c2d4e5b6
Create Date: 2026-11-02 21:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b8c4d1e2f3a0"
down_revision: str | None = "a3f1c2d4e5b6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "sys_audit_log",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("request_id", sa.String(length=64), nullable=True, comment="请求 ID"),
        sa.Column("actor_id", sa.Integer(), nullable=True, comment="操作人"),
        sa.Column("actor_account", sa.String(length=20), nullable=True, comment="操作人账号"),
        sa.Column("action", sa.String(length=40), nullable=False, comment="动作，如 user.create"),
        sa.Column("resource_type", sa.String(length=30), nullable=False, comment="资源类型"),
        sa.Column("resource_id", sa.String(length=40), nullable=True, comment="资源标识"),
        sa.Column("summary", sa.String(length=300), nullable=False, comment="摘要"),
        sa.Column("ip", sa.String(length=64), nullable=True, comment="来源 IP"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
            comment="发生时间",
        ),
        sa.ForeignKeyConstraint(["actor_id"], ["sys_user.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sys_audit_log_request_id", "sys_audit_log", ["request_id"])
    op.create_index("ix_sys_audit_log_action", "sys_audit_log", ["action"])
    op.create_index("ix_sys_audit_log_created_at", "sys_audit_log", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_sys_audit_log_created_at", table_name="sys_audit_log")
    op.drop_index("ix_sys_audit_log_action", table_name="sys_audit_log")
    op.drop_index("ix_sys_audit_log_request_id", table_name="sys_audit_log")
    op.drop_table("sys_audit_log")
