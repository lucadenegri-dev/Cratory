"""Planner: calcola le operazioni del piano. Puro, deterministico."""

import os
import re
import unicodedata
from dataclasses import dataclass

# I 9 campi tag testuali che Sortory gestisce: compongono i "tag effettivi" per il
# piano, sono gli unici correggibili a mano (services.manual_edit) e via fix di una
# issue (routers.issues). Unica fonte condivisa, per non farli divergere.
EDITABLE_TAG_FIELDS = ("artist", "title", "album", "album_artist", "genre", "year",
                       "label", "track_no", "comment")
_TEMPLATE_FIELD_RE = re.compile(r"\{(\w+)\}")
_SANITIZE_RE = re.compile(r'[/\\:*?"<>|]')


def _norm(v):
    # year/track_no sono colonne int ma il "to" degli override arriva come stringa:
    # normalizziamo entrambi a str (preservando None) per non generare RETAG fantasma.
    return None if v is None else str(v)


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
    tags = {k: getattr(file, k) for k in EDITABLE_TAG_FIELDS}
    for fix in fixes:
        field = fix.get("field")
        if field in EDITABLE_TAG_FIELDS:
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
    files_by_id = {f.id: f for f in files}
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
                              if fix.get("field") in EDITABLE_TAG_FIELDS})
            # Solo i campi il cui valore è DAVVERO diverso da quello già sul file:
            # una issue resta 'accepted' per sempre, e senza questo filtro
            # rigenererebbe un RETAG no-op a ogni ricostruzione del piano.
            changed = [field for field in touched if _norm(getattr(f, field)) != _norm(eff[field])]
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

    cover_ops: list[PlanOpComputed] = []
    for issue in accepted_issues:
        if issue.type != "missing_cover" or not issue.suggested_fix_json:
            continue
        f = files_by_id.get(issue.file_id)
        if f is None or f.id in removals or f.has_cover:
            continue
        fix = issue.suggested_fix_json
        cover_ops.append(PlanOpComputed(
            "COVER", f.id, {"has_cover": False},
            {"full_url": fix.get("full_url"), "source": fix.get("source"),
             "confidence": fix.get("confidence")}))

    rating_ops: list[PlanOpComputed] = []
    for issue in accepted_issues:
        if issue.type != "stray_rating" or not issue.suggested_fix_json:
            continue
        f = files_by_id.get(issue.file_id)
        # has_rating è il filtro no-op del RATING (come has_cover per la COVER):
        # la stray_rating resta 'accepted' per sempre, senza questo controllo
        # rigenererebbe un clear su file già puliti a ogni ricostruzione del piano.
        if f is None or f.id in removals or not f.has_rating:
            continue
        rating_ops.append(PlanOpComputed(
            "RATING", f.id, {"rating": "present"}, {"action": "clear"}))

    return retag_ops + cover_ops + rating_ops + move_ops + del_ops
