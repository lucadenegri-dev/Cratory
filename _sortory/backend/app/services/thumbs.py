"""Miniature delle copertine **già embeddate** nei file: generate alla prima
richiesta, cachate su disco, invalidate dall'mtime del file audio.

Gemello di cover_cache.py, che invece ospita le copertine *proposte* dai
provider e non richiede né lettura del file né ridimensionamento."""

import io
import os
import uuid

from PIL import Image

from app.core.config import settings
from app.integrations import tagio

# 3x rispetto ai 32px a schermo: nitida su display retina, ~4 KB per file.
THUMB_MAX_PX = 96


def _dir() -> str:
    os.makedirs(settings.thumb_cache_dir, exist_ok=True)
    return settings.thumb_cache_dir


def thumb_path(file_id: int) -> str:
    return os.path.join(_dir(), f"{file_id}.jpg")


def drop_thumb(file_id: int) -> None:
    """Rimuove la thumbnail cachata di un file eliminato. `id` di AudioFile è
    un rowid SQLite semplice (niente AUTOINCREMENT): una volta liberato può
    essere riassegnato da uno scan successivo, e senza questa pulizia
    servirebbe la cover del vecchio file. Silenziosa se il file non c'è."""
    try:
        os.remove(thumb_path(file_id))
    except OSError:
        pass


def _render(data: bytes) -> bytes | None:
    """Ridimensiona a THUMB_MAX_PX (lato lungo) e ricodifica in JPEG.
    None se l'immagine non è decodificabile: artwork rotto = nessuna cover.

    Confine di degradazione volutamente ampio (`except Exception`): oltre a
    `UnidentifiedImageError`/`OSError`/`ValueError`, Pillow solleva anche
    `DecompressionBombError` — che eredita da `Exception`, non da `OSError` —
    quando le dimensioni dichiarate nell'header superano ~179 milioni di
    pixel (bastano pochi KB di header per dichiararle). Qualunque eccezione
    qui dentro vale come "artwork non decodificabile": nessuna cover."""
    try:
        img = Image.open(io.BytesIO(data)).convert("RGB")
        img.thumbnail((THUMB_MAX_PX, THUMB_MAX_PX))
        out = io.BytesIO()
        img.save(out, format="JPEG", quality=80)
        return out.getvalue()
    except Exception:
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
    # Scrittura atomica: file temporaneo nella stessa dir + os.replace(), così
    # due richieste concorrenti per lo stesso file_id non interleaviano byte
    # nello stesso handle (il JPEG corrotto risultante passerebbe comunque il
    # controllo sull'mtime e verrebbe servito finché l'audio non cambia).
    # Suffisso random (non solo pid): con handler sincroni FastAPI gira su un
    # threadpool, quindi due richieste concorrenti possono condividere il pid.
    tmp = f"{cached}.{uuid.uuid4().hex}.tmp"
    with open(tmp, "wb") as fh:
        fh.write(thumb)
    os.replace(tmp, cached)
    return thumb
