"""HTTP per la coda di acquisizione. Nessuna logica di business qui."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core import runtime_settings
from app.core.http_errors import api_error
from app.db import get_db
from app.models import DownloadQueueItem, Track
from app.services import download_queue as queue
from app.services.download_dispatcher import active_count, fill
from app.services.track_label import track_label

router = APIRouter(prefix="/api/downloads/queue", tags=["downloads"])


class CandidateIn(BaseModel):
    username: str
    filename: str
    size: int | None = None
    bitrate: int | None = None
    length: int | None = None


class EnqueueIn(BaseModel):
    track_ids: list[int]
    kind: str = "soulseek_auto"
    # Solo con esattamente un track_id: un candidato e' per definizione la
    # scelta su una traccia sola, con una lista sarebbe ambiguo.
    candidate: CandidateIn | None = None


class EnqueueOut(BaseModel):
    enqueued: int
    skipped: int


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


class QueueOut(BaseModel):
    slots: int
    active: int
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
    return QueueOut(
        slots=runtime_settings.download_slots(),
        active=active_count(),
        items=[_item_out(i, labels.get(i.track_id, "?")) for i in items],
    )


@router.post("", response_model=EnqueueOut)
def enqueue(req: EnqueueIn, db: Session = Depends(get_db)):
    if req.candidate is not None and len(req.track_ids) != 1:
        raise api_error(422, "candidate_needs_one_track",
                        "Un candidato vale per una sola traccia.")
    kind = "soulseek_chosen" if req.candidate is not None else req.kind
    payload = req.candidate.model_dump() if req.candidate is not None else None
    added, skipped = queue.enqueue(db, req.track_ids, kind=kind, payload=payload)
    if added:
        fill()
    return EnqueueOut(enqueued=added, skipped=skipped)


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
