"""M5.5：批次上传、分诊、缺失补填与宽松草稿。"""

from io import BytesIO

from httpx import AsyncClient
from openpyxl import Workbook
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion.pipeline import run_pipeline
from app.models.records import BizRecord

AWARD = "ODS_JSHJSJ"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


async def _login(client: AsyncClient, account: str = "2015200012") -> str:
    response = await client.post("/api/auth/login", json={"account": account, "password": "123456"})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _option(meta: dict, code: str) -> str:
    for item in meta["dicts"][code]:
        if item["value"] == "0" or item["label"] == "否":
            return item["value"]
    return meta["dicts"][code][0]["value"]


def _award_row(meta: dict) -> dict[str, str]:
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
    return row


def _xlsx(row: dict[str, str]) -> bytes:
    book = Workbook()
    sheet = book.active
    assert sheet is not None
    headers = list(row)
    sheet.append(headers)
    sheet.append([row[code] for code in headers])
    buffer = BytesIO()
    book.save(buffer)
    return buffer.getvalue()


async def test_batch_upload_triage_gaps_and_lenient_draft(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    token = await _login(client)
    meta = (await client.get(f"/api/datasets/{AWARD}/meta", headers=_auth(token))).json()
    batch = await client.post(
        "/api/ingestion/batches",
        headers=_auth(token),
        json={"dataset_codes": [AWARD], "title": "获奖批量填报"},
    )
    assert batch.status_code == 200, batch.text
    batch_id = batch.json()["id"]
    created = await client.post(
        f"/api/ingestion/batches/{batch_id}/files",
        headers=_auth(token),
        data={"dataset_code": AWARD},
        files={"file": ("awards.xlsx", _xlsx(_award_row(meta)), XLSX)},
    )
    assert created.status_code == 202, created.text
    task_id = created.json()["id"]
    await run_pipeline(db_session, task_id)

    task = await client.get(f"/api/ingestion/tasks/{task_id}", headers=_auth(token))
    assert task.json()["plan_source"] in {"exact", "template"}
    plan = await client.get(f"/api/ingestion/tasks/{task_id}/plan", headers=_auth(token))
    assert plan.json()["profile"]["sheets"]
    assert plan.json()["dry_run"]["rows"] == 1

    candidates = await client.get(
        f"/api/ingestion/batches/{batch_id}/candidates", headers=_auth(token)
    )
    rows = candidates.json()
    assert len(rows) == 1
    row = rows[0]
    assert row["batch_id"] == batch_id
    assert row["completeness"] > 0
    assert len(row["field_sources"]) > 0
    assert row["field_sources"]["HJMC"]["source"] == "file"
    assert row["triage"] in {"auto", "review"}

    broken = dict(row["values"])
    broken["BJDWMC"] = ""
    patched = await client.patch(
        f"/api/ingestion/candidates/{row['id']}",
        headers=_auth(token),
        json={"values": broken},
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["triage"] == "missing"
    assert patched.json()["completeness"] < row["completeness"]

    gaps = await client.get(f"/api/ingestion/batches/{batch_id}/gaps", headers=_auth(token))
    assert gaps.status_code == 200, gaps.text
    assert any(item["code"] == "BJDWMC" and item["reason"] == "missing" for item in gaps.json())

    confirmed = await client.post(
        f"/api/ingestion/batches/{batch_id}/confirm",
        headers=_auth(token),
        json={"candidate_ids": [row["id"]], "submit": False},
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["created"] == 1
    record = await db_session.scalar(select(BizRecord).where(BizRecord.source_ref == row["id"]))
    assert record is not None
    assert record.status == "draft"
    assert record.source_type == "ai"
    assert record.batch_id == batch_id
    assert record.field_sources
    assert record.completeness == patched.json()["completeness"]

    submitted = await client.post(f"/api/records/{record.id}/submit", headers=_auth(token))
    assert submitted.status_code == 400
    detail = await client.get(f"/api/ingestion/batches/{batch_id}", headers=_auth(token))
    assert detail.status_code == 200, detail.text
    assert detail.json()["batch"]["status"] == "completed"


async def test_two_files_in_batch_merge_by_business_key(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    token = await _login(client)
    meta = (await client.get(f"/api/datasets/{AWARD}/meta", headers=_auth(token))).json()
    batch = await client.post(
        "/api/ingestion/batches",
        headers=_auth(token),
        json={"dataset_codes": [AWARD]},
    )
    batch_id = batch.json()["id"]
    content = _xlsx(_award_row(meta))
    for prompt in ("第一份", "第二份"):
        response = await client.post(
            f"/api/ingestion/batches/{batch_id}/files",
            headers=_auth(token),
            data={"dataset_code": AWARD, "prompt": prompt},
            files={"file": ("awards.xlsx", content, XLSX)},
        )
        assert response.status_code == 202, response.text
        await run_pipeline(db_session, response.json()["id"])
    rows = (
        await client.get(f"/api/ingestion/batches/{batch_id}/candidates", headers=_auth(token))
    ).json()
    assert len(rows) == 1
    assert rows[0]["batch_id"] == batch_id
    confirmed = await client.post(
        f"/api/ingestion/batches/{batch_id}/confirm",
        headers=_auth(token),
        json={"candidate_ids": [rows[0]["id"]], "submit": False},
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["created"] == 1


async def test_bulk_update_applies_same_value(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    token = await _login(client)
    meta = (await client.get(f"/api/datasets/{AWARD}/meta", headers=_auth(token))).json()
    first = _award_row(meta)
    second = {**_award_row(meta), "HJMC": "技能大赛"}
    book = Workbook()
    sheet = book.active
    assert sheet is not None
    headers = list(first)
    sheet.append(headers)
    sheet.append([first[code] for code in headers])
    sheet.append([second[code] for code in headers])
    buffer = BytesIO()
    book.save(buffer)
    created = await client.post(
        "/api/ingestion/tasks",
        headers=_auth(token),
        data={"dataset_code": AWARD, "prompt": "批量改"},
        files={"file": ("awards.xlsx", buffer.getvalue(), XLSX)},
    )
    assert created.status_code == 202, created.text
    await run_pipeline(db_session, created.json()["id"])
    rows = (
        await client.get(
            f"/api/ingestion/tasks/{created.json()['id']}/candidates", headers=_auth(token)
        )
    ).json()
    assert len(rows) == 2
    ids = [row["id"] for row in rows]
    response = await client.post(
        "/api/ingestion/candidates/bulk",
        headers=_auth(token),
        json={"candidate_ids": ids, "values": {"HJRQ": "2024-06"}},
    )
    assert response.status_code == 200, response.text
    assert all(item["values"]["HJRQ"] == "2024-06" for item in response.json())


async def test_delete_task_requires_purge_when_drafts_exist(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    token = await _login(client)
    meta = (await client.get(f"/api/datasets/{AWARD}/meta", headers=_auth(token))).json()
    created = await client.post(
        "/api/ingestion/tasks",
        headers=_auth(token),
        data={"dataset_code": AWARD},
        files={"file": ("awards.xlsx", _xlsx(_award_row(meta)), XLSX)},
    )
    assert created.status_code == 202, created.text
    task_id = created.json()["id"]
    await run_pipeline(db_session, task_id)
    rows = (
        await client.get(f"/api/ingestion/tasks/{task_id}/candidates", headers=_auth(token))
    ).json()
    confirmed = await client.post(
        f"/api/ingestion/tasks/{task_id}/confirm",
        headers=_auth(token),
        json={"candidate_ids": [rows[0]["id"]], "submit": False},
    )
    assert confirmed.status_code == 200, confirmed.text
    record = await db_session.scalar(select(BizRecord).where(BizRecord.source_ref == rows[0]["id"]))
    assert record is not None

    blocked = await client.delete(f"/api/ingestion/tasks/{task_id}", headers=_auth(token))
    assert blocked.status_code == 400
    assert "草稿" in blocked.json()["detail"]

    purged = await client.delete(
        f"/api/ingestion/tasks/{task_id}?purge_records=true", headers=_auth(token)
    )
    assert purged.status_code == 200, purged.text
    assert purged.json() == {"deleted_tasks": 1, "cleared_records": 1}

    db_session.expire_all()
    assert await db_session.get(BizRecord, record.id) is None
    gone = await client.get(f"/api/ingestion/tasks/{task_id}", headers=_auth(token))
    assert gone.status_code == 404
    candidates = await client.get(
        f"/api/ingestion/tasks/{task_id}/candidates", headers=_auth(token)
    )
    assert candidates.status_code == 404


async def test_delete_batch_removes_tasks_and_candidates(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    token = await _login(client)
    meta = (await client.get(f"/api/datasets/{AWARD}/meta", headers=_auth(token))).json()
    batch = await client.post(
        "/api/ingestion/batches",
        headers=_auth(token),
        json={"dataset_codes": [AWARD], "title": "待删除批次"},
    )
    batch_id = batch.json()["id"]
    created = await client.post(
        f"/api/ingestion/batches/{batch_id}/files",
        headers=_auth(token),
        data={"dataset_code": AWARD},
        files={"file": ("awards.xlsx", _xlsx(_award_row(meta)), XLSX)},
    )
    assert created.status_code == 202, created.text
    task_id = created.json()["id"]
    await run_pipeline(db_session, task_id)

    removed = await client.delete(f"/api/ingestion/batches/{batch_id}", headers=_auth(token))
    assert removed.status_code == 200, removed.text
    assert removed.json() == {"deleted_tasks": 1, "cleared_records": 0}

    assert (
        await client.get(f"/api/ingestion/batches/{batch_id}", headers=_auth(token))
    ).status_code == 404
    assert (
        await client.get(f"/api/ingestion/tasks/{task_id}", headers=_auth(token))
    ).status_code == 404
