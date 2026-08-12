"""Nessun test deve poter scrivere sul DB reale: l'engine di modulo punta
sempre a un file temporaneo per la sessione di test."""

from app.db import engine


def test_engine_non_punta_al_db_reale():
    url = str(engine.url)
    assert "djassistant.db" not in url
    assert "djorganizer.db" not in url


def test_engine_punta_a_una_temp_dir():
    url = str(engine.url)
    assert "/tmp" in url or "/var/folders" in url  # mkdtemp su Linux / macOS


def test_guard_scan_azzera_tutte_e_tre_le_radici(db):
    """La fixture autouse `_no_real_library_scan` (conftest.py) deve azzerare
    le TRE cartelle configurabili (library_root, archive_root,
    slskd_download_dir/inbox), non solo le prime due: con una gamba mancante,
    `radici(db)` risolverebbe comunque la cartella Inbox vera dello
    sviluppatore (SLSKD_DOWNLOAD_DIR del suo .env) e un test che chiama
    scan_job._run/scanner.scan senza monkeypatchare a mano cammina e hasha
    quella cartella reale."""
    from app.organize.services.roots import radici

    esito = radici(db)

    assert esito == {}
