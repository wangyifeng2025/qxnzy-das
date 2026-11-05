export type FieldMeta = {
  code: string;
  label: string;
  kind: string;
  group: string;
  required: boolean;
  max_length: number | null;
  dict_code: string | null;
  visible_when: string | null;
  sensitive: boolean;
  default: string | null;
};

export type DatasetMeta = {
  code: string;
  name: string;
  list_fields: string[];
  business_key_fields?: string[];
  can_fill: boolean;
  can_review: boolean;
  can_export_sensitive: boolean;
  owner_field: string | null;
  owner_name_field: string | null;
  department_field: string;
  filler_type: string | null;
  account: string;
  user_name: string;
  department_name: string | null;
  departments: string[];
  dicts: Record<string, Array<{ value: string; label: string }>>;
  title_ranks: string[];
  groups: Array<{ title: string; hint: string | null }>;
  fields: FieldMeta[];
};

export type RecordItem = {
  id: string;
  dataset_code: string;
  dataset_name: string;
  business_key: string;
  status: string;
  owner_account: string;
  filler_account: string;
  filler_type: string;
  department_name: string | null;
  summary: Record<string, string | number | null>;
  warnings: string[];
  errors: string[];
  completeness: number;
  updated_at: string;
  published_version: number;
  /** 当前用户能否对该记录审核通过或退回 */
  can_review?: boolean;
  /** 当前用户能否把已发布记录改回草稿（仅信息中心） */
  can_revise?: boolean;
};

export type RecordDetail = RecordItem & {
  payload: Record<string, string | number | null>;
  field_sources: Record<string, unknown>;
  source_type: string;
  schema_version: number;
  ods_id: string | null;
};

export type RecordEvent = {
  id: number;
  action: string;
  from_status: string | null;
  to_status: string;
  comment: string | null;
  actor_account: string | null;
  diff: Record<string, { from?: unknown; to?: unknown }> | null;
  created_at: string;
};

export type RecordPage = {
  items: RecordItem[];
  total: number;
  page: number;
  page_size: number;
};

export const STATUS_LABEL: Record<string, string> = {
  draft: "草稿",
  pending_dept: "待系部初审",
  pending_domain: "待业务部门审核",
  pending_center: "待信息中心审核",
  returned: "已退回",
  published: "已发布",
  archived: "已归档",
};

export function canWithdraw(row: Pick<RecordItem, "filler_account" | "filler_type" | "status">, account: string) {
  if (row.filler_account !== account) return false;
  if (row.filler_type === "teacher") return row.status === "pending_dept";
  if (row.filler_type === "department") return row.status === "pending_domain";
  if (row.filler_type === "domain") return row.status === "pending_center";
  return false;
}

export function fieldLabel(meta: DatasetMeta | null, code: string) {
  return meta?.fields.find((field) => field.code === code)?.label ?? code;
}

export function optionLabel(meta: DatasetMeta, code: string, value: string | number | null | undefined) {
  if (value == null || value === "") return "—";
  const text = String(value);
  const field = meta.fields.find((item) => item.code === code);
  const options =
    field?.dict_code === "departments"
      ? meta.departments.map((name) => ({ value: name, label: name }))
      : field?.dict_code === "titles"
        ? meta.title_ranks.map((name) => ({ value: name, label: name }))
        : field?.dict_code
          ? (meta.dicts[field.dict_code] ?? [])
          : [];
  return options.find((item) => item.value === text)?.label ?? text;
}
