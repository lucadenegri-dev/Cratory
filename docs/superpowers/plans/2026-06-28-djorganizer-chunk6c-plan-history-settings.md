# DjOrganizer Chunk 6c — PLAN + HISTORY + SETTINGS — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Completare le tre pagine placeholder — PLAN (anteprima operazioni + apply con conferma), HISTORY (run + undo), SETTINGS (template + target per radice) — chiudendo il flusso end-to-end dell'app.

**Architecture:** Solo frontend: tutti gli endpoint backend (plan/apply/history/settings) esistono già. Si aggiungono i tipi+funzioni al client `lib/api.ts`, si estende `jobs-provider` per fare polling anche del job di apply (additivo, retro-compatibile), e si costruiscono le 3 pagine + 2 componenti del PLAN.

**Tech Stack:** Next 16.2.9, React 19.2.4, Tailwind 4, TypeScript 5. **Nessuna modifica backend.**

## Global Constraints

- **Solo frontend. NESSUNA modifica backend.** La suite pytest esistente deve restare verde/pristine (non toccata).
- Frontend: pattern di 6a/6b — client tipizzato, `useJobs`, `PageLayout`, `ui.tsx` (incl. `Modal`, `EqMeter`, `Button`, `Alert`, `EmptyState`), token `--c-*` (incl. `--c-ok`/`--c-warning`). Il "test" è **`npm run lint` + `npm run build` verdi** (NO unit test/TDD). Comandi npm da `frontend/`.
- Ogni mutazione utente (build/apply/undo/save) ha **try/catch con feedback `Alert`** (lezione 6a: niente errori silenziosi).
- **Apply = conferma con riepilogo** (scelta utente): il bottone Applica apre un `Modal` che riepiloga le operazioni + rassicura ("annullabile da HISTORY, eliminati in quarantena"); la conferma avvia il job di apply.
- `jobs-provider` esteso resta **retro-compatibile**: i consumer esistenti che leggono `scan`/`startScan`/`refresh` non cambiano; si aggiungono `apply`/`startApply`.
- Base URL backend: `NEXT_PUBLIC_API_BASE` (default `http://localhost:8010`). Spec: `docs/superpowers/specs/2026-06-28-djorganizer-chunk6c-plan-history-settings-design.md`.

---

## File Structure

```text
frontend/
  lib/api.ts                 # + tipi/funzioni plan/apply/history/settings
  components/
    jobs-provider.tsx        # + polling job apply (retro-compatibile)
    plan-ops.tsx             # NEW: operazioni raggruppate per tipo
    apply-modal.tsx          # NEW: modale di conferma apply
  app/
    settings/page.tsx        # SETTINGS (sostituisce placeholder)
    history/page.tsx         # HISTORY (sostituisce placeholder)
    plan/page.tsx            # PLAN (sostituisce placeholder)
```

---

## Task 1: Client API plan/apply/history/settings + jobs-provider esteso

**Files:**
- Modify: `frontend/lib/api.ts`
- Modify: `frontend/components/jobs-provider.tsx`

**Interfaces:**
- Produces (da `@/lib/api`): tipi `PlanOp`, `Conflict`, `PlanStats`, `Plan`, `ApplyResult`, `ApplyJobState`, `UndoResult`, `HistoryItem`, `RootTarget`, `Settings`; funzioni `buildPlan()`, `getPlan()`, `startApply()`, `applyStatus()`, `listHistory()`, `undoRun(id)`, `getSettings()`, `updateSettings(body)`, `setRootTarget(rootId, target)`.
- Produces (da `@/components/jobs-provider`): `useJobs()` → `{ scan, apply, startScan, startApply, refresh }` (`apply: ApplyJobState`, `startApply: () => Promise<void>`).

- [ ] **Step 1: Aggiungi tipi e funzioni in `lib/api.ts`**

In `frontend/lib/api.ts`, prima della sezione `// --- helpers`, aggiungi:

```ts
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
```

- [ ] **Step 2: Estendi `jobs-provider.tsx` col job di apply** (riscrittura completa del file)

```tsx
"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import {
  scanJobStatus, startScan as apiStartScan, applyStatus, startApply as apiStartApply,
  type ScanJobState, type ApplyJobState,
} from "@/lib/api";
import { EqMeter } from "./ui";

const IDLE = {
  status: "idle" as const, phase: null, processed: 0, total: 0,
  result: null, error: null, started_at: null, finished_at: null,
};

type JobsApi = {
  scan: ScanJobState;
  apply: ApplyJobState;
  startScan: (rootIds?: number[]) => Promise<void>;
  startApply: () => Promise<void>;
  refresh: () => void;
};

const JobsCtx = createContext<JobsApi>({
  scan: IDLE, apply: IDLE,
  startScan: async () => {}, startApply: async () => {}, refresh: () => {},
});

export function useJobs() {
  return useContext(JobsCtx);
}

/**
 * Poller globale dei job (scan + apply). Vive nello shell: il progresso è
 * mostrato in una barra fissa in basso finché un job è in corso. Scan e apply
 * sono mutuamente esclusivi lato backend (409).
 */
export function JobsProvider({ children }: { children: ReactNode }) {
  const [scan, setScan] = useState<ScanJobState>(IDLE);
  const [apply, setApply] = useState<ApplyJobState>(IDLE);
  const alive = useRef(true);

  const pollOnce = useCallback(async () => {
    try {
      const s = await scanJobStatus();
      if (alive.current) setScan(s);
    } catch { /* backend offline */ }
    try {
      const a = await applyStatus();
      if (alive.current) setApply(a);
    } catch { /* backend offline */ }
  }, []);

  const refresh = useCallback(() => { pollOnce(); }, [pollOnce]);

  const startScan = useCallback(async (rootIds?: number[]) => {
    const s = await apiStartScan(rootIds);
    setScan(s);
  }, []);
  const startApply = useCallback(async () => {
    const a = await apiStartApply();
    setApply(a);
  }, []);

  useEffect(() => {
    alive.current = true;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    pollOnce();
    const id = setInterval(pollOnce, 1500);
    return () => { alive.current = false; clearInterval(id); };
  }, [pollOnce]);

  const api = useMemo<JobsApi>(
    () => ({ scan, apply, startScan, startApply, refresh }),
    [scan, apply, startScan, startApply, refresh],
  );

  const active = scan.status === "running"
    ? { label: "Scansione", job: scan as ScanJobState | ApplyJobState }
    : apply.status === "running"
    ? { label: "Applicazione", job: apply as ScanJobState | ApplyJobState }
    : null;

  return (
    <JobsCtx.Provider value={api}>
      {children}
      {active && <GlobalProgress label={active.label} job={active.job} />}
    </JobsCtx.Provider>
  );
}

function GlobalProgress({ label, job }: { label: string; job: ScanJobState | ApplyJobState }) {
  const pct = job.total > 0 ? Math.round((job.processed / job.total) * 100) : null;
  return (
    <div className="fixed inset-x-0 bottom-0 z-40 border-t border-border-strong bg-surface px-4 py-2.5">
      <div className="mx-auto flex max-w-5xl items-center gap-4">
        <span className="whitespace-nowrap text-[10px] font-medium uppercase tracking-wider text-muted">
          {label}{job.phase ? ` · ${job.phase}` : ""}
        </span>
        <div className="flex-1"><EqMeter value={pct} className="h-6 w-full" /></div>
        <span className="tnum whitespace-nowrap text-[10px] text-muted">
          {job.processed}/{job.total || "?"}{pct != null ? ` · ${pct}%` : ""}
        </span>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Verifica lint e build**

Run: `cd frontend && npm run lint && npm run build`
Expected: verdi (i consumer esistenti di `useJobs().scan` restano validi).

- [ ] **Step 4: Commit**

```bash
cd ~/Develop/DjOrganizer01
git add frontend/lib/api.ts frontend/components/jobs-provider.tsx
git commit -m "feat(fe): client API plan/apply/history/settings + jobs-provider con job di apply"
```

---

## Task 2: Pagina SETTINGS

**Files:**
- Modify: `frontend/app/settings/page.tsx`

**Interfaces:**
- Consumes: `getSettings`, `updateSettings`, `setRootTarget`, `Settings`, `RootTarget` (Task 1); `PageLayout`; `Alert`, `Button` (`ui.tsx`).

- [ ] **Step 1: Sostituisci `frontend/app/settings/page.tsx`**

```tsx
"use client";

import { useCallback, useEffect, useState } from "react";
import { getSettings, updateSettings, setRootTarget, type Settings, type RootTarget } from "@/lib/api";
import { PageLayout } from "@/components/page-layout";
import { Alert, Button } from "@/components/ui";

// Valori d'esempio per l'anteprima client-side (approssimata: la resa reale con
// sanitizzazione è lato planner).
const SAMPLE: Record<string, string> = {
  artist: "ANNA", title: "Hidden Beauties", album: "Hidden Beauties",
  album_artist: "ANNA", genre: "House", year: "2023", label: "Diynamic",
  track_no: "1", comment: "",
};
function preview(tpl: string): string {
  return tpl.replace(/\{(\w+)\}/g, (_, k) => SAMPLE[k] ?? `{${k}}`);
}

export default function SettingsPage() {
  const [settings, setSettings] = useState<Settings | null>(null);
  const [offline, setOffline] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [naming, setNaming] = useState("");
  const [folder, setFolder] = useState("");

  const load = useCallback(() => {
    getSettings()
      .then((s) => { setSettings(s); setNaming(s.naming_template); setFolder(s.folder_template); setOffline(false); })
      .catch(() => setOffline(true));
  }, []);
  useEffect(() => { load(); }, [load]);

  const saveTemplates = async () => {
    setError(null);
    try { setSettings(await updateSettings({ naming_template: naming, folder_template: folder })); }
    catch (e) { setError(e instanceof Error ? e.message : "Errore"); }
  };
  const saveTarget = async (rootId: number, target: string) => {
    setError(null);
    try { setSettings(await setRootTarget(rootId, target.trim() || null)); }
    catch (e) { setError(e instanceof Error ? e.message : "Errore"); }
  };

  return (
    <PageLayout title="Settings">
      <div className="flex max-w-2xl flex-col gap-6">
        {offline && <Alert>Backend non raggiungibile. Avvia il server FastAPI.</Alert>}
        {error && <Alert>{error}</Alert>}

        {settings && (
          <>
            <label className="block">
              <span className="mb-1.5 block text-[10px] font-medium uppercase tracking-wider text-muted">template nome file</span>
              <input className="w-full border border-border bg-surface px-3 py-2 text-sm text-fg-strong focus:border-border-strong focus:outline-none"
                value={naming} onChange={(e) => setNaming(e.target.value)} />
              <span className="mt-1.5 block text-xs text-faint">anteprima: <span className="text-ok">{preview(naming) || "—"}.flac</span></span>
            </label>

            <label className="block">
              <span className="mb-1.5 block text-[10px] font-medium uppercase tracking-wider text-muted">template cartelle</span>
              <input className="w-full border border-border bg-surface px-3 py-2 text-sm text-fg-strong focus:border-border-strong focus:outline-none"
                value={folder} onChange={(e) => setFolder(e.target.value)} />
              <span className="mt-1.5 block text-xs text-faint">{folder.trim() ? <>anteprima: <span className="text-ok">{preview(folder)}/</span></> : "vuoto = niente sottocartelle"}</span>
            </label>

            <Button variant="outline" size="sm" className="self-start" onClick={saveTemplates}>salva template</Button>

            <div>
              <div className="mb-1 text-[10px] font-medium uppercase tracking-wider text-muted">dove organizzare (target per radice)</div>
              <p className="mb-3 text-xs text-faint">vuoto = organizza nella stessa cartella del file. Un path assoluto sposta là i file di quella radice.</p>
              <div className="flex flex-col gap-2">
                {settings.roots.map((r) => <RootRow key={r.id} root={r} onSave={saveTarget} />)}
              </div>
            </div>
          </>
        )}
      </div>
    </PageLayout>
  );
}

function RootRow({ root, onSave }: { root: RootTarget; onSave: (rootId: number, target: string) => Promise<void> }) {
  const [target, setTarget] = useState(root.target_root ?? "");
  const [busy, setBusy] = useState(false);
  const save = async () => { setBusy(true); try { await onSave(root.id, target); } finally { setBusy(false); } };
  return (
    <div className="flex items-center gap-2">
      <div className="min-w-0 flex-1">
        <div className="truncate text-xs text-fg-strong" title={root.path}>{root.path}</div>
        <div className="text-[10px] text-muted">{root.label || "—"}</div>
      </div>
      <input
        className="w-64 border border-border bg-bg px-2 py-1 text-[11px] text-fg placeholder:text-faint focus:border-border-strong focus:outline-none"
        value={target} onChange={(e) => setTarget(e.target.value)} placeholder="(stessa cartella)"
      />
      <Button variant="outline" size="sm" disabled={busy} onClick={save}>salva</Button>
    </div>
  );
}
```

- [ ] **Step 2: Verifica lint e build**

Run: `cd frontend && npm run lint && npm run build`
Expected: verdi.

- [ ] **Step 3: Commit**

```bash
cd ~/Develop/DjOrganizer01
git add frontend/app/settings/page.tsx
git commit -m "feat(fe): pagina SETTINGS — template con anteprima + target_root per radice"
```

---

## Task 3: Pagina HISTORY

**Files:**
- Modify: `frontend/app/history/page.tsx`

**Interfaces:**
- Consumes: `listHistory`, `undoRun`, `fmtDate`, `HistoryItem` (Task 1 + 6a); `useJobs` (per ricaricare a fine apply); `PageLayout`; `Alert`, `EmptyState` (`ui.tsx`); `cn`.

- [ ] **Step 1: Sostituisci `frontend/app/history/page.tsx`**

```tsx
"use client";

import { useCallback, useEffect, useState } from "react";
import { listHistory, undoRun, fmtDate, type HistoryItem } from "@/lib/api";
import { useJobs } from "@/components/jobs-provider";
import { PageLayout } from "@/components/page-layout";
import { Alert, EmptyState } from "@/components/ui";
import { cn } from "@/lib/cn";

export default function HistoryPage() {
  const { apply } = useJobs();
  const [runs, setRuns] = useState<HistoryItem[]>([]);
  const [offline, setOffline] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);

  const load = useCallback(() => {
    listHistory()
      .then((r) => { setRuns(r); setOffline(false); })
      .catch(() => setOffline(true));
  }, []);
  useEffect(() => { load(); }, [load]);
  // a fine apply compare una nuova run
  useEffect(() => { if (apply.status === "done") load(); }, [apply.status, load]);

  const onUndo = async (id: number) => {
    if (busyId !== null) return;
    setError(null); setBusyId(id);
    try { await undoRun(id); }
    catch (e) { setError(e instanceof Error ? e.message : "Errore"); }
    finally { setBusyId(null); load(); }
  };

  const applied = runs.filter((r) => r.status === "applied").length;
  const undone = runs.filter((r) => r.status === "undone").length;

  return (
    <PageLayout
      title="History"
      meta={`${runs.length} run`}
      marginaliaTitle="Riepilogo"
      marginalia={
        <div className="flex flex-col gap-4 text-xs">
          <div><div className="tnum text-2xl leading-none text-fg-strong">{applied}</div><div className="mt-1 text-[10px] uppercase tracking-wider text-muted">applicate</div></div>
          <div><div className="tnum text-2xl leading-none text-fg-strong">{undone}</div><div className="mt-1 text-[10px] uppercase tracking-wider text-muted">annullate</div></div>
        </div>
      }
    >
      <div className="flex flex-col gap-4">
        {offline && <Alert>Backend non raggiungibile. Avvia il server FastAPI.</Alert>}
        {error && <Alert>{error}</Alert>}

        {runs.length === 0 && !offline ? (
          <EmptyState title="Nessuna run">Applica un piano da PLAN per vederlo qui.</EmptyState>
        ) : (
          <div className="overflow-x-auto border border-border">
            <table className="w-full border-collapse text-xs">
              <thead>
                <tr className="border-b border-border text-left text-[9px] uppercase tracking-wider text-faint">
                  <th className="px-3 py-2 font-normal">Run</th>
                  <th className="px-3 py-2 font-normal">Quando</th>
                  <th className="px-3 py-2 text-right font-normal">Operazioni</th>
                  <th className="px-3 py-2 font-normal">Stato</th>
                  <th className="px-3 py-2" />
                </tr>
              </thead>
              <tbody>
                {runs.map((r) => (
                  <tr key={r.id} className="border-b border-surface-2 last:border-0">
                    <td className="px-3 py-2 text-fg-strong">#{r.id}</td>
                    <td className="px-3 py-2 text-muted">{fmtDate(r.created_at)}</td>
                    <td className="tnum px-3 py-2 text-right text-fg">{r.n_ops}</td>
                    <td className="px-3 py-2">
                      <span className={cn("border border-border px-2 py-0.5 text-[9px] uppercase tracking-wider",
                        r.status === "applied" ? "text-ok" : "text-faint")}>
                        {r.status === "applied" ? "applicata" : "annullata"}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-right">
                      {r.status === "applied" ? (
                        <button
                          disabled={busyId !== null}
                          onClick={() => onUndo(r.id)}
                          className="border border-border px-2 py-0.5 text-[10px] text-muted hover:bg-elevated disabled:opacity-40"
                        >↺ annulla</button>
                      ) : (
                        <span className="text-faint">—</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </PageLayout>
  );
}
```

- [ ] **Step 2: Verifica lint e build**

Run: `cd frontend && npm run lint && npm run build`
Expected: verdi.

- [ ] **Step 3: Commit**

```bash
cd ~/Develop/DjOrganizer01
git add frontend/app/history/page.tsx
git commit -m "feat(fe): pagina HISTORY — run applicate/annullate + undo"
```

---

## Task 4: Pagina PLAN (operazioni + apply con conferma)

**Files:**
- Create: `frontend/components/plan-ops.tsx`
- Create: `frontend/components/apply-modal.tsx`
- Modify: `frontend/app/plan/page.tsx`

**Interfaces:**
- Consumes: `buildPlan`, `getPlan`, `Plan`, `PlanOp`, `PlanStats`, `ApplyResult` (Task 1); `useJobs` → `{ apply, startApply, refresh }` (Task 1); `PageLayout`; `Modal`, `Button`, `Alert`, `EmptyState`, `EqMeter` (`ui.tsx`); `cn`.
- Produces: `PlanOps` (consumato solo da PLAN), `ApplyModal` (consumato solo da PLAN).

- [ ] **Step 1: Crea `frontend/components/plan-ops.tsx`**

```tsx
"use client";

import { type PlanOp } from "@/lib/api";
import { cn } from "@/lib/cn";

const GROUPS: { kind: string; label: string }[] = [
  { kind: "RETAG", label: "Retag" },
  { kind: "RENAME", label: "Rinomina" },
  { kind: "MOVE", label: "Sposta" },
  { kind: "DELETE", label: "Elimina" },
];

function basename(p: string): string {
  const i = p.lastIndexOf("/");
  return i >= 0 ? p.slice(i + 1) : p;
}

function OpRow({ op }: { op: PlanOp }) {
  const isDelete = op.kind === "DELETE";
  return (
    <div className={cn("flex items-baseline gap-3 border border-t-0 border-surface-2 px-3 py-1.5 first:border-t",
      isDelete ? "border-l-2 border-l-danger" : "border-l-2 border-l-border")}>
      <span className="min-w-[200px] max-w-[200px] truncate text-[11px] text-muted" title={op.file_path}>{basename(op.file_path)}</span>
      <span className="text-[11px]">
        {op.kind === "RETAG" ? (
          Object.keys(op.after).map((f, i) => (
            <span key={f}>
              {i > 0 ? " · " : ""}{f}: <span className="text-faint">{String(op.before[f] ?? "—")}</span>
              {" → "}<span className="text-fg-strong">{String(op.after[f] ?? "—")}</span>
            </span>
          ))
        ) : isDelete ? (
          <span><span className="text-faint">→</span> <span className="text-warning">quarantena</span></span>
        ) : (
          <span><span className="text-faint">→</span> <span className="text-fg-strong">{String(op.after.path ?? "")}</span></span>
        )}
      </span>
    </div>
  );
}

export function PlanOps({ ops }: { ops: PlanOp[] }) {
  return (
    <div className="flex flex-col gap-5">
      {GROUPS.map(({ kind, label }) => {
        const group = ops.filter((o) => o.kind === kind);
        if (group.length === 0) return null;
        return (
          <div key={kind}>
            <div className="mb-2 text-[11px] uppercase tracking-wider text-fg-strong">
              {label} <span className="text-muted">· {group.length}</span>
            </div>
            <div className="flex flex-col">{group.map((o) => <OpRow key={o.id} op={o} />)}</div>
          </div>
        );
      })}
    </div>
  );
}
```

- [ ] **Step 2: Crea `frontend/components/apply-modal.tsx`**

```tsx
"use client";

import { Modal, Button } from "./ui";
import { type PlanStats } from "@/lib/api";

function mb(bytes: number): string {
  return `${Math.round(bytes / (1024 * 1024))} MB`;
}

export function ApplyModal({ open, onClose, stats, onConfirm }: {
  open: boolean;
  onClose: () => void;
  stats: PlanStats | undefined;
  onConfirm: () => void;
}) {
  if (!stats) return null;
  const total = stats.n_retag + stats.n_rename + stats.n_move + stats.n_delete;
  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Applicare il piano?"
      footer={
        <>
          <Button variant="ghost" size="sm" onClick={onClose}>Annulla</Button>
          <Button variant="danger" size="sm" onClick={onConfirm}>▶ Applica {total} operazioni</Button>
        </>
      }
    >
      <div className="flex flex-col gap-2 text-sm">
        <Row k="retag (tag corretti)" v={stats.n_retag} />
        <Row k="rinomina" v={stats.n_rename} />
        <Row k="sposta" v={stats.n_move} />
        <Row k="elimina (doppioni)" v={stats.n_delete} />
        <Row k="spazio liberato" v={`≈ ${mb(stats.space_freed_bytes)}`} />
        <div className="mt-2 border border-border px-3 py-2 text-xs text-ok">
          ✓ Tutto annullabile da HISTORY. Gli eliminati vanno in quarantena, non cancellati.
        </div>
      </div>
    </Modal>
  );
}

function Row({ k, v }: { k: string; v: string | number }) {
  return (
    <div className="flex justify-between">
      <span className="text-muted">{k}</span>
      <span className="tnum text-fg-strong">{v}</span>
    </div>
  );
}
```

- [ ] **Step 3: Sostituisci `frontend/app/plan/page.tsx`**

```tsx
"use client";

import { useCallback, useEffect, useState } from "react";
import { buildPlan, getPlan, type Plan, type PlanStats, type ApplyResult } from "@/lib/api";
import { useJobs } from "@/components/jobs-provider";
import { PageLayout } from "@/components/page-layout";
import { PlanOps } from "@/components/plan-ops";
import { ApplyModal } from "@/components/apply-modal";
import { Alert, Button, EmptyState, EqMeter } from "@/components/ui";

export default function PlanPage() {
  const { apply, startApply, refresh } = useJobs();
  const [plan, setPlan] = useState<Plan | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [building, setBuilding] = useState(false);
  const [offline, setOffline] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [modal, setModal] = useState(false);

  const load = useCallback(() => {
    getPlan()
      .then((p) => { setPlan(p); setOffline(false); })
      .catch((e) => {
        // 404 = nessun draft; un fallimento di rete è offline
        setPlan(null);
        if (e instanceof Error && /fetch|network|raggiung/i.test(e.message)) setOffline(true);
      })
      .finally(() => setLoaded(true));
  }, []);
  useEffect(() => { load(); }, [load]);
  // a fine apply il draft è consumato → pulisci la vista e aggiorna i conteggi
  useEffect(() => {
    if (apply.status === "done") { setPlan(null); refresh(); }
  }, [apply.status, refresh]);

  const rebuild = async () => {
    setError(null); setBuilding(true);
    try { setPlan(await buildPlan()); setOffline(false); }
    catch (e) { setError(e instanceof Error ? e.message : "Errore"); }
    finally { setBuilding(false); }
  };

  const confirmApply = async () => {
    setModal(false); setError(null);
    try { await startApply(); }
    catch (e) { setError(e instanceof Error ? e.message : "Errore"); }
  };

  const stats = plan?.stats;
  const blocking = stats?.blocking ?? false;
  const nOps = plan?.ops.length ?? 0;
  const applying = apply.status === "running";
  const result = apply.status === "done" ? apply.result : null;

  return (
    <PageLayout
      title="Plan"
      meta={plan ? `${nOps} operazioni` : undefined}
      marginaliaTitle={plan && stats ? "Operazioni" : undefined}
      marginalia={
        plan && stats ? (
          <Marginalia stats={stats} disabled={blocking || nOps === 0 || applying} onApply={() => setModal(true)} />
        ) : undefined
      }
    >
      <div className="flex flex-col gap-4">
        {offline && <Alert>Backend non raggiungibile. Avvia il server FastAPI.</Alert>}
        {error && <Alert>{error}</Alert>}

        <div className="flex items-center gap-3">
          <Button variant="outline" size="sm" onClick={rebuild} disabled={building || applying}>
            ↻ {plan ? "ricostruisci" : "costruisci"} il piano
          </Button>
          {building && <span className="text-xs text-muted">calcolo…</span>}
        </div>

        {applying && (
          <div className="flex flex-col gap-2 border border-border bg-surface px-4 py-3">
            <div className="flex items-center justify-between">
              <span className="text-xs uppercase tracking-wider text-fg-strong">Applicazione in corso{apply.phase ? ` · ${apply.phase}` : ""}</span>
              <span className="tnum text-xs text-fg-strong">{apply.processed} / {apply.total || "?"}</span>
            </div>
            <EqMeter value={apply.total > 0 ? Math.round((apply.processed / apply.total) * 100) : null} className="h-6 w-full" />
          </div>
        )}

        {result && <ApplyResultBanner result={result} />}

        {blocking && plan && (
          <div className="border border-danger px-4 py-3">
            <div className="text-xs font-semibold uppercase tracking-wider text-danger">{plan.conflicts.length} conflitti bloccanti</div>
            <div className="mt-2 flex flex-col gap-1 text-xs text-muted">
              {plan.conflicts.map((c, i) => <div key={i}>· {c.detail}</div>)}
            </div>
            <div className="mt-2 text-[11px] text-faint">Risolvi in ISSUES / DUPLICATES / SETTINGS, poi ricostruisci.</div>
          </div>
        )}

        {!loaded ? null
          : plan && nOps > 0 ? <PlanOps ops={plan.ops} />
          : plan && nOps === 0 ? <EmptyState title="Niente da applicare">Accetta delle issue o scegli i doppioni, poi ricostruisci.</EmptyState>
          : !applying && !result ? <EmptyState title="Nessun piano">Costruisci il piano dalle tue decisioni in ISSUES e DUPLICATES.</EmptyState>
          : null}
      </div>

      <ApplyModal open={modal} onClose={() => setModal(false)} stats={stats} onConfirm={confirmApply} />
    </PageLayout>
  );
}

function Marginalia({ stats, disabled, onApply }: { stats: PlanStats; disabled: boolean; onApply: () => void }) {
  return (
    <div className="flex flex-col gap-4 text-xs">
      <div className="flex flex-col gap-1.5">
        <Row k="retag" v={stats.n_retag} />
        <Row k="rinomina" v={stats.n_rename} />
        <Row k="sposta" v={stats.n_move} />
        <Row k="elimina" v={stats.n_delete} />
        <Row k="spazio liberato" v={`${Math.round(stats.space_freed_bytes / (1024 * 1024))} MB`} ok />
        <Row k="conflitti" v={stats.n_conflicts} danger={stats.n_conflicts > 0} />
      </div>
      <Button variant="danger" onClick={onApply} disabled={disabled} className="w-full">▶ Applica il piano</Button>
      <p className="text-[10px] leading-relaxed text-faint">Apre un riepilogo di conferma. Tutto annullabile da HISTORY; gli eliminati vanno in quarantena.</p>
    </div>
  );
}

function Row({ k, v, ok, danger }: { k: string; v: string | number; ok?: boolean; danger?: boolean }) {
  return (
    <div className="flex justify-between">
      <span className="text-muted">{k}</span>
      <span className={`tnum ${danger ? "text-danger" : ok ? "text-ok" : "text-fg-strong"}`}>{v}</span>
    </div>
  );
}

function ApplyResultBanner({ result }: { result: ApplyResult }) {
  const ok = !result.refused && !result.partial && !result.error;
  return (
    <div className={`border px-4 py-3 text-xs ${ok ? "border-border" : "border-danger"}`}>
      {result.refused ? (
        <span className="text-danger">Apply rifiutato{result.reason ? `: ${result.reason}` : ""}.</span>
      ) : result.partial ? (
        <span className="text-danger">Applicate {result.applied_ops} operazioni, fermato all&apos;op #{result.failed_op_seq}{result.error ? `: ${result.error}` : ""}.</span>
      ) : result.error ? (
        <span className="text-danger">Errore: {result.error}</span>
      ) : (
        <span className="text-ok">✓ Applicate {result.applied_ops} operazioni · run #{result.run_id}. Vedi HISTORY per annullare.</span>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Verifica lint e build**

Run: `cd frontend && npm run lint && npm run build`
Expected: verdi.

- [ ] **Step 5: Verifica live** (best-effort, non bloccante)

Con backend + `npm run dev` e una libreria scansionata + decisioni prese (issue accettate / doppioni scelti), apri `/plan`: "costruisci il piano" mostra le operazioni raggruppate + stat; "Applica" apre il modale con riepilogo; confermando parte il job (EqMeter) e a fine vedi il risultato; con conflitti bloccanti il banner rosso compare e Applica è disabilitato.

- [ ] **Step 6: Commit**

```bash
cd ~/Develop/DjOrganizer01
git add frontend/components/plan-ops.tsx frontend/components/apply-modal.tsx frontend/app/plan/page.tsx
git commit -m "feat(fe): pagina PLAN — operazioni per tipo, conflitti, apply con modale di conferma"
```

---

## Self-Review

**1. Spec coverage:**
- PLAN: build/rebuild, ops per tipo, conflitti bloccanti+disable apply, stat, apply con modale → job → risultato → Task 4 ✓
- HISTORY: run + undo → Task 3 ✓
- SETTINGS: template con anteprima + target per radice → Task 2 ✓
- Client API plan/apply/history/settings → Task 1 ✓
- jobs-provider esteso al job di apply (retro-compatibile) → Task 1 ✓
- Errori/offline/empty (try/catch su ogni mutazione) → Task 2, 3, 4 ✓
- Nessuna modifica backend; suite resta verde → rispettato (nessun task tocca `backend/`) ✓
- Test: lint+build per il frontend ✓

**2. Placeholder scan:** nessun TBD/TODO; codice completo in ogni step. La verifica "live" del Task 4 è best-effort non bloccante (gate = lint+build), come in 6a/6b.

**3. Type consistency:**
- `Plan`/`PlanOp`/`PlanStats`/`Conflict` (api.ts) ↔ `PlanRead`/`PlanOpRead`/`PlanStats`/`ConflictRead` Pydantic ✓
- `ApplyResult` ↔ `ApplyResult` Pydantic; `ApplyJobState` = shape di `apply_job.job_state()` ✓
- `HistoryItem` ↔ `HistoryItem`; `UndoResult` ↔ `UndoResult` ✓
- `Settings`/`RootTarget` ↔ `SettingsRead`/`RootTargetRead`; `updateSettings` → `SettingsUpdate`; `setRootTarget` body `{target_root}` ↔ `RootTargetUpdate` ✓
- `useJobs()` ora `{ scan, apply, startScan, startApply, refresh }`; i consumer 6a/6b leggono solo `scan`/`startScan`/`refresh` → invariati ✓
- `PlanOps`/`ApplyModal` props coerenti con i tipi (PlanOp[], PlanStats) ✓
- token `text-ok`/`text-warning`/`text-danger` già definiti (6a/6b) ✓

---

## Execution Handoff

Piano completo e salvato in `docs/superpowers/plans/2026-06-28-djorganizer-chunk6c-plan-history-settings.md`.
