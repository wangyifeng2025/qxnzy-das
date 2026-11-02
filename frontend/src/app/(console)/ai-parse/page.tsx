"use client";

import { useState } from "react";

import { PageIntro, Panel, primaryButton, StatusPill } from "@/components/page-bits";
import { useToast } from "@/components/toast";

const sessions: string[][] = [];

const rows: string[][] = [];

const mappings = [
  ["教师工号", "工号"],
  ["教师姓名", "姓名"],
  ["培训项目", "培训名称"],
  ["培训类别", "培训类型"],
  ["开始时间", "开始日期"],
  ["结束时间", "结束日期"],
  ["培训学时", "学时"],
];

export default function AiParsePage() {
  const toast = useToast();
  const [onlyHints, setOnlyHints] = useState(false);
  const [fileName, setFileName] = useState("");
  const visible = onlyHints ? rows.filter((row) => row[9] === "提示") : rows;

  return (
    <div className="mx-auto max-w-[1600px] p-5 xl:p-6">
      <PageIntro
        title="文件解析入库"
        badge="大模型驱动"
        badgeClass="bg-blue-50 text-blue-700"
        description="上传 Excel、Word 或 PDF，让 AI 自动识别目标数据表、映射字段并生成入库记录。"
        actions={
          <button type="button" className={primaryButton} onClick={() => toast("已新建解析会话")}>
            新建解析
          </button>
        }
      />
      <div className="grid gap-4 xl:grid-cols-[240px_minmax(0,1fr)_300px]">
        <Panel title="解析会话" description="今天 4 个">
          <ul className="divide-y divide-zinc-100">
            {sessions.map(([name, detail, time], index) => (
              <li key={name}>
                <button type="button" className={`w-full px-4 py-3 text-left ${index === 0 ? "bg-zinc-50" : ""}`} onClick={() => toast(`已打开会话：${name}`)}>
                  <p className="text-[12px] font-medium">{name}</p>
                  <p className="mt-1 text-[10px] text-zinc-400">{detail} · {time}</p>
                </button>
              </li>
            ))}
          </ul>
        </Panel>
        <Panel title="AI 数据解析助手" description="在线 · 已加载 12 张数据表 Schema">
          <div className="space-y-3 p-4 text-[12px] leading-6">
            <p className="rounded-md bg-zinc-50 px-3 py-2 text-zinc-600">你好，我是数据解析助手。上传文件并说明采集范围后，我会判断所属数据表、映射字段并校验数据。</p>
            <p className="rounded-md bg-zinc-900 px-3 py-2 text-white">{fileName} · 请分析文件内容，自动匹配到教师培训与交流数据表。</p>
            <p className="rounded-md border border-emerald-100 bg-emerald-50 px-3 py-2 text-emerald-800">解析完成。共识别 24 条培训记录，其中 22 条通过校验、2 条存在提示项。匹配置信度 96.8%。</p>
            <label className="flex h-24 cursor-pointer flex-col items-center justify-center rounded-lg border border-dashed border-zinc-300 text-zinc-500">
              支持 xlsx / docx / pdf · 最大 20MB
              <input
                type="file"
                className="sr-only"
                accept=".xlsx,.xls,.csv,.docx,.pdf"
                onChange={(event) => {
                  const name = event.target.files?.[0]?.name;
                  if (name) setFileName(name);
                  toast(name ? `已接收 ${name}，开始解析` : "未选择文件");
                }}
              />
            </label>
          </div>
        </Panel>
        <Panel title="解析结果" description="待确认">
          <div className="space-y-3 p-4 text-[12px]">
            <div>
              <p className="text-[10px] text-zinc-400">目标数据表</p>
              <p className="mt-1 font-medium">教师培训与交流数据</p>
              <p className="text-[10px] text-zinc-400">T_TEACHER_TRAINING · 教师工作部</p>
            </div>
            <p>匹配置信度 96.8% · 字段映射 7 / 7</p>
            <ul className="space-y-1 text-[11px] text-zinc-600">
              {mappings.map(([from, to]) => (
                <li key={from} className="flex justify-between">
                  <span>{from}</span>
                  <span className="text-zinc-400">{to}</span>
                </li>
              ))}
            </ul>
            <button type="button" className={primaryButton} onClick={() => toast("已确认 24 条记录入库，可在我的填报中跟踪")}>
              确认入库
            </button>
          </div>
        </Panel>
      </div>
      <Panel
        className="mt-4"
        title="解析明细"
        description="可直接核对提示项"
        action={
          <button type="button" className="text-[11px] text-zinc-600" onClick={() => setOnlyHints((value) => !value)}>
            {onlyHints ? "查看全部" : "仅看提示项"}
          </button>
        }
      >
        <div className="overflow-x-auto">
          <table className="w-full min-w-[900px] text-left text-[12px]">
            <thead className="bg-zinc-50 text-[11px] text-zinc-500">
              <tr>
                {["工号", "姓名", "培训名称", "培训类型", "学时", "开始日期", "结束日期", "结业证书编号", "置信度", "状态"].map((head) => (
                  <th key={head} className="px-3 py-2.5 font-medium">{head}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {visible.map((row) => (
                <tr key={row[2]} className="border-t border-zinc-100">
                  {row.slice(0, 9).map((cell) => (
                    <td key={cell} className="px-3 py-2.5">{cell}</td>
                  ))}
                  <td className="px-3 py-2.5">
                    <StatusPill tone={row[9] === "通过" ? "ok" : "warn"}>{row[9]}</StatusPill>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
    </div>
  );
}
