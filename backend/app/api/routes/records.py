from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status
from sqlalchemy import func, or_, select
from sqlalchemy.sql import Select

from app.api.deps import DbSession, require_any_permission
from app.datasets.access import (
    can_act,
    can_fill,
    can_review_dataset,
    can_revise,
    can_view,
    filler_type_for,
    is_center,
)
from app.datasets.registry import DATASETS, get_dataset
from app.datasets.spec import DatasetSpec
from app.datasets.staff import TITLE_RANK_OPTIONS
from app.models.records import BizRecord, BizRecordEvent, BizRecordVersion
from app.models.system import Department, User
from app.schemas.common import Message, Page
from app.schemas.records import (
    BatchAction,
    BatchFailure,
    BatchResult,
    CommentWrite,
    DatasetAccess,
    DatasetMeta,
    DictOption,
    FieldMeta,
    GroupMeta,
    ImportCommit,
    ImportResult,
    ImportRow,
    RecordDetail,
    RecordEventRead,
    RecordListItem,
    RecordVersionRead,
    RecordWrite,
    ReviewWrite,
)
from app.services.audit import write_audit
from app.services.records import (
    allowed_department_names,
    create_record,
    delete_record,
    export_csv,
    mask_payload,
    review_record,
    revise_record,
    skip_publish,
    submit_record,
    update_record,
    withdraw_record,
)
from app.services.spreadsheet import parse_upload, preview_rows, template_bytes
from app.services.staff import active_department_names, load_dict_options

router = APIRouter(tags=["填报记录"])

Reader = Annotated[
    User, Depends(require_any_permission("fill:view", "fill:submit", "review:manage"))
]


def _summary(spec: DatasetSpec, payload: dict[str, object], *, reveal: bool) -> dict[str, object]:
    shown = mask_payload(spec, payload, reveal=reveal)
    return {code: shown.get(code) for code in spec.list_fields}


async def _department_name(session: DbSession, department_id: int | None) -> str | None:
    if department_id is None:
        return None
    name = await session.scalar(select(Department.name).where(Department.id == department_id))
    return name if isinstance(name, str) else None


def _item(
    user: User,
    spec: DatasetSpec,
    record: BizRecord,
    department_name: str | None,
    *,
    reveal: bool,
) -> RecordListItem:
    return RecordListItem(
        id=record.id,
        dataset_code=record.dataset_code,
        dataset_name=spec.name,
        business_key=record.business_key,
        status=record.status,
        owner_account=record.owner_account,
        filler_account=record.filler_account,
        filler_type=record.filler_type,
        department_name=department_name,
        summary=_summary(spec, record.payload, reveal=reveal),
        warnings=list(record.warnings or []),
        errors=list(record.errors or []),
        completeness=record.completeness,
        updated_at=record.updated_at,
        published_version=record.published_version,
        can_review=can_act(user, spec, record) or can_act(user, spec, record, skip=True),
        can_revise=can_revise(user, spec, record),
    )


async def _load(session: DbSession, user: User, record_id: str) -> tuple[DatasetSpec, BizRecord]:
    record = await session.get(BizRecord, record_id)
    if record is None or record.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="记录不存在或无权查看")
    spec = get_dataset(record.dataset_code)
    if not can_view(user, spec, record):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="记录不存在或无权查看")
    return spec, record


def _reveal(user: User, record: BizRecord) -> bool:
    return is_center(user) or user.account in {record.owner_account, record.filler_account}


@router.get("/api/datasets", response_model=list[DatasetAccess], summary="当前用户可见的数据集")
async def list_datasets(user: Reader) -> list[DatasetAccess]:
    return [
        DatasetAccess(
            code=spec.code,
            name=spec.name,
            category=spec.category,
            can_fill=can_fill(user, spec),
            can_review=can_review_dataset(user, spec),
        )
        for spec in DATASETS.values()
        if can_fill(user, spec) or can_review_dataset(user, spec) or is_center(user)
    ]


@router.get("/api/datasets/{code}/meta", response_model=DatasetMeta, summary="数据集表单元数据")
async def read_meta(code: str, session: DbSession, user: Reader) -> DatasetMeta:
    spec = get_dataset(code)
    found, _options = await load_dict_options(session)
    names = await active_department_names(session)
    return DatasetMeta(
        code=spec.code,
        name=spec.name,
        list_fields=list(spec.list_fields),
        business_key_fields=list(spec.business_key_fields),
        can_fill=can_fill(user, spec),
        can_review=can_review_dataset(user, spec),
        can_export_sensitive=is_center(user),
        owner_field=spec.owner_field,
        owner_name_field=spec.owner_name_field,
        department_field=spec.department_field,
        filler_type=filler_type_for(user, spec),
        account=user.account,
        user_name=user.name,
        department_name=user.department.name if user.department is not None else None,
        departments=allowed_department_names(user, spec, names),
        dicts={
            dict_code: [DictOption(value=item.value, label=item.label) for item in items]
            for dict_code, items in found.items()
            if dict_code in {field.dict_code for field in spec.fields}
        },
        title_ranks=list(TITLE_RANK_OPTIONS),
        groups=[GroupMeta(title=title, hint=hint) for title, hint in spec.groups],
        fields=[FieldMeta(**field.__dict__) for field in spec.fields],
    )


@router.get(
    "/api/datasets/{code}/records",
    response_model=Page[RecordListItem],
    summary="数据集记录",
)
async def list_records(
    code: str,
    session: DbSession,
    user: Reader,
    keyword: Annotated[str | None, Query()] = None,
    record_status: Annotated[str | None, Query(alias="status")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=50)] = 8,
) -> Page[RecordListItem]:
    spec = get_dataset(code)
    query = _visible(user, spec)
    if record_status:
        query = query.where(BizRecord.status.in_(record_status.split(",")))
    if keyword:
        like = f"%{keyword.strip()}%"
        matched = [BizRecord.business_key.ilike(like)]
        matched.extend(BizRecord.payload[code].astext.ilike(like) for code in spec.list_fields)
        query = query.where(or_(*matched))
    total = await session.scalar(select(func.count()).select_from(query.subquery()))
    rows = (
        await session.scalars(
            query.order_by(BizRecord.updated_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    items = []
    for row in rows:
        department = await _department_name(session, row.department_id)
        items.append(_item(user, spec, row, department, reveal=False))
    return Page(items=items, total=int(total or 0), page=page, page_size=page_size)


@router.get("/api/datasets/{code}/export", summary="导出当前用户可见的记录")
async def export_records(
    code: str,
    session: DbSession,
    user: Reader,
    reveal: Annotated[bool, Query()] = False,
) -> Response:
    spec = get_dataset(code)
    if reveal and not is_center(user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="只有信息中心可以导出明文")
    rows = (
        await session.scalars(
            _visible(user, spec).order_by(BizRecord.updated_at.desc()).limit(5000)
        )
    ).all()
    if reveal:
        await write_audit(
            session,
            action="record.export_sensitive",
            resource_type="biz_record",
            resource_id=spec.code,
            summary=f"{spec.code} 明文导出 {len(rows)} 条",
            actor=user,
        )
        await session.commit()
    return Response(
        content=export_csv(spec, list(rows), reveal=reveal),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{spec.code}.csv"'},
    )


@router.get("/api/datasets/{code}/template", summary="下载填报模板")
async def download_template(code: str, user: Reader) -> Response:
    spec = get_dataset(code)
    if not can_fill(user, spec):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="无权下载该数据集模板")
    return Response(
        content=template_bytes(spec),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{spec.code}.xlsx"'},
    )


@router.post("/api/datasets/{code}/imports", response_model=list[ImportRow], summary="预览导入")
async def preview_import(
    code: str,
    session: DbSession,
    user: Reader,
    file: Annotated[UploadFile, File()],
) -> list[ImportRow]:
    spec = get_dataset(code)
    if not can_fill(user, spec):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="无权导入该数据集")
    content = await file.read()
    found, _options = await load_dict_options(session)
    rows = parse_upload(spec, file.filename or "", content, found)
    return await preview_rows(session, user, spec, rows)


@router.post(
    "/api/datasets/{code}/imports/commit",
    response_model=ImportResult,
    summary="把选中的行生成草稿或提交审核",
)
async def commit_import(
    code: str, body: ImportCommit, session: DbSession, user: Reader
) -> ImportResult:
    spec = get_dataset(code)
    if not can_fill(user, spec):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="无权导入该数据集")
    if not body.payloads:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="没有可导入的行")
    created = 0
    submitted = 0
    for payload in body.payloads:
        record = await create_record(session, user, spec, payload, source_type="excel")
        created += 1
        if body.submit:
            await submit_record(session, user, spec, record)
            submitted += 1
    await session.commit()
    return ImportResult(created=created, submitted=submitted)


@router.post(
    "/api/datasets/{code}/records",
    response_model=RecordDetail,
    status_code=status.HTTP_201_CREATED,
    summary="新建草稿",
)
async def create(code: str, body: RecordWrite, session: DbSession, user: Reader) -> RecordDetail:
    spec = get_dataset(code)
    record = await create_record(session, user, spec, body.payload)
    await session.commit()
    await session.refresh(record)
    return await _detail(session, user, spec, record)


@router.get("/api/my/records", response_model=Page[RecordListItem], summary="我填写或属于我的记录")
async def my_records(
    session: DbSession,
    user: Reader,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=50)] = 8,
) -> Page[RecordListItem]:
    query = select(BizRecord).where(
        BizRecord.deleted_at.is_(None),
        or_(BizRecord.filler_account == user.account, BizRecord.owner_account == user.account),
    )
    return await _page(session, user, query, page, page_size)


@router.get("/api/reviews/todo", response_model=Page[RecordListItem], summary="待我审核的记录")
async def review_todo(
    session: DbSession,
    user: Reader,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=50)] = 8,
) -> Page[RecordListItem]:
    query = select(BizRecord).where(BizRecord.id == "")
    clauses = []
    for spec in DATASETS.values():
        if not can_review_dataset(user, spec):
            continue
        if is_center(user):
            clauses.append(
                (BizRecord.dataset_code == spec.code)
                & BizRecord.status.in_(("pending_dept", "pending_domain", "pending_center"))
            )
            continue
        if user.department is None:
            continue
        if "staff" in {role.code for role in user.roles}:
            clauses.append(
                (BizRecord.dataset_code == spec.code)
                & (BizRecord.status == "pending_dept")
                & (BizRecord.department_id == user.department_id)
                & (BizRecord.filler_account != user.account)
            )
        auditor = "auditor" in {role.code for role in user.roles}
        if auditor and spec.review_department == user.department.code:
            clauses.append(
                (BizRecord.dataset_code == spec.code)
                & (BizRecord.status == "pending_domain")
                & (BizRecord.filler_account != user.account)
            )
    if clauses:
        combined = clauses[0]
        for clause in clauses[1:]:
            combined = combined | clause
        query = select(BizRecord).where(BizRecord.deleted_at.is_(None), combined)
    return await _page(session, user, query, page, page_size)


@router.get("/api/records/{record_id}", response_model=RecordDetail, summary="记录详情")
async def read_record(record_id: str, session: DbSession, user: Reader) -> RecordDetail:
    spec, record = await _load(session, user, record_id)
    return await _detail(session, user, spec, record)


@router.put("/api/records/{record_id}", response_model=RecordDetail, summary="修改草稿")
async def update(
    record_id: str, body: RecordWrite, session: DbSession, user: Reader
) -> RecordDetail:
    spec, record = await _load(session, user, record_id)
    record = await update_record(session, user, spec, record, body.payload)
    await session.commit()
    await session.refresh(record)
    return await _detail(session, user, spec, record)


@router.delete("/api/records/{record_id}", response_model=Message, summary="删除草稿")
async def remove(record_id: str, session: DbSession, user: Reader) -> Message:
    spec, record = await _load(session, user, record_id)
    await delete_record(session, user, spec, record)
    await session.commit()
    return Message(detail="已删除")


@router.post("/api/records/{record_id}/submit", response_model=RecordDetail, summary="提交审核")
async def submit(record_id: str, session: DbSession, user: Reader) -> RecordDetail:
    spec, record = await _load(session, user, record_id)
    record = await submit_record(session, user, spec, record)
    await session.commit()
    await session.refresh(record)
    return await _detail(session, user, spec, record)


@router.post("/api/records/{record_id}/withdraw", response_model=RecordDetail, summary="撤回")
async def withdraw(record_id: str, session: DbSession, user: Reader) -> RecordDetail:
    spec, record = await _load(session, user, record_id)
    record = await withdraw_record(session, user, spec, record)
    await session.commit()
    await session.refresh(record)
    return await _detail(session, user, spec, record)


@router.post("/api/records/batch", response_model=BatchResult, summary="批量提交、撤回、审核或退回")
async def batch_action(body: BatchAction, session: DbSession, user: Reader) -> BatchResult:
    """逐条处理，单条失败不影响其它记录；失败原因逐条返回。

    审核通过时，信息中心对尚在系部、业务部门环节的记录直接跳级发布。
    """
    comment = body.comment.strip()
    if body.action == "return" and not comment:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="退回必须填写意见")
    done = 0
    failed: list[BatchFailure] = []
    for record_id in dict.fromkeys(body.ids):
        try:
            async with session.begin_nested():
                spec, record = await _load(session, user, record_id)
                if body.action == "submit":
                    await submit_record(session, user, spec, record)
                elif body.action == "withdraw":
                    await withdraw_record(session, user, spec, record)
                elif body.action == "return" or can_act(user, spec, record):
                    await review_record(
                        session, user, spec, record, decision=body.action, comment=comment
                    )
                else:
                    await skip_publish(
                        session, user, spec, record, comment or "信息中心批量审核发布"
                    )
        except HTTPException as exc:
            failed.append(BatchFailure(id=record_id, reason=str(exc.detail)))
            continue
        done += 1
    await session.commit()
    return BatchResult(done=done, failed=failed)


@router.post("/api/records/{record_id}/review", response_model=RecordDetail, summary="审核")
async def review(
    record_id: str, body: ReviewWrite, session: DbSession, user: Reader
) -> RecordDetail:
    spec, record = await _load(session, user, record_id)
    record = await review_record(
        session, user, spec, record, decision=body.decision, comment=body.comment
    )
    await session.commit()
    await session.refresh(record)
    return await _detail(session, user, spec, record)


@router.post("/api/records/{record_id}/publish", response_model=RecordDetail, summary="跳级发布")
async def publish(
    record_id: str, body: CommentWrite, session: DbSession, user: Reader
) -> RecordDetail:
    spec, record = await _load(session, user, record_id)
    record = await skip_publish(session, user, spec, record, body.comment)
    await session.commit()
    await session.refresh(record)
    return await _detail(session, user, spec, record)


@router.post(
    "/api/records/{record_id}/revise",
    response_model=RecordDetail,
    summary="已发布记录改为草稿",
)
async def revise(record_id: str, session: DbSession, user: Reader) -> RecordDetail:
    spec, record = await _load(session, user, record_id)
    record = await revise_record(session, user, spec, record)
    await session.commit()
    await session.refresh(record)
    return await _detail(session, user, spec, record)


@router.get(
    "/api/records/{record_id}/events",
    response_model=list[RecordEventRead],
    summary="流转记录",
)
async def events(record_id: str, session: DbSession, user: Reader) -> list[RecordEventRead]:
    await _load(session, user, record_id)
    rows = (
        await session.scalars(
            select(BizRecordEvent)
            .where(BizRecordEvent.record_id == record_id)
            .order_by(BizRecordEvent.id)
        )
    ).all()
    result = []
    for row in rows:
        account = None
        if row.actor_id is not None:
            account = await session.scalar(select(User.account).where(User.id == row.actor_id))
        result.append(
            RecordEventRead(
                id=row.id,
                action=row.action,
                from_status=row.from_status,
                to_status=row.to_status,
                comment=row.comment,
                actor_account=account,
                diff=row.diff,
                created_at=row.created_at,
            )
        )
    return result


@router.get("/api/records/{record_id}/versions", response_model=list[RecordVersionRead])
async def versions(record_id: str, session: DbSession, user: Reader) -> list[RecordVersionRead]:
    spec, _record = await _load(session, user, record_id)
    rows = (
        await session.scalars(
            select(BizRecordVersion)
            .where(BizRecordVersion.record_id == record_id)
            .order_by(BizRecordVersion.version_no)
        )
    ).all()
    return [
        RecordVersionRead(
            version_no=row.version_no,
            payload=mask_payload(spec, row.payload, reveal=is_center(user)),
            published_at=row.published_at,
        )
        for row in rows
    ]


def _visible(user: User, spec: DatasetSpec) -> Select[tuple[BizRecord]]:
    query = select(BizRecord).where(
        BizRecord.dataset_code == spec.code, BizRecord.deleted_at.is_(None)
    )
    if is_center(user):
        return query
    domain_auditor = (
        user.department is not None
        and "auditor" in {role.code for role in user.roles}
        and spec.review_department == user.department.code
    )
    if spec.category != "teacher":
        if domain_auditor:
            return query
        return query.where(BizRecord.id == "")
    if domain_auditor:
        return query
    if user.department is not None and "staff" in {role.code for role in user.roles}:
        return query.where(BizRecord.department_id == user.department_id)
    return query.where(BizRecord.owner_account == user.account)


async def _page(
    session: DbSession,
    user: User,
    query: Select[tuple[BizRecord]],
    page: int,
    page_size: int,
) -> Page[RecordListItem]:
    total = await session.scalar(select(func.count()).select_from(query.subquery()))
    rows = (
        await session.scalars(
            query.order_by(BizRecord.updated_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    items = []
    for row in rows:
        spec = get_dataset(row.dataset_code)
        department = await _department_name(session, row.department_id)
        items.append(_item(user, spec, row, department, reveal=False))
    return Page(items=items, total=int(total or 0), page=page, page_size=page_size)


async def _detail(
    session: DbSession, user: User, spec: DatasetSpec, record: BizRecord
) -> RecordDetail:
    department = await _department_name(session, record.department_id)
    base = _item(user, spec, record, department, reveal=_reveal(user, record))
    return RecordDetail(
        **base.model_dump(),
        payload=mask_payload(spec, record.payload, reveal=_reveal(user, record)),
        field_sources=dict(record.field_sources or {}),
        source_type=record.source_type,
        schema_version=record.schema_version,
        ods_id=record.ods_id,
    )
