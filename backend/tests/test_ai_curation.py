"""Curatela AI: compilazione intento, mood-fit a lotti, anchor, degradazione."""

from app.integrations import LLMClient
from app.integrations.llm import LLMError
from app.models import Track
from app.schemas import SetGenerationRequest
from app.services.ai_curation import compile_intent, score_mood_fit, suggest_anchors


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


def _mk_track(i, genre="Techno"):
    t = Track(source_type="spotify", title=f"T{i}", artist=f"A{i}",
              duration_seconds=200, bpm=120.0 + i, camelot_key="8A", genre=genre)
    t.id = i
    return t


def _mood_response(ids, score=80):
    return {"items": [{"track_id": i, "mood_fit": score, "tags": ["deep"]} for i in ids]}


def test_mood_batches_of_50_and_merges():
    cands = [_mk_track(i) for i in range(1, 121)]  # 120 -> 3 lotti (50/50/20)
    llm = ScriptedLLM([_mood_response(range(1, 51)), _mood_response(range(51, 101), score=30),
                       _mood_response(range(101, 121))])
    scores, tags, warnings = score_mood_fit(llm, SetGenerationRequest(prompt="p"), cands, "it")
    assert len(llm.calls) == 3
    assert all(len(c[1]["candidate_tracks"]) <= 60 for c in llm.calls)  # tetto per chiamata
    assert scores[1] == 80 and scores[60] == 30 and scores[110] == 80
    assert tags[1] == ["deep"]
    assert warnings == []


def test_mood_discards_foreign_ids_and_fills_neutral():
    cands = [_mk_track(i) for i in range(1, 4)]
    resp = {"items": [{"track_id": 1, "mood_fit": 90, "tags": ["dark"]},
                      {"track_id": 999, "mood_fit": 10, "tags": ["x"]}]}
    scores, tags, warnings = score_mood_fit(ScriptedLLM([resp]),
                                            SetGenerationRequest(prompt="p"), cands, "it")
    assert scores == {1: 90, 2: 50, 3: 50}
    assert 999 not in scores and tags.get(2, []) == []
    assert len(warnings) == 1  # id estranei scartati (aggregato)


def test_mood_failed_batch_degrades_but_others_survive():
    cands = [_mk_track(i) for i in range(1, 101)]  # 2 lotti
    llm = ScriptedLLM([LLMError("boom"), _mood_response(range(51, 101), score=70)])
    scores, tags, warnings = score_mood_fit(llm, SetGenerationRequest(prompt="p"), cands, "it")
    assert scores[10] == 50 and scores[60] == 70
    assert len(warnings) == 1


def test_anchors_sees_top60_by_mood_and_validates_ids():
    cands = [_mk_track(i) for i in range(1, 101)]
    mood = {i: (90 if i <= 55 else 20) for i in range(1, 101)}
    resp = {"opening": [3], "peak": [7, 999], "closing": [55], "reason": "arco"}
    llm = ScriptedLLM([resp])
    hints, warnings = suggest_anchors(llm, SetGenerationRequest(prompt="p"), cands, mood, "it")
    sent_ids = {c["id"] for c in llm.calls[0][1]["candidate_tracks"]}
    assert len(sent_ids) == 60 and all(mood[i] >= 20 for i in sent_ids)
    assert set(range(1, 56)) <= sent_ids          # le top per mood ci sono tutte
    assert hints == {"opening": [3], "peak": [7], "closing": [55]}  # 999 scartato
    assert len(warnings) == 1


def test_anchors_degrade_on_llm_error():
    cands = [_mk_track(i) for i in range(1, 10)]
    hints, warnings = suggest_anchors(ScriptedLLM([LLMError("boom")]),
                                      SetGenerationRequest(prompt="p"), cands,
                                      {t.id: 50 for t in cands}, "it")
    assert hints == {} and len(warnings) == 1
