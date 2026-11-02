"""create system tables: department, user, role, permission, dictionary

Revision ID: a3f1c2d4e5b6
Revises: 7279be8ab696
Create Date: 2026-11-02 19:05:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a3f1c2d4e5b6"
down_revision: str | None = "7279be8ab696"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "sys_department",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(length=20), nullable=False, comment="部门编码"),
        sa.Column("name", sa.String(length=60), nullable=False, comment="部门规范名称（全称）"),
        sa.Column("short_name", sa.String(length=30), nullable=True, comment="简称"),
        sa.Column(
            "kind",
            sa.String(length=20),
            nullable=False,
            comment="类型：teaching/functional/other",
        ),
        sa.Column("parent_id", sa.Integer(), nullable=True, comment="上级部门"),
        sa.Column("leader", sa.String(length=36), nullable=True, comment="负责人"),
        sa.Column("data_manager", sa.String(length=36), nullable=True, comment="数据管理员"),
        sa.Column("phone", sa.String(length=30), nullable=True, comment="联系电话"),
        sa.Column("sort_order", sa.Integer(), nullable=False, comment="排序"),
        sa.Column("is_active", sa.Boolean(), nullable=False, comment="是否启用"),
        sa.Column("remark", sa.Text(), nullable=True, comment="备注"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
            comment="创建时间",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
            comment="更新时间",
        ),
        sa.ForeignKeyConstraint(["parent_id"], ["sys_department.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "sys_permission",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(length=60), nullable=False, comment="权限编码，如 user:write"),
        sa.Column("name", sa.String(length=60), nullable=False, comment="权限名称"),
        sa.Column("module", sa.String(length=30), nullable=False, comment="所属模块"),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_table(
        "sys_role",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(length=30), nullable=False, comment="角色编码"),
        sa.Column("name", sa.String(length=30), nullable=False, comment="角色名称"),
        sa.Column("description", sa.String(length=200), nullable=True, comment="说明"),
        sa.Column(
            "data_scope",
            sa.String(length=20),
            nullable=False,
            comment="数据范围：self/department/all",
        ),
        sa.Column("is_builtin", sa.Boolean(), nullable=False, comment="内置角色不可删除"),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
            comment="创建时间",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
            comment="更新时间",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "sys_dict_type",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(length=10), nullable=False, comment="字典编号，如 D01"),
        sa.Column("name", sa.String(length=60), nullable=False, comment="字典名称"),
        sa.Column("ref_standard", sa.String(length=60), nullable=True, comment="引用标准代码集"),
        sa.Column("applies_to", sa.String(length=300), nullable=True, comment="适用标准表"),
        sa.Column("remark", sa.Text(), nullable=True, comment="说明"),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_table(
        "sys_user",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("account", sa.String(length=20), nullable=False, comment="登录账号（教工号）"),
        sa.Column("name", sa.String(length=36), nullable=False, comment="姓名"),
        sa.Column("password_hash", sa.String(length=255), nullable=False, comment="密码哈希"),
        sa.Column("department_id", sa.Integer(), nullable=True, comment="所属部门"),
        sa.Column("post", sa.String(length=60), nullable=True, comment="岗位 / 职务"),
        sa.Column("phone", sa.String(length=30), nullable=True, comment="手机号"),
        sa.Column("email", sa.String(length=120), nullable=True, comment="邮箱"),
        sa.Column("status", sa.String(length=20), nullable=False, comment="状态：active/disabled"),
        sa.Column("is_superuser", sa.Boolean(), nullable=False, comment="超级管理员"),
        sa.Column(
            "last_login_at", sa.DateTime(timezone=True), nullable=True, comment="最近登录时间"
        ),
        sa.Column("remark", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
            comment="创建时间",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
            comment="更新时间",
        ),
        sa.ForeignKeyConstraint(["department_id"], ["sys_department.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("account"),
    )
    op.create_table(
        "sys_dict_item",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("type_id", sa.Integer(), nullable=False),
        sa.Column(
            "value",
            sa.String(length=20),
            nullable=True,
            comment="代码值；校本字典无国标代码时为空",
        ),
        sa.Column("label", sa.String(length=100), nullable=False, comment="代码名称 / 值"),
        sa.Column("remark", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["type_id"], ["sys_dict_type.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("type_id", "label", name="uq_sys_dict_item_type_label"),
    )
    op.create_index("ix_sys_dict_item_type_id", "sys_dict_item", ["type_id"])
    op.create_table(
        "sys_role_permission",
        sa.Column("role_id", sa.Integer(), nullable=False),
        sa.Column("permission_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["permission_id"], ["sys_permission.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["role_id"], ["sys_role.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("role_id", "permission_id"),
    )
    op.create_table(
        "sys_user_role",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("role_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["role_id"], ["sys_role.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["sys_user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "role_id"),
    )


def downgrade() -> None:
    op.drop_table("sys_user_role")
    op.drop_table("sys_role_permission")
    op.drop_index("ix_sys_dict_item_type_id", table_name="sys_dict_item")
    op.drop_table("sys_dict_item")
    op.drop_table("sys_user")
    op.drop_table("sys_dict_type")
    op.drop_table("sys_role")
    op.drop_table("sys_permission")
    op.drop_table("sys_department")
