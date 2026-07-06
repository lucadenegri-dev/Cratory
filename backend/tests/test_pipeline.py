"""pipeline_snapshot: conteggi DB + disco per la striscia di orientamento."""
import pytest

from app.core.config import settings
from app.services.pipeline import pipeline_snapshot


@pytest.fixture(autouse=True)
def _no_dirs(monkeypatch):
    """Default: nessuna cartella/URL configurati (i test che servono li impostano)."""
    monkeypatch.setattr(settings, "slskd_download_dir", "")
    monkeypatch.setattr(settings, "library_root", "")
    monkeypatch.setattr(settings, "organizer_url", "")


def test_snapshot_vuoto(db):
    snap = pipeline_snapshot(db)
    assert snap["total_tracks"] == 0
    assert snap["playlists"] == 0
    assert snap["download_active"] is False
    assert snap["inbox_files"] is None
    assert snap["files_on_disk"] is None
    assert snap["index_mismatch"] is None
    assert snap["last_index_at"] is None
    assert snap["organizer_url"] is None


def test_conteggi_db(db, seed_tracks):
    seed_tracks(10)
    snap = pipeline_snapshot(db)
    assert snap["total_tracks"] == 10
    assert snap["missing_key"] == 0   # il seed ha sempre la key
    assert snap["wishlist"] == 0      # il seed ha has_local_file=True
    assert snap["ready_for_set"] == 10


def test_inbox_conta_solo_file_audio(db, tmp_path, monkeypatch):
    (tmp_path / "a.mp3").write_bytes(b"x")
    (tmp_path / "b.flac").write_bytes(b"x")
    (tmp_path / "note.txt").write_bytes(b"x")
    monkeypatch.setattr(settings, "slskd_download_dir", str(tmp_path))
    assert pipeline_snapshot(db)["inbox_files"] == 2


def test_inbox_cartella_vuota(db, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "slskd_download_dir", str(tmp_path))
    assert pipeline_snapshot(db)["inbox_files"] == 0


def test_inbox_cartella_inesistente_e_neutra(db, monkeypatch):
    monkeypatch.setattr(settings, "slskd_download_dir", "/percorso/che/non/esiste")
    assert pipeline_snapshot(db)["inbox_files"] is None


def test_disallineamento_disco_db(db, seed_tracks, tmp_path, monkeypatch):
    seed_tracks(3)                          # 3 tracce possedute nel DB...
    (tmp_path / "a.mp3").write_bytes(b"x")  # ...ma 1 solo file su disco
    monkeypatch.setattr(settings, "library_root", str(tmp_path))
    snap = pipeline_snapshot(db)
    assert snap["files_on_disk"] == 1
    assert snap["index_mismatch"] is True


def test_disco_db_allineati(db, seed_tracks, tmp_path, monkeypatch):
    seed_tracks(2)
    (tmp_path / "a.mp3").write_bytes(b"x")
    (tmp_path / "b.mp3").write_bytes(b"x")
    monkeypatch.setattr(settings, "library_root", str(tmp_path))
    assert pipeline_snapshot(db)["index_mismatch"] is False


def test_organizer_url_esposto(db, monkeypatch):
    monkeypatch.setattr(settings, "organizer_url", "http://localhost:3100")
    assert pipeline_snapshot(db)["organizer_url"] == "http://localhost:3100"


def test_analyze_pending_counts_owned_without_features(db):
    from app.models import Track

    db.add(Track(source_type="spotify", has_local_file=True))
    db.add(Track(source_type="spotify", has_local_file=True, bpm=124.0, camelot_key="8A"))
    db.add(Track(source_type="spotify", has_local_file=False))
    db.commit()
    assert pipeline_snapshot(db)["analyze_pending"] == 1
