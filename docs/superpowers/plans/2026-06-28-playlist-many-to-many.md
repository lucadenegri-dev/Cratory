# Playlist many-to-many (membership) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Permettere a un brano di appartenere a più playlist tramite una tabella associativa `playlist_tracks`, convertendo import/prune/delete/enrichment-scoping/endpoint alla membership e mostrando "in N playlist" in UI.

**Architecture:** Tabella associativa `playlist_tracks(playlist_id, track_id, added_at)` con relationship SQLAlchemy; migrazione additiva idempotente in `ensure_schema` che fa backfill dai `Track.playlist_id` esistenti e poi svuota le colonne legacy. Tutte le letture/scritture passano da helper di repository sulla membership. `TrackOut` espone `playlists[]`.

**Tech Stack:** Python 3 + FastAPI + Pydantic + SQLAlchemy (backend), pytest; Next.js 16 + React + TypeScript (frontend).

## Global Constraints

- Niente Alembic: migrazione additiva idempotente in `ensure_schema` (SQLite, app locale).
- Deterministico; nessuna AI.
- Non perdere dati: il backfill copia le appartenenze prima di azzerare le colonne legacy.
- Colonne legacy `Track.playlist_id` / `Track.playlist_name`: lasciate fisicamente in tabella, **svuotate** dopo backfill, non più lette/scritte dall'app.
- `added_at` diventa per-playlist (sulla membership).
- Schema Pydantic nuovo: `TrackPlaylistRef{id,name}` (per non confondersi con `SpotifyPlaylistRef`).
- Stile commit: nessun trailer `Co-Authored-By`.
- Comandi backend da `backend/` con venv attivo: `source .venv/bin/activate`.

---

## File Structure

- `backend/app/models.py` — tabella `playlist_tracks` + relationships `Track.playlists`/`Playlist.tracks`.
- `backend/app/db.py` — `_migrate_playlist_memberships` in `ensure_schema`.
- `backend/app/repositories.py` — helper membership; `tracks_for_playlist`/`delete_playlist` su membership.
- `backend/app/services/playlist_import.py` — `_apply`/prune su membership.
- `backend/app/services/manual_import.py` — import manuale su membership.
- `backend/app/services/feature_enrichment.py` — scoping playlist via membership.
- `backend/app/routers/playlists.py` — `add_discovered_track` su membership.
- `backend/app/schemas.py` — `TrackPlaylistRef`, `TrackOut.playlists`.
- `backend/app/serializers.py` — `track_out` espone `playlists`.
- `backend/tests/test_playlist_membership.py` — nuovi test (migrazione + repo).
- Test esistenti aggiornati: `test_playlist_sync.py`, `test_manual_import.py`, `test_playlist_pivot.py`, `test_set_builder_phase_c.py`, `test_enrichment_resilience.py`, `test_discovery.py`, `test_playlist_add_track.py`.
- `frontend/lib/api.ts`, `frontend/app/library/page.tsx`, `frontend/app/tracks/[id]/page.tsx`.

---

## Task 1: Modello associativo + migrazione backfill

**Files:**
- Modify: `backend/app/models.py`
- Modify: `backend/app/db.py`
- Test: `backend/tests/test_playlist_membership.py` (nuovo)

**Interfaces:**
- Produces:
  - tabella core `playlist_tracks` (colonne `playlist_id`, `track_id`, `added_at`) esportata da `app.models`
  - `Track.playlists: list[Playlist]`, `Playlist.tracks: list[Track]`
  - migrazione idempotente eseguita da `ensure_schema(engine)`

- [ ] **Step 1: Scrivi il test di migrazione (fallisce all'import della tabella)**

Crea `backend/tests/test_playlist_membership.py`:

```python
"""Test playlist many-to-many: migrazione backfill + helper membership."""

from sqlalchemy import create_engine, text

from app.db import Base, ensure_schema


def _legacy_engine():
    """Engine in-memory con una traccia legacy (Track.playlist_id valorizzato)."""
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(eng)
    with eng.begin() as c:
        c.execute(text(
            "INSERT INTO playlists (id, platform, name, track_count, kind) "
            "VALUES (1, 'spotify', 'P', 0, 'playlist')"
        ))
        c.execute(text(
            "INSERT INTO tracks (id, source_type, playlist_id, playlist_name, title, artist) "
            "VALUES (1, 'spotify', 1, 'P', 'T', 'A')"
        ))
    return eng


def test_backfill_creates_membership_and_clears_legacy():
    eng = _legacy_engine()
    ensure_schema(eng)
    with eng.connect() as c:
        rows = c.execute(text("SELECT playlist_id, track_id FROM playlist_tracks")).fetchall()
        assert rows == [(1, 1)]
        leftover = c.execute(text("SELECT playlist_id, playlist_name FROM tracks WHERE id=1")).fetchone()
        assert leftover == (None, None)


def test_backfill_is_idempotent():
    eng = _legacy_engine()
    ensure_schema(eng)
    ensure_schema(eng)  # seconda passata: nessun duplicato
    with eng.connect() as c:
        n = c.execute(text("SELECT COUNT(*) FROM playlist_tracks")).scalar()
        assert n == 1
```

- [ ] **Step 2: Esegui il test (fallisce)**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_playlist_membership.py -v`
Expected: FAIL — `no such table: playlist_tracks`.

- [ ] **Step 3: Aggiungi la tabella associativa e le relationship**

In `backend/app/models.py`:

(a) aggiorna l'import sqlalchemy per includere `Column` e `Table`:

```python
from sqlalchemy import JSON, Column, Date, DateTime, Float, ForeignKey, Integer, String, Table, Text
```

(b) dopo `def utcnow()` e prima di `class Track`, definisci la tabella:

```python
# Associazione M2M brano<->playlist. `added_at` e' per-playlist (quando il brano e'
# stato aggiunto a QUELLA playlist). PK composta: una membership per coppia.
playlist_tracks = Table(
    "playlist_tracks",
    Base.metadata,
    Column("playlist_id", ForeignKey("playlists.id"), primary_key=True, index=True),
    Column("track_id", ForeignKey("tracks.id"), primary_key=True, index=True),
    Column("added_at", DateTime, nullable=True),
)
```

(c) in `class Track`, aggiungi la relationship (dopo gli altri campi, prima della fine classe):

```python
    playlists: Mapped[list["Playlist"]] = relationship(
        secondary="playlist_tracks", back_populates="tracks", viewonly=False,
    )
```

(d) in `class Playlist`, aggiungi:

```python
    tracks: Mapped[list["Track"]] = relationship(
        secondary="playlist_tracks", back_populates="playlists", viewonly=False,
    )
```

- [ ] **Step 4: Aggiungi la migrazione backfill in `ensure_schema`**

In `backend/app/db.py`, dentro `ensure_schema`, nel blocco `with eng.begin() as conn:` aggiungi la chiamata dopo `_migrate_drop_legacy(conn)`:

```python
        _migrate_drop_legacy(conn)
        _migrate_playlist_memberships(conn)
```

Poi definisci la funzione (dopo `_migrate_drop_legacy`):

```python
def _migrate_playlist_memberships(conn) -> None:
    """Backfill M2M: copia Track.playlist_id nelle membership, poi svuota le colonne legacy.

    Idempotente: INSERT OR IGNORE non duplica; dopo lo svuotamento non ci sono piu'
    righe con playlist_id valorizzato, quindi le esecuzioni successive sono no-op.
    """
    if not _table_exists(conn, "playlist_tracks"):
        return
    cols = [r[1] for r in conn.execute(text("PRAGMA table_info(tracks)")).fetchall()]
    if "playlist_id" not in cols:
        return
    conn.execute(text(
        "INSERT OR IGNORE INTO playlist_tracks (playlist_id, track_id, added_at) "
        "SELECT playlist_id, id, added_at FROM tracks WHERE playlist_id IS NOT NULL"
    ))
    conn.execute(text(
        "UPDATE tracks SET playlist_id = NULL, playlist_name = NULL WHERE playlist_id IS NOT NULL"
    ))
```

- [ ] **Step 5: Esegui i test (passano)**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_playlist_membership.py -v`
Expected: PASS (2 test).

- [ ] **Step 6: Esegui l'intera suite (nessuna regressione: le letture usano ancora playlist_id)**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests -q`
Expected: PASS (le letture/scritture app non sono ancora cambiate).

- [ ] **Step 7: Commit**

```bash
git add backend/app/models.py backend/app/db.py backend/tests/test_playlist_membership.py
git commit -m "feat(model): tabella associativa playlist_tracks + migrazione backfill"
```

---

## Task 2: Switch backend alla membership (read + write)

**Files:**
- Modify: `backend/app/repositories.py`
- Modify: `backend/app/services/playlist_import.py`
- Modify: `backend/app/services/manual_import.py`
- Modify: `backend/app/services/feature_enrichment.py`
- Modify: `backend/app/routers/playlists.py`
- Test: `backend/tests/test_playlist_membership.py` (+ aggiornamento test esistenti)

**Interfaces:**
- Consumes: tabella `playlist_tracks` (Task 1).
- Produces (in `app.repositories`):
  - `add_track_to_playlist(db, track, playlist, *, added_at=None) -> None` (idempotente, non committa)
  - `remove_track_from_playlist(db, playlist_id, track_id) -> None`
  - `recount_playlist(db, playlist) -> None`
  - `tracks_for_playlist(db, playlist_id) -> list[Track]` (via membership, ordine `added_at`)
  - `delete_playlist(db, playlist_id) -> bool` (cancella membership + playlist)

- [ ] **Step 1: Scrivi i nuovi test di repository (falliscono)**

Aggiungi a `backend/tests/test_playlist_membership.py`:

```python
import pytest

from app.models import Playlist, Track
from app.repositories import (
    add_track_to_playlist,
    delete_playlist,
    recount_playlist,
    remove_track_from_playlist,
    tracks_for_playlist,
)


def _pl(db, name):
    pl = Playlist(platform="spotify", name=name, kind="playlist")
    db.add(pl); db.flush()
    return pl


def _tr(db, title):
    t = Track(source_type="spotify", title=title, artist="A")
    db.add(t); db.flush()
    return t


def test_add_membership_is_idempotent(db):
    pl, t = _pl(db, "P"), _tr(db, "T")
    add_track_to_playlist(db, t, pl)
    add_track_to_playlist(db, t, pl)  # secondo add: no-op
    db.commit()
    assert [x.title for x in tracks_for_playlist(db, pl.id)] == ["T"]


def test_track_in_two_playlists(db):
    a, b, t = _pl(db, "A"), _pl(db, "B"), _tr(db, "T")
    add_track_to_playlist(db, t, a)
    add_track_to_playlist(db, t, b)
    db.commit()
    assert {p.name for p in t.playlists} == {"A", "B"}
    assert t in tracks_for_playlist(db, a.id)
    assert t in tracks_for_playlist(db, b.id)


def test_remove_membership_keeps_track(db):
    a, b, t = _pl(db, "A"), _pl(db, "B"), _tr(db, "T")
    add_track_to_playlist(db, t, a)
    add_track_to_playlist(db, t, b)
    db.commit()
    remove_track_from_playlist(db, a.id, t.id)
    db.commit()
    assert t not in tracks_for_playlist(db, a.id)
    assert t in tracks_for_playlist(db, b.id)
    assert db.query(Track).count() == 1


def test_delete_playlist_keeps_shared_track(db):
    a, b, t = _pl(db, "A"), _pl(db, "B"), _tr(db, "T")
    add_track_to_playlist(db, t, a)
    add_track_to_playlist(db, t, b)
    db.commit()
    assert delete_playlist(db, a.id) is True
    assert db.query(Track).count() == 1          # brano resta in libreria
    assert t in tracks_for_playlist(db, b.id)     # e nell'altra playlist


def test_recount_playlist(db):
    pl, t1, t2 = _pl(db, "P"), _tr(db, "T1"), _tr(db, "T2")
    add_track_to_playlist(db, t1, pl)
    add_track_to_playlist(db, t2, pl)
    db.commit()
    recount_playlist(db, pl)
    assert pl.track_count == 2
```

- [ ] **Step 2: Esegui i nuovi test (falliscono)**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_playlist_membership.py -k "membership or two_playlists or delete_playlist_keeps or recount" -v`
Expected: FAIL — `cannot import name 'add_track_to_playlist'`.

- [ ] **Step 3: Implementa gli helper e converti le letture in `repositories.py`**

In `backend/app/repositories.py`:

(a) aggiorna l'import dei modelli:

```python
from app.models import DjSet, DjSetTrack, Playlist, Setlist, SetlistTrack, Track, playlist_tracks
```

(b) sostituisci `tracks_for_playlist` e `delete_playlist` e aggiungi gli helper:

```python
def add_track_to_playlist(db: Session, track: Track, playlist: Playlist, *, added_at=None) -> None:
    """Crea la membership brano<->playlist se non esiste (idempotente). Non committa."""
    exists = db.execute(
        select(playlist_tracks.c.track_id).where(
            playlist_tracks.c.playlist_id == playlist.id,
            playlist_tracks.c.track_id == track.id,
        )
    ).first()
    if exists:
        return
    db.execute(playlist_tracks.insert().values(
        playlist_id=playlist.id, track_id=track.id, added_at=added_at,
    ))


def remove_track_from_playlist(db: Session, playlist_id: int, track_id: int) -> None:
    db.execute(playlist_tracks.delete().where(
        playlist_tracks.c.playlist_id == playlist_id,
        playlist_tracks.c.track_id == track_id,
    ))


def recount_playlist(db: Session, playlist: Playlist) -> None:
    n = db.scalar(
        select(func.count()).select_from(playlist_tracks)
        .where(playlist_tracks.c.playlist_id == playlist.id)
    )
    playlist.track_count = n or 0


def tracks_for_playlist(db: Session, playlist_id: int) -> list[Track]:
    return list(db.scalars(
        select(Track)
        .join(playlist_tracks, playlist_tracks.c.track_id == Track.id)
        .where(playlist_tracks.c.playlist_id == playlist_id)
        .order_by(playlist_tracks.c.added_at.is_(None), playlist_tracks.c.added_at)
    ).all())


def delete_playlist(db: Session, playlist_id: int) -> bool:
    """Rimuove una playlist: cancella le sue membership; le tracce restano in libreria
    (e nelle altre playlist). Ritorna False se la playlist non esiste."""
    playlist = get_playlist(db, playlist_id)
    if playlist is None:
        return False
    db.execute(playlist_tracks.delete().where(playlist_tracks.c.playlist_id == playlist_id))
    db.delete(playlist)
    db.commit()
    return True
```

- [ ] **Step 4: Converti l'import Spotify (`playlist_import.py`) alla membership**

In `backend/app/services/playlist_import.py`:

(a) import degli helper in cima (dopo gli import esistenti):

```python
from app.repositories import add_track_to_playlist, recount_playlist, remove_track_from_playlist, tracks_for_playlist
```

(b) sostituisci `_apply` per ricevere `db` e creare la membership invece di settare i campi legacy:

```python
def _apply(db: Session, track: Track, norm: NormalizedTrack, playlist: Playlist) -> None:
    _apply_fields(track, norm)
    refresh_status(track)
    db.flush()  # garantisce track.id per la membership
    add_track_to_playlist(db, track, playlist, added_at=norm.added_at)
```

(c) aggiorna le due chiamate nel loop di `import_playlist`:

```python
        existing = _find_existing(db, norm)
        if existing is None:
            track = Track(source_type=platform)
            db.add(track)
            _apply(db, track, norm, playlist)
            created += 1
        else:
            _apply(db, existing, norm, playlist)
            updated += 1
```

(d) sostituisci il blocco prune e il `track_count`:

```python
    removed = 0
    if prune:
        for track in tracks_for_playlist(db, playlist.id):
            still_present = (
                (track.isrc is not None and track.isrc in present_isrcs)
                or (track.platform_track_id is not None
                    and track.platform_track_id in present_platform_ids)
            )
            if not still_present:
                remove_track_from_playlist(db, playlist.id, track.id)
                removed += 1

    recount_playlist(db, playlist)
    db.commit()
```

(Rimuovi la vecchia riga `playlist.track_count = created + updated` e il vecchio loop prune basato su `Track.playlist_id`.)

- [ ] **Step 5: Converti l'import manuale (`manual_import.py`)**

In `backend/app/services/manual_import.py`:

(a) import helper:

```python
from app.repositories import add_track_to_playlist, recount_playlist
```

(b) sostituisci il corpo del loop e il `track_count`:

```python
        existing = _find_by_name(db, artist, title)
        if existing is not None:
            refresh_status(existing)
            db.flush()
            add_track_to_playlist(db, existing, playlist)
            updated += 1
        else:
            track = Track(source_type="manual", platform="manual", artist=artist, title=title)
            db.add(track)
            refresh_status(track)
            db.flush()
            add_track_to_playlist(db, track, playlist)
            created += 1

    recount_playlist(db, playlist)
    db.commit()
```

(Rimuovi `existing.playlist_id/playlist_name = ...`, i kwarg `playlist_id=`/`playlist_name=` nel costruttore `Track`, e `playlist.track_count = created + updated`.)

- [ ] **Step 6: Converti lo scoping enrichment (`feature_enrichment.py`)**

In `backend/app/services/feature_enrichment.py`, sostituisci il ramo `elif playlist_id is not None:`:

```python
    elif playlist_id is not None:
        from app.models import playlist_tracks
        stmt = stmt.where(Track.id.in_(
            select(playlist_tracks.c.track_id).where(playlist_tracks.c.playlist_id == playlist_id)
        ))
```

(`select` è già importato nel file; verificare l'import in cima e aggiungerlo se assente.)

- [ ] **Step 7: Converti l'endpoint `add_discovered_track` (`routers/playlists.py`)**

In `backend/app/routers/playlists.py`:

(a) aggiungi gli helper all'import da `app.repositories`:

```python
from app.repositories import (
    add_track_to_playlist,
    all_playable_tracks,
    delete_playlist,
    get_playlist,
    list_playlists,
    recount_playlist,
    tracks_for_playlist,
)
```

(b) sostituisci il blocco di attach + l'edge-case 1:1 in `add_discovered_track`:

```python
    platform = "spotify" if req.spotify_id else "manual"
    track, created = import_single_track(
        db, platform=platform, platform_track_id=req.spotify_id,
        title=req.title, artist=req.artist, isrc=req.isrc,
        duration_seconds=req.duration_seconds, url=req.url, artwork_url=req.album_art_url,
    )
    add_track_to_playlist(db, track, playlist)
    recount_playlist(db, playlist)
    db.commit()
```

(Rimuovi il blocco `if track.playlist_id is None: ...` con il commento sul modello 1:1.)

- [ ] **Step 8: Aggiorna i test esistenti rotti dal cambio modello**

(8a) `tests/test_playlist_sync.py` — sostituisci le asserzioni basate su `Track.playlist_id` con la membership:

- riga 45-47:
```python
    t3 = db.query(Track).filter(Track.isrc == "ISRC0000003").one()
    assert t3 not in tracks_for_playlist(db, playlist.id)
```
- riga 52:
```python
    assert len(tracks_for_playlist(db, playlist.id)) == 2
```
- riga 86:
```python
    assert len(tracks_for_playlist(db, pl_b.id)) == 1
```
- riga 102:
```python
    assert len(tracks_for_playlist(db, playlist.id)) == 2
```
- riga 137-138:
```python
    pl = db.query(Playlist).filter(Playlist.platform_playlist_id == "PL1").one()
    assert db.query(Track).filter(Track.isrc == "ISRC0000002").one() not in tracks_for_playlist(db, pl.id)
```
Aggiungi in cima al file: `from app.repositories import tracks_for_playlist`.
(La riga 49-50 `playlist.track_count == 2` resta valida.)

(8b) `tests/test_manual_import.py` — riga 27:
```python
    from app.repositories import tracks_for_playlist
    tracks = tracks_for_playlist(db, pl.id)
```
(8c) `tests/test_playlist_pivot.py` — riga 217-220 (delete): sostituisci
```python
    assert db.query(Track).one().playlist_id is None
```
con
```python
    assert db.query(Track).count() == 1  # il brano resta in libreria dopo la delete
```

(8d) `tests/test_set_builder_phase_c.py` — converti `_add_track` alla membership:
```python
from app.repositories import add_track_to_playlist, tracks_for_playlist


def _add_track(db, pl, i, **kw):
    t = Track(source_type="spotify", title=f"T{i}", artist=f"Art{i}", duration_seconds=200, **kw)
    db.add(t); db.flush()
    add_track_to_playlist(db, t, pl)
    return t
```
e aggiorna le chiamate `_add_track(db, pl.id, ...)` → `_add_track(db, pl, ...)` e `_add_track(db, other.id, ...)` → `_add_track(db, other, ...)`; sostituisci
`in_pl = {t.id for t in db.query(Track).filter(Track.playlist_id == pl.id).all()}`
con
`in_pl = {t.id for t in tracks_for_playlist(db, pl.id)}`.

(8e) `tests/test_enrichment_resilience.py` — righe 106-115: crea i track e poi la membership:
```python
    from app.repositories import add_track_to_playlist, tracks_for_playlist
    for i in range(3):
        ta = Track(source_type="spotify", title=f"A{i}", artist="X"); db.add(ta); db.flush()
        add_track_to_playlist(db, ta, pa)
        tb = Track(source_type="spotify", title=f"B{i}", artist="Y"); db.add(tb); db.flush()
        add_track_to_playlist(db, tb, pb)
    db.commit()
    report = enrich_features(db, _ConstProvider(), playlist_id=pa.id)
    ...
    a_tracks = tracks_for_playlist(db, pa.id)
    b_tracks = tracks_for_playlist(db, pb.id)
```
(Adatta ai nomi di variabile effettivi `pa`/`pb` nel file.)

(8f) `tests/test_discovery.py` — `_make_playlist` (137-145): membership invece di playlist_id:
```python
    from app.repositories import add_track_to_playlist
    pl = Playlist(platform="spotify", name="Test Playlist", kind="playlist")
    db.add(pl); db.flush()
    for r in rows:
        t = Track(source_type="spotify", platform="spotify", status="ready_for_set", **r)
        db.add(t); db.flush()
        add_track_to_playlist(db, t, pl)
    db.commit()
    return pl.id
```
e nel test `test_dig_endpoint_honors_taste_playlist_id` sostituisci la creazione `Track(..., playlist_id=pl.id)` con creazione + `add_track_to_playlist(db, t, pl)` + `db.commit()`.
(La riga 228 `assert track.playlist_id is None` resta valida: l'`/add` non collega a playlist e la colonna legacy resta None.)

(8g) `tests/test_playlist_add_track.py` — aggiorna le asserzioni che leggono `Track.playlist_id`:
- import in cima: `from app.repositories import tracks_for_playlist`
- in `test_add_to_spotify_playlist_attaches_and_writes_back` (riga 45-46):
```python
    assert track_in_playlist(db, pl.id, "sp1")
```
dove aggiungi in fondo al file l'helper:
```python
def track_in_playlist(db, playlist_id, spotify_id):
    return any(t.spotify_id == spotify_id for t in tracks_for_playlist(db, playlist_id))
```
- `test_add_to_manual_playlist_local_only` (riga 57): `assert track_in_playlist(db, pl.id, "sp1")`
- `test_write_back_failure_is_non_blocking` (riga 79): `assert track_in_playlist(db, pl.id, "sp1")`
- `test_add_does_not_move_track_from_other_playlist`: cambia semantica — ora la traccia entra ANCHE nella target. Riscrivi le asserzioni finali:
```python
    resp = add_discovered_track(target.id, _req(), db)
    assert resp.created is False                      # gia' in libreria
    assert track_in_playlist(db, other.id, "sp1")    # resta nella prima
    assert track_in_playlist(db, target.id, "sp1")   # e viene aggiunta alla target
    assert resp.spotify_added is True
```
e rinomina il test in `test_add_links_existing_track_to_target_playlist`.

- [ ] **Step 9: Esegui l'intera suite**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests -q`
Expected: PASS (tutti). Se un test fallisce per setup residuo su `Track.playlist_id`, convertilo alla membership con lo stesso pattern (`add_track_to_playlist` + `tracks_for_playlist`).

- [ ] **Step 10: Commit**

```bash
git add backend/app/repositories.py backend/app/services/playlist_import.py backend/app/services/manual_import.py backend/app/services/feature_enrichment.py backend/app/routers/playlists.py backend/tests/
git commit -m "feat(playlists): import/prune/delete/enrichment/endpoint su membership M2M"
```

---

## Task 3: Serializer + schema `TrackOut.playlists`

**Files:**
- Modify: `backend/app/schemas.py`
- Modify: `backend/app/serializers.py`
- Modify: `backend/app/repositories.py` (eager-load)
- Test: `backend/tests/test_playlist_membership.py`

**Interfaces:**
- Consumes: `Track.playlists` (Task 1), helper repo (Task 2).
- Produces: `TrackPlaylistRef{id:int, name:str}`; `TrackOut.playlists: list[TrackPlaylistRef]` (rimossi `playlist_id`/`playlist_name`).

- [ ] **Step 1: Scrivi il test del serializer (fallisce)**

Aggiungi a `backend/tests/test_playlist_membership.py`:

```python
def test_track_out_exposes_playlists(db):
    from app.serializers import track_out
    a, b, t = _pl(db, "A"), _pl(db, "B"), _tr(db, "T")
    add_track_to_playlist(db, t, a)
    add_track_to_playlist(db, t, b)
    db.commit()
    out = track_out(t)
    assert {p.name for p in out.playlists} == {"A", "B"}
    assert not hasattr(out, "playlist_id")
```

- [ ] **Step 2: Esegui il test (fallisce)**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_playlist_membership.py -k track_out -v`
Expected: FAIL — `TrackOut` ha ancora `playlist_id` / non ha `playlists`.

- [ ] **Step 3: Aggiorna lo schema**

In `backend/app/schemas.py`, trova `TrackOut` (campi attorno alla riga 26-45 mostrano `playlist_id`/`playlist_name`). Aggiungi prima di `TrackOut` la ref e modifica i campi:

```python
class TrackPlaylistRef(BaseModel):
    id: int
    name: str
```

In `TrackOut` rimuovi:
```python
    playlist_id: int | None = None
    playlist_name: str | None = None
```
e aggiungi:
```python
    playlists: list[TrackPlaylistRef] = []
```

- [ ] **Step 4: Aggiorna il serializer**

In `backend/app/serializers.py`, in `track_out`, sostituisci le righe:
```python
        playlist_id=track.playlist_id,
        playlist_name=track.playlist_name,
```
con:
```python
        playlists=[TrackPlaylistRef(id=p.id, name=p.name) for p in track.playlists],
```
e aggiungi `TrackPlaylistRef` all'import degli schemi in cima al file.

- [ ] **Step 5: Eager-load delle appartenenze (evita N+1)**

In `backend/app/repositories.py`:
- in `list_tracks`, aggiungi `.options(selectinload(Track.playlists))` allo `stmt` prima di eseguire `rows`:
```python
    rows = db.scalars(
        stmt.options(selectinload(Track.playlists)).order_by(*order_by).limit(limit).offset(offset)
    ).all()
```
- in `get_track`:
```python
def get_track(db: Session, track_id: int) -> Track | None:
    return db.scalar(
        select(Track).options(selectinload(Track.playlists)).where(Track.id == track_id)
    )
```
- in `tracks_for_playlist`, aggiungi `.options(selectinload(Track.playlists))` allo statement.

(`selectinload` è già importato in `repositories.py`.)

- [ ] **Step 6: Esegui la suite**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas.py backend/app/serializers.py backend/app/repositories.py backend/tests/test_playlist_membership.py
git commit -m "feat(api): TrackOut espone playlists[] (membership), rimossi i campi legacy"
```

---

## Task 4: Frontend — interfaccia + "in N playlist"

**Files:**
- Modify: `frontend/lib/api.ts`
- Modify: `frontend/app/library/page.tsx`
- Modify: `frontend/app/tracks/[id]/page.tsx`

**Interfaces:**
- Consumes: `TrackOut.playlists` (Task 3).

- [ ] **Step 1: Aggiorna l'interfaccia `Track`**

In `frontend/lib/api.ts`, nell'interfaccia `Track`, sostituisci:
```typescript
  playlist_id: number | null;
  playlist_name: string | null;
```
con:
```typescript
  playlists: { id: number; name: string }[];
```

- [ ] **Step 2: Libreria — colonna/badge "in N playlist"**

In `frontend/app/library/page.tsx`:
- nell'header tabella, dopo l'header Stato (`<th className={cell}></th>` o quello dello stato), aggiungi una colonna:
```tsx
              <th className={cell}>Playlist</th>
```
- nelle righe, dopo la cella Stato (riga ~147), aggiungi:
```tsx
                <td className={`${cell} tnum text-muted`} title={t.playlists.map((p) => p.name).join(", ")}>
                  {t.playlists.length || "—"}
                </td>
```
- aggiorna il `colSpan` dell'empty-state da `10` a `11` (riga ~157).

- [ ] **Step 3: Dettaglio traccia — elenco playlist**

In `frontend/app/tracks/[id]/page.tsx`, nell'array `rows` (riga ~60-64) aggiungi una voce:
```tsx
    ["Playlist", track.playlists.length ? track.playlists.map((p) => p.name).join(", ") : "—"],
```

- [ ] **Step 4: Lint + build**

Run: `cd frontend && npm run lint && npm run build`
Expected: 0 errori (warning `<img>` preesistenti ok); `/library` e `/tracks/[id]` compilano.

- [ ] **Step 5: Commit**

```bash
git add frontend/lib/api.ts frontend/app/library/page.tsx "frontend/app/tracks/[id]/page.tsx"
git commit -m "feat(ui): mostra le playlist di appartenenza (libreria + dettaglio traccia)"
```

---

## Task 5: Verifica + documentazione

**Files:**
- Modify: `docs/ROADMAP.md`, `PROGRESS.md`, `docs/ARCHITECTURE.md` (se descrive il modello)

- [ ] **Step 1: Verifica nel browser (preview)**

Con backend (codice nuovo, porta 8000) e preview frontend attivi:
1. Importa o usa una playlist esistente; usa l'espansione + "Aggiungi" per mettere un brano già presente in una seconda playlist.
2. In `/library` verifica il conteggio "in N playlist" sul brano condiviso (tooltip coi nomi).
3. Nel dettaglio del brano verifica l'elenco delle playlist.
Cattura uno screenshot.

- [ ] **Step 2: Aggiorna ROADMAP**

In `docs/ROADMAP.md`, sotto "Stato completato" aggiungi:
```markdown
- Playlist many-to-many: tabella associativa `playlist_tracks` (membership), import che
  aggiunge appartenenze invece di sovrascrivere, delete/prune per-playlist, libreria che
  mostra "in N playlist". Colonne legacy `Track.playlist_id`/`playlist_name` svuotate.
```
e rimuovi la voce "Playlist many-to-many" dal backlog tecnico.

- [ ] **Step 3: Aggiorna PROGRESS**

In `PROGRESS.md` aggiungi una milestone datata 2026-06-28 con i file toccati e il punto di ripresa; aggiorna "Ultimo aggiornamento".

- [ ] **Step 4: Aggiorna ARCHITECTURE (se serve)**

Se `docs/ARCHITECTURE.md` descrive il legame brano-playlist come 1:1, aggiornalo al modello M2M (`playlist_tracks`, `added_at` per-playlist).

- [ ] **Step 5: Suite backend finale**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add docs/ROADMAP.md PROGRESS.md docs/ARCHITECTURE.md
git commit -m "docs(status): playlist many-to-many completato"
```

---

## Self-Review (eseguita)

**Spec coverage:**
- Tabella associativa + relationships + `added_at` per-playlist → Task 1.
- Migrazione backfill idempotente + svuotamento colonne legacy → Task 1.
- Helper repo + `tracks_for_playlist`/`delete_playlist` su membership → Task 2.
- Import Spotify+manuale (add membership, non overwrite) + prune → Task 2.
- Enrichment scoping via membership → Task 2.
- Endpoint `discovered-tracks` su membership (via edge-case 1:1) → Task 2.
- `track_count` ricalcolato (`recount_playlist`) → Task 2.
- `TrackOut.playlists` + eager-load → Task 3.
- UI "in N playlist" (libreria + dettaglio) → Task 4.
- Test (migrazione, due playlist, no-steal, prune, delete, endpoint, enrichment, serializer) → Task 1/2/3.
- Docs → Task 5.

**Placeholder scan:** nessun TBD/TODO; ogni step mostra il codice o l'edit esatto.

**Type consistency:** `add_track_to_playlist(db, track, playlist, *, added_at)`, `remove_track_from_playlist(db, playlist_id, track_id)`, `recount_playlist(db, playlist)`, `tracks_for_playlist(db, playlist_id)`, `TrackPlaylistRef{id,name}`, `TrackOut.playlists`, frontend `Track.playlists` coerenti tra i task.
