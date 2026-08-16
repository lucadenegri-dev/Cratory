# Frontespizio ASCII della Home

Data: 2026-08-16. Stato: approvata a voce.

## Problema

La Home apre su una striscia di contatori. È informativa ma anonima: non dice
dove sei. Il nome dell'app vive solo piccolo nella nav laterale
(`components/index-nav.tsx`), e la pagina non ha nemmeno un `h1` — `PageLayout`
riceve `title` da tutte le pagine tranne questa.

La Home guadagna un **frontespizio**: CRATORY a lettere grandi in ASCII, in
cima, con la cabina DJ subito sotto. Le due sezioni di dati che oggi stanno in
alto scendono sotto il frontespizio.

Fuori scope: toccare la cabina DJ, la striscia del ciclo, le quattro cifre o il
wordmark della nav. Cambia l'ordine della pagina e si aggiunge la scritta.

## Decisioni chiave

- **Lettering a blocchi pieni di `#`**, 5×5 per lettera. Stesso vocabolario
  grafico delle casse della cabina (`#########` in `ascii-dj.tsx`): le due
  scritte sembrano fatte dello stesso materiale.
- **ASCII puro, niente unicode.** I glifi pieni unicode (`█`, `▓`) cadono sul
  font di fallback con larghezza diversa e disallineano le colonne. È la stessa
  regola per cui la cabina usa `°*·` al posto di `♪♫`.
- **Statica e monocroma.** Nessun timer, nessuno stato. La cabina resta l'unica
  cosa che si muove in pagina: due elementi animati incolonnati si darebbero
  fastidio.
- **Sempre visibile**, anche a libreria vuota e durante il caricamento: la Home
  ha sempre una testata, sotto cambia solo il contenuto.
- **Font ristretto alle 6 lettere di CRATORY** (C R A T O Y). Un alfabeto
  completo sarebbe codice mai chiamato.

## Struttura della pagina

Dall'alto:

```text
CRATORY                     frontespizio ASCII, sempre
[errore | caricamento | "importa una playlist"]   quando servono
la cabina DJ                invariata (click = traccia a caso)
              statistiche →  right-aligned
striscia del ciclo          sezione 1, invariata
le quattro cifre            sezione 2, invariata
```

Il link alle statistiche oggi sta in cima alla pagina. Scende **sotto la
cabina**, appoggiato alle due sezioni di dati a cui appartiene: il frontespizio
(scritta + cabina) resta pulito, senza un rimando che gli penzola sopra.

## Il componente

Nuovo `frontend/components/dashboard/ascii-wordmark.tsx`, a due strati come la
cabina:

- **Core puro.** `GLYPHS`, dizionario di lettere 5×5, e `wordmarkLines(word)`
  che le compone unendo i glifi con una colonna di spazio. Deterministica,
  senza React, testabile da sola. `WORDMARK_LINES` è la composizione di
  `CRATORY`, calcolata una volta al caricamento del modulo.
- **Guscio React.** `AsciiWordmark`, senza stato e senza props: `<pre>` in
  `text-fg-strong` con `leading-[1.15]` come la cabina.

Nessun `padEnd` di sicurezza sulle righe composte: l'allineamento è garantito
dalla geometria dei glifi, e quella la sorveglia il test. Una rete di sicurezza
non testata renderebbe vacuo il test sulla larghezza.

## Accessibilità

L'arte è `aria-hidden="true"`; accanto, un `<h1 className="sr-only">Cratory</h1>`.
Effetto collaterale voluto: la Home acquista il titolo di pagina che oggi non ha.

## Responsive

Involucro `flex justify-center overflow-x-auto`, scala tipografica che sale per
breakpoint come fa la cabina. La scritta è 41 colonne contro le 75 della cabina:
va dimensionata perché resti **più stretta della cabina a ogni breakpoint** —
domina per peso, non per larghezza. I valori si tarano misurando l'advance reale
di DM Mono in preview, non a stima.

## i18n

Niente. CRATORY è un nome proprio, identico nelle due lingue; l'`sr-only` è
"Cratory" in entrambe.

## Test

Nuovo `frontend/tests/ascii-wordmark.test.tsx`:

- ogni glifo di `GLYPHS` è esattamente 5 righe da 5 caratteri — è l'invariante
  che, se salta, spacca l'allineamento;
- i glifi contengono solo `#` e spazio (la regola "niente unicode");
- `wordmarkLines("CRATORY")` dà 5 righe da 41 colonne, tutte uguali di
  larghezza, e la funzione rifiuta una lettera che non ha glifo;
- il guscio espone l'`h1` accessibile e marca l'arte come decorativa.

Ogni asserzione va provata rompendo il codice prima di dichiararla verde.

## Revisione del 2026-08-16: la Home sta in una schermata

Due richieste arrivate dopo la prima consegna, che spostano quel che qui sopra
era dato per fuori scope.

**La cabina prende una cornice.** Lo stesso involucro delle due sezioni sotto
(`Card`: bordo pieno e fondo `surface`). Le tre lastre — cabina, striscia,
cifre — si leggono come una serie invece che come un disegno sospeso nel vuoto.

**Tutto deve stare senza scrollare.** La pagina misurava 785px di contenuto a
1280 di larghezza; ora ne misura 663, e regge 648 a 1024 e 707 a 1920. Da dove
vengono i 122px:

- gli stacchi verticali si stringono (`mb-8`→`mb-3` sotto il frontespizio,
  `mt-10`→`mt-1.5` sopra il link statistiche);
- le due sezioni combaciano su un bordo solo (`-mt-px` invece di `mt-10`):
  affiancate a 8px lasciavano un filetto doppio, e ora si leggono come un
  blocco continuo;
- il frontespizio e la cabina scendono di un passo nella scala tipografica dai
  breakpoint alti. La cabina è 12 righe: è l'elemento da cui si recupera più
  altezza.

Le tre righe d'aria in cima alla scena (`DJ_AIR_ROWS`) restano come sono, pur
essendo il "margine" più grosso della cabina: ridurle cambierebbe la salita
delle note, cioè il comportamento della cabina e non la sua impaginazione.

**Anche il frontespizio prende la cornice, un gradino avanti.** Stessa `Card`
delle lastre sotto, ma con fondo `elevated` e bordo `border-strong`: viene
avanti per contrasto restando in fila, perché il sistema è piatto e non ha
ombre. Contrasto del testo sul nuovo fondo: 13.6:1 in entrambi i temi.

Due conseguenze misurate, entrambe corrette:

- sul telefono la cornice toglie 24px di larghezza utile e la scritta a 13px
  non ci stava più (320px contro 309 disponibili): scesa a 12px, che fa 295px;
- `overflow-x-auto` da solo promuove anche l'asse verticale ad `auto`, e
  siccome l'interlinea sta sotto l'unità l'inchiostro deborda di un paio di
  pixel: bastava a far comparire una barra di scorrimento verticale dentro la
  cornice. Risolto con `overflow-y-hidden` esplicito più un rientro in `em`
  sull'arte — non si ritaglia nulla, si toglie solo la barra.

Il contenuto resta sotto il viewport da 1024 in su (648px a 1024, 689 a 1280,
707 a 1920). Nella fascia 768–1023 la nav passa in orizzontale e si prende
~85px: lì la pagina eccede di 21px. Non compensato: recuperarli chiederebbe di
rimpicciolire la cabina a 14px in quella sola fascia, e non vale il prezzo.

**La posa a riposo.** Ferma, la cabina stava al tick 0, che è in battere:
tweeter compressi e la `O` grande in `danger`, la posa di un colpo mentre non
esce alcun suono. Con la cabina in cima alla pagina l'incoerenza si vede.
`DJ_REST_TICK = 1`, dispari di proposito, vale per il tick iniziale e per il
congelamento con `prefers-reduced-motion`. L'aria non si svuota su nessun tick
— le note nascono sui pari e ne resta sempre una viva — ma un glifo che
fluttua non stona: stonava la cassa.
