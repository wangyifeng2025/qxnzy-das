"use client";

import { Download, Plus } from "lucide-react";
import Link from "next/link";

import { ghostButton, KpiCard, PageIntro, Panel, primaryButton, StatusPill } from "@/components/page-bits";
import { useToast } from "@/components/toast";
import { DATA_TABLES } from "@/lib/tables";

const activities: string[][] = [];

export default function HomePage() {
  const toast = useToast();
  return (
    <div className="mx-auto max-w-400 p-5 xl:p-6">
      <PageIntro
        title="采集总览"
        badge="全校视角"
        description="汇总 12 张业务数据表的采集进度、数据质量与渠道运行状态。"
        actions={
          <>
            <button type="button" className={ghostButton} onClick={() => toast("统计周期已切换为本学期")}>
              本学期
            </button>
            <button type="button" className={ghostButton} onClick={() => toast("采集周报已生成，可在任务中心下载")}>
              <Download className="size-3.5" aria-hidden="true" />
              导出周报
            </button>
            <Link href="/fill" className={primaryButton}>
              <Plus className="size-3.5" aria-hidden="true" />
              进入填报
            </Link>
          </>
        }
      />

      <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
        <KpiCard label="采集记录总量" value="0" note="尚无采集记录" />
        <KpiCard label="本月新增" value="0" note="尚无新增" />
        <KpiCard label="数据完整率" value="—" note="尚无已发布数据" />
        <KpiCard label="待处理事项" value="0" note="暂无待办" />
      </div>

      <div className="mt-4 grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1.4fr)_360px]">
        <Panel title="12 张数据表采集进度" description="统计口径：有效记录数 / 本学期应采集记录数">
          <div className="overflow-x-auto">
            <table className="w-full min-w-160 text-left text-[12px]">
              <thead className="bg-zinc-50 text-[11px] text-zinc-500">
                <tr>
                  <th className="px-4 py-2.5 font-medium">数据表</th>
                  <th className="px-4 py-2.5 font-medium">责任部门</th>
                  <th className="px-4 py-2.5 font-medium">已采集 / 应采集</th>
                  <th className="px-4 py-2.5 font-medium">完成率</th>
                  <th className="px-4 py-2.5 font-medium">状态</th>
                </tr>
              </thead>
              <tbody>
                {DATA_TABLES.map((table) => (
                  <tr key={table.id} className="border-t border-zinc-100">
                    <td className="px-4 py-2.5 font-medium text-zinc-800">{table.name}</td>
                    <td className="px-4 py-2.5 text-zinc-500">{table.dept}</td>
                    <td className="px-4 py-2.5 text-zinc-600">
                      {table.collected} / {table.expected}
                    </td>
                    <td className="px-4 py-2.5">{table.rate}</td>
                    <td className="px-4 py-2.5">
                      <StatusPill tone={table.status === "已达标" ? "ok" : table.status === "需关注" ? "warn" : "run"}>{table.status}</StatusPill>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="border-t border-zinc-100 px-4 py-2.5 text-[10px] text-zinc-400">共 {DATA_TABLES.length} 张数据表 · 尚无采集进度</p>
        </Panel>

        <div className="space-y-4">
          <Panel title="数据质量评分" description="完整、规范、一致、及时四维加权">
            <div className="grid grid-cols-2 gap-3 p-4 text-[12px]">
              <p className="col-span-2 text-[32px] leading-none font-semibold">—</p>
              {[
                ["完整性", "—"],
                ["规范性", "—"],
                ["一致性", "—"],
                ["及时性", "—"],
              ].map(([label, value]) => (
                <div key={label} className="rounded-md bg-zinc-50 px-3 py-2">
                  <p className="text-[10px] text-zinc-400">{label}</p>
                  <p className="mt-1 font-medium">{value}</p>
                </div>
              ))}
            </div>
          </Panel>
          <Panel title="采集渠道贡献" description="本月">
            <ul className="space-y-3 p-4 text-[12px]">
              <li className="flex justify-between"><span>业务系统 API</span><span className="text-zinc-500">0 条</span></li>
              <li className="flex justify-between"><span>教师手动填报</span><span className="text-zinc-500">0 条</span></li>
              <li className="flex justify-between"><span>AI 文件解析</span><span className="text-zinc-500">0 条</span></li>
            </ul>
          </Panel>
        </div>
      </div>

      <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Panel title="近期采集动态" description="手动填报、AI 解析与 API 同步的实时记录">
          <ul className="divide-y divide-zinc-100">
            {activities.length ? null : <li className="px-4 py-6 text-center text-[12px] text-zinc-400">暂无采集记录</li>}
            {activities.map(([title, body, detail, time]) => (
              <li key={title} className="px-4 py-3">
                <div className="flex items-center justify-between gap-3">
                  <p className="text-[12px] font-medium">{title}</p>
                  <span className="text-[10px] text-zinc-400">{time}</span>
                </div>
                <p className="mt-1 text-[12px] text-zinc-600">{body}</p>
                <p className="mt-0.5 text-[10px] text-zinc-400">{detail}</p>
              </li>
            ))}
          </ul>
        </Panel>
        <Panel title="快捷入口" description="常用操作">
          <div className="grid grid-cols-2 gap-2 p-4">
            {[
              ["/fill", "新建填报", "选择数据表"],
              ["/ai-parse", "AI 文件解析", "上传表格后确认入库"],
              ["/api-tasks", "API 采集", "尚未配置任务"],
              ["/open-api", "开放接口", "尚未开放"],
              ["/review", "审核本部门", "暂无待审核"],
              ["/my-fill", "我的填报", "暂无填报记录"],
            ].map(([href, title, text]) => (
              <Link key={href} href={href} className="rounded-md border border-zinc-200 px-3 py-3 hover:bg-zinc-50">
                <p className="text-[12px] font-medium">{title}</p>
                <p className="mt-1 text-[10px] text-zinc-400">{text}</p>
              </Link>
            ))}
          </div>
        </Panel>
      </div>
      <p className="mt-4 pb-1 text-center text-[9px] text-zinc-400">黔西南民族职业技术学院 · 数据采集系统</p>
    </div>
  );
}
