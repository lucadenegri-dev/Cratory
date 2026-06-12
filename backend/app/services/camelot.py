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
