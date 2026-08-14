# DjOrganizer Chunk 6b — ISSUES + DUPLICATES — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Costruire le pagine ISSUES (triage + correzione manuale inline plan-routed) e DUPLICATES (gruppi come card, scelta keeper, scarta/ripristina), più la piccola aggiunta backend che la correzione manuale richiede.

**Architecture:** Il backend ha già i router `issues` e `duplicates`; questo chunk aggiunge un solo endpoint (`POST /api/issues/{id}/fix`) e un campo (`root_id` su `IssueRead`), poi costruisce le due pagine frontend che consumano l'API esistente + le nuove funzioni del client. Tutte le decisioni (accetta/ignora/keeper/dismiss/fix) confluiscono nel PLAN (6c) — nessuna scrittura su disco in 6b.

**Tech Stack:** Backend — FastAPI, SQLAlchemy 2.0, Pydantic v2, pytest. Frontend — Next 16.2.9, React 19.2.4, Tailwind 4, TypeScript 5.

## Global Constraints

- Backend router **sottili**, read/write minimale, stile dei router esistenti (`select`, `Depends(get_db)`, `utcnow()`). Test **pristine** (`filterwarnings = error`); pattern: fixture `db` semina + `with TestClient(app) as client`.
- La correzione manuale è **plan-routed**: `/fix` imposta `suggested_fix_json` + `status="accepted"`, **non** scrive su disco. La forma del fix deve combaciare con ciò che `planner.effective_tags` consuma: `{"field": <field>, "action": "retag", "to": <value>}` (il `before` lo ricava il planner dal file).
- Campi **retaggabili** (gli unici fix manuali ammessi) = `artist, title, album, album_artist, genre, year, label, track_no, comment` (i `_EFFECTIVE_FIELDS` del planner).
- Status issue ammessi: `open`, `accepted`, `dismissed`. `accepted` via `/status` è permesso solo se la issue è auto-fixabile (ha `suggested_fix_json`); `/fix` invece imposta esso stesso il `suggested_fix_json`.
- Frontend: copia i pattern di 6a (client tipizzato, `useJobs`, `PageLayout`, `ui.tsx`, token `--c-*`). Il "test" frontend è **`npm run lint` + `npm run build` verdi** (NON pytest/TDD). Ogni mutazione utente ha **try/catch con feedback** (lezione 6a: niente errori silenziosi). Comandi npm da `frontend/`.
- Base URL backend: `NEXT_PUBLIC_API_BASE` (default `http://localhost:8010`). Spec: `docs/superpowers/specs/2026-06-28-djorganizer-chunk6b-issues-duplicates-design.md`.

---

## File Structure

**Backend:**
- Modify: `backend/app/schemas.py` — `IssueRead` + `root_id`; nuovo `IssueFixBody`
- Modify: `backend/app/routers/issues.py` — `_to_read` + root_id; nuovo endpoint `/fix`
- Test: `backend/tests/test_issues_api.py` — test `/fix` + `root_id`

**Frontend:**
- Modify: `frontend/lib/api.ts` — tipi + funzioni issues/duplicates; generalizza `apiGet` params
- Modify: `frontend/components/index-nav.tsx` — refresh conteggi al cambio pagina
- Modify: `frontend/app/globals.css` — token `--c-ok` (verde "tieni/accettato")
- Create: `frontend/components/issues-table.tsx` — tabella ISSUES + riga con fix inline
- Modify: `frontend/app/issues/page.tsx` — pagina ISSUES (sostituisce il placeholder)
- Create: `frontend/components/dup-group.tsx` — card di un gruppo doppioni
- Modify: `frontend/app/duplicates/page.tsx` — pagina DUPLICATES (sostituisce il placeholder)

---

## Task 1: Backend — `POST /api/issues/{id}/fix` + `root_id` su `IssueRead`

**Files:**
- Modify: `backend/app/schemas.py`
- Modify: `backend/app/routers/issues.py`
- Test: `backend/tests/test_issues_api.py`

**Interfaces:**
- Produces: `POST /api/issues/{id}/fix` body `{value: str}` → `IssueRead`. 404 se assente; 400 se `field` non retaggabile o `value` vuoto. Imposta `suggested_fix_json={"field":field,"action":"retag","to":value}` + `status="accepted"`. `IssueRead` ora include `root_id: int`.

- [ ] **Step 1: Scrivi i test che falliscono**

Aggiungi in `backend/tests/test_issues_api.py` (riusa `_seed` esistente, che crea file id=1 con due issue warning di tipo `missing_metadata`/`inconsistent_casing`):

```python
def test_issue_read_has_root_id(db):
    _seed(db)
    with TestClient(app) as client:
        rows = client.get("/api/issues").json()
        assert all("root_id" in r for r in rows)
        assert rows[0]["root_id"] == 1


def test_fix_sets_retag_and_accepts(db):
    _seed(db)
    with TestClient(app) as client:
        genre_id = client.get("/api/issues",
                              params={"type": "missing_metadata"}).json()[0]["id"]
        resp = client.post(f"/api/issues/{genre_id}/fix", json={"value": "House"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "accepted"
        assert body["suggested_fix_json"] == {"field": "genre",
                                              "action": "retag", "to": "House"}


def test_fix_rejects_non_retaggable_field(db):
    f = AudioFile(id=2, root_id=1, path="/m/b.mp3", ext="mp3", size_bytes=1,
                  hash_method="file", status="present", has_cover=False)
    db.add(f)
    db.add(Issue(file_id=2, type="bad_bitrate", field="file", severity="error",
                 detail="128<256", suggested_fix_json=None, status="open"))
    db.commit()
    with TestClient(app) as client:
        iid = client.get("/api/issues", params={"type": "bad_bitrate"}).json()[0]["id"]
        resp = client.post(f"/api/issues/{iid}/fix", json={"value": "x"})
        assert resp.status_code == 400


def test_fix_rejects_empty_value(db):
    _seed(db)
    with TestClient(app) as client:
        genre_id = client.get("/api/issues",
                              params={"type": "missing_metadata"}).json()[0]["id"]
        resp = client.post(f"/api/issues/{genre_id}/fix", json={"value": "   "})
        assert resp.status_code == 400


def test_fix_404(db):
    with TestClient(app) as client:
        assert client.post("/api/issues/999/fix", json={"value": "x"}).status_code == 404
```

Nota: il `missing_metadata` seminato ha `field="genre"` (vedi `_seed`).

- [ ] **Step 2: Lancia i test, verifica che falliscono**

Run: `cd backend && python -m pytest tests/test_issues_api.py -k "root_id or fix" -v`
Expected: FAIL (root_id assente; endpoint `/fix` 404 perché non esiste).

- [ ] **Step 3: Aggiungi `root_id` e `IssueFixBody` agli schemi**

In `backend/app/schemas.py`, nella classe `IssueRead`, aggiungi `root_id` subito dopo `file_id`:

```python
class IssueRead(BaseModel):
    id: int
    file_id: int
    root_id: int
    type: str
    field: str | None
    severity: str
    detail: str
    suggested_fix_json: dict | None
    status: str
    file_path: str
    artist: str | None
    title: str | None
```

E dopo `IssueBulkBody` aggiungi:

```python
class IssueFixBody(BaseModel):
    value: str
```

- [ ] **Step 4: Aggiorna il router issues**

In `backend/app/routers/issues.py`, aggiorna l'import degli schemi e aggiungi il set retaggabile:

```python
from app.schemas import IssueBulkBody, IssueFixBody, IssueRead, IssueStatusBody
```

Aggiungi sotto `_VALID`:

```python
# Campi tag effettivi (= planner._EFFECTIVE_FIELDS): gli unici correggibili a mano.
_RETAGGABLE = {"artist", "title", "album", "album_artist", "genre", "year",
               "label", "track_no", "comment"}
```

In `_to_read`, aggiungi `root_id`:

```python
def _to_read(issue: Issue, file: AudioFile) -> IssueRead:
    return IssueRead(
        id=issue.id, file_id=issue.file_id, root_id=file.root_id, type=issue.type,
        field=issue.field, severity=issue.severity, detail=issue.detail,
        suggested_fix_json=issue.suggested_fix_json, status=issue.status,
        file_path=file.path, artist=file.artist, title=file.title,
    )
```

Aggiungi l'endpoint in fondo al file:

```python
@router.post("/{issue_id}/fix", response_model=IssueRead)
def fix_issue(issue_id: int, body: IssueFixBody, db: Session = Depends(get_db)):
    issue = db.get(Issue, issue_id)
    if issue is None:
        raise HTTPException(status_code=404, detail="issue non trovato")
    if issue.field not in _RETAGGABLE:
        raise HTTPException(status_code=400, detail="campo non correggibile a mano")
    value = body.value.strip()
    if not value:
        raise HTTPException(status_code=400, detail="valore vuoto")
    issue.suggested_fix_json = {"field": issue.field, "action": "retag", "to": value}
    issue.status = "accepted"
    issue.updated_at = utcnow()
    db.commit()
    file = db.get(AudioFile, issue.file_id)
    return _to_read(issue, file)
```

(`value` resta una stringa, coerente con la forma degli auto-fix; l'eventuale coercizione numerica per `year`/`track_no` è una preoccupazione dell'apply, 6c — fuori scope qui.)

- [ ] **Step 5: Lancia i test, verifica che passano**

Run: `cd backend && python -m pytest tests/test_issues_api.py -v`
Expected: PASS (tutti, inclusi i preesistenti).

- [ ] **Step 6: Suite intera (no regressioni, pristine)**

Run: `cd backend && python -m pytest -q`
Expected: tutti verdi, zero warning.

- [ ] **Step 7: Commit**

```bash
cd ~/Develop/DjOrganizer01
git add backend/app/schemas.py backend/app/routers/issues.py backend/tests/test_issues_api.py
git commit -m "feat(api): POST /api/issues/{id}/fix (correzione manuale plan-routed) + root_id su IssueRead"
```

---

## Task 2: Frontend — client API issues/duplicates + nav refresh + token `--c-ok`

**Files:**
- Modify: `frontend/lib/api.ts`
- Modify: `frontend/components/index-nav.tsx`
- Modify: `frontend/app/globals.css`

**Interfaces:**
- Produces (da `@/lib/api`): tipi `Issue`, `IssueFilters`, `IssueBulk`, `DupMember`, `DupGroup`; funzioni `listIssues(filters?)`, `setIssueStatus(id, status)`, `fixIssue(id, value)`, `bulkIssues(body)`, `listDuplicates()`, `setKeeper(groupId, fileId)`, `dismissDuplicate(groupId)`. Utility Tailwind `text-ok` / `border-ok` / `border-l-ok` dal token `--c-ok`.
- Consumes: `apiGet`/`apiSend`/`Severity`/`fmtDuration` esistenti in `api.ts`.

- [ ] **Step 1: Generalizza `apiGet` params**

In `frontend/lib/api.ts`, cambia la firma di `apiGet` (riga ~90) da `params?: FileQuery` a un record generico, così accetta sia `FileQuery` sia `IssueFilters`:

```ts
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
```

- [ ] **Step 2: Aggiungi tipi e funzioni issues/duplicates**

In `frontend/lib/api.ts`, prima della sezione `// --- helpers`, aggiungi:

```ts
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
```

- [ ] **Step 3: Aggiungi il token `--c-ok` in globals.css**

In `frontend/app/globals.css`:
- nel blocco `@theme inline`, dopo `--color-warning: var(--c-warning);`, aggiungi:
  ```css
  --color-ok: var(--c-ok);
  ```
- nel blocco `:root` (dark), dopo `--c-warning: #c9a23a;`, aggiungi:
  ```css
  --c-ok: #5a8f6b;
  ```
- nel blocco `html[data-theme="paper"]`, dopo `--c-warning: #8a6d18;`, aggiungi:
  ```css
  --c-ok: #3f6b4f;
  ```

- [ ] **Step 4: Refresh dei conteggi nav al cambio pagina**

In `frontend/components/index-nav.tsx`, cambia l'effetto di mount (riga 37) perché si ri-esegua anche al cambio di `pathname` (così i totali nav riflettono le azioni 6b appena cambi sezione):

```tsx
  // ricarica i conteggi all'avvio, al cambio pagina, e quando uno scan finisce
  useEffect(() => { load(); }, [pathname, load]);
  useEffect(() => {
    if (scan.status === "done") load();
  }, [scan.status, load]);
```

(`pathname` è già disponibile da `usePathname()` a inizio componente.)

- [ ] **Step 5: Verifica lint e build**

Run: `cd frontend && npm run lint && npm run build`
Expected: verdi.

- [ ] **Step 6: Commit**

```bash
cd ~/Develop/DjOrganizer01
git add frontend/lib/api.ts frontend/components/index-nav.tsx frontend/app/globals.css
git commit -m "feat(fe): client API issues/duplicates, refresh conteggi nav al cambio pagina, token --c-ok"
```

---

## Task 3: Frontend — pagina ISSUES

**Files:**
- Create: `frontend/components/issues-table.tsx`
- Modify: `frontend/app/issues/page.tsx`

**Interfaces:**
- Consumes: `Issue`, `listIssues`, `setIssueStatus`, `fixIssue`, `bulkIssues`, `listSources`, `ScanRoot` (Task 2 + 6a); `useJobs`; `PageLayout`; `Select`, `Button`, `EmptyState`, `Alert` (`ui.tsx`); `cn`. Token `text-ok` (Task 2).
- Produces: `IssuesTable` (consumato solo dalla pagina ISSUES).

- [ ] **Step 1: Crea `frontend/components/issues-table.tsx`**

```tsx
"use client";

import { useState } from "react";
import { type Issue } from "@/lib/api";
import { cn } from "@/lib/cn";

// Stessi campi retaggabili del backend (planner._EFFECTIVE_FIELDS).
const RETAGGABLE = new Set([
  "artist", "title", "album", "album_artist", "genre", "year", "label", "track_no", "comment",
]);

function SevMark({ sev }: { sev: string }) {
  if (sev === "error") return <span className="text-danger">▲</span>;
  if (sev === "warning") return <span className="text-warning">●</span>;
  return <span className="text-faint">·</span>;
}

function IssueRow({ issue, onFix, onDismiss, onReopen }: {
  issue: Issue;
  onFix: (id: number, value: string) => Promise<void>;
  onDismiss: (id: number) => Promise<void>;
  onReopen: (id: number) => Promise<void>;
}) {
  const fixable = issue.field != null && RETAGGABLE.has(issue.field);
  const suggested = typeof issue.suggested_fix_json?.to === "string"
    ? (issue.suggested_fix_json.to as string) : "";
  const [value, setValue] = useState(suggested);
  const [busy, setBusy] = useState(false);
  const run = async (fn: () => Promise<void>) => {
    setBusy(true);
    try { await fn(); } finally { setBusy(false); }
  };

  return (
    <tr className={cn("border-b border-surface-2 last:border-0 hover:bg-surface", issue.status !== "open" && "opacity-70")}>
      <td className="px-3 py-2 text-center"><SevMark sev={issue.severity} /></td>
      <td className="whitespace-nowrap px-3 py-2 text-fg">{issue.type}</td>
      <td className="px-3 py-2">
        <div className="text-fg-strong">{issue.artist || "—"}{issue.title ? ` — ${issue.title}` : ""}</div>
        <div className="max-w-[220px] truncate text-[10px] text-faint" title={issue.file_path}>{issue.file_path}</div>
      </td>
      <td className="px-3 py-2 text-muted">{issue.field || "—"}</td>
      <td className="px-3 py-2">
        {issue.status === "open" ? (
          fixable ? (
            <input
              className="w-36 border border-border bg-bg px-2 py-1 text-[11px] text-fg-strong placeholder:text-faint focus:border-border-strong focus:outline-none"
              value={value}
              onChange={(e) => setValue(e.target.value)}
              placeholder={`scrivi ${issue.field}…`}
            />
          ) : (
            <span className="text-faint">— non correggibile</span>
          )
        ) : (
          <span className="text-fg">{issue.status === "accepted" ? (suggested || "—") : "—"}</span>
        )}
      </td>
      <td className="whitespace-nowrap px-3 py-2">
        {issue.status === "open" ? (
          <span className="flex gap-1">
            {fixable && (
              <button
                disabled={busy || !value.trim()}
                onClick={() => run(() => onFix(issue.id, value.trim()))}
                className="border border-border px-2 py-0.5 text-[10px] text-ok hover:bg-elevated disabled:opacity-40"
              >✓ accetta</button>
            )}
            <button
              disabled={busy}
              onClick={() => run(() => onDismiss(issue.id))}
              className="border border-border px-2 py-0.5 text-[10px] text-muted hover:bg-elevated disabled:opacity-40"
            >✕ ignora</button>
          </span>
        ) : (
          <span className="flex items-center gap-2">
            <span className={cn("border px-1.5 py-0.5 text-[9px] uppercase tracking-wider",
              issue.status === "accepted" ? "border-border text-ok" : "border-border text-faint")}>
              {issue.status === "accepted" ? "accettata" : "ignorata"}
            </span>
            <button disabled={busy} onClick={() => run(() => onReopen(issue.id))}
              className="text-faint hover:text-fg disabled:opacity-40" title="riapri">↺</button>
          </span>
        )}
      </td>
    </tr>
  );
}

export function IssuesTable({ issues, onFix, onDismiss, onReopen }: {
  issues: Issue[];
  onFix: (id: number, value: string) => Promise<void>;
  onDismiss: (id: number) => Promise<void>;
  onReopen: (id: number) => Promise<void>;
}) {
  return (
    <div className="overflow-x-auto border border-border">
      <table className="w-full border-collapse text-xs">
        <thead>
          <tr className="border-b border-border text-left text-[9px] uppercase tracking-wider text-faint">
            <th className="px-3 py-2 text-center font-normal">!</th>
            <th className="px-3 py-2 font-normal">Tipo</th>
            <th className="px-3 py-2 font-normal">Traccia</th>
            <th className="px-3 py-2 font-normal">Campo</th>
            <th className="px-3 py-2 font-normal">Correzione</th>
            <th className="px-3 py-2 font-normal">Azioni</th>
          </tr>
        </thead>
        <tbody>
          {issues.map((i) => (
            <IssueRow key={i.id} issue={i} onFix={onFix} onDismiss={onDismiss} onReopen={onReopen} />
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

- [ ] **Step 2: Sostituisci `frontend/app/issues/page.tsx`**

```tsx
"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  listIssues, listSources, setIssueStatus, fixIssue, bulkIssues,
  type Issue, type ScanRoot,
} from "@/lib/api";
import { useJobs } from "@/components/jobs-provider";
import { PageLayout } from "@/components/page-layout";
import { IssuesTable } from "@/components/issues-table";
import { Alert, Button, EmptyState, Select } from "@/components/ui";

export default function IssuesPage() {
  const { scan } = useJobs();
  const [issues, setIssues] = useState<Issue[]>([]);
  const [roots, setRoots] = useState<ScanRoot[]>([]);
  const [offline, setOffline] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const [sev, setSev] = useState("");
  const [type, setType] = useState("");
  const [status, setStatus] = useState("open");
  const [rootId, setRootId] = useState("");

  const load = useCallback(() => {
    listIssues()
      .then((r) => { setIssues(r); setOffline(false); })
      .catch(() => setOffline(true));
  }, []);
  useEffect(() => { load(); }, [load]);
  useEffect(() => { listSources().then(setRoots).catch(() => {}); }, []);
  useEffect(() => { if (scan.status === "done") load(); }, [scan.status, load]);

  const act = async (fn: () => Promise<unknown>) => {
    setActionError(null);
    try { await fn(); load(); }
    catch (e) { setActionError(e instanceof Error ? e.message : "Errore"); }
  };
  const onFix = (id: number, value: string) => act(() => fixIssue(id, value));
  const onDismiss = (id: number) => act(() => setIssueStatus(id, "dismissed"));
  const onReopen = (id: number) => act(() => setIssueStatus(id, "open"));
  const acceptAllFixable = () => act(() => bulkIssues({ status: "accepted" }));
  const dismissAllInfo = () => act(() => bulkIssues({ severity: "info", status: "dismissed" }));

  const types = useMemo(() => [...new Set(issues.map((i) => i.type))].sort(), [issues]);

  const filtered = issues.filter((i) =>
    (!sev || i.severity === sev) &&
    (!type || i.type === type) &&
    (!status || i.status === status) &&
    (!rootId || i.root_id === Number(rootId)),
  );

  const bySev: Record<string, number> = { error: 0, warning: 0, info: 0 };
  const byType: Record<string, number> = {};
  let accepted = 0;
  for (const i of issues) {
    bySev[i.severity] = (bySev[i.severity] ?? 0) + 1;
    byType[i.type] = (byType[i.type] ?? 0) + 1;
    if (i.status === "accepted") accepted++;
  }

  return (
    <PageLayout
      title="Issues"
      meta={`${filtered.length} / ${issues.length}`}
      marginaliaTitle="Riepilogo"
      marginalia={
        <Marginalia
          total={issues.length} bySev={bySev} byType={byType} accepted={accepted}
          onAcceptFixable={acceptAllFixable} onDismissInfo={dismissAllInfo}
        />
      }
    >
      <div className="flex flex-col gap-4">
        {offline && <Alert>Backend non raggiungibile. Avvia il server FastAPI.</Alert>}
        {actionError && <Alert>{actionError}</Alert>}

        <div className="flex flex-wrap gap-2">
          <Select value={sev} onChange={(e) => setSev(e.target.value)} className="w-auto">
            <option value="">severità: tutte</option>
            <option value="error">error</option>
            <option value="warning">warning</option>
            <option value="info">info</option>
          </Select>
          <Select value={type} onChange={(e) => setType(e.target.value)} className="w-auto">
            <option value="">tipo: tutti</option>
            {types.map((t) => <option key={t} value={t}>{t}</option>)}
          </Select>
          <Select value={status} onChange={(e) => setStatus(e.target.value)} className="w-auto">
            <option value="open">aperte</option>
            <option value="accepted">accettate</option>
            <option value="dismissed">ignorate</option>
            <option value="">tutti gli stati</option>
          </Select>
          <Select value={rootId} onChange={(e) => setRootId(e.target.value)} className="w-auto">
            <option value="">tutte le radici</option>
            {roots.map((r) => <option key={r.id} value={r.id}>{r.label || r.path}</option>)}
          </Select>
        </div>

        {filtered.length === 0 && !offline ? (
          <EmptyState title="Nessuna issue">
            {issues.length === 0 ? "La libreria è pulita (o non ancora scansionata)." : "Nessuna issue con questi filtri."}
          </EmptyState>
        ) : (
          <IssuesTable issues={filtered} onFix={onFix} onDismiss={onDismiss} onReopen={onReopen} />
        )}
      </div>
    </PageLayout>
  );
}

function Marginalia({ total, bySev, byType, accepted, onAcceptFixable, onDismissInfo }: {
  total: number;
  bySev: Record<string, number>;
  byType: Record<string, number>;
  accepted: number;
  onAcceptFixable: () => void;
  onDismissInfo: () => void;
}) {
  return (
    <div className="flex flex-col gap-4 text-xs">
      <div>
        <div className="tnum text-2xl leading-none text-fg-strong">{total}</div>
        <div className="mt-1 text-[10px] uppercase tracking-wider text-muted">issue</div>
        <div className="mt-1 flex gap-3 text-[11px]">
          <span className="text-danger">{bySev.error ?? 0} err</span>
          <span className="text-warning">{bySev.warning ?? 0} warn</span>
          <span className="text-muted">{bySev.info ?? 0} info</span>
        </div>
      </div>
      <div>
        <div className="mb-1 text-[10px] uppercase tracking-wider text-muted">per tipo</div>
        <div className="flex flex-col gap-1">
          {Object.entries(byType).sort((a, b) => b[1] - a[1]).map(([t, n]) => (
            <div key={t} className="flex justify-between"><span className="text-muted">{t}</span><span className="tnum text-fg">{n}</span></div>
          ))}
        </div>
      </div>
      <div>
        <div className="text-[10px] uppercase tracking-wider text-muted">accettate</div>
        <div className="mt-1 text-[11px] text-ok">{accepted} → andranno nel PLAN</div>
      </div>
      <div className="flex flex-col gap-2">
        <Button variant="outline" size="sm" onClick={onAcceptFixable}>✓ accetta tutti i fixabili</Button>
        <Button variant="outline" size="sm" onClick={onDismissInfo}>✕ ignora tutti gli info</Button>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Verifica lint e build**

Run: `cd frontend && npm run lint && npm run build`
Expected: verdi.

- [ ] **Step 4: Verifica live** (best-effort, non bloccante)

Con backend + `npm run dev` attivi e una libreria scansionata, apri `/issues`: filtri per severità/tipo/stato/radice; correggi un campo mancante scrivendo nel campo + ✓ accetta (la riga passa a "accettata"); ignora un info; usa i due bottoni blocco dalla marginalia; i conteggi si aggiornano.

- [ ] **Step 5: Commit**

```bash
cd ~/Develop/DjOrganizer01
git add frontend/components/issues-table.tsx frontend/app/issues/page.tsx
git commit -m "feat(fe): pagina ISSUES — triage filtrabile + correzione manuale inline + bulk in marginalia"
```

---

## Task 4: Frontend — pagina DUPLICATES

**Files:**
- Create: `frontend/components/dup-group.tsx`
- Modify: `frontend/app/duplicates/page.tsx`

**Interfaces:**
- Consumes: `DupGroup`, `DupMember`, `listDuplicates`, `setKeeper`, `dismissDuplicate`, `fmtDuration` (Task 2 + 6a); `useJobs`; `PageLayout`; `Alert`, `EmptyState` (`ui.tsx`); `cn`. Token `text-ok`/`border-ok`/`border-l-ok` (Task 2).
- Produces: `DupGroupCard` (consumato solo dalla pagina DUPLICATES). Nota: "ripristina" un gruppo scartato = `setKeeper(group.id, group.keeper_file_id)` (il backend, su keeper, rimette `dismissed=False`).

- [ ] **Step 1: Crea `frontend/components/dup-group.tsx`**

```tsx
"use client";

import { useState } from "react";
import { fmtDuration, type DupGroup } from "@/lib/api";
import { cn } from "@/lib/cn";

export function DupGroupCard({ group, onSetKeeper, onDismiss }: {
  group: DupGroup;
  onSetKeeper: (groupId: number, fileId: number) => Promise<void>;
  onDismiss: (groupId: number) => Promise<void>;
}) {
  const [busy, setBusy] = useState(false);
  const run = async (fn: () => Promise<void>) => {
    setBusy(true);
    try { await fn(); } finally { setBusy(false); }
  };
  const dismissed = group.dismissed;

  return (
    <div className={cn("border border-border", dismissed && "opacity-60")}>
      <div className="flex items-center justify-between border-b border-border bg-surface-2 px-3 py-1.5">
        <span className="text-[10px] tracking-wider text-muted">
          GRUPPO #{group.id} · match: <span className="text-fg-strong">{group.match_kind}</span>
          {dismissed && <span className="text-faint"> · scartato</span>}
        </span>
        {dismissed ? (
          <button
            disabled={busy}
            onClick={() => run(() => onSetKeeper(group.id, group.keeper_file_id))}
            className="border border-border px-2 py-0.5 text-[10px] text-muted hover:bg-elevated disabled:opacity-40"
          >↺ ripristina</button>
        ) : (
          <button
            disabled={busy}
            onClick={() => run(() => onDismiss(group.id))}
            className="border border-border px-2 py-0.5 text-[10px] text-muted hover:bg-elevated disabled:opacity-40"
          >non è un doppione</button>
        )}
      </div>
      <div>
        {group.members.map((m) => {
          const isKeeper = !dismissed && m.file_id === group.keeper_file_id;
          const isRemove = !dismissed && !isKeeper;
          return (
            <div
              key={m.file_id}
              onClick={isRemove && !busy ? () => run(() => onSetKeeper(group.id, m.file_id)) : undefined}
              title={isRemove ? "rendi questo il keeper" : undefined}
              className={cn(
                "grid grid-cols-[64px_1fr_auto] items-center gap-3 border-b border-surface-2 px-3 py-1.5 last:border-0",
                isKeeper && "border-l-2 border-l-ok bg-surface",
                isRemove && "cursor-pointer hover:bg-surface",
              )}
            >
              <span className={cn("border px-1.5 py-0.5 text-center text-[9px] tracking-wider",
                isKeeper ? "border-ok text-ok" : "border-border text-muted")}>
                {isKeeper ? "KEEP" : isRemove ? "REMOVE" : "—"}
              </span>
              <span className={cn("truncate text-[11px]", isKeeper ? "text-fg-strong" : "text-muted")} title={m.path}>{m.path}</span>
              <span className="flex items-center gap-3 text-[10px] text-muted">
                <span className="uppercase">{m.ext}</span>
                <span className="tnum w-10 text-right">{m.bitrate ?? "—"}</span>
                <span className="tnum w-9 text-right">{fmtDuration(m.duration_s)}</span>
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Sostituisci `frontend/app/duplicates/page.tsx`**

```tsx
"use client";

import { useCallback, useEffect, useState } from "react";
import { listDuplicates, setKeeper, dismissDuplicate, type DupGroup } from "@/lib/api";
import { useJobs } from "@/components/jobs-provider";
import { PageLayout } from "@/components/page-layout";
import { DupGroupCard } from "@/components/dup-group";
import { Alert, EmptyState } from "@/components/ui";

export default function DuplicatesPage() {
  const { scan } = useJobs();
  const [groups, setGroups] = useState<DupGroup[]>([]);
  const [offline, setOffline] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const load = useCallback(() => {
    listDuplicates()
      .then((g) => { setGroups(g); setOffline(false); })
      .catch(() => setOffline(true));
  }, []);
  useEffect(() => { load(); }, [load]);
  useEffect(() => { if (scan.status === "done") load(); }, [scan.status, load]);

  const act = async (fn: () => Promise<unknown>) => {
    setActionError(null);
    try { await fn(); load(); }
    catch (e) { setActionError(e instanceof Error ? e.message : "Errore"); }
  };
  const onSetKeeper = (groupId: number, fileId: number) => act(() => setKeeper(groupId, fileId));
  const onDismiss = (groupId: number) => act(() => dismissDuplicate(groupId));

  const active = groups.filter((g) => !g.dismissed);
  const filesToRemove = active.reduce(
    (n, g) => n + g.members.filter((m) => m.action === "remove").length, 0,
  );
  const byMatch: Record<string, number> = {};
  for (const g of active) byMatch[g.match_kind] = (byMatch[g.match_kind] ?? 0) + 1;

  const ordered = [...active, ...groups.filter((g) => g.dismissed)];

  return (
    <PageLayout
      title="Duplicates"
      meta={`${active.length} gruppi`}
      marginaliaTitle="Riepilogo"
      marginalia={<Marginalia groups={active.length} filesToRemove={filesToRemove} byMatch={byMatch} />}
    >
      <div className="flex flex-col gap-4">
        {offline && <Alert>Backend non raggiungibile. Avvia il server FastAPI.</Alert>}
        {actionError && <Alert>{actionError}</Alert>}

        {groups.length === 0 && !offline ? (
          <EmptyState title="Nessun doppione">Nessun gruppo di doppioni (o libreria non ancora scansionata).</EmptyState>
        ) : (
          ordered.map((g) => (
            <DupGroupCard key={g.id} group={g} onSetKeeper={onSetKeeper} onDismiss={onDismiss} />
          ))
        )}
      </div>
    </PageLayout>
  );
}

function Marginalia({ groups, filesToRemove, byMatch }: {
  groups: number;
  filesToRemove: number;
  byMatch: Record<string, number>;
}) {
  return (
    <div className="flex flex-col gap-4 text-xs">
      <div>
        <div className="tnum text-2xl leading-none text-fg-strong">{groups}</div>
        <div className="mt-1 text-[10px] uppercase tracking-wider text-muted">gruppi</div>
      </div>
      <div>
        <div className="tnum text-2xl leading-none text-fg-strong">{filesToRemove}</div>
        <div className="mt-1 text-[10px] uppercase tracking-wider text-muted">file da rimuovere</div>
      </div>
      <div>
        <div className="mb-1 text-[10px] uppercase tracking-wider text-muted">per match</div>
        <div className="flex flex-col gap-1">
          {Object.entries(byMatch).sort((a, b) => b[1] - a[1]).map(([k, n]) => (
            <div key={k} className="flex justify-between"><span className="text-muted">{k}</span><span className="tnum text-fg">{n}</span></div>
          ))}
        </div>
      </div>
      <div className="text-[11px] text-ok">{filesToRemove} rimozioni → andranno nel PLAN</div>
    </div>
  );
}
```

- [ ] **Step 3: Verifica lint e build**

Run: `cd frontend && npm run lint && npm run build`
Expected: verdi.

- [ ] **Step 4: Verifica live** (best-effort, non bloccante)

Con backend + `npm run dev` e libreria scansionata, apri `/duplicates`: vedi i gruppi come card col keeper evidenziato (verde); clic su una riga REMOVE la rende keeper; "non è un doppione" scarta (il gruppo si attenua, in fondo) e "↺ ripristina" lo riporta attivo; la marginalia aggiorna gruppi/file-da-rimuovere/match.

- [ ] **Step 5: Commit**

```bash
cd ~/Develop/DjOrganizer01
git add frontend/components/dup-group.tsx frontend/app/duplicates/page.tsx
git commit -m "feat(fe): pagina DUPLICATES — gruppi come card, scelta keeper, scarta/ripristina, marginalia"
```

---

## Self-Review

**1. Spec coverage:**
- ISSUES lista filtrabile + triage (accetta/ignora/riapri) + correzione inline → Task 3 ✓
- ISSUES bulk nella marginalia → Task 3 (Marginalia) ✓
- DUPLICATES card + keeper + scarta/ripristina + marginalia → Task 4 ✓
- Backend `POST /api/issues/{id}/fix` (forma `{field,action:retag,to}`, validazione 400/404) → Task 1 ✓
- `root_id` su `IssueRead` (filtro radice client) → Task 1 ✓
- Client API issues/duplicates → Task 2 ✓
- Refresh conteggi nav al cambio pagina → Task 2 ✓
- Token verde "ok" per keep/accettato → Task 2 (`--c-ok`) ✓
- Errori/offline/empty (try/catch su ogni azione) → Task 3 e 4 ✓
- Test: pytest per i 2 cambi backend (Task 1); lint+build per il frontend ✓

**2. Placeholder scan:** nessun TBD/TODO; ogni step ha codice completo. Le verifiche "live" sono best-effort non bloccanti (gate = lint+build), come in 6a.

**3. Type consistency:**
- `Issue` (api.ts) ↔ `IssueRead` Pydantic (id, file_id, **root_id**, type, field, severity, detail, suggested_fix_json, status, file_path, artist, title) ✓
- `fixIssue(id, value)` → `POST /api/issues/{id}/fix {value}` ↔ `IssueFixBody` ✓
- `DupGroup`/`DupMember` ↔ `DupGroupRead`/`DupMemberRead` (id, match_kind, keeper_file_id, keeper_overridden, dismissed, members[file_id, action, path, ext, bitrate, duration_s, content_hash]) ✓
- `setKeeper(groupId, fileId)` → body `{file_id}` ↔ `KeeperBody` ✓
- `useJobs()` `{ scan }` consumato come in 6a ✓
- `_RETAGGABLE` (frontend `RETAGGABLE`) == `planner._EFFECTIVE_FIELDS` == backend `_RETAGGABLE` ✓
- token `--c-ok` definito (Task 2) e usato come `text-ok`/`border-ok`/`border-l-ok` (Task 3, 4) ✓

---

## Execution Handoff

Piano completo e salvato in `docs/superpowers/plans/2026-06-28-djorganizer-chunk6b-issues-duplicates.md`.
