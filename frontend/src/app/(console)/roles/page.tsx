"use client";

import { Plus, Search, ShieldAlert, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { ApiConnect } from "@/components/api-connect";
import { useToast } from "@/components/toast";
import { ApiError, api } from "@/lib/api";
import { readToken } from "@/lib/session";

type DataScope = "self" | "department" | "all";

type Permission = {
  code: string;
  name: string;
  module: string;
  sort_order: number;
};

type RoleRow = {
  id: number;
  name: string;
  code: string;
  description: string | null;
  data_scope: DataScope;
  is_builtin: boolean;
  permission_codes: string[];
  user_count: number;
  updated_at: string;
};

const fieldClass = "w-full rounded-md border border-zinc-200 bg-white px-2.5 py-2 text-[12px] outline-none focus:border-zinc-400";

const scopeOptions: Array<{ value: DataScope; label: string }> = [
  { value: "self", label: "本人" },
  { value: "department", label: "本部门" },
  { value: "all", label: "全校" },
];

function messageOf(error: unknown) {
  return error instanceof ApiError ? error.message : "请求失败";
}

function scopeLabel(scope: DataScope) {
  return scopeOptions.find((item) => item.value === scope)?.label ?? scope;
}

function scopeBadge(scope: DataScope) {
  if (scope === "all") return "bg-zinc-900 text-white";
  if (scope === "department") return "bg-violet-50 text-violet-700";
  return "bg-blue-50 text-blue-700";
}

function formatTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  const pad = (number: number) => String(number).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

export default function RolesPage() {
  const toast = useToast();
  const [phase, setPhase] = useState<"boot" | "auth" | "ready">("boot");
  const [roles, setRoles] = useState<RoleRow[]>([]);
  const [permissions, setPermissions] = useState<Permission[]>([]);
  const [keyword, setKeyword] = useState("");
  const [editing, setEditing] = useState<RoleRow | "new" | null>(null);
  const [permRole, setPermRole] = useState<RoleRow | null>(null);
  const [selected, setSelected] = useState<string[]>([]);
  const [scope, setScope] = useState<DataScope>("department");
  const [deleteReason, setDeleteReason] = useState("");
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
    Promise.all([api<RoleRow[]>("/api/roles"), api<Permission[]>("/api/permissions")])
      .then(([roleRows, permissionRows]) => {
        if (cancelled) return;
        setRoles(roleRows);
        setPermissions(permissionRows);
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

  const visible = useMemo(() => {
    const needle = keyword.trim().toLowerCase();
    return roles.filter((role) => !needle || `${role.name}${role.code}`.toLowerCase().includes(needle));
  }, [roles, keyword]);

  const modules = useMemo(() => {
    const groups = new Map<string, Permission[]>();
    for (const item of [...permissions].sort((a, b) => a.sort_order - b.sort_order)) {
      const list = groups.get(item.module) ?? [];
      list.push(item);
      groups.set(item.module, list);
    }
    return [...groups.entries()];
  }, [permissions]);

  const builtinRoles = roles.filter((role) => role.is_builtin);

  async function reload() {
    setRoles(await api<RoleRow[]>("/api/roles"));
  }

  function openPerm(role: RoleRow) {
    setPermRole(role);
    setSelected(role.permission_codes);
    setScope(role.data_scope);
    setFormError("");
  }

  async function saveRole(form: FormData) {
    const name = String(form.get("name") ?? "").trim();
    const code = String(form.get("code") ?? "").trim();
    const nextScope = String(form.get("scope") ?? "self") as DataScope;
    const description = String(form.get("description") ?? "").trim();
    if (!name || (editing === "new" && !code)) {
      setFormError("请填写角色名称和角色编码");
      return;
    }
    try {
      if (editing && editing !== "new") {
        await api(`/api/roles/${editing.id}`, {
          method: "PATCH",
          body: JSON.stringify({ name, description: description || null, data_scope: nextScope }),
        });
        toast("角色信息已更新");
      } else {
        await api("/api/roles", {
          method: "POST",
          body: JSON.stringify({
            code,
            name,
            description: description || null,
            data_scope: nextScope,
            permission_codes: [],
          }),
        });
        toast("角色已新增，请继续配置权限");
      }
      await reload();
      setEditing(null);
      setFormError("");
    } catch (reason) {
      setFormError(messageOf(reason));
    }
  }

  async function tryDelete(role: RoleRow) {
    if (role.is_builtin) {
      setDeleteReason(`「${role.name}」是系统内置角色，删除会破坏已有的登录与数据范围规则，请勿删除。`);
      return;
    }
    if (role.user_count > 0) {
      setDeleteReason(`「${role.name}」仍关联 ${role.user_count} 个用户，请先迁移这些用户后再删除。`);
      return;
    }
    try {
      await api(`/api/roles/${role.id}`, { method: "DELETE" });
      await reload();
      toast("角色已删除");
    } catch (reason) {
      setDeleteReason(messageOf(reason));
    }
  }

  async function savePermissions() {
    if (!permRole) return;
    try {
      await api(`/api/roles/${permRole.id}`, {
        method: "PATCH",
        body: JSON.stringify({ permission_codes: selected, data_scope: scope }),
      });
      await reload();
      toast(`「${permRole.name}」的权限已保存`);
      setPermRole(null);
    } catch (reason) {
      setFormError(messageOf(reason));
    }
  }

  if (phase === "boot") {
    return <div className="grid min-h-[320px] place-items-center text-sm text-zinc-400">正在加载角色</div>;
  }
  if (phase === "auth") return <ApiConnect title="角色管理" />;

  const draft = editing && editing !== "new" ? editing : null;

  return (
    <div className="mx-auto max-w-[1180px] space-y-4 p-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-[19px] font-semibold tracking-tight text-zinc-900">角色管理</h1>
          <p className="mt-1 text-[12px] text-zinc-500">维护角色、数据范围与功能权限，控制各账号登录后可见的功能</p>
        </div>
        <button type="button" className="flex items-center gap-1.5 rounded-md bg-zinc-900 px-3.5 py-2 text-[12px] font-medium text-white transition hover:bg-zinc-800" onClick={() => { setFormError(""); setEditing("new"); }}>
          <Plus className="size-3.5" />新增角色
        </button>
      </div>

      {loadError ? <p className="rounded-md bg-rose-50 px-3 py-2 text-[12px] text-rose-700">{loadError}</p> : null}

      <div className="rounded-lg border border-zinc-200 bg-white">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-zinc-100 px-4 py-3">
          <div className="flex items-center gap-2">
            <h2 className="text-[13px] font-semibold text-zinc-800">角色列表</h2>
            <span className="rounded-full bg-zinc-100 px-2 py-0.5 text-[10px] text-zinc-500">{roles.filter((role) => role.is_builtin).length} 个内置角色</span>
          </div>
          <div className="flex items-center gap-2 rounded-md border border-zinc-200 px-2.5 py-1.5">
            <Search className="size-3.5 text-zinc-400" />
            <input className="w-44 border-0 bg-transparent p-0 text-[12px] outline-none placeholder:text-zinc-400" placeholder="搜索角色名称 / 编码" value={keyword} onChange={(event) => setKeyword(event.target.value)} />
          </div>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[900px] border-collapse text-left">
            <thead>
              <tr className="border-b border-zinc-100 bg-zinc-50/60 text-[11px] text-zinc-500">
                {["角色名称", "角色编码", "数据范围", "关联用户数", "权限数", "更新时间"].map((head) => <th key={head} className="px-4 py-2.5 font-medium">{head}</th>)}
                <th className="px-4 py-2.5 text-right font-medium">操作</th>
              </tr>
            </thead>
            <tbody className="text-[12px] text-zinc-700">
              {visible.length ? visible.map((role) => (
                <tr key={role.id} className="border-b border-zinc-50 last:border-0 hover:bg-zinc-50/60">
                  <td className="px-4 py-3"><div className="flex items-center gap-2"><span className="font-medium text-zinc-900">{role.name}</span>{role.is_builtin ? <span className="rounded border border-zinc-200 px-1.5 py-0.5 text-[9px] text-zinc-500">内置</span> : null}</div></td>
                  <td className="px-4 py-3 font-mono text-[11px] text-zinc-500">{role.code}</td>
                  <td className="px-4 py-3"><span className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${scopeBadge(role.data_scope)}`}>{scopeLabel(role.data_scope)}</span></td>
                  <td className="px-4 py-3 text-zinc-600">{role.user_count} 人</td>
                  <td className="px-4 py-3 text-zinc-600">{role.permission_codes.length}</td>
                  <td className="px-4 py-3 text-[11px] text-zinc-500">{formatTime(role.updated_at)}</td>
                  <td className="px-4 py-3">
                    <div className="flex items-center justify-end gap-1">
                      <button type="button" className="rounded px-1.5 py-1 text-[11px] text-zinc-600 hover:bg-zinc-100" onClick={() => { setFormError(""); setEditing(role); }}>编辑</button>
                      <button type="button" className="rounded px-1.5 py-1 text-[11px] text-blue-600 hover:bg-blue-50" onClick={() => openPerm(role)}>配置权限</button>
                      <button type="button" className={`rounded px-1.5 py-1 text-[11px] ${role.is_builtin ? "text-zinc-400" : "text-rose-600 hover:bg-rose-50"}`} onClick={() => void tryDelete(role)}>删除</button>
                    </div>
                  </td>
                </tr>
              )) : <tr><td colSpan={7} className="px-4 py-10 text-center text-[12px] text-zinc-400">未找到匹配的角色</td></tr>}
            </tbody>
          </table>
        </div>
      </div>

      <div className="rounded-lg border border-zinc-200 bg-white">
        <div className="border-b border-zinc-100 px-4 py-3">
          <h2 className="text-[13px] font-semibold text-zinc-800">内置角色权限差异</h2>
          <p className="mt-1 text-[11px] text-zinc-400">按当前权限配置生成。信息中心管理员的权限由系统固定，不能在此修改。</p>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[880px] border-collapse text-left text-[12px]">
            <thead>
              <tr className="border-b border-zinc-100 bg-zinc-50/60 text-[11px] text-zinc-500">
                <th className="px-4 py-2.5 font-medium">能力项</th>
                {builtinRoles.map((role) => <th key={role.id} className="px-4 py-2.5 font-medium">{role.name}</th>)}
              </tr>
            </thead>
            <tbody className="text-zinc-600">
              <tr className="border-b border-zinc-50">
                <td className="px-4 py-2.5 font-medium text-zinc-800">数据范围</td>
                {builtinRoles.map((role) => (
                  <td key={role.id} className="px-4 py-2.5"><span className={`rounded px-1.5 py-0.5 text-[10px] ${scopeBadge(role.data_scope)}`}>{scopeLabel(role.data_scope)}</span></td>
                ))}
              </tr>
              {modules.map(([module, items], index) => (
                <tr key={module} className={index % 2 ? "border-b border-zinc-50 bg-zinc-50/30" : "border-b border-zinc-50"}>
                  <td className="px-4 py-2.5 font-medium text-zinc-800">{module}</td>
                  {builtinRoles.map((role) => {
                    const names = items.filter((item) => role.permission_codes.includes(item.code)).map((item) => item.name);
                    return <td key={role.id} className="px-4 py-2.5">{names.length ? names.join("、") : <span className="text-zinc-400">—</span>}</td>;
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {editing ? (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-zinc-900/40 p-4">
          <form className="w-full max-w-md rounded-xl border border-zinc-200 bg-white shadow-xl" onSubmit={(event) => { event.preventDefault(); void saveRole(new FormData(event.currentTarget)); }}>
            <div className="flex items-center justify-between border-b border-zinc-100 px-5 py-3.5">
              <h3 className="text-[14px] font-semibold text-zinc-900">{editing === "new" ? "新增角色" : "编辑角色"}</h3>
              <button type="button" className="flex h-7 w-7 items-center justify-center rounded-md text-zinc-400 hover:bg-zinc-100" onClick={() => setEditing(null)} aria-label="关闭"><X className="size-3.5" /></button>
            </div>
            <div className="space-y-3 px-5 py-4">
              <label className="block"><span className="mb-1 block text-[11px] text-zinc-500">角色名称 <span className="text-rose-500">*</span></span><input name="name" className={fieldClass} placeholder="如 院系填报审核员" defaultValue={draft?.name ?? ""} /></label>
              <label className="block"><span className="mb-1 block text-[11px] text-zinc-500">角色编码 <span className="text-rose-500">*</span></span><input name="code" className={`${fieldClass} font-mono`} placeholder="如 dept_reviewer" defaultValue={draft?.code ?? ""} readOnly={Boolean(draft)} /></label>
              <label className="block"><span className="mb-1 block text-[11px] text-zinc-500">数据范围</span>
                <select name="scope" className={fieldClass} defaultValue={draft?.data_scope ?? "department"}>
                  {scopeOptions.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
                </select>
              </label>
              <label className="block"><span className="mb-1 block text-[11px] text-zinc-500">说明</span><input name="description" className={fieldClass} defaultValue={draft?.description ?? ""} /></label>
              <p className="rounded-md bg-zinc-50 px-3 py-2 text-[11px] leading-relaxed text-zinc-500">编码创建后不可修改。保存后可继续在「配置权限」中勾选功能权限。</p>
              {formError ? <p className="text-[11px] text-rose-600">{formError}</p> : null}
            </div>
            <div className="flex items-center justify-end gap-2 border-t border-zinc-100 px-5 py-3">
              <button type="button" className="rounded-md border border-zinc-200 px-3.5 py-2 text-[12px] text-zinc-600 hover:bg-zinc-50" onClick={() => setEditing(null)}>取消</button>
              <button type="submit" className="rounded-md bg-zinc-900 px-3.5 py-2 text-[12px] font-medium text-white hover:bg-zinc-800">保存</button>
            </div>
          </form>
        </div>
      ) : null}

      {permRole ? (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-zinc-900/40 p-4">
          <div className="flex max-h-[86vh] w-full max-w-2xl flex-col rounded-xl border border-zinc-200 bg-white shadow-xl">
            <div className="flex flex-none items-center justify-between border-b border-zinc-100 px-5 py-3.5">
              <div>
                <h3 className="text-[14px] font-semibold text-zinc-900">配置功能权限</h3>
                <p className="mt-0.5 text-[11px] text-zinc-400">{permRole.name}（{permRole.code}）· 数据范围：{scopeLabel(scope)}</p>
              </div>
              <button type="button" className="flex h-7 w-7 items-center justify-center rounded-md text-zinc-400 hover:bg-zinc-100" onClick={() => setPermRole(null)} aria-label="关闭"><X className="size-3.5" /></button>
            </div>
            <div className="flex-1 space-y-4 overflow-y-auto px-5 py-4">
              {modules.map(([module, items]) => (
                <div key={module}>
                  <p className="mb-2 text-[11px] font-semibold tracking-wide text-zinc-500">{module}</p>
                  <div className="grid grid-cols-1 gap-1.5 sm:grid-cols-2">
                    {items.map((item) => (
                      <label key={item.code} className="flex items-center gap-2 rounded-md border border-zinc-200 px-2.5 py-2 text-[11px] text-zinc-600">
                        <input
                          type="checkbox"
                          className="h-3.5 w-3.5 accent-zinc-900"
                          checked={selected.includes(item.code)}
                          disabled={permRole.code === "admin"}
                          onChange={() => setSelected((current) => current.includes(item.code) ? current.filter((code) => code !== item.code) : [...current, item.code])}
                        />
                        <span>{item.name}</span>
                      </label>
                    ))}
                  </div>
                </div>
              ))}
              <div>
                <p className="mb-2 text-[11px] font-semibold tracking-wide text-zinc-500">数据范围</p>
                <div className="flex flex-wrap gap-2">
                  {scopeOptions.map((item) => (
                    <label key={item.value} className="flex items-center gap-2 rounded-md border border-zinc-200 px-3 py-2 text-[11px] text-zinc-600">
                      <input type="radio" name="permScope" className="h-3.5 w-3.5 accent-zinc-900" checked={scope === item.value} disabled={permRole.code === "admin"} onChange={() => setScope(item.value)} />
                      <span>{item.label}</span>
                    </label>
                  ))}
                </div>
              </div>
              {permRole.code === "admin" ? <p className="rounded-md bg-amber-50 px-3 py-2 text-[11px] leading-relaxed text-amber-700">信息中心管理员的权限由系统固定，不能在此修改。</p> : null}
              {formError ? <p className="text-[11px] text-rose-600">{formError}</p> : null}
            </div>
            <div className="flex flex-none items-center justify-end gap-2 border-t border-zinc-100 px-5 py-3">
              <button type="button" className="rounded-md border border-zinc-200 px-3.5 py-2 text-[12px] text-zinc-600 hover:bg-zinc-50" onClick={() => setPermRole(null)}>取消</button>
              <button type="button" className="rounded-md bg-zinc-900 px-3.5 py-2 text-[12px] font-medium text-white hover:bg-zinc-800 disabled:opacity-40" disabled={permRole.code === "admin"} onClick={() => void savePermissions()}>保存权限</button>
            </div>
          </div>
        </div>
      ) : null}

      {deleteReason ? (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-zinc-900/40 p-4">
          <div className="w-full max-w-sm rounded-xl border border-zinc-200 bg-white p-5 shadow-xl">
            <div className="flex items-start gap-3">
              <div className="flex h-9 w-9 flex-none items-center justify-center rounded-full bg-rose-50 text-rose-600"><ShieldAlert className="size-4" /></div>
              <div>
                <h3 className="text-[13px] font-semibold text-zinc-900">无法删除该角色</h3>
                <p className="mt-1 text-[11px] leading-relaxed text-zinc-500">{deleteReason}</p>
              </div>
            </div>
            <div className="mt-4 flex justify-end">
              <button type="button" className="rounded-md bg-zinc-900 px-3.5 py-2 text-[12px] font-medium text-white hover:bg-zinc-800" onClick={() => setDeleteReason("")}>我知道了</button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
