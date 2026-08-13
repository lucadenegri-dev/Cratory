# Revisione totale codice e documentazione — Design

Data: 2026-08-13
Stato: approvato dall'utente (design a sezioni, conversazione del 2026-08-13)

## Obiettivo

Dopo mesi di sviluppo il progetto ha accumulato codice morto/ridondante e una
documentazione stratificata, scritta più per l'AI che per un umano (riferimenti a
fasi F1-F6, lotti, cronologia delle fusioni). Questa revisione:

1. rimuove il codice morto e consolida le ridondanze evidenti, con i test come
   rete di sicurezza;
2. archivia il materiale documentale storico fuori dal percorso di lettura;
3. riscrive le docs vive per un lettore umano che deve capire il progetto oggi.

Modalità scelta: **revisione e correzione in un unico passaggio** (niente fase di
solo-audit), con **checkpoint per area** — a fine fase commit, riepilogo, e
possibilità per l'utente di fermare o correggere la rotta.

## Perimetro

- Backend: `backend/app/` (~23k righe Python), `requirements.txt`, test.
- Frontend: `frontend/` (~18k righe TS/TSX), `package.json`, i18n, test.
- Docs storiche: `PROGRESS.md` (1.410 righe), `docs/AUDIT-2026-07-05.md`,
  `docs/organize/` (storico Sortory), `docs/superpowers/` (148 file specs+plans,
  inclusa questa spec una volta eseguita la Fase 3).
- Docs vive: `README.md`, `docs/ARCHITECTURE.md`, `docs/API.md`,
  `docs/ROADMAP.md`, `docs/DESIGN.md`, `docs/DEPENDENCIES.md`, `CLAUDE.md`,
  `frontend/CLAUDE.md`.

Fuori perimetro: schema DB (colonne/tabelle sospette vengono solo segnalate),
refactoring architetturali profondi (solo segnalati), qualunque mutazione dei
file audio dell'utente.

## Struttura in 5 fasi

L'ordine è vincolato: il codice prima delle docs (le docs devono descrivere lo
stato post-pulizia), le docs storiche prima delle vive (lo spostamento cambia i
percorsi che le docs vive citano).

### Fase 0 — Baseline

- Setup del worktree: `npm install` reale nel frontend (i symlink a
  `node_modules` rompono Turbopack), pytest col venv del checkout principale
  (cwd = backend del worktree).
- Giro completo di verifica: `pytest` backend, `lint` + `build` + test frontend.
  Se qualcosa è già rosso, si registra e si segnala prima di procedere.
- Snapshot delle metriche: righe di codice per area, numero endpoint, numero
  dipendenze (pip e npm), righe delle docs vive. Serve per il confronto finale.

### Fase 1 — Backend

- Rilevamento: vulture + ruff sul Python; incrocio endpoint censiti in
  `docs/API.md` e nei router contro le chiamate reali dal frontend; servizi e
  repository mai importati; dipendenze in `requirements.txt` mai usate; modelli
  o colonne orfane (solo segnalazione).
- Azione: rimozione del morto confermato, consolidamento duplicazioni evidenti,
  test verdi, commit tematici.

### Fase 2 — Frontend

- Rilevamento: knip + depcheck; componenti e hook mai importati; pagine orfane
  (attenzione alle convenzioni App Router); dipendenze npm inutilizzate; chiavi
  i18n morte (entrambe le lingue); duplicazioni evidenti tra componenti.
- Azione: come Fase 1, più `npm run lint` e `npm run build` verdi.

### Fase 3 — Docs storiche (archiviazione, non cancellazione)

- `PROGRESS.md` ridotto a un riassunto di ~30 righe; il diario completo va in
  `docs/archive/`.
- `docs/AUDIT-2026-07-05.md`, `docs/organize/` storico e l'intero
  `docs/superpowers/` spostati sotto `docs/archive/` con un indice breve.
- Aggiornamento dei riferimenti ai nuovi percorsi in CLAUDE.md e nelle docs vive.

### Fase 4 — Docs vive (riscrittura per ruolo)

- `README.md`: vetrina in inglese per un lettore esterno; via i riferimenti a
  fasi di sviluppo.
- `ARCHITECTURE.md`, `API.md`, `DESIGN.md`, `DEPENDENCIES.md`: riscritte per un
  umano che deve capire il progetto oggi; la cronologia (F1-F6, lotti,
  "ex Sortory" come storia) sparisce, resta solo ciò che spiega il presente.
- `ROADMAP.md`: asciugata a stato attuale + backlog reale.
- `CLAUDE.md`: resta l'unico documento ottimizzato per l'AI; aggiornato per
  coerenza con i nuovi percorsi e con ciò che è stato rimosso.
- Controllo finale link/percorsi: nessun riferimento a file spostati o rimossi.

## Metodo di rilevamento: doppia conferma

Gli strumenti statici producono candidati, non verdetti: i router FastAPI sono
registrati dinamicamente, Next.js App Router carica le pagine per convenzione di
percorso, i componenti possono essere referenziati solo via JSX. Ogni candidato
passa una seconda verifica indipendente: grep sull'intero repo (test inclusi),
controllo entrypoint/convenzioni framework, e per gli endpoint il confronto con
le chiamate reali dal frontend. La fase di incrocio usa subagenti di ricerca in
parallelo. Si rimuove solo ciò che risulta morto da entrambe le vie.

## Tre livelli di azione

1. **Rimozione diretta** — non referenziato da nessuna parte: import morti,
   funzioni/componenti mai usati, endpoint mai chiamati né documentati come API
   pubblica, dipendenze assenti dal codice, chiavi i18n orfane. I test che
   coprivano solo codice rimosso se ne vanno con esso.
2. **Consolidamento** — duplicazioni evidenti e a basso rischio, solo quando la
   fusione è meccanica e i test coprono il comportamento; altrimenti si
   retrocede al livello 3.
3. **Solo segnalazione** — implicazioni oltre il codice: colonne/tabelle DB
   sospette, ridondanze architetturali profonde, endpoint che sembrano
   inutilizzati ma potrebbero servire a script esterni o a chiamate manuali.
   Finiscono nella lista del riepilogo di fase; decide l'utente.

**Regola speciale Organize** (`backend/app/organize/`): unico scrittore di tag,
con journal di undo. Lì il livello 2 è disattivato: solo rimozioni certe
(livello 1) o segnalazioni (livello 3).

## Verifica e checkpoint

- Ogni fase chiude solo con: pytest backend verde, lint + build + test frontend
  verdi, e per le fasi docs il controllo link/percorsi.
- Commit piccoli e tematici (es. "endpoint orfani", "chiavi i18n morte"): ogni
  rimozione è revertibile da sola.
- Checkpoint di fine fase in tre blocchi: **rimosso** (cosa e perché era morto),
  **consolidato** (quali duplicazioni e come), **segnalato** (lista livello 3
  con valutazione). L'utente decide se proseguire, correggere, o promuovere
  segnalazioni a rimozione.

## Consegna finale

- Confronto con la baseline: righe rimosse, endpoint eliminati, dipendenze
  tolte, docs vive prima/dopo.
- Lista consolidata delle segnalazioni di livello 3 non affrontate.
- Struttura docs finale: docs vive snelle e per umani, `docs/archive/` con
  indice, CLAUDE.md coerente.
- Il lavoro resta sul branch del worktree; merge su master o PR da decidere
  insieme a fine lavoro.
