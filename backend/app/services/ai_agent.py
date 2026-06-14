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
- Usa SOLO le tracce candidate fornite. Non inventare track_id ne' tracce.
- Riferisciti a ogni traccia tramite il suo "id" numerico.
- Costruisci una scaletta coerente che rispetti durata target, arco BPM e vincoli.
- Ordina le tracce in modo musicalmente sensato (mixaggio armonico Camelot, progressione BPM).
- Per ogni traccia spiega brevemente la scelta (reason) e la transizione (transition_note),
  e indica il rischio della transizione (low|medium|high).
- Distingui dati di fatto da inferenze musicali e da ipotesi creative.
- Fornisci una global_explanation narrativa, eventuali critical_points, alternative_directions
  e missing_library_suggestions (cosa manca in libreria, in modo contestualizzato).

Sii CONCISO per restare reattivo:
- reason e transition_note: una frase breve ciascuno (max ~20 parole).
- global_explanation: max 3-4 frasi.
- ogni lista (critical_points, alternative_directions, missing_library_suggestions): max 3 voci brevi.
Rispondi esclusivamente nel formato JSON richiesto."""

# Modalità "creative": l'AI porta giudizio musicale, non solo matching tecnico.
CREATIVE_SYSTEM_PROMPT = """Sei un DJ di esperienza che costruisce un set con gusto e racconto, non solo con la teoria.
Ricevi una richiesta utente, vincoli strutturati, il profilo delle tracce candidate e la lista delle CANDIDATE
(id, titolo, artista, BPM, Camelot, durata, genere, mood, energia, sorgente).

Oltre alla compatibilità tecnica, usa la TUA conoscenza musicale di questi brani e artisti — vibe, peso
culturale, come funzionano in pista, il momento giusto della serata — per costruire un ARCO EMOTIVO:
tensione e rilascio, contrasto voluto, qualche sorpresa, un climax e una chiusura che abbiano senso.
Puoi rompere di proposito una regola armonica o di BPM se serve all'effetto: in quel caso segnala risk_level più alto
e spiega la scelta.

Regole inderogabili (NON negoziabili):
- Usa SOLO le tracce candidate fornite. Non inventare track_id né tracce.
- Riferisciti a ogni traccia tramite il suo "id" numerico.
- I dati tecnici forniti (BPM, Camelot) sono autorevoli: ragiona su quelli, non inventarli.
- Rispetta la durata target e i vincoli espliciti dell'utente (mood/energia/durata).
- Per ogni traccia: reason (perché lì, anche per ragioni musicali/emotive), transition_note, risk_level (low|medium|high).
- global_explanation che racconti l'arco del set; più critical_points, alternative_directions, missing_library_suggestions.

Sii CONCISO: reason e transition_note una frase breve; global_explanation max 3-4 frasi; ogni lista max 3 voci.
Rispondi esclusivamente nel formato JSON richiesto."""

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
        "critical_points": {"type": "array", "items": {"type": "string"}},
        "alternative_directions": {"type": "array", "items": {"type": "string"}},
        "missing_library_suggestions": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "set_title", "global_explanation", "tracks",
        "critical_points", "alternative_directions", "missing_library_suggestions",
    ],
}


class AIAgentError(Exception):
    pass


def _rank_candidates(candidates: list[Track], req: SetGenerationRequest) -> list[Track]:
    """Ordina e taglia le candidate per rilevanza, garantendo gli artisti seed."""
    seeds = [s.lower() for s in req.seed_artists]
    anchor_bpm = req.start_bpm or 0

    def relevance(t: Track) -> float:
        score = 0.0
        if seeds and t.artist and any(s in t.artist.lower() for s in seeds):
            score += 1000.0
        if anchor_bpm and t.bpm:
            score -= abs(t.bpm - anchor_bpm)
        return score

    ranked = sorted(candidates, key=relevance, reverse=True)
    return ranked[:MAX_CANDIDATES]


def _candidate_payload(t: Track) -> dict:
    return {
        "id": t.id,
        "title": t.title or "",
        "artist": t.artist or "",
        "bpm": round(t.bpm, 1) if t.bpm else None,
        "key": t.camelot_key or "",
        "duration_seconds": t.duration_seconds or 0,
        "genre": t.genre or "",
        "mood": t.mood or "",
        "energy": t.energy,
        "source": t.source_type,
    }


def _compute_candidate_profile(candidates: list[Track]) -> dict:
    """Profilo sintetico delle candidate: BPM arc, distribuzione chiavi, top generi, lacune."""
    bpms = [t.bpm for t in candidates if t.bpm is not None]
    keys = [t.camelot_key for t in candidates if t.camelot_key]
    genres = [t.genre for t in candidates if t.genre]
    energies = [t.energy for t in candidates if t.energy is not None]
    moods = [t.mood for t in candidates if t.mood]

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
        "top_moods": [m for m, _ in Counter(moods).most_common(3)],
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
        validation={
            **result.as_dict(),
            "critical_points": ai.critical_points,
            "alternative_directions": ai.alternative_directions,
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
