const API = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8010";

export interface ScanRoot {
  id: number;
  path: string;
  label: string | null;
  last_scanned_at: string | null;
  file_count: number;
}

export interface ScanResult {
  roots: number[];
  found: number;
  inserted: number;
  updated: number;
  moved: number;
  missing: number;
  errors: number;
  started_at: string | null;
  finished_at: string | null;
  analysis?: {
    issues_total: number;
    issues_by_severity: Record<string, number>;
    dup_groups: number;
    dup_files: number;
  };
}

export interface ScanJobState {
  status: "idle" | "running" | "done" | "error";
  phase: string | null;
  processed: number;
  total: number;
  result: ScanResult | null;
  error: string | null;
  started_at: string | null;
  finished_at: string | null;
}

export type Severity = "error" | "warning" | "info";

export interface FileRow {
  id: number;
  root_id: number;
  path: string;
  ext: string;
  artist: string | null;
  title: string | null;
  bitrate: number | null;
  duration_s: number | null;
  status: string;
  issue_count: number;
  worst_severity: Severity | null;
  in_dup_group: boolean;
}

export interface LibraryStats {
  files_total: number;
  by_ext: Record<string, number>;
  issues_by_severity: Record<string, number>;
  dup_groups: number;
  sources: number;
}

export interface FileQuery {
  root_id?: number;
  status?: string;
  has_issues?: boolean;
  q?: string;
  sort?: "path" | "artist" | "title" | "bitrate" | "duration";
  limit?: number;
  offset?: number;
  [key: string]: string | number | boolean | undefined;
}

async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* keep statusText */
    }
    throw new Error(detail);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

async function apiGet<T>(
  path: string,
  params?: Record<string, string | number | boolean | undefined>,
): Promise<T> {
  const url = new URL(API + path);
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== "") url.searchParams.set(k, String(v));
    }
  }
  return handle<T>(await fetch(url));
}

async function apiSend<T>(method: string, path: string, body?: unknown): Promise<T> {
  return handle<T>(
    await fetch(API + path, {
      method,
      headers: { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    }),
  );
}

// --- SOURCES ----------------------------------------------------------------
export function listSources() {
  return apiGet<ScanRoot[]>("/api/sources");
}
export function addSource(path: string, label?: string) {
  return apiSend<ScanRoot>("POST", "/api/sources", { path, label: label || null });
}
export function deleteSource(id: number) {
  return apiSend<void>("DELETE", `/api/sources/${id}`);
}

// --- SCAN (job) -------------------------------------------------------------
export function startScan(rootIds?: number[]) {
  return apiSend<ScanJobState>("POST", "/api/scan", { root_ids: rootIds ?? null });
}
export function scanJobStatus() {
  return apiGet<ScanJobState>("/api/scan/status");
}

// --- FILES + STATS ----------------------------------------------------------
export function listFiles(query?: FileQuery) {
  return apiGet<FileRow[]>("/api/files", query);
}
export function libraryStats() {
  return apiGet<LibraryStats>("/api/library/stats");
}

// --- ISSUES -----------------------------------------------------------------
export interface Issue {
  id: number;
  file_id: number;
  root_id: number;
  type: string;
  field: string | null;
  severity: Severity;
  detail: string;
  suggested_fix_json: Record<string, unknown> | null;
  status: "open" | "accepted" | "dismissed";
  file_path: string;
  artist: string | null;
  title: string | null;
}

export interface IssueFilters {
  severity?: string;
  type?: string;
  status?: string;
  root_id?: number;
  [key: string]: string | number | boolean | undefined;
}

export interface IssueBulk {
  type?: string;
  severity?: string;
  status: "open" | "accepted" | "dismissed";
}

export function listIssues(filters?: IssueFilters) {
  return apiGet<Issue[]>("/api/issues", filters);
}
export function setIssueStatus(id: number, status: "open" | "accepted" | "dismissed") {
  return apiSend<{ id: number; status: string }>("POST", `/api/issues/${id}/status`, { status });
}
export function fixIssue(id: number, value: string) {
  return apiSend<Issue>("POST", `/api/issues/${id}/fix`, { value });
}
export function bulkIssues(body: IssueBulk) {
  return apiSend<{ updated: number }>("POST", "/api/issues/bulk", body);
}

export interface AiSuggestResult {
  configured: boolean;
  files: number;
  suggested: number;
  unresolved: number;
}
export function aiSuggestTags() {
  return apiSend<AiSuggestResult>("POST", "/api/issues/ai-suggest");
}

// --- DUPLICATES -------------------------------------------------------------
export interface DupMember {
  file_id: number;
  action: "keep" | "remove";
  path: string;
  ext: string;
  bitrate: number | null;
  duration_s: number | null;
  content_hash: string | null;
}
export interface DupGroup {
  id: number;
  match_kind: string;
  keeper_file_id: number;
  keeper_overridden: boolean;
  dismissed: boolean;
  members: DupMember[];
}

export function listDuplicates() {
  return apiGet<DupGroup[]>("/api/duplicates");
}
export function setKeeper(groupId: number, fileId: number) {
  return apiSend<DupGroup>("POST", `/api/duplicates/${groupId}/keeper`, { file_id: fileId });
}
export function dismissDuplicate(groupId: number) {
  return apiSend<DupGroup>("POST", `/api/duplicates/${groupId}/dismiss`);
}

// --- PLAN + APPLY -----------------------------------------------------------
export interface PlanOp {
  id: number;
  seq: number;
  kind: string; // RETAG | RENAME | MOVE | DELETE
  file_id: number;
  file_path: string;
  before: Record<string, unknown>;
  after: Record<string, unknown>;
  status: string;
}
export interface Conflict {
  kind: string;
  file_id: number;
  detail: string;
}
export interface PlanStats {
  n_retag: number;
  n_rename: number;
  n_move: number;
  n_delete: number;
  space_freed_bytes: number;
  n_conflicts: number;
  blocking: boolean;
}
export interface Plan {
  id: number;
  status: string;
  created_at: string;
  rules: Record<string, unknown>;
  ops: PlanOp[];
  conflicts: Conflict[];
  stats: PlanStats;
}
export interface ApplyResult {
  run_id: number | null;
  applied_ops: number;
  refused: boolean;
  stale: boolean;
  partial: boolean;
  failed_op_seq: number | null;
  error: string | null;
  reason: string | null;
  started_at: string | null;
  finished_at: string | null;
}
export interface ApplyJobState {
  status: "idle" | "running" | "done" | "error";
  phase: string | null;
  processed: number;
  total: number;
  result: ApplyResult | null;
  error: string | null;
  started_at: string | null;
  finished_at: string | null;
}

export function buildPlan() {
  return apiSend<Plan>("POST", "/api/plan");
}
export function getPlan() {
  return apiGet<Plan>("/api/plan");
}
export function startApply() {
  return apiSend<ApplyJobState>("POST", "/api/apply");
}
export function applyStatus() {
  return apiGet<ApplyJobState>("/api/apply/status");
}

// --- HISTORY ----------------------------------------------------------------
export interface HistoryItem {
  id: number;
  status: string; // applied | undone
  created_at: string;
  n_ops: number;
}
export interface UndoResult {
  run_id: number;
  reversed_ops: number;
  error: string | null;
}
export function listHistory() {
  return apiGet<HistoryItem[]>("/api/history");
}
export function undoRun(id: number) {
  return apiSend<UndoResult>("POST", `/api/history/${id}/undo`);
}

// --- SETTINGS ---------------------------------------------------------------
export interface RootTarget {
  id: number;
  path: string;
  label: string | null;
  target_root: string | null;
}
export interface Settings {
  naming_template: string;
  folder_template: string;
  roots: RootTarget[];
}
export function getSettings() {
  return apiGet<Settings>("/api/settings");
}
export function updateSettings(body: { naming_template?: string; folder_template?: string }) {
  return apiSend<Settings>("PUT", "/api/settings", body);
}
export function setRootTarget(rootId: number, target: string | null) {
  return apiSend<Settings>("PUT", `/api/settings/roots/${rootId}/target`, { target_root: target });
}

// --- helpers ----------------------------------------------------------------
export function fmtDuration(seconds: number | null | undefined): string {
  if (!seconds) return "—";
  const total = Math.round(seconds);
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "mai";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString("it-IT", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
}
