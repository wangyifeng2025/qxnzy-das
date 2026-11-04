"use client";

import { useMemo, useState } from "react";

import { KpiCard, PageIntro, Panel, StatusPill } from "@/components/page-bits";
import { useToast } from "@/components/toast";

const issues: string[][] = [];

const logs: string[][] = [];

export default function QualityPage() {
  const toast = useToast();
  const [level, setLevel] = useState("全部级别");
  const visible = useMemo(() => logs.filter((row) => level === "全部级别" || row[1] === level), [level]);

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
        <div className="overflow-x-auto">
          <table className="w-full min-w-190 text-left text-[12px]">
            <thead className="bg-zinc-50 text-[11px] text-zinc-500">
              <tr>
                {["级别", "数据表 / 字段", "异常说明", "影响记录", "最近发生", "状态", "操作"].map((head) => (
                  <th key={head} className="px-4 py-2.5 font-medium">{head}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {issues.map((row) => (
                <tr key={row[1]} className="border-t border-zinc-100">
                  <td className="px-4 py-2.5"><StatusPill tone={row[0] === "严重" ? "bad" : row[0] === "警告" ? "warn" : "muted"}>{row[0]}</StatusPill></td>
                  <td className="px-4 py-2.5 font-medium">{row[1]}</td>
                  <td className="px-4 py-2.5">{row[2]}</td>
                  <td className="px-4 py-2.5">{row[3]}</td>
                  <td className="px-4 py-2.5 text-zinc-500">{row[4]}</td>
                  <td className="px-4 py-2.5">{row[5]}</td>
                  <td className="px-4 py-2.5">
                    <button type="button" className="text-[11px] font-medium" onClick={() => toast(`已记录处置：${row[1]}`)}>处理</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
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
