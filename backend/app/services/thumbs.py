"""Miniature delle copertine **già embeddate** nei file: generate alla prima
richiesta, cachate su disco, invalidate dall'mtime del file audio.

Gemello di cover_cache.py, che invece ospita le copertine *proposte* dai
provider e non richiede né lettura del file né ridimensionamento."""

import io
import os

from PIL import Image, UnidentifiedImageError

from app.core.config import settings
from app.integrations import tagio

# 3x rispetto ai 32px a schermo: nitida su display retina, ~4 KB per file.
THUMB_MAX_PX = 96


def _dir() -> str:
    os.makedirs(settings.thumb_cache_dir, exist_ok=True)
    return settings.thumb_cache_dir


def thumb_path(file_id: int) -> str:
    return os.path.join(_dir(), f"{file_id}.jpg")


def _render(data: bytes) -> bytes | None:
    """Ridimensiona a THUMB_MAX_PX (lato lungo) e ricodifica in JPEG.
    None se l'immagine non è decodificabile: artwork rotto = nessuna cover."""
    try:
        img = Image.open(io.BytesIO(data)).convert("RGB")
        img.thumbnail((THUMB_MAX_PX, THUMB_MAX_PX))
        out = io.BytesIO()
        img.save(out, format="JPEG", quality=80)
        return out.getvalue()
    except (UnidentifiedImageError, OSError, ValueError):
        return None


def get_thumb(file_id: int, audio_path: str) -> bytes | None:
    """Miniatura JPEG della cover embeddata, dalla cache o rigenerata.
    La cache è valida finché è più recente del file audio: apply, undo e
    ri-taggature cambiano l'mtime e quindi la invalidano da sé."""
    try:
        audio_mtime = os.path.getmtime(audio_path)
    except OSError:
        return None
    cached = thumb_path(file_id)
    if os.path.exists(cached) and os.path.getmtime(cached) >= audio_mtime:
        with open(cached, "rb") as fh:
            return fh.read()
    raw = tagio.read_cover(audio_path)
    if raw is None:
        return None
    thumb = _render(raw)
    if thumb is None:
        return None
    with open(cached, "wb") as fh:
        fh.write(thumb)
    return thumb
