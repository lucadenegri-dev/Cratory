"""Validation Engine (MVP 3, F8).

Prende l'output dell'AI Set Agent (ordine di track_id + narrativa) e lo valida
deterministicamente: esistenza tracce, deduplica, max per artista, filtro
sorgente, durata vicina al target, salti BPM e incompatibilita' Camelot.
Auto-corregge dove possibile (scartando tracce non valide) e raccoglie warning.
"""

from dataclasses import dataclass, field

from app.models import Track
from app.schemas import AISetResponse, SetGenerationRequest
from app.services.camelot import camelot_compatibility
from app.services.scoring import effective_bpm_diff, score_transition


@dataclass
class ValidatedTrack:
    track: Track
    ai_reason: str
    risk_level: str
    transition_score: float | None
    transition_reason: str
    transition_note: str = ""  # nota di transizione narrativa dell'AI


@dataclass
class ValidationResult:
    tracks: list[ValidatedTrack] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    auto_fixes: list[str] = field(default_factory=list)
    stats: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {"warnings": self.warnings, "auto_fixes": self.auto_fixes, "stats": self.stats}


SHORT_TRACK_SECONDS = 90
DURATION_TOLERANCE = 0.25  # +/- 25% del target


def _label(track: Track) -> str:
    """Etichetta leggibile di una traccia per i messaggi: mai l'id numerico."""
    artist = (track.artist or "").strip()
    title = (track.title or "").strip()
    if artist and title:
        return f"{artist} – {title}"
    return title or artist or "traccia senza titolo"


def _positions(positions: list[int]) -> str:
    nums = ", ".join(str(p) for p in positions)
    return f"al brano {nums}" if len(positions) == 1 else f"ai brani {nums}"


def validate_ai_set(
    ai: AISetResponse,
    candidates_by_id: dict[int, Track],
    req: SetGenerationRequest,
) -> ValidationResult:
    result = ValidationResult()

    ordered = sorted(ai.tracks, key=lambda t: t.position)
    seen: set[int] = set()
    artist_counts: dict[str, int] = {}
    risk_by_level = {"low", "medium", "high"}
    # Posizioni (1-based) dei problemi, per aggregarli in pochi warning leggibili.
    weak_key_at: list[int] = []
    bpm_jump_at: list[int] = []
    short_at: list[int] = []

    for choice in ordered:
        track = candidates_by_id.get(choice.track_id)
        if track is None:
            result.warnings.append("una traccia suggerita dall'AI non è tra le candidate: scartata")
            continue
        if track.id in seen:
            result.auto_fixes.append(f"duplicato rimosso: {_label(track)}")
            continue
        if req.sources and track.source_type not in req.sources:
            result.warnings.append(f"sorgente non ammessa ({track.source_type}) scartata: {_label(track)}")
            continue
        artist_key = (track.artist or "").lower()
        if artist_key and artist_counts.get(artist_key, 0) >= req.max_tracks_per_artist:
            result.auto_fixes.append(
                f"superato max {req.max_tracks_per_artist} per artista ({track.artist}): traccia in piu' rimossa"
            )
            continue

        seen.add(track.id)
        if artist_key:
            artist_counts[artist_key] = artist_counts.get(artist_key, 0) + 1

        # score tecnico deterministico della transizione dal brano precedente
        position = len(result.tracks) + 1  # posizione finale di questo brano nel set
        transition_score: float | None = None
        transition_reason = "traccia di apertura"
        if result.tracks:
            prev = result.tracks[-1].track
            ts = score_transition(prev, track)
            transition_score = float(ts.score)
            transition_reason = "; ".join(ts.technical_reasons)
            if camelot_compatibility(prev.camelot_key, track.camelot_key)[0] == "weak":
                weak_key_at.append(position)
            if prev.bpm and track.bpm and effective_bpm_diff(prev.bpm, track.bpm)[0] > 8:
                bpm_jump_at.append(position)

        if (track.duration_seconds or 0) and track.duration_seconds < SHORT_TRACK_SECONDS:
            short_at.append(position)

        risk = choice.risk_level if choice.risk_level in risk_by_level else "medium"
        result.tracks.append(ValidatedTrack(
            track=track,
            ai_reason=choice.reason,
            risk_level=risk,
            transition_score=transition_score,
            transition_reason=transition_reason,
            transition_note=choice.transition_note,
        ))

    # --- Warning aggregati, in ordine di importanza (durata prima) ---
    # Gli avvisi di scarto raccolti nel loop (traccia non candidata/sorgente) restano
    # in coda; qui davanti mettiamo i pochi warning azionabili e sintetici.
    total = sum(vt.track.duration_seconds or 0 for vt in result.tracks)
    target = req.target_duration_minutes * 60
    aggregated: list[str] = []
    if target and abs(total - target) > target * DURATION_TOLERANCE:
        verso = "aggiungi tracce" if total < target else "accorcia il set"
        aggregated.append(
            f"Durata {total // 60} min lontana dal target {req.target_duration_minutes} min: {verso}."
        )
    if weak_key_at:
        noun = "transizione fuori chiave" if len(weak_key_at) == 1 else "transizioni fuori chiave"
        aggregated.append(f"{len(weak_key_at)} {noun} ({_positions(weak_key_at)}): tienile brevi o maschera con l'EQ.")
    if bpm_jump_at:
        noun = "salto di BPM marcato" if len(bpm_jump_at) == 1 else "salti di BPM marcati"
        aggregated.append(f"{len(bpm_jump_at)} {noun} ({_positions(bpm_jump_at)}): usa un break o una traccia ponte.")
    if short_at:
        noun = "traccia molto corta" if len(short_at) == 1 else "tracce molto corte"
        aggregated.append(f"{len(short_at)} {noun} ({_positions(short_at)}).")
    result.warnings = aggregated + result.warnings

    result.stats = {
        "track_count": len(result.tracks),
        "total_duration_seconds": total,
        "target_duration_seconds": target,
        "safe_transitions": sum(1 for vt in result.tracks if (vt.transition_score or 0) >= 70),
    }
    return result
