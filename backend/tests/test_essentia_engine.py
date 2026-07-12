"""Adapter Essentia: mapping key->Camelot (puro) + smoke test sul motore vero."""
import math
import struct
import wave

import pytest

from app.integrations import essentia_engine as eng


def test_key_to_camelot_mapping():
    assert eng._key_to_camelot("A", "minor") == "8A"
    assert eng._key_to_camelot("C", "major") == "8B"
    assert eng._key_to_camelot("F#", "minor") == "11A"
    assert eng._key_to_camelot("Eb", "major") == "5B"
    assert eng._key_to_camelot("", "minor") is None


def test_is_available_bool():
    assert isinstance(eng.is_available(), bool)


def _click_track_wav(path, bpm=120.0, seconds=20, sr=44100):
    """Click ogni beat a `bpm`: contenuto ritmico inequivocabile per il tempo."""
    interval = int(sr * 60 / bpm)
    frames = bytearray()
    for i in range(sr * seconds):
        on_click = (i % interval) < int(sr * 0.01)  # click di 10ms
        val = int(0.9 * 32767 * math.sin(2 * math.pi * 1000 * i / sr)) if on_click else 0
        frames += struct.pack("<h", val)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes(bytes(frames))


@pytest.mark.skipif(not eng.is_available(), reason="Essentia non installata")
def test_analyze_click_track(tmp_path):
    p = tmp_path / "click120.wav"
    _click_track_wav(p, bpm=120.0)
    res = eng.analyze(str(p))
    assert res.bpm is not None and abs(res.bpm - 120.0) < 2.0
    # La key di un click track non e' significativa: basta che non crashi.


@pytest.mark.skipif(not eng.is_available(), reason="Essentia non installata")
def test_analyze_subprocess_click_track(tmp_path):
    """analyze_subprocess deve dare lo stesso BPM di analyze, ma isolando Essentia
    in un processo separato (non trattiene il GIL del web server)."""
    p = tmp_path / "click120.wav"
    _click_track_wav(p, bpm=120.0)
    res = eng.analyze_subprocess(str(p))
    assert res.bpm is not None and abs(res.bpm - 120.0) < 2.0


def test_analyze_subprocess_raises_on_bad_file(tmp_path):
    """File inesistente: il worker esce con codice != 0 e analyze_subprocess
    solleva — così il job registra analysis_error e prosegue il batch. Vale a
    prescindere da Essentia (assente -> import error nel worker -> rc != 0)."""
    with pytest.raises(Exception):
        eng.analyze_subprocess(str(tmp_path / "non-esiste.wav"))
