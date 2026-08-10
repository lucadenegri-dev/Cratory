# Unify Sources + Files (with auto-scan after Apply) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Merge the `Sources` nav entry into `Files` (sources become a dropdown that both filters and manages), keep the Scan action always visible, and auto-scan the library after a successful Apply.

**Architecture:** Pure frontend change (Next.js App Router). A new `SourceMenu` disclosure component absorbs the sources list + per-row scan/delete + `AddSource`. The `Files` page hosts it, owns the roots state (moved from the old Sources page), and gains an always-visible Scan button plus a scan-result strip. `/sources` becomes a client redirect to `/files`, and the nav drops the entry. Auto-scan lives in `jobs-provider` as a global running→done edge trigger on Apply. The backend already accepts `root_ids` on `POST /api/scan`, so no backend change.

**Tech Stack:** Next.js 16 (App Router), React 19, Tailwind v4, TypeScript. i18n via `frontend/lib/i18n` (`en.ts` source of truth, `it.ts` typed as `typeof en`).

## Global Constraints

- No frontend unit-test framework exists. The automated gate per task is `npm run build` (Next build = typecheck) and `npm run lint`, both run from `frontend/`. Behavioural verification is done in the browser preview.
- i18n rule: add every new key to `frontend/lib/i18n/en.ts` **first**, then mirror it in `frontend/lib/i18n/it.ts` in the same commit — a missing key is a TypeScript error (it.ts is typed `as typeof en`), so the build fails otherwise.
- Backend must stay green as regression: `backend/.venv/bin/python -m pytest backend/tests -q` (use the project venv, Python 3.11 — system 3.9 breaks on `X | None`). No backend files are modified by this plan.
- Match surrounding language: code comments/docstrings in this repo are Italian. Keep new comments Italian.
- Historical identifiers are frozen (`DJORG_` prefix, `djorganizer.db`, theme storage key) — do not touch.

---

### Task 1: Add i18n keys for the unified Files UI

**Files:**
- Modify: `frontend/lib/i18n/en.ts` (the `files: { … }` block)
- Modify: `frontend/lib/i18n/it.ts` (the `files: { … }` block)

**Interfaces:**
- Produces (consumed by Tasks 2–3): `t.files.allSourcesN(n)`, `t.files.allSourcesRow`, `t.files.scanRootAria`, `t.files.scanAll`, `t.files.scanOne(label)`. Also updated copy for `t.files.emptyBody`.

- [ ] **Step 1: Add the new keys to `en.ts`**

In `frontend/lib/i18n/en.ts`, inside the `files: {` object, add these five keys (put them right after the `allRoots:` line) and change `emptyBody`:

```ts
    allRoots: "all roots",
    allSourcesN: (n: number) => (n === 1 ? "All sources · 1" : `All sources · ${n}`),
    allSourcesRow: "All sources",
    scanRootAria: "Rescan this source",
    scanAll: "▶ Scan all",
    scanOne: (label: string) => `▶ Scan ${label}`,
```

Change the existing `emptyBody` line in the `files` block from:

```ts
    emptyBody: "Add a root in Sources and run a scan.",
```

to:

```ts
    emptyBody: "Add a source and run a scan.",
```

- [ ] **Step 2: Mirror the keys in `it.ts`**

In `frontend/lib/i18n/it.ts`, inside the `files: {` object, add after the `allRoots:` line (currently line ~181):

```ts
    allRoots: "tutte le radici",
    allSourcesN: (n: number) => (n === 1 ? "Tutte le sorgenti · 1" : `Tutte le sorgenti · ${n}`),
    allSourcesRow: "Tutte le sorgenti",
    scanRootAria: "Ri-scansiona questa sorgente",
    scanAll: "▶ Scansiona tutto",
    scanOne: (label: string) => `▶ Scansiona ${label}`,
```

Change the existing `emptyBody` in the `files` block (currently line ~192) from:

```ts
    emptyBody: "Aggiungi una radice in Sources e lancia uno scan.",
```

to:

```ts
    emptyBody: "Aggiungi una sorgente e lancia una scansione.",
```

- [ ] **Step 3: Verify build + lint pass**

Run (from `frontend/`):

```bash
npm run build && npm run lint
```

Expected: build succeeds, no type error about missing keys in `it.ts`.

- [ ] **Step 4: Commit**

```bash
git add frontend/lib/i18n/en.ts frontend/lib/i18n/it.ts
git commit -m "i18n: chiavi per la pagina Files unificata (sorgenti + scan)"
```

---

### Task 2: Create the `SourceMenu` component

**Files:**
- Create: `frontend/components/source-menu.tsx`

**Interfaces:**
- Consumes: `ScanRoot` + `fmtDate` from `@/lib/api`; `AddSource` from `./add-source`; `useJobs` from `./jobs-provider`; `cn` from `@/lib/cn`; `t.files.*` (Task 1), `t.sources.missingCount`, `t.sources.removeRoot`.
- Produces (consumed by Task 3): component
  `SourceMenu({ roots, selectedId, onSelect, onScanRoot, onDelete, onAdded, deletingId })` where
  `roots: ScanRoot[]`, `selectedId: number | null`,
  `onSelect: (id: number | null) => void`, `onScanRoot: (id: number) => void`,
  `onDelete: (id: number) => void`, `onAdded: () => void`,
  `deletingId: number | null`.

- [ ] **Step 1: Write the component**

Create `frontend/components/source-menu.tsx` with exactly:

```tsx
"use client";

import { useEffect, useRef, useState } from "react";
import { fmtDate, type ScanRoot } from "@/lib/api";
import { AddSource } from "./add-source";
import { useJobs } from "./jobs-provider";
import { cn } from "@/lib/cn";
import { useT } from "@/lib/i18n";

// Tendina sorgenti: filtra i file (selezione riga) e gestisce le radici
// (scan/elimina per riga + aggiungi). Sostituisce la vecchia pagina Sources.
export function SourceMenu({
  roots, selectedId, onSelect, onScanRoot, onDelete, onAdded, deletingId,
}: {
  roots: ScanRoot[];
  selectedId: number | null;
  onSelect: (id: number | null) => void;
  onScanRoot: (id: number) => void;
  onDelete: (id: number) => void;
  onAdded: () => void;
  deletingId: number | null;
}) {
  const t = useT();
  const { scan } = useJobs();
  const running = scan.status === "running";
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  // chiudi cliccando fuori dalla tendina
  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);

  const selected = roots.find((r) => r.id === selectedId) ?? null;
  const triggerLabel = selected
    ? (selected.label || selected.path)
    : t.files.allSourcesN(roots.length);

  const select = (id: number | null) => { onSelect(id); setOpen(false); };

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-2 border border-border bg-bg px-2 py-1 text-[11px] text-fg-strong hover:border-border-strong"
      >
        <span className="text-faint">▾</span>
        <span className="max-w-[16rem] truncate">{triggerLabel}</span>
      </button>

      {open && (
        <div className="absolute left-0 z-20 mt-1 w-80 border border-border bg-bg shadow-lg">
          <ul className="max-h-72 overflow-y-auto">
            <li>
              <button
                onClick={() => select(null)}
                className={cn(
                  "flex w-full items-center justify-between px-3 py-2 text-left text-xs hover:bg-elevated",
                  selectedId === null ? "text-fg-strong" : "text-muted",
                )}
              >
                <span>{t.files.allSourcesRow}</span>
                <span className="tnum text-faint">
                  {roots.reduce((a, r) => a + r.file_count, 0)}
                </span>
              </button>
            </li>
            {roots.map((r) => (
              <li key={r.id} className="border-t border-surface-2">
                <div
                  className={cn(
                    "flex items-center gap-2 px-3 py-2 text-xs",
                    selectedId === r.id && "bg-surface-2",
                  )}
                >
                  <button onClick={() => select(r.id)} className="min-w-0 flex-1 text-left">
                    <span className="block truncate text-fg-strong">{r.label || r.path}</span>
                    <span className="block text-[10px] text-faint">
                      {r.file_count} · {fmtDate(r.last_scanned_at)}
                      {r.missing_count > 0 && ` · ${t.sources.missingCount(r.missing_count)}`}
                    </span>
                  </button>
                  <button
                    onClick={() => onScanRoot(r.id)}
                    disabled={running}
                    aria-label={t.files.scanRootAria}
                    className="text-faint transition-colors hover:text-fg disabled:cursor-not-allowed disabled:opacity-40"
                  >⟳</button>
                  <button
                    onClick={() => onDelete(r.id)}
                    disabled={deletingId === r.id}
                    aria-label={t.sources.removeRoot}
                    className="text-faint transition-colors hover:text-danger disabled:cursor-not-allowed disabled:opacity-40"
                  >×</button>
                </div>
              </li>
            ))}
          </ul>
          <div className="border-t border-border p-3">
            <AddSource onAdded={onAdded} />
          </div>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Verify build + lint pass**

Run (from `frontend/`):

```bash
npm run build && npm run lint
```

Expected: build succeeds. (The component compiles even though it is not yet mounted; Task 3 wires it in.)

- [ ] **Step 3: Commit**

```bash
git add frontend/components/source-menu.tsx
git commit -m "feat(files): componente SourceMenu (tendina sorgenti filtro+gestione)"
```

---

### Task 3: Host `SourceMenu` in the Files page + always-visible Scan + scan-result strip

**Files:**
- Modify: `frontend/app/files/page.tsx`

**Interfaces:**
- Consumes: `SourceMenu` (Task 2); `useJobs().startScan`, `useJobs().scan`; `listSources`, `deleteSource` from `@/lib/api`; `t.files.scanAll`, `t.files.scanOne`, `t.sources.*` (scanning, statFound…statErrors, guideFolders/guideAddPre/guideAddPost).
- Produces: the unified page (terminal — nothing downstream depends on its internals).

- [ ] **Step 1: Update imports**

In `frontend/app/files/page.tsx`, replace the current api import block and add the new component/handlers. Change the top imports (lines 3–12) to:

```tsx
import { useCallback, useEffect, useState } from "react";
import {
  listFiles, libraryStats, listSources, libraryFacets, deleteSource,
  type FileRow, type LibraryStats, type LibraryFacets, type ScanRoot, type FileQuery,
} from "@/lib/api";
import { useJobs } from "@/components/jobs-provider";
import { PageLayout } from "@/components/page-layout";
import { FilesTable } from "@/components/files-table";
import { SourceMenu } from "@/components/source-menu";
import { Alert, Button, EmptyState, Input, Loading, Select, Spinner } from "@/components/ui";
import { useT } from "@/lib/i18n";
```

- [ ] **Step 2: Add roots-management state + handlers, and scan wiring**

Replace the destructure `const { scan } = useJobs();` (line ~48) with:

```tsx
  const { scan, startScan, refresh } = useJobs();
```

Then, immediately after the existing `setTagField` definition (line ~63), add:

```tsx
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const loadRoots = useCallback(() => {
    listSources().then(setRoots).catch(() => {});
  }, []);

  const selectedRoot = rootId ? roots.find((r) => r.id === Number(rootId)) ?? null : null;
  const running = scan.status === "running";

  const onScan = async () => {
    setActionError(null);
    try {
      await startScan(rootId ? [Number(rootId)] : undefined);
      refresh();
    } catch (e) {
      setActionError(e instanceof Error ? e.message : t.sources.scanStartFailed);
    }
  };
  const onScanRoot = async (id: number) => {
    setActionError(null);
    try {
      await startScan([id]);
      refresh();
    } catch (e) {
      setActionError(e instanceof Error ? e.message : t.sources.scanStartFailed);
    }
  };
  const onDeleteRoot = async (id: number) => {
    if (deletingId !== null) return;
    setActionError(null);
    setDeletingId(id);
    try {
      await deleteSource(id);
    } catch (e) {
      setActionError(e instanceof Error ? e.message : t.sources.rootRemoveFailed);
    } finally {
      setDeletingId(null);
      loadRoots();
    }
  };
```

- [ ] **Step 3: Use `loadRoots` for the roots effect**

Replace the existing roots effect (line ~91):

```tsx
  useEffect(() => { listSources().then(setRoots).catch(() => {}); }, []);
```

with:

```tsx
  useEffect(() => { loadRoots(); }, [loadRoots]);
```

- [ ] **Step 4: Swap the root `<Select>` for `SourceMenu` + add the Scan button and error alert**

In the JSX, replace the first filter row — the block that starts with the root `<Select>` (lines ~114–121, the `<Select value={rootId} …>` … `</Select>` for `allRoots`, but **keep** the `onlyIssues` Select, `sort` Select and search `Input`). Concretely, change the opening of the first `<div className="flex flex-wrap items-center gap-2">` filter row so its first two children become the `SourceMenu` and the Scan `Button`:

```tsx
        {actionError && <Alert>{actionError}</Alert>}

        <div className="flex flex-wrap items-center gap-2">
          <SourceMenu
            roots={roots}
            selectedId={rootId ? Number(rootId) : null}
            onSelect={(id) => setRootId(id === null ? "" : String(id))}
            onScanRoot={onScanRoot}
            onDelete={onDeleteRoot}
            onAdded={loadRoots}
            deletingId={deletingId}
          />
          <Button onClick={onScan} disabled={running || roots.length === 0}>
            {running && <Spinner />}
            {running
              ? t.sources.scanning
              : selectedRoot
                ? t.files.scanOne(selectedRoot.label || selectedRoot.path)
                : t.files.scanAll}
          </Button>
          <Select value={onlyIssues ? "issues" : "all"} onChange={(e) => setOnlyIssues(e.target.value === "issues")} className="w-auto">
            <option value="all">{t.files.filterAll}</option>
            <option value="issues">{t.files.filterIssues}</option>
          </Select>
          <Select value={sort} onChange={(e) => setSort(e.target.value as FileQuery["sort"])} className="w-auto">
            <option value="path">{t.files.sortPath}</option>
            <option value="artist">{t.files.sortArtist}</option>
            <option value="title">{t.files.sortTitle}</option>
            <option value="bitrate">{t.files.sortBitrate}</option>
            <option value="duration">{t.files.sortDuration}</option>
          </Select>
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t.files.searchPlaceholder} className="w-48" />
        </div>
```

(The old `<Select value={rootId} …>` with `t.files.allRoots` is fully removed — `SourceMenu` replaces it. `t.files.allRoots` may now be unused; leave the key in place, it is harmless.)

- [ ] **Step 5: Add the scan-result strip below the top filter rows**

Immediately after the facet row `</div>` (the second `flex flex-wrap` block, ends ~line 146) and before the `{!loaded ? …}` table block, insert:

```tsx
        {scan.result && (
          <div className="flex flex-wrap gap-x-4 gap-y-1 border border-border px-3 py-2 text-[11px]">
            <ScanStat k={t.sources.statFound} v={scan.result.found} />
            <ScanStat k={t.sources.statNew} v={`+${scan.result.inserted}`} />
            <ScanStat k={t.sources.statUpdated} v={scan.result.updated} />
            <ScanStat k={t.sources.statMoved} v={scan.result.moved} />
            <ScanStat k={t.sources.statMissing} v={scan.result.missing} />
            <ScanStat k={t.sources.statErrors} v={scan.result.errors} danger={scan.result.errors > 0} />
          </div>
        )}
```

- [ ] **Step 6: Merge the two Guides and add the `ScanStat` helper**

Replace the `guide` prop of `<PageLayout>` (lines ~104–108) with the merged guide:

```tsx
      guide={<>
        <p>{t.sources.guideFolders}</p>
        <p>{t.files.guide2}</p>
        <p>{t.files.guide3}</p>
      </>}
```

Then add this helper at the bottom of the file, after the `Stat` function:

```tsx
function ScanStat({ k, v, danger }: { k: string; v: string | number; danger?: boolean }) {
  return (
    <span className="flex items-center gap-1">
      <span className="text-muted">{k}</span>
      <span className={`tnum ${danger ? "text-danger" : "text-fg"}`}>{v}</span>
    </span>
  );
}
```

- [ ] **Step 7: Verify build + lint pass**

Run (from `frontend/`):

```bash
npm run build && npm run lint
```

Expected: build succeeds, no unused-import lint error (all of `Button`, `Spinner`, `deleteSource` are now used).

- [ ] **Step 8: Verify in the browser preview**

Start the frontend preview (dev server per `.claude/launch.json`, or `npm run dev`) with the backend running on `:8010`. Navigate to `/files`. Confirm:
- the source dropdown opens, lists roots + "All sources", and `Add source` is at the bottom;
- clicking a source row filters the table and closes the dropdown; the trigger shows that source's label;
- the `Scan` button label reads `Scan all` with no selection, `Scan <label>` with one;
- per-row ⟳ starts a scan (jobs bar appears), × deletes a source;
- after a scan finishes, the scan-result strip appears under the filters.

Take a screenshot as proof.

- [ ] **Step 9: Commit**

```bash
git add frontend/app/files/page.tsx
git commit -m "feat(files): tendina sorgenti + Scan sempre visibile + striscia risultato-scan"
```

---

### Task 4: Redirect `/sources` → `/files`, drop the nav entry, retire `SourcesTable`

**Files:**
- Modify (replace contents): `frontend/app/sources/page.tsx`
- Modify: `frontend/components/index-nav.tsx`
- Delete: `frontend/components/sources-table.tsx`

**Interfaces:**
- Consumes: `useRouter` from `next/navigation`.
- Produces: nav with 6 entries; `/sources` route that redirects.

- [ ] **Step 1: Turn the Sources page into a redirect**

Replace the **entire** contents of `frontend/app/sources/page.tsx` with:

```tsx
"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

// La pagina Sources è stata fusa in Files: qui solo un redirect per vecchi link.
export default function SourcesRedirect() {
  const router = useRouter();
  useEffect(() => { router.replace("/files"); }, [router]);
  return null;
}
```

- [ ] **Step 2: Remove the `Sources` nav entry and its counter**

In `frontend/components/index-nav.tsx`:

Change the `NAV` array (lines 13–21) to drop the `/sources` line:

```tsx
const NAV = [
  { href: "/files", label: "Files" },
  { href: "/issues", label: "Issues" },
  { href: "/duplicates", label: "Duplicates" },
  { href: "/plan", label: "Plan" },
  { href: "/history", label: "History" },
  { href: "/settings", label: "Settings" },
] as const;
```

Change the `counts` map (lines 44–52) to drop the `/sources` entry:

```tsx
  const counts: Record<string, string> = {
    "/files": stats ? String(stats.files_total) : "—",
    "/issues": stats ? String(sumIssues(stats)) : "—",
    "/duplicates": stats ? String(stats.dup_groups) : "—",
    "/plan": "—",
    "/history": "—",
    "/settings": "",
  };
```

Change the logo `Link` (line 59) target from `/sources` to `/files`:

```tsx
        <Link href="/files" className="block text-sm font-semibold tracking-[0.12em] text-fg-strong">
```

- [ ] **Step 3: Delete the now-unused `SourcesTable`**

```bash
git rm frontend/components/sources-table.tsx
```

- [ ] **Step 4: Verify build + lint pass**

Run (from `frontend/`):

```bash
npm run build && npm run lint
```

Expected: build succeeds; no dangling import of `sources-table` (Task confirmed it was only imported by the old `sources/page.tsx`, now replaced).

- [ ] **Step 5: Verify in the browser preview**

Reload the preview. Confirm:
- the left nav shows 6 entries, no `Sources`;
- visiting `/sources` immediately lands on `/files`;
- the `SORTORY` logo links to `/files`.

Screenshot the nav as proof.

- [ ] **Step 6: Commit**

```bash
git add frontend/app/sources/page.tsx frontend/components/index-nav.tsx
git commit -m "feat(nav): /sources redirige a /files; rimossa voce Sources e SourcesTable"
```

---

### Task 5: Auto-scan after a successful Apply

**Files:**
- Modify: `frontend/components/jobs-provider.tsx`

**Interfaces:**
- Consumes: existing `apply` state (`ApplyJobState`, fields `status`, `result.applied_ops`) and `startScan` — both already in `JobsProvider`.
- Produces: side-effect only (auto-triggered scan). No API surface change.

- [ ] **Step 1: Add the running→done edge effect**

In `frontend/components/jobs-provider.tsx`, the `startScan` callback is already defined (around line 77). After the block that defines `startIntegrity` and **before** the existing polling `useEffect` (the one that calls `pollOnce` on an interval, around line 100), add:

```tsx
  // Auto-scan dopo un Apply andato a buon fine: rileva il fronte running→done
  // e riscansiona (tutte le sorgenti) solo se sono state applicate operazioni.
  const prevApplyStatus = useRef<ApplyJobState["status"]>(apply.status);
  useEffect(() => {
    const was = prevApplyStatus.current;
    prevApplyStatus.current = apply.status;
    if (was === "running" && apply.status === "done" && (apply.result?.applied_ops ?? 0) > 0) {
      startScan().catch(() => { /* backend offline o scan già in corso (409) */ });
    }
  }, [apply.status, apply.result, startScan]);
```

(`useRef` and `useEffect` are already imported at the top of the file.)

- [ ] **Step 2: Verify build + lint pass**

Run (from `frontend/`):

```bash
npm run build && npm run lint
```

Expected: build succeeds.

- [ ] **Step 3: Verify the backend suite still green (regression)**

Run (from repo root):

```bash
backend/.venv/bin/python -m pytest backend/tests -q
```

Expected: PASS (no backend change; this guards against accidental drift).

- [ ] **Step 4: Verify in the browser preview**

With backend + frontend running and a non-empty Plan available: go to `/plan`, run Apply on a plan with at least one operation. Confirm that when Apply reaches `done`, a scan starts automatically (jobs bar switches from apply to scan). Then confirm an Apply with zero applied ops does **not** trigger a scan. Screenshot the jobs bar showing the auto-started scan.

- [ ] **Step 5: Commit**

```bash
git add frontend/components/jobs-provider.tsx
git commit -m "feat(jobs): auto-scan dopo un Apply con operazioni applicate"
```

---

## Self-Review

**Spec coverage:**
- Feature 1 §1.1 (nav 7→6, /sources redirect, counter) → Task 4. ✓
- Feature 1 §1.2 (top bar: dropdown + always-visible Scan + adaptive label + existing filters) → Task 3 Step 4. ✓
- Feature 1 §1.3 (SourceMenu: row select+close, All sources, per-row ⟳ scan, × delete, AddSource, click-outside) → Task 2. ✓
- Feature 1 §1.4 (library marginalia unchanged; scan-result strip; merged guide; empty state copy) → Task 3 Steps 5–6 + Task 1 (emptyBody). Marginalia left untouched. ✓
- Feature 1 §1.5 (new source-menu.tsx; files page host; sources redirect; retire SourcesTable; nav; i18n) → Tasks 1–4. ✓
- Feature 2 (auto-scan in jobs-provider, running→done edge, ops>0 guard) → Task 5. ✓

**Placeholder scan:** No TBD/TODO; every code step shows complete code. ✓

**Type consistency:** `SourceMenu` prop names (`selectedId`, `onSelect`, `onScanRoot`, `onDelete`, `onAdded`, `deletingId`) are identical in Task 2 (definition) and Task 3 Step 4 (usage). `startScan(rootIds?: number[])` used with `[Number(rootId)]` / `[id]` / `undefined` matches its signature. `apply.result?.applied_ops` matches `ApplyResult`. ✓
