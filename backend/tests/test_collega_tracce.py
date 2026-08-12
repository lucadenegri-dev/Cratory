"""Fase 2: l'aggancio parte dalle righe AudioFile, non da una camminata sul disco."""

import pytest
from sqlalchemy import select

from app.models import Track
from app.organize.models import AudioFile
from app.organize.services.roots import radici
from app.services.library_index import collega_tracce


@pytest.fixture(autouse=True)
def _radici_configurate(monkeypatch, tmp_path):
    """`radici()` non produce la chiave per una cartella non configurata (vedi
    `app/organize/services/roots.py`); il conftest radice azzera library_root
    (`_no_real_library_scan`) per non far scattare uno scan vero. Qui serve
    solo che le due chiavi esistano — i path non devono combaciare coi file
    di `fake_audio`, `_riga` scrive la location esplicitamente."""
    from app.core.config import settings
    monkeypatch.setattr(settings, "library_root", str(tmp_path / "Library"))
    monkeypatch.setattr(settings, "slskd_download_dir", str(tmp_path / "Inbox"))


def _riga(db, path: str, *, location: str = "library") -> AudioFile:
    f = AudioFile(root_id=radici(db)[location].id, path=path, ext=".mp3", size_bytes=1,
                  hash_method="stream", status="present", location=location)
    db.add(f)
    db.flush()
    return f


def test_crea_la_traccia_partendo_dalla_riga(db, fake_audio):
    make, _root = fake_audio
    p = make("Techno/N/N - New.mp3", digest="H7", artist="N", title="New")
    _riga(db, str(p.resolve()))
    db.commit()

    report = collega_tracce(db)

    assert report["created"] == 1
    t = db.scalar(select(Track).where(Track.audio_hash == "H7"))
    assert t is not None and t.source_type == "local_files"


def test_non_guarda_i_file_dell_inbox(db, fake_audio):
    """La fase 2 aggancia solo la libreria: un file in inbox non è una traccia."""
    make, _root = fake_audio
    p = make("pack/x.mp3", digest="H8", artist="X", title="X")
    _riga(db, str(p.resolve()), location="inbox")
    db.commit()

    report = collega_tracce(db)

    assert report["created"] == 0
    assert db.scalars(select(Track)).all() == []


def test_non_guarda_un_file_marcato_missing(db, fake_audio):
    make, _root = fake_audio
    p = make("Techno/N/N - Gone.mp3", digest="H9", artist="N", title="Gone")
    f = _riga(db, str(p.resolve()))
    f.status = "missing"
    db.commit()

    assert collega_tracce(db)["created"] == 0


def test_e_idempotente(db, fake_audio):
    make, _root = fake_audio
    p = make("Techno/N/N - New.mp3", digest="H7", artist="N", title="New")
    _riga(db, str(p.resolve()))
    db.commit()

    collega_tracce(db)
    db.commit()
    secondo = collega_tracce(db)

    assert secondo["created"] == 0
    assert len(db.scalars(select(Track)).all()) == 1


def test_aggancia_la_riga_alla_traccia(db, fake_audio):
    """L'invariante di F3a deve reggere anche passando dalla fase 2."""
    make, _root = fake_audio
    p = make("Techno/N/N - New.mp3", digest="H7", artist="N", title="New")
    f = _riga(db, str(p.resolve()))
    db.commit()

    collega_tracce(db)
    db.commit()

    db.refresh(f)
    t = db.scalar(select(Track).where(Track.audio_hash == "H7"))
    assert f.track_id == t.id
    assert t.primary_file_id == f.id
