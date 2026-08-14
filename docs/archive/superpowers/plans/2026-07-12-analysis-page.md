# Pagina Analisi — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Nuova pagina `/analysis` che unifica import Rekordbox (source-aware) e analisi BPM/key in-app con Essentia, con provenienza esplicita dei valori (`manual` > `rekordbox` > `cratory`) e tabella divergenze con apply/force.

**Architecture:** Il job di analisi (pattern `library_index_job`: stato in memoria + lock + thread daemon) scrive SOLO le colonne `analysis_*`; i campi canonici `bpm`/`camelot_key` cambiano solo via modifica manuale, import Rekordbox o apply esplicito/automatico. Motore Essentia dietro adapter con import lazy in `integrations/`.

**Tech Stack:** FastAPI + SQLAlchemy/SQLite (backend), Essentia (analisi audio), Next.js 16 App Router + Tailwind (frontend).

**Spec:** `docs/superpowers/specs/2026-07-12-analysis-page-design.md` (leggerla prima di iniziare).

## Global Constraints

- **Sessioni parallele sullo stesso checkout**: il working tree contiene modifiche di un'altra sessione. `git add` SOLO i file elencati nel task corrente, MAI `git add -A` / `git add .`. Verificare `git branch --show-current` = `master` prima di ogni commit.
- **Commit**: messaggi in italiano, stile conventional dei commit recenti (`feat:`, `feat(ui):`, `docs:`). NIENTE riga `Co-Authored-By`.
- **Backend**: comandi da `backend/` con venv attivo (`source .venv/bin/activate`). Test: `python -m pytest tests -q`.
- **Frontend**: Next.js 16 ha breaking changes — leggere la guida pertinente in `frontend/node_modules/next/dist/docs/` PRIMA di scrivere pagine/routing (obbligo da `frontend/CLAUDE.md`). Verifica: `npm run lint && npm run build` da `frontend/`.
- **i18n**: ogni stringa UI va in `frontend/lib/i18n/en.ts` E `it.ts` (it si tipizza da en — se manca una chiave il build fallisce).
- **Camelot canonico**: sempre `"7A"` (numero + lettera maiuscola), validato con `parse_camelot`.
- **Dipendenza pinnata**: `essentia==2.1b6.dev1438` NO — usare ESATTAMENTE `essentia==2.1b6.dev1389` (unica release con wheel cp311 macosx arm64).
- **Errori API**: sempre `api_error(status, code, message)` da `app.core.http_errors`; ogni `code` nuovo va tradotto in `errors` di en.ts/it.ts.

---

### Task 1: Colonne provenienza + analisi (schema e backfill)

**Files:**
- Modify: `backend/app/models.py:82-92` (classe `Track`, dopo `camelot_key`/`energy_source`)
- Modify: `backend/app/db.py:44-78` (dict `additions["tracks"]`) e `db.py:105-109` (chiamate migrazioni in `ensure_schema`)
- Test: `backend/tests/test_analysis_schema.py` (nuovo)

**Interfaces:**
- Consumes: pattern migrazioni idempotenti di `ensure_schema` (`db.py`).
- Produces: colonne `Track.bpm_source`, `Track.key_source` (`str | None`: `'manual'|'rekordbox'|'cratory'`), `Track.analysis_bpm` (`float | None`), `Track.analysis_camelot` (`str | None`), `Track.analyzed_at` (`datetime | None`), `Track.analysis_error` (`str | None`); migrazione `_migrate_backfill_bpm_key_sources(conn)`.

- [ ] **Step 1: Scrivere il test che fallisce**

```python
# backend/tests/test_analysis_schema.py
"""Colonne provenienza/analisi e backfill delle source (pagina Analisi)."""
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import ensure_schema
from app.models import Track


def _engine():
    return create_engine("sqlite://", connect_args={"check_same_thread": False},
                         poolclass=StaticPool)


def test_track_ha_colonne_provenienza_e_analisi(db):
    t = Track(source_type="spotify", bpm=128.0, camelot_key="8A",
              bpm_source="rekordbox", key_source="manual",
              analysis_bpm=127.9, analysis_camelot="8A",
              analysis_error=None)
    db.add(t); db.commit(); db.refresh(t)
    assert t.bpm_source == "rekordbox" and t.key_source == "manual"
    assert t.analysis_bpm == 127.9 and t.analysis_camelot == "8A"
    assert t.analyzed_at is None and t.analysis_error is None


def test_backfill_source_rekordbox_su_valori_esistenti():
    """DB pre-migrazione: bpm/key presenti ma source NULL -> 'rekordbox'."""
    e = _engine()
    ensure_schema(e)
    S = sessionmaker(bind=e, expire_on_commit=False)
    with S() as s:
        s.add(Track(source_type="spotify", bpm=130.0, camelot_key="9A"))
        s.add(Track(source_type="spotify"))  # senza valori: source resta NULL
        s.commit()
        s.execute(text("UPDATE tracks SET bpm_source = NULL, key_source = NULL"))
        s.commit()
    ensure_schema(e)  # idempotente: il backfill gira di nuovo
    with S() as s:
        con, senza = s.scalars(select(Track).order_by(Track.id)).all()
        assert con.bpm_source == "rekordbox" and con.key_source == "rekordbox"
        assert senza.bpm_source is None and senza.key_source is None
```

- [ ] **Step 2: Verificare che fallisca**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_analysis_schema.py -v`
Expected: FAIL (`TypeError: 'bpm_source' is an invalid keyword argument for Track`)

- [ ] **Step 3: Implementare**

In `models.py`, dopo la riga `energy_source: Mapped[str | None] = mapped_column(String)` (riga 87):

```python
    # Provenienza di bpm/camelot_key: manual | rekordbox | cratory (null se il
    # valore e' null). Gerarchia: manual > rekordbox > cratory; l'import
    # Rekordbox sovrascrive di default solo i valori 'cratory'.
    bpm_source: Mapped[str | None] = mapped_column(String)
    key_source: Mapped[str | None] = mapped_column(String)
    # Analisi BPM/key in-app (Essentia). Il job scrive SOLO questi campi: i
    # canonici bpm/camelot_key cambiano solo via apply (vedi services/audio_analysis).
    analysis_bpm: Mapped[float | None] = mapped_column(Float)
    analysis_camelot: Mapped[str | None] = mapped_column(String)
    analyzed_at: Mapped[datetime | None] = mapped_column(DateTime)
    analysis_error: Mapped[str | None] = mapped_column(String)
```

In `db.py`, dentro `additions["tracks"]` (dopo `"last_download_path": "TEXT",`):

```python
            # Pagina Analisi: provenienza bpm/key + risultati analisi in-app
            "bpm_source": "VARCHAR",
            "key_source": "VARCHAR",
            "analysis_bpm": "FLOAT",
            "analysis_camelot": "VARCHAR",
            "analyzed_at": "DATETIME",
            "analysis_error": "VARCHAR",
```

In `db.py`, nuova funzione dopo `_migrate_rename_liked_spotify`:

```python
def _migrate_backfill_bpm_key_sources(conn) -> None:
    """Backfill provenienza bpm/key: i valori esistenti arrivavano dall'import
    Rekordbox (unica fonte storica di scrittura); un valore in realta' corretto a
    mano si ri-etichetta 'manual' alla prossima modifica. Idempotente: la WHERE
    su source NULL rende no-op le esecuzioni successive."""
    conn.execute(text(
        "UPDATE tracks SET bpm_source = 'rekordbox' "
        "WHERE bpm IS NOT NULL AND bpm_source IS NULL"))
    conn.execute(text(
        "UPDATE tracks SET key_source = 'rekordbox' "
        "WHERE camelot_key IS NOT NULL AND camelot_key != '' AND key_source IS NULL"))
```

e in `ensure_schema`, dopo `_migrate_rename_liked_spotify(conn)`:

```python
        _migrate_backfill_bpm_key_sources(conn)
```

- [ ] **Step 4: Verificare che passi (e niente regressioni)**

Run: `python -m pytest tests/test_analysis_schema.py tests/test_db_hygiene.py tests/test_engine_upgrades.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/models.py backend/app/db.py backend/tests/test_analysis_schema.py
git commit -m "feat(db): provenienza bpm/key + colonne analisi in-app con backfill"
```

---

### Task 2: Modifica manuale source-aware

**Files:**
- Modify: `backend/app/repositories.py:121-141` (`update_track`)
- Test: `backend/tests/test_analysis_sources.py` (nuovo)

**Interfaces:**
- Consumes: `Track.bpm_source`/`key_source` (Task 1).
- Produces: `update_track` imposta `bpm_source='manual'` quando il patch tocca `bpm` (null se azzerato), idem `key_source` per `camelot_key`. Firma invariata: `update_track(db, track, data) -> Track`.

- [ ] **Step 1: Scrivere il test che fallisce**

```python
# backend/tests/test_analysis_sources.py
"""Regole di provenienza: modifica manuale (repositories.update_track)."""
from app.models import Track
from app.repositories import update_track


def test_patch_bpm_imposta_source_manual(db):
    t = Track(source_type="spotify", bpm=128.0, bpm_source="rekordbox")
    db.add(t); db.commit()
    update_track(db, t, {"bpm": 130.0})
    assert t.bpm == 130.0 and t.bpm_source == "manual"


def test_patch_key_imposta_source_manual(db):
    t = Track(source_type="spotify", camelot_key="8A", key_source="cratory")
    db.add(t); db.commit()
    update_track(db, t, {"camelot_key": "9A"})
    assert t.camelot_key == "9A" and t.key_source == "manual"


def test_azzeramento_azzera_anche_la_source(db):
    t = Track(source_type="spotify", bpm=128.0, bpm_source="manual",
              camelot_key="8A", key_source="manual")
    db.add(t); db.commit()
    update_track(db, t, {"bpm": None, "camelot_key": None})
    assert t.bpm is None and t.bpm_source is None
    assert t.camelot_key is None and t.key_source is None


def test_patch_altri_campi_non_tocca_le_source(db):
    t = Track(source_type="spotify", bpm=128.0, bpm_source="rekordbox")
    db.add(t); db.commit()
    update_track(db, t, {"title": "Nuovo"})
    assert t.bpm_source == "rekordbox"
```

- [ ] **Step 2: Verificare che fallisca**

Run: `python -m pytest tests/test_analysis_sources.py -v`
Expected: FAIL su `test_patch_bpm_imposta_source_manual` (`bpm_source == "rekordbox"`)

- [ ] **Step 3: Implementare**

In `repositories.py`, in `update_track`, subito DOPO il loop `for field, value in data.items(): ... setattr(...)` e PRIMA del blocco `if "bpm" in data or "genre" in data:`:

```python
    # Provenienza: l'inserimento a mano e' la massima autorita' (manual >
    # rekordbox > cratory). Azzerare il valore azzera anche la source.
    if "bpm" in data:
        track.bpm_source = "manual" if track.bpm is not None else None
    if "camelot_key" in data:
        track.key_source = "manual" if track.camelot_key else None
```

Aggiornare la docstring di `update_track` aggiungendo in coda: `Imposta bpm_source/key_source='manual' quando il patch tocca bpm/camelot_key.`

- [ ] **Step 4: Verificare che passi**

Run: `python -m pytest tests/test_analysis_sources.py -v`
Expected: PASS (4 test)

- [ ] **Step 5: Commit**

```bash
git add backend/app/repositories.py backend/tests/test_analysis_sources.py
git commit -m "feat: modifica manuale bpm/key imposta provenienza manual"
```

---

### Task 3: Import Rekordbox source-aware

**Files:**
- Modify: `backend/app/services/rekordbox_import.py:104-139` (`apply_collection`)
- Test: `backend/tests/test_analysis_sources.py` (aggiunta in coda)

**Interfaces:**
- Consumes: `Track.bpm_source`/`key_source` (Task 1).
- Produces: `apply_collection(db, xml_bytes, overwrite=False) -> dict` (firma invariata) con nuova semantica: default scrive se campo vuoto O source `'cratory'`; protegge `'manual'`; `overwrite=True` vince su tutto; ogni scrittura imposta source `'rekordbox'`.

- [ ] **Step 1: Scrivere i test che falliscono**

Aggiungere in coda a `backend/tests/test_analysis_sources.py`:

```python
# ---- Import Rekordbox source-aware (services/rekordbox_import) ----

def _xml(bpm="130.00", tonality="9A", path="/x/a.mp3"):
    loc = f"file://localhost{path}"
    return (f'<DJ_PLAYLISTS><COLLECTION><TRACK Location="{loc}" '
            f'AverageBpm="{bpm}" Tonality="{tonality}" Artist="A" Name="T"/>'
            f"</COLLECTION></DJ_PLAYLISTS>").encode()


def _owned(db, **kw):
    from app.models import Track
    t = Track(source_type="spotify", has_local_file=True, local_path="/x/a.mp3",
              artist="A", title="T", **kw)
    db.add(t); db.commit()
    return t


def test_rekordbox_sovrascrive_cratory_di_default(db):
    from app.services.rekordbox_import import apply_collection
    t = _owned(db, bpm=127.5, bpm_source="cratory", camelot_key="8A", key_source="cratory")
    apply_collection(db, _xml())
    assert t.bpm == 130.0 and t.bpm_source == "rekordbox"
    assert t.camelot_key == "9A" and t.key_source == "rekordbox"


def test_rekordbox_protegge_manual_di_default(db):
    from app.services.rekordbox_import import apply_collection
    t = _owned(db, bpm=127.5, bpm_source="manual", camelot_key="8A", key_source="manual")
    apply_collection(db, _xml())
    assert t.bpm == 127.5 and t.bpm_source == "manual"
    assert t.camelot_key == "8A" and t.key_source == "manual"


def test_rekordbox_overwrite_vince_anche_su_manual(db):
    from app.services.rekordbox_import import apply_collection
    t = _owned(db, bpm=127.5, bpm_source="manual", camelot_key="8A", key_source="manual")
    apply_collection(db, _xml(), overwrite=True)
    assert t.bpm == 130.0 and t.bpm_source == "rekordbox"
    assert t.camelot_key == "9A" and t.key_source == "rekordbox"


def test_rekordbox_riempie_campi_vuoti_con_source(db):
    from app.services.rekordbox_import import apply_collection
    t = _owned(db)
    apply_collection(db, _xml())
    assert t.bpm == 130.0 and t.bpm_source == "rekordbox"
    assert t.camelot_key == "9A" and t.key_source == "rekordbox"
```

- [ ] **Step 2: Verificare che falliscano**

Run: `python -m pytest tests/test_analysis_sources.py -v`
Expected: FAIL su `test_rekordbox_sovrascrive_cratory_di_default` (bpm resta 127.5) e su `..._con_source` (source resta None); i test manual/overwrite possono già passare per la vecchia semantica ma senza source.

- [ ] **Step 3: Implementare**

In `apply_collection`, sostituire il blocco condizioni (righe 127-132):

```python
        # Source-aware (manual > rekordbox > cratory): di default Rekordbox
        # riempie i vuoti e riprende i valori 'cratory' (l'analisi in-app e'
        # fallback); non tocca le correzioni manuali. overwrite=True vince su
        # tutto (intento esplicito). Ogni scrittura marca la fonte.
        bpm_writable = overwrite or t.bpm is None or t.bpm_source == "cratory"
        if r.bpm is not None and bpm_writable and t.bpm != r.bpm:
            t.bpm = r.bpm
            t.bpm_source = "rekordbox"
            bpm_set += 1
        key_writable = overwrite or not t.camelot_key or t.key_source == "cratory"
        if r.camelot and key_writable and t.camelot_key != r.camelot:
            t.camelot_key = r.camelot
            t.key_source = "rekordbox"
            key_set += 1
```

Aggiornare la docstring di `apply_collection`: sostituire `Di default riempie solo i campi vuoti (protegge le correzioni manuali)` con `Di default riempie i campi vuoti e sovrascrive i valori 'cratory' (analisi in-app); protegge le correzioni manuali`.

- [ ] **Step 4: Verificare che passino (e la suite Rekordbox esistente)**

Run: `python -m pytest tests/test_analysis_sources.py tests/ -q -k "rekordbox or analysis"`
Expected: PASS. Poi l'intera suite: `python -m pytest tests -q` → PASS (se un test esistente assumeva la vecchia semantica sui non-vuoti non-manual, aggiornarlo alla nuova semantica dichiarata nella spec).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/rekordbox_import.py backend/tests/test_analysis_sources.py
git commit -m "feat: import Rekordbox source-aware (sovrascrive cratory, protegge manual)"
```

---

### Task 4: Motore Essentia (adapter + dipendenza)

**Files:**
- Modify: `backend/requirements.txt`
- Create: `backend/app/integrations/essentia_engine.py`
- Test: `backend/tests/test_essentia_engine.py` (nuovo)

**Interfaces:**
- Consumes: `pitch_to_camelot` da `app.services.camelot`.
- Produces: modulo `app.integrations.essentia_engine` con `is_available() -> bool`, `analyze(path: str) -> AnalysisResult` (dataclass con `bpm: float | None`, `camelot: str | None`), helper puro `_key_to_camelot(key: str, scale: str) -> str | None`.

- [ ] **Step 1: Aggiungere la dipendenza pinnata e installarla**

In coda a `backend/requirements.txt`:

```text
# Analisi BPM/key in-app (pagina Analisi). Pin ESATTO: Essentia pubblica solo
# build rolling (2.1b6.devN) con copertura wheel a macchia di leopardo; questa
# e' l'ultima con wheel cp311 macosx-arm64. Licenza AGPL-3.0 (ok per uso
# personale self-hosted, nessuna distribuzione).
essentia==2.1b6.dev1389
```

Run: `pip install essentia==2.1b6.dev1389`
Expected: installazione dalla wheel (nessuna compilazione). Verifica: `python -c "import essentia.standard; print('ok')"` → `ok` (warning di log Essentia accettabili).

- [ ] **Step 2: Scrivere i test che falliscono**

```python
# backend/tests/test_essentia_engine.py
"""Adapter Essentia: mapping key->Camelot (puro) + smoke test sul motore vero."""
import math
import struct
import wave

import pytest

from app.integrations import essentia_engine as eng


def test_key_to_camelot_mapping():
    assert eng._key_to_camelot("A", "minor") == "8A"
    assert eng._key_to_camelot("C", "major") == "8B"
    assert eng._key_to_camelot("F#", "minor") == "11A"
    assert eng._key_to_camelot("Eb", "major") == "5B"
    assert eng._key_to_camelot("", "minor") is None


def test_is_available_bool():
    assert isinstance(eng.is_available(), bool)


def _click_track_wav(path, bpm=120.0, seconds=20, sr=44100):
    """Click ogni beat a `bpm`: contenuto ritmico inequivocabile per il tempo."""
    interval = int(sr * 60 / bpm)
    frames = bytearray()
    for i in range(sr * seconds):
        on_click = (i % interval) < int(sr * 0.01)  # click di 10ms
        val = int(0.9 * 32767 * math.sin(2 * math.pi * 1000 * i / sr)) if on_click else 0
        frames += struct.pack("<h", val)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes(bytes(frames))


@pytest.mark.skipif(not eng.is_available(), reason="Essentia non installata")
def test_analyze_click_track(tmp_path):
    p = tmp_path / "click120.wav"
    _click_track_wav(p, bpm=120.0)
    res = eng.analyze(str(p))
    assert res.bpm is not None and abs(res.bpm - 120.0) < 2.0
    # La key di un click track non e' significativa: basta che non crashi.
```

- [ ] **Step 3: Verificare che falliscano**

Run: `python -m pytest tests/test_essentia_engine.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'app.integrations.essentia_engine'`

- [ ] **Step 4: Implementare**

```python
# backend/app/integrations/essentia_engine.py
"""Motore di analisi BPM/key in-app (Essentia).

Import lazy: l'app parte anche senza la libreria installata; is_available()
alimenta il 503 `analysis_engine_unavailable` del router. Deterministico: BPM da
RhythmExtractor2013 (multifeature), key dal profilo 'edma' (tarato elettronica),
convertita nella notazione Camelot canonica del progetto ("7A")."""

from __future__ import annotations

from dataclasses import dataclass

from app.services.camelot import pitch_to_camelot


@dataclass
class AnalysisResult:
    bpm: float | None
    camelot: str | None


def is_available() -> bool:
    try:
        import essentia.standard  # noqa: F401
    except ImportError:
        return False
    return True


def _key_to_camelot(key: str, scale: str) -> str | None:
    """Mappa l'output di KeyExtractor (es. 'A', 'minor') in Camelot canonico."""
    if not key:
        return None
    suffix = "m" if (scale or "").lower().startswith("min") else ""
    return pitch_to_camelot(f"{key}{suffix}")


def analyze(path: str) -> AnalysisResult:
    """Analizza un file audio (mp3/flac/aiff/wav: decoding interno di Essentia).

    Puo' sollevare qualunque eccezione Essentia su file illeggibili: il job la
    traduce in `analysis_error` per traccia senza fermare il batch.
    """
    import essentia.standard as es

    audio = es.MonoLoader(filename=path, sampleRate=44100)()
    bpm_raw = float(es.RhythmExtractor2013(method="multifeature")(audio)[0])
    bpm = round(bpm_raw, 2) if bpm_raw > 0 else None
    key, scale, _strength = es.KeyExtractor(profileType="edma")(audio)
    return AnalysisResult(bpm=bpm, camelot=_key_to_camelot(key, scale))
```

- [ ] **Step 5: Verificare che passino**

Run: `python -m pytest tests/test_essentia_engine.py -v`
Expected: PASS (3 test + lo smoke test se Essentia installata; il click track richiede ~10-30s di calcolo).

- [ ] **Step 6: Commit**

```bash
git add backend/requirements.txt backend/app/integrations/essentia_engine.py backend/tests/test_essentia_engine.py
git commit -m "feat: adapter Essentia per analisi BPM/key in-app (import lazy, pin wheel arm64)"
```

---

### Task 5: Servizio apply/divergenze

**Files:**
- Create: `backend/app/services/audio_analysis.py`
- Test: `backend/tests/test_audio_analysis.py` (nuovo)

**Interfaces:**
- Consumes: `Track` (Task 1), `camelot_compatibility`, `apply_estimated_energy`, `refresh_status`.
- Produces: `diverges(track) -> bool`, `apply_analysis(track) -> bool` (copia `analysis_*` nei canonici con source `'cratory'`, ricalcola energia+stato), `auto_apply_missing(track) -> bool` (solo campi vuoti), `divergence_row(track) -> dict` (chiavi: `track_id, artist, title, bpm, bpm_source, analysis_bpm, bpm_delta, camelot_key, key_source, analysis_camelot, key_compatibility`).

- [ ] **Step 1: Scrivere i test che falliscono**

```python
# backend/tests/test_audio_analysis.py
"""Regole deterministiche di divergenza e apply dell'analisi in-app."""
from app.models import Track
from app.services.audio_analysis import (apply_analysis, auto_apply_missing,
                                         divergence_row, diverges)


def _t(**kw):
    return Track(source_type="spotify", has_local_file=True, **kw)


def test_diverges_bpm_a_un_decimale():
    assert diverges(_t(bpm=128.0, analysis_bpm=128.04)) is False  # 128.0 vs 128.0
    assert diverges(_t(bpm=128.0, analysis_bpm=128.3)) is True
    assert diverges(_t(bpm=None, analysis_bpm=128.3)) is False    # vuoto: non diverge
    assert diverges(_t(bpm=128.0, analysis_bpm=None)) is False    # non analizzata


def test_diverges_key_stringa_canonica():
    assert diverges(_t(camelot_key="8A", analysis_camelot="8A")) is False
    assert diverges(_t(camelot_key="8A", analysis_camelot="9A")) is True
    assert diverges(_t(camelot_key=None, analysis_camelot="9A")) is False


def test_apply_analysis_scrive_canonici_e_source():
    t = _t(bpm=128.0, bpm_source="rekordbox", camelot_key="8A", key_source="manual",
           analysis_bpm=130.0, analysis_camelot="9A", genre="techno")
    assert apply_analysis(t) is True
    assert t.bpm == 130.0 and t.bpm_source == "cratory"
    assert t.camelot_key == "9A" and t.key_source == "cratory"
    assert t.status == "ready_for_set" and t.energy is not None


def test_apply_analysis_noop_senza_differenze():
    t = _t(bpm=130.0, bpm_source="rekordbox", camelot_key="9A", key_source="rekordbox",
           analysis_bpm=130.0, analysis_camelot="9A")
    assert apply_analysis(t) is False
    assert t.bpm_source == "rekordbox"  # valore identico: la fonte non cambia


def test_auto_apply_solo_campi_vuoti():
    t = _t(bpm=128.0, bpm_source="rekordbox", camelot_key=None,
           analysis_bpm=130.0, analysis_camelot="9A")
    assert auto_apply_missing(t) is True
    assert t.bpm == 128.0 and t.bpm_source == "rekordbox"  # pieno: intatto
    assert t.camelot_key == "9A" and t.key_source == "cratory"  # vuoto: riempito
    assert t.status == "ready_for_set"


def test_divergence_row_completa():
    t = _t(bpm=128.0, bpm_source="rekordbox", camelot_key="8A", key_source="rekordbox",
           analysis_bpm=130.5, analysis_camelot="8B", artist="A", title="T")
    t.id = 7
    row = divergence_row(t)
    assert row["track_id"] == 7 and row["bpm_delta"] == 2.5
    assert row["key_compatibility"] == "compatible"  # 8A vs 8B: relativa
```

- [ ] **Step 2: Verificare che falliscano**

Run: `python -m pytest tests/test_audio_analysis.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'app.services.audio_analysis'`

- [ ] **Step 3: Implementare**

```python
# backend/app/services/audio_analysis.py
"""Regole deterministiche di divergenza e apply per l'analisi BPM/key in-app.

Il job (audio_analysis_job) scrive SOLO analysis_*; queste funzioni sono l'unico
ponte verso i campi canonici bpm/camelot_key, sempre con source='cratory'.
Gerarchia fonti: manual > rekordbox > cratory. L'autorizzazione a sovrascrivere
sta nella SELEZIONE delle tracce (router/UI), non qui: apply_analysis applica e
basta, auto_apply_missing riempie solo i vuoti (nessun conflitto possibile)."""

from app.services.camelot import camelot_compatibility
from app.services.energy import apply_estimated_energy
from app.services.track_status import refresh_status


def diverges(track) -> bool:
    """True se l'analisi differisce dal canonico (BPM a 1 decimale, key esatta)."""
    bpm_div = (track.analysis_bpm is not None and track.bpm is not None
               and round(track.analysis_bpm, 1) != round(track.bpm, 1))
    key_div = (bool(track.analysis_camelot) and bool(track.camelot_key)
               and track.analysis_camelot != track.camelot_key)
    return bpm_div or key_div


def _apply(track, bpm_ok: bool, key_ok: bool) -> bool:
    changed = False
    if bpm_ok and track.analysis_bpm is not None and track.bpm != track.analysis_bpm:
        track.bpm = track.analysis_bpm
        track.bpm_source = "cratory"
        changed = True
    if key_ok and track.analysis_camelot and track.camelot_key != track.analysis_camelot:
        track.camelot_key = track.analysis_camelot
        track.key_source = "cratory"
        changed = True
    if changed:
        apply_estimated_energy(track)
        refresh_status(track)
    return changed


def apply_analysis(track) -> bool:
    """Copia i valori analysis_* nei canonici dove esistono. True se ha scritto."""
    return _apply(track, bpm_ok=True, key_ok=True)


def auto_apply_missing(track) -> bool:
    """Fallback automatico post-job: riempie SOLO i campi vuoti."""
    return _apply(track, bpm_ok=track.bpm is None, key_ok=not track.camelot_key)


def divergence_row(track) -> dict:
    level, _ = camelot_compatibility(track.camelot_key, track.analysis_camelot)
    delta = (round(track.analysis_bpm - track.bpm, 1)
             if track.analysis_bpm is not None and track.bpm is not None else None)
    return {
        "track_id": track.id, "artist": track.artist, "title": track.title,
        "bpm": track.bpm, "bpm_source": track.bpm_source,
        "analysis_bpm": track.analysis_bpm, "bpm_delta": delta,
        "camelot_key": track.camelot_key, "key_source": track.key_source,
        "analysis_camelot": track.analysis_camelot,
        "key_compatibility": level,
    }
```

- [ ] **Step 4: Verificare che passino**

Run: `python -m pytest tests/test_audio_analysis.py -v`
Expected: PASS (6 test)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/audio_analysis.py backend/tests/test_audio_analysis.py
git commit -m "feat: servizio apply/divergenze per analisi in-app (source cratory)"
```

---

### Task 6: Job di analisi in background

**Files:**
- Create: `backend/app/services/audio_analysis_job.py`
- Test: `backend/tests/test_audio_analysis_job.py` (nuovo)

**Interfaces:**
- Consumes: `essentia_engine.analyze` (Task 4), `auto_apply_missing` (Task 5), `SessionLocal`, `utcnow` da `app.models`.
- Produces: `start_job(scope: str = "missing", track_ids: list[int] | None = None) -> dict`, `job_state() -> dict` (chiavi: `status idle|running|done|error, processed, total, analyzed, failed, applied, current_label, error, started_at, finished_at`), `is_running() -> bool`, `_spawn(fn)` (monkeypatchabile nei test).

- [ ] **Step 1: Scrivere i test che falliscono**

```python
# backend/tests/test_audio_analysis_job.py
"""Job di analisi: selezione scope, scrittura analysis_*, auto-apply, errori per traccia."""
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import Track


@pytest.fixture()
def sync_job(monkeypatch):
    """Job sincrono su DB in memoria condiviso, con motore finto (128 bpm / 8A)."""
    from app.integrations.essentia_engine import AnalysisResult
    from app.services import audio_analysis_job as aj

    e = create_engine("sqlite://", connect_args={"check_same_thread": False},
                      poolclass=StaticPool)
    Base.metadata.create_all(e)
    S = sessionmaker(bind=e, expire_on_commit=False)
    monkeypatch.setattr(aj, "SessionLocal", S)
    monkeypatch.setattr(aj, "_spawn", lambda fn: fn())  # sincrono nei test
    monkeypatch.setattr(aj.essentia_engine, "analyze",
                        lambda path: AnalysisResult(bpm=128.0, camelot="8A"))
    return aj, S


def _seed(S):
    with S() as s:
        s.add(Track(id=1, source_type="spotify", has_local_file=True,
                    local_path="/x/vuota.mp3", artist="A", title="Vuota"))
        s.add(Track(id=2, source_type="spotify", has_local_file=True,
                    local_path="/x/piena.mp3", artist="A", title="Piena",
                    bpm=130.0, bpm_source="rekordbox",
                    camelot_key="9A", key_source="rekordbox"))
        s.add(Track(id=3, source_type="spotify", has_local_file=False, title="NoFile"))
        s.commit()


def test_scope_missing_analizza_solo_le_mancanti(sync_job):
    aj, S = sync_job
    _seed(S)
    aj.start_job(scope="missing")
    st = aj.job_state()
    assert st["status"] == "done" and st["total"] == 1 and st["analyzed"] == 1
    with S() as s:
        vuota = s.get(Track, 1)
        assert vuota.analysis_bpm == 128.0 and vuota.analysis_camelot == "8A"
        # auto-apply sui vuoti: canonici riempiti con source cratory
        assert vuota.bpm == 128.0 and vuota.bpm_source == "cratory"
        assert vuota.status == "ready_for_set" and vuota.analyzed_at is not None
        piena = s.get(Track, 2)
        assert piena.analysis_bpm is None  # fuori scope


def test_scope_all_non_tocca_i_canonici_pieni(sync_job):
    aj, S = sync_job
    _seed(S)
    aj.start_job(scope="all")
    assert aj.job_state()["total"] == 2  # solo has_local_file
    with S() as s:
        piena = s.get(Track, 2)
        assert piena.analysis_bpm == 128.0  # analizzata
        assert piena.bpm == 130.0 and piena.bpm_source == "rekordbox"  # canonico intatto


def test_errore_per_traccia_non_ferma_il_batch(sync_job, monkeypatch):
    aj, S = sync_job
    _seed(S)

    def _boom(path):
        raise RuntimeError("file corrotto")
    monkeypatch.setattr(aj.essentia_engine, "analyze", _boom)
    aj.start_job(scope="all")
    st = aj.job_state()
    assert st["status"] == "done" and st["failed"] == 2
    with S() as s:
        assert s.get(Track, 1).analysis_error == "analysis_decode_failed"


def test_track_ids_espliciti(sync_job):
    aj, S = sync_job
    _seed(S)
    aj.start_job(scope="all", track_ids=[2])
    assert aj.job_state()["total"] == 1
    with S() as s:
        assert s.get(Track, 2).analysis_bpm == 128.0
        assert s.get(Track, 1).analysis_bpm is None
```

- [ ] **Step 2: Verificare che falliscano**

Run: `python -m pytest tests/test_audio_analysis_job.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'app.services.audio_analysis_job'`

- [ ] **Step 3: Implementare**

```python
# backend/app/services/audio_analysis_job.py
"""Job di analisi BPM/key in background (pattern library_index_job: mono-utente,
un job alla volta, stato in memoria con lock).

Scrive SOLO analysis_* + analyzed_at/analysis_error; l'unico ponte automatico
verso i canonici e' auto_apply_missing (campi vuoti, nessun conflitto). Il resto
passa dall'apply esplicito del router."""

import logging
import threading
from datetime import datetime, timezone

from sqlalchemy import or_, select

from app.db import SessionLocal
from app.integrations import essentia_engine
from app.models import Track, utcnow
from app.services.audio_analysis import auto_apply_missing

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_state: dict = {
    "status": "idle",  # idle | running | done | error
    "processed": 0, "total": 0,
    "analyzed": 0, "failed": 0, "applied": 0,
    "current_label": None, "error": None,
    "started_at": None, "finished_at": None,
}


def job_state() -> dict:
    return dict(_state)


def is_running() -> bool:
    return _state["status"] == "running"


def _spawn(fn) -> None:
    """Separato per i test (che lo rendono sincrono)."""
    threading.Thread(target=fn, daemon=True).start()


def _select_tracks(db, scope: str, track_ids: list[int] | None) -> list[Track]:
    q = select(Track).where(Track.has_local_file.is_(True), Track.local_path.is_not(None))
    if track_ids:
        q = q.where(Track.id.in_(track_ids))
    elif scope == "missing":
        q = q.where(or_(Track.bpm.is_(None), Track.camelot_key.is_(None),
                        Track.camelot_key == ""))
    return list(db.scalars(q).all())


def _run_job(scope: str, track_ids: list[int] | None) -> None:
    db = SessionLocal()
    try:
        tracks = _select_tracks(db, scope, track_ids)
        _state["total"] = len(tracks)
        analyzed = failed = applied = 0
        for i, t in enumerate(tracks, start=1):
            _state.update(processed=i,
                          current_label=f"{t.artist or '?'} — {t.title or '?'}")
            try:
                res = essentia_engine.analyze(t.local_path)
                t.analysis_bpm, t.analysis_camelot = res.bpm, res.camelot
                t.analysis_error = None
                analyzed += 1
            except Exception as exc:  # noqa: BLE001 — file illeggibile: il batch prosegue
                t.analysis_error = "analysis_decode_failed"
                failed += 1
                logger.warning("Analisi fallita per %s: %s", t.local_path, exc)
            t.analyzed_at = utcnow()
            if auto_apply_missing(t):
                applied += 1
            db.commit()  # commit per traccia: il progresso sopravvive a un'interruzione
            _state.update(analyzed=analyzed, failed=failed, applied=applied)
        _state.update(status="done")
    except Exception as exc:  # noqa: BLE001
        _state.update(status="error", error=str(exc))
        logger.exception("Job di analisi fallito")
    finally:
        _state.update(finished_at=datetime.now(timezone.utc).isoformat(),
                      current_label=None)
        db.close()


def start_job(scope: str = "missing", track_ids: list[int] | None = None) -> dict:
    """Avvia il job. No-op (stato invariato) se gia' in corso."""
    with _lock:
        if _state["status"] == "running":
            return job_state()
        _state.update(status="running", processed=0, total=0, analyzed=0,
                      failed=0, applied=0, current_label=None, error=None,
                      started_at=datetime.now(timezone.utc).isoformat(),
                      finished_at=None)
    _spawn(lambda: _run_job(scope, track_ids))
    return job_state()
```

Nota: `utcnow` è l'helper già esportato da `app/models.py:16` (datetime coerente col resto del modello).

- [ ] **Step 4: Verificare che passino**

Run: `python -m pytest tests/test_audio_analysis_job.py -v`
Expected: PASS (4 test)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/audio_analysis_job.py backend/tests/test_audio_analysis_job.py
git commit -m "feat: job analisi BPM/key in background con auto-apply sui vuoti"
```

---

### Task 7: Router /api/analysis + schemas + registrazione

**Files:**
- Modify: `backend/app/schemas.py` (in coda, vicino a `LibraryIndexJobStatus:553`)
- Create: `backend/app/routers/analysis.py`
- Modify: `backend/app/main.py:11` (import) e `:84` (include_router, accanto a rekordbox)
- Test: `backend/tests/test_analysis_router.py` (nuovo)

**Interfaces:**
- Consumes: `audio_analysis_job.start_job/job_state/is_running` (Task 6), `essentia_engine.is_available` (Task 4), `apply_analysis/diverges/divergence_row` (Task 5).
- Produces: endpoint `GET /api/analysis/overview`, `POST /api/analysis/start` (202/409/503), `GET /api/analysis/status`, `GET /api/analysis/divergences`, `POST /api/analysis/apply`. Schemi Pydantic: `AnalysisJobStatus`, `AnalysisStartIn`, `AnalysisOverviewOut`, `AnalysisDivergenceOut`, `AnalysisApplyIn`, `AnalysisApplyOut`. Codici errore: `analysis_engine_unavailable`, `analysis_already_running`, `analysis_force_required`, `analysis_apply_empty`.

- [ ] **Step 1: Scrivere i test che falliscono**

```python
# backend/tests/test_analysis_router.py
"""Router /api/analysis: start (503/409/202), overview, divergences, apply."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app
from app.models import Track


@pytest.fixture()
def client():
    e = create_engine("sqlite://", connect_args={"check_same_thread": False},
                      poolclass=StaticPool)
    Base.metadata.create_all(e)
    S = sessionmaker(bind=e, expire_on_commit=False)

    def _get_db():
        db = S()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _get_db
    yield TestClient(app), S
    app.dependency_overrides.clear()


def _seed_divergent(S):
    with S() as s:
        s.add(Track(id=1, source_type="spotify", has_local_file=True,
                    local_path="/x/a.mp3", artist="A", title="T",
                    bpm=128.0, bpm_source="rekordbox",
                    camelot_key="8A", key_source="rekordbox",
                    analysis_bpm=130.0, analysis_camelot="9A"))
        s.commit()


def test_start_503_senza_motore(client, monkeypatch):
    from app.routers import analysis as ar
    c, _ = client
    monkeypatch.setattr(ar.essentia_engine, "is_available", lambda: False)
    r = c.post("/api/analysis/start", json={"scope": "missing"})
    assert r.status_code == 503
    assert r.json()["detail"]["code"] == "analysis_engine_unavailable"


def test_start_409_se_gia_in_corso(client, monkeypatch):
    from app.routers import analysis as ar
    c, _ = client
    monkeypatch.setattr(ar.essentia_engine, "is_available", lambda: True)
    monkeypatch.setattr(ar.audio_analysis_job, "is_running", lambda: True)
    r = c.post("/api/analysis/start", json={"scope": "all"})
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "analysis_already_running"


def test_start_202_avvia(client, monkeypatch):
    from app.routers import analysis as ar
    c, _ = client
    monkeypatch.setattr(ar.essentia_engine, "is_available", lambda: True)
    monkeypatch.setattr(ar.audio_analysis_job, "is_running", lambda: False)
    monkeypatch.setattr(ar.audio_analysis_job, "start_job",
                        lambda scope, track_ids: {"status": "running", "processed": 0,
                                                  "total": 0, "analyzed": 0, "failed": 0,
                                                  "applied": 0, "current_label": None,
                                                  "error": None, "started_at": None,
                                                  "finished_at": None})
    r = c.post("/api/analysis/start", json={"scope": "missing"})
    assert r.status_code == 202 and r.json()["status"] == "running"


def test_overview_e_divergences(client):
    c, S = client
    _seed_divergent(S)
    ov = c.get("/api/analysis/overview").json()
    assert ov["owned"] == 1 and ov["divergent"] == 1 and ov["analyzed"] == 0
    rows = c.get("/api/analysis/divergences").json()
    assert len(rows) == 1
    assert rows[0]["bpm_delta"] == 2.0 and rows[0]["key_compatibility"] == "compatible"


def test_apply_track_ids(client):
    c, S = client
    _seed_divergent(S)
    r = c.post("/api/analysis/apply", json={"track_ids": [1]})
    assert r.status_code == 200 and r.json()["applied"] == 1
    with S() as s:
        t = s.get(Track, 1)
        assert t.bpm == 130.0 and t.bpm_source == "cratory"
        assert t.camelot_key == "9A" and t.key_source == "cratory"


def test_apply_all_richiede_force(client):
    c, S = client
    _seed_divergent(S)
    r = c.post("/api/analysis/apply", json={"mode": "all"})
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "analysis_force_required"
    r = c.post("/api/analysis/apply", json={"mode": "all", "force": True})
    assert r.status_code == 200


def test_apply_vuoto_422(client):
    c, _ = client
    r = c.post("/api/analysis/apply", json={})
    assert r.status_code == 422
```

- [ ] **Step 2: Verificare che falliscano**

Run: `python -m pytest tests/test_analysis_router.py -v`
Expected: FAIL (404 sugli endpoint / ImportError sul router)

- [ ] **Step 3: Implementare gli schemi**

In `schemas.py`, dopo `LibraryIndexJobStatus` (usa gli import gia' presenti: `BaseModel`, `ConfigDict`, `Field`; aggiungere `Literal` a `from typing import ...` se non c'è):

```python
class AnalysisJobStatus(BaseModel):
    """Stato del job di analisi BPM/key in-app (pagina Analisi)."""

    status: str
    processed: int = 0
    total: int = 0
    analyzed: int = 0
    failed: int = 0
    applied: int = 0
    current_label: str | None = None
    error: str | None = None
    started_at: str | None = None
    finished_at: str | None = None


class AnalysisStartIn(BaseModel):
    """Avvio del job: scope 'missing' (default) | 'all', o track_ids espliciti."""

    model_config = ConfigDict(extra="forbid")

    scope: Literal["missing", "all"] = "missing"
    track_ids: list[int] | None = None


class AnalysisOverviewOut(BaseModel):
    """Copertura BPM/key della libreria posseduta, per la pagina Analisi."""

    owned: int
    ready_for_set: int
    missing_bpm: int
    missing_key: int
    bpm_by_source: dict[str, int]
    key_by_source: dict[str, int]
    analyzed: int
    divergent: int
    rekordbox_pending: int


class AnalysisDivergenceOut(BaseModel):
    """Riga della tabella divergenze: canonico vs analisi in-app."""

    track_id: int
    artist: str | None = None
    title: str | None = None
    bpm: float | None = None
    bpm_source: str | None = None
    analysis_bpm: float | None = None
    bpm_delta: float | None = None
    camelot_key: str | None = None
    key_source: str | None = None
    analysis_camelot: str | None = None
    key_compatibility: str  # same | compatible | weak | unknown


class AnalysisApplyIn(BaseModel):
    """Apply dei valori analizzati: per id, per modo, o riscrittura totale (force)."""

    model_config = ConfigDict(extra="forbid")

    track_ids: list[int] | None = None
    mode: Literal["divergent", "all"] | None = None
    force: bool = False


class AnalysisApplyOut(BaseModel):
    applied: int
    skipped: int
```

- [ ] **Step 4: Implementare il router**

```python
# backend/app/routers/analysis.py
"""Router ANALYSIS: analisi BPM/key in-app (Essentia), divergenze e apply.

Il job scrive solo analysis_*; l'apply e' l'unico ponte verso i campi canonici.
Gerarchia fonti: manual > rekordbox > cratory (vedi services/audio_analysis).
L'import Rekordbox resta in routers/rekordbox."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.http_errors import api_error
from app.db import get_db
from app.integrations import essentia_engine
from app.models import Track
from app.schemas import (AnalysisApplyIn, AnalysisApplyOut, AnalysisDivergenceOut,
                         AnalysisJobStatus, AnalysisOverviewOut, AnalysisStartIn)
from app.services import audio_analysis_job
from app.services.audio_analysis import apply_analysis, divergence_row, diverges

router = APIRouter(prefix="/api/analysis", tags=["analysis"])


def _owned(db: Session) -> list[Track]:
    return list(db.scalars(select(Track).where(Track.has_local_file.is_(True))).all())


@router.get("/overview", response_model=AnalysisOverviewOut)
def overview(db: Session = Depends(get_db)):
    # Conteggi in Python su una sola query: app mono-utente, libreria di migliaia
    # di righe, piu' leggibile di otto aggregate SQL separate.
    owned = _owned(db)

    def by_source(attr: str) -> dict[str, int]:
        out = {"manual": 0, "rekordbox": 0, "cratory": 0}
        for t in owned:
            s = getattr(t, attr)
            if s in out:
                out[s] += 1
        return out

    return AnalysisOverviewOut(
        owned=len(owned),
        ready_for_set=sum(1 for t in owned if t.status == "ready_for_set"),
        missing_bpm=sum(1 for t in owned if t.bpm is None),
        missing_key=sum(1 for t in owned if not t.camelot_key),
        bpm_by_source=by_source("bpm_source"),
        key_by_source=by_source("key_source"),
        analyzed=sum(1 for t in owned if t.analyzed_at is not None),
        divergent=sum(1 for t in owned if diverges(t)),
        rekordbox_pending=sum(1 for t in owned if t.bpm is None or not t.camelot_key),
    )


@router.post("/start", response_model=AnalysisJobStatus, status_code=202)
def start(payload: AnalysisStartIn):
    if not essentia_engine.is_available():
        raise api_error(503, "analysis_engine_unavailable",
                        "Essentia not installed: install the pinned version from backend/requirements.txt.")
    if audio_analysis_job.is_running():
        raise api_error(409, "analysis_already_running", "Analysis job already running.")
    return audio_analysis_job.start_job(scope=payload.scope, track_ids=payload.track_ids)


@router.get("/status", response_model=AnalysisJobStatus)
def status():
    return audio_analysis_job.job_state()


@router.get("/divergences", response_model=list[AnalysisDivergenceOut])
def divergences(db: Session = Depends(get_db)):
    return [divergence_row(t) for t in _owned(db) if diverges(t)]


@router.post("/apply", response_model=AnalysisApplyOut)
def apply(payload: AnalysisApplyIn, db: Session = Depends(get_db)):
    """Applica i valori analizzati. track_ids/mode='divergent' = scelta esplicita
    dell'utente dalla tabella; mode='all' riscrive TUTTE le analizzate (qualunque
    fonte, anche manual) e richiede force=true come conferma."""
    if payload.mode == "all" and not payload.force:
        raise api_error(422, "analysis_force_required",
                        "mode='all' rewrites every analyzed track: pass force=true.")
    if not payload.track_ids and payload.mode is None:
        raise api_error(422, "analysis_apply_empty", "Provide track_ids or mode.")
    owned = _owned(db)
    if payload.track_ids:
        ids = set(payload.track_ids)
        targets = [t for t in owned if t.id in ids]
    elif payload.mode == "divergent":
        targets = [t for t in owned if diverges(t)]
    else:  # mode == "all"
        targets = [t for t in owned if t.analyzed_at is not None]
    applied = sum(1 for t in targets if apply_analysis(t))
    db.commit()
    return AnalysisApplyOut(applied=applied, skipped=len(targets) - applied)
```

In `main.py`: aggiungere `analysis` alla tupla import da `app.routers` (riga 11) e `app.include_router(analysis.router)` accanto a `app.include_router(rekordbox.router)` (riga 84).

- [ ] **Step 5: Verificare che passino, poi tutta la suite**

Run: `python -m pytest tests/test_analysis_router.py -v && python -m pytest tests -q`
Expected: PASS ovunque.

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers/analysis.py backend/app/schemas.py backend/app/main.py backend/tests/test_analysis_router.py
git commit -m "feat(api): router /api/analysis (overview, start, status, divergences, apply)"
```

---

### Task 8: Frontend — API client, i18n, voce nav

**Files:**
- Modify: `frontend/lib/api.ts` (tipi + funzioni, vicino a `libraryIndexStatus:201`)
- Modify: `frontend/lib/i18n/en.ts` (sezioni `nav`, `jobs`, nuova `analysis`, `errors`)
- Modify: `frontend/lib/i18n/it.ts` (stesse chiavi, in italiano)
- Modify: `frontend/components/index-nav.tsx:23-31` (gruppo Collect)

**Interfaces:**
- Consumes: endpoint del Task 7; helper `apiGet`/`apiPost` esistenti.
- Produces: `analysisOverview(): Promise<AnalysisOverview>`, `startAnalysis(scope, trackIds?): Promise<AnalysisJobStatus>`, `analysisStatus(): Promise<AnalysisJobStatus>`, `analysisDivergences(): Promise<AnalysisDivergence[]>`, `applyAnalysis(body): Promise<{applied: number; skipped: number}>`; dizionario `t.analysis.*`, `t.nav.analysis`, `t.jobs.audioAnalysis`; voce nav `/analysis`.

- [ ] **Step 1: Leggere la guida Next 16 pertinente**

Run: `ls frontend/node_modules/next/dist/docs/` e leggere le pagine su App Router/pagine client se non già lette in sessione.

- [ ] **Step 2: API client**

In `api.ts`, dopo il blocco `libraryIndexStatus` (riga ~201):

```ts
export interface AnalysisJobStatus {
  status: "idle" | "running" | "done" | "error";
  processed: number;
  total: number;
  analyzed: number;
  failed: number;
  applied: number;
  current_label: string | null;
  error: string | null;
}

export interface AnalysisOverview {
  owned: number;
  ready_for_set: number;
  missing_bpm: number;
  missing_key: number;
  bpm_by_source: Record<string, number>;
  key_by_source: Record<string, number>;
  analyzed: number;
  divergent: number;
  rekordbox_pending: number;
}

export interface AnalysisDivergence {
  track_id: number;
  artist: string | null;
  title: string | null;
  bpm: number | null;
  bpm_source: string | null;
  analysis_bpm: number | null;
  bpm_delta: number | null;
  camelot_key: string | null;
  key_source: string | null;
  analysis_camelot: string | null;
  key_compatibility: "same" | "compatible" | "weak" | "unknown";
}

export async function analysisOverview() {
  return apiGet<AnalysisOverview>("/api/analysis/overview");
}

export async function startAnalysis(scope: "missing" | "all", trackIds?: number[]) {
  return apiPost<AnalysisJobStatus>("/api/analysis/start", {
    scope, track_ids: trackIds ?? null,
  });
}

export async function analysisStatus() {
  return apiGet<AnalysisJobStatus>("/api/analysis/status");
}

export async function analysisDivergences() {
  return apiGet<AnalysisDivergence[]>("/api/analysis/divergences");
}

export async function applyAnalysis(body: {
  track_ids?: number[]; mode?: "divergent" | "all"; force?: boolean;
}) {
  return apiPost<{ applied: number; skipped: number }>("/api/analysis/apply", body);
}
```

- [ ] **Step 3: i18n (en.ts)**

In `nav`: aggiungere `analysis: "Analysis",` dopo `library`. In `jobs`: aggiungere `audioAnalysis: "BPM/key analysis",`. Nuova sezione top-level `analysis` (dopo `dashboard`):

```ts
  analysis: {
    pageTitle: "Analysis",
    intro: "BPM and key of owned tracks: Rekordbox import and in-app analysis (Essentia).",
    tileOwned: "Owned",
    tileReady: "Ready for set",
    tileMissingBpm: "Missing BPM",
    tileMissingKey: "Missing key",
    tileAnalyzed: "Analyzed",
    tileDivergent: "Divergent",
    sourceManual: "manual",
    sourceRekordbox: "rekordbox",
    sourceCratory: "cratory",
    bySourceBpm: (m: number, r: number, c: number) => `BPM: ${m} manual · ${r} rekordbox · ${c} cratory`,
    bySourceKey: (m: number, r: number, c: number) => `Key: ${m} manual · ${r} rekordbox · ${c} cratory`,
    rekordboxHeading: "Rekordbox import",
    analysisHeading: "In-app analysis",
    engineUnavailable: "Essentia is not installed in the backend: install the pinned version from backend/requirements.txt and restart.",
    scopeLabel: "Scope",
    scopeMissing: "Only tracks missing BPM/key",
    scopeAll: "All owned tracks",
    startButton: "Start analysis",
    startedNote: "Analysis started: progress in the bottom bar. Empty fields are filled automatically; conflicts appear below.",
    divergencesHeading: "Divergences",
    divergencesEmpty: "No divergences: in-app analysis matches the current values.",
    colTrack: "Track",
    colCurrent: "Current",
    colAnalysis: "Cratory",
    colDelta: "Δ BPM",
    colKeyCompat: "Key",
    compatSame: "same",
    compatCompatible: "compatible",
    compatWeak: "divergent",
    compatUnknown: "—",
    applyRow: "Apply",
    applySelected: (n: number) => `Apply selected (${n})`,
    forceApplyAll: "Force apply all",
    forceConfirm: "Overwrite BPM/key of ALL analyzed tracks (including manual and Rekordbox values)? This cannot be undone.",
    appliedSummary: (applied: number, skipped: number) => `${applied} applied · ${skipped} unchanged`,
  },
```

In `errors`: aggiungere accanto ai codici rekordbox:

```ts
    analysis_engine_unavailable: "Analysis engine unavailable: Essentia is not installed in the backend.",
    analysis_already_running: "An analysis job is already running.",
    analysis_force_required: "Applying to all tracks requires explicit confirmation (force).",
    analysis_apply_empty: "Nothing to apply: select tracks or a mode.",
```

- [ ] **Step 4: i18n (it.ts)** — stesse chiavi:

```ts
  analysis: {
    pageTitle: "Analisi",
    intro: "BPM e tonalità delle tracce possedute: import Rekordbox e analisi in-app (Essentia).",
    tileOwned: "Possedute",
    tileReady: "Pronte per il set",
    tileMissingBpm: "Senza BPM",
    tileMissingKey: "Senza tonalità",
    tileAnalyzed: "Analizzate",
    tileDivergent: "Divergenti",
    sourceManual: "manuale",
    sourceRekordbox: "rekordbox",
    sourceCratory: "cratory",
    bySourceBpm: (m: number, r: number, c: number) => `BPM: ${m} manuali · ${r} rekordbox · ${c} cratory`,
    bySourceKey: (m: number, r: number, c: number) => `Key: ${m} manuali · ${r} rekordbox · ${c} cratory`,
    rekordboxHeading: "Import Rekordbox",
    analysisHeading: "Analisi in-app",
    engineUnavailable: "Essentia non è installata nel backend: installa la versione pinnata da backend/requirements.txt e riavvia.",
    scopeLabel: "Ambito",
    scopeMissing: "Solo tracce senza BPM/key",
    scopeAll: "Tutte le tracce possedute",
    startButton: "Avvia analisi",
    startedNote: "Analisi avviata: progresso nella barra in basso. I campi vuoti si riempiono da soli; i conflitti compaiono qui sotto.",
    divergencesHeading: "Divergenze",
    divergencesEmpty: "Nessuna divergenza: l'analisi in-app coincide con i valori attuali.",
    colTrack: "Traccia",
    colCurrent: "Attuale",
    colAnalysis: "Cratory",
    colDelta: "Δ BPM",
    colKeyCompat: "Key",
    compatSame: "uguale",
    compatCompatible: "compatibile",
    compatWeak: "divergente",
    compatUnknown: "—",
    applyRow: "Applica",
    applySelected: (n: number) => `Applica selezionate (${n})`,
    forceApplyAll: "Forza su tutte",
    forceConfirm: "Sovrascrivere BPM/key di TUTTE le tracce analizzate (compresi valori manuali e Rekordbox)? L'operazione non è annullabile.",
    appliedSummary: (applied: number, skipped: number) => `${applied} applicate · ${skipped} invariate`,
  },
```

`nav.analysis: "Analisi"`, `jobs.audioAnalysis: "Analisi BPM/key"`, ed errors:

```ts
    analysis_engine_unavailable: "Motore di analisi non disponibile: Essentia non è installata nel backend.",
    analysis_already_running: "Un job di analisi è già in corso.",
    analysis_force_required: "Applicare a tutte le tracce richiede conferma esplicita (force).",
    analysis_apply_empty: "Niente da applicare: seleziona tracce o una modalità.",
```

- [ ] **Step 5: Voce nav**

In `index-nav.tsx`, gruppo Collect (riga 24-31), aggiungere dopo `library`:

```ts
      { href: "/analysis", label: t.nav.analysis },
```

- [ ] **Step 6: Verificare**

Run: `cd frontend && npm run lint && npm run build`
Expected: lint ok; build ok (il link /analysis punta a una pagina che ancora non esiste: in Next l'href stringa non è type-checked di default, ma se `typedRoutes` è attivo creare prima un placeholder `frontend/app/analysis/page.tsx` con `export default function AnalysisPage() { return null; }` e completarlo nel Task 9).

- [ ] **Step 7: Commit**

```bash
git add frontend/lib/api.ts frontend/lib/i18n/en.ts frontend/lib/i18n/it.ts frontend/components/index-nav.tsx
git commit -m "feat(ui): client API analisi, i18n e voce nav Analisi"
```

(Se creato il placeholder page.tsx, includerlo nel commit.)

---

### Task 9: Frontend — pagina /analysis

**Files:**
- Create: `frontend/components/analysis/rekordbox-import-card.tsx` (trasloco del pannello da `pipeline.tsx`)
- Create: `frontend/app/analysis/page.tsx`

**Interfaces:**
- Consumes: funzioni API e i18n del Task 8; `importRekordbox`, `rekordboxPending` esistenti in api.ts (se `rekordboxPending` non esiste, l'overview fornisce già `rekordbox_pending`: usare quello); `useJobs().refresh` da `components/jobs-provider.tsx`; componenti `Card`, `Alert`, `Spinner` da `components/ui`.
- Produces: componente `RekordboxImportCard({ pending, onImported })` (stesso comportamento del vecchio `RekordboxImportPanel`, chiavi i18n spostate su `t.analysis.*` dove nuove) e pagina client `/analysis`.

- [ ] **Step 1: Estrarre la card Rekordbox**

Creare `frontend/components/analysis/rekordbox-import-card.tsx` copiando il corpo di `RekordboxImportPanel` da `pipeline.tsx:29-97` (import inclusi: `useRef/useState`, `Upload` da lucide, `importRekordbox`, `RekordboxImportReport`, `useT`, `Alert`, `Spinner`), rinominando il componente in `RekordboxImportCard` con `export function`. Le chiavi i18n `t.dashboard.rekordboxIntroPrefix/rekordboxIntroSuffix/pendingTracks/overwriteLabel/importing/reportInFile/reportMatched/reportUnmatched/reportBpmSet/reportKeySet/reportEnergySet` restano in `dashboard` (nessuna migrazione di chiavi: churn inutile, il componente le referenzia com'è).

- [ ] **Step 2: Scrivere la pagina**

```tsx
// frontend/app/analysis/page.tsx
"use client";

import { useCallback, useEffect, useState } from "react";
import {
  analysisDivergences, analysisOverview, applyAnalysis, startAnalysis,
  type AnalysisDivergence, type AnalysisOverview,
} from "@/lib/api";
import { cn } from "@/lib/cn";
import { useT } from "@/lib/i18n";
import { useJobs } from "@/components/jobs-provider";
import { RekordboxImportCard } from "@/components/analysis/rekordbox-import-card";
import { Alert, Card } from "@/components/ui";

export default function AnalysisPage() {
  const t = useT();
  const jobs = useJobs();
  const [overview, setOverview] = useState<AnalysisOverview | null>(null);
  const [rows, setRows] = useState<AnalysisDivergence[]>([]);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [scope, setScope] = useState<"missing" | "all">("missing");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const reload = useCallback(async () => {
    try {
      const [ov, dv] = await Promise.all([analysisOverview(), analysisDivergences()]);
      setOverview(ov);
      setRows(dv);
      setSelected(new Set());
      setError(null);
    } catch (e) {
      setError(String((e as Error).message ?? e));
    }
  }, []);

  useEffect(() => { reload(); }, [reload]);

  const onStart = async () => {
    setBusy(true); setError(null); setNotice(null);
    try {
      await startAnalysis(scope);
      jobs.refresh(); // la barra globale aggancia subito il job
      setNotice(t.analysis.startedNote);
    } catch (e) {
      setError(String((e as Error).message ?? e));
    } finally {
      setBusy(false);
    }
  };

  const onApply = async (body: Parameters<typeof applyAnalysis>[0]) => {
    setBusy(true); setError(null);
    try {
      const r = await applyAnalysis(body);
      setNotice(t.analysis.appliedSummary(r.applied, r.skipped));
      await reload();
    } catch (e) {
      setError(String((e as Error).message ?? e));
    } finally {
      setBusy(false);
    }
  };

  const onForceAll = async () => {
    if (!window.confirm(t.analysis.forceConfirm)) return;
    await onApply({ mode: "all", force: true });
  };

  const toggle = (id: number) =>
    setSelected((s) => {
      const n = new Set(s);
      if (n.has(id)) n.delete(id); else n.add(id);
      return n;
    });

  const compatLabel = {
    same: t.analysis.compatSame, compatible: t.analysis.compatCompatible,
    weak: t.analysis.compatWeak, unknown: t.analysis.compatUnknown,
  } as const;

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-lg font-semibold text-fg-strong">{t.analysis.pageTitle}</h1>
        <p className="mt-1 text-xs text-muted">{t.analysis.intro}</p>
      </header>

      {error && <Alert tone="danger">⚠ {error}</Alert>}
      {notice && <Alert>{notice}</Alert>}

      {overview && (
        <Card>
          <div className="grid grid-cols-2 gap-px sm:grid-cols-3 lg:grid-cols-6">
            {[
              [t.analysis.tileOwned, overview.owned],
              [t.analysis.tileReady, overview.ready_for_set],
              [t.analysis.tileMissingBpm, overview.missing_bpm],
              [t.analysis.tileMissingKey, overview.missing_key],
              [t.analysis.tileAnalyzed, overview.analyzed],
              [t.analysis.tileDivergent, overview.divergent],
            ].map(([label, value]) => (
              <div key={String(label)} className="px-4 py-3">
                <p className="text-[10px] uppercase tracking-wider text-muted">{label}</p>
                <p className="tnum text-lg font-semibold text-fg-strong">{String(value)}</p>
              </div>
            ))}
          </div>
          <p className="border-t border-border px-4 py-2 text-[11px] text-faint">
            {t.analysis.bySourceBpm(overview.bpm_by_source.manual ?? 0,
              overview.bpm_by_source.rekordbox ?? 0, overview.bpm_by_source.cratory ?? 0)}
            {" · "}
            {t.analysis.bySourceKey(overview.key_by_source.manual ?? 0,
              overview.key_by_source.rekordbox ?? 0, overview.key_by_source.cratory ?? 0)}
          </p>
        </Card>
      )}

      <Card>
        <h2 className="px-4 pt-3 text-xs font-semibold uppercase tracking-wider text-muted">
          {t.analysis.rekordboxHeading}
        </h2>
        <RekordboxImportCard pending={overview?.rekordbox_pending ?? 0} onImported={reload} />
      </Card>

      <Card>
        <h2 className="px-4 pt-3 text-xs font-semibold uppercase tracking-wider text-muted">
          {t.analysis.analysisHeading}
        </h2>
        <div className="flex flex-wrap items-end gap-4 px-4 py-3 text-xs">
          <label className="block">
            <span className="mb-1 block text-[10px] uppercase tracking-wider text-muted">
              {t.analysis.scopeLabel}
            </span>
            <select
              value={scope}
              onChange={(e) => setScope(e.target.value as "missing" | "all")}
              className="border border-border-strong bg-transparent px-2 py-1.5 text-xs"
            >
              <option value="missing">{t.analysis.scopeMissing}</option>
              <option value="all">{t.analysis.scopeAll}</option>
            </select>
          </label>
          <button
            type="button"
            onClick={onStart}
            disabled={busy}
            className="border border-border-strong px-3 py-1.5 text-xs font-medium uppercase tracking-wider text-fg hover:bg-elevated disabled:opacity-50"
          >
            {t.analysis.startButton}
          </button>
        </div>
      </Card>

      <Card>
        <div className="flex flex-wrap items-center justify-between gap-2 px-4 py-3">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-muted">
            {t.analysis.divergencesHeading}
          </h2>
          <div className="flex gap-2">
            <button
              type="button"
              disabled={busy || selected.size === 0}
              onClick={() => onApply({ track_ids: [...selected] })}
              className="border border-border-strong px-3 py-1.5 text-xs uppercase tracking-wider text-fg hover:bg-elevated disabled:opacity-50"
            >
              {t.analysis.applySelected(selected.size)}
            </button>
            <button
              type="button"
              disabled={busy || (overview?.analyzed ?? 0) === 0}
              onClick={onForceAll}
              className="border border-danger px-3 py-1.5 text-xs uppercase tracking-wider text-danger hover:bg-elevated disabled:opacity-50"
            >
              {t.analysis.forceApplyAll}
            </button>
          </div>
        </div>
        {rows.length === 0 ? (
          <p className="border-t border-border px-4 py-4 text-xs text-muted">
            {t.analysis.divergencesEmpty}
          </p>
        ) : (
          <div className="overflow-x-auto border-t border-border">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-left text-[10px] uppercase tracking-wider text-muted">
                  <th className="px-4 py-2" />
                  <th className="px-2 py-2">{t.analysis.colTrack}</th>
                  <th className="px-2 py-2">{t.analysis.colCurrent}</th>
                  <th className="px-2 py-2">{t.analysis.colAnalysis}</th>
                  <th className="px-2 py-2 text-right">{t.analysis.colDelta}</th>
                  <th className="px-2 py-2">{t.analysis.colKeyCompat}</th>
                  <th className="px-4 py-2" />
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.track_id} className="border-t border-border">
                    <td className="px-4 py-2">
                      <input
                        type="checkbox"
                        checked={selected.has(r.track_id)}
                        onChange={() => toggle(r.track_id)}
                        className="accent-fg-strong"
                        aria-label={`${r.artist ?? "?"} — ${r.title ?? "?"}`}
                      />
                    </td>
                    <td className="max-w-[16rem] truncate px-2 py-2 text-fg">
                      {r.artist ?? "?"} — {r.title ?? "?"}
                    </td>
                    <td className="tnum px-2 py-2 text-muted">
                      {r.bpm ?? "—"} · {r.camelot_key ?? "—"}
                      {(r.bpm_source ?? r.key_source) && (
                        <span className="ml-1 text-[10px] text-faint">
                          ({r.bpm_source ?? r.key_source})
                        </span>
                      )}
                    </td>
                    <td className="tnum px-2 py-2 text-fg">
                      {r.analysis_bpm ?? "—"} · {r.analysis_camelot ?? "—"}
                    </td>
                    <td className="tnum px-2 py-2 text-right">
                      {r.bpm_delta != null ? (r.bpm_delta > 0 ? `+${r.bpm_delta}` : r.bpm_delta) : "—"}
                    </td>
                    <td className="px-2 py-2">
                      <span className={cn(r.key_compatibility === "weak" ? "text-danger" : "text-muted")}>
                        {compatLabel[r.key_compatibility]}
                      </span>
                    </td>
                    <td className="px-4 py-2 text-right">
                      <button
                        type="button"
                        disabled={busy}
                        onClick={() => onApply({ track_ids: [r.track_id] })}
                        className="text-[11px] uppercase tracking-wider text-fg-strong hover:underline disabled:opacity-50"
                      >
                        {t.analysis.applyRow}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
```

Nota: verificare le prop reali di `Alert`/`Card` in `components/ui.tsx` e le classi/layout delle altre pagine (`frontend/app/downloads/page.tsx` è un buon riferimento) e adeguare markup/classi allo stile della codebase se differiscono.

- [ ] **Step 3: Verificare**

Run: `cd frontend && npm run lint && npm run build`
Expected: OK. Poi verifica visiva: avviare backend e frontend (dev server), aprire `/analysis`, controllare tile, card import (upload di un XML di prova se disponibile), avvio analisi con motore installato.

- [ ] **Step 4: Commit**

```bash
git add frontend/app/analysis/page.tsx frontend/components/analysis/rekordbox-import-card.tsx
git commit -m "feat(ui): pagina Analisi con copertura, import Rekordbox e tabella divergenze"
```

---

### Task 10: Frontend — dashboard link + poller job

**Files:**
- Modify: `frontend/components/dashboard/pipeline.tsx` (rimozione pannello, stage → link)
- Modify: `frontend/components/jobs-provider.tsx` (poll del job analisi)

**Interfaces:**
- Consumes: `analysisStatus()` e `t.jobs.audioAnalysis` (Task 8); pagina `/analysis` (Task 9).
- Produces: stage "Analizza" con `href: "/analysis"`; riga job "Analisi BPM/key" nella barra globale.

- [ ] **Step 1: pipeline.tsx**

- Eliminare l'intera funzione `RekordboxImportPanel` (righe 26-97) e gli import ora inutilizzati (`useRef`, `Upload`, `importRekordbox`, `RekordboxImportReport`, `Alert`, `Spinner` — verificare con lint cosa resta usato).
- Nello stage `analizza` (righe 132-135) aggiungere `href: "/analysis"`.
- Rimuovere lo state `analyzeOpen`, la riga `{analyzeOpen && <RekordboxImportPanel ... />}` (riga 186) e semplificare `onStageClick` (ora solo `organizza` apre un pannello):

```ts
  const onStageClick = (key: string) => {
    if (key === "organizza") setOrganizeOpen((v) => !v);
  };
```

- [ ] **Step 2: jobs-provider.tsx**

- Import: aggiungere `analysisStatus` e `type AnalysisJobStatus` a quelli da `@/lib/api`.
- In `pollOnce`, estendere il `Promise.allSettled` (riga 109-111):

```ts
    const [s, d, li, an] = await Promise.allSettled([
      shazamIdentifyStatus(), downloadStatus(), libraryIndexStatus(), analysisStatus(),
    ]);
```

- Dopo il blocco `li` (riga 131-138), aggiungere:

```ts
    if (an.status === "fulfilled") {
      const v = an.value;
      track(v.status, {
        key: "analysis", label: t.jobs.audioAnalysis, detail: v.current_label ?? undefined,
        processed: v.processed, total: v.total, href: "/analysis",
      }, v.status === "error" ? (v.error ?? t.common.error) : t.jobs.completed);
    }
```

- [ ] **Step 3: Verificare**

Run: `cd frontend && npm run lint && npm run build`
Expected: OK. Verifica visiva: dashboard → click su "Analizza" naviga a `/analysis`; avviando un'analisi la barra in basso mostra la riga con la EqMeter.

- [ ] **Step 4: Commit**

```bash
git add frontend/components/dashboard/pipeline.tsx frontend/components/jobs-provider.tsx
git commit -m "feat(ui): stage Analizza collegato alla pagina Analisi + job analisi nella barra globale"
```

---

### Task 11: Documentazione (regola CLAUDE.md, ARCHITECTURE, API, ROADMAP, PROGRESS)

**Files:**
- Modify: `CLAUDE.md` (regola non negoziabile n.2)
- Modify: `docs/ARCHITECTURE.md` (sezione dati/pipeline: provenienza + analisi in-app)
- Modify: `docs/API.md` (endpoint `/api/analysis/*`, semantica source-aware di `/api/rekordbox/import`)
- Modify: `docs/ROADMAP.md` (voce completata)
- Modify: `PROGRESS.md` (diario)
- Modify: `docs/DEPENDENCIES.md` (Essentia: pin, licenza AGPL, ruolo)

**Interfaces:** nessuna (solo documentazione).

- [ ] **Step 1: CLAUDE.md**

Sostituire la regola 2 con:

```markdown
2. **BPM/key: Rekordbox è la fonte primaria, l'analisi in-app è l'alternativa
   deterministica.** Il flusso principale resta l'export XML da Rekordbox
   (`/api/rekordbox/import`). In più la pagina Analisi può calcolare BPM/key
   in-app (Essentia, deterministico) sulle tracce possedute. Ogni valore ha una
   provenienza esplicita (`bpm_source`/`key_source`: manual > rekordbox >
   cratory): l'import Rekordbox di default sovrascrive i valori `cratory` e
   protegge quelli `manual` (con `?overwrite=true` vince su tutto); l'analisi
   in-app scrive i campi `analysis_*` e tocca i canonici solo via apply (i vuoti
   in automatico, il resto su azione esplicita, la riscrittura totale con
   force). Cratory non chiede MAI BPM/key a un'AI né a provider streaming.
   `energy` è un derivato deterministico (da BPM+genere o dai file audio).
   Beatgrid/cue restano fuori scope; nessuna integrazione live con Rekordbox.
```

- [ ] **Step 2: Gli altri documenti**

- `docs/API.md`: nuova sezione "Analysis" con i 5 endpoint (metodo, path, body, codici errore) e nota sulla nuova semantica di default di `/api/rekordbox/import`.
- `docs/ARCHITECTURE.md`: nella sezione dati, le nuove colonne di `Track` e la gerarchia fonti; nella sezione integrazioni, `essentia_engine` (lazy, pin, AGPL).
- `docs/ROADMAP.md`: aggiungere/spuntare la voce "Pagina Analisi (import Rekordbox + analisi in-app)".
- `PROGRESS.md`: voce datata 2026-07-12 con il riassunto del lavoro.
- `docs/DEPENDENCIES.md`: riga Essentia (versione pinnata, wheel arm64, AGPL-3.0, usata solo da `integrations/essentia_engine`).

Adeguare il testo allo stile esistente di ciascun documento (leggerli prima di modificarli).

- [ ] **Step 3: Verifica finale completa**

Run: `cd backend && python -m pytest tests -q && cd ../frontend && npm run lint && npm run build`
Expected: tutto PASS/OK.

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md docs/ARCHITECTURE.md docs/API.md docs/ROADMAP.md PROGRESS.md docs/DEPENDENCIES.md
git commit -m "docs: pagina Analisi — regola BPM/key riformulata, API e roadmap aggiornate"
```
