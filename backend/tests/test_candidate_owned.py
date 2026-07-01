"""Candidate Engine disk-first: di default solo tracce possedute."""
from app.models import Track
from app.schemas import SetGenerationRequest
from app.services.candidate_engine import select_candidates


def _track(i: int, *, owned: bool) -> Track:
    return Track(
        source_type="spotify", title=f"T{i}", artist=f"A{i}",
        bpm=126.0 + i, camelot_key="8A", duration_seconds=300,
        has_local_file=owned,
    )


def test_default_solo_possedute(db):
    db.add(_track(1, owned=True))
    db.add(_track(2, owned=False))
    db.commit()

    out = select_candidates(db, SetGenerationRequest())
    assert [t.title for t in out] == ["T1"]


def test_opt_out_include_lead(db):
    db.add(_track(1, owned=True))
    db.add(_track(2, owned=False))
    db.commit()

    out = select_candidates(db, SetGenerationRequest(owned_only=False))
    assert {t.title for t in out} == {"T1", "T2"}


def test_errore_contestuale_owned_only(db):
    """Con owned_only e zero possedute, l'errore spiega il rimedio."""
    import pytest
    from app.services.set_generator import SetGenerationError, generate_set

    db.add(_track(1, owned=False))
    db.add(_track(2, owned=False))
    db.add(_track(3, owned=False))
    db.commit()

    with pytest.raises(SetGenerationError, match="posseduti"):
        generate_set(db, SetGenerationRequest())
