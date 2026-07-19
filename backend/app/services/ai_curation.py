"""Curatela AI del Set Builder (tappa 2).

L'AI legge, non scrive la scaletta: compila l'intento dal prompt libero,
giudica il mood-fit delle candidate a lotti, suggerisce anchor e narra il set
costruito. Il sequencing resta SEMPRE del motore deterministico
(set_generator/set_skeleton). Ogni chiamata LLM degrada con un warning, mai
con un errore. Regola: pool <= POOL_CAP, ogni chiamata vede <= PER_CALL_CAP.
"""

from collections import Counter

from sqlalchemy.orm import Session

from app.models import Track
from app.repositories import library_stats
from app.schemas import SetGenerationRequest

POOL_CAP = 200  # tetto massimo del pool di candidate portate in memoria per la curatela
PER_CALL_CAP = 60  # tetto di tracce viste da una singola chiamata LLM (token budget / latenza)
MOOD_BATCH_SIZE = 50  # dimensione dei lotti per il giudizio di mood-fit

CORRIDOR_BANDS = 6  # fasce lungo l'arco BPM per il campionamento stratificato


def _rank_candidates(candidates: list[Track], req: SetGenerationRequest, budget: int = POOL_CAP) -> list[Track]:
    """Taglia le candidate a `budget` garantendo che coprano l'intero arco BPM.

    I seed sono sempre inclusi. Il resto è campionato in modo stratificato lungo il
    corridoio [start_bpm, end_bpm]: così l'AI riceve materiale per tutto il viaggio,
    non solo ammassato vicino allo start (che affamava il finale dell'arco).
    """
    seeds = [s.lower() for s in req.seed_artists]

    def is_seed(t: Track) -> bool:
        return bool(seeds and t.artist and any(s in t.artist.lower() for s in seeds))

    seed_tracks = [t for t in candidates if is_seed(t)]
    rest = [t for t in candidates if not is_seed(t)]
    rest_budget = budget - len(seed_tracks)
    if rest_budget <= 0:
        return seed_tracks[:budget]

    declared = [b for b in (req.start_bpm, req.end_bpm) if b]
    lo, hi = (min(declared), max(declared)) if declared else (None, None)

    if lo is None or hi == lo:
        # Nessun corridoio dichiarato: vicinanza al BPM ancora (start, oppure
        # l'unico valore dichiarato). Senza alcun vincolo BPM l'ancora è la
        # mediana del pool (deterministica): ancorare a 0 degenerava nel
        # selezionare sempre le 60 tracce più lente della libreria.
        anchor = req.start_bpm or req.end_bpm
        if not anchor:
            pool_bpms = sorted(t.bpm for t in rest if t.bpm is not None)
            anchor = pool_bpms[len(pool_bpms) // 2] if pool_bpms else 0.0
        chosen = sorted(rest, key=lambda t: (abs((t.bpm or anchor) - anchor), t.id))[:rest_budget]
        return seed_tracks + chosen

    width = (hi - lo) / CORRIDOR_BANDS

    def band_of(bpm: float | None) -> int:
        if bpm is None:
            return -1
        if bpm <= lo:
            return 0
        if bpm >= hi:
            return CORRIDOR_BANDS - 1
        return min(CORRIDOR_BANDS - 1, int((bpm - lo) / width))

    buckets: dict[int, list[Track]] = {}
    for t in rest:
        buckets.setdefault(band_of(t.bpm), []).append(t)

    per_band = max(1, rest_budget // CORRIDOR_BANDS)
    chosen: list[Track] = []
    picked: set[int] = set()
    for band in range(CORRIDOR_BANDS):
        center = lo + (band + 0.5) * width
        band_tracks = sorted(buckets.get(band, []), key=lambda t: (abs((t.bpm or center) - center), t.id))
        for t in band_tracks[:per_band]:
            chosen.append(t)
            picked.add(t.id)

    # Riempi lo spazio residuo con le migliori rimanenti (vicinanza al corridoio).
    if len(chosen) < rest_budget:
        def corridor_dist(t: Track) -> float:
            if t.bpm is None:
                return 1e9
            return max(0.0, lo - t.bpm, t.bpm - hi)
        leftover = sorted((t for t in rest if t.id not in picked),
                          key=lambda t: (corridor_dist(t), t.id))
        chosen.extend(leftover[:rest_budget - len(chosen)])

    return seed_tracks + chosen[:rest_budget]


def _candidate_payload(t: Track) -> dict:
    return {
        "id": t.id,
        "title": t.title or "",
        "artist": t.artist or "",
        "bpm": round(t.bpm, 1) if t.bpm else None,
        "key": t.camelot_key or "",
        "duration_seconds": t.duration_seconds or 0,
        "genre": t.genre or "",
        "energy": t.energy,
        "source": t.source_type,
    }


def _compute_candidate_profile(candidates: list[Track]) -> dict:
    """Profilo sintetico delle candidate: BPM arc, distribuzione chiavi, top generi, lacune."""
    bpms = [t.bpm for t in candidates if t.bpm is not None]
    keys = [t.camelot_key for t in candidates if t.camelot_key]
    genres = [t.genre for t in candidates if t.genre]
    energies = [t.energy for t in candidates if t.energy is not None]

    return {
        "candidate_count": len(candidates),
        "bpm_range": {
            "min": round(min(bpms), 1),
            "max": round(max(bpms), 1),
            "mean": round(sum(bpms) / len(bpms), 1),
        } if bpms else {},
        "key_distribution": dict(Counter(keys).most_common()),
        "top_genres": [g for g, _ in Counter(genres).most_common(5)],
        "avg_energy": round(sum(energies) / len(energies)) if energies else None,
        "missing": {
            "bpm": len(candidates) - len(bpms),
            "key": len(candidates) - len(keys),
            "genre": len(candidates) - len(genres),
        },
    }


def _safe_library_context(db: Session) -> dict:
    stats = library_stats(db)
    return {
        "total_tracks": stats["total_tracks"],
        "bpm_min": stats["bpm_min"],
        "bpm_max": stats["bpm_max"],
        "key_distribution": stats["key_distribution"],
    }
