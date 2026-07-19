"""Fase 1 del set generator: il layer di pianificazione.

Qui vivono il carattere delle strategie (StrategyProfile) e la matematica degli
archi BPM/energia; sopra ci si costruisce lo scheletro del set (anchor, riserva
delle bombe, piano di genere). Il beam search di set_generator (fase 2) riempie
i segmenti. Direzione delle dipendenze: set_generator importa da qui, mai il
contrario.
"""

import statistics
from dataclasses import dataclass

from app.models import Track
from app.schemas import SetGenerationRequest
from app.services.scoring import genre_families_of


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
    """id -> percentile 0-1 sul pool (rank-based, pari a rango medio).

    Le tracce con lo stesso valore ricevono lo stesso percentile (la media dei
    loro ranghi): l'id non decide piu' chi "vale di piu'" tra gemelle, cosi'
    l'impatto riflette la musica e non l'ordine di inserimento. Chi rompe il
    pareggio a valle (elezione, riserva) resta deterministico per id.
    """
    if not values:
        return {}
    if len(values) == 1:
        return {tid: 0.5 for tid in values}
    ordered = sorted(values.items(), key=lambda kv: (kv[1], kv[0]))
    top = len(ordered) - 1
    out: dict[int, float] = {}
    i, n = 0, len(ordered)
    while i < n:
        j = i
        while j < n and ordered[j][1] == ordered[i][1]:
            j += 1
        mean_rank = (i + j - 1) / 2  # media dei ranghi del gruppo a pari valore
        for k in range(i, j):
            out[ordered[k][0]] = mean_rank / top
        i = j
    return out


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


# Piano di genere: soglie tunabili. Sopra DOMINANT il piano degenera (monogenere);
# una famiglia "conta" solo se copre almeno MIN_SHARE del pool.
_GENRE_DOMINANT_SHARE = 0.80
_GENRE_MIN_SHARE = 0.15


@dataclass(frozen=True)
class GenrePlan:
    """Famiglie assegnate ai segmenti: principal al peak, calm al resto."""
    principal: str
    calm: str


def plan_genre_families(candidates: list[Track]) -> GenrePlan | None:
    """Sceglie famiglia principale (peak) e famiglia calma (resto del set).

    Ritorna None quando il piano non ha senso: pool monogenere (>=80%), nessuna
    seconda famiglia con quota >=15%, o generi tutti ignoti. In quel caso il
    generatore si comporta esattamente come oggi.
    """
    by_family: dict[str, list[Track]] = {}
    for t in candidates:
        for fam in genre_families_of(t.genre):
            by_family.setdefault(fam, []).append(t)
    if not by_family:
        return None
    total = len(candidates)
    counts = {fam: len(ts) for fam, ts in by_family.items()}
    principal = max(counts, key=lambda f: (counts[f], f))
    if counts[principal] / total >= _GENRE_DOMINANT_SHARE:
        return None
    qualified = [f for f, c in counts.items()
                 if f != principal and c / total >= _GENRE_MIN_SHARE]
    if not qualified:
        return None

    def calm_key(fam: str) -> tuple:
        tracks = by_family[fam]
        energies = [t.energy for t in tracks if t.energy is not None]
        if energies:
            return (0, statistics.mean(energies), fam)
        bpms = [t.bpm for t in tracks if t.bpm]
        return (1, statistics.mean(bpms) if bpms else 999.0, fam)

    return GenrePlan(principal=principal, calm=min(qualified, key=calm_key))


# Scheletro: soglie e pesi tunabili. Il fallback (None) riproduce il flusso attuale.
_MIN_POOL_FOR_SKELETON = 8      # sotto, l'elezione degli anchor affama il pool
_MIN_EXPECTED_TRACKS = 6        # set attesi corti: la struttura non ha spazio
_RESERVE_SHARE = 0.15           # quota del pool riservata al peak (le "bombe")
_PEAK_POSITION = 0.7            # arco piatto/ascendente (allineato ad assign_roles)
_PEAK_POSITION_DESCENDING = 0.2  # arco discendente (closing): l'apice sta presto
_PEAK_WINDOW = (0.15, 0.10)     # finestra (prima, dopo) attorno al peak per le bombe
_MIN_ANCHOR_GAP = 0.1           # reset troppo vicini a un altro anchor: scartati
_ANCHOR_SEED_BONUS = 15.0       # i seed valgono anche nell'elezione degli anchor
_PEAK_FAMILY_BONUS = 10.0
_ANCHOR_HINT_BONUS = 12.0       # hint AI (suggest_anchors) sul ruolo in elezione (tunabile)
_ELECTION_MOOD_WEIGHT = 0.2     # peso del mood AI nell'elezione degli anchor (tunabile, max 20 punti)


@dataclass(frozen=True)
class Anchor:
    role: str        # "opening" | "peak" | "reset" | "closing"
    position: float  # frazione 0-1 del set
    track: Track


@dataclass(frozen=True)
class Segment:
    """Tratto da riempire fino all'anchor di arrivo.

    fill_until_secs e' in secondi assoluti di set, gia' al netto della durata
    dell'anchor: il riempimento si ferma li' e l'anchor atterra sulla sua
    posizione nominale.
    """
    end_anchor: Anchor
    fill_until_secs: int
    family: str | None


@dataclass(frozen=True)
class Skeleton:
    anchors: list[Anchor]
    segments: list[Segment]
    reserved_ids: frozenset[int]
    peak_window: tuple[float, float] | None  # (da, a) in progress 0-1


def _arc_fit(value: float | None, desired: float | None) -> float:
    """Aderenza 0-100 a un target (energia): neutro 50 se manca uno dei due."""
    if desired is None or value is None:
        return 50.0
    return max(0.0, 100.0 - abs(float(value) - desired))


def _is_seed(track: Track, seeds: list[str]) -> bool:
    return bool(seeds and track.artist
                and any(s in track.artist.lower() for s in seeds))


def _peak_position(req: SetGenerationRequest, profile: StrategyProfile) -> float:
    """Apice del set: 0.7 di default, presto se l'arco di energia scende."""
    start = end = None
    if req.start_energy is not None or req.end_energy is not None:
        start = req.start_energy if req.start_energy is not None else req.end_energy
        end = req.end_energy if req.end_energy is not None else req.start_energy
    elif profile.energy_arc is not None:
        start, end = profile.energy_arc
    if start is not None and end is not None and end < start:
        return _PEAK_POSITION_DESCENDING
    return _PEAK_POSITION


def build_skeleton(
    candidates: list[Track], req: SetGenerationRequest, profile: StrategyProfile,
    start_bpm: float, end_bpm: float, target_seconds: int,
    mood_scores: dict[int, int] | None = None,
    anchor_hints: dict[str, list[int]] | None = None,
) -> Skeleton | None:
    """Fase 1: elegge gli anchor e prepara segmenti, riserva e piano di genere.

    Ritorna None (fallback alla fase singola attuale) quando la struttura non ha
    spazio: pool piccolo, set atteso corto, o pool troppo stretto per eleggere
    anchor distinti nel rispetto del limite per artista.
    """
    if len(candidates) < _MIN_POOL_FOR_SKELETON:
        return None
    durations = [t.duration_seconds for t in candidates if t.duration_seconds]
    median_duration = statistics.median(durations) if durations else 300
    if target_seconds / max(1, median_duration) < _MIN_EXPECTED_TRACKS:
        return None

    impacts = impact_scores(candidates)
    reserve_size = max(1, round(len(candidates) * _RESERVE_SHARE))
    reserved = frozenset(sorted(impacts, key=lambda t: (-impacts[t], t))[:reserve_size])
    plan = plan_genre_families(candidates)
    seeds = [s.lower() for s in req.seed_artists]

    peak_pos = _peak_position(req, profile)
    # Posizioni degli anchor: opening/closing fissi, peak dalla strategia, reset
    # dai reset_points (scartati se troppo vicini a un anchor gia' piazzato).
    slots: list[tuple[float, str]] = [(0.0, "opening"), (peak_pos, "peak"), (1.0, "closing")]
    for rp in profile.reset_points:
        if all(abs(rp - pos) >= _MIN_ANCHOR_GAP for pos, _ in slots):
            slots.append((rp, "reset"))
    slots.sort()

    taken: set[int] = set()
    artist_counts: dict[str, int] = {}

    def elect(score_fn, avoid: frozenset[int]) -> Track | None:
        pool = [t for t in candidates
                if t.id not in taken
                and (not t.artist
                     or artist_counts.get(t.artist.lower(), 0) < req.max_tracks_per_artist)]
        if not pool:
            return None
        preferred = [t for t in pool if t.id not in avoid]
        pool = preferred or pool
        winner = max(pool, key=lambda t: (score_fn(t), -t.id))
        taken.add(winner.id)
        if winner.artist:
            key = winner.artist.lower()
            artist_counts[key] = artist_counts.get(key, 0) + 1
        return winner

    def desired_at(pos: float) -> tuple[float, float | None]:
        return (_desired_bpm(start_bpm, end_bpm, pos, profile.bpm_curve),
                _desired_energy(req, pos, profile))

    def curation_terms(t: Track, role: str) -> float:
        """Curatela AI nell'elezione: mood-fit (sempre, se presente) + hint sull'anchor
        del ruolo (i reset non hanno hint: nessun ruolo "reset" negli anchor_hints)."""
        s = 0.0
        if mood_scores is not None:
            s += mood_scores.get(t.id, 50) * _ELECTION_MOOD_WEIGHT
        if anchor_hints and t.id in anchor_hints.get(role, ()):
            s += _ANCHOR_HINT_BONUS
        return s

    def peak_score(t: Track) -> float:
        d_bpm, d_energy = desired_at(peak_pos)
        s = (impacts[t.id] * 100.0 * 0.6
             + _trajectory_fit(t.bpm, d_bpm) * 0.25
             + _arc_fit(t.energy, d_energy) * 0.15)
        if plan and plan.principal in genre_families_of(t.genre):
            s += _PEAK_FAMILY_BONUS
        return s + (_ANCHOR_SEED_BONUS if _is_seed(t, seeds) else 0.0) + curation_terms(t, "peak")

    def opening_score(t: Track) -> float:
        _, d_energy = desired_at(0.0)
        s = -abs((t.bpm or start_bpm) - start_bpm) * 2.0 + _arc_fit(t.energy, d_energy) * 0.3
        return s + (100.0 if _is_seed(t, seeds) else 0.0) + curation_terms(t, "opening")  # come _pick_first

    def closing_score(t: Track) -> float:
        _, d_energy = desired_at(1.0)
        s = -abs((t.bpm or end_bpm) - end_bpm) * 2.0 + _arc_fit(t.energy, d_energy) * 0.3
        return s + (_ANCHOR_SEED_BONUS if _is_seed(t, seeds) else 0.0) + curation_terms(t, "closing")

    def reset_score_at(pos: float):
        d_bpm, _ = desired_at(pos)

        def score(t: Track) -> float:
            # Un reset e' uno stacco che respira: premia l'energia bassa.
            calm = 100.0 - float(t.energy) if t.energy is not None else 50.0
            return (calm * 0.5 + _trajectory_fit(t.bpm, d_bpm) * 0.2
                    + (_ANCHOR_SEED_BONUS if _is_seed(t, seeds) else 0.0)
                    + curation_terms(t, "reset"))
        return score

    # Ordine di elezione: il peak per primo (criteri piu' esigenti), poi gli
    # estremi, poi i reset. Le bombe restano libere solo per il peak.
    elected: dict[float, Anchor] = {}
    peak_track = elect(peak_score, avoid=frozenset())
    if peak_track is None:
        return None
    elected[peak_pos] = Anchor("peak", peak_pos, peak_track)
    for pos, role in slots:
        if role == "peak":
            continue
        score_fn = {"opening": opening_score, "closing": closing_score}.get(role)
        track = elect(score_fn or reset_score_at(pos), avoid=reserved)
        if track is None:
            return None
        elected[pos] = Anchor(role, pos, track)

    anchors = [elected[pos] for pos, _ in slots]
    segments = []
    for prev, nxt in zip(anchors, anchors[1:]):
        fill_until = max(0, round(nxt.position * target_seconds)
                         - (nxt.track.duration_seconds or 0))
        family = None
        if plan is not None:
            family = plan.principal if nxt.role == "peak" else plan.calm
        segments.append(Segment(end_anchor=nxt, fill_until_secs=fill_until, family=family))

    window = (max(0.0, peak_pos - _PEAK_WINDOW[0]), min(1.0, peak_pos + _PEAK_WINDOW[1]))
    return Skeleton(anchors=anchors, segments=segments,
                    reserved_ids=reserved, peak_window=window)
