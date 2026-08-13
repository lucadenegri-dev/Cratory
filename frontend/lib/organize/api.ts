import { getCurrentLanguage, translateApiError, type Language } from "@/lib/i18n/runtime";

/* Base relativa = stesso host della pagina: le chiamate /api/organize/* passano
   dal rewrite di next.config.ts verso il backend (come lib/api/client.ts), così
   l'app funziona anche aperta da un altro dispositivo in LAN e senza CORS.
   Le rotte Organize vivono sotto /api/organize: i path passati a apiGet/apiSend
   sono relativi a questa base (es. "/files" → /api/organize/files). */
const API = "/api/organize";

// F3b: `scan_root` non è più un concetto gestito dall'utente. Esistono
// esattamente due cartelle canoniche, derivate da Settings (LIBRARY_ROOT e
// SLSKD_DOWNLOAD_DIR): la UI le tratta come location fisse, non come righe
// di una lista da aggiungere/rimuovere.
export type Location = "inbox" | "library";

export interface ScanResult {
  roots: number[];
  found: number;
  inserted: number;
  updated: number;
  // File il cui (path, size, mtime) combacia con la riga esistente: rilevato
  // dal fast-path incrementale, non riletto. Su una rescan di routine (disco
  // fermo) è la stragrande maggioranza di `found` — updated resta a 0.
  unchanged: number;
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
  location: Location;
  path: string;
  ext: string;
  artist: string | null;
  title: string | null;
  album: string | null;
  album_artist: string | null;
  genre: string | null;
  year: number | null;
  label: string | null;
  track_no: number | null;
  comment: string | null;
  bitrate: number | null;
  duration_s: number | null;
  status: string;
  issue_count: number;
  worst_severity: Severity | null;
  in_dup_group: boolean;
  cover_source: "embedded" | "provider" | null;
}

export interface LibraryFacets {
  genre: string[];
  artist: string[];
  album: string[];
  label: string[];
  ext: string[];
  year: number[];
}

export interface LibraryStats {
  files_total: number;
  by_ext: Record<string, number>;
  issues_by_severity: Record<string, number>;
  dup_groups: number;
  sources: number;
}

export interface FileQuery {
  location?: Location;
  status?: string;
  has_issues?: boolean;
  q?: string;
  genre?: string;
  artist?: string;
  album?: string;
  label?: string;
  ext?: string;
  year?: number;
  sort?: "path" | "artist" | "title" | "ext" | "bitrate" | "duration";
  dir?: "asc" | "desc";
  limit?: number;
  offset?: number;
  [key: string]: string | number | boolean | undefined;
}

async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      const d = body.detail;
      if (d && typeof d === "object" && !Array.isArray(d) && typeof d.code === "string") {
        detail = translateApiError(d.code, d.params ?? {}, d.message ?? res.statusText);
      } else {
        detail = typeof d === "string" ? d : JSON.stringify(d);
      }
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
  // Niente `new URL(...)`: con base relativa (API sotto /api/organize) lancerebbe.
  // La query string viene costruita a mano, come in lib/api/client.ts, così l'URL
  // resta relativo allo stesso host.
  let url = API + path;
  if (params) {
    const qs = new URLSearchParams();
    for (const [k, v] of Object.entries(params)) {
      if (v === undefined || v === "") continue;
      qs.set(k, String(v));
    }
    const s = qs.toString();
    if (s) url += (url.includes("?") ? "&" : "?") + s;
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

// --- SCAN (job) -------------------------------------------------------------
export function startScan(locations?: Location[]) {
  return apiSend<ScanJobState>("POST", "/scan", { locations: locations ?? null });
}
export function scanJobStatus() {
  return apiGet<ScanJobState>("/scan/status");
}

// --- FILES + STATS ----------------------------------------------------------
export function listFiles(query?: FileQuery) {
  return apiGet<FileRow[]>("/files", query);
}
export function libraryStats() {
  return apiGet<LibraryStats>("/library/stats");
}
export function libraryFacets() {
  return apiGet<LibraryFacets>("/library/facets");
}

export interface EditableTags {
  artist: string;
  title: string;
  album: string;
  album_artist: string;
  genre: string;
  year: string;
  label: string;
  track_no: string;
  comment: string;
}

// Modifica manuale dei tag da FILES: manda solo i campi cambiati; ritorna la
// riga aggiornata (issue_count ricalcolato) da rimettere in-place nella tabella.
export function updateFileTags(fileId: number, changes: Partial<EditableTags>) {
  return apiSend<FileRow>("POST", `/files/${fileId}/tags`, changes);
}

// --- ISSUES -----------------------------------------------------------------
export interface Issue {
  id: number;
  file_id: number;
  location: Location;
  type: string;
  field: string | null;
  severity: Severity;
  detail: string;
  suggested_fix_json: Record<string, unknown> | null;
  status: "open" | "accepted" | "dismissed";
  file_path: string;
  artist: string | null;
  title: string | null;
  current_value: string | null;
  is_new: boolean;
}

export interface IssueFilters {
  severity?: string;
  type?: string;
  status?: string;
  location?: Location;
  q?: string;
  [key: string]: string | number | boolean | undefined;
}

export interface IssueBulk {
  type?: string;
  severity?: string;
  status: "open" | "accepted" | "dismissed";
}

export function listIssues(filters?: IssueFilters) {
  return apiGet<Issue[]>("/issues", filters);
}
export function setIssueStatus(id: number, status: "open" | "accepted" | "dismissed") {
  return apiSend<{ id: number; status: string }>("POST", `/issues/${id}/status`, { status });
}
export function fixIssue(id: number, value: string) {
  return apiSend<Issue>("POST", `/issues/${id}/fix`, { value });
}
export function bulkIssues(body: IssueBulk) {
  return apiSend<{ updated: number }>("POST", "/issues/bulk", body);
}

export interface AiSuggestResult {
  configured: boolean;
  files: number;
  suggested: number;
  unresolved: number;
}
export function aiSuggestTags() {
  return apiSend<AiSuggestResult>("POST", "/issues/ai-suggest");
}

export interface ProviderSuggestResult {
  configured: boolean;
  acoustid_available: boolean;
  files: number;
  suggested: number;
  unresolved: number;
  fingerprinted: number;
  covers: number;
}
export function providerSuggest(covers = true) {
  return apiSend<ProviderSuggestResult>("POST", "/issues/provider-suggest", { covers });
}
export function coverThumbUrl(fileId: number): string {
  return `${API}/issues/cover-thumb/${fileId}`;
}

/** Miniatura della traccia: artwork embeddato, o proposta provider come fallback. */
export function fileThumbUrl(fileId: number): string {
  return `${API}/files/${fileId}/thumb`;
}

export interface DetectRatingsResult {
  files: number;
  found: number;
  created: number;
}
export function detectRatings() {
  return apiSend<DetectRatingsResult>("POST", "/issues/detect-ratings");
}

export interface ProviderRescanBody {
  folder?: string | null;
  genre?: string | null;
  fields: string[];
  include_accepted?: boolean;
  include_dismissed?: boolean;
  covers?: boolean;
  only_new?: boolean;
}
export interface ProviderRescanResult {
  configured: boolean;
  acoustid_available: boolean;
  scanned: number;
  fingerprinted: number;
  matched: number;
  no_match: number;
  proposed_strong: number;
  proposed_medium: number;
  proposed_weak: number;
  covers: number;
}
export interface ProviderRescanJobState {
  status: "idle" | "running" | "done" | "error";
  phase: string | null;
  processed: number;
  total: number;
  result: ProviderRescanResult | null;
  error: string | null;
  started_at: string | null;
  finished_at: string | null;
}
export function providerRescan(body: ProviderRescanBody) {
  return apiSend<ProviderRescanJobState>("POST", "/issues/provider-rescan", body);
}
export function providerRescanStatus() {
  return apiGet<ProviderRescanJobState>("/issues/provider-rescan/status");
}
export function acceptStrongOverrides() {
  return apiSend<{ updated: number }>("POST", "/issues/provider-override/accept-strong");
}

export interface GenreReviewResult {
  configured: boolean;
  files: number;
  proposed: number;
  confirmed: number;
  unresolved: number;
  skipped: number;
  // Ricerche web effettivamente consumate dalla passata (opzionale: stato
  // job più vecchi in memoria, prima del fix, possono non averlo).
  web_searches?: number;
}
export interface GenreReviewJobState {
  status: "idle" | "running" | "done" | "error";
  phase: string | null;
  processed: number;
  total: number;
  result: GenreReviewResult | null;
  error: string | null;
  started_at: string | null;
  finished_at: string | null;
  configured?: boolean;
}
export interface GenreReviewBody {
  folder?: string | null;
  genre?: string | null;
  redo?: boolean;
}
export function genreReview(body: GenreReviewBody = {}) {
  return apiSend<GenreReviewJobState>("POST", "/genre-review", body);
}
export function genreReviewStatus() {
  return apiGet<GenreReviewJobState>("/genre-review/status");
}
export function genreReviewPreview(folder?: string) {
  return apiGet<{ configured: boolean; files: number }>("/genre-review/preview", { folder });
}

export interface IntegrityResult {
  scanned: number; checked: number; skipped: number; corrupt: number;
}
export interface IntegrityJobState {
  status: "idle" | "running" | "done" | "error";
  phase: string | null; processed: number; total: number;
  result: IntegrityResult | null; error: string | null; available: boolean;
  started_at: string | null; finished_at: string | null;
}
export function integrityCheck(force = false) {
  return apiSend<IntegrityJobState>("POST", "/issues/integrity-check", { force });
}
export function integrityStatus() {
  return apiGet<IntegrityJobState>("/issues/integrity-check/status");
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
  return apiGet<DupGroup[]>("/duplicates");
}
export function setKeeper(groupId: number, fileId: number) {
  return apiSend<DupGroup>("POST", `/duplicates/${groupId}/keeper`, { file_id: fileId });
}
export function dismissDuplicate(groupId: number) {
  return apiSend<DupGroup>("POST", `/duplicates/${groupId}/dismiss`);
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
  skipped: boolean; // in conflitto: all'apply verrà saltato
}
export interface Conflict {
  kind: string;
  file_id: number;
  detail: string;
}
export interface PlanStats {
  n_retag: number;
  n_cover: number;
  n_rename: number;
  n_move: number;
  n_delete: number;
  space_freed_bytes: number;
  n_conflicts: number;
  n_skipped: number;
  blocking: boolean; // niente da applicare (tutti gli op saltati)
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
  skipped_ops: number;
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
  return apiSend<Plan>("POST", "/plan");
}
export function getPlan() {
  return apiGet<Plan>("/plan");
}
export function startApply() {
  return apiSend<ApplyJobState>("POST", "/apply");
}
export function applyStatus() {
  return apiGet<ApplyJobState>("/apply/status");
}

// --- HISTORY ----------------------------------------------------------------
export interface HistoryItem {
  id: number;
  status: string; // applied | undone
  created_at: string;
  n_ops: number;
  kind: string | null; // "manual_edit" per le modifiche manuali, altrimenti null
}
export interface UndoResult {
  run_id: number;
  reversed_ops: number;
  error: string | null;
}
export function listHistory() {
  return apiGet<HistoryItem[]>("/history");
}
export function undoRun(id: number) {
  return apiSend<UndoResult>("POST", `/history/${id}/undo`);
}

// --- SETTINGS ---------------------------------------------------------------
export interface Settings {
  naming_template: string;
  folder_template: string;
}
export function getSettings() {
  return apiGet<Settings>("/settings");
}
export function updateSettings(body: {
  naming_template?: string;
  folder_template?: string;
}) {
  return apiSend<Settings>("PUT", "/settings", body);
}
export function getLanguage() {
  return apiGet<{ language: Language }>("/settings/language");
}
export function setLanguage(language: Language) {
  return apiSend<{ language: Language }>("PUT", "/settings/language", { language });
}

// --- FINGERPRINT --------------------------------------------------------------
export interface FingerprintStatus {
  configured: boolean;
  fpcalc: boolean;
}
export interface FingerprintResult {
  configured: boolean;
  identified: number;
  below_threshold: number;
  not_found: number;
  errors: number;
  total: number;
}
export function fingerprintStatus() {
  return apiGet<FingerprintStatus>("/fingerprint/status");
}
export function runFingerprint() {
  return apiSend<FingerprintResult>("POST", "/fingerprint");
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
  const lang = getCurrentLanguage();
  if (!iso) return lang === "it" ? "mai" : "never";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  const locale = lang === "it" ? "it-IT" : "en-GB";
  return d.toLocaleString(locale, { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
}

// --- PICKER -----------------------------------------------------------------
/** Il dialog nativo di scelta percorso è disponibile? (solo backend su macOS) */
export function pickerAvailability() {
  return apiGet<{ available: boolean }>("/picker/availability");
}
/** Apre il dialog nativo sulla macchina del backend; path null = annullato. */
export function pickPath(kind: "folder" | "file", start?: string, prompt?: string) {
  return apiSend<{ path: string | null }>("POST", "/picker/pick", {
    kind, start: start || null, prompt: prompt || null,
  });
}
