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
