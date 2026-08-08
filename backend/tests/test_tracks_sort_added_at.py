"""Sort per data di aggiunta in libreria: GET /tracks?sort=added_at."""
from datetime import datetime

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
import pytest

import app.models  # noqa: F401
from app.db import Base, get_db
from app.main import app
from app.models import Track


@pytest.fixture()
def client_db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    app.dependency_overrides[get_db] = lambda: session
    try:
        yield TestClient(app), session
    finally:
        app.dependency_overrides.pop(get_db, None)
        session.close()


def _tr(db, title, added_at):
    t = Track(source_type="manual", title=title, artist="A", added_at=added_at)
    db.add(t)
    db.flush()
    return t


def test_sort_added_at_asc_null_in_fondo(client_db):
    client, db = client_db
    _tr(db, "vecchia", datetime(2026, 1, 1))
    _tr(db, "nuova", datetime(2026, 8, 1))
    _tr(db, "senza-data", None)
    db.commit()

    r = client.get("/api/tracks", params={"sort": "added_at", "order": "asc"})
    assert r.status_code == 200
    titles = [t["title"] for t in r.json()["items"]]
    assert titles == ["vecchia", "nuova", "senza-data"]


def test_sort_added_at_desc_null_in_fondo(client_db):
    client, db = client_db
    _tr(db, "vecchia", datetime(2026, 1, 1))
    _tr(db, "nuova", datetime(2026, 8, 1))
    _tr(db, "senza-data", None)
    db.commit()

    r = client.get("/api/tracks", params={"sort": "added_at", "order": "desc"})
    assert r.status_code == 200
    titles = [t["title"] for t in r.json()["items"]]
    assert titles == ["nuova", "vecchia", "senza-data"]
