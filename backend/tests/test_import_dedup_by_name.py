"""A11: dedup per artista+titolo(+durata) anche in import_playlist. Senza, una
traccia importata a mano poi reimportata da Spotify diventa un doppione."""
from app.models import Track
from app.services.playlist_import import NormalizedTrack, identity_normalize, import_playlist


def _spotify_item(title, artist, duration, *, track_id="spot1", isrc=None):
    return NormalizedTrack(
        platform="spotify", platform_track_id=track_id, title=title, artist=artist,
        album=None, duration_seconds=duration, url=None, artwork_url=None,
        isrc=isrc, added_at=None,
    )


def test_spotify_import_dedups_onto_manual_track(db):
    # Traccia già in libreria, importata "a mano": solo artista+titolo, nessun id/isrc/durata.
    db.add(Track(source_type="manual", platform="manual", title="Strobe", artist="Deadmau5"))
    db.commit()

    report = import_playlist(
        db, platform="spotify", name="P", platform_playlist_id="pl1",
        items=[_spotify_item("Strobe", "Deadmau5", 600, isrc="US1")],
        normalize=identity_normalize,
    )

    tracks = db.query(Track).all()
    assert len(tracks) == 1, "la traccia manuale non deve duplicarsi"
    assert report["created"] == 0 and report["updated"] == 1
    assert tracks[0].spotify_id == "spot1"  # ha guadagnato l'identità Spotify


def test_same_name_but_different_duration_is_not_merged(db):
    # Stesso artista+titolo ma durata molto diversa (es. intro 30s vs extended 10min):
    # NON è la stessa traccia, non va fusa.
    db.add(Track(source_type="manual", platform="manual", title="Intro", artist="X", duration_seconds=30))
    db.commit()

    import_playlist(
        db, platform="spotify", name="P", platform_playlist_id="pl1",
        items=[_spotify_item("Intro", "X", 600, track_id="s1")],
        normalize=identity_normalize,
    )

    assert db.query(Track).count() == 2, "durata troppo diversa → traccia distinta"
