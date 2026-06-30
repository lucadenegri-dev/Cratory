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


def _basename_stem(filename: str) -> str:
    """Solo il nome file (senza cartelle ne' estensione).

    I path Soulseek sono lunghi e rumorosi (`Music\\Arca\\KiCk i (2020) [FLAC]\\02 Time.flac`):
    il titolo va confrontato col nome file, non con l'intero path, altrimenti il
    rumore di cartelle/anno/formato abbatte la similarita'.
    """
    name = filename.replace("\\", "/").rsplit("/", 1)[-1]
    return _strip_extension(name)


def _name_score(file: SlskdFile, artist: str, title: str) -> float:
    full = _norm(file.filename.replace("\\", "/").replace("/", " "))
    base = _norm(_basename_stem(file.filename))
    a, t = _norm(artist), _norm(title)
    s = 0.0
    if t:
        # Titolo: confronto col nome file (alto segnale) + bonus se contenuto.
        s += SequenceMatcher(None, t, base).ratio() * 0.55
        if t in base:
            s += 0.30
        elif t in full:
            s += 0.15
    if a:
        # Artista: di solito e' una cartella del path → cerca nell'intero path.
        if a in full:
            s += 0.15
        else:
            s += SequenceMatcher(None, a, full).ratio() * 0.10
    return min(s, 1.0)


def _quality_tier(file: SlskdFile, pref: QualityPreference) -> int:
    ext = file.extension
    if ext in LOSSLESS_EXTS:
        return 3
    if ext in LOSSY_EXTS:
        br = file.bitrate
        if br is None:
            # Soulseek spesso non riporta il bitrate in ricerca: ignoto != sotto-soglia.
            return 1
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
