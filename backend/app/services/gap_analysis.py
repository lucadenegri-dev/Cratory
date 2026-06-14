"""Analisi DETERMINISTICA dei "buchi" di una playlist rispetto a un DJ set.

Vedi nuovo_progetto.md sez. 6. Nessuna AI: solo statistiche sulle feature delle
tracce. L'AI (a valle) potra' trasformare questi findings in linguaggio naturale e
in suggerimenti di crate digging, ma i fatti vengono da qui.

Ogni finding: {gap_type, severity (info|warning), description, suggestion}.
"""

from collections import Counter
from dataclasses import asdict, dataclass

from app.models import Track

# Soglie BPM per i bucket (electronic-oriented, ma generiche).
_BPM_BUCKET = 2.0  # ampiezza istogramma BPM
_OPENER_BPM_MAX = 120.0
_PEAK_BPM_MIN = 126.0
_MIN_OPENERS = 2
_MIN_PEAK = 3
_UNIFORM_ENERGY_STD = 8.0   # sotto: energia troppo piatta
_VOCAL_RUN_THRESHOLD = 70   # vocalness >= soglia -> traccia "vocal"
_MAX_GENRE_SHARE = 0.6      # un genere oltre il 60% -> poco vario; molti generi -> dispersiva
_MAX_DISTINCT_GENRES = 8


@dataclass
class Gap:
    gap_type: str
    severity: str
    description: str
    suggestion: str


def _bpms(tracks: list[Track]) -> list[float]:
    return sorted(t.bpm for t in tracks if t.bpm)


def _energies(tracks: list[Track]) -> list[int]:
    return [t.energy for t in tracks if t.energy is not None]


def _std(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    return (sum((v - mean) ** 2 for v in values) / len(values)) ** 0.5


def _check_openers(tracks: list[Track]) -> Gap | None:
    openers = [t for t in tracks if t.bpm and t.bpm <= _OPENER_BPM_MAX]
    if len(openers) < _MIN_OPENERS:
        return Gap(
            "missing_openers", "warning",
            f"Solo {len(openers)} tracce sotto {_OPENER_BPM_MAX:.0f} BPM adatte all'apertura.",
            "Aggiungi qualche brano piu' lento/atmosferico per costruire un'intro.",
        )
    return None


def _check_peak(tracks: list[Track]) -> Gap | None:
    peak = [t for t in tracks if t.bpm and t.bpm >= _PEAK_BPM_MIN]
    if len(peak) < _MIN_PEAK:
        return Gap(
            "few_peak_tracks", "warning",
            f"Solo {len(peak)} tracce sopra {_PEAK_BPM_MIN:.0f} BPM adatte al peak.",
            "Servono piu' brani energici per sostenere il momento clou del set.",
        )
    return None


def _check_bpm_bridges(tracks: list[Track]) -> Gap | None:
    bpms = _bpms(tracks)
    if len(bpms) < 4:
        return None
    # Cerca il buco piu' ampio tra BPM consecutivi nell'arco coperto.
    biggest = (0.0, 0.0, 0.0)  # (gap, lo, hi)
    for a, b in zip(bpms, bpms[1:]):
        if b - a > biggest[0]:
            biggest = (b - a, a, b)
    gap, lo, hi = biggest
    if gap >= 6.0:
        return Gap(
            "missing_bpm_bridge", "warning",
            f"Salto di {gap:.0f} BPM tra {lo:.0f} e {hi:.0f}: poche tracce ponte in mezzo.",
            f"Cerca brani tra {lo:.0f} e {hi:.0f} BPM per rendere piu' naturale la crescita.",
        )
    return None


def _check_energy_uniform(tracks: list[Track]) -> Gap | None:
    energies = _energies(tracks)
    if len(energies) >= 5 and _std([float(e) for e in energies]) < _UNIFORM_ENERGY_STD:
        return Gap(
            "uniform_energy", "info",
            "Energia molto piatta lungo la playlist: poca dinamica per un set.",
            "Aggiungi brani piu' calmi e altri piu' intensi per creare una progressione.",
        )
    return None


def _check_harmonic(tracks: list[Track]) -> Gap | None:
    with_key = [t for t in tracks if t.camelot_key]
    if tracks and len(with_key) < max(3, len(tracks) // 2):
        return Gap(
            "missing_harmonic_data", "warning",
            f"Solo {len(with_key)}/{len(tracks)} tracce hanno una tonalita' (Camelot).",
            "Arricchisci le tracce (key/BPM) per abilitare il mixing armonico.",
        )
    return None


def _check_vocal_runs(tracks: list[Track]) -> Gap | None:
    run = best = 0
    for t in tracks:
        if t.vocalness is not None and t.vocalness >= _VOCAL_RUN_THRESHOLD:
            run += 1
            best = max(best, run)
        else:
            run = 0
    if best >= 4:
        return Gap(
            "too_many_vocals", "info",
            f"Fino a {best} tracce vocal consecutive: rischio di affaticare l'ascolto.",
            "Intervalla con brani piu' strumentali/groove.",
        )
    return None


def _check_genre_spread(tracks: list[Track]) -> Gap | None:
    genres = Counter(t.genre.split(",")[0].strip().lower() for t in tracks if t.genre)
    total = sum(genres.values())
    if total < 5:
        return None
    top_share = genres.most_common(1)[0][1] / total
    if top_share > _MAX_GENRE_SHARE:
        return Gap(
            "low_genre_variety", "info",
            f"Un solo genere domina (~{top_share * 100:.0f}% delle tracce).",
            "Per un set piu' interessante valuta qualche brano di generi affini.",
        )
    if len(genres) > _MAX_DISTINCT_GENRES:
        return Gap(
            "scattered_genres", "info",
            f"Playlist molto dispersiva: {len(genres)} generi diversi.",
            "Restringi attorno a 2-3 generi coerenti per un set piu' fluido.",
        )
    return None


_CHECKS = (
    _check_openers,
    _check_peak,
    _check_bpm_bridges,
    _check_energy_uniform,
    _check_harmonic,
    _check_vocal_runs,
    _check_genre_spread,
)


def analyze_gaps(tracks: list[Track]) -> list[dict]:
    """Ritorna la lista dei findings (dizionari pronti per la response)."""
    if not tracks:
        return []
    findings = [check(tracks) for check in _CHECKS]
    return [asdict(g) for g in findings if g is not None]
