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
    assert seen == [(1, 1, "scanning")]


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


def test_stat_failure_recorded_not_crash(db, copy_fixture, tmp_path):
    """Un file che sparisce dopo os.walk (stat fallisce con OSError) non crasha lo scan.

    Usa un broken symlink come trigger realistico: os.walk lo yielda ma
    os.path.getsize su di esso solleva FileNotFoundError (sottoclasse di OSError).
    Il test verifica che lo scan termini, che errors >= 1, che il file buono
    sia inserito, e che la riga rotta abbia scan_error != None.
    """
    import os as _os

    root_dir = tmp_path / "lib"
    root_dir.mkdir(parents=True, exist_ok=True)

    # File buono
    copy_fixture("flac", root_dir / "a.flac")

    # Broken symlink con estensione audio: os.walk lo yielda, os.path.getsize crasha
    ghost = root_dir / "ghost.mp3"
    _os.symlink("/nonexistent/target.mp3", ghost)

    root = ScanRoot(path=str(root_dir))
    db.add(root)
    db.commit()

    # Non deve sollevare eccezioni
    summary = scan(db, [root])

    assert summary.errors >= 1, "La riga con stat-failure deve essere conteggiata in errors"
    assert summary.found >= 2, "os.walk deve aver trovato almeno i 2 file (buono + ghost)"

    # Il file buono deve essere inserito
    good = db.scalar(select(AudioFile).where(AudioFile.path.like("%a.flac%")))
    assert good is not None and good.scan_error is None

    # La riga rotta deve esistere con scan_error valorizzato
    broken = db.scalar(select(AudioFile).where(AudioFile.path.like("%ghost%")))
    assert broken is not None, "La riga per ghost.mp3 deve essere inserita anche se rotta"
    assert broken.scan_error is not None, "scan_error deve descrivere il fallimento del stat"


def test_rescan_marks_missing(db, copy_fixture, tmp_path):
    root = _make_root(db, copy_fixture, tmp_path, [("a.flac", "flac")])
    scan(db, [root])
    (tmp_path / "lib" / "a.flac").unlink()
    summary = scan(db, [root])
    assert summary.missing == 1 and summary.inserted == 0
    row = db.scalar(select(AudioFile))
    assert row.status == "missing"


def test_rescan_reconciles_move(db, copy_fixture, tmp_path):
    root = _make_root(db, copy_fixture, tmp_path, [("a.flac", "flac")])
    scan(db, [root])
    original = db.scalar(select(AudioFile))
    original_id, first_seen = original.id, original.first_seen_at
    (tmp_path / "lib" / "a.flac").rename(tmp_path / "lib" / "b.flac")
    summary = scan(db, [root])
    assert summary.moved == 1 and summary.missing == 0 and summary.inserted == 0
    db.expire_all()
    rows = db.scalars(select(AudioFile)).all()
    assert len(rows) == 1
    assert rows[0].id == original_id
    assert rows[0].path.endswith("b.flac")
    assert rows[0].first_seen_at == first_seen
    assert rows[0].status == "present"


def test_scan_skips_quarantine_and_hidden_dirs(db, copy_fixture, tmp_path):
    """La .quarantine (creata dall'Apply per i DELETE) e le dir nascoste
    non devono rientrare nello scan: niente falsi 'nuovi file'."""
    root_dir = tmp_path / "lib"
    copy_fixture("mp3", root_dir / "a.mp3")
    copy_fixture("mp3", root_dir / ".quarantine" / "b.mp3")
    copy_fixture("mp3", root_dir / ".hidden" / "sub" / "c.mp3")
    root = ScanRoot(path=str(root_dir))
    db.add(root)
    db.commit()
    summary = scan(db, [root])
    assert summary.found == 1
    rows = db.scalars(select(AudioFile)).all()
    assert len(rows) == 1 and rows[0].path.endswith("a.mp3")


def test_scan_reads_isrc(db, copy_fixture, tmp_path):
    from mutagen.flac import FLAC

    root_dir = tmp_path / "lib"
    path = copy_fixture("flac", root_dir / "a.flac")
    audio = FLAC(path)
    audio["isrc"] = "DEAB12300123"
    audio.save()
    root = ScanRoot(path=str(root_dir))
    db.add(root)
    db.commit()
    scan(db, [root])
    row = db.scalar(select(AudioFile))
    assert row.isrc == "DEAB12300123"
