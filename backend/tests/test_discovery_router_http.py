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


def test_dig_endpoint_accepts_depth_and_returns_pile_reach(client, monkeypatch):
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
    assert r.json()["pile_reach"] == 10_000  # tetto duro Discogs: 100 pagine da 100
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

    r = c.get("/api/discovery/release", params={"id": "42"})
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


def test_dig_response_speaks_items_not_pages(client, monkeypatch):
    from app.routers import discovery as router_mod
    from app.services.dig_sources import DiscoveryLead
    from app.services.discovery_dig import DigResult

    def _fake_dig(db, **kw):
        return DigResult(
            seed_type="genre", value="Acid House",
            leads=[DiscoveryLead(artist="A", title="B", source="discogs",
                                 source_id="7", source_url="https://discogs/7")],
            pile_total=43345, pile_reach=10_000, seed_resolution="style",
        )

    monkeypatch.setattr(router_mod, "dig", _fake_dig)
    c, _ = client
    r = c.post("/api/discovery/dig", json={"seed_type": "genre", "value": "Acid House"})
    assert r.status_code == 200
    body = r.json()
    assert body["pile_total"] == 43345
    assert body["pile_reach"] == 10_000
    assert "pile_pages" not in body
    assert body["source"] == "discogs"
    lead = body["leads"][0]
    assert lead["source_id"] == "7" and lead["source_url"] == "https://discogs/7"
    assert lead["stream_url"] is None
    assert "discogs_id" not in lead


def test_dig_rejects_an_unknown_source(client):
    c, _ = client
    r = c.post("/api/discovery/dig",
               json={"seed_type": "genre", "value": "x", "source": "soundcloud"})
    assert r.status_code == 422


# --- Task 6: GET /api/discovery/release?source=&id= — entrambe le sorgenti ---


def test_release_detail_of_a_bandcamp_lead(client, monkeypatch):
    from app.routers import discovery as router_mod

    class _FakeBandcamp:
        def tralbum(self, *, band_id, tralbum_id, tralbum_type="a"):
            assert (band_id, tralbum_id) == (2920024821, 1022287860)
            return {
                "title": "Love Letter", "tralbum_artist": "Inox Traxx",
                "bandcamp_url": "https://ostgut.bandcamp.com/album/love-letter",
                "art_id": 2027095290, "label": "Ostgut Ton", "release_date": 1782432000,
                "tags": [{"name": "techno"}],
                "tracks": [{"track_num": 1, "title": "Love Letter", "duration": 212.012,
                            "streaming_url": {"mp3-128": "https://bandcamp/stream/1"}}],
            }

        def close(self):
            pass

    monkeypatch.setattr(router_mod, "BandcampClient", lambda: _FakeBandcamp())
    c, _ = client
    r = c.get("/api/discovery/release", params={"source": "bandcamp",
                                                "id": "2920024821:1022287860"})
    assert r.status_code == 200
    body = r.json()
    assert body["source"] == "bandcamp"
    assert body["artist"] == "Inox Traxx"
    assert body["source_url"].endswith("/album/love-letter")
    assert body["tracks"][0]["stream_url"] == "https://bandcamp/stream/1"
    assert body["tracks"][0]["duration_seconds"] == 212
    assert body["videos"] == []


@pytest.mark.parametrize("bad", ["notanumber", "1:2:3", "abc:1", ""])
def test_release_detail_rejects_a_malformed_id(client, bad):
    c, _ = client
    r = c.get("/api/discovery/release", params={"source": "bandcamp", "id": bad})
    assert r.status_code == 400
