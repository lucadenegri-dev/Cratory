"""Import della collezione Rekordbox (File > Export Collection in xml format).
Il parser è puro (testabile senza DB/rete); l'applicazione al DB sta in apply_collection."""

from __future__ import annotations

import logging
import os
import unicodedata
from dataclasses import dataclass
from urllib.parse import unquote, urlparse

import defusedxml.ElementTree as ET  # parser sicuro (anti-XXE/entity-expansion)
from xml.etree.ElementTree import ParseError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.integrations.local_files import audio_hash
from app.models import Track
from app.services.camelot import parse_camelot
from app.services.energy import apply_estimated_energy
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
        parsed = parse_camelot(tonality) if tonality else None
        # Canonico (numero+lettera maiuscola), non la stringa grezza: cosi' le key
        # combaciano con la normalizzazione del percorso manuale (routers/tracks.py).
        camelot = f"{parsed[0]}{parsed[1]}" if parsed else None
        out.append(RbTrack(
            path=_location_to_path(el.get("Location")),
            bpm=_bpm(el.get("AverageBpm")),
            camelot=camelot,
            artist=(el.get("Artist") or "").strip() or None,
            title=(el.get("Name") or "").strip() or None,
        ))
    return out


def _norm_path(p: str | None) -> str | None:
    # NFC: macOS/Rekordbox puo' decodificare Location in NFD (es. "e" + accento
    # combinante), mentre l'indicizzatore salva local_path in NFC. Senza questa
    # normalizzazione lo stesso percorso, byte-diverso, non farebbe mai match.
    return os.path.normpath(unicodedata.normalize("NFC", p)) if p else None


def _low(s: str | None) -> str:
    return (s or "").strip().lower()


def _match(r, by_path, by_hash, by_at, owned_basenames):
    t = by_path.get(_norm_path(r.path))
    if t is not None:
        return t
    # Fallback hash: serve solo per "stesso file spostato" — in quel caso il nome
    # file sopravvive quasi sempre. Gate sul basename per evitare un decode ffmpeg
    # (audio_hash, ~60s) per ogni riga Rekordbox che non e' nostra.
    if r.path and os.path.basename(_norm_path(r.path)) in owned_basenames and os.path.isfile(r.path):
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
    owned_basenames = {os.path.basename(_norm_path(t.local_path)) for t in owned if t.local_path}

    matched = bpm_set = key_set = energy_set = no_match = 0
    seen: set[int] = set()
    for r in rows:
        t = _match(r, by_path, by_hash, by_at, owned_basenames)
        if t is None:
            no_match += 1
            continue
        if t.id in seen:
            continue  # riga duplicata su una traccia gia' matchata: non e' un mancato match
        seen.add(t.id)
        matched += 1
        if r.bpm is not None and t.bpm is None:
            t.bpm = r.bpm
            bpm_set += 1
        if r.camelot and not t.camelot_key:
            t.camelot_key = r.camelot
            key_set += 1
        if apply_estimated_energy(t):
            energy_set += 1
        refresh_status(t)
    db.commit()
    return {"in_file": len(rows), "matched": matched,
            "unmatched": no_match, "bpm_set": bpm_set,
            "key_set": key_set, "energy_set": energy_set}
