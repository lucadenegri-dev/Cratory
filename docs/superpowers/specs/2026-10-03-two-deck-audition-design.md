# Ascolto a due deck — provare un passaggio dentro il banco

Data: 2026-10-03. Stato: design approvato in conversazione, implementazione non
iniziata. Nasce dal rinvio deciso il 2026-09-17 nella spec del banco
(`2026-09-15-set-builder-workbench.md`, sezione 7), che prevedeva due deck
senza waveform, cue e loop. Questa spec allarga quel perimetro, per decisione
dell'utente: entrano waveform e memory cue. Restano fuori loop, EQ a tre
bande, cuffia e qualunque uso dei deck fuori dal banco.

## In due parole

Nel banco (`/sets/manual`), su un passaggio fra due righe vicine, un pulsante
"Prova il passaggio" apre un pannello fisso in basso con due deck: la traccia
di partenza sul deck A, quella d'arrivo sul deck B. Ogni deck ha waveform con
griglia dei battiti e cue, trasporto, pitch con master tempo, volume e taglio
bassi. Un pulsante di sync allinea tempo e fase. Le cue si creano nel deck e si
salvano in Cratory, per traccia. La griglia dei battiti la calcola Essentia in
casa. Nulla di tutto questo entra o esce da Rekordbox.

È un'eccezione dichiarata e circoscritta alla regola "Cratory prepara, non
suona": serve a decidere se un passaggio funziona, non a suonare un set. Il
rischio già scritto nella spec del banco, la china verso un deck completo,
resta vero e va tenuto d'occhio a ogni richiesta successiva.

## 1. Decisioni

- **I deck vivono nel banco.** Si aprono solo da un passaggio del percorso,
  entrante o uscente, nel pannello del dettaglio. Niente pagina Deck a sé,
  niente caricamento di tracce qualsiasi. Solo tracce possedute
  (`has_local_file`).
- **Griglia autonoma.** I battiti vengono da Essentia (`RhythmExtractor2013`,
  che li calcola già e oggi li scarta), ridotti a una griglia a tempo costante:
  istante del primo battito e BPM della griglia. Il nodo `TEMPO` dell'XML
  Rekordbox resta ignorato, per scelta dell'utente. Niente battuta uno, niente
  cambi di tempo, niente editor di griglia.
- **La regola 2 non si tocca.** `Track.bpm` e `camelot_key` continuano a
  venire da Rekordbox, dall'analisi applicata o dalla mano dell'utente. La
  griglia è un dato derivato che serve solo ai deck, come `energy`. Nessun
  codice dei deck scrive `bpm`, `key` o le loro provenienze.
- **Cue solo in Cratory.** Create nel deck, salvate per traccia, massimo dieci
  come le memory cue di Rekordbox così un export futuro non deve tagliare.
  Nessun import delle cue di Rekordbox, nessun export: l'export via XML
  richiederebbe l'import a due passi in Rekordbox (dalla 5.6.1 non aggiorna le
  tracce già in collezione) e l'utente ha scelto di non affrontarlo ora.
- **Materiale già collaudato, non codice nostro.** wavesurfer.js v7 per
  waveform, zoom, cursore e marker; `playbackRate` e `preservesPitch` del
  browser per il tempo e il master tempo; Web Audio per volume e taglio bassi;
  ffmpeg e numpy, già presenti, per i picchi; Essentia, già presente, per i
  battiti. Nessuna decodifica dei file in memoria nel frontend.
- **Due media element, non precisione al campione.** Il sync fra due `<audio>`
  è preciso a qualche millisecondo. Basta per giudicare un passaggio. Il deck
  misura e mostra lo scarto di fase, offre "riallinea" e spinte manuali, e non
  corregge mai da solo.
- **Un solo padrone del fondo pagina.** Quando i deck si aprono il player
  docked si ferma e si nasconde. Un play normale altrove chiude i deck.
- **Niente scorciatoie da tastiera, niente loop, niente cuffia** nella prima
  versione.

## 2. Esperienza

### Apertura

In ogni `TransitionPanel` del dettaglio, entrante e uscente, un pulsante
"Prova il passaggio". Attivo solo se entrambe le tracce hanno il file locale;
altrimenti disabilitato, con il motivo nel titolo. Al click la pagina del
banco monta il dock con la traccia di partenza sul deck A e quella d'arrivo
sul deck B. Il rate iniziale di ogni deck è `play_bpm / bpm` se la riga ha
"la suono a", altrimenti 1. Il deck suona subito, in streaming; waveform e
griglia arrivano quando pronte.

### Il dock

Pannello fisso in basso, lo stesso telaio del player docked: stessa posizione,
stessi confini di colonna da `lg` in su, altezza pubblicata in
`--player-bar-height` così il banco non resta coperto. Il banco rimane visibile
sopra, perché dopo l'ascolto si scrive l'appunto del passaggio nel pannello
che c'è già.

Disposizione scelta a mockup (`.superpowers/brainstorm/…/deck-layout-v4.html`,
non versionato): **deck impilati**, waveform a tutta larghezza una sopra
l'altra, stesso cursore fisso al centro e stesso zoom per entrambe, come
Rekordbox, Serato e Traktor in orizzontale. Il motivo è vedere a occhio se i
battiti coincidono.

Ogni deck è una riga a due colonne:

- **Blocco a sinistra**, circa 270 px: etichetta del deck, titolo, artista,
  tonalità; play/pausa con tempo trascorso e residuo; BPM effettivo in grande
  con la percentuale di pitch e l'interruttore del master tempo; poi il cursore
  del pitch con il selettore della corsa (±8 % o ±16 %), il fader del volume
  con l'interruttore del taglio bassi, il pulsante "Sync su B" (su A per il
  deck B) e "Usa come la suono a".
- **A destra**: striscia panoramica (plugin Minimap), waveform zoomata con i
  battiti sul canvas e i marker delle cue (plugin Regions), click per
  spostarsi; sotto, le chip delle cue, "metti cue" con l'interruttore "al
  battito", e in fondo a destra i salti di un battito avanti e indietro e le
  spinte di ±10 ms.

Sotto i due deck una striscia condivisa: scarto di fase in millisecondi con
segno, "Riallinea", zoom − e +.

In alto a destra due comandi: "nascondi pitch e volume", che toglie da entrambi
i blocchi a sinistra pitch, volume, taglio bassi, sync e "la suono a" e abbassa
il pannello da circa 330 a circa 240 px, ricordato in `localStorage`; e la ✕
che chiude il dock e mette in pausa entrambi i deck.

### I gesti

- **Play/pausa** per deck. **Click sulla waveform** sposta la posizione.
- **Cue**: click su una chip salta alla cue; in riproduzione continua da lì,
  da fermo si posiziona. Una matita rinomina in linea, la × elimina. "Metti
  cue" salva la posizione corrente; con "al battito" acceso, e griglia
  presente, la arrotonda al battito più vicino. Oltre la decima il pulsante si
  disabilita.
- **Pitch**: cursore continuo nella corsa scelta, doppio click azzera. Il
  master tempo (`preservesPitch`) è acceso di default.
- **Sync su X**: questo deck adotta tempo e fase dell'altro. Il rate si
  calcola sui BPM delle griglie quando entrambe esistono, sui BPM nominali di
  `Track` altrimenti; la fase si allinea spostando `currentTime` di questo deck
  di al più mezzo battito. Senza griglia su uno dei due, solo il rate, e il
  deck lo dice. Il deck sincronizzato resta "schiavo" finché non si tocca il
  suo pitch: "Riallinea" agisce su di lui, e senza schiavo è disabilitato.
- **Salto di un battito** avanti e indietro (con griglia; senza griglia salta
  di `60 / bpm` nominale). **Spinte** di ±10 ms sempre disponibili.
- **Usa come la suono a**: scrive il BPM effettivo (nominale × rate, due
  decimali) nel `play_bpm` della riga da cui il deck è stato caricato, con la
  stessa chiamata del dettaglio. Unico dato che l'ascolto scrive nel set.

### Stati di attesa ed errori visibili

Testi di stato al posto di waveform o griglia finché mancano: "waveform in
calcolo", "griglia in calcolo", "analisi di massa in corso, attendo", "griglia
non disponibile: <motivo>" (motore assente, griglia incerta, errore). Senza
griglia restano attivi trasporto, cue, pitch, volume e sync del solo rate.

Se il BPM della griglia e quello nominale di `Track` differiscono oltre l'1 %,
dopo aver provato il doppio e la metà, l'intestazione del deck lo segnala con
i due valori. Nessuno corregge `Track.bpm`: lo fa l'utente da Analisi o a mano.

Errore dell'elemento audio (formato non supportato dal browser, file sparito):
lo stesso messaggio del player docked, l'altro deck continua. Nota: come per il
player docked, Chrome non riproduce AIFF; WebKit sì.

## 3. Modello dati

### Colonne aggiunte a `Track`

| Colonna | Tipo | Significato |
|---|---|---|
| `grid_first_beat` | float nullable | Istante, in secondi dall'inizio del file, del primo battito della griglia |
| `grid_bpm` | float nullable | BPM della griglia, a tempo costante |
| `grid_error` | str nullable | Motivo per cui la griglia manca: `uncertain`, `too_few_beats`, oppure il messaggio dell'eccezione |

Chi le scrive, per esteso:

1. Il job di analisi (`audio_analysis_job.py`), ogni volta che gira su una
   traccia, qualunque sia l'esito di "applica" o "ignora" sui BPM/key proposti.
   Una griglia valida azzera `grid_error`; una griglia rifiutata azzera le due
   colonne e scrive `grid_error`.
2. L'indicizzazione della libreria e lo scollegamento del file: quando
   `has_local_file` diventa falso o `audio_hash` cambia, le tre colonne tornano
   `NULL`.
3. Lo strumento `merge_duplicate_tracks` scarta la griglia della traccia
   assorbita; la superstite tiene la sua.

Nessun altro punto di scrittura. Nessun backfill: la griglia si calcola alla
prima richiesta del deck o al prossimo giro di analisi.

### Tabelle nuove

**`TrackWaveform`** — una riga per traccia.

| Colonna | Tipo | Note |
|---|---|---|
| `track_id` | int PK, FK `Track` on delete cascade | |
| `samples_per_second` | int | 100 |
| `duration_seconds` | float | Dal PCM decodificato, non da `Track.duration_seconds` |
| `audio_hash` | str | L'`audio_hash` del file al momento del calcolo; se diverso da `Track.audio_hash` la riga è stantia |
| `peaks` | blob | Un byte per picco, 0–255 |
| `created_at` | datetime | |

**`TrackCue`** — le memory cue.

| Colonna | Tipo | Note |
|---|---|---|
| `id` | int PK | |
| `track_id` | int FK `Track` on delete cascade, index | |
| `position_seconds` | float | ≥ 0; ≤ durata se nota |
| `name` | str nullable | ≤ 60 caratteri |
| `created_at` | datetime | |

Massimo dieci per traccia, imposto dal servizio. Ordinate per posizione.
`merge_duplicate_tracks` sposta le cue della traccia assorbita sulla
superstite (restando entro dieci: le eccedenti si scartano, in ordine di
posizione) e scarta la waveform dell'assorbita.

Migrazioni idempotenti in `db.py`, come per tutte le altre.

### Regole di calcolo

**Griglia** (`services/beatgrid.py`, puro). Ingresso: i battiti di Essentia in
secondi, crescenti. Procedura:

1. Meno di sedici battiti: `too_few_beats`.
2. Periodo grezzo = mediana degli intervalli fra battiti consecutivi.
3. Si scartano gli intervalli che si discostano dal periodo grezzo oltre il
   20 % (battiti saltati o raddoppiati). Se la deviazione mediana assoluta dei
   rimanenti supera il 2 % del periodo: `uncertain`.
4. A ogni battito si assegna l'indice `k = round((t − t0) / periodo)`; una
   regressione ai minimi quadrati di `t` su `k` sui battiti rimasti dà periodo
   e ancora.
5. `grid_bpm = 60 / periodo`; `grid_first_beat = ancora` riportata in
   `[0, periodo)`.

Niente piegatura di ottava: la griglia è quella che Essentia misura.

**Picchi** (`services/waveform.py`, puro). Ingresso: PCM mono 22050 Hz s16le
dell'intera traccia, ottenuto dalla stessa pipeline ffmpeg di `audio_hash`
(`decode_pcm_bytes` con una variante senza limite di durata). Cento picchi al
secondo: la finestra `i` copre i campioni da `floor(i · sr / 100)` a
`floor((i + 1) · sr / 100)`; il picco è il massimo del valore assoluto,
quantizzato a `round(max / 32767 · 255)`. Numero di picchi =
`ceil(n_campioni · 100 / sr)`. Il JSON li trasporta in base64.

## 4. API

Nuovo router `routers/deck.py`, prefisso `/api/tracks`.

- `GET /api/tracks/{id}/deck` → `DeckOut`:
  `track` (id, title, artist, bpm, camelot_key, duration_seconds,
  album_art_url, has_local_file), `grid` (`first_beat`, `bpm`) o `null`,
  `grid_error`, `waveform` (`samples_per_second`, `duration_seconds`,
  `peaks` base64) o `null` se mancante o stantia, `cues` ordinate per
  posizione. 404 `track_not_found`, 404 `track_no_local_file`.
- `POST /api/tracks/{id}/deck/prepare`. Calcola i picchi se mancano o sono
  stantii, in modo sincrono (ffmpeg in sottoprocesso, il server non si
  blocca). Poi, per la griglia: se presente → 200 `{"grid": "ready"}`; se il
  motore Essentia manca → 200 `{"grid": "unavailable", "reason": …}`; se il
  job di analisi sta già girando → 409 `analysis_busy` (i picchi appena
  calcolati restano salvati); altrimenti avvia il job sulla sola traccia →
  202 `{"grid": "queued"}`. 503 `ffmpeg_unavailable` se ffmpeg manca; errore
  di decodifica → 500 `waveform_failed`, niente salvato.
- `POST /api/tracks/{id}/cues` body `{position_seconds, name?}` → 201 `CueOut`.
  409 `cue_limit` oltre la decima; 422 fuori dai bordi o nome troppo lungo.
- `PATCH /api/tracks/{id}/cues/{cue_id}` body con i soli campi da cambiare
  (`null` azzera il nome) → 200 `CueOut`. 404 `cue_not_found`.
- `DELETE /api/tracks/{id}/cues/{cue_id}` → 204.

Il job di analisi cambia così: il worker (`essentia_worker.py`) stampa anche
`"ticks": [...]`; `audio_analysis_job.py` chiama `beatgrid.fit` e scrive le
colonne della griglia a ogni traccia analizzata. `analysis_error` e
`grid_error` restano separati: una griglia rifiutata non è un'analisi fallita.

Il frontend chiama `prepare` all'apertura di ogni deck e poi legge `deck` ogni
due secondi finché griglia e waveform non sono arrivate, con ritentativo di
`prepare` sul 409; alla chiusura del dock le richieste in volo si invalidano
con un contatore, come fa il player per le preview.

## 5. Motore audio

### Grafo

Un solo `AudioContext`, quello che `audio-analyser.ts` già crea per lo spettro
della Home, esposto con un getter. Per deck: `<audio>` nascosto con `src`
sull'endpoint audio esistente e `crossOrigin="anonymous"` (in Tauri frontend e
backend sono origini diverse; lo spettro usa già lo stesso accorgimento), poi
`MediaElementAudioSourceNode` → `BiquadFilterNode` passa-alto (10 Hz spento,
300 Hz acceso, Q 0,7) → `GainNode` del volume → `GainNode` master →
destinazione.

### Tempo e sync

`playbackRate` per il tempo, `preservesPitch` per il master tempo (ripiego su
`webkitPreservesPitch`; se manca anche quello il master tempo si disattiva con
avviso). Il rate è sempre bloccato nella corsa scelta.

Definizioni, in `lib/deck/grid.ts` (puro, testato):

- `beatTimes(grid, from, to)`: istanti dei battiti nell'intervallo.
- `phaseAt(grid, t)`: frazione di battito in `[0, 1)`.
- `nearestBeat(grid, t)`.
- `syncRate(master, slave)`: `rate_slave = bpm_master · rate_master /
  bpm_slave`, con i BPM delle griglie se entrambe esistono, altrimenti i
  nominali.
- `alignShift(master, slave)`: spostamento in secondi, entro ±mezzo periodo
  dello schiavo, perché la fase dello schiavo coincida con quella del master.
- `bpmDisagreement(gridBpm, nominalBpm)`: scarto relativo minimo fra la griglia
  e il nominale, il suo doppio e la sua metà.

Lo scarto di fase mostrato si misura quattro volte al secondo:
`(phase_slave − phase_master)` riportata in `[−0,5, 0,5)`, moltiplicata per il
periodo in uscita del master (`60 / (bpm_master · rate_master)`), in
millisecondi. Nessuna correzione automatica.

`lib/deck/engine.ts` è il cablaggio imperativo: carica, play, pausa, seek,
rate con o senza master tempo, volume, taglio bassi, letture di posizione,
distruzione. Non conosce React né il banco.

### Waveform

Un'istanza wavesurfer.js per deck, creata con `media` sull'`<audio>` del deck,
`peaks` e `duration` dal backend (nessun fetch, nessuna decodifica),
`autoCenter`, zoom con `minPxPerSec` condiviso fra i due deck (livelli 20, 40,
80, 160 px/s, default 80). Plugin Minimap per la panoramica, plugin Regions per
i marker delle cue (regioni senza `end`). I battiti si disegnano su un canvas
sovrapposto, ridisegnato agli eventi `scroll` e `zoom` di wavesurfer, tutti
uguali perché la battuta uno non è nota. I colori vengono dai token CSS del
design system, letti al montaggio e al cambio tema.

### Convivenza con il player docked

All'apertura del dock la pagina chiama `stop()` del `PlayerProvider`; mentre il
dock è aperto, se `active` del player torna non nullo (un play altrove), la
pagina chiude il dock. I deck non registrano comandi Media Session.

## 6. Interfaccia: componenti

- `components/deck/deck-dock.tsx`: telaio fisso, i due deck, la striscia
  condivisa, il comando "nascondi", la ✕, il motore in un `ref`, il polling di
  `deck`/`prepare`, la convivenza con il player docked.
- `components/deck/deck.tsx`: un deck, le due colonne.
- `components/deck/deck-waveform.tsx`: montaggio di wavesurfer, Minimap,
  Regions, canvas dei battiti.
- `components/deck/cue-strip.tsx`: chip, rinomina, elimina, "metti cue", "al
  battito".
- `lib/deck/grid.ts`, `lib/deck/engine.ts` come sopra; `lib/api` guadagna le
  chiamate `trackDeck`, `trackDeckPrepare`, `trackCueCreate/Update/Delete`.
- La pagina del banco tiene lo stato `audition: {fromRow, toRow} | null` e
  passa a `TransitionPanel` un `onAudition`.
- Testi in entrambi i dizionari, italiano e inglese. Look del player docked:
  bordi sottili, superficie elevata, cifre tabellari.

## 7. Gestione degli errori

Riassunto di ciò che le sezioni 2 e 4 già dicono, perché stia in un posto:

| Situazione | Backend | Deck |
|---|---|---|
| Traccia senza file | 404 `track_no_local_file` | Pulsante disabilitato a monte |
| ffmpeg assente | 503 `ffmpeg_unavailable` | "waveform non disponibile: ffmpeg assente"; tutto il resto funziona |
| Decodifica fallita | 500 `waveform_failed` | Stesso testo con il motivo; ritentabile |
| Essentia assente | 200 `grid: unavailable` | "griglia non disponibile: motore assente" |
| Griglia incerta / pochi battiti | `grid_error` salvato | "griglia non disponibile: <motivo>" |
| Job occupato | 409 `analysis_busy` | "analisi di massa in corso, attendo", ritenta |
| Waveform stantia | `deck` → `null`, `prepare` ricalcola | "waveform in calcolo" |
| Cue oltre la decima | 409 `cue_limit` | Pulsante disabilitato a monte |
| Cue fuori dai bordi | 422 | Non raggiungibile dall'interfaccia |
| Errore dell'elemento audio | — | Messaggio del player docked; l'altro deck continua |
| Traccia scollegata dopo l'apertura | 404 al prossimo `deck` | "file non più disponibile" |
| Contesto audio sospeso | — | Si riattiva al primo gesto (`primeOnFirstGesture`) |
| `preservesPitch` assente | — | Ripiego prefissato, poi master tempo disattivato con avviso |

## 8. Test

Criterio: ogni asserzione deve rompersi se il codice si rompe; invarianti sulla
correttezza, non sulla presenza di un valore.

**Backend, pytest.**

- `beatgrid.fit`: battiti regolari a 128 BPM dal secondo 0,37 → esattamente
  `grid_bpm = 128.0`, `grid_first_beat = 0.37` (tolleranza 1e-6); con jitter
  uniforme di ±10 ms → BPM entro 0,1 e primo battito entro 5 ms; con tre
  battiti saltati e due raddoppiati → stesso risultato; meno di sedici battiti
  → `too_few_beats`; battiti casuali → `uncertain`; un controllo che 128 non
  diventi 64 né 256.
- `waveform.peaks`: PCM sintetico con un secondo di silenzio, un secondo di
  sinusoide a piena scala, mezzo secondo di silenzio → 250 picchi, i primi
  cento zero, i cento centrali 255, gli ultimi cinquanta zero.
- Router: 404 senza file; `prepare` con `decode` sostituito da una funzione
  che restituisce il PCM sintetico crea la riga con l'`audio_hash` della
  traccia; se l'hash della riga differisce da quello della traccia `deck` dà
  `null` e `prepare` ricalcola; `is_running` vero → 409; motore assente →
  `unavailable`; cue: creazione, modifica, cancellazione, undicesima → 409,
  posizione negativa → 422, nome di 61 caratteri → 422, elenco ordinato per
  posizione; `merge_duplicate_tracks` sposta le cue e scarta waveform e
  griglia dell'assorbita.
- Job: worker finto che restituisce battiti → le colonne della griglia sono
  scritte anche quando l'analisi non viene applicata; scollegamento del file →
  colonne azzerate; worker con battiti casuali → `grid_error = uncertain` e
  `analysis_error` nullo.

**Frontend, vitest.**

- `grid.ts`: ogni funzione con valori calcolati a mano; per `alignShift` una
  proprietà su cento casi: spostamento entro ±mezzo periodo e fase risultante
  uguale a quella del master entro 1e-6; `bpmDisagreement(126, 63) = 0`.
- Componenti con motore finto: due deck dal passaggio con titoli e BPM giusti;
  pulsante disabilitato senza file locale; cue aggiunta, rinominata ed
  eliminata chiamano l'API con i parametri attesi e aggiornano le chip;
  "nascondi" toglie i regolatori e scrive la chiave in `localStorage`; un test
  per ciascun testo di stato; "Usa come la suono a" chiama `onSavePlayBpm` con
  nominale × rate.
- `engine.ts` con `AudioContext` finto: gain, frequenza del filtro,
  `playbackRate` e `preservesPitch` sugli elementi come richiesto.
- Limite dichiarato: jsdom non ha Web Audio né canvas; nessun test ascolta.

**End to end, Playwright (`test:e2e`).** Set manuale con due tracce possedute
da file WAV minuscoli: "Prova il passaggio" apre il dock con due deck; la
waveform compare dopo `prepare`; una cue aggiunta sopravvive al ricaricamento;
la ✕ fa tornare il player docked. Lo stato della griglia si confronta con ciò
che `analysis/overview` dichiara sul motore, così il test è esatto con e senza
Essentia.

**Verifica a orecchio**, lista di controllo da chiudere a mano con due tracce
vere, nel browser dell'app e in Tauri:

1. Sync su B: i BPM effettivi coincidono, lo scarto di fase è entro ±10 ms e
   resta stabile per due minuti.
2. Master tempo acceso: il pitch non cambia l'intonazione; spento: la cambia.
3. Taglio bassi: la cassa sparisce dal deck interessato.
4. Spinte di ±10 ms e salti di battito: udibili e coerenti con la lettura di
   fase.
5. Cue: il salto è preciso al battito con "al battito" acceso.
6. Apertura dei deck ferma il player docked; un play altrove chiude i deck.
7. "Nascondi" e chiusura, poi riapertura: lo stato è ricordato.

## 9. Documentazione da aggiornare

Nella stessa tappa che chiude l'implementazione, e con la nota di stile della
roadmap (parentesi e "vedi X" controllati a parte):

- `CLAUDE.md`: il paragrafo "The project does not act as a DJ deck (no
  waveform/cue/queue…)" diventa l'eccezione circoscritta: due deck dentro il
  banco, waveform, cue e griglia propria, solo per provare un passaggio; la
  regola 2 cita la griglia come derivato Essentia che non tocca BPM/key;
  l'elenco dei router aggiunge `deck`, quello dei servizi `beatgrid` e
  `waveform`.
- `README.md`, frase "Cratory is not a DJ deck — no waveforms, no cues, no
  queue": riscritta nello stesso senso.
- `docs/ARCHITECTURE.md`: la frase "Beatgrid and cue points are out of scope"
  e quella "Cratory is not a DJ deck" nella sezione sui file; la nota di scope
  dell'import Rekordbox resta vera (il nodo `TEMPO` continua a non entrare) ma
  va riletta; una sezione nuova sul dock a due deck con il grafo audio e le
  tre strutture dati.
- `docs/API.md`: gli endpoint della sezione 4 e il campo `ticks` del worker.
- `docs/ROADMAP.md`: la voce rinviata del 2026-09-17 diventa lo stato di
  questa spec, con la differenza dichiarata (waveform e cue entrano, `TEMPO`
  no).
- `docs/DEPENDENCIES.md`: `wavesurfer.js` nella sezione frontend, con licenza.
- `PROGRESS.md`: voce di chiusura.

## 10. Tappe

1. **Griglia.** Worker con `ticks`, `beatgrid.py`, colonne su `Track`,
   scrittura dal job, azzeramento allo scollegamento, fusione duplicati, test.
2. **Waveform, deck e cue.** `waveform.py`, decodifica intera, tabelle,
   router `deck.py`, test di router e servizi.
3. **Motore nel frontend.** Dipendenza `wavesurfer.js`, `grid.ts`,
   `engine.ts`, chiamate API, test vitest.
4. **Il dock nel banco.** Componenti, stati, "nascondi", convivenza con il
   player docked, testi nei due dizionari, test dei componenti.
5. **Chiusura.** E2E, lista a orecchio, documentazione della sezione 9.

Ogni tappa lascia l'app funzionante: le prime due non cambiano nulla di
visibile, la terza aggiunge solo codice non ancora montato.

## 11. Criteri di riuscita

- Da un passaggio del banco si arriva ad ascoltare i due deck sincronizzati in
  meno di dieci secondi su una traccia già preparata, e la prima volta entro il
  tempo dell'analisi Essentia.
- Lo scarto di fase dopo "Sync" è entro ±10 ms e non deriva in due minuti su
  tracce a tempo costante.
- Nessun test, nessun codice dei deck scrive `Track.bpm`, `camelot_key` o le
  loro provenienze. Un grep su `bpm_source`/`key_source` nei file nuovi deve
  dare zero.
- Il banco, il player docked e la pagina Analisi funzionano come prima quando
  il dock è chiuso.

## 12. Dopo la prima versione, solo se serve

- Scorciatoie da tastiera per trasporto, cue e spinte.
- Export delle cue nell'XML Rekordbox insieme al set, con il nodo `TRACK`
  conservato all'import e riemesso identico più le `POSITION_MARK`; richiede
  l'import a due passi in Rekordbox, da documentare.
- Import delle cue di Rekordbox, con regole di fusione.
- Loop, EQ a tre bande, cuffia, crossfader.
- Battuta uno e allineamento di frase: servirebbe un rilevatore di downbeat
  (per esempio madmom), dipendenza nuova.
- Riduzione del dock a una striscia con solo trasporto e BPM.
- Una pagina Deck fuori dal banco: scartata ora, è il primo passo della china
  verso il deck completo.
