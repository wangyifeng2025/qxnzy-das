export type DepartmentKind = "teaching" | "functional" | "other";

export type Department = {
  id: number;
  code: string;
  name: string;
  shortName: string;
  kind: DepartmentKind;
  leader: string;
  dataManager: string;
  phone: string;
  sortOrder: number;
  isActive: boolean;
  userCount: number;
  remark: string;
};

export const DEPARTMENT_KIND_LABEL: Record<DepartmentKind, string> = {
  teaching: "教学系部",
  functional: "职能部门",
  other: "其他",
};

