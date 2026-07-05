"""Sezione Etichette (deterministica).

Due responsabilita':
- ``backfill_labels``: completa ``Track.label`` leggendo l'etichetta dall'album
  Spotify completo (la label NON c'e' nell'album semplificato annidato nelle tracce
  di playlist/liked, va letta da GET /albums/{id}). Metadata editoriale, non una
  feature di mixing: non sovrascrive una label gia' presente.

  Robusto contro il rate limit di Spotify in development mode (dove i batch danno
  403 e si finisce a fare GET singole):
    * dedup album->label nello stesso run (``run_cache``) -> un fetch per album;
    * le tracce gia' etichettate escono dai candidati -> i run futuri non le ritoccano;
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
from app.models import Track

logger = logging.getLogger(__name__)

_MAX_GENRES_PER_LABEL = 6

# "X under exclusive licence to Y" -> tiene solo Y (l'etichetta del master).
_LICENCE_RE = re.compile(r".*\bunder exclusive licen[cs]e to\s+", re.IGNORECASE)
# Suffissi societari finali da rimuovere ("Warp Records Limited" -> "Warp Records").
_LEGAL_SUFFIX_RE = re.compile(
    r"[\s,]+(?:Limited|Ltd\.?|LLC|Inc\.?|GmbH|B\.?V\.?|S\.?r\.?l\.?|S\.?A\.?|Pty\.?\s*Ltd\.?|Co\.?)\s*$",
    re.IGNORECASE,
)


def _clean_label(raw: str | None) -> str | None:
    """Normalizza il nome etichetta da un copyright verboso.

    - "X under exclusive licence to Y" -> Y (l'etichetta del master).
    - rimuove i suffissi societari finali (Limited/Ltd/LLC/Inc/GmbH/...).
    Idempotente: un nome gia' pulito resta invariato.
    """
    if not raw:
        return None
    s = raw.strip()
    s = _LICENCE_RE.sub("", s)          # tieni solo cio' dopo "under ... licence to"
    prev = None
    while prev != s:                    # strip ripetuto (es. "Records Limited Ltd")
        prev = s
        s = _LEGAL_SUFFIX_RE.sub("", s).strip()
    return s or None


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
    return _clean_label(s)


def _is_rate_limit(exc: SpotifyError) -> bool:
    return "rate limit" in str(exc).lower()


def album_label(client, album_id: str) -> str | None:
    """Etichetta (pulita) di un album Spotify. Ritorna None se non risolvibile.

    Usata dal Discovery per annotare i candidati (che gia' deduplica per album nel
    proprio run). Nessuna cache persistente dopo lo slim-down dello schema:
    l'etichetta si rilegge dalla rete quando serve.
    """
    if not album_id:
        return None
    try:
        obj = client.get_album(album_id)
    except SpotifyError:
        return None
    label = None
    if obj:
        label = obj.get("label") or _label_from_copyrights(obj.get("copyrights"))
    return _clean_label(label)


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

        # 1) traccia -> album (una lookup: l'album non e' piu' persistito sulla traccia)
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
        if not album_id:
            continue

        # 2) album -> label (dedup nello stesso run, poi rete)
        if album_id in run_cache:
            label = run_cache[album_id]
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

    # Merge a read-time delle varianti dello stesso label (es. "Warp Records
    # Limited" e "Warp Records Ltd" -> "Warp Records"): nessuna migrazione dati.
    buckets: dict[str, list[Track]] = {}
    for t in tracks:
        key = _clean_label(t.label) or t.label
        buckets.setdefault(key, []).append(t)

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
