"""Cover caricata dall'utente per le playlist di Cratory (manual/shazam).

Le playlist sincronizzate hanno la cover della piattaforma; quelle create qui
non ne hanno una, e l'utente può darla lui. Il file vive sotto
`DATA_DIR/data/covers/playlist-{id}.{ext}` — un solo file per playlist — e
`Playlist.artwork_url` punta alla route `GET /api/playlists/{id}/artwork`
con un `?v=` che cambia a ogni upload, così il browser non mostra la cover
vecchia dalla cache.

Il tipo lo decide il contenuto (magic bytes), non il `Content-Type`
dichiarato dal client né l'estensione del nome: sono entrambi arbitrari.
"""
from __future__ import annotations

import time
from pathlib import Path

from app.core import paths

MAX_BYTES = 5 * 1024 * 1024

# (prefisso, estensione, media type). WebP: "RIFF" + 4 byte di lunghezza + "WEBP".
_SIGNATURES: tuple[tuple[bytes, str, str], ...] = (
    (b"\x89PNG\r\n\x1a\n", ".png", "image/png"),
    (b"\xff\xd8\xff", ".jpg", "image/jpeg"),
)
_MEDIA_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".webp": "image/webp"}


class ArtworkError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def covers_dir() -> Path:
    return paths.DATA_DIR / "data" / "covers"


def sniff(content: bytes) -> tuple[str, str]:
    """(estensione, media type) dai magic bytes; `ArtworkError` se non è un'immagine ammessa."""
    for prefix, ext, media in _SIGNATURES:
        if content.startswith(prefix):
            return ext, media
    if content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return ".webp", "image/webp"
    raise ArtworkError("unsupported_image_type", "Only PNG, JPEG and WebP images are accepted.")


def artwork_path(playlist_id: int) -> Path | None:
    """Il file cover della playlist, o None. Un solo file per id: il primo che combacia."""
    folder = covers_dir()
    if not folder.is_dir():
        return None
    for p in sorted(folder.glob(f"playlist-{playlist_id}.*")):
        if p.is_file():
            return p
    return None


def media_type_of(path: Path) -> str:
    return _MEDIA_TYPES.get(path.suffix.lower(), "application/octet-stream")


def save_artwork(playlist_id: int, content: bytes) -> str:
    """Scrive la cover (sostituendo l'eventuale precedente) e ritorna il nuovo `artwork_url`."""
    if len(content) > MAX_BYTES:
        raise ArtworkError("image_too_large", f"Image larger than {MAX_BYTES // (1024 * 1024)} MB.")
    ext, _ = sniff(content)
    folder = covers_dir()
    folder.mkdir(parents=True, exist_ok=True)
    delete_artwork(playlist_id)
    (folder / f"playlist-{playlist_id}{ext}").write_bytes(content)
    return f"/api/playlists/{playlist_id}/artwork?v={int(time.time() * 1000)}"


def delete_artwork(playlist_id: int) -> bool:
    """Toglie il file cover, se c'è. True se ne ha rimosso uno."""
    removed = False
    while (p := artwork_path(playlist_id)) is not None:
        p.unlink()
        removed = True
    return removed
