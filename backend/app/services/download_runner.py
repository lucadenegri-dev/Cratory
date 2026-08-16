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
    SlskdFile, classify_transfer_state, get_slskd_client,
)
from app.integrations.soundcloud_audio import SoundCloudAudioError, download_track_audio
from app.models import DownloadQueueItem, Track
from app.services import download_queue as queue
from app.services.acquisition import attach_local_file
from app.services.soulseek_select import auto_pick_candidates, search_candidates

logger = logging.getLogger(__name__)


def _candidate_from_payload(payload: dict | None) -> SlskdFile | None:
    if not payload:
        return None
    return SlskdFile(username=payload["username"], filename=payload["filename"],
                     size=payload.get("size"), bitrate=payload.get("bitrate"),
                     length=payload.get("length"), has_free_slot=True,
                     queue_length=None)


def _run_soulseek(db, item: DownloadQueueItem, track: Track,
                  chosen: SlskdFile | None) -> tuple[str, str | None, str | None]:
    """Ritorna (esito, motivo, path_dubbio), come il job storico.

    `should_cancel` viene interrogato dal ciclo di attesa del transfer: senza,
    annullare una traccia gia' in corso non avrebbe effetto fino alla fine del
    trasferimento — che su un lossless da un peer lento sono minuti.
    """
    client = get_slskd_client()
    try:
        download_dir = runtime_settings.slskd_download_dir()
        return _process_item(db, client, download_dir, track, chosen,
                             should_cancel=lambda: queue.is_cancelled(db, item.id))
    finally:
        client.close()


def _run_soundcloud(db, item: DownloadQueueItem, track: Track,
                    chosen: SlskdFile | None) -> tuple[str, str | None, str | None]:
    try:
        path = download_track_audio(track.url, runtime_settings.slskd_download_dir())
    except SoundCloudAudioError as exc:
        return "failed", str(exc), None
    quality = read_audio_quality(path)
    attach_local_file(db, track, path=path, fmt=quality["format"],
                      bitrate=quality["bitrate"])
    return "downloaded", None, None


def run_item(item_id: int) -> None:
    """Esegue un item. Non solleva mai: un fallimento chiude l'item, non il pool."""
    db = SessionLocal()
    try:
        item = db.get(DownloadQueueItem, item_id)
        if item is None or item.state != "running":
            return  # annullato prima di partire, o gia' concluso
        track = db.get(Track, item.track_id)
        if track is None:
            queue.finish(db, item_id, "failed", "track_not_found")
            return
        queue.set_progress(db, item_id, "searching")
        try:
            if item.kind == "soundcloud":
                outcome, reason, path = _run_soundcloud(db, item, track, None)
            else:
                chosen = _candidate_from_payload(item.payload_dict())
                outcome, reason, path = _run_soulseek(db, item, track, chosen)
        except Exception as exc:  # noqa: BLE001 — un item rotto non ferma la coda
            db.rollback()
            logger.exception("Item di coda %s fallito", item_id)
            outcome, reason, path = "failed", str(exc) or "error", None
        # Annullato mentre lavorava: l'item resta `cancelled` e la traccia NON
        # riceve un esito — non e' andata male, e' stata fermata.
        if outcome == "cancelled" or queue.is_cancelled(db, item_id):
            return
        # L'esito va anche sulla traccia: e' la fonte dei tab della wishlist.
        track = db.get(Track, item.track_id)
        if track is not None:
            track.last_download_outcome = outcome
            track.last_download_reason = reason
            track.last_download_path = path
            db.commit()
        queue.finish(db, item_id, outcome, reason)
    finally:
        db.close()


# --- Logica di trasferimento assorbita da soulseek_download_job.py ---------
#
# Copiata alla lettera dal job storico (che resta in piedi fino al Task 7).
# Le uniche differenze sono le tre modifiche per far arrivare l'annullo fin
# dentro il ciclo di attesa: il parametro `should_cancel`, inoltrato da
# `_process_item` a `_attempt_download` a `_wait_for_download`, e l'esito
# "cancelled" che risale senza essere scavalcato dal fallback su un altro
# utente. Il resto — cascata di varianti, soglie di confidenza, guardia sulla
# durata, timeout — e' identico: e' il codice coperto dai test di regressione
# del job originale.

POLL_INTERVAL = 2.0
STALL_TIMEOUT = 60.0           # transfer InProgress ma bytesTransferred fermo da tanto: ci si arrende
QUEUE_PATIENCE = 45.0          # oltre questo, se resta solo in coda, si prova un altro utente
HARD_TIMEOUT = 1800.0          # tetto assoluto anche se il progresso avanza (lossless da peer lenti)
MAX_ATTEMPTS = 4               # quanti candidati (utenti diversi) provare per traccia
SEARCH_MAX_WAIT = 15.0         # il job e' in background: attesa piena per variante, non il budget ridotto di /candidates


def _resolve_local_path(download_dir: str, filename: str) -> str | None:
    base = Path(filename.replace("\\", "/")).name
    root = Path(download_dir)
    if not root.exists():
        return None
    matches = [p for p in root.rglob(base) if p.is_file()]
    if not matches:
        return None
    if len(matches) > 1:
        logger.warning("Più file con basename %r in %s: scelgo il più recente", base, download_dir)
    return str(max(matches, key=lambda p: p.stat().st_mtime).resolve())


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


def _wait_for_download(client, file: SlskdFile, should_cancel=None) -> tuple[str, str | None]:
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
                        should_cancel=None) -> tuple[str | None, str | None]:
    """Accoda un candidato, attende l'esito e risolve il path locale.

    Ritorna (path, motivo): (path, None) se ok, (None, <code>) se fallisce.
    """
    try:
        client.enqueue_download(file)
    except Exception:  # noqa: BLE001 — un candidato che non parte non ferma il fallback
        logger.exception("enqueue fallito user=%s", file.username)
        return None, "enqueue_rejected"
    outcome, reason = _wait_for_download(client, file, should_cancel=should_cancel)
    if outcome != "completed":
        return None, reason
    path = _resolve_local_path(download_dir, file.filename)
    if not path:
        return None, "file_missing"
    return path, None


def _attempt_download(db, client, download_dir, track, file: SlskdFile,
                      expected_duration: int | None = None,
                      enforce_duration: bool = True,
                      should_cancel=None) -> tuple[str, str | None, str | None]:
    """Scarica un candidato e lo collega a una Track. Ritorna (esito, motivo, path_dubbio).

    Verifica post-download (solo se `enforce_duration`): se la durata reale del
    file non e' coerente con quella attesa (>20s di scarto) e' quasi certamente
    la versione sbagliata → il file resta in inbox per revisione, il suo path
    viene restituito e la Track NON viene marcata posseduta. Il guard e' pensato
    per l'auto-pick, che non ha supervisione umana: quando l'utente ha scelto lui
    il candidato (review modal), la sua scelta va rispettata e il guard va saltato.
    """
    path, reason = _download_candidate(client, download_dir, file, should_cancel=should_cancel)
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
                  should_cancel=None) -> tuple[str, str | None, str | None]:
    expected = track.duration_seconds
    # Discovery/singola: candidato gia' scelto dall'utente, un solo tentativo.
    # La scelta esplicita dell'utente prevale sul guard di coerenza durata
    # (pensato per proteggere l'auto-pick, senza supervisione umana).
    if chosen is not None:
        return _attempt_download(db, client, download_dir, track, chosen, expected,
                                 enforce_duration=False, should_cancel=should_cancel)

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
                                                  should_cancel=should_cancel)
        if outcome == "cancelled":
            # Un annullo non deve essere scavalcato dal fallback su un altro utente.
            return outcome, reason, path
        if outcome != "failed":
            return outcome, reason, path
        last_reason = reason
    return "failed", last_reason or "all_candidates_failed", None
