"""Compatibilita' tecnica di un passaggio del set manuale (tappa 4).

Non si salva niente: si calcola a ogni lettura dai metadati correnti. La regola
che governa tutto il modulo e' della spec: con un dato mancante si DICHIARA che
manca, non si mostra il punteggio neutro che `score_transition` restituirebbe —
un 50 su una traccia senza BPM sembra un giudizio e non lo e'.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.models import SetlistTrack
from app.services.camelot import parse_camelot
from app.services.scoring import pitch_percent, score_transition


@dataclass(frozen=True)
class PairCompat:
    bpm_from: float | None = None
    bpm_to: float | None = None
    bpm_percent: float | None = None
    halftime: bool = False
    key_from: str | None = None
    key_to: str | None = None
    key_relation: str = "unknown"
    score: int | None = None
    missing: list[str] = field(default_factory=list)


class _AlTempoDi:
    """La traccia vista al tempo di cabina. Delega tutto alla vera `Track` e
    sovrascrive il solo `bpm`: assegnarlo sull'oggetto caricato lo scriverebbe
    in libreria al primo flush, che e' esattamente cio' che `play_bpm` evita.
    """

    def __init__(self, track, bpm: float) -> None:
        self._track = track
        self.bpm = bpm

    def __getattr__(self, nome: str):
        return getattr(self._track, nome)


def bpm_of(row: SetlistTrack) -> float | None:
    """Il tempo a cui questa riga suona: «la suono a» se c'e', altrimenti quello
    della traccia. `play_bpm` vale in questo set e non tocca la libreria."""
    if row.play_bpm:
        return row.play_bpm
    return row.track.bpm if row.track is not None else None


def _relation(from_key: str | None, to_key: str | None) -> str:
    a, b = parse_camelot(from_key), parse_camelot(to_key)
    if a is None or b is None:
        return "unknown"
    if a == b:
        return "same"
    num_a, let_a = a
    num_b, let_b = b
    if num_a == num_b:
        return "same_number"
    if min((num_a - num_b) % 12, (num_b - num_a) % 12) == 1 and let_a == let_b:
        return "adjacent"
    return "weak"


def pair_compat(from_row: SetlistTrack, to_row: SetlistTrack) -> PairCompat:
    bpm_from, bpm_to = bpm_of(from_row), bpm_of(to_row)
    key_from = from_row.track.camelot_key if from_row.track is not None else None
    key_to = to_row.track.camelot_key if to_row.track is not None else None

    missing: list[str] = []
    if not bpm_from or not bpm_to:
        missing.append("bpm")
    relation = _relation(key_from, key_to)
    if relation == "unknown":
        missing.append("key")

    percento: float | None = None
    piegato = False
    if "bpm" not in missing:
        percento, piegato = pitch_percent(bpm_from, bpm_to)

    score = None
    if not missing and from_row.track is not None and to_row.track is not None:
        # `score_transition` legge i BPM dalla traccia: «la suono a» va fatto
        # valere senza toccare gli oggetti caricati, che finirebbero al flush.
        score = score_transition(
            _AlTempoDi(from_row.track, bpm_from), _AlTempoDi(to_row.track, bpm_to)
        ).score

    return PairCompat(
        bpm_from=bpm_from, bpm_to=bpm_to, bpm_percent=percento, halftime=piegato,
        key_from=key_from, key_to=key_to, key_relation=relation,
        score=score, missing=missing,
    )
