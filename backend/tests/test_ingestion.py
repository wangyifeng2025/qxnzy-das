"""文件解析：场景 2、3、4、8，以及变换、文件头和卡住任务恢复。"""

import json
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path

import pytest
from docx import Document
from fastapi import HTTPException
from httpx import AsyncClient
from openpyxl import Workbook
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.client import LLMResult, ModelUnavailable
from app.datasets.registry import get_dataset
from app.datasets.validate import check_fields
from app.ingestion.execute import build_records
from app.ingestion.file_check import FileRejected, check_upload
from app.ingestion.mapping import exact_plan
from app.ingestion.normalize import normalize_payload
from app.ingestion.parsers.spreadsheet import parse_xlsx
from app.ingestion.pipeline import run_pipeline
from app.ingestion.plan import ColumnMap, SheetPlan, StructurePlan
from app.ingestion.profile import profile_sheet
from app.ingestion.queue import enqueue_ingest
from app.ingestion.recovery import tasks_to_enqueue
from app.ingestion.transforms import concat_date, split_date_range, split_name_id
from app.models.ingestion import IngestCandidate, IngestFile, IngestTask
from app.models.records import BizRecord

AWARD = "ODS_JSHJSJ"
SCAN = "首版不支持扫描件识别，请上传可复制文字的 PDF 或改用表格"


def test_transforms() -> None:
    assert split_date_range("2024年3月至2024年6月") == ("2024年3月", "2024年6月")
    assert split_date_range("明年") is None
    assert split_name_id("罗胜（2015200012）") == ("罗胜", "2015200012")
    assert concat_date(["2024", "3", "8"]) == "2024-03-08"
    assert concat_date(["2024", "3"]) == "2024-03"


def test_merged_cells_keep_leaf_headers() -> None:
    book = Workbook()
    sheet = book.active
    assert sheet is not None
    sheet["A1"] = "注意事项"
    sheet.merge_cells("A1:D1")
    sheet["A2"] = "专业名称*"
    sheet["B2"] = "分组"
    sheet["D2"] = "专业代码*"
    sheet.merge_cells("A2:A3")
    sheet.merge_cells("B2:C2")
    sheet.merge_cells("D2:D3")
    sheet["B3"] = "是否重点专业*"
    sheet["C3"] = "级别*"
    sheet["A4"] = "生态农业技术"
    sheet["D4"] = "410104"
    buffer = BytesIO()
    book.save(buffer)
    document = parse_xlsx(buffer.getvalue())
    assert len(document.sheets) == 1
    sheet = document.sheets[0]
    assert set(sheet.merged) == {"A1:D1", "A2:A3", "B2:C2", "D2:D3"}
    profile = profile_sheet(sheet)
    assert profile.header_rows == [2, 3]
    assert profile.headers == ["专业名称*", "是否重点专业*", "级别*", "专业代码*"]
    execution = build_records(
        document,
        StructurePlan(
            sheets=[
                SheetPlan(
                    sheet=profile.sheet,
                    header_rows=profile.header_rows,
                    data_start=4,
                    columns=[
                        ColumnMap(header="专业名称*", field="ZYMC"),
                        ColumnMap(header="专业代码*", field="ZYDM"),
                    ],
                )
            ]
        ),
    )
    assert execution.records[0].raw == {"ZYMC": "生态农业技术", "ZYDM": "410104"}


def test_major_export_skips_banner_and_group_titles() -> None:
    path = (
        Path(__file__).resolve().parents[2]
        / "docs"
        / "AI解析测试数据"
        / "1.2.1开设专业表-导出结果.xlsx"
    )
    content = path.read_bytes()
    document = parse_xlsx(content)
    profile = profile_sheet(document.sheets[0])
    assert profile.headers[0] == "专业名称*"
    assert "是否重点专业*" in profile.headers
    assert "注意事项" not in profile.headers[0]
    spec = get_dataset("ODS_ZYSZSJ")
    sheet_plan = exact_plan(spec, profile)
    assert sheet_plan is not None
    execution = build_records(document, StructurePlan(sheets=[sheet_plan]))
    assert len(execution.records) == 47
    assert [record.row for record in execution.records[:2]] == [4, 9]
    assert "作物遗传育种栽培技术人员" in str(execution.records[0].raw.get("ZYJYXLMC"))


def test_major_export_maps_headers_without_model() -> None:
    path = (
        Path(__file__).resolve().parents[2]
        / "docs"
        / "AI解析测试数据"
        / "1.2.1开设专业表-导出结果.xlsx"
    )
    profile = profile_sheet(parse_xlsx(path.read_bytes()).sheets[0])
    spec = get_dataset("ODS_ZYSZSJ")
    plan = exact_plan(spec, profile)
    assert plan is not None
    fields = {column.header: column.field for column in plan.columns}
    assert fields["批准设置日期（年月）*"] == "PZSZNY"
    assert fields["类型（可多选）*"] == "ZDZYLXM"
    assert fields["小类名称*"] == "ZYJYXLMC"
    assert fields.get("填报人") is None
    missing = profile.model_copy(update={"headers": ["专业名称*", "填报人"]})
    assert exact_plan(spec, missing) is None


def test_dict_labels_normalize_by_dict_code() -> None:
    spec = get_dataset("ODS_ZYSZSJ")
    data = normalize_payload(
        spec, {"ZYCCM": "高职专科", "SFZDZY": "否"}, {"D01": {"高职专科": "2"}, "D28": {"否": "0"}}
    )
    assert data["ZYCCM"] == "2"
    assert data["SFZDZY"] == "0"


def test_degree_category_required_only_for_bachelor() -> None:
    fields = tuple(
        field for field in get_dataset("ODS_ZYSZSJ").fields if field.code in {"ZYCCM", "SYXWLBM"}
    )
    options = {"D01": {"1", "2"}, "D03": {"工学"}}
    data, _ = check_fields(fields, {"ZYCCM": "2", "SYXWLBM": "工学"}, options, set())
    assert data["SYXWLBM"] is None
    data, _ = check_fields(fields, {"ZYCCM": "1", "SYXWLBM": "工学"}, options, set())
    assert data["SYXWLBM"] == "工学"
    with pytest.raises(HTTPException, match="学位授予门类不能为空"):
        check_fields(fields, {"ZYCCM": "1"}, options, set())


def test_sparse_rows_without_anchor_fold_into_previous_record() -> None:
    content = _xlsx(
        ["名称", "代码", "层次", "类别"],
        [["甲", "01", "专科", "A"], ["", "", "", "B"], ["", "02", "本科", "C"]],
    )
    document = parse_xlsx(content)
    plan = SheetPlan(
        sheet=document.sheets[0].name,
        header_rows=[1],
        data_start=2,
        columns=[
            ColumnMap(header="名称", field="名称"),
            ColumnMap(header="代码", field="代码"),
            ColumnMap(header="层次", field="层次"),
            ColumnMap(header="类别", field="类别"),
        ],
        row_mode="grouped",
        group_key=["名称"],
        multi_value_fields=["类别"],
    )
    execution = build_records(document, StructurePlan(sheets=[plan]))
    assert [record.row for record in execution.records] == [2, 4]
    assert execution.records[0].raw == {
        "名称": "甲",
        "代码": "01",
        "层次": "专科",
        "类别": "A，B",
    }
    assert execution.records[1].raw["名称"] == ""
    assert execution.records[1].raw["代码"] == "02"


def test_rejects_xlsx_renamed_to_pdf() -> None:
    content = _xlsx(["HJMC"], [["教学成果奖"]])
    with pytest.raises(FileRejected, match="文件内容与扩展名不一致"):
        check_upload("awards.pdf", "application/pdf", content)


class _Down:
    async def complete(self, *, system: str, user: str) -> LLMResult:
        raise ModelUnavailable("down")


class _Reply:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    async def complete(self, *, system: str, user: str) -> LLMResult:
        content = json.dumps(self.payload, ensure_ascii=False)
        return LLMResult(content=content, tokens_in=2, tokens_out=4)


async def _login(client: AsyncClient, account: str = "2015200012") -> str:
    response = await client.post("/api/auth/login", json={"account": account, "password": "123456"})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _meta(client: AsyncClient, token: str) -> dict:
    response = await client.get(f"/api/datasets/{AWARD}/meta", headers=_auth(token))
    assert response.status_code == 200, response.text
    return response.json()


def _option(meta: dict, code: str) -> str:
    preferred = "0" if code == "D28" else None
    for item in meta["dicts"][code]:
        if preferred is None or item["value"] == preferred or item["label"] == preferred:
            return item["value"]
    return meta["dicts"][code][0]["value"]


def _award_row(meta: dict, **overrides: str) -> dict[str, str]:
    row: dict[str, str] = {}
    for field in meta["fields"]:
        if field["visible_when"]:
            continue
        code = field["code"]
        if code == meta["owner_field"]:
            row[code] = "2015200012"
        elif code == meta["owner_name_field"]:
            row[code] = "罗胜"
        elif code == meta["department_field"]:
            row[code] = "机械与电子工程系"
        elif field["dict_code"] and field["dict_code"] != "departments":
            row[code] = _option(meta, field["dict_code"])
        elif field["kind"] == "month":
            row[code] = "2024-03"
        elif field["required"]:
            row[code] = "教学成果奖"
        else:
            continue
    row.update(overrides)
    return row


def _xlsx(headers: list[str], rows: list[list[str]]) -> bytes:
    book = Workbook()
    sheet = book.active
    assert sheet is not None
    sheet.append(headers)
    for row in rows:
        sheet.append(row)
    buffer = BytesIO()
    book.save(buffer)
    return buffer.getvalue()


def _docx(text: str) -> bytes:
    document = Document()
    document.add_paragraph(text)
    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _blank_pdf() -> bytes:
    objects = [
        b"1 0 obj<< /Type /Catalog /Pages 2 0 R >>endobj\n",
        b"2 0 obj<< /Type /Pages /Kids [3 0 R] /Count 1 >>endobj\n",
        b"3 0 obj<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>endobj\n",
    ]
    header = b"%PDF-1.4\n"
    offsets = [0]
    body = b""
    cursor = len(header)
    for item in objects:
        offsets.append(cursor)
        body += item
        cursor += len(item)
    xref = [f"xref\n0 {len(offsets)}\n", "0000000000 65535 f \n"]
    xref.extend(f"{offset:010d} 00000 n \n" for offset in offsets[1:])
    trailer = f"trailer<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{cursor}\n%%EOF\n"
    return header + body + "".join(xref).encode() + trailer.encode()


async def _upload(
    client: AsyncClient,
    token: str,
    filename: str,
    content: bytes,
    mime: str,
    prompt: str,
) -> dict:
    response = await client.post(
        "/api/ingestion/tasks",
        headers=_auth(token),
        data={"dataset_code": AWARD, "prompt": prompt},
        files={"file": (filename, content, mime)},
    )
    assert response.status_code == 202, response.text
    return response.json()


async def _candidates(client: AsyncClient, token: str, task_id: str) -> list[dict]:
    response = await client.get(f"/api/ingestion/tasks/{task_id}/candidates", headers=_auth(token))
    assert response.status_code == 200, response.text
    return response.json()


async def _file_count(session: AsyncSession, task_id: str) -> int:
    count = await session.scalar(
        select(func.count()).select_from(IngestFile).where(IngestFile.task_id == task_id)
    )
    return int(count or 0)


async def _ai_count(session: AsyncSession, task_id: str) -> int:
    count = await session.scalar(
        select(func.count())
        .select_from(BizRecord)
        .where(BizRecord.batch_id == task_id, BizRecord.source_type == "ai")
    )
    return int(count or 0)


@pytest.mark.asyncio
async def test_scenario_2_confirms_only_selected_excel_row(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    token = await _login(client)
    meta = await _meta(client, token)
    good = _award_row(meta, HJMC="教学成果奖", HJRQ="2024-03")
    bad = _award_row(meta, HJMC="技能大赛", HJRQ="明年")
    headers = list(good)
    content = _xlsx(headers, [[good[code] for code in headers], [bad[code] for code in headers]])
    created = await _upload(
        client,
        token,
        "awards.xlsx",
        content,
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "提取获奖",
    )
    await run_pipeline(db_session, created["id"])
    rows = await _candidates(client, token, created["id"])
    assert len(rows) == 2
    valid = next(row for row in rows if not row["errors"])
    invalid = next(row for row in rows if row["errors"])
    fixed = dict(invalid["values"])
    fixed["HJRQ"] = "2024-06"
    patched = await client.patch(
        f"/api/ingestion/candidates/{invalid['id']}",
        headers=_auth(token),
        json={"values": fixed},
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["errors"] == []
    confirmed = await client.post(
        f"/api/ingestion/tasks/{created['id']}/confirm",
        headers=_auth(token),
        json={"candidate_ids": [valid["id"]], "submit": False},
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["created"] == 1
    assert confirmed.json()["submitted"] == 0
    record = await db_session.scalar(select(BizRecord).where(BizRecord.batch_id == created["id"]))
    assert record is not None
    assert record.source_type == "ai"
    assert record.source_ref == valid["id"]
    assert record.status == "draft"
    assert await _ai_count(db_session, created["id"]) == 1


async def _seed_task(
    db_session: AsyncSession, token: str, account: str = "2015200012"
) -> IngestTask:
    """直接写入一个待核对的解析任务，避免测试依赖模型服务。"""
    from app.models.system import User

    user = await db_session.scalar(select(User).where(User.account == account))
    assert user is not None
    now = datetime.now(UTC)
    task = IngestTask(
        dataset_code=AWARD,
        created_by=user.id,
        status="pending_confirmation",
        progress=100,
        user_prompt="",
        idempotency_key=f"test-{now.timestamp()}",
        created_at=now,
    )
    db_session.add(task)
    await db_session.commit()
    return task


def _seed_candidate(task: IngestTask, seq: int, values: dict[str, object]) -> IngestCandidate:
    return IngestCandidate(
        task_id=task.id,
        dataset_code=AWARD,
        seq=seq,
        source_location={"sheet": "Sheet1", "row": seq + 1},
        raw_values=values,
        values=values,
        triage="missing",
    )


@pytest.mark.asyncio
async def test_missing_business_key_is_reported_and_blocks_confirm(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    token = await _login(client)
    meta = await _meta(client, token)
    values = _award_row(meta, HJRQ="2024-03")
    values.pop("HJMC")
    task = await _seed_task(db_session, token)
    db_session.add(_seed_candidate(task, 1, values))
    await db_session.commit()

    rows = await _candidates(client, token, task.id)
    assert len(rows) == 1
    assert rows[0]["missing_key"] == ["HJMC"]
    assert rows[0]["errors"] == []

    checked = await client.post(f"/api/ingestion/tasks/{task.id}/reassess", headers=_auth(token))
    assert checked.status_code == 200, checked.text
    body = checked.json()
    assert body["checked"] == 1
    # 缺业务主键的记录即使校验通过也不计入可确认
    assert body["ready"] == 0

    blocked = await client.post(
        f"/api/ingestion/tasks/{task.id}/confirm",
        headers=_auth(token),
        json={"candidate_ids": [rows[0]["id"]], "submit": False},
    )
    assert blocked.status_code == 400
    assert "缺少业务主键：获奖名称" in blocked.json()["detail"]
    assert await _ai_count(db_session, task.id) == 0


@pytest.mark.asyncio
async def test_reassess_recomputes_values_for_pending_candidates(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """重新校验按当前字典与已发布数据重算候选；已生成的记录不再参与。"""
    token = await _login(client)
    meta = await _meta(client, token)
    task = await _seed_task(db_session, token)
    stale = _award_row(meta, HJMC="教学成果奖", HJRQ="2024-03")
    stale["JB"] = "国家级"
    db_session.add(_seed_candidate(task, 1, stale))
    await db_session.commit()

    checked = await client.post(f"/api/ingestion/tasks/{task.id}/reassess", headers=_auth(token))
    assert checked.status_code == 200, checked.text
    body = checked.json()
    assert body["checked"] == 1
    assert body["updated"] == 1

    after = (await _candidates(client, token, task.id))[0]
    # 字典中文名被规范化成编码
    assert after["values"]["JB"] != "国家级"

    confirmed = await client.post(
        f"/api/ingestion/tasks/{task.id}/confirm",
        headers=_auth(token),
        json={"candidate_ids": [after["id"]], "submit": False},
    )
    assert confirmed.status_code == 200, confirmed.text
    again = await client.post(f"/api/ingestion/tasks/{task.id}/reassess", headers=_auth(token))
    assert again.json() == {"checked": 0, "ready": 0, "updated": 0}


@pytest.mark.asyncio
async def test_scenario_3_blank_pdf_does_not_invent_fields(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    token = await _login(client)
    content = _blank_pdf()
    created = await _upload(client, token, "scan.pdf", content, "application/pdf", "")
    await run_pipeline(db_session, created["id"])
    task = await db_session.get(IngestTask, created["id"])
    assert task is not None
    assert task.status == "failed"
    assert task.error_message == SCAN
    assert await _candidates(client, token, created["id"]) == []
    renamed = await client.post(
        "/api/ingestion/tasks",
        headers=_auth(token),
        data={"dataset_code": AWARD, "prompt": "伪装"},
        files={"file": ("awards.pdf", _xlsx(["HJMC"], [["教学成果奖"]]), "application/pdf")},
    )
    assert renamed.status_code == 400
    assert renamed.json()["detail"] == "文件内容与扩展名不一致"


@pytest.mark.asyncio
async def test_scenario_4_invalid_model_output_cannot_be_submitted(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    token = await _login(client)
    meta = await _meta(client, token)
    source = "罗胜申报教学成果奖，获奖日期明年"
    values = _award_row(meta, HJMC="教学成果奖", HJRQ="明年")
    values.pop("HJMC")
    created = await _upload(
        client,
        token,
        "award.docx",
        _docx(source),
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "提取一条",
    )
    await run_pipeline(
        db_session,
        created["id"],
        _Reply({"records": [{"values": values, "evidence": source, "confidence": 0.4}]}),
    )
    rows = await _candidates(client, token, created["id"])
    assert len(rows) == 1
    assert rows[0]["errors"]
    confirmed = await client.post(
        f"/api/ingestion/tasks/{created['id']}/confirm",
        headers=_auth(token),
        json={"candidate_ids": [rows[0]["id"]], "submit": True},
    )
    assert confirmed.status_code == 400
    assert confirmed.json()["detail"] == "存在校验错误或重复记录，不能确认"
    assert await _ai_count(db_session, created["id"]) == 0


@pytest.mark.asyncio
async def test_scenario_8_retry_does_not_duplicate(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    token = await _login(client)
    meta = await _meta(client, token)
    values = _award_row(meta, HJMC="重试后的奖", HJRQ="2024-05")
    source = "；".join(f"{code}：{value}" for code, value in values.items())
    content = _docx(source)
    mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    created = await _upload(client, token, "retry.docx", content, mime, "重试")
    assert created["status"] == "queued"
    assert await enqueue_ingest(created["id"], "redis://127.0.0.1:1") is False
    again = await _upload(client, token, "retry.docx", content, mime, "重试")
    assert again["id"] == created["id"]
    assert await _file_count(db_session, created["id"]) == 1
    await run_pipeline(db_session, created["id"], _Down())
    failed = await db_session.get(IngestTask, created["id"])
    assert failed is not None
    assert failed.error_message == "模型服务暂不可用"
    repeated = await _upload(client, token, "retry.docx", content, mime, "重试")
    assert repeated["id"] == created["id"]
    retried = await client.post(f"/api/ingestion/tasks/{created['id']}/retry", headers=_auth(token))
    assert retried.status_code == 200, retried.text
    assert retried.json()["id"] == created["id"]
    assert retried.json()["status"] == "queued"
    assert await _file_count(db_session, created["id"]) == 1
    await run_pipeline(
        db_session,
        created["id"],
        _Reply({"records": [{"values": values, "evidence": source, "confidence": 0.8}]}),
    )
    rows = await _candidates(client, token, created["id"])
    assert len(rows) == 1
    assert rows[0]["errors"] == []
    first = await client.post(
        f"/api/ingestion/tasks/{created['id']}/confirm",
        headers=_auth(token),
        json={"candidate_ids": [rows[0]["id"]], "submit": False},
    )
    second = await client.post(
        f"/api/ingestion/tasks/{created['id']}/confirm",
        headers=_auth(token),
        json={"candidate_ids": [rows[0]["id"]], "submit": False},
    )
    assert first.status_code == 200 and first.json()["created"] == 1
    assert second.status_code == 200 and second.json()["created"] == 0
    assert await _ai_count(db_session, created["id"]) == 1


@pytest.mark.asyncio
async def test_unexpected_parse_error_is_recorded(
    client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    token = await _login(client)
    created = await _upload(
        client,
        token,
        "broken.xlsx",
        _xlsx(["HJMC"], [["教学成果奖"]]),
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "异常",
    )

    def _boom(_content: bytes) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr("app.ingestion.pipeline.parse_xlsx", _boom)
    await run_pipeline(db_session, created["id"])
    task = await db_session.get(IngestTask, created["id"])
    assert task is not None
    assert task.status == "failed"
    assert task.error_message == "解析过程出现错误"


async def test_stuck_task_is_requeued_then_failed(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    token = await _login(client)
    created = await _upload(
        client,
        token,
        "stuck.docx",
        _docx("卡住"),
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "卡住",
    )
    task = await db_session.get(IngestTask, created["id"])
    assert task is not None
    task.status = "parsing"
    task.attempts = 1
    task.heartbeat_at = datetime.now(UTC) - timedelta(minutes=6)
    ready = await tasks_to_enqueue(db_session)
    assert task.status == "queued"
    assert created["id"] in ready
    task.status = "extracting"
    task.attempts = 3
    task.heartbeat_at = datetime.now(UTC) - timedelta(minutes=6)
    ready = await tasks_to_enqueue(db_session)
    assert task.status == "failed"
    assert task.error_message == "任务长时间无响应"
    assert created["id"] not in ready
