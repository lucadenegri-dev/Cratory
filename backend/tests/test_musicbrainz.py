from app.integrations.musicbrainz import MusicBrainzProvider


def test_parse_recording_extracts_label_genre_date():
    p = MusicBrainzProvider(user_agent="test/0.1")
    rec = {
        "id": "mbid-1", "title": "Dreamscapes",
        "artist-credit": [{"name": "SLV"}],
        "releases": [{"date": "2019-05-01",
                      "label-info": [{"label": {"name": "Drumcode"}}]}],
        "tags": [{"name": "techno", "count": 5}, {"name": "acid", "count": 2}],
    }
    out = p._parse_recording(rec, isrc="ITX", exact=True)
    assert out["label"] == "Drumcode"
    assert out["genre_primary"] == "techno"
    assert out["release_date"] == "2019-05-01"
    assert out["canonical_artist"] == "SLV"
    assert out["mbid"] == "mbid-1"
    assert out["confidence"] == 95


def test_best_recording_prefers_title_match():
    p = MusicBrainzProvider(user_agent="test/0.1")
    recs = [
        {"title": "Other", "score": 50, "artist-credit": [{"name": "SLV"}]},
        {"title": "Dreamscapes", "score": 50, "artist-credit": [{"name": "SLV"}]},
    ]
    best = p._best_recording(recs, "Dreamscapes", "SLV")
    assert best["title"] == "Dreamscapes"
