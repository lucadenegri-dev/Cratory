"""GET /api/tracks/lookup: bridge read-only per DjOrganizer.

Route reale via TestClient (serve per verificare l'ordine delle route: vedi
`test_route_ordering_track_detail_intatto`). Il fixture `db` di conftest usa
`SingletonThreadPool`, che assegna una connessione per-thread: dato che
`TestClient` esegue le route in un thread separato, la stessa sessione
"vedrebbe" un DB in-memory vuoto. Qui usiamo un engine dedicato con
`StaticPool` (connessione unica condivisa) cosi' la sessione seedata nel test
e quella usata dalla route sono garantite sullo stesso DB in-memory.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app
from app.models import Track


@pytest.fixture()
def lookup_db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(lookup_db):
    app.dependency_overrides[get_db] = lambda: lookup_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _seed(db):
    db.add(Track(source_type="spotify", isrc="ISRC42", artist="Artist One",
                 title="Song A", genre="Techno", genre_secondary="Dub Techno",
                 label="Ostgut Ton", year=2023))
    db.commit()


def test_match_per_isrc(lookup_db, client):
    _seed(lookup_db)
    r = client.get("/api/tracks/lookup", params={"isrc": "ISRC42"})
    body = r.json()
    assert r.status_code == 200
    assert body["found"] is True and body["match"] == "isrc" and body["confidence"] == 100
    assert body["genre"] == "Techno" and body["label"] == "Ostgut Ton" and body["year"] == 2023


def test_match_fuzzy_case_insensitive(lookup_db, client):
    _seed(lookup_db)
    r = client.get("/api/tracks/lookup",
                    params={"artist": "artist one", "title": "song a"})
    body = r.json()
    assert body["found"] is True and body["match"] == "fuzzy" and body["confidence"] == 70


def test_non_trovata(lookup_db, client):
    _seed(lookup_db)
    r = client.get("/api/tracks/lookup", params={"artist": "X", "title": "Y"})
    body = r.json()
    assert r.status_code == 200
    assert body["found"] is False and body["match"] is None and body["confidence"] == 0
    assert body["genre"] is None


def test_422_senza_parametri_sufficienti(lookup_db, client):
    _seed(lookup_db)
    assert client.get("/api/tracks/lookup").status_code == 422
    assert client.get("/api/tracks/lookup", params={"artist": "solo artista"}).status_code == 422


def test_route_ordering_track_detail_intatto(lookup_db, client):
    """/tracks/lookup non deve rompere /tracks/{id}."""
    _seed(lookup_db)
    tid = client.get("/api/tracks").json()["items"][0]["id"]
    assert client.get(f"/api/tracks/{tid}").status_code == 200


def test_lookup_espone_genre_source_e_album(lookup_db, client):
    lookup_db.add(Track(source_type="spotify", spotify_id="g1", platform_track_id="g1",
                        artist="Rataxes", title="Acid Face", isrc="DEAB12300123",
                        genre="Acid Techno", genre_source="provider", album="Bunker EP"))
    lookup_db.commit()
    r = client.get("/api/tracks/lookup", params={"isrc": "DEAB12300123"}).json()
    assert r["found"] is True
    assert r["genre_source"] == "provider"
    assert r["album"] == "Bunker EP"
