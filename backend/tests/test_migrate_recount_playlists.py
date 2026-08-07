"""Migrazione: riallinea il track_count denormalizzato alle membership reali."""

from sqlalchemy import create_engine, text

import app.models  # noqa: F401 — registra i modelli in Base.metadata
from app.db import Base, ensure_schema


def _engine_with_counts(stored_count: int, real_memberships: int):
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(eng)
    with eng.begin() as c:
        c.execute(text(
            "INSERT INTO playlists (id, platform, name, track_count, kind, imported_at, created_at, updated_at) "
            "VALUES (1, 'spotify', 'P', :count, 'playlist', datetime('now'), datetime('now'), datetime('now'))"
        ), {"count": stored_count})
        for i in range(real_memberships):
            c.execute(text(
                "INSERT INTO tracks (id, source_type, title, artist, status, has_local_file, created_at, updated_at) "
                "VALUES (:tid, 'spotify', :title, 'X', 'imported', 0, datetime('now'), datetime('now'))"
            ), {"tid": i + 1, "title": f"T{i + 1}"})
            c.execute(text(
                "INSERT INTO playlist_tracks (playlist_id, track_id, position) VALUES (1, :tid, :pos)"
            ), {"tid": i + 1, "pos": i + 1})
    return eng


def _count(eng) -> int:
    with eng.connect() as c:
        return c.execute(text("SELECT track_count FROM playlists WHERE id=1")).scalar()


def test_recount_ripara_conteggio_gonfiato():
    # Bug storico di merge_tracks: conteggio più alto delle membership reali.
    eng = _engine_with_counts(stored_count=5, real_memberships=2)
    ensure_schema(eng)
    assert _count(eng) == 2


def test_recount_azzera_playlist_vuota():
    eng = _engine_with_counts(stored_count=3, real_memberships=0)
    ensure_schema(eng)
    assert _count(eng) == 0


def test_recount_conteggio_corretto_resta_invariato():
    eng = _engine_with_counts(stored_count=2, real_memberships=2)
    ensure_schema(eng)
    assert _count(eng) == 2
