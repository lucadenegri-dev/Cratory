"""Fusione di due tracce che sono lo stesso brano (merge_tracks)."""
from app.models import Playlist, Setlist, SetlistTrack, Track
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


def test_merge_noop_su_stessa_traccia(db):
    t = Track(source_type="spotify", title="K", artist="X")
    db.add(t); db.commit()
    assert merge_tracks(db, t, t) is t
    assert db.query(Track).count() == 1
