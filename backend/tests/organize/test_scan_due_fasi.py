"""Uno scan solo produce l'indice dei file E le tracce."""

from sqlalchemy import select

from app.models import Track
from app.organize.models import AudioFile
from app.organize.services.roots import radici
from app.organize.services.scanner import scan


def test_uno_scan_produce_indice_e_tracce(db, fake_audio, monkeypatch):
    from app.core.config import settings

    make, root = fake_audio
    monkeypatch.setattr(settings, "library_root", str(root))
    monkeypatch.setattr(settings, "slskd_download_dir", "")
    make("Techno/N/N - New.mp3", digest="H7", artist="N", title="New")

    summary = scan(db, [radici(db)["library"]])
    db.commit()

    assert summary.inserted == 1
    assert len(db.scalars(select(AudioFile)).all()) == 1
    t = db.scalar(select(Track).where(Track.audio_hash == "H7"))
    assert t is not None
    assert summary.linking is not None and summary.linking["created"] == 1


def test_le_fasi_sono_riportate_al_progresso(db, fake_audio, monkeypatch):
    from app.core.config import settings

    make, root = fake_audio
    monkeypatch.setattr(settings, "library_root", str(root))
    monkeypatch.setattr(settings, "slskd_download_dir", "")
    make("Techno/N/N - New.mp3", digest="H7", artist="N", title="New")

    fasi = []
    scan(db, [radici(db)["library"]], on_progress=lambda p, t, phase: fasi.append(phase))
    db.commit()

    assert "scanning" in fasi
    assert "linking" in fasi


def test_il_secondo_scan_non_cambia_nulla(db, fake_audio, monkeypatch):
    """Idempotenza: è la milestone della fase."""
    from app.core.config import settings

    make, root = fake_audio
    monkeypatch.setattr(settings, "library_root", str(root))
    monkeypatch.setattr(settings, "slskd_download_dir", "")
    make("Techno/N/N - New.mp3", digest="H7", artist="N", title="New")

    scan(db, [radici(db)["library"]])
    db.commit()
    secondo = scan(db, [radici(db)["library"]])
    db.commit()

    assert secondo.inserted == 0
    assert secondo.linking["created"] == 0
    assert len(db.scalars(select(Track)).all()) == 1
    assert len(db.scalars(select(AudioFile)).all()) == 1
