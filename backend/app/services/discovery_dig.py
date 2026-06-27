"""Discovery v2 — "crate digging": lista-dig a volume da Discogs.

A differenza dell'espansione playlist (Last.fm -> resolver Spotify, ~20 candidati
risolti), il dig produce TANTI lead leggeri NON risolti dai semi Genere/Etichetta,
ordinati per profondita' + novita' (deep cut). L'identita' Spotify si risolve solo al
salvataggio (riusa l'import idempotente). Sorgente: Discogs (vedi integrations/discogs).

De-noise: distingue la gemma rara dal rumore self-released con la DOMANDA (want vs
have), scarta formati off-target (compilation/DJ mix) e self-released morti, deduplica
le varianti ("(Original Mix)") e limita quante voci per artista.

Deterministico e testabile: la funzione di ricerca Discogs e' iniettata.
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.services.discovery import _library_tracks, _norm

logger = logging.getLogger(__name__)

DEFAULT_DIG_LIMIT = 80
# Sopra questo numero di "have" un disco e' molto diffuso: novita' ~0 (non un deep cut).
_HAVE_CAP = 5000
_MAX_PER_ARTIST = 2  # un artista non deve monopolizzare la lista
_VARIOUS = {"various", "various artists", "va", "unknown artist"}
# Formati che un DJ NON vuole tra i lead (vuole release singole, non mix gia' fatti).
_BAD_FORMATS = {"compilation", "dj mix", "mixed", "mixtape"}
# Etichetta "non etichetta": segnale di autoproduzione.
_SELF_RELEASED_RE = re.compile(r"not on label|self[- ]released", re.IGNORECASE)
# Suffisso finale tra parentesi che indica una variante (mix/edit/version/...): per la dedup.
_VARIANT_RE = re.compile(
    r"\s*[\(\[][^\)\]]*\b(mix|edit|version|remaster|remastered|dub|instrumental|rework|vip|re-?edit)\b[^\)\]]*[\)\]]\s*$",
    re.IGNORECASE,
)

# Pesi del termine "gusto" nello score (somma 1.0). Tarabili.
W_ARTIST = 0.5
W_LABEL = 0.3
W_STYLE = 0.2
# Quante release di un artista nel riferimento bastano per familiarita' piena.
FAMILIARITY_FULL_AT = 3

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


def _is_self_released(labels: Any) -> bool:
    return any(_SELF_RELEASED_RE.search(str(label)) for label in (labels or []))


def _dedup_title(title: str) -> str:
    """Rimuove il suffisso di variante finale ('(Original Mix)', '[Radio Edit]') per la dedup."""
    prev = None
    s = title
    while prev != s:
        prev = s
        s = _VARIANT_RE.sub("", s).strip()
    return s


def _dedup_key(artist: str, title: str) -> tuple[str, str]:
    return _norm(artist), _norm(_dedup_title(title))


def _style_tokens(value: Any) -> set[str]:
    """Token normalizzati di uno style/genere ('Deep House' -> {'deep','house'})."""
    return {tok for tok in re.split(r"[^a-z0-9]+", _norm(value)) if tok}


@dataclass
class TasteProfile:
    """Riassunto deterministico del gusto di un riferimento (libreria o playlist).

    Costruito da una lista di Track-like (servono artist, label, genre).
    Indipendente dalla dedup: misura affinita', non possesso.
    """
    artist_counts: dict[str, int] = field(default_factory=dict)
    owned_labels: set[str] = field(default_factory=set)
    genre_tokens: set[str] = field(default_factory=set)

    @classmethod
    def from_tracks(cls, tracks: list) -> "TasteProfile":
        artist_counts: dict[str, int] = {}
        owned_labels: set[str] = set()
        genre_tokens: set[str] = set()
        for t in tracks or []:
            a = _norm(getattr(t, "artist", None))
            if a:
                artist_counts[a] = artist_counts.get(a, 0) + 1
            lbl = _norm(getattr(t, "label", None))
            if lbl:
                owned_labels.add(lbl)
            genre_tokens |= _style_tokens(getattr(t, "genre", None))
        return cls(artist_counts, owned_labels, genre_tokens)

    def artist_count(self, artist: str) -> int:
        return self.artist_counts.get(_norm(artist), 0)

    def familiarity(self, artist: str) -> float:
        return min(self.artist_count(artist) / FAMILIARITY_FULL_AT, 1.0)

    def label_affinity(self, label: str | None) -> float:
        return 1.0 if label and _norm(label) in self.owned_labels else 0.0

    def style_affinity(self, style: str | None) -> float:
        return 1.0 if _style_tokens(style) & self.genre_tokens else 0.0


def _lead_from_release(item: dict[str, Any], seed: str) -> DiscoveryLead | None:
    """Lead da un result di /database/search, con filtri anti-rumore.

    Scarta: titoli non splittabili, Various, formati off-target (compilation/DJ mix),
    e i self-released 'morti' (nessuno li ha ne' li cerca).
    """
    title = item.get("title") or ""
    if " - " not in title:
        return None
    artist, _, track_title = title.partition(" - ")
    artist, track_title = artist.strip(), track_title.strip()
    if not artist or not track_title or artist.lower() in _VARIOUS:
        return None
    formats = {str(f).lower() for f in (item.get("format") or [])}
    if formats & _BAD_FORMATS:
        return None
    community = item.get("community") or {}
    have = int(community.get("have") or 0)
    want = int(community.get("want") or 0)
    labels = item.get("label") or []
    # self-released che nessuno ha ne' cerca: rumore, non una gemma rara.
    if have == 0 and want == 0 and _is_self_released(labels):
        return None
    uri = item.get("uri") or ""
    return DiscoveryLead(
        artist=artist, title=track_title,
        year=_parse_year(item.get("year")),
        label=_first(labels),
        style=_first(item.get("style")),
        source="discogs", seed=seed,
        discogs_id=item.get("id"),
        discogs_url=f"https://www.discogs.com{uri}" if uri.startswith("/") else (uri or None),
        thumb_url=item.get("cover_image") or item.get("thumb") or None,
        have=have, want=want,
    )


def _recency(year: int | None, current_year: int) -> float:
    """0..1: piu' recente -> piu' alto (lineare sugli ultimi 15 anni)."""
    if not year:
        return 0.0
    span = 15
    return max(0.0, min(1.0, (year - (current_year - span)) / span))


def _demand(have: int, want: int) -> float:
    """0..1: quanto e' RICHIESTO rispetto a quanto e' posseduto.

    Una gemma rara ha pochi che la hanno ma molti che la vogliono (want >> have);
    il self-released morto ha want=0 -> domanda 0. Distingue rarita' da rumore.
    """
    if want <= 0:
        return 0.0
    return want / (have + want)


def _score(lead: DiscoveryLead, owned_artists: set[str], adventurousness: float, current_year: int) -> float:
    """Familiarita' (gusto noto) vs scoperta (novita' + domanda), pesate da adventurousness.

    A `adventurousness` alto contano novita' E domanda insieme: cosi' le rarita'
    *richieste* salgono e il self-released anonimo (want=0) resta in basso.
    """
    novelty = 1.0 - min(lead.have, _HAVE_CAP) / _HAVE_CAP
    demand = _demand(lead.have, lead.want)
    discovery = 0.5 * novelty + 0.5 * demand
    familiarity = 1.0 if _norm(lead.artist) in owned_artists else 0.0
    recency = _recency(lead.year, current_year)
    return adventurousness * discovery + (1.0 - adventurousness) * familiarity + 0.2 * recency


def _select(leads: list[DiscoveryLead], limit: int) -> list[DiscoveryLead]:
    """Ordina per score e applica il cap per artista (no monopolio), poi tronca a limit."""
    out: list[DiscoveryLead] = []
    per_artist: dict[str, int] = {}
    for lead in sorted(leads, key=lambda x: x.score, reverse=True):
        a = _norm(lead.artist)
        if per_artist.get(a, 0) >= _MAX_PER_ARTIST:
            continue
        per_artist[a] = per_artist.get(a, 0) + 1
        out.append(lead)
        if len(out) >= limit:
            break
    return out


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
    """Lead non posseduti dal seme dato (genere|etichetta), de-noised e ordinati per gusto."""
    if library is None:
        library = _library_tracks(db)
    owned_keys = {_dedup_key(t.artist or "", t.title or "") for t in library if t.artist and t.title}
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
        k = _dedup_key(lead.artist, lead.title)  # collassa varianti e pressature
        if k in owned_keys or k in seen:
            continue
        seen.add(k)
        leads.append(lead)

    adv = max(0.0, min(1.0, adventurousness))
    current_year = datetime.now(timezone.utc).year
    for lead in leads:
        lead.score = _score(lead, owned_artists, adv, current_year)
    selected = _select(leads, limit)

    logger.info("Discovery dig %s=%r: %s lead (adv=%.2f)", seed_type, value, len(selected), adv)
    return DigResult(seed_type=seed_type, value=value, leads=selected)
