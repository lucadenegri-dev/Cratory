"""File-browser confinato alla root: elenco sottocartelle, blocco fuori-root."""

import pytest

from app.services.fs_browse import FsBrowseError, browse


def test_browse_elenca_sottocartelle_e_conta_audio(tmp_path):
    (tmp_path / "house").mkdir()
    (tmp_path / "techno").mkdir()
    (tmp_path / "house" / "a.mp3").write_bytes(b"x")
    (tmp_path / "house" / "b.flac").write_bytes(b"x")
    (tmp_path / "house" / "cover.jpg").write_bytes(b"x")
    res = browse(None, root=tmp_path)
    by_name = {d["name"]: d for d in res["dirs"]}
    assert set(by_name) == {"house", "techno"}
    assert by_name["house"]["audio_file_count"] == 2
    assert by_name["techno"]["audio_file_count"] == 0
    assert res["parent_path"] is None  # alla root non si sale


def test_browse_naviga_in_sottocartella(tmp_path):
    sub = tmp_path / "house"
    sub.mkdir()
    (sub / "deep").mkdir()
    res = browse(str(sub), root=tmp_path)
    assert res["current_path"] == str(sub.resolve())
    assert res["parent_path"] == str(tmp_path.resolve())
    assert [d["name"] for d in res["dirs"]] == ["deep"]


def test_browse_blocca_path_fuori_root(tmp_path):
    outside = tmp_path.parent
    with pytest.raises(FsBrowseError):
        browse(str(outside), root=tmp_path / "sub")


def test_browse_blocca_traversal(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    with pytest.raises(FsBrowseError):
        browse(str(root / ".." / ".."), root=root)


def test_browse_blocca_symlink_fuori_root(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    secret = tmp_path / "secret"
    secret.mkdir()
    link = root / "link"
    link.symlink_to(secret)
    with pytest.raises(FsBrowseError):
        browse(str(link), root=root)


def test_browse_path_inesistente_solleva(tmp_path):
    with pytest.raises(FsBrowseError):
        browse(str(tmp_path / "nope"), root=tmp_path)
