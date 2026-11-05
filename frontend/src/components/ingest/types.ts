export type IngestTask = {
  id: string;
  dataset_code: string;
  batch_id: string | null;
  status: string;
  progress: number;
  user_prompt: string;
  error_message: string | null;
  attempts: number;
  mapping_applied: boolean;
  has_mapping: boolean;
  plan_source: string | null;
  llm_calls: number;
  tokens_in: number;
  tokens_out: number;
  file_name: string | null;
  candidate_count: number;
  created_at: string;
};

export type Candidate = {
  id: string;
  seq: number;
  dataset_code: string;
  business_key: string | null;
  /** 业务主键里为空的字段代码，非空时不能写入 */
  missing_key?: string[];
  completeness: number;
  triage: "auto" | "review" | "missing" | "duplicate";
  field_sources: Record<string, { source?: string; score?: number; evidence?: string }>;
  conflicts: { code?: string; label?: string; kept?: string; dropped?: string }[];
  source_text: string | null;
  target_record_id: string | null;
  values: Record<string, string | number | null>;
  errors: string[];
  warnings: string[];
  duplicate_of: string | null;
  status: string;
  record_id: string | null;
};

export type PlanColumn = {
  header?: string | null;
  headers?: string[] | null;
  field?: string | null;
  fields?: string[] | null;
  transform?: string;
};

export type PlanSheet = {
  sheet: string;
  dataset_code?: string | null;
  role: string;
  header_rows: number[];
  data_start: number;
  row_mode: string;
  columns: PlanColumn[];
  dedupe_by?: string[];
};

export type StructurePlan = {
  sheets: PlanSheet[];
  merge_sheets?: string[][];
  joins?: unknown[];
  source?: string;
  confidence?: number;
};

export type PlanGap = { code: string; label: string; reason: string };

export type SheetProfile = {
  sheet: string;
  rows: number;
  cols: number;
  headers: string[];
  samples: string[][];
  duplicate_headers?: string[];
  skip_reason?: string | null;
};

export type DryRun = {
  rows?: number;
  required_total?: number;
  required_covered?: number;
  empty_required_rate?: number;
  transform_failure_rate?: number;
  error_rate?: number;
  duplicate_rate?: number;
  gaps?: PlanGap[];
  conditional?: PlanGap[];
  samples?: { dataset_code: string; sheet: string; row: number; values: Record<string, unknown> }[];
};

export type PlanRead = {
  task_id: string;
  status: string;
  plan_source: string | null;
  profile?: { kind?: string; sheets?: SheetProfile[] } | null;
  plan: StructurePlan | null;
  dry_run: DryRun | null;
};

export type MappingItem = {
  header?: string | null;
  field?: string | null;
  transform?: string;
  confidence?: number;
};

export type BatchRead = {
  id: string;
  title: string;
  dataset_codes: string[];
  status: string;
  task_count: number;
  candidate_count: number;
  auto_count: number;
  review_count: number;
  missing_count: number;
  duplicate_count: number;
};

export type GapRead = {
  dataset_code: string;
  dataset_name: string;
  code: string;
  label: string;
  count: number;
  reason: string;
};

export const STATUS_LABEL: Record<string, string> = {
  queued: "排队中",
  parsing: "解析中",
  awaiting_plan: "待确认结构",
  extracting: "提取中",
  pending_confirmation: "待核对",
  completed: "已完成",
  failed: "失败",
  cancelled: "已取消",
};

export const TRIAGE_LABEL: Record<Candidate["triage"], string> = {
  auto: "可直接确认",
  review: "需复核",
  missing: "待补字段",
  duplicate: "重复",
};

export const TRIAGE_BADGE: Record<Candidate["triage"], string> = {
  auto: "bg-emerald-50 text-emerald-700",
  review: "bg-sky-50 text-sky-700",
  missing: "bg-amber-50 text-amber-700",
  duplicate: "bg-rose-50 text-rose-700",
};

export const PLAN_SOURCE_LABEL: Record<string, string> = {
  template: "模板记忆",
  exact: "表头精确匹配",
  llm: "模型规划",
  user: "人工确认",
};

export const ACTIVE = new Set(["queued", "parsing", "extracting"]);

export function tone(status: string): "ok" | "run" | "warn" | "bad" | "muted" {
  if (status === "completed" || status === "confirmed") return "ok";
  if (status === "failed") return "bad";
  if (status === "pending_confirmation" || status === "pending" || status === "awaiting_plan") return "warn";
  if (ACTIVE.has(status)) return "run";
  return "muted";
}
