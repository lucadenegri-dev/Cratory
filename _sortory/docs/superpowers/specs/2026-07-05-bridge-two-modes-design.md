# Bridge Cratory a due modalità: "Riempi" e "Importa" (+ match per path)

Data: 2026-07-05
Stato: approvato da Luca (conversazione del 2026-07-05)
Repo coinvolti: DjOrganizer01 (questo) e DJProject01 (Cratory)

## Problema

"Suggerisci da Cratory" oggi fa una cosa sola: riempie i suggerimenti sulle
issue aperte e, per i soli file con ISRC, segnala discrepanze artist/title/genre
come `bridge_mismatch`. Luca vuole distinguere due intenti:

- **A) Riempi**: usa Cratory solo per colmare i buchi, non toccare mai un campo
  già valorizzato.
- **B) Importa**: proponi i valori Cratory anche dove il file ha già un valore
  diverso, su tutti i campi del contratto — ma **mai svuotare** un campo se
  Cratory non ce l'ha (nessun suggerimento a null/vuoto).

Inoltre molti file non hanno ISRC, ma in Cratory Luca collega a mano la traccia
al file su disco (`local_path`, via link-file o indicizzazione libreria): quel
collegamento è un match certo quanto l'ISRC e il bridge deve poterlo usare.

## Decisioni (dalle domande di brainstorming)

1. **Modalità B = suggerimenti da accettare.** Niente auto-accettazione: le
   proposte restano issue da rivedere col ✓; nulla entra nel PLAN da solo.
2. **Sovrascritture solo con match certo**: `path` o `isrc` (confidence 100).
   Il match fuzzy artist+title (70) resta valido solo per riempire i buchi.
3. **Catena di fiducia del genere invariata anche in B**: la sovrascrittura del
   genere è proposta solo se `genre_source` di Cratory è `manual` o `provider`
   (mai `ai`/`file_tag`, che non sono meglio del tag nel file).

## Modifiche a Cratory (DJProject01)

`GET /api/tracks/lookup` accetta un nuovo parametro opzionale `path`:

- Validazione: serve `path` OPPURE `isrc` OPPURE `artist`+`title` (422 se nulla).
- Priorità di match: `path` → `isrc` → fuzzy artist+title.
- Match per path: confronto esatto su `Track.local_path` dopo normalizzazione
  `str(Path(path).expanduser())` (stessa normalizzazione di `link_local_file`).
- Risposta: `match: "path"`, `confidence: 100`; resto del contratto invariato.
- `TrackLookupOut` aggiornato se il campo `match` è vincolato a valori enumerati.

## Modifiche a DjOrganizer

### Client bridge (`services/cratory_bridge.py`)

`lookup()` accetta `path` opzionale e lo manda insieme alle altre chiavi
disponibili in un'unica GET (Cratory applica la priorità). La guardia diventa:
serve `path` oppure `isrc` oppure `artist`+`title`.

### Endpoint (`routers/issues.py`)

`POST /api/issues/bridge-suggest` accetta body `{"mode": "fill" | "import"}`,
default `"fill"` (retro-compatibile con la POST senza body).

Lookup per file (cache invariata, una GET per file): passa sempre `AudioFile.path`
(già assoluto: costruito da `os.walk(root.path)` in `scanner.py`, nessuna
ricostruzione necessaria) più ISRC e artist+title se presenti. Ogni file
present è quindi interrogabile, anche senza ISRC e senza tag.

**Modalità `fill`** (ex comportamento, depurato):
- Riempie `suggested_fix_json` sulle issue aperte (`missing_required_tag`,
  `missing_metadata`, `dirty_genre`) come oggi; qualunque match (anche fuzzy)
  va bene per un buco; valore vuoto in Cratory → issue resta senza suggerimento
  (mai null).
- Pulisce le `bridge_mismatch` orfane il cui file non è più `present`.
- **Non** crea/aggiorna discrepanze: un campo già valorizzato non viene toccato.

**Modalità `import`** = tutto quello che fa `fill`, più il check discrepanze
generalizzato:
- Candidati: tutti i file `present` (non più solo quelli con ISRC).
- Gating: solo `match in ("path", "isrc")`; fuzzy o not-found → nessuna azione
  sulle discrepanze di quel file (né creazione né cancellazione).
- Campi: tutti e 6 (`artist`, `title`, `genre`, `year`, `label`, `album`).
  Confronto normalizzato (`_norm`) per le stringhe, confronto numerico per
  `year`. Campo vuoto in Cratory → si salta (mai proporre lo svuotamento).
  Campo vuoto nel file (anche se Cratory ce l'ha) → si salta anche qui: è un
  buco, ci pensa il riempimento (Step 1/`missing_metadata`), non il mismatch —
  stessa regola già in vigore oggi per il genere, estesa a tutti i campi.
- Genere: proposta di sovrascrittura solo se `genre_source ∈ {manual, provider}`.
- Le issue `bridge_mismatch` aperte vengono aggiornate; quelle
  accettate/rifiutate non si toccano. Per i soli file con match certo, le
  discrepanze aperte non più confermate (campo ora uguale, o campo Cratory
  vuoto) si cancellano — stessa semantica di oggi, estesa ai 6 campi. Per i
  file senza match certo non si cancella né si crea nulla (coerente col gating).
- La regola di orfanità perde la condizione "senza ISRC": un file senza ISRC ora
  è verificabile via path. Orfana = file non più `present`.

Risposta: contatori attuali (`configured`, `files`, `suggested`, `unresolved`,
`mismatches`) + echo di `mode`. In `fill`, `mismatches` è sempre 0.

### Frontend

- `lib/api.ts`: `bridgeSuggest(mode)`.
- Pagina ISSUES: due pulsanti al posto di uno — "⇄ Riempi da Cratory" e
  "⇄ Importa da Cratory" — busy state condiviso, messaggi di esito distinti
  (import riporta anche il numero di discrepanze proposte).

### Documentazione

Contratto bridge aggiornato nei docs di entrambi i repo (parametro `path`,
match `"path"`, le due modalità).

## Error handling

Invariato: Cratory irraggiungibile → rollback e risposta "non configurato"
(nessuna modifica parziale). `mode` sconosciuto → 422.

## Test (TDD, entrambi i repo)

Cratory: match per path (esatto, normalizzato, expanduser), priorità
path>isrc>fuzzy, 422 senza chiavi, `found=false` se path ignoto.

DjOrganizer: client manda il path; `fill` non crea mismatch e non tocca campi
pieni; `import` propone su tutti i 6 campi solo con match certo (path o isrc);
mai suggerimenti vuoti/null; genere protetto da `genre_source`; fuzzy = solo
riempimento; orfane cancellate solo per file non-present; default mode=fill;
mode invalido → 422. Frontend: build ok (nessun test UI automatico previsto).

## Ordine di rollout

1. Cratory: lookup con `path` (+ test) — prerequisito.
2. DjOrganizer backend: client + endpoint a modalità (+ test).
3. DjOrganizer frontend: due pulsanti.
4. Docs contratto nei due repo.

Integrazione: merge in main + push su entrambi i repo (preferenza standard).
