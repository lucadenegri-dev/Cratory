"""Client SoundCloud via yt-dlp: SOLO metadati, mai audio.

Fetcher provvisorio in attesa dell'API ufficiale (che richiede Artist Pro):
usa l'estrazione flat di yt-dlp per leggere playlist pubbliche, secret link
e like. Failure mode noto: se SoundCloud cambia qualcosa, l'estrazione si
rompe finché non si aggiorna yt-dlp (il messaggio d'errore lo dice).

Fetch sequenziali, nessun parallelismo: profilo basso su API non ufficiale.
"""
from __future__ import annotations

import importlib.util
from urllib.parse import urlparse

DEFAULT_LIKES_LIMIT = 100
_SOCKET_TIMEOUT = 20
_ALLOWED_HOSTS = {"soundcloud.com", "www.soundcloud.com", "m.soundcloud.com", "on.soundcloud.com"}


class SoundCloudError(RuntimeError):
    """Errore nel fetch da SoundCloud (rete, estrazione, URL vuoto...)."""


class SoundCloudInvalidUrl(SoundCloudError):
    """URL non valido come input: mappa su HTTP 422, non 502."""


def soundcloud_available() -> bool:
    return importlib.util.find_spec("yt_dlp") is not None


def ytdlp_version() -> str | None:
    try:
        from yt_dlp.version import __version__
        return __version__
    except Exception:  # noqa: BLE001
        return None


def _validate_url(url: str) -> str:
    url = (url or "").strip()
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        # Evita che yt-dlp riceva file://, schemi locali o host vuoti (SSRF / lettura file).
        raise SoundCloudInvalidUrl("URL non valido: ammessi solo link http(s).")
    if parsed.netloc.lower() not in _ALLOWED_HOSTS:
        raise SoundCloudInvalidUrl("URL non valido: atteso un link soundcloud.com.")
    return url


def is_likes_url(url: str) -> bool:
    """True per gli URL /likes: nel flusso import-playlist vanno rifiutati (422)."""
    return urlparse(url or "").path.rstrip("/").endswith("/likes")


def _extract(url: str, *, limit: int | None = None) -> dict:
    import yt_dlp

    opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": "in_playlist",  # solo metadati delle entry, mai risolvere l'audio
        "skip_download": True,
        "socket_timeout": _SOCKET_TIMEOUT,
    }
    if limit:
        opts["playlistend"] = limit
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as exc:  # noqa: BLE001 — yt-dlp solleva tipi eterogenei
        raise SoundCloudError(
            f"Fetch SoundCloud fallito ({exc}). Se l'URL è corretto, prova ad aggiornare yt-dlp."
        ) from exc
    if not info:
        raise SoundCloudError("Nessun dato all'URL indicato.")
    return info


def _materialized(info: dict) -> dict:
    # yt-dlp può restituire `entries` come generatore: materializza e scarta i None.
    info["entries"] = [e for e in (info.get("entries") or []) if e]
    if not info["entries"]:
        raise SoundCloudError("Nessuna traccia trovata all'URL indicato.")
    return info


def fetch_playlist(url: str) -> dict:
    """Playlist (pubblica o secret link) -> info dict con `entries` in lista."""
    return _materialized(_extract(_validate_url(url)))


def fetch_likes(username: str, limit: int = DEFAULT_LIKES_LIMIT) -> dict:
    """Like pubblici dell'utente -> info dict con `entries` in lista (più recenti prima)."""
    username = (username or "").strip().lstrip("@")
    if not username:
        raise SoundCloudError("Username SoundCloud non configurato.")
    return _materialized(_extract(f"https://soundcloud.com/{username}/likes", limit=limit))
