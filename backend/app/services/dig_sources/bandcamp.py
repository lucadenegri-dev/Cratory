"""Bandcamp come sorgente del dig: un'altra pila da cui pescare.

Differenze strutturali da Discogs, tutte volute e tutte visibili qui:
- la pila si sfoglia SOLO in sequenza (cursore opaco), quindi la profondita' costa
  richieste invece di essere un salto: `BANDCAMP_REACH` e' il tetto che tiene il dig
  peggiore sotto i ~20s;
- non esiste have/want, quindi niente segnale di rarita' e niente de-noise per
  domanda: restano solo gli scarti strutturali;
- gli stili non ci sono nella lista (solo nel dettaglio release), quindi il peso
  `style` esce e si redistribuisce — se ne occupa `_weights` nel motore, guardando i
  dati e non il nome della sorgente.
"""

import logging
import re
from datetime import datetime, timezone
from typing import Any

from app.integrations.bandcamp import DISCOVER_PAGE_SIZE, BandcampError
from app.services.dig_sources import DiscoveryLead, Pile, Seed
from app.services.discovery_dig import _VARIOUS, _clean_artist, _norm

logger = logging.getLogger(__name__)

# Quanti item della pila la sorgente raggiunge davvero. Non e' un limite di Bandcamp
# ma una scelta di costo: l'offset si consuma sfogliando, e ogni batch da 500 costa
# ~3,2s. A 3.000 il dig piu' profondo sta in 6 richieste (~20s), quello in superficie
# in 2. Tarabile: alzarlo allunga solo i dig profondi.
BANDCAMP_REACH = 3000

# I semi curati sono vocabolario DISCOGS. Misurati tutti e 25 contro l'API il
# 2026-07-22: 24 funzionano con la sola normalizzazione. L'unico alias serve dove la
# forma naive trova una pila VERA ma sbagliata — 'drum-n-bass' esiste (9.745) e
# quindi nessun controllo su "zero risultati" lo intercetterebbe mai.
# Come `_CURATED_STYLES`, questa tabella marcira': la difesa e' che un seme senza
# pila si dichiara tale (`result_count: 0`), non che la tabella resti giusta.
_TAG_ALIASES = {
    "drum n bass": "drum-and-bass",
}

# Soglie del badge derivato dal numero di tracce. Bandcamp non dichiara un formato:
# e' l'unico punto in cui questa sorgente inferisce invece di leggere.
_EP_MAX_TRACKS = 5


def _tag_norm(value: str) -> str:
    """Il tag Bandcamp corrispondente a un seme.

    Minuscolo e trattini: ogni corsa di caratteri non alfanumerici diventa un solo
    trattino, cosi' 'Funk / Soul' -> 'funk-soul' e non 'funk-/-soul' (che non esiste).
    """
    key = " ".join((value or "").strip().lower().split())
    if key in _TAG_ALIASES:
        return _TAG_ALIASES[key]
    return re.sub(r"[^a-z0-9]+", "-", key).strip("-")


def _bc_year(value: Any) -> int | None:
    """L'anno da una data Bandcamp.

    Serve un parser dedicato: le due forme che l'API restituisce sono
    '2026-07-17 00:00:00 UTC' e '26 Jun 2026 00:00:00 GMT', e `_parse_year` del motore
    ancora la regex all'inizio della stringa — sulla seconda tornerebbe None.
    """
    m = re.search(r"\b(\d{4})\b", str(value or ""))
    return int(m.group(1)) if m else None


def _bc_year_from_epoch(value: Any) -> int | None:
    """`tralbum_details` da' la data come timestamp unix, non come stringa."""
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc).year
    except (TypeError, ValueError, OSError):
        return None


def _art_url(art_id: Any, size: str = "9") -> str | None:
    """La copertina da un id immagine. `_9` e' ~15KB (griglia), `_16` ~50KB (pannello)."""
    return f"https://f4.bcbits.com/img/a{art_id}_{size}.jpg" if art_id else None


def _track_count(value: Any) -> int:
    """Il conteggio tracce di un item discover, tollerante al valore.

    Endpoint non documentato: se `track_count` arriva non numerico non deve far
    esplodere `to_lead` (che `dig()` non protegge con un try/except) in un 500 — deve
    solo valere 0, cosi' il guard sotto scarta il lead come release vuota.
    """
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _badge(track_count: int) -> str | None:
    if track_count <= 0:
        return None
    if track_count == 1:
        return "Single"
    return "EP" if track_count <= _EP_MAX_TRACKS else "Album"


class BandcampSource:
    name = "bandcamp"

    def __init__(self, client):
        self.client = client

    # --- probe ---------------------------------------------------------------

    def probe(self, seed: Seed) -> Pile:
        if seed.type == "label":
            return self._probe_label(seed)
        if seed.type != "genre":
            return Pile(height=0, reach=0)
        tag = _tag_norm(seed.value)
        if not tag:
            return Pile(height=0, reach=0)
        # size=1: la sonda serve solo a sapere quanto e' alta la pila.
        _, _, total = self.client.discover(tag=tag, cursor="*", size=1)
        return Pile(height=total, reach=BANDCAMP_REACH,
                    resolution="tag" if total else None, handle=tag)

    def _probe_label(self, seed: Seed) -> Pile:
        """L'etichetta non e' un filtro del discover: si passa dalla sua discografia.

        Due richieste (cerca il nome, scarica la discografia) e la lista finisce in
        `handle`: `fetch` diventa una fetta, zero richieste. La pila e' quindi corta
        per costruzione, e `reach == height` perche' non esiste un fondo oltre a
        quello che l'etichetta ha pubblicato.
        """
        band = self.client.find_band(seed.value)
        if not band or not band.get("id"):
            return Pile(height=0, reach=0)
        discography = self.client.band_discography(int(band["id"]))
        return Pile(height=len(discography), reach=len(discography),
                    resolution="discography" if discography else None,
                    handle=discography)

    # --- fetch ---------------------------------------------------------------

    def fetch(self, seed: Seed, pile: Pile, offset: int, count: int) -> list[dict]:
        if count <= 0 or not pile.handle:
            return []
        if seed.type == "label":
            return list(pile.handle)[offset:offset + count]
        tag = pile.handle
        cursor: str | None = "*"
        seen = 0
        out: list[dict] = []
        while len(out) < count:
            try:
                batch, cursor, _ = self.client.discover(
                    tag=tag, cursor=cursor, size=DISCOVER_PAGE_SIZE)
            except BandcampError:
                # Durante lo skip non c'e' ancora NIENTE di valido in mano: degradare
                # restituirebbe lead da una profondita' diversa da quella chiesta,
                # cioe' mentirebbe sul contratto. Dopo, i risultati raccolti sono
                # comunque quelli giusti e si tengono.
                if not out:
                    raise
                logger.warning(
                    "Bandcamp: sfogliata di %r interrotta, torno i %d item gia' raccolti",
                    tag, len(out),
                )
                break
            if not batch:
                break
            for item in batch:
                if seen >= offset:
                    out.append(item)
                seen += 1
                if len(out) >= count:
                    break
            if not cursor:
                break
        return out

    # --- mapping -------------------------------------------------------------

    def to_lead(self, raw: dict, seed: Seed) -> DiscoveryLead | None:
        # Due endpoint, due forme: il discover porta stream e conteggio tracce, la
        # discografia porta `artist_name` e nient'altro di riproducibile.
        if seed.type == "label":
            return self._lead_from_discography(raw, seed)
        return self._lead_from_discover(raw, seed)

    def _lead_from_discography(self, raw: dict, seed: Seed) -> DiscoveryLead | None:
        title = (raw.get("title") or "").strip()
        artist_raw = (raw.get("artist_name") or "").strip()
        if not title or not artist_raw or artist_raw.lower() in _VARIOUS:
            return None
        artist, artist_keys = _clean_artist(artist_raw)
        if not artist or not artist_keys:
            return None
        band_id, item_id = raw.get("band_id"), raw.get("item_id")
        return DiscoveryLead(
            artist=artist, artist_keys=artist_keys, title=title,
            year=_bc_year(raw.get("release_date")),
            label=(raw.get("band_name") or "").strip() or None,
            styles=[],
            source="bandcamp", seed=seed.value,
            source_id=(f"{band_id}:{item_id}" if band_id and item_id else None),
            # La discografia non porta l'URL della pagina: lo risolve il pannello,
            # che apre `tralbum_details` e riceve `bandcamp_url`.
            source_url=None,
            thumb_url=_art_url(raw.get("art_id")),
            stream_url=None,
            format_badge=None,
        )

    def _lead_from_discover(self, raw: dict, seed: Seed) -> DiscoveryLead | None:
        title = (raw.get("title") or "").strip()
        band = (raw.get("band_name") or "").strip()
        album_artist = (raw.get("album_artist") or "").strip()
        artist_raw = album_artist or band
        if not title or not artist_raw or artist_raw.lower() in _VARIOUS:
            return None
        track_count = _track_count(raw.get("track_count"))
        if track_count <= 0:
            return None
        stream = ((raw.get("featured_track") or {}).get("stream_url") or "").strip()
        if not stream:
            # Senza brano in evidenza la card non ha niente da far sentire, ed e' il
            # segnale piu' affidabile che la release sia vuota o non pubblicata.
            return None
        artist, artist_keys = _clean_artist(artist_raw)
        if not artist or not artist_keys:
            return None
        # L'etichetta e' la band che OSPITA, quando non coincide con l'artista.
        # `band or None`: se il nome band arriva vuoto l'etichetta e' assente, non "".
        label = (band or None) if album_artist and _norm(band) != _norm(album_artist) else None
        band_id, item_id = raw.get("band_id"), raw.get("item_id")
        return DiscoveryLead(
            artist=artist, artist_keys=artist_keys, title=title,
            year=_bc_year(raw.get("release_date")),
            label=label,
            styles=[],
            source="bandcamp", seed=seed.value,
            source_id=(f"{band_id}:{item_id}" if band_id and item_id else None),
            source_url=(raw.get("item_url") or "").split("?")[0] or None,
            thumb_url=_art_url((raw.get("primary_image") or {}).get("image_id")),
            stream_url=stream,
            format_badge=_badge(track_count),
        )


# Quanti item chiedere al discover per l'arco stile. `DISCOVER_PAGE_SIZE` (500) è la
# misura del dig, che deve riempire una finestra; qui l'arco è un rinforzo e la
# finestra temporale scarta già molto, quindi una batch corta basta e costa meno.
STYLE_EDGE_ITEMS = 120

# Tag troppo larghi per definire uno stile: non discriminano niente e il discover
# che ne uscirebbe è indistinguibile da un dig generico.
GENERIC_TAGS = {"electronic", "music", "dance"}

# `item_type` della discografia -> `tralbum_type` di tralbum_details. L'API rifiuta
# esplicitamente "album" ("Expected tralbum_type as 'a' or 't'"): la mappa non è
# cosmesi, senza di lei la risoluzione fallisce sempre.
_TRALBUM_TYPES = {"album": "a", "track": "t", "a": "a", "t": "t"}


class BandcampSimilar:
    """I parenti di un disco su Bandcamp: risoluzione e archi.

    L'unico punto che conosce la forma dei payload Bandcamp per i simili. Condivide
    con `BandcampSource` i mapper da record grezzo a lead: la discografia e il
    discover hanno due forme diverse, ed è già `BandcampSource` a saperlo.
    """

    name = "bandcamp"

    def __init__(self, client):
        self.client = client
        self._source = BandcampSource(client)

    # --- resolve -------------------------------------------------------------

    def resolve(self, track) -> Any:
        from app.services.discovery_similar import Origin

        artist_raw = (getattr(track, "artist", None) or "").strip()
        if not artist_raw:
            return None
        artist, _keys = _clean_artist(artist_raw)
        if not artist:
            return None
        band = self.client.find_band(artist)
        if not band or not band.get("id"):
            return None
        band_id = int(band["id"])
        discography = self.client.band_discography(band_id)

        item = self._match_release(discography, track)
        if item is None:
            # Release non riconosciuta: si tiene l'artista e si prendono dai tag del
            # file quel che la release avrebbe dato. Dichiarato, non nascosto.
            return Origin(
                artist=artist, band_id=band_id, title=None, tralbum_id=None,
                tralbum_type=None,
                label=(getattr(track, "label", None) or "").strip() or None,
                label_id=None,
                tag=(_tag_norm(getattr(track, "genre", None) or "") or None),
                year=getattr(track, "year", None),
                source_url=None, resolution="artist_only", discography=discography,
            )

        tralbum_type = _TRALBUM_TYPES.get(str(item.get("item_type") or "a"), "a")
        detail = self.client.tralbum(
            band_id=int(item.get("band_id") or band_id),
            tralbum_id=int(item["item_id"]),
            tralbum_type=tralbum_type,
        )
        label_id = detail.get("label_id")
        return Origin(
            artist=artist, band_id=band_id,
            title=(item.get("title") or "").strip() or None,
            tralbum_id=int(item["item_id"]), tralbum_type=tralbum_type,
            label=(detail.get("label") or "").strip() or None,
            label_id=int(label_id) if label_id else None,
            tag=self._style_tag(detail, track),
            year=_bc_year_from_epoch(detail.get("release_date"))
                 or getattr(track, "year", None),
            source_url=(detail.get("bandcamp_url") or "").split("?")[0] or None,
            resolution="release", discography=discography,
        )

    def _match_release(self, discography: list[dict], track) -> dict | None:
        """La release della discografia che corrisponde alla traccia.

        La discografia elenca RELEASE, non brani: si prova prima l'album (match
        diretto) e poi il titolo (funziona quando il brano è uscito come single o EP
        omonimo). Aprire ogni release per cercarci dentro il brano costerebbe una
        richiesta a release: fuori scope.
        """
        from app.services.discovery_dig import _dedup_title

        wanted = [_norm(_dedup_title(v)) for v in
                  ((getattr(track, "album", None) or ""), (getattr(track, "title", None) or ""))
                  if (v or "").strip()]
        for want in wanted:
            for item in discography:
                if _norm(_dedup_title(item.get("title") or "")) == want:
                    return item
        return None

    def _style_tag(self, detail: dict, track) -> str | None:
        """Il primo tag utile della release: né di luogo né generico."""
        for tag in detail.get("tags") or []:
            if tag.get("isloc"):
                continue
            norm = (tag.get("norm_name") or "").strip().lower()
            if norm and norm not in GENERIC_TAGS:
                return norm
        return _tag_norm(getattr(track, "genre", None) or "") or None

    # --- expand --------------------------------------------------------------

    def expand(self, origin, *, style_period: bool) -> list[tuple[str, dict]]:
        out: list[tuple[str, dict]] = []
        out.extend(("same_artist", item) for item in self._artist_edge(origin))
        out.extend(("same_label", item) for item in self._label_edge(origin))
        if style_period:
            out.extend(("same_period_style", item) for item in self._style_edge(origin))
        return out

    def _artist_edge(self, origin) -> list[dict]:
        """Le altre release dell'artista. Zero richieste: la discografia è già in mano."""
        return [item for item in origin.discography
                if str(item.get("item_id")) != str(origin.tralbum_id)]

    def _label_edge(self, origin) -> list[dict]:
        """La discografia dell'etichetta.

        Autoprodotto (`label_id` assente o uguale alla band) non è un errore: è un
        arco che non esiste, e non deve costare una richiesta.
        """
        if origin.label_id and origin.label_id != origin.band_id:
            return self.client.band_discography(origin.label_id)
        if origin.resolution == "artist_only" and origin.label:
            band = self.client.find_band(origin.label)
            if band and band.get("id"):
                return self.client.band_discography(int(band["id"]))
        return []

    def _style_edge(self, origin) -> list[dict]:
        """Il discover del tag, ristretto alla finestra temporale dell'origine.

        Una sola batch: l'arco è un rinforzo, non un dig, e la finestra scarta già
        molto. Il filtro sull'anno è sul client perché il discover non lo offre.
        """
        from app.services.discovery_similar import PERIOD_YEARS

        if not origin.tag or origin.year is None:
            return []
        try:
            batch, _cursor, _total = self.client.discover(
                tag=origin.tag, cursor="*", size=STYLE_EDGE_ITEMS)
        except BandcampError:
            raise
        lo, hi = origin.year - PERIOD_YEARS, origin.year + PERIOD_YEARS
        out = []
        for item in batch or []:
            year = _bc_year(item.get("release_date"))
            if year is not None and lo <= year <= hi:
                out.append(item)
        return out

    # --- mapping -------------------------------------------------------------

    def to_lead(self, edge: str, raw: dict):
        """Due archi, due forme: discografia (artista, etichetta) vs discover (stile).

        I mapper sono quelli di `BandcampSource`: il seme che gli si passa serve solo
        a marcare il lead, e qui è il nome dell'arco.
        """
        seed = Seed(type="label" if edge != "same_period_style" else "genre", value=edge)
        return self._source.to_lead(raw, seed)
