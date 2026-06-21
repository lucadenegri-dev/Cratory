"""Sezione Etichette (deterministica).

Due responsabilita':
- ``backfill_labels``: completa ``Track.label`` leggendo l'etichetta dall'album
  Spotify completo (la label NON c'e' nell'album semplificato annidato nelle tracce
  di playlist/liked, va letta da GET /albums/{id}). Metadata editoriale, non una
  feature di mixing: non sovrascrive una label gia' presente.

  Robusto contro il rate limit di Spotify in development mode (dove i batch danno
  403 e si finisce a fare GET singole):
    * ``album_id`` memorizzato sulla traccia -> i run futuri saltano la lookup traccia;
    * cache album->label in ``EnrichmentCache`` -> niente ri-fetch;
    * budget di lookup per chiamata (``max_lookups``) -> nessuna raffica;
    * stop pulito sul rate limit (commit parziale + report), niente lavoro perso.
- ``labels_overview``: aggrega la libreria per etichetta (conteggi + info derivate).
"""

import logging
import re
import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.integrations.spotify import SpotifyError
from app.models import EnrichmentCache, Track

logger = logging.getLogger(__name__)

_MAX_GENRES_PER_LABEL = 6
# v2: da nov. 2024 Spotify non espone piu' `label` su GET /albums/{id} in
# development mode; l'etichetta si ricava da `copyrights`. Il bump invalida le
# voci di cache "label None" salvate dalla versione precedente (bug).
_ALBUM_LABEL_PROVIDER = "spotify_album_label_v2"


def _spotify_track_id(track: Track) -> str | None:
    return track.spotify_id or track.platform_track_id


def _label_from_copyrights(copyrights) -> str | None:
    """Ricava il nome dell'etichetta dai ``copyrights`` dell'album.

    Da novembre 2024 Spotify non espone piu' il campo ``label`` su
    GET /albums/{id} per le app in development mode, ma resta ``copyrights``.
    Si preferisce il copyright fonografico (tipo ``"P"``), che nomina l'owner del
    master / l'etichetta; si rimuovono simboli (©/℗/(C)/(P)) e l'anno iniziale.
    """
    if not copyrights:
        return None
    phono = corp = other = None
    for entry in copyrights:
        text = (entry or {}).get("text")
        if not text:
            continue
        typ = (entry or {}).get("type")
        if typ == "P" and phono is None:
            phono = text
        elif typ == "C" and corp is None:
            corp = text
        elif other is None:
            other = text
    text = phono or corp or other
    if not text:
        return None
    s = re.sub(r"^[\s©℗]+", "", text.strip())
    s = re.sub(r"^\(\s*[cp]\s*\)\s*", "", s, flags=re.IGNORECASE)
    s = re.sub(r"^\s*\d{4}\s+", "", s).strip()
    return s or None


def _is_rate_limit(exc: SpotifyError) -> bool:
    return "rate limit" in str(exc).lower()


def _cached_album(db: Session, album_id: str) -> EnrichmentCache | None:
    return db.scalar(
        select(EnrichmentCache).where(
            EnrichmentCache.provider == _ALBUM_LABEL_PROVIDER,
            EnrichmentCache.lookup_key == album_id,
        )
    )


def _cache_album_label(db: Session, album_id: str, label: str | None) -> None:
    db.add(EnrichmentCache(
        provider=_ALBUM_LABEL_PROVIDER, lookup_key=album_id,
        result_json={"label": label} if label else None,
    ))


def backfill_labels(
    db: Session, client, tracks: list[Track] | None = None,
    *, max_lookups: int = 60, force: bool = False, pause: float = 0.0,
) -> dict:
    """Popola ``Track.label`` dall'album Spotify. Bounded e ripetibile. Ritorna un report.

    ``client`` espone ``get_track_metadata(id)`` e ``get_album(id)`` (GET singole).
    ``max_lookups`` limita le chiamate di rete per invocazione: se restano candidati,
    il report riporta ``remaining`` > 0 e basta rilanciare.
    """
    if tracks is None:
        tracks = list(db.scalars(select(Track)).all())

    candidates = [
        t for t in tracks
        if _spotify_track_id(t) is not None and (force or not t.label)
    ]

    updated = 0
    lookups = 0
    rate_limited = False
    run_cache: dict[str, str | None] = {}  # album_id -> label (dedup nello stesso run)

    for track in candidates:
        if lookups >= max_lookups:
            break

        # 1) album_id (dalla traccia se gia' noto, altrimenti una lookup traccia)
        album_id = track.album_id
        if not album_id:
            sid = _spotify_track_id(track)
            try:
                obj = client.get_track_metadata(sid)
                lookups += 1
                if pause:
                    time.sleep(pause)
            except SpotifyError as exc:
                if _is_rate_limit(exc):
                    rate_limited = True
                    break
                logger.warning("Backfill label: lookup traccia %s fallita: %s", sid, exc)
                continue
            album_id = (obj.get("album") or {}).get("id") if obj else None
            track.album_id = album_id
        if not album_id:
            continue

        # 2) album -> label (run cache -> EnrichmentCache -> rete)
        if album_id in run_cache:
            label = run_cache[album_id]
        else:
            cached = _cached_album(db, album_id)
            if cached is not None:
                label = (cached.result_json or {}).get("label")
            else:
                if lookups >= max_lookups:
                    break
                try:
                    obj = client.get_album(album_id)
                    lookups += 1
                    if pause:
                        time.sleep(pause)
                except SpotifyError as exc:
                    if _is_rate_limit(exc):
                        rate_limited = True
                        break
                    logger.warning("Backfill label: lookup album %s fallita: %s", album_id, exc)
                    continue
                label = None
                if obj:
                    label = obj.get("label") or _label_from_copyrights(obj.get("copyrights"))
                _cache_album_label(db, album_id, label)
            run_cache[album_id] = label

        if label and (force or not track.label):
            track.label = label
            updated += 1

    db.commit()
    remaining = sum(1 for t in candidates if not t.label)
    report = {
        "updated": updated,
        "candidates": len(candidates),
        "remaining": remaining,
        "rate_limited": rate_limited,
    }
    logger.info("Backfill label da Spotify: %s", report)
    return report


def labels_overview(db: Session) -> list[dict]:
    """Aggrega la libreria per etichetta. Ritorna una lista ordinata per conteggio desc.

    Ogni voce: label, track_count, artist_count, generi distinti (cap), range anni.
    """
    tracks = db.scalars(
        select(Track).where(Track.label.is_not(None), Track.label != "")
    ).all()

    buckets: dict[str, list[Track]] = {}
    for t in tracks:
        buckets.setdefault(t.label, []).append(t)

    out: list[dict] = []
    for label, items in buckets.items():
        artists = {t.artist for t in items if t.artist}
        genres = {t.genre for t in items if t.genre}
        years = [t.year for t in items if t.year]
        out.append({
            "label": label,
            "track_count": len(items),
            "artist_count": len(artists),
            "genres": sorted(genres)[:_MAX_GENRES_PER_LABEL],
            "year_min": min(years) if years else None,
            "year_max": max(years) if years else None,
        })

    out.sort(key=lambda o: (-o["track_count"], o["label"].lower()))
    return out
