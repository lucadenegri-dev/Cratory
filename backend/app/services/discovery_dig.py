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
import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.integrations.discogs import DISCOGS_MAX_PAGES, SEARCH_PER_PAGE
from app.services.discovery import _library_tracks, _norm

logger = logging.getLogger(__name__)

DEFAULT_DIG_LIMIT = 80

PAGES_PER_DIG = 3  # quante pagine scarica un dig: 3 richieste di contenuto


def _window(depth: float, total_items: int) -> list[int]:
    """Le pagine da scaricare dalla pila ordinata per domanda.

    depth 0 = il canone del seme, depth 1 = il fondo della pila. La pila regge per
    tutta la sua lunghezza: a rango 9901-10000 il `want` mediano e' ancora 89, e a
    NESSUNA profondita' esiste un disco con want<5 (misurato su style=Acid House).

    Su una pila piu' corta della finestra, `depth` non ha effetto: non c'e' profondita'
    da scegliere. Il chiamante lo segnala alla UI via `pile_pages`.
    """
    usable = min(math.ceil(total_items / SEARCH_PER_PAGE), DISCOGS_MAX_PAGES)
    if usable <= 0:
        return []
    start = 1 + round(max(0.0, min(1.0, depth)) * max(0, usable - PAGES_PER_DIG))
    # il `- 1` non e' cosmetico: senza, la finestra e' di 4 pagine e ogni dig
    # spende una richiesta di troppo.
    return list(range(start, min(start + PAGES_PER_DIG - 1, usable) + 1))


_MAX_PER_ARTIST = 2  # un artista non deve monopolizzare la lista
_VARIOUS = {"various", "various artists", "va", "unknown artist"}
# Formati che un DJ NON vuole tra i lead (vuole release singole, non mix gia' fatti).
_BAD_FORMATS = {"compilation", "dj mix", "mixed", "mixtape"}
# Etichetta "non etichetta": segnale di autoproduzione.
_SELF_RELEASED_RE = re.compile(r"not on label|self[- ]released", re.IGNORECASE)

# Grammatica di Discogs: gli omonimi sono disambiguati con '*' o '(N)' — 'Tyree*',
# 'Gravity Zero (4)'. Non sono parte del nome: senza toglierli, il 17% dei lead non
# aggancia la libreria (misurato su style=Acid House).
_DISCOGS_CRUFT_RE = re.compile(r"\*|\s*\(\d+\)")
# Piu' artisti in un campo: 'Nail / Einzelkind'. Si spezza SOLO sui separatori non
# ambigui: '/' con spazi attorno e' la convenzione Discogs per le split release.
# '&' e ',' sono ESCLUSI apposta: separano artisti ('Yen Sung & Photonz') ma compaiono
# anche dentro i nomi di band ('Earth, Wind & Fire') e non c'e' modo di distinguerli.
# Decide l'asimmetria del danno: un match MANCATO lascia un lead non valorizzato (finisce
# piu' in basso in lista), un match SBAGLIATO mette in cima un disco che non c'entra.
# Si preferisce mancare. La chiave intera resta comunque prima: 'Above & Beyond' matcha
# per intero se ce l'hai.
_ARTIST_SPLIT_RE = re.compile(r"\s+(?:/|feat\.?|vs\.?)\s+", re.IGNORECASE)

# Suffisso di FORMATO: il titolo di una release Discogs e' spesso il nome di un EP/LP,
# mentre Track.title e' il titolo di una TRACCIA. Senza toglierlo, 'Piercing Love EP'
# non riconosce la traccia 'Piercing Love' che possiedi.
_FORMAT_SUFFIX_RE = re.compile(r"\s+(?:ep|lp|12\"|single)\s*$", re.IGNORECASE)


def _clean_artist(raw: str) -> tuple[str, list[str]]:
    """(stringa da mostrare, chiavi normalizzate per il match).

    La chiave INTERA viene per prima: 'Above & Beyond' e' un artista solo e deve
    poter matchare per intero. Le parti seguono, per gli split veri
    ('Nail / Einzelkind': se collezioni Einzelkind, il lead e' rilevante).
    """
    display = _DISCOGS_CRUFT_RE.sub("", raw or "").strip()
    parts = [p.strip() for p in _ARTIST_SPLIT_RE.split(display) if p.strip()]
    keys = [_norm(display), *(_norm(p) for p in parts)]
    return display, [k for k in dict.fromkeys(keys) if k]


# Suffisso finale tra parentesi che indica una variante (mix/edit/version/...): per la dedup.
_VARIANT_RE = re.compile(
    r"\s*[\(\[][^\)\]]*\b(mix|edit|version|remaster|remastered|dub|instrumental|rework|vip|re-?edit)\b[^\)\]]*[\)\]]\s*$",
    re.IGNORECASE,
)

# Badge di formato per la UI (grid cell): primo match in ordine di priorità sui
# descrittori Discogs. Match ESATTO (intersezione di insiemi), non per sostringa:
# 'ep' e' sottostringa di 'repress' (r-e-p...), e le ristampe sono frequentissime
# nel crate digging — una ristampa LP verrebbe marcata "EP". Il campo `format` e'
# gia' nella risposta di /database/search: nessuna chiamata di rete aggiuntiva.
_FORMAT_BADGES = [
    ({"ep"}, "EP"),
    ({"lp"}, "LP"),
    ({"album"}, "Album"),
    ({"single"}, "Single"),
    ({'12"'}, '12"'),
]


def _format_badge(formats: set[str]) -> str | None:
    for needles, badge in _FORMAT_BADGES:
        if needles & formats:
            return badge
    return None


# Pesi del termine "gusto" nello score (somma 1.0). Tarabili.
W_ARTIST = 0.5
W_LABEL = 0.3
W_STYLE = 0.2
# Quante release di un artista nel riferimento bastano per familiarita' piena.
FAMILIARITY_FULL_AT = 3

# Soglie per i reason code (spiegazioni). Costanti, deterministiche.
REASON_RARE_MIN_WANT = 10       # almeno 10 persone lo cercano
REASON_RARE_MIN_DEMAND = 0.5    # want/(have+want) >= 0.5
REASON_DEEP_CUT_MAX_HAVE = 50   # pochissimi lo possiedono
REASON_RECENT_MIN = 0.8         # recency alta (ultimi ~3 anni su span 15)

SearchReleases = Callable[..., list[dict[str, Any]]]


@dataclass
class Reason:
    """Spiegazione strutturata: codice + payload dati. Il testo lo compone la UI."""
    code: str
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class DiscoveryLead:
    artist: str
    title: str
    year: int | None = None
    label: str | None = None
    styles: list[str] = field(default_factory=list)   # TUTTI gli style della release
    artist_keys: list[str] = field(default_factory=list)  # interno: match, non DTO
    source: str = "discogs"
    seed: str | None = None
    discogs_id: int | None = None
    discogs_url: str | None = None
    thumb_url: str | None = None
    have: int = 0
    want: int = 0
    format_badge: str | None = None    # EP | LP | Album | Single | 12" | None
    isrc: str | None = None
    score: float = 0.0
    reasons: list[Reason] = field(default_factory=list)


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


def _title_candidates(title: str) -> list[str]:
    """Tutti i titoli sotto cui una release puo' essere gia' in libreria.

    Il titolo di una release non e' il titolo di una traccia: puo' essere un EP
    ('Piercing Love EP') o due lati in un campo ('Sentipede / 808 Rhythm Traxx 3').
    """
    sides = [s.strip() for s in title.split(" / ")] if " / " in title else []
    out: list[str] = []
    for raw in [title, *sides]:
        t = _dedup_title(raw)
        out.append(t)
        stripped = _FORMAT_SUFFIX_RE.sub("", t).strip()
        if stripped:
            out.append(stripped)
    return [x for x in dict.fromkeys(out) if x]


def _owned_index(library: list) -> tuple[set[tuple[str, str]], set[tuple[str, str]]]:
    """Due indici del posseduto: per titolo di traccia e per album.

    Gli artisti della libreria vengono da tag/streaming: niente grammatica Discogs
    da ripulire, `_norm` basta.
    """
    tracks: set[tuple[str, str]] = set()
    albums: set[tuple[str, str]] = set()
    for t in library or []:
        a = _norm(getattr(t, "artist", None))
        if not a:
            continue
        if getattr(t, "title", None):
            tracks.add((a, _norm(_dedup_title(t.title))))
        if getattr(t, "album", None):
            albums.add((a, _norm(_dedup_title(t.album))))
    return tracks, albums


def _is_owned(lead: DiscoveryLead, owned_tracks: set, owned_albums: set) -> bool:
    """Un falso positivo costa un lead in meno; un falso negativo mostra all'utente
    un disco che ha gia'. Il secondo e' l'errore che si vede: si preferisce escludere.
    """
    for a in lead.artist_keys:
        for t in _title_candidates(lead.title):
            k = (a, _norm(t))
            if k in owned_tracks or k in owned_albums:
                return True
    return False


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
    # Un set di token PER GENERE DISTINTO, non un'unione: contro un sacco unico
    # bastava 'house' per valere 1.0 su qualunque release house.
    genre_sets: list[set[str]] = field(default_factory=list)

    @classmethod
    def from_tracks(cls, tracks: list) -> "TasteProfile":
        artist_counts: dict[str, int] = {}
        owned_labels: set[str] = set()
        genres: set[str] = set()
        for t in tracks or []:
            a = _norm(getattr(t, "artist", None))
            if a:
                artist_counts[a] = artist_counts.get(a, 0) + 1
            lbl = _norm(getattr(t, "label", None))
            if lbl:
                owned_labels.add(lbl)
            g = _norm(getattr(t, "genre", None))
            if g:
                genres.add(g)
        genre_sets = [toks for toks in map(_style_tokens, genres) if toks]
        return cls(artist_counts, owned_labels, genre_sets)

    def artist_count(self, artist_keys: list[str]) -> int:
        return max((self.artist_counts.get(k, 0) for k in artist_keys), default=0)

    def familiarity(self, artist_keys: list[str]) -> float:
        return min(self.artist_count(artist_keys) / FAMILIARITY_FULL_AT, 1.0)

    def label_affinity(self, label: str | None) -> float:
        return 1.0 if label and _norm(label) in self.owned_labels else 0.0

    def style_affinity(self, styles: list[str]) -> float:
        """Jaccard massima tra gli style della release e i generi della libreria.

        'Deep House' vs libreria con 'Deep House' -> 1.0; vs sola 'Acid House' -> 0.33
        ({house} / {deep, house, acid}); vs sola 'Drum n Bass' -> 0.0.
        """
        best = 0.0
        for s in (toks for toks in map(_style_tokens, styles or []) if toks):
            for g in self.genre_sets:
                best = max(best, len(s & g) / len(s | g))
        return best


def _lead_from_release(item: dict[str, Any], seed: str) -> DiscoveryLead | None:
    """Lead da un result di /database/search, con filtri anti-rumore.

    Scarta: titoli non splittabili, Various, formati off-target (compilation/DJ mix),
    e i self-released 'morti' (nessuno li ha ne' li cerca).
    """
    title = item.get("title") or ""
    if " - " not in title:
        return None
    artist_raw, _, track_title = title.partition(" - ")
    artist_raw, track_title = artist_raw.strip(), track_title.strip()
    if not artist_raw or not track_title or artist_raw.lower() in _VARIOUS:
        return None
    artist, artist_keys = _clean_artist(artist_raw)
    if not artist or not artist_keys:
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
        artist=artist, artist_keys=artist_keys, title=track_title,
        year=_parse_year(item.get("year")),
        label=_first(labels),
        styles=[str(s) for s in (item.get("style") or [])],
        source="discogs", seed=seed,
        discogs_id=item.get("id"),
        discogs_url=f"https://www.discogs.com{uri}" if uri.startswith("/") else (uri or None),
        thumb_url=item.get("cover_image") or item.get("thumb") or None,
        have=have, want=want,
        format_badge=_format_badge(formats),
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


@dataclass(frozen=True)
class Weights:
    artist: float
    label: float
    style: float


def _weights(seed_type: str) -> Weights:
    """I segnali costanti per costruzione escono, e il peso si redistribuisce.

    Su un dig per etichetta ogni lead ha l'etichetta del seme: `label_affinity` vale
    1.0 per tutti. E' una costante additiva — non ordina, e dilava gli altri segnali.
    Su un dig per genere invece Discogs restituisce PIU' style per release, quindi lo
    style del seme non e' l'unico e `style_affinity` conserva potere discriminante.
    """
    if seed_type == "label":
        rest = W_ARTIST + W_STYLE
        return Weights(artist=W_ARTIST / rest, label=0.0, style=W_STYLE / rest)
    return Weights(artist=W_ARTIST, label=W_LABEL, style=W_STYLE)


def _score(lead: DiscoveryLead, profile: TasteProfile, weights: Weights) -> float:
    """Solo gusto. La domanda l'ha gia' codificata la finestra (`_window`): dentro una
    finestra il `want` e' ~costante, quindi non ordina. La profondita' sceglie il
    bacino, il gusto ordina — sempre, non come modalita'.
    """
    return (
        weights.artist * profile.familiarity(lead.artist_keys)
        + weights.label * profile.label_affinity(lead.label)
        + weights.style * profile.style_affinity(lead.styles)
    )


def _reasons(lead: DiscoveryLead, profile: TasteProfile, current_year: int) -> list[Reason]:
    """Emette i reason code attivi per un lead, secondo soglie deterministiche."""
    out: list[Reason] = []
    if lead.want >= REASON_RARE_MIN_WANT and _demand(lead.have, lead.want) >= REASON_RARE_MIN_DEMAND:
        out.append(Reason("rare_wanted", {"have": lead.have, "want": lead.want}))
    if lead.have <= REASON_DEEP_CUT_MAX_HAVE:
        out.append(Reason("deep_cut", {"have": lead.have}))
    if profile.label_affinity(lead.label) > 0:
        out.append(Reason("label_followed", {"label": lead.label}))
    count = profile.artist_count(lead.artist)
    if count > 0:
        out.append(Reason("artist_collected", {"artist": lead.artist, "count": count}))
    if profile.style_affinity(lead.style) > 0:
        out.append(Reason("style_match", {"style": lead.style}))
    if _recency(lead.year, current_year) >= REASON_RECENT_MIN:
        out.append(Reason("recent", {"year": lead.year}))
    return out


def _select(leads: list[DiscoveryLead], limit: int) -> list[DiscoveryLead]:
    """Ordina per score e applica il cap per artista (no monopolio), poi tronca a limit.

    Il sort DEVE restare stabile — `sorted` lo garantisce, ed e' su questa garanzia che
    poggia il fallback a gusto piatto: quando il riferimento e' vuoto (o nessun segnale
    aggancia) i lead pareggiano tutti, e l'ordine che sopravvive e' quello in cui sono
    entrati, cioe' l'ordine per domanda con cui Discogs ha risposto dentro la finestra.
    E' l'unico ordine sensato che resta quando il gusto non discrimina, ed e' voluto:
    sostituire `sorted` con un ordinamento instabile lo romperebbe in silenzio (nessun
    errore, solo lead in ordine arbitrario).
    """
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
    taste_tracks: list | None = None,
    adventurousness: float = 0.4,
    limit: int = DEFAULT_DIG_LIMIT,
) -> DigResult:
    """Lead non posseduti dal seme dato (genere|etichetta), de-noised e ordinati per gusto.

    Dedup sempre su tutta la `library`; l'affinita' di gusto usa `taste_tracks`
    (default: la libreria stessa), che puo' essere una playlist specifica.
    """
    if library is None:
        library = _library_tracks(db)
    owned_tracks, owned_albums = _owned_index(library)
    profile = TasteProfile.from_tracks(library if taste_tracks is None else taste_tracks)

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
        k = _dedup_key(lead.artist_keys[0], lead.title)  # collassa varianti e pressature
        if k in seen or _is_owned(lead, owned_tracks, owned_albums):
            continue
        seen.add(k)
        leads.append(lead)

    adv = max(0.0, min(1.0, adventurousness))
    current_year = datetime.now(timezone.utc).year
    weights = _weights(seed_type)  # minimo indispensabile qui: la finestra/adv le sistema il Task 8
    for lead in leads:
        lead.score = _score(lead, profile, weights)
        lead.reasons = _reasons(lead, profile, current_year)
    selected = _select(leads, limit)

    logger.info("Discovery dig %s=%r: %s lead (adv=%.2f)", seed_type, value, len(selected), adv)
    return DigResult(seed_type=seed_type, value=value, leads=selected)
