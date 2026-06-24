"""Discovery v2 — "crate digging": lista-dig a volume da Discogs.

A differenza dell'espansione playlist (Last.fm -> resolver Spotify, ~20 candidati
risolti), il dig produce TANTI lead leggeri NON risolti dai semi Genere/Etichetta,
ordinati per profondita' + novita' (deep cut). L'identita' Spotify si risolve solo al
salvataggio (riusa l'import idempotente). Sorgente: Discogs (vedi integrations/discogs).

Deterministico e testabile: la funzione di ricerca Discogs e' iniettata.
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.services.discovery import _key, _library_tracks, _norm

logger = logging.getLogger(__name__)

DEFAULT_DIG_LIMIT = 80
# Sopra questo numero di "have" un disco e' molto diffuso: novita' ~0 (non un deep cut).
_HAVE_CAP = 5000
_VARIOUS = {"various", "various artists", "va", "unknown artist"}

SearchReleases = Callable[..., list[dict[str, Any]]]


@dataclass
class DiscoveryLead:
    artist: str
    title: str
    year: int | None = None
    label: str | None = None
    style: str | None = None
    source: str = "discogs"
    seed: str | None = None
    discogs_id: int | None = None
    discogs_url: str | None = None
    thumb_url: str | None = None
    have: int = 0
    want: int = 0
    isrc: str | None = None
    score: float = 0.0


@dataclass
class DigResult:
    seed_type: str
    value: str
    leads: list[DiscoveryLead] = field(default_factory=list)


def _parse_year(value: Any) -> int | None:
    m = re.match(r"\s*(\d{4})", str(value or ""))
    return int(m.group(1)) if m else None


def _first(seq: Any) -> str | None:
    return seq[0] if isinstance(seq, list) and seq else None


def _lead_from_release(item: dict[str, Any], seed: str) -> DiscoveryLead | None:
    """Costruisce un lead da un result di /database/search. Scarta i 'Various'/non splittabili."""
    title = item.get("title") or ""
    if " - " not in title:
        return None
    artist, _, track_title = title.partition(" - ")
    artist, track_title = artist.strip(), track_title.strip()
    if not artist or not track_title or artist.lower() in _VARIOUS:
        return None
    community = item.get("community") or {}
    uri = item.get("uri") or ""
    return DiscoveryLead(
        artist=artist, title=track_title,
        year=_parse_year(item.get("year")),
        label=_first(item.get("label")),
        style=_first(item.get("style")),
        source="discogs", seed=seed,
        discogs_id=item.get("id"),
        discogs_url=f"https://www.discogs.com{uri}" if uri.startswith("/") else (uri or None),
        thumb_url=item.get("cover_image") or item.get("thumb") or None,
        have=int(community.get("have") or 0),
        want=int(community.get("want") or 0),
    )


def _recency(year: int | None, current_year: int) -> float:
    """0..1: piu' recente -> piu' alto (lineare sugli ultimi 15 anni)."""
    if not year:
        return 0.0
    span = 15
    return max(0.0, min(1.0, (year - (current_year - span)) / span))


def _score(lead: DiscoveryLead, owned_artists: set[str], adventurousness: float, current_year: int) -> float:
    """Profondita' + novita'. `adventurousness` 0..1 pesa novita' (deep cut) vs familiarita'.

    - novelty: meno copie possedute nel mondo (have) -> piu' deep cut.
    - familiarity: artista gia' in libreria (rassicurante quando adventurousness e' basso).
    - recency: piccolo bonus ai brani recenti.
    """
    novelty = 1.0 - min(lead.have, _HAVE_CAP) / _HAVE_CAP
    familiarity = 1.0 if _norm(lead.artist) in owned_artists else 0.0
    recency = _recency(lead.year, current_year)
    return adventurousness * novelty + (1.0 - adventurousness) * familiarity + 0.2 * recency


def dig(
    db: Session,
    *,
    seed_type: str,
    value: str,
    search_releases: SearchReleases,
    library: list | None = None,
    adventurousness: float = 0.4,
    limit: int = DEFAULT_DIG_LIMIT,
) -> DigResult:
    """Lead non posseduti dal seme dato (genere|etichetta), ordinati per profondita'+novita'."""
    if library is None:
        library = _library_tracks(db)
    owned_keys = {_key(t.artist or "", t.title or "") for t in library if t.artist and t.title}
    owned_artists = {_norm(t.artist) for t in library if t.artist}

    if seed_type == "genre":
        items = search_releases(style=value) or search_releases(genre=value)
    elif seed_type == "label":
        items = search_releases(label=value)
    else:
        items = []

    leads: list[DiscoveryLead] = []
    seen: set[tuple[str, str]] = set()
    for item in items or []:
        lead = _lead_from_release(item, value)
        if lead is None:
            continue
        k = _key(lead.artist, lead.title)
        if k in owned_keys or k in seen:  # dedup vs libreria e tra release/pressature
            continue
        seen.add(k)
        leads.append(lead)

    adv = max(0.0, min(1.0, adventurousness))
    current_year = datetime.now(timezone.utc).year
    for lead in leads:
        lead.score = _score(lead, owned_artists, adv, current_year)
    leads.sort(key=lambda x: x.score, reverse=True)

    logger.info("Discovery dig %s=%r: %s lead (adv=%.2f)", seed_type, value, len(leads[:limit]), adv)
    return DigResult(seed_type=seed_type, value=value, leads=leads[:limit])
