# Vista griglia libreria + motivo download falliti — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Aggiungere alla Libreria una vista a griglia cover-centrica selezionabile e persistita, e far sì che i download falliti mostrino il motivo reale del fallimento tradotto IT/EN.

**Architecture:** Feature indipendenti. (A) Backend: le funzioni interne del job Soulseek propagano un *codice motivo* stabile fino a `Track.last_download_reason` per l'esito `failed`; il frontend Downloads mappa il codice a testo bilingue. (B) Frontend: nuovo componente `LibraryTrackGrid` (pattern `DiscoveryLeadGrid`) + toggle lista/griglia nella pagina Libreria, con persistenza `localStorage`.

**Tech Stack:** Backend Python + FastAPI + SQLAlchemy + pytest. Frontend Next.js 16 + React 19 + Tailwind. i18n custom in `frontend/lib/i18n/{it,en}.ts`.

## Global Constraints

- Nessuna modifica a modelli/schema/DB: il campo `last_download_reason` (VARCHAR) esiste già.
- Il codice motivo viene salvato in `last_download_reason` **solo** per l'esito `failed`. `not_found` resta `None`, `needs_review` resta prosa invariata.
- Frontend senza test runner: la verifica è `npm run lint` + `npm run build` + controllo nel browser. Non introdurre framework di test.
- Backend test: `cd backend && source .venv/bin/activate && python -m pytest tests/...`.
- Commit senza `Co-Authored-By` (preferenza utente). Committare solo i file del task in corso: nel working tree ci sono modifiche di altre sessioni (`frontend/app/discovery/page.tsx`, `frontend/lib/i18n/*.ts`) — mai `git add -A`.
- **Attenzione al conflitto i18n:** `frontend/lib/i18n/it.ts` e `en.ts` risultano già modificati da un'altra sessione. Prima di editarli fare `git status` e aggiungere solo i propri hunk.

---

### Task 1: Backend — propaga i codici motivo del fallimento

**Files:**
- Modify: `backend/app/services/soulseek_download_job.py`
- Test: `backend/tests/test_soulseek_download_job.py`

**Interfaces:**
- Consumes: `classify_transfer_state` (già importato), `SlskdFile`.
- Produces (nuove firme interne):
  - `_wait_for_download(client, file) -> tuple[str, str | None]` — `("completed", None)` oppure `("failed", <code>)`.
  - `_download_candidate(client, download_dir, file) -> tuple[str | None, str | None]` — `(path, None)` oppure `(None, <code>)`.
  - `_attempt_download(...) -> tuple[str, str | None, str | None]` — invariata come firma, ora popola il code su `failed`.
  - `_process_item(...) -> tuple[str, str | None, str | None]` — su `failed` restituisce il code.
  - Codici possibili: `transfer_failed`, `queue_timeout`, `download_timeout`, `enqueue_rejected`, `file_missing`, `all_candidates_failed`, `error`.

- [ ] **Step 1: Scrivi i test che falliscono**

Aggiungi in coda a `backend/tests/test_soulseek_download_job.py`:

```python
def test_chosen_transfer_failed_sets_reason(patch_job, monkeypatch):
    TestSession, fake = patch_job

    class _Errored(_FakeClient):
        def transfer_state(self, username, filename):
            return {"state": "Completed, Errored"}

    client = _Errored("bob\\Da Funk.flac")
    monkeypatch.setattr(job, "get_slskd_client", lambda: client)
    db = TestSession()
    t = Track(platform="spotify", spotify_id="rf1", source_type="spotify",
              title="Da Funk", artist="Daft Punk")
    db.add(t); db.commit(); track_id = t.id; db.close()

    chosen = client.search("Daft Punk", "Da Funk")[0]
    job._run([(track_id, chosen)], None)

    db = TestSession(); t2 = db.get(Track, track_id)
    assert t2.last_download_outcome == "failed"
    assert t2.last_download_reason == "transfer_failed"
    db.close()


def test_enqueue_exception_sets_reason(patch_job, monkeypatch):
    TestSession, fake = patch_job

    class _NoEnqueue(_FakeClient):
        def enqueue_download(self, file):
            raise RuntimeError("boom")

    client = _NoEnqueue("bob\\Da Funk.flac")
    monkeypatch.setattr(job, "get_slskd_client", lambda: client)
    db = TestSession()
    t = Track(platform="spotify", spotify_id="rf2", source_type="spotify",
              title="Da Funk", artist="Daft Punk")
    db.add(t); db.commit(); track_id = t.id; db.close()

    chosen = client.search("Daft Punk", "Da Funk")[0]
    job._run([(track_id, chosen)], None)

    db = TestSession(); t2 = db.get(Track, track_id)
    assert t2.last_download_outcome == "failed"
    assert t2.last_download_reason == "enqueue_rejected"
    db.close()


def test_queue_timeout_sets_reason(patch_job, monkeypatch):
    TestSession, fake = patch_job
    monkeypatch.setattr(job, "QUEUE_PATIENCE", 0.0)  # pazienza esaurita subito

    class _Queued(_FakeClient):
        def transfer_state(self, username, filename):
            return {"state": "Queued, Remotely"}

    client = _Queued("bob\\Da Funk.flac")
    monkeypatch.setattr(job, "get_slskd_client", lambda: client)
    db = TestSession()
    t = Track(platform="spotify", spotify_id="rf3", source_type="spotify",
              title="Da Funk", artist="Daft Punk")
    db.add(t); db.commit(); track_id = t.id; db.close()

    chosen = client.search("Daft Punk", "Da Funk")[0]
    job._run([(track_id, chosen)], None)

    db = TestSession(); t2 = db.get(Track, track_id)
    assert t2.last_download_reason == "queue_timeout"
    db.close()


def test_cascade_all_failed_sets_reason(patch_job, monkeypatch):
    TestSession, _ = patch_job

    class _AllErrored:
        def __init__(self): self.enqueued = []
        def search(self, artist, title, **kw):
            return [
                SlskdFile(username="u1", filename="u1\\Da Funk.flac", size=10,
                          bitrate=None, length=None, has_free_slot=True, queue_length=0),
                SlskdFile(username="u2", filename="u2\\Da Funk.flac", size=10,
                          bitrate=None, length=None, has_free_slot=True, queue_length=0),
            ]
        def enqueue_download(self, file): self.enqueued.append(file.username)
        def transfer_state(self, username, filename):
            return {"state": "Completed, Errored"}

    client = _AllErrored()
    monkeypatch.setattr(job, "get_slskd_client", lambda: client)
    db = TestSession()
    t = Track(platform="spotify", spotify_id="rf4", source_type="spotify",
              title="Da Funk", artist="Daft Punk")
    db.add(t); db.commit(); track_id = t.id; db.close()

    job._run([(track_id, None)], None)  # None -> cascata via search

    db = TestSession(); t2 = db.get(Track, track_id)
    assert t2.last_download_outcome == "failed"
    assert t2.last_download_reason == "all_candidates_failed"
    db.close()
```

- [ ] **Step 2: Esegui i test per vederli fallire**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_soulseek_download_job.py -v -k "reason"`
Expected: FAIL (i test toccano `last_download_reason` che oggi è sempre `None` per `failed`; `test_queue_timeout`/`transfer_failed`/`cascade` falliranno sull'assert del code, `enqueue` idem).

- [ ] **Step 3: Modifica `_wait_for_download`**

Sostituisci l'intera funzione (attualmente `-> str`) con:

```python
def _wait_for_download(client, file: SlskdFile) -> tuple[str, str | None]:
    """Attende l'esito di un transfer. Ritorna (esito, motivo).

    Se il transfer sta scaricando ("InProgress") si concede fino a DOWNLOAD_TIMEOUT;
    se invece resta solo in coda (Queued/Requested) oltre QUEUE_PATIENCE ci si arrende,
    cosi' il chiamante puo' provare un altro utente col fallback.
    """
    waited = 0.0
    queued = 0.0
    while waited < DOWNLOAD_TIMEOUT:
        state = (client.transfer_state(file.username, file.filename) or {}).get("state", "")
        cls = classify_transfer_state(state)
        if cls == "completed":
            return "completed", None
        if cls == "failed":
            return "failed", "transfer_failed"
        if "inprogress" in state.lower():
            queued = 0.0
        else:
            queued += POLL_INTERVAL
            if queued >= QUEUE_PATIENCE:
                return "failed", "queue_timeout"
        time.sleep(POLL_INTERVAL)
        waited += POLL_INTERVAL
    return "failed", "download_timeout"
```

- [ ] **Step 4: Modifica `_download_candidate`**

Sostituisci l'intera funzione con:

```python
def _download_candidate(client, download_dir, file: SlskdFile) -> tuple[str | None, str | None]:
    """Accoda un candidato, attende l'esito e risolve il path locale.

    Ritorna (path, motivo): (path, None) se ok, (None, <code>) se fallisce.
    """
    try:
        client.enqueue_download(file)
    except Exception:  # noqa: BLE001 — un candidato che non parte non ferma il fallback
        logger.exception("enqueue fallito user=%s", file.username)
        return None, "enqueue_rejected"
    outcome, reason = _wait_for_download(client, file)
    if outcome != "completed":
        return None, reason
    path = _resolve_local_path(download_dir, file.filename)
    if not path:
        return None, "file_missing"
    return path, None
```

- [ ] **Step 5: Aggiorna i due chiamanti di `_download_candidate`**

In `_attempt_download`, la prima riga passa da `path = _download_candidate(...)` a:

```python
    path, reason = _download_candidate(client, download_dir, file)
    if not path:
        return "failed", reason, None
```

In `_process_manual`, la riga passa da `path = _download_candidate(...)` a:

```python
    path, _ = _download_candidate(client, download_dir, file)
    return "downloaded" if path else "failed"
```

- [ ] **Step 6: Aggiorna la cascata in `_process_item`**

Sostituisci il blocco finale della cascata (da `tried: set[str] = set()` fino a `return "failed", None, None`) con:

```python
    tried: set[str] = set()
    last_reason: str | None = None
    for cand in ranked:
        if len(tried) >= MAX_ATTEMPTS:
            break
        if cand.file.username in tried:
            continue
        tried.add(cand.file.username)
        outcome, reason, path = _attempt_download(db, client, download_dir, track,
                                                  cand.file, expected)
        if outcome != "failed":
            return outcome, reason, path
        last_reason = reason
    return "failed", last_reason or "all_candidates_failed", None
```

- [ ] **Step 7: Imposta il motivo nel fallback d'eccezione di `_run`**

Nel ramo `else` (track non None), il blocco `except Exception` che oggi fa solo `outcome = "failed"` diventa:

```python
                    except Exception:  # noqa: BLE001 — un fallimento non ferma il job
                        logger.exception("Download Soulseek fallito per track_id=%s", track_id)
                        outcome = "failed"
                        reason = "error"
```

- [ ] **Step 8: Esegui i test — devono passare**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_soulseek_download_job.py -v`
Expected: PASS (nuovi test + i tre esistenti `downloads`/`auto_pick`/`fallback` restano verdi).

- [ ] **Step 9: Commit**

```bash
cd /Users/lucadenegri/Develop/DJProject01
git add backend/app/services/soulseek_download_job.py backend/tests/test_soulseek_download_job.py
git commit -m "feat(downloads): motivo reale del fallimento propagato come codice"
```

---

### Task 2: Frontend — mostra il motivo del fallimento (Downloads + i18n)

**Files:**
- Modify: `frontend/lib/i18n/it.ts` (sezione `downloads`)
- Modify: `frontend/lib/i18n/en.ts` (sezione `downloads`)
- Modify: `frontend/app/downloads/page.tsx`

**Interfaces:**
- Consumes: `Track.last_download_reason: string | null`, `Track.last_download_outcome`.
- Produces: `t.downloads.failedReason(code: string | null): string`.

- [ ] **Step 1: Aggiungi `failedReason` all'i18n italiano**

In `frontend/lib/i18n/it.ts`, dentro l'oggetto `downloads: { … }` (dopo `outcomeFailed`), aggiungi:

```ts
    failedReason: (code: string | null): string => {
      switch (code) {
        case "transfer_failed": return "Trasferimento interrotto dall'utente remoto.";
        case "queue_timeout": return "Rimasto troppo a lungo in coda (utente lento o offline).";
        case "download_timeout": return "Trasferimento troppo lento: superato il tempo massimo.";
        case "enqueue_rejected": return "Richiesta di download rifiutata dall'utente remoto.";
        case "file_missing": return "Download completato ma file non trovato su disco.";
        case "all_candidates_failed": return "Nessun candidato ha completato il download.";
        case "error": return "Errore imprevisto durante il download.";
        default: return "Download non riuscito.";
      }
    },
```

- [ ] **Step 2: Aggiungi `failedReason` all'i18n inglese**

In `frontend/lib/i18n/en.ts`, dentro l'oggetto `downloads: { … }` (stessa posizione), aggiungi:

```ts
    failedReason: (code: string | null): string => {
      switch (code) {
        case "transfer_failed": return "Transfer interrupted by the remote peer.";
        case "queue_timeout": return "Stuck in the queue too long (peer slow or offline).";
        case "download_timeout": return "Transfer too slow: exceeded the time limit.";
        case "enqueue_rejected": return "Download request rejected by the remote peer.";
        case "file_missing": return "Download completed but the file wasn't found on disk.";
        case "all_candidates_failed": return "No candidate completed the download.";
        case "error": return "Unexpected error during the download.";
        default: return "Download failed.";
      }
    },
```

- [ ] **Step 3: Usa il motivo nella riga del work-list**

In `frontend/app/downloads/page.tsx`, dentro `rows.map((tr) => { … })`, dopo la riga `const hasFile = …;` aggiungi:

```tsx
                  const detail = outcome === "failed"
                    ? t.downloads.failedReason(tr.last_download_reason)
                    : tr.last_download_reason;
```

Poi sostituisci la riga che mostra il motivo:

```tsx
                        {tr.last_download_reason && <div className="text-xs text-muted">{tr.last_download_reason}</div>}
```

con:

```tsx
                        {detail && <div className="text-xs text-muted">{detail}</div>}
```

- [ ] **Step 4: Lint + build**

Run: `cd frontend && npm run lint && npm run build`
Expected: nessun errore. (Se `en.ts`/`it.ts` sono di tipo generato, verificare che entrambe le lingue abbiano `failedReason` — un mismatch di chiavi tra `Dictionary` IT/EN darebbe errore TS in build.)

- [ ] **Step 5: Verifica nel browser**

Avvia il dev server (`preview_start` con la config del frontend), apri `/downloads`. Con un work-list che contiene una traccia `failed`, la riga deve mostrare il testo del motivo sotto il titolo. Cambia lingua da Impostazioni e verifica che il motivo si traduca.

- [ ] **Step 6: Commit**

```bash
cd /Users/lucadenegri/Develop/DJProject01
git status   # verifica di aggiungere solo i propri hunk in it.ts/en.ts
git add frontend/app/downloads/page.tsx frontend/lib/i18n/it.ts frontend/lib/i18n/en.ts
git commit -m "feat(downloads): mostra il motivo tradotto dei download falliti"
```

---

### Task 3: Frontend — componente `LibraryTrackGrid`

**Files:**
- Create: `frontend/components/library-track-grid.tsx`

**Interfaces:**
- Consumes: `Track` da `@/lib/api`, `TrackCover`, `useT` (usa `t.library.untitledTrack`, `t.library.editValuesTitle` già esistenti).
- Produces: `LibraryTrackGrid({ tracks, onEdit }: { tracks: Track[]; onEdit: (t: Track) => void })`.

- [ ] **Step 1: Crea il componente**

Crea `frontend/components/library-track-grid.tsx`:

```tsx
"use client";

import Link from "next/link";
import { Pencil } from "lucide-react";
import { type Track } from "@/lib/api";
import { TrackCover } from "@/components/track-cover";
import { useT } from "@/lib/i18n";

/** Vista a griglia della libreria: card cover-centriche sul modello dei
 *  risultati Discovery (DiscoveryLeadGrid). Presentazione pura: riceve tracce
 *  gia' filtrate/paginate, non fa fetch. */
export function LibraryTrackGrid({
  tracks,
  onEdit,
}: {
  tracks: Track[];
  onEdit: (t: Track) => void;
}) {
  return (
    <div className="grid grid-cols-[repeat(auto-fill,minmax(120px,1fr))] gap-3">
      {tracks.map((tr) => (
        <LibraryTrackCard key={tr.id} track={tr} onEdit={onEdit} />
      ))}
    </div>
  );
}

function LibraryTrackCard({ track, onEdit }: { track: Track; onEdit: (t: Track) => void }) {
  const t = useT();
  // Badge BPM·Key: solo i valori presenti, uniti con " · " (es. "128 · 7A").
  const meta = [track.bpm != null ? track.bpm.toFixed(0) : null, track.camelot_key ?? null]
    .filter(Boolean)
    .join(" · ");
  return (
    <div className="group relative flex flex-col gap-1.5 text-left">
      <Link
        href={`/tracks/${track.id}`}
        className="relative block aspect-square w-full overflow-hidden border border-border bg-elevated outline-none focus-visible:ring-1 focus-visible:ring-fg"
      >
        <TrackCover track={track} className="h-full w-full" iconSize={22} />
        {meta && (
          <span className="tnum absolute bottom-1 left-1 border border-border-strong bg-bg px-1 text-[9px] uppercase tracking-wide text-muted">
            {meta}
          </span>
        )}
      </Link>
      {/* Pencil fuori dal Link (niente <button> dentro <a>): overlay su hover. */}
      <button
        type="button"
        onClick={() => onEdit(track)}
        title={t.library.editValuesTitle}
        className="absolute right-1 top-1 border border-border-strong bg-bg p-1 text-faint opacity-0 transition-opacity hover:text-fg-strong focus-visible:opacity-100 group-hover:opacity-100"
      >
        <Pencil size={12} />
      </button>
      <div className="min-w-0">
        <div className="truncate text-xs font-medium text-fg">
          {track.title ?? <span className="italic text-faint">{t.library.untitledTrack}</span>}
        </div>
        <div className="truncate text-[11px] text-faint">{track.artist ?? "—"}</div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Lint + build (verifica isolata)**

Run: `cd frontend && npm run lint && npm run build`
Expected: nessun errore. Il componente non è ancora usato: la build conferma solo che tipizza e compila. Il rendering effettivo si verifica nel Task 4.

- [ ] **Step 3: Commit**

```bash
cd /Users/lucadenegri/Develop/DJProject01
git add frontend/components/library-track-grid.tsx
git commit -m "feat(library): componente LibraryTrackGrid (vista card)"
```

---

### Task 4: Frontend — toggle lista/griglia + persistenza nella Libreria

**Files:**
- Modify: `frontend/lib/i18n/it.ts` (sezione `library`)
- Modify: `frontend/lib/i18n/en.ts` (sezione `library`)
- Modify: `frontend/app/library/page.tsx`

**Interfaces:**
- Consumes: `LibraryTrackGrid` (Task 3), `t.library.viewListLabel`, `t.library.viewGridLabel`.
- Produces: nessuna interfaccia riusata a valle.

- [ ] **Step 1: Aggiungi le label del toggle all'i18n**

In `frontend/lib/i18n/it.ts`, dentro `library: { … }` (dopo `editValuesTitle`):

```ts
    viewListLabel: "Lista",
    viewGridLabel: "Griglia",
```

In `frontend/lib/i18n/en.ts`, dentro `library: { … }` (stessa posizione):

```ts
    viewListLabel: "List",
    viewGridLabel: "Grid",
```

- [ ] **Step 2: Importa le icone e il componente**

In `frontend/app/library/page.tsx`, aggiungi `List, LayoutGrid` all'import esistente da `lucide-react`:

```tsx
import { ChevronLeft, ChevronRight, ChevronUp, ChevronDown, Pencil, List, LayoutGrid } from "lucide-react";
```

e aggiungi l'import del componente vicino agli altri import di componenti:

```tsx
import { LibraryTrackGrid } from "@/components/library-track-grid";
```

- [ ] **Step 3: Aggiungi lo state `view` e la persistenza**

Dentro `LibraryInner`, vicino agli altri `useState` (es. dopo `const [editing, setEditing] = useState<Track | null>(null);`):

```tsx
  const [view, setView] = useState<"list" | "grid">("list");
  // Persistenza: letta solo lato client (mai in render/SSR) per non rompere l'hydration.
  useEffect(() => {
    const saved = localStorage.getItem("cratory:library:view");
    if (saved === "grid" || saved === "list") setView(saved);
  }, []);
  useEffect(() => {
    localStorage.setItem("cratory:library:view", view);
  }, [view]);
```

- [ ] **Step 4: Rimuovi le righe loading/empty da dentro la tabella**

Nel `<tbody>`, elimina questi due blocchi (verranno gestiti fuori, condivisi tra le viste):

```tsx
            {items === null && (
              <tr><td colSpan={10} className="px-3"><Loading /></td></tr>
            )}
            {items?.length === 0 && (
              <tr><td colSpan={10} className="px-3 py-10 text-center text-sm text-muted">{t.library.emptyStatePrefix} <Link href="/playlists" className="text-fg underline-offset-4 hover:underline">{t.dashboard.importPlaylist}</Link> {t.library.emptyStateSuffix}</td></tr>
            )}
```

- [ ] **Step 5: Sostituisci il contenitore risultati con toolbar + render condizionale**

Sostituisci il blocco:

```tsx
      <div className="border border-border">
        <table className="w-full text-sm">
          {/* …thead + tbody… */}
        </table>
      </div>
```

con (mantieni **identici** `thead` e `tbody`, ora senza le righe loading/empty rimosse allo Step 4):

```tsx
      <div className="mb-3 flex items-center justify-end">
        <div className="inline-flex rounded-none border border-border bg-surface p-0.5">
          <button
            type="button"
            onClick={() => setView("list")}
            aria-pressed={view === "list"}
            title={t.library.viewListLabel}
            className={`rounded-none px-2.5 py-1 transition-colors ${view === "list" ? "bg-elevated text-fg" : "text-muted hover:text-fg"}`}
          >
            <List size={15} />
          </button>
          <button
            type="button"
            onClick={() => setView("grid")}
            aria-pressed={view === "grid"}
            title={t.library.viewGridLabel}
            className={`rounded-none px-2.5 py-1 transition-colors ${view === "grid" ? "bg-elevated text-fg" : "text-muted hover:text-fg"}`}
          >
            <LayoutGrid size={15} />
          </button>
        </div>
      </div>

      {items === null && <Loading />}
      {items?.length === 0 && (
        <div className="py-10 text-center text-sm text-muted">
          {t.library.emptyStatePrefix}{" "}
          <Link href="/playlists" className="text-fg underline-offset-4 hover:underline">{t.dashboard.importPlaylist}</Link>{" "}
          {t.library.emptyStateSuffix}
        </div>
      )}

      {items && items.length > 0 && (
        view === "list" ? (
          <div className="border border-border">
            <table className="w-full text-sm">
              {/* …thead e tbody invariati (senza le righe loading/empty)… */}
            </table>
          </div>
        ) : (
          <LibraryTrackGrid tracks={items} onEdit={setEditing} />
        )
      )}
```

Nota: `{" "}` espliciti nell'empty state perché Next 16 rimuove lo spazio JSX quando il testo va a capo nel sorgente.

- [ ] **Step 6: Lint + build**

Run: `cd frontend && npm run lint && npm run build`
Expected: nessun errore.

- [ ] **Step 7: Verifica nel browser**

Avvia il dev server, apri `/library`.
- Il toggle in alto a destra alterna tabella ↔ griglia di card.
- Le card mostrano cover, titolo, artista e badge `BPM · Key` quando presenti; il pencil appare su hover e apre il `TrackEditModal`; il click sulla cover porta a `/tracks/{id}`.
- I filtri (marginalia) e la paginazione funzionano in entrambe le viste.
- Ricarica la pagina: la vista scelta è ricordata. In modalità griglia, verifica anche `localStorage.getItem("cratory:library:view") === "grid"` via console.

- [ ] **Step 8: Commit**

```bash
cd /Users/lucadenegri/Develop/DJProject01
git status   # solo i propri hunk in it.ts/en.ts
git add frontend/app/library/page.tsx frontend/lib/i18n/it.ts frontend/lib/i18n/en.ts
git commit -m "feat(library): toggle vista lista/griglia con persistenza"
```

---

## Note per l'esecuzione

- **Task indipendenti:** 1→2 (Downloads) e 3→4 (Libreria) sono due catene separate; possono procedere in qualsiasi ordine. Il Task 4 dipende dal Task 3.
- **Conflitto i18n:** `it.ts`/`en.ts` sono toccati sia dal Task 2 che dal Task 4, ed erano già modificati da un'altra sessione all'inizio. Se si eseguono in parallelo, fare attenzione a stage/commit dei soli hunk propri.
