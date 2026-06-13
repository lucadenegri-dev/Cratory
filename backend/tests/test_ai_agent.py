"""Test dell'AI Set Agent e del Validation Engine con un LLM finto (niente rete/chiave)."""

import pytest

from app.integrations import LLMClient
from app.schemas import SetGenerationRequest
from app.services.ai_agent import AIAgentError, generate_ai_set
from app.services.import_service import import_rekordbox_xml


class FakeLLM(LLMClient):
    """Sceglie le prime N candidate in ordine e restituisce un set JSON valido."""

    def __init__(self, n=8, extra_ids=None, duplicate_first=False):
        self.n = n
        self.extra_ids = extra_ids or []
        self.duplicate_first = duplicate_first
        self.last_payload = None

    def complete_json(self, system_prompt, payload, schema):
        self.last_payload = payload
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
            "critical_points": ["punto critico"],
            "alternative_directions": ["piu' morbido"],
            "missing_library_suggestions": ["esplora label X"],
        }


def _req(**kw):
    base = dict(target_duration_minutes=40, start_bpm=128, end_bpm=134, prompt="set club fluido", use_ai=True)
    base.update(kw)
    return SetGenerationRequest(**base)


def test_ai_set_uses_only_candidates(db, sample_xml_bytes):
    import_rekordbox_xml(db, sample_xml_bytes)
    llm = FakeLLM(n=8)
    setlist = generate_ai_set(db, _req(), llm)

    assert setlist.generated_by == "ai"
    assert setlist.global_explanation
    assert len(setlist.tracks) == 8
    candidate_ids = {c["id"] for c in llm.last_payload["candidate_tracks"]}
    assert all(st.track_id in candidate_ids for st in setlist.tracks)
    # l'AI non riceve l'intera libreria
    assert len(llm.last_payload["candidate_tracks"]) <= 80


def test_ai_set_persists_narrative_and_validation(db, sample_xml_bytes):
    import_rekordbox_xml(db, sample_xml_bytes)
    setlist = generate_ai_set(db, _req(), FakeLLM(n=6))
    v = setlist.validation
    assert "warnings" in v and "stats" in v
    assert v["missing_library_suggestions"] == ["esplora label X"]
    assert v["critical_points"] == ["punto critico"]
    # gli score di transizione sono calcolati dal motore deterministico, non dall'AI
    assert setlist.tracks[0].transition_score is None  # apertura
    assert all(st.ai_reason for st in setlist.tracks)


def test_validation_drops_invalid_track_id(db, sample_xml_bytes):
    import_rekordbox_xml(db, sample_xml_bytes)
    llm = FakeLLM(n=5, extra_ids=[999999])  # id inesistente
    setlist = generate_ai_set(db, _req(), llm)
    assert len(setlist.tracks) == 5  # bogus scartato
    assert any("999999" in w for w in setlist.validation["warnings"])


def test_validation_removes_duplicates(db, sample_xml_bytes):
    import_rekordbox_xml(db, sample_xml_bytes)
    llm = FakeLLM(n=5, duplicate_first=True)
    setlist = generate_ai_set(db, _req(), llm)
    ids = [st.track_id for st in setlist.tracks]
    assert len(ids) == len(set(ids))
    assert any("duplicato" in f for f in setlist.validation["auto_fixes"])


def test_validation_enforces_source_filter(db, sample_xml_bytes):
    import_rekordbox_xml(db, sample_xml_bytes)
    setlist = generate_ai_set(db, _req(sources=["spotify"]), FakeLLM(n=8))
    assert all(st.track.source_type == "spotify" for st in setlist.tracks)


def test_ai_agent_errors_without_candidates(db):
    # DB vuoto: nessuna candidata
    with pytest.raises(AIAgentError):
        generate_ai_set(db, _req(), FakeLLM())
