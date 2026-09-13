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


@dataclass
class Riepilogo:
    creato_il: str | None
    app_version: str | None
    tracce: int
    playlist: int
    membri: list[str]
    ha_credenziali: bool


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
