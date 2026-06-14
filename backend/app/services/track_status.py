"""Calcolo deterministico dello stato di una traccia nel nuovo flusso playlist->set.

Stati (vedi nuovo_progetto.md sez. 2):
- imported          : appena importata, nessun arricchimento musicale.
- enriched          : ha ricevuto enrichment ma mancano feature chiave per il set.
- ready_for_set     : ha BPM e key (Camelot) -> usabile dal Set Builder.
- missing_features  : enrichment tentato ma BPM/key ancora assenti.
- low_confidence    : match dell'enrichment a bassa confidenza (dato poco affidabile).

Il Set Builder considera "usabili" le tracce con BPM e key presenti; le altre
restano in libreria ma vengono segnalate (e tipicamente escluse dalle candidate).
"""

from app.models import Track

LOW_CONFIDENCE_THRESHOLD = 50  # sotto questa confidenza l'enrichment e' "low_confidence"


def _has_key(track: Track) -> bool:
    return bool(track.camelot_key)


def compute_status(track: Track) -> str:
    has_core = track.bpm is not None and _has_key(track)
    enriched = track.enriched_at is not None or track.enrichment_source is not None

    if has_core:
        if track.enrichment_confidence is not None and track.enrichment_confidence < LOW_CONFIDENCE_THRESHOLD:
            return "low_confidence"
        return "ready_for_set"
    if enriched:
        return "missing_features"
    return "imported"


def refresh_status(track: Track) -> str:
    track.status = compute_status(track)
    return track.status
