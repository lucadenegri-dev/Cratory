# ① Bundle-ready — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Il backend gira interamente da una cartella di codice in sola lettura, scrivendo tutto in una cartella dati separata indicata da `CRATORY_DATA_DIR`.

**Architecture:** Oggi `BACKEND_DIR` significa due cose insieme — dove sta il codice e dove si scrive — e in un `.app` firmato devono divergere. Si aggiunge un modulo `app/core/paths.py` senza dipendenze che espone `BACKEND_DIR` e `DATA_DIR`, e i cinque punti di scrittura (database, log, cache cover/thumb, `bin/`, `.env`) si riancorano al secondo. Senza la variabile d'ambiente i due coincidono e non cambia niente.

**Tech Stack:** Python 3.11, `os` e `pathlib` (stdlib), pydantic-settings, pytest.

Spec: `docs/superpowers/specs/2026-08-22-bundle-ready-design.md`.
Contesto d'insieme: `docs/superpowers/specs/2026-08-22-tauri-decomposizione-design.md`.

## Global Constraints

- **Nessuna dipendenza nuova.** Solo `os` e `pathlib`. Non aggiungere righe a `backend/requirements.txt`.
- **Variabile assente = comportamento identico a oggi**, byte per byte. È l'invariante che ogni task deve preservare.
- **Il backend non indovina mai di essere in un bundle.** Non sniffare il proprio percorso, non cercare `Contents/Resources`: si onora una variabile e basta.
- **Il calcolo dei percorsi non tocca il filesystem.** Nessun `mkdir` e nessun test di esistenza fuori da `verifica_scrivibile`, che è l'unico punto autorizzato: `managed_bin_dir()` gira su praticamente ogni `resolve_binary`, e un accesso al filesystem lì trasformerebbe un `GET /api/services` in un 500 su un mount di sola lettura.
- **Lingua del codice:** docstring, commenti e nomi dei test in italiano, come il resto di `app/core/`.
- **Comando dei test** (il worktree non ha un proprio `.venv` — si usa quello del checkout principale con la cwd nel `backend/` del worktree):

```bash
cd backend && /Users/lucadenegri/Develop/DJProject01/backend/.venv/bin/python -m pytest tests -q
```

- **`core/version.py` non si tocca.** Continua a leggere `VERSION` da `BACKEND_DIR.parent`: è sola lettura, e il caso bundle ha già la sua risposta in `CRATORY_VERSION`.

---

### Task 1: Il modulo dei percorsi

**Files:**
- Create: `backend/app/core/paths.py`
- Test: `backend/tests/test_data_dir.py`

**Interfaces:**
- Consumes: niente (modulo foglia, per costruzione).
- Produces:
  - `BACKEND_DIR: Path` — la cartella del codice (`backend/`).
  - `DATA_DIR_ENV: str` — la costante `"CRATORY_DATA_DIR"`.
  - `risolvi_data_dir(raw: str | None) -> Path` — pura; solleva `RuntimeError` su percorso relativo.
  - `DATA_DIR: Path` — costante di modulo, `risolvi_data_dir(os.environ.get(DATA_DIR_ENV))`.
  - `verifica_scrivibile(cartella: Path) -> None` — solleva `RuntimeError` con messaggio leggibile.

- [ ] **Step 1: Scrivere i test che falliscono**

Creare `backend/tests/test_data_dir.py`:

```python
"""La cartella dei dati è distinta da quella del codice.

Senza la variabile coincidono e nessuno se ne accorge; con la variabile
divergono, che è la condizione per girare da un .app di sola lettura."""
import stat
from pathlib import Path

import pytest

from app.core import paths


def test_senza_variabile_e_la_cartella_del_codice():
    """La guardia di non-regressione: chi non usa il seam non lo vede."""
    assert paths.risolvi_data_dir(None) == paths.BACKEND_DIR
    assert paths.risolvi_data_dir("") == paths.BACKEND_DIR
    assert paths.risolvi_data_dir("   ") == paths.BACKEND_DIR


def test_percorso_assoluto_usato_com_e(tmp_path):
    assert paths.risolvi_data_dir(str(tmp_path)) == tmp_path


def test_tilde_espansa():
    """Come già fa expand_user_paths in config.py per library_root."""
    atteso = Path.home() / "Library" / "Application Support" / "Cratory"
    assert paths.risolvi_data_dir("~/Library/Application Support/Cratory") == atteso


def test_percorso_relativo_solleva():
    """Risolverlo contro la cwd metterebbe i dati dove capita: meglio non
    partire che partire scrivendo altrove."""
    with pytest.raises(RuntimeError) as errore:
        paths.risolvi_data_dir("./dati")
    assert paths.DATA_DIR_ENV in str(errore.value)
    assert "assoluto" in str(errore.value)


def test_data_dir_di_default_e_backend_dir(monkeypatch):
    """La costante di modulo, non solo la funzione."""
    monkeypatch.delenv(paths.DATA_DIR_ENV, raising=False)
    assert paths.risolvi_data_dir(None) == paths.BACKEND_DIR


def test_verifica_scrivibile_crea_la_cartella_mancante(tmp_path):
    nuova = tmp_path / "non" / "esiste" / "ancora"
    paths.verifica_scrivibile(nuova)
    assert nuova.is_dir()


def test_verifica_scrivibile_non_lascia_la_sonda(tmp_path):
    """Un file di prova dimenticato finirebbe nella cartella dati dell'utente."""
    paths.verifica_scrivibile(tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_verifica_scrivibile_solleva_leggibile(tmp_path):
    """In un'app impacchettata questo messaggio è tutto ciò che l'utente vedrà:
    deve nominare la cartella e la variabile da cui cambiarla."""
    bloccata = tmp_path / "sola-lettura"
    bloccata.mkdir()
    bloccata.chmod(stat.S_IRUSR | stat.S_IXUSR)
    try:
        with pytest.raises(RuntimeError) as errore:
            paths.verifica_scrivibile(bloccata)
        assert str(bloccata) in str(errore.value)
        assert paths.DATA_DIR_ENV in str(errore.value)
    finally:
        bloccata.chmod(stat.S_IRWXU)
```

- [ ] **Step 2: Eseguirli per vederli fallire**

```bash
cd backend && /Users/lucadenegri/Develop/DJProject01/backend/.venv/bin/python -m pytest tests/test_data_dir.py -q
```

Atteso: FAIL in raccolta, `ModuleNotFoundError: No module named 'app.core.paths'`.

- [ ] **Step 3: Scrivere il modulo**

Creare `backend/app/core/paths.py`:

```python
"""Dove sta il codice, e dove l'app scrive. Sono due cose diverse.

`BACKEND_DIR` è la cartella del codice; `DATA_DIR` quella dei dati — database,
log, cache, binari scaricati, `.env`. Oggi coincidono, e senza
`CRATORY_DATA_DIR` continuano a coincidere: chi non sa di questo seam non deve
accorgersi che esiste. In un bundle `.app` firmato devono divergere, perché la
cartella del codice è di sola lettura e scriverci invaliderebbe la firma.

Stessa forma di `CRATORY_BIN_DIR` e `CRATORY_VERSION`, e stessa disciplina: il
backend non indovina mai di essere dentro un bundle, si limita a onorare una
variabile che il packager imposta al lancio.

Modulo senza dipendenze di proposito. `main.py` chiama `load_dotenv()` prima di
importare `app.core.config`, perché `FPCALC` viene letto da `os.environ` e non
da pydantic-settings: importare `config` a quel punto costruirebbe `Settings()`
troppo presto. Qui non c'è niente da importare, quindi nessun vincolo d'ordine.
"""
from __future__ import annotations

import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent

DATA_DIR_ENV = "CRATORY_DATA_DIR"


def risolvi_data_dir(raw: str | None) -> Path:
    """Il valore grezzo della variabile diventa la cartella dei dati.

    Assente o vuota = `BACKEND_DIR`, cioè il comportamento di sempre. La `~`
    viene espansa, come già fa `expand_user_paths` in `config.py`.

    Un percorso relativo solleva invece di essere risolto contro la cwd: i dati
    finirebbero in un posto che dipende da come è stato lanciato il processo —
    esattamente il difetto che i validator di `config.py` dichiarano di aver
    corretto. È una configurazione sbagliata che non deve poter passare
    inosservata, e a questo punto l'app non ha ancora fatto niente.
    """
    testo = (raw or "").strip()
    if not testo:
        return BACKEND_DIR
    cartella = Path(testo).expanduser()
    if not cartella.is_absolute():
        raise RuntimeError(
            f"{DATA_DIR_ENV}={testo!r} è un percorso relativo. Serve un "
            "percorso assoluto: altrimenti i dati finiscono in una cartella "
            "che dipende dalla directory di lavoro del processo."
        )
    return cartella


DATA_DIR = risolvi_data_dir(os.environ.get(DATA_DIR_ENV))


def verifica_scrivibile(cartella: Path) -> None:
    """Solleva con un messaggio leggibile se non ci si può scrivere.

    Va chiamata all'avvio, prima di qualunque scrittura. In un'app
    impacchettata l'utente non ha un terminale da cui leggere uno stack trace:
    un `PermissionError` grezzo sepolto in un log che non sa di avere è
    indistinguibile da un'app che non parte e basta.

    È l'unico punto di questo modulo autorizzato a toccare il filesystem.
    """
    try:
        cartella.mkdir(parents=True, exist_ok=True)
        sonda = cartella / ".cratory-prova-scrittura"
        sonda.write_text("")
        sonda.unlink()
    except OSError as exc:
        raise RuntimeError(
            f"La cartella dei dati non è scrivibile: {cartella} ({exc}). "
            f"Impostare {DATA_DIR_ENV} su una cartella scrivibile."
        ) from exc
```

- [ ] **Step 4: Eseguire i test**

```bash
cd backend && /Users/lucadenegri/Develop/DJProject01/backend/.venv/bin/python -m pytest tests/test_data_dir.py -q
```

Atteso: 8 passed.

- [ ] **Step 5: Provare le asserzioni rompendo il codice**

Un test che resta verde quando il codice è sbagliato non serve a niente. Verificare a mano, uno alla volta, poi rimettere a posto:

1. In `risolvi_data_dir`, sostituire `return BACKEND_DIR` con `return Path("/tmp")` → deve fallire `test_senza_variabile_e_la_cartella_del_codice`.
2. Togliere il `raise` sul percorso relativo e sostituirlo con `return BACKEND_DIR / cartella` → deve fallire `test_percorso_relativo_solleva`.
3. In `verifica_scrivibile`, togliere `sonda.unlink()` → deve fallire `test_verifica_scrivibile_non_lascia_la_sonda`.

Dopo ogni verifica ripristinare il codice e rieseguire: 8 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/app/core/paths.py backend/tests/test_data_dir.py
git commit -m "feat(paths): la cartella dei dati e' distinta da quella del codice

BACKEND_DIR significava due cose insieme. In un .app firmato la cartella del
codice e' di sola lettura, e scriverci invaliderebbe la firma."
```

---

### Task 2: I punti di scrittura di `config.py`

**Files:**
- Modify: `backend/app/core/config.py` (righe 1-16, 96-118)
- Test: `backend/tests/test_config_paths.py`

**Interfaces:**
- Consumes: `app.core.paths` — `BACKEND_DIR`, `DATA_DIR` (Task 1).
- Produces: `config.BACKEND_DIR` resta importabile (`core/version.py` e `services/system_probe.py` lo prendono da lì). `LOG_DIR`, `LOG_FILE`, `DEFAULT_DATABASE_PATH`, `DEFAULT_DATABASE_URL` invariati come nomi, riancorati come valori.

**Nota per chi implementa:** i validator devono leggere `paths.DATA_DIR` **come attributo del modulo**, non tramite `from app.core.paths import DATA_DIR`. Un nome importato si lega una volta sola all'import e non risponderebbe più al `monkeypatch.setattr` dei test — né, in futuro, a nient'altro.

- [ ] **Step 1: Scrivere i test che falliscono**

In `backend/tests/test_config_paths.py`, aggiungere `from app.core import paths`
al blocco di import in testa al file (accanto a `from app.core.config import
Settings`), e i test in coda:

```python
def test_cache_relative_si_ancorano_a_data_dir(monkeypatch, tmp_path):
    """I default testuali non cambiano: cambia la radice contro cui si
    risolvono. È così che il bundle li sposta senza toccare le impostazioni."""
    monkeypatch.setattr(paths, "DATA_DIR", tmp_path)
    s = Settings(cover_cache_dir="./data/cover_cache",
                 thumb_cache_dir="./data/thumb_cache",
                 bin_dir="./data/bin")
    assert s.cover_cache_dir == (tmp_path / "data/cover_cache").resolve().as_posix()
    assert s.thumb_cache_dir == (tmp_path / "data/thumb_cache").resolve().as_posix()
    assert s.bin_dir == (tmp_path / "data/bin").resolve().as_posix()


def test_database_relativo_si_ancora_a_data_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(paths, "DATA_DIR", tmp_path)
    s = Settings(database_url="sqlite:///data/djassistant.db")
    atteso = (tmp_path / "data/djassistant.db").resolve().as_posix()
    assert s.database_url == f"sqlite:///{atteso}"


def test_percorso_assoluto_dell_utente_non_viene_riancorato(monkeypatch, tmp_path):
    """Chi ha messo un percorso assoluto nel proprio .env non deve vederselo
    spostare sotto la cartella dei dati: i validator riancorano solo i relativi.

    Il confronto passa da `.resolve()` perche' e' quello che il validator fa,
    su relativi e assoluti indifferentemente: su macOS /var e' un symlink a
    /private/var, e un'uguaglianza col letterale fallirebbe per la
    normalizzazione dei symlink invece che per il riancoraggio, cioe' per il
    motivo sbagliato."""
    monkeypatch.setattr(paths, "DATA_DIR", tmp_path)
    s = Settings(bin_dir="/opt/cratory/bin", cover_cache_dir="/var/cover")
    assert s.bin_dir == Path("/opt/cratory/bin").resolve().as_posix()
    assert s.cover_cache_dir == Path("/var/cover").resolve().as_posix()
    # Il punto del test: nessuno dei due e' finito sotto DATA_DIR.
    assert not s.bin_dir.startswith(str(tmp_path))
    assert not s.cover_cache_dir.startswith(str(tmp_path))


def test_backend_dir_resta_importabile_da_config():
    """core/version.py e services/system_probe.py lo prendono da qui."""
    from app.core.config import BACKEND_DIR
    assert BACKEND_DIR == paths.BACKEND_DIR
```

- [ ] **Step 2: Eseguirli per vederli fallire**

```bash
cd backend && /Users/lucadenegri/Develop/DJProject01/backend/.venv/bin/python -m pytest tests/test_config_paths.py -q
```

Atteso: **2 FAIL** — `test_cache_relative_si_ancorano_a_data_dir` e
`test_database_relativo_si_ancora_a_data_dir`, perché i validator si ancorano
ancora a `BACKEND_DIR`. Gli altri due (`test_percorso_assoluto_dell_utente_non_viene_riancorato`,
`test_backend_dir_resta_importabile_da_config`) passano già: sono guardie, non
obiettivi.

- [ ] **Step 3: Riancorare le costanti di modulo**

In `backend/app/core/config.py`, sostituire le righe 8-12:

```python
BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
LOG_DIR = BACKEND_DIR / "logs"
LOG_FILE = LOG_DIR / "djassistant.log"
DEFAULT_DATABASE_PATH = BACKEND_DIR / "data" / "djassistant.db"
DEFAULT_DATABASE_URL = f"sqlite:///{DEFAULT_DATABASE_PATH.as_posix()}"
```

con:

```python
from app.core import paths

# Ri-esportata: core/version.py e services/system_probe.py la importano da qui.
BACKEND_DIR = paths.BACKEND_DIR
# Tutto ciò che si scrive sta sotto DATA_DIR, che senza CRATORY_DATA_DIR è
# BACKEND_DIR: in sviluppo non cambia niente, in un bundle diverge.
LOG_DIR = paths.DATA_DIR / "logs"
LOG_FILE = LOG_DIR / "djassistant.log"
DEFAULT_DATABASE_PATH = paths.DATA_DIR / "data" / "djassistant.db"
DEFAULT_DATABASE_URL = f"sqlite:///{DEFAULT_DATABASE_PATH.as_posix()}"
```

L'import `from pathlib import Path` alla riga 3 resta: `Path` è usato dai validator.

- [ ] **Step 4: Riancorare `env_file`**

Alla riga 16, sostituire:

```python
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore")
```

con:

```python
    # Il .env segue i dati, non il codice: in un bundle `backend/` è di sola
    # lettura e l'utente non può metterne uno lì dentro.
    model_config = SettingsConfigDict(env_file=paths.DATA_DIR / ".env", extra="ignore")
```

- [ ] **Step 5: Riancorare i due validator**

In `normalize_database_url`, sostituire il corpo del `if`:

```python
        if not db_path.is_absolute():
            db_path = BACKEND_DIR / db_path
```

con:

```python
        if not db_path.is_absolute():
            db_path = paths.DATA_DIR / db_path
```

e aggiornarne il docstring da `"""SQLite locale sempre relativo a backend/, mai alla cwd del processo."""` a:

```python
        """SQLite locale sempre relativo alla cartella dei dati, mai alla cwd."""
```

In `_cache_dir_assoluta`, sostituire:

```python
        path = Path(value)
        if not path.is_absolute():
            path = BACKEND_DIR / path
```

con:

```python
        path = Path(value)
        if not path.is_absolute():
            path = paths.DATA_DIR / path
```

e aggiornarne il docstring:

```python
        """Path relativo risolto rispetto alla cartella dei dati, mai alla cwd
        del processo: stesso difetto che database_url aveva prima del suo
        validator. `paths.DATA_DIR` letto come attributo, non importato: un
        nome importato si legherebbe una volta sola all'import."""
```

- [ ] **Step 6: Eseguire i test**

```bash
cd backend && /Users/lucadenegri/Develop/DJProject01/backend/.venv/bin/python -m pytest tests/test_config_paths.py tests/test_data_dir.py -q
```

Atteso: tutti passati.

- [ ] **Step 7: Eseguire i test che dipendono da LOG_DIR**

```bash
cd backend && /Users/lucadenegri/Develop/DJProject01/backend/.venv/bin/python -m pytest tests/test_logging_setup.py -q
```

Atteso: nessun fallimento nuovo.

- [ ] **Step 8: Verificare che non sia cambiato niente per chi non usa il seam**

L'intera suite, che gira senza `CRATORY_DATA_DIR`:

```bash
cd backend && /Users/lucadenegri/Develop/DJProject01/backend/.venv/bin/python -m pytest tests -q
```

Atteso: stesso esito di prima del task, nessun fallimento nuovo. Se qualcosa fallisce, è una regressione da correggere qui e non da rimandare.

- [ ] **Step 9: Commit**

```bash
git add backend/app/core/config.py backend/tests/test_config_paths.py
git commit -m "feat(config): database, log, cache e .env seguono la cartella dei dati

I default testuali non cambiano: cambia la radice contro cui i validator li
risolvono. Senza CRATORY_DATA_DIR resta esattamente il comportamento di prima."
```

---

### Task 3: L'avvio

**Files:**
- Modify: `backend/app/main.py:1-16`, `backend/app/main.py:62-63`
- Test: `backend/tests/test_avvio_data_dir.py`

**Interfaces:**
- Consumes: `app.core.paths` — `DATA_DIR`, `verifica_scrivibile` (Task 1); `config.setup_logging` (Task 2).
- Produces: niente di nuovo. Cambia il comportamento all'avvio: `.env` letto da `DATA_DIR`, e un `RuntimeError` leggibile se `DATA_DIR` non è scrivibile.

- [ ] **Step 1: Scrivere i test che falliscono**

Creare `backend/tests/test_avvio_data_dir.py`:

```python
"""L'avvio legge il .env dalla cartella dei dati e si ferma con un messaggio
comprensibile se quella cartella non è scrivibile."""
import os
import stat
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient

from app.core import paths
from app.main import app


def test_dotenv_letto_dalla_cartella_dei_dati(tmp_path):
    """In un bundle `backend/` è di sola lettura: il .env deve stare coi dati.

    Subprocess e non monkeypatch: `env_file` si fissa alla definizione della
    classe Settings, quindi va provato il percorso d'avvio vero — che è poi
    quello che eseguirà Tauri.
    """
    (tmp_path / ".env").write_text("LOG_LEVEL=WARNING\n")
    ambiente = {k: v for k, v in os.environ.items() if k != "LOG_LEVEL"}
    ambiente["CRATORY_DATA_DIR"] = str(tmp_path)
    esito = subprocess.run(
        [sys.executable, "-c",
         "from app.core.config import settings; print(settings.log_level)"],
        cwd=str(paths.BACKEND_DIR), env=ambiente,
        capture_output=True, text=True,
    )
    assert esito.returncode == 0, esito.stderr
    assert esito.stdout.strip() == "WARNING"


def test_load_dotenv_popola_l_ambiente_dalla_cartella_dei_dati(tmp_path):
    """`load_dotenv` in main.py ed `env_file` in config.py sono due meccanismi
    diversi con due effetti diversi: il primo riempie os.environ — da cui
    organize/integrations/acoustid.py legge FPCALC direttamente — il secondo i
    campi di Settings. Coprire il secondo non copre il primo, e questo test e'
    l'unico che importa `app.main`."""
    (tmp_path / ".env").write_text("FPCALC=/percorso/finto/fpcalc\n")
    ambiente = {k: v for k, v in os.environ.items() if k != "FPCALC"}
    ambiente["CRATORY_DATA_DIR"] = str(tmp_path)
    esito = subprocess.run(
        [sys.executable, "-c",
         "import app.main, os; print('FPCALC=' + str(os.environ.get('FPCALC')))"],
        cwd=str(paths.BACKEND_DIR), env=ambiente,
        capture_output=True, text=True,
    )
    assert esito.returncode == 0, esito.stderr
    assert "FPCALC=/percorso/finto/fpcalc" in esito.stdout


def test_avvio_con_cartella_non_scrivibile_dice_perche(monkeypatch, tmp_path):
    """Il messaggio è tutto ciò che l'utente di un'app impacchettata vedrà."""
    bloccata = tmp_path / "sola-lettura"
    bloccata.mkdir()
    bloccata.chmod(stat.S_IRUSR | stat.S_IXUSR)
    monkeypatch.setattr(paths, "DATA_DIR", bloccata)
    try:
        with pytest.raises(RuntimeError) as errore:
            with TestClient(app):
                pass
        assert paths.DATA_DIR_ENV in str(errore.value)
        assert str(bloccata) in str(errore.value)
    finally:
        bloccata.chmod(stat.S_IRWXU)
```

- [ ] **Step 2: Eseguirli per vederli fallire**

```bash
cd backend && /Users/lucadenegri/Develop/DJProject01/backend/.venv/bin/python -m pytest tests/test_avvio_data_dir.py -q
```

Atteso: **1 FAIL** — `test_avvio_con_cartella_non_scrivibile_dice_perche`, perche' nessuno controlla la scrivibilita' e l'avvio procede senza sollevare. `test_dotenv_letto_dalla_cartella_dei_dati` passa gia': copre `env_file`, che il Task 2 ha gia' riancorato. `test_load_dotenv_popola_l_ambiente_dalla_cartella_dei_dati` invece fallisce solo dopo lo Step 3, ed e' l'unico che copre davvero la riga di `main.py`: i due meccanismi sono distinti.

- [ ] **Step 3: Leggere il `.env` dalla cartella dei dati**

In `backend/app/main.py`, sostituire le righe 1-11:

```python
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
# pydantic-settings carica .env dentro Settings (incluso ai_api_key, passato
# esplicito ai client Anthropic), ma non tocca l'os.environ di processo. Serve
# comunque per FPCALC, letto direttamente da os.environ in
# organize/integrations/acoustid.py.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")
```

con:

```python
import logging
import time
from contextlib import asynccontextmanager

from dotenv import load_dotenv

from app.core import paths
# pydantic-settings carica .env dentro Settings (incluso ai_api_key, passato
# esplicito ai client Anthropic), ma non tocca l'os.environ di processo. Serve
# comunque per FPCALC, letto direttamente da os.environ in
# organize/integrations/acoustid.py.
#
# Il percorso arriva da app.core.paths e non da app.core.config: importare
# config qui costruirebbe Settings() prima che il .env sia nell'ambiente, che è
# proprio quello che questa riga deve evitare. paths non dipende da niente.
load_dotenv(paths.DATA_DIR / ".env")
```

`from pathlib import Path` sparisce dal blocco sopra: alla data di scrittura di
questo piano `Path` compare in `main.py` solo alle righe 4 e 11, entrambe
sostituite qui. Verificarlo comunque prima di considerare chiuso lo step:

```bash
cd backend && grep -n "Path" app/main.py
```

Se compare altrove, lasciare l'import.

- [ ] **Step 4: Controllare la scrivibilità all'avvio**

In `backend/app/main.py`, dentro `lifespan`, sostituire:

```python
async def lifespan(app: FastAPI):
    setup_logging()
```

con:

```python
async def lifespan(app: FastAPI):
    # Prima di setup_logging(), che è il primo a scrivere (LOG_DIR.mkdir).
    # Fallire qui con un messaggio leggibile è l'unica forma di diagnosi
    # disponibile a un utente che ha un'icona e nessun terminale.
    paths.verifica_scrivibile(paths.DATA_DIR)
    setup_logging()
```

- [ ] **Step 5: Eseguire i test**

```bash
cd backend && /Users/lucadenegri/Develop/DJProject01/backend/.venv/bin/python -m pytest tests/test_avvio_data_dir.py -q
```

Atteso: 2 passed.

- [ ] **Step 6: Eseguire l'intera suite**

```bash
cd backend && /Users/lucadenegri/Develop/DJProject01/backend/.venv/bin/python -m pytest tests -q
```

Atteso: nessun fallimento nuovo rispetto a prima del task.

- [ ] **Step 7: Commit**

```bash
git add backend/app/main.py backend/tests/test_avvio_data_dir.py
git commit -m "feat(avvio): .env dalla cartella dei dati, e un errore leggibile se non e' scrivibile

Chi apre un'icona non ha un terminale in cui leggere uno stack trace: un
PermissionError sepolto in un log che non sa di avere e' indistinguibile da
un'app che non parte."
```

---

### Task 4: La cartella dei binari gestiti

**Files:**
- Modify: `backend/app/services/system_probe.py` (dentro `managed_bin_dir`)
- Test: `backend/tests/test_managed_bin_dir.py`

**Interfaces:**
- Consumes: `app.core.paths.DATA_DIR` (Task 1).
- Produces: `managed_bin_dir() -> Path` — firma invariata, radice cambiata.

**Nota:** `settings.bin_dir` è già reso assoluto dal validator di Task 2 quando `Settings` viene costruito, quindi il ramo relativo di `managed_bin_dir` si esercita solo passando un valore relativo in `CRATORY_BIN_DIR`. È il motivo per cui il test qui sotto imposta quella variabile.

- [ ] **Step 1: Scrivere i test che falliscono**

Creare `backend/tests/test_managed_bin_dir.py`:

```python
"""La cartella dei binari gestiti sta coi dati, non col codice: in un bundle
`backend/` è di sola lettura e l'installer non potrebbe scriverci."""
from app.core import paths
from app.services import system_probe


def test_bin_dir_relativa_si_ancora_ai_dati(monkeypatch, tmp_path):
    monkeypatch.setattr(paths, "DATA_DIR", tmp_path)
    monkeypatch.setenv(system_probe.BIN_DIR_ENV, "bin-relativa")
    assert system_probe.managed_bin_dir() == tmp_path / "bin-relativa"


def test_bin_dir_assoluta_passa_intatta(monkeypatch, tmp_path):
    """È il caso del bundle Tauri: la variabile punta dentro l'app."""
    bundle = tmp_path / "Cratory.app" / "Contents" / "Resources" / "bin"
    monkeypatch.setenv(system_probe.BIN_DIR_ENV, str(bundle))
    assert system_probe.managed_bin_dir() == bundle


def test_non_tocca_il_filesystem(monkeypatch, tmp_path):
    """Gira su praticamente ogni resolve_binary: un mkdir qui trasformerebbe un
    GET /api/services in un 500 su un mount di sola lettura."""
    monkeypatch.setattr(paths, "DATA_DIR", tmp_path)
    monkeypatch.setenv(system_probe.BIN_DIR_ENV, "bin-relativa")
    system_probe.managed_bin_dir()
    assert not (tmp_path / "bin-relativa").exists()
```

- [ ] **Step 2: Eseguirli per vederli fallire**

```bash
cd backend && /Users/lucadenegri/Develop/DJProject01/backend/.venv/bin/python -m pytest tests/test_managed_bin_dir.py -q
```

Atteso: 1 FAIL (`test_bin_dir_relativa_si_ancora_ai_dati`, che risolve ancora contro `BACKEND_DIR`). Gli altri due passano già, e sono lì come guardie.

- [ ] **Step 3: Riancorare**

In `backend/app/services/system_probe.py`, dentro `managed_bin_dir`, sostituire:

```python
    from app.core.config import BACKEND_DIR, settings
    raw = os.environ.get(BIN_DIR_ENV) or settings.bin_dir
    path = Path(raw)
    if not path.is_absolute():
        path = BACKEND_DIR / path
    return path
```

con:

```python
    from app.core import paths
    from app.core.config import settings
    raw = os.environ.get(BIN_DIR_ENV) or settings.bin_dir
    path = Path(raw)
    if not path.is_absolute():
        path = paths.DATA_DIR / path
    return path
```

Poi aggiungere, come ultimo paragrafo del docstring di `managed_bin_dir`
(subito prima delle virgolette di chiusura), lasciando intatto il testo che c'è:

```
    La radice dei percorsi relativi è la cartella dei dati, non quella del
    codice: in un bundle l'installer non potrebbe scrivere dentro `backend/`.
```

- [ ] **Step 4: Eseguire i test**

```bash
cd backend && /Users/lucadenegri/Develop/DJProject01/backend/.venv/bin/python -m pytest tests/test_managed_bin_dir.py -q
```

Atteso: 3 passed.

- [ ] **Step 5: Eseguire i test dell'installer, che dipendono da questa cartella**

```bash
cd backend && /Users/lucadenegri/Develop/DJProject01/backend/.venv/bin/python -m pytest tests/test_binary_install.py tests/test_binary_download.py tests/test_binary_extract.py tests/test_system_probe.py -q
```

Atteso: nessun fallimento nuovo.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/system_probe.py backend/tests/test_managed_bin_dir.py
git commit -m "feat(probe): i binari gestiti stanno con i dati, non col codice"
```

---

### Task 5: L'invariante

**Files:**
- Test: `backend/tests/test_niente_scritture_nel_checkout.py`

**Interfaces:**
- Consumes: tutto quanto sopra. Nessun codice di produzione nuovo.
- Produces: la guardia che tiene nel tempo.

Questo test non elenca i cinque punti di scrittura: verifica la proprietà. Un sesto punto aggiunto fra un anno senza riancorarlo lo fa fallire, mentre un test che confronta cinque percorsi noti passerebbe contento.

- [ ] **Step 1: Scrivere il test**

Creare `backend/tests/test_niente_scritture_nel_checkout.py`:

```python
"""Con CRATORY_DATA_DIR impostata, sotto backend/ non compare niente di nuovo.

Non è la somma dei test precedenti: quelli verificano cinque percorsi noti,
questo verifica la proprietà. È l'unico che si accorge di un sesto punto di
scrittura aggiunto in futuro senza riancorarlo.

Subprocess e non monkeypatch: `settings` e `DATA_DIR` sono singleton costruiti
a import-time, quindi cambiare la variabile dentro il processo di pytest non
rifà i calcoli. Il subprocess prova il percorso d'avvio vero, che è poi quello
che eseguirà Tauri.
"""
import os
import subprocess
import sys
from pathlib import Path

from app.core import paths

# `.venv` escluso per velocità (decine di migliaia di file nel checkout
# principale); `__pycache__` e `.pyc` perché sarebbe il test stesso a sporcare
# l'albero che sta osservando, e diventerebbe intermittente.
_IGNORATI = {"__pycache__", ".venv"}


def _fotografia(radice: Path) -> set[tuple[str, int, int]]:
    """Percorso, dimensione e mtime — non il solo percorso.

    Un confronto fra soli nomi e' cieco sul caso piu' probabile. I cinque
    ancoraggi riusano nomi fissi (`djassistant.log`, `djassistant.db`), quindi
    su qualunque macchina che abbia gia' avviato l'app in sviluppo quei file
    esistono gia': una regressione che ci riscrive dentro non fa comparire
    nessun nome nuovo, e un confronto fra insiemi di nomi resta verde mentre la
    regressione e' viva. Con dimensione e mtime la riscrittura si vede.

    Leggere un file non ne cambia l'mtime, quindi niente falsi positivi da
    lettura. Le cartelle entrano col solo nome: il loro mtime cambia anche
    quando ci compare dentro un `__pycache__` che abbiamo gia' escluso, e
    quello si', sarebbe un falso positivo.
    """
    voci: set[tuple[str, int, int]] = set()
    for percorso in radice.rglob("*"):
        rel = percorso.relative_to(radice)
        if set(rel.parts) & _IGNORATI or percorso.suffix == ".pyc":
            continue
        if percorso.is_dir():
            voci.add((str(rel), -1, -1))
            continue
        try:
            stato = percorso.stat()
        except OSError:
            continue
        voci.add((str(rel), stato.st_size, stato.st_mtime_ns))
    return voci


_ESERCITA_LE_SCRITTURE = (
    "from app.core.config import setup_logging;"
    "from app.db import ensure_schema;"
    "from app.organize.services import thumbs, cover_cache;"
    "from app.services import system_probe;"
    "setup_logging();"
    "ensure_schema();"
    "thumbs.thumb_path(1);"
    "cover_cache.thumb_path(1);"
    "system_probe.ensure_bin_dir();"
    "print('fatto')"
)


def test_niente_di_nuovo_sotto_backend(tmp_path):
    prima = _fotografia(paths.BACKEND_DIR)

    # DATABASE_URL va tolta: conftest.py la punta a un file temporaneo, e con
    # quella impostata il default ancorato a DATA_DIR non verrebbe esercitato.
    ambiente = {k: v for k, v in os.environ.items() if k != "DATABASE_URL"}
    ambiente["CRATORY_DATA_DIR"] = str(tmp_path)
    esito = subprocess.run(
        [sys.executable, "-c", _ESERCITA_LE_SCRITTURE],
        cwd=str(paths.BACKEND_DIR), env=ambiente,
        capture_output=True, text=True,
    )
    assert esito.returncode == 0, esito.stderr
    assert esito.stdout.strip().endswith("fatto")

    scritti = _fotografia(paths.BACKEND_DIR) - prima
    assert not scritti, (
        "scritti o modificati dentro il checkout: "
        f"{sorted({v[0] for v in scritti})}"
    )


def test_e_invece_tutto_e_atterrato_nella_cartella_dei_dati(tmp_path):
    """Il complemento del test sopra: senza questo, un backend che non scrive
    da nessuna parte passerebbe la prima asserzione a pieni voti."""
    ambiente = {k: v for k, v in os.environ.items() if k != "DATABASE_URL"}
    ambiente["CRATORY_DATA_DIR"] = str(tmp_path)
    esito = subprocess.run(
        [sys.executable, "-c", _ESERCITA_LE_SCRITTURE],
        cwd=str(paths.BACKEND_DIR), env=ambiente,
        capture_output=True, text=True,
    )
    assert esito.returncode == 0, esito.stderr

    assert (tmp_path / "logs" / "djassistant.log").is_file()
    assert (tmp_path / "data" / "djassistant.db").is_file()
    assert (tmp_path / "data" / "bin").is_dir()
    assert (tmp_path / "data" / "thumb_cache").is_dir()
    assert (tmp_path / "data" / "cover_cache").is_dir()
```

- [ ] **Step 2: Eseguire i test**

```bash
cd backend && /Users/lucadenegri/Develop/DJProject01/backend/.venv/bin/python -m pytest tests/test_niente_scritture_nel_checkout.py -q
```

Atteso: 2 passed. Se il primo fallisce elencando dei percorsi, quelli sono punti di scrittura non riancorati: correggerli, non allargare `_IGNORATI`.

- [ ] **Step 3: Provare l'asserzione rompendo il codice**

In `backend/app/core/config.py` rimettere `LOG_DIR = paths.BACKEND_DIR / "logs"`.

```bash
cd backend && /Users/lucadenegri/Develop/DJProject01/backend/.venv/bin/python -m pytest tests/test_niente_scritture_nel_checkout.py -q
```

Atteso: FAIL su `test_niente_di_nuovo_sotto_backend`, con `logs/djassistant.log` nell'elenco. Se passa, il test non serve a niente e va corretto prima di proseguire.

Ripristinare `LOG_DIR = paths.DATA_DIR / "logs"` e rieseguire: 2 passed.

- [ ] **Step 4: Eseguire l'intera suite**

```bash
cd backend && /Users/lucadenegri/Develop/DJProject01/backend/.venv/bin/python -m pytest tests -q
```

Atteso: nessun fallimento nuovo rispetto a prima del task.

- [ ] **Step 5: Verificare a mano il consegnabile**

Il punto di tutto ①: il backend gira da una cartella di codice in sola lettura.

```bash
cd backend && CRATORY_DATA_DIR="$HOME/Library/Application Support/Cratory-prova" /Users/lucadenegri/Develop/DJProject01/backend/.venv/bin/python -m uvicorn app.main:app --port 8123 &
sleep 6 && curl -sf http://127.0.0.1:8123/api/setup/state && echo && ls -R "$HOME/Library/Application Support/Cratory-prova"
```

Atteso: l'endpoint risponde, e sotto `Cratory-prova` compaiono `data/` e `logs/`. Poi fermare il processo e ripulire:

```bash
kill %1 2>/dev/null; rm -rf "$HOME/Library/Application Support/Cratory-prova"
```

- [ ] **Step 6: Commit**

```bash
git add backend/tests/test_niente_scritture_nel_checkout.py
git commit -m "test(paths): l'invariante e' che il checkout resti intatto, non che i cinque percorsi combacino

Un sesto punto di scrittura aggiunto senza riancorarlo fa fallire questo test;
un confronto fra cinque percorsi noti passerebbe contento."
```

---

### Task 6: La documentazione

**Files:**
- Modify: `docs/ARCHITECTURE.md` (sezione del seam Tauri, intorno a riga 886)
- Modify: `docs/ROADMAP.md` (sezione «Current state»)
- Modify: `PROGRESS.md` (sezione «Current state by area»)

**Interfaces:**
- Consumes: il comportamento dei Task 1-5.
- Produces: niente codice.

`docs/API.md` non si tocca: nessun endpoint cambia.

- [ ] **Step 1: Estendere la sezione del seam in `docs/ARCHITECTURE.md`**

Il paragrafo che comincia con `**One seam exists purely for an eventual Tauri desktop build**` va aggiornato: i seam ora sono tre, non uno. Aggiungere in coda a quel paragrafo:

```markdown
A second seam of the same shape covers what the app *writes*. `core/paths.py`
separates two meanings that used to share one name: `BACKEND_DIR` is where the
code lives, `DATA_DIR` is where the writes go — database, logs, cover and thumb
caches, the managed `bin/` folder, and `.env`. `CRATORY_DATA_DIR` sets the
second; without it the two coincide and nothing changes, which is why
development, self-hosting and the test suite never notice the seam exists.
It matters because inside a signed `.app` the code directory is read-only, and
writing there would invalidate the signature. A relative `CRATORY_DATA_DIR`
raises at import rather than resolving against the process's working directory:
data landing wherever the app happened to be launched from is the exact defect
the config validators already declare they fixed. The startup writability check
exists for a packaged user, who has an icon and no terminal in which to read a
`PermissionError`.
```

- [ ] **Step 2: Aggiungere la riga in `docs/ROADMAP.md`**

Nella sezione «Current state», dopo il punto «Guided setup», aggiungere:

```markdown
- **Bundle-ready** (2026-08-22). The backend no longer writes inside its own
  checkout: `core/paths.py` splits `BACKEND_DIR` (where the code is) from
  `DATA_DIR` (where the writes go), with `CRATORY_DATA_DIR` selecting the
  second and everything unchanged when it is unset. An invariant test starts
  the app in a subprocess with the variable set and asserts that nothing new
  appears under `BACKEND_DIR` — the property, not a list of five known paths.
  First of the four sub-projects of the Tauri packaging work
  (`docs/superpowers/specs/2026-08-22-tauri-decomposizione-design.md`).
```

- [ ] **Step 3: Aggiungere la riga in `PROGRESS.md`**

Nella sezione «Current state by area», in cima all'elenco (è la voce più recente):

```markdown
- **Bundle-ready** (2026-08-22): the backend runs entirely from a read-only code
  directory. `CRATORY_DATA_DIR` — same seam shape as `CRATORY_BIN_DIR` and
  `CRATORY_VERSION` — redirects database, logs, caches, managed binaries and
  `.env`; unset, nothing changes. Step one of four toward a Tauri desktop build.
```

- [ ] **Step 4: Rileggere quello che si è scritto**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/wizardly-bassi-00b805 && git diff docs/ PROGRESS.md
```

Controllare che non ci siano affermazioni non vere: in particolare che nessuna riga dica che il bundle Tauri esiste, perché non esiste — esiste solo la condizione perché possa esistere.

- [ ] **Step 5: Commit**

```bash
git add docs/ARCHITECTURE.md docs/ROADMAP.md PROGRESS.md
git commit -m "docs(paths): il seam dei dati accanto a quelli dei binari e della versione"
```

---

## Verifica finale

- [ ] L'intera suite backend passa:

```bash
cd backend && /Users/lucadenegri/Develop/DJProject01/backend/.venv/bin/python -m pytest tests -q
```

- [ ] Il backend parte con `CRATORY_DATA_DIR` impostata e scrive solo lì (Task 5, Step 5).
- [ ] Il backend parte **senza** `CRATORY_DATA_DIR` e si comporta come sempre:

```bash
cd backend && /Users/lucadenegri/Develop/DJProject01/backend/.venv/bin/python -m uvicorn app.main:app --port 8124 &
sleep 6 && curl -sf http://127.0.0.1:8124/api/setup/state && echo && kill %1
```

- [ ] `git status --porcelain` è vuoto: niente lasciato indietro, niente file di prova committati per sbaglio.
