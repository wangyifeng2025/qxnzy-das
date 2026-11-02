"use client";

import { useMemo, useState } from "react";

import { fieldClass, ghostButton, PageIntro, primaryButton } from "@/components/page-bits";
import { useToast } from "@/components/toast";
import { DATA_TABLES, type FormField } from "@/lib/tables";

function initialValues(fields: FormField[]) {
  return Object.fromEntries(fields.map((field) => [field.key, field.value ?? ""]));
}

export default function FillPage() {
  const toast = useToast();
  const [tableId, setTableId] = useState("staff");
  const table = DATA_TABLES.find((item) => item.id === tableId) ?? DATA_TABLES[1];
  const fields = useMemo(() => table.sections.flatMap((section) => section.fields), [table]);
  const [values, setValues] = useState<Record<string, string>>(() => initialValues(DATA_TABLES[1].sections.flatMap((section) => section.fields)));

  function selectTable(id: string) {
    const next = DATA_TABLES.find((item) => item.id === id) ?? DATA_TABLES[0];
    setTableId(id);
    setValues(initialValues(next.sections.flatMap((section) => section.fields)));
  }

  function submit(mode: "draft" | "publish") {
    const missing = fields.filter((field) => field.required && !values[field.key]?.trim());
    if (mode === "publish" && missing.length) {
      toast(`还有 ${missing.length} 个必填项未填写：${missing[0].label}`);
      return;
    }
    toast(mode === "draft" ? "草稿已保存，未提交审核" : "已提交入库，等待本部门管理员审核");
  }

  return (
    <div className="mx-auto grid max-w-[1600px] gap-4 p-5 lg:grid-cols-[280px_minmax(0,1fr)] xl:p-6">
      <aside className="h-fit rounded-lg border border-zinc-200 bg-white p-3 shadow-sm">
        <div className="px-2 py-1.5">
          <p className="text-sm font-semibold">数据表目录</p>
          <p className="mt-0.5 text-[10px] text-zinc-400">12 张 · 单条 4 张 · 多条 8 张</p>
        </div>
        <div className="mt-2 space-y-1">
          {DATA_TABLES.map((item) => {
            const active = item.id === table.id;
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => selectTable(item.id)}
                className={`flex w-full items-start gap-2 rounded-md px-2.5 py-2 text-left ${active ? "bg-zinc-100" : "hover:bg-zinc-50"}`}
              >
                <span className="min-w-0 flex-1">
                  <span className="block text-[12px] font-medium">{item.name}</span>
                  <span className="mt-0.5 block text-[10px] text-zinc-400">
                    {item.dept} · {item.kind === "multi" ? "多条" : "单条"}
                  </span>
                </span>
                <span className="text-[10px] text-zinc-400">{item.rate}</span>
              </button>
            );
          })}
        </div>
      </aside>

      <section className="rounded-lg border border-zinc-200 bg-white shadow-sm">
        <div className="border-b border-zinc-100 px-5 py-4">
          <PageIntro
            title={table.name}
            badge={table.kind === "multi" ? "多条记录" : "单条记录"}
            badgeClass={table.kind === "multi" ? "bg-blue-50 text-blue-700" : "bg-zinc-100 text-zinc-500"}
            description={`${table.code} · 责任部门：${table.dept} · ${table.kind === "single" ? "每人 / 每对象仅一条" : "按条登记，可继续新增多条"}`}
            actions={
              <>
                <button type="button" className={ghostButton} onClick={() => submit("draft")}>
                  保存草稿
                </button>
                <button type="button" className={primaryButton} onClick={() => submit("publish")}>
                  提交入库
                </button>
              </>
            }
          />
        </div>
        <form
          className="space-y-6 p-5"
          onSubmit={(event) => {
            event.preventDefault();
            submit("publish");
          }}
        >
          {table.sections.map((section) => (
            <fieldset key={section.title}>
              <legend className="text-sm font-semibold">{section.title}</legend>
              {section.desc ? <p className="mt-1 text-[11px] text-zinc-400">{section.desc}</p> : null}
              <div className="mt-3 grid gap-3 md:grid-cols-2">
                {section.fields.map((field) => (
                  <label key={field.key} className={field.span === "full" ? "md:col-span-2" : ""}>
                    <span className="mb-1.5 flex items-center gap-1 text-[11px] font-medium text-zinc-700">
                      {field.label}
                      {field.required ? <span className="text-rose-500">*</span> : <span className="font-normal text-zinc-400">选填</span>}
                    </span>
                    {field.type === "textarea" ? (
                      <textarea
                        className={`${fieldClass} h-20 py-2`}
                        value={values[field.key] ?? ""}
                        placeholder={field.placeholder}
                        onChange={(event) => setValues((current) => ({ ...current, [field.key]: event.target.value }))}
                      />
                    ) : field.type === "select" ? (
                      <select
                        className={fieldClass}
                        value={values[field.key] ?? ""}
                        onChange={(event) => setValues((current) => ({ ...current, [field.key]: event.target.value }))}
                      >
                        <option value="">请选择</option>
                        {field.options?.map((option) => (
                          <option key={option}>{option}</option>
                        ))}
                      </select>
                    ) : (
                      <input
                        className={fieldClass}
                        type={field.type}
                        value={values[field.key] ?? ""}
                        placeholder={field.placeholder}
                        onChange={(event) => setValues((current) => ({ ...current, [field.key]: event.target.value }))}
                      />
                    )}
                    {field.hint ? <span className="mt-1 block text-[10px] text-zinc-400">{field.hint}</span> : null}
                  </label>
                ))}
              </div>
            </fieldset>
          ))}
          <p className="text-[11px] text-zinc-400">提交后进入本部门数据管理员审核，审核通过的数据将同步开放给业务系统。</p>
        </form>
      </section>
    </div>
  );
}
