"""填报记录的保存、审核和发布。调用方负责提交事务。"""

import csv
import io
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.datasets.access import (
    can_act,
    can_fill,
    can_revise,
    can_view,
    filler_type_for,
    is_center,
    review_steps,
)
from app.datasets.spec import DatasetSpec, jsonable
from app.models.records import BizRecord, BizRecordEvent, BizRecordVersion
from app.models.system import Department, User
from app.services.audit import write_audit
from app.services.staff import active_department_names, load_dict_options, mask_id_card


def _now() -> datetime:
    return datetime.now(UTC)


def mask_payload(
    spec: DatasetSpec, payload: dict[str, object], *, reveal: bool
) -> dict[str, object]:
    if reveal:
        return dict(payload)
    masked = dict(payload)
    for field in spec.fields:
        if field.sensitive and isinstance(masked.get(field.code), str):
            masked[field.code] = mask_id_card(str(masked[field.code]))
    return masked


def _diff(before: dict[str, object], after: dict[str, object]) -> dict[str, object]:
    keys = set(before) | set(after)
    return {
        key: {"from": before.get(key), "to": after.get(key)}
        for key in sorted(keys)
        if before.get(key) != after.get(key)
    }


async def _event(
    session: AsyncSession,
    record: BizRecord,
    user: User,
    action: str,
    from_status: str | None,
    to_status: str,
    comment: str | None = None,
    diff: dict[str, object] | None = None,
) -> None:
    session.add(
        BizRecordEvent(
            record_id=record.id,
            action=action,
            from_status=from_status,
            to_status=to_status,
            comment=comment,
            actor_id=user.id,
            diff=diff,
            created_at=_now(),
        )
    )
    await write_audit(
        session,
        action=f"record.{action}",
        resource_type="biz_record",
        resource_id=record.id,
        summary=f"{record.dataset_code} {action} {from_status or '-'}→{to_status}",
        actor=user,
    )


def allowed_department_names(user: User, spec: DatasetSpec, names: set[str]) -> list[str]:
    kind = filler_type_for(user, spec)
    if kind in {"center", "domain"}:
        return sorted(names)
    if kind in {"teacher", "department"} and user.department is not None:
        if user.department.name in names:
            return [user.department.name]
    return []


async def _checked(
    session: AsyncSession,
    user: User,
    spec: DatasetSpec,
    payload: dict[str, object],
    *,
    strict: bool = True,
) -> tuple[dict[str, object], list[str], list[str], Department | None, str]:
    """strict=True 是提交级校验；保存草稿时放宽必填，只保留权限、主键和院系。"""
    if not can_fill(user, spec):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="无权填写该数据集")
    _found, options = await load_dict_options(session)
    names = await active_department_names(session)
    allowed = set(allowed_department_names(user, spec, names))
    errors: list[str] = []
    if strict:
        data, warnings = spec.validate(payload, options, allowed)
        if spec.relate is not None:
            await spec.relate(session, data)
    else:
        try:
            data, warnings = spec.validate(payload, options, allowed)
        except HTTPException as exc:
            detail = exc.detail if isinstance(exc.detail, str) else "校验未通过"
            errors = [part for part in detail.split("；") if part and "不能为空" not in part]
            warnings = [part for part in detail.split("；") if part and "不能为空" in part]
            data = jsonable(dict(payload))
    data = jsonable(data)
    for field in spec.business_key_fields:
        if not data.get(field):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="业务主键不能为空")
    department: Department | None = None
    department_name = str(data.get(spec.department_field) or "")
    if department_name:
        department = await session.scalar(
            select(Department).where(
                Department.name == department_name, Department.is_active.is_(True)
            )
        )
        if department is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="院系部不存在")
    elif strict:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="院系部不能为空")
    owner = str(data.get(spec.owner_field)) if spec.owner_field else ""
    kind = filler_type_for(user, spec)
    if kind == "teacher" and owner and owner != user.account:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="只能填报本人数据")
    if kind == "department" and department is not None and department.id != user.department_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="只能填报本部门数据")
    return data, warnings, errors, department, owner


async def _ensure_key(
    session: AsyncSession, spec: DatasetSpec, key: str, current_id: str | None
) -> None:
    query = select(BizRecord.id).where(
        BizRecord.dataset_code == spec.code,
        BizRecord.business_key == key,
        BizRecord.deleted_at.is_(None),
    )
    if current_id is not None:
        query = query.where(BizRecord.id != current_id)
    if await session.scalar(query) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="业务主键重复")


def _key(spec: DatasetSpec, data: dict[str, object]) -> str:
    return "|".join(str(data[field]) for field in spec.business_key_fields)


async def create_record(
    session: AsyncSession,
    user: User,
    spec: DatasetSpec,
    payload: dict[str, object],
    *,
    source_type: str = "manual",
    strict: bool = True,
    errors: list[str] | None = None,
    completeness: int = 0,
    field_sources: dict[str, object] | None = None,
    source_ref: str | None = None,
    batch_id: str | None = None,
) -> BizRecord:
    data, warnings, found, department, owner = await _checked(
        session, user, spec, payload, strict=strict
    )
    key = _key(spec, data)
    await _ensure_key(session, spec, key, None)
    now = _now()
    record = BizRecord(
        dataset_code=spec.code,
        business_key=key,
        department_id=department.id if department is not None else None,
        owner_account=owner,
        filler_type=filler_type_for(user, spec) or "teacher",
        filler_account=user.account,
        status="draft",
        payload=data,
        warnings=[*warnings, *(errors or [])],
        errors=errors or [],
        completeness=completeness,
        field_sources=field_sources or {},
        source_type=source_type,
        source_ref=source_ref,
        batch_id=batch_id,
        schema_version=spec.schema_version,
        published_version=0,
        created_by=user.id,
        updated_by=user.id,
        created_at=now,
        updated_at=now,
    )
    session.add(record)
    await session.flush()
    await _event(session, record, user, "create", None, "draft")
    return record


async def update_record(
    session: AsyncSession,
    user: User,
    spec: DatasetSpec,
    record: BizRecord,
    payload: dict[str, object],
    *,
    strict: bool = True,
    errors: list[str] | None = None,
    completeness: int | None = None,
    field_sources: dict[str, object] | None = None,
) -> BizRecord:
    _require_view(user, spec, record)
    if record.status == "published":
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="已发布记录由信息中心修改，请先由信息中心生成新草稿"
        )
    if record.status not in {"draft", "returned"}:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="审核中的记录不能修改")
    if record.filler_account != user.account and not is_center(user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="只能修改自己填写的草稿")
    data, warnings, found, department, owner = await _checked(
        session, user, spec, payload, strict=strict
    )
    key = _key(spec, data)
    await _ensure_key(session, spec, key, record.id)
    diff = _diff(record.payload, data)
    record.payload = data
    record.warnings = [*warnings, *(found or [])]
    record.errors = errors or []
    if completeness is not None:
        record.completeness = completeness
    if field_sources:
        record.field_sources = {**(record.field_sources or {}), **field_sources}
    record.business_key = key
    record.department_id = department.id if department is not None else None
    record.owner_account = owner
    record.updated_by = user.id
    record.updated_at = _now()
    await _event(session, record, user, "update", record.status, record.status, diff=diff or None)
    return record


async def delete_record(
    session: AsyncSession, user: User, spec: DatasetSpec, record: BizRecord
) -> None:
    _require_view(user, spec, record)
    if record.status not in {"draft", "returned"}:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="只能删除草稿或已退回的记录")
    if record.filler_account != user.account and not is_center(user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="只能删除自己填写的记录")
    record.deleted_at = _now()
    record.updated_at = record.deleted_at
    await _event(session, record, user, "delete", record.status, record.status)


async def submit_record(
    session: AsyncSession, user: User, spec: DatasetSpec, record: BizRecord
) -> BizRecord:
    _require_view(user, spec, record)
    if record.status not in {"draft", "returned"}:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="当前状态不能提交")
    if record.filler_account != user.account and not is_center(user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="只能提交自己填写的记录")
    data, warnings, _errors, _department, _owner = await _checked(
        session, user, spec, record.payload
    )
    record.payload = data
    record.warnings = warnings
    steps = review_steps(spec, record.filler_type)
    previous = record.status
    if not steps:
        await _publish(session, user, spec, record, action="submit")
        return record
    record.status = steps[0]
    record.updated_at = _now()
    record.updated_by = user.id
    await _event(session, record, user, "submit", previous, record.status)
    return record


async def withdraw_record(
    session: AsyncSession, user: User, spec: DatasetSpec, record: BizRecord
) -> BizRecord:
    _require_view(user, spec, record)
    steps = review_steps(spec, record.filler_type)
    if not steps or record.status != steps[0]:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="只有刚提交、尚未审核的记录可以撤回"
        )
    if record.filler_account != user.account and not is_center(user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="只能撤回自己提交的记录")
    previous = record.status
    record.status = "draft"
    record.updated_at = _now()
    record.updated_by = user.id
    await _event(session, record, user, "withdraw", previous, "draft")
    return record


async def review_record(
    session: AsyncSession,
    user: User,
    spec: DatasetSpec,
    record: BizRecord,
    *,
    decision: str,
    comment: str,
) -> BizRecord:
    allowed = can_act(user, spec, record) or (
        decision == "return" and can_act(user, spec, record, skip=True)
    )
    if not allowed:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="无权审核该记录")
    if decision == "return" and not comment.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="退回必须填写意见")
    previous = record.status
    if decision == "return":
        record.status = "returned"
        record.updated_at = _now()
        record.updated_by = user.id
        await _event(session, record, user, "return", previous, "returned", comment.strip())
        return record
    steps = review_steps(spec, record.filler_type)
    index = steps.index(record.status)
    if index == len(steps) - 1:
        await _publish(
            session, user, spec, record, action="approve", comment=comment.strip() or None
        )
        return record
    record.status = steps[index + 1]
    record.updated_at = _now()
    record.updated_by = user.id
    await _event(session, record, user, "approve", previous, record.status, comment.strip() or None)
    return record


async def skip_publish(
    session: AsyncSession, user: User, spec: DatasetSpec, record: BizRecord, comment: str
) -> BizRecord:
    if not comment.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="跳级发布必须填写说明")
    if not can_act(user, spec, record, skip=True):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="只有信息中心可以跳级发布")
    await _publish(session, user, spec, record, action="skip_publish", comment=comment.strip())
    return record


async def revise_record(
    session: AsyncSession, user: User, spec: DatasetSpec, record: BizRecord
) -> BizRecord:
    _require_view(user, spec, record)
    if not can_revise(user, spec, record):
        if record.status != "published":
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="只有已发布记录可以生成新草稿")
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, detail="已发布数据由信息中心统一维护，请联系信息中心修改"
        )
    previous = record.status
    record.status = "draft"
    record.updated_at = _now()
    record.updated_by = user.id
    await _event(session, record, user, "revise", previous, "draft")
    return record


async def _publish(
    session: AsyncSession,
    user: User,
    spec: DatasetSpec,
    record: BizRecord,
    *,
    action: str,
    comment: str | None = None,
) -> None:
    if record.status == "published":
        return
    data, warnings, _errors, _department, _owner = await _checked(
        session, user, spec, record.payload
    )
    previous = record.status
    ods_id = await spec.publish(session, record, data, user)
    record.payload = data
    record.warnings = warnings
    record.ods_id = ods_id
    record.published_version += 1
    record.status = "published"
    record.updated_at = _now()
    record.updated_by = user.id
    session.add(
        BizRecordVersion(
            record_id=record.id,
            version_no=record.published_version,
            payload=data,
            schema_version=record.schema_version,
            published_by=user.id,
            published_at=record.updated_at,
        )
    )
    await _event(session, record, user, action, previous, "published", comment)


def _require_view(user: User, spec: DatasetSpec, record: BizRecord) -> None:
    if not can_view(user, spec, record):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="记录不存在或无权查看")


_EXPORT_STATUS = {
    "draft": "草稿",
    "pending_dept": "待系部初审",
    "pending_domain": "待业务部门审核",
    "pending_center": "待信息中心审核",
    "returned": "已退回",
    "published": "已发布",
    "archived": "已归档",
}


def _csv_cell(value: object) -> str:
    text = "" if value is None else str(value)
    if text[:1] in {"=", "+", "-", "@"}:
        return f"'{text}"
    return text


def export_csv(spec: DatasetSpec, records: list[BizRecord], *, reveal: bool) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["状态", *[field.label for field in spec.fields]])
    for record in records:
        payload = mask_payload(spec, record.payload, reveal=reveal)
        writer.writerow(
            [
                _EXPORT_STATUS.get(record.status, record.status),
                *[_csv_cell(payload.get(field.code)) for field in spec.fields],
            ]
        )
    return "\ufeff" + buffer.getvalue()
