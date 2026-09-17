# Set Builder — banco di preparazione del DJ, su un solo modello

Data: 2026-09-16 (riscrive la bozza del 2026-09-15). Stato: design approvato in
conversazione, implementazione non iniziata.

## In due parole

Oggi il Set Builder genera un set da solo e poi lascia ritoccarlo. Non è mai
stato davvero utile. Da ora il set lo prepara il DJ: parte da una playlist,
mette in fila le tracce, le ascolta, scrive appunti, tiene riserve, lascia buchi
da riempire dopo e ritrova tutto il giorno dopo. Nessuna AI.

Il set che esiste già nell'app (`Setlist`) resta l'unico tipo di set. Gli si
aggiungono le cose che mancano: buchi, sequenze, alternative, riserve, appunti,
"provato", annulla. Il generatore non sparisce e non resta in un angolo: diventa
un bottone dentro il set, "riempi questo buco", che propone e non decide.

Non si fa nessun lavoro per i set generati in passato: ce n'è uno, di prova, e
si può cancellare.

## 1. Decisioni

- **Un solo modello.** `Setlist` e `SetlistTrack` ospitano sia i set generati
  (quelli di ieri) sia i set preparati a mano (quelli di domani). Una sola
  lista, una sola pagina di dettaglio, una sola catena di export, un solo ciclo
  di vita delle tracce. Nessuna tabella `SetProject`.
- **Il DJ decide.** Nessun ordinamento imposto, nessun ruolo assegnato, nessuna
  intenzione dedotta. La compatibilità tecnica (BPM, tonalità) si mostra come
  dato, separata dal giudizio personale.
- **Niente AI nel banco.** Il flusso nuovo funziona senza chiave e senza
  chiamate. La curatela AI attuale se ne va con il vecchio form (tappa 6).
- **Il generatore è uno strumento del banco.** "Riempi il varco" chiama il
  motore deterministico esistente sul tratto tra due tracce scelte dal DJ, con
  un numero di slot fisso. Il risultato entra come proposta modificabile.
- **Materiale = playlist aggiornata.** Il set tiene un riferimento alla playlist
  di origine e la legge com'è ora. Le tracce già nel set restano nel set anche
  se la playlist le perde. Si può aggiungere qualunque traccia dalla libreria.
- **Salvataggio immediato e annulla.** Ogni gesto strutturale è una transazione
  che salva anche uno snapshot; annulla e ripeti ripristinano la struttura.
- **Set esistenti: nessuna compatibilità da costruire.** Le righe esistenti
  ricevono `kind = generated` e basta. Nessuna azione "apri una copia".

### Cosa cambia rispetto alla bozza del 2026-09-15

| Bozza | Ora | Perché |
|---|---|---|
| 7 tabelle nuove `SetProject*` | `Setlist` estesa + 4 tabelle piccole | Un mondo solo: cleanup, merge, backup, export già funzionano |
| Materiale copiato dalla playlist | Riferimento alla playlist, letta aggiornata | Niente membership da gestire nel merge |
| Endpoint comandi con union tipizzata, `operation_id` | Un endpoint per gesto, come l'editor attuale | App locale mono-utente, niente retry da deduplicare |
| Destinazione live/registrazione | Rimossa dalla v1 | Cambiava solo etichette |
| Generatore in pagina secondaria per sempre | Generatore come "riempi il varco" | Un solo prodotto da mantenere |
| Rigenerazione di parti del set fuori perimetro | È la tappa 6 | Con un modello solo costa poco |
| Primo uso alla tappa 3 | Primo uso alla tappa 1 | Si prova il gesto base prima di costruire il resto |

### Fuori dalla prima versione

Mixaggio, beatmatch, waveform, cue, analisi delle frasi, ascolto automatico
delle transizioni, scoring del gusto, apprendimento delle preferenze, stima
automatica della durata mixata, alternative a sequenze intere, riuso di
sequenze tra set, confronto tra versioni, chat AI. Le note sono del set e non
scrivono mai tag nei file.

## 2. Esperienza

### La pagina del set

| Zona | Cosa c'è |
|---|---|
| Materiale | Le tracce della playlist di origine, aggiornate, più ricerca nella libreria. Filtri: testo, su disco, usata/non usata, BPM, tonalità. Ascolto. Le tracce già nel set sono riconoscibili. |
| Percorso | Le sequenze in ordine, con le tracce e i varchi. Sotto, il banco: sequenze non ancora inserite. Spostare, raggruppare, separare. |
| Dettaglio | Della traccia o del passaggio selezionato: appunti, alternative, dati tecnici, stato "da provare / provato". |
| Player | Quello esistente, docked, indipendente dalla selezione. |

Design system di `docs/DESIGN.md`. Su finestra stretta materiale e dettaglio
diventano pannelli apribili; il percorso resta sempre raggiungibile; nulla copre
il player. Ogni azione ha un equivalente senza drag.

### I gesti

1. **Mettere in fila.** Dal materiale al percorso o al banco. L'ordine iniziale
   è quello della selezione.
2. **Fare sequenze.** Raggruppare tracce contigue, dare un nome, spostare il
   gruppo intero, separarlo senza perdere l'ordine. Nessun gruppo dentro un
   gruppo.
3. **Lasciare un varco.** Un buco tra due tracce, con un appunto. Non è una
   traccia e non viene riempito da solo.
4. **Tenere alternative.** Più candidate su uno stesso punto; una è attiva.
   Confronto compatto di 2–4, ascolto una alla volta. La scelta precedente
   resta tra le alternative.
5. **Riserve.** Tracce messe da parte per la serata, non nel percorso.
6. **Appunti e "provato".** Note su tracce e passaggi. Un passaggio si segna
   "da provare" o "provato" a mano: ascoltarlo nell'app non conta.
7. **Annulla e ripeti.** Sulla struttura. Riavviare l'app non perde nulla.
8. **Riempi il varco** (tappa 6). Il generatore propone N tracce tra le due ai
   lati del varco; si accetta, si modifica o si scarta.

Togliere una traccia dal percorso la lascia nel materiale. Spostare una sequenza
sul banco non la elimina. Nessun effetto sui file audio, mai.

### Ascolto e confronto

Player unico esistente con un contesto esplicito: i candidati in confronto,
oppure la sequenza selezionata. Cambiare filtri o selezione non cambia ciò che
sta suonando. Nessun autoplay al cambio selezione. File mancante: visibile, mai
saltato in silenzio.

Compatibilità tecnica tra vicini: BPM e tonalità mostrati per i due lati, con
"sconosciuto" quando manca un dato. Nessuna etichetta "mix sicuro", nessuna
"più morbida" dedotta dal solo tempo. Ordinare il materiale per compatibilità
con i vicini di un punto è facoltativo e dichiara su cosa si basa.

## 3. Modello dati

Tutto su `backend/app/models.py`, migrato da `ensure_schema` (colonne nuove con
`ALTER TABLE`, tabelle nuove con `create_all`). Le righe esistenti ricevono i
default.

### Colonne aggiunte

| Tabella | Colonna | Uso |
|---|---|---|
| `Setlist` | `kind` `generated`/`manual`, default `generated` | I set a mano non ricevono ruoli né riassegnazioni |
| `Setlist` | `source_playlist_id` FK nullable | La playlist di origine, letta aggiornata; azzerata da `delete_playlist` |
| `Setlist` | `notes` text | Appunti del set |
| `Setlist` | `revision` int, default 0 | Controllo di concorrenza e cursore annulla |
| `SetlistTrack` | `track_id` diventa nullable | Un varco è una riga senza traccia |
| `SetlistTrack` | `slot_kind` `track`/`gap`, default `track` | |
| `SetlistTrack` | `block_id` FK nullable | La sequenza; `NULL` = riserva |
| `SetlistTrack` | `note` text | Appunto sulla traccia in quel punto |
| `SetlistTrack` | `planned_seconds` int nullable | Contributo netto alla durata (tappa 5) |
| `SetlistTrack` | `play_bpm` float nullable | "La suono a": il tempo a cui il DJ suonerà la traccia in questo set. Non tocca `Track.bpm` (tappa 4) |

`position` resta, ma diventa la posizione **dentro il blocco** (o dentro la
riserva, per le righe con `block_id NULL`). I set `generated` non usano blocchi:
per loro `block_id` è sempre `NULL` e il percorso è l'ordine delle righe, come
oggi. È una lettura dipendente da `kind`, accettabile perché quei set spariscono
con la tappa 6.

Rendere `track_id` nullable richiede una ricostruzione una tantum di
`setlist_tracks` (SQLite non cambia la nullabilità con `ALTER`): stesso pattern
di rebuild con `RENAME` già usato in `db.py`, eseguito prima di creare
`setlist_alternatives`, che referenzia `setlist_tracks.id`.

### Tabelle nuove

| Tabella | Campi | Note |
|---|---|---|
| `SetlistBlock` | id, setlist_id, name nullable, placement `main`/`bench`, position | La sequenza. Posizioni contigue per placement |
| `SetlistAlternative` | id, setlist_track_id, track_id, position, note | Candidate su uno slot; l'attiva è `SetlistTrack.track_id` |
| `SetlistPairNote` | id, setlist_id, from_track_id, to_track_id, state `unreviewed`/`to_try`/`tried`, note | Giudizio su una coppia precisa di tracce, indipendente dalla posizione |
| `SetlistRevision` | id, setlist_id, seq, snapshot JSON, created_at | Snapshot completo della struttura; ultimi 50 |

`SetlistPairNote` risolve da sola la regola "il giudizio non si trasferisce":
se dopo A viene C, la coppia A→C non ha riga e si mostra "da valutare"; se si
rimette B, la riga A→B torna visibile. Nessun trasferimento, nessuna perdita.

### Regole

- Un set a mano può essere vuoto. La pulizia legacy di `db.py` che elimina i
  `setlists` senza righe viene limitata a `kind = generated`.
- Uno slot `track` ha sempre la traccia. Se il file sparisce, lo slot resta e
  si mostra "non disponibile". L'indicizzazione non cancella mai una decisione.
- Un varco non ha traccia. Scegliere una candidata lo trasforma in `track`
  mantenendo id e appunto. Finché è aperto, le tracce ai suoi lati non sono
  vicine: nessuna compatibilità calcolata tra loro.
- Una traccia compare al più una volta nel percorso principale. Può stare su
  più tentativi sul banco, tra le alternative di più punti, o in riserva.
  Scegliere una traccia già attiva altrove segnala il conflitto.
- I set a mano non passano da `assign_roles`, `_reassign_roles`, né
  dall'`ai_reason`. I campi restano `NULL`.
- La compatibilità tecnica usa `score_transition` sui metadati correnti; con
  BPM o tonalità mancanti si mostra "sconosciuto", non il punteggio neutro.
  Lo scostamento di tempo si mostra come percentuale ("124 → 123, −0,8 %"),
  cioè quanto pitch serve, non come differenza secca. Se una riga ha
  `play_bpm`, i vicini si valutano su quel valore invece che su `Track.bpm`.
- Il ciclo di vita esistente (cleanup, merge, dedup, backup) conosce già
  `setlist_tracks`; vanno aggiunte `setlist_alternatives` e `setlist_pair_notes`
  ai punti che spostano o cancellano tracce (`merge_tracks`, cleanup,
  `tools/clean_user_data.py`), più le nuove tabelle nel backup.

### Salvataggio, annulla, concorrenza

Ogni endpoint che cambia la struttura: valida, muta, incrementa `revision`,
scrive uno snapshot in `SetlistRevision`, nella stessa transazione. Il client
manda `expected_revision`; se non coincide, 409 e ricarica. Annulla ripristina
lo snapshot precedente e sposta il cursore; una nuova modifica dopo annulla
scarta il ramo "ripeti". Le note si salvano al blur con stato visibile
("Salvataggio / Salvato / Errore") e non producono una revisione per carattere:
edit consecutivi della stessa nota si accorpano. Nessuna cronologia per
selezione, filtri, playback.

## 4. API

Stesso router `backend/app/routers/sets.py`, stesso `SetlistOut` esteso con
`kind`, `source_playlist_id`, `revision`, `blocks`, riserve e, per riga, `id`,
`slot_kind`, `block_id`, `note`, `alternatives`, `pair_note`. Gli endpoint nuovi
identificano le righe **per id**, non per posizione. Errori con `api_error`,
testi nei dizionari frontend.

| Endpoint | Cosa fa |
|---|---|
| `POST /api/sets/manual` | Crea un set a mano, vuoto o da playlist |
| `GET /api/sets/{id}/material` | Playlist aggiornata + ricerca libreria, filtri, flag "già nel set" |
| `POST /api/sets/{id}/rows` | Inserisce tracce o un varco in un blocco o in riserva |
| `PATCH /api/sets/{id}/rows/{row_id}` | Appunto, `planned_seconds`, traccia attiva |
| `POST /api/sets/{id}/rows/{row_id}/move` | Sposta in un blocco/posizione |
| `DELETE /api/sets/{id}/rows/{row_id}` | Toglie la riga |
| `POST /api/sets/{id}/blocks`, `PATCH`, `DELETE`, `.../move`, `.../split` | Sequenze |
| `POST /api/sets/{id}/rows/{row_id}/alternatives`, `DELETE .../{alt_id}` | Candidate |
| `PUT /api/sets/{id}/pair-notes` | Stato e appunto di una coppia |
| `POST /api/sets/{id}/undo`, `/redo` | Con `expected_revision` |
| `POST /api/sets/{id}/fill-gap` | Tappa 6: propone N tracce per un varco |
| `POST /api/sets/{id}/export` (esistente) | Legge il percorso risolto |

Il **percorso risolto** è la proiezione usata da export, durata e compatibilità:
blocchi `main` in ordine, sole righe `track` con la traccia attiva, i varchi
interrompono l'adiacenza. Banco, alternative e riserve non ci entrano.

## 5. Tappe

Ogni tappa arriva con i suoi test (TDD, suite `backend/tests/test_set_manual_*.py`
e `frontend/tests/set-builder-*.test.tsx`) ed è usabile da sola.

### Tappa 1 — Il gesto base

- Colonne e `SetlistBlock`; `kind`; pulizia legacy limitata ai generati.
- `POST /api/sets/manual` da playlist; `material`; `rows` inserisci, sposta,
  togli, appunto; varco. Un blocco `main` implicito creato al primo inserimento.
- `revision` con 409 fin da ora.
- Pagina nuova `frontend/app/sets/manual/page.tsx?id=…` con materiale, percorso
  e dettaglio; player esistente. `/set-builder` offre "Prepara un set" accanto
  al form attuale, che non si tocca.

**Verifica:** da una playlist creo un set, metto in fila tre tracce, sposto,
scrivo un appunto, lascio un varco, riavvio e ritrovo tutto. Tolgo una traccia
dalla playlist: sparisce dal materiale, resta nel set. Traccia senza BPM
inseribile.

### Tappa 2 — Alternative, riserve, confronto

- `SetlistAlternative`; scelta dell'attiva con conservazione della precedente.
- Riserve (`block_id NULL`) e filtro "in riserva" nel materiale.
- Confronto 2–4 con dati tecnici e "sconosciuto"; contesto di ascolto esplicito.

**Verifica:** confronto tre tracce, scelgo la seconda, ricarico e ritrovo le
altre due. Cambio filtri mentre suona: il player non cambia.

### Tappa 3 — Sequenze, banco, annulla

- Raggruppa, nomina, sposta, separa; banco `bench`; comandi da tastiera e menu.
- `SetlistRevision`, undo/redo, limite 50.

**Verifica:** due sequenze, ne sposto una sul banco, la separo, annullo fino
all'inizio, ricarico e ripeto. Un comando fallito non lascia metà spostamento.

### Tappa 4 — Passaggi

- `SetlistPairNote`: stato e appunto per coppia; filtro "da provare".
- Compatibilità tecnica per coppia, separata dal giudizio, con dati mancanti
  dichiarati e scostamento di tempo in percentuale.
- Campo "la suono a" (`play_bpm`) per riga: facoltativo, usato al posto del
  BPM della traccia nella valutazione dei vicini; il cambio di tonalità da
  pitch resta fuori.

**Verifica:** segno A→B provato; sostituisco B con C: A→C è da valutare;
rimetto B e ritrovo stato e appunto di A→B.

### Tappa 5 — Durata ed export

- Somma dei file e durata pianificata da `planned_seconds`; "stima incompleta"
  se manca un valore o c'è un varco aperto.
- Export esistenti (M3U8, CSV, MD, Spotify) sul percorso risolto; scheda di
  preparazione MD con sequenze, alternative, appunti, stati, varchi; export
  "Riserve". Anteprima uguale al file prodotto; file mancanti visibili.

**Verifica:** con alternative, riserve, banco, varco e un file sparito,
l'anteprima coincide con ciò che esporto.

### Tappa 6 — Il generatore come strumento

- `fill-gap`: `_beam_search_span` con opener = traccia prima del varco,
  `converge_to` = traccia dopo, stop a conteggio (nuovo parametro accanto a
  quello a secondi), pool = materiale meno le tracce già nel percorso. Le
  proposte entrano nel varco come righe normali, modificabili.
- Il vecchio form di generazione e la curatela AI vengono rimossi:
  `ai_curation.py`, il ramo AI del job, `curation`, `mood_tags`, `ai_reason`,
  la pagina `set-builder` diventa la lista dei set con "Prepara un set".
  I set `generated` esistenti si possono cancellare; nessuna conversione.

**Verifica:** varco da tre slot tra due tracce bloccate, la proposta rispetta
i vicini e il numero; la scarto e il varco torna aperto. Chiave AI assente o
presente: nessuna chiamata.

### Tappa 7 — Documentazione e verifica integrata

- README, `docs/ARCHITECTURE.md`, `docs/API.md`, `docs/DESIGN.md`,
  `docs/ROADMAP.md`, `PROGRESS.md`, `CLAUDE.md` (regola 1: il DJ costruisce, il
  motore propone su richiesta; nessuna AI nel Set Builder).
- E2E `frontend/e2e/set-builder.spec.ts`: un percorso completo da playlist a
  export. Suite backend e unit frontend complete.

Comandi:

```bash
cd backend
.venv/bin/python -m pytest tests -q
```

```bash
cd frontend
npm run test:unit
npm run test:e2e -- set-builder.spec.ts
npm run lint
npm run build
```

## 6. Criteri di riuscita

Con una playlist di circa 80 tracce e un obiettivo di 90 minuti:

1. Costruire due sequenze senza impostare alcun arco.
2. Lasciare un varco e conservare due alternative.
3. Cambiare ordine, ascoltare, annullare senza perdere lavoro.
4. Riaprire il giorno dopo e capire subito cosa è deciso e cosa resta da provare.
5. Ottenere scaletta e riserve senza AI né servizi esterni.

Il segnale utile è dove il DJ deve ancora ricorrere a playlist duplicate o
appunti esterni. Il punteggio tecnico medio non misura nulla.

## 7. Dopo la prima versione, solo se serve

- **Ascolto a due deck**, cantiere a sé con la sua spec, da aprire quando il
  banco è alla tappa 4 e ci sono passaggi veri da provare. Deciso il
  2026-09-17: o questo o niente, quindi in v1 non entrano né un cursore di
  tempo sul player né l'"ascolto della cucitura". Il minimo che avrebbe senso:
  griglia dei battiti dal nodo `TEMPO` dell'XML Rekordbox (oggi ignorato) e dai
  battiti che Essentia già calcola (oggi scartati); due deck su Web Audio con
  tempo allineato, partenza sull'inizio di frase, volume e taglio bassi per
  deck, "sposta di un battito"; nessuna waveform, cue o loop. Rischio dichiarato:
  la china verso un deck completo.
- Alternative a sequenze intere: un blocco sul banco marcato come alternativa
  di un blocco `main`. Confronto tra due revisioni: gli snapshot sono già
  completi.
- Copiare una sequenza da un altro set, con provenienza; si lega alla memoria
  d'uso (cantiere 1 della roadmap).
- AI su un problema osservato nell'uso: critica del set fatto, note di mix sui
  passaggi rischiosi, alternative spiegate. Nessun ruolo preassegnato.
