"""Router /api/backup: il servizio è monkeypatchato, tranne dove si vuole il
percorso vero di ripiego (~/Downloads)."""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app
from app.services import backup

client = TestClient(app)


@pytest.fixture()
def db():
    """`StaticPool`, non il generico `db` di conftest.py: questi endpoint
    leggono/scrivono `AppState` per davvero (get_state/set_state) e girano nel
    thread-pool di TestClient — col `SingletonThreadPool` di default per SQLite
    in-memory quel thread vedrebbe un database vuoto ("no such table:
    app_state"), perché lo schema è stato creato sul thread del test. Stesso
    rimedio già in uso in test_slskd_daemon_router.py e affini."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        yield session
    finally:
        session.close()


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
