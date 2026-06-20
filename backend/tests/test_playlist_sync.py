"""Test del sync playlist da Spotify: importa nuove, scollega rimosse (restano in libreria)."""

import pytest
from fastapi import HTTPException

from app.models import Playlist, Track
from app.routers import playlists as playlists_router
from app.services.playlist_import import import_playlist


def _spotify_item(tid: str, *, name: str, artist: str, isrc: str | None = None,
                  ms: int = 200_000, added: str | None = "2024-01-01T00:00:00Z") -> dict:
    return {
        "added_at": added,
        "track": {
            "id": tid,
            "type": "track",
            "name": name,
            "duration_ms": ms,
            "artists": [{"name": artist}],
            "album": {"name": "Album", "images": [{"url": "http://img/cover.jpg"}]},
            "external_ids": {"isrc": isrc} if isrc else {},
            "external_urls": {"spotify": f"https://open.spotify.com/track/{tid}"},
        },
    }


def test_prune_unlinks_removed_tracks_but_keeps_them_in_library(db):
    items = [
        _spotify_item("t1", name="One", artist="A", isrc="ISRC0000001"),
        _spotify_item("t2", name="Two", artist="B", isrc="ISRC0000002"),
        _spotify_item("t3", name="Three", artist="C", isrc="ISRC0000003"),
    ]
    import_playlist(db, platform="spotify", name="PL", items=items, platform_playlist_id="PL1")

    # ri-sync: t3 non è più nella playlist Spotify
    report = import_playlist(
        db, platform="spotify", name="PL",
        items=[items[0], items[1]], platform_playlist_id="PL1", prune=True,
    )

    assert report["removed"] == 1
    assert report["total"] == 2  # tracce ancora collegate
    # t3 scollegata dalla playlist ma ancora in libreria
    t3 = db.query(Track).filter(Track.isrc == "ISRC0000003").one()
    assert t3.playlist_id is None
    assert t3.playlist_name is None
    assert db.query(Track).count() == 3  # nessuna traccia cancellata
    playlist = db.query(Playlist).filter(Playlist.platform_playlist_id == "PL1").one()
    assert playlist.track_count == 2
    # t1/t2 restano collegate
    assert db.query(Track).filter(Track.playlist_id == playlist.id).count() == 2


def test_prune_imports_new_and_unlinks_removed(db):
    import_playlist(db, platform="spotify", name="PL", items=[
        _spotify_item("t1", name="One", artist="A", isrc="ISRC0000001"),
        _spotify_item("t2", name="Two", artist="B", isrc="ISRC0000002"),
    ], platform_playlist_id="PL1")

    report = import_playlist(db, platform="spotify", name="PL", items=[
        _spotify_item("t1", name="One", artist="A", isrc="ISRC0000001"),
        _spotify_item("t9", name="Nine", artist="Z", isrc="ISRC0000009"),
    ], platform_playlist_id="PL1", prune=True)

    assert report["created"] == 1   # t9 nuova
    assert report["removed"] == 1   # t2 rimossa
    assert report["total"] == 2     # t1 + t9
    playlist = db.query(Playlist).filter(Playlist.platform_playlist_id == "PL1").one()
    assert playlist.track_count == 2


def test_prune_does_not_touch_other_playlists(db):
    import_playlist(db, platform="spotify", name="A", items=[
        _spotify_item("a1", name="A1", artist="A", isrc="ISRCA000001"),
    ], platform_playlist_id="PLA")
    import_playlist(db, platform="spotify", name="B", items=[
        _spotify_item("b1", name="B1", artist="B", isrc="ISRCB000001"),
    ], platform_playlist_id="PLB")

    # sync di A senza tracce: a1 viene scollegata, b1 resta intatta
    import_playlist(db, platform="spotify", name="A", items=[],
                    platform_playlist_id="PLA", prune=True)

    pl_b = db.query(Playlist).filter(Playlist.platform_playlist_id == "PLB").one()
    assert db.query(Track).filter(Track.playlist_id == pl_b.id).count() == 1


def test_default_import_does_not_prune(db):
    import_playlist(db, platform="spotify", name="PL", items=[
        _spotify_item("t1", name="One", artist="A", isrc="ISRC0000001"),
        _spotify_item("t2", name="Two", artist="B", isrc="ISRC0000002"),
    ], platform_playlist_id="PL1")

    # re-import (senza prune) di un sottoinsieme: nessuna rimozione (comportamento storico)
    report = import_playlist(db, platform="spotify", name="PL", items=[
        _spotify_item("t1", name="One", artist="A", isrc="ISRC0000001"),
    ], platform_playlist_id="PL1")

    assert report["removed"] == 0
    playlist = db.query(Playlist).filter(Playlist.platform_playlist_id == "PL1").one()
    assert db.query(Track).filter(Track.playlist_id == playlist.id).count() == 2


# --- endpoint POST /api/playlists/{id}/sync ----------------------------------


class _FakeSpotify:
    def __init__(self, items):
        self._items = items

    def get_playlist_tracks(self, playlist_id):
        return self._items

    def get_liked_tracks(self):
        return self._items


def test_sync_endpoint_reports_added_and_removed(db, monkeypatch):
    import_playlist(db, platform="spotify", name="PL", items=[
        _spotify_item("t1", name="One", artist="A", isrc="ISRC0000001"),
        _spotify_item("t2", name="Two", artist="B", isrc="ISRC0000002"),
    ], platform_playlist_id="PL1")
    playlist = db.query(Playlist).filter(Playlist.platform_playlist_id == "PL1").one()

    fake = _FakeSpotify([
        _spotify_item("t1", name="One", artist="A", isrc="ISRC0000001"),
        _spotify_item("t9", name="Nine", artist="Z", isrc="ISRC0000009"),
    ])
    monkeypatch.setattr(playlists_router, "SpotifyWebClient", lambda _db: fake)
    monkeypatch.setattr(playlists_router, "_autoenrich", lambda _pid: None)

    report = playlists_router.sync_playlist(playlist.id, db)
    assert report.created == 1
    assert report.removed == 1
    assert report.total == 2
    t2 = db.query(Track).filter(Track.isrc == "ISRC0000002").one()
    assert t2.playlist_id is None


def test_sync_endpoint_rejects_manual_playlist(db):
    playlist = Playlist(platform="manual", name="Manuale", kind="playlist")
    db.add(playlist)
    db.commit()
    with pytest.raises(HTTPException) as exc:
        playlists_router.sync_playlist(playlist.id, db)
    assert exc.value.status_code == 409


def test_sync_endpoint_404_for_missing_playlist(db):
    with pytest.raises(HTTPException) as exc:
        playlists_router.sync_playlist(999, db)
    assert exc.value.status_code == 404
