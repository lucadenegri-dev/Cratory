"""Config effettiva a runtime: override DB (AppState `cfg.*`) sopra i default `.env`.

La cache di `runtime_settings` è un global di modulo: ogni test chiama `rs.load(db)`
con un DB fresco (fixture `db`) per ripartire pulito.
"""
from pathlib import Path

from app.core import config, runtime_settings as rs
from app.services.app_state import get_state, set_state


def test_default_is_env_when_no_override(db, monkeypatch):
    monkeypatch.setattr(config.settings, "slskd_url", "http://env:5030")
    rs.load(db)
    assert rs.slskd_url() == "http://env:5030"
    assert rs.source("slskd_url") == "env"


def test_override_takes_precedence(db, monkeypatch):
    monkeypatch.setattr(config.settings, "slskd_url", "http://env:5030")
    rs.load(db)
    rs.apply(db, "slskd_url", "http://db:9999")
    assert rs.slskd_url() == "http://db:9999"
    assert rs.source("slskd_url") == "db"
    # persistito con prefisso cfg.
    assert get_state(db, "cfg.slskd_url") == "http://db:9999"


def test_clear_returns_to_env(db, monkeypatch):
    monkeypatch.setattr(config.settings, "slskd_url", "http://env:5030")
    rs.load(db)
    rs.apply(db, "slskd_url", "http://db:9999")
    rs.apply(db, "slskd_url", "")  # vuoto = azzera
    assert rs.slskd_url() == "http://env:5030"
    assert rs.source("slskd_url") == "env"
    assert get_state(db, "cfg.slskd_url") is None


def test_load_populates_from_db(db):
    set_state(db, "cfg.library_root", "/data/lib")
    rs.load(db)
    assert rs.library_root() == "/data/lib"
    assert rs.source("library_root") == "db"


def test_path_override_expands_tilde(db):
    rs.load(db)
    rs.apply(db, "library_root", "~/Music/Lib")
    assert rs.library_root() == str(Path("~/Music/Lib").expanduser())


def test_share_library_is_bool_and_off_by_default(db):
    rs.load(db)
    assert rs.share_library() is False
    rs.apply(db, "share_library", "1")
    assert rs.share_library() is True
    rs.clear(db, "share_library")
    assert rs.share_library() is False
