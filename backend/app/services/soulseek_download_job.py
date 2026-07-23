"""Job in background per scaricare tracce via slskd e collegarle alle Track.

Mono-utente, uno-job-per-volta (come local_import_job): threading + stato in
memoria + lock. Per ogni traccia: ricerca -> selezione -> enqueue -> polling
del transfer -> link del file alla Track. Un errore su una traccia non ferma
il job.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import settings
from app.db import SessionLocal
from app.integrations.local_files import read_audio_quality, read_tags
from app.integrations.slskd import (
    SlskdError, SlskdFile, classify_transfer_state, get_slskd_client,
)
from app.repositories import get_track, tracks_without_local_file
from app.services.acquisition import attach_local_file
from app.services.soulseek_select import auto_pick_candidates, search_candidates
from app.integrations.soundcloud_audio import SoundCloudAudioError, download_track_audio

logger = logging.getLogger(__name__)

POLL_INTERVAL = 2.0
STALL_TIMEOUT = 60.0           # transfer InProgress ma bytesTransferred fermo da tanto: ci si arrende
QUEUE_PATIENCE = 45.0          # oltre questo, se resta solo in coda, si prova un altro utente
HARD_TIMEOUT = 1800.0          # tetto assoluto anche se il progresso avanza (lossless da peer lenti)
MAX_ATTEMPTS = 4               # quanti candidati (utenti diversi) provare per traccia
SEARCH_MAX_WAIT = 15.0         # il job e' in background: attesa piena per variante, non il budget ridotto di /candidates

_lock = threading.Lock()
_state: dict = {
    "status": "idle",
    "processed": 0,
    "total": 0,
    "downloaded": 0,
    "needs_review": 0,
    "not_found": 0,
    "failed": 0,
    "playlist_id": None,
    "items": [],
    "error": None,
    "current_label": None,
    "started_at": None,
    "finished_at": None,
}


def _track_label(track) -> str:
    artist = (track.artist or "").strip() or "Artista sconosciuto"
    title = (track.title or "").strip() or "Senza titolo"
    return f"{artist} — {title}"


def job_state() -> dict:
    return dict(_state)


def is_running() -> bool:
    return _state["status"] == "running"


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


def _wait_for_download(client, file: SlskdFile) -> tuple[str, str | None]:
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
    """
    waited = 0.0
    queued = 0.0
    stalled = 0.0
    last_bytes: float | None = None
    info: dict = {}
    while waited < HARD_TIMEOUT:
        info = client.transfer_state(file.username, file.filename) or {}
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


def _download_candidate(client, download_dir, file: SlskdFile) -> tuple[str | None, str | None]:
    """Accoda un candidato, attende l'esito e risolve il path locale.

    Ritorna (path, motivo): (path, None) se ok, (None, <code>) se fallisce.
    """
    try:
        client.enqueue_download(file)
    except Exception:  # noqa: BLE001 — un candidato che non parte non ferma il fallback
        logger.exception("enqueue fallito user=%s", file.username)
        return None, "enqueue_rejected"
    outcome, reason = _wait_for_download(client, file)
    if outcome != "completed":
        return None, reason
    path = _resolve_local_path(download_dir, file.filename)
    if not path:
        return None, "file_missing"
    return path, None


def _attempt_download(db, client, download_dir, track, file: SlskdFile,
                      expected_duration: int | None = None,
                      enforce_duration: bool = True) -> tuple[str, str | None, str | None]:
    """Scarica un candidato e lo collega a una Track. Ritorna (esito, motivo, path_dubbio).

    Verifica post-download (solo se `enforce_duration`): se la durata reale del
    file non e' coerente con quella attesa (>20s di scarto) e' quasi certamente
    la versione sbagliata → il file resta in inbox per revisione, il suo path
    viene restituito e la Track NON viene marcata posseduta. Il guard e' pensato
    per l'auto-pick, che non ha supervisione umana: quando l'utente ha scelto lui
    il candidato (review modal), la sua scelta va rispettata e il guard va saltato.
    """
    path, reason = _download_candidate(client, download_dir, file)
    if not path:
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


def _process_manual(client, download_dir, file: SlskdFile) -> str:
    """Ricerca manuale: scarica il file sul disco (inbox slskd). NON lo cataloga in
    Cratory: entra in libreria via Sortory (sposta i file in LIBRARY_ROOT) +
    indicizzazione, come un qualsiasi file posseduto. Niente playlist 'Soulseek'."""
    path, _ = _download_candidate(client, download_dir, file)
    return "downloaded" if path else "failed"


def _process_item(db, client, download_dir, track,
                  chosen: SlskdFile | None) -> tuple[str, str | None, str | None]:
    expected = track.duration_seconds
    # Discovery/singola: candidato gia' scelto dall'utente, un solo tentativo.
    # La scelta esplicita dell'utente prevale sul guard di coerenza durata
    # (pensato per proteggere l'auto-pick, senza supervisione umana).
    if chosen is not None:
        return _attempt_download(db, client, download_dir, track, chosen, expected,
                                 enforce_duration=False)

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
                                                  cand.file, expected)
        if outcome != "failed":
            return outcome, reason, path
        last_reason = reason
    return "failed", last_reason or "all_candidates_failed", None


def _run(items: list[tuple[int, SlskdFile | None]], playlist_id: int | None) -> None:
    db = SessionLocal()
    client = None
    try:
        client = get_slskd_client()
        download_dir = settings.slskd_download_dir
        _state.update(total=len(items), playlist_id=playlist_id)
        for i, (track_id, chosen) in enumerate(items, start=1):
            track = None
            reason = None
            path = None
            if track_id is None:  # ricerca manuale: scarica + cataloga in libreria
                _state["current_label"] = (
                    Path(chosen.filename.replace("\\", "/")).name if chosen else None
                )
                try:
                    outcome = _process_manual(client, download_dir, chosen) if chosen else "failed"
                except SlskdError:
                    raise  # daemon giu'/disconnesso: le restanti fallirebbero tutte uguali
                except Exception:  # noqa: BLE001 — un fallimento non ferma il job
                    logger.exception("Download Soulseek manuale fallito")
                    outcome = "failed"
                title = chosen.filename if chosen else None
            else:
                track = get_track(db, track_id)
                if track is None:
                    outcome = "failed"
                else:
                    _state["current_label"] = _track_label(track)
                    try:
                        outcome, reason, path = _process_item(db, client, download_dir, track, chosen)
                    except SlskdError:
                        raise  # daemon giu'/disconnesso: fail-fast col messaggio in _state.error
                    except Exception:  # noqa: BLE001 — un fallimento non ferma il job
                        logger.exception("Download Soulseek fallito per track_id=%s", track_id)
                        outcome = "failed"
                        reason = "error"
                title = getattr(track, "title", None)
            _state[outcome] = _state.get(outcome, 0) + 1
            if track is not None:
                # Persisti l'esito sulla traccia: la sezione "da sistemare"
                # deve sopravvivere a job e riavvii. path != None solo per un
                # needs_review-per-durata (file dubbio in inbox da rivedere).
                track.last_download_outcome = outcome
                track.last_download_reason = reason
                track.last_download_path = path
                db.commit()
            _state["processed"] = i
            _state["items"].append({
                "track_id": track_id,
                "artist": getattr(track, "artist", None),
                "title": title,
                "outcome": outcome,
                "reason": reason,
            })
        _state.update(status="done")
        # Enrichment non piu' avviato qui: e' ora responsabilita' di Sortory.
    except Exception as exc:  # noqa: BLE001
        _state.update(status="error", error=str(exc))
        logger.exception("Job di download Soulseek interrotto: %s", exc)
    finally:
        _state["current_label"] = None
        _state["finished_at"] = datetime.now(timezone.utc).isoformat()
        if client is not None:
            client.close()
        db.close()


def _reset_running_state(total: int, playlist_id: int | None) -> None:
    _state.update(status="running", processed=0, total=total,
                  downloaded=0, needs_review=0, not_found=0, failed=0,
                  playlist_id=playlist_id, items=[], error=None,
                  current_label=None,
                  started_at=datetime.now(timezone.utc).isoformat(),
                  finished_at=None)


def _start(items, playlist_id) -> dict:
    with _lock:
        if _state["status"] == "running":
            return job_state()
        _reset_running_state(len(items), playlist_id)
    threading.Thread(target=_run, args=(items, playlist_id), daemon=True).start()
    return job_state()


def start_playlist_job(playlist_id: int) -> dict:
    db = SessionLocal()
    try:
        items = [(t.id, None) for t in tracks_without_local_file(db, playlist_id)]
    finally:
        db.close()
    return _start(items, playlist_id)


def start_retry_job() -> dict:
    """Ritenta l'auto-pick su tutte le tracce con esito da sistemare."""
    from app.repositories import tracks_download_pending
    db = SessionLocal()
    try:
        items = [(t.id, None) for t in tracks_download_pending(db)]
    finally:
        db.close()
    return _start(items, None)


def start_track_job(track_id: int, chosen: SlskdFile) -> dict:
    return _start([(track_id, chosen)], None)


def start_track_autopick_job(track_id: int) -> dict:
    """Auto-pick immediato per una singola traccia (es. 'Scarica ora' dalla
    tracklist di un lead Discovery): nessun candidato pre-scelto, stessa
    cascata di ricerca usata da start_playlist_job/start_retry_job."""
    return _start([(track_id, None)], None)


def start_manual_job(chosen: SlskdFile) -> dict:
    """Ricerca manuale: scarica il candidato scelto e lo cataloga in libreria."""
    return _start([(None, chosen)], None)


def start_soundcloud_track_job(track_id: int) -> dict:
    """Scarica via yt-dlp l'audio di una singola traccia SoundCloud e la collega.

    Riusa lo stesso stato/lock/barra del download Soulseek (un solo download alla
    volta). Nessun candidato slskd: scarica direttamente da track.url.
    """
    with _lock:
        if _state["status"] == "running":
            return job_state()
        _reset_running_state(1, None)
    threading.Thread(target=_run_soundcloud, args=(track_id,), daemon=True).start()
    return job_state()


def _run_soundcloud(track_id: int) -> None:
    """Worker: scarica l'audio SoundCloud della traccia e la collega. Niente slskd."""
    db = SessionLocal()
    outcome = "failed"
    reason: str | None = None
    try:
        track = get_track(db, track_id)
        if track is None:
            _state.update(status="error", error="track_not_found")
            return
        _state["current_label"] = _track_label(track)
        try:
            path = download_track_audio(track.url, settings.slskd_download_dir)
            quality = read_audio_quality(path)
            attach_local_file(db, track, path=path, fmt=quality["format"],
                              bitrate=quality["bitrate"])
            outcome = "downloaded"
        except SoundCloudAudioError as exc:
            # attach_local_file puo' aver gia' mutato track.has_local_file in memoria
            # prima di fallire: rollback per non persistere un possesso solo parziale.
            db.rollback()
            reason = str(exc)
            logger.warning("Download SoundCloud fallito per track_id=%s: %s", track_id, exc)
        except Exception:  # noqa: BLE001 — un fallimento non deve lasciare il job appeso
            db.rollback()
            reason = "error"
            logger.exception("Download SoundCloud fallito per track_id=%s", track_id)
        _state[outcome] = _state.get(outcome, 0) + 1
        _state["processed"] = 1
        track.last_download_outcome = outcome
        track.last_download_reason = reason
        track.last_download_path = None
        db.commit()
        _state["items"].append({
            "track_id": track_id,
            "artist": track.artist,
            "title": track.title,
            "outcome": outcome,
            "reason": reason,
        })
        _state.update(status="done")
    except Exception as exc:  # noqa: BLE001
        _state.update(status="error", error=str(exc))
        logger.exception("Job download SoundCloud interrotto: %s", exc)
    finally:
        _state["current_label"] = None
        _state["finished_at"] = datetime.now(timezone.utc).isoformat()
        db.close()
