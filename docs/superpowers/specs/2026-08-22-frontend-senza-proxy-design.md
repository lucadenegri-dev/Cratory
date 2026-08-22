# ② Il frontend senza il proxy di Next

Data: 2026-08-22. Stato: **decisa da Claude in autonomia, da rivedere.**
Contesto d'insieme: `2026-08-22-tauri-decomposizione-design.md`.

> **Nota di processo.** Questa spec non è passata dal solito giro di
> approvazione: è stata scritta mentre il committente era assente, su sua
> richiesta esplicita di proseguire. La decisione della sezione 2 (le rotte
> dinamiche) è quella che cambia più codice ed è la prima cosa da rivedere.

## Problema

Il frontend oggi parla col backend attraverso `rewrites()` in
`frontend/next.config.ts`: il browser chiama `/api/*` sullo stesso host della
pagina e Next inoltra a `http://127.0.0.1:8000`. Comodo, e funziona anche da un
altro dispositivo in LAN.

In un bundle Tauri non c'è nessun server Next. Il frontend diventa un insieme di
file statici serviti dal webview, e `rewrites()` — che è codice del server Next
— semplicemente non esiste. Tre conseguenze, tutte verificate sul codice:

1. **`output: "export"` è incompatibile con `rewrites()`.** Vanno separati i due
   modi di build.
2. **Un client su due non ha un aggancio per la base URL.**
   `lib/api/client.ts:7` ha `NEXT_PUBLIC_API_URL`; `lib/organize/api.ts:8` è
   `const API = "/api/organize"` e basta. Metà app perderebbe le chiamate.
3. **Cinque rotte dinamiche non sono staticamente esportabili.**
   `tracks/[id]`, `playlists/[id]`, `sets/[id]`, `labels/[label]`,
   `shazam/[id]`. In export statico ogni segmento dinamico vuole
   `generateStaticParams`, e su id arbitrari quella lista non esiste.

## Decisioni chiave

- **Due modi di build, non due frontend.** `output: "export"` si accende con una
  variabile d'ambiente al momento del build. Senza, `npm run dev` e il
  self-hosting restano identici a oggi, `rewrites()` compreso.
- **Le rotte dinamiche diventano query string.** Vedi sezione 2 per il perché e
  per le alternative scartate.
- **Un solo aggancio di base URL, condiviso dai due client.** La ROADMAP già
  segnalava questa duplicazione fra `lib/api/client.ts` e `lib/organize/api.ts`
  come debito noto; qui smette di essere facoltativo sanarla.
- **Il CORS del backend deve ammettere l'origin del webview.** In un bundle la
  pagina non arriva più da `localhost:3000`.

## Ambito

Dentro: il modo di build statico, l'aggancio di base URL per entrambi i client,
la conversione delle cinque rotte, l'origin CORS.

Fuori: Tauri (è il ③), il packaging, il backend oltre alla riga del CORS.

Il consegnabile è verificabile da solo: `npm run build` in modo statico produce
una cartella servibile da qualunque file server, e l'app funziona puntando al
backend su `127.0.0.1:8000`.

---

## 1. Due modi di build

`next.config.ts` legge una variabile — `CRATORY_STATIC_EXPORT` — e in sua
presenza attiva `output: "export"` e **omette `rewrites()`**, che in quel modo
sarebbe comunque inerte e la cui presenza confonde soltanto.

Senza la variabile non cambia niente: `npm run dev`, l'HMR, il proxy `/api/*`,
la suite E2E su `:3211` e il `distDir` separato restano quelli di oggi.

## 2. Le rotte dinamiche

**La decisione: `/tracks/123` diventa `/tracks?id=123`.**

Le cinque pagine leggono oggi il segmento con `use(params)` su un
`Promise<{id: string}>` — per esempio `app/tracks/[id]/page.tsx:58-60`. Passano
a `useSearchParams()`. Le cartelle `[id]` spariscono e il loro contenuto sale di
un livello. I punti che costruiscono i link sono diciassette, contati:
`/tracks` 4, `/playlists` 8, `/sets` 2, `/labels` 1, `/shazam` 2.

Costo totale misurato: **23 file**.

**Le alternative, e perché sono state scartate.**

*Spedire il server Next come sidecar.* Funzionerebbe senza toccare una rotta,
ma metterebbe un runtime Node nel bundle accanto a quello Python: due
interpreti, due processi da sorvegliare, cinquanta megabyte in più, per evitare
un refactoring meccanico da 23 file. Il rapporto non regge.

*`generateStaticParams` con un id segnaposto.* Genera `tracks/segnaposto.html` e
niente altro: una richiesta per `/tracks/999` non trova nessun file, e se anche
la si servisse col segnaposto la pagina leggerebbe `"segnaposto"` come id. Non
è una soluzione parziale, è una rottura silenziosa.

*Un catch-all che smista leggendo `window.location`.* È riscrivere a mano un
router SPA sopra l'App Router di Next per non usare le query string. Più codice,
più fragile, stesso risultato.

**Il costo vero della decisione**, dichiarato: gli URL dell'app cambiano anche
per l'uso da browser, e i segnalibri esistenti si rompono. Su un'app personale a
utente singolo è accettabile, ma è una perdita reale e non va nascosta.

**Attenzione tecnica:** `useSearchParams()` obbliga la pagina a stare dentro un
confine `<Suspense>`, altrimenti il build statico fallisce. Due delle cinque
pagine hanno già la struttura giusta (`TrackPageInner` dentro `TrackPage`,
`PlaylistDetailInner` dentro `PlaylistDetail`); le altre tre vanno adeguate.

## 3. Un aggancio solo per due client

`lib/api/client.ts` e `lib/organize/api.ts` derivano la loro base da un unico
punto condiviso, che vale `""` (stesso host, com'è oggi) salvo override da
`NEXT_PUBLIC_API_URL`. Organize continua a comporre `/api/organize` sopra quella
base invece di fissarla.

Non è un rifacimento dei due client: la ROADMAP li segnala come duplicazione più
ampia (`fmtDuration`, `fmtDate`, due HTTP client interi) e quella resta un ciclo
di design a sé. Qui si unifica **solo la base URL**, che è ciò che il bundle
richiede.

## 4. Il CORS

`frontend_origin` in `backend/app/core/config.py` vale oggi
`http://localhost:3000,http://localhost:3001`. Va aggiunto l'origin del webview
Tauri. Il valore esatto va **verificato leggendolo dal webview reale nel ③**,
non assunto: è documentato come `tauri://localhost` su macOS, ma è precisamente
il tipo di dettaglio che cambia fra versioni, e sbagliarlo produce un'app che
non fa una sola chiamata riuscita senza dire perché.

Finché il ③ non lo conferma, questa sezione resta aperta di proposito.

## 5. Verifica

- Il build statico produce una cartella servibile, e ogni pagina si apre
  puntando al backend su `127.0.0.1:8000`.
- Le cinque pagine convertite funzionano da URL diretto — è il caso che il
  segmento dinamico gestiva e che le query string devono continuare a gestire.
- La suite unit (375 test su 63 file, verde prima di iniziare) resta verde, e i
  test E2E Playwright vanno aggiornati dove navigano verso le rotte convertite.
- Senza `CRATORY_STATIC_EXPORT`, `npm run dev` si comporta esattamente come
  oggi: è l'invariante gemella di quella del ①.
