"""Cover art dai provider: Cover Art Archive (via release-MBID) + download immagini.
L'orchestratore lookup_cover (Task 3) combina CAA con il fallback Discogs.
http iniettabile → test senza rete, come musicbrainz/discogs_meta."""

import logging
from dataclasses import dataclass

import httpx

from app.integrations._http import get_with_retries

logger = logging.getLogger(__name__)
CAA = "https://coverartarchive.org"
_USER_AGENT = "Sortory/0.1 (+http://localhost)"


class CoverArtError(Exception):
    pass


def _client(http: httpx.Client | None) -> httpx.Client:
    return http or httpx.Client(timeout=15, follow_redirects=True,
                                headers={"User-Agent": _USER_AGENT})


def fetch_image(url: str, http: httpx.Client | None = None) -> bytes:
    """Scarica i byte di un'immagine. Solleva CoverArtError su qualunque errore."""
    cli = _client(http)
    try:
        r = get_with_retries(cli, url, error_cls=CoverArtError)
    except CoverArtError:
        raise
    if r.status_code >= 400:
        raise CoverArtError(f"immagine {r.status_code}: {url}")
    return r.content


class CoverArtArchiveClient:
    def __init__(self, http: httpx.Client | None = None):
        self.http = _client(http)

    def front_thumb(self, mbid: str) -> bytes | None:
        """Thumbnail 250px del fronte per un release-MBID. None se assente/errore."""
        try:
            r = get_with_retries(self.http, f"{CAA}/release/{mbid}/front-250",
                                 error_cls=CoverArtError)
        except CoverArtError as exc:
            logger.warning("CAA thumb %s fallito: %s", mbid, exc)
            return None
        if r.status_code >= 400:
            return None
        return r.content

    def front_url(self, mbid: str) -> str:
        return f"{CAA}/release/{mbid}/front"


@dataclass
class CoverResult:
    thumb_bytes: bytes
    full_url: str
    source: str       # 'caa' | 'discogs'
    confidence: str   # 'high' | 'text'


def lookup_cover(*, release_mbids, confidence, artist, title,
                 caa=None, discogs=None, fetch=None) -> CoverResult | None:
    """CAA (release-MBID) su match 'high'; Discogs cover come fallback (sempre 'text').
    Ritorna None se nessuna immagine trovata o scaricabile."""
    if confidence == "high" and caa is not None:
        for mbid in release_mbids or []:
            thumb = caa.front_thumb(mbid)
            if thumb:
                return CoverResult(thumb, caa.front_url(mbid), "caa", "high")
    if discogs is not None:
        cov = discogs.cover(artist=artist, title=title)
        if cov:
            fetcher = fetch or fetch_image
            try:
                thumb = fetcher(cov.get("thumb_url") or cov.get("full_url"))
            except CoverArtError:
                return None
            if thumb:
                full = cov.get("full_url") or cov.get("thumb_url")
                return CoverResult(thumb, full, "discogs", "text")
    return None
