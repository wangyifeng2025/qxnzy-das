"use client";

import { AlertTriangle, ChevronDown, X } from "lucide-react";
import { useMemo, useState } from "react";

import { primaryButton } from "@/components/page-bits";
import type { DatasetMeta } from "@/lib/records";

import { PLAN_SOURCE_LABEL, type PlanColumn, type PlanRead, type SheetProfile } from "./types";

type Filter = "all" | "mapped" | "skipped";

type Row = {
  /** 在计划 columns 里的下标；计划里没有列出的文件列为 null，选字段时再补进计划。 */
  index: number | null;
  key: string;
  /** 在文件里是第几列（从 0 开始）；多列合成的取第一列。 */
  position: number | null;
  column: PlanColumn;
  label: string;
  samples: string[];
  /** 同名表头共几个、这里是第几个，只有重名列才有值。 */
  repeat: { nth: number; total: number } | null;
  targets: string[];
};

/**
 * 按后端执行时的规则对齐样例：同名表头依次取第 1、2… 个出现的位置。
 * 模型给出的计划常常省略“不导入”的列，这里把文件里剩下的列补上，按文件顺序排列，
 * 否则用户看不到、也没法映射被省略的列（例如第二个“课程号”）。
 */
function buildRows(columns: PlanColumn[], profile: SheetProfile | undefined): Row[] {
  const headers = profile?.headers ?? [];
  const samples = profile?.samples ?? [];
  const pools = new Map<string, number[]>();
  headers.forEach((header, position) => {
    const key = header.trim();
    pools.set(key, [...(pools.get(key) ?? []), position]);
  });
  const used = new Map<string, number>();
  const taken = new Set<number>();

  const take = (header: string) => {
    const key = header.trim();
    const positions = pools.get(key) ?? [];
    const nth = used.get(key) ?? 0;
    used.set(key, nth + 1);
    const position = positions[nth] ?? null;
    if (position != null) taken.add(position);
    return { position, nth, total: positions.length };
  };
  const sampleAt = (positions: (number | null)[]) =>
    samples
      .map((row) => positions.map((position) => (position == null ? "" : (row[position] ?? ""))).join(""))
      .filter((value) => value.trim() !== "");

  const planned: Row[] = columns.map((column, index) => {
    const names = column.headers?.length ? column.headers : column.header ? [column.header] : [];
    const picked = names.map(take);
    const single = picked.length === 1 ? picked[0] : null;
    return {
      index,
      key: `p-${index}`,
      position: picked.find((item) => item.position != null)?.position ?? null,
      column,
      label: column.header || names.join(" + ") || "未命名列",
      samples: sampleAt(picked.map((item) => item.position)),
      repeat: single && single.total > 1 ? { nth: single.nth + 1, total: single.total } : null,
      targets: column.fields?.length ? column.fields : column.field ? [column.field] : [],
    };
  });

  const extra: Row[] = [];
  headers.forEach((header, position) => {
    if (taken.has(position) || !header.trim()) return;
    const positions = pools.get(header.trim()) ?? [];
    extra.push({
      index: null,
      key: `x-${position}`,
      position,
      column: { header, transform: "direct" },
      label: header,
      samples: sampleAt([position]),
      repeat: positions.length > 1 ? { nth: positions.indexOf(position) + 1, total: positions.length } : null,
      targets: [],
    });
  });

  return [...planned, ...extra].sort(
    (left, right) => (left.position ?? Number.MAX_SAFE_INTEGER) - (right.position ?? Number.MAX_SAFE_INTEGER),
  );
}

export function PlanReview({
  plan,
  meta,
  editable,
  busy,
  remember,
  onRememberChange,
  onFieldChange,
  onDedupeChange,
  onApply,
}: {
  plan: PlanRead;
  meta: DatasetMeta | null;
  editable: boolean;
  busy: boolean;
  remember: boolean;
  onRememberChange: (value: boolean) => void;
  /** columnIndex 为 null 表示计划里还没有这一列，需要按 header 追加。 */
  onFieldChange: (sheetIndex: number, columnIndex: number | null, header: string, field: string) => void;
  onDedupeChange: (sheetIndex: number, fields: string[]) => void;
  onApply: () => void;
}) {
  const sheets = useMemo(
    () => (plan.plan?.sheets ?? []).map((sheet, index) => ({ sheet, index })).filter(({ sheet }) => sheet.role !== "ignore"),
    [plan.plan],
  );
  const [activeSheet, setActiveSheet] = useState(0);
  const [filter, setFilter] = useState<Filter>("all");
  const [previewOpen, setPreviewOpen] = useState(false);
  const [flash, setFlash] = useState<string | null>(null);

  const current = sheets[Math.min(activeSheet, Math.max(0, sheets.length - 1))];
  const profile = plan.profile?.sheets?.find((item) => item.sheet === current?.sheet.sheet);
  const rows = useMemo(() => (current ? buildRows(current.sheet.columns, profile) : []), [current, profile]);
  const labels = useMemo(() => new Map((meta?.fields ?? []).map((field) => [field.code, field.label])), [meta]);

  const conflicts = useMemo(() => {
    const seen = new Map<string, number>();
    for (const row of rows) for (const target of row.targets) seen.set(target, (seen.get(target) ?? 0) + 1);
    return new Set([...seen].filter(([, count]) => count > 1).map(([code]) => code));
  }, [rows]);
  const allConflicts = useMemo(() => {
    const found: string[] = [];
    for (const { sheet } of sheets) {
      const seen = new Set<string>();
      for (const column of sheet.columns) {
        for (const target of column.fields?.length ? column.fields : column.field ? [column.field] : []) {
          if (seen.has(target)) found.push(`${sheet.sheet}：${labels.get(target) ?? target}`);
          seen.add(target);
        }
      }
    }
    return found;
  }, [sheets, labels]);

  const mappedCount = rows.filter((row) => row.targets.length > 0).length;
  const visibleRows = rows.filter((row) =>
    filter === "mapped" ? row.targets.length > 0 : filter === "skipped" ? row.targets.length === 0 : true,
  );

  const dry = plan.dry_run;
  const gaps = new Map((dry?.gaps ?? []).map((gap) => [gap.code, gap]));
  const required = (meta?.fields ?? []).filter((field) => field.required && !field.visible_when);
  const providers = new Map<string, { label: string; sheetPos: number; row: string }[]>();
  sheets.forEach(({ sheet }, sheetPos) => {
    if (sheet.role !== "main") return;
    const sheetRows = buildRows(sheet.columns, plan.profile?.sheets?.find((item) => item.sheet === sheet.sheet));
    for (const row of sheetRows) {
      for (const target of row.targets) {
        providers.set(target, [...(providers.get(target) ?? []), { label: row.label, sheetPos, row: row.key }]);
      }
    }
  });
  const missing = required.filter((field) => !providers.has(field.code) && gaps.has(field.code));

  function locate(sheetPos: number, row: string) {
    setActiveSheet(sheetPos);
    setFilter("all");
    setFlash(row);
    window.setTimeout(() => {
      document.getElementById(`plan-row-${row}`)?.scrollIntoView({ block: "center", behavior: "smooth" });
    }, 0);
    window.setTimeout(() => setFlash(null), 1600);
  }

  const coverage = Math.round((1 - (dry?.empty_required_rate ?? 0)) * 100);
  const previewFields = (meta?.fields ?? []).filter((field) =>
    (dry?.samples ?? []).some((sample) => String(sample.values[field.code] ?? "").trim() !== ""),
  );

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex shrink-0 flex-wrap items-center gap-x-5 gap-y-1 border-b border-zinc-100 px-5 py-2.5 text-[12px] text-zinc-600">
        <span>
          试跑 <b className="font-semibold text-zinc-900 tabular-nums">{dry?.rows ?? 0}</b> 行
        </span>
        <span>
          必填覆盖 <b className={`font-semibold tabular-nums ${coverage >= 80 ? "text-emerald-700" : "text-amber-700"}`}>{coverage}%</b>
        </span>
        {missing.length > 0 ? (
          <span className="text-amber-700">文件缺少 {missing.length} 项必填</span>
        ) : (
          <span className="text-emerald-700">必填字段都有来源</span>
        )}
        {plan.plan_source ? <span className="text-zinc-400">计划来源：{PLAN_SOURCE_LABEL[plan.plan_source] ?? plan.plan_source}</span> : null}
        {!editable ? <span className="ml-auto text-zinc-400">结构已确认，只读查看</span> : null}
      </div>

      <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto p-4 lg:flex-row lg:overflow-hidden">
        <section className="flex min-h-[420px] min-w-0 flex-1 flex-col overflow-hidden rounded-lg border border-zinc-200 lg:min-h-0" aria-label="列与字段对应">
          <div className="flex shrink-0 flex-wrap items-center gap-2 border-b border-zinc-100 px-3 py-2 text-[12px]">
            {sheets.length > 1 ? (
              <div className="flex gap-1" role="tablist" aria-label="工作表">
                {sheets.map(({ sheet }, position) => (
                  <button
                    key={`${sheet.sheet}-${position}`}
                    type="button"
                    role="tab"
                    aria-selected={position === activeSheet}
                    className={`rounded-md px-2 py-1 transition ${position === activeSheet ? "bg-zinc-900 text-white" : "text-zinc-600 hover:bg-zinc-100"}`}
                    onClick={() => setActiveSheet(position)}
                  >
                    {sheet.sheet}
                    <span className={`ml-1 text-[10px] ${position === activeSheet ? "text-zinc-300" : "text-zinc-400"}`}>
                      {sheet.role === "reference" ? "参考表" : "数据表"}
                    </span>
                  </button>
                ))}
              </div>
            ) : (
              <span className="font-medium text-zinc-800">{current?.sheet.sheet}</span>
            )}
            <span className="text-[11px] text-zinc-400">
              {current?.sheet.row_mode === "grouped" ? "按主键合并续行" : "逐行读取"}，第 {current?.sheet.data_start} 行起
            </span>
            <div className="ml-auto flex gap-1 text-[11px]" role="group" aria-label="筛选列">
              {(
                [
                  ["all", `全部 ${rows.length}`],
                  ["mapped", `导入 ${mappedCount}`],
                  ["skipped", `不导入 ${rows.length - mappedCount}`],
                ] as const
              ).map(([key, text]) => (
                <button
                  key={key}
                  type="button"
                  aria-pressed={filter === key}
                  className={`rounded-full px-2.5 py-0.5 transition ${filter === key ? "bg-zinc-200 text-zinc-900" : "text-zinc-500 hover:bg-zinc-100"}`}
                  onClick={() => setFilter(key)}
                >
                  {text}
                </button>
              ))}
            </div>
          </div>
          {current?.sheet.role === "main" ? (
            <DedupeBar
              fields={meta?.fields ?? []}
              businessKey={meta?.business_key_fields ?? []}
              value={current.sheet.dedupe_by ?? []}
              editable={editable && !busy}
              onChange={(next) => onDedupeChange(current.index, next)}
            />
          ) : null}
          <div className="min-h-0 flex-1 overflow-auto [scrollbar-width:thin]">
            <table className="w-full table-fixed text-left text-[12px]">
              <colgroup>
                <col className="w-10" />
                <col className="w-[30%]" />
                <col />
                <col className="w-44" />
              </colgroup>
              <thead className="sticky top-0 z-10 bg-zinc-50 text-[11px] text-zinc-500">
                <tr>
                  <th className="px-3 py-2 text-center font-medium">#</th>
                  <th className="px-3 py-2 font-medium">文件中的列</th>
                  <th className="px-3 py-2 font-medium">样例值（前 3 行）</th>
                  <th className="px-3 py-2 font-medium">导入到字段</th>
                </tr>
              </thead>
              <tbody>
                {visibleRows.map((row) => {
                  const conflict = row.targets.some((target) => conflicts.has(target));
                  const split = (row.column.fields?.length ?? 0) > 0;
                  return (
                    <tr
                      key={row.key}
                      id={`plan-row-${row.key}`}
                      className={`border-b border-zinc-100 last:border-0 ${
                        flash === row.key ? "bg-sky-50" : conflict ? "bg-rose-50/60" : row.targets.length === 0 ? "text-zinc-400" : ""
                      } transition-colors`}
                    >
                      <td className="px-3 py-2 text-center tabular-nums text-zinc-400">
                        {row.position == null ? "—" : row.position + 1}
                      </td>
                      <td className="px-3 py-2">
                        <p className={`truncate ${row.targets.length ? "font-medium text-zinc-800" : ""}`} title={row.label}>
                          {row.label}
                        </p>
                        {row.repeat ? (
                          <p className="mt-0.5 text-[10px] text-amber-600">
                            文件里有 {row.repeat.total} 列同名，这是第 {row.repeat.nth} 个
                          </p>
                        ) : null}
                      </td>
                      <td className="px-3 py-2">
                        <p className="truncate text-zinc-500" title={row.samples.join("\n")}>
                          {row.samples.length ? row.samples.join("、") : <span className="text-zinc-300">空</span>}
                        </p>
                      </td>
                      <td className="px-3 py-1.5">
                        {split ? (
                          <p className="truncate text-zinc-700" title="拆分为多个字段，可在模板里调整">
                            拆分为 {row.targets.map((code) => labels.get(code) ?? code).join("、")}
                          </p>
                        ) : (
                          <select
                            className={`h-7 w-full min-w-0 rounded-md border bg-white px-1.5 text-[12px] disabled:bg-transparent disabled:opacity-100 ${
                              conflict ? "border-rose-300 text-rose-700" : "border-zinc-200"
                            }`}
                            value={row.column.field ?? ""}
                            disabled={!editable || busy || !current}
                            aria-label={`${row.label} 导入到字段`}
                            onChange={(event) =>
                              current && onFieldChange(current.index, row.index, row.label, event.target.value)
                            }
                          >
                            <option value="">不导入</option>
                            {(meta?.fields ?? []).map((field) => (
                              <option key={field.code} value={field.code}>
                                {field.label}
                                {field.required ? " *" : ""}
                              </option>
                            ))}
                          </select>
                        )}
                        {conflict ? <p className="mt-0.5 text-[10px] text-rose-600">该字段被多列选用，只能保留一列</p> : null}
                      </td>
                    </tr>
                  );
                })}
                {visibleRows.length === 0 ? (
                  <tr>
                    <td colSpan={4} className="px-3 py-8 text-center text-zinc-400">
                      没有符合筛选条件的列
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </section>

        <aside className="flex shrink-0 flex-col rounded-lg border border-zinc-200 lg:min-h-0 lg:w-72" aria-label="必填字段核对">
          <div className="shrink-0 border-b border-zinc-100 px-3 py-2">
            <p className="text-[12px] font-medium text-zinc-800">必填字段</p>
            <p className="mt-0.5 text-[11px] text-zinc-400">点击已对应的字段可定位到列</p>
          </div>
          <ul className="min-h-0 flex-1 divide-y divide-zinc-100 overflow-y-auto pb-2 text-[12px] [scrollbar-width:thin]">
            {required.map((field) => {
              const from = providers.get(field.code);
              const gap = gaps.get(field.code);
              const status = from
                ? gap?.reason === "empty_column"
                  ? "empty"
                  : "ok"
                : gap
                  ? "missing"
                  : "auto";
              return (
                <li key={field.code}>
                  <button
                    type="button"
                    disabled={!from}
                    className="flex w-full items-start gap-2 px-3 py-1.5 text-left transition enabled:hover:bg-zinc-50"
                    onClick={() => from && locate(from[0].sheetPos, from[0].row)}
                  >
                    <span
                      className={`mt-1.5 size-1.5 shrink-0 rounded-full ${
                        status === "ok" ? "bg-emerald-500" : status === "auto" ? "bg-sky-400" : "bg-amber-500"
                      }`}
                      aria-hidden="true"
                    />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-zinc-800">{field.label}</span>
                      <span
                        className={`block truncate text-[11px] ${
                          status === "ok" ? "text-zinc-400" : status === "auto" ? "text-sky-600" : "text-amber-700"
                        }`}
                      >
                        {status === "ok"
                          ? `来自「${from?.map((item) => item.label).join("、")}」`
                          : status === "empty"
                            ? `「${from?.[0].label}」整列为空`
                            : status === "auto"
                              ? "系统自动补齐"
                              : "文件中没有，需要人工补录"}
                      </span>
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
          {missing.length > 0 ? (
            <p className="shrink-0 border-t border-zinc-100 bg-amber-50/50 px-3 py-2 text-[11px] leading-4 text-amber-800">
              缺少的必填项可以先继续，下一步用「批量设置字段」统一填入。
            </p>
          ) : null}
        </aside>
      </div>

      {(dry?.samples ?? []).length > 0 ? (
        <div className="shrink-0 border-t border-zinc-100 px-4 py-2">
          <button
            type="button"
            className="flex items-center gap-1 text-[12px] text-zinc-600 hover:text-zinc-900"
            aria-expanded={previewOpen}
            onClick={() => setPreviewOpen((open) => !open)}
          >
            <ChevronDown className={`size-3.5 transition ${previewOpen ? "" : "-rotate-90"}`} aria-hidden="true" />
            试跑结果预览（前 {(dry?.samples ?? []).length} 行）
          </button>
          {previewOpen ? (
            <div className="mt-2 max-h-56 overflow-auto rounded-md border border-zinc-200 [scrollbar-width:thin]">
              <table className="w-full min-w-max text-left text-[11px]">
                <thead className="sticky top-0 bg-zinc-50 text-zinc-500">
                  <tr>
                    <th className="px-2 py-1.5 font-medium">行号</th>
                    {previewFields.map((field) => (
                      <th key={field.code} className="px-2 py-1.5 font-medium whitespace-nowrap">
                        {field.label}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {(dry?.samples ?? []).map((sample, index) => (
                    <tr key={`${sample.sheet}-${sample.row}-${index}`} className="border-t border-zinc-100">
                      <td className="px-2 py-1.5 tabular-nums text-zinc-400">{sample.row}</td>
                      {previewFields.map((field) => (
                        <td key={field.code} className="max-w-48 truncate px-2 py-1.5 whitespace-nowrap text-zinc-700">
                          {String(sample.values[field.code] ?? "")}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
        </div>
      ) : null}

      {editable ? (
        <div className="flex shrink-0 flex-wrap items-center gap-3 border-t border-zinc-200 bg-zinc-50/80 px-5 py-3">
          <label className="flex items-center gap-1.5 text-[12px] text-zinc-600">
            <input type="checkbox" checked={remember} onChange={(event) => onRememberChange(event.target.checked)} />
            记住这个结构，下次相同表头不再调用模型
          </label>
          {allConflicts.length > 0 ? (
            <span className="flex items-center gap-1 text-[12px] text-rose-600">
              <AlertTriangle className="size-3.5" aria-hidden="true" />
              {allConflicts.length} 个字段被多列选用，请先处理
            </span>
          ) : null}
          <button
            type="button"
            className={`${primaryButton} ml-auto`}
            disabled={busy || allConflicts.length > 0}
            onClick={onApply}
          >
            按此结构提取候选
          </button>
        </div>
      ) : null}
    </div>
  );
}

function DedupeBar({
  fields,
  businessKey,
  value,
  editable,
  onChange,
}: {
  fields: DatasetMeta["fields"];
  businessKey: string[];
  value: string[];
  editable: boolean;
  onChange: (next: string[]) => void;
}) {
  const labels = new Map(fields.map((field) => [field.code, field.label]));
  const name = (code: string) => labels.get(code) ?? code;
  const custom = value.length > 0;
  return (
    <div className="flex shrink-0 flex-wrap items-center gap-1.5 border-b border-zinc-100 px-3 py-2 text-[12px]">
      <span className="text-zinc-500">重复判定</span>
      {custom ? (
        value.map((code) => (
          <span key={code} className="inline-flex items-center gap-1 rounded-full bg-sky-50 py-0.5 pr-1 pl-2 text-[11px] text-sky-800">
            {name(code)}
            {editable ? (
              <button
                type="button"
                className="flex size-4 items-center justify-center rounded-full text-sky-500 hover:bg-sky-100 hover:text-sky-800"
                aria-label={`移除 ${name(code)}`}
                onClick={() => onChange(value.filter((item) => item !== code))}
              >
                <X className="size-3" aria-hidden="true" />
              </button>
            ) : null}
          </span>
        ))
      ) : (
        <span className="text-[11px] text-zinc-400">
          默认按业务主键（{businessKey.length ? businessKey.map(name).join(" + ") : "未配置"}）
        </span>
      )}
      <span className="text-[11px] text-zinc-400">{custom ? "都相同的行合并为一条" : ""}</span>
      {editable ? (
        <select
          className="ml-auto h-7 rounded-md border border-zinc-200 bg-white px-1.5 text-[12px] text-zinc-600"
          value=""
          aria-label="添加重复判定字段"
          onChange={(event) => event.target.value && onChange([...value, event.target.value])}
        >
          <option value="">{custom ? "再加一个字段" : "改为按指定字段判定"}</option>
          {fields
            .filter((field) => !value.includes(field.code))
            .map((field) => (
              <option key={field.code} value={field.code}>
                {field.label}
              </option>
            ))}
        </select>
      ) : null}
    </div>
  );
}
