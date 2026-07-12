"""E10: niente doppio calcolo dello score nel router transizioni e soglie di
rischio unificate su scoring.risk_from_score (niente duplicati che divergono).
"""

from app.models import Track
from app.routers import transitions
from app.services import scoring
from app.services import set_generator


def make_track(bpm=None, key=None, duration=300, energy=None, genre=None) -> Track:
    return Track(source_type="spotify", bpm=bpm, camelot_key=key, duration_seconds=duration,
                 energy=energy, genre=genre)


def _count_score_calls(monkeypatch) -> dict:
    """Avvolge score_transition con un contatore, in TUTTI i namespace che lo
    referenziano direttamente (il router lo importa per nome)."""
    calls = {"n": 0}
    real = scoring.score_transition

    def counting(*args, **kwargs):
        calls["n"] += 1
        return real(*args, **kwargs)

    monkeypatch.setattr(scoring, "score_transition", counting)
    monkeypatch.setattr(transitions, "score_transition", counting)
    return calls


def test_score_out_computes_score_once(monkeypatch):
    """Il percorso router (_score_out) deve calcolare score_transition UNA volta
    per coppia: classify_transition riusa lo score gia' calcolato."""
    calls = _count_score_calls(monkeypatch)
    a = make_track(bpm=128, key="8A", energy=60, genre="techno")
    b = make_track(bpm=129, key="9A", energy=62, genre="techno")

    out = transitions._score_out(a, b, "it")

    assert calls["n"] == 1
    assert out.classification in {"technically_safe", "creative_risk", "good_reset"}


def test_classify_with_precomputed_score_equals_default():
    """Passare lo score precomputato non cambia la classificazione rispetto al
    calcolo interno (stesso label e stessa reason), per tutte le classi."""
    pairs = [
        (make_track(bpm=128, key="8A"), make_track(bpm=129, key="9A")),        # safe
        (make_track(bpm=128, key="8A"), make_track(bpm=150, key="3B")),        # creative_risk
        (make_track(bpm=128, key="8A", energy=80, genre="techno"),
         make_track(bpm=128, key="8A", energy=40, genre="ambient")),           # good_reset
    ]
    for a, b in pairs:
        precomputed = scoring.score_transition(a, b).score
        base = scoring.classify_transition(a, b)
        via_param = scoring.classify_transition(a, b, score=precomputed)
        assert via_param.label == base.label
        assert via_param.reason == base.reason


def test_generator_uses_risk_from_score():
    """Il set generator usa scoring.risk_from_score: nessuna soglia duplicata."""
    assert set_generator.risk_from_score is scoring.risk_from_score
    # Le soglie ai bordi restano quelle storiche del generator (70/45).
    assert scoring.risk_from_score(70) == "low"
    assert scoring.risk_from_score(69) == "medium"
    assert scoring.risk_from_score(45) == "medium"
    assert scoring.risk_from_score(44) == "high"
    assert scoring.risk_from_score(None) == "low"  # traccia di apertura
