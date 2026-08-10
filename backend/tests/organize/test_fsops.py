import errno
import os

import pytest

from app.organize.integrations import fsops


def test_safe_move_renames(tmp_path):
    src = tmp_path / "a.txt"
    src.write_text("x")
    dst = tmp_path / "sub" / "b.txt"
    fsops.safe_move(str(src), str(dst))
    assert dst.read_text() == "x" and not src.exists()


def test_safe_move_refuses_existing_dst(tmp_path):
    src = tmp_path / "a.txt"; src.write_text("x")
    dst = tmp_path / "b.txt"; dst.write_text("y")
    with pytest.raises(fsops.FsOpError):
        fsops.safe_move(str(src), str(dst))
    assert src.exists() and dst.read_text() == "y"


def test_safe_move_allows_case_only_rename(tmp_path):
    # Su FS case-insensitive (APFS) la dest "esiste" perché È il file sorgente:
    # il rename di solo case deve passare, non essere rifiutato.
    src = tmp_path / "house" / "a - t.mp3"
    src.parent.mkdir()
    src.write_text("x")
    dst = tmp_path / "house" / "A - T.mp3"
    fsops.safe_move(str(src), str(dst))
    assert os.path.exists(str(dst))
    assert "A - T.mp3" in os.listdir(tmp_path / "house")


def test_quarantine_path_preserves_relpath(tmp_path):
    root = tmp_path / "lib"
    f = root / "House" / "x.mp3"
    f.parent.mkdir(parents=True)
    f.write_text("z")
    q = fsops.quarantine_path_for(str(f), str(root))
    assert q == str(root / ".quarantine" / "House" / "x.mp3")


def test_cleanup_removes_empty_chain_up_to_root(tmp_path):
    root = tmp_path / "lib"
    deep = root / "House" / "A"
    deep.mkdir(parents=True)
    removed = fsops.cleanup_empty_dirs([str(deep)], [str(root)])
    assert removed == 2
    assert not (root / "House").exists()
    assert root.exists()  # la radice non si tocca mai


def test_cleanup_stops_at_non_empty_dir(tmp_path):
    root = tmp_path / "lib"
    (root / "House" / "A").mkdir(parents=True)
    (root / "House" / "resta.mp3").write_text("x")
    fsops.cleanup_empty_dirs([str(root / "House" / "A")], [str(root)])
    assert not (root / "House" / "A").exists()
    assert (root / "House").exists()


def test_cleanup_treats_ds_store_as_empty(tmp_path):
    root = tmp_path / "lib"
    d = root / "House"
    d.mkdir(parents=True)
    (d / ".DS_Store").write_text("")
    fsops.cleanup_empty_dirs([str(d)], [str(root)])
    assert not d.exists()


def test_cleanup_ignores_dirs_outside_roots(tmp_path):
    fuori = tmp_path / "fuori"
    fuori.mkdir()
    assert fsops.cleanup_empty_dirs([str(fuori)], [str(tmp_path / "lib")]) == 0
    assert fuori.exists()


def test_cross_device_fallback(copy_fixture, tmp_path, monkeypatch):
    src = copy_fixture("flac", tmp_path / "a.flac")
    dst = tmp_path / "moved.flac"
    real_rename = os.rename

    def fake_rename(a, b):
        raise OSError(errno.EXDEV, "cross-device")
    monkeypatch.setattr(os, "rename", fake_rename)
    fsops.safe_move(src, str(dst))
    monkeypatch.setattr(os, "rename", real_rename)
    assert dst.exists() and not os.path.exists(src)
