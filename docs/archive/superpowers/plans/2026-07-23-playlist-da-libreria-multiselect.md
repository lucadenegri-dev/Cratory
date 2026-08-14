# Playlist da libreria: multiselect + "Aggiungi a playlist" — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Potenziare la creazione playlist da libreria (modalità `library` di import-manual) con multi-selezione a checkbox, seleziona-tutto e filtri per genere e per playlist di appartenenza; e aggiungere nel dettaglio traccia un menù "Aggiungi a playlist" verso playlist esistenti.

**Architecture:** Un nuovo filtro `in_playlist` su `GET /api/tracks` e un nuovo endpoint `POST /api/playlists/{id}/add-tracks` (idempotente, `added_by="cratory"`) coprono il backend. Il frontend riscrive il blocco `library` di import-manual (checkbox + filtri + seleziona-tutto via `limit=0`) e aggiunge un componente popover `AddToPlaylistMenu` nella sidebar del dettaglio traccia. Nessuna modifica ai file audio: si toccano solo le membership in `playlist_tracks`.

**Tech Stack:** Backend FastAPI + SQLAlchemy + Pydantic (SQLite). Frontend Next.js 16 (App Router, client components), Tailwind/design-system in `frontend/components/ui.tsx`, i18n it/en in `frontend/lib/i18n/{it,en}.ts`.

## Global Constraints

- **Commit message:** NON aggiungere mai `Co-Authored-By: Claude` (preferenza utente). Frequent commits: uno per task.
- **Branch:** lavora sul branch corrente `feat/playlist-da-libreria-multiselect` (già creato). Verifica con `git rev-parse --abbrev-ref HEAD` prima di committare; stagea solo i file di questo lavoro.
- **Backend test:** `cd backend && source .venv/bin/activate && python -m pytest tests/<file> -v`. Ogni test file replica la fixture `client_db` (TestClient + sessione SQLite in-memory, override di `get_db`) come in `backend/tests/test_playlist_from_tracks.py`.
- **Nuove membership:** sempre `added_by="cratory"` (protette dal prune del sync). `added_at` lasciato a `None`, coerente con `create-from-tracks`.
- **Backend endpoint accetta qualsiasi playlist**, ma i selettori frontend elencano solo le playlist `kind === "manual"`.
- **Frontend — prima di editare le pagine:** leggi `frontend/CLAUDE.md` (questo Next.js ha breaking changes) e, se tocchi routing/params, la guida in `node_modules/next/dist/docs/`. Segui i pattern esistenti.
- **Frontend — i18n:** OGNI stringa visibile passa da `useT()`; aggiungi le chiavi in **entrambi** `frontend/lib/i18n/it.ts` e `frontend/lib/i18n/en.ts` (stessa forma, altrimenti il type dell'oggetto `t` diverge e `tsc` fallisce).
- **Frontend — componenti UI:** usa quelli esistenti in `@/components/ui` (`Button`, `Input`, `Select`, `Checkbox`, `Badge`, `Card`, `CardHeader`, `Field`, `Spinner`, `Alert`). `Select` è un wrapper di `<select>` (usa `<option>` figli). Token colore validi: `bg-elevated`, `bg-surface`, `bg-bg`, `text-muted`, `text-fg`, `text-faint`, `text-fg-strong`, `text-danger`, `border-border`.
- **Frontend verify:** `cd frontend && npm run lint && npm run build`. La verifica visiva (dev server + browser) è nei passi dei task frontend.

---

### Task 1: Backend — filtro `in_playlist` su `GET /api/tracks`

**Files:**
- Modify: `backend/app/repositories.py` (funzione `_apply_track_filters`, righe ~33-98)
- Modify: `backend/app/routers/tracks.py` (endpoint `get_tracks`, righe ~31-73)
- Test: `backend/tests/test_tracks_in_playlist_filter.py` (create)

**Interfaces:**
- Produces: query param `in_playlist: int | None` su `GET /api/tracks` → mostra solo le tracce che appartengono alla playlist indicata. `list_tracks(**filters)` inoltra automaticamente il kwarg a `_apply_track_filters`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_tracks_in_playlist_filter.py`:

```python
"""GET /api/tracks?in_playlist=<id>: solo le tracce dentro quella playlist."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app
from app.models import Playlist, Track
from app.repositories import add_track_to_playlist


@pytest.fixture()
def client_db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    app.dependency_overrides[get_db] = lambda: session
    try:
        yield TestClient(app), session
    finally:
        app.dependency_overrides.pop(get_db, None)
        session.close()


def _tr(db, title, genre=None):
    t = Track(source_type="local_files", platform="local_files", title=title,
              artist="A", genre=genre)
    db.add(t); db.flush()
    return t


def test_in_playlist_filtra_solo_membri(client_db):
    client, db = client_db
    pl = Playlist(platform="manual", name="P", kind="manual")
    db.add(pl); db.flush()
    a, b, c = _tr(db, "in1"), _tr(db, "in2"), _tr(db, "out")
    add_track_to_playlist(db, a, pl)
    add_track_to_playlist(db, b, pl)
    db.commit()

    r = client.get("/api/tracks", params={"in_playlist": pl.id})
    assert r.status_code == 200
    titles = sorted(t["title"] for t in r.json()["items"])
    assert titles == ["in1", "in2"]


def test_in_playlist_combina_con_genre(client_db):
    client, db = client_db
    pl = Playlist(platform="manual", name="P", kind="manual")
    db.add(pl); db.flush()
    house = _tr(db, "h", genre="House")
    techno = _tr(db, "t", genre="Techno")
    add_track_to_playlist(db, house, pl)
    add_track_to_playlist(db, techno, pl)
    db.commit()

    r = client.get("/api/tracks", params={"in_playlist": pl.id, "genre": "House"})
    assert r.status_code == 200
    assert [t["title"] for t in r.json()["items"]] == ["h"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_tracks_in_playlist_filter.py -v`
Expected: FAIL (il param `in_playlist` è ignorato → `test_in_playlist_filtra_solo_membri` vede 3 tracce invece di 2).

- [ ] **Step 3a: Add the filter clause in `_apply_track_filters`**

In `backend/app/repositories.py`, aggiungi il parametro alla firma di `_apply_track_filters` (dopo `archived: bool = False,`):

```python
    archived: bool = False,
    in_playlist: int | None = None,
):
```

e la clausola prima della gestione `archived` (cioè prima del blocco `stmt = (stmt.where(Track.archived...`):

```python
    if in_playlist is not None:
        stmt = stmt.where(Track.id.in_(
            select(playlist_tracks.c.track_id).where(
                playlist_tracks.c.playlist_id == in_playlist
            )
        ))
```

Assicurati che `playlist_tracks` sia importato nel modulo. Verifica in cima al file: se non c'è, aggiungi `playlist_tracks` all'import da `app.models` (es. `from app.models import ..., playlist_tracks`). `select` è già importato.

- [ ] **Step 3b: Thread the param through the router**

In `backend/app/routers/tracks.py`, aggiungi il query param nella firma di `get_tracks` (dopo `archived: bool = False,` e prima di `incomplete_metadata`):

```python
    archived: bool = False,
    in_playlist: int | None = None,
    incomplete_metadata: bool | None = None,
```

e passalo alla chiamata `list_tracks(...)` (nel blocco degli argomenti, accanto ad `archived=archived,`):

```python
        archived=archived,
        in_playlist=in_playlist,
        incomplete_metadata=incomplete_metadata,
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_tracks_in_playlist_filter.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Run the existing tracks tests to ensure no regression**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_playlist_membership.py tests/test_playlist_from_tracks.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/repositories.py backend/app/routers/tracks.py backend/tests/test_tracks_in_playlist_filter.py
git commit -m "feat(tracks): filtro in_playlist su GET /api/tracks"
```

---

### Task 2: Backend — endpoint `POST /api/playlists/{id}/add-tracks`

**Files:**
- Modify: `backend/app/schemas.py` (dopo `PlaylistFromTracksRequest`/`PlaylistOut`, righe ~241-259)
- Modify: `backend/app/routers/playlists.py` (nuovo endpoint dopo `create_from_tracks`, ~riga 215; import schemi)
- Test: `backend/tests/test_playlist_add_tracks.py` (create)

**Interfaces:**
- Consumes: `repositories.add_track_to_playlist(db, track, playlist, *, added_by="cratory")`, `get_playlist`, `recount_playlist` (già importati in `playlists.py`).
- Produces: `POST /api/playlists/{playlist_id}/add-tracks` con body `{ track_ids: list[int] }` → `PlaylistAddTracksResult { playlist: PlaylistOut, added: int, skipped: int }`. Errori: 404 `playlist_not_found`, 422 `tracks_not_found` (con `missing`).

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_playlist_add_tracks.py`:

```python
"""POST /api/playlists/{id}/add-tracks: aggiunta idempotente a playlist esistente."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app
from app.models import Playlist, Track, playlist_tracks


@pytest.fixture()
def client_db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    app.dependency_overrides[get_db] = lambda: session
    try:
        yield TestClient(app), session
    finally:
        app.dependency_overrides.pop(get_db, None)
        session.close()


def _pl(db):
    pl = Playlist(platform="manual", name="P", kind="manual")
    db.add(pl); db.flush()
    return pl


def _tracks(db, n):
    ids = []
    for i in range(n):
        t = Track(source_type="local_files", platform="local_files",
                  title=f"T{i}", artist="A")
        db.add(t); db.flush(); ids.append(t.id)
    db.commit()
    return ids


def test_add_tracks_aggiunge_e_marca_cratory(client_db):
    client, db = client_db
    pl = _pl(db); db.commit()
    ids = _tracks(db, 2)

    r = client.post(f"/api/playlists/{pl.id}/add-tracks", json={"track_ids": ids})
    assert r.status_code == 200
    body = r.json()
    assert body["added"] == 2 and body["skipped"] == 0
    assert body["playlist"]["track_count"] == 2

    added_by = db.execute(
        select(playlist_tracks.c.added_by).where(playlist_tracks.c.playlist_id == pl.id)
    ).scalars().all()
    assert added_by == ["cratory", "cratory"]


def test_add_tracks_e_idempotente(client_db):
    client, db = client_db
    pl = _pl(db); db.commit()
    ids = _tracks(db, 2)
    client.post(f"/api/playlists/{pl.id}/add-tracks", json={"track_ids": ids})

    r = client.post(f"/api/playlists/{pl.id}/add-tracks", json={"track_ids": ids})
    assert r.status_code == 200
    assert r.json()["added"] == 0 and r.json()["skipped"] == 2
    assert r.json()["playlist"]["track_count"] == 2


def test_add_tracks_404_playlist_inesistente(client_db):
    client, db = client_db
    ids = _tracks(db, 1)
    assert client.post("/api/playlists/9999/add-tracks",
                       json={"track_ids": ids}).status_code == 404


def test_add_tracks_422_track_inesistente(client_db):
    client, db = client_db
    pl = _pl(db); db.commit()
    r = client.post(f"/api/playlists/{pl.id}/add-tracks", json={"track_ids": [99999]})
    assert r.status_code == 422
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_playlist_add_tracks.py -v`
Expected: FAIL con 404/405 (endpoint inesistente).

- [ ] **Step 3a: Add the schemas**

In `backend/app/schemas.py`, subito dopo `class PlaylistOut(...)` (dopo la riga `imported_at: datetime`):

```python
class PlaylistAddTracksRequest(BaseModel):
    """Aggiunta di tracce di libreria a una playlist esistente."""
    track_ids: list[int] = Field(min_length=1)


class PlaylistAddTracksResult(BaseModel):
    playlist: PlaylistOut
    added: int
    skipped: int
```

- [ ] **Step 3b: Add the endpoint**

In `backend/app/routers/playlists.py`, estendi l'import da `app.schemas` aggiungendo `PlaylistAddTracksRequest` e `PlaylistAddTracksResult` (nel blocco `from app.schemas import (...)`). Poi, subito dopo la funzione `create_from_tracks`:

```python
@router.post("/{playlist_id}/add-tracks", response_model=PlaylistAddTracksResult)
def add_tracks(playlist_id: int, req: PlaylistAddTracksRequest, db: Session = Depends(get_db)):
    """Aggiunge tracce di libreria a una playlist esistente (idempotente).

    Le membership sono marcate `added_by="cratory"`, cosi' il prune del sync non
    le rimuove. Le tracce gia' presenti (o id ripetuti) contano come `skipped`.
    """
    playlist = get_playlist(db, playlist_id)
    if playlist is None:
        raise api_error(404, "playlist_not_found", "Playlist not found")
    tracks = db.scalars(select(Track).where(Track.id.in_(req.track_ids))).all()
    by_id = {t.id: t for t in tracks}
    missing = [i for i in req.track_ids if i not in by_id]
    if missing:
        raise api_error(422, "tracks_not_found", f"Nonexistent tracks: {missing}", missing=missing)
    existing = {t.id for t in playlist.tracks}
    added = 0
    for track_id in req.track_ids:
        if track_id in existing:
            continue
        add_track_to_playlist(db, by_id[track_id], playlist, added_by="cratory")
        existing.add(track_id)
        added += 1
    skipped = len(req.track_ids) - added
    recount_playlist(db, playlist)
    db.commit()
    db.refresh(playlist)
    return PlaylistAddTracksResult(
        playlist=PlaylistOut.model_validate(playlist), added=added, skipped=skipped,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_playlist_add_tracks.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas.py backend/app/routers/playlists.py backend/tests/test_playlist_add_tracks.py
git commit -m "feat(playlists): endpoint add-tracks per aggiungere a playlist esistente"
```

---

### Task 3: Frontend — client API `addTracksToPlaylist` + tipo

**Files:**
- Modify: `frontend/lib/api/types.ts` (aggiungi `PlaylistAddTracksResult`)
- Modify: `frontend/lib/api/playlists.ts` (aggiungi `addTracksToPlaylist`)

**Interfaces:**
- Produces: `addTracksToPlaylist(playlistId: number, trackIds: number[]): Promise<PlaylistAddTracksResult>`; tipo `PlaylistAddTracksResult { playlist: Playlist; added: number; skipped: number }`. Riesportati dal barrel `@/lib/api`.

- [ ] **Step 1: Add the type**

In `frontend/lib/api/types.ts`, dopo `interface Playlist { ... }` (dopo riga ~45):

```ts
export interface PlaylistAddTracksResult {
  playlist: Playlist;
  added: number;
  skipped: number;
}
```

- [ ] **Step 2: Add the client function**

In `frontend/lib/api/playlists.ts`, aggiungi `PlaylistAddTracksResult` all'import `import type { ... } from "./types";`, poi in fondo al file:

```ts
/** Aggiunge tracce a una playlist esistente (idempotente, additivo).
 *  `added` = nuove membership create, `skipped` = tracce gia' presenti. */
export function addTracksToPlaylist(playlistId: number, trackIds: number[]) {
  return apiPost<PlaylistAddTracksResult>(`/api/playlists/${playlistId}/add-tracks`, {
    track_ids: trackIds,
  });
}
```

- [ ] **Step 3: Verify it type-checks**

Run: `cd frontend && npx tsc --noEmit`
Expected: nessun errore relativo a `addTracksToPlaylist`/`PlaylistAddTracksResult`. (Il barrel `@/lib/api` riesporta da `./api/playlists` e `./api/types`: verifica che l'export sia raggiungibile — se `@/lib/api` usa `export * from` sui moduli, non serve altro.)

- [ ] **Step 4: Commit**

```bash
git add frontend/lib/api/types.ts frontend/lib/api/playlists.ts
git commit -m "feat(api): client addTracksToPlaylist"
```

---

### Task 4: Frontend — import-manual: multiselect + filtri (genere/playlist) + crea/aggiungi

**Files:**
- Modify: `frontend/lib/i18n/it.ts` (blocco `playlists.importManual`, ~riga 535)
- Modify: `frontend/lib/i18n/en.ts` (blocco `playlists.importManual`, ~riga 533)
- Modify: `frontend/app/playlists/import-manual/page.tsx` (riscrittura della modalità `library`)

**Interfaces:**
- Consumes: `addTracksToPlaylist` (Task 3), `createPlaylistFromTracks`, `listImportedPlaylists`, `apiGet`, filtro `in_playlist` (Task 1), componenti UI, `useT`.

- [ ] **Step 1: Add i18n keys (it.ts)**

In `frontend/lib/i18n/it.ts`, dentro l'oggetto `importManual: { ... }`, aggiungi queste chiavi (accanto a quelle esistenti; NON rimuovere le esistenti):

```ts
      filterSelectSubtitle: "Filtra, seleziona in blocco e crea o aggiungi a una playlist.",
      genreFilterPlaceholder: "Filtra per genere…",
      playlistFilterAllOption: "Da qualsiasi playlist",
      selectAllMatching: (n: number) => `Seleziona tutte (${n})`,
      clearSelection: "Deseleziona",
      selectedCount: (n: number) => `${n} selezionate`,
      addToExistingLabel: "Aggiungi a playlist esistente",
      addToExistingPlaceholder: "Scegli playlist…",
      addToExistingButton: "Aggiungi",
      addedFeedback: (added: number, skipped: number) =>
        `${added} aggiunte, ${skipped} già presenti.`,
      addFailed: (msg: string) => `Aggiunta fallita: ${msg}`,
```

- [ ] **Step 2: Add i18n keys (en.ts)**

In `frontend/lib/i18n/en.ts`, dentro l'oggetto `importManual: { ... }`, aggiungi le stesse chiavi con i valori inglesi:

```ts
      filterSelectSubtitle: "Filter, bulk-select and create or add to a playlist.",
      genreFilterPlaceholder: "Filter by genre…",
      playlistFilterAllOption: "From any playlist",
      selectAllMatching: (n: number) => `Select all (${n})`,
      clearSelection: "Clear",
      selectedCount: (n: number) => `${n} selected`,
      addToExistingLabel: "Add to existing playlist",
      addToExistingPlaceholder: "Choose playlist…",
      addToExistingButton: "Add",
      addedFeedback: (added: number, skipped: number) =>
        `${added} added, ${skipped} already in.`,
      addFailed: (msg: string) => `Add failed: ${msg}`,
```

- [ ] **Step 3: Rewrite imports and state in `import-manual/page.tsx`**

Sostituisci la riga di import da `@/lib/api` con (aggiunge `addTracksToPlaylist`, `listImportedPlaylists`, `type Playlist`):

```ts
import { apiGet, addTracksToPlaylist, createPlaylistFromTracks, errText, importManualPlaylist, listImportedPlaylists, trackLabel, type Playlist, type Track } from "@/lib/api";
```

Aggiungi `Select` all'import dei componenti UI:

```ts
import { Card, CardHeader, Button, Alert, Spinner, Input, Textarea, Field, Checkbox, Badge, Select } from "@/components/ui";
```

Aggiorna la lista di icone importate da `lucide-react` (rimuovi quelle non più usate `Plus, X, ChevronUp, ChevronDown`, mantieni le altre, aggiungi `ListPlus`):

```ts
import { ArrowLeft, ClipboardList, Library, ListPlus } from "lucide-react";
```

Sostituisci il blocco di stato della modalità libreria (le righe con `query`, `ownedOnly`, `results`, `picked`) con:

```ts
  // Modalità "Dalla libreria": filtri + selezione multipla a checkbox
  const [query, setQuery] = useState("");
  const [ownedOnly, setOwnedOnly] = useState(true);
  const [genre, setGenre] = useState("");
  const [inPlaylist, setInPlaylist] = useState("");   // id playlist come stringa; "" = tutte
  const [results, setResults] = useState<Track[]>([]);
  const [total, setTotal] = useState(0);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [manualPlaylists, setManualPlaylists] = useState<Playlist[]>([]);
  const [addTarget, setAddTarget] = useState("");     // id playlist per "aggiungi a esistente"
  const [feedback, setFeedback] = useState<string | null>(null);
```

- [ ] **Step 4: Replace the data-loading effect and helpers**

Sostituisci l'`useEffect` che carica i risultati con questo (filtri estesi + total) e aggiungi il caricamento delle playlist manuali:

```ts
  useEffect(() => {
    if (mode !== "library") return;
    listImportedPlaylists()
      .then((all) => setManualPlaylists(all.filter((p) => p.kind === "manual")))
      .catch(() => setManualPlaylists([]));
  }, [mode]);

  useEffect(() => {
    if (mode !== "library") return;
    const timer = setTimeout(() => {
      apiGet<{ total: number; items: Track[] }>("/api/tracks", {
        title: query || undefined,
        genre: genre || undefined,
        has_local_file: ownedOnly ? "true" : undefined,
        in_playlist: inPlaylist || undefined,
        limit: 50,
      })
        .then((r) => { setResults(r.items); setTotal(r.total); })
        .catch(() => { setResults([]); setTotal(0); });
    }, 300);
    return () => clearTimeout(timer);
  }, [mode, query, genre, ownedOnly, inPlaylist]);
```

Sostituisci `doCreateFromLibrary` e le helper `pick/unpick/move` con:

```ts
  const doCreateFromLibrary = async () => {
    setError(null);
    setBusy(true);
    try {
      await createPlaylistFromTracks(name.trim() || t.playlists.importManual.defaultPlaylistName, [...selected]);
      router.push("/playlists");
    } catch (e) {
      setError(t.playlists.importManual.createFailed(errText(e)));
      setBusy(false);
    }
  };

  const doAddToExisting = async () => {
    if (!addTarget) return;
    setError(null);
    setFeedback(null);
    setBusy(true);
    try {
      const res = await addTracksToPlaylist(Number(addTarget), [...selected]);
      setFeedback(t.playlists.importManual.addedFeedback(res.added, res.skipped));
      setBusy(false);
    } catch (e) {
      setError(t.playlists.importManual.addFailed(errText(e)));
      setBusy(false);
    }
  };

  const toggle = (id: number) =>
    setSelected((s) => {
      const next = new Set(s);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });

  const selectAllMatching = async () => {
    try {
      const r = await apiGet<{ total: number; items: Track[] }>("/api/tracks", {
        title: query || undefined,
        genre: genre || undefined,
        has_local_file: ownedOnly ? "true" : undefined,
        in_playlist: inPlaylist || undefined,
        limit: 0,
      });
      setSelected(new Set(r.items.map((tr) => tr.id)));
    } catch {
      /* noop: la selezione resta invariata */
    }
  };
```

- [ ] **Step 5: Update the marginalia counter**

Nel `marginalia`, sostituisci `picked.length` con `selected.size` (nella riga che mostra `tracksSelectedLabel`):

```tsx
          <span className="tnum text-fg">{mode === "paste" ? lineCount : selected.size}</span>
```

- [ ] **Step 6: Replace the library-mode JSX**

Sostituisci l'intero blocco JSX della modalità libreria (il ramo `) : (` … `</>` che oggi contiene search+ownedOnly, la lista `results.map`, il blocco `picked.length > 0`, e il bottone `doCreateFromLibrary`) con:

```tsx
            <>
              {feedback && <Alert tone="success">{feedback}</Alert>}

              <div className="grid gap-2 sm:grid-cols-2">
                <Input
                  className="h-9"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder={im.searchByTitlePlaceholder}
                  disabled={busy}
                />
                <Input
                  className="h-9"
                  value={genre}
                  onChange={(e) => setGenre(e.target.value)}
                  placeholder={im.genreFilterPlaceholder}
                  disabled={busy}
                />
                <Select
                  className="h-9"
                  value={inPlaylist}
                  onChange={(e) => setInPlaylist(e.target.value)}
                  disabled={busy}
                >
                  <option value="">{im.playlistFilterAllOption}</option>
                  {manualPlaylists.map((p) => (
                    <option key={p.id} value={String(p.id)}>{p.name}</option>
                  ))}
                </Select>
                <div className="flex items-center">
                  <Checkbox label={im.ownedOnlyLabel} checked={ownedOnly} onChange={setOwnedOnly} />
                </div>
              </div>

              <div className="flex items-center justify-between gap-2 text-xs text-muted">
                <span>{im.selectedCount(selected.size)}</span>
                <div className="flex gap-3">
                  <button type="button" onClick={selectAllMatching} className="hover:text-fg" disabled={total === 0}>
                    {im.selectAllMatching(total)}
                  </button>
                  <button type="button" onClick={() => setSelected(new Set())} className="hover:text-fg" disabled={selected.size === 0}>
                    {im.clearSelection}
                  </button>
                </div>
              </div>

              <div className="max-h-72 divide-y divide-border overflow-y-auto border border-border">
                {results.map((tr) => (
                  <label
                    key={tr.id}
                    className="flex w-full cursor-pointer items-center gap-2 px-3 py-2 text-sm transition-colors hover:bg-elevated"
                  >
                    <input
                      type="checkbox"
                      checked={selected.has(tr.id)}
                      onChange={() => toggle(tr.id)}
                      className="shrink-0"
                    />
                    <span className="min-w-0 flex-1 truncate">{trackLabel(tr)}</span>
                    {tr.has_local_file && <Badge tone="success">FILE</Badge>}
                  </label>
                ))}
                {results.length === 0 && (
                  <div className="px-3 py-6 text-center text-sm text-muted">{im.noResults}</div>
                )}
              </div>

              <div className="flex flex-wrap items-end justify-between gap-3 border-t border-border pt-3">
                <div className="flex items-end gap-2">
                  <Select
                    className="h-9"
                    value={addTarget}
                    onChange={(e) => setAddTarget(e.target.value)}
                    disabled={busy}
                    aria-label={im.addToExistingLabel}
                  >
                    <option value="">{im.addToExistingPlaceholder}</option>
                    {manualPlaylists.map((p) => (
                      <option key={p.id} value={String(p.id)}>{p.name}</option>
                    ))}
                  </Select>
                  <Button variant="outline" onClick={doAddToExisting} disabled={busy || selected.size === 0 || !addTarget}>
                    {busy ? <Spinner /> : <ListPlus size={15} />} {im.addToExistingButton}
                  </Button>
                </div>
                <Button onClick={doCreateFromLibrary} disabled={busy || selected.size === 0}>
                  {busy ? <Spinner /> : <Library size={15} />} {im.createPlaylistButton(selected.size)}
                </Button>
              </div>
            </>
```

Aggiorna anche il `subtitle` della `CardHeader` per la modalità libreria: sostituisci `im.searchSelectOrderSubtitle` con `im.filterSelectSubtitle`.

- [ ] **Step 7: Lint + typecheck + build**

Run: `cd frontend && npm run lint && npm run build`
Expected: nessun errore. (Se `tsc` segnala chiavi i18n mancanti, hai dimenticato di allineare it.ts/en.ts — Step 1/2.)

- [ ] **Step 8: Visual verification (dev server + browser)**

Avvia il preview (dev server dal `.claude/launch.json`, o crealo se assente per il frontend), naviga a `/playlists/import-manual`, clicca "Dalla libreria" e verifica: filtri genere + playlist popolati, checkbox e "Seleziona tutte (N)" funzionanti, contatore aggiornato, "Crea playlist" e "Aggiungi a esistente" con feedback. Controlla `read_console_messages` per errori. Fai uno screenshot come prova.

- [ ] **Step 9: Commit**

```bash
git add frontend/lib/i18n/it.ts frontend/lib/i18n/en.ts frontend/app/playlists/import-manual/page.tsx
git commit -m "feat(import-manual): multiselect + filtri genere/playlist e aggiungi a esistente"
```

---

### Task 5: Frontend — dettaglio traccia: menù "Aggiungi a playlist"

**Files:**
- Create: `frontend/components/add-to-playlist-menu.tsx`
- Modify: `frontend/lib/i18n/it.ts` (blocco `tracks`)
- Modify: `frontend/lib/i18n/en.ts` (blocco `tracks`)
- Modify: `frontend/app/tracks/[id]/page.tsx` (marginalia + refresh)

**Interfaces:**
- Consumes: `addTracksToPlaylist`, `createPlaylistFromTracks`, `listImportedPlaylists`, `errText`, `type Playlist`, `type TrackDetail`, componenti UI, `useT`.
- Produces: componente `<AddToPlaylistMenu track={TrackDetail} onChanged={() => void} />`.

- [ ] **Step 1: Add i18n keys (tracks) in it.ts**

In `frontend/lib/i18n/it.ts`, dentro l'oggetto `tracks: { ... }`, aggiungi:

```ts
      addToPlaylist: "Aggiungi a playlist",
      addToPlaylistNoManual: "Nessuna playlist manuale.",
      createNewPlaylistOption: "Crea nuova playlist",
      newPlaylistNamePlaceholder: "Nome nuova playlist…",
      createAndAddButton: "Crea",
      addToPlaylistFailed: (msg: string) => `Aggiunta fallita: ${msg}`,
```

- [ ] **Step 2: Add i18n keys (tracks) in en.ts**

In `frontend/lib/i18n/en.ts`, dentro l'oggetto `tracks: { ... }`, aggiungi:

```ts
      addToPlaylist: "Add to playlist",
      addToPlaylistNoManual: "No manual playlists.",
      createNewPlaylistOption: "Create new playlist",
      newPlaylistNamePlaceholder: "New playlist name…",
      createAndAddButton: "Create",
      addToPlaylistFailed: (msg: string) => `Add failed: ${msg}`,
```

- [ ] **Step 3: Create the component**

Create `frontend/components/add-to-playlist-menu.tsx`:

```tsx
"use client";

import { useEffect, useRef, useState } from "react";
import { Check, ListPlus, Plus } from "lucide-react";
import { addTracksToPlaylist, createPlaylistFromTracks, errText, listImportedPlaylists, type Playlist, type TrackDetail } from "@/lib/api";
import { Button, Input, Spinner } from "@/components/ui";
import { useT } from "@/lib/i18n";

/** Popover nella sidebar del dettaglio traccia: aggiunge la traccia a una
 *  playlist manuale esistente, o ne crea una nuova con dentro la traccia. */
export function AddToPlaylistMenu({ track, onChanged }: { track: TrackDetail; onChanged: () => void }) {
  const t = useT();
  const [open, setOpen] = useState(false);
  const [playlists, setPlaylists] = useState<Playlist[]>([]);
  const [busy, setBusy] = useState<number | "new" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    listImportedPlaylists()
      .then((all) => setPlaylists(all.filter((p) => p.kind === "manual")))
      .catch(() => setPlaylists([]));
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);

  const inIds = new Set(track.playlists.map((p) => p.id));

  const addTo = async (pl: Playlist) => {
    setBusy(pl.id);
    setError(null);
    try {
      await addTracksToPlaylist(pl.id, [track.id]);
      onChanged();
    } catch (e) {
      setError(t.tracks.addToPlaylistFailed(errText(e)));
    } finally {
      setBusy(null);
    }
  };

  const createAndAdd = async () => {
    if (!newName.trim()) return;
    setBusy("new");
    setError(null);
    try {
      await createPlaylistFromTracks(newName.trim(), [track.id]);
      setNewName("");
      setCreating(false);
      onChanged();
    } catch (e) {
      setError(t.tracks.addToPlaylistFailed(errText(e)));
    } finally {
      setBusy(null);
    }
  };

  return (
    <div ref={ref} className="relative">
      <Button size="sm" variant="outline" onClick={() => setOpen((o) => !o)}>
        <ListPlus size={14} /> {t.tracks.addToPlaylist}
      </Button>
      {open && (
        <div className="absolute left-0 z-20 mt-1 w-64 border border-border bg-elevated p-1 shadow-lg">
          {error && <p className="px-2 py-1 text-xs text-danger">⚠ {error}</p>}
          <div className="max-h-60 overflow-y-auto">
            {playlists.length === 0 && (
              <p className="px-2 py-3 text-center text-xs text-muted">{t.tracks.addToPlaylistNoManual}</p>
            )}
            {playlists.map((pl) => {
              const already = inIds.has(pl.id);
              return (
                <button
                  key={pl.id}
                  type="button"
                  disabled={already || busy !== null}
                  onClick={() => addTo(pl)}
                  className="flex w-full items-center gap-2 px-2 py-1.5 text-left text-sm hover:bg-surface disabled:cursor-default disabled:opacity-60"
                >
                  <span className="min-w-0 flex-1 truncate">{pl.name}</span>
                  {busy === pl.id ? <Spinner /> : already ? <Check size={14} className="text-fg" /> : <Plus size={14} className="text-muted" />}
                </button>
              );
            })}
          </div>
          <div className="mt-1 border-t border-border pt-1">
            {creating ? (
              <div className="flex items-center gap-1 p-1">
                <Input
                  className="h-8 flex-1"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  placeholder={t.tracks.newPlaylistNamePlaceholder}
                  autoFocus
                />
                <Button size="sm" onClick={createAndAdd} disabled={busy !== null || !newName.trim()}>
                  {busy === "new" ? <Spinner /> : t.tracks.createAndAddButton}
                </Button>
              </div>
            ) : (
              <button
                type="button"
                onClick={() => setCreating(true)}
                className="flex w-full items-center gap-2 px-2 py-1.5 text-left text-sm text-muted hover:bg-surface hover:text-fg"
              >
                <Plus size={14} /> {t.tracks.createNewPlaylistOption}
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Wire it into the track detail page**

In `frontend/app/tracks/[id]/page.tsx`:

Aggiungi l'import in cima:

```ts
import { AddToPlaylistMenu } from "@/components/add-to-playlist-menu";
```

Aggiungi una funzione di refresh (subito dopo la definizione degli state / prima del `return`, dentro `TrackPageInner`):

```ts
  const refresh = () => {
    apiGet<TrackDetail>(`/api/tracks/${id}`).then(setTrack).catch(() => {});
  };
```

Nel `marginalia`, aggiungi il pulsante nel `<div className="flex flex-col gap-2">` accanto a "Modifica valori":

```tsx
      <div className="flex flex-col gap-2">
        <Button size="sm" variant="outline" onClick={() => setEditing(true)}><Pencil size={14} /> {t.tracks.editValues}</Button>
        <AddToPlaylistMenu track={track} onChanged={refresh} />
      </div>
```

- [ ] **Step 5: Lint + typecheck + build**

Run: `cd frontend && npm run lint && npm run build`
Expected: nessun errore.

- [ ] **Step 6: Visual verification (dev server + browser)**

Nel preview, apri un dettaglio traccia (`/tracks/<id>`), clicca "Aggiungi a playlist": verifica che il popover elenchi solo le playlist manuali, che le playlist già contenenti la traccia mostrino la spunta e siano disabilitate, che aggiungere aggiorni la riga "Playlist" nella metadata card, e che "Crea nuova playlist" crei e aggiunga. Controlla la console per errori. Screenshot come prova.

- [ ] **Step 7: Commit**

```bash
git add frontend/components/add-to-playlist-menu.tsx frontend/lib/i18n/it.ts frontend/lib/i18n/en.ts frontend/app/tracks/[id]/page.tsx
git commit -m "feat(tracks): menù aggiungi a playlist nel dettaglio traccia"
```

---

## Self-Review

**Spec coverage:**
- Multi-select + seleziona-tutto in create-from-library → Task 4 (checkbox + `selectAllMatching` via `limit=0`). ✅
- Filtro per genere → Task 4 (Input `genre`, filtro esistente `ilike`). ✅
- Filtro per playlist (tracce DENTRO) → Task 1 (`in_playlist`) + Task 4 (Select). ✅
- Bottone "aggiungi a playlist" sulla destra del dettaglio → Task 5 (marginalia). ✅
- Aggiunta a playlist esistente (nuovo endpoint, `added_by="cratory"`, idempotente) → Task 2 + Task 3. ✅
- Extra concordati: "aggiungi a esistente" anche in import-manual (Task 4) e "crea nuova" nel popover (Task 5). ✅
- Rimozione riordino frecce → Task 4 (helper `move`/`pick`/`unpick` e blocco `picked` eliminati). ✅

**Placeholder scan:** nessun TBD/TODO; ogni step ha codice o comando concreto. Nota: la datalist dei generi citata nello spec è resa come Input free-text (coerente col filtro genere della pagina Libreria) per non introdurre un endpoint dedicato — nessuna perdita funzionale.

**Type consistency:**
- `addTracksToPlaylist(playlistId, trackIds)` e `PlaylistAddTracksResult { playlist, added, skipped }` coerenti tra Task 2 (backend), Task 3 (tipo/fn) e i consumi Task 4/5.
- Query param `in_playlist` (numero) inviato come stringa dal Select e passato come `in_playlist: inPlaylist || undefined` (Task 4), letto come `int | None` dal router (Task 1).
- `selected: Set<number>`; le azioni usano `[...selected]` → `number[]`, coerente con le firme.
```
