"""Stato 'scartata': Track.archived e setting ARCHIVE_ROOT."""
import pytest

from app.core.config import Settings
from app.models import Track


def test_archived_default_false(db):
    t = Track(source_type="manual", title="T", artist="A")
    db.add(t); db.commit(); db.refresh(t)
    assert t.archived is False


def test_archive_root_default_vuoto():
    s = Settings(_env_file=None)
    assert s.archive_root == ""


@pytest.fixture()
def fake_audio(monkeypatch, tmp_path):
    """Stesso pattern di test_library_index.py: file finti, hash/tag deterministici."""
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


def test_file_in_archivio_scarta_la_traccia(db, fake_audio):
    from app.services.library_index import index_library

    make, root = fake_audio
    lib = root / "Libreria"; arc = root / "Archived"
    lib.mkdir(); arc.mkdir()
    t = Track(source_type="spotify", spotify_id="s1", title="T", artist="A",
              has_local_file=True, local_path="/inbox/vecchio.mp3", audio_hash="H1")
    db.add(t); db.commit()

    make("Archived/A - T.mp3", digest="H1")
    report = index_library(db, root=lib, archive_root=arc)

    db.refresh(t)
    assert report["archived"] == 1
    assert t.archived is True and t.has_local_file is False
    assert t.local_path.endswith("Archived/A - T.mp3")


def test_ritorno_in_libreria_riabilita(db, fake_audio):
    from app.services.library_index import index_library

    make, root = fake_audio
    lib = root / "Libreria"; arc = root / "Archived"
    lib.mkdir(); arc.mkdir()
    t = Track(source_type="spotify", spotify_id="s1", title="T", artist="A",
              archived=True, audio_hash="H1")
    db.add(t); db.commit()

    make("Libreria/Techno/A - T.mp3", digest="H1")
    index_library(db, root=lib, archive_root=arc)

    db.refresh(t)
    assert t.archived is False and t.has_local_file is True


def test_archivio_non_configurato_o_assente_neutro(db, fake_audio):
    from app.services.library_index import index_library

    make, root = fake_audio
    lib = root / "Libreria"; lib.mkdir()
    r1 = index_library(db, root=lib)                          # senza archive_root
    r2 = index_library(db, root=lib, archive_root=root / "non-esiste")
    assert r1["archived"] == 0 and r2["archived"] == 0


def test_file_ignoto_in_archivio_non_crea_tracce(db, fake_audio):
    """Un file mai visto da Cratory che scarti non e' una wishlist da ricordare."""
    from app.services.library_index import index_library

    make, root = fake_audio
    lib = root / "Libreria"; arc = root / "Archived"
    lib.mkdir(); arc.mkdir()
    make("Archived/Sconosciuto - Boh.mp3", digest="H-IGNOTO")
    report = index_library(db, root=lib, archive_root=arc)
    assert report["created"] == 0 and report["archived"] == 0


def test_archivio_incrementale_niente_rehash(db, fake_audio, monkeypatch):
    from app.services import library_index as li
    from app.services.library_index import index_library

    make, root = fake_audio
    lib = root / "Libreria"; arc = root / "Archived"
    lib.mkdir(); arc.mkdir()
    t = Track(source_type="spotify", spotify_id="s1", title="T", artist="A", audio_hash="H1")
    db.add(t); db.commit()
    make("Archived/A - T.mp3", digest="H1", artist="A", title="T")
    index_library(db, root=lib, archive_root=arc)  # primo run: hash + scarto

    calls = []
    original = li.audio_hash
    monkeypatch.setattr(li, "audio_hash", lambda p: calls.append(p) or original(p))
    report = index_library(db, root=lib, archive_root=arc)
    assert calls == [] and report["unchanged"] >= 1


def _mk(db, i, **kw):
    t = Track(source_type="spotify", spotify_id=f"x{i}", platform_track_id=f"x{i}",
              title=f"T{i}", artist=f"A{i}", **kw)
    db.add(t); db.commit()
    return t


def test_lista_esclude_scartate_di_default(db):
    from app.repositories import list_tracks
    _mk(db, 1)
    _mk(db, 2, archived=True)
    total, rows = list_tracks(db)
    assert total == 1 and rows[0].title == "T1"
    total, rows = list_tracks(db, archived=True)
    assert total == 1 and rows[0].title == "T2"


def test_coda_download_esclude_scartate(db):
    from app.models import Playlist, playlist_tracks
    from app.repositories import tracks_without_local_file
    p = Playlist(platform="manual", name="P"); db.add(p); db.commit()
    t1 = _mk(db, 1)
    t2 = _mk(db, 2, archived=True)
    db.execute(playlist_tracks.insert().values([
        {"playlist_id": p.id, "track_id": t1.id},
        {"playlist_id": p.id, "track_id": t2.id}]))
    db.commit()
    assert [t.id for t in tracks_without_local_file(db, p.id)] == [t1.id]


def test_pipeline_wishlist_esclude_scartate(db, monkeypatch):
    from app.core.config import settings
    from app.services.pipeline import pipeline_snapshot
    monkeypatch.setattr(settings, "slskd_download_dir", "")
    monkeypatch.setattr(settings, "library_root", "")
    monkeypatch.setattr(settings, "organizer_url", "")
    _mk(db, 1)
    _mk(db, 2, archived=True)
    snap = pipeline_snapshot(db)
    assert snap["wishlist"] == 1
    assert snap["archived_count"] == 1