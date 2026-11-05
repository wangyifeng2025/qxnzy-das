import json

from app.datasets.spec import DatasetSpec
from app.ingestion.profile import DocumentProfile


def field_guide(spec: DatasetSpec, options: dict[str, list[tuple[str, str]]]) -> str:
    lines = [f"目标数据表：{spec.name}（{spec.code}）", "字段："]
    for field in spec.fields:
        required = "必填" if field.required else "可空"
        extra = ""
        if field.aliases:
            extra += "；常见表头：" + "、".join(field.aliases[:5])
        if field.hint:
            extra += f"；说明：{field.hint}"
        if field.example:
            extra += f"；示例：{field.example}"
        if field.dict_code and field.dict_code not in {"departments", "titles"}:
            labels = [label for _value, label in options.get(field.dict_code, [])[:20]]
            if labels:
                extra += "；可选值：" + "、".join(labels)
        lines.append(f"- {field.code} {field.label} {field.kind} {required}{extra}")
    return "\n".join(lines)


def plan_input(profile: DocumentProfile, specs: dict[str, DatasetSpec]) -> str:
    sheets = [
        {
            "sheet": sheet.sheet,
            "visible": sheet.visible,
            "rows": sheet.rows,
            "cols": sheet.cols,
            "header_rows": sheet.header_rows,
            "header_texts": [row[:40] for row in sheet.header_texts],
            "headers": sheet.headers[:40],
            "samples": [row[:40] for row in sheet.samples[:3]],
            "merged": sheet.merged[:20],
            "empty_row_ratio": sheet.empty_row_ratio,
            "continuation_ratio": sheet.continuation_ratio,
            "formula_ratio": sheet.formula_ratio,
            "number_formats": sheet.number_formats,
            "duplicate_headers": sheet.duplicate_headers,
            "looks_like_columnar": sheet.looks_like_columnar,
            "looks_like_dict": sheet.looks_like_dict,
            "skip_reason": sheet.skip_reason,
        }
        for sheet in profile.sheets
    ]
    targets = [
        {
            "dataset_code": spec.code,
            "name": spec.name,
            "business_key": list(spec.business_key_fields),
            "required": spec.required_codes(),
            "fields": [
                {
                    "code": field.code,
                    "label": field.label,
                    "kind": field.kind,
                    "required": field.required,
                    "visible_when": field.visible_when,
                    "aliases": list(field.aliases),
                }
                for field in spec.fields
            ],
        }
        for spec in specs.values()
    ]
    return json.dumps({"sheets": sheets, "targets": targets}, ensure_ascii=False)


def completion_input(
    spec: DatasetSpec,
    missing: list[str],
    values: dict[str, object],
    source_text: str,
) -> str:
    fields = spec.field_map()
    payload = {
        "dataset_code": spec.code,
        "missing": [{"code": code, "label": fields[code].label} for code in missing],
        "known": values,
        "source_text": source_text[:8000],
    }
    return json.dumps(payload, ensure_ascii=False)
