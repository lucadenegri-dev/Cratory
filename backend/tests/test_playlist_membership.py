"""Test playlist many-to-many: migrazione backfill + helper membership."""

import pytest

from sqlalchemy import create_engine, text

import app.models  # noqa: F401 — registra tutti i modelli in Base.metadata
from app.db import Base, ensure_schema
from app.models import Playlist, Track
from app.repositories import (
    add_track_to_playlist,
    delete_playlist,
    delete_playlist_track,
    recount_playlist,
    remove_track_from_playlist,
    tracks_for_playlist,
)


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


def _pl(db, name):
    pl = Playlist(platform="spotify", name=name, kind="playlist")
    db.add(pl); db.flush()
    return pl


def _tr(db, title):
    t = Track(source_type="spotify", title=title, artist="A")
    db.add(t); db.flush()
    return t


def test_add_membership_is_idempotent(db):
    pl, t = _pl(db, "P"), _tr(db, "T")
    add_track_to_playlist(db, t, pl)
    add_track_to_playlist(db, t, pl)  # secondo add: no-op
    db.commit()
    assert [x.title for x in tracks_for_playlist(db, pl.id)] == ["T"]


def test_track_in_two_playlists(db):
    a, b, t = _pl(db, "A"), _pl(db, "B"), _tr(db, "T")
    add_track_to_playlist(db, t, a)
    add_track_to_playlist(db, t, b)
    db.commit()
    assert {p.name for p in t.playlists} == {"A", "B"}
    assert t in tracks_for_playlist(db, a.id)
    assert t in tracks_for_playlist(db, b.id)


def test_remove_membership_keeps_track(db):
    a, b, t = _pl(db, "A"), _pl(db, "B"), _tr(db, "T")
    add_track_to_playlist(db, t, a)
    add_track_to_playlist(db, t, b)
    db.commit()
    remove_track_from_playlist(db, a.id, t.id)
    db.commit()
    assert t not in tracks_for_playlist(db, a.id)
    assert t in tracks_for_playlist(db, b.id)
    assert db.query(Track).count() == 1


def test_delete_playlist_keeps_shared_track(db):
    a, b, t = _pl(db, "A"), _pl(db, "B"), _tr(db, "T")
    add_track_to_playlist(db, t, a)
    add_track_to_playlist(db, t, b)
    db.commit()
    assert delete_playlist(db, a.id) == 0        # in un'altra playlist: non orfano
    assert db.query(Track).count() == 1          # brano resta in libreria
    assert t in tracks_for_playlist(db, b.id)     # e nell'altra playlist


def test_delete_playlist_removes_orphan_lead(db):
    """Lead senza file, solo in questa playlist e in nessun set: viene cancellato."""
    a, t = _pl(db, "A"), _tr(db, "solo")
    add_track_to_playlist(db, t, a)
    db.commit()
    assert delete_playlist(db, a.id) == 1
    assert db.query(Track).count() == 0


def test_delete_playlist_keeps_owned_track(db):
    """Traccia su disco: resta in libreria anche se orfana dalle playlist."""
    a, t = _pl(db, "A"), _tr(db, "owned")
    t.has_local_file = True
    add_track_to_playlist(db, t, a)
    db.commit()
    assert delete_playlist(db, a.id) == 0
    assert db.query(Track).count() == 1


def test_delete_playlist_keeps_lead_used_in_setlist(db):
    """Lead orfano dalle playlist ma usato in un set salvato: NON si cancella."""
    from app.models import Setlist, SetlistTrack

    a, t = _pl(db, "A"), _tr(db, "inset")
    add_track_to_playlist(db, t, a)
    s = Setlist(name="S"); db.add(s); db.flush()
    db.add(SetlistTrack(setlist_id=s.id, track_id=t.id, position=0))
    db.commit()
    assert delete_playlist(db, a.id) == 0
    assert db.query(Track).count() == 1


def test_delete_playlist_missing_returns_none(db):
    assert delete_playlist(db, 9999) is None


def test_delete_playlist_track_keeps_shared_track(db):
    """Traccia in due playlist: tolta da una, resta nell'altra e in libreria."""
    a, b, t = _pl(db, "A"), _pl(db, "B"), _tr(db, "T")
    add_track_to_playlist(db, t, a)
    add_track_to_playlist(db, t, b)
    db.commit()
    assert delete_playlist_track(db, a.id, t.id) == 0   # in un'altra playlist: non orfano
    assert t not in tracks_for_playlist(db, a.id)
    assert t in tracks_for_playlist(db, b.id)
    assert db.query(Track).count() == 1


def test_delete_playlist_track_removes_orphan_lead(db):
    """Lead senza file, solo in questa playlist e in nessun set: viene cancellato."""
    a, t = _pl(db, "A"), _tr(db, "solo")
    add_track_to_playlist(db, t, a)
    db.commit()
    assert delete_playlist_track(db, a.id, t.id) == 1
    assert db.query(Track).count() == 0


def test_delete_playlist_track_keeps_owned_track(db):
    """Traccia su disco: resta in libreria anche se orfana dalle playlist."""
    a, t = _pl(db, "A"), _tr(db, "owned")
    t.has_local_file = True
    add_track_to_playlist(db, t, a)
    db.commit()
    assert delete_playlist_track(db, a.id, t.id) == 0
    assert db.query(Track).count() == 1


def test_delete_playlist_track_recounts(db):
    a, t1, t2 = _pl(db, "A"), _tr(db, "T1"), _tr(db, "T2")
    t1.has_local_file = t2.has_local_file = True  # non orfane: restano
    add_track_to_playlist(db, t1, a)
    add_track_to_playlist(db, t2, a)
    recount_playlist(db, a)
    db.commit()
    assert a.track_count == 2
    delete_playlist_track(db, a.id, t1.id)
    assert a.track_count == 1


def test_delete_playlist_track_missing_membership_returns_none(db):
    a, t = _pl(db, "A"), _tr(db, "loose")  # traccia esiste ma non in playlist
    db.commit()
    assert delete_playlist_track(db, a.id, t.id) is None


def test_delete_playlist_track_missing_playlist_returns_none(db):
    assert delete_playlist_track(db, 9999, 1) is None


def test_recount_playlist(db):
    pl, t1, t2 = _pl(db, "P"), _tr(db, "T1"), _tr(db, "T2")
    add_track_to_playlist(db, t1, pl)
    add_track_to_playlist(db, t2, pl)
    db.commit()
    recount_playlist(db, pl)
    assert pl.track_count == 2


def test_track_out_exposes_playlists(db):
    from app.serializers import track_out
    a, b, t = _pl(db, "A"), _pl(db, "B"), _tr(db, "T")
    add_track_to_playlist(db, t, a)
    add_track_to_playlist(db, t, b)
    db.commit()
    out = track_out(t)
    assert {p.name for p in out.playlists} == {"A", "B"}
    assert not hasattr(out, "playlist_id")
