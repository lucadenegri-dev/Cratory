"""Mini chiave-valore app_state: stato applicativo persistente (es. last_index_at)."""
from app.services.app_state import get_state, set_state


def test_get_su_chiave_assente(db):
    assert get_state(db, "manca") is None


def test_set_e_get(db):
    set_state(db, "last_index_at", "2026-07-02T10:00:00+00:00")
    assert get_state(db, "last_index_at") == "2026-07-02T10:00:00+00:00"


def test_set_sovrascrive(db):
    set_state(db, "k", "v1")
    set_state(db, "k", "v2")
    assert get_state(db, "k") == "v2"
