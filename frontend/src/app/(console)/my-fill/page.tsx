"use client";

import { Plus, Sparkles } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";

import { ghostButton, PageIntro, Panel, primaryButton, StatusPill } from "@/components/page-bits";
import { useToast } from "@/components/toast";
import { readSession } from "@/lib/session";

const tasks: Array<[string, string, string, string, string, "ok" | "warn" | "bad" | "muted"]> = [];

const filters = ["全部", "待办", "审核中", "已完成"] as const;

export default function MyFillPage() {
  const toast = useToast();
  const [filter, setFilter] = useState<(typeof filters)[number]>("全部");
  const session = readSession();
  const intro = session
    ? `${session.name} · ${session.dept} · ${session.post} · 工号 ${session.account}`
    : "个人填报进展";

  const rows = useMemo(() => {
    return tasks.filter((task) => {
      if (filter === "待办") return task[4] === "待补充" || task[4].startsWith("草稿");
      if (filter === "审核中") return task[4].includes("审核");
      if (filter === "已完成") return task[4] === "已入库";
      return true;
    });
  }, [filter]);

  return (
    <div className="mx-auto max-w-[1600px] p-5 xl:p-6">
      <PageIntro
        title="我的填报"
        badge="2025—2026-1"
        description={intro}
        actions={
          <>
            <Link href="/ai-parse" className={ghostButton}>
              <Sparkles className="size-3.5 text-blue-600" aria-hidden="true" />
              上传文件填报
            </Link>
            <Link href="/fill" className={primaryButton}>
              <Plus className="size-3.5" aria-hidden="true" />
              新建填报
            </Link>
          </>
        }
      />

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1fr)_320px]">
        <section className="rounded-lg border border-zinc-200 bg-white p-5 shadow-sm">
          <div className="flex flex-col gap-5 md:flex-row md:items-center">
            <div
              className="relative flex size-[116px] shrink-0 items-center justify-center rounded-full"
              style={{ background: "conic-gradient(#18181b 0 71%, #f4f4f5 71% 100%)" }}
            >
              <div className="flex size-[94px] flex-col items-center justify-center rounded-full bg-white">
                <span className="text-[27px] leading-none font-semibold">
                  71<span className="text-sm font-medium text-zinc-400">%</span>
                </span>
                <span className="mt-1.5 text-[9px] text-zinc-400">本学期进度</span>
              </div>
            </div>
            <div>
              <p className="text-sm font-semibold">个人数据填报进展</p>
              <p className="mt-1 max-w-xl text-[12px] leading-6 text-zinc-500">本学期共 7 项填报任务，已完成 5 项。还需补充 2 项，请在 11 月 15 日 18:00 前完成。</p>
              <div className="mt-3 flex gap-4 text-[12px] text-zinc-600">
                <span>已提交 5</span>
                <span>审核中 1</span>
                <span>待补充 2</span>
              </div>
            </div>
          </div>
        </section>
        <section className="rounded-lg border border-zinc-200 bg-white p-5 shadow-sm">
          <p className="text-sm font-semibold">本期填报倒计时</p>
          <p className="mt-3 text-[28px] leading-none font-semibold">15 天</p>
          <p className="mt-2 text-[12px] text-zinc-500">截止 2025-11-15 18:00</p>
          <Link href="/fill" className={`${primaryButton} mt-4`}>
            立即继续填报
          </Link>
        </section>
      </div>

      <Panel
        className="mt-4"
        title="本学期的填报任务"
        description="按教师角色分配，共 7 张业务数据表"
        action={
          <div className="flex gap-1">
            {filters.map((item) => (
              <button
                key={item}
                type="button"
                onClick={() => setFilter(item)}
                className={`rounded-md px-2 py-1 text-[11px] ${filter === item ? "bg-zinc-900 text-white" : "text-zinc-500 hover:bg-zinc-50"}`}
              >
                {item}
              </button>
            ))}
          </div>
        }
      >
        <div className="overflow-x-auto">
          <table className="w-full min-w-[720px] text-left text-[12px]">
            <thead className="bg-zinc-50 text-[11px] text-zinc-500">
              <tr>
                <th className="px-4 py-2.5 font-medium">数据表 / 填报任务</th>
                <th className="px-4 py-2.5 font-medium">完成情况</th>
                <th className="px-4 py-2.5 font-medium">最近更新</th>
                <th className="px-4 py-2.5 font-medium">状态</th>
                <th className="px-4 py-2.5 font-medium">操作</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row[0]} className="border-t border-zinc-100">
                  <td className="px-4 py-2.5">
                    <p className="font-medium">{row[0]}</p>
                    <p className="mt-0.5 text-[10px] text-zinc-400">{row[1]}</p>
                  </td>
                  <td className="px-4 py-2.5">{row[2]}</td>
                  <td className="px-4 py-2.5 text-zinc-500">{row[3]}</td>
                  <td className="px-4 py-2.5">
                    <StatusPill tone={row[5]}>{row[4]}</StatusPill>
                  </td>
                  <td className="px-4 py-2.5">
                    <Link href="/fill" className="text-[11px] font-medium text-zinc-700 hover:underline">
                      查看记录
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <Panel title="待办提醒" description="2 项">
          <ul className="divide-y divide-zinc-100 text-[12px]">
            <li className="px-4 py-3">
              <p className="font-medium">论文著作缺少 ISSN / ISBN</p>
              <p className="mt-1 text-zinc-500">《乡村旅游高质量发展路径研究》需要补充发表刊号。</p>
            </li>
            <li className="px-4 py-3">
              <p className="font-medium">企业实践证明材料未上传</p>
              <p className="mt-1 text-zinc-500">请上传企业出具的实践鉴定表或考核证明。</p>
            </li>
          </ul>
        </Panel>
        <Panel title="最近草稿" action={<button type="button" className="text-[11px] text-zinc-500" onClick={() => toast("已打开全部草稿")}>全部</button>}>
          <ul className="divide-y divide-zinc-100 text-[12px]">
            <li className="px-4 py-3">
              <p className="font-medium">教师企业实践锻炼 · 60%</p>
              <p className="mt-1 text-[11px] text-zinc-400">10-28 17:06 · 共 2 条 · 最近：万峰林国际会议中心</p>
            </li>
            <li className="px-4 py-3">
              <p className="font-medium">教师论文著作 · 68%</p>
              <p className="mt-1 text-[11px] text-zinc-400">10-29 10:12 · 共 3 条 · 最近：乡村旅游高质量发展路径研究</p>
            </li>
          </ul>
          <div className="border-t border-zinc-100 px-4 py-3 text-[12px]">
            <p>你有 3 份培训证书可以合并上传，AI 可自动识别并生成培训记录。</p>
            <Link href="/ai-parse" className="mt-2 inline-block text-[11px] font-medium text-blue-600">
              去解析文件
            </Link>
          </div>
        </Panel>
      </div>
    </div>
  );
}
