"""Guardia "un solo job alla volta" (mono-utente): un secondo avvio mentre uno e'
gia' in corso deve essere rifiutato, senza avviare un secondo thread. Copre i job
che condividono il pattern (stato globale in memoria + threading.Lock):
shazam/mix, indicizzazione libreria, analisi BPM/key, import streaming.

Ogni job espone il contratto in un punto diverso:
- analysis / import streaming: il ROUTER controlla is_running() e ritorna 409
  PRIMA di chiamare start_job (vedi app/routers/analysis.py, app/routers/playlists.py).
- library index / mix identify: nessun controllo nel router (app/routers/tracks.py,
  app/routers/dj_sets.py chiamano start_job() incondizionatamente); la guardia vive
  DENTRO start_job/_start, che e' un no-op silenzioso (nessuna eccezione, nessun
  secondo thread) se lo stato e' gia' "running".

Il download Soulseek non e' piu' qui: non e' piu' un job uno-alla-volta ma una
coda a N slot, dove accodare e' sempre lecito. La sua concorrenza e' coperta da
tests/test_download_dispatcher.py e tests/test_download_queue_claim.py.
"""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


class _ThreadNotExpected:
    """threading.Thread finto che fallisce il test se istanziato: garantisce che
    il secondo avvio non spawni un secondo worker."""

    def __init__(self, *a, **kw):
        raise AssertionError("un secondo job non deve avviare un nuovo thread")


# --- analysis: guardia nel router (409 esplicito) -----------------------------


def test_analysis_double_start_refused_via_router(monkeypatch):
    from app.routers import analysis as ar

    monkeypatch.setattr(ar.essentia_engine, "is_available", lambda: True)
    monkeypatch.setattr(ar.audio_analysis_job, "is_running", lambda: True)
    started = {"n": 0}
    monkeypatch.setattr(ar.audio_analysis_job, "start_job",
                        lambda **kw: started.update(n=started["n"] + 1))

    r = client.post("/api/analysis/start", json={"scope": "missing"})

    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "analysis_already_running"
    assert started["n"] == 0  # start_job non e' mai stato chiamato


# --- library index (F4 Task 3: alias di scan_job): nessun controllo nel -------
# --- router, guardia dentro start_job ------------------------------------------


def test_library_index_double_start_is_noop_at_job_level(monkeypatch):
    from app.organize.services import scan_job

    monkeypatch.setattr(scan_job.threading, "Thread", _ThreadNotExpected)
    scan_job._state.update(status="running", processed=5, total=10)

    result = scan_job.start_job()

    assert result["status"] == "running"
    assert result["processed"] == 5  # stato precedente intatto
    assert result["total"] == 10

    # ripristina per non contaminare altri test del modulo
    scan_job._state.update(status="idle", processed=0, total=0)


def test_library_index_double_start_via_router_is_also_noop(monkeypatch):
    """Il router /api/library/index (alias di scan_job da F4 Task 3) non
    controlla is_running() esplicitamente (a differenza di analysis/downloads):
    verifichiamo che la richiesta HTTP non esploda e che il job non venga
    comunque rilanciato mentre uno e' in corso."""
    from app.core.config import settings
    from app.organize.services import scan_job

    monkeypatch.setattr(settings, "library_root", "/some/root")
    monkeypatch.setattr(scan_job.threading, "Thread", _ThreadNotExpected)
    scan_job._state.update(status="running", processed=7, total=10)

    r = client.post("/api/library/index")

    assert r.status_code == 202
    assert r.json()["status"] == "running"
    assert r.json()["processed"] == 7  # non risistemato: nessun nuovo run e' partito

    scan_job._state.update(status="idle", processed=0, total=0)


# --- mix identify (shazam): nessun controllo nel router, guardia in start_job -


def test_mix_identify_double_start_is_noop_at_job_level(monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from app.db import Base
    from app.services import mix_identify_job as mij

    # A differenza degli altri job, start_job consulta il DB (cache per URL)
    # PRIMA della guardia sul lock: senza questo monkeypatch il test dipende
    # dal DB reale del progetto (backend/data/djassistant.db) — su un checkout
    # o worktree vergine la tabella dj_sets non esiste ancora al primo run
    # della suite (la crea, per effetto collaterale, un test successivo che
    # esegue la lifespan) e start_job esplode con "no such table: dj_sets".
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    monkeypatch.setattr(mij, "SessionLocal",
                        sessionmaker(bind=engine, expire_on_commit=False))

    monkeypatch.setattr(mij.threading, "Thread", _ThreadNotExpected)
    mij._state.update(status="running", dj_set_id=42, phase="Riconosco i brani…")

    result = mij.start_job("https://soundcloud.com/never-seen-before")

    assert result["cached"] is False
    assert result["status"] == "running"
    assert result["dj_set_id"] == 42  # stato precedente intatto

    mij._state.update(status="idle", dj_set_id=None, phase=None)


# --- import/sync streaming: guardia nel router (409 esplicito), come analysis -


def test_streaming_import_double_start_refused_via_router(monkeypatch):
    from app.services import streaming_import_job as sij

    monkeypatch.setattr(sij, "is_running", lambda: True)
    started = {"n": 0}
    monkeypatch.setattr(sij, "start_job", lambda kind, **kw: started.update(n=started["n"] + 1))

    r = client.post("/api/playlists/import", json={"playlist_id": "liked"})

    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "streaming_import_already_running"
    assert started["n"] == 0


def test_streaming_import_double_start_refused_via_soundcloud_router(monkeypatch):
    from app.services import streaming_import_job as sij

    monkeypatch.setattr(sij, "is_running", lambda: True)
    started = {"n": 0}
    monkeypatch.setattr(sij, "start_job", lambda kind, **kw: started.update(n=started["n"] + 1))

    r = client.post("/api/soundcloud/import", json={"url": "https://soundcloud.com/a/sets/b"})

    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "streaming_import_already_running"
    assert started["n"] == 0


def test_streaming_import_start_job_is_noop_at_job_level_when_running(monkeypatch):
    """Difesa in profondita' come library index/mix identify: anche a monte del
    router, start_job() non deve rilanciare un thread se lo stato e' gia' 'running'."""
    from app.services import streaming_import_job as sij

    monkeypatch.setattr(sij, "_spawn",
                        lambda fn: (_ for _ in ()).throw(AssertionError("non deve rilanciare il job")))
    sij._state.update(status="running", kind="spotify_liked", processed=3, total=10)

    result = sij.start_job("soundcloud_playlist", url="https://soundcloud.com/x")

    assert result["status"] == "running"
    assert result["kind"] == "spotify_liked"  # stato precedente intatto, non sovrascritto
    assert result["processed"] == 3

    sij._state.update(status="idle", kind=None, processed=0, total=0)
