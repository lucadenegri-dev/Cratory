"""Lo scanner deve derivare `location`, non lasciarla al default del modello.

Senza questo, ogni file scansionato dopo il backfill nasce con location="inbox"
anche se sta in LIBRARY_ROOT: il campo si degrada in silenzio a partire dal
primo scan.
"""

import pytest
from sqlalchemy import select

from app.organize.models import AudioFile, ScanRoot
from app.organize.services import scanner


@pytest.fixture()
def radici(tmp_path, monkeypatch):
    """Due cartelle vere, configurate come le radici di Settings."""
    library = tmp_path / "Library"
    inbox = tmp_path / "Downloads"
    library.mkdir()
    inbox.mkdir()
    from app.core.config import settings
    monkeypatch.setattr(settings, "library_root", str(library))
    monkeypatch.setattr(settings, "slskd_download_dir", str(inbox))
    return library, inbox


def _mp3(dirpath, nome: str):
    p = dirpath / nome
    p.write_bytes(b"ID3" + b"\x00" * 200)
    return p


def test_file_in_library_nasce_con_location_library(db, radici, monkeypatch):
    library, _ = radici
    _mp3(library, "a.mp3")

    root = ScanRoot(path=str(library))
    db.add(root)
    db.commit()

    scanner.scan(db, [root])
    db.commit()

    f = db.scalar(select(AudioFile).where(AudioFile.path.like(f"{library}%")))
    assert f is not None
    assert f.location == "library"


def test_file_in_inbox_nasce_con_location_inbox(db, radici):
    _, inbox = radici
    _mp3(inbox, "b.mp3")

    root = ScanRoot(path=str(inbox))
    db.add(root)
    db.commit()

    scanner.scan(db, [root])
    db.commit()

    f = db.scalar(select(AudioFile).where(AudioFile.path.like(f"{inbox}%")))
    assert f is not None
    assert f.location == "inbox"
