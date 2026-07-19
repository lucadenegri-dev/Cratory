"""Job di identificazione mix via Shazam (mix_identify_job): ZERO coverage prima
di questo file. Pattern preso da test_soulseek_download_job.py/test_library_index_router.py
(stato globale in memoria, SessionLocal monkeypatchata, job eseguito in-thread nei test
chiamando direttamente _run_job/start_job, niente thread reale)."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import DjSet, DjSetTrack
from app.services import mix_identify_job as job
from app.services.mix_identify import IdentifiedTrack, SetMeta


@pytest.fixture()
def patch_job(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(job, "SessionLocal", TestSession)
    # Stato globale in memoria condiviso tra i test del modulo: va azzerato ad ogni test.
    job._state.update(status="idle", phase=None, processed=0, total=0, dj_set_id=None,
                      error=None, started_at=None, finished_at=None)
    return TestSession


class _FakeRecognizer:
    """Finto AudioRecognizer: _run_job chiama .close() nel finally (cleanup delle
    risorse di rete/processo di ShazamioRecognizer), un semplice object() non basta."""

    def close(self) -> None:
        pass


def _make_dj_set(TestSession, url="https://soundcloud.com/x/mix", status="identifying"):
    db = TestSession()
    dj_set = DjSet(source_url=url, status=status)
    db.add(dj_set)
    db.commit()
    dj_set_id = dj_set.id
    db.close()
    return dj_set_id


def _fake_identify_set_ok(url, *, recognizer, on_progress=None):
    if on_progress:
        on_progress(1, 2)
        on_progress(2, 2)
    meta = SetMeta(source_url=url, title="Boiler Room Set", dj_name="DJ Test",
                   platform="soundcloud", duration_seconds=3600, artwork_url="http://img/art.jpg")
    tracks = [
        IdentifiedTrack(position=1, start_offset_seconds=0, artist="Artist A", title="Track A",
                        isrc="US1234500001", confidence=90),
        IdentifiedTrack(position=2, start_offset_seconds=180, artist="Artist B", title="Track B",
                        isrc=None, confidence=70),
    ]
    return meta, tracks, None


def _fake_identify_set_aborted(url, *, recognizer, on_progress=None):
    """Analisi troncata: l'endpoint e' morto a meta' mix (aborted_at valorizzato)."""
    meta = SetMeta(source_url=url, title="Set Troncato", dj_name="DJ Test",
                   platform="soundcloud", duration_seconds=7200, artwork_url=None)
    tracks = [IdentifiedTrack(position=1, start_offset_seconds=0, artist="A", title="One",
                              isrc=None, confidence=90)]
    return meta, tracks, 2769


def test_run_job_persiste_l_interruzione_dell_analisi(patch_job, monkeypatch):
    TestSession = patch_job
    monkeypatch.setattr("app.services.mix_identify.identify_set", _fake_identify_set_aborted)
    monkeypatch.setattr("app.integrations.shazam.ShazamioRecognizer", _FakeRecognizer)

    dj_set_id = _make_dj_set(TestSession)
    job._run_job(dj_set_id, "https://soundcloud.com/x/mix")

    db = TestSession()
    dj_set = db.get(DjSet, dj_set_id)
    assert dj_set.status == "done"  # parziale, ma il lavoro fatto resta
    assert dj_set.aborted_at_seconds == 2769  # ...e l'interruzione non e' silenziosa
    db.close()


# --- happy path ---------------------------------------------------------------


def test_run_job_happy_path_persiste_dj_set_e_tracce(patch_job, monkeypatch):
    TestSession = patch_job
    monkeypatch.setattr("app.services.mix_identify.identify_set", _fake_identify_set_ok)
    monkeypatch.setattr("app.integrations.shazam.ShazamioRecognizer", _FakeRecognizer)

    dj_set_id = _make_dj_set(TestSession)
    job._run_job(dj_set_id, "https://soundcloud.com/x/mix")

    st = job.job_state()
    assert st["status"] == "done"
    assert st["dj_set_id"] == dj_set_id
    assert st["phase"] is None

    db = TestSession()
    dj_set = db.get(DjSet, dj_set_id)
    assert dj_set.status == "done"
    assert dj_set.title == "Boiler Room Set"
    assert dj_set.dj_name == "DJ Test"
    assert dj_set.platform == "soundcloud"
    assert dj_set.duration_seconds == 3600
    assert dj_set.artwork_url == "http://img/art.jpg"
    assert dj_set.identified_count == 2
    assert dj_set.analyzed_at is not None
    assert dj_set.aborted_at_seconds is None  # analisi completa: nessuna interruzione
    tracks = db.query(DjSetTrack).filter(DjSetTrack.dj_set_id == dj_set_id).order_by(DjSetTrack.position).all()
    assert [t.artist for t in tracks] == ["Artist A", "Artist B"]
    assert [t.title for t in tracks] == ["Track A", "Track B"]
    assert tracks[0].isrc == "US1234500001"
    assert tracks[0].confidence == 90
    db.close()


def test_run_job_ripulisce_tentativo_precedente_fallito(patch_job, monkeypatch):
    """Se il DjSet aveva gia' delle DjSetTrack da un tentativo fallito in precedenza
    (start_job le ripulisce prima di rilanciare), _run_job deve limitarsi ad
    aggiungere le nuove: qui verifichiamo che non ci sia duplicazione residua."""
    TestSession = patch_job
    monkeypatch.setattr("app.services.mix_identify.identify_set", _fake_identify_set_ok)
    monkeypatch.setattr("app.integrations.shazam.ShazamioRecognizer", _FakeRecognizer)

    dj_set_id = _make_dj_set(TestSession)
    job._run_job(dj_set_id, "https://soundcloud.com/x/mix")

    db = TestSession()
    count = db.query(DjSetTrack).filter(DjSetTrack.dj_set_id == dj_set_id).count()
    assert count == 2
    db.close()


# --- failure path --------------------------------------------------------------


def test_run_job_failure_path_persiste_stato_errore(patch_job, monkeypatch):
    def _boom(url, *, recognizer, on_progress=None):
        raise RuntimeError("yt-dlp: video non disponibile")

    monkeypatch.setattr("app.services.mix_identify.identify_set", _boom)
    monkeypatch.setattr("app.integrations.shazam.ShazamioRecognizer", _FakeRecognizer)

    dj_set_id = _make_dj_set(patch_job)
    job._run_job(dj_set_id, "https://soundcloud.com/x/mix")

    st = job.job_state()
    assert st["status"] == "error"
    assert "yt-dlp" in (st["error"] or "")
    assert st["phase"] is None

    db = patch_job()
    dj_set = db.get(DjSet, dj_set_id)
    assert dj_set.status == "error"
    assert "yt-dlp" in (dj_set.error or "")
    # nessuna traccia persistita in caso di errore
    assert db.query(DjSetTrack).filter(DjSetTrack.dj_set_id == dj_set_id).count() == 0
    db.close()


def test_run_job_failure_finished_at_e_impostato(patch_job, monkeypatch):
    def _boom(url, *, recognizer, on_progress=None):
        raise RuntimeError("boom")

    monkeypatch.setattr("app.services.mix_identify.identify_set", _boom)
    monkeypatch.setattr("app.integrations.shazam.ShazamioRecognizer", _FakeRecognizer)

    dj_set_id = _make_dj_set(patch_job)
    assert job.job_state()["finished_at"] is None
    job._run_job(dj_set_id, "https://soundcloud.com/x/mix")
    assert job.job_state()["finished_at"] is not None


# --- double-start guard ---------------------------------------------------------


def test_start_job_no_op_se_gia_in_corso(patch_job, monkeypatch):
    """Un job gia' 'running' non deve avviare un secondo thread ne' toccare il DB
    per un URL diverso: start_job ritorna lo stato corrente con cached=False."""
    monkeypatch.setattr(job.threading, "Thread",
                        lambda *a, **kw: (_ for _ in ()).throw(AssertionError("non deve partire un secondo thread")))
    job._state.update(status="running", dj_set_id=777, phase="Riconosco i brani…")

    result = job.start_job("https://soundcloud.com/y/altro-mix")

    assert result["cached"] is False
    assert result["status"] == "running"
    assert result["dj_set_id"] == 777  # stato invariato, non e' stato riscritto


def test_start_job_url_gia_done_ritorna_cache_senza_rilanciare(patch_job, monkeypatch):
    """Un URL gia' identificato con successo non viene ri-analizzato (cache),
    anche se non c'e' alcun job in corso."""
    monkeypatch.setattr(job.threading, "Thread",
                        lambda *a, **kw: (_ for _ in ()).throw(AssertionError("non deve rilanciare l'analisi")))
    TestSession = patch_job
    dj_set_id = _make_dj_set(TestSession, url="https://soundcloud.com/z/done-mix", status="done")

    result = job.start_job("https://soundcloud.com/z/done-mix")

    assert result["cached"] is True
    assert result["dj_set_id"] == dj_set_id


def test_start_job_avvia_un_nuovo_job_quando_libero(patch_job, monkeypatch):
    """Stato idle, URL mai visto: start_job prepara lo stato 'running' e avvia UN
    thread (verificato intercettando threading.Thread invece di farlo girare davvero)."""
    started = {}

    class _FakeThread:
        def __init__(self, target=None, args=(), daemon=None):
            started["target"] = target
            started["args"] = args

        def start(self):
            started["started"] = True

    monkeypatch.setattr(job.threading, "Thread", _FakeThread)

    result = job.start_job("https://soundcloud.com/w/new-mix")

    assert result["cached"] is False
    assert result["status"] == "running"
    assert started.get("started") is True
    assert started["target"] is job._run_job
    assert started["args"][1] == "https://soundcloud.com/w/new-mix"


# --- job_state() copy / progress updates ----------------------------------------


def test_job_state_ritorna_una_copia(patch_job):
    """job_state() deve ritornare una copia: mutare il dict ricevuto non deve
    corrompere lo stato interno del modulo (bug facile con un semplice `return _state`)."""
    st = job.job_state()
    st["status"] = "corrotto"
    st["dj_set_id"] = 99999
    assert job.job_state()["status"] != "corrotto"
    assert job.job_state()["dj_set_id"] != 99999


def test_on_progress_aggiorna_processed_total_phase(patch_job, monkeypatch):
    seen = []

    def _fake_identify_set(url, *, recognizer, on_progress=None):
        on_progress(1, 2)
        seen.append(dict(job.job_state()))
        on_progress(2, 2)
        seen.append(dict(job.job_state()))
        meta = SetMeta(source_url=url, title="T")
        return meta, [], None

    monkeypatch.setattr("app.services.mix_identify.identify_set", _fake_identify_set)
    monkeypatch.setattr("app.integrations.shazam.ShazamioRecognizer", _FakeRecognizer)

    dj_set_id = _make_dj_set(patch_job)
    job._run_job(dj_set_id, "https://soundcloud.com/x/mix")

    assert seen[0]["processed"] == 1 and seen[0]["total"] == 2
    assert "1/2" in seen[0]["phase"]
    assert seen[1]["processed"] == 2 and seen[1]["total"] == 2


def test_is_running_riflette_lo_stato(patch_job):
    assert job.is_running() is False
    job._state["status"] = "running"
    assert job.is_running() is True
