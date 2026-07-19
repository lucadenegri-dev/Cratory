# Set Builder a due fasi (Tappa 1) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Il generatore deterministico pianifica prima uno scheletro (anchor di apertura/peak/chiusura/reset, riserva delle bombe, piano di genere) e poi riempie i segmenti col beam search esistente, con convergenza verso l'anchor in arrivo.

**Architecture:** Nuovo modulo `set_skeleton.py` (Fase 1: profili strategia + matematica degli archi + scheletro) da cui `set_generator.py` importa — mai il contrario. Il beam search viene generalizzato a "span" con budget in secondi e stato condiviso; lo scoring di coppia guadagna termini opzionali keyword-only (convergenza, piano di genere, penalità riserva) così le firme esistenti e i loro test restano validi. Se il set atteso è corto o il pool piccolo, `build_skeleton` ritorna `None` e il flusso resta quello attuale a fase singola.

**Tech Stack:** Python 3.12, FastAPI/SQLAlchemy/Pydantic, pytest. Nessuna dipendenza nuova, nessuna chiamata LLM.

## Global Constraints

- Spec di riferimento: `docs/superpowers/specs/2026-07-19-set-builder-two-phase-ai-curation-design.md` (sezione Tappa 1).
- Tutto deterministico: a parità di input, stesso output. Tie-break sempre espliciti (per `track.id`).
- Interfaccia esterna invariata: `SetGenerationRequest`, `POST /api/sets/generate-async`, shape di `Setlist` — nessun campo nuovo.
- Costanti nuove: nominate a livello di modulo, con commento "tunabile" e valore iniziale della spec (riserva 15%, penalità −25, pesi 0.35/0.20, soglie 80%/15%, fallback < 6 tracce attese o pool < 8).
- Commenti in italiano, stile del file ospite (razionale, non parafrasi del codice).
- Comandi test dal repo root: `cd backend && source .venv/bin/activate` una volta, poi `python -m pytest tests/<file> -v`.
- Commit frequenti, messaggi in italiano stile `feat(set): ...` / `refactor(set): ...`. NON aggiungere Co-Authored-By.
- La suite completa (`python -m pytest tests`) deve restare verde a ogni commit.

---

### Task 1: Estrarre il layer strategia/archi in `set_skeleton.py` (refactor puro)

Serve a evitare l'import circolare: lo scheletro ha bisogno di `StrategyProfile`, `_desired_bpm`, `_desired_energy`, `_trajectory_fit`; se vivessero in `set_generator`, `set_skeleton` non potrebbe importarli mentre `set_generator` importa `build_skeleton`. Direzione finale: `set_generator → set_skeleton → scoring/schemas`.

**Files:**
- Create: `backend/app/services/set_skeleton.py`
- Modify: `backend/app/services/set_generator.py` (rimozione dei blocchi spostati + re-import)

**Interfaces:**
- Produces: `set_skeleton.StrategyProfile`, `_DEFAULT_PROFILE`, `_STRATEGY_PROFILES`, `strategy_profile(strategy) -> StrategyProfile`, `_desired_bpm(start, end, progress, curve) -> float`, `_trajectory_fit(bpm, desired) -> float`, `_desired_energy(req, progress, profile=None) -> float | None` — identici byte per byte a oggi, solo spostati.
- `set_generator` re-esporta gli stessi nomi (i test esistenti importano `_DEFAULT_PROFILE` da lì).

- [ ] **Step 1: Creare `backend/app/services/set_skeleton.py`** con il codice spostato da `set_generator.py` (righe 45–84: `StrategyProfile`, `_DEFAULT_PROFILE`, `_STRATEGY_PROFILES`, `strategy_profile`; righe 143–167: `_desired_bpm`, `_trajectory_fit`, `_desired_energy`), invariato nel contenuto:

```python
"""Fase 1 del set generator: il layer di pianificazione.

Qui vivono il carattere delle strategie (StrategyProfile) e la matematica degli
archi BPM/energia; sopra ci si costruisce lo scheletro del set (anchor, riserva
delle bombe, piano di genere). Il beam search di set_generator (fase 2) riempie
i segmenti. Direzione delle dipendenze: set_generator importa da qui, mai il
contrario.
"""

import statistics
from dataclasses import dataclass

from app.models import Track
from app.schemas import SetGenerationRequest


@dataclass(frozen=True)
class StrategyProfile:
    ...  # docstring e campi ESATTAMENTE come in set_generator.py righe 45-67

# _DEFAULT_PROFILE, _STRATEGY_PROFILES, strategy_profile: righe 70-84 invariate
# _desired_bpm, _trajectory_fit, _desired_energy: righe 143-167 invariate
#   (in _desired_energy il type hint diventa `profile: StrategyProfile | None = None`
#    senza virgolette: qui la classe e' definita sopra)
```

(Copiare il codice reale dalle righe indicate, non riscriverlo. `import statistics` e `Track` servono ai task successivi ma includerli già ora è innocuo solo se usati — quindi in questo task importare SOLO ciò che serve: `dataclass`, `SetGenerationRequest`.)

- [ ] **Step 2: In `set_generator.py`** eliminare i blocchi spostati e aggiungere il re-import subito dopo gli import esistenti:

```python
from app.services.set_skeleton import (  # noqa: F401 - re-export per compat test
    _DEFAULT_PROFILE,
    _STRATEGY_PROFILES,
    StrategyProfile,
    _desired_bpm,
    _desired_energy,
    _trajectory_fit,
    strategy_profile,
)
```

- [ ] **Step 3: Verificare che nulla si sia rotto**

Run: `python -m pytest tests -q`
Expected: tutti PASS (stesso conteggio di prima del refactor).

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/set_skeleton.py backend/app/services/set_generator.py
git commit -m "refactor(set): estratto il layer strategia/archi in set_skeleton — prepara la fase di pianificazione"
```

---

### Task 2: Helper pubblico `genre_families_of` in scoring.py

**Files:**
- Modify: `backend/app/services/scoring.py` (dopo `_genre_families`, riga ~582)
- Test: `backend/tests/test_genre_coherence.py` (append)

**Interfaces:**
- Produces: `scoring.genre_families_of(genre: str | None) -> frozenset[str]` — famiglie note di un genere grezzo; vuoto per None/sconosciuto/umbrella.

- [ ] **Step 1: Scrivere il test che fallisce** (append a `test_genre_coherence.py`; aggiungere `genre_families_of` all'import da `app.services.scoring`):

```python
def test_genre_families_of_public_helper():
    # Lookup pubblico delle famiglie: serve al piano di genere dello scheletro.
    assert genre_families_of("Acid House") == frozenset({"techno", "house"})
    assert genre_families_of("Techno") == frozenset({"techno"})
    assert genre_families_of("Electronic") == frozenset()   # umbrella: nessuna famiglia
    assert genre_families_of("Weirdcore") == frozenset()    # fuori mappa
    assert genre_families_of(None) == frozenset()
    assert genre_families_of("  ") == frozenset()
```

- [ ] **Step 2: Verificare che fallisca**

Run: `python -m pytest tests/test_genre_coherence.py::test_genre_families_of_public_helper -v`
Expected: FAIL con `ImportError: cannot import name 'genre_families_of'`

- [ ] **Step 3: Implementare** in `scoring.py`, subito dopo `_genre_families`:

```python
def genre_families_of(genre: str | None) -> frozenset[str]:
    """Famiglie note di un genere grezzo (vuoto se assente/sconosciuto/umbrella).

    Lookup pubblico usato dallo scheletro del set per il piano di genere.
    """
    if not genre:
        return frozenset()
    norm = _norm_genre(genre)
    return _genre_families(norm) if norm else frozenset()
```

- [ ] **Step 4: Verificare che passi**

Run: `python -m pytest tests/test_genre_coherence.py -v`
Expected: tutti PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/scoring.py backend/tests/test_genre_coherence.py
git commit -m "feat(set): genre_families_of pubblico — lookup famiglie per il piano di genere"
```

---

### Task 3: Punteggio di impatto (`impact_scores`)

**Files:**
- Modify: `backend/app/services/set_skeleton.py`
- Test: `backend/tests/test_set_skeleton.py` (create)

**Interfaces:**
- Produces: `set_skeleton.impact_scores(candidates: list[Track]) -> dict[int, float]` — id → impatto 0–1 (0.7·percentile energia + 0.3·percentile BPM; solo BPM se l'energia manca).

- [ ] **Step 1: Creare `backend/tests/test_set_skeleton.py` col test che fallisce:**

```python
"""Fase 1 del set generator: scheletro (impatto, piano di genere, anchor)."""

from app.models import Track
from app.services.set_skeleton import impact_scores


def make_track(**kw) -> Track:
    kw.setdefault("source_type", "spotify")
    kw.setdefault("duration_seconds", 300)
    return Track(**kw)


# --- punteggio di impatto ------------------------------------------------------


def test_impact_ordering_follows_energy_then_bpm():
    lo = make_track(id=1, bpm=120.0, energy=30)
    mid = make_track(id=2, bpm=125.0, energy=60)
    hi = make_track(id=3, bpm=130.0, energy=95)
    imp = impact_scores([lo, mid, hi])
    assert imp[3] > imp[2] > imp[1]
    assert imp[3] == 1.0 and imp[1] == 0.0  # percentili estremi


def test_impact_without_energy_falls_back_to_bpm():
    # Nessuna traccia ha energia: conta solo il percentile BPM.
    a = make_track(id=1, bpm=120.0)
    b = make_track(id=2, bpm=128.0)
    c = make_track(id=3, bpm=140.0)
    imp = impact_scores([a, b, c])
    assert imp[3] > imp[2] > imp[1]


def test_impact_mixed_pool_track_without_energy_uses_bpm_only():
    with_e = make_track(id=1, bpm=120.0, energy=90)
    without_e = make_track(id=2, bpm=140.0)
    other = make_track(id=3, bpm=125.0, energy=50)
    imp = impact_scores([with_e, without_e, other])
    assert imp[2] == 1.0  # solo BPM per lei, ed e' il BPM piu' alto


def test_impact_single_track_is_neutral():
    only = make_track(id=1, bpm=128.0, energy=70)
    assert impact_scores([only]) == {1: 0.5}
```

- [ ] **Step 2: Verificare che fallisca**

Run: `python -m pytest tests/test_set_skeleton.py -v`
Expected: FAIL con `ImportError: cannot import name 'impact_scores'`

- [ ] **Step 3: Implementare** in `set_skeleton.py` (aggiungere `import statistics` se non già presente — servirà anche dopo — e `from app.models import Track`):

```python
# Impatto (0-1): quanto una traccia "spinge" rispetto al pool. Percentili
# rank-based, tie-break per id (determinismo). Pesi tunabili.
_IMPACT_ENERGY_SHARE = 0.7
_IMPACT_BPM_SHARE = 0.3


def _percentiles(values: dict[int, float]) -> dict[int, float]:
    """id -> percentile 0-1 sul pool (rank-based, tie-break deterministico per id)."""
    if not values:
        return {}
    if len(values) == 1:
        return {tid: 0.5 for tid in values}
    ordered = sorted(values.items(), key=lambda kv: (kv[1], kv[0]))
    top = len(ordered) - 1
    return {tid: idx / top for idx, (tid, _) in enumerate(ordered)}


def impact_scores(candidates: list[Track]) -> dict[int, float]:
    """Impatto 0-1 per candidata: energia (peso 0.7) + BPM (0.3), percentili sul pool.

    Se l'energia manca sulla traccia conta solo il percentile BPM: nessuna
    penalita' per le librerie non analizzate.
    """
    bpm_pct = _percentiles({t.id: float(t.bpm) for t in candidates if t.bpm})
    energy_pct = _percentiles(
        {t.id: float(t.energy) for t in candidates if t.energy is not None})
    out: dict[int, float] = {}
    for t in candidates:
        b = bpm_pct.get(t.id, 0.5)
        e = energy_pct.get(t.id)
        out[t.id] = _IMPACT_ENERGY_SHARE * e + _IMPACT_BPM_SHARE * b if e is not None else b
    return out
```

- [ ] **Step 4: Verificare che passi**

Run: `python -m pytest tests/test_set_skeleton.py -v`
Expected: PASS (4 test)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/set_skeleton.py backend/tests/test_set_skeleton.py
git commit -m "feat(set): punteggio di impatto per candidata — percentili energia+bpm sul pool"
```

---

### Task 4: Piano di genere (`plan_genre_families`)

**Files:**
- Modify: `backend/app/services/set_skeleton.py`
- Test: `backend/tests/test_set_skeleton.py` (append)

**Interfaces:**
- Consumes: `scoring.genre_families_of` (Task 2).
- Produces: `set_skeleton.GenrePlan` (frozen dataclass: `principal: str`, `calm: str`) e `plan_genre_families(candidates: list[Track]) -> GenrePlan | None`. `None` = piano degenerato (monogenere ≥80%, nessuna seconda famiglia ≥15%, o nessuna famiglia nota).

- [ ] **Step 1: Test che falliscono** (append; estendere l'import da `set_skeleton` con `plan_genre_families`):

```python
# --- piano di genere -----------------------------------------------------------


def test_plan_none_when_pool_is_dominated_by_one_family():
    pool = ([make_track(id=i, genre="Techno") for i in range(1, 10)]
            + [make_track(id=99, genre="House")])
    assert plan_genre_families(pool) is None  # 90% techno: degenera


def test_plan_none_without_a_second_qualified_family():
    # 75% techno (sotto l'80%) ma nessun'altra famiglia raggiunge il 15%.
    pool = ([make_track(id=i, genre="Techno") for i in range(1, 7)]
            + [make_track(id=7, genre="Weirdcore"), make_track(id=8)])
    assert plan_genre_families(pool) is None


def test_plan_picks_principal_by_count_and_calm_by_energy():
    pool = ([make_track(id=i, genre="Techno", energy=80) for i in range(1, 6)]
            + [make_track(id=10 + i, genre="House", energy=40) for i in range(3)]
            + [make_track(id=20 + i, genre="Ambient", energy=20) for i in range(2)])
    plan = plan_genre_families(pool)
    assert plan is not None
    assert plan.principal == "techno"   # famiglia piu' numerosa
    assert plan.calm == "chill"         # tra le qualificate, energia media piu' bassa


def test_plan_calm_falls_back_to_bpm_when_energy_missing():
    pool = ([make_track(id=i, genre="Techno", bpm=140.0) for i in range(1, 6)]
            + [make_track(id=10 + i, genre="House", bpm=124.0) for i in range(3)]
            + [make_track(id=20 + i, genre="Trance", bpm=138.0) for i in range(2)])
    plan = plan_genre_families(pool)
    assert plan is not None and plan.calm == "house"  # BPM medio piu' basso
```

- [ ] **Step 2: Verificare che falliscano**

Run: `python -m pytest tests/test_set_skeleton.py -v`
Expected: FAIL con `ImportError: cannot import name 'plan_genre_families'`

- [ ] **Step 3: Implementare** in `set_skeleton.py` (aggiungere `from app.services.scoring import genre_families_of` e `import statistics` in testa se mancano):

```python
# Piano di genere: soglie tunabili. Sopra DOMINANT il piano degenera (monogenere);
# una famiglia "conta" solo se copre almeno MIN_SHARE del pool.
_GENRE_DOMINANT_SHARE = 0.80
_GENRE_MIN_SHARE = 0.15


@dataclass(frozen=True)
class GenrePlan:
    """Famiglie assegnate ai segmenti: principal al peak, calm al resto."""
    principal: str
    calm: str


def plan_genre_families(candidates: list[Track]) -> GenrePlan | None:
    """Sceglie famiglia principale (peak) e famiglia calma (resto del set).

    Ritorna None quando il piano non ha senso: pool monogenere (>=80%), nessuna
    seconda famiglia con quota >=15%, o generi tutti ignoti. In quel caso il
    generatore si comporta esattamente come oggi.
    """
    by_family: dict[str, list[Track]] = {}
    for t in candidates:
        for fam in genre_families_of(t.genre):
            by_family.setdefault(fam, []).append(t)
    if not by_family:
        return None
    total = len(candidates)
    counts = {fam: len(ts) for fam, ts in by_family.items()}
    principal = max(counts, key=lambda f: (counts[f], f))
    if counts[principal] / total >= _GENRE_DOMINANT_SHARE:
        return None
    qualified = [f for f, c in counts.items()
                 if f != principal and c / total >= _GENRE_MIN_SHARE]
    if not qualified:
        return None

    def calm_key(fam: str) -> tuple:
        tracks = by_family[fam]
        energies = [t.energy for t in tracks if t.energy is not None]
        if energies:
            return (0, statistics.mean(energies), fam)
        bpms = [t.bpm for t in tracks if t.bpm]
        return (1, statistics.mean(bpms) if bpms else 999.0, fam)

    return GenrePlan(principal=principal, calm=min(qualified, key=calm_key))
```

- [ ] **Step 4: Verificare che passi**

Run: `python -m pytest tests/test_set_skeleton.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/set_skeleton.py backend/tests/test_set_skeleton.py
git commit -m "feat(set): piano di genere — famiglia principale al peak, famiglia calma al resto"
```

---

### Task 5: Elezione anchor e `build_skeleton`

**Files:**
- Modify: `backend/app/services/set_skeleton.py`
- Test: `backend/tests/test_set_skeleton.py` (append)

**Interfaces:**
- Consumes: `impact_scores`, `plan_genre_families`, `_desired_bpm`, `_desired_energy`, `_trajectory_fit`, `StrategyProfile`; `scoring.genre_families_of`.
- Produces (usate dal Task 8):
  - `Anchor` (frozen dataclass): `role: str` ("opening"|"peak"|"reset"|"closing"), `position: float`, `track: Track`
  - `Segment` (frozen dataclass): `end_anchor: Anchor`, `fill_until_secs: int` (secondi assoluti di set a cui fermare il riempimento, già al netto della durata dell'anchor), `family: str | None`
  - `Skeleton` (frozen dataclass): `anchors: list[Anchor]` (ordinati per posizione), `segments: list[Segment]` (len = anchors−1), `reserved_ids: frozenset[int]`, `peak_window: tuple[float, float] | None` (finestra di progress dove le bombe sono libere)
  - `build_skeleton(candidates: list[Track], req: SetGenerationRequest, profile: StrategyProfile, start_bpm: float, end_bpm: float, target_seconds: int) -> Skeleton | None` — `None` = fallback a fase singola.

- [ ] **Step 1: Test che falliscono** (append; estendere l'import con `build_skeleton, impact_scores` e `from app.schemas import SetGenerationRequest`, `from app.services.set_skeleton import strategy_profile`):

```python
# --- scheletro: anchor, riserva, segmenti --------------------------------------


def _pool(n: int = 16, genre: str = "Techno") -> list[Track]:
    """Pool sintetico: energie e BPM crescenti, artisti tutti diversi."""
    return [make_track(id=i, title=f"T{i}", artist=f"Art{i}",
                       bpm=120.0 + i, energy=10 + i * 5, genre=genre)
            for i in range(1, n + 1)]


def _build(pool, strategy: str = "smooth", minutes: int = 70, **req_kw):
    req = SetGenerationRequest(target_duration_minutes=minutes,
                               strategy=strategy, **req_kw)
    return build_skeleton(pool, req, strategy_profile(strategy),
                          start_bpm=125.0, end_bpm=125.0,
                          target_seconds=minutes * 60)


def test_skeleton_none_for_short_sets():
    # 20 min / ~300s a traccia = 4 tracce attese: sotto la soglia di 6.
    assert _build(_pool(), minutes=20) is None


def test_skeleton_none_for_tiny_pool():
    assert _build(_pool(n=7)) is None  # pool < 8


def test_skeleton_has_opening_peak_closing_in_order():
    sk = _build(_pool())
    roles = [a.role for a in sk.anchors]
    assert roles[0] == "opening" and roles[-1] == "closing" and "peak" in roles
    positions = [a.position for a in sk.anchors]
    assert positions == sorted(positions)
    assert len(sk.segments) == len(sk.anchors) - 1


def test_peak_anchor_is_top_impact_and_reserved():
    pool = _pool()
    sk = _build(pool)
    imp = impact_scores(pool)
    peak = next(a for a in sk.anchors if a.role == "peak")
    top3 = sorted(imp, key=lambda tid: (-imp[tid], tid))[:3]
    assert peak.track.id in top3
    assert peak.track.id in sk.reserved_ids
    # Riserva = top 15% del pool (16 -> 2 tracce), tie-break per id.
    assert sk.reserved_ids == frozenset(sorted(imp, key=lambda t: (-imp[t], t))[:2])


def test_anchors_are_distinct_and_respect_artist_cap():
    # Stesso artista su tutte le tracce + cap 1: lo scheletro non puo' eleggere
    # due anchor dello stesso artista, quindi degrada a None.
    pool = [make_track(id=i, artist="Solo", bpm=120.0 + i, energy=10 + i * 5,
                       genre="Techno") for i in range(1, 17)]
    assert _build(pool, max_tracks_per_artist=1) is None


def test_peak_position_for_descending_arc():
    # Strategia closing (arco 75->40): il momento piu' alto sta all'inizio.
    sk = _build(_pool(), strategy="closing")
    peak = next(a for a in sk.anchors if a.role == "peak")
    assert peak.position <= 0.3


def test_reset_anchors_come_from_strategy_points():
    # contrast ha reset_points (0.34, 0.67): il primo diventa anchor, il secondo
    # viene scartato perche' dista meno di _MIN_ANCHOR_GAP dal peak (0.7).
    sk = _build(_pool(), strategy="contrast")
    resets = [a for a in sk.anchors if a.role == "reset"]
    assert {round(a.position, 2) for a in resets} == {0.34}


def test_segment_families_follow_plan():
    pool = ([make_track(id=i, title=f"T{i}", artist=f"A{i}", bpm=130.0 + i % 5,
                        energy=60 + i, genre="Techno") for i in range(1, 9)]
            + [make_track(id=20 + i, title=f"H{i}", artist=f"B{i}", bpm=124.0 + i % 5,
                          energy=30 + i, genre="House") for i in range(1, 7)])
    sk = _build(pool)
    peak_segments = [s for s in sk.segments if s.end_anchor.role == "peak"]
    other_segments = [s for s in sk.segments if s.end_anchor.role != "peak"]
    assert all(s.family == "techno" for s in peak_segments)
    assert all(s.family == "house" for s in other_segments)


def test_segment_families_none_for_single_family_pool():
    sk = _build(_pool())  # tutto techno: piano degenerato
    assert all(s.family is None for s in sk.segments)
    assert sk.peak_window is not None
```

- [ ] **Step 2: Verificare che falliscano**

Run: `python -m pytest tests/test_set_skeleton.py -v`
Expected: FAIL con `ImportError: cannot import name 'build_skeleton'`

- [ ] **Step 3: Implementare** in `set_skeleton.py`:

```python
# Scheletro: soglie e pesi tunabili. Il fallback (None) riproduce il flusso attuale.
_MIN_POOL_FOR_SKELETON = 8      # sotto, l'elezione degli anchor affama il pool
_MIN_EXPECTED_TRACKS = 6        # set attesi corti: la struttura non ha spazio
_RESERVE_SHARE = 0.15           # quota del pool riservata al peak (le "bombe")
_PEAK_POSITION = 0.7            # arco piatto/ascendente (allineato ad assign_roles)
_PEAK_POSITION_DESCENDING = 0.2  # arco discendente (closing): l'apice sta presto
_PEAK_WINDOW = (0.15, 0.10)     # finestra (prima, dopo) attorno al peak per le bombe
_MIN_ANCHOR_GAP = 0.1           # reset troppo vicini a un altro anchor: scartati
_ANCHOR_SEED_BONUS = 15.0       # i seed valgono anche nell'elezione degli anchor
_PEAK_FAMILY_BONUS = 10.0


@dataclass(frozen=True)
class Anchor:
    role: str        # "opening" | "peak" | "reset" | "closing"
    position: float  # frazione 0-1 del set
    track: Track


@dataclass(frozen=True)
class Segment:
    """Tratto da riempire fino all'anchor di arrivo.

    fill_until_secs e' in secondi assoluti di set, gia' al netto della durata
    dell'anchor: il riempimento si ferma li' e l'anchor atterra sulla sua
    posizione nominale.
    """
    end_anchor: Anchor
    fill_until_secs: int
    family: str | None


@dataclass(frozen=True)
class Skeleton:
    anchors: list[Anchor]
    segments: list[Segment]
    reserved_ids: frozenset[int]
    peak_window: tuple[float, float] | None  # (da, a) in progress 0-1


def _arc_fit(value: float | None, desired: float | None) -> float:
    """Aderenza 0-100 a un target (energia): neutro 50 se manca uno dei due."""
    if desired is None or value is None:
        return 50.0
    return max(0.0, 100.0 - abs(float(value) - desired))


def _is_seed(track: Track, seeds: list[str]) -> bool:
    return bool(seeds and track.artist
                and any(s in track.artist.lower() for s in seeds))


def _peak_position(req: SetGenerationRequest, profile: StrategyProfile) -> float:
    """Apice del set: 0.7 di default, presto se l'arco di energia scende."""
    start = end = None
    if req.start_energy is not None or req.end_energy is not None:
        start = req.start_energy if req.start_energy is not None else req.end_energy
        end = req.end_energy if req.end_energy is not None else req.start_energy
    elif profile.energy_arc is not None:
        start, end = profile.energy_arc
    if start is not None and end is not None and end < start:
        return _PEAK_POSITION_DESCENDING
    return _PEAK_POSITION


def build_skeleton(
    candidates: list[Track], req: SetGenerationRequest, profile: StrategyProfile,
    start_bpm: float, end_bpm: float, target_seconds: int,
) -> Skeleton | None:
    """Fase 1: elegge gli anchor e prepara segmenti, riserva e piano di genere.

    Ritorna None (fallback alla fase singola attuale) quando la struttura non ha
    spazio: pool piccolo, set atteso corto, o pool troppo stretto per eleggere
    anchor distinti nel rispetto del limite per artista.
    """
    if len(candidates) < _MIN_POOL_FOR_SKELETON:
        return None
    durations = [t.duration_seconds for t in candidates if t.duration_seconds]
    median_duration = statistics.median(durations) if durations else 300
    if target_seconds / max(1, median_duration) < _MIN_EXPECTED_TRACKS:
        return None

    impacts = impact_scores(candidates)
    reserve_size = max(1, round(len(candidates) * _RESERVE_SHARE))
    reserved = frozenset(sorted(impacts, key=lambda t: (-impacts[t], t))[:reserve_size])
    plan = plan_genre_families(candidates)
    seeds = [s.lower() for s in req.seed_artists]

    peak_pos = _peak_position(req, profile)
    # Posizioni degli anchor: opening/closing fissi, peak dalla strategia, reset
    # dai reset_points (scartati se troppo vicini a un anchor gia' piazzato).
    slots: list[tuple[float, str]] = [(0.0, "opening"), (peak_pos, "peak"), (1.0, "closing")]
    for rp in profile.reset_points:
        if all(abs(rp - pos) >= _MIN_ANCHOR_GAP for pos, _ in slots):
            slots.append((rp, "reset"))
    slots.sort()

    taken: set[int] = set()
    artist_counts: dict[str, int] = {}

    def elect(score_fn, avoid: frozenset[int]) -> Track | None:
        pool = [t for t in candidates
                if t.id not in taken
                and (not t.artist
                     or artist_counts.get(t.artist.lower(), 0) < req.max_tracks_per_artist)]
        if not pool:
            return None
        preferred = [t for t in pool if t.id not in avoid]
        pool = preferred or pool
        winner = max(pool, key=lambda t: (score_fn(t), -t.id))
        taken.add(winner.id)
        if winner.artist:
            key = winner.artist.lower()
            artist_counts[key] = artist_counts.get(key, 0) + 1
        return winner

    def desired_at(pos: float) -> tuple[float, float | None]:
        return (_desired_bpm(start_bpm, end_bpm, pos, profile.bpm_curve),
                _desired_energy(req, pos, profile))

    def peak_score(t: Track) -> float:
        d_bpm, d_energy = desired_at(peak_pos)
        s = (impacts[t.id] * 100.0 * 0.6
             + _trajectory_fit(t.bpm, d_bpm) * 0.25
             + _arc_fit(t.energy, d_energy) * 0.15)
        if plan and plan.principal in genre_families_of(t.genre):
            s += _PEAK_FAMILY_BONUS
        return s + (_ANCHOR_SEED_BONUS if _is_seed(t, seeds) else 0.0)

    def opening_score(t: Track) -> float:
        _, d_energy = desired_at(0.0)
        s = -abs((t.bpm or start_bpm) - start_bpm) * 2.0 + _arc_fit(t.energy, d_energy) * 0.3
        return s + (100.0 if _is_seed(t, seeds) else 0.0)  # come _pick_first

    def closing_score(t: Track) -> float:
        _, d_energy = desired_at(1.0)
        s = -abs((t.bpm or end_bpm) - end_bpm) * 2.0 + _arc_fit(t.energy, d_energy) * 0.3
        return s + (_ANCHOR_SEED_BONUS if _is_seed(t, seeds) else 0.0)

    def reset_score_at(pos: float):
        d_bpm, _ = desired_at(pos)

        def score(t: Track) -> float:
            # Un reset e' uno stacco che respira: premia l'energia bassa.
            calm = 100.0 - float(t.energy) if t.energy is not None else 50.0
            return (calm * 0.5 + _trajectory_fit(t.bpm, d_bpm) * 0.2
                    + (_ANCHOR_SEED_BONUS if _is_seed(t, seeds) else 0.0))
        return score

    # Ordine di elezione: il peak per primo (criteri piu' esigenti), poi gli
    # estremi, poi i reset. Le bombe restano libere solo per il peak.
    elected: dict[float, Anchor] = {}
    peak_track = elect(peak_score, avoid=frozenset())
    if peak_track is None:
        return None
    elected[peak_pos] = Anchor("peak", peak_pos, peak_track)
    for pos, role in slots:
        if role == "peak":
            continue
        score_fn = {"opening": opening_score, "closing": closing_score}.get(role)
        track = elect(score_fn or reset_score_at(pos), avoid=reserved)
        if track is None:
            return None
        elected[pos] = Anchor(role, pos, track)

    anchors = [elected[pos] for pos, _ in slots]
    segments = []
    for prev, nxt in zip(anchors, anchors[1:]):
        fill_until = max(0, round(nxt.position * target_seconds)
                         - (nxt.track.duration_seconds or 0))
        family = None
        if plan is not None:
            family = plan.principal if nxt.role == "peak" else plan.calm
        segments.append(Segment(end_anchor=nxt, fill_until_secs=fill_until, family=family))

    window = (max(0.0, peak_pos - _PEAK_WINDOW[0]), min(1.0, peak_pos + _PEAK_WINDOW[1]))
    return Skeleton(anchors=anchors, segments=segments,
                    reserved_ids=reserved, peak_window=window)
```

Nota per l'esecutore: `_pool()` nel test usa artisti tutti diversi proprio perché il default `max_tracks_per_artist=2` non deve interferire; il test del cap usa artista unico e si aspetta `None` perché dopo la prima elezione il pool eleggibile si svuota.

- [ ] **Step 4: Verificare che passi**

Run: `python -m pytest tests/test_set_skeleton.py -v`
Expected: PASS (tutti)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/set_skeleton.py backend/tests/test_set_skeleton.py
git commit -m "feat(set): build_skeleton — anchor eletti per ruolo, riserva bombe, segmenti col piano di genere"
```

---

### Task 6: Termini nuovi in `_candidate_score` (convergenza, piano, riserva)

**Files:**
- Modify: `backend/app/services/set_generator.py`
- Test: `backend/tests/test_two_phase_generator.py` (create)

**Interfaces:**
- Consumes: `scoring.genre_families_of`, `scoring.score_transition`.
- Produces: `_candidate_score(..., *, converge_to: Track | None = None, converge_ramp: float = 0.0, plan_family: str | None = None, reserved_ids: frozenset[int] = frozenset(), peak_window: tuple[float, float] | None = None)` — la firma posizionale esistente resta identica (i test attuali continuano a chiamarla senza kwargs).

- [ ] **Step 1: Creare `backend/tests/test_two_phase_generator.py` coi test che falliscono:**

```python
"""Fase 2 del generatore: convergenza verso l'anchor, piano di genere, riserva."""

from app.models import Track
from app.schemas import SetGenerationRequest
from app.services.set_generator import _DEFAULT_PROFILE, _candidate_score


def make_track(**kw) -> Track:
    kw.setdefault("source_type", "spotify")
    kw.setdefault("duration_seconds", 300)
    return Track(**kw)


def _score(prev, cand, **kw) -> float:
    total, _ = _candidate_score(prev, cand, 126.0, SetGenerationRequest(), {},
                                _DEFAULT_PROFILE, 0.5, **kw)
    return total


def test_convergence_rewards_tracks_near_the_incoming_anchor():
    prev = make_track(id=1, bpm=124.0, camelot_key="8A")
    near = make_track(id=2, bpm=130.0, camelot_key="9A")
    far = make_track(id=3, bpm=118.0, camelot_key="3B")
    anchor = make_track(id=9, bpm=132.0, camelot_key="10A")
    gain_near = (_score(prev, near, converge_to=anchor, converge_ramp=1.0)
                 - _score(prev, near))
    gain_far = (_score(prev, far, converge_to=anchor, converge_ramp=1.0)
                - _score(prev, far))
    assert gain_near > gain_far > 0


def test_convergence_ramp_zero_changes_nothing():
    prev = make_track(id=1, bpm=124.0, camelot_key="8A")
    cand = make_track(id=2, bpm=130.0, camelot_key="9A")
    anchor = make_track(id=9, bpm=132.0, camelot_key="10A")
    assert _score(prev, cand, converge_to=anchor, converge_ramp=0.0) == _score(prev, cand)


def test_reserved_track_penalized_outside_peak_window():
    prev = make_track(id=1, bpm=126.0, camelot_key="8A")
    bomb = make_track(id=2, bpm=126.0, camelot_key="8A", energy=95)
    base = _score(prev, bomb)
    # progress=0.5, finestra (0.55, 0.8): fuori -> -25
    outside = _score(prev, bomb, reserved_ids=frozenset({2}), peak_window=(0.55, 0.8))
    assert outside == base - 25.0
    # finestra che copre 0.5: nessuna penalita'
    inside = _score(prev, bomb, reserved_ids=frozenset({2}), peak_window=(0.4, 0.8))
    assert inside == base


def test_plan_family_bonus_orders_match_over_unknown_over_mismatch():
    prev = make_track(id=1, bpm=126.0, camelot_key="8A", genre="Techno")
    match = make_track(id=2, bpm=126.0, camelot_key="8A", genre="Acid")
    unknown = make_track(id=3, bpm=126.0, camelot_key="8A", genre="Weirdcore")
    mismatch = make_track(id=4, bpm=126.0, camelot_key="8A", genre="Acid House")
    s_match = _score(prev, match, plan_family="techno")
    s_unknown = _score(prev, unknown, plan_family="techno")
    # "Acid House" appartiene a techno E house: il mismatch va testato con una
    # famiglia a cui la traccia NON appartiene affatto.
    s_mismatch = _score(prev, mismatch, plan_family="dnb")
    # Il confronto isola il termine di piano: stessi prev, chiavi e BPM.
    assert s_match - _score(prev, match) == pytest.approx(100.0 * 0.20)
    assert s_unknown - _score(prev, unknown) == pytest.approx(50.0 * 0.20)
    assert s_mismatch - _score(prev, mismatch) == 0.0
```

(In testa al file di test serve anche `import pytest`.)

- [ ] **Step 2: Verificare che falliscano**

Run: `python -m pytest tests/test_two_phase_generator.py -v`
Expected: FAIL con `TypeError: _candidate_score() got an unexpected keyword argument 'converge_to'`

- [ ] **Step 3: Implementare.** In `set_generator.py`: aggiungere `genre_families_of` all'import da `app.services.scoring`; nuove costanti sotto le esistenti (riga ~42):

```python
_CONVERGE_WEIGHT = 0.35   # attrazione verso l'anchor in arrivo (cresce col ramp)
_GENRE_PLAN_WEIGHT = 0.20  # aderenza alla famiglia assegnata al segmento
_RESERVE_PENALTY = 25.0   # bomba spesa fuori dalla finestra del peak
```

Firma e corpo di `_candidate_score` (aggiunte in coda al corpo, prima del `return`):

```python
def _candidate_score(
    prev: Track, cand: Track, desired_bpm: float, req: SetGenerationRequest,
    artist_counts: dict[str, int], profile: StrategyProfile, progress: float,
    desired_energy: float | None = None, *,
    converge_to: Track | None = None, converge_ramp: float = 0.0,
    plan_family: str | None = None, reserved_ids: frozenset[int] = frozenset(),
    peak_window: tuple[float, float] | None = None,
) -> tuple[float, TransitionScore]:
    ...  # corpo esistente invariato fino a prima del return, poi:

    # Convergenza verso l'anchor in arrivo: la vicinanza (misurata come una
    # transizione verso l'anchor) pesa sempre di piu' man mano che il segmento
    # si consuma, cosi' al peak ci si arriva preparati, non per caso.
    if converge_to is not None and converge_ramp > 0.0:
        total += (float(score_transition(cand, converge_to).score)
                  * _CONVERGE_WEIGHT * converge_ramp)
    # Piano di genere del segmento: appartenere alla famiglia assegnata premia,
    # genere ignoto resta neutro, famiglia diversa non guadagna nulla.
    if plan_family is not None:
        families = genre_families_of(cand.genre)
        fit = 100.0 if plan_family in families else (50.0 if not families else 0.0)
        total += fit * _GENRE_PLAN_WEIGHT * profile.genre_coherence
    # Riserva delle bombe: spenderle lontano dal peak costa.
    if cand.id in reserved_ids and not (
            peak_window and peak_window[0] <= progress <= peak_window[1]):
        total -= _RESERVE_PENALTY
    return total, ts
```

- [ ] **Step 4: Verificare che passi, insieme al resto**

Run: `python -m pytest tests/test_two_phase_generator.py tests/test_genre_coherence.py tests/test_set_builder_phase_c.py -v`
Expected: tutti PASS (le chiamate esistenti senza kwargs sono invariate)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/set_generator.py backend/tests/test_two_phase_generator.py
git commit -m "feat(set): scoring con convergenza all'anchor, piano di genere e penalita' riserva"
```

---

### Task 7: Beam search a span (`_beam_search_span`)

**Files:**
- Modify: `backend/app/services/set_generator.py`
- Test: `backend/tests/test_two_phase_generator.py` (append)

**Interfaces:**
- Produces: `_beam_search_span(opener: Track, candidates, req, profile, start_bpm, end_bpm, target_seconds, *, elapsed_secs: int, fill_until_secs: int, converge_to: Track | None = None, used: set[int] | None = None, artist_counts: dict[str, int] | None = None, plan_family: str | None = None, reserved_ids: frozenset[int] = frozenset(), peak_window: tuple[float, float] | None = None) -> list[tuple[Track, TransitionScore]]` — ritorna SOLO i filler (opener escluso); il primo filler ha `ts = score_transition(opener, filler)`. `elapsed_secs` include già la durata dell'opener. Si ferma quando i secondi cumulati raggiungono `fill_until_secs`.
- La vecchia `_beam_search` viene SOSTITUITA da questa (unico chiamante: `generate_set`, adeguato nello stesso task).

- [ ] **Step 1: Test che falliscono** (append a `test_two_phase_generator.py`; estendere gli import con `_beam_search_span` e `from app.services.set_skeleton import strategy_profile`):

```python
# --- beam search a span --------------------------------------------------------


def _span_pool(n: int = 10) -> list[Track]:
    return [make_track(id=i, title=f"T{i}", artist=f"Art{i}",
                       bpm=124.0 + i, energy=40 + i * 3, genre="Techno")
            for i in range(1, n + 1)]


def test_span_returns_only_fillers_within_budget():
    pool = _span_pool()
    opener = pool[0]
    fillers = _beam_search_span(
        opener, pool, SetGenerationRequest(), strategy_profile("smooth"),
        125.0, 125.0, 3600,
        elapsed_secs=300, fill_until_secs=1200)  # spazio per ~3 filler da 300s
    assert 0 < len(fillers) <= 3
    ids = [t.id for t, _ in fillers]
    assert opener.id not in ids
    assert fillers[0][1] is not None  # transizione opener -> primo filler
    assert 300 + sum(t.duration_seconds for t, _ in fillers) >= 1200


def test_span_excludes_used_and_respects_artist_counts():
    pool = _span_pool()
    opener = pool[0]
    fillers = _beam_search_span(
        opener, pool, SetGenerationRequest(max_tracks_per_artist=1),
        strategy_profile("smooth"), 125.0, 125.0, 3600,
        elapsed_secs=300, fill_until_secs=1500,
        used={pool[1].id, opener.id}, artist_counts={"art3": 1})
    ids = {t.id for t, _ in fillers}
    assert pool[1].id not in ids   # gia' usato (es. anchor futuro)
    assert pool[2].id not in ids   # artista "Art3" gia' al limite


def test_span_empty_when_budget_already_filled():
    pool = _span_pool()
    fillers = _beam_search_span(
        pool[0], pool, SetGenerationRequest(), strategy_profile("smooth"),
        125.0, 125.0, 3600, elapsed_secs=1200, fill_until_secs=1200)
    assert fillers == []
```

- [ ] **Step 2: Verificare che falliscano**

Run: `python -m pytest tests/test_two_phase_generator.py -v`
Expected: FAIL con `ImportError: cannot import name '_beam_search_span'`

- [ ] **Step 3: Implementare.** Sostituire `_beam_search` (righe ~303-368) con:

```python
def _beam_search_span(
    opener: Track, candidates: list[Track], req: SetGenerationRequest,
    profile: StrategyProfile, start_bpm: float, end_bpm: float,
    target_seconds: int, *, elapsed_secs: int, fill_until_secs: int,
    converge_to: Track | None = None,
    used: set[int] | None = None, artist_counts: dict[str, int] | None = None,
    plan_family: str | None = None, reserved_ids: frozenset[int] = frozenset(),
    peak_window: tuple[float, float] | None = None,
) -> list[tuple[Track, TransitionScore]]:
    """Riempe uno span di set col beam search; ritorna i soli filler (opener escluso).

    elapsed_secs include gia' l'opener; ci si ferma a fill_until_secs. Il progress
    passato allo scoring resta GLOBALE (secondi/target del set intero), cosi'
    archi, reset point e finestra del peak parlano la stessa scala. Il ramp di
    convergenza invece e' locale allo span: cresce da 0 a 1 verso l'anchor.
    """
    span_start = elapsed_secs
    span_len = max(1, fill_until_secs - span_start)
    base_used = set(used or ()) | {opener.id}
    base_arts = dict(artist_counts or {})

    def new_beam() -> dict:
        return {"chosen": [], "prev": opener, "used": set(base_used),
                "arts": dict(base_arts), "secs": elapsed_secs, "cum": 0.0,
                "done": elapsed_secs >= fill_until_secs}

    def expand(b: dict) -> list[dict]:
        progress = min(1.0, b["secs"] / target_seconds)
        ramp = min(1.0, (b["secs"] - span_start) / span_len)
        desired = _desired_bpm(start_bpm, end_bpm, progress, profile.bpm_curve)
        desired_energy = _desired_energy(req, progress, profile)
        eligible = [
            t for t in candidates
            if t.id not in b["used"]
            and (not t.artist or b["arts"].get(t.artist.lower(), 0) < req.max_tracks_per_artist)
        ]
        if not eligible:
            b["done"] = True
            return [b]
        scored = sorted(
            ((_candidate_score(b["prev"], t, desired, req, b["arts"], profile, progress,
                               desired_energy, converge_to=converge_to,
                               converge_ramp=ramp, plan_family=plan_family,
                               reserved_ids=reserved_ids, peak_window=peak_window), t)
             for t in eligible),
            key=lambda it: (it[0][0], it[1].id), reverse=True,
        )[:BEAM_EXPANSIONS]
        children = []
        for (sc, ts), t in scored:
            arts = dict(b["arts"])
            if t.artist:
                arts[t.artist.lower()] = arts.get(t.artist.lower(), 0) + 1
            secs = b["secs"] + (t.duration_seconds or 0)
            children.append({
                "chosen": b["chosen"] + [(t, ts)], "prev": t,
                "used": b["used"] | {t.id}, "arts": arts,
                "secs": secs, "cum": b["cum"] + sc,
                "done": secs >= fill_until_secs,
            })
        return children

    beams = [new_beam()]
    while any(not b["done"] for b in beams):
        expanded: list[dict] = []
        for b in beams:
            expanded.extend([b] if b["done"] else expand(b))
        expanded.sort(key=lambda b: (b["cum"], [t.id for t, _ in b["chosen"]]), reverse=True)
        beams = expanded[:BEAM_WIDTH]

    # Rete di sicurezza greedy, come prima: il percorso "sempre il migliore
    # localmente" resta in gara, il beam non puo' fare peggio.
    greedy = new_beam()
    while not greedy["done"]:
        greedy = expand(greedy)[0]

    complete = [b for b in beams if b["secs"] >= fill_until_secs] or beams
    complete.append(greedy)
    best = max(complete, key=lambda b: (b["cum"] / max(1, len(b["chosen"])),
                                        [t.id for t, _ in b["chosen"]]))
    return best["chosen"]
```

In `generate_set`, sostituire la riga `chosen = _beam_search(first, ...)` con:

```python
    chosen = [(first, None)] + _beam_search_span(
        first, candidates, req, profile, start_bpm, end_bpm, target_seconds,
        elapsed_secs=first.duration_seconds or 0, fill_until_secs=target_seconds)
```

- [ ] **Step 4: Verificare che passi, insieme alla suite completa**

Run: `python -m pytest tests -q`
Expected: tutti PASS (il comportamento a fase singola è equivalente: stesso scoring, stesso criterio di stop `secs >= target`)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/set_generator.py backend/tests/test_two_phase_generator.py
git commit -m "refactor(set): beam search a span — budget in secondi, stato condiviso, convergenza opzionale"
```

---

### Task 8: Orchestrazione a due fasi in `generate_set` + ruoli allineati al peak

**Files:**
- Modify: `backend/app/services/set_generator.py`
- Test: `backend/tests/test_two_phase_generator.py` (append)

**Interfaces:**
- Consumes: `set_skeleton.build_skeleton`, `Skeleton`, `_beam_search_span`, `score_transition`.
- Produces: `assign_roles(n: int, peak_at: int | None = None) -> list[str]` (default = comportamento attuale; `set_editor` e `ai_agent` non cambiano). `generate_set` invariato nella firma.

- [ ] **Step 1: Test che falliscono** (append; import aggiuntivi: `from app.models import Playlist`, `from app.repositories import add_track_to_playlist`, `from app.services.set_generator import assign_roles, generate_set`):

```python
# --- ruoli col peak esplicito --------------------------------------------------


def test_assign_roles_with_explicit_peak():
    roles = assign_roles(10, peak_at=3)
    assert roles[3] == "peak"
    assert roles.count("peak") == 1
    assert roles[0] == "intro" and roles[-1] == "closing"
    assert all(r == "release" for r in roles[4:-1])


def test_assign_roles_default_unchanged():
    assert assign_roles(10) == assign_roles(10, peak_at=None)
    assert assign_roles(10)[round(9 * 0.7)] == "peak"


def test_assign_roles_peak_clamped_for_tiny_sets():
    # Sotto le 4 tracce il peak esplicito viene ignorato (niente indici assurdi).
    assert assign_roles(3, peak_at=0) == assign_roles(3)


# --- generazione a due fasi (integrazione) -------------------------------------


def _seed_playlist(db, n: int = 16, minutes_each: int = 5):
    pl = Playlist(platform="spotify", name="PL2F")
    db.add(pl)
    db.flush()
    tracks = []
    for i in range(1, n + 1):
        t = Track(source_type="spotify", title=f"T{i}", artist=f"Art{i}",
                  duration_seconds=minutes_each * 60, bpm=120.0 + i,
                  camelot_key="8A", energy=10 + i * 5, genre="Techno",
                  has_local_file=True)
        db.add(t)
        db.flush()
        add_track_to_playlist(db, t, pl)
        tracks.append(t)
    db.commit()
    return pl, tracks


def test_two_phase_peak_lands_in_peak_zone(db):
    pl, tracks = _seed_playlist(db)
    setlist = generate_set(db, SetGenerationRequest(
        playlist_id=pl.id, target_duration_minutes=70, max_tracks_per_artist=1))
    ordered = sorted(setlist.tracks, key=lambda st: st.position)
    n = len(ordered)
    peak_positions = [i for i, st in enumerate(ordered) if st.role == "peak"]
    assert len(peak_positions) == 1
    assert 0.45 <= peak_positions[0] / (n - 1) <= 0.9
    # Il ruolo peak sta sulla traccia eletta dallo scheletro (top impatto).
    peak_track_id = ordered[peak_positions[0]].track_id
    top_impact_ids = {t.id for t in sorted(tracks, key=lambda t: -(t.energy or 0))[:3]}
    assert peak_track_id in top_impact_ids


def test_two_phase_bombs_stay_out_of_the_first_third(db):
    pl, tracks = _seed_playlist(db)
    setlist = generate_set(db, SetGenerationRequest(
        playlist_id=pl.id, target_duration_minutes=70, max_tracks_per_artist=1))
    ordered = sorted(setlist.tracks, key=lambda st: st.position)
    n = len(ordered)
    reserved = {t.id for t in sorted(tracks, key=lambda t: -(t.energy or 0))[:2]}
    early = {st.track_id for st in ordered[: max(1, n // 3)]}
    assert not (reserved & early), "bomba spesa nel primo terzo del set"


def test_short_sets_keep_single_phase_behavior(db):
    # 13 minuti / 5 a traccia = ~3 tracce attese: niente scheletro, nessun errore.
    pl, _ = _seed_playlist(db, n=10)
    setlist = generate_set(db, SetGenerationRequest(
        playlist_id=pl.id, target_duration_minutes=13, max_tracks_per_artist=1))
    ordered = sorted(setlist.tracks, key=lambda st: st.position)
    assert len(ordered) >= 3
    assert ordered[0].role == "intro" and ordered[-1].role == "closing"
```

- [ ] **Step 2: Verificare che falliscano**

Run: `python -m pytest tests/test_two_phase_generator.py -v`
Expected: FAIL — `TypeError: assign_roles() got an unexpected keyword argument 'peak_at'` e, per gli integration, peak/bombe non ancora pianificati (possibile fail sulle posizioni).

- [ ] **Step 3: Implementare.**

3a. `assign_roles` — nuova firma e clamp (il resto della funzione invariato, cambia solo il calcolo di `peak_at` interno):

```python
def assign_roles(n: int, peak_at: int | None = None) -> list[str]:
    """Assegna un ruolo a ciascuna posizione lungo l'arco del set (deterministico).

    peak_at (0-based) permette di allineare il ruolo "peak" all'anchor eletto
    dallo scheletro; None = posizionale come sempre (~70% del set). Sotto le 4
    tracce il peak esplicito viene ignorato: non c'e' spazio per la struttura.
    """
    if n <= 0:
        return []
    if n == 1:
        return ["intro"]
    roles: list[str] = []
    if peak_at is not None and n >= 4:
        peak_pos = min(max(peak_at, 1), n - 2)
    else:
        peak_pos = max(1, round((n - 1) * 0.7))
    for i in range(n):
        frac = i / (n - 1)
        if i == 0:
            roles.append("intro")
        elif i == n - 1:
            roles.append("closing")
        elif i == peak_pos:
            roles.append("peak")
        elif i > peak_pos:
            roles.append("release")
        elif frac < 0.25:
            roles.append("warmup")
        elif frac < 0.55:
            roles.append("groove")
        else:
            roles.append("transition")
    return roles
```

3b. `generate_set` — orchestrazione (sostituire il blocco `first = _pick_first(...)` / `chosen = ...`; import: aggiungere `build_skeleton` al re-import da `set_skeleton`):

```python
    skeleton = build_skeleton(candidates, req, profile, start_bpm, end_bpm, target_seconds)
    peak_at: int | None = None
    if skeleton is None:
        first = _pick_first(candidates, req, start_bpm)
        chosen = [(first, None)] + _beam_search_span(
            first, candidates, req, profile, start_bpm, end_bpm, target_seconds,
            elapsed_secs=first.duration_seconds or 0, fill_until_secs=target_seconds)
    else:
        # Fase 2: riempi i segmenti tra un anchor e il successivo. Gli anchor
        # contano da subito in used/artist_counts, cosi' i filler non li rubano
        # ne' sforano il limite per artista con un anchor futuro.
        opening = skeleton.anchors[0]
        chosen = [(opening.track, None)]
        used = {a.track.id for a in skeleton.anchors}
        arts: dict[str, int] = {}
        for a in skeleton.anchors:
            if a.track.artist:
                key = a.track.artist.lower()
                arts[key] = arts.get(key, 0) + 1
        secs = opening.track.duration_seconds or 0
        for seg in skeleton.segments:
            fillers = _beam_search_span(
                chosen[-1][0], candidates, req, profile, start_bpm, end_bpm,
                target_seconds, elapsed_secs=secs,
                fill_until_secs=seg.fill_until_secs,
                converge_to=seg.end_anchor.track, used=used, artist_counts=arts,
                plan_family=seg.family, reserved_ids=skeleton.reserved_ids,
                peak_window=skeleton.peak_window)
            for t, _ in fillers:
                used.add(t.id)
                if t.artist:
                    key = t.artist.lower()
                    arts[key] = arts.get(key, 0) + 1
                secs += t.duration_seconds or 0
            chosen.extend(fillers)
            anchor_track = seg.end_anchor.track
            chosen.append((anchor_track, score_transition(chosen[-1][0], anchor_track)))
            secs += anchor_track.duration_seconds or 0
        peak_ids = [a.track.id for a in skeleton.anchors if a.role == "peak"]
        if peak_ids:
            peak_at = next(i for i, (t, _) in enumerate(chosen) if t.id == peak_ids[0])
    total_seconds = sum((t.duration_seconds or 0) for t, _ in chosen)
```

e più sotto: `roles = assign_roles(len(chosen), peak_at=peak_at)`.

- [ ] **Step 4: Verificare che passi, con la suite completa**

Run: `python -m pytest tests -q`
Expected: tutti PASS. Attenzione ai test esistenti di `test_set_builder_phase_c.py` e `test_genre_coherence.py::test_generated_set_groups_genres`: usano set corti/pool piccoli, quindi cadono nel fallback a fase singola e devono restare identici. Se uno di questi cambia esito, NON adattare il test: capire quale soglia dello scheletro è scattata per sbaglio.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/set_generator.py backend/tests/test_two_phase_generator.py
git commit -m "feat(set): generazione a due fasi — scheletro con anchor, segmenti riempiti in convergenza, ruoli allineati al peak"
```

---

### Task 9: Documentazione e diario

**Files:**
- Modify: `docs/ARCHITECTURE.md` (sezione Set Builder / pipeline)
- Modify: `docs/ROADMAP.md` (stato: tappa 1 completata, tappa 2 prossima)
- Modify: `PROGRESS.md` (voce diario in testa, data 2026-07-19)

**Interfaces:** nessuna — solo testo.

- [ ] **Step 1: ARCHITECTURE.md** — nella sezione del Set Builder, sostituire la descrizione del generatore monolitico con il flusso a due fasi (3-6 righe): Fase 1 `set_skeleton.build_skeleton` (anchor opening/peak/closing/reset eletti deterministicamente, riserva delle bombe = top 15% d'impatto libera solo nella finestra del peak, piano di genere principal/calm con degenerazione a vuoto), Fase 2 beam search a span con convergenza verso l'anchor in arrivo; fallback a fase singola per set attesi < 6 tracce o pool < 8. Precisare che il percorso resta 100% deterministico e che la Tappa 2 (AI curatrice, spec `docs/superpowers/specs/2026-07-19-set-builder-two-phase-ai-curation-design.md`) non è ancora implementata.

- [ ] **Step 2: ROADMAP.md** — aggiungere sotto lo stato del Set Builder una voce: tappa 1 (generatore a due fasi) completata in data 2026-07-19 con rimando alla spec; tappa 2 (AI curatrice, ritiro del percorso AI-ordina) pianificata, con nota che `use_ai`/`generate_ai_set` restano invariati fino ad allora.

- [ ] **Step 3: PROGRESS.md** — voce diario: cosa è cambiato (moduli toccati: `set_skeleton.py` nuovo, `set_generator.py`, `scoring.py`), perché (struttura piatta / bombe sprecate / genere solo locale), come riprendere (tappa 2 nella spec).

- [ ] **Step 4: Verifica finale completa**

Run: `python -m pytest tests -q`
Expected: tutti PASS

- [ ] **Step 5: Commit**

```bash
git add docs/ARCHITECTURE.md docs/ROADMAP.md PROGRESS.md
git commit -m "docs(set): due fasi documentate — architettura, roadmap e diario allineati alla tappa 1"
```
