"""Fix review finale (F1): DATABASE_URL relativo va riancorato a
backend/, non alla cwd del processo — stesso pattern di app/core/config.py.
Stessa normalizzazione anche per cover_cache_dir/thumb_cache_dir."""
from pathlib import Path

from app.core.config import BACKEND_DIR, Settings


def test_relative_database_url_is_anchored_to_backend_dir(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    s = Settings(_env_file=None, database_url="sqlite:///./data/djorganizer.db")
    expected = (BACKEND_DIR / "data" / "djorganizer.db").resolve().as_posix()
    assert s.database_url == f"sqlite:///{expected}"


def test_absolute_database_url_unchanged(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    s = Settings(_env_file=None, database_url="sqlite:////mnt/data/djorganizer.db")
    assert s.database_url == "sqlite:////mnt/data/djorganizer.db"


def test_in_memory_database_url_unchanged(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    s = Settings(_env_file=None, database_url="sqlite:///:memory:")
    assert s.database_url == "sqlite:///:memory:"


def test_non_sqlite_database_url_unchanged(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    s = Settings(_env_file=None, database_url="postgresql://user:pw@host/db")
    assert s.database_url == "postgresql://user:pw@host/db"


def test_default_database_url_is_already_absolute(monkeypatch):
    """Il default in classe è già assoluto: il bug riguardava solo l'override
    da .env, che vince sul default e reintroduceva la dipendenza dal cwd."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    s = Settings(_env_file=None)
    assert Path(s.database_url.removeprefix("sqlite:///")).is_absolute()


def test_relative_cache_dirs_are_anchored_to_backend_dir(monkeypatch):
    monkeypatch.delenv("COVER_CACHE_DIR", raising=False)
    monkeypatch.delenv("THUMB_CACHE_DIR", raising=False)
    s = Settings(_env_file=None, cover_cache_dir="./data/cover_cache",
                 thumb_cache_dir="./data/thumb_cache")
    assert s.cover_cache_dir == (BACKEND_DIR / "data" / "cover_cache").resolve().as_posix()
    assert s.thumb_cache_dir == (BACKEND_DIR / "data" / "thumb_cache").resolve().as_posix()


def test_absolute_cache_dirs_unchanged(monkeypatch):
    monkeypatch.delenv("COVER_CACHE_DIR", raising=False)
    s = Settings(_env_file=None, cover_cache_dir="/mnt/cache/covers")
    assert s.cover_cache_dir == "/mnt/cache/covers"
