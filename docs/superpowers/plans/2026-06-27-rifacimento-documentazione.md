# Rifacimento documentazione — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ridisegnare l'architettura della documentazione di Cratory così che ogni informazione abbia un solo proprietario canonico, il README sia una vetrina in inglese, e i doc riflettano il codice reale.

**Architecture:** Due livelli — vetrina (`README` in inglese) e riferimento/operativo (resto in italiano, `DESIGN` in inglese). Un "contratto anti-deriva" assegna a ogni informazione un unico file proprietario; gli altri linkano. Consolidamento delle guide agent in `CLAUDE.md` (eliminato `AGENTS.md`), spostamento di `PRODUCT`/`DESIGN` in `docs/`, audit di accuratezza di `API`/`ARCHITECTURE` contro il backend.

**Tech Stack:** Markdown, SVG (diagramma), `git mv` per gli spostamenti. Nessuna modifica al codice applicativo Python/TS (eccezione documentale: `.impeccable/design.json`).

## Global Constraints

- **Lingua per file:** `README.md` e `docs/DESIGN.md` in **inglese**; `CLAUDE.md`, `PROGRESS.md`, `docs/ARCHITECTURE.md`, `docs/API.md`, `docs/ROADMAP.md`, `docs/PRODUCT.md` in **italiano**.
- **Commit:** messaggi in italiano con prefisso conventional (`docs:`, `chore:`). **Mai** aggiungere `Co-Authored-By` (preferenza utente).
- **Nome prodotto:** **Cratory**. I path tecnici legacy (`djassistant.db`, `backend/logs/djassistant.log`) restano invariati.
- **Proprietario canonico unico** per ogni informazione (vedi spec §4). Gli altri doc linkano, non copiano.
- **Nessuna modifica al codice applicativo.** Unica eccezione consentita: `.impeccable/design.json` (fix branding).
- **Catena provider enrichment (verbatim):** `Deezer → MusicBrainz → AcousticBrainz → GetSongBPM → Last.fm`.
- **Discovery:** "Scava" usa **Discogs**; Spotify è solo resolver via `/search`; `/recommendations` non si usa.
- Spec di riferimento: `docs/superpowers/specs/2026-06-27-rifacimento-documentazione-design.md`.

---

### Task 1: Audit accuratezza `docs/API.md` vs router

**Files:**
- Modify: `docs/API.md`
- Read-only: `backend/app/routers/*.py`

**Interfaces:**
- Consumes: nulla (prima task).
- Produces: `docs/API.md` allineato ai router reali — referenziato da README (Task 9) e dall'indice CLAUDE (Task 5).

**Discrepanze note da risolvere** (rilevate in fase di planning):
- Esiste `backend/app/routers/labels.py` ma `API.md` non ha sezione Labels.
- Verificare che la rimozione di `/api/discovery/labels` (vedi PROGRESS 27/06) sia coerente con `discovery.py`.

- [ ] **Step 1: Estrarre gli endpoint reali dai router**

Run:
```bash
cd backend && grep -rnE "@router\.(get|post|patch|delete|put)" app/routers/ | sed -E 's/.*@router\.//'
```
Expected: elenco di tutte le route con metodo e path. Annotare ogni `prefix` dei router leggendo l'inizio di ciascun file (`APIRouter(prefix=...)`) e `app/main.py` per gli `include_router`.

- [ ] **Step 2: Confrontare con `docs/API.md`**

Leggere `docs/API.md` sezione per sezione e marcare: (a) endpoint documentati ma assenti nei router → da rimuovere; (b) endpoint nei router ma non documentati → da aggiungere; (c) path/metodo divergenti → da correggere. Prestare attenzione a `labels.py` (manca una sezione) e a `discovery.py`.

- [ ] **Step 3: Aggiornare `docs/API.md`**

Applicare le correzioni: aggiungere la sezione mancante (es. `## Labels` con i suoi endpoint reali), rimuovere quelli morti, correggere path/metodi. Mantenere stile e lingua (italiano) coerenti con il resto del file. Le note "Convenzioni" in coda restano.

- [ ] **Step 4: Verificare che ogni endpoint documentato esista**

Run:
```bash
cd backend && for p in $(grep -oE "/api/[a-zA-Z0-9_/{}-]+" ../docs/API.md | sort -u); do \
  base=$(echo "$p" | sed -E 's/\{[^}]+\}/{/'); \
  grep -rqE "\"$(echo "$base" | sed -E 's#/api/[a-z_]+##')" app/routers/ 2>/dev/null || echo "VERIFICA MANUALE: $p"; done
```
Expected: la lista di "VERIFICA MANUALE" deve contenere solo path con prefissi non banali; controllare a mano che ciascuno corrisponda a una route reale. Nessun endpoint documentato deve mancare dai router.

- [ ] **Step 5: Commit**

```bash
git add docs/API.md
git commit -m "docs(api): allinea API.md ai router reali (sezione labels, dead endpoint)"
```

---

### Task 2: Audit accuratezza `docs/ARCHITECTURE.md` vs codice

**Files:**
- Modify: `docs/ARCHITECTURE.md`
- Read-only: `backend/app/integrations/`, `backend/app/models.py`, `backend/app/services/`, `backend/app/routers/`

**Interfaces:**
- Consumes: nulla.
- Produces: `docs/ARCHITECTURE.md` allineato al codice — referenziato da README (Task 9) e indice CLAUDE (Task 5).

**Discrepanze note da risolvere:**
- `backend/app/integrations/discogs.py` esiste ma la tabella "Integrazioni" non cita **Discogs** (centrale per "Scava"). Aggiungerlo (stato: attiva; nota: crate digging per genere/etichetta).
- Verificare la lista layer backend contro `app/` reale (presenza di `labels.py` tra i router, `db.py`, `tools/`).

- [ ] **Step 1: Estrarre la struttura reale**

Run:
```bash
cd backend && echo "ROUTERS:" && ls app/routers/*.py && echo "INTEGRATIONS:" && ls app/integrations/*.py && echo "MODELS:" && grep -E "^class " app/models.py
```
Expected: elenco router, integrazioni e classi modello reali.

- [ ] **Step 2: Confrontare le quattro aree di ARCHITECTURE.md**

Verificare contro il codice: (a) **Layer backend** (sezione "Layer backend" + lista router); (b) **catena provider** `Deezer → MusicBrainz → AcousticBrainz → GetSongBPM → Last.fm` (in `integrations/` e nel servizio enrichment); (c) **tabella Integrazioni** (manca Discogs); (d) **Modello dati** (entità `Playlist`, `Track`, `Setlist`, `SetlistTrack`, `EnrichmentCache`, `DjSet`, `DjSetTrack` vs `models.py`). Verificare anche i flussi Discovery (expand Last.fm/Spotify vs dig Discogs) contro `routers/discovery.py` e i servizi.

- [ ] **Step 3: Aggiornare `docs/ARCHITECTURE.md`**

Aggiungere Discogs alla tabella Integrazioni; correggere eventuali entità/layer divergenti; allineare i flussi. Mantenere italiano e stile esistenti.

- [ ] **Step 4: Verificare la tabella Integrazioni vs integrations/**

Run:
```bash
cd backend && for i in $(ls app/integrations/*.py | xargs -n1 basename | sed 's/\.py//' | grep -vE "^_|__init__"); do \
  grep -qi "$i" ../docs/ARCHITECTURE.md || echo "MANCANTE in ARCHITECTURE: $i"; done
```
Expected: nessuna riga "MANCANTE" (ogni integrazione reale è citata; `_http` e dunder esclusi). Se compare un'integrazione legittimamente interna, decidere consapevolmente se documentarla.

- [ ] **Step 5: Commit**

```bash
git add docs/ARCHITECTURE.md
git commit -m "docs(architecture): allinea al codice (integrazione Discogs, layer, modello dati)"
```

---

### Task 3: Spostare e riconciliare `PRODUCT.md` → `docs/PRODUCT.md`

**Files:**
- Move: `PRODUCT.md` → `docs/PRODUCT.md`
- Modify: `docs/PRODUCT.md`
- Read-only: `docs/DESIGN.md`, `docs/ROADMAP.md`

**Interfaces:**
- Consumes: la direzione prodotto di `docs/ROADMAP.md` e il sistema visivo di `docs/DESIGN.md`.
- Produces: `docs/PRODUCT.md` riconciliato — referenziato da README (Task 9) e indice CLAUDE (Task 5).

- [ ] **Step 1: Spostare il file**

Run:
```bash
git mv PRODUCT.md docs/PRODUCT.md
```
Expected: `docs/PRODUCT.md` esiste, `PRODUCT.md` in root no.

- [ ] **Step 2: Riscrivere le sezioni contraddittorie**

In `docs/PRODUCT.md` riscrivere tre sezioni per allinearle all'editorial-archive (fonte: `docs/DESIGN.md`):
- **Brand Personality:** da "Fluida, creativa, sperimentale" + "accento lime è la luce dello studio" → personalità coerente con DESIGN: strumento **quiet, typographic, archival**; il crate digging resta un atto con energia, ma resa **monocroma e tipografica**, non cromatica. Rimuovere ogni riferimento al lime/accento colorato (il sistema ha **un solo rosso**, solo per errori/distruzione).
- **Anti-references:** rimuovere la voce che rifiuta "cream backgrounds / pastel gradients" come anti-pattern assoluto: il tema **paper (cream) è una scelta deliberata** del sistema. Riformulare l'anti-reference "AI tool hype" così da colpire i pastelli/gradient/rounded, **non** il cream in sé. Mantenere le anti-reference valide (consumer music app, generic SaaS dashboard, legacy DJ software).
- **Design Principles:** correggere il principio 4 ("L'accento lime è la luce dello studio") → riformulare sul **monocromo + hairline + tabular figures** come linguaggio visivo. Gli altri principi (dati prima, ogni schermata spinge avanti, denso ma respirabile, energia sperimentale) restano se non contraddicono DESIGN.

- [ ] **Step 3: Mantenere le parti valide e linkare DESIGN**

Lasciare invariate **Users**, **Job to be done / Product Purpose**, **Accessibility**. Allineare la descrizione prodotto alla direzione **personale/self-hosted** (non SaaS) di `docs/ROADMAP.md`. Aggiungere in testa o coda un rimando: il dettaglio del sistema visivo vive in `docs/DESIGN.md`.

- [ ] **Step 4: Verificare l'assenza delle contraddizioni**

Run:
```bash
grep -niE "lime|accento .*color|cream background" docs/PRODUCT.md || echo "OK: nessuna contraddizione residua"
```
Expected: `OK: nessuna contraddizione residua` (nessun match su lime/accento colorato; "cream" può comparire solo se descritto come scelta deliberata, da verificare a vista).

- [ ] **Step 5: Commit**

```bash
git add -A docs/PRODUCT.md PRODUCT.md
git commit -m "docs(product): sposta in docs/ e riconcilia con l'editorial-archive (no lime, paper deliberato)"
```

---

### Task 4: Spostare `DESIGN.md` → `docs/DESIGN.md` e fixare il branding in `.impeccable/design.json`

**Files:**
- Move: `DESIGN.md` → `docs/DESIGN.md`
- Modify: `.impeccable/design.json`

**Interfaces:**
- Consumes: nulla.
- Produces: `docs/DESIGN.md` — referenziato da README (Task 9), PRODUCT (Task 3) e indice CLAUDE (Task 5).

- [ ] **Step 1: Spostare il file**

Run:
```bash
git mv DESIGN.md docs/DESIGN.md
```
Expected: `docs/DESIGN.md` esiste, `DESIGN.md` in root no. Contenuto invariato (la skill `impeccable` legge `.impeccable/design.json`, non il markdown — `.impeccable/live/config.json` punta a `frontend/app/layout.tsx`).

- [ ] **Step 2: Correggere il branding nel JSON**

In `.impeccable/design.json` sostituire le occorrenze stale di SetArc con Cratory:
- `"title": "Design System: SetArc — Editorial Archive"` → `"title": "Design System: Cratory — Editorial Archive"`
- `"purpose": "The SETARC wordmark — uppercase, 0.16em tracking."` → `"purpose": "The CRATORY wordmark — uppercase, 0.16em tracking."`

- [ ] **Step 3: Verificare l'assenza di SetArc/SETARC**

Run:
```bash
grep -niE "setarc" .impeccable/design.json docs/DESIGN.md || echo "OK: nessun SetArc residuo"
```
Expected: `OK: nessun SetArc residuo`.

- [ ] **Step 4: Commit**

```bash
git add -A docs/DESIGN.md DESIGN.md .impeccable/design.json
git commit -m "docs(design): sposta DESIGN in docs/ e correggi branding SetArc->Cratory nel design.json"
```

---

### Task 5: Consolidare la guida agent in `CLAUDE.md`, eliminare `AGENTS.md`

**Files:**
- Modify: `CLAUDE.md`
- Delete: `AGENTS.md`
- Read-only: `AGENTS.md` (per estrarre il contenuto da assorbire)

**Interfaces:**
- Consumes: i path `docs/PRODUCT.md` e `docs/DESIGN.md` (creati nei Task 3-4).
- Produces: `CLAUDE.md` come unica guida agent con indice "fonte di verità" completo.

- [ ] **Step 1: Assorbire in `CLAUDE.md` il contenuto unico di `AGENTS.md`**

Confrontare i due file e portare in `CLAUDE.md` ciò che è solo in `AGENTS.md` e ancora utile: dettaglio **layer backend** (la mappa `routers/services/repositories/...`), **identità tracce** (`platform/platform_track_id/isrc/url`, ordine deduplica, stati traccia), **catena provider**, **nota Next.js 16** (`frontend/CLAUDE.md` va letto prima di toccare il frontend). Le 8 regole non negoziabili e i comandi sono già in entrambi: tenerne **una sola copia** in `CLAUDE.md`.

- [ ] **Step 2: Aggiornare l'indice "fonte di verità" e la self-description**

In `CLAUDE.md`:
- Aggiornare la lista "Leggere in quest'ordine" / "Fonte di verità" includendo `docs/PRODUCT.md` e `docs/DESIGN.md` e **rimuovendo** il riferimento ad `AGENTS.md`.
- Riscrivere l'apertura: rimuovere "serve come entrypoint per l'AI usata insieme a Codex" e "Non eliminarlo durante cleanup documentali". `CLAUDE.md` diventa semplicemente "la guida per l'AI collaboratrice del progetto".

- [ ] **Step 3: Eliminare `AGENTS.md`**

Run:
```bash
git rm AGENTS.md
```
Expected: `AGENTS.md` rimosso dall'indice git.

- [ ] **Step 4: Verificare assenza di riferimenti pendenti**

Run:
```bash
grep -rn "AGENTS.md" --include="*.md" . | grep -v node_modules | grep -v "docs/superpowers/" | grep -vE "frontend/(AGENTS|CLAUDE)\.md" || echo "OK: nessun riferimento ad AGENTS.md a livello root"
```
Expected: `OK: nessun riferimento ad AGENTS.md a livello root` (i file frontend sono gestiti nel Task 6; gli spec/plan storici in `docs/superpowers/` sono esclusi).

- [ ] **Step 5: Commit**

```bash
git add -A CLAUDE.md AGENTS.md
git commit -m "docs(agent): unifica la guida agent in CLAUDE.md ed elimina AGENTS.md (toolchain solo-Claude)"
```

---

### Task 6: Consolidare le regole frontend in `frontend/CLAUDE.md`, eliminare `frontend/AGENTS.md`

**Files:**
- Modify: `frontend/CLAUDE.md`
- Delete: `frontend/AGENTS.md`

**Interfaces:**
- Consumes: nulla.
- Produces: `frontend/CLAUDE.md` autosufficiente (niente più `@AGENTS.md`).

- [ ] **Step 1: Inserire le regole Next.js direttamente in `frontend/CLAUDE.md`**

Sostituire il contenuto attuale di `frontend/CLAUDE.md` (oggi solo `@AGENTS.md`) con le regole reali oggi in `frontend/AGENTS.md`:
```markdown
<!-- BEGIN:nextjs-agent-rules -->
# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` before writing any code. Heed deprecation notices.
<!-- END:nextjs-agent-rules -->
```

- [ ] **Step 2: Eliminare `frontend/AGENTS.md`**

Run:
```bash
git rm frontend/AGENTS.md
```
Expected: `frontend/AGENTS.md` rimosso.

- [ ] **Step 3: Verificare che non resti l'indirezione**

Run:
```bash
grep -n "@AGENTS" frontend/CLAUDE.md || echo "OK: nessuna indirezione @AGENTS"
ls frontend/AGENTS.md 2>/dev/null && echo "ERRORE: frontend/AGENTS.md ancora presente" || echo "OK: frontend/AGENTS.md rimosso"
```
Expected: `OK: nessuna indirezione @AGENTS` e `OK: frontend/AGENTS.md rimosso`.

- [ ] **Step 4: Commit**

```bash
git add -A frontend/CLAUDE.md frontend/AGENTS.md
git commit -m "docs(frontend): inline regole Next.js in frontend/CLAUDE.md ed elimina frontend/AGENTS.md"
```

---

### Task 7: Riconciliare `ROADMAP` (canonico) e `PROGRESS` (diario)

**Files:**
- Modify: `docs/ROADMAP.md`, `PROGRESS.md`
- Read-only: entrambi (confronto pre-dedup)

**Interfaces:**
- Consumes: nulla.
- Produces: `docs/ROADMAP.md` unica fonte di verità stato/direzione; `PROGRESS.md` ridotto a diario + ripresa.

- [ ] **Step 1: Garantire che `ROADMAP` catturi lo stato unico di `PROGRESS`**

Confrontare le sezioni di stato dei due file. Qualsiasi informazione di **stato/decisione/priorità** presente solo in `PROGRESS` ("Funzionalità completate", "Prossimi step", "Prossimi passi consigliati", "Decisione 2026-06-23") che **non** sia già in `ROADMAP` va portata in `ROADMAP` (nella sezione pertinente: Stato completato / Prossimi passi / Decisioni consolidate / Direzione prodotto). Niente perdita di informazione.

- [ ] **Step 2: Ridurre `PROGRESS.md` a diario + ripresa**

Riscrivere `PROGRESS.md` tenendo **solo**:
- intestazione: ultimo aggiornamento, nome prodotto, **fase corrente corretta** (rimuovere "documentazione riscritta" residuo del reset SetArc; descrivere la fase reale);
- le **milestone datate** (18/06 reset, 23/06 rebranding+etichette, 27/06 audit) come narrativa;
- un **punto di ripresa** ("dove riprendo") che **linka** `docs/ROADMAP.md` per le priorità invece di riportarle.

Rimuovere da `PROGRESS`: "Funzionalità completate", "Prossimi step", "Prossimi passi consigliati", "Decisione 2026-06-23" (→ ROADMAP). Ridurre "Note operative" e "Verifiche consigliate" a un puntatore (i comandi vivono in `README`/`CLAUDE`; i path operativi in `ARCHITECTURE`).

- [ ] **Step 3: Verificare che lo stato non sia più duplicato**

Run:
```bash
grep -niE "funzionalit.* completate|prossimi step|prossimi passi consigliati" PROGRESS.md || echo "OK: PROGRESS non duplica più lo stato"
```
Expected: `OK: PROGRESS non duplica più lo stato`.

- [ ] **Step 4: Verificare il rimando a ROADMAP**

Run:
```bash
grep -n "ROADMAP" PROGRESS.md && echo "OK: PROGRESS linka ROADMAP"
```
Expected: almeno un match e `OK: PROGRESS linka ROADMAP`.

- [ ] **Step 5: Commit**

```bash
git add docs/ROADMAP.md PROGRESS.md
git commit -m "docs(status): ROADMAP unica fonte di verità, PROGRESS ridotto a diario+ripresa"
```

---

### Task 8: Creare il diagramma architettura attuale e ritirare gli orfani

**Files:**
- Create: `docs/architettura.svg`
- Delete: `docs/flusso-servizi.png`, `docs/servizi-sinergie.svg`
- Read-only: `docs/ARCHITECTURE.md` (sezione "Flusso principale")

**Interfaces:**
- Consumes: il flusso descritto in `docs/ARCHITECTURE.md`.
- Produces: `docs/architettura.svg` — incorporato dal README (Task 9).

- [ ] **Step 1: Creare `docs/architettura.svg` coerente col design system**

Diagramma del flusso principale (fonte: `docs/ARCHITECTURE.md` → "Flusso principale"), nodi in sequenza:
`Spotify / import manuale → Playlist Importer → normalizzazione+deduplica → SQLite → Music Feature Enrichment (cache) → Library / Gap Analysis → Candidate Engine → Set Builder deterministico → AI Set Agent (opz.) → Validation Engine → Set Editor / Export / Discovery write-back`,
più i due rami Discovery (expand Last.fm/Spotify; dig Discogs) e il ramo Shazam come blocco separato.
Vincoli visivi (da `docs/DESIGN.md`, tema dark): sfondo `#0d0d0d`, box `#161616` con bordo hairline `#2b2b2b`, testo `#c4c4c4`/`#ededed`, **monocromo** (nessun colore tranne eventuale `#d8593f` solo se serve marcare un errore/limite — qui non serve), font monospace (`ui-monospace, 'SF Mono', Menlo, monospace`), **angoli square** (no border-radius), nessuna ombra. `viewBox` orizzontale (es. `0 0 1200 700`).

- [ ] **Step 2: Eliminare gli asset orfani**

Run:
```bash
git rm docs/flusso-servizi.png docs/servizi-sinergie.svg
```
Expected: entrambi rimossi. La copia untracked `docs/servizi-sinergie.svg` nel working tree, se ricompare, **non** va aggiunta (verificare con `git status`).

- [ ] **Step 3: Verificare gli asset**

Run:
```bash
ls docs/architettura.svg && echo "OK: diagramma creato"
ls docs/flusso-servizi.png docs/servizi-sinergie.svg 2>/dev/null && echo "ERRORE: orfani ancora presenti" || echo "OK: orfani ritirati"
```
Expected: `OK: diagramma creato` e `OK: orfani ritirati`.

- [ ] **Step 4: Commit**

```bash
git add docs/architettura.svg
git add -A docs/flusso-servizi.png docs/servizi-sinergie.svg
git commit -m "docs(diagram): nuovo diagramma architettura monocromo, ritirati gli asset orfani"
```

---

### Task 9: Riscrivere `README.md` in inglese (vetrina)

**Files:**
- Modify: `README.md`
- Read-only: `docs/ARCHITECTURE.md`, `docs/ROADMAP.md`, `docs/PRODUCT.md`, `backend/.env.example`, `docs/architettura.svg`

**Interfaces:**
- Consumes: tutti i doc già allineati (Task 1-8) e il diagramma (Task 8).
- Produces: README vetrina con tabella documentazione completa.

- [ ] **Step 1: Riscrivere il README in inglese con questa struttura**

Sezioni e contenuto (in **inglese**):
- **Title + tagline:** `# Cratory` + una riga: a personal, self-hosted workbench that turns streaming playlists into thought-out DJ sets.
- **What & why:** pitch riformulato sulla natura reale — strumento **personale/self-hosted mono-utente**, esplicitamente **non** un SaaS Spotify; il vincolo policy Spotify è una **scelta di design** (qualità del prodotto, non scala), non un limite subìto. Niente audio playback, niente storage audio; Shazam usa download temporanei solo per il fingerprinting.
- **Features:** bullet sintetici derivati dall'attuale "Cosa fa" del README (import Spotify/liked/manuale, deduplica, enrichment multi-provider, fonte/confidenza, correzioni manuali, set deterministico+AI, classificazione transizioni, Discovery per gusto + Scava via Discogs, identificazione mix Shazam).
- **Architecture at a glance:** incorporare `docs/architettura.svg` (`![Architecture](docs/architettura.svg)`) + 3-4 frasi su **motore deterministico vs AI** (l'AI non riceve mai tutta la libreria; cap 60 candidate; output validato).
- **Tech stack:** blocco come l'attuale (Python/FastAPI/SQLAlchemy/Pydantic; Next.js 16/React/Tailwind; SQLite; LLM dietro interfaccia; provider esterni — **includere Discogs**).
- **Quickstart:** setup backend + frontend condensato (venv, requirements, `.env`, uvicorn; npm install/dev). Includere le **env minime** e **aggiungere `DISCOGS_TOKEN`** tra i provider consigliati (oggi mancante) insieme a Spotify/MusicBrainz/GetSongBPM/Last.fm/AI.
- **Documentation:** tabella link che copre **tutti** i doc: `docs/ARCHITECTURE.md`, `docs/API.md`, `docs/ROADMAP.md`, `docs/PRODUCT.md`, `docs/DESIGN.md`, `PROGRESS.md`, `CLAUDE.md` (con `docs/PRODUCT.md` e `docs/DESIGN.md` ora inclusi; **non** citare `AGENTS.md`).
- **Status:** 1-2 righe con rimando a `docs/ROADMAP.md` come fonte di verità.

Mantenere il README **scorrevole** per un lettore esterno: il pitch/feature/architettura vengono prima del muro setup. I dettagli operativi estesi (pulizia DB, PowerShell, workflow a 9 step) possono restare in coda in forma condensata o ridursi a rimandi.

- [ ] **Step 2: Verificare lingua e completezza tabella doc**

Run:
```bash
grep -qiE "personal|self-hosted" README.md && echo "OK: pitch EN presente"
for d in docs/ARCHITECTURE.md docs/API.md docs/ROADMAP.md docs/PRODUCT.md docs/DESIGN.md PROGRESS.md CLAUDE.md; do \
  grep -q "$d" README.md || echo "MANCA nella tabella doc: $d"; done
grep -q "AGENTS.md" README.md && echo "ERRORE: README cita ancora AGENTS.md" || echo "OK: nessun riferimento AGENTS"
grep -qi "DISCOGS_TOKEN" README.md && echo "OK: DISCOGS_TOKEN documentato"
```
Expected: `OK: pitch EN presente`, nessuna riga "MANCA", `OK: nessun riferimento AGENTS`, `OK: DISCOGS_TOKEN documentato`.

- [ ] **Step 3: Verificare che i link del README risolvano**

Run:
```bash
for l in $(grep -oE "\]\(([^)]+\.(md|svg|png))\)" README.md | sed -E 's/\]\(//; s/\)//'); do \
  [ -f "$l" ] || echo "LINK ROTTO: $l"; done; echo "fine check link"
```
Expected: nessuna riga "LINK ROTTO".

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs(readme): riscrive il README come vetrina in inglese (pitch, architettura, Discogs)"
```

---

### Task 10: Verifica finale indici e link cross-doc

**Files:**
- Modify (solo se emergono fix): qualsiasi doc con link rotti o riferimenti pendenti

**Interfaces:**
- Consumes: tutti i doc finali.
- Produces: documentazione internamente coerente, nessun orfano, nessun riferimento pendente.

- [ ] **Step 1: Nessun riferimento residuo ad `AGENTS.md`**

Run:
```bash
grep -rn "AGENTS.md" --include="*.md" . | grep -v node_modules | grep -v "docs/superpowers/" || echo "OK: nessun AGENTS.md residuo"
```
Expected: `OK: nessun AGENTS.md residuo` (gli spec/plan storici in `docs/superpowers/` sono ammessi).

- [ ] **Step 2: Tutti i link markdown interni risolvono**

Run:
```bash
for f in README.md CLAUDE.md PROGRESS.md docs/ARCHITECTURE.md docs/API.md docs/ROADMAP.md docs/PRODUCT.md docs/DESIGN.md; do \
  for l in $(grep -oE "\]\(([^)#]+\.(md|svg|png))" "$f" 2>/dev/null | sed -E 's/\]\(//'); do \
    p="$l"; case "$l" in /*) p=".$l";; docs/*) p="$l";; *) [ "${f%/*}" = "docs" ] && p="docs/$l" || p="$l";; esac; \
    [ -f "$p" ] || echo "$f -> LINK ROTTO: $l"; done; done; echo "fine check"
```
Expected: nessuna riga "LINK ROTTO". Verificare a vista i path relativi ambigui.

- [ ] **Step 3: Nessun doc orfano (ogni doc raggiungibile da README o CLAUDE)**

Run:
```bash
for d in docs/ARCHITECTURE.md docs/API.md docs/ROADMAP.md docs/PRODUCT.md docs/DESIGN.md PROGRESS.md; do \
  (grep -q "$d" README.md || grep -q "$d" CLAUDE.md) || echo "ORFANO: $d"; done; echo "fine check orfani"
```
Expected: nessuna riga "ORFANO".

- [ ] **Step 4: Coerenza nome prodotto (no SetArc/DJ Assistant come nome corrente)**

Run:
```bash
grep -rniE "\bsetarc\b" --include="*.md" --include="*.json" . | grep -v node_modules | grep -v "docs/superpowers/" | grep -viE "storic|legacy|nome.*provvisorio|precedentemente" || echo "OK: nessun SetArc come nome corrente"
```
Expected: `OK: nessun SetArc come nome corrente` (eventuali match devono essere solo riferimenti storici espliciti).

- [ ] **Step 5: Commit (se ci sono stati fix)**

```bash
git add -A
git commit -m "docs: verifica finale link e indici cross-doc" || echo "Niente da committare: documentazione già coerente"
```

---

## Self-Review (eseguita)

**Spec coverage:** ogni sezione dello spec è coperta — §3 mappa file → Task 3-9; §4 contratto anti-deriva → Task 7 (stato) + Task 5 (indici); §5 spec per file → Task 1-9 (uno per file); §6 audit accuratezza → Task 1-2 (+ DISCOGS_TOKEN in Task 9); eliminazioni/aggiunte → Task 5,6,8; criteri di successo → Task 10. Nessun gap.

**Placeholder scan:** nessun "TBD/TODO/handle appropriately"; le sezioni da riscrivere hanno contenuto puntuale (sezioni esatte, cosa cambiare, perché). Il testo finale di README/PRODUCT è specificato per sezione anziché incollato per intero — scelta deliberata per un task documentale, con punti di contenuto espliciti e non ambigui.

**Type consistency:** i path file sono coerenti tra task (`docs/PRODUCT.md`, `docs/DESIGN.md`, `docs/architettura.svg`); l'ordine risolve le dipendenze (i file si spostano in `docs/` nei Task 3-4 prima di essere indicizzati nel Task 5 e linkati nel Task 9; il diagramma nel Task 8 prima del README nel Task 9).
