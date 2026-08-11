"""Router DUPLICATES: lista gruppi + scelta keeper / dismiss. Sottile."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.organize.db import get_db
from app.organize.core.http_errors import api_error
from app.organize.models import AudioFile, DupGroup, DupMember
from app.organize.schemas import DupGroupRead, DupMemberRead, KeeperBody

router = APIRouter(prefix="/api/organize/duplicates", tags=["duplicates"])


def _group_read(db: Session, grp: DupGroup) -> DupGroupRead:
    rows = db.execute(
        select(DupMember, AudioFile)
        .join(AudioFile, DupMember.file_id == AudioFile.id)
        .where(DupMember.group_id == grp.id)
    ).all()
    members = [DupMemberRead(file_id=m.file_id, action=m.action, path=a.path, ext=a.ext,
                             bitrate=a.bitrate, duration_s=a.duration_s,
                             content_hash=a.content_hash) for m, a in rows]
    return DupGroupRead(id=grp.id, match_kind=grp.match_kind,
                        keeper_file_id=grp.keeper_file_id,
                        keeper_overridden=grp.keeper_overridden, dismissed=grp.dismissed,
                        members=members)


@router.get("", response_model=list[DupGroupRead])
def list_duplicates(db: Session = Depends(get_db)):
    return [_group_read(db, g) for g in db.scalars(select(DupGroup)).all()]


@router.post("/{group_id}/keeper", response_model=DupGroupRead)
def set_keeper(group_id: int, body: KeeperBody, db: Session = Depends(get_db)):
    grp = db.get(DupGroup, group_id)
    if grp is None:
        raise api_error(404, "dup_group_not_found", "Group not found")
    members = db.scalars(select(DupMember).where(DupMember.group_id == group_id)).all()
    if body.file_id not in {m.file_id for m in members}:
        raise api_error(400, "dup_file_not_member", "file_id is not a member of the group")
    grp.keeper_file_id = body.file_id
    grp.keeper_overridden = True
    grp.dismissed = False
    for m in members:
        m.action = "keep" if m.file_id == body.file_id else "remove"
    db.commit()
    return _group_read(db, grp)


@router.post("/{group_id}/dismiss", response_model=DupGroupRead)
def dismiss(group_id: int, db: Session = Depends(get_db)):
    grp = db.get(DupGroup, group_id)
    if grp is None:
        raise api_error(404, "dup_group_not_found", "Group not found")
    grp.dismissed = True
    for m in db.scalars(select(DupMember).where(DupMember.group_id == group_id)).all():
        m.action = "keep"
    db.commit()
    return _group_read(db, grp)
