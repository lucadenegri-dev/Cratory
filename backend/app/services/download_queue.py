"""Coda di acquisizione: operazioni sui dati, senza thread e senza rete.

Separato dal dispatcher (che decide QUANDO lavorare) e dal runner (che sa COME
scaricare) così si testa in memoria, senza slskd e senza aspettare.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from typing import NamedTuple

from sqlalchemy.orm import Session

from app.models import DownloadQueueItem, Track
from app.services import app_state

ACTIVE_STATES = ("queued", "running")

# Marcatore persistente del "giro corrente" (vedi `current_round_items`):
# l'id del primo item del giro in corso, o dell'ultimo concluso a coda ferma.
# Persistito (non solo in memoria) perche' l'app puo' riavviarsi con la coda
# ferma e la barra deve comunque raccontare l'ultimo giro, non azzerarsi.
ROUND_START_KEY = "downloads_queue_round_start_id"

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


def current_round_items(db: Session) -> list[DownloadQueueItem]:
    """Gli item del "giro" corrente — o dell'ultimo concluso, a coda ferma.

    Usata da `/api/downloads/status` per la barra globale, che deve
    raccontare solo il giro in corso (le tracce accodate da quando la coda,
    l'ultima volta, non aveva nulla di attivo), non l'intero storico ne' uno
    zero posticcio a coda ferma. Esclude sempre gli annullati, come
    `list_items` filtrato faceva prima dell'introduzione del giro.
    """
    start_id_raw = app_state.get_state(db, ROUND_START_KEY)
    query = db.query(DownloadQueueItem).filter(DownloadQueueItem.state != "cancelled")
    if start_id_raw is not None:
        query = query.filter(DownloadQueueItem.id >= int(start_id_raw))
    return query.order_by(DownloadQueueItem.position, DownloadQueueItem.id).all()


def _next_position(db: Session) -> int:
    last = (db.query(DownloadQueueItem)
            .order_by(DownloadQueueItem.position.desc()).first())
    return (last.position + 1) if last else 0


def _has_active_items(db: Session) -> bool:
    return (db.query(DownloadQueueItem.id)
            .filter(DownloadQueueItem.state.in_(ACTIVE_STATES))
            .first() is not None)


class EnqueueResult(NamedTuple):
    """Cos'e' successo a un lotto di accodamento.

    Tre esiti e non due perche' una richiesta con candidato esplicito su una
    traccia gia' in attesa non e' ne' "aggiunta" ne' "scartata": sostituisce.
    Chiamarla `added` mentirebbe (nessuna riga nuova), chiamarla `skipped`
    anche (la richiesta ha avuto effetto).
    """

    added: int
    skipped: int
    replaced: int = 0


def enqueue(db: Session, track_ids: list[int], kind: str = "soulseek_auto",
            payload: dict | None = None) -> EnqueueResult:
    """Accoda le tracce indicate. Ritorna (accodati, saltati, sostituiti).

    Si salta una traccia che ha gia' un item attivo (`queued`/`running`):
    senza questo, "accoda la playlist" due volte raddoppia la coda. Gli item
    conclusi (`done`/`cancelled`) non bloccano — e' il caso "riprova".
    Un `track_id` inesistente viene contato fra i saltati, non fa errore: un
    lotto non deve fallire per una traccia sparita nel frattempo.

    Eccezione alla deduplica: se questa chiamata porta un candidato scelto
    dall'utente (`payload`) e l'item attivo di quella traccia e' ancora in
    attesa (`queued`), il candidato ne SOSTITUISCE il carico invece di essere
    scartato. Il percorso e' reale: si accodano venti tracce in auto-pick, se
    ne apre una nel modal di ricerca, si sceglie a mano il file giusto — e la
    richiesta piu' specifica non deve perdere contro quella piu' generica
    arrivata prima. Su un item gia' `running` non si tocca nulla: il worker ha
    gia' preso il suo candidato e cambiarglielo sotto non avrebbe effetto; li'
    si salta, ed e' compito del chiamante dirlo all'utente.

    Se la coda non ha nulla di attivo (ne' `queued` ne' `running`) PRIMA di
    questa chiamata, e questa chiamata accoda davvero qualcosa, comincia un
    nuovo "giro" (vedi `current_round_items`): il marcatore del giro si
    sposta sul primo item appena inserito. Se invece la coda aveva gia'
    lavoro attivo, gli item di questo lotto si aggiungono al giro in corso
    (nessun aggiornamento del marcatore: lo status quo del giro basta, dato
    che gli id crescono e la query del giro e' "id >= marcatore").
    """
    added = skipped = replaced = 0
    position = _next_position(db)
    encoded = json.dumps(payload) if payload else None
    starting_new_round = not _has_active_items(db)

    # Due query in blocco al posto di due per traccia: un lotto di 300 non
    # deve fare ~600 round-trip. Gli esiti restano identici, calcolati poi
    # in memoria sul lotto.
    existing_ids = set()
    busy_ids = set()
    attesa_per_traccia: dict[int, DownloadQueueItem] = {}
    if track_ids:
        existing_ids = {row[0] for row in
                         db.query(Track.id).filter(Track.id.in_(track_ids)).all()}
        attivi = (db.query(DownloadQueueItem)
                  .filter(DownloadQueueItem.track_id.in_(track_ids),
                          DownloadQueueItem.state.in_(ACTIVE_STATES)).all())
        busy_ids = {i.track_id for i in attivi}
        attesa_per_traccia = {i.track_id: i for i in attivi if i.state == "queued"}

    seen_in_batch: set[int] = set()
    new_items: list[DownloadQueueItem] = []
    for track_id in track_ids:
        if track_id not in existing_ids:
            skipped += 1
            continue
        in_attesa = attesa_per_traccia.get(track_id)
        if payload is not None and in_attesa is not None and track_id not in seen_in_batch:
            # La scelta esplicita dell'utente prende il posto di quella
            # generica gia' in attesa, invece di essere scartata in silenzio.
            in_attesa.kind = kind
            in_attesa.payload = encoded
            seen_in_batch.add(track_id)
            replaced += 1
            continue
        if track_id in busy_ids or track_id in seen_in_batch:
            skipped += 1
            continue
        seen_in_batch.add(track_id)
        item = DownloadQueueItem(track_id=track_id, kind=kind, payload=encoded,
                                 state="queued", position=position)
        db.add(item)
        new_items.append(item)
        position += 1
        added += 1
    db.commit()
    if new_items and starting_new_round:
        app_state.set_state(db, ROUND_START_KEY, str(min(i.id for i in new_items)))
    return EnqueueResult(added, skipped, replaced)


def claim_next(db: Session, *, slskd_available: bool = True) -> DownloadQueueItem | None:
    """Prende il primo item in attesa e lo marca `running`. None se non c'e'
    lavoro lavorabile ora, o se un altro worker ha vinto la gara.

    `slskd_available=False` esclude dalla ricerca gli item che dipendono da
    slskd per scaricare (tutti tranne `kind="soundcloud"`): il filtro e' nella
    query stessa, quindi un item cosi' escluso non viene mai marcato
    `running` ne' toccato in alcun modo — resta `queued`, intatto, finche'
    slskd non torna disponibile. E' il chiamante (il dispatcher, che decide
    QUANDO lavorare) a calcolare il flag; qui e' solo un filtro sui dati, cosi'
    il modulo resta testabile senza slskd vero (vedi il docstring in cima al
    file).
    """
    with _claim_lock:
        query = db.query(DownloadQueueItem).filter(DownloadQueueItem.state == "queued")
        if not slskd_available:
            query = query.filter(DownloadQueueItem.kind == "soundcloud")
        candidate = (query
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


def requeue(db: Session, item_id: int) -> bool:
    """Rimette in attesa un item `running` senza contarlo come fallito.

    Serve quando l'ostacolo non riguarda la traccia ma l'infrastruttura (slskd
    irraggiungibile): l'item torna `queued` intatto e nessun esito viene
    scritto sulla traccia, cosi' il tentativo puo' essere rifatto identico
    quando il daemon torna. `attempts` viene riportato indietro perche'
    `claim_next` lo aveva gia' incrementato: un daemon spento per un'ora non
    deve gonfiare il contatore dei tentativi di decine di unita' mai avvenute.

    False se nel frattempo l'item e' stato annullato o concluso da un'altra
    sessione: come `finish`, un item annullato dall'utente non deve resuscitare.
    """
    updated = (db.query(DownloadQueueItem)
               .filter(DownloadQueueItem.id == item_id,
                       DownloadQueueItem.state == "running")
               .update({"state": "queued", "started_at": None, "phase": None,
                        "bytes_done": None, "bytes_total": None,
                        "attempts": DownloadQueueItem.attempts - 1},
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
