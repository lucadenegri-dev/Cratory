"""Fusione di due tracce che sono lo stesso brano (merge_tracks)."""
from sqlalchemy import select

from app.models import Playlist, Setlist, SetlistTrack, Track, playlist_tracks
from app.repositories import add_track_to_playlist, merge_tracks, tracks_for_playlist


def _pl(db, name):
    p = Playlist(platform="spotify", name=name)
    db.add(p); db.flush()
    return p


def test_merge_trasferisce_membership_playlist(db):
    pa, pb = _pl(db, "A"), _pl(db, "B")
    keep = Track(source_type="spotify", title="K", artist="X")
    drop = Track(source_type="local_files", title="D", artist="X")
    db.add_all([keep, drop]); db.flush()
    add_track_to_playlist(db, keep, pa)
    add_track_to_playlist(db, drop, pb)
    db.commit()

    merge_tracks(db, keep, drop); db.commit()

    assert db.query(Track).count() == 1
    assert keep in tracks_for_playlist(db, pa.id)
    assert keep in tracks_for_playlist(db, pb.id)  # trasferita da drop
    assert db.get(Track, drop.id) is None


def test_merge_riempie_solo_i_campi_vuoti(db):
    keep = Track(source_type="spotify", title="K", artist="X", spotify_id="s1")
    drop = Track(source_type="local_files", title="D", artist="X",
                 bpm=128.0, camelot_key="8A", label="Warp")
    db.add_all([keep, drop]); db.commit()

    merge_tracks(db, keep, drop); db.commit()
    db.refresh(keep)

    assert keep.bpm == 128.0 and keep.camelot_key == "8A" and keep.label == "Warp"  # riempiti da drop
    assert keep.title == "K" and keep.spotify_id == "s1"  # non sovrascritti
    assert db.get(Track, drop.id) is None


def test_merge_ripunta_setlist(db):
    keep = Track(source_type="spotify", title="K", artist="X")
    drop = Track(source_type="local_files", title="D", artist="X")
    db.add_all([keep, drop]); db.flush()
    s = Setlist(name="S"); db.add(s); db.flush()
    db.add(SetlistTrack(setlist_id=s.id, track_id=drop.id, position=0))
    db.commit()

    merge_tracks(db, keep, drop); db.commit()

    st = db.query(SetlistTrack).one()
    assert st.track_id == keep.id
    assert db.get(Track, drop.id) is None


def test_merge_conserva_la_position_della_membership_trasferita(db):
    pa = _pl(db, "A")
    t1 = Track(source_type="spotify", title="T1", artist="X")
    t2 = Track(source_type="spotify", title="T2", artist="X")
    drop = Track(source_type="local_files", title="D", artist="X")
    keep = Track(source_type="spotify", title="K", artist="X")  # non membro di pa
    db.add_all([t1, t2, drop, keep]); db.flush()
    add_track_to_playlist(db, t1, pa)
    add_track_to_playlist(db, t2, pa)
    add_track_to_playlist(db, drop, pa)  # posizioni assegnate in ordine di append
    db.commit()

    drop_pos = db.execute(
        select(playlist_tracks.c.position).where(
            playlist_tracks.c.playlist_id == pa.id, playlist_tracks.c.track_id == drop.id,
        )
    ).scalar_one()
    assert drop_pos is not None

    merge_tracks(db, keep, drop); db.commit()

    keep_pos = db.execute(
        select(playlist_tracks.c.position).where(
            playlist_tracks.c.playlist_id == pa.id, playlist_tracks.c.track_id == keep.id,
        )
    ).scalar_one()
    assert keep_pos == drop_pos  # keep eredita lo slot di drop, non NULL
    assert keep in tracks_for_playlist(db, pa.id)
    assert db.get(Track, drop.id) is None


def test_merge_noop_su_stessa_traccia(db):
    t = Track(source_type="spotify", title="K", artist="X")
    db.add(t); db.commit()
    assert merge_tracks(db, t, t) is t
    assert db.query(Track).count() == 1
