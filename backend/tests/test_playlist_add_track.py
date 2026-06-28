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


from app.integrations.spotify import SpotifyError
from app.models import Playlist, Track
from app.routers.playlists import add_discovered_track
from app.schemas import PlaylistAddTrackRequest


def _req(**kw):
    base = dict(artist="A", title="B", spotify_id="sp1", isrc="ISRC1",
                duration_seconds=200, url="http://u", album_art_url="http://img")
    base.update(kw)
    return PlaylistAddTrackRequest(**base)


def test_add_to_spotify_playlist_attaches_and_writes_back(db, monkeypatch):
    pl = Playlist(platform="spotify", platform_playlist_id="PLspot", name="Mine")
    db.add(pl); db.commit()
    called = {}
    monkeypatch.setattr(SpotifyWebClient, "add_tracks",
                        lambda self, pid, ids: called.update(pid=pid, ids=ids))

    resp = add_discovered_track(pl.id, _req(), db)
    assert resp.created is True
    assert resp.spotify_added is True and resp.spotify_error is None
    assert called == {"pid": "PLspot", "ids": ["sp1"]}
    t = db.query(Track).filter_by(spotify_id="sp1").one()
    assert t.playlist_id == pl.id


def test_add_to_manual_playlist_local_only(db, monkeypatch):
    pl = Playlist(platform="manual", name="Manuale")
    db.add(pl); db.commit()
    monkeypatch.setattr(SpotifyWebClient, "add_tracks",
                        lambda self, pid, ids: (_ for _ in ()).throw(AssertionError("non chiamare")))

    resp = add_discovered_track(pl.id, _req(), db)
    assert resp.created is True and resp.spotify_added is False and resp.spotify_error is None
    assert db.query(Track).filter_by(spotify_id="sp1").one().playlist_id == pl.id


def test_add_unresolved_candidate_local_only(db, monkeypatch):
    pl = Playlist(platform="spotify", platform_playlist_id="PLspot", name="Mine")
    db.add(pl); db.commit()
    monkeypatch.setattr(SpotifyWebClient, "add_tracks",
                        lambda self, pid, ids: (_ for _ in ()).throw(AssertionError("non chiamare")))

    resp = add_discovered_track(pl.id, _req(spotify_id=None), db)
    assert resp.spotify_added is False and resp.spotify_error is None


def test_write_back_failure_is_non_blocking(db, monkeypatch):
    pl = Playlist(platform="spotify", platform_playlist_id="PLspot", name="Mine")
    db.add(pl); db.commit()
    def boom(self, pid, ids): raise SpotifyError("Account Spotify non collegato")
    monkeypatch.setattr(SpotifyWebClient, "add_tracks", boom)

    resp = add_discovered_track(pl.id, _req(), db)
    assert resp.created is True and resp.spotify_added is False
    assert "Spotify" in resp.spotify_error
    assert db.query(Track).filter_by(spotify_id="sp1").one().playlist_id == pl.id


def test_add_does_not_move_track_from_other_playlist(db, monkeypatch):
    other = Playlist(platform="spotify", platform_playlist_id="PLother", name="Other")
    target = Playlist(platform="spotify", platform_playlist_id="PLtarget", name="Target")
    db.add_all([other, target]); db.commit()
    db.add(Track(source_type="spotify", platform="spotify", platform_track_id="sp1",
                 spotify_id="sp1", artist="A", title="B", playlist_id=other.id))
    db.commit()
    monkeypatch.setattr(SpotifyWebClient, "add_tracks", lambda self, pid, ids: None)

    resp = add_discovered_track(target.id, _req(), db)
    assert resp.created is False
    # membership locale NON spostata (modello 1:1), ma write-back tentato
    assert db.query(Track).filter_by(spotify_id="sp1").one().playlist_id == other.id
    assert resp.spotify_added is True
