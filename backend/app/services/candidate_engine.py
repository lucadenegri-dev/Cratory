"""Candidate Engine deterministico: seleziona il sottoinsieme di tracce candidate
per la costruzione di un set. In MVP 3 sara' anche il filtro a monte dell'AI Agent.
"""

import re
import unicodedata

from sqlalchemy.orm import Session

from app.models import Track
from app.repositories import all_playable_tracks, tracks_for_playlist
from app.schemas import SetGenerationRequest

MIN_TRACK_SECONDS = 120  # esclude sample/oneshot del sampler Rekordbox
BPM_WINDOW_TOLERANCE = 12.0


def _norm(value: str | None) -> str:
    ascii_ = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", ascii_.lower()).strip()


def _fuzzy_key(track: Track) -> str:
    """Chiave normalizzata artista+titolo per la dedup: accenti/punteggiatura/case
    ignorati, e un eventuale prefisso «artista - » nel titolo rimosso (es. la stessa
    traccia salvata come "Raär – Sirens" e "Raar - Raar - Sirens")."""
    artist = _norm(track.artist)
    title = _norm(track.title)
    if artist and title.startswith(artist + " "):
        title = title[len(artist) + 1:]
    return f"{artist}|{title}"


def _dedupe_fuzzy(tracks: list[Track]) -> list[Track]:
    """Collassa i duplicati fuzzy (stesso brano, grafie diverse). Preferisce la copia
    posseduta; a parità tiene la prima. Le tracce senza artista né titolo non si toccano."""
    result: list[Track] = []
    seen: dict[str, int] = {}  # chiave fuzzy -> indice in result
    for t in tracks:
        key = _fuzzy_key(t)
        if key == "|":  # niente identità testuale: non deduplicare
            result.append(t)
        elif key not in seen:
            seen[key] = len(result)
            result.append(t)
        elif t.has_local_file and not result[seen[key]].has_local_file:
            result[seen[key]] = t  # la copia posseduta vince
    return result


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
        if req.owned_only and not t.has_local_file:
            continue
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
    # Duplicati fuzzy (stesso brano in grafie diverse): un set non deve ripeterlo.
    return _dedupe_fuzzy(candidates)
