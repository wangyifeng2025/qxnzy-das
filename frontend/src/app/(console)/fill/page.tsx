"use client";

import {
  Award,
  BookMarked,
  BookOpen,
  CalendarClock,
  CircleCheckBig,
  Clock3,
  Factory,
  FilePenLine,
  Filter,
  FlaskConical,
  GraduationCap,
  Handshake,
  Library,
  Lightbulb,
  ListChecks,
  Plus,
  Presentation,
  RotateCcw,
  Search,
  ShieldAlert,
  Sparkles,
  Users,
  X,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";

import { FormCombobox } from "@/components/form-combobox";
import { fieldClass } from "@/components/page-bits";
import { StaffFill } from "@/components/staff-fill";
import { useToast } from "@/components/toast";
import { canFillTable } from "@/lib/navigation";
import { readSession, type Role } from "@/lib/session";
import { DATA_TABLES, type FormField } from "@/lib/tables";

type RecordStatus = "draft" | "submitted" | "approved";

type FillRecord = {
  id: string;
  values: Record<string, string>;
  status: RecordStatus;
  updatedAt: string;
};

const LIST_COLUMNS: Record<string, Array<{ key: string; label: string }>> = {
  staff: [
    { key: "staffNo", label: "工号" },
    { key: "name", label: "姓名" },
    { key: "gender", label: "性别" },
    { key: "department", label: "所属系部" },
    { key: "postType", label: "岗位类别" },
    { key: "title", label: "职称" },
  ],
  training: [
    { key: "trainingName", label: "培训名称" },
    { key: "organizer", label: "举办单位" },
    { key: "trainingType", label: "培训类别" },
    { key: "startDate", label: "开始时间" },
    { key: "endDate", label: "结束时间" },
    { key: "hours", label: "学时" },
  ],
  award: [
    { key: "awardName", label: "获奖名称" },
    { key: "awardLevel", label: "奖项级别" },
    { key: "issuer", label: "颁奖单位" },
    { key: "awardDate", label: "获奖时间" },
    { key: "awardType", label: "奖项类别" },
  ],
  paper: [
    { key: "achievementName", label: "成果名称" },
    { key: "achievementType", label: "类型" },
    { key: "publisher", label: "刊物 / 出版社" },
    { key: "publishDate", label: "发表时间" },
    { key: "authorRank", label: "作者排名" },
  ],
  vertical: [
    { key: "projectName", label: "项目名称" },
    { key: "projectNo", label: "项目编号" },
    { key: "projectLevel", label: "项目级别" },
    { key: "funding", label: "经费（万元）" },
    { key: "projectStatus", label: "项目状态" },
  ],
  horizontal: [
    { key: "projectName", label: "课题名称" },
    { key: "contractNo", label: "合同编号" },
    { key: "client", label: "委托单位" },
    { key: "contractAmount", label: "合同经费（万元）" },
    { key: "projectStatus", label: "结题状态" },
  ],
  practice: [
    { key: "enterprise", label: "实践单位" },
    { key: "position", label: "实践岗位" },
    { key: "practiceType", label: "实践类型" },
    { key: "startDate", label: "起始时间" },
    { key: "endDate", label: "结束时间" },
    { key: "days", label: "累计天数" },
  ],
  ip: [
    { key: "ipName", label: "成果名称" },
    { key: "ipType", label: "类型" },
    { key: "authNo", label: "授权号" },
    { key: "grantDate", label: "授权日期" },
    { key: "legalStatus", label: "法律状态" },
  ],
  course: [
    { key: "courseCode", label: "课程代码" },
    { key: "courseName", label: "课程名称" },
    { key: "department", label: "开课系部" },
    { key: "major", label: "适用专业" },
    { key: "credits", label: "学分" },
    { key: "totalHours", label: "总学时" },
  ],
  teaching: [
    { key: "courseName", label: "课程名称" },
    { key: "courseCode", label: "课程代码" },
    { key: "className", label: "授课班级" },
    { key: "semester", label: "学期" },
    { key: "weeklyHours", label: "周学时" },
    { key: "location", label: "授课地点" },
  ],
  student: [
    { key: "studentNo", label: "学号" },
    { key: "name", label: "姓名" },
    { key: "gender", label: "性别" },
    { key: "major", label: "专业" },
    { key: "className", label: "班级" },
    { key: "status", label: "学籍状态" },
  ],
  major: [
    { key: "majorCode", label: "专业代码" },
    { key: "majorName", label: "专业名称" },
    { key: "department", label: "所属系部" },
    { key: "duration", label: "学制" },
    { key: "enrollment", label: "招生状态" },
  ],
};

const TABLE_ICON: Record<string, LucideIcon> = {
  staff: Users,
  training: Presentation,
  award: Award,
  paper: Library,
  vertical: FlaskConical,
  horizontal: Handshake,
  practice: Factory,
  ip: Lightbulb,
  course: BookMarked,
  teaching: CalendarClock,
  student: GraduationCap,
  major: BookOpen,
};

const STATUS_LABEL: Record<RecordStatus, string> = {
  draft: "草稿",
  submitted: "审核中",
  approved: "已通过",
};

const PAGE_SIZE = 8;

function stamp() {
  const now = new Date();
  const part = (value: number) => String(value).padStart(2, "0");
  return `${now.getFullYear()}-${part(now.getMonth() + 1)}-${part(now.getDate())} ${part(now.getHours())}:${part(now.getMinutes())}`;
}

function emptyHint(tableId: string, dept: string) {
  if (tableId === "major") return "专业设置数据按专业逐条维护，由教务处与各系部专业带头人登记。";
  if (tableId === "course") return "课程基本数据按课程逐条维护，由教务处与开课系部共同登记。";
  if (tableId === "student") return "在校生基本信息按学生逐条维护，由学生工作处与各系部辅导员登记。";
  if (tableId === "staff") return "教职工基本信息每人一条，由人事处主数据同步，教师可补充本人信息。";
  return `该类数据可以逐条登记。请新增记录后提交审核，责任部门为${dept}。`;
}

function blankValues(fields: FormField[]) {
  return Object.fromEntries(fields.map((field) => [field.key, ""]));
}

function FillPageContent() {
  const toast = useToast();
  const searchParams = useSearchParams();
  const requested = searchParams.get("table") || "staff";
  const table = DATA_TABLES.find((item) => item.id === requested);
  const [role, setRole] = useState<Role | null>(null);
  const [records, setRecords] = useState<Record<string, FillRecord[]>>({});
  const [keyword, setKeyword] = useState("");
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(1);
  const [editing, setEditing] = useState<FillRecord | "new" | null>(null);
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [filterTable, setFilterTable] = useState(requested);

  if (filterTable !== requested) {
    setFilterTable(requested);
    setKeyword("");
    setStatus("");
    setPage(1);
    setEditing(null);
  }

  useEffect(() => {
    queueMicrotask(() => setRole(readSession()?.role ?? "teacher"));
  }, []);

  const fields = useMemo(() => table?.sections.flatMap((section) => section.fields) ?? [], [table]);
  const columns = table ? (LIST_COLUMNS[table.id] ?? fields.slice(0, 6).map((field) => ({ key: field.key, label: field.label }))) : [];
  const rows = table ? (records[table.id] ?? []) : [];
  const allowed = table && role ? canFillTable(role, table.id) : Boolean(table);
  const Icon = table ? (TABLE_ICON[table.id] ?? FilePenLine) : FilePenLine;
  const teacherStaffLocked = role === "teacher" && table?.id === "staff" && rows.length > 0;
  const canCreate = allowed && !teacherStaffLocked;
  const filtered = rows.filter((row) => {
    if (status && row.status !== status) return false;
    const text = Object.values(row.values).join(" ").toLowerCase();
    return !keyword.trim() || text.includes(keyword.trim().toLowerCase());
  });
  const pages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const currentPage = Math.min(page, pages);
  const pageRows = filtered.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE);
  const counts = {
    total: rows.length,
    draft: rows.filter((row) => row.status === "draft").length,
    submitted: rows.filter((row) => row.status === "submitted").length,
    approved: rows.filter((row) => row.status === "approved").length,
  };

  function openForm(record?: FillRecord) {
    setEditing(record ?? "new");
    setDraft(record ? { ...record.values } : blankValues(fields));
  }

  function save(nextStatus: RecordStatus) {
    if (!table) return;
    const missing = fields.filter((field) => field.required && !draft[field.key]?.trim());
    if (nextStatus === "submitted" && missing.length) {
      toast(`还有 ${missing.length} 个必填项未填写：${missing[0].label}`);
      return;
    }
    const now = stamp();
    setRecords((current) => {
      const list = current[table.id] ?? [];
      if (editing && editing !== "new") {
        return {
          ...current,
          [table.id]: list.map((row) => (row.id === editing.id ? { ...row, values: draft, status: nextStatus, updatedAt: now } : row)),
        };
      }
      return {
        ...current,
        [table.id]: [{ id: crypto.randomUUID(), values: draft, status: nextStatus, updatedAt: now }, ...list],
      };
    });
    setEditing(null);
    toast(nextStatus === "draft" ? "草稿已保存" : "已提交审核");
  }

  function remove(id: string) {
    if (!table) return;
    setRecords((current) => ({ ...current, [table.id]: (current[table.id] ?? []).filter((row) => row.id !== id) }));
    toast("已删除这条记录");
  }

  function submitRow(id: string) {
    if (!table) return;
    setRecords((current) => ({
      ...current,
      [table.id]: (current[table.id] ?? []).map((row) => (row.id === id ? { ...row, status: "submitted", updatedAt: stamp() } : row)),
    }));
    toast("已提交审核");
  }

  if (!table || (role && !allowed)) {
    return (
      <div className="mx-auto max-w-[620px] p-5 xl:p-6">
        <div className="mt-8 rounded-xl border border-zinc-200 bg-white p-8 text-center shadow-sm">
          <div className="mx-auto flex size-12 items-center justify-center rounded-full bg-amber-50 text-amber-600">
            <ShieldAlert className="size-6" aria-hidden="true" />
          </div>
          <h2 className="mt-4 text-base font-semibold text-zinc-900">{table ? "该数据表不在你的填报范围内" : "未找到该数据表"}</h2>
          <p className="mx-auto mt-2 max-w-[440px] text-[12px] leading-relaxed text-zinc-500">
            {table ? `${table.name}由部门管理员或信息中心维护，当前身份不能填报。` : "左侧菜单中的数据表才可以打开。"}
          </p>
          <div className="mt-5 flex flex-wrap items-center justify-center gap-2">
            <Link href="/fill?table=staff" className="flex h-9 items-center gap-1.5 rounded-md bg-zinc-900 px-4 text-xs font-medium text-white">
              返回可填数据表
            </Link>
            <Link href="/my-fill" className="flex h-9 items-center gap-1.5 rounded-md border border-zinc-200 bg-white px-4 text-xs font-medium text-zinc-700">
              前往我的填报
            </Link>
          </div>
        </div>
      </div>
    );
  }

  const scopeText = role === "teacher" ? "本人数据" : role === "staff" ? "本部门数据" : "全校数据";
  const readonly = editing !== null && editing !== "new" && editing.status === "approved";

  return (
    <div className="mx-auto max-w-[1600px] p-5 xl:p-6">
      <section className="overflow-hidden rounded-lg border border-zinc-200 bg-white shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-3 border-b border-zinc-100 px-5 py-4">
          <div className="flex min-w-0 items-start gap-3">
            <div className="flex size-10 shrink-0 items-center justify-center rounded-lg border border-zinc-200 bg-zinc-50 text-zinc-700">
              <Icon className="size-[19px]" aria-hidden="true" />
            </div>
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <h1 className="text-base font-semibold tracking-tight text-zinc-900">{table.name}</h1>
                <span className="rounded-full border border-zinc-200 px-2 py-0.5 text-[9px] font-medium text-zinc-500">
                  必填项 {fields.filter((field) => field.required).length} 项
                </span>
                <span className="rounded-full border border-zinc-200 bg-zinc-50 px-2 py-0.5 text-[9px] font-medium text-zinc-600">
                  {table.kind === "multi" ? "多条记录 · 一名教师可登记多条" : "单条记录 · 每人 / 每对象仅一条"}
                </span>
                <span className="rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-[9px] font-medium text-emerald-700">{scopeText}</span>
              </div>
              <p className="mt-1 text-[11px] text-zinc-400">{table.code} · 责任部门：{table.dept} · 数据来源：手动填报 / 业务系统 API</p>
              <p className="mt-0.5 text-[10px] text-zinc-400">数据范围：{scopeText}</p>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {role !== "teacher" ? (
              <Link href={`/ai-parse?table=${table.id}`} className="flex h-9 items-center gap-1.5 rounded-md border border-blue-200 bg-blue-50 px-3 text-[11px] font-medium text-blue-700">
                <Sparkles className="size-3.5" aria-hidden="true" />
                批量导入
              </Link>
            ) : null}
            {canCreate ? (
              <button type="button" className="flex h-9 items-center gap-1.5 rounded-md bg-zinc-900 px-3.5 text-[11px] font-medium text-white" onClick={() => openForm()}>
                <Plus className="size-3.5" aria-hidden="true" />
                {table.kind === "multi" ? "新增一条" : "新增 / 填报"}
              </button>
            ) : null}
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2 border-b border-zinc-100 bg-zinc-50/50 px-5 py-3">
          {[
            ["总条数", counts.total, ListChecks, "text-zinc-900"],
            ["草稿", counts.draft, FilePenLine, "text-zinc-800"],
            ["待审", counts.submitted, Clock3, "text-amber-700"],
            ["已通过", counts.approved, CircleCheckBig, "text-emerald-700"],
          ].map(([label, value, StatIcon, tone]) => {
            const IconStat = StatIcon as LucideIcon;
            return (
              <div key={String(label)} className="flex min-w-[88px] flex-1 items-center gap-2 rounded-md border border-zinc-200 bg-white px-3 py-2">
                <IconStat className="size-4 text-zinc-400" aria-hidden="true" />
                <div>
                  <p className="text-[9px] text-zinc-400">{label as string}</p>
                  <p className={`text-[14px] leading-tight font-semibold ${tone as string}`}>{value as number}</p>
                </div>
              </div>
            );
          })}
        </div>

        <div className="flex flex-wrap items-center gap-2 border-b border-zinc-100 px-5 py-2.5">
          <label className="flex h-8 w-52 items-center gap-2 rounded-md border border-zinc-200 bg-zinc-50/60 px-2.5">
            <Search className="size-3 text-zinc-400" aria-hidden="true" />
            <input
              value={keyword}
              onChange={(event) => {
                setKeyword(event.target.value);
                setPage(1);
              }}
              className="w-full bg-transparent text-[10px] outline-none placeholder:text-zinc-400"
              placeholder="搜索关键字"
            />
          </label>
          <label className="flex h-8 items-center gap-1.5 rounded-md border border-zinc-200 bg-white px-2">
            <Filter className="size-3 text-zinc-400" aria-hidden="true" />
            <select
              value={status}
              onChange={(event) => {
                setStatus(event.target.value);
                setPage(1);
              }}
              className="bg-transparent text-[10px] text-zinc-700 outline-none"
            >
              <option value="">全部状态</option>
              <option value="draft">草稿</option>
              <option value="submitted">审核中</option>
              <option value="approved">已通过</option>
            </select>
          </label>
          <button
            type="button"
            className="flex h-8 items-center gap-1 rounded-md px-2 text-[10px] text-zinc-500 hover:bg-zinc-100"
            onClick={() => {
              setKeyword("");
              setStatus("");
              setPage(1);
            }}
          >
            <RotateCcw className="size-3" aria-hidden="true" />
            重置
          </button>
          <span className="text-[10px] text-zinc-400 xl:ml-auto">{scopeText} · 共 {filtered.length} 条</span>
        </div>

        <div className="p-5">
          {rows.length === 0 ? (
            <div className="flex flex-col items-center justify-center rounded-lg border border-dashed border-zinc-300 bg-zinc-50/40 px-6 py-14 text-center">
              <span className="flex size-12 items-center justify-center rounded-full bg-white text-zinc-400 ring-1 ring-zinc-200">
                <Icon className="size-5" aria-hidden="true" />
              </span>
              <p className="mt-3 text-[12px] font-medium text-zinc-700">暂无「{table.name.replace(/数据(表)?$/, "")}」记录</p>
              <p className="mt-1 max-w-[320px] text-[10px] leading-relaxed text-zinc-400">{emptyHint(table.id, table.dept)}</p>
              {canCreate ? (
                <button type="button" className="mt-4 flex h-8 items-center gap-1.5 rounded-md bg-zinc-900 px-3.5 text-[11px] font-medium text-white" onClick={() => openForm()}>
                  <Plus className="size-3" aria-hidden="true" />
                  {table.kind === "multi" ? "新增第一条记录" : "新增一条数据"}
                </button>
              ) : null}
            </div>
          ) : filtered.length === 0 ? (
            <div className="flex flex-col items-center justify-center rounded-lg border border-dashed border-zinc-300 bg-zinc-50/40 px-6 py-12 text-center">
              <p className="text-[12px] font-medium text-zinc-700">当前筛选条件下没有匹配记录</p>
              <button
                type="button"
                className="mt-4 flex h-8 items-center gap-1.5 rounded-md border border-zinc-200 bg-white px-3.5 text-[11px] font-medium text-zinc-700"
                onClick={() => {
                  setKeyword("");
                  setStatus("");
                  setPage(1);
                }}
              >
                清空筛选
              </button>
            </div>
          ) : (
            <div className="overflow-hidden rounded-lg border border-zinc-200">
              <div className="max-h-[560px] overflow-auto [scrollbar-width:none]">
                <table className="w-full min-w-[860px] text-[11px]">
                  <thead className="sticky top-0 z-10 bg-zinc-50 text-[10px] text-zinc-500">
                    <tr>
                      <th className="w-10 px-3 py-2.5 text-left font-medium">#</th>
                      {columns.map((column) => (
                        <th key={column.key} className="px-3 py-2.5 text-left font-medium whitespace-nowrap">{column.label}</th>
                      ))}
                      <th className="px-3 py-2.5 text-left font-medium whitespace-nowrap">审核状态</th>
                      <th className="px-3 py-2.5 text-left font-medium whitespace-nowrap">最近更新</th>
                      <th className="px-3 py-2.5 text-right font-medium whitespace-nowrap">操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    {pageRows.map((row, index) => (
                      <tr key={row.id} className="border-b border-zinc-100 align-top hover:bg-zinc-50/60">
                        <td className="px-3 py-3">
                          <span className="flex size-5 items-center justify-center rounded bg-zinc-100 text-[9px] font-medium text-zinc-500">
                            {(currentPage - 1) * PAGE_SIZE + index + 1}
                          </span>
                        </td>
                        {columns.map((column, columnIndex) => (
                          <td key={column.key} className={`px-3 py-3 ${columnIndex === 0 ? "max-w-[260px] font-medium text-zinc-800" : "whitespace-nowrap text-zinc-600"}`}>
                            {row.values[column.key] || "—"}
                          </td>
                        ))}
                        <td className="px-3 py-3 whitespace-nowrap">
                          <span className={`rounded-full px-2 py-0.5 text-[9px] font-medium ${row.status === "approved" ? "bg-emerald-50 text-emerald-700" : row.status === "submitted" ? "bg-amber-50 text-amber-700" : "bg-zinc-100 text-zinc-600"}`}>
                            {STATUS_LABEL[row.status]}
                          </span>
                        </td>
                        <td className="px-3 py-3 text-[10px] whitespace-nowrap text-zinc-400">{row.updatedAt}</td>
                        <td className="px-3 py-3 text-right whitespace-nowrap">
                          <button type="button" className="text-[10px] font-medium text-zinc-600 hover:text-zinc-900" onClick={() => openForm(row)}>
                            {row.status === "approved" ? "查看" : "编辑"}
                          </button>
                          {row.status === "draft" ? (
                            <>
                              <span className="mx-1.5 text-zinc-300">|</span>
                              <button type="button" className="text-[10px] font-medium text-blue-600" onClick={() => submitRow(row.id)}>提交审核</button>
                              <span className="mx-1.5 text-zinc-300">|</span>
                              <button type="button" className="text-[10px] font-medium text-rose-500" onClick={() => remove(row.id)}>删除</button>
                            </>
                          ) : null}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="flex flex-wrap items-center justify-between gap-2 border-t border-zinc-100 px-3 py-2.5">
                <p className="text-[10px] text-zinc-400">共 {filtered.length} 条 · 第 {currentPage} / {pages} 页</p>
                <div className="flex items-center gap-1">
                  <button type="button" className="h-6 rounded border border-zinc-200 px-2 text-[10px] text-zinc-600 disabled:text-zinc-300" disabled={currentPage <= 1} onClick={() => setPage(currentPage - 1)}>上一页</button>
                  <button type="button" className="h-6 rounded border border-zinc-200 px-2 text-[10px] text-zinc-600 disabled:text-zinc-300" disabled={currentPage >= pages} onClick={() => setPage(currentPage + 1)}>下一页</button>
                </div>
              </div>
            </div>
          )}
        </div>
      </section>

      {editing ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <button type="button" aria-label="关闭" className="absolute inset-0 bg-zinc-950/40" onClick={() => setEditing(null)} />
          <div className="relative flex max-h-[88vh] w-full max-w-[820px] flex-col overflow-hidden rounded-xl border border-zinc-200 bg-white shadow-2xl">
            <div className="flex items-start justify-between border-b border-zinc-100 px-5 py-4">
              <div>
                <h3 className="text-sm font-semibold text-zinc-900">{editing === "new" ? `新增${table.name}` : readonly ? `查看${table.name}` : `编辑${table.name}`}</h3>
                <p className="mt-1 text-[10px] text-zinc-500">{table.name} · {table.kind === "multi" ? "一名教师可登记多条记录" : "每名对象保留一条记录"}</p>
              </div>
              <button type="button" aria-label="关闭对话框" className="flex size-7 items-center justify-center rounded-md text-zinc-400 hover:bg-zinc-100" onClick={() => setEditing(null)}>
                <X className="size-4" aria-hidden="true" />
              </button>
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4 [scrollbar-width:none]">
              {table.sections.map((section, sectionIndex) => (
                <div key={section.title} className={sectionIndex > 0 ? "mt-5 border-t border-zinc-100 pt-5" : ""}>
                  <h4 className="text-[12px] font-semibold text-zinc-800">{section.title}</h4>
                  {section.desc ? <p className="mt-0.5 text-[9px] text-zinc-400">{section.desc}</p> : null}
                  <div className="mt-3 grid grid-cols-1 gap-x-4 gap-y-3 md:grid-cols-2">
                    {section.fields.map((field) => (
                      <label key={field.key} className={field.span === "full" ? "md:col-span-2" : ""}>
                        <span className="mb-1.5 flex items-center gap-1 text-[11px] font-medium text-zinc-700">
                          {field.label}
                          {field.required ? <span className="text-rose-500">*</span> : null}
                        </span>
                        {field.type === "textarea" ? (
                          <textarea
                            disabled={readonly}
                            className={`${fieldClass} h-20 py-2`}
                            value={draft[field.key] ?? ""}
                            placeholder={field.placeholder}
                            onChange={(event) => setDraft((current) => ({ ...current, [field.key]: event.target.value }))}
                          />
                        ) : field.type === "select" ? (
                          <FormCombobox
                            disabled={readonly}
                            placeholder="请选择"
                            value={draft[field.key] ?? ""}
                            options={[
                              { value: "", label: "请选择" },
                              ...(field.options ?? []).map((option) => ({ value: option, label: option })),
                            ]}
                            onValueChange={(value) => setDraft((current) => ({ ...current, [field.key]: value }))}
                          />
                        ) : (
                          <input
                            disabled={readonly}
                            type={field.type === "number" ? "number" : field.type === "date" ? "date" : "text"}
                            className={fieldClass}
                            value={draft[field.key] ?? ""}
                            placeholder={field.placeholder}
                            onChange={(event) => setDraft((current) => ({ ...current, [field.key]: event.target.value }))}
                          />
                        )}
                      </label>
                    ))}
                  </div>
                </div>
              ))}
            </div>
            <div className="flex flex-wrap items-center justify-end gap-2 border-t border-zinc-100 bg-zinc-50/60 px-5 py-3">
              <p className="mr-auto text-[10px] text-zinc-400">保存草稿后可继续编辑；提交审核后记录转为只读。</p>
              <button type="button" className="h-8 rounded-md border border-zinc-200 bg-white px-3 text-[11px] font-medium text-zinc-700" onClick={() => setEditing(null)}>关闭</button>
              {readonly ? null : (
                <>
                  <button type="button" className="h-8 rounded-md border border-zinc-200 bg-white px-3 text-[11px] font-medium text-zinc-700" onClick={() => save("draft")}>保存草稿</button>
                  <button type="button" className="h-8 rounded-md bg-zinc-900 px-3 text-[11px] font-medium text-white" onClick={() => save("submitted")}>提交审核</button>
                </>
              )}
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

function FillSwitch() {
  const requested = useSearchParams().get("table") || "staff";
  if (requested === "staff") return <StaffFill />;
  return <FillPageContent />;
}

export default function FillPage() {
  return (
    <Suspense fallback={<div className="p-6 text-sm text-zinc-400">正在打开数据表</div>}>
      <FillSwitch />
    </Suspense>
  );
}
