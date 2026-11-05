import type { LucideIcon } from "lucide-react";
import {
  BookOpen,
  Braces,
  ClipboardCheck,
  LayoutDashboard,
  ListChecks,
  ShieldCheck,
  Sparkles,
  TableProperties,
  Users,
  Workflow,
} from "lucide-react";

import type { Role, SessionUser } from "@/lib/session";

export type NavChild = {
  href: string;
  label: string;
};

export type NavItem = {
  href?: string;
  label: string;
  icon: LucideIcon;
  badge?: string;
  badgeClass?: string;
  children?: NavChild[];
};

export type NavGroup = {
  title: string;
  items: NavItem[];
};

export const TEACHER_FILL_TABLES: NavChild[] = [
  { href: "/fill?table=staff", label: "教职工基本信息" },
  { href: "/fill?table=training", label: "教师培训与交流" },
  { href: "/fill?table=award", label: "教师获奖信息" },
  { href: "/fill?table=paper", label: "教师论文著作" },
  { href: "/fill?table=vertical", label: "教师纵向科研项目" },
  { href: "/fill?table=horizontal", label: "教师横向课题" },
  { href: "/fill?table=practice", label: "教师企业实践锻炼" },
  { href: "/fill?table=ip", label: "教师知识产权" },
  { href: "/fill?table=teaching", label: "授课信息" },
];

const TEACHER_TABLE_IDS = new Set(
  TEACHER_FILL_TABLES.map((item) => new URLSearchParams(item.href.split("?")[1]).get("table")),
);

export function fillScopeLabel(role: Role) {
  if (role === "admin") return "全校范围";
  if (role === "staff") return "本部门范围";
  return "本人填报";
}

export function canFillTable(role: Role, tableId: string) {
  if (role === "teacher") return TEACHER_TABLE_IDS.has(tableId);
  return true;
}

function fillHref(code: string) {
  return code === "ODS_JZGJBSJ" ? "/fill?table=staff" : `/fill?table=${code}`;
}

export function navigationFor(user: SessionUser): NavGroup[] {
  const role = user.role;
  const auditor = user.roleCodes.includes("auditor");
  const workbench = auditor
    ? { href: "/review", label: "业务部门工作台", icon: LayoutDashboard }
    : role === "admin"
      ? { href: "/home", label: "信息中心工作台", icon: LayoutDashboard }
      : role === "staff"
        ? { href: "/review", label: "系部工作台", icon: LayoutDashboard }
        : { href: "/my-fill", label: "我的工作台", icon: LayoutDashboard };

  const fillable = user.datasets.filter((item) => item.can_fill);
  const collectionItems: NavItem[] = [];
  const academic = fillable.filter((item) => item.category === "academic");
  const teacher = fillable.filter((item) => item.category !== "academic");
  if (teacher.length > 0) {
    collectionItems.push({
      label: "教师信息采集",
      icon: Users,
      badge: auditor ? "全校范围" : fillScopeLabel(role),
      badgeClass: "bg-white text-zinc-500",
      children: teacher.map((item) => ({ href: fillHref(item.code), label: item.name })),
    });
  }
  if (academic.length > 0) {
    collectionItems.push({
      label: "教务数据采集",
      icon: BookOpen,
      badge: auditor ? "全校范围" : fillScopeLabel(role),
      badgeClass: "bg-white text-zinc-500",
      children: academic.map((item) => ({ href: fillHref(item.code), label: item.name })),
    });
  }

  collectionItems.push(
    {
      href: "/ai-parse",
      label: "文件解析入库",
      icon: Sparkles,
      badge: "AI",
      badgeClass: "bg-blue-50 text-blue-600",
    },
    {
      href: "/my-fill",
      label: role === "teacher" ? "我的填报" : "填报跟踪",
      icon: ClipboardCheck,
    },
  );

  // 信息中心在各数据表页面直接批量审核发布，不单设审核菜单
  if (role !== "admin" && (role === "staff" || user.datasets.some((item) => item.can_review))) {
    collectionItems.push({
      href: "/review",
      label: auditor ? "业务部门审核" : "系部审核",
      icon: ListChecks,
    });
  }

  const groups: NavGroup[] = [
    { title: "工作台", items: [workbench] },
    { title: "数据采集", items: collectionItems },
  ];

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
    groups.push({
      title: "系统管理",
      items: [
        { href: "/users", label: "用户管理", icon: Users },
        { href: "/roles", label: "角色管理", icon: ShieldCheck },
        { href: "/dicts", label: "字典管理", icon: BookOpen },
      ],
    });
  }

  return groups;
}

export function navLinks(groups: NavGroup[]): Array<NavItem & { href: string }> {
  return groups.flatMap((group) =>
    group.items.flatMap((item) => {
      const links: Array<NavItem & { href: string }> = [];
      if (item.href) links.push({ ...item, href: item.href });
      for (const child of item.children ?? []) {
        links.push({ href: child.href, label: child.label, icon: item.icon });
      }
      return links;
    }),
  );
}

export const ROUTE_ACCESS: Record<string, Role[]> = {
  "/home": ["admin"],
  "/fill": ["teacher", "staff", "admin"],
  "/ai-parse": ["teacher", "staff", "admin"],
  "/my-fill": ["teacher", "staff", "admin"],
  "/review": ["staff"],
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
  "/fill": { crumb: "数据填报表单", heading: "2025—2026 学年第一学期" },
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
