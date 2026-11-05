from io import BytesIO

import pytest
from httpx import AsyncClient
from openpyxl import load_workbook
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.academic import Major
from app.models.records import BizRecord

MAJOR = "ODS_ZYSZSJ"
COURSE = "ODS_KCJBSJ"
TEACHING = "ODS_SKXXSJ"
STUDENT = "ODS_XSJBSJ"
ACADEMIC = {MAJOR, COURSE, TEACHING, STUDENT}


async def _login(client: AsyncClient, account: str, password: str = "123456") -> str:
    response = await client.post("/api/auth/login", json={"account": account, "password": password})
    assert response.status_code == 200, response.text
    token = response.json()["access_token"]
    assert isinstance(token, str)
    return token


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _option(meta: dict, code: str, preferred: str | None = None) -> str:
    for item in meta["dicts"][code]:
        if preferred is not None and (item["value"] == preferred or item["label"] == preferred):
            return item["value"]
    return meta["dicts"][code][0]["value"]


async def _meta(client: AsyncClient, token: str, code: str) -> dict:
    response = await client.get(f"/api/datasets/{code}/meta", headers=_auth(token))
    assert response.status_code == 200, response.text
    return response.json()


def _payload(meta: dict, **overrides: object) -> dict[str, object]:
    body: dict[str, object] = {}
    for field in meta["fields"]:
        if field["visible_when"]:
            body[field["code"]] = None
            continue
        if field["code"] == meta["department_field"]:
            body[field["code"]] = "机械与电子工程系"
        elif field["dict_code"] and field["dict_code"] != "departments":
            preferred = "0" if field["dict_code"] == "D28" else None
            body[field["code"]] = _option(meta, field["dict_code"], preferred)
        elif field["kind"] == "month":
            body[field["code"]] = "2024-09"
        elif field["kind"] == "date":
            body[field["code"]] = "2006-03-07"
        elif field["kind"] == "number":
            body[field["code"]] = 64
        elif field["kind"] == "decimal":
            body[field["code"]] = "16.0"
        elif field["required"]:
            body[field["code"]] = "示例内容"
        else:
            body[field["code"]] = None
    if "D14" in meta["dicts"]:
        body["GGKC"] = _option(meta, "D14")
    if "D15" in meta["dicts"]:
        body["ZYKC"] = _option(meta, "D15")
    if "KKXQM" in body:
        body["KKXQM"] = "2025-2026-1学期"
    if "SKXQM" in body:
        body["SKXQM"] = "2025-2026-1学期"
    if "SJJXKSS" in body:
        body["SJJXKSS"] = 16
    body.update(overrides)
    return body


async def _publish_major(client: AsyncClient, code: str, name: str) -> None:
    center = await _login(client, "admin", "Admin@2026")
    meta = await _meta(client, center, MAJOR)
    payload = _payload(
        meta,
        ZYDM=code,
        ZYMC=name,
        PZSZNY="2020-09",
        SCZSNY="2021-09",
        SYXWLBM=_option(meta, "D03"),
    )
    created = await client.post(
        f"/api/datasets/{MAJOR}/records", headers=_auth(center), json={"payload": payload}
    )
    assert created.status_code == 201, created.text
    submitted = await client.post(
        f"/api/records/{created.json()['id']}/submit", headers=_auth(center)
    )
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["status"] == "published"


@pytest.mark.asyncio
async def test_academic_menus_belong_to_jwc(client: AsyncClient) -> None:
    jwc = await _login(client, "jwc01")
    teacher = await _login(client, "2024020008")
    staff = await _login(client, "2015200012")
    research = await _login(client, "kyc01")

    async def codes(token: str) -> dict[str, dict]:
        response = await client.get("/api/auth/me", headers=_auth(token))
        assert response.status_code == 200, response.text
        return {item["code"]: item for item in response.json()["datasets"]}

    academic = await codes(jwc)
    assert ACADEMIC <= set(academic)
    assert all(
        academic[code]["can_fill"] and academic[code]["category"] == "academic" for code in ACADEMIC
    )
    for token in (teacher, staff, research):
        assert not ACADEMIC & set(await codes(token))


@pytest.mark.asyncio
async def test_major_and_course_association(client: AsyncClient, db_session: AsyncSession) -> None:
    jwc = await _login(client, "jwc01")
    meta = await _meta(client, jwc, MAJOR)
    invalid = _payload(meta, ZYDM="ABC", ZYMC="格式错误专业")
    rejected = await client.post(
        f"/api/datasets/{MAJOR}/records", headers=_auth(jwc), json={"payload": invalid}
    )
    assert rejected.status_code == 400
    assert "专业代码" in rejected.json()["detail"]

    course_meta = await _meta(client, jwc, COURSE)
    missing = _payload(
        course_meta, ZYDM="460301", ZYMC="机电一体化技术", KCH="KC001", KCMC="机械制图"
    )
    blocked = await client.post(
        f"/api/datasets/{COURSE}/records", headers=_auth(jwc), json={"payload": missing}
    )
    assert blocked.status_code == 400
    assert "专业代码尚未发布" in blocked.json()["detail"]

    await _publish_major(client, "460301", "机电一体化技术")
    row = await db_session.scalar(select(Major).where(Major.ZYDM == "460301"))
    assert row is not None and row.ZYMC == "机电一体化技术"


@pytest.mark.asyncio
async def test_course_import_rejects_bad_rows_and_duplicates(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _publish_major(client, "460302", "数控技术")
    jwc = await _login(client, "jwc01")
    teacher = await _login(client, "2024020008")
    denied = await client.get(f"/api/datasets/{COURSE}/template", headers=_auth(teacher))
    assert denied.status_code == 403

    template = await client.get(f"/api/datasets/{COURSE}/template", headers=_auth(jwc))
    assert template.status_code == 200, template.text
    book = load_workbook(BytesIO(template.content))
    sheet = book.active
    columns: dict[str, int] = {}
    for cell in sheet[1]:
        if cell.comment is not None and isinstance(cell.column, int):
            columns[cell.comment.text] = cell.column
    assert columns["KCH"]

    meta = await _meta(client, jwc, COURSE)
    good = _payload(
        meta, ZYDM="460302", ZYMC="数控技术", KCH="KC100", KCMC="数控编程", NJ=_option(meta, "D11")
    )
    bad = dict(good)
    bad["KKXQM"] = "第一学期"
    duplicate = dict(good)
    for row_number, payload in ((2, bad), (3, good), (4, duplicate)):
        for code, value in payload.items():
            sheet.cell(row_number, columns[code], value)
    buffer = BytesIO()
    book.save(buffer)

    preview = await client.post(
        f"/api/datasets/{COURSE}/imports",
        headers=_auth(jwc),
        files={
            "file": (
                "course.xlsx",
                buffer.getvalue(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert preview.status_code == 200, preview.text
    rows = {item["row"]: item for item in preview.json()}
    assert rows[2]["ok"] is False
    assert "开课学期" in rows[2]["errors"][0]
    assert rows[3]["ok"] is True
    assert rows[4]["ok"] is False
    assert "重复" in rows[4]["errors"][0]

    committed = await client.post(
        f"/api/datasets/{COURSE}/imports/commit",
        headers=_auth(jwc),
        json={"payloads": [rows[3]["payload"]], "submit": True},
    )
    assert committed.status_code == 200, committed.text
    assert committed.json() == {"created": 1, "submitted": 1}
    record = await db_session.scalar(
        select(BizRecord).where(BizRecord.dataset_code == COURSE, BizRecord.deleted_at.is_(None))
    )
    assert record is not None
    assert record.status == "pending_center"
    assert record.source_type == "excel"

    again = await client.post(
        f"/api/datasets/{COURSE}/imports",
        headers=_auth(jwc),
        files={
            "file": (
                "course.xlsx",
                buffer.getvalue(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert again.status_code == 200, again.text
    second = {item["row"]: item for item in again.json()}
    assert second[3]["ok"] is False
    assert "业务主键重复" in second[3]["errors"][0]
    total = await db_session.scalar(
        select(func.count())
        .select_from(BizRecord)
        .where(BizRecord.dataset_code == COURSE, BizRecord.deleted_at.is_(None))
    )
    assert total == 1

    staff = await _login(client, "2015200012")
    hidden = await client.get(f"/api/datasets/{COURSE}/records", headers=_auth(staff))
    assert hidden.status_code == 200, hidden.text
    assert hidden.json()["total"] == 0
    detail = await client.get(f"/api/records/{record.id}", headers=_auth(staff))
    assert detail.status_code == 404


@pytest.mark.asyncio
async def test_teaching_and_student_require_published_major(client: AsyncClient) -> None:
    jwc = await _login(client, "jwc01")
    teaching = _payload(
        await _meta(client, jwc, TEACHING),
        JGH="2024020008",
        JSXM="谭元霸",
        ZYDM="460303",
        ZYMC="未发布专业",
        KCH="KC9",
        KCMC="未发布课程",
        BJMC="数控1班",
    )
    blocked = await client.post(
        f"/api/datasets/{TEACHING}/records", headers=_auth(jwc), json={"payload": teaching}
    )
    assert blocked.status_code == 400
    assert "课程尚未发布" in blocked.json()["detail"]

    student = _payload(
        await _meta(client, jwc, STUDENT),
        XH="202401001",
        XSXM="张三",
        ZYDM="460303",
        ZYMC="未发布专业",
        SFZJH="G12345678",
    )
    rejected = await client.post(
        f"/api/datasets/{STUDENT}/records", headers=_auth(jwc), json={"payload": student}
    )
    assert rejected.status_code == 400
    assert "专业代码尚未发布" in rejected.json()["detail"]


@pytest.mark.asyncio
async def test_only_center_can_revise_published_academic_record(client: AsyncClient) -> None:
    """教务处（业务部门审核员）不能把信息中心审核发布的记录撤成草稿。"""
    jwc = await _login(client, "jwc01")
    center = await _login(client, "admin", "Admin@2026")
    meta = await _meta(client, jwc, MAJOR)
    payload = _payload(
        meta,
        ZYDM="640199",
        ZYMC="发布权限校验专业",
        PZSZNY="2020-09",
        SCZSNY="2021-09",
        SYXWLBM=_option(meta, "D03"),
    )
    created = await client.post(
        f"/api/datasets/{MAJOR}/records", headers=_auth(jwc), json={"payload": payload}
    )
    assert created.status_code == 201, created.text
    record_id = created.json()["id"]
    submitted = await client.post(f"/api/records/{record_id}/submit", headers=_auth(jwc))
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["status"] == "pending_center"
    published = await client.post(
        f"/api/records/{record_id}/review",
        headers=_auth(center),
        json={"decision": "approve", "comment": "信息中心发布"},
    )
    assert published.status_code == 200, published.text
    assert published.json()["status"] == "published"

    denied = await client.post(f"/api/records/{record_id}/revise", headers=_auth(jwc))
    assert denied.status_code == 403
    assert "信息中心" in denied.json()["detail"]

    listing = await client.get(
        f"/api/datasets/{MAJOR}/records?keyword=640199&page_size=50", headers=_auth(center)
    )
    assert listing.status_code == 200, listing.text
    item = next(row for row in listing.json()["items"] if row["id"] == record_id)
    assert item["can_revise"] is True

    revised = await client.post(f"/api/records/{record_id}/revise", headers=_auth(center))
    assert revised.status_code == 200, revised.text
    assert revised.json()["status"] == "draft"
