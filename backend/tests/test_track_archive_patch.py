"""Archivia/ripristina dalla wishlist: campo `archived` nel PATCH /api/tracks/{id}.

Prima via manuale per impostare Track.archived (finora solo DJPlayer/indicizzazione).
Semantica PATCH: campo assente O null = invariato (archived e' un bool NOT NULL:
il "null azzera" degli altri campi qui non si applica). Stile test_track_update.py:
chiamate dirette a router/repository, niente TestClient.
"""

from app.models import Track
from app.repositories import list_tracks
from app.routers import tracks
from app.schemas import TrackUpdateIn


def _track(db, **kw) -> Track:
    t = Track(source_type="spotify", title="X", artist="Y", **kw)
    db.add(t)
    db.commit()
    return t


def test_patch_archivia_e_ripristina(db):
    t = _track(db)
    tracks.patch_track(t.id, TrackUpdateIn(archived=True), db)
    db.refresh(t)
    assert t.archived is True
    tracks.patch_track(t.id, TrackUpdateIn(archived=False), db)
    db.refresh(t)
    assert t.archived is False


def test_patch_senza_archived_non_tocca(db):
    t = _track(db)
    tracks.patch_track(t.id, TrackUpdateIn(archived=True), db)
    tracks.patch_track(t.id, TrackUpdateIn(title="Nuovo"), db)
    db.refresh(t)
    assert t.archived is True  # campo assente = invariato
    assert t.title == "Nuovo"


def test_patch_archived_null_e_invariato(db):
    """`archived: null` esplicito non deve scrivere NULL su una colonna NOT NULL."""
    t = _track(db)
    tracks.patch_track(t.id, TrackUpdateIn(archived=True), db)
    tracks.patch_track(t.id, TrackUpdateIn(archived=None), db)
    db.refresh(t)
    assert t.archived is True


def test_lista_riflette_l_archiviazione(db):
    t = _track(db)
    tracks.patch_track(t.id, TrackUpdateIn(archived=True), db)
    total_attive, attive = list_tracks(db, limit=0, offset=0)
    total_arch, archiviate = list_tracks(db, limit=0, offset=0, archived=True)
    assert t.id not in [x.id for x, _ in attive]
    assert t.id in [x.id for x, _ in archiviate]
