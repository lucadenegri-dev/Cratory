"""Cache su disco delle thumbnail cover proposte. Byte fuori dal DB → DB leggero,
servibili come file statico. La full-res NON passa di qui (scaricata all'apply)."""

import os

from app.core.config import settings


def _dir() -> str:
    os.makedirs(settings.cover_cache_dir, exist_ok=True)
    return settings.cover_cache_dir


def thumb_path(file_id: int) -> str:
    return os.path.join(_dir(), f"{file_id}.jpg")


def save_thumb(file_id: int, data: bytes) -> str:
    with open(thumb_path(file_id), "wb") as fh:
        fh.write(data)
    return f"cover_cache/{file_id}.jpg"


def read_thumb(file_id: int) -> bytes | None:
    path = thumb_path(file_id)
    if not os.path.exists(path):
        return None
    with open(path, "rb") as fh:
        return fh.read()
