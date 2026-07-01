"""Alternative Generator deterministico (MVP 3, F9).

Per una traccia del set propone 3-5 sostituzioni motivate, valutando la
compatibilita' col brano precedente e successivo con lo scoring deterministico.
Nessuna chiamata AI: pura selezione/ranking sulle tracce della libreria non
gia' presenti nel set. Modalita': safer | softer | harder | same_artist | surprising.
"""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models import Setlist, Track
from app.repositories import all_playable_tracks
from app.services.scoring import risk_from_score, score_transition

BPM_TOLERANCE = 0.5            # margine per considerare due BPM "uguali"
SURPRISING_MIN_SCORE = 50      # sotto questa compatibilita' media non e' accettabile
SURPRISING_TARGET = 66         # punto "interessante ma non scontato" della compatibilita'


class AlternativesError(Exception):
    pass


@dataclass
class ScoredCandidate:
    track: Track
    score_prev: int | None
    score_next: int | None

    @property
    def combined(self) -> float:
        vals = [s for s in (self.score_prev, self.score_next) if s is not None]
        return sum(vals) / len(vals) if vals else 50.0

    @property
    def risk(self) -> str:
        vals = [s for s in (self.score_prev, self.score_next) if s is not None]
        return risk_from_score(min(vals)) if vals else "medium"


@dataclass
class Alternative:
    track: Track
    score_prev: int | None
    score_next: int | None
    reason: str
    risk_level: str


def _evaluate(cand: Track, prev: Track | None, nxt: Track | None) -> ScoredCandidate:
    sp = score_transition(prev, cand).score if prev else None
    sn = score_transition(cand, nxt).score if nxt else None
    return ScoredCandidate(track=cand, score_prev=sp, score_next=sn)


def _bpm_note(cand: Track, ref: Track) -> str:
    if cand.bpm and ref.bpm:
        d = cand.bpm - ref.bpm
        if abs(d) < BPM_TOLERANCE:
            return "stesso BPM"
        return f"{d:+.0f} BPM"
    return ""


def _reason(mode: str, cand: ScoredCandidate, ref: Track) -> str:
    bpm = _bpm_note(cand.track, ref)
    if mode == "safer":
        return f"Compatibile con i brani vicini · {cand.combined:.0f}/100"
    if mode == "softer":
        return f"Più morbida{f' · {bpm}' if bpm else ''}"
    if mode == "harder":
        return f"Più spinta{f' · {bpm}' if bpm else ''}"
    if mode == "same_artist":
        return f"Stesso artista{f' · {bpm}' if bpm else ''}"
    if mode == "surprising":
        return f"Scelta meno ovvia, ancora coerente · {cand.combined:.0f}/100"
    return ""


def find_alternatives(
    db: Session, setlist: Setlist, position: int, mode: str, limit: int = 5,
) -> list[Alternative]:
    ordered = sorted(setlist.tracks, key=lambda st: st.position)
    if not 1 <= position <= len(ordered):
        raise AlternativesError("Posizione non valida")

    idx = position - 1
    current = ordered[idx].track
    prev = ordered[idx - 1].track if idx > 0 else None
    nxt = ordered[idx + 1].track if idx < len(ordered) - 1 else None
    present_ids = {st.track_id for st in ordered}

    # Il pool rispetta la garanzia del set: niente lead se e' nato "solo posseduti".
    pool = [
        t for t in all_playable_tracks(db, owned_only=bool(setlist.owned_only))
        if t.id not in present_ids
    ]

    if mode == "same_artist":
        artist = (current.artist or "").strip().lower()
        if not artist:
            return []
        pool = [t for t in pool if (t.artist or "").strip().lower() == artist]

    scored = [_evaluate(t, prev, nxt) for t in pool]
    ranked = _rank(scored, mode, current)[:limit]
    return [
        Alternative(
            track=c.track,
            score_prev=c.score_prev,
            score_next=c.score_next,
            reason=_reason(mode, c, current),
            risk_level=c.risk,
        )
        for c in ranked
    ]


def _rank(scored: list[ScoredCandidate], mode: str, current: Track) -> list[ScoredCandidate]:
    ref_bpm = current.bpm

    if mode == "safer":
        return sorted(scored, key=lambda c: c.combined, reverse=True)

    if mode == "softer":
        pool = [c for c in scored if not (ref_bpm and c.track.bpm) or c.track.bpm <= ref_bpm + BPM_TOLERANCE]
        # transizioni buone, a parita' preferisci BPM piu' basso
        return sorted(pool, key=lambda c: (c.combined, -(c.track.bpm or 0)), reverse=True)

    if mode == "harder":
        pool = [c for c in scored if not (ref_bpm and c.track.bpm) or c.track.bpm >= ref_bpm - BPM_TOLERANCE]
        return sorted(pool, key=lambda c: (c.combined, c.track.bpm or 0), reverse=True)

    if mode == "same_artist":
        return sorted(scored, key=lambda c: c.combined, reverse=True)

    if mode == "surprising":
        # compatibilita' accettabile ma scelta meno ovvia: scarta gli score pessimi,
        # poi avvicinati a una compatibilita' "media", premiando il cambio di tonalita'.
        band = [c for c in scored if c.combined >= SURPRISING_MIN_SCORE]
        cur_key = current.camelot_key

        def surprise_key(c: ScoredCandidate):
            key_change = bool(c.track.camelot_key and cur_key and c.track.camelot_key != cur_key)
            return (abs(c.combined - SURPRISING_TARGET), not key_change)

        return sorted(band, key=surprise_key)

    return sorted(scored, key=lambda c: c.combined, reverse=True)
