# DjOrganizer — Specifica di design

> Data: 2026-06-27 · Stato: spina dorsale approvata; UI/test in revisione.
> App personale, locale, standalone. Repo separato da Cratory.

## 1. Scopo

DjOrganizer organizza le cartelle di musica sul disco e le prepara all'import in
Rekordbox. Tre lavori:

1. **Tag & metadata** — leggere e sistemare i tag (artist, title, album, genre, year,
   label), riempire i buchi, uniformare.
2. **Nomi file & struttura cartelle** — rinominare con schema coerente e riordinare in
   cartelle per genere / anno / label.
3. **Doppioni & qualita'** — trovare duplicati e versioni, file rotti, bitrate bassi,
   formati non ideali.

Non riproduce audio, non conserva audio, **non analizza BPM/key** (lo fa Rekordbox).

## 2. Relazione con Cratory

- **App separata, repo separato** (`~/Develop/DjOrganizer01`). Cratory gestisce
  metadata di streaming e per scelta non tocca i file audio; DjOrganizer gestisce i file
  fisici. Domini complementari.
- **Bridge opzionale, sola lettura**: DjOrganizer puo' chiamare l'API di Cratory
  (`GET /api/tracks?artist=&title=`) per proporre genere/label/anno gia' arricchiti.
  Cratory resta invariato e l'app funziona anche se Cratory e' spento.
- **Design system condiviso**: si copia lo strato grafico di Cratory; `DESIGN.md` resta
  la spec comune. Porta aperta a un merge futuro (monorepo) senza riscrivere la UI.

## 3. Principi (ereditati da Cratory)

1. **Motore deterministico**: scan, inspection, dedup, plan, conflict, apply, undo sono
   codice deterministico. Niente AI nel percorso critico.
2. **Output validati** con Pydantic prima di mostrare o eseguire.
3. **Anteprima-prima-di-mutare**: ogni modifica ai file e' prima un *piano* esplicito
   che l'utente approva.
4. **Reversibilita'**: modifiche in-place ma sempre annullabili. I delete vanno in
   **quarantena** (mai hard-delete); ogni run scrive un **undo journal**.
5. **Router sottili**: la logica (dedup, ranking, template) sta nei `services/`, non nei
   router.
6. **Mai sovrascrivere** un file esistente: collisione di destinazione -> op bloccata e
   segnalata.

## 4. Architettura

```text
Backend:   Python · FastAPI · SQLAlchemy · Pydantic
Frontend:  Next.js 16 · React 19 · Tailwind 4 (design system copiato da Cratory)
Database:  SQLite locale
Audio I/O: mutagen (lettura/scrittura tag; nessuna DSP)
Bridge:    client HTTP read-only verso l'API di Cratory
```

Layer backend (come Cratory):

- `app/routers/` — endpoint HTTP sottili.
- `app/services/` — il motore deterministico (una unita' per stage).
- `app/schemas.py` — modelli Pydantic, I/O validato.
- `app/models.py` — SQLAlchemy + SQLite.
- `app/integrations/` — wrapper `mutagen` (`tagio`) e `CratoryClient`.

## 5. Il motore deterministico

Pipeline di unita' piccole e isolate; ognuna ha un solo compito, input/output chiari, ed
e' testabile da sola.

| Stage | Compito | Input -> Output | Side effect |
|---|---|---|---|
| **Scanner** | walk cartelle, riconosce audio, legge tag, calcola hash+durata | radici -> righe `audio_file` | lettura FS + scrittura DB |
| **Inspector** | rileva problemi | file -> `issue[]` | nessuno (puro) |
| **Dedup** | raggruppa doppioni, propone keeper | file -> `dup_group[]` | nessuno (puro) |
| **Plan** | calcola le operazioni da regole+scelte | regole+file -> `plan_op[]` (RETAG/RENAME/MOVE/DELETE, prima->dopo) | nessuno (puro) |
| **Conflict** | valida il piano | plan -> errori/warning | nessuno (puro) |
| **Apply** | esegue il piano approvato | plan -> mutazioni FS + `undo_journal` | scrive FS |
| **Undo** | inverte un run | journal -> ripristino | scrive FS |
| **Bridge** | suggerisce tag da Cratory | artist+title -> genere/label/anno | rete (read-only) |

Dettagli chiave:

- **Scanner**: formati MVP `mp3, flac, wav, aiff, m4a/aac`. `content_hash` = hash dello
  stream audio (non dei tag), cosi' un retag non cambia l'identita' del file. File
  illeggibili/corrotti -> diventano un `issue`, lo scan non si interrompe.
- **Inspector** — tipi di issue MVP: tag obbligatorio mancante (artist/title), nome file
  incoerente coi tag, formato/bitrate non ideale, durata sospetta, tag-spazzatura
  (es. "Track 01", spam nei commenti), casing incoerente, genere/anno/label mancanti.
- **Dedup**: due livelli — **esatto** (stesso `content_hash`) e **versione/fuzzy**
  (stesso `artist+title` normalizzato, file diversi: mp3 vs flac, bitrate diverso).
  Keeper per precedenza: *lossless > bitrate piu' alto > tag piu' completi > path piu'
  pulito*. I non-keeper sono marcati `remove` (-> quarantena all'apply).
- **Plan**: template configurabili — nome file `{artist} - {title}`, cartella es.
  `{genre}/{artist}` o piatto. Piano deterministico, puro, validato Pydantic.
- **Conflict**: collisioni (due file -> stessa destinazione), dati mancanti per il
  template, destinazioni fuori dalle radici permesse. Blocca l'apply finche' non risolti.
- **Apply**: ordine sicuro (retag -> rename/move -> delete). Move via temp+rename, mai
  overwrite. Ogni op -> riga `undo_journal` con valori/percorsi precedenti. Delete = move
  in `.quarantine/`. Fallimento a meta' -> stop + proposta di undo del parziale.
- **Undo**: rilegge il journal di un run e inverte in ordine inverso.

**Invariante chiave (primo test):** per ogni piano, `apply` poi `undo` riporta il
filesystem **esattamente** allo stato iniziale (path, nomi, tag).

## 6. Modello dati (SQLite)

- `scan_root(id, path, label, last_scanned_at)`
- `audio_file(id, root_id, path, ext, bitrate, sample_rate, channels, duration_s,
  size_bytes, content_hash, artist, title, album, album_artist, genre, year, label,
  track_no, comment, has_cover, status[present|missing|quarantined], first_seen_at,
  last_scanned_at)`
- `issue(id, file_id, type, severity, detail, suggested_fix_json, resolved)`
- `dup_group(id, match_kind[exact|fuzzy], keeper_file_id)`
- `dup_member(group_id, file_id, action[keep|remove])`
- `plan(id, created_at, status[draft|applied|undone], rules_json)`
- `plan_op(id, plan_id, seq, kind[RETAG|RENAME|MOVE|DELETE], file_id, before_json,
  after_json, status)`
- `undo_journal(id, run_id, op_seq, kind, from_path, to_path, prior_tags_json,
  quarantine_path, applied_at, reversed)`
- `settings(id, naming_template, folder_template, allowed_roots_json,
  dedup_keep_rules_json, cratory_base_url)`

## 7. Pagine UI e flusso

Riuso diretto dei componenti di Cratory: `EditorialShell` (INDEX/CONTENT/MARGINALIA),
`PageLayout`, `ui.tsx` (Button/Badge/Card/Input/tabelle), `theme-toggle`, `clock`, e il
pattern `jobs-provider` + barre di progresso (scan e apply sono job asincroni).

Nav INDEX (sostituisce le voci di Cratory; wordmark proprio — nome di lavoro
**DJORGANIZER**):

- **SOURCES** — gestisci le radici, lancia lo scan, riepilogo conteggi.
- **FILES** — i file come indice tabellare denso (path, artist, title, formato, bitrate,
  durata, n. issue). Filtri/sort.
- **ISSUES** — raggruppate per tipo, con fix suggerito e accettazione in blocco.
- **DUPLICATES** — gruppi doppioni; scegli il keeper, marca le rimozioni.
- **PLAN** — anteprima del piano (diff prima->dopo per ogni op) + warning di conflitto;
  azione **APPLY**. Marginalia = statistiche piano (n. rename/move/retag/delete, spazio
  liberato).
- **HISTORY** — run passati; ognuno con **UNDO**.
- **SETTINGS** — template nome/cartella con anteprima live, regole tipo-file, regole keep
  dedup, URL + stato bridge Cratory.

Flusso: aggiungi radice -> **scan** (job) -> file/issue/doppioni persistiti -> rivedi
FILES/ISSUES/DUPLICATES, accetti fix e scegli keeper -> imposti i template (SETTINGS) ->
**PLAN** calcola e mostra l'anteprima -> CONFLICT valida -> **APPLY** (job) con undo
journal -> HISTORY mostra il run con UNDO.

## 8. Errori e sicurezza

- **Scanner resiliente**: errori di lettura/permessi per-file -> issue, mai crash.
- **Piano validato**: i conflitti bloccano l'apply con messaggi chiari (monocromi; rosso
  solo per errori veri, da `DESIGN.md`).
- **Apply**: ordine sicuro, niente overwrite, delete in quarantena, journal per-op,
  fallimento parziale -> stop + undo del parziale.
- **Bridge spento**: i suggerimenti spariscono, il resto funziona.
- **Idempotenza**: ri-scan riconcilia (file spostati/mancanti -> `status` aggiornato).

## 9. Test (come Cratory: pytest)

- Unit sulle funzioni pure (inspector, dedup, plan, conflict, render template) con
  fixture: cartelle temporanee + dizionari tag d'esempio.
- Apply/undo su filesystem temporaneo: crea file finti, applica, verifica le mutazioni,
  fai undo, verifica il ripristino.
- **Property test**: `apply` poi `undo` == stato iniziale.
- Frontend: `npm run lint` + `npm run build`.

## 10. Scope

**MVP**

- Scan + lettura tag (mutagen).
- FILES, ISSUES (tipi core), DUPLICATES (esatti + fuzzy).
- SETTINGS: template nome/cartella con anteprima.
- PLAN + conflict check.
- APPLY con quarantena + undo journal; HISTORY + UNDO.
- Design system copiato da Cratory; wordmark/nav propri.
- Bridge Cratory read-only (sottile: solo `GET /api/tracks`).

**Dopo (esplicitamente fuori MVP — YAGNI)**

- Embedding/fix cover art.
- Export Rekordbox XML/collection (MVP: cartelle pulite che trascini in Rekordbox).
- Dedup per fingerprint acustico (MVP: hash contenuto + metadata).
- Scrittura BPM/key nei tag pescandoli da Cratory.

## 11. Punti aperti

- **Nome/brand** (wordmark INDEX). Nome di lavoro: DjOrganizer.
- **Posizione quarantena** (configurabile; default `.quarantine/` nella radice).
- **Soglie fuzzy** per dedup e precedenza keeper (default: lossless > bitrate >
  completezza tag).
