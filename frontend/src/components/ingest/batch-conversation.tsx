"use client";

import { Check, Download, FileSpreadsheet, MessageSquareText, Send, Upload, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import {
  ACTIVE,
  STATUS_LABEL,
  TIER_LABEL,
  type ActionRead,
  type IngestTask,
  type NextRead,
  type RoundRead,
  type SupplementDetail,
} from "@/components/ingest/types";
import { ghostButton, primaryButton } from "@/components/page-bits";
import { useToast } from "@/components/toast";
import { ApiError, api, download, upload } from "@/lib/api";

type Reply = { id: number; text: string; mine: boolean };

export type BatchState = {
  rounds: RoundRead[];
  actions: ActionRead[];
  next: NextRead | null;
  /** 本次打开页面后的对话记录；放在这里，展开和收起两种形态切换时不会丢 */
  replies: Reply[];
  say: (text: string, mine?: boolean) => void;
  refresh: () => Promise<void>;
};

type Loaded = { id: string; rounds: RoundRead[]; actions: ActionRead[]; next: NextRead | null };

const EMPTY: RoundRead[] = [];
const NO_ACTIONS: ActionRead[] = [];
const NO_REPLIES: Reply[] = [];

/**
 * 轮次、待确认动作和下一步建议。
 * batchId 为空时不请求；version 变化时重新拉取；切换批次后在新数据回来前返回空值。
 */
export function useBatchState(batchId: string, version: string): BatchState {
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const [talk, setTalk] = useState<{ id: string; replies: Reply[] }>({ id: "", replies: [] });
  const replySeq = useRef(0);

  const say = useCallback(
    (text: string, mine = false) => {
      replySeq.current += 1;
      const reply = { id: replySeq.current, text, mine };
      setTalk((current) => ({
        id: batchId,
        replies: current.id === batchId ? [...current.replies, reply] : [reply],
      }));
    },
    [batchId],
  );

  const refresh = useCallback(async () => {
    if (!batchId) return;
    const [rounds, actions, next] = await Promise.all([
      api<RoundRead[]>(`/api/ingestion/batches/${batchId}/rounds`),
      api<ActionRead[]>(`/api/ingestion/batches/${batchId}/actions`),
      api<NextRead>(`/api/ingestion/batches/${batchId}/next`),
    ]);
    setLoaded({ id: batchId, rounds, actions, next });
  }, [batchId]);

  useEffect(() => {
    if (!batchId) return;
    let cancelled = false;
    queueMicrotask(() => {
      if (cancelled) return;
      void refresh().catch(() => undefined);
    });
    return () => {
      cancelled = true;
    };
  }, [batchId, refresh, version]);

  const current = loaded && loaded.id === batchId ? loaded : null;
  return {
    rounds: current?.rounds ?? EMPTY,
    actions: current?.actions ?? NO_ACTIONS,
    next: current?.next ?? null,
    replies: talk.id === batchId ? talk.replies : NO_REPLIES,
    say,
    refresh,
  };
}

function pendingTotal(next: NextRead | null) {
  return next ? Object.values(next.totals).reduce((sum, value) => sum + value, 0) : 0;
}

/**
 * 批次的多轮补齐对话。
 * 展开时左边是轮次时间线和输入框，右边固定放待确认动作和下一步建议；
 * 收起时只剩一行：输入框、下一步建议和待确认条数。两种形态共用同一份对话记录。
 */
export function BatchConversation({
  collapsed,
  state,
  batchId,
  datasetCode,
  names,
  tasks,
  onExpand,
  onRemoveBatch,
  onSelectTask,
  onUploaded,
  onChanged,
  onShowTriage,
}: {
  collapsed: boolean;
  state: BatchState;
  batchId: string;
  datasetCode: string;
  names: Map<string, string>;
  /** 本批次的文件任务，用于显示正在处理的文件 */
  tasks: IngestTask[];
  onExpand: () => void;
  onRemoveBatch: () => void;
  onSelectTask: (id: string) => void;
  onUploaded: (task: IngestTask) => void;
  onChanged: () => void;
  onShowTriage: (triage: "auto" | "review" | "missing") => void;
}) {
  const toast = useToast();
  const { rounds, actions, next, replies, say, refresh } = state;
  const [text, setText] = useState("");
  const [sending, setSending] = useState(false);
  const [working, setWorking] = useState("");
  const [asNew, setAsNew] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);
  const bottom = useRef<HTMLLIElement>(null);

  const running = tasks.filter((task) => ACTIVE.has(task.status));
  const step = next?.next;
  const target = step?.dataset_code || datasetCode;
  const proposed = actions.filter((action) => action.status === "proposed");
  const last = rounds.at(-1)?.report;

  useEffect(() => {
    if (!collapsed) bottom.current?.scrollIntoView({ block: "nearest" });
  }, [collapsed, rounds.length, replies.length, running.length]);

  async function send() {
    const message = text.trim();
    if (!message || sending) return;
    setSending(true);
    say(message, true);
    setText("");
    try {
      const result = await api<{ reply: string; action: ActionRead | null }>(
        `/api/ingestion/batches/${batchId}/messages`,
        { method: "POST", body: JSON.stringify({ text: message, dataset_code: datasetCode }) },
      );
      say(result.reply);
      if (collapsed) toast(result.reply, "info");
      if (result.action) await refresh();
    } catch (reason: unknown) {
      const error = reason instanceof ApiError ? reason.message : "发送失败，请稍后再试";
      say(error);
      if (collapsed) toast(error, "error");
    } finally {
      setSending(false);
    }
  }

  async function decide(action: ActionRead, apply: boolean) {
    setWorking(action.id);
    try {
      await api(`/api/ingestion/actions/${action.id}/${apply ? "apply" : "reject"}`, { method: "POST" });
      if (apply) {
        toast(`已执行：${action.preview.summary}`);
        onChanged();
      }
      await refresh();
    } catch (reason: unknown) {
      toast(reason instanceof ApiError ? reason.message : "操作失败", "error");
      await refresh().catch(() => undefined);
    } finally {
      setWorking("");
    }
  }

  async function sendFile(file: File, dataset: string) {
    setWorking("upload");
    try {
      const body = new FormData();
      body.set("dataset_code", dataset);
      body.set("as_new", String(asNew));
      body.set("file", file);
      const task = await upload<IngestTask>(`/api/ingestion/batches/${batchId}/files`, body);
      toast(asNew ? "已上传，将作为新数据解析" : "已上传，系统会先与已有记录对齐再补空字段");
      setAsNew(false);
      onUploaded(task);
    } catch (reason: unknown) {
      toast(reason instanceof ApiError ? reason.message : "上传失败", "error");
    } finally {
      setWorking("");
      if (fileInput.current) fileInput.current.value = "";
    }
  }

  async function downloadTemplate(dataset: string, fields: string[]) {
    setWorking("template");
    try {
      const query = new URLSearchParams({ dataset_code: dataset, fields: fields.join(",") });
      await download(
        `/api/ingestion/batches/${batchId}/supplement-template?${query.toString()}`,
        `${names.get(dataset) ?? dataset}-补充模板.xlsx`,
      );
    } catch (reason: unknown) {
      toast(reason instanceof ApiError ? reason.message : "模板生成失败", "error");
    } finally {
      setWorking("");
    }
  }

  /** 收起形态下的“去处理”：能就地完成的直接跳转，需要上传或下载的先展开对话。 */
  function act() {
    if (step?.kind === "plan" && step.task_id) onSelectTask(step.task_id);
    else if (step?.kind === "conflicts") onShowTriage("review");
    else if (step?.kind === "confirm") onShowTriage("auto");
    else onExpand();
  }

  const filePicker = (
    <input
      ref={fileInput}
      type="file"
      className="sr-only"
      accept=".xlsx,.xls,.csv,.docx,.pdf"
      onChange={(event) => {
        const file = event.target.files?.[0];
        if (file && target) void sendFile(file, target);
      }}
    />
  );

  const composer = (compact: boolean) => (
    <form
      className={`flex min-w-0 items-end gap-2 ${compact ? "flex-1" : "shrink-0 border-t border-zinc-100 px-3 py-2"}`}
      onSubmit={(event) => {
        event.preventDefault();
        void send();
      }}
    >
      <textarea
        rows={1}
        className={`min-w-0 flex-1 resize-none rounded-md border border-zinc-200 px-2 text-[12px] outline-none focus:border-zinc-400 ${
          compact ? "h-8 py-1.5" : "h-10 py-2"
        }`}
        maxLength={500}
        value={text}
        placeholder="一句话批量补，例如：这些课程都不是校企合作开发"
        onChange={(event) => setText(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
            event.preventDefault();
            void send();
          }
        }}
      />
      <button
        type="submit"
        className={`${primaryButton} h-8 shrink-0 px-2.5`}
        disabled={sending || !text.trim()}
        aria-label="发送"
      >
        <Send className="size-3.5" aria-hidden="true" />
      </button>
    </form>
  );

  if (collapsed) {
    return (
      <div className="flex min-w-0 flex-1 items-center gap-3">
        {composer(true)}
        {step ? (
          <span className="hidden min-w-0 max-w-[45%] items-center gap-2 text-[12px] md:flex">
            <span className="truncate text-zinc-500" title={step.message}>
              下一步：{step.message}
            </span>
            {step.kind !== "wait" ? (
              <button type="button" className="shrink-0 font-medium text-sky-700 hover:text-sky-900" onClick={act}>
                去处理
              </button>
            ) : null}
          </span>
        ) : null}
        {proposed.length > 0 ? (
          <button
            type="button"
            className="shrink-0 rounded-full bg-amber-50 px-2.5 py-1 text-[11px] font-medium text-amber-700 hover:bg-amber-100"
            onClick={onExpand}
          >
            待确认 {proposed.length} 条
          </button>
        ) : null}
        {filePicker}
      </div>
    );
  }

  return (
    <section className="@container flex min-h-0 min-w-0 flex-1 flex-col" aria-label="补齐对话">
      <header className="flex shrink-0 items-center gap-x-4 gap-y-1 border-b border-zinc-100 px-4 py-2 text-[12px] text-zinc-600">
        <span className="flex shrink-0 items-center gap-1.5 font-semibold text-zinc-900">
          <MessageSquareText className="size-4 text-zinc-500" aria-hidden="true" />
          补齐对话
        </span>
        <span className="shrink-0">
          第 <b className="font-semibold text-zinc-900 tabular-nums">{rounds.length}</b> 轮
        </span>
        <span className="hidden shrink-0 sm:inline">
          待确认 <b className="font-semibold text-zinc-900 tabular-nums">{pendingTotal(next)}</b> 条
          {next?.ready ? <span className="text-emerald-700">（{next.ready} 条可直接入库）</span> : null}
        </span>
        {last?.completeness_after != null ? (
          <span className="hidden shrink-0 md:inline">
            完整度 <b className="font-semibold text-zinc-900 tabular-nums">{last.completeness_after}%</b>
          </span>
        ) : null}
        <button
          type="button"
          className="ml-auto shrink-0 text-[11px] text-zinc-400 hover:text-rose-600"
          onClick={onRemoveBatch}
        >
          删除整批
        </button>
      </header>

      <div className="flex min-h-0 flex-1 flex-col @2xl:flex-row">
        <div className="flex min-h-0 min-w-0 flex-1 flex-col">
          <ol className="min-h-0 flex-1 space-y-2 overflow-y-auto px-4 py-3 text-[12px] [scrollbar-width:thin]">
            {rounds.length === 0 && running.length === 0 && replies.length === 0 ? (
              <li className="text-zinc-400">文件解析完成后，这里会告诉你填进了什么、还缺什么。</li>
            ) : null}
            {rounds.map((round) => (
              <RoundCard key={round.id} round={round} onSelect={onSelectTask} />
            ))}
            {running.map((task) => (
              <li key={task.id} className="rounded-md border border-dashed border-sky-200 bg-sky-50/50 px-3 py-2 text-sky-700">
                <span className="font-medium">{task.file_name || "文件"}</span>：{STATUS_LABEL[task.status] ?? task.status}
                {task.progress ? ` ${task.progress}%` : ""}
              </li>
            ))}
            {replies.map((reply) => (
              <li
                key={reply.id}
                className={`w-fit max-w-[85%] rounded-lg px-3 py-1.5 leading-5 ${
                  reply.mine ? "ml-auto bg-zinc-900 text-white" : "bg-zinc-100 text-zinc-700"
                }`}
              >
                {reply.text}
              </li>
            ))}
            <li ref={bottom} aria-hidden="true" />
          </ol>
          {composer(false)}
        </div>

        <aside
          className="flex max-h-32 shrink-0 flex-col gap-2 overflow-y-auto border-t border-zinc-100 bg-zinc-50/50 p-3 text-[12px] [scrollbar-width:thin] @2xl:max-h-none @2xl:w-72 @2xl:border-t-0 @2xl:border-l @4xl:w-80"
          aria-label="下一步与待确认"
        >
          {proposed.map((action) => (
            <div key={action.id} className="rounded-md border border-amber-200 bg-amber-50/70 px-3 py-2.5">
              <p className="font-medium text-zinc-900">待确认：{action.preview.summary}</p>
              <p className="mt-0.5 text-[11px] text-zinc-500">
                “{action.message}”，影响 {action.preview.count} 条记录
              </p>
              {action.preview.samples.length > 0 ? (
                <ul className="mt-1.5 space-y-0.5 text-[11px] text-zinc-600">
                  {action.preview.samples.slice(0, 3).map((sample, index) => (
                    <li key={`${sample.id}-${index}`} className="truncate" title={sample.label}>
                      {sample.label}
                      {sample.field ? `：${sample.field}` : ""}
                      {sample.after ? ` ${sample.before || "空"} → ${sample.after}` : ""}
                    </li>
                  ))}
                </ul>
              ) : null}
              <div className="mt-2 flex gap-2">
                <button
                  type="button"
                  className={`${primaryButton} h-7 px-2.5`}
                  disabled={Boolean(working)}
                  onClick={() => void decide(action, true)}
                >
                  <Check className="size-3.5" aria-hidden="true" />
                  执行
                </button>
                <button
                  type="button"
                  className={`${ghostButton} h-7 px-2.5`}
                  disabled={Boolean(working)}
                  onClick={() => void decide(action, false)}
                >
                  <X className="size-3.5" aria-hidden="true" />
                  取消
                </button>
              </div>
            </div>
          ))}

          {step ? (
            <div className="rounded-md border border-zinc-200 bg-white px-3 py-2.5">
              <p className="text-[11px] font-medium text-zinc-500">下一步建议</p>
              <p className="mt-1 leading-5 text-zinc-800">{step.message}</p>
              <div className="mt-2 flex flex-wrap gap-2">
                {step.kind === "plan" && step.task_id ? (
                  <button
                    type="button"
                    className={`${primaryButton} h-7 px-2.5`}
                    onClick={() => onSelectTask(step.task_id as string)}
                  >
                    去确认读取方式
                  </button>
                ) : null}
                {step.kind === "template" && target ? (
                  <button
                    type="button"
                    className={`${ghostButton} h-7 px-2.5`}
                    disabled={Boolean(working)}
                    onClick={() => void downloadTemplate(target, step.fields)}
                  >
                    <Download className="size-3.5" aria-hidden="true" />
                    下载补充模板
                  </button>
                ) : null}
                {step.kind === "template" || step.kind === "upload" ? (
                  <button
                    type="button"
                    className={`${primaryButton} h-7 px-2.5`}
                    disabled={Boolean(working) || !target}
                    onClick={() => fileInput.current?.click()}
                  >
                    <Upload className="size-3.5" aria-hidden="true" />
                    {working === "upload" ? "正在上传" : "上传文件"}
                  </button>
                ) : null}
                {step.kind === "conflicts" ? (
                  <button type="button" className={`${ghostButton} h-7 px-2.5`} onClick={() => onShowTriage("review")}>
                    查看冲突记录
                  </button>
                ) : null}
                {step.kind === "confirm" ? (
                  <button type="button" className={`${primaryButton} h-7 px-2.5`} onClick={() => onShowTriage("auto")}>
                    去确认入库
                  </button>
                ) : null}
              </div>
              {step.kind === "template" || step.kind === "upload" ? (
                <label className="mt-2 flex items-center gap-1.5 text-[11px] text-zinc-500">
                  <input type="checkbox" checked={asNew} onChange={(event) => setAsNew(event.target.checked)} />
                  作为新数据（不与已有记录对齐，可新增记录）
                </label>
              ) : null}
            </div>
          ) : (
            <p className="text-zinc-400">加载中…</p>
          )}
          {filePicker}
        </aside>
      </div>
    </section>
  );
}

function RoundCard({ round, onSelect }: { round: RoundRead; onSelect: (id: string) => void }) {
  const report = round.report;
  const title =
    report.trigger === "file"
      ? `文件「${report.file_name ?? "未命名"}」${report.mode === "supplement" ? "（补齐）" : ""}`
      : `你说：“${report.message ?? ""}”`;
  const waiting = report.status === "awaiting_plan";
  return (
    <li className="rounded-md border border-zinc-200 px-3 py-2">
      <p className="flex items-center gap-1.5 text-[11px] text-zinc-500">
        <FileSpreadsheet className="size-3.5 shrink-0" aria-hidden="true" />
        <span className="shrink-0">第 {round.seq} 轮</span>
        {report.trigger === "file" && round.task_id ? (
          <button
            type="button"
            className="truncate text-left hover:text-zinc-900 hover:underline"
            title={`${title}，点击在下方查看`}
            onClick={() => onSelect(round.task_id as string)}
          >
            {title}
          </button>
        ) : (
          <span className="truncate" title={title}>
            {title}
          </span>
        )}
      </p>
      <ul className="mt-1 space-y-0.5 leading-5 text-zinc-800">
        {(report.lines ?? []).map((line, index) => (
          <li key={index}>{line}</li>
        ))}
      </ul>
      {waiting && round.task_id ? (
        <button
          type="button"
          className={`${ghostButton} mt-2 h-7 px-2.5`}
          onClick={() => onSelect(round.task_id as string)}
        >
          去确认读取方式
        </button>
      ) : null}
      {!waiting && report.gaps.length > 0 ? (
        <div className="mt-1.5 flex flex-wrap gap-1">
          {report.gaps.slice(0, 5).map((gap) => (
            <span
              key={`${gap.dataset_code}-${gap.code}`}
              className="rounded-full bg-amber-50 px-2 py-0.5 text-[10px] text-amber-700"
              title={gap.unlocks.length ? `补上后可自动带出 ${gap.unlocks.length} 个字段` : undefined}
            >
              {TIER_LABEL[gap.tier] ?? gap.tier} · {gap.label} ×{gap.count}
            </span>
          ))}
        </div>
      ) : null}
    </li>
  );
}

/** 补齐文件未达到自动补齐条件时，在“核对结构”步骤顶部说明对齐结果。 */
export function SupplementSummary({ detail }: { detail: SupplementDetail }) {
  if (detail.error) {
    return (
      <p className="shrink-0 border-b border-amber-100 bg-amber-50/70 px-5 py-2.5 text-[12px] text-amber-800">
        补齐文件：{detail.error}。请在下方把能识别记录的列（如工号、课程号、名称）对应到字段后再执行。
      </p>
    );
  }
  const rate = Math.round((detail.match_rate ?? 0) * 100);
  return (
    <div className="shrink-0 border-b border-amber-100 bg-amber-50/70 px-5 py-2.5 text-[12px] leading-5 text-amber-900">
      <p>
        这是一份补齐文件：按「{(detail.key_labels ?? []).join("+")}」对上已有记录 {detail.matched}/{detail.rows} 行（{rate}%），
        将补充「{(detail.field_labels ?? []).join("、")}」，只填空字段，不覆盖已有值。
      </p>
      <p className="text-[11px] text-amber-700">
        {detail.conflicts ? `${detail.conflicts} 条与已有值不同，将记为冲突待你确认；` : ""}
        {detail.extra ? `文件中多出 ${detail.extra} 条记录（如 ${(detail.extra_samples ?? []).join("、")}）不会加入；` : ""}
        {detail.ambiguous ? `${detail.ambiguous} 行在文件中重复且取值不同，将跳过；` : ""}
        确认无误后点击下方按钮执行。
      </p>
    </div>
  );
}
