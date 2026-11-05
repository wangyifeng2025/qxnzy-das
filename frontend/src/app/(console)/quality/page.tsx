"use client";

import { useMemo, useState } from "react";

import { allRowsPagination, createAppColumnHelper, DataTable, useAppTable } from "@/components/data-table";
import { KpiCard, PageIntro, Panel, StatusPill } from "@/components/page-bits";
import { useToast } from "@/components/toast";

type Issue = {
  level: string;
  target: string;
  description: string;
  affected: string;
  occurred_at: string;
  status: string;
};

const issues: Issue[] = [];

const issueHelper = createAppColumnHelper<Issue>();

const logs: string[][] = [];

export default function QualityPage() {
  const toast = useToast();
  const [level, setLevel] = useState("全部级别");
  const visible = useMemo(() => logs.filter((row) => level === "全部级别" || row[1] === level), [level]);
  const issueColumns = useMemo(
    () =>
      issueHelper.columns([
        issueHelper.accessor("level", {
          header: "级别",
          cell: ({ getValue }) => (
            <StatusPill tone={getValue() === "严重" ? "bad" : getValue() === "警告" ? "warn" : "muted"}>{getValue()}</StatusPill>
          ),
        }),
        issueHelper.accessor("target", { header: "数据表 / 字段", meta: { cellClassName: "font-medium" } }),
        issueHelper.accessor("description", { header: "异常说明", meta: { cellClassName: "whitespace-normal" } }),
        issueHelper.accessor("affected", { header: "影响记录" }),
        issueHelper.accessor("occurred_at", { header: "最近发生", meta: { cellClassName: "text-zinc-500" } }),
        issueHelper.accessor("status", { header: "状态" }),
        issueHelper.display({
          id: "actions",
          header: "操作",
          meta: { headClassName: "text-right", cellClassName: "text-right" },
          cell: ({ row }) => (
            <button type="button" className="text-[11px] font-medium" onClick={() => toast(`已记录处置：${row.original.target}`)}>
              处理
            </button>
          ),
        }),
      ]),
    [toast],
  );
  const issueTable = useAppTable({
    data: issues,
    columns: issueColumns,
    initialState: { pagination: allRowsPagination },
  });

  return (
    <div className="mx-auto max-w-400 p-5 xl:p-6">
      <PageIntro
        title="采集日志与数据质量"
        badge="暂无异常"
        badgeClass="bg-rose-50 text-rose-700"
        description="追踪数据采集全链路，定位异常与校验失败记录，持续提升数据完整性和一致性。"
        actions={
          <button type="button" className="inline-flex h-9 items-center rounded-md border border-zinc-200 bg-white px-3 text-xs" onClick={() => toast("已导出最近 180 天采集日志")}>
            导出日志
          </button>
        }
      />
      <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
        <KpiCard label="今日采集日志" value="0" note="尚无日志" />
        <KpiCard label="异常事件" value="0" note="暂无异常" />
        <KpiCard label="校验失败记录" value="0" note="尚无校验记录" />
        <KpiCard label="综合质量评分" value="—" note="尚无已发布数据" />
      </div>
      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <Panel title="近 7 日数据质量趋势" description="尚无质量评分">
          <p className="px-4 py-10 text-center text-[12px] text-zinc-400">暂无质量趋势</p>
        </Panel>
        <Panel title="待处理异常分布" description="尚无自动修复记录">
          <ul className="grid grid-cols-2 gap-3 p-4 text-[12px]">
            {[["完整性问题", "0"], ["规范性问题", "0"], ["一致性问题", "0"], ["及时性问题", "0"]].map(([label, count]) => (
              <li key={label} className="rounded-md bg-zinc-50 px-3 py-3">
                <p className="text-[10px] text-zinc-400">{label}</p>
                <p className="mt-1 text-lg font-semibold">{count}</p>
              </li>
            ))}
          </ul>
        </Panel>
      </div>
      <Panel className="mt-4" title="异常与校验失败明细">
        <DataTable table={issueTable} empty="暂无异常与校验失败记录" className="min-w-190" />
      </Panel>
      <Panel className="mt-4" title="采集日志" action={
        <select className="h-8 rounded-md border border-zinc-200 px-2 text-[12px]" value={level} onChange={(event) => setLevel(event.target.value)}>
          {["全部级别", "INFO", "WARN", "ERROR"].map((item) => <option key={item}>{item}</option>)}
        </select>
      }>
        <ul className="divide-y divide-zinc-100 text-[12px]">
          {visible.map((row) => (
            <li key={row[0] + row[3]} className="px-4 py-3">
              <div className="flex flex-wrap items-center gap-2">
                <StatusPill tone={row[1] === "ERROR" ? "bad" : row[1] === "WARN" ? "warn" : "ok"}>{row[1]}</StatusPill>
                <span className="font-medium">{row[2]}</span>
                <span className="text-zinc-400">{row[0]}</span>
              </div>
              <p className="mt-1 text-zinc-600">{row[4]}</p>
              <p className="mt-0.5 text-[10px] text-zinc-400">{row[3]} · {row[5]}</p>
            </li>
          ))}
        </ul>
      </Panel>
    </div>
  );
}
