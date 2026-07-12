"""Regole deterministiche di divergenza e apply dell'analisi in-app."""
from app.models import Track
from app.services.audio_analysis import (apply_analysis, auto_apply_missing,
                                         divergence_row, diverges)


def _t(**kw):
    return Track(source_type="spotify", has_local_file=True, **kw)


def test_diverges_bpm_a_un_decimale():
    assert diverges(_t(bpm=128.0, analysis_bpm=128.04)) is False  # 128.0 vs 128.0
    assert diverges(_t(bpm=128.0, analysis_bpm=128.3)) is True
    assert diverges(_t(bpm=None, analysis_bpm=128.3)) is False    # vuoto: non diverge
    assert diverges(_t(bpm=128.0, analysis_bpm=None)) is False    # non analizzata


def test_diverges_key_stringa_canonica():
    assert diverges(_t(camelot_key="8A", analysis_camelot="8A")) is False
    assert diverges(_t(camelot_key="8A", analysis_camelot="9A")) is True
    assert diverges(_t(camelot_key=None, analysis_camelot="9A")) is False


def test_apply_analysis_scrive_canonici_e_source():
    t = _t(bpm=128.0, bpm_source="rekordbox", camelot_key="8A", key_source="manual",
           analysis_bpm=130.0, analysis_camelot="9A", genre="techno")
    assert apply_analysis(t) is True
    assert t.bpm == 130.0 and t.bpm_source == "cratory"
    assert t.camelot_key == "9A" and t.key_source == "cratory"
    assert t.status == "ready_for_set" and t.energy is not None


def test_apply_analysis_noop_senza_differenze():
    t = _t(bpm=130.0, bpm_source="rekordbox", camelot_key="9A", key_source="rekordbox",
           analysis_bpm=130.0, analysis_camelot="9A")
    assert apply_analysis(t) is False
    assert t.bpm_source == "rekordbox"  # valore identico: la fonte non cambia


def test_apply_analysis_noop_bpm_identico_a_un_decimale():
    # 128.0 vs 128.04 = identici a 1 decimale (rumore analizzatore): non deve
    # riscrivere il BPM ne' declassare bpm_source rekordbox -> cratory.
    t = _t(bpm=128.0, bpm_source="rekordbox", camelot_key="8A", key_source="rekordbox",
           analysis_bpm=128.04, analysis_camelot="8A")
    assert apply_analysis(t) is False
    assert t.bpm == 128.0 and t.bpm_source == "rekordbox"


def test_auto_apply_solo_campi_vuoti():
    t = _t(bpm=128.0, bpm_source="rekordbox", camelot_key=None,
           analysis_bpm=130.0, analysis_camelot="9A")
    assert auto_apply_missing(t) is True
    assert t.bpm == 128.0 and t.bpm_source == "rekordbox"  # pieno: intatto
    assert t.camelot_key == "9A" and t.key_source == "cratory"  # vuoto: riempito
    assert t.status == "ready_for_set"


def test_divergence_row_completa():
    t = _t(bpm=128.0, bpm_source="rekordbox", camelot_key="8A", key_source="rekordbox",
           analysis_bpm=130.5, analysis_camelot="8B", artist="A", title="T")
    t.id = 7
    row = divergence_row(t)
    assert row["track_id"] == 7 and row["bpm_delta"] == 2.5
    assert row["key_compatibility"] == "compatible"  # 8A vs 8B: relativa
