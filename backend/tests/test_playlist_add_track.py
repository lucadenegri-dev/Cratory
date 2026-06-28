"""Test add-to-playlist + write-back Spotify (nessuna rete: client finto)."""

from app.integrations.spotify import SpotifyWebClient


def test_add_tracks_posts_uris_in_chunks(monkeypatch):
    calls = []
    monkeypatch.setattr(
        SpotifyWebClient, "_call",
        lambda self, method, path, **kw: calls.append((method, path, kw.get("json"))),
    )
    client = SpotifyWebClient.__new__(SpotifyWebClient)  # niente db: _call e' patchato
    client.add_tracks("PL123", ["a", "b", "c"])
    assert calls == [
        ("POST", "/playlists/PL123/tracks", {"uris": ["spotify:track:a", "spotify:track:b", "spotify:track:c"]}),
    ]
    # i chunk sono da 100: una sola chiamata per 3 tracce
    assert len(calls) == 1
