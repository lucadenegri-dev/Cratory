"""GET /api/tracks?q=: un campo solo che cerca su artista O titolo.

Serve alla ricerca traccia della barra del Dig, che ha un campo di testo e
non due. `artist=` e `title=` restano separati e restrittivi."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

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


def _tr(db, artist, title):
    t = Track(source_type="local_files", platform="local_files", artist=artist, title=title)
    db.add(t)
    db.flush()
    return t


def _titles(r):
    return sorted(t["title"] for t in r.json()["items"])


def test_q_cerca_su_artista_o_titolo(client_db):
    client, db = client_db
    _tr(db, "Jasmín", "Bite The Hand")
    _tr(db, "Pearson Sound", "Jasmine Tea")      # il titolo contiene la query
    _tr(db, "Objekt", "Theme From Q")
    db.commit()

    r = client.get("/api/tracks", params={"q": "jasm"})
    assert r.status_code == 200
    assert _titles(r) == ["Bite The Hand", "Jasmine Tea"]


def test_q_non_interferisce_con_artist_esplicito(client_db):
    client, db = client_db
    _tr(db, "Jasmín", "Bite The Hand")
    _tr(db, "Pearson Sound", "Jasmine Tea")
    db.commit()

    # `artist=` resta un filtro a sé: la riga con "jasm" solo nel titolo non passa.
    r = client.get("/api/tracks", params={"q": "jasm", "artist": "Pearson"})
    assert _titles(r) == []
    r = client.get("/api/tracks", params={"artist": "Pearson"})
    assert _titles(r) == ["Jasmine Tea"]


def test_q_vuoto_non_filtra(client_db):
    client, db = client_db
    _tr(db, "A", "x")
    _tr(db, "B", "y")
    db.commit()
    r = client.get("/api/tracks", params={"q": ""})
    assert _titles(r) == ["x", "y"]
