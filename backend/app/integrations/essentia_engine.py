"""Motore di analisi BPM/key in-app (Essentia).

Import lazy: l'app parte anche senza la libreria installata; is_available()
alimenta il 503 `analysis_engine_unavailable` del router. Deterministico: BPM da
RhythmExtractor2013 (multifeature), key dal profilo 'edma' (tarato elettronica),
convertita nella notazione Camelot canonica del progetto ("7A")."""

from __future__ import annotations

from dataclasses import dataclass

from app.services.camelot import pitch_to_camelot


@dataclass
class AnalysisResult:
    bpm: float | None
    camelot: str | None


def is_available() -> bool:
    try:
        import essentia.standard  # noqa: F401
    except ImportError:
        return False
    return True


def _key_to_camelot(key: str, scale: str) -> str | None:
    """Mappa l'output di KeyExtractor (es. 'A', 'minor') in Camelot canonico."""
    if not key:
        return None
    suffix = "m" if (scale or "").lower().startswith("min") else ""
    return pitch_to_camelot(f"{key}{suffix}")


def analyze(path: str) -> AnalysisResult:
    """Analizza un file audio (mp3/flac/aiff/wav: decoding interno di Essentia).

    Puo' sollevare qualunque eccezione Essentia su file illeggibili: il job la
    traduce in `analysis_error` per traccia senza fermare il batch.
    """
    import essentia.standard as es

    audio = es.MonoLoader(filename=path, sampleRate=44100)()
    bpm_raw = float(es.RhythmExtractor2013(method="multifeature")(audio)[0])
    bpm = round(bpm_raw, 2) if bpm_raw > 0 else None
    key, scale, _strength = es.KeyExtractor(profileType="edma")(audio)
    return AnalysisResult(bpm=bpm, camelot=_key_to_camelot(key, scale))
