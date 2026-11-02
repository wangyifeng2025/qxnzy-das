from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.api.deps import DbSession, require_permissions
from app.models.system import DictItem, DictType, User
from app.schemas.common import Message
from app.schemas.system import (
    DictItemCreate,
    DictItemRead,
    DictItemUpdate,
    DictTypeCreate,
    DictTypeRead,
    DictTypeUpdate,
    DictTypeWithItems,
)
from app.services.audit import write_audit

router = APIRouter(prefix="/api/dicts", tags=["数据字典"])

ReadDict = Annotated[User, Depends(require_permissions("dict:read"))]
WriteDict = Annotated[User, Depends(require_permissions("dict:write"))]


@router.get("", response_model=list[DictTypeRead], summary="字典分类列表")
async def list_dict_types(
    session: DbSession,
    _: ReadDict,
    keyword: Annotated[str | None, Query(description="编号 / 名称")] = None,
) -> list[DictTypeRead]:
    count_sub = (
        select(DictItem.type_id, func.count().label("n")).group_by(DictItem.type_id).subquery()
    )
    query = select(DictType, func.coalesce(count_sub.c.n, 0)).outerjoin(
        count_sub, count_sub.c.type_id == DictType.id
    )
    if keyword:
        like = f"%{keyword.strip()}%"
        query = query.where(DictType.code.ilike(like) | DictType.name.ilike(like))
    rows = (await session.execute(query.order_by(DictType.sort_order, DictType.id))).all()
    result = []
    for dict_type, item_count in rows:
        read = DictTypeRead.model_validate(dict_type)
        read.item_count = int(item_count)
        result.append(read)
    return result


@router.post(
    "",
    response_model=DictTypeRead,
    status_code=status.HTTP_201_CREATED,
    summary="新增字典分类",
)
async def create_dict_type(
    payload: DictTypeCreate, session: DbSession, operator: WriteDict
) -> DictTypeRead:
    code = payload.code.strip().upper()
    name = payload.name.strip()
    existing_code = await session.scalar(select(DictType.id).where(DictType.code == code))
    if existing_code is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="该分类编号已存在")
    existing_name = await session.scalar(select(DictType.id).where(DictType.name == name))
    if existing_name is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="该分类名称已存在")
    if payload.sort_order is None:
        max_sort = await session.scalar(select(func.max(DictType.sort_order)))
        sort_order = int(max_sort or 0) + 1
    else:
        sort_order = payload.sort_order
    dict_type = DictType(
        code=code,
        name=name,
        ref_standard=_blank(payload.ref_standard),
        applies_to=_blank(payload.applies_to),
        remark=_blank(payload.remark),
        sort_order=sort_order,
        is_active=True,
    )
    session.add(dict_type)
    await session.flush()
    await write_audit(
        session,
        action="dict.create",
        resource_type="dict_type",
        resource_id=dict_type.code,
        summary=f"新增字典分类 {dict_type.code} {dict_type.name}",
        actor=operator,
    )
    await session.commit()
    await session.refresh(dict_type)
    read = DictTypeRead.model_validate(dict_type)
    read.item_count = 0
    return read


async def _load_type(session: DbSession, code: str) -> DictType:
    dict_type = await session.scalar(
        select(DictType).where(DictType.code == code.upper()).options(selectinload(DictType.items))
    )
    if dict_type is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"字典 {code} 不存在")
    return dict_type


@router.get("/{code}", response_model=DictTypeWithItems, summary="字典取值")
async def read_dict_type(
    code: str,
    session: DbSession,
    _: ReadDict,
    include_inactive: bool = False,
) -> DictTypeWithItems:
    dict_type = await _load_type(session, code)
    items = [
        DictItemRead.model_validate(item)
        for item in dict_type.items
        if include_inactive or item.is_active
    ]
    read = DictTypeWithItems.model_validate(dict_type)
    read.items = items
    read.item_count = len(dict_type.items)
    return read


def _blank(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


@router.patch("/{code}", response_model=DictTypeRead, summary="修改字典分类")
async def update_dict_type(
    code: str, payload: DictTypeUpdate, session: DbSession, operator: WriteDict
) -> DictTypeRead:
    dict_type = await _load_type(session, code)
    item_count = len(dict_type.items)
    data = payload.model_dump(exclude_unset=True)
    if "name" in data and data["name"] is not None:
        data["name"] = data["name"].strip()
    for field in ("ref_standard", "applies_to", "remark"):
        if field in data:
            data[field] = _blank(data[field])
    for field, value in data.items():
        setattr(dict_type, field, value)
    await write_audit(
        session,
        action="dict.update",
        resource_type="dict_type",
        resource_id=dict_type.code,
        summary=f"修改字典分类 {dict_type.code} {dict_type.name}",
        actor=operator,
    )
    await session.commit()
    await session.refresh(dict_type)
    read = DictTypeRead.model_validate(dict_type)
    read.item_count = item_count
    return read


@router.delete("/{code}", response_model=Message, summary="删除字典分类")
async def delete_dict_type(code: str, session: DbSession, operator: WriteDict) -> Message:
    dict_type = await _load_type(session, code)
    name = dict_type.name
    item_count = len(dict_type.items)
    await write_audit(
        session,
        action="dict.delete",
        resource_type="dict_type",
        resource_id=dict_type.code,
        summary=f"删除字典分类 {dict_type.code} {name}",
        actor=operator,
    )
    await session.delete(dict_type)
    await session.commit()
    detail = f"已删除字典分类「{name}」"
    if item_count:
        detail += f"及其 {item_count} 个取值"
    return Message(detail=detail)


@router.post(
    "/{code}/items",
    response_model=DictItemRead,
    status_code=status.HTTP_201_CREATED,
    summary="新增字典取值",
)
async def create_dict_item(
    code: str, payload: DictItemCreate, session: DbSession, operator: WriteDict
) -> DictItemRead:
    dict_type = await _load_type(session, code)
    label = payload.label.strip()
    if any(item.label == label for item in dict_type.items):
        raise HTTPException(status.HTTP_409_CONFLICT, detail="该取值已存在")
    item = DictItem(
        type_id=dict_type.id,
        value=_blank(payload.value),
        label=label,
        remark=_blank(payload.remark),
        sort_order=payload.sort_order,
        is_active=payload.is_active,
    )
    session.add(item)
    await session.flush()
    await write_audit(
        session,
        action="dict.item_create",
        resource_type="dict_item",
        resource_id=str(item.id),
        summary=f"新增 {dict_type.code} 取值「{item.label}」",
        actor=operator,
    )
    await session.commit()
    await session.refresh(item)
    return DictItemRead.model_validate(item)


@router.patch("/{code}/items/{item_id}", response_model=DictItemRead, summary="修改字典取值")
async def update_dict_item(
    code: str, item_id: int, payload: DictItemUpdate, session: DbSession, operator: WriteDict
) -> DictItemRead:
    dict_type = await _load_type(session, code)
    item = next((i for i in dict_type.items if i.id == item_id), None)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="字典取值不存在")
    data = payload.model_dump(exclude_unset=True)
    if "label" in data and data["label"] is not None:
        data["label"] = data["label"].strip()
    if "value" in data:
        data["value"] = _blank(data["value"])
    if "remark" in data:
        data["remark"] = _blank(data["remark"])
    new_label = data.get("label")
    if new_label and any(i.label == new_label and i.id != item_id for i in dict_type.items):
        raise HTTPException(status.HTTP_409_CONFLICT, detail="该取值已存在")
    for field, value in data.items():
        setattr(item, field, value)
    await write_audit(
        session,
        action="dict.item_update",
        resource_type="dict_item",
        resource_id=str(item.id),
        summary=f"修改 {dict_type.code} 取值「{item.label}」",
        actor=operator,
    )
    await session.commit()
    await session.refresh(item)
    return DictItemRead.model_validate(item)


@router.delete("/{code}/items/{item_id}", response_model=Message, summary="删除字典取值")
async def delete_dict_item(
    code: str, item_id: int, session: DbSession, operator: WriteDict
) -> Message:
    dict_type = await _load_type(session, code)
    item = next((i for i in dict_type.items if i.id == item_id), None)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="字典取值不存在")
    label = item.label
    await write_audit(
        session,
        action="dict.item_delete",
        resource_type="dict_item",
        resource_id=str(item.id),
        summary=f"删除 {dict_type.code} 取值「{label}」",
        actor=operator,
    )
    await session.delete(item)
    await session.commit()
    return Message(detail=f"已删除 {dict_type.name} 取值「{label}」")
