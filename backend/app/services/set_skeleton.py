"""Fase 1 del set generator: il layer di pianificazione.

Qui vivono il carattere delle strategie (StrategyProfile) e la matematica degli
archi BPM/energia; sopra ci si costruisce lo scheletro del set (anchor, riserva
delle bombe, piano di genere). Il beam search di set_generator (fase 2) riempie
i segmenti. Direzione delle dipendenze: set_generator importa da qui, mai il
contrario.
"""

from dataclasses import dataclass

from app.models import Track
from app.schemas import SetGenerationRequest


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


def _desired_bpm(start: float, end: float, progress: float, curve: float) -> float:
    return start + (end - start) * (progress ** curve)


def _trajectory_fit(bpm: float | None, desired: float) -> float:
    if not bpm:
        return 40.0
    return max(0.0, 100.0 - abs(bpm - desired) * 8.0)


def _desired_energy(req: SetGenerationRequest, progress: float,
                    profile: StrategyProfile | None = None) -> float | None:
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


# Impatto (0-1): quanto una traccia "spinge" rispetto al pool. Percentili
# rank-based, tie-break per id (determinismo). Pesi tunabili.
_IMPACT_ENERGY_SHARE = 0.7
_IMPACT_BPM_SHARE = 0.3


def _percentiles(values: dict[int, float]) -> dict[int, float]:
    """id -> percentile 0-1 sul pool (rank-based, tie-break deterministico per id)."""
    if not values:
        return {}
    if len(values) == 1:
        return {tid: 0.5 for tid in values}
    ordered = sorted(values.items(), key=lambda kv: (kv[1], kv[0]))
    top = len(ordered) - 1
    return {tid: idx / top for idx, (tid, _) in enumerate(ordered)}


def impact_scores(candidates: list[Track]) -> dict[int, float]:
    """Impatto 0-1 per candidata: energia (peso 0.7) + BPM (0.3), percentili sul pool.

    Se l'energia manca sulla traccia conta solo il percentile BPM: nessuna
    penalita' per le librerie non analizzate.
    """
    bpm_pct = _percentiles({t.id: float(t.bpm) for t in candidates if t.bpm})
    energy_pct = _percentiles(
        {t.id: float(t.energy) for t in candidates if t.energy is not None})
    out: dict[int, float] = {}
    for t in candidates:
        b = bpm_pct.get(t.id, 0.5)
        e = energy_pct.get(t.id)
        out[t.id] = _IMPACT_ENERGY_SHARE * e + _IMPACT_BPM_SHARE * b if e is not None else b
    return out
