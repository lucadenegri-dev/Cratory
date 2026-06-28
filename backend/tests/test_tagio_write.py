from app.integrations import tagio
from app.integrations.content_hash import compute


def test_write_then_read(copy_fixture, tmp_path):
    f = copy_fixture("flac", tmp_path / "a.flac")
    tagio.write_tags(f, {"artist": "Pinco", "title": "Titolo"})
    tags = tagio.read_tags(f)
    assert tags.artist == "Pinco" and tags.title == "Titolo"


def test_content_hash_stable_after_write(copy_fixture, tmp_path):
    f = copy_fixture("flac", tmp_path / "a.flac")
    before = compute(f, ".flac")[0]
    tagio.write_tags(f, {"artist": "Nuovo Artista"})
    assert compute(f, ".flac")[0] == before  # hash dello stream invariato


def test_clear_field(copy_fixture, tmp_path):
    f = copy_fixture("flac", tmp_path / "a.flac")
    tagio.write_tags(f, {"artist": "X"})
    tagio.write_tags(f, {"artist": None})
    assert tagio.read_tags(f).artist is None
