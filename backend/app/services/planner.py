"""Planner: calcola le operazioni del piano. Puro, deterministico."""

import os
import re
from dataclasses import dataclass

_EFFECTIVE_FIELDS = ("artist", "title", "album", "album_artist", "genre", "year",
                     "label", "track_no", "comment")
_TEMPLATE_FIELD_RE = re.compile(r"\{(\w+)\}")
_SANITIZE_RE = re.compile(r'[/\\:*?"<>|]')


@dataclass(frozen=True)
class PlanOpComputed:
    kind: str
    file_id: int
    before: dict
    after: dict


def _sanitize(value: str) -> str:
    s = _SANITIZE_RE.sub("_", value).replace("..", "_")
    return s.strip(" .")


def _render(template: str, tags: dict) -> tuple[str | None, str | None]:
    """Ritorna (stringa_renderizzata, None) oppure (None, primo_campo_mancante)."""
    fields = _TEMPLATE_FIELD_RE.findall(template)
    for field in fields:
        v = tags.get(field)
        if v is None or (isinstance(v, str) and not v.strip()):
            return None, field
    out = template
    for field in fields:
        out = out.replace("{" + field + "}", _sanitize(str(tags[field]).strip()))
    return out, None


def fixes_by_file(accepted_issues) -> dict[int, list[dict]]:
    out: dict[int, list[dict]] = {}
    for issue in accepted_issues:
        if issue.suggested_fix_json:
            out.setdefault(issue.file_id, []).append(issue.suggested_fix_json)
    return out


def effective_tags(file, fixes: list[dict]) -> dict:
    tags = {k: getattr(file, k) for k in _EFFECTIVE_FIELDS}
    for fix in fixes:
        field = fix.get("field")
        if field in _EFFECTIVE_FIELDS:
            tags[field] = None if fix.get("action") == "clear" else fix.get("to")
    return tags


def render_destination(file, tags: dict, settings_snapshot: dict,
                       root_targets: dict) -> tuple[str | None, str | None]:
    folder_tpl = settings_snapshot.get("folder_template", "") or ""
    folder_part, miss = (_render(folder_tpl, tags) if folder_tpl else ("", None))
    if miss is not None:
        return None, miss
    name_part, miss = _render(settings_snapshot["naming_template"], tags)
    if miss is not None:
        return None, miss
    target_root = root_targets.get(file.root_id) or os.path.dirname(file.path)
    dest_dir = os.path.join(target_root, folder_part) if folder_part else target_root
    return os.path.join(dest_dir, f"{name_part}.{file.ext}"), None


def build_plan(files, accepted_issues, removals, settings_snapshot,
               root_targets) -> list[PlanOpComputed]:
    removals = set(removals)
    by_file = fixes_by_file(accepted_issues)
    retag_ops: list[PlanOpComputed] = []
    move_ops: list[PlanOpComputed] = []
    del_ops: list[PlanOpComputed] = []

    for f in sorted(files, key=lambda x: (x.path, x.id)):
        fixes = by_file.get(f.id, [])
        if fixes:
            before, after = {}, {}
            for fix in fixes:
                field = fix.get("field")
                if field not in _EFFECTIVE_FIELDS:
                    continue
                new_val = None if fix.get("action") == "clear" else fix.get("to")
                before.setdefault(field, getattr(f, field))
                after[field] = new_val
            if before:
                retag_ops.append(PlanOpComputed("RETAG", f.id, before, after))

        if f.id in removals:
            del_ops.append(PlanOpComputed("DELETE", f.id, {"path": f.path}, {}))
            continue

        dest, _miss = render_destination(f, effective_tags(f, fixes),
                                         settings_snapshot, root_targets)
        if dest is None or dest == f.path:
            continue
        kind = "RENAME" if os.path.dirname(dest) == os.path.dirname(f.path) else "MOVE"
        move_ops.append(PlanOpComputed(kind, f.id, {"path": f.path}, {"path": dest}))

    return retag_ops + move_ops + del_ops
