"""一句话转成的批量动作：校验、圈定影响范围、生成预览。纯函数，执行在路由里完成。

模型只负责翻译成动作；字段是否存在、取值是否合法、影响哪些记录都由这里按规则判定。
"""

from dataclasses import dataclass

from app.ai.extract import ProposedAction
from app.datasets.spec import DatasetSpec
from app.ingestion import triage
from app.ingestion.normalize import cell_text
from app.ingestion.reference import match_key
from app.models.ingestion import IngestCandidate

_SAMPLES = 5
_TEXT_DICTS = {None, "departments", "titles"}
_CONFLICT_CHOICES = {"incoming": "采用新文件的值", "kept": "保留原值"}


class ActionInvalid(Exception):
    pass


@dataclass(frozen=True)
class Action:
    kind: str
    dataset_code: str
    field: str | None
    value: str | None
    triage: str | None
    where: tuple[tuple[str, str], ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "action": self.kind,
            "dataset_code": self.dataset_code,
            "field": self.field,
            "value": self.value,
            "scope": {"triage": self.triage, "where": dict(self.where)},
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "Action":
        scope = data.get("scope") if isinstance(data.get("scope"), dict) else {}
        assert isinstance(scope, dict)
        where = scope.get("where") if isinstance(scope.get("where"), dict) else {}
        assert isinstance(where, dict)
        return cls(
            kind=str(data.get("action")),
            dataset_code=str(data.get("dataset_code")),
            field=str(data["field"]) if data.get("field") else None,
            value=str(data["value"]) if data.get("value") is not None else None,
            triage=str(scope["triage"]) if scope.get("triage") else None,
            where=tuple((str(key), str(value)) for key, value in where.items()),
        )


def _dict_value(spec: DatasetSpec, code: str, text: str, lookups: dict[str, dict[str, str]]) -> str:
    item = spec.field_map()[code]
    if item.dict_code in _TEXT_DICTS:
        return text
    found = lookups.get(item.dict_code or "", {}).get(text.strip())
    if found is None:
        raise ActionInvalid(f"「{text}」不是「{item.label}」的可选值")
    return found


def validate(
    proposed: ProposedAction,
    specs: dict[str, DatasetSpec],
    lookups: dict[str, dict[str, str]],
    default_dataset: str | None,
) -> Action:
    if proposed.action == "none":
        raise ActionInvalid(
            proposed.reply
            or "没能理解这句话，请说明要对哪个字段做什么，例如“这些课程都不是校企合作开发”。"
        )
    code = proposed.dataset_code or default_dataset
    spec = specs.get(code or "")
    if spec is None:
        raise ActionInvalid("请说明是哪张数据表")
    known = spec.field_map()
    field = proposed.field or None
    if field is not None and field not in known:
        raise ActionInvalid(f"数据表「{spec.name}」没有字段「{field}」")
    if proposed.action in {"bulk_set", "skip_field"} and field is None:
        raise ActionInvalid("请说明要处理哪个字段")
    where: list[tuple[str, str]] = []
    for key, text in proposed.scope.where.items():
        if key not in known:
            raise ActionInvalid(f"筛选条件里的字段「{key}」不存在")
        if cell_text(text):
            where.append((key, _dict_value(spec, key, text, lookups)))
    value: str | None = None
    if proposed.action == "bulk_set":
        assert field is not None
        if not cell_text(proposed.value):
            raise ActionInvalid(f"请说明「{known[field].label}」要填什么")
        value = _dict_value(spec, field, str(proposed.value), lookups)
    elif proposed.action == "resolve_conflict":
        value = proposed.value if proposed.value in _CONFLICT_CHOICES else None
        if value is None:
            raise ActionInvalid("请说明冲突时采用新文件的值还是保留原值")
    return Action(
        kind=proposed.action,
        dataset_code=spec.code,
        field=field,
        value=value,
        triage=proposed.scope.triage,
        where=tuple(where),
    )


def targets(
    spec: DatasetSpec, rows: list[IngestCandidate], action: Action
) -> list[IngestCandidate]:
    found: list[IngestCandidate] = []
    for row in rows:
        if row.dataset_code != action.dataset_code or row.record_id is not None:
            continue
        if action.triage and row.triage != action.triage:
            continue
        values = row.values or {}
        if any(match_key(values.get(key)) != match_key(text) for key, text in action.where):
            continue
        if action.kind == "resolve_conflict":
            if any(
                not action.field or conflict.get("field") == action.field
                for conflict in row.conflicts or []
            ):
                found.append(row)
            continue
        assert action.field is not None
        if action.field not in triage.visible_fields(spec, values):
            continue
        if not cell_text(values.get(action.field)):
            found.append(row)
    return found


def _label(spec: DatasetSpec, values: dict[str, object]) -> str:
    parts = [cell_text(values.get(code)) for code in spec.list_fields[:3]]
    return " / ".join(part for part in parts if part) or "（未命名记录）"


def _display(
    spec: DatasetSpec, code: str, value: str | None, options: dict[str, dict[str, str]]
) -> str:
    if value is None:
        return ""
    item = spec.field_map().get(code)
    if item is None or item.dict_code in _TEXT_DICTS:
        return value
    return options.get(item.dict_code or "", {}).get(value, value)


def describe(spec: DatasetSpec, action: Action, options: dict[str, dict[str, str]]) -> str:
    labels = spec.field_map()
    scope = ""
    if action.where:
        scope = "、".join(
            f"{labels[key].label}为“{_display(spec, key, text, options)}”"
            for key, text in action.where
        )
        scope = f"（{scope}）"
    if action.kind == "bulk_set":
        assert action.field is not None
        return (
            f"把{spec.name}{scope}中「{labels[action.field].label}」为空的记录"
            f"填为“{_display(spec, action.field, action.value, options)}”"
        )
    if action.kind == "resolve_conflict":
        target = f"「{labels[action.field].label}」" if action.field else "所有字段"
        return f"{spec.name}{scope}中{target}的冲突统一{_CONFLICT_CHOICES[action.value or 'kept']}"
    assert action.field is not None
    return f"暂不补「{labels[action.field].label}」，后续建议里不再提示"


def preview(
    spec: DatasetSpec,
    action: Action,
    rows: list[IngestCandidate],
    options: dict[str, dict[str, str]],
) -> dict[str, object]:
    """options 为字典代码到 {值: 名称}，用于把代码显示成名称。"""
    samples: list[dict[str, object]] = []
    for row in rows[:_SAMPLES]:
        values = row.values or {}
        if action.kind == "resolve_conflict":
            for conflict in row.conflicts or []:
                if action.field and conflict.get("field") != action.field:
                    continue
                after = (
                    conflict.get("incoming") if action.value == "incoming" else conflict.get("kept")
                )
                samples.append(
                    {
                        "id": row.id,
                        "label": _label(spec, values),
                        "field": conflict.get("label"),
                        "before": conflict.get("kept"),
                        "after": after,
                    }
                )
            continue
        samples.append(
            {
                "id": row.id,
                "label": _label(spec, values),
                "field": spec.field_map()[action.field].label if action.field else "",
                "before": "",
                "after": _display(spec, action.field or "", action.value, options)
                if action.kind == "bulk_set"
                else "",
            }
        )
    return {
        "count": len(rows),
        "summary": describe(spec, action, options),
        "samples": samples[:_SAMPLES],
    }


def context_text(
    specs: list[DatasetSpec],
    totals: dict[str, int],
    gaps: list[dict[str, object]],
    options: dict[str, list[tuple[str, str]]],
    conflicts: int,
) -> str:
    """给模型的批次说明：每张表的字段、可选值和当前缺口。不含任何记录内容。"""
    lines: list[str] = []
    for spec in specs:
        lines.append(f"## 数据表 {spec.code}（{spec.name}），待确认 {totals.get(spec.code, 0)} 条")
        for item in spec.fields:
            note = "必填" if item.required else "选填"
            choices = options.get(item.dict_code or "", [])
            if item.dict_code not in _TEXT_DICTS and choices:
                names = "、".join(label for _value, label in choices[:20])
                more = f" 等 {len(choices)} 项" if len(choices) > 20 else ""
                note += f"，可选：{names}{more}"
            lines.append(f"- {item.code} {item.label}（{note}）")
        own = [gap for gap in gaps if gap.get("dataset_code") == spec.code]
        if own:
            lines.append(
                "当前缺口："
                + "；".join(
                    f"{gap['label']}（{gap['code']}）缺 {gap['count']} 条" for gap in own[:10]
                )
            )
    lines.append(f"存在取值冲突的记录：{conflicts} 条")
    return "\n".join(lines)
