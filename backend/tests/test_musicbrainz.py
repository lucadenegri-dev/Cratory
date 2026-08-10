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


def test_parse_exposes_release_mbids_non_va_first():
    from app.integrations.musicbrainz import MusicBrainzProvider
    mb = MusicBrainzProvider(user_agent="test")
    rec = {
        "id": "REC-1", "title": "T", "score": 100,
        "artist-credit": [{"name": "A"}],
        "releases": [
            {"id": "VA", "artist-credit": [{"name": "Various Artists"}]},
            {"id": "SINGLE", "artist-credit": [{"name": "A"}]},
        ],
    }
    out = mb._parse_recording(rec, isrc=None, exact=True)
    assert out["release_mbids"] == ["SINGLE", "VA"]  # non-VA prima


def test_album_prefers_studio_album_over_single():
    """Caso Chemical Brothers: la stessa registrazione è su un Single ('Got to
    Keep On') e sull'album in studio ('No Geography'). L'album da proporre è
    quello in studio, non il singolo — anche se MB elenca il singolo per primo."""
    p = MusicBrainzProvider(user_agent="test/0.1")
    rec = {
        "id": "mbid-cb", "title": "Got to Keep On",
        "artist-credit": [{"name": "The Chemical Brothers"}],
        "releases": [
            {"id": "rel-single", "date": "2019-02-01", "title": "Got to Keep On",
             "release-group": {"primary-type": "Single", "secondary-types": ["Remix"]},
             "label-info": [{"label": {"name": "Single Label"}}]},
            {"id": "rel-album", "date": "2019-04-12", "title": "No Geography",
             "release-group": {"primary-type": "Album", "secondary-types": []},
             "label-info": [{"label": {"name": "Virgin"}}]},
        ],
        "tags": [{"name": "big beat", "count": 4}],
    }
    out = p._parse_recording(rec, isrc=None, exact=False)
    assert out["canonical_album"] == "No Geography"      # album in studio, non il singolo
    assert out["label"] == "Virgin"                      # label dall'album
    assert out["release_date"].startswith("2019")
    # il release-MBID dell'album viene prima del singolo
    assert out["release_mbids"][0] == "rel-album"


def test_parse_recording_exposes_genre_candidates():
    """_parse_recording espone tutti i tag come candidati genere (ordinati per count)."""
    p = MusicBrainzProvider(user_agent="test/1.0")
    rec = {"id": "mbid-1", "title": "Spastik",
           "artist-credit": [{"name": "Plastikman"}],
           "tags": [{"name": "techno", "count": 5},
                    {"name": "acid techno", "count": 2},
                    {"name": "electronic", "count": 7}]}
    out = p._parse_recording(rec, isrc=None, exact=True)
    assert out["genre_primary"] == "electronic"
    assert out["genre_candidates"] == ["electronic", "techno", "acid techno"]


def test_parse_recording_no_tags_no_candidates():
    p = MusicBrainzProvider(user_agent="test/1.0")
    rec = {"id": "mbid-2", "title": "X", "artist-credit": [{"name": "Y"}]}
    out = p._parse_recording(rec, isrc=None, exact=False)
    assert "genre_candidates" not in out
