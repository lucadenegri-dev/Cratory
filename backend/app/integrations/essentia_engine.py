"""Motore di analisi BPM/key in-app (Essentia).

Import lazy: l'app parte anche senza la libreria installata; is_available()
alimenta il 503 `analysis_engine_unavailable` del router. Deterministico: BPM da
RhythmExtractor2013 (multifeature), key dal profilo 'edma' (tarato elettronica),
convertita nella notazione Camelot canonica del progetto ("7A")."""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from app.services.camelot import pitch_to_camelot

# Radice backend (contiene il package `app`): serve come cwd del subprocess perche'
# `python -m app.integrations.essentia_worker` risolva l'import. __file__ =
# backend/app/integrations/essentia_engine.py -> parents[2] = backend/.
_BACKEND_ROOT = Path(__file__).resolve().parents[2]

# Timeout per traccia: un'analisi reale sta sotto i ~10s; oltre il minuto e' un file
# patologico o un hang -> meglio far fallire quella traccia e proseguire il batch.
_ANALYZE_TIMEOUT_S = 120


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


def analyze_subprocess(path: str) -> AnalysisResult:
    """Come analyze(), ma esegue Essentia in un processo separato.

    Essentia e' C++ e trattiene il GIL per secondi su una traccia reale: eseguirla
    nel thread del job (stesso processo del web server single-worker) congela tutte
    le altre richieste finche' l'analisi non finisce. Il subprocess isola quel
    lavoro CPU-bound — il chiamante resta in attesa I/O e rilascia il GIL, cosi' il
    server resta reattivo (stesso pattern di ffmpeg nell'indicizzazione).

    Solleva su fallimento (rc != 0, timeout, output non parsabile): il job traduce
    l'eccezione in `analysis_error` per traccia senza fermare il batch.
    """
    proc = subprocess.run(
        [sys.executable, "-m", "app.integrations.essentia_worker", path],
        capture_output=True, text=True, cwd=_BACKEND_ROOT, timeout=_ANALYZE_TIMEOUT_S,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"essentia worker rc={proc.returncode} per {path}: "
            f"{proc.stderr.strip()[-500:]}")
    # Essentia logga su stderr: lo stdout contiene solo il JSON. Ultima riga per
    # difesa da eventuale rumore.
    data = json.loads(proc.stdout.strip().splitlines()[-1])
    return AnalysisResult(bpm=data["bpm"], camelot=data["camelot"])
