"""Test dello scoring tecnico transizioni e della compatibilita' Camelot."""

from app.models import Track
from app.services.camelot import camelot_compatibility, parse_camelot
from app.services.scoring import (
    bpm_compatibility_score,
    classify_transition,
    energy_progression_score,
    genre_similarity_score,
    key_compatibility_score,
    mixing_tip,
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


# --- consiglio di mix deterministico (mixing_tip) ----------------------------


def test_mixing_tip_smooth_harmonic():
    a = make_track(bpm=128, key="8A", energy=60)
    b = make_track(bpm=129, key="9A", energy=66)  # +1 BPM, key adiacente
    tip = mixing_tip(a, b)
    assert "BPM" in tip
    assert "8A→9A compatibile" in tip
    assert "id" not in tip.lower().split()  # mai id numerici


def test_mixing_tip_same_key_and_bpm():
    a = make_track(bpm=130, key="5A")
    b = make_track(bpm=130, key="5A")
    tip = mixing_tip(a, b)
    assert "beatmatch diretto" in tip
    assert "stessa key" in tip


def test_mixing_tip_big_jump_and_energy_drop():
    a = make_track(bpm=130, key="7A", energy=80)
    b = make_track(bpm=145, key="2B", energy=50)  # +15 BPM, key debole, -30 energia
    tip = mixing_tip(a, b)
    assert "stacco netto" in tip or "cut" in tip
    assert "fuori chiave" in tip
    assert "reset" in tip


def test_mixing_tip_handles_missing_bpm():
    a = make_track(bpm=None, key=None)
    b = make_track(bpm=128, key="8A")
    tip = mixing_tip(a, b)
    assert "sincronizza a orecchio" in tip


def test_mixing_overview_summarizes_plan():
    from app.services.scoring import mixing_overview
    tracks = [
        make_track(bpm=120, key="8A", energy=40),
        make_track(bpm=121, key="9A", energy=50),   # +1 BPM, armonico
        make_track(bpm=138, key="2B", energy=80),   # +17 BPM (salto), fuori chiave
    ]
    out = mixing_overview(tracks)
    text = " ".join(out)
    assert any("Armonia" in b for b in out)
    assert "fuori chiave" in text          # 9A->2B debole
    assert "salto marcato al brano 3" in text  # il salto BPM è all'ingresso del brano 3
    assert "Energia in salita" in text


def test_mixing_overview_empty_for_single_track():
    from app.services.scoring import mixing_overview
    assert mixing_overview([make_track(bpm=120, key="8A")]) == []
