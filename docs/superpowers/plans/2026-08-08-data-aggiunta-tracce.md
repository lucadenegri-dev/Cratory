# Data di aggiunta tracce in Library e Playlist — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Mostrare la data di aggiunta delle tracce come colonna ordinabile in Library (data primo import) e nel dettaglio playlist (data di ingresso in quella playlist).

**Architecture:** Nessuna migrazione DB — `Track.added_at` e `playlist_tracks.added_at` esistono già. Backend: nuova opzione di sort `added_at` su `GET /tracks`, nuovo campo `playlist_added_at` su `TrackOut` valorizzato solo da `GET /playlists/{id}/tracks` (stesso pattern di `playlist_position`), default `utcnow()` in `add_track_to_playlist`. Frontend: colonna "Aggiunta" nelle due tabelle con `fmtDate` esistente.

**Tech Stack:** FastAPI + SQLAlchemy + Pydantic (backend), Next.js 16 + React + Tailwind (frontend), pytest.

**Spec:** `docs/superpowers/specs/2026-08-08-data-aggiunta-tracce-design.md`

## Global Constraints

- Nessuna migrazione DB.
- Valori mancanti mostrati come `—` (già il comportamento di `fmtDate`).
- Formato data corto it-IT via `fmtDate` esistente (`12 lug 2026`).
- Le tabelle tracce non devono introdurre scroll orizzontale (colonna nowrap, verifica visiva finale).
- Frontend: leggere `frontend/CLAUDE.md` prima di toccare le pagine (Next 16).
- Commit frequenti, messaggio in italiano stile repo, **niente Co-Authored-By**.

---

### Task 1: Backend — sort `added_at` su GET /tracks

**Files:**
- Modify: `backend/app/routers/tracks.py:56-59` (pattern del parametro `sort`)
- Modify: `backend/app/repositories.py:19-31` (`_SORT_COLUMNS`)
- Test: `backend/tests/test_tracks_sort_added_at.py` (nuovo)

**Interfaces:**
- Produces: `GET /api/tracks?sort=added_at&order=asc|desc` — ordina per `Track.added_at`, NULL in fondo, tie-break su `Track.id` (già garantito dal meccanismo esistente in `list_tracks`).

- [ ] **Step 1: Write the failing test**

```python
"""Sort per data di aggiunta in libreria: GET /tracks?sort=added_at."""
from datetime import datetime

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import pytest

import app.models  # noqa: F401
from app.db import Base, get_db
from app.main import app
from app.models import Track


@pytest.fixture()
def client_db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    app.dependency_overrides[get_db] = lambda: session
    try:
        yield TestClient(app), session
    finally:
        app.dependency_overrides.pop(get_db, None)
        session.close()


def _tr(db, title, added_at):
    t = Track(source_type="manual", title=title, artist="A", added_at=added_at)
    db.add(t)
    db.flush()
    return t


def test_sort_added_at_asc_null_in_fondo(client_db):
    client, db = client_db
    _tr(db, "vecchia", datetime(2026, 1, 1))
    _tr(db, "nuova", datetime(2026, 8, 1))
    _tr(db, "senza-data", None)
    db.commit()

    r = client.get("/api/tracks", params={"sort": "added_at", "order": "asc"})
    assert r.status_code == 200
    titles = [t["title"] for t in r.json()["items"]]
    assert titles == ["vecchia", "nuova", "senza-data"]


def test_sort_added_at_desc_null_in_fondo(client_db):
    client, db = client_db
    _tr(db, "vecchia", datetime(2026, 1, 1))
    _tr(db, "nuova", datetime(2026, 8, 1))
    _tr(db, "senza-data", None)
    db.commit()

    r = client.get("/api/tracks", params={"sort": "added_at", "order": "desc"})
    assert r.status_code == 200
    titles = [t["title"] for t in r.json()["items"]]
    assert titles == ["nuova", "vecchia", "senza-data"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_tracks_sort_added_at.py -v`
Expected: FAIL — 422 (pattern del parametro `sort` non ammette `added_at`).

- [ ] **Step 3: Implement**

In `backend/app/repositories.py`, dentro `_SORT_COLUMNS`, aggiungere la riga:

```python
    "rating": Track.rating,
    "added_at": Track.added_at,
}
```

In `backend/app/routers/tracks.py`, aggiornare il pattern:

```python
    sort: str | None = Query(
        default=None,
        pattern="^(title|artist|source|bpm|key|energy|genre|duration|year|status|rating|added_at)$",
    ),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_tracks_sort_added_at.py -v`
Expected: PASS (2 test).

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/tracks.py backend/app/repositories.py backend/tests/test_tracks_sort_added_at.py
git commit -m "feat(tracks): sort per data di aggiunta (added_at) su GET /tracks"
```

---

### Task 2: Backend — `playlist_added_at` su GET /playlists/{id}/tracks

**Files:**
- Modify: `backend/app/schemas.py:37-39` (campo su `TrackOut`, accanto a `playlist_position`)
- Modify: `backend/app/routers/playlists.py:448-457` (endpoint `playlist_tracks`)
- Test: `backend/tests/test_playlist_added_at.py` (nuovo)

**Interfaces:**
- Produces: `TrackOut.playlist_added_at: datetime | None` — valorizzato SOLO da `GET /api/playlists/{id}/tracks` con `playlist_tracks.added_at` della membership; `None` altrove (es. `GET /tracks`). Il frontend lo legge come `playlist_added_at: string | null`.

- [ ] **Step 1: Write the failing test**

```python
"""GET /playlists/{id}/tracks espone la data di aggiunta per-playlist."""
from datetime import datetime

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import pytest

import app.models  # noqa: F401
from app.db import Base, get_db
from app.main import app
from app.models import Playlist, Track
from app.repositories import add_track_to_playlist


@pytest.fixture()
def client_db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    app.dependency_overrides[get_db] = lambda: session
    try:
        yield TestClient(app), session
    finally:
        app.dependency_overrides.pop(get_db, None)
        session.close()


def test_playlist_added_at_valorizzato(client_db):
    client, db = client_db
    pl = Playlist(platform="manual", name="P", kind="manual")
    a = Track(source_type="manual", title="a", artist="A")
    b = Track(source_type="manual", title="b", artist="A")
    db.add_all([pl, a, b])
    db.flush()
    add_track_to_playlist(db, a, pl, added_at=datetime(2026, 3, 15, 12, 0, 0))
    add_track_to_playlist(db, b, pl)  # senza data esplicita
    db.commit()

    r = client.get(f"/api/playlists/{pl.id}/tracks")
    assert r.status_code == 200
    rows = {t["title"]: t for t in r.json()}
    assert rows["a"]["playlist_added_at"].startswith("2026-03-15T12:00:00")


def test_playlist_added_at_assente_su_get_tracks(client_db):
    client, db = client_db
    t = Track(source_type="manual", title="solo", artist="A")
    db.add(t)
    db.commit()

    r = client.get("/api/tracks")
    assert r.status_code == 200
    assert r.json()["items"][0]["playlist_added_at"] is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_playlist_added_at.py -v`
Expected: FAIL — `KeyError: 'playlist_added_at'` (campo inesistente).

- [ ] **Step 3: Implement**

In `backend/app/schemas.py`, sotto `playlist_position`:

```python
    # Posizione 1-based nella playlist: valorizzata SOLO da GET /api/playlists/{id}/tracks.
    playlist_position: int | None = None
    # Data di aggiunta ALLA playlist (playlist_tracks.added_at): valorizzata SOLO
    # da GET /api/playlists/{id}/tracks. `added_at` resta il primo import in libreria.
    playlist_added_at: datetime | None = None
```

In `backend/app/routers/playlists.py`, endpoint `playlist_tracks` (riusa l'import esistente di `playlist_tracks` la tabella — verificare il nome importato in testa al file; se il modulo importa la tabella come `playlist_tracks` c'è collisione col nome della funzione endpoint: in tal caso importare la tabella con alias, es. `from ..models import playlist_tracks as playlist_tracks_table`):

```python
@router.get("/{playlist_id}/tracks", response_model=list[TrackOut])
def playlist_tracks(playlist_id: int, db: Session = Depends(get_db)):
    if get_playlist(db, playlist_id) is None:
        raise api_error(404, "playlist_not_found", "Playlist not found")
    added_map = dict(db.execute(
        select(playlist_tracks_table.c.track_id, playlist_tracks_table.c.added_at)
        .where(playlist_tracks_table.c.playlist_id == playlist_id)
    ).all())
    out = []
    for i, t in enumerate(tracks_for_playlist(db, playlist_id), start=1):
        row = track_out(t)
        row.playlist_position = i
        row.playlist_added_at = added_map.get(t.id)
        out.append(row)
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_playlist_added_at.py -v`
Expected: PASS (2 test).

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas.py backend/app/routers/playlists.py backend/tests/test_playlist_added_at.py
git commit -m "feat(playlists): esponi playlist_added_at nel dettaglio tracce playlist"
```

---

### Task 3: Backend — default `added_at = adesso` per aggiunte manuali

**Files:**
- Modify: `backend/app/repositories.py:340-364` (`add_track_to_playlist`)
- Test: `backend/tests/test_playlist_added_at.py` (aggiunta test)

**Interfaces:**
- Consumes: `add_track_to_playlist(db, track, playlist, *, added_at=None, added_by=None)` — firma invariata.
- Produces: se `added_at` non è passato, la membership viene creata con `added_at = utcnow()` (import `utcnow` da `app.models`). I chiamanti che passano la data (import Spotify) restano invariati.

- [ ] **Step 1: Write the failing test**

Aggiungere in coda a `backend/tests/test_playlist_added_at.py`:

```python
def test_add_senza_added_at_valorizza_adesso(client_db):
    client, db = client_db
    pl = Playlist(platform="manual", name="P2", kind="manual")
    t = Track(source_type="manual", title="x", artist="A")
    db.add_all([pl, t])
    db.flush()
    add_track_to_playlist(db, t, pl)
    db.commit()

    r = client.get(f"/api/playlists/{pl.id}/tracks")
    assert r.status_code == 200
    assert r.json()[0]["playlist_added_at"] is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_playlist_added_at.py -v`
Expected: FAIL sul nuovo test (`playlist_added_at` è `None`).

- [ ] **Step 3: Implement**

In `backend/app/repositories.py`: aggiungere `utcnow` all'import da `.models` (riga import esistente in testa al file), poi nell'insert di `add_track_to_playlist`:

```python
    db.execute(playlist_tracks.insert().values(
        playlist_id=playlist.id, track_id=track.id,
        added_at=added_at or utcnow(), added_by=added_by,
        position=(max_pos or 0) + 1,
    ))
```

Aggiornare la docstring della funzione: `added_at=None` → la membership viene datata adesso.

- [ ] **Step 4: Run tests to verify they pass (incluso il resto della suite playlist)**

Run: `python -m pytest tests/test_playlist_added_at.py tests/test_playlist_position.py tests/test_playlist_membership.py tests/test_playlist_add_tracks.py -v`
Expected: PASS. Se un test esistente asseriva `added_at IS NULL` per aggiunte manuali, aggiornarlo alla nuova semantica.

- [ ] **Step 5: Commit**

```bash
git add backend/app/repositories.py backend/tests/test_playlist_added_at.py
git commit -m "feat(playlists): default added_at=adesso per membership senza data"
```

---

### Task 4: Frontend — colonna "Aggiunta" in Library

**Files:**
- Modify: `frontend/lib/api/types.ts:21` (accanto ad `added_at` aggiungere `playlist_added_at`)
- Modify: `frontend/lib/i18n/en.ts` e `frontend/lib/i18n/it.ts` (chiave `colAdded` nel blocco `library`)
- Modify: `frontend/app/library/page.tsx` (colonna th + td)

**Interfaces:**
- Consumes: `Track.added_at: string | null` (già presente), `fmtDate` da `@/lib/api` (già esportato).
- Produces: chiave i18n `t.library.colAdded` ("Added" / "Aggiunta") usata anche dal Task 5; `Track.playlist_added_at: string | null` in `types.ts` usato dal Task 5.

- [ ] **Step 1: Leggere `frontend/CLAUDE.md`** (regola repo per Next 16) prima delle modifiche.

- [ ] **Step 2: Implement**

`frontend/lib/api/types.ts` — sotto `added_at`:

```ts
  added_at: string | null;
  /** Data di aggiunta ALLA playlist: presente solo da GET /playlists/{id}/tracks. */
  playlist_added_at: string | null;
```

`frontend/lib/i18n/en.ts` — nel blocco `library`, accanto a `colStatus`:

```ts
    colAdded: "Added",
```

`frontend/lib/i18n/it.ts` — stessa posizione (verificare la struttura del file: se `it.ts` è un partial/override, aggiungere la chiave dove stanno le altre `col*`):

```ts
    colAdded: "Aggiunta",
```

`frontend/app/library/page.tsx` — nell'`<thead>`, tra `Dur` e `Status` (per lasciare rating/azioni sul bordo destro):

```tsx
              {th(t.library.colDuration, "duration", true)}
              {th(t.library.colAdded, "added_at")}
              <th className={cell}>{t.library.colStatus}</th>
```

Nel `<tbody>`, dopo la cella `fmtDuration`:

```tsx
                <td className={`${cell} tnum text-muted`}>{fmtDuration(tr.duration_seconds)}</td>
                <td className={`${cell} whitespace-nowrap text-xs text-muted`}>{fmtDate(tr.added_at)}</td>
                <td className={cell}><TrackStateIcons track={tr} /></td>
```

Aggiungere `fmtDate` all'import da `@/lib/api` in testa al file se non già presente.

- [ ] **Step 3: Lint**

Run: `cd frontend && npm run lint`
Expected: pulito.

- [ ] **Step 4: Commit**

```bash
git add frontend/lib/api/types.ts frontend/lib/i18n/en.ts frontend/lib/i18n/it.ts frontend/app/library/page.tsx
git commit -m "feat(ui): colonna data di aggiunta ordinabile in libreria"
```

---

### Task 5: Frontend — colonna "Aggiunta" nel dettaglio playlist

**Files:**
- Modify: `frontend/app/playlists/[id]/page.tsx` (getter sort client-side, th, td, colSpan)

**Interfaces:**
- Consumes: `Track.playlist_added_at` (Task 4), `t.library.colAdded` (Task 4), `fmtDate` da `@/lib/api`.

- [ ] **Step 1: Implement**

Nel memo `visible`, aggiungere il getter (ISO string ordina lessicograficamente; null in fondo in entrambi i versi):

```ts
      genre: (tr) => str(tr.genre), duration: (tr) => num(tr.duration_seconds), status: (tr) => tr.status,
      added: (tr) => tr.playlist_added_at ?? (order === "asc" ? "￿" : ""),
```

Nell'`<thead>`, tra `Dur` e `Status`:

```tsx
              {th(t.library.colDuration, "duration", true)}
              {th(t.library.colAdded, "added")}
              <th className={cell}>{t.library.colStatus}</th>
```

Nel `<tbody>`, dopo la cella `fmtDuration` (riga ~732):

```tsx
                <td className={`${cell} tnum text-muted`}>{fmtDuration(tr.duration_seconds)}</td>
                <td className={`${cell} whitespace-nowrap text-xs text-muted`}>{fmtDate(tr.playlist_added_at)}</td>
                <td className={cell}><TrackStateIcons track={tr} /></td>
```

Aggiornare il `colSpan={9}` della riga vuota (riga ~749) a `colSpan={10}`. Aggiungere `fmtDate` all'import da `@/lib/api` se manca.

- [ ] **Step 2: Lint + build**

Run: `cd frontend && npm run lint && npm run build`
Expected: puliti entrambi.

- [ ] **Step 3: Commit**

```bash
git add "frontend/app/playlists/[id]/page.tsx"
git commit -m "feat(ui): colonna data di aggiunta alla playlist nel dettaglio"
```

---

### Task 6: Verifica finale

**Files:** nessuno (solo verifica).

- [ ] **Step 1: Suite backend completa**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests`
Expected: tutto verde.

- [ ] **Step 2: Verifica visiva nel browser**

Avviare i dev server via preview (launch.json), aprire `/library` (vista lista) e un dettaglio playlist:
- colonna "Aggiunta" visibile con date `12 lug 2026` o `—`;
- click sull'header in Library ordina asc/desc (query `sort=added_at` in rete);
- click sull'header in playlist ordina client-side;
- **nessuno scroll orizzontale** in entrambe le tabelle a larghezza desktop; screenshot come prova.

- [ ] **Step 3: Aggiornare docs**

`docs/API.md`: aggiungere `added_at` ai valori di `sort` di `GET /tracks` e documentare `playlist_added_at` su `GET /playlists/{id}/tracks`. `PROGRESS.md`: riga diario. Commit:

```bash
git add docs/API.md PROGRESS.md
git commit -m "docs: data di aggiunta tracce (sort added_at, playlist_added_at)"
```
