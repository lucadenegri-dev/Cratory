"""Job di analisi: selezione scope, scrittura analysis_*, auto-apply, errori per traccia."""
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import Track


@pytest.fixture()
def sync_job(monkeypatch):
    """Job sincrono su DB in memoria condiviso, con motore finto (128 bpm / 8A)."""
    from app.integrations.essentia_engine import AnalysisResult
    from app.services import audio_analysis_job as aj

    e = create_engine("sqlite://", connect_args={"check_same_thread": False},
                      poolclass=StaticPool)
    Base.metadata.create_all(e)
    S = sessionmaker(bind=e, expire_on_commit=False)
    monkeypatch.setattr(aj, "SessionLocal", S)
    monkeypatch.setattr(aj, "_spawn", lambda fn: fn())  # sincrono nei test
    monkeypatch.setattr(aj.essentia_engine, "analyze",
                        lambda path: AnalysisResult(bpm=128.0, camelot="8A"))
    return aj, S


def _seed(S):
    with S() as s:
        s.add(Track(id=1, source_type="spotify", has_local_file=True,
                    local_path="/x/vuota.mp3", artist="A", title="Vuota"))
        s.add(Track(id=2, source_type="spotify", has_local_file=True,
                    local_path="/x/piena.mp3", artist="A", title="Piena",
                    bpm=130.0, bpm_source="rekordbox",
                    camelot_key="9A", key_source="rekordbox"))
        s.add(Track(id=3, source_type="spotify", has_local_file=False, title="NoFile"))
        s.commit()


def test_scope_missing_analizza_solo_le_mancanti(sync_job):
    aj, S = sync_job
    _seed(S)
    aj.start_job(scope="missing")
    st = aj.job_state()
    assert st["status"] == "done" and st["total"] == 1 and st["analyzed"] == 1
    with S() as s:
        vuota = s.get(Track, 1)
        assert vuota.analysis_bpm == 128.0 and vuota.analysis_camelot == "8A"
        # auto-apply sui vuoti: canonici riempiti con source cratory
        assert vuota.bpm == 128.0 and vuota.bpm_source == "cratory"
        assert vuota.status == "ready_for_set" and vuota.analyzed_at is not None
        piena = s.get(Track, 2)
        assert piena.analysis_bpm is None  # fuori scope


def test_scope_all_non_tocca_i_canonici_pieni(sync_job):
    aj, S = sync_job
    _seed(S)
    aj.start_job(scope="all")
    assert aj.job_state()["total"] == 2  # solo has_local_file
    with S() as s:
        piena = s.get(Track, 2)
        assert piena.analysis_bpm == 128.0  # analizzata
        assert piena.bpm == 130.0 and piena.bpm_source == "rekordbox"  # canonico intatto


def test_errore_per_traccia_non_ferma_il_batch(sync_job, monkeypatch):
    aj, S = sync_job
    _seed(S)

    def _boom(path):
        raise RuntimeError("file corrotto")
    monkeypatch.setattr(aj.essentia_engine, "analyze", _boom)
    aj.start_job(scope="all")
    st = aj.job_state()
    assert st["status"] == "done" and st["failed"] == 2
    with S() as s:
        assert s.get(Track, 1).analysis_error == "analysis_decode_failed"


def test_track_ids_espliciti(sync_job):
    aj, S = sync_job
    _seed(S)
    aj.start_job(scope="all", track_ids=[2])
    assert aj.job_state()["total"] == 1
    with S() as s:
        assert s.get(Track, 2).analysis_bpm == 128.0
        assert s.get(Track, 1).analysis_bpm is None
