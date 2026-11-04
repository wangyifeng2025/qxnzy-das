"use client";

import { BookOpen, Info, Plus, Search, Trash2, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { FormCombobox } from "@/components/form-combobox";
import { useToast } from "@/components/toast";
import { ApiError, api, loginRequest } from "@/lib/api";
import { readToken, sessionFromAuth, writeSession, writeToken } from "@/lib/session";

type DictType = {
  code: string;
  name: string;
  applies_to: string | null;
  remark: string | null;
  item_count: number;
};

type DictItem = {
  id: number;
  value: string | null;
  label: string;
  remark: string | null;
  sort_order: number;
  is_active: boolean;
};

type DictDetail = DictType & { items: DictItem[] };

const fieldClass = "w-full rounded-md border border-zinc-200 px-2.5 py-2 text-[12px] outline-none focus:border-zinc-400";

function messageOf(error: unknown) {
  return error instanceof ApiError ? error.message : "请求失败";
}

function nextDictCode(types: DictType[]) {
  let max = 0;
  for (const item of types) {
    const match = /^D(\d+)$/i.exec(item.code);
    if (match) max = Math.max(max, Number(match[1]));
  }
  return `D${String(max + 1).padStart(2, "0")}`;
}

export default function DictsPage() {
  const toast = useToast();
  const [phase, setPhase] = useState<"boot" | "auth" | "ready">("boot");
  const [types, setTypes] = useState<DictType[]>([]);
  const [active, setActive] = useState("");
  const [items, setItems] = useState<DictItem[]>([]);
  const [keyword, setKeyword] = useState("");
  const [editing, setEditing] = useState<DictItem | "new" | null>(null);
  const [creatingType, setCreatingType] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<DictItem | null>(null);
  const [pendingType, setPendingType] = useState<DictType | null>(null);
  const [formError, setFormError] = useState("");
  const [account, setAccount] = useState("admin");
  const [password, setPassword] = useState("");
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
    api<DictType[]>("/api/dicts")
      .then((rows) => {
        if (cancelled) return;
        setTypes(rows);
        setActive((current) => rows.find((item) => item.code === current)?.code ?? rows[0]?.code ?? "");
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

  useEffect(() => {
    if (phase !== "ready" || !active) return;
    let cancelled = false;
    api<DictDetail>(`/api/dicts/${active}?include_inactive=true`)
      .then((row) => {
        if (cancelled) return;
        setItems(row.items);
        setTypes((current) =>
          current.map((item) => (item.code === row.code ? { ...item, item_count: row.items.length, name: row.name, applies_to: row.applies_to, remark: row.remark } : item)),
        );
      })
      .catch((reason: unknown) => {
        if (!cancelled) toast(messageOf(reason));
      });
    return () => {
      cancelled = true;
    };
  }, [phase, active, toast]);

  const category = types.find((item) => item.code === active);
  const suggestedCode = useMemo(() => nextDictCode(types), [types]);
  const visibleItems = useMemo(() => {
    const needle = keyword.trim().toLowerCase();
    return items.filter((item) => !needle || `${item.value ?? ""}${item.label}`.toLowerCase().includes(needle));
  }, [items, keyword]);

  async function loadTypes(selectCode?: string) {
    const rows = await api<DictType[]>("/api/dicts");
    setTypes(rows);
    setActive((current) => {
      const preferred = selectCode ?? current;
      return rows.find((item) => item.code === preferred)?.code ?? rows[0]?.code ?? "";
    });
    if (!rows.length) setItems([]);
    return rows;
  }

  async function reloadActive() {
    if (!active) return;
    const row = await api<DictDetail>(`/api/dicts/${active}?include_inactive=true`);
    setItems(row.items);
    setTypes((current) => current.map((item) => (item.code === row.code ? { ...item, item_count: row.items.length } : item)));
  }

  async function connect(event: React.FormEvent) {
    event.preventDefault();
    setFormError("");
    try {
      const result = await loginRequest(account.trim(), password);
      writeToken(result.access_token);
      writeSession(sessionFromAuth(result.user));
      toast("已连接后端，可以维护数据字典");
      window.location.reload();
    } catch (reason) {
      setFormError(messageOf(reason));
    }
  }

  async function saveItem(form: FormData) {
    if (!category) return;
    const label = String(form.get("label") ?? "").trim();
    const value = String(form.get("value") ?? "").trim();
    if (!label) {
      setFormError("请填写字典名称");
      return;
    }
    const body = {
      value: value || null,
      label,
      sort_order: Number(form.get("sort") ?? 0) || 0,
      is_active: String(form.get("status") ?? "active") === "active",
      remark: String(form.get("remark") ?? "").trim() || null,
    };
    try {
      if (editing && editing !== "new") {
        await api(`/api/dicts/${category.code}/items/${editing.id}`, { method: "PATCH", body: JSON.stringify(body) });
        toast("字典项已更新，填报表单下拉已同步");
      } else {
        await api(`/api/dicts/${category.code}/items`, { method: "POST", body: JSON.stringify(body) });
        toast("字典项已新增，填报表单下拉已同步");
      }
      setEditing(null);
      setFormError("");
      await reloadActive();
    } catch (reason) {
      setFormError(messageOf(reason));
    }
  }

  async function toggleItem(item: DictItem) {
    if (!category) return;
    try {
      await api(`/api/dicts/${category.code}/items/${item.id}`, {
        method: "PATCH",
        body: JSON.stringify({ is_active: !item.is_active }),
      });
      toast(`「${item.label}」已${item.is_active ? "停用" : "启用"}`);
      await reloadActive();
    } catch (reason) {
      toast(messageOf(reason));
    }
  }

  async function saveType(form: FormData) {
    const code = String(form.get("code") ?? "").trim().toUpperCase();
    const name = String(form.get("name") ?? "").trim();
    if (!/^[A-Za-z][A-Za-z0-9_-]{0,9}$/.test(code)) {
      setFormError("分类编号需以字母开头，最长 10 位，只能包含字母、数字、下划线或连字符");
      return;
    }
    if (!name) {
      setFormError("请填写分类名称");
      return;
    }
    try {
      await api("/api/dicts", {
        method: "POST",
        body: JSON.stringify({
          code,
          name,
          applies_to: String(form.get("applies_to") ?? "").trim() || null,
          remark: String(form.get("remark") ?? "").trim() || null,
        }),
      });
      setCreatingType(false);
      setFormError("");
      toast("字典分类已新增");
      await loadTypes(code);
    } catch (reason) {
      setFormError(messageOf(reason));
    }
  }

  async function confirmDelete() {
    if (!category || !pendingDelete) return;
    try {
      await api(`/api/dicts/${category.code}/items/${pendingDelete.id}`, { method: "DELETE" });
      setPendingDelete(null);
      toast("字典项已删除");
      await reloadActive();
    } catch (reason) {
      toast(messageOf(reason));
    }
  }

  async function confirmDeleteType() {
    if (!pendingType) return;
    const removed = pendingType;
    const index = types.findIndex((item) => item.code === removed.code);
    try {
      await api(`/api/dicts/${removed.code}`, { method: "DELETE" });
      setPendingType(null);
      toast(`已删除字典分类「${removed.name}」`);
      const rows = await api<DictType[]>("/api/dicts");
      setTypes(rows);
      const keepCurrent = active !== removed.code && rows.some((item) => item.code === active);
      const neighbor = rows[Math.min(Math.max(index, 0), Math.max(rows.length - 1, 0))];
      const next = keepCurrent ? active : (neighbor?.code ?? "");
      setActive(next);
      if (!next) setItems([]);
    } catch (reason) {
      toast(messageOf(reason));
    }
  }

  if (phase === "boot") {
    return <div className="grid min-h-[320px] place-items-center text-sm text-zinc-400">正在加载字典</div>;
  }

  if (phase === "auth") {
    return (
      <div className="mx-auto max-w-md p-5">
        <h1 className="text-[19px] font-semibold tracking-tight">字典管理</h1>
        <form className="mt-4 rounded-xl border border-zinc-200 bg-white p-5" onSubmit={(event) => void connect(event)}>
          <p className="text-[12px] leading-relaxed text-zinc-500">当前浏览器没有后端登录令牌。使用管理员账号 admin，初始密码 Admin@2026。</p>
          <label className="mt-4 block text-[11px] text-zinc-500">账号<input className={`${fieldClass} mt-1`} value={account} onChange={(event) => setAccount(event.target.value)} /></label>
          <label className="mt-3 block text-[11px] text-zinc-500">密码<input type="password" className={`${fieldClass} mt-1`} value={password} onChange={(event) => setPassword(event.target.value)} /></label>
          {formError ? <p className="mt-3 text-[11px] text-rose-600">{formError}</p> : null}
          <button type="submit" className="mt-4 rounded-md bg-zinc-900 px-3.5 py-2 text-[12px] font-medium text-white">连接并进入字典</button>
        </form>
      </div>
    );
  }

  return (
    <div className="absolute inset-0 flex flex-col gap-4 overflow-hidden p-5">
      <div className="flex shrink-0 flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-[19px] font-semibold tracking-tight text-zinc-900">字典管理</h1>
          <p className="mt-1 text-[12px] text-zinc-500">维护填报表单使用的标准下拉字典，保证各角色填报口径一致</p>
        </div>
        <div className="flex items-center gap-2 rounded-md border border-blue-100 bg-blue-50 px-3 py-2 text-[11px] text-blue-700">
          <Info className="size-3.5" />
          字典项供填报表单下拉使用，停用后不再出现在新表单中
        </div>
      </div>
      {loadError ? <p className="shrink-0 rounded-md bg-rose-50 px-3 py-2 text-[12px] text-rose-700">{loadError}</p> : null}
      <div className="grid min-h-0 flex-1 grid-cols-1 grid-rows-[minmax(0,11.5rem)_minmax(0,1fr)] gap-4 lg:grid-cols-[250px_minmax(0,1fr)] lg:grid-rows-1">
        <div className="flex min-h-0 flex-col overflow-hidden rounded-lg border border-zinc-200 bg-white">
          <div className="flex shrink-0 items-center justify-between border-b border-zinc-100 px-3.5 py-3">
            <h2 className="text-[13px] font-semibold text-zinc-800">字典分类</h2>
            <span className="text-[10px] text-zinc-400">{types.length} 类</span>
          </div>
          <div className="min-h-0 flex-1 space-y-0.5 overflow-y-auto p-2">
            {types.map((item) => {
              const selected = item.code === active;
              return (
                <div key={item.code} className={`group flex items-center gap-1 rounded-md pr-1 transition ${selected ? "bg-zinc-100 text-zinc-900" : "text-zinc-600 hover:bg-zinc-50"}`}>
                  <button
                    type="button"
                    onClick={() => { setActive(item.code); setKeyword(""); }}
                    className="flex min-w-0 flex-1 items-center gap-2.5 px-2.5 py-2 text-left"
                  >
                    <BookOpen className={`size-3.5 shrink-0 ${selected ? "text-zinc-700" : "text-zinc-400"}`} />
                    <span className={`min-w-0 flex-1 truncate text-[12px] ${selected ? "font-medium" : ""}`}>{item.code} {item.name}</span>
                    <span className={`rounded bg-white px-1.5 py-0.5 text-[9px] text-zinc-500 ${selected ? "border border-zinc-200" : ""}`}>{item.item_count}</span>
                  </button>
                  <button
                    type="button"
                    aria-label={`删除${item.name}`}
                    title="删除分类"
                    className={`rounded p-1 text-zinc-400 transition hover:bg-rose-50 hover:text-rose-600 ${selected ? "opacity-100" : "opacity-0 group-hover:opacity-100 focus:opacity-100"}`}
                    onClick={() => setPendingType(item)}
                  >
                    <Trash2 className="size-3.5" />
                  </button>
                </div>
              );
            })}
          </div>
          <div className="shrink-0 border-t border-zinc-100 p-3">
            <button type="button" className="flex w-full items-center justify-center gap-1.5 rounded-md border border-dashed border-zinc-300 py-2 text-[11px] text-zinc-500 transition hover:bg-zinc-50" onClick={() => { setFormError(""); setCreatingType(true); }}>
              <Plus className="size-3.5" />新增字典分类
            </button>
          </div>
        </div>

        <div className="flex min-h-0 min-w-0 flex-col overflow-hidden rounded-lg border border-zinc-200 bg-white">
          <div className="flex shrink-0 flex-wrap items-center justify-between gap-2 border-b border-zinc-100 px-4 py-3">
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-[13px] font-semibold text-zinc-800">{category?.name ?? "字典"}</h2>
                <span className="rounded border border-zinc-200 px-1.5 py-0.5 font-mono text-[10px] text-zinc-500">{category?.code ?? ""}</span>
              </div>
              <p className="mt-1 text-[11px] text-zinc-400">{category?.applies_to || category?.remark || "填报表单下拉使用"}</p>
            </div>
            <div className="flex items-center gap-2">
              <div className="flex items-center gap-2 rounded-md border border-zinc-200 px-2.5 py-1.5">
                <Search className="size-3.5 text-zinc-400" />
                <input className="w-40 border-0 bg-transparent p-0 text-[12px] outline-none placeholder:text-zinc-400" placeholder="搜索字典名称 / 编码" value={keyword} onChange={(event) => setKeyword(event.target.value)} />
              </div>
              {category ? (
                <button type="button" className="rounded-md border border-rose-200 px-3 py-2 text-[11px] text-rose-600 transition hover:bg-rose-50" onClick={() => setPendingType(category)}>
                  删除分类
                </button>
              ) : null}
              <button type="button" className="flex items-center gap-1.5 rounded-md bg-zinc-900 px-3 py-2 text-[11px] font-medium text-white transition hover:bg-zinc-800" onClick={() => { setFormError(""); setEditing("new"); }} disabled={!category}>
                <Plus className="size-3.5" />新增字典项
              </button>
            </div>
          </div>
          <div className="min-h-0 flex-1 overflow-auto">
            <table className="w-full border-collapse text-left">
              <thead className="sticky top-0 z-10">
                <tr className="border-b border-zinc-100 bg-zinc-50 text-[11px] text-zinc-500">
                  {["字典编码", "字典名称", "排序", "状态", "备注"].map((head) => <th key={head} className="px-4 py-2.5 font-medium">{head}</th>)}
                  <th className="px-4 py-2.5 text-right font-medium">操作</th>
                </tr>
              </thead>
              <tbody className="text-[12px] text-zinc-700">
                {visibleItems.length ? visibleItems.map((item) => (
                  <tr key={item.id} className="border-b border-zinc-50 last:border-0 hover:bg-zinc-50/60">
                    <td className="px-4 py-2.5 font-mono text-[11px] text-zinc-500">{item.value || "—"}</td>
                    <td className="px-4 py-2.5 font-medium text-zinc-900">{item.label}</td>
                    <td className="px-4 py-2.5 text-zinc-500">{item.sort_order}</td>
                    <td className="px-4 py-2.5">
                      {item.is_active ? (
                        <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-0.5 text-[10px] font-medium text-emerald-700"><span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />启用</span>
                      ) : (
                        <span className="inline-flex items-center gap-1 rounded-full bg-zinc-100 px-2 py-0.5 text-[10px] font-medium text-zinc-500"><span className="h-1.5 w-1.5 rounded-full bg-zinc-400" />停用</span>
                      )}
                    </td>
                    <td className="px-4 py-2.5 text-[11px] text-zinc-500">{item.remark || "—"}</td>
                    <td className="px-4 py-2.5">
                      <div className="flex items-center justify-end gap-1">
                        <button type="button" className="rounded px-1.5 py-1 text-[11px] text-zinc-600 transition hover:bg-zinc-100" onClick={() => { setFormError(""); setEditing(item); }}>编辑</button>
                        <button type="button" className={`rounded px-1.5 py-1 text-[11px] ${item.is_active ? "text-amber-600 hover:bg-amber-50" : "text-emerald-600 hover:bg-emerald-50"}`} onClick={() => void toggleItem(item)}>{item.is_active ? "停用" : "启用"}</button>
                        <button type="button" className="rounded px-1.5 py-1 text-[11px] text-rose-600 transition hover:bg-rose-50" onClick={() => setPendingDelete(item)}>删除</button>
                      </div>
                    </td>
                  </tr>
                )) : <tr><td colSpan={6} className="px-4 py-10 text-center text-[12px] text-zinc-400">该分类暂无字典项</td></tr>}
              </tbody>
            </table>
          </div>
          <div className="flex shrink-0 flex-wrap items-center justify-between gap-2 border-t border-zinc-100 px-4 py-3">
            <p className="text-[11px] text-zinc-400">{category?.name ?? "字典"} · 共 {items.length} 项，当前显示 {visibleItems.length} 项</p>
            <div className="flex items-center gap-3 text-[10px] text-zinc-400">
              <span className="flex items-center gap-1"><span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />启用中：下拉可见</span>
              <span className="flex items-center gap-1"><span className="h-1.5 w-1.5 rounded-full bg-zinc-400" />已停用：历史数据保留</span>
            </div>
          </div>
        </div>
      </div>

      {creatingType ? (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-zinc-900/40 p-4">
          <form className="w-full max-w-md rounded-xl border border-zinc-200 bg-white shadow-xl" onSubmit={(event) => { event.preventDefault(); void saveType(new FormData(event.currentTarget)); }}>
            <div className="flex items-center justify-between border-b border-zinc-100 px-5 py-3.5">
              <h3 className="text-[14px] font-semibold text-zinc-900">新增字典分类</h3>
              <button type="button" className="flex h-7 w-7 items-center justify-center rounded-md text-zinc-400 hover:bg-zinc-100" onClick={() => setCreatingType(false)} aria-label="关闭"><X className="size-3.5" /></button>
            </div>
            <div className="space-y-3 px-5 py-4">
              <div className="grid grid-cols-2 gap-3">
                <label className="block"><span className="mb-1 block text-[11px] text-zinc-500">分类编号 <span className="text-rose-500">*</span></span><input name="code" className={`${fieldClass} font-mono`} defaultValue={suggestedCode} /></label>
                <label className="block"><span className="mb-1 block text-[11px] text-zinc-500">分类名称 <span className="text-rose-500">*</span></span><input name="name" className={fieldClass} placeholder="如 专业层次" /></label>
              </div>
              <label className="block"><span className="mb-1 block text-[11px] text-zinc-500">适用数据表</span><input name="applies_to" className={fieldClass} placeholder="选填，如 ODS_ZYSZSJ" /></label>
              <label className="block"><span className="mb-1 block text-[11px] text-zinc-500">备注</span><input name="remark" className={fieldClass} placeholder="说明该分类的用途" /></label>
              {formError ? <p className="text-[11px] text-rose-600">{formError}</p> : null}
            </div>
            <div className="flex items-center justify-end gap-2 border-t border-zinc-100 px-5 py-3">
              <button type="button" className="rounded-md border border-zinc-200 px-3.5 py-2 text-[12px] text-zinc-600 hover:bg-zinc-50" onClick={() => setCreatingType(false)}>取消</button>
              <button type="submit" className="rounded-md bg-zinc-900 px-3.5 py-2 text-[12px] font-medium text-white hover:bg-zinc-800">保存</button>
            </div>
          </form>
        </div>
      ) : null}

      {editing ? (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-zinc-900/40 p-4">
          <form className="w-full max-w-md rounded-xl border border-zinc-200 bg-white shadow-xl" onSubmit={(event) => { event.preventDefault(); void saveItem(new FormData(event.currentTarget)); }}>
            <div className="flex items-center justify-between border-b border-zinc-100 px-5 py-3.5">
              <h3 className="text-[14px] font-semibold text-zinc-900">{editing === "new" ? "新增字典项" : "编辑字典项"}</h3>
              <button type="button" className="flex h-7 w-7 items-center justify-center rounded-md text-zinc-400 hover:bg-zinc-100" onClick={() => setEditing(null)} aria-label="关闭"><X className="size-3.5" /></button>
            </div>
            <div className="space-y-3 px-5 py-4">
              <p className="rounded-md bg-zinc-50 px-3 py-2 text-[11px] text-zinc-500">所属分类：{category?.name}（{category?.code}）</p>
              <div className="grid grid-cols-2 gap-3">
                <label className="block"><span className="mb-1 block text-[11px] text-zinc-500">字典编码</span><input name="value" className={`${fieldClass} font-mono`} placeholder="国标代码，校本字典可留空" defaultValue={editing === "new" ? "" : (editing.value ?? "")} /></label>
                <label className="block"><span className="mb-1 block text-[11px] text-zinc-500">排序</span><input name="sort" type="number" className={fieldClass} defaultValue={editing === "new" ? items.length + 1 : editing.sort_order} /></label>
              </div>
              <label className="block"><span className="mb-1 block text-[11px] text-zinc-500">字典名称 <span className="text-rose-500">*</span></span><input name="label" className={fieldClass} placeholder="下拉中显示的文本" defaultValue={editing === "new" ? "" : editing.label} /></label>
              <label className="block"><span className="mb-1 block text-[11px] text-zinc-500">状态</span>
                <FormCombobox
                  name="status"
                  placeholder="请选择状态"
                  defaultValue={editing !== "new" && !editing.is_active ? "disabled" : "active"}
                  options={[
                    { value: "active", label: "启用" },
                    { value: "disabled", label: "停用" },
                  ]}
                />
              </label>
              <label className="block"><span className="mb-1 block text-[11px] text-zinc-500">备注</span><input name="remark" className={fieldClass} placeholder="说明该字典项适用范围" defaultValue={editing === "new" ? "" : (editing.remark ?? "")} /></label>
              {formError ? <p className="text-[11px] text-rose-600">{formError}</p> : null}
            </div>
            <div className="flex items-center justify-end gap-2 border-t border-zinc-100 px-5 py-3">
              <button type="button" className="rounded-md border border-zinc-200 px-3.5 py-2 text-[12px] text-zinc-600 hover:bg-zinc-50" onClick={() => setEditing(null)}>取消</button>
              <button type="submit" className="rounded-md bg-zinc-900 px-3.5 py-2 text-[12px] font-medium text-white hover:bg-zinc-800">保存</button>
            </div>
          </form>
        </div>
      ) : null}

      {pendingType ? (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-zinc-900/40 p-4">
          <div className="w-full max-w-sm rounded-xl border border-zinc-200 bg-white p-5 shadow-xl">
            <h3 className="text-[13px] font-semibold text-zinc-900">确认删除字典分类？</h3>
            <p className="mt-1.5 text-[11px] leading-relaxed text-zinc-500">
              将删除「{pendingType.name}」（{pendingType.code}）
              {pendingType.item_count ? `及其 ${pendingType.item_count} 个字典项` : ""}。删除后不能恢复，已提交的历史数据保持不变。
            </p>
            <div className="mt-4 flex justify-end gap-2">
              <button type="button" className="rounded-md border border-zinc-200 px-3.5 py-2 text-[12px] text-zinc-600 hover:bg-zinc-50" onClick={() => setPendingType(null)}>取消</button>
              <button type="button" className="rounded-md bg-rose-600 px-3.5 py-2 text-[12px] font-medium text-white hover:bg-rose-700" onClick={() => void confirmDeleteType()}>删除</button>
            </div>
          </div>
        </div>
      ) : null}

      {pendingDelete ? (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-zinc-900/40 p-4">
          <div className="w-full max-w-sm rounded-xl border border-zinc-200 bg-white p-5 shadow-xl">
            <h3 className="text-[13px] font-semibold text-zinc-900">确认删除字典项？</h3>
            <p className="mt-1.5 text-[11px] leading-relaxed text-zinc-500">将删除「{pendingDelete.label}」，删除后新表单下拉将不再包含该项，已提交的历史数据保持不变。</p>
            <div className="mt-4 flex justify-end gap-2">
              <button type="button" className="rounded-md border border-zinc-200 px-3.5 py-2 text-[12px] text-zinc-600 hover:bg-zinc-50" onClick={() => setPendingDelete(null)}>取消</button>
              <button type="button" className="rounded-md bg-rose-600 px-3.5 py-2 text-[12px] font-medium text-white hover:bg-rose-700" onClick={() => void confirmDelete()}>删除</button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
