"""Curatela AI: compilazione intento, mood-fit a lotti, anchor, degradazione."""

from app.integrations import LLMClient
from app.integrations.llm import LLMError
from app.schemas import SetGenerationRequest
from app.services.ai_curation import compile_intent


class ScriptedLLM(LLMClient):
    """Risponde con output preconfezionati, in ordine; registra le chiamate."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []  # (system, payload, schema)

    def complete_json(self, system_prompt, payload, schema):
        self.calls.append((system_prompt, payload, schema))
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def _intent(**kw):
    base = {"intent_summary": "warm-up deep in salita", "strategy": "warm_up",
            "start_bpm": None, "end_bpm": None, "start_energy": 25, "end_energy": 55,
            "genres": ["deep house"], "seed_artists": [], "target_duration_minutes": None}
    base.update(kw)
    return base


def test_intent_fills_only_unset_fields():
    req = SetGenerationRequest(prompt="warm-up deep che sale piano", strategy="peak_time")
    llm = ScriptedLLM([_intent()])
    merged, compiled, warnings = compile_intent(llm, req, "it")
    assert merged.strategy == "peak_time"          # esplicito dell'utente: vince
    assert merged.start_energy == 25 and merged.end_energy == 55  # vuoti: compilati
    assert merged.genres == ["deep house"]
    assert compiled["intent_summary"] == "warm-up deep in salita"
    assert "strategy" not in compiled              # non applicato -> non dichiarato
    assert warnings == []


def test_intent_skipped_without_prompt():
    req = SetGenerationRequest()
    llm = ScriptedLLM([])
    merged, compiled, warnings = compile_intent(llm, req, "it")
    assert merged is req and compiled == {} and warnings == [] and llm.calls == []


def test_intent_degrades_on_llm_error():
    req = SetGenerationRequest(prompt="qualcosa")
    merged, compiled, warnings = compile_intent(ScriptedLLM([LLMError("boom")]), req, "it")
    assert merged is req and compiled == {}
    assert len(warnings) == 1


def test_intent_rejects_out_of_bounds_values():
    # target 5 min viola ge=10: la ri-validazione Pydantic scarta TUTTO il merge
    # (fail-safe: meglio i vincoli originali che un merge parziale ambiguo).
    req = SetGenerationRequest(prompt="p")
    llm = ScriptedLLM([_intent(target_duration_minutes=5)])
    merged, compiled, warnings = compile_intent(llm, req, "it")
    assert merged is req and compiled == {} and len(warnings) == 1
