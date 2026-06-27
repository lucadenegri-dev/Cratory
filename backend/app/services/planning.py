"""Orchestratore Plan/Conflict: settings + costruzione/lettura del piano."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ScanRoot, Settings, utcnow

DEFAULT_NAMING = "{artist} - {title}"
DEFAULT_FOLDER = "{genre}/{artist}"


def get_settings(db: Session) -> Settings:
    s = db.get(Settings, 1)
    if s is None:
        s = Settings(id=1, naming_template=DEFAULT_NAMING, folder_template=DEFAULT_FOLDER)
        db.add(s)
        db.commit()
        db.refresh(s)
    return s


def update_settings(db: Session, naming_template=None, folder_template=None) -> Settings:
    s = get_settings(db)
    if naming_template is not None:
        s.naming_template = naming_template
    if folder_template is not None:
        s.folder_template = folder_template
    s.updated_at = utcnow()
    db.commit()
    db.refresh(s)
    return s


def set_root_target(db: Session, root_id: int, target_root) -> ScanRoot | None:
    root = db.get(ScanRoot, root_id)
    if root is None:
        return None
    root.target_root = target_root
    db.commit()
    db.refresh(root)
    return root


def root_targets(db: Session) -> dict[int, str]:
    return {r.id: (r.target_root or r.path) for r in db.scalars(select(ScanRoot)).all()}
