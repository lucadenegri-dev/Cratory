"""Validation Engine (MVP 3, F8).

Prende l'output dell'AI Set Agent (ordine di track_id + narrativa) e lo valida
deterministicamente: esistenza tracce, deduplica, max per artista, filtro
sorgente, durata vicina al target, salti BPM e incompatibilita' Camelot.
Auto-corregge dove possibile (scartando tracce non valide) e raccoglie warning.
"""

from dataclasses import dataclass, field

from app.models import Track
from app.schemas import AISetResponse, SetGenerationRequest
from app.services.scoring import score_transition


@dataclass
class ValidatedTrack:
    track: Track
    ai_reason: str
    risk_level: str
    transition_score: float | None
    transition_reason: str


@dataclass
class ValidationResult:
    tracks: list[ValidatedTrack] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    auto_fixes: list[str] = field(default_factory=list)
    stats: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {"warnings": self.warnings, "auto_fixes": self.auto_fixes, "stats": self.stats}


BPM_JUMP_WARN = 8.0
SHORT_TRACK_SECONDS = 90
DURATION_TOLERANCE = 0.25  # +/- 25% del target


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

    for choice in ordered:
        track = candidates_by_id.get(choice.track_id)
        if track is None:
            result.warnings.append(f"track_id {choice.track_id} inesistente tra le candidate: scartata")
            continue
        if track.id in seen:
            result.auto_fixes.append(f"duplicato rimosso: {track.artist or '?'} - {track.title or track.id}")
            continue
        if req.sources and track.source_type not in req.sources:
            result.warnings.append(f"sorgente non ammessa ({track.source_type}) scartata: {track.title or track.id}")
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
        transition_score: float | None = None
        transition_reason = "traccia di apertura"
        if result.tracks:
            prev = result.tracks[-1].track
            ts = score_transition(prev, track, penalize_overplayed=req.avoid_overplayed)
            transition_score = float(ts.score)
            transition_reason = "; ".join(ts.technical_reasons)
            for w in ts.warnings:
                result.warnings.append(f"{prev.title or prev.id} -> {track.title or track.id}: {w}")

        if (track.duration_seconds or 0) and track.duration_seconds < SHORT_TRACK_SECONDS:
            result.warnings.append(f"traccia molto corta ({track.duration_seconds}s): {track.title or track.id}")

        risk = choice.risk_level if choice.risk_level in risk_by_level else "medium"
        result.tracks.append(ValidatedTrack(
            track=track,
            ai_reason=choice.reason,
            risk_level=risk,
            transition_score=transition_score,
            transition_reason=transition_reason,
        ))

    # durata totale vs target
    total = sum(vt.track.duration_seconds or 0 for vt in result.tracks)
    target = req.target_duration_minutes * 60
    if target and abs(total - target) > target * DURATION_TOLERANCE:
        result.warnings.append(
            f"durata {total // 60} min lontana dal target {req.target_duration_minutes} min"
        )

    result.stats = {
        "track_count": len(result.tracks),
        "total_duration_seconds": total,
        "target_duration_seconds": target,
        "safe_transitions": sum(1 for vt in result.tracks if (vt.transition_score or 0) >= 70),
    }
    return result
