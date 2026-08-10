"""Operazioni filesystem sicure per Apply/Undo: mai overwrite, fallback cross-disco."""

import errno
import os
import shutil

from app.organize.integrations.content_hash import compute


class FsOpError(Exception):
    """Operazione FS rifiutata o fallita."""


def _same_file(a: str, b: str) -> bool:
    try:
        return os.path.exists(a) and os.path.exists(b) and os.path.samefile(a, b)
    except OSError:
        return False


def safe_move(src: str, dst: str) -> None:
    # Su FS case-insensitive (APFS) un rename di solo case vede la dest
    # "esistente" perché È il file sorgente: va lasciato passare.
    if os.path.exists(dst) and not _same_file(src, dst):
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


def _strictly_under(path: str, roots: set[str]) -> bool:
    for root in roots:
        try:
            if path != root and os.path.commonpath([path, root]) == root:
                return True
        except ValueError:
            continue
    return False


def cleanup_empty_dirs(dirs, stop_roots) -> int:
    """Rimuove le directory vuote (o con solo .DS_Store) risalendo da `dirs`
    verso le radici in `stop_roots`, senza mai toccare le radici stesse."""
    stops = {os.path.abspath(r) for r in stop_roots}
    removed = 0
    for start in sorted({os.path.abspath(d) for d in dirs}, key=len, reverse=True):
        cur = start
        while _strictly_under(cur, stops):
            try:
                entries = os.listdir(cur)
            except OSError:
                break
            if entries == [".DS_Store"]:
                try:
                    os.remove(os.path.join(cur, ".DS_Store"))
                except OSError:
                    break
                entries = []
            if entries:
                break
            try:
                os.rmdir(cur)
            except OSError:
                break
            removed += 1
            cur = os.path.dirname(cur)
    return removed


def quarantine_path_for(path: str, root_path: str) -> str:
    rel = os.path.relpath(path, root_path)
    q = os.path.join(root_path, ".quarantine", rel)
    base, i = q, 1
    while os.path.exists(q):
        q = f"{base}.{i}"
        i += 1
    return q
