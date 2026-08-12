import time

from app.organize.models import AudioFile, ScanRoot
from app.organize.services import provider_rescan_job


def _wait_done(timeout=5.0):
    start = time.monotonic()
    while time.monotonic() - start < timeout:
        st = provider_rescan_job.job_state()
        if st["status"] in ("done", "error"):
            return st
        time.sleep(0.02)
    raise AssertionError("job non terminato")


def test_job_runs_and_reports_done(db, monkeypatch):
    root = ScanRoot(path="/m"); db.add(root); db.flush()
    db.add(AudioFile(root_id=root.id, path="/m/a.mp3", ext="mp3", size_bytes=1,
                     hash_method="file", status="present", title="A", genre="x"))
    db.commit()

    # provider + fingerprint neutralizzati: niente rete nel test
    from app.organize.services.text_providers import ResolvedText
    monkeypatch.setattr("app.organize.services.provider_rescan.text_providers.resolve",
                        lambda f, **kw: ResolvedText(fields={}, release_mbids=[], confidence=None))
    monkeypatch.setattr(provider_rescan_job.acoustid, "acoustid_configured", lambda: False)

    provider_rescan_job.start_job(fields=["genre"])
    st = _wait_done()
    assert st["status"] == "done"
    assert st["result"]["scanned"] == 1
    assert st["result"]["acoustid_available"] is False
