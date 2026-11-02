"use client";

import { useState, type FormEvent } from "react";

import { ApiError, loginRequest } from "@/lib/api";
import { sessionFromAuth, writeSession, writeToken } from "@/lib/session";

const fieldClass =
  "mt-1 w-full rounded-md border border-zinc-200 px-2.5 py-2 text-[12px] outline-none focus:border-zinc-400";

export function ApiConnect({ title }: { title: string }) {
  const [account, setAccount] = useState("admin");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");

  async function connect(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    try {
      const result = await loginRequest(account.trim(), password);
      writeToken(result.access_token);
      writeSession(sessionFromAuth(result.user));
      window.location.reload();
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "登录失败");
    }
  }

  return (
    <div className="mx-auto max-w-md p-5">
      <h1 className="text-[19px] font-semibold tracking-tight">{title}</h1>
      <form className="mt-4 rounded-xl border border-zinc-200 bg-white p-5" onSubmit={(event) => void connect(event)}>
        <p className="text-[12px] leading-relaxed text-zinc-500">
          当前浏览器没有后端登录令牌。使用管理员账号 admin，初始密码 Admin@2026。
        </p>
        <label className="mt-4 block text-[11px] text-zinc-500">
          账号
          <input className={fieldClass} value={account} onChange={(event) => setAccount(event.target.value)} />
        </label>
        <label className="mt-3 block text-[11px] text-zinc-500">
          密码
          <input
            type="password"
            className={fieldClass}
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </label>
        {error ? <p className="mt-3 text-[11px] text-rose-600">{error}</p> : null}
        <button type="submit" className="mt-4 rounded-md bg-zinc-900 px-3.5 py-2 text-[12px] font-medium text-white">
          连接并进入
        </button>
      </form>
    </div>
  );
}
