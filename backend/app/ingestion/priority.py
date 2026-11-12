"""缺口优先级与下一步建议。纯函数，不访问数据库和模型。

排序规则：
- P0 业务主键字段：缺了无法判重，也无法被补充文件匹配；
- P1 查库补全的依据字段：补上后能自动带出其他字段；
- P2 其他必填与已触发的条件必填字段；
- 同层按收益排序，收益 = 缺该字段的记录数 × (1 + 补上后可自动带出的字段数)。
"""

from collections import Counter
from dataclasses import dataclass, field

from app.datasets.spec import DatasetSpec
from app.ingestion import triage

TIER_LABELS = {
    "P0": "主键字段",
    "P1": "可带出其他字段",
    "P2": "必填字段",
}
# 查库补全规则的来源对应哪个数据集；同批次里先补被依赖的数据集
SOURCE_DATASETS = {"major": "ODS_ZYSZSJ", "course": "ODS_KCJBSJ", "staff": "ODS_JZGJBSJ"}
_BULK_OPTIONS = 3


@dataclass
class Gap:
    dataset_code: str
    code: str
    label: str
    tier: str
    count: int
    gain: int
    unlocks: list[str] = field(default_factory=list)
    bulk_hint: bool = False

    def as_dict(self) -> dict[str, object]:
        return {
            "dataset_code": self.dataset_code,
            "code": self.code,
            "label": self.label,
            "tier": self.tier,
            "count": self.count,
            "gain": self.gain,
            "unlocks": self.unlocks,
            "bulk_hint": self.bulk_hint,
        }


def _unlock_map(spec: DatasetSpec) -> dict[str, set[str]]:
    found: dict[str, set[str]] = {}
    for rule in spec.lookups:
        targets = {target for target, _source in rule.fill}
        for code in rule.by:
            found.setdefault(code, set()).update(targets - {code})
    return found


def gaps_for(
    spec: DatasetSpec,
    rows: list[dict[str, object]],
    *,
    skipped: set[str] | None = None,
    option_counts: dict[str, int] | None = None,
) -> list[Gap]:
    skipped = skipped or set()
    option_counts = option_counts or {}
    unlock_map = _unlock_map(spec)
    labels = spec.field_map()
    order = {item.code: index for index, item in enumerate(spec.fields)}
    counts: Counter[str] = Counter()
    missing_rows: list[set[str]] = []
    for values in rows:
        missing = set(triage.missing_required(spec, values)) - skipped
        missing_rows.append(missing)
        counts.update(missing)
    gaps: list[Gap] = []
    for code, count in counts.items():
        unlocks = sorted(
            target
            for target in unlock_map.get(code, set())
            if any(code in missing and target in missing for missing in missing_rows)
        )
        if code in spec.business_key_fields:
            tier = "P0"
        elif code in unlock_map:
            tier = "P1"
        else:
            tier = "P2"
        item = labels.get(code)
        gaps.append(
            Gap(
                dataset_code=spec.code,
                code=code,
                label=item.label if item else code,
                tier=tier,
                count=count,
                gain=count * (1 + len(unlocks)),
                unlocks=unlocks,
                bulk_hint=bool(
                    item
                    and item.dict_code
                    and 0 < option_counts.get(item.dict_code, 0) <= _BULK_OPTIONS
                ),
            )
        )
    gaps.sort(key=lambda gap: (gap.tier, -gap.gain, order.get(gap.code, 999)))
    return gaps


def dataset_order(specs: list[DatasetSpec]) -> list[str]:
    """被查库补全依赖的数据集排在前面，其余保持批次中的顺序。"""
    codes = [spec.code for spec in specs]
    depends: dict[str, set[str]] = {}
    for spec in specs:
        needed = {SOURCE_DATASETS.get(rule.source, "") for rule in spec.lookups}
        depends[spec.code] = {code for code in needed if code in codes and code != spec.code}
    ordered: list[str] = []
    visiting: set[str] = set()

    def visit(code: str) -> None:
        if code in ordered or code in visiting:
            return
        visiting.add(code)
        for needed in sorted(depends.get(code, set()), key=codes.index):
            visit(needed)
        visiting.discard(code)
        ordered.append(code)

    for code in codes:
        visit(code)
    return ordered


def next_step(
    order: list[str],
    gaps: dict[str, list[Gap]],
    *,
    names: dict[str, str],
    totals: dict[str, int],
    conflicts: int,
    ready: int,
    template_fields: int,
) -> dict[str, object]:
    """给出一个最值得做的下一步。只建议，不执行。"""
    if not any(totals.values()):
        return {
            "kind": "upload",
            "dataset_code": order[0] if order else None,
            "fields": [],
            "message": "先上传第一份文件，系统会识别出记录并告诉你还缺哪些字段。",
        }
    for code in order:
        items = gaps.get(code) or []
        if not items:
            continue
        name = names.get(code, code)
        top = items[0]
        if top.tier == "P0":
            keys = [gap for gap in items if gap.tier == "P0"]
            fields = [gap.code for gap in keys]
            labels = "、".join(gap.label for gap in keys)
            return {
                "kind": "upload",
                "dataset_code": code,
                "fields": fields,
                "message": (
                    f"「{name}」有 {top.count} 条记录缺主键字段「{labels}」，"
                    "缺了它们后续文件无法对上记录。请先上传包含这些字段的名单或表格。"
                ),
            }
        chosen: list[Gap] = []
        covered: set[str] = set()
        for gap in items:
            if gap.code in covered:
                continue
            chosen.append(gap)
            covered.update(gap.unlocks)
            if len(chosen) >= template_fields:
                break
        fields = [gap.code for gap in chosen]
        labels = "、".join(f"「{gap.label}」" for gap in chosen)
        message = (
            f"「{name}」最值得先补的是 {labels}，共涉及 {top.count} 条记录。"
            "可以下载补充模板填好后上传，也可以直接上传手边含这些列的表格。"
        )
        if top.unlocks:
            message += f"补上「{top.label}」后可自动带出 {len(top.unlocks)} 个字段。"
        hint = next((gap for gap in chosen if gap.bulk_hint), None)
        if hint is not None:
            message += f"如果「{hint.label}」大多相同，也可以直接说一句，例如“这些都填否”。"
        return {"kind": "template", "dataset_code": code, "fields": fields, "message": message}
    if conflicts:
        return {
            "kind": "conflicts",
            "dataset_code": None,
            "fields": [],
            "message": (
                f"必填字段已补齐，还有 {conflicts} 条记录存在多份文件取值不一致，"
                "请逐条确认采用哪个值。"
            ),
        }
    return {
        "kind": "confirm",
        "dataset_code": None,
        "fields": [],
        "message": f"必填字段已全部补齐，{ready} 条记录可直接确认，请检查后确认入库。",
    }
