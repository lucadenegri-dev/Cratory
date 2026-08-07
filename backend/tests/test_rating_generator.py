"""Bonus voto nel generator: tie-break, mai sopra la compatibilita' BPM/key."""

from app.models import Track
from app.schemas import SetGenerationRequest
from app.services.set_generator import _DEFAULT_PROFILE, _candidate_score


def make_track(**kw) -> Track:
    kw.setdefault("source_type", "spotify")
    kw.setdefault("duration_seconds", 300)
    return Track(**kw)


def _score(prev, cand) -> float:
    total, _ = _candidate_score(prev, cand, 126.0, SetGenerationRequest(), {},
                                _DEFAULT_PROFILE, 0.5)
    return total


def test_a_parita_vince_la_traccia_votata():
    prev = make_track(id=1, bpm=124.0, camelot_key="8A")
    votata = make_track(id=2, bpm=126.0, camelot_key="8A", rating=3)
    non_votata = make_track(id=3, bpm=126.0, camelot_key="8A")
    assert _score(prev, votata) > _score(prev, non_votata)


def test_voto_piu_alto_batte_voto_piu_basso():
    prev = make_track(id=1, bpm=124.0, camelot_key="8A")
    tre = make_track(id=2, bpm=126.0, camelot_key="8A", rating=3)
    uno = make_track(id=3, bpm=126.0, camelot_key="8A", rating=1)
    assert _score(prev, tre) > _score(prev, uno)


def test_voto_non_ribalta_la_compatibilita():
    prev = make_track(id=1, bpm=124.0, camelot_key="8A")
    compatibile = make_track(id=2, bpm=126.0, camelot_key="8A")
    incompatibile_votata = make_track(id=3, bpm=145.0, camelot_key="3B", rating=3)
    assert _score(prev, compatibile) > _score(prev, incompatibile_votata)
