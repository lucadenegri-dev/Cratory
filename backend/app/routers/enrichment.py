"""Enrichment feature musicali (Fase B): BPM, key/Camelot, danceability.

Qui si ottengono le feature che servono al Set Builder e che lo streaming non da':
BPM/key (GetSongBPM), label/release/genere (MusicBrainz), genere/mood dai tag (Last.fm),
energia stimata. Job asincrono in background (services/enrichment_job): la UI lancia
e poi fa polling dello stato. Lo stesso job e' avviato automaticamente dopo l'import
di una playlist (router playlists).
"""

import logging

from fastapi import APIRouter, HTTPException, Query

from app.integrations.getsongbpm import (
    FeatureProviderNotConfigured,
    configured_provider_name,
    feature_provider_configured,
)
from app.services import enrichment_job

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/enrichment", tags=["enrichment"])


@router.get("/status")
def status():
    return {"configured": feature_provider_configured(), "provider": configured_provider_name()}


@router.post("/features")
def enrich(force: bool = Query(default=False)):
    """Avvia l'enrichment feature in background e ritorna subito. Seguire /features/status."""
    try:
        return enrichment_job.start_job(force=force)
    except FeatureProviderNotConfigured as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/features/status")
def features_status():
    return enrichment_job.job_state()
