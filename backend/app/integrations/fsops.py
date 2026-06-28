"""Operazioni filesystem sicure per Apply/Undo: mai overwrite, fallback cross-disco."""

import errno
import os
import shutil

from app.integrations.content_hash import compute


class FsOpError(Exception):
    """Operazione FS rifiutata o fallita."""


def safe_move(src: str, dst: str) -> None:
    if os.path.exists(dst):
        raise FsOpError(f"destinazione già esistente: {dst}")
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    try:
        os.rename(src, dst)
    except OSError as exc:
        if exc.errno != errno.EXDEV:
            raise
        ext = os.path.splitext(src)[1]
        tmp = dst + ".tmp"
        shutil.copy2(src, tmp)
        if compute(tmp, ext)[0] != compute(src, ext)[0]:
            os.remove(tmp)
            raise FsOpError(f"verifica hash fallita copiando {src}") from exc
        os.replace(tmp, dst)
        os.remove(src)


def quarantine_path_for(path: str, root_path: str) -> str:
    rel = os.path.relpath(path, root_path)
    q = os.path.join(root_path, ".quarantine", rel)
    base, i = q, 1
    while os.path.exists(q):
        q = f"{base}.{i}"
        i += 1
    return q
