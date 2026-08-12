"""Backfill di location, track_id e primary_file_id sui dati esistenti."""

import pytest
from sqlalchemy import select

from app.models import Track
from app.organize.models import AudioFile, ScanRoot
from app.tools.backfill_track_files import backfill

LIB = "/lib"
INBOX = "/inbox"


@pytest.fixture()
def dati(db):
    r = ScanRoot(path=LIB)
    db.add(r)
    db.flush()
    files = [
        AudioFile(root_id=r.id, path=f"{LIB}/a.flac", ext=".flac", size_bytes=1,
                  hash_method="stream", status="present"),
        AudioFile(root_id=r.id, path=f"{LIB}/b.flac", ext=".flac", size_bytes=1,
                  hash_method="stream", status="present"),
        AudioFile(root_id=r.id, path=f"{INBOX}/c.mp3", ext=".mp3", size_bytes=1,
                  hash_method="stream", status="present"),
    ]
    db.add_all(files)
    # Solo il primo file ha una traccia che lo rivendica.
    db.add(Track(source_type="manual", has_local_file=True, local_path=f"{LIB}/a.flac"))
    db.commit()
    return files


def test_dry_run_non_scrive(db, dati):
    report = backfill(db, library_root=LIB, inbox_root=INBOX, dry_run=True)
    assert report.ok()
    assert report.agganciati == 1

    # backfill() ha già fatto rollback: rileggendo si torna allo stato
    # committato dalla fixture.
    assert db.scalars(select(AudioFile.track_id)).all() == [None, None, None]


def test_backfill_assegna_location_e_agganci(db, dati):
    report = backfill(db, library_root=LIB, inbox_root=INBOX, dry_run=False)
    db.commit()

    assert report.location_library == 2
    assert report.location_inbox == 1
    assert report.location_fuori == 0
    assert report.agganciati == 1
    assert report.primary == report.agganciati  # simmetria

    a = db.scalar(select(AudioFile).where(AudioFile.path == f"{LIB}/a.flac"))
    t = db.scalar(select(Track).where(Track.local_path == f"{LIB}/a.flac"))
    assert a.track_id == t.id
    assert t.primary_file_id == a.id
    assert a.location == "library"


def test_un_path_fuori_dalle_radici_fa_fallire(db, dati):
    db.add(AudioFile(root_id=dati[0].root_id, path="/altrove/x.flac", ext=".flac",
                     size_bytes=1, hash_method="stream", status="present"))
    db.commit()

    report = backfill(db, library_root=LIB, inbox_root=INBOX, dry_run=True)
    assert report.location_fuori == 1
    assert not report.ok()
