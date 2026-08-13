# Revisione totale codice e documentazione — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rimuovere codice morto e ridondanze evidenti da backend e frontend, archiviare le docs storiche, riscrivere le docs vive per un lettore umano.

**Architecture:** Cinque fasi in ordine vincolato (baseline → backend → frontend → docs storiche → docs vive), rilevamento a doppia conferma (strumento statico + grep indipendente), tre livelli di azione (rimozione / consolidamento / segnalazione), checkpoint utente a fine fase.

**Tech Stack:** vulture (Python dead code), knip + depcheck via npx (TS/npm), pytest, vitest, eslint, next build.

**Spec:** `docs/superpowers/specs/2026-08-13-revisione-codice-docs-design.md`

## Global Constraints

- Worktree: `/Users/lucadenegri/Develop/DJProject01/.claude/worktrees/code-docs-review-plan-3345fa` (sotto: `WT`). Checkout principale: `/Users/lucadenegri/Develop/DJProject01` (sotto: `MAIN`). Ogni blocco di comandi assume questi export fatti a inizio shell:

```bash
export WT="/Users/lucadenegri/Develop/DJProject01/.claude/worktrees/code-docs-review-plan-3345fa"
export MAIN="/Users/lucadenegri/Develop/DJProject01"
```
- Pytest gira col venv del checkout principale, cwd nel backend del worktree: `cd $WT/backend && $MAIN/backend/.venv/bin/python -m pytest tests`.
- Frontend nel worktree richiede `npm install` REALE (niente symlink a node_modules: rompe Turbopack).
- Schema DB intoccabile: colonne/tabelle sospette → solo segnalazione (livello 3).
- In `backend/app/organize/` il livello 2 (consolidamento) è DISATTIVATO: solo rimozioni certe o segnalazioni.
- Doppia conferma obbligatoria prima di ogni rimozione: il candidato dello strumento statico va confermato con grep sull'intero repo (test inclusi) e controllo convenzioni framework (router FastAPI registrati dinamicamente, pagine App Router caricate per percorso, componenti referenziati solo via JSX).
- Commit piccoli e tematici, messaggi in italiano nello stile del repo (`fix(...):`, `chore(...):`, `docs(...):`). MAI aggiungere `Co-Authored-By: Claude` ai commit.
- Ogni fase chiude solo con: pytest verde, `npm run lint` + `npm run build` + `npm run test:unit` verdi. E2e Playwright: solo nella verifica finale, opzionale (richiede `backend/.venv` nel worktree).
- I risultati di rilevamento e i riepiloghi di fase si accumulano nel log di lavoro `docs/superpowers/plans/2026-08-13-revisione-log.md` (creato nel Task 1, archiviato con tutto `docs/superpowers/` in Fase 3).
- STOP a ogni checkpoint di fine fase: presentare il riepilogo (rimosso / consolidato / segnalato) e attendere l'ok dell'utente prima della fase successiva.

---

## Fase 0 — Baseline

### Task 1: Setup worktree e baseline

**Files:**
- Create: `docs/superpowers/plans/2026-08-13-revisione-log.md`
- Modify: nessuno (solo installazioni e run di verifica)

**Interfaces:**
- Produces: log di lavoro con metriche baseline; ambiente pronto (node_modules reale, vulture installato); esito test di partenza registrato.

- [ ] **Step 1: npm install reale nel frontend del worktree**

```bash
cd "$WT/frontend" && ls node_modules >/dev/null 2>&1 && echo "presente" || npm install
```

Se `node_modules` è un symlink (`ls -la` lo mostra), rimuoverlo e rifare `npm install`.

- [ ] **Step 2: installare vulture nel venv principale**

```bash
"$MAIN/backend/.venv/bin/python" -m pip install vulture
```

Expected: `Successfully installed vulture-...` (o già presente). Nota: il venv principale resta altrimenti intatto; vulture è inerte.

- [ ] **Step 3: giro di test backend di partenza**

```bash
cd "$WT/backend" && "$MAIN/backend/.venv/bin/python" -m pytest tests -q
```

Expected: tutto verde. Se ci sono rossi PRE-esistenti: registrarli nel log (Step 6) e segnalarli all'utente PRIMA di procedere — non ce li attribuiamo.

- [ ] **Step 4: giro frontend di partenza**

```bash
cd "$WT/frontend" && npm run lint && npm run build && npm run test:unit
```

Expected: tutti e tre verdi. Stessa regola dello Step 3 per eventuali rossi pre-esistenti.

- [ ] **Step 5: snapshot metriche**

```bash
cd "$WT" && \
echo "py files: $(find backend/app -name '*.py' | wc -l), righe: $(find backend/app -name '*.py' -exec cat {} + | wc -l)" && \
echo "ts files: $(find frontend/app frontend/components frontend/lib -name '*.ts' -o -name '*.tsx' | wc -l), righe: $(find frontend/app frontend/components frontend/lib \( -name '*.ts' -o -name '*.tsx' \) -exec cat {} + | wc -l)" && \
echo "endpoint: $(grep -rE '@router\.(get|post|put|delete|patch)' backend/app --include='*.py' | wc -l)" && \
echo "deps pip: $(grep -cE '^[a-zA-Z]' backend/requirements.txt), deps npm: $(python3 -c "import json;d=json.load(open('frontend/package.json'));print(len(d['dependencies'])+len(d['devDependencies']))")" && \
wc -l README.md PROGRESS.md CLAUDE.md docs/*.md | tail -1
```

- [ ] **Step 6: creare il log di lavoro**

Creare `docs/superpowers/plans/2026-08-13-revisione-log.md` con: le metriche dello Step 5 in una sezione `## Baseline (Fase 0)`, l'esito dei test di partenza, e le sezioni vuote `## Fase 1 — Findings backend`, `## Fase 2 — Findings frontend`, `## Segnalazioni (livello 3)`, `## Riepiloghi checkpoint`.

- [ ] **Step 7: commit**

```bash
cd "$WT" && git add docs/superpowers/plans/2026-08-13-revisione-log.md && git commit -m "chore(revisione): baseline fase 0 — metriche e stato test di partenza"
```

---

## Fase 1 — Backend

### Task 2: Rilevamento backend

**Files:**
- Modify: `docs/superpowers/plans/2026-08-13-revisione-log.md` (sezione Fase 1)

**Interfaces:**
- Produces: lista findings backend classificati L1 (rimozione) / L2 (consolidamento) / L3 (segnalazione), ognuno con la prova della doppia conferma. I Task 3-4 lavorano SOLO da questa lista.

- [ ] **Step 1: vulture sul backend**

```bash
cd "$WT/backend" && "$MAIN/backend/.venv/bin/python" -m vulture app --min-confidence 80 --sort-by-size
```

Ogni voce è un CANDIDATO. Falsi positivi noti da scartare subito: handler FastAPI (referenziati dai decorator), validators Pydantic, colonne SQLAlchemy, hook di lifecycle, `__init__.py` re-export usati altrove.

- [ ] **Step 2: censimento endpoint reali**

```bash
cd "$WT/backend" && "$MAIN/backend/.venv/bin/python" -c "
from app.main import app
spec = app.openapi()
rows = []
for path, ops in spec['paths'].items():
    for method in ops:
        if method.lower() in ('get','post','put','delete','patch'):
            rows.append(f'{method.upper():6} {path}')
print('\n'.join(sorted(rows)))
print('TOTALE:', len(rows))
"
```

Expected: 149 righe `GET    /api/...` + il totale. Salvare l'output nel log.

Nota (verificata durante l'esecuzione): NON iterare `app.routes` cercando
`.methods` — su questa versione di FastAPI restituisce 31 wrapper
`_IncludedRouter` privi di `.methods` e il censimento collassa a 5 righe.
`app.openapi()` è la fonte affidabile. I 149 endpoint sono 148 decoratori
`@router.*` più `GET /api/health`, registrato con `@app.get` in
`app/main.py:130`: per questo la metrica grep della baseline dice 148. La
baseline continua a usare il grep (confronto omogeneo in Task 14), il
censimento usa openapi (verità sugli endpoint).

- [ ] **Step 3: incrocio endpoint ↔ chiamate frontend**

Per ogni path dello Step 2, normalizzare i segmenti dinamici (`{id}` → ``) e cercare il frammento statico nel frontend:

```bash
cd "$WT" && grep -rn "api/organize" frontend/lib frontend/app frontend/components --include='*.ts' --include='*.tsx' -l | head
# poi, per ogni endpoint sospetto (nessun hit sul path completo):
grep -rn "<frammento-path>" frontend backend/tests --include='*.ts' --include='*.tsx' --include='*.py'
```

Un endpoint è candidato L1 solo se: nessuna chiamata dal frontend, nessun uso nei test come API di prodotto (i test che lo coprono contano come "solo test", vedi Step 5), non documentato in `docs/API.md` come interfaccia per uso manuale/script. In dubbio → L3 (l'utente potrebbe chiamarlo via curl).

- [ ] **Step 4: dipendenze pip inutilizzate**

Per ogni pacchetto in `requirements.txt`, cercare l'import corrispondente:

```bash
cd "$WT/backend" && for pkg in fastapi uvicorn sqlalchemy pydantic pydantic_settings dotenv multipart ruamel yaml pytest httpx anthropic yt_dlp shazamio mutagen defusedxml essentia acoustid PIL; do echo "== $pkg: $(grep -rE "import $pkg|from $pkg" app tests --include='*.py' | wc -l)"; done
```

Attenzione ai nomi divergenti (pacchetto ≠ modulo: `python-multipart`→`multipart` usato da FastAPI internamente, `uvicorn` usato solo da CLI — questi NON sono morti).

- [ ] **Step 5: doppia conferma e classificazione**

Per ogni candidato sopravvissuto: grep del simbolo/path sull'INTERO repo (test e docs inclusi). Dispatch di 2-3 subagent Explore in parallelo per lotti di candidati è ammesso e consigliato. Classificare nel log ogni finding come:
- `L1` — zero referenze reali (i test che coprono SOLO quel codice si contano come parte del morto);
- `L2` — duplicazione evidente con fusione meccanica e comportamento coperto dai test (MAI in `app/organize/`);
- `L3` — tutto il resto (colonne DB, dubbi, architettura).

Formato voce log: `- [L1] app/services/foo.py:barra() — vulture 90%, grep 0 hit fuori dal file, nessun test dedicato`.

- [ ] **Step 6: commit del log**

```bash
cd "$WT" && git add docs/superpowers/plans/2026-08-13-revisione-log.md && git commit -m "chore(revisione): findings backend classificati L1/L2/L3"
```

### Task 3: Rimozioni L1 backend

**Files:**
- Modify: i file elencati come L1 nel log (sezione Fase 1) — nessun altro.

**Interfaces:**
- Consumes: lista L1 dal log del Task 2.
- Produces: backend senza codice morto, suite verde, un commit per lotto tematico.

- [ ] **Step 1: raggruppare i finding L1 in lotti tematici**

Esempi di lotto: "import e funzioni morte nei services", "endpoint orfani router X", "dipendenze pip inutilizzate". Ogni lotto = un commit.

- [ ] **Step 2: per ogni lotto — rimuovere, ricontrollare, testare**

Per ogni finding del lotto: rimuovere il codice; se un test copriva SOLO quel codice, rimuovere anche il test (annotarlo nel log). Poi:

```bash
cd "$WT/backend" && grep -rn "<simbolo-rimosso>" app tests --include='*.py'   # expected: 0 hit
cd "$WT/backend" && "$MAIN/backend/.venv/bin/python" -m pytest tests -q      # expected: verde
```

Se un test NON dedicato al morto si rompe, il finding era classificato male: ripristinare, riclassificare a L3 nel log, proseguire col lotto.

- [ ] **Step 3: commit per lotto**

```bash
cd "$WT" && git add -A && git commit -m "chore(revisione): rimuove <descrizione lotto> (morto confermato)"
```

Ripetere Step 2-3 per ogni lotto fino a esaurire la lista L1.

### Task 4: Consolidamenti L2 backend

**Files:**
- Modify: i file elencati come L2 nel log — MAI file sotto `backend/app/organize/`.

**Interfaces:**
- Consumes: lista L2 dal log del Task 2.
- Produces: duplicazioni consolidate, suite verde, un commit per consolidamento.

- [ ] **Step 1: per ogni finding L2, verificare la copertura PRIMA di toccare**

Identificare i test che coprono ENTRAMBE le copie della logica duplicata:

```bash
cd "$WT/backend" && grep -rln "<nome-funzione-a>\|<nome-funzione-b>" tests
```

Se una delle due copie non è coperta: scrivere PRIMA un test che ne fissa il comportamento attuale (input reale → output atteso), verificarlo verde, poi procedere.

- [ ] **Step 2: consolidare (una duplicazione alla volta)**

Fondere sulla copia meglio collocata (layer services per la logica, `repositories.py` per le query); aggiornare i chiamanti; rimuovere la copia morta.

```bash
cd "$WT/backend" && "$MAIN/backend/.venv/bin/python" -m pytest tests -q
```

Expected: verde. Se il consolidamento richiede più di una sostituzione meccanica dei chiamanti: fermarsi, retrocedere il finding a L3 nel log, ripristinare.

- [ ] **Step 3: commit per consolidamento**

```bash
cd "$WT" && git add -A && git commit -m "refactor(revisione): consolida <descrizione duplicazione>"
```

### Task 5: Checkpoint Fase 1 — STOP utente

- [ ] **Step 1: aggiornare il log** — sezione `## Riepiloghi checkpoint`: blocchi **rimosso** / **consolidato** / **segnalato** con conteggi e motivazioni.

- [ ] **Step 2: verifica di fase completa**

```bash
cd "$WT/backend" && "$MAIN/backend/.venv/bin/python" -m pytest tests -q && cd "$WT/frontend" && npm run lint && npm run build && npm run test:unit
```

(Anche il frontend: le rimozioni di endpoint non devono aver rotto nulla di chiamato.)

- [ ] **Step 3: commit log + presentare il riepilogo all'utente e ATTENDERE l'ok.**

---

## Fase 2 — Frontend

### Task 6: Rilevamento frontend

**Files:**
- Modify: `docs/superpowers/plans/2026-08-13-revisione-log.md` (sezione Fase 2)

**Interfaces:**
- Produces: findings frontend L1/L2/L3 nel log. I Task 7-8 lavorano SOLO da questa lista.

- [ ] **Step 1: knip (file, export e dipendenze non usati)**

```bash
cd "$WT/frontend" && npx knip
```

Falsi positivi noti App Router da scartare: `app/**/page.tsx`, `layout.tsx`, `loading.tsx`, `error.tsx`, `not-found.tsx`, `route.ts`, i config (`next.config.ts`, `playwright.config.ts`, `vitest.config.ts`, `postcss.config.mjs`, `eslint.config.mjs`) e `e2e/**`.

- [ ] **Step 2: depcheck (controprova sulle dipendenze npm)**

```bash
cd "$WT/frontend" && npx depcheck
```

Una dipendenza è candidata L1 solo se la flaggano ENTRAMBI (knip e depcheck) e il grep manuale su config e sorgenti dà zero (attenzione a plugin citati solo nei config: `@tailwindcss/postcss`, `eslint-config-next`, `@vitejs/plugin-react`, `jsdom` via `vitest.config.ts`).

- [ ] **Step 3: chiavi i18n morte**

`frontend/lib/i18n/en.ts` è la fonte di verità (oggetto annidato, `it.ts` si tipizza con `typeof en`). Estrarre le chiavi foglia e cercarne l'uso:

```bash
cd "$WT/frontend" && python3 - <<'EOF'
import re, subprocess, pathlib
src = pathlib.Path("lib/i18n/en.ts").read_text()
# chiavi foglia: `identificatore:` seguito da stringa/funzione, dentro l'oggetto `en`
keys = sorted(set(re.findall(r'^\s+([a-zA-Z_][a-zA-Z0-9_]*):\s', src, re.M)))
dead = []
for k in keys:
    hits = subprocess.run(["grep", "-rE", rf"\.{k}\b", "app", "components", "lib"],
                          capture_output=True, text=True).stdout
    real = [l for l in hits.splitlines() if "lib/i18n/" not in l]
    if not real:
        dead.append(k)
print("candidate morte:", len(dead))
print("\n".join(dead))
EOF
```

Ogni candidata va doppio-confermata a mano (le chiavi possono essere raggiunte dinamicamente, es. `dict[status]` — in dubbio → L3). Una chiave morta va rimossa da ENTRAMBE le lingue (`en.ts` + `it.ts`; il typecheck lo impone).

- [ ] **Step 4: componenti e lib orfani, doppia conferma**

Per ogni file flaggato da knip fuori dalle convenzioni App Router:

```bash
cd "$WT/frontend" && grep -rnE "<NomeComponente[^A-Za-z0-9]|\bNomeComponente\b" app components lib tests e2e
```

**Ancorare SEMPRE la fine del nome** (`\b`, o una classe di caratteri che escluda
lettere e cifre). Un grep non ancorato su un nome che è prefisso di un altro
(`TrackCard` dentro `TrackCardCompact`) trova le occorrenze del fratello vivo e fa
sembrare vivo un simbolo morto. È lo stesso difetto che in Fase 1 ha nascosto
`POST /api/sets/generate` dietro `/api/sets/generate-async`: sbaglia in direzione
prudente (roba morta non trovata, mai roba viva cancellata), ma lascia sporco.

Zero hit reali → L1. Componenti quasi-fotocopia individuati leggendo i file → L2. Classificare nel log, stesso formato della Fase 1.

- [ ] **Step 5: commit del log**

```bash
cd "$WT" && git add docs/superpowers/plans/2026-08-13-revisione-log.md && git commit -m "chore(revisione): findings frontend classificati L1/L2/L3"
```

### Task 7: Rimozioni L1 frontend

**Files:**
- Modify: i file elencati come L1 nel log (sezione Fase 2) — nessun altro.

**Interfaces:**
- Consumes: lista L1 frontend dal log del Task 6.
- Produces: frontend senza morto, lint+build+test:unit verdi, un commit per lotto tematico.

- [ ] **Step 1: lotti tematici** (es. "componenti orfani", "chiavi i18n morte", "dipendenze npm").

- [ ] **Step 2: per ogni lotto — rimuovere e verificare**

```bash
cd "$WT/frontend" && grep -rn "<simbolo-rimosso>" app components lib tests e2e   # expected: 0 hit
cd "$WT/frontend" && npm run lint && npm run build && npm run test:unit          # expected: verdi
```

Il `build` è il gate decisivo (typecheck completo; per le chiavi i18n verifica che `it.ts` sia allineato). Rottura inattesa → ripristinare il finding, riclassificare a L3.

- [ ] **Step 3: commit per lotto**

```bash
cd "$WT" && git add -A && git commit -m "chore(revisione): rimuove <descrizione lotto> (morto confermato)"
```

### Task 8: Consolidamenti L2 frontend + checkpoint Fase 2 — STOP utente

**Files:**
- Modify: i file elencati come L2 nel log (sezione Fase 2).

- [ ] **Step 1: per ogni L2, consolidare una duplicazione alla volta** — stessa regola della Fase 1: se esiste un test (vitest) che copre il comportamento, verificarlo prima; altrimenti scriverlo. Fusione solo se meccanica; altrimenti retrocedere a L3.

```bash
cd "$WT/frontend" && npm run lint && npm run build && npm run test:unit
```

- [ ] **Step 2: commit per consolidamento**

```bash
cd "$WT" && git add -A && git commit -m "refactor(revisione): consolida <descrizione duplicazione>"
```

- [ ] **Step 3: checkpoint** — aggiornare il log (rimosso/consolidato/segnalato Fase 2), verifica completa backend+frontend come Task 5 Step 2, commit, presentare riepilogo all'utente e ATTENDERE l'ok.

---

## Fase 3 — Docs storiche

### Task 9: Archiviazione + checkpoint — STOP utente

**Files:**
- Create: `docs/archive/README.md` (indice), `docs/archive/PROGRESS-diario-completo.md`
- Move: `docs/AUDIT-2026-07-05.md`, `docs/organize/CLAUDE-sortory-storico.md`, `docs/organize/README-sortory-storico.md`, `docs/superpowers/` (intera, spec e piano di questa revisione inclusi) → sotto `docs/archive/`
- Modify: `PROGRESS.md` (riassunto ~30 righe), `CLAUDE.md`, `docs/organize/PRODUCT.md` se referenzia percorsi spostati

**Interfaces:**
- Produces: `docs/archive/` con indice; percorso di lettura pulito; nessun riferimento rotto ai vecchi percorsi. NOTA per la Fase 4: il log di lavoro dopo questo task vive in `docs/archive/superpowers/plans/2026-08-13-revisione-log.md`.

- [ ] **Step 1: spostare con git mv**

```bash
cd "$WT" && mkdir -p docs/archive && \
git mv docs/AUDIT-2026-07-05.md docs/archive/ && \
git mv docs/superpowers docs/archive/superpowers && \
git mv docs/organize/CLAUDE-sortory-storico.md docs/organize/README-sortory-storico.md docs/archive/
```

Nota: `docs/organize/PRODUCT.md` resta dov'è SOLO se ancora attuale come doc di prodotto della sezione Organize; se anch'esso è storico, spostarlo e aggiornare i riferimenti.

- [ ] **Step 2: ridurre PROGRESS.md**

```bash
cd "$WT" && git mv PROGRESS.md docs/archive/PROGRESS-diario-completo.md
```

Creare un nuovo `PROGRESS.md` (~30 righe): 2-3 frasi su cos'è il progetto oggi, lo stato corrente per area (library, set builder, discovery, organize, analisi, shazam, download), puntatore a `docs/archive/PROGRESS-diario-completo.md` per la cronologia e a `docs/ROADMAP.md` per il backlog.

- [ ] **Step 3: indice dell'archivio**

Creare `docs/archive/README.md`: una riga per gruppo (diario completo, audit 2026-07-05 chiuso, docs storiche Sortory, specs e plans delle feature — con nota che sono lo storico di sviluppo, non docs operative).

- [ ] **Step 4: aggiornare i riferimenti ai percorsi spostati**

```bash
cd "$WT" && grep -rn "docs/superpowers\|AUDIT-2026-07-05\|sortory-storico\|PROGRESS.md" --include='*.md' . | grep -v docs/archive | grep -v node_modules
```

Aggiornare ogni hit (atteso: `CLAUDE.md`, forse `README.md`/`docs/*.md`) al nuovo percorso `docs/archive/...`.

- [ ] **Step 5: verifica link su tutte le md vive**

```bash
cd "$WT" && python3 - <<'EOF'
import re, pathlib
bad = []
for md in list(pathlib.Path(".").glob("*.md")) + list(pathlib.Path("docs").rglob("*.md")):
    if "archive" in md.parts or "node_modules" in md.parts: continue
    for m in re.finditer(r'\]\(([^)#\s]+)\)|`((?:docs|backend|frontend)/[^`\s]+\.md)`', md.read_text()):
        target = m.group(1) or m.group(2)
        if target.startswith(("http", "mailto")): continue
        p = (md.parent / target) if not target.startswith(("docs/", "backend/", "frontend/")) else pathlib.Path(target)
        if not p.exists(): bad.append(f"{md}: {target}")
print("\n".join(bad) or "OK: nessun riferimento rotto")
EOF
```

Expected: `OK: nessun riferimento rotto`.

- [ ] **Step 6: commit + checkpoint**

```bash
cd "$WT" && git add -A && git commit -m "docs(archive): archivia diario, audit chiuso, storico Sortory e specs/plans; PROGRESS ridotto a riassunto"
```

Presentare all'utente la nuova struttura docs e ATTENDERE l'ok.

---

## Fase 4 — Docs vive

Regola di riscrittura per tutti i task della fase: si scrive per un umano che apre il progetto OGGI. Via: cronologia di sviluppo (F1-F6, lotti, chunk, "fusione", "ex Sortory" come narrazione), voci "cosa è cambiato", giustificazioni di decisioni passate. Resta: cosa fa il sistema, come è fatto, come si usa. La storia vive in `docs/archive/` e nel git log. Ogni affermazione fattuale (endpoint, comandi, percorsi, dipendenze) va verificata contro il codice POST-pulizia, non copiata dalla doc precedente.

### Task 10: README.md (vetrina, inglese)

**Files:**
- Modify: `README.md`

- [ ] **Step 1: riscrivere** — struttura target: cos'è Cratory (3-4 frasi, per un lettore esterno), feature principali per area (bullet, senza gergo interno), screenshot/design note se già presenti, quickstart (comandi backend e frontend copiati da `CLAUDE.md` e VERIFICATI), stack, licenza/nota personale. Lunghezza target: ≤150 righe. Zero riferimenti a fasi di sviluppo.

- [ ] **Step 2: verificare i comandi del quickstart eseguendoli** (backend: uvicorn parte; frontend: `npm run dev` parte — poi arrestarli).

- [ ] **Step 3: commit**

```bash
cd "$WT" && git add README.md && git commit -m "docs(readme): riscrittura vetrina per lettore esterno, via i riferimenti storici"
```

### Task 11: ARCHITECTURE.md, DESIGN.md, DEPENDENCIES.md

**Files:**
- Modify: `docs/ARCHITECTURE.md`, `docs/DESIGN.md`, `docs/DEPENDENCIES.md`

- [ ] **Step 1: ARCHITECTURE.md** — descrivere il sistema al presente: principi (motore deterministico vs AI, library=disco, provenienza BPM/key), layer backend con l'albero REALE post-pulizia (rigenerare da `ls backend/app/...`), flussi principali (import → dedup → ready; dig discovery; organize scan → plan → apply → undo), integrazioni con i loro confini. Eliminare le sezioni-cronologia.

- [ ] **Step 2: DESIGN.md** — tenere il design system "editorial archive" e il contesto prodotto; eliminare la cronologia delle decisioni superate.

- [ ] **Step 3: DEPENDENCIES.md** — rigenerare l'elenco dai `requirements.txt` e `package.json` POST-pulizia, con la ragione d'essere di ognuna (le note preziose tipo il pin di essentia restano).

- [ ] **Step 4: commit**

```bash
cd "$WT" && git add docs/ARCHITECTURE.md docs/DESIGN.md docs/DEPENDENCIES.md && git commit -m "docs: ARCHITECTURE/DESIGN/DEPENDENCIES riscritte al presente, per un lettore umano"
```

### Task 12: API.md (verificata contro i router reali)

**Files:**
- Modify: `docs/API.md`

- [ ] **Step 1: rigenerare il censimento endpoint** e confrontarlo con `docs/API.md`: ogni endpoint documentato deve esistere, ogni endpoint esistente deve essere documentato (o esplicitamente marcato interno).

```bash
cd "$WT/backend" && "$MAIN/backend/.venv/bin/python" -c "
from app.main import app
spec = app.openapi()
rows = []
for path, ops in spec['paths'].items():
    for method in ops:
        if method.lower() in ('get','post','put','delete','patch'):
            rows.append(f'{method.upper():6} {path}')
print('\n'.join(sorted(rows)))
print('TOTALE:', len(rows))
"
```

Usare QUESTO comando: iterare `app.routes` cercando `.methods` non funziona su
questa versione di FastAPI (restituisce 5 righe invece di 149 — vedi la nota nel
Task 2 Step 2). Al via della revisione gli endpoint erano 149.

- [ ] **Step 2: riscrivere** — raggruppare per area (playlists, tracks, sets, discovery, organize, …), per ogni endpoint: metodo, path, una riga di scopo, parametri non ovvi. Le regole di dominio importanti (sovrascrittura BPM/key, apply rekordbox) restano ma come regole del presente. Via i "changelog" interni alla doc.

- [ ] **Step 3: commit**

```bash
cd "$WT" && git add docs/API.md && git commit -m "docs(api): censimento rigenerato dai router reali, riscrittura per aree"
```

### Task 13: ROADMAP.md, CLAUDE.md, frontend/CLAUDE.md

**Files:**
- Modify: `docs/ROADMAP.md`, `CLAUDE.md`, `frontend/CLAUDE.md`

- [ ] **Step 1: ROADMAP.md** — due sole sezioni: stato attuale (cosa funziona, per area, al presente) e backlog reale (incluse le segnalazioni L3 di questa revisione, importate dal log). Via lo storico "fatto il…".

- [ ] **Step 2: CLAUDE.md** — resta il documento per l'AI: aggiornare l'ordine di lettura (PROGRESS ridotto, archive), i percorsi (`docs/archive/...`), rimuovere i riferimenti a file spostati e a codice rimosso. Le regole non-negoziabili NON cambiano nella sostanza. Verificare `frontend/CLAUDE.md` (5 righe) per coerenza.

- [ ] **Step 3: ricontrollo link** — rieseguire lo script del Task 9 Step 5. Expected: `OK`.

- [ ] **Step 4: commit**

```bash
cd "$WT" && git add docs/ROADMAP.md CLAUDE.md frontend/CLAUDE.md && git commit -m "docs: ROADMAP a stato+backlog, CLAUDE.md coerente coi nuovi percorsi"
```

### Task 14: Verifica finale e consegna

**Files:**
- Modify: `docs/archive/superpowers/plans/2026-08-13-revisione-log.md` (rapporto finale)

- [ ] **Step 1: verifica completa**

```bash
cd "$WT/backend" && "$MAIN/backend/.venv/bin/python" -m pytest tests -q && \
cd "$WT/frontend" && npm run lint && npm run build && npm run test:unit
```

Expected: tutto verde. (Opzionale, su richiesta utente: e2e Playwright — richiede `python3 -m venv backend/.venv && backend/.venv/bin/pip install -r backend/requirements.txt` nel worktree, poi `npm run test:e2e`.)

- [ ] **Step 2: metriche finali e confronto baseline** — rieseguire il comando del Task 1 Step 5, scrivere nel log il rapporto finale: righe rimosse per area, endpoint eliminati, dipendenze tolte, docs vive prima/dopo (righe), lista consolidata delle L3 non affrontate (già importate in ROADMAP).

- [ ] **Step 3: commit finale**

```bash
cd "$WT" && git add -A && git commit -m "chore(revisione): rapporto finale — confronto baseline e segnalazioni residue"
```

- [ ] **Step 4: presentare all'utente il rapporto finale** e decidere insieme: merge diretto su master o PR.
