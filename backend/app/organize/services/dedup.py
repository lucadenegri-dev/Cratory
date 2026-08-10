"""Dedup: raggruppa i doppioni e propone un keeper. Puro, deterministico."""

import re
import unicodedata
from dataclasses import dataclass

from app.organize.core.config import settings
from app.organize.models import AudioFile

_LOSSLESS = {"flac", "wav", "aiff", "aif"}
_PATH_MARKER_RE = re.compile(r"\(\d+\)|copy|duplicate", re.IGNORECASE)
_TAG_FIELDS = ("artist", "title", "album", "album_artist", "genre", "year",
               "label", "track_no", "has_cover")


@dataclass(frozen=True)
class DupGroupComputed:
    match_kind: str
    member_ids: tuple[int, ...]
    keeper_id: int


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s.strip().lower())


def _present(value) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


def _completeness(f: AudioFile) -> int:
    return sum(1 for k in _TAG_FIELDS if _present(getattr(f, k)))


def _path_penalty(f: AudioFile):
    return (1 if _PATH_MARKER_RE.search(f.path or "") else 0, len(f.path or ""))


def _pick_keeper(files: list[AudioFile]) -> AudioFile:
    def key(f: AudioFile):
        return (
            0 if f.ext in _LOSSLESS else 1,
            -(f.bitrate or 0),
            -_completeness(f),
            _path_penalty(f),
            f.id,
        )
    return sorted(files, key=key)[0]


def _cluster_by_duration(files: list[AudioFile]) -> list[list[AudioFile]]:
    with_dur = sorted((f for f in files if f.duration_s is not None),
                      key=lambda f: f.duration_s)
    clusters: list[list[AudioFile]] = []
    cur: list[AudioFile] = []
    anchor = None
    for f in with_dur:
        if not cur:
            cur, anchor = [f], f.duration_s
        elif f.duration_s - anchor <= settings.fuzzy_dur_tol_s:
            cur.append(f)
        else:
            clusters.append(cur)
            cur, anchor = [f], f.duration_s
    if cur:
        clusters.append(cur)
    for f in files:  # file senza durata: ognuno per sé (non clusterizzabili)
        if f.duration_s is None:
            clusters.append([f])
    return clusters


def _all_same_hash(files: list[AudioFile]) -> bool:
    hashes = {f.content_hash for f in files}
    return len(hashes) == 1 and None not in hashes


def _make_group(members: list[AudioFile], force_exact: bool = False) -> DupGroupComputed:
    match_kind = "exact" if force_exact or _all_same_hash(members) else "fuzzy"
    ids = tuple(sorted(m.id for m in members))
    return DupGroupComputed(match_kind, ids, _pick_keeper(members).id)


def find_duplicates(files: list[AudioFile]) -> list[DupGroupComputed]:
    groups: list[DupGroupComputed] = []
    used: set[int] = set()

    # Passo 1: fuzzy primario (richiede artist e title)
    by_key: dict[tuple[str, str], list[AudioFile]] = {}
    for f in files:
        if _present(f.artist) and _present(f.title):
            by_key.setdefault((_norm(f.artist), _norm(f.title)), []).append(f)
    for _key, group_files in by_key.items():
        for cluster in _cluster_by_duration(group_files):
            if len(cluster) >= 2:
                groups.append(_make_group(cluster))
                used.update(m.id for m in cluster)

    # Passo 2: esatto di recupero sui file rimasti soli
    by_hash: dict[str, list[AudioFile]] = {}
    for f in files:
        if f.id in used or not f.content_hash:
            continue
        by_hash.setdefault(f.content_hash, []).append(f)
    for _h, group_files in by_hash.items():
        if len(group_files) >= 2:
            groups.append(_make_group(group_files, force_exact=True))

    return sorted(groups, key=lambda g: g.member_ids)
