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
