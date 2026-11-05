"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import { allRowsPagination, createAppColumnHelper, DataTable, useAppTable } from "@/components/data-table";
import { PageIntro, StatusPill } from "@/components/page-bits";
import { useToast } from "@/components/toast";
import { ApiError, api } from "@/lib/api";
import {
  canWithdraw,
  STATUS_LABEL,
  type RecordEvent,
  type RecordItem,
  type RecordPage,
} from "@/lib/records";
import { readSession, type SessionUser } from "@/lib/session";

const filters = [
  { id: "all", label: "全部" },
  { id: "draft", label: "草稿" },
  { id: "pending", label: "审核中" },
  { id: "returned", label: "已退回" },
  { id: "published", label: "已发布" },
] as const;

function tone(status: string): "ok" | "run" | "warn" | "muted" {
  if (status === "published") return "ok";
  if (status === "returned") return "warn";
  if (status.startsWith("pending")) return "run";
  return "muted";
}

const recordHelper = createAppColumnHelper<RecordItem>();

export default function MyFillPage() {
  const toast = useToast();
  const [session, setSession] = useState<SessionUser | null>(null);
  const [filter, setFilter] = useState<(typeof filters)[number]["id"]>("all");
  const [rows, setRows] = useState<RecordItem[]>([]);
  const [comments, setComments] = useState<Record<string, string>>({});
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    const result = await api<RecordPage>("/api/my/records?page=1&page_size=50");
    const nextComments: Record<string, string> = {};
    await Promise.all(
      result.items
        .filter((item) => item.status === "returned")
        .map(async (item) => {
          const events = await api<RecordEvent[]>(`/api/records/${item.id}/events`);
          const comment = [...events].reverse().find((event) => event.action === "return")?.comment;
          if (comment) nextComments[item.id] = comment;
        }),
    );
    setRows(result.items);
    setComments(nextComments);
  }, []);

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
  }, [load]);

  const visible = useMemo(
    () =>
      rows.filter((row) => {
        if (filter === "draft") return row.status === "draft";
        if (filter === "pending") return row.status.startsWith("pending");
        if (filter === "returned") return row.status === "returned";
        if (filter === "published") return row.status === "published";
        return true;
      }),
    [rows, filter],
  );

  const act = useCallback(
    async (id: string, action: "submit" | "withdraw") => {
      try {
        await api(`/api/records/${id}/${action}`, { method: "POST" });
        toast(action === "submit" ? "已重新提交" : "已撤回");
        await load();
      } catch (reason) {
        toast(reason instanceof ApiError ? reason.message : "操作失败");
      }
    },
    [load, toast],
  );

  const columns = useMemo(
    () =>
      recordHelper.columns([
        recordHelper.accessor("dataset_name", { header: "数据集" }),
        recordHelper.accessor("business_key", { header: "主键" }),
        recordHelper.accessor("completeness", {
          header: "完整度",
          meta: { cellClassName: "w-36" },
          cell: ({ row }) => {
            const value = Math.max(0, Math.min(100, row.original.completeness));
            const gap = row.original.errors.length;
            return (
              <div className="flex items-center gap-2" title={gap > 0 ? `缺 ${gap} 项必填：${row.original.errors.join("、")}` : "必填项已齐全"}>
                <div className="h-1.5 w-16 overflow-hidden rounded-full bg-zinc-100">
                  <div
                    className={`h-full rounded-full ${value >= 100 ? "bg-emerald-500" : value >= 70 ? "bg-amber-500" : "bg-rose-500"}`}
                    style={{ width: `${value}%` }}
                  />
                </div>
                <span className="tabular-nums text-[11px] text-zinc-500">{value}%</span>
                {gap > 0 ? <span className="text-[10px] text-rose-500">缺{gap}</span> : null}
              </div>
            );
          },
        }),
        recordHelper.accessor("status", {
          header: "状态",
          cell: ({ getValue }) => (
            <StatusPill tone={tone(getValue())}>{STATUS_LABEL[getValue()] ?? getValue()}</StatusPill>
          ),
        }),
        recordHelper.display({
          id: "comment",
          header: "退回意见",
          meta: { cellClassName: "text-zinc-500 whitespace-normal" },
          cell: ({ row }) => comments[row.original.id] || "—",
        }),
        recordHelper.display({
          id: "actions",
          header: "操作",
          meta: { headClassName: "text-right", cellClassName: "text-right" },
          cell: ({ row }) => (
            <div className="whitespace-nowrap">
              <Link href={`/fill?table=${row.original.dataset_code}&record=${row.original.id}`} className="font-medium text-zinc-700">
                {row.original.status === "draft" || row.original.status === "returned" ? "继续填写" : "查看"}
              </Link>
              {row.original.status === "draft" || row.original.status === "returned" ? (
                <button type="button" className="ml-3 font-medium" onClick={() => void act(row.original.id, "submit")}>
                  提交
                </button>
              ) : null}
              {session && canWithdraw(row.original, session.account) ? (
                <button type="button" className="ml-3 font-medium" onClick={() => void act(row.original.id, "withdraw")}>
                  撤回
                </button>
              ) : null}
            </div>
          ),
        }),
      ]),
    [act, comments, session],
  );

  const recordTable = useAppTable({
    data: visible,
    columns,
    initialState: { pagination: allRowsPagination },
  });

  return (
    <div className="mx-auto max-w-400 p-5 xl:p-6">
      <PageIntro
        title="我的填报"
        description={session ? `${session.name} · ${session.dept} · 工号 ${session.account}` : "个人填报进展"}
      />
      <div className="mb-4 flex flex-wrap gap-1">
        {filters.map((item) => (
          <button
            key={item.id}
            type="button"
            onClick={() => setFilter(item.id)}
            className={`rounded-md px-3 py-1.5 text-[12px] ${filter === item.id ? "bg-zinc-900 text-white" : "bg-white text-zinc-600 ring-1 ring-zinc-200"}`}
          >
            {item.label}
          </button>
        ))}
      </div>
      {error ? <p className="text-sm text-rose-600">{error}</p> : null}
      <section className="overflow-hidden rounded-lg border border-zinc-200 bg-white">
        <DataTable table={recordTable} empty="没有符合条件的记录" />
      </section>
    </div>
  );
}
