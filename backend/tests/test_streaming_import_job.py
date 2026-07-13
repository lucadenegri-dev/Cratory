"""Job unico di import/sync streaming: dispatch per kind, fasi, mapping errori."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.integrations.soundcloud import SoundCloudError, SoundCloudInvalidUrl
from app.integrations.spotify import SpotifyError, SpotifyNotConfigured, SpotifyNotConnected
from app.models import Playlist, Track


@pytest.fixture()
def sync_job(monkeypatch):
    """Job sincrono su DB in memoria condiviso (mirror di sync_job in
    test_audio_analysis_job.py: SessionLocal dedicata + _spawn sincrono)."""
    from app.services import streaming_import_job as sij

    e = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(e)
    S = sessionmaker(bind=e, expire_on_commit=False)
    monkeypatch.setattr(sij, "SessionLocal", S)
    monkeypatch.setattr(sij, "_spawn", lambda fn: fn())
    return sij, S


def _spotify_item(tid: str, *, name: str, artist: str, isrc: str | None = None) -> dict:
    return {
        "added_at": "2024-01-01T00:00:00Z",
        "track": {
            "id": tid, "type": "track", "name": name, "duration_ms": 200_000,
            "artists": [{"name": artist}],
            "album": {"name": "Album", "images": []},
            "external_ids": {"isrc": isrc} if isrc else {},
            "external_urls": {"spotify": f"https://open.spotify.com/track/{tid}"},
        },
    }


class _FakeSpotify:
    def __init__(self, items=None, playlist_meta=None):
        self._items = items or []
        self._meta = playlist_meta or {}

    def get_liked_tracks(self):
        return self._items

    def get_playlist_tracks(self, playlist_id):
        return self._items

    def get_playlist_meta(self, playlist_id):
        return self._meta

    def close(self):
        pass


def _sc_entry(i: int, title: str = "Artist X - Cool Track") -> dict:
    return {"id": str(1000 + i), "url": f"https://soundcloud.com/u/track-{i}",
            "title": title, "duration": 245.0, "uploader": "channelY"}


def _sc_info(entries: list) -> dict:
    return {"id": "12345", "title": "Deep Crate", "uploader": "digger",
            "thumbnails": [{"url": "http://sc/cover.jpg"}], "entries": entries}


# --- dispatch per kind ---------------------------------------------------------


def test_spotify_playlist(sync_job, monkeypatch):
    aj, S = sync_job
    fake = _FakeSpotify([_spotify_item("t1", name="One", artist="A", isrc="ISRC1")],
                        playlist_meta={"name": "Mia Playlist"})
    monkeypatch.setattr(aj, "SpotifyWebClient", lambda _db: fake)

    state = aj.start_job("spotify_playlist", playlist_id="PL1")

    assert state["status"] == "done"
    assert state["result"]["created"] == 1
    assert state["result"]["name"] == "Mia Playlist"
    with S() as s:
        assert s.query(Playlist).filter(Playlist.platform_playlist_id == "PL1").one()


def test_spotify_liked(sync_job, monkeypatch):
    aj, S = sync_job
    fake = _FakeSpotify([_spotify_item("t1", name="One", artist="A", isrc="ISRC1")])
    monkeypatch.setattr(aj, "SpotifyWebClient", lambda _db: fake)

    state = aj.start_job("spotify_liked")

    assert state["status"] == "done"
    with S() as s:
        assert s.query(Playlist).filter(Playlist.kind == "liked", Playlist.platform == "spotify").one()


def test_spotify_liked_selected(sync_job, monkeypatch):
    aj, S = sync_job
    fake = _FakeSpotify([
        _spotify_item("t1", name="One", artist="A", isrc="ISRC1"),
        _spotify_item("t2", name="Two", artist="B", isrc="ISRC2"),
    ])
    monkeypatch.setattr(aj, "SpotifyWebClient", lambda _db: fake)

    state = aj.start_job("spotify_liked_selected", spotify_ids=["t2"])

    assert state["status"] == "done"
    assert state["result"]["created"] == 1
    with S() as s:
        assert s.query(Track).count() == 1
        assert s.query(Track).one().title == "Two"


def test_soundcloud_playlist(sync_job, monkeypatch):
    aj, S = sync_job
    monkeypatch.setattr(aj, "sc_fetch_playlist", lambda url: _sc_info([_sc_entry(1)]))

    state = aj.start_job("soundcloud_playlist", url="https://soundcloud.com/digger/sets/deep-crate")

    assert state["status"] == "done"
    assert state["result"]["created"] == 1
    with S() as s:
        pl = s.query(Playlist).filter(Playlist.platform == "soundcloud").one()
        assert pl.platform_playlist_id == "12345"


def test_soundcloud_likes_selected(sync_job, monkeypatch):
    aj, S = sync_job
    monkeypatch.setattr(aj, "fetch_likes", lambda username, limit=None: _sc_info([_sc_entry(1), _sc_entry(2)]))
    monkeypatch.setattr(aj, "fetch_track", lambda url: _sc_entry(1))

    state = aj.start_job("soundcloud_likes_selected", username="luca", track_ids=["1001"], limit=None)

    assert state["status"] == "done"
    assert state["result"]["created"] == 1
    with S() as s:
        assert s.query(Track).count() == 1


def test_playlist_sync_spotify_prune(sync_job, monkeypatch):
    aj, S = sync_job
    with S() as s:
        pl = Playlist(platform="spotify", name="PL", kind="playlist", platform_playlist_id="PL1")
        s.add(pl)
        s.commit()
        playlist_id = pl.id
    fake = _FakeSpotify([_spotify_item("t1", name="One", artist="A", isrc="ISRC1")])
    monkeypatch.setattr(aj, "SpotifyWebClient", lambda _db: fake)

    state = aj.start_job("playlist_sync", playlist_id=playlist_id)

    assert state["status"] == "done"
    assert state["result"]["created"] == 1


def test_playlist_sync_soundcloud_additive(sync_job, monkeypatch):
    aj, S = sync_job
    with S() as s:
        pl = Playlist(platform="soundcloud", name="Deep Crate", kind="playlist",
                      url="https://soundcloud.com/digger/sets/deep-crate")
        s.add(pl)
        s.commit()
        playlist_id = pl.id
    monkeypatch.setattr(aj, "sc_fetch_playlist", lambda url: _sc_info([_sc_entry(1)]))

    state = aj.start_job("playlist_sync", playlist_id=playlist_id)

    assert state["status"] == "done"
    assert state["result"]["created"] == 1


# --- fasi ------------------------------------------------------------------------


def test_phase_fetching_then_importing(sync_job, monkeypatch):
    aj, S = sync_job
    seen_phases = []

    class _Recording(_FakeSpotify):
        def get_liked_tracks(self):
            seen_phases.append(aj.job_state()["phase"])  # durante il fetch: 'fetching'
            return self._items

    monkeypatch.setattr(aj, "SpotifyWebClient",
                        lambda _db: _Recording([_spotify_item("t1", name="One", artist="A", isrc="ISRC1")]))

    state = aj.start_job("spotify_liked")

    assert seen_phases == ["fetching"]
    assert state["phase"] is None  # azzerata a fine job


def test_progress_reported_during_import(sync_job, monkeypatch):
    aj, S = sync_job
    items = [_spotify_item(f"t{i}", name=f"T{i}", artist="A", isrc=f"ISRC{i}") for i in range(3)]
    monkeypatch.setattr(aj, "SpotifyWebClient", lambda _db: _FakeSpotify(items))

    state = aj.start_job("spotify_liked")

    assert state["status"] == "done"
    assert state["total"] == 3
    assert state["processed"] == 3


# --- mapping errori ------------------------------------------------------------


def test_spotify_not_configured_error_code(sync_job, monkeypatch):
    aj, S = sync_job

    class _Boom:
        def get_liked_tracks(self):
            raise SpotifyNotConfigured("Credenziali mancanti")

        def close(self):
            pass

    monkeypatch.setattr(aj, "SpotifyWebClient", lambda _db: _Boom())
    state = aj.start_job("spotify_liked")
    assert state["status"] == "error"
    assert state["error_code"] == "spotify_not_configured"
    assert state["error"] == "Credenziali mancanti"


def test_spotify_not_connected_error_code(sync_job, monkeypatch):
    aj, S = sync_job

    class _Boom:
        def get_liked_tracks(self):
            raise SpotifyNotConnected("Login mancante")

        def close(self):
            pass

    monkeypatch.setattr(aj, "SpotifyWebClient", lambda _db: _Boom())
    state = aj.start_job("spotify_liked")
    assert state["status"] == "error"
    assert state["error_code"] == "spotify_not_connected"


def test_generic_spotify_error_code(sync_job, monkeypatch):
    aj, S = sync_job

    class _Boom:
        def get_liked_tracks(self):
            raise SpotifyError("Boh")

        def close(self):
            pass

    monkeypatch.setattr(aj, "SpotifyWebClient", lambda _db: _Boom())
    state = aj.start_job("spotify_liked")
    assert state["status"] == "error"
    assert state["error_code"] == "spotify_error"


def test_soundcloud_invalid_url_error_code(sync_job, monkeypatch):
    aj, S = sync_job

    def boom(url):
        raise SoundCloudInvalidUrl("URL non valido")
    monkeypatch.setattr(aj, "sc_fetch_playlist", boom)

    state = aj.start_job("soundcloud_playlist", url="x")
    assert state["status"] == "error"
    assert state["error_code"] == "soundcloud_invalid_url"


def test_generic_soundcloud_error_code(sync_job, monkeypatch):
    aj, S = sync_job

    def boom(url):
        raise SoundCloudError("estrazione fallita")
    monkeypatch.setattr(aj, "sc_fetch_playlist", boom)

    state = aj.start_job("soundcloud_playlist", url="https://soundcloud.com/a/sets/b")
    assert state["status"] == "error"
    assert state["error_code"] == "soundcloud_error"


def test_unexpected_error_has_no_error_code(sync_job, monkeypatch):
    aj, S = sync_job

    def boom(url):
        raise RuntimeError("qualcosa d'altro")
    monkeypatch.setattr(aj, "sc_fetch_playlist", boom)

    state = aj.start_job("soundcloud_playlist", url="https://soundcloud.com/a/sets/b")
    assert state["status"] == "error"
    assert state["error_code"] is None
    assert state["error"] == "qualcosa d'altro"


# --- sync_error_for --------------------------------------------------------------


def test_sync_error_for_soundcloud_liked():
    from app.services import streaming_import_job as sij
    pl = Playlist(platform="soundcloud", kind="liked")
    err = sij.sync_error_for(pl)
    assert err is not None and err[0] == "soundcloud_playlist_not_syncable"


def test_sync_error_for_soundcloud_without_url():
    from app.services import streaming_import_job as sij
    pl = Playlist(platform="soundcloud", kind="playlist", url=None)
    err = sij.sync_error_for(pl)
    assert err is not None and err[0] == "soundcloud_playlist_not_syncable"


def test_sync_error_for_soundcloud_with_url_ok():
    from app.services import streaming_import_job as sij
    pl = Playlist(platform="soundcloud", kind="playlist", url="https://soundcloud.com/a/sets/b")
    assert sij.sync_error_for(pl) is None


def test_sync_error_for_other_platform():
    from app.services import streaming_import_job as sij
    pl = Playlist(platform="manual", kind="playlist")
    err = sij.sync_error_for(pl)
    assert err is not None and err[0] == "playlist_platform_not_syncable"


def test_sync_error_for_spotify_without_platform_playlist_id():
    from app.services import streaming_import_job as sij
    pl = Playlist(platform="spotify", kind="playlist", platform_playlist_id=None)
    err = sij.sync_error_for(pl)
    assert err is not None and err[0] == "playlist_not_syncable"


def test_sync_error_for_spotify_liked_ok():
    from app.services import streaming_import_job as sij
    pl = Playlist(platform="spotify", kind="liked", platform_playlist_id=None)
    assert sij.sync_error_for(pl) is None
