"""Planner: calcola le operazioni del piano. Puro, deterministico."""

import os
import re
import unicodedata
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


def same_fs_path(a: str, b: str) -> bool:
    """True se due percorsi indicano lo STESSO file sul filesystem locale.

    macOS/APFS è insensibile a maiuscole/minuscole *e* alla forma di
    normalizzazione Unicode: un nome scritto NFD su disco e lo stesso nome NFC
    reso dai tag sono lo stesso file. Confrontarli come stringhe esatte farebbe
    rigenerare all'infinito rinomine/spostamenti già soddisfatti (il file c'è
    già, cambia solo la forma dei byte del nome, che `os.rename` non tocca)."""
    return unicodedata.normalize("NFC", a).casefold() == \
        unicodedata.normalize("NFC", b).casefold()


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
        if f.id in removals:
            del_ops.append(PlanOpComputed("DELETE", f.id, {"path": f.path}, {}))
            continue
        fixes = by_file.get(f.id, [])
        if fixes:
            eff = effective_tags(f, fixes)
            touched = sorted({fix["field"] for fix in fixes
                              if fix.get("field") in _EFFECTIVE_FIELDS})
            # Solo i campi il cui valore è DAVVERO diverso da quello già sul file:
            # una issue resta 'accepted' per sempre, e senza questo filtro
            # rigenererebbe un RETAG no-op a ogni ricostruzione del piano.
            changed = [field for field in touched if getattr(f, field) != eff[field]]
            if changed:
                before = {field: getattr(f, field) for field in changed}
                after = {field: eff[field] for field in changed}
                retag_ops.append(PlanOpComputed("RETAG", f.id, before, after))

        dest, _miss = render_destination(f, effective_tags(f, fixes),
                                         settings_snapshot, root_targets)
        if dest is None or same_fs_path(dest, f.path):
            continue
        kind = "RENAME" if os.path.dirname(dest) == os.path.dirname(f.path) else "MOVE"
        move_ops.append(PlanOpComputed(kind, f.id, {"path": f.path}, {"path": dest}))

    return retag_ops + move_ops + del_ops
