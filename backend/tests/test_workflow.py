from dataclasses import replace

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.datasets.access import review_steps
from app.datasets.staff import staff_dataset
from app.models.staff import StaffMember
from app.services.staff_rules import id_card_birth_gender
from tests.test_staff_rules import valid_id

CODE = "ODS_JZGJBSJ"


def test_review_steps_follow_filler_and_domain() -> None:
    staff = staff_dataset()
    assert review_steps(staff, "teacher") == ["pending_dept", "pending_domain", "pending_center"]
    assert review_steps(staff, "department") == ["pending_domain", "pending_center"]
    assert review_steps(staff, "domain") == ["pending_center"]
    assert review_steps(staff, "center") == []

    award = replace(staff, code="ODS_JSHJSJ", review_department="owner_department")
    assert review_steps(award, "teacher") == ["pending_dept", "pending_center"]
    assert review_steps(award, "department") == ["pending_center"]
    assert review_steps(award, "center") == []


async def _login(client: AsyncClient, account: str, password: str = "123456") -> str:
    response = await client.post("/api/auth/login", json={"account": account, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _option(meta: dict, code: str, preferred: str | None = None) -> str:
    options = meta["dicts"][code]
    if preferred is not None:
        for item in options:
            if item["value"] == preferred or item["label"] == preferred:
                return item["value"]
    return options[0]["value"]


async def _staff_payload(client: AsyncClient, token: str, staff_no: str, name: str) -> dict:
    meta = await client.get(f"/api/datasets/{CODE}/meta", headers=_auth(token))
    assert meta.status_code == 200, meta.text
    body = meta.json()
    identity = valid_id(order="013" if staff_no.endswith("8") else "011")
    birth, gender, errors = id_card_birth_gender(identity)
    assert errors == []
    assert birth is not None and gender is not None
    return {
        "JGH": staff_no,
        "JSXM": name,
        "XB": gender,
        "SFZJH": identity,
        "CSRQ": birth,
        "ZZMM": _option(body, "D21"),
        "MZ": _option(body, "D22"),
        "XL": _option(body, "D23"),
        "XW": _option(body, "D24"),
        "BYXXGJDQ": _option(body, "D63"),
        "BYXXMC": "贵州大学",
        "YXBMCMC": "机械与电子工程系",
        "RYLB": _option(body, "D19"),
        "SRZW": "教师",
        "ZYLY": _option(body, "D25"),
        "ZYTC": "软件",
        "SFYGXJSZGZS": _option(body, "D28", "0"),
        "SFZYJS": _option(body, "D28", "0"),
        "SFGGKJS": _option(body, "D28", "0"),
        "SFSZXJS": _option(body, "D29", "否"),
        "JXMS": _option(body, "D30", "否"),
        "SFZZSZKJS": _option(body, "D28", "0"),
        "SFJZSZKJS": _option(body, "D28", "0"),
        "SFZZFDY": _option(body, "D28", "0"),
        "SFJZFDY": _option(body, "D28", "0"),
        "SFZZXLJKJS": _option(body, "D28", "0"),
        "SFJZXLJKJS": _option(body, "D28", "0"),
        "SFZYDTR": _option(body, "D31", "否"),
        "ZYDTNX": 0,
        "SFZYQFZR": _option(body, "D32", "否"),
        "ZYQFZRNX": 0,
        "CZHYQYGZNX": "1.0",
    }


async def _create(client: AsyncClient, token: str, payload: dict) -> dict:
    response = await client.post(
        f"/api/datasets/{CODE}/records",
        headers=_auth(token),
        json={"payload": payload},
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.asyncio
async def test_staff_review_pipeline_and_republish(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    teacher = await _login(client, "2024020008")
    staff = await _login(client, "2015200012")
    domain = await _login(client, "zzrsb01")
    center = await _login(client, "admin", "Admin@2026")
    payload = await _staff_payload(client, teacher, "2024020008", "谭元霸")
    created = await _create(client, teacher, payload)
    record_id = created["id"]
    assert created["status"] == "draft"
    assert "****" not in created["payload"]["SFZJH"]

    submitted = await client.post(f"/api/records/{record_id}/submit", headers=_auth(teacher))
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["status"] == "pending_dept"
    masked = await client.get(f"/api/records/{record_id}", headers=_auth(domain))
    assert masked.status_code == 200
    assert "*" in masked.json()["payload"]["SFZJH"]

    withdrawn = await client.post(f"/api/records/{record_id}/withdraw", headers=_auth(teacher))
    assert withdrawn.json()["status"] == "draft"
    submitted = await client.post(f"/api/records/{record_id}/submit", headers=_auth(teacher))
    assert submitted.json()["status"] == "pending_dept"

    returned = await client.post(
        f"/api/records/{record_id}/review",
        headers=_auth(staff),
        json={"decision": "return", "comment": "专业特长请写具体方向"},
    )
    assert returned.status_code == 200, returned.text
    assert returned.json()["status"] == "returned"

    payload["ZYTC"] = "工业软件"
    updated = await client.put(
        f"/api/records/{record_id}", headers=_auth(teacher), json={"payload": payload}
    )
    assert updated.status_code == 200, updated.text
    resubmitted = await client.post(f"/api/records/{record_id}/submit", headers=_auth(teacher))
    assert resubmitted.json()["status"] == "pending_dept"

    own = await client.post(
        f"/api/records/{record_id}/review",
        headers=_auth(teacher),
        json={"decision": "approve", "comment": ""},
    )
    assert own.status_code == 403

    dept = await client.post(
        f"/api/records/{record_id}/review",
        headers=_auth(staff),
        json={"decision": "approve", "comment": "系部通过"},
    )
    assert dept.json()["status"] == "pending_domain"
    domain_pass = await client.post(
        f"/api/records/{record_id}/review",
        headers=_auth(domain),
        json={"decision": "approve", "comment": "人事通过"},
    )
    assert domain_pass.json()["status"] == "pending_center"
    published = await client.post(
        f"/api/records/{record_id}/review",
        headers=_auth(center),
        json={"decision": "approve", "comment": "发布"},
    )
    assert published.status_code == 200, published.text
    assert published.json()["status"] == "published"
    assert published.json()["published_version"] == 1
    ods_id = published.json()["ods_id"]
    row = await db_session.get(StaffMember, ods_id)
    assert row is not None
    assert row.JGH == "2024020008"
    assert row.ZYTC == "工业软件"

    forbidden = await client.post(f"/api/records/{record_id}/revise", headers=_auth(teacher))
    assert forbidden.status_code == 403
    listed = await client.get(
        f"/api/datasets/{CODE}/records?keyword=2024020008&page_size=50",
        headers=_auth(teacher),
    )
    assert listed.status_code == 200, listed.text
    items = {item["id"]: item for item in listed.json()["items"]}
    assert items[record_id]["can_revise"] is False
    revised = await client.post(f"/api/records/{record_id}/revise", headers=_auth(center))
    assert revised.status_code == 200, revised.text
    assert revised.json()["status"] == "draft"
    payload["ZYTC"] = "工业控制软件"
    await client.put(f"/api/records/{record_id}", headers=_auth(teacher), json={"payload": payload})
    await client.post(f"/api/records/{record_id}/submit", headers=_auth(teacher))
    skipped = await client.post(
        f"/api/records/{record_id}/publish",
        headers=_auth(center),
        json={"comment": "信息中心跳级发布修订稿"},
    )
    assert skipped.status_code == 200, skipped.text
    assert skipped.json()["published_version"] == 2
    assert skipped.json()["ods_id"] == ods_id
    await db_session.refresh(row)
    assert row.ZYTC == "工业控制软件"
    total = await db_session.scalar(
        select(func.count()).select_from(StaffMember).where(StaffMember.JGH == "2024020008")
    )
    assert total == 1


@pytest.mark.asyncio
async def test_center_skip_publish_requires_comment(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    teacher = await _login(client, "2024020008")
    center = await _login(client, "admin", "Admin@2026")
    payload = await _staff_payload(client, teacher, "2024020008", "谭元霸")
    created = await _create(client, teacher, payload)
    record_id = created["id"]
    await client.post(f"/api/records/{record_id}/submit", headers=_auth(teacher))
    missing = await client.post(
        f"/api/records/{record_id}/publish", headers=_auth(center), json={"comment": ""}
    )
    assert missing.status_code == 422
    published = await client.post(
        f"/api/records/{record_id}/publish",
        headers=_auth(center),
        json={"comment": "跳过系部和人事，直接发布"},
    )
    assert published.status_code == 200, published.text
    assert published.json()["status"] == "published"
    events = await client.get(f"/api/records/{record_id}/events", headers=_auth(center))
    assert any(item["action"] == "skip_publish" for item in events.json())
    total = await db_session.scalar(
        select(func.count()).select_from(StaffMember).where(StaffMember.JGH == "2024020008")
    )
    assert total == 1


@pytest.mark.asyncio
async def test_visibility_and_foreign_auditor(client: AsyncClient) -> None:
    teacher = await _login(client, "2024020008")
    staff = await _login(client, "2015200012")
    research = await _login(client, "kyc01")
    denied = await client.post(
        f"/api/datasets/{CODE}/records",
        headers=_auth(research),
        json={"payload": {}},
    )
    assert denied.status_code == 403

    own = await _create(client, staff, await _staff_payload(client, staff, "2015200012", "罗胜"))
    hidden = await client.get(f"/api/records/{own['id']}", headers=_auth(teacher))
    assert hidden.status_code == 404
    visible = await client.get(f"/api/records/{own['id']}", headers=_auth(staff))
    assert visible.status_code == 200


@pytest.mark.asyncio
async def test_batch_submit_and_withdraw_report_each_failure(client: AsyncClient) -> None:
    teacher = await _login(client, "2024020008")
    staff = await _login(client, "2015200012")
    draft = await _create(
        client, teacher, await _staff_payload(client, teacher, "2024020008", "谭元霸")
    )
    foreign = await _create(
        client, staff, await _staff_payload(client, staff, "2015200012", "罗胜")
    )

    submitted = await client.post(
        "/api/records/batch",
        headers=_auth(teacher),
        json={"action": "submit", "ids": [draft["id"], foreign["id"], "missing"]},
    )
    assert submitted.status_code == 200, submitted.text
    body = submitted.json()
    assert body["done"] == 1
    assert {item["id"] for item in body["failed"]} == {foreign["id"], "missing"}
    detail = await client.get(f"/api/records/{draft['id']}", headers=_auth(teacher))
    assert detail.json()["status"] == "pending_dept"

    again = await client.post(
        "/api/records/batch",
        headers=_auth(teacher),
        json={"action": "submit", "ids": [draft["id"]]},
    )
    assert again.json() == {
        "done": 0,
        "failed": [{"id": draft["id"], "reason": "当前状态不能提交"}],
    }

    withdrawn = await client.post(
        "/api/records/batch",
        headers=_auth(teacher),
        json={"action": "withdraw", "ids": [draft["id"]]},
    )
    assert withdrawn.json() == {"done": 1, "failed": []}
    detail = await client.get(f"/api/records/{draft['id']}", headers=_auth(teacher))
    assert detail.json()["status"] == "draft"


@pytest.mark.asyncio
async def test_batch_review_from_dataset_list(client: AsyncClient) -> None:
    teacher = await _login(client, "2024020008")
    staff = await _login(client, "2015200012")
    center = await _login(client, "admin", "Admin@2026")
    early = await _create(
        client, teacher, await _staff_payload(client, teacher, "2024020008", "谭元霸")
    )
    late = await _create(client, staff, await _staff_payload(client, staff, "2015200012", "罗胜"))
    await client.post(
        "/api/records/batch",
        headers=_auth(teacher),
        json={"action": "submit", "ids": [early["id"]]},
    )
    await client.post(
        "/api/records/batch", headers=_auth(staff), json={"action": "submit", "ids": [late["id"]]}
    )

    listed = await client.get(
        f"/api/datasets/{CODE}/records",
        headers=_auth(center),
        params={"status": "pending_dept,pending_domain,pending_center"},
    )
    flags = {item["id"]: item["can_review"] for item in listed.json()["items"]}
    assert flags == {early["id"]: True, late["id"]: True}
    own_view = await client.get(f"/api/datasets/{CODE}/records", headers=_auth(teacher))
    assert all(not item["can_review"] for item in own_view.json()["items"])

    blank = await client.post(
        "/api/records/batch",
        headers=_auth(center),
        json={"action": "return", "ids": [early["id"]]},
    )
    assert blank.status_code == 400
    returned = await client.post(
        "/api/records/batch",
        headers=_auth(center),
        json={"action": "return", "ids": [early["id"]], "comment": "请补充学历证明"},
    )
    assert returned.json() == {"done": 1, "failed": []}

    approved = await client.post(
        "/api/records/batch",
        headers=_auth(center),
        json={"action": "approve", "ids": [early["id"], late["id"]]},
    )
    body = approved.json()
    assert body["done"] == 1
    assert [item["id"] for item in body["failed"]] == [early["id"]]
    detail = await client.get(f"/api/records/{late['id']}", headers=_auth(center))
    assert detail.json()["status"] == "published"
    events = await client.get(f"/api/records/{late['id']}/events", headers=_auth(center))
    assert events.json()[-1]["comment"] == "信息中心批量审核发布"

    await client.post(
        "/api/records/batch",
        headers=_auth(teacher),
        json={"action": "submit", "ids": [early["id"]]},
    )
    dept = await client.post(
        "/api/records/batch",
        headers=_auth(staff),
        json={"action": "approve", "ids": [early["id"]]},
    )
    assert dept.json() == {"done": 1, "failed": []}
    detail = await client.get(f"/api/records/{early['id']}", headers=_auth(staff))
    assert detail.json()["status"] == "pending_domain"
