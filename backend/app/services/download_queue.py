"""Coda di acquisizione: operazioni sui dati, senza thread e senza rete.

Separato dal dispatcher (che decide QUANDO lavorare) e dal runner (che sa COME
scaricare) così si testa in memoria, senza slskd e senza aspettare.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import DownloadQueueItem, Track

ACTIVE_STATES = ("queued", "running")

# La rivendicazione e' serializzata in-processo: l'app gira in un solo uvicorn,
# quindi un lock qui basta. L'UPDATE resta comunque condizionato a
# state='queued' come seconda cintura: con due processi il perdente si
# accorgerebbe di aver perso la gara invece di scaricare la stessa traccia.
_claim_lock = threading.Lock()


def _now() -> datetime:
    return datetime.now(timezone.utc)


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


def claim_next(db: Session) -> DownloadQueueItem | None:
    """Prende il primo item in attesa e lo marca `running`. None se non c'e'
    lavoro o se un altro worker ha vinto la gara."""
    with _claim_lock:
        candidate = (db.query(DownloadQueueItem)
                     .filter(DownloadQueueItem.state == "queued")
                     .order_by(DownloadQueueItem.position, DownloadQueueItem.id)
                     .first())
        if candidate is None:
            return None
        updated = (db.query(DownloadQueueItem)
                   .filter(DownloadQueueItem.id == candidate.id,
                           DownloadQueueItem.state == "queued")
                   .update({"state": "running", "started_at": _now(),
                            "attempts": DownloadQueueItem.attempts + 1},
                           synchronize_session=False))
        db.commit()
        if updated != 1:
            return None
        db.refresh(candidate)
        return candidate


def finish(db: Session, item_id: int, outcome: str, error: str | None = None) -> bool:
    """Conclude un item `running`. False se nel frattempo e' stato annullato
    (o e' gia' concluso) da un'altra sessione: senza questo controllo un
    worker ignaro dell'annullo dell'utente resuscita l'item a `done`."""
    # synchronize_session=False come le sorelle (cancel, cancel_all_queued,
    # clear_done, requeue_stale): il modulo non garantisce che un oggetto ORM
    # gia' in identity map rifletta lo stato appena scritto dall'UPDATE in
    # blocco. Chi deve rileggerlo dopo una mutazione fa un db.refresh(...)
    # esplicito, come gia' i chiamanti di cancel() in questo file.
    updated = (db.query(DownloadQueueItem)
               .filter(DownloadQueueItem.id == item_id,
                       DownloadQueueItem.state == "running")
               .update({"state": "done", "outcome": outcome, "error": error,
                        "phase": None, "finished_at": _now()},
                       synchronize_session=False))
    db.commit()
    return updated == 1


def cancel(db: Session, item_id: int) -> bool:
    """Annulla un item in attesa o in corso. False se e' gia' concluso."""
    updated = (db.query(DownloadQueueItem)
               .filter(DownloadQueueItem.id == item_id,
                       DownloadQueueItem.state.in_(ACTIVE_STATES))
               .update({"state": "cancelled", "finished_at": _now(), "phase": None},
                       synchronize_session=False))
    db.commit()
    return updated == 1


def cancel_all_queued(db: Session) -> int:
    updated = (db.query(DownloadQueueItem)
               .filter(DownloadQueueItem.state == "queued")
               .update({"state": "cancelled", "finished_at": _now()},
                       synchronize_session=False))
    db.commit()
    return updated


def move_to_top(db: Session, item_id: int) -> bool:
    item = db.get(DownloadQueueItem, item_id)
    if item is None or item.state != "queued":
        return False
    first = (db.query(DownloadQueueItem)
             .order_by(DownloadQueueItem.position).first())
    item.position = (first.position - 1) if first else 0
    db.commit()
    return True


def clear_done(db: Session) -> int:
    """Svuota lo storico delle concluse con successo o meno (`done`).
    Gli annullati restano: sono un gesto recente dell'utente."""
    removed = (db.query(DownloadQueueItem)
               .filter(DownloadQueueItem.state == "done")
               .delete(synchronize_session=False))
    db.commit()
    return removed


def requeue_stale(db: Session) -> int:
    """All'avvio: gli item rimasti `running` non hanno piu' un worker vivo."""
    updated = (db.query(DownloadQueueItem)
               .filter(DownloadQueueItem.state == "running")
               .update({"state": "queued", "started_at": None, "phase": None,
                        "bytes_done": None, "bytes_total": None},
                       synchronize_session=False))
    db.commit()
    return updated


def set_progress(db: Session, item_id: int, phase: str | None,
                 bytes_done: int | None = None,
                 bytes_total: int | None = None) -> None:
    item = db.get(DownloadQueueItem, item_id)
    if item is None:
        return
    item.phase = phase
    item.bytes_done = bytes_done
    item.bytes_total = bytes_total
    db.commit()


def is_cancelled(db: Session, item_id: int) -> bool:
    """Letto dal worker fra una fase e l'altra: l'annullo arriva da un'altra
    sessione, quindi si interroga il DB e non l'oggetto in memoria."""
    db.expire_all()
    state = (db.query(DownloadQueueItem.state)
             .filter(DownloadQueueItem.id == item_id).scalar())
    return state == "cancelled"
