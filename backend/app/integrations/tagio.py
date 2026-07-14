"""Lettura tag e info tecniche via mutagen. Nessuna scrittura in questo chunk."""

import re
import struct
from dataclasses import dataclass

from mutagen import File as MutagenFile
from mutagen import MutagenError
from mutagen.easymp4 import EasyMP4Tags
from mutagen.flac import FLAC, Picture
from mutagen.id3 import ID3, APIC, COMM, POPM, TALB, TCON, TDRC, TIT2, TPE1, TPE2, TPUB, TRCK
from mutagen.mp4 import MP4, MP4Cover

# EasyMP4 non conosce la chiave 'organization' (label): senza registrarla, la
# scrittura della label sui .m4a viene saltata in silenzio e il RETAG label si
# ripropone a ogni PLAN. La mappiamo sull'atom freeform ----:com.apple.iTunes:
# LABEL (convenzione Picard), così read/write in modalità easy la gestiscono.
if "organization" not in EasyMP4Tags.List:
    EasyMP4Tags.RegisterFreeformKey("organization", "LABEL")


class TagReadError(Exception):
    """Il file non è leggibile/riconoscibile da mutagen."""


class TagWriteError(Exception):
    """Scrittura tag fallita."""


_EASY_WRITE_KEY = {
    "artist": "artist", "title": "title", "album": "album",
    "album_artist": "albumartist", "genre": "genre", "year": "date",
    "label": "organization", "track_no": "tracknumber", "comment": "comment",
}

# WAV e AIFF usano ID3 ma NON hanno la modalità easy: vanno scritti i Frame.
_ID3_FRAMES = {
    "artist": TPE1, "title": TIT2, "album": TALB, "album_artist": TPE2,
    "genre": TCON, "year": TDRC, "label": TPUB, "track_no": TRCK,
}


def _empty(value) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _write_id3_frames(tags: ID3, changes: dict) -> None:
    """Scrive su un tag ID3 grezzo (WAV/AIFF) usando i Frame, non le stringhe."""
    for field, value in changes.items():
        if field == "comment":
            tags.delall("COMM")
            if not _empty(value):
                tags.add(COMM(encoding=3, lang="eng", desc="", text=str(value)))
            continue
        frame_cls = _ID3_FRAMES.get(field)
        if frame_cls is None:
            continue  # campo non mappato → best-effort, salta
        name = frame_cls.__name__
        if _empty(value):
            tags.delall(name)
        else:
            tags.setall(name, [frame_cls(encoding=3, text=str(value))])


def _repair_riff_tail(path: str) -> bool:
    """Ripara un WAV la cui coda RIFF è corrotta (chunk-id non ASCII o dimensione
    oltre EOF): alcuni file da DJ pool hanno byte spuri dopo i chunk validi, e
    mutagen ci si blocca sopra — scrive l'`id3 ` ma poi non lo rilegge.

    Ricostruisce il file tenendo solo i chunk ben formati dall'inizio e scartando
    la coda. Interviene SOLO se ha ritrovato sia `fmt ` sia `data` (mai rischiare
    di troncare l'audio). Ritorna True se ha modificato il file."""
    try:
        with open(path, "rb") as fh:
            head = fh.read(12)
            if len(head) < 12 or head[0:4] != b"RIFF" or head[8:12] != b"WAVE":
                return False
            size = fh.seek(0, 2)
            chunks: list[tuple[bytes, int, int]] = []   # (id, start, total_len)
            pos = 12
            clean = True
            while pos + 8 <= size:
                fh.seek(pos)
                cid = fh.read(4)
                csz = struct.unpack("<I", fh.read(4))[0]
                if not all(0x20 <= b < 0x7F for b in cid) or pos + 8 + csz > size:
                    clean = False   # id non ASCII o dimensione oltre EOF → coda spuria
                    break
                chunks.append((cid, pos, 8 + csz + (csz & 1)))
                pos += 8 + csz + (csz & 1)
            if clean:
                return False   # nessuna coda corrotta: niente da riparare
            kept = {c[0] for c in chunks}
            if b"fmt " not in kept or b"data" not in kept:
                return False   # senza fmt+data validi non tocco nulla
            fh.seek(0)
            body = bytearray()
            for _cid, start, total in chunks:
                fh.seek(start)
                body += fh.read(total)
        with open(path, "wb") as out:
            out.write(b"RIFF" + struct.pack("<I", 4 + len(body)) + b"WAVE" + body)
        return True
    except OSError as exc:
        raise TagWriteError(str(exc)) from exc


def _is_riff_wave(path: str) -> bool:
    try:
        with open(path, "rb") as fh:
            head = fh.read(12)
        return head[0:4] == b"RIFF" and head[8:12] == b"WAVE"
    except OSError:
        return False


def write_tags(path: str, changes: dict) -> None:
    # WAV con coda RIFF corrotta: ripara prima di scrivere, altrimenti mutagen
    # scrive i tag ma non riesce più a rileggerli (RETAG che si ripete all'infinito).
    if _is_riff_wave(path):
        _repair_riff_tail(path)
    try:
        audio = MutagenFile(path, easy=True)
        if audio is None:
            raise TagWriteError(f"formato non scrivibile: {path}")
        if audio.tags is None:
            audio.add_tags()
        if isinstance(audio.tags, ID3):
            # WAV/AIFF: niente modalità easy → l'assegnazione di stringhe esplode
            # ("X not a Frame instance"). Scrivi i Frame ID3 direttamente.
            _write_id3_frames(audio.tags, changes)
        else:
            for field, value in changes.items():
                key = _EASY_WRITE_KEY.get(field, field)
                try:
                    if _empty(value):
                        if key in audio:
                            del audio[key]
                    else:
                        audio[key] = str(value)
                except (KeyError, ValueError):
                    continue  # campo non supportato dal formato easy → salta
        audio.save()
    except MutagenError as exc:
        raise TagWriteError(str(exc)) from exc


# --- Rating (stelline) -------------------------------------------------------
# Il rating è format-specifico: POPM per ID3 (mp3/aiff/wav), chiave RATING
# Vorbis per FLAC. MP4 non gestito in v1 (→ None / no-op). Email canonica usata
# solo per il ripristino da undo (il valore-stelle si conserva, non l'email
# dell'app originale).
_RATING_EMAIL = "Sortory"


def _read_rating(raw) -> str | None:
    if raw is None:
        return None
    if isinstance(raw, FLAC):
        vals = raw.get("rating")
        v = str(vals[0]).strip() if vals else ""
        return v or None
    tags = getattr(raw, "tags", None)
    if isinstance(tags, ID3):
        rated = [p for p in tags.getall("POPM") if getattr(p, "rating", 0)]
        return str(rated[0].rating) if rated else None
    return None


def read_rating(path: str) -> str | None:
    """Rating nativo del file come stringa (POPM 0-255 per ID3, valore RATING per
    FLAC/Vorbis). None se assente o formato non gestito (es. MP4)."""
    try:
        raw = MutagenFile(path)
    except MutagenError as exc:
        raise TagReadError(str(exc)) from exc
    return _read_rating(raw)


def _apply_rating(path: str, value) -> None:
    clear = _empty(value)
    try:
        raw = MutagenFile(path)
        if raw is None:
            raise TagWriteError(f"formato non scrivibile: {path}")
        if isinstance(raw, FLAC):
            if clear:
                if "rating" in raw:
                    del raw["rating"]
            else:
                raw["rating"] = [str(value)]
            raw.save()
            return
        tags = getattr(raw, "tags", None)
        if isinstance(tags, ID3):
            tags.delall("POPM")
            if not clear:
                tags.add(POPM(email=_RATING_EMAIL, rating=int(value), count=0))
            raw.save()
            return
        # MP4 e altri formati: rating non gestito in v1 → no-op.
    except (MutagenError, ValueError) as exc:
        raise TagWriteError(str(exc)) from exc


def clear_rating(path: str) -> None:
    """Rimuove il rating (POPM/RATING). No-op sui formati non gestiti."""
    _apply_rating(path, None)


def set_rating(path: str, value: str) -> None:
    """Riscrive il rating (per il ripristino da undo)."""
    _apply_rating(path, value)


def write_cover(path: str, data: bytes, mime: str = "image/jpeg") -> None:
    """Embed della cover (type 3 = front). FLAC Picture, ID3 APIC (mp3/wav/aiff),
    MP4 covr. Sostituisce eventuali cover esistenti."""
    try:
        raw = MutagenFile(path)
        if raw is None:
            raise TagWriteError(f"formato non scrivibile: {path}")
        if isinstance(raw, FLAC):
            pic = Picture()
            pic.type = 3
            pic.mime = mime
            pic.data = data
            raw.clear_pictures()
            raw.add_picture(pic)
        elif isinstance(raw, MP4):
            fmt = MP4Cover.FORMAT_PNG if mime == "image/png" else MP4Cover.FORMAT_JPEG
            raw["covr"] = [MP4Cover(data, imageformat=fmt)]
        else:  # ID3-based: mp3, wav, aiff
            if raw.tags is None:
                raw.add_tags()
            raw.tags.delall("APIC")
            raw.tags.add(APIC(encoding=3, mime=mime, type=3, desc="", data=data))
        raw.save()
    except MutagenError as exc:
        raise TagWriteError(str(exc)) from exc


def remove_cover(path: str) -> None:
    """Rimuove ogni cover embeddata (usato dall'undo)."""
    try:
        raw = MutagenFile(path)
        if raw is None:
            return
        if isinstance(raw, FLAC):
            raw.clear_pictures()
        elif isinstance(raw, MP4):
            if "covr" in raw:
                del raw["covr"]
        elif raw.tags is not None and hasattr(raw.tags, "delall"):
            raw.tags.delall("APIC")
        raw.save()
    except MutagenError as exc:
        raise TagWriteError(str(exc)) from exc


@dataclass
class TechInfo:
    bitrate: int | None
    sample_rate: int | None
    channels: int | None
    duration_s: float | None


@dataclass
class TagData:
    artist: str | None
    title: str | None
    album: str | None
    album_artist: str | None
    genre: str | None
    year: int | None
    label: str | None
    track_no: int | None
    comment: str | None
    isrc: str | None
    has_cover: bool


def _first(tags, key):
    if not tags:
        return None
    value = tags.get(key)
    if isinstance(value, list):
        return str(value[0]) if value else None
    return str(value) if value is not None else None


# Lettura di un ID3 grezzo (WAV/AIFF) verso le chiavi "easy" usate da read_tags:
# senza modalità easy le chiavi sono i nomi dei Frame (TPE1, TIT2, …).
_ID3_READ = {
    "artist": "TPE1", "title": "TIT2", "album": "TALB", "albumartist": "TPE2",
    "genre": "TCON", "date": "TDRC", "organization": "TPUB", "tracknumber": "TRCK",
    "comment": "COMM",
    "isrc": "TSRC",
}


def _id3_as_easy(id3: ID3) -> dict:
    out: dict[str, str] = {}
    for easy_key, frame_name in _ID3_READ.items():
        frames = id3.getall(frame_name)
        if frames:
            out[easy_key] = str(frames[0])
    return out


def _parse_year(value):
    if not value:
        return None
    match = re.search(r"\d{4}", str(value))
    return int(match.group()) if match else None


def _parse_track(value):
    if not value:
        return None
    head = str(value).split("/")[0].strip()
    try:
        return int(head)
    except ValueError:
        return None


def _detect_cover(raw) -> bool:
    if raw is None:
        return False
    if getattr(raw, "pictures", None):  # FLAC
        return True
    tags = getattr(raw, "tags", None)
    if tags is None:
        return False
    if hasattr(tags, "getall") and tags.getall("APIC"):  # ID3 (mp3)
        return True
    try:
        if "covr" in tags:  # MP4 (m4a)
            return True
    except TypeError:
        pass
    return False


def read_info(path: str) -> TechInfo:
    try:
        mf = MutagenFile(path)
    except MutagenError as exc:
        raise TagReadError(str(exc)) from exc
    if mf is None or getattr(mf, "info", None) is None:
        raise TagReadError(f"formato non riconosciuto: {path}")
    info = mf.info
    return TechInfo(
        bitrate=getattr(info, "bitrate", None),
        sample_rate=getattr(info, "sample_rate", None),
        channels=getattr(info, "channels", None),
        duration_s=getattr(info, "length", None),
    )


def read_tags(path: str) -> TagData:
    try:
        easy = MutagenFile(path, easy=True)
        raw = MutagenFile(path)
    except MutagenError as exc:
        raise TagReadError(str(exc)) from exc
    if easy is None:
        raise TagReadError(f"formato non riconosciuto: {path}")
    # WAV/AIFF: easy.tags è un ID3 grezzo (chiavi = nomi Frame) → normalizza.
    tags = _id3_as_easy(easy.tags) if isinstance(easy.tags, ID3) else (easy.tags or {})
    return TagData(
        artist=_first(tags, "artist"),
        title=_first(tags, "title"),
        album=_first(tags, "album"),
        album_artist=_first(tags, "albumartist"),
        genre=_first(tags, "genre"),
        year=_parse_year(_first(tags, "date")),
        label=_first(tags, "organization") or _first(tags, "label"),
        track_no=_parse_track(_first(tags, "tracknumber")),
        comment=_first(tags, "comment"),
        isrc=_first(tags, "isrc"),
        has_cover=_detect_cover(raw),
    )
