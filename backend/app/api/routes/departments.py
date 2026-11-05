from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select

from app.api.deps import DbSession, require_permissions
from app.models.system import Department, DepartmentKind, User
from app.schemas.common import Message
from app.schemas.system import DepartmentCreate, DepartmentRead, DepartmentUpdate
from app.services.audit import write_audit
from app.services.system import department_to_read, department_user_counts

router = APIRouter(prefix="/api/departments", tags=["系部管理"])

ReadDept = Annotated[User, Depends(require_permissions("department:read"))]
WriteDept = Annotated[User, Depends(require_permissions("department:write"))]


@router.get("", response_model=list[DepartmentRead], summary="系部 / 部门列表")
async def list_departments(
    session: DbSession,
    _: ReadDept,
    keyword: Annotated[str | None, Query(description="编码 / 名称 / 简称")] = None,
    kind: DepartmentKind | None = None,
    is_active: bool | None = None,
) -> list[DepartmentRead]:
    query = select(Department)
    if keyword:
        like = f"%{keyword.strip()}%"
        query = query.where(
            or_(
                Department.code.ilike(like),
                Department.name.ilike(like),
                Department.short_name.ilike(like),
            )
        )
    if kind is not None:
        query = query.where(Department.kind == kind)
    if is_active is not None:
        query = query.where(Department.is_active.is_(is_active))
    depts = (await session.scalars(query.order_by(Department.sort_order, Department.id))).all()
    counts = await department_user_counts(session)
    return [department_to_read(d, counts.get(d.id, 0)) for d in depts]


async def _ensure_unique(
    session: DbSession, code: str | None, name: str | None, exclude_id: int | None = None
) -> None:
    conditions = []
    if code is not None:
        conditions.append(Department.code == code)
    if name is not None:
        conditions.append(Department.name == name)
    if not conditions:
        return
    query = select(Department).where(or_(*conditions))
    if exclude_id is not None:
        query = query.where(Department.id != exclude_id)
    dup = await session.scalar(query)
    if dup is not None:
        field = "编码" if dup.code == code else "名称"
        raise HTTPException(status.HTTP_409_CONFLICT, detail=f"部门{field}已存在")


async def _load(session: DbSession, department_id: int) -> Department:
    dept = await session.get(Department, department_id)
    if dept is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="部门不存在")
    return dept


@router.post(
    "", response_model=DepartmentRead, status_code=status.HTTP_201_CREATED, summary="新增系部"
)
async def create_department(
    payload: DepartmentCreate, session: DbSession, operator: WriteDept
) -> DepartmentRead:
    await _ensure_unique(session, payload.code, payload.name)
    if payload.parent_id is not None:
        await _load(session, payload.parent_id)
    dept = Department(**payload.model_dump())
    session.add(dept)
    await session.flush()
    await write_audit(
        session,
        action="department.create",
        resource_type="department",
        resource_id=str(dept.id),
        summary=f"新增部门 {dept.name}（{dept.code}）",
        actor=operator,
    )
    await session.commit()
    await session.refresh(dept)
    return department_to_read(dept)


@router.get("/{department_id}", response_model=DepartmentRead, summary="系部详情")
async def read_department(department_id: int, session: DbSession, _: ReadDept) -> DepartmentRead:
    dept = await _load(session, department_id)
    counts = await department_user_counts(session)
    return department_to_read(dept, counts.get(dept.id, 0))


@router.patch("/{department_id}", response_model=DepartmentRead, summary="修改系部")
async def update_department(
    department_id: int, payload: DepartmentUpdate, session: DbSession, operator: WriteDept
) -> DepartmentRead:
    dept = await _load(session, department_id)
    data = payload.model_dump(exclude_unset=True)
    await _ensure_unique(session, data.get("code"), data.get("name"), exclude_id=dept.id)
    if data.get("parent_id") is not None:
        if data["parent_id"] == dept.id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="上级部门不能是自己")
        await _load(session, data["parent_id"])
    for field, value in data.items():
        setattr(dept, field, value)
    await write_audit(
        session,
        action="department.update",
        resource_type="department",
        resource_id=str(dept.id),
        summary=f"修改部门 {dept.name}（{dept.code}）",
        actor=operator,
    )
    await session.commit()
    await session.refresh(dept)
    counts = await department_user_counts(session)
    return department_to_read(dept, counts.get(dept.id, 0))


@router.delete("/{department_id}", response_model=Message, summary="删除系部")
async def delete_department(department_id: int, session: DbSession, operator: WriteDept) -> Message:
    dept = await _load(session, department_id)
    counts = await department_user_counts(session)
    if counts.get(dept.id, 0):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="该部门下仍有用户，请先调整用户所属部门或停用部门"
        )
    child = await session.scalar(select(Department.id).where(Department.parent_id == dept.id))
    if child is not None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="该部门下仍有下级部门")
    name = dept.name
    await write_audit(
        session,
        action="department.delete",
        resource_type="department",
        resource_id=str(dept.id),
        summary=f"删除部门 {name}",
        actor=operator,
    )
    await session.delete(dept)
    await session.commit()
    return Message(detail=f"已删除部门 {name}")
