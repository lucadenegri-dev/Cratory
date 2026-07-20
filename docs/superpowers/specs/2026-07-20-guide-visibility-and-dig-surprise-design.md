# Guida visibile nel Set Builder + "Sorprendimi" nel dig — design

Data: 2026-07-20. Due interventi indipendenti, entrambi solo frontend.

## A) Guida del Set Builder: da icona-fantasma a link leggibile

### Problema

Il link alla guida (`/set-builder/guida`) è un'icona `HelpCircle` da 17px, colore
`text-faint`, senza testo, nell'angolo in alto a destra dell'header
(`frontend/app/set-builder/page.tsx:198-203`). Di fatto invisibile: l'utente non sa
che la guida esiste.

### Soluzione

Due tocchi, zero stato, nessuna modifica alla pagina guida:

1. **Header** — il link nella prop `action` di `PageLayout` diventa icona
   `HelpCircle` + testo "Guida" (i18n: `guida`/`guide`), con contrasto pieno da
   subito (stile link secondario del design system, es. `text-muted hover:text-fg`
   con underline o border coerente con l'editoriale — non più `text-faint`).
   Restano `title`/`aria-label` esistenti.
2. **Intro** — la frase introduttiva sotto il titolo (`page.tsx:205`) si chiude con
   un richiamo inline: "…Per capire come ragiona il motore, leggi la guida", dove
   "leggi la guida" è un link a `/set-builder/guida`. Nuove chiavi i18n in
   `frontend/lib/i18n/it.ts` e `en.ts` (attenzione al gotcha Next 16 sugli spazi
   JSX a capo: `{" "}` esplicito se serve).

### Test

Nessun test dedicato: è markup statico. `npm run lint` + `npm run build`.

## B) "Sorprendimi": dig con seme casuale dal proprio gusto

### Scopo

Un bottone nella barra del dig per quando non sai cosa scavare: pesca da solo un
seme (genere o label **della tua libreria**) e una profondità, e lancia il dig.
Serendipità guidata: resti nel tuo mondo, ma senza scegliere tu.

### Architettura: roulette dei parametri, frontend-only

Il random sta **solo nella scelta dei parametri**, come se l'utente li avesse
digitati: il motore backend resta intatto e deterministico (il sort stabile di
`_select` è load-bearing, documentato). Il bottone naviga aggiornando i parametri
URL (`seed`, `value`, `depth`) e il dig parte dall'effetto esistente che reagisce
alla query string (`frontend/app/discovery/page.tsx:85-94`). L'URL risultante è
quindi condivisibile e riproducibile.

Nessuna modifica backend: `GET /api/discovery/genres` distingue già
`library` vs `styles` nel payload (`DiscoveryGenresOut`), e la barra riceve già
`options.genres.library` e `options.labels` separati.

### Logica di pick

Funzione pura estratta in un modulo dedicato (es.
`frontend/lib/discovery-surprise.ts`), con RNG iniettabile per i test:

```ts
type SurprisePick = { seedType: "genre" | "label"; value: string; depth: number };
function pickSurprise(
  pool: { genres: string[]; labels: string[] },
  current: string | null,          // valore attualmente in barra
  rng: () => number,               // default Math.random
): SurprisePick | null;
```

Regole:

- **Pool** = `genres.library` + `labels` (semi derivati dalla libreria). Gli style
  curati `_CURATED_STYLES` restano fuori: "dal mio gusto" significa libreria.
- **Pick uniforme** sul pool unificato (ogni voce equiprobabile, genere o label che
  sia). `seedType` deriva dal gruppo di provenienza della voce pescata.
- **Anti-ripetizione**: la voce uguale a `current` (confronto case-insensitive,
  trim) è esclusa dal pool del colpo. Se il pool al netto dell'esclusione è vuoto
  ma `current` esiste nel pool (libreria con un solo seme), si ripesca `current`
  (meglio un dig ripetuto che un bottone morto).
- **Depth** uniforme tra i tre valori di `DEPTHS` (0.0 / 0.5 / 1.0).
- Pool totalmente vuoto → `null`.

### UI

In `frontend/components/discovery-dig-bar.tsx`, accanto a "Scava":

- Bottone secondario "Sorprendimi" con icona `Dices` (lucide). Al click chiama un
  nuovo callback `onSurprise()` gestito da `page.tsx`, che esegue il pick e naviga
  con i nuovi parametri; combobox e depth mostrano i valori pescati (già derivati
  dall'URL), così l'utente vede cosa è uscito e può rifinire a mano.
- Disabilitato (con `title` esplicativo) quando il pool è vuoto o `busy`.
- i18n IT/EN: label bottone, tooltip pool vuoto.

### Colpo a vuoto: un solo reroll automatico

Se un dig innescato da "Sorprendimi" torna con **0 lead** (label minuscola, tutto
già posseduto), `page.tsx` ripesca automaticamente **una volta sola** (il pick
successivo esclude il seme appena fallito) e rilancia; se anche il secondo colpo è
vuoto, si mostra l'empty state normale. Il reroll vale solo per i dig avviati da
"Sorprendimi" (flag effimero in stato client, non nell'URL), mai per i dig manuali.
Costo Discogs massimo per click: ~10 richieste (2 dig).

### Test

- Unit (`test:unit` frontend) su `pickSurprise`: pool vuoto → null; anti-ripetizione;
  pool a un solo elemento uguale a current → ripesca current; con RNG fisso il pick
  è deterministico; depth ∈ {0, 0.5, 1}; seedType coerente col gruppo.
- Il reroll e la navigazione restano logica di pagina, coperti dal lint/build e
  dalla verifica manuale in browser; niente e2e nuovo.

## Fuori scope

- Pesatura del pick sul TasteProfile (endpoint backend): scartata, differenza
  pratica modesta su libreria personale.
- Random dentro il motore (`dig()`): scartato, romperebbe il determinismo
  load-bearing del ranking.
- Callout "prima volta" per la guida: scelto il link sempre visibile, senza stato.
