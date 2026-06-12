"""Scoring tecnico deterministico delle transizioni tra due tracce.

Composizione score (0-100):
- BPM:        max 40  (0-2 ottimo, 2-5 buono, 5-8 rischioso, >8 difficile)
- Camelot:    max 35  (stessa key / compatibile / debole)
- Durata+cue: max 15  (penalita' tracce corte, bonus cue e beatgrid)
- Play count: max 10  (bonus varieta', penalita' overplayed opzionale)
"""

from dataclasses import dataclass, field

from app.models import Track
from app.services.camelot import camelot_compatibility

SHORT_TRACK_SECONDS = 90
OVERPLAYED_THRESHOLD = 15


@dataclass
class TransitionScore:
    score: int
    technical_reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _bpm_points(from_bpm: float | None, to_bpm: float | None) -> tuple[float, str, str | None]:
    if not from_bpm or not to_bpm:
        return 15.0, "BPM mancante su una delle tracce: valutazione neutra", "BPM mancante"
    diff = abs(from_bpm - to_bpm)
    if diff <= 2:
        return 40.0, f"differenza BPM ottima ({diff:.1f})", None
    if diff <= 5:
        return 30.0, f"differenza BPM buona ({diff:.1f})", None
    if diff <= 8:
        return 16.0, f"differenza BPM rischiosa ({diff:.1f})", f"salto BPM di {diff:.1f}: transizione rischiosa"
    return 4.0, f"differenza BPM difficile ({diff:.1f})", f"salto BPM di {diff:.1f}: transizione difficile"


def _key_points(from_key: str | None, to_key: str | None) -> tuple[float, str, str | None]:
    level, desc = camelot_compatibility(from_key, to_key)
    if level == "same":
        return 35.0, desc, None
    if level == "compatible":
        return 28.0, desc, None
    if level == "unknown":
        return 15.0, desc, "tonalita' non confrontabile"
    return 8.0, desc, "key poco compatibili: mix armonico difficile"


def score_transition(
    from_track: Track,
    to_track: Track,
    *,
    penalize_overplayed: bool = False,
) -> TransitionScore:
    reasons: list[str] = []
    warnings: list[str] = []
    total = 0.0

    pts, reason, warn = _bpm_points(from_track.bpm, to_track.bpm)
    total += pts
    reasons.append(reason)
    if warn:
        warnings.append(warn)

    pts, reason, warn = _key_points(from_track.tonality, to_track.tonality)
    total += pts
    reasons.append(reason)
    if warn:
        warnings.append(warn)

    # Durata, cue, beatgrid (max 15)
    structure = 5.0
    duration = to_track.duration_seconds or 0
    if duration and duration < SHORT_TRACK_SECONDS:
        structure -= 5.0
        warnings.append(f"traccia in entrata molto corta ({duration}s)")
    if to_track.cue_points:
        structure += 5.0
        reasons.append(f"cue point presenti sulla traccia in entrata ({len(to_track.cue_points)})")
    if to_track.beatgrid_points:
        structure += 5.0
        reasons.append("beatgrid disponibile sulla traccia in entrata")
    total += max(structure, 0.0)

    # Play count (max 10)
    pc = to_track.play_count or 0
    if pc == 0:
        total += 8.0
        reasons.append("traccia mai suonata: bonus varieta'")
    elif penalize_overplayed and pc > OVERPLAYED_THRESHOLD:
        total += 2.0
        warnings.append(f"traccia suonata spesso ({pc} volte)")
    else:
        total += 5.0

    return TransitionScore(
        score=max(0, min(100, round(total))),
        technical_reasons=reasons,
        warnings=warnings,
    )
