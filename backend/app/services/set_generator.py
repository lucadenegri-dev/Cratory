"""Set generator algoritmico (MVP 1): greedy sulla traiettoria BPM + scoring transizioni.

In MVP 3 questo modulo restera' il fallback deterministico; l'AI Set Agent
ricevera' le candidate da candidate_engine e gli score da scoring.
"""

import logging
import statistics

from sqlalchemy.orm import Session

from app.models import Setlist, SetlistTrack, Track
from app.schemas import SetGenerationRequest
from app.services.camelot import parse_camelot
from app.services.candidate_engine import select_candidates
from app.services.scoring import (
    TransitionScore,
    energy_progression_score,
    genre_similarity_score,
    mood_coherence_score,
    score_transition,
)

logger = logging.getLogger(__name__)

# Esponente della curva BPM start->end per strategia (1 = lineare,
# >1 = ramp lenta poi veloce, <1 = ramp veloce poi plateau).
_STRATEGY_CURVE = {
    "smooth": 1.0,
    "progressive": 1.0,
    "contrast": 1.0,
    "experimental": 1.0,
    "peak_time": 0.6,
    "warm_up": 1.6,
    "closing": 1.0,
}

# Peso dello score di transizione vs aderenza alla traiettoria BPM.
_TRANSITION_WEIGHT = 0.55
_TRAJECTORY_WEIGHT = 0.35
_FEATURE_WEIGHT = 0.20  # energia/mood/genere quando le feature sono disponibili
_KEY_PREF_BONUS = 8.0
_SEED_BONUS = 15.0


class SetGenerationError(Exception):
    pass


def _risk_level(score: int) -> str:
    if score >= 70:
        return "low"
    if score >= 45:
        return "medium"
    return "high"


def assign_roles(n: int) -> list[str]:
    """Assegna un ruolo a ciascuna posizione lungo l'arco del set (deterministico).

    Ruoli (vedi nuovo_progetto.md sez. 4): intro, warmup, groove, transition,
    peak, release, closing. Il peak e' collocato intorno al 70% del set.
    """
    if n <= 0:
        return []
    if n == 1:
        return ["intro"]
    roles: list[str] = []
    peak_at = max(1, round((n - 1) * 0.7))
    for i in range(n):
        frac = i / (n - 1)
        if i == 0:
            roles.append("intro")
        elif i == n - 1:
            roles.append("closing")
        elif i == peak_at:
            roles.append("peak")
        elif i > peak_at:
            roles.append("release")
        elif frac < 0.25:
            roles.append("warmup")
        elif frac < 0.55:
            roles.append("groove")
        else:
            roles.append("transition")
    return roles


def _desired_bpm(start: float, end: float, progress: float, strategy: str) -> float:
    exp = _STRATEGY_CURVE.get(strategy, 1.0)
    return start + (end - start) * (progress ** exp)


def _trajectory_fit(bpm: float | None, desired: float) -> float:
    if not bpm:
        return 40.0
    return max(0.0, 100.0 - abs(bpm - desired) * 8.0)


def _desired_energy(req: SetGenerationRequest, progress: float) -> float | None:
    """Energia target lungo il set (0-100), interpolata start->end. None se non richiesta."""
    if req.start_energy is None and req.end_energy is None:
        return None
    start = req.start_energy if req.start_energy is not None else req.end_energy
    end = req.end_energy if req.end_energy is not None else req.start_energy
    return start + (end - start) * progress


def _feature_fit(prev: Track, cand: Track, req: SetGenerationRequest,
                 desired_energy: float | None) -> float | None:
    """Blend 0-100 di energia/mood/genere, solo sui segnali effettivamente presenti.

    Ritorna None se la traccia non ha alcuna feature (dataset non arricchito):
    in quel caso il termine feature non incide sul ranking.
    """
    feats: list[float] = []
    if prev.energy is not None and cand.energy is not None:
        feats.append(float(energy_progression_score(prev.energy, cand.energy)))
    if desired_energy is not None and cand.energy is not None:
        feats.append(max(0.0, 100.0 - abs(cand.energy - desired_energy)))
    ref_mood = req.start_mood or prev.mood
    if cand.mood and ref_mood:
        feats.append(float(mood_coherence_score(ref_mood, cand.mood)))
    if prev.genre and cand.genre:
        feats.append(float(genre_similarity_score(prev.genre, cand.genre)))
    return sum(feats) / len(feats) if feats else None


def _pick_first(candidates: list[Track], req: SetGenerationRequest, start_bpm: float) -> Track:
    seeds = [s.lower() for s in req.seed_artists]

    def first_score(t: Track) -> float:
        s = -abs((t.bpm or start_bpm) - start_bpm)
        if seeds and t.artist and any(seed in t.artist.lower() for seed in seeds):
            s += 100.0
        return s

    return max(candidates, key=first_score)


def _candidate_score(
    prev: Track, cand: Track, desired_bpm: float, req: SetGenerationRequest,
    artist_counts: dict[str, int], desired_energy: float | None = None,
) -> tuple[float, TransitionScore]:
    ts = score_transition(prev, cand)
    transition_pts = float(ts.score)
    if not req.allow_sharp_changes and ts.score < 30:
        transition_pts -= 40.0  # scoraggia fortemente i salti se non richiesti

    total = transition_pts * _TRANSITION_WEIGHT
    if req.prefer_progressive_bpm:
        total += _trajectory_fit(cand.bpm, desired_bpm) * _TRAJECTORY_WEIGHT
    feature_fit = _feature_fit(prev, cand, req, desired_energy)
    if feature_fit is not None:
        total += feature_fit * _FEATURE_WEIGHT
    if req.prefer_harmonic and req.preferred_keys and cand.camelot_key in req.preferred_keys:
        total += _KEY_PREF_BONUS
    seeds = [s.lower() for s in req.seed_artists]
    if seeds and cand.artist and any(seed in cand.artist.lower() for seed in seeds):
        total += _SEED_BONUS
    artist_key = (cand.artist or "").lower()
    if artist_key and artist_counts.get(artist_key, 0) > 0:
        total -= 6.0 * artist_counts[artist_key]  # leggera spinta alla varieta'
    return total, ts


def _explanation(setlist_tracks: list[tuple[Track, TransitionScore | None]],
                 req: SetGenerationRequest, total_seconds: int) -> str:
    tracks = [t for t, _ in setlist_tracks]
    scores = [ts for _, ts in setlist_tracks if ts]
    bpms = [t.bpm for t in tracks if t.bpm]
    keys = {t.camelot_key for t in tracks if t.camelot_key}
    safe = sum(1 for ts in scores if ts.score >= 70)
    risky = sum(1 for ts in scores if ts.score < 45)
    parts = [
        f"Set '{req.strategy}' di {len(tracks)} tracce, durata {total_seconds // 60} minuti "
        f"(target {req.target_duration_minutes}).",
    ]
    if bpms:
        parts.append(f"Arco BPM da {bpms[0]:.0f} a {bpms[-1]:.0f} "
                     f"(min {min(bpms):.0f}, max {max(bpms):.0f}).")
    if scores:
        parts.append(f"{safe}/{len(scores)} transizioni tecnicamente sicure"
                     + (f", {risky} rischiose da preparare con cura." if risky else "."))
    if keys:
        parts.append(f"Tonalita' toccate: {', '.join(sorted(keys))}.")
    parts.append("Generato dal motore deterministico (MVP 1): le motivazioni sono tecniche, "
                 "le spiegazioni narrative arriveranno con l'AI Set Agent (MVP 3).")
    return " ".join(parts)


def generate_set(db: Session, req: SetGenerationRequest) -> Setlist:
    candidates = select_candidates(db, req)
    if len(candidates) < 3:
        raise SetGenerationError(
            "Tracce candidate insufficienti: allargare i vincoli (BPM, sorgenti, durata) "
            "o importare piu' tracce."
        )

    bpm_values = [t.bpm for t in candidates if t.bpm]
    start_bpm = req.start_bpm or statistics.median(bpm_values)
    end_bpm = req.end_bpm or start_bpm

    target_seconds = req.target_duration_minutes * 60
    first = _pick_first(candidates, req, start_bpm)

    chosen: list[tuple[Track, TransitionScore | None]] = [(first, None)]
    remaining = [t for t in candidates if t.id != first.id]
    artist_counts: dict[str, int] = {}
    if first.artist:
        artist_counts[first.artist.lower()] = 1
    total_seconds = first.duration_seconds or 0

    while total_seconds < target_seconds and remaining:
        prev = chosen[-1][0]
        progress = min(1.0, total_seconds / target_seconds)
        desired = _desired_bpm(start_bpm, end_bpm, progress, req.strategy)
        desired_energy = _desired_energy(req, progress)

        eligible = [
            t for t in remaining
            if artist_counts.get((t.artist or "").lower(), 0) < req.max_tracks_per_artist
            or not t.artist
        ]
        if not eligible:
            break

        scored = [(_candidate_score(prev, t, desired, req, artist_counts, desired_energy), t) for t in eligible]
        ((_, ts), best) = max(scored, key=lambda item: item[0][0])

        chosen.append((best, ts))
        remaining = [t for t in remaining if t.id != best.id]
        if best.artist:
            artist_counts[best.artist.lower()] = artist_counts.get(best.artist.lower(), 0) + 1
        total_seconds += best.duration_seconds or 0

    setlist = Setlist(
        name=req.name or f"Set {req.strategy} {req.target_duration_minutes}min",
        target_duration_minutes=req.target_duration_minutes,
        start_bpm=start_bpm,
        end_bpm=end_bpm,
        strategy=req.strategy,
        prompt=req.prompt,
        global_explanation=_explanation(chosen, req, total_seconds),
    )
    roles = assign_roles(len(chosen))
    for position, (track, ts) in enumerate(chosen, start=1):
        setlist.tracks.append(SetlistTrack(
            track_id=track.id,
            position=position,
            role=roles[position - 1],
            transition_score=float(ts.score) if ts else None,
            transition_reason="; ".join(ts.technical_reasons) if ts else "traccia di apertura",
            risk_level=_risk_level(ts.score) if ts else "low",
        ))
    db.add(setlist)
    db.commit()
    db.refresh(setlist)
    logger.info("Set generato: %s tracce, %ss (target %ss)", len(chosen), total_seconds, target_seconds)
    return setlist


def preferred_keys_sanity(keys: list[str]) -> list[str]:
    """Mantiene solo key Camelot valide (input utente)."""
    return [k for k in keys if parse_camelot(k)]
