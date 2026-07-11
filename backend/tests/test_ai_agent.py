"""Test dell'AI Set Agent e del Validation Engine con un LLM finto (niente rete/chiave)."""

import pytest

from app.integrations import LLMClient
from app.schemas import SetGenerationRequest
from app.services.ai_agent import AIAgentError, generate_ai_set
from app.services.app_state import set_state


class FakeLLM(LLMClient):
    """Sceglie le prime N candidate in ordine e restituisce un set JSON valido."""

    def __init__(self, n=8, extra_ids=None, duplicate_first=False):
        self.n = n
        self.extra_ids = extra_ids or []
        self.duplicate_first = duplicate_first
        self.last_payload = None
        self.last_system = None

    def complete_json(self, system_prompt, payload, schema):
        self.last_payload = payload
        self.last_system = system_prompt
        cands = payload["candidate_tracks"]
        ids = [c["id"] for c in cands[: self.n]]
        if self.duplicate_first and ids:
            ids.append(ids[0])
        ids += self.extra_ids
        return {
            "set_title": "Set di prova",
            "global_explanation": "Spiegazione narrativa di prova.",
            "tracks": [
                {"position": i + 1, "track_id": tid, "reason": "scelta", "transition_note": "mix", "risk_level": "low"}
                for i, tid in enumerate(ids)
            ],
            "missing_library_suggestions": ["esplora label X"],
        }


def _req(**kw):
    base = dict(target_duration_minutes=40, start_bpm=128, end_bpm=134, prompt="set club fluido", use_ai=True)
    base.update(kw)
    return SetGenerationRequest(**base)


def test_ai_set_uses_only_candidates(db, seed_tracks):
    seed_tracks(n=30)
    llm = FakeLLM(n=8)
    setlist = generate_ai_set(db, _req(), llm)

    assert setlist.generated_by == "ai"
    assert setlist.global_explanation
    assert len(setlist.tracks) == 8
    candidate_ids = {c["id"] for c in llm.last_payload["candidate_tracks"]}
    assert all(st.track_id in candidate_ids for st in setlist.tracks)
    # l'AI non riceve mai l'intera libreria
    assert len(llm.last_payload["candidate_tracks"]) <= 60


def test_ai_set_persists_narrative_and_validation(db, seed_tracks):
    seed_tracks(n=30)
    setlist = generate_ai_set(db, _req(), FakeLLM(n=6))
    v = setlist.validation
    assert "warnings" in v and "stats" in v
    assert v["missing_library_suggestions"] == ["esplora label X"]
    # gli score di transizione sono calcolati dal motore deterministico, non dall'AI
    assert setlist.tracks[0].transition_score is None  # apertura
    assert all(st.ai_reason for st in setlist.tracks)


def test_validation_drops_invalid_track_id(db, seed_tracks):
    seed_tracks(n=30)
    llm = FakeLLM(n=5, extra_ids=[999999])  # id inesistente
    setlist = generate_ai_set(db, _req(), llm)
    assert len(setlist.tracks) == 5  # bogus scartato
    warnings = setlist.validation["warnings"]
    assert any("non è tra le candidate" in w for w in warnings)
    assert all("999999" not in w for w in warnings)  # nessun id numerico nei messaggi


def test_validation_removes_duplicates(db, seed_tracks):
    seed_tracks(n=30)
    llm = FakeLLM(n=5, duplicate_first=True)
    setlist = generate_ai_set(db, _req(), llm)
    ids = [st.track_id for st in setlist.tracks]
    assert len(ids) == len(set(ids))
    assert any("duplicato" in f for f in setlist.validation["auto_fixes"])


def test_validation_enforces_source_filter(db, seed_tracks):
    seed_tracks(n=30)
    setlist = generate_ai_set(db, _req(sources=["spotify"]), FakeLLM(n=8))
    assert all(st.track.source_type == "spotify" for st in setlist.tracks)


def test_ai_agent_errors_without_candidates(db):
    # DB vuoto: nessuna candidata
    with pytest.raises(AIAgentError):
        generate_ai_set(db, _req(), FakeLLM())


def test_ai_agent_reports_phases(db, seed_tracks):
    seed_tracks(n=30)
    phases = []
    generate_ai_set(db, _req(), FakeLLM(n=5), on_phase=phases.append)
    assert phases  # il job asincrono riceve le fasi
    assert any("AI" in p for p in phases)


def test_creative_mode_uses_creative_prompt(db, seed_tracks):
    seed_tracks(n=30)
    llm = FakeLLM(n=6)
    generate_ai_set(db, _req(mode="creative"), llm)
    assert "arco emotivo" in llm.last_system.lower()
    assert "conoscenza musicale" in llm.last_system.lower()


def test_technical_mode_is_default(db, seed_tracks):
    seed_tracks(n=30)
    llm = FakeLLM(n=6)
    generate_ai_set(db, _req(), llm)  # default = technical
    assert "arco emotivo" not in llm.last_system.lower()


def test_prompt_lingua_default_italiano(db, seed_tracks):
    seed_tracks(n=30)
    llm = FakeLLM(n=6)
    generate_ai_set(db, _req(), llm)
    assert "Scrivi SEMPRE in italiano" in llm.last_system
    assert "ALWAYS write in English" not in llm.last_system


def test_prompt_lingua_en(db, seed_tracks):
    seed_tracks(n=30)
    set_state(db, "language", "en")
    llm = FakeLLM(n=6)
    generate_ai_set(db, _req(), llm)
    assert "ALWAYS write in English" in llm.last_system
    assert "italiano" not in llm.last_system


def test_fasi_lingua_en(db, seed_tracks):
    seed_tracks(n=30)
    set_state(db, "language", "en")
    phases = []
    generate_ai_set(db, _req(), FakeLLM(n=5), on_phase=phases.append)
    assert any("Selecting candidate tracks" in p for p in phases)
    assert any("building" in p.lower() for p in phases)
    assert not any("Seleziono" in p for p in phases)


def test_errore_candidate_insufficienti_lingua_en(db):
    set_state(db, "language", "en")
    with pytest.raises(AIAgentError, match="Not enough candidate tracks"):
        generate_ai_set(db, _req(), FakeLLM())


def test_prompt_contains_candidate_profile(db, seed_tracks):
    """Il payload verso l'AI include il profilo sintetico delle candidate."""
    seed_tracks(n=30)
    llm = FakeLLM(n=8)
    generate_ai_set(db, _req(), llm)
    profile = llm.last_payload.get("candidate_profile")
    assert profile is not None
    assert "bpm_range" in profile
    assert profile["bpm_range"]  # non vuoto: le tracce hanno BPM
    assert "key_distribution" in profile
    assert profile["key_distribution"]  # non vuoto: le tracce hanno camelot_key
    assert "top_genres" in profile
    assert "missing" in profile
    assert profile["candidate_count"] > 0
