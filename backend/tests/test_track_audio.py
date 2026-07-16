"""Player tracce possedute: sicurezza del path e endpoint di streaming."""
from pathlib import Path

from app.services.file_search import path_within_roots


def test_path_within_roots_accetta_file_dentro_la_root(tmp_path):
    f = tmp_path / "song.mp3"
    f.write_bytes(b"x")
    assert path_within_roots(f, [str(tmp_path)]) is True


def test_path_within_roots_rifiuta_file_fuori_dalla_root(tmp_path):
    root = tmp_path / "library"
    root.mkdir()
    outside = tmp_path / "secret.mp3"
    outside.write_bytes(b"x")
    assert path_within_roots(outside, [str(root)]) is False


def test_path_within_roots_rifiuta_traversal(tmp_path):
    root = tmp_path / "library"
    root.mkdir()
    outside = tmp_path / "secret.mp3"
    outside.write_bytes(b"x")
    traversal = root / ".." / "secret.mp3"
    assert path_within_roots(traversal, [str(root)]) is False


def test_path_within_roots_rifiuta_symlink_verso_esterno(tmp_path):
    root = tmp_path / "library"
    root.mkdir()
    outside = tmp_path / "secret.mp3"
    outside.write_bytes(b"x")
    link = root / "link.mp3"
    link.symlink_to(outside)
    assert path_within_roots(link, [str(root)]) is False


def test_path_within_roots_con_roots_vuota_e_falso(tmp_path):
    f = tmp_path / "song.mp3"
    f.write_bytes(b"x")
    assert path_within_roots(f, []) is False
