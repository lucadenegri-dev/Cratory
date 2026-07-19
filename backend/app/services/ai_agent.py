"""AI Set Agent (MVP 3, F7).

Flusso: il Candidate Engine deterministico filtra le tracce -> l'AI interpreta
il prompt, sceglie e ordina e narra -> il Validation Engine ricontrolla e calcola
gli score tecnici. L'AI non riceve mai l'intera libreria e non inventa track_id:
puo' usare solo le candidate fornite (verificato dalla validazione).
"""

import logging

from app.integrations import LLMClient
from app.models import Setlist, SetlistTrack
from app.schemas import AISetResponse
from app.services.ai_curation import (
    _candidate_payload,
    _compute_candidate_profile,
    _rank_candidates,
    _safe_library_context,
)
from app.services.app_state import get_language
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
- missing_library_suggestions: max 3 voci brevi."""

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

Sii CONCISO: reason e transition_note una frase breve; global_explanation max 2 frasi; missing_library_suggestions max 3 voci."""

LANGUAGE_INSTRUCTIONS = {
    "it": "Scrivi SEMPRE in italiano. Rispondi esclusivamente nel formato JSON richiesto.",
    "en": "ALWAYS write in English. Reply exclusively in the requested JSON format.",
}

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


_PHASES = {
    "candidates": {"it": "Seleziono le tracce candidate", "en": "Selecting candidate tracks"},
    "building": {"it": "L'AI sta costruendo il set (puo' richiedere un minuto)",
                 "en": "The AI is building the set (may take a minute)"},
    "validating": {"it": "Valido il risultato", "en": "Validating the result"},
}

_ERRORS = {
    "not_enough_candidates": {
        "it": "Tracce candidate insufficienti per l'AI: allargare i vincoli o importare piu' tracce.",
        "en": "Not enough candidate tracks for the AI: widen the constraints or import more tracks.",
    },
    "no_valid_tracks": {
        "it": "L'AI non ha prodotto tracce valide tra le candidate.",
        "en": "The AI did not produce any valid tracks among the candidates.",
    },
}


def _safe_lang(lang: str) -> str:
    """Guardia lingua sconosciuta -> "it" (stesso default di get_language)."""
    return lang if lang in ("it", "en") else "it"


def generate_ai_set(db, req, llm, on_phase=None):
    """on_phase(str) opzionale per riportare la fase corrente a un job asincrono."""
    lang = _safe_lang(get_language(db))

    def phase(p: str) -> None:
        if on_phase:
            on_phase(p)

    phase(_PHASES["candidates"][lang])
    candidates = select_candidates(db, req)
    if len(candidates) < 3:
        raise AIAgentError(_ERRORS["not_enough_candidates"][lang])
    chosen_candidates = _rank_candidates(candidates, req, budget=MAX_CANDIDATES)
    candidates_by_id = {t.id: t for t in chosen_candidates}

    payload = {
        "user_request": req.prompt or "",
        "structured_constraints": {
            "target_duration_minutes": req.target_duration_minutes,
            "start_bpm": req.start_bpm,
            "end_bpm": req.end_bpm,
            "start_energy": req.start_energy,
            "end_energy": req.end_energy,
            "seed_artists": req.seed_artists,
            "genres": req.genres,
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

    base_prompt = CREATIVE_SYSTEM_PROMPT if getattr(req, "mode", "technical") == "creative" else SYSTEM_PROMPT
    system = base_prompt + "\n" + LANGUAGE_INSTRUCTIONS[lang]
    logger.info("AI Set Agent (%s): %s candidate, prompt=%r",
                getattr(req, "mode", "technical"), len(chosen_candidates), (req.prompt or "")[:80])
    phase(_PHASES["building"][lang])
    raw = llm.complete_json(system, payload, OUTPUT_SCHEMA)
    ai = AISetResponse.model_validate(raw)

    phase(_PHASES["validating"][lang])
    result = validate_ai_set(ai, candidates_by_id, req)
    if not result.tracks:
        raise AIAgentError(_ERRORS["no_valid_tracks"][lang])

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
