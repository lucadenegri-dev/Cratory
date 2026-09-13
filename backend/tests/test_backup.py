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
            c.execute(
                "INSERT INTO app_state(key, value, updated_at) VALUES (?, ?, ?)",
                (f"k{i}", "x" * 4000, "2024-01-01 00:00:00"),
            )
        c.execute("DELETE FROM app_state")
    # Il WAL è cresciuto di centinaia di KB; la stima segue le pagine usate, non il WAL.
    assert (db.parent / "djassistant.db-wal").stat().st_size > 100_000
    assert abs(backup.stima_byte() - prima) < 50_000


def test_nome_di_default_ha_data_e_ora():
    nome = backup.nome_di_default()
    assert nome.startswith("cratory-backup-") and nome.endswith(".zip")
    assert len(nome) == len("cratory-backup-20260913-1840.zip")


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
    viva.execute(
        "INSERT INTO app_state(key, value, updated_at) VALUES ('prima', 'si', '2024-01-01 00:00:00')"
    )
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
    # `dati` (la cartella DATA_DIR della fixture) è l'unica cosa che deve
    # restare in tmp_path: né zip né `.parziale` né `.db-snapshot`.
    assert list(tmp_path.iterdir()) == [dati]


def test_due_backup_insieme_il_secondo_e_rifiutato(dati, tmp_path):
    assert backup._lock.acquire(blocking=False)
    try:
        with pytest.raises(backup.BackupInCorso):
            backup.crea(tmp_path / "b.zip")
    finally:
        backup._lock.release()


# --- ispezione ------------------------------------------------------------------

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
        c.execute(
            "INSERT INTO playlists(name, platform, track_count, kind, imported_at, created_at, updated_at) "
            "VALUES ('p', 'manual', 0, 'playlist', '2024-01-01 00:00:00', '2024-01-01 00:00:00', '2024-01-01 00:00:00')"
        )
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
