from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.http_errors import api_error
from app.db import get_db
from app.models import Track
from app.repositories import all_playable_tracks, get_track
from app.schemas import TransitionCandidateOut, TransitionScoreOut
from app.serializers import track_out
from app.services.app_state import get_language
from app.services.scoring import classify_transition, score_transition

router = APIRouter(prefix="/api/transitions", tags=["transitions"])


def _score_out(from_track: Track, to_track: Track, lang: str = "it") -> TransitionScoreOut:
    ts = score_transition(from_track, to_track, lang)
    # Score gia' calcolato: classify_transition lo riusa invece di ricomputarlo
    # (il ranking chiama _score_out per OGNI traccia della libreria).
    cls = classify_transition(from_track, to_track, lang, score=ts.score)
    return TransitionScoreOut(
        score=ts.score, technical_reasons=ts.technical_reasons, warnings=ts.warnings,
        classification=cls.label, classification_reason=cls.reason,
    )


def _ranked(db: Session, track_id: int, *, incoming: bool, limit: int,
            lens: str | None = None) -> list[TransitionCandidateOut]:
    anchor = get_track(db, track_id)
    if anchor is None:
        raise api_error(404, "track_not_found", "Track not found")
    lang = get_language(db)
    results: list[tuple[int, Track, TransitionScoreOut]] = []
    for other in all_playable_tracks(db):
        if other.id == anchor.id:
            continue
        out = _score_out(other, anchor, lang) if incoming else _score_out(anchor, other, lang)
        # La lente ordina DENTRO una classe (sicura/reset/azzardo): così i reset e gli
        # azzardi — che hanno score più basso — emergono invece di restare sepolti.
        if lens and out.classification != lens:
            continue
        results.append((out.score, other, out))
    results.sort(key=lambda item: item[0], reverse=True)
    return [TransitionCandidateOut(track=track_out(t), score=s) for _, t, s in results[:limit]]


_LENSES = {"technically_safe", "good_reset", "creative_risk"}


@router.get("/after/{track_id}", response_model=list[TransitionCandidateOut])
def transitions_after(track_id: int, limit: int = Query(default=20, le=100),
                      lens: str | None = Query(default=None), db: Session = Depends(get_db)):
    """Cosa posso mettere dopo questa traccia. `lens` opzionale: filtra per classe."""
    return _ranked(db, track_id, incoming=False, limit=limit,
                   lens=lens if lens in _LENSES else None)


@router.get("/before/{track_id}", response_model=list[TransitionCandidateOut])
def transitions_before(track_id: int, limit: int = Query(default=20, le=100),
                       lens: str | None = Query(default=None), db: Session = Depends(get_db)):
    """Cosa posso mettere prima di questa traccia. `lens` opzionale: filtra per classe."""
    return _ranked(db, track_id, incoming=True, limit=limit,
                   lens=lens if lens in _LENSES else None)


# POST /score rimosso (2026-07-12): documentato ma mai chiamato dalla UI ne'
# da script; il ranking sopra copre il caso d'uso reale.
