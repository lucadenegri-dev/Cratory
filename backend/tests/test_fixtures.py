import pytest

from mutagen import File as MutagenFile


@pytest.mark.parametrize("fmt", ["mp3", "flac", "wav", "aiff", "m4a"])
def test_fixture_is_readable_audio(fixture_path, fmt):
    mf = MutagenFile(fixture_path(fmt))
    assert mf is not None
    assert 0.5 < mf.info.length < 1.5
