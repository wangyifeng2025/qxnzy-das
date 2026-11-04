"use client";

import { Plus, Search, X } from "lucide-react";
import { useEffect, useState } from "react";

import { FormCombobox } from "@/components/form-combobox";
import { fieldClass } from "@/components/page-bits";
import { useToast } from "@/components/toast";
import { ApiError, api } from "@/lib/api";

type Option = { value: string; label: string };

type StaffFormMeta = {
  departments: string[];
  dicts: Record<string, Option[]>;
  title_ranks: string[];
  scope: string;
  account: string;
  name: string;
  department_name: string | null;
  can_submit: boolean;
};

type StaffListItem = {
  ZJSJWYXBS: string;
  JGH: string;
  JSXM: string;
  XB: string;
  YXBMCMC: string;
  RYLB: string;
  XL: string;
  SFZJH: string;
  SJCJSJ: string;
};

type StaffRecord = StaffListItem & Record<string, string | number | null | string[]>;

type PageResult = { items: StaffListItem[]; total: number; page: number; page_size: number };

type FieldKind = "text" | "select" | "date" | "month" | "number" | "decimal";

type FieldDef = {
  key: string;
  label: string;
  kind: FieldKind;
  options?: string;
  required?: boolean;
  maxLength?: number;
  when?: string;
};

const SECTIONS: Array<{ title: string; hint?: string; fields: FieldDef[] }> = [
  {
    title: "身份信息",
    hint: "姓名、性别、出生日期须与身份证一致。性别按字典代码保存。",
    fields: [
      { key: "JGH", label: "教工号", kind: "text", required: true, maxLength: 20 },
      { key: "JSXM", label: "姓名", kind: "text", required: true, maxLength: 36 },
      { key: "XB", label: "性别", kind: "select", options: "D55", required: true },
      { key: "SFZJH", label: "身份证号", kind: "text", required: true, maxLength: 18 },
      { key: "CSRQ", label: "出生日期", kind: "date", required: true },
      { key: "ZZMM", label: "政治面貌", kind: "select", options: "D21", required: true },
      { key: "MZ", label: "民族", kind: "select", options: "D22", required: true },
    ],
  },
  {
    title: "学历与学位",
    fields: [
      { key: "XL", label: "学历", kind: "select", options: "D23", required: true },
      { key: "XW", label: "学位", kind: "select", options: "D24", required: true },
      { key: "BYXXGJDQ", label: "最高学历毕业学校所在国家（地区）", kind: "select", options: "D63", required: true },
      { key: "BYXXMC", label: "最高学历毕业学校名称", kind: "text", required: true, maxLength: 100 },
    ],
  },
  {
    title: "岗位",
    fields: [
      { key: "YXBMCMC", label: "院系部名称", kind: "select", options: "departments", required: true },
      { key: "RYLB", label: "人员类别", kind: "select", options: "D19", required: true },
      { key: "SRZW", label: "所任职务", kind: "text", required: true, maxLength: 60 },
      { key: "ZYLY", label: "专业领域", kind: "select", options: "D25", required: true },
      { key: "ZYTC", label: "专业特长", kind: "text", required: true, maxLength: 100 },
    ],
  },
  {
    title: "高校教师资格证书",
    hint: "选择“是”后须填写发证单位和获取年月。",
    fields: [
      { key: "SFYGXJSZGZS", label: "是否拥有高校教师资格证书", kind: "select", options: "D28", required: true },
      { key: "GXJSZGZFZDW", label: "发证单位", kind: "text", maxLength: 60, when: "SFYGXJSZGZS" },
      { key: "GXJSZGZHQRQ", label: "获取日期", kind: "month", when: "SFYGXJSZGZS" },
    ],
  },
  {
    title: "专业技术职务",
    hint: "没有职务可留空；填写其中一项时，等级、名称、发证单位和获取日期都要填。",
    fields: [
      { key: "ZYJSZWDJ", label: "专业技术职务等级", kind: "select", options: "titles" },
      { key: "ZYJSZWMC", label: "专业技术职务名称", kind: "text", maxLength: 60 },
      { key: "ZYJSZWFZDW", label: "发证单位", kind: "text", maxLength: 60 },
      { key: "ZYJSZWHQRQ", label: "获取日期", kind: "month" },
    ],
  },
  {
    title: "职业资格证书",
    hint: "没有证书选“无”。等级为高级、中级、初级或无等级时，名称、发证单位和获取日期必填。",
    fields: [
      { key: "ZYGGZSDJ", label: "职业资格证书等级", kind: "select", options: "D27" },
      { key: "ZYGGZSMC", label: "职业资格证书名称", kind: "text", maxLength: 100 },
      { key: "ZYGGZSFZDW", label: "发证单位", kind: "text", maxLength: 60 },
      { key: "ZYGGZSHQRQ", label: "获取日期", kind: "month" },
    ],
  },
  {
    title: "教学身份",
    fields: [
      { key: "SFZYJS", label: "是否专业教师", kind: "select", options: "D28", required: true },
      { key: "XZSSZYMC", label: "行政所属专业名称", kind: "text", maxLength: 60, when: "SFZYJS" },
      { key: "XZSSZYDM", label: "行政所属专业代码", kind: "text", maxLength: 6, when: "SFZYJS" },
      { key: "XZSSZYCC", label: "行政所属专业层次", kind: "select", options: "D01", when: "SFZYJS" },
      { key: "XZSSZYDL", label: "行政所属专业大类", kind: "text", maxLength: 40, when: "SFZYJS" },
      { key: "SFGGKJS", label: "是否公共课教师", kind: "select", options: "D28", required: true },
      { key: "SRGGKC", label: "所任公共课程", kind: "select", options: "D14", when: "SFGGKJS" },
      { key: "SFSZXJS", label: "是否为双师型教师", kind: "select", options: "D29", required: true },
      { key: "JXMS", label: "教学名师", kind: "select", options: "D30", required: true },
    ],
  },
  {
    title: "思政、辅导员与心理健康",
    fields: [
      { key: "SFZZSZKJS", label: "是否专职思政课教师", kind: "select", options: "D28", required: true },
      { key: "SFJZSZKJS", label: "是否兼职思政课教师", kind: "select", options: "D28", required: true },
      { key: "SFZZFDY", label: "是否专职辅导员", kind: "select", options: "D28", required: true },
      { key: "SFJZFDY", label: "是否兼职辅导员", kind: "select", options: "D28", required: true },
      { key: "SFZZXLJKJS", label: "是否专职心理健康教师", kind: "select", options: "D28", required: true },
      { key: "SFJZXLJKJS", label: "是否兼职心理健康教师", kind: "select", options: "D28", required: true },
    ],
  },
  {
    title: "带头人与企业经历",
    hint: "不是专业带头人或专业（群）负责人时，年限填 0。企业工作年限保留 1 位小数，没有则填 0。",
    fields: [
      { key: "SFZYDTR", label: "是否专业带头人", kind: "select", options: "D31", required: true },
      { key: "ZYDTNX", label: "担任专业带头人年限", kind: "number", required: true },
      { key: "SFZYQFZR", label: "是否专业（群）负责人", kind: "select", options: "D32", required: true },
      { key: "ZYQFZRNX", label: "担任专业（群）负责人年限", kind: "number", required: true },
      { key: "CZHYQYGZNX", label: "曾在行业企业工作年限", kind: "decimal", required: true },
    ],
  },
];

const OPTIONAL = new Set([
  "GXJSZGZFZDW",
  "GXJSZGZHQRQ",
  "ZYJSZWDJ",
  "ZYJSZWMC",
  "ZYJSZWFZDW",
  "ZYJSZWHQRQ",
  "ZYGGZSDJ",
  "ZYGGZSMC",
  "ZYGGZSFZDW",
  "ZYGGZSHQRQ",
  "XZSSZYMC",
  "XZSSZYDM",
  "XZSSZYCC",
  "XZSSZYDL",
  "SRGGKC",
]);

function labelOf(meta: StaffFormMeta, code: string, value: string) {
  return meta.dicts[code]?.find((item) => item.value === value)?.label ?? value;
}

function visible(field: FieldDef, draft: Record<string, string>) {
  if (!field.when) return true;
  return draft[field.when] === "1";
}

function blankDraft(meta: StaffFormMeta): Record<string, string> {
  const department =
    meta.department_name && meta.departments.includes(meta.department_name)
      ? meta.department_name
      : (meta.departments[0] ?? "");
  const draft: Record<string, string> = {
    YXBMCMC: department,
    JGH: meta.scope === "self" ? meta.account : "",
    JSXM: meta.scope === "self" ? meta.name : "",
    SFYGXJSZGZS: "0",
    SFZYJS: "0",
    SFGGKJS: "0",
    SFSZXJS: "否",
    JXMS: "否",
    SFZZSZKJS: "0",
    SFJZSZKJS: "0",
    SFZZFDY: "0",
    SFJZFDY: "0",
    SFZZXLJKJS: "0",
    SFJZXLJKJS: "0",
    SFZYDTR: "否",
    ZYDTNX: "0",
    SFZYQFZR: "否",
    ZYQFZRNX: "0",
    CZHYQYGZNX: "0.0",
  };
  return draft;
}

function draftFromRecord(record: StaffRecord): Record<string, string> {
  const draft: Record<string, string> = {};
  for (const section of SECTIONS) {
    for (const field of section.fields) {
      const value = record[field.key];
      draft[field.key] = value == null ? "" : String(value);
    }
  }
  return draft;
}

function toPayload(draft: Record<string, string>) {
  const body: Record<string, string | number | null> = {};
  for (const section of SECTIONS) {
    for (const field of section.fields) {
      const text = (draft[field.key] ?? "").trim();
      if (field.kind === "number") body[field.key] = text === "" ? null : Number(text);
      else if (field.kind === "decimal") body[field.key] = text === "" ? "0.0" : text;
      else if (OPTIONAL.has(field.key)) body[field.key] = text || null;
      else body[field.key] = text;
    }
  }
  if (draft.SFZYDTR === "否") body.ZYDTNX = 0;
  if (draft.SFZYQFZR === "否") body.ZYQFZRNX = 0;
  if (draft.SFYGXJSZGZS !== "1") {
    body.GXJSZGZFZDW = null;
    body.GXJSZGZHQRQ = null;
  }
  if (draft.SFZYJS !== "1") {
    body.XZSSZYMC = null;
    body.XZSSZYDM = null;
    body.XZSSZYCC = null;
    body.XZSSZYDL = null;
  }
  if (draft.SFGGKJS !== "1") body.SRGGKC = null;
  return body;
}

export function StaffFill() {
  const toast = useToast();
  const [meta, setMeta] = useState<StaffFormMeta | null>(null);
  const [page, setPage] = useState<PageResult | null>(null);
  const [keyword, setKeyword] = useState("");
  const [query, setQuery] = useState("");
  const [currentPage, setCurrentPage] = useState(1);
  const [loadError, setLoadError] = useState("");
  const [editing, setEditing] = useState<string | "new" | null>(null);
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);

  async function loadList(nextPage: number, nextQuery: string) {
    const params = new URLSearchParams({ page: String(nextPage), page_size: "8" });
    if (nextQuery.trim()) params.set("keyword", nextQuery.trim());
    const result = await api<PageResult>(`/api/staff?${params.toString()}`);
    setPage(result);
    setCurrentPage(nextPage);
  }

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const nextMeta = await api<StaffFormMeta>("/api/staff/form-meta");
        const result = await api<PageResult>("/api/staff?page=1&page_size=8");
        if (cancelled) return;
        setMeta(nextMeta);
        setPage(result);
      } catch (error) {
        if (!cancelled) setLoadError(error instanceof ApiError ? error.message : "加载失败");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  function optionsFor(field: FieldDef): Option[] {
    if (!meta) return [];
    if (field.options === "departments") return meta.departments.map((name) => ({ value: name, label: name }));
    if (field.options === "titles") return meta.title_ranks.map((name) => ({ value: name, label: name }));
    return field.options ? (meta.dicts[field.options] ?? []) : [];
  }

  async function openRecord(id: string | "new") {
    if (!meta) return;
    if (id === "new") {
      setDraft(blankDraft(meta));
      setEditing("new");
      return;
    }
    try {
      const record = await api<StaffRecord>(`/api/staff/${id}`);
      setDraft(draftFromRecord(record));
      setEditing(id);
    } catch (error) {
      toast(error instanceof ApiError ? error.message : "无法打开记录");
    }
  }

  async function save() {
    if (!meta?.can_submit || !editing) return;
    setSaving(true);
    try {
      const body = JSON.stringify(toPayload(draft));
      const saved =
        editing === "new"
          ? await api<StaffRecord>("/api/staff", { method: "POST", body })
          : await api<StaffRecord>(`/api/staff/${editing}`, { method: "PUT", body });
      const warnings = Array.isArray(saved.warnings) ? saved.warnings.join("；") : "";
      toast(warnings ? `已保存。${warnings}` : "已保存教职工基本信息");
      setEditing(null);
      await loadList(currentPage, query);
    } catch (error) {
      toast(error instanceof ApiError ? error.message : "保存失败");
    } finally {
      setSaving(false);
    }
  }

  async function remove(id: string, name: string) {
    if (!window.confirm(`删除 ${name} 的教职工基本信息？`)) return;
    try {
      await api(`/api/staff/${id}`, { method: "DELETE" });
      toast("已删除");
      await loadList(1, query);
    } catch (error) {
      toast(error instanceof ApiError ? error.message : "删除失败");
    }
  }

  if (loadError) {
    return <div className="p-6 text-sm text-rose-600">{loadError}</div>;
  }
  if (!meta || !page) {
    return <div className="p-6 text-sm text-zinc-400">正在加载教职工基本信息</div>;
  }

  const lockedAccount = meta.scope === "self";
  const lockedDepartment = meta.departments.length <= 1;
  const pages = Math.max(1, Math.ceil(page.total / page.page_size));
  const readonly = !meta.can_submit;

  return (
    <div className="mx-auto max-w-400 p-5 xl:p-6">
      <section className="overflow-hidden rounded-lg border border-zinc-200 bg-white shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-3 border-b border-zinc-100 px-5 py-4">
          <div>
            <h1 className="text-base font-semibold tracking-tight">教职工基本信息表</h1>
            <p className="mt-1 text-[11px] text-zinc-400">ODS_JZGJBSJ · 责任部门：人事处 · 业务主键：教工号</p>
            <p className="mt-0.5 text-[10px] text-zinc-400">
              {meta.scope === "all" ? "全校数据" : meta.scope === "department" ? "本部门数据" : "本人数据"}
              {meta.department_name ? ` · ${meta.department_name}` : ""}
            </p>
          </div>
          {meta.can_submit && !(meta.scope === "self" && page.total > 0) ? (
            <button type="button" className="flex h-9 items-center gap-1.5 rounded-md bg-zinc-900 px-3.5 text-[11px] font-medium text-white" onClick={() => void openRecord("new")}>
              <Plus className="size-3.5" aria-hidden="true" />
              新增一条
            </button>
          ) : null}
        </div>
        <form
          className="flex flex-wrap items-center gap-2 border-b border-zinc-100 px-5 py-2.5"
          onSubmit={(event) => {
            event.preventDefault();
            setQuery(keyword);
            void loadList(1, keyword).catch((error: unknown) => {
              toast(error instanceof ApiError ? error.message : "查询失败");
            });
          }}
        >
          <label className="flex h-8 w-56 items-center gap-2 rounded-md border border-zinc-200 bg-zinc-50/60 px-2.5">
            <Search className="size-3 text-zinc-400" aria-hidden="true" />
            <input value={keyword} onChange={(event) => setKeyword(event.target.value)} className="w-full bg-transparent text-[10px] outline-none" placeholder="搜索教工号或姓名" />
          </label>
          <button type="submit" className="h-8 rounded-md border border-zinc-200 px-3 text-[10px] text-zinc-600">查询</button>
          <span className="text-[10px] text-zinc-400 xl:ml-auto">共 {page.total} 条 · 列表中的身份证号已脱敏</span>
        </form>
        <div className="p-5">
          {page.items.length === 0 ? (
            <div className="rounded-lg border border-dashed border-zinc-300 bg-zinc-50/40 px-6 py-14 text-center">
              <p className="text-[12px] font-medium text-zinc-700">暂无教职工基本信息</p>
              <p className="mt-1 text-[10px] text-zinc-400">按数据标准逐人维护，每人一条，教工号和身份证号都不能重复。</p>
            </div>
          ) : (
            <div className="overflow-hidden rounded-lg border border-zinc-200">
              <table className="w-full min-w-215 text-[11px]">
                <thead className="bg-zinc-50 text-[10px] text-zinc-500">
                  <tr>
                    {["教工号", "姓名", "性别", "院系部名称", "人员类别", "学历", "身份证号", "采集时间", "操作"].map((head) => (
                      <th key={head} className="px-3 py-2.5 text-left font-medium whitespace-nowrap">{head}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {page.items.map((row) => (
                    <tr key={row.ZJSJWYXBS} className="border-t border-zinc-100">
                      <td className="px-3 py-3 font-medium">{row.JGH}</td>
                      <td className="px-3 py-3">{row.JSXM}</td>
                      <td className="px-3 py-3">{labelOf(meta, "D55", row.XB)}</td>
                      <td className="px-3 py-3">{row.YXBMCMC}</td>
                      <td className="px-3 py-3">{row.RYLB}</td>
                      <td className="px-3 py-3">{row.XL}</td>
                      <td className="px-3 py-3 font-mono text-[10px]">{row.SFZJH}</td>
                      <td className="px-3 py-3 text-zinc-400">{row.SJCJSJ}</td>
                      <td className="px-3 py-3 text-right whitespace-nowrap">
                        <button type="button" className="text-[10px] font-medium text-zinc-600" onClick={() => void openRecord(row.ZJSJWYXBS)}>
                          {readonly ? "查看" : "编辑"}
                        </button>
                        {readonly ? null : (
                          <>
                            <span className="mx-1.5 text-zinc-300">|</span>
                            <button type="button" className="text-[10px] font-medium text-rose-500" onClick={() => void remove(row.ZJSJWYXBS, row.JSXM)}>删除</button>
                          </>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <div className="flex items-center justify-between border-t border-zinc-100 px-3 py-2.5">
                <p className="text-[10px] text-zinc-400">第 {currentPage} / {pages} 页</p>
                <div className="flex gap-1">
                  <button type="button" className="h-6 rounded border border-zinc-200 px-2 text-[10px] disabled:text-zinc-300" disabled={currentPage <= 1} onClick={() => void loadList(currentPage - 1, query)}>上一页</button>
                  <button type="button" className="h-6 rounded border border-zinc-200 px-2 text-[10px] disabled:text-zinc-300" disabled={currentPage >= pages} onClick={() => void loadList(currentPage + 1, query)}>下一页</button>
                </div>
              </div>
            </div>
          )}
        </div>
      </section>

      {editing ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <button type="button" aria-label="关闭" className="absolute inset-0 bg-zinc-950/40" onClick={() => setEditing(null)} />
          <div className="relative flex max-h-[88vh] w-full max-w-230 flex-col overflow-hidden rounded-xl border border-zinc-200 bg-white shadow-2xl">
            <div className="flex items-start justify-between border-b border-zinc-100 px-5 py-4">
              <div>
                <h3 className="text-sm font-semibold">{editing === "new" ? "新增教职工基本信息" : readonly ? "查看教职工基本信息" : "编辑教职工基本信息"}</h3>
                <p className="mt-1 text-[10px] text-zinc-500">学校代码和采集时间由系统写入，不在表单中填写。</p>
              </div>
              <button type="button" aria-label="关闭对话框" className="flex size-7 items-center justify-center rounded-md text-zinc-400 hover:bg-zinc-100" onClick={() => setEditing(null)}>
                <X className="size-4" />
              </button>
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
              {SECTIONS.map((section, index) => (
                <div key={section.title} className={index > 0 ? "mt-5 border-t border-zinc-100 pt-5" : ""}>
                  <h4 className="text-[12px] font-semibold">{section.title}</h4>
                  {section.hint ? <p className="mt-0.5 text-[9px] text-zinc-400">{section.hint}</p> : null}
                  <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2">
                    {section.fields.filter((field) => visible(field, draft)).map((field) => {
                      const disabled =
                        readonly ||
                        (field.key === "JGH" && lockedAccount) ||
                        (field.key === "YXBMCMC" && lockedDepartment) ||
                        (field.key === "ZYDTNX" && draft.SFZYDTR === "否") ||
                        (field.key === "ZYQFZRNX" && draft.SFZYQFZR === "否");
                      const choices = optionsFor(field);
                      return (
                        <label key={field.key} className={field.key === "BYXXMC" || field.key === "ZYTC" ? "md:col-span-2" : ""}>
                          <span className="mb-1.5 flex items-center gap-1 text-[11px] font-medium text-zinc-700">
                            {field.label}
                            {field.required ? <span className="text-rose-500">*</span> : null}
                          </span>
                          {field.kind === "select" ? (
                            <FormCombobox
                              disabled={disabled}
                              placeholder={field.options === "titles" ? "无专业技术职务" : "请选择"}
                              value={draft[field.key] ?? ""}
                              options={[
                                { value: "", label: field.options === "titles" ? "无专业技术职务" : "请选择" },
                                ...choices,
                              ]}
                              onValueChange={(value) => {
                                setDraft((current) => {
                                  const next = { ...current, [field.key]: value };
                                  if (field.key === "SFZYDTR" && value === "否") next.ZYDTNX = "0";
                                  if (field.key === "SFZYQFZR" && value === "否") next.ZYQFZRNX = "0";
                                  return next;
                                });
                              }}
                            />
                          ) : (
                            <input
                              disabled={disabled}
                              type={field.kind === "date" ? "date" : field.kind === "month" ? "month" : field.kind === "number" || field.kind === "decimal" ? "number" : "text"}
                              step={field.kind === "decimal" ? "0.1" : field.kind === "number" ? "1" : undefined}
                              min={field.kind === "number" || field.kind === "decimal" ? "0" : undefined}
                              maxLength={field.maxLength}
                              className={fieldClass}
                              value={draft[field.key] ?? ""}
                              onChange={(event) => setDraft((current) => ({ ...current, [field.key]: event.target.value }))}
                            />
                          )}
                        </label>
                      );
                    })}
                  </div>
                </div>
              ))}
            </div>
            <div className="flex items-center justify-end gap-2 border-t border-zinc-100 bg-zinc-50/60 px-5 py-3">
              <p className="mr-auto text-[10px] text-zinc-400">学历与学位不匹配时仍可保存，系统会给出提示。</p>
              <button type="button" className="h-8 rounded-md border border-zinc-200 bg-white px-3 text-[11px]" onClick={() => setEditing(null)}>关闭</button>
              {readonly ? null : (
                <button type="button" disabled={saving} className="h-8 rounded-md bg-zinc-900 px-3 text-[11px] font-medium text-white disabled:opacity-50" onClick={() => void save()}>
                  {saving ? "保存中" : "保存"}
                </button>
              )}
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
