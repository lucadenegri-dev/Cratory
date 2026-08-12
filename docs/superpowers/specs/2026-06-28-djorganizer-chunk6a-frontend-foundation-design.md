# DjOrganizer — Chunk 6a: Frontend Fondazione + SOURCES + FILES

> Data: 2026-06-28 · Stato: design approvato (mockup validati), pronto per il plan.
> Primo dei tre sub-chunk del Frontend (6a · 6b · 6c). Spec madre:
> [2026-06-27-djorganizer-design.md](2026-06-27-djorganizer-design.md).

## 1. Contesto

Il backend (chunk 1–4) è completo e in `main`: scan → inspector/dedup → plan/conflict →
apply/undo, esposto via API REST. Il chunk 5 (Bridge Cratory) è **saltato** (non serve al
flusso dell'utente). Resta il **Frontend** (chunk 6), spezzato in 3 sub-chunk:

| # | Sub-chunk | Pagine |
|---|---|---|
| **6a** | **Fondazione + SOURCES + FILES** | scaffold, design system, shell, SOURCES, FILES |
| 6b | ISSUES + DUPLICATES | revisione issue + doppioni |
| 6c | PLAN + HISTORY + SETTINGS | piano/apply, storico/undo, impostazioni (incl. `target_root`) |

Questa spec copre **6a**: lo scheletro dell'intera UI + le prime due pagine. Estetica
**copiata da Cratory** (`~/Develop/DJProject01/frontend`), identità propria di DjOrganizer.

## 2. Scope

**Dentro:**
- Scaffold Next.js 16 / React 19 / Tailwind 4 / TypeScript (come Cratory).
- Port del **design system**: token CSS (`globals.css`), `EditorialShell` (INDEX·CONTENT·
  MARGINALIA), `PageLayout`, `ui.tsx` (Button/Badge/Card/Input/Table), `theme-toggle`,
  `clock`, `index-nav`, `jobs-provider`, loader **EqMeter**.
- Client API tipizzato (`lib/api.ts`).
- Pagine **SOURCES** (radici + scan come job) e **FILES** (tabella densa).
- Due **endpoint backend read-only nuovi** che il frontend richiede: `GET /api/files` e
  `GET /api/library/stats`.

**Fuori:** pagine ISSUES/DUPLICATES (6b), PLAN/HISTORY/SETTINGS e la UI di `target_root`
(6c). Le voci di nav di queste sezioni esistono ma puntano a un placeholder "in arrivo".

## 3. Design (validato coi mockup)

- **Estetica "editorial archive" di Cratory**, copiata: monospace (IBM Plex Mono),
  monocromo, filetti, angoli squadrati (radius 0), due temi **Dark** (default) e **Paper**.
  Rosso (`--c-danger`) solo per errori veri. Numeri tabellari per bitrate/durata.
- **Shell a 3 colonne `EditorialShell`:** INDEX (sinistra) con wordmark **DJORGANIZER** +
  nav delle 7 sezioni con conteggi + theme-toggle e clock in basso · CONTENT (centro, la
  pagina) · MARGINALIA (destra, statistiche/contesto).
- **FILES:** tabella densa — colonne `PATH · ARTIST · TITLE · FMT · KBPS · DUR · !`, dove
  `!` è l'indicatore issue: `▲N` rosso (errori), `●N` giallo (warning), `·` pulito, `⧉`
  doppione. Filtri (tutti / con issue / per radice) + sort. MARGINALIA = conteggi
  (file, issue per severità, doppioni) + breakdown formati.
- **SOURCES:** riga "aggiungi radice" (path + etichetta + AGGIUNGI) in cima; tabella radici
  (`PATH · LABEL · FILES · ULTIMO SCAN · ×`); azione **SCAN** che a scan fermo è un
  bottone e durante lo scan diventa **EqMeter animato + barra di progresso + file
  corrente** (`847/1247 · hashing · …`). MARGINALIA = riepilogo ultimo scan (trovati /
  nuovi / aggiornati / spostati / mancanti / errori).
- **Scan = job non bloccante** col pattern `jobs-provider`: `POST /api/scan` avvia, polling
  di `GET /api/scan/status`, progresso live. Lo stesso provider servirà all'Apply (6c).

## 4. Architettura

```text
frontend/
  package.json · next.config.ts · tsconfig.json · postcss/tailwind config (come Cratory)
  app/
    layout.tsx          # root: font IBM Plex Mono, tema, EditorialShell + JobsProvider
    globals.css         # token --c-* (dark/paper), .tnum, classi EqMeter (port da Cratory)
    page.tsx            # redirect → /sources
    sources/page.tsx    # SOURCES
    files/page.tsx      # FILES
    [issues|duplicates|plan|history|settings]/page.tsx  # placeholder "in arrivo" (riempiti in 6b/6c)
  components/
    editorial-shell.tsx · index-nav.tsx · page-layout.tsx · ui.tsx
    theme-toggle.tsx · clock.tsx · jobs-provider.tsx · eq-meter.tsx
    sources-table.tsx · add-source.tsx · files-table.tsx
  lib/
    api.ts              # client tipizzato verso il backend
    cn.ts               # util classnames
```

- **Base URL backend:** `NEXT_PUBLIC_API_BASE` (default `http://localhost:8010`), backend
  e frontend girano separati (come Cratory). `.env.example` documentato.
- **Routing:** Next app router. La nav mostra le 7 sezioni; SOURCES/FILES funzionano, le
  altre puntano a un placeholder finché 6b/6c non le riempiono. I conteggi nella nav
  vengono da `GET /api/library/stats` (+ scan status).
- **`jobs-provider`:** context React che incapsula avvio + polling del job di scan; espone
  `{ status, phase, processed, total, result, startScan() }`. EqMeter + barra lo consumano.
- **Componenti riusabili** (`ui.tsx`): Button, Badge (severità), Card, Input, Table — la
  base per 6b/6c.

## 5. Aggiunte backend (read-only, sottili)

Il frontend richiede due endpoint che ancora non esistono (il chunk 1 espose solo
`sources`/`scan`):

- **`GET /api/files`** — lista `audio_file` per la pagina FILES. Query: `root_id?`,
  `status?` (default `present`), `has_issues?` (bool), `q?` (ricerca su path/artist/title),
  `sort?` (`path|artist|title|bitrate|duration`), `limit?`/`offset?` (paginazione, default
  500). Ogni riga: `id, path, ext, artist, title, bitrate, duration_s, status,
  issue_count` (count delle `issue` del file), `worst_severity` (`error|warning|info|null`,
  per colorare l'indicatore `▲`/`●`/`·`), `in_dup_group` (bool, per il marcatore `⧉`).
  Router sottile `routers/files.py` + schema `FileRow`.
- **`GET /api/library/stats`** — conteggi per la MARGINALIA e la nav: `files_total`,
  `by_ext` (`{flac, mp3, …}`), `issues_by_severity` (`{error, warning, info}`),
  `dup_groups`, `sources` (n. radici). Router sottile (stesso file o `routers/stats.py`).

Entrambi puri-lettura, validati Pydantic, stile dei router esistenti. Coperti da test
pytest (TestClient) come gli altri endpoint.

## 6. Errori, stati vuoti, resilienza

- **Backend spento/irraggiungibile:** la UI mostra uno stato "backend non raggiungibile"
  (non crasha); il client API gestisce i fetch falliti con un messaggio chiaro.
- **Stati vuoti:** nessuna radice → SOURCES invita ad aggiungerne una; nessun file →
  FILES invita a lanciare uno scan.
- **Scan in errore:** lo stato del job mostra l'errore nella MARGINALIA, la UI resta usabile.
- **Tema:** Dark default, toggle Paper persistito (localStorage / `data-theme`, come Cratory).

## 7. Test

Per il frontend (come Cratory): **`npm run lint` + `npm run build`** verdi sono il gate
(niente unit test). Più una **verifica live**: con backend avviato e una libreria
scansionata, SOURCES e FILES rendono i dati reali, lo scan parte come job con progresso,
i temi si commutano. I due endpoint backend nuovi hanno test pytest (TestClient).

## 8. Convenzioni

- Frontend: copia struttura e pattern di Cratory (`~/Develop/DJProject01/frontend`).
  Comandi: `cd frontend && npm install && npm run dev | lint | build`.
- Backend: SQLAlchemy 2.0, router sottili, Pydantic, output test pristine
  (`filterwarnings = error`).

## 9. Definition of Done (chunk 6a)

- `npm run lint` e `npm run build` verdi; `pytest tests` verde (coi due endpoint nuovi).
- Con backend avviato e una cartella reale: aggiungo una radice in SOURCES, lancio lo scan
  (job con EqMeter + barra), e in FILES vedo la libreria come tabella densa con gli
  indicatori issue; la MARGINALIA mostra i conteggi; il toggle Dark/Paper funziona.
- La shell con la nav delle 7 sezioni è completa; le sezioni 6b/6c sono placeholder "in
  arrivo".
