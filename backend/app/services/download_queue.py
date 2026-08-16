"""Coda di acquisizione: operazioni sui dati, senza thread e senza rete.

Separato dal dispatcher (che decide QUANDO lavorare) e dal runner (che sa COME
scaricare) così si testa in memoria, senza slskd e senza aspettare.
"""
from __future__ import annotations

import json

from sqlalchemy.orm import Session

from app.models import DownloadQueueItem, Track

ACTIVE_STATES = ("queued", "running")


def list_items(db: Session) -> list[DownloadQueueItem]:
    return (db.query(DownloadQueueItem)
            .order_by(DownloadQueueItem.position, DownloadQueueItem.id).all())


def _next_position(db: Session) -> int:
    last = (db.query(DownloadQueueItem)
            .order_by(DownloadQueueItem.position.desc()).first())
    return (last.position + 1) if last else 0


def enqueue(db: Session, track_ids: list[int], kind: str = "soulseek_auto",
            payload: dict | None = None) -> tuple[int, int]:
    """Accoda le tracce indicate. Ritorna (accodati, saltati).

    Si salta una traccia che ha gia' un item attivo (`queued`/`running`):
    senza questo, "accoda la playlist" due volte raddoppia la coda. Gli item
    conclusi (`done`/`cancelled`) non bloccano — e' il caso "riprova".
    Un `track_id` inesistente viene contato fra i saltati, non fa errore: un
    lotto non deve fallire per una traccia sparita nel frattempo.
    """
    added = skipped = 0
    position = _next_position(db)
    encoded = json.dumps(payload) if payload else None

    # Due query in blocco al posto di due per traccia: un lotto di 300 non
    # deve fare ~600 round-trip. Gli esiti restano identici, calcolati poi
    # in memoria sul lotto.
    existing_ids = set()
    busy_ids = set()
    if track_ids:
        existing_ids = {row[0] for row in
                         db.query(Track.id).filter(Track.id.in_(track_ids)).all()}
        busy_ids = {row[0] for row in
                    db.query(DownloadQueueItem.track_id)
                    .filter(DownloadQueueItem.track_id.in_(track_ids),
                            DownloadQueueItem.state.in_(ACTIVE_STATES)).all()}

    seen_in_batch: set[int] = set()
    for track_id in track_ids:
        if track_id not in existing_ids:
            skipped += 1
            continue
        if track_id in busy_ids or track_id in seen_in_batch:
            skipped += 1
            continue
        seen_in_batch.add(track_id)
        db.add(DownloadQueueItem(track_id=track_id, kind=kind, payload=encoded,
                                 state="queued", position=position))
        position += 1
        added += 1
    db.commit()
    return added, skipped
