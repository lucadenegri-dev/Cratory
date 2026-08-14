# Set Builder Tappa 2: l'AI cura, il motore sequenzia — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ritirare il percorso "AI ordina la scaletta" e sostituirlo con un layer di curatela: l'AI compila l'intento dal prompt libero, giudica il mood-fit di un pool fino a 200 candidate (a lotti ≤60), suggerisce anchor, e narra il set a valle — il sequencing resta sempre del motore deterministico a due fasi.

**Architecture:** Nuovo modulo `ai_curation.py` che assorbe gli helper riusabili di `ai_agent.py` e implementa 4 chiamate LLM indipendenti (intento, mood a lotti, anchor, narrativa), ognuna degradabile: qualsiasi fallimento AI produce un warning, mai un errore. Il motore (`set_generator`/`set_skeleton`) guadagna due input opzionali (mood_scores, anchor_hints) come kwargs semplici — nessun import inverso. `ai_agent.py`, `validation.py` e i loro schemi/test vengono eliminati. Persistenza: due colonne JSON auto-migrate (`Setlist.curation`, `SetlistTrack.mood_tags`).

**Tech Stack:** Python 3.12/FastAPI/SQLAlchemy/Pydantic, SDK Anthropic (structured outputs, già incapsulato in `integrations/llm.py`), Next.js 16/React 19/TS, Vitest.

## Global Constraints

- Spec di riferimento: `docs/superpowers/specs/2026-07-19-set-builder-two-phase-ai-curation-design.md`, sezione "Tappa 2". Decisione già presa dall'utente: il percorso AI-ordina si ritira DEL TUTTO (niente opzione nascosta).
- Cap: pool AI ≤ **200** (`POOL_CAP`), campionamento stratificato esistente; ogni chiamata LLM vede ≤ **60** candidate (`PER_CALL_CAP`); lotti mood da **50** (`MOOD_BATCH_SIZE`).
- Merge dell'intento: i campi compilati dall'AI NON sovrascrivono mai i campi impostati esplicitamente dall'utente — discriminante: `req.model_fields_set` (Pydantic).
- Ogni output AI è validato: id fuori pool scartati in silenzio con warning aggregato, score clampati dal JSON Schema, valori fuori bounds scartati dalla ri-validazione Pydantic.
- Degradazione, mai errore: se una chiamata AI fallisce (`LLMError`) la pipeline continua senza quel contributo, con warning; se falliscono tutte, il set nasce comunque (deterministico puro) con `generated_by="algorithmic"`.
- `generated_by` dei nuovi set curati: `"algorithmic+ai_curation"`. I setlist storici con `"ai"` restano leggibili (nessuna migrazione dati).
- Semantica `use_ai` invariata: `true` = curatela, `false` = puro, `None` = auto (AI configurata + prompt presente).
- Determinismo del motore invariato; l'AI influenza solo tramite mood_scores/anchor_hints/vincoli compilati.
- Commenti in italiano; comandi backend `cd backend && source .venv/bin/activate`; frontend `cd frontend && npm run lint && npm run build && npm run test:unit`. Commit in italiano, MAI Co-Authored-By.
- Suite backend completa verde a ogni commit; frontend lint+build+unit verdi nel task frontend.
- Frontend: leggere `frontend/CLAUDE.md` prima di toccare pagine (Next 16: breaking changes, `use(params)`, Suspense per `useSearchParams`); i18n = dizionari TS in `lib/i18n/it.ts` + `en.ts`, ogni chiave va in ENTRAMBI (il tipo `Dictionary` deriva da en.ts).

---

### Task 1: Persistenza e contratto API (curation + mood_tags)

**Files:**
- Modify: `backend/app/models.py` (Setlist ~riga 165, SetlistTrack ~riga 187)
- Modify: `backend/app/schemas.py` (SetlistTrackOut ~riga 154, SetlistOut ~riga 170)
- Modify: `backend/app/serializers.py` (`setlist_out`, righe 59-100)
- Test: `backend/tests/test_curation_columns.py` (create)

**Interfaces:**
- Produces: `Setlist.curation: dict` (default {}), `SetlistTrack.mood_tags: list | None`; `SetlistOut.curation: dict = {}`, `SetlistTrackOut.mood_tags: list[str] = []`. La colonna nuova su tabella esistente è auto-aggiunta da `_migrate_add_model_columns` in `ensure_schema` (nessun codice di migrazione da scrivere).

- [ ] **Step 1: Test che falliscono** (`backend/tests/test_curation_columns.py`):

```python
"""Colonne di curatela AI: Setlist.curation e SetlistTrack.mood_tags."""

from sqlalchemy import inspect

from app.models import Setlist, SetlistTrack, Track
from app.serializers import setlist_out


def test_new_columns_exist_after_ensure_schema(db):
    cols_setlists = {c["name"] for c in inspect(db.get_bind()).get_columns("setlists")}
    cols_tracks = {c["name"] for c in inspect(db.get_bind()).get_columns("setlist_tracks")}
    assert "curation" in cols_setlists
    assert "mood_tags" in cols_tracks


def test_serializer_exposes_curation_and_mood_tags(db):
    t = Track(source_type="spotify", title="T", artist="A", duration_seconds=200,
              bpm=126.0, camelot_key="8A")
    db.add(t)
    db.flush()
    sl = Setlist(name="S", curation={"intent_summary": "warm-up malinconico"})
    sl.tracks.append(SetlistTrack(track_id=t.id, position=1, mood_tags=["malinconico", "deep"]))
    db.add(sl)
    db.commit()
    db.refresh(sl)
    out = setlist_out(sl)
    assert out.curation == {"intent_summary": "warm-up malinconico"}
    assert out.tracks[0].mood_tags == ["malinconico", "deep"]


def test_serializer_defaults_for_legacy_sets(db):
    sl = Setlist(name="Vecchio")
    db.add(sl)
    db.commit()
    db.refresh(sl)
    out = setlist_out(sl)
    assert out.curation == {}
    assert out.tracks == []
```

- [ ] **Step 2: Verifica FAIL** — `python -m pytest tests/test_curation_columns.py -v` → FAIL (`curation` assente / TypeError su kwarg).

- [ ] **Step 3: Implementare.**

`models.py` — in `Setlist`, dopo la riga `validation`:

```python
    # Curatela AI (tappa 2): intento compilato ("come ti ho capito"), warning
    # delle chiamate AI. {} = set non curato.
    curation: Mapped[dict] = mapped_column(JSON, default=dict)
```

In `SetlistTrack`, dopo `risk_level`:

```python
    # Tag di mood assegnati dalla curatela AI alla generazione (None = non curato).
    mood_tags: Mapped[list | None] = mapped_column(JSON)
```

`schemas.py` — `SetlistTrackOut`: aggiungere `mood_tags: list[str] = []`; `SetlistOut`: aggiungere `curation: dict = {}` (sotto `validation`).

`serializers.py` — in `setlist_out`: nel costruttore di `SetlistTrackOut` aggiungere `mood_tags=st.mood_tags or []`; in quello di `SetlistOut` aggiungere `curation=setlist.curation or {}`.

- [ ] **Step 4: Verifica PASS + suite completa** — `python -m pytest tests/test_curation_columns.py tests -q` → tutti PASS.

- [ ] **Step 5: Commit** — `feat(set): colonne di curatela — Setlist.curation e mood_tags per traccia, esposti dal serializer`

---

### Task 2: Scaffold `ai_curation.py` — helper migrati e cap a 200

**Files:**
- Create: `backend/app/services/ai_curation.py`
- Modify: `backend/app/services/ai_agent.py` (importa gli helper dal nuovo modulo, cancella i duplicati)
- Modify: `backend/tests/test_ai_candidate_ranking.py` (import + cap parametrico)

**Interfaces:**
- Produces (in `ai_curation`): `POOL_CAP = 200`, `PER_CALL_CAP = 60`, `MOOD_BATCH_SIZE = 50`, `CORRIDOR_BANDS = 6`; `_rank_candidates(candidates, req, budget: int = POOL_CAP) -> list[Track]` (identica alla versione di ai_agent ma con budget parametrico: ogni occorrenza di `MAX_CANDIDATES` diventa `budget`); `_candidate_payload(t) -> dict`; `_compute_candidate_profile(candidates) -> dict`; `_safe_library_context(db) -> dict`. Tutte spostate VERBATIM (solo il parametro budget in più).
- `ai_agent.py` resta funzionante fino al Task 8: rimuove le copie locali e importa `from app.services.ai_curation import _candidate_payload, _compute_candidate_profile, _rank_candidates, _safe_library_context`, chiamando `_rank_candidates(candidates, req, budget=MAX_CANDIDATES)` (il suo `MAX_CANDIDATES = 60` resta lì finché il file vive).

- [ ] **Step 1: Test** — aggiornare `tests/test_ai_candidate_ranking.py`: l'import diventa `from app.services.ai_curation import POOL_CAP, _rank_candidates`; nei test esistenti ogni `MAX_CANDIDATES` diventa una chiamata esplicita `_rank_candidates(cands, _req(), budget=60)` con `60` al posto della costante (il comportamento a budget 60 resta il contratto testato). Aggiungere in coda:

```python
def test_default_budget_is_pool_cap_200():
    cands = [_mk(i, 100.0 + i * 0.5) for i in range(300)]
    ranked = _rank_candidates(cands, _req())
    assert len(ranked) == POOL_CAP == 200


def test_small_pool_passes_through_untruncated():
    cands = [_mk(i, 120.0 + i) for i in range(40)]
    assert len(_rank_candidates(cands, _req())) == 40
```

- [ ] **Step 2: Verifica FAIL** — `python -m pytest tests/test_ai_candidate_ranking.py -v` → ImportError.

- [ ] **Step 3: Implementare.** Creare `ai_curation.py` con docstring di modulo:

```python
"""Curatela AI del Set Builder (tappa 2).

L'AI legge, non scrive la scaletta: compila l'intento dal prompt libero,
giudica il mood-fit delle candidate a lotti, suggerisce anchor e narra il set
costruito. Il sequencing resta SEMPRE del motore deterministico
(set_generator/set_skeleton). Ogni chiamata LLM degrada con un warning, mai
con un errore. Regola: pool <= POOL_CAP, ogni chiamata vede <= PER_CALL_CAP.
"""
```

quindi spostare le quattro funzioni da `ai_agent.py` (righe 140-251 e 338-345) cambiando SOLO `MAX_CANDIDATES` → parametro `budget` in `_rank_candidates(candidates, req, budget: int = POOL_CAP)`. Import necessari: `Counter`, `Session`, `Track`, `SetGenerationRequest`, `library_stats`. In `ai_agent.py` sostituire le definizioni con l'import e la chiamata `_rank_candidates(candidates, req, budget=MAX_CANDIDATES)`.

- [ ] **Step 4: Verifica PASS + suite completa** (`test_ai_agent.py` deve restare verde: percorso vecchio intatto).

- [ ] **Step 5: Commit** — `refactor(set): helper AI in ai_curation con pool a 200 — ai_agent li importa a budget 60`

---

### Task 3: `compile_intent` — dal prompt libero ai vincoli, l'utente vince

**Files:**
- Modify: `backend/app/services/ai_curation.py`
- Test: `backend/tests/test_ai_curation.py` (create)

**Interfaces:**
- Produces: `INTENT_SCHEMA` (JSON Schema, additionalProperties:false), `compile_intent(llm, req: SetGenerationRequest, lang: str) -> tuple[SetGenerationRequest, dict, list[str]]` → (request effettiva, `compiled` dict con `intent_summary` + i soli campi applicati, warnings). Se `req.prompt` è vuoto: ritorna `(req, {}, [])` senza chiamare l'LLM.

- [ ] **Step 1: Test** (`tests/test_ai_curation.py`, nuovo file):

```python
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
```

- [ ] **Step 2: Verifica FAIL** — ImportError su `compile_intent`.

- [ ] **Step 3: Implementare** in `ai_curation.py`:

```python
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
```

Import da aggiungere in testa: `import logging`, `from app.integrations.llm import LLMError`, `logger = logging.getLogger(__name__)`.

Nota per l'esecutore: `model_validate({**req.model_dump(), ...})` produce una request il cui `model_fields_set` contiene tutti i campi — va bene, perché `compile_intent` è chiamata una sola volta, prima di ogni altro uso.

- [ ] **Step 4: Verifica PASS + suite.**
- [ ] **Step 5: Commit** — `feat(set): compile_intent — il prompt libero diventa vincoli, i campi dell'utente vincono sempre`

---

### Task 4: `score_mood_fit` — giudizio per traccia, a lotti

**Files:**
- Modify: `backend/app/services/ai_curation.py`
- Test: `backend/tests/test_ai_curation.py` (append)

**Interfaces:**
- Produces: `MOOD_SCHEMA`, `score_mood_fit(llm, req, candidates: list[Track], lang) -> tuple[dict[int, int], dict[int, list[str]], list[str]]` → (mood_scores id→0-100, mood_tags id→list[str] max 3, warnings). Lotti da `MOOD_BATCH_SIZE=50`; id fuori lotto scartati (1 warning aggregato); candidate senza giudizio → score 50, niente tag; lotto fallito → warning e si continua col successivo.

- [ ] **Step 1: Test** (append; estendere import con `score_mood_fit`, `from app.models import Track`):

```python
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
```

- [ ] **Step 2: Verifica FAIL.**
- [ ] **Step 3: Implementare:**

```python
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
```

- [ ] **Step 4: Verifica PASS + suite.**
- [ ] **Step 5: Commit** — `feat(set): score_mood_fit — giudizio di mood per candidata a lotti, neutro dove l'AI tace`

---

### Task 5: `suggest_anchors` — rosa motivata, mai vincolante

**Files:**
- Modify: `backend/app/services/ai_curation.py`
- Test: `backend/tests/test_ai_curation.py` (append)

**Interfaces:**
- Produces: `ANCHOR_SCHEMA`, `suggest_anchors(llm, req, candidates, mood_scores, lang) -> tuple[dict[str, list[int]], list[str]]` → ({"opening": [...], "peak": [...], "closing": [...]} con id validati, warnings). La chiamata vede le top `PER_CALL_CAP` candidate per mood (tie-break id).

- [ ] **Step 1: Test** (append; estendere import con `suggest_anchors`):

```python
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
```

- [ ] **Step 2: Verifica FAIL.**
- [ ] **Step 3: Implementare:**

```python
ANCHOR_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "opening": {"type": "array", "items": {"type": "integer"}, "maxItems": 3},
        "peak": {"type": "array", "items": {"type": "integer"}, "maxItems": 3},
        "closing": {"type": "array", "items": {"type": "integer"}, "maxItems": 3},
        "reason": {"type": "string"},
    },
    "required": ["opening", "peak", "closing", "reason"],
}

ANCHOR_SYSTEM = """Sei un DJ esperto. Ricevi l'intento del set e le candidate migliori
per mood. Proponi fino a 3 track_id per ciascun ruolo: opening (come deve
iniziare), peak (il momento piu' alto), closing (come deve finire). Sono
SUGGERIMENTI per un motore deterministico che elegge gli anchor con criteri
tecnici: scegli per carattere musicale, non per BPM/tonalita'. Usa solo i
track_id forniti. reason: una frase sull'arco che immagini."""

_WARN_ANCHORS = {
    "it": "curatela AI: suggerimenti anchor non disponibili",
    "en": "AI curation: anchor suggestions unavailable",
}
_WARN_ANCHOR_FOREIGN = {
    "it": "curatela AI: suggerimenti anchor su tracce non candidate scartati",
    "en": "AI curation: anchor suggestions on non-candidate tracks discarded",
}


def suggest_anchors(llm, req: SetGenerationRequest, candidates: list[Track],
                    mood_scores: dict[int, int], lang: str,
                    ) -> tuple[dict[str, list[int]], list[str]]:
    """Rosa di anchor suggeriti dall'AI (bonus in elezione, mai un vincolo)."""
    top = sorted(candidates, key=lambda t: (-mood_scores.get(t.id, 50), t.id))[:PER_CALL_CAP]
    payload = {
        "user_prompt": req.prompt or "",
        "constraints": {"strategy": req.strategy, "genres": req.genres},
        "candidate_tracks": [_candidate_payload(t) for t in top],
    }
    try:
        raw = llm.complete_json(ANCHOR_SYSTEM, payload, ANCHOR_SCHEMA)
    except LLMError:
        logger.warning("suggest_anchors fallita", exc_info=True)
        return {}, [_WARN_ANCHORS[lang]]
    sent_ids = {t.id for t in top}
    hints: dict[str, list[int]] = {}
    foreign = False
    for role in ("opening", "peak", "closing"):
        ids = [i for i in raw.get(role, []) if i in sent_ids]
        if len(ids) != len(raw.get(role, [])):
            foreign = True
        if ids:
            hints[role] = ids
    return hints, ([_WARN_ANCHOR_FOREIGN[lang]] if foreign else [])
```

- [ ] **Step 4: Verifica PASS + suite.**
- [ ] **Step 5: Commit** — `feat(set): suggest_anchors — rosa AI per apertura/peak/chiusura, id validati`

---

### Task 6: Il motore ascolta la curatela (mood + anchor hints)

**Files:**
- Modify: `backend/app/services/set_generator.py` (`_candidate_score`, `_beam_search_span`, `generate_set`)
- Modify: `backend/app/services/set_skeleton.py` (`build_skeleton`, funzioni di elezione)
- Test: `backend/tests/test_two_phase_generator.py` (append), `backend/tests/test_set_skeleton.py` (append)

**Interfaces:**
- `_candidate_score(..., *, mood_scores: dict[int, int] | None = None, ...)`: nuovo termine `mood_scores.get(cand.id, 50) * _MOOD_WEIGHT` (costante `_MOOD_WEIGHT = 0.30`), attivo solo se `mood_scores is not None`.
- `_beam_search_span(..., mood_scores=None)`: passthrough a `_candidate_score`.
- `build_skeleton(..., mood_scores: dict[int, int] | None = None, anchor_hints: dict[str, list[int]] | None = None)`: nelle funzioni di elezione, termine mood `mood_scores.get(t.id, 50) * 0.2` (se presente) e bonus `_ANCHOR_HINT_BONUS = 12.0` se `t.id` è tra gli hint del ruolo in elezione (per i reset: nessun hint).
- `generate_set(db, req, *, mood_scores=None, anchor_hints=None) -> Setlist`: passthrough a `build_skeleton` e a tutti gli span (fallback compreso).

- [ ] **Step 1: Test.** In `test_two_phase_generator.py` (append):

```python
def test_mood_scores_shift_candidate_ranking():
    prev = make_track(id=1, bpm=126.0, camelot_key="8A")
    cand = make_track(id=2, bpm=126.0, camelot_key="8A")
    base = _score(prev, cand)
    assert _score(prev, cand, mood_scores={2: 100}) == pytest.approx(base + 100 * 0.30)
    assert _score(prev, cand, mood_scores={2: 0}) == pytest.approx(base)
    # id assente dal giudizio -> neutro 50
    assert _score(prev, cand, mood_scores={99: 100}) == pytest.approx(base + 50 * 0.30)
    assert _score(prev, cand, mood_scores=None) == base
```

In `test_set_skeleton.py` (append):

```python
def test_anchor_hint_bonus_tips_the_election():
    # Tre tracce di punta quasi gemelle (stesso BPM/energia, id diversi): senza
    # hint vince la 51 (tie-break sui percentili per id); l'hint AI sulla 50
    # vale +12, piu' del gap di impatto (~3.5 punti), e ribalta l'elezione.
    pool = _pool()
    twin_a = make_track(id=50, title="TA", artist="ZA", bpm=136.0, energy=90, genre="Techno")
    twin_b = make_track(id=51, title="TB", artist="ZB", bpm=136.0, energy=90, genre="Techno")
    req = SetGenerationRequest(target_duration_minutes=70)
    sk_plain = build_skeleton(pool + [twin_a, twin_b], req, strategy_profile("smooth"),
                              125.0, 125.0, 70 * 60)
    assert next(a for a in sk_plain.anchors if a.role == "peak").track.id == 51
    sk_hint = build_skeleton(pool + [twin_a, twin_b], req, strategy_profile("smooth"),
                             125.0, 125.0, 70 * 60, anchor_hints={"peak": [50]})
    assert next(a for a in sk_hint.anchors if a.role == "peak").track.id == 50


def test_mood_scores_influence_election():
    # Mood 100 sulla traccia 14 e 0 sulle due sopra di lei: il termine mood in
    # elezione (x0.2, max 20 punti) supera il gap di impatto verso la 16
    # (~0.6*100*(1.0-0.867) ~ 8 punti) e il peak va alla 14.
    pool = _pool()
    req = SetGenerationRequest(target_duration_minutes=70)
    mood = {16: 0, 15: 0, 14: 100, **{t.id: 50 for t in pool if t.id <= 13}}
    sk = build_skeleton(pool, req, strategy_profile("smooth"), 125.0, 125.0,
                        70 * 60, mood_scores=mood)
    assert next(a for a in sk.anchors if a.role == "peak").track.id == 14
```

- [ ] **Step 2: Verifica FAIL** (TypeError sui kwargs nuovi).
- [ ] **Step 3: Implementare.** In `set_generator.py`: costante `_MOOD_WEIGHT = 0.30` con commento; `_candidate_score` aggiunge il kwarg e, accanto agli altri termini nuovi:

```python
    # Mood-fit della curatela AI: giudizio semantico per traccia (50 = neutro).
    if mood_scores is not None:
        total += float(mood_scores.get(cand.id, 50)) * _MOOD_WEIGHT
```

`_beam_search_span` accetta `mood_scores=None` e lo passa a `_candidate_score`. `generate_set(db, req, *, mood_scores=None, anchor_hints=None)` passa entrambi a `build_skeleton` e `mood_scores` a ogni chiamata `_beam_search_span` (fallback incluso).

In `set_skeleton.py`: costante `_ANCHOR_HINT_BONUS = 12.0` e `_ELECTION_MOOD_WEIGHT = 0.2` (commenti tunabile); `build_skeleton(..., mood_scores=None, anchor_hints=None)`; helper interno:

```python
    def curation_terms(t: Track, role: str) -> float:
        s = 0.0
        if mood_scores is not None:
            s += mood_scores.get(t.id, 50) * _ELECTION_MOOD_WEIGHT
        if anchor_hints and t.id in anchor_hints.get(role, ()):  # i reset non hanno hint
            s += _ANCHOR_HINT_BONUS
        return s
```

sommato in `peak_score` (role "peak"), `opening_score` ("opening"), `closing_score` ("closing"); per `reset_score_at` solo il termine mood (`curation_terms(t, "reset")` va bene: nessun hint per quel ruolo).

- [ ] **Step 4: Verifica PASS + suite completa** (i default `None` garantiscono zero cambi al percorso non curato: gli score restano identici).
- [ ] **Step 5: Commit** — `feat(set): il motore ascolta la curatela — mood nel ranking, hint AI nell'elezione degli anchor`

---

### Task 7: `narrate` + pipeline `run_curated_generation`

**Files:**
- Modify: `backend/app/services/ai_curation.py`
- Test: `backend/tests/test_curated_generation.py` (create)

**Interfaces:**
- Produces: `NARRATIVE_SCHEMA`, `narrate(llm, setlist_payload, req, lang) -> tuple[dict, list[str]]`; `run_curated_generation(db, req, llm, on_phase=None) -> Setlist` — pipeline completa: candidate → `_rank_candidates` (POOL_CAP) → `compile_intent` → `score_mood_fit` → `suggest_anchors` → `generate_set(db, merged_req, mood_scores=…, anchor_hints=…)` → `narrate` → persistenza (curation, mood_tags, generated_by, validation, nome/spiegazione).
- Persistenza: `setlist.curation = {"intent_summary": …, "compiled": {campi applicati}, "warnings": [tutti i warning AI]}`; `setlist.validation = {"warnings": warnings_ai, "missing_library_suggestions": […]}`; `mood_tags` sui `SetlistTrack` delle tracce giudicate; `generated_by = "algorithmic+ai_curation"` se almeno una chiamata AI è andata a segno, altrimenti resta `"algorithmic"`.
- Fasi (per il job async): `_CURATION_PHASES` IT/EN: intento / mood / anchor / costruzione / narrativa.

- [ ] **Step 1: Test** (`tests/test_curated_generation.py`):

```python
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
```

- [ ] **Step 2: Verifica FAIL.**
- [ ] **Step 3: Implementare** in `ai_curation.py` (import aggiuntivi: `from app.services.app_state import get_language`, `from app.services.candidate_engine import select_candidates`, `from app.services.set_generator import SetGenerationError, generate_set`):

```python
NARRATIVE_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "set_title": {"type": "string"},
        "global_explanation": {"type": "string"},
        "missing_library_suggestions": {"type": "array", "items": {"type": "string"},
                                         "maxItems": 3},
    },
    "required": ["set_title", "global_explanation", "missing_library_suggestions"],
}

NARRATIVE_SYSTEM = """Sei un DJ esperto. Ricevi la scaletta DEFINITIVA di un set (gia'
costruita da un motore deterministico) e l'intento dell'utente. Scrivi:
set_title (breve, evocativo, senza virgolette), global_explanation (max 2 frasi
sul racconto del set; NON dichiarare compatibilita' armonica: la calcola il
sistema), missing_library_suggestions (0-3 consigli su che TIPO di traccia
aggiungere alla libreria; niente id, niente brani inventati).
Riferisciti ai brani per «artista – titolo», mai per id."""

_NARRATIVE_LANGUAGE = {
    "it": "Scrivi in italiano.",
    "en": "Write in English.",
}

_WARN_NARRATIVE = {
    "it": "curatela AI: narrativa non disponibile (titolo e spiegazione deterministici)",
    "en": "AI curation: narrative unavailable (deterministic title and explanation)",
}

_CURATION_PHASES = {
    "intent": {"it": "Interpreto la richiesta", "en": "Interpreting the request"},
    "mood": {"it": "Giudico il mood delle candidate", "en": "Judging candidate mood"},
    "anchors": {"it": "Cerco gli anchor del racconto", "en": "Looking for story anchors"},
    "building": {"it": "Costruisco il set", "en": "Building the set"},
    "narrating": {"it": "Racconto il set", "en": "Narrating the set"},
}


def narrate(llm, setlist_payload: list[dict], req: SetGenerationRequest, lang: str,
            ) -> tuple[dict, list[str]]:
    payload = {"user_prompt": req.prompt or "", "strategy": req.strategy,
               "tracks": setlist_payload}
    try:
        raw = llm.complete_json(NARRATIVE_SYSTEM + "\n" + _NARRATIVE_LANGUAGE[lang],
                                payload, NARRATIVE_SCHEMA)
    except LLMError:
        logger.warning("narrate fallita", exc_info=True)
        return {}, [_WARN_NARRATIVE[lang]]
    return raw, []


def run_curated_generation(db, req: SetGenerationRequest, llm, on_phase=None):
    """Pipeline tappa 2: l'AI compila/cura/narra, generate_set sequenzia.

    Ogni passo AI degrada con warning. generated_by testimonia se almeno un
    contributo AI e' arrivato al set.
    """
    lang = get_language(db)
    lang = lang if lang in ("it", "en") else "it"

    def phase(key: str) -> None:
        if on_phase:
            on_phase(_CURATION_PHASES[key][lang])

    warnings: list[str] = []
    phase("intent")
    merged, compiled, w = compile_intent(llm, req, lang)
    warnings += w

    candidates = select_candidates(db, merged)
    if len(candidates) < 3:
        # generate_set solleva l'errore giusto: inutile spendere chiamate AI
        return generate_set(db, merged)
    pool = _rank_candidates(candidates, merged)  # budget = POOL_CAP

    phase("mood")
    mood_scores, mood_tags, w = score_mood_fit(llm, merged, pool, lang)
    warnings += w
    # I tag esistono solo per i giudizi arrivati davvero (gli score si riempiono
    # comunque col neutro 50): sono la prova che almeno un lotto e' andato a segno.
    mood_useful = bool(mood_tags)

    phase("anchors")
    anchor_hints, w = suggest_anchors(llm, merged, pool, mood_scores, lang)
    warnings += w

    phase("building")
    setlist = generate_set(db, merged,
                           mood_scores=mood_scores if mood_useful else None,
                           anchor_hints=anchor_hints or None)

    phase("narrating")
    tracks_payload = [{"position": st.position, "artist": st.track.artist or "",
                       "title": st.track.title or "", "role": st.role or ""}
                      for st in setlist.tracks]
    narrative, w = narrate(llm, tracks_payload, merged, lang)
    warnings += w

    curated = bool(compiled or mood_useful or anchor_hints or narrative)
    if narrative:
        if not req.name and narrative.get("set_title"):
            setlist.name = narrative["set_title"]
        if narrative.get("global_explanation"):
            setlist.global_explanation = narrative["global_explanation"]
    setlist.generated_by = "algorithmic+ai_curation" if curated else "algorithmic"
    setlist.curation = {"intent_summary": compiled.get("intent_summary", ""),
                        "compiled": {k: v for k, v in compiled.items()
                                     if k != "intent_summary"},
                        "warnings": warnings}
    setlist.validation = {
        "warnings": warnings,
        "missing_library_suggestions": narrative.get("missing_library_suggestions", []) if narrative else [],
    }
    if mood_useful:
        for st in setlist.tracks:
            st.mood_tags = mood_tags.get(st.track_id) or None
    db.commit()
    db.refresh(setlist)
    logger.info("Set curato generato: %s tracce, %s warning AI, curated=%s",
                len(setlist.tracks), len(warnings), curated)
    return setlist
```

Nota: `mood_useful` usa la presenza di TAG (non di score) come prova che almeno un lotto è arrivato: gli score sono sempre popolati col neutro 50.

- [ ] **Step 4: Verifica PASS + suite.**
- [ ] **Step 5: Commit** — `feat(set): run_curated_generation — la pipeline dove l'AI legge e il motore sequenzia`

---

### Task 8: Rewiring del router e ritiro del percorso AI-ordina

**Files:**
- Modify: `backend/app/routers/sets.py` (`_run_generation`, `/generate`)
- Delete: `backend/app/services/ai_agent.py`, `backend/app/services/validation.py`, `backend/tests/test_ai_agent.py`
- Modify: `backend/app/schemas.py` (rimuovere `AITrackChoice`, `AISetResponse`)
- Test: `backend/tests/test_generate_async.py` (adeguare se importa dal vecchio percorso), suite completa

**Interfaces:**
- `sets.py`: `from app.services.ai_curation import run_curated_generation` sostituisce `from app.services.ai_agent import AIAgentError, generate_ai_set`. In `_run_generation`: il ramo `use_ai` chiama `run_curated_generation(db, req, get_llm_client(_model_for(req)), on_phase=…)`. Nel sync `/generate`: idem. La clausola `except` perde `AIAgentError` e guadagna `SetGenerationError` anche nel ramo AI (la pipeline può sollevarla per candidate insufficienti); `LLMNotConfigured` resta gestita (la factory del client può sollevarla).
- `_should_use_ai` INVARIATA (semantica confermata dalla spec).

- [ ] **Step 1: Grep di sicurezza.** `grep -rn "ai_agent\|validate_ai_set\|AISetResponse\|AITrackChoice\|generate_ai_set" backend/app backend/tests` — l'elenco atteso: `sets.py`, `schemas.py`, `ai_agent.py`, `validation.py`, `test_ai_agent.py`, `test_generate_async.py` (eventuale mock del percorso AI). Ogni occorrenza fuori lista va capita PRIMA di cancellare.

- [ ] **Step 2: Test.** Adeguare `test_generate_async.py`: dove mocka/percorre il ramo AI, sostituire il riferimento a `generate_ai_set` con `run_curated_generation` (stesso monkeypatch, nuova destinazione: il modulo importato in `app.routers.sets`). Aggiungere in `tests/test_curated_generation.py`:

```python
def test_router_uses_curated_pipeline(db, seed_tracks, monkeypatch):
    # Il ramo use_ai del router deve puntare alla pipeline curata (niente
    # TestClient: conftest non ha una fixture client, si chiama la funzione
    # del router direttamente col db della fixture).
    import app.routers.sets as sets_router
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
```

- [ ] **Step 3: Implementare** il rewiring di `sets.py` come da Interfaces; cancellare i tre file; rimuovere i due schemi. Controllare che `validation.py` non abbia altri consumatori (il grep dello Step 1 fa fede).

- [ ] **Step 4: Suite completa** — `python -m pytest tests -q` → verde (il conteggio scende: test_ai_agent.py rimosso).

- [ ] **Step 5: Commit** — `feat(set)!: ritirato il percorso "AI ordina la scaletta" — il router genera sempre col motore, la curatela e' l'unico ramo AI`

---

### Task 9: Frontend — toggle "Curatela AI", intento e mood nel workbench

**Files:**
- Modify: `frontend/app/set-builder/page.tsx` (sezione Motore, righe ~254-287; footer ~392-395)
- Modify: `frontend/app/sets/[id]/page.tsx` (badge ~287-289 e ~273; intento ~307; meta row tracce ~379-390)
- Modify: `frontend/lib/api/types.ts` (Setlist ~264, SetlistTrack ~241)
- Modify: `frontend/lib/i18n/it.ts` + `frontend/lib/i18n/en.ts` (blocchi `setBuilder` e `sets`)

**Interfaces:**
- Tipi: `SetlistTrack` guadagna `mood_tags: string[]`; `Setlist` guadagna `curation: { intent_summary?: string; compiled?: Record<string, unknown>; warnings?: string[] }`.
- Payload di generazione INVARIATO (`use_ai`, `mode`, `prompt`).
- PRIMA di toccare le pagine: leggere `frontend/CLAUDE.md` e rispettare i pattern esistenti (client components, `useT()`, `Badge` da `@/components/ui`).

- [ ] **Step 1: Tipi.** In `types.ts`: `mood_tags: string[];` in `SetlistTrack`; `curation: { intent_summary?: string; compiled?: Record<string, unknown>; warnings?: string[] };` in `Setlist`.

- [ ] **Step 2: i18n.** Nuove chiavi in ENTRAMBI i dizionari:
  - `setBuilder.curationOffLabel`: IT "Solo algoritmo" / EN "Algorithm only"
  - `setBuilder.curationOnLabel`: IT "Curatela AI" / EN "AI curation"
  - `setBuilder.curationOnDesc`: IT "L'AI interpreta il prompt e cura il pool; a sequenziare è sempre il motore" / EN "The AI interprets the prompt and curates the pool; sequencing is always the engine's"
  - `setBuilder.curationOffDesc`: IT "Motore deterministico sui soli dati tecnici" / EN "Deterministic engine on technical data only"
  - `sets.compiledIntentTitle`: IT "Come ti ho capito" / EN "How I understood you"
  - `sets.curatedBadge`: IT "AI curatela" / EN "AI curated"
  Le chiavi vecchie del toggle (`algorithmLabel`, `aiReasoningLabel`, `deterministicMixLabel`) vengono sostituite nei punti d'uso e RIMOSSE dai dizionari se non restano consumatori (grep).

- [ ] **Step 3: Set builder page.** Nella sezione Motore: i due bottoni usano `curationOffLabel`/`curationOnLabel` (il secondo mantiene icona Sparkles e `disabled={!aiReady}`); la descrizione a lato usa `curationOnDesc`/`curationOffDesc` (con `aiStatus.model` accanto quando attiva, come oggi). Footer: la voce engine usa le stesse due label nuove. Stato/payload invariati (`useAi`, `mode`, `prompt`).

- [ ] **Step 4: Workbench.** In `sets/[id]/page.tsx`:
  - Badge header e "Origine": condizione `setlist.generated_by.includes("ai")` → label `t.sets.curatedBadge` per i nuovi (`algorithmic+ai_curation`) e per gli storici `"ai"` va bene la stessa etichetta.
  - Sotto `global_explanation` (~riga 307): se `setlist.curation?.intent_summary`, un paragrafo con prefisso in grassetto `t.sets.compiledIntentTitle` + `: ` + summary (stile del paragrafo esistente).
  - Meta row della traccia (~379-390): dopo il badge `transition_class`, `{(st.mood_tags ?? []).map(tag => <Badge key={tag} tone="info">{tag}</Badge>)}`.

- [ ] **Step 5: Verifica** — `cd frontend && npm run lint && npm run build && npm run test:unit` → tutto verde.

- [ ] **Step 6: Commit** — `feat(set-ui): toggle Curatela AI, intento compilato e tag mood nel workbench`

---

### Task 10: Documentazione — regole, architettura, API, diario

**Files:**
- Modify: `CLAUDE.md` (regole 1 e 4)
- Modify: `docs/ARCHITECTURE.md`, `docs/API.md`, `docs/ROADMAP.md`, `PROGRESS.md`
- Modify: `docs/superpowers/specs/2026-07-19-set-builder-two-phase-ai-curation-design.md` (stato: implementata; allineare la nota sulla riserva small-pool alla formula reale `max(1, round(n*0.15))`)

**Interfaces:** solo testo; i numeri citati devono corrispondere alle costanti reali (POOL_CAP 200, PER_CALL_CAP 60, MOOD_BATCH_SIZE 50, pesi 0.30/0.2, bonus 12).

- [ ] **Step 1: CLAUDE.md.** Regola 4: "The AI never receives the whole library. It only receives candidates filtered by the Candidate Engine — pool cap 200, in per-call batches of at most 60." Regola 1: nella frase sull'AI, i compiti diventano "intent interpretation, pool curation (mood-fit, anchor hints), narrative and explanations — never sequencing".
- [ ] **Step 2: ARCHITECTURE.md.** Sezione Set Builder: pipeline aggiornata (Candidate Engine → [AI curation: intent/mood/anchors] → two-phase generator → narrative → Set Editor); rimozione del ramo AI-ordina e di `validate_ai_set`; degradazione a deterministico su fallimento AI; `generated_by` values. In inglese, "phase 2" non "Tappa".
- [ ] **Step 3: API.md.** `use_ai` semantica nuova; campi `curation` e `mood_tags` in SetlistOut; `generated_by: algorithmic | algorithmic+ai_curation` (storico: `ai`).
- [ ] **Step 4: ROADMAP.md + PROGRESS.md.** Phase 2 completata (2026-07-19) con rimando alla spec; voce diario in testa a PROGRESS (moduli, perché, come riprendere: tuning pesi/`lru_cache` su `genre_families_of`/percentili con tie medi come possibili follow-up).
- [ ] **Step 5: Verifica finale completa** — suite backend + `npm run lint && npm run build` frontend.
- [ ] **Step 6: Commit** — `docs(set): la curatela AI documentata — regole, architettura, API e diario allineati alla tappa 2`
