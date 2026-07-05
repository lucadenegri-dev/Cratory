"""Fingerprinting della libreria posseduta: file audio -> Track.mbid (via AcoustID).

Da' alle tracce possedute un'identita' MusicBrainz certa, ricavata dall'audio
stesso: la catena di enrichment poi usa l'MBID per il lookup diretto MusicBrainz
e per AcousticBrainz (vedi feature_enrichment/musicbrainz).

Regole:
- Si processano solo tracce con file su disco (`has_local_file` + `local_path`).
- Si applica il candidato migliore solo con score >= SCORE_THRESHOLD; sotto
  soglia niente mbid (mai un'identita' incerta), ma l'esito resta in cache.
- Cache in EnrichmentCache (provider "acoustid", chiave hash:{audio_hash}):
  si cacheano SOLO esiti definitivi (inclusa lista vuota = "non nel DB AcoustID").
  Errori di fingerprint/rete non si cacheano: ritentabili al run successivo.
- Il client e' iniettato -> testabile senza fpcalc ne' rete.
"""

import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Callable, Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.integrations.acoustid import AcoustIDError
from app.models import EnrichmentCache, Track

logger = logging.getLogger(__name__)

ProgressFn = Callable[[int, int, str], None]

_PROVIDER = "acoustid"
SCORE_THRESHOLD = 0.85  # sotto: candidato in cache ma nessun mbid applicato
_MIN_INTERVAL = 0.4     # AcoustID: ~3 req/s -> throttle tra i lookup di rete


class FingerprintClient(Protocol):
    def identify(self, path: str) -> list[dict[str, Any]]: ...


def _cache_key(track: Track) -> str:
    """audio_hash quando c'e' (stabile a rinomina/spostamento), altrimenti il path."""
    if track.audio_hash:
        return f"hash:{track.audio_hash}"
    return f"path:{track.local_path}"


def fingerprint_tracks(
    db: Session,
    client: FingerprintClient,
    *,
    force: bool = False,
    track_ids: list[int] | None = None,
    on_progress: ProgressFn | None = None,
) -> dict:
    """Identifica via fingerprint le tracce possedute senza mbid.

    force=True: riprocessa anche le tracce con mbid e bypassa la cache in lettura.
    Ritorna un report con i contatori (identified/below_threshold/not_found/
    cache_hits/errors/missing_files).
    """
    stmt = select(Track).where(Track.has_local_file.is_(True), Track.local_path.is_not(None))
    if track_ids is not None:
        stmt = stmt.where(Track.id.in_(track_ids))
    if not force:
        stmt = stmt.where(Track.mbid.is_(None))
    tracks = list(db.scalars(stmt).all())
    total = len(tracks)

    # Pre-carica la cache per tutte le chiavi coinvolte (come feature_enrichment).
    keys = {_cache_key(t) for t in tracks}
    rows = db.scalars(
        select(EnrichmentCache).where(
            EnrichmentCache.provider == _PROVIDER,
            EnrichmentCache.lookup_key.in_(keys) if keys else False,
        )
    ).all() if keys else []
    row_map: dict[str, EnrichmentCache] = {row.lookup_key: row for row in rows}

    identified = below_threshold = not_found = cache_hits = errors = missing_files = 0
    network_calls = 0

    for i, track in enumerate(tracks, start=1):
        key = _cache_key(track)
        candidates: list[dict[str, Any]] | None = None

        if key in row_map and not force:
            candidates = (row_map[key].result_json or {}).get("candidates") or []
            cache_hits += 1
        elif not track.local_path or not os.path.isfile(track.local_path):
            # L'indice dice "posseduta" ma il file non c'e' piu': non e' un esito
            # AcoustID, niente cache. Lo risolve una ri-indicizzazione.
            missing_files += 1
        else:
            if network_calls and _MIN_INTERVAL:
                time.sleep(_MIN_INTERVAL)
            try:
                candidates = client.identify(track.local_path)
                network_calls += 1
            except AcoustIDError as exc:
                errors += 1
                logger.warning("Fingerprint fallito per '%s': %s", track.local_path, exc)
            else:
                # Esito definitivo (anche lista vuota): upsert in cache.
                if key in row_map:
                    row_map[key].result_json = {"candidates": candidates}
                    row_map[key].cached_at = datetime.now(timezone.utc)
                else:
                    row = EnrichmentCache(provider=_PROVIDER, lookup_key=key,
                                          result_json={"candidates": candidates})
                    db.add(row)
                    row_map[key] = row

        if candidates is not None:
            if not candidates:
                not_found += 1
            elif float(candidates[0].get("score") or 0.0) >= SCORE_THRESHOLD:
                track.mbid = candidates[0]["mbid"]
                identified += 1
            else:
                below_threshold += 1

        if on_progress:
            on_progress(i, total, "fingerprint")

    db.commit()
    report = {
        "total": total,
        "identified": identified,
        "below_threshold": below_threshold,
        "not_found": not_found,
        "cache_hits": cache_hits,
        "errors": errors,
        "missing_files": missing_files,
    }
    logger.info("Fingerprint libreria: %s", report)
    return report
