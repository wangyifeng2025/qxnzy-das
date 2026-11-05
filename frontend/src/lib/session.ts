export type Role = "teacher" | "staff" | "admin";

export type DatasetAccess = {
  code: string;
  name: string;
  category?: string;
  can_fill: boolean;
  can_review: boolean;
};

export type SessionUser = {
  role: Role;
  name: string;
  dept: string;
  account: string;
  post: string;
  roleCodes: string[];
  datasets: DatasetAccess[];
};

export const ROLE_LABEL: Record<Role, string> = {
  teacher: "教师",
  staff: "部门管理员",
  admin: "信息中心管理员",
};

export const ROLE_HOME: Record<Role, string> = {
  teacher: "/my-fill",
  staff: "/review",
  admin: "/home",
};

const USER_KEY = "qxCurrentUser";
const ROLE_KEY = "qxRole";
const REMEMBER_KEY = "qxRememberAccount";
const TOKEN_KEY = "qxToken";

export type AuthUser = {
  account: string;
  name: string;
  department_name: string | null;
  post: string | null;
  role_codes: string[];
  is_superuser: boolean;
  datasets?: DatasetAccess[];
};

export function sessionFromAuth(user: AuthUser): SessionUser {
  const role: Role =
    user.is_superuser || user.role_codes.includes("admin")
      ? "admin"
      : user.role_codes.includes("staff") || user.role_codes.includes("auditor")
        ? "staff"
        : "teacher";
  return {
    role,
    name: user.name,
    dept: user.department_name || "未分配部门",
    account: user.account,
    post: user.post || ROLE_LABEL[role],
    roleCodes: user.role_codes,
    datasets: user.datasets ?? [],
  };
}

export function readSession(): SessionUser | null {
  if (typeof window === "undefined") return null;
  const role = window.localStorage.getItem(ROLE_KEY);
  if (role !== "teacher" && role !== "staff" && role !== "admin") return null;
  try {
    const user = JSON.parse(window.localStorage.getItem(USER_KEY) ?? "null") as SessionUser | null;
    if (!user?.name || user.role !== role) return null;
    return { ...user, roleCodes: user.roleCodes ?? [], datasets: user.datasets ?? [] };
  } catch {
    return null;
  }
}

export function writeSession(user: SessionUser) {
  window.localStorage.setItem(ROLE_KEY, user.role);
  window.localStorage.setItem(USER_KEY, JSON.stringify(user));
}

export function readToken() {
  if (typeof window === "undefined") return "";
  return window.localStorage.getItem(TOKEN_KEY) ?? "";
}

export function writeToken(token: string | null) {
  if (token) window.localStorage.setItem(TOKEN_KEY, token);
  else window.localStorage.removeItem(TOKEN_KEY);
}

export function clearSession() {
  window.localStorage.removeItem(ROLE_KEY);
  window.localStorage.removeItem(USER_KEY);
  window.localStorage.removeItem(TOKEN_KEY);
}

export function readRememberedAccount() {
  if (typeof window === "undefined") return "";
  return window.localStorage.getItem(REMEMBER_KEY) ?? "";
}

export function writeRememberedAccount(account: string | null) {
  if (account) window.localStorage.setItem(REMEMBER_KEY, account);
  else window.localStorage.removeItem(REMEMBER_KEY);
}
