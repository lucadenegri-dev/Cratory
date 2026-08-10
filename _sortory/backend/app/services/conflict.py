"""Conflict: valida il piano. `check` è puro e deterministico;
`disk_occupied` è l'unico punto che tocca il filesystem."""

import os
from dataclasses import dataclass

from app.services import planner


@dataclass(frozen=True)
class ConflictComputed:
    kind: str
    file_id: int
    detail: str


def _is_under(path: str, base: str) -> bool:
    try:
        return os.path.commonpath([os.path.abspath(path), os.path.abspath(base)]) \
            == os.path.abspath(base)
    except ValueError:
        return False


def disk_occupied(plan_ops) -> set[str]:
    """Destinazioni dei MOVE/RENAME già esistenti su disco (file non noti al DB).
    Esclude i rename di solo case (samefile) e gli slot liberati da un DELETE."""
    delete_paths = {op.before["path"] for op in plan_ops if op.kind == "DELETE"}
    out: set[str] = set()
    for op in plan_ops:
        if op.kind not in ("RENAME", "MOVE"):
            continue
        dest = op.after["path"]
        if dest in delete_paths or not os.path.exists(dest):
            continue
        try:
            if os.path.samefile(op.before["path"], dest):
                continue
        except OSError:
            pass
        out.add(dest)
    return out


def check(plan_ops, files_by_id, accepted_issues, removals, settings_snapshot,
          root_targets, disk_occupied=None) -> list[ConflictComputed]:
    removals = set(removals)
    on_disk = disk_occupied or set()
    conflicts: list[ConflictComputed] = []

    move_ops = [op for op in plan_ops if op.kind in ("RENAME", "MOVE")]
    dest_count: dict[str, int] = {}
    for op in move_ops:
        dest = op.after["path"]
        dest_count[dest] = dest_count.get(dest, 0) + 1
    moved_ids = {op.file_id for op in move_ops}
    occupied = {f.path for fid, f in files_by_id.items()
                if fid not in moved_ids and fid not in removals}

    for op in move_ops:
        dest = op.after["path"]
        if dest_count[dest] > 1 or dest in occupied:
            conflicts.append(ConflictComputed("collision", op.file_id,
                                              f"collisione destinazione: {dest}"))
        elif dest in on_disk:
            conflicts.append(ConflictComputed("collision", op.file_id,
                                              f"destinazione già esistente su disco: {dest}"))
        file = files_by_id.get(op.file_id)
        target = root_targets.get(file.root_id) if file else None
        if target is not None and not _is_under(dest, target):
            conflicts.append(ConflictComputed("outside_root", op.file_id,
                                              f"destinazione fuori radice: {dest}"))

    by_file = planner.fixes_by_file(accepted_issues)
    for fid, file in files_by_id.items():
        if fid in removals:
            continue
        tags = planner.effective_tags(file, by_file.get(fid, []))
        _dest, miss = planner.render_destination(file, tags, settings_snapshot, root_targets)
        if miss is not None:
            conflicts.append(ConflictComputed("missing_template_data", fid,
                                              f"campo mancante per il template: {miss}"))
    return conflicts
