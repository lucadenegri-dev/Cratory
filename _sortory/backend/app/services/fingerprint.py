"""Job di fingerprinting: per ogni file presente senza mbid, interroga AcoustID
e salva il miglior candidato sopra soglia in AudioFile.mbid. Il client è
iniettabile → test senza fpcalc né rete."""

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AudioFile

logger = logging.getLogger(__name__)


def fingerprint_one(file, client, *, threshold: float = 0.5) -> str | None:
    """Fingerprint di un singolo file: imposta file.mbid (senza commit) e lo
    ritorna se c'è un candidato sopra soglia; None altrimenti. Non solleva."""
    from app.integrations.acoustid import AcoustIDError
    try:
        candidates = client.identify(file.path)
    except AcoustIDError as exc:
        logger.warning("Fingerprint %s fallito: %s", file.path, exc)
        return None
    if not candidates:
        return None
    best = candidates[0]
    if best.get("score", 0) >= threshold and best.get("mbid"):
        file.mbid = best["mbid"]
        return best["mbid"]
    return None


def fingerprint_files(db: Session, client, *, threshold: float = 0.5) -> dict:
    files = db.scalars(
        select(AudioFile).where(AudioFile.status == "present", AudioFile.mbid.is_(None))
    ).all()
    identified = below = not_found = errors = 0
    from app.integrations.acoustid import AcoustIDError
    for f in files:
        try:
            candidates = client.identify(f.path)
        except AcoustIDError as exc:
            errors += 1
            logger.warning("Fingerprint %s fallito: %s", f.path, exc)
            continue
        if not candidates:
            not_found += 1
            continue
        best = candidates[0]
        if best.get("score", 0) >= threshold and best.get("mbid"):
            f.mbid = best["mbid"]
            identified += 1
        else:
            below += 1
    db.commit()
    return {"identified": identified, "below_threshold": below,
            "not_found": not_found, "errors": errors, "total": len(files)}
