# Lotto C (Cratory) — Catena del Genere e Auto-Enrichment — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cratory diventa l'autorità sul genere (catena `manuale > provider > AI > tag file`, tracciata in `genre_source`) e l'enrichment parte da solo per ogni traccia nuova (download Soulseek, indicizzazione disco).

**Architecture:** Nuova colonna `Track.genre_source`; normalizzazione leggera in `services/genre_norm.py` applicata a ogni scrittura di genere; classificatore AI in `services/genre_ai.py` invocato da `enrich_features` quando i provider non danno genere; fallback dal tag file durante l'indicizzazione; `enrichment_job.start_job` esteso con `track_ids` e invocato best-effort dal job Soulseek e dal job indice; il bridge lookup espone `genre_source` e `album`.

**Tech Stack:** Python/FastAPI + SQLAlchemy + pytest. Spec: `~/Develop/docs/superpowers/specs/2026-07-02-metadati-stati-automazioni-design.md` (Lotto C). **Prerequisiti: Lotti A e B mergiati.**

## Global Constraints

- Repo: `/Users/lucadenegri/Develop/DJProject01`, branch dedicato. Commenti in italiano.
- Test: `cd /Users/lucadenegri/Develop/DJProject01/backend && .venv/bin/python -m pytest tests/ -q`.
- Regole CLAUDE.md intoccabili: l'AI non inventa dati fattuali senza marcarli (qui: `genre_source="ai"`), mai sovrascrivere valori esistenti, `enrichment_source="manual"` autorevole.
- L'AI genere usa il client esistente `integrations/llm.py` (`get_llm_client().complete_json(system, payload, schema)`); nessun nuovo client.

---

### Task 1: `Track.genre_source` + normalizzazione leggera

**Files:**
- Modify: `backend/app/models.py` (dopo `genre_secondary`, riga ~61), `backend/app/db.py` (`additions["tracks"]`), `backend/app/schemas.py` (`TrackOut.genre_source`)
- Create: `backend/app/services/genre_norm.py`
- Test: `backend/tests/test_genre_chain.py` (nuovo)

**Interfaces:**
- Produces: `Track.genre_source: str | None` (valori: `"manual" | "provider" | "ai" | "file_tag"`); `normalize_genre(raw: str | None) -> str | None` (None per stringhe vuote). Usati dai Task 2-5.

- [ ] **Step 1: Test che falliscono** — crea `backend/tests/test_genre_chain.py`:

```python
"""Catena del genere: normalizzazione e tracciamento della sorgente."""
import pytest

from app.services.genre_norm import normalize_genre


@pytest.mark.parametrize("raw,expected", [
    ("  tech house ", "Tech House"),
    ("tech-house", "Tech House"),
    ("TECH  HOUSE", "Tech House"),
    ("drum'n'bass", "Drum & Bass"),
    ("dnb", "Drum & Bass"),
    ("Deep House", "Deep House"),
    ("", None),
    ("   ", None),
    (None, None),
])
def test_normalize_genre(raw, expected):
    assert normalize_genre(raw) == expected


def test_track_ha_genre_source(db):
    from app.models import Track
    t = Track(source_type="manual", title="T", artist="A",
              genre="Techno", genre_source="provider")
    db.add(t); db.commit(); db.refresh(t)
    assert t.genre_source == "provider"
```

- [ ] **Step 2: Verifica FAIL** — `pytest tests/test_genre_chain.py -v` → modulo mancante.

- [ ] **Step 3: Implementa** — `models.py` dopo `genre_secondary`:

```python
    # Da dove viene il genere: manual | provider | ai | file_tag (catena di fiducia).
    genre_source: Mapped[str | None] = mapped_column(String)
```

`db.py`: `"genre_source": "VARCHAR",` in `additions["tracks"]`.
`schemas.py`, `TrackOut`: `genre_source: str | None = None` (e in `serializers.py` se i campi sono elencati a mano).

Crea `backend/app/services/genre_norm.py`:

```python
"""Normalizzazione leggera dei generi: niente vocabolario, solo pulizia.

Trim, spazi multipli, trattini come spazi, Title Case, piccola mappa alias.
Deterministica: nessuna AI, nessun provider.
"""
from __future__ import annotations

import re

# Alias noti (chiave: forma normalizzata minuscola DOPO la pulizia base).
_ALIASES = {
    "drum'n'bass": "Drum & Bass",
    "drum n bass": "Drum & Bass",
    "drum and bass": "Drum & Bass",
    "dnb": "Drum & Bass",
    "d&b": "Drum & Bass",
    "edm": "EDM",
    "uk garage": "UK Garage",
    "ukg": "UK Garage",
    "idm": "IDM",
    "r&b": "R&B",
    "rnb": "R&B",
}
_SPACES = re.compile(r"\s+")


def normalize_genre(raw: str | None) -> str | None:
    if raw is None:
        return None
    s = _SPACES.sub(" ", raw.replace("-", " ").replace("_", " ")).strip()
    if not s:
        return None
    alias = _ALIASES.get(s.lower())
    if alias:
        return alias
    return " ".join(w if w.isupper() and len(w) <= 3 else w.capitalize()
                    for w in s.split(" "))
```

- [ ] **Step 4: Verifica PASS + suite** — `pytest tests/test_genre_chain.py -v && pytest tests/ -q`.
- [ ] **Step 5: Commit** — `git commit -m "feat: Track.genre_source e normalizzazione leggera dei generi"`

---

### Task 2: La catena scrive genre_source (provider, manuale, tag file)

**Files:**
- Modify: `backend/app/services/feature_enrichment.py` (`apply_features`, righe ~125-130), `backend/app/routers/tracks.py` (PATCH update traccia — dove `update_track` riceve `data`, righe ~120-137), `backend/app/services/library_index.py` (`_fill_identity`), `backend/app/integrations/local_files.py` (`read_tags`: aggiungi `genre`)
- Test: `backend/tests/test_genre_chain.py` (aggiunte)

**Interfaces:**
- Consumes: `normalize_genre` dal Task 1.
- Produces: ogni scrittura di `Track.genre` passa da `normalize_genre` e valorizza `genre_source`: provider in `apply_features`, `"manual"` nel PATCH se `genre` è nel payload, `"file_tag"` in `_fill_identity` (solo se genere vuoto). `read_tags` ritorna anche `"genre"`.

- [ ] **Step 1: Test che falliscono** — in coda a `tests/test_genre_chain.py`:

```python
def _track(db, **kw):
    from app.models import Track
    t = Track(source_type="spotify", spotify_id="s1", platform_track_id="s1",
              title="T", artist="A", **kw)
    db.add(t); db.commit()
    return t


def test_provider_setta_genre_source(db):
    from app.services.feature_enrichment import apply_features
    t = _track(db)
    apply_features(t, {"genre_primary": "tech-house", "confidence": 80}, source="deezer")
    assert t.genre == "Tech House"
    assert t.genre_source == "provider"


def test_provider_non_sovrascrive_manuale(db):
    from app.services.feature_enrichment import apply_features
    t = _track(db, genre="Acid Techno", genre_source="manual")
    apply_features(t, {"genre_primary": "House", "confidence": 80}, source="deezer")
    assert t.genre == "Acid Techno" and t.genre_source == "manual"


def test_fill_identity_usa_tag_file_come_ultima_spiaggia(db, tmp_path):
    from app.services.library_index import _fill_identity
    t = _track(db)
    _fill_identity(t, {"artist": "A", "title": "T", "genre": "  deep   house "},
                   tmp_path / "A - T.mp3")
    assert t.genre == "Deep House"
    assert t.genre_source == "file_tag"


def test_fill_identity_non_tocca_genere_esistente(db, tmp_path):
    from app.services.library_index import _fill_identity
    t = _track(db, genre="Techno", genre_source="provider")
    _fill_identity(t, {"artist": "A", "title": "T", "genre": "House"},
                   tmp_path / "A - T.mp3")
    assert t.genre == "Techno" and t.genre_source == "provider"
```

- [ ] **Step 2: Verifica FAIL** — `pytest tests/test_genre_chain.py -v`.

- [ ] **Step 3: Implementa**

`feature_enrichment.py`, in `apply_features` sostituisci il blocco genere (righe ~125-130):

```python
    if not track.genre and data.get("genre_primary"):
        track.genre = normalize_genre(data["genre_primary"])
        track.genre_source = "provider"
        applied.add("genre")
    if not track.genre_secondary and data.get("genre_secondary"):
        track.genre_secondary = normalize_genre(data["genre_secondary"])
        applied.add("genre_secondary")
```

con import in testa: `from app.services.genre_norm import normalize_genre`.

`routers/tracks.py`, nel PATCH della traccia (il punto dove `data` viene validato prima di `update_track`, accanto alla validazione Camelot):

```python
    # Il genere corretto a mano e' la massima autorita' della catena.
    if "genre" in data:
        data["genre"] = normalize_genre(data.get("genre"))
        data["genre_source"] = "manual"
```

(import di `normalize_genre`; verifica che `update_track` in `repositories.py` applichi campi arbitrari del dict — se ha una whitelist, aggiungi `genre_source`.)

`integrations/local_files.py`, `read_tags`: aggiungi l'estrazione del genere accanto agli altri campi easy/ID3 (chiave mutagen easy `"genre"`, frame ID3 `TCON` — segui il pattern degli altri campi del file, es. album). Il dict ritornato guadagna `"genre": <str | None>`.

`library_index.py`, `_fill_identity`, dopo il blocco `track.isrc = ...`:

```python
    # Genere dal tag del file: ultima spiaggia della catena (mai sovrascrivere).
    if not track.genre and tags.get("genre"):
        normalized = normalize_genre(tags["genre"])
        if normalized:
            track.genre = normalized
            track.genre_source = "file_tag"
```

(import di `normalize_genre` in testa al modulo.)

- [ ] **Step 4: Verifica PASS + suite** — `pytest tests/ -q` (occhio ai test esistenti di enrichment: il genere ora esce normalizzato — se qualche assert usa il valore grezzo del provider, aggiorna l'atteso SOLO se il nuovo valore è la normalizzazione corretta).
- [ ] **Step 5: Commit** — `git commit -m "feat: catena del genere con genre_source (manuale/provider/tag file)"`

---

### Task 3: Classificatore AI come anello di riserva

**Files:**
- Create: `backend/app/services/genre_ai.py`
- Modify: `backend/app/services/feature_enrichment.py` (nel loop di `enrich_features`, dopo l'applicazione dei provider)
- Test: `backend/tests/test_genre_chain.py` (aggiunte)

**Interfaces:**
- Consumes: `get_llm_client` da `integrations/llm.py` (`complete_json(system_prompt, payload, schema)`); `settings.ai_api_key`; `normalize_genre`.
- Produces: `suggest_genre(track) -> str | None` (None se non configurata, errore LLM, o risposta senza genere). In `enrich_features`, dopo i provider: se `track.genre` ancora vuoto → AI → `genre_source="ai"`.

- [ ] **Step 1: Test che falliscono** — in coda a `tests/test_genre_chain.py`:

```python
def test_ai_entra_solo_se_genere_vuoto(db, monkeypatch):
    from app.services import genre_ai
    t = _track(db)
    monkeypatch.setattr(genre_ai, "suggest_genre", lambda track: "Minimal Techno")
    from app.services.feature_enrichment import maybe_ai_genre
    maybe_ai_genre(t)
    assert t.genre == "Minimal Techno" and t.genre_source == "ai"

    t2 = _track(db, genre="House", genre_source="provider")
    maybe_ai_genre(t2)
    assert t2.genre == "House" and t2.genre_source == "provider"


def test_ai_non_configurata_o_errore_neutra(db, monkeypatch):
    from app.services import genre_ai
    from app.services.feature_enrichment import maybe_ai_genre
    t = _track(db)
    monkeypatch.setattr(genre_ai, "suggest_genre", lambda track: None)
    maybe_ai_genre(t)
    assert t.genre is None and t.genre_source is None
```

- [ ] **Step 2: Verifica FAIL** — `pytest tests/test_genre_chain.py -v`.

- [ ] **Step 3: Implementa**

Crea `backend/app/services/genre_ai.py`:

```python
"""Classificazione AI del genere: anello di riserva della catena.

Entra SOLO quando i provider non hanno dato un genere. L'output e' marcato
genre_source="ai" dal chiamante: mai spacciato per dato fattuale (CLAUDE.md).
"""
from __future__ import annotations

import logging

from app.core.config import settings
from app.integrations.llm import LLMError, LLMNotConfigured, get_llm_client
from app.services.genre_norm import normalize_genre

logger = logging.getLogger(__name__)

_SYSTEM = (
    "Sei un archivista musicale per DJ. Dato artista, titolo ed eventuali "
    "etichetta/anno, indica il genere principale del brano in 1-3 parole "
    "(es. 'Tech House', 'Drum & Bass'). Se non conosci il brano con ragionevole "
    "certezza rispondi con genre=null: MAI tirare a indovinare."
)
_SCHEMA = {
    "type": "object",
    "properties": {"genre": {"type": ["string", "null"]}},
    "required": ["genre"],
    "additionalProperties": False,
}


def suggest_genre(track) -> str | None:
    """Genere suggerito dall'AI, normalizzato. None = niente risposta affidabile."""
    if not settings.ai_api_key or not (track.artist and track.title):
        return None
    payload = {"artist": track.artist, "title": track.title,
               "label": track.label, "year": track.year}
    try:
        out = get_llm_client().complete_json(_SYSTEM, payload, _SCHEMA)
    except (LLMNotConfigured, LLMError) as exc:
        logger.warning("AI genere non disponibile per '%s - %s': %s",
                       track.artist, track.title, exc)
        return None
    return normalize_genre(out.get("genre"))
```

In `feature_enrichment.py` aggiungi (import: `from app.services import genre_ai`):

```python
def maybe_ai_genre(track: Track) -> None:
    """Anello AI della catena del genere: solo su genere vuoto, mai sovrascrive."""
    if track.genre:
        return
    genre = genre_ai.suggest_genre(track)
    if genre:
        track.genre = genre
        track.genre_source = "ai"
```

e nel loop di `enrich_features`, nel punto in cui una traccia ha terminato il giro provider (subito dopo la chiamata ad `apply_features` / gestione cache, prima del commit della traccia): `maybe_ai_genre(track)`.

**Nota anti-costo:** `suggest_genre` fa una chiamata LLM per traccia senza genere: accettabile perché entra solo dopo che TUTTI i provider hanno fallito e solo con `AI_API_KEY` configurata.

- [ ] **Step 4: Verifica PASS + suite** — `pytest tests/ -q`. Verifica esplicita: i test esistenti di enrichment NON devono fare chiamate LLM (senza `ai_api_key` nei test, `suggest_genre` ritorna `None` prima di creare il client).
- [ ] **Step 5: Commit** — `git commit -m "feat: AI come anello di riserva della catena del genere"`

---

### Task 4: Auto-enrichment su download e indicizzazione

**Files:**
- Modify: `backend/app/services/enrichment_job.py` (`start_job` e `_run_job`: parametro `track_ids`), `backend/app/services/soulseek_download_job.py` (a fine job, enrich dei downloaded), `backend/app/services/library_index.py` (report `created_ids`), `backend/app/services/library_index_job.py` (a fine job, enrich dei creati)
- Test: `backend/tests/test_autoenrich.py` (nuovo)

**Interfaces:**
- Consumes: `enrich_features(db, provider, force, playlist_id, track_ids, on_progress)` (supporta già `track_ids`); report di `index_library`.
- Produces: `enrichment_job.start_job(*, force=False, playlist_id=None, track_ids=None)`; `index_library` report con `created_ids: list[int]`; i due job chiamano `enrichment_job.start_job(track_ids=...)` best-effort (mai far fallire il job chiamante — stesso pattern di `_autoenrich` in `routers/playlists.py:65`).

- [ ] **Step 1: Test che falliscono** — crea `backend/tests/test_autoenrich.py`:

```python
"""Auto-enrichment: parte da solo per le tracce nuove (download, indice)."""


def test_report_indice_contiene_created_ids(db, tmp_path, monkeypatch):
    from app.services import library_index as li
    from app.services.library_index import index_library

    p = tmp_path / "Libreria" / "A - Nuova.mp3"
    p.parent.mkdir(parents=True)
    p.write_bytes(b"x")
    monkeypatch.setattr(li, "audio_hash", lambda _: "H-NEW")
    monkeypatch.setattr(li, "read_tags", lambda _: {
        "title": "Nuova", "artist": "A", "album": None, "year": None,
        "duration_seconds": 200, "isrc": None, "genre": None})
    monkeypatch.setattr(li, "read_audio_quality", lambda _: {"format": "mp3", "bitrate": 320})

    report = index_library(db, root=tmp_path / "Libreria")
    assert report["created"] == 1
    assert len(report["created_ids"]) == 1


def test_job_indice_lancia_autoenrich(monkeypatch, tmp_path):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from app.core.config import settings
    from app.db import Base
    from app.services import library_index_job

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    monkeypatch.setattr(library_index_job, "SessionLocal",
                        sessionmaker(bind=engine, expire_on_commit=False))
    monkeypatch.setattr(settings, "library_root", str(tmp_path))
    monkeypatch.setattr(library_index_job, "_spawn", lambda fn: fn())

    calls = []
    monkeypatch.setattr(library_index_job, "_autoenrich_created",
                        lambda ids: calls.append(ids))
    # cartella vuota: nessuna traccia creata => niente enrich
    library_index_job.start_job()
    assert calls == []
```

- [ ] **Step 2: Verifica FAIL** — `pytest tests/test_autoenrich.py -v` → `KeyError: 'created_ids'` / attributo mancante.

- [ ] **Step 3: Implementa**

`library_index.py`: nel dict `report` iniziale aggiungi `"created_ids": []`; nel ramo `if track is None:` (creazione), dopo `report["created"] += 1` aggiungi `db.flush()` e `report["created_ids"].append(track.id)`.

`enrichment_job.py`:

```python
def start_job(*, force: bool = False, playlist_id: int | None = None,
              track_ids: list[int] | None = None) -> dict:
```

propaga `track_ids` in `_state` (chiave informativa), in `_run_job(force, playlist_id, track_ids)` e nella chiamata `enrich_features(db, provider, force=force, playlist_id=playlist_id, track_ids=track_ids, on_progress=on_progress)`; aggiorna `threading.Thread(target=_run_job, args=(force, playlist_id, track_ids), daemon=True)`.

`library_index_job.py`, nuova funzione + hook in `_run_job` dopo il `set_state(...)` del Lotto A:

```python
def _autoenrich_created(track_ids: list[int]) -> None:
    """Best-effort: le tracce nuove dell'indice partono subito in enrichment."""
    if not track_ids:
        return
    try:
        from app.services import enrichment_job
        enrichment_job.start_job(track_ids=track_ids)
    except Exception:  # noqa: BLE001 — l'indice non deve fallire per l'enrichment
        logger.exception("Auto-enrichment non avviato per %d tracce nuove", len(track_ids))
```

e in `_run_job`, subito dopo `_state.update(status="done", ...)`: `_autoenrich_created(report["created_ids"])`. (Import locale dentro la funzione per evitare cicli.)

`soulseek_download_job.py`: nel loop del job, colleziona gli id scaricati (`downloaded_ids: list[int]`, append di `track.id` quando l'esito è `"downloaded"`); a fine job (nel `finally`/dopo il loop, prima della chiusura db) chiama una funzione locale identica `_autoenrich_downloaded(downloaded_ids)` con lo stesso pattern best-effort. ATTENZIONE: individuare il punto esatto del loop in `_run_job` del job Soulseek dove `outcome` viene registrato (`_state[outcome] += 1`, riga ~230) e appendere lì.

- [ ] **Step 4: Verifica PASS + suite** — `pytest tests/ -q`.
- [ ] **Step 5: Commit** — `git commit -m "feat: auto-enrichment per tracce nuove (download Soulseek e indice)"`

---

### Task 5: Il bridge espone `genre_source` e `album`

**Files:**
- Modify: `backend/app/schemas.py` (`TrackLookupOut`), `backend/app/routers/tracks.py` (lookup, righe ~73-108)
- Test: `backend/tests/test_track_lookup.py` (aggiunta)

**Interfaces:**
- Produces: `TrackLookupOut` con `genre_source: str | None` e `album: str | None`; il contratto del bridge DjOrganizer (piano C-DjOrganizer) li legge.

- [ ] **Step 1: Test che fallisce** — in `tests/test_track_lookup.py` aggiungi (usando le fixture `lookup_db`/`client` esistenti del file):

```python
def test_lookup_espone_genre_source_e_album(lookup_db, client):
    lookup_db.add(Track(source_type="spotify", spotify_id="g1", platform_track_id="g1",
                        artist="Rataxes", title="Acid Face", isrc="DEAB12300123",
                        genre="Acid Techno", genre_source="provider", album="Bunker EP"))
    lookup_db.commit()
    r = client.get("/api/tracks/lookup", params={"isrc": "DEAB12300123"}).json()
    assert r["found"] is True
    assert r["genre_source"] == "provider"
    assert r["album"] == "Bunker EP"
```

- [ ] **Step 2: Verifica FAIL** — `pytest tests/test_track_lookup.py -v`.

- [ ] **Step 3: Implementa** — `schemas.py`, `TrackLookupOut` dopo `genre_secondary`:

```python
    genre_source: str | None = None  # manual | provider | ai | file_tag
    album: str | None = None
```

`routers/tracks.py`, nel `return TrackLookupOut(...)` finale del lookup aggiungi `genre_source=hit.genre_source, album=hit.album,`.

- [ ] **Step 4: Verifica PASS + suite** — `pytest tests/ -q`.
- [ ] **Step 5: Commit** — `git commit -m "feat: lookup bridge espone genre_source e album"`
