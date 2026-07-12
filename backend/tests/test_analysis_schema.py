"""Colonne provenienza/analisi e backfill delle source (pagina Analisi)."""
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import ensure_schema
from app.models import Track


def _engine():
    return create_engine("sqlite://", connect_args={"check_same_thread": False},
                         poolclass=StaticPool)


def test_track_ha_colonne_provenienza_e_analisi(db):
    t = Track(source_type="spotify", bpm=128.0, camelot_key="8A",
              bpm_source="rekordbox", key_source="manual",
              analysis_bpm=127.9, analysis_camelot="8A",
              analysis_error=None)
    db.add(t); db.commit(); db.refresh(t)
    assert t.bpm_source == "rekordbox" and t.key_source == "manual"
    assert t.analysis_bpm == 127.9 and t.analysis_camelot == "8A"
    assert t.analyzed_at is None and t.analysis_error is None


def test_backfill_source_rekordbox_su_valori_esistenti():
    """DB pre-migrazione: bpm/key presenti ma source NULL -> 'rekordbox'."""
    e = _engine()
    ensure_schema(e)
    S = sessionmaker(bind=e, expire_on_commit=False)
    with S() as s:
        s.add(Track(source_type="spotify", bpm=130.0, camelot_key="9A"))
        s.add(Track(source_type="spotify"))  # senza valori: source resta NULL
        s.commit()
        s.execute(text("UPDATE tracks SET bpm_source = NULL, key_source = NULL"))
        s.commit()
    ensure_schema(e)  # idempotente: il backfill gira di nuovo
    with S() as s:
        con, senza = s.scalars(select(Track).order_by(Track.id)).all()
        assert con.bpm_source == "rekordbox" and con.key_source == "rekordbox"
        assert senza.bpm_source is None and senza.key_source is None
