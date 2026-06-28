import errno
import os

import pytest

from app.integrations import fsops


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


def test_quarantine_path_preserves_relpath(tmp_path):
    root = tmp_path / "lib"
    f = root / "House" / "x.mp3"
    f.parent.mkdir(parents=True)
    f.write_text("z")
    q = fsops.quarantine_path_for(str(f), str(root))
    assert q == str(root / ".quarantine" / "House" / "x.mp3")


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
