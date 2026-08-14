# EQ / Waveform loaders — design

Data: 2026-06-27
Stato: approvato in brainstorming, in attesa di review spec → piano.

## 1. Contesto e obiettivo

Sostituire **tutti** gli indicatori di attesa dell'app (spinner circolari "O", barre
shimmer indeterminate, testi "Caricamento…") con un linguaggio visivo a tema DJ:

- un **EQ a colonne** (spettro con bassi/medi/alti + un "battito") per i loader
  inline e indeterminati;
- una **waveform stile rekordbox che avanza** da sinistra a destra in base alla
  percentuale reale, per le barre di progresso larghe.

Vincolo estetico: il design system dell'app e' "editorial archive" — monospace,
monocromo, squadrato (`--radius: 0px`), con **un solo** accento caldo
(`--c-danger: #d8593f` dark / `#a83a22` paper). Niente palette RGB stile rekordbox:
ci si ispira solo allo *stile*.

Riferimento integrazione: rekordbox resta fuori progetto (vedi `CLAUDE.md`). Questa
e' un'ispirazione puramente visiva, nessun dato/feature rekordbox viene introdotto.

## 2. Decisioni di design (fissate in brainstorming)

1. **Scope**: l'EQ mostra anche il progresso. Lo spinner diventa EQ animato; la barra
   job in basso diventa una waveform il cui spettro si riempie con la % reale.
2. **Struttura ibrida**: waveform dove c'e' larghezza (barra job, generazione set,
   load di pagina con %); EQ verticale mini nei bottoni da ~16px (dove la waveform
   sarebbe illeggibile).
3. **EQ inline**: stile "Picco caldo" — barre segmentate (LED ladder) monocrome con
   **tacca di picco** nell'accento caldo in cima a ogni barra.
4. **Waveform**: monocroma con **cuore caldo sui bassi** a dose **media** (gradiente
   verticale per barra: grigio punte → caldo al centro → grigio), e **testina**
   (playhead) calda sul fronte di avanzamento.

## 3. Componenti

Tutti in `frontend/components/ui.tsx`. CSS/keyframes in `frontend/app/globals.css`.
Tutti theme-aware via le variabili runtime `--c-*` (commutano con `data-theme`).

### 3.1 `Equalizer` (loader inline, ex-`Spinner`)

```tsx
export function Equalizer({ className }: { className?: string }): JSX.Element
```

- Render: contenitore `inline-flex items-end` con **4 barre** verticali segmentate
  (3 spettro + 1 "battito"). Dimensione del box dal `className` (fallback identico
  all'attuale Spinner: `h-4 w-4`).
- Ogni barra: una "scala" di segmenti (gradiente ripetuto verticale in `--c-fg`,
  gap trasparenti) con **fill** animato in altezza, piu' una **tacca di picco** in
  cima in `--c-danger`. Binario spento opzionale in `--c-border` (a queste taglie
  puo' essere omesso per pulizia: si valuta in implementazione).
- Animazione: solo CSS, 4 "lane" con durate/delay diversi (desync organico). La
  barra "battito" usa una keyframe piu' secca e regolare (kick).
- Indeterminato puro (nessun valore).
- Accessibilita': wrapper `role="status"` + `aria-label="Caricamento"`.

### 3.2 `Spinner` (alias di compatibilita')

```tsx
export const Spinner = Equalizer;
```

Mantiene il contratto `className`. Gli **11 file consumer** che importano `Spinner`
restano invariati: cambia solo l'aspetto.

### 3.3 `EqMeter` (waveform che avanza)

```tsx
export function EqMeter({ value, className }: { value: number | null; className?: string }): JSX.Element
```

- Render: striscia orizzontale di **N barre** (≈56) di una **pseudo-waveform
  deterministica** (array di ampiezze calcolato una volta a livello di modulo da una
  somma di sinusoidi — **niente `Math.random`**, per evitare mismatch di idratazione
  SSR in Next). Barre centrate sull'asse (estensione simmetrica su/giu).
- **Determinato** (`value` numerico 0–100):
  - barre con indice `< round(N * value / 100)` = **accese**, con gradiente verticale
    "cuore caldo dose media": basso/centro tendente a `--c-danger`, punte verso
    `--c-fg`/`--c-fg-strong`;
  - barre restanti = **spente** in `--c-border`;
  - **playhead**: linea sottile (2px) in `--c-danger` a `left: value%`. Crisp, niente
    blur/glow (coerenza col sistema flat).
  - Accessibilita': `role="progressbar"`, `aria-valuenow={value}`, `aria-valuemin={0}`,
    `aria-valuemax={100}`.
- **Indeterminato** (`value === null`):
  - tutte le barre spente + overlay **scan** (linea calda + scia chiara semitrasparente)
    che spazza sx→dx in loop (CSS), effetto "analisi rekordbox".
  - Accessibilita': `role="status"` + `aria-label`.
- Il caldo "dose media" e' ottenuto via `color-mix` (es.
  `color-mix(in oklab, var(--c-danger) ~60%, var(--c-fg))`) come stop centrale del
  gradiente, cosi' resta legato al tema. Valori esatti rifiniti a video.

### 3.4 `Progress` (semplificata, resta per i dati)

`Progress` perde il ramo indeterminato: firma `{ value: number }`, barra
deterministica come oggi. In fase di piano **verificare** che dopo le migrazioni
nessun chiamante passi `null` (atteso: solo `app/page.tsx` la usa, con `value`
numerico). Se cosi', rimuovere ramo indeterminato + `shimmer`; altrimenti mantenere
`number | null` e togliere solo lo shimmer.

```tsx
export function Progress({ value }: { value: number }): JSX.Element
```

Usata **solo** dalle barre-dati (copertura libreria) in dashboard — **non** e' un
loader e **non** diventa EQ/waveform.

## 4. Mappa delle modifiche (file per file)

| File | Modifica |
|---|---|
| `frontend/components/ui.tsx` | Aggiungi `Equalizer` + `EqMeter`; `Spinner = Equalizer`; semplifica `Progress` (solo `value:number`). |
| `frontend/app/globals.css` | Aggiungi keyframes EQ (4 lane + battito), keyframe scan playhead, regole `prefers-reduced-motion`. **Rimuovi** `@keyframes shimmer` e `.animate-shimmer` (diventano morti). |
| `frontend/components/jobs-provider.tsx` | `GlobalProgress`: sostituisci `Spinner + Progress` con `EqMeter value={pct}`; togli lo Spinner inline (la waveform e' gia' l'indicatore vivo); mantieni label, conteggio `processed/total`, e il `+N` per job multipli. |
| `frontend/app/set-builder/page.tsx` | `<Progress value={null} />` (≈ riga 330) → `<EqMeter value={null} />`. |
| Placeholder "Caricamento…" (≈7 punti) | Anteporre un `Equalizer` piccolo al testo, es. `<span className="inline-flex items-center gap-2"><Equalizer className="h-3.5 w-3.5" /> Caricamento…</span>`. File noti: `app/settings/page.tsx`, `app/playlists/[id]/page.tsx`, `app/labels/page.tsx`, `app/tracks/[id]/page.tsx`, `app/sets/[id]/page.tsx`, e gli stati "DIG in corso…/Cerco tracce…/Cerco alternative…" in `app/discovery/page.tsx` e `app/sets/[id]/page.tsx` (il piano enumera righe esatte). |

Gli **11 file** che usano `<Spinner/>` nei bottoni non vengono modificati (alias).

## 5. Stile, colori, temi

- Barre/waveform accese: `--c-fg`; punte/highlight: `--c-fg-strong`; spento/binario:
  `--c-border`; picco e playhead e cuore caldo: `--c-danger`.
- Tutto squadrato (nessun border-radius), coerente con `--radius: 0`.
- Adattamento automatico **dark** e **paper** perche' si usano solo variabili `--c-*`.

## 6. Animazioni & CSS

- EQ: 4 keyframe d'altezza (`eqA..eqD`) + 1 "battito" (`eqK`, spike secco), assegnate
  per `nth-child`/classi lane con durate diverse (0.6–1.05s) e `animation-delay`
  negativi per desync.
- Waveform indeterminata: keyframe `scan` che muove l'overlay `left: -14% → 100%`.
- Mantenere le animazioni GPU-friendly; preferire poche regole, niente JS di
  animazione (solo CSS).

## 7. Accessibilita' & reduced motion

- `@media (prefers-reduced-motion: reduce)`: le barre EQ si **congelano** in una
  sagoma statica sfalsata; la waveform mostra fill statico fino alla % (determinata)
  e una posizione fissa (indeterminata), senza scan.
- Ruoli/aria come in §3. I testi "Caricamento…" restano leggibili dagli screen reader.

## 8. Vincoli tecnici

- **Next 16 con breaking changes** (`frontend/AGENTS.md`): consultare
  `node_modules/next/dist/docs/` prima di scrivere codice.
- `EqMeter`/`Equalizer` sono presentazionali e **senza stato**; la pseudo-waveform e'
  deterministica → nessun rischio di hydration mismatch.

## 9. Non-obiettivi

- Non toccare le barre-dati di copertura in dashboard (`Progress` con valore reale).
- Nessun audio, nessun fingerprint, nessuna integrazione rekordbox (solo omaggio
  visivo).
- Nessuna modifica a backend, endpoint o intervalli di polling dei job.

## 10. Verifica

- `npm run lint` e `npm run build` puliti.
- Verifica visiva (dev server) di: uno spinner-in-bottone, la barra job in basso
  durante un enrichment (waveform determinata), generazione set (indeterminata), un
  "Caricamento…" di pagina.
- Verifica `prefers-reduced-motion` (freeze) e tema **dark + paper**.

## 11. Rischi / punti aperti

- Numero esatto di barre/segmenti e taglie inline: rifinitura a video.
- `color-mix` per il cuore caldo: supportato dai browser evergreen; l'app e'
  personale/self-hosted, ok. Fallback eventuale a un colore caldo statico in `--c-*`.
