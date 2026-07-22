"""Discovery v2 — "crate digging": lista-dig a volume da una `DigSource`.

Il dig produce TANTI lead leggeri NON risolti dai semi Genere/Etichetta (l'identita'
Spotify si risolve solo al salvataggio). Il motore ragiona in ITEM, non in pagine: chiede
alla sorgente una `Pile` (quanto e' alta, quanto ne raggiunge) e ne ricava una finestra
(offset, count) via `_window`; `depth` sceglie IN CHE PUNTO pescarci dentro (0 = la cima
della pila, 1 = il fondo di cio' che la sorgente raggiunge), il gusto (`TasteProfile`)
ordina SEMPRE dentro la finestra scelta. Chi conosce la paginazione del provider (pagine
Discogs, sfogliata Bandcamp) e' la `DigSource` stessa (`app/services/dig_sources/`), non
questo modulo: e' il confine che rende possibile aggiungerne una seconda.

De-noise: distingue la gemma rara dal rumore self-released con la DOMANDA (want vs
have) come FILTRO — non piu' come ordinamento, quello lo decide il gusto dentro la
finestra —, scarta formati off-target (compilation/DJ mix) e self-released morti,
deduplica le varianti ("(Original Mix)") e limita quante voci per artista (questi filtri
restano nella sorgente Discogs, che e' l'unica a doverne conoscere i dati grezzi).

Deterministico e testabile: la sorgente e' iniettata (`DigSource` Protocol).
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.services.dig_sources import (
    WINDOW_ITEMS,
    DigSource,
    DiscoveryLead,
    Pile,
    Reason,
    Seed,
)
from app.models import Track

logger = logging.getLogger(__name__)


def _norm(value: str | None) -> str:
    return (value or "").strip().lower()


def _library_tracks(db: Session) -> list[Track]:
    return list(db.scalars(select(Track)).all())


def _window(depth: float, pile: Pile) -> tuple[int, int]:
    """La finestra (offset, count) da pescare nella pila.

    depth 0 = la cima (il canone del seme), depth 1 = il fondo di cio' che la sorgente
    RAGGIUNGE — che non e' il fondo della pila quando `reach < height`. Su una pila piu'
    corta della finestra `depth` non ha effetto: non c'e' profondita' da scegliere, e il
    chiamante lo segnala alla UI via `pile_reach`.
    """
    reach = max(0, min(pile.height, pile.reach))
    if reach <= 0:
        return 0, 0
    start = round(max(0.0, min(1.0, depth)) * max(0, reach - WINDOW_ITEMS))
    return start, min(WINDOW_ITEMS, reach - start)


_MAX_PER_ARTIST = 2  # un artista non deve monopolizzare la lista
_VARIOUS = {"various", "various artists", "va", "unknown artist"}

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
REASON_DEEP_CUT_MIN_WANT = 5    # sotto, non c'e' domanda misurabile: rumore, non gemma
REASON_STYLE_MATCH_MIN = 0.5    # soglia sulla Jaccard: un token condiviso non basta
REASON_RECENT_MIN = 0.8         # recency alta (ultimi ~3 anni su span 15)


def _parse_year(value: Any) -> int | None:
    m = re.match(r"\s*(\d{4})", str(value or ""))
    return int(m.group(1)) if m else None


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


def _weights(seed_type: str, *, has_styles: bool = True) -> Weights:
    """I segnali costanti per costruzione escono, e il peso si redistribuisce.

    Su un dig per etichetta ogni lead ha l'etichetta del seme: `label_affinity` vale
    1.0 per tutti. E' una costante additiva — non ordina, e dilava gli altri segnali.
    Stessa malattia quando la sorgente non porta gli stili nella lista (Bandcamp): un
    peso su un segnale sempre nullo e' peso buttato.

    Il seme `genre` NON perde il peso `style` per la ragione simmetrica, anche se ogni
    release del dig contiene lo style del seme per costruzione: li' la cura non e'
    azzerare il peso (si butterebbe anche il segnale buono) ma `_styles_beyond_seed`,
    che esclude il seme dal calcolo lasciando solo l'affinita' EXTRA.
    """
    artist, label, style = W_ARTIST, W_LABEL, W_STYLE
    if seed_type == "label":
        label = 0.0
    if not has_styles:
        style = 0.0
    total = artist + label + style
    if total <= 0:
        return Weights(artist=1.0, label=0.0, style=0.0)
    return Weights(artist=artist / total, label=label / total, style=style / total)


def _styles_beyond_seed(styles: list[str], seed_norm: str) -> list[str]:
    """Gli style della release OLTRE il seme del dig.

    Su un dig per genere ogni release contiene lo style del seme per costruzione
    (e' il filtro `style=value` della ricerca): la sua somiglianza con la libreria
    e' un PAVIMENTO comune a tutti i lead — se possiedi il genere alla lettera vale
    1.0, e `style_affinity` diventa una costante che non ordina e accende il badge
    su ogni card. Escludere il seme misura solo l'affinita' EXTRA, che e'
    l'informazione vera (una release taggata anche 'Tech House' che collezioni).
    Sui dig per etichetta e' un no-op: nessuno style si chiama come l'etichetta.
    """
    return [s for s in styles if _norm(s) != seed_norm]


def _score(lead: DiscoveryLead, profile: TasteProfile, weights: Weights,
           styles_beyond_seed: list[str]) -> float:
    """Solo gusto. La domanda l'ha gia' codificata la finestra (`_window`): dentro una
    finestra il `want` e' ~costante, quindi non ordina. La profondita' sceglie il
    bacino, il gusto ordina — sempre, non come modalita'.
    """
    return (
        weights.artist * profile.familiarity(lead.artist_keys)
        + weights.label * profile.label_affinity(lead.label)
        + weights.style * profile.style_affinity(styles_beyond_seed)
    )


def _reasons(lead: DiscoveryLead, profile: TasteProfile, seed_type: str,
             current_year: int, styles_beyond_seed: list[str]) -> list[Reason]:
    """Badge a soglia, deterministici. NON sono i fattori del punteggio: sono calcolati
    a parte e non spiegano la posizione del lead in lista.
    """
    out: list[Reason] = []
    if lead.want >= REASON_RARE_MIN_WANT and _demand(lead.have, lead.want) >= REASON_RARE_MIN_DEMAND:
        out.append(Reason("rare_wanted", {"have": lead.have, "want": lead.want}))
    if lead.have <= REASON_DEEP_CUT_MAX_HAVE and lead.want >= REASON_DEEP_CUT_MIN_WANT:
        out.append(Reason("deep_cut", {"have": lead.have}))
    # su un dig per etichetta il badge ce l'avrebbero tutti: non emesso
    if seed_type != "label" and profile.label_affinity(lead.label) > 0:
        out.append(Reason("label_followed", {"label": lead.label}))
    count = profile.artist_count(lead.artist_keys)
    if count > 0:
        out.append(Reason("artist_collected", {"artist": lead.artist, "count": count}))
    if profile.style_affinity(styles_beyond_seed) >= REASON_STYLE_MATCH_MIN:
        out.append(Reason("style_match", {"style": styles_beyond_seed[0] if styles_beyond_seed else None}))
    if _recency(lead.year, current_year) >= REASON_RECENT_MIN:
        out.append(Reason("recent", {"year": lead.year}))
    return out


def _select(leads: list[DiscoveryLead]) -> list[DiscoveryLead]:
    """Ordina per score e applica il cap per artista (no monopolio). NON tronca:
    la finestra di WINDOW_ITEMS item e' gia' il limite naturale (~300 release grezze),
    e il vecchio tetto di 80 nascondeva 160 lead a ogni dig senza che nulla lo dicesse
    (misurato su style=Acid House: 244 candidati validi su 300). Quanti mostrarne
    e' una lente della UI, non un parametro del motore.

    Il sort DEVE restare stabile — `sorted` lo garantisce, ed e' su questa garanzia che
    poggia il fallback a gusto piatto: quando il riferimento e' vuoto (o nessun segnale
    aggancia) i lead pareggiano tutti, e l'ordine che sopravvive e' quello in cui sono
    entrati, cioe' l'ordine con cui la sorgente ha risposto dentro la finestra (per
    Discogs, quello per domanda). E' l'unico ordine sensato che resta quando il gusto
    non discrimina, ed e' voluto: sostituire `sorted` con un ordinamento instabile lo
    romperebbe in silenzio (nessun errore, solo lead in ordine arbitrario).
    """
    out: list[DiscoveryLead] = []
    per_artist: dict[str, int] = {}
    for lead in sorted(leads, key=lambda x: x.score, reverse=True):
        a = lead.artist_keys[0]
        if per_artist.get(a, 0) >= _MAX_PER_ARTIST:
            continue
        per_artist[a] = per_artist.get(a, 0) + 1
        out.append(lead)
    return out


@dataclass
class DigResult:
    seed_type: str
    value: str
    leads: list[DiscoveryLead] = field(default_factory=list)
    # Quanto e' alta la pila del seme (0 = seme che la sorgente non conosce).
    pile_total: int = 0
    # Quanti item la sorgente raggiunge davvero. Se <= WINDOW_ITEMS la finestra e'
    # l'intera pila e `depth` non ha effetto: la UI deve poterlo dire invece di
    # offrire un controllo inerte. Se < pile_total, la UI avverte che si vede
    # solo una porzione.
    pile_reach: int = 0
    # Com'e' stato risolto il seme: "style"|"genre"|"label"|"tag"|"discography"|None.
    seed_resolution: str | None = None


def dig(
    db: Session,
    *,
    seed_type: str,
    value: str,
    source: DigSource,
    library: list | None = None,
    depth: float = 0.0,
) -> DigResult:
    """Lead non posseduti dal seme dato (genere|etichetta), ordinati per gusto.

    Due assi separati: `depth` sceglie DOVE pescare nella pila della sorgente (0 = la
    cima, 1 = il fondo di cio' che raggiunge); il gusto ordina SEMPRE dentro la
    finestra.

    Il profilo di gusto e la dedup del posseduto usano la STESSA `library`, per
    scelta: il riferimento per-playlist e' stato rimosso perche' su una playlist magra
    il gusto si azzerava in silenzio e la lista ricadeva sull'ordine della pila senza
    che nulla lo dicesse.
    """
    if library is None:
        library = _library_tracks(db)
    owned_tracks, owned_albums = _owned_index(library)
    profile = TasteProfile.from_tracks(library)

    seed = Seed(type=seed_type, value=value)
    pile = source.probe(seed)
    offset, count = _window(depth, pile)
    reach = max(0, min(pile.height, pile.reach))
    if count <= 0:
        return DigResult(seed_type=seed_type, value=value, pile_total=pile.height,
                         pile_reach=reach, seed_resolution=pile.resolution)

    items = source.fetch(seed, pile, offset, count)

    leads: list[DiscoveryLead] = []
    seen: set[tuple[str, str]] = set()
    for item in items or []:
        lead = source.to_lead(item, seed)
        if lead is None:
            continue
        k = _dedup_key(lead.artist_keys[0], lead.title)  # collassa varianti e pressature
        if k in seen or _is_owned(lead, owned_tracks, owned_albums):
            continue
        seen.add(k)
        leads.append(lead)

    # Quali segnali esistono lo dicono i DATI, non il nome della sorgente: se un
    # giorno Bandcamp restituisse gli stili nella lista, il peso torna da solo.
    has_styles = any(lead.styles for lead in leads)
    weights = _weights(seed_type, has_styles=has_styles)
    current_year = datetime.now(timezone.utc).year
    seed_norm = _norm(value)
    for lead in leads:
        extra_styles = _styles_beyond_seed(lead.styles, seed_norm)
        lead.score = _score(lead, profile, weights, extra_styles)
        lead.reasons = _reasons(lead, profile, seed_type, current_year, extra_styles)
    selected = _select(leads)

    logger.info("Discovery dig %s %s=%r: %s lead (depth=%.2f, offset %s, pila %s/%s)",
                source.name, seed_type, value, len(selected), depth, offset,
                reach, pile.height)
    return DigResult(seed_type=seed_type, value=value, leads=selected,
                     pile_total=pile.height, pile_reach=reach,
                     seed_resolution=pile.resolution)
