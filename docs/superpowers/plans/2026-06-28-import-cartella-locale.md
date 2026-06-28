# Import playlist da cartella locale — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Aggiungere una nuova sorgente di import — una cartella del filesystem locale — che legge i tag dei file audio, ne calcola un'identità via hash audio e crea una playlist, riusando la pipeline di import esistente.

**Architecture:** Modulo locale isolato (lettura tag + hash via ffmpeg) che produce `NormalizedTrack` e li passa a `import_playlist()` generalizzato. L'import gira come job in background con progresso pollabile (modello `enrichment_job.py`). Il frontend ha un file-browser servito dal backend, confinato a una root configurabile.

**Tech Stack:** Python 3 + FastAPI + SQLAlchemy (SQLite), `mutagen` (lettura tag), ffmpeg di sistema (già usato dal modulo Shazam), Next.js 16 + React + Tailwind.

## Global Constraints

- **Non si conservano file audio.** L'import legge solo tag e calcola un hash; non copia/sposta/conserva l'audio. Il path è un riferimento volatile.
- **BPM/key non si inventano e non si sovrascrivono.** L'import locale NON deriva feature di mixing dall'audio; BPM/key arrivano dalla catena di enrichment esistente. Si riusa `_apply_fields` (riempie-solo-vuoti). L'unico campo sovrascritto deliberatamente è `local_path`.
- **`source_type` / `platform` = `"local_files"`** (NON `"local"`: `db.py` riserva `"local"` come sorgente legacy Rekordbox in `_LEGACY_SOURCES` e la cancella nel rebuild legacy).
- **Identità traccia locale = hash dello stream audio**, primi ~60s decodificati (`platform_track_id = audio_hash`).
- **Una cartella ricorsiva = una playlist** col nome della cartella.
- **Convenzioni codice:** commenti/docstring in italiano come nel resto del backend; niente Alembic (migrazioni idempotenti in `db.py`); i test chiamano le funzioni dei router direttamente col fixture `db` (niente TestClient); commit message senza `Co-Authored-By`.
- **Estensioni audio (v1):** `.mp3 .flac .m4a .aac .aiff .aif .wav .ogg .opus .wma`.
- **Frontend:** prima di toccare pagine/routing leggere `frontend/CLAUDE.md` e i doc in `node_modules/next/dist/docs/` (Next.js 16, breaking changes).

---

### Task 1: Lettore file locali (`integrations/local_files.py`)

Lettura tag con `mutagen` e hash dello stream audio con ffmpeg. Modulo puro, senza DB.

**Files:**
- Modify: `backend/requirements.txt` (aggiungi `mutagen`)
- Create: `backend/app/integrations/local_files.py`
- Test: `backend/tests/test_local_files.py`

**Interfaces:**
- Produces:
  - `AUDIO_EXTENSIONS: set[str]` — estensioni minuscole con punto.
  - `read_tags(path: str | Path) -> dict` — chiavi `{"title","artist","album","year","duration_seconds","isrc"}`, valori `str|int|None`.
  - `audio_hash(path: str | Path, *, seconds: int = 60) -> str` — SHA-256 hex dei primi `seconds` di audio decodificato mono 22050 Hz s16le.
  - `class LocalFilesError(Exception)` — ffmpeg assente o decodifica fallita.

- [ ] **Step 1: Aggiungi la dipendenza**

In `backend/requirements.txt`, dopo la riga `shazamio>=0.5`, aggiungi:

```
mutagen>=1.47
```

Installa nel venv: `cd backend && source .venv/bin/activate && pip install "mutagen>=1.47"`

- [ ] **Step 2: Scrivi i test (falliscono)**

Create `backend/tests/test_local_files.py`:

```python
"""Lettura tag + hash audio dei file locali (integrations/local_files.py).

I file di test sono WAV generati con la stdlib (nessun encoder esterno). I tag ID3
vengono scritti via mutagen.wave.WAVE: ffmpeg decodifica solo lo stream audio, quindi
l'hash resta stabile anche dopo aver modificato i tag.
"""

import math
import struct
import wave

import pytest

from app.integrations.local_files import (
    AUDIO_EXTENSIONS,
    LocalFilesError,
    audio_hash,
    read_tags,
)


def _write_wav(path, *, freq: int = 440, secs: float = 1.0, rate: int = 22050) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        frames = b"".join(
            struct.pack("<h", int(30000 * math.sin(2 * math.pi * freq * i / rate)))
            for i in range(int(rate * secs))
        )
        w.writeframes(frames)


def _tag_wav(path, *, title=None, artist=None, album=None, date=None, isrc=None) -> None:
    from mutagen.id3 import TALB, TDRC, TIT2, TPE1, TSRC
    from mutagen.wave import WAVE

    w = WAVE(str(path))
    if w.tags is None:
        w.add_tags()
    if title:
        w.tags.add(TIT2(encoding=3, text=[title]))
    if artist:
        w.tags.add(TPE1(encoding=3, text=[artist]))
    if album:
        w.tags.add(TALB(encoding=3, text=[album]))
    if date:
        w.tags.add(TDRC(encoding=3, text=[date]))
    if isrc:
        w.tags.add(TSRC(encoding=3, text=[isrc]))
    w.save()


def test_audio_hash_deterministico(tmp_path):
    p = tmp_path / "a.wav"
    _write_wav(p, freq=440)
    assert audio_hash(p) == audio_hash(p)


def test_audio_hash_diverso_per_audio_diverso(tmp_path):
    a = tmp_path / "a.wav"
    b = tmp_path / "b.wav"
    _write_wav(a, freq=440)
    _write_wav(b, freq=880)
    assert audio_hash(a) != audio_hash(b)


def test_audio_hash_stabile_dopo_modifica_tag(tmp_path):
    p = tmp_path / "a.wav"
    _write_wav(p, freq=440)
    before = audio_hash(p)
    _tag_wav(p, title="Nuovo", artist="Tizio")
    assert audio_hash(p) == before  # i tag non entrano nell'hash dell'audio


def test_read_tags_legge_id3(tmp_path):
    p = tmp_path / "a.wav"
    _write_wav(p, secs=1.0)
    _tag_wav(p, title="Da Funk", artist="Daft Punk", album="Homework", date="1997", isrc="FRZ129700001")
    tags = read_tags(p)
    assert tags["title"] == "Da Funk"
    assert tags["artist"] == "Daft Punk"
    assert tags["album"] == "Homework"
    assert tags["year"] == 1997
    assert tags["isrc"] == "FRZ129700001"
    assert tags["duration_seconds"] == 1


def test_read_tags_file_senza_tag(tmp_path):
    p = tmp_path / "a.wav"
    _write_wav(p, secs=1.0)
    tags = read_tags(p)
    assert tags["title"] is None
    assert tags["artist"] is None
    assert tags["duration_seconds"] == 1


def test_audio_extensions_minuscole_con_punto():
    assert ".mp3" in AUDIO_EXTENSIONS
    assert ".flac" in AUDIO_EXTENSIONS
    assert all(e.startswith(".") and e == e.lower() for e in AUDIO_EXTENSIONS)


def test_audio_hash_su_file_non_audio_solleva(tmp_path):
    p = tmp_path / "x.wav"
    p.write_bytes(b"non audio")
    with pytest.raises(LocalFilesError):
        audio_hash(p)
```

- [ ] **Step 3: Esegui i test (devono fallire)**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_local_files.py -v`
Expected: FAIL con `ModuleNotFoundError: app.integrations.local_files`

- [ ] **Step 4: Implementa il modulo**

Create `backend/app/integrations/local_files.py`:

```python
"""Lettura metadati e identità dei file audio locali.

Modulo puro (nessun DB): legge i tag con mutagen e calcola un hash dello stream
audio decodificato con ffmpeg (già richiesto dal modulo Shazam). L'hash ignora i
tag, quindi è stabile a rinomine/spostamenti e a correzioni dei metadati.

L'app NON conserva l'audio: qui si legge soltanto. Le feature di mixing (BPM/key)
NON si derivano dall'audio, restano alla catena di enrichment esterna.
"""

import hashlib
import logging
import subprocess
from pathlib import Path

import mutagen

logger = logging.getLogger(__name__)

AUDIO_EXTENSIONS = {
    ".mp3", ".flac", ".m4a", ".aac", ".aiff", ".aif", ".wav", ".ogg", ".opus", ".wma",
}

HASH_SECONDS = 60


class LocalFilesError(Exception):
    """ffmpeg assente o impossibile decodificare/leggere il file."""


def _id3_text(tags, frame: str) -> str | None:
    f = tags.get(frame)
    if f is not None and getattr(f, "text", None):
        return str(f.text[0])
    return None


def read_tags(path: str | Path) -> dict:
    """Legge i tag principali. Valori assenti -> None. Non solleva su file taggati male."""
    out = {"title": None, "artist": None, "album": None, "year": None,
           "duration_seconds": None, "isrc": None}
    try:
        audio = mutagen.File(str(path))
    except Exception as exc:  # noqa: BLE001 — file corrotto/illeggibile: tag vuoti, non fatale
        logger.warning("Tag illeggibili da %s: %s", path, exc)
        return out
    if audio is None:
        return out
    if audio.info is not None and getattr(audio.info, "length", None):
        out["duration_seconds"] = int(audio.info.length)
    tags = getattr(audio, "tags", None)
    if tags is None:
        return out
    date = None
    if hasattr(tags, "getall") and "TIT2" in tags or _id3_text_safe(tags, "TIT2") is not None:
        # ID3 (mp3 / wav con ID3)
        out["title"] = _id3_text(tags, "TIT2")
        out["artist"] = _id3_text(tags, "TPE1")
        out["album"] = _id3_text(tags, "TALB")
        out["isrc"] = _id3_text(tags, "TSRC")
        date = _id3_text(tags, "TDRC")
    else:
        # Vorbis comment (flac/ogg/opus): chiavi minuscole; MP4 (m4a): atom "©nam" ecc.
        def first(*keys: str):
            for k in keys:
                v = tags.get(k) or tags.get(k.upper())
                if v:
                    return str(v[0])
            return None

        out["title"] = first("title", "\xa9nam")
        out["artist"] = first("artist", "\xa9ART")
        out["album"] = first("album", "\xa9alb")
        out["isrc"] = first("isrc")  # MP4 tiene l'ISRC in atom freeform: non coperto in v1
        date = first("date", "\xa9day")
    if date and str(date)[:4].isdigit():
        out["year"] = int(str(date)[:4])
    return out


def _id3_text_safe(tags, frame: str) -> str | None:
    try:
        return _id3_text(tags, frame)
    except Exception:  # noqa: BLE001
        return None


def audio_hash(path: str | Path, *, seconds: int = HASH_SECONDS) -> str:
    """SHA-256 dei primi `seconds` di audio decodificato (mono 22050 Hz s16le).

    Solleva LocalFilesError se ffmpeg manca o non riesce a decodificare il file.
    """
    cmd = [
        "ffmpeg", "-v", "error", "-i", str(path),
        "-t", str(seconds), "-ac", "1", "-ar", "22050", "-f", "s16le", "-",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, check=True)
    except FileNotFoundError as exc:
        raise LocalFilesError("ffmpeg non trovato: necessario per l'hash audio dei file locali.") from exc
    except subprocess.CalledProcessError as exc:
        raise LocalFilesError(f"ffmpeg non ha potuto decodificare {path}") from exc
    if not proc.stdout:
        raise LocalFilesError(f"Nessuno stream audio decodificato da {path}")
    return hashlib.sha256(proc.stdout).hexdigest()
```

- [ ] **Step 5: Esegui i test (devono passare)**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_local_files.py -v`
Expected: PASS (tutti). Richiede `ffmpeg` nel PATH.

- [ ] **Step 6: Commit**

```bash
git add backend/requirements.txt backend/app/integrations/local_files.py backend/tests/test_local_files.py
git commit -m "feat(local-import): lettura tag e hash audio dei file locali"
```

---

### Task 2: Colonna `local_path` su Track + supporto in NormalizedTrack/_apply_fields

Persistenza del path locale: nuova colonna, migrazione idempotente, campo nel dataclass e overwrite-quando-presente in `_apply_fields`.

**Files:**
- Modify: `backend/app/models.py` (Track: aggiungi `local_path`)
- Modify: `backend/app/db.py` (`ensure_schema`: ALTER per `local_path`)
- Modify: `backend/app/services/playlist_import.py` (`NormalizedTrack.local_path` + `_apply_fields`)
- Test: `backend/tests/test_local_path_column.py`

**Interfaces:**
- Produces:
  - `Track.local_path: str | None` (colonna SQL `local_path VARCHAR`).
  - `NormalizedTrack.local_path: str | None = None` (nuovo campo, default None).
  - `_apply_fields` aggiorna `track.local_path = norm.local_path` quando `norm.local_path` è valorizzato (overwrite-quando-presente).

- [ ] **Step 1: Scrivi i test (falliscono)**

Create `backend/tests/test_local_path_column.py`:

```python
"""Colonna local_path: persistenza + overwrite-quando-presente in _apply_fields."""

from app.models import Playlist, Track
from app.services.playlist_import import NormalizedTrack, _apply_fields


def test_track_ha_local_path(db):
    t = Track(source_type="local_files", title="X", local_path="/music/x.flac")
    db.add(t)
    db.commit()
    db.refresh(t)
    assert t.local_path == "/music/x.flac"


def test_apply_fields_imposta_local_path(db):
    t = Track(source_type="local_files")
    norm = NormalizedTrack(
        platform="local_files", platform_track_id="h1", title="X", artist="Y",
        album=None, duration_seconds=None, url=None, artwork_url=None, isrc=None,
        added_at=None, local_path="/music/a.flac",
    )
    _apply_fields(t, norm)
    assert t.local_path == "/music/a.flac"


def test_apply_fields_aggiorna_local_path_su_spostamento(db):
    t = Track(source_type="local_files", local_path="/music/old.flac")
    norm = NormalizedTrack(
        platform="local_files", platform_track_id="h1", title="X", artist="Y",
        album=None, duration_seconds=None, url=None, artwork_url=None, isrc=None,
        added_at=None, local_path="/music/new.flac",
    )
    _apply_fields(t, norm)
    assert t.local_path == "/music/new.flac"  # sovrascritto deliberatamente


def test_apply_fields_non_tocca_local_path_se_norm_vuoto(db):
    t = Track(source_type="spotify", local_path="/music/keep.flac")
    norm = NormalizedTrack(
        platform="spotify", platform_track_id="s1", title="X", artist="Y",
        album=None, duration_seconds=None, url=None, artwork_url=None, isrc=None,
        added_at=None,  # local_path resta None
    )
    _apply_fields(t, norm)
    assert t.local_path == "/music/keep.flac"  # invariato: norm.local_path è None
```

- [ ] **Step 2: Esegui i test (devono fallire)**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_local_path_column.py -v`
Expected: FAIL (`AttributeError`/`TypeError`: `local_path` inesistente)

- [ ] **Step 3: Aggiungi la colonna al modello**

In `backend/app/models.py`, dentro `class Track`, dopo la riga `url: Mapped[str | None] = mapped_column(Text)` (riga 43), aggiungi:

```python
    # Path assoluto del file per le tracce locali (source_type="local_files"). Riferimento
    # volatile (non si conserva l'audio): aggiornato a ogni ri-scansione se il file si sposta.
    local_path: Mapped[str | None] = mapped_column(Text)
```

- [ ] **Step 4: Aggiungi la migrazione idempotente**

In `backend/app/db.py`, nel dizionario `additions["tracks"]`, aggiungi una voce (dopo `"url": "TEXT",`):

```python
            "local_path": "TEXT",
```

- [ ] **Step 5: Aggiungi il campo a NormalizedTrack e l'update in _apply_fields**

In `backend/app/services/playlist_import.py`, nel dataclass `NormalizedTrack`, dopo `album_id: str | None = None` (riga 40), aggiungi:

```python
    local_path: str | None = None
```

In `_apply_fields`, dopo la riga `track.added_at = track.added_at or norm.added_at` (riga 126), aggiungi:

```python
    # local_path: overwrite-quando-presente (solo i NormalizedTrack locali lo valorizzano),
    # così un file spostato/rinominato aggiorna il path pur mantenendo l'identità via hash.
    if norm.local_path:
        track.local_path = norm.local_path
```

- [ ] **Step 6: Esegui i test (devono passare)**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_local_path_column.py -v`
Expected: PASS

- [ ] **Step 7: Verifica nessuna regressione import**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_playlist_pivot.py tests/test_playlist_membership.py tests/test_manual_import.py -q`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add backend/app/models.py backend/app/db.py backend/app/services/playlist_import.py backend/tests/test_local_path_column.py
git commit -m "feat(local-import): colonna local_path e supporto in NormalizedTrack/_apply_fields"
```

---

### Task 3: Generalizzare `import_playlist` con un normalizzatore iniettabile

Oggi `import_playlist` è hardcoded a Spotify (riga 194 solleva; riga 220 usa `normalize_spotify_item`). Lo si generalizza con un parametro `normalize`, default Spotify, così il locale può passare item già normalizzati.

**Files:**
- Modify: `backend/app/services/playlist_import.py` (`import_playlist`)
- Test: `backend/tests/test_import_playlist_normalize.py`

**Interfaces:**
- Consumes: `NormalizedTrack` (Task 2).
- Produces:
  - `import_playlist(db, *, platform, name, items, normalize=normalize_spotify_item, platform_playlist_id=None, owner=None, url=None, artwork_url=None, kind="playlist", prune=False) -> dict`
  - `def identity_normalize(item: NormalizedTrack) -> NormalizedTrack` — passthrough per item già normalizzati.

- [ ] **Step 1: Scrivi i test (falliscono)**

Create `backend/tests/test_import_playlist_normalize.py`:

```python
"""import_playlist generalizzato: normalizzatore iniettabile + identità per item già pronti."""

from app.models import Playlist, Track
from app.services.playlist_import import (
    NormalizedTrack,
    identity_normalize,
    import_playlist,
)


def _norm(**kw) -> NormalizedTrack:
    base = dict(
        platform="local_files", platform_track_id=None, title=None, artist=None,
        album=None, duration_seconds=None, url=None, artwork_url=None, isrc=None,
        added_at=None,
    )
    base.update(kw)
    return NormalizedTrack(**base)


def test_importa_item_gia_normalizzati(db):
    items = [
        _norm(platform_track_id="h1", title="A", artist="X", local_path="/m/a.flac"),
        _norm(platform_track_id="h2", title="B", artist="Y", local_path="/m/b.flac"),
    ]
    report = import_playlist(
        db, platform="local_files", name="Crate", items=items, normalize=identity_normalize,
    )
    assert report["created"] == 2
    assert report["total"] == 2
    pl = db.get(Playlist, report["playlist_id"])
    assert pl.platform == "local_files"
    tracks = {t.title: t for t in db.query(Track).all()}
    assert tracks["A"].local_path == "/m/a.flac"
    assert tracks["A"].platform_track_id == "h1"


def test_dedup_per_platform_track_id(db):
    items = [_norm(platform_track_id="h1", title="A", artist="X", local_path="/m/a.flac")]
    import_playlist(db, platform="local_files", name="C1", items=items, normalize=identity_normalize)
    # stesso hash, path diverso (file spostato) -> aggiorna, non duplica
    items2 = [_norm(platform_track_id="h1", title="A", artist="X", local_path="/m/moved.flac")]
    report = import_playlist(db, platform="local_files", name="C2", items=items2, normalize=identity_normalize)
    assert report["created"] == 0
    assert report["updated"] == 1
    assert db.query(Track).count() == 1
    assert db.query(Track).first().local_path == "/m/moved.flac"


def test_spotify_resta_default(db):
    # item Spotify grezzo: il default normalize_spotify_item lo gestisce ancora.
    item = {
        "track": {
            "id": "sp1", "name": "Song", "duration_ms": 200000,
            "artists": [{"name": "Artist"}],
            "album": {"name": "Alb", "images": [], "release_date": "2020"},
            "external_ids": {"isrc": "US1234567890"},
            "external_urls": {"spotify": "http://x"},
        }
    }
    report = import_playlist(db, platform="spotify", name="P", items=[item])
    assert report["created"] == 1
```

- [ ] **Step 2: Esegui i test (devono fallire)**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_import_playlist_normalize.py -v`
Expected: FAIL (`identity_normalize` inesistente; `import_playlist` solleva per `platform != "spotify"`)

- [ ] **Step 3: Aggiungi `identity_normalize` e generalizza `import_playlist`**

In `backend/app/services/playlist_import.py`, dopo la definizione di `normalize_spotify_item` (dopo riga 87), aggiungi:

```python
def identity_normalize(item: NormalizedTrack) -> NormalizedTrack:
    """Passthrough per chi fornisce già NormalizedTrack (es. import locale)."""
    return item
```

Aggiungi l'import del tipo in cima (se non presente):

```python
from collections.abc import Callable
from typing import Any
```

Modifica la firma di `import_playlist` (riga 175-187): aggiungi il parametro `normalize` dopo `items`:

```python
def import_playlist(
    db: Session,
    *,
    platform: str,
    name: str,
    items: list,
    normalize: Callable[[Any], "NormalizedTrack | None"] = normalize_spotify_item,
    platform_playlist_id: str | None = None,
    owner: str | None = None,
    url: str | None = None,
    artwork_url: str | None = None,
    kind: str = "playlist",
    prune: bool = False,
) -> dict:
```

Rimuovi la guardia hardcoded (righe 194-195):

```python
    if platform != "spotify":
        raise ValueError(f"Piattaforma non supportata per l'import: {platform}")
```

Sostituisci la riga 220:

```python
        norm = normalize_spotify_item(item) if platform == "spotify" else None
```

con:

```python
        norm = normalize(item)
```

- [ ] **Step 4: Esegui i test (devono passare)**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_import_playlist_normalize.py -v`
Expected: PASS

- [ ] **Step 5: Verifica nessuna regressione (Spotify/sync/membership)**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_playlist_pivot.py tests/test_playlist_sync.py tests/test_playlist_membership.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/playlist_import.py backend/tests/test_import_playlist_normalize.py
git commit -m "refactor(import): import_playlist accetta un normalizzatore iniettabile"
```

---

### Task 4: Servizio di import locale (`services/local_import.py`)

Scansione cartella, costruzione `NormalizedTrack` (tag + fallback nome file + hash), orchestrazione su `import_playlist`.

**Files:**
- Create: `backend/app/services/local_import.py`
- Test: `backend/tests/test_local_import.py`

**Interfaces:**
- Consumes: `read_tags`, `audio_hash`, `AUDIO_EXTENSIONS`, `LocalFilesError` (Task 1); `import_playlist`, `identity_normalize`, `NormalizedTrack` (Task 3); `parse_line` da `manual_import`.
- Produces:
  - `scan_folder(path: str | Path, *, recurse: bool = True) -> list[Path]` — file audio ordinati.
  - `build_normalized(path: str | Path) -> NormalizedTrack` — può sollevare `LocalFilesError` (hash fallito).
  - `import_local_folder(db, *, path, name=None, recurse=True, on_progress=None) -> dict` — report `{playlist_id, name, created, updated, failed, total, errors}`. `on_progress(processed, total)` opzionale. `name` default = nome cartella.

- [ ] **Step 1: Scrivi i test (falliscono)**

Create `backend/tests/test_local_import.py`:

```python
"""Import da cartella locale: scansione, fallback nome file, idempotenza, separazione tracce."""

import math
import struct
import wave

import pytest

from app.models import Track
from app.services.local_import import import_local_folder, scan_folder


def _write_wav(path, *, freq: int = 440, secs: float = 0.5, rate: int = 22050) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        frames = b"".join(
            struct.pack("<h", int(30000 * math.sin(2 * math.pi * freq * i / rate)))
            for i in range(int(rate * secs))
        )
        w.writeframes(frames)


def _tag_wav(path, *, title=None, artist=None) -> None:
    from mutagen.id3 import TIT2, TPE1
    from mutagen.wave import WAVE

    w = WAVE(str(path))
    if w.tags is None:
        w.add_tags()
    if title:
        w.tags.add(TIT2(encoding=3, text=[title]))
    if artist:
        w.tags.add(TPE1(encoding=3, text=[artist]))
    w.save()


def test_scan_folder_ricorsivo_ignora_non_audio(tmp_path):
    _write_wav(tmp_path / "a.wav", freq=440)
    sub = tmp_path / "sub"
    sub.mkdir()
    _write_wav(sub / "b.wav", freq=660)
    (tmp_path / "note.txt").write_text("x")
    found = scan_folder(tmp_path, recurse=True)
    names = sorted(p.name for p in found)
    assert names == ["a.wav", "b.wav"]


def test_import_usa_fallback_nome_file(db, tmp_path):
    p = tmp_path / "Daft Punk - Da Funk.wav"
    _write_wav(p, freq=440)  # nessun tag
    report = import_local_folder(db, path=tmp_path, name="Crate")
    assert report["created"] == 1
    t = db.query(Track).first()
    assert t.artist == "Daft Punk"
    assert t.title == "Da Funk"
    assert t.source_type == "local_files"
    assert t.platform == "local_files"


def test_riscansione_idempotente(db, tmp_path):
    _write_wav(tmp_path / "a.wav", freq=440)
    _tag_wav(tmp_path / "a.wav", title="A", artist="X")
    r1 = import_local_folder(db, path=tmp_path, name="Crate")
    r2 = import_local_folder(db, path=tmp_path, name="Crate")
    assert r1["created"] == 1
    assert r2["created"] == 0
    assert r2["updated"] == 1
    assert db.query(Track).count() == 1


def test_file_rinominato_aggiorna_path_senza_duplicare(db, tmp_path):
    a = tmp_path / "a.wav"
    _write_wav(a, freq=440)
    _tag_wav(a, title="A", artist="X")
    import_local_folder(db, path=tmp_path, name="Crate")
    a.rename(tmp_path / "renamed.wav")  # stesso audio -> stesso hash
    import_local_folder(db, path=tmp_path, name="Crate")
    assert db.query(Track).count() == 1
    assert db.query(Track).first().local_path.endswith("renamed.wav")


def test_due_file_audio_diversi_stesso_nome_brano_due_tracce(db, tmp_path):
    a = tmp_path / "a.wav"
    b = tmp_path / "b.wav"
    _write_wav(a, freq=440)
    _write_wav(b, freq=880)  # audio diverso -> hash diverso
    _tag_wav(a, title="Stesso", artist="Brano")
    _tag_wav(b, title="Stesso", artist="Brano")
    report = import_local_folder(db, path=tmp_path, name="Crate")
    assert report["created"] == 2  # identità per hash, non per nome
    assert db.query(Track).count() == 2


def test_non_si_fonde_con_traccia_spotify_omonima(db, tmp_path):
    db.add(Track(source_type="spotify", platform="spotify", platform_track_id="sp1",
                 title="Da Funk", artist="Daft Punk"))
    db.commit()
    p = tmp_path / "x.wav"
    _write_wav(p, freq=440)
    _tag_wav(p, title="Da Funk", artist="Daft Punk")
    import_local_folder(db, path=tmp_path, name="Crate")
    assert db.query(Track).count() == 2  # crea una traccia locale distinta
    assert db.query(Track).filter_by(source_type="local_files").count() == 1
    assert db.query(Track).filter_by(source_type="spotify").count() == 1


def test_cartella_vuota_non_crea_playlist(db, tmp_path):
    report = import_local_folder(db, path=tmp_path, name="Vuota")
    assert report["total"] == 0
    assert report["playlist_id"] is None


def test_progress_callback_invocato(db, tmp_path):
    _write_wav(tmp_path / "a.wav", freq=440)
    _write_wav(tmp_path / "b.wav", freq=660)
    seen = []
    import_local_folder(db, path=tmp_path, name="Crate",
                        on_progress=lambda p, t: seen.append((p, t)))
    assert seen[-1] == (2, 2)
```

- [ ] **Step 2: Esegui i test (devono fallire)**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_local_import.py -v`
Expected: FAIL (`ModuleNotFoundError: app.services.local_import`)

- [ ] **Step 3: Implementa il servizio**

Create `backend/app/services/local_import.py`:

```python
"""Import di una cartella locale come playlist (specchio della collezione DJ).

Deterministico: scansiona i file audio, legge i tag (fallback dal nome file),
calcola l'identità via hash dello stream audio e riusa import_playlist. Non
conserva l'audio: tiene solo metadati e il path (riferimento volatile).

Le tracce locali restano SEPARATE da quelle streaming (nessuna fusione per nome):
l'identità è l'hash, non artista+titolo.
"""

import logging
import os
from pathlib import Path

from sqlalchemy.orm import Session

from app.integrations.local_files import (
    AUDIO_EXTENSIONS,
    LocalFilesError,
    audio_hash,
    read_tags,
)
from app.services.manual_import import parse_line
from app.services.playlist_import import (
    NormalizedTrack,
    identity_normalize,
    import_playlist,
)

logger = logging.getLogger(__name__)

PLATFORM = "local_files"


def scan_folder(path: str | Path, *, recurse: bool = True) -> list[Path]:
    """Elenco ordinato dei file audio sotto `path` (ricorsivo di default)."""
    root = Path(path)
    files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        for fn in filenames:
            if Path(fn).suffix.lower() in AUDIO_EXTENSIONS:
                files.append(Path(dirpath) / fn)
        if not recurse:
            dirnames.clear()
    return sorted(files)


def build_normalized(path: str | Path) -> NormalizedTrack:
    """Costruisce un NormalizedTrack da un file. Solleva LocalFilesError se l'hash fallisce."""
    p = Path(path)
    tags = read_tags(p)
    artist, title = tags["artist"], tags["title"]
    if not artist or not title:
        # Fallback dal nome file ("Artista - Titolo"), stesso parser dell'import manuale.
        parsed = parse_line(p.stem)
        if parsed is not None:
            fb_artist, fb_title = parsed
            artist = artist or fb_artist
            title = title or fb_title
    digest = audio_hash(p)  # può sollevare LocalFilesError
    return NormalizedTrack(
        platform=PLATFORM,
        platform_track_id=digest,
        title=title,
        artist=artist,
        album=tags["album"],
        duration_seconds=tags["duration_seconds"],
        url=None,
        artwork_url=None,
        isrc=tags["isrc"],
        added_at=None,
        year=tags["year"],
        local_path=str(p.resolve()),
    )


def import_local_folder(
    db: Session,
    *,
    path: str | Path,
    name: str | None = None,
    recurse: bool = True,
    on_progress=None,
) -> dict:
    """Importa una cartella come playlist. Ritorna report con created/updated/failed/errors.

    La fase pesante (tag + hash) è qui: on_progress(processed, total) viene chiamato per
    file. La playlist si crea solo se almeno una traccia è stata normalizzata (total>0).
    """
    root = Path(path)
    playlist_name = name or root.name or "Cartella locale"
    files = scan_folder(root, recurse=recurse)
    total = len(files)

    items: list[NormalizedTrack] = []
    failed = 0
    errors: list[dict] = []
    for i, f in enumerate(files, start=1):
        try:
            items.append(build_normalized(f))
        except LocalFilesError as exc:
            failed += 1
            errors.append({"path": str(f), "error": str(exc)})
            logger.warning("File locale saltato %s: %s", f, exc)
        if on_progress is not None:
            on_progress(i, total)

    if not items:
        return {
            "playlist_id": None, "name": playlist_name, "created": 0, "updated": 0,
            "removed": 0, "skipped": 0, "failed": failed, "total": 0, "errors": errors,
        }

    report = import_playlist(
        db, platform=PLATFORM, name=playlist_name, items=items,
        normalize=identity_normalize, kind="local",
    )
    report["failed"] = failed
    report["errors"] = errors
    return report
```

- [ ] **Step 4: Esegui i test (devono passare)**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_local_import.py -v`
Expected: PASS (tutti)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/local_import.py backend/tests/test_local_import.py
git commit -m "feat(local-import): servizio di scansione e import cartella locale"
```

---

### Task 5: Config root + file-browser confinato (`services/fs_browse.py`)

Setting `local_import_root` e navigazione filesystem confinata alla root (anti `../` e symlink).

**Files:**
- Modify: `backend/app/core/config.py` (setting `local_import_root`)
- Create: `backend/app/services/fs_browse.py`
- Test: `backend/tests/test_fs_browse.py`

**Interfaces:**
- Produces:
  - `resolve_import_root() -> Path` — `settings.local_import_root` se valorizzato, altrimenti `Path.home()`, risolto con `.resolve()`.
  - `class FsBrowseError(Exception)` — path fuori root o inesistente.
  - `browse(path: str | None, *, root: Path) -> dict` — `{"current_path","parent_path","dirs":[{"name","path","audio_file_count"}]}`. `path=None` → contenuto di `root`. Solleva `FsBrowseError` se il path risolto è fuori da `root` o non è una directory.

- [ ] **Step 1: Scrivi i test (falliscono)**

Create `backend/tests/test_fs_browse.py`:

```python
"""File-browser confinato alla root: elenco sottocartelle, blocco fuori-root."""

import pytest

from app.services.fs_browse import FsBrowseError, browse


def test_browse_elenca_sottocartelle_e_conta_audio(tmp_path):
    (tmp_path / "house").mkdir()
    (tmp_path / "techno").mkdir()
    (tmp_path / "house" / "a.mp3").write_bytes(b"x")
    (tmp_path / "house" / "b.flac").write_bytes(b"x")
    (tmp_path / "house" / "cover.jpg").write_bytes(b"x")
    res = browse(None, root=tmp_path)
    by_name = {d["name"]: d for d in res["dirs"]}
    assert set(by_name) == {"house", "techno"}
    assert by_name["house"]["audio_file_count"] == 2
    assert by_name["techno"]["audio_file_count"] == 0
    assert res["parent_path"] is None  # alla root non si sale


def test_browse_naviga_in_sottocartella(tmp_path):
    sub = tmp_path / "house"
    sub.mkdir()
    (sub / "deep").mkdir()
    res = browse(str(sub), root=tmp_path)
    assert res["current_path"] == str(sub.resolve())
    assert res["parent_path"] == str(tmp_path.resolve())
    assert [d["name"] for d in res["dirs"]] == ["deep"]


def test_browse_blocca_path_fuori_root(tmp_path):
    outside = tmp_path.parent
    with pytest.raises(FsBrowseError):
        browse(str(outside), root=tmp_path / "sub")


def test_browse_blocca_traversal(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    with pytest.raises(FsBrowseError):
        browse(str(root / ".." / ".."), root=root)


def test_browse_blocca_symlink_fuori_root(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    secret = tmp_path / "secret"
    secret.mkdir()
    link = root / "link"
    link.symlink_to(secret)
    with pytest.raises(FsBrowseError):
        browse(str(link), root=root)


def test_browse_path_inesistente_solleva(tmp_path):
    with pytest.raises(FsBrowseError):
        browse(str(tmp_path / "nope"), root=tmp_path)
```

- [ ] **Step 2: Esegui i test (devono fallire)**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_fs_browse.py -v`
Expected: FAIL (`ModuleNotFoundError: app.services.fs_browse`)

- [ ] **Step 3: Aggiungi il setting**

In `backend/app/core/config.py`, dentro `class Settings`, dopo `log_level: str = "INFO"` (riga 20), aggiungi:

```python
    # Import da cartella locale: radice consentita per il file-browser (vuoto = home utente).
    local_import_root: str = ""
```

- [ ] **Step 4: Implementa il browser**

Create `backend/app/services/fs_browse.py`:

```python
"""Navigazione filesystem confinata a una root, per scegliere la cartella da importare.

App mono-utente locale: il browser non risolve mai un path sopra `local_import_root`
(default: home utente). Protegge da traversal (`..`) e symlink che escono dalla root.
"""

from pathlib import Path

from app.core.config import settings
from app.integrations.local_files import AUDIO_EXTENSIONS


class FsBrowseError(Exception):
    """Path fuori dalla root consentita, inesistente o non una directory."""


def resolve_import_root() -> Path:
    raw = settings.local_import_root.strip()
    return (Path(raw) if raw else Path.home()).resolve()


def _is_within(child: Path, root: Path) -> bool:
    try:
        child.relative_to(root)
        return True
    except ValueError:
        return False


def _audio_count(directory: Path) -> int:
    n = 0
    try:
        for entry in directory.iterdir():
            if entry.is_file() and entry.suffix.lower() in AUDIO_EXTENSIONS:
                n += 1
    except OSError:
        return 0
    return n


def browse(path: str | None, *, root: Path) -> dict:
    """Elenca le sottocartelle di `path` (o della root). Confina dentro `root`."""
    root = root.resolve()
    target = root if not path else Path(path)
    try:
        target = target.resolve()
    except OSError as exc:
        raise FsBrowseError(f"Path non risolvibile: {path}") from exc
    if not _is_within(target, root):
        raise FsBrowseError("Percorso fuori dalla cartella consentita.")
    if not target.is_dir():
        raise FsBrowseError(f"Non è una cartella: {target}")

    dirs = []
    for entry in sorted(target.iterdir(), key=lambda p: p.name.lower()):
        if entry.is_dir() and _is_within(entry.resolve(), root):
            dirs.append({
                "name": entry.name,
                "path": str(entry.resolve()),
                "audio_file_count": _audio_count(entry),
            })
    parent = target.parent.resolve()
    parent_path = str(parent) if target != root and _is_within(parent, root) else None
    return {"current_path": str(target), "parent_path": parent_path, "dirs": dirs}
```

- [ ] **Step 5: Esegui i test (devono passare)**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_fs_browse.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/core/config.py backend/app/services/fs_browse.py backend/tests/test_fs_browse.py
git commit -m "feat(local-import): file-browser confinato a local_import_root"
```

---

### Task 6: Job in background (`services/local_import_job.py`)

Stato in memoria con lock, un job alla volta; a fine import chiama l'auto-enrichment.

**Files:**
- Create: `backend/app/services/local_import_job.py`
- Test: `backend/tests/test_local_import_job.py`

**Interfaces:**
- Consumes: `import_local_folder` (Task 4); `enrichment_job.start_job` (auto-enrichment).
- Produces:
  - `job_state() -> dict` — snapshot `{status, processed, total, created, updated, failed, playlist_id, errors, error, started_at, finished_at}`.
  - `is_running() -> bool`
  - `start_job(*, path: str, name: str | None) -> dict` — avvia il thread, ritorna lo stato; se già running ritorna lo stato senza avviarne un altro.
  - `_run_job(path: str, name: str | None) -> None` — corpo sincrono (testabile).

- [ ] **Step 1: Scrivi i test (falliscono)**

Create `backend/tests/test_local_import_job.py`:

```python
"""Job di import locale: stato e contatori dopo l'esecuzione sincrona del corpo."""

import math
import struct
import wave

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.services import local_import_job


def _write_wav(path, *, freq: int = 440, secs: float = 0.4, rate: int = 22050) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"".join(
            struct.pack("<h", int(30000 * math.sin(2 * math.pi * freq * i / rate)))
            for i in range(int(rate * secs))
        ))


@pytest.fixture()
def patch_session(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(local_import_job, "SessionLocal", TestSession)
    # niente provider di enrichment nei test: rendi l'auto-enrichment un no-op
    monkeypatch.setattr(local_import_job, "_autoenrich", lambda pid: None)
    return TestSession


def test_run_job_popola_stato(patch_session, tmp_path):
    _write_wav(tmp_path / "a.wav", freq=440)
    _write_wav(tmp_path / "b.wav", freq=660)
    local_import_job._run_job(str(tmp_path), "Crate")
    st = local_import_job.job_state()
    assert st["status"] == "done"
    assert st["total"] == 2
    assert st["created"] == 2
    assert st["processed"] == 2
    assert st["playlist_id"] is not None


def test_run_job_cartella_vuota(patch_session, tmp_path):
    local_import_job._run_job(str(tmp_path), "Vuota")
    st = local_import_job.job_state()
    assert st["status"] == "done"
    assert st["total"] == 0
    assert st["playlist_id"] is None
```

- [ ] **Step 2: Esegui i test (devono fallire)**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_local_import_job.py -v`
Expected: FAIL (`ModuleNotFoundError: app.services.local_import_job`)

- [ ] **Step 3: Implementa il job**

Create `backend/app/services/local_import_job.py`:

```python
"""Job di import cartella locale in background.

App locale mono-utente: un solo job alla volta, stato in memoria con lock. La UI
lo avvia e poi fa polling di job_state() via /api/playlists/import-local/status.
La fase pesante (tag + hash) riporta il progresso processed/total.
"""

import logging
import threading
from datetime import datetime, timezone

from app.db import SessionLocal
from app.services.local_import import import_local_folder

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_state: dict = {
    "status": "idle",  # idle | running | done | error
    "processed": 0,
    "total": 0,
    "created": 0,
    "updated": 0,
    "failed": 0,
    "playlist_id": None,
    "errors": [],
    "error": None,
    "started_at": None,
    "finished_at": None,
}


def job_state() -> dict:
    return dict(_state)


def is_running() -> bool:
    return _state["status"] == "running"


def _autoenrich(playlist_id: int | None) -> None:
    """Avvia l'enrichment dopo l'import (best-effort: se non configurato, no-op)."""
    if playlist_id is None:
        return
    try:
        from app.integrations.getsongbpm import FeatureProviderNotConfigured
        from app.services import enrichment_job

        enrichment_job.start_job(playlist_id=playlist_id)
    except FeatureProviderNotConfigured:
        logger.info("Auto-enrichment saltato: nessun provider di feature configurato.")
    except Exception:  # noqa: BLE001
        logger.exception("Auto-enrichment post import locale fallito (non bloccante).")


def _run_job(path: str, name: str | None) -> None:
    db = SessionLocal()

    def on_progress(processed: int, total: int) -> None:
        _state.update(processed=processed, total=total)

    try:
        report = import_local_folder(db, path=path, name=name, on_progress=on_progress)
        _state.update(
            status="done",
            created=report.get("created", 0),
            updated=report.get("updated", 0),
            failed=report.get("failed", 0),
            playlist_id=report.get("playlist_id"),
            errors=report.get("errors", []),
            total=report.get("total", _state["total"]),
        )
        logger.info("Import locale completato: %s", {k: report.get(k) for k in
                    ("playlist_id", "created", "updated", "failed", "total")})
        _autoenrich(report.get("playlist_id"))
    except Exception as exc:  # noqa: BLE001
        _state.update(status="error", error=str(exc))
        logger.exception("Import locale fallito (inatteso)")
    finally:
        _state["finished_at"] = datetime.now(timezone.utc).isoformat()
        db.close()


def start_job(*, path: str, name: str | None = None) -> dict:
    """Avvia il job in background e ritorna subito lo stato. No-op se già in corso."""
    with _lock:
        if _state["status"] == "running":
            return job_state()
        _state.update(
            status="running", processed=0, total=0, created=0, updated=0, failed=0,
            playlist_id=None, errors=[], error=None,
            started_at=datetime.now(timezone.utc).isoformat(), finished_at=None,
        )
    threading.Thread(target=_run_job, args=(path, name), daemon=True).start()
    return job_state()
```

- [ ] **Step 4: Esegui i test (devono passare)**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_local_import_job.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/local_import_job.py backend/tests/test_local_import_job.py
git commit -m "feat(local-import): job in background con progresso e auto-enrichment"
```

---

### Task 7: Schemi + endpoint del router

Tre endpoint nel router playlist esistente: browse, avvio import, stato. Test chiamando le funzioni direttamente (stile del progetto).

**Files:**
- Modify: `backend/app/schemas.py` (nuovi schemi)
- Modify: `backend/app/routers/playlists.py` (import + 3 endpoint)
- Test: `backend/tests/test_local_import_router.py`

**Interfaces:**
- Consumes: `fs_browse.browse/resolve_import_root/FsBrowseError` (Task 5); `local_import_job` (Task 6).
- Produces (schemi Pydantic):
  - `LocalDirEntry{name:str, path:str, audio_file_count:int}`
  - `LocalBrowseResponse{current_path:str, parent_path:str|None, dirs:list[LocalDirEntry]}`
  - `LocalFolderImportRequest{path:str, name:str|None=None, recurse:bool=True}`
  - `LocalImportJobStatus{status:str, processed:int, total:int, created:int, updated:int, failed:int, playlist_id:int|None, errors:list[dict], error:str|None}`
- Produces (endpoint):
  - `GET /api/playlists/local/browse?path=` → `LocalBrowseResponse`
  - `POST /api/playlists/import-local` → `LocalImportJobStatus` (202)
  - `GET /api/playlists/import-local/status` → `LocalImportJobStatus`

- [ ] **Step 1: Scrivi i test (falliscono)**

Create `backend/tests/test_local_import_router.py`:

```python
"""Endpoint import locale: browse, avvio (validazione), stato. Chiamate dirette al router."""

from pathlib import Path

import pytest
from fastapi import HTTPException

from app.routers import playlists
from app.schemas import LocalFolderImportRequest
from app.services import local_import_job


def test_browse_ritorna_sottocartelle(tmp_path, monkeypatch):
    (tmp_path / "house").mkdir()
    monkeypatch.setattr(playlists, "resolve_import_root", lambda: tmp_path)
    res = playlists.browse_local_folder(path=str(tmp_path))
    assert [d.name for d in res.dirs] == ["house"]
    assert res.current_path == str(tmp_path.resolve())


def test_browse_fuori_root_400(tmp_path, monkeypatch):
    root = tmp_path / "root"
    root.mkdir()
    monkeypatch.setattr(playlists, "resolve_import_root", lambda: root)
    with pytest.raises(HTTPException) as ei:
        playlists.browse_local_folder(path=str(tmp_path))
    assert ei.value.status_code == 400


def test_import_local_path_inesistente_400(tmp_path, monkeypatch):
    monkeypatch.setattr(playlists, "resolve_import_root", lambda: tmp_path)
    req = LocalFolderImportRequest(path=str(tmp_path / "nope"))
    with pytest.raises(HTTPException) as ei:
        playlists.import_local_folder_endpoint(req)
    assert ei.value.status_code == 400


def test_import_local_avvia_job(tmp_path, monkeypatch):
    monkeypatch.setattr(playlists, "resolve_import_root", lambda: tmp_path)
    called = {}
    monkeypatch.setattr(local_import_job, "start_job",
                        lambda *, path, name: called.update(path=path, name=name) or local_import_job.job_state())
    monkeypatch.setattr(local_import_job, "is_running", lambda: False)
    req = LocalFolderImportRequest(path=str(tmp_path), name="Crate")
    res = playlists.import_local_folder_endpoint(req)
    assert called["path"] == str(tmp_path)
    assert res.status in {"idle", "running", "done", "error"}


def test_import_local_gia_in_corso_409(tmp_path, monkeypatch):
    monkeypatch.setattr(playlists, "resolve_import_root", lambda: tmp_path)
    monkeypatch.setattr(local_import_job, "is_running", lambda: True)
    req = LocalFolderImportRequest(path=str(tmp_path))
    with pytest.raises(HTTPException) as ei:
        playlists.import_local_folder_endpoint(req)
    assert ei.value.status_code == 409


def test_status_ritorna_stato(monkeypatch):
    monkeypatch.setattr(local_import_job, "job_state",
                        lambda: {"status": "done", "processed": 1, "total": 1, "created": 1,
                                 "updated": 0, "failed": 0, "playlist_id": 5, "errors": [],
                                 "error": None})
    res = playlists.local_import_status()
    assert res.status == "done"
    assert res.playlist_id == 5
```

- [ ] **Step 2: Esegui i test (devono fallire)**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_local_import_router.py -v`
Expected: FAIL (`ImportError`: schemi/funzioni inesistenti)

- [ ] **Step 3: Aggiungi gli schemi**

In `backend/app/schemas.py`, dopo `ManualImportRequest` (riga 283), aggiungi:

```python
class LocalDirEntry(BaseModel):
    name: str
    path: str
    audio_file_count: int = 0


class LocalBrowseResponse(BaseModel):
    current_path: str
    parent_path: str | None = None
    dirs: list[LocalDirEntry] = []


class LocalFolderImportRequest(BaseModel):
    path: str = Field(min_length=1)
    name: str | None = Field(default=None, max_length=200)
    recurse: bool = True


class LocalImportJobStatus(BaseModel):
    status: str
    processed: int = 0
    total: int = 0
    created: int = 0
    updated: int = 0
    failed: int = 0
    playlist_id: int | None = None
    errors: list[dict] = []
    error: str | None = None
```

- [ ] **Step 4: Aggiungi import ed endpoint al router**

In `backend/app/routers/playlists.py`, estendi gli import.

Negli schemi importati (blocco `from app.schemas import (` ... `)`, righe 31-42), aggiungi:

```python
    LocalBrowseResponse,
    LocalFolderImportRequest,
    LocalImportJobStatus,
```

Dopo gli import dei servizi (dopo riga 47), aggiungi:

```python
from app.services import local_import_job
from app.services.fs_browse import FsBrowseError, browse, resolve_import_root
```

In fondo agli endpoint del router (dopo `import_manual`, riga 179), aggiungi:

```python
@router.get("/local/browse", response_model=LocalBrowseResponse)
def browse_local_folder(path: str | None = None):
    """Naviga le sottocartelle sotto la root consentita, per scegliere cosa importare."""
    try:
        result = browse(path, root=resolve_import_root())
    except FsBrowseError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return LocalBrowseResponse(**result)


@router.post("/import-local", response_model=LocalImportJobStatus, status_code=202)
def import_local_folder_endpoint(req: LocalFolderImportRequest):
    """Avvia l'import di una cartella locale come job in background. 409 se già in corso."""
    if local_import_job.is_running():
        raise HTTPException(status_code=409, detail="Un import locale è già in corso.")
    try:
        target = browse(req.path, root=resolve_import_root())  # valida confinamento + esistenza
    except FsBrowseError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    state = local_import_job.start_job(path=target["current_path"], name=req.name)
    return LocalImportJobStatus(**state)


@router.get("/import-local/status", response_model=LocalImportJobStatus)
def local_import_status():
    """Stato corrente del job di import locale (per il polling della UI)."""
    return LocalImportJobStatus(**local_import_job.job_state())
```

Nota: l'endpoint `import-local` riusa `browse()` per validare path (confinamento + esistenza dir) prima di avviare il job; `current_path` è il path risolto.

- [ ] **Step 5: Esegui i test (devono passare)**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_local_import_router.py -v`
Expected: PASS

- [ ] **Step 6: Verifica la suite backend completa**

Run: `cd backend && source .venv/bin/activate && python -m pytest -q`
Expected: PASS (nessuna regressione). Richiede ffmpeg per i test locali.

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas.py backend/app/routers/playlists.py backend/tests/test_local_import_router.py
git commit -m "feat(local-import): endpoint browse, import-local e status"
```

---

### Task 8: Client API frontend (`lib/api.ts`)

Funzioni e tipi per browse, avvio import e polling stato.

**Files:**
- Modify: `frontend/lib/api.ts`

**Interfaces:**
- Consumes: endpoint del Task 7; `apiGet`, `apiPost` esistenti.
- Produces:
  - `interface LocalDirEntry{name; path; audio_file_count}`
  - `interface LocalBrowseResponse{current_path; parent_path; dirs}`
  - `interface LocalImportJobStatus{status; processed; total; created; updated; failed; playlist_id; errors; error}`
  - `browseLocalFolder(path?: string): Promise<LocalBrowseResponse>`
  - `startLocalImport(path: string, name?: string): Promise<LocalImportJobStatus>`
  - `localImportStatus(): Promise<LocalImportJobStatus>`

- [ ] **Step 1: Leggi la guida Next.js (vincolo di progetto)**

Run: `cat frontend/CLAUDE.md` e, se tocchi routing/pagine nei task successivi, sfoglia `frontend/node_modules/next/dist/docs/`. Questo task tocca solo `lib/api.ts` (nessun routing).

- [ ] **Step 2: Aggiungi tipi e funzioni**

In `frontend/lib/api.ts`, nella sezione `// --- Playlist (nuovo flusso) ---` (dopo `syncPlaylist`, riga 430), aggiungi:

```typescript
export interface LocalDirEntry {
  name: string;
  path: string;
  audio_file_count: number;
}

export interface LocalBrowseResponse {
  current_path: string;
  parent_path: string | null;
  dirs: LocalDirEntry[];
}

export interface LocalImportJobStatus {
  status: "idle" | "running" | "done" | "error";
  processed: number;
  total: number;
  created: number;
  updated: number;
  failed: number;
  playlist_id: number | null;
  errors: { path: string; error: string }[];
  error: string | null;
}

export function browseLocalFolder(path?: string) {
  return apiGet<LocalBrowseResponse>("/api/playlists/local/browse", { path });
}

export function startLocalImport(path: string, name?: string) {
  return apiPost<LocalImportJobStatus>("/api/playlists/import-local", { path, name });
}

export function localImportStatus() {
  return apiGet<LocalImportJobStatus>("/api/playlists/import-local/status");
}
```

- [ ] **Step 3: Verifica typecheck/lint**

Run: `cd frontend && npm run lint`
Expected: nessun errore nuovo in `lib/api.ts`.

- [ ] **Step 4: Commit**

```bash
git add frontend/lib/api.ts
git commit -m "feat(local-import): client API frontend per browse/import/status"
```

---

### Task 9: Pagina di import + CTA

Pagina `import-local` con file-browser, nome playlist, avvio e progresso; link dalla pagina playlist.

**Files:**
- Create: `frontend/app/playlists/import-local/page.tsx`
- Modify: `frontend/app/playlists/page.tsx` (CTA)

**Interfaces:**
- Consumes: `browseLocalFolder`, `startLocalImport`, `localImportStatus`, tipi del Task 8; componenti UI esistenti (`Card`, `CardHeader`, `Button`, `Alert`, `Spinner`, `Input`, `Field`, `PageLayout`).

- [ ] **Step 1: Leggi la guida Next.js (routing/pagine)**

Run: `cat frontend/CLAUDE.md`; consulta `frontend/node_modules/next/dist/docs/` per le convenzioni di `app/` (client components, `useRouter` da `next/navigation`). Replica i pattern di `frontend/app/playlists/import-manual/page.tsx` (già `"use client"`, `useRouter`, `PageLayout`, `Card`).

- [ ] **Step 2: Crea la pagina**

Create `frontend/app/playlists/import-local/page.tsx`:

```tsx
"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft, ArrowUp, Folder, HardDriveDownload } from "lucide-react";
import {
  browseLocalFolder,
  startLocalImport,
  localImportStatus,
  type LocalBrowseResponse,
  type LocalImportJobStatus,
} from "@/lib/api";
import { Card, CardHeader, Button, Alert, Spinner, Input, Field } from "@/components/ui";
import { PageLayout } from "@/components/page-layout";

function err(e: unknown): string {
  return String((e as { message?: string })?.message ?? e);
}

export default function ImportLocalPage() {
  const router = useRouter();
  const [view, setView] = useState<LocalBrowseResponse | null>(null);
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [job, setJob] = useState<LocalImportJobStatus | null>(null);

  const load = async (path?: string) => {
    setError(null);
    try {
      const res = await browseLocalFolder(path);
      setView(res);
      const segs = res.current_path.split(/[\\/]/).filter(Boolean);
      setName(segs[segs.length - 1] ?? "");
    } catch (e) {
      setError(`Navigazione fallita: ${err(e)}`);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  // Polling dello stato mentre il job è in corso.
  useEffect(() => {
    if (!job || job.status !== "running") return;
    const id = setInterval(async () => {
      try {
        const st = await localImportStatus();
        setJob(st);
        if (st.status === "done" && st.playlist_id) {
          clearInterval(id);
          router.push(`/playlists/${st.playlist_id}`);
        }
      } catch {
        /* ritenta al prossimo tick */
      }
    }, 1000);
    return () => clearInterval(id);
  }, [job, router]);

  const doImport = async () => {
    if (!view) return;
    setError(null);
    try {
      const st = await startLocalImport(view.current_path, name.trim() || undefined);
      setJob(st);
    } catch (e) {
      setError(`Import fallito: ${err(e)}`);
    }
  };

  const running = job?.status === "running";

  const marginalia = (
    <div className="space-y-2 text-xs leading-relaxed text-muted">
      <p>Scegli una cartella: i file audio (anche nelle sottocartelle) entrano in una sola playlist.</p>
      <p>Si leggono solo i <span className="text-fg">tag</span>: l&apos;audio non viene copiato.</p>
      <p>BPM/key arrivano dopo, dall&apos;arricchimento automatico.</p>
    </div>
  );

  return (
    <PageLayout title="Import — Cartella locale" marginaliaTitle="Come funziona" marginalia={marginalia}>
      <Link href="/playlists" className="mb-4 inline-flex items-center gap-1.5 text-sm text-muted hover:text-fg">
        <ArrowLeft size={15} /> Playlist
      </Link>

      {error && <div className="mb-4"><Alert tone="danger">⚠ {error}</Alert></div>}

      {job && (
        <div className="mb-4">
          <Alert tone={job.status === "error" ? "danger" : "info"}>
            {job.status === "running" && <>Import in corso… {job.processed}/{job.total} file</>}
            {job.status === "done" && <>Completato: {job.created} nuove, {job.updated} aggiornate{job.failed ? `, ${job.failed} saltate` : ""}.</>}
            {job.status === "error" && <>Errore: {job.error}</>}
          </Alert>
        </div>
      )}

      <Card>
        <CardHeader title="Scegli la cartella" subtitle={view?.current_path ?? "Caricamento…"} />
        <div className="grid gap-3 p-4">
          <div className="flex flex-wrap gap-2">
            <Button
              size="sm"
              variant="outline"
              disabled={!view?.parent_path || running}
              onClick={() => view?.parent_path && load(view.parent_path)}
            >
              <ArrowUp size={15} /> Su
            </Button>
            {view?.dirs.map((d) => (
              <Button key={d.path} size="sm" variant="outline" disabled={running} onClick={() => load(d.path)}>
                <Folder size={15} /> {d.name}
                {d.audio_file_count > 0 && <span className="ml-1 text-muted tnum">({d.audio_file_count})</span>}
              </Button>
            ))}
            {view && view.dirs.length === 0 && <span className="text-sm text-muted">Nessuna sottocartella.</span>}
          </div>

          <Field label="Nome playlist">
            <Input value={name} onChange={(e) => setName(e.target.value)} disabled={running} placeholder="Nome della playlist" />
          </Field>

          <div className="flex justify-end">
            <Button onClick={doImport} disabled={!view || running}>
              {running ? <Spinner /> : <HardDriveDownload size={15} />} Importa questa cartella
            </Button>
          </div>
        </div>
      </Card>
    </PageLayout>
  );
}
```

Nota: se un componente UI importato (es. `Field`, `Alert` con `tone="info"`) ha un'API diversa, allinea ai pattern reali di `import-manual/page.tsx` e degli altri file in `frontend/components/ui`.

- [ ] **Step 3: Aggiungi la CTA nella pagina playlist**

In `frontend/app/playlists/page.tsx`, dopo la riga della CTA manuale (riga 82), aggiungi:

```tsx
      <Link href="/playlists/import-local" className="block"><Button size="sm" variant="outline" className="w-full"><HardDriveDownload size={15} /> Importa da cartella</Button></Link>
```

Aggiungi `HardDriveDownload` all'import da `lucide-react` in cima al file (dove sono già importati `Download`, `ClipboardList`).

- [ ] **Step 4: Lint + build**

Run: `cd frontend && npm run lint && npm run build`
Expected: nessun errore.

- [ ] **Step 5: Verifica manuale (preview)**

Avvia backend (`uvicorn app.main:app --reload --port 8000`) e frontend (`npm run dev`). Imposta `local_import_root` (in `backend/.env`) a una cartella con qualche file audio. Naviga a `/playlists/import-local`, scegli una cartella, avvia, osserva il progresso e l'atterraggio sulla playlist creata.

- [ ] **Step 6: Commit**

```bash
git add frontend/app/playlists/import-local/page.tsx frontend/app/playlists/page.tsx
git commit -m "feat(local-import): pagina import cartella locale e CTA"
```

---

## Note finali

- **Documentazione:** aggiornare `docs/API.md` (nuovi endpoint), `docs/ARCHITECTURE.md` (sorgente import locale, principio "legge tag, non conserva audio"), `docs/ROADMAP.md` e `PROGRESS.md` come passo separato dopo l'implementazione (fonte di verità di stato).
- **Dipendenza di sistema:** ffmpeg è richiesto per l'hash audio (già assunto da Shazam). Documentarlo nel README come prerequisito dell'import locale.
