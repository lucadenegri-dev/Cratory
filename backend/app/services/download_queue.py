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
    for track_id in track_ids:
        if db.get(Track, track_id) is None:
            skipped += 1
            continue
        busy = (db.query(DownloadQueueItem.id)
                .filter(DownloadQueueItem.track_id == track_id,
                        DownloadQueueItem.state.in_(ACTIVE_STATES)).first())
        if busy:
            skipped += 1
            continue
        db.add(DownloadQueueItem(track_id=track_id, kind=kind, payload=encoded,
                                 state="queued", position=position))
        position += 1
        added += 1
    db.commit()
    return added, skipped
