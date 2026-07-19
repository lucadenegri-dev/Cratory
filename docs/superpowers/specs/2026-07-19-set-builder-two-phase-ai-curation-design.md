# Set Builder: generatore a due fasi + AI curatrice

Data: 2026-07-19
Stato: bozza in revisione

## Contesto e problema

Il Set Builder oggi funziona così: il Candidate Engine filtra il pool, poi o il beam
search deterministico (`set_generator.py`) costruisce la scaletta, oppure — percorso
alternativo — l'AI riceve ≤60 candidate e produce selezione + ordinamento + narrativa,
ricontrollata dal Validation Engine.

Due sintomi ricorrenti sulla qualità delle scalette:

1. **Struttura piatta.** Le transizioni reggono tecnicamente, ma il set non ha un
   racconto: peak anonimo, nessuna tensione. Causa: il beam search ottimizza
   localmente ("la prossima traccia buona data la precedente" + aderenza all'arco di
   posizione), nessuno pianifica la struttura globale. Le tracce forti si sprecano
   nei posti sbagliati.
2. **Scelte fuori mood.** Tracce che non c'entrano col vibe richiesto anche se BPM e
   key tornano. Causa: il motore vede solo BPM/key/energia/famiglie di genere;
   "malinconico", "tribale", "da tramonto" non esistono in nessuna formula.

Diagnosi sul ruolo dell'AI: oggi l'AI fa l'ordinamento, cioè il lavoro in cui è più
debole (non può calcolare compatibilità: glielo vieta il prompt stesso) e il
Validation Engine le fa da badante. Il suo vantaggio comparato — giudizio
semantico/culturale su tracce e intenti — oggi non viene usato.

Inoltre il genere musicale ha oggi solo un ruolo locale (similarità di coppia,
peso ×0.25): evita il ping-pong tra famiglie ma nessuno pianifica un percorso di
genere lungo il set.

## Obiettivi

- Dare struttura globale ai set: anchor pianificati (apertura/peak/chiusura/reset),
  bombe riservate al peak, piano di genere per segmento.
- Spostare l'AI da "ordina la scaletta" a "interpreta l'intento e cura il pool":
  compilazione del prompt libero in vincoli, mood-fit per candidata, anchor suggeriti.
- Alzare il pool visibile all'AI da 60 a 200 candidate (a lotti), mantenendo lo
  spirito della regola "mai l'intera libreria".
- Ritirare del tutto il percorso "AI ordina la scaletta" (deciso, nessuna opzione
  nascosta di ripiego).

## Non-obiettivi

- Analisi audio aggiuntiva (struttura interna, intro/outro, fraseggio): fuori scope.
- Apprendimento dai gesti di editing nel workbench: idea registrata, non in questa
  iterazione.
- Nessuna modifica a: identità tracce, provenienza BPM/key, ruoli di Sortory,
  player, export.

## Tappa 1 — Generatore a due fasi (solo deterministico)

Sostituisce il flusso monolitico di `generate_set()` con: **Fase 1 scheletro →
Fase 2 riempimento**. Nessuna chiamata LLM. Interfaccia esterna invariata
(`POST /api/sets/generate-async`, stessa request/response).

### Fase 1: lo scheletro

**Punteggio di impatto** (nuovo, deterministico) per ogni candidata:
`impact = 0.7·percentile_energia + 0.3·percentile_bpm` calcolati sul pool; se
l'energia manca, solo il percentile BPM. Costanti iniziali, dichiarate tunabili.

**Anchor.** Posizioni derivate dalla strategia (`_STRATEGY_PROFILES`): apertura (0),
peak (posizione dell'apice dell'`energy_arc`, ~70%), chiusura (fine), più un anchor
per ogni `reset_point` della strategia. Elezione deterministica per ruolo:

- peak: argmax di `impact` + aderenza BPM all'arco in quella posizione + bonus se
  appartiene alla famiglia di genere assegnata al segmento peak;
- apertura: vicinanza a `start_bpm` + aderenza al punto di partenza dell'arco
  energia della strategia (sostituisce l'attuale `_pick_first`, conservandone il
  bonus seed);
- chiusura: aderenza a `end_bpm` e al punto finale dell'arco;
- reset: coerenti con il `reset_bonus`/calo di energia della strategia.

Gli artisti seed mantengono il bonus attuale anche nell'elezione degli anchor.

**Riserva delle bombe.** Le candidate nel top 15% di `impact` sono prenotate per il
segmento peak: fuori da quel segmento ricevono una penalità fissa (−25) nello
scoring di fase 2. Se il pool è piccolo (sotto ~20 candidate) la riserva si riduce
alle sole top 3 per non affamare gli altri segmenti.

**Piano di genere.** Le candidate si raggruppano per famiglia (`_GENRE_FAMILIES`
esistente). Se la famiglia dominante copre ≥80% del pool, il piano degenera: nessun
vincolo aggiuntivo (comportamento identico a oggi). Altrimenti si assegna a ogni
segmento una famiglia dominante in base a composizione del pool e strategia (es.
warm-up nella famiglia più "deep" presente, peak nella famiglia principale), con
severità proporzionale al `genre_coherence` della strategia.

### Fase 2: il riempimento

Il beam search esistente (`_beam_search`, larghezza 6, espansioni 8, rete di
sicurezza greedy) riempie ogni segmento tra un anchor e il successivo, con budget
di durata per segmento. Due componenti nuove in `_candidate_score()`:

- **Convergenza verso l'anchor in arrivo**: distanza BPM/key/genere dal prossimo
  anchor, con peso che cresce man mano che gli slot residui del segmento calano
  (peso base ×0.35 · (1 − slot_residui/slot_segmento)). Si arriva al peak
  preparati, non per caso.
- **Aderenza al piano di genere**: bonus/penalità se la traccia appartiene alla
  famiglia assegnata al segmento (peso scalato su `genre_coherence`). La
  similarità di coppia esistente resta per la coerenza locale.

### Degradazioni e errori

- Set attesi corti (< 6 tracce stimate dal target di durata): si salta lo
  scheletro e si usa il flusso attuale a fase singola.
- Anchor non raggiungibile entro il budget del segmento: l'anchor viene piazzato
  comunque e la transizione risultante genera il warning standard (score basso →
  `creative_risk`); nessun fallimento.
- Pool < 3: `SetGenerationError` come oggi.
- Ruoli (`assign_roles`), spiegazione globale, mix tip, export: invariati; i ruoli
  si allineano agli anchor (il peak eletto riceve ruolo `peak`, ecc.).

### Test tappa 1

- Unit: elezione anchor per strategia (posizioni e criteri), riserva bombe
  (penalità fuori peak, riduzione su pool piccoli), piano di genere (assegnazione,
  degenerazione monogenere ≥80%), termine di convergenza (peso crescente).
- Integrazione: `generate_set()` su pool sintetici — il picco di energia cade nel
  segmento peak, le top-impact non appaiono nel primo terzo, set corti usano il
  flusso a fase singola, parità di interfaccia con la request attuale.

## Tappa 2 — L'AI cura, il motore sequenzia

Il percorso `generate_ai_set()` (AI che ordina) viene **ritirato**. L'AI diventa un
passaggio di lettura prima del generatore deterministico, più la narrativa a valle.

### Chiamate AI (per generazione, quando `use_ai` attivo)

1. **Compilazione dell'intento** (solo se c'è un prompt libero): il prompt viene
   tradotto in vincoli strutturati (strategia, archi BPM/energia, generi, seed,
   durata se espressa). Schema Pydantic; i campi compilati NON sovrascrivono i
   campi che l'utente ha impostato esplicitamente nel form — riempiono solo i vuoti.
   Il risultato ("ecco come ti ho capito") viene salvato nei metadati del setlist e
   mostrato nel workbench.
2. **Mood-fit a lotti**: il pool AI sale a ≤200 candidate (se il pool filtrato è
   più grande, campionamento stratificato sulle fasce BPM come oggi). Lotti da ~50
   candidate per chiamata; per ciascuna: punteggio 0–100 di aderenza all'intento +
   1–3 tag sintetici. Il mood-fit entra in `_candidate_score()` come componente
   aggiuntiva (peso iniziale ×0.30, tunabile) e nell'elezione degli anchor.
   I giudizi sono transienti (per generazione), non persistiti sulle tracce.
3. **Anchor suggeriti**: dopo il mood-fit, una chiamata con le top ≤60 candidate
   per mood-fit propone una rosa motivata di apertura/peak/chiusura. La fase 1 li
   tratta come bonus nell'elezione, mai come vincoli.
4. **Narrativa a valle** (come oggi): titolo, spiegazione globale, suggerimenti
   sulla libreria — sulla scaletta già costruita dal motore.

Ogni chiamata rispetta il tetto per-chiamata di 60 candidate; il tetto di pool
complessivo diventa 200.

### Validazione

`validate_ai_set()` (la "badante" della scaletta AI) viene rimossa con il percorso
che la richiedeva. Restano/nascono validazioni Pydantic per i nuovi output:

- vincoli compilati: bounds (durata, archi BPM/energia dentro range sensati),
  strategie/generi da enum note;
- mood-fit: ogni id deve appartenere al pool inviato, score 0–100, id inventati
  scartati in silenzio con warning aggregato;
- anchor suggeriti: id nel pool, ruoli da enum.

### Fallimenti

Qualsiasi chiamata AI che fallisce degrada senza bloccare: la generazione procede
deterministica con un warning sul setlist ("curatela AI non disponibile"). La
compilazione dell'intento che fallisce lascia i vincoli del form così come sono.

### API e UI

- `use_ai` resta nella request ma cambia semantica: `true` = intento + curatela +
  narrativa; `false` = puro deterministico; auto (assente) = AI se configurata e
  c'è un prompt, come oggi.
- Il toggle "Algoritmo vs AI" nel form diventa "Curatela AI on/off" (il motore è
  sempre uno). Il prompt libero resta visibile solo con AI configurata. Il toggle
  technical/creative resta e seleziona il system prompt della curatela/narrativa.
- Il workbench mostra i vincoli compilati ("come ti ho capito") e i tag mood-fit
  per traccia quando presenti.
- `generated_by` sui setlist: sparisce il valore `ai` per le nuove generazioni;
  si introduce `algorithmic+ai_curation` (i setlist storici restano leggibili).

### Test tappa 2

- Unit: schemi dei tre output AI (id fuori pool scartati, bounds), merge dei
  vincoli compilati con quelli espliciti (l'utente vince), batching del mood-fit
  (pool 200 → 4 lotti, ogni chiamata ≤60), degradazione su fallimento AI.
- Integrazione: generazione con AI mockata end-to-end — mood-fit che influenza la
  selezione, anchor suggerito che vince l'elezione a parità, narrativa applicata.

## Documentazione da aggiornare

- `CLAUDE.md` regola 4: "L'AI non riceve mai l'intera libreria. Riceve solo
  candidate filtrate dal Candidate Engine: pool massimo 200, per chiamate a lotti
  di massimo 60." Regola 1: aggiornare la lista dei compiti AI (interpretazione
  intento, curatela, narrativa — mai sequencing).
- `docs/ARCHITECTURE.md`: nuova pipeline (Candidate Engine → [AI curatrice] →
  generatore a due fasi → Set Editor), rimozione del ramo AI-ordina e di
  `validate_ai_set`.
- `docs/API.md`: semantica `use_ai`, nuovi metadati setlist (vincoli compilati,
  tag mood-fit, `generated_by`).
- `docs/ROADMAP.md` e `PROGRESS.md`: registrare le due tappe.

## Sequenza di consegna

1. **Tappa 1** (autonoma, rilasciabile da sola): scheletro + riserva bombe + piano
   di genere + convergenza. Nessun cambio API/UI.
2. **Tappa 2** (dipende dalla 1): curatela AI, ritiro del percorso AI-ordina,
   aggiornamento UI e documenti.

## Rischi e mitigazioni

- **Costo/latenza AI in tappa 2**: fino a ~6 chiamate per generazione (1 intento +
  4 lotti + 1 anchor) più la narrativa. Mitigazione: lotti in parallelo, pool 200
  solo quando il filtrato lo supera, generazione già asincrona con polling.
- **Pesi nuovi da tarare** (impatto, convergenza, mood-fit): dichiarati come
  costanti nominate e tunabili; i valori iniziali sono ipotesi esplicite.
- **Metadati di genere poveri**: il piano di genere degenera con grazia; in tappa 2
  il mood-fit compensa dove le famiglie non arrivano.
