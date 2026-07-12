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


def test_attach_salva_audio_hash(db, monkeypatch):
    from app.models import Track
    from app.services import acquisition

    monkeypatch.setattr(acquisition, "audio_hash", lambda p: "abc123")
    t = Track(source_type="spotify")
    db.add(t); db.commit()
    out = acquisition.attach_local_file(db, t, path="/x/y.mp3", fmt="mp3", bitrate=320)
    assert out.audio_hash == "abc123"
    assert out.has_local_file is True


def test_attach_salva_mtime_e_size(db, tmp_path, monkeypatch):
    """Il collegamento memorizza la firma del file (mtime+size): senza, il prossimo
    indice incrementale non puo' skipparlo e lo ri-hasha (decodifica ffmpeg)."""
    from app.services import acquisition

    monkeypatch.setattr(acquisition, "audio_hash", lambda p: "HMS")
    f = tmp_path / "song.mp3"
    f.write_bytes(b"finto audio")
    t = Track(source_type="spotify")
    db.add(t); db.commit()

    out = acquisition.attach_local_file(db, t, path=str(f), fmt="mp3", bitrate=320)

    stat = f.stat()
    assert out.local_mtime == stat.st_mtime
    assert out.local_size == stat.st_size


def test_attach_stat_fallito_non_blocca(db, monkeypatch):
    """File non stat-abile (path sparito tra download e attach): il possesso resta,
    la firma incrementale semplicemente non c'e'."""
    from app.services import acquisition

    monkeypatch.setattr(acquisition, "audio_hash", lambda p: "HNS")
    t = Track(source_type="spotify")
    db.add(t); db.commit()

    out = acquisition.attach_local_file(db, t, path="/non/esiste/y.mp3", fmt="mp3")

    assert out.has_local_file is True
    assert out.local_mtime is None
    assert out.local_size is None


def test_attach_hash_fallito_non_blocca(db, monkeypatch):
    from app.integrations.local_files import LocalFilesError
    from app.models import Track
    from app.services import acquisition

    def boom(p):
        raise LocalFilesError("ffmpeg assente")

    monkeypatch.setattr(acquisition, "audio_hash", boom)
    t = Track(source_type="spotify")
    db.add(t); db.commit()
    out = acquisition.attach_local_file(db, t, path="/x/y.mp3")
    assert out.has_local_file is True
    assert out.audio_hash is None
