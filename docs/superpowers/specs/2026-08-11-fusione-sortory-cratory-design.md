# Fusione Sortory → Cratory — Design

**Data:** 2026-08-11
**Stato:** approvato
**Repo coinvolti:** `DJProject01` (Cratory, casa), `DjOrganizer01` (Sortory, assorbito)

## Obiettivo

Unire Sortory e Cratory in un solo prodotto: un repo, un backend, un frontend, un
database, un modello dati. Il prodotto resta **Cratory**; le pagine di Sortory
diventano la sezione **Organize** della sua navigazione.

Le quattro motivazioni, tutte valide insieme:

1. Il design system e diversi moduli sono oggi duplicati e vanno manutenuti due volte.
2. Serve una UI sola e un avvio solo, non due server e due tab.
3. I due DB indicizzano gli stessi file su disco: una traccia deve essere una sola entità.
4. `Downloads → Sortory → Library → Cratory` è già di fatto una pipeline unica.

## Stato attuale (misurato, 2026-08-11)

### Stack — identico nei due progetti

Next 16.2.9, React 19.2.4, Tailwind v4, lucide-react; FastAPI + SQLAlchemy 2 +
Pydantic 2 + SQLite; Python 3.11.15 in entrambi i venv.

### Dimensioni

| | Sortory | Cratory |
|---|---:|---:|
| backend (righe .py) | 6.154 | 16.103 |
| frontend (righe .ts/.tsx) | 5.707 | 17.225 |
| file di test | 82 | 158 |
| commit | 320 | 860 |

### Collisioni di nome (le uniche)

- `routers/files.py`, `routers/settings.py`
- `services/genre_norm.py`, `services/native_picker.py` — **byte-identici**
- `integrations/_http.py` — quello di Cratory è un superset (212 righe contro 44,
  con workaround TLS 1.2 per host dietro ispezione HTTPS)
- rotta frontend `/settings`
- `components/ui.tsx` di Cratory è un superset esatto di quello di Sortory
  tranne `Progress` (Sortory) e `Chip`/`Combobox`/`DropdownMenu`/`SegmentedControl`/`BTN` (Cratory)

Nessuna collisione fra i nomi delle tabelle dei due DB.

### Le stesse due cartelle, descritte due volte

| Sortory | Cratory |
|---|---|
| `scan_root` #1 → `/Users/lucadenegri/Music/Downloads`, target `…/Library` | `SLSKD_DOWNLOAD_DIR=/Users/lucadenegri/Music/Downloads` |
| `scan_root` #2 → `/Users/lucadenegri/Music/Library` | `LIBRARY_ROOT=/Users/lucadenegri/Music/Library` |

### Dati esistenti

| Sortory (`djorganizer.db`) | | Cratory (`djassistant.db`) | |
|---|---:|---|---:|
| `scan_root` | 2 | `tracks` | 677 |
| `audio_file` | 1.777 | di cui `has_local_file` | 626 |
| di cui in `Library/` | 649 | `playlists` | 12 |
| di cui in `Downloads/` | 1.128 | `dj_sets` | 9 |
| `issue` (tutte chiuse) | 1.025 | `setlists` | 2 |
| `dup_group` | 0 | tracce votate | 184 |
| `plan` | 98 | | |
| `undo_journal` | 2.995 | | |

**Join su path assoluto fra i due DB**: 625 match esatti; 1 traccia Cratory senza
file corrispondente; 26 file in `Library/` che Cratory non conosce. Sortory
memorizza già path assoluti in `audio_file.path`, quindi il riappaiamento è una
join diretta, non un'euristica.

### I due hash non sono compatibili

- Sortory `content_hash`: blake2b sui byte dello stream (ID3/metadata block
  saltati). Niente ffmpeg, identità byte-esatta, gratis durante la lettura del file.
- Cratory `audio_hash`: sha256 sui primi secondi di audio **decodificato** via ffmpeg.
  Sopravvive a retag e rinomina, ma costa un processo esterno per file.

Non si joinano. La chiave di migrazione è il **path assoluto**.

## Decisioni

| # | Decisione | Scartate |
|---|---|---|
| D1 | Prodotto **Cratory**, Sortory diventa la sezione **Organize** | nome nuovo per l'insieme; Sortory come brand interno |
| D2 | Modello **`Track` 1─N `AudioFile`** | collasso letterale in `tracks`; Library in `tracks` + tabella `inbox_file` a parte |
| D3 | Repo Cratory + **subtree merge** di Sortory (storia preservata) | repo nuovo; copia senza storia |
| D4 | Migro **storia sì, derivati rigenerati** | migrazione completa; solo Cratory con Sortory da zero |
| D5 | **Uno scan solo, in due fasi** | due job concatenati; due job separati |
| D6 | Codice Sortory sotto namespace **`app/organize/`** | appiattimento con prefissi `organize_*` |
| D7 | `scan_root` **eliminata**: le cartelle vengono da Settings | lista di sorgenti gestita dall'utente |

### Perché non il collasso letterale in `tracks` (D2)

`Track` e `AudioFile` non descrivono la stessa cosa e il rapporto non è 1:1:

- `Track` è **l'opera musicale**: esiste anche senza file (lead di discovery,
  wishlist, playlist Spotify), ha identità `isrc`/`platform_track_id`, è già
  de-duplicata per costruzione.
- `AudioFile` è **il file su disco**. Che esistano più file per la stessa traccia
  non è un incidente: è la ragione d'essere di `DupGroup`/`DupMember`. E 1.128
  file su 1.777 vivono in `Downloads/`, dove Cratory non guarda affatto.

Inoltre `title/artist/album/genre/year/label` esistono su entrambe ma con
significato diverso: su `AudioFile` sono **ciò che c'è scritto nel tag adesso**,
su `Track` sono **ciò che la traccia è**. La differenza fra i due *è* l'Issue di
Sortory: collassarli in una colonna sola lascia il motore di issue senza niente
da confrontare.

## Design

### 1. Navigazione

Il gruppo **Organize** si inserisce fra Scopri e Colleziona, cioè nel punto della
catena dove Sortory vive:

```
Scopri      Discovery · Shazam · Download
Organize    Inbox · Duplicati · Piano · Storico
Colleziona  Libreria · Playlist · Etichette
Suona       Set · Transizioni · Analisi
```

**Confine Organize / Libreria** — è il punto dove può rinascere la ridondanza:

- **Organize** guarda i *file*: cosa c'è nei tag adesso, cosa è rotto, cosa è
  duplicato, dove va spostato. Campo d'azione naturale: l'inbox.
- **Libreria** guarda le *tracce*: possesso, BPM/key, rating, playlist, set.

Per i file **già in Library** con tag da correggere non nasce una seconda
tabella: la traccia in Libreria mostra il suo stato "file" (issue aperte,
qualità, duplicati) e da lì si entra nel dettaglio di Organize.

**Rotte**: tutte le pagine Sortory sotto `/organize/*` (`/organize`,
`/organize/duplicates`, `/organize/plan`, `/organize/history`). L'unica
collisione, `/settings`, si risolve fondendo le due pagine: naming template,
folder template e regole dedup diventano card aggiuntive in quella di Cratory.

**Sources sparisce** (D7): non c'è una lista di sorgenti gestita dall'utente, ci
sono due cartelle canoniche già configurate in Settings, e `AudioFile` deriva la
propria collocazione dal prefisso del path.

### 2. Backend

Un solo processo FastAPI (`:8000`), un solo DB, un solo venv. La porta `:8010` di
Sortory sparisce.

```
backend/app/
  models.py              Track, Playlist, Setlist, DjSet, … + AudioFile
  routers/               (Cratory, invariato)
  services/              (Cratory) + genre_norm, native_picker deduplicati
  integrations/          (Cratory) + tagio, fsops, acoustid, musicbrainz, …
  organize/
    models.py            Issue, DupGroup, DupMember, Plan, PlanOp, UndoJournal
    routers/             scan, issues, duplicates, plan, apply, history, …
    services/            scanner, planner, apply, dedup, undo, inspector, …
```

Il namespace risolve tutte e tre le collisioni di modulo senza rinominare nulla,
il che tiene validi gli 82 file di test di Sortory con una riscrittura
**meccanica** degli import (D6).

**`AudioFile` sale a `app/models.py`**, accanto a `Track`: con D2 anche Libreria
la legge, non è più un dettaglio interno di Organize. Restano in
`organize/models.py` solo le entità del flusso di correzione. Questo evita anche
l'import circolare che nascerebbe dalla relazione `Track` ↔ `AudioFile`.

**Deduplicazioni**: `genre_norm.py` e `native_picker.py` → una copia sola in
`app/services/`. `_http.py` → vince quello di Cratory, i provider di Sortory ci
si appoggiano.

**Configurazione**: un solo `backend/.env`, senza prefisso (stile Cratory). Le
chiavi `DJORG_*` lo perdono (`DJORG_DISCOGS_TOKEN` → `DISCOGS_TOKEN`): è la
deroga esplicita alla regola "non toccare gli identificatori storici" di Sortory,
che aveva senso finché le app erano separate. Muore `organizer_url`, usato solo
dal link "Apri Sortory" in dashboard.

**DB**: resta `djassistant.db`, nome legacy incluso. Rinominarlo costringerebbe a
rifare i path in `.env`, negli script e nei worktree senza guadagno.

**Dipendenze**: unione dei due `requirements.txt`. Cratory guadagna `pyacoustid`
e `Pillow` (più il binario di sistema `fpcalc`); `mutagen` e `anthropic` ci sono
già in entrambi.

**Rischio noto**: `pytest.ini` di Sortory ha `filterwarnings = error`, quello di
Cratory no. Fondendoli, i 158 file di test di Cratory finiscono sotto una regola
più severa di quella con cui sono stati scritti. Quanti warning emergano è
verificabile in pochi minuti ed è **il primo controllo di F1**. Se sono pochi si
sistemano; se sono molti la strictness resta ristretta a `tests/organize/` finché
il resto non è ripulito.

### 3. Modello dati

```
Track  (l'opera musicale / il lead)
  id, isrc, platform_track_id, spotify_id, …
  title, artist, album, genre, year, label      ← metadati canonici
  bpm, camelot_key, energy, rating, status, …
  primary_file_id ──┐
  has_local_file, local_path, local_format, local_bitrate   ← cache derivata
                    │
                    │ 1 ─── N
                    ▼
AudioFile  (il file su disco)
  id, path (assoluto, unique), ext, size_bytes, bitrate, sample_rate, channels
  track_id ──> tracks.id  (NULL = file non ancora riconosciuto)
  location: inbox | library  NOT NULL           ← derivata dal prefisso del path
  artist, title, album, genre, year, label      ← tag LETTI dal file, ora
  content_hash (blake2b byte-esatto) + audio_hash (sha256 decodificato)
  integrity_ok, status, first_seen_at, last_scanned_at
       │
       ├── Issue        (file_id)   ← invariata
       ├── DupMember    (file_id)   ← invariata
       ├── PlanOp       (file_id)   ← invariata
       └── UndoJournal  (file_id)   ← invariata
```

Modifiche allo schema esistente:

- `audio_file`: rimossa `root_id`; `path` diventa unique da sola (prima
  `UNIQUE(root_id, path)`); aggiunte `track_id` (FK nullable) e `location`.
- `tracks`: aggiunta `primary_file_id` (FK nullable).
- `scan_root`: eliminata.

`location` è NOT NULL con due soli valori. Non esiste un terzo caso: lo scan
cammina esclusivamente le due radici configurate, quindi un file fuori da
entrambe non entra nell'indice. Se una radice non è configurata in Settings,
quella metà dello scan è semplicemente inattiva — stesso comportamento che
Cratory ha già oggi con `LIBRARY_ROOT` vuoto.

Tre scelte da motivare:

**I `local_*` restano su `Track` come cache derivata**, mantenuta dallo scan.
`has_local_file` è indicizzato e interrogato ovunque nelle 16.000 righe di
Cratory: tenerlo come colonna significa che Libreria, Discovery, wishlist e Set
Builder continuano a funzionare **senza toccare una query**. `primary_file_id`
indica il file rappresentante quando ce n'è più d'uno.

**I tag su `AudioFile` non vengono rinominati** in `observed_*`: il significato lo
porta la tabella, e rinominarli costerebbe un passaggio su tutto il codice di
Sortory per un guadagno cosmetico.

**I due hash convivono**, perché rispondono a domande diverse. `audio_hash` si
calcola solo per i file con `location = library`, non per i 1.128 dell'inbox.

**`DupGroup` resta com'è**: con `track_id` i duplicati "stessa traccia" sarebbero
derivabili, ma il gruppo porta stato reale (keeper scelto a mano, `dismissed`)
che una vista non può tenere. Guadagna semmai un `match_kind` in più.

### 4. Scanner unico (D5)

Oggi due job camminano sulle stesse cartelle: `scan_job`/`scanner` di Sortory
(tag, bitrate, integrità, `content_hash`) e `library_index_job`/`library_index`
di Cratory (`audio_hash`, creazione tracce, `added_at` dal birthtime, riaggancio
dei file spostati).

Diventano **una camminata sola in due fasi**:

1. **Lettura file → `AudioFile`**: base il codice di Sortory, il più ricco.
2. **Aggancio a `Track` e aggiornamento della cache `local_*`**: logica di Cratory.

Un bottone, una progress bar, nessun disallineamento possibile fra i due indici.

### 5. Frontend

Un solo `frontend/` (quello di Cratory), pagine Sortory sotto `app/organize/*`.

**Componenti condivisi**: si tiene la versione Cratory di `clock`,
`editorial-shell`, `theme-toggle`, `path-picker-button`, `cn.ts` (usa
`tailwind-merge`) e `ui.tsx`, travasando `Progress` da Sortory. `page-layout.tsx`
è l'unico davvero divergente (49 righe contro 40, 51 di diff) e va riconciliato
a mano.

**`jobs-provider`** è il vero punto di merge del frontend: due sistemi di job con
due progress bar. Base quello di Cratory (396 righe contro 178, già coordina più
job concorrenti); i job di Sortory — scan, apply, provider rescan, genre review,
integrity — si registrano lì dentro. Una barra sola in fondo alla pagina.

**i18n**: i due progetti hanno la stessa identica architettura (`en.ts` source of
truth senza `as const`, `it.ts` tipizzato su `typeof en`, `index.tsx` col
provider, `runtime.ts` fuori React). Le 485 righe di `en.ts` di Sortory entrano
sotto la chiave `organize.*` nelle 1.194 di Cratory, idem `it.ts`. Una chiave
mancante resta un errore di tipo.

**Componenti che muoiono**: `add-source.tsx`, `source-menu.tsx`, `index-nav.tsx`
di Sortory.
**Componenti che traslocano** sotto `components/organize/`: `files-table`,
`issues-table`, `dup-group`, `plan-ops`, `apply-modal`, `file-edit-panel`,
`cover-thumb`.

**`globals.css`**: 90 righe di differenza su ~150, da riconciliare guardando le
due app affiancate — è l'unico punto in cui una scelta sbagliata si vede su tutte
le pagine.

### 6. Migrazione dei dati

**La migrazione non tocca il disco**: sposta righe fra due file SQLite. Nessun
file audio viene letto, spostato o riscritto.

1. **Backup** dei due `.db` con timestamp, fuori dalle cartelle `data/`. Prima
   riga dello script, non negoziabile.
2. `djassistant.db` viene **copiato**; si lavora sulla copia. L'originale non
   viene mai aperto in scrittura: il rollback è cancellare la copia.
3. `ensure_schema` crea le tabelle `organize/` e le colonne nuove.
4. `ATTACH` di `djorganizer.db` e travaso di `audio_file`: `root_id` sparisce,
   `location` derivata dal prefisso (`inbox` sotto `SLSKD_DOWNLOAD_DIR`,
   `library` sotto `LIBRARY_ROOT`).
5. Aggancio:
   `UPDATE audio_file SET track_id = (SELECT id FROM tracks WHERE local_path = audio_file.path)`
   e `tracks.primary_file_id` in specchio.
6. `plan`, `plan_op`, `undo_journal` con rimappatura degli id vecchi→nuovi via
   tabella di corrispondenza temporanea.
7. `issue` e `dup_group` **non** si migrano: sono derivati, le issue sono tutte
   chiuse, i gruppi sono zero. Li rigenera il primo scan.

**Assert di fine migrazione — su invarianti, non su costanti.** Lo script conta
la sorgente all'inizio della propria transazione e verifica che la destinazione
combaci; se un confronto non torna, si ferma e la copia si butta.

```
audio_file migrati        == COUNT(*) da s.audio_file
location=library + inbox  == audio_file migrati            (nessun terzo caso)
track_id valorizzati      == COUNT(join su path assoluto)
tracks.primary_file_id    == track_id valorizzati          (specchio esatto)
plan, plan_op, undo_journal == rispettivi COUNT sorgente
FK orfane                 == 0
```

**Perché non numeri fissi.** La prima stesura di questa spec congelava i valori
misurati il 2026-08-11 (1777 / 649 / 1128 / 625 / 98 / 2995). Rimisurati lo
stesso giorno, dopo un uso di Sortory standalone, erano già 1778 / 650 / 1128 /
625 / 99 / 2996. Un assert su costanti avrebbe fatto fallire una migrazione
corretta. I numeri assoluti restano utili come **ordine di grandezza atteso**
nel report, non come condizione di successo.

Baseline di riferimento (2026-08-11, seconda misura), da confrontare a occhio
col report del dry-run:

| | |
|---|---:|
| `audio_file` totali | 1.778 |
| di cui in `Library/` | 650 |
| di cui in `Downloads/` | 1.128 |
| match su path assoluto | 625 |
| `plan` | 99 |
| `undo_journal` | 2.996 |
| `issue` (non migrate) | 1.025 |
| `dup_group` (non migrati) | 0 |
| `tracks` Cratory | 677 |
| `tracks` con `has_local_file` | 626 |

Se il dry-run si discosta di molto da questi ordini di grandezza, **fermati**:
non è la migrazione ad avere un bug, è il DB sorgente a non essere quello atteso.

Prima della migrazione reale gira un **dry-run**: stessa procedura su un DB in
memoria, stampa il report, non scrive niente.

**Cosa ha trovato la migrazione reale (2026-08-12).** Il dry-run è fallito al primo
tentativo, ed è il suo mestiere: **158 riferimenti orfani** nella sorgente,
accumulati perché il vecchio engine di Organize girava con le foreign key spente —
87 `plan_op.file_id` e 71 `undo_journal.file_id` verso `audio_file` non più
esistenti (gli altri tre vincoli: zero). Delle 71 voci di undo, **52 erano rename
di sola normalizzazione Unicode** (`from_path` e `to_path` byte-diversi ma
identici dopo NFC), 19 differenze di percorso reali.

Decisione presa: **scartarle**, con dump completo su file
(`backend/data/djassistant.scartati.jsonl`, 158 righe con tutte le colonne, quindi
la storia resta ricostruibile). Lo script ha guadagnato il flag `--scarta-orfani`;
senza flag il default resta il rifiuto, e l'invariante è passato da
`migrati == sorgente` a `migrati + scartati == sorgente`.

Nota per chi legge dopo: la normalizzazione Unicode **non** tocca l'aggancio dei
625 di F3 (verificato: 625 match esatti, zero recuperi aggiuntivi via NFC).

**Casi noti fuori dai 625**, attesi nel report:

- 1 traccia Cratory il cui `local_path` nessun file Sortory conosce → resta senza
  `track_id` agganciato finché il primo scan non la ritrova.
- 26 file in `Library/` sconosciuti a Cratory → entrano con `track_id` NULL; la
  fase 2 dello scanner crea la traccia, come fa oggi l'indicizzazione libreria.

**Garanzie di sicurezza invariate**: il piano approvato prima di ogni scrittura
resta, la quarantena al posto della cancellazione resta, l'undo journal resta —
e diventa più affidabile, perché journal e tracce finiscono nella stessa
transazione SQLite invece che in due DB che potevano divergere.

## Fasi

Il lavoro va fatto in un **worktree isolato**, con `npm install` reale (non
symlink) e un `backend/.venv` proprio.

Ogni fase è abbastanza grossa da meritare il **proprio piano di
implementazione**: questa spec è il contratto complessivo, i piani si scrivono
uno per fase, in sequenza, ciascuno dopo che la milestone della fase precedente
è verde.

| Fase | Contenuto | Milestone |
|---|---|---|
| **F1** Innesto | subtree merge (`--allow-unrelated-histories`), codice sotto `organize/`, import riscritti, un `requirements.txt`, un venv, un `package.json`. Un solo processo FastAPI che monta anche i router `organize`, ma con **due engine e due file DB** ancora separati; il client API del frontend Sortory punta all'unica base `:8000` | entrambe le suite passano insieme, l'app parte, le pagine Organize rispondono; misurato l'impatto di `filterwarnings = error` |
| **F2** DB unico | un `Base`, un engine, un `ensure_schema`; script di migrazione con dry-run e assert | ✅ **completata 2026-08-12** — 1801 test verdi, 0 warning; migrazione reale eseguita (1.778 `audio_file`, 99 `plan`, 3.337 `plan_op`, 2.925 `undo_journal`); 191 issue rigenerate; 625 agganci pronti per F3 |
| **F3a** Modello A | `track_id`, `location`, `primary_file_id`; `local_*` come cache | **completata 2026-08-12**: 624 tracce col file agganciato (625 prima della fusione del duplicato *Aqua Viva*), zero asimmetrie e zero orfani anche dopo uno scan reale, `routers/` e `repositories.py` non toccati, 1829 test verdi |
| **F3b** Via `scan_root` | rimozione di `scan_root`/`root_id`/`root_targets` e della pagina Sources (83 riferimenti) | ✅ **completata 2026-08-12** — eseguita in due tempi, F3a (modello) e F3b (`scan_root` fuori dal dominio): i target del piano derivano da Settings, nessuna regressione su Piano e Apply, 1844 test verdi. La rimozione **di schema** — la colonna `audio_file.root_id` e la tabella `scan_root` — è **rimandata**: si rivaluta dopo F4, se lo scanner unico richiede comunque un rebuild di `audio_file` |
| **F4** Scanner unico | una camminata, due fasi | un solo bottone; il secondo scan consecutivo non cambia nulla nel DB (idempotenza) |
| **F5** UI unificata | nav con Organize, componenti deduplicati, `Progress` travasato, i18n `organize.*`, `globals.css`, Settings unica, Sources cancellata | `npm run build` + `lint` + e2e Playwright verdi; confronto visivo con le due app affiancate |
| **F6** Pulizia | `CLAUDE.md`, `README.md`, `docs/ARCHITECTURE.md`, `docs/API.md`, `docs/ROADMAP.md` per un prodotto solo; repo Sortory archiviato su GitHub (non cancellato); rimossi `organizer_url` e il link "Apri Sortory" | documentazione senza riferimenti a due app separate |

## Verifica

Nessuna fase si dichiara chiusa senza l'output dei comandi: `pytest` completo,
`npm run build`, `npm run lint`, e per F5 anche gli e2e Playwright.

In più, dopo F4, un controllo non automatizzabile: **uno scan reale sulle 1.777
righe con confronto prima/dopo**, perché i test girano su fixture e il disco no.

## Fuori scope

**`DJPlayer01`**, terzo pezzo della catena. Condivide le stesse cartelle
(`MUSIC_DIR` = `Downloads`, `ARCHIVE_DIR` = `ARCHIVE_ROOT`) ed è il candidato
successivo, ma è Next-only senza backend Python: è una fusione di natura diversa.
Questo design non lo tocca; gli lascia la porta aperta, perché dopo F3 esiste un
posto solo dove un file su disco è rappresentato.

## Impatto sulle regole di progetto

`CLAUDE.md` dichiara oggi che *"le due app non si parlano via rete: l'unica
interfaccia è il disco"*. Con la fusione la regola non si allenta, **decade**: non
ci sono più due app. Restano invece invariate, e vanno riaffermate in F6:

- **Sortory è l'unico che scrive i tag testuali.** Dopo la fusione è la sezione
  Organize, ma la proprietà della scrittura resta sua: nessun'altra parte del
  codice tocca i tag.
- **BPM/key**: Rekordbox primario, analisi in-app alternativa deterministica.
- **Ogni operazione sui file è prima un piano approvato**, con quarantena e undo.
