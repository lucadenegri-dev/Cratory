"""Regole deterministiche di divergenza e apply per l'analisi BPM/key in-app.

Il job (audio_analysis_job) scrive SOLO analysis_*; queste funzioni sono l'unico
ponte verso i campi canonici bpm/camelot_key, sempre con source='cratory'.
Gerarchia fonti: manual > rekordbox > cratory. L'autorizzazione a sovrascrivere
sta nella SELEZIONE delle tracce (router/UI), non qui: apply_analysis applica e
basta, auto_apply_missing riempie solo i vuoti (nessun conflitto possibile).

Lo scarto (dismiss_divergence) non tocca i valori veri (ne' i canonici ne'
analysis_*): salva uno snapshot di ENTRAMBI i lati (analizzato e canonico);
is_dismissed richiede che entrambi coincidano ancora col loro snapshot, cosi'
un PATCH manuale o un import Rekordbox successivo alla scarto non resta
invisibile per sempre dietro un esito Essentia deterministico e immutato."""

from app.services.camelot import camelot_compatibility
from app.services.energy import apply_estimated_energy
from app.services.track_status import refresh_status


def _bpm_matches(a: float | None, b: float | None) -> bool:
    """Confronto BPM None-safe a 1 decimale, la precisione usata ovunque in
    questo modulo (diverges, _apply, is_dismissed su entrambi i lati)."""
    if a is None or b is None:
        return a is None and b is None
    return round(a, 1) == round(b, 1)


def diverges(track) -> bool:
    """True se l'analisi differisce dal canonico (BPM a 1 decimale, key esatta)."""
    bpm_div = (track.analysis_bpm is not None and track.bpm is not None
               and not _bpm_matches(track.analysis_bpm, track.bpm))
    key_div = (bool(track.analysis_camelot) and bool(track.camelot_key)
               and track.analysis_camelot != track.camelot_key)
    return bpm_div or key_div


def dismiss_divergence(track) -> None:
    """Fotografa l'esito corrente come «visto e ignorato»: sia il lato
    analizzato sia il lato canonico, cosi' una mutazione futura di uno solo
    dei due riapre la divergenza."""
    track.analysis_dismissed_bpm = track.analysis_bpm
    track.analysis_dismissed_camelot = track.analysis_camelot
    track.analysis_dismissed_of_bpm = track.bpm
    track.analysis_dismissed_of_camelot = track.camelot_key


def is_dismissed(track) -> bool:
    """True se lo snapshot scartato coincide ANCORA con lo stato corrente su
    entrambi i lati, alla stessa precisione di diverges(): BPM a 1 decimale
    (None==None), key esatta (vuoto==vuoto). Una nuova analisi con esito
    diverso, o una mutazione del canonico (PATCH, import Rekordbox), invalida
    lo scarto da sola. Una traccia mai analizzata e mai scartata non e'
    "dismissed": senza questa guardia il default None/None combacerebbe con
    None/None per costruzione, un trabocchetto per un futuro chiamante che non
    passi per open_divergence (che gia' filtra su diverges())."""
    if track.analysis_bpm is None and not track.analysis_camelot:
        return False
    bpm_same = _bpm_matches(track.analysis_bpm, track.analysis_dismissed_bpm)
    key_same = (track.analysis_camelot or None) == (track.analysis_dismissed_camelot or None)
    bpm_of_same = _bpm_matches(track.bpm, track.analysis_dismissed_of_bpm)
    key_of_same = (track.camelot_key or None) == (track.analysis_dismissed_of_camelot or None)
    # I quattro confronti sono in AND: un cambio sul canonico riapre lo scarto
    # anche quando tocca il lato che da solo non potrebbe divergere (es. il BPM
    # canonico si riempie dopo uno scarto su una divergenza di sola key). Non e'
    # un bug: e' deliberato, ed erra verso la visibilita', la direzione sicura
    # in assenza di una UI di recupero per le righe scartate.
    return bpm_same and key_same and bpm_of_same and key_of_same


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
            and not _bpm_matches(track.analysis_bpm, track.bpm)):
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
