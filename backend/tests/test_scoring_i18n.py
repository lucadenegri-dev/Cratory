"""Scoring bilingue (Task 13): `reason`/`mixing_tip`/`mixing_overview` parametrici
su `lang`, `TransitionClassification` senza `label_it` (la label enum la traduce
il frontend da `label`, il codice).
"""

from app.models import Track
from app.services.scoring import classify_transition, mixing_overview, mixing_tip


def make_track(bpm=None, key=None, duration=300, energy=None, genre=None) -> Track:
    return Track(source_type="spotify", bpm=bpm, camelot_key=key, duration_seconds=duration,
                 energy=energy, genre=genre)


def test_classify_transition_en():
    # coppia usata anche nei test IT esistenti di good_reset (calo di energia)
    a = make_track(bpm=130, key="7A", energy=80)
    b = make_track(bpm=145, key="2B", energy=40)
    cls_it = classify_transition(a, b)              # default "it"
    cls_en = classify_transition(a, b, lang="en")
    assert cls_it.label == cls_en.label              # il codice non dipende dalla lingua
    assert cls_it.reason != cls_en.reason
    assert not hasattr(cls_it, "label_it")
    assert not hasattr(cls_en, "label_it")


def test_classify_transition_en_technically_safe():
    a = make_track(bpm=130, key="7A")
    b = make_track(bpm=130, key="7A")
    cls_it = classify_transition(a, b)
    cls_en = classify_transition(a, b, lang="en")
    assert cls_it.label == cls_en.label == "technically_safe"
    assert cls_it.reason != cls_en.reason


def test_classify_transition_en_creative_risk():
    a = make_track(bpm=130, key="7A", energy=70, genre="techno")
    b = make_track(bpm=145, key="2B", energy=72, genre="techno")
    cls_it = classify_transition(a, b)
    cls_en = classify_transition(a, b, lang="en")
    assert cls_it.label == cls_en.label == "creative_risk"
    assert cls_it.reason != cls_en.reason


def test_classify_transition_unknown_lang_falls_back_to_it():
    a = make_track(bpm=130, key="7A")
    b = make_track(bpm=130, key="7A")
    assert classify_transition(a, b, lang="fr").reason == classify_transition(a, b, lang="it").reason


def test_mixing_tip_en():
    a = make_track(bpm=128, key="8A", energy=60)
    b = make_track(bpm=129, key="9A", energy=66)  # +1 BPM, key adiacente
    assert mixing_tip(a, b, lang="en") != mixing_tip(a, b, lang="it")


def test_mixing_tip_en_missing_bpm():
    a = make_track(bpm=None, key=None)
    b = make_track(bpm=128, key="8A")
    tip_it = mixing_tip(a, b)
    tip_en = mixing_tip(a, b, lang="en")
    assert tip_it != tip_en
    assert "sincronizza a orecchio" in tip_it
    assert "sync by ear" in tip_en


def test_mixing_overview_en():
    tracks = [
        make_track(bpm=120, key="8A", energy=40),
        make_track(bpm=121, key="9A", energy=50),
        make_track(bpm=138, key="2B", energy=80),
    ]
    out_it = mixing_overview(tracks)
    out_en = mixing_overview(tracks, lang="en")
    assert out_it != out_en
    assert any("salto marcato al brano 3" in b for b in out_it)
    assert any("sharp jump at track 3" in b for b in out_en)
