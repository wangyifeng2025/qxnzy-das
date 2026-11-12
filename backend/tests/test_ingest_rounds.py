"""多轮补齐：补齐模式、优先级、补充模板、轮次报告与一句话批量动作。

这些测试都不访问真实模型：解析流程按“未配置模型”运行，对话接口注入假的模型客户端。
"""

import json
from io import BytesIO

import pytest
from httpx import AsyncClient
from openpyxl import Workbook, load_workbook
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.client import LLMResult
from app.api.routes import ingest_chat
from app.datasets.registry import get_dataset
from app.ingestion import pipeline, priority
from app.ingestion.pipeline import run_pipeline
from app.ingestion.supplement import MARKER_SHEET

AWARD = "ODS_JSHJSJ"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@pytest.fixture(autouse=True)
def _no_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pipeline, "resolved_ai", lambda: ("test", "", "", "test-model"))


async def _login(client: AsyncClient) -> dict[str, str]:
    response = await client.post(
        "/api/auth/login", json={"account": "2015200012", "password": "123456"}
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _book(headers: list[str], rows: list[list[str]]) -> bytes:
    book = Workbook()
    sheet = book.active
    assert sheet is not None
    sheet.append(headers)
    for row in rows:
        sheet.append(row)
    buffer = BytesIO()
    book.save(buffer)
    return buffer.getvalue()


def _option(meta: dict, code: str) -> str:
    for item in meta["dicts"][code]:
        if item["value"] == "0" or item["label"] == "否":
            return str(item["value"])
    return str(meta["dicts"][code][0]["value"])


def _first_file(meta: dict, units: dict[str, str]) -> bytes:
    """两条获奖记录，颁奖单位按 units 填，缺省为空。"""
    headers: list[str] = []
    base: dict[str, str] = {}
    for field in meta["fields"]:
        if field["visible_when"]:
            continue
        code = field["code"]
        headers.append(code)
        if code == meta["owner_field"]:
            base[code] = "2015200012"
        elif code == meta["owner_name_field"]:
            base[code] = "罗胜"
        elif code == meta["department_field"]:
            base[code] = "机械与电子工程系"
        elif field["dict_code"] and field["dict_code"] != "departments":
            base[code] = _option(meta, field["dict_code"])
        elif field["kind"] == "month":
            base[code] = "2024-03"
        else:
            base[code] = ""
    rows = []
    for name in ("教学成果奖", "技能大赛"):
        row = {**base, "HJMC": name, "BJDWMC": units.get(name, "")}
        rows.append([row[code] for code in headers])
    return _book(headers, rows)


async def _start(
    client: AsyncClient, db_session: AsyncSession, headers: dict[str, str], content: bytes
) -> tuple[str, dict]:
    meta = (await client.get(f"/api/datasets/{AWARD}/meta", headers=headers)).json()
    batch = await client.post(
        "/api/ingestion/batches", headers=headers, json={"dataset_codes": [AWARD]}
    )
    assert batch.status_code == 200, batch.text
    batch_id = batch.json()["id"]
    await _upload(client, db_session, headers, batch_id, content, "first.xlsx")
    return batch_id, meta


async def _upload(
    client: AsyncClient,
    db_session: AsyncSession,
    headers: dict[str, str],
    batch_id: str,
    content: bytes,
    name: str,
) -> dict:
    created = await client.post(
        f"/api/ingestion/batches/{batch_id}/files",
        headers=headers,
        data={"dataset_code": AWARD},
        files={"file": (name, content, XLSX)},
    )
    assert created.status_code == 202, created.text
    await run_pipeline(db_session, created.json()["id"])
    task = await client.get(f"/api/ingestion/tasks/{created.json()['id']}", headers=headers)
    return dict(task.json())


async def _candidates(client: AsyncClient, headers: dict[str, str], batch_id: str) -> list[dict]:
    response = await client.get(f"/api/ingestion/batches/{batch_id}/candidates", headers=headers)
    return sorted(response.json(), key=lambda row: row["values"]["HJMC"])


async def _rounds(client: AsyncClient, headers: dict[str, str], batch_id: str) -> list[dict]:
    response = await client.get(f"/api/ingestion/batches/{batch_id}/rounds", headers=headers)
    assert response.status_code == 200, response.text
    return list(response.json())


async def test_supplement_file_fills_empty_fields_by_alternate_key(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    headers = await _login(client)
    meta = (await client.get(f"/api/datasets/{AWARD}/meta", headers=headers)).json()
    batch_id, _meta = await _start(client, db_session, headers, _first_file(meta, {}))
    rows = await _candidates(client, headers, batch_id)
    assert [row["triage"] for row in rows] == ["missing", "missing"]
    first = (await _rounds(client, headers, batch_id))[0]["report"]
    assert first["created"] == 2
    assert any(gap["code"] == "BJDWMC" for gap in first["gaps"])
    assert first["next"]["kind"] == "template"
    assert "BJDWMC" in first["next"]["fields"]

    # 只有“获奖名称 + 颁奖单位”两列，不覆盖任何其他必填字段
    supplement = _book(
        ["获奖名称", "颁奖单位名称"], [["技能大赛", "人社厅"], ["教学成果奖", "教育厅"]]
    )
    task = await _upload(client, db_session, headers, batch_id, supplement, "units.xlsx")
    assert task["status"] == "pending_confirmation", task
    assert task["mode"] == "supplement"
    assert task["match_key"] == ["HJMC"]
    assert task["llm_calls"] == 0
    assert task["candidate_count"] == 0

    rows = await _candidates(client, headers, batch_id)
    assert len(rows) == 2
    assert {row["values"]["HJMC"]: row["values"]["BJDWMC"] for row in rows} == {
        "技能大赛": "人社厅",
        "教学成果奖": "教育厅",
    }
    assert all(row["triage"] != "missing" for row in rows)
    assert rows[0]["field_sources"]["BJDWMC"]["ref"]["task"] == task["id"]

    report = (await _rounds(client, headers, batch_id))[-1]["report"]
    assert report["seq"] == 2
    assert report["matched"] == 2
    assert report["created"] == 0
    assert report["filled"] == [{"code": "BJDWMC", "label": "颁奖单位名称", "count": 2}]
    assert report["completeness_after"] > report["completeness_before"]
    assert report["supplement"]["match_rate"] == 1
    assert report["next"]["kind"] in {"confirm", "conflicts"}


async def test_low_match_waits_then_keeps_existing_values_on_conflict(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    headers = await _login(client)
    meta = (await client.get(f"/api/datasets/{AWARD}/meta", headers=headers)).json()
    batch_id, _meta = await _start(
        client, db_session, headers, _first_file(meta, {"教学成果奖": "教育厅"})
    )
    supplement = _book(
        ["获奖名称", "颁奖单位名称"],
        [["教学成果奖", "人社厅"], ["技能大赛", "人社厅"], ["文明教师", "市教育局"]],
    )
    task = await _upload(client, db_session, headers, batch_id, supplement, "units.xlsx")
    assert task["status"] == "awaiting_plan"
    plan = (await client.get(f"/api/ingestion/tasks/{task['id']}/plan", headers=headers)).json()
    detail = plan["dry_run"]["supplement"]
    assert (detail["rows"], detail["matched"], detail["extra"], detail["conflicts"]) == (3, 2, 1, 1)
    assert detail["extra_samples"] == ["文明教师"]
    waiting = (await _rounds(client, headers, batch_id))[-1]["report"]
    assert waiting["status"] == "awaiting_plan"
    assert all(
        row["values"]["BJDWMC"] != "人社厅"
        for row in await _candidates(client, headers, batch_id)
        if row["values"]["HJMC"] == "技能大赛"
    )

    confirmed = await client.put(
        f"/api/ingestion/tasks/{task['id']}/plan",
        headers=headers,
        json={"plan": plan["plan"], "remember": False, "match_key": ["HJMC"]},
    )
    assert confirmed.status_code == 200, confirmed.text
    await run_pipeline(db_session, task["id"])

    rows = {row["values"]["HJMC"]: row for row in await _candidates(client, headers, batch_id)}
    assert len(rows) == 2, "文件中多出的记录不应新建候选"
    assert rows["技能大赛"]["values"]["BJDWMC"] == "人社厅"
    kept = rows["教学成果奖"]
    assert kept["values"]["BJDWMC"] == "教育厅"
    assert kept["triage"] == "review"
    assert kept["conflicts"][0]["incoming"] == "人社厅"
    report = (await _rounds(client, headers, batch_id))[-1]["report"]
    assert report["new_conflicts"] == 1
    assert report["supplement"]["extra"] == 1
    assert any("多出 1 条" in line for line in report["lines"])


async def test_supplement_template_round_trip_uses_no_model(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    headers = await _login(client)
    meta = (await client.get(f"/api/datasets/{AWARD}/meta", headers=headers)).json()
    batch_id, _meta = await _start(client, db_session, headers, _first_file(meta, {}))
    response = await client.get(
        f"/api/ingestion/batches/{batch_id}/supplement-template",
        headers=headers,
        params={"dataset_code": AWARD},
    )
    assert response.status_code == 200, response.text
    book = load_workbook(BytesIO(response.content))
    assert book[MARKER_SHEET].sheet_state == "hidden"
    sheet = book["补充数据"]
    header = [cell.value for cell in sheet[1]]
    assert header[-1] == "颁奖单位名称"
    assert sheet.max_row == 3
    for row in range(2, sheet.max_row + 1):
        sheet.cell(row=row, column=len(header), value="省教育厅")
    buffer = BytesIO()
    book.save(buffer)

    task = await _upload(client, db_session, headers, batch_id, buffer.getvalue(), "template.xlsx")
    assert task["status"] == "pending_confirmation", task
    assert task["plan_source"] == "supplement"
    assert task["llm_calls"] == 0
    rows = await _candidates(client, headers, batch_id)
    assert all(row["values"]["BJDWMC"] == "省教育厅" for row in rows)


async def test_full_second_file_still_merges_as_initial(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """完整覆盖必填字段的文件不走补齐模式，仍按业务主键合并、可以新增记录。"""
    headers = await _login(client)
    meta = (await client.get(f"/api/datasets/{AWARD}/meta", headers=headers)).json()
    batch_id, _meta = await _start(client, db_session, headers, _first_file(meta, {}))
    task = await _upload(
        client,
        db_session,
        headers,
        batch_id,
        _first_file(meta, {"教学成果奖": "教育厅", "技能大赛": "人社厅"}),
        "full.xlsx",
    )
    assert task["mode"] == "initial"
    rows = await _candidates(client, headers, batch_id)
    assert len(rows) == 2
    assert {row["values"]["BJDWMC"] for row in rows} == {"教育厅", "人社厅"}


def test_priority_tiers_and_dataset_order() -> None:
    course = get_dataset("ODS_KCJBSJ")
    major = get_dataset("ODS_ZYSZSJ")
    gaps = priority.gaps_for(course, [{}, {}, {"ZYDM": "460104"}])
    tiers = [gap.tier for gap in gaps]
    assert tiers == sorted(tiers)
    first = gaps[0]
    assert first.tier == "P0"
    by_code = {gap.code: gap for gap in gaps}
    assert by_code["ZYDM"].tier == "P0"
    assert by_code["ZYDM"].count == 2
    assert by_code["ZYDM"].gain == 2 * (1 + len(by_code["ZYDM"].unlocks))
    assert "ZYMC" in by_code["ZYDM"].unlocks
    assert priority.dataset_order([course, major]) == ["ODS_ZYSZSJ", "ODS_KCJBSJ"]
    step = priority.next_step(
        ["ODS_KCJBSJ"],
        {"ODS_KCJBSJ": gaps},
        names={"ODS_KCJBSJ": course.name},
        totals={"ODS_KCJBSJ": 3},
        conflicts=0,
        ready=0,
        template_fields=5,
    )
    assert step["kind"] == "upload"
    assert "ZYDM" in step["fields"]


class _FakeModel:
    def __init__(self, output: dict[str, object]) -> None:
        self.output = output
        self.calls = 0

    async def complete(self, *, system: str, user: str) -> LLMResult:
        self.calls += 1
        assert "用户说：" in user
        return LLMResult(
            content=json.dumps(self.output, ensure_ascii=False), tokens_in=1, tokens_out=1
        )


async def test_message_proposes_action_and_applies_only_after_confirm(
    client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers = await _login(client)
    meta = (await client.get(f"/api/datasets/{AWARD}/meta", headers=headers)).json()
    batch_id, _meta = await _start(client, db_session, headers, _first_file(meta, {}))
    fake = _FakeModel(
        {
            "action": "bulk_set",
            "dataset_code": AWARD,
            "field": "BJDWMC",
            "value": "省教育厅",
            "scope": {"triage": None, "where": {}},
            "reply": "",
        }
    )
    monkeypatch.setattr(ingest_chat, "_client", lambda: fake)
    sent = await client.post(
        f"/api/ingestion/batches/{batch_id}/messages",
        headers=headers,
        json={"text": "颁奖单位都是省教育厅"},
    )
    assert sent.status_code == 200, sent.text
    action = sent.json()["action"]
    assert action["status"] == "proposed"
    assert action["preview"]["count"] == 2
    assert fake.calls == 1
    assert all(
        not row["values"].get("BJDWMC") for row in await _candidates(client, headers, batch_id)
    )

    applied = await client.post(f"/api/ingestion/actions/{action['id']}/apply", headers=headers)
    assert applied.status_code == 200, applied.text
    report = applied.json()["round"]["report"]
    assert report["trigger"] == "action"
    assert report["filled"] == [{"code": "BJDWMC", "label": "颁奖单位名称", "count": 2}]
    rows = await _candidates(client, headers, batch_id)
    assert all(row["values"]["BJDWMC"] == "省教育厅" for row in rows)
    assert rows[0]["field_sources"]["BJDWMC"]["source"] == "bulk"
    again = await client.post(f"/api/ingestion/actions/{action['id']}/apply", headers=headers)
    assert again.status_code == 400


async def test_message_rejects_invalid_dict_value(
    client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers = await _login(client)
    meta = (await client.get(f"/api/datasets/{AWARD}/meta", headers=headers)).json()
    batch_id, _meta = await _start(client, db_session, headers, _first_file(meta, {}))
    fake = _FakeModel(
        {"action": "bulk_set", "dataset_code": AWARD, "field": "JB", "value": "宇宙级"}
    )
    monkeypatch.setattr(ingest_chat, "_client", lambda: fake)
    sent = await client.post(
        f"/api/ingestion/batches/{batch_id}/messages",
        headers=headers,
        json={"text": "级别都填宇宙级"},
    )
    assert sent.status_code == 200, sent.text
    assert sent.json()["action"] is None
    assert "不是「级别」的可选值" in sent.json()["reply"]
    actions = await client.get(f"/api/ingestion/batches/{batch_id}/actions", headers=headers)
    assert actions.json() == []
