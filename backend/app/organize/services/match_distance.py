"""Confidenza graduata di un match provider via distanza pesata locale.
Puro e deterministico (niente I/O), stile dedup.py. Ispirato a beets
autotag/distance.py, adattato al modello per-traccia di Sortory: si
confrontano i tag che il file GIA' dichiara con i valori canonici del
candidato MusicBrainz."""

import difflib
import re

# Pesi per campo per il match TESTUALE. Ispirati a beets, ridotti ai campi
# che Sortory risolve davvero. artist/title sono le ancore.
_WEIGHTS = {"artist": 3.0, "title": 3.0, "album": 3.0, "year": 1.0, "label": 0.5}

# Soglie distanza -> grado. PROVVISORIE: calibrate dai test (il metrico
# difflib differisce da beets, i suoi 0.04/0.25 non si trasferiscono).
_STRONG_MAX = 0.15
_MEDIUM_MAX = 0.40

_FEAT_RE = re.compile(r"\b(feat|ft|featuring)\b.*$", re.IGNORECASE)
_THE_RE = re.compile(r"^the\s+", re.IGNORECASE)
_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)
_WS_RE = re.compile(r"\s+")

# campo file -> chiave nel dict canonical del provider
_CANON_KEY = {"artist": "canonical_artist", "title": "canonical_title",
              "album": "canonical_album", "label": "label"}


def _normalize(s: str) -> str:
    """Minuscole, via feat./the/punteggiatura, spazi compattati."""
    s = s.casefold()
    s = _FEAT_RE.sub("", s)
    s = _THE_RE.sub("", s)
    s = _PUNCT_RE.sub(" ", s)
    return _WS_RE.sub(" ", s).strip()


def _string_dist(a: str, b: str) -> float:
    na, nb = _normalize(a), _normalize(b)
    if not na and not nb:
        return 0.0
    return 1.0 - difflib.SequenceMatcher(None, na, nb).ratio()


def _present(v) -> bool:
    if v is None:
        return False
    if isinstance(v, str):
        return bool(v.strip())
    return True


def _canonical_value(canonical: dict, field: str):
    if field == "year":
        rd = canonical.get("release_date")
        if isinstance(rd, str) and len(rd) >= 4 and rd[:4].isdigit():
            return int(rd[:4])
        return None
    return canonical.get(_CANON_KEY[field])


def weighted_distance(file, canonical: dict) -> float | None:
    """Distanza pesata 0..1 sui soli campi comparabili (presenti su entrambi).
    None se nessun campo e' comparabile (es. file senza artist ne' title)."""
    num = 0.0
    den = 0.0
    for field, weight in _WEIGHTS.items():
        fv = getattr(file, field, None)
        cv = _canonical_value(canonical, field)
        if not _present(fv) or not _present(cv):
            continue
        if field == "year":
            d = 0.0 if int(fv) == int(cv) else 1.0
        else:
            d = _string_dist(str(fv), str(cv))
        num += weight * d
        den += weight
    if den == 0:
        return None
    return num / den


def grade_confidence(file, canonical: dict, *, exact: bool) -> str:
    """Grado di confidenza: "strong" | "medium" | "weak".
    exact=True (match per MBID/ISRC) -> strong a prescindere dai tag."""
    if exact:
        return "strong"
    d = weighted_distance(file, canonical)
    if d is None:
        return "weak"
    if d <= _STRONG_MAX:
        return "strong"
    if d <= _MEDIUM_MAX:
        return "medium"
    return "weak"
