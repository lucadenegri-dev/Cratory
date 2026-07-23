"""Download dell'audio di una singola traccia SoundCloud via yt-dlp, estratto in MP3.

Eccezione esplicita a "non conserva audio di terzi", come Soulseek: scarica un
file e lo collega alla Track come posseduto. Solo la singola traccia dal dettaglio,
mai batch. Scrive nella cartella di download condivisa (SLSKD_DOWNLOAD_DIR); i tag
NON vengono toccati (compito di Sortory).
"""
from __future__ import annotations

import os

from app.integrations.soundcloud import validate_soundcloud_url

_SOCKET_TIMEOUT = 30


class SoundCloudAudioError(RuntimeError):
    """Download/estrazione audio SoundCloud fallito (rete, yt-dlp, ffmpeg...)."""


def download_track_audio(url: str, dest_dir: str) -> str:
    """Scarica l'audio di `url` in `dest_dir`, lo estrae in MP3 e ritorna il path.

    SSRF guard: valida l'host (solo soundcloud.com). Solleva SoundCloudAudioError
    se la cartella manca o se yt-dlp/ffmpeg falliscono; SoundCloudInvalidUrl su
    URL ostile (delega a validate_soundcloud_url).
    """
    url = validate_soundcloud_url(url)  # usa l'URL normalizzato (strip), non il grezzo
    if not dest_dir:
        raise SoundCloudAudioError("Cartella di download non configurata (SLSKD_DOWNLOAD_DIR).")

    import yt_dlp

    opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "format": "bestaudio/best",
        "socket_timeout": _SOCKET_TIMEOUT,
        "outtmpl": os.path.join(dest_dir, "%(title)s.%(ext)s"),
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "0",
        }],
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            pre_pp_name = ydl.prepare_filename(info)
    except Exception as exc:  # noqa: BLE001 — yt-dlp/ffmpeg sollevano tipi eterogenei
        raise SoundCloudAudioError(
            f"Download SoundCloud fallito ({exc}). Se l'URL è corretto, prova ad aggiornare yt-dlp."
        ) from exc
    return _final_mp3_path(info, pre_pp_name)


def _final_mp3_path(info: dict, pre_pp_name: str) -> str:
    """Path del file dopo il postprocessor MP3.

    yt-dlp lo espone in `requested_downloads[*].filepath`; se manca si ripiega sul
    nome pre-postprocessor con estensione .mp3.
    """
    downloads = info.get("requested_downloads") or []
    if downloads and downloads[0].get("filepath"):
        return downloads[0]["filepath"]
    return os.path.splitext(pre_pp_name)[0] + ".mp3"
