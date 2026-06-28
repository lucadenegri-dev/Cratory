"""Test playlist many-to-many: migrazione backfill + helper membership."""

from sqlalchemy import create_engine, text

import app.models  # noqa: F401 — registra tutti i modelli in Base.metadata
from app.db import Base, ensure_schema


def _legacy_engine():
    """Engine in-memory con una traccia legacy (Track.playlist_id valorizzato)."""
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(eng)
    with eng.begin() as c:
        c.execute(text(
            "INSERT INTO playlists (id, platform, name, track_count, kind, imported_at, created_at, updated_at) "
            "VALUES (1, 'spotify', 'P', 0, 'playlist', datetime('now'), datetime('now'), datetime('now'))"
        ))
        c.execute(text(
            "INSERT INTO tracks (id, source_type, playlist_id, playlist_name, title, artist, status, created_at, updated_at) "
            "VALUES (1, 'spotify', 1, 'P', 'T', 'A', 'imported', datetime('now'), datetime('now'))"
        ))
    return eng


def test_backfill_creates_membership_and_clears_legacy():
    eng = _legacy_engine()
    ensure_schema(eng)
    with eng.connect() as c:
        rows = c.execute(text("SELECT playlist_id, track_id FROM playlist_tracks")).fetchall()
        assert rows == [(1, 1)]
        leftover = c.execute(text("SELECT playlist_id, playlist_name FROM tracks WHERE id=1")).fetchone()
        assert leftover == (None, None)


def test_backfill_is_idempotent():
    eng = _legacy_engine()
    ensure_schema(eng)
    ensure_schema(eng)  # seconda passata: nessun duplicato
    with eng.connect() as c:
        n = c.execute(text("SELECT COUNT(*) FROM playlist_tracks")).scalar()
        assert n == 1
