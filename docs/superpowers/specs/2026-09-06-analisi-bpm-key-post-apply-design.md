# L'analisi BPM/key riparte da sola a fine Apply

Data: 2026-09-06. Stato: approvata a voce.

## Problema

Chi organizza la libreria fa un giro solo: costruisce il piano, lo applica, e i
file finiscono ritaggati, rinominati e al posto giusto. Da quel momento in poi
esistono tracce possedute **senza BPM e senza key**, e nulla lo dice: per
riempire quei buchi bisogna ricordarsi di aprire la pagina Analisi e premere
Avvia.

Il gesto è sempre lo stesso e arriva sempre nello stesso punto della catena.
Vale la pena farlo fare all'app.

## Il vincolo che decide dove agganciarsi

A fine Apply esiste già un anello automatico: `apply → scan`, in
`frontend/components/jobs-provider.tsx`. Non è un dettaglio implementativo che
si può scavalcare, è **la ragione per cui l'analisi non può partire subito**.

`apply_plan` sposta e rinomina i file sul disco ma non riscrive `AudioFile.path`
né `Track.local_path`: quei percorsi restano quelli di prima finché la scansione
non riallinea indice e agganci. Il job di analisi legge `Track.local_path` e ci
passa Essentia. Lanciarlo a fine Apply significherebbe un
`analysis_decode_failed` per ogni file spostato — e, peggio, un
`analyzed_at` valorizzato su un fallimento, che maschera il buco invece di
riempirlo.

L'analisi va quindi in coda **alla scansione**, non all'apply.

## Decisioni chiave

- **Tre anelli, non due**: `apply (done, applied_ops > 0) → scan → analisi
  (scope "missing")`. Il terzo anello ha la stessa forma del secondo, che è già
  in produzione da F5.
- **Sempre automatico.** Niente spunta nel modale, niente interruttore in
  Impostazioni: il job è già interrompibile e la barra dei job lo racconta
  mentre gira. Una chiave di configurazione in più per un comportamento
  annullabile non si ripaga.
- **Solo le tracce senza BPM o key** (`scope: "missing"`). Se non manca niente,
  il job parte e finisce subito su zero tracce: costo nullo, nessun caso
  speciale da scrivere.
- **Nessuna API nuova.** `startAnalysis("missing")` esiste già in
  `frontend/lib/api/analysis.ts`; lo stato dell'analisi è già fra quelli pollati
  dal provider, quindi la riga di progresso compare da sola nella barra.
- **La modifica sta tutta nel client.** Il backend non cambia di una riga.

## Meccanica

Nel `JobsProvider`:

1. Un riferimento interno (`analysisAfterScan`) viene **armato solo quando la
   scansione post-apply è stata accettata dal backend**, cioè quando la
   `startScan()` dell'anello esistente risolve. Se il backend la rifiuta perché
   una scansione è già in corso (409) o è irraggiungibile, il riferimento resta
   disarmato.
2. Un secondo effetto riconosce il **fronte `running → done` del job di
   scansione** (che nel provider è `libraryIndex`, lo stesso job sotto due
   nomi). Se il riferimento è armato lo disarma e avvia l'analisi.
3. Lo stesso effetto **disarma anche sul fronte `running → error`**. Senza
   questa riga l'innesco resterebbe appeso e verrebbe ereditato dalla prima
   scansione manuale successiva, che non c'entra nulla con l'apply.
4. Gli errori dell'avvio sono **ingoiati in silenzio**, come già fa l'anello
   `apply → scan`: Essentia non installato (503), analisi già in corso (409),
   backend offline. Nessuno di questi è un fallimento dell'apply, che a quel
   punto è concluso e riuscito.

Il riferimento è un `useRef`, non uno stato: cambia fuori dal ciclo di render e
non deve provocarne uno.

## Effetto sui dati

Il job scrive solo i campi `analysis_*`. L'unico ponte automatico verso i
canonici è `auto_apply_missing`, che riempie **soltanto i campi vuoti** con
provenienza `cratory`. La gerarchia `manual > rekordbox > cratory` della regola
2 resta intatta: un import Rekordbox o una correzione manuale non vengono mai
declassati da questa catena. Dove il canonico esiste già e diverge, la riga
finisce nella lista divergenze e aspetta una decisione, come sempre.

## Ambito

Dentro:

- `frontend/components/jobs-provider.tsx`: il terzo anello.
- `frontend/tests/jobs-provider-organize.test.tsx`: i casi nuovi.
- `PROGRESS.md` e, se pertinente, `docs/ARCHITECTURE.md` per il comportamento.

Fuori:

- Il backend, in ogni sua parte.
- L'apply automatico delle divergenze: resta esplicito, dalla pagina Analisi.
- Il caso "scansione già in corso al termine dell'apply": oggi non riscansiona
  e da oggi non analizza. Coerente con quello che c'è, non peggiore.

## Limite accettato

La catena vive nel client. Ricaricare la pagina mentre la scansione gira perde
l'innesco e l'analisi non parte. È esattamente la fragilità dell'anello
`apply → scan` già esistente, che il codice documenta come *comportamento, non
API*. Spostare la catena nel backend risolverebbe entrambe, ma è un lavoro di
altra natura: sarebbe `scan_job` a dover conoscere l'analisi audio, cioè un
servizio di Organize che chiama un job del nucleo. Non lo si fa per questo.

## Test

In `frontend/tests/jobs-provider-organize.test.tsx`, che già copre l'anello
`apply → scan` con il suo caso negativo:

1. **Fine scansione innescata da un apply → l'analisi parte**, con
   `scope: "missing"`.
2. **Scansione manuale → l'analisi NON parte.** È il caso che distingue questo
   design da un innesco incondizionato su ogni fine scansione.
3. **Scansione rifiutata (409) → l'analisi NON parte**, perché l'innesco non si
   è mai armato.
4. **Scansione finita in errore → l'analisi NON parte**, e l'innesco non
   sopravvive alla scansione manuale successiva.
5. **Avvio dell'analisi che rifiuta (503 Essentia mancante) → il provider non si
   rompe** e la barra continua a funzionare.

Ogni asserzione va provata rompendo il codice: un test che passa anche con il
terzo anello cancellato non sta misurando niente.
