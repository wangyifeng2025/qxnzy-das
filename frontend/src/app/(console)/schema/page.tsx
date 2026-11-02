"use client";

import { useState } from "react";

import { fieldClass, PageIntro, Panel, primaryButton, StatusPill } from "@/components/page-bits";
import { useToast } from "@/components/toast";
import { DATA_TABLES, SCHEMA_FIELDS } from "@/lib/tables";

export default function SchemaPage() {
  const toast = useToast();
  const [tableId, setTableId] = useState("staff");
  const [open, setOpen] = useState(false);
  const [extra, setExtra] = useState<{ cn: string; code: string; type: string; required: boolean; source: string; fill: string }[]>([]);
  const table = DATA_TABLES.find((item) => item.id === tableId) ?? DATA_TABLES[1];
  const fields = [...(SCHEMA_FIELDS[table.id] ?? table.sections.flatMap((section) => section.fields).map((field) => ({
    cn: field.label,
    code: field.key,
    type: field.type === "number" ? "INT" : field.type === "date" ? "DATE" : field.type === "textarea" ? "TEXT" : "VARCHAR(64)",
    required: Boolean(field.required),
    source: "手动填报",
    fill: "完整",
  }))), ...extra];

  return (
    <div className="mx-auto max-w-[1600px] p-5 xl:p-6">
      <PageIntro
        title="数据表与字段管理"
        badge="数据标准 v2.4.1"
        description="维护 12 张采集数据表的结构、字段类型、来源渠道与填报状态。"
        actions={
          <button type="button" className={primaryButton} onClick={() => setOpen(true)}>新增字段</button>
        }
      />
      <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
        {[
          ["数据表总数", "12", "全部已发布至数据目录"],
          ["字段总数", String(106 + extra.length), "必填 68 · 选填 38"],
          ["API 来源字段", "64", "来自 6 个业务系统"],
          ["字段完整率", "93.6%", "+0.8%"],
        ].map(([label, value, note]) => (
          <div key={label} className="rounded-lg border border-zinc-200 bg-white p-4 shadow-sm">
            <p className="text-[11px] text-zinc-500">{label}</p>
            <p className="mt-2 text-[26px] leading-none font-semibold">{value}</p>
            <p className="mt-3 text-[10px] text-zinc-400">{note}</p>
          </div>
        ))}
      </div>
      <div className="mt-4 grid gap-4 lg:grid-cols-[280px_minmax(0,1fr)]">
        <Panel title="数据表目录" description="最近发布 2026-10-28">
          <ul className="max-h-[640px] overflow-y-auto">
            {DATA_TABLES.map((item) => (
              <li key={item.id}>
                <button type="button" onClick={() => { setTableId(item.id); setExtra([]); }} className={`w-full px-4 py-3 text-left ${item.id === table.id ? "bg-zinc-100" : "hover:bg-zinc-50"}`}>
                  <p className="text-[12px] font-medium">{item.name}</p>
                  <p className="mt-0.5 text-[10px] text-zinc-400">{item.code} · {item.dept}</p>
                </button>
              </li>
            ))}
          </ul>
        </Panel>
        <Panel title={table.name} description={`${table.code} · ${table.dept} · ${table.collected} 条`}>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[680px] text-left text-[12px]">
              <thead className="bg-zinc-50 text-[11px] text-zinc-500">
                <tr>
                  {["字段名称", "字段编码", "数据类型", "必填", "来源渠道", "填报状态"].map((head) => (
                    <th key={head} className="px-4 py-2.5 font-medium">{head}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {fields.map((field) => (
                  <tr key={field.code} className="border-t border-zinc-100">
                    <td className="px-4 py-2.5 font-medium">{field.cn}</td>
                    <td className="px-4 py-2.5 font-mono text-[11px] text-zinc-500">{field.code}</td>
                    <td className="px-4 py-2.5">{field.type}</td>
                    <td className="px-4 py-2.5">{field.required ? "是" : "否"}</td>
                    <td className="px-4 py-2.5">{field.source}</td>
                    <td className="px-4 py-2.5"><StatusPill tone={field.fill === "完整" ? "ok" : "warn"}>{field.fill}</StatusPill></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
      </div>
      {open ? (
        <div className="fixed inset-0 z-50 grid place-items-center bg-zinc-950/40 p-4">
          <form
            className="w-full max-w-md rounded-xl border border-zinc-200 bg-white p-5 shadow-xl"
            onSubmit={(event) => {
              event.preventDefault();
              const data = new FormData(event.currentTarget);
              const cn = String(data.get("cn") ?? "").trim();
              const code = String(data.get("code") ?? "").trim();
              if (!cn || !code) {
                toast("请填写字段名称和字段编码");
                return;
              }
              setExtra((current) => [...current, { cn, code, type: String(data.get("type")), required: data.get("required") === "on", source: String(data.get("source")), fill: "待补全" }]);
              setOpen(false);
              toast(`已新增字段 ${cn}`);
            }}
          >
            <h2 className="text-sm font-semibold">新增字段</h2>
            <p className="mt-1 text-[11px] text-zinc-500">保存后立即出现在当前数据表的字段目录中。</p>
            <div className="mt-4 grid gap-3">
              <input name="cn" className={fieldClass} placeholder="字段名称" />
              <input name="code" className={`${fieldClass} font-mono`} placeholder="field_code" />
              <select name="type" className={fieldClass}><option>VARCHAR(64)</option><option>TEXT</option><option>INT</option><option>DATE</option></select>
              <select name="source" className={fieldClass}><option>手动填报</option><option>业务系统 API</option><option>AI 文件解析</option></select>
              <label className="flex items-center gap-2 text-[12px]"><input name="required" type="checkbox" />设为必填字段</label>
            </div>
            <div className="mt-4 flex justify-end gap-2">
              <button type="button" className="h-8 rounded-md border border-zinc-200 px-3 text-[12px]" onClick={() => setOpen(false)}>取消</button>
              <button type="submit" className="h-8 rounded-md bg-zinc-900 px-3 text-[12px] text-white">保存字段</button>
            </div>
          </form>
        </div>
      ) : null}
    </div>
  );
}
