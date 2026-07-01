"""Indicizzazione della libreria canonica (LIBRARY_ROOT)."""
from app.core.config import Settings


def test_library_root_default_vuoto():
    s = Settings(_env_file=None)
    assert s.library_root == ""
