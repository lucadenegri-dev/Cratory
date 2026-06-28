"""Enrichment musicale esterno: BPM, key/camelot, genere, mood, energia, label...

Separato dall'enrichment Spotify (services/enrichment.py, solo metadata editoriali).
Qui si ottengono le feature che servono al Set Builder ma che lo streaming non da'.

Regole inderogabili:
- Se la traccia ha gia' BPM/key, NON li sovrascrive.
- I dati esterni completano i campi vuoti, con `enrichment_source` e
  `enrichment_confidence` per tracciabilita'.
- Nessun dato inventato: arriva da un MusicFeatureProvider (vedi integrations/).
- Le risposte del provider vengono cachate in DB: secondo lookup a zero chiamate rete.
- Aggiorna lo stato della traccia tramite track_status.

Il provider e' iniettato (Protocol) -> testabile con un fake, senza rete.
"""

import logging
from datetime import date, datetime, timezone
from typing import Any, Callable, Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import EnrichmentCache, Track
from app.services.camelot import parse_camelot
from app.services.track_status import refresh_status

logger = logging.getLogger(__name__)

ProgressFn = Callable[[int, int, str], None]


class FeatureProvider(Protocol):
    name: str

    def lookup(
        self,
        *,
        title: str | None,
        artist: str | None,
        isrc: str | None = None,
        duration_seconds: int | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None: ...


def _cache_key(track: Track) -> str:
    """Chiave deterministica per la cache: ISRC se disponibile, altrimenti title::artist."""
    if track.isrc:
        return f"isrc:{track.isrc}"
    t = (track.title or "").strip().lower()
    a = (track.artist or "").strip().lower()
    return f"ta:{t}::{a}"


# Generi tipicamente ad alta/bassa energia: piccolo aggiustamento alla stima.
_HIGH_ENERGY_GENRES = (
    "techno", "hardcore", "hardstyle", "drum and bass", "dnb", "trance", "rave",
    "gabber", "acid", "industrial", "schranz", "speed garage", "bass", "hard",
)
_LOW_ENERGY_GENRES = (
    "ambient", "chill", "downtempo", "lo-fi", "lofi", "dub", "deep house",
    "minimal", "jazz", "soul", "acoustic", "ballad", "lounge",
)


def estimate_energy(bpm: float | None, danceability: int | None, genre: str | None) -> int | None:
    """Stima deterministica dell'energia (0-100) dai dati che abbiamo gia'.

    NON e' energia percepita "vera" (servirebbe analisi audio, non disponibile gratis):
    e' un proxy monotono utile all'arco del set. Base sul BPM nel range dance elettronico
    (~110-140), miscelato con la danceability se presente, con piccolo bias per genere.
    """
    if bpm is None:
        return None
    energy = max(0.0, min(100.0, (bpm - 110.0) / 30.0 * 100.0))
    if danceability is not None:
        energy = 0.6 * energy + 0.4 * danceability
    g = (genre or "").lower()
    if any(k in g for k in _HIGH_ENERGY_GENRES):
        energy += 12
    elif any(k in g for k in _LOW_ENERGY_GENRES):
        energy -= 12
    return int(max(0, min(100, round(energy))))


def _parse_release_date(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    if isinstance(value, str) and len(value) >= 4 and value[:4].isdigit():
        try:
            return date.fromisoformat(value if len(value) == 10 else f"{value[:4]}-01-01")
        except ValueError:
            return date(int(value[:4]), 1, 1)
    return None


def apply_features(track: Track, data: dict[str, Any], *, source: str) -> set[str]:
    """Completa i campi vuoti con i dati del provider (mai sovrascrive BPM/key esistenti)."""
    applied: set[str] = set()
    if track.bpm is None and data.get("bpm"):
        track.bpm = float(data["bpm"])
        applied.add("bpm")
    camelot = data.get("camelot_key") or data.get("key")
    if camelot and parse_camelot(camelot):
        if not track.camelot_key:
            track.camelot_key = camelot
            applied.add("camelot_key")
    if not track.genre and data.get("genre_primary"):
        track.genre = data["genre_primary"]
        applied.add("genre")
    if not track.genre_secondary and data.get("genre_secondary"):
        track.genre_secondary = data["genre_secondary"]
        applied.add("genre_secondary")
    if not track.mood and data.get("mood"):
        track.mood = data["mood"]
        applied.add("mood")
    if track.energy is None and data.get("energy") is not None:
        track.energy = int(data["energy"])
        applied.add("energy")
    if track.danceability is None and data.get("danceability") is not None:
        track.danceability = int(data["danceability"])
        applied.add("danceability")
    if track.vocalness is None and data.get("vocalness") is not None:
        track.vocalness = int(data["vocalness"])
        applied.add("vocalness")
    if not track.label and data.get("label"):
        track.label = data["label"]
        applied.add("label")
    if not track.release_date and data.get("release_date"):
        track.release_date = _parse_release_date(data["release_date"])
        if track.release_date:
            applied.add("release_date")
    if not track.isrc and data.get("isrc"):
        track.isrc = data["isrc"]
        applied.add("isrc")

    if applied:
        track.enrichment_source = source
        track.enrichment_confidence = int(data.get("confidence", 0))
        track.enriched_at = datetime.now(timezone.utc)
    refresh_status(track)
    return applied


def enrich_features(
    db: Session,
    provider: FeatureProvider,
    *,
    force: bool = False,
    playlist_id: int | None = None,
    track_ids: list[int] | None = None,
    on_progress: ProgressFn | None = None,
) -> dict:
    """Arricchisce con feature musicali le tracce che ne sono prive.

    force=True: ri-elabora tutte le tracce (anche quelle con BPM) e bypassa la cache
    in lettura (utile per forzare dati freschi dal provider, es. dopo un errore di
    rete). In ogni caso aggiorna la cache con i nuovi risultati.

    playlist_id: se valorizzato, limita l'enrichment alle tracce di quella playlist
    (auto-enrichment post-import e ri-arricchimento di una singola playlist).

    Ritorna un report con:
    enriched: tracce con almeno un campo utile applicato;
    provider_matches: risposte non vuote dal provider, anche se non hanno completato
    campi nuovi;
    with_bpm/with_key/ready_for_set/missing_core_features: stato finale del batch.
    """
    stmt = select(Track)
    if track_ids is not None:
        stmt = stmt.where(Track.id.in_(track_ids))  # arricchimento di tracce specifiche
    elif playlist_id is not None:
        from app.models import playlist_tracks
        stmt = stmt.where(Track.id.in_(
            select(playlist_tracks.c.track_id).where(playlist_tracks.c.playlist_id == playlist_id)
        ))
    if not force:
        stmt = stmt.where(Track.bpm.is_(None))
    tracks = list(db.scalars(stmt).all())
    total = len(tracks)
    enriched = provider_matches = not_found = cache_hits = metadata_enriched = 0
    field_counts: dict[str, int] = {}
    lookup_sources: dict[str, int] = {}
    metadata_fields = {"genre", "genre_secondary", "mood", "label", "release_date", "isrc"}

    provider_name = getattr(provider, "name", "external")

    # Pre-carica la cache per tutte le chiavi coinvolte (evita query N+1).
    keys = [_cache_key(t) for t in tracks]
    cached_rows = db.scalars(
        select(EnrichmentCache).where(
            EnrichmentCache.provider == provider_name,
            EnrichmentCache.lookup_key.in_(keys) if keys else False,
        )
    ).all() if keys else []
    cache_row_map: dict[str, EnrichmentCache] = {row.lookup_key: row for row in cached_rows}

    for i, track in enumerate(tracks, start=1):
        key = _cache_key(track)

        if key in cache_row_map and not force:
            data = cache_row_map[key].result_json
            cache_hits += 1
        else:
            data = provider.lookup(
                title=track.title,
                artist=track.artist,
                isrc=track.isrc,
                duration_seconds=track.duration_seconds,
            )
            # Upsert cache: aggiorna la riga esistente o inserisce una nuova.
            if key in cache_row_map:
                cache_row_map[key].result_json = data
                cache_row_map[key].cached_at = datetime.now(timezone.utc)
            else:
                new_row = EnrichmentCache(provider=provider_name, lookup_key=key, result_json=data)
                db.add(new_row)
                cache_row_map[key] = new_row

        if data:
            provider_matches += 1
            if data.get("lookup_source"):
                source = str(data["lookup_source"])
                lookup_sources[source] = lookup_sources.get(source, 0) + 1
            applied = apply_features(track, data, source=provider_name)
            if applied:
                enriched += 1
            if applied & metadata_fields:
                metadata_enriched += 1
            for field in applied:
                field_counts[field] = field_counts.get(field, 0) + 1
        else:
            not_found += 1
            refresh_status(track)

        # Energia: stima deterministica se nessun provider l'ha fornita (proxy da BPM/dance/genere).
        if track.energy is None and track.bpm is not None:
            track.energy = estimate_energy(track.bpm, track.danceability, track.genre)
            if track.energy is not None:
                field_counts["energy"] = field_counts.get("energy", 0) + 1

        if on_progress:
            on_progress(i, total, "feature")

    db.commit()
    with_bpm = sum(1 for track in tracks if track.bpm is not None)
    with_key = sum(1 for track in tracks if track.camelot_key)
    ready_for_set = sum(1 for track in tracks if track.status == "ready_for_set")
    missing_core_features = sum(1 for track in tracks if track.bpm is None or not track.camelot_key)
    logger.info(
        "Feature enrichment: %s/%s campi applicati, %s match provider, %s ready, %s cache hits, %s non trovate",
        enriched, total, provider_matches, ready_for_set, cache_hits, not_found,
    )
    return {
        "enriched": enriched,
        "provider_matches": provider_matches,
        "metadata_enriched": metadata_enriched,
        "not_found": not_found,
        "total": total,
        "cache_hits": cache_hits,
        "with_bpm": with_bpm,
        "with_key": with_key,
        "ready_for_set": ready_for_set,
        "missing_core_features": missing_core_features,
        "field_counts": dict(sorted(field_counts.items())),
        "lookup_sources": dict(sorted(lookup_sources.items())),
    }
