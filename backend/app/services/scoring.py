"""Scoring tecnico deterministico delle transizioni tra due tracce.

Composizione score (0-100), tutta basata su dati ottenuti dall'enrichment esterno
(lo streaming non da' BPM/key): cue/beatgrid/play_count Rekordbox non esistono piu'.
- BPM:    max 50  (0-2 ottimo, 2-5 buono, 5-8 rischioso, >8 difficile)
- Camelot: max 40  (stessa key / compatibile / debole)
- Durata: max 10  (penalita' per tracce molto corte)
"""

import re
from dataclasses import dataclass, field

from app.models import Track
from app.services.camelot import camelot_compatibility, camelot_score

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

_LANGS = ("it", "en")

# --- Cataloghi di frasi per lingua --------------------------------------------
# Le frasi generate (reason, mixing tip/overview) sono deterministiche ma
# bilingui: il codice sceglie SEMPRE il testo dal catalogo, mai stringhe
# hardcoded fuori da qui. `label` (il codice enum) resta indipendente dalla
# lingua: la label leggibile la traduce il frontend (namespace `transitionLabels`).

_REASONS = {
    "harmonic_safe": {
        "it": "BPM e tonalità compatibili: mix sicuro",
        "en": "Compatible BPM and key: safe mix",
    },
    "energy_drop": {"it": "calo di energia ({delta:+d})", "en": "energy drop ({delta:+d})"},
    "genre_change": {"it": "cambio di genere", "en": "genre change"},
    "reset": {
        "it": "Stacco netto ({bits}): utile per resettare la pista",
        "en": "Hard cut ({bits}): useful to reset the floor",
    },
    "key_clash": {
        "it": "Beatmatch facile ma tonalità in contrasto: mix breve o maschera con l'EQ",
        "en": "Easy beatmatch but clashing keys: keep the mix short or mask with EQ",
    },
    "creative_jump": {
        "it": "Salto di BPM/tonalità voluto ma azzardato: gestire con cura",
        "en": "Deliberate but risky BPM/key jump: handle with care",
    },
}


def _txt(key: str, lang: str, **fmt) -> str:
    return _REASONS[key][lang if lang in _LANGS else "it"].format(**fmt)


@dataclass
class TransitionClassification:
    label: str       # technically_safe | creative_risk | good_reset (indipendente dalla lingua)
    reason: str


def classify_transition(from_track: Track, to_track: Track, lang: str = "it") -> TransitionClassification:
    """Classifica una transizione in technically_safe | creative_risk | good_reset.

    - technically_safe: BPM/key compatibili (score tecnico alto), rischio basso.
    - good_reset: stacco netto voluto (forte calo di energia o cambio di genere),
      utile per "resettare" la pista.
    - creative_risk: salto di BPM/tonalità deliberato ma azzardato.

    `lang` ("it" | "en") sceglie la lingua di `reason`; `label` resta il codice enum,
    tradotto in etichetta leggibile lato frontend.
    """
    score = score_transition(from_track, to_track).score
    level, _ = camelot_compatibility(from_track.camelot_key, to_track.camelot_key)
    harmonic_ok = level in ("same", "compatible")
    # "Sicura" richiede ANCHE l'armonia: un BPM perfetto con key stonata non è un mix sicuro.
    if score >= SAFE_CLASSIFICATION_SCORE and harmonic_ok:
        return TransitionClassification("technically_safe", _txt("harmonic_safe", lang))

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
            bits.append(_txt("energy_drop", lang, delta=energy_delta))
        if genre_change:
            bits.append(_txt("genre_change", lang))
        return TransitionClassification("good_reset", _txt("reset", lang, bits=", ".join(bits)))

    # BPM in riga ma key in contrasto: azzardo di sola tonalità, non un salto di tempo.
    bpm_close = False
    if from_track.bpm and to_track.bpm:
        bpm_close = effective_bpm_diff(from_track.bpm, to_track.bpm)[0] <= 5
    if bpm_close and not harmonic_ok:
        return TransitionClassification("creative_risk", _txt("key_clash", lang))
    return TransitionClassification("creative_risk", _txt("creative_jump", lang))


_TIPS = {
    "halftime": {
        "it": "mezzo/doppio tempo: allinea la griglia sul break",
        "en": "half/double time: align the grid on the break",
    },
    "same_bpm": {"it": "stesso BPM: beatmatch diretto", "en": "same BPM: direct beatmatch"},
    "bpm_nudge": {
        "it": "{delta:+.0f} BPM: ritocca il pitch, blend lungo",
        "en": "{delta:+.0f} BPM: nudge the pitch, long blend",
    },
    "bpm_gradual": {
        "it": "{delta:+.0f} BPM: pitch bend o blend graduale sull'intro",
        "en": "{delta:+.0f} BPM: pitch bend or gradual blend on the intro",
    },
    "bpm_sharp": {
        "it": "{delta:+.0f} BPM: salto deciso, usa un break o un EQ blend",
        "en": "{delta:+.0f} BPM: sharp jump, use a break or an EQ blend",
    },
    "bpm_hardcut": {
        "it": "{delta:+.0f} BPM: stacco netto, meglio un cut o una traccia ponte",
        "en": "{delta:+.0f} BPM: hard cut, better a cut or a bridge track",
    },
    "bpm_missing": {"it": "BPM mancante: sincronizza a orecchio", "en": "Missing BPM: sync by ear"},
    "key_same": {
        "it": "{fk} stessa key: mix armonico totale",
        "en": "{fk} same key: fully harmonic mix",
    },
    "key_compatible": {
        "it": "{fk}→{tk} compatibile: mix armonico",
        "en": "{fk}→{tk} compatible: harmonic mix",
    },
    "key_weak": {
        "it": "{fk}→{tk} fuori chiave: mix breve o maschera con l'EQ",
        "en": "{fk}→{tk} out of key: keep the mix short or mask with EQ",
    },
    "energy_up": {"it": "porta su l'energia", "en": "bring the energy up"},
    "energy_down": {"it": "scarica l'energia (reset)", "en": "drop the energy (reset)"},
    "opening_track": {"it": "apertura", "en": "opener"},
    "at_track_one": {"it": "al brano {nums}", "en": "at track {nums}"},
    "at_track_many": {"it": "ai brani {nums}", "en": "at tracks {nums}"},
    "overview_harmony": {
        "it": "Armonia: {harmonic}/{known} cambi in chiave (mix armonico Camelot).",
        "en": "Harmony: {harmonic}/{known} changes in key (Camelot harmonic mix).",
    },
    "overview_harmony_weak": {
        "it": " {weak} fuori chiave: tienili brevi o maschera con l'EQ.",
        "en": " {weak} out of key: keep them short or mask with EQ.",
    },
    "overview_bpm_arc": {"it": "BPM da {lo:.0f} a {hi:.0f}", "en": "BPM from {lo:.0f} to {hi:.0f}"},
    "overview_bpm_jump_one": {"it": "salto marcato", "en": "sharp jump"},
    "overview_bpm_jump_many": {"it": "salti marcati", "en": "sharp jumps"},
    "overview_bpm_jump_line": {
        "it": "{arc}: {noun} {at} — meglio un cut su un break o una traccia ponte; altrove beatmatch e blend lungo.",
        "en": "{arc}: {noun} {at} — better a cut on a break or a bridge track; elsewhere beatmatch and long blend.",
    },
    "overview_bpm_smooth_line": {
        "it": "{arc}: differenze contenute, lega in beatmatch con blend graduale sull'intro.",
        "en": "{arc}: contained differences, link in beatmatch with a gradual blend on the intro.",
    },
    "overview_energy_trend_up": {"it": "in salita", "en": "climbing"},
    "overview_energy_trend_down": {"it": "in discesa", "en": "dropping"},
    "overview_energy_trend_stable": {"it": "stabile", "en": "stable"},
    "overview_energy_line": {
        "it": "Energia {trend} ({e0} → {e1}).",
        "en": "Energy {trend} ({e0} → {e1}).",
    },
    "overview_reset_one": {"it": "Stacco di reset", "en": "Reset break"},
    "overview_reset_many": {"it": "Stacchi di reset", "en": "Reset breaks"},
    "overview_reset_line": {
        "it": " {noun} {at}: sfrutta il calo per cambiare zona.",
        "en": " {noun} {at}: use the drop to change zone.",
    },
}


def _tip(key: str, lang: str, **fmt) -> str:
    return _TIPS[key][lang if lang in _LANGS else "it"].format(**fmt)


def opening_track_label(lang: str = "it") -> str:
    """Etichetta per la prima traccia di un set (nessuna transizione precedente)."""
    return _tip("opening_track", lang)


def mixing_tip(from_track: Track, to_track: Track, lang: str = "it") -> str:
    """Istruzione concisa e DETERMINISTICA su come mixare due brani consecutivi.

    Tutto dai dati di enrichment (BPM, Camelot, energia): niente AI, niente id.
    Pensata per il DJ: cosa fare in pratica per passare dal brano precedente a questo.
    `lang` ("it" | "en") sceglie la lingua del testo.
    """
    parts: list[str] = []

    fb, tb = from_track.bpm, to_track.bpm
    if fb and tb:
        eff, folded = effective_bpm_diff(fb, tb)
        if folded and eff <= 5:
            parts.append(_tip("halftime", lang))
        else:
            delta = tb - fb
            ad = abs(delta)
            if ad <= 0.5:
                parts.append(_tip("same_bpm", lang))
            elif ad <= 2:
                parts.append(_tip("bpm_nudge", lang, delta=delta))
            elif ad <= 5:
                parts.append(_tip("bpm_gradual", lang, delta=delta))
            elif ad <= 8:
                parts.append(_tip("bpm_sharp", lang, delta=delta))
            else:
                parts.append(_tip("bpm_hardcut", lang, delta=delta))
    else:
        parts.append(_tip("bpm_missing", lang))

    level, _ = camelot_compatibility(from_track.camelot_key, to_track.camelot_key)
    fk, tk = from_track.camelot_key, to_track.camelot_key
    if level == "same":
        parts.append(_tip("key_same", lang, fk=fk))
    elif level == "compatible":
        parts.append(_tip("key_compatible", lang, fk=fk, tk=tk))
    elif level == "weak":
        parts.append(_tip("key_weak", lang, fk=fk, tk=tk))
    # level == "unknown": tonalità mancante, nessun consiglio armonico

    fe, te = from_track.energy, to_track.energy
    if fe is not None and te is not None:
        ed = te - fe
        if ed >= 12:
            parts.append(_tip("energy_up", lang))
        elif ed <= -12:
            parts.append(_tip("energy_down", lang))

    return " · ".join(parts)


def mixing_overview(tracks: list[Track], lang: str = "it") -> list[str]:
    """Piano di mixaggio del set, DETERMINISTICO: una sintesi tecnica di come legare
    i brani (armonia, salti di BPM, arco di energia). Complementa i `mixing_tip` per
    traccia con la visione d'insieme. I numeri di brano sono le posizioni 1-based.
    `lang` ("it" | "en") sceglie la lingua del testo.
    """
    pairs = list(zip(tracks, tracks[1:]))
    if not pairs:
        return []
    bullets: list[str] = []

    def at_tracks(positions: list[int]) -> str:
        nums = ", ".join(str(p) for p in positions)
        key = "at_track_one" if len(positions) == 1 else "at_track_many"
        return _tip(key, lang, nums=nums)

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
        s = _tip("overview_harmony", lang, harmonic=harmonic, known=known)
        if weak:
            s += _tip("overview_harmony_weak", lang, weak=weak)
        bullets.append(s)

    # BPM: arco e salti che richiedono un cut/ponte
    bpms = [t.bpm for t in tracks if t.bpm]
    jumps = [i + 2 for i, (a, b) in enumerate(pairs) if a.bpm and b.bpm and abs(b.bpm - a.bpm) > 8]
    if bpms:
        arc = _tip("overview_bpm_arc", lang, lo=min(bpms), hi=max(bpms))
        if jumps:
            noun = _tip("overview_bpm_jump_one", lang) if len(jumps) == 1 else _tip("overview_bpm_jump_many", lang)
            bullets.append(_tip("overview_bpm_jump_line", lang, arc=arc, noun=noun, at=at_tracks(jumps)))
        else:
            bullets.append(_tip("overview_bpm_smooth_line", lang, arc=arc))

    # Energia: andamento e reset
    energies = [t.energy for t in tracks if t.energy is not None]
    resets = [i + 2 for i, (a, b) in enumerate(pairs)
              if a.energy is not None and b.energy is not None and b.energy - a.energy <= -15]
    if len(energies) >= 2:
        delta = energies[-1] - energies[0]
        if delta >= 8:
            trend = _tip("overview_energy_trend_up", lang)
        elif delta <= -8:
            trend = _tip("overview_energy_trend_down", lang)
        else:
            trend = _tip("overview_energy_trend_stable", lang)
        s = _tip("overview_energy_line", lang, trend=trend, e0=energies[0], e1=energies[-1])
        if resets:
            noun = _tip("overview_reset_one", lang) if len(resets) == 1 else _tip("overview_reset_many", lang)
            s += _tip("overview_reset_line", lang, noun=noun, at=at_tracks(resets))
        bullets.append(s)

    return bullets


def effective_bpm_diff(a: float, b: float) -> tuple[float, bool]:
    """Differenza BPM efficace tenendo conto di mezzo/doppio tempo (griglia condivisa).

    Ritorna (diff, folded): folded=True quando il match half/double è migliore di
    quello diretto (es. 87<->174, 140<->70), cioè un mix a mezzo tempo intenzionale.
    """
    direct = abs(a - b)
    folded = min(abs(a - 2 * b), abs(2 * a - b))
    return (folded, True) if folded < direct else (direct, False)


def _bpm_points(from_bpm: float | None, to_bpm: float | None) -> tuple[float, str, str | None]:
    if not from_bpm or not to_bpm:
        return 25.0, "BPM mancante su una delle tracce: valutazione neutra", "BPM mancante"
    diff, folded = effective_bpm_diff(from_bpm, to_bpm)
    if folded and diff <= 5:
        pts = 40.0 if diff <= 2 else 30.0
        return pts, f"mezzo/doppio tempo (Δ effettivo {diff:.1f})", "mezzo/doppio tempo: allinea la griglia sul break"
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
    pts = camelot_score(from_key, to_key) / 100.0 * 40.0  # graduato: distingue +2 boost da tritono
    if level == "unknown":
        return pts, desc, "tonalita' non confrontabile"
    if level == "weak":
        return pts, desc, "key poco compatibili: mix armonico difficile"
    return pts, desc, None


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
    """Compatibilita' di tempo (0-100), consapevole di mezzo/doppio tempo."""
    if not from_bpm or not to_bpm:
        return 50
    diff, folded = effective_bpm_diff(from_bpm, to_bpm)
    if folded and diff <= 5:
        return 100 if diff <= 2 else 75
    diff = abs(from_bpm - to_bpm)
    if diff <= 2:
        return 100
    if diff <= 5:
        return 75
    if diff <= 8:
        return 40
    return max(10, 40 - round((diff - 8) * 4))


def key_compatibility_score(from_key: str | None, to_key: str | None) -> int:
    """Compatibilita' armonica Camelot (0-100), graduata sulla distanza della ruota."""
    return camelot_score(from_key, to_key)


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


# Famiglie di genere: stesso "mondo sonoro" anche senza token in comune
# (Ambient/Downtempo, Techno/Acid). Un genere puo' appartenere a piu' famiglie
# ("Acid House" -> techno+house). Match per parola intera sul genere normalizzato,
# cosi' "electro" non cattura "electronic". Mappa deterministica, niente AI.
_GENRE_FAMILIES: dict[str, tuple[str, ...]] = {
    "techno": ("techno", "acid", "industrial", "ebm", "schranz"),
    "house": ("house", "garage", "ukg", "disco", "funky"),
    "breaks": ("breakbeat", "breaks", "electro", "idm", "braindance", "juke", "footwork"),
    "dnb": ("drum & bass", "drum and bass", "dnb", "jungle", "liquid"),
    "chill": ("ambient", "downtempo", "chillout", "chill", "drone", "trip hop", "abstract"),
    "trance": ("trance", "psytrance", "goa"),
    "bass": ("dubstep", "grime", "bass music", "bassline", "deconstructed club"),
    "hiphop": ("hip hop", "rap", "r&b", "soul", "funk"),
    "pop_rock": ("pop", "rock", "indie", "punk", "metal"),
}
# Super-generi: dicono poco, ma non sono uno stacco. Match esatto, valore neutro.
_UMBRELLA_GENRES = frozenset({"electronic", "electronica", "edm", "dance", "club",
                              "experimental", "alternative", "music"})
_GENRE_SPACES = re.compile(r"\s+")

# Valori di similarita' (0-100), allineati alle soglie d'uso:
# cross-family < RESET_GENRE_SIMILARITY (45) -> vale come reset di genere;
# umbrella > 45 -> mai un falso reset; same-family > 60 -> mai "novelty".
_GENRE_SAME_FAMILY = 80
_GENRE_SUBGENRE_BONUS = 10   # famiglia condivisa + token condiviso (sottogenere)
_GENRE_CROSS_FAMILY = 25
_GENRE_UMBRELLA = 55


def _norm_genre(raw: str) -> str:
    return _GENRE_SPACES.sub(" ", raw.lower().replace("-", " ").replace("_", " ")).strip()


def _genre_families(norm: str) -> frozenset[str]:
    padded = f" {norm} "
    return frozenset(fam for fam, keywords in _GENRE_FAMILIES.items()
                     if any(f" {kw} " in padded for kw in keywords))


def genre_similarity_score(from_genre: str | None, to_genre: str | None) -> int:
    """Similarita' di genere (0-100): famiglie note prima, token overlap come fallback."""
    if not from_genre or not to_genre:
        return 50
    a, b = _norm_genre(from_genre), _norm_genre(to_genre)
    if not a or not b:
        return 50
    if a == b:
        return 100
    fam_a, fam_b = _genre_families(a), _genre_families(b)
    if fam_a and fam_b:
        if fam_a & fam_b:
            shared_token = bool(set(a.split()) & set(b.split()))
            return _GENRE_SAME_FAMILY + (_GENRE_SUBGENRE_BONUS if shared_token else 0)
        return _GENRE_CROSS_FAMILY
    if a in _UMBRELLA_GENRES or b in _UMBRELLA_GENRES:
        return _GENRE_UMBRELLA
    # Generi fuori mappa: sovrapposizione grezza dei token, come prima.
    tokens_a, tokens_b = set(a.split()), set(b.split())
    overlap = len(tokens_a & tokens_b) / len(tokens_a | tokens_b)
    return round(40 + overlap * 60)
