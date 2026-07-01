"""Indicizzazione della libreria canonica (LIBRARY_ROOT)."""
import pytest

from app.core.config import Settings


def test_library_root_default_vuoto():
    s = Settings(_env_file=None)
    assert s.library_root == ""


@pytest.fixture()
def fake_audio(monkeypatch, tmp_path):
    """Crea file finti e monkeypatcha hash/tag/qualita' per renderli deterministici."""
    from app.services import library_index as li

    hashes: dict[str, str] = {}
    tags: dict[str, dict] = {}

    def make(rel: str, *, digest: str, artist=None, title=None, isrc=None):
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"x")
        hashes[str(p.resolve())] = digest
        tags[str(p.resolve())] = {
            "title": title, "artist": artist, "album": None, "year": None,
            "duration_seconds": 200, "isrc": isrc,
        }
        return p

    monkeypatch.setattr(li, "audio_hash", lambda p: hashes[str(p.resolve() if hasattr(p, 'resolve') else p)])
    monkeypatch.setattr(li, "read_tags", lambda p: tags[str(p.resolve() if hasattr(p, 'resolve') else p)])
    monkeypatch.setattr(li, "read_audio_quality", lambda p: {"format": "mp3", "bitrate": 320})
    return make, tmp_path


def test_riaggancio_per_audio_hash(db, fake_audio):
    """File rinominato/ritaggato: stesso hash ⇒ stessa Track, local_path aggiornato."""
    from app.models import Track
    from app.services.library_index import index_library

    make, root = fake_audio
    t = Track(source_type="spotify", spotify_id="s1", title="Origin", artist="A",
              has_local_file=True, local_path="/vecchio/inbox/file.mp3", audio_hash="H1")
    db.add(t); db.commit()

    make("Techno/A/A - Origin.mp3", digest="H1")
    report = index_library(db, root=root)

    db.refresh(t)
    assert report["relinked"] == 1 and report["created"] == 0
    assert t.local_path.endswith("A - Origin.mp3")
    assert t.has_local_file is True and t.local_format == "mp3"


def test_match_per_isrc_da_tag(db, fake_audio):
    from app.models import Track
    from app.services.library_index import index_library

    make, root = fake_audio
    t = Track(source_type="spotify", isrc="ISRC001", title="X", artist="A")
    db.add(t); db.commit()

    make("f.mp3", digest="H9", isrc="ISRC001")
    index_library(db, root=root)

    db.refresh(t)
    assert t.has_local_file is True and t.audio_hash == "H9"


def test_match_fuzzy_artista_titolo(db, fake_audio):
    from app.models import Track
    from app.services.library_index import index_library

    make, root = fake_audio
    t = Track(source_type="spotify", title="My Song", artist="Someone")
    db.add(t); db.commit()

    make("g.mp3", digest="H8", artist="someone", title="my song")
    index_library(db, root=root)

    db.refresh(t)
    assert t.has_local_file is True


def test_file_sconosciuto_crea_track_local_files(db, fake_audio):
    from sqlalchemy import select
    from app.models import Track
    from app.services.library_index import index_library

    make, root = fake_audio
    make("Techno/N/N - New.mp3", digest="H7", artist="N", title="New")
    report = index_library(db, root=root)

    assert report["created"] == 1
    t = db.scalar(select(Track).where(Track.audio_hash == "H7"))
    assert t is not None and t.source_type == "local_files"
    assert t.platform_track_id == "H7" and t.artist == "N"


def test_non_sovrascrive_identita_esistente(db, fake_audio):
    """I tag del file riempiono solo i campi vuoti (l'enrichment/manuale resta autorevole)."""
    from app.models import Track
    from app.services.library_index import index_library

    make, root = fake_audio
    t = Track(source_type="spotify", title="Titolo Corretto", artist="A",
              genre="Techno", audio_hash="H1")
    db.add(t); db.commit()

    make("f.mp3", digest="H1", artist="A", title="titolo sbagliato dal tag")
    index_library(db, root=root)

    db.refresh(t)
    assert t.title == "Titolo Corretto" and t.genre == "Techno"
