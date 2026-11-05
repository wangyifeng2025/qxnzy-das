"use client";

import { FileSpreadsheet, X } from "lucide-react";
import { useState } from "react";

import { primaryButton } from "@/components/page-bits";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { ApiError, upload } from "@/lib/api";

export type ReferenceResult = {
  file_name: string;
  sheets: { name: string; rows: number; columns: { header: string; field: string | null; label: string | null }[] }[];
  sheet: string | null;
  key: string[];
  fill: string[];
  overwrite: boolean;
  candidates: number;
  matched: number;
  unmatched: number;
  ambiguous: number;
  changed: number;
  overwritten: number;
  unmatched_samples: string[];
  applied: boolean;
  ready: number;
};

type Choice = { sheet: string; key: string; fill: string[]; overwrite: boolean };

/** 给已有任务补传参照表（例如专业名称—专业代码对照表），按共同字段批量回填候选。 */
export function ReferenceDialog({
  open,
  onOpenChange,
  taskId,
  onApplied,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  taskId: string;
  onApplied: (result: ReferenceResult) => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<ReferenceResult | null>(null);
  const [choice, setChoice] = useState<Choice | null>(null);
  const [loading, setLoading] = useState<"" | "preview" | "apply">("");
  const [error, setError] = useState("");

  function reset() {
    setFile(null);
    setResult(null);
    setChoice(null);
    setError("");
  }

  /** next 为 null 时让后端推荐匹配字段和回填字段；sheet 指定换到哪张工作表。 */
  async function send(target: File, next: Choice | null, apply: boolean, sheet = "") {
    const body = new FormData();
    body.append("file", target);
    if (sheet) body.append("sheet", sheet);
    if (next) {
      body.append("sheet", next.sheet);
      body.append("key", next.key);
      // 全部取消勾选时传一个逗号，后端据此识别为“不回填任何字段”，而不是“按默认全部回填”
      body.append("fill", next.fill.join(",") || ",");
      body.append("overwrite", String(next.overwrite));
    }
    body.append("apply", String(apply));
    return upload<ReferenceResult>(`/api/ingestion/tasks/${taskId}/reference`, body);
  }

  async function preview(target: File, next: Choice | null, sheet = "") {
    setLoading("preview");
    setError("");
    try {
      const body = await send(target, next, false, sheet);
      setResult(body);
      setChoice({ sheet: body.sheet ?? "", key: body.key[0] ?? "", fill: body.fill, overwrite: body.overwrite });
    } catch (reason: unknown) {
      setResult(null);
      setError(reason instanceof ApiError ? reason.message : "参照表读取失败");
    } finally {
      setLoading("");
    }
  }

  async function apply() {
    if (!file || !choice) return;
    setLoading("apply");
    setError("");
    try {
      const body = await send(file, choice, true);
      onApplied(body);
      reset();
      onOpenChange(false);
    } catch (reason: unknown) {
      setError(reason instanceof ApiError ? reason.message : "回填失败");
    } finally {
      setLoading("");
    }
  }

  function change(patch: Partial<Choice>) {
    if (!file || !choice) return;
    if (patch.sheet !== undefined && patch.sheet !== choice.sheet) {
      // 换工作表后让后端重新推荐匹配字段和回填字段
      void preview(file, null, patch.sheet);
      return;
    }
    const next = { ...choice, ...patch };
    if (patch.key !== undefined) next.fill = next.fill.filter((code) => code !== patch.key);
    setChoice(next);
    void preview(file, next);
  }

  const sheet = result?.sheets.find((item) => item.name === choice?.sheet);
  const mapped = (sheet?.columns ?? []).filter((column) => column.field);
  const labelOf = (code: string) => mapped.find((column) => column.field === code)?.label ?? code;
  const busy = Boolean(loading);

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (busy) return;
        if (!next) reset();
        onOpenChange(next);
      }}
    >
      <DialogContent
        showCloseButton={false}
        overlayClassName="bg-zinc-900/40"
        className="flex max-h-[85vh] w-full max-w-[calc(100%-2rem)] flex-col gap-0 overflow-hidden bg-white p-0 text-zinc-900 ring-zinc-200 sm:max-w-xl"
      >
        <DialogHeader className="shrink-0 flex-row items-start justify-between gap-3 space-y-0 border-b border-zinc-100 px-5 py-3.5">
          <div>
            <DialogTitle className="text-[14px] font-semibold tracking-tight text-zinc-900">补传参照表</DialogTitle>
            <DialogDescription className="mt-0.5 text-[11px] leading-4 text-zinc-500">
              上传一份含共同字段的表（例如“专业名称、专业代码”对照表），按共同字段回填当前任务里未确认的候选，回填后自动重新校验。
            </DialogDescription>
          </div>
          <button
            type="button"
            className="flex size-7 shrink-0 items-center justify-center rounded-md text-zinc-400 transition hover:bg-zinc-100 hover:text-zinc-600 disabled:opacity-40"
            onClick={() => {
              reset();
              onOpenChange(false);
            }}
            disabled={busy}
            aria-label="关闭"
          >
            <X className="size-3.5" />
          </button>
        </DialogHeader>

        <div className="min-h-0 flex-1 space-y-3.5 overflow-y-auto px-5 py-4 text-[12px]">
          <label className="flex min-h-20 cursor-pointer flex-col items-center justify-center gap-1.5 rounded-lg border border-dashed border-zinc-300 px-3 py-3 text-center text-zinc-500 transition hover:border-zinc-400 hover:bg-zinc-50/60 focus-within:border-zinc-500">
            <FileSpreadsheet className="size-5 text-zinc-400" aria-hidden="true" />
            {file ? (
              <span className="break-all text-zinc-800">
                {file.name}
                <span className="mt-0.5 block text-[11px] text-zinc-400">点击可重新选择</span>
              </span>
            ) : (
              <span>
                点击选择参照表
                <span className="mt-0.5 block text-[11px] text-zinc-400">xlsx、xls、csv；表头要能对应到本数据表的字段</span>
              </span>
            )}
            <input
              type="file"
              className="sr-only"
              accept=".xlsx,.xls,.csv"
              disabled={busy}
              onChange={(event) => {
                const picked = event.target.files?.[0] ?? null;
                event.target.value = "";
                setFile(picked);
                setResult(null);
                setChoice(null);
                if (picked) void preview(picked, null);
              }}
            />
          </label>

          {error ? <p className="rounded-md bg-rose-50 px-3 py-2 text-[11px] leading-4 text-rose-700">{error}</p> : null}

          {loading === "preview" && !result ? (
            <p className="flex items-center gap-1.5 text-zinc-500">
              <span className="size-3 animate-spin rounded-full border-2 border-zinc-300 border-t-zinc-700" aria-hidden="true" />
              正在读取参照表…
            </p>
          ) : null}

          {result && choice ? (
            <>
              <div className="grid gap-3 sm:grid-cols-2">
                {result.sheets.length > 1 ? (
                  <label className="block">
                    <span className="text-zinc-600">工作表</span>
                    <select
                      className="mt-1 h-8 w-full rounded-md border border-zinc-200 bg-white px-2"
                      value={choice.sheet}
                      disabled={busy}
                      onChange={(event) => change({ sheet: event.target.value })}
                    >
                      {result.sheets.map((item) => (
                        <option key={item.name} value={item.name}>
                          {item.name}（{item.rows} 行）
                        </option>
                      ))}
                    </select>
                  </label>
                ) : null}
                <label className="block">
                  <span className="text-zinc-600">按哪个字段匹配</span>
                  <select
                    className="mt-1 h-8 w-full rounded-md border border-zinc-200 bg-white px-2"
                    value={choice.key}
                    disabled={busy}
                    onChange={(event) => change({ key: event.target.value })}
                  >
                    {choice.key ? null : <option value="">请选择</option>}
                    {mapped.map((column) => (
                      <option key={column.field} value={column.field ?? ""}>
                        {column.label}（表头：{column.header}）
                      </option>
                    ))}
                  </select>
                </label>
              </div>

              <fieldset>
                <legend className="text-zinc-600">回填哪些字段</legend>
                <div className="mt-1.5 flex flex-wrap gap-x-4 gap-y-1.5">
                  {mapped
                    .filter((column) => column.field !== choice.key)
                    .map((column) => {
                      const code = column.field ?? "";
                      return (
                        <label key={code} className="flex items-center gap-1.5 text-zinc-700">
                          <input
                            type="checkbox"
                            checked={choice.fill.includes(code)}
                            disabled={busy}
                            onChange={(event) =>
                              change({
                                fill: event.target.checked
                                  ? [...choice.fill, code]
                                  : choice.fill.filter((item) => item !== code),
                              })
                            }
                          />
                          {column.label}
                        </label>
                      );
                    })}
                </div>
                <label className="mt-2 flex items-center gap-1.5 text-zinc-600">
                  <input
                    type="checkbox"
                    checked={choice.overwrite}
                    disabled={busy}
                    onChange={(event) => change({ overwrite: event.target.checked })}
                  />
                  覆盖候选里已有的值
                  <span className="text-[11px] text-zinc-400">（取消后只填空着的字段）</span>
                </label>
              </fieldset>

              <div className="rounded-lg border border-zinc-200 bg-zinc-50/70 px-3 py-2.5 leading-5 text-zinc-600">
                {choice.key ? (
                  <>
                    按「{labelOf(choice.key)}」匹配：待确认候选 {result.candidates} 条，命中{" "}
                    <b className="font-semibold text-zinc-900 tabular-nums">{result.matched}</b> 条，其中{" "}
                    <b className="font-semibold text-emerald-700 tabular-nums">{result.changed}</b> 条会被修改
                    {result.overwritten > 0 ? `（覆盖已有值 ${result.overwritten} 处）` : ""}。
                    {result.unmatched > 0 ? <span className="block text-amber-700">未命中 {result.unmatched} 条，保持原样。</span> : null}
                    {result.ambiguous > 0 ? (
                      <span className="block text-amber-700">
                        {result.ambiguous} 条在参照表里对应多个不同的值，无法确定，已跳过。
                      </span>
                    ) : null}
                  </>
                ) : (
                  "参照表里没有与候选取值相同的字段，请换一个匹配字段或换一份参照表。"
                )}
                {loading === "preview" ? <span className="ml-1 text-zinc-400">正在重新计算…</span> : null}
              </div>

              {result.unmatched_samples.length > 0 ? (
                <div>
                  <p className="text-[11px] text-zinc-500">未命中的取值（最多显示 20 个）：</p>
                  <ul className="mt-1 flex flex-wrap gap-1">
                    {result.unmatched_samples.map((item) => (
                      <li key={item} className="max-w-full truncate rounded bg-amber-50 px-1.5 py-0.5 text-[11px] text-amber-800" title={item}>
                        {item}
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </>
          ) : null}
        </div>

        <DialogFooter className="mx-0 mb-0 shrink-0 flex-row justify-end gap-2 border-t border-zinc-100 bg-white px-5 py-3">
          <button
            type="button"
            className="h-9 rounded-md border border-zinc-200 bg-white px-3 text-xs font-medium text-zinc-700 transition hover:bg-zinc-50 disabled:opacity-45"
            disabled={busy}
            onClick={() => {
              reset();
              onOpenChange(false);
            }}
          >
            取消
          </button>
          <button
            type="button"
            className={primaryButton}
            disabled={busy || !result || result.changed === 0}
            onClick={() => void apply()}
          >
            {loading === "apply" ? (
              <span className="size-3 animate-spin rounded-full border-2 border-white/40 border-t-white" aria-hidden="true" />
            ) : null}
            {loading === "apply" ? "正在回填" : `回填 ${result?.changed ?? 0} 条候选`}
          </button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
