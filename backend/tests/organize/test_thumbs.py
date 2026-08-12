"""Miniature generate dall'artwork embeddato: generazione, cache, invalidazione."""

import io
import os
import struct

import pytest
from PIL import Image

from app.core.config import settings
from app.organize.integrations import tagio
from app.organize.services import thumbs


def _jpeg(size=(500, 400), color=(200, 30, 30)) -> bytes:
    """JPEG vero: Pillow deve poterlo aprire (il _JPG dei test tagio è un
    header senza dati e non è decodificabile)."""
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="JPEG")
    return buf.getvalue()


def _decompression_bomb_bmp(width=20000, height=20000) -> bytes:
    """Header BMP valido che dichiara `width x height` pixel senza contenerne
    i dati: Pillow calcola le dimensioni dall'header in Image.open(), prima
    di decodificare un solo pixel, e solleva DecompressionBombError appena
    width*height supera 2x Image.MAX_IMAGE_PIXELS (~179M). Non serve altro
    che i 54 byte di header per farlo scattare."""
    dib = struct.pack("<IiiHHIIiiII", 40, width, height, 1, 24, 0, 0, 0, 0, 0, 0)
    file_header = b"BM" + struct.pack("<IHHI", 14 + 40, 0, 0, 14 + 40)
    return file_header + dib


@pytest.fixture
def cache_dir(tmp_path, monkeypatch):
    d = tmp_path / "tc"
    monkeypatch.setattr(settings, "thumb_cache_dir", str(d))
    return d


def test_get_thumb_generates_and_caches(copy_fixture, tmp_path, cache_dir):
    f = copy_fixture("flac", tmp_path / "a.flac")
    tagio.write_cover(f, _jpeg())

    data = thumbs.get_thumb(1, f)

    assert data is not None
    assert os.path.exists(cache_dir / "1.jpg")
    img = Image.open(io.BytesIO(data))
    assert max(img.size) == thumbs.THUMB_MAX_PX   # 500x400 → 96x76
    assert img.format == "JPEG"


def test_get_thumb_second_call_reads_the_cache(copy_fixture, tmp_path, cache_dir, monkeypatch):
    f = copy_fixture("flac", tmp_path / "a.flac")
    tagio.write_cover(f, _jpeg())
    first = thumbs.get_thumb(1, f)

    calls = []
    monkeypatch.setattr(thumbs.tagio, "read_cover", lambda p: calls.append(p))
    assert thumbs.get_thumb(1, f) == first
    assert calls == []          # il file audio non è stato riaperto


def test_get_thumb_invalidated_by_mtime(copy_fixture, tmp_path, cache_dir):
    f = copy_fixture("flac", tmp_path / "a.flac")
    tagio.write_cover(f, _jpeg(color=(200, 30, 30)))
    red = thumbs.get_thumb(1, f)

    tagio.write_cover(f, _jpeg(color=(30, 30, 200)))
    future = os.path.getmtime(f) + 10
    os.utime(f, (future, future))   # deterministico: l'audio è più recente della thumb

    assert thumbs.get_thumb(1, f) != red


def test_get_thumb_without_cover_is_none(copy_fixture, tmp_path, cache_dir):
    f = copy_fixture("flac", tmp_path / "a.flac")
    assert thumbs.get_thumb(1, f) is None
    assert not os.path.exists(cache_dir / "1.jpg")


def test_get_thumb_missing_file_is_none(tmp_path, cache_dir):
    assert thumbs.get_thumb(1, str(tmp_path / "fantasma.flac")) is None


def test_get_thumb_corrupt_artwork_is_none(copy_fixture, tmp_path, cache_dir):
    """Artwork che Pillow non sa aprire: trattato come 'senza copertina'."""
    f = copy_fixture("flac", tmp_path / "a.flac")
    tagio.write_cover(f, b"questa non e' un'immagine")
    assert thumbs.get_thumb(1, f) is None


def test_get_thumb_decompression_bomb_is_none(copy_fixture, tmp_path, cache_dir):
    """Image.open() solleva DecompressionBombError (eredita da Exception, non
    da OSError/ValueError) per un header che dichiara dimensioni abnormi:
    deve degradare a 'nessuna cover', non propagare un 500."""
    f = copy_fixture("flac", tmp_path / "a.flac")
    tagio.write_cover(f, _decompression_bomb_bmp())
    assert thumbs.get_thumb(1, f) is None
