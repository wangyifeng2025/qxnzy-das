from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from app.api.deps import DbSession, require_permissions
from app.models.system import Permission, Role, User
from app.schemas.common import Message
from app.schemas.system import PermissionRead, RoleCreate, RoleRead, RoleUpdate
from app.services.audit import write_audit
from app.services.system import get_permissions_by_codes, role_to_read, role_user_counts

router = APIRouter(prefix="/api", tags=["权限管理"])

ReadRole = Annotated[User, Depends(require_permissions("role:read"))]
WriteRole = Annotated[User, Depends(require_permissions("role:write"))]


@router.get("/permissions", response_model=list[PermissionRead], summary="全部权限点")
async def list_permissions(session: DbSession, _: ReadRole) -> list[PermissionRead]:
    perms = (
        await session.scalars(select(Permission).order_by(Permission.sort_order, Permission.id))
    ).all()
    return [PermissionRead.model_validate(p) for p in perms]


@router.get("/roles", response_model=list[RoleRead], summary="角色列表")
async def list_roles(session: DbSession, _: ReadRole) -> list[RoleRead]:
    roles = (await session.scalars(select(Role).order_by(Role.sort_order, Role.id))).all()
    counts = await role_user_counts(session)
    return [role_to_read(role, counts.get(role.id, 0)) for role in roles]


@router.post(
    "/roles", response_model=RoleRead, status_code=status.HTTP_201_CREATED, summary="新增角色"
)
async def create_role(payload: RoleCreate, session: DbSession, operator: WriteRole) -> RoleRead:
    dup = await session.scalar(
        select(Role.id).where((Role.code == payload.code) | (Role.name == payload.name))
    )
    if dup is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="角色编码或名称已存在")
    role = Role(
        code=payload.code,
        name=payload.name,
        description=payload.description,
        data_scope=payload.data_scope,
        sort_order=payload.sort_order,
        is_builtin=False,
    )
    role.permissions = await get_permissions_by_codes(session, payload.permission_codes)
    session.add(role)
    await session.flush()
    await write_audit(
        session,
        action="role.create",
        resource_type="role",
        resource_id=str(role.id),
        summary=f"新增角色 {role.name}（{role.code}）",
        actor=operator,
    )
    await session.commit()
    await session.refresh(role)
    return role_to_read(role)


async def _load_role(session: DbSession, role_id: int) -> Role:
    role = await session.get(Role, role_id)
    if role is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="角色不存在")
    return role


@router.patch("/roles/{role_id}", response_model=RoleRead, summary="修改角色与权限")
async def update_role(
    role_id: int, payload: RoleUpdate, session: DbSession, operator: WriteRole
) -> RoleRead:
    role = await _load_role(session, role_id)
    data = payload.model_dump(exclude_unset=True)
    if "permission_codes" in data:
        if role.code == "admin":
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, detail="信息中心管理员角色权限不可修改"
            )
        role.permissions = await get_permissions_by_codes(session, data.pop("permission_codes"))
    if "name" in data and data["name"] != role.name:
        dup = await session.scalar(select(Role.id).where(Role.name == data["name"]))
        if dup is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, detail="角色名称已存在")
    for field, value in data.items():
        setattr(role, field, value)
    await write_audit(
        session,
        action="role.update",
        resource_type="role",
        resource_id=str(role.id),
        summary=f"修改角色 {role.name}（{role.code}）",
        actor=operator,
    )
    await session.commit()
    await session.refresh(role)
    counts = await role_user_counts(session)
    return role_to_read(role, counts.get(role.id, 0))


@router.delete("/roles/{role_id}", response_model=Message, summary="删除角色")
async def delete_role(role_id: int, session: DbSession, operator: WriteRole) -> Message:
    role = await _load_role(session, role_id)
    if role.is_builtin:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="内置角色不可删除")
    counts = await role_user_counts(session)
    if counts.get(role.id, 0):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="仍有用户使用该角色，请先调整用户角色"
        )
    name = role.name
    await write_audit(
        session,
        action="role.delete",
        resource_type="role",
        resource_id=str(role.id),
        summary=f"删除角色 {name}",
        actor=operator,
    )
    await session.delete(role)
    await session.commit()
    return Message(detail=f"已删除角色 {name}")
