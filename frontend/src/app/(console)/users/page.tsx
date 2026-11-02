"use client";

import { Activity, ChevronLeft, ChevronRight, Search, Upload, UserCheck, UserPlus, UserX, Users, X } from "lucide-react";
import { useEffect, useMemo, useState, type ReactNode } from "react";

import { ApiConnect } from "@/components/api-connect";
import { useToast } from "@/components/toast";
import { ApiError, api } from "@/lib/api";
import { readToken } from "@/lib/session";

type DepartmentOption = { id: number; name: string };
type RoleOption = { code: string; name: string };

type UserRow = {
  id: number;
  account: string;
  name: string;
  department_id: number | null;
  department_name: string | null;
  role_codes: string[];
  role_names: string[];
  post: string | null;
  phone: string | null;
  status: "active" | "disabled";
  is_superuser: boolean;
  last_login_at: string | null;
};

type UserPage = { items: UserRow[]; total: number; page: number; page_size: number };

const pageSize = 6;
const fieldClass = "w-full rounded-md border border-zinc-200 bg-white px-2.5 py-2 text-[12px] outline-none focus:border-zinc-400";

const roleStyles: Record<string, string> = {
  teacher: "bg-blue-50 text-blue-700",
  staff: "bg-violet-50 text-violet-700",
  auditor: "bg-amber-50 text-amber-700",
  admin: "bg-zinc-900 text-white",
};

function messageOf(error: unknown) {
  return error instanceof ApiError ? error.message : "请求失败";
}

function blank(value: string) {
  const text = value.trim();
  return text || null;
}

function formatTime(value: string | null) {
  if (!value) return "尚未登录";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  const pad = (number: number) => String(number).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function Modal({
  title,
  onClose,
  children,
  footer,
}: {
  title: string;
  onClose: () => void;
  children: ReactNode;
  footer: ReactNode;
}) {
  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-zinc-900/40 p-4">
      <div className="w-full max-w-lg rounded-xl border border-zinc-200 bg-white shadow-xl">
        <div className="flex items-center justify-between border-b border-zinc-100 px-5 py-3.5">
          <h3 className="text-[14px] font-semibold text-zinc-900">{title}</h3>
          <button type="button" className="flex h-7 w-7 items-center justify-center rounded-md text-zinc-400 transition hover:bg-zinc-100" onClick={onClose} aria-label="关闭">
            <X className="size-3.5" />
          </button>
        </div>
        <div className="space-y-3 px-5 py-4">{children}</div>
        <div className="flex items-center justify-end gap-2 border-t border-zinc-100 px-5 py-3">{footer}</div>
      </div>
    </div>
  );
}

export default function UsersPage() {
  const toast = useToast();
  const [phase, setPhase] = useState<"boot" | "auth" | "ready">("boot");
  const [users, setUsers] = useState<UserRow[]>([]);
  const [total, setTotal] = useState(0);
  const [departments, setDepartments] = useState<DepartmentOption[]>([]);
  const [roles, setRoles] = useState<RoleOption[]>([]);
  const [keyword, setKeyword] = useState("");
  const [dept, setDept] = useState("");
  const [role, setRole] = useState("");
  const [status, setStatus] = useState<"" | "active" | "disabled">("");
  const [page, setPage] = useState(1);
  const [editing, setEditing] = useState<UserRow | "new" | null>(null);
  const [assigning, setAssigning] = useState<UserRow | null>(null);
  const [roleCodes, setRoleCodes] = useState<string[]>([]);
  const [resetUser, setResetUser] = useState<UserRow | null>(null);
  const [formError, setFormError] = useState("");
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
    Promise.all([
      api<UserPage>("/api/users?page=1&page_size=200"),
      api<DepartmentOption[]>("/api/departments"),
      api<RoleOption[]>("/api/roles"),
    ])
      .then(([userPage, departmentRows, roleRows]) => {
        if (cancelled) return;
        setUsers(userPage.items);
        setTotal(userPage.total);
        setDepartments(departmentRows.map((item) => ({ id: item.id, name: item.name })));
        setRoles(roleRows.map((item) => ({ code: item.code, name: item.name })));
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

  const filtered = useMemo(() => {
    const needle = keyword.trim().toLowerCase();
    return users.filter((user) => {
      const hit = !needle || `${user.account} ${user.name} ${user.phone ?? ""}`.toLowerCase().includes(needle);
      const deptHit = !dept || String(user.department_id ?? "") === dept;
      const roleHit = !role || user.role_codes.includes(role);
      const statusHit = !status || user.status === status;
      return hit && deptHit && roleHit && statusHit;
    });
  }, [users, keyword, dept, role, status]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));
  const currentPage = Math.min(page, totalPages);
  const rows = filtered.slice((currentPage - 1) * pageSize, currentPage * pageSize);
  const activeCount = users.filter((user) => user.status === "active").length;
  const signedInCount = users.filter((user) => user.last_login_at).length;
  const loadedNote = total > users.length ? `已加载 ${users.length} / ${total} 个账号` : `共 ${users.length} 个账号`;

  async function reloadUsers() {
    const userPage = await api<UserPage>("/api/users?page=1&page_size=200");
    setUsers(userPage.items);
    setTotal(userPage.total);
  }

  async function saveUser(form: FormData) {
    const account = String(form.get("account") ?? "").trim();
    const name = String(form.get("name") ?? "").trim();
    const password = String(form.get("password") ?? "");
    if (!account || !name) {
      setFormError("请填写工号和姓名");
      return;
    }
    const departmentId = Number(form.get("department_id") || 0) || null;
    const selectedRole = String(form.get("role") ?? "");
    const payload = {
      name,
      department_id: departmentId,
      post: blank(String(form.get("post") ?? "")),
      phone: blank(String(form.get("phone") ?? "")),
    };
    try {
      if (editing && editing !== "new") {
        await api(`/api/users/${editing.id}`, { method: "PATCH", body: JSON.stringify(payload) });
        toast("用户信息已更新");
      } else {
        if (password.length < 6) {
          setFormError("初始密码至少 6 位");
          return;
        }
        await api("/api/users", {
          method: "POST",
          body: JSON.stringify({
            account,
            password,
            status: "active",
            role_codes: selectedRole ? [selectedRole] : [],
            ...payload,
          }),
        });
        toast("用户已新增");
        setPage(1);
      }
      await reloadUsers();
      setEditing(null);
      setFormError("");
    } catch (reason) {
      setFormError(messageOf(reason));
    }
  }

  async function toggleStatus(user: UserRow) {
    const next = user.status === "active" ? "disabled" : "active";
    try {
      await api(`/api/users/${user.id}/status`, { method: "PATCH", body: JSON.stringify({ status: next }) });
      await reloadUsers();
      toast(`${user.name}${next === "disabled" ? " 已停用" : " 已启用"}`);
    } catch (reason) {
      toast(messageOf(reason));
    }
  }

  async function saveRoles() {
    if (!assigning) return;
    try {
      await api(`/api/users/${assigning.id}`, {
        method: "PATCH",
        body: JSON.stringify({ role_codes: roleCodes }),
      });
      await reloadUsers();
      toast(`${assigning.name} 的角色已更新`);
      setAssigning(null);
    } catch (reason) {
      toast(messageOf(reason));
    }
  }

  async function resetPassword(form: FormData) {
    if (!resetUser) return;
    const password = String(form.get("password") ?? "");
    if (password.length < 6) {
      setFormError("新密码至少 6 位");
      return;
    }
    try {
      await api(`/api/users/${resetUser.id}/reset-password`, {
        method: "POST",
        body: JSON.stringify({ password }),
      });
      toast(`${resetUser.name} 的密码已重置`);
      setResetUser(null);
      setFormError("");
    } catch (reason) {
      setFormError(messageOf(reason));
    }
  }

  if (phase === "boot") {
    return <div className="grid min-h-[320px] place-items-center text-sm text-zinc-400">正在加载用户</div>;
  }
  if (phase === "auth") return <ApiConnect title="用户管理" />;

  const draft = editing && editing !== "new" ? editing : null;

  return (
    <div className="mx-auto max-w-[1180px] space-y-4 p-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-[19px] font-semibold tracking-tight text-zinc-900">用户管理</h1>
          <p className="mt-1 text-[12px] text-zinc-500">维护全校填报账号、所属部门与角色权限分配</p>
        </div>
        <div className="flex items-center gap-2">
          <button type="button" className="flex items-center gap-1.5 rounded-md border border-zinc-200 bg-white px-3 py-2 text-[12px] text-zinc-600 transition hover:bg-zinc-50" onClick={() => toast("批量导入接口尚未提供")}>
            <Upload className="size-3.5" />批量导入
          </button>
          <button type="button" className="flex items-center gap-1.5 rounded-md bg-zinc-900 px-3.5 py-2 text-[12px] font-medium text-white transition hover:bg-zinc-800" onClick={() => { setFormError(""); setEditing("new"); }}>
            <UserPlus className="size-3.5" />新增用户
          </button>
        </div>
      </div>

      {loadError ? <p className="rounded-md bg-rose-50 px-3 py-2 text-[12px] text-rose-700">{loadError}</p> : null}

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {[
          { label: "账号总数", value: total, note: loadedNote, icon: Users, tone: "text-zinc-900", iconTone: "text-zinc-400" },
          { label: "正常启用", value: activeCount, note: "可正常登录填报", icon: UserCheck, tone: "text-emerald-600", iconTone: "text-emerald-500" },
          { label: "已停用", value: users.length - activeCount, note: "停用后无法登录", icon: UserX, tone: "text-amber-600", iconTone: "text-amber-500" },
          { label: "曾登录", value: signedInCount, note: "已有最近登录记录的账号", icon: Activity, tone: "text-blue-600", iconTone: "text-blue-500" },
        ].map((card) => (
          <div key={card.label} className="rounded-lg border border-zinc-200 bg-white p-4">
            <div className="flex items-center justify-between">
              <p className="text-[11px] text-zinc-500">{card.label}</p>
              <card.icon className={`size-4 ${card.iconTone}`} />
            </div>
            <p className={`mt-2 text-[22px] leading-none font-semibold ${card.tone}`}>{card.value}</p>
            <p className="mt-1.5 text-[10px] text-zinc-400">{card.note}</p>
          </div>
        ))}
      </div>

      <div className="rounded-lg border border-zinc-200 bg-white">
        <div className="flex flex-wrap items-center gap-2 border-b border-zinc-100 px-4 py-3">
          <div className="flex min-w-[190px] flex-1 items-center gap-2 rounded-md border border-zinc-200 px-2.5 py-1.5 focus-within:border-zinc-400">
            <Search className="size-3.5 text-zinc-400" />
            <input className="w-full border-0 bg-transparent p-0 text-[12px] outline-none placeholder:text-zinc-400" placeholder="搜索工号 / 姓名 / 手机号" value={keyword} onChange={(event) => { setKeyword(event.target.value); setPage(1); }} />
          </div>
          <select className="rounded-md border border-zinc-200 bg-white px-2.5 py-1.5 text-[12px] text-zinc-600 outline-none" value={dept} onChange={(event) => { setDept(event.target.value); setPage(1); }}>
            <option value="">全部部门</option>
            {departments.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
          </select>
          <select className="rounded-md border border-zinc-200 bg-white px-2.5 py-1.5 text-[12px] text-zinc-600 outline-none" value={role} onChange={(event) => { setRole(event.target.value); setPage(1); }}>
            <option value="">全部角色</option>
            {roles.map((item) => <option key={item.code} value={item.code}>{item.name}</option>)}
          </select>
          <select className="rounded-md border border-zinc-200 bg-white px-2.5 py-1.5 text-[12px] text-zinc-600 outline-none" value={status} onChange={(event) => { setStatus(event.target.value as "" | "active" | "disabled"); setPage(1); }}>
            <option value="">全部状态</option>
            <option value="active">正常</option>
            <option value="disabled">停用</option>
          </select>
          <button type="button" className="rounded-md border border-zinc-200 px-2.5 py-1.5 text-[12px] text-zinc-500 transition hover:bg-zinc-50" onClick={() => { setKeyword(""); setDept(""); setRole(""); setStatus(""); setPage(1); }}>重置</button>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[980px] border-collapse text-left">
            <thead>
              <tr className="border-b border-zinc-100 bg-zinc-50/60 text-[11px] text-zinc-500">
                {["工号 / 账号", "姓名", "所属部门", "角色", "岗位", "手机号", "状态", "最近登录时间"].map((head) => <th key={head} className="px-4 py-2.5 font-medium">{head}</th>)}
                <th className="px-4 py-2.5 text-right font-medium">操作</th>
              </tr>
            </thead>
            <tbody className="text-[12px] text-zinc-700">
              {rows.length ? rows.map((user) => (
                <tr key={user.id} className="border-b border-zinc-50 last:border-0 hover:bg-zinc-50/60">
                  <td className="px-4 py-2.5 font-mono text-[11px] text-zinc-500">{user.account}</td>
                  <td className="px-4 py-2.5 font-medium text-zinc-900">{user.name}</td>
                  <td className="px-4 py-2.5 text-zinc-600">{user.department_name || "—"}</td>
                  <td className="px-4 py-2.5">
                    <div className="flex flex-wrap gap-1">
                      {user.role_names.length ? user.role_names.map((name, index) => (
                        <span key={`${user.id}-${name}`} className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${roleStyles[user.role_codes[index] ?? ""] ?? "bg-zinc-100 text-zinc-600"}`}>{name}</span>
                      )) : <span className="text-zinc-400">未分配</span>}
                    </div>
                  </td>
                  <td className="px-4 py-2.5 text-zinc-600">{user.post || "—"}</td>
                  <td className="px-4 py-2.5 font-mono text-[11px] text-zinc-500">{user.phone || "—"}</td>
                  <td className="px-4 py-2.5">
                    {user.status === "active" ? (
                      <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-0.5 text-[10px] font-medium text-emerald-700"><span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />正常</span>
                    ) : (
                      <span className="inline-flex items-center gap-1 rounded-full bg-zinc-100 px-2 py-0.5 text-[10px] font-medium text-zinc-500"><span className="h-1.5 w-1.5 rounded-full bg-zinc-400" />停用</span>
                    )}
                  </td>
                  <td className="px-4 py-2.5 text-[11px] text-zinc-500">{formatTime(user.last_login_at)}</td>
                  <td className="px-4 py-2.5">
                    <div className="flex items-center justify-end gap-1">
                      <button type="button" className="rounded px-1.5 py-1 text-[11px] text-zinc-600 transition hover:bg-zinc-100" onClick={() => { setFormError(""); setEditing(user); }}>编辑</button>
                      <button type="button" className={`rounded px-1.5 py-1 text-[11px] ${user.status === "active" ? "text-amber-600 hover:bg-amber-50" : "text-emerald-600 hover:bg-emerald-50"}`} onClick={() => void toggleStatus(user)}>{user.status === "active" ? "停用" : "启用"}</button>
                      <button type="button" className="rounded px-1.5 py-1 text-[11px] text-blue-600 transition hover:bg-blue-50" onClick={() => { setAssigning(user); setRoleCodes(user.role_codes); }}>分配角色</button>
                      <button type="button" className="rounded px-1.5 py-1 text-[11px] text-zinc-500 transition hover:bg-zinc-100" onClick={() => { setFormError(""); setResetUser(user); }}>重置密码</button>
                    </div>
                  </td>
                </tr>
              )) : (
                <tr><td colSpan={9} className="px-4 py-10 text-center text-[12px] text-zinc-400">未找到匹配的用户，请调整筛选条件</td></tr>
              )}
            </tbody>
          </table>
        </div>
        <div className="flex flex-wrap items-center justify-between gap-2 border-t border-zinc-100 px-4 py-3">
          <p className="text-[11px] text-zinc-400">共 {filtered.length} 条，第 {currentPage} / {totalPages} 页</p>
          <div className="flex items-center gap-1.5">
            <button type="button" className="flex h-7 w-7 items-center justify-center rounded-md border border-zinc-200 text-zinc-500 transition hover:bg-zinc-50 disabled:opacity-40" onClick={() => setPage(Math.max(1, currentPage - 1))} disabled={currentPage <= 1} aria-label="上一页"><ChevronLeft className="size-3.5" /></button>
            {Array.from({ length: totalPages }, (_, index) => index + 1).map((number) => (
              <button key={number} type="button" className={`flex h-7 min-w-7 items-center justify-center rounded-md px-2 text-[11px] ${number === currentPage ? "bg-zinc-900 text-white" : "border border-zinc-200 text-zinc-500 hover:bg-zinc-50"}`} onClick={() => setPage(number)}>{number}</button>
            ))}
            <button type="button" className="flex h-7 w-7 items-center justify-center rounded-md border border-zinc-200 text-zinc-500 transition hover:bg-zinc-50 disabled:opacity-40" onClick={() => setPage(Math.min(totalPages, currentPage + 1))} disabled={currentPage >= totalPages} aria-label="下一页"><ChevronRight className="size-3.5" /></button>
          </div>
        </div>
      </div>

      {editing ? (
        <Modal
          title={editing === "new" ? "新增用户" : "编辑用户"}
          onClose={() => setEditing(null)}
          footer={
            <>
              <button type="button" className="rounded-md border border-zinc-200 px-3.5 py-2 text-[12px] text-zinc-600 transition hover:bg-zinc-50" onClick={() => setEditing(null)}>取消</button>
              <button type="submit" form="user-form" className="rounded-md bg-zinc-900 px-3.5 py-2 text-[12px] font-medium text-white transition hover:bg-zinc-800">保存</button>
            </>
          }
        >
          <form id="user-form" className="grid grid-cols-2 gap-3" onSubmit={(event) => { event.preventDefault(); void saveUser(new FormData(event.currentTarget)); }}>
            <label className="block"><span className="mb-1 block text-[11px] text-zinc-500">工号 / 账号 <span className="text-rose-500">*</span></span><input name="account" className={fieldClass} placeholder="如 T20260118" defaultValue={draft?.account ?? ""} readOnly={Boolean(draft)} /></label>
            <label className="block"><span className="mb-1 block text-[11px] text-zinc-500">姓名 <span className="text-rose-500">*</span></span><input name="name" className={fieldClass} placeholder="请输入真实姓名" defaultValue={draft?.name ?? ""} /></label>
            <label className="block"><span className="mb-1 block text-[11px] text-zinc-500">所属部门</span>
              <select name="department_id" className={fieldClass} defaultValue={draft?.department_id ?? ""}>
                <option value="">未分配</option>
                {departments.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
              </select>
            </label>
            {editing === "new" ? (
              <label className="block"><span className="mb-1 block text-[11px] text-zinc-500">角色</span>
                <select name="role" className={fieldClass} defaultValue={roles.find((item) => item.code === "teacher")?.code ?? ""}>
                  <option value="">未分配</option>
                  {roles.map((item) => <option key={item.code} value={item.code}>{item.name}</option>)}
                </select>
              </label>
            ) : (
              <label className="block"><span className="mb-1 block text-[11px] text-zinc-500">角色</span>
                <input className={fieldClass} defaultValue={draft?.role_names.join("、") || "未分配"} readOnly />
              </label>
            )}
            <label className="block"><span className="mb-1 block text-[11px] text-zinc-500">岗位</span><input name="post" className={fieldClass} placeholder="如 专任教师 / 教学秘书" defaultValue={draft?.post ?? ""} /></label>
            <label className="block"><span className="mb-1 block text-[11px] text-zinc-500">手机号</span><input name="phone" className={fieldClass} placeholder="11 位手机号" defaultValue={draft?.phone ?? ""} /></label>
            {editing === "new" ? (
              <label className="col-span-2 block"><span className="mb-1 block text-[11px] text-zinc-500">初始密码 <span className="text-rose-500">*</span></span><input name="password" type="password" className={fieldClass} placeholder="至少 6 位" /></label>
            ) : null}
            <p className="col-span-2 rounded-md bg-zinc-50 px-3 py-2 text-[11px] leading-relaxed text-zinc-500">角色决定该账号登录后可见的功能范围。需要同时授予多个角色时，使用列表中的「分配角色」。</p>
            {formError ? <p className="col-span-2 text-[11px] text-rose-600">{formError}</p> : null}
          </form>
        </Modal>
      ) : null}

      {assigning ? (
        <Modal
          title={`分配角色 · ${assigning.name}`}
          onClose={() => setAssigning(null)}
          footer={
            <>
              <button type="button" className="rounded-md border border-zinc-200 px-3.5 py-2 text-[12px] text-zinc-600 hover:bg-zinc-50" onClick={() => setAssigning(null)}>取消</button>
              <button type="button" className="rounded-md bg-zinc-900 px-3.5 py-2 text-[12px] font-medium text-white hover:bg-zinc-800" onClick={() => void saveRoles()}>保存</button>
            </>
          }
        >
          <div className="grid gap-1.5">
            {roles.map((item) => (
              <label key={item.code} className="flex items-center gap-2 rounded-md border border-zinc-200 px-2.5 py-2 text-[12px] text-zinc-700">
                <input
                  type="checkbox"
                  className="size-3.5 accent-zinc-900"
                  checked={roleCodes.includes(item.code)}
                  onChange={() => setRoleCodes((current) => current.includes(item.code) ? current.filter((code) => code !== item.code) : [...current, item.code])}
                />
                {item.name}
                <span className="font-mono text-[10px] text-zinc-400">{item.code}</span>
              </label>
            ))}
          </div>
        </Modal>
      ) : null}

      {resetUser ? (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-zinc-900/40 p-4">
          <form
            className="w-full max-w-sm rounded-xl border border-zinc-200 bg-white shadow-xl"
            onSubmit={(event) => {
              event.preventDefault();
              void resetPassword(new FormData(event.currentTarget));
            }}
          >
            <div className="flex items-center justify-between border-b border-zinc-100 px-5 py-3.5">
              <h3 className="text-[14px] font-semibold text-zinc-900">重置密码</h3>
              <button type="button" className="flex h-7 w-7 items-center justify-center rounded-md text-zinc-400 hover:bg-zinc-100" onClick={() => setResetUser(null)} aria-label="关闭"><X className="size-3.5" /></button>
            </div>
            <div className="space-y-3 px-5 py-4">
              <p className="text-[12px] text-zinc-600">为 {resetUser.name}（{resetUser.account}）设置新密码。重置操作会记入审计日志。</p>
              <label className="block"><span className="mb-1 block text-[11px] text-zinc-500">新密码</span><input name="password" type="password" className={fieldClass} placeholder="至少 6 位" /></label>
              {formError ? <p className="text-[11px] text-rose-600">{formError}</p> : null}
            </div>
            <div className="flex items-center justify-end gap-2 border-t border-zinc-100 px-5 py-3">
              <button type="button" className="rounded-md border border-zinc-200 px-3.5 py-2 text-[12px] text-zinc-600 hover:bg-zinc-50" onClick={() => setResetUser(null)}>取消</button>
              <button type="submit" className="rounded-md bg-zinc-900 px-3.5 py-2 text-[12px] font-medium text-white hover:bg-zinc-800">确认重置</button>
            </div>
          </form>
        </div>
      ) : null}
    </div>
  );
}
