# Lotto B — Stato "Scartata" e Dettagli Disco — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Le tracce archiviate da DJPlayer diventano "scartate" in Cratory (fuori da wishlist/discovery/download, filtro dedicato in Libreria default off) e la pagina traccia mostra i dati del file su disco.

**Architecture:** Nuovo campo `Track.archived` + setting `ARCHIVE_ROOT`. `index_library` accetta `archive_root` e, dopo la Libreria, scansiona l'archivio con lo stesso meccanismo incrementale: file matchato ⇒ `archived=True`, `has_local_file=False`, `local_path` al file in archivio. Un file che ricompare in Libreria viene ri-posseduto (`archived=False` in `_own`). Le query di wishlist/lista escludono le scartate di default.

**Tech Stack:** Python/FastAPI + SQLAlchemy + pytest; Next.js 16 (`npm run build` come verifica frontend). Spec: `~/Develop/docs/superpowers/specs/2026-07-02-metadati-stati-automazioni-design.md` (Lotto B). **Prerequisito: Lotto A mergiato** (usa lo skip incrementale e `local_mtime`/`local_size`).

## Global Constraints

- Repo: `/Users/lucadenegri/Develop/DJProject01`, branch dedicato. Commenti in italiano.
- Test backend: `cd /Users/lucadenegri/Develop/DJProject01/backend && .venv/bin/python -m pytest tests/ -q`. Frontend: `cd frontend && npm run build`.
- Pattern test indice: fixture `fake_audio` (vedi `tests/test_library_index_incremental.py` dal Lotto A).
- Path reali utente: archivio = `/Users/lucadenegri/Music/Archived`, inbox = `/Users/lucadenegri/Music/Downloads`.

---

### Task 1: Campo `Track.archived` + setting `ARCHIVE_ROOT`

**Files:**
- Modify: `backend/app/models.py` (blocco campi locali Track), `backend/app/db.py` (`additions["tracks"]`), `backend/app/core/config.py` (dopo `library_root`), `backend/.env.example`
- Test: `backend/tests/test_archived.py` (nuovo)

**Interfaces:**
- Produces: `Track.archived: bool` (default False, server_default "0"); `settings.archive_root: str` (default ""). Usati dai Task 2-4.

- [ ] **Step 1: Test che fallisce** — crea `backend/tests/test_archived.py`:

```python
"""Stato 'scartata': Track.archived e setting ARCHIVE_ROOT."""
from app.core.config import Settings
from app.models import Track


def test_archived_default_false(db):
    t = Track(source_type="manual", title="T", artist="A")
    db.add(t); db.commit(); db.refresh(t)
    assert t.archived is False


def test_archive_root_default_vuoto():
    s = Settings(_env_file=None)
    assert s.archive_root == ""
```

- [ ] **Step 2: Verifica FAIL** — `cd backend && .venv/bin/python -m pytest tests/test_archived.py -v` → errori attributo mancante.

- [ ] **Step 3: Implementa** — in `models.py` dopo `local_size` (Lotto A):

```python
    # Scartata: il file e' finito nell'archivio (PASSED in DJPlayer). Esclusa da
    # wishlist/discovery/download; il possesso in Libreria la riabilita.
    archived: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0", index=True)
```

In `db.py`, `additions["tracks"]`: `"archived": "BOOLEAN DEFAULT 0",`
In `config.py` dopo `library_root`:

```python
    # Archivio delle scartate (PASSED di DJPlayer). Vuoto = riconoscimento disattivo.
    archive_root: str = ""
```

In `.env.example` dopo `LIBRARY_ROOT=`:

```
# Archivio delle tracce scartate (ARCHIVE_DIR di DJPlayer). Vuoto = disattivo.
ARCHIVE_ROOT=
```

- [ ] **Step 4: Verifica PASS + suite** — `pytest tests/test_archived.py -v && pytest tests/ -q`
- [ ] **Step 5: Commit** — `git add backend/app/models.py backend/app/db.py backend/app/core/config.py backend/.env.example backend/tests/test_archived.py && git commit -m "feat: Track.archived e setting ARCHIVE_ROOT"`

---

### Task 2: L'indice riconosce l'archivio

**Files:**
- Modify: `backend/app/services/library_index.py` (`index_library`, `_own`), `backend/app/services/library_index_job.py` (passa `archive_root`, chiave `archived` nello stato), `backend/app/schemas.py` (`LibraryIndexJobStatus.archived`)
- Test: `backend/tests/test_archived.py` (aggiunte)

**Interfaces:**
- Consumes: skip incrementale e `fake_audio` dal Lotto A.
- Produces: `index_library(db, *, root, archive_root=None, on_progress=None)` con chiave report `archived: int` (file d'archivio riconosciuti in questo run). Semantica: match per hash/digest/ISRC/fuzzy come la Libreria, ma l'esito è `archived=True, has_local_file=False, local_path=<path archivio>`; `_own` (Libreria) forza `archived=False`.

- [ ] **Step 1: Test che falliscono** — in coda a `tests/test_archived.py` (riusa la fixture `fake_audio` copiandola da `test_library_index_incremental.py` in testa al file):

```python
def test_file_in_archivio_scarta_la_traccia(db, fake_audio):
    from app.models import Track
    from app.services.library_index import index_library

    make, root = fake_audio
    lib = root / "Libreria"; arc = root / "Archived"
    lib.mkdir(); arc.mkdir()
    t = Track(source_type="spotify", spotify_id="s1", title="T", artist="A",
              has_local_file=True, local_path="/inbox/vecchio.mp3", audio_hash="H1")
    db.add(t); db.commit()

    make("Archived/A - T.mp3", digest="H1")
    report = index_library(db, root=lib, archive_root=arc)

    db.refresh(t)
    assert report["archived"] == 1
    assert t.archived is True and t.has_local_file is False
    assert t.local_path.endswith("Archived/A - T.mp3")


def test_ritorno_in_libreria_riabilita(db, fake_audio):
    from app.models import Track
    from app.services.library_index import index_library

    make, root = fake_audio
    lib = root / "Libreria"; arc = root / "Archived"
    lib.mkdir(); arc.mkdir()
    t = Track(source_type="spotify", spotify_id="s1", title="T", artist="A",
              archived=True, audio_hash="H1")
    db.add(t); db.commit()

    make("Libreria/Techno/A - T.mp3", digest="H1")
    index_library(db, root=lib, archive_root=arc)

    db.refresh(t)
    assert t.archived is False and t.has_local_file is True


def test_archivio_non_configurato_o_assente_neutro(db, fake_audio):
    from app.services.library_index import index_library

    make, root = fake_audio
    lib = root / "Libreria"; lib.mkdir()
    r1 = index_library(db, root=lib)                          # senza archive_root
    r2 = index_library(db, root=lib, archive_root=root / "non-esiste")
    assert r1["archived"] == 0 and r2["archived"] == 0


def test_archivio_incrementale_niente_rehash(db, fake_audio, monkeypatch):
    from app.services import library_index as li
    from app.services.library_index import index_library

    make, root = fake_audio
    lib = root / "Libreria"; arc = root / "Archived"
    lib.mkdir(); arc.mkdir()
    make("Archived/A - T.mp3", digest="H1", artist="A", title="T")
    index_library(db, root=lib, archive_root=arc)  # primo run: hash + scarto

    calls = []
    original = li.audio_hash
    monkeypatch.setattr(li, "audio_hash", lambda p: calls.append(p) or original(p))
    report = index_library(db, root=lib, archive_root=arc)
    assert calls == [] and report["unchanged"] >= 1
```

- [ ] **Step 2: Verifica FAIL** — `pytest tests/test_archived.py -v` → `TypeError: index_library() got an unexpected keyword argument 'archive_root'`.

- [ ] **Step 3: Implementa** — in `library_index.py`:

`_own` forza il rientro dallo scarto (ultima riga in più):

```python
def _own(track: Track, *, path: Path, digest: str) -> None:
    quality = read_audio_quality(path)
    stat = path.stat()
    track.local_path = str(path.resolve())
    track.has_local_file = True
    track.local_format = quality["format"]
    track.local_bitrate = quality["bitrate"]
    track.audio_hash = digest
    track.local_mtime = stat.st_mtime
    track.local_size = stat.st_size
    track.archived = False  # il possesso in Libreria vince sullo scarto
```

Nuova funzione `_discard` (dopo `_own`):

```python
def _discard(track: Track, *, path: Path, digest: str) -> None:
    """Il file vive nell'archivio: traccia scartata, non posseduta.

    local_path punta al file in archivio (si sa dov'e' finita); mtime/size
    servono allo skip incrementale anche per l'archivio.
    """
    stat = path.stat()
    track.archived = True
    track.has_local_file = False
    track.local_path = str(path.resolve())
    track.local_format = None
    track.local_bitrate = None
    track.audio_hash = digest
    track.local_mtime = stat.st_mtime
    track.local_size = stat.st_size
```

`index_library` — firma e struttura. Rifattorizza il corpo del loop attuale in una funzione interna parametrizzata sull'esito, così Libreria e archivio condividono skip incrementale, hash, dedup e match:

```python
def index_library(db: Session, *, root: str | Path,
                  archive_root: str | Path | None = None, on_progress=None) -> dict:
    """Indicizza la libreria canonica e (se configurato) l'archivio delle scartate."""
    files = scan_folder(root)
    archive_files: list[Path] = []
    if archive_root and Path(archive_root).is_dir():
        archive_files = scan_folder(archive_root)
    total = len(files) + len(archive_files)
    report = {"scanned": len(files), "matched": 0, "created": 0,
              "relinked": 0, "duplicates": 0, "lost": 0, "failed": 0,
              "unchanged": 0, "archived": 0, "errors": []}
    seen_paths: set[str] = set()
    seen_digests: set[str] = set()

    def _process(path: Path, i: int, *, in_archive: bool) -> None:
        # Incrementale: path noto con mtime+size invariati => niente ri-hash.
        resolved = str(path.resolve())
        stat = path.stat()
        known = db.scalar(select(Track).where(Track.local_path == resolved))
        if (known is not None and known.local_mtime == stat.st_mtime
                and known.local_size == stat.st_size):
            report["unchanged"] += 1
            seen_paths.add(resolved)
            if known.audio_hash:
                seen_digests.add(known.audio_hash)
            if on_progress is not None:
                on_progress(i, total)
            return
        try:
            digest = audio_hash(path)
        except LocalFilesError as exc:
            report["failed"] += 1
            report["errors"].append({"path": str(path), "error": str(exc)})
            logger.warning("File saltato %s: %s", path, exc)
            return
        if digest in seen_digests:
            report["duplicates"] += 1
            logger.warning("Audio duplicato nello stesso run: %s (digest gia' visto)", path)
            if on_progress is not None:
                on_progress(i, total)
            return
        seen_digests.add(digest)
        tags = read_tags(path)
        track, how = _find_track(db, digest=digest, tags=tags)
        if in_archive:
            # In archivio non si creano tracce nuove: un file mai visto da
            # Cratory che scarti non e' una wishlist da ricordare.
            if track is not None:
                _fill_identity(track, tags, path)
                _discard(track, path=path, digest=digest)
                refresh_status(track)
                report["archived"] += 1
                seen_paths.add(resolved)
            if on_progress is not None:
                on_progress(i, total)
            return
        if track is None:
            track = Track(source_type=PLATFORM, platform=PLATFORM, platform_track_id=digest)
            db.add(track)
            report["created"] += 1
        else:
            report["matched"] += 1
            if track.local_path != resolved:
                report["relinked"] += 1
        _fill_identity(track, tags, path)
        _own(track, path=path, digest=digest)
        refresh_status(track)
        seen_paths.add(resolved)
        if on_progress is not None:
            on_progress(i, total)

    for i, path in enumerate(files, start=1):
        _process(path, i, in_archive=False)
    for j, path in enumerate(archive_files, start=len(files) + 1):
        _process(path, j, in_archive=True)
```

La riconciliazione esistente resta INVARIATA (itera i posseduti: le scartate hanno `has_local_file=False` e non vengono toccate); il guard anti-unmount resta su `if not files:` (la sola Libreria vuota blocca, l'archivio vuoto no). ATTENZIONE: preserva il commento anti-unmount e il `db.commit()` finale.

In `library_index_job.py`: `_run_job` chiama `index_library(db, root=root, archive_root=settings.archive_root or None, on_progress=on_progress)`; aggiungi `"archived"` alle chiavi di `_state`, alle due tuple copiate dal report e al reset in `start_job` (stesso pattern di `unchanged` nel Lotto A).

In `schemas.py`, `LibraryIndexJobStatus`: `archived: int = 0`.

- [ ] **Step 4: Verifica PASS + suite** — `pytest tests/test_archived.py tests/test_library_index.py tests/test_library_index_incremental.py -v && pytest tests/ -q` (i test esistenti dell'indice non devono cambiare esito: `archive_root` è opzionale).
- [ ] **Step 5: Commit** — `git commit -m "feat: l'indice riconosce l'archivio e scarta le tracce (archived)"`

---

### Task 3: Esclusione delle scartate da wishlist, download e pipeline

**Files:**
- Modify: `backend/app/repositories.py` (`_apply_track_filters` riga ~71, `tracks_without_local_file` riga ~315), `backend/app/routers/tracks.py` (param `archived` su GET /tracks, riga ~30), `backend/app/services/pipeline.py` (conteggio wishlist), `backend/app/schemas.py` (`TrackOut.archived`), `backend/app/serializers.py` (se `track_out` elenca i campi a mano, aggiungi `archived`)
- Test: `backend/tests/test_archived.py` (aggiunte)

**Interfaces:**
- Consumes: `Track.archived` dal Task 1.
- Produces: `list_tracks(..., archived: bool = False)` — default esclude le scartate, `archived=True` mostra SOLO le scartate; `tracks_without_local_file` esclude le scartate (coda download); `pipeline_snapshot`: `wishlist` esclude le scartate e nuova chiave `archived_count: int`. `TrackOut.archived: bool`.

- [ ] **Step 1: Test che falliscono** — in coda a `tests/test_archived.py`:

```python
def _mk(db, i, **kw):
    from app.models import Track
    t = Track(source_type="spotify", spotify_id=f"x{i}", platform_track_id=f"x{i}",
              title=f"T{i}", artist=f"A{i}", **kw)
    db.add(t); db.commit()
    return t


def test_lista_esclude_scartate_di_default(db):
    from app.repositories import list_tracks
    _mk(db, 1)
    _mk(db, 2, archived=True)
    total, rows = list_tracks(db)
    assert total == 1 and rows[0].title == "T1"
    total, rows = list_tracks(db, archived=True)
    assert total == 1 and rows[0].title == "T2"


def test_coda_download_esclude_scartate(db):
    from app.models import Playlist, playlist_tracks
    from app.repositories import tracks_without_local_file
    p = Playlist(spotify_id="pl1", name="P"); db.add(p); db.commit()
    t1 = _mk(db, 1)
    t2 = _mk(db, 2, archived=True)
    db.execute(playlist_tracks.insert().values([
        {"playlist_id": p.id, "track_id": t1.id},
        {"playlist_id": p.id, "track_id": t2.id}]))
    db.commit()
    assert [t.id for t in tracks_without_local_file(db, p.id)] == [t1.id]


def test_pipeline_wishlist_esclude_scartate(db, monkeypatch):
    from app.core.config import settings
    from app.services.pipeline import pipeline_snapshot
    monkeypatch.setattr(settings, "slskd_download_dir", "")
    monkeypatch.setattr(settings, "library_root", "")
    monkeypatch.setattr(settings, "organizer_url", "")
    _mk(db, 1)
    _mk(db, 2, archived=True)
    snap = pipeline_snapshot(db)
    assert snap["wishlist"] == 1
    assert snap["archived_count"] == 1
```

(NOTA per il costruttore `Playlist`: verificare i campi obbligatori reali in `models.py` e adeguare `_mk`/il test — es. `name` e `spotify_id`.)

- [ ] **Step 2: Verifica FAIL** — `pytest tests/test_archived.py -v`.

- [ ] **Step 3: Implementa**

`repositories.py` — `_apply_track_filters`: aggiungi il parametro `archived: bool = False` alla firma e, come PRIMA clausola del corpo:

```python
    # Scartate: fuori da ogni vista di default; archived=True le mostra da sole.
    stmt = (stmt.where(Track.archived.is_(True)) if archived
            else stmt.where(Track.archived.is_not(True)))
```

`tracks_without_local_file`: aggiungi `.where(Track.archived.is_not(True))` dopo il filtro has_local_file.

`routers/tracks.py` — GET /tracks: parametro `archived: bool = False` passato a `list_tracks`.

`services/pipeline.py` — nel dict di ritorno:

```python
        "wishlist": count(Track.archived.is_not(True),
                          (Track.has_local_file.is_(False)) | (Track.has_local_file.is_(None))),
        "archived_count": count(Track.archived.is_(True)),
```

(sostituisce `"wishlist": total - with_local_file`; aggiorna `PipelineOut` in `schemas.py` con `archived_count: int = 0` e il tipo `PipelineStatus` in `frontend/lib/api.ts` con `archived_count: number;`).

`schemas.py` — `TrackOut`: `archived: bool = False`. `serializers.py`: verifica come `track_out` costruisce l'output (se usa `model_validate`/campi espliciti, aggiungi `archived=track.archived`).

Discovery: NESSUNA modifica — `_drop_in_library` scarta i candidati che matchano QUALUNQUE Track esistente (anche scartata), quindi le scartate non vengono ri-proposte già oggi. Aggiungi solo questo test di guardia in `tests/test_archived.py`:

```python
def test_discovery_non_ripropone_scartate(db):
    from app.services.discovery import _drop_in_library, _key
    t = _mk(db, 1, archived=True)
    candidates = {_key(t.artist, t.title): object()}
    assert _drop_in_library(candidates, [t]) == []
```

(verificare la firma reale di `_drop_in_library`/`_key` in `services/discovery.py:200` e adeguare il test.)

- [ ] **Step 4: Verifica PASS + suite completa** — `pytest tests/ -q`.
- [ ] **Step 5: Commit** — `git commit -m "feat: le scartate escono da lista, coda download e wishlist pipeline"`

---

### Task 4: Frontend — filtro "Scartate" e sezione "Disco" nel dettaglio

**Files:**
- Modify: `frontend/lib/api.ts` (`Track` type: `archived: boolean;` dopo `local_bitrate`), `frontend/app/library/page.tsx` (filtri, righe ~88-115 e fetch ~50-60), `frontend/app/tracks/[id]/page.tsx` (sezione dopo la card metadati, riga ~114)

**Interfaces:**
- Consumes: param `archived` di GET /api/tracks (Task 3); campi `local_*`/`archived` già nel tipo `Track`.
- Produces: UI. Nessun simbolo per altri task.

- [ ] **Step 1: Filtro in Libreria** — in `app/library/page.tsx`: nuovo state `const [archived, setArchived] = useState("");` e nel pannello filtri, dopo la Select "Possesso":

```tsx
<Select className="h-9" value={archived} onChange={(e) => { setArchived(e.target.value); setOffset(0); }}>
  <option value="">Scartate: nascoste</option>
  <option value="true">Solo scartate</option>
</Select>
```

Nella chiamata `apiGet` aggiungi `archived: archived || undefined,` e `archived` alle dipendenze del `useCallback`. Nella riga della tabella, accanto al badge FILE:

```tsx
{t.archived && <Badge tone="warning" className="ml-1">SCARTATA</Badge>}
```

(verificare i `tone` disponibili di `Badge` in `components/ui.tsx`; usare quello di avviso esistente.)

- [ ] **Step 2: Sezione "Disco" nel dettaglio** — in `app/tracks/[id]/page.tsx`, dopo la card metadati (riga ~114), nuova card:

```tsx
<Card>
  <div className="px-5 py-4">
    <div className="mb-3 text-[10px] font-semibold uppercase tracking-wider text-fg-strong">Disco</div>
    <table className="w-full text-sm">
      <tbody>
        <tr><td className="py-1 pr-4 text-muted">Stato</td><td>
          {track.has_local_file ? <Badge tone="success">Posseduta</Badge>
            : track.archived ? <Badge tone="warning">Scartata</Badge>
            : <Badge tone="neutral">Senza file</Badge>}
        </td></tr>
        {track.local_path && <tr><td className="py-1 pr-4 text-muted">File</td><td className="break-all font-mono text-xs">{track.local_path}</td></tr>}
        {track.local_format && <tr><td className="py-1 pr-4 text-muted">Formato</td><td>{track.local_format.toUpperCase()}{track.local_bitrate ? ` · ${track.local_bitrate} kbps` : ""}</td></tr>}
      </tbody>
    </table>
  </div>
</Card>
```

(adattare markup/classi alla card metadati esistente nella stessa pagina — righe 102-114 — per coerenza visiva; import `Badge` se manca.)

- [ ] **Step 3: Verifica** — `cd frontend && npm run build` verde; visiva: dettaglio traccia posseduta mostra path/formato; filtro Libreria di default non mostra scartate.
- [ ] **Step 4: Commit** — `git commit -m "feat: filtro Scartate in Libreria e sezione Disco nel dettaglio traccia"`

---

### Task 5: Configurazione ambienti reali

**Files:**
- Modify: `/Users/lucadenegri/Develop/DJProject01/backend/.env` (aggiungi riga), `/Users/lucadenegri/Develop/DJPlayer01/.env` (correggi 2 righe)

**Interfaces:** nessuna (solo config).

- [ ] **Step 1:** In `DJProject01/backend/.env` aggiungi:

```
ARCHIVE_ROOT=/Users/lucadenegri/Music/Archived
```

- [ ] **Step 2:** In `DJPlayer01/.env` sostituisci i valori scratchpad con:

```
MUSIC_DIR=/Users/lucadenegri/Music/Downloads
ARCHIVE_DIR=/Users/lucadenegri/Music/Archived
```

- [ ] **Step 3: Smoke test** — riavvia il backend Cratory e verifica che `GET /api/pipeline` risponda e che una scansione (`POST /api/library/index`) riporti `archived` ≥ 0 senza errori. I file `.env` NON si committano (sono ignorati): nessun commit.
