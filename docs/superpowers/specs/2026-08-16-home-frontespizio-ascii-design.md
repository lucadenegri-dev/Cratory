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
