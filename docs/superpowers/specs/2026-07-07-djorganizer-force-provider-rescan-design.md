# DjOrganizer — "Forza ricerca da provider": riclassificazione tracce già taggate

> Data: 2026-07-07 · Stato: design approvato, pronto per il plan.
> Estende la feature provider esistente ([[djorganizer-ai-genre-suggestions]] è l'AI;
> qui parliamo del provider MusicBrainz→Discogs). App in `main` @ `1130ffe`.

## 1. Contesto

Il flusso di arricchimento metadati (sia AI sia **provider** MusicBrainz→Discogs) è **guidato
dalle issue**: `POST /api/issues/provider-suggest` ([issues.py:206](../../../backend/app/routers/issues.py))
lavora **solo su issue `status == "open"`** di tipo `missing_required_tag` / `missing_metadata`
/ `dirty_genre`, e salta quelle già marcate `source:"provider"`.

Conseguenza: una traccia che ha **già un genere valido** non genera nessuna issue, quindi il
provider non ha niente su cui lavorarci. E dopo che l'utente ha **accettato e lanciato il
plan**, il genere viene scritto sul file → lo scan successivo non rileva più nessuna issue di
genere → cliccare "⇄ Suggerisci da provider" restituisce `0 file`.

Ma il caso d'uso reale di Luca è la **riorganizzazione/riclassificazione della libreria per
genere**: vuole poter **ri-cercare via provider anche sulle tracce che un genere ce l'hanno
già**, per proporre un genere (o album/label/anno) migliore/canonico. Oggi non è possibile:
non esiste nessun flag di *force*, né via UI né via API.

Questa feature aggiunge una **ricerca provider "per traccia"** (non "per issue"), on-demand,
filtrabile, che gira come job in background e produce proposte revisionabili nel flusso
esistente accept → PLAN → apply.

## 2. Scope

**Dentro:**
- Nuovo entry-point **per traccia**: interroga il provider su tracce `present` **a prescindere
  dal genere attuale**, filtrabile per **cartella** (prefisso path) e/o **genere attuale**.
- Campi **selezionabili per-run**: `genre`, `album`, `label`, `year` (default: solo `genre`).
  **Mai** `artist`/`title` (troppo rischioso sovrascriverli su tracce curate).
- **Fingerprint automatico** (AcoustID → `mbid`) sulle tracce senza `mbid`, prima del lookup,
  per massimizzare i match ad alta confidenza.
- **Due livelli di confidenza per-campo**, entrambi proposti (non si scarta nulla):
  `high` (MBID/ISRC esatto) e `text` (match testuale artista+titolo), distinti visivamente.
- Le proposte diventano issue sintetiche di **nuovo tipo `provider_override`** (`source:
  "provider"`, `status:"open"`), che confluiscono nel flusso esistente: revisione inline →
  accetta → PLAN → apply.
- Gira come **job in background** con progress (sullo stampo di [scan_job.py](../../../backend/app/services/scan_job.py)),
  **niente limite arbitrario** di righe.
- UI nella pagina ISSUES: pannello (cartella, genere, checkbox campi, bottone, barra di
  progresso); le issue `provider_override` mostrano **`vecchio valore → proposta` + badge di
  confidenza**; bottone **"accetta tutte le alta confidenza"** (bulk).

**Fuori:**
- Override di `artist`/`title`.
- Scrittura su disco senza revisione / auto-accettazione.
- Esecuzione automatica dentro lo scan.
- Job concorrenti multipli (resta il modello mono-job dell'app).
- Paginazione/coda persistente del job (stato in memoria come lo scan; YAGNI).

## 3. Design (approvato)

### 3.1 Job in background — `provider_rescan_job.py`
Nuovo modulo modellato su `scan_job.py`: **proprio** `_state` + `_lock` (indipendente dallo
scan, ma resta valido il vincolo mono-job dell'app — vedi §4), funzione `_run()` in un thread
daemon, `on_progress(processed, total, phase)`, `job_state()` per il polling.

Parametri del job: `{folder: str|None, genre: str|None, fields: list[str]}`.

Fasi (`phase`): `"fingerprinting"` → `"looking_up"` → done. Lo `_state` espone anche il
`result` finale (§3.3).

### 3.2 Endpoint
- `POST /api/issues/provider-rescan` body `{folder?, genre?, fields?}` → avvia il job; se un job
  è già `running` fa **echo dello stato** senza ripartire (HTTP 200, come `scan_job.start_job`).
  `fields` default `["genre"]`; valori ammessi `{"genre","album","label","year"}` (validati;
  artist/title rifiutati con 422).
- `GET /api/issues/provider-rescan/status` → `job_state()` (polling), stessa forma dello scan.
- Se MusicBrainz non configurato → `result` con `configured:false` e nessuna proposta.

### 3.3 Logica per traccia (nel job)
Selezione: `AudioFile.status == "present"`, filtrata per `folder` (**match substring
case-insensitive** su `AudioFile.path`, così basta digitare un nome di sottocartella) e/o
`genre` (genere attuale == valore esatto). Poi, per ogni traccia:

1. **Fingerprint auto:** se `AudioFile.mbid` è vuoto e AcoustID+fpcalc sono configurati →
   fingerprint per popolare `mbid`. Se AcoustID/fpcalc **non** configurati → si salta il
   fingerprint e si processa la traccia solo se ha già `mbid`/ISRC; le tracce senza identità
   forte vengono **contate** in `result.skipped_no_id` (niente troncamento silenzioso).
2. **Lookup provider:** MusicBrainz (via `mbid`/ISRC, o testuale artista+titolo se manca) →
   Discogs per i campi mancanti (tipicamente `label`/`genre`). Riusa `text_providers.lookup()`
   e le integrazioni esistenti.
3. **Confidenza per-campo:** ogni campo proposto porta la confidenza con cui è stato ottenuto:
   - campo da MusicBrainz con match **MBID o ISRC esatto** → `high`;
   - campo da MusicBrainz con match **testuale** → `text`;
   - campo da **Discogs** (ricerca sempre testuale per "artista titolo") → `text`.
4. **Upsert delle proposte:** per ogni campo richiesto in `fields`:
   - se `valore_provider` è valorizzato **e** `!= valore_attuale` sul file **e** non esiste già
     un'issue **Inspector aperta** sullo stesso `(file, field)` (per non duplicare/collidere col
     flusso normale) → **upsert** issue `provider_override`:
     `suggested_fix_json = {"field", "action":"retag", "to", "source":"provider",
     "confidence": "high"|"text"}`, `status:"open"`. Se esiste già un `provider_override`
     **aperto** per quel `(file, field)` → si aggiorna `to`/`confidence`/`updated_at`.
   - se `valore_provider == valore_attuale` (il provider conferma) **oppure** nessun match, e
     esiste un `provider_override` **aperto** stantìo per quel `(file, field)` → lo si
     **elimina** (proposta non più necessaria).
   - i `provider_override` già `accepted`/`dismissed` **non si toccano** (decisione utente).

`result` finale: `{configured, scanned, fingerprinted, matched, proposed_high, proposed_text,
skipped_no_id, unresolved}`.

### 3.4 Nuovo tipo issue `provider_override`
- Aggiunto ai valori ammessi di `Issue.type`. Campo `field` ∈ `{genre,album,label,year}`.
- **Escluso dallo sweep di cancellazione** di `_merge_issues`
  ([analysis.py:35](../../../backend/app/services/analysis.py)): il loop finale che elimina le
  issue non ricalcolate dall'Inspector **deve saltare** le issue di tipo `provider_override`
  (l'Inspector non le produce mai; sono gestite solo dal job di rescan). Senza questa esclusione
  un normale re-scan cancellerebbe gli override pendenti.
- Il **planner non cambia**: `effective_tags`/`build_plan` usano `suggested_fix_json` a
  prescindere dal `type`, e `genre/album/label/year` sono già in `_EFFECTIVE_FIELDS`
  ([planner.py:8](../../../backend/app/services/planner.py)). Il filtro no-op esistente
  ([planner.py:103](../../../backend/app/services/planner.py)) scarta automaticamente i RETAG
  dove il valore coincide col file.

### 3.5 Frontend (pagina ISSUES)
- `lib/api.ts`: `providerRescan(params)` → `POST /api/issues/provider-rescan`;
  `providerRescanStatus()` → `GET .../status`.
- **Pannello "Forza ricerca provider":** input **cartella**, dropdown **genere attuale** (dai
  generi distinti presenti), **checkbox campi** (genere/album/label/anno, genere pre-spuntato),
  bottone **"⇄ Forza ricerca provider"**. Durante il job: **barra di progresso** con
  `phase`/`processed`/`total` (polling di `/status`, come lo scan). A fine job: nota riassuntiva
  dal `result` (es. *"58 proposte: 34 alta confidenza, 24 testuali; 12 tracce senza identità"*).
- **Rendering delle issue `provider_override`:** badge **"override"**, riga **`vecchio → proposta`**
  per il campo, e **badge di confidenza** distinto (es. verde "alta" / ambra "testuale"). Da lì
  si accettano col flusso esistente (`✓` → `/fix` → PLAN).
- **Bulk "accetta tutte le alta confidenza":** bottone che accetta in un colpo tutte le
  `provider_override` `open` con `confidence == "high"` (chiamate `/fix` in serie o un endpoint
  bulk dedicato — decisione lasciata al plan), lasciando da rivedere a mano le `text`.

## 4. Errori, edge case, resilienza

- **Provider non configurato** (MusicBrainz user-agent assente) → `result.configured:false`,
  nessuna proposta, nessun crash.
- **AcoustID/fpcalc assenti** → nessun fingerprint; si processano solo tracce con `mbid`/ISRC
  già presenti; le altre in `skipped_no_id` (riportate in UI).
- **Nessun match** per una traccia → nessuna proposta; eventuali override aperti stantìi puliti.
- **Il provider conferma il valore attuale** → nessuna issue (o pulizia di quella stantìa) → e
  comunque il planner scarterebbe il no-op.
- **Re-run idempotente:** aggiorna/pulisce i propri `provider_override` aperti; non tocca gli
  accettati/dismessi.
- **Re-scan non distruttivo:** `_merge_issues` preserva i `provider_override` (esclusione dallo
  sweep). *Nota:* un `provider_override` accettato-e-applicato che l'utente non ri-scansiona
  resta in storico come `accepted` (stesso comportamento delle issue normali oggi); un rescan
  successivo lo elimina perché il provider confermerebbe il valore ormai scritto.
- **Mono-job:** se uno scan o un altro rescan è `running`, il nuovo avvio fa echo dello stato
  senza partire (come lo scan). Fingerprint/lookup rispettano i rate-limit già esistenti nelle
  integrazioni.
- **Rate-limit/durata:** nessun limite di righe; il filtro cartella/genere è la leva per tenere
  i batch gestibili. Il job in background evita il timeout HTTP.

## 5. Test

- **Backend (pytest, provider e AcoustID mockati):**
  - filtro `folder`/`genre` seleziona il set giusto di tracce `present`;
  - fingerprint auto invocato solo per tracce senza `mbid` (e saltato se AcoustID non config,
    con `skipped_no_id` corretto);
  - confidenza per-campo: `high` da match MBID/ISRC, `text` da MusicBrainz testuale e da Discogs;
  - upsert `provider_override` **solo** dove `provider != attuale`; skip del campo se c'è già
    un'issue Inspector aperta su quel `(file,field)`; delete dell'override stantìo quando il
    provider conferma / non matcha; override `accepted` non toccati;
  - `_merge_issues` **preserva** i `provider_override` dopo un `recompute`;
  - planner: `provider_override` → RETAG corretto sui 4 campi; no-op scartato;
  - endpoint start/status; `configured:false` senza MusicBrainz; validazione `fields` (rifiuta
    artist/title). Output pristine (`filterwarnings = error`).
- **Frontend:** `npm run lint` + `npm run build` verdi.

## 6. Convenzioni & DoD

- Backend: router sottile, job isolato/mockabile (come `scan_job`), Pydantic per i body,
  filtri JSON in Python secondo convenzione, test pristine.
- **DoD:** `pytest` verde (provider/AcoustID mockati); lint+build verdi. Con provider
  configurato: "Forza ricerca provider" (con filtro cartella/genere e campi scelti) gira in
  background con progress e crea issue `provider_override` **anche su tracce già taggate**, con
  `vecchio → proposta` e badge di confidenza; il bulk accetta tutte le `high`; le proposte si
  accettano col flusso esistente → PLAN → apply; un re-scan **non** cancella gli override
  pendenti; senza provider/AcoustID nessun crash e conteggi espliciti; artista/titolo mai
  toccati.
