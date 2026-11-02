"""系统管理模型：系部、用户、角色、权限、数据字典。

与 ODS_* 标准表区分，统一使用 sys_ 前缀。
"""

from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class DepartmentKind(StrEnum):
    TEACHING = "teaching"  # 教学系部
    FUNCTIONAL = "functional"  # 职能部门
    OTHER = "other"


class UserStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"


class DataScope(StrEnum):
    SELF = "self"  # 仅本人
    DEPARTMENT = "department"  # 本部门
    ALL = "all"  # 全校


DATA_SCOPE_RANK: dict[str, int] = {
    DataScope.SELF: 1,
    DataScope.DEPARTMENT: 2,
    DataScope.ALL: 3,
}


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), comment="创建时间"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        comment="更新时间",
    )


sys_user_role = Table(
    "sys_user_role",
    Base.metadata,
    Column("user_id", ForeignKey("sys_user.id", ondelete="CASCADE"), primary_key=True),
    Column("role_id", ForeignKey("sys_role.id", ondelete="CASCADE"), primary_key=True),
)

sys_role_permission = Table(
    "sys_role_permission",
    Base.metadata,
    Column("role_id", ForeignKey("sys_role.id", ondelete="CASCADE"), primary_key=True),
    Column(
        "permission_id",
        ForeignKey("sys_permission.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class Department(TimestampMixin, Base):
    __tablename__ = "sys_department"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(20), unique=True, comment="部门编码")
    name: Mapped[str] = mapped_column(String(60), unique=True, comment="部门规范名称（全称）")
    short_name: Mapped[str | None] = mapped_column(String(30), comment="简称")
    kind: Mapped[str] = mapped_column(
        String(20), default=DepartmentKind.TEACHING, comment="类型：teaching/functional/other"
    )
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("sys_department.id", ondelete="SET NULL"), comment="上级部门"
    )
    leader: Mapped[str | None] = mapped_column(String(36), comment="负责人")
    data_manager: Mapped[str | None] = mapped_column(String(36), comment="数据管理员")
    phone: Mapped[str | None] = mapped_column(String(30), comment="联系电话")
    sort_order: Mapped[int] = mapped_column(Integer, default=0, comment="排序")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否启用")
    remark: Mapped[str | None] = mapped_column(Text, comment="备注")

    users: Mapped[list["User"]] = relationship(back_populates="department")


class Permission(Base):
    __tablename__ = "sys_permission"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(60), unique=True, comment="权限编码，如 user:write")
    name: Mapped[str] = mapped_column(String(60), comment="权限名称")
    module: Mapped[str] = mapped_column(String(30), comment="所属模块")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    roles: Mapped[list["Role"]] = relationship(
        secondary=sys_role_permission, back_populates="permissions"
    )


class Role(TimestampMixin, Base):
    __tablename__ = "sys_role"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(30), unique=True, comment="角色编码")
    name: Mapped[str] = mapped_column(String(30), unique=True, comment="角色名称")
    description: Mapped[str | None] = mapped_column(String(200), comment="说明")
    data_scope: Mapped[str] = mapped_column(
        String(20), default=DataScope.SELF, comment="数据范围：self/department/all"
    )
    is_builtin: Mapped[bool] = mapped_column(Boolean, default=False, comment="内置角色不可删除")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    permissions: Mapped[list[Permission]] = relationship(
        secondary=sys_role_permission, back_populates="roles", lazy="selectin"
    )
    users: Mapped[list["User"]] = relationship(secondary=sys_user_role, back_populates="roles")


class User(TimestampMixin, Base):
    __tablename__ = "sys_user"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account: Mapped[str] = mapped_column(String(20), unique=True, comment="登录账号（教工号）")
    name: Mapped[str] = mapped_column(String(36), comment="姓名")
    password_hash: Mapped[str] = mapped_column(String(255), comment="密码哈希")
    department_id: Mapped[int | None] = mapped_column(
        ForeignKey("sys_department.id", ondelete="SET NULL"), comment="所属部门"
    )
    post: Mapped[str | None] = mapped_column(String(60), comment="岗位 / 职务")
    phone: Mapped[str | None] = mapped_column(String(30), comment="手机号")
    email: Mapped[str | None] = mapped_column(String(120), comment="邮箱")
    status: Mapped[str] = mapped_column(
        String(20), default=UserStatus.ACTIVE, comment="状态：active/disabled"
    )
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False, comment="超级管理员")
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), comment="最近登录时间"
    )
    remark: Mapped[str | None] = mapped_column(Text)

    department: Mapped[Department | None] = relationship(back_populates="users", lazy="selectin")
    roles: Mapped[list[Role]] = relationship(
        secondary=sys_user_role, back_populates="users", lazy="selectin"
    )

    @property
    def permission_codes(self) -> set[str]:
        return {perm.code for role in self.roles for perm in role.permissions}

    @property
    def data_scope(self) -> str:
        if self.is_superuser:
            return DataScope.ALL
        best = DataScope.SELF
        for role in self.roles:
            if DATA_SCOPE_RANK.get(role.data_scope, 0) > DATA_SCOPE_RANK[best]:
                best = DataScope(role.data_scope)
        return best


class DictType(Base):
    __tablename__ = "sys_dict_type"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(10), unique=True, comment="字典编号，如 D01")
    name: Mapped[str] = mapped_column(String(60), comment="字典名称")
    ref_standard: Mapped[str | None] = mapped_column(String(60), comment="引用标准代码集")
    applies_to: Mapped[str | None] = mapped_column(String(300), comment="适用标准表")
    remark: Mapped[str | None] = mapped_column(Text, comment="说明")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    items: Mapped[list["DictItem"]] = relationship(
        back_populates="type", cascade="all, delete-orphan", order_by="DictItem.sort_order"
    )


class DictItem(Base):
    __tablename__ = "sys_dict_item"
    __table_args__ = (UniqueConstraint("type_id", "label", name="uq_sys_dict_item_type_label"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    type_id: Mapped[int] = mapped_column(
        ForeignKey("sys_dict_type.id", ondelete="CASCADE"), index=True
    )
    value: Mapped[str | None] = mapped_column(
        String(20), comment="代码值；校本字典无国标代码时为空"
    )
    label: Mapped[str] = mapped_column(String(100), comment="代码名称 / 值")
    remark: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    type: Mapped[DictType] = relationship(back_populates="items")


class AuditLog(Base):
    __tablename__ = "sys_audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_id: Mapped[str | None] = mapped_column(String(64), index=True, comment="请求 ID")
    actor_id: Mapped[int | None] = mapped_column(
        ForeignKey("sys_user.id", ondelete="SET NULL"), comment="操作人"
    )
    actor_account: Mapped[str | None] = mapped_column(String(20), comment="操作人账号")
    action: Mapped[str] = mapped_column(String(40), index=True, comment="动作，如 user.create")
    resource_type: Mapped[str] = mapped_column(String(30), comment="资源类型")
    resource_id: Mapped[str | None] = mapped_column(String(40), comment="资源标识")
    summary: Mapped[str] = mapped_column(String(300), comment="摘要")
    ip: Mapped[str | None] = mapped_column(String(64), comment="来源 IP")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True, comment="发生时间"
    )
