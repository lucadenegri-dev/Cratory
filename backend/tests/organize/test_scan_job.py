import time

from sqlalchemy import select

from app.core.config import settings
from app.organize.models import AudioFile, ScanRoot
from app.organize.services import scan_job


def _wait_done(timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        state = scan_job.job_state()
        if state["status"] in ("done", "error"):
            return state
        time.sleep(0.02)
    raise AssertionError("job non terminato in tempo")


def test_job_runs_and_completes(db, copy_fixture, tmp_path, monkeypatch):
    root_dir = tmp_path / "lib"
    # start_job ora deriva le radici da roots.radici(): la cartella ad hoc del
    # test deve essere quella configurata, e la ScanRoot creata qui sotto ne
    # viene adottata (stesso path, label ancora NULL) mantenendo lo stesso id.
    monkeypatch.setattr(settings, "library_root", str(root_dir))
    copy_fixture("mp3", root_dir / "a.mp3")
    root = ScanRoot(path=str(root_dir))
    db.add(root)
    db.commit()

    scan_job.start_job(["library"])
    state = _wait_done()
    assert state["status"] == "done"
    assert state["result"]["inserted"] == 1
    assert db.scalar(select(AudioFile)) is not None


def test_created_ids_non_esposto_nello_stato(db, copy_fixture, tmp_path, monkeypatch):
    """`linking.created_ids` porta gli id delle Track create — comodo dentro il
    processo, ma su una prima indicizzazione da 20k brani ogni poll di
    GET /api/organize/scan/status trascinerebbe altrettanti interi. Il report
    esposto in `job_state()["result"]` lo esclude; l'aggregato `created` resta."""
    root_dir = tmp_path / "lib"
    monkeypatch.setattr(settings, "library_root", str(root_dir))
    copy_fixture("mp3", root_dir / "a.mp3")
    root = ScanRoot(path=str(root_dir))
    db.add(root)
    db.commit()

    scan_job.start_job(["library"])
    state = _wait_done()

    assert state["status"] == "done"
    assert state["result"]["linking"]["created"] == 1
    assert "created_ids" not in state["result"]["linking"]


def test_double_start_is_rejected():
    # Forza lo stato running e verifica che start_job non lo sovrascriva.
    scan_job._state.update(status="running", processed=0, total=0)
    before = scan_job.job_state()
    returned = scan_job.start_job(["library"])
    assert returned["status"] == "running"
    assert scan_job.job_state()["started_at"] == before["started_at"]
    scan_job._state.update(status="idle")  # ripristina per gli altri test
