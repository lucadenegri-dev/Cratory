from app.services.inspector import inspect
from tests.conftest import make_audio_file


def _types(issues):
    return {(i.type, i.field) for i in issues}


def test_scan_error_only(make=make_audio_file):
    f = make(1, scan_error="corrotto", artist=None, title=None)
    issues = inspect([f])
    assert _types(issues) == {("scan_error", None)}
    assert issues[0].severity == "error"


def test_missing_artist_title():
    f = make_audio_file(1, artist="", title=None, genre="House", year=2020, label="X",
                        duration_s=200.0, bitrate=320000, ext="mp3")
    issues = inspect([f])
    assert ("missing_required_tag", "artist") in _types(issues)
    assert ("missing_required_tag", "title") in _types(issues)
    assert all(i.severity == "error" for i in issues if i.type == "missing_required_tag")


def test_missing_metadata():
    f = make_audio_file(1, artist="A", title="T", genre=None, year=None, label=None,
                        duration_s=200.0, bitrate=320000, path="/music/A - T.mp3")
    issues = inspect([f])
    assert {("missing_metadata", "genre"), ("missing_metadata", "year"),
            ("missing_metadata", "label")} <= _types(issues)


def test_casing_fix():
    f = make_audio_file(1, artist="PINCO PALLINO", title="Bel Titolo", genre="House",
                        year=2020, label="X", duration_s=200.0, bitrate=320000,
                        path="/music/PINCO PALLINO - Bel Titolo.mp3")
    issues = inspect([f])
    casing = [i for i in issues if i.type == "inconsistent_casing"]
    assert len(casing) == 1 and casing[0].field == "artist"
    assert casing[0].suggested_fix == {"field": "artist", "action": "retag",
                                       "from": "PINCO PALLINO", "to": "Pinco Pallino"}


def test_casing_ignores_single_word_stylized():
    f = make_audio_file(1, artist="deadmau5", title="Strobe", genre="House", year=2020,
                        label="X", duration_s=200.0, bitrate=320000,
                        path="/music/deadmau5 - Strobe.mp3")
    assert not [i for i in inspect([f]) if i.type == "inconsistent_casing"]


def test_junk_title_and_comment():
    f = make_audio_file(1, artist="A", title="Track 01", comment="ripped by xyz",
                        genre="House", year=2020, label="X", duration_s=200.0,
                        bitrate=320000, path="/music/A - Track 01.mp3")
    issues = inspect([f])
    assert ("junk_tag", "title") in _types(issues)
    assert ("junk_tag", "comment") in _types(issues)


def test_low_quality_and_duration():
    f = make_audio_file(1, artist="A", title="T", genre="House", year=2020, label="X",
                        ext="mp3", bitrate=128000, duration_s=5.0, path="/music/A - T.mp3")
    issues = inspect([f])
    assert ("low_quality", None) in _types(issues)
    assert ("suspicious_duration", None) in _types(issues)


def test_lossless_not_low_quality():
    f = make_audio_file(1, artist="A", title="T", genre="House", year=2020, label="X",
                        ext="flac", bitrate=1000, duration_s=200.0,
                        path="/music/A - T.flac")
    assert not [i for i in inspect([f]) if i.type == "low_quality"]


def test_filename_mismatch():
    f = make_audio_file(1, artist="Pinco", title="Titolo", genre="House", year=2020,
                        label="X", duration_s=200.0, bitrate=320000, path="/music/track03.mp3")
    assert ("filename_tag_mismatch", None) in _types(inspect([f]))
