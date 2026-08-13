"""Regola unica di allineamento `Track.genre` al tag genere del file.

Perimetro deliberatamente stretto: SOLO `genre`. Non tocca `title`/`artist`
(identita' della traccia, de-duplicazione e matching streaming) ne'
`album`/`label`/`year` (fuori dallo scope richiesto).

Una sola funzione, usata da tre chiamanti — nessuno dei quali la duplica:
- il backfill retroattivo (`app.services.db_hygiene.align_owned_genre_from_file`);
- la modifica manuale dei tag in Organize (`app.organize.services.manual_edit`);
- la scansione (`app.organize.services.scanner`), quando rilegge un tag
  cambiato fuori dall'app su un file gia' agganciato a una traccia.

Il `COALESCE` di lettura (`app.repositories._EFFECTIVE_TAGS`) resta invariato:
`Track.genre` e' uno specchio di comodo per il dato in tabella, non la fonte
di verita' delle letture. Un tag file vuoto o assente non tocca mai la
traccia (il valore streaming resta l'unico che c'e', ed e' cio' che il
COALESCE mostra).
"""
from __future__ import annotations

from app.models import Track
from app.services.energy import apply_estimated_energy
from app.services.genre_norm import normalize_genre


def align_track_genre(track: Track, file_genre: str | None, *, apply: bool) -> str | None:
    """Se il tag genere del file e' non vuoto e diverge (trim + case-insensitive,
    dopo la stessa normalizzazione leggera usata altrove per i generi da tag)
    da `track.genre`, ritorna il nuovo genere normalizzato — che verrebbe
    scritto (`apply=False`, dry-run) o e' stato scritto (`apply=True`).
    Altrimenti ritorna None e non tocca nulla.

    Con `apply=True` scrive `track.genre` e ricalcola l'energia derivata
    (`apply_estimated_energy`: `energy` dipende da bpm+genere), esattamente
    come gia' fa `db_hygiene.realign_owned_from_disk` per il suo perimetro piu'
    ampio. Con `apply=False` (dry-run) non scrive nulla: il chiamante puo'
    comunque leggere qui il valore "dopo" per un campione leggibile.
    """
    normalized = normalize_genre(file_genre)
    if not normalized:
        return None
    if normalized.casefold() == (track.genre or "").strip().casefold():
        return None
    if apply:
        track.genre = normalized
        apply_estimated_energy(track)
    return normalized
