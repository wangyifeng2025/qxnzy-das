"use client";

import { Bell, ChevronRight, ChevronsUpDown, Database, LogOut, School, Search } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { ToastProvider, useToast } from "@/components/toast";
import { navigationFor, ROUTE_ACCESS, ROUTE_TITLE } from "@/lib/navigation";
import { clearSession, readSession, ROLE_HOME, type Role, type SessionUser } from "@/lib/session";

const avatarTone: Record<Role, string> = {
  teacher: "bg-emerald-700",
  staff: "bg-sky-700",
  admin: "bg-zinc-900",
};

function ShellFrame({ user, children }: { user: SessionUser; children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const toast = useToast();
  const groups = navigationFor(user.role);
  const navItems = groups.flatMap((group) => group.items);
  const matched = navItems.filter((item) => item.href === pathname);
  const currentNav = matched.find((item) => !item.label.endsWith("工作台")) ?? matched[0];
  const meta = ROUTE_TITLE[pathname] ?? { crumb: "数据采集", heading: "2025—2026 学年第一学期" };
  const heading =
    pathname === "/my-fill"
      ? user.role === "staff"
        ? "本部门填报跟踪"
        : user.role === "admin"
          ? "全校填报跟踪"
          : "教师个人工作台"
      : pathname === "/review"
        ? user.role === "admin"
          ? "全校审核工作台"
          : `${user.dept} · 部门管理员工作台`
        : meta.heading;
  const allowed = ROUTE_ACCESS[pathname]?.includes(user.role) ?? false;
  const scope =
    user.role === "admin"
      ? "信息中心 · 全校数据范围"
      : user.role === "staff"
        ? `${user.dept} · 本部门数据`
        : `${user.dept} · 个人数据`;

  function logout() {
    clearSession();
    router.replace("/login");
  }

  return (
    <div className="flex h-screen w-full overflow-hidden bg-[#f7f7f8] text-zinc-900">
      <aside className="hidden h-full w-[236px] shrink-0 flex-col border-r border-zinc-200 bg-white lg:flex">
        <div className="flex h-16 items-center gap-3 border-b border-zinc-100 px-5">
          <div className="flex size-9 items-center justify-center rounded-lg bg-zinc-900 text-white">
            <Database className="size-[18px]" aria-hidden="true" />
          </div>
          <div className="min-w-0">
            <p className="text-[9px] font-semibold tracking-[0.14em] text-zinc-400">QIANXINAN VOCATIONAL</p>
            <p className="mt-0.5 text-[15px] font-semibold tracking-tight">数据采集系统</p>
          </div>
        </div>
        <div className="border-b border-zinc-100 px-3.5 py-3">
          <button
            type="button"
            className="flex w-full items-center gap-2 rounded-md border border-zinc-200 bg-white px-2.5 py-2 text-left text-xs text-zinc-700 transition hover:bg-zinc-50"
            onClick={() => toast("当前已选择：黔西南民族职业技术学院")}
          >
            <span className="flex size-6 items-center justify-center rounded bg-emerald-50 text-emerald-700">
              <School className="size-3.5" aria-hidden="true" />
            </span>
            <span className="min-w-0 flex-1">
              <span className="block truncate font-medium">黔西南民族职业技术学院</span>
              <span className="mt-0.5 block text-[10px] text-zinc-400">
                {user.role === "admin" ? "校级数据空间" : user.dept}
              </span>
            </span>
            <ChevronsUpDown className="size-3.5 text-zinc-400" aria-hidden="true" />
          </button>
        </div>
        <nav aria-label="主导航" className="flex-1 space-y-5 overflow-y-auto px-3 py-4">
          {groups.map((group) => (
            <div key={group.title}>
              <p className="px-2.5 pb-2 text-[10px] font-semibold tracking-[0.12em] text-zinc-400">{group.title}</p>
              <div className="space-y-1">
                {group.items.map((item) => {
                  const active = currentNav?.href === item.href && currentNav.label === item.label;
                  const Icon = item.icon;
                  return (
                    <Link
                      key={`${group.title}-${item.label}`}
                      href={item.href}
                      aria-current={active ? "page" : undefined}
                      className={`flex items-center gap-2.5 rounded-md px-2.5 py-2 text-[13px] transition ${
                        active ? "bg-zinc-100 font-medium text-zinc-900" : "text-zinc-600 hover:bg-zinc-50 hover:text-zinc-900"
                      }`}
                    >
                      <Icon className={`size-4 ${active ? "text-zinc-700" : "text-zinc-400"}`} aria-hidden="true" />
                      <span className="flex-1">{item.label}</span>
                      {item.badge ? (
                        <span className={`rounded px-1.5 py-0.5 text-[9px] font-medium ${item.badgeClass ?? "bg-zinc-100 text-zinc-500"}`}>
                          {item.badge}
                        </span>
                      ) : null}
                    </Link>
                  );
                })}
              </div>
            </div>
          ))}
        </nav>
        <div className="m-3 rounded-lg border border-zinc-200 bg-zinc-50 p-3">
          <div className="flex items-center gap-2 text-[11px] font-medium text-zinc-700">
            <span className="size-2 rounded-full bg-emerald-500" />
            同步服务运行正常
          </div>
          <p className="mt-1.5 text-[10px] leading-relaxed text-zinc-400">数据源尚未接入</p>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-16 shrink-0 items-center gap-4 border-b border-zinc-200 bg-white px-4 xl:px-6">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-1.5 text-[11px] text-zinc-400">
              <span>数据采集</span>
              <ChevronRight className="size-3" aria-hidden="true" />
              <span className="text-zinc-700">{meta.crumb}</span>
            </div>
            <p className="mt-0.5 truncate text-[13px] font-semibold text-zinc-900">{heading}</p>
          </div>
          <form
            className="hidden h-9 w-56 items-center gap-2 rounded-md border border-zinc-200 bg-zinc-50/60 px-3 lg:flex xl:w-64"
            onSubmit={(event) => {
              event.preventDefault();
              const data = new FormData(event.currentTarget);
              const query = String(data.get("q") ?? "").trim();
              toast(query ? `已提交检索：${query}` : "请输入检索内容");
            }}
          >
            <Search className="size-3.5 text-zinc-400" aria-hidden="true" />
            <input
              name="q"
              className="w-full bg-transparent text-xs outline-none placeholder:text-zinc-400"
              placeholder="搜索数据表、教师或记录"
            />
            <kbd className="rounded border border-zinc-200 bg-white px-1.5 py-0.5 text-[9px] text-zinc-400">⌘ K</kbd>
          </form>
          <button
            type="button"
            aria-label="通知"
            className="relative flex size-9 items-center justify-center rounded-md border border-zinc-200 bg-white text-zinc-500 transition hover:bg-zinc-50"
            onClick={() => toast("暂无新的系统通知")}
          >
            <Bell className="size-4" aria-hidden="true" />
            <span className="absolute top-2 right-2 size-1.5 rounded-full bg-rose-500 ring-2 ring-white" />
          </button>
          <div className="flex items-center gap-2.5 border-l border-zinc-200 pl-3.5">
            <div className={`flex size-8 items-center justify-center rounded-full text-[11px] font-semibold text-white ${avatarTone[user.role]}`}>
              {user.name.slice(0, 1)}
            </div>
            <div className="hidden xl:block">
              <p className="text-xs leading-tight font-medium text-zinc-800">{user.name}</p>
              <p className="mt-0.5 text-[10px] text-zinc-400">{scope}</p>
            </div>
            <button
              type="button"
              aria-label="退出登录"
              title="退出登录"
              className="ml-1 flex size-8 items-center justify-center rounded-md text-zinc-400 transition hover:bg-zinc-100 hover:text-zinc-700"
              onClick={logout}
            >
              <LogOut className="size-3.5" aria-hidden="true" />
            </button>
          </div>
        </header>

        <nav aria-label="移动导航" className="flex gap-1 overflow-x-auto border-b border-zinc-200 bg-white px-3 py-2 lg:hidden">
          {groups.flatMap((group) => group.items).map((item) => (
            <Link
              key={item.href + item.label}
              href={item.href}
              className={`shrink-0 rounded-md px-2.5 py-1.5 text-[12px] ${
                pathname === item.href ? "bg-zinc-900 text-white" : "bg-zinc-100 text-zinc-600"
              }`}
            >
              {item.label}
            </Link>
          ))}
        </nav>

        <main className="relative min-h-0 flex-1 overflow-y-auto">
          {allowed ? (
            children
          ) : (
            <div className="mx-auto flex max-w-md flex-col items-start px-6 py-20">
              <h1 className="text-[22px] font-semibold tracking-tight">无访问权限</h1>
              <p className="mt-2 text-sm leading-6 text-zinc-500">当前身份不能打开这个页面。请返回自己的工作台，或使用有权限的账号登录。</p>
              <Link href={ROLE_HOME[user.role]} className="mt-6 rounded-md bg-zinc-900 px-4 py-2 text-[12px] font-medium text-white">
                返回我的工作台
              </Link>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}

export function ConsoleShell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [user, setUser] = useState<SessionUser | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const session = readSession();
    if (!session) {
      router.replace("/login");
      return;
    }
    if (pathname === "/home" && session.role !== "admin") {
      router.replace(ROLE_HOME[session.role]);
      return;
    }
    setUser(session);
    setReady(true);
  }, [pathname, router]);

  return (
    <ToastProvider>
      {ready && user ? (
        <ShellFrame user={user}>{children}</ShellFrame>
      ) : (
        <div className="grid h-screen place-items-center bg-[#f7f7f8] text-sm text-zinc-400">
          正在进入工作台
          <div className="hidden">{children}</div>
        </div>
      )}
    </ToastProvider>
  );
}
