"""Set generator algoritmico deterministico: beam search sulla traiettoria BPM +
scoring transizioni, con profili per dare un carattere distinto a ciascuna strategia.

Il beam costruisce piu' set in parallelo e tiene il migliore (con rete di sicurezza
sul percorso greedy, così non fa mai peggio). Resta il fallback deterministico
accanto all'AI Set Agent, che riceve le candidate da candidate_engine e gli score
da scoring.
"""

import logging
import statistics

from sqlalchemy.orm import Session

from app.models import Setlist, SetlistTrack, Track
from app.repositories import effective_genres_for_tracks
from app.schemas import SetGenerationRequest
from app.services.camelot import camelot_compatibility
from app.services.scoring import (
    RESET_ENERGY_DROP,
    RESET_GENRE_SIMILARITY,
    TransitionScore,
    energy_progression_score,
    genre_families_of,
    genre_of,
    genre_similarity_score,
    risk_from_score,
    score_transition,
)
from app.services.set_skeleton import (  # noqa: F401 - re-export per compat test
    _DEFAULT_PROFILE,
    _STRATEGY_PROFILES,
    StrategyProfile,
    _desired_bpm,
    _desired_energy,
    _trajectory_fit,
    strategy_profile,
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
_RATING_BONUS = 2.0  # per livello di voto (max 6.0): tie-break, mai sopra la compatibilita'
_SEED_BONUS = 15.0
_SHARP_PENALTY = 40.0  # scoraggia i salti bruschi quando la strategia non li vuole
RESET_WINDOW = 0.1     # ampiezza (frazione di set) attorno a un reset point
_CONVERGE_WEIGHT = 0.35   # attrazione verso l'anchor in arrivo (cresce col ramp)
_GENRE_PLAN_WEIGHT = 0.20  # aderenza alla famiglia assegnata al segmento
_RESERVE_PENALTY = 25.0   # bomba spesa fuori dalla finestra del peak
_MOOD_WEIGHT = 0.30       # peso del giudizio mood AI nel ranking dei filler (50 = neutro)
_REQUESTED_GENRE_BONUS = 45.0  # copertura "presence-only": spinge un genere RICHIESTO
#   (req.genres) ancora assente dal set; cala come 1/(1+visti) e si spegne una volta
#   rappresentato, cosi' ogni genere chiesto compare senza forzare quote ne' rovinare
#   il mix. Match esatto sul genere: robusto anche per generi senza famiglia (es. Dub).


def _near_reset(progress: float, points: tuple[float, ...]) -> bool:
    return any(abs(progress - p) <= RESET_WINDOW for p in points)


def _is_reset(prev: Track, cand: Track,
              genre_map: dict[int, str | None] | None = None) -> bool:
    """Stacco netto voluto: forte calo di energia o cambio di genere."""
    if (prev.energy is not None and cand.energy is not None
            and cand.energy - prev.energy <= -RESET_ENERGY_DROP):
        return True
    pg, cg = genre_of(prev, genre_map), genre_of(cand, genre_map)
    return bool(pg and cg and genre_similarity_score(pg, cg) < RESET_GENRE_SIMILARITY)


def _is_novel(prev: Track, cand: Track,
             genre_map: dict[int, str | None] | None = None) -> bool:
    """Esplorazione: cambio di tonalità o di genere rispetto al brano precedente."""
    if prev.camelot_key and cand.camelot_key and prev.camelot_key != cand.camelot_key:
        return True
    pg, cg = genre_of(prev, genre_map), genre_of(cand, genre_map)
    return bool(pg and cg and genre_similarity_score(pg, cg) < RESET_GENRE_SIMILARITY + 15)


class SetGenerationError(Exception):
    pass


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

    # A questa scala (~1 punto per BPM di distanza) il bonus voto additivo
    # ribalterebbe l'aderenza al BPM di partenza: il voto conta SOLO come
    # tie-break puro (secondo criterio dell'ordinamento), mai sommato al punteggio.
    return max(candidates, key=lambda t: (first_score(t), t.rating or 0))


def _candidate_score(
    prev: Track, cand: Track, desired_bpm: float, req: SetGenerationRequest,
    artist_counts: dict[str, int], profile: StrategyProfile, progress: float,
    desired_energy: float | None = None, *,
    converge_to: Track | None = None, converge_ramp: float = 0.0,
    plan_family: str | None = None, reserved_ids: frozenset[int] = frozenset(),
    peak_window: tuple[float, float] | None = None,
    mood_scores: dict[int, int] | None = None,
    genre_counts: dict[str, int] | None = None,
    genre_map: dict[int, str | None] | None = None,
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
    # I4: genere EFFETTIVO (genre_map se fornita, altrimenti Track.genre) — lo
    # stesso valore che ha ammesso `cand` nel pool del candidate engine.
    total += (float(genre_similarity_score(genre_of(prev, genre_map), genre_of(cand, genre_map)))
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
    if (profile.reset_bonus and _near_reset(progress, profile.reset_points)
            and _is_reset(prev, cand, genre_map)):
        total += profile.reset_bonus
    if profile.novelty_bonus and _is_novel(prev, cand, genre_map):
        total += profile.novelty_bonus
    # Convergenza verso l'anchor in arrivo: la vicinanza (misurata come una
    # transizione verso l'anchor) pesa sempre di piu' man mano che il segmento
    # si consuma, cosi' al peak ci si arriva preparati, non per caso.
    if converge_to is not None and converge_ramp > 0.0:
        total += (float(score_transition(cand, converge_to).score)
                  * _CONVERGE_WEIGHT * converge_ramp)
    # Piano di genere del segmento: appartenere alla famiglia assegnata premia,
    # genere ignoto resta neutro, famiglia diversa non guadagna nulla.
    if plan_family is not None:
        families = genre_families_of(genre_of(cand, genre_map))
        fit = 100.0 if plan_family in families else (50.0 if not families else 0.0)
        total += fit * _GENRE_PLAN_WEIGHT * profile.genre_coherence
    # Riserva delle bombe: spenderle lontano dal peak costa.
    if cand.id in reserved_ids and not (
            peak_window and peak_window[0] <= progress <= peak_window[1]):
        total -= _RESERVE_PENALTY
    # Mood-fit della curatela AI: giudizio semantico per traccia (50 = neutro).
    if mood_scores is not None:
        total += float(mood_scores.get(cand.id, 50)) * _MOOD_WEIGHT
    # Copertura dei generi richiesti (presence-only): quando ci sono generi espliciti
    # (form o compilati dall'AI), spingi quelli ancora assenti dal set, con boost
    # decrescente col numero di occorrenze gia' scelte. Senza req.genres e' inerte.
    cand_genre_eff = genre_of(cand, genre_map)
    if req.genres and cand_genre_eff:
        wanted = {g.strip().lower() for g in req.genres if g and g.strip()}
        cand_genre = cand_genre_eff.strip().lower()
        if cand_genre in wanted:
            seen = (genre_counts or {}).get(cand_genre, 0)
            total += _REQUESTED_GENRE_BONUS / (1 + seen)
    # Voto personale: spinta piccola e deterministica, a parita' di compatibilita'.
    total += _RATING_BONUS * (cand.rating or 0)
    return total, ts


# Beam search: invece di costruire UN set passo-passo (greedy, che si intrappola in
# ottimi locali), ne costruisce BEAM_WIDTH in parallelo e alla fine tiene il migliore
# per punteggio cumulativo. Costo: qualche migliaio di score, cioè millisecondi.
BEAM_WIDTH = 6
BEAM_EXPANSIONS = 8


def _beam_search_span(
    opener: Track, candidates: list[Track], req: SetGenerationRequest,
    profile: StrategyProfile, start_bpm: float, end_bpm: float,
    target_seconds: int, *, elapsed_secs: int, fill_until_secs: int,
    converge_to: Track | None = None,
    used: set[int] | None = None, artist_counts: dict[str, int] | None = None,
    plan_family: str | None = None, reserved_ids: frozenset[int] = frozenset(),
    peak_window: tuple[float, float] | None = None,
    mood_scores: dict[int, int] | None = None,
    genre_counts: dict[str, int] | None = None,
    genre_map: dict[int, str | None] | None = None,
    max_count: int | None = None,
) -> list[tuple[Track, TransitionScore]]:
    """Riempe uno span di set col beam search; ritorna i soli filler (opener escluso).

    elapsed_secs include gia' l'opener; ci si ferma a fill_until_secs. Il progress
    passato allo scoring resta GLOBALE (secondi/target del set intero), cosi'
    archi, reset point e finestra del peak parlano la stessa scala. Il ramp di
    convergenza invece e' locale allo span: cresce da 0 a 1 verso l'anchor.

    used viene arricchito con opener.id qui dentro; artist_counts NO: l'artista dell'opener
    deve essere gia' contato dal chiamante (altrimenti il cap per artista sfora di uno).

    max_count: se dato, lo span si chiude appena ha scelto quel numero di tracce,
    a prescindere dai secondi. Serve a "riempi il varco", che ragiona in slot e
    non in durata; None lascia il comportamento a secondi di sempre.
    """
    span_start = elapsed_secs
    span_len = max(1, fill_until_secs - span_start)
    base_used = set(used or ()) | {opener.id}
    base_arts = dict(artist_counts or {})
    base_genres = dict(genre_counts or {})

    def _span_finito(secs: int, quanti: int) -> bool:
        """Il criterio di chiusura dello span: a conteggio se `max_count` c'e',
        altrimenti a secondi come sempre."""
        if max_count is not None:
            return quanti >= max_count
        return secs >= fill_until_secs

    def new_beam() -> dict:
        return {"chosen": [], "prev": opener, "used": set(base_used),
                "arts": dict(base_arts), "genres": dict(base_genres),
                "secs": elapsed_secs, "cum": 0.0,
                "done": _span_finito(elapsed_secs, 0)}

    def expand(b: dict) -> list[dict]:
        progress = min(1.0, b["secs"] / target_seconds)
        ramp = min(1.0, (b["secs"] - span_start) / span_len)
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
            ((_candidate_score(b["prev"], t, desired, req, b["arts"], profile, progress,
                               desired_energy, converge_to=converge_to,
                               converge_ramp=ramp, plan_family=plan_family,
                               reserved_ids=reserved_ids, peak_window=peak_window,
                               mood_scores=mood_scores, genre_counts=b["genres"],
                               genre_map=genre_map), t)
             for t in eligible),
            key=lambda it: (it[0][0], it[1].id), reverse=True,
        )[:BEAM_EXPANSIONS]
        children = []
        for (sc, ts), t in scored:
            arts = dict(b["arts"])
            if t.artist:
                arts[t.artist.lower()] = arts.get(t.artist.lower(), 0) + 1
            genres = dict(b["genres"])
            t_genre = genre_of(t, genre_map)
            if t_genre:
                gk = t_genre.strip().lower()
                genres[gk] = genres.get(gk, 0) + 1
            secs = b["secs"] + (t.duration_seconds or 0)
            children.append({
                "chosen": b["chosen"] + [(t, ts)], "prev": t,
                "used": b["used"] | {t.id}, "arts": arts, "genres": genres,
                "secs": secs, "cum": b["cum"] + sc,
                "done": _span_finito(secs, len(b["chosen"]) + 1),
            })
        return children

    beams = [new_beam()]
    while any(not b["done"] for b in beams):
        expanded: list[dict] = []
        for b in beams:
            expanded.extend([b] if b["done"] else expand(b))
        expanded.sort(key=lambda b: (b["cum"], [t.id for t, _ in b["chosen"]]), reverse=True)
        beams = expanded[:BEAM_WIDTH]

    # Rete di sicurezza greedy, come prima: il percorso "sempre il migliore
    # localmente" resta in gara, il beam non puo' fare peggio.
    greedy = new_beam()
    while not greedy["done"]:
        greedy = expand(greedy)[0]

    complete = [b for b in beams if _span_finito(b["secs"], len(b["chosen"]))] or beams
    complete.append(greedy)
    best = max(complete, key=lambda b: (b["cum"] / max(1, len(b["chosen"])),
                                        [t.id for t, _ in b["chosen"]]))
    return best["chosen"]


