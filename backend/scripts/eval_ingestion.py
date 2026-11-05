"""黄金集评测：离线跑结构计划与确定性执行，输出第 1 节的指标。

用法（在 backend 目录）：
    uv run python scripts/eval_ingestion.py
    uv run python scripts/eval_ingestion.py --out storage/eval_report.json
    uv run python scripts/eval_ingestion.py --baseline storage/eval_report.json

黄金集目录：docs/AI解析测试数据/黄金集/<数据集编码>/<样例文件>
同名 .json 是标注，格式：
{
  "dataset_code": "ODS_ZYSZSJ",
  "record_count": 47,
  "plan": {"sheets": [...]},          # 可选，用于计划正确率
  "checks": [
    {"business_key": "410104", "values": {"ZYMC": "生态农业技术"}}
  ]
}

文本类样例（Word/PDF）需要模型，脚本标记为 needs_model，不计入汇总。
"""

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.datasets.registry import get_dataset  # noqa: E402
from app.ingestion import triage  # noqa: E402
from app.ingestion.execute import build_records  # noqa: E402
from app.ingestion.mapping import exact_plan  # noqa: E402
from app.ingestion.parsers.base import ParsedDocument  # noqa: E402
from app.ingestion.parsers.docx import parse_docx  # noqa: E402
from app.ingestion.parsers.pdf import parse_pdf  # noqa: E402
from app.ingestion.parsers.spreadsheet import parse_csv, parse_xls, parse_xlsx  # noqa: E402
from app.ingestion.plan import StructurePlan  # noqa: E402
from app.ingestion.planning import PlanInvalid, validate_plan  # noqa: E402
from app.ingestion.profile import profile_document  # noqa: E402
from app.ingestion.triage import completeness, missing_required  # noqa: E402

DEFAULT_ROOT = ROOT / "docs" / "AI解析测试数据" / "黄金集"
SUFFIXES = {
    ".xlsx": parse_xlsx,
    ".xls": parse_xls,
    ".csv": parse_csv,
    ".docx": parse_docx,
    ".pdf": parse_pdf,
}


def parse(path: Path) -> ParsedDocument:
    return SUFFIXES[path.suffix.lower()](path.read_bytes())


def evaluate_sample(path: Path, annotation: dict[str, Any]) -> dict[str, Any]:
    code = str(annotation.get("dataset_code") or path.parent.name)
    spec = get_dataset(code)
    document = parse(path)
    profile = profile_document(document)
    usable = [sheet for sheet in profile.sheets if not sheet.skip_reason]
    if not usable:
        return {"file": path.name, "dataset_code": code, "status": "needs_model", "metrics": {}}
    plan: StructurePlan | None = None
    if annotation.get("plan"):
        try:
            plan = validate_plan(
                StructurePlan.model_validate(annotation["plan"]), profile, {code: spec}
            )
        except PlanInvalid as exc:
            return {
                "file": path.name,
                "dataset_code": code,
                "status": "plan_invalid",
                "notes": exc.errors[:3],
                "metrics": {},
            }
    else:
        sheet = next(
            (item for item in usable if exact_plan(spec, item) is not None), None
        )
        if sheet is not None:
            sheet_plan = exact_plan(spec, sheet)
            assert sheet_plan is not None
            plan = StructurePlan(sheets=[sheet_plan], source="exact", confidence=1)
    if plan is None:
        return {"file": path.name, "dataset_code": code, "status": "needs_model", "metrics": {}}
    execution = build_records(document, plan)
    rows = [record.raw for record in execution.records]
    sources = {code: {"source": "file", "score": 0.95} for code in spec.field_map()}
    triages = [
        triage.classify(spec, row, [], sources, duplicate=None, conflict=False) for row in rows
    ]
    missing = sum(len(missing_required(spec, row)) for row in rows)
    checks = list(annotation.get("checks") or [])
    matched = 0
    compared = 0
    for check in checks:
        key = str(check.get("business_key") or "")
        expected = dict(check.get("values") or {})
        hit = next((row for row in rows if str(row.get(spec.business_key_fields[0])) == key), None)
        if hit is None:
            compared += len(expected)
            continue
        for field, value in expected.items():
            compared += 1
            actual = str(hit.get(field) or "").strip()
            if actual == str(value).strip():
                matched += 1
    expected_count = annotation.get("record_count")
    plan_accuracy = _plan_accuracy(plan, annotation.get("plan"))
    metrics = {
        "records": len(rows),
        "record_count_error": (
            abs(len(rows) - expected_count) if expected_count is not None else None
        ),
        "auto_rate": round(triages.count(triage.TRIAGE_AUTO) / len(rows), 4) if rows else 0,
        "review_rate": round(triages.count(triage.TRIAGE_REVIEW) / len(rows), 4) if rows else 0,
        "missing_rate": round(triages.count(triage.TRIAGE_MISSING) / len(rows), 4) if rows else 0,
        "avg_completeness": round(sum(completeness(spec, row) for row in rows) / len(rows), 2)
        if rows
        else 0,
        "missing_field_count": missing,
        "field_accuracy": round(matched / compared, 4) if compared else None,
        "plan_accuracy": plan_accuracy,
        "tokens_per_record": 0.0,
        "llm_calls": 0,
    }
    return {
        "file": path.name,
        "dataset_code": code,
        "status": "ok",
        "metrics": metrics,
        "gaps": sorted({gap for row in rows for gap in missing_required(spec, row)}),
    }


def _plan_accuracy(plan: StructurePlan, expected: dict[str, Any] | None) -> float | None:
    if not expected:
        return None
    expected_sheets = {sheet.get("sheet"): sheet for sheet in expected.get("sheets") or []}
    total = 0
    matched = 0
    for sheet in plan.sheets:
        want = expected_sheets.get(sheet.sheet)
        if not want:
            continue
        want_columns = {
            (column.get("header") or ""): column.get("field")
            for column in want.get("columns") or []
        }
        for column in sheet.columns:
            header = column.header or ""
            if header not in want_columns:
                continue
            total += 1
            if (column.field or None) == (want_columns[header] or None):
                matched += 1
    return round(matched / total, 4) if total else None


def discover(root: Path) -> list[tuple[Path, dict[str, Any]]]:
    samples: list[tuple[Path, dict[str, Any]]] = []
    if not root.exists():
        return samples
    sources = [root.parent, root]
    for folder in sorted(item for item in root.iterdir() if item.is_dir()):
        for annotation_path in sorted(folder.glob("*.json")):
            annotation = json.loads(annotation_path.read_text("utf-8"))
            annotation.setdefault("dataset_code", folder.name)
            name = str(annotation.get("file") or "")
            candidates = [folder / name, *(source / name for source in sources)] if name else []
            path = next(
                (
                    item
                    for item in candidates
                    if item.is_file() and item.suffix.lower() in SUFFIXES
                ),
                None,
            )
            if path is None:
                sample = next(
                    (
                        item
                        for item in folder.iterdir()
                        if item.suffix.lower() in SUFFIXES
                        and item.with_suffix(".json").stem == annotation_path.stem
                    ),
                    None,
                )
                path = sample
            if path is not None:
                samples.append((path, annotation))
        for path in sorted(folder.iterdir()):
            if path.suffix.lower() in SUFFIXES and not path.with_suffix(".json").exists():
                samples.append((path, {"dataset_code": folder.name}))
    return samples


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    ok = [item for item in results if item["status"] == "ok" and item["metrics"]["records"]]
    records = sum(item["metrics"]["records"] for item in ok)
    checks = [item for item in ok if item["metrics"]["field_accuracy"] is not None]
    return {
        "samples": len(results),
        "evaluated": len(ok),
        "needs_model": sum(1 for item in results if item["status"] == "needs_model"),
        "records": records,
        "auto_rate": round(
            sum(item["metrics"]["auto_rate"] * item["metrics"]["records"] for item in ok)
            / records,
            4,
        )
        if records
        else 0,
        "avg_completeness": round(
            sum(item["metrics"]["avg_completeness"] * item["metrics"]["records"] for item in ok)
            / records,
            2,
        )
        if records
        else 0,
        "field_accuracy": round(
            sum(item["metrics"]["field_accuracy"] for item in checks) / len(checks), 4
        )
        if checks
        else None,
        "missing_field_count": sum(item["metrics"]["missing_field_count"] for item in ok),
        "tokens_per_record": 0.0,
    }


def markdown(report: dict[str, Any], baseline: dict[str, Any] | None) -> str:
    lines = [
        "# 解析评测报告",
        "",
        f"生成时间：{report['generated_at']}",
        "",
        "| 样例 | 数据表 | 状态 | 记录数 | 自动可确认率 "
        "| 平均完整度 | 字段准确率 | 计划正确率 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for item in report["samples"]:
        metrics = item["metrics"]
        row_template = (
            "| {file} | {code} | {status} | {records} | {auto} "
            "| {complete} | {field} | {plan} |"
        )
        lines.append(
            row_template.format(
                file=item["file"],
                code=item["dataset_code"],
                status=item["status"],
                records=metrics.get("records", "-"),
                auto=_pct(metrics.get("auto_rate")),
                complete=metrics.get("avg_completeness", "-"),
                field=_pct(metrics.get("field_accuracy")),
                plan=_pct(metrics.get("plan_accuracy")),
            )
        )
    summary = report["summary"]
    lines.extend(
        [
            "",
            "## 汇总",
            "",
            "| 指标 | 本版 | 上一版 | 变化 |",
            "| --- | --- | --- | --- |",
        ]
    )
    previous = (baseline or {}).get("summary")
    keys = (
        "evaluated",
        "records",
        "auto_rate",
        "avg_completeness",
        "field_accuracy",
        "missing_field_count",
    )
    for key in keys:
        value = summary.get(key)
        old = (previous or {}).get(key)
        shown = old if old is not None else "-"
        lines.append(f"| {key} | {value} | {shown} | {_delta(value, old)} |")
    lines.append("")
    lines.append("说明：本脚本只跑确定性执行，`needs_model` 的 Word/PDF 样例不计入汇总。")
    return "\n".join(lines)


def _pct(value: Any) -> str:
    return f"{round(float(value) * 100, 2)}%" if value is not None else "-"


def _delta(value: Any, old: Any) -> str:
    if not isinstance(value, (int, float)) or not isinstance(old, (int, float)):
        return "-"
    return f"{value - old:+.4f}"


def main() -> int:
    parser = argparse.ArgumentParser(description="黄金集解析评测")
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--baseline", type=Path, default=None)
    args = parser.parse_args()
    samples = discover(args.root)
    if not samples:
        print(f"未找到黄金集样例：{args.root}")
        return 1
    results = [evaluate_sample(path, annotation) for path, annotation in samples]
    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "root": str(args.root),
        "samples": results,
        "summary": summarize(results),
    }
    baseline = None
    if args.baseline and args.baseline.exists():
        baseline = json.loads(args.baseline.read_text("utf-8"))
    text = markdown(report, baseline)
    print(text)
    target = args.out or (args.baseline if args.baseline else None)
    if target is not None:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, ensure_ascii=False, indent=2), "utf-8")
        print(f"\n报告已写入 {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
