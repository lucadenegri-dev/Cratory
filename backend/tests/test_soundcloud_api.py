"""Router /api/soundcloud: import da URL, config username, like selettivi.

L'import/sync vero e proprio gira ora in background (streaming_import_job):
questi test collegano il job allo stesso DB in-memory della richiesta HTTP
(SessionLocal monkeypatchato) e rendono lo spawn sincrono, cosi' la risposta
POST puo' essere ispezionata subito (mirror di test_library_index_router.py)."""

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
from app.services import streaming_import_job as sij

client = TestClient(app)


@pytest.fixture()
def api_db(monkeypatch):
    # StaticPool: connessione unica condivisa. FastAPI esegue gli endpoint sync
    # nel threadpool, quindi thread diversi per richieste diverse: con il pool di
    # default (SingletonThreadPool) ognuno vedrebbe un DB :memory: differente
    # (stesso motivo di test_rekordbox_api.py/_db()).
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine, expire_on_commit=False)()
    app.dependency_overrides[get_db] = lambda: db
    # Il job usa la propria SessionLocal() (thread separato in produzione): va
    # legata allo stesso engine del test, altrimenti scriverebbe altrove.
    monkeypatch.setattr(sij, "SessionLocal", sessionmaker(bind=engine, expire_on_commit=False))
    # Niente thread reale nei test: il job gira sincrono, la risposta POST
    # riflette gia' lo stato finale (mirror di library_index_job/audio_analysis_job).
    monkeypatch.setattr(sij, "_spawn", lambda fn: fn())
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


def test_config_username_solo_chiocciola_422(api_db):
    # "@" spogliato del prefisso diventa stringa vuota: va rifiutato, non persistito.
    r = client.put("/api/soundcloud/config", json={"username": "@"})
    assert r.status_code == 422
    assert client.get("/api/soundcloud/status").json()["username"] is None


def test_import_da_url_crea_playlist(api_db, monkeypatch):
    monkeypatch.setattr(sij, "sc_fetch_playlist", lambda url: _info([_entry(1), _entry(2)]))
    r = client.post("/api/soundcloud/import",
                    json={"url": "https://soundcloud.com/digger/sets/deep-crate/s-abc123"})
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "done"
    assert body["result"]["created"] == 2
    pl = api_db.get(Playlist, body["result"]["playlist_id"])
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
    monkeypatch.setattr(sij, "sc_fetch_playlist", boom_invalid)
    r = client.post("/api/soundcloud/import", json={"url": "x"})
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "error"
    assert body["error_code"] == "soundcloud_invalid_url"

    def boom_remote(url):
        raise SoundCloudError("estrazione fallita")
    monkeypatch.setattr(sij, "sc_fetch_playlist", boom_remote)
    r = client.post("/api/soundcloud/import", json={"url": "https://soundcloud.com/a/sets/b"})
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "error"
    assert body["error_code"] == "soundcloud_error"


def test_likes_preview_409_senza_username(api_db):
    assert client.get("/api/soundcloud/likes/preview").status_code == 409


def test_likes_preview_e_import_selettivo(api_db, monkeypatch):
    client.put("/api/soundcloud/config", json={"username": "luca"})
    fake_likes = lambda username, limit=100: _info([_entry(1), _entry(2, title="Other - Tune")])  # noqa: E731
    monkeypatch.setattr(sc_router, "fetch_likes", fake_likes)  # preview: fetch resta sincrono
    monkeypatch.setattr(sij, "fetch_likes", fake_likes)  # import: gira nel job
    r = client.get("/api/soundcloud/likes/preview")
    assert r.status_code == 200
    assert [p["track_id"] for p in r.json()] == ["1001", "1002"]

    r = client.post("/api/soundcloud/import/likes", json={"track_ids": ["1002"]})
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "done"
    assert body["result"]["created"] == 1
    # nella preview successiva la 1002 risulta importata
    preview = client.get("/api/soundcloud/likes/preview").json()
    assert {p["track_id"]: p["already_imported"] for p in preview} == {"1001": False, "1002": True}


def test_import_likes_arricchisce_con_fetch_pieno(api_db, monkeypatch):
    """L'import dei selezionati rifetcha ogni traccia in modalità piena
    (uploader/durata veri); se il fetch pieno fallisce, ripiega sull'entry flat."""
    from app.models import Track

    client.put("/api/soundcloud/config", json={"username": "luca"})
    # entries flat: senza uploader né durata (come nella realtà)
    flat = [
        _entry(1, title="Axis", uploader=None, duration=None),
        _entry(2, title="Evolution", uploader=None, duration=None),
    ]
    monkeypatch.setattr(sij, "fetch_likes", lambda username, limit=100: _info(list(flat)))

    def fake_fetch_track(url):
        if url.endswith("track-2"):
            raise SoundCloudError("giù")  # fallback: si importa l'entry flat
        return _entry(1, title="Axis", uploader="Nuclear Hyde", duration=380.2)

    monkeypatch.setattr(sij, "fetch_track", fake_fetch_track)
    r = client.post("/api/soundcloud/import/likes", json={"track_ids": ["1001", "1002"]})
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "done"
    assert body["result"]["created"] == 2
    by_id = {t.platform_track_id: t for t in api_db.query(Track).all()}
    assert by_id["1001"].artist == "Nuclear Hyde"  # dal fetch pieno
    assert by_id["1001"].duration_seconds == 380
    assert by_id["1002"].artist is None  # fallback flat: uploader non noto
    assert by_id["1002"].title == "Evolution"


# --- sync per piattaforma --------------------------------------------------------


def test_sync_soundcloud_additivo_senza_prune(api_db, monkeypatch):
    monkeypatch.setattr(sij, "sc_fetch_playlist", lambda url: _info([_entry(1), _entry(2)]))
    body = client.post("/api/soundcloud/import",
                       json={"url": "https://soundcloud.com/digger/sets/deep-crate"}).json()["result"]

    # al secondo fetch la traccia 1 è sparita (takedown) e c'è una nuova traccia 3
    monkeypatch.setattr(sij, "sc_fetch_playlist",
                        lambda url: _info([_entry(2), _entry(3, title="Third - One")]))
    r = client.post(f"/api/playlists/{body['playlist_id']}/sync")
    assert r.status_code == 202
    state = r.json()
    assert state["status"] == "done"
    report = state["result"]
    assert report["created"] == 1
    assert report["removed"] == 0  # additivo: il takedown non scollega nulla
    pl = api_db.get(Playlist, body["playlist_id"])
    assert pl.track_count == 3


def test_sync_soundcloud_refreshes_name_and_cover(api_db, monkeypatch):
    # A25 (gemello SoundCloud): il sync rilegge titolo/copertina dalla sorgente.
    monkeypatch.setattr(sij, "sc_fetch_playlist", lambda url: _info([_entry(1)]))
    body = client.post("/api/soundcloud/import",
                       json={"url": "https://soundcloud.com/digger/sets/deep-crate"}).json()["result"]

    renamed = {"id": "12345", "title": "Deep Crate Vol.2", "uploader": "digger",
               "webpage_url": "https://soundcloud.com/digger/sets/deep-crate",
               "thumbnails": [{"url": "http://sc/cover-v2.jpg"}], "entries": [_entry(1)]}
    monkeypatch.setattr(sij, "sc_fetch_playlist", lambda url: renamed)
    r = client.post(f"/api/playlists/{body['playlist_id']}/sync")
    assert r.status_code == 202
    assert r.json()["status"] == "done"

    pl = api_db.get(Playlist, body["playlist_id"])
    assert pl.name == "Deep Crate Vol.2"
    assert pl.artwork_url == "http://sc/cover-v2.jpg"


def test_sync_liked_soundcloud_409(api_db, monkeypatch):
    client.put("/api/soundcloud/config", json={"username": "luca"})
    monkeypatch.setattr(sij, "fetch_likes", lambda username, limit=100: _info([_entry(1)]))
    client.post("/api/soundcloud/import/likes", json={"track_ids": ["1001"]})
    liked = api_db.query(Playlist).filter(
        Playlist.platform == "soundcloud", Playlist.kind == "liked",
    ).one()
    # Validazione sincrona nel router (non serve avviare il job): 409 immediato.
    assert client.post(f"/api/playlists/{liked.id}/sync").status_code == 409


def test_sync_soundcloud_mappa_errori(api_db, monkeypatch):
    monkeypatch.setattr(sij, "sc_fetch_playlist", lambda url: _info([_entry(1)]))
    body = client.post("/api/soundcloud/import",
                       json={"url": "https://soundcloud.com/digger/sets/deep-crate"}).json()["result"]

    def boom_invalid(url):
        raise SoundCloudInvalidUrl("URL non valido")
    monkeypatch.setattr(sij, "sc_fetch_playlist", boom_invalid)
    r = client.post(f"/api/playlists/{body['playlist_id']}/sync")
    assert r.status_code == 202
    state = r.json()
    assert state["status"] == "error"
    assert state["error_code"] == "soundcloud_invalid_url"

    def boom_remote(url):
        raise SoundCloudError("estrazione fallita")
    monkeypatch.setattr(sij, "sc_fetch_playlist", boom_remote)
    r = client.post(f"/api/playlists/{body['playlist_id']}/sync")
    assert r.status_code == 202
    state = r.json()
    assert state["status"] == "error"
    assert state["error_code"] == "soundcloud_error"


def test_import_e_sync_senza_id_non_duplica_playlist(api_db, monkeypatch):
    # yt-dlp puo' non esporre un id di set (secret link "grezzi"): senza fallback
    # sull'URL, ogni /import o /sync creerebbe una nuova Playlist.
    info_senza_id = _info([_entry(1), _entry(2)])
    info_senza_id.pop("id")
    monkeypatch.setattr(sij, "sc_fetch_playlist", lambda url: info_senza_id)
    url = "https://soundcloud.com/digger/sets/deep-crate/s-abc123"

    r1 = client.post("/api/soundcloud/import", json={"url": url})
    assert r1.status_code == 202
    r2 = client.post("/api/soundcloud/import", json={"url": url})
    assert r2.status_code == 202
    assert r1.json()["result"]["playlist_id"] == r2.json()["result"]["playlist_id"]

    playlists = api_db.query(Playlist).filter(Playlist.platform == "soundcloud").all()
    assert len(playlists) == 1
    assert playlists[0].platform_playlist_id is None

    monkeypatch.setattr(sij, "sc_fetch_playlist", lambda url: info_senza_id)
    r3 = client.post(f"/api/playlists/{r1.json()['result']['playlist_id']}/sync")
    assert r3.status_code == 202
    assert r3.json()["status"] == "done"
    playlists = api_db.query(Playlist).filter(Playlist.platform == "soundcloud").all()
    assert len(playlists) == 1
