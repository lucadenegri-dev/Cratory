"""Il materiale di un set manuale: la playlist di origine letta AGGIORNATA,
piu' le tracce gia' nel set, piu' (con `q`) la ricerca in libreria.
Nessuna membership copiata (spec 2026-09-15, "Materiale = playlist aggiornata")."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import Setlist, Track
from app.repositories import list_tracks, tracks_for_playlist

SEARCH_LIMIT = 50


def material_for(db: Session, setlist: Setlist, *, q: str | None, owned: bool, unused: bool,
                 reserved: bool = False,
                 ) -> list[tuple[Track, bool, bool, bool]]:
    """Ritorna (track, in_set, from_playlist, in_reserve) in ordine: playlist,
    poi tracce del set fuori playlist, poi risultati di ricerca. Senza `q`
    niente ricerca. `in_set` e' il PERCORSO: una riga di riserva non ci entra."""
    in_set = {st.track_id for st in setlist.tracks
              if st.track_id is not None and st.block_id is not None}
    in_reserve = {st.track_id for st in setlist.tracks
                  if st.track_id is not None and st.block_id is None}
    items: list[tuple[Track, bool, bool, bool]] = []
    seen: set[int] = set()

    def push(track: Track, from_playlist: bool) -> None:
        if track.id in seen:
            return
        seen.add(track.id)
        items.append((track, track.id in in_set, from_playlist, track.id in in_reserve))

    if setlist.source_playlist_id is not None:
        for track in tracks_for_playlist(db, setlist.source_playlist_id):
            push(track, True)
    for st in sorted(setlist.tracks, key=lambda s: (s.block_id or 0, s.position)):
        if st.track is not None:
            push(st.track, False)
    query = (q or "").strip()
    if query:
        _, rows = list_tracks(db, limit=SEARCH_LIMIT, q=query)
        for track, _tags in rows:
            push(track, False)
        items = [it for it in items if _matches(it[0], query)]
    if owned:
        items = [it for it in items if it[0].has_local_file]
    if unused:
        items = [it for it in items if not it[1]]
    if reserved:
        items = [it for it in items if it[3]]
    return items


def _matches(track: Track, query: str) -> bool:
    needle = query.lower()
    return needle in (track.artist or "").lower() or needle in (track.title or "").lower()
