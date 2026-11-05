"use client";

import type { RowSelectionState } from "@tanstack/react-table";
import { FilePlus2, FileSpreadsheet, RefreshCw, RotateCcw, Trash2, X } from "lucide-react";
import Link from "next/link";
import { useCallback, useMemo, useState, useEffect } from "react";

import { createAppColumnHelper, DataTable, TablePagination, useAppTable } from "@/components/data-table";
import { PlanReview } from "@/components/ingest/plan-review";
import { STEPS, StepBar, type StepKey } from "@/components/ingest/step-bar";
import {
  ACTIVE,
  PLAN_SOURCE_LABEL,
  STATUS_LABEL,
  TRIAGE_BADGE,
  TRIAGE_LABEL,
  tone,
  type BatchRead,
  type Candidate,
  type GapRead,
  type IngestTask,
  type MappingItem,
  type PlanRead,
} from "@/components/ingest/types";
import { ReferenceDialog, type ReferenceResult } from "@/components/ingest/reference-dialog";
import { UploadDialog } from "@/components/ingest/upload-dialog";
import { ProgressBar, StatusPill, ghostButton, primaryButton } from "@/components/page-bits";
import { useToast } from "@/components/toast";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { ApiError, api, upload } from "@/lib/api";
import { optionLabel, type DatasetMeta, type FieldMeta } from "@/lib/records";
import { readSession, type DatasetAccess } from "@/lib/session";

const PAGE_SIZE = 20;
/** 确认写入时每批提交的候选条数：分批可以让进度条真实反映写入量，并在单批失败时保住已完成的数据。 */
const CONFIRM_BATCH = 20;
/** 批量设置字段时每批提交的条数：后端单次最多 500 条，勾选全量时要分批。 */
const BULK_BATCH = 200;

const SOURCE_LABEL: Record<string, string> = {
  file: "文件原值",
  ai: "模型提取",
  completion: "原文补全",
  dict: "字典规范化",
  lookup: "关联表补齐",
  reference: "参照表回填",
  derive: "规则计算",
  default: "默认值",
  user: "人工修改",
};

/** 粘性列需要不透明背景，并跟随整行的悬停与勾选状态变色。 */
const STICKY_CELL =
  "sticky z-[1] bg-white group-hover/row:bg-zinc-50 group-data-[state=selected]/row:bg-sky-50";
const EDGE_LEFT = "border-r border-r-zinc-200 shadow-[6px_0_8px_-6px_rgba(24,24,27,0.18)]";
const EDGE_RIGHT = "border-l border-l-zinc-200 shadow-[-6px_0_8px_-6px_rgba(24,24,27,0.18)]";

const candidateHelper = createAppColumnHelper<Candidate>();

/** 已生成草稿、重复、无权填写：这些行既不能勾选，也不能确认。 */
function locked(row: Candidate) {
  return Boolean(row.record_id) || Boolean(row.duplicate_of) || row.warnings.includes("无权填写");
}

/** 能确认的候选。校验未通过、缺业务主键的行可以勾选（用于批量修正），但不能确认。 */
function blocked(row: Candidate) {
  return row.errors.length > 0 || (row.missing_key?.length ?? 0) > 0 || locked(row);
}

export default function AiParsePage() {
  const toast = useToast();
  const [datasets, setDatasets] = useState<DatasetAccess[]>([]);
  const [datasetCode, setDatasetCode] = useState("");
  const [prompt, setPrompt] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [referenceOpen, setReferenceOpen] = useState(false);
  const [tasks, setTasks] = useState<IngestTask[]>([]);
  const [selectedId, setSelectedId] = useState("");
  /** 已加载详情的任务；切换任务后在新详情回来之前不渲染旧任务的内容。 */
  const [loadedFor, setLoadedFor] = useState("");
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [mappings, setMappings] = useState<MappingItem[]>([]);
  const [plan, setPlan] = useState<PlanRead | null>(null);
  const [batchInfo, setBatchInfo] = useState<{ id: string; batch: BatchRead; gaps: GapRead[] } | null>(null);
  const [batchTick, setBatchTick] = useState(0);
  const [rememberPlan, setRememberPlan] = useState(true);
  const [triageFilter, setTriageFilter] = useState<Candidate["triage"] | "">("");
  const [requiredOnly, setRequiredOnly] = useState(false);
  const [bulkField, setBulkField] = useState("");
  const [bulkValue, setBulkValue] = useState("");
  const [appendToBatch, setAppendToBatch] = useState(false);
  const [freshPlan, setFreshPlan] = useState(false);
  const [replanning, setReplanning] = useState(false);
  const [meta, setMeta] = useState<DatasetMeta | null>(null);
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({});
  const [submit, setSubmit] = useState(false);
  const [editing, setEditing] = useState<Candidate | null>(null);
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [completing, setCompleting] = useState("");
  /** 用户手动切换查看的步骤；任务或其所处步骤变化后自动失效，回到当前步骤。 */
  const [viewChoice, setViewChoice] = useState<{ task: string; from: StepKey; step: StepKey } | null>(null);
  /** 批量写入进度：done 为已写入条数，total 为本次勾选的条数；null 表示不在写入中。 */
  const [writing, setWriting] = useState<{ done: number; total: number } | null>(null);
  /** 批量设置字段的分批进度；null 表示不在批量设置中。 */
  const [bulkProgress, setBulkProgress] = useState<{ done: number; total: number } | null>(null);
  /** 写入失败的常驻提示，避免 toast 消失后用户看不到结果。 */
  const [writeError, setWriteError] = useState("");
  const [reassessing, setReassessing] = useState(false);
  /** 删除任务或批次；purgeDrafts 决定是否一并清除已生成的草稿。 */
  const [deleting, setDeleting] = useState<{ kind: "task" | "batch"; id: string; name: string } | null>(null);
  const [purgeDrafts, setPurgeDrafts] = useState(false);
  const [removing, setRemoving] = useState(false);

  const selected = tasks.find((item) => item.id === selectedId) ?? null;
  const selectedStatus = selected?.status ?? "";
  const selectedBatchId = selected?.batch_id ?? "";

  async function loadTasks() {
    const rows = await api<IngestTask[]>("/api/ingestion/tasks");
    setTasks(rows);
    return rows;
  }

  async function loadDetail(task: IngestTask) {
    const [rows, planBody] = await Promise.all([
      api<Candidate[]>(`/api/ingestion/tasks/${task.id}/candidates`),
      api<PlanRead>(`/api/ingestion/tasks/${task.id}/plan`).catch(() => null),
    ]);
    setCandidates(rows);
    setPlan(planBody);
    if (task.has_mapping && !task.mapping_applied && task.candidate_count === 0) {
      const body = await api<{ mappings?: MappingItem[] }>(`/api/ingestion/tasks/${task.id}/mapping`);
      setMappings(body.mappings ?? []);
    } else {
      setMappings([]);
    }
    setLoadedFor(task.id);
  }

  useEffect(() => {
    let cancelled = false;
    queueMicrotask(() => {
      const session = readSession();
      const fillable = (session?.datasets ?? []).filter((item) => item.can_fill);
      if (cancelled) return;
      setDatasets(fillable);
      setDatasetCode((current) => current || fillable[0]?.code || "");
      void loadTasks().catch((reason: unknown) => {
        if (!cancelled) toast(reason instanceof ApiError ? reason.message : "任务加载失败", "error");
      });
    });
    return () => {
      cancelled = true;
    };
  }, [toast]);

  useEffect(() => {
    if (!selectedId || !ACTIVE.has(selectedStatus)) return;
    let elapsed = 0;
    let timer = 0;
    let stopped = false;
    const tick = () => {
      if (stopped) return;
      void loadTasks()
        .then((rows) => {
          const next = rows.find((item) => item.id === selectedId);
          if (next) return loadDetail(next);
          return undefined;
        })
        .catch((reason: unknown) => {
          toast(reason instanceof ApiError ? reason.message : "进度刷新失败", "error");
        });
      const delay = elapsed < 30_000 ? 2000 : 5000;
      elapsed += delay;
      timer = window.setTimeout(tick, delay);
    };
    timer = window.setTimeout(tick, 2000);
    return () => {
      stopped = true;
      window.clearTimeout(timer);
    };
  }, [selectedId, selectedStatus, toast]);

  useEffect(() => {
    if (!selectedBatchId) return;
    let cancelled = false;
    queueMicrotask(() => {
      void api<{ batch: BatchRead; gaps: GapRead[] }>(`/api/ingestion/batches/${selectedBatchId}`)
        .then((body) => {
          if (cancelled) return;
          setBatchInfo({ id: selectedBatchId, batch: body.batch, gaps: body.gaps ?? [] });
        })
        .catch(() => undefined);
    });
    return () => {
      cancelled = true;
    };
  }, [selectedBatchId, batchTick]);

  useEffect(() => {
    if (!selectedId) return;
    let cancelled = false;
    queueMicrotask(() => {
      void api<IngestTask>(`/api/ingestion/tasks/${selectedId}`)
        .then((task) => {
          if (cancelled) return undefined;
          void api<DatasetMeta>(`/api/datasets/${task.dataset_code}/meta`)
            .then((next) => {
              if (!cancelled) setMeta(next);
            })
            .catch(() => {
              if (!cancelled) setMeta(null);
            });
          return loadDetail(task);
        })
        .catch((reason: unknown) => {
          if (!cancelled) toast(reason instanceof ApiError ? reason.message : "候选加载失败", "error");
        });
    });
    return () => {
      cancelled = true;
    };
  }, [selectedId, selectedStatus, toast]);

  function selectTask(id: string) {
    if (id !== selectedId) {
      setCandidates([]);
      setPlan(null);
      setMappings([]);
      setLoadedFor("");
    }
    setSelectedId(id);
    setRowSelection({});
    setTriageFilter("");
    candidateTable.setPageIndex(0);
    setEditing(null);
    setWriteError("");
  }

  async function createTask() {
    if (!datasetCode || files.length === 0) {
      toast("请选择数据表和文件", "info");
      return;
    }
    setBusy(true);
    try {
      let first: IngestTask | null = null;
      if (files.length === 1 && appendToBatch && selected?.batch_id) {
        const body = new FormData();
        body.set("dataset_code", datasetCode);
        body.set("prompt", prompt);
        body.set("fresh_plan", String(freshPlan));
        body.set("file", files[0]);
        first = await upload<IngestTask>(`/api/ingestion/batches/${selected.batch_id}/files`, body);
      } else if (files.length === 1) {
        const body = new FormData();
        body.set("dataset_code", datasetCode);
        body.set("prompt", prompt);
        body.set("fresh_plan", String(freshPlan));
        body.set("file", files[0]);
        first = await upload<IngestTask>("/api/ingestion/tasks", body);
      } else {
        const batch = await api<{ id: string }>("/api/ingestion/batches", {
          method: "POST",
          body: JSON.stringify({ dataset_codes: [datasetCode] }),
        });
        for (const item of files) {
          const body = new FormData();
          body.set("dataset_code", datasetCode);
          body.set("prompt", prompt);
          body.set("fresh_plan", String(freshPlan));
          body.set("file", item);
          const task = await upload<IngestTask>(`/api/ingestion/batches/${batch.id}/files`, body);
          first ??= task;
        }
      }
      toast(files.length > 1 ? `已创建批次，共 ${files.length} 个文件排队解析` : "任务已提交，正在排队解析");
      setUploadOpen(false);
      setFiles([]);
      setFreshPlan(false);
      if (first) selectTask(first.id);
      await loadTasks();
    } catch (reason: unknown) {
      toast(reason instanceof ApiError ? reason.message : "上传失败", "error");
    } finally {
      setBusy(false);
    }
  }

  async function applyMapping() {
    if (!selected) return;
    setBusy(true);
    try {
      await api<IngestTask>(`/api/ingestion/tasks/${selected.id}/mapping`, {
        method: "PUT",
        body: JSON.stringify({ mappings }),
      });
      toast("列对应已保存，任务重新排队");
      await loadTasks();
    } catch (reason: unknown) {
      toast(reason instanceof ApiError ? reason.message : "保存列对应失败", "error");
    } finally {
      setBusy(false);
    }
  }

  async function applyPlan() {
    if (!selected || !plan?.plan) return;
    setBusy(true);
    try {
      await api<IngestTask>(`/api/ingestion/tasks/${selected.id}/plan`, {
        method: "PUT",
        body: JSON.stringify({
          plan: { ...plan.plan, source: "user", confidence: 1 },
          remember: rememberPlan,
        }),
      });
      toast(rememberPlan ? "结构已保存，下次相同表头将直接复用" : "结构已保存，正在提取候选");
      await loadTasks();
    } catch (reason: unknown) {
      toast(reason instanceof ApiError ? reason.message : "保存结构失败", "error");
    } finally {
      setBusy(false);
    }
  }

  function updatePlanField(sheetIndex: number, columnIndex: number | null, header: string, field: string) {
    setPlan((current) => {
      if (!current?.plan) return current;
      const sheets = current.plan.sheets.map((sheet, index) => {
        if (index !== sheetIndex) return sheet;
        if (columnIndex == null) {
          return field ? { ...sheet, columns: [...sheet.columns, { header, field, transform: "direct" }] } : sheet;
        }
        return {
          ...sheet,
          columns: sheet.columns.map((column, inner) =>
            inner === columnIndex
              ? { ...column, field: field || null, transform: column.transform === "narrative" ? "direct" : column.transform }
              : column,
          ),
        };
      });
      return { ...current, plan: { ...current.plan, sheets } };
    });
  }

  async function referenceApplied(result: ReferenceResult) {
    if (selected) await loadDetail(selected).catch(() => undefined);
    setRowSelection({});
    toast(
      `已按参照表回填 ${result.changed} 条候选并重新校验${result.ready > 0 ? `，当前可确认 ${result.ready} 条` : ""}`,
    );
  }

  async function bulkSet() {
    const ids = Object.keys(rowSelection);
    if (!bulkField || ids.length === 0) {
      toast("请选择字段并勾选候选", "info");
      return;
    }
    setBusy(true);
    setBulkProgress({ done: 0, total: ids.length });
    /** 已成功返回的行；接口单次最多 500 条，勾选全量时按批提交。 */
    const rows: Candidate[] = [];
    let failure = "";
    let failedFrom = ids.length;
    try {
      for (let start = 0; start < ids.length; start += BULK_BATCH) {
        const chunk = ids.slice(start, start + BULK_BATCH);
        try {
          const result = await api<Candidate[]>("/api/ingestion/candidates/bulk", {
            method: "POST",
            body: JSON.stringify({ candidate_ids: chunk, values: { [bulkField]: bulkValue } }),
          });
          rows.push(...result);
          setBulkProgress({ done: rows.length, total: ids.length });
        } catch (reason: unknown) {
          failure = reason instanceof ApiError ? reason.message : "批量设置失败";
          failedFrom = start;
          break;
        }
      }
    } finally {
      setBusy(false);
      setBulkProgress(null);
    }

    if (rows.length > 0) {
      const updated = new Map(rows.map((row) => [row.id, row]));
      setCandidates((current) => current.map((row) => updated.get(row.id) ?? row));
      // 保留仍然可勾选的行，修正完就能直接确认；已生成草稿/重复的行自动去掉勾选
      setRowSelection(
        Object.fromEntries([
          ...rows.filter((row) => !locked(row)).map((row) => [row.id, true] as const),
          // 失败批次的行保持勾选，便于重试
          ...ids.slice(failedFrom).map((id) => [id, true] as const),
        ]),
      );
    }

    if (failure) {
      toast(
        rows.length > 0
          ? `已更新 ${rows.length} 条，剩余 ${ids.length - rows.length} 条失败：${failure}`
          : `批量设置失败：${failure}`,
        "error",
      );
      return;
    }

    const ready = rows.filter((row) => !blocked(row)).length;
    toast(
      ready === rows.length
        ? `已批量更新 ${rows.length} 条，校验已通过，可直接确认`
        : `已批量更新 ${rows.length} 条，系统已重新校验${ready > 0 ? `，其中 ${ready} 条已可确认` : ""}`,
    );
  }

  const completeCandidate = useCallback(
    async (row: Candidate) => {
      setCompleting(row.id);
      try {
        const result = await api<{ candidate: Candidate; filled: string[]; message: string }>(
          `/api/ingestion/candidates/${row.id}/complete`,
          { method: "POST" },
        );
        setCandidates((current) => current.map((item) => (item.id === row.id ? result.candidate : item)));
        toast(
          result.filled.length > 0 ? `已补全 ${result.filled.length} 个字段` : result.message,
          result.filled.length > 0 ? "success" : "info",
        );
      } catch (reason: unknown) {
        toast(reason instanceof ApiError ? reason.message : "补全失败", "error");
      } finally {
        setCompleting("");
      }
    },
    [toast],
  );

  const openEditor = useCallback(
    (row: Candidate) => {
      setEditing(row);
      const next: Record<string, string> = {};
      for (const field of meta?.fields ?? []) {
        const value = row.values[field.code];
        next[field.code] = value == null ? "" : String(value);
      }
      setDraft(next);
    },
    [meta],
  );

  async function saveCandidate() {
    if (!editing || !meta) return;
    const values: Record<string, string | null> = {};
    for (const field of meta.fields) {
      const text = (draft[field.code] ?? "").trim();
      values[field.code] = text || null;
    }
    setBusy(true);
    try {
      await api<Candidate>(`/api/ingestion/candidates/${editing.id}`, {
        method: "PATCH",
        body: JSON.stringify({ values }),
      });
      setEditing(null);
      if (selected) await loadDetail(selected);
      toast("候选已重新校验");
    } catch (reason: unknown) {
      toast(reason instanceof ApiError ? reason.message : "保存失败", "error");
    } finally {
      setBusy(false);
    }
  }

  async function reassess() {
    if (!selected || reassessing) return;
    setReassessing(true);
    try {
      const result = await api<{ checked: number; ready: number; updated: number }>(
        `/api/ingestion/tasks/${selected.id}/reassess`,
        { method: "POST" },
      );
      await loadDetail(selected);
      toast(
        result.checked === 0
          ? "没有待校验的候选"
          : `已重新校验 ${result.checked} 条，${result.updated} 条有更新，当前可确认 ${result.ready} 条`,
      );
    } catch (reason) {
      toast(reason instanceof ApiError ? reason.message : "重新校验失败", "error");
    } finally {
      setReassessing(false);
    }
  }

  async function confirmSelected(idsArg?: string[]) {
    if (!selected || writing) return;
    const task = selected;
    // 勾选里可能包含校验未通过的行（勾选是为了批量修正）；确认时只提交能确认的
    const requested = [...new Set(idsArg ?? picked)];
    const ids = requested.filter((id) => confirmable.has(id));
    const skipped = requested.length - ids.length;
    if (ids.length === 0) {
      const missing = requested.filter((id) => {
        const row = candidates.find((item) => item.id === id);
        return row != null && (row.missing_key?.length ?? 0) > 0;
      }).length;
      toast(
        missing > 0
          ? `所选 ${missing} 条缺少业务主键，补齐后才能写入`
          : skipped > 0
            ? `所选 ${skipped} 条存在校验错误或重复，修正后才能确认`
            : "没有可确认的候选",
        "info",
      );
      return;
    }
    const total = ids.length;
    let done = 0;
    let created = 0;
    let submitted = 0;
    const skippedNote = skipped > 0 ? `，跳过 ${skipped} 条需先修正的记录` : "";

    setWriteError("");
    setBusy(true);
    setWriting({ done: 0, total });

    try {
      for (let start = 0; start < total; start += CONFIRM_BATCH) {
        const batch = ids.slice(start, start + CONFIRM_BATCH);
        const result = await api<{ created: number; submitted: number }>(
          `/api/ingestion/tasks/${task.id}/confirm`,
          { method: "POST", body: JSON.stringify({ candidate_ids: batch, submit }) },
        );
        created += result.created;
        submitted += result.submitted;
        done += batch.length;
        setWriting({ done, total });
        // 每批写完后刷新候选，让已写入的行立即显示「已生成草稿」。
        await loadDetail(task).catch(() => undefined);
      }
      toast(
        submit
          ? `已提交 ${submitted} 条${created > submitted ? `，其余 ${created - submitted} 条已生成草稿` : ""}${skippedNote}`
          : `已生成 ${created} 条草稿${skippedNote}`,
      );
      setRowSelection({});
      candidateTable.setPageIndex(0);
    } catch (reason: unknown) {
      const message = reason instanceof ApiError ? reason.message : "写入失败";
      setWriteError(
        done > 0
          ? `已写入 ${done}/${total} 条，剩余 ${total - done} 条未写入：${message}。已保留未写入记录的勾选，可再次确认重试。`
          : `写入失败：${message}`,
      );
      toast(`确认未完成：${message}`, "error");
      // 只保留未写入的勾选，已写入的行刷新后会变为不可勾选；仍需修正的记录也保留勾选
      const keep = [...ids.slice(done), ...requested.filter((id) => !confirmable.has(id))];
      setRowSelection(Object.fromEntries(keep.map((id) => [id, true])));
    } finally {
      setWriting(null);
      await Promise.allSettled([loadTasks(), loadDetail(task)]);
      setBusy(false);
    }
  }

  async function retry(task: IngestTask) {
    try {
      await api(`/api/ingestion/tasks/${task.id}/retry`, { method: "POST" });
      await loadTasks();
      toast("已重新排队");
    } catch (reason: unknown) {
      toast(reason instanceof ApiError ? reason.message : "重试失败", "error");
    }
  }

  async function replan(task: IngestTask) {
    setReplanning(false);
    setBusy(true);
    try {
      await api(`/api/ingestion/tasks/${task.id}/replan`, { method: "POST" });
      setCandidates([]);
      setPlan(null);
      setMappings([]);
      setRowSelection({});
      setViewChoice(null);
      await loadTasks();
      toast("已重新排队，模型将重新识别结构");
    } catch (reason: unknown) {
      toast(reason instanceof ApiError ? reason.message : "重新识别失败", "error");
    } finally {
      setBusy(false);
    }
  }

  function updatePlanDedupe(sheetIndex: number, fields: string[]) {
    setPlan((current) => {
      if (!current?.plan) return current;
      const sheets = current.plan.sheets.map((sheet, index) =>
        index === sheetIndex ? { ...sheet, dedupe_by: fields } : sheet,
      );
      return { ...current, plan: { ...current.plan, sheets } };
    });
  }

  function askDelete(kind: "task" | "batch", id: string, name: string) {
    setPurgeDrafts(false);
    setDeleting({ kind, id, name });
  }

  async function removeTarget() {
    if (!deleting || removing) return;
    setRemoving(true);
    try {
      const path =
        deleting.kind === "task"
          ? `/api/ingestion/tasks/${deleting.id}`
          : `/api/ingestion/batches/${deleting.id}`;
      const result = await api<{ deleted_tasks: number; cleared_records: number }>(
        `${path}?purge_records=${purgeDrafts}`,
        { method: "DELETE" },
      );
      toast(
        result.cleared_records > 0
          ? `已删除 ${result.deleted_tasks} 个任务和 ${result.cleared_records} 条草稿`
          : `已删除 ${result.deleted_tasks} 个任务`,
      );
      const touchedSelection =
        deleting.kind === "batch" ||
        deleting.id === selectedId ||
        tasks.some((task) => task.id === selectedId && task.batch_id === deleting.id);
      if (touchedSelection) {
        setSelectedId("");
        setCandidates([]);
        setPlan(null);
        setRowSelection({});
        setEditing(null);
        setWriteError("");
      }
      setDeleting(null);
      await loadTasks();
      setBatchTick((current) => current + 1);
    } catch (reason: unknown) {
      toast(reason instanceof ApiError ? reason.message : "删除失败", "error");
    } finally {
      setRemoving(false);
    }
  }

  const names = new Map(datasets.map((item) => [item.code, item.name]));
  const needsMapping = Boolean(
    selected &&
      selected.has_mapping &&
      !selected.mapping_applied &&
      selected.candidate_count === 0 &&
      !plan?.plan,
  );
  const written = candidates.filter((row) => row.record_id).length;
  const allWritten = candidates.length > 0 && written === candidates.length;

  const currentStep: StepKey = (() => {
    if (!selected) return "parse";
    if (ACTIVE.has(selected.status) || selected.status === "failed" || selected.status === "cancelled") return "parse";
    if (selected.status === "awaiting_plan" || needsMapping) return "plan";
    if (selected.status === "completed" || allWritten) return "done";
    return "review";
  })();
  const skipped: StepKey[] =
    selected && loadedFor === selectedId && !plan?.plan && !needsMapping && currentStep !== "parse" && currentStep !== "plan" ? ["plan"] : [];
  const viewing: StepKey =
    viewChoice && viewChoice.task === selectedId && viewChoice.from === currentStep ? viewChoice.step : currentStep;

  const ready = Boolean(selected) && loadedFor === selectedId;
  const canReplan =
    ready &&
    written === 0 &&
    ["awaiting_plan", "pending_confirmation", "failed"].includes(selected?.status ?? "") &&
    Boolean(selected?.file_name && !/\.(docx|pdf)$/i.test(selected.file_name));

  const triageCounts = {
    auto: candidates.filter((row) => row.triage === "auto").length,
    review: candidates.filter((row) => row.triage === "review").length,
    missing: candidates.filter((row) => row.triage === "missing").length,
    duplicate: candidates.filter((row) => row.triage === "duplicate").length,
  };
  const visibleCandidates = triageFilter
    ? candidates.filter((row) => row.triage === triageFilter)
    : candidates;
  const hasPending = visibleCandidates.some((row) => !row.record_id);
  const pickable = visibleCandidates.filter((row) => !row.record_id && !blocked(row)).map((row) => row.id);
  const autoConfirmable = candidates
    .filter((row) => row.triage === "auto" && !row.record_id && !blocked(row))
    .map((row) => row.id);
  // 勾选可以跨分诊筛选保留，确认范围按整个任务算，而不是只看当前筛选出来的行
  const confirmable = new Set(
    candidates.filter((row) => !row.record_id && !blocked(row)).map((row) => row.id),
  );
  const picked = Object.keys(rowSelection);
  const pickedConfirmable = picked.filter((id) => confirmable.has(id)).length;
  // 没有任何可确认候选时，明确说明卡在哪里，避免用户反复点击「确认所选」却不知道原因。
  const blockedReason = (() => {
    if (pickable.length > 0 || visibleCandidates.length === 0) return "";
    const rest = visibleCandidates.filter((row) => !row.record_id);
    if (rest.length === 0) return "候选已全部生成草稿，无需再次确认";
    const duplicate = rest.filter((row) => row.duplicate_of).length;
    const invalid = rest.filter((row) => row.errors.length > 0).length;
    const denied = rest.filter((row) => row.warnings.includes("无权填写")).length;
    const noKey = rest.filter((row) => (row.missing_key?.length ?? 0) > 0).length;
    const reasons = [
      duplicate ? `${duplicate} 条重复` : "",
      invalid ? `${invalid} 条校验未通过` : "",
      noKey ? `${noKey} 条缺业务主键` : "",
      denied ? `${denied} 条无填写权限` : "",
    ].filter(Boolean);
    return `剩余 ${rest.length} 条不可确认${reasons.length ? `（${reasons.join("、")}）` : ""}，可勾选后批量修正`;
  })();

  const shownFields = useMemo(
    () => (meta?.fields ?? []).filter((field) => !requiredOnly || field.required),
    [meta, requiredOnly],
  );

  const candidateColumns = useMemo(() => {
    const fieldColumns = shownFields.map((field) =>
      candidateHelper.display({
        id: `f_${field.code}`,
        header: () => (
          <span title={field.code}>
            {field.label}
            {field.required ? <span className="ml-0.5 text-rose-400">*</span> : null}
          </span>
        ),
        cell: ({ row }) => <FieldCell row={row.original} field={field} meta={meta} />,
        meta: { headClassName: "min-w-[112px] max-w-[220px]", cellClassName: "max-w-[220px] px-3 py-2" },
      }),
    );

    return candidateHelper.columns([
      candidateHelper.display({
        id: "select",
        header: ({ table }) => {
          const rows = table.getPrePaginatedRowModel().rows;
          const allSelected = table.getIsAllRowsSelected();
          return (
            <input
              type="checkbox"
              aria-label="勾选全部候选"
              title="勾选全部候选（不含已生成草稿、重复或无填写权限的记录）"
              className="size-3.5 cursor-pointer accent-zinc-900 disabled:cursor-not-allowed"
              disabled={busy || !rows.some((row) => row.getCanSelect())}
              checked={allSelected}
              ref={(element) => {
                if (element) element.indeterminate = !allSelected && table.getIsSomeRowsSelected();
              }}
              onChange={table.getToggleAllRowsSelectedHandler()}
            />
          );
        },
        cell: ({ row }) => (
          <input
            type="checkbox"
            aria-label={`勾选第 ${row.original.seq} 条`}
            className="size-3.5 cursor-pointer accent-zinc-900 disabled:cursor-not-allowed disabled:opacity-40"
            disabled={busy || !row.getCanSelect()}
            checked={row.getIsSelected()}
            onChange={row.getToggleSelectedHandler()}
          />
        ),
        meta: {
          headClassName: "sticky left-0 z-20 w-10 min-w-10 bg-zinc-50 px-3",
          cellClassName: `${STICKY_CELL} left-0 w-10 min-w-10 px-3 py-2`,
        },
      }),
      candidateHelper.display({
        id: "seq",
        header: "序号",
        cell: ({ row }) => row.original.seq,
        meta: {
          headClassName: `sticky left-10 z-20 w-12 min-w-12 bg-zinc-50 px-1 text-center ${EDGE_LEFT}`,
          cellClassName: `${STICKY_CELL} left-10 w-12 min-w-12 px-1 py-2 text-center tabular-nums text-zinc-400 ${EDGE_LEFT}`,
        },
      }),
      candidateHelper.display({
        id: "triage",
        header: "分诊",
        cell: ({ row }) => (
          <div className="space-y-1">
            <span className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${TRIAGE_BADGE[row.original.triage]}`}>
              {TRIAGE_LABEL[row.original.triage]}
            </span>
            <div className="flex items-center gap-1.5 text-[10px] tabular-nums text-zinc-400">
              <span className="h-1 w-10 overflow-hidden rounded-full bg-zinc-100">
                <span
                  className={`block h-full rounded-full ${row.original.completeness >= 80 ? "bg-emerald-400" : "bg-amber-400"}`}
                  style={{ width: `${Math.min(100, row.original.completeness)}%` }}
                />
              </span>
              {row.original.completeness}%
            </div>
          </div>
        ),
        meta: { headClassName: "min-w-[96px]", cellClassName: "py-2" },
      }),
      candidateHelper.display({
        id: "issues",
        header: "问题",
        cell: ({ row }) => {
          if (row.original.record_id) return <span className="text-[11px] text-emerald-600">已生成草稿</span>;
          const missingKey = (row.original.missing_key ?? []).map(
            (code) => meta?.fields.find((field) => field.code === code)?.label ?? code,
          );
          const items = [
            ...row.original.errors.map((item) => ({ tone: "text-rose-600" as const, text: item })),
            ...(missingKey.length > 0
              ? [{ tone: "text-amber-600" as const, text: `缺业务主键：${missingKey.join("、")}` }]
              : []),
            ...row.original.warnings.map((item) => ({ tone: "text-amber-600" as const, text: item })),
          ];
          if (items.length === 0) return <span className="text-[11px] text-emerald-600">通过</span>;
          return (
            <ul className="space-y-0.5 text-[11px] leading-4" title={items.map((item) => item.text).join("\n")}>
              {items.slice(0, 2).map((item, index) => (
                <li key={`${index}-${item.text}`} className={`line-clamp-2 ${item.tone}`}>
                  {item.text}
                </li>
              ))}
              {items.length > 2 ? <li className="text-zinc-400">等 {items.length} 项</li> : null}
            </ul>
          );
        },
        meta: { headClassName: "min-w-[200px] w-[200px]", cellClassName: "w-[200px] py-2 whitespace-normal" },
      }),
      ...fieldColumns,
      candidateHelper.display({
        id: "actions",
        header: "操作",
        cell: ({ row }) =>
          row.original.record_id ? null : (
            <div className="flex items-center gap-1">
              <button
                type="button"
                className="rounded-md border border-zinc-200 bg-white px-2 py-0.5 text-[11px] text-zinc-600 transition hover:border-zinc-300"
                onClick={() => openEditor(row.original)}
              >
                修正
              </button>
              {row.original.triage === "missing" && row.original.source_text ? (
                <button
                  type="button"
                  className="rounded-md border border-sky-200 bg-white px-2 py-0.5 text-[11px] text-sky-700 transition hover:bg-sky-50 disabled:opacity-50"
                  disabled={Boolean(completing)}
                  onClick={() => void completeCandidate(row.original)}
                >
                  {completing === row.original.id ? "补全中" : "原文补全"}
                </button>
              ) : null}
            </div>
          ),
        meta: {
          headClassName: `sticky right-0 z-20 min-w-[132px] bg-zinc-50 ${EDGE_RIGHT}`,
          cellClassName: `${STICKY_CELL} right-0 min-w-[132px] py-2 ${EDGE_RIGHT}`,
        },
      }),
    ].filter((column) => hasPending || column.id !== "actions"));
  }, [shownFields, meta, busy, completing, completeCandidate, openEditor, hasPending]);

  const candidateTable = useAppTable({
    data: visibleCandidates,
    columns: candidateColumns,
    getRowId: (row) => row.id,
    enableRowSelection: (row) => !locked(row.original),
    autoResetPageIndex: false,
    state: { rowSelection },
    onRowSelectionChange: setRowSelection,
    initialState: { pagination: { pageIndex: 0, pageSize: PAGE_SIZE } },
  });

  useEffect(() => {
    const { pageIndex } = candidateTable.state.pagination;
    const pageCount = Math.max(1, candidateTable.getPageCount());
    if (pageIndex > pageCount - 1) candidateTable.setPageIndex(pageCount - 1);
  }, [candidateTable, visibleCandidates.length]);

  const stepIndex = STEPS.findIndex((step) => step.key === viewing);

  return (
    <div className="flex h-full min-h-0 flex-col gap-3 p-4 xl:p-6">
      <div className="flex shrink-0 flex-wrap items-baseline gap-x-3 gap-y-1">
        <h1 className="text-[18px] font-semibold tracking-tight text-zinc-900">文件解析入库</h1>
        <p className="text-[11px] text-zinc-500">上传表格、Word 或可复制文字的 PDF，核对后生成草稿，再进入审核流程。</p>
      </div>

      <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto lg:grid lg:grid-cols-[220px_minmax(0,1fr)] lg:overflow-hidden xl:grid-cols-[260px_minmax(0,1fr)]">
        <section className="flex max-h-72 shrink-0 flex-col overflow-hidden rounded-lg border border-zinc-200 bg-white shadow-sm lg:max-h-none lg:min-h-0">
          <div className="flex shrink-0 items-center justify-between gap-2 border-b border-zinc-100 px-3 py-3">
            <div className="pl-1">
              <h2 className="text-sm font-semibold text-zinc-900">我的任务</h2>
              <p className="mt-0.5 text-[10px] text-zinc-400">最近 50 条</p>
            </div>
            <button type="button" className={`${primaryButton} h-8 px-2.5`} onClick={() => setUploadOpen(true)}>
              <FilePlus2 className="size-3.5" aria-hidden="true" />
              新建解析
            </button>
          </div>
          <ul className="min-h-0 flex-1 divide-y divide-zinc-100 overflow-y-auto [scrollbar-width:thin]">
            {tasks.length === 0 ? (
              <li className="px-4 py-6 text-[12px] text-zinc-400">还没有解析任务，点击「新建解析」上传文件。</li>
            ) : null}
            {tasks.map((task) => {
              const active = task.id === selectedId;
              return (
                <li key={task.id} className="group relative">
                  <button
                    type="button"
                    aria-current={active ? "true" : undefined}
                    className={`w-full border-l-2 px-3.5 py-2.5 pr-9 text-left transition ${
                      active ? "border-zinc-900 bg-zinc-50" : "border-transparent hover:bg-zinc-50/70"
                    }`}
                    onClick={() => selectTask(task.id)}
                  >
                    <span className="flex items-center justify-between gap-2">
                      <span className="truncate text-[12px] font-medium text-zinc-900" title={task.file_name ?? ""}>
                        {task.file_name || task.dataset_code}
                      </span>
                      <StatusPill tone={tone(task.status)}>{STATUS_LABEL[task.status] || task.status}</StatusPill>
                    </span>
                    <span className="mt-1 block truncate text-[11px] text-zinc-500">
                      {names.get(task.dataset_code) || task.dataset_code}
                      {task.candidate_count > 0 ? `，${task.candidate_count} 条候选` : ""}
                      {task.batch_id ? "，批内文件" : ""}
                    </span>
                    {ACTIVE.has(task.status) ? (
                      <ProgressBar value={task.progress} max={100} className="mt-1.5 h-1" label={`进度 ${task.progress}%`} />
                    ) : null}
                  </button>
                  <button
                    type="button"
                    className="absolute top-2.5 right-2 flex size-6 items-center justify-center rounded-md text-zinc-300 opacity-0 transition group-hover:opacity-100 hover:bg-rose-50 hover:text-rose-500 focus-visible:opacity-100"
                    title="删除这个任务及其候选数据"
                    aria-label={`删除任务 ${task.file_name || task.dataset_code}`}
                    onClick={() => askDelete("task", task.id, task.file_name || task.dataset_code)}
                  >
                    <Trash2 className="size-3.5" />
                  </button>
                </li>
              );
            })}
          </ul>
        </section>

        <section className="flex min-h-[560px] min-w-0 flex-col overflow-hidden rounded-lg border border-zinc-200 bg-white shadow-sm lg:min-h-0">
          {!selected ? (
            <div className="flex flex-1 flex-col items-center justify-center gap-3 p-8 text-center">
              <p className="text-[13px] text-zinc-700">从左侧选择一个任务，或上传新文件开始解析。</p>
              <p className="max-w-sm text-[12px] leading-5 text-zinc-400">
                每个任务依次经过解析文件、核对结构、核对候选三步，确认后才会生成草稿。
              </p>
              <button type="button" className={primaryButton} onClick={() => setUploadOpen(true)}>
                <FilePlus2 className="size-3.5" aria-hidden="true" />
                新建解析
              </button>
            </div>
          ) : (
            <>
              <header className="flex shrink-0 flex-wrap items-center gap-x-4 gap-y-2.5 border-b border-zinc-100 px-5 py-3">
                <div className="order-1 min-w-0 flex-1">
                  <h2 className="truncate text-[14px] font-semibold text-zinc-900" title={selected.file_name ?? ""}>
                    {selected.file_name || "未命名文件"}
                  </h2>
                  <p className="mt-0.5 truncate text-[11px] text-zinc-500">
                    导入到「{names.get(selected.dataset_code) || selected.dataset_code}」
                    {selected.plan_source ? `，结构来自${PLAN_SOURCE_LABEL[selected.plan_source] ?? selected.plan_source}` : ""}
                    {selected.llm_calls > 0
                      ? `，调用模型 ${selected.llm_calls} 次、${(selected.tokens_in + selected.tokens_out).toLocaleString()} tokens`
                      : ""}
                  </p>
                  {selected.user_prompt ? (
                    <p className="mt-0.5 truncate text-[11px] text-zinc-400" title={selected.user_prompt}>
                      补充说明：{selected.user_prompt}
                    </p>
                  ) : null}
                </div>
                <div className="order-3 basis-full 2xl:order-2 2xl:basis-auto">
                  <StepBar
                    current={currentStep}
                    viewing={viewing}
                    skipped={skipped}
                    onSelect={(step) => setViewChoice({ task: selectedId, from: currentStep, step })}
                  />
                </div>
                <div className="order-2 flex shrink-0 items-center gap-1 2xl:order-3">
                  {canReplan ? (
                    <button
                      type="button"
                      className="flex h-8 items-center gap-1.5 rounded-md border border-zinc-200 px-2.5 text-[12px] text-zinc-600 transition hover:border-zinc-300 hover:text-zinc-900 disabled:opacity-45"
                      title="丢弃当前结构和未确认的候选，不用记住的结构，交给模型重新识别"
                      disabled={busy}
                      onClick={() => setReplanning(true)}
                    >
                      <RefreshCw className="size-3.5" aria-hidden="true" />
                      重新识别结构
                    </button>
                  ) : null}
                  <button
                    type="button"
                    className="flex size-8 items-center justify-center rounded-md text-zinc-400 transition hover:bg-rose-50 hover:text-rose-600"
                    title="删除这个任务"
                    aria-label="删除这个任务"
                    onClick={() => askDelete("task", selected.id, selected.file_name || selected.dataset_code)}
                  >
                    <Trash2 className="size-4" />
                  </button>
                </div>
              </header>

              {viewing === "parse" ? (
                <ParseStep task={selected} onRetry={() => void retry(selected)} />
              ) : null}

              {viewing !== "parse" && !ready ? (
                <div className="flex flex-1 items-center justify-center text-[12px] text-zinc-400">正在加载任务详情…</div>
              ) : null}

              {viewing === "plan" && plan?.plan ? (
                <PlanReview
                  key={selected.id}
                  plan={plan}
                  meta={meta}
                  editable={selected.status === "awaiting_plan"}
                  busy={busy}
                  remember={rememberPlan}
                  onRememberChange={setRememberPlan}
                  onFieldChange={updatePlanField}
                  onDedupeChange={updatePlanDedupe}
                  onApply={() => void applyPlan()}
                />
              ) : null}

              {ready && viewing === "plan" && !plan?.plan && needsMapping ? (
                <div className="flex min-h-0 flex-1 flex-col">
                  <p className="shrink-0 border-b border-zinc-100 px-5 py-2.5 text-[12px] text-zinc-600">
                    表头无法与字段一一对应，请确认列对应后继续提取，这一步不调用模型。
                  </p>
                  <div className="min-h-0 flex-1 overflow-y-auto p-4">
                    <div className="grid gap-x-6 gap-y-1.5 text-[12px] md:grid-cols-2">
                      {mappings.map((item, index) => (
                        <label key={`${item.header ?? "col"}-${index}`} className="grid grid-cols-[minmax(0,1fr)_180px] items-center gap-2">
                          <span className="truncate text-zinc-700" title={item.header ?? ""}>
                            {item.header || "未命名列"}
                          </span>
                          <select
                            className="h-8 rounded-md border border-zinc-200 bg-white px-2"
                            value={item.field ?? ""}
                            onChange={(event) => {
                              const field = event.target.value;
                              setMappings((current) =>
                                current.map((entry, entryIndex) =>
                                  entryIndex === index ? { ...entry, field, transform: entry.transform || "direct" } : entry,
                                ),
                              );
                            }}
                          >
                            <option value="">不导入</option>
                            {(meta?.fields ?? []).map((field) => (
                              <option key={field.code} value={field.code}>
                                {field.label}
                              </option>
                            ))}
                          </select>
                        </label>
                      ))}
                    </div>
                  </div>
                  <div className="flex shrink-0 justify-end border-t border-zinc-200 bg-zinc-50/80 px-5 py-3">
                    <button type="button" className={primaryButton} disabled={busy} onClick={() => void applyMapping()}>
                      按此对应提取候选
                    </button>
                  </div>
                </div>
              ) : null}

              {ready && viewing === "review" ? (
                candidates.length === 0 ? (
                  <div className="flex flex-1 items-center justify-center p-8 text-[12px] text-zinc-500">
                    未提取到候选记录，请检查文件内容，或回到「核对结构」调整列对应后重新提取。
                  </div>
                ) : (
                  <div className="flex min-h-0 flex-1 flex-col">
                    {batchInfo && batchInfo.id === selectedBatchId ? (
                      <div className="flex shrink-0 flex-wrap items-center gap-x-3 gap-y-1 border-b border-zinc-100 bg-zinc-50/60 px-5 py-2 text-[11px] text-zinc-600">
                        <span className="font-medium text-zinc-800">批次汇总</span>
                        <span>{batchInfo.batch.task_count} 个文件</span>
                        <span>{batchInfo.batch.candidate_count} 条候选</span>
                        {batchInfo.gaps.length > 0 ? (
                          <span className="min-w-0 truncate" title={batchInfo.gaps.map((gap) => `${gap.dataset_name}.${gap.label} ×${gap.count}`).join("、")}>
                            主要缺口：
                            {batchInfo.gaps
                              .slice(0, 3)
                              .map((gap) => `${gap.label} ×${gap.count}`)
                              .join("、")}
                            {batchInfo.gaps.length > 3 ? ` 等 ${batchInfo.gaps.length} 项` : ""}
                          </span>
                        ) : (
                          <span className="text-emerald-700">批次必填项已全部覆盖</span>
                        )}
                        <button
                          type="button"
                          className="ml-auto inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-zinc-400 transition hover:bg-rose-50 hover:text-rose-600"
                          onClick={() =>
                            askDelete("batch", batchInfo.batch.id, `批次：${batchInfo.batch.title || `${batchInfo.batch.task_count} 个文件`}`)
                          }
                        >
                          <Trash2 className="size-3" />
                          删除整批
                        </button>
                      </div>
                    ) : null}

                    <div className="flex shrink-0 flex-wrap items-center gap-x-4 gap-y-2 border-b border-zinc-100 px-5 py-2.5 text-[11px]">
                      <div className="flex flex-wrap gap-1.5" role="group" aria-label="按分诊筛选">
                        <button
                          type="button"
                          aria-pressed={triageFilter === ""}
                          className={`rounded-full px-2.5 py-1 transition ${triageFilter === "" ? "bg-zinc-900 text-white" : "bg-zinc-100 text-zinc-600 hover:bg-zinc-200"}`}
                          onClick={() => {
                            setTriageFilter("");
                            candidateTable.setPageIndex(0);
                          }}
                        >
                          全部 {candidates.length}
                        </button>
                        {(["auto", "review", "missing", "duplicate"] as const).map((key) => (
                          <button
                            key={key}
                            type="button"
                            aria-pressed={triageFilter === key}
                            className={`rounded-full px-2.5 py-1 transition ${triageFilter === key ? "bg-zinc-900 text-white" : `${TRIAGE_BADGE[key]} hover:opacity-80`}`}
                            onClick={() => {
                              setTriageFilter(key);
                              candidateTable.setPageIndex(0);
                            }}
                          >
                            {TRIAGE_LABEL[key]} {triageCounts[key]}
                          </button>
                        ))}
                      </div>
                      <label className="flex items-center gap-1.5 text-zinc-600">
                        <input type="checkbox" checked={requiredOnly} onChange={(event) => setRequiredOnly(event.target.checked)} />
                        只显示必填字段
                      </label>
                      <div className="ml-auto flex flex-wrap items-center gap-1.5">
                        <select
                          className="h-7 max-w-40 min-w-0 rounded-md border border-zinc-200 bg-white px-1"
                          value={bulkField}
                          aria-label="批量设置的字段"
                          onChange={(event) => setBulkField(event.target.value)}
                        >
                          <option value="">批量设置字段</option>
                          {(meta?.fields ?? []).map((field) => (
                            <option key={field.code} value={field.code}>
                              {field.label}
                              {field.required ? " *" : ""}
                            </option>
                          ))}
                        </select>
                        <input
                          className="h-7 w-32 rounded-md border border-zinc-200 px-2"
                          value={bulkValue}
                          aria-label="统一填入的值"
                          placeholder="统一填入的值"
                          onChange={(event) => setBulkValue(event.target.value)}
                        />
                        <button
                          type="button"
                          className="h-7 rounded-md border border-zinc-200 bg-white px-2 text-zinc-600 transition hover:bg-zinc-50 disabled:opacity-50"
                          disabled={busy || picked.length === 0 || !bulkField}
                          onClick={() => void bulkSet()}
                        >
                          {bulkProgress
                            ? `写入中 ${bulkProgress.done}/${bulkProgress.total}`
                            : `应用到已选 ${picked.length} 条`}
                        </button>
                        <button
                          type="button"
                          className="flex h-7 items-center gap-1 rounded-md border border-zinc-200 bg-white px-2 text-zinc-700 transition hover:bg-zinc-50 disabled:opacity-50"
                          disabled={busy || !hasPending}
                          title="按当前已发布的数据重新查库补全并校验；适用于专业库等在解析之后才发布的场景"
                          onClick={() => void reassess()}
                        >
                          <RefreshCw className={`size-3.5 ${reassessing ? "animate-spin" : ""}`} aria-hidden="true" />
                          {reassessing ? "校验中…" : "重新校验"}
                        </button>
                        <button
                          type="button"
                          className="flex h-7 items-center gap-1 rounded-md border border-sky-200 bg-sky-50 px-2 text-sky-700 transition hover:bg-sky-100 disabled:opacity-50"
                          disabled={busy || !hasPending}
                          title="上传一份对照表（例如专业名称—专业代码），按共同字段批量回填候选"
                          onClick={() => setReferenceOpen(true)}
                        >
                          <FileSpreadsheet className="size-3.5" aria-hidden="true" />
                          补传参照表
                        </button>
                      </div>
                    </div>

                    <div className="flex min-h-0 flex-1 flex-col px-5 pt-3">
                      <DataTable
                        table={candidateTable}
                        stickyHeader
                        className="w-max min-w-full border-separate border-spacing-0 [&_td]:border-b [&_td]:border-zinc-100 [&_th]:border-b [&_th]:border-zinc-200"
                        containerClassName="min-h-[320px] flex-1 overflow-auto rounded-lg border border-zinc-200 lg:min-h-0 [scrollbar-color:#d4d4d8_transparent] [scrollbar-width:thin]"
                        rowClassName={(row) =>
                          `group/row align-top ${row.getIsSelected() ? "bg-sky-50 hover:bg-sky-50" : "hover:bg-zinc-50"}`
                        }
                      />
                      <TablePagination table={candidateTable} className="shrink-0 border-t-0 px-0 py-2" />
                    </div>

                    <div className="flex shrink-0 flex-col gap-2 border-t border-zinc-200 bg-zinc-50/80 px-5 py-3">
                      {writing ? (
                        <div>
                          <div className="flex items-center justify-between gap-3 text-[11px] text-zinc-600">
                            <span className="flex items-center gap-1.5 font-medium">
                              <span className="size-3 animate-spin rounded-full border-2 border-zinc-300 border-t-zinc-700" aria-hidden="true" />
                              正在写入 {writing.done} / {writing.total} 条，每批 {CONFIRM_BATCH} 条，请不要关闭页面
                            </span>
                            <span className="tabular-nums text-zinc-400">
                              {Math.round((writing.done / Math.max(1, writing.total)) * 100)}%
                            </span>
                          </div>
                          <ProgressBar
                            value={writing.done}
                            max={writing.total}
                            label={`已写入 ${writing.done} / ${writing.total} 条`}
                            className="mt-1.5"
                          />
                        </div>
                      ) : null}
                      {writeError ? (
                        <div
                          role="alert"
                          className="flex items-start justify-between gap-2 rounded-md bg-rose-50 px-3 py-2 text-[11px] leading-4 text-rose-700"
                        >
                          <span>{writeError}</span>
                          <button
                            type="button"
                            className="shrink-0 text-rose-400 transition hover:text-rose-600"
                            aria-label="关闭错误提示"
                            onClick={() => setWriteError("")}
                          >
                            <X className="size-3.5" />
                          </button>
                        </div>
                      ) : null}
                      <div className="flex flex-wrap items-center gap-3 text-[12px]">
                        <span className="text-zinc-500">
                          可确认 <b className="font-semibold text-zinc-800 tabular-nums">{pickable.length}</b> 条，已生成草稿{" "}
                          <b className="font-semibold text-zinc-800 tabular-nums">{written}</b> 条
                        </span>
                        {picked.length > pickedConfirmable ? (
                          <span className="text-amber-600">
                            所选 {picked.length} 条里有 {picked.length - pickedConfirmable} 条需先修正或补齐业务主键，确认时会跳过
                          </span>
                        ) : null}
                        {blockedReason ? <span className="text-amber-600">{blockedReason}</span> : null}
                        <label className="ml-auto flex items-center gap-1 text-zinc-600">
                          <input
                            type="checkbox"
                            checked={submit}
                            disabled={Boolean(writing)}
                            onChange={(event) => setSubmit(event.target.checked)}
                          />
                          确认后直接提交审核
                        </label>
                        {autoConfirmable.length > 0 ? (
                          <button
                            type="button"
                            className="h-9 rounded-md border border-emerald-200 bg-emerald-50 px-3 text-xs font-medium text-emerald-700 transition hover:bg-emerald-100 disabled:opacity-50"
                            disabled={busy || Boolean(writing)}
                            onClick={() => void confirmSelected(autoConfirmable)}
                            title="仅确认无需复核且必填齐全的候选"
                          >
                            确认全部可直接确认的（{autoConfirmable.length}）
                          </button>
                        ) : null}
                        <button
                          type="button"
                          className={primaryButton}
                          disabled={busy || pickedConfirmable === 0}
                          onClick={() => void confirmSelected()}
                        >
                          {writing ? (
                            <span className="size-3 animate-spin rounded-full border-2 border-white/40 border-t-white" aria-hidden="true" />
                          ) : null}
                          {writing ? `写入中 ${writing.done}/${writing.total}` : `确认所选${pickedConfirmable > 0 ? `（${pickedConfirmable}）` : ""}`}
                        </button>
                      </div>
                    </div>
                  </div>
                )
              ) : null}

              {ready && viewing === "done" ? (
                <div className="flex flex-1 flex-col items-center justify-center gap-3 p-8 text-center">
                  <p className="text-[15px] font-semibold text-zinc-900">已生成 {written} 条草稿</p>
                  <p className="max-w-md text-[12px] leading-5 text-zinc-500">
                    草稿在「我的填报」里，可以继续修改后提交审核。勾选过「确认后直接提交审核」的记录已经进入审核流程。
                  </p>
                  <div className="flex flex-wrap justify-center gap-2">
                    <Link href="/my-fill" className={primaryButton}>
                      到我的填报查看
                    </Link>
                    <button
                      type="button"
                      className={ghostButton}
                      onClick={() => setViewChoice({ task: selectedId, from: currentStep, step: "review" })}
                    >
                      回看候选记录
                    </button>
                    <button type="button" className={ghostButton} onClick={() => setUploadOpen(true)}>
                      新建解析
                    </button>
                  </div>
                </div>
              ) : null}

              <p className="sr-only" aria-live="polite">
                当前第 {stepIndex + 1} 步：{STEPS[stepIndex]?.label}
              </p>
            </>
          )}
        </section>
      </div>

      <UploadDialog
        open={uploadOpen}
        onOpenChange={setUploadOpen}
        datasets={datasets}
        datasetCode={datasetCode}
        onDatasetChange={setDatasetCode}
        prompt={prompt}
        onPromptChange={setPrompt}
        freshPlan={freshPlan}
        onFreshPlanChange={setFreshPlan}
        files={files}
        onFilesChange={setFiles}
        canAppend={Boolean(selected?.batch_id)}
        appendToBatch={appendToBatch}
        onAppendChange={setAppendToBatch}
        busy={busy}
        onSubmit={() => void createTask()}
      />

      {selected ? (
        <ReferenceDialog
          open={referenceOpen}
          onOpenChange={setReferenceOpen}
          taskId={selected.id}
          onApplied={(result) => void referenceApplied(result)}
        />
      ) : null}

      <Dialog
        open={Boolean(deleting)}
        onOpenChange={(next) => {
          if (!next && !removing) setDeleting(null);
        }}
      >
        <DialogContent
          showCloseButton={false}
          overlayClassName="bg-zinc-900/40"
          className="flex w-full max-w-[calc(100%-2rem)] flex-col gap-0 overflow-hidden bg-white p-0 text-zinc-900 ring-zinc-200 sm:max-w-md"
        >
          <DialogHeader className="shrink-0 border-b border-zinc-100 px-5 py-3.5">
            <DialogTitle className="text-[14px] font-semibold tracking-tight text-zinc-900">删除确认</DialogTitle>
            <DialogDescription className="mt-1 text-[11px] leading-4 text-zinc-500">
              将删除「{deleting?.name ?? ""}」的任务、候选记录和已上传文件，删除后无法恢复。
              {deleting?.kind === "batch" ? "批内所有文件会一起删除。" : ""}
            </DialogDescription>
          </DialogHeader>
          <div className="px-5 py-4 text-[12px]">
            <label className="flex cursor-pointer items-start gap-2 text-zinc-700">
              <input
                type="checkbox"
                className="mt-0.5 size-3.5 cursor-pointer accent-rose-600"
                checked={purgeDrafts}
                disabled={removing}
                onChange={(event) => setPurgeDrafts(event.target.checked)}
              />
              <span>
                同时清除已生成的草稿
                <span className="mt-0.5 block text-[10px] leading-4 text-zinc-400">
                  只清除由文件解析生成、仍处于草稿或退回状态的记录；已提交审核的记录会阻止删除，请先撤回。
                </span>
              </span>
            </label>
          </div>
          <DialogFooter className="mx-0 mb-0 shrink-0 flex-row justify-end gap-2 border-t border-zinc-100 bg-white px-5 py-3">
            <button
              type="button"
              className="h-9 rounded-md border border-zinc-200 bg-white px-3 text-xs font-medium text-zinc-700 transition hover:bg-zinc-50 disabled:opacity-45"
              disabled={removing}
              onClick={() => setDeleting(null)}
            >
              取消
            </button>
            <button
              type="button"
              className="h-9 rounded-md bg-rose-600 px-3 text-xs font-medium text-white transition hover:bg-rose-700 disabled:opacity-60"
              disabled={removing}
              onClick={() => void removeTarget()}
            >
              {removing ? "删除中…" : "确认删除"}
            </button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      <Dialog
        open={replanning}
        onOpenChange={(next) => {
          if (!next) setReplanning(false);
        }}
      >
        <DialogContent
          showCloseButton={false}
          overlayClassName="bg-zinc-900/40"
          className="flex w-full max-w-[calc(100%-2rem)] flex-col gap-0 overflow-hidden bg-white p-0 text-zinc-900 ring-zinc-200 sm:max-w-md"
        >
          <DialogHeader className="shrink-0 border-b border-zinc-100 px-5 py-3.5">
            <DialogTitle className="text-[14px] font-semibold tracking-tight text-zinc-900">重新识别结构</DialogTitle>
            <DialogDescription className="mt-1 text-[11px] leading-4 text-zinc-500">
              将丢弃「{selected?.file_name ?? ""}」当前的结构和全部候选记录，不使用已记住的结构，由模型重新识别。
              {selected?.user_prompt ? `补充说明「${selected.user_prompt}」会一并交给模型。` : ""}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className="mx-0 mb-0 shrink-0 flex-row justify-end gap-2 border-t border-zinc-100 bg-white px-5 py-3">
            <button
              type="button"
              className="h-9 rounded-md border border-zinc-200 bg-white px-3 text-xs font-medium text-zinc-700 transition hover:bg-zinc-50"
              onClick={() => setReplanning(false)}
            >
              取消
            </button>
            <button
              type="button"
              className={primaryButton}
              disabled={busy || !selected}
              onClick={() => selected && void replan(selected)}
            >
              确认重新识别
            </button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      <CandidateEditor
        candidate={editing}
        meta={meta}
        draft={draft}
        busy={busy}
        onDraftChange={(code, value) => setDraft((current) => ({ ...current, [code]: value }))}
        onClose={() => setEditing(null)}
        onSave={() => void saveCandidate()}
      />
    </div>
  );
}

/** 第①步：排队、解析中显示进度；失败时给出原因和重试入口。 */
function ParseStep({ task, onRetry }: { task: IngestTask; onRetry: () => void }) {
  if (task.status === "failed") {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-3 p-8">
        <div className="w-full max-w-lg rounded-lg border border-rose-200 bg-rose-50/60 px-4 py-3">
          <p className="text-[13px] font-medium text-rose-800">解析失败</p>
          <p className="mt-1 text-[12px] leading-5 break-words text-rose-700">{task.error_message || "未知错误"}</p>
          <p className="mt-2 text-[11px] text-rose-600/80">已尝试 {task.attempts} 次。重试会重新读取文件并生成结构。</p>
        </div>
        <button type="button" className={primaryButton} onClick={onRetry}>
          <RotateCcw className="size-3.5" aria-hidden="true" />
          重试
        </button>
      </div>
    );
  }
  if (task.status === "cancelled") {
    return <div className="flex flex-1 items-center justify-center p-8 text-[12px] text-zinc-500">任务已取消。</div>;
  }
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-3 p-8">
      <div className="w-full max-w-md">
        <div className="flex items-center justify-between text-[12px] text-zinc-600">
          <span className="flex items-center gap-1.5">
            <span className="size-3 animate-spin rounded-full border-2 border-zinc-300 border-t-zinc-700" aria-hidden="true" />
            {STATUS_LABEL[task.status] || task.status}
          </span>
          <span className="tabular-nums text-zinc-400">{task.progress}%</span>
        </div>
        <ProgressBar value={task.progress} max={100} className="mt-2" label={`进度 ${task.progress}%`} />
        <p className="mt-3 text-center text-[11px] leading-5 text-zinc-400">
          宽表首次解析需要模型识别结构，通常不到 1 分钟。可以先处理其他任务，完成后这里会自动刷新。
        </p>
      </div>
    </div>
  );
}

/** 宽表单元格：显示字典中文名，标出缺失的必填项、校验错误和模型推断的值。 */
function FieldCell({ row, field, meta }: { row: Candidate; field: FieldMeta; meta: DatasetMeta | null }) {
  const raw = row.values[field.code];
  const empty = raw == null || String(raw).trim() === "";
  const source = row.field_sources?.[field.code]?.source;
  const evidence = row.field_sources?.[field.code]?.evidence;
  const hasError = !row.record_id && row.errors.some((item) => item.includes(field.label));
  if (empty) {
    if (field.required && !row.record_id) {
      return <span className="rounded bg-amber-50 px-1.5 py-0.5 text-[11px] text-amber-700">缺</span>;
    }
    return <span className="text-zinc-300">—</span>;
  }
  const text = meta ? optionLabel(meta, field.code, raw) : String(raw);
  const inferred = source === "ai" || source === "completion";
  const title = [text, source ? `来源：${SOURCE_LABEL[source] ?? source}` : "", evidence ? `证据：${evidence}` : ""]
    .filter(Boolean)
    .join("\n");
  return (
    <span
      className={`block truncate ${hasError ? "rounded bg-rose-50 px-1 text-rose-700" : inferred ? "text-violet-700" : "text-zinc-800"}`}
      title={title}
    >
      {text}
    </span>
  );
}

/** 候选记录修正对话框：把校验未通过的记录放进弹窗编辑，避免挤压候选表格的高度。 */
function CandidateEditor({
  candidate,
  meta,
  draft,
  busy,
  onDraftChange,
  onClose,
  onSave,
}: {
  candidate: Candidate | null;
  meta: DatasetMeta | null;
  draft: Record<string, string>;
  busy: boolean;
  onDraftChange: (code: string, value: string) => void;
  onClose: () => void;
  onSave: () => void;
}) {
  const open = Boolean(candidate && meta);
  const issues = candidate ? [...candidate.errors, ...candidate.warnings] : [];
  const missingKey = (candidate?.missing_key ?? []).map(
    (code) => meta?.fields.find((field) => field.code === code)?.label ?? code,
  );
  const hasIssues = issues.length > 0 || missingKey.length > 0;

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        // 保存过程中不允许关闭，避免请求回来时弹窗已被销毁。
        if (!next && !busy) onClose();
      }}
    >
      <DialogContent
        showCloseButton={false}
        overlayClassName="bg-zinc-900/40"
        className="flex max-h-[85vh] w-full max-w-[calc(100%-2rem)] flex-col gap-0 overflow-hidden bg-white p-0 text-zinc-900 ring-zinc-200 sm:max-w-xl"
      >
        <DialogHeader className="shrink-0 flex-row items-center justify-between gap-3 space-y-0 border-b border-zinc-100 px-5 py-3.5">
          <div className="min-w-0">
            <DialogTitle className="text-[14px] font-semibold tracking-tight text-zinc-900">
              修正第 {candidate?.seq ?? ""} 条
            </DialogTitle>
            <DialogDescription className="mt-0.5 truncate text-[11px] text-zinc-500">
              {candidate && meta ? summary(candidate, meta) : "调整字段后保存，系统会重新校验"}
            </DialogDescription>
          </div>
          <button
            type="button"
            className="flex size-7 shrink-0 items-center justify-center rounded-md text-zinc-400 transition hover:bg-zinc-100 hover:text-zinc-600 disabled:opacity-40"
            onClick={onClose}
            disabled={busy}
            aria-label="关闭"
          >
            <X className="size-3.5" />
          </button>
        </DialogHeader>

        <div className="grid min-h-0 flex-1 grid-cols-1 content-start gap-3 overflow-y-auto px-5 py-4 text-[12px] sm:grid-cols-2">
          {hasIssues ? (
            <div className="space-y-1 rounded-md bg-amber-50/70 px-3 py-2 sm:col-span-2">
              <p className="text-[11px] font-medium text-amber-700">需要处理的问题</p>
              {candidate?.errors.map((item, index) => (
                <p key={`e-${index}-${item}`} className="text-[11px] leading-4 text-rose-600">
                  {item}
                </p>
              ))}
              {missingKey.length > 0 ? (
                <p className="text-[11px] leading-4 text-amber-700">
                  缺业务主键：{missingKey.join("、")}，补齐后才能写入
                </p>
              ) : null}
              {candidate?.warnings.map((item, index) => (
                <p key={`w-${index}-${item}`} className="text-[11px] leading-4 text-amber-700">
                  {item}
                </p>
              ))}
              {(candidate?.conflicts ?? []).map((item, index) => (
                <p key={`c-${index}`} className="text-[11px] leading-4 text-amber-700">
                  冲突字段 {item.label || item.code}：文件值「{item.kept}」，未采用「{item.dropped}」
                </p>
              ))}
            </div>
          ) : (
            <p className="text-[11px] text-zinc-400 sm:col-span-2">此记录校验通过，可按需调整字段后保存。</p>
          )}
          {meta
            ? meta.fields.map((field) => (
                <FieldInput
                  key={field.code}
                  field={field}
                  meta={meta}
                  value={draft[field.code] ?? ""}
                  source={candidate?.field_sources?.[field.code]}
                  onChange={(value) => onDraftChange(field.code, value)}
                />
              ))
            : null}
        </div>

        <DialogFooter className="mx-0 mb-0 shrink-0 flex-row justify-end gap-2 border-t border-zinc-100 bg-white px-5 py-3">
          <button
            type="button"
            className="h-9 rounded-md border border-zinc-200 bg-white px-3 text-xs font-medium text-zinc-700 transition hover:bg-zinc-50 disabled:cursor-not-allowed disabled:opacity-45"
            onClick={onClose}
            disabled={busy}
          >
            取消
          </button>
          <button type="button" className={primaryButton} disabled={busy} onClick={onSave}>
            {busy ? (
              <span className="size-3 animate-spin rounded-full border-2 border-white/40 border-t-white" aria-hidden="true" />
            ) : null}
            {busy ? "正在校验" : "保存并重新校验"}
          </button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function summary(row: Candidate, meta: DatasetMeta | null) {
  const fields = meta?.list_fields ?? Object.keys(row.values).slice(0, 3);
  return (
    fields
      .map((code) => {
        const value = row.values[code];
        const dict = meta?.fields.find((field) => field.code === code)?.dict_code;
        const option = dict ? meta?.dicts[dict]?.find((item) => item.value === String(value)) : undefined;
        return option ? option.label : value;
      })
      .filter((value) => value != null && value !== "")
      .join("，") || "未识别到字段"
  );
}

function FieldInput({
  field,
  meta,
  value,
  source,
  onChange,
}: {
  field: FieldMeta;
  meta: DatasetMeta;
  value: string;
  source?: { source?: string; score?: number; evidence?: string };
  onChange: (value: string) => void;
}) {
  const hint = source?.source ? SOURCE_LABEL[source.source] ?? source.source : "";
  const sourceTone =
    source?.source === "file"
      ? "border-zinc-200"
      : source?.source === "ai" || source?.source === "completion"
        ? "border-violet-300 bg-violet-50/30"
        : source?.source === "lookup" || source?.source === "dict"
          ? "border-sky-300 bg-sky-50/30"
          : source?.source === "derive"
            ? "border-teal-300 bg-teal-50/30"
            : "border-zinc-200";
  const evidence = source?.evidence ? `证据：${source.evidence}` : hint ? `来源：${hint}` : undefined;
  const options = field.dict_code ? meta.dicts[field.dict_code] : undefined;
  if (field.dict_code === "departments") {
    return (
      <label className="block">
        <span className="text-zinc-500">{field.label}</span>
        <select className={`mt-1 h-8 w-full rounded-md border px-2 ${sourceTone}`} title={evidence} value={value} onChange={(event) => onChange(event.target.value)}>
          <option value="">请选择</option>
          {meta.departments.map((name) => (
            <option key={name} value={name}>{name}</option>
          ))}
        </select>
        {hint ? <span className="mt-0.5 block text-[10px] text-zinc-400">来源：{hint}</span> : null}
      </label>
    );
  }
  if (options) {
    return (
      <label className="block">
        <span className="text-zinc-500">{field.label}</span>
        <select className={`mt-1 h-8 w-full rounded-md border px-2 ${sourceTone}`} title={evidence} value={value} onChange={(event) => onChange(event.target.value)}>
          <option value="">请选择</option>
          {options.map((item) => (
            <option key={item.value} value={item.value}>{item.label}</option>
          ))}
        </select>
        {hint ? <span className="mt-0.5 block text-[10px] text-zinc-400">来源：{hint}</span> : null}
      </label>
    );
  }
  return (
    <label className="block">
      <span className="text-zinc-500">{field.label}</span>
      <input className={`mt-1 h-8 w-full rounded-md border px-2 ${sourceTone}`} title={evidence} value={value} onChange={(event) => onChange(event.target.value)} />
      {hint ? <span className="mt-0.5 block text-[10px] text-zinc-400">来源：{hint}</span> : null}
    </label>
  );
}
