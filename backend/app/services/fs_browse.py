"""Navigazione filesystem confinata a una root, per scegliere la cartella da importare.

App mono-utente locale: il browser non risolve mai un path sopra `local_import_root`
(default: home utente). Protegge da traversal (`..`) e symlink che escono dalla root.
"""

from pathlib import Path

from app.core.config import settings
from app.integrations.local_files import AUDIO_EXTENSIONS


class FsBrowseError(Exception):
    """Path fuori dalla root consentita, inesistente o non una directory."""


def resolve_import_root() -> Path:
    raw = settings.local_import_root.strip()
    return (Path(raw) if raw else Path.home()).resolve()


def _is_within(child: Path, root: Path) -> bool:
    try:
        child.relative_to(root)
        return True
    except ValueError:
        return False


def _audio_count(directory: Path) -> int:
    n = 0
    try:
        for entry in directory.iterdir():
            if entry.is_file() and entry.suffix.lower() in AUDIO_EXTENSIONS:
                n += 1
    except OSError:
        return 0
    return n


def browse(path: str | None, *, root: Path) -> dict:
    """Elenca le sottocartelle di `path` (o della root). Confina dentro `root`."""
    root = root.resolve()
    target = root if not path else Path(path)
    try:
        target = target.resolve()
    except OSError as exc:
        raise FsBrowseError(f"Path non risolvibile: {path}") from exc
    if not _is_within(target, root):
        raise FsBrowseError("Percorso fuori dalla cartella consentita.")
    if not target.is_dir():
        raise FsBrowseError(f"Non è una cartella: {target}")

    dirs = []
    for entry in sorted(target.iterdir(), key=lambda p: p.name.lower()):
        if entry.is_dir() and _is_within(entry.resolve(), root):
            dirs.append({
                "name": entry.name,
                "path": str(entry.resolve()),
                "audio_file_count": _audio_count(entry),
            })
    parent = target.parent.resolve()
    parent_path = str(parent) if target != root and _is_within(parent, root) else None
    return {"current_path": str(target), "parent_path": parent_path, "dirs": dirs}
