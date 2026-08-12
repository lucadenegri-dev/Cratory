# backend/app/services/library_index.py
"""Indicizzazione della libreria canonica (disk-first): il disco È la libreria.

Deterministico, senza AI. Per ogni file audio sotto LIBRARY_ROOT:
hash → match (audio_hash → digest legacy → ISRC → fuzzy artist+title) → upsert
del possesso (local_path/has_local_file/formato/bitrate/audio_hash). I tag del
file riempiono SOLO i campi identità vuoti: enrichment e correzioni manuali
restano autorevoli (regola: mai sovrascrivere).
"""
from __future__ import annotations

import logging
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.integrations.local_files import (
    LocalFilesError,
    audio_hash,
    read_audio_quality,
    read_tags,
)
from app.models import ArchiveSeen, Track, utcnow
from app.repositories import ci_equals, unreferenced_track_ids
from app.services.audio_energy import analyze_file, recompute_energy
from app.services.genre_norm import normalize_genre
# Ponte fra il modello core e Organize: file_link è il solo modulo autorizzato a
# scrivere primary_file_id/track_id, e resta minuscolo apposta per non aprire un
# ciclo di import fra i due mondi.
from app.organize.services.file_link import aggiorna_primary
from app.services.manual_import import parse_line
from app.services.local_import import scan_folder
from app.services.track_status import refresh_status

logger = logging.getLogger(__name__)

PLATFORM = "local_files"

# Commit incrementale nella scansione: ogni N file elaborati il lavoro viene
# persistito, così un crash a metà run non butta via tutto (stesso principio
# del job di analisi, che committa per traccia). Vale solo per il loop
# per-file: la riconciliazione finale (lost/orfani) resta un blocco unico.
COMMIT_EVERY = 50


def _norm_key(s: str | None) -> str:
    """Chiave di confronto per artista/titolo: senza diacritici, minuscola, senza
    suffissi tipici (`feat.`/`(Original Mix)`/`- ... Remix`) e senza punteggiatura.
    Serve ad agganciare 'X feat. Y (Original Mix)' al lead 'X'."""
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = re.sub(r"\([^)]*\)|\[[^\]]*\]", " ", s)                      # (Original Mix), [xxx]
    s = re.sub(r"\b(feat|ft)\.?\s.*$", " ", s)                       # feat. X ... a fine
    s = re.sub(r"\s[-–]\s.*\b(mix|remix|edit|version|dub|rework)\b.*$", " ", s)  # " - ... Mix"
    s = re.sub(r"[^a-z0-9]+", " ", s)                                # punteggiatura -> spazio
    return re.sub(r"\s+", " ", s).strip()


def _duration_ok(a: int | None, b: int | None, tol: int = 7) -> bool:
    """Durate compatibili (o almeno una assente): guardia contro merge sbagliati."""
    if a is None or b is None:
        return True
    return abs(a - b) <= tol


def _find_track(db: Session, *, digest: str, tags: dict, path: str) -> tuple[Track | None, str]:
    """Match nell'ordine di affidabilità. Ritorna (track, come)."""
    # Il path per primo: se una Track rivendica gia' QUESTO file, e' quella. La
    # passata 1 usa lo stesso criterio per il fast-path (`known`), ma lo scarta
    # appena mtime/size cambiano — cioe' dopo ogni Apply di Organize, che ritagga
    # il file. Senza questo ramo la passata 2 coniava un doppione per un path che
    # la passata 1 aveva gia' identificato: hash diverso, ISRC assente dai tag e
    # rami per nome che escludono di proposito le tracce gia' possedute.
    # Sta prima dell'hash di proposito: l'hash identifica l'AUDIO e sopravvive a
    # uno spostamento, il path identifica QUESTO file. Quando i due dissentono
    # vince il path, perche' e' l'unica delle due letture che non puo' creare un
    # secondo proprietario dello stesso local_path.
    hit = db.scalar(select(Track).where(Track.local_path == path,
                                        Track.has_local_file.is_(True)))
    if hit:
        return hit, "path"
    hit = db.scalar(select(Track).where(Track.audio_hash == digest))
    if hit:
        return hit, "hash"
    # Import locali storici: il digest viveva in platform_track_id.
    hit = db.scalar(select(Track).where(
        Track.platform == PLATFORM, Track.platform_track_id == digest))
    if hit:
        return hit, "digest"
    if tags.get("isrc"):
        hit = db.scalar(select(Track).where(Track.isrc == tags["isrc"]))
        if hit:
            return hit, "isrc"
    artist, title = tags.get("artist"), tags.get("title")
    if artist and title:
        # Solo tracce senza file: come il ramo normalizzato piu' sotto, il match
        # per nome non deve rubare il file a una posseduta (il riaggancio
        # legittimo dello stesso contenuto passa dai rami hash/ISRC sopra).
        hit = db.scalar(select(Track).where(
            ci_equals(Track.artist, artist), ci_equals(Track.title, title),
            Track.has_local_file.is_not(True)))
        if hit:
            return hit, "fuzzy"
        # Fuzzy normalizzato: titoli con suffissi diversi ma stesso brano. Solo su
        # tracce SENZA file (lead da agganciare), con guardia sulla durata: non si
        # ruba il file a una posseduta né si fonde un brano col suo remix.
        na, nt = _norm_key(artist), _norm_key(title)
        if na and nt:
            file_dur = tags.get("duration_seconds")
            for cand in db.scalars(select(Track).where(
                Track.has_local_file.is_not(True),
                Track.artist.is_not(None), Track.title.is_not(None),
            )):
                if (_norm_key(cand.artist) == na and _norm_key(cand.title) == nt
                        and _duration_ok(cand.duration_seconds, file_dur)):
                    return cand, "fuzzy-norm"
    return None, ""


def _added_at_from_stat(st) -> datetime | None:
    """Data di nascita del file (st_birthtime su macOS, st_ctime su Windows).
    L'mtime non va bene: le scritture dei tag (Sortory) lo aggiornano."""
    ts = getattr(st, "st_birthtime", None) or getattr(st, "st_ctime", None)
    return datetime.fromtimestamp(ts, tz=timezone.utc) if ts else None


def _file_added_at(path: Path) -> datetime | None:
    try:
        st = path.stat()
    except OSError:
        return None
    return _added_at_from_stat(st)


def _fill_identity(track: Track, tags: dict, path: Path) -> None:
    """Riempie SOLO i campi vuoti dai tag (fallback dal nome file, come l'import locale)."""
    artist, title = tags.get("artist"), tags.get("title")
    if not artist or not title:
        parsed = parse_line(path.stem)
        if parsed is not None:
            artist = artist or parsed[0]
            title = title or parsed[1]
    track.title = track.title or title
    track.artist = track.artist or artist
    track.album = track.album or tags.get("album")
    track.year = track.year or tags.get("year")
    track.duration_seconds = track.duration_seconds or tags.get("duration_seconds")
    track.isrc = track.isrc or tags.get("isrc")
    track.label = track.label or tags.get("label")
    # Genere dal tag del file: ultima spiaggia della catena (mai sovrascrivere).
    if not track.genre and tags.get("genre"):
        normalized = normalize_genre(tags["genre"])
        if normalized:
            track.genre = normalized


def _own(track: Track, *, path: Path, digest: str) -> None:
    quality = read_audio_quality(path)
    stat = path.stat()
    track.local_path = str(path.resolve())
    track.has_local_file = True
    track.local_format = quality["format"]
    track.local_bitrate = quality["bitrate"]
    track.audio_hash = digest
    track.local_mtime = stat.st_mtime
    track.local_size = stat.st_size
    track.archived = False  # il possesso in Libreria vince sullo scarto
    # Energia vera dai campioni audio (PR4). Solo qui, cioè sui file nuovi/cambiati
    # (la passata incrementale salta gli invariati). Fallback silenzioso: la
    # calibrazione a fine job trasforma energy_raw in energy (0-100).
    try:
        raw = analyze_file(path, track.duration_seconds)
    except Exception as exc:  # decode/analisi non deve mai far fallire l'indicizzazione
        logger.debug("Analisi energia saltata per %s: %s", path, exc)
        raw = None
    if raw is not None:
        track.energy_raw = raw


def _discard(track: Track, *, path: Path, digest: str) -> None:
    """Il file vive nell'archivio: traccia scartata, non posseduta.

    local_path punta al file in archivio (si sa dov'e' finita); mtime/size
    servono allo skip incrementale anche per l'archivio.
    """
    stat = path.stat()
    track.archived = True
    track.has_local_file = False
    track.local_path = str(path.resolve())
    track.local_format = None
    track.local_bitrate = None
    track.audio_hash = digest
    track.local_mtime = stat.st_mtime
    track.local_size = stat.st_size


def _is_hidden_path(path: Path, root: str | Path) -> bool:
    """True se, sotto `root`, un segmento della path inizia per '.' (es. `.quarantine`):
    `scan_folder` lo esclude, quindi non è più contenuto di libreria. File fuori da
    `root` (o path non risolvibile): non considerati nascosti qui."""
    try:
        rel = path.resolve().relative_to(Path(root).resolve())
    except (ValueError, OSError):
        return False
    return any(part.startswith(".") for part in rel.parts)


def index_library(db: Session, *, root: str | Path,
                  archive_root: str | Path | None = None, on_progress=None) -> dict:
    """Indicizza la libreria canonica e (se configurato) l'archivio delle scartate."""
    files = scan_folder(root)
    archive_files: list[Path] = []
    archive_scanned = bool(archive_root and Path(archive_root).is_dir())
    if archive_scanned:
        archive_files = scan_folder(archive_root)
    total = len(files) + len(archive_files)
    report = {"scanned": len(files), "matched": 0, "created": 0,
              "relinked": 0, "duplicates": 0, "lost": 0, "orphans_removed": 0,
              "failed": 0, "unchanged": 0, "archived": 0, "errors": [], "created_ids": []}
    seen_paths: set[str] = set()
    seen_digests: set[str] = set()
    # Firme dei file d'archivio già visti che non corrispondono ad alcuna traccia:
    # senza questo, verrebbero ri-hashati (ffmpeg) a ogni run. {path: (mtime, size)}
    archive_seen: dict[str, tuple[float, int]] = {}
    if archive_files:
        archive_seen = {r.path: (r.mtime, r.size) for r in db.scalars(select(ArchiveSeen))}

    # Passata 1 — incrementale (Libreria E archivio): i file invariati (path noto,
    # mtime+size uguali) reclamano subito path e hash SENZA ri-hash. Va fatta PRIMA
    # della passata completa: altrimenti una copia nuova dello stesso audio, se
    # scansionata prima dell'originale invariato, gli ruberebbe la traccia.
    done = 0
    pending: list[tuple[Path, bool]] = []
    for path, in_archive in ([(p, False) for p in files]
                             + [(p, True) for p in archive_files]):
        resolved = str(path.resolve())
        try:
            stat = path.stat()
        except OSError as exc:
            # File sparito tra la scansione e lo stat() (o illeggibile): si
            # salta e si conta, senza far morire l'intero run.
            report["failed"] += 1
            report["errors"].append({"path": str(path), "error": str(exc)})
            logger.warning("File saltato %s: %s", path, exc)
            done += 1
            if on_progress is not None:
                on_progress(done, total)
            continue
        known = db.scalar(select(Track).where(Track.local_path == resolved))
        if (known is not None and known.local_mtime == stat.st_mtime
                and known.local_size == stat.st_size):
            report["unchanged"] += 1
            seen_paths.add(resolved)
            if known.audio_hash:
                seen_digests.add(known.audio_hash)
            if known.added_at is None:
                # Recupero data anche sul fast-path: traccia storica senza data,
                # lo stat è già in mano (nessun costo aggiuntivo).
                known.added_at = _added_at_from_stat(stat)
            done += 1
            if on_progress is not None:
                on_progress(done, total)
        elif in_archive and archive_seen.get(resolved) == (stat.st_mtime, stat.st_size):
            # File d'archivio senza traccia, ma già visto e invariato: niente ri-hash.
            report["unchanged"] += 1
            seen_paths.add(resolved)
            done += 1
            if on_progress is not None:
                on_progress(done, total)
        else:
            pending.append((path, in_archive))

    # Passata 2 — flusso completo per i soli file nuovi o modificati.
    # La Libreria viene prima dell'archivio: a parita' di audio il possesso vince.
    for n_pending, (path, in_archive) in enumerate(pending):
        # Commit incrementale a inizio giro (così i `continue` non lo saltano):
        # persiste il blocco precedente prima di attaccare il file successivo.
        if n_pending and n_pending % COMMIT_EVERY == 0:
            db.commit()
        done += 1
        i = done
        try:
            digest = audio_hash(path)
        except LocalFilesError as exc:
            report["failed"] += 1
            report["errors"].append({"path": str(path), "error": str(exc)})
            logger.warning("File saltato %s: %s", path, exc)
            continue
        if digest in seen_digests:
            # Due file con lo stesso audio nello stesso run: il primo vince, gli altri
            # si contano soltanto (la dedup su disco e' compito di Sortory).
            report["duplicates"] += 1
            logger.warning("Audio duplicato nello stesso run: %s (digest gia' visto)", path)
            if on_progress is not None:
                on_progress(i, total)
            continue
        seen_digests.add(digest)
        tags = read_tags(path)
        track, how = _find_track(db, digest=digest, tags=tags, path=str(path.resolve()))
        if in_archive:
            # In archivio non si creano tracce nuove: un file mai visto da
            # Cratory che scarti non e' una wishlist da ricordare.
            if track is not None:
                _fill_identity(track, tags, path)
                _discard(track, path=path, digest=digest)
                # local_path punta ora al file in ARCHIVE_ROOT, che non è
                # indicizzato da Organize: l'aggancio si azzera da sé.
                aggiorna_primary(db, track)
                refresh_status(track)
                report["archived"] += 1
                seen_paths.add(str(path.resolve()))
            else:
                # Senza traccia: ricorda la firma per non ri-hasharlo al prossimo run.
                try:
                    stat = path.stat()
                except OSError as exc:
                    # File sparito/illeggibile tra l'hash e lo stat(): si salta e
                    # si conta, senza far morire l'intero run (come in passata 1).
                    report["failed"] += 1
                    report["errors"].append({"path": str(path), "error": str(exc)})
                    logger.warning("File saltato %s: %s", path, exc)
                    if on_progress is not None:
                        on_progress(i, total)
                    continue
                db.merge(ArchiveSeen(path=str(path.resolve()), mtime=stat.st_mtime, size=stat.st_size))
            if on_progress is not None:
                on_progress(i, total)
            continue
        if track is None:
            track = Track(source_type=PLATFORM, platform=PLATFORM, platform_track_id=digest)
            db.add(track)
            db.flush()  # serve l'id per l'auto-enrichment a fine job
            report["created"] += 1
            report["created_ids"].append(track.id)
        else:
            report["matched"] += 1
            if track.local_path != str(path.resolve()):
                report["relinked"] += 1
        _fill_identity(track, tags, path)
        _own(track, path=path, digest=digest)
        aggiorna_primary(db, track)
        if track.added_at is None:
            # Data d'ingresso in collezione: birthtime del file. Vale sia per le
            # tracce nuove sia come recupero per le storiche rimaste senza data.
            track.added_at = _file_added_at(path) or utcnow()
        refresh_status(track)
        seen_paths.add(str(path.resolve()))
        if on_progress is not None:
            on_progress(i, total)

    # Pulisci la cache d'archivio dalle firme di file non più presenti.
    if archive_scanned:
        current_archive = {str(p.resolve()) for p in archive_files}
        stale = [pth for pth in archive_seen if pth not in current_archive]
        if stale:
            db.execute(delete(ArchiveSeen).where(ArchiveSeen.path.in_(stale)))

    # Anti-unmount (stesso principio dell'import locale): una radice vuota o
    # illeggibile (path sbagliato, disco smontato) non deve azzerare i possessi.
    if not files:
        db.commit()
        return report

    # Riconciliazione: possessi il cui file la scansione non ha visto — cancellato,
    # spostato fuori, oppure finito in una cartella nascosta (esclusa da scan_folder).
    # L'audio_hash resta: se il file ricompare, il riaggancio (anche a un lead Spotify
    # via ISRC/artista+titolo) e' immediato.
    owned = db.scalars(select(Track).where(Track.has_local_file.is_(True))).all()
    lost: list[Track] = []
    for track in owned:
        if not track.local_path or track.local_path in seen_paths:
            continue
        p = Path(track.local_path)
        # Tenuto solo se il file esiste ancora ED e' in una cartella visibile: un
        # file esistente ma nascosto non e' piu' libreria.
        if p.exists() and not _is_hidden_path(p, root):
            continue
        lost.append(track)

    # I file persi il cui brano non e' in nessuna playlist/set si rimuovono del tutto
    # (niente lead fantasma); gli altri restano come lead con il solo link al file
    # tolto. Decidiamo PRIMA di mutare, cosi' gli orfani si cancellano via ORM senza
    # conflitti di stato.
    unref = set(unreferenced_track_ids(db, [t.id for t in lost]))
    for track in lost:
        if track.id in unref:
            db.delete(track)
            report["orphans_removed"] += 1
        else:
            track.has_local_file = False
            track.local_path = None
            track.local_format = None
            track.local_bitrate = None
            track.primary_file_id = None  # senza local_path non c'è file da indicare
            refresh_status(track)
            report["lost"] += 1

    db.commit()
    # Calibrazione energia: mappa gli energy_raw (0..1) in energy 0-100 per percentili
    # sull'INTERA libreria, così "100" è la traccia più energica dell'utente.
    report["energy_computed"] = recompute_energy(db)
    return report
