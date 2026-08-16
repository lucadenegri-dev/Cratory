"""Il pool: quanti item lavorare insieme, e quando ripescare.

Non sa cosa sia un download (quello e' `download_runner`) ne' come si scriva
sul DB (quello e' `download_queue`): decide solo l'occupazione degli slot.
"""
from __future__ import annotations

import logging
import threading

from app.core import runtime_settings
from app.db import SessionLocal
from app.services import download_queue as queue
from app.services.download_runner import run_item
from app.services.job_spawn import spawn

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_active = 0


def active_count() -> int:
    with _lock:
        return _active


def _reserve() -> bool:
    """Occupa uno slot se ce n'e' uno libero. Il numero di slot si rilegge qui,
    a ogni tentativo: cambiarlo dalle impostazioni ha effetto senza riavvio."""
    global _active
    with _lock:
        if _active >= runtime_settings.download_slots():
            return False
        _active += 1
        return True


def _release() -> None:
    global _active
    with _lock:
        _active -= 1


def _work(item_id: int) -> None:
    try:
        run_item(item_id)
    except Exception:  # noqa: BLE001 — il runner non dovrebbe sollevare, ma uno
        logger.exception("Worker della coda esploso su item %s", item_id)
    finally:
        _release()
        fill()          # uno slot si e' liberato: ripesca


def fill() -> None:
    """Riempie gli slot liberi finche' c'e' lavoro in attesa."""
    while _reserve():
        db = SessionLocal()
        try:
            item = queue.claim_next(db)
        except Exception:
            # Uno slot appena riservato non deve restare occupato per sempre
            # se la rivendicazione esplode (DB non raggiungibile, ecc.): senza
            # questo rilascio la capacita' del pool si erode ad ogni errore,
            # fino a bloccarlo per il resto del processo.
            _release()
            raise
        finally:
            db.close()
        if item is None:
            _release()
            return
        spawn(lambda item_id=item.id: _work(item_id))


def boot() -> None:
    """All'avvio: gli item rimasti `running` non hanno piu' un worker, tornano
    in coda; poi si riparte."""
    db = SessionLocal()
    try:
        recovered = queue.requeue_stale(db)
    finally:
        db.close()
    if recovered:
        logger.info("Coda download: %s item ripresi dopo il riavvio", recovered)
    fill()
