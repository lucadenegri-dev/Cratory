"""Orchestratore dell'analisi: legge audio_file, chiama Inspector/Dedup, fa il merge
preservando le decisioni utente. Impuro (scrive il DB)."""

import hashlib

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AudioFile, DupGroup, DupMember, Issue, utcnow
from app.schemas import AnalyzeSummary
from app.services.dedup import find_duplicates
from app.services.inspector import inspect


def _merge_issues(db: Session, computed) -> None:
    existing = {(i.file_id, i.type, i.field): i for i in db.scalars(select(Issue)).all()}
    # Campi (file, field) su cui un provider ha autorità: il provider_override è
    # synthetic (persiste anche da accepted) e fa da marcatore di provenienza.
    # Il provider vince sul case → l'Inspector non deve ri-proporre
    # 'inconsistent_casing' su quel campo, altrimenti provider (es. 'ivanovo
    # night luxe') e Inspector ('Ivanovo Night Luxe') oscillano all'infinito.
    # Non aggiungendo la key a 'seen', una eventuale casing già accettata viene
    # anche rimossa in coda (non è synthetic), togliendo il RETAG opposto.
    provider_owned = {(i.file_id, i.field) for i in existing.values()
                      if i.type == "provider_override"}
    seen: set = set()
    for c in computed:
        if c.type == "inconsistent_casing" and (c.file_id, c.field) in provider_owned:
            continue
        key = (c.file_id, c.type, c.field)
        seen.add(key)
        row = existing.get(key)
        if row is None:
            db.add(Issue(file_id=c.file_id, type=c.type, field=c.field, severity=c.severity,
                         detail=c.detail, suggested_fix_json=c.suggested_fix, status="open"))
        else:
            row.severity = c.severity
            row.detail = c.detail
            # Le decisioni utente sono intoccabili: aggiorna il suggested_fix solo
            # per le issue ancora 'open' e solo se l'Inspector ne ha uno. Non
            # azzerare con None un valore scelto dall'utente (es. suggerimenti AI
            # accettati), né riscrivere una decisione già presa.
            if row.status == "open" and c.suggested_fix is not None:
                row.suggested_fix_json = c.suggested_fix
            row.updated_at = utcnow()
    for key, row in existing.items():
        # Tipi sintetici (non prodotti dall'Inspector ma da azioni on-demand:
        # rescan provider, ricerca cover, rilevamento rating): NON cancellarli nel
        # merge, o un re-scan azzererebbe proposte pendenti già create/accettate.
        if key not in seen and row.type not in _SYNTHETIC_TYPES:
            db.delete(row)


# Issue create fuori dall'Inspector (azioni on-demand): sopravvivono al re-scan.
_SYNTHETIC_TYPES = {"provider_override", "missing_cover", "stray_rating"}


def _signature(member_ids) -> str:
    joined = ",".join(str(i) for i in sorted(member_ids))
    return hashlib.blake2b(joined.encode()).hexdigest()


def _merge_dups(db: Session, computed) -> None:
    old_groups = db.scalars(select(DupGroup)).all()
    decisions = {g.signature: (g.dismissed, g.keeper_overridden, g.keeper_file_id)
                 for g in old_groups}
    for g in old_groups:
        db.delete(g)  # la cascade all/delete-orphan rimuove anche i membri
    db.flush()
    for c in computed:
        sig = _signature(c.member_ids)
        dismissed, overridden, keeper = False, False, c.keeper_id
        if sig in decisions:
            d_dismissed, d_overridden, d_keeper = decisions[sig]
            if d_dismissed:
                dismissed = True
            elif d_overridden and d_keeper in c.member_ids:
                overridden, keeper = True, d_keeper
        grp = DupGroup(match_kind=c.match_kind, keeper_file_id=keeper,
                       keeper_overridden=overridden, dismissed=dismissed, signature=sig)
        db.add(grp)
        db.flush()
        for fid in c.member_ids:
            action = "keep" if (dismissed or fid == keeper) else "remove"
            db.add(DupMember(group_id=grp.id, file_id=fid, action=action))


def _summary(db: Session) -> AnalyzeSummary:
    by_sev = dict(db.execute(
        select(Issue.severity, func.count()).group_by(Issue.severity)
    ).all())
    dup_groups = db.scalar(select(func.count()).select_from(DupGroup)) or 0
    dup_files = db.scalar(select(func.count()).select_from(DupMember)) or 0
    return AnalyzeSummary(issues_total=sum(by_sev.values()), issues_by_severity=by_sev,
                          dup_groups=dup_groups, dup_files=dup_files)


def recompute(db: Session, on_progress=None) -> AnalyzeSummary:
    """Ricalcola Inspector+Dedup e fa il merge preservando le decisioni utente.

    Nota sul sequencing: `accepted`/`dismissed` su issue e `keeper_overridden`/`dismissed`
    sui gruppi sono una coda di lavoro pendente — consumata dal Plan (chunk 3) e applicata
    dall'Apply (chunk 4). Ri-eseguire `recompute` prima dell'Apply è sicuro: le decisioni
    vengono preservate per design. L'analisi va ri-eseguita *dopo* l'Apply perché solo
    allora i file saranno cambiati e le issue/gruppi aggiornati rifletteranno la realtà.
    """
    started = utcnow()
    files = db.scalars(select(AudioFile).where(AudioFile.status == "present")).all()
    if on_progress is not None:
        on_progress(0, 2, "inspecting")
    _merge_issues(db, inspect(files))
    if on_progress is not None:
        on_progress(1, 2, "deduping")
    _merge_dups(db, find_duplicates(files))
    db.commit()
    summary = _summary(db)
    summary.started_at = started
    summary.finished_at = utcnow()
    return summary
