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
    rows = [t for t, _ in rows]
    bpms = [r.bpm for r in rows]
    assert bpms[:3] == [140.0, 128.0, 120.0]
    assert bpms[-1] is None  # NULL sempre in fondo


def test_sort_by_artist_asc(db):
    _seed_varied(db)
    _total, rows = list_tracks(db, sort="artist", order="asc")
    rows = [t for t, _ in rows]
    artists = [r.artist for r in rows if r.artist]
    assert artists == ["Xen", "Yan", "Zed"]


def _keys_sorted(db, order):
    _total, rows = list_tracks(db, sort="key", order=order)
    return [t.camelot_key for t, _ in rows]


def test_sort_by_key_follows_camelot_wheel(db):
    # Inserite alla rinfusa: l'ordine lessicografico darebbe 10A, 10B, 11A, …, 1A.
    keys = ["10A", "1B", "12B", "2A", "1A", "11A", "10B", "2B", "12A", "11B"]
    db.add_all([Track(source_type="manual", title=k, artist="A", camelot_key=k) for k in keys])
    db.commit()

    wheel = ["1A", "1B", "2A", "2B", "10A", "10B", "11A", "11B", "12A", "12B"]
    assert _keys_sorted(db, "asc") == wheel
    assert _keys_sorted(db, "desc") == wheel[::-1]


def test_sort_by_key_unknown_last_both_ways(db):
    # Minuscole e spazi contano come la key normale (come nel filtro); malformate,
    # vuote e NULL in fondo in entrambi i versi, per id.
    keys = ["8A", "foo", None, "", "8a", " 3B ", "13A", "9B"]
    db.add_all([Track(source_type="manual", title=str(k), artist="A", camelot_key=k) for k in keys])
    db.commit()

    unknown = ["foo", None, "", "13A"]
    assert _keys_sorted(db, "asc") == [" 3B ", "8A", "8a", "9B", *unknown]
    assert _keys_sorted(db, "desc") == ["9B", "8A", "8a", " 3B ", *unknown]


def test_status_filter(db):
    _seed_varied(db)
    total, rows = list_tracks(db, status="ready_for_set")
    rows = [t for t, _ in rows]
    assert total == 1
    assert rows[0].title == "Alpha"


def test_key_filter_is_case_insensitive(db):
    _seed_varied(db)
    total, rows = list_tracks(db, key="8a")  # minuscolo deve matchare "8A"
    rows = [t for t, _ in rows]
    assert total == 1
    assert rows[0].camelot_key == "8A"


def test_incomplete_metadata_includes_missing_bpm_or_key_or_artist(db):
    _seed_varied(db)
    total, rows = list_tracks(db, incomplete_metadata=True)
    rows = [t for t, _ in rows]
    titles = {r.title for r in rows}
    # Gamma (no bpm/key), Delta (no artist) sono incomplete; Alpha/Beta no.
    assert titles == {"Gamma", "Delta"}
    assert total == 2


def test_genre_filter_partial_match(db):
    _seed_varied(db)
    total, rows = list_tracks(db, genre="house")
    rows = [t for t, _ in rows]
    assert total == 1 and rows[0].genre == "house"


def test_filtro_has_local_file(db):
    db.add(Track(source_type="spotify", title="Owned", artist="A", has_local_file=True))
    db.add(Track(source_type="spotify", title="Wish", artist="B", has_local_file=False))
    db.commit()

    total_owned, owned = list_tracks(db, has_local_file=True)
    total_wish, wish = list_tracks(db, has_local_file=False)
    owned = [t for t, _ in owned]
    wish = [t for t, _ in wish]
    assert total_owned == 1 and owned[0].title == "Owned"
    assert total_wish == 1 and wish[0].title == "Wish"


def test_filtro_source_local_files(db):
    db.add(Track(source_type="local_files", title="Loc", artist="A"))
    db.add(Track(source_type="spotify", title="Sp", artist="B"))
    db.commit()

    total, rows = list_tracks(db, source="local_files")
    rows = [t for t, _ in rows]
    assert total == 1 and rows[0].title == "Loc"
