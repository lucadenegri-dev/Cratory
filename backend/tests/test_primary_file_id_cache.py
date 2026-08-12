"""primary_file_id è la cache che dice DA QUALE file vengono i local_*.

Non basta che l'helper funzioni: va verificato che l'indicizzazione vera lo
chiami, perché è il percorso che nella pratica scrive i local_*.
"""

import pytest
from sqlalchemy import select

from app.models import Track
from app.organize.models import AudioFile, ScanRoot
from app.services.library_index import index_library


@pytest.fixture()
def fake_audio(monkeypatch, tmp_path):
    """Stessa forma della fixture in test_library_index.py."""
    from app.services import library_index as li

    hashes: dict[str, str] = {}
    tags: dict[str, dict] = {}

    def make(rel: str, *, digest: str, artist=None, title=None):
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"x")
        hashes[str(p.resolve())] = digest
        tags[str(p.resolve())] = {
            "title": title, "artist": artist, "album": None, "year": None,
            "duration_seconds": 200, "isrc": None, "genre": None, "label": None,
        }
        return p

    monkeypatch.setattr(li, "audio_hash", lambda p: hashes[str(p.resolve() if hasattr(p, "resolve") else p)])
    monkeypatch.setattr(li, "read_tags", lambda p: tags[str(p.resolve() if hasattr(p, "resolve") else p)])
    monkeypatch.setattr(li, "read_audio_quality", lambda p: {"format": "mp3", "bitrate": 320})
    return make, tmp_path


def test_indicizzazione_aggancia_il_file_gia_scansionato(db, fake_audio):
    """Se Organize ha già indicizzato quel path, l'indicizzazione libreria
    deve agganciare le due facce della relazione."""
    make, root = fake_audio
    p = make("a.mp3", digest="d1", artist="A", title="B")

    radice = ScanRoot(path=str(root))
    db.add(radice)
    db.flush()
    f = AudioFile(root_id=radice.id, path=str(p.resolve()), ext=".mp3", size_bytes=1,
                  hash_method="stream", status="present", location="library")
    db.add(f)
    db.commit()

    index_library(db, root=root)

    track = db.scalar(select(Track).where(Track.local_path == str(p.resolve())))
    assert track is not None
    assert track.primary_file_id == f.id
    assert db.get(AudioFile, f.id).track_id == track.id


def test_file_sparito_azzera_primary_file_id(db, fake_audio):
    """La spazzata dei file persi deve togliere anche il puntatore al file.

    Serve un SECONDO file che resta: con la radice svuotata scatta il guard
    anti-unmount (`if not files: return`), che di proposito non azzera nessun
    possesso — un disco smontato non deve cancellare la libreria.
    """
    make, root = fake_audio
    p = make("a.mp3", digest="d1", artist="A", title="B")
    make("resta.mp3", digest="d2", artist="C", title="D")

    radice = ScanRoot(path=str(root))
    db.add(radice)
    db.flush()
    f = AudioFile(root_id=radice.id, path=str(p.resolve()), ext=".mp3", size_bytes=1,
                  hash_method="stream", status="present", location="library")
    db.add(f)
    db.commit()

    index_library(db, root=root)
    track = db.scalar(select(Track).where(Track.local_path == str(p.resolve())))
    assert track.primary_file_id == f.id

    # La traccia è referenziata da una playlist: sopravvive come lead invece di
    # essere cancellata come orfana.
    from app.models import Playlist, playlist_tracks
    pl = Playlist(platform="spotify", name="P")
    db.add(pl)
    db.flush()
    db.execute(playlist_tracks.insert().values(playlist_id=pl.id, track_id=track.id))
    db.commit()

    p.unlink()
    index_library(db, root=root)

    db.refresh(track)
    assert track.has_local_file is False
    assert track.primary_file_id is None
