from app.organize.services.dedup import find_duplicates
from tests.organize.conftest import make_audio_file


def test_fuzzy_flac_plus_mp3_same_track():
    flac = make_audio_file(1, artist="Pinco", title="Song", ext="flac", bitrate=1000,
                           duration_s=200.0, content_hash="a")
    mp3 = make_audio_file(2, artist="pinco", title="song", ext="mp3", bitrate=320000,
                          duration_s=200.5, content_hash="b")
    groups = find_duplicates([flac, mp3])
    assert len(groups) == 1
    g = groups[0]
    assert g.member_ids == (1, 2)
    assert g.match_kind == "fuzzy"
    assert g.keeper_id == 1  # lossless vince


def test_duration_guard_splits_versions():
    radio = make_audio_file(1, artist="A", title="Song", ext="mp3", bitrate=320000,
                            duration_s=200.0, content_hash="a")
    extended = make_audio_file(2, artist="A", title="Song", ext="mp3", bitrate=320000,
                               duration_s=360.0, content_hash="b")
    assert find_duplicates([radio, extended]) == []


def test_distinct_markers_not_grouped():
    a = make_audio_file(1, artist="A", title="Song (Radio Edit)", ext="mp3",
                        duration_s=200.0, content_hash="a")
    b = make_audio_file(2, artist="A", title="Song (Extended Mix)", ext="mp3",
                        duration_s=200.0, content_hash="b")
    assert find_duplicates([a, b]) == []


def test_exact_fallback_untagged():
    a = make_audio_file(1, artist=None, title=None, ext="mp3", content_hash="same")
    b = make_audio_file(2, artist=None, title=None, ext="mp3", content_hash="same")
    groups = find_duplicates([a, b])
    assert len(groups) == 1 and groups[0].match_kind == "exact"
    assert groups[0].member_ids == (1, 2)


def test_keeper_precedence_bitrate_then_completeness():
    low = make_audio_file(1, artist="A", title="T", ext="mp3", bitrate=128000,
                          duration_s=200.0, content_hash="a")
    high = make_audio_file(2, artist="A", title="T", ext="mp3", bitrate=320000,
                           duration_s=200.0, content_hash="b")
    groups = find_duplicates([low, high])
    assert groups[0].keeper_id == 2  # bitrate più alto


def test_deterministic():
    a = make_audio_file(1, artist="A", title="T", ext="mp3", bitrate=320000,
                        duration_s=200.0, content_hash="a")
    b = make_audio_file(2, artist="A", title="T", ext="mp3", bitrate=320000,
                        duration_s=200.0, content_hash="b")
    assert find_duplicates([a, b]) == find_duplicates([b, a])
