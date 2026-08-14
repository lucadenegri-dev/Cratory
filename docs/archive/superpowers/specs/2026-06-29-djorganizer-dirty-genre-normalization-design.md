# DjOrganizer — Normalizzazione AI dei "generi sporchi"

> Data: 2026-06-29 · Stato: design approvato, pronto per il plan.
> Estensione di [[ai-genre-suggestions]]. App in `main` @ `177f5c7`.

## 1. Contesto

Dopo l'apply, la libreria ha ~12 cartelle-spazzatura sotto `…/Library/` perché il folder
template è `{genre}/{artist}` e **37 file** avevano un genere brutto **nei tag originali**:
blob multi-genere (`Techno, House, Breakbeat, …`), separati da `/`, URL
(`http://vk.com/…`), parole inutili (`Unbekannt`, `Music`, `Other`). L'AI non li aveva
toccati perché un genere *ce l'avevano* (non erano "mancanti"). Servono normalizzati nei
**tag**, non solo nelle cartelle, così anche Rekordbox li vede puliti.

## 2. Scope

**Dentro:**
- Nuova issue **`dirty_genre`** (warning, field `genre`): l'Inspector segnala i generi
  *presenti ma sporchi*.
- Il bottone esistente **"Suggerisci genere"** (`POST /api/issues/ai-suggest-genre`) le
  gestisce insieme ai `missing_metadata/genre`, passando all'AI il genere attuale come
  indizio → propone **un genere pulito** → l'utente rivede/accetta → retag → re-apply.

**Fuori:**
- Il caso ` - ` (es. `Electro - Dance`, 12 file): **non** considerato sporco (scelta
  conservativa dell'utente).
- Anno/label, scrittura su disco diretta, auto-accept.
- Rimozione delle cartelle-spazzatura rimaste vuote dopo il re-apply (eventuale follow-up).

## 3. Design (approvato)

### Regola "sporco" — `inspector._is_dirty_genre(value) -> bool`
Genere presente e non vuoto, ed **uno** tra:
- contiene un separatore multi-genere `,` `/` `;` (NON `&`, NON ` - `, NON `-` semplice);
- contiene un URL: `http` / `://` / `www.` (case-insensitive);
- è una parola-spazzatura (trim + lower) in
  `{unbekannt, unknown, sconosciuto, music, other, various, n/a, none}`.

Esiti per il genere: assente → `missing_metadata/genre` (invariato); presente+sporco →
`dirty_genre`; pulito → nessuna issue. (Catalogo conservativo: cattura 25/37 file; lascia i
12 `Electro - Dance`.)

### Inspector
In `_inspect_one`, dopo il loop `missing_metadata` (invariato), aggiungere:
```python
if _present(f.genre) and _is_dirty_genre(f.genre):
    out.append(IssueComputed(f.id, "dirty_genre", "genre", "warning",
                             "genere da normalizzare", None))
```
Minimale: non altera il comportamento `missing_metadata` esistente.

### Endpoint `POST /api/issues/ai-suggest-genre`
- La select passa da `type == "missing_metadata"` a
  `type.in_(("missing_metadata", "dirty_genre"))` (sempre `field == "genre"`, status open,
  `suggested_fix_json is None` filtrato in Python).
- `_describe(f)` aggiunge il genere attuale quando presente:
  `"{artista} - {titolo} [genere attuale: {f.genre}]"` (per i missing resta senza genere).
  Così Haiku normalizza il blob al primario (`"Techno, House, …"` → `"Techno"`).
- Il resto invariato: imposta `suggested_fix_json = {"field":"genre","action":"retag",
  "to":<pulito>}` (status open), ritorna `{configured, files, suggested, unresolved}`.

### Accettazione → apply
`genre` è già in `_RETAGGABLE`: accettare col `✓` (→ `/fix`) imposta il retag (before =
genere sporco dal DB, after = pulito). Il re-apply riscrive il tag e sposta il file nella
cartella pulita (`{genre}/{artist}`).

### Frontend
Nessuna modifica strutturale: le `dirty_genre` compaiono in ISSUES (filtrabili per tipo e
per il filtro campo `genre`), con input genere editabile (field retaggabile). Unico
ritocco: la nota di `onAiGenres` diventa "N generi suggeriti (mancanti + sporchi) …".

## 4. Errori, edge case

- **Genere già pulito**: nessuna issue, l'AI non lo tocca.
- **`Electro - Dance` / `Drum & Bass` / `Tech House`**: NON sporchi (no `,`/`/`/`;`, no URL,
  no junk-word) → invariati.
- **AI ritorna null**: issue senza suggerimento (fix manuale), conteggiata in `unresolved`.
- **Idempotente**: salta i `dirty_genre` già con `suggested_fix`.
- **No key**: `{configured:false}`, nessun crash (invariato).

## 5. Test

- **Inspector (pytest)**: `_is_dirty_genre` via `inspect([file])` — `,`/`/`/URL/junk →
  emette `dirty_genre`; `Electro - Dance`, `Drum & Bass`, `Tech House` → nessun
  `dirty_genre`; genere assente → `missing_metadata` (invariato); genere pulito → nessuna
  issue di genere.
- **Endpoint (pytest, Haiku mockato)**: una issue `dirty_genre` viene processata; la
  descrizione passata a `suggest_genres` contiene `"[genere attuale: …]"`; il
  `suggested_fix` viene impostato (status open).
- **Frontend**: `npm run lint` + `npm run build` verdi.

## 6. Convenzioni & DoD

- Inspector puro/deterministico; endpoint sottile; test pristine; JSON-null in Python.
- **DoD**: `pytest` verde; lint+build verdi. Dopo un re-scan compaiono le issue
  `dirty_genre`; "Suggerisci genere" le pre-riempie con un genere pulito (usando il genere
  attuale come contesto); accettando e ri-applicando i file finiscono in cartelle pulite;
  `Electro - Dance` e i generi single-word restano intatti.
