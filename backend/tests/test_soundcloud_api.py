"""Router /api/soundcloud: import da URL, config username, like selettivi."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.integrations.soundcloud import SoundCloudError, SoundCloudInvalidUrl
from app.main import app
from app.models import Playlist
from app.routers import soundcloud as sc_router

client = TestClient(app)


@pytest.fixture()
def api_db():
    # StaticPool: connessione unica condivisa. FastAPI esegue gli endpoint sync
    # nel threadpool, quindi thread diversi per richieste diverse: con il pool di
    # default (SingletonThreadPool) ognuno vedrebbe un DB :memory: differente
    # (stesso motivo di test_rekordbox_api.py/_db()).
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine, expire_on_commit=False)()
    app.dependency_overrides[get_db] = lambda: db
    try:
        yield db
    finally:
        app.dependency_overrides.pop(get_db, None)
        db.close()


def _entry(i: int = 1, title: str = "Artist X - Cool Track", **kw) -> dict:
    e = {"id": str(1000 + i), "url": f"https://soundcloud.com/u/track-{i}",
         "title": title, "duration": 245.0, "uploader": "channelY"}
    e.update(kw)
    return e


def _info(entries: list) -> dict:
    return {"id": "12345", "title": "Deep Crate", "uploader": "digger",
            "webpage_url": "https://soundcloud.com/digger/sets/deep-crate",
            "entries": entries}


def test_status_e_config(api_db, monkeypatch):
    monkeypatch.setattr(sc_router, "soundcloud_available", lambda: True)
    monkeypatch.setattr(sc_router, "ytdlp_version", lambda: "2026.01.01")
    r = client.get("/api/soundcloud/status")
    assert r.status_code == 200
    assert r.json() == {"available": True, "ytdlp_version": "2026.01.01", "username": None}

    r = client.put("/api/soundcloud/config", json={"username": " luca "})
    assert r.status_code == 200
    assert r.json()["username"] == "luca"
    assert client.get("/api/soundcloud/status").json()["username"] == "luca"


def test_import_da_url_crea_playlist(api_db, monkeypatch):
    monkeypatch.setattr(sc_router, "fetch_playlist", lambda url: _info([_entry(1), _entry(2)]))
    r = client.post("/api/soundcloud/import",
                    json={"url": "https://soundcloud.com/digger/sets/deep-crate/s-abc123"})
    assert r.status_code == 200
    body = r.json()
    assert body["created"] == 2
    pl = api_db.get(Playlist, body["playlist_id"])
    assert pl.platform == "soundcloud"
    assert pl.platform_playlist_id == "12345"
    # l'URL salvato è quello incollato (conserva il secret link), non il canonico
    assert pl.url == "https://soundcloud.com/digger/sets/deep-crate/s-abc123"


def test_import_rifiuta_url_likes(api_db):
    r = client.post("/api/soundcloud/import", json={"url": "https://soundcloud.com/luca/likes"})
    assert r.status_code == 422


def test_import_mappa_errori(api_db, monkeypatch):
    def boom_invalid(url):
        raise SoundCloudInvalidUrl("URL non valido")
    monkeypatch.setattr(sc_router, "fetch_playlist", boom_invalid)
    assert client.post("/api/soundcloud/import", json={"url": "x"}).status_code == 422

    def boom_remote(url):
        raise SoundCloudError("estrazione fallita")
    monkeypatch.setattr(sc_router, "fetch_playlist", boom_remote)
    r = client.post("/api/soundcloud/import", json={"url": "https://soundcloud.com/a/sets/b"})
    assert r.status_code == 502


def test_likes_preview_409_senza_username(api_db):
    assert client.get("/api/soundcloud/likes/preview").status_code == 409


def test_likes_preview_e_import_selettivo(api_db, monkeypatch):
    client.put("/api/soundcloud/config", json={"username": "luca"})
    monkeypatch.setattr(sc_router, "fetch_likes",
                        lambda username, limit=100: _info([_entry(1), _entry(2, title="Other - Tune")]))
    r = client.get("/api/soundcloud/likes/preview")
    assert r.status_code == 200
    assert [p["track_id"] for p in r.json()] == ["1001", "1002"]

    r = client.post("/api/soundcloud/import/likes", json={"track_ids": ["1002"]})
    assert r.status_code == 200
    assert r.json()["created"] == 1
    # nella preview successiva la 1002 risulta importata
    preview = client.get("/api/soundcloud/likes/preview").json()
    assert {p["track_id"]: p["already_imported"] for p in preview} == {"1001": False, "1002": True}
