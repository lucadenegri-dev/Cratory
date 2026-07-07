from app.integrations.musicbrainz import MusicBrainzProvider


def test_parse_recording_extracts_label_genre_date():
    p = MusicBrainzProvider(user_agent="test/0.1")
    rec = {
        "id": "mbid-1", "title": "Dreamscapes",
        "artist-credit": [{"name": "SLV"}],
        "releases": [{"date": "2019-05-01", "title": "Dreamscapes EP",
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
    assert out["canonical_album"] == "Dreamscapes EP"


def test_album_and_label_skip_various_artists_compilation():
    """Una traccia che compare SOLO su una compilation Various Artists / DJ-mix
    non deve proporre il nome della compilation come album (né il suo label):
    quel titolo (es. 'Progressive') non è l'album reale della traccia."""
    p = MusicBrainzProvider(user_agent="test/0.1")
    rec = {
        "id": "mbid-x", "title": "Tracid Theme",
        "artist-credit": [{"name": "Kai Tracid"}],
        "releases": [{
            "date": "2002", "title": "Progressive",
            "artist-credit": [{"name": "Various Artists"}],
            "release-group": {"primary-type": "Album",
                              "secondary-types": ["Compilation", "DJ-mix"]},
            "label-info": [{"label": {"name": "Some Comp Label"}}],
        }],
        "tags": [{"name": "trance", "count": 3}],
    }
    out = p._parse_recording(rec, isrc=None, exact=False)
    assert "canonical_album" not in out  # nessun album spurio dalla compilation
    assert "label" not in out            # né label dalla compilation
    assert out["genre_primary"] == "trance"  # il genere (dai tag) resta valido


def test_album_prefers_official_release_over_compilation():
    """Se esiste una release ufficiale (non VA/compilation), è quella a fornire
    album e label, ignorando le compilation presenti nella lista."""
    p = MusicBrainzProvider(user_agent="test/0.1")
    rec = {
        "id": "mbid-y", "title": "Tracid Theme",
        "artist-credit": [{"name": "Kai Tracid"}],
        "releases": [
            {"date": "2002", "title": "Progressive",
             "artist-credit": [{"name": "Various Artists"}],
             "release-group": {"secondary-types": ["Compilation", "DJ-mix"]},
             "label-info": [{"label": {"name": "Comp Label"}}]},
            {"date": "2002", "title": "Trance & Acid",
             "artist-credit": [{"name": "Kai Tracid"}],
             "release-group": {"primary-type": "Single"},
             "label-info": [{"label": {"name": "Tracid Traxxx"}}]},
        ],
    }
    out = p._parse_recording(rec, isrc=None, exact=False)
    assert out["canonical_album"] == "Trance & Acid"
    assert out["label"] == "Tracid Traxxx"


def test_best_recording_prefers_title_match():
    p = MusicBrainzProvider(user_agent="test/0.1")
    recs = [
        {"title": "Other", "score": 50, "artist-credit": [{"name": "SLV"}]},
        {"title": "Dreamscapes", "score": 50, "artist-credit": [{"name": "SLV"}]},
    ]
    best = p._best_recording(recs, "Dreamscapes", "SLV")
    assert best["title"] == "Dreamscapes"
