"""系统管理业务逻辑：用户、角色、部门的查询与校验。"""

from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password, verify_password
from app.models.system import (
    Department,
    Permission,
    Role,
    User,
    UserStatus,
    sys_user_role,
)
from app.schemas.system import (
    CurrentUser,
    DepartmentRead,
    RoleRead,
    UserRead,
)
from app.services.audit import write_audit

# ---------- 序列化 ----------


def user_to_read(user: User, *, department_name: str | None = None) -> UserRead:
    return UserRead(
        id=user.id,
        account=user.account,
        name=user.name,
        department_id=user.department_id,
        department_name=department_name
        or (user.department.name if user.department is not None else None),
        post=user.post,
        phone=user.phone,
        email=user.email,
        status=user.status,
        is_superuser=user.is_superuser,
        role_codes=[role.code for role in user.roles],
        role_names=[role.name for role in user.roles],
        last_login_at=user.last_login_at,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


def user_to_current(user: User) -> CurrentUser:
    base = user_to_read(user)
    return CurrentUser(
        **base.model_dump(),
        permissions=sorted(user.permission_codes),
        data_scope=user.data_scope,
    )


def role_to_read(role: Role, user_count: int = 0) -> RoleRead:
    return RoleRead(
        id=role.id,
        code=role.code,
        name=role.name,
        description=role.description,
        data_scope=role.data_scope,
        is_builtin=role.is_builtin,
        sort_order=role.sort_order,
        permission_codes=sorted(perm.code for perm in role.permissions),
        user_count=user_count,
        created_at=role.created_at,
        updated_at=role.updated_at,
    )


def department_to_read(dept: Department, user_count: int = 0) -> DepartmentRead:
    return DepartmentRead(
        id=dept.id,
        code=dept.code,
        name=dept.name,
        short_name=dept.short_name,
        kind=dept.kind,
        parent_id=dept.parent_id,
        leader=dept.leader,
        data_manager=dept.data_manager,
        phone=dept.phone,
        sort_order=dept.sort_order,
        is_active=dept.is_active,
        remark=dept.remark,
        user_count=user_count,
        created_at=dept.created_at,
        updated_at=dept.updated_at,
    )


# ---------- 认证 ----------


async def authenticate(session: AsyncSession, account: str, password: str) -> User:
    attempted = account.strip()
    user = await session.scalar(select(User).where(User.account == attempted))
    if user is None or not verify_password(password, user.password_hash):
        await write_audit(
            session,
            action="auth.login_failed",
            resource_type="user",
            resource_id=attempted,
            summary=f"登录失败：{attempted}",
            actor_account=attempted,
        )
        await session.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="账号或密码不正确")
    if user.status != UserStatus.ACTIVE:
        await write_audit(
            session,
            action="auth.login_denied",
            resource_type="user",
            resource_id=str(user.id),
            summary=f"停用账号尝试登录：{user.account}",
            actor=user,
        )
        await session.commit()
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="账号已停用，请联系信息中心")
    user.last_login_at = datetime.now(UTC)
    await write_audit(
        session,
        action="auth.login",
        resource_type="user",
        resource_id=str(user.id),
        summary=f"登录成功：{user.account}",
        actor=user,
    )
    await session.commit()
    await session.refresh(user)
    return user


# ---------- 查询辅助 ----------


async def get_roles_by_codes(session: AsyncSession, codes: list[str]) -> list[Role]:
    if not codes:
        return []
    roles = (await session.scalars(select(Role).where(Role.code.in_(codes)))).all()
    found = {role.code for role in roles}
    missing = sorted(set(codes) - found)
    if missing:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=f"角色不存在：{', '.join(missing)}")
    return list(roles)


async def get_permissions_by_codes(session: AsyncSession, codes: list[str]) -> list[Permission]:
    if not codes:
        return []
    perms = (await session.scalars(select(Permission).where(Permission.code.in_(codes)))).all()
    found = {perm.code for perm in perms}
    missing = sorted(set(codes) - found)
    if missing:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=f"权限不存在：{', '.join(missing)}")
    return list(perms)


async def ensure_department_exists(session: AsyncSession, department_id: int | None) -> None:
    if department_id is None:
        return
    if await session.get(Department, department_id) is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="所属部门不存在")


async def ensure_account_unique(session: AsyncSession, account: str) -> None:
    exists = await session.scalar(select(User.id).where(User.account == account))
    if exists is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=f"账号 {account} 已存在")


async def role_user_counts(session: AsyncSession) -> dict[int, int]:
    rows = await session.execute(
        select(sys_user_role.c.role_id, func.count()).group_by(sys_user_role.c.role_id)
    )
    return {role_id: count for role_id, count in rows.all()}


async def department_user_counts(session: AsyncSession) -> dict[int, int]:
    rows = await session.execute(
        select(User.department_id, func.count())
        .where(User.department_id.is_not(None))
        .group_by(User.department_id)
    )
    return {dept_id: count for dept_id, count in rows.all() if dept_id is not None}


def set_password(user: User, password: str) -> None:
    user.password_hash = hash_password(password)
