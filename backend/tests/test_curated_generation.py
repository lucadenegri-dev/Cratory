"""Pipeline di generazione curata: l'AI legge, il motore sequenzia.

tests/ non e' un package: niente import da test_ai_curation, i fake sono locali.
"""

from app.integrations import LLMClient
from app.integrations.llm import LLMError
from app.schemas import SetGenerationRequest
from app.services.ai_curation import run_curated_generation


def _req(**kw):
    base = dict(target_duration_minutes=40, prompt="warm-up deep", use_ai=True)
    base.update(kw)
    return SetGenerationRequest(**base)


def _mood_for(payload_ids, score=70):
    return {"items": [{"track_id": i, "mood_fit": score, "tags": ["deep"]} for i in payload_ids]}


class PipelineLLM(LLMClient):
    """Risponde per schema: intento, mood (per ogni lotto), anchor, narrativa."""

    def __init__(self):
        self.calls = []
        self.intent = {"intent_summary": "warm-up deep in salita", "strategy": "warm_up",
                       "start_bpm": None, "end_bpm": None, "start_energy": 25,
                       "end_energy": 55, "genres": [], "seed_artists": [],
                       "target_duration_minutes": None}

    def complete_json(self, system_prompt, payload, schema):
        self.calls.append((system_prompt, payload, schema))
        props = schema.get("properties", {})
        if "intent_summary" in props:
            return self.intent
        if "items" in props:
            ids = [c["id"] for c in payload["candidate_tracks"]]
            return _mood_for(ids)
        if "peak" in props:
            ids = [c["id"] for c in payload["candidate_tracks"]]
            return {"opening": ids[:1], "peak": ids[1:2], "closing": ids[2:3], "reason": "arco"}
        return {"set_title": "Titolo AI", "global_explanation": "Racconto.",
                "missing_library_suggestions": ["piu' dub"]}


def test_curated_set_is_sequenced_by_the_engine(db, seed_tracks):
    seed_tracks(n=30)
    llm = PipelineLLM()
    setlist = run_curated_generation(db, _req(), llm)
    assert setlist.generated_by == "algorithmic+ai_curation"
    assert setlist.name == "Titolo AI"
    assert setlist.global_explanation == "Racconto."
    assert setlist.curation["intent_summary"] == "warm-up deep in salita"
    assert setlist.validation["missing_library_suggestions"] == ["piu' dub"]
    assert len(setlist.tracks) >= 3
    assert all(st.mood_tags == ["deep"] for st in setlist.tracks)
    # ogni chiamata AI ha visto al massimo 60 candidate
    for _, payload, _schema in llm.calls:
        if "candidate_tracks" in payload:
            assert len(payload["candidate_tracks"]) <= 60


class DeadLLM(LLMClient):
    def complete_json(self, *a, **k):
        raise LLMError("giu'")


def test_all_ai_calls_fail_degrades_to_algorithmic(db, seed_tracks):
    seed_tracks(n=30)
    setlist = run_curated_generation(db, _req(), DeadLLM())
    assert setlist.generated_by == "algorithmic"
    assert setlist.tracks  # il set nasce comunque
    assert setlist.curation["warnings"]  # i fallimenti sono raccontati
    assert setlist.global_explanation  # spiegazione deterministica conservata


def test_user_name_wins_over_ai_title(db, seed_tracks):
    seed_tracks(n=30)
    setlist = run_curated_generation(db, _req(name="Il mio set"), PipelineLLM())
    assert setlist.name == "Il mio set"


def test_phases_are_reported(db, seed_tracks):
    seed_tracks(n=30)
    phases = []
    run_curated_generation(db, _req(), PipelineLLM(), on_phase=phases.append)
    assert len(phases) >= 4  # intento, mood, anchor, costruzione, narrativa


class NarrowGenreLLM(PipelineLLM):
    """Come PipelineLLM, ma l'intento compila un genere che non esiste in libreria:
    il pool con quel vincolo crolla sotto 3 candidate."""

    def __init__(self):
        super().__init__()
        self.intent = {**self.intent, "genres": ["genere inesistente"]}


def test_compiled_constraints_too_strict_fallback_to_original_request(db, seed_tracks):
    seed_tracks(n=30)
    llm = NarrowGenreLLM()
    setlist = run_curated_generation(db, _req(), llm)
    assert setlist.tracks  # il set nasce comunque, niente 422
    assert any("troppo stretti" in w for w in setlist.curation["warnings"])
    assert "genres" not in setlist.curation["compiled"]


def test_router_uses_curated_pipeline(db, seed_tracks, monkeypatch):
    # Il ramo use_ai del router deve puntare alla pipeline curata (niente
    # TestClient: conftest non ha una fixture client, si chiama la funzione
    # del router direttamente col db della fixture).
    import app.routers.sets as sets_router
    from app.schemas import SetGenerationRequest
    from app.services.set_generator import generate_set

    called = {}

    def fake_curated(db_, req_, llm_, on_phase=None):
        called["yes"] = True
        return generate_set(db_, req_)

    monkeypatch.setattr(sets_router, "run_curated_generation", fake_curated)
    monkeypatch.setattr(sets_router, "get_llm_client", lambda model=None: object())
    seed_tracks(n=20)
    out = sets_router.generate(
        SetGenerationRequest(target_duration_minutes=30, use_ai=True, prompt="x"), db=db)
    assert called.get("yes") and out.id
