# Rifiniture disk-first (fetta 4) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Il modello disk-first diventa visibile e documentato: copertura possesso in dashboard, playlist presentate come "lead" (non libreria), README/CLAUDE.md dei tre repo allineati alla realtà.

**Architecture:** Solo copy, UI leggera e documentazione. Nessuna logica nuova: consuma `stats.with_local_file` (fetta 1). Tocca i TRE repo (commit separati per repo).

**Tech Stack:** Next.js 16 + React (Cratory frontend), Markdown.

## Global Constraints

- Dipende dalle fette 1–3 (mergiate su `master`/`main` dei rispettivi repo).
- Frontend Cratory: `cd frontend && npm run lint && npm run build` verdi. **Leggere `frontend/CLAUDE.md` prima di toccare pagine.**
- Copy UI in italiano, tono asciutto del design system "editorial archive".
- Branch: `feat/disk-first-rifiniture` in DJProject01; in DjOrganizer01 e DJPlayer01 le modifiche sono solo-README (commit diretto su `main` accettabile, oppure micro-branch a scelta dell'implementatore).
- Spec di riferimento: `~/Develop/docs/superpowers/specs/2026-07-01-dj-ecosystem-disk-first-design.md` e north-star `~/Develop/dj-ecosystem-north-star.md`.

---

### Task 0: Branch (DJProject01)

- [ ] **Step 1:**

```bash
cd /Users/lucadenegri/Develop/DJProject01
git checkout master && git checkout -b feat/disk-first-rifiniture
```

---

### Task 1: Dashboard — copertura possesso

**Files:**
- Modify: `frontend/lib/api.ts` (tipo stats)
- Modify: `frontend/app/page.tsx` (dashboard)

**Interfaces:**
- Consumes: `GET /api/stats` → campo `with_local_file: number` (fetta 1) e `total_tracks`.
- Produces: una hero figure/card "Possedute" con `with_local_file` e percentuale su `total_tracks`.

- [ ] **Step 1: Tipo** — in `frontend/lib/api.ts`, trovare l'interfaccia usata per `/api/stats` (cercare `total_tracks`) e aggiungere:

```typescript
  with_local_file: number;
```

- [ ] **Step 2: Card** — in `frontend/app/page.tsx`, individuare il blocco delle hero figures (dove sono renderizzati `total_tracks`, `with_bpm`, ecc.) e aggiungere, con lo STESSO markup delle figure esistenti:

```tsx
{/* Possesso disk-first: quante tracce hanno il file in libreria */}
<Figure label="Possedute" value={stats.with_local_file}
        hint={stats.total_tracks ? `${Math.round((stats.with_local_file / stats.total_tracks) * 100)}% della libreria` : undefined} />
```

(`Figure` è un nome indicativo: usare il componente/markup reale delle hero figures della pagina — replicare esattamente quello esistente.)

- [ ] **Step 3: Verifica** `cd frontend && npm run lint && npm run build` → 0 errori.

- [ ] **Step 4: Commit**

```bash
git add frontend/lib/api.ts frontend/app/page.tsx
git commit -m "feat(disk-first): copertura possesso in dashboard"
```

---

### Task 2: Copy — le playlist sono lead, la libreria è il disco

**Files:**
- Modify: `frontend/app/playlists/page.tsx` (descrizione/meta della pagina)
- Modify: `frontend/app/playlists/import-spotify/page.tsx` (copy dell'import)

**Interfaces:** solo stringhe UI, nessuna logica.

- [ ] **Step 1:** In `frontend/app/playlists/page.tsx`, individuare titolo/descrizione della pagina (prop di `PageLayout` o heading) e integrare il concetto, ad esempio nel sottotitolo/marginalia:

```
Le playlist importate sono liste di lead: candidati da procurare e pianificare.
La libreria — ciò che possiedi — è il disco.
```

(Adattare alla struttura reale della pagina: se esiste già una descrizione, sostituirla; non aggiungere componenti nuovi.)

- [ ] **Step 2:** In `frontend/app/playlists/import-spotify/page.tsx`, stessa operazione sulla descrizione dell'import, ad esempio:

```
L'import non aggiunge file alla libreria: porta dentro i lead della playlist,
da arricchire, scaricare e organizzare.
```

- [ ] **Step 3: Verifica** `cd frontend && npm run lint && npm run build` → 0 errori.

- [ ] **Step 4: Commit**

```bash
git add frontend/app/playlists/
git commit -m "copy(disk-first): playlist come lead, libreria = disco"
```

---

### Task 3: Documentazione Cratory (README, CLAUDE.md, ARCHITECTURE, ROADMAP)

**Files:**
- Modify: `README.md`
- Modify: `CLAUDE.md`
- Modify: `docs/ARCHITECTURE.md`
- Modify: `docs/ROADMAP.md`

- [ ] **Step 1: README.md** — nel paragrafo di apertura (dopo il pitch), aggiungere il principio:

```markdown
**Disk-first:** the library is the disk. Cratory indexes your canonical music
folder (`LIBRARY_ROOT`), re-links files by audio hash after DjOrganizer
renames/moves them, and builds sets from tracks you actually own. Streaming
playlists are *leads* — candidates to acquire — not the library.
```

e nella sezione env/setup documentare `LIBRARY_ROOT`.

- [ ] **Step 2: CLAUDE.md** — nella sezione "Regole non negoziabili", aggiungere come regola 9:

```markdown
9. **La libreria è il disco.** Il possesso (`has_local_file`) viene dall'indicizzazione
   di `LIBRARY_ROOT` (riaggancio per `audio_hash`); le playlist streaming sono lead.
   Cratory legge i file ma non li muta mai: i tag li scrive solo DjOrganizer.
```

- [ ] **Step 3: docs/ARCHITECTURE.md** — aggiungere una sottosezione "Disk-first" che descrive: `LIBRARY_ROOT`, `audio_hash` (ffmpeg, stabile a rinomina/retag), `library_index` (match hash→digest→ISRC→fuzzy, riconciliazione), il lookup read-only `/api/tracks/lookup` per DjOrganizer. Collocarla accanto alla sezione dati/pipeline esistente, stile del documento.

- [ ] **Step 4: docs/ROADMAP.md** — spostare "Vista tracce senza file" tra i FATTI (fetta 1); registrare le fette disk-first 1–4 come completate con data 2026-07; il backlog Discovery resta invariato.

- [ ] **Step 5: Commit**

```bash
git add README.md CLAUDE.md docs/ARCHITECTURE.md docs/ROADMAP.md
git commit -m "docs(disk-first): README/CLAUDE/ARCHITECTURE/ROADMAP allineati al modello disco-centrico"
```

---

### Task 4: README DjOrganizer — non più "in design"

**Files:**
- Modify: `/Users/lucadenegri/Develop/DjOrganizer01/README.md`

- [ ] **Step 1:** Sostituire la sezione "## Stato" (che dice "In design") con:

```markdown
## Stato

Operativo: pipeline completa scan → issues → dedup → piano → applica → undo,
testata end-to-end (148+ test). Il bridge read-only verso Cratory suggerisce
genere/etichetta/anno durante la pulizia dei tag (opzionale: senza Cratory
l'app funziona identica).

## Posto nella catena

`inbox/` → **DjOrganizer** → `Libreria/{genere}/{artist}/Artist - Title.ext` → Rekordbox.
Unico scrittore dei tag dell'ecosistema; precedenza valori:
manuale > tag pulito del file > suggerimento Cratory > AI dal nome file.
Vedi `~/Develop/dj-ecosystem-north-star.md`.
```

- [ ] **Step 2: Commit**

```bash
cd /Users/lucadenegri/Develop/DjOrganizer01
git add README.md && git commit -m "docs: stato reale (operativo) e posto nella catena disk-first"
```

---

### Task 5: README DJPlayer — posto nella catena

**Files:**
- Modify: `/Users/lucadenegri/Develop/DJPlayer01/README.md`

- [ ] **Step 1:** Dopo il paragrafo di apertura, aggiungere:

```markdown
## Place in the chain

DJPlayer is the entry filter of the disk library: `MUSIC_DIR` is the download
inbox, KEEP means "goes on to DjOrganizer → Libreria → Rekordbox", archiving
moves the rejects out. It never writes tags and never renames files.
See `~/Develop/dj-ecosystem-north-star.md`.
```

- [ ] **Step 2: Commit**

```bash
cd /Users/lucadenegri/Develop/DJPlayer01
git add README.md && git commit -m "docs: place in the disk-first chain"
```

---

### Task 6: Verifica finale

- [ ] **Step 1:** Cratory: `cd backend && .venv/bin/python -m pytest tests -q` e `cd frontend && npm run lint && npm run build` → verdi.
- [ ] **Step 2:** Rileggere README dei tre repo: nessuna affermazione contraddice la spec o il north-star.
- [ ] **Step 3: Commit di chiusura** in DJProject01:

```bash
git add -A && git commit -m "chore(disk-first): chiusura fetta 4 — rifiniture e documentazione"
```
