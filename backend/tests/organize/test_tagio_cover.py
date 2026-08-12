import pytest

from app.organize.integrations import tagio

# JPEG minimale valido (header + EOI); mutagen non lo valida, basta come payload.
_JPG = bytes.fromhex("ffd8ffe000104a46494600010100000100010000ffd9")


@pytest.mark.parametrize("fmt", ["flac", "mp3", "m4a", "aiff", "wav"])
def test_write_then_detect_cover(copy_fixture, tmp_path, fmt):
    f = copy_fixture(fmt, tmp_path / f"a.{fmt}")
    assert tagio.read_tags(f).has_cover is False
    tagio.write_cover(f, _JPG)
    assert tagio.read_tags(f).has_cover is True


@pytest.mark.parametrize("fmt", ["flac", "mp3", "m4a", "aiff", "wav"])
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


@pytest.mark.parametrize("fmt", ["flac", "mp3", "m4a", "aiff", "wav"])
def test_read_cover_roundtrip(copy_fixture, tmp_path, fmt):
    f = copy_fixture(fmt, tmp_path / f"a.{fmt}")
    assert tagio.read_cover(f) is None       # fixture pulita
    tagio.write_cover(f, _JPG)
    assert tagio.read_cover(f) == _JPG


@pytest.mark.parametrize("fmt", ["flac", "mp3", "m4a", "aiff", "wav"])
def test_read_cover_after_remove(copy_fixture, tmp_path, fmt):
    f = copy_fixture(fmt, tmp_path / f"a.{fmt}")
    tagio.write_cover(f, _JPG)
    tagio.remove_cover(f)
    assert tagio.read_cover(f) is None


def test_read_cover_unreadable_file(tmp_path):
    """Un file che non è audio non deve sollevare: è semplicemente senza cover."""
    p = tmp_path / "nope.mp3"
    p.write_bytes(b"questo non e' audio")
    assert tagio.read_cover(str(p)) is None


def test_read_cover_missing_file(tmp_path):
    assert tagio.read_cover(str(tmp_path / "fantasma.flac")) is None
