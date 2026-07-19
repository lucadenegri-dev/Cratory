"""Migrazione idempotente: playlist di sistema Discovery 'Scoperte' -> 'Discovery'."""

from sqlalchemy import create_engine, text

import app.models  # noqa: F401 — registra i modelli in Base.metadata
from app.db import Base, ensure_schema


def _engine_with_playlist(name: str, *, kind: str = "discovery", platform: str = "manual"):
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(eng)
    with eng.begin() as c:
        c.execute(text(
            "INSERT INTO playlists (id, platform, name, track_count, kind, imported_at, created_at, updated_at) "
            "VALUES (1, :platform, :name, 0, :kind, datetime('now'), datetime('now'), datetime('now'))"
        ), {"platform": platform, "name": name, "kind": kind})
    return eng


def _name(eng) -> str:
    with eng.connect() as c:
        return c.execute(text("SELECT name FROM playlists WHERE id=1")).scalar()


def test_rename_old_discovery_playlist():
    eng = _engine_with_playlist("Scoperte")
    ensure_schema(eng)
    assert _name(eng) == "Discovery"


def test_rename_is_idempotent():
    eng = _engine_with_playlist("Scoperte")
    ensure_schema(eng)
    ensure_schema(eng)  # seconda passata: no-op
    assert _name(eng) == "Discovery"


def test_rename_leaves_other_playlists_untouched():
    # Stesso nome ma non è la playlist di sistema Discovery: non va toccata.
    eng = _engine_with_playlist("Scoperte", kind="playlist", platform="spotify")
    ensure_schema(eng)
    assert _name(eng) == "Scoperte"
