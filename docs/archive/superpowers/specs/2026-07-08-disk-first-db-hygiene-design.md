# Disk-first: allineamento DB ↔ disco e pulizia residui

Data: 2026-07-08
Stato: design approvato (in attesa di review dello spec)

## Contesto

Cratory è passata al paradigma **disk-first**: la libreria è il disco, i metadati
testuali arrivano dal disco (tag scritti da DjOrganizer), BPM/tonalità da Rekordbox,
l'identità/editoriale streaming da Spotify. La vecchia catena di enrichment è **già
stata rimossa dal codice** (colonne droppate in [`db.py`](../../../backend/app/db.py)
via `_migrate_drop_enrichment_cols`), ma nel DB possono restare:

1. **Lead orfani** — tracce senza file su disco che non appartengono più a nessuna
   playlist e non servono a nulla.
2. **Valori residui legacy** — campi che nessun flusso attuale scrive più (scritti
   dalla vecchia catena prima della sua rimozione).
3. **Disallineamento disco↔DB sulle possedute** — l'indicizzazione è backfill-only
   (riempie solo i campi vuoti), quindi valori stantii possono sopravvivere anche
   quando il file su disco dice altro.

Inoltre il reader del disco legge un set minimo di tag: `label` e la **cover
embedded** non vengono lette, quindi le possedute dipendono da Spotify anche quando
il dato è sul file.

## Mappa provenienza campi (stato attuale, verificata nel codice)

| Campo | Chi lo scrive oggi |
|---|---|
| title, artist, album, year, duration, isrc | Spotify import + disco (indicizzazione) |
| album_art_url (cover) | Spotify import (e discovery-add) — **mai dal disco** |
| genre | **solo** disco (tag file) o modifica manuale |
| label | Spotify Labels backfill ([`labels.py:184`](../../../backend/app/services/labels.py)) — **mai dal disco** |
| bpm, camelot_key | **solo** Rekordbox (su possedute) o modifica manuale |
| energy | derivato da bpm+genere ([`services/energy.py`](../../../backend/app/services/energy.py)) |
| release_date | **nessuno** lo scrive, mai |

Conseguenza: su un **lead puro** (streaming, senza file, senza match Rekordbox,
senza edit manuale) i campi `genre, bpm, camelot_key, energy, release_date` non
hanno alcuno scrittore attuale → ogni valore presente è **residuo legacy**.

## Obiettivi

1. Leggere `label` e la **cover** dal disco quando disponibili (rispettando la
   precedenza Spotify sulla cover).
2. Ripulire il DB dai lead orfani e dai residui legacy, e riallineare le possedute
   al disco, con una passata una-tantum **reversibile nella decisione** (dry-run).
3. Rendere la cancellazione di una playlist automaticamente pulita (feature runtime).

## Non-obiettivi

- Nessun tracciamento di provenienza per-campo (non esiste; non lo introduciamo).
- Nessuna modifica ai file su disco: Cratory **legge** i tag, non li scrive mai.
- L'indicizzazione resta **backfill-only** (l'allineamento disco-autorevole è la
  passata una-tantum, non un nuovo comportamento permanente).
- Nessun cestino/undo: le cancellazioni sono definitive (i lead sono re-importabili).

---

## Pezzo 1 — Reader disco: aggiungere `label`

[`read_tags`](../../../backend/app/integrations/local_files.py) estende l'output con
`label`, letto da:
- **ID3** (mp3/wav): `TPUB` (publisher).
- **Vorbis** (flac/ogg/opus): `LABEL`, in fallback `ORGANIZATION`/`PUBLISHER`.
- **MP4** (m4a): best-effort freeform `----:com.apple.iTunes:LABEL`; se assente,
  si lascia vuoto (come già si fa per l'ISRC MP4).

`library_index._fill_identity` aggiunge il backfill-only di `label` (riempie solo se
vuoto). L'allineamento autorevole avviene nella passata una-tantum (Pezzo 3c).

## Pezzo 2 — Cover embedded on-demand

Nuovo endpoint **`GET /api/tracks/{id}/cover`**:
- 404 se la traccia non esiste, non è posseduta (`has_local_file` falso), il file
  non esiste, o non c'è artwork embedded.
- Estrae la prima immagine via mutagen: ID3 `APIC`, FLAC `.pictures`, MP4 `covr`,
  Vorbis `metadata_block_picture`.
- Risponde con i byte e il `media_type` corretto (`image/jpeg` o `image/png`) e un
  header di cache breve. Nessuna immagine viene salvata nel DB.

**Frontend**: helper condiviso `trackCoverSrc(track)` in `lib/`:
```ts
album_art_url (Spotify, se presente)  →  else  →  has_local_file ? `/api/tracks/${id}/cover` : null
```
Applicato ai punti dove si rende la cover di una traccia, con `onError` che nasconde
l'immagine se l'endpoint dà 404. Rispetta la regola "Spotify se c'è, sennò disco".

## Pezzo 3 — Script di pulizia una-tantum

`backend/app/tools/cleanup_disk_first.py`, eseguibile a mano. **Dry-run di default**
(stampa un report senza scrivere); `--apply` per applicare in transazione.

Ordine ed effetti:

### 3a — Lead orfani (eliminazione)
Elimina le tracce che soddisfano **tutte**:
- non su disco (`has_local_file` non `True`),
- non in nessuna playlist (`playlist_tracks`),
- non in nessun set salvato (`setlist_tracks`).

Riusa l'helper condiviso con il Pezzo 4 (`delete_orphan_leads`).

### 3b — Residui legacy sui lead
Sui lead sopravvissuti (non su disco), azzera i campi senza writer attuale:
`genre, bpm, camelot_key, energy, release_date` → `NULL`.
Si **tengono**: `title, artist, album, year, duration_seconds, album_art_url, isrc,
label` (hanno un writer attuale, incluso Spotify per label).

### 3c — Possedute: disco autorevole
Per ogni traccia posseduta (`has_local_file = True`) con file esistente, rilegge i
tag e **sovrascrive** i campi disco-derivabili con i valori del file:
- `title, artist`: tag del file, **altrimenti** parse dal nome file (stesso fallback
  dell'indicizzazione, `parse_line(path.stem)`) — non si lascia mai una posseduta
  senza artist/title se il nome file è interpretabile.
- `album, genre, year, isrc, duration_seconds, label`: tag del file, svuotati se il
  file non li ha.

Poi **ricalcola** `energy` (da bpm+genere aggiornato).
Si **tengono**: `bpm, camelot_key` (Rekordbox), `album_art_url` (Spotify; la cover
da disco è servita on-demand dal Pezzo 2, non scritta in DB).

Il report dry-run mostra, per ciascuna operazione, i conteggi e un campione delle
modifiche (per 3c: quali campi cambierebbero su quante tracce).

## Pezzo 4 — Cancellazione lead orfani a eliminazione playlist (runtime)

`delete_playlist(db, playlist_id)` in
[`repositories.py`](../../../backend/app/repositories.py) cambia ritorno da `bool` a
`int | None`:
- `None` → playlist inesistente (router → 404);
- `int` → numero di lead orfani cancellati (0+).

Algoritmo: raccoglie gli `id` delle tracce della playlist, cancella le membership di
questa playlist e la riga `Playlist`, poi invoca l'helper condiviso
`delete_orphan_leads(db, candidate_ids)` che esegue un'unica DELETE:
```sql
DELETE FROM tracks WHERE id IN (:candidate_ids)
  AND has_local_file IS NOT 1
  AND id NOT IN (SELECT track_id FROM playlist_tracks)
  AND id NOT IN (SELECT track_id FROM setlist_tracks)
```
e ritorna il numero di righe cancellate.

**API**: `DELETE /api/playlists/{playlist_id}` passa da `204` a `200` con corpo
`{ "deleted_tracks": N }` (schema `PlaylistDeleteResult`). Il frontend legge il
conteggio e mostra es. *"Playlist eliminata · N tracce orfane rimosse"*.

## Helper condiviso

`delete_orphan_leads(db, candidate_ids: Iterable[int]) -> int` in `repositories.py`:
esegue la DELETE sopra sui soli `candidate_ids` e ritorna il conteggio. Usato sia
dal Pezzo 4 (candidate = tracce della playlist eliminata) sia dal Pezzo 3a
(candidate = tutti i lead non su disco).

## Test (pytest)

- **Helper orfani**: (a) lead solo in questa playlist → cancellato; (b) lead anche
  in un'altra playlist → resta; (c) traccia su disco → resta; (d) lead in un set
  salvato → resta; (e) conteggio corretto.
- **Endpoint DELETE playlist**: ritorna `{deleted_tracks}` corretto; 404 su id
  inesistente.
- **read_tags label**: legge `TPUB`/`LABEL`; assenza → `label` vuoto.
- **Cover endpoint**: file con artwork → 200 + bytes + mime; senza artwork o non
  posseduta → 404.
- **Cleanup 3b**: lead con genre/bpm/key/energy/release_date → azzerati; label e
  identità Spotify → intatti.
- **Cleanup 3c**: posseduta con tag su disco diversi dal DB → DB allineato al file;
  campo assente nel file → svuotato; bpm/key/cover → intatti; energy ricalcolato.
- **Dry-run**: nessuna scrittura, report coerente coi conteggi che poi `--apply`
  produce.

## Rischi

- **Distruttivo**: 3a cancella righe `Track`; 3b/3c azzerano/sovrascrivono campi.
  Mitigato dal dry-run e dal fatto che si toccano solo lead senza file o valori
  disco-derivabili delle possedute; nessun file su disco viene mai modificato.
- **Perdita edit manuali**: 3c sovrascrive da disco anche eventuali correzioni
  manuali fatte nella UI sulle possedute. Accettato; il dry-run le evidenzia.
- **BPM/key legacy sulle possedute non distinguibili**: un valore bpm/key stantio su
  una posseduta che non è mai passata da Rekordbox non è distinguibile da uno
  Rekordbox e viene mantenuto. Limite noto; si risolve re-importando Rekordbox.

## Ordine di implementazione

1. Pezzo 1 (read_tags label) + Pezzo 4 (helper + delete_playlist + API) — base
   condivisa e feature runtime.
2. Pezzo 3 (script una-tantum) — dipende dall'helper e da read_tags.
3. Pezzo 2 (cover endpoint + frontend) — indipendente, può andare in parallelo.
