"""«Riempi il varco»: il generatore come strumento dentro un set preparato a mano.

Non e' un generatore nuovo — e' `_beam_search_span`, lo stesso del set builder,
con il criterio di stop a conteggio. Deterministico e senza AI: `mood_scores`
resta None, che e' l'unico gancio da cui la curatela potrebbe entrare.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import Setlist, SetlistTrack, Track
from app.services.manual_material import material_for
from app.services.manual_set import ManualSetError, path_rows, resolved_path
from app.services.set_generator import BeamParams, _beam_search_span
from app.services.set_skeleton import strategy_profile


class FillError(ManualSetError):
    pass


def _vicini(setlist: Setlist, gap: SetlistTrack) -> tuple[SetlistTrack | None, SetlistTrack | None]:
    """Le righe con traccia che stanno subito prima e subito dopo il varco, nel
    percorso. Un varco in testa o in coda ne ha una sola, e va benissimo."""
    righe = path_rows(setlist)
    at = next(i for i, r in enumerate(righe) if r.id == gap.id)
    prima = next((r for r in reversed(righe[:at]) if r.track is not None), None)
    dopo = next((r for r in righe[at + 1:] if r.track is not None), None)
    return prima, dopo


def propose_fill(db: Session, setlist: Setlist, gap: SetlistTrack, *, count: int) -> list[Track]:
    # material_for ritorna tuple (track, in_set, from_playlist, in_reserve),
    # NON un oggetto con .items: quello e' il MaterialOut del serializer.
    materiale = material_for(db, setlist, q=None, owned=False, unused=False, reserved=False)
    gia_nel_percorso = {r.track_id for r in resolved_path(setlist)}
    pool = [track for track, *_ in materiale if track.id not in gia_nel_percorso]
    if not pool:
        raise FillError("No material left to fill this gap")

    prima, dopo = _vicini(setlist, gap)
    opener = prima.track if prima is not None else pool[0]
    if prima is None:
        # Varco in testa: la prima proposta fa da opener e non e' un "filler",
        # quindi va tolta dal pool e riaggiunta in cima al risultato.
        pool = pool[1:]

    start = (prima.play_bpm or prima.track.bpm) if prima is not None else opener.bpm
    end = (dopo.play_bpm or dopo.track.bpm) if dopo is not None else start
    quanti = count if prima is not None else count - 1

    fillers = []
    if quanti > 0 and pool:
        req = BeamParams()
        fillers = _beam_search_span(
            opener, pool, req, strategy_profile("smooth"),
            start_bpm=start or 124.0, end_bpm=end or start or 124.0,
            target_seconds=3600, elapsed_secs=0, fill_until_secs=3600,
            converge_to=dopo.track if dopo is not None else None,
            mood_scores=None,           # nessuna AI: e' il gancio della curatela
            max_count=quanti,
        )
    proposte = [t for t, _ in fillers]
    if prima is None:
        proposte = [opener] + proposte
    if not proposte:
        raise FillError("The generator found nothing for this gap")
    return proposte[:count]
