"""Scanner incrementale (F4 Task 3b): il segnale (path, size_bytes, mtime) evita
di rileggere/rihashare un file invariato a ogni corsa.

Ogni test qui usa file VERI su disco (via `copy_fixture`), non `fake_audio`
(che monkeypatcha l'hash): è esattamente `content_hash.compute` che si vuole
misurare, quindi serve un file reale con mtime e size manipolabili.
"""

import os

from sqlalchemy import select

from app.core.config import settings
from app.organize.integrations import content_hash
from app.organize.models import AudioFile, ScanRoot
from app.organize.services.scanner import scan


def _make_root(db, copy_fixture, tmp_path, files, monkeypatch):
    """Stesso helper di test_scanner.py: la cartella ad hoc deve coincidere con
    LIBRARY_ROOT, altrimenti la riga scritta userebbe un root_id diverso da
    quello della ScanRoot creata qui sotto (vedi scan(): root percorsa vs
    root derivata da location)."""
    root_dir = tmp_path / "lib"
    monkeypatch.setattr(settings, "library_root", str(root_dir))
    for name, fmt in files:
        copy_fixture(fmt, root_dir / name)
    root = ScanRoot(path=str(root_dir))
    db.add(root)
    db.commit()
    return root


def _spy_compute(monkeypatch):
    """Sostituisce content_hash.compute con una spia che conta le chiamate ma
    delega al vero compute: si vuole osservare SE viene chiamato, non
    stravolgere il comportamento dello scan."""
    calls: list[str] = []
    original = content_hash.compute

    def spy(path, ext):
        calls.append(path)
        return original(path, ext)

    monkeypatch.setattr(content_hash, "compute", spy)
    return calls


def test_seconda_corsa_non_rilegge_file_invariati(db, copy_fixture, tmp_path, monkeypatch):
    root = _make_root(db, copy_fixture, tmp_path, [("a.mp3", "mp3"), ("b.flac", "flac")], monkeypatch)
    scan(db, [root])

    calls = _spy_compute(monkeypatch)
    summary = scan(db, [root])

    assert calls == [], "nessun file invariato deve richiamare content_hash.compute"
    assert summary.unchanged == 2
    assert summary.inserted == 0 and summary.updated == 0


def test_mtime_cambiato_forza_rilettura(db, copy_fixture, tmp_path, monkeypatch):
    root = _make_root(db, copy_fixture, tmp_path, [("a.mp3", "mp3")], monkeypatch)
    scan(db, [root])

    path = tmp_path / "lib" / "a.mp3"
    st = os.stat(path)
    os.utime(path, (st.st_atime, st.st_mtime + 1000))

    calls = _spy_compute(monkeypatch)
    summary = scan(db, [root])

    assert len(calls) == 1
    assert summary.unchanged == 0 and summary.updated == 1


def test_dimensione_cambiata_forza_rilettura(db, copy_fixture, tmp_path, monkeypatch):
    root = _make_root(db, copy_fixture, tmp_path, [("a.mp3", "mp3")], monkeypatch)
    scan(db, [root])

    path = tmp_path / "lib" / "a.mp3"
    st_before = os.stat(path)
    with open(path, "ab") as fh:
        fh.write(b"\x00" * 5000)
    # Isola l'effetto size dall'effetto mtime: ripristina l'mtime originale
    # dopo la scrittura, così a cambiare è SOLO size_bytes.
    os.utime(path, (st_before.st_atime, st_before.st_mtime))

    calls = _spy_compute(monkeypatch)
    summary = scan(db, [root])

    assert len(calls) == 1
    assert summary.unchanged == 0 and summary.updated == 1


def test_scan_error_viene_ritentato_anche_se_invariato(db, copy_fixture, tmp_path, monkeypatch):
    root = _make_root(db, copy_fixture, tmp_path, [("a.mp3", "mp3")], monkeypatch)
    scan(db, [root])
    row = db.scalar(select(AudioFile))
    row.scan_error = "errore di una corsa precedente"
    db.commit()

    calls = _spy_compute(monkeypatch)
    summary = scan(db, [root])

    assert len(calls) == 1, "una riga con scan_error va ritentata, non saltata per sempre"
    assert summary.unchanged == 0 and summary.updated == 1
    db.expire_all()
    row = db.scalar(select(AudioFile))
    assert row.scan_error is None


def test_file_saltato_non_diventa_missing(db, copy_fixture, tmp_path, monkeypatch):
    """L'invariante che protegge dal difetto più pericoloso del task: un file
    che prende il ramo di skip deve comunque risultare "visto" da
    seen_by_root, altrimenti _reconcile lo dichiara missing."""
    root = _make_root(db, copy_fixture, tmp_path, [("a.mp3", "mp3")], monkeypatch)
    scan(db, [root])
    summary = scan(db, [root])

    assert summary.unchanged == 1
    assert summary.missing == 0
    db.expire_all()
    row = db.scalar(select(AudioFile))
    assert row.status == "present"


def test_riga_con_mtime_null_viene_riletta(db, copy_fixture, tmp_path, monkeypatch):
    """Prima corsa dopo la migrazione: una riga pre-esistente con mtime NULL
    (mai scritta da questo meccanismo) va riletta anche se size_bytes combacia."""
    root = _make_root(db, copy_fixture, tmp_path, [("a.mp3", "mp3")], monkeypatch)
    scan(db, [root])
    row = db.scalar(select(AudioFile))
    row.mtime = None
    db.commit()

    calls = _spy_compute(monkeypatch)
    summary = scan(db, [root])

    assert len(calls) == 1
    assert summary.unchanged == 0 and summary.updated == 1
