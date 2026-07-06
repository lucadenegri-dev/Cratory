"""Import della collezione Rekordbox (File > Export Collection in xml format).
Il parser è puro (testabile senza DB/rete); l'applicazione al DB sta in apply_collection."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from urllib.parse import unquote, urlparse

import defusedxml.ElementTree as ET  # parser sicuro (anti-XXE/entity-expansion)
from xml.etree.ElementTree import ParseError

from app.services.camelot import parse_camelot

logger = logging.getLogger(__name__)


@dataclass
class RbTrack:
    path: str | None
    bpm: float | None
    camelot: str | None
    artist: str | None
    title: str | None


def _location_to_path(location: str | None) -> str | None:
    if not location:
        return None
    # Rekordbox: "file://localhost/Users/..." (percent-encoded). urlparse dà il path.
    parsed = urlparse(location)
    path = unquote(parsed.path)
    return path or None


def _bpm(value: str | None) -> float | None:
    try:
        b = float(value) if value else 0.0
    except ValueError:
        return None
    return b if b > 0 else None


def parse_collection(xml_bytes: bytes) -> list[RbTrack]:
    try:
        root = ET.fromstring(xml_bytes)
    except (ParseError, ValueError) as exc:
        # defusedxml solleva ParseError su XML malformato ed EntitiesForbidden
        # (sottoclasse di ValueError-like) su entity pericolose: entrambe → 400.
        raise ValueError(f"XML Rekordbox non valido o non sicuro: {exc}") from exc
    out: list[RbTrack] = []
    for el in root.iter("TRACK"):
        tonality = (el.get("Tonality") or "").strip()
        camelot = tonality if tonality and parse_camelot(tonality) else None
        out.append(RbTrack(
            path=_location_to_path(el.get("Location")),
            bpm=_bpm(el.get("AverageBpm")),
            camelot=camelot,
            artist=(el.get("Artist") or "").strip() or None,
            title=(el.get("Name") or "").strip() or None,
        ))
    return out
