"""Ordine persistente delle tracce in playlist: colonna position + backfill + append."""
import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401
from app.db import Base, ensure_schema, _migrate_backfill_playlist_positions
from app.models import Playlist, Track, playlist_tracks
from app.repositories import add_track_to_playlist, tracks_for_playlist


@pytest.fixture()
def db():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(eng)
    s = sessionmaker(bind=eng, expire_on_commit=False)()
    try:
        yield s
    finally:
        s.close()


def _pl(db, name="P", kind="manual"):
    pl = Playlist(platform="manual", name=name, kind=kind)
    db.add(pl); db.flush()
    return pl


def _tr(db, title):
    t = Track(source_type="local_files", title=title, artist="A")
    db.add(t); db.flush()
    return t


def test_add_appende_position(db):
    pl = _pl(db)
    a, b, c = _tr(db, "a"), _tr(db, "b"), _tr(db, "c")
    add_track_to_playlist(db, a, pl)
    add_track_to_playlist(db, b, pl)
    add_track_to_playlist(db, c, pl)
    db.commit()
    rows = db.execute(
        select(playlist_tracks.c.track_id, playlist_tracks.c.position)
        .where(playlist_tracks.c.playlist_id == pl.id)
        .order_by(playlist_tracks.c.position)
    ).all()
    assert [r.position for r in rows] == [1, 2, 3]
    assert [t.title for t in tracks_for_playlist(db, pl.id)] == ["a", "b", "c"]


def test_backfill_assegna_1_n_su_null(db):
    pl = _pl(db)
    a, b, c = _tr(db, "a"), _tr(db, "b"), _tr(db, "c")
    # inserimento raw SENZA position (simula righe pre-migrazione), added_at crescente
    for i, t in enumerate([a, b, c]):
        db.execute(playlist_tracks.insert().values(
            playlist_id=pl.id, track_id=t.id, added_at=text(f"datetime('2020-01-0{i+1}')"),
        ))
    db.commit()
    conn = db.connection()
    _migrate_backfill_playlist_positions(conn)
    db.commit()
    rows = db.execute(
        select(playlist_tracks.c.track_id, playlist_tracks.c.position)
        .where(playlist_tracks.c.playlist_id == pl.id)
        .order_by(playlist_tracks.c.position)
    ).all()
    assert [r.position for r in rows] == [1, 2, 3]
    assert [r.track_id for r in rows] == [a.id, b.id, c.id]
