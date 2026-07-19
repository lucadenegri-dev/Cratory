"""Export M3U8 di una playlist (importabile in Rekordbox)."""

import pytest
from fastapi import HTTPException

from app.models import Playlist, Track
from app.repositories import add_track_to_playlist
from app.routers.playlists import export_playlist


def _pl(db):
    pl = Playlist(platform="spotify", name="P", kind="playlist")
    db.add(pl); db.flush()
    return pl


def _tr(db, title, *, local_path=None):
    t = Track(
        source_type="spotify", title=title, artist="A", duration_seconds=200,
        local_path=local_path, has_local_file=local_path is not None,
    )
    db.add(t); db.flush()
    return t


def _body(resp) -> str:
    return resp.body.decode()


def test_export_m3u8_includes_only_local_files_in_added_order(db):
    pl = _pl(db)
    a = _tr(db, "First", local_path="/music/first.aiff")
    b = _tr(db, "Second", local_path="/music/second.aiff")
    add_track_to_playlist(db, a, pl)
    add_track_to_playlist(db, b, pl)
    db.commit()

    resp = export_playlist(pl.id, "m3u8", db)
    assert resp.media_type == "audio/x-mpegurl"
    body = _body(resp)
    assert body.startswith("#EXTM3U")
    # ordine di inserimento (added_at) preservato
    assert body.index("/music/first.aiff") < body.index("/music/second.aiff")
    assert "#EXTINF:200,A — First" in body
    assert "senza file locale" not in body


def test_export_m3u8_skips_streaming_only_and_notes_count(db):
    pl = _pl(db)
    owned = _tr(db, "Owned", local_path="/music/owned.aiff")
    lead = _tr(db, "Lead", local_path=None)  # solo streaming: escluso
    add_track_to_playlist(db, owned, pl)
    add_track_to_playlist(db, lead, pl)
    db.commit()

    body = _body(export_playlist(pl.id, "m3u8", db))
    assert "/music/owned.aiff" in body
    assert "Lead" not in body
    assert "# 1 tracce senza file locale non incluse" in body


def test_export_missing_playlist_404(db):
    with pytest.raises(HTTPException) as exc:
        export_playlist(9999, "m3u8", db)
    assert exc.value.status_code == 404
