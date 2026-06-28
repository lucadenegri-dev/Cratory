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

async function apiGet<T>(path: string, params?: FileQuery): Promise<T> {
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
