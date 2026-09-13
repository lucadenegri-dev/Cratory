# Backup e ripristino — piano di implementazione

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Un backup in un solo zip dei dati utente (DB via `VACUUM INTO`, cover caricate, `.env`, `slskd.yml`), creabile da Impostazioni e su richiesta prima di un aggiornamento, e un ripristino dall'app che si applica a freddo al riavvio successivo.

**Architecture:** Un servizio deterministico `backend/app/services/backup.py` (crea, ispeziona, prepara/conferma/annulla, applica al riavvio) dietro un router HTTP-only `/api/backup`. Il picker nativo impara «salva con nome». Il frontend aggiunge una scheda «Dati» in Impostazioni e sostituisce la conferma dell'updater con una modale che offre il backup prima. Lo scambio dei file avviene in `main.py` **prima di `load_dotenv`**, mai a DB aperto.

**Tech Stack:** Python 3.11, FastAPI, sqlite3 (≥ 3.27 per `VACUUM INTO`; in uso 3.53), `zipfile`, pytest; Next.js 16, React, vitest + testing-library; AppleScript via `osascript`.

**Spec:** `docs/superpowers/specs/2026-09-13-backup-ripristino-design.md`

## Global Constraints

- `backend/app/services/backup.py` **non importa `app.core.config` né `app.core.version` a livello di modulo**: `applica_se_in_attesa()` gira prima di `load_dotenv`. Tutti gli import che portano a `config` stanno dentro le funzioni.
- `paths.DATA_DIR` si legge sempre come attributo (`paths.DATA_DIR`), mai `from app.core.paths import DATA_DIR`: i test lo monkeypatchano.
- Nomi dei membri dello zip, fissi: `manifest.json`, `data/djassistant.db`, `data/covers/<file>`, `.env`, `data/slskd.yml`. `manifest.json` ha `formato: 1`.
- Codici d'errore stabili: `archivio_non_valido`, `manifest_assente`, `db_assente`, `db_corrotto`, `versione_piu_recente`, `backup_in_corso`, `job_in_corso`, `niente_da_ripristinare`, `file_non_trovato`. Il client HTTP del frontend li traduce già da solo (`translateApiError` legge `DICTIONARIES[lang].errors[code]` e mette la frase in `ApiError.message`): i codici nuovi vanno nella sezione `errors` di `it.ts` ed `en.ts`, e i componenti mostrano `errText(e)`. Nessuna tabella di traduzione nei componenti.
- Chiavi `app_state`: `last_backup_at` (ISO 8601 UTC), `last_restore` (JSON dell'`EsitoRipristino`).
- Cartelle sotto `DATA_DIR/data/`: `restore-staging/`, `restore-pending.json`, `pre-restore/`.
- Nessuna riga `Co-Authored-By` nei commit (preferenza dell'autore del repo).
- Comandi: backend `cd backend && source .venv/bin/activate && python -m pytest tests/<file> -q`; frontend `cd frontend && npx vitest run tests/<file>` e `npm run lint`.
- Frontend: leggere `frontend/CLAUDE.md` prima di toccare pagine. Spazi JSX espliciti con `{" "}` quando il testo va a capo nel sorgente.
- Testi user-facing solo nei dizionari `frontend/lib/i18n/it.ts` e `en.ts` (`Dictionary = typeof en`: le due strutture devono coincidere).

---

## Struttura dei file

| File | Ruolo |
|---|---|
| `backend/app/services/backup.py` (nuovo) | contenuto, stima, crea, ispeziona, prepara/conferma/annulla, applica_se_in_attesa, controllo job |
| `backend/app/routers/backup.py` (nuovo) | i sei endpoint `/api/backup/*`, solo mapping eccezioni → `api_error` |
| `backend/app/services/native_picker.py` | `kind="save"` con `default_name` |
| `backend/app/routers/files.py` | `PickIn.kind` esteso, `default_name` |
| `backend/app/main.py` | `applica_se_in_attesa()` prima di `load_dotenv`; esito in `app_state` nel lifespan; router |
| `backend/tests/test_backup.py` (nuovo) | servizio |
| `backend/tests/test_backup_router.py` (nuovo) | router |
| `backend/tests/test_native_picker.py`, `test_files_pick_router.py` | `save` |
| `backend/tests/test_niente_scritture_nel_checkout.py` | esercita backup e staging |
| `frontend/lib/api/backup.ts` (nuovo) + `frontend/lib/api.ts` | client tipizzato |
| `frontend/lib/api/settings.ts` | `pickPath` con `save` e `defaultName` |
| `frontend/components/path-picker-button.tsx` | `kind="save"`, `defaultName` |
| `frontend/components/settings/backup-card.tsx` (nuovo) | scheda Dati |
| `frontend/components/settings/conferma-aggiornamento.tsx` (nuovo) | la modale a tre uscite |
| `frontend/components/settings/aggiornamento-guscio.tsx` | usa la modale nuova |
| `frontend/app/settings/page.tsx` | monta la scheda Dati |
| `frontend/lib/i18n/it.ts`, `en.ts` | chiavi `settings.backup*`, `settings.versionBackup*` |
| `frontend/tests/backup-card.test.tsx`, `conferma-aggiornamento.test.tsx` (nuovi), `aggiornamento-guscio.test.tsx` | |
| `docs/API.md`, `docs/ARCHITECTURE.md`, `docs/ROADMAP.md`, `PROGRESS.md`, `README.md` | |

---

### Task 1: il picker impara «salva con nome»

**Files:**
- Modify: `backend/app/services/native_picker.py:42-100`
- Modify: `backend/app/routers/files.py:31-60`
- Test: `backend/tests/test_native_picker.py`, `backend/tests/test_files_pick_router.py`

**Interfaces:**
- Produces: `native_picker.build_script(kind: str, start: str | None, prompt: str | None, default_name: str | None = None) -> str`; `native_picker.pick_path(kind, start=None, prompt=None, default_name=None, *, runner=subprocess.run) -> str | None`; `PickIn.kind: Literal["folder","file","save"]`, `PickIn.default_name: str | None`.

- [ ] **Step 1: test del servizio (fallisce)**

Aggiungere in fondo a `backend/tests/test_native_picker.py`:

```python
def test_build_script_save_usa_choose_file_name_col_nome_di_default():
    script = np.build_script("save", None, "Salva il backup", default_name="cratory-backup.zip")
    assert "choose file name" in script
    assert 'default name "cratory-backup.zip"' in script
    assert 'with prompt "Salva il backup"' in script
    assert "choose file" not in script.replace("choose file name", "")


def test_build_script_save_escapa_le_virgolette_nel_nome():
    script = np.build_script("save", None, None, default_name='a"b.zip')
    assert 'default name "a\\"b.zip"' in script


def test_pick_save_non_tronca_il_percorso(monkeypatch):
    _force_available(monkeypatch)
    got = np.pick_path("save", default_name="x.zip",
                       runner=lambda *a, **k: _proc(stdout="/Users/x/Desktop/x.zip\n"))
    assert got == "/Users/x/Desktop/x.zip"
```

- [ ] **Step 2: eseguire, verificare il rosso**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_native_picker.py -q`
Expected: 3 FAIL (`TypeError: build_script() got an unexpected keyword argument 'default_name'`).

- [ ] **Step 3: implementare in `native_picker.py`**

Sostituire `build_script` e la firma di `pick_path`:

```python
def build_script(kind: str, start: str | None, prompt: str | None,
                 default_name: str | None = None) -> str:
    """AppleScript `choose folder`/`choose file`/`choose file name` dentro System
    Events attivato: porta il dialog in primo piano anche se il backend gira in
    background. `start` diventa `default location` solo se è una directory
    esistente. `choose file name` (kind="save") restituisce un percorso anche
    se il file non esiste e chiede da solo conferma di sovrascrittura.

    Il `choose` gira dentro un blocco `with timeout of` esplicito: l'Apple
    Event verso System Events ha di default un reply timeout di 120s, troppo
    poco se l'utente lascia il dialog aperto più a lungo. Lo estendiamo a
    `TIMEOUT_SECONDS` per allinearlo al timeout del subprocess."""
    if kind == "folder":
        choose = "choose folder"
    elif kind == "save":
        choose = "choose file name"
    else:
        choose = "choose file"
    if prompt:
        choose += f' with prompt "{_escape(prompt)}"'
    if kind == "save" and default_name:
        choose += f' default name "{_escape(default_name)}"'
    if start:
        start_dir = Path(start).expanduser()
        if start_dir.is_dir():
            choose += f' default location (POSIX file "{_escape(str(start_dir))}")'
    return (
        'tell application "System Events"\n'
        "activate\n"
        f"with timeout of {int(TIMEOUT_SECONDS)} seconds\n"
        f"POSIX path of ({choose})\n"
        "end timeout\n"
        "end tell"
    )


def pick_path(kind: str, start: str | None = None, prompt: str | None = None,
              default_name: str | None = None, *, runner=subprocess.run) -> str | None:
```

e dentro `pick_path` la chiamata diventa `build_script(kind, start, prompt, default_name)`. Il resto del corpo non cambia (`rstrip("/")` resta solo per `folder`).

- [ ] **Step 4: verde**

Run: `python -m pytest tests/test_native_picker.py -q`
Expected: tutti PASS.

- [ ] **Step 5: test del router (fallisce)**

In `backend/tests/test_files_pick_router.py` aggiungere:

```python
def test_pick_save_passa_il_nome_di_default(monkeypatch):
    seen: dict = {}

    def fake_pick(kind, start=None, prompt=None, default_name=None):
        seen.update(kind=kind, default_name=default_name)
        return "/Users/x/Desktop/cratory-backup.zip"

    monkeypatch.setattr(native_picker, "pick_path", fake_pick)
    r = client.post("/api/files/pick",
                    json={"kind": "save", "default_name": "cratory-backup.zip"})
    assert r.status_code == 200
    assert r.json() == {"path": "/Users/x/Desktop/cratory-backup.zip"}
    assert seen == {"kind": "save", "default_name": "cratory-backup.zip"}
```

Attenzione: `test_pick_ritorna_il_percorso` ha un `fake_pick(kind, start=None, prompt=None)` che con il nuovo argomento posizionale fallirebbe. Aggiornarlo a `fake_pick(kind, start=None, prompt=None, default_name=None)`.

- [ ] **Step 6: rosso, poi implementare in `routers/files.py`**

```python
class PickIn(BaseModel):
    kind: Literal["folder", "file", "save"]
    start: str | None = None
    prompt: str | None = None
    # Solo per kind="save": il nome proposto nel dialogo.
    default_name: str | None = None
```

e in `pick`: `native_picker.pick_path(body.kind, body.start, body.prompt, body.default_name)`.

- [ ] **Step 7: verde e commit**

Run: `python -m pytest tests/test_native_picker.py tests/test_files_pick_router.py -q`
Expected: PASS.

```bash
git add backend/app/services/native_picker.py backend/app/routers/files.py backend/tests/test_native_picker.py backend/tests/test_files_pick_router.py
git commit -m "feat(files): il picker nativo sa salvare con nome — choose file name con nome di default"
```

---

### Task 2: il servizio di backup — contenuto, stima, creazione

**Files:**
- Create: `backend/app/services/backup.py`
- Test: `backend/tests/test_backup.py`

**Interfaces:**
- Produces:
  - `Voce(nome: str, percorso: str, byte: int, presente: bool)`
  - `EsitoBackup(percorso: str, byte: int, creato_il: str)`
  - `contenuto() -> list[Voce]`; `stima_byte() -> int`; `nome_di_default() -> str`
  - `crea(destinazione: Path) -> EsitoBackup`; solleva `BackupInCorso`
  - costanti `MEMBRO_MANIFEST`, `MEMBRO_DB`, `MEMBRO_ENV`, `MEMBRO_SLSKD`, `PREFISSO_COVERS`, `FORMATO`
  - helper privati usati dai test: `_db_path()`, `_covers_dir()`, `_env_path()`, `_slskd_yml()`

- [ ] **Step 1: fixture e primi test (fallisce)**

Creare `backend/tests/test_backup.py`:

```python
"""Servizio backup: DATA_DIR e DB su cartelle temporanee, sqlite vero."""
import json
import shutil
import sqlite3
import zipfile
from pathlib import Path

import pytest
from sqlalchemy import create_engine

from app.core import paths
from app.core.config import settings
from app.db import Base, ensure_schema
from app.services import backup


@pytest.fixture()
def dati(tmp_path, monkeypatch):
    """Un DATA_DIR temporaneo con un DB vero (schema completo, WAL acceso),
    una cover, un .env, uno slskd.yml, e roba che NON deve entrare."""
    data_dir = tmp_path / "dati"
    (data_dir / "data" / "covers").mkdir(parents=True)
    (data_dir / "data" / "thumb_cache").mkdir()
    (data_dir / "logs").mkdir()
    db_path = data_dir / "data" / "djassistant.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    ensure_schema(engine)
    with sqlite3.connect(db_path, isolation_level=None) as c:
        c.execute("PRAGMA journal_mode=WAL")
    (data_dir / "data" / "covers" / "playlist-1.jpg").write_bytes(b"\xff\xd8cover")
    (data_dir / ".env").write_text("SPOTIFY_CLIENT_ID=abc\n")
    (data_dir / "data" / "slskd.yml").write_text("soulseek:\n  password: segreta\n")
    (data_dir / "data" / "thumb_cache" / "1.jpg").write_bytes(b"no")
    (data_dir / "data" / "slskd.log").write_text("no")
    (data_dir / "logs" / "djassistant.log").write_text("no")
    monkeypatch.setattr(paths, "DATA_DIR", data_dir)
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{db_path}")
    engine.dispose()
    return data_dir


def _membri(zip_path: Path) -> set[str]:
    with zipfile.ZipFile(zip_path) as z:
        return set(z.namelist())


def test_contenuto_elenca_le_quattro_voci_e_le_dimensioni(dati):
    voci = {v.nome: v for v in backup.contenuto()}
    assert set(voci) == {"database", "covers", "env", "slskd"}
    assert all(v.presente for v in voci.values())
    assert voci["covers"].byte == len(b"\xff\xd8cover")
    assert voci["database"].byte > 0


def test_contenuto_segna_assente_cio_che_manca(dati):
    (dati / ".env").unlink()
    voci = {v.nome: v for v in backup.contenuto()}
    assert voci["env"].presente is False and voci["env"].byte == 0


def test_stima_non_dipende_dal_wal(dati):
    prima = backup.stima_byte()
    db = backup._db_path()
    with sqlite3.connect(db, isolation_level=None) as c:
        c.execute("PRAGMA wal_autocheckpoint=0")
        for i in range(200):
            c.execute("INSERT INTO app_state(key, value) VALUES (?, ?)", (f"k{i}", "x" * 4000))
        c.execute("DELETE FROM app_state")
    # Il WAL è cresciuto di centinaia di KB; la stima segue le pagine usate, non il WAL.
    assert (db.parent / "djassistant.db-wal").stat().st_size > 100_000
    assert abs(backup.stima_byte() - prima) < 50_000


def test_nome_di_default_ha_data_e_ora():
    nome = backup.nome_di_default()
    assert nome.startswith("cratory-backup-") and nome.endswith(".zip")
    assert len(nome) == len("cratory-backup-20260913-1840.zip")
```

- [ ] **Step 2: rosso**

Run: `python -m pytest tests/test_backup.py -q`
Expected: `ModuleNotFoundError: No module named 'app.services.backup'`.

- [ ] **Step 3: il modulo, prima parte**

Creare `backend/app/services/backup.py`:

```python
"""Backup e ripristino dei dati utente, in un solo zip.

Cosa entra: il DB (snapshot `VACUUM INTO`, coerente anche col WAL aperto), le
cover caricate, `.env` e `slskd.yml` — credenziali comprese, per scelta: un
ripristino rimette l'app com'era. Cosa resta fuori: cache, log, pid, la
cartella download di slskd (sono i file della libreria, che il disco già
rappresenta).

Il ripristino avviene in due tempi: `prepara` valida ed estrae in staging,
`conferma` scrive un marker, e `applica_se_in_attesa` — chiamato da `main.py`
PRIMA di `load_dotenv` — scambia i file al riavvio, quando nessuno ha ancora
aperto il DB. Per questo il modulo non importa `app.core.config` né
`app.core.version` a livello di modulo: a quel punto l'ambiente non è pronto.

`paths.DATA_DIR` letto come attributo, mai importato per nome: i test lo
monkeypatchano.
"""
from __future__ import annotations

import json
import logging
import shutil
import sqlite3
import threading
import zipfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from app.core import paths

log = logging.getLogger(__name__)

FORMATO = 1
MEMBRO_MANIFEST = "manifest.json"
MEMBRO_DB = "data/djassistant.db"
MEMBRO_ENV = ".env"
MEMBRO_SLSKD = "data/slskd.yml"
PREFISSO_COVERS = "data/covers/"

_lock = threading.Lock()


class BackupInCorso(Exception):
    """Un backup è già in scrittura."""


class BackupNonValido(Exception):
    def __init__(self, codice: str, dettaglio: str = ""):
        super().__init__(dettaglio or codice)
        self.codice = codice
        self.dettaglio = dettaglio


class JobInCorso(Exception):
    def __init__(self, job: str):
        super().__init__(job)
        self.job = job


class NienteDaRipristinare(Exception):
    """`conferma()` senza uno staging preparato."""


@dataclass
class Voce:
    nome: str
    percorso: str
    byte: int
    presente: bool


@dataclass
class EsitoBackup:
    percorso: str
    byte: int
    creato_il: str


# --- percorsi -----------------------------------------------------------------

def _db_path() -> Path:
    from app.core.config import settings  # dentro: vedi docstring del modulo
    return Path(settings.database_url.removeprefix("sqlite:///"))


def _covers_dir() -> Path:
    return paths.DATA_DIR / "data" / "covers"


def _env_path() -> Path:
    return paths.DATA_DIR / ".env"


def _slskd_yml() -> Path:
    return paths.DATA_DIR / "data" / "slskd.yml"


def _staging() -> Path:
    return paths.DATA_DIR / "data" / "restore-staging"


def _marker() -> Path:
    return paths.DATA_DIR / "data" / "restore-pending.json"


def _pre_restore() -> Path:
    return paths.DATA_DIR / "data" / "pre-restore"


def _adesso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# --- contenuto e stima --------------------------------------------------------

def _byte_db(db: Path) -> int:
    """Pagine usate × dimensione pagina: quanto peserà lo snapshot, non quanto
    pesano DB + WAL su disco (il WAL può essere grande quanto il DB e sparire al
    checkpoint successivo)."""
    if not db.is_file():
        return 0
    # Connessione normale, non `mode=ro`: su un DB in WAL una connessione di
    # sola lettura pretende che il `-shm` esista già, e all'avvio può non esserci.
    con = sqlite3.connect(str(db))
    try:
        page_count = con.execute("PRAGMA page_count").fetchone()[0]
        page_size = con.execute("PRAGMA page_size").fetchone()[0]
        freelist = con.execute("PRAGMA freelist_count").fetchone()[0]
    finally:
        con.close()
    return max(page_count - freelist, 0) * page_size


def _byte_cartella(cartella: Path) -> int:
    if not cartella.is_dir():
        return 0
    return sum(f.stat().st_size for f in cartella.rglob("*") if f.is_file())


def _byte_file(f: Path) -> int:
    return f.stat().st_size if f.is_file() else 0


def contenuto() -> list[Voce]:
    """Le quattro voci del backup. Se se ne aggiunge una, va aggiunta anche a
    `applica_se_in_attesa`: sono le due sole liste e devono coincidere."""
    db, covers, env, slskd = _db_path(), _covers_dir(), _env_path(), _slskd_yml()
    return [
        Voce("database", str(db), _byte_db(db), db.is_file()),
        Voce("covers", str(covers), _byte_cartella(covers), covers.is_dir()),
        Voce("env", str(env), _byte_file(env), env.is_file()),
        Voce("slskd", str(slskd), _byte_file(slskd), slskd.is_file()),
    ]


def stima_byte() -> int:
    return sum(v.byte for v in contenuto())


def nome_di_default() -> str:
    return datetime.now().strftime("cratory-backup-%Y%m%d-%H%M.zip")
```

- [ ] **Step 4: verde sui primi quattro test**

Run: `python -m pytest tests/test_backup.py -q`
Expected: 4 PASS.

- [ ] **Step 5: test di `crea` (fallisce)**

Aggiungere a `tests/test_backup.py`:

```python
def test_crea_include_i_membri_attesi_e_nessun_escluso(dati, tmp_path):
    esito = backup.crea(tmp_path / "b.zip")
    assert Path(esito.percorso) == tmp_path / "b.zip"
    assert esito.byte == (tmp_path / "b.zip").stat().st_size
    membri = _membri(tmp_path / "b.zip")
    assert membri == {"manifest.json", "data/djassistant.db", "data/covers/playlist-1.jpg",
                      ".env", "data/slskd.yml"}
    with zipfile.ZipFile(tmp_path / "b.zip") as z:
        manifest = json.loads(z.read("manifest.json"))
    assert manifest["formato"] == 1
    assert manifest["creato_il"] == esito.creato_il
    assert {m["nome"] for m in manifest["membri"]} == membri - {"manifest.json"}
    assert isinstance(manifest["app_version"], str)


def test_crea_aggiunge_zip_se_manca(dati, tmp_path):
    esito = backup.crea(tmp_path / "senza-estensione")
    assert esito.percorso.endswith("senza-estensione.zip")


def test_crea_salta_le_voci_assenti(dati, tmp_path):
    (dati / ".env").unlink()
    shutil.rmtree(dati / "data" / "covers")
    membri = _membri(Path(backup.crea(tmp_path / "b.zip").percorso))
    assert membri == {"manifest.json", "data/djassistant.db", "data/slskd.yml"}


def test_lo_snapshot_e_coerente_con_una_connessione_aperta(dati, tmp_path):
    db = backup._db_path()
    viva = sqlite3.connect(db, isolation_level=None)
    viva.execute("INSERT INTO app_state(key, value) VALUES ('prima', 'si')")
    esito = backup.crea(tmp_path / "b.zip")
    viva.close()
    with zipfile.ZipFile(esito.percorso) as z:
        z.extract("data/djassistant.db", tmp_path / "estratto")
    with sqlite3.connect(tmp_path / "estratto" / "data" / "djassistant.db") as c:
        assert c.execute("SELECT value FROM app_state WHERE key='prima'").fetchone() == ("si",)
        assert c.execute("PRAGMA integrity_check").fetchone() == ("ok",)


def test_un_errore_non_lascia_ne_zip_ne_parziale(dati, tmp_path, monkeypatch):
    class Rotto:
        def __init__(self, *a, **k):
            raise OSError("disco pieno")

    monkeypatch.setattr(backup.zipfile, "ZipFile", Rotto)
    with pytest.raises(OSError):
        backup.crea(tmp_path / "b.zip")
    assert list(tmp_path.iterdir()) == []


def test_due_backup_insieme_il_secondo_e_rifiutato(dati, tmp_path):
    assert backup._lock.acquire(blocking=False)
    try:
        with pytest.raises(backup.BackupInCorso):
            backup.crea(tmp_path / "b.zip")
    finally:
        backup._lock.release()
```

- [ ] **Step 6: rosso, poi `crea`**

Aggiungere al modulo, dopo `nome_di_default`:

```python
# --- creazione ------------------------------------------------------------------

def _snapshot_db(sorgente: Path, destinazione: Path) -> None:
    """`VACUUM INTO`: snapshot transazionale, va bene con il WAL aperto e altri
    worker che scrivono. Connessione in autocommit: VACUUM non gira dentro una
    transazione."""
    con = sqlite3.connect(str(sorgente), isolation_level=None)
    try:
        con.execute("VACUUM INTO ?", (str(destinazione),))
    finally:
        con.close()


def crea(destinazione: Path) -> EsitoBackup:
    """Scrive lo zip in `destinazione` (`.zip` aggiunto se manca). Si scrive un
    parziale accanto e si rinomina alla fine: un backup interrotto non lascia
    mai uno zip a metà col nome buono."""
    if not _lock.acquire(blocking=False):
        raise BackupInCorso
    try:
        from app.core.version import app_version  # dentro: vedi docstring del modulo

        destinazione = Path(destinazione)
        if destinazione.suffix.lower() != ".zip":
            destinazione = destinazione.with_name(destinazione.name + ".zip")
        destinazione.parent.mkdir(parents=True, exist_ok=True)
        parziale = destinazione.with_name(destinazione.name + ".parziale")
        snapshot = destinazione.with_name(destinazione.name + ".db-snapshot")
        creato_il = _adesso()
        membri: list[dict] = []
        try:
            _snapshot_db(_db_path(), snapshot)
            with zipfile.ZipFile(parziale, "w", compression=zipfile.ZIP_DEFLATED) as z:
                z.write(snapshot, MEMBRO_DB)
                membri.append({"nome": MEMBRO_DB, "byte": snapshot.stat().st_size})
                covers = _covers_dir()
                if covers.is_dir():
                    for f in sorted(covers.iterdir()):
                        if f.is_file():
                            z.write(f, PREFISSO_COVERS + f.name)
                            membri.append({"nome": PREFISSO_COVERS + f.name, "byte": f.stat().st_size})
                for sorgente, nome in ((_env_path(), MEMBRO_ENV), (_slskd_yml(), MEMBRO_SLSKD)):
                    if sorgente.is_file():
                        z.write(sorgente, nome)
                        membri.append({"nome": nome, "byte": sorgente.stat().st_size})
                z.writestr(MEMBRO_MANIFEST, json.dumps({
                    "formato": FORMATO,
                    "app_version": app_version(),
                    "creato_il": creato_il,
                    "membri": membri,
                }, indent=2))
            parziale.replace(destinazione)
        except BaseException:
            parziale.unlink(missing_ok=True)
            raise
        finally:
            snapshot.unlink(missing_ok=True)
        return EsitoBackup(str(destinazione), destinazione.stat().st_size, creato_il)
    finally:
        _lock.release()
```

Nota: `VACUUM INTO ?` con parametro legato funziona (il nome file è un'espressione). Se la sqlite in uso lo rifiutasse (`OperationalError: near "?"`), usare `con.execute(f"VACUUM INTO '{str(destinazione).replace(chr(39), chr(39) * 2)}'")`.

- [ ] **Step 7: verde e commit**

Run: `python -m pytest tests/test_backup.py -q`
Expected: 10 PASS.

```bash
git add backend/app/services/backup.py backend/tests/test_backup.py
git commit -m "feat(backup): il servizio — contenuto, stima sulle pagine usate, zip con snapshot VACUUM INTO"
```

---

### Task 3: ispezione dell'archivio

**Files:**
- Modify: `backend/app/services/backup.py`
- Modify: `docs/superpowers/specs/2026-09-13-backup-ripristino-design.md` (una riga, vedi Step 3)
- Test: `backend/tests/test_backup.py`

**Interfaces:**
- Produces: `Riepilogo(creato_il: str | None, app_version: str | None, tracce: int, playlist: int, membri: list[str], ha_credenziali: bool)`; `ispeziona(archivio: Path) -> Riepilogo`, solleva `BackupNonValido(codice)`.

- [ ] **Step 1: test (fallisce)**

```python
def _zip_con(tmp_path, nome="x.zip", *, manifest=..., db: bytes | Path | None = ..., extra=()):
    """Costruisce uno zip di prova a partire da un backup vero e lo altera."""
    vero = Path(backup.crea(tmp_path / "vero.zip").percorso)
    out = tmp_path / nome
    with zipfile.ZipFile(vero) as src, zipfile.ZipFile(out, "w") as dst:
        for m in src.namelist():
            if m == "manifest.json":
                if manifest is None:
                    continue
                dst.writestr(m, src.read(m) if manifest is ... else json.dumps(manifest))
            elif m == "data/djassistant.db":
                if db is None:
                    continue
                dst.writestr(m, src.read(m) if db is ... else (db if isinstance(db, bytes) else db.read_bytes()))
            else:
                dst.writestr(m, src.read(m))
        for nome_extra, contenuto in extra:
            dst.writestr(nome_extra, contenuto)
    return out


def test_ispeziona_un_backup_vero(dati, tmp_path):
    with sqlite3.connect(backup._db_path()) as c:
        c.execute("INSERT INTO playlists(name, platform, source_type) VALUES ('p', 'manual', 'manual')")
    esito = backup.crea(tmp_path / "b.zip")
    r = backup.ispeziona(Path(esito.percorso))
    assert r.creato_il == esito.creato_il
    assert r.playlist == 1 and r.tracce == 0
    assert r.ha_credenziali is True
    assert "data/djassistant.db" in r.membri


def test_ispeziona_senza_credenziali(dati, tmp_path):
    (dati / ".env").unlink()
    (dati / "data" / "slskd.yml").unlink()
    r = backup.ispeziona(Path(backup.crea(tmp_path / "b.zip").percorso))
    assert r.ha_credenziali is False


@pytest.mark.parametrize("caso, codice", [
    ("non_zip", "archivio_non_valido"),
    ("senza_manifest", "manifest_assente"),
    ("formato_2", "manifest_assente"),
    ("senza_db", "db_assente"),
    ("db_troncato", "db_corrotto"),
])
def test_ispeziona_rifiuta_con_il_codice_giusto(dati, tmp_path, caso, codice):
    if caso == "non_zip":
        archivio = tmp_path / "x.zip"
        archivio.write_bytes(b"non sono uno zip")
    elif caso == "senza_manifest":
        archivio = _zip_con(tmp_path, manifest=None)
    elif caso == "formato_2":
        archivio = _zip_con(tmp_path, manifest={"formato": 2, "app_version": "1.0.0"})
    elif caso == "senza_db":
        archivio = _zip_con(tmp_path, db=None)
    else:
        archivio = _zip_con(tmp_path, db=b"SQLite format 3\x00" + b"\x00" * 100)
    with pytest.raises(backup.BackupNonValido) as e:
        backup.ispeziona(archivio)
    assert e.value.codice == codice


def test_ispeziona_rifiuta_una_versione_piu_recente(dati, tmp_path, monkeypatch):
    from app.core import version
    monkeypatch.setattr(version, "app_version", lambda: "1.0.8")
    archivio = _zip_con(tmp_path, manifest={"formato": 1, "app_version": "1.1.0", "creato_il": "x", "membri": []})
    with pytest.raises(backup.BackupNonValido) as e:
        backup.ispeziona(archivio)
    assert e.value.codice == "versione_piu_recente"


def test_ispeziona_accetta_una_versione_piu_vecchia_o_uguale(dati, tmp_path, monkeypatch):
    from app.core import version
    monkeypatch.setattr(version, "app_version", lambda: "1.0.8")
    for v in ("1.0.8", "0.9.0"):
        archivio = _zip_con(tmp_path, nome=f"{v}.zip", manifest={"formato": 1, "app_version": v, "creato_il": "x", "membri": []})
        assert backup.ispeziona(archivio).app_version == v


def test_in_sviluppo_la_versione_non_si_controlla(dati, tmp_path, monkeypatch):
    """`0.0.0-dev` batterebbe qualunque backup fatto da un'app vera: in un
    checkout senza VERSION il controllo si salta."""
    from app.core import version
    monkeypatch.setattr(version, "app_version", lambda: version.FALLBACK)
    archivio = _zip_con(tmp_path, manifest={"formato": 1, "app_version": "9.9.9", "creato_il": "x", "membri": []})
    assert backup.ispeziona(archivio).app_version == "9.9.9"
```

- [ ] **Step 2: rosso, poi `ispeziona`**

Aggiungere al modulo (dopo la dataclass `EsitoBackup`):

```python
@dataclass
class Riepilogo:
    creato_il: str | None
    app_version: str | None
    tracce: int
    playlist: int
    membri: list[str]
    ha_credenziali: bool
```

e dopo `crea`:

```python
# --- ispezione ------------------------------------------------------------------

def _membro_ammesso(nome: str) -> bool:
    """Solo nomi noti, e per le cover solo un nome di file piatto: uno zip
    scritto da altri non deve poter estrarre fuori dallo staging."""
    if nome in (MEMBRO_MANIFEST, MEMBRO_DB, MEMBRO_ENV, MEMBRO_SLSKD):
        return True
    if nome.startswith(PREFISSO_COVERS):
        resto = nome[len(PREFISSO_COVERS):]
        return bool(resto) and "/" not in resto and resto not in (".", "..")
    return False


def _piu_recente_dell_app(versione_backup: str | None) -> bool:
    from app.core import version  # dentro: vedi docstring del modulo
    in_esecuzione = version.app_version()
    if in_esecuzione == version.FALLBACK:
        return False  # checkout di sviluppo: nessun numero con cui confrontare
    mia = version.parse_version(in_esecuzione)
    sua = version.parse_version(versione_backup or "")
    if mia is None or sua is None:
        return False
    return sua > mia


def _conta(con: sqlite3.Connection, tabella: str) -> int:
    try:
        return int(con.execute(f"SELECT count(*) FROM {tabella}").fetchone()[0])
    except sqlite3.DatabaseError:
        return 0


def _verifica_db(percorso: Path) -> tuple[int, int]:
    """(tracce, playlist); `BackupNonValido("db_corrotto")` se non è un DB sano.
    Il file è una copia temporanea che nessun altro tocca: connessione normale."""
    try:
        con = sqlite3.connect(str(percorso))
    except sqlite3.DatabaseError as exc:
        raise BackupNonValido("db_corrotto", str(exc)) from exc
    try:
        try:
            esito = con.execute("PRAGMA integrity_check").fetchone()
        except sqlite3.DatabaseError as exc:
            raise BackupNonValido("db_corrotto", str(exc)) from exc
        if not esito or esito[0] != "ok":
            raise BackupNonValido("db_corrotto", str(esito))
        return _conta(con, "tracks"), _conta(con, "playlists")
    finally:
        con.close()


def _leggi_manifest(z: zipfile.ZipFile) -> dict:
    if MEMBRO_MANIFEST not in z.namelist():
        raise BackupNonValido("manifest_assente")
    try:
        manifest = json.loads(z.read(MEMBRO_MANIFEST))
    except ValueError as exc:
        raise BackupNonValido("manifest_assente", str(exc)) from exc
    if not isinstance(manifest, dict) or manifest.get("formato") != FORMATO:
        raise BackupNonValido("manifest_assente", f"formato {manifest.get('formato') if isinstance(manifest, dict) else '?'}")
    return manifest


def ispeziona(archivio: Path) -> Riepilogo:
    """Legge lo zip senza applicare nulla. Estrae il DB in una cartella
    temporanea per il controllo d'integrità e i contatori."""
    import tempfile

    archivio = Path(archivio)
    if not zipfile.is_zipfile(archivio):
        raise BackupNonValido("archivio_non_valido")
    with zipfile.ZipFile(archivio) as z:
        if z.testzip() is not None:
            raise BackupNonValido("archivio_non_valido", "membro corrotto")
        manifest = _leggi_manifest(z)
        membri = [m for m in z.namelist() if _membro_ammesso(m)]
        if MEMBRO_DB not in membri:
            raise BackupNonValido("db_assente")
        if _piu_recente_dell_app(manifest.get("app_version")):
            raise BackupNonValido("versione_piu_recente", str(manifest.get("app_version")))
        with tempfile.TemporaryDirectory(prefix="cratory-ispezione-") as tmp:
            estratto = Path(tmp) / "db.sqlite"
            with z.open(MEMBRO_DB) as src, estratto.open("wb") as dst:
                shutil.copyfileobj(src, dst)
            tracce, playlist = _verifica_db(estratto)
    return Riepilogo(
        creato_il=manifest.get("creato_il"),
        app_version=manifest.get("app_version"),
        tracce=tracce,
        playlist=playlist,
        membri=membri,
        ha_credenziali=MEMBRO_ENV in membri or MEMBRO_SLSKD in membri,
    )
```

- [ ] **Step 3: la riga nella spec**

Nella spec, nella tabella dei codici di §1 «Ispezione», alla riga `versione_piu_recente` aggiungere in coda: «Se l'app in esecuzione riporta la versione di ripiego `0.0.0-dev` (checkout senza `VERSION`), il controllo si salta: altrimenti in sviluppo ogni backup fatto da un'app vera verrebbe rifiutato.»

- [ ] **Step 4: verde e commit**

Run: `python -m pytest tests/test_backup.py -q`
Expected: PASS (il caso `db_troncato`: un file di 116 byte con l'intestazione sqlite fallisce in `integrity_check` o già in `connect`; entrambi danno `db_corrotto`).

```bash
git add backend/app/services/backup.py backend/tests/test_backup.py docs/superpowers/specs/2026-09-13-backup-ripristino-design.md
git commit -m "feat(backup): ispezione dell'archivio — manifest, integrità, contatori, versione"
```

---

### Task 4: il ripristino in due tempi e lo scambio a freddo

**Files:**
- Modify: `backend/app/services/backup.py`
- Test: `backend/tests/test_backup.py`

**Interfaces:**
- Produces:
  - `EsitoRipristino(stato: str, applicato_il: str, motivo: str | None = None, backup_creato_il: str | None = None, backup_app_version: str | None = None, tracce: int | None = None, playlist: int | None = None)`
  - `job_in_corso(db: Session) -> str | None` (`"analysis" | "import" | "shazam" | "downloads"`)
  - `prepara(archivio: Path, db: Session) -> Riepilogo` (solleva `BackupNonValido`, `JobInCorso`, `FileNotFoundError`)
  - `conferma(db: Session) -> None` (solleva `JobInCorso`, `NienteDaRipristinare`)
  - `annulla() -> None`
  - `applica_se_in_attesa() -> EsitoRipristino | None`
  - `riepilogo_in_attesa() -> Riepilogo | None` (lo staging preparato, se c'è)

- [ ] **Step 1: test (fallisce)**

```python
from sqlalchemy.orm import sessionmaker


@pytest.fixture()
def sessione(dati):
    engine = create_engine(f"sqlite:///{backup._db_path()}", connect_args={"check_same_thread": False})
    s = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        yield s
    finally:
        s.close()
        engine.dispose()


def test_prepara_popola_lo_staging_senza_marker(dati, tmp_path, sessione):
    archivio = Path(backup.crea(tmp_path / "b.zip").percorso)
    r = backup.prepara(archivio, sessione)
    staging = dati / "data" / "restore-staging"
    assert (staging / "data" / "djassistant.db").is_file()
    assert (staging / "data" / "covers" / "playlist-1.jpg").is_file()
    assert (staging / ".env").is_file() and (staging / "data" / "slskd.yml").is_file()
    assert json.loads((staging / "riepilogo.json").read_text())["playlist"] == r.playlist
    assert not (dati / "data" / "restore-pending.json").exists()
    assert backup.riepilogo_in_attesa().creato_il == r.creato_il


def test_prepara_ignora_membri_non_ammessi(dati, tmp_path, sessione):
    archivio = _zip_con(tmp_path, extra=[("../fuori.txt", b"no"), ("data/covers/../../x", b"no")])
    backup.prepara(archivio, sessione)
    assert not (tmp_path / "fuori.txt").exists()
    assert not (dati / "x").exists()


def test_prepara_file_inesistente(dati, sessione, tmp_path):
    with pytest.raises(FileNotFoundError):
        backup.prepara(tmp_path / "manca.zip", sessione)


def test_conferma_scrive_il_marker_con_db_path_e_riepilogo(dati, tmp_path, sessione):
    archivio = Path(backup.crea(tmp_path / "b.zip").percorso)
    backup.prepara(archivio, sessione)
    backup.conferma(sessione)
    marker = json.loads((dati / "data" / "restore-pending.json").read_text())
    assert marker["db_path"] == str(backup._db_path())
    assert marker["staging"] == str(dati / "data" / "restore-staging")
    assert marker["riepilogo"]["tracce"] == 0


def test_conferma_senza_staging_solleva(dati, sessione):
    with pytest.raises(backup.NienteDaRipristinare):
        backup.conferma(sessione)


def test_annulla_pulisce_tutto_ed_e_idempotente(dati, tmp_path, sessione):
    backup.prepara(Path(backup.crea(tmp_path / "b.zip").percorso), sessione)
    backup.conferma(sessione)
    backup.annulla()
    backup.annulla()
    assert not (dati / "data" / "restore-staging").exists()
    assert not (dati / "data" / "restore-pending.json").exists()
    assert backup.riepilogo_in_attesa() is None


@pytest.mark.parametrize("modulo, attr, atteso", [
    ("app.services.audio_analysis_job", "is_running", "analysis"),
    ("app.services.streaming_import_job", "is_running", "import"),
    ("app.services.mix_identify_job", "is_running", "shazam"),
])
def test_prepara_rifiuta_con_un_job_in_corso(dati, tmp_path, sessione, monkeypatch, modulo, attr, atteso):
    import importlib
    monkeypatch.setattr(importlib.import_module(modulo), attr, lambda: True)
    archivio = Path(backup.crea(tmp_path / "b.zip").percorso)
    with pytest.raises(backup.JobInCorso) as e:
        backup.prepara(archivio, sessione)
    assert e.value.job == atteso
    assert not (dati / "data" / "restore-staging").exists()


def test_prepara_rifiuta_con_un_download_in_corso(dati, tmp_path, sessione):
    from app.models import DownloadQueueItem, Track
    t = Track(platform="spotify", platform_track_id="x", source_type="spotify", title="t", artist="a")
    sessione.add(t)
    sessione.flush()
    sessione.add(DownloadQueueItem(track_id=t.id, kind="soulseek_auto", state="running"))
    sessione.commit()
    with pytest.raises(backup.JobInCorso) as e:
        backup.prepara(Path(backup.crea(tmp_path / "b.zip").percorso), sessione)
    assert e.value.job == "downloads"


def test_un_download_in_coda_ma_non_in_corso_non_blocca(dati, tmp_path, sessione):
    from app.models import DownloadQueueItem, Track
    t = Track(platform="spotify", platform_track_id="x", source_type="spotify", title="t", artist="a")
    sessione.add(t)
    sessione.flush()
    sessione.add(DownloadQueueItem(track_id=t.id, kind="soulseek_auto", state="queued"))
    sessione.commit()
    backup.prepara(Path(backup.crea(tmp_path / "b.zip").percorso), sessione)


def _sha(p: Path) -> str:
    import hashlib
    return hashlib.sha256(p.read_bytes()).hexdigest()


def test_applica_senza_marker_non_tocca_niente(dati):
    prima = _sha(backup._db_path())
    assert backup.applica_se_in_attesa() is None
    assert _sha(backup._db_path()) == prima


def test_applica_scambia_i_file_e_conserva_pre_restore(dati, tmp_path, sessione):
    # Il backup contiene 'nel_backup'; il DB attuale, dopo, conterrà 'dopo'.
    with sqlite3.connect(backup._db_path()) as c:
        c.execute("INSERT INTO app_state(key, value) VALUES ('nel_backup', '1')")
    archivio = Path(backup.crea(tmp_path / "b.zip").percorso)
    with sqlite3.connect(backup._db_path()) as c:
        c.execute("DELETE FROM app_state WHERE key='nel_backup'")
        c.execute("INSERT INTO app_state(key, value) VALUES ('dopo', '1')")
    (dati / ".env").write_text("CAMBIATO=1\n")
    backup.prepara(archivio, sessione)
    backup.conferma(sessione)
    sessione.close()

    esito = backup.applica_se_in_attesa()

    assert esito.stato == "ok" and esito.tracce == 0
    with sqlite3.connect(backup._db_path()) as c:
        chiavi = {r[0] for r in c.execute("SELECT key FROM app_state")}
    assert "nel_backup" in chiavi and "dopo" not in chiavi
    assert (dati / ".env").read_text() == "SPOTIFY_CLIENT_ID=abc\n"
    pre = dati / "data" / "pre-restore"
    assert (pre / "djassistant.db").is_file()
    assert (pre / ".env").read_text() == "CAMBIATO=1\n"
    assert (pre / "covers" / "playlist-1.jpg").is_file()
    assert not (dati / "data" / "restore-pending.json").exists()
    assert not (dati / "data" / "restore-staging").exists()
    assert not (backup._db_path().parent / "djassistant.db-wal").exists()


def test_applica_con_staging_mancante_toglie_il_marker_e_non_tocca_i_dati(dati):
    prima = _sha(backup._db_path())
    (dati / "data" / "restore-pending.json").write_text(json.dumps({
        "staging": str(dati / "data" / "restore-staging"),
        "db_path": str(backup._db_path()),
        "riepilogo": {},
    }))
    esito = backup.applica_se_in_attesa()
    assert esito.stato == "fallito" and esito.motivo == "staging_incompleto"
    assert _sha(backup._db_path()) == prima
    assert not (dati / "data" / "restore-pending.json").exists()


def test_applica_con_marker_illeggibile_lo_toglie(dati):
    (dati / "data" / "restore-pending.json").write_text("{non json")
    esito = backup.applica_se_in_attesa()
    assert esito.stato == "fallito"
    assert not (dati / "data" / "restore-pending.json").exists()
```

- [ ] **Step 2: rosso, poi implementare**

Aggiungere la dataclass dopo `Riepilogo`:

```python
@dataclass
class EsitoRipristino:
    stato: str  # "ok" | "fallito"
    applicato_il: str
    motivo: str | None = None
    backup_creato_il: str | None = None
    backup_app_version: str | None = None
    tracce: int | None = None
    playlist: int | None = None
```

e in fondo al modulo:

```python
# --- ripristino: i due tempi --------------------------------------------------

def job_in_corso(db) -> str | None:
    """Il riavvio interromperebbe questi: l'utente deve saperlo prima di
    scegliere. Import dentro la funzione: portano a `config`."""
    from app.models import DownloadQueueItem
    from app.services import audio_analysis_job, mix_identify_job, streaming_import_job

    if audio_analysis_job.is_running():
        return "analysis"
    if streaming_import_job.is_running():
        return "import"
    if mix_identify_job.is_running():
        return "shazam"
    if db.query(DownloadQueueItem).filter(DownloadQueueItem.state == "running").first():
        return "downloads"
    return None


def _riepilogo_path() -> Path:
    return _staging() / "riepilogo.json"


def riepilogo_in_attesa() -> Riepilogo | None:
    try:
        return Riepilogo(**json.loads(_riepilogo_path().read_text()))
    except (OSError, ValueError, TypeError):
        return None


def prepara(archivio: Path, db) -> Riepilogo:
    archivio = Path(archivio)
    if not archivio.is_file():
        raise FileNotFoundError(str(archivio))
    job = job_in_corso(db)
    if job:
        raise JobInCorso(job)
    riepilogo = ispeziona(archivio)
    staging = _staging()
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    with zipfile.ZipFile(archivio) as z:
        for nome in riepilogo.membri:
            destinazione = staging / nome
            destinazione.parent.mkdir(parents=True, exist_ok=True)
            with z.open(nome) as src, destinazione.open("wb") as dst:
                shutil.copyfileobj(src, dst)
    _riepilogo_path().write_text(json.dumps(asdict(riepilogo)))
    return riepilogo


def conferma(db) -> None:
    job = job_in_corso(db)
    if job:
        raise JobInCorso(job)
    riepilogo = riepilogo_in_attesa()
    if riepilogo is None or not (_staging() / MEMBRO_DB).is_file():
        raise NienteDaRipristinare
    _marker().write_text(json.dumps({
        "staging": str(_staging()),
        # Il percorso del DB si fissa ADESSO, a config caricata: chi applica
        # gira prima di load_dotenv e non deve dedurlo.
        "db_path": str(_db_path()),
        "confermato_il": _adesso(),
        "riepilogo": asdict(riepilogo),
    }))


def annulla() -> None:
    _marker().unlink(missing_ok=True)
    shutil.rmtree(_staging(), ignore_errors=True)


# --- ripristino: lo scambio, a freddo -------------------------------------------

def _sposta(sorgente: Path, destinazione: Path) -> None:
    if sorgente.exists():
        destinazione.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(sorgente), str(destinazione))


def applica_se_in_attesa() -> EsitoRipristino | None:
    """Da chiamare all'avvio PRIMA che chiunque apra il DB. Senza marker non
    tocca niente. Con staging mancante o incompleto toglie il marker e lascia i
    dati com'erano: meglio ripartire con i vecchi che con metà dei nuovi."""
    marker = _marker()
    if not marker.exists():
        return None
    try:
        dati = json.loads(marker.read_text())
        if not isinstance(dati, dict):
            dati = {}
    except (OSError, ValueError):
        dati = {}
    marker.unlink(missing_ok=True)

    staging = Path(dati.get("staging") or _staging())
    db_dest = Path(dati.get("db_path") or "")
    riepilogo = dati.get("riepilogo") or {}
    if not db_dest.is_absolute() or not (staging / MEMBRO_DB).is_file():
        log.warning("ripristino: staging incompleto in %s, marker rimosso, dati intatti", staging)
        shutil.rmtree(staging, ignore_errors=True)
        return EsitoRipristino(stato="fallito", applicato_il=_adesso(), motivo="staging_incompleto")

    pre = _pre_restore()
    shutil.rmtree(pre, ignore_errors=True)
    pre.mkdir(parents=True)
    for suffisso in ("", "-wal", "-shm"):
        _sposta(db_dest.with_name(db_dest.name + suffisso), pre / (db_dest.name + suffisso))
    _sposta(_covers_dir(), pre / "covers")
    _sposta(_env_path(), pre / ".env")
    _sposta(_slskd_yml(), pre / "slskd.yml")

    _sposta(staging / MEMBRO_DB, db_dest)
    covers_dst = _covers_dir()
    covers_dst.mkdir(parents=True, exist_ok=True)
    covers_src = staging / PREFISSO_COVERS.rstrip("/")
    if covers_src.is_dir():
        for f in covers_src.iterdir():
            _sposta(f, covers_dst / f.name)
    _sposta(staging / MEMBRO_ENV, _env_path())
    _sposta(staging / MEMBRO_SLSKD, _slskd_yml())
    shutil.rmtree(staging, ignore_errors=True)

    log.warning("ripristino applicato dal backup del %s (v%s)", riepilogo.get("creato_il"), riepilogo.get("app_version"))
    return EsitoRipristino(
        stato="ok",
        applicato_il=_adesso(),
        backup_creato_il=riepilogo.get("creato_il"),
        backup_app_version=riepilogo.get("app_version"),
        tracce=riepilogo.get("tracce"),
        playlist=riepilogo.get("playlist"),
    )
```

- [ ] **Step 3: verde e commit**

Run: `python -m pytest tests/test_backup.py -q`
Expected: PASS. Se `test_applica_scambia_i_file…` fallisce sul `-wal` residuo: la `sessione` chiusa nel test rilascia la connessione ma l'engine va `dispose()`-ato prima dell'apply — la fixture lo fa nel teardown, quindi nel test chiamare `sessione.get_bind().dispose()` subito dopo `sessione.close()`.

```bash
git add backend/app/services/backup.py backend/tests/test_backup.py
git commit -m "feat(backup): il ripristino in due tempi — staging, marker, scambio a freddo con pre-restore"
```

---

### Task 5: router `/api/backup`, l'anello in `main.py`, il test di invarianza

**Files:**
- Create: `backend/app/routers/backup.py`
- Modify: `backend/app/main.py:1-16` e il `lifespan` (righe 70-100)
- Modify: `backend/tests/test_niente_scritture_nel_checkout.py` (`_ESERCITA_LE_SCRITTURE` e il secondo test)
- Test: `backend/tests/test_backup_router.py`

**Interfaces:**
- Consumes: tutto il Task 2-4.
- Produces: gli endpoint della tabella in spec §3; il payload di `GET /api/backup/estimate` è `{byte, voci: [{nome, byte, presente}], last_backup_at, nome_di_default, picker_disponibile}`; `POST /api/backup` → `{percorso, byte, creato_il}`; `prepare` → il `Riepilogo` come JSON; `confirm` → `{riavvio_necessario: true}`; `restore/last` → `EsitoRipristino` o `null`.

- [ ] **Step 1: test del router (fallisce)**

Creare `backend/tests/test_backup_router.py`:

```python
"""Router /api/backup: il servizio è monkeypatchato, tranne dove si vuole il
percorso vero di ripiego (~/Downloads)."""
import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.db import get_db
from app.main import app
from app.services import backup

client = TestClient(app)


def test_estimate(monkeypatch, db):
    app.dependency_overrides[get_db] = lambda: db
    try:
        monkeypatch.setattr(backup, "contenuto", lambda: [backup.Voce("database", "/x", 10, True), backup.Voce("env", "/e", 0, False)])
        monkeypatch.setattr(backup, "nome_di_default", lambda: "cratory-backup-x.zip")
        from app.services import native_picker
        monkeypatch.setattr(native_picker, "picker_available", lambda: False)
        r = client.get("/api/backup/estimate")
        assert r.status_code == 200
        assert r.json() == {
            "byte": 10,
            "voci": [{"nome": "database", "byte": 10, "presente": True}, {"nome": "env", "byte": 0, "presente": False}],
            "last_backup_at": None,
            "nome_di_default": "cratory-backup-x.zip",
            "picker_disponibile": False,
        }
    finally:
        app.dependency_overrides.clear()


def test_backup_con_path_scrive_li_e_segna_last_backup_at(monkeypatch, db, tmp_path):
    app.dependency_overrides[get_db] = lambda: db
    try:
        visto = {}

        def finto_crea(destinazione):
            visto["dest"] = Path(destinazione)
            return backup.EsitoBackup(str(destinazione), 123, "2026-09-13T16:40:00+00:00")

        monkeypatch.setattr(backup, "crea", finto_crea)
        r = client.post("/api/backup", json={"path": str(tmp_path / "b.zip")})
        assert r.status_code == 200
        assert r.json() == {"percorso": str(tmp_path / "b.zip"), "byte": 123, "creato_il": "2026-09-13T16:40:00+00:00"}
        assert visto["dest"] == tmp_path / "b.zip"
        from app.services.app_state import get_state
        assert get_state(db, "last_backup_at") == "2026-09-13T16:40:00+00:00"
    finally:
        app.dependency_overrides.clear()


def test_backup_senza_path_va_in_downloads(monkeypatch, db, tmp_path):
    app.dependency_overrides[get_db] = lambda: db
    try:
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setattr(backup, "nome_di_default", lambda: "cratory-backup-x.zip")
        monkeypatch.setattr(backup, "crea", lambda d: backup.EsitoBackup(str(d), 1, "x"))
        r = client.post("/api/backup", json={"path": None})
        assert r.json()["percorso"] == str(tmp_path / "Downloads" / "cratory-backup-x.zip")
    finally:
        app.dependency_overrides.clear()


def test_backup_in_corso_409(monkeypatch, db):
    app.dependency_overrides[get_db] = lambda: db
    try:
        def occupato(d):
            raise backup.BackupInCorso
        monkeypatch.setattr(backup, "crea", occupato)
        r = client.post("/api/backup", json={"path": "/tmp/x.zip"})
        assert r.status_code == 409 and r.json()["detail"]["code"] == "backup_in_corso"
    finally:
        app.dependency_overrides.clear()


def test_prepare_risponde_il_riepilogo(monkeypatch, db):
    app.dependency_overrides[get_db] = lambda: db
    try:
        r_ok = backup.Riepilogo("2026-09-01T00:00:00+00:00", "1.0.7", 3412, 58, ["data/djassistant.db", ".env"], True)
        monkeypatch.setattr(backup, "prepara", lambda archivio, db: r_ok)
        r = client.post("/api/backup/restore/prepare", json={"path": "/x/b.zip"})
        assert r.status_code == 200
        assert r.json()["tracce"] == 3412 and r.json()["ha_credenziali"] is True
    finally:
        app.dependency_overrides.clear()


def test_prepare_mappa_gli_errori(monkeypatch, db):
    app.dependency_overrides[get_db] = lambda: db
    try:
        def non_valido(archivio, db):
            raise backup.BackupNonValido("db_corrotto", "integrity")
        monkeypatch.setattr(backup, "prepara", non_valido)
        r = client.post("/api/backup/restore/prepare", json={"path": "/x/b.zip"})
        assert r.status_code == 400 and r.json()["detail"]["code"] == "db_corrotto"

        def job(archivio, db):
            raise backup.JobInCorso("analysis")
        monkeypatch.setattr(backup, "prepara", job)
        r = client.post("/api/backup/restore/prepare", json={"path": "/x/b.zip"})
        assert r.status_code == 409
        assert r.json()["detail"] == {"code": "job_in_corso", "message": "A job is running: analysis", "params": {"job": "analysis"}}

        def manca(archivio, db):
            raise FileNotFoundError(archivio)
        monkeypatch.setattr(backup, "prepara", manca)
        r = client.post("/api/backup/restore/prepare", json={"path": "/x/b.zip"})
        assert r.status_code == 404 and r.json()["detail"]["code"] == "file_non_trovato"
    finally:
        app.dependency_overrides.clear()


def test_confirm_e_annulla(monkeypatch, db):
    app.dependency_overrides[get_db] = lambda: db
    try:
        chiamate = []
        monkeypatch.setattr(backup, "conferma", lambda db: chiamate.append("conferma"))
        monkeypatch.setattr(backup, "annulla", lambda: chiamate.append("annulla"))
        assert client.post("/api/backup/restore/confirm").json() == {"riavvio_necessario": True}
        assert client.delete("/api/backup/restore").status_code == 204
        assert chiamate == ["conferma", "annulla"]

        def niente(db):
            raise backup.NienteDaRipristinare
        monkeypatch.setattr(backup, "conferma", niente)
        r = client.post("/api/backup/restore/confirm")
        assert r.status_code == 409 and r.json()["detail"]["code"] == "niente_da_ripristinare"
    finally:
        app.dependency_overrides.clear()


def test_restore_last(db):
    app.dependency_overrides[get_db] = lambda: db
    try:
        assert client.get("/api/backup/restore/last").json() is None
        from app.services.app_state import set_state
        set_state(db, "last_restore", json.dumps({"stato": "ok", "applicato_il": "x", "tracce": 1}))
        assert client.get("/api/backup/restore/last").json()["tracce"] == 1
    finally:
        app.dependency_overrides.clear()
```

- [ ] **Step 2: rosso, poi il router**

Creare `backend/app/routers/backup.py`:

```python
"""HTTP per backup e ripristino. Solo trasporto: le regole stanno in
services/backup.py, qui si mappano le eccezioni a codici stabili."""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.http_errors import api_error
from app.db import get_db
from app.services import backup, native_picker
from app.services.app_state import get_state, set_state

router = APIRouter(prefix="/api/backup", tags=["backup"])


class VoceOut(BaseModel):
    nome: str
    byte: int
    presente: bool


class EstimateOut(BaseModel):
    byte: int
    voci: list[VoceOut]
    last_backup_at: str | None
    nome_di_default: str
    picker_disponibile: bool


class BackupIn(BaseModel):
    # Nullo = ripiego senza picker: ~/Downloads/<nome_di_default>.
    path: str | None = None


class BackupOut(BaseModel):
    percorso: str
    byte: int
    creato_il: str


class RestoreIn(BaseModel):
    path: str


class RiepilogoOut(BaseModel):
    creato_il: str | None
    app_version: str | None
    tracce: int
    playlist: int
    membri: list[str]
    ha_credenziali: bool


class ConfirmOut(BaseModel):
    riavvio_necessario: bool


@router.get("/estimate", response_model=EstimateOut)
def estimate(db: Session = Depends(get_db)):
    voci = backup.contenuto()
    return EstimateOut(
        byte=sum(v.byte for v in voci),
        voci=[VoceOut(nome=v.nome, byte=v.byte, presente=v.presente) for v in voci],
        last_backup_at=get_state(db, "last_backup_at"),
        nome_di_default=backup.nome_di_default(),
        picker_disponibile=native_picker.picker_available(),
    )


@router.post("", response_model=BackupOut)
def crea(body: BackupIn, db: Session = Depends(get_db)):
    destinazione = Path(body.path) if body.path else Path.home() / "Downloads" / backup.nome_di_default()
    try:
        esito = backup.crea(destinazione)
    except backup.BackupInCorso:
        raise api_error(409, "backup_in_corso", "A backup is already being written")
    set_state(db, "last_backup_at", esito.creato_il)
    return BackupOut(percorso=esito.percorso, byte=esito.byte, creato_il=esito.creato_il)


def _job_error(exc: backup.JobInCorso):
    return api_error(409, "job_in_corso", f"A job is running: {exc.job}", job=exc.job)


@router.post("/restore/prepare", response_model=RiepilogoOut)
def prepare(body: RestoreIn, db: Session = Depends(get_db)):
    try:
        r = backup.prepara(Path(body.path), db)
    except FileNotFoundError:
        raise api_error(404, "file_non_trovato", "Backup file not found")
    except backup.BackupNonValido as exc:
        raise api_error(400, exc.codice, f"Invalid backup: {exc.codice}", detail=exc.dettaglio)
    except backup.JobInCorso as exc:
        raise _job_error(exc)
    return RiepilogoOut(**r.__dict__)


@router.post("/restore/confirm", response_model=ConfirmOut)
def confirm(db: Session = Depends(get_db)):
    try:
        backup.conferma(db)
    except backup.NienteDaRipristinare:
        raise api_error(409, "niente_da_ripristinare", "No restore has been prepared")
    except backup.JobInCorso as exc:
        raise _job_error(exc)
    return ConfirmOut(riavvio_necessario=True)


@router.delete("/restore", status_code=204)
def annulla():
    backup.annulla()
    return Response(status_code=204)


@router.get("/restore/last")
def last(db: Session = Depends(get_db)) -> dict | None:
    raw = get_state(db, "last_restore")
    if not raw:
        return None
    try:
        return json.loads(raw)
    except ValueError:
        return None
```

- [ ] **Step 3: `main.py`**

In cima, sostituire il blocco `from app.core import paths` … `load_dotenv(...)` con:

```python
from app.core import paths
# Il ripristino confermato si applica QUI, prima di load_dotenv e prima che
# qualunque import costruisca Settings o apra il DB: uno .env ripristinato deve
# valere già in questo avvio, e i file si scambiano solo a DB chiuso.
# services/backup non importa config a livello di modulo proprio per questo.
from app.services import backup as _backup
_ESITO_RIPRISTINO = _backup.applica_se_in_attesa()
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

Aggiungere `backup` all'import dei router (`from app.routers import (ai, analysis, backup, discovery, …)`) e `app.include_router(backup.router)` dopo `app.include_router(setup.router)`.

Nel `lifespan`, subito dopo il blocco `runtime_settings.load(db)`:

```python
    # L'esito del ripristino applicato all'avvio (prima di load_dotenv, a DB
    # chiuso) si annota adesso che il DB è aperto: la pagina Impostazioni lo
    # legge da /api/backup/restore/last.
    if _ESITO_RIPRISTINO is not None:
        from dataclasses import asdict
        import json as _json
        from app.services.app_state import set_state
        with SessionLocal() as db:
            set_state(db, "last_restore", _json.dumps(asdict(_ESITO_RIPRISTINO)))
```

Verificare che `app.services.backup` non importi config a livello di modulo:

Run: `cd backend && source .venv/bin/activate && python -c "import sys; import app.services.backup; assert 'app.core.config' not in sys.modules, 'config importato troppo presto'; print('ok')"`
Expected: `ok`.

- [ ] **Step 4: verde sul router**

Run: `python -m pytest tests/test_backup_router.py tests/test_backup.py -q`
Expected: PASS.

- [ ] **Step 5: il test di invarianza esercita i punti di scrittura nuovi**

In `backend/tests/test_niente_scritture_nel_checkout.py`, dentro `_ESERCITA_LE_SCRITTURE`, prima di `print("fatto")`:

```python
# Backup e ripristino (spec 2026-09-13): tre punti di scrittura nuovi sotto
# DATA_DIR — il parziale dello zip accanto alla destinazione, lo staging e il
# marker. Lo zip stesso si scrive dove dice l'utente: qui in una cartella
# dentro DATA_DIR per non sporcare nient'altro.
from app.services import backup
_dest_backup = _dentro_data_dir(_DATA_DIR / "prova-backup" / "b.zip")
_esito = backup.crea(_dest_backup)
class _SessioneFinta:
    def query(self, *_a, **_k):
        return self
    def filter(self, *_a, **_k):
        return self
    def first(self):
        return None
backup.prepara(Path(_esito.percorso), _SessioneFinta())
backup.conferma(_SessioneFinta())
backup.annulla()
```

e nel secondo test aggiungere:

```python
    assert (tmp_path / "prova-backup" / "b.zip").is_file()
    assert not (tmp_path / "data" / "restore-staging").exists()
    assert not (tmp_path / "data" / "restore-pending.json").exists()
```

Run: `python -m pytest tests/test_niente_scritture_nel_checkout.py -q`
Expected: PASS (nessun server di sviluppo in ascolto su :8000 durante il test, vedi docstring del file).

- [ ] **Step 6: suite intera e commit**

Run: `python -m pytest tests -q -x`
Expected: PASS.

```bash
git add backend/app/routers/backup.py backend/app/main.py backend/tests/test_backup_router.py backend/tests/test_niente_scritture_nel_checkout.py
git commit -m "feat(backup): /api/backup, lo scambio applicato prima di load_dotenv, l'invarianza estesa"
```

---

### Task 6: client, dizionari e picker nel frontend

**Files:**
- Create: `frontend/lib/api/backup.ts`
- Modify: `frontend/lib/api.ts`, `frontend/lib/api/settings.ts:29-34`, `frontend/components/path-picker-button.tsx`
- Modify: `frontend/lib/i18n/it.ts` (dopo `versionErrSconosciuto`, riga 108), `frontend/lib/i18n/en.ts` (dopo la riga 120)
- Test: `frontend/tests/path-picker-button.test.tsx`

**Interfaces:**
- Produces:
  - `pickPath(kind: "folder" | "file" | "save", start?: string, prompt?: string, defaultName?: string)`
  - `PathPickerButton` prop `kind: "folder" | "file" | "save"`, `defaultName?: string`, `label?: ReactNode`
  - `getBackupEstimate(): Promise<BackupEstimate>`, `createBackup(path: string | null): Promise<BackupResult>`, `prepareRestore(path: string): Promise<RestoreSummary>`, `confirmRestore(): Promise<{riavvio_necessario: boolean}>`, `cancelRestore(): Promise<void>`, `lastRestore(): Promise<RestoreOutcome | null>`
  - chiavi `t.settings.backup*` e `t.settings.versionBackup*` (elenco sotto)

- [ ] **Step 1: test del picker (fallisce)**

In `frontend/tests/path-picker-button.test.tsx` aggiungere:

```tsx
  it("kind save passa il nome di default e usa l'etichetta data", async () => {
    pickPath.mockResolvedValue({ path: "/Users/x/Desktop/b.zip" });
    const onPick = vi.fn();
    render(<PathPickerButton kind="save" defaultName="b.zip" label="Backup ora…" onPick={onPick} onError={() => {}} />);
    await act(async () => {
      fireEvent.click(screen.getByText("Backup ora…"));
    });
    expect(pickPath).toHaveBeenCalledWith("save", undefined, undefined, "b.zip");
    expect(onPick).toHaveBeenCalledWith("/Users/x/Desktop/b.zip");
  });
```

Aggiornare anche l'asserzione del primo test: `expect(pickPath).toHaveBeenCalledWith("folder", "/Users/x", undefined, undefined);`.

- [ ] **Step 2: rosso, poi implementare**

`frontend/lib/api/settings.ts`:

```ts
/** Apre il dialog nativo sulla macchina del backend; path null = annullato.
 *  `save` = «salva con nome»: restituisce un percorso anche se il file non esiste. */
export function pickPath(kind: "folder" | "file" | "save", start?: string, prompt?: string, defaultName?: string) {
  return apiPost<{ path: string | null }>("/api/files/pick", {
    kind, start: start || null, prompt: prompt || null, default_name: defaultName || null,
  });
}
```

`frontend/components/path-picker-button.tsx`, firma e chiamata:

```tsx
export function PathPickerButton({ kind, start, prompt, defaultName, label, variant = "primary", onPick, onError }: {
  kind: "folder" | "file" | "save";
  start?: string;
  prompt?: string;
  defaultName?: string;
  /** Testo del pulsante; default «Sfoglia…». */
  label?: ReactNode;
  variant?: "primary" | "outline";
  onPick: (path: string) => void;
  onError: (message: string) => void;
}) {
  const t = useT();
  const [busy, setBusy] = useState(false);

  const open = async () => {
    setBusy(true);
    try {
      const r = await pickPath(kind, start, prompt, defaultName);
      if (r.path) onPick(r.path);
    } catch (e) {
      onError(errText(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Button type="button" size="sm" variant={variant} onClick={open} disabled={busy}>
      {busy ? <Spinner /> : (label ?? t.settings.browseButton)}
    </Button>
  );
}
```

(import `type ReactNode` da react.)

`frontend/lib/api/backup.ts`:

```ts
import { apiDelete, apiGet, apiPost } from "./client";

export type BackupVoce = { nome: string; byte: number; presente: boolean };
export type BackupEstimate = {
  byte: number;
  voci: BackupVoce[];
  last_backup_at: string | null;
  nome_di_default: string;
  picker_disponibile: boolean;
};
export type BackupResult = { percorso: string; byte: number; creato_il: string };
export type RestoreSummary = {
  creato_il: string | null;
  app_version: string | null;
  tracce: number;
  playlist: number;
  membri: string[];
  ha_credenziali: boolean;
};
export type RestoreOutcome = {
  stato: "ok" | "fallito";
  applicato_il: string;
  motivo?: string | null;
  backup_creato_il?: string | null;
  backup_app_version?: string | null;
  tracce?: number | null;
  playlist?: number | null;
};

export function getBackupEstimate() {
  return apiGet<BackupEstimate>("/api/backup/estimate");
}

/** `path` nullo = il backend salva in ~/Downloads col nome di default. */
export function createBackup(path: string | null) {
  return apiPost<BackupResult>("/api/backup", { path });
}

export function prepareRestore(path: string) {
  return apiPost<RestoreSummary>("/api/backup/restore/prepare", { path });
}

export function confirmRestore() {
  return apiPost<{ riavvio_necessario: boolean }>("/api/backup/restore/confirm");
}

export function cancelRestore() {
  return apiDelete<void>("/api/backup/restore");
}

export function lastRestore() {
  return apiGet<RestoreOutcome | null>("/api/backup/restore/last");
}
```

In `frontend/lib/api.ts` aggiungere `export * from "./api/backup";` dopo la riga di `./api/updates`.

- [ ] **Step 3: dizionari**

In `it.ts`, dentro `settings`, subito dopo `versionErrSconosciuto`:

```ts
    versionBackupQuestion: (mb: string) => `Vuoi fare prima un backup? Occuperebbe circa ${mb} MB.`,
    versionBackupAndInstall: "Backup e aggiorna",
    versionInstallWithoutBackup: "Aggiorna senza backup",
    versionBackupRunning: "Backup in corso…",
    versionBackupFailed: "Il backup non è riuscito: l'aggiornamento non è partito.",
    dataHeading: "Dati",
    backupLast: (when: string) => `Ultimo backup: ${when}`,
    backupNever: "Nessun backup finora",
    backupEstimate: (mb: string, parts: string) => `circa ${mb} MB · ${parts}`,
    backupPartDatabase: "database",
    backupPartCovers: (n: number) => (n === 1 ? "1 cover" : `${n} cover`),
    backupPartCredentials: "credenziali",
    backupNow: "Backup ora…",
    backupSavePrompt: "Salva il backup di Cratory",
    backupDone: (path: string, mb: string) => `Backup scritto in ${path} (${mb} MB).`,
    backupNote: "Il file contiene anche le credenziali: custodiscilo come il file .env.",
    restoreButton: "Ripristina da backup…",
    restorePickPrompt: "Scegli un backup di Cratory",
    restoreTitle: "Ripristinare questo backup?",
    restoreSummary: (when: string, version: string) => `Backup del ${when}, versione ${version}.`,
    restoreCounts: (tracks: number, playlists: number) => `${tracks} tracce, ${playlists} playlist.`,
    restoreHasCredentials: "Include le credenziali.",
    restoreNoCredentials: "Non include le credenziali: dopo il ripristino vanno reinserite.",
    restoreWarnKept: "I dati attuali vengono messi da parte, non cancellati.",
    restoreWarnQueue: "La coda download torna com'era nel backup.",
    restoreConfirm: "Ripristina e riavvia",
    restoreManualRestart: "Ripristino pronto. Riavvia il backend per completarlo.",
    restoreApplied: (applied: string, from: string) => `Ripristinato il ${applied} dal backup del ${from}.`,
    restoreFailedLast: "L'ultimo ripristino non è stato applicato: i dati sono rimasti com'erano.",
```

Sempre in `it.ts`, nella sezione `errors` (riga ~1863, chiavi = codici del backend, tradotte da `translateApiError`), aggiungere:

```ts
    archivio_non_valido: "Il file scelto non è un backup di Cratory.",
    manifest_assente: "Il backup non ha un manifesto leggibile.",
    db_assente: "Il backup non contiene il database.",
    db_corrotto: "Il database nel backup è danneggiato.",
    versione_piu_recente: "Il backup viene da una versione più recente di Cratory: aggiorna l'app, poi ripristina.",
    backup_in_corso: "Un altro backup è già in corso.",
    job_in_corso: (p: Record<string, unknown>) => {
      const nomi: Record<string, string> = {
        analysis: "analisi BPM/key", import: "import playlist", shazam: "identificazione mix", downloads: "download",
      };
      return `C'è un lavoro in corso (${nomi[String(p.job)] ?? String(p.job ?? "")}): aspetta che finisca o fermalo, poi riprova.`;
    },
    niente_da_ripristinare: "Non c'è nessun ripristino preparato.",
    file_non_trovato: "File non trovato.",
```

In `en.ts`, dentro `settings` nello stesso punto:

```ts
    versionBackupQuestion: (mb: string) => `Back up first? It would take about ${mb} MB.`,
    versionBackupAndInstall: "Back up and update",
    versionInstallWithoutBackup: "Update without backup",
    versionBackupRunning: "Backing up…",
    versionBackupFailed: "The backup failed: the update did not start.",
    dataHeading: "Data",
    backupLast: (when: string) => `Last backup: ${when}`,
    backupNever: "No backup yet",
    backupEstimate: (mb: string, parts: string) => `about ${mb} MB · ${parts}`,
    backupPartDatabase: "database",
    backupPartCovers: (n: number) => (n === 1 ? "1 cover" : `${n} covers`),
    backupPartCredentials: "credentials",
    backupNow: "Back up now…",
    backupSavePrompt: "Save the Cratory backup",
    backupDone: (path: string, mb: string) => `Backup written to ${path} (${mb} MB).`,
    backupNote: "The file also holds your credentials: keep it as you keep the .env file.",
    restoreButton: "Restore from backup…",
    restorePickPrompt: "Choose a Cratory backup",
    restoreTitle: "Restore this backup?",
    restoreSummary: (when: string, version: string) => `Backup from ${when}, version ${version}.`,
    restoreCounts: (tracks: number, playlists: number) => `${tracks} tracks, ${playlists} playlists.`,
    restoreHasCredentials: "Includes credentials.",
    restoreNoCredentials: "Does not include credentials: enter them again after restoring.",
    restoreWarnKept: "Your current data is set aside, not deleted.",
    restoreWarnQueue: "The download queue goes back to how it was in the backup.",
    restoreConfirm: "Restore and restart",
    restoreManualRestart: "Restore is ready. Restart the backend to complete it.",
    restoreApplied: (applied: string, from: string) => `Restored on ${applied} from the backup of ${from}.`,
    restoreFailedLast: "The last restore was not applied: your data stayed as it was.",
```

e nella sezione `errors` di `en.ts` (riga ~1882):

```ts
    archivio_non_valido: "The chosen file is not a Cratory backup.",
    manifest_assente: "The backup has no readable manifest.",
    db_assente: "The backup does not contain the database.",
    db_corrotto: "The database inside the backup is damaged.",
    versione_piu_recente: "The backup comes from a newer Cratory: update the app, then restore.",
    backup_in_corso: "Another backup is already running.",
    job_in_corso: (p: Record<string, unknown>) => {
      const nomi: Record<string, string> = {
        analysis: "BPM/key analysis", import: "playlist import", shazam: "mix identification", downloads: "downloads",
      };
      return `Something is running (${nomi[String(p.job)] ?? String(p.job ?? "")}): wait for it to finish or stop it, then try again.`;
    },
    niente_da_ripristinare: "No restore has been prepared.",
    file_non_trovato: "File not found.",
```

- [ ] **Step 4: verde, tipi, lint, commit**

Run: `cd frontend && npx vitest run tests/path-picker-button.test.tsx && npx tsc --noEmit -p . && npm run lint`
Expected: PASS, nessun errore di tipo (le due strutture dei dizionari coincidono).

```bash
git add frontend/lib/api/backup.ts frontend/lib/api.ts frontend/lib/api/settings.ts frontend/components/path-picker-button.tsx frontend/lib/i18n/it.ts frontend/lib/i18n/en.ts frontend/tests/path-picker-button.test.tsx
git commit -m "feat(frontend): client di backup, picker con salva con nome, i testi in due lingue"
```

---

### Task 7: la scheda «Dati» in Impostazioni

**Files:**
- Create: `frontend/components/settings/backup-card.tsx`
- Modify: `frontend/app/settings/page.tsx` (fra `<OrganizeSection />` e l'intestazione Versione)
- Test: `frontend/tests/backup-card.test.tsx`

**Interfaces:**
- Consumes: Task 6 (`getBackupEstimate`, `createBackup`, `prepareRestore`, `confirmRestore`, `cancelRestore`, `lastRestore`, `pickPath`), `useAggiornamento().nelGuscio` e `riavviaOra`, `fmtDate`.
- Produces: `export function BackupCard()`.

- [ ] **Step 1: test (fallisce)**

Creare `frontend/tests/backup-card.test.tsx`:

```tsx
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

const api = vi.hoisted(() => ({
  getBackupEstimate: vi.fn(),
  createBackup: vi.fn(),
  prepareRestore: vi.fn(),
  confirmRestore: vi.fn(),
  cancelRestore: vi.fn(),
  lastRestore: vi.fn(),
  pickPath: vi.fn(),
}));
vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<object>()),
  ...api,
}));

const guscio = vi.hoisted(() => ({ nelGuscio: false, riavviaOra: vi.fn() }));
vi.mock("@/lib/updates", () => ({
  useAggiornamento: () => ({ ...guscio, stato: { fase: "sconosciuto" }, controllaOra: vi.fn(), installaOra: vi.fn() }),
}));

import { BackupCard } from "@/components/settings/backup-card";
import { ApiError } from "@/lib/api";

const stima = (extra = {}) => ({
  byte: 23_400_000,
  voci: [
    { nome: "database", byte: 20_000_000, presente: true },
    { nome: "covers", byte: 3_400_000, presente: true },
    { nome: "env", byte: 100, presente: true },
    { nome: "slskd", byte: 50, presente: true },
  ],
  last_backup_at: null as string | null,
  nome_di_default: "cratory-backup-20260913-1840.zip",
  picker_disponibile: true,
  ...extra,
});

beforeEach(() => {
  api.getBackupEstimate.mockResolvedValue(stima());
  api.lastRestore.mockResolvedValue(null);
  guscio.nelGuscio = false;
});
afterEach(() => {
  cleanup();
  Object.values(api).forEach((f) => f.mockReset());
  guscio.riavviaOra.mockReset();
});

describe("scheda Dati", () => {
  it("dice che non c'è ancora un backup e quanto peserebbe", async () => {
    render(<BackupCard />);
    expect(await screen.findByText("Nessun backup finora")).toBeTruthy();
    expect(screen.getByText(/circa 23 MB · database, 1 cover, credenziali/)).toBeTruthy();
  });

  it("mostra la data dell'ultimo backup", async () => {
    api.getBackupEstimate.mockResolvedValue(stima({ last_backup_at: "2026-09-12T16:40:00+00:00" }));
    render(<BackupCard />);
    expect(await screen.findByText(/Ultimo backup: 12 set 2026/)).toBeTruthy();
  });

  it("senza picker il backup va al backend con path nullo e mostra dove è finito", async () => {
    api.getBackupEstimate.mockResolvedValue(stima({ picker_disponibile: false }));
    api.createBackup.mockResolvedValue({ percorso: "/Users/x/Downloads/b.zip", byte: 23_400_000, creato_il: "x" });
    render(<BackupCard />);
    fireEvent.click(await screen.findByText("Backup ora…"));
    await waitFor(() => expect(api.createBackup).toHaveBeenCalledWith(null));
    expect(await screen.findByText(/Backup scritto in \/Users\/x\/Downloads\/b.zip \(23 MB\)/)).toBeTruthy();
    expect(api.pickPath).not.toHaveBeenCalled();
    // Senza picker il ripristino non si offre.
    expect(screen.queryByText("Ripristina da backup…")).toBeNull();
  });

  it("con il picker chiede dove salvare, col nome di default", async () => {
    api.pickPath.mockResolvedValue({ path: "/Users/x/Desktop/b.zip" });
    api.createBackup.mockResolvedValue({ percorso: "/Users/x/Desktop/b.zip", byte: 1_000_000, creato_il: "x" });
    render(<BackupCard />);
    await act(async () => {
      fireEvent.click(await screen.findByText("Backup ora…"));
    });
    expect(api.pickPath).toHaveBeenCalledWith("save", undefined, "Salva il backup di Cratory", "cratory-backup-20260913-1840.zip");
    await waitFor(() => expect(api.createBackup).toHaveBeenCalledWith("/Users/x/Desktop/b.zip"));
  });

  it("il ripristino mostra il riepilogo, e Annulla scarta lo staging", async () => {
    api.pickPath.mockResolvedValue({ path: "/x/b.zip" });
    api.prepareRestore.mockResolvedValue({
      creato_il: "2026-09-01T10:00:00+00:00", app_version: "1.0.7", tracce: 3412, playlist: 58,
      membri: [], ha_credenziali: true,
    });
    api.cancelRestore.mockResolvedValue(undefined);
    render(<BackupCard />);
    await act(async () => {
      fireEvent.click(await screen.findByText("Ripristina da backup…"));
    });
    expect(await screen.findByText(/3412 tracce, 58 playlist/)).toBeTruthy();
    expect(screen.getByText(/versione 1.0.7/)).toBeTruthy();
    expect(screen.getByText("Include le credenziali.")).toBeTruthy();
    expect(screen.getByText(/messi da parte/)).toBeTruthy();
    fireEvent.click(screen.getByText("Annulla"));
    await waitFor(() => expect(api.cancelRestore).toHaveBeenCalled());
    expect(api.confirmRestore).not.toHaveBeenCalled();
  });

  it("la conferma nel guscio riavvia; nel browser chiede di riavviare il backend", async () => {
    api.pickPath.mockResolvedValue({ path: "/x/b.zip" });
    api.prepareRestore.mockResolvedValue({ creato_il: null, app_version: null, tracce: 0, playlist: 0, membri: [], ha_credenziali: false });
    api.confirmRestore.mockResolvedValue({ riavvio_necessario: true });

    render(<BackupCard />);
    await act(async () => {
      fireEvent.click(await screen.findByText("Ripristina da backup…"));
    });
    fireEvent.click(await screen.findByText("Ripristina e riavvia"));
    expect(await screen.findByText(/Riavvia il backend per completarlo/)).toBeTruthy();
    expect(guscio.riavviaOra).not.toHaveBeenCalled();
    cleanup();

    guscio.nelGuscio = true;
    render(<BackupCard />);
    await act(async () => {
      fireEvent.click(await screen.findByText("Ripristina da backup…"));
    });
    fireEvent.click(await screen.findByText("Ripristina e riavvia"));
    await waitFor(() => expect(guscio.riavviaOra).toHaveBeenCalled());
  });

  it("un job in corso diventa una frase che lo nomina", async () => {
    // Il client traduce il codice prima di sollevare: qui arriva già la frase.
    api.pickPath.mockResolvedValue({ path: "/x/b.zip" });
    api.prepareRestore.mockRejectedValue(new ApiError(
      "C'è un lavoro in corso (analisi BPM/key): aspetta che finisca o fermalo, poi riprova.", 409, "job_in_corso",
    ));
    render(<BackupCard />);
    await act(async () => {
      fireEvent.click(await screen.findByText("Ripristina da backup…"));
    });
    expect(await screen.findByText(/lavoro in corso \(analisi BPM\/key\)/)).toBeTruthy();
  });

  it("mostra l'esito dell'ultimo ripristino", async () => {
    api.lastRestore.mockResolvedValue({ stato: "ok", applicato_il: "2026-09-13T08:00:00+00:00", backup_creato_il: "2026-09-01T10:00:00+00:00", tracce: 1, playlist: 1 });
    render(<BackupCard />);
    expect(await screen.findByText(/Ripristinato il 13 set 2026 dal backup del 01 set 2026/)).toBeTruthy();
  });
});
```

La frase del 409 nel test deve coincidere con la voce `job_in_corso` aggiunta a `errors` nel Task 6: è la prova che il dizionario e il componente si parlano attraverso il client, senza tabelle intermedie.

- [ ] **Step 2: rosso, poi il componente**

Creare `frontend/components/settings/backup-card.tsx`:

```tsx
"use client";

/* La scheda «Dati»: backup in uno zip (salva con nome quando il picker c'è,
   ~/Downloads altrimenti) e ripristino in due tempi — riepilogo, conferma,
   riavvio. Lo scambio dei file lo fa il backend al prossimo avvio, mai a caldo:
   nel guscio il riavvio parte da qui, nel browser si chiede di farlo a mano. */

import { useCallback, useEffect, useState } from "react";
import {
  cancelRestore, confirmRestore, createBackup, errText, fmtDate, getBackupEstimate,
  lastRestore, pickPath, prepareRestore,
  type BackupEstimate, type RestoreOutcome, type RestoreSummary,
} from "@/lib/api";
import { Alert, Button, Modal, Spinner } from "@/components/ui";
import { useAggiornamento } from "@/lib/updates";
import { useT, type Dictionary } from "@/lib/i18n";

const MB = 1_000_000;
const mb = (byte: number) => Math.max(1, Math.round(byte / MB)).toString();

// Gli errori del backend arrivano già tradotti dal client (dizionario
// `errors`): qui basta `errText(e)`.

function partiDellaStima(t: Dictionary, s: BackupEstimate): string {
  const parti: string[] = [];
  const v = (nome: string) => s.voci.find((x) => x.nome === nome);
  if (v("database")?.presente) parti.push(t.settings.backupPartDatabase);
  const covers = v("covers");
  if (covers?.presente && covers.byte > 0) parti.push(t.settings.backupPartCovers(1));
  if (v("env")?.presente || v("slskd")?.presente) parti.push(t.settings.backupPartCredentials);
  return parti.join(", ");
}

export function BackupCard() {
  const t = useT();
  const { nelGuscio, riavviaOra } = useAggiornamento();
  const [stima, setStima] = useState<BackupEstimate | null>(null);
  const [ultimo, setUltimo] = useState<RestoreOutcome | null>(null);
  const [busy, setBusy] = useState(false);
  const [esito, setEsito] = useState<string | null>(null);
  const [errore, setErrore] = useState<string | null>(null);
  const [riepilogo, setRiepilogo] = useState<RestoreSummary | null>(null);
  const [riavvioManuale, setRiavvioManuale] = useState(false);

  const carica = useCallback(() => {
    getBackupEstimate().then(setStima).catch(() => setStima(null));
    lastRestore().then(setUltimo).catch(() => setUltimo(null));
  }, []);
  useEffect(carica, [carica]);

  const backupOra = async () => {
    setErrore(null);
    setEsito(null);
    setBusy(true);
    try {
      let path: string | null = null;
      if (stima?.picker_disponibile) {
        const r = await pickPath("save", undefined, t.settings.backupSavePrompt, stima.nome_di_default);
        if (!r.path) return;
        path = r.path;
      }
      const fatto = await createBackup(path);
      setEsito(t.settings.backupDone(fatto.percorso, mb(fatto.byte)));
      carica();
    } catch (e) {
      setErrore(errText(e));
    } finally {
      setBusy(false);
    }
  };

  const ripristinaDa = async () => {
    setErrore(null);
    setEsito(null);
    setBusy(true);
    try {
      const r = await pickPath("file", undefined, t.settings.restorePickPrompt);
      if (!r.path) return;
      setRiepilogo(await prepareRestore(r.path));
    } catch (e) {
      setErrore(errText(e));
    } finally {
      setBusy(false);
    }
  };

  const annulla = () => {
    setRiepilogo(null);
    setRiavvioManuale(false);
    void cancelRestore().catch(() => undefined);
  };

  const conferma = async () => {
    setBusy(true);
    try {
      await confirmRestore();
      if (nelGuscio) {
        await riavviaOra();
      } else {
        setRiavvioManuale(true);
      }
    } catch (e) {
      setRiepilogo(null);
      setErrore(errText(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="border border-border p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-sm text-fg">
            {stima?.last_backup_at ? t.settings.backupLast(fmtDate(stima.last_backup_at)) : t.settings.backupNever}
          </p>
          {stima && (
            <p className="mt-1 text-xs text-muted">{t.settings.backupEstimate(mb(stima.byte), partiDellaStima(t, stima))}</p>
          )}
        </div>
        <div className="flex flex-wrap gap-2">
          <Button size="sm" variant="primary" disabled={busy || !stima} onClick={() => void backupOra()}>
            {busy ? <Spinner /> : t.settings.backupNow}
          </Button>
          {stima?.picker_disponibile && (
            <Button size="sm" variant="outline" disabled={busy} onClick={() => void ripristinaDa()}>
              {t.settings.restoreButton}
            </Button>
          )}
        </div>
      </div>
      <p className="mt-3 text-[10px] text-faint">{t.settings.backupNote}</p>
      {ultimo && (
        <p className="mt-2 text-xs text-muted">
          {ultimo.stato === "ok"
            ? t.settings.restoreApplied(fmtDate(ultimo.applicato_il), fmtDate(ultimo.backup_creato_il))
            : t.settings.restoreFailedLast}
        </p>
      )}
      {esito && <div className="mt-3"><Alert tone="success">{esito}</Alert></div>}
      {errore && <div className="mt-3"><Alert tone="danger">{errore}</Alert></div>}

      <Modal
        open={riepilogo !== null}
        onClose={annulla}
        title={t.settings.restoreTitle}
        footer={
          riavvioManuale ? null : (
            <>
              <Button variant="ghost" size="sm" onClick={annulla}>{t.common.cancel}</Button>
              <Button variant="danger" size="sm" disabled={busy} onClick={() => void conferma()}>
                {t.settings.restoreConfirm}
              </Button>
            </>
          )
        }
      >
        {riepilogo && (
          <div className="space-y-2 text-sm text-muted">
            <p className="text-fg">
              {t.settings.restoreSummary(fmtDate(riepilogo.creato_il), riepilogo.app_version ?? "—")}{" "}
              {t.settings.restoreCounts(riepilogo.tracce, riepilogo.playlist)}
            </p>
            <p>{riepilogo.ha_credenziali ? t.settings.restoreHasCredentials : t.settings.restoreNoCredentials}</p>
            <p>{t.settings.restoreWarnKept}</p>
            <p>{t.settings.restoreWarnQueue}</p>
            {riavvioManuale && <Alert tone="info">{t.settings.restoreManualRestart}</Alert>}
          </div>
        )}
      </Modal>
    </div>
  );
}
```

Nota su `partiDellaStima`: il numero di cover non viaggia nella stima (solo i byte), quindi si mostra «1 cover» quando la voce è presente e non vuota. Se un giorno servirà il conteggio esatto, si aggiunge `file: int` alla `Voce` del backend; fuori scope qui.

- [ ] **Step 3: montare in Impostazioni**

In `frontend/app/settings/page.tsx`, aggiungere l'import `import { BackupCard } from "@/components/settings/backup-card";` e, fra `<OrganizeSection />` e l'intestazione `versionHeading`:

```tsx
      <div className="mb-2 mt-8 text-[10px] uppercase tracking-wider text-muted">{t.settings.dataHeading}</div>
      <BackupCard />
```

Aggiornare il commento in testa alla pagina: «6 gruppi: Generale · Discovery · Percorsi e libreria · Servizi esterni · Organize · Dati» (più la Versione).

- [ ] **Step 4: verde, lint, prova nel browser, commit**

Run: `cd frontend && npx vitest run tests/backup-card.test.tsx && npm run lint`
Expected: PASS.

Verifica visiva: con backend e `npm run dev` attivi, aprire `/settings`, premere «Backup ora…», salvare sulla Scrivania, controllare che lo zip esista e che la scheda mostri percorso e data. Poi «Ripristina da backup…» sullo stesso file: il riepilogo deve mostrare i contatori; premere Annulla e verificare che `backend/data/restore-staging` non esista più.

```bash
git add frontend/components/settings/backup-card.tsx frontend/app/settings/page.tsx frontend/tests/backup-card.test.tsx
git commit -m "feat(settings): la scheda Dati — backup ora, ripristino con riepilogo e riavvio"
```

---

### Task 8: l'updater chiede prima

**Files:**
- Create: `frontend/components/settings/conferma-aggiornamento.tsx`
- Modify: `frontend/components/settings/aggiornamento-guscio.tsx` (sostituire la `ConfirmModal`)
- Test: `frontend/tests/conferma-aggiornamento.test.tsx`, `frontend/tests/aggiornamento-guscio.test.tsx`

**Interfaces:**
- Consumes: `getBackupEstimate`, `createBackup`, `pickPath`, `errText` (Task 6).
- Produces: `export function ConfermaAggiornamento({ open, onClose, onInstall }: { open: boolean; onClose: () => void; onInstall: () => void })`.

- [ ] **Step 1: test (fallisce)**

Creare `frontend/tests/conferma-aggiornamento.test.tsx`:

```tsx
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

const api = vi.hoisted(() => ({
  getBackupEstimate: vi.fn(),
  createBackup: vi.fn(),
  pickPath: vi.fn(),
}));
vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<object>()),
  ...api,
}));

import { ConfermaAggiornamento } from "@/components/settings/conferma-aggiornamento";

const stima = (picker = true) => ({
  byte: 23_400_000, voci: [], last_backup_at: null, nome_di_default: "b.zip", picker_disponibile: picker,
});

beforeEach(() => {
  api.getBackupEstimate.mockResolvedValue(stima());
});
afterEach(() => {
  cleanup();
  Object.values(api).forEach((f) => f.mockReset());
});

const monta = () => {
  const onInstall = vi.fn();
  const onClose = vi.fn();
  render(<ConfermaAggiornamento open onClose={onClose} onInstall={onInstall} />);
  return { onInstall, onClose };
};

describe("la conferma dell'aggiornamento", () => {
  it("con la stima offre tre uscite e dice i MB", async () => {
    monta();
    expect(await screen.findByText(/Occuperebbe circa 23 MB/)).toBeTruthy();
    expect(screen.getByText("Backup e aggiorna")).toBeTruthy();
    expect(screen.getByText("Aggiorna senza backup")).toBeTruthy();
    expect(screen.getByText("Annulla")).toBeTruthy();
    expect(screen.getByText(/viene interrotto/)).toBeTruthy();
  });

  it("senza stima restano le due uscite di prima", async () => {
    api.getBackupEstimate.mockRejectedValue(new Error("giù"));
    monta();
    expect(await screen.findByText("Scarica e installa (≈172 MB)")).toBeTruthy();
    expect(screen.queryByText("Backup e aggiorna")).toBeNull();
    expect(screen.queryByText(/Occuperebbe/)).toBeNull();
  });

  it("aggiorna senza backup installa e basta", async () => {
    const { onInstall } = monta();
    fireEvent.click(await screen.findByText("Aggiorna senza backup"));
    expect(onInstall).toHaveBeenCalled();
    expect(api.createBackup).not.toHaveBeenCalled();
  });

  it("il dialogo annullato riporta alla modale senza installare", async () => {
    api.pickPath.mockResolvedValue({ path: null });
    const { onInstall, onClose } = monta();
    await act(async () => {
      fireEvent.click(await screen.findByText("Backup e aggiorna"));
    });
    expect(api.createBackup).not.toHaveBeenCalled();
    expect(onInstall).not.toHaveBeenCalled();
    expect(onClose).not.toHaveBeenCalled();
    expect(screen.getByText("Backup e aggiorna")).toBeTruthy();
  });

  it("un backup fallito mostra l'errore e non installa", async () => {
    api.pickPath.mockResolvedValue({ path: "/x/b.zip" });
    api.createBackup.mockRejectedValue(new Error("disco pieno"));
    const { onInstall } = monta();
    await act(async () => {
      fireEvent.click(await screen.findByText("Backup e aggiorna"));
    });
    expect(await screen.findByText(/Il backup non è riuscito/)).toBeTruthy();
    expect(screen.getByText("disco pieno")).toBeTruthy();
    expect(onInstall).not.toHaveBeenCalled();
  });

  it("percorso felice: backup, poi installazione", async () => {
    api.pickPath.mockResolvedValue({ path: "/x/b.zip" });
    api.createBackup.mockResolvedValue({ percorso: "/x/b.zip", byte: 1, creato_il: "x" });
    const { onInstall } = monta();
    await act(async () => {
      fireEvent.click(await screen.findByText("Backup e aggiorna"));
    });
    await waitFor(() => expect(onInstall).toHaveBeenCalled());
    expect(api.pickPath).toHaveBeenCalledWith("save", undefined, "Salva il backup di Cratory", "b.zip");
    expect(api.createBackup).toHaveBeenCalledWith("/x/b.zip");
  });

  it("senza picker il backup va in Downloads, senza dialogo", async () => {
    api.getBackupEstimate.mockResolvedValue(stima(false));
    api.createBackup.mockResolvedValue({ percorso: "/Users/x/Downloads/b.zip", byte: 1, creato_il: "x" });
    const { onInstall } = monta();
    await act(async () => {
      fireEvent.click(await screen.findByText("Backup e aggiorna"));
    });
    await waitFor(() => expect(onInstall).toHaveBeenCalled());
    expect(api.pickPath).not.toHaveBeenCalled();
    expect(api.createBackup).toHaveBeenCalledWith(null);
  });
});
```

- [ ] **Step 2: rosso, poi il componente**

Creare `frontend/components/settings/conferma-aggiornamento.tsx`:

```tsx
"use client";

/* La conferma dell'aggiornamento, con il backup offerto prima. La stima
   arriva dal backend, che a questo punto è ancora vivo; se non risponde la
   domanda non compare e restano le due uscite di sempre. Il backup annullato
   o fallito NON fa partire l'installazione: l'utente ha detto di volerlo. */

import { useEffect, useState } from "react";
import { createBackup, errText, getBackupEstimate, pickPath, type BackupEstimate } from "@/lib/api";
import { Button, Modal } from "@/components/ui";
import { useT } from "@/lib/i18n";

const MB = 1_000_000;
const mb = (byte: number) => Math.max(1, Math.round(byte / MB)).toString();

export function ConfermaAggiornamento({ open, onClose, onInstall }: {
  open: boolean;
  onClose: () => void;
  onInstall: () => void;
}) {
  const t = useT();
  const [stima, setStima] = useState<BackupEstimate | null>(null);
  const [inCorso, setInCorso] = useState(false);
  const [errore, setErrore] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    let vivo = true;
    setErrore(null);
    getBackupEstimate()
      .then((s) => { if (vivo) setStima(s); })
      .catch(() => { if (vivo) setStima(null); });
    return () => { vivo = false; };
  }, [open]);

  const backupPoiInstalla = async () => {
    if (!stima) return;
    setErrore(null);
    setInCorso(true);
    try {
      let path: string | null = null;
      if (stima.picker_disponibile) {
        const r = await pickPath("save", undefined, t.settings.backupSavePrompt, stima.nome_di_default);
        if (!r.path) return; // annullato: si resta sulla modale
        path = r.path;
      }
      await createBackup(path);
      onInstall();
    } catch (e) {
      setErrore(errText(e));
    } finally {
      setInCorso(false);
    }
  };

  return (
    <Modal
      open={open}
      onClose={inCorso ? () => undefined : onClose}
      title={t.settings.versionConfirmTitle}
      footer={
        <>
          <Button variant="ghost" size="sm" disabled={inCorso} onClick={onClose}>{t.common.cancel}</Button>
          {stima ? (
            <>
              <Button variant="outline" size="sm" disabled={inCorso} onClick={onInstall}>
                {t.settings.versionInstallWithoutBackup}
              </Button>
              <Button variant="primary" size="sm" disabled={inCorso} onClick={() => void backupPoiInstalla()}>
                {t.settings.versionBackupAndInstall}
              </Button>
            </>
          ) : (
            <Button variant="primary" size="sm" onClick={onInstall}>{t.settings.versionInstall}</Button>
          )}
        </>
      }
    >
      <p className="text-sm text-muted">{t.settings.versionConfirmBody}</p>
      {stima && <p className="mt-2 text-sm text-fg">{t.settings.versionBackupQuestion(mb(stima.byte))}</p>}
      {inCorso && <p className="mt-2 text-xs text-muted">{t.settings.versionBackupRunning}</p>}
      {errore && (
        <p className="mt-2 text-xs text-danger">
          {t.settings.versionBackupFailed} <span className="text-faint">{errore}</span>
        </p>
      )}
    </Modal>
  );
}
```

L'errore è in due nodi (frase fissa + dettaglio in uno `<span>`) perché il test cerca `disco pieno` da solo: `errText(e)` di un `Error` generico è il suo messaggio; di un `ApiError` è la frase già tradotta dal client dal dizionario `errors`.

- [ ] **Step 3: sostituire in `aggiornamento-guscio.tsx`**

Rimuovere `import { ConfirmModal } from "@/components/confirm-modal";`, aggiungere `import { ConfermaAggiornamento } from "@/components/settings/conferma-aggiornamento";`, e sostituire il blocco `<ConfirmModal … />` con:

```tsx
      <ConfermaAggiornamento
        open={conferma}
        onClose={() => setConferma(false)}
        onInstall={() => {
          setConferma(false);
          void installaOra();
        }}
      />
```

In `frontend/tests/aggiornamento-guscio.test.tsx` il primo test («il clic chiede conferma prima») ora monta una modale che chiama `getBackupEstimate`: aggiungere in cima al file, accanto al mock di `@/lib/updates`:

```tsx
vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<object>()),
  getBackupEstimate: () => Promise.reject(new Error("non in questo test")),
}));
```

così la modale mostra le due uscite di sempre e l'asserzione `/viene interrotto/` continua a valere.

- [ ] **Step 4: verde, lint, commit**

Run: `cd frontend && npx vitest run tests/conferma-aggiornamento.test.tsx tests/aggiornamento-guscio.test.tsx tests/backup-card.test.tsx && npm run lint && npx tsc --noEmit -p .`
Expected: PASS.

```bash
git add frontend/components/settings/conferma-aggiornamento.tsx frontend/components/settings/aggiornamento-guscio.tsx frontend/tests/conferma-aggiornamento.test.tsx frontend/tests/aggiornamento-guscio.test.tsx
git commit -m "feat(updater): prima di aggiornare si può fare un backup — tre uscite, la stima in MB"
```

---

### Task 9: documentazione

**Files:**
- Modify: `docs/API.md` (dopo la sezione «Local files and the native picker», riga ~1339), `docs/ARCHITECTURE.md` (elenco router riga ~77 e una sezione nuova), `docs/ROADMAP.md` («Current state», dopo il punto «slskd è un servizio», riga ~305), `PROGRESS.md` (in testa a «Current state by area»), `README.md`.

- [ ] **Step 1: `docs/API.md`**

Aggiornare il blocco del picker:

```text
`POST /api/files/pick` `{kind: "folder"|"file"|"save", start?, prompt?, default_name?}` opens the
Finder dialog **on the backend machine** and returns `{path}`, or `path: null` if the user
cancels or the dialog times out (300s). `save` is a "save as" dialog (`choose file name`):
it returns a path even when the file does not exist yet, proposing `default_name`.
`409 picker_unavailable` off macOS, `409 picker_busy` if a dialog is already open.
```

e aggiungere subito dopo la sezione:

```markdown
## Backup and restore

```text
GET    /api/backup/estimate
POST   /api/backup
POST   /api/backup/restore/prepare
POST   /api/backup/restore/confirm
DELETE /api/backup/restore
GET    /api/backup/restore/last
```

One zip holds the user data the disk cannot rebuild: the database (a `VACUUM INTO`
snapshot, consistent while the app runs), the uploaded playlist covers
(`data/covers/`), `.env` and `slskd.yml` — **credentials included**, so a restore puts
the app back exactly as it was. Caches, logs, pid files and the slskd download folder
stay out. Member names are fixed: `manifest.json` (`formato: 1`, `app_version`,
`creato_il`, `membri`), `data/djassistant.db`, `data/covers/<file>`, `.env`,
`data/slskd.yml`.

`GET /api/backup/estimate` → `{byte, voci: [{nome, byte, presente}], last_backup_at,
nome_di_default, picker_disponibile}`. The database size is used pages × page size,
not DB + WAL on disk.

`POST /api/backup` `{path: string | null}` writes the zip at `path` (`.zip` appended if
missing; a `.parziale` file is written next to it and renamed at the end) and returns
`{percorso, byte, creato_il}`; `path: null` saves to `~/Downloads/<nome_di_default>`.
`409 backup_in_corso` while another one is being written.

Restore is a two-step, cold swap. `POST /api/backup/restore/prepare` `{path}` validates
the archive, extracts it to `DATA_DIR/data/restore-staging/` and returns the summary
`{creato_il, app_version, tracce, playlist, membri, ha_credenziali}` — nothing is
applied yet. Errors: `404 file_non_trovato`; `400` with `archivio_non_valido`,
`manifest_assente`, `db_assente`, `db_corrotto` or `versione_piu_recente` (a backup
made by a newer app; older ones are fine, `ensure_schema` migrates forward; the check
is skipped when the running version is the `0.0.0-dev` fallback); `409 job_in_corso`
with `params.job` = `analysis | import | shazam | downloads` when the restart would
interrupt something. `POST /api/backup/restore/confirm` writes
`DATA_DIR/data/restore-pending.json` and answers `{riavvio_necessario: true}`
(`409 niente_da_ripristinare` without a prepared staging, `409 job_in_corso` re-checked).
`DELETE /api/backup/restore` discards staging and marker (204). On the next backend
start — in `main.py`, before `load_dotenv` and before anything opens the database —
the current files are moved to `DATA_DIR/data/pre-restore/` (only the latest set is
kept) and the staged ones take their place; the outcome is stored in
`app_state.last_restore` and served by `GET /api/backup/restore/last` (`{stato, applicato_il,
motivo?, backup_creato_il?, backup_app_version?, tracce?, playlist?}` or `null`).
```

- [ ] **Step 2: `docs/ARCHITECTURE.md`**

Nell'elenco dei router (riga ~77-83) aggiungere `backup` fra `ai` e `pipeline`. Aggiungere una sezione (accanto a quelle su settings/setup):

```markdown
### Backup and restore

`services/backup.py` is deterministic and HTTP-free. Backup: `VACUUM INTO` a temporary
file (a transactional snapshot that needs no job to stop), zip it with the uploaded
covers, `.env` and `slskd.yml` under fixed member names, write to `<name>.zip.parziale`
and rename at the end. The list of what goes in lives in `contenuto()` and mirrors the
list `applica_se_in_attesa()` swaps: they are the two only lists and must match.

Restore never touches the live database. `prepara()` validates (zip integrity,
manifest `formato: 1`, `PRAGMA integrity_check` on the extracted DB, version not newer
than the running app) and extracts into `data/restore-staging/`; `conferma()` writes
`data/restore-pending.json` — including the database path resolved *now*, with the
config loaded. The swap runs at the next start, in `main.py` **before `load_dotenv`**:
a restored `.env` must be in force in that very start, and at that point nothing has
opened the database yet (SQLAlchemy's engine is built at import but connects lazily).
That is also why `services/backup.py` imports `app.core.config` and `app.core.version`
only inside functions. Current files go to `data/pre-restore/` (latest set only); a
missing or incomplete staging removes the marker and leaves the data untouched. The
outcome lands in `app_state.last_restore` once the lifespan has the DB open. In the
desktop shell the page calls the existing `riavvia_app`; in the dev browser the
restore completes when the backend is restarted by hand — the alternative, a hot swap
with `engine.dispose()` and `SessionLocal.configure(bind=…)`, was rejected for the
concurrent-session and in-memory-state hazards it would add for the dev environment
alone. The updater asks for a backup before installing; that backup runs while the
backend is still alive, so `aggiornamento.rs` is unchanged.
```

- [ ] **Step 3: `docs/ROADMAP.md`, `PROGRESS.md`, `README.md`**

ROADMAP, «Current state», un punto nuovo dopo «slskd è un servizio, non un componente»:

```markdown
- **Backup e ripristino** (2026-09-13). Una scheda «Dati» in Impostazioni scrive uno
  zip — DB da `VACUUM INTO`, cover caricate, `.env`, `slskd.yml`, credenziali comprese
  per scelta — con «salva con nome» (il picker nativo ha imparato `choose file name`),
  o in `~/Downloads` senza picker. L'updater chiede prima di installare se fare un
  backup, dicendo quanto peserebbe; un backup annullato o fallito non fa partire
  l'aggiornamento. Il ripristino è in due tempi e a freddo: `prepare` valida ed
  estrae in staging e mostra il riepilogo (data, versione, tracce, playlist),
  `confirm` scrive un marker, e `main.py` applica lo scambio al riavvio **prima di
  `load_dotenv`**, mettendo i dati attuali in `pre-restore/`. Nel guscio il riavvio
  parte dalla pagina; nel browser si riavvia il backend a mano. Spec in
  `docs/superpowers/specs/2026-09-13-backup-ripristino-design.md`.
```

PROGRESS, in testa a «Current state by area»:

```markdown
- **Backup e ripristino (2026-09-13).** I dati che il disco non ricostruisce — voti,
  wishlist, set, playlist, cover, credenziali — stanno in un solo zip, salvato con
  nome da Impostazioni o su richiesta prima di un aggiornamento. Il ripristino non
  tocca mai il DB vivo: valida, mostra il riepilogo, e al riavvio scambia i file
  prima che chiunque li apra, conservando i precedenti in `pre-restore/`.
```

README, nella sezione sul flusso di lavoro o vicino alla parte su aggiornamenti/installazione, un paragrafo:

```markdown
### Backup

Settings → Data writes a single zip with everything the disk cannot rebuild: the
database, uploaded covers, `.env` and `slskd.yml`. **The file contains your
credentials** (API keys, Spotify tokens, the Soulseek password): keep it as you keep
`.env`. The updater offers a backup before installing a new version. Restore from the
same card: pick the zip, read the summary, confirm — the app restarts and swaps the
files before opening them; the previous data is kept in `data/pre-restore/`.
```

- [ ] **Step 4: rileggere parentesi e rimandi, commit**

Come chiede la nota in fondo alla ROADMAP: ogni «see X» aggiunto deve puntare a qualcosa che esiste (la spec, la sezione di ARCHITECTURE). Poi:

```bash
git add docs/API.md docs/ARCHITECTURE.md docs/ROADMAP.md PROGRESS.md README.md
git commit -m "docs: backup e ripristino — endpoint, architettura dello scambio a freddo, stato"
```

---

## Verifica finale (prima di dichiarare chiuso)

- [ ] `cd backend && python -m pytest tests -q` verde, nessun server di sviluppo su :8000.
- [ ] `cd frontend && npx vitest run && npm run lint && npx tsc --noEmit -p .` verdi.
- [ ] Prova reale nel browser di sviluppo: backup sulla Scrivania → zip apribile, manifest leggibile; ripristino dello stesso zip → riepilogo → conferma → messaggio di riavvio manuale → riavviare uvicorn → la scheda mostra «Ripristinato il …», `backend/data/pre-restore/` contiene i vecchi file, il marker non c'è più.
- [ ] `git status --porcelain` vuoto, branch corretto (vedi memoria sulle sessioni parallele).
