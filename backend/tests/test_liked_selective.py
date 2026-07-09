"""Import selettivo dei Liked Spotify: anteprima marcata, import additivo, no duplicati."""

from app.models import Playlist, Track
from app.repositories import tracks_for_playlist
from app.routers import playlists as playlists_router
from app.schemas import LikedSelectedImportRequest
from app.services.playlist_import import (
    import_selected_liked_tracks,
    preview_liked_tracks,
)


def _liked_item(tid: str, *, name: str, artist: str, isrc: str | None = None,
                ms: int = 200_000) -> dict:
    return {
        "added_at": "2024-01-01T00:00:00Z",
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


class _FakeSpotify:
    def __init__(self, items):
        self._items = items

    def get_liked_tracks(self):
        return self._items


def _liked_playlist(db) -> Playlist:
    return db.query(Playlist).filter(Playlist.kind == "liked").one()


def test_import_selected_imports_only_chosen(db):
    items = [
        _liked_item("t1", name="One", artist="A", isrc="ISRC0000001"),
        _liked_item("t2", name="Two", artist="B", isrc="ISRC0000002"),
        _liked_item("t3", name="Three", artist="C", isrc="ISRC0000003"),
    ]
    report = import_selected_liked_tracks(db, items, ["t1", "t3"])

    assert report["created"] == 2
    assert report["name"] == "Liked Spotify"
    pl = _liked_playlist(db)
    titles = {t.title for t in tracks_for_playlist(db, pl.id)}
    assert titles == {"One", "Three"}


def test_second_import_is_additive_and_no_duplicate_playlist(db):
    items = [
        _liked_item("t1", name="One", artist="A", isrc="ISRC0000001"),
        _liked_item("t2", name="Two", artist="B", isrc="ISRC0000002"),
    ]
    import_selected_liked_tracks(db, items, ["t1"])
    # secondo giro: aggiungo t2; t1 resta (nessun prune)
    import_selected_liked_tracks(db, items, ["t2"])

    assert db.query(Playlist).filter(Playlist.kind == "liked").count() == 1
    pl = _liked_playlist(db)
    titles = {t.title for t in tracks_for_playlist(db, pl.id)}
    assert titles == {"One", "Two"}


def test_preview_marks_already_imported(db):
    items = [
        _liked_item("t1", name="One", artist="A", isrc="ISRC0000001"),
        _liked_item("t2", name="Two", artist="B", isrc="ISRC0000002"),
    ]
    import_selected_liked_tracks(db, items, ["t1"])

    preview = {p["spotify_id"]: p for p in preview_liked_tracks(db, items)}
    assert preview["t1"]["already_imported"] is True
    assert preview["t2"]["already_imported"] is False
    assert preview["t1"]["duration_seconds"] == 200
    assert preview["t1"]["title"] == "One"


def test_preview_empty_when_nothing_imported(db):
    items = [_liked_item("t1", name="One", artist="A", isrc="ISRC0000001")]
    preview = preview_liked_tracks(db, items)
    assert len(preview) == 1
    assert preview[0]["already_imported"] is False


def test_preview_endpoint(db, monkeypatch):
    items = [_liked_item("t1", name="One", artist="A", isrc="ISRC0000001")]
    monkeypatch.setattr(playlists_router, "SpotifyWebClient", lambda _db: _FakeSpotify(items))
    out = playlists_router.liked_preview(db)
    assert len(out) == 1
    assert out[0].spotify_id == "t1"
    assert out[0].already_imported is False


def test_import_selected_endpoint(db, monkeypatch):
    items = [
        _liked_item("t1", name="One", artist="A", isrc="ISRC0000001"),
        _liked_item("t2", name="Two", artist="B", isrc="ISRC0000002"),
    ]
    monkeypatch.setattr(playlists_router, "SpotifyWebClient", lambda _db: _FakeSpotify(items))
    report = playlists_router.import_liked_selected(
        LikedSelectedImportRequest(spotify_ids=["t2"]), db
    )
    assert report.created == 1
    pl = _liked_playlist(db)
    assert {t.title for t in tracks_for_playlist(db, pl.id)} == {"Two"}
    assert db.query(Track).count() == 1
