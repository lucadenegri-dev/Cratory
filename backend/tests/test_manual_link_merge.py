"""Il collegamento manuale di un file deve fondere l'eventuale traccia gia'
indicizzata per lo stesso file, invece di lasciare un doppione."""
from app.models import Playlist, Track
from app.repositories import add_track_to_playlist, tracks_for_playlist
from app.services import acquisition


def test_link_manuale_fonde_il_duplicato_indicizzato(db, tmp_path, monkeypatch):
    f = tmp_path / "song.mp3"; f.write_bytes(b"x")
    monkeypatch.setattr(acquisition, "audio_hash", lambda p: "HDUP")
    monkeypatch.setattr(acquisition, "read_audio_quality", lambda p: {"format": "mp3", "bitrate": 320})

    # Il file e' gia' stato indicizzato come traccia local_files (con BPM da Rekordbox).
    indexed = Track(source_type="local_files", title="Song (Original Mix)", artist="A",
                    has_local_file=True, local_path=str(f), audio_hash="HDUP", bpm=128.0)
    # Il lead Spotify che l'utente collega a mano a quel file.
    lead = Track(source_type="spotify", spotify_id="s1", title="Song", artist="A",
                 isrc="I1", has_local_file=False)
    db.add_all([indexed, lead]); db.flush()
    pl = Playlist(platform="spotify", name="P"); db.add(pl); db.flush()
    add_track_to_playlist(db, lead, pl); db.commit()

    result = acquisition.link_local_file(db, lead, path=str(f))

    assert db.query(Track).count() == 1                  # niente doppione
    assert result.id == lead.id and result.has_local_file is True
    assert result.audio_hash == "HDUP"
    assert result.bpm == 128.0                           # backfill dal file indicizzato
    assert result.spotify_id == "s1" and result.isrc == "I1"
    assert result in tracks_for_playlist(db, pl.id)
