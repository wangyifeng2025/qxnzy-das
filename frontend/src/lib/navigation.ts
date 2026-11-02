import type { LucideIcon } from "lucide-react";
import {
  BookOpen,
  Braces,
  Building2,
  ClipboardCheck,
  FilePenLine,
  LayoutDashboard,
  ListChecks,
  ShieldCheck,
  Sparkles,
  TableProperties,
  Users,
  Workflow,
} from "lucide-react";

import type { Role } from "@/lib/session";

export type NavItem = {
  href: string;
  label: string;
  icon: LucideIcon;
  badge?: string;
  badgeClass?: string;
};

export type NavGroup = {
  title: string;
  items: NavItem[];
};

const fillScope: Record<Role, string> = {
  teacher: "本人填报",
  staff: "本部门范围",
  admin: "全校范围",
};

export function navigationFor(role: Role): NavGroup[] {
  const workbench =
    role === "admin"
      ? { href: "/home", label: "信息中心工作台", icon: LayoutDashboard }
      : role === "staff"
        ? { href: "/review", label: "部门管理员工作台", icon: LayoutDashboard }
        : { href: "/my-fill", label: "我的工作台", icon: LayoutDashboard };

  const collection: NavGroup = {
    title: "数据采集",
    items: [
      { href: "/fill", label: "数据填报表单", icon: FilePenLine, badge: fillScope[role] },
      {
        href: "/ai-parse",
        label: "文件解析入库",
        icon: Sparkles,
        badge: "AI",
        badgeClass: "bg-blue-50 text-blue-600",
      },
      {
        href: "/my-fill",
        label: role === "staff" ? "本部门填报跟踪" : "我的填报",
        icon: ClipboardCheck,
        badge: role === "admin" ? undefined : "2",
        badgeClass: "bg-rose-50 text-rose-600",
      },
    ],
  };

  if (role === "staff" || role === "admin") {
    collection.items.push({
      href: "/review",
      label: role === "admin" ? "审核与复核导入" : "审核与批量导入",
      icon: ListChecks,
      badge: "18",
      badgeClass: "bg-amber-50 text-amber-700",
    });
  }

  const groups: NavGroup[] = [{ title: "工作台", items: [workbench] }];

  if (role === "admin") {
    groups.push({
      title: "系统管理",
      items: [
        { href: "/departments", label: "系部管理", icon: Building2 },
        { href: "/users", label: "用户管理", icon: Users },
        { href: "/roles", label: "角色管理", icon: ShieldCheck },
        { href: "/dicts", label: "字典管理", icon: BookOpen },
      ],
    });
  }

  groups.push(collection);

  if (role === "admin") {
    groups.push({
      title: "数据治理",
      items: [
        { href: "/schema", label: "数据表与字段", icon: TableProperties },
        { href: "/api-tasks", label: "API 采集任务", icon: Workflow },
        { href: "/open-api", label: "对外数据接口", icon: Braces },
        { href: "/quality", label: "采集日志与质量", icon: ShieldCheck },
      ],
    });
  }

  return groups;
}

export const ROUTE_ACCESS: Record<string, Role[]> = {
  "/home": ["admin"],
  "/fill": ["teacher", "staff", "admin"],
  "/ai-parse": ["teacher", "staff", "admin"],
  "/my-fill": ["teacher", "staff", "admin"],
  "/review": ["staff", "admin"],
  "/schema": ["admin"],
  "/api-tasks": ["admin"],
  "/open-api": ["admin"],
  "/quality": ["admin"],
  "/departments": ["admin"],
  "/users": ["admin"],
  "/roles": ["admin"],
  "/dicts": ["admin"],
};

export const ROUTE_TITLE: Record<string, { crumb: string; heading: string }> = {
  "/home": { crumb: "采集总览", heading: "数据采集工作台" },
  "/fill": { crumb: "数据填报表单", heading: "手动采集" },
  "/ai-parse": { crumb: "文件解析入库", heading: "大模型驱动" },
  "/my-fill": { crumb: "我的填报", heading: "教师个人工作台" },
  "/review": { crumb: "审核与批量导入", heading: "部门审核工作台" },
  "/schema": { crumb: "数据表与字段", heading: "数据标准" },
  "/api-tasks": { crumb: "API 采集任务", heading: "自动采集渠道" },
  "/open-api": { crumb: "对外数据接口", heading: "Open API v1" },
  "/quality": { crumb: "采集日志与质量", heading: "数据质量" },
  "/departments": { crumb: "系部管理", heading: "系统管理" },
  "/users": { crumb: "用户管理", heading: "系统管理" },
  "/roles": { crumb: "角色管理", heading: "系统管理" },
  "/dicts": { crumb: "字典管理", heading: "系统管理" },
};
