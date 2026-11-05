"use client";

import { useMemo } from "react";

import { allRowsPagination, createAppColumnHelper, DataTable, useAppTable } from "@/components/data-table";
import { KpiCard, PageIntro, Panel, primaryButton, StatusPill } from "@/components/page-bits";
import { useToast } from "@/components/toast";

type ApiTask = {
  name: string;
  source: string;
  target: string;
  schedule: string;
  last_run: string;
  fetched: string;
  status: string;
};

const tasks: ApiTask[] = [];

const taskHelper = createAppColumnHelper<ApiTask>();

const runs: string[][] = [];

export default function ApiTasksPage() {
  const toast = useToast();
  const taskColumns = useMemo(
    () =>
      taskHelper.columns([
        taskHelper.display({
          id: "task",
          header: "任务 / 数据源",
          cell: ({ row }) => (
            <div>
              <p className="font-medium">{row.original.name}</p>
              <p className="text-[10px] text-zinc-400">{row.original.source}</p>
            </div>
          ),
        }),
        taskHelper.accessor("target", { header: "目标数据表" }),
        taskHelper.accessor("schedule", { header: "调度周期" }),
        taskHelper.accessor("last_run", { header: "最近运行" }),
        taskHelper.accessor("fetched", { header: "本次拉取" }),
        taskHelper.accessor("status", {
          header: "状态",
          cell: ({ getValue }) => (
            <StatusPill tone={getValue() === "异常" ? "bad" : getValue() === "执行中" ? "run" : "ok"}>{getValue()}</StatusPill>
          ),
        }),
        taskHelper.display({
          id: "actions",
          header: "操作",
          meta: { cellClassName: "text-right" },
          cell: ({ row }) => (
            <button
              type="button"
              className="text-[11px] font-medium"
              onClick={() => toast(row.original.status === "异常" ? "已重新发起认证并排队重试" : `已触发：${row.original.name}`)}
            >
              {row.original.status === "异常" ? "重试" : "立即运行"}
            </button>
          ),
        }),
      ]),
    [toast],
  );
  const taskTable = useAppTable({
    data: tasks,
    columns: taskColumns,
    initialState: { pagination: allRowsPagination },
  });
  return (
    <div className="mx-auto max-w-400 p-5 xl:p-6">
      <PageIntro
        title="API 采集任务"
        badge="自动采集渠道"
        description="配置业务系统数据源、调度周期与增量规则，将数据自动同步至 12 张标准数据表。"
        actions={
          <button type="button" className={primaryButton} onClick={() => toast("请先选择数据源、目标表和调度周期")}>
            新建采集任务
          </button>
        }
      />
      <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
        <KpiCard label="采集任务" value="0" note="尚未配置" />
        <KpiCard label="今日同步记录" value="0" note="尚无同步" />
        <KpiCard label="同步成功率" value="—" note="尚无运行记录" />
        <KpiCard label="数据源连接" value="0" note="尚未接入" />
      </div>
      <Panel className="mt-4" title="采集任务列表" description="按业务系统和数据表配置自动同步规则">
        <DataTable table={taskTable} empty="尚未配置采集任务" className="min-w-215" />
      </Panel>
      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <Panel title="数据源健康状态" description="最近 5 分钟探测结果">
          <ul className="divide-y divide-zinc-100 text-[12px]">
            {[
              ["教务系统 API", "42 ms", true],
              ["人事系统 API", "38 ms", true],
              ["科研管理系统", "65 ms", true],
              ["学工系统 API", "57 ms", true],
              ["校企合作平台", "认证失败 · 218 ms", false],
            ].map(([name, latency, healthy]) => (
              <li key={String(name)} className="flex items-center justify-between px-4 py-3">
                <span>{name}</span>
                <StatusPill tone={healthy ? "ok" : "bad"}>{latency}</StatusPill>
              </li>
            ))}
          </ul>
        </Panel>
        <Panel title="最近运行记录">
          <ul className="divide-y divide-zinc-100 text-[12px]">
            {runs.map((row) => (
              <li key={row[0] + row[1]} className="px-4 py-3">
                <div className="flex justify-between gap-3">
                  <p className="font-medium">{row[1]}</p>
                  <span className="text-[10px] text-zinc-400">{row[0]}</span>
                </div>
                <p className="mt-1 text-[11px] text-zinc-500">{row[2]} · {row[3]} · {row[4]} · {row[5]}</p>
              </li>
            ))}
          </ul>
        </Panel>
      </div>
    </div>
  );
}
