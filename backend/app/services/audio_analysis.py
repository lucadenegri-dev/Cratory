"""Regole deterministiche di divergenza e apply per l'analisi BPM/key in-app.

Il job (audio_analysis_job) scrive SOLO analysis_*; queste funzioni sono l'unico
ponte verso i campi canonici bpm/camelot_key, sempre con source='cratory'.
Gerarchia fonti: manual > rekordbox > cratory. L'autorizzazione a sovrascrivere
sta nella SELEZIONE delle tracce (router/UI), non qui: apply_analysis applica e
basta, auto_apply_missing riempie solo i vuoti (nessun conflitto possibile)."""

from app.services.camelot import camelot_compatibility
from app.services.energy import apply_estimated_energy
from app.services.track_status import refresh_status


def diverges(track) -> bool:
    """True se l'analisi differisce dal canonico (BPM a 1 decimale, key esatta)."""
    bpm_div = (track.analysis_bpm is not None and track.bpm is not None
               and round(track.analysis_bpm, 1) != round(track.bpm, 1))
    key_div = (bool(track.analysis_camelot) and bool(track.camelot_key)
               and track.analysis_camelot != track.camelot_key)
    return bpm_div or key_div


def _apply(track, bpm_ok: bool, key_ok: bool) -> bool:
    changed = False
    # Scrive il BPM solo se differisce alla STESSA precisione (1 decimale) usata
    # da diverges(): cosi' un force-apply-all su un valore identico a 1 decimale
    # (es. 128.0 vs 128.04, rumore dell'analizzatore) resta un no-op e non
    # declassa silenziosamente bpm_source (manual/rekordbox -> cratory). Se il
    # canonico e' vuoto scrive comunque (auto_apply_missing / campo mancante).
    if (bpm_ok and track.analysis_bpm is not None
            and (track.bpm is None
                 or round(track.analysis_bpm, 1) != round(track.bpm, 1))):
        track.bpm = track.analysis_bpm
        track.bpm_source = "cratory"
        changed = True
    if key_ok and track.analysis_camelot and track.camelot_key != track.analysis_camelot:
        track.camelot_key = track.analysis_camelot
        track.key_source = "cratory"
        changed = True
    if changed:
        apply_estimated_energy(track)
        refresh_status(track)
    return changed


def apply_analysis(track) -> bool:
    """Copia i valori analysis_* nei canonici dove esistono. True se ha scritto."""
    return _apply(track, bpm_ok=True, key_ok=True)


def auto_apply_missing(track) -> bool:
    """Fallback automatico post-job: riempie SOLO i campi vuoti."""
    return _apply(track, bpm_ok=track.bpm is None, key_ok=not track.camelot_key)


def divergence_row(track) -> dict:
    level, _ = camelot_compatibility(track.camelot_key, track.analysis_camelot)
    delta = (round(track.analysis_bpm - track.bpm, 1)
             if track.analysis_bpm is not None and track.bpm is not None else None)
    return {
        "track_id": track.id, "artist": track.artist, "title": track.title,
        "bpm": track.bpm, "bpm_source": track.bpm_source,
        "analysis_bpm": track.analysis_bpm, "bpm_delta": delta,
        "camelot_key": track.camelot_key, "key_source": track.key_source,
        "analysis_camelot": track.analysis_camelot,
        "key_compatibility": level,
    }
