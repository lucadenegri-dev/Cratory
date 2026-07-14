"""Orchestrazione del controllo integrita': itera i file present, salta gli
invariati gia' controllati (cache su content_hash), delega il decode a un
checker iniettabile. L'I/O ffmpeg vive nell'adapter integrations/integrity."""

from sqlalchemy import select

from app.integrations.integrity import check_file
from app.models import AudioFile


def run_integrity(db, *, checker=None, force: bool = False, on_progress=None) -> dict:
    """Controlla i file present. checker(path) -> IntegrityResult (iniettabile
    per i test). Ritorna i contatori {scanned, checked, skipped, corrupt}."""
    checker = checker or check_file
    files = db.scalars(
        select(AudioFile).where(AudioFile.status == "present")).all()
    total = len(files)
    res = {"scanned": total, "checked": 0, "skipped": 0, "corrupt": 0}
    for idx, f in enumerate(files):
        if on_progress is not None:
            on_progress(idx, total, "checking")
        if not force and f.content_hash is not None \
                and f.integrity_checked_hash == f.content_hash:
            res["skipped"] += 1
            continue
        result = checker(f.path)
        f.integrity_ok = result.ok
        f.integrity_detail = result.detail
        f.integrity_checked_hash = f.content_hash
        res["checked"] += 1
        if not result.ok:
            res["corrupt"] += 1
        db.commit()
    if on_progress is not None:
        on_progress(total, total, "checking")
    return res
