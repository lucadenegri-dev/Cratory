"""Anti-regressione N+1: i path che serializzano Track devono eager-loadare
`Track.playlists` (selectinload), non una SELECT extra per traccia.

Il serializer (`serializers.track_out`) tocca sempre `track.playlists`: senza
eager loading ogni traccia restituita costa una query in piu' (1+N).
"""

from contextlib import contextmanager

from sqlalchemy import event

from app import repositories
from app.models import Playlist, Setlist, SetlistTrack, Track


@contextmanager
def count_queries(session):
    """Conta gli statement SQL eseguiti sull'engine della sessione."""
    counts: list[str] = []
    engine = session.get_bind()

    def before(conn, cursor, stmt, params, ctx, executemany):
        counts.append(stmt)

    event.listen(engine, "before_cursor_execute", before)
    try:
        yield counts
    finally:
        event.remove(engine, "before_cursor_execute", before)


N_TRACKS = 10


def _seed_tracks_in_playlist(db, seed_tracks) -> list[Track]:
    """10 tracce (con BPM, possedute) tutte membre di una playlist."""
    seed_tracks(N_TRACKS)
    playlist = Playlist(platform="spotify", name="Seed", track_count=0)
    db.add(playlist)
    db.commit()
    tracks = list(db.query(Track).all())
    for t in tracks:
        repositories.add_track_to_playlist(db, t, playlist)
    db.commit()
    return tracks


def test_all_playable_tracks_no_n_plus_one(db, seed_tracks):
    _seed_tracks_in_playlist(db, seed_tracks)
    db.expire_all()  # nessuna collezione gia' in memoria: misura reale

    with count_queries(db) as queries:
        rows = repositories.all_playable_tracks(db)
        for t in rows:
            _ = [p.name for p in t.playlists]  # come farebbe track_out

    assert len(rows) == N_TRACKS
    # 1 query per le tracce + 1 batch selectinload per le playlist (tolleranza 3).
    assert len(queries) <= 3, f"N+1 su Track.playlists: {len(queries)} query eseguite"


def test_tracks_download_pending_no_n_plus_one(db, seed_tracks):
    tracks = _seed_tracks_in_playlist(db, seed_tracks)
    # Le rendo "wishlist con esito da sistemare" per entrare nel filtro.
    for t in tracks:
        t.has_local_file = False
        t.last_download_outcome = "needs_review"
    db.commit()
    db.expire_all()

    with count_queries(db) as queries:
        rows = repositories.tracks_download_pending(db)
        for t in rows:
            _ = [p.name for p in t.playlists]

    assert len(rows) == N_TRACKS
    assert len(queries) <= 3, f"N+1 su Track.playlists: {len(queries)} query eseguite"


def test_get_setlist_no_n_plus_one(db, seed_tracks):
    tracks = _seed_tracks_in_playlist(db, seed_tracks)
    setlist = Setlist(name="Serata test")
    db.add(setlist)
    db.flush()
    for pos, t in enumerate(tracks):
        db.add(SetlistTrack(setlist_id=setlist.id, track_id=t.id, position=pos))
    db.commit()
    setlist_id = setlist.id
    db.expire_all()

    with count_queries(db) as queries:
        loaded = repositories.get_setlist(db, setlist_id)
        for st in loaded.tracks:
            _ = [p.name for p in st.track.playlists]  # come il serializer del dettaglio set

    assert len(loaded.tracks) == N_TRACKS
    # 1 setlist + 1 setlist_tracks + 1 tracks + 1 batch playlists (tolleranza 5).
    assert len(queries) <= 5, f"N+1 su Track.playlists: {len(queries)} query eseguite"
