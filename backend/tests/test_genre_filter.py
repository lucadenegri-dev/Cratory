"""Filtro genere nel Set Builder (multi-select, match esatto) + endpoint aggregazione."""

from app.models import Track
from app.schemas import SetGenerationRequest


def _t(db, genre, **kw):
    kw.setdefault("bpm", 128.0)
    kw.setdefault("camelot_key", "8A")
    kw.setdefault("duration_seconds", 300)
    kw.setdefault("has_local_file", True)
    t = Track(source_type="spotify", genre=genre, **kw)
    db.add(t)
    return t


def test_genres_overview_counts_and_sorts(db):
    from app.repositories import genres_overview
    for g, n in [("Techno", 3), ("House", 1), ("Ambient", 2)]:
        for _ in range(n):
            _t(db, g)
    _t(db, None)          # senza genere: ignorata
    _t(db, "", bpm=None)  # senza bpm: fuori dal pool candidabile
    db.commit()

    rows = genres_overview(db)
    assert rows[0] == {"genre": "Techno", "count": 3}   # ordinati per frequenza
    assert {r["genre"] for r in rows} == {"Techno", "House", "Ambient"}


def test_candidates_filtered_by_genres_exact_match(db):
    from app.services.candidate_engine import select_candidates
    _t(db, "Techno")
    _t(db, "Techno")
    _t(db, "House")
    _t(db, "Acid Techno")  # match ESATTO: non deve entrare filtrando "Techno"
    db.commit()

    cands, _ = select_candidates(db, SetGenerationRequest(genres=["Techno"], owned_only=True))
    assert {t.genre for t in cands} == {"Techno"}
    assert len(cands) == 2


def test_candidates_multi_genre_union(db):
    from app.services.candidate_engine import select_candidates
    _t(db, "Techno")
    _t(db, "Electro")
    _t(db, "Ambient")
    db.commit()

    cands, _ = select_candidates(db, SetGenerationRequest(genres=["Techno", "Electro"], owned_only=True))
    assert {t.genre for t in cands} == {"Techno", "Electro"}


def test_no_genre_filter_keeps_all(db):
    from app.services.candidate_engine import select_candidates
    _t(db, "Techno")
    _t(db, "House")
    db.commit()
    cands, _ = select_candidates(db, SetGenerationRequest(genres=[], owned_only=True))
    assert len(cands) == 2
