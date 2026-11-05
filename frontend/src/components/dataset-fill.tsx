"use client";

import type { RowSelectionState } from "@tanstack/react-table";
import { Plus, Search } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { createAppColumnHelper, DataTable, useAppTable } from "@/components/data-table";
import { FormCombobox } from "@/components/form-combobox";
import { fieldClass, ProgressBar } from "@/components/page-bits";
import { useToast } from "@/components/toast";
import { ApiError, api, download, upload } from "@/lib/api";
import {
  canWithdraw,
  optionLabel,
  STATUS_LABEL,
  type DatasetMeta,
  type FieldMeta,
  type RecordDetail,
  type RecordItem,
  type RecordPage,
} from "@/lib/records";

/** 导入写入时每批提交的行数：分批提交让进度条反映真实写入量，单批失败也能保住已写入的数据。 */
const IMPORT_BATCH = 40;
/** 批量提交、撤回、审核时每次请求的条数，后端单次上限 200。 */
const ACTION_BATCH = 100;
const PAGE_SIZES = [8, 20, 50];
const STATUS_FILTERS = [
  { value: "", label: "全部状态" },
  { value: "draft,returned", label: "草稿 / 已退回" },
  { value: "pending_dept,pending_domain,pending_center", label: "审核中" },
  { value: "published", label: "已发布" },
];

type BatchAction = "submit" | "withdraw" | "approve" | "return";
type BatchResult = { done: number; failed: { id: string; reason: string }[] };

function submittable(row: RecordItem) {
  return row.status === "draft" || row.status === "returned";
}

function selectable(row: RecordItem, meta: DatasetMeta | null) {
  if (row.can_review) return true;
  return Boolean(meta?.can_fill) && (submittable(row) || canWithdraw(row, meta?.account ?? ""));
}

function blankDraft(meta: DatasetMeta) {  const draft: Record<string, string> = {};
  for (const field of meta.fields) draft[field.code] = field.default ?? "";
  if (meta.filler_type === "teacher") {
    if (meta.owner_field) draft[meta.owner_field] = meta.account;
    if (meta.owner_name_field) draft[meta.owner_name_field] = meta.user_name;
  }
  if (meta.departments.length === 1) draft[meta.department_field] = meta.departments[0];
  return draft;
}

function draftFromPayload(meta: DatasetMeta, payload: Record<string, string | number | null>) {
  const draft = blankDraft(meta);
  for (const field of meta.fields) {
    const value = payload[field.code];
    if (value != null) draft[field.code] = String(value);
  }
  return draft;
}

function toPayload(meta: DatasetMeta, draft: Record<string, string>) {
  const body: Record<string, string | number | null> = {};
  for (const field of meta.fields) {
    if (field.visible_when && draft[field.visible_when] !== "1") {
      body[field.code] = null;
      continue;
    }
    const text = (draft[field.code] ?? "").trim();
    if (field.kind === "number") body[field.code] = text === "" ? null : Number(text);
    else body[field.code] = text;
  }
  return body;
}

type ImportRow = {
  row: number;
  ok: boolean;
  errors: string[];
  payload: Record<string, unknown>;
};

const fillHelper = createAppColumnHelper<RecordItem>();
const importHelper = createAppColumnHelper<ImportRow>();

function optionsFor(meta: DatasetMeta, field: FieldMeta) {
  if (field.dict_code === "departments") {
    return meta.departments.map((name) => ({ value: name, label: name }));
  }
  if (field.dict_code === "titles") return meta.title_ranks.map((name) => ({ value: name, label: name }));
  return field.dict_code ? (meta.dicts[field.dict_code] ?? []) : [];
}

export function DatasetFill({ code, recordId }: { code: string; recordId?: string | null }) {
  const toast = useToast();
  const [meta, setMeta] = useState<DatasetMeta | null>(null);
  const [page, setPage] = useState<RecordPage | null>(null);
  const [keyword, setKeyword] = useState("");
  const [query, setQuery] = useState("");
  const [currentPage, setCurrentPage] = useState(1);
  const [loadError, setLoadError] = useState("");
  const [editing, setEditing] = useState<string | "new" | null>(null);
  const [editingStatus, setEditingStatus] = useState("draft");
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [importRows, setImportRows] = useState<ImportRow[] | null>(null);
  const [importSelection, setImportSelection] = useState<RowSelectionState>({});
  const [importing, setImporting] = useState(false);
  /** 导入写入进度：done 为已写入行数，total 为本次待写入行数；null 表示不在写入中。 */
  const [importProgress, setImportProgress] = useState<{ done: number; total: number } | null>(null);
  const [importError, setImportError] = useState("");
  const [pageSize, setPageSize] = useState(PAGE_SIZES[0]);
  /** 已勾选记录的快照：翻页后勾选仍保留，需要靠它知道每条记录的状态。 */
  const [chosen, setChosen] = useState<Record<string, RecordItem>>({});
  const selection = useMemo<RowSelectionState>(
    () => Object.fromEntries(Object.keys(chosen).map((id) => [id, true])),
    [chosen],
  );
  const [acting, setActing] = useState<"" | BatchAction>("");
  const [statusFilter, setStatusFilter] = useState("");
  const [editingReviewable, setEditingReviewable] = useState(false);
  /** 审核意见弹窗：ids 为本次要审核的记录。 */
  const [reviewing, setReviewing] = useState<{ action: "approve" | "return"; ids: string[] } | null>(null);
  const [reviewComment, setReviewComment] = useState("");

  async function loadList(nextPage: number, nextQuery: string, size = pageSize, nextStatus = statusFilter) {
    const params = new URLSearchParams({ page: String(nextPage), page_size: String(size) });
    if (nextQuery.trim()) params.set("keyword", nextQuery.trim());
    if (nextStatus) params.set("status", nextStatus);
    const result = await api<RecordPage>(`/api/datasets/${code}/records?${params.toString()}`);
    setPage(result);
    setCurrentPage(nextPage);
    // 记录状态可能已变（例如单条提交、删除），刷新勾选快照并去掉已不能操作的
    const fresh = new Map(result.items.map((row) => [row.id, row]));
    setChosen((current) => {
      const next: Record<string, RecordItem> = {};
      for (const [id, row] of Object.entries(current)) {
        const latest = fresh.get(id) ?? row;
        if (selectable(latest, meta)) next[id] = latest;
      }
      return next;
    });
  }

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const nextMeta = await api<DatasetMeta>(`/api/datasets/${code}/meta`);
        const result = await api<RecordPage>(`/api/datasets/${code}/records?page=1&page_size=8`);
        if (cancelled) return;
        setMeta(nextMeta);
        setPage(result);
        if (recordId) {
          const detail = await api<RecordDetail>(`/api/records/${recordId}`);
          if (cancelled) return;
          setDraft(draftFromPayload(nextMeta, detail.payload));
          setEditingStatus(detail.status);
          setEditingReviewable(Boolean(detail.can_review));
          setEditing(recordId);
        }
      } catch (error) {
        if (!cancelled) setLoadError(error instanceof ApiError ? error.message : "加载失败");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [code, recordId]);

  const records = useMemo(() => page?.items ?? [], [page]);

  const columns = useMemo(() => {
    if (!meta) return [];
    return fillHelper.columns([
      fillHelper.display({
        id: "select",
        header: ({ table }) => {
          const all = table.getIsAllPageRowsSelected();
          return (
            <input
              type="checkbox"
              aria-label="勾选本页可操作的记录"
              title="勾选本页可提交、撤回或审核的记录"
              className="size-3.5 cursor-pointer accent-zinc-900 disabled:cursor-not-allowed disabled:opacity-40"
              disabled={!table.getRowModel().rows.some((row) => row.getCanSelect())}
              checked={all}
              ref={(element) => {
                if (element) element.indeterminate = !all && table.getIsSomePageRowsSelected();
              }}
              onChange={table.getToggleAllPageRowsSelectedHandler()}
            />
          );
        },
        cell: ({ row }) => (
          <input
            type="checkbox"
            aria-label="勾选该记录"
            className="size-3.5 cursor-pointer accent-zinc-900 disabled:cursor-not-allowed disabled:opacity-30"
            disabled={!row.getCanSelect()}
            checked={row.getIsSelected()}
            onChange={row.getToggleSelectedHandler()}
          />
        ),
        meta: { headClassName: "w-10 px-3", cellClassName: "w-10 px-3 py-3" },
      }),
      ...meta.list_fields.map((field) =>
        fillHelper.accessor((row: RecordItem) => optionLabel(meta, field, row.summary[field]), {
          id: field,
          header: meta.fields.find((item) => item.code === field)?.label ?? field,
          meta: { cellClassName: "px-3 py-3 text-zinc-700" },
        }),
      ),
      fillHelper.accessor((row: RecordItem) => STATUS_LABEL[row.status] ?? row.status, {
        id: "status",
        header: "状态",
        meta: { cellClassName: "px-3 py-3 text-zinc-700" },
      }),
      fillHelper.accessor((row: RecordItem) => row.updated_at.replace("T", " ").slice(0, 16), {
        id: "updated",
        header: "更新时间",
        meta: { cellClassName: "px-3 py-3 text-zinc-700" },
      }),
      fillHelper.display({
        id: "actions",
        header: "操作",
        meta: { headClassName: "text-right", cellClassName: "px-3 py-3 text-right" },
        cell: ({ row }) => (
          <div className="whitespace-nowrap">
            <button type="button" className="text-[10px] font-medium text-zinc-600" onClick={() => void openRecord(row.original.id)}>
              {submittable(row.original) ? "编辑" : row.original.can_review ? "审核" : "查看"}
            </button>
            {row.original.status === "draft" || row.original.status === "returned" ? (
              <>
                <span className="mx-1.5 text-zinc-300">|</span>
                <button type="button" className="text-[10px] font-medium text-zinc-800" onClick={() => void act(row.original.id, "submit")}>提交</button>
                <span className="mx-1.5 text-zinc-300">|</span>
                <button type="button" className="text-[10px] font-medium text-rose-500" onClick={() => void act(row.original.id, "delete")}>删除</button>
              </>
            ) : null}
            {canWithdraw(row.original, meta.account) ? (
              <>
                <span className="mx-1.5 text-zinc-300">|</span>
                <button type="button" className="text-[10px] font-medium text-zinc-800" onClick={() => void act(row.original.id, "withdraw")}>撤回</button>
              </>
            ) : null}
            {row.original.can_revise ? (
              <>
                <span className="mx-1.5 text-zinc-300">|</span>
                <button type="button" className="text-[10px] font-medium text-zinc-800" onClick={() => void act(row.original.id, "revise")}>修改已发布</button>
              </>
            ) : null}
          </div>
        ),
      }),
    ]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [meta]);

  const table = useAppTable({
    data: records,
    columns,
    getRowId: (row) => row.id,
    manualPagination: true,
    enableRowSelection: (row) => selectable(row.original, meta),
    state: { rowSelection: selection },
    onRowSelectionChange: (updater) => {
      const next = typeof updater === "function" ? updater(selection) : updater;
      setChosen((current) => {
        const kept: Record<string, RecordItem> = {};
        for (const id of Object.keys(next)) {
          const found = records.find((row) => row.id === id) ?? current[id];
          if (found) kept[id] = found;
        }
        return kept;
      });
    },
  });

  const importColumns = useMemo(
    () =>
      importHelper.columns([
        importHelper.display({
          id: "select",
          header: "选择",
          meta: { headClassName: "px-3 py-2", cellClassName: "px-3 py-2" },
          cell: ({ row }) => (
            <input
              type="checkbox"
              disabled={!row.getCanSelect()}
              checked={row.getIsSelected()}
              onChange={row.getToggleSelectedHandler()}
            />
          ),
        }),
        importHelper.accessor("row", {
          header: "行号",
          meta: { headClassName: "px-3 py-2", cellClassName: "px-3 py-2" },
        }),
        importHelper.display({
          id: "result",
          header: "结果",
          meta: { headClassName: "px-3 py-2", cellClassName: "px-3 py-2 text-zinc-600 whitespace-normal" },
          cell: ({ row }) => (row.original.ok ? "可以导入" : row.original.errors.join("；")),
        }),
      ]),
    [],
  );

  const importData = useMemo(() => importRows ?? [], [importRows]);

  const importTable = useAppTable({
    data: importData,
    columns: importColumns,
    getRowId: (row) => String(row.row),
    enableRowSelection: (row) => row.original.ok,
    state: { rowSelection: importSelection },
    onRowSelectionChange: setImportSelection,
  });

  const picked = useMemo(() => Object.keys(importSelection).map(Number), [importSelection]);

  if (loadError) return <div className="p-6 text-sm text-rose-600">{loadError}</div>;
  if (!meta || !page) return <div className="p-6 text-sm text-zinc-400">正在加载{code}</div>;

  const editable = meta.can_fill;
  const pages = Math.max(1, Math.ceil(page.total / page.page_size));
  const pickedRows = Object.values(chosen);
  const toSubmit = pickedRows.filter(submittable).map((row) => row.id);
  const toWithdraw = pickedRows.filter((row) => canWithdraw(row, meta.account)).map((row) => row.id);
  const toReview = pickedRows.filter((row) => row.can_review).map((row) => row.id);
  const center = meta.filler_type === "center";
  const approveLabel = center ? "审核发布" : "审核通过";

  function openNew() {
    setDraft(blankDraft(meta!));
    setEditingStatus("draft");
    setEditingReviewable(false);
    setEditing("new");
  }

  async function openRecord(id: string) {
    try {
      const detail = await api<RecordDetail>(`/api/records/${id}`);
      setDraft(draftFromPayload(meta!, detail.payload));
      setEditingStatus(detail.status);
      setEditingReviewable(Boolean(detail.can_review));
      setEditing(id);
    } catch (error) {
      toast(error instanceof ApiError ? error.message : "无法打开记录", "error");
    }
  }

  async function persist(submit: boolean) {
    if (!editing || !meta?.can_fill) return;
    setSaving(true);
    try {
      const body = JSON.stringify({ payload: toPayload(meta, draft) });
      const saved =
        editing === "new"
          ? await api<RecordDetail>(`/api/datasets/${code}/records`, { method: "POST", body })
          : await api<RecordDetail>(`/api/records/${editing}`, { method: "PUT", body });
      const finalRecord = submit
        ? await api<RecordDetail>(`/api/records/${saved.id}/submit`, { method: "POST" })
        : saved;
      const warnings = finalRecord.warnings.length ? finalRecord.warnings.join("；") : "";
      toast(warnings ? `已${submit ? "提交" : "保存"}。${warnings}` : submit ? "已提交审核" : "已保存草稿");
      setEditing(null);
      await loadList(currentPage, query);
    } catch (error) {
      toast(error instanceof ApiError ? error.message : "保存失败", "error");
    } finally {
      setSaving(false);
    }
  }

  async function previewFile(file: File) {
    const body = new FormData();
    body.append("file", file);
    setImporting(true);
    try {
      const rows = await upload<ImportRow[]>(`/api/datasets/${code}/imports`, body);
      setImportRows(rows);
      setImportSelection(
        Object.fromEntries(rows.filter((item) => item.ok).map((item) => [String(item.row), true])),
      );
    } catch (error) {
      toast(error instanceof ApiError ? error.message : "导入失败", "error");
    } finally {
      setImporting(false);
    }
  }

  async function commitImport(submit: boolean) {
    const rows = (importRows ?? []).filter((item) => item.ok && picked.includes(item.row));
    const payloads = rows.map((item) => item.payload);
    if (payloads.length === 0) {
      toast("请选择至少一行有效数据", "info");
      return;
    }
    let done = 0;
    let created = 0;
    let submitted = 0;
    setImportError("");
    setImporting(true);
    setImportProgress({ done: 0, total: payloads.length });
    try {
      for (let start = 0; start < payloads.length; start += IMPORT_BATCH) {
        const batch = payloads.slice(start, start + IMPORT_BATCH);
        const result = await api<{ created: number; submitted: number }>(`/api/datasets/${code}/imports/commit`, {
          method: "POST",
          body: JSON.stringify({ payloads: batch, submit }),
        });
        created += result.created;
        submitted += result.submitted;
        done += batch.length;
        setImportProgress({ done, total: payloads.length });
      }
      toast(submit ? `已提交 ${submitted} 行` : `已保存 ${created} 条草稿`);
      setImportRows(null);
      await loadList(1, query);
    } catch (error) {
      const message = error instanceof ApiError ? error.message : "导入失败";
      setImportError(
        done > 0
          ? `已写入 ${done}/${payloads.length} 行，剩余 ${payloads.length - done} 行未写入：${message}。已写入的行已从勾选中移除，可再次提交剩余行。`
          : `导入失败：${message}`,
      );
      toast(`导入未完成：${message}`, "error");
      // 已写入的行取消勾选，避免重试时重复生成记录。
      const written = new Set(rows.slice(0, done).map((item) => String(item.row)));
      setImportSelection((current) =>
        Object.fromEntries(Object.entries(current).filter(([key]) => !written.has(key))),
      );
      await loadList(1, query).catch(() => undefined);
    } finally {
      setImportProgress(null);
      setImporting(false);
    }
  }

  async function batch(action: BatchAction, ids: string[], comment = "") {
    if (ids.length === 0 || acting) return false;
    setActing(action);
    let done = 0;
    let processed = 0;
    const failed: BatchResult["failed"] = [];
    try {
      for (; processed < ids.length; processed += ACTION_BATCH) {
        const result = await api<BatchResult>("/api/records/batch", {
          method: "POST",
          body: JSON.stringify({ action, comment, ids: ids.slice(processed, processed + ACTION_BATCH) }),
        });
        done += result.done;
        failed.push(...result.failed);
      }
    } catch (error) {
      failed.push(
        ...ids.slice(processed).map((id) => ({
          id,
          reason: error instanceof ApiError ? error.message : "请求失败",
        })),
      );
    } finally {
      setActing("");
    }
    const verb = { submit: "提交", withdraw: "撤回", approve: approveLabel, return: "退回" }[action];
    if (failed.length === 0) {
      toast(`已${verb} ${done} 条`);
    } else {
      const reasons = [...new Set(failed.map((item) => item.reason))].slice(0, 3).join("；");
      toast(`已${verb} ${done} 条，${failed.length} 条未${verb}：${reasons}`, done > 0 ? "info" : "error");
    }
    // 失败的记录保持勾选，便于修改后重试
    const left = new Set(failed.map((item) => item.id));
    setChosen((current) => Object.fromEntries(Object.entries(current).filter(([id]) => left.has(id))));
    await loadList(currentPage, query).catch(() => undefined);
    return done > 0;
  }

  async function confirmReview() {
    if (!reviewing) return;
    const comment = reviewComment.trim();
    if (reviewing.action === "return" && !comment) {
      toast("退回必须填写意见", "info");
      return;
    }
    const changed = await batch(reviewing.action, reviewing.ids, comment);
    setReviewing(null);
    if (changed && editing && reviewing.ids.includes(editing)) setEditing(null);
  }

  function startReview(action: "approve" | "return", ids: string[]) {
    setReviewComment("");
    setReviewing({ action, ids });
  }

  function clearSelection() {
    setChosen({});
  }

  async function act(id: string, action: "delete" | "withdraw" | "revise" | "submit") {
    try {
      await api(`/api/records/${id}${action === "delete" ? "" : `/${action}`}`, {
        method: action === "delete" ? "DELETE" : "POST",
      });
      toast(action === "delete" ? "已删除" : action === "withdraw" ? "已撤回" : action === "revise" ? "已生成新草稿" : "已提交");
      await loadList(1, query);
    } catch (error) {
      toast(error instanceof ApiError ? error.message : "操作失败", "error");
    }
  }

  return (
    <div className="mx-auto max-w-400 p-5 xl:p-6">
      <section className="overflow-hidden rounded-lg border border-zinc-200 bg-white shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-3 border-b border-zinc-100 px-5 py-4">
          <div>
            <h1 className="text-base font-semibold tracking-tight">{meta.name}</h1>
            <p className="mt-1 text-[11px] text-zinc-400">
              {meta.code}
              {meta.department_name ? ` · ${meta.department_name}` : ""}
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button type="button" className="h-9 rounded-md border border-zinc-200 px-3 text-[11px]" onClick={() => void download(`/api/datasets/${code}/export`, `${code}.csv`).catch((error: unknown) => toast(error instanceof ApiError ? error.message : "导出失败", "error"))}>导出</button>
            {meta.can_export_sensitive ? (
              <button type="button" className="h-9 rounded-md border border-zinc-200 px-3 text-[11px]" onClick={() => void download(`/api/datasets/${code}/export?reveal=true`, `${code}-plain.csv`).catch((error: unknown) => toast(error instanceof ApiError ? error.message : "导出失败", "error"))}>导出明文</button>
            ) : null}
            {editable ? (
              <button type="button" className="h-9 rounded-md border border-zinc-200 px-3 text-[11px]" onClick={() => void download(`/api/datasets/${code}/template`, `${code}.xlsx`).catch((error: unknown) => toast(error instanceof ApiError ? error.message : "下载失败", "error"))}>下载模板</button>
            ) : null}
            {editable ? (
              <label className="flex h-9 cursor-pointer items-center rounded-md border border-zinc-200 px-3 text-[11px]">
                {importing ? "正在读取" : "导入"}
                <input
                  type="file"
                  accept=".xlsx,.csv"
                  className="hidden"
                  onChange={(event) => {
                    const file = event.target.files?.[0];
                    event.target.value = "";
                    if (file) void previewFile(file);
                  }}
                />
              </label>
            ) : null}
            {editable ? (
              <button type="button" className="flex h-9 items-center gap-1.5 rounded-md bg-zinc-900 px-3.5 text-[11px] font-medium text-white" onClick={openNew}>
                <Plus className="size-3.5" aria-hidden="true" />
                新增一条
              </button>
            ) : null}
          </div>
        </div>
        <form
          className="flex flex-wrap items-center gap-2 border-b border-zinc-100 px-5 py-2.5"
          onSubmit={(event) => {
            event.preventDefault();
            setQuery(keyword);
            void loadList(1, keyword).catch((error: unknown) => toast(error instanceof ApiError ? error.message : "查询失败", "error"));
          }}
        >
          <label className="flex h-8 w-56 items-center gap-2 rounded-md border border-zinc-200 bg-zinc-50/60 px-2.5">
            <Search className="size-3 text-zinc-400" aria-hidden="true" />
            <input value={keyword} onChange={(event) => setKeyword(event.target.value)} className="w-full bg-transparent text-[10px] outline-none" placeholder="搜索关键字" />
          </label>
          <button type="submit" className="h-8 rounded-md border border-zinc-200 px-3 text-[10px] text-zinc-600">查询</button>
          <select
            className="h-8 rounded-md border border-zinc-200 bg-white px-2 text-[10px] text-zinc-600"
            aria-label="按状态筛选"
            value={statusFilter}
            onChange={(event) => {
              const next = event.target.value;
              setStatusFilter(next);
              void loadList(1, query, pageSize, next).catch((error: unknown) => toast(error instanceof ApiError ? error.message : "加载失败", "error"));
            }}
          >
            {STATUS_FILTERS.map((item) => (
              <option key={item.value} value={item.value}>
                {item.label}
              </option>
            ))}
          </select>
          <div className="flex flex-wrap items-center gap-2 rounded-md bg-sky-50 px-2.5 py-1 text-[10px] text-sky-800">
            <span>
              已选 <b className="tabular-nums">{pickedRows.length}</b> 条
            </span>
            {editable ? (
              <>
                <button
                  type="button"
                  className="h-6 rounded bg-zinc-900 px-2 font-medium text-white disabled:opacity-40"
                  disabled={Boolean(acting) || toSubmit.length === 0}
                  title="提交勾选中的草稿和已退回记录"
                  onClick={() => void batch("submit", toSubmit)}
                >
                  {acting === "submit" ? "提交中…" : `批量提交（${toSubmit.length}）`}
                </button>
                <button
                  type="button"
                  className="h-6 rounded border border-zinc-300 bg-white px-2 font-medium text-zinc-700 disabled:opacity-40"
                  disabled={Boolean(acting) || toWithdraw.length === 0}
                  title="撤回勾选中刚提交、尚未审核的记录"
                  onClick={() => void batch("withdraw", toWithdraw)}
                >
                  {acting === "withdraw" ? "撤回中…" : `批量撤回（${toWithdraw.length}）`}
                </button>
              </>
            ) : null}
            {meta.can_review ? (
              <>
                <span className="h-4 w-px bg-sky-200" aria-hidden="true" />
                <button
                  type="button"
                  className="h-6 rounded bg-emerald-600 px-2 font-medium text-white disabled:opacity-40"
                  disabled={Boolean(acting) || toReview.length === 0}
                  title={center ? "通过勾选中的待审记录并发布；尚在系部、业务部门环节的记录将跳级发布" : "通过勾选中的待审记录，进入下一审核环节"}
                  onClick={() => startReview("approve", toReview)}
                >
                  {acting === "approve" ? `${approveLabel}中…` : `批量${approveLabel}（${toReview.length}）`}
                </button>
                <button
                  type="button"
                  className="h-6 rounded border border-rose-300 bg-white px-2 font-medium text-rose-600 disabled:opacity-40"
                  disabled={Boolean(acting) || toReview.length === 0}
                  title="退回勾选中的待审记录，需填写意见"
                  onClick={() => startReview("return", toReview)}
                >
                  {acting === "return" ? "退回中…" : `批量退回（${toReview.length}）`}
                </button>
              </>
            ) : null}
            <button
              type="button"
              className="text-sky-600 hover:text-sky-800 disabled:opacity-40"
              disabled={Boolean(acting) || pickedRows.length === 0}
              onClick={clearSelection}
            >
              清除
            </button>
          </div>
          <span className="text-[10px] text-zinc-400 xl:ml-auto">共 {page.total} 条</span>
        </form>
        <div className="p-5">
          <div className="overflow-hidden rounded-lg border border-zinc-200">
            <DataTable table={table} empty="暂无记录" className="min-w-215" />
            <div className="flex items-center justify-between border-t border-zinc-100 px-3 py-2.5">
              <p className="flex items-center gap-2 text-[10px] text-zinc-400">
                第 {currentPage} / {pages} 页
                <select
                  className="h-6 rounded border border-zinc-200 bg-white px-1 text-[10px] text-zinc-600"
                  aria-label="每页条数"
                  value={pageSize}
                  onChange={(event) => {
                    const size = Number(event.target.value);
                    setPageSize(size);
                    void loadList(1, query, size).catch((error: unknown) => toast(error instanceof ApiError ? error.message : "加载失败", "error"));
                  }}
                >
                  {PAGE_SIZES.map((size) => (
                    <option key={size} value={size}>
                      每页 {size} 条
                    </option>
                  ))}
                </select>
              </p>
              <div className="flex gap-1">
                <button type="button" className="h-6 rounded border border-zinc-200 px-2 text-[10px] disabled:text-zinc-300" disabled={currentPage <= 1} onClick={() => void loadList(currentPage - 1, query)}>上一页</button>
                <button type="button" className="h-6 rounded border border-zinc-200 px-2 text-[10px] disabled:text-zinc-300" disabled={currentPage >= pages} onClick={() => void loadList(currentPage + 1, query)}>下一页</button>
              </div>
            </div>
          </div>
        </div>
      </section>
      {editing ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <button type="button" aria-label="关闭" className="absolute inset-0 bg-zinc-950/40" onClick={() => setEditing(null)} />
          <div className="relative flex max-h-[88vh] w-full max-w-230 flex-col overflow-hidden rounded-xl border border-zinc-200 bg-white shadow-2xl">
            <div className="border-b border-zinc-100 px-5 py-4">
              <h3 className="text-sm font-semibold">{editing === "new" ? "新增" : editingStatus === "draft" || editingStatus === "returned" ? "编辑" : editingReviewable ? "审核" : "查看"}
                {meta.name}
                {editing !== "new" ? <span className="ml-2 text-[11px] font-normal text-zinc-400">{STATUS_LABEL[editingStatus] ?? editingStatus}</span> : null}</h3>
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
              {meta.groups.map((group) => {
                const fields = meta.fields.filter((field) => field.group === group.title && (!field.visible_when || draft[field.visible_when] === "1"));
                if (fields.length === 0) return null;
                return (
                  <section key={group.title} className="mb-5">
                    <h4 className="text-[12px] font-semibold text-zinc-800">{group.title}</h4>
                    {group.hint ? <p className="mt-0.5 text-[10px] text-zinc-400">{group.hint}</p> : null}
                    <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2">
                      {fields.map((field) => {
                        const locked =
                          !editable ||
                          (meta.filler_type === "teacher" && field.code === meta.owner_field) ||
                          (field.code === meta.department_field && meta.departments.length <= 1);
                        return (
                          <label key={field.code} className="block text-[11px] text-zinc-500">
                            {field.label}
                            {field.required ? <span className="text-rose-500"> *</span> : null}
                            {field.dict_code ? (
                              <div className="mt-1">
                                <FormCombobox
                                  options={optionsFor(meta, field)}
                                  value={draft[field.code] ?? ""}
                                  disabled={locked}
                                  onValueChange={(value) => setDraft((current) => ({ ...current, [field.code]: value }))}
                                />
                              </div>
                            ) : (
                              <input
                                className={`${fieldClass} mt-1`}
                                type={field.kind === "date" ? "date" : field.kind === "month" ? "month" : field.kind === "number" || field.kind === "decimal" ? "number" : "text"}
                                step={field.kind === "decimal" ? "0.1" : undefined}
                                maxLength={field.max_length ?? undefined}
                                disabled={locked}
                                value={draft[field.code] ?? ""}
                                onChange={(event) => setDraft((current) => ({ ...current, [field.code]: event.target.value }))}
                              />
                            )}
                          </label>
                        );
                      })}
                    </div>
                  </section>
                );
              })}
            </div>
            <div className="flex justify-end gap-2 border-t border-zinc-100 px-5 py-3">
              <button type="button" className="h-9 rounded-md border border-zinc-200 px-3 text-xs" onClick={() => setEditing(null)}>取消</button>
              {editable && (editing === "new" || editingStatus === "draft" || editingStatus === "returned") ? (
                <>
                  <button type="button" className="h-9 rounded-md border border-zinc-200 px-3 text-xs" disabled={saving} onClick={() => void persist(false)}>保存草稿</button>
                  <button type="button" className="h-9 rounded-md bg-zinc-900 px-3 text-xs text-white" disabled={saving} onClick={() => void persist(true)}>提交审核</button>
                </>
              ) : null}
              {editing !== "new" && editingReviewable ? (
                <>
                  <button type="button" className="h-9 rounded-md border border-rose-300 px-3 text-xs text-rose-600" disabled={Boolean(acting)} onClick={() => startReview("return", [editing])}>退回</button>
                  <button type="button" className="h-9 rounded-md bg-emerald-600 px-3 text-xs text-white" disabled={Boolean(acting)} onClick={() => startReview("approve", [editing])}>{approveLabel}</button>
                </>
              ) : null}
            </div>
          </div>
        </div>
      ) : null}
      {reviewing ? (
        <div className="fixed inset-0 z-60 flex items-center justify-center p-4">
          <button type="button" aria-label="关闭" className="absolute inset-0 bg-zinc-950/40" onClick={() => (acting ? undefined : setReviewing(null))} />
          <div className="relative w-full max-w-md rounded-xl border border-zinc-200 bg-white p-5 shadow-2xl">
            <h3 className="text-sm font-semibold">
              {reviewing.action === "approve" ? approveLabel : "退回"} {reviewing.ids.length} 条记录
            </h3>
            <p className="mt-1 text-[11px] leading-4 text-zinc-500">
              {reviewing.action === "return"
                ? "退回后记录回到填报人手中，可修改后重新提交。"
                : center
                  ? "通过后记录直接发布入库；尚在系部、业务部门环节的记录将跳级发布。"
                  : "通过后记录进入下一审核环节。"}
            </p>
            <label className="mt-3 block text-[11px] text-zinc-500">
              审核意见{reviewing.action === "return" ? <span className="text-rose-500"> *</span> : "（选填）"}
              <textarea
                autoFocus
                maxLength={500}
                className="mt-1 h-20 w-full rounded-md border border-zinc-200 px-3 py-2 text-[12px] outline-none focus:border-zinc-400"
                value={reviewComment}
                onChange={(event) => setReviewComment(event.target.value)}
              />
            </label>
            <div className="mt-3 flex justify-end gap-2">
              <button type="button" className="h-9 rounded-md border border-zinc-200 px-3 text-xs" disabled={Boolean(acting)} onClick={() => setReviewing(null)}>取消</button>
              <button
                type="button"
                className={`h-9 rounded-md px-3 text-xs text-white disabled:opacity-50 ${reviewing.action === "return" ? "bg-rose-600" : "bg-emerald-600"}`}
                disabled={Boolean(acting)}
                onClick={() => void confirmReview()}
              >
                {acting ? "处理中…" : `确认${reviewing.action === "approve" ? approveLabel : "退回"}`}
              </button>
            </div>
          </div>
        </div>
      ) : null}
      {importRows ? (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-zinc-900/30 p-4">
          <div className="max-h-[80vh] w-full max-w-3xl overflow-hidden rounded-lg bg-white shadow-lg">
            <div className="border-b border-zinc-100 px-5 py-4">
              <h2 className="text-sm font-semibold">导入预览</h2>
              <p className="mt-1 text-[11px] text-zinc-400">错误行不会写入。勾选有效行后保存为草稿或提交审核。</p>
            </div>
            <DataTable
              table={importTable}
              empty="没有可导入的行"
              containerClassName="max-h-[50vh] overflow-auto"
            />
            <div className="flex flex-col gap-2 border-t border-zinc-100 px-5 py-3">
              {importProgress ? (
                <div className="rounded-md border border-zinc-200 bg-zinc-50 px-3 py-2">
                  <div className="flex items-center justify-between gap-3 text-[11px] text-zinc-600">
                    <span className="flex items-center gap-1.5 font-medium">
                      <span className="size-3 animate-spin rounded-full border-2 border-zinc-300 border-t-zinc-700" aria-hidden="true" />
                      正在写入 {importProgress.done} / {importProgress.total} 行
                    </span>
                    <span className="tabular-nums text-zinc-400">
                      {Math.round((importProgress.done / Math.max(1, importProgress.total)) * 100)}%
                    </span>
                  </div>
                  <ProgressBar
                    value={importProgress.done}
                    max={importProgress.total}
                    label={`已写入 ${importProgress.done} / ${importProgress.total} 行`}
                    className="mt-1.5"
                  />
                  <p className="mt-1.5 text-[10px] text-zinc-400">每批 {IMPORT_BATCH} 行依次提交，请勿关闭页面。</p>
                </div>
              ) : null}
              {importError ? (
                <div
                  role="alert"
                  className="flex items-start justify-between gap-2 rounded-md bg-rose-50 px-3 py-2 text-[11px] leading-4 text-rose-700"
                >
                  <span>{importError}</span>
                  <button
                    type="button"
                    className="shrink-0 text-rose-400 transition hover:text-rose-600"
                    aria-label="关闭错误提示"
                    onClick={() => setImportError("")}
                  >
                    ✕
                  </button>
                </div>
              ) : null}
              <div className="flex justify-end gap-2">
                <button
                  type="button"
                  className="h-9 rounded-md border border-zinc-200 px-3 text-xs disabled:cursor-not-allowed disabled:opacity-45"
                  disabled={importing}
                  onClick={() => setImportRows(null)}
                >
                  取消
                </button>
                <button
                  type="button"
                  className="h-9 rounded-md border border-zinc-200 px-3 text-xs disabled:cursor-not-allowed disabled:opacity-45"
                  disabled={importing}
                  onClick={() => void commitImport(false)}
                >
                  {importProgress ? `写入中 ${importProgress.done}/${importProgress.total}` : "保存为草稿"}
                </button>
                <button
                  type="button"
                  className="h-9 rounded-md bg-zinc-900 px-3 text-xs text-white disabled:cursor-not-allowed disabled:opacity-45"
                  disabled={importing}
                  onClick={() => void commitImport(true)}
                >
                  提交审核
                </button>
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
