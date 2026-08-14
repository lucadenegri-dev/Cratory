"""Ex pulizia una-tantum disk-first: modulo svuotato.

Ospitava quattro funzioni (`dedupe_by_audio_hash`, `purge_lead_residue`,
`realign_owned_from_disk`, `align_owned_genre_from_file`), tutte invocate solo
dagli script CLI one-shot di `app/tools/` (`cleanup_disk_first.py`,
`align_genre_from_file.py`). Quegli script sono stati rimossi durante la
revisione codice/documentazione del 2026-08-13 (Task 5b); le quattro funzioni
sono rimaste senza chiamanti di produzione e sono state rimosse a loro volta
(Task 8b, decisione utente al checkpoint di Fase 2). La logica che
orchestravano resta viva altrove e testata separatamente:
`app.repositories.merge_tracks` (`tests/test_track_merge.py`,
`tests/test_rating_top_playlist.py`), `app.services.genre_align.align_track_genre`
(`tests/test_library_index.py` e i chiamanti in Organize) e
`app.services.energy.apply_estimated_energy` (`tests/test_audio_energy.py`).

Il file non ha piu' contenuto operativo: se resta cosi' vuoto attraverso una
prossima passata di pulizia, valutare se cancellarlo del tutto.
"""
