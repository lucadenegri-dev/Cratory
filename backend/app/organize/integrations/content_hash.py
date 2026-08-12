"""Identità audio: hash dello stream (non dei tag), stabile al retag.

mp3/flac: si salta il contenitore di metadata e si hasha l'audio (method='stream').
Altri formati: hash full-file (method='file'), con la nota della limitazione.
"""

import hashlib
import logging

logger = logging.getLogger(__name__)


def _synchsafe(b: bytes) -> int:
    return (b[0] << 21) | (b[1] << 14) | (b[2] << 7) | b[3]


def _mp3_range(data: bytes) -> tuple[int, int] | None:
    """Intervallo [start, end) dei frame MPEG, saltando ID3v2 in testa e ID3v1 in coda.

    Restituisce None se l'intestazione ID3v2 è corrotta/troncata (start >= end).
    """
    start = 0
    if data[:3] == b"ID3" and len(data) >= 10:
        start = 10 + _synchsafe(data[6:10])
        if data[5] & 0x10:  # footer ID3v2 presente
            start += 10
    end = len(data)
    if end - start >= 128 and data[end - 128 : end - 125] == b"TAG":
        end -= 128
    if start >= end:
        return None
    return start, end


def _flac_range(data: bytes) -> tuple[int, int] | None:
    """Intervallo dei frame audio, saltando i metadata block dopo il marker fLaC.

    Restituisce None se:
    - manca il marker fLaC (non è un FLAC);
    - il file è troncato (il loop termina senza trovare il last-block flag);
    - l'offset post-loop supera la fine del file (nessun frame audio).
    """
    if data[:4] != b"fLaC":
        return None
    i = 4
    found_last = False
    while i + 4 <= len(data):
        header = data[i]
        length = int.from_bytes(data[i + 1 : i + 4], "big")
        i += 4 + length
        if header & 0x80:  # ultimo metadata block
            found_last = True
            break
    if not found_last or i >= len(data):
        return None
    return i, len(data)


_STREAM = {".mp3": _mp3_range, ".flac": _flac_range}


def compute(path: str, ext: str) -> tuple[str | None, str]:
    ext = ext.lower()
    try:
        with open(path, "rb") as fh:
            data = fh.read()
    except OSError:
        return None, "file"
    ranger = _STREAM.get(ext)
    if ranger is not None:
        result = ranger(data)
        if result is not None:
            start, end = result
            return hashlib.blake2b(data[start:end]).hexdigest(), "stream"
        logger.debug(
            "content_hash fallback full-file (container corrotto per %s): %s", ext, path
        )
    else:
        logger.debug("content_hash full-file (no stream-strip per %s): %s", ext, path)
    return hashlib.blake2b(data).hexdigest(), "file"
