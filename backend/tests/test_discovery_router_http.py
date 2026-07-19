"""Copertura HTTP (TestClient) del router /api/discovery: /genres, /dig. La logica
di dig e' gia' testata a fondo a livello di funzione in tests/test_discovery.py
(anche chiamando dig_endpoint/get_release_detail direttamente) e
tests/test_discovery_dig.py: qui si copre lo strato HTTP mancante (shape JSON via
TestClient). Il 502 su dig e' gia' coperto in test_discovery.py, non duplicato qui."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app
from app.models import Track


@pytest.fixture()
def client():
    e = create_engine("sqlite://", connect_args={"check_same_thread": False},
                      poolclass=StaticPool)
    Base.metadata.create_all(e)
    S = sessionmaker(bind=e, expire_on_commit=False)

    def _get_db():
        db = S()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _get_db
    yield TestClient(app), S
    app.dependency_overrides.clear()


# --- /genres ----------------------------------------------------------------------


def test_genres_200_include_libreria_e_stili_curati(client):
    c, S = client
    with S() as s:
        s.add(Track(source_type="spotify", title="T1", artist="A", genre="Acid House"))
        s.add(Track(source_type="spotify", title="T2", artist="B", genre="Acid House"))  # duplicato
        s.add(Track(source_type="spotify", title="T3", artist="C", genre="Ambient"))
        s.add(Track(source_type="spotify", title="T4", artist="D", genre=None))  # ignorato
        s.commit()

    r = c.get("/api/discovery/genres")
    assert r.status_code == 200
    body = r.json()
    assert body["library"] == ["Acid House", "Ambient"]  # ordinato, senza duplicati
    assert "House" in body["styles"]  # stile curato sempre presente


def test_genres_200_libreria_vuota(client):
    c, _ = client
    r = c.get("/api/discovery/genres")
    assert r.status_code == 200
    assert r.json()["library"] == []


# --- /dig -----------------------------------------------------------------------


def _fake_release(title="Cult - Grail", *, label="Lbl", style="Acid House"):
    return {
        "id": 1, "title": title, "year": 2024,
        "label": [label], "style": [style],
        "community": {"have": 3, "want": 120}, "format": ["Vinyl"],
        "uri": "/release/1", "cover_image": "http://img",
    }


def test_dig_200_via_http(client, monkeypatch):
    from app.integrations.discogs import DiscogsClient

    c, _ = client
    monkeypatch.setattr(DiscogsClient, "search_releases", lambda self, **kw: [_fake_release()])
    # La sonda va mockata come la search: il dig la chiama SEMPRE, e senza mock
    # questo test farebbe una richiesta VERA a Discogs (test senza rete: vedi il
    # docstring di app/integrations/discogs.py). 100 = una pagina sola: pila corta,
    # la finestra e' l'intera pila e `depth` non c'entra con cio' che qui si dimostra
    # (la shape JSON del lead). Deve comunque essere > 0, o il dig si ferma prima
    # della search e non ci sarebbero lead da verificare.
    monkeypatch.setattr(DiscogsClient, "count_releases", lambda self, **kw: 100)

    r = c.post("/api/discovery/dig", json={"seed_type": "genre", "value": "Acid House"})
    assert r.status_code == 200
    body = r.json()
    assert body["seed_type"] == "genre"
    assert body["value"] == "Acid House"
    assert len(body["leads"]) == 1
    assert body["leads"][0]["artist"] == "Cult"
    assert body["leads"][0]["title"] == "Grail"


def test_dig_422_seed_type_non_valido(client):
    c, _ = client
    r = c.post("/api/discovery/dig", json={"seed_type": "not_a_seed_type", "value": "x"})
    assert r.status_code == 422  # Literal["genre", "label"] non rispettato


def test_dig_endpoint_accepts_depth_and_returns_pile_pages(client, monkeypatch):
    from app.integrations.discogs import DiscogsClient

    c, _ = client
    captured = {}

    def _fake_search(self, **kw):
        captured.update(kw)
        return []

    monkeypatch.setattr(DiscogsClient, "search_releases", _fake_search)
    monkeypatch.setattr(DiscogsClient, "count_releases", lambda self, **kw: 43345)

    r = c.post("/api/discovery/dig", json={"seed_type": "genre", "value": "Acid House", "depth": 1.0})
    assert r.status_code == 200
    assert r.json()["pile_pages"] == 100
    assert captured["pages"] == [98, 99, 100]


def test_dig_endpoint_depth_defaults_to_the_canon(client, monkeypatch):
    from app.integrations.discogs import DiscogsClient

    c, _ = client
    captured = {}

    def _fake_search(self, **kw):
        captured.update(kw)
        return []

    monkeypatch.setattr(DiscogsClient, "search_releases", _fake_search)
    monkeypatch.setattr(DiscogsClient, "count_releases", lambda self, **kw: 43345)

    r = c.post("/api/discovery/dig", json={"seed_type": "genre", "value": "Acid House"})
    assert r.status_code == 200
    assert captured["pages"] == [1, 2, 3]  # default depth=0.0: i classici


def test_dig_endpoint_rejects_out_of_range_depth(client):
    c, _ = client
    r = c.post("/api/discovery/dig", json={"seed_type": "genre", "value": "x", "depth": 1.5})
    assert r.status_code == 422


def test_release_detail_exposes_youtube_videos(client, monkeypatch):
    from app.integrations.discogs import DiscogsClient

    c, _ = client
    payload = {
        "id": 42,
        "title": "Artist - EP",
        "artists": [{"name": "Artist"}],
        "labels": [{"name": "Lbl"}],
        "images": [],
        "uri": "/release/42",
        "year": 2001,
        "tracklist": [{"type_": "track", "position": "A", "title": "Acid Trip", "duration": "5:00"}],
        "videos": [
            {"uri": "https://www.youtube.com/watch?v=abcdefghijk", "title": "Artist - Acid Trip", "duration": 300},
            {"uri": "https://vimeo.com/1", "title": "nope", "duration": 1},
        ],
    }
    monkeypatch.setattr(DiscogsClient, "get_release", lambda self, rid: payload)

    r = c.get("/api/discovery/release/42")
    assert r.status_code == 200
    body = r.json()
    assert body["videos"] == [
        {"youtube_video_id": "abcdefghijk", "title": "Artist - Acid Trip", "duration_seconds": 300}
    ]


def test_dig_endpoint_ignores_legacy_limit_field(client, monkeypatch):
    """Il campo `limit` non esiste piu' nel contratto (il tetto nascondeva 160 lead a
    ogni dig). DiscoveryDigRequest non ha extra="forbid", quindi Pydantic IGNORA i campi
    sconosciuti (verificato sulla config reale): una richiesta vecchia non si rompe e,
    soprattutto, non tronca piu' nulla.
    """
    from app.integrations.discogs import DiscogsClient

    c, _ = client
    monkeypatch.setattr(
        DiscogsClient, "search_releases",
        lambda self, **kw: [_fake_release(title=f"Artist{i} - T{i}") for i in range(150)],
    )
    monkeypatch.setattr(DiscogsClient, "count_releases", lambda self, **kw: 43345)

    r = c.post("/api/discovery/dig",
               json={"seed_type": "genre", "value": "Acid House", "limit": 5})
    assert r.status_code == 200
    # Asserzione ESATTA, non `> 5`: coglie sia il troncamento a 5 (campo legacy
    # rispettato) sia la reintroduzione di QUALUNQUE tetto a valle (es. 80).
    assert len(r.json()["leads"]) == 150


def test_dig_endpoint_exposes_seed_resolution_and_pile_total(client, monkeypatch):
    from app.integrations.discogs import DiscogsClient

    c, _ = client
    monkeypatch.setattr(DiscogsClient, "search_releases", lambda self, **kw: [])
    monkeypatch.setattr(
        DiscogsClient, "count_releases",
        lambda self, **kw: 0 if "style" in kw else 4_960_093,
    )
    r = c.post("/api/discovery/dig", json={"seed_type": "genre", "value": "Electronic"})
    assert r.status_code == 200
    assert r.json()["seed_resolution"] == "genre"
    assert r.json()["pile_total"] == 4_960_093
