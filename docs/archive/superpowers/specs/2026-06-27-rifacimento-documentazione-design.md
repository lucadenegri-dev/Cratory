# Rifacimento documentazione — Design

> Spec del punto roadmap "Rifacimento documentazione". Approccio approvato: **ridisegno
> dell'architettura doc** (Approccio A), pubblico misto (autore + agent AI + portfolio/OSS),
> vetrina in inglese e resto in italiano.

## 1. Contesto e problema

Il nucleo tecnico (`README`, `docs/ARCHITECTURE`, `docs/API`, `docs/ROADMAP`, `PROGRESS`)
è aggiornato al 2026-06-27 e sostanzialmente solido. Il problema non è il contenuto dei
singoli doc ma la **deriva ai bordi**: incoerenze, doppioni e orfani accumulati durante
l'evoluzione incrementale del prodotto.

Sei problemi rilevati:

1. **`PRODUCT.md` è obsoleto e contraddice il design reale.** Cita "accento **lime** è la
   luce dello studio", personalità "fluida, creativa, sperimentale", e tra le anti-reference
   rifiuta "cream backgrounds / pastel". Ma `DESIGN.md` descrive il sistema realmente
   implementato: "editorial archive" **monocromo** con **un solo rosso**, tema **paper
   (cream) deliberato**, "quiet, typographic, archival instrument". `PRODUCT.md` è rimasto
   all'era pre-rebranding.
2. **`DESIGN.md` e `PRODUCT.md` sono orfani**: non compaiono nella "fonte di verità" di
   `CLAUDE.md`, né in `AGENTS.md`, né nella tabella documentazione del `README`.
3. **Doppia fonte di verità sullo stato.** `ROADMAP` ("Stato completato" / "Prossimi passi")
   e `PROGRESS` ("Funzionalità completate" / "Prossimi step") si sovrappongono molto e
   sono già parzialmente divergenti.
4. **`CLAUDE.md` ≈ `AGENTS.md`** quasi identici (era intenzionale per supportare Codex).
5. **Asset grafici orfani**: `docs/flusso-servizi.png` (1.5 MB) e `docs/servizi-sinergie.svg`
   non sono referenziati da nessun doc.
6. **Staleness residue**: la riga "Fase" di `PROGRESS` dice "documentazione riscritta"
   (eredità del reset SetArc del 18/06); `.impeccable/design.json` dice ancora
   "SetArc / SETARC wordmark".

## 2. Decisioni (input utente)

- **Ambizione**: ridisegno dell'architettura doc (non solo riconciliazione chirurgica,
  non riscrittura da zero).
- **Pubblico**: autore + agent AI + portfolio/open-source. Il `README` diventa anche
  vetrina che regge lo sguardo di un lettore esterno.
- **Lingua**: `README` (livello vetrina) in **inglese**; resto della documentazione in
  **italiano**. `DESIGN.md` resta inglese (nativo del design system).
- **Toolchain agent**: solo Claude (niente Codex). Quindi `AGENTS.md` (root e frontend)
  va eliminato e accorpato in `CLAUDE.md`.
- **`PROGRESS` + `ROADMAP`**: si tengono **entrambi**, con confini netti (vedi §4).

## 3. Architettura target

### Mappa file

| File | Lingua | Ruolo |
|---|---|---|
| `README.md` | 🇬🇧 EN | Vetrina / porta d'ingresso esterna |
| `CLAUDE.md` | 🇮🇹 IT | Unica guida agent (assorbe AGENTS.md) |
| `PROGRESS.md` | 🇮🇹 IT | Solo diario cronologico + punto di ripresa |
| `docs/ARCHITECTURE.md` | 🇮🇹 IT | Principi, pipeline, layer, dati, integrazioni |
| `docs/API.md` | 🇮🇹 IT | Reference REST |
| `docs/ROADMAP.md` | 🇮🇹 IT | **Unica fonte di verità** stato + direzione |
| `docs/PRODUCT.md` | 🇮🇹 IT | Brief prodotto, riconciliato con l'editorial-archive |
| `docs/DESIGN.md` | 🇬🇧 EN | Design system (spostato da root) |
| `frontend/CLAUDE.md` | 🇬🇧 EN | Regole Next.js inline |

### Eliminazioni

- `AGENTS.md` (root) — contenuto utile assorbito in `CLAUDE.md`.
- `frontend/AGENTS.md` — contenuto (regole Next.js) inline in `frontend/CLAUDE.md`,
  rimuovendo l'indirezione `@AGENTS.md`.
- `docs/flusso-servizi.png` e `docs/servizi-sinergie.svg` — asset orfani.
- Copia untracked `docs/servizi-sinergie.svg` (working tree) — non aggiungere.

### Aggiunte

- Un diagramma architettura **attuale** (SVG, monocromo coerente col design system) per
  il `README`. Sostituisce gli orfani ritirati.

## 4. Contratto anti-deriva (cuore del ridisegno)

Ogni informazione ha **un solo proprietario canonico**. Gli altri doc linkano, non copiano.

| Informazione | Proprietario canonico | Chi linka |
|---|---|---|
| Stato completato (funzionalità) | `docs/ROADMAP.md` | PROGRESS, README |
| Prossimi passi / priorità | `docs/ROADMAP.md` | PROGRESS |
| Direzione prodotto / decisioni / rischi | `docs/ROADMAP.md` | PRODUCT, PROGRESS |
| Narrativa prodotto (users, JTBD, principi) | `docs/PRODUCT.md` | README |
| Design system | `docs/DESIGN.md` | README, PRODUCT |
| Riferimento operativo (db/log path, redirect, comandi) | `README.md` + `CLAUDE.md` | PROGRESS |
| Diario milestone + punto di ripresa | `PROGRESS.md` | — |

### Confine ROADMAP vs PROGRESS

- **`ROADMAP.md`** = presente + futuro, organizzato **per argomento**, curato/riscritto.
  Risponde a "dove siamo e dove andiamo?". Tiene: naming, stato completato (curato),
  prossimi passi (prioritizzati), sospesi, backlog tecnico, direzione prodotto, rischi,
  decisioni consolidate.
- **`PROGRESS.md`** = passato + "dove ho lasciato", organizzato **per data**, append-only.
  Risponde a "cos'è successo, in che ordine, e dove riprendo?". Tiene **solo**: narrativa
  delle milestone datate, fase corrente, punto di ripresa. **Non** ripete liste di
  completato/prossimi/decisioni: le linka in ROADMAP. Le milestone sono di livello
  narrativo (aggregano molti commit), non un changelog commit-per-commit (quello è git).

## 5. Spec per file

### `README.md` (EN, vetrina)
Sezioni: titolo + tagline; **What & why** (pitch riformulato sulla natura reale —
strumento personale/self-hosted per DJ, esplicitamente **non** un SaaS Spotify; il vincolo
policy Spotify spiegato come scelta di design, non come limite subìto); **Features**
(bullet sintetici); **Architecture at a glance** (diagramma nuovo + 3-4 frasi su motore
deterministico vs AI); **Tech stack**; **Quickstart** (setup backend + frontend, env
minime); **Documentation** (tabella link a tutti i doc, inclusi PRODUCT/DESIGN);
**Status** (1-2 righe → `docs/ROADMAP.md`). Il workflow consigliato e i dettagli setup
estesi possono restare nel README o linkare; mantenere il README scorrevole per un lettore
esterno (evitare il muro di dettagli operativi dell'attuale).

### `CLAUDE.md` (IT, unica guida agent)
Assorbe da `AGENTS.md`: descrizione progetto, **regole non negoziabili** (le 8), stack +
layer backend, identità tracce e stati, catena provider, comandi (backend/frontend,
incl. PowerShell), nota Next.js 16. Aggiorna la "fonte di verità" (ordine di lettura) per
includere `docs/PRODUCT.md` e `docs/DESIGN.md` e togliere `AGENTS.md`. Aggiorna la
self-description: rimuovere "entrypoint per l'AI usata insieme a Codex" e la nota
"non eliminarlo durante cleanup"; diventa semplicemente la guida agent del progetto.

### `PROGRESS.md` (IT, diario)
Riduci a: intestazione (ultimo aggiornamento, nome prodotto, fase corrente — corretta),
**milestone datate** (mantieni 18/06, 23/06, 27/06 come narrativa), **punto di ripresa**
(cosa fare dopo, con link a ROADMAP per le priorità). Rimuovi "Funzionalità completate",
"Prossimi step", "Prossimi passi consigliati", "Decisione 23/06" (→ ROADMAP/PRODUCT),
"Note operative" e "Verifiche consigliate" (→ README/CLAUDE/ARCHITECTURE), riducendoli a
puntatori dove serve.

### `docs/ROADMAP.md` (IT, fonte di verità stato)
Mantieni struttura attuale (è già la più completa). Assicura che sia l'**unico** posto con
le liste di stato. Verifica coerenza dei contenuti con PROGRESS prima di deduplicare.

### `docs/PRODUCT.md` (IT, riconciliato)
Riscrivi **Brand Personality**, **Anti-references**, **Design Principles** per allinearli
all'editorial-archive: via "accento lime", via il rifiuto del "cream" (il tema paper è
deliberatamente cream), personalità → "quiet, typographic, archival" coerente con DESIGN.
Mantieni le parti valide e non contraddette: **Users**, **Job to be done**, **Product
Purpose**, **Accessibility**. Allinea con la direzione prodotto (personale/self-hosted) di
ROADMAP. Linka `docs/DESIGN.md` come dettaglio del sistema visivo.

### `docs/DESIGN.md` (EN, spostato)
Sposta `DESIGN.md` → `docs/DESIGN.md` invariato nel contenuto (la skill `impeccable` legge
`.impeccable/design.json`, non il markdown — spostamento sicuro). Separatamente, correggi
`.impeccable/design.json`: `title` e la voce typography `brand` da "SetArc / SETARC" a
"Cratory / CRATORY".

### `frontend/CLAUDE.md` (EN)
Inserisci direttamente le regole Next.js (oggi in `frontend/AGENTS.md`), rimuovendo
`@AGENTS.md`. Elimina `frontend/AGENTS.md`.

### `docs/ARCHITECTURE.md` e `docs/API.md`
Nessun cambio di ruolo. Sottoposti all'audit di accuratezza (§6).

## 6. Audit di accuratezza

Dato che i doc diventano anche vetrina, verifica che riflettano il codice reale:

- **API.md vs router**: confronta gli endpoint elencati con `backend/app/routers/*`.
  Allinea path, metodi e descrizioni; segnala endpoint mancanti o rimossi.
- **ARCHITECTURE.md vs codice**: verifica layer backend (`routers/services/repositories/
  models/schemas/serializers/integrations/core`), catena provider
  (`Deezer → MusicBrainz → AcousticBrainz → GetSongBPM → Last.fm`), entità del modello
  dati e flussi (import, enrichment, discovery expand/dig, shazam).
- **README quickstart**: verifica comandi, path env e porte contro `backend/.env.example`
  e gli script reali.

Discrepanze trovate → corrette nel doc relativo (non nel codice: l'audit è documentale).

## 7. Non-goal

- Nessuna migrazione a docs-site / generatore statico (Approccio C scartato).
- Nessun accorpamento aggressivo dei doc tecnici (Approccio B scartato).
- Nessuna traduzione in inglese di ARCHITECTURE/API/ROADMAP/PRODUCT (restano italiano).
- Nessun rename di path tecnici legacy (`djassistant.db`, log path) — fuori scope.
- Nessuna modifica al codice applicativo (solo `.impeccable/design.json` come fix dato).
- Nessuna i18n dell'app (sospesa in roadmap).

## 8. Criteri di successo

- Ogni informazione ha un solo proprietario canonico; nessuna lista di stato duplicata.
- `README` leggibile da un esterno in inglese, con architettura a colpo d'occhio.
- `PRODUCT` non contraddice più `DESIGN`.
- Nessun doc orfano: tutti raggiungibili dagli indici (README + CLAUDE).
- `ARCHITECTURE` e `API` verificati contro il codice.
- Nessun file `AGENTS.md` residuo; `CLAUDE.md` è la guida agent unica.
- Asset grafici orfani ritirati; un diagramma attuale nel README.
