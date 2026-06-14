"""Candidate Engine deterministico: seleziona il sottoinsieme di tracce candidate
per la costruzione di un set. In MVP 3 sara' anche il filtro a monte dell'AI Agent.
"""

from sqlalchemy.orm import Session

from app.models import Track
from app.repositories import all_playable_tracks, tracks_for_playlist
from app.schemas import SetGenerationRequest

MIN_TRACK_SECONDS = 120  # esclude sample/oneshot del sampler Rekordbox
BPM_WINDOW_TOLERANCE = 12.0


def select_candidates(db: Session, req: SetGenerationRequest) -> list[Track]:
    # Nuovo flusso: se e' indicata una playlist, il set nasce SOLO da quelle tracce
    # (servono comunque BPM/key, quindi solo le tracce arricchite sono candidate).
    if req.playlist_id:
        tracks = [t for t in tracks_for_playlist(db, req.playlist_id) if t.bpm is not None]
    else:
        tracks = all_playable_tracks(db)
    candidates: list[Track] = []

    bpm_lo = bpm_hi = None
    declared = [b for b in (req.start_bpm, req.end_bpm) if b]
    if declared:
        bpm_lo = min(declared) - BPM_WINDOW_TOLERANCE
        bpm_hi = max(declared) + BPM_WINDOW_TOLERANCE

    min_duration = MIN_TRACK_SECONDS if req.avoid_short_tracks else 30
    seeds = [s.lower() for s in req.seed_artists]
    genre = req.genre.lower() if req.genre else None

    for t in tracks:
        if req.sources and t.source_type not in req.sources:
            continue
        if (t.duration_seconds or 0) < min_duration:
            continue
        if bpm_lo is not None and t.bpm and not (bpm_lo <= t.bpm <= bpm_hi):
            continue
        candidates.append(t)

    # Il filtro genere e' soft: nel dataset reale Genre e' quasi sempre vuoto
    # (arrivera' dagli artist genres Spotify in MVP 2). Se il filtro stretto
    # svuota la lista, si ignora.
    if genre:
        strict = [t for t in candidates if t.genre and genre in t.genre.lower()]
        if strict:
            candidates = strict

    # Gli artisti seed non filtrano: garantiscono presenza, gestiti dal generator.
    _ = seeds
    return candidates
