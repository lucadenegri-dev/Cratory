"""Lettura tag e info tecniche via mutagen. Nessuna scrittura in questo chunk."""

import re
from dataclasses import dataclass

from mutagen import File as MutagenFile
from mutagen import MutagenError


class TagReadError(Exception):
    """Il file non è leggibile/riconoscibile da mutagen."""


class TagWriteError(Exception):
    """Scrittura tag fallita."""


_EASY_WRITE_KEY = {
    "artist": "artist", "title": "title", "album": "album",
    "album_artist": "albumartist", "genre": "genre", "year": "date",
    "label": "organization", "track_no": "tracknumber", "comment": "comment",
}


def write_tags(path: str, changes: dict) -> None:
    try:
        audio = MutagenFile(path, easy=True)
        if audio is None:
            raise TagWriteError(f"formato non scrivibile: {path}")
        if audio.tags is None:
            audio.add_tags()
        for field, value in changes.items():
            key = _EASY_WRITE_KEY.get(field, field)
            try:
                if value is None or (isinstance(value, str) and not value.strip()):
                    if key in audio:
                        del audio[key]
                else:
                    audio[key] = str(value)
            except (KeyError, ValueError):
                continue  # campo non supportato dal formato easy → best-effort, salta
        audio.save()
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
    has_cover: bool


def _first(tags, key):
    if not tags:
        return None
    value = tags.get(key)
    if isinstance(value, list):
        return str(value[0]) if value else None
    return str(value) if value is not None else None


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
    tags = easy.tags or {}
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
        has_cover=_detect_cover(raw),
    )
