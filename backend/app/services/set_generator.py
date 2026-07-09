"""Set generator algoritmico deterministico: beam search sulla traiettoria BPM +
scoring transizioni, con profili per dare un carattere distinto a ciascuna strategia.

Il beam costruisce piu' set in parallelo e tiene il migliore (con rete di sicurezza
sul percorso greedy, così non fa mai peggio). Resta il fallback deterministico
accanto all'AI Set Agent, che riceve le candidate da candidate_engine e gli score
da scoring.
"""

import logging
import statistics
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models import Setlist, SetlistTrack, Track
from app.schemas import SetGenerationRequest
from app.services.camelot import camelot_compatibility
from app.services.candidate_engine import select_candidates
from app.services.scoring import (
    RESET_ENERGY_DROP,
    RESET_GENRE_SIMILARITY,
    TransitionScore,
    energy_progression_score,
    genre_similarity_score,
    score_transition,
)

logger = logging.getLogger(__name__)

# Peso dello score di transizione vs aderenza alla traiettoria BPM.
_TRANSITION_WEIGHT = 0.55
_TRAJECTORY_WEIGHT = 0.35
_FEATURE_WEIGHT = 0.20  # smoothness dell'energia quando disponibile
_ENERGY_ARC_WEIGHT = 0.30  # aderenza al target di energia della posizione (arco strategia/utente)
_GENRE_WEIGHT = 0.25   # coerenza di genere: termine dedicato (come l'arco di energia),
#                        cosi' il set resta nello stesso mondo sonoro invece di zigzagare
_KEY_PREF_BONUS = 8.0
_SEED_BONUS = 15.0
_SHARP_PENALTY = 40.0  # scoraggia i salti bruschi quando la strategia non li vuole
RESET_WINDOW = 0.1     # ampiezza (frazione di set) attorno a un reset point


@dataclass(frozen=True)
class StrategyProfile:
    """Parametri che danno un carattere distinto a ciascuna strategia.

    - bpm_curve: esponente della traiettoria BPM (1=lineare, >1 sale piano, <1 sale in fretta).
    - allow_sharp: ammette transizioni brusche senza la penalità -40.
    - reset_points: frazioni del set (0-1) dove uno stacco "reset" è premiato invece che penalizzato.
    - reset_bonus: entità del premio a una transizione di reset vicino a un reset point.
    - novelty_bonus: premio al cambio di tonalità/genere (esplorazione voluta).
    - energy_arc: (energia_iniziale, energia_finale) 0-100 imposta dalla strategia quando
      l'utente non specifica un arco; None = nessun arco imposto. Ora che l'energia è reale
      (dai file audio) questo distingue davvero progressive (in salita) da smooth (piatto).
    - genre_coherence: moltiplicatore (0-1) del termine di coerenza di genere. 1 =
      il set resta nello stesso mondo sonoro; ridotto per le strategie esplorative,
      così il novelty_bonus non viene neutralizzato dalla coerenza.
    """
    bpm_curve: float
    allow_sharp: bool
    reset_points: tuple[float, ...]
    reset_bonus: float
    novelty_bonus: float
    energy_arc: tuple[float, float] | None = None
    genre_coherence: float = 1.0


_DEFAULT_PROFILE = StrategyProfile(1.0, False, (), 0.0, 0.0)
_STRATEGY_PROFILES: dict[str, StrategyProfile] = {
    "smooth":       StrategyProfile(1.0, False, (), 0.0, 0.0, energy_arc=None),
    "progressive":  StrategyProfile(1.0, False, (), 0.0, 0.0, energy_arc=(35, 85)),
    "contrast":     StrategyProfile(1.0, True, (0.34, 0.67), 22.0, 0.0, energy_arc=None),
    "experimental": StrategyProfile(1.0, True, (0.5,), 12.0, 12.0, energy_arc=None,
                                    genre_coherence=0.5),
    "peak_time":    StrategyProfile(0.6, False, (), 0.0, 0.0, energy_arc=(70, 92)),
    "warm_up":      StrategyProfile(1.6, False, (), 0.0, 0.0, energy_arc=(25, 55)),
    "closing":      StrategyProfile(1.0, False, (0.85,), 15.0, 0.0, energy_arc=(75, 40)),
}


def strategy_profile(strategy: str) -> StrategyProfile:
    return _STRATEGY_PROFILES.get(strategy, _DEFAULT_PROFILE)


def _near_reset(progress: float, points: tuple[float, ...]) -> bool:
    return any(abs(progress - p) <= RESET_WINDOW for p in points)


def _is_reset(prev: Track, cand: Track) -> bool:
    """Stacco netto voluto: forte calo di energia o cambio di genere."""
    if (prev.energy is not None and cand.energy is not None
            and cand.energy - prev.energy <= -RESET_ENERGY_DROP):
        return True
    return bool(prev.genre and cand.genre
                and genre_similarity_score(prev.genre, cand.genre) < RESET_GENRE_SIMILARITY)


def _is_novel(prev: Track, cand: Track) -> bool:
    """Esplorazione: cambio di tonalità o di genere rispetto al brano precedente."""
    if prev.camelot_key and cand.camelot_key and prev.camelot_key != cand.camelot_key:
        return True
    return bool(prev.genre and cand.genre
                and genre_similarity_score(prev.genre, cand.genre) < RESET_GENRE_SIMILARITY + 15)


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


def _desired_bpm(start: float, end: float, progress: float, curve: float) -> float:
    return start + (end - start) * (progress ** curve)


def _trajectory_fit(bpm: float | None, desired: float) -> float:
    if not bpm:
        return 40.0
    return max(0.0, 100.0 - abs(bpm - desired) * 8.0)


def _desired_energy(req: SetGenerationRequest, progress: float,
                    profile: "StrategyProfile | None" = None) -> float | None:
    """Energia target lungo il set (0-100), interpolata start->end.

    L'energia esplicita dell'utente vince; altrimenti si usa l'arco della strategia
    (energy_arc); se nessuno dei due, None (nessun vincolo di energia).
    """
    if req.start_energy is not None or req.end_energy is not None:
        start = req.start_energy if req.start_energy is not None else req.end_energy
        end = req.end_energy if req.end_energy is not None else req.start_energy
        return start + (end - start) * progress
    if profile is not None and profile.energy_arc is not None:
        start, end = profile.energy_arc
        return start + (end - start) * progress
    return None


def _feature_fit(prev: Track, cand: Track, req: SetGenerationRequest,
                 desired_energy: float | None) -> float | None:
    """Smoothness dell'energia (0-100), solo se il dato e' presente.

    Ritorna None se manca l'energia (dataset non arricchito): il termine non
    incide sul ranking. L'aderenza all'arco di energia e la coerenza di genere
    NON sono qui: sono termini dedicati in _candidate_score (con peso proprio),
    così ciascun segnale modella il set invece di diluirsi in una media.
    """
    _ = desired_energy
    if prev.energy is not None and cand.energy is not None:
        return float(energy_progression_score(prev.energy, cand.energy))
    return None


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
    artist_counts: dict[str, int], profile: StrategyProfile, progress: float,
    desired_energy: float | None = None,
) -> tuple[float, TransitionScore]:
    ts = score_transition(prev, cand)
    transition_pts = float(ts.score)
    # Salto brusco: penalizzato, a meno che la strategia (o la richiesta) lo ammetta.
    if ts.score < 30 and not (req.allow_sharp_changes or profile.allow_sharp):
        transition_pts -= _SHARP_PENALTY

    total = transition_pts * _TRANSITION_WEIGHT
    if req.prefer_progressive_bpm:
        total += _trajectory_fit(cand.bpm, desired_bpm) * _TRAJECTORY_WEIGHT
    feature_fit = _feature_fit(prev, cand, req, desired_energy)
    if feature_fit is not None:
        total += feature_fit * _FEATURE_WEIGHT
    # Coerenza di genere: sempre attiva (50 = neutro quando il dato manca), così
    # una traccia senza genere non batte né perde contro una coerente per assenza.
    total += (float(genre_similarity_score(prev.genre, cand.genre))
              * _GENRE_WEIGHT * profile.genre_coherence)
    # Aderenza all'arco di energia (termine dedicato): tira le tracce verso il target
    # di energia della posizione, così l'arco della strategia modella il set.
    if desired_energy is not None and cand.energy is not None:
        total += max(0.0, 100.0 - abs(cand.energy - desired_energy)) * _ENERGY_ARC_WEIGHT
    if req.prefer_harmonic and req.preferred_keys and cand.camelot_key in req.preferred_keys:
        total += _KEY_PREF_BONUS
    seeds = [s.lower() for s in req.seed_artists]
    if seeds and cand.artist and any(seed in cand.artist.lower() for seed in seeds):
        total += _SEED_BONUS
    artist_key = (cand.artist or "").lower()
    if artist_key and artist_counts.get(artist_key, 0) > 0:
        total -= 6.0 * artist_counts[artist_key]  # leggera spinta alla varieta'
    # Carattere della strategia: reset premiato nei punti giusti, novità per l'esplorazione.
    if profile.reset_bonus and _near_reset(progress, profile.reset_points) and _is_reset(prev, cand):
        total += profile.reset_bonus
    if profile.novelty_bonus and _is_novel(prev, cand):
        total += profile.novelty_bonus
    return total, ts


_STRATEGY_LABELS = {
    "smooth": "fluido", "progressive": "progressivo", "contrast": "a contrasti",
    "experimental": "sperimentale", "peak_time": "peak time", "warm_up": "warm-up",
    "closing": "di chiusura",
}


def _positions_phrase(positions: list[int]) -> str:
    nums = ", ".join(str(p) for p in positions)
    return f"al brano {nums}" if len(positions) == 1 else f"ai brani {nums}"


def _explanation(setlist_tracks: list[tuple[Track, TransitionScore | None]],
                 req: SetGenerationRequest, total_seconds: int) -> str:
    """Riga di sintesi PER IL DJ: carattere del set, qualità armonica e cosa preparare.
    Niente stat già visibili nella UI (conteggio, durata, min/max) né gergo di roadmap.
    """
    tracks = [t for t, _ in setlist_tracks]
    scores = [ts for _, ts in setlist_tracks if ts]
    bpms = [t.bpm for t in tracks if t.bpm]
    weak_positions = [
        i + 1 for i, (t, ts) in enumerate(setlist_tracks)
        if ts is not None
        and camelot_compatibility(tracks[i - 1].camelot_key, t.camelot_key)[0] == "weak"
    ]

    strat = _STRATEGY_LABELS.get(req.strategy, req.strategy)
    parts: list[str] = []
    if bpms:
        move = ("sale" if bpms[-1] > bpms[0] + 1
                else "scende" if bpms[-1] < bpms[0] - 1 else "resta stabile")
        parts.append(f"Set {strat}: l'arco {move} da {bpms[0]:.0f} a {bpms[-1]:.0f} BPM.")
    else:
        parts.append(f"Set {strat}.")

    if scores:
        n = len(scores)
        in_key = n - len(weak_positions)
        if not weak_positions:
            parts.append(f"Mix armonico continuo: tutte le {n} transizioni in chiave.")
        elif len(weak_positions) == 1:
            parts.append(f"{in_key}/{n} transizioni in chiave; tieni corta quella fuori "
                         f"chiave ({_positions_phrase(weak_positions)}).")
        else:
            parts.append(f"{in_key}/{n} transizioni in chiave; tieni corte le "
                         f"{len(weak_positions)} fuori chiave ({_positions_phrase(weak_positions)}).")

    target = req.target_duration_minutes
    if target:
        minutes = total_seconds // 60
        delta = minutes - target
        if abs(delta) > target * 0.15:
            verso = "sotto" if delta < 0 else "sopra"
            azione = "aggiungi qualche traccia" if delta < 0 else "accorcia o togli una traccia"
            parts.append(f"Durata {minutes} min, {abs(delta)} {verso} il target di {target}: {azione}.")
    return " ".join(parts)


# Beam search: invece di costruire UN set passo-passo (greedy, che si intrappola in
# ottimi locali), ne costruisce BEAM_WIDTH in parallelo e alla fine tiene il migliore
# per punteggio cumulativo. Costo: qualche migliaio di score, cioè millisecondi.
BEAM_WIDTH = 6
BEAM_EXPANSIONS = 8


def _beam_search(
    opener: Track, candidates: list[Track], req: SetGenerationRequest,
    profile: StrategyProfile, start_bpm: float, end_bpm: float, target_seconds: int,
) -> list[tuple[Track, TransitionScore | None]]:
    """Ritorna la sequenza [(track, transition_score|None), ...] con opener in testa."""
    def new_beam() -> dict:
        arts: dict[str, int] = {}
        if opener.artist:
            arts[opener.artist.lower()] = 1
        return {"chosen": [(opener, None)], "used": {opener.id}, "arts": arts,
                "secs": opener.duration_seconds or 0, "cum": 0.0,
                "done": (opener.duration_seconds or 0) >= target_seconds}

    def expand(b: dict) -> list[dict]:
        """Espande un beam nei suoi migliori BEAM_EXPANSIONS successori (o lo marca done)."""
        prev = b["chosen"][-1][0]
        progress = min(1.0, b["secs"] / target_seconds)
        desired = _desired_bpm(start_bpm, end_bpm, progress, profile.bpm_curve)
        desired_energy = _desired_energy(req, progress, profile)
        eligible = [
            t for t in candidates
            if t.id not in b["used"]
            and (not t.artist or b["arts"].get(t.artist.lower(), 0) < req.max_tracks_per_artist)
        ]
        if not eligible:
            b["done"] = True
            return [b]
        scored = sorted(
            ((_candidate_score(prev, t, desired, req, b["arts"], profile, progress, desired_energy), t)
             for t in eligible),
            key=lambda it: (it[0][0], it[1].id), reverse=True,
        )[:BEAM_EXPANSIONS]
        children = []
        for (sc, ts), t in scored:
            arts = dict(b["arts"])
            if t.artist:
                arts[t.artist.lower()] = arts.get(t.artist.lower(), 0) + 1
            secs = b["secs"] + (t.duration_seconds or 0)
            children.append({
                "chosen": b["chosen"] + [(t, ts)], "used": b["used"] | {t.id},
                "arts": arts, "secs": secs, "cum": b["cum"] + sc,
                "done": secs >= target_seconds,
            })
        return children

    beams = [new_beam()]
    while any(not b["done"] for b in beams):
        expanded: list[dict] = []
        for b in beams:
            expanded.extend([b] if b["done"] else expand(b))
        # Prune ai migliori BEAM_WIDTH per punteggio cumulativo (tie-break deterministico).
        expanded.sort(key=lambda b: (b["cum"], [t.id for t, _ in b["chosen"]]), reverse=True)
        beams = expanded[:BEAM_WIDTH]

    # Rete di sicurezza: il percorso puramente greedy (sempre il #1 successore) è
    # sempre in gara nella scelta finale, così il beam non può fare peggio del greedy.
    greedy = new_beam()
    while not greedy["done"]:
        greedy = expand(greedy)[0]

    # Fra i beam completi scegli il migliore per punteggio medio (evita il bias sulla lunghezza).
    complete = [b for b in beams if b["secs"] >= target_seconds] or beams
    complete.append(greedy)
    best = max(complete, key=lambda b: (b["cum"] / max(1, len(b["chosen"]) - 1),
                                        [t.id for t, _ in b["chosen"]]))
    return best["chosen"]


def generate_set(db: Session, req: SetGenerationRequest) -> Setlist:
    candidates = select_candidates(db, req)
    if len(candidates) < 3:
        if req.owned_only:
            raise SetGenerationError(
                "Tracce candidate insufficienti tra quelle possedute: indicizza la "
                "libreria (Impostazioni → Libreria) o disattiva \"solo brani posseduti\" "
                "per includere i lead."
            )
        raise SetGenerationError(
            "Tracce candidate insufficienti: allargare i vincoli (BPM, sorgenti, durata) "
            "o importare piu' tracce."
        )

    bpm_values = [t.bpm for t in candidates if t.bpm]
    start_bpm = req.start_bpm or statistics.median(bpm_values)
    end_bpm = req.end_bpm or start_bpm

    target_seconds = req.target_duration_minutes * 60
    profile = strategy_profile(req.strategy)
    first = _pick_first(candidates, req, start_bpm)
    chosen = _beam_search(first, candidates, req, profile, start_bpm, end_bpm, target_seconds)
    total_seconds = sum((t.duration_seconds or 0) for t, _ in chosen)

    setlist = Setlist(
        name=req.name or f"Set {req.strategy} {req.target_duration_minutes}min",
        target_duration_minutes=req.target_duration_minutes,
        start_bpm=start_bpm,
        end_bpm=end_bpm,
        strategy=req.strategy,
        prompt=req.prompt,
        global_explanation=_explanation(chosen, req, total_seconds),
        owned_only=req.owned_only,
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
