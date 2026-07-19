"""Curatela AI del Set Builder (tappa 2).

L'AI legge, non scrive la scaletta: compila l'intento dal prompt libero,
giudica il mood-fit delle candidate a lotti, suggerisce anchor e narra il set
costruito. Il sequencing resta SEMPRE del motore deterministico
(set_generator/set_skeleton). Ogni chiamata LLM degrada con un warning, mai
con un errore. Regola: pool <= POOL_CAP, ogni chiamata vede <= PER_CALL_CAP.
"""

import logging
from collections import Counter

from sqlalchemy.orm import Session

from app.integrations.llm import LLMError
from app.models import Track
from app.repositories import library_stats
from app.schemas import SetGenerationRequest

logger = logging.getLogger(__name__)

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


_STRATEGIES = ("smooth", "progressive", "contrast", "experimental",
               "peak_time", "warm_up", "closing")

INTENT_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "intent_summary": {"type": "string"},
        "strategy": {"type": ["string", "null"], "enum": list(_STRATEGIES) + [None]},
        "start_bpm": {"type": ["number", "null"]},
        "end_bpm": {"type": ["number", "null"]},
        "start_energy": {"type": ["integer", "null"]},
        "end_energy": {"type": ["integer", "null"]},
        "genres": {"type": "array", "items": {"type": "string"}},
        "seed_artists": {"type": "array", "items": {"type": "string"}},
        "target_duration_minutes": {"type": ["integer", "null"]},
    },
    "required": ["intent_summary", "strategy", "start_bpm", "end_bpm", "start_energy",
                 "end_energy", "genres", "seed_artists", "target_duration_minutes"],
}

INTENT_SYSTEM = """Sei l'interprete delle richieste di un DJ. Ricevi il prompt libero
dell'utente e i vincoli gia' impostati nel form. Traduci il prompt in vincoli
strutturati SOLO per i campi che il form ha lasciato vuoti (elencati in
`fields_open`): per gli altri restituisci null/liste vuote. Non inventare: se il
prompt non implica un campo, lascialo null. intent_summary: una frase in cui
riformuli come hai capito la richiesta (mostrata all'utente)."""

_INTENT_LANGUAGE = {
    "it": "Scrivi intent_summary in italiano.",
    "en": "Write intent_summary in English.",
}

# Campi della request che l'intento puo' compilare (mai quelli di sicurezza
# come owned_only/sources: restano scelte esplicite dell'utente).
_COMPILABLE = ("strategy", "start_bpm", "end_bpm", "start_energy", "end_energy",
               "genres", "seed_artists", "target_duration_minutes")

_WARN_INTENT_FAILED = {
    "it": "curatela AI: compilazione dell'intento non disponibile (il set usa i vincoli del form)",
    "en": "AI curation: intent compilation unavailable (the set uses the form constraints)",
}


def compile_intent(llm, req: SetGenerationRequest, lang: str,
                   ) -> tuple[SetGenerationRequest, dict, list[str]]:
    """Compila il prompt libero in vincoli, senza mai sovrascrivere l'utente.

    Il discriminante e' req.model_fields_set: un campo passato esplicitamente
    nel payload della request non viene MAI toccato, anche se uguale al default.
    Qualsiasi fallimento (LLM o valori fuori bounds) degrada ai vincoli originali.
    """
    if not (req.prompt and req.prompt.strip()):
        return req, {}, []
    open_fields = [f for f in _COMPILABLE if f not in req.model_fields_set]
    if not open_fields:
        return req, {}, []
    payload = {
        "user_prompt": req.prompt,
        "fields_open": open_fields,
        "form_constraints": {f: getattr(req, f) for f in _COMPILABLE},
    }
    try:
        raw = llm.complete_json(INTENT_SYSTEM + "\n" + _INTENT_LANGUAGE[lang],
                                payload, INTENT_SCHEMA)
    except LLMError:
        logger.warning("compile_intent fallita", exc_info=True)
        return req, {}, [_WARN_INTENT_FAILED[lang]]

    updates = {}
    for f in open_fields:
        value = raw.get(f)
        if value in (None, [], ""):
            continue
        updates[f] = value
    summary = (raw.get("intent_summary") or "").strip()
    if not updates:
        return req, ({"intent_summary": summary} if summary else {}), []
    try:
        merged = SetGenerationRequest.model_validate({**req.model_dump(), **updates})
    except Exception:  # valori compilati fuori bounds: fail-safe sui vincoli originali
        logger.warning("compile_intent: merge scartato dalla validazione", exc_info=True)
        return req, {}, [_WARN_INTENT_FAILED[lang]]
    return merged, {"intent_summary": summary, **updates}, []


MOOD_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object", "additionalProperties": False,
                "properties": {
                    "track_id": {"type": "integer"},
                    "mood_fit": {"type": "integer", "minimum": 0, "maximum": 100},
                    "tags": {"type": "array", "items": {"type": "string"}, "maxItems": 3},
                },
                "required": ["track_id", "mood_fit", "tags"],
            },
        },
    },
    "required": ["items"],
}

MOOD_SYSTEM = """Sei un DJ esperto con vasta conoscenza di artisti, etichette e scene.
Ricevi l'intento del set (prompt e vincoli) e un lotto di tracce candidate.
Per OGNI traccia del lotto esprimi mood_fit 0-100: quanto la traccia appartiene
al mood/racconto richiesto (100 = perfetta, 50 = neutra/sconosciuta, 0 = fuori
luogo), usando la tua conoscenza di brani e artisti oltre ai metadati. tags:
1-3 aggettivi brevi sul carattere della traccia. Giudica la traccia, non
inventare dati tecnici. Usa solo i track_id forniti."""

MOOD_LANGUAGE = {"it": "Scrivi i tag in italiano.", "en": "Write tags in English."}

_WARN_MOOD_BATCH = {
    "it": "curatela AI: giudizio mood non disponibile per una parte delle candidate",
    "en": "AI curation: mood judgement unavailable for part of the candidates",
}
_WARN_MOOD_FOREIGN = {
    "it": "curatela AI: giudizi su tracce non candidate scartati",
    "en": "AI curation: judgements on non-candidate tracks discarded",
}


def _mood_payload(req: SetGenerationRequest, batch: list[Track]) -> dict:
    return {
        "user_prompt": req.prompt or "",
        "constraints": {"strategy": req.strategy, "genres": req.genres,
                        "start_energy": req.start_energy, "end_energy": req.end_energy},
        "candidate_tracks": [_candidate_payload(t) for t in batch],
    }


def score_mood_fit(llm, req: SetGenerationRequest, candidates: list[Track], lang: str,
                   ) -> tuple[dict[int, int], dict[int, list[str]], list[str]]:
    """Mood-fit per candidata, a lotti <= MOOD_BATCH_SIZE (mai oltre PER_CALL_CAP).

    Le candidate senza giudizio (lotto fallito o dimenticate dal modello) valgono
    50 (neutro): non vincono ne' perdono per assenza.
    """
    valid_ids = {t.id for t in candidates}
    scores: dict[int, int] = {}
    tags: dict[int, list[str]] = {}
    warnings: list[str] = []
    foreign = False
    failed = False
    system = MOOD_SYSTEM + "\n" + MOOD_LANGUAGE[lang]
    for start in range(0, len(candidates), MOOD_BATCH_SIZE):
        batch = candidates[start:start + MOOD_BATCH_SIZE]
        try:
            raw = llm.complete_json(system, _mood_payload(req, batch), MOOD_SCHEMA)
        except LLMError:
            logger.warning("score_mood_fit: lotto fallito", exc_info=True)
            failed = True
            continue
        for item in raw.get("items", []):
            tid = item.get("track_id")
            if tid not in valid_ids:
                foreign = True
                continue
            scores[tid] = int(item["mood_fit"])
            tags[tid] = [s for s in item.get("tags", []) if s][:3]
    for t in candidates:
        scores.setdefault(t.id, 50)
    if failed:
        warnings.append(_WARN_MOOD_BATCH[lang])
    if foreign:
        warnings.append(_WARN_MOOD_FOREIGN[lang])
    return scores, tags, warnings
