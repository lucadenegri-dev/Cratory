# Playlist reorder + colonne Genere/Energia — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Aggiungere colonne Genere/Energia alla lista tracce della playlist e il riordino manuale persistente (sposta una traccia a una posizione, le altre scalano), abilitato solo sulle playlist manuali.

**Architecture:** Nuova colonna `position` su `playlist_tracks` (migrazione auto + backfill idempotente); `add_track_to_playlist` appende; `tracks_for_playlist` ordina per posizione; endpoint `POST /api/playlists/{id}/reorder` (manual-only) sposta+rinumera. Frontend: due colonne in più; `#` modificabile + "in cima" che chiamano il reorder; `insertionRank` passa all'ordine dell'array.

**Tech Stack:** FastAPI + SQLAlchemy (SQLite, migrazioni idempotenti in `db.py`, niente Alembic); Next.js 16 client components, i18n it/en.

## Global Constraints

- Commit: NO `Co-Authored-By`. Branch corrente `feat/playlist-reorder-e-colonne` (verifica `git rev-parse --abbrev-ref HEAD`); stagea solo i file del task.
- Backend test TDD: `cd backend && source .venv/bin/activate && python -m pytest tests/<file> -v`. Fixture con sessione SQLite in-memory come in `backend/tests/test_playlist_from_tracks.py` (TestClient) o `test_playlist_membership.py` (fixture `db`).
- Riordino consentito SOLO su playlist `kind == "manual"`: l'endpoint dà 409 sulle altre, il frontend non mostra i controlli.
- Nessuna modifica ai file audio; solo `playlist_tracks`.
- Frontend: leggi `frontend/CLAUDE.md` prima di editare (Next 16 modificato). Stringhe via `useT()`, chiavi i18n in **entrambi** `it.ts` e `en.ts`. Componenti da `@/components/ui`; token colore validi: `bg-elevated`,`bg-surface`,`bg-bg`,`text-muted`,`text-fg`,`text-faint`,`text-fg-strong`,`text-danger`,`border-border`. Verifica frontend: `npm run lint && npm run build` (no dev server: la verifica live la fa il controller).

---

### Task 1: Backend — colonna `position`, backfill, append, ordinamento

**Files:**
- Modify: `backend/app/models.py` (Table `playlist_tracks`, ~riga 25-32)
- Modify: `backend/app/db.py` (`ensure_schema` + nuova `_migrate_backfill_playlist_positions`)
- Modify: `backend/app/repositories.py` (`add_track_to_playlist`, `tracks_for_playlist`)
- Test: `backend/tests/test_playlist_position.py` (create)

**Interfaces:**
- Produces: colonna `playlist_tracks.position` (int, nullable); `add_track_to_playlist` appende (`position=max+1`); `tracks_for_playlist` ritorna in ordine di `position`.

- [ ] **Step 1: Write failing tests** — `backend/tests/test_playlist_position.py`:

```python
"""Ordine persistente delle tracce in playlist: colonna position + backfill + append."""
import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401
from app.db import Base, ensure_schema, _migrate_backfill_playlist_positions
from app.models import Playlist, Track, playlist_tracks
from app.repositories import add_track_to_playlist, tracks_for_playlist


@pytest.fixture()
def db():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(eng)
    s = sessionmaker(bind=eng, expire_on_commit=False)()
    try:
        yield s
    finally:
        s.close()


def _pl(db, name="P", kind="manual"):
    pl = Playlist(platform="manual", name=name, kind=kind)
    db.add(pl); db.flush()
    return pl


def _tr(db, title):
    t = Track(source_type="local_files", title=title, artist="A")
    db.add(t); db.flush()
    return t


def test_add_appende_position(db):
    pl = _pl(db)
    a, b, c = _tr(db, "a"), _tr(db, "b"), _tr(db, "c")
    add_track_to_playlist(db, a, pl)
    add_track_to_playlist(db, b, pl)
    add_track_to_playlist(db, c, pl)
    db.commit()
    rows = db.execute(
        select(playlist_tracks.c.track_id, playlist_tracks.c.position)
        .where(playlist_tracks.c.playlist_id == pl.id)
        .order_by(playlist_tracks.c.position)
    ).all()
    assert [r.position for r in rows] == [1, 2, 3]
    assert [t.title for t in tracks_for_playlist(db, pl.id)] == ["a", "b", "c"]


def test_backfill_assegna_1_n_su_null(db):
    pl = _pl(db)
    a, b, c = _tr(db, "a"), _tr(db, "b"), _tr(db, "c")
    # inserimento raw SENZA position (simula righe pre-migrazione), added_at crescente
    for i, t in enumerate([a, b, c]):
        db.execute(playlist_tracks.insert().values(
            playlist_id=pl.id, track_id=t.id, added_at=text(f"datetime('2020-01-0{i+1}')"),
        ))
    db.commit()
    conn = db.connection()
    _migrate_backfill_playlist_positions(conn)
    db.commit()
    rows = db.execute(
        select(playlist_tracks.c.track_id, playlist_tracks.c.position)
        .where(playlist_tracks.c.playlist_id == pl.id)
        .order_by(playlist_tracks.c.position)
    ).all()
    assert [r.position for r in rows] == [1, 2, 3]
    assert [r.track_id for r in rows] == [a.id, b.id, c.id]
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_playlist_position.py -v`
Expected: FAIL (`position` non esiste / `_migrate_backfill_playlist_positions` non importabile).

- [ ] **Step 3a: aggiungi la colonna** — in `backend/app/models.py`, nella `Table("playlist_tracks", ...)` aggiungi dopo `Column("added_by", String, nullable=True),`:

```python
    Column("position", Integer, nullable=True),
```

(`Integer` è già importato.)

- [ ] **Step 3b: append in `add_track_to_playlist`** — in `backend/app/repositories.py`, dentro `add_track_to_playlist`, PRIMA dell'`INSERT` (dopo il check `if exists: return`) calcola la posizione e passala nell'insert:

```python
    max_pos = db.scalar(
        select(func.max(playlist_tracks.c.position)).where(
            playlist_tracks.c.playlist_id == playlist.id
        )
    )
    db.execute(playlist_tracks.insert().values(
        playlist_id=playlist.id, track_id=track.id, added_at=added_at, added_by=added_by,
        position=(max_pos or 0) + 1,
    ))
```

(`func` e `select` sono già importati.)

- [ ] **Step 3c: ordina per posizione** — sostituisci l'`order_by` in `tracks_for_playlist`:

```python
        .order_by(
            playlist_tracks.c.position.is_(None), playlist_tracks.c.position,
            playlist_tracks.c.added_at.is_(None), playlist_tracks.c.added_at,
            Track.id,
        )
```

- [ ] **Step 3d: migrazione backfill** — in `backend/app/db.py` aggiungi la funzione (accanto alle altre `_migrate_*`):

```python
def _migrate_backfill_playlist_positions(conn) -> None:
    """Backfill di playlist_tracks.position: per ogni playlist assegna 1..N nell'ordine
    corrente (added_at NULLs-last, poi track_id) alle sole righe con position NULL.

    Idempotente: dopo il backfill le position sono valorizzate, quindi le ri-esecuzioni
    (WHERE position IS NULL) sono no-op.
    """
    if not _table_exists(conn, "playlist_tracks"):
        return
    cols = {r[1] for r in conn.execute(text('PRAGMA table_info("playlist_tracks")')).fetchall()}
    if "position" not in cols:
        return
    conn.execute(text(
        "WITH ordered AS ("
        "  SELECT playlist_id, track_id, ROW_NUMBER() OVER ("
        "    PARTITION BY playlist_id ORDER BY (added_at IS NULL), added_at, track_id"
        "  ) AS rn FROM playlist_tracks"
        ") "
        "UPDATE playlist_tracks SET position = ("
        "  SELECT rn FROM ordered o WHERE o.playlist_id = playlist_tracks.playlist_id "
        "    AND o.track_id = playlist_tracks.track_id"
        ") WHERE position IS NULL"
    ))
```

e chiamala in `ensure_schema`, subito dopo `_migrate_playlist_memberships(conn)`:

```python
        _migrate_playlist_memberships(conn)
        _migrate_backfill_playlist_positions(conn)
```

- [ ] **Step 4: Run to verify pass**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_playlist_position.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Regressione** — `pytest tests/test_playlist_membership.py tests/test_playlist_from_tracks.py tests/test_playlist_add_tracks.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/models.py backend/app/db.py backend/app/repositories.py backend/tests/test_playlist_position.py
git commit -m "feat(playlists): colonna position + backfill + append + ordinamento"
```

---

### Task 2: Backend — endpoint di riordino (manual-only)

**Files:**
- Modify: `backend/app/schemas.py` (`PlaylistReorderRequest`)
- Modify: `backend/app/repositories.py` (`reorder_playlist_track`)
- Modify: `backend/app/routers/playlists.py` (endpoint `reorder_track` + import)
- Test: `backend/tests/test_playlist_reorder.py` (create)

**Interfaces:**
- Consumes: `tracks_for_playlist` (Task 1, ora in ordine di position), `get_playlist`, `track_out`, `TrackOut`.
- Produces: `POST /api/playlists/{playlist_id}/reorder` body `{track_id, position}` → `list[TrackOut]` riordinata. Errori: 404 `playlist_not_found`, 409 `playlist_not_manual`, 404 `track_not_in_playlist`. `reorder_playlist_track(db, playlist_id, track_id, position) -> list[Track] | None`.

- [ ] **Step 1: Write failing tests** — `backend/tests/test_playlist_reorder.py`:

```python
"""POST /api/playlists/{id}/reorder: riordino manuale (solo playlist manuali)."""
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
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    app.dependency_overrides[get_db] = lambda: session
    try:
        yield TestClient(app), session
    finally:
        app.dependency_overrides.pop(get_db, None)
        session.close()


def _pl(db, kind="manual"):
    pl = Playlist(platform="manual", name="P", kind=kind)
    db.add(pl); db.flush()
    return pl


def _members(db, pl, n):
    ids = []
    for i in range(n):
        t = Track(source_type="local_files", title=f"T{i}", artist="A")
        db.add(t); db.flush()
        add_track_to_playlist(db, t, pl)
        ids.append(t.id)
    db.commit()
    return ids


def test_reorder_sposta_e_rinumera(client_db):
    client, db = client_db
    pl = _pl(db)
    ids = _members(db, pl, 5)  # T0..T4 in posizioni 1..5
    # sposta l'ultima (T4) in posizione 1
    r = client.post(f"/api/playlists/{pl.id}/reorder", json={"track_id": ids[4], "position": 1})
    assert r.status_code == 200
    assert [t["title"] for t in r.json()] == ["T4", "T0", "T1", "T2", "T3"]


def test_reorder_clamp_oltre_la_fine(client_db):
    client, db = client_db
    pl = _pl(db)
    ids = _members(db, pl, 3)
    r = client.post(f"/api/playlists/{pl.id}/reorder", json={"track_id": ids[0], "position": 999})
    assert r.status_code == 200
    assert [t["title"] for t in r.json()] == ["T1", "T2", "T0"]


def test_reorder_409_su_non_manuale(client_db):
    client, db = client_db
    pl = _pl(db, kind="playlist")
    ids = _members(db, pl, 2)
    r = client.post(f"/api/playlists/{pl.id}/reorder", json={"track_id": ids[0], "position": 1})
    assert r.status_code == 409


def test_reorder_404_traccia_non_membro(client_db):
    client, db = client_db
    pl = _pl(db)
    _members(db, pl, 2)
    r = client.post(f"/api/playlists/{pl.id}/reorder", json={"track_id": 99999, "position": 1})
    assert r.status_code == 404


def test_reorder_404_playlist_inesistente(client_db):
    client, _ = client_db
    r = client.post("/api/playlists/9999/reorder", json={"track_id": 1, "position": 1})
    assert r.status_code == 404
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_playlist_reorder.py -v`
Expected: FAIL (endpoint inesistente → 404/405).

- [ ] **Step 3a: schema** — in `backend/app/schemas.py`, dopo `PlaylistAddTracksResult`:

```python
class PlaylistReorderRequest(BaseModel):
    track_id: int
    position: int = Field(ge=1)
```

- [ ] **Step 3b: repo** — in `backend/app/repositories.py`:

```python
def reorder_playlist_track(db: Session, playlist_id: int, track_id: int, position: int) -> list[Track] | None:
    """Sposta `track_id` alla posizione 1-based `position` (clampata) e rinumera 1..N.
    Ritorna la lista riordinata, o None se la traccia non e' nella playlist. Non committa."""
    members = tracks_for_playlist(db, playlist_id)
    ids = [t.id for t in members]
    if track_id not in ids:
        return None
    ids.remove(track_id)
    idx = max(0, min(position - 1, len(ids)))
    ids.insert(idx, track_id)
    for new_pos, tid in enumerate(ids, start=1):
        db.execute(playlist_tracks.update().where(
            playlist_tracks.c.playlist_id == playlist_id,
            playlist_tracks.c.track_id == tid,
        ).values(position=new_pos))
    return tracks_for_playlist(db, playlist_id)
```

- [ ] **Step 3c: endpoint** — in `backend/app/routers/playlists.py` aggiungi `reorder_playlist_track` all'import da `app.repositories` e `PlaylistReorderRequest` all'import da `app.schemas`. Poi:

```python
@router.post("/{playlist_id}/reorder", response_model=list[TrackOut])
def reorder_track(playlist_id: int, req: PlaylistReorderRequest, db: Session = Depends(get_db)):
    """Riordino manuale: sposta una traccia a una posizione (solo playlist manuali)."""
    playlist = get_playlist(db, playlist_id)
    if playlist is None:
        raise api_error(404, "playlist_not_found", "Playlist not found")
    if playlist.kind != "manual":
        raise api_error(409, "playlist_not_manual", "Reorder is only allowed on manual playlists")
    result = reorder_playlist_track(db, playlist_id, req.track_id, req.position)
    if result is None:
        raise api_error(404, "track_not_in_playlist", "Track is not in this playlist")
    db.commit()
    return [track_out(t) for t in result]
```

- [ ] **Step 4: Run to verify pass**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_playlist_reorder.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas.py backend/app/repositories.py backend/app/routers/playlists.py backend/tests/test_playlist_reorder.py
git commit -m "feat(playlists): endpoint reorder (manual-only) + repo reorder_playlist_track"
```

---

### Task 3: Frontend — colonne Genere ed Energia

**Files:**
- Modify: `frontend/lib/i18n/it.ts` + `frontend/lib/i18n/en.ts` (`library.colEnergy`)
- Modify: `frontend/app/playlists/[id]/page.tsx` (thead + tbody)

**Interfaces:**
- Consumes: getters `genre`/`energy` già presenti nel sort; `t.library.colGenre` esistente.

- [ ] **Step 1: i18n** — aggiungi `colEnergy` accanto a `colDuration`/`colGenre` in `library` (e nel blocco annidato se presente, es. seconda occorrenza vista in en.ts):
  - it.ts: `colEnergy: "Energia",`
  - en.ts: `colEnergy: "Energy",`

- [ ] **Step 2: thead** — in `frontend/app/playlists/[id]/page.tsx`, nel `<thead>`, aggiungi le due intestazioni: **Genere** dopo `{th("Artist", "artist")}` ed **Energia** dopo `{th("Key", "key")}`:

```tsx
              {th("Artist", "artist")}
              {th(t.library.colGenre, "genre")}
              {th("BPM", "bpm", true)}
              {th("Key", "key")}
              {th(t.library.colEnergy, "energy", true)}
              {th(t.library.colDuration, "duration", true)}
```

- [ ] **Step 3: tbody** — aggiungi le due celle corrispondenti, Genere dopo Artista ed Energia dopo Key:

```tsx
                <td className={`${cell} text-muted`}>{tr.artist ?? "—"}</td>
                <td className={`${cell} max-w-[10rem] truncate text-muted`}>{tr.genre ?? "—"}</td>
                <td className={`${cell} tnum`}>{tr.bpm?.toFixed(0) ?? "—"}</td>
                <td className={`${cell} tnum`}><KeyBadge camelot={tr.camelot_key} /></td>
                <td className={`${cell} tnum text-muted`}>{tr.energy ?? "—"}</td>
                <td className={`${cell} tnum text-muted`}>{fmtDuration(tr.duration_seconds)}</td>
```

- [ ] **Step 4: colspan** — l'empty-state ha `colSpan={8}`; con due colonne in più diventa `colSpan={10}`. Aggiornalo.

- [ ] **Step 5: Lint + build**

Run: `cd frontend && npm run lint && npm run build`
Expected: nessun errore.

- [ ] **Step 6: Commit**

```bash
git add frontend/lib/i18n/it.ts frontend/lib/i18n/en.ts "frontend/app/playlists/[id]/page.tsx"
git commit -m "feat(playlist-detail): colonne Genere ed Energia"
```

---

### Task 4: Frontend — riordino manuale (# modificabile + "in cima")

**Files:**
- Modify: `frontend/lib/api/playlists.ts` (`reorderPlaylistTrack`)
- Modify: `frontend/lib/i18n/it.ts` + `frontend/lib/i18n/en.ts` (`playlists.*`)
- Modify: `frontend/app/playlists/[id]/page.tsx`

**Interfaces:**
- Consumes: endpoint reorder (Task 2). `playlist.kind`, `sort`, `insertionRank`, `setTracks`.
- Produces: `reorderPlaylistTrack(playlistId: number, trackId: number, position: number): Promise<Track[]>`.

- [ ] **Step 1: client fn** — in `frontend/lib/api/playlists.ts`:

```ts
/** Sposta una traccia alla posizione 1-based indicata (solo playlist manuali).
 *  Ritorna la lista tracce riordinata. */
export function reorderPlaylistTrack(playlistId: number, trackId: number, position: number) {
  return apiPost<Track[]>(`/api/playlists/${playlistId}/reorder`, { track_id: trackId, position });
}
```

- [ ] **Step 2: i18n** — aggiungi in `playlists` (it.ts / en.ts):
  - it.ts: `moveToTopTitle: "Sposta in cima",` · `reorderPositionAria: "Nuova posizione",` · `reorderFailed: (msg: string) => \`Riordino fallito: ${msg}\`,`
  - en.ts: `moveToTopTitle: "Move to top",` · `reorderPositionAria: "New position",` · `reorderFailed: (msg: string) => \`Reorder failed: ${msg}\`,`

- [ ] **Step 3: insertionRank all'ordine dell'array** — sostituisci il corpo del `useMemo` `insertionRank` (che oggi ri-ordina per `added_at`) con l'indice dell'array `tracks` (che ora arriva in ordine `position` dal backend):

```tsx
  const insertionRank = useMemo(() => {
    const map = new Map<number, number>();
    tracks.forEach((tr, i) => map.set(tr.id, i + 1));
    return map;
  }, [tracks]);
```

- [ ] **Step 4: stato + handler riordino** — aggiungi vicino agli altri handler:

```tsx
  const canReorder = playlist?.kind === "manual" && sort === "";
  const [editingRank, setEditingRank] = useState<number | null>(null); // track id in edit
  const [reordering, setReordering] = useState(false);

  const applyReorder = async (trackId: number, position: number) => {
    setEditingRank(null);
    setActionError(null);
    setReordering(true);
    try {
      const rows = await reorderPlaylistTrack(pid, trackId, position);
      setTracks(rows);
    } catch (e) {
      setActionError(t.playlists.reorderFailed(errText(e)));
    } finally {
      setReordering(false);
    }
  };
```

Importa `reorderPlaylistTrack` da `@/lib/api` e assicurati che `useState` sia importato (lo è).

- [ ] **Step 5: cella `#` modificabile + "in cima"** — sostituisci la cella `#` (`<td className={`${cell} tnum text-faint`}>{insertionRank.get(tr.id) ?? "—"}</td>`) con:

```tsx
                <td className={`${cell} tnum text-faint`}>
                  {canReorder ? (
                    editingRank === tr.id ? (
                      <input
                        type="number"
                        min={1}
                        max={visible.length}
                        defaultValue={insertionRank.get(tr.id) ?? 1}
                        autoFocus
                        disabled={reordering}
                        aria-label={t.playlists.reorderPositionAria}
                        onBlur={() => setEditingRank(null)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") {
                            const v = Number((e.target as HTMLInputElement).value);
                            if (Number.isFinite(v) && v >= 1) applyReorder(tr.id, v);
                          } else if (e.key === "Escape") setEditingRank(null);
                        }}
                        className="w-12 border border-border bg-bg px-1 py-0.5 text-right text-xs tnum"
                      />
                    ) : (
                      <div className="flex items-center gap-1">
                        <button
                          type="button"
                          onClick={() => setEditingRank(tr.id)}
                          disabled={reordering}
                          className="tnum hover:text-fg"
                          title={t.library.sortColumnHint}
                        >
                          {insertionRank.get(tr.id) ?? "—"}
                        </button>
                        {insertionRank.get(tr.id) !== 1 && (
                          <button
                            type="button"
                            onClick={() => applyReorder(tr.id, 1)}
                            disabled={reordering}
                            title={t.playlists.moveToTopTitle}
                            className="text-faint hover:text-fg"
                          >
                            <ChevronsUp size={13} />
                          </button>
                        )}
                      </div>
                    )
                  ) : (
                    insertionRank.get(tr.id) ?? "—"
                  )}
                </td>
```

Importa `ChevronsUp` da `lucide-react` (aggiungilo all'import esistente delle icone).

- [ ] **Step 6: Lint + build**

Run: `cd frontend && npm run lint && npm run build`
Expected: nessun errore.

- [ ] **Step 7: Commit**

```bash
git add frontend/lib/api/playlists.ts frontend/lib/i18n/it.ts frontend/lib/i18n/en.ts "frontend/app/playlists/[id]/page.tsx"
git commit -m "feat(playlist-detail): riordino manuale (# modificabile + in cima)"
```

---

## Self-Review

**Spec coverage:**
- Colonna position + backfill + append + ordinamento → Task 1. ✅
- Endpoint reorder manual-only (409/404, clamp, renumber) → Task 2. ✅
- Colonne Genere/Energia → Task 3. ✅
- Riordino UI (# modificabile + in cima, solo manual & sort==="") → Task 4. ✅

**Type consistency:** `reorderPlaylistTrack(playlistId, trackId, position): Promise<Track[]>` coerente tra Task 2 (endpoint `list[TrackOut]`) e Task 4. `insertionRank` ora indice-array = ordine `position` dal backend (`tracks_for_playlist`). `canReorder = kind==="manual" && sort===""`. `PlaylistReorderRequest {track_id, position>=1}`.

**Placeholder scan:** nessun TBD; codice concreto in ogni step. La migrazione backfill è idempotente (`WHERE position IS NULL`); l'endpoint clampa la posizione (test dedicato).
