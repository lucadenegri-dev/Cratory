"""Regola unica di allineamento `Track.genre` al tag genere del file.

Perimetro deliberatamente stretto: SOLO `genre`. Non tocca `title`/`artist`
(identita' della traccia, de-duplicazione e matching streaming) ne'
`album`/`label`/`year` (fuori dallo scope richiesto).

Una sola funzione, usata da tutti i punti in cui il tag di un file puo'
cambiare o un aggancio puo' nascere — nessuno dei quali la duplica:
- il backfill retroattivo (`app.services.db_hygiene.align_owned_genre_from_file`);
- la modifica manuale dei tag in Organize (`app.organize.services.manual_edit`);
- l'Apply dei piani di Organize (`app.organize.services.apply`, operazioni RETAG);
- la scansione (`app.organize.services.scanner`), quando rilegge un tag
  cambiato fuori dall'app su un file gia' agganciato a una traccia;
- l'indicizzazione libreria (`app.services.library_index.collega_tracce`) e
  l'acquisizione (`app.services.acquisition.attach_local_file`: Soulseek,
  download SoundCloud, collegamento manuale), cioe' i due momenti in cui una
  traccia acquisisce un file. Servono entrambi perche' li' la riga `AudioFile`
  viene INSERITA, non aggiornata: la guardia dello scan sul tag cambiato non
  scatta mai per quel file, e senza questa chiamata un lead che arriva con un
  genere streaming se lo terrebbe per sempre.

Il `COALESCE` di lettura (`app.repositories._EFFECTIVE_TAGS`) resta invariato:
`Track.genre` e' uno specchio di comodo per il dato in tabella, non la fonte
di verita' delle letture. Un tag file vuoto o assente non tocca mai la
traccia (il valore streaming resta l'unico che c'e', ed e' cio' che il
COALESCE mostra).

Lo specchio non converge mai byte-per-byte col tag: il confronto (sotto) e'
`normalize_genre(...).casefold()` contro `track.genre`, quindi trattini,
underscore e maiuscole/minuscole si appianano ("Tech-House" sul file resta
"Tech House" in `tracks.genre`). Innocuo per la lettura (il COALESCE mostra
comunque il tag alla lettera quando c'e' un file), ma non leggere
`tracks.genre` aspettandosi il testo esatto del tag.
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
