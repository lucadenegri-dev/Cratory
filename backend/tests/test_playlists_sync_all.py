"""Sync di massa delle playlist: quali playlist entrano nel giro, prosecuzione
dopo un fallimento, short-circuit quando Spotify non è connesso, guardie del router."""

import pytest

from app.models import Playlist


def test_syncable_playlists_excludes_liked_and_manual(db):
    """Solo playlist vere Spotify/SoundCloud: i liked crescono per selezione
    manuale, le manuali non hanno una sorgente da cui riallinearsi."""
    from app.services.streaming_import_job import syncable_playlists

    db.add_all([
        Playlist(platform="spotify", name="PL", kind="playlist", platform_playlist_id="PL1"),
        Playlist(platform="spotify", name="Liked", kind="liked"),
        Playlist(platform="spotify", name="Senza id", kind="playlist"),
        Playlist(platform="soundcloud", name="SC", kind="playlist",
                 url="https://soundcloud.com/utente/set"),
        Playlist(platform="soundcloud", name="SC Likes", kind="liked"),
        Playlist(platform="soundcloud", name="SC senza url", kind="playlist"),
        Playlist(platform="manual", name="Manuale", kind="manual"),
    ])
    db.commit()

    assert sorted(p.name for p in syncable_playlists(db)) == ["PL", "SC"]


@pytest.fixture()
def sync_job(db, monkeypatch):
    """Job sincrono legato alla sessione del test (mirror di sync_job in
    test_playlist_sync.py): start_job(...) ritorna già lo stato finale."""
    from sqlalchemy.orm import sessionmaker

    from app.services import streaming_import_job as sij

    monkeypatch.setattr(sij, "SessionLocal", sessionmaker(bind=db.get_bind(), expire_on_commit=False))
    monkeypatch.setattr(sij, "_spawn", lambda fn: fn())
    return sij


def _spotify_item(tid: str, *, name: str, artist: str, isrc: str) -> dict:
    return {
        "added_at": "2024-01-01T00:00:00Z",
        "track": {
            "id": tid, "type": "track", "name": name, "duration_ms": 200_000,
            "artists": [{"name": artist}],
            "album": {"name": "Album", "images": []},
            "external_ids": {"isrc": isrc},
            "external_urls": {"spotify": f"https://open.spotify.com/track/{tid}"},
        },
    }


class _FakeSpotify:
    """Client Spotify finto: `broken` elenca gli id di playlist che esplodono."""

    def __init__(self, items, broken=()):
        self._items = items
        self._broken = set(broken)

    def get_playlist_meta(self, playlist_id):
        from app.integrations.spotify import SpotifyError

        if playlist_id in self._broken:
            raise SpotifyError("playlist sparita")
        return {}

    def get_playlist_tracks(self, playlist_id):
        return self._items

    def get_liked_tracks(self):
        return self._items

    def close(self):
        pass


def test_sync_all_continues_after_a_failure(db, sync_job, monkeypatch):
    """Una playlist rotta non deve impedire il riallineamento delle altre."""
    db.add_all([
        Playlist(platform="spotify", name="Buona", kind="playlist", platform_playlist_id="OK1"),
        Playlist(platform="spotify", name="Rotta", kind="playlist", platform_playlist_id="KO1"),
    ])
    db.commit()

    fake = _FakeSpotify([_spotify_item("t1", name="One", artist="A", isrc="ISRC0000001")], broken={"KO1"})
    monkeypatch.setattr(sync_job, "SpotifyWebClient", lambda _db: fake)

    state = sync_job.start_job("playlists_sync_all")

    assert state["status"] == "done"  # i fallimenti non fanno fallire il job
    assert state["result"] is None
    report = state["sync_all"]
    assert report["synced"] == 1
    assert report["failed"] == 1
    assert report["created"] == 1
    assert [f["name"] for f in report["failures"]] == ["Rotta"]
    assert "playlist sparita" in report["failures"][0]["error"]
    assert report["failures"][0]["platform"] == "spotify"


def test_sync_all_short_circuits_when_spotify_is_disconnected(db, sync_job, monkeypatch):
    """Token assente: inutile ritentare playlist per playlist. Le SoundCloud
    proseguono comunque."""
    from app.integrations.spotify import SpotifyNotConnected

    db.add_all([
        Playlist(platform="spotify", name="S1", kind="playlist", platform_playlist_id="P1"),
        Playlist(platform="spotify", name="S2", kind="playlist", platform_playlist_id="P2"),
        Playlist(platform="soundcloud", name="SC", kind="playlist",
                 url="https://soundcloud.com/utente/set"),
    ])
    db.commit()

    calls = {"spotify": 0}

    def _boom(_db):
        calls["spotify"] += 1
        raise SpotifyNotConnected("Spotify non connesso")

    monkeypatch.setattr(sync_job, "SpotifyWebClient", _boom)
    monkeypatch.setattr(sync_job, "sc_fetch_playlist", lambda url: {
        "title": "SC", "uploader": "u", "thumbnails": [], "id": "SC1",
        "entries": [{
            "id": "sc1", "title": "Artist X - Cool Track", "uploader": "Artist X",
            "duration": 300, "webpage_url": "https://soundcloud.com/utente/track-1",
        }],
    })

    state = sync_job.start_job("playlists_sync_all")

    assert state["status"] == "done"
    report = state["sync_all"]
    assert calls["spotify"] == 1  # la seconda Spotify non ritenta la rete
    assert report["failed"] == 2
    assert report["synced"] == 1
    assert sorted(f["name"] for f in report["failures"]) == ["S1", "S2"]
