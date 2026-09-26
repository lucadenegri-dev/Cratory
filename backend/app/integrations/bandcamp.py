"""Bandcamp: seconda sorgente del dig, accanto a Discogs.

Cosa da' / cosa NON da':
- Pile enormi per tag (`techno` = 434.149 release), data di uscita esatta, etichetta,
  prezzo e — regalato dentro il risultato della ricerca — lo STREAM mp3 del brano in
  evidenza. Il dettaglio release da' la tracklist con uno stream per traccia.
- NON da' have/want (nessun segnale di rarita'), non da' gli stili nella lista (solo
  nel dettaglio) e non da' un formato dichiarato.

ATTENZIONE: sono endpoint INTERNI e non documentati, quelli dietro
`bandcamp.com/discover`. Possono cambiare senza preavviso. La difesa e' il confinamento
(tutto l'HTTP sta qui), il parsing difensivo a valle e il test di contratto in
`tests/test_bandcamp_contract.py`, che si lancia a mano quando qualcosa non torna.

httpx iniettabile -> test senza rete.
"""

import re
from typing import Any

import httpx

from app.integrations._http import ClosableHttpClient, post_json

BASE = "https://bandcamp.com"
_USER_AGENT = "Mozilla/5.0 (compatible; Cratory/0.1)"

# Massimo osservato per `size`, e il tempo cresce meno che linearmente: 60 risultati
# in 0,8s, 500 in 3,2s (misurato 2026-07-22). Sfogliare in profondita' e' quindi
# molto piu' economico che a batch piccole.
DISCOVER_PAGE_SIZE = 500
# L'equivalente piu' vicino a `sort=want` di Discogs. "new" funziona ma sarebbe un
# asse diverso; "rec" non risponde.
DISCOVER_SLICE = "top"


class BandcampError(Exception):
    pass


def _words(value: Any) -> list[str]:
    """Le parole di un nome, minuscole, senza punteggiatura: 'AK-One' -> ['ak', 'one']."""
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).split()


def _name_matches(wanted: str, candidate: Any) -> bool:
    """Il nome trovato e' quello cercato: uguale, o lo estende di parole intere.

    'NAFF' accetta 'naff recordings' e 'Sun Runner' accetta 'Sun Runner EP'; 'Music
    For Nations' rifiuta 'Music For An Alternative Nation' (terza parola diversa) e
    '747' rifiuta 'AK-747s' (la parola e' '747s'). Per parole intere e non per
    caratteri: un prefisso di caratteri accetterebbe 'Ciel' per 'Cielo'.
    """
    wanted_words = _words(wanted)
    return bool(wanted_words) and _words(candidate)[:len(wanted_words)] == wanted_words


class BandcampClient(ClosableHttpClient):
    def __init__(self, http: httpx.Client | None = None):
        self.http = http or httpx.Client(
            timeout=25, follow_redirects=True,
            headers={"User-Agent": _USER_AGENT, "Content-Type": "application/json"},
        )

    def _post(self, path: str, body: dict) -> dict[str, Any]:
        return post_json(
            self.http, f"{BASE}{path}", json_body=body,
            error_cls=BandcampError, name="Bandcamp",
            rate_limit_message="Bandcamp: rate limit (riprova piu' tardi).",
        )

    @staticmethod
    def _checked(payload: dict[str, Any], what: str) -> dict[str, Any]:
        """Bandcamp risponde 200 anche quando fallisce, con {"error": true}.

        Senza questo controllo un band_id sbagliato sembrerebbe un'etichetta senza
        dischi, cioe' un seme morto: l'utente incolperebbe il proprio seme.
        """
        if payload.get("error"):
            raise BandcampError(f"Bandcamp {what}: {payload.get('error_message') or 'errore'}")
        return payload

    def discover(
        self, *, tag: str, cursor: str = "*", size: int = DISCOVER_PAGE_SIZE,
    ) -> tuple[list[dict], str | None, int]:
        """Una batch della pila di un tag. Ritorna (risultati, cursore, altezza pila).

        Il cursore e' opaco e va sfogliato in sequenza: non esiste un salto a pagina N.
        """
        data = self._checked(self._post("/api/discover/1/discover_web", {
            "category_id": 0,
            "tag_norm_names": [tag],
            "geoname_id": 0,
            "slice": DISCOVER_SLICE,
            # Solo album: con ["t"] la risposta non contiene affatto `results`.
            "include_result_types": ["a"],
            "size": size,
            "cursor": cursor,
        }), "discover")
        return (
            list(data.get("results") or []),
            data.get("cursor") or None,
            int(data.get("result_count") or 0),
        )

    def _autocomplete(self, text: str, item_type: str) -> list[dict[str, Any]]:
        """I risultati dell'autocomplete di un solo tipo (`b` band, `a` album, `t` traccia).

        Il filtro chiede solo quel tipo; i risultati di altro tipo si scartano
        comunque, perche' l'ordine non e' garantito.
        """
        data = self._checked(self._post("/api/bcsearch_public_api/1/autocomplete_elastic", {
            "search_text": text, "search_filter": item_type, "full_page": False, "fan_id": None,
        }), "search")
        return [item for item in ((data.get("auto") or {}).get("results") or [])
                if item.get("type") == item_type and item.get("id")]

    def find_band(self, name: str, *, label: bool = False) -> dict[str, Any] | None:
        """La band (artista o etichetta) con QUEL nome. `None` se non c'e'.

        L'autocomplete e' approssimativo: per "Music For Nations" restituisce "Music
        For An Alternative Nation", per "PMEDIA" "Red Letter Media". Si tiene solo
        chi corrisponde al nome cercato (`_name_matches`): meglio nessuna band di una
        band sbagliata, che farebbe camminare un arco sul catalogo di un altro.

        Con `label=True`, tra i corrispondenti vince chi Bandcamp segna come
        etichetta: "NAFF" trova "naff recordings" (etichetta) prima di "Naff"
        (una band omonima).
        """
        matches = [item for item in self._autocomplete(name, "b")
                   if _name_matches(name, item.get("name"))]
        if label:
            for item in matches:
                if item.get("is_label"):
                    return item
        return matches[0] if matches else None

    def find_release(self, artist: str, title: str) -> dict[str, Any] | None:
        """La release "artista + titolo", ovunque sia ospitata. `None` se non c'e'.

        Cerca fra gli album di TUTTE le pagine, non solo in una discografia: una
        release pubblicata da un'etichetta sta sulla pagina dell'etichetta e la
        discografia dell'artista non la elenca. Il risultato porta `band_id` della
        pagina che ospita e `id` della release: quel che serve a `tralbum`.

        Si accetta solo se il nome band corrisponde all'artista e il titolo a
        quello cercato: la query e' approssimativa e il primo risultato per
        "Boards of Canada Inferno" e' il caricamento di un fan.
        """
        for item in self._autocomplete(f"{artist} {title}", "a"):
            if not item.get("band_id"):
                continue
            if (_name_matches(artist, item.get("band_name"))
                    and _name_matches(title, item.get("name"))):
                return item
        return None

    def band_discography(self, band_id: int) -> list[dict]:
        """Le release pubblicate da una band/etichetta.

        Forma DIVERSA dai risultati di `discover`: l'artista sta in `artist_name`, non
        ci sono ne' stream ne' conteggio tracce, e la data e' '26 Jun 2026 ...'.
        """
        data = self._checked(self._post("/api/mobile/24/band_details", {"band_id": band_id}),
                             "band_details")
        return list(data.get("discography") or [])

    def tralbum(self, *, band_id: int, tralbum_id: int, tralbum_type: str = "a") -> dict[str, Any]:
        """Dettaglio di una release: `bandcamp_url`, `tags`, `price` e le tracce con
        `streaming_url["mp3-128"]`.

        Sostituisce lo scraping dell'attributo `data-tralbum` dalla pagina album (337KB
        di HTML per release) e, lavorando su id numerici, evita che un URL debba
        attraversare il confine HTTP verso il backend.
        """
        return self._checked(self._post("/api/mobile/24/tralbum_details", {
            "band_id": band_id, "tralbum_id": tralbum_id, "tralbum_type": tralbum_type,
        }), "tralbum_details")
