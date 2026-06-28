"""Inspector: rileva problemi per-file. Puro (nessun DB), deterministico."""

import os
import re
from dataclasses import dataclass

from app.core.config import settings
from app.models import AudioFile

_LOSSLESS = {"flac", "wav", "aiff", "aif"}
_JUNK_TITLE_RE = re.compile(r"^(track\s*\d+|\d+)$", re.IGNORECASE)
_SPAM_RE = re.compile(r"https?://|www\.|ripped by|encoded by|\.com\b", re.IGNORECASE)
_GENRE_SEP_RE = re.compile(r"[,/;]")
_GENRE_JUNK = {"unbekannt", "unknown", "sconosciuto", "music", "other",
               "various", "n/a", "none"}


def _is_dirty_genre(value: str) -> bool:
    """Genere presente ma da normalizzare: blob multi-genere, URL o parola-spazzatura."""
    s = (value or "").strip()
    if not s:
        return False
    low = s.lower()
    if _GENRE_SEP_RE.search(s):
        return True
    if "http" in low or "://" in s or "www." in low:
        return True
    return low in _GENRE_JUNK


@dataclass(frozen=True)
class IssueComputed:
    file_id: int
    type: str
    field: str | None
    severity: str
    detail: str
    suggested_fix: dict | None


def inspect(files: list[AudioFile]) -> list[IssueComputed]:
    out: list[IssueComputed] = []
    for f in files:
        out.extend(_inspect_one(f))
    return out


def _present(value) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


def _casing_fix(value):
    if not isinstance(value, str):
        return None
    s = value.strip()
    if len(s.split()) < 2:  # solo multi-parola, per non toccare nomi stilizzati
        return None
    if s.isupper() or s.islower():
        proposed = s.title()
        if proposed != s:
            return proposed
    return None


def _norm_basic(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _inspect_one(f: AudioFile) -> list[IssueComputed]:
    out: list[IssueComputed] = []
    if f.scan_error:
        return [IssueComputed(f.id, "scan_error", None, "error", f.scan_error, None)]

    for field in ("artist", "title"):
        if not _present(getattr(f, field)):
            out.append(IssueComputed(f.id, "missing_required_tag", field, "error",
                                     f"{field} mancante", None))

    for field in ("genre", "year", "label"):
        if not _present(getattr(f, field)):
            out.append(IssueComputed(f.id, "missing_metadata", field, "warning",
                                     f"{field} mancante", None))

    if _present(f.genre) and _is_dirty_genre(f.genre):
        out.append(IssueComputed(f.id, "dirty_genre", "genre", "warning",
                                 "genere da normalizzare", None))

    for field in ("artist", "title", "album"):
        value = getattr(f, field)
        fix = _casing_fix(value)
        if fix is not None:
            out.append(IssueComputed(f.id, "inconsistent_casing", field, "warning",
                                     f"casing incoerente in {field}",
                                     {"field": field, "action": "retag", "from": value, "to": fix}))

    if f.title and _JUNK_TITLE_RE.match(f.title.strip()):
        out.append(IssueComputed(f.id, "junk_tag", "title", "warning", "title spazzatura",
                                 {"field": "title", "action": "clear"}))
    if f.comment and (_SPAM_RE.search(f.comment) or len(f.comment.strip()) > 200):
        out.append(IssueComputed(f.id, "junk_tag", "comment", "warning", "commento spazzatura",
                                 {"field": "comment", "action": "clear"}))

    if _present(f.artist) and _present(f.title):
        stem = _norm_basic(os.path.splitext(os.path.basename(f.path))[0])
        if _norm_basic(f.artist) not in stem and _norm_basic(f.title) not in stem:
            out.append(IssueComputed(f.id, "filename_tag_mismatch", None, "warning",
                                     "il nome file non riflette i tag", None))

    if f.ext not in _LOSSLESS and f.bitrate is not None \
            and f.bitrate < settings.low_bitrate_kbps * 1000:
        out.append(IssueComputed(f.id, "low_quality", None, "info",
                                 f"bitrate basso ({f.bitrate} bps)", None))

    if f.duration_s is not None and (f.duration_s < settings.duration_min_s
                                     or f.duration_s > settings.duration_max_s):
        out.append(IssueComputed(f.id, "suspicious_duration", None, "info",
                                 f"durata sospetta ({f.duration_s}s)", None))
    return out
