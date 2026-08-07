"""Sync della playlist speciale "Top" (kind='rating_top') col voto delle tracce.

Deterministica e idempotente: voto 3 => membership presente, qualsiasi altro
voto (o nessuno) => assente. Chiamata da repositories.update_track PRIMA del
commit, cosi' la sync viaggia nella stessa transazione del PATCH. Stesso
precedente di get_or_create_discovery_playlist (playlist_import).
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Playlist, Track

# "Top" e' identico in IT ed EN: un solo nome salvato copre entrambe le lingue.
RATING_TOP_PLAYLIST_NAME = "Top"
RATING_TOP_LEVEL = 3


def _rating_top_playlist(db: Session) -> Playlist | None:
    return db.scalar(
        select(Playlist).where(Playlist.platform == "manual", Playlist.kind == "rating_top")
    )


def get_or_create_rating_top_playlist(db: Session) -> Playlist:
    """Al piu' una (kind='rating_top'), creata al primo voto 3."""
    playlist = _rating_top_playlist(db)
    if playlist is None:
        playlist = Playlist(platform="manual", name=RATING_TOP_PLAYLIST_NAME, kind="rating_top")
        db.add(playlist)
        db.flush()
    return playlist


def sync_rating_top(db: Session, track: Track) -> None:
    """Allinea membership e track_count della Top al voto corrente. Non committa."""
    from app.repositories import (
        add_track_to_playlist,
        recount_playlist,
        remove_track_from_playlist,
    )

    if track.rating == RATING_TOP_LEVEL:
        playlist = get_or_create_rating_top_playlist(db)
        add_track_to_playlist(db, track, playlist, added_by="cratory")
    else:
        playlist = _rating_top_playlist(db)
        if playlist is None:
            return  # nessun voto 3 finora: niente da allineare
        remove_track_from_playlist(db, playlist.id, track.id)
    # Il denormalizzato non resta mai indietro (lezione del fix conteggi).
    recount_playlist(db, playlist)
