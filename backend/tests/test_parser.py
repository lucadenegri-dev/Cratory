"""Test del parser Rekordbox XML sul file di export reale (293 tracce)."""

from app.services.rekordbox_parser import detect_source, parse_rekordbox_xml


def test_detect_source_patterns():
    assert detect_source("file://localhostspotify:track:6CkLFR9wcDaRjyhxdTydBg") == (
        "spotify", "6CkLFR9wcDaRjyhxdTydBg", None,
    )
    assert detect_source("file://localhostsoundcloud:tracks:36057077") == (
        "soundcloud", None, "36057077",
    )
    assert detect_source("file://localhost/Users/foo/Music/track.wav") == ("local", None, None)
    assert detect_source(None) == ("local", None, None)


def test_parse_real_export(sample_xml_bytes):
    result = parse_rekordbox_xml(sample_xml_bytes)
    assert not result.errors
    assert len(result.tracks) == 293

    by_source = {}
    for t in result.tracks:
        by_source[t.source_type] = by_source.get(t.source_type, 0) + 1
    assert by_source["spotify"] == 198
    assert by_source["soundcloud"] > 0
    assert by_source["local"] > 0

    spotify_tracks = [t for t in result.tracks if t.source_type == "spotify"]
    assert all(t.spotify_id for t in spotify_tracks)
    # insidia nota: le tracce Spotify hanno spesso Name/Artist vuoti nell'export
    assert any(t.title is None for t in spotify_tracks)
    # ...ma Rekordbox fornisce BPM e tonalita' Camelot
    assert any(t.bpm and t.tonality for t in spotify_tracks)


def test_zero_values_become_none(sample_xml_bytes):
    result = parse_rekordbox_xml(sample_xml_bytes)
    for t in result.tracks:
        assert t.bpm != 0.0, "AverageBpm=0.00 deve diventare None"
        assert t.year != 0, "Year=0 deve diventare None"


def test_beatgrid_extracted(sample_xml_bytes):
    result = parse_rekordbox_xml(sample_xml_bytes)
    with_grid = [t for t in result.tracks if t.beatgrid]
    assert with_grid, "almeno una traccia deve avere beatgrid TEMPO"
    point = with_grid[0].beatgrid[0]
    assert point.bpm > 0
    assert point.start_seconds >= 0


def test_invalid_xml_reports_error():
    result = parse_rekordbox_xml(b"not xml at all")
    assert result.errors
    assert not result.tracks


def test_missing_collection_reports_error():
    result = parse_rekordbox_xml(b"<DJ_PLAYLISTS></DJ_PLAYLISTS>")
    assert result.errors
