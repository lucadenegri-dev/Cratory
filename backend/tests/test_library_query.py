"""Filtri e ordinamento della libreria (repositories.list_tracks)."""

from app.models import Track
from app.repositories import list_tracks


def _seed_varied(db):
    """Tracce con BPM/genere/stato/key eterogenei per testare filtri e sort."""
    rows = [
        Track(source_type="spotify", title="Alpha", artist="Zed", bpm=128.0,
              camelot_key="8A", genre="techno", energy=70, status="ready_for_set"),
        Track(source_type="spotify", title="Beta", artist="Yan", bpm=120.0,
              camelot_key="9B", genre="house", energy=50, status="enriched"),
        Track(source_type="manual", title="Gamma", artist="Xen", bpm=None,
              camelot_key=None, genre=None, energy=None, status="imported"),
        Track(source_type="spotify", title="Delta", artist=None, bpm=140.0,
              camelot_key="10A", genre="trance", energy=90, status="missing_features"),
    ]
    db.add_all(rows)
    db.commit()


def test_sort_by_bpm_desc_nulls_last(db):
    _seed_varied(db)
    _total, rows = list_tracks(db, sort="bpm", order="desc")
    bpms = [r.bpm for r in rows]
    assert bpms[:3] == [140.0, 128.0, 120.0]
    assert bpms[-1] is None  # NULL sempre in fondo


def test_sort_by_artist_asc(db):
    _seed_varied(db)
    _total, rows = list_tracks(db, sort="artist", order="asc")
    artists = [r.artist for r in rows if r.artist]
    assert artists == ["Xen", "Yan", "Zed"]


def test_status_filter(db):
    _seed_varied(db)
    total, rows = list_tracks(db, status="ready_for_set")
    assert total == 1
    assert rows[0].title == "Alpha"


def test_key_filter_is_case_insensitive(db):
    _seed_varied(db)
    total, rows = list_tracks(db, key="8a")  # minuscolo deve matchare "8A"
    assert total == 1
    assert rows[0].camelot_key == "8A"


def test_incomplete_metadata_includes_missing_bpm_or_key_or_artist(db):
    _seed_varied(db)
    total, rows = list_tracks(db, incomplete_metadata=True)
    titles = {r.title for r in rows}
    # Gamma (no bpm/key), Delta (no artist) sono incomplete; Alpha/Beta no.
    assert titles == {"Gamma", "Delta"}
    assert total == 2


def test_genre_filter_partial_match(db):
    _seed_varied(db)
    total, rows = list_tracks(db, genre="house")
    assert total == 1 and rows[0].genre == "house"
