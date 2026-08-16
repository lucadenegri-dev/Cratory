from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core import runtime_settings as rs
from app.db import Base, get_db
from app.main import app

client = TestClient(app)


def _override_db():
    e = create_engine("sqlite://", connect_args={"check_same_thread": False},
                      poolclass=StaticPool)
    Base.metadata.create_all(e)
    factory = sessionmaker(bind=e, expire_on_commit=False)

    def _db():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _db
    return factory


def teardown_function():
    app.dependency_overrides.clear()
    rs._overrides.pop("download_slots", None)


def test_default_e_tre():
    rs._overrides.pop("download_slots", None)
    assert rs.download_slots() == 3


def test_override_letto_dalla_cache():
    rs._overrides["download_slots"] = "5"
    assert rs.download_slots() == 5


def test_valore_illeggibile_torna_al_default():
    rs._overrides["download_slots"] = "molti"
    assert rs.download_slots() == 3


def test_valori_fuori_scala_vengono_riportati_nei_limiti():
    rs._overrides["download_slots"] = "0"
    assert rs.download_slots() == 1
    rs._overrides["download_slots"] = "99"
    assert rs.download_slots() == 10


def test_put_persiste_e_aggiorna_la_cache():
    _override_db()
    r = client.put("/api/settings/download-slots", json={"slots": 6})
    assert r.status_code == 200
    assert r.json()["download_slots"] == 6
    assert rs.download_slots() == 6


def test_put_rifiuta_valori_fuori_scala():
    _override_db()
    assert client.put("/api/settings/download-slots", json={"slots": 0}).status_code == 422
    assert client.put("/api/settings/download-slots", json={"slots": 11}).status_code == 422


def test_config_espone_il_valore():
    _override_db()
    rs._overrides["download_slots"] = "4"
    assert client.get("/api/settings/config").json()["download_slots"] == 4
