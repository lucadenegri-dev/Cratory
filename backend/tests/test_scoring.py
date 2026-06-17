"""Test dello scoring tecnico transizioni e della compatibilita' Camelot."""

from app.models import Track
from app.services.camelot import camelot_compatibility, parse_camelot
from app.services.scoring import (
    bpm_compatibility_score,
    classify_transition,
    energy_progression_score,
    genre_similarity_score,
    key_compatibility_score,
    mood_coherence_score,
    score_transition,
)


def make_track(bpm=None, key=None, duration=300, energy=None, genre=None) -> Track:
    return Track(source_type="spotify", bpm=bpm, camelot_key=key, duration_seconds=duration,
                 energy=energy, genre=genre)


def test_parse_camelot():
    assert parse_camelot("7A") == (7, "A")
    assert parse_camelot("12b") == (12, "B")
    assert parse_camelot("13A") is None
    assert parse_camelot("") is None
    assert parse_camelot(None) is None
    assert parse_camelot("Cmaj") is None


def test_camelot_compatibility_levels():
    assert camelot_compatibility("7A", "7A")[0] == "same"
    assert camelot_compatibility("7A", "7B")[0] == "compatible"
    assert camelot_compatibility("7A", "8A")[0] == "compatible"
    assert camelot_compatibility("7A", "6A")[0] == "compatible"
    assert camelot_compatibility("12A", "1A")[0] == "compatible"  # wrap della ruota
    assert camelot_compatibility("7A", "10B")[0] == "weak"
    assert camelot_compatibility("7A", None)[0] == "unknown"


def test_bpm_tiers_ordering():
    base = make_track(bpm=130, key="7A")
    perfect = score_transition(base, make_track(bpm=131, key="7A")).score
    good = score_transition(base, make_track(bpm=134, key="7A")).score
    risky = score_transition(base, make_track(bpm=137, key="7A")).score
    hard = score_transition(base, make_track(bpm=145, key="7A")).score
    assert perfect > good > risky > hard


def test_bpm_jump_warning():
    ts = score_transition(make_track(bpm=130, key="7A"), make_track(bpm=145, key="7A"))
    assert any("BPM" in w for w in ts.warnings)


def test_key_compatibility_affects_score():
    base = make_track(bpm=130, key="7A")
    same = score_transition(base, make_track(bpm=130, key="7A")).score
    weak = score_transition(base, make_track(bpm=130, key="2B")).score
    assert same > weak


def test_short_track_penalized():
    base = make_track(bpm=130, key="7A")
    normal = score_transition(base, make_track(bpm=130, key="7A", duration=300)).score
    short = score_transition(base, make_track(bpm=130, key="7A", duration=40)).score
    assert normal > short
    ts = score_transition(base, make_track(bpm=130, key="7A", duration=40))
    assert any("corta" in w for w in ts.warnings)


def test_six_named_scores():
    # I sei score deterministici della spec (sez. 5): tutti 0-100, neutri sul dato mancante.
    assert bpm_compatibility_score(128, 128) == 100
    assert bpm_compatibility_score(128, 140) < bpm_compatibility_score(128, 130)
    assert bpm_compatibility_score(None, 128) == 50
    assert key_compatibility_score("7A", "7A") == 100
    assert key_compatibility_score("7A", "8A") > key_compatibility_score("7A", "2B")
    assert key_compatibility_score("7A", None) == 50
    assert energy_progression_score(50, 55) > energy_progression_score(50, 20)
    assert mood_coherence_score("dark", "dark") > mood_coherence_score("dark", "uplifting")
    assert genre_similarity_score("deep house", "deep house") > genre_similarity_score("house", "techno")


def test_score_in_range():
    ts = score_transition(make_track(bpm=130, key="7A"), make_track(bpm=131, key="7A"))
    assert 0 <= ts.score <= 100
    assert ts.technical_reasons


# --- F10: classificazione semantica della transizione ------------------------

def test_classify_technically_safe():
    # BPM e key compatibili -> score alto -> mix sicuro
    c = classify_transition(make_track(bpm=130, key="7A"), make_track(bpm=130, key="7A"))
    assert c.label == "technically_safe"


def test_classify_good_reset_on_energy_drop():
    # BPM/key incompatibili + forte calo di energia -> reset voluto
    a = make_track(bpm=130, key="7A", energy=80)
    b = make_track(bpm=145, key="2B", energy=40)  # salto BPM grosso + key debole + -40 energia
    c = classify_transition(a, b)
    assert c.label == "good_reset"
    assert "energia" in c.reason


def test_classify_good_reset_on_genre_change():
    a = make_track(bpm=130, key="7A", energy=70, genre="deep house")
    b = make_track(bpm=145, key="2B", energy=70, genre="drum and bass")  # generi diversi, energia stabile
    c = classify_transition(a, b)
    assert c.label == "good_reset"
    assert "genere" in c.reason


def test_classify_creative_risk():
    # Salto tecnico azzardato ma senza calo di energia né cambio di genere
    a = make_track(bpm=130, key="7A", energy=70, genre="techno")
    b = make_track(bpm=145, key="2B", energy=72, genre="techno")
    c = classify_transition(a, b)
    assert c.label == "creative_risk"
