"""Playlist speciale "Top" (kind='rating_top'): sync deterministica col voto 3."""

from sqlalchemy import select

from app.models import Playlist, Track, playlist_tracks
from app.repositories import merge_tracks
from app.routers import tracks
from app.schemas import TrackUpdateIn


def _track(db, **kw) -> Track:
    t = Track(source_type="spotify", title="X", artist="Y", **kw)
    db.add(t)
    db.commit()
    return t


def _top(db) -> Playlist | None:
    return db.scalar(select(Playlist).where(Playlist.kind == "rating_top"))


def _member_ids(db, playlist: Playlist) -> set[int]:
    rows = db.execute(select(playlist_tracks.c.track_id).where(
        playlist_tracks.c.playlist_id == playlist.id)).all()
    return {r[0] for r in rows}


def test_primo_voto_3_crea_top_e_aggiunge(db):
    t = _track(db)
    tracks.patch_track(t.id, TrackUpdateIn(rating=3), db)
    top = _top(db)
    assert top is not None
    assert top.name == "Top" and top.platform == "manual"
    assert _member_ids(db, top) == {t.id}
    assert top.track_count == 1


def test_voto_sotto_3_non_crea_top(db):
    t = _track(db)
    tracks.patch_track(t.id, TrackUpdateIn(rating=2), db)
    assert _top(db) is None


def test_downgrade_rimuove_dalla_top(db):
    t = _track(db)
    tracks.patch_track(t.id, TrackUpdateIn(rating=3), db)
    tracks.patch_track(t.id, TrackUpdateIn(rating=1), db)
    top = _top(db)
    assert _member_ids(db, top) == set()
    assert top.track_count == 0


def test_togliere_il_voto_rimuove_dalla_top(db):
    t = _track(db)
    tracks.patch_track(t.id, TrackUpdateIn(rating=3), db)
    tracks.patch_track(t.id, TrackUpdateIn(rating=None), db)
    assert _member_ids(db, _top(db)) == set()


def test_rivoto_3_idempotente(db):
    t = _track(db)
    tracks.patch_track(t.id, TrackUpdateIn(rating=3), db)
    tracks.patch_track(t.id, TrackUpdateIn(rating=3), db)
    top = _top(db)
    assert _member_ids(db, top) == {t.id}
    assert top.track_count == 1


def test_patch_di_altri_campi_non_tocca_la_top(db):
    t = _track(db)
    tracks.patch_track(t.id, TrackUpdateIn(rating=3), db)
    tracks.patch_track(t.id, TrackUpdateIn(title="Nuovo"), db)
    assert _member_ids(db, _top(db)) == {t.id}


def test_merge_con_keep_non_votata_e_drop_votata_3_porta_keep_in_top(db):
    # drop e' in Top (voto 3), keep non ha voto: il merge deve backfillare il
    # voto su keep e la sync deve confermarlo in Top (non lasciare la membership
    # trasferita "orfana" di un voto coerente).
    keep = _track(db)
    drop = _track(db)
    tracks.patch_track(drop.id, TrackUpdateIn(rating=3), db)
    db.refresh(keep)
    db.refresh(drop)

    merge_tracks(db, keep, drop)
    db.commit()
    db.refresh(keep)

    top = _top(db)
    assert keep.rating == 3
    assert _member_ids(db, top) == {keep.id}
    assert top.track_count == 1


def test_merge_con_keep_votata_1_e_drop_votata_3_non_lascia_keep_in_top(db):
    # keep ha gia' un voto (1): il backfill non lo tocca (keep resta autorevole).
    # drop era in Top per il suo voto 3: quella membership viene trasferita dal
    # merge ma la sync la deve rimuovere, perche' il voto di keep resta 1.
    keep = _track(db)
    drop = _track(db)
    tracks.patch_track(keep.id, TrackUpdateIn(rating=1), db)
    tracks.patch_track(drop.id, TrackUpdateIn(rating=3), db)
    db.refresh(keep)
    db.refresh(drop)

    merge_tracks(db, keep, drop)
    db.commit()
    db.refresh(keep)

    top = _top(db)
    assert keep.rating == 1
    assert _member_ids(db, top) == set()
    assert top.track_count == 0
