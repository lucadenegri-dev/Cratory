"""Router ANALYSIS: analisi BPM/key in-app (Essentia), divergenze e apply.

Il job scrive solo analysis_*; l'apply e' l'unico ponte verso i campi canonici.
Gerarchia fonti: manual > rekordbox > cratory (vedi services/audio_analysis).
L'import Rekordbox resta in routers/rekordbox."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.http_errors import api_error
from app.db import get_db
from app.integrations import essentia_engine
from app.models import Track
from app.schemas import (AnalysisApplyIn, AnalysisApplyOut, AnalysisDismissIn,
                         AnalysisDismissOut, AnalysisDivergenceOut,
                         AnalysisJobStatus, AnalysisOverviewOut, AnalysisStartIn)
from app.services import audio_analysis_job
from app.services.audio_analysis import (apply_analysis, dismiss_divergence,
                                         divergence_row, open_divergence)

router = APIRouter(prefix="/api/analysis", tags=["analysis"])


def _owned(db: Session) -> list[Track]:
    return list(db.scalars(select(Track).where(Track.has_local_file.is_(True))).all())


@router.get("/overview", response_model=AnalysisOverviewOut)
def overview(db: Session = Depends(get_db)):
    # Conteggi in Python su una sola query: app mono-utente, libreria di migliaia
    # di righe, piu' leggibile di otto aggregate SQL separate.
    owned = _owned(db)

    def by_source(attr: str) -> dict[str, int]:
        out = {"manual": 0, "rekordbox": 0, "cratory": 0}
        for t in owned:
            s = getattr(t, attr)
            if s in out:
                out[s] += 1
        return out

    return AnalysisOverviewOut(
        owned=len(owned),
        ready_for_set=sum(1 for t in owned if t.status == "ready_for_set"),
        missing_bpm=sum(1 for t in owned if t.bpm is None),
        missing_key=sum(1 for t in owned if not t.camelot_key),
        bpm_by_source=by_source("bpm_source"),
        key_by_source=by_source("key_source"),
        analyzed=sum(1 for t in owned if t.analyzed_at is not None),
        divergent=sum(1 for t in owned if open_divergence(t)),
        rekordbox_pending=sum(1 for t in owned if t.bpm is None or not t.camelot_key),
    )


@router.post("/start", response_model=AnalysisJobStatus, status_code=202)
def start(payload: AnalysisStartIn):
    if not essentia_engine.is_available():
        raise api_error(503, "analysis_engine_unavailable",
                        "Essentia not installed: install the pinned version from backend/requirements.txt.")
    if audio_analysis_job.is_running():
        raise api_error(409, "analysis_already_running", "Analysis job already running.")
    return audio_analysis_job.start_job(scope=payload.scope, track_ids=payload.track_ids)


@router.get("/status", response_model=AnalysisJobStatus)
def status():
    return audio_analysis_job.job_state()


@router.get("/divergences", response_model=list[AnalysisDivergenceOut])
def divergences(db: Session = Depends(get_db)):
    return [divergence_row(t) for t in _owned(db) if open_divergence(t)]


@router.post("/apply", response_model=AnalysisApplyOut)
def apply(payload: AnalysisApplyIn, db: Session = Depends(get_db)):
    """Applica i valori analizzati. track_ids = scelta esplicita su righe
    precise; mode='divergent' = tutte le divergenze APERTE (le scartate restano
    fuori); mode='all' = tutte le analizzate, scartate comprese, e richiede
    force=true come conferma.

    Solo `track_ids` scavalca la gerarchia delle fonti: la riga della lista
    divergenze mostra da dove viene il valore, quindi chi la sceglie sa cosa
    sta sostituendo. Le due modalita' in blocco no — riempiono i vuoti e
    riscrivono i valori gia' 'cratory', ma non declassano Rekordbox ne' una
    correzione manuale (regola 2). Senza questa distinzione un click
    rimpiazzava un import Rekordbox appena fatto con le stime dell'analisi.
    Quelle tracce restano nella lista divergenze, applicabili una per una."""
    if payload.mode == "all" and not payload.force:
        raise api_error(422, "analysis_force_required",
                        "mode='all' rewrites every analyzed track: pass force=true.")
    if not payload.track_ids and payload.mode is None:
        raise api_error(422, "analysis_apply_empty", "Provide track_ids or mode.")
    owned = _owned(db)
    if payload.track_ids:
        ids = set(payload.track_ids)
        targets = [t for t in owned if t.id in ids]
    elif payload.mode == "divergent":
        targets = [t for t in owned if open_divergence(t)]
    else:  # mode == "all"
        targets = [t for t in owned if t.analyzed_at is not None]
    per_traccia = bool(payload.track_ids)
    applied = sum(1 for t in targets
                  if apply_analysis(t, respect_source=not per_traccia))
    db.commit()
    return AnalysisApplyOut(applied=applied, skipped=len(targets) - applied)


@router.post("/dismiss", response_model=AnalysisDismissOut)
def dismiss(payload: AnalysisDismissIn, db: Session = Depends(get_db)):
    """Scarta le divergenze: la coppia analizzata e la coppia canonica vengono
    fotografate insieme; la divergenza resta nascosta finche' ENTRAMBE
    coincidono ancora con lo snapshot, e riappare se una nuova analisi o un
    cambio del canonico (PATCH, import Rekordbox) altera anche solo un lato."""
    if not payload.track_ids:
        raise api_error(422, "analysis_dismiss_empty", "Provide track_ids.")
    ids = set(payload.track_ids)
    targets = [t for t in _owned(db) if t.id in ids]
    for t in targets:
        dismiss_divergence(t)
    db.commit()
    return AnalysisDismissOut(dismissed=len(targets))
