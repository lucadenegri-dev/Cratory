"""Risoluzione preview audio per i lead del Discovery dig (funzione pura).

Catena deterministica: iTunes (clip 30s pulita) -> video YouTube della release
Discogs -> nessuna. Le dipendenze di rete sono INIETTATE come callable, così il
service è testabile senza rete. Vedi docs/superpowers/specs/2026-07-16-discovery-preview-audio-design.md
"""

import logging
import re
from dataclasses import dataclass
from typing import Callable
from urllib.parse import parse_qs, urlparse

logger = logging.getLogger(__name__)

ItunesSearch = Callable[[str], list[dict]]
GetRelease = Callable[[int], dict]

_NOISE = re.compile(r"\b(?:feat\.?|featuring|remix|edit|version|original|mix)\b", re.IGNORECASE)
_PARENS = re.compile(r"\(.*?\)|\[.*?\]")
_NONWORD = re.compile(r"[^a-z0-9 ]")


@dataclass
class PreviewResult:
    kind: str  # "itunes" | "youtube" | "none"
    audio_url: str | None = None
    youtube_video_id: str | None = None
    source_url: str | None = None
    matched_title: str | None = None


def norm_tokens(s: str) -> set[str]:
    s = (s or "").lower()
    s = _PARENS.sub(" ", s)
    s = _NOISE.sub(" ", s)
    s = _NONWORD.sub(" ", s)
    return {t for t in s.split() if len(t) > 1}


def _matches(want: set[str], got: set[str]) -> bool:
    if not want:
        return False
    return len(want & got) >= max(1, len(want) // 2)


def parse_youtube_id(uri: str) -> str | None:
    if not uri:
        return None
    u = urlparse(uri)
    host = (u.hostname or "").lower()
    if host.endswith("youtu.be"):
        vid = u.path.lstrip("/")
        return vid or None
    if "youtube.com" in host:
        qs = parse_qs(u.query)
        vals = qs.get("v")
        if vals:
            return vals[0]
    return None


def extract_youtube_videos(payload: dict) -> list[dict]:
    out = []
    for v in (payload.get("videos") or []):
        vid = parse_youtube_id(v.get("uri") or "")
        if not vid:
            continue
        out.append({
            "youtube_video_id": vid,
            "title": v.get("title") or "",
            "duration_seconds": v.get("duration"),
        })
    return out


def itunes_hit(results: list[dict], title: str) -> dict | None:
    want = norm_tokens(title)
    for r in results:
        if not r.get("previewUrl"):
            continue
        if _matches(want, norm_tokens(r.get("trackName", ""))):
            return r
    return None


def pick_video(videos: list[dict], title: str, level: str) -> dict | None:
    if not videos:
        return None
    if level == "release":
        return videos[0]
    want = norm_tokens(title)
    for v in videos:
        if _matches(want, norm_tokens(v.get("title", ""))):
            return v
    return None


def resolve_preview(
    artist: str,
    title: str,
    *,
    itunes_search: ItunesSearch,
    get_release: GetRelease | None = None,
    discogs_id: int | None = None,
    level: str = "track",
) -> PreviewResult:
    # 1. iTunes (pulito)
    term = " ".join(p for p in (artist, title) if p).strip()
    try:
        results = itunes_search(term)
    except Exception as exc:  # rete/rate: la preview manca, non è un errore fatale
        logger.info("itunes preview lookup failed: %s", exc)
        results = []
    hit = itunes_hit(results, title)
    if hit:
        return PreviewResult(
            kind="itunes",
            audio_url=hit.get("previewUrl"),
            source_url=hit.get("trackViewUrl"),
            matched_title=hit.get("trackName"),
        )
    # 2. Fallback video YouTube della release
    if discogs_id is not None and get_release is not None:
        try:
            payload = get_release(discogs_id)
            videos = extract_youtube_videos(payload)
        except Exception as exc:
            logger.info("discogs videos lookup failed: %s", exc)
            videos = []
        vid = pick_video(videos, title, level)
        if vid:
            return PreviewResult(
                kind="youtube",
                youtube_video_id=vid["youtube_video_id"],
                source_url=f"https://www.youtube.com/watch?v={vid['youtube_video_id']}",
                matched_title=vid.get("title") or None,
            )
    # 3. Niente
    return PreviewResult(kind="none")
