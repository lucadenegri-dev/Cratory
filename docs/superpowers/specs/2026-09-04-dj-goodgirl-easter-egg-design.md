# DJ GOODGIRL: il frontespizio della Home per un solo username

Data: 2026-09-04. Stato: approvata a voce, con mockup statici.

## Cosa

Un easter egg. Quando l'username SoundCloud salvato in Impostazioni è
`xgiorgix`, il frontespizio della Home cambia persona: la scritta grande che si
risolve dal rumore dice **DJ GOODGIRL** invece di CRATORY, e nella cabina ascii
il DJ diventa una DJ — ricci in testa, capelli ai lati del viso, scollo a V.
Per qualunque altro username (o nessuno) la Home resta identica a oggi.

Niente in Impostazioni, niente nel backend, niente in Tauri, nessun testo
visibile nuovo: la scelta vive tutta nel frontend, e si legge da un endpoint
che esiste già.

## L'interruttore

- **Sorgente**: `GET /api/soundcloud/status` (già esposto da
  `frontend/lib/api/misc.ts` come `soundcloudStatus()`), campo `username`.
  Il backend lo salva già ripulito di spazi e `@`.
- **Regola**: helper puro `personaFor(username: string | null): Persona` in
  `frontend/lib/persona.ts`, con `type Persona = "cratory" | "goodgirl"`.
  Confronto senza distinzione di maiuscole con `xgiorgix`; `null`, stringa
  vuota o qualunque altro nome danno `"cratory"`.
- **Chi lo chiama**: la Home (`frontend/app/page.tsx`), insieme alle altre
  fetch dell'`useEffect` di montaggio. Fetch fallita = `"cratory"`.
- **Niente lampeggio**: il frontespizio (scritta) si monta solo quando la
  persona è nota (stato `Persona | null`, `null` = in attesa). Oggi la scritta
  compare subito e la cabina aspetta i dati; con l'easter egg aspettano
  entrambe la stessa risposta, che in locale arriva in pochi millisecondi.
  L'ingresso "dal rumore" (`useAsciiIntro`) parte quando la scritta monta,
  quindi si risolve direttamente nella parola giusta: mai CRATORY che poi
  diventa DJ GOODGIRL.

## La scritta

`AsciiWordmark` (`frontend/components/dashboard/ascii-wordmark.tsx`) prende
due prop nuove, entrambe con default che lasciano la Home com'è:

- `word` (default `"CRATORY"`): la parola composta dai glifi.
- `title` (default `"Cratory"`): il testo dell'`h1` nascosto per gli
  assistivi. Per l'easter egg: `"DJ Goodgirl"`.

L'alfabeto `GLYPHS` si estende con **D, J, G, I, L** e lo **spazio** (cinque
colonne vuote), sempre 5×5, solo `#` e spazio. Le lettere ora sono tutte e sole
quelle di CRATORY e di DJ GOODGIRL: `ACDGIJLORTY` più lo spazio. Glifi nuovi:

```text
D       J       G       I       L
####    #####    ####   #####   #
#   #       #   #         #     #
#   #       #   # ###     #     #
#   #   #   #   #   #     #     #
####     ###     ####   #####   #####
```

DJ GOODGIRL fa 65 colonne (11 caratteri × 5 + 10 separatori) contro le 41 di
CRATORY. `WORDMARK_LINES` resta la costante di CRATORY; la Home compone la
parola con `wordmarkLines(word)`.

**Corpo del carattere.** Il `sizeClass` della Home dipende dalla persona:

- CRATORY: quello di oggi
  (`text-[12px] sm:text-lg md:text-xl lg:text-[min(4.1cqh,4.5cqw)]`).
- DJ GOODGIRL: un passo sotto perché stia nella stessa larghezza:
  `text-[7px] sm:text-sm md:text-lg lg:text-[min(4.1cqh,2.8cqw)]`.
  Sul telefono 65 colonne a 7px sull'advance di DM Mono (~0,6em) fanno ~273px,
  dentro i 309 disponibili; da lg in su `2.8cqw` è `4.5 × 41 / 65`.
  Le misure si verificano in preview e si aggiustano lì se serve; il vincolo
  è "nessuna barra di scorrimento nella cornice".

## La cabina

`djFrame` (`frontend/components/dashboard/ascii-dj.tsx`) accetta
`figure?: "boy" | "girl"` nelle opzioni (default `"boy"`, il DJ di oggi). La
figura è ciò che cambia nel template; l'aria, i tweeter, i woofer, i piatti,
le onde e le barre restano identici.

Il template `girl` è `SCENE` con tre righe ritoccate, ogni sostituzione lunga
quanto il pezzo che rimpiazza, agganciata con `indexOf` sul template di base
(niente coordinate a mano):

```text
riga 1   ///       →  ()()      ricci, alla colonna di (oo)
riga 2   _(oo)_    →  /(oo)\    capelli ai lati del viso
riga 3   //    //  →  //\  ///  scollo a V fra le braccia
riga 4   invariata (la consolle: niente gonna, scelta a mockup)
```

Le posizioni animate (`AT`) si calcolano per template, una volta sola per
ciascuno: in `girl` `indexOf("(oo)")` trova ancora il viso, quindi sbattere
di ciglia `(--)` e ammiccamento `(o-)` funzionano come oggi, dentro `/…\`.

`AsciiDj` prende la stessa prop `figure` e la passa a `djFrame`; la Home
gliela passa in base alla persona.

## I cuori nell'aria

Richiesta arrivata dopo i mockup: "dei cuoricini nell'ambiente quando parte a
suonare". L'ambiente è `AsciiAtmosphere`
(`frontend/components/dashboard/ascii-atmosphere.tsx`), il pulviscolo che
sale dietro tutta la composizione: a musica ferma è invisibile
(`AIR_IDLE_GLOW = 0`) e si accende quando dall'app esce suono. Basta quindi
cambiare di cosa è fatto il pulviscolo, non quando si vede.

- `AsciiAtmosphere` prende `hearts?: boolean` (default `false`). La Home lo
  passa `true` solo con la persona goodgirl.
- `airParticles(count, seed, glyphs)` prende la tavolozza come terzo
  parametro (default quella di oggi). La tavolozza dei cuori è
  `["·", ".", "♥", "'", ",", "♥"]`: un terzo delle particelle è un cuore, il
  resto è il pulviscolo di sempre. Il campo dei cuori è una costante calcolata
  una volta, come quello di oggi.
- Il cuore `♥` non sta in DM Mono e cade sul font di fallback. Qui è
  accettabile, a differenza della cabina e della scritta: ogni particella è un
  elemento posizionato per conto suo, non una cella di una griglia monospace,
  quindi la larghezza del glifo non sposta nulla.
- I cuori portano la classe `air-heart`, in `app/globals.css` subito dopo
  `.air-near`: `color: var(--c-danger)`, lo stesso rosso del colpo di cassa.
  Restano soggetti a `--air-glow` e a `air-still` come le altre particelle.

## Test

Tutti in `frontend/tests`, con vitest.

- `ascii-atmosphere.test.tsx` (nuovo): la tavolozza di default non produce
  cuori; quella dei cuori ne produce fra 20 e 60 su 120 particelle (un terzo,
  con tolleranza); `<AsciiAtmosphere active hearts />` rende span con `♥` e
  classe `air-heart`, `<AsciiAtmosphere active />` nessuno.

- `persona.test.ts`: `xgiorgix`, `XGIORGIX` → `goodgirl`; `null`, `""`,
  `giorgia`, `xgiorgix2` → `cratory`.
- `ascii-wordmark.test.tsx`: il denominatore delle lettere passa da 6 a 12
  (11 lettere + spazio); l'elenco atteso diventa `ACDGIJLORTY` più lo spazio;
  `wordmarkLines("DJ GOODGIRL")` dà 5 righe da 65 colonne; lo spazio è 5
  colonne vuote; `title` e `word` cambiano h1 e arte, e i default restano
  CRATORY/Cratory.
- `ascii-dj.test.tsx`: `djFrame(t, { figure: "girl" })` ha le stesse
  dimensioni di `boy` su molti tick; contiene `()()`, `/(oo)\`, `//\  ///`;
  `boy` non li contiene (denominatore); il blink `(--)` compare in `girl` sul
  tick giusto; `djFrame(t)` senza opzioni è identico a `figure: "boy"`.
- `home-persona.test.tsx`: la Home con `@/lib/api` mockato. Con
  `soundcloudStatus` che risponde `xgiorgix` l'h1 dice "DJ Goodgirl", l'arte
  contiene `/(oo)\` e l'atmosfera ha cuori; con un altro username o con la
  fetch che fallisce l'h1 dice "Cratory" e non ci sono cuori. Prima della
  risposta nessun h1 (niente lampeggio).

## Fuori scope

Impostazioni, backend, i18n, Tauri, lo spettro della Home e le tre righe
d'aria sopra la cabina (che sono una griglia monospace: lì un cuore
disallineerebbe le colonne).
