"use client";

import { useEffect, useMemo, useState } from "react";

import { allRowsPagination, createAppColumnHelper, DataTable, useAppTable } from "@/components/data-table";
import { PageIntro, StatusPill } from "@/components/page-bits";
import { useToast } from "@/components/toast";
import { ApiError, api } from "@/lib/api";
import {
  fieldLabel,
  optionLabel,
  STATUS_LABEL,
  type DatasetMeta,
  type RecordDetail,
  type RecordEvent,
  type RecordItem,
  type RecordPage,
} from "@/lib/records";
import { readSession, type SessionUser } from "@/lib/session";

const reviewHelper = createAppColumnHelper<RecordItem>();

export default function ReviewPage() {
  const toast = useToast();
  const [session, setSession] = useState<SessionUser | null>(null);
  const center = session?.role === "admin";
  const [rows, setRows] = useState<RecordItem[]>([]);
  const [error, setError] = useState("");
  const [current, setCurrent] = useState<RecordDetail | null>(null);
  const [meta, setMeta] = useState<DatasetMeta | null>(null);
  const [events, setEvents] = useState<RecordEvent[]>([]);
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);

  async function load() {
    const result = await api<RecordPage>("/api/reviews/todo?page=1&page_size=50");
    setRows(result.items);
  }

  useEffect(() => {
    let cancelled = false;
    queueMicrotask(() => {
      setSession(readSession());
      void load().catch((reason: unknown) => {
        if (!cancelled) setError(reason instanceof ApiError ? reason.message : "加载失败");
      });
    });
    return () => {
      cancelled = true;
    };
  }, []);

  async function open(row: RecordItem) {
    try {
      const [detail, history, form] = await Promise.all([
        api<RecordDetail>(`/api/records/${row.id}`),
        api<RecordEvent[]>(`/api/records/${row.id}/events`),
        api<DatasetMeta>(`/api/datasets/${row.dataset_code}/meta`),
      ]);
      setCurrent(detail);
      setEvents(history);
      setMeta(form);
      setComment("");
    } catch (reason) {
      toast(reason instanceof ApiError ? reason.message : "无法打开记录");
    }
  }

  async function decide(kind: "approve" | "return" | "publish") {
    if (!current) return;
    if ((kind === "return" || kind === "publish") && !comment.trim()) {
      toast(kind === "return" ? "退回必须填写意见" : "跳级发布必须填写说明");
      return;
    }
    setBusy(true);
    try {
      if (kind === "publish") {
        await api(`/api/records/${current.id}/publish`, {
          method: "POST",
          body: JSON.stringify({ comment: comment.trim() }),
        });
      } else {
        await api(`/api/records/${current.id}/review`, {
          method: "POST",
          body: JSON.stringify({ decision: kind, comment: comment.trim() }),
        });
      }
      toast(kind === "return" ? "已退回" : kind === "publish" ? "已跳级发布" : "已通过");
      setCurrent(null);
      await load();
    } catch (reason) {
      toast(reason instanceof ApiError ? reason.message : "审核失败");
    } finally {
      setBusy(false);
    }
  }

  const own = current != null && session != null && current.filler_account === session.account;
  const diff = [...events].reverse().find((event) => event.diff && Object.keys(event.diff).length > 0)?.diff;

  const columns = useMemo(
    () =>
      reviewHelper.columns([
        reviewHelper.accessor("dataset_name", { header: "数据集" }),
        reviewHelper.display({
          id: "filler",
          header: "填报人",
          cell: ({ row }) => row.original.summary.JSXM || row.original.filler_account,
        }),
        reviewHelper.display({
          id: "department",
          header: "部门",
          cell: ({ row }) => row.original.department_name || "—",
        }),
        reviewHelper.accessor("status", {
          header: "环节",
          cell: ({ getValue }) => <StatusPill tone="run">{STATUS_LABEL[getValue()] ?? getValue()}</StatusPill>,
        }),
        reviewHelper.display({
          id: "actions",
          header: "操作",
          meta: { headClassName: "text-right", cellClassName: "text-right" },
          cell: ({ row }) => (
            <button type="button" className="font-medium text-zinc-700" onClick={() => void open(row.original)}>
              审核
            </button>
          ),
        }),
      ]),
    [toast],
  );

  const todoTable = useAppTable({
    data: rows,
    columns,
    initialState: { pagination: allRowsPagination },
  });

  return (
    <div className="mx-auto max-w-400 p-5 xl:p-6">
      <PageIntro
        title={center ? "审核与发布" : "审核中心"}
        description={center ? "信息中心可以逐级通过，也可以填写说明后跳级发布。" : "处理到达本环节的填报记录。退回时必须填写意见。"}
      />
      {error ? <p className="mb-3 text-sm text-rose-600">{error}</p> : null}
      <section className="overflow-hidden rounded-lg border border-zinc-200 bg-white">
        <DataTable table={todoTable} empty="当前没有待审核记录" />
      </section>
      {current && meta ? (
        <section className="mt-4 rounded-lg border border-zinc-200 bg-white p-5">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h2 className="text-sm font-semibold">{current.dataset_name}</h2>
              <p className="mt-1 text-[12px] text-zinc-500">
                {STATUS_LABEL[current.status]} · 填报人 {current.filler_account}
              </p>
            </div>
            <button type="button" className="text-[12px] text-zinc-500" onClick={() => setCurrent(null)}>
              关闭
            </button>
          </div>
          {diff ? (
            <div className="mt-4">
              <p className="text-[12px] font-medium">本次修改</p>
              <ul className="mt-2 space-y-1 text-[12px] text-zinc-600">
                {Object.entries(diff).map(([code, change]) => (
                  <li key={code}>
                    {fieldLabel(meta, code)}：{meta ? optionLabel(meta, code, change.from as string | number | null) : String(change.from ?? "空")} → {meta ? optionLabel(meta, code, change.to as string | number | null) : String(change.to ?? "空")}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
          <div className="mt-4 grid grid-cols-1 gap-2 md:grid-cols-2">
            {meta.fields
              .filter((field) => current.payload[field.code] != null && current.payload[field.code] !== "")
              .map((field) => (
                <p key={field.code} className="text-[12px] text-zinc-600">
                  <span className="text-zinc-400">{field.label}</span> {meta ? optionLabel(meta, field.code, current.payload[field.code]) : String(current.payload[field.code])}
                </p>
              ))}
          </div>
          <label className="mt-4 block text-[12px] text-zinc-500">
            审核意见
            <textarea
              className="mt-1 h-20 w-full rounded-md border border-zinc-200 px-3 py-2 text-[12px] outline-none focus:border-zinc-400"
              value={comment}
              onChange={(event) => setComment(event.target.value)}
            />
          </label>
          <div className="mt-3 flex flex-wrap gap-2">
            {own ? null : (
              <>
                <button type="button" className="h-9 rounded-md bg-zinc-900 px-3 text-xs text-white" disabled={busy} onClick={() => void decide("approve")}>
                  通过
                </button>
                <button type="button" className="h-9 rounded-md border border-zinc-200 px-3 text-xs" disabled={busy} onClick={() => void decide("return")}>
                  退回
                </button>
              </>
            )}
            {center ? (
              <button type="button" className="h-9 rounded-md border border-zinc-900 px-3 text-xs" disabled={busy} onClick={() => void decide("publish")}>
                跳级发布
              </button>
            ) : null}
          </div>
        </section>
      ) : null}
    </div>
  );
}
