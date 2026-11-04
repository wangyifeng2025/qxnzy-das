"use client";

import { KpiCard, PageIntro, Panel, primaryButton, StatusPill } from "@/components/page-bits";
import { useToast } from "@/components/toast";

const tasks: string[][] = [];

const runs: string[][] = [];

export default function ApiTasksPage() {
  const toast = useToast();
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
        <div className="overflow-x-auto">
          <table className="w-full min-w-215 text-left text-[12px]">
            <thead className="bg-zinc-50 text-[11px] text-zinc-500">
              <tr>
                {["任务 / 数据源", "目标数据表", "调度周期", "最近运行", "本次拉取", "状态", "操作"].map((head) => (
                  <th key={head} className="px-4 py-2.5 font-medium">{head}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {tasks.map((row) => (
                <tr key={row[0]} className="border-t border-zinc-100">
                  <td className="px-4 py-2.5">
                    <p className="font-medium">{row[0]}</p>
                    <p className="text-[10px] text-zinc-400">{row[1]}</p>
                  </td>
                  <td className="px-4 py-2.5">{row[2]}</td>
                  <td className="px-4 py-2.5">{row[3]}</td>
                  <td className="px-4 py-2.5">{row[4]}</td>
                  <td className="px-4 py-2.5">{row[5]}</td>
                  <td className="px-4 py-2.5">
                    <StatusPill tone={row[6] === "异常" ? "bad" : row[6] === "执行中" ? "run" : "ok"}>{row[6]}</StatusPill>
                  </td>
                  <td className="px-4 py-2.5">
                    <button type="button" className="text-[11px] font-medium" onClick={() => toast(row[6] === "异常" ? "已重新发起认证并排队重试" : `已触发：${row[0]}`)}>
                      {row[6] === "异常" ? "重试" : "立即运行"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
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
