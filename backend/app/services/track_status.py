"""Stato deterministico della traccia (disk-first, post-slim-down).

Stati:
- imported      : nessun BPM+key (non usabile dal Set Builder).
- ready_for_set : ha BPM e key (Camelot) -> usabile dal Set Builder.

BPM/key arrivano da Rekordbox (import XML). Gli stati enriched/missing_features/
low_confidence sono stati rimossi con il motore di enrichment.
"""

from app.models import Track


def compute_status(track: Track) -> str:
    if track.bpm is not None and bool(track.camelot_key):
        return "ready_for_set"
    return "imported"


def refresh_status(track: Track) -> str:
    track.status = compute_status(track)
    return track.status
