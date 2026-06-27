from sqlalchemy import select

from app.models import AudioFile, ScanRoot
from app.services.scanner import scan


def _make_root(db, copy_fixture, tmp_path, files):
    root_dir = tmp_path / "lib"
    for name, fmt in files:
        copy_fixture(fmt, root_dir / name)
    root = ScanRoot(path=str(root_dir))
    db.add(root)
    db.commit()
    return root


def test_scan_inserts_rows(db, copy_fixture, tmp_path):
    root = _make_root(db, copy_fixture, tmp_path, [("a.mp3", "mp3"), ("b.flac", "flac")])
    summary = scan(db, [root])
    assert summary.found == 2 and summary.inserted == 2 and summary.updated == 0
    rows = db.scalars(select(AudioFile)).all()
    assert {r.ext for r in rows} == {"mp3", "flac"}
    assert all(r.status == "present" and r.content_hash for r in rows)


def test_progress_callback_called(db, copy_fixture, tmp_path):
    root = _make_root(db, copy_fixture, tmp_path, [("a.mp3", "mp3")])
    seen = []
    scan(db, [root], on_progress=lambda p, t, ph: seen.append((p, t, ph)))
    assert seen[-1] == (1, 1, "scanning")


def test_rescan_is_idempotent(db, copy_fixture, tmp_path):
    root = _make_root(db, copy_fixture, tmp_path, [("a.mp3", "mp3")])
    scan(db, [root])
    summary = scan(db, [root])
    assert summary.inserted == 0 and summary.updated == 1
    assert db.scalar(select(AudioFile)) is not None
    assert len(db.scalars(select(AudioFile)).all()) == 1


def test_unreadable_file_recorded_not_crash(db, copy_fixture, tmp_path):
    root_dir = tmp_path / "lib"
    copy_fixture("mp3", root_dir / "ok.mp3")
    (root_dir / "broken.mp3").write_bytes(b"non audio")
    root = ScanRoot(path=str(root_dir))
    db.add(root)
    db.commit()
    summary = scan(db, [root])
    assert summary.found == 2 and summary.errors == 1
    broken = db.scalar(select(AudioFile).where(AudioFile.path.like("%broken%")))
    assert broken.scan_error is not None
