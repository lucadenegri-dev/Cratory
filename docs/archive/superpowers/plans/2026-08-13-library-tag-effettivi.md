# Library: tag effettivi dal file fisico — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Per le tracce possedute, la Library mostra e filtra genre/album/label/year presi dai tag del file fisico (primary file), e il TrackEditModal li modifica scrivendo i tag via l'endpoint Organize esistente.

**Architecture:** Risoluzione a query-time con `COALESCE` su un `outerjoin` tra `tracks` e `audio_file` via `tracks.primary_file_id` — nessuna colonna derivata, nessuna migrazione. Il serializer espone il valore effettivo nei campi esistenti più flag di provenienza; la scrittura fisica dei tag resta SOLO su `POST /api/organize/files/{id}/tags` (regola single-writer, CLAUDE.md regola 7).

**Tech Stack:** FastAPI + SQLAlchemy/SQLite (backend), Next.js 16 App Router + React + vitest (frontend).

**Spec:** `docs/superpowers/specs/2026-08-13-library-tag-effettivi-design.md`

## Global Constraints

- **Single writer:** nessun nuovo codice che scrive tag su file. L'unica scrittura è il riuso di `POST /api/organize/files/{id}/tags`.
- **Semantica COALESCE:** tag NULL sul file → si vede il valore streaming della `Track`. Flag `*_from_file` = "il file ha un valore non-NULL per questo campo".
- **Backend test:** `cd backend && source .venv/bin/activate && python -m pytest tests/<file> -v` (in un worktree: usare il venv del checkout principale, cwd = backend del worktree).
- **Frontend:** Next.js 16 ha breaking changes — leggere la doc in `frontend/node_modules/next/dist/docs/` prima di toccare pagine/routing. `useSearchParams` richiede un boundary `<Suspense>`.
- **i18n:** ogni stringa visibile va aggiunta sia in `frontend/lib/i18n/it.ts` sia in `frontend/lib/i18n/en.ts` (test di parità esistente).
- **Commit:** MAI aggiungere `Co-Authored-By` / firme Claude nei messaggi (preferenza utente, override del default).
- **Test non vacui:** ogni asserzione va provata rompendo il codice (regola di casa): il test del filtro effettivo DEVE fallire se il filtro usa la sola colonna `tracks.genre`.
- **Sessioni parallele:** prima di ogni commit `git status --porcelain` e stage dei SOLI file del task; verificare di essere su `master`.

---

### Task 1: Repository — espressioni effettive, join sul primary file, `FileTags`

**Files:**
- Modify: `backend/app/repositories.py` (righe ~1–140: import, `_SORT_COLUMNS`, `_apply_track_filters`, `list_tracks`, dopo `get_track`)
- Test: `backend/tests/test_library_effective_tags.py` (nuovo)

**Interfaces:**
- Consumes: `Track.primary_file_id` (già esistente), `app.organize.models.AudioFile`.
- Produces (usati dai Task 2–3):
  - `FileTags` dataclass frozen con campi `genre: str | None`, `album: str | None`, `label: str | None`, `year: int | None`, `artist: str | None`, `title: str | None`, tutti default `None`.
  - `list_tracks(db, *, limit, offset, sort, order, **filters) -> tuple[int, list[tuple[Track, FileTags]]]` (PRIMA restituiva `tuple[int, list[Track]]`).
  - `get_primary_file(db: Session, track: Track) -> AudioFile | None`.
  - `_EFFECTIVE_TAGS: dict[str, ColumnElement]` e `_join_primary_file(stmt)` (privati, riusati da `genres_overview` nel Task 3).

- [ ] **Step 1: Scrivere i test che falliscono**

Creare `backend/tests/test_library_effective_tags.py`:

```python
"""I tag descrittivi (genre/album/label/year) in Library sono quelli del file
fisico quando la traccia ha un primary file: COALESCE(file, track) a query-time.

Il file vince quando ha un valore; un tag NULL sul file lascia visibile il
valore streaming. Artist/title NON seguono il file (identità Cratory).
"""

import pytest

from app.models import Track
from app.organize.models import AudioFile, ScanRoot
from app.repositories import FileTags, get_primary_file, list_tracks


@pytest.fixture()
def make_owned(db):
    """Factory: crea una Track con un AudioFile primario dai tag dati."""
    root = ScanRoot(path="/tmp/lib")
    db.add(root)
    db.flush()

    def make(*, track_kw=None, file_kw=None) -> Track:
        t = Track(source_type="spotify", **(track_kw or {}))
        db.add(t)
        db.flush()
        f = AudioFile(
            root_id=root.id, track_id=t.id, path=f"/tmp/lib/{t.id}.mp3",
            ext=".mp3", size_bytes=1, hash_method="stream",
            status="present", location="library", **(file_kw or {}),
        )
        db.add(f)
        db.flush()
        t.primary_file_id = f.id
        t.has_local_file = True
        db.commit()
        return t

    return make


def test_file_tags_vincono_su_quelli_streaming(db, make_owned):
    make_owned(
        track_kw={"title": "T", "artist": "A", "genre": "Pop", "album": "SA",
                  "label": "SL", "year": 2001},
        file_kw={"genre": "Techno", "album": "FA", "label": "FL", "year": 2020},
    )
    _, rows = list_tracks(db)
    (_track, tags) = rows[0]
    assert tags == FileTags(genre="Techno", album="FA", label="FL", year=2020)


def test_tag_null_sul_file_lascia_il_valore_track(db, make_owned):
    make_owned(
        track_kw={"title": "T", "artist": "A", "genre": "Pop"},
        file_kw={"genre": None, "album": "FA"},
    )
    _, rows = list_tracks(db)
    (_track, tags) = rows[0]
    # genre resta None nei FileTags: il fallback su Track.genre avviene nel
    # serializer, così il flag di provenienza è derivabile (None = non dal file).
    assert tags.genre is None
    assert tags.album == "FA"


def test_traccia_senza_file_ha_filetags_vuoti(db):
    db.add(Track(source_type="spotify", title="T", artist="A", genre="Pop"))
    db.commit()
    _, rows = list_tracks(db)
    (_track, tags) = rows[0]
    assert tags == FileTags()


def test_filtro_genre_matcha_il_tag_del_file(db, make_owned):
    """DEVE fallire se il filtro usa la sola colonna tracks.genre."""
    make_owned(track_kw={"title": "T", "artist": "A", "genre": "Pop"},
               file_kw={"genre": "Techno"})
    total, rows = list_tracks(db, genre="techno")
    assert total == 1 and len(rows) == 1
    # ...e il valore streaming ora mascherato dal file NON matcha più:
    total, _ = list_tracks(db, genre="pop")
    assert total == 0


def test_filtro_genre_matcha_ancora_il_valore_track_senza_file(db):
    db.add(Track(source_type="spotify", title="T", artist="A", genre="Pop"))
    db.commit()
    total, _ = list_tracks(db, genre="pop")
    assert total == 1


def test_sort_genre_usa_il_valore_effettivo(db, make_owned):
    # senza file, genre "A"; con file, tag "Z" che maschera genre "B"
    db.add(Track(source_type="spotify", title="T1", artist="A", genre="Alpha"))
    db.commit()
    make_owned(track_kw={"title": "T2", "artist": "A", "genre": "Beta"},
               file_kw={"genre": "Zulu"})
    _, rows = list_tracks(db, sort="genre", order="asc")
    generi_effettivi = [tags.genre or t.genre for t, tags in rows]
    assert generi_effettivi == ["Alpha", "Zulu"]
    _, rows = list_tracks(db, sort="genre", order="desc")
    generi_effettivi = [tags.genre or t.genre for t, tags in rows]
    assert generi_effettivi == ["Zulu", "Alpha"]


def test_get_primary_file(db, make_owned):
    t = make_owned(track_kw={"title": "T", "artist": "A"},
                   file_kw={"genre": "Techno", "artist": "FA", "title": "FT"})
    pf = get_primary_file(db, t)
    assert pf is not None and pf.genre == "Techno"
    lead = Track(source_type="spotify", title="L", artist="A")
    db.add(lead)
    db.commit()
    assert get_primary_file(db, lead) is None
```

- [ ] **Step 2: Eseguire i test e verificarli FAIL**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_library_effective_tags.py -v`
Expected: FAIL con `ImportError: cannot import name 'FileTags'`.

- [ ] **Step 3: Implementare in `repositories.py`**

In testa al file (dopo gli import esistenti):

```python
from dataclasses import dataclass

from app.organize.models import AudioFile


@dataclass(frozen=True)
class FileTags:
    """Tag letti dal primary file di una traccia (None = campo assente o
    nessun file). Il fallback sui valori Track avviene nel serializer, che
    da un None deriva anche il flag di provenienza."""

    genre: str | None = None
    album: str | None = None
    label: str | None = None
    year: int | None = None
    artist: str | None = None
    title: str | None = None


def _join_primary_file(stmt):
    """Aggancia il file rappresentante: da qui vengono i tag effettivi."""
    return stmt.outerjoin(AudioFile, AudioFile.id == Track.primary_file_id)


# Valore effettivo dei campi descrittivi: il tag del file vince, il valore
# streaming della Track è il fallback. Riusato identico in select/filtri/sort
# così ciò che si vede e ciò che si filtra coincidono sempre.
_EFFECTIVE_TAGS = {
    "genre": func.coalesce(AudioFile.genre, Track.genre),
    "album": func.coalesce(AudioFile.album, Track.album),
    "label": func.coalesce(AudioFile.label, Track.label),
    "year": func.coalesce(AudioFile.year, Track.year),
}
```

In `_SORT_COLUMNS` sostituire le due voci:

```python
    "genre": _EFFECTIVE_TAGS["genre"],
    "year": _EFFECTIVE_TAGS["year"],
```

In `_apply_track_filters` sostituire le tre condizioni:

```python
    if album:
        stmt = stmt.where(_EFFECTIVE_TAGS["album"].ilike(f"%{album}%"))
    if genre:
        stmt = stmt.where(_EFFECTIVE_TAGS["genre"].ilike(f"%{genre}%"))
    if label:
        stmt = stmt.where(_EFFECTIVE_TAGS["label"] == label)  # match esatto: drill-down dall'etichetta
```

Riscrivere `list_tracks` (il join va applicato PRIMA dei filtri, sia alla
select sia alla count):

```python
def list_tracks(
    db: Session, *, limit: int = 100, offset: int = 0,
    sort: str | None = None, order: str = "asc", **filters,
) -> tuple[int, list[tuple[Track, FileTags]]]:
    file_cols = (AudioFile.genre, AudioFile.album, AudioFile.label,
                 AudioFile.year, AudioFile.artist, AudioFile.title)
    stmt = _apply_track_filters(_join_primary_file(select(Track, *file_cols)), **filters)
    total = db.scalar(select(func.count()).select_from(
        _apply_track_filters(_join_primary_file(select(Track.id)), **filters).subquery()))

    column = _SORT_COLUMNS.get(sort or "")
    if column is not None:
        direction = column.desc() if order == "desc" else column.asc()
        # NULL sempre in fondo, poi id come tie-breaker (paginazione deterministica).
        order_by = (column.is_(None), direction, Track.id.asc())
    else:
        order_by = (Track.artist.is_(None), Track.artist, Track.title)

    result = db.execute(
        # limit=0 -> None: nessun limite (tutte le tracce, per la vista griglia).
        stmt.options(selectinload(Track.playlists)).order_by(*order_by).limit(limit or None).offset(offset)
    ).all()
    rows = [(row[0], FileTags(genre=row[1], album=row[2], label=row[3],
                              year=row[4], artist=row[5], title=row[6]))
            for row in result]
    return total or 0, rows
```

Dopo `get_track` aggiungere:

```python
def get_primary_file(db: Session, track: Track) -> AudioFile | None:
    """Il file rappresentante della traccia (fonte dei tag effettivi)."""
    if not track.primary_file_id:
        return None
    return db.get(AudioFile, track.primary_file_id)
```

- [ ] **Step 4: Eseguire i test e verificarli PASS**

Run: `python -m pytest tests/test_library_effective_tags.py -v`
Expected: PASS (8 test).

- [ ] **Step 5: Suite completa (il cambio di firma rompe il chiamante — atteso)**

Run: `python -m pytest tests -x -q 2>&1 | tail -20`
`routers/tracks.py:75` fa `track_out(t) for t in rows`: con le tuple i test
del router falliranno. Se falliscono SOLO per questo, va bene: lo sistema il
Task 2 (stessa PR logica). NON committare ancora la suite rossa: il commit di
questo task arriva nel Task 2 insieme al fix del chiamante, oppure — se la
suite è verde perché nessun test copre la lista — committare qui:

```bash
git status --porcelain   # solo i due file attesi
git add backend/app/repositories.py backend/tests/test_library_effective_tags.py
git commit -m "feat(library): tag effettivi dal primary file a query-time (COALESCE su audio_file)"
```

---

### Task 2: Serializer e schemi — flag di provenienza, `primary_file_id`, `file_artist`/`file_title`

**Files:**
- Modify: `backend/app/serializers.py` (`track_out`, `track_detail_out`)
- Modify: `backend/app/schemas.py` (`TrackOut`, `TrackDetailOut`)
- Modify: `backend/app/routers/tracks.py:63-83` (list e detail)
- Test: `backend/tests/test_library_effective_tags.py` (estendere)

**Interfaces:**
- Consumes: `FileTags`, `list_tracks` (nuova firma), `get_primary_file` dal Task 1.
- Produces:
  - `track_out(track: Track, file_tags: FileTags | None = None) -> TrackOut` — con `file_tags=None` comportamento identico a prima (tutti i chiamanti esistenti — setlist, playlists, downloads, discovery, transitions — restano validi senza modifiche).
  - `track_detail_out(track: Track, file_tags: FileTags | None = None) -> TrackDetailOut`.
  - `TrackOut` nuovi campi: `primary_file_id: int | None = None`, `genre_from_file: bool = False`, `album_from_file: bool = False`, `label_from_file: bool = False`, `year_from_file: bool = False`.
  - `TrackDetailOut` nuovi campi: `file_artist: str | None = None`, `file_title: str | None = None`.

- [ ] **Step 1: Estendere il test (failing)**

Aggiungere in coda a `backend/tests/test_library_effective_tags.py`:

```python
from app.repositories import get_track
from app.routers import tracks as tracks_router
from app.serializers import track_detail_out, track_out


def test_track_out_espone_effettivi_e_provenienza(db, make_owned):
    t = make_owned(
        track_kw={"title": "T", "artist": "A", "genre": "Pop", "year": 2001},
        file_kw={"genre": "Techno", "album": "FA"},  # label/year NULL sul file
    )
    _, rows = list_tracks(db)
    out = track_out(rows[0][0], rows[0][1])
    assert out.genre == "Techno" and out.genre_from_file is True
    assert out.album == "FA" and out.album_from_file is True
    assert out.year == 2001 and out.year_from_file is False   # fallback su Track
    assert out.label is None and out.label_from_file is False
    assert out.primary_file_id == t.primary_file_id
    # identità NON seguono il file:
    assert out.title == "T" and out.artist == "A"


def test_track_out_senza_filetags_invariato(db):
    t = Track(source_type="spotify", title="T", artist="A", genre="Pop")
    db.add(t)
    db.commit()
    out = track_out(t)
    assert out.genre == "Pop" and out.genre_from_file is False
    assert out.primary_file_id is None


def test_detail_espone_artist_title_del_file(db, make_owned):
    t = make_owned(track_kw={"title": "T", "artist": "A"},
                   file_kw={"artist": "File Artist", "title": "File Title",
                            "genre": "Techno"})
    detail = tracks_router.get_track_detail(t.id, db=db)
    assert detail.file_artist == "File Artist"
    assert detail.file_title == "File Title"
    assert detail.genre == "Techno" and detail.genre_from_file is True


def test_detail_lead_senza_file(db):
    t = Track(source_type="spotify", title="T", artist="A")
    db.add(t)
    db.commit()
    detail = tracks_router.get_track_detail(t.id, db=db)
    assert detail.file_artist is None and detail.file_title is None
```

- [ ] **Step 2: Verificare che falliscano**

Run: `python -m pytest tests/test_library_effective_tags.py -v`
Expected: i 4 nuovi FAIL (`track_out() takes 1 positional argument` / `TrackOut has no field genre_from_file`).

- [ ] **Step 3: Implementare**

`backend/app/schemas.py`, in `TrackOut` dopo `local_bitrate`:

```python
    # F-tag-effettivi: i campi genre/album/label/year qui sopra portano il
    # valore EFFETTIVO (tag del primary file se non-NULL, altrimenti il valore
    # streaming). I flag dicono da dove viene ogni valore.
    primary_file_id: int | None = None
    genre_from_file: bool = False
    album_from_file: bool = False
    label_from_file: bool = False
    year_from_file: bool = False
```

In `TrackDetailOut`:

```python
class TrackDetailOut(TrackOut):
    """Dettaglio traccia: aggiunge artist/title letti dal file (informativi,
    l'identità resta quella della Track)."""

    file_artist: str | None = None
    file_title: str | None = None
```

`backend/app/serializers.py` — import e firma:

```python
from app.repositories import FileTags
```

In `track_out`, nuova firma `def track_out(track: Track, file_tags: FileTags | None = None) -> TrackOut:` e, come prime righe del corpo:

```python
    ft = file_tags or FileTags()
```

Sostituire le quattro righe dei campi descrittivi e aggiungere i nuovi campi:

```python
        album=ft.album if ft.album is not None else track.album,
        genre=ft.genre if ft.genre is not None else track.genre,
        year=ft.year if ft.year is not None else track.year,
        label=ft.label if ft.label is not None else track.label,
        primary_file_id=track.primary_file_id,
        genre_from_file=ft.genre is not None,
        album_from_file=ft.album is not None,
        label_from_file=ft.label is not None,
        year_from_file=ft.year is not None,
```

(attenzione: `album`/`genre`/`year` stanno già nella chiamata esistente in
posizioni diverse — sostituirle lì, non duplicarle; `label` idem.)

`track_detail_out`:

```python
def track_detail_out(track: Track, file_tags: FileTags | None = None) -> TrackDetailOut:
    ft = file_tags or FileTags()
    return TrackDetailOut(**track_out(track, file_tags).model_dump(),
                          file_artist=ft.artist, file_title=ft.title)
```

`backend/app/routers/tracks.py` — riga 75:

```python
    return TrackListOut(total=total, items=[track_out(t, ft) for t, ft in rows])
```

`track_detail_out` ha TRE chiamanti in questo router (GET detail riga 83,
PATCH riga 159, link-file riga 173), tutti con una `Track` in mano: aggiungere
un helper condiviso e usarlo in tutti e tre. Import: `get_primary_file` e
`FileTags` da `app.repositories`.

```python
def _detail_with_file_tags(db: Session, track: Track) -> TrackDetailOut:
    """Dettaglio con i tag del primary file (effettivi + file_artist/file_title)."""
    pf = get_primary_file(db, track)
    ft = FileTags(genre=pf.genre, album=pf.album, label=pf.label, year=pf.year,
                  artist=pf.artist, title=pf.title) if pf else None
    return track_detail_out(track, ft)
```

Le tre `return track_detail_out(track)` (righe 83, 159, 173) diventano:

```python
    return _detail_with_file_tags(db, track)
```

(Il PATCH e link-file così rispondono subito con gli effettivi aggiornati —
importante per link-file, che imposta il primary file nella stessa richiesta.)

- [ ] **Step 4: Test PASS + suite completa**

Run: `python -m pytest tests/test_library_effective_tags.py -v` → PASS.
Run: `python -m pytest tests -q 2>&1 | tail -5` → tutta verde (il chiamante rotto dal Task 1 è sistemato).

- [ ] **Step 5: Commit (include repositories.py del Task 1 se non già committato)**

```bash
git status --porcelain
git add backend/app/repositories.py backend/app/serializers.py backend/app/schemas.py backend/app/routers/tracks.py backend/tests/test_library_effective_tags.py
git commit -m "feat(library): payload con tag effettivi, flag di provenienza e artist/title del file nel dettaglio"
```

---

### Task 3: Aggregato generi e candidate engine sul genere effettivo

**Files:**
- Modify: `backend/app/repositories.py` (`genres_overview`, `all_playable_tracks`, nuovo helper `effective_genre`)
- Modify: `backend/app/services/candidate_engine.py:82`
- Test: `backend/tests/test_library_effective_tags.py` (estendere)

**Interfaces:**
- Consumes: `_EFFECTIVE_TAGS`, `_join_primary_file` dal Task 1.
- Produces: `effective_genre(track: Track) -> str | None` (richiede `track.files` caricata o lazy-loadabile).

**Perché il candidate engine è incluso:** `/api/library/genres` alimenta il
multi-select del Set Builder; se l'aggregato passa ai generi effettivi ma il
candidate engine continua a filtrare su `Track.genre`, un genere curato solo
nei tag file comparirebbe nel multi-select e matcherebbe zero candidati. La
coerenza "ciò che si vede è ciò che si filtra" impone di aggiornare entrambi.

- [ ] **Step 1: Test failing**

Aggiungere a `backend/tests/test_library_effective_tags.py`:

```python
from app.repositories import all_playable_tracks, effective_genre, genres_overview


def test_genres_overview_conta_il_genere_effettivo(db, make_owned):
    # candidabile = con BPM (come da docstring di genres_overview)
    make_owned(track_kw={"title": "T", "artist": "A", "genre": "Pop", "bpm": 128.0},
               file_kw={"genre": "Techno"})
    db.add(Track(source_type="spotify", title="L", artist="A",
                 genre="House", bpm=124.0))
    db.commit()
    rows = genres_overview(db)
    assert {r["genre"] for r in rows} == {"Techno", "House"}  # niente "Pop"


def test_effective_genre_helper(db, make_owned):
    t = make_owned(track_kw={"title": "T", "artist": "A", "genre": "Pop", "bpm": 128.0},
                   file_kw={"genre": "Techno"})
    (t_loaded,) = [x for x in all_playable_tracks(db) if x.id == t.id]
    assert effective_genre(t_loaded) == "Techno"
    lead = Track(source_type="spotify", title="L", artist="A", genre="House", bpm=124.0)
    db.add(lead)
    db.commit()
    assert effective_genre(lead) == "House"


def test_candidate_engine_filtra_sul_genere_effettivo(db, make_owned):
    """DEVE fallire se candidate_engine confronta t.genre invece del genere
    effettivo: la traccia è taggata Techno solo sul file (Track.genre="Pop")."""
    from app.schemas import SetGenerationRequest
    from app.services.candidate_engine import select_candidates

    t = make_owned(track_kw={"title": "T", "artist": "A", "genre": "Pop",
                             "bpm": 128.0, "camelot_key": "8A",
                             "duration_seconds": 300},
                   file_kw={"genre": "Techno"})
    pool = select_candidates(db, SetGenerationRequest(genres=["Techno"]))
    assert [x.id for x in pool] == [t.id]
    # ...e il genere streaming, ora mascherato dal tag file, non matcha più:
    pool = select_candidates(db, SetGenerationRequest(genres=["Pop"]))
    assert pool == []
```

(Il match del candidate engine è ESATTO case-insensitive su `req.genres` —
riga 74 di `candidate_engine.py` — quindi "Techno" matcha "Techno" del tag
file; `owned_only=True` di default è soddisfatto perché `make_owned` imposta
`has_local_file=True`; `duration_seconds=300` supera `MIN_TRACK_SECONDS`.)

- [ ] **Step 2: Verificare FAIL**

Run: `python -m pytest tests/test_library_effective_tags.py -v`
Expected: i nuovi test FAIL (`cannot import name 'effective_genre'`).

- [ ] **Step 3: Implementare**

`backend/app/repositories.py` — `genres_overview`:

```python
def genres_overview(db: Session) -> list[dict]:
    """Generi EFFETTIVI (tag del primary file, fallback streaming) tra le tracce
    candidabili (con BPM), col conteggio, ordinati per frequenza. Alimenta il
    multi-select del Set Builder e i link della dashboard."""
    eff = _EFFECTIVE_TAGS["genre"]
    rows = db.execute(
        _join_primary_file(select(eff, func.count()))
        .where(Track.bpm.is_not(None), eff.is_not(None), eff != "")
        .group_by(eff)
        .order_by(func.count().desc(), eff)
    ).all()
    return [{"genre": g, "count": n} for g, n in rows]
```

Nuovo helper (sotto `get_primary_file`):

```python
def effective_genre(track: Track) -> str | None:
    """Genere effettivo lato Python (specchio di _EFFECTIVE_TAGS['genre'] per
    il codice che lavora su oggetti ORM già caricati, es. candidate engine).
    `track.files` è il backref dichiarato su AudioFile.track."""
    pf = None
    if track.primary_file_id:
        pf = next((f for f in track.files if f.id == track.primary_file_id), None)
    return pf.genre if pf is not None and pf.genre is not None else track.genre
```

`all_playable_tracks`: aggiungere il caricamento batch dei file (evita N+1
lazy load quando il candidate engine chiama `effective_genre` su tutto il pool):

```python
    stmt = select(Track).options(
        selectinload(Track.playlists), selectinload(Track.files)
    ).where(Track.bpm.is_not(None))
```

`backend/app/services/candidate_engine.py` riga 82 — sostituire il confronto:

```python
        genere = effective_genre(t)
        if wanted_genres and (not genere or genere.strip().lower() not in wanted_genres):
```

con `from app.repositories import effective_genre` negli import del modulo.

- [ ] **Step 4: Test PASS + suite completa**

Run: `python -m pytest tests/test_library_effective_tags.py -v` → PASS.
Run: `python -m pytest tests -q 2>&1 | tail -5` → verde.

- [ ] **Step 5: Commit**

```bash
git add backend/app/repositories.py backend/app/services/candidate_engine.py backend/tests/test_library_effective_tags.py
git commit -m "feat(library): genres_overview e candidate engine sul genere effettivo"
```

---

### Task 4: Organize — `track_id` in `FileRow` (backend + tipo frontend)

**Files:**
- Modify: `backend/app/organize/schemas.py:271-293` (`FileRow`)
- Modify: `backend/app/organize/routers/library.py:72-81` (`_file_row`)
- Modify: `frontend/lib/organize/api.ts:51-72` (`FileRow`)
- Test: `backend/tests/organize/test_files_filters.py` (estendere: è il test esistente della lista file)

**Interfaces:**
- Produces: `FileRow.track_id: int | null` in API e tipo TS — consumato dal Task 7.

- [ ] **Step 1: Test failing** — in coda a `backend/tests/organize/test_files_filters.py` (stesso stile di `_seed`: `client` è il `TestClient(app)` a livello di modulo, il DB è quello condiviso del conftest radice):

```python
def test_filerow_espone_track_id(db):
    from app.models import Track

    root = ScanRoot(path="/m2")
    db.add(root)
    db.flush()
    t = Track(source_type="spotify", title="T", artist="A")
    db.add(t)
    db.flush()
    db.add_all([
        AudioFile(root_id=root.id, path="/m2/linked.mp3", ext="mp3", size_bytes=1,
                  hash_method="file", status="present", title="Linked", track_id=t.id),
        AudioFile(root_id=root.id, path="/m2/loose.mp3", ext="mp3", size_bytes=1,
                  hash_method="file", status="present", title="Loose"),
    ])
    db.commit()
    rows = client.get("/api/organize/files").json()
    linked = next(r for r in rows if r["title"] == "Linked")
    loose = next(r for r in rows if r["title"] == "Loose")
    assert linked["track_id"] == t.id
    assert loose["track_id"] is None
```

- [ ] **Step 2: FAIL** — `python -m pytest tests/organize/test_files_filters.py -v` → il nuovo test fallisce (`FileRow has no attribute track_id`).

- [ ] **Step 3: Implementare**

`schemas.py`, in `FileRow` dopo `ext: str`:

```python
    # Traccia agganciata (per il cross-link "apri traccia" dalla pagina FILES).
    track_id: int | None = None
```

`library.py`, in `_file_row` aggiungere nel costruttore:

```python
        track_id=f.track_id,
```

`frontend/lib/organize/api.ts`, in `FileRow` dopo `ext: string;`:

```typescript
  track_id: number | null;
```

- [ ] **Step 4: PASS** — `python -m pytest tests/organize -q 2>&1 | tail -3` → verde. Frontend: `cd frontend && npm run lint` → pulito.

- [ ] **Step 5: Commit**

```bash
git add backend/app/organize/schemas.py backend/app/organize/routers/library.py frontend/lib/organize/api.ts backend/tests/organize/test_files_filters.py
git commit -m "feat(organize): FileRow espone track_id per il cross-link verso la traccia"
```

---

### Task 5: Frontend — tipi + TrackEditModal a doppio percorso

**Files:**
- Modify: `frontend/lib/api/types.ts:1-35,176` (`Track`, `TrackDetail`)
- Modify: `frontend/components/track-edit-modal.tsx`
- Modify: `frontend/lib/i18n/it.ts` e `frontend/lib/i18n/en.ts` (chiavi sotto `tracks.`)
- Test: `frontend/tests/track-edit-modal.test.tsx` (nuovo)

**Interfaces:**
- Consumes: `Track.primary_file_id` + flags (Task 2 via API), `updateFileTags(fileId, changes)` da `@/lib/organize/api`.
- Produces: modal che salva genre/album/label/year sul file quando `track.primary_file_id != null`, il resto sulla `Track`; dopo il salvataggio ri-fetch di `/api/tracks/{id}` e `onSaved(fresh)`.

- [ ] **Step 1: Aggiornare i tipi (necessari al test per compilare)**

`frontend/lib/api/types.ts` — in `Track` dopo `local_bitrate`:

```typescript
  primary_file_id: number | null;
  genre_from_file: boolean;
  album_from_file: boolean;
  label_from_file: boolean;
  year_from_file: boolean;
```

Sostituire la riga 176:

```typescript
export interface TrackDetail extends Track {
  file_artist: string | null;
  file_title: string | null;
}
```

Poi `npm run lint`: se altri punti costruiscono oggetti `Track` letterali
(mock nei test, fixture), aggiungere i nuovi campi lì dove il type-check li
richiede (i test esistenti che usano `Partial<Track>` o cast non si toccano).

- [ ] **Step 2: Test failing**

Creare `frontend/tests/track-edit-modal.test.tsx`:

```tsx
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/api", async (importOriginal) => {
  const mod = await importOriginal<Record<string, unknown>>();
  return {
    ...mod,
    updateTrack: vi.fn().mockResolvedValue({}),
    apiGet: vi.fn().mockResolvedValue({ id: 1 }),
    trackCoverSrc: () => null,
  };
});
vi.mock("@/lib/organize/api", () => ({
  updateFileTags: vi.fn().mockResolvedValue({}),
}));

import { apiGet, updateTrack } from "@/lib/api";
import { updateFileTags } from "@/lib/organize/api";
import { TrackEditModal } from "@/components/track-edit-modal";

function makeTrack(overrides: Record<string, unknown> = {}) {
  return {
    id: 1, title: "T", artist: "A", album: null, genre: "Pop", year: 2001,
    bpm: 128, camelot_key: "8A", label: null, rating: null,
    primary_file_id: null, genre_from_file: false, album_from_file: false,
    label_from_file: false, year_from_file: false,
    playlists: [], has_local_file: false, spotify_id: null, soundcloud_id: null,
    source_type: "spotify", platform: null, duration_seconds: 300, energy: null,
    status: "ready_for_set", url: null, isrc: null, added_at: null,
    playlist_added_at: null, spotify_url: null, album_art_url: null,
    local_path: null, local_format: null, local_bitrate: null, archived: false,
    last_download_outcome: null, last_download_reason: null, last_download_path: null,
    ...overrides,
  } as never;
}

afterEach(() => { cleanup(); vi.clearAllMocks(); });

describe("TrackEditModal — routing del salvataggio", () => {
  it("traccia posseduta: genre va sul file via Organize, non sulla Track", async () => {
    render(<TrackEditModal track={makeTrack({ primary_file_id: 42 })} open
                           onClose={() => {}} onSaved={() => {}} />);
    fireEvent.change(screen.getByDisplayValue("Pop"), { target: { value: "Techno" } });
    fireEvent.submit(document.getElementById("track-edit-form")!);
    await waitFor(() => expect(updateFileTags).toHaveBeenCalledWith(42, { genre: "Techno" }));
    expect(updateTrack).not.toHaveBeenCalled();
    expect(apiGet).toHaveBeenCalledWith("/api/tracks/1"); // refresh degli effettivi
  });

  it("traccia posseduta: bpm resta sulla Track", async () => {
    render(<TrackEditModal track={makeTrack({ primary_file_id: 42 })} open
                           onClose={() => {}} onSaved={() => {}} />);
    fireEvent.change(screen.getByDisplayValue("128"), { target: { value: "130" } });
    fireEvent.submit(document.getElementById("track-edit-form")!);
    await waitFor(() => expect(updateTrack).toHaveBeenCalledWith(1, { bpm: 130 }));
    expect(updateFileTags).not.toHaveBeenCalled();
  });

  it("lead senza file: genre va sulla Track come oggi", async () => {
    render(<TrackEditModal track={makeTrack()} open
                           onClose={() => {}} onSaved={() => {}} />);
    fireEvent.change(screen.getByDisplayValue("Pop"), { target: { value: "House" } });
    fireEvent.submit(document.getElementById("track-edit-form")!);
    await waitFor(() => expect(updateTrack).toHaveBeenCalledWith(1, { genre: "House" }));
    expect(updateFileTags).not.toHaveBeenCalled();
  });
});
```

Run: `cd frontend && npx vitest run tests/track-edit-modal.test.tsx`
Expected: FAIL (il modal non importa `updateFileTags`, salva tutto su `updateTrack`).

- [ ] **Step 3: Implementare il modal**

`frontend/components/track-edit-modal.tsx`:

1. Import: `import { apiGet, updateTrack, type Track, type TrackUpdate } from "@/lib/api";` e `import { updateFileTags, type EditableTags } from "@/lib/organize/api";`
2. Aggiungere il campo album: in `FIELD_KEYS` inserire `"album"` dopo `"artist"`; in `buildFields` dopo la riga artist:

```typescript
    { key: "album", label: "Album", type: "text", full: true },
```

3. Costante a livello di modulo:

```typescript
// Campi descrittivi: su una traccia posseduta scrivono i TAG DEL FILE via
// l'endpoint Organize (single writer); sul lead restano campi della Track.
const FILE_FIELDS = new Set<Key>(["genre", "album", "label", "year"]);
```

4. Riscrivere `save()`:

```typescript
  async function save() {
    if (camelotInvalid) return;
    const toFile = track.primary_file_id != null;
    const trackPatch: TrackUpdate = {};
    const filePatch: Partial<EditableTags> = {};
    for (const { key, type } of FIELDS) {
      const raw = form[key].trim();
      if (raw === initial[key].trim()) continue; // invia solo i campi cambiati
      if (toFile && FILE_FIELDS.has(key)) {
        (filePatch as Record<string, string>)[key] = raw; // "" svuota il tag
      } else if (raw === "") {
        (trackPatch as Record<string, unknown>)[key] = null;
      } else if (type === "text") {
        (trackPatch as Record<string, unknown>)[key] = key === "camelot_key" ? raw.toUpperCase() : raw;
      } else {
        (trackPatch as Record<string, unknown>)[key] = Number(raw);
      }
    }
    if (Object.keys(trackPatch).length === 0 && Object.keys(filePatch).length === 0) { onClose(); return; }
    setBusy(true);
    setError(null);
    // Due percorsi di scrittura indipendenti: l'errore di uno non deve
    // mascherare l'esito dell'altro.
    const errors: string[] = [];
    if (Object.keys(filePatch).length > 0) {
      try { await updateFileTags(track.primary_file_id!, filePatch); }
      catch (e) { errors.push(`${t.tracks.fileTagsErrorPrefix}: ${String((e as Error).message ?? e)}`); }
    }
    if (Object.keys(trackPatch).length > 0) {
      try { await updateTrack(track.id, trackPatch); }
      catch (e) { errors.push(`${t.tracks.trackErrorPrefix}: ${String((e as Error).message ?? e)}`); }
    }
    try {
      // Ricarica gli effettivi (il salvataggio file risponde un FileRow, non una Track).
      onSaved(await apiGet<Track>(`/api/tracks/${track.id}`));
    } catch { /* la lista si riallineerà da sola al prossimo load */ }
    setBusy(false);
    if (errors.length > 0) setError(errors.join(" — "));
    else onClose();
  }
```

5. Nota sotto `manualValuesHint` (riga ~119):

```tsx
      {track.primary_file_id != null && (
        <p className="-mt-2 mb-4 text-xs text-muted">{t.tracks.fileTagsHint}</p>
      )}
```

6. i18n — `frontend/lib/i18n/it.ts` sotto `tracks.` (vicino a `manualValuesHint`):

```typescript
    fileTagsHint: "Genere, album, etichetta e anno scrivono i tag del file collegato (via Organize). Gli altri campi restano nel database di Cratory.",
    fileTagsErrorPrefix: "Tag file",
    trackErrorPrefix: "Traccia",
```

`frontend/lib/i18n/en.ts` stesse chiavi:

```typescript
    fileTagsHint: "Genre, album, label and year write the linked file's tags (via Organize). The other fields stay in Cratory's database.",
    fileTagsErrorPrefix: "File tags",
    trackErrorPrefix: "Track",
```

- [ ] **Step 4: PASS**

Run: `npx vitest run tests/track-edit-modal.test.tsx` → PASS (3 test).
Run: `npm run test:unit` → tutta verde. `npm run lint` → pulito.

- [ ] **Step 5: Commit**

```bash
git add frontend/lib/api/types.ts frontend/components/track-edit-modal.tsx frontend/lib/i18n/it.ts frontend/lib/i18n/en.ts frontend/tests/track-edit-modal.test.tsx
git commit -m "feat(library): TrackEditModal a doppio percorso — i campi descrittivi scrivono i tag del file via Organize"
```

---

### Task 6: Frontend — dettaglio traccia: provenienza, artist/title del file, link a Organize

**Files:**
- Modify: `frontend/app/tracks/[id]/page.tsx`
- Modify: `frontend/lib/i18n/it.ts`, `frontend/lib/i18n/en.ts`

**Interfaces:**
- Consumes: `TrackDetail.file_artist/file_title` + flags `*_from_file` (Task 2/5), chiavi i18n nuove.

- [ ] **Step 1: Implementare** (pagina già coperta solo da e2e smoke: niente unit test nuovo; la verifica è browser + e2e esistenti)

In `frontend/app/tracks/[id]/page.tsx`:

1. Import `cn`: `import { cn } from "@/lib/cn";`
2. Prima dell'array `rows` (riga ~91):

```tsx
  const fromFile = (v: React.ReactNode, flag: boolean) =>
    flag ? (
      <span className="inline-flex items-center gap-2">
        {v}
        <Badge tone="neutral">{t.tracks.fromFile}</Badge>
      </span>
    ) : v;
```

3. Nell'array `rows` sostituire le quattro voci descrittive:

```tsx
    ["Album", fromFile(track.album ?? "—", track.album_from_file)],
    [t.tracks.rowGenre, fromFile(track.genre ?? "—", track.genre_from_file)],
    [t.tracks.rowYear, fromFile(track.year ?? "—", track.year_from_file)],
    ...
    [t.tracks.rowLabel, fromFile(track.label ?? "—", track.label_from_file)],
```

(le altre voci dell'array restano al loro posto e nell'ordine attuale.)

4. Sopra il `return`, i confronti identità/file:

```tsx
  const norm = (s: string | null) => (s ?? "").trim().toLowerCase();
  const fileArtistMismatch = track.file_artist != null && norm(track.file_artist) !== norm(track.artist);
  const fileTitleMismatch = track.file_title != null && norm(track.file_title) !== norm(track.title);
```

5. Nella tabella della card disco, dopo la riga `local_format` (riga ~205):

```tsx
              {track.file_artist != null && (
                <tr className="border-b border-border/50 last:border-0">
                  <td className="px-4 py-2 text-muted">{t.tracks.rowFileArtist}</td>
                  <td className={cn("px-4 py-2 text-right", fileArtistMismatch && "text-warning")}
                      title={fileArtistMismatch ? t.tracks.fileMismatchTitle : undefined}>
                    {track.file_artist}{fileArtistMismatch ? " ⚠" : ""}
                  </td>
                </tr>
              )}
              {track.file_title != null && (
                <tr className="border-b border-border/50 last:border-0">
                  <td className="px-4 py-2 text-muted">{t.tracks.rowFileTitle}</td>
                  <td className={cn("px-4 py-2 text-right", fileTitleMismatch && "text-warning")}
                      title={fileTitleMismatch ? t.tracks.fileMismatchTitle : undefined}>
                    {track.file_title}{fileTitleMismatch ? " ⚠" : ""}
                  </td>
                </tr>
              )}
```

6. Nelle azioni della card disco (accanto al bottone `linkFile`, riga ~171):

```tsx
                {track.has_local_file && track.local_path && (
                  <Link href={`/organize/files?q=${encodeURIComponent(track.local_path)}`} className="inline-flex">
                    <Button size="sm" variant="outline"><ExternalLink size={14} /> {t.tracks.openInOrganize}</Button>
                  </Link>
                )}
```

7. i18n — `it.ts` sotto `tracks.`:

```typescript
    fromFile: "dal file",
    rowFileArtist: "Artista (file)",
    rowFileTitle: "Titolo (file)",
    fileMismatchTitle: "Diverso dall'identità della traccia",
    openInOrganize: "Apri in Organize",
```

`en.ts`:

```typescript
    fromFile: "from file",
    rowFileArtist: "Artist (file)",
    rowFileTitle: "Title (file)",
    fileMismatchTitle: "Differs from the track identity",
    openInOrganize: "Open in Organize",
```

- [ ] **Step 2: Verifica**

Run: `npm run lint && npm run test:unit` → verdi.
Verifica visiva col dev server (preview): aprire il dettaglio di una traccia
posseduta con tag file → badge "dal file" sui campi coperti dal tag, righe
Artista/Titolo (file), link "Apri in Organize" che porta a
`/organize/files?q=<path>`; su un lead senza file la pagina è identica a prima.

- [ ] **Step 3: Commit**

```bash
git add "frontend/app/tracks/[id]/page.tsx" frontend/lib/i18n/it.ts frontend/lib/i18n/en.ts
git commit -m "feat(tracks): dettaglio con provenienza dal file, artist/title del file e link a Organize"
```

---

### Task 7: Frontend — Files: `?q=` iniziale dall'URL e link "apri traccia"

**Files:**
- Modify: `frontend/app/organize/files/page.tsx`
- Modify: `frontend/components/organize/files-table.tsx`
- Modify: `frontend/lib/i18n/it.ts`, `frontend/lib/i18n/en.ts` (chiave sotto `organize.files.`)

**Interfaces:**
- Consumes: `FileRow.track_id` (Task 4); il link del Task 6 arriva qui con `?q=<path>`.

- [ ] **Step 1: Implementare**

`frontend/app/organize/files/page.tsx`:

1. Import: aggiungere `Suspense` a quelli di react e `useSearchParams` da `next/navigation`.
2. Nello stato (riga ~61), inizializzare `q` dall'URL:

```tsx
  // Il cross-link dal dettaglio traccia arriva con ?q=<path del file>.
  const searchParams = useSearchParams();
  const [q, setQ] = useState(() => searchParams.get("q") ?? "");
```

3. `useSearchParams` in Next 16 richiede un boundary Suspense: rinominare
`export default function FilesPage()` in `function FilesInner()` e aggiungere
in coda al file:

```tsx
export default function FilesPage() {
  return <Suspense><FilesInner /></Suspense>;
}
```

`frontend/components/organize/files-table.tsx`:

1. Import: `import Link from "next/link";` e l'icona `import { ExternalLink } from "lucide-react";`
2. Nell'header, dopo la colonna `!`:

```tsx
            <th className="w-8 px-3 py-2" aria-label="track" />
```

3. Nel body, dopo la cella `<Indicator />`:

```tsx
              <td className="px-3 py-1 text-center">
                {r.track_id != null && (
                  <Link
                    href={`/tracks/${r.track_id}`}
                    onClick={(e) => e.stopPropagation()} // la riga apre l'editor tag
                    className="text-faint hover:text-fg"
                    title={t.organize.files.openTrack}
                  >
                    <ExternalLink size={13} />
                  </Link>
                )}
              </td>
```

`FilesTable` non usa ancora `useT` nel corpo principale: aggiungere
`const t = useT();` in cima al componente `FilesTable` (l'hook è già
importato nel file per `Indicator`).

4. i18n — `it.ts` sotto `organize.files.`:

```typescript
    openTrack: "Apri la traccia in libreria",
```

`en.ts`:

```typescript
    openTrack: "Open the track in the library",
```

- [ ] **Step 2: Verifica**

Run: `npm run lint && npm run test:unit && npm run build` → verdi (il build
conferma il boundary Suspense richiesto da Next 16).
Verifica visiva: `/organize/files?q=nomefile` apre FILES già filtrata; l'icona
sulla riga di un file agganciato porta al dettaglio traccia; il click sul
resto della riga apre ancora l'editor tag.

- [ ] **Step 3: Commit**

```bash
git add frontend/app/organize/files/page.tsx frontend/components/organize/files-table.tsx frontend/lib/i18n/it.ts frontend/lib/i18n/en.ts
git commit -m "feat(organize): FILES filtrabile via ?q= e link apri-traccia sulle righe agganciate"
```

---

### Task 8: Documentazione

**Files:**
- Modify: `docs/API.md` (sezione tracks: nuovi campi payload; sezione organize: `FileRow.track_id`)
- Modify: `PROGRESS.md` (voce di diario in coda, data 2026-08-13)
- Modify: `docs/ROADMAP.md` (solo se la feature era a backlog: spuntarla; altrimenti non toccare)

- [ ] **Step 1: docs/API.md** — nella sezione di `GET /api/tracks` e `GET /api/tracks/{id}` documentare:
  - `genre`/`album`/`label`/`year` portano il valore EFFETTIVO (tag del primary file se non-NULL, fallback sul valore streaming);
  - nuovi campi: `primary_file_id`, `genre_from_file`, `album_from_file`, `label_from_file`, `year_from_file`; nel solo dettaglio `file_artist`, `file_title`;
  - filtri `genre`/`album`/`label`, sort `genre`/`year` e `GET /api/library/genres` lavorano sul valore effettivo;
  - la modifica dei quattro campi per tracce possedute passa da `POST /api/organize/files/{id}/tags` (nessun nuovo endpoint).
  Nella sezione organize: `FileRow.track_id`.

- [ ] **Step 2: PROGRESS.md** — voce sintetica: cosa (tag effettivi in Library, edit dal modal via Organize, cross-link), dove (repositories/serializers/schemas/routers, modal, dettaglio, FILES), rimando alla spec.

- [ ] **Step 3: Verifica finale completa**

```bash
cd backend && source .venv/bin/activate && python -m pytest tests -q 2>&1 | tail -3
cd ../frontend && npm run lint && npm run test:unit && npm run build
```

Tutto verde prima del commit.

- [ ] **Step 4: Commit**

```bash
git add docs/API.md PROGRESS.md docs/ROADMAP.md
git commit -m "docs: tag effettivi dal file in Library (payload, filtri, cross-link)"
```
