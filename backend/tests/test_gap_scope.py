"""Gap analysis scope-aware: i controlli di coerenza genere valgono per una
playlist (fonte di un set), non per la libreria intera — una collezione che
spazia su molti generi e' sana, non 'dispersiva'."""
from app.models import Track
from app.services.gap_analysis import analyze_gaps


def _tracks_many_genres(n_genres=12, per_genre=2):
    out = []
    for g in range(n_genres):
        for i in range(per_genre):
            out.append(Track(source_type="manual", title=f"T{g}-{i}", artist="A",
                             bpm=120.0 + g, camelot_key="8A", genre=f"genre-{g}",
                             energy=50 + (g * 3) % 40))
    return out


def test_library_scope_skips_genre_checks():
    gaps = analyze_gaps(_tracks_many_genres(), scope="library")
    types = {g["gap_type"] for g in gaps}
    assert "scattered_genres" not in types
    assert "low_genre_variety" not in types


def test_playlist_scope_keeps_genre_checks():
    gaps = analyze_gaps(_tracks_many_genres(), scope="playlist")
    types = {g["gap_type"] for g in gaps}
    assert "scattered_genres" in types


def test_default_scope_is_playlist():
    gaps = analyze_gaps(_tracks_many_genres())
    assert "scattered_genres" in {g["gap_type"] for g in gaps}


def test_no_gap_text_mentions_playlist_at_library_scope():
    tracks = _tracks_many_genres()
    # forza anche il gap di energia piatta (tutte uguali)
    for t in tracks:
        t.energy = 50
    gaps = analyze_gaps(tracks, scope="library")
    for g in gaps:
        assert "playlist" not in g["description"].lower(), g
