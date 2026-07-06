"""Import della collezione Rekordbox (File > Export Collection in xml format).
Il parser è puro (testabile senza DB/rete); l'applicazione al DB sta in apply_collection."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from urllib.parse import unquote, urlparse

import defusedxml.ElementTree as ET  # parser sicuro (anti-XXE/entity-expansion)
from xml.etree.ElementTree import ParseError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.integrations.local_files import audio_hash
from app.models import Track
from app.services.camelot import parse_camelot
from app.services.energy import estimate_energy
from app.services.track_status import refresh_status

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


def _norm_path(p: str | None) -> str | None:
    return os.path.normpath(p) if p else None


def _low(s: str | None) -> str:
    return (s or "").strip().lower()


def _match(r, by_path, by_hash, by_at):
    t = by_path.get(_norm_path(r.path))
    if t is not None:
        return t
    if r.path and os.path.isfile(r.path):
        try:
            t = by_hash.get(audio_hash(r.path))
            if t is not None:
                return t
        except Exception as exc:  # file illeggibile: degrada al match testuale
            logger.warning("audio_hash fallito per %s: %s", r.path, exc)
    return by_at.get((_low(r.artist), _low(r.title)))


def apply_collection(db: Session, xml_bytes: bytes) -> dict:
    rows = parse_collection(xml_bytes)
    owned = list(db.scalars(select(Track).where(Track.has_local_file.is_(True))).all())
    by_path = {_norm_path(t.local_path): t for t in owned if t.local_path}
    by_hash = {t.audio_hash: t for t in owned if t.audio_hash}
    by_at = {(_low(t.artist), _low(t.title)): t for t in owned if t.artist and t.title}

    matched = bpm_set = key_set = energy_set = 0
    seen: set[int] = set()
    for r in rows:
        t = _match(r, by_path, by_hash, by_at)
        if t is None or t.id in seen:
            continue
        seen.add(t.id)
        matched += 1
        if r.bpm is not None and t.bpm is None:
            t.bpm = r.bpm
            bpm_set += 1
        if r.camelot and not t.camelot_key:
            t.camelot_key = r.camelot
            key_set += 1
        if t.bpm is not None:
            new_energy = estimate_energy(t.bpm, None, t.genre)
            if new_energy is not None and new_energy != t.energy:
                t.energy = new_energy
                energy_set += 1
        refresh_status(t)
    db.commit()
    return {"in_file": len(rows), "matched": matched,
            "unmatched": len(rows) - matched, "bpm_set": bpm_set,
            "key_set": key_set, "energy_set": energy_set}
