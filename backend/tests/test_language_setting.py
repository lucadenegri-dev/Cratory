"""Impostazione lingua: colonna Settings.language + GET/PUT /api/settings/language.
Default EN; valori ignoti degradano a EN."""
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app

client = TestClient(app)


def _factory():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def _override(factory):
    def _get_db():
        db = factory()
        try:
            yield db
        finally:
            db.close()
    return _get_db


def setup_function():
    app.dependency_overrides[get_db] = _override(_factory())


def teardown_function():
    app.dependency_overrides.clear()


def test_get_default_en():
    r = client.get("/api/settings/language")
    assert r.status_code == 200
    assert r.json() == {"language": "en"}


def test_put_then_get_it():
    assert client.put("/api/settings/language", json={"language": "it"}).status_code == 200
    assert client.get("/api/settings/language").json() == {"language": "it"}


def test_put_invalid_422():
    assert client.put("/api/settings/language", json={"language": "fr"}).status_code == 422


def test_get_language_helper():
    from app.services.planning import get_language, set_language
    factory = _factory()
    db = factory()
    try:
        assert get_language(db) == "en"          # default
        set_language(db, "it")
        assert get_language(db) == "it"
        set_language(db, "garbage")
        assert get_language(db) == "en"          # valore ignoto -> default
    finally:
        db.close()
