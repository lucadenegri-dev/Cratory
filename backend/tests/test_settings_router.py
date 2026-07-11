"""Endpoint lingua: GET/PUT /api/settings/language su AppState (chiave `language`)."""
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app

client = TestClient(app)


def _override_db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def _get_db():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    return _get_db


def setup_function():
    app.dependency_overrides[get_db] = _override_db()


def teardown_function():
    app.dependency_overrides.clear()


def test_get_default_it():
    r = client.get("/api/settings/language")
    assert r.status_code == 200
    assert r.json() == {"language": "it"}


def test_put_e_get_en():
    r = client.put("/api/settings/language", json={"language": "en"})
    assert r.status_code == 200
    assert r.json() == {"language": "en"}
    # nuova sessione, stessa engine StaticPool: il valore deve persistere
    assert client.get("/api/settings/language").json() == {"language": "en"}


def test_put_valore_invalido_422():
    r = client.put("/api/settings/language", json={"language": "fr"})
    assert r.status_code == 422


def test_get_language_helper(db):
    from app.services.app_state import get_language, set_state
    assert get_language(db) == "it"
    set_state(db, "language", "en")
    assert get_language(db) == "en"
    set_state(db, "language", "garbage")
    assert get_language(db) == "it"
