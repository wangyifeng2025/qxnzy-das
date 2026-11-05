import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.datasets.access import review_steps
from app.datasets.teacher import award_dataset
from app.models.system import AuditLog, Department, Role, User, UserStatus
from app.models.teacher_activity import TeacherAward, TeacherTraining

TRAINING = "ODS_XXJXSJ"


def test_award_review_skips_functional_department() -> None:
    award = award_dataset()
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
    for item in meta["dicts"][code]:
        if preferred is not None and (item["value"] == preferred or item["label"] == preferred):
            return item["value"]
    return meta["dicts"][code][0]["value"]


async def _meta(client: AsyncClient, token: str, code: str) -> dict:
    response = await client.get(f"/api/datasets/{code}/meta", headers=_auth(token))
    assert response.status_code == 200, response.text
    return response.json()


def _payload(meta: dict, owner: str, name: str, **overrides: object) -> dict:
    body: dict[str, object] = {}
    for field in meta["fields"]:
        if field["visible_when"]:
            body[field["code"]] = None
            continue
        if field["code"] == meta["owner_field"]:
            body[field["code"]] = owner
        elif field["code"] == meta["owner_name_field"]:
            body[field["code"]] = name
        elif field["code"] == meta["department_field"]:
            body[field["code"]] = "机械与电子工程系"
        elif field["dict_code"] and field["dict_code"] != "departments":
            preferred = "0" if field["dict_code"] == "D28" else None
            body[field["code"]] = _option(meta, field["dict_code"], preferred)
        elif field["kind"] == "month":
            body[field["code"]] = "2024-03" if field["required"] else None
        elif field["kind"] == "number":
            body[field["code"]] = 2
        elif field["kind"] == "decimal":
            body[field["code"]] = "1.5000"
        elif field["required"]:
            body[field["code"]] = "示例内容"
        else:
            body[field["code"]] = None
    body.update(overrides)
    return body


async def _codes(client: AsyncClient, token: str) -> dict[str, dict]:
    response = await client.get("/api/auth/me", headers=_auth(token))
    assert response.status_code == 200, response.text
    return {item["code"]: item for item in response.json()["datasets"]}


@pytest.mark.asyncio
async def test_domain_menus_follow_review_department(client: AsyncClient) -> None:
    teacher = await _codes(client, await _login(client, "2024020008"))
    personnel = await _codes(client, await _login(client, "zzrsb01"))
    research = await _codes(client, await _login(client, "kyc01"))
    academic = await _codes(client, await _login(client, "jwc01"))
    teacher_codes = {
        "ODS_JZGJBSJ",
        TRAINING,
        "ODS_JSHJSJ",
        "ODS_LWZZSJ",
        "ODS_KYXMJBSJ",
        "ODS_HXKTSJ",
        "ODS_JSQYJZSJSJ",
        "ODS_ZSCQSJ",
    }
    assert teacher_codes <= set(teacher)
    assert all(teacher[code]["can_fill"] for code in teacher_codes)
    assert personnel[TRAINING]["can_fill"] and personnel[TRAINING]["can_review"]
    assert "ODS_LWZZSJ" not in personnel
    assert research["ODS_LWZZSJ"]["can_fill"] and research["ODS_KYXMJBSJ"]["can_review"]
    assert TRAINING not in research
    assert "ODS_JSHJSJ" not in research
    assert not academic.keys() & teacher_codes


@pytest.mark.asyncio
async def test_training_publish_and_validation_hooks(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    teacher = await _login(client, "2024020008")
    meta = await _meta(client, teacher, TRAINING)
    payload = _payload(meta, "2024020008", "谭元霸", JXPXMC="骨干教师培训", JXPXDD="贵阳")
    created = await client.post(
        f"/api/datasets/{TRAINING}/records",
        headers=_auth(teacher),
        json={"payload": payload},
    )
    assert created.status_code == 201, created.text
    record_id = created.json()["id"]
    assert created.json()["status"] == "draft"

    payload["PXTS"] = 0
    rejected = await client.put(
        f"/api/records/{record_id}", headers=_auth(teacher), json={"payload": payload}
    )
    assert rejected.status_code == 400
    assert "时长" in rejected.json()["detail"]

    payload["PXTS"] = 3
    saved = await client.put(
        f"/api/records/{record_id}", headers=_auth(teacher), json={"payload": payload}
    )
    assert saved.status_code == 200, saved.text
    submitted = await client.post(f"/api/records/{record_id}/submit", headers=_auth(teacher))
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["status"] == "pending_dept"

    center = await _login(client, "admin", "Admin@2026")
    published = await client.post(
        f"/api/records/{record_id}/publish",
        headers=_auth(center),
        json={"comment": "培训记录跳级发布"},
    )
    assert published.status_code == 200, published.text
    row = await db_session.get(TeacherTraining, published.json()["ods_id"])
    assert row is not None
    assert row.JXPXMC == "骨干教师培训"
    assert row.PXTS == 3


@pytest.mark.asyncio
async def test_conditional_hooks_reject_incomplete_records(client: AsyncClient) -> None:
    teacher = await _login(client, "2024020008")
    cases = [
        ("ODS_JSHJSJ", {"SFXQHZ": "1", "HZQYMC": None}, "合作企业"),
        ("ODS_KYXMJBSJ", {"LXRQ": "2024-06", "JXRQ": "2024-01"}, "结项日期"),
        ("ODS_HXKTSJ", {"BXNDKJE": "3", "LJDKJE": "1"}, "累计到账"),
        ("ODS_ZSCQSJ", {"ZRXKJE": "10", "SRFMC": None, "ZRXKRQ": None}, "受让方"),
    ]
    for code, overrides, message in cases:
        meta = await _meta(client, teacher, code)
        payload = _payload(meta, "2024020008", "谭元霸", **overrides)
        response = await client.post(
            f"/api/datasets/{code}/records",
            headers=_auth(teacher),
            json={"payload": payload},
        )
        assert response.status_code == 400, response.text
        assert message in response.json()["detail"]


@pytest.mark.asyncio
async def test_department_award_skips_to_center(client: AsyncClient) -> None:
    staff = await _login(client, "2015200012")
    meta = await _meta(client, staff, "ODS_JSHJSJ")
    payload = _payload(
        meta,
        "2024020008",
        "谭元霸",
        HJMC="教学能力大赛",
        HJRQ="2024-05",
    )
    created = await client.post(
        "/api/datasets/ODS_JSHJSJ/records",
        headers=_auth(staff),
        json={"payload": payload},
    )
    assert created.status_code == 201, created.text
    submitted = await client.post(
        f"/api/records/{created.json()['id']}/submit", headers=_auth(staff)
    )
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["status"] == "pending_center"


@pytest.mark.asyncio
async def test_teacher_cannot_see_colleague_and_sensitive_export_is_audited(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    department = await db_session.scalar(select(Department).where(Department.code == "BM04"))
    role = await db_session.scalar(select(Role).where(Role.code == "teacher"))
    assert department is not None and role is not None
    colleague = User(
        account="2024990001",
        name="测试教师",
        password_hash=hash_password("123456"),
        status=UserStatus.ACTIVE,
    )
    colleague.department = department
    colleague.roles = [role]
    db_session.add(colleague)
    await db_session.flush()

    owner = await _login(client, "2024990001")
    meta = await _meta(client, owner, TRAINING)
    created = await client.post(
        f"/api/datasets/{TRAINING}/records",
        headers=_auth(owner),
        json={
            "payload": _payload(meta, "2024990001", "测试教师", JXPXMC="同事项目", JXPXDD="兴义")
        },
    )
    assert created.status_code == 201, created.text
    record_id = created.json()["id"]

    teacher = await _login(client, "2024020008")
    hidden = await client.get(f"/api/records/{record_id}", headers=_auth(teacher))
    assert hidden.status_code == 404
    listed = await client.get(f"/api/datasets/{TRAINING}/records", headers=_auth(teacher))
    assert listed.status_code == 200
    assert all(item["id"] != record_id for item in listed.json()["items"])
    exported = await client.get(f"/api/datasets/{TRAINING}/export", headers=_auth(teacher))
    assert exported.status_code == 200
    assert "同事项目" not in exported.text

    staff = await _login(client, "2015200012")
    visible = await client.get(f"/api/records/{record_id}", headers=_auth(staff))
    assert visible.status_code == 200

    denied = await client.get(
        "/api/datasets/ODS_JZGJBSJ/export?reveal=true", headers=_auth(teacher)
    )
    assert denied.status_code == 403

    center = await _login(client, "admin", "Admin@2026")
    revealed = await client.get(
        "/api/datasets/ODS_JZGJBSJ/export?reveal=true", headers=_auth(center)
    )
    assert revealed.status_code == 200
    audit = await db_session.scalar(
        select(AuditLog).where(
            AuditLog.action == "record.export_sensitive",
            AuditLog.resource_id == "ODS_JZGJBSJ",
            AuditLog.actor_account == "admin",
        )
    )
    assert audit is not None
    assert "明文导出" in audit.summary


@pytest.mark.asyncio
async def test_republish_does_not_duplicate_ods_row(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    teacher = await _login(client, "2024020008")
    meta = await _meta(client, teacher, "ODS_JSHJSJ")
    payload = _payload(meta, "2024020008", "谭元霸", HJMC="课堂创新奖", HJRQ="2024-09")
    created = await client.post(
        "/api/datasets/ODS_JSHJSJ/records",
        headers=_auth(teacher),
        json={"payload": payload},
    )
    assert created.status_code == 201, created.text
    record_id = created.json()["id"]
    await client.post(f"/api/records/{record_id}/submit", headers=_auth(teacher))
    center = await _login(client, "admin", "Admin@2026")
    first = await client.post(
        f"/api/records/{record_id}/publish",
        headers=_auth(center),
        json={"comment": "获奖发布"},
    )
    assert first.status_code == 200, first.text
    again = await client.post(
        f"/api/records/{record_id}/publish",
        headers=_auth(center),
        json={"comment": "重复发布"},
    )
    assert again.status_code == 403
    rows = (
        await db_session.scalars(select(TeacherAward).where(TeacherAward.HJMC == "课堂创新奖"))
    ).all()
    assert len(rows) == 1
