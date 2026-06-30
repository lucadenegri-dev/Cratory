"""Selezione deterministica del candidato Soulseek (zero AI).

Ordina i file restituiti da slskd per aderenza ad artista+titolo e qualita',
secondo una preferenza configurabile.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher

from app.integrations.slskd import SlskdFile

_SPACE_RE = re.compile(r"\s+")
LOSSLESS_EXTS = {"flac", "wav", "aiff", "aif", "alac", "ape"}
LOSSY_EXTS = {"mp3", "m4a", "aac", "ogg", "opus", "wma"}

AUTO_PICK_MIN_CONFIDENCE = 0.7
_MIN_NAME_SCORE = 0.45


@dataclass(frozen=True)
class QualityPreference:
    prefer_lossless: bool = True
    min_bitrate: int = 256
    preferred_bitrate: int = 320


@dataclass
class ScoredCandidate:
    file: SlskdFile
    name_score: float
    quality_tier: int
    score: float
    confidence: float


def _norm(text: str | None) -> str:
    text = (text or "").lower().replace("&", " and ")
    text = re.sub(r"[^\w\s]", " ", text)
    return _SPACE_RE.sub(" ", text).strip()


def _strip_extension(filename: str) -> str:
    if "." in filename:
        return filename.rsplit(".", 1)[0]
    return filename


def _name_score(file: SlskdFile, artist: str, title: str) -> float:
    stem = _strip_extension(file.filename)
    hay = _norm(stem.replace("\\", "/").replace("/", " "))
    a, t = _norm(artist), _norm(title)
    s = 0.0
    if t:
        s += SequenceMatcher(None, t, hay).ratio() * 0.6
        if t in hay:
            s += 0.15
    if a:
        s += SequenceMatcher(None, a, hay).ratio() * 0.2
        if a in hay:
            s += 0.05
    return min(s, 1.0)


def _quality_tier(file: SlskdFile, pref: QualityPreference) -> int:
    ext = file.extension
    if ext in LOSSLESS_EXTS:
        return 3
    if ext in LOSSY_EXTS:
        br = file.bitrate or 0
        if br >= pref.preferred_bitrate:
            return 2
        if br >= pref.min_bitrate:
            return 1
        return 0
    return 0


def rank_candidates(files, *, artist: str, title: str,
                    pref: QualityPreference = QualityPreference()) -> list[ScoredCandidate]:
    scored: list[ScoredCandidate] = []
    for f in files:
        tier = _quality_tier(f, pref)
        if tier == 0:
            continue
        name = _name_score(f, artist, title)
        if name < _MIN_NAME_SCORE:
            continue
        avail = 1.0 if f.has_free_slot else 0.6
        score = name * 100 + tier * 12 + avail * 5
        confidence = round(min(1.0, name * 0.8 + (tier / 3) * 0.2), 3)
        scored.append(ScoredCandidate(file=f, name_score=round(name, 3),
                                      quality_tier=tier, score=round(score, 2),
                                      confidence=confidence))
    scored.sort(key=lambda c: c.score, reverse=True)
    return scored


def best_for_auto(files, *, artist: str, title: str,
                  pref: QualityPreference = QualityPreference()) -> ScoredCandidate | None:
    ranked = rank_candidates(files, artist=artist, title=title, pref=pref)
    if ranked and ranked[0].confidence >= AUTO_PICK_MIN_CONFIDENCE:
        return ranked[0]
    return None
