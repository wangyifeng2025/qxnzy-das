"use client";

import { useEffect, useMemo, useState } from "react";

import { ApiConnect } from "@/components/api-connect";
import { createAppColumnHelper, DataTable, TablePagination, useAppTable } from "@/components/data-table";
import { FormCombobox } from "@/components/form-combobox";
import {
  fieldClass,
  ghostButton,
  KpiCard,
  primaryButton,
  StatusPill,
} from "@/components/page-bits";
import { useToast } from "@/components/toast";
import { ApiError, api } from "@/lib/api";
import {
  DEPARTMENT_KIND_LABEL,
  type Department,
  type DepartmentKind,
} from "@/lib/departments";
import { readToken } from "@/lib/session";

type DepartmentDto = {
  id: number;
  code: string;
  name: string;
  short_name: string | null;
  kind: DepartmentKind;
  leader: string | null;
  data_manager: string | null;
  phone: string | null;
  sort_order: number;
  is_active: boolean;
  remark: string | null;
  user_count: number;
};

type Editing = { mode: "create" } | { mode: "edit"; department: Department };

const pageSize = 8;

const kindFilters: Array<{ value: "all" | DepartmentKind; label: string }> = [
  { value: "all", label: "全部" },
  { value: "teaching", label: "教学系部" },
  { value: "functional", label: "职能部门" },
  { value: "other", label: "其他" },
];

const deptHelper = createAppColumnHelper<Department>();

function messageOf(error: unknown) {
  return error instanceof ApiError ? error.message : "请求失败";
}

function blank(value: string) {
  const text = value.trim();
  return text || null;
}

function toDepartment(row: DepartmentDto): Department {
  return {
    id: row.id,
    code: row.code,
    name: row.name,
    shortName: row.short_name ?? "",
    kind: row.kind,
    leader: row.leader ?? "",
    dataManager: row.data_manager ?? "",
    phone: row.phone ?? "",
    sortOrder: row.sort_order,
    isActive: row.is_active,
    userCount: row.user_count,
    remark: row.remark ?? "",
  };
}

export default function DepartmentsPage() {
  const toast = useToast();
  const [phase, setPhase] = useState<"boot" | "auth" | "ready">("boot");
  const [departments, setDepartments] = useState<Department[]>([]);
  const [keyword, setKeyword] = useState("");
  const [kind, setKind] = useState<"all" | DepartmentKind>("all");
  const [showInactive, setShowInactive] = useState(true);
  const [editing, setEditing] = useState<Editing | null>(null);
  const [error, setError] = useState("");
  const [loadError, setLoadError] = useState("");

  useEffect(() => {
    let cancelled = false;
    if (!readToken()) {
      queueMicrotask(() => {
        if (!cancelled) setPhase("auth");
      });
      return () => {
        cancelled = true;
      };
    }
    api<DepartmentDto[]>("/api/departments")
      .then((rows) => {
        if (cancelled) return;
        setDepartments(rows.map(toDepartment));
        setPhase("ready");
      })
      .catch((reason: unknown) => {
        if (cancelled) return;
        if (reason instanceof ApiError && reason.status === 401) {
          setPhase("auth");
          return;
        }
        setLoadError(messageOf(reason));
        setPhase("ready");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const rows = useMemo(() => {
    const needle = keyword.trim().toLowerCase();
    return departments
      .filter((item) => kind === "all" || item.kind === kind)
      .filter((item) => showInactive || item.isActive)
      .filter(
        (item) =>
          !needle ||
          item.name.toLowerCase().includes(needle) ||
          item.code.toLowerCase().includes(needle) ||
          item.shortName.toLowerCase().includes(needle),
      )
      .sort((a, b) => a.sortOrder - b.sortOrder || a.id - b.id);
  }, [departments, keyword, kind, showInactive]);

  const columns = useMemo(
    () =>
      deptHelper.columns([
        deptHelper.accessor("code", {
          header: "编码",
          meta: { cellClassName: "font-mono text-[11px] text-zinc-500" },
        }),
        deptHelper.accessor("name", {
          header: "规范名称",
          meta: { cellClassName: "font-medium" },
        }),
        deptHelper.accessor("shortName", {
          header: "简称",
          cell: ({ getValue }) => getValue() || "—",
          meta: { cellClassName: "text-zinc-500" },
        }),
        deptHelper.accessor("kind", {
          header: "类型",
          cell: ({ getValue }) => (
            <StatusPill
              tone={
                getValue() === "teaching"
                  ? "run"
                  : getValue() === "functional"
                    ? "warn"
                    : "muted"
              }
            >
              {DEPARTMENT_KIND_LABEL[getValue()]}
            </StatusPill>
          ),
        }),
        deptHelper.accessor("leader", {
          header: "负责人",
          cell: ({ getValue }) => getValue() || "—",
        }),
        deptHelper.accessor("dataManager", {
          header: "数据管理员",
          cell: ({ getValue }) => getValue() || "—",
        }),
        deptHelper.accessor("phone", {
          header: "联系电话",
          cell: ({ getValue }) => getValue() || "—",
          meta: { cellClassName: "font-mono text-[11px]" },
        }),
        deptHelper.accessor("userCount", { header: "账号数" }),
        deptHelper.accessor("sortOrder", {
          header: "排序",
          meta: { cellClassName: "text-zinc-500" },
        }),
        deptHelper.accessor("isActive", {
          header: "状态",
          cell: ({ getValue }) => (
            <StatusPill tone={getValue() ? "ok" : "muted"}>
              {getValue() ? "启用" : "停用"}
            </StatusPill>
          ),
        }),
        deptHelper.display({
          id: "actions",
          header: "操作",
          meta: { headClassName: "text-right", cellClassName: "text-right" },
          cell: ({ row }) => (
            <div className="flex gap-3 text-[11px] font-medium">
              <button
                type="button"
                onClick={() => {
                  setError("");
                  setEditing({ mode: "edit", department: row.original });
                }}
              >
                编辑
              </button>
              <button type="button" onClick={() => void toggleActive(row.original)}>
                {row.original.isActive ? "停用" : "启用"}
              </button>
              <button
                type="button"
                className="text-rose-700"
                onClick={() => void remove(row.original)}
              >
                删除
              </button>
            </div>
          ),
        }),
      ]),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  );

  const deptTable = useAppTable({
    data: rows,
    columns,
    initialState: { pagination: { pageIndex: 0, pageSize } },
  });

  const teachingCount = departments.filter(
    (item) => item.kind === "teaching",
  ).length;
  const functionalCount = departments.filter(
    (item) => item.kind === "functional",
  ).length;
  const activeCount = departments.filter((item) => item.isActive).length;
  const totalUsers = departments.reduce((sum, item) => sum + item.userCount, 0);

  async function reload() {
    const next = (await api<DepartmentDto[]>("/api/departments")).map(
      toDepartment,
    );
    setDepartments(next);
  }

  async function toggleActive(target: Department) {
    if (target.isActive && target.userCount > 0 && target.kind === "teaching") {
      toast(
        `${target.name} 下仍有 ${target.userCount} 个账号，停用后这些账号将无法填报`,
      );
    }
    try {
      await api(`/api/departments/${target.id}`, {
        method: "PATCH",
        body: JSON.stringify({ is_active: !target.isActive }),
      });
      await reload();
      toast(
        target.isActive ? `已停用 ${target.name}` : `已启用 ${target.name}`,
      );
    } catch (reason) {
      toast(messageOf(reason));
    }
  }

  async function remove(target: Department) {
    try {
      await api(`/api/departments/${target.id}`, { method: "DELETE" });
      await reload();
      toast(`已删除 ${target.name}`);
    } catch (reason) {
      toast(messageOf(reason));
    }
  }

  async function save(form: FormData) {
    const code = String(form.get("code") ?? "")
      .trim()
      .toUpperCase();
    const name = String(form.get("name") ?? "").trim();
    if (!code || !name) {
      setError("部门编码和规范名称为必填项。");
      return;
    }
    const body = {
      code,
      name,
      short_name: blank(String(form.get("shortName") ?? "")),
      kind: String(form.get("kind") ?? "teaching"),
      leader: blank(String(form.get("leader") ?? "")),
      data_manager: blank(String(form.get("dataManager") ?? "")),
      phone: blank(String(form.get("phone") ?? "")),
      sort_order: Number(form.get("sortOrder") ?? 0) || 0,
      remark: blank(String(form.get("remark") ?? "")),
    };
    try {
      if (editing?.mode === "edit") {
        await api(`/api/departments/${editing.department.id}`, {
          method: "PATCH",
          body: JSON.stringify(body),
        });
        toast(`已更新 ${name}`);
      } else {
        await api("/api/departments", {
          method: "POST",
          body: JSON.stringify(body),
        });
        toast(`已新增 ${name}`);
      }
      await reload();
      setEditing(null);
      setError("");
    } catch (reason) {
      setError(messageOf(reason));
    }
  }

  const draft = editing?.mode === "edit" ? editing.department : null;

  if (phase === "boot") {
    return (
      <div className="grid min-h-80 place-items-center text-sm text-zinc-400">
        正在加载系部
      </div>
    );
  }
  if (phase === "auth") return <ApiConnect title="系部管理" />;

  return (
    <div className="absolute inset-0 flex flex-col gap-4 overflow-hidden p-5">
      <div className="flex shrink-0 flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-[19px] font-semibold tracking-tight text-zinc-900">
            系部管理
          </h1>
          <p className="mt-1 text-[12px] text-zinc-500">
            维护学院教学系部与职能部门的规范名称、编码与数据管理员，作为填报范围与审核职责的组织依据
          </p>
        </div>
        <button
          type="button"
          className={primaryButton}
          onClick={() => {
            setError("");
            setEditing({ mode: "create" });
          }}
        >
          新增系部 / 部门
        </button>
      </div>

      {loadError ? (
        <p className="shrink-0 rounded-md bg-rose-50 px-3 py-2 text-[12px] text-rose-700">
          {loadError}
        </p>
      ) : null}

      <div className="grid shrink-0 grid-cols-2 gap-3 xl:grid-cols-4">
        <KpiCard
          label="教学系部"
          value={String(teachingCount)}
          note="承担专业建设与数据填报"
        />
        <KpiCard
          label="职能部门"
          value={String(functionalCount)}
          note="按职责审核与归口管理"
        />
        <KpiCard
          label="启用中"
          value={`${activeCount} / ${departments.length}`}
          note="停用的部门不再出现在填报下拉中"
        />
        <KpiCard
          label="关联账号"
          value={String(totalUsers)}
          note="所有部门下的用户账号合计"
        />
      </div>

      <section className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-lg border border-zinc-200 bg-white shadow-sm">
        <div className="flex shrink-0 flex-wrap items-center gap-2 border-b border-zinc-100 px-4 py-3">
          <input
            className={`${fieldClass} max-w-64`}
            placeholder="搜索编码、名称或简称"
            value={keyword}
            onChange={(event) => setKeyword(event.target.value)}
          />
          <div className="flex gap-1">
            {kindFilters.map((item) => (
              <button
                key={item.value}
                type="button"
                onClick={() => setKind(item.value)}
                className={`rounded-md px-3 py-1.5 text-[12px] ${
                  kind === item.value
                    ? "bg-zinc-900 text-white"
                    : "bg-white text-zinc-600 ring-1 ring-zinc-200"
                }`}
              >
                {item.label}
              </button>
            ))}
          </div>
          <label className="ml-auto flex items-center gap-2 text-[12px] text-zinc-600">
            <input
              type="checkbox"
              className="size-3.5"
              checked={showInactive}
              onChange={(event) => setShowInactive(event.target.checked)}
            />
            显示已停用
          </label>
        </div>
        <DataTable
          table={deptTable}
          empty="没有符合条件的系部或部门"
          stickyHeader
          containerClassName="min-h-0 flex-1 overflow-auto"
        />
        <TablePagination table={deptTable} />
      </section>

      {editing ? (
        <div className="fixed inset-0 z-50 grid place-items-center overflow-y-auto bg-zinc-950/40 p-4">
          <form
            className="max-h-[calc(100vh-2rem)] w-full max-w-lg overflow-y-auto rounded-xl bg-white p-5"
            onSubmit={(event) => {
              event.preventDefault();
              void save(new FormData(event.currentTarget));
            }}
          >
            <h2 className="text-sm font-semibold">
              {draft ? `编辑 ${draft.name}` : "新增系部 / 部门"}
            </h2>
            <div className="mt-4 grid gap-3 sm:grid-cols-2">
              <label className="grid gap-1 text-[11px] text-zinc-500">
                部门编码 *
                <input
                  name="code"
                  className={fieldClass}
                  placeholder="如 XB07"
                  defaultValue={draft?.code ?? ""}
                />
              </label>
              <label className="grid gap-1 text-[11px] text-zinc-500">
                类型 *
                <FormCombobox
                  name="kind"
                  placeholder="请选择类型"
                  defaultValue={draft?.kind ?? "teaching"}
                  options={[
                    { value: "teaching", label: "教学系部" },
                    { value: "functional", label: "职能部门" },
                    { value: "other", label: "其他" },
                  ]}
                />
              </label>
              <label className="grid gap-1 text-[11px] text-zinc-500 sm:col-span-2">
                规范名称（全称） *
                <input
                  name="name"
                  className={fieldClass}
                  placeholder="如 护理系"
                  defaultValue={draft?.name ?? ""}
                />
              </label>
              <label className="grid gap-1 text-[11px] text-zinc-500">
                简称
                <input
                  name="shortName"
                  className={fieldClass}
                  defaultValue={draft?.shortName ?? ""}
                />
              </label>
              <label className="grid gap-1 text-[11px] text-zinc-500">
                排序
                <input
                  name="sortOrder"
                  type="number"
                  className={fieldClass}
                  defaultValue={draft?.sortOrder ?? 20}
                />
              </label>
              <label className="grid gap-1 text-[11px] text-zinc-500">
                负责人
                <input
                  name="leader"
                  className={fieldClass}
                  defaultValue={draft?.leader ?? ""}
                />
              </label>
              <label className="grid gap-1 text-[11px] text-zinc-500">
                数据管理员
                <input
                  name="dataManager"
                  className={fieldClass}
                  defaultValue={draft?.dataManager ?? ""}
                />
              </label>
              <label className="grid gap-1 text-[11px] text-zinc-500">
                联系电话
                <input
                  name="phone"
                  className={fieldClass}
                  defaultValue={draft?.phone ?? ""}
                />
              </label>
              <label className="grid gap-1 text-[11px] text-zinc-500 sm:col-span-2">
                备注
                <input
                  name="remark"
                  className={fieldClass}
                  defaultValue={draft?.remark ?? ""}
                />
              </label>
            </div>
            {error ? (
              <p className="mt-3 rounded-md bg-rose-50 px-2.5 py-2 text-[11px] text-rose-700">
                {error}
              </p>
            ) : null}
            <div className="mt-4 flex justify-end gap-2">
              <button
                type="button"
                className={ghostButton}
                onClick={() => setEditing(null)}
              >
                取消
              </button>
              <button type="submit" className={primaryButton}>
                保存
              </button>
            </div>
          </form>
        </div>
      ) : null}
    </div>
  );
}
