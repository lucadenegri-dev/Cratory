from app.models import Track
from app.repositories import tracks_without_local_file
from app.services.acquisition import attach_local_file


def test_attach_local_file_sets_ownership_fields(db):
    t = Track(platform="spotify", spotify_id="s1", source_type="spotify",
              title="Da Funk", artist="Daft Punk", status="imported")
    db.add(t)
    db.commit()
    attach_local_file(db, t, path="/music/x.flac", fmt="flac", bitrate=1000)
    db.refresh(t)
    assert t.has_local_file is True
    assert t.local_path == "/music/x.flac"
    assert t.local_format == "flac"
    assert t.local_bitrate == 1000
    # lo status di enrichment NON viene toccato
    assert t.status == "imported"


def test_tracks_without_local_file_filters(db):
    from app.models import Playlist
    from app.repositories import add_track_to_playlist

    pl = Playlist(name="PL", platform="spotify", platform_playlist_id="pl1", kind="spotify")
    db.add(pl)
    db.commit()
    owned = Track(platform="spotify", spotify_id="o", source_type="spotify",
                  title="A", artist="X", has_local_file=True)
    missing = Track(platform="spotify", spotify_id="m", source_type="spotify",
                    title="B", artist="Y")
    db.add_all([owned, missing])
    db.commit()
    add_track_to_playlist(db, owned, pl)
    add_track_to_playlist(db, missing, pl)
    db.commit()
    result = tracks_without_local_file(db, pl.id)
    ids = {t.spotify_id for t in result}
    assert ids == {"m"}
