from datetime import datetime

from pydantic import BaseModel, Field

from app.models.system import DataScope, DepartmentKind, UserStatus
from app.schemas.common import ORMModel

# ---------- 部门 ----------


class DepartmentBase(BaseModel):
    code: str = Field(min_length=1, max_length=20)
    name: str = Field(min_length=1, max_length=60)
    short_name: str | None = Field(default=None, max_length=30)
    kind: DepartmentKind = DepartmentKind.TEACHING
    parent_id: int | None = None
    leader: str | None = Field(default=None, max_length=36)
    data_manager: str | None = Field(default=None, max_length=36)
    phone: str | None = Field(default=None, max_length=30)
    sort_order: int = 0
    is_active: bool = True
    remark: str | None = None


class DepartmentCreate(DepartmentBase):
    pass


class DepartmentUpdate(BaseModel):
    code: str | None = Field(default=None, min_length=1, max_length=20)
    name: str | None = Field(default=None, min_length=1, max_length=60)
    short_name: str | None = Field(default=None, max_length=30)
    kind: DepartmentKind | None = None
    parent_id: int | None = None
    leader: str | None = Field(default=None, max_length=36)
    data_manager: str | None = Field(default=None, max_length=36)
    phone: str | None = Field(default=None, max_length=30)
    sort_order: int | None = None
    is_active: bool | None = None
    remark: str | None = None


class DepartmentRead(ORMModel):
    id: int
    code: str
    name: str
    short_name: str | None
    kind: str
    parent_id: int | None
    leader: str | None
    data_manager: str | None
    phone: str | None
    sort_order: int
    is_active: bool
    remark: str | None
    user_count: int = 0
    created_at: datetime
    updated_at: datetime


# ---------- 权限 / 角色 ----------


class PermissionRead(ORMModel):
    id: int
    code: str
    name: str
    module: str
    sort_order: int


class RoleBase(BaseModel):
    code: str = Field(min_length=1, max_length=30, pattern=r"^[a-z][a-z0-9_-]*$")
    name: str = Field(min_length=1, max_length=30)
    description: str | None = Field(default=None, max_length=200)
    data_scope: DataScope = DataScope.SELF
    permission_codes: list[str] = Field(default_factory=list)
    sort_order: int = 0


class RoleCreate(RoleBase):
    pass


class RoleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=30)
    description: str | None = Field(default=None, max_length=200)
    data_scope: DataScope | None = None
    permission_codes: list[str] | None = None
    sort_order: int | None = None


class RoleRead(ORMModel):
    id: int
    code: str
    name: str
    description: str | None
    data_scope: str
    is_builtin: bool
    sort_order: int
    permission_codes: list[str] = Field(default_factory=list)
    user_count: int = 0
    created_at: datetime
    updated_at: datetime


# ---------- 用户 ----------


class UserBase(BaseModel):
    account: str = Field(min_length=1, max_length=20)
    name: str = Field(min_length=1, max_length=36)
    department_id: int | None = None
    post: str | None = Field(default=None, max_length=60)
    phone: str | None = Field(default=None, max_length=30)
    email: str | None = Field(default=None, max_length=120)
    status: UserStatus = UserStatus.ACTIVE
    role_codes: list[str] = Field(default_factory=list)
    remark: str | None = None


class UserCreate(UserBase):
    password: str = Field(min_length=6, max_length=72)


class UserUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=36)
    department_id: int | None = None
    post: str | None = Field(default=None, max_length=60)
    phone: str | None = Field(default=None, max_length=30)
    email: str | None = Field(default=None, max_length=120)
    status: UserStatus | None = None
    role_codes: list[str] | None = None
    remark: str | None = None


class UserStatusUpdate(BaseModel):
    status: UserStatus


class PasswordReset(BaseModel):
    password: str = Field(min_length=6, max_length=72)


class PasswordChange(BaseModel):
    old_password: str
    new_password: str = Field(min_length=6, max_length=72)


class UserRead(ORMModel):
    id: int
    account: str
    name: str
    department_id: int | None
    department_name: str | None = None
    post: str | None
    phone: str | None
    email: str | None
    status: str
    is_superuser: bool
    role_codes: list[str] = Field(default_factory=list)
    role_names: list[str] = Field(default_factory=list)
    last_login_at: datetime | None
    created_at: datetime
    updated_at: datetime


class CurrentUser(UserRead):
    permissions: list[str] = Field(default_factory=list)
    data_scope: str


# ---------- 认证 ----------


class LoginRequest(BaseModel):
    account: str = Field(min_length=1, max_length=20)
    password: str = Field(min_length=1, max_length=72)


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: CurrentUser


class AuditLogRead(ORMModel):
    id: int
    request_id: str | None
    actor_id: int | None
    actor_account: str | None
    action: str
    resource_type: str
    resource_id: str | None
    summary: str
    ip: str | None
    created_at: datetime


# ---------- 字典 ----------


class DictItemRead(ORMModel):
    id: int
    value: str | None
    label: str
    remark: str | None
    sort_order: int
    is_active: bool


class DictTypeRead(ORMModel):
    id: int
    code: str
    name: str
    ref_standard: str | None
    applies_to: str | None
    remark: str | None
    is_active: bool
    sort_order: int
    item_count: int = 0


class DictTypeWithItems(DictTypeRead):
    items: list[DictItemRead] = Field(default_factory=list)


class DictItemCreate(BaseModel):
    value: str | None = Field(default=None, max_length=20)
    label: str = Field(min_length=1, max_length=100)
    remark: str | None = None
    sort_order: int = 0
    is_active: bool = True


class DictItemUpdate(BaseModel):
    value: str | None = Field(default=None, max_length=20)
    label: str | None = Field(default=None, min_length=1, max_length=100)
    remark: str | None = None
    sort_order: int | None = None
    is_active: bool | None = None


class DictTypeCreate(BaseModel):
    code: str = Field(min_length=1, max_length=10, pattern=r"^[A-Za-z][A-Za-z0-9_-]*$")
    name: str = Field(min_length=1, max_length=60)
    ref_standard: str | None = Field(default=None, max_length=60)
    applies_to: str | None = Field(default=None, max_length=300)
    remark: str | None = None
    sort_order: int | None = None


class DictTypeUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=60)
    ref_standard: str | None = Field(default=None, max_length=60)
    applies_to: str | None = Field(default=None, max_length=300)
    remark: str | None = None
    is_active: bool | None = None
    sort_order: int | None = None
