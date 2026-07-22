"""Discogs come sorgente del dig: profondita' e segnale di rarita' (have/want).

Traduce la finestra in item del motore nella paginazione di Discogs (pagine da 100,
tetto a pagina 100) e mappa i record di `/database/search` su `DiscoveryLead`.
"""

import math
import re
from typing import Any

from app.integrations.discogs import (
    DISCOGS_MAX_PAGES,
    SEARCH_PER_PAGE,
    SORT_DESC,
    SORT_WANT,
)
from app.services.dig_sources import DiscoveryLead, Pile, Seed
# Il motore e le altre sorgenti condividono queste utility: stanno nel motore per non
# duplicarle. Nessun ciclo: `dig_sources/__init__` non importa il motore, e il motore
# non importa le sorgenti concrete (le costruisce il router).
from app.services.discovery_dig import _VARIOUS, _clean_artist, _parse_year

# Formati che un DJ NON vuole tra i lead (vuole release singole, non mix gia' fatti).
_BAD_FORMATS = {"compilation", "dj mix", "mixed", "mixtape"}
# Etichetta "non etichetta": segnale di autoproduzione.
_SELF_RELEASED_RE = re.compile(r"not on label|self[- ]released", re.IGNORECASE)

# Badge di formato per la UI. Match ESATTO (intersezione di insiemi), non per
# sostringa: 'ep' e' sottostringa di 'repress' e le ristampe sono frequentissime nel
# crate digging — una ristampa LP verrebbe marcata "EP".
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


def _first(seq: Any) -> str | None:
    return seq[0] if isinstance(seq, list) and seq else None


def _is_self_released(labels: Any) -> bool:
    return any(_SELF_RELEASED_RE.search(str(label)) for label in (labels or []))


class DiscogsSource:
    """La pila Discogs di un seme, ordinata per DOMANDA (`sort=want desc`).

    Senza `sort` Discogs risponde in un ordine arbitrario: su style=Acid House (43k
    release) le prime 300 non contengono NEMMENO UNA release con have>1000 e il 46%
    ne ha meno di 5. Misurato, non supposto.
    """

    name = "discogs"

    def __init__(self, client):
        self.client = client

    def probe(self, seed: Seed) -> Pile:
        if seed.type == "label":
            filters: dict[str, Any] = {"label": seed.value}
            resolution = "label"
        elif seed.type == "genre":
            # Discogs distingue `style` (fine: 'Deep House') da `genre` (grosso:
            # 'Electronic'): si prova il piu' specifico e si ripiega.
            filters = {"style": seed.value}
            resolution = "style"
        else:
            return Pile(height=0, reach=0)

        total = self.client.count_releases(**filters)
        if total == 0 and seed.type == "genre":
            filters = {"genre": seed.value}
            resolution = "genre"
            total = self.client.count_releases(**filters)

        return Pile(
            height=total,
            # Tetto duro di Discogs: pagina 101 -> 404.
            reach=DISCOGS_MAX_PAGES * SEARCH_PER_PAGE,
            resolution=resolution if total else None,
            handle=filters,
        )

    def fetch(self, seed: Seed, pile: Pile, offset: int, count: int) -> list[dict]:
        if count <= 0:
            return []
        # Quante pagine servono per `count` item, a partire da quella che contiene
        # l'offset. Contare invece le pagine "toccate" dall'intervallo ne chiederebbe
        # una quarta quando l'offset non e' allineato al centinaio: una richiesta
        # sprecata a ogni dig profondo.
        first = offset // SEARCH_PER_PAGE + 1
        pages = [p for p in range(first, first + math.ceil(count / SEARCH_PER_PAGE))
                 if p <= DISCOGS_MAX_PAGES]
        return self.client.search_releases(
            **(pile.handle or {}), pages=pages, sort=SORT_WANT, sort_order=SORT_DESC,
        )

    def to_lead(self, raw: dict, seed: Seed) -> DiscoveryLead | None:
        """Lead da un result di `/database/search`, con filtri anti-rumore.

        Scarta: titoli non splittabili, Various, formati off-target (compilation/DJ
        mix) e i self-released 'morti' (nessuno li ha ne' li cerca).
        """
        title = raw.get("title") or ""
        if " - " not in title:
            return None
        artist_raw, _, track_title = title.partition(" - ")
        artist_raw, track_title = artist_raw.strip(), track_title.strip()
        if not artist_raw or not track_title or artist_raw.lower() in _VARIOUS:
            return None
        artist, artist_keys = _clean_artist(artist_raw)
        if not artist or not artist_keys:
            return None
        formats = {str(f).lower() for f in (raw.get("format") or [])}
        if formats & _BAD_FORMATS:
            return None
        community = raw.get("community") or {}
        have = int(community.get("have") or 0)
        want = int(community.get("want") or 0)
        labels = raw.get("label") or []
        # self-released che nessuno ha ne' cerca: rumore, non una gemma rara.
        if have == 0 and want == 0 and _is_self_released(labels):
            return None
        uri = raw.get("uri") or ""
        rid = raw.get("id")
        return DiscoveryLead(
            artist=artist, artist_keys=artist_keys, title=track_title,
            year=_parse_year(raw.get("year")),
            label=_first(labels),
            styles=[str(s) for s in (raw.get("style") or [])],
            source="discogs", seed=seed.value,
            source_id=str(rid) if rid is not None else None,
            source_url=(f"https://www.discogs.com{uri}" if uri.startswith("/")
                        else (uri or None)),
            thumb_url=raw.get("cover_image") or raw.get("thumb") or None,
            have=have, want=want,
            format_badge=_format_badge(formats),
        )
