"""Utility per la notazione Camelot (es. '7A', '12B').

Rekordbox esporta Tonality gia' in Camelot nel dataset reale.
"""

import re

_CAMELOT_RE = re.compile(r"^\s*(\d{1,2})\s*([ABab])\s*$")


def parse_camelot(value: str | None) -> tuple[int, str] | None:
    """Ritorna (numero 1-12, lettera 'A'|'B') oppure None se non valido."""
    if not value:
        return None
    m = _CAMELOT_RE.match(value)
    if not m:
        return None
    number = int(m.group(1))
    if not 1 <= number <= 12:
        return None
    return number, m.group(2).upper()


# Mappa classe di altezza (0=C ... 11=B) -> Camelot, per maggiore e minore.
# Maggiore = lettera B della ruota, minore = lettera A (relativa).
_MAJOR_CAMELOT = {0: "8B", 1: "3B", 2: "10B", 3: "5B", 4: "12B", 5: "7B",
                  6: "2B", 7: "9B", 8: "4B", 9: "11B", 10: "6B", 11: "1B"}
_MINOR_CAMELOT = {0: "5A", 1: "12A", 2: "7A", 3: "2A", 4: "9A", 5: "4A",
                  6: "11A", 7: "6A", 8: "1A", 9: "8A", 10: "3A", 11: "10A"}
_NOTE_PC = {
    "C": 0, "B#": 0, "C#": 1, "DB": 1, "D": 2, "D#": 3, "EB": 3, "E": 4, "FB": 4,
    "E#": 5, "F": 5, "F#": 6, "GB": 6, "G": 7, "G#": 8, "AB": 8, "A": 9, "A#": 10,
    "BB": 10, "B": 11, "CB": 11,
}


def pitch_to_camelot(value: str | None) -> str | None:
    """Converte una key musicale (es. 'Am', 'C#m', 'F# minor', 'Db') in Camelot.

    Una key senza modo esplicito viene letta come MAGGIORE (convenzione comune).
    Ritorna None se non interpretabile (mai inventare la tonalita').
    """
    if not value:
        return None
    s = value.strip().replace("♯", "#").replace("♭", "b").replace("−", "-")
    s = s.replace("-sharp", "#").replace("-flat", "b")
    if not s or s[0] not in "ABCDEFGabcdefg":
        return None
    note = s[0].upper()
    rest = s[1:]
    if rest[:1] in ("#", "b"):  # accidentale (es. C#, Db); 'm' resta nel modo
        note += rest[:1]
        rest = rest[1:]
    pc = _NOTE_PC.get(note.upper())
    if pc is None:
        return None
    mode = rest.strip().lower()
    is_minor = mode in ("m", "min", "minor", "-") or mode.startswith("min")
    table = _MINOR_CAMELOT if is_minor else _MAJOR_CAMELOT
    return table[pc]


# Punteggio graduato (0-100) per distanza sulla ruota Camelot. A differenza dei
# tre livelli same/compatible/weak, distingue un +2 "energy boost" (8A->10A,
# mixabile con intento) da un tritono (8A->2A, stonatura). num_dist = passi minimi
# sulla ruota (0-6); la lettera uguale/diversa distingue relativa e diagonale.
_SAME_LETTER_SCORE = {0: 100, 1: 85, 2: 65, 3: 35, 4: 25, 5: 18, 6: 10}
_DIFF_LETTER_SCORE = {0: 90, 1: 60, 2: 45, 3: 30, 4: 22, 5: 15, 6: 10}


def camelot_score(key_a: str | None, key_b: str | None) -> int:
    """Compatibilità armonica graduata (0-100). 50 (neutro) se una key manca."""
    a, b = parse_camelot(key_a), parse_camelot(key_b)
    if a is None or b is None:
        return 50
    num_a, let_a = a
    num_b, let_b = b
    num_dist = min((num_a - num_b) % 12, (num_b - num_a) % 12)
    table = _SAME_LETTER_SCORE if let_a == let_b else _DIFF_LETTER_SCORE
    return table[num_dist]


def camelot_compatibility(key_a: str | None, key_b: str | None) -> tuple[str, str]:
    """Classifica la compatibilita' armonica tra due key Camelot.

    Ritorna (livello, descrizione). Livelli: 'same', 'compatible', 'weak', 'unknown'.
    """
    a, b = parse_camelot(key_a), parse_camelot(key_b)
    if a is None or b is None:
        return "unknown", "tonalita' mancante o non in formato Camelot"
    if a == b:
        return "same", f"stessa key ({key_a})"
    num_a, let_a = a
    num_b, let_b = b
    if num_a == num_b:
        return "compatible", f"stesso numero, lettera diversa ({key_a} -> {key_b})"
    diff = min((num_a - num_b) % 12, (num_b - num_a) % 12)
    if diff == 1 and let_a == let_b:
        return "compatible", f"key adiacente sulla ruota Camelot ({key_a} -> {key_b})"
    return "weak", f"key poco compatibili ({key_a} -> {key_b})"
