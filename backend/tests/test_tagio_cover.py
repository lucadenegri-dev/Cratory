import pytest

from app.integrations import tagio

# JPEG minimale valido (header + EOI); mutagen non lo valida, basta come payload.
_JPG = bytes.fromhex("ffd8ffe000104a46494600010100000100010000ffd9")


@pytest.mark.parametrize("fmt", ["flac", "mp3", "m4a", "aiff"])
def test_write_then_detect_cover(copy_fixture, tmp_path, fmt):
    f = copy_fixture(fmt, tmp_path / f"a.{fmt}")
    assert tagio.read_tags(f).has_cover is False
    tagio.write_cover(f, _JPG)
    assert tagio.read_tags(f).has_cover is True


@pytest.mark.parametrize("fmt", ["flac", "mp3", "m4a", "aiff"])
def test_remove_cover(copy_fixture, tmp_path, fmt):
    f = copy_fixture(fmt, tmp_path / f"a.{fmt}")
    tagio.write_cover(f, _JPG)
    assert tagio.read_tags(f).has_cover is True
    tagio.remove_cover(f)
    assert tagio.read_tags(f).has_cover is False


def test_write_cover_preserves_text_tags(copy_fixture, tmp_path):
    f = copy_fixture("flac", tmp_path / "a.flac")
    tagio.write_tags(f, {"artist": "Pinco", "title": "Titolo"})
    tagio.write_cover(f, _JPG)
    tags = tagio.read_tags(f)
    assert tags.artist == "Pinco" and tags.title == "Titolo" and tags.has_cover
