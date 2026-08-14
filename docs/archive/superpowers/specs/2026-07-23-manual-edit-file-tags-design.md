# Modifica manuale dei metadati in FILES

**Data:** 2026-07-23
**Stato:** design approvato, in attesa di piano

## Obiettivo

Dare all'utente la possibilità di **modificare a mano i metadati testuali di un
file** direttamente dalla schermata FILES: aprire un pannello sulla riga,
correggere artist/title/album/… e salvare, con la scrittura sul file su disco che
avviene **subito** ed è **reversibile** (compare in History, si annulla come una
qualsiasi run).

Oggi non esiste alcun percorso per farlo. Ogni scrittura di tag passa da un'unica
strada — una `Issue.suggested_fix` marcata `accepted` → PLAN → Apply — e un file
"pulito" (senza issue aperte su un campo) **non è modificabile in nessun modo**.
La modifica manuale è esattamente questa capacità mancante: toccare metadati già
validi, non solo proporre correzioni a metadati sbagliati.

## Stato attuale

- **Unico percorso di scrittura tag:** `Issue.suggested_fix_json` (`action:
  "retag"`, `to: …`) marcata `accepted` → `planner.build_plan` → `apply_plan`
  scrive su disco con `tagio.write_tags` e registra un `UndoJournal` `RETAG`.
- `routers/issues.py:102` `fix_issue` — il "fix manuale" esistente: imposta
  `suggested_fix = {field, action:"retag", to: valore, source:"manual"}` (di
  fatto; qui il marker `source` non è scritto ma i marker provider sono
  preservati) e `status="accepted"`. **Non scrive su disco**: attende l'Apply.
- `integrations/tagio.py:117` `write_tags(path, changes)` — scrive i soli campi
  passati; **valore vuoto ⇒ elimina la chiave** dal tag. Gestisce mp3/flac/m4a
  (easy) e wav/aiff (frame ID3 grezzi).
- `services/apply.py:128` — pattern RETAG di riferimento: legge i valori
  precedenti dal disco, **journal prima** (`_journal("RETAG", …, prior_tags=…)`),
  poi `write_tags`, poi allinea la riga `AudioFile` nel DB.
- `services/undo.py:23` — l'undo `RETAG` riscrive `prior_tags_json` sul file se
  esiste. Già oggi inverte perfettamente una scrittura di tag.
- `services/planner.py:110` — un RETAG viene emesso **solo** per i campi il cui
  valore differisce davvero da quello nel DB (`_norm(getattr(f, field)) !=
  _norm(eff[field])`). È la garanzia che, se il DB è allineato al disco, nessun
  Apply successivo può riscrivere sopra la modifica manuale.
- `routers/library.py:87` `list_files` — read-only; costruisce ogni `FileRow` con
  scalar-subquery per `issue_count` / `worst_rank` / `in_dup` / `cover_source`.
- `frontend/components/files-table.tsx` — righe con `hover:bg-surface` (già
  predisposte a essere interattive), mostrano solo path/artist/title/fmt/kbps/dur.
- `frontend/app/files/page.tsx` — carica già i `LibraryFacets`
  (genre/artist/album/label/ext/year) per i filtri: sono riusabili come sorgente
  di autocomplete dell'editor senza query nuove.
- Campi editabili (= `planner._EFFECTIVE_FIELDS` = `issues._RETAGGABLE`):
  `artist, title, album, album_artist, genre, year, label, track_no, comment`.

## Decisioni prese in brainstorming

| Domanda | Scelta |
|---|---|
| Quando la modifica scrive sul disco | **Subito**, non via PLAN/Apply |
| Reversibilità | **Sì**: voce `UndoJournal` `RETAG` → compare in History, annullabile |
| Superficie UI | **Pannello per riga** (non edit inline), con tutti i 9 campi |
| Granularità in History | **Una run per salvataggio-file** (un journal con tutti i campi cambiati) |
| Issue aperte sul campo modificato | Chiuse come `accepted` con `source:"manual"` (specchio di `fix_issue`) |
| Fuori scope | Rating (stelline) e cover: hanno già meccanismi dedicati |

## Feature 1 — Backend: servizio, endpoint, undo

### 1.1 `services/manual_edit.py` (nuovo)

```
edit_tags(db, file: AudioFile, changes: dict[str, str | None]) -> AudioFile
```

Orchestrazione, ricalcata sul RETAG di `apply.py`:

1. **Validazione / coercizione** dei `changes`:
   - solo chiavi nella whitelist `_RETAGGABLE`; una chiave estranea ⇒ errore
     `field_not_editable` (400);
   - stringhe: `strip()`; **stringa vuota o `None` ⇒ `None`** (pulisce il tag);
   - `year`: intero a 4 cifre plausibile (o vuoto); non parsabile ⇒
     `value_invalid` (400);
   - `track_no`: intero positivo (o vuoto); non parsabile ⇒ `value_invalid`.
   - Si tengono solo i campi il cui valore normalizzato **differisce** da quello
     già nel DB: se nulla cambia, no-op (nessuna run, nessuna scrittura).
2. **Guardie di stato**: `file.status == "present"` e `os.path.exists(file.path)`,
   altrimenti `file_not_writable` (409). Il file non deve avere `scan_error`.
3. **Cattura dei valori precedenti** dal **disco** (`tagio.read_tags`), sui soli
   campi che cambiano — identico ad `apply.py:131`, così l'undo ripristina il
   vero stato pre-modifica anche se DB e disco divergevano.
4. **Journal-first**: crea un `Plan` sintetico e la voce di journal *prima* di
   toccare il file:
   - `Plan(status="applied", rules_json={"kind":"manual_edit", "file_id": file.id,
     "fields": [campi cambiati]})`;
   - `UndoJournal(run_id=plan.id, op_seq=0, kind="RETAG", file_id=file.id,
     from_path=file.path, prior_tags_json=prior)` con `prior` = dict di tutti i
     campi cambiati → un'unica voce li annulla insieme.
   - commit.
5. **Scrittura su disco**: `tagio.write_tags(file.path, changes_effettivi)`.
6. **Allineamento DB**: `setattr(file, campo, valore)` per ogni campo cambiato
   (DB = disco ⇒ il planner non rigenererà mai un RETAG per questi campi).
7. **Riconciliazione issue**: per ogni campo modificato, ogni `Issue` con
   `field == campo` e `status == "open"` viene chiusa come nel `fix_issue`
   esistente: `status="accepted"`, `suggested_fix = {field, action:"retag",
   to: valore_manuale, source:"manual"}` (se il valore è stato svuotato →
   `action:"clear"`). Poiché il DB ora coincide, `planner.py:110` non produce
   alcun RETAG: idempotente.
8. commit finale.

Errore di scrittura (`TagWriteError`): si propaga come 500 controllato; la voce
di journal resta ma è innocua (undo `RETAG` su prior == corrente è un no-op).

### 1.2 `routers/files.py` (nuovo)

`POST /api/files/{file_id}/tags`, prefix `/api`. Body = `FileTagsUpdate`
(`schemas.py`): un oggetto con i 9 campi opzionali (`str | None`).

- 404 `file_not_found` se il file non esiste;
- delega a `manual_edit.edit_tags`;
- ritorna il **`FileRow` aggiornato** (con `issue_count` / `worst_severity` /
  `cover_source` ricalcolati), così la tabella riflette subito le issue chiuse.

Per non duplicare l'assemblaggio del `FileRow`, si estrae da `library.list_files`
un helper `_build_file_row(db, file) -> FileRow` (le quattro scalar-subquery per
un singolo file) riusato sia dalla lista sia da questo endpoint.

La logica di business resta in `manual_edit.py`; il router è sottile (convenzione
del codebase: router = forma HTTP, service = logica).

### 1.3 History: distinguere la run manuale

`HistoryItem` (`schemas.py`) prende un campo opzionale `kind: str | None`.
`history.list_history` lo popola da `plan.rules_json.get("kind")` (`"manual_edit"`
per le nostre run, assente/`None` per gli Apply normali). Il frontend History
mostra "Manual edit" al posto/accanto al conteggio ops. L'undo di una run
manuale usa lo **stesso** endpoint `POST /api/history/{id}/undo` senza modifiche:
è un `Plan` con `status="applied"` come gli altri.

## Feature 2 — Frontend: pannello di modifica

### 2.1 `components/file-edit-panel.tsx` (nuovo)

Pannello (drawer laterale o modale, coerente col design system editoriale/mono)
aperto dalla riga FILES. Riceve `row: FileRow`, `facets: LibraryFacets | null`,
`onClose`, `onSaved(updated: FileRow)`.

- Un input per ciascuno dei 9 campi, pre-riempito col valore corrente del file.
  Il `FileRow` oggi non porta tutti i campi (mancano album_artist, track_no,
  comment): il pannello richiede lo stato completo del file. **Scelta:** estendere
  `FileRow` con i campi mancanti (`album_artist`, `track_no`, `comment`) — sono
  già letti dallo scan e a costo zero nella query — così la riga porta tutto e il
  pannello non fa una GET aggiuntiva.
- **Autocomplete (datalist)** su `genre / artist / album / label` riusando
  `LibraryFacets` già caricati in `FilesPage` (nessuna query nuova).
- Validazione inline per `year` / `track_no` (numerici); il resto libero.
- Salva → invia **solo i campi cambiati** a `updateFileTags`. Vuoto è un valore
  valido (pulisce il tag). Bottone disabilitato se nulla è cambiato.
- Errore backend → `Alert` nel pannello (riusa `translateApiError`).

### 2.2 `files-table.tsx`

La riga (già `hover:bg-surface`) diventa cliccabile e chiama `onEdit(row)` passato
dal parent. Il click sulla cella cover/indicatori non deve avere comportamenti
propri in conflitto (oggi non ne hanno). Un piccolo affordance visivo (cursor
pointer) segnala l'interattività.

### 2.3 `app/files/page.tsx`

Tiene lo stato `editing: FileRow | null`. Passa `onEdit={setEditing}` alla
tabella e `facets` al pannello. `onSaved(updated)` **sostituisce la riga
in-place** nello `state` (niente refetch di 500 righe) e chiude il pannello.

### 2.4 `lib/api.ts`

```
updateFileTags(fileId: number, changes: Partial<EditableTags>): Promise<FileRow>
```
`POST /api/files/{id}/tags`. `FileRow` esteso con `album_artist`, `track_no`,
`comment`.

### 2.5 i18n

Nuove chiavi prima in `lib/i18n/en.ts` (fonte di verità), poi tradotte in
`it.ts`: label dei campi, titolo pannello, Salva/Annulla, messaggi di
validazione, "Manual edit" per History.

## Errori e degrado

- File sparito dal disco o `status != "present"` tra il caricamento della lista e
  il salvataggio → 409 `file_not_writable`, `Alert` nel pannello, nessuna
  scrittura.
- `TagWriteError` (formato non scrivibile, permessi) → 500 controllato; il DB non
  viene allineato (resta coerente col disco non modificato); la voce di journal
  eventualmente creata è innocua.
- Campo fuori whitelist o valore numerico non valido → 400, messaggio tradotto.

## Interazione col resto della pipeline

- **Precedenza** (`manual > cleaned tag > provider > ai`): rispettata. La
  modifica manuale vince e chiude le issue sul campo marcandole `source:"manual"`.
- **Nessun re-rilevamento issue**: la modifica manuale chiude le issue esistenti
  sui campi toccati ma non ne crea di nuove (es. svuotare l'artista non genera
  subito `missing_required_tag`, né un genere sporco genera `dirty_genre`). Una
  ri-scansione riconcilia. Limite noto e documentato.
- **Undo**: un `undo` della run manuale ripristina i tag precedenti e lascia le
  issue nello stato `accepted` (non le riapre). Coerente con l'undo degli Apply,
  che pure non riapre le issue. Accettato.

## Test (pytest, venv 3.11)

- `edit_tags` scrive i campi su disco (verifica via `read_tags`) e allinea il DB.
- Undo della run manuale ripristina i valori precedenti sul file.
- La run manuale compare in History con `kind == "manual_edit"`.
- Un'issue `open` sul campo modificato viene chiusa `accepted` con
  `source:"manual"`; una issue su un **altro** campo resta invariata.
- Dopo l'edit, `build_plan` non rigenera alcun RETAG per i campi toccati
  (idempotenza / garanzia planner.py:110).
- Validazione: `year`/`track_no` non numerici → 400; campo fuori whitelist → 400;
  stringa vuota → tag rimosso (chiave assente in `read_tags`).
- Guardie: file `missing` o assente su disco → 409.
- No-op: `changes` uguali ai valori correnti → nessuna run creata, nessuna
  scrittura.
- Endpoint: ritorna un `FileRow` con `issue_count` aggiornato dopo la chiusura
  dell'issue.

## Fuori scope (YAGNI)

- Modifica di rating (stelline) e cover art dall'editor: meccanismi già dedicati
  altrove.
- Edit inline nelle celle della tabella e edit multi-file (bulk) da FILES.
- Ricalcolo automatico delle issue dopo una modifica manuale (lo fa la
  ri-scansione).
- Anteprima "prima/dopo" del piano per la modifica manuale: la modifica è
  immediata per scelta di design.
- Normalizzazione/pulizia automatica del valore digitato: `manual` è verbatim e
  autoritativo.
