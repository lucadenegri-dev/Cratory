"""Esecuzione di un singolo item della coda: cosa vuol dire "scaricare".

Il dispatcher decide quando, questo modulo sa come. L'esito viene scritto sia
sull'item sia sulla Track: la coda dice come sta andando, la traccia com'e'
finita — e i tab della wishlist leggono la traccia.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path

from app.core import runtime_settings
from app.db import SessionLocal
from app.integrations.local_files import read_audio_quality, read_tags
from app.integrations.slskd import (
    SlskdFile, classify_transfer_state, get_slskd_client, slskd_unreachable,
)
from app.integrations.soundcloud_audio import SoundCloudAudioError, download_track_audio
from app.models import DownloadQueueItem, Track
from app.services import download_queue as queue
from app.services.acquisition import attach_local_file
from app.services.soulseek_select import auto_pick_candidates, search_candidates

logger = logging.getLogger(__name__)


class SlskdUnreachable(Exception):
    """Il daemon slskd non risponde: l'item NON e' fallito, e' stato rimesso in
    attesa (`queued`) e la traccia non ha ricevuto alcun esito.

    E' l'unica eccezione che `run_item` lascia uscire, ed e' un segnale
    indirizzato al dispatcher: chi la riceve apre l'interruttore del pool,
    cosi' gli altri item che dipendono da slskd non vengono nemmeno
    rivendicati finche' il daemon non torna. Vive qui e non nel client
    (`integrations/slskd.py`) perche' non descrive un errore di quel client —
    lo classifica: dice cosa ne fa la coda.
    """


def _candidate_from_payload(payload: dict | None) -> SlskdFile | None:
    if not payload:
        return None
    return SlskdFile(username=payload["username"], filename=payload["filename"],
                     size=payload.get("size"), bitrate=payload.get("bitrate"),
                     length=payload.get("length"), has_free_slot=True,
                     queue_length=None)


# Salto minimo, in byte, perche' valga la pena riscrivere il progresso quando
# la dimensione totale non e' nota (senza totale non c'e' una percentuale su
# cui ragionare). Un mega: sotto, nessuno se ne accorgerebbe.
_PROGRESS_MIN_STEP_BYTES = 1024 * 1024


def _progress_writer(db, item_id: int):
    """Ritorna una `write(fase, byte_fatti, byte_totali)` che scrive sull'item
    solo quando cambia qualcosa di visibile.

    Il ciclo di poll gira ogni `POLL_INTERVAL` secondi, per ogni worker: girare
    la scrittura pari pari sul DB significherebbe una commit ogni due secondi a
    testa per tutta la durata di un trasferimento (mezz'ora, sui lossless da
    peer lenti), quasi sempre per ridisegnare la stessa identica barra. La
    barra si muove per punti percentuali interi, quindi si scrive solo quando
    la percentuale mostrata cambierebbe davvero — al massimo cento scritture
    per download, invece di novecento.
    """
    last: dict = {"phase": None, "done": None, "total": None}

    def significativo(nuovo: int | None, totale: int | None) -> bool:
        precedente = last["done"]
        if nuovo is None:
            return precedente is not None
        if precedente is None:
            return True
        if totale:
            return nuovo * 100 // totale != precedente * 100 // totale
        return abs(nuovo - precedente) >= _PROGRESS_MIN_STEP_BYTES

    def write(phase: str | None, bytes_done: int | None = None,
              bytes_total: int | None = None) -> None:
        if (phase == last["phase"] and bytes_total == last["total"]
                and not significativo(bytes_done, bytes_total)):
            return
        queue.set_progress(db, item_id, phase, bytes_done, bytes_total)
        last.update(phase=phase, done=bytes_done, total=bytes_total)

    return write


def _run_soulseek(db, item: DownloadQueueItem, track: Track,
                  chosen: SlskdFile | None) -> tuple[str, str | None, str | None]:
    """Ritorna (esito, motivo, path_dubbio), come il job storico.

    `should_cancel` viene interrogato dal ciclo di attesa del transfer: senza,
    annullare una traccia gia' in corso non avrebbe effetto fino alla fine del
    trasferimento — che su un lossless da un peer lento sono minuti.

    `on_progress` e' l'altra meta': senza, la fase resterebbe "searching" per
    tutta la durata del trasferimento e la barra per-traccia non avrebbe mai un
    numero da mostrare.
    """
    client = get_slskd_client()
    try:
        download_dir = runtime_settings.slskd_download_dir()
        return _process_item(db, client, download_dir, track, chosen,
                             should_cancel=lambda: queue.is_cancelled(db, item.id),
                             on_progress=_progress_writer(db, item.id))
    finally:
        client.close()


def _run_soundcloud(db, item: DownloadQueueItem, track: Track,
                    chosen: SlskdFile | None) -> tuple[str, str | None, str | None]:
    # yt-dlp non riporta avanzamento a Cratory: la fase si puo' dire, i byte no.
    # Meglio "scarico" senza barra che "Ricerca..." per tutta la durata.
    queue.set_progress(db, item.id, "downloading")
    try:
        path = download_track_audio(track.url, runtime_settings.slskd_download_dir())
    except SoundCloudAudioError as exc:
        return "failed", str(exc), None
    quality = read_audio_quality(path)
    attach_local_file(db, track, path=path, fmt=quality["format"],
                      bitrate=quality["bitrate"])
    return "downloaded", None, None


def run_item(item_id: int) -> tuple[str, str | None] | None:
    """Esegue un item. Un fallimento chiude l'item, non il pool.

    Ritorna `(esito, motivo)` se l'item e' stato concluso, `None` se non c'era
    nulla da fare (annullato, gia' concluso). Non serve al runner: lo legge il
    dispatcher per contare i fallimenti consecutivi e aprire l'interruttore
    quando sono troppi e sempre uguali — un daemon che sbaglia sempre allo
    stesso modo non e' un problema delle singole tracce.

    Unica eccezione che esce di qui: `SlskdUnreachable`, quando l'errore non
    riguarda la traccia ma il daemon che non risponde. In quel caso l'item e'
    gia' tornato `queued` e la traccia non ha ricevuto esito: e' il dispatcher
    a raccogliere il segnale e a mettere in pausa il pool.
    """
    db = SessionLocal()
    try:
        item = db.get(DownloadQueueItem, item_id)
        if item is None or item.state != "running":
            return None  # annullato prima di partire, o gia' concluso
        track = db.get(Track, item.track_id)
        if track is None:
            queue.finish(db, item_id, "failed", "track_not_found")
            return "failed", "track_not_found"
        queue.set_progress(db, item_id, "searching")
        try:
            if item.kind == "soundcloud":
                outcome, reason, path = _run_soundcloud(db, item, track, None)
            else:
                chosen = _candidate_from_payload(item.payload_dict())
                outcome, reason, path = _run_soulseek(db, item, track, chosen)
        except Exception as exc:  # noqa: BLE001 — un item rotto non ferma la coda
            db.rollback()
            if slskd_unreachable(exc):
                # Non e' colpa della traccia: il daemon e' spento o irraggiungibile.
                # L'item torna in attesa, identico, e la traccia NON riceve un
                # `last_download_outcome="failed"` con dentro un "Connection
                # refused" — un daemon giu' non deve bruciare la coda.
                queue.requeue(db, item_id)
                logger.warning("Item di coda %s rinviato, slskd irraggiungibile: %s",
                               item_id, exc)
                raise SlskdUnreachable(str(exc)) from exc
            logger.exception("Item di coda %s fallito", item_id)
            outcome, reason, path = "failed", str(exc) or "error", None
        # Annullato mentre lavorava: l'item resta `cancelled` e la traccia NON
        # riceve un esito — non e' andata male, e' stata fermata.
        if outcome == "cancelled" or queue.is_cancelled(db, item_id):
            return None
        # L'esito va anche sulla traccia: e' la fonte dei tab della wishlist.
        track = db.get(Track, item.track_id)
        if track is not None:
            track.last_download_outcome = outcome
            track.last_download_reason = reason
            track.last_download_path = path
            db.commit()
        queue.finish(db, item_id, outcome, reason)
        return outcome, reason
    finally:
        db.close()


# --- Logica di trasferimento assorbita dal job monolitico ------------------
#
# Copiata alla lettera dal job storico, ora eliminato. Le uniche differenze
# sono le tre modifiche per far arrivare l'annullo fin dentro il ciclo di
# attesa: il parametro `should_cancel`, inoltrato da `_process_item` a
# `_attempt_download` a `_wait_for_download`, e l'esito "cancelled" che risale
# senza essere scavalcato dal fallback su un altro utente. Il resto — cascata
# di varianti, soglie di confidenza, guardia sulla durata, timeout — e'
# identico: e' il codice coperto da tests/test_download_runner_soulseek.py,
# che sono i test di regressione del job originale.

POLL_INTERVAL = 2.0
STALL_TIMEOUT = 60.0           # transfer InProgress ma bytesTransferred fermo da tanto: ci si arrende
QUEUE_PATIENCE = 45.0          # oltre questo, se resta solo in coda, si prova un altro utente
HARD_TIMEOUT = 1800.0          # tetto assoluto anche se il progresso avanza (lossless da peer lenti)
MAX_ATTEMPTS = 4               # quanti candidati (utenti diversi) provare per traccia
SEARCH_MAX_WAIT = 15.0         # il job e' in background: attesa piena per variante, non il budget ridotto di /candidates


def _coda_condivisa(locale: Path, remoto: tuple[str, ...]) -> int:
    """Quanti componenti finali di percorso hanno in comune il file su disco e
    il percorso remoto del candidato. Confronto senza maiuscole/minuscole: i
    peer Soulseek sono spesso Windows."""
    parti_locali = [p.lower() for p in locale.parts]
    parti_remote = [p.lower() for p in remoto]
    condivisi = 0
    for a, b in zip(reversed(parti_locali), reversed(parti_remote)):
        if a != b:
            break
        condivisi += 1
    return condivisi


def _resolve_local_path(download_dir: str, filename: str,
                        started_at: float | None = None) -> str | None:
    """Trova su disco il file appena scaricato per un candidato.

    Cercare il solo basename e prendere il piu' recente era accettabile con un
    download alla volta. Con tre worker in parallelo sulla stessa cartella
    condivisa il piu' recente e' spesso di qualcun altro, e i nomi che
    collidono sono ordinari nei rip da vinile (`A1.flac`, `01 Intro.mp3`): si
    aggancia il file sbagliato, e `attach_local_file` puo' fondere due tracce
    distinte cancellandone una.

    Si sceglie quindi guardando, in ordine: quanti componenti finali di
    percorso il file condivide col percorso remoto del candidato (`bob\\Album
    X\\A1.flac` distingue il proprio `A1.flac` da quello di un altro album
    scaricato nello stesso momento), se e' comparso dopo l'inizio di questo
    lavoro, e infine l'mtime come prima.

    L'ora d'inizio e' un criterio di preferenza, non un filtro: se slskd
    conservasse l'mtime del peer o l'orologio fosse storto, filtrare darebbe un
    "file_missing" su un file che invece c'e'.
    """
    parti_remote = tuple(Path(filename.replace("\\", "/")).parts)
    base = parti_remote[-1] if parti_remote else ""
    root = Path(download_dir)
    if not base or not root.exists():
        return None
    # Si cammina l'albero e si confronta il NOME, invece di passare `base` come
    # pattern a `rglob`: il nome di un file non e' un glob. `A2 [SOMA123].flac`
    # (il numero di catalogo, ordinario nei rilasci techno) diventerebbe una
    # classe di caratteri e non troverebbe mai se stesso — download riuscito,
    # traccia marcata `failed` con "file mancante", file mai agganciato. E nel
    # verso opposto `01 - Track [ab].mp3` aggancerebbe `01 - Track a.mp3`, che e'
    # il file di qualcun altro. Il costo e' lo stesso: `rglob` cammina comunque
    # tutto l'albero.
    matches = [p for p in root.rglob("*") if p.name == base and p.is_file()]
    if not matches:
        return None

    def chiave(p: Path) -> tuple:
        mtime = p.stat().st_mtime
        recente = started_at is None or mtime >= started_at
        return (_coda_condivisa(p, parti_remote), recente, mtime)

    scelto = max(matches, key=chiave)
    if len(matches) > 1:
        logger.warning("Più file con basename %r in %s: scelgo %s (percorso remoto %r)",
                       base, download_dir, scelto, filename)
    return str(scelto.resolve())


def _cancel_abandoned_transfer(client, username: str, info: dict) -> None:
    """Annulla nel daemon un transfer che il job sta abbandonando (timeout/stallo).

    Best-effort: se il daemon non risponde o l'id manca, si logga e si prosegue
    — l'esito del download non deve dipendere dalla riuscita della cancellazione.
    """
    transfer_id = (info or {}).get("id")
    if not transfer_id:
        return
    try:
        client.cancel_download(username, transfer_id)
    except Exception:  # noqa: BLE001 — pulizia best-effort, non deve propagare
        logger.warning("Cancellazione transfer abbandonato fallita user=%s id=%s",
                       username, transfer_id, exc_info=True)


def _wait_for_download(client, file: SlskdFile, should_cancel=None,
                       on_progress=None) -> tuple[str, str | None]:
    """Attende l'esito di un transfer. Ritorna (esito, motivo).

    Se il transfer sta scaricando ("InProgress") si guarda `bytesTransferred`: finche'
    avanza si continua ad attendere anche oltre un tetto fisso (un file lossless da un
    peer lento puo' metterci parecchio), fino al tetto assoluto HARD_TIMEOUT. Se i byte
    restano fermi per STALL_TIMEOUT si conclude che il transfer e' bloccato e si desiste.
    Se invece resta solo in coda (Queued/Requested) oltre QUEUE_PATIENCE ci si arrende
    subito, cosi' il chiamante puo' provare un altro utente col fallback.

    Quando si desiste (stallo, coda o tetto assoluto) il transfer resta comunque
    attivo nel daemon se non lo si annulla esplicitamente: lo si cancella qui,
    best-effort, per non lasciarlo scaricare a vuoto in slskd.

    `should_cancel`, se passato, viene interrogato a ogni giro subito dopo aver
    letto lo stato dal daemon (cosi' la cancellazione dell'eventuale transfer
    in corso conosce gia' il suo id) e prima di processarlo ulteriormente: e'
    cosi' che l'annullo dell'utente arriva dentro un'attesa che altrimenti
    durerebbe fino al prossimo timeout — minuti, su un lossless da un peer lento.

    `on_progress`, se passato, riceve i byte trasferiti a ogni giro: e' lo
    stesso `bytesTransferred` gia' letto qui per rilevare lo stallo, quindi
    non costa una chiamata in piu' al daemon. Il totale lo porta il candidato
    (`file.size`), noto da prima di cominciare.
    """
    waited = 0.0
    queued = 0.0
    stalled = 0.0
    last_bytes: float | None = None
    info: dict = {}
    while waited < HARD_TIMEOUT:
        info = client.transfer_state(file.username, file.filename) or {}
        if should_cancel is not None and should_cancel():
            _cancel_abandoned_transfer(client, file.username, info)
            return "cancelled", None
        state = info.get("state", "")
        cls = classify_transfer_state(state)
        if cls == "completed":
            return "completed", None
        if cls == "failed":
            return "failed", "transfer_failed"
        if "inprogress" in state.lower():
            queued = 0.0
            transferred = info.get("bytesTransferred")
            if isinstance(transferred, (int, float)):
                if on_progress is not None:
                    on_progress("downloading", int(transferred), file.size)
                if last_bytes is not None and transferred <= last_bytes:
                    stalled += POLL_INTERVAL
                    if stalled >= STALL_TIMEOUT:
                        _cancel_abandoned_transfer(client, file.username, info)
                        return "failed", "download_timeout"
                else:
                    stalled = 0.0
                last_bytes = transferred
            # bytesTransferred non esposto: nessun dato per rilevare lo stallo,
            # si prosegue affidandosi solo al tetto assoluto HARD_TIMEOUT.
        else:
            queued += POLL_INTERVAL
            if queued >= QUEUE_PATIENCE:
                _cancel_abandoned_transfer(client, file.username, info)
                return "failed", "queue_timeout"
        time.sleep(POLL_INTERVAL)
        waited += POLL_INTERVAL
    _cancel_abandoned_transfer(client, file.username, info)
    return "failed", "download_timeout"


def _download_candidate(client, download_dir, file: SlskdFile,
                        should_cancel=None, on_progress=None) -> tuple[str | None, str | None]:
    """Accoda un candidato, attende l'esito e risolve il path locale.

    Ritorna (path, motivo): (path, None) se ok, (None, <code>) se fallisce.
    """
    # Segnato prima dell'accodamento: serve a `_resolve_local_path` per
    # preferire un file comparso durante QUESTO tentativo a uno che era gia' li'
    # (magari di un altro worker, con lo stesso nome).
    inizio = time.time()
    try:
        client.enqueue_download(file)
    except Exception as exc:  # noqa: BLE001 — un candidato che non parte non ferma il fallback
        if slskd_unreachable(exc):
            # Il daemon e' caduto fra la ricerca e l'accodamento: provare gli
            # altri candidati e' inutile (falliranno tutti uguale) e li
            # brucerebbe come "enqueue_rejected". Risale a run_item, che rimette
            # l'item in coda.
            raise
        logger.exception("enqueue fallito user=%s", file.username)
        return None, "enqueue_rejected"
    if on_progress is not None:
        # La fase cambia PRIMA dell'attesa, non dopo: e' l'attesa a durare. I
        # byte restano invece vuoti finche' il daemon non ne riporta uno vero:
        # scrivere subito (0, file.size) fa comparire una barra ferma a zero
        # per tutto il trasferimento se `bytesTransferred` non viene mai
        # esposto — che si legge come "bloccato", cioe' peggio di nessuna barra.
        # La fase «scarico» da sola dice gia' che sta succedendo qualcosa
        # (stessa scelta di `_run_soundcloud`, dove yt-dlp non riporta nulla).
        # Il None serve anche al fallback su un altro utente: ripulisce i byte
        # del tentativo precedente invece di lasciarli a schermo.
        on_progress("downloading", None, None)
    outcome, reason = _wait_for_download(client, file, should_cancel=should_cancel,
                                         on_progress=on_progress)
    if outcome != "completed":
        return None, reason
    path = _resolve_local_path(download_dir, file.filename, started_at=inizio)
    if not path:
        return None, "file_missing"
    return path, None


def _attempt_download(db, client, download_dir, track, file: SlskdFile,
                      expected_duration: int | None = None,
                      enforce_duration: bool = True,
                      should_cancel=None, on_progress=None) -> tuple[str, str | None, str | None]:
    """Scarica un candidato e lo collega a una Track. Ritorna (esito, motivo, path_dubbio).

    Verifica post-download (solo se `enforce_duration`): se la durata reale del
    file non e' coerente con quella attesa (>20s di scarto) e' quasi certamente
    la versione sbagliata → il file resta in inbox per revisione, il suo path
    viene restituito e la Track NON viene marcata posseduta. Il guard e' pensato
    per l'auto-pick, che non ha supervisione umana: quando l'utente ha scelto lui
    il candidato (review modal), la sua scelta va rispettata e il guard va saltato.
    """
    path, reason = _download_candidate(client, download_dir, file,
                                       should_cancel=should_cancel,
                                       on_progress=on_progress)
    if not path:
        # _wait_for_download ritorna reason=None solo per "completed" (gia'
        # escluso, essendoci un path) o per "cancelled": e' l'unico modo in
        # cui l'annullo risale da _download_candidate, che non porta l'outcome.
        if reason is None:
            return "cancelled", None, None
        return "failed", reason, None
    real = read_tags(path).get("duration_seconds")
    if enforce_duration and expected_duration and real and abs(real - expected_duration) > 20:
        return "needs_review", (
            f"durata non corrisponde (attesa {expected_duration}s, file {real}s)"
        ), path
    quality = read_audio_quality(path)
    attach_local_file(db, track, path=path, fmt=quality["format"],
                      bitrate=quality["bitrate"])
    return "downloaded", None, None


def _process_item(db, client, download_dir, track,
                  chosen: SlskdFile | None,
                  should_cancel=None, on_progress=None) -> tuple[str, str | None, str | None]:
    expected = track.duration_seconds
    # Discovery/singola: candidato gia' scelto dall'utente, un solo tentativo.
    # La scelta esplicita dell'utente prevale sul guard di coerenza durata
    # (pensato per proteggere l'auto-pick, senza supervisione umana).
    if chosen is not None:
        return _attempt_download(db, client, download_dir, track, chosen, expected,
                                 enforce_duration=False, should_cancel=should_cancel,
                                 on_progress=on_progress)

    # Cascata di varianti di query (la letterale spesso esclude file validi).
    ranked = search_candidates(client, artist=track.artist or "",
                               title=track.title or "", expected_duration=expected,
                               max_wait=SEARCH_MAX_WAIT)
    if not ranked:
        return "not_found", None, None
    # La confidenza si valuta su tutti i candidati: un primo posto incerto non
    # deve oscurare un candidato affidabile piu' in basso nella classifica.
    eligible = auto_pick_candidates(ranked)
    if not eligible:
        return "needs_review", "confidenza sotto soglia per l'auto-pick", None
    # Fallback: prova i migliori candidati, un utente diverso alla volta, finche' uno riesce.
    tried: set[str] = set()
    last_reason: str | None = None
    for cand in eligible:
        if len(tried) >= MAX_ATTEMPTS:
            break
        if cand.file.username in tried:
            continue
        tried.add(cand.file.username)
        outcome, reason, path = _attempt_download(db, client, download_dir, track,
                                                  cand.file, expected,
                                                  should_cancel=should_cancel,
                                                  on_progress=on_progress)
        if outcome == "cancelled":
            # Un annullo non deve essere scavalcato dal fallback su un altro utente.
            return outcome, reason, path
        if outcome != "failed":
            return outcome, reason, path
        last_reason = reason
    return "failed", last_reason or "all_candidates_failed", None
