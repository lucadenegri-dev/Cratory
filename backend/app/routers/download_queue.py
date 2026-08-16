"""HTTP per la coda di acquisizione. Nessuna logica di business qui."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core import runtime_settings
from app.core.http_errors import api_error
from app.db import get_db
from app.integrations.slskd import slskd_configured
from app.models import DownloadQueueItem, Track
from app.services import download_queue as queue
from app.services.download_dispatcher import active_count, breaker_state, fill
from app.services.track_label import track_label

router = APIRouter(prefix="/api/downloads/queue", tags=["downloads"])


class CandidateIn(BaseModel):
    username: str
    filename: str
    size: int | None = None
    bitrate: int | None = None
    length: int | None = None


# I tre soli modi di scaricare che il runner sa eseguire. Vincolati qui, non
# lasciati stringa libera: un `kind` arbitrario non finiva in errore, finiva
# sulla via slskd (il runner manda a yt-dlp solo "soundcloud" e tratta tutto
# il resto come Soulseek) — silenziosamente, e sbagliato.
QueueKind = Literal["soulseek_auto", "soulseek_chosen", "soundcloud"]


class EnqueueIn(BaseModel):
    track_ids: list[int]
    kind: QueueKind = "soulseek_auto"
    # Solo con esattamente un track_id: un candidato e' per definizione la
    # scelta su una traccia sola, con una lista sarebbe ambiguo.
    candidate: CandidateIn | None = None


class EnqueueOut(BaseModel):
    enqueued: int
    skipped: int
    # Item gia' in attesa il cui candidato e' stato sostituito da quello di
    # questa richiesta: ne' aggiunti ne' scartati (vedi `queue.EnqueueResult`).
    replaced: int = 0


class QueueItemOut(BaseModel):
    id: int
    track_id: int
    label: str
    kind: str
    state: str
    outcome: str | None = None
    phase: str | None = None
    bytes_done: int | None = None
    bytes_total: int | None = None
    attempts: int
    error: str | None = None
    position: int


class QueuePauseOut(BaseModel):
    """Lo stato dell'interruttore su slskd, per la testa della pagina /downloads.

    Senza, una coda in pausa e' indistinguibile da una coda lenta: item «in
    attesa» senza spiegazione, e nessun posto dove leggere che il daemon non
    risponde e si riproverà fra poco. `reason` e' un codice
    (`unreachable` | `repeated_failures`), tradotto dal frontend.
    """

    paused: bool
    reason: str | None = None
    retry_in_seconds: int | None = None


class QueueOut(BaseModel):
    slots: int
    active: int
    pause: QueuePauseOut
    items: list[QueueItemOut]


def _item_out(item: DownloadQueueItem, label: str) -> QueueItemOut:
    return QueueItemOut(
        id=item.id, track_id=item.track_id, label=label, kind=item.kind,
        state=item.state, outcome=item.outcome, phase=item.phase,
        bytes_done=item.bytes_done, bytes_total=item.bytes_total,
        attempts=item.attempts, error=item.error, position=item.position,
    )


@router.get("", response_model=QueueOut)
def read_queue(db: Session = Depends(get_db)):
    items = queue.list_items(db)
    labels = {t.id: track_label(t) for t in
              db.query(Track).filter(Track.id.in_([i.track_id for i in items])).all()} \
        if items else {}
    paused, reason, retry_in = breaker_state()
    return QueueOut(
        slots=runtime_settings.download_slots(),
        active=active_count(),
        pause=QueuePauseOut(paused=paused, reason=reason, retry_in_seconds=retry_in),
        items=[_item_out(i, labels.get(i.track_id, "?")) for i in items],
    )


@router.post("", response_model=EnqueueOut)
def enqueue(req: EnqueueIn, db: Session = Depends(get_db)):
    if req.candidate is not None and len(req.track_ids) != 1:
        raise api_error(422, "candidate_needs_one_track",
                        "Un candidato vale per una sola traccia.")
    kind = "soulseek_chosen" if req.candidate is not None else req.kind
    # Come i suoi fratelli in `routers/downloads.py`: senza slskd quegli item
    # non partiranno mai, e accodarli in silenzio riempie la coda di lavoro
    # morto. Non vale per `soundcloud`, che passa da yt-dlp e non da slskd.
    if kind != "soundcloud" and not slskd_configured():
        raise api_error(409, "slskd_not_configured",
                        "slskd not configured (SLSKD_URL/SLSKD_DOWNLOAD_DIR).")
    payload = req.candidate.model_dump() if req.candidate is not None else None
    esito = queue.enqueue(db, req.track_ids, kind=kind, payload=payload)
    if esito.added or esito.replaced:
        fill()
    return EnqueueOut(enqueued=esito.added, skipped=esito.skipped,
                      replaced=esito.replaced)


@router.delete("/done")
def clear_done(db: Session = Depends(get_db)):
    return {"removed": queue.clear_done(db)}


@router.post("/cancel-queued")
def cancel_queued(db: Session = Depends(get_db)):
    return {"cancelled": queue.cancel_all_queued(db)}


@router.delete("/{item_id}")
def cancel_item(item_id: int, db: Session = Depends(get_db)):
    if db.get(DownloadQueueItem, item_id) is None:
        raise api_error(404, "queue_item_not_found", "Queue item not found.")
    if not queue.cancel(db, item_id):
        raise api_error(409, "queue_item_not_active", "Item already finished.")
    return {"cancelled": True}


@router.post("/{item_id}/top")
def move_top(item_id: int, db: Session = Depends(get_db)):
    if db.get(DownloadQueueItem, item_id) is None:
        raise api_error(404, "queue_item_not_found", "Queue item not found.")
    if not queue.move_to_top(db, item_id):
        raise api_error(409, "queue_item_not_queued", "Only a waiting item can be moved.")
    return {"moved": True}
