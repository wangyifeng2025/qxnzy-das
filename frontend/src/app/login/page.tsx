"use client";

import { ArrowRight, Building2, Database, Eye, EyeOff, Fingerprint, Lock, LogIn, ShieldCheck, UserRound } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { ToastProvider, useToast } from "@/components/toast";
import { ApiError, loginRequest } from "@/lib/api";
import {
  readRememberedAccount,
  readSession,
  ROLE_HOME,
  sessionFromAuth,
  writeRememberedAccount,
  writeSession,
  writeToken,
  type Role,
} from "@/lib/session";

const quickAccounts: { role: Role; account: string; password: string; title: string; hint: string; badge: string; tone: string }[] = [
  { role: "teacher", account: "2024020008", password: "123456", title: "教师", hint: "谭元霸 · 工号 2024020008 · 密码 123456", badge: "本人数据", tone: "bg-emerald-50 text-emerald-700" },
  { role: "staff", account: "2015200012", password: "123456", title: "系部数据管理员", hint: "罗胜 · 工号 2015200012 · 密码 123456", badge: "本部门", tone: "bg-sky-50 text-sky-700" },
  { role: "admin", account: "2004020159", password: "123456", title: "信息中心管理员", hint: "王一锋 · 工号 2004020159 · 密码 123456", badge: "全校", tone: "bg-violet-50 text-violet-700" },
];

function LoginForm() {
  const router = useRouter();
  const toast = useToast();
  const [account, setAccount] = useState("");
  const [password, setPassword] = useState("");
  const [remember, setRemember] = useState(true);
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);

  useEffect(() => {
    const session = readSession();
    if (session) {
      router.replace(ROLE_HOME[session.role]);
      return;
    }
    const remembered = readRememberedAccount();
    if (remembered) {
      queueMicrotask(() => {
        setAccount(remembered);
        setRemember(true);
      });
    }
  }, [router]);

  async function enterWithApi(nextAccount: string, nextPassword: string) {
    const result = await loginRequest(nextAccount, nextPassword);
    writeToken(result.access_token);
    const profile = sessionFromAuth(result.user);
    writeSession(profile);
    toast(`登录成功，正在以「${profile.name}」进入`);
    window.setTimeout(() => router.push(ROLE_HOME[profile.role]), 280);
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    const nextAccount = account.trim();
    if (!nextAccount || !password.trim()) {
      setError("请输入账号与密码后再登录。");
      return;
    }
    setError("");
    setPending(true);
    writeRememberedAccount(remember ? nextAccount : null);
    try {
      await enterWithApi(nextAccount, password);
    } catch (error) {
      setError(error instanceof ApiError ? error.message : "登录失败");
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="flex h-screen w-full overflow-hidden bg-[#f7f7f8] text-zinc-900">
      <aside className="relative hidden h-full w-[44%] shrink-0 flex-col justify-between overflow-hidden border-r border-zinc-200 bg-zinc-950 px-12 py-12 text-white lg:flex xl:px-16">
        <div
          className="pointer-events-none absolute inset-0 opacity-[0.07]"
          style={{
            backgroundImage: "linear-gradient(#fff 1px, transparent 1px), linear-gradient(90deg, #fff 1px, transparent 1px)",
            backgroundSize: "44px 44px",
          }}
        />
        <div className="relative">
          <div className="flex items-center gap-3">
            <div className="flex size-10 items-center justify-center rounded-lg bg-white text-zinc-900">
              <Database className="size-5" aria-hidden="true" />
            </div>
            <div>
              <p className="text-[9px] font-semibold tracking-[0.16em] text-zinc-500">QIANXINAN VOCATIONAL</p>
              <p className="mt-0.5 text-[15px] font-semibold tracking-tight">数据采集系统</p>
            </div>
          </div>
          <h1 className="mt-14 text-[30px] leading-snug font-semibold tracking-tight xl:text-[34px]">
            黔西南民族职业技术学院
            <br />
            <span className="text-zinc-400">数据采集系统</span>
          </h1>
          <p className="mt-4 max-w-[380px] text-[13px] leading-relaxed text-zinc-400">
            统一采集 12 张业务数据表，按「教师—部门—学校」三级数据权限管理填报、审核与开放接口，让每一份数据都有明确的责任边界。
          </p>
          <div className="mt-10 max-w-[400px] space-y-3">
            {[
              { icon: UserRound, title: "教师 · 管好自己的数据", text: "本人基本信息、培训、获奖、论文、科研、实践与知识产权" },
              { icon: Building2, title: "部门管理员 · 管好本部门数据", text: "本部门教师审核、代填、批量导入与填报进度统计" },
              { icon: ShieldCheck, title: "信息中心 · 管好全校数据", text: "全局数据表、全院进度、API 采集任务、开放接口与质量日志" },
            ].map((item) => (
              <div key={item.title} className="flex items-start gap-3 rounded-lg border border-white/10 bg-white/[0.03] px-3.5 py-3">
                <span className="flex size-7 shrink-0 items-center justify-center rounded-md bg-white/10 text-zinc-300">
                  <item.icon className="size-3.5" aria-hidden="true" />
                </span>
                <div>
                  <p className="text-[12px] font-medium text-zinc-200">{item.title}</p>
                  <p className="mt-0.5 text-[10px] leading-relaxed text-zinc-500">{item.text}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
        <div className="relative flex items-center justify-between border-t border-white/10 pt-5 text-[10px] text-zinc-500">
          <span>© 2026 黔西南民族职业技术学院 · 信息中心</span>
          <span className="flex items-center gap-1.5">
            <span className="size-1.5 rounded-full bg-emerald-500" />
            统一身份认证已接入
          </span>
        </div>
      </aside>

      <main className="flex min-w-0 flex-1 items-center justify-center overflow-y-auto">
        <div className="w-full max-w-[420px] px-6 py-10">
          <div className="mb-8 flex items-center gap-3 lg:hidden">
            <div className="flex size-9 items-center justify-center rounded-lg bg-zinc-900 text-white">
              <Database className="size-[18px]" aria-hidden="true" />
            </div>
            <p className="text-[14px] font-semibold tracking-tight">黔西南职院数据采集系统</p>
          </div>
          <div className="mb-6">
            <h2 className="text-[22px] font-semibold tracking-tight">登录数据采集系统</h2>
            <p className="mt-1.5 text-[12px] text-zinc-500">使用学院统一账号登录，系统将按您的身份自动限定数据范围。</p>
          </div>
          <div className="rounded-xl border border-zinc-200 bg-white p-6 shadow-sm">
            <form onSubmit={submit} noValidate>
              <label className="mb-1.5 block text-[11px] font-medium text-zinc-700" htmlFor="account">
                账号
              </label>
              <div className="flex h-10 items-center gap-2 rounded-md border border-zinc-200 px-3 focus-within:border-zinc-400 focus-within:ring-2 focus-within:ring-zinc-100">
                <UserRound className="size-3.5 text-zinc-400" aria-hidden="true" />
                <input
                  id="account"
                  value={account}
                  onChange={(event) => setAccount(event.target.value)}
                  className="w-full bg-transparent text-[12px] outline-none placeholder:text-zinc-400"
                  placeholder="工号 / 手机号"
                />
              </div>
              <label className="mt-4 mb-1.5 block text-[11px] font-medium text-zinc-700" htmlFor="password">
                密码
              </label>
              <div className="flex h-10 items-center gap-2 rounded-md border border-zinc-200 px-3 focus-within:border-zinc-400 focus-within:ring-2 focus-within:ring-zinc-100">
                <Lock className="size-3.5 text-zinc-400" aria-hidden="true" />
                <input
                  id="password"
                  type={showPassword ? "text" : "password"}
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  className="w-full bg-transparent text-[12px] outline-none placeholder:text-zinc-400"
                  placeholder="请输入登录密码"
                />
                <button
                  type="button"
                  aria-label={showPassword ? "隐藏密码" : "显示密码"}
                  className="text-zinc-400 transition hover:text-zinc-600"
                  onClick={() => setShowPassword((value) => !value)}
                >
                  {showPassword ? <EyeOff className="size-3.5" /> : <Eye className="size-3.5" />}
                </button>
              </div>
              {error ? <p className="mt-3 rounded-md bg-rose-50 px-2.5 py-2 text-[10px] leading-relaxed text-rose-700">{error}</p> : null}
              <div className="mt-4 flex items-center justify-between">
                <label className="flex cursor-pointer items-center gap-2 text-[11px] text-zinc-600">
                  <input
                    type="checkbox"
                    checked={remember}
                    onChange={(event) => {
                      setRemember(event.target.checked);
                      if (!event.target.checked) writeRememberedAccount(null);
                    }}
                    className="size-3.5 accent-zinc-900"
                  />
                  记住账号
                </label>
                <button type="button" className="text-[11px] font-medium text-zinc-500 hover:text-zinc-900" onClick={() => toast("请联系信息中心重置统一身份密码")}>
                  忘记密码？
                </button>
              </div>
              <button type="submit" disabled={pending} className="mt-5 flex h-10 w-full items-center justify-center gap-2 rounded-md bg-zinc-900 text-[12px] font-medium text-white hover:bg-zinc-800 disabled:opacity-60">
                <LogIn className="size-3.5" aria-hidden="true" />
                登录
              </button>
            </form>
            <div className="my-5 flex items-center gap-3">
              <div className="h-px flex-1 bg-zinc-100" />
              <span className="text-[10px] text-zinc-400">或使用统一身份认证</span>
              <div className="h-px flex-1 bg-zinc-100" />
            </div>
            <button
              type="button"
              className="flex h-10 w-full items-center justify-center gap-2 rounded-md border border-zinc-200 text-[12px] font-medium text-zinc-700 hover:bg-zinc-50"
              onClick={() => toast("已跳转学院统一身份认证，完成认证后按账号自动匹配数据范围")}
            >
              <Fingerprint className="size-4 text-zinc-500" aria-hidden="true" />
              统一身份认证（CAS / 一网通办）
            </button>
          </div>

          <div className="mt-6">
            <div className="mb-2.5 flex items-center justify-between">
              <p className="text-[11px] font-medium text-zinc-700">测试账号</p>
              <span className="text-[10px] text-zinc-400">登录后按角色进入对应页面</span>
            </div>
            <div className="space-y-2">
              {quickAccounts.map((item) => {
                const Icon = item.role === "teacher" ? UserRound : item.role === "staff" ? Building2 : ShieldCheck;
                return (
                  <button
                    key={item.role}
                    type="button"
                    disabled={pending}
                    className="group flex w-full items-center gap-3 rounded-lg border border-zinc-200 bg-white px-3.5 py-3 text-left transition hover:border-zinc-300 hover:bg-zinc-50 disabled:opacity-60"
                    onClick={() => {
                      setAccount(item.account);
                      setPassword(item.password);
                      setError("");
                      setPending(true);
                      enterWithApi(item.account, item.password).catch((error: unknown) => {
                        setError(error instanceof ApiError ? error.message : "登录失败");
                      }).finally(() => setPending(false));
                    }}
                  >
                    <span className={`flex size-9 shrink-0 items-center justify-center rounded-md ${item.tone}`}>
                      <Icon className="size-4" aria-hidden="true" />
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="flex items-center gap-2">
                        <span className="text-[12px] font-medium text-zinc-800">{item.title}</span>
                        <span className="rounded-full bg-zinc-100 px-1.5 py-0.5 text-[9px] text-zinc-500">{item.badge}</span>
                      </span>
                      <span className="mt-0.5 block text-[10px] text-zinc-400">{item.hint}</span>
                    </span>
                    <ArrowRight className="size-3.5 text-zinc-300 transition group-hover:text-zinc-600" aria-hidden="true" />
                  </button>
                );
              })}
            </div>
          </div>
          <p className="mt-6 text-center text-[10px] leading-relaxed text-zinc-400">登录即表示同意《学院数据采集管理办法》与个人信息保护相关规定</p>
        </div>
      </main>
    </div>
  );
}

export default function LoginPage() {
  return (
    <ToastProvider>
      <LoginForm />
    </ToastProvider>
  );
}
