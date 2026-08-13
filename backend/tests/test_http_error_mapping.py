"""Caratterizza a livello router la mappatura status/codice di _http_error(SpotifyError)
sui due siti duplicati (routers/playlists.py, routers/spotify.py), PRIMA della fusione
in app/core/http_errors.py (Task 4, L2 finding).

Nessun test esistente copre questo code path: test_streaming_import_job.py:210-256
asserisce gli stessi tre codici ma su state["error_code"] del job, un percorso diverso
(errore intercettato dentro il job, non rilanciato come HTTPException dal router)."""

import pytest
from fastapi import HTTPException

from app.integrations.spotify import (
    SpotifyError,
    SpotifyNotConfigured,
    SpotifyNotConnected,
    SpotifyWebClient,
)
from app.models import Setlist, SetlistTrack, Track

_CASES = [
    (SpotifyNotConfigured, 409, "spotify_not_configured"),
    (SpotifyNotConnected, 401, "spotify_not_connected"),
    (SpotifyError, 502, "spotify_error"),
]


@pytest.mark.parametrize("exc_cls,status,code", _CASES)
def test_playlists_spotify_available_http_error_mapping(db, monkeypatch, exc_cls, status, code):
    """routers/playlists.py:spotify_available, che passa dal _http_error locale."""
    from app.routers.playlists import spotify_available

    def _raise(self):
        raise exc_cls("boom")

    monkeypatch.setattr(SpotifyWebClient, "list_user_playlists", _raise)

    with pytest.raises(HTTPException) as exc_info:
        spotify_available(db)
    assert exc_info.value.status_code == status
    assert exc_info.value.detail["code"] == code


def _setlist_with_spotify_track(db):
    t = Track(source_type="spotify", spotify_id="sp1", title="T", artist="A")
    db.add(t); db.flush()
    sl = Setlist(name="SL")
    db.add(sl); db.flush()
    db.add(SetlistTrack(setlist_id=sl.id, track_id=t.id, position=1))
    db.commit()
    return sl


@pytest.mark.parametrize("exc_cls,status,code", _CASES)
def test_spotify_create_playlist_http_error_mapping(db, monkeypatch, exc_cls, status, code):
    """routers/spotify.py:create_playlist, che passa dal _http_error locale (byte-identico
    a quello di playlists.py)."""
    from app.routers.spotify import CreatePlaylistRequest, create_playlist

    sl = _setlist_with_spotify_track(db)

    def _raise(self, name, track_ids):
        raise exc_cls("boom")

    monkeypatch.setattr(SpotifyWebClient, "create_playlist", _raise)

    with pytest.raises(HTTPException) as exc_info:
        create_playlist(CreatePlaylistRequest(setlist_id=sl.id), db)
    assert exc_info.value.status_code == status
    assert exc_info.value.detail["code"] == code
