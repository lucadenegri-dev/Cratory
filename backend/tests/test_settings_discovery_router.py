"""GET/PUT /api/settings/discovery: Discogs come sorgente della barra del Dig.

Preferenza di interfaccia su AppState (`discovery.discogs_enabled`), default
acceso. Il backend non la fa rispettare: /dig accetta source=discogs comunque."""
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app
from app.models import AppState
from app.services.app_state import DISCOGS_ENABLED_KEY, get_discogs_enabled

client = TestClient(app)
_factory = None


def _override_db():
    global _factory
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    _factory = sessionmaker(bind=engine, expire_on_commit=False)

    def _get_db():
        db = _factory()
        try:
            yield db
        finally:
            db.close()

    return _get_db


def setup_function():
    app.dependency_overrides[get_db] = _override_db()


def teardown_function():
    app.dependency_overrides.clear()


def test_default_acceso():
    r = client.get("/api/settings/discovery")
    assert r.status_code == 200
    assert r.json() == {"discogs_enabled": True}


def test_put_spegne_e_persiste():
    r = client.put("/api/settings/discovery", json={"discogs_enabled": False})
    assert r.status_code == 200
    assert r.json() == {"discogs_enabled": False}
    assert client.get("/api/settings/discovery").json() == {"discogs_enabled": False}
    with _factory() as db:
        assert db.get(AppState, DISCOGS_ENABLED_KEY).value == "0"


def test_put_riaccende():
    client.put("/api/settings/discovery", json={"discogs_enabled": False})
    client.put("/api/settings/discovery", json={"discogs_enabled": True})
    assert client.get("/api/settings/discovery").json() == {"discogs_enabled": True}


def test_valore_ignoto_vale_acceso():
    # Una riga corrotta non deve spegnere Discogs in silenzio: solo "0" spegne.
    with _factory() as db:
        db.add(AppState(key=DISCOGS_ENABLED_KEY, value="boh"))
        db.commit()
        assert get_discogs_enabled(db) is True
