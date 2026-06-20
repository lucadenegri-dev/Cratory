"""Router etichette discografiche.

- panoramica delle etichette presenti in libreria (aggregati deterministici),
- backfill della label dall'album Spotify completo (la label non e' nell'album
  semplificato annidato nelle tracce di playlist/liked).
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.integrations.spotify import SpotifyError, SpotifyWebClient
from app.routers.playlists import _http_error
from app.schemas import LabelBackfillReport, LabelStatsOut
from app.services.labels import backfill_labels, labels_overview

router = APIRouter(prefix="/api/labels", tags=["labels"])


@router.get("", response_model=list[LabelStatsOut])
def list_labels(db: Session = Depends(get_db)):
    return [LabelStatsOut(**row) for row in labels_overview(db)]


@router.post("/backfill", response_model=LabelBackfillReport)
def backfill(db: Session = Depends(get_db)):
    """Recupera l'etichetta dall'album Spotify per le tracce che ne sono prive.

    Bounded e ripetibile: elabora un lotto per chiamata (budget di lookup) con una
    piccola pausa anti rate-limit. Se ``remaining`` > 0, rilanciare per continuare.
    """
    client = SpotifyWebClient(db)
    try:
        report = backfill_labels(db, client, max_lookups=60, pause=0.25)
    except SpotifyError as exc:
        raise _http_error(exc) from exc
    return LabelBackfillReport(**report)
