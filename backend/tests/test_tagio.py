import pytest
from mutagen import File as MutagenFile
from mutagen.flac import FLAC

from app.integrations import tagio


def test_read_info_flac(copy_fixture, tmp_path):
    f = copy_fixture("flac", tmp_path / "a.flac")
    info = tagio.read_info(f)
    assert info.sample_rate == 44100
    assert info.channels == 2
    assert 0.5 < info.duration_s < 1.5


def test_read_tags_roundtrip(copy_fixture, tmp_path):
    f = copy_fixture("flac", tmp_path / "a.flac")
    audio = FLAC(f)
    audio["artist"] = "Pinco Pallino"
    audio["title"] = "Titolo"
    audio["date"] = "2020"
    audio["tracknumber"] = "3"
    audio.save()
    tags = tagio.read_tags(f)
    assert tags.artist == "Pinco Pallino"
    assert tags.title == "Titolo"
    assert tags.year == 2020
    assert tags.track_no == 3


def test_empty_fixture_has_no_required_tags(copy_fixture, tmp_path):
    f = copy_fixture("wav", tmp_path / "a.wav")
    tags = tagio.read_tags(f)
    assert tags.artist is None and tags.title is None


def test_corrupt_file_raises(tmp_path):
    bad = tmp_path / "bad.mp3"
    bad.write_bytes(b"questo non e' audio")
    with pytest.raises(tagio.TagReadError):
        tagio.read_info(str(bad))


def test_read_isrc_flac(copy_fixture, tmp_path):
    f = copy_fixture("flac", tmp_path / "a.flac")
    audio = FLAC(f)
    audio["isrc"] = "DEAB12300123"
    audio.save()
    assert tagio.read_tags(f).isrc == "DEAB12300123"


def test_read_isrc_mp3(copy_fixture, tmp_path):
    f = copy_fixture("mp3", tmp_path / "a.mp3")
    audio = MutagenFile(f, easy=True)
    if audio.tags is None:
        audio.add_tags()
    audio["isrc"] = "DEAB12300123"  # EasyID3: 'isrc' -> frame TSRC
    audio.save()
    assert tagio.read_tags(f).isrc == "DEAB12300123"


def test_missing_isrc_is_none(copy_fixture, tmp_path):
    f = copy_fixture("flac", tmp_path / "a.flac")
    assert tagio.read_tags(f).isrc is None
