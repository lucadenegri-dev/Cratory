"""Avvio: se LIBRARY_ROOT è configurata, l'indicizzazione parte da sola."""
from fastapi.testclient import TestClient

from app.main import app


def test_avvio_lancia_indicizzazione_se_dovuto(monkeypatch, tmp_path):
    from app.core.config import settings
    from app.services import library_index_job

    called = []
    monkeypatch.setattr(settings, "library_root", str(tmp_path))
    monkeypatch.setattr(library_index_job, "get_state", lambda db, k: None)  # mai indicizzato → dovuto
    monkeypatch.setattr(library_index_job, "start_job", lambda: called.append(True) or {})

    with TestClient(app):  # il context manager esegue il lifespan
        pass
    assert called == [True]


def test_avvio_salta_indicizzazione_se_recente(monkeypatch, tmp_path):
    from datetime import datetime, timezone

    from app.core.config import settings
    from app.services import library_index_job

    called = []
    monkeypatch.setattr(settings, "library_root", str(tmp_path))
    monkeypatch.setattr(library_index_job, "get_state",
                        lambda db, k: datetime.now(timezone.utc).isoformat())  # appena indicizzato
    monkeypatch.setattr(library_index_job, "start_job", lambda: called.append(True) or {})

    with TestClient(app):
        pass
    assert called == []  # debounce: niente re-indicizzazione a ridosso dell'ultima


def test_avvio_senza_library_root_non_lancia(monkeypatch):
    from app.core.config import settings
    from app.services import library_index_job

    called = []
    monkeypatch.setattr(settings, "library_root", "")
    monkeypatch.setattr(library_index_job, "start_job", lambda: called.append(True) or {})

    with TestClient(app):
        pass
    assert called == []
