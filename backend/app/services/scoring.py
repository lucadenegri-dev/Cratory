"""Scoring tecnico deterministico delle transizioni tra due tracce.

Composizione score (0-100), tutta basata su dati ottenuti dall'enrichment esterno
(lo streaming non da' BPM/key): cue/beatgrid/play_count Rekordbox non esistono piu'.
- BPM:    max 50  (0-2 ottimo, 2-5 buono, 5-8 rischioso, >8 difficile)
- Camelot: max 40  (stessa key / compatibile / debole)
- Durata: max 10  (penalita' per tracce molto corte)
"""

from dataclasses import dataclass, field

from app.models import Track
from app.services.camelot import camelot_compatibility

SHORT_TRACK_SECONDS = 90


@dataclass
class TransitionScore:
    score: int
    technical_reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def risk_from_score(score: float | None) -> str:
    """Classifica il rischio di una transizione dal suo score tecnico (0-100)."""
    if score is None:
        return "low"  # traccia di apertura
    if score >= 70:
        return "low"
    if score >= 45:
        return "medium"
    return "high"


# --- F10: classificazione semantica della transizione ------------------------
# Etichetta leggibile per il DJ, costruita sopra gli score deterministici. Distingue
# un mix tecnicamente sicuro da uno stacco voluto (cambio di energia/genere per
# "resettare" la pista) o da un azzardo creativo (salto BPM/key deliberato).

SAFE_CLASSIFICATION_SCORE = 70  # sopra questo: transizione tecnicamente sicura
RESET_ENERGY_DROP = 15          # calo di energia (0-100) che segnala un reset voluto
RESET_GENRE_SIMILARITY = 45     # sotto questa similarità i generi sono "diversi"
#                                 (generi senza token in comune valgono 40)


@dataclass
class TransitionClassification:
    label: str       # technically_safe | creative_risk | good_reset
    label_it: str    # etichetta leggibile in italiano
    reason: str


def classify_transition(from_track: Track, to_track: Track) -> TransitionClassification:
    """Classifica una transizione in technically_safe | creative_risk | good_reset.

    - technically_safe: BPM/key compatibili (score tecnico alto), rischio basso.
    - good_reset: stacco netto voluto (forte calo di energia o cambio di genere),
      utile per "resettare" la pista.
    - creative_risk: salto di BPM/tonalità deliberato ma azzardato.
    """
    score = score_transition(from_track, to_track).score
    if score >= SAFE_CLASSIFICATION_SCORE:
        return TransitionClassification(
            "technically_safe", "tecnicamente sicura",
            "BPM e tonalità compatibili: mix sicuro",
        )

    energy_delta = None
    if from_track.energy is not None and to_track.energy is not None:
        energy_delta = to_track.energy - from_track.energy
    big_energy_drop = energy_delta is not None and energy_delta <= -RESET_ENERGY_DROP

    genre_change = bool(
        from_track.genre and to_track.genre
        and genre_similarity_score(from_track.genre, to_track.genre) < RESET_GENRE_SIMILARITY
    )

    if big_energy_drop or genre_change:
        bits = []
        if big_energy_drop:
            bits.append(f"calo di energia ({energy_delta:+d})")
        if genre_change:
            bits.append("cambio di genere")
        return TransitionClassification(
            "good_reset", "reset voluto",
            f"Stacco netto ({', '.join(bits)}): utile per resettare la pista",
        )

    return TransitionClassification(
        "creative_risk", "azzardo creativo",
        "Salto di BPM/tonalità voluto ma azzardato: gestire con cura",
    )


def mixing_tip(from_track: Track, to_track: Track) -> str:
    """Istruzione concisa e DETERMINISTICA su come mixare due brani consecutivi.

    Tutto dai dati di enrichment (BPM, Camelot, energia): niente AI, niente id.
    Pensata per il DJ: cosa fare in pratica per passare dal brano precedente a questo.
    """
    parts: list[str] = []

    fb, tb = from_track.bpm, to_track.bpm
    if fb and tb:
        delta = tb - fb
        ad = abs(delta)
        if ad <= 0.5:
            parts.append("stesso BPM: beatmatch diretto")
        elif ad <= 2:
            parts.append(f"{delta:+.0f} BPM: ritocca il pitch, blend lungo")
        elif ad <= 5:
            parts.append(f"{delta:+.0f} BPM: pitch bend o blend graduale sull'intro")
        elif ad <= 8:
            parts.append(f"{delta:+.0f} BPM: salto deciso, usa un break o un EQ blend")
        else:
            parts.append(f"{delta:+.0f} BPM: stacco netto, meglio un cut o una traccia ponte")
    else:
        parts.append("BPM mancante: sincronizza a orecchio")

    level, _ = camelot_compatibility(from_track.camelot_key, to_track.camelot_key)
    fk, tk = from_track.camelot_key, to_track.camelot_key
    if level == "same":
        parts.append(f"{fk} stessa key: mix armonico totale")
    elif level == "compatible":
        parts.append(f"{fk}→{tk} compatibile: mix armonico")
    elif level == "weak":
        parts.append(f"{fk}→{tk} fuori chiave: mix breve o maschera con l'EQ")
    # level == "unknown": tonalità mancante, nessun consiglio armonico

    fe, te = from_track.energy, to_track.energy
    if fe is not None and te is not None:
        ed = te - fe
        if ed >= 12:
            parts.append("porta su l'energia")
        elif ed <= -12:
            parts.append("scarica l'energia (reset)")

    return " · ".join(parts)


def mixing_overview(tracks: list[Track]) -> list[str]:
    """Piano di mixaggio del set, DETERMINISTICO: una sintesi tecnica di come legare
    i brani (armonia, salti di BPM, arco di energia). Complementa i `mixing_tip` per
    traccia con la visione d'insieme. I numeri di brano sono le posizioni 1-based.
    """
    pairs = list(zip(tracks, tracks[1:]))
    if not pairs:
        return []
    bullets: list[str] = []

    def at_tracks(positions: list[int]) -> str:
        nums = ", ".join(str(p) for p in positions)
        return f"al brano {nums}" if len(positions) == 1 else f"ai brani {nums}"

    # Armonia (Camelot)
    harmonic = weak = known = 0
    for a, b in pairs:
        level, _ = camelot_compatibility(a.camelot_key, b.camelot_key)
        if level in ("same", "compatible"):
            harmonic += 1
            known += 1
        elif level == "weak":
            weak += 1
            known += 1
    if known:
        s = f"Armonia: {harmonic}/{known} cambi in chiave (mix armonico Camelot)."
        if weak:
            s += f" {weak} fuori chiave: tienili brevi o maschera con l'EQ."
        bullets.append(s)

    # BPM: arco e salti che richiedono un cut/ponte
    bpms = [t.bpm for t in tracks if t.bpm]
    jumps = [i + 2 for i, (a, b) in enumerate(pairs) if a.bpm and b.bpm and abs(b.bpm - a.bpm) > 8]
    if bpms:
        arc = f"BPM da {min(bpms):.0f} a {max(bpms):.0f}"
        if jumps:
            noun = "salto marcato" if len(jumps) == 1 else "salti marcati"
            bullets.append(f"{arc}: {noun} {at_tracks(jumps)} — meglio un cut su un break o una traccia ponte; altrove beatmatch e blend lungo.")
        else:
            bullets.append(f"{arc}: differenze contenute, lega in beatmatch con blend graduale sull'intro.")

    # Energia: andamento e reset
    energies = [t.energy for t in tracks if t.energy is not None]
    resets = [i + 2 for i, (a, b) in enumerate(pairs)
              if a.energy is not None and b.energy is not None and b.energy - a.energy <= -15]
    if len(energies) >= 2:
        delta = energies[-1] - energies[0]
        trend = "in salita" if delta >= 8 else "in discesa" if delta <= -8 else "stabile"
        s = f"Energia {trend} ({energies[0]} → {energies[-1]})."
        if resets:
            noun = "Stacco di reset" if len(resets) == 1 else "Stacchi di reset"
            s += f" {noun} {at_tracks(resets)}: sfrutta il calo per cambiare zona."
        bullets.append(s)

    return bullets


def _bpm_points(from_bpm: float | None, to_bpm: float | None) -> tuple[float, str, str | None]:
    if not from_bpm or not to_bpm:
        return 25.0, "BPM mancante su una delle tracce: valutazione neutra", "BPM mancante"
    diff = abs(from_bpm - to_bpm)
    if diff <= 2:
        return 50.0, f"differenza BPM ottima ({diff:.1f})", None
    if diff <= 5:
        return 38.0, f"differenza BPM buona ({diff:.1f})", None
    if diff <= 8:
        return 20.0, f"differenza BPM rischiosa ({diff:.1f})", f"salto BPM di {diff:.1f}: transizione rischiosa"
    return 5.0, f"differenza BPM difficile ({diff:.1f})", f"salto BPM di {diff:.1f}: transizione difficile"


def _key_points(from_key: str | None, to_key: str | None) -> tuple[float, str, str | None]:
    level, desc = camelot_compatibility(from_key, to_key)
    if level == "same":
        return 40.0, desc, None
    if level == "compatible":
        return 32.0, desc, None
    if level == "unknown":
        return 18.0, desc, "tonalita' non confrontabile"
    return 10.0, desc, "key poco compatibili: mix armonico difficile"


def score_transition(from_track: Track, to_track: Track) -> TransitionScore:
    reasons: list[str] = []
    warnings: list[str] = []
    total = 0.0

    pts, reason, warn = _bpm_points(from_track.bpm, to_track.bpm)
    total += pts
    reasons.append(reason)
    if warn:
        warnings.append(warn)

    pts, reason, warn = _key_points(from_track.camelot_key, to_track.camelot_key)
    total += pts
    reasons.append(reason)
    if warn:
        warnings.append(warn)

    # Durata (max 10): penalizza solo le tracce molto corte
    structure = 10.0
    duration = to_track.duration_seconds or 0
    if duration and duration < SHORT_TRACK_SECONDS:
        structure -= 8.0
        warnings.append(f"traccia in entrata molto corta ({duration}s)")
    total += max(structure, 0.0)

    return TransitionScore(
        score=max(0, min(100, round(total))),
        technical_reasons=reasons,
        warnings=warnings,
    )


# --- I sei score deterministici (nuovo_progetto.md sez. 5) -------------------
# Tutti 0-100, standalone. `score_transition` (sopra) resta il composito pesato
# usato per il ranking; queste funzioni espongono i singoli score per traccia in
# modo confrontabile. In assenza del dato ritornano un valore neutro (50).


def bpm_compatibility_score(from_bpm: float | None, to_bpm: float | None) -> int:
    """Compatibilita' di tempo (0-100). Stessa scala a gradini di `_bpm_points`."""
    if not from_bpm or not to_bpm:
        return 50
    diff = abs(from_bpm - to_bpm)
    if diff <= 2:
        return 100
    if diff <= 5:
        return 75
    if diff <= 8:
        return 40
    return max(10, 40 - round((diff - 8) * 4))


def key_compatibility_score(from_key: str | None, to_key: str | None) -> int:
    """Compatibilita' armonica Camelot (0-100)."""
    level, _ = camelot_compatibility(from_key, to_key)
    return {"same": 100, "compatible": 80, "weak": 25}.get(level, 50)  # unknown -> neutro


def energy_progression_score(from_energy: int | None, to_energy: int | None) -> int:
    """Premia una progressione di energia dolce e monotona; penalizza i crolli bruschi."""
    if from_energy is None or to_energy is None:
        return 50
    delta = to_energy - from_energy
    if -5 <= delta <= 12:
        return 100  # leggera salita o plateau: ideale lungo il set
    if delta > 12:
        return max(40, 100 - (delta - 12) * 3)  # salita troppo brusca
    return max(20, 100 + delta * 2)  # crollo di energia


def mood_coherence_score(from_mood: str | None, to_mood: str | None) -> int:
    if not from_mood or not to_mood:
        return 50
    return 100 if from_mood.strip().lower() == to_mood.strip().lower() else 60


def genre_similarity_score(from_genre: str | None, to_genre: str | None) -> int:
    """Similarita' grezza basata sulla sovrapposizione dei token di genere."""
    if not from_genre or not to_genre:
        return 50
    a = {g.strip().lower() for g in from_genre.replace(",", " ").split() if g.strip()}
    b = {g.strip().lower() for g in to_genre.replace(",", " ").split() if g.strip()}
    if not a or not b:
        return 50
    overlap = len(a & b) / len(a | b)
    return round(40 + overlap * 60)
