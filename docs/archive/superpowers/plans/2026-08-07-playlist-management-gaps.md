# Playlist Management Gaps Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Chiudere le 6 mancanze della gestione playlist: rename (con lock sul sync), riordino esteso + drag-and-drop, azioni bulk nel dettaglio, duplica-come-manuale, storico diff dei sync, export multi-formato; più l'esposizione di `playlist_position` nei payload.

**Architecture:** Backend FastAPI: nuovi endpoint nel router `playlists`, logica in `repositories.py`/`services/playlist_import.py`, colonna `name_locked` su `Playlist` e nuova tabella `playlist_sync_events` (entrambe auto-migrate da `ensure_schema`: create_all + ADD COLUMN). Frontend Next.js: tutte le feature vivono nella pagina dettaglio playlist + API client + i18n it/en.

**Tech Stack:** Python/FastAPI/SQLAlchemy/Pydantic, pytest (TestClient + sqlite in-memory), Next.js 16/React/Tailwind.

## Global Constraints

- Nessun Alembic: le migrazioni sono `ensure_schema` (create_all + ADD COLUMn automatico per colonne nuove). Non scrivere migrazioni a mano per colonne/tabelle nuove.
- Commit message in stile repo (`feat:`/`fix:`/`docs:`, descrizione in italiano), **senza** Co-Authored-By.
- Test backend: `cd <worktree>/backend && /Users/lucadenegri/Develop/DJProject01/backend/.venv/bin/python -m pytest tests/<file> -q` (venv del checkout principale, cwd nel worktree).
- Frontend: dopo ogni task frontend `cd frontend && npm run lint`. i18n: ogni chiave nuova va sia in `lib/i18n/it.ts` sia in `lib/i18n/en.ts` (stessa struttura).
- Next.js 16 ha breaking changes: non usare pattern deprecati; la pagina dettaglio usa già `use(params)` — seguire il codice esistente.
- Il confirm di rimozione traccia esistente (`removeTrackConfirm`) già avverte dei lead orfani: il confirm della rimozione bulk deve fare lo stesso.

---

### Task 1: Rename playlist — backend

**Files:**
- Modify: `backend/app/models.py` (classe `Playlist`, ~riga 144)
- Modify: `backend/app/schemas.py` (~riga 250 `PlaylistOut`, + nuova `PlaylistUpdateIn`)
- Modify: `backend/app/routers/playlists.py` (nuovo endpoint PATCH)
- Modify: `backend/app/services/playlist_import.py` (~riga 387: rispetta il lock)
- Test: `backend/tests/test_playlist_rename.py` (nuovo)

**Interfaces:**
- Produces: `PATCH /api/playlists/{id}` body `{"name": str}` → `PlaylistOut` (con nuovo campo `name_locked: bool`). Errori: 404 `playlist_not_found`, 422 `playlist_name_empty`.
- Produces: `Playlist.name_locked` (bool, default False): quando True, `import_playlist` NON sovrascrive `playlist.name` dalla sorgente.

- [ ] **Step 1: Scrivi i test che falliscono**

```python
"""PATCH /api/playlists/{id}: rename con lock del nome sul sync."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app
from app.models import Playlist
from app.services.playlist_import import import_playlist


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


def test_rename_cambia_nome_e_locka(client_db):
    client, db = client_db
    pl = Playlist(platform="spotify", platform_playlist_id="sp1", name="Vecchio", kind="playlist")
    db.add(pl); db.commit()
    r = client.patch(f"/api/playlists/{pl.id}", json={"name": "  Nuovo  "})
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "Nuovo"
    assert body["name_locked"] is True


def test_rename_nome_vuoto_422(client_db):
    client, db = client_db
    pl = Playlist(platform="manual", name="P", kind="manual")
    db.add(pl); db.commit()
    assert client.patch(f"/api/playlists/{pl.id}", json={"name": "   "}).status_code == 422


def test_rename_playlist_inesistente_404(client_db):
    client, _ = client_db
    assert client.patch("/api/playlists/9999", json={"name": "X"}).status_code == 404


def test_sync_non_sovrascrive_nome_lockato(client_db):
    _, db = client_db
    pl = Playlist(platform="spotify", platform_playlist_id="sp1", name="Mio nome", kind="playlist", name_locked=True)
    db.add(pl); db.commit()
    import_playlist(db, platform="spotify", name="Nome piattaforma", items=[], platform_playlist_id="sp1")
    db.refresh(pl)
    assert pl.name == "Mio nome"


def test_sync_sovrascrive_nome_non_lockato(client_db):
    _, db = client_db
    pl = Playlist(platform="spotify", platform_playlist_id="sp1", name="Vecchio", kind="playlist")
    db.add(pl); db.commit()
    import_playlist(db, platform="spotify", name="Nome piattaforma", items=[], platform_playlist_id="sp1")
    db.refresh(pl)
    assert pl.name == "Nome piattaforma"
```

- [ ] **Step 2: Verifica che falliscano**

Run: `pytest tests/test_playlist_rename.py -q` → FAIL (`name_locked` inesistente / 405 sul PATCH).

- [ ] **Step 3: Implementa**

In `models.py`, dentro `Playlist` dopo `kind`:

```python
    # Nome bloccato dall'utente (rename): il sync non lo sovrascrive più dalla sorgente.
    name_locked: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
```

In `schemas.py`: aggiungi a `PlaylistOut` il campo `name_locked: bool = False`; sotto `PlaylistFromTracksRequest` aggiungi:

```python
class PlaylistUpdateIn(BaseModel):
    """Rename di una playlist. Su playlist sincronizzabili blocca il nome (name_locked)."""
    name: str = Field(min_length=1, max_length=200)
```

In `routers/playlists.py`: importa `PlaylistUpdateIn`; aggiungi l'endpoint sopra `list_imported` (l'ordine dei route con path `/{playlist_id}` non confligge con i path statici già definiti prima):

```python
@router.patch("/{playlist_id}", response_model=PlaylistOut)
def update_playlist(playlist_id: int, req: PlaylistUpdateIn, db: Session = Depends(get_db)):
    """Rename della playlist. Il nome scelto e' definitivo: `name_locked` impedisce
    al sync di risovrascriverlo dalla piattaforma (no-op sulle playlist manuali,
    che un sync non ce l'hanno)."""
    playlist = get_playlist(db, playlist_id)
    if playlist is None:
        raise api_error(404, "playlist_not_found", "Playlist not found")
    name = req.name.strip()
    if not name:
        raise api_error(422, "playlist_name_empty", "Playlist name is empty.")
    playlist.name = name
    playlist.name_locked = True
    db.commit()
    db.refresh(playlist)
    return PlaylistOut.model_validate(playlist)
```

In `services/playlist_import.py` riga ~387, sostituisci `playlist.name = name` con:

```python
    if not playlist.name_locked:
        playlist.name = name
```

- [ ] **Step 4: Verifica che passino**

Run: `pytest tests/test_playlist_rename.py -q` → PASS. Poi `pytest tests -q -k "playlist"` per non-regressione.

- [ ] **Step 5: Commit**

```bash
git add backend/app/models.py backend/app/schemas.py backend/app/routers/playlists.py backend/app/services/playlist_import.py backend/tests/test_playlist_rename.py
git commit -m "feat(playlists): rename con name_locked, il sync rispetta il nome scelto"
```

---

### Task 2: Rename playlist — frontend

**Files:**
- Modify: `frontend/lib/api/playlists.ts`
- Modify: `frontend/lib/api/types.ts` (interfaccia `Playlist`)
- Modify: `frontend/app/playlists/[id]/page.tsx` (titolo → edit inline)
- Modify: `frontend/lib/i18n/it.ts`, `frontend/lib/i18n/en.ts`

**Interfaces:**
- Consumes: `PATCH /api/playlists/{id}` (Task 1).
- Produces: `renamePlaylist(id: number, name: string): Promise<Playlist>` in `lib/api/playlists.ts`.

- [ ] **Step 1: API client + tipo**

In `types.ts` aggiungi `name_locked: boolean;` all'interfaccia `Playlist`. In `playlists.ts` (serve `apiPatch`: esiste già in `client.ts`? verificare; se manca, aggiungere `apiPatch` sul modello di `apiPost`):

```typescript
/** Rinomina la playlist. Il nome scelto e' definitivo: il sync non lo sovrascrive. */
export function renamePlaylist(id: number, name: string) {
  return apiPatch<Playlist>(`/api/playlists/${id}`, { name });
}
```

- [ ] **Step 2: i18n**

In `it.ts`, sezione `playlists`:

```typescript
    renameTitle: "Rinomina playlist",
    renameFailed: (msg: string) => `Rinomina fallita: ${msg}`,
```

In `en.ts` le stesse chiavi (`"Rename playlist"`, `` (msg: string) => `Rename failed: ${msg}` ``).

- [ ] **Step 3: UI inline nel dettaglio**

In `app/playlists/[id]/page.tsx`: stato `const [renaming, setRenaming] = useState(false);` + handler; accanto all'`<h1>` un bottone matita (icona `Pencil` già importata) visibile sempre; quando `renaming` è true l'`<h1>` diventa un `<Input>` con `defaultValue={playlist.name}`, submit su Enter (chiama `renamePlaylist`, `setPlaylist(updated)`), Escape annulla:

```tsx
{renaming ? (
  <Input
    className="h-9 max-w-md text-xl font-semibold"
    defaultValue={playlist.name}
    autoFocus
    aria-label={t.playlists.renameTitle}
    onBlur={() => setRenaming(false)}
    onKeyDown={async (e) => {
      if (e.key === "Enter") {
        const v = (e.target as HTMLInputElement).value.trim();
        if (!v || v === playlist.name) { setRenaming(false); return; }
        try {
          const updated = await renamePlaylist(pid, v);
          setPlaylist(updated);
        } catch (err) {
          setActionError(t.playlists.renameFailed(errText(err)));
        }
        setRenaming(false);
      } else if (e.key === "Escape") setRenaming(false);
    }}
  />
) : (
  <h1 className="text-2xl font-semibold tracking-tight">{playlist.name}</h1>
)}
{!renaming && (
  <button onClick={() => setRenaming(true)} title={t.playlists.renameTitle}
    className="text-faint transition-colors hover:text-fg-strong"><Pencil size={15} /></button>
)}
```

- [ ] **Step 4: Verifica**

Run: `cd frontend && npm run lint` → 0 errori.

- [ ] **Step 5: Commit**

```bash
git add frontend/lib/api/playlists.ts frontend/lib/api/types.ts frontend/app/playlists/\[id\]/page.tsx frontend/lib/i18n/it.ts frontend/lib/i18n/en.ts frontend/lib/api/client.ts
git commit -m "feat(playlists): rename inline dal dettaglio playlist"
```

---

### Task 3: Riordino esteso + ordine completo + playlist_position — backend

**Files:**
- Modify: `backend/app/routers/playlists.py` (guard riordino, endpoint PUT /order, playlist_position)
- Modify: `backend/app/repositories.py` (nuova `set_playlist_order`)
- Modify: `backend/app/schemas.py` (`PlaylistOrderRequest`, `TrackOut.playlist_position`)
- Modify: `backend/tests/test_playlist_reorder.py` (guard aggiornato)
- Test: `backend/tests/test_playlist_order.py` (nuovo)

**Interfaces:**
- Produces: `REORDERABLE_KINDS = {"manual", "shazam"}` (module-level in routers/playlists.py); errore 409 diventa `playlist_not_reorderable`.
- Produces: `PUT /api/playlists/{id}/order` body `{"track_ids": [int, ...]}` (permutazione completa) → `list[TrackOut]` riordinata. 422 `order_mismatch` se gli id non coincidono con i membri.
- Produces: `repositories.set_playlist_order(db, playlist_id: int, track_ids: list[int]) -> list[Track] | None` (None = mismatch; non committa).
- Produces: `TrackOut.playlist_position: int | None` valorizzato (1-based) SOLO da `GET /api/playlists/{id}/tracks`.

- [ ] **Step 1: Test che falliscono** (`tests/test_playlist_order.py`; stessa fixture `client_db`/`_pl`/`_members` di `test_playlist_reorder.py`, copiala)

```python
def test_set_order_permuta(client_db):
    client, db = client_db
    pl = _pl(db)
    ids = _members(db, pl, 4)
    r = client.put(f"/api/playlists/{pl.id}/order", json={"track_ids": [ids[2], ids[0], ids[3], ids[1]]})
    assert r.status_code == 200
    assert [t["title"] for t in r.json()] == ["T2", "T0", "T3", "T1"]
    assert [t["playlist_position"] for t in client.get(f"/api/playlists/{pl.id}/tracks").json()] == [1, 2, 3, 4]


def test_set_order_mismatch_422(client_db):
    client, db = client_db
    pl = _pl(db)
    ids = _members(db, pl, 3)
    r = client.put(f"/api/playlists/{pl.id}/order", json={"track_ids": [ids[0], ids[1]]})
    assert r.status_code == 422


def test_set_order_409_su_kind_non_riordinabile(client_db):
    client, db = client_db
    pl = _pl(db, kind="playlist")
    ids = _members(db, pl, 2)
    assert client.put(f"/api/playlists/{pl.id}/order", json={"track_ids": ids}).status_code == 409


def test_reorder_singolo_su_shazam_ok(client_db):
    client, db = client_db
    pl = _pl(db, kind="shazam")
    ids = _members(db, pl, 3)
    r = client.post(f"/api/playlists/{pl.id}/reorder", json={"track_id": ids[2], "position": 1})
    assert r.status_code == 200
    assert [t["title"] for t in r.json()] == ["T2", "T0", "T1"]
```

- [ ] **Step 2: Verifica FAIL** (`pytest tests/test_playlist_order.py -q`)

- [ ] **Step 3: Implementa**

`repositories.py`, sotto `reorder_playlist_track`:

```python
def set_playlist_order(db: Session, playlist_id: int, track_ids: list[int]) -> list[Track] | None:
    """Sostituisce l'ordine completo della playlist con la permutazione data e
    rinumera 1..N. None se `track_ids` non e' una permutazione esatta dei membri.
    Non committa."""
    current = [t.id for t in tracks_for_playlist(db, playlist_id)]
    if sorted(current) != sorted(track_ids):
        return None
    for new_pos, tid in enumerate(track_ids, start=1):
        db.execute(playlist_tracks.update().where(
            playlist_tracks.c.playlist_id == playlist_id,
            playlist_tracks.c.track_id == tid,
        ).values(position=new_pos))
    return tracks_for_playlist(db, playlist_id)
```

`schemas.py`: in `TrackOut` aggiungi `playlist_position: int | None = None` (dopo `playlists`); nuova request sotto `PlaylistReorderRequest`:

```python
class PlaylistOrderRequest(BaseModel):
    """Ordine completo della playlist: permutazione esatta dei membri."""
    track_ids: list[int] = Field(min_length=1)
```

`routers/playlists.py`: importa `set_playlist_order` e `PlaylistOrderRequest`; sopra `reorder_track` definisci la costante e il guard condiviso:

```python
# Kind con ordine posseduto dall'utente (nessuna sorgente che lo ridetta).
REORDERABLE_KINDS = {"manual", "shazam"}


def _reorderable_or_409(playlist: Playlist) -> None:
    if playlist.kind not in REORDERABLE_KINDS:
        raise api_error(409, "playlist_not_reorderable",
                        "Reorder is only allowed on manual and shazam playlists")
```

In `reorder_track` sostituisci il check `if playlist.kind != "manual": raise ...` con `_reorderable_or_409(playlist)`. Nuovo endpoint dopo `reorder_track`:

```python
@router.put("/{playlist_id}/order", response_model=list[TrackOut])
def set_order(playlist_id: int, req: PlaylistOrderRequest, db: Session = Depends(get_db)):
    """Sostituisce l'ordine completo (drag-and-drop): permutazione esatta dei membri."""
    playlist = get_playlist(db, playlist_id)
    if playlist is None:
        raise api_error(404, "playlist_not_found", "Playlist not found")
    _reorderable_or_409(playlist)
    result = set_playlist_order(db, playlist_id, req.track_ids)
    if result is None:
        raise api_error(422, "order_mismatch",
                        "track_ids must be an exact permutation of the playlist members")
    db.commit()
    return [track_out(t) for t in result]
```

In `playlist_tracks` (GET /{id}/tracks) valorizza la posizione:

```python
    out = []
    for i, t in enumerate(tracks_for_playlist(db, playlist_id), start=1):
        row = track_out(t)
        row.playlist_position = i
        out.append(row)
    return out
```

In `test_playlist_reorder.py` aggiorna il commento/nome del test 409 se serve (resta valido: kind="playlist" non è riordinabile).

- [ ] **Step 4: Verifica PASS** — `pytest tests/test_playlist_order.py tests/test_playlist_reorder.py -q`, poi `pytest tests -q -k "playlist or track"`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/playlists.py backend/app/repositories.py backend/app/schemas.py backend/tests/test_playlist_order.py backend/tests/test_playlist_reorder.py
git commit -m "feat(playlists): ordine completo via PUT /order, riordino anche su shazam, playlist_position nei payload"
```

---

### Task 4: Drag-and-drop riordino — frontend

**Files:**
- Modify: `frontend/lib/api/playlists.ts` (`setPlaylistOrder`)
- Modify: `frontend/app/playlists/[id]/page.tsx`
- Modify: `frontend/lib/i18n/it.ts`, `frontend/lib/i18n/en.ts`

**Interfaces:**
- Consumes: `PUT /api/playlists/{id}/order` (Task 3).
- Produces: `setPlaylistOrder(playlistId: number, trackIds: number[]): Promise<Track[]>`.

- [ ] **Step 1: API client**

```typescript
/** Sostituisce l'ordine completo della playlist (drag-and-drop). */
export function setPlaylistOrder(playlistId: number, trackIds: number[]) {
  return apiPut<Track[]>(`/api/playlists/${playlistId}/order`, { track_ids: trackIds });
}
```

(`apiPut` come per `apiPatch`: se manca in `client.ts`, aggiungerlo sul modello di `apiPost`.)

- [ ] **Step 2: i18n** — `it.ts`: `dragToReorderHint: "Trascina le righe per riordinare (senza filtri né ordinamenti attivi)",`; `en.ts` equivalente.

- [ ] **Step 3: DnD nella tabella**

In `page.tsx`:
- `const canReorder = playlist?.kind === "manual" || playlist?.kind === "shazam";` (sostituisce il check solo-manual).
- Il drag è attivo solo quando la vista È l'ordine playlist: `const dragEnabled = canReorder && sort === "" && visible.length === tracks.length;`
- Stato `const [dragId, setDragId] = useState<number | null>(null);`
- Sulle `<tr>`: `draggable={dragEnabled}`, `onDragStart={() => setDragId(tr.id)}`, `onDragOver={(e) => { if (dragEnabled && dragId !== null) e.preventDefault(); }}`, `onDrop={() => dragId !== null && dragId !== tr.id && applyDrop(tr.id)}`, `onDragEnd={() => setDragId(null)}`, classe extra `dragEnabled ? "cursor-grab" : ""` e `dragId === tr.id ? "opacity-40" : ""`.
- Handler:

```tsx
const applyDrop = async (targetId: number) => {
  if (dragId === null) return;
  const ids = tracks.map((x) => x.id).filter((x) => x !== dragId);
  ids.splice(ids.indexOf(targetId), 0, dragId);
  setDragId(null);
  setActionError(null);
  setReordering(true);
  try {
    setTracks(await setPlaylistOrder(pid, ids));
  } catch (e) {
    setActionError(t.playlists.reorderFailed(errText(e)));
    reload();
  } finally {
    setReordering(false);
  }
};
```

- Sotto la tabella, se `canReorder && !dragEnabled` mostra il suggerimento `t.playlists.dragToReorderHint` in `text-xs text-faint` (spiega perché il drag è spento con filtri/sort attivi); se `dragEnabled`, mostralo come hint neutro.

- [ ] **Step 4: Verifica** — `npm run lint`; poi verifica visiva col dev server (preview): trascina una riga su una playlist manuale e ricontrolla l'ordine dopo un refresh.

- [ ] **Step 5: Commit**

```bash
git add frontend/lib/api/playlists.ts frontend/lib/api/client.ts frontend/app/playlists/\[id\]/page.tsx frontend/lib/i18n/it.ts frontend/lib/i18n/en.ts
git commit -m "feat(playlists): drag-and-drop per riordinare le playlist manuali e shazam"
```

---

### Task 5: Rimozione bulk — backend

**Files:**
- Modify: `backend/app/repositories.py` (nuova `delete_playlist_tracks`)
- Modify: `backend/app/schemas.py` (`PlaylistRemoveTracksRequest`, `PlaylistBulkRemoveResult`)
- Modify: `backend/app/routers/playlists.py`
- Test: `backend/tests/test_playlist_bulk_remove.py` (nuovo)

**Interfaces:**
- Produces: `POST /api/playlists/{id}/tracks/remove` body `{"track_ids": [int, ...]}` → `{"removed": int, "deleted_tracks": int}`. 404 solo se la playlist non esiste; id non-membri vengono ignorati (removed conta solo le membership tolte).
- Produces: `repositories.delete_playlist_tracks(db, playlist_id, track_ids) -> tuple[int, int] | None` — (membership rimosse, lead orfani cancellati); committa (stessa politica di `delete_playlist_track`).

- [ ] **Step 1: Test che falliscono** (fixture `client_db` come in `test_playlist_reorder.py`; helper `_pl`/`_members` copiati)

```python
def test_bulk_remove_toglie_membership_e_orfani(client_db):
    client, db = client_db
    pl = _pl(db)
    ids = _members(db, pl, 4)  # lead: source_type local_files ma has_local_file False di default
    r = client.post(f"/api/playlists/{pl.id}/tracks/remove", json={"track_ids": ids[:2]})
    assert r.status_code == 200
    assert r.json()["removed"] == 2
    assert r.json()["deleted_tracks"] == 2  # orfani: non su disco, in nessun'altra playlist/set
    rest = client.get(f"/api/playlists/{pl.id}/tracks").json()
    assert [t["title"] for t in rest] == ["T2", "T3"]


def test_bulk_remove_ignora_non_membri(client_db):
    client, db = client_db
    pl = _pl(db)
    ids = _members(db, pl, 2)
    r = client.post(f"/api/playlists/{pl.id}/tracks/remove", json={"track_ids": [ids[0], 99999]})
    assert r.status_code == 200
    assert r.json()["removed"] == 1


def test_bulk_remove_playlist_inesistente_404(client_db):
    client, _ = client_db
    assert client.post("/api/playlists/9999/tracks/remove", json={"track_ids": [1]}).status_code == 404
```

- [ ] **Step 2: Verifica FAIL** — `pytest tests/test_playlist_bulk_remove.py -q`

- [ ] **Step 3: Implementa**

`repositories.py`, sotto `delete_playlist_track`:

```python
def delete_playlist_tracks(db: Session, playlist_id: int, track_ids: list[int]) -> tuple[int, int] | None:
    """Toglie piu' tracce dalla playlist in un colpo; i lead diventati orfani
    vengono cancellati (stessa politica di `delete_playlist_track`). Ritorna
    (membership rimosse, orfani cancellati), o None se la playlist non esiste.
    Gli id non-membri sono ignorati. Committa."""
    playlist = get_playlist(db, playlist_id)
    if playlist is None:
        return None
    members = set(db.scalars(
        select(playlist_tracks.c.track_id).where(
            playlist_tracks.c.playlist_id == playlist_id,
            playlist_tracks.c.track_id.in_(track_ids),
        )
    ).all())
    if not members:
        db.commit()
        return (0, 0)
    db.execute(playlist_tracks.delete().where(
        playlist_tracks.c.playlist_id == playlist_id,
        playlist_tracks.c.track_id.in_(members),
    ))
    recount_playlist(db, playlist)
    db.flush()  # le membership rimosse devono essere visibili al check orfani
    deleted = delete_orphan_leads(db, list(members))
    db.commit()
    return (len(members), deleted)
```

`schemas.py`, sotto `PlaylistDeleteResult`:

```python
class PlaylistRemoveTracksRequest(BaseModel):
    """Rimozione bulk di tracce dalla playlist."""
    track_ids: list[int] = Field(min_length=1)


class PlaylistBulkRemoveResult(BaseModel):
    removed: int = 0          # membership tolte
    deleted_tracks: int = 0   # lead orfani cancellati dalla libreria
```

`routers/playlists.py`, dopo `remove_playlist_track` (import di `delete_playlist_tracks` e dei due schemi):

```python
@router.post("/{playlist_id}/tracks/remove", response_model=PlaylistBulkRemoveResult)
def remove_playlist_tracks(playlist_id: int, req: PlaylistRemoveTracksRequest, db: Session = Depends(get_db)):
    """Toglie piu' tracce dalla playlist (bulk). I lead diventati orfani vengono
    cancellati come nella rimozione singola; gli id non-membri sono ignorati."""
    result = delete_playlist_tracks(db, playlist_id, req.track_ids)
    if result is None:
        raise api_error(404, "playlist_not_found", "Playlist not found")
    removed, deleted = result
    return PlaylistBulkRemoveResult(removed=removed, deleted_tracks=deleted)
```

- [ ] **Step 4: Verifica PASS** — `pytest tests/test_playlist_bulk_remove.py -q` poi `pytest tests -q -k playlist`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/repositories.py backend/app/schemas.py backend/app/routers/playlists.py backend/tests/test_playlist_bulk_remove.py
git commit -m "feat(playlists): rimozione bulk di tracce con cleanup dei lead orfani"
```

---

### Task 6: Selezione multipla + azioni bulk — frontend

**Files:**
- Modify: `frontend/lib/api/playlists.ts` (`removeTracksFromPlaylist`)
- Modify: `frontend/components/add-to-playlist-menu.tsx` (generalizza a più tracce)
- Modify: `frontend/app/playlists/[id]/page.tsx` (checkbox + barra selezione)
- Modify: `frontend/lib/i18n/it.ts`, `frontend/lib/i18n/en.ts`

**Interfaces:**
- Consumes: `POST /api/playlists/{id}/tracks/remove` (Task 5), `addTracksToPlaylist` (esistente).
- Produces: `removeTracksFromPlaylist(playlistId: number, trackIds: number[]): Promise<{removed: number; deleted_tracks: number}>`.
- Produces: `AddToPlaylistMenu` accetta la nuova prop-shape `{ trackIds: number[]; inPlaylistIds?: number[]; onChanged: () => void; excludePlaylistId?: number }` (il call-site esistente nel dettaglio traccia va aggiornato: `trackIds={[track.id]}`, `inPlaylistIds={track.playlists.map(p => p.id)}`).

- [ ] **Step 1: API client + tipo risultato**

```typescript
/** Toglie più tracce dalla playlist (bulk); i lead orfani vengono cancellati. */
export function removeTracksFromPlaylist(playlistId: number, trackIds: number[]) {
  return apiPost<{ removed: number; deleted_tracks: number }>(
    `/api/playlists/${playlistId}/tracks/remove`, { track_ids: trackIds });
}
```

- [ ] **Step 2: Generalizza AddToPlaylistMenu**

Cambia la firma in `{ trackIds, inPlaylistIds = [], excludePlaylistId, onChanged }`; dentro: `const inIds = new Set(inPlaylistIds);` (marca "già presente" solo con 1 traccia: `trackIds.length === 1`); filtro playlist `all.filter((p) => p.kind === "manual" && p.id !== excludePlaylistId)`; `addTo` chiama `addTracksToPlaylist(pl.id, trackIds)`; `createAndAdd` chiama `createPlaylistFromTracks(newName.trim(), trackIds)`. Aggiorna il call-site in `frontend/app/tracks/[id]/page.tsx` (cerca `<AddToPlaylistMenu`): `trackIds={[track.id]} inPlaylistIds={track.playlists.map((p) => p.id)}`.

- [ ] **Step 3: i18n**

`it.ts` sezione `playlists`:

```typescript
    selectedCount: (n: number) => `${n} selezionate`,
    bulkRemoveButton: "Togli dalla playlist",
    bulkRemoveConfirm: (n: number) =>
      `Togliere ${n} tracce da questa playlist? I lead senza file su disco, non in altre playlist né in un set, verranno cancellati.`,
    bulkRemoved: (n: number, deleted: number) =>
      deleted > 0 ? `${n} tracce tolte · ${deleted} lead orfani rimossi.` : `${n} tracce tolte dalla playlist.`,
    bulkAddedTo: (name: string, added: number, skipped: number) =>
      skipped > 0 ? `${added} aggiunte a ${name} (${skipped} già presenti).` : `${added} aggiunte a ${name}.`,
    clearSelection: "Deseleziona",
```

`en.ts` equivalenti.

- [ ] **Step 4: Selezione nella tabella**

In `page.tsx`:
- Stato `const [selected, setSelected] = useState<Set<number>>(new Set());` — azzera la selezione quando cambiano i `tracks` (`useEffect` su `tracks`: `setSelected(new Set())`).
- Colonna in più a sinistra: nell'header un `<Checkbox>` che seleziona/deseleziona tutte le righe **visibili** (`visible`, non solo la pagina); in ogni riga un checkbox che aggiunge/toglie `tr.id`. Aggiorna il `colSpan` dell'empty-state (da 10 a 11).
- Barra sticky sopra la tabella quando `selected.size > 0`:

```tsx
{selected.size > 0 && (
  <div className="mb-2 flex flex-wrap items-center gap-2 border border-border bg-elevated px-3 py-2 text-sm">
    <span className="text-muted">{t.playlists.selectedCount(selected.size)}</span>
    <AddToPlaylistMenu trackIds={[...selected]} excludePlaylistId={pid} onChanged={() => reload()} />
    <Button size="sm" variant="danger" onClick={() => setConfirmBulkRemove(true)} disabled={bulkRemoving}>
      {bulkRemoving ? <Spinner /> : <Trash2 size={14} />} {t.playlists.bulkRemoveButton}
    </Button>
    <button className="text-xs text-muted hover:text-fg" onClick={() => setSelected(new Set())}>{t.playlists.clearSelection}</button>
  </div>
)}
```

- Handler bulk remove con `ConfirmModal` (`confirmBulkRemove` boolean, message `t.playlists.bulkRemoveConfirm(selected.size)`):

```tsx
const doBulkRemove = async () => {
  const ids = [...selected];
  setBulkRemoving(true);
  setActionError(null);
  try {
    const { removed, deleted_tracks } = await removeTracksFromPlaylist(pid, ids);
    setNotice(t.playlists.bulkRemoved(removed, deleted_tracks));
    setSelected(new Set());
    getPlaylist(pid).then(setPlaylist).catch(() => {});
    reload();
  } catch (e) {
    setActionError(t.playlists.removeTrackFailed(errText(e)));
  } finally {
    setBulkRemoving(false);
  }
};
```

- [ ] **Step 5: Verifica** — `npm run lint`; verifica visiva nel dev server: seleziona 2 tracce, "Togli dalla playlist", conferma, controlla il notice e il conteggio.

- [ ] **Step 6: Commit**

```bash
git add frontend/lib/api/playlists.ts frontend/components/add-to-playlist-menu.tsx frontend/app/playlists/\[id\]/page.tsx frontend/app/tracks/\[id\]/page.tsx frontend/lib/i18n/it.ts frontend/lib/i18n/en.ts
git commit -m "feat(playlists): selezione multipla con rimozione bulk e aggiunta a playlist"
```

---

### Task 7: Duplica come manuale — backend

**Files:**
- Modify: `backend/app/routers/playlists.py`
- Modify: `backend/app/schemas.py` (`PlaylistDuplicateRequest`)
- Test: `backend/tests/test_playlist_duplicate.py` (nuovo)

**Interfaces:**
- Produces: `POST /api/playlists/{id}/duplicate` body `{"name": str | null}` → 201 `PlaylistOut` della copia (platform="manual", kind="manual", stesso ordine tracce, membership `added_by="cratory"`). Nome default: `"<nome> (copia)"`.

- [ ] **Step 1: Test che falliscono** (fixture/helper come in `test_playlist_reorder.py`)

```python
def test_duplicate_crea_copia_manuale_ordinata(client_db):
    client, db = client_db
    pl = _pl(db, kind="playlist")  # anche una playlist sincronizzata si può forkare
    ids = _members(db, pl, 3)
    r = client.post(f"/api/playlists/{pl.id}/duplicate", json={})
    assert r.status_code == 201
    body = r.json()
    assert body["kind"] == "manual" and body["platform"] == "manual"
    assert body["name"] == "P (copia)"
    assert body["track_count"] == 3
    copied = client.get(f"/api/playlists/{body['id']}/tracks").json()
    assert [t["title"] for t in copied] == ["T0", "T1", "T2"]


def test_duplicate_nome_custom(client_db):
    client, db = client_db
    pl = _pl(db)
    _members(db, pl, 1)
    r = client.post(f"/api/playlists/{pl.id}/duplicate", json={"name": "Mia copia"})
    assert r.status_code == 201
    assert r.json()["name"] == "Mia copia"


def test_duplicate_404(client_db):
    client, _ = client_db
    assert client.post("/api/playlists/9999/duplicate", json={}).status_code == 404
```

- [ ] **Step 2: Verifica FAIL** — `pytest tests/test_playlist_duplicate.py -q`

- [ ] **Step 3: Implementa**

`schemas.py`:

```python
class PlaylistDuplicateRequest(BaseModel):
    """Fork della playlist in una copia manuale (riordinabile/editabile)."""
    name: str | None = Field(default=None, max_length=200)
```

`routers/playlists.py` (dopo `create_from_tracks`):

```python
@router.post("/{playlist_id}/duplicate", response_model=PlaylistOut, status_code=201)
def duplicate_playlist(playlist_id: int, req: PlaylistDuplicateRequest, db: Session = Depends(get_db)):
    """Fork: copia la playlist in una manuale (stesso ordine). Una playlist
    sincronizzata non e' riordinabile ne' editabile: la copia manuale si'."""
    src = get_playlist(db, playlist_id)
    if src is None:
        raise api_error(404, "playlist_not_found", "Playlist not found")
    name = (req.name or f"{src.name} (copia)").strip()
    if not name:
        raise api_error(422, "playlist_name_empty", "Playlist name is empty.")
    copy = Playlist(platform="manual", name=name, kind="manual")
    db.add(copy)
    db.flush()
    for track in tracks_for_playlist(db, playlist_id):
        add_track_to_playlist(db, track, copy, added_by="cratory")
    recount_playlist(db, copy)
    db.commit()
    db.refresh(copy)
    return PlaylistOut.model_validate(copy)
```

- [ ] **Step 4: Verifica PASS** — `pytest tests/test_playlist_duplicate.py -q` poi `pytest tests -q -k playlist`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/playlists.py backend/app/schemas.py backend/tests/test_playlist_duplicate.py
git commit -m "feat(playlists): duplica una playlist come copia manuale editabile"
```

---

### Task 8: Duplica — frontend

**Files:**
- Modify: `frontend/lib/api/playlists.ts` (`duplicatePlaylist`)
- Modify: `frontend/app/playlists/[id]/page.tsx` (bottone in sidebar)
- Modify: `frontend/lib/i18n/it.ts`, `frontend/lib/i18n/en.ts`

**Interfaces:**
- Consumes: `POST /api/playlists/{id}/duplicate` (Task 7).
- Produces: `duplicatePlaylist(id: number, name?: string): Promise<Playlist>`.

- [ ] **Step 1: API client**

```typescript
/** Fork della playlist in una copia manuale (riordinabile/editabile). */
export function duplicatePlaylist(id: number, name?: string) {
  return apiPost<Playlist>(`/api/playlists/${id}/duplicate`, { name: name ?? null });
}
```

- [ ] **Step 2: i18n** — `it.ts`: `duplicateButton: "Duplica come manuale",` e `duplicateFailed: (msg: string) => \`Duplicazione fallita: ${msg}\`,`; `en.ts` equivalenti (`"Duplicate as manual"`).

- [ ] **Step 3: Bottone in sidebar** (in `marginalia`, sopra il bottone Rimuovi; icona `Copy` da lucide-react):

```tsx
<Button size="sm" variant="outline" className="w-full" onClick={doDuplicate} disabled={duplicating}>
  {duplicating ? <Spinner /> : <Copy size={14} />} {t.playlists.duplicateButton}
</Button>
```

```tsx
const doDuplicate = async () => {
  setDuplicating(true);
  setActionError(null);
  try {
    const copy = await duplicatePlaylist(pid);
    router.push(`/playlists/${copy.id}`);
  } catch (e) {
    setActionError(t.playlists.duplicateFailed(errText(e)));
    setDuplicating(false);
  }
};
```

- [ ] **Step 4: Verifica** — `npm run lint`; visiva: duplica una playlist Spotify, atterra sulla copia manuale riordinabile.

- [ ] **Step 5: Commit**

```bash
git add frontend/lib/api/playlists.ts frontend/app/playlists/\[id\]/page.tsx frontend/lib/i18n/it.ts frontend/lib/i18n/en.ts
git commit -m "feat(playlists): bottone Duplica come manuale nel dettaglio"
```

---

### Task 9: Storico diff dei sync — backend

**Files:**
- Modify: `backend/app/models.py` (nuova `PlaylistSyncEvent`)
- Modify: `backend/app/services/playlist_import.py` (registra il diff)
- Modify: `backend/app/repositories.py` (cleanup eventi in `delete_playlist`)
- Modify: `backend/app/schemas.py` (`PlaylistSyncEventOut`, `SyncTrackRef`)
- Modify: `backend/app/routers/playlists.py` (`GET /{id}/sync-log`)
- Test: `backend/tests/test_playlist_sync_log.py` (nuovo)

**Interfaces:**
- Produces: tabella `playlist_sync_events` (creata da create_all in `ensure_schema`, nessuna migrazione a mano).
- Produces: `GET /api/playlists/{id}/sync-log?limit=20` → `list[PlaylistSyncEventOut]` (più recente prima): `{id, created_at, added: [{id, artist, title}], removed: [{id, artist, title}]}`. Un sync senza variazioni NON crea eventi.
- `import_playlist` registra l'evento dentro la stessa transazione del commit finale.

- [ ] **Step 1: Test che falliscono**

```python
"""Storico diff dei sync: playlist_sync_events + GET /sync-log."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app
from app.services.playlist_import import import_playlist


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


def _item(sid: str, title: str, artist: str = "A"):
    """Item Spotify minimale per normalize_spotify_item."""
    return {"track": {
        "id": sid, "name": title, "duration_ms": 200000,
        "artists": [{"name": artist}], "album": {"images": []},
        "external_ids": {"isrc": None}, "external_urls": {},
    }}


def test_import_e_prune_registrano_eventi(client_db):
    client, db = client_db
    report = import_playlist(db, platform="spotify", name="P",
                             items=[_item("s1", "Uno"), _item("s2", "Due")],
                             platform_playlist_id="pl1")
    pid = report["playlist_id"]
    log = client.get(f"/api/playlists/{pid}/sync-log").json()
    assert len(log) == 1
    assert sorted(t["title"] for t in log[0]["added"]) == ["Due", "Uno"]
    assert log[0]["removed"] == []

    # secondo sync: s2 sparisce (prune), s3 entra
    import_playlist(db, platform="spotify", name="P",
                    items=[_item("s1", "Uno"), _item("s3", "Tre")],
                    platform_playlist_id="pl1", prune=True)
    log = client.get(f"/api/playlists/{pid}/sync-log").json()
    assert len(log) == 2
    latest = log[0]
    assert [t["title"] for t in latest["added"]] == ["Tre"]
    assert [t["title"] for t in latest["removed"]] == ["Due"]


def test_sync_senza_variazioni_non_crea_eventi(client_db):
    client, db = client_db
    items = [_item("s1", "Uno")]
    report = import_playlist(db, platform="spotify", name="P", items=items, platform_playlist_id="pl1")
    import_playlist(db, platform="spotify", name="P", items=items, platform_playlist_id="pl1", prune=True)
    log = client.get(f"/api/playlists/{report['playlist_id']}/sync-log").json()
    assert len(log) == 1  # solo il primo import


def test_sync_log_404(client_db):
    client, _ = client_db
    assert client.get("/api/playlists/9999/sync-log").status_code == 404
```

Nota: verificare la forma esatta accettata da `normalize_spotify_item` (leggerla in `services/playlist_import.py`) e adeguare `_item` se serve.

- [ ] **Step 2: Verifica FAIL** — `pytest tests/test_playlist_sync_log.py -q`

- [ ] **Step 3: Implementa**

`models.py`, dopo `Playlist`:

```python
class PlaylistSyncEvent(Base):
    """Diff di un import/sync di playlist: quali tracce sono entrate/uscite.

    Snapshot testuale (artist/title) perche' una traccia rimossa puo' sparire
    dalla libreria (lead orfano): l'evento resta leggibile comunque."""

    __tablename__ = "playlist_sync_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    playlist_id: Mapped[int] = mapped_column(ForeignKey("playlists.id"), index=True)
    added_tracks: Mapped[list] = mapped_column(JSON, default=list)    # [{id, artist, title}]
    removed_tracks: Mapped[list] = mapped_column(JSON, default=list)  # [{id, artist, title}]
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
```

`services/playlist_import.py`, in `import_playlist`:
- import `PlaylistSyncEvent` da `app.models`.
- Dopo il `db.flush()` che segue la creazione/lookup della playlist: `before_ids = {t.id for t in tracks_for_playlist(db, playlist.id)}`.
- Nel loop di prune, accanto a `removed += 1`: `removed_details.append({"id": track.id, "artist": track.artist, "title": track.title})` (inizializza `removed_details: list[dict] = []` prima del blocco prune).
- Prima di `recount_playlist(db, playlist)`:

```python
    after = tracks_for_playlist(db, playlist.id)
    added_details = [
        {"id": t.id, "artist": t.artist, "title": t.title}
        for t in after if t.id not in before_ids
    ]
    if added_details or removed_details:
        db.add(PlaylistSyncEvent(
            playlist_id=playlist.id,
            added_tracks=added_details, removed_tracks=removed_details,
        ))
```

`repositories.py`, in `delete_playlist` prima di `db.delete(playlist)`:

```python
    db.execute(delete(PlaylistSyncEvent).where(PlaylistSyncEvent.playlist_id == playlist_id))
```

(import di `PlaylistSyncEvent` in testa al file, dove sono importati gli altri modelli).

`schemas.py`:

```python
class SyncTrackRef(BaseModel):
    """Riferimento snapshot a una traccia in un evento di sync (l'id puo' essere
    di una traccia nel frattempo cancellata come lead orfano)."""
    id: int | None = None
    artist: str | None = None
    title: str | None = None


class PlaylistSyncEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    added: list[SyncTrackRef] = []
    removed: list[SyncTrackRef] = []
```

`routers/playlists.py` (import `PlaylistSyncEvent` dai modelli, `desc` non serve: usa `order_by(...id.desc())`):

```python
@router.get("/{playlist_id}/sync-log", response_model=list[PlaylistSyncEventOut])
def playlist_sync_log(playlist_id: int, limit: int = Query(default=20, ge=1, le=100),
                      db: Session = Depends(get_db)):
    """Ultimi diff di import/sync (piu' recente prima): cosa e' entrato e uscito."""
    if get_playlist(db, playlist_id) is None:
        raise api_error(404, "playlist_not_found", "Playlist not found")
    events = db.scalars(
        select(PlaylistSyncEvent).where(PlaylistSyncEvent.playlist_id == playlist_id)
        .order_by(PlaylistSyncEvent.id.desc()).limit(limit)
    ).all()
    return [
        PlaylistSyncEventOut(
            id=e.id, created_at=e.created_at,
            added=[SyncTrackRef(**x) for x in (e.added_tracks or [])],
            removed=[SyncTrackRef(**x) for x in (e.removed_tracks or [])],
        )
        for e in events
    ]
```

- [ ] **Step 4: Verifica PASS** — `pytest tests/test_playlist_sync_log.py -q`, poi `pytest tests -q` COMPLETO (import_playlist è toccato da molti test).

- [ ] **Step 5: Commit**

```bash
git add backend/app/models.py backend/app/services/playlist_import.py backend/app/repositories.py backend/app/schemas.py backend/app/routers/playlists.py backend/tests/test_playlist_sync_log.py
git commit -m "feat(playlists): storico diff dei sync (playlist_sync_events + GET /sync-log)"
```

---

### Task 10: Storico sync — frontend

**Files:**
- Modify: `frontend/lib/api/playlists.ts` + `frontend/lib/api/types.ts`
- Modify: `frontend/app/playlists/[id]/page.tsx` (pannello collassabile)
- Modify: `frontend/lib/i18n/it.ts`, `frontend/lib/i18n/en.ts`

**Interfaces:**
- Consumes: `GET /api/playlists/{id}/sync-log` (Task 9).
- Produces: `playlistSyncLog(id: number, opts?): Promise<PlaylistSyncEvent[]>`; tipo `PlaylistSyncEvent {id; created_at; added: SyncTrackRef[]; removed: SyncTrackRef[]}`, `SyncTrackRef {id: number | null; artist: string | null; title: string | null}`.

- [ ] **Step 1: Tipi + API client**

```typescript
export interface SyncTrackRef { id: number | null; artist: string | null; title: string | null; }
export interface PlaylistSyncEvent { id: number; created_at: string; added: SyncTrackRef[]; removed: SyncTrackRef[]; }
```

```typescript
/** Ultimi diff di import/sync della playlist (più recente prima). */
export function playlistSyncLog(id: number, opts?: { signal?: AbortSignal }) {
  return apiGet<PlaylistSyncEvent[]>(`/api/playlists/${id}/sync-log`, undefined, opts);
}
```

- [ ] **Step 2: i18n**

`it.ts`:

```typescript
    syncLogHeading: (n: number) => `Storico sync · ${n}`,
    syncLogAdded: (n: number) => n === 1 ? "1 aggiunta" : `${n} aggiunte`,
    syncLogRemoved: (n: number) => n === 1 ? "1 rimossa" : `${n} rimosse`,
    syncLogEmpty: "Nessuna variazione registrata.",
```

`en.ts` equivalenti.

- [ ] **Step 3: Pannello nel dettaglio**

In `page.tsx`: stato `const [syncLog, setSyncLog] = useState<PlaylistSyncEvent[]>([]);`; caricalo in `reload` (`playlistSyncLog(pid, { signal }).then(setSyncLog).catch(() => {});` — così si aggiorna anche dopo un sync). Mostra il pannello solo su playlist sincronizzabili (`canSync`) e se `syncLog.length > 0`, come `<details>` gemello del pannello gaps (stesso markup), subito sotto di esso:

```tsx
{canSync && syncLog.length > 0 && (
  <details className="group mb-4 border border-border">
    <summary className="flex cursor-pointer list-none items-center justify-between gap-2 px-4 py-3 text-xs font-semibold uppercase tracking-wide text-muted transition-colors hover:text-fg [&::-webkit-details-marker]:hidden">
      <span>{t.playlists.syncLogHeading(syncLog.length)}</span>
      <ChevronDown size={15} className="text-faint transition-transform duration-200 group-open:rotate-180" />
    </summary>
    <div className="grid gap-3 border-t border-border p-4 text-sm">
      {syncLog.map((ev) => (
        <div key={ev.id}>
          <p className="text-xs text-faint">{new Date(ev.created_at).toLocaleString()} · {t.playlists.syncLogAdded(ev.added.length)} · {t.playlists.syncLogRemoved(ev.removed.length)}</p>
          {ev.added.map((x, i) => (
            <p key={`a${i}`} className="text-fg">+ {x.artist ?? "?"} — {x.title ?? "?"}</p>
          ))}
          {ev.removed.map((x, i) => (
            <p key={`r${i}`} className="text-muted">− {x.artist ?? "?"} — {x.title ?? "?"}</p>
          ))}
        </div>
      ))}
    </div>
  </details>
)}
```

- [ ] **Step 4: Verifica** — `npm run lint`; visiva dopo un sync reale (o con dati esistenti).

- [ ] **Step 5: Commit**

```bash
git add frontend/lib/api/playlists.ts frontend/lib/api/types.ts frontend/app/playlists/\[id\]/page.tsx frontend/lib/i18n/it.ts frontend/lib/i18n/en.ts
git commit -m "feat(playlists): pannello storico sync nel dettaglio playlist"
```

---

### Task 11: Export multi-formato — backend

**Files:**
- Modify: `backend/app/routers/playlists.py` (endpoint export)
- Modify: `backend/tests/test_playlist_export.py` (estendere)

**Interfaces:**
- Produces: `POST /api/playlists/{id}/export?format=m3u8|csv|text|markdown` (pattern esteso; default resta `m3u8`, comportamento m3u8 invariato).
- CSV colonne: `position,title,artist,genre,bpm,key,energy,duration_seconds,rating,owned,local_path,url`.
- text: righe `N. Artista - Titolo [BPM, Key]` (BPM/key omessi se assenti, come l'export text dei set).
- markdown: `# <nome>` + tabella `| # | Traccia | Genere | BPM | Key | Durata |`.

- [ ] **Step 1: Test che falliscono** (aggiungi a `test_playlist_export.py`, riusa fixture/helper esistenti nel file)

```python
def test_export_csv(client_db):
    client, db = client_db
    pl = _pl(db)          # adattare agli helper reali del file esistente
    _members(db, pl, 2)
    r = client.post(f"/api/playlists/{pl.id}/export?format=csv")
    assert r.status_code == 200
    lines = r.text.strip().splitlines()
    assert lines[0].startswith("position,title,artist")
    assert len(lines) == 3


def test_export_text(client_db):
    client, db = client_db
    pl = _pl(db)
    _members(db, pl, 2)
    r = client.post(f"/api/playlists/{pl.id}/export?format=text")
    assert r.status_code == 200
    assert r.text.splitlines()[0] == f"# {pl.name}"


def test_export_markdown(client_db):
    client, db = client_db
    pl = _pl(db)
    _members(db, pl, 1)
    r = client.post(f"/api/playlists/{pl.id}/export?format=markdown")
    assert r.status_code == 200
    assert "| # |" in r.text


def test_export_formato_invalido_422(client_db):
    client, db = client_db
    pl = _pl(db)
    assert client.post(f"/api/playlists/{pl.id}/export?format=xml").status_code == 422
```

- [ ] **Step 2: Verifica FAIL** — `pytest tests/test_playlist_export.py -q`

- [ ] **Step 3: Implementa** — in `routers/playlists.py` cambia il pattern in `^(m3u8|csv|text|markdown)$` e struttura l'endpoint come quello dei set (`routers/sets.py:167`), con `import csv, io` in testa al file:

```python
@router.post("/{playlist_id}/export", response_class=PlainTextResponse)
def export_playlist(
    playlist_id: int,
    format: str = Query(default="m3u8", pattern="^(m3u8|csv|text|markdown)$"),
    db: Session = Depends(get_db),
):
    """Export della playlist: M3U8 (Rekordbox, solo tracce con file locale), CSV,
    testo o Markdown (tutte le tracce, ordine playlist)."""
    playlist = get_playlist(db, playlist_id)
    if playlist is None:
        raise api_error(404, "playlist_not_found", "Playlist not found")
    tracks = tracks_for_playlist(db, playlist_id)

    if format == "csv":
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["position", "title", "artist", "genre", "bpm", "key", "energy",
                         "duration_seconds", "rating", "owned", "local_path", "url"])
        for i, t in enumerate(tracks, start=1):
            writer.writerow([i, t.title or "", t.artist or "", t.genre or "", t.bpm or "",
                             t.camelot_key or "", t.energy or "", t.duration_seconds or "",
                             t.rating or "", "1" if t.has_local_file else "0",
                             t.local_path or "", t.url or ""])
        return PlainTextResponse(buf.getvalue(), media_type="text/csv")

    if format == "markdown":
        md = [f"# {playlist.name}", "",
              "| # | Traccia | Genere | BPM | Key | Durata |",
              "|--:|---|---|--:|---|--:|"]
        for i, t in enumerate(tracks, start=1):
            label = f"{t.artist or '?'} — {t.title or '?'}"
            bpm = f"{t.bpm:.0f}" if t.bpm else "—"
            dur = f"{t.duration_seconds // 60}:{t.duration_seconds % 60:02d}" if t.duration_seconds else "—"
            md.append(f"| {i} | {label} | {t.genre or '—'} | {bpm} | {t.camelot_key or '—'} | {dur} |")
        return PlainTextResponse("\n".join(md), media_type="text/markdown")

    if format == "text":
        lines = [f"# {playlist.name}", ""]
        for i, t in enumerate(tracks, start=1):
            label = f"{t.artist or '?'} - {t.title or '?'}"
            meta = f" [{t.bpm:.0f} BPM, {t.camelot_key or '?'}]" if t.bpm else (f" [{t.camelot_key}]" if t.camelot_key else "")
            lines.append(f"{i:2d}. {label}{meta}")
        return PlainTextResponse("\n".join(lines))

    # m3u8 (default): comportamento invariato
    owned = [t for t in tracks if t.local_path]
    skipped = len(tracks) - len(owned)
    m3u = ["#EXTM3U"]
    if skipped:
        m3u.append(f"# {skipped} tracce senza file locale non incluse")
    for t in owned:
        secs = int(t.duration_seconds) if t.duration_seconds else -1
        m3u.append(f"#EXTINF:{secs},{t.artist or '?'} — {t.title or t.spotify_id or '?'}")
        m3u.append(t.local_path)
    return PlainTextResponse("\n".join(m3u), media_type="audio/x-mpegurl")
```

- [ ] **Step 4: Verifica PASS** — `pytest tests/test_playlist_export.py -q`

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/playlists.py backend/tests/test_playlist_export.py
git commit -m "feat(playlists): export playlist anche in CSV, testo e Markdown"
```

---

### Task 12: Menu export — frontend

**Files:**
- Modify: `frontend/lib/api/playlists.ts` (`exportPlaylist` con formato)
- Modify: `frontend/app/playlists/[id]/page.tsx` (menu al posto del bottone singolo)
- Modify: `frontend/lib/i18n/it.ts`, `frontend/lib/i18n/en.ts`

**Interfaces:**
- Consumes: Task 11.
- Produces: `exportPlaylist(id: number, format?: "m3u8" | "csv" | "text" | "markdown"): Promise<string>`.

- [ ] **Step 1: API client** — estendi la funzione esistente:

```typescript
export type PlaylistExportFormat = "m3u8" | "csv" | "text" | "markdown";

/** Export della playlist nel formato scelto (default M3U8 per Rekordbox). */
export async function exportPlaylist(id: number, format: PlaylistExportFormat = "m3u8"): Promise<string> {
  const res = await fetch(`${API}/api/playlists/${id}/export?format=${format}`, { method: "POST" });
  if (!res.ok) throw new Error(res.statusText);
  return res.text();
}
```

- [ ] **Step 2: i18n** — `it.ts`: `exportButton: "Esporta",`, `exportM3u8Option: "M3U8 (Rekordbox)",`, `exportCsvOption: "CSV",`, `exportTextOption: "Testo",`, `exportMarkdownOption: "Markdown",`; `en.ts` equivalenti. (La chiave `exportRekordboxButton` resta finché usata altrove; se non più referenziata, rimuovila da entrambi i file.)

- [ ] **Step 3: Menu in sidebar** — sostituisci il bottone export con un piccolo popover (stesso pattern ref/mousedown di `AddToPlaylistMenu`): bottone `t.playlists.exportButton` che apre 4 voci; ogni voce chiama `doExport(format)` generalizzato:

```tsx
const EXPORT_EXT: Record<PlaylistExportFormat, string> = { m3u8: "m3u8", csv: "csv", text: "txt", markdown: "md" };
const EXPORT_MIME: Record<PlaylistExportFormat, string> = {
  m3u8: "audio/x-mpegurl", csv: "text/csv", text: "text/plain", markdown: "text/markdown",
};

const doExport = async (format: PlaylistExportFormat) => {
  if (!playlist) return;
  setActionError(null);
  setExporting(true);
  try {
    const body = await exportPlaylist(pid, format);
    const url = URL.createObjectURL(new Blob([body], { type: EXPORT_MIME[format] }));
    const a = document.createElement("a");
    a.href = url;
    a.download = `${slugName(playlist.name)}.${EXPORT_EXT[format]}`;
    a.click();
    URL.revokeObjectURL(url);
  } catch (e) {
    setActionError(t.playlists.exportFailed(errText(e)));
  } finally {
    setExporting(false);
  }
};
```

- [ ] **Step 4: Verifica** — `npm run lint`; visiva: scarica un CSV e un M3U8.

- [ ] **Step 5: Commit**

```bash
git add frontend/lib/api/playlists.ts frontend/app/playlists/\[id\]/page.tsx frontend/lib/i18n/it.ts frontend/lib/i18n/en.ts
git commit -m "feat(playlists): menu export multi-formato nel dettaglio"
```

---

### Task 13: Verifica finale + documentazione

**Files:**
- Modify: `docs/API.md` (sezione playlists: PATCH, PUT /order, /tracks/remove, /duplicate, /sync-log, export formats, name_locked, playlist_position)
- Modify: `PROGRESS.md` (voce datata 2026-08-07)
- Modify: `docs/ROADMAP.md` (se elenca le mancanze playlist, aggiornare)

- [ ] **Step 1: Suite completa backend** — `pytest tests -q` → tutto verde.
- [ ] **Step 2: Frontend** — `npm run lint` e `npm run build` → 0 errori (node_modules del worktree è reale, il build Turbopack funziona).
- [ ] **Step 3: Smoke test visivo** — dev server: rename, drag-and-drop, selezione bulk, duplica, storico sync, export CSV.
- [ ] **Step 4: Docs** — aggiorna `docs/API.md` con i nuovi endpoint/campi (stile delle voci esistenti); aggiungi a `PROGRESS.md` una voce sintetica; controlla `docs/ROADMAP.md`.
- [ ] **Step 5: Commit**

```bash
git add docs/API.md PROGRESS.md docs/ROADMAP.md
git commit -m "docs: gestione playlist completata (rename, riordino DnD, bulk, fork, sync-log, export)"
```

## Note di self-review

- Il fix "confirm esplicito su rimozione traccia orfana" della richiesta originale è risultato già implementato (`removeTrackConfirm` in i18n lo dice già): coperto in Task 6 solo per il confirm bulk.
- `playlist_position` (fix minore) è dentro Task 3.
- `apiPatch`/`apiPut` in `client.ts`: verificarne l'esistenza al primo uso (Task 2/4) e crearli sul modello di `apiPost` se assenti.
- La forma di `_item` nel test del sync-log (Task 9) va verificata contro `normalize_spotify_item` reale prima di scrivere il test.
