"""Un solo job per l'intera scansione."""

import pytest


def test_library_index_job_non_esiste_piu():
    with pytest.raises(ModuleNotFoundError):
        import app.services.library_index_job  # noqa: F401


def test_scan_job_espone_lavvio_automatico():
    from app.organize.services import scan_job

    assert hasattr(scan_job, "start_job_if_due")


class _SpyDict(dict):
    """Sostituisce `scan_job._state`: registra le `phase` viste da ogni update,
    così il test osserva le fasi REALMENTE scritte durante una corsa invece di
    controllare solo che la chiave esista (già vera oggi anche a riposo)."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.phases: list[str | None] = []

    def update(self, *a, **kw):
        if "phase" in kw:
            self.phases.append(kw["phase"])
        super().update(*a, **kw)


def test_lo_stato_osservato_durante_la_corsa_copre_scanning_e_linking(db, fake_audio, monkeypatch):
    """`"phase" in job_state()` è vero anche a riposo (vale `None`): un test che
    si fermasse lì sarebbe vacuo. Qui si fa girare una corsa vera e si controlla
    quali fasi il job scrive DAVVERO in `_state` durante l'esecuzione."""
    from app.core.config import settings
    from app.organize.services import scan_job

    make, root = fake_audio
    monkeypatch.setattr(settings, "library_root", str(root))
    monkeypatch.setattr(settings, "slskd_download_dir", "")
    make("Techno/N/N - New.mp3", digest="H7", artist="N", title="New")

    spia = _SpyDict(scan_job._state)
    monkeypatch.setattr(scan_job, "_state", spia)

    scan_job._run(None)  # sincrono, senza thread

    assert "scanning" in spia.phases
    assert "linking" in spia.phases


def test_la_corsa_scrive_last_index_at(db, fake_audio, monkeypatch):
    """La data dell'ultima indicizzazione alimenta l'avvio automatico: se si
    perde, il job riparte a ogni reload di uvicorn."""
    from app.core.config import settings
    from app.organize.services import scan_job
    from app.services.app_state import get_state

    make, root = fake_audio
    monkeypatch.setattr(settings, "library_root", str(root))
    monkeypatch.setattr(settings, "slskd_download_dir", "")
    make("Techno/N/N - New.mp3", digest="H7", artist="N", title="New")

    scan_job._run(None)  # sincrono, senza thread

    # _run apre una SessionLocal propria: la sessione del test ha una vista
    # precedente al suo commit. Il rollback la rinfresca senza perdere nulla
    # (il seed è già committato sopra).
    db.rollback()
    assert get_state(db, "last_index_at") is not None
