"""Cache su disco delle thumbnail cover proposte. Byte fuori dal DB → DB leggero,
servibili come file statico. La full-res NON passa di qui (scaricata all'apply)."""

import os
import uuid

from app.organize.core.config import settings


def _dir() -> str:
    os.makedirs(settings.cover_cache_dir, exist_ok=True)
    return settings.cover_cache_dir


def thumb_path(file_id: int) -> str:
    return os.path.join(_dir(), f"{file_id}.jpg")


def drop_thumb(file_id: int) -> None:
    """Rimuove la proposta cachata di un file eliminato. Gemella di
    thumbs.drop_thumb: stesso motivo (id di AudioFile riassegnabile),
    silenziosa se il file non c'è."""
    try:
        os.remove(thumb_path(file_id))
    except OSError:
        pass


def save_thumb(file_id: int, data: bytes) -> str:
    # Scrittura atomica: file temporaneo nella stessa dir + os.replace(), così
    # due richieste concorrenti non interleaviano mai byte nello stesso file.
    # Suffisso random (non solo pid): con handler sincroni FastAPI gira su un
    # threadpool, quindi due richieste concorrenti possono condividere il pid.
    path = thumb_path(file_id)
    tmp = f"{path}.{uuid.uuid4().hex}.tmp"
    with open(tmp, "wb") as fh:
        fh.write(data)
    os.replace(tmp, path)
    return f"cover_cache/{file_id}.jpg"


def read_thumb(file_id: int) -> bytes | None:
    path = thumb_path(file_id)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "rb") as fh:
            return fh.read()
    except OSError:
        # Race con una delete/rewrite concorrente tra l'exists() e l'open():
        # trattata come cache assente, non come 500.
        return None
