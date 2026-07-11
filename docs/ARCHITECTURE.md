# Architettura

Cratory e' una webapp locale/self-hosted, mono-utente, per trasformare playlist
streaming e libreria su disco in materiale operativo da DJ: bozze di set, gap
analysis, discovery e corpus di mix identificati.

## Principi

- Il motore deterministico gestisce fatti, score, deduplica, ruoli, ranking e validazione.
- L'AI gestisce linguaggio, narrativa, interpretazione del prompt e spiegazioni.
- **BPM e Camelot/key vengono solo dall'import Rekordbox XML**: Cratory non li stima
  ne' li inventa. Un dato gia' presente non viene mai sovrascritto dall'import.
- **`energy` e' sempre derivata** (deterministica, da BPM+genere): non e' un dato di
  provider ne' un campo editabile a mano.
- **Cratory legge i file audio ma non li scrive mai.** Tag, rename e organizzazione
  su disco restano competenza di Sortory; l'arricchimento testuale dei metadati
  (titolo/artista/album/label/genere) e' anch'esso di Sortory.
- Spotify non fornisce feature di mixing: serve per identita', metadata, import/export.
- I provider esterni rimasti (Last.fm, Discogs, Spotify) servono **solo la Discovery**
  per gusto e similarita', non la pipeline di feature.
- L'AI non riceve mai tutta la libreria: il Candidate Engine le passa al massimo 60 candidate.
- Ogni output AI passa da schema Pydantic e Validation Engine.
- L'app non riproduce audio. Non conserva file audio, con un'eccezione dichiarata:
  l'acquisizione persistente via Soulseek/slskd, collegata a una `Track` esistente
  (`has_local_file`/`local_path`/`local_format`/`local_bitrate`). Resta distinta dal
  modulo Shazam, che scarica audio solo in modo temporaneo per il fingerprinting e
  non lo conserva.

## Flusso principale

```text
Spotify / import manuale
  -> Playlist Importer
  -> normalizzazione + deduplica
  -> SQLite
  -> Library Explorer / Gap Analysis
  -> Candidate Engine
  -> Set Builder deterministico
  -> AI Set Agent opzionale
  -> Validation Engine
  -> Set Editor / Export / Discovery write-back
```

In parallelo, la fonte di BPM/key:

```text
Rekordbox (analisi utente)
  -> File > Export Collection in xml format
  -> POST /api/rekordbox/import
  -> match path (NFC) -> audio_hash (gated su basename) -> artist+title
  -> bpm/camelot_key riempiti solo se assenti (mai sovrascritti)
  -> energy ricalcolata deterministicamente
```

Discovery ha due rami paralleli, entrambi orientati al **gusto** (non alla
compatibilita' tecnica, che resta del Set Builder). Espansione playlist:

```text
playlist importata
  -> seed artisti/tracce
  -> Last.fm similarity
  -> dedup vs libreria
  -> resolver Spotify /search
  -> ranking per gusto + annotazione etichetta (boost se gia' collezionata)
  -> spiegazione AI opzionale
  -> add to library
```

Crate digging (Scava), sorgente alternativa via Discogs (niente Last.fm/Spotify):

```text
seme: genere o etichetta
  -> Discogs search (release per genere/stile o per label)
  -> lead non posseduti, dedup vs libreria + dedup varianti
  -> ranking per domanda (want/have), profondita' e novita'
  -> preset Familiare/Bilanciato/Avventuroso, cap per artista
  -> add to library
```

La Gap Analysis resta una lettura deterministica delle mancanze della playlist, ma la
vecchia sezione Discovery che suggeriva tracce partendo dai gap e' stata rimossa.

Identificazione mix:

```text
URL SoundCloud/Mixcloud/YouTube
  -> yt-dlp download temporaneo
  -> ffmpeg segmenti audio
  -> Shazam recognizer
  -> dedup match consecutivi
  -> DjSet + DjSetTrack
```

Le tracce identificate nei mix non entrano nella libreria principale: restano un corpus
separato per analisi e suggerimenti futuri. Questo e' l'unico fingerprinting che Cratory
esegue: identifica i brani di un mix esterno via Shazam, non le tracce della libreria.

Acquisizione file via Soulseek (slskd), distinta dal download temporaneo Shazam:

```text
Track in libreria (identita' streaming)
  -> SlskdClient.search (slskd REST)
  -> selezione deterministica (qualita' + match nome + disponibilita')
     | ricerca libera -> selezione manuale (/api/downloads/search + /manual)
  -> auto-pick (blocco playlist) | mini-selettore (Discovery)
  -> slskd enqueue + polling transfer
  -> attach_local_file: has_local_file + local_path/format/bitrate
```

E' deterministica (zero AI), mono-job (un download alla volta) e best-effort: un
errore su una traccia non ferma il job. Richiede slskd configurato; senza, gli
endpoint rispondono `409`. Il file resta collegato alla `Track` come riferimento
locale, non viene ricaricato ne' ridistribuito dall'app.

Oltre all'auto-pick, `POST /api/downloads/search` offre ricerca libera su slskd con
selezione manuale del candidato (`POST /api/downloads/manual`). Gli esiti da rivedere
(`needs_review|not_found|failed`) restano in coda "da sistemare", persistiti su
`Track.last_download_outcome`/`last_download_reason` cosi' da sopravvivere a job e
riavvii (`GET /api/downloads/pending`, `DELETE /api/downloads/pending/{track_id}`,
`POST /api/downloads/retry-pending`). Un file gia' su disco puo' anche essere
collegato manualmente dal dettaglio traccia (`POST /api/tracks/{track_id}/link-file`,
ricerca per nome in `LIBRARY_ROOT` e nella cartella download slskd via
`GET /api/files/search`), con lo stesso `attach_local_file`/`audio_hash`
dell'acquisizione.

## Disk-first

La libreria e' il disco: il possesso di una traccia (`has_local_file`) non e' un
side-effect dell'acquisizione Soulseek soltanto, ma lo stato di una cartella
canonica che Cratory indicizza attivamente. **Cratory legge i file audio ma non li
muta mai** — tag, rename e organizzazione restano competenza esclusiva di Sortory.

- **`LIBRARY_ROOT`**: cartella organizzata (gestita da Sortory) che Cratory
  indicizza da Impostazioni -> "Libreria (disco)". Vuota = indicizzazione disattiva.
  L'indicizzazione parte anche automaticamente a ogni avvio dell'app (job in
  background, se `LIBRARY_ROOT` e' configurata), oltre che on-demand.
- **`ARCHIVE_ROOT`**: archivio delle scartate (PASSED di DJPlayer), scansionato
  insieme alla libreria. Un match in archivio marca la Track `archived=True` e
  toglie il possesso, senza creare tracce nuove; il possesso in Libreria vince
  sempre sullo scarto e riabilita la traccia.
- **`audio_hash`**: SHA-256 dei primi secondi di audio decodificato via ffmpeg (mono,
  22050 Hz, s16le) — stabile a rinomina e retag, a differenza di path o tag ID3/MP4.
  Calcolato sia dall'indicizzazione di libreria sia dall'acquisizione Soulseek
  (`attach_local_file`) sia dal match di fallback dell'import Rekordbox, cosi' i
  percorsi convergono sullo stesso identificativo.
- **`library_index`** (`backend/app/services/library_index.py`, deterministico):
  per ogni file sotto `LIBRARY_ROOT` calcola l'hash e cerca un match nell'ordine
  `audio_hash -> digest legacy (import locali storici, in platform_track_id) ->
  ISRC -> fuzzy artist+title esatto -> fuzzy normalizzato`; se non trova nulla crea
  una nuova `Track`. Il **fuzzy normalizzato** aggancia titoli con suffissi diversi
  ma stesso brano (toglie `feat./ft.`, `(Original Mix)`, `- ... Remix`, diacritici e
  punteggiatura) confrontando artista+titolo normalizzati, ma **solo su lead senza
  file** e con **guardia sulla durata** (±7s): non ruba il file a una posseduta ne'
  fonde un brano col suo remix di durata diversa. I tag del
  file riempiono solo i campi identita' vuoti, in sola lettura (mai sovrascrivere
  BPM/key o correzioni manuali; Cratory non scrive mai sul file). Anche `label`
  (ID3 `TPUB` / Vorbis `LABEL`) viene letta dal file e riempita solo se assente.
  Lo scan **ignora sempre cartelle e file nascosti** (nome che inizia con `.`, es.
  `.quarantine`, `.DS_Store`, `.git`): non sono contenuto di libreria, ne' per il
  conteggio ne' per l'indicizzazione. Scan incrementale: un file con path+mtime+size
  invariati non viene ri-hashato. Riconciliazione: un possesso il cui file la
  scansione **non ha visto** — cancellato, spostato fuori da `LIBRARY_ROOT`, oppure
  finito in una cartella nascosta (es. `.quarantine`) — viene sganciato
  (`has_local_file=False`, `local_path` azzerato) ma mantiene `audio_hash`, cosi' il
  riaggancio e' immediato se il file ricompare (anche a un lead Spotify esistente via
  ISRC o artist+title). Se il brano sganciato non e' in nessuna playlist ne' in un set
  salvato viene **eliminato** (niente lead fantasma, contatore `orphans_removed`);
  altrimenti resta come lead senza file (contatore `lost`). Guard anti-unmount: uno
  scan a zero file (radice vuota, path sbagliato, disco smontato) non tocca i possessi
  esistenti. `duplicates` conta i file con lo stesso hash visti nello stesso run (il
  primo vince; la dedup su disco resta compito di Sortory). Esposto via
  `POST /api/library/index` (202, job async) e `GET /api/library/index/status`;
  risponde `409` se `LIBRARY_ROOT` non e' configurata.
- **Cover art:** l'artwork della traccia posseduta e' servito on-demand dal file
  (`GET /api/tracks/{id}/cover`, artwork incorporato letto al volo, non salvato in DB;
  copre FLAC/OGG, ID3 APIC, MP4 `covr`). La cover Spotify (`album_art_url`) ha
  precedenza quando presente; il frontend ripiega sull'endpoint solo per le possedute
  senza cover streaming.
- **Lead orfani e pulizia.** Un "lead orfano" e' una traccia senza file su disco che
  non appartiene a nessuna playlist ne' a un set salvato: non ha piu' ragione di
  esistere. Vengono rimossi in due punti, con l'helper condiviso `delete_orphan_leads`
  / `unreferenced_track_ids` (in `repositories.py`): quando si **cancella una playlist**
  (`DELETE /api/playlists/{id}` ritorna `{deleted_tracks}`) e durante la
  **riconciliazione dell'indice** (vedi sopra). Per un allineamento una-tantum del DB
  al paradigma disk-first c'e' `backend/app/tools/cleanup_disk_first.py` (dry-run di
  default, `--apply` per scrivere), che si appoggia a
  `backend/app/services/db_hygiene.py`: fonde i doppioni stesso-file, elimina i lead
  orfani, azzera sui lead i campi residui legacy (`genre`/`bpm`/`camelot_key`/`energy`,
  senza writer nel flusso attuale) e **rilegge le possedute dal disco** rendendolo
  autorevole sui campi
  disco-derivabili (mai tocca BPM/key da Rekordbox ne' la cover Spotify; sola lettura
  dei file).
- **Fusione doppioni (stesso brano in due righe).** L'helper `merge_tracks(keep, drop)`
  (in `repositories.py`) sposta le membership playlist/set su `keep`, riempie i suoi
  campi vuoti da `drop` (keep resta autorevole su cio' che ha gia') e cancella `drop`.
  Usato in due punti: il **collegamento manuale di un file** (`attach_local_file`)
  fonde una traccia che possiede gia' quello stesso file (stesso `audio_hash`/
  `local_path`), cosi' non restano due righe; e la **dedup per `audio_hash`**
  (`dedupe_by_audio_hash` in `db_hygiene`, operazione dello script
  `cleanup_disk_first`) fonde le righe che condividono lo stesso file, tenendo quella
  con identita' streaming (`spotify_id`/`isrc`). Con questi e il fuzzy normalizzato il
  match manuale dovrebbe essere raramente necessario.
- Il possesso alimenta anche il Set Builder: `SetGenerationRequest.owned_only` (default
  `True`) filtra le candidate del Candidate Engine alle sole tracce con file locale;
  la scelta e' persistita su `Setlist.owned_only` e rispettata anche da editor
  (alternative, sostituzione traccia — 422 se la sostituta non e' posseduta e il set
  e' nato "solo posseduti").

## Import Rekordbox (fonte di BPM/key)

Cratory non stima ne' inventa BPM/tonalita': l'utente analizza la libreria in
Rekordbox (fuori da Cratory) ed esporta la collezione (`File > Export Collection in
xml format`); Cratory importa quell'XML per riempire BPM/Camelot sulle tracce gia'
possedute sul disco. Beatgrid, cue e altri campi Rekordbox restano fuori scope.

- **`POST /api/rekordbox/import`** (multipart, campo `file`): parsa l'XML
  (`defusedxml`, anti-XXE) e per ogni `TRACK` cerca la `Track` posseduta
  corrispondente nell'ordine: **path normalizzato NFC** (macOS/Rekordbox puo'
  decodificare `Location` in NFD) -> **`audio_hash`** di fallback, gated sul
  basename del path per evitare un decode ffmpeg costoso su righe non nostre ->
  **fuzzy artist+title**. Su match, riempie `bpm`/`camelot_key` **solo se assenti**
  (un dato gia' presente resta autorevole, non viene mai sovrascritto), ricalcola
  `energy` deterministicamente quando il BPM e' impostato, e aggiorna lo stato
  traccia. Risponde con i conteggi (`in_file`, `matched`, `unmatched`, `bpm_set`,
  `key_set`, `energy_set`). `400` su file vuoto o XML non valido/non sicuro.
- **`GET /api/rekordbox/pending`**: conta le tracce possedute (`has_local_file`)
  ancora senza BPM o senza key — il numero che l'utente deve ancora "analizzare in
  Rekordbox ed importare". Esposto anche in `GET /api/pipeline` come
  `analyze_pending`.

## Layer backend

```text
backend/app/
  routers/        endpoint FastAPI, solo HTTP e mapping errori
  services/       logica applicativa deterministica e orchestrazione
  repositories.py query SQLAlchemy e mutazioni DB
  models.py       modelli SQLAlchemy
  db.py           sessione/engine, ensure_schema e migrazioni idempotenti
  schemas.py      request/response Pydantic
  serializers.py  ORM -> Pydantic, campi derivati
  integrations/   client esterni dietro interfacce
  core/           config, logging
  tools/          script di manutenzione (es. clean_user_data, cleanup_disk_first)
```

I router non devono contenere logica di business. Le integrazioni esterne devono
essere iniettabili o isolabili, cosi' i test possono usare fake client senza rete.

## Motore deterministico

Responsabilita':

- import playlist e import manuale;
- deduplica con priorita' `ISRC -> platform_track_id -> artist+title+duration -> fuzzy`;
- import Rekordbox (BPM/key, mai sovrascritti) e ricalcolo `energy` derivata;
- stato traccia (`imported`, `ready_for_set`);
- score BPM, Camelot, energia, genere e durata (il contratto include anche uno score
  di coerenza mood, oggi sempre neutro: `Track` non ha piu' un campo mood da quando
  il motore di enrichment e' stato ritirato). La similarita' di genere usa una mappa
  deterministica di famiglie (techno/house/breaks/chill/...): sottogeneri della stessa
  famiglia sono coerenti anche senza token in comune, i super-generi ("Electronic")
  sono neutri, famiglie diverse valgono come stacco. Nel set generator la coerenza di
  genere e' un termine di ranking dedicato (come l'arco di energia), modulato per
  strategia (`StrategyProfile.genre_coherence`: le strategie esplorative lo riducono);
- classificazione transizioni;
- assegnazione ruoli nell'arco del set;
- candidate filtering con cap 60;
- gap analysis;
- discovery ranking;
- validazione output AI.

L'assenza di BPM/key non blocca il sistema: la traccia resta `imported` (non
usabile dal Set Builder finche' non arrivano da un import Rekordbox) e gli score
parziali usano valori neutri dove possibile.

## AI

L'AI puo':

- interpretare prompt liberi;
- proporre una direzione narrativa;
- spiegare scelte e transizioni;
- suggerire alternative creative;
- commentare candidati Discovery.

L'AI non puo':

- inventare track_id;
- inventare BPM/key/ISRC/fonti;
- selezionare tracce fuori dalle candidate ricevute;
- bypassare il Validation Engine;
- toccare BPM/key/energy.

Modalita' Set Builder:

- `technical`: prudente, basata sui dati forniti.
- `creative`: usa anche conoscenza musicale generale, ma resta vincolata a candidate e validazione.

## Internazionalizzazione (i18n IT/EN)

Cratory e' bilingue italiano/inglese. La lingua e' un'impostazione persistente
(chiave `language` in `AppState`, default `it`), scelta da un toggle in Impostazioni;
nessun routing per locale (app mono-utente, niente SEO). Endpoint `GET/PUT
/api/settings/language`.

Tre superfici, tre strategie:

- **UI frontend**: dizionario TypeScript fatto in casa in `frontend/lib/i18n/`.
  `en.ts` e' la fonte di verita' delle chiavi; `it.ts` e' tipizzato `: Dictionary`
  (`= typeof en`), cosi' una chiave mancante o in piu' e' errore di compilazione.
  `I18nProvider`/`useT()` espongono il dizionario attivo; `runtime.ts` tiene lo stato
  lingua accessibile fuori da React (usato da `lib/api.ts`) senza cicli di import.
- **Errori backend**: language-agnostic. Ogni `HTTPException` passa per
  `api_error(status, code, message, **params)` (`app/core/http_errors.py`) con `detail`
  strutturato `{code, message, params?}`; il frontend traduce il `code` dal namespace
  `errors` del dizionario (`translateApiError`), con `message` inglese come fallback.
- **Frasi generate + output AI**: prodotte dal backend direttamente nella lingua
  selezionata. Le etichette enum (es. classificazione transizione) restano codici
  tradotti dal frontend; le frasi composte (reason/mixing tip/overview in
  `services/scoring.py`, fasi dei job, testi dell'agente AI in `services/ai_agent.py`)
  escono da cataloghi per-lingua indicizzati da `get_language(db)` al punto d'ingresso.
  I prompt di sistema dell'AI restano in italiano come istruzioni al modello: solo la
  direttiva sulla lingua dell'output e' parametrica.

Limite noto: i `transition_reason` persistiti nel DB al momento della generazione del
set restano nella lingua attiva a quel momento (la lingua di visualizzazione futura non
e' nota alla generazione).

## Modello dati

Entita' principali:

- `Playlist`: playlist importata da Spotify o import manuale.
- `Track`: traccia della libreria, con identita' streaming, metadata editoriali,
  BPM/Camelot (da import Rekordbox), `energy` derivata e stato. Ownership file
  locale (indicizzazione `LIBRARY_ROOT`, acquisizione Soulseek o collegamento
  manuale link-file): `has_local_file`, `local_path`, `local_format`,
  `local_bitrate`, `audio_hash` (vedi "Disk-first"). Altri campi: `archived` (file
  finito nell'archivio delle scartate), `local_mtime`/`local_size` (scan
  incrementale), `last_download_outcome`/`last_download_reason` (coda "da
  sistemare" dei download).
- `playlist_tracks`: tabella associativa M2M (Playlist <-> Track) con `added_at`
  per-playlist. Un brano puo' appartenere a piu' playlist; l'import aggiunge
  membership senza sovrascrivere.
- `Setlist`: set generato, prompt, strategia, spiegazione globale, validazione e
  `owned_only` (garanzia "solo posseduti", vedi "Disk-first").
- `SetlistTrack`: posizione, ruolo, score, note di transizione, motivo AI e rischio.
- `SpotifyToken`: token OAuth Spotify persistiti per l'utente locale.
- `DjSet`: mix esterno identificato via Shazam, separato dalla libreria.
- `DjSetTrack`: traccia identificata dentro un `DjSet`.
- `AppState`: chiave-valore persistente per stato applicativo (es. `last_index_at`).

Campi legacy Rekordbox come beatgrid, cue, `rekordbox_track_id`, `play_count` e
`tonality` sono fuori modello. Non esiste piu' un motore di enrichment interno ne'
una cache di provider audio: `energy` e' un campo derivato (`services/energy`), non
un dato esterno cacheable. Sono stati rimossi anche gli ultimi residui
dell'enrichment legacy (i provider `LastFmTagProvider`, `MusicFeatureProvider`) e la
colonna inutilizzata `Track.release_date` (droppata con migrazione FK-safe). Le
colonne pre-M2M `Track.playlist_id`/`playlist_name` restano in schema — non sono
droppabili su SQLite per una FK baked-in su `playlist_id` — ma sono morte e vuote
(la membership vive su `playlist_tracks`).

## Integrazioni

| Integrazione | Stato | Note |
|---|---|---|
| Spotify | attiva | OAuth, import, resolver Discovery, export playlist |
| Last.fm | attiva | similarita' artisti/tracce per il Discovery (espansione playlist) |
| Discogs | attiva | crate digging Discovery "Scava" per genere/etichetta; funziona senza token, `DISCOGS_TOKEN` alza il rate limit |
| LLM | attiva se configurata | output strutturati e validati |
| Shazam | attiva se dipendenze presenti | ffmpeg, yt-dlp, shazamio; fingerprinting di mix esterni, non della libreria |
| slskd (Soulseek) | attiva se configurato | download via REST API; `SLSKD_URL`/`SLSKD_API_KEY`/`SLSKD_DOWNLOAD_DIR` |
| Rekordbox | manuale (via export XML) | fonte di BPM/key: `POST /api/rekordbox/import`; nessuna API/dipendenza esterna, solo parsing file |
| SoundCloud | attiva se dipendenze presenti | yt-dlp (estrazione flat, solo metadati, mai audio) per playlist/secret link e like; niente ISRC (non esposto), dedup su `platform_track_id`; sync sempre additivo (mai prune, a differenza di Spotify) |
| PostgreSQL | backlog | SQLite basta per mono-utente |

I provider esterni residui (Last.fm, Discogs, Spotify) servono **solo la
Discovery**: nessuno di loro fornisce piu' BPM/key/mood/energia. L'arricchimento
testuale dei metadati (titolo/artista/album/label/genere) e' di competenza di
Sortory, non di Cratory. Spotify `/recommendations` non deve essere usato: per
app nuove o in development mode puo' restituire 403/404.

## Persistenza e migrazioni

SQLite resta il database operativo:

```text
backend/data/djassistant.db
```

`ensure_schema()` crea tabelle e applica migrazioni idempotenti (incluse quelle
FK-safe che hanno droppato le colonne del vecchio motore di enrichment). Non c'e'
Alembic. Per cambio nome prodotto, non rinominare automaticamente il DB: pianificare
una migrazione o mantenere il path legacy per compatibilita'.
