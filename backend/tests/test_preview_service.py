from app.services.preview import (
    PreviewResult,
    extract_youtube_videos,
    itunes_hit,
    norm_tokens,
    parse_youtube_id,
    pick_video,
    resolve_preview,
)


def test_parse_youtube_id_watch_and_short():
    assert parse_youtube_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert parse_youtube_id("https://youtu.be/dQw4w9WgXcQ?t=5") == "dQw4w9WgXcQ"
    assert parse_youtube_id("https://example.com/x") is None


def test_extract_youtube_videos_maps_fields():
    payload = {"videos": [
        {"uri": "https://www.youtube.com/watch?v=aaaaaaaaaaa", "title": "Foo - Bar", "duration": 214},
        {"uri": "https://vimeo.com/1", "title": "skip", "duration": 10},
    ]}
    out = extract_youtube_videos(payload)
    assert out == [{"youtube_video_id": "aaaaaaaaaaa", "title": "Foo - Bar", "duration_seconds": 214}]


def test_norm_tokens_strips_noise():
    assert norm_tokens("Track Name (Original Mix)") == {"track", "name"}


def test_itunes_hit_matches_by_title_tokens():
    results = [
        {"trackName": "Other Song", "artistName": "A", "previewUrl": "http://a", "trackViewUrl": "http://va"},
        {"trackName": "Never Gonna Give You Up", "artistName": "Rick Astley", "previewUrl": "http://p", "trackViewUrl": "http://v"},
    ]
    hit = itunes_hit(results, "Never Gonna Give You Up")
    assert hit["previewUrl"] == "http://p"


def test_itunes_hit_skips_results_without_preview_url():
    results = [{"trackName": "Never Gonna Give You Up", "artistName": "R", "previewUrl": None}]
    assert itunes_hit(results, "Never Gonna Give You Up") is None


def test_itunes_hit_none_when_no_title_match():
    results = [{"trackName": "Totally Different", "previewUrl": "http://p"}]
    assert itunes_hit(results, "Never Gonna Give You Up") is None


def test_pick_video_track_level_fuzzy_match():
    videos = [
        {"youtube_video_id": "v1", "title": "Artist - Acid Trip (Original Mix)", "duration_seconds": 300},
        {"youtube_video_id": "v2", "title": "Artist - Other Track", "duration_seconds": 200},
    ]
    got = pick_video(videos, "Acid Trip", level="track")
    assert got["youtube_video_id"] == "v1"


def test_pick_video_release_level_takes_first():
    videos = [
        {"youtube_video_id": "v1", "title": "whatever", "duration_seconds": 1},
        {"youtube_video_id": "v2", "title": "second", "duration_seconds": 2},
    ]
    got = pick_video(videos, "Titolo Release", level="release")
    assert got["youtube_video_id"] == "v1"


def test_pick_video_none_when_empty():
    assert pick_video([], "x", level="track") is None
    assert pick_video([{"youtube_video_id": "v", "title": "zzz"}], "abc", level="track") is None


def test_pick_video_rejects_wrong_track_sharing_only_stopword():
    videos = [{"youtube_video_id": "v1", "title": "Artist - The Return", "duration_seconds": 200}]
    # "The Journey" and "The Return" share only the stopword "the" -> no match
    assert pick_video(videos, "The Journey", level="track") is None


def test_resolve_preview_itunes_first():
    def fake_itunes(term):
        return [{"trackName": "Acid Trip", "artistName": "Artist", "previewUrl": "http://p", "trackViewUrl": "http://v"}]

    res = resolve_preview("Artist", "Acid Trip", itunes_search=fake_itunes)
    assert res.kind == "itunes"
    assert res.audio_url == "http://p"
    assert res.source_url == "http://v"
    assert res.matched_title == "Acid Trip"


def test_resolve_preview_falls_back_to_youtube():
    payload = {"videos": [{"uri": "https://youtu.be/bbbbbbbbbbb", "title": "Artist - Acid Trip", "duration": 200}]}
    res = resolve_preview(
        "Artist", "Acid Trip",
        itunes_search=lambda term: [],
        get_release=lambda rid: payload,
        discogs_id=123, level="track",
    )
    assert res.kind == "youtube"
    assert res.youtube_video_id == "bbbbbbbbbbb"
    assert res.source_url == "https://www.youtube.com/watch?v=bbbbbbbbbbb"


def test_resolve_preview_none_when_nothing_matches():
    res = resolve_preview(
        "Artist", "Acid Trip",
        itunes_search=lambda term: [],
        get_release=lambda rid: {"videos": []},
        discogs_id=123, level="track",
    )
    assert res.kind == "none"
    assert res.audio_url is None and res.youtube_video_id is None


def test_resolve_preview_none_when_get_release_raises():
    def boom(rid):
        raise RuntimeError("discogs down")

    res = resolve_preview(
        "Artist", "Acid Trip",
        itunes_search=lambda term: [],
        get_release=boom, discogs_id=123, level="track",
    )
    assert res.kind == "none"


def test_resolve_preview_none_when_itunes_raises():
    def boom(term):
        raise RuntimeError("itunes down")
    res = resolve_preview("Artist", "Acid Trip", itunes_search=boom)
    assert res.kind == "none"


def test_resolve_preview_builds_search_term():
    seen = {}
    def spy(term):
        seen["term"] = term
        return []
    resolve_preview("Rick Astley", "Never Gonna Give You Up", itunes_search=spy)
    assert seen["term"] == "Rick Astley Never Gonna Give You Up"
