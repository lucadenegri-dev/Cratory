"""Filtro rating=N e sort=rating su GET /api/tracks."""

from app.models import Track
from app.repositories import list_tracks


def _seed(db):
    a = Track(source_type="manual", title="A", artist="a", rating=1)
    b = Track(source_type="manual", title="B", artist="b", rating=3)
    c = Track(source_type="manual", title="C", artist="c")  # non votata
    db.add_all([a, b, c]); db.commit()
    return a, b, c


def test_filtro_rating_esatto(db):
    a, b, c = _seed(db)
    total, rows = list_tracks(db, rating=3)
    assert total == 1 and [t.id for t, _ in rows] == [b.id]


def test_sort_rating_desc_non_votate_in_fondo(db):
    a, b, c = _seed(db)
    _, rows = list_tracks(db, sort="rating", order="desc")
    assert [t.id for t, _ in rows] == [b.id, a.id, c.id]


def test_sort_rating_asc_non_votate_comunque_in_fondo(db):
    a, b, c = _seed(db)
    _, rows = list_tracks(db, sort="rating", order="asc")
    assert [t.id for t, _ in rows] == [a.id, b.id, c.id]
