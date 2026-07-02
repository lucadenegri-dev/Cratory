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


def test_job_indicizzazione_persiste_last_index_at(monkeypatch, tmp_path):
    """A fine indicizzazione riuscita, last_index_at è salvato in app_state."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from app.core.config import settings
    from app.db import Base
    from app.services import library_index_job

    # StaticPool: connessione unica condivisa, così la sessione del job e quella
    # di verifica vedono lo stesso DB in-memory (vedi test_track_lookup.py).
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(library_index_job, "SessionLocal", factory)
    monkeypatch.setattr(settings, "library_root", str(tmp_path))
    monkeypatch.setattr(library_index_job, "_spawn", lambda fn: fn())  # sincrono nel test

    library_index_job.start_job()

    session = factory()
    try:
        assert get_state(session, "last_index_at") is not None
    finally:
        session.close()
