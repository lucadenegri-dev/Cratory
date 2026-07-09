"""AI Set Agent (MVP 3, F7).

Flusso: il Candidate Engine deterministico filtra le tracce -> l'AI interpreta
il prompt, sceglie e ordina e narra -> il Validation Engine ricontrolla e calcola
gli score tecnici. L'AI non riceve mai l'intera libreria e non inventa track_id:
puo' usare solo le candidate fornite (verificato dalla validazione).
"""

import logging
from collections import Counter

from sqlalchemy.orm import Session

from app.integrations import LLMClient
from app.models import Setlist, SetlistTrack, Track
from app.repositories import library_stats
from app.schemas import AISetResponse, SetGenerationRequest
from app.services.candidate_engine import select_candidates
from app.services.set_generator import assign_roles
from app.services.validation import validate_ai_set

logger = logging.getLogger(__name__)

MAX_CANDIDATES = 60  # tetto di tracce passate all'AI (token budget / latenza)

SYSTEM_PROMPT = """Sei un DJ esperto che costruisce DJ set coerenti.
Ricevi una richiesta utente, vincoli strutturati, il profilo delle tracce candidate
(BPM arc, distribuzione tonale, generi predominanti, lacune) e la lista delle tracce CANDIDATE
gia' filtrate (con id, titolo, artista, BPM, tonalita' Camelot, durata, genere, sorgente).

Usa `candidate_profile` per capire la palette musicale a disposizione: BPM range, chiavi
prevalenti, generi dominanti, energie medie. Sfrutta questa visione d'insieme per costruire
un arco coerente senza scorrere tutti i candidati a mano. Le lacune segnalate (missing.*)
indicano dove non hai dati affidabili.

Regole inderogabili:
- Usa SOLO le tracce candidate fornite. Seleziona ogni brano col suo "track_id".
- NON citare MAI l'id numerico nei testi: nei campi reason/transition_note e nei
  suggerimenti riferisciti ai brani per «artista – titolo».
- Costruisci una scaletta coerente che rispetti durata target, arco BPM e vincoli.
- Ordina le tracce in modo musicalmente sensato (mixaggio armonico Camelot, progressione BPM).
- reason: in una frase, perché quel brano in quel punto. transition_note: l'INTENZIONE del
  passaggio (energia, groove, stacco). NON affermare che due tonalità sono compatibili né che
  il mix è "armonico"/"in chiave": la compatibilità la calcola il sistema deterministico, e
  affermarla a vanvera è un errore. risk_level: low|medium|high.
- missing_library_suggestions: 0-3 consigli CONCRETI per migliorare il set, cioè che TIPO di
  traccia aggiungere alla libreria (BPM, tonalità, energia, mood, ruolo) per colmare un punto
  debole. Niente id, niente nomi di brani non presenti.

Sii CONCISO per restare reattivo:
- reason e transition_note: una frase breve ciascuno (max ~18 parole).
- global_explanation: max 2 frasi.
- missing_library_suggestions: max 3 voci brevi.
Scrivi SEMPRE in italiano. Rispondi esclusivamente nel formato JSON richiesto."""

# Modalità "creative": l'AI porta giudizio musicale, non solo matching tecnico.
CREATIVE_SYSTEM_PROMPT = """Sei un DJ di esperienza che costruisce un set con gusto e racconto, non solo con la teoria.
Ricevi una richiesta utente, vincoli strutturati, il profilo delle tracce candidate e la lista delle CANDIDATE
(id, titolo, artista, BPM, Camelot, durata, genere, energia, sorgente).

Oltre alla compatibilità tecnica, usa la TUA conoscenza musicale di questi brani e artisti — vibe, peso
culturale, come funzionano in pista, il momento giusto della serata — per costruire un ARCO EMOTIVO:
tensione e rilascio, contrasto voluto, qualche sorpresa, un climax e una chiusura che abbiano senso.
Puoi rompere di proposito una regola armonica o di BPM se serve all'effetto: in quel caso segnala risk_level più alto
e spiega la scelta.

Regole inderogabili (NON negoziabili):
- Usa SOLO le tracce candidate fornite. Seleziona ogni brano col suo "track_id".
- NON citare MAI l'id numerico nei testi: riferisciti ai brani per «artista – titolo».
- I dati tecnici forniti (BPM, Camelot) sono autorevoli: ragiona su quelli, non inventarli.
- Nei testi NON dichiarare compatibilità armonica o "mix in chiave" (la calcola il sistema):
  descrivi l'intenzione musicale — tensione, rilascio, contrasto, il momento della serata.
- Rispetta la durata target e i vincoli espliciti dell'utente (mood/energia/durata).
- Per ogni traccia: reason (perché lì, anche per ragioni musicali/emotive), transition_note (come mixare), risk_level (low|medium|high).
- missing_library_suggestions: max 3 consigli concreti su che TIPO di traccia aggiungere (BPM/tonalità/energia/mood/ruolo) per rendere il set migliore. Niente id.

Sii CONCISO: reason e transition_note una frase breve; global_explanation max 2 frasi; missing_library_suggestions max 3 voci.
Scrivi SEMPRE in italiano. Rispondi esclusivamente nel formato JSON richiesto."""

# JSON Schema per structured outputs (additionalProperties:false ovunque).
OUTPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "set_title": {"type": "string"},
        "global_explanation": {"type": "string"},
        "tracks": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "position": {"type": "integer"},
                    "track_id": {"type": "integer"},
                    "reason": {"type": "string"},
                    "transition_note": {"type": "string"},
                    "risk_level": {"type": "string", "enum": ["low", "medium", "high"]},
                },
                "required": ["position", "track_id", "reason", "transition_note", "risk_level"],
            },
        },
        "missing_library_suggestions": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["set_title", "global_explanation", "tracks", "missing_library_suggestions"],
}


class AIAgentError(Exception):
    pass


CORRIDOR_BANDS = 6  # fasce lungo l'arco BPM per il campionamento stratificato


def _rank_candidates(candidates: list[Track], req: SetGenerationRequest) -> list[Track]:
    """Taglia le candidate a MAX_CANDIDATES garantendo che coprano l'intero arco BPM.

    I seed sono sempre inclusi. Il resto è campionato in modo stratificato lungo il
    corridoio [start_bpm, end_bpm]: così l'AI riceve materiale per tutto il viaggio,
    non solo ammassato vicino allo start (che affamava il finale dell'arco).
    """
    seeds = [s.lower() for s in req.seed_artists]

    def is_seed(t: Track) -> bool:
        return bool(seeds and t.artist and any(s in t.artist.lower() for s in seeds))

    seed_tracks = [t for t in candidates if is_seed(t)]
    rest = [t for t in candidates if not is_seed(t)]
    budget = MAX_CANDIDATES - len(seed_tracks)
    if budget <= 0:
        return seed_tracks[:MAX_CANDIDATES]

    declared = [b for b in (req.start_bpm, req.end_bpm) if b]
    lo, hi = (min(declared), max(declared)) if declared else (None, None)

    if lo is None or hi == lo:
        # Nessun corridoio dichiarato: vicinanza allo start (o ordine per BPM).
        anchor = req.start_bpm or 0
        chosen = sorted(rest, key=lambda t: (abs((t.bpm or anchor) - anchor), t.id))[:budget]
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

    per_band = max(1, budget // CORRIDOR_BANDS)
    chosen: list[Track] = []
    picked: set[int] = set()
    for band in range(CORRIDOR_BANDS):
        center = lo + (band + 0.5) * width
        band_tracks = sorted(buckets.get(band, []), key=lambda t: (abs((t.bpm or center) - center), t.id))
        for t in band_tracks[:per_band]:
            chosen.append(t)
            picked.add(t.id)

    # Riempi lo spazio residuo con le migliori rimanenti (vicinanza al corridoio).
    if len(chosen) < budget:
        def corridor_dist(t: Track) -> float:
            if t.bpm is None:
                return 1e9
            return max(0.0, lo - t.bpm, t.bpm - hi)
        leftover = sorted((t for t in rest if t.id not in picked),
                          key=lambda t: (corridor_dist(t), t.id))
        chosen.extend(leftover[:budget - len(chosen)])

    return seed_tracks + chosen[:budget]


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


def generate_ai_set(db, req, llm, on_phase=None):
    """on_phase(str) opzionale per riportare la fase corrente a un job asincrono."""
    def phase(p: str) -> None:
        if on_phase:
            on_phase(p)

    phase("Seleziono le tracce candidate")
    candidates = select_candidates(db, req)
    if len(candidates) < 3:
        raise AIAgentError(
            "Tracce candidate insufficienti per l'AI: allargare i vincoli o importare piu' tracce."
        )
    chosen_candidates = _rank_candidates(candidates, req)
    candidates_by_id = {t.id: t for t in chosen_candidates}

    payload = {
        "user_request": req.prompt or "",
        "structured_constraints": {
            "target_duration_minutes": req.target_duration_minutes,
            "start_bpm": req.start_bpm,
            "end_bpm": req.end_bpm,
            "start_energy": req.start_energy,
            "end_energy": req.end_energy,
            "start_mood": req.start_mood,
            "end_mood": req.end_mood,
            "seed_artists": req.seed_artists,
            "genre": req.genre,
            "preferred_keys": req.preferred_keys,
            "strategy": req.strategy,
            "max_tracks_per_artist": req.max_tracks_per_artist,
            "sources": req.sources,
            "prefer_harmonic": req.prefer_harmonic,
            "prefer_progressive_bpm": req.prefer_progressive_bpm,
            "allow_sharp_changes": req.allow_sharp_changes,
        },
        "candidate_profile": _compute_candidate_profile(chosen_candidates),
        "candidate_tracks": [_candidate_payload(t) for t in chosen_candidates],
        "library_context": _safe_library_context(db),
    }

    system = CREATIVE_SYSTEM_PROMPT if getattr(req, "mode", "technical") == "creative" else SYSTEM_PROMPT
    logger.info("AI Set Agent (%s): %s candidate, prompt=%r",
                getattr(req, "mode", "technical"), len(chosen_candidates), (req.prompt or "")[:80])
    phase("L'AI sta costruendo il set (puo' richiedere un minuto)")
    raw = llm.complete_json(system, payload, OUTPUT_SCHEMA)
    ai = AISetResponse.model_validate(raw)

    phase("Valido il risultato")
    result = validate_ai_set(ai, candidates_by_id, req)
    if not result.tracks:
        raise AIAgentError("L'AI non ha prodotto tracce valide tra le candidate.")

    setlist = Setlist(
        name=ai.set_title or req.name or "Set AI",
        target_duration_minutes=req.target_duration_minutes,
        start_bpm=req.start_bpm,
        end_bpm=req.end_bpm,
        strategy=req.strategy,
        prompt=req.prompt,
        global_explanation=ai.global_explanation,
        generated_by="ai",
        owned_only=req.owned_only,
        validation={
            **result.as_dict(),
            "missing_library_suggestions": ai.missing_library_suggestions,
        },
    )
    roles = assign_roles(len(result.tracks))
    for position, vt in enumerate(result.tracks, start=1):
        setlist.tracks.append(SetlistTrack(
            track_id=vt.track.id,
            position=position,
            role=roles[position - 1],
            transition_score=vt.transition_score,
            transition_reason=vt.transition_reason,
            transition_note=vt.transition_note,
            ai_reason=vt.ai_reason,
            risk_level=vt.risk_level,
        ))
    db.add(setlist)
    db.commit()
    db.refresh(setlist)
    logger.info("Set AI generato: %s tracce, %s warning", len(result.tracks), len(result.warnings))
    return setlist


def _safe_library_context(db: Session) -> dict:
    stats = library_stats(db)
    return {
        "total_tracks": stats["total_tracks"],
        "bpm_min": stats["bpm_min"],
        "bpm_max": stats["bpm_max"],
        "key_distribution": stats["key_distribution"],
    }
