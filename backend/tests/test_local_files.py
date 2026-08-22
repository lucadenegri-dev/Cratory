"""Lettura tag + hash audio dei file locali (integrations/local_files.py).

I file di test sono WAV generati con la stdlib (nessun encoder esterno). I tag ID3
vengono scritti via mutagen.wave.WAVE: ffmpeg decodifica solo lo stream audio, quindi
l'hash resta stabile anche dopo aver modificato i tag.
"""

import math
import struct
import subprocess
import wave

import pytest

from app.integrations import local_files
from app.integrations.local_files import (
    AUDIO_EXTENSIONS,
    LocalFilesError,
    audio_hash,
    decode_pcm_bytes,
    read_cover,
    read_tags,
)
from app.services import system_probe as sp


def _ffmpeg_encode(path, *, title=None, artist=None, freq=440, secs=1.0):
    """Genera un file audio reale con ffmpeg (per testare formati non-WAV con tag)."""
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi",
           "-i", f"sine=frequency={freq}:duration={secs}"]
    if title:
        cmd += ["-metadata", f"title={title}"]
    if artist:
        cmd += ["-metadata", f"artist={artist}"]
    cmd += [str(path), "-y"]
    subprocess.run(cmd, check=True)


def _write_wav(path, *, freq: int = 440, secs: float = 1.0, rate: int = 22050) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        frames = b"".join(
            struct.pack("<h", int(30000 * math.sin(2 * math.pi * freq * i / rate)))
            for i in range(int(rate * secs))
        )
        w.writeframes(frames)


def _tag_wav(path, *, title=None, artist=None, album=None, date=None, isrc=None, label=None) -> None:
    from mutagen.id3 import TALB, TDRC, TIT2, TPE1, TPUB, TSRC
    from mutagen.wave import WAVE

    w = WAVE(str(path))
    if w.tags is None:
        w.add_tags()
    if title:
        w.tags.add(TIT2(encoding=3, text=[title]))
    if artist:
        w.tags.add(TPE1(encoding=3, text=[artist]))
    if album:
        w.tags.add(TALB(encoding=3, text=[album]))
    if date:
        w.tags.add(TDRC(encoding=3, text=[date]))
    if isrc:
        w.tags.add(TSRC(encoding=3, text=[isrc]))
    if label:
        w.tags.add(TPUB(encoding=3, text=[label]))
    w.save()


def test_audio_hash_deterministico(tmp_path):
    p = tmp_path / "a.wav"
    _write_wav(p, freq=440)
    assert audio_hash(p) == audio_hash(p)


def test_audio_hash_diverso_per_audio_diverso(tmp_path):
    a = tmp_path / "a.wav"
    b = tmp_path / "b.wav"
    _write_wav(a, freq=440)
    _write_wav(b, freq=880)
    assert audio_hash(a) != audio_hash(b)


def test_audio_hash_stabile_dopo_modifica_tag(tmp_path):
    p = tmp_path / "a.wav"
    _write_wav(p, freq=440)
    before = audio_hash(p)
    _tag_wav(p, title="Nuovo", artist="Tizio")
    assert audio_hash(p) == before  # i tag non entrano nell'hash dell'audio


def test_read_tags_legge_id3(tmp_path):
    p = tmp_path / "a.wav"
    _write_wav(p, secs=1.0)
    _tag_wav(p, title="Da Funk", artist="Daft Punk", album="Homework", date="1997", isrc="FRZ129700001")
    tags = read_tags(p)
    assert tags["title"] == "Da Funk"
    assert tags["artist"] == "Daft Punk"
    assert tags["album"] == "Homework"
    assert tags["year"] == 1997
    assert tags["isrc"] == "FRZ129700001"
    assert tags["duration_seconds"] == 1


def test_read_tags_legge_label_id3(tmp_path):
    p = tmp_path / "a.wav"
    _write_wav(p, secs=1.0)
    _tag_wav(p, title="Windowlicker", artist="Aphex Twin", label="Warp")
    tags = read_tags(p)
    assert tags["label"] == "Warp"


def test_read_tags_label_assente_e_none(tmp_path):
    p = tmp_path / "a.wav"
    _write_wav(p, secs=1.0)
    _tag_wav(p, title="No Label", artist="Anon")
    tags = read_tags(p)
    assert tags["label"] is None


def test_read_tags_legge_label_vorbis(tmp_path):
    # Vorbis comment (FLAC): la label sta nella chiave LABEL/ORGANIZATION.
    from mutagen.flac import FLAC

    p = tmp_path / "x.flac"
    _ffmpeg_encode(p, title="Xtal", artist="Aphex Twin")
    f = FLAC(str(p))
    f["LABEL"] = "R&S Records"
    f.save()
    tags = read_tags(p)
    assert tags["label"] == "R&S Records"


def test_read_tags_file_senza_tag(tmp_path):
    p = tmp_path / "a.wav"
    _write_wav(p, secs=1.0)
    tags = read_tags(p)
    assert tags["title"] is None
    assert tags["artist"] is None
    assert tags["duration_seconds"] == 1


def test_read_tags_flac_vorbis(tmp_path):
    # Regressione: i tag Vorbis (FLAC) non devono far sollevare le sonde di chiavi MP4.
    p = tmp_path / "x.flac"
    _ffmpeg_encode(p, title="Spastik", artist="Plastikman")
    tags = read_tags(p)
    assert tags["title"] == "Spastik"
    assert tags["artist"] == "Plastikman"


def test_read_tags_ogg_vorbis(tmp_path):
    p = tmp_path / "x.ogg"
    _ffmpeg_encode(p, title="Kerala", artist="Bonobo")
    tags = read_tags(p)
    assert tags["title"] == "Kerala"
    assert tags["artist"] == "Bonobo"


def test_audio_extensions_minuscole_con_punto():
    assert ".mp3" in AUDIO_EXTENSIONS
    assert ".flac" in AUDIO_EXTENSIONS
    assert all(e.startswith(".") and e == e.lower() for e in AUDIO_EXTENSIONS)
    # Verifica che tutte le estensioni fondamentali siano presenti
    assert {".mp3", ".flac", ".m4a", ".aac", ".aiff", ".aif", ".wav", ".ogg", ".opus", ".wma"} <= AUDIO_EXTENSIONS


def test_read_cover_flac_embedded(tmp_path):
    from mutagen.flac import FLAC, Picture

    p = tmp_path / "x.flac"
    _ffmpeg_encode(p, title="X", artist="A")
    pic = Picture()
    pic.type = 3  # front cover
    pic.mime = "image/png"
    pic.data = b"\x89PNG\r\n\x1a\nFAKEIMAGE"
    f = FLAC(str(p))
    f.add_picture(pic)
    f.save()

    cover = read_cover(p)
    assert cover is not None
    data, mime = cover
    assert data == b"\x89PNG\r\n\x1a\nFAKEIMAGE"
    assert mime == "image/png"


def test_read_cover_senza_artwork_e_none(tmp_path):
    p = tmp_path / "x.flac"
    _ffmpeg_encode(p, title="X", artist="A")
    assert read_cover(p) is None


def test_audio_hash_su_file_non_audio_solleva(tmp_path):
    p = tmp_path / "x.wav"
    p.write_bytes(b"non audio")
    with pytest.raises(LocalFilesError):
        audio_hash(p)


def test_read_audio_quality_returns_format(tmp_path):
    from app.integrations.local_files import read_audio_quality
    p = tmp_path / "a.wav"
    _write_wav(p, secs=1.0)
    q = read_audio_quality(p)
    assert q["format"] == "wav"
    # il bitrate puo' essere None o un intero, ma la chiave esiste
    assert "bitrate" in q


# --- Seam Tauri: audio_hash/decode_pcm_bytes devono risolvere ffmpeg con ----
# --- resolve_binary, non invocarlo nudo (solo PATH) -------------------------
#
# Un'app lanciata dal Finder eredita il PATH minimo di launchd, dove ffmpeg
# non c'e' (vive in /opt/homebrew/bin o, nel bundle, in Resources/bin). Il
# probe del wizard usa gia' resolve_binary (vede CRATORY_BIN_DIR): se queste
# funzioni invocano "ffmpeg" nudo, il wizard dice "presente" e l'hash/decode
# falliscono comunque.


def _finto_ffmpeg(tmp_path):
    fake = tmp_path / "ffmpeg"
    fake.write_text("#!/bin/sh\n")
    return fake


def test_audio_hash_usa_il_seam_per_risolvere_ffmpeg(tmp_path, monkeypatch):
    fake = _finto_ffmpeg(tmp_path)
    monkeypatch.setenv(sp.BIN_DIR_ENV, str(tmp_path))
    monkeypatch.setattr(sp.shutil, "which", lambda name: None)

    catturato = {}

    class _Esito:
        stdout = b"\x00\x00" * 100

    def _run_finto(cmd, **kwargs):
        catturato["cmd"] = cmd
        return _Esito()

    monkeypatch.setattr(local_files.subprocess, "run", _run_finto)

    audio_hash(tmp_path / "song.wav")

    assert catturato["cmd"][0] == str(fake)


def test_audio_hash_solleva_se_ffmpeg_non_risolvibile(tmp_path, monkeypatch):
    """Senza un ffmpeg risolvibile (ne' PATH ne' CRATORY_BIN_DIR), deve
    fallire con LocalFilesError PRIMA di invocare subprocess — mai un nome
    nudo che ricadrebbe silenziosamente sul solo PATH."""
    monkeypatch.setenv(sp.BIN_DIR_ENV, str(tmp_path))  # vuota: nessun ffmpeg dentro
    monkeypatch.setattr(sp.shutil, "which", lambda name: None)

    def _esplodi(cmd, **kwargs):
        raise AssertionError("non doveva invocare subprocess senza un binario risolto")

    monkeypatch.setattr(local_files.subprocess, "run", _esplodi)

    with pytest.raises(LocalFilesError):
        audio_hash(tmp_path / "song.wav")


def test_decode_pcm_bytes_usa_il_seam_per_risolvere_ffmpeg(tmp_path, monkeypatch):
    """Stesso seam di audio_hash, per decode_pcm_bytes (usato da audio_energy
    per l'analisi energia dei file locali)."""
    fake = _finto_ffmpeg(tmp_path)
    monkeypatch.setenv(sp.BIN_DIR_ENV, str(tmp_path))
    monkeypatch.setattr(sp.shutil, "which", lambda name: None)

    catturato = {}

    class _Esito:
        stdout = b"\x00\x00" * 100

    def _run_finto(cmd, **kwargs):
        catturato["cmd"] = cmd
        return _Esito()

    monkeypatch.setattr(local_files.subprocess, "run", _run_finto)

    decode_pcm_bytes(tmp_path / "song.wav")

    assert catturato["cmd"][0] == str(fake)


def test_decode_pcm_bytes_solleva_se_ffmpeg_non_risolvibile(tmp_path, monkeypatch):
    monkeypatch.setenv(sp.BIN_DIR_ENV, str(tmp_path))
    monkeypatch.setattr(sp.shutil, "which", lambda name: None)

    def _esplodi(cmd, **kwargs):
        raise AssertionError("non doveva invocare subprocess senza un binario risolto")

    monkeypatch.setattr(local_files.subprocess, "run", _esplodi)

    with pytest.raises(LocalFilesError):
        decode_pcm_bytes(tmp_path / "song.wav")
