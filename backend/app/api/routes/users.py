from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select

from app.api.deps import DbSession, require_permissions
from app.models.system import Role, User, UserStatus
from app.schemas.common import Message, Page
from app.schemas.system import (
    PasswordReset,
    UserCreate,
    UserRead,
    UserStatusUpdate,
    UserUpdate,
)
from app.services.audit import write_audit
from app.services.system import (
    ensure_account_unique,
    ensure_department_exists,
    get_roles_by_codes,
    set_password,
    user_to_read,
)

router = APIRouter(prefix="/api/users", tags=["用户管理"])

ReadUser = Annotated[User, Depends(require_permissions("user:read"))]
WriteUser = Annotated[User, Depends(require_permissions("user:write"))]


async def _load_user(session: DbSession, user_id: int) -> User:
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="用户不存在")
    return user


@router.get("", response_model=Page[UserRead], summary="分页查询用户")
async def list_users(
    session: DbSession,
    _: ReadUser,
    keyword: Annotated[str | None, Query(description="账号 / 姓名 / 手机号")] = None,
    department_id: int | None = None,
    role_code: str | None = None,
    status_filter: Annotated[UserStatus | None, Query(alias="status")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 20,
) -> Page[UserRead]:
    query = select(User)
    if keyword:
        like = f"%{keyword.strip()}%"
        query = query.where(
            or_(User.account.ilike(like), User.name.ilike(like), User.phone.ilike(like))
        )
    if department_id is not None:
        query = query.where(User.department_id == department_id)
    if role_code:
        query = query.where(User.roles.any(Role.code == role_code))
    if status_filter is not None:
        query = query.where(User.status == status_filter)

    total = await session.scalar(select(func.count()).select_from(query.subquery())) or 0
    users = (
        await session.scalars(
            query.order_by(User.id).offset((page - 1) * page_size).limit(page_size)
        )
    ).all()
    return Page(
        items=[user_to_read(user) for user in users],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED, summary="新增用户")
async def create_user(payload: UserCreate, session: DbSession, operator: WriteUser) -> UserRead:
    await ensure_account_unique(session, payload.account)
    await ensure_department_exists(session, payload.department_id)
    roles = await get_roles_by_codes(session, payload.role_codes)
    user = User(
        account=payload.account.strip(),
        name=payload.name.strip(),
        department_id=payload.department_id,
        post=payload.post,
        phone=payload.phone,
        email=payload.email,
        status=payload.status,
        remark=payload.remark,
    )
    set_password(user, payload.password)
    user.roles = roles
    session.add(user)
    await session.flush()
    await write_audit(
        session,
        action="user.create",
        resource_type="user",
        resource_id=str(user.id),
        summary=f"新增用户 {user.account}（{user.name}）",
        actor=operator,
    )
    await session.commit()
    await session.refresh(user)
    return user_to_read(user)


@router.get("/{user_id}", response_model=UserRead, summary="用户详情")
async def read_user(user_id: int, session: DbSession, _: ReadUser) -> UserRead:
    return user_to_read(await _load_user(session, user_id))


@router.patch("/{user_id}", response_model=UserRead, summary="修改用户")
async def update_user(
    user_id: int, payload: UserUpdate, session: DbSession, operator: WriteUser
) -> UserRead:
    user = await _load_user(session, user_id)
    data = payload.model_dump(exclude_unset=True)
    if "department_id" in data:
        await ensure_department_exists(session, data["department_id"])
    if "role_codes" in data:
        if user.id == operator.id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="不能修改当前登录账号的角色")
        user.roles = await get_roles_by_codes(session, data.pop("role_codes"))
    if data.get("status") == UserStatus.DISABLED and user.id == operator.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="不能停用当前登录账号")
    for field, value in data.items():
        setattr(user, field, value)
    await write_audit(
        session,
        action="user.update",
        resource_type="user",
        resource_id=str(user.id),
        summary=f"修改用户 {user.account}",
        actor=operator,
    )
    await session.commit()
    await session.refresh(user)
    return user_to_read(user)


@router.patch("/{user_id}/status", response_model=UserRead, summary="启用 / 停用用户")
async def update_status(
    user_id: int, payload: UserStatusUpdate, session: DbSession, operator: WriteUser
) -> UserRead:
    user = await _load_user(session, user_id)
    if user.id == operator.id and payload.status == UserStatus.DISABLED:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="不能停用当前登录账号")
    if user.is_superuser and payload.status == UserStatus.DISABLED:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="不能停用超级管理员")
    user.status = payload.status
    await write_audit(
        session,
        action="user.status",
        resource_type="user",
        resource_id=str(user.id),
        summary=f"{'停用' if payload.status == UserStatus.DISABLED else '启用'}用户 {user.account}",
        actor=operator,
    )
    await session.commit()
    await session.refresh(user)
    return user_to_read(user)


@router.post("/{user_id}/reset-password", response_model=Message, summary="重置密码")
async def reset_password(
    user_id: int, payload: PasswordReset, session: DbSession, operator: WriteUser
) -> Message:
    user = await _load_user(session, user_id)
    set_password(user, payload.password)
    await write_audit(
        session,
        action="user.reset_password",
        resource_type="user",
        resource_id=str(user.id),
        summary=f"重置用户 {user.account} 的密码",
        actor=operator,
    )
    await session.commit()
    return Message(detail=f"已重置 {user.name} 的密码")


@router.delete("/{user_id}", response_model=Message, summary="删除用户")
async def delete_user(user_id: int, session: DbSession, operator: WriteUser) -> Message:
    user = await _load_user(session, user_id)
    if user.id == operator.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="不能删除当前登录账号")
    if user.is_superuser:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="不能删除超级管理员")
    account = user.account
    await write_audit(
        session,
        action="user.delete",
        resource_type="user",
        resource_id=str(user.id),
        summary=f"删除用户 {account}",
        actor=operator,
    )
    await session.delete(user)
    await session.commit()
    return Message(detail=f"已删除用户 {account}")
