import { readToken, writeToken, type AuthUser } from "@/lib/session";

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export function apiBase() {
  return process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";
}

function errorMessage(payload: unknown, fallback: string) {
  if (!payload || typeof payload !== "object" || !("detail" in payload)) return fallback;
  const detail = payload.detail;
  if (typeof detail === "string") return detail;
  return fallback;
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  const token = readToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  let response: Response;
  try {
    response = await fetch(`${apiBase()}${path}`, { ...init, headers });
  } catch {
    throw new ApiError(0, "无法连接后端，请确认 API 已在 8000 端口启动");
  }
  if (response.status === 401) writeToken(null);
  const text = await response.text();
  const payload = text ? (JSON.parse(text) as unknown) : null;
  if (!response.ok) {
    throw new ApiError(response.status, errorMessage(payload, "请求失败"));
  }
  return payload as T;
}

export async function download(path: string, filename: string) {
  const headers = new Headers();
  const token = readToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  let response: Response;
  try {
    response = await fetch(`${apiBase()}${path}`, { headers });
  } catch {
    throw new ApiError(0, "无法连接后端，请确认 API 已在 8000 端口启动");
  }
  if (!response.ok) {
    const text = await response.text();
    const payload = text ? (JSON.parse(text) as unknown) : null;
    throw new ApiError(response.status, errorMessage(payload, "导出失败"));
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

export async function upload<T>(path: string, body: FormData): Promise<T> {
  const headers = new Headers();
  const token = readToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  let response: Response;
  try {
    response = await fetch(`${apiBase()}${path}`, { method: "POST", headers, body });
  } catch {
    throw new ApiError(0, "无法连接后端，请确认 API 已在 8000 端口启动");
  }
  if (response.status === 401) writeToken(null);
  const text = await response.text();
  const payload = text ? (JSON.parse(text) as unknown) : null;
  if (!response.ok) {
    throw new ApiError(response.status, errorMessage(payload, "导入失败"));
  }
  return payload as T;
}

export function loginRequest(account: string, password: string) {
  return api<{ access_token: string; user: AuthUser }>("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({ account, password }),
  });
}
