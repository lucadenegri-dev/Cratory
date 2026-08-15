"""Regole deterministiche di divergenza e apply per l'analisi BPM/key in-app.

Il job (audio_analysis_job) scrive SOLO analysis_*; queste funzioni sono l'unico
ponte verso i campi canonici bpm/camelot_key, sempre con source='cratory'.
Gerarchia fonti: manual > rekordbox > cratory. L'autorizzazione a sovrascrivere
sta nella SELEZIONE delle tracce (router/UI), non qui: apply_analysis applica e
basta, auto_apply_missing riempie solo i vuoti (nessun conflitto possibile).

Lo scarto (dismiss_divergence) non tocca ne' i canonici ne' analysis_*: salva
solo lo snapshot dismissed_*; is_dismissed lo confronta con l'analisi corrente."""

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


def dismiss_divergence(track) -> None:
    """Fotografa l'esito corrente dell'analisi come «visto e ignorato»."""
    track.analysis_dismissed_bpm = track.analysis_bpm
    track.analysis_dismissed_camelot = track.analysis_camelot


def is_dismissed(track) -> bool:
    """True se lo snapshot scartato coincide con l'analisi corrente, alla
    stessa precisione di diverges(): BPM a 1 decimale (None==None), key esatta
    (vuoto==vuoto). Una nuova analisi con esito diverso lo invalida da sola."""
    bpm_same = (
        (track.analysis_bpm is None) == (track.analysis_dismissed_bpm is None)
        and (track.analysis_bpm is None
             or round(track.analysis_bpm, 1) == round(track.analysis_dismissed_bpm, 1))
    )
    key_same = (track.analysis_camelot or None) == (track.analysis_dismissed_camelot or None)
    return bpm_same and key_same


def open_divergence(track) -> bool:
    """Divergenza aperta: diverge dal canonico E non e' stata scartata."""
    return diverges(track) and not is_dismissed(track)


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
