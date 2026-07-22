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


def _art_url(art_id: Any, size: str = "9") -> str | None:
    """La copertina da un id immagine. `_9` e' ~15KB (griglia), `_16` ~50KB (pannello)."""
    return f"https://f4.bcbits.com/img/a{art_id}_{size}.jpg" if art_id else None


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
        if seed.type != "genre":
            return Pile(height=0, reach=0)
        tag = _tag_norm(seed.value)
        if not tag:
            return Pile(height=0, reach=0)
        # size=1: la sonda serve solo a sapere quanto e' alta la pila.
        _, _, total = self.client.discover(tag=tag, cursor="*", size=1)
        return Pile(height=total, reach=BANDCAMP_REACH,
                    resolution="tag" if total else None, handle=tag)

    # --- fetch ---------------------------------------------------------------

    def fetch(self, seed: Seed, pile: Pile, offset: int, count: int) -> list[dict]:
        if count <= 0 or not pile.handle:
            return []
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
        return self._lead_from_discover(raw, seed)

    def _lead_from_discover(self, raw: dict, seed: Seed) -> DiscoveryLead | None:
        title = (raw.get("title") or "").strip()
        band = (raw.get("band_name") or "").strip()
        album_artist = (raw.get("album_artist") or "").strip()
        artist_raw = album_artist or band
        if not title or not artist_raw or artist_raw.lower() in _VARIOUS:
            return None
        track_count = int(raw.get("track_count") or 0)
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
        label = band if album_artist and _norm(band) != _norm(album_artist) else None
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
