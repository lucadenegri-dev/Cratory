# Fusione Sortory → Cratory — F2 (DB unico) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Portare Organize e Cratory su un solo `Base`, un solo engine, un solo file SQLite e una sola classe `Settings`, migrando i dati reali di `djorganizer.db` dentro `djassistant.db` con un dry-run verificabile e assert su invarianti.

**Architecture:** `app/organize/db.py` e `app/organize/core/config.py` spariscono: i 18 punti che li importano passano a `app.db` e `app.core.config`. `ensure_schema()` di Cratory registra anche i modelli Organize — essendo model-derived (`_migrate_add_model_columns` itera `Base.metadata`), le tabelle Organize ereditano gratis create_all, ADD COLUMN automatico e creazione indici. Lo script di migrazione lavora su una **copia** del DB Cratory, con `ATTACH` del DB Organize e rimappatura degli id.

**Tech Stack:** Python 3.11.15, SQLAlchemy 2, pydantic-settings, SQLite, pytest.

**Spec di riferimento:** `docs/superpowers/specs/2026-08-11-fusione-sortory-cratory-design.md` (fase F2, sezione "6. Migrazione dei dati").

**Prerequisito:** F1 completa sul branch `feat/fusione-f1` (worktree `.claude/worktrees/fusione-f1`), inclusi i quattro item di chiusura pre-F2 (commit `31e5825`).

## Global Constraints

- Si lavora nel worktree **`.claude/worktrees/fusione-f1`**, sullo stesso branch `feat/fusione-f1`. Non su `master`.
- **Commit senza `Co-Authored-By`.**
- **Prima di ogni commit**: `git status --porcelain` e `git branch --show-current`; stageare solo i propri file.
- Comandi backend dal worktree: `backend/.venv/bin/python -m pytest tests`.
- **Il DB reale non si tocca mai in scrittura.** Lo script lavora su una copia; l'originale `backend/data/djassistant.db` resta intatto finché non sei tu a sostituirlo (Task 6).
- **`track_id`, `location` e `primary_file_id` NON sono di questa fase.** La spec li descrive nella stessa sezione perché racconta la migrazione end-to-end, ma la tabella delle fasi li assegna a F3, insieme al backfill dei 625 aggancí. F2 sposta righe; F3 introduce il modello.
- **Gli assert sono su invarianti calcolati dalla sorgente, mai su costanti.** La baseline misurata è un ordine di grandezza da confrontare a occhio, non una condizione di successo (vedi spec, sezione 6).
- **Entrypoint che spariscono** (`app/organize/db.py`, `app/organize/core/config.py`): per ognuno, elencare *cosa fornisce* — non cosa importa — e dove ricompare. È la regressione che è costata due Critical in F1.

## Baseline attesa (misurata 2026-08-11, seconda misura)

| | |
|---|---:|
| `audio_file` | 1.778 |
| `scan_root` | 2 |
| `plan` | 99 |
| `undo_journal` | 2.996 |
| `issue` (non migrate) | 1.025 |
| `dup_group` (non migrati) | 0 |
| `tracks` Cratory | 677 |

---

## File Structure

```
backend/
  app/
    core/config.py            modificato: assorbe i campi Organize (senza prefisso)
    db.py                     modificato: ensure_schema registra anche i modelli Organize
    organize/
      db.py                   ELIMINATO
      core/config.py          ELIMINATO
      core/http_errors.py     invariato
      models.py               invariato (import da app.db)
      routers/, services/     modificati: import da app.db / app.core.config
    tools/
      migrate_organize_db.py  nuovo: dry-run + migrazione
  tests/
    conftest.py               modificato: DATABASE_URL su file temporaneo
    organize/conftest.py      modificato: perde l'env var, usa app.db
    test_migrate_organize_db.py  nuovo
  .env.example                modificato: le chiavi DJORG_* perdono il prefisso
```

---

### Task 1: Un solo `Base` e un solo engine

**Files:**
- Delete: `backend/app/organize/db.py`
- Modify: `backend/app/db.py`
- Modify: 18 punti di import in `backend/app/organize/**` e ~12 in `backend/tests/organize/**`
- Test: `backend/tests/organize/test_db_unificato.py`

**Interfaces:**
- Consumes: `app.db.Base`, `app.db.engine`, `app.db.SessionLocal`, `app.db.get_db`, `app.db.ensure_schema`
- Produces: `Base.metadata` contiene sia le tabelle Cratory sia quelle Organize; `app.organize.db` non esiste più

**Cosa fornisce `app/organize/db.py` prima di sparire** (inventario obbligatorio, non è cosa importa): `Base` (1 uso), `SessionLocal` (5 usi), `get_db` (12 usi), `engine` e `ensure_schema` (usati solo dai test). Nessun side effect a import-time oltre alla creazione dell'engine e al `mkdir` della cartella del DB — quest'ultimo lo fa già `_make_engine` di `app/db.py`.

- [ ] **Step 1: Scrivere il test che fallisce**

Crea `backend/tests/organize/test_db_unificato.py`:

```python
"""F2: un solo Base, un solo engine. Le tabelle Organize e Cratory convivono
nello stesso metadata e ensure_schema le crea tutte insieme."""

import pytest
from sqlalchemy import create_engine, inspect


def test_modulo_organize_db_non_esiste_piu():
    with pytest.raises(ModuleNotFoundError):
        import app.organize.db  # noqa: F401


def test_tabelle_organize_sullo_stesso_metadata():
    import app.models  # noqa: F401
    import app.organize.models  # noqa: F401
    from app.db import Base

    nomi = set(Base.metadata.tables)
    assert {"audio_file", "issue", "dup_group", "plan", "undo_journal", "scan_root"} <= nomi
    assert {"tracks", "playlists", "dj_sets"} <= nomi


def test_ensure_schema_crea_anche_le_tabelle_organize(tmp_path):
    from app.db import ensure_schema

    eng = create_engine(f"sqlite:///{tmp_path / 'unificato.db'}")
    ensure_schema(eng)
    tabelle = set(inspect(eng).get_table_names())
    assert {"tracks", "audio_file", "issue", "plan", "undo_journal"} <= tabelle
```

- [ ] **Step 2: Lanciare il test e verificare che fallisca**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/backend && .venv/bin/python -m pytest tests/organize/test_db_unificato.py -v
```

Atteso: `test_modulo_organize_db_non_esiste_piu` FALLISCE (il modulo esiste ancora) e `test_tabelle_organize_sullo_stesso_metadata` FALLISCE (`audio_file` non è nel metadata di Cratory).

- [ ] **Step 3: Registrare i modelli Organize in `ensure_schema`**

In `backend/app/db.py`, dentro `ensure_schema`, sostituire la riga `Base.metadata.create_all(eng)` con:

```python
    # F2: un solo Base. L'import registra le tabelle Organize su Base.metadata
    # prima di create_all; da qui in poi ereditano gratis tutto il macchinario
    # model-derived di questo modulo (_migrate_add_model_columns, creazione
    # indici), che itera Base.metadata senza sapere di chi sia la tabella.
    import app.models  # noqa: F401
    import app.organize.models  # noqa: F401

    Base.metadata.create_all(eng)
```

- [ ] **Step 4: Riscrivere i 18 punti di import nel codice applicativo**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/backend/app/organize && \
find . -name '*.py' -print0 | xargs -0 sed -i '' -E 's|from app\.organize\.db import|from app.db import|g' && \
grep -rn "app\.organize\.db" . | head
```

Atteso dal `grep`: **nessun output**.

Nota BSD: `sed` di macOS non conosce `\b`; qui non serve perché il pattern è una stringa intera. Dove servisse un confine di parola, usare `[[:<:]]` e `[[:>:]]`.

- [ ] **Step 5: Riscrivere gli import nei test**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/backend/tests/organize && \
find . -name '*.py' -print0 | xargs -0 sed -i '' -E 's|from app\.organize\.db import|from app.db import|g' && \
grep -rn "app\.organize\.db" . | grep -v test_db_unificato | head
```

Atteso: nessun output (a parte il test nuovo, che il modulo lo cerca apposta).

Il test `test_import_smoke.py` di F1 asserisce che i due `Base` siano **distinti**: quell'asserzione è ora falsa per costruzione. Sostituiscila — il file diventa:

```python
"""Il codice Organize è importabile dal namespace app.organize e condivide
Base/engine con Cratory (F2: un solo DB)."""


def test_moduli_organize_importabili():
    from app.organize import models, schemas  # noqa: F401
    from app.organize.core import http_errors  # noqa: F401


def test_base_condiviso():
    import app.models  # noqa: F401
    import app.organize.models  # noqa: F401
    from app.db import Base

    assert "audio_file" in Base.metadata.tables
    assert "tracks" in Base.metadata.tables
```

- [ ] **Step 6: Eliminare `app/organize/db.py`**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1 && git rm -q backend/app/organize/db.py
```

- [ ] **Step 7: Lanciare i test nuovi**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/backend && .venv/bin/python -m pytest tests/organize/test_db_unificato.py tests/organize/test_import_smoke.py -v
```

Atteso: 5 passed.

- [ ] **Step 8: Lanciare tutta la suite**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/backend && .venv/bin/python -m pytest tests -q
```

Atteso: i test Organize che dipendono dal DB **falliscono** — puntano ancora al vecchio engine via `DJORG_DATABASE_URL`, che ora non configura più nulla. È il buco che chiude il Task 3. Annota il conteggio dei fallimenti.

- [ ] **Step 9: Commit**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1 && \
git add -A backend/app backend/tests && \
git commit -m "feat(f2): un solo Base ed engine, ensure_schema registra i modelli Organize"
```

---

### Task 2: Configurazione unificata (via il prefisso `DJORG_`)

**Files:**
- Delete: `backend/app/organize/core/config.py`
- Modify: `backend/app/core/config.py`
- Modify: gli import di `app.organize.core.config` in `backend/app/organize/**`
- Modify: `backend/.env.example`
- Test: `backend/tests/organize/test_config_unificata.py`

**Interfaces:**
- Consumes: `app.core.config.settings`
- Produces: su `settings` compaiono `audio_exts`, `low_bitrate_kbps`, `duration_min_s`, `duration_max_s`, `fuzzy_dur_tol_s`, `acoustid_api_key`, `musicbrainz_user_agent`, `cover_cache_dir`, `thumb_cache_dir`

**Decisione: `discogs_token` diventa uno solo.** Entrambe le config avevano il campo; togliendo il prefisso collidono. Si tiene quello di Cratory (`discogs_token: str = ""`) e Organize lo usa: è un solo account Discogs, e due chiavi per lo stesso servizio sarebbero solo un modo per dimenticarne una. `DJORG_DISCOGS_TOKEN` sparisce da `.env.example`.

**Cosa fornisce `app/organize/core/config.py` prima di sparire**: la classe `Settings` con 11 campi, due `field_validator` (normalizzazione di `database_url` e delle due cache dir su path assoluti relativi a `backend/`), l'istanza `settings`, e `BACKEND_DIR`. `database_url` non trasloca — muore con il DB separato. I due validator sì: la logica va replicata sui campi che traslocano.

- [ ] **Step 1: Scrivere il test che fallisce**

Crea `backend/tests/organize/test_config_unificata.py`:

```python
"""F2: una sola classe Settings, senza prefisso DJORG_."""

import pytest


def test_modulo_config_organize_non_esiste_piu():
    with pytest.raises(ModuleNotFoundError):
        import app.organize.core.config  # noqa: F401


def test_campi_organize_su_settings_unica():
    from app.core.config import settings

    assert settings.audio_exts
    assert ".flac" in settings.audio_exts
    assert settings.low_bitrate_kbps > 0
    assert settings.duration_min_s > 0
    assert isinstance(settings.musicbrainz_user_agent, str)
    assert hasattr(settings, "acoustid_api_key")


def test_discogs_token_unico():
    from app.core.config import settings

    assert isinstance(settings.discogs_token, str)


def test_cache_dir_normalizzate_ad_assoluto(monkeypatch):
    """Un path relativo nel .env non deve dipendere dalla cwd del processo:
    stesso difetto che DJORG_DATABASE_URL aveva prima del validator."""
    from app.core.config import Settings

    s = Settings(cover_cache_dir="./data/cover_cache", thumb_cache_dir="./data/thumb_cache")
    assert s.cover_cache_dir.startswith("/")
    assert s.thumb_cache_dir.startswith("/")
```

- [ ] **Step 2: Lanciare il test e verificare che fallisca**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/backend && .venv/bin/python -m pytest tests/organize/test_config_unificata.py -v
```

Atteso: FAIL su `test_modulo_config_organize_non_esiste_piu` e su `test_campi_organize_su_settings_unica` (`settings` non ha `audio_exts`).

- [ ] **Step 3: Portare i campi su `app/core/config.py`**

Dentro `class Settings`, in fondo ai campi esistenti, aggiungere:

```python
    # --- Organize (ex Sortory) ---------------------------------------------
    # Estensioni audio riconosciute dallo scanner (minuscole, col punto).
    audio_exts: tuple[str, ...] = (".mp3", ".flac", ".wav", ".aiff", ".aif", ".m4a", ".aac")
    # Soglie Inspector / Dedup.
    low_bitrate_kbps: int = 256
    duration_min_s: float = 30.0
    duration_max_s: float = 900.0
    fuzzy_dur_tol_s: float = 2.0
    # Provider di metadati testuali e fingerprint. Chiavi opzionali: senza
    # chiave il provider è inattivo (degradazione pulita). `discogs_token` non
    # si duplica: è lo stesso account che usa il Discovery, qui sopra.
    acoustid_api_key: str = ""
    musicbrainz_user_agent: str = "Cratory-Organize/0.1 (+http://localhost)"
    # Cache thumbnail: cover proposte dai provider e cover embeddate nei file.
    # Separate di proposito — entrambe indicizzano per {file_id}.jpg e
    # condividerle confonderebbe l'artwork reale con la proposta di un provider.
    cover_cache_dir: str = "./data/cover_cache"
    thumb_cache_dir: str = "./data/thumb_cache"
```

E, accanto agli altri validator della classe:

```python
    @field_validator("cover_cache_dir", "thumb_cache_dir")
    @classmethod
    def _cache_dir_assoluta(cls, value: str) -> str:
        """Path relativo risolto rispetto a backend/, mai alla cwd del processo:
        stesso difetto che database_url aveva prima del suo validator."""
        if not value:
            return value
        path = Path(value)
        if not path.is_absolute():
            path = BACKEND_DIR / path
        return path.resolve().as_posix()
```

Verifica che `Path` e `field_validator` siano già importati nel file (lo sono: `from pathlib import Path`, `from pydantic import field_validator`).

- [ ] **Step 4: Riscrivere gli import**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/backend && \
find app/organize tests/organize -name '*.py' -print0 | xargs -0 sed -i '' -E 's|app\.organize\.core\.config|app.core.config|g' && \
grep -rn "organize\.core\.config" app tests | grep -v test_config_unificata | head
```

Atteso: nessun output.

- [ ] **Step 5: Eliminare il modulo e verificare che nulla usi più `DJORG_`**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1 && \
git rm -q backend/app/organize/core/config.py && \
grep -rn "DJORG_" backend/app backend/tests | head
```

Atteso dal `grep`: nessun output. Se compare `DJORG_DATABASE_URL` in `tests/organize/conftest.py`, lascialo: lo rimuove il Task 3.

- [ ] **Step 6: Aggiornare `.env.example`**

Nel blocco `--- Organize (ex Sortory) ---` aggiunto in F1: eliminare `DJORG_DATABASE_URL` e `DJORG_DISCOGS_TOKEN`, rinominare le altre due senza prefisso, e aggiornare la nota di testa.

```
# --- Organize (ex Sortory) --------------------------------------------------
# Sezione /organize: pulizia tag, duplicati, piano e apply sui file su disco.
# Dalla fusione F2 non c'è più un DB né un prefisso separati: queste chiavi
# vivono nella stessa Settings di Cratory. Il token Discogs è quello unico
# dichiarato più sopra (DISCOGS_TOKEN), non ce n'è uno dedicato.

# MusicBrainz non richiede chiave, ma esige uno User-Agent identificabile.
MUSICBRAINZ_USER_AGENT=Cratory-Organize/0.1 (+http://localhost)

# AcoustID: fingerprint acustico → AudioFile.mbid.
# Serve ANCHE il binario fpcalc (Chromaprint): `brew install chromaprint`.
ACOUSTID_API_KEY=
```

`ANTHROPIC_API_KEY` resta dov'è, con la sua nota: è letta da `os.environ`, non da pydantic-settings.

- [ ] **Step 7: Lanciare i test di config**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/backend && .venv/bin/python -m pytest tests/organize/test_config_unificata.py -v
```

Atteso: 4 passed.

- [ ] **Step 8: Commit**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1 && \
git add -A backend && \
git commit -m "feat(f2): una sola Settings, il prefisso DJORG_ sparisce (discogs_token unificato)"
```

---

### Task 3: Isolamento del DB nei test

**Files:**
- Modify: `backend/tests/conftest.py`
- Modify: `backend/tests/organize/conftest.py`
- Test: `backend/tests/test_db_isolation.py`

**Interfaces:**
- Consumes: `app.db.engine` (ora unico)
- Produces: l'engine di modulo punta a un file temporaneo per l'intera sessione di test, in entrambe le suite

**Il problema, in chiaro.** Le due suite isolavano il DB in modi diversi: Cratory con `app.dependency_overrides[get_db]` per test (l'engine di modulo non lo usava nessuno), Organize puntando l'engine di modulo a un file temporaneo via env var. Unificato l'engine, la seconda strategia si rompe — e non basta spostare l'env var in `tests/organize/conftest.py`, perché `tests/conftest.py` importa `app.db` **prima**, e a quel punto `app.core.config` ha già letto l'ambiente.

La correzione va quindi nel conftest di livello superiore, e chiude anche un buco latente lato Cratory: oggi un test che si dimenticasse l'override scriverebbe sul `data/djassistant.db` **reale**. Non è teorico: `DATABASE_URL=sqlite:///data/djassistant.db` è relativo e il validator lo risolve contro il `BACKEND_DIR` di chi esegue — nel checkout principale, quello vero.

**Due cose in più, emerse eseguendo il Task 1.**

**(a) Rimuovere lo stopgap del Task 1.** Il Task 1 ha dovuto tamponare l'isolamento sostituendo a runtime l'oggetto `engine` e riconfigurando `SessionLocal`, con una guardia di re-entrancy per il caso `from tests.organize.conftest import make_audio_file` (che rifà girare il conftest sotto un'altra identità di modulo, perché `tests/` non è un package e `tests/organize/` sì). Quel tampone esiste solo perché l'env var arrivava troppo tardi. Impostata `DATABASE_URL` nel conftest radice — cioè prima di ogni import di `app.*` — la sostituzione dell'engine e la guardia **vanno rimosse**: sono complessità che non serve più a nulla, e lasciarle significa due meccanismi di isolamento sovrapposti.

**(b) Seminare le `ScanRoot` canoniche.** L'engine di Cratory imposta `PRAGMA foreign_keys=ON` a ogni connessione (`app/db.py:26`); il vecchio engine di Organize no. Unificandoli, l'enforcement delle FK si accende su 519 test scritti sotto un engine più permissivo, e **71 falliscono** con `FOREIGN KEY constraint failed`: creano un `AudioFile` con `root_id` che punta a una `ScanRoot` mai inserita (`make_audio_file` ha `root_id=1` di default).

Non sistemare le 71 fixture una per una: in F3 `scan_root` sparisce insieme a `root_id`, e sarebbe lavoro da buttare. Semina invece le due radici canoniche dentro `_fresh_db`, subito dopo `create_all`:

```python
    # F2: l'engine unificato accende PRAGMA foreign_keys=ON (app/db.py), che il
    # vecchio engine di Organize non aveva. Le fixture creano AudioFile con
    # root_id 1/2 senza inserire la ScanRoot: qui le seminiamo una volta, così
    # il vincolo è soddisfatto senza toccare 71 test.
    # F3 rimuove scan_root: queste righe se ne vanno con lei.
    from app.organize.models import ScanRoot

    with SessionLocal() as seed:
        seed.add_all([
            ScanRoot(id=1, path="/inbox"),
            ScanRoot(id=2, path="/library"),
        ])
        seed.commit()
```

I test che creano una propria `ScanRoot` con id espliciti diversi continuano a funzionare; quelli che ne creano una con id 1 o 2 vanno adattati se sbattono su un conflitto di chiave — verifica caso per caso, sono pochi.

- [ ] **Step 1: Scrivere il test che fallisce**

Crea `backend/tests/test_db_isolation.py`:

```python
"""Nessun test deve poter scrivere sul DB reale: l'engine di modulo punta
sempre a un file temporaneo per la sessione di test."""

from app.db import engine


def test_engine_non_punta_al_db_reale():
    url = str(engine.url)
    assert "djassistant.db" not in url
    assert "djorganizer.db" not in url


def test_engine_punta_a_una_temp_dir():
    url = str(engine.url)
    assert "/tmp" in url or "/var/folders" in url  # mkdtemp su Linux / macOS
```

- [ ] **Step 2: Lanciare il test e verificare che fallisca**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/backend && .venv/bin/python -m pytest tests/test_db_isolation.py -v
```

Atteso: FAIL — l'engine punta a `backend/data/djassistant.db`.

- [ ] **Step 3: Puntare l'engine a un file temporaneo nel conftest radice**

In `backend/tests/conftest.py`, **prima** di qualunque `import app.*` (quindi prima della riga `from app.db import Base`), inserire:

```python
import os
import tempfile

# DEVE precedere ogni import di app.*: app.core.config legge l'ambiente al
# momento dell'import, e app.db costruisce l'engine da settings.database_url.
# Senza questo, un test che dimentichi dependency_overrides[get_db] scriverebbe
# sul DB reale. Vale per entrambe le suite: da F2 l'engine è uno solo.
_TMP_DB = os.path.join(tempfile.mkdtemp(prefix="cratory-test-"), "test.db")
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP_DB}"
```

Le righe `sys.path.insert` esistenti restano dove sono, purché anch'esse precedano gli import di `app.*`.

- [ ] **Step 4: Ripulire il conftest di Organize**

**Modifica chirurgica, NON riscrittura del file.** `backend/tests/organize/conftest.py` contiene molto più di quanto mostrato qui sotto e tutto il resto va lasciato **esattamente com'è**:

- `pytest_collection_modifyitems` con il filtro su `_ORGANIZE_TESTS` — l'hook riceve da pytest gli item dell'**intera** sessione, e senza quel filtro la strictness sui warning tracimerebbe sui test Cratory. È già stato un bug in F1: non reintrodurlo.
- le fixture `db`, `fixture_path`, `copy_fixture` e la factory `make_audio_file`.

Le uniche tre modifiche da fare:

1. rimuovere il blocco che imposta `DJORG_DATABASE_URL` (e `import os` / `import tempfile` se non servono ad altro nel file);
2. cambiare la riga di import dell'engine;
3. aggiungere `import app.models` dentro `_fresh_db`.

L'import dell'engine diventa:

```python
"""Fixture pytest di Organize.

Il DB temporaneo è impostato dal conftest radice (un solo engine da F2): qui
resta solo lo schema pulito per test. Le fixture autouse del conftest radice
(reset runtime_settings, no-LLM, no-scan, reset job state) restano attive e
sono innocue per questi test.
"""

import pytest

from app.db import Base, SessionLocal, engine
```

La fixture `_fresh_db` resta com'è ma deve importare **entrambi** i moduli di modelli, altrimenti `create_all` sul Base condiviso ricrea solo metà schema.

Nota di costo, da tenere d'occhio ma non da ottimizzare adesso: con un solo `Base` questa fixture passa da ~9 a ~20 tabelle droppate e ricreate, per ognuno dei 519 test Organize. Se la suite rallenta in modo evidente, segnalalo come concern — non cambiare strategia di tua iniziativa.

```python
@pytest.fixture(autouse=True)
def _fresh_db():
    """Schema pulito prima di ogni test (import dei modelli per registrarli)."""
    import app.models  # noqa: F401
    import app.organize.models  # noqa: F401

    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield
```

- [ ] **Step 5: Lanciare il test di isolamento**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/backend && .venv/bin/python -m pytest tests/test_db_isolation.py -v
```

Atteso: 2 passed.

- [ ] **Step 6: Lanciare tutta la suite**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/backend && .venv/bin/python -m pytest tests -q
```

Atteso: **tutto verde**, e in particolare azzerati i 71 `FOREIGN KEY constraint failed` annotati allo Step 8 del Task 1. Output pulito: il Task 1 lasciava anche 1 warning, e la suite non deve averne.

Se qualche test Cratory fallisce ora e prima passava, è un test che dipendeva senza dirlo dal DB reale: **non aggirarlo puntandolo di nuovo al DB vero**. Rendilo esplicito seminando i dati che gli servono.

- [ ] **Step 7: Verificare che il DB reale sia intatto**

```bash
sqlite3 /Users/lucadenegri/Develop/DJProject01/backend/data/djassistant.db "select count(*) from tracks;"
```

Atteso: `677`. Se è cambiato, un test ha scritto sul DB reale prima di questa correzione — fermati e capisci quale.

- [ ] **Step 8: Commit**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1 && \
git add -A backend/tests && \
git commit -m "test(f2): engine di test su file temporaneo per entrambe le suite"
```

---

### Task 4: Script di migrazione con dry-run

**Files:**
- Create: `backend/app/tools/migrate_organize_db.py`
- Test: `backend/tests/test_migrate_organize_db.py`

**Interfaces:**
- Consumes: `app.db.ensure_schema`
- Produces:
  - `migra(src_organize: Path, dest: Path, *, dry_run: bool) -> Report`
  - `class Report` con i campi `audio_file: int`, `scan_root: int`, `plan: int`, `plan_op: int`, `undo_journal: int`, `fk_orfane: int`, `sorgente: dict[str, int]`
  - `Report.ok() -> bool` — tutti gli invarianti rispettati
  - `Report.render() -> str` — il report leggibile stampato a video
  - CLI: `python -m app.tools.migrate_organize_db --src … --dest … [--apply]` (senza `--apply` è dry-run)

**Cosa migra e cosa no.** Migra `scan_root`, `audio_file`, `plan`, `plan_op`, `undo_journal`. **Non** migra `issue` e `dup_group` (derivati: le issue sono tutte chiuse, i gruppi sono zero — li rigenera il primo scan). **Non** tocca `track_id`, `location`, `primary_file_id`: sono colonne di F3, e con loro il backfill dei 625 agganci.

- [ ] **Step 1: Scrivere il test che fallisce**

Crea `backend/tests/test_migrate_organize_db.py`:

```python
"""Migrazione del DB Organize dentro quello Cratory: invarianti, non costanti."""

import sqlite3

import pytest

from app.tools.migrate_organize_db import migra


@pytest.fixture()
def src_organize(tmp_path):
    """DB Organize sintetico: 3 file su 2 radici, 1 piano con 2 op, 2 undo."""
    path = tmp_path / "djorganizer.db"
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE scan_root (id INTEGER PRIMARY KEY, path VARCHAR, label VARCHAR,
                                last_scanned_at DATETIME, target_root VARCHAR);
        CREATE TABLE audio_file (id INTEGER PRIMARY KEY, root_id INTEGER, path VARCHAR,
                                 ext VARCHAR, size_bytes INTEGER, hash_method VARCHAR,
                                 status VARCHAR, first_seen_at DATETIME, last_scanned_at DATETIME);
        CREATE TABLE plan (id INTEGER PRIMARY KEY, created_at DATETIME, status VARCHAR, rules_json JSON);
        CREATE TABLE plan_op (id INTEGER PRIMARY KEY, plan_id INTEGER, seq INTEGER, kind VARCHAR,
                              file_id INTEGER, before_json JSON, after_json JSON, status VARCHAR);
        CREATE TABLE undo_journal (id INTEGER PRIMARY KEY, run_id INTEGER, op_seq INTEGER,
                                   kind VARCHAR, file_id INTEGER, from_path VARCHAR, to_path VARCHAR,
                                   applied_at DATETIME, reversed BOOLEAN);
        CREATE TABLE issue (id INTEGER PRIMARY KEY, file_id INTEGER, type VARCHAR, severity VARCHAR,
                            detail TEXT, status VARCHAR, created_at DATETIME, updated_at DATETIME);
        INSERT INTO scan_root (id, path) VALUES (1, '/inbox'), (2, '/library');
        INSERT INTO audio_file (id, root_id, path, ext, size_bytes, hash_method, status)
            VALUES (10, 1, '/inbox/a.mp3', '.mp3', 1, 'stream', 'present'),
                   (11, 2, '/library/b.flac', '.flac', 2, 'stream', 'present'),
                   (12, 2, '/library/c.flac', '.flac', 3, 'stream', 'present');
        INSERT INTO plan (id, status, rules_json) VALUES (5, 'applied', '{}');
        INSERT INTO plan_op (id, plan_id, seq, kind, file_id, before_json, after_json, status)
            VALUES (50, 5, 0, 'move', 10, '{}', '{}', 'done'),
                   (51, 5, 1, 'move', 11, '{}', '{}', 'done');
        INSERT INTO undo_journal (id, run_id, op_seq, kind, file_id, reversed)
            VALUES (100, 5, 0, 'move', 10, 0), (101, 5, 1, 'move', 11, 0);
        INSERT INTO issue (id, file_id, type, severity, detail, status)
            VALUES (200, 10, 'missing_tag', 'warn', 'x', 'closed');
    """)
    conn.commit()
    conn.close()
    return path


@pytest.fixture()
def dest_cratory(tmp_path):
    """DB Cratory di destinazione, con lo schema unificato già creato."""
    from sqlalchemy import create_engine

    from app.db import ensure_schema

    path = tmp_path / "djassistant.db"
    ensure_schema(create_engine(f"sqlite:///{path}"))
    return path


def test_dry_run_non_scrive(src_organize, dest_cratory):
    report = migra(src_organize, dest_cratory, dry_run=True)
    assert report.ok()
    assert report.audio_file == 3

    # Il contenuto, non l'mtime del file: SQLite può toccare il file anche su
    # rollback (journal/WAL), quindi un assert sull'mtime sarebbe fragile.
    conn = sqlite3.connect(dest_cratory)
    assert conn.execute("select count(*) from audio_file").fetchone()[0] == 0
    assert conn.execute("select count(*) from plan").fetchone()[0] == 0
    conn.close()


def test_migrazione_reale_travasa_tutto(src_organize, dest_cratory):
    report = migra(src_organize, dest_cratory, dry_run=False)
    assert report.ok()

    conn = sqlite3.connect(dest_cratory)
    conta = lambda t: conn.execute(f"select count(*) from {t}").fetchone()[0]  # noqa: E731
    assert conta("audio_file") == 3
    assert conta("scan_root") == 2
    assert conta("plan") == 1
    assert conta("plan_op") == 2
    assert conta("undo_journal") == 2
    conn.close()


def test_issue_e_dupgroup_non_migrate(src_organize, dest_cratory):
    migra(src_organize, dest_cratory, dry_run=False)
    conn = sqlite3.connect(dest_cratory)
    assert conn.execute("select count(*) from issue").fetchone()[0] == 0
    conn.close()


def test_id_rimappati_e_fk_coerenti(src_organize, dest_cratory):
    """plan_op e undo_journal devono puntare agli audio_file nuovi, non ai vecchi id."""
    migra(src_organize, dest_cratory, dry_run=False)
    conn = sqlite3.connect(dest_cratory)
    orfane = conn.execute("""
        select count(*) from plan_op o
        where not exists (select 1 from audio_file f where f.id = o.file_id)
    """).fetchone()[0]
    assert orfane == 0
    orfane_undo = conn.execute("""
        select count(*) from undo_journal u
        where not exists (select 1 from audio_file f where f.id = u.file_id)
    """).fetchone()[0]
    assert orfane_undo == 0
    conn.close()


def test_migrazione_su_destinazione_non_vuota_fallisce(src_organize, dest_cratory):
    """Rilanciare la migrazione su un DB già migrato deve fermarsi, non duplicare."""
    migra(src_organize, dest_cratory, dry_run=False)
    with pytest.raises(RuntimeError, match="già popolata"):
        migra(src_organize, dest_cratory, dry_run=False)
```

- [ ] **Step 2: Lanciare il test e verificare che fallisca**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/backend && .venv/bin/python -m pytest tests/test_migrate_organize_db.py -v
```

Atteso: FAIL con `ModuleNotFoundError: No module named 'app.tools.migrate_organize_db'`.

- [ ] **Step 3: Scrivere lo script**

Crea `backend/app/tools/migrate_organize_db.py`:

```python
"""Migrazione del DB Organize (djorganizer.db) dentro quello Cratory (djassistant.db).

Migra scan_root, audio_file, plan, plan_op, undo_journal rimappando gli id.
NON migra issue e dup_group: sono derivati e li rigenera il primo scan.
NON tocca track_id/location/primary_file_id: sono colonne di F3.

La verifica è su invarianti calcolati dalla sorgente, mai su costanti: i numeri
del DB reale cambiano a ogni uso dell'app.

Uso:
    python -m app.tools.migrate_organize_db --src ../DjOrganizer01/backend/data/djorganizer.db \\
        --dest data/djassistant.db            # dry-run: stampa il report, non scrive
    python -m app.tools.migrate_organize_db --src … --dest … --apply
"""

from __future__ import annotations

import argparse
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

# Ordine di travaso: le tabelle che fanno da bersaglio alle FK vengono prima.
_TABELLE = ("scan_root", "audio_file", "plan", "plan_op", "undo_journal")


@dataclass
class Report:
    sorgente: dict[str, int] = field(default_factory=dict)
    scan_root: int = 0
    audio_file: int = 0
    plan: int = 0
    plan_op: int = 0
    undo_journal: int = 0
    fk_orfane: int = 0
    dry_run: bool = True

    def ok(self) -> bool:
        return (
            self.fk_orfane == 0
            and all(getattr(self, t) == self.sorgente.get(t, 0) for t in _TABELLE)
        )

    def render(self) -> str:
        righe = [f"{'DRY-RUN' if self.dry_run else 'MIGRAZIONE'} — righe travasate"]
        for t in _TABELLE:
            atteso = self.sorgente.get(t, 0)
            ottenuto = getattr(self, t)
            segno = "ok" if atteso == ottenuto else "MISMATCH"
            righe.append(f"  {t:<14} {ottenuto:>6} / {atteso:<6} {segno}")
        righe.append(f"  {'FK orfane':<14} {self.fk_orfane:>6}")
        righe.append(f"  esito: {'OK' if self.ok() else 'FALLITO'}")
        return "\n".join(righe)


def _colonne(conn: sqlite3.Connection, tabella: str, schema: str = "main") -> list[str]:
    cur = conn.execute(f"PRAGMA {schema}.table_info({tabella})")
    return [r[1] for r in cur.fetchall()]


def migra(src_organize: Path, dest: Path, *, dry_run: bool) -> Report:
    """Travasa src_organize dentro dest. Con dry_run=True non scrive nulla:
    esegue tutto dentro una transazione e fa ROLLBACK."""
    src_organize = Path(src_organize)
    dest = Path(dest)
    if not src_organize.exists():
        raise FileNotFoundError(f"DB Organize non trovato: {src_organize}")
    if not dest.exists():
        raise FileNotFoundError(f"DB di destinazione non trovato: {dest}")

    conn = sqlite3.connect(dest)
    # isolation_level=None → autocommit: BEGIN/COMMIT/ROLLBACK espliciti
    # funzionano. Col default, sqlite3 apre transazioni implicite sulle DML e il
    # nostro BEGIN esploderebbe con "cannot start a transaction within a
    # transaction". ATTACH, per lo stesso motivo, va fatto fuori transazione.
    conn.isolation_level = None
    conn.execute("PRAGMA foreign_keys = OFF")  # travasiamo in ordine, controlliamo dopo
    conn.execute("ATTACH DATABASE ? AS org", (str(src_organize),))
    report = Report(dry_run=dry_run)

    try:
        # Precondizione, PRIMA di aprire la transazione: la destinazione dev'essere
        # vergine. È ciò che permette di conservare gli id originali senza tabella
        # di corrispondenza — vedi la nota sulla rimappatura nel piano.
        for tabella in _TABELLE:
            report.sorgente[tabella] = conn.execute(
                f"select count(*) from org.{tabella}"
            ).fetchone()[0]
            gia_presenti = conn.execute(f"select count(*) from main.{tabella}").fetchone()[0]
            if gia_presenti:
                raise RuntimeError(
                    f"main.{tabella} è già popolata ({gia_presenti} righe): "
                    "la destinazione non è vergine, migrazione annullata."
                )

        conn.execute("BEGIN")
        # Le colonne comuni alle due copie della tabella (la destinazione può
        # averne di più: ensure_schema crea lo schema corrente).
        for tabella in _TABELLE:
            comuni = [c for c in _colonne(conn, tabella, "org") if c in _colonne(conn, tabella)]
            lista = ", ".join(comuni)
            conn.execute(
                f"INSERT INTO main.{tabella} ({lista}) SELECT {lista} FROM org.{tabella}"
            )
            setattr(report, tabella, conn.execute(
                f"select count(*) from main.{tabella}"
            ).fetchone()[0])

        report.fk_orfane = _conta_fk_orfane(conn)

        if dry_run or not report.ok():
            conn.execute("ROLLBACK")
        else:
            conn.execute("COMMIT")
    except Exception:
        # La precondizione "destinazione vergine" scatta PRIMA del BEGIN: lì non
        # c'è transazione da annullare e ROLLBACK solleverebbe a sua volta,
        # mascherando l'errore vero.
        try:
            conn.execute("ROLLBACK")
        except sqlite3.OperationalError:
            pass
        raise
    finally:
        conn.execute("DETACH DATABASE org")
        conn.close()

    return report


def _conta_fk_orfane(conn: sqlite3.Connection) -> int:
    """Righe figlie che puntano a un padre inesistente dopo il travaso."""
    controlli = (
        "select count(*) from audio_file f "
        "where not exists (select 1 from scan_root r where r.id = f.root_id)",
        "select count(*) from plan_op o "
        "where not exists (select 1 from plan p where p.id = o.plan_id)",
        "select count(*) from plan_op o "
        "where not exists (select 1 from audio_file f where f.id = o.file_id)",
        "select count(*) from undo_journal u "
        "where not exists (select 1 from audio_file f where f.id = u.file_id)",
        "select count(*) from undo_journal u "
        "where not exists (select 1 from plan p where p.id = u.run_id)",
    )
    return sum(conn.execute(q).fetchone()[0] for q in controlli)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--src", required=True, type=Path, help="djorganizer.db sorgente")
    parser.add_argument("--dest", required=True, type=Path, help="djassistant.db di destinazione (una COPIA)")
    parser.add_argument("--apply", action="store_true", help="scrive davvero (default: dry-run)")
    args = parser.parse_args()

    report = migra(args.src, args.dest, dry_run=not args.apply)
    print(report.render())
    return 0 if report.ok() else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

**Nota sulla rimappatura degli id.** Il travaso conserva gli id originali perché le tabelle di destinazione sono vuote (lo script si ferma se non lo sono): non serve una tabella di corrispondenza, e le FK `plan_op.file_id` / `undo_journal.file_id` restano valide per costruzione. È la ragione per cui il controllo "destinazione vergine" non è una comodità ma una precondizione — ed è coperta dall'ultimo test.

- [ ] **Step 4: Lanciare i test**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/backend && .venv/bin/python -m pytest tests/test_migrate_organize_db.py -v
```

Atteso: 5 passed.

- [ ] **Step 5: Lanciare la suite intera**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/backend && .venv/bin/python -m pytest tests -q
```

Atteso: tutto verde.

- [ ] **Step 6: Commit**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1 && \
git add backend/app/tools/migrate_organize_db.py backend/tests/test_migrate_organize_db.py && \
git commit -m "feat(f2): script di migrazione del DB Organize con dry-run e assert su invarianti"
```

---

### Task 5: Dry-run e migrazione sui dati reali

**Files:** nessuno — è un'esecuzione, con backup su disco

**Interfaces:**
- Consumes: `app.tools.migrate_organize_db.migra`
- Produces: `backend/data/djassistant.db` migrato, con i due originali salvati

- [ ] **Step 1: Backup, prima di ogni altra cosa**

```bash
mkdir -p ~/Backup/fusione-f2 && \
cp /Users/lucadenegri/Develop/DJProject01/backend/data/djassistant.db ~/Backup/fusione-f2/djassistant-pre-f2.db && \
cp /Users/lucadenegri/Develop/DjOrganizer01/backend/data/djorganizer.db ~/Backup/fusione-f2/djorganizer-pre-f2.db && \
ls -la ~/Backup/fusione-f2/
```

Atteso: due file, dimensioni non nulle. **Se questo passo fallisce, fermati.**

- [ ] **Step 2: Rimisurare la baseline sulla sorgente reale**

```bash
sqlite3 /Users/lucadenegri/Develop/DjOrganizer01/backend/data/djorganizer.db \
  "select 'scan_root', count(*) from scan_root union all \
    select 'audio_file', count(*) from audio_file union all \
    select 'plan', count(*) from plan union all \
    select 'plan_op', count(*) from plan_op union all \
    select 'undo_journal', count(*) from undo_journal union all \
    select 'issue', count(*) from issue union all \
    select 'dup_group', count(*) from dup_group;"
```

Confronta con la baseline in testa a questo piano (1.778 / 2 / 99 / 2.996 / 1.025 / 0). **Piccole differenze sono normali** — sono già cambiati una volta in giornata. Una differenza di ordine di grandezza no: in quel caso fermati, non stai guardando il DB che credi.

- [ ] **Step 3: Preparare la copia di lavoro**

```bash
cd /Users/lucadenegri/Develop/DJProject01/backend && \
cp data/djassistant.db data/djassistant-migrato.db && \
ls -la data/djassistant*.db
```

Si lavora su `djassistant-migrato.db`. L'originale non viene mai aperto in scrittura.

- [ ] **Step 4: Creare le tabelle Organize sulla copia**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/backend && \
.venv/bin/python -c "
from sqlalchemy import create_engine
from app.db import ensure_schema
ensure_schema(create_engine('sqlite:////Users/lucadenegri/Develop/DJProject01/backend/data/djassistant-migrato.db'))
print('schema aggiornato')
"
```

Atteso: `schema aggiornato`.

- [ ] **Step 5: Dry-run**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/backend && \
.venv/bin/python -m app.tools.migrate_organize_db \
  --src /Users/lucadenegri/Develop/DjOrganizer01/backend/data/djorganizer.db \
  --dest /Users/lucadenegri/Develop/DJProject01/backend/data/djassistant-migrato.db
```

Atteso: il report con tutte le righe `ok`, `FK orfane 0`, `esito: OK`, ed exit code 0.

**Leggi i numeri**, non solo l'esito: devono essere nell'ordine di grandezza dello Step 2. Se `esito: FALLITO`, non forzare — capisci quale riga è in `MISMATCH`.

- [ ] **Step 6: Migrazione reale**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/backend && \
.venv/bin/python -m app.tools.migrate_organize_db \
  --src /Users/lucadenegri/Develop/DjOrganizer01/backend/data/djorganizer.db \
  --dest /Users/lucadenegri/Develop/DJProject01/backend/data/djassistant-migrato.db \
  --apply
```

Atteso: stesso report, intestazione `MIGRAZIONE`, `esito: OK`.

- [ ] **Step 7: Verificare il DB migrato**

```bash
sqlite3 /Users/lucadenegri/Develop/DJProject01/backend/data/djassistant-migrato.db \
  "select 'tracks', count(*) from tracks union all \
    select 'audio_file', count(*) from audio_file union all \
    select 'plan', count(*) from plan union all \
    select 'undo_journal', count(*) from undo_journal union all \
    select 'issue', count(*) from issue union all \
    select 'playlists', count(*) from playlists union all \
    select 'dj_sets', count(*) from dj_sets;"
```

Atteso: i dati Cratory intatti (`tracks` 677, `playlists` 12, `dj_sets` 9) **e** quelli Organize presenti, con `issue` a 0 (non migrate, per scelta).

- [ ] **Step 8: Provare il join che servirà a F3**

Non modifica nulla: serve a sapere adesso quanti agganci troverà F3.

```bash
sqlite3 /Users/lucadenegri/Develop/DJProject01/backend/data/djassistant-migrato.db \
  "select count(*) from tracks t join audio_file f on f.path = t.local_path where t.has_local_file = 1;"
```

Atteso: intorno a 625. **Annota il numero**: è la baseline dell'assert di F3.

- [ ] **Step 9: Promuovere la copia a DB ufficiale**

```bash
cd /Users/lucadenegri/Develop/DJProject01/backend/data && \
mv djassistant.db djassistant-pre-f2.db && \
mv djassistant-migrato.db djassistant.db && \
ls -la djassistant*.db
```

Il rollback resta a portata di mano: `djassistant-pre-f2.db` accanto, più i backup in `~/Backup/fusione-f2/`.

- [ ] **Step 10: Avvio reale e verifica delle due sezioni**

Avvia backend e frontend, poi:

```bash
curl -s localhost:8000/api/health && \
curl -s "localhost:8000/api/organize/library/stats" && \
curl -s "localhost:8000/api/tracks?limit=1"
```

Atteso: le tre risposte OK, con Organize che riporta i file migrati e Cratory le sue tracce — dallo stesso file SQLite.

Infine, nel browser: `http://localhost:3000/organize/history` deve mostrare i piani applicati (i ~99 `plan`), e `http://localhost:3000/library` le tracce di sempre.

---

### Task 6: Verifica di fase e chiusura di F2

**Files:**
- Modify: `docs/superpowers/specs/2026-08-11-fusione-sortory-cratory-design.md` (spunta F2)

- [ ] **Step 1: Suite completa**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/backend && .venv/bin/python -m pytest tests -q
```

Atteso: tutto verde. Riporta il conteggio.

- [ ] **Step 2: Frontend**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/frontend && npm run lint && npm run build && npm run test:unit && npm run test:e2e
```

Atteso: tutti verdi (l'e2e con il fallimento pre-esistente già noto, se ancora presente).

- [ ] **Step 3: Verificare che un bottone AGISCA, non che la pagina carichi**

La lezione di F1: su un DB vuoto le pagine caricano benissimo e i bottoni sono morti. Ora il DB ha dati veri.

Nel browser, su `/organize`: lancia uno **scan** e verifica che la barra dei job avanzi e che al termine i conteggi cambino. Poi su `/organize/history` apri un piano applicato e verifica che l'undo sia offerto (senza eseguirlo).

```bash
sqlite3 /Users/lucadenegri/Develop/DJProject01/backend/data/djassistant.db "select count(*) from issue;"
```

Atteso: **maggiore di 0** dopo lo scan — è la prova che le issue si rigenerano, cioè che non migrarle era la scelta giusta.

- [ ] **Step 4: Spuntare F2 nella spec**

Nella tabella delle fasi, riga **F2**, aggiungere in coda alla milestone: `— completata <data>, N test verdi`.

- [ ] **Step 5: Commit**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1 && \
git status --porcelain && git add -A docs && \
git commit -m "docs(f2): F2 completata — un solo DB, dati Organize migrati"
```

- [ ] **Step 6: Riepilogo per F3**

Riporta all'utente: numero di test verdi, il conteggio del join dello Step 8 di Task 5 (la baseline degli agganci di F3), e se lo scan dello Step 3 ha rigenerato le issue.

---

## Definizione di "F2 completa"

- `app/organize/db.py` e `app/organize/core/config.py` non esistono più; nessun `DJORG_` nel codice.
- Un solo file SQLite: `backend/data/djassistant.db`, con dentro tracce, playlist, set **e** file, piani, undo journal.
- `pytest tests` verde; nessun test può scrivere sul DB reale.
- Dry-run e migrazione reale eseguiti, con backup conservati in `~/Backup/fusione-f2/`.
- Uno scan da `/organize` rigenera le issue sul DB unico.
- `track_id`, `location`, `primary_file_id` **non** esistono ancora — è corretto: sono F3.
