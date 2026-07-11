"""Client SoundCloud via yt-dlp: SOLO metadati, mai audio.

Fetcher provvisorio in attesa dell'API ufficiale (che richiede Artist Pro).
Due modalità:
- flat (preview like): un'unica richiesta, ma le entry hanno solo titolo/URL
  (niente uploader né durata);
- piena (import playlist/track): una richiesta per traccia (~1s l'una), con
  uploader reale, durata e artwork. `ignore_no_formats_error` evita che una
  traccia DRM faccia fallire l'estrazione (non risolviamo mai l'audio).

Failure mode noto: se SoundCloud cambia qualcosa, l'estrazione si rompe
finché non si aggiorna yt-dlp (il messaggio d'errore lo dice).
Fetch sequenziali, nessun parallelismo: profilo basso su API non ufficiale.
"""
from __future__ import annotations

import importlib.util
import re
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


def _extract(url: str, *, limit: int | None = None, flat: bool = True) -> dict:
    import yt_dlp

    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "socket_timeout": _SOCKET_TIMEOUT,
    }
    if flat:
        # Solo metadati delle entry (titolo/URL), una richiesta sola.
        opts["extract_flat"] = "in_playlist"
    else:
        # Metadati pieni (uploader/durata/artwork), una richiesta per traccia.
        # Mai risolvere l'audio: una traccia DRM non deve far fallire il fetch
        # e le entry irrecuperabili diventano None (scartate a valle).
        opts["extract_flat"] = False
        opts["ignore_no_formats_error"] = True
        opts["ignoreerrors"] = True
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


def _is_set_entry(entry: dict) -> bool:
    # Nei like possono comparire anche playlist (/sets/): non sono tracce.
    url = entry.get("url") or entry.get("webpage_url") or ""
    return "/sets/" in urlparse(url).path


def uploader_from_url(url: str | None) -> str | None:
    """Utente che ha caricato, dallo slug dell'URL traccia (per la preview flat,
    dove il display name non c'è): "bruno-ruotolo-711086630" -> "bruno ruotolo".
    """
    segments = [s for s in urlparse(url or "").path.split("/") if s]
    if not segments:
        return None
    slug = re.sub(r"-\d+$", "", segments[0])  # via il suffisso numerico di disambiguazione
    return slug.replace("-", " ").replace("_", " ").strip() or None


def fetch_playlist(url: str) -> dict:
    """Playlist (pubblica o secret link) -> info dict con `entries` in lista.

    Estrazione piena: uploader/durata/artwork per ogni traccia (una richiesta
    per traccia, l'import mostra lo spinner nel frontend).
    """
    return _materialized(_extract(_validate_url(url), flat=False))


def fetch_likes(username: str, limit: int = DEFAULT_LIKES_LIMIT) -> dict:
    """Like pubblici dell'utente -> info dict con `entries` in lista (più recenti prima).

    Estrazione flat (veloce, per la preview): titolo/URL ma niente uploader né
    durata. I metadati pieni arrivano con `fetch_track` sulle tracce selezionate.
    """
    username = (username or "").strip().lstrip("@")
    if not username:
        raise SoundCloudError("Username SoundCloud non configurato.")
    info = _materialized(_extract(f"https://soundcloud.com/{username}/likes", limit=limit))
    info["entries"] = [e for e in info["entries"] if not _is_set_entry(e)]
    return info


def fetch_track(url: str) -> dict:
    """Singola traccia -> info dict pieno (uploader/durata/artwork)."""
    info = _extract(_validate_url(url), flat=False)
    if not info.get("id"):
        raise SoundCloudError("L'URL non punta a una traccia SoundCloud.")
    return info
