"use client";

import { Download, Upload } from "lucide-react";
import { useMemo, useState } from "react";

import { ghostButton, KpiCard, PageIntro, Panel, primaryButton, StatusPill } from "@/components/page-bits";
import { useToast } from "@/components/toast";

const queue: { id: string; table: string; teacher: string; dept: string; time: string; count: string; check: string; rows: string[] }[] = [];

const history: string[][] = [];

const tabs = ["审核队列", "批量导入", "审核记录"] as const;

export default function ReviewPage() {
  const toast = useToast();
  const [tab, setTab] = useState<(typeof tabs)[number]>("审核队列");
  const [tableFilter, setTableFilter] = useState("全部");
  const [openId, setOpenId] = useState<string | null>(null);
  const tables = ["全部", ...new Set(queue.map((item) => item.table))];
  const visible = useMemo(
    () => queue.filter((item) => tableFilter === "全部" || item.table === tableFilter),
    [tableFilter],
  );

  return (
    <div className="mx-auto max-w-400 p-5 xl:p-6">
      <PageIntro
        title="审核与批量导入"
        badge="部门管理员"
        badgeClass="bg-sky-50 text-sky-700"
        description="审核本部门教师提交的数据，代填或批量导入本部门业务数据，跟踪填报完成情况。"
        actions={
          <>
            <button type="button" className={ghostButton} onClick={() => toast("已导出本系部填报进度表")}>
              <Download className="size-3.5" aria-hidden="true" />
              导出进度
            </button>
            <button type="button" className={primaryButton} onClick={() => setTab("批量导入")}>
              <Upload className="size-3.5" aria-hidden="true" />
              批量导入
            </button>
          </>
        }
      />

      <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
        <KpiCard label="待审核提交" value="18" note="2 条已超时 · 平均处理 3.2 小时" />
        <KpiCard label="今日已审核" value="7" note="通过 6 · 驳回 1" />
        <KpiCard label="本月审核通过率" value="94.2%" note="共处理 86 条教师提交" />
        <KpiCard label="本系部填报率" value="87.6%" note="46 / 52 人" />
      </div>

      <div className="mt-4 flex gap-1">
        {tabs.map((item) => (
          <button
            key={item}
            type="button"
            onClick={() => setTab(item)}
            className={`rounded-md px-3 py-1.5 text-[12px] ${tab === item ? "bg-zinc-900 text-white" : "bg-white text-zinc-600 ring-1 ring-zinc-200"}`}
          >
            {item}
          </button>
        ))}
      </div>

      {tab === "审核队列" ? (
        <Panel className="mt-4" title="审核队列" description={`当前显示 ${visible.length} 条`}>
          <div className="flex flex-wrap gap-2 border-b border-zinc-100 px-4 py-3">
            <label className="text-[11px] text-zinc-500">
              数据表
              <select className="ml-2 h-8 rounded-md border border-zinc-200 px-2 text-[12px]" value={tableFilter} onChange={(event) => setTableFilter(event.target.value)}>
                {tables.map((item) => (
                  <option key={item}>{item}</option>
                ))}
              </select>
            </label>
            <button type="button" className="text-[11px] text-zinc-500" onClick={() => setTableFilter("全部")}>
              重置
            </button>
            <button type="button" className="ml-auto text-[11px] font-medium text-zinc-700" onClick={() => toast("已批量通过当前筛选中的待审核记录")}>
              批量通过
            </button>
          </div>
          <ul className="divide-y divide-zinc-100">
            {visible.map((item) => (
              <li key={item.id} className="px-4 py-3">
                <div className="flex flex-wrap items-center gap-3">
                  <div className="min-w-0 flex-1">
                    <p className="text-[13px] font-medium">{item.table}</p>
                    <p className="mt-0.5 text-[11px] text-zinc-400">
                      {item.teacher} · {item.dept} · {item.time} · {item.count}
                    </p>
                  </div>
                  <StatusPill tone={item.check === "校验通过" ? "ok" : "warn"}>{item.check}</StatusPill>
                  <button type="button" className="text-[12px] font-medium text-zinc-800" onClick={() => setOpenId(openId === item.id ? null : item.id)}>
                    逐条审核
                  </button>
                </div>
                {openId === item.id ? (
                  <ul className="mt-3 space-y-2 rounded-md bg-zinc-50 p-3 text-[12px]">
                    {item.rows.map((row) => (
                      <li key={row} className="flex items-center justify-between gap-3">
                        <span>{row}</span>
                        <span className="flex gap-2">
                          <button type="button" className="text-emerald-700" onClick={() => toast(`已通过：${row}`)}>
                            通过
                          </button>
                          <button type="button" className="text-rose-700" onClick={() => toast(`已退回：${row}`)}>
                            退回
                          </button>
                        </span>
                      </li>
                    ))}
                  </ul>
                ) : null}
              </li>
            ))}
          </ul>
        </Panel>
      ) : null}

      {tab === "批量导入" ? (
        <div className="mt-4 grid gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
          <Panel title="批量导入本系部数据" description="支持 Excel / CSV 模板，导入前将自动校验字段与主数据关联">
            <div className="p-4">
              <label className="flex h-36 cursor-pointer flex-col items-center justify-center rounded-lg border border-dashed border-zinc-300 bg-zinc-50 text-center">
                <Upload className="size-5 text-zinc-400" aria-hidden="true" />
                <span className="mt-2 text-[12px]">拖拽文件到此处，或点击选择文件</span>
                <span className="mt-1 text-[10px] text-zinc-400">支持 .xlsx / .csv，单个文件不超过 20MB</span>
                <input
                  type="file"
                  accept=".xlsx,.xls,.csv"
                  className="sr-only"
                  onChange={(event) => toast(`已识别文件：${event.target.files?.[0]?.name ?? "未选择"}`)}
                />
              </label>
              <button type="button" className={`${primaryButton} mt-4`} onClick={() => toast("导入完成：成功 18 条，失败 0 条")}>
                开始导入
              </button>
            </div>
          </Panel>
          <Panel title="导入规则">
            <ol className="space-y-3 p-4 text-[12px] leading-6 text-zinc-600">
              <li>1. 根据表头自动推荐 12 张表中的目标表。</li>
              <li>2. 检查必填字段、格式、值域及教师工号。</li>
              <li>3. 成功记录入库，异常行生成修正清单。</li>
            </ol>
          </Panel>
        </div>
      ) : null}

      {tab === "审核记录" ? (
        <Panel className="mt-4" title="审核记录" description="近 30 天本系部审核操作留痕">
          <div className="overflow-x-auto">
            <table className="w-full min-w-190 text-left text-[12px]">
              <thead className="bg-zinc-50 text-[11px] text-zinc-500">
                <tr>
                  {["审核单号", "提交教师", "数据表", "审核结果", "审核意见", "审核人", "审核时间"].map((head) => (
                    <th key={head} className="px-4 py-2.5 font-medium">{head}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {history.map((row) => (
                  <tr key={row[0]} className="border-t border-zinc-100">
                    {row.map((cell) => (
                      <td key={cell} className="px-4 py-2.5 text-zinc-700">{cell}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
      ) : null}
    </div>
  );
}
