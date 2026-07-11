# Documentation Reorganization + English + Dependencies — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Translate Cratory's docs to English, consolidate duplicated content, and add a dedicated dependencies reference — without touching the two files a parallel session owns.

**Architecture:** Pure documentation work. Each task rewrites or creates one Markdown file, then verifies via grep/diff (link integrity, translation completeness, untouched-file guarantee). No application code changes.

**Tech Stack:** Markdown. Verification via `git diff`, `grep`, `rg`.

## Global Constraints

- **NEVER edit `docs/API.md` or `docs/ARCHITECTURE.md`** — the parallel `i18n-it-en` branch owns them. They must be byte-for-byte unchanged at the end.
- **NEVER edit `backend/requirements.txt` or `frontend/package.json`** — deps cleanup is a separate task; this session only documents.
- **Do NOT translate `docs/AUDIT-2026-07-05.md`** — frozen historical snapshot.
- **All output English** (except the frozen AUDIT). No invented content — translate + reorganize only.
- **Commit style:** no `Co-Authored-By` trailer (user preference).
- **Canonical English vocabulary = `README.md`.** Mirror its terms exactly (see Glossary) so all files read as one voice.
- Work on branch `claude/reorganize-project-docs-2d2144`. Commit only the files each task names (parallel sessions share the checkout — stage explicitly, never `git add -A`).

## Translation Glossary (IT → EN, anchored to README.md)

| Italiano | English |
|---|---|
| possedute / posseduta | owned |
| scartate / scartata | discarded |
| lead (streaming) | leads |
| libreria | library |
| buchi / lacune (libreria) | (library) gaps |
| scaletta / set | set |
| tracce | tracks |
| brano | track |
| etichetta (discografica) | (record) label |
| tonalità / chiave | (Camelot) key |
| possesso | ownership |
| arricchimento (metadati) | (metadata) enrichment |
| motore deterministico | deterministic engine |
| striscia / pipeline (fasi) | pipeline strip / stages |
| Scopri → Acquisisci → Organizza → Analizza → Suona | Discover → Acquire → Organize → Analyze → Play |
| Indicizza / indicizzazione | Index / indexing |
| fonte di verità | source of truth |
| regole non negoziabili | non-negotiable rules |
| stato completato | (removed — history lives in PROGRESS) |
| prossimi passi | next steps |
| decisioni consolidate | settled decisions |
| rischi | risks |
| diario di sviluppo | development diary |

Keep proper nouns and technical identifiers verbatim: `Cratory`, `Sortory`, `Rekordbox`, `Spotify`, `Last.fm`, `Discogs`, `slskd`, `Shazam`, `LIBRARY_ROOT`, `ARCHIVE_ROOT`, `has_local_file`, `audio_hash`, endpoint paths, env var names, file paths, code identifiers.

---

## File Structure

- **Create:** `docs/DEPENDENCIES.md` — exhaustive dependency reference from the real manifests.
- **Rewrite (translate + transform):**
  - `docs/DESIGN.md` — translate residual Italian + absorb `PRODUCT.md`.
  - `docs/ROADMAP.md` — translate + drop the `Stato completato` changelog.
  - `PROGRESS.md` — translate (sole home of history).
  - `CLAUDE.md` — translate + slim + update reading-order list.
- **Modify:** `README.md` — Documentation table + DEPENDENCIES link + drop "docs in Italian" note.
- **Delete:** `docs/PRODUCT.md` (content moved into DESIGN.md).
- **Untouched:** `docs/API.md`, `docs/ARCHITECTURE.md`, `docs/AUDIT-2026-07-05.md`, `docs/architettura.svg`.

Task order is chosen so cross-references settle last: content files first, README table + final link-integrity gate last.

---

### Task 1: `docs/DEPENDENCIES.md` (new)

**Files:**
- Create: `docs/DEPENDENCIES.md`
- Read for grounding: `backend/requirements.txt`, `frontend/package.json`

**Interfaces:**
- Consumes: nothing.
- Produces: `docs/DEPENDENCIES.md` — linked by README in Task 6.

- [ ] **Step 1: Re-read the manifests to confirm versions are current**

Run: `cat backend/requirements.txt frontend/package.json`
Expected: matches the content used below. If versions differ, use the file's actual values (the file wins over this plan).

- [ ] **Step 2: Write `docs/DEPENDENCIES.md`**

Use this content (adjust only if Step 1 showed drift):

```markdown
# Dependencies

Every runtime and build dependency of Cratory, grouped by purpose, plus the external
services features rely on. Package versions are sourced from `backend/requirements.txt`
and `frontend/package.json` — those manifests are authoritative; this document explains
*why* each dependency is here.

## System requirements

| Requirement | Version | Needed for |
|---|---|---|
| Python | 3.12+ | Backend |
| Node.js | 20+ | Frontend |
| ffmpeg | system install | Shazam module (audio decode for fingerprinting) |

> `fpcalc`/chromaprint was previously required by AcoustID fingerprinting. That feature
> was removed in the 2026-07 disk-first pivot — see the cleanup note below.

## Backend (Python) — `backend/requirements.txt`

**Web / API**
- `fastapi>=0.115,<1.0` — HTTP framework (routers, request/response).
- `uvicorn[standard]>=0.32` — ASGI server.
- `python-multipart>=0.0.17` — multipart parsing for the Rekordbox `collection.xml` upload.

**Data / validation**
- `sqlalchemy>=2.0,<3.0` — ORM over SQLite.
- `pydantic>=2.9,<3.0` — schemas; validates every AI output before it is shown or saved.
- `pydantic-settings>=2.6,<3.0` — typed settings from `.env`.

**HTTP client**
- `httpx>=0.27` — outbound calls to Spotify, Last.fm, Discogs, slskd.

**AI**
- `anthropic>=0.69,<1.0` — LLM client behind the AI interface.

**Shazam / mix identification**
- `yt-dlp>=2024.0` — pulls audio for mix fingerprinting and does flat metadata extraction
  for the SoundCloud import (metadata only, never stored audio).
- `shazamio>=0.5` — Shazam fingerprint lookup.
- `mutagen>=1.47` — reads tags (incl. `label`) from library files on disk.

**XML security**
- `defusedxml` — hardened XML parsing for the Rekordbox collection import.

**Testing**
- `pytest>=8.3` — backend test suite.
- `httpx>=0.27` — also used as the test client (listed above).

## Frontend (Node) — `frontend/package.json`

**Runtime**
- `next@16.2.9` — App Router framework. (Next 16 has breaking changes — see `frontend/CLAUDE.md`.)
- `react@19.2.4`, `react-dom@19.2.4` — UI runtime.
- `lucide-react@^1.18.0` — icon set (monochrome, per the design system).

**Dev / build**
- `tailwindcss@^4` + `@tailwindcss/postcss@^4` — styling / design tokens.
- `typescript@^5`, `@types/node@^20`, `@types/react@^19`, `@types/react-dom@^19` — types.
- `eslint@^9` + `eslint-config-next@16.2.9` — linting.

## External services & runtime dependencies

Not Python/Node packages, but required for the corresponding feature to work:

| Service | Feature | Required? |
|---|---|---|
| Spotify Web API | Track identity, editorial metadata, covers, ISRC, playlist import/export | Required for Spotify import |
| Last.fm API | Discovery (playlist expand, similarity) | Optional (Discovery) |
| Discogs API | Discovery "Scava" (crate-dig by genre/label) | Optional (token only raises rate limit) |
| slskd daemon | File acquisition via Soulseek | Optional, runs separately |
| Rekordbox | BPM/Camelot key via `collection.xml` export | Required for BPM/key (no package dep — just a file upload) |
| Sortory (sibling app) | Text metadata enrichment + on-disk tagging | Optional, separate app |

None of Last.fm/Discogs/Spotify feed BPM/key/genre — those providers serve **Discovery
only**. BPM/key come from Rekordbox; text metadata/tagging come from Sortory.

## Cleanup note (documentation finding)

`backend/requirements.txt` still lists `pyacoustid>=1.3` with an AcoustID comment, but
AcoustID fingerprinting of the owned library was **removed in the 2026-07 disk-first
pivot** (see `docs/ROADMAP.md`). It is very likely a dead dependency. Verify and remove it
(and drop `fpcalc`/chromaprint from system requirements) in a separate code-cleanup task —
this document does not edit `requirements.txt`.
```

- [ ] **Step 3: Verify no forbidden files were touched**

Run: `git status --short`
Expected: only `docs/DEPENDENCIES.md` shown as new (`??`). `requirements.txt`/`package.json` NOT listed.

- [ ] **Step 4: Commit**

```bash
git add docs/DEPENDENCIES.md
git commit -m "docs(deps): add dedicated DEPENDENCIES reference"
```

---

### Task 2: `docs/DESIGN.md` absorbs `PRODUCT.md` + English

**Files:**
- Modify: `docs/DESIGN.md` (translate residual Italian phrases; prepend a "Product context" section)
- Delete: `docs/PRODUCT.md`
- Read for grounding: `docs/PRODUCT.md`, `docs/DESIGN.md`

**Interfaces:**
- Consumes: nothing.
- Produces: `docs/DESIGN.md` as the single "Product & Design" doc. Task 6 (README) and Task 3/5 (ROADMAP/CLAUDE) will link to it; `PRODUCT.md` must no longer be referenced anywhere.

- [ ] **Step 1: Translate PRODUCT.md content into an English "Product context" section**

Take the Italian sections of `docs/PRODUCT.md` — *Users*, *Product Purpose*, *Brand
Personality*, *Anti-references*, *Design Principles*, *Accessibility & Inclusion* — and
render them in English (drop the near-empty `Register`/`product` lines). Use the Glossary.
The result becomes a new top section of DESIGN.md placed **after** the YAML frontmatter and
**before** the existing `# Design System: Cratory — Editorial Archive` heading, e.g.:

```markdown
# Product & Design: Cratory

## Product context

### Users
[translated Users section]

### Purpose
[translated Product Purpose section]

### Brand personality
[translated Brand Personality section]

### Anti-references
[translated Anti-references section]

### Design principles
[translated Design Principles section — the numbered list]

### Accessibility & inclusion
[translated Accessibility section]

---
```

Then keep the entire existing design-system body (sections 1–6) as-is, translating any
residual Italian phrases (e.g. "unica eccezione ammessa…", "impostato dal consumer…",
"reso da `PageLayout`", "raggruppata per stazioni del flusso", "Caricamento…", the
Companion fields section, etc.) into English. Preserve every token name, hex value, code
identifier, and the YAML frontmatter unchanged.

- [ ] **Step 2: Fix the internal `PRODUCT.md`↔`DESIGN.md` links**

The old PRODUCT.md said `Il sistema visivo completo … vive in [DESIGN.md](DESIGN.md)` — that
pointer is now redundant (same file) and should be dropped. Ensure DESIGN.md contains no
link back to `PRODUCT.md`.

- [ ] **Step 3: Delete PRODUCT.md**

```bash
git rm docs/PRODUCT.md
```

- [ ] **Step 4: Verify no Italian left and no forbidden files touched**

Run: `git status --short`
Expected: `M docs/DESIGN.md`, `D docs/PRODUCT.md`. Nothing else.
Run: `rg -n "Caricamento|impostato dal|unica eccezione|raggruppat|reso da|non tocc" docs/DESIGN.md || echo CLEAN`
Expected: `CLEAN` (spot-check for common leftover Italian tokens; skim the file for others).

- [ ] **Step 5: Commit**

```bash
git add docs/DESIGN.md docs/PRODUCT.md
git commit -m "docs(design): merge PRODUCT into DESIGN, translate to English"
```

---

### Task 3: `docs/ROADMAP.md` — translate + drop changelog

**Files:**
- Modify: `docs/ROADMAP.md`
- Read for grounding: `docs/ROADMAP.md`, `PROGRESS.md` (to confirm history is preserved there)

**Interfaces:**
- Consumes: nothing.
- Produces: English ROADMAP with sections: `Naming`, `Current state` (new, replaces the changelog), `Product direction`, `Next steps`, `Suspended / revised`, `Technical backlog`, `Audit backlog` (keeps the `docs/AUDIT-2026-07-05.md` reference), `Risks`, `Settled decisions`.

- [ ] **Step 1: Remove the `## Stato completato` section entirely**

Delete the whole `## Stato completato` bulleted changelog (the large list of done items).
Replace it with a short English `## Current state` section (3–5 sentences) summarizing the
present phase, ending with: `Full chronological history lives in [PROGRESS.md](../PROGRESS.md).`
Base the summary on PROGRESS.md's "Stato attuale" / "Fase" paragraph (translated), not on
re-listing every done item.

- [ ] **Step 2: Translate every remaining section to English**

Translate `Naming`, `Direzione prodotto`→`Product direction`, `Prossimi passi`→`Next steps`,
`Sospesi / rivisti`→`Suspended / revised`, `Backlog tecnico`→`Technical backlog`, the audit
backlog subsection (keep its `docs/AUDIT-2026-07-05.md` link and the per-ID references
verbatim), `Rischi`→`Risks` (keep the table), `Decisioni consolidate`→`Settled decisions`.
Use the Glossary. Keep all code identifiers, endpoint paths, env var names, and audit IDs
(A1, E10, B24, …) verbatim.

- [ ] **Step 3: Verify**

Run: `rg -n "Stato completato" docs/ROADMAP.md || echo CHANGELOG-REMOVED`
Expected: `CHANGELOG-REMOVED`.
Run: `rg -n "AUDIT-2026-07-05" docs/ROADMAP.md`
Expected: at least one match (audit reference preserved).
Run: `git status --short`
Expected: only `M docs/ROADMAP.md`.

- [ ] **Step 4: Commit**

```bash
git add docs/ROADMAP.md
git commit -m "docs(roadmap): translate to English, drop changelog (history in PROGRESS)"
```

---

### Task 4: `PROGRESS.md` — translate to English

**Files:**
- Modify: `PROGRESS.md`

**Interfaces:**
- Consumes: nothing.
- Produces: English `PROGRESS.md`, the sole home of chronological history. Its header pointer must reference ROADMAP/README/ARCHITECTURE/CLAUDE.

- [ ] **Step 1: Translate the whole file to English**

Translate the header blockquote, `## Stato attuale`→`## Current state`, every
`## Milestone …` entry, and all bullets. Preserve chronology, dates, code identifiers,
endpoint paths, env var names, and file paths verbatim. Use the Glossary. Do not drop or
summarize entries — this file *is* the history now; translate 1:1.

- [ ] **Step 2: Update the header pointer**

The header currently reads (IT): "Lo stato corrente … vive in `docs/ROADMAP.md`. Per
orientarsi: `README.md`, `docs/ARCHITECTURE.md`, `docs/ROADMAP.md`, `CLAUDE.md`." Render in
English, keeping those four links. Do not add a PRODUCT.md link (deleted).

- [ ] **Step 3: Verify**

Run: `rg -n "PRODUCT.md" PROGRESS.md || echo NO-PRODUCT-LINK`
Expected: `NO-PRODUCT-LINK`.
Run: `git status --short`
Expected: only `M PROGRESS.md`.

- [ ] **Step 4: Commit**

```bash
git add PROGRESS.md
git commit -m "docs(progress): translate development diary to English"
```

---

### Task 5: `CLAUDE.md` — translate + slim + update reading order

**Files:**
- Modify: `CLAUDE.md`
- Read for grounding: `docs/ARCHITECTURE.md` (to confirm which rules it already states — do NOT edit it)

**Interfaces:**
- Consumes: the final file set from Tasks 1–4 (names/roles).
- Produces: English `CLAUDE.md`. Reading-order list must reflect the new set (no PRODUCT.md; DESIGN.md is "Product & Design"; DEPENDENCIES.md added).

- [ ] **Step 1: Translate the whole file to English**

Translate all sections: intro, `Progetto`→`Project`, `Fonte di verità`→`Source of truth`,
`Regole non negoziabili`→`Non-negotiable rules`, `Stack e layout`, `Identità tracce`→`Track
identity`, `Comandi`→`Commands`, `Frontend`. Keep all code blocks, paths, endpoint names,
and the `frontend/CLAUDE.md` pointer verbatim. Use the Glossary.

- [ ] **Step 2: Slim the duplicated rules**

The `Regole non negoziabili` list restates ARCHITECTURE (rules 2 and 7 both cover
"BPM/key from Rekordbox"; the ROADMAP cleanup note flags this redundancy). Condense the
overlapping BPM/key rules into one, keeping every distinct constraint. Do not drop any
unique rule — only merge literal repetition.

- [ ] **Step 3: Update the "Source of truth" reading-order list**

Update it to the new file set and roles:
1. `README.md` — overview, setup, workflow (showcase, English).
2. `docs/ARCHITECTURE.md` — principles, pipeline, data, integrations.
3. `docs/API.md` — current endpoints.
4. `docs/ROADMAP.md` — status, naming, backlog, next steps (state source of truth).
5. `PROGRESS.md` — chronological diary to resume work.
6. `docs/DESIGN.md` — product context + design system ("editorial archive").
7. `docs/DEPENDENCIES.md` — dependencies reference.

(Remove the separate PRODUCT.md entry — merged into DESIGN.md.)

- [ ] **Step 4: Verify**

Run: `rg -n "PRODUCT.md" CLAUDE.md || echo NO-PRODUCT-LINK`
Expected: `NO-PRODUCT-LINK`.
Run: `rg -n "DEPENDENCIES.md" CLAUDE.md`
Expected: one match.
Run: `git diff --stat docs/ARCHITECTURE.md`
Expected: empty (ARCHITECTURE untouched).
Run: `git status --short`
Expected: only `M CLAUDE.md`.

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(claude): translate to English, slim duplicated rules, update reading order"
```

---

### Task 6: `README.md` — Documentation table + DEPENDENCIES link

**Files:**
- Modify: `README.md`

**Interfaces:**
- Consumes: final file set (Tasks 1–5).
- Produces: README whose Documentation table matches the new set.

- [ ] **Step 1: Update the Documentation table**

In the `## Documentation` table: remove the `docs/PRODUCT.md` row; change the `docs/DESIGN.md`
row description to "Product context + design system ('editorial archive')"; add a row
`| [docs/DEPENDENCIES.md](docs/DEPENDENCIES.md) | All runtime/build dependencies and external services |`.

- [ ] **Step 2: Remove the "docs are in Italian" note**

Delete the blockquote: "> Note: the README is in English as the project's showcase; the
reference docs above are in Italian (except the design system)." (No longer true — all docs
are English now.)

- [ ] **Step 3: Add a DEPENDENCIES pointer near Quickstart prerequisites**

After the "Prerequisites:" paragraph in `## Quickstart`, add: "Full dependency list in
[docs/DEPENDENCIES.md](docs/DEPENDENCIES.md)."

- [ ] **Step 4: Verify**

Run: `rg -n "PRODUCT.md|are in Italian" README.md || echo CLEAN`
Expected: `CLEAN`.
Run: `rg -n "DEPENDENCIES.md" README.md`
Expected: two matches (table + Quickstart).
Run: `git status --short`
Expected: only `M README.md`.

- [ ] **Step 5: Commit**

```bash
git add README.md
git commit -m "docs(readme): update documentation index for new English doc set"
```

---

### Task 7: Cross-reference integrity + untouched-file gate (final)

**Files:**
- Read-only verification across the repo.

**Interfaces:**
- Consumes: all prior tasks.
- Produces: confirmation that no link is broken and the two owned files are unchanged.

- [ ] **Step 1: No dangling PRODUCT.md references anywhere**

Run: `rg -n "PRODUCT\.md" . --glob '!docs/superpowers/**'`
Expected: no matches (the deleted file is referenced nowhere). If any appear, fix that file and amend its commit.

- [ ] **Step 2: All internal doc links resolve**

Run: `rg -no "\]\((\.{0,2}/?[A-Za-z0-9_./-]+\.md)" -r '$1' README.md CLAUDE.md PROGRESS.md docs/*.md | sort -u`
Then eyeball each target path exists (`ls` the ones you're unsure of). Every linked `.md`
must exist. Fix any broken link and amend the owning commit.

- [ ] **Step 3: API.md and ARCHITECTURE.md are byte-for-byte unchanged**

Run: `git diff --stat master -- docs/API.md docs/ARCHITECTURE.md`
Expected: empty output (this branch introduced zero changes to those two files).

- [ ] **Step 4: AUDIT untouched**

Run: `git diff --stat master -- docs/AUDIT-2026-07-05.md`
Expected: empty output.

- [ ] **Step 5: Final status sanity**

Run: `git status --short && git log --oneline master..HEAD`
Expected: clean working tree; commits from Tasks 1–6 present (spec commit + 6 doc commits).

---

## Self-Review

**Spec coverage:**
- English translation of CLAUDE/PROGRESS/ROADMAP/DESIGN → Tasks 2–5. ✓
- README table update → Task 6. ✓
- ROADMAP changelog removal → Task 3. ✓
- PRODUCT merged into DESIGN + deleted → Task 2. ✓
- DEPENDENCIES.md created from manifests + pyacoustid finding → Task 1. ✓
- API.md/ARCHITECTURE.md untouched → Global Constraints + Task 7 Step 3. ✓
- AUDIT frozen → Global Constraints + Task 7 Step 4. ✓
- Cross-reference integrity → Task 7. ✓

**Placeholder scan:** No TBD/TODO. DEPENDENCIES.md content is fully written; translation
tasks specify exact source sections, target headings, keep/drop/merge rules, and a shared
glossary (full re-typing of 400+ translated lines inside the plan is neither feasible nor
useful — the instruction + glossary + verification is the executable unit for a translation
task).

**Type consistency:** File names, section headings, and the reading-order list are
consistent across Tasks 3–6 (DESIGN.md = "Product & Design"; no PRODUCT.md anywhere;
DEPENDENCIES.md added in Tasks 1, 5, 6).
