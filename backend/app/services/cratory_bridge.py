"""Client HTTP read-only verso Cratory (app sorella, FastAPI su localhost:8000).
Solo GET /api/tracks/lookup: il bridge non scrive mai su Cratory. Mockabile nei
test (monkeypatch su cratory_bridge.lookup, come ai_tags.suggest)."""

import httpx

_TIMEOUT_S = 3.0


class CratoryUnreachable(Exception):
    """Cratory non raggiungibile (timeout/rete/status non-2xx): degradare, non rompere."""


def lookup(base_url: str, isrc: str | None = None, artist: str | None = None,
           title: str | None = None) -> dict:
    """GET {base_url}/api/tracks/lookup. Contratto: serve isrc OPPURE artist+title.

    Ritorna il body JSON del contratto:
    {"found": bool, "match": "isrc"|"fuzzy"|None, "track_id": int|None,
     "artist": ..., "title": ..., "genre": ..., "genre_secondary": ...,
     "genre_source": "manual"|"provider"|"ai"|"file_tag"|None,
     "album": ..., "label": ..., "year": ..., "confidence": 100|70|0}
    Solleva CratoryUnreachable su timeout, errore di rete o status != 2xx.
    Solleva ValueError se mancano sia isrc che artist+title.
    """
    # Guardia lato client: contratto Cratory richiede isrc oppure artist+title.
    if not isrc and not (artist and title):
        raise ValueError("lookup richiede isrc oppure artist+title")

    params: dict[str, str] = {}
    if isrc:
        params["isrc"] = isrc
    if artist:
        params["artist"] = artist
    if title:
        params["title"] = title
    try:
        resp = httpx.get(f"{base_url.rstrip('/')}/api/tracks/lookup",
                         params=params, timeout=_TIMEOUT_S)
        resp.raise_for_status()
        return resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        # Cattura sia errori di rete/status che ValueError da json() malformato.
        raise CratoryUnreachable(str(exc)) from exc
