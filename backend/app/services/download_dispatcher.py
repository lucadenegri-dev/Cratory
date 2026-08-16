"""Il pool: quanti item lavorare insieme, e quando ripescare.

Non sa cosa sia un download (quello e' `download_runner`) ne' come si scriva
sul DB (quello e' `download_queue`): decide solo l'occupazione degli slot, e
quando ha senso provarci — l'interruttore su slskd e il riaggancio periodico
qui sotto.
"""
from __future__ import annotations

import logging
import threading
import time

from app.core import runtime_settings
from app.db import SessionLocal
from app.integrations.slskd import slskd_configured
from app.services import download_queue as queue
from app.services.download_runner import SlskdUnreachable, run_item
from app.services.job_spawn import spawn

logger = logging.getLogger(__name__)

# Quanto resta aperto l'interruttore dopo un errore di connessione verso slskd,
# prima di riprovare. Abbastanza lungo da non martellare un daemon spento,
# abbastanza corto da non far aspettare l'utente che lo riaccende.
SLSKD_COOLDOWN = 60.0

# Ogni quanto il riaggancio periodico riprova a riempire gli slot. E' l'unica
# cosa che rimette in moto una coda ferma senza un gesto dell'utente: senza,
# una coda fermata da un daemon spento resterebbe ferma per sempre (il frontend
# spegne i pulsanti di download finche' /status dice `running`, quindi
# nemmeno un nuovo accodamento sarebbe possibile).
RETRY_INTERVAL = 30.0

_lock = threading.Lock()
_active = 0
# Scadenza dell'interruttore, sull'orologio monotono: finche' non e' passata,
# gli item che dipendono da slskd non vengono rivendicati. 0.0 = chiuso.
_slskd_blocked_until = 0.0

_retry_lock = threading.Lock()
_retry_stop = threading.Event()
_retry_thread: threading.Thread | None = None


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


def slskd_ready() -> bool:
    """Falso finche' l'interruttore e' aperto (raffreddamento in corso)."""
    with _lock:
        return time.monotonic() >= _slskd_blocked_until


def _trip_slskd_breaker() -> None:
    """Apre l'interruttore per `SLSKD_COOLDOWN` secondi.

    Una scadenza letta a ogni `claim_next`, invece di un flag da azzerare con
    un evento esplicito: cosi' l'interruttore si richiude da solo allo
    scadere, senza che nessuno debba accorgersi che il daemon e' tornato — il
    prossimo item lavorato e' la verifica.
    """
    global _slskd_blocked_until
    with _lock:
        _slskd_blocked_until = time.monotonic() + SLSKD_COOLDOWN
    logger.warning("slskd irraggiungibile: coda in pausa per %.0fs", SLSKD_COOLDOWN)


def _work(item_id: int) -> None:
    try:
        run_item(item_id)
    except SlskdUnreachable as exc:
        # L'item e' gia' tornato `queued` (lo fa il runner) e la traccia non ha
        # ricevuto esito: qui si apre l'interruttore, cosi' il pool smette di
        # rivendicare gli altri item che dipendono da slskd invece di bruciarli
        # tutti uno dopo l'altro contro un daemon spento.
        _trip_slskd_breaker()
        logger.info("Item %s rimesso in coda: %s", item_id, exc)
    except Exception:  # noqa: BLE001 — il runner non dovrebbe sollevare, ma uno
        logger.exception("Worker della coda esploso su item %s", item_id)
    finally:
        _release()
        fill()          # uno slot si e' liberato: ripesca


def fill() -> None:
    """Riempie gli slot liberi finche' c'e' lavoro in attesa lavorabile.

    Gli item che dipendono da slskd sono lavorabili solo se slskd e'
    configurato (URL e cartella di download) E l'interruttore e' chiuso.
    Quando non lo sono, `claim_next` li esclude a livello di query: non
    vengono mai marcati `running` ne' toccati in alcun modo — restano
    `queued`, intatti, invece di essere bruciati all'istante da `run_item`.
    Solo un item `kind="soundcloud"`, che non passa da slskd, puo' comunque
    partire. Entrambe le condizioni si rileggono a ogni iterazione, come gli
    slot.

    Chi rimette in moto una coda cosi' congelata: il riaggancio periodico
    (`start_retry_loop`), che richiama questa funzione a pool fermo. Senza di
    lui ne' la riconfigurazione a caldo ne' il daemon che torna basterebbero,
    perche' nessuno chiamerebbe piu' `fill()` — gli endpoint di download lo
    fanno solo su un nuovo accodamento, che il frontend impedisce finche'
    /status resta `running`.
    """
    while _reserve():
        db = SessionLocal()
        try:
            item = queue.claim_next(db, slskd_available=slskd_configured() and slskd_ready())
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


def _retry_loop() -> None:
    """Richiama `fill()` a intervalli regolari, ma solo a pool fermo.

    A pool non fermo non servirebbe: ogni worker richiama gia' `fill()` quando
    libera il suo slot. Su coda vuota e' innocuo — `fill()` riserva uno slot,
    non trova nulla da rivendicare e lo rilascia subito.
    """
    while not _retry_stop.wait(RETRY_INTERVAL):
        try:
            if active_count() == 0:
                fill()
        except Exception:  # noqa: BLE001 — un giro storto non deve uccidere il loop
            logger.exception("Riaggancio periodico della coda fallito")


def start_retry_loop() -> None:
    """Accende il riaggancio periodico, una volta sola.

    La guardia su `is_alive()` serve perche' `boot()` puo' essere chiamato piu'
    di una volta nello stesso processo: il reload di uvicorn e i test lo fanno,
    e due loop significherebbero due `fill()` concorrenti a ogni intervallo.
    """
    global _retry_thread
    with _retry_lock:
        if _retry_thread is not None and _retry_thread.is_alive():
            return
        _retry_stop.clear()
        _retry_thread = threading.Thread(target=_retry_loop, daemon=True,
                                         name="download-queue-retry")
        _retry_thread.start()


def stop_retry_loop(timeout: float = 5.0) -> None:
    """Spegne il riaggancio periodico e ne attende la fine.

    In produzione non serve (e' un thread daemon, muore col processo): esiste
    per i test, che non devono lasciare in volo un thread capace di rivendicare
    righe del DB condiviso dopo lo smontaggio del proprio monkeypatch.
    """
    global _retry_thread
    with _retry_lock:
        thread, _retry_thread = _retry_thread, None
    _retry_stop.set()
    if thread is not None:
        thread.join(timeout=timeout)


def boot() -> None:
    """All'avvio: gli item rimasti `running` non hanno piu' un worker, tornano
    in coda; poi si riparte e si accende il riaggancio periodico."""
    db = SessionLocal()
    try:
        recovered = queue.requeue_stale(db)
    finally:
        db.close()
    if recovered:
        logger.info("Coda download: %s item ripresi dopo il riavvio", recovered)
    fill()
    start_retry_loop()
