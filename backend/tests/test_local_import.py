"""Import da cartella locale: scansione, fallback nome file, idempotenza, separazione tracce."""

import math
import struct
import wave

import pytest

from app.models import Playlist, Track
from app.services.local_import import scan_folder


def _write_wav(path, *, freq: int = 440, secs: float = 0.5, rate: int = 22050) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        frames = b"".join(
            struct.pack("<h", int(30000 * math.sin(2 * math.pi * freq * i / rate)))
            for i in range(int(rate * secs))
        )
        w.writeframes(frames)


def _tag_wav(path, *, title=None, artist=None) -> None:
    from mutagen.id3 import TIT2, TPE1
    from mutagen.wave import WAVE

    w = WAVE(str(path))
    if w.tags is None:
        w.add_tags()
    if title:
        w.tags.add(TIT2(encoding=3, text=[title]))
    if artist:
        w.tags.add(TPE1(encoding=3, text=[artist]))
    w.save()


def test_scan_folder_ricorsivo_ignora_non_audio(tmp_path):
    _write_wav(tmp_path / "a.wav", freq=440)
    sub = tmp_path / "sub"
    sub.mkdir()
    _write_wav(sub / "b.wav", freq=660)
    (tmp_path / "note.txt").write_text("x")
    found = scan_folder(tmp_path, recurse=True)
    names = sorted(p.name for p in found)
    assert names == ["a.wav", "b.wav"]

