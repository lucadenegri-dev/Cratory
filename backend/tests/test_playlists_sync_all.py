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
