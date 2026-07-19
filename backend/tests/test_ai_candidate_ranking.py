"""Test del ranking candidate AI senza vincoli BPM (residuo A5).

Senza start/end_bpm dichiarati l'ancora del taglio al budget non deve
degenerare a 0 (che selezionava sempre le 60 tracce più lente della libreria),
ma rappresentare il profilo del pool (mediana BPM, deterministica).
Con start_bpm esplicito il comportamento resta invariato.

Il budget di taglio è parametrico (`_rank_candidates(..., budget=...)`); qui
si esercita esplicitamente il contratto storico a 60 (quello di ai_agent) e,
in coda, il nuovo default POOL_CAP=200 di ai_curation.
"""

from app.models import Track
from app.schemas import SetGenerationRequest
from app.services.ai_curation import POOL_CAP, _rank_candidates


def _mk(i, bpm, artist=None):
    t = Track(source_type="spotify", title=f"T{i}", artist=artist or f"Art{i}",
              duration_seconds=200, bpm=bpm, camelot_key="8A")
    t.id = i
    return t


def _req(**kw):
    return SetGenerationRequest(**kw)


def test_no_bpm_constraint_does_not_pick_only_the_slowest():
    # Pool 80..180 BPM (101 tracce), nessun vincolo BPM. Con l'ancora a 0 le
    # 60 scelte erano sempre le 60 più lente (80..139): niente sopra la
    # mediana del pool (130). Il campione deve rappresentare la libreria.
    cands = [_mk(i, 80.0 + i) for i in range(101)]
    ranked = _rank_candidates(cands, _req(), budget=60)
    assert len(ranked) == 60
    bpms = sorted(t.bpm for t in cands)
    median = bpms[len(bpms) // 2]  # 130
    # Non deve essere la coda lenta: il campione è centrato sulla mediana...
    slowest_ids = {t.id for t in sorted(cands, key=lambda t: t.bpm)[:60]}
    assert {t.id for t in ranked} != slowest_ids
    # ...quindi circa metà della selezione sta sopra la mediana del pool.
    assert sum(1 for t in ranked if t.bpm > median) >= 60 // 3


def test_start_bpm_only_keeps_anchoring_to_start():
    # Regressione: con start_bpm esplicito (senza end) l'ancora resta lo start
    # e il taglio è identico al comportamento precedente (vicinanza + id).
    cands = [_mk(i, 80.0 + i) for i in range(101)]
    ranked = _rank_candidates(cands, _req(start_bpm=100), budget=60)
    expected = sorted(cands, key=lambda t: (abs(t.bpm - 100), t.id))[:60]
    assert [t.id for t in ranked] == [t.id for t in expected]


def test_no_bpm_constraint_ranking_is_deterministic():
    # Stesso pool (anche in ordine diverso) -> stessa selezione, stesso ordine.
    cands = [_mk(i, 80.0 + i) for i in range(101)]
    a = _rank_candidates(list(cands), _req(), budget=60)
    b = _rank_candidates(list(reversed(cands)), _req(), budget=60)
    assert [t.id for t in a] == [t.id for t in b]


def test_no_bpm_constraint_tolerates_missing_bpm():
    # Pool senza alcun BPM: nessun crash, il taglio resta entro il budget.
    cands = [_mk(i, None) for i in range(70)]
    ranked = _rank_candidates(cands, _req(), budget=60)
    assert len(ranked) == 60


def test_default_budget_is_pool_cap_200():
    cands = [_mk(i, 100.0 + i * 0.5) for i in range(300)]
    ranked = _rank_candidates(cands, _req())
    assert len(ranked) == POOL_CAP == 200


def test_small_pool_passes_through_untruncated():
    cands = [_mk(i, 120.0 + i) for i in range(40)]
    assert len(_rank_candidates(cands, _req())) == 40
