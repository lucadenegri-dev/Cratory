"""Avvio: se LIBRARY_ROOT è configurata, l'indicizzazione parte da sola."""
from fastapi.testclient import TestClient

from app.main import app


def test_avvio_lancia_indicizzazione(monkeypatch, tmp_path):
    from app.core.config import settings
    from app.services import library_index_job

    called = []
    monkeypatch.setattr(settings, "library_root", str(tmp_path))
    monkeypatch.setattr(library_index_job, "start_job", lambda: called.append(True) or {})

    with TestClient(app):  # il context manager esegue il lifespan
        pass
    assert called == [True]


def test_avvio_senza_library_root_non_lancia(monkeypatch):
    from app.core.config import settings
    from app.services import library_index_job

    called = []
    monkeypatch.setattr(settings, "library_root", "")
    monkeypatch.setattr(library_index_job, "start_job", lambda: called.append(True) or {})

    with TestClient(app):
        pass
    assert called == []
