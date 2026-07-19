"""A18: mix senza durata da yt-dlp -> fallback ffprobe sul file scaricato.

Senza fallback, plan_offsets(0) campiona il solo offset 0: tracklist di 1 brano
marcata "done". Il WAV di test e' generato con la stdlib (wave), niente rete.
"""
import wave
from pathlib import Path

from app.services import mix_identify
from app.services.mix_identify import SetMeta, identify_set, plan_offsets, probe_duration


def _make_wav(path: Path, seconds: int, rate: int = 8000) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * rate * seconds)


def test_probe_duration_reads_real_file(tmp_path):
    wav = tmp_path / "mix.wav"
    _make_wav(wav, seconds=3)
    assert probe_duration(str(wav)) == 3


def test_probe_duration_none_on_invalid_file(tmp_path):
    bad = tmp_path / "not_audio.bin"
    bad.write_bytes(b"junk")
    assert probe_duration(str(bad)) is None


def test_identify_set_falls_back_to_probe_when_no_duration(tmp_path, monkeypatch):
    # yt-dlp non fornisce la durata -> identify_set deve ripiegare su probe_duration
    # e passare al campionamento la durata reale, non 0 (= solo offset 0).
    meta = SetMeta(source_url="https://x/mix", title="Mix", duration_seconds=None)
    monkeypatch.setattr(mix_identify, "download_audio",
                        lambda url, workdir: (str(tmp_path / "mix.wav"), meta))
    monkeypatch.setattr(mix_identify, "probe_duration", lambda path: 600)

    seen: dict = {}

    def fake_core(duration, recognize_at, on_progress=None):
        seen["duration"] = duration
        return [], None

    monkeypatch.setattr(mix_identify, "identify_from_recognizer", fake_core)

    out_meta, _tracks, _aborted = identify_set("https://x/mix", recognizer=object())

    assert seen["duration"] == 600, \
        "senza durata yt-dlp deve campionare la durata da ffprobe, non 0"
    assert out_meta.duration_seconds == 600, "la durata ripiegata va salvata nel meta"
