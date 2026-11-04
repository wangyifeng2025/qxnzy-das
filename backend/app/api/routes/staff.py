from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select

from app.api.deps import DbSession, require_any_permission, require_permissions
from app.core.config import settings
from app.models.staff import StaffMember
from app.models.system import User
from app.schemas.common import Message, Page
from app.schemas.staff import StaffFormMeta, StaffListItem, StaffMemberRead
from app.services.audit import write_audit
from app.services.staff import (
    active_department_names,
    allowed_departments,
    apply_rules,
    assert_scope,
    assign_row,
    can_submit,
    ensure_unique,
    form_meta,
    load_dict_options,
    scoped_query,
    to_list_item,
    to_read,
)
from app.services.staff_rules import StaffWrite

router = APIRouter(prefix="/api/staff", tags=["教职工基本信息"])

ReadStaff = Annotated[User, Depends(require_any_permission("fill:view", "fill:submit"))]
WriteStaff = Annotated[User, Depends(require_permissions("fill:submit"))]


async def _load(session: DbSession, user: User, record_id: str) -> StaffMember:
    row = await session.scalar(
        scoped_query(user).where(StaffMember.ZJSJWYXBS == record_id)
    )
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="教职工基本信息不存在或无权查看")
    return row


@router.get("/form-meta", response_model=StaffFormMeta, summary="填报表单所需字典与部门")
async def read_form_meta(session: DbSession, user: ReadStaff) -> StaffFormMeta:
    dicts, _allowed = await load_dict_options(session)
    names = await active_department_names(session)
    return form_meta(user, allowed_departments(user, names), dicts)


@router.get("", response_model=Page[StaffListItem], summary="教职工基本信息列表")
async def list_staff(
    session: DbSession,
    user: ReadStaff,
    keyword: Annotated[str | None, Query(description="教工号 / 姓名")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=50)] = 8,
) -> Page[StaffListItem]:
    query = scoped_query(user)
    if keyword:
        like = f"%{keyword.strip()}%"
        query = query.where(or_(StaffMember.JGH.ilike(like), StaffMember.JSXM.ilike(like)))
    total = await session.scalar(select(func.count()).select_from(query.subquery()))
    rows = (
        await session.scalars(
            query.order_by(StaffMember.YXBMCMC, StaffMember.JGH)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    return Page(
        items=[to_list_item(row) for row in rows],
        total=int(total or 0),
        page=page,
        page_size=page_size,
    )


@router.get("/{record_id}", response_model=StaffMemberRead, summary="教职工基本信息详情")
async def read_staff(record_id: str, session: DbSession, user: ReadStaff) -> StaffMemberRead:
    return to_read(await _load(session, user, record_id))


@router.post(
    "",
    response_model=StaffMemberRead,
    status_code=status.HTTP_201_CREATED,
    summary="新增教职工基本信息",
)
async def create_staff(
    payload: StaffWrite, session: DbSession, user: WriteStaff
) -> StaffMemberRead:
    if not can_submit(user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="缺少权限：fill:submit")
    _dicts, options = await load_dict_options(session)
    names = await active_department_names(session)
    data, warnings = apply_rules(payload, options, set(allowed_departments(user, names)))
    assert_scope(user, department=str(data["YXBMCMC"]), staff_no=str(data["JGH"]))
    await ensure_unique(session, str(data["JGH"]), str(data["SFZJH"]), None)
    row = StaffMember(XXDM=settings.school_code)
    assign_row(row, data, user)
    session.add(row)
    await session.flush()
    await write_audit(
        session,
        action="staff.create",
        resource_type="staff",
        resource_id=row.ZJSJWYXBS,
        summary=f"新增教职工基本信息 {row.JGH}（{row.JSXM}）",
        actor=user,
    )
    await session.commit()
    await session.refresh(row)
    return to_read(row, warnings)


@router.put("/{record_id}", response_model=StaffMemberRead, summary="修改教职工基本信息")
async def update_staff(
    record_id: str, payload: StaffWrite, session: DbSession, user: WriteStaff
) -> StaffMemberRead:
    row = await _load(session, user, record_id)
    _dicts, options = await load_dict_options(session)
    names = await active_department_names(session)
    data, warnings = apply_rules(payload, options, set(allowed_departments(user, names)))
    assert_scope(user, department=str(data["YXBMCMC"]), staff_no=str(data["JGH"]))
    if user.data_scope == "self" and not user.is_superuser and str(data["JGH"]) != row.JGH:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="不能修改本人教工号")
    await ensure_unique(session, str(data["JGH"]), str(data["SFZJH"]), row.ZJSJWYXBS)
    assign_row(row, data, user)
    await write_audit(
        session,
        action="staff.update",
        resource_type="staff",
        resource_id=row.ZJSJWYXBS,
        summary=f"修改教职工基本信息 {row.JGH}（{row.JSXM}）",
        actor=user,
    )
    await session.commit()
    await session.refresh(row)
    return to_read(row, warnings)


@router.delete("/{record_id}", response_model=Message, summary="删除教职工基本信息")
async def delete_staff(record_id: str, session: DbSession, user: WriteStaff) -> Message:
    row = await _load(session, user, record_id)
    summary = f"删除教职工基本信息 {row.JGH}（{row.JSXM}）"
    await session.delete(row)
    await write_audit(
        session,
        action="staff.delete",
        resource_type="staff",
        resource_id=record_id,
        summary=summary,
        actor=user,
    )
    await session.commit()
    return Message(detail="已删除")
