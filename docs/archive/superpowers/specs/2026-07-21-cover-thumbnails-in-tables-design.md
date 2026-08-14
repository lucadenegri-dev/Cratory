# Miniature delle copertine nelle tabelle (FILES, ISSUES, DUPLICATES, PLAN)

**Data:** 2026-07-21
**Stato:** design approvato, in attesa di piano

## Obiettivo

Rendere le tracce **riconoscibili a colpo d'occhio** mostrando la copertina in
ogni riga delle quattro tabelle che elencano file. Oggi l'unica immagine visibile
nell'app è la copertina *proposta* dai provider nella pagina ISSUES: l'artwork
già embeddato nei file non è servito da nessuna parte, benché `AudioFile.has_cover`
lo registri fin dallo scan.

In coda allo stesso obiettivo (riconoscere senza leggere) la colonna **Path**
smette di troncare la fine e mostra la coda del percorso, cioè il nome del file.

## Stato attuale

- `AudioFile.has_cover` (`models.py:57`) — booleano, valorizzato allo scan da
  `tagio._detect_cover`. Dice *se* c'è artwork, non lo espone.
- `integrations/tagio.py` — sa **scrivere** (`write_cover`, riga 216) e
  **rimuovere** (`remove_cover`, riga 243) la cover, ma non leggerla.
- `services/cover_cache.py` — cache su disco delle thumbnail **proposte** dai
  provider (`cover_cache/{file_id}.jpg`), servite da
  `GET /api/issues/cover-thumb/{file_id}` (`routers/issues.py:326`).
- `components/issues-table.tsx` — unico punto del frontend che mostra
  un'immagine, e solo per le issue `missing_cover`.
- `components/files-table.tsx` — tabella densa (righe ~26px, `text-xs`,
  monospace), colonna Path con `truncate` (ellissi in **coda**, quindi si legge
  l'inizio del percorso e si perde il nome del file).
- `file_id` è presente in tutte e quattro le liste del frontend
  (`FileRow.id`, `Issue.file_id`, `DupMember.file_id`, `PlanOp.file_id`):
  **un solo endpoint** serve tutte le pagine.

## Decisioni prese in brainstorming

| Domanda | Scelta |
|---|---|
| Dove mostrare le copertine | Tutte e quattro: FILES, ISSUES, DUPLICATES, PLAN |
| Traccia senza artwork nei tag | Proposta provider se già in cache, marcata come tale; altrimenti placeholder. **Nessuna** richiesta di rete durante lo scroll |
| Dimensione miniatura | **32px** (riga FILES ~38px, ≈ −30% righe per schermata). Confrontata visivamente con 20px e 48px |
| Quando generare le miniature | **On-demand + cache su disco**, non allo scan |

## Feature 1 — Backend: lettura artwork, cache, endpoint

### 1.1 `tagio.read_cover(path) -> bytes | None`

Speculare a `write_cover`. Ritorna i byte della copertina embeddata:

- **FLAC** → `raw.pictures`, preferendo `type == 3` (front cover);
- **ID3** (mp3/wav/aiff) → frame `APIC:`, stessa preferenza per il front;
- **MP4/M4A** → atom `covr`, primo elemento.

Se non c'è artwork, o il file è illeggibile, ritorna `None` (non solleva).

### 1.2 `services/thumbs.py` (nuovo)

Gemello di `cover_cache.py`, ma per l'artwork **già nel file**:

```
get_thumb(file_id: int, audio_path: str) -> bytes | None
```

1. se `thumb_cache/{file_id}.jpg` esiste **ed è più recente dell'mtime del file
   audio** → lo ritorna così com'è;
2. altrimenti `tagio.read_cover()`, ridimensiona con Pillow a **max 96px** lato
   lungo (JPEG q80, ~4 KB), salva nella cache e ritorna;
3. artwork assente o illeggibile → `None`.

Nuova voce in `core/config.py`:

```python
thumb_cache_dir: str = "./data/thumb_cache"
```

Directory **separata** da `cover_cache_dir`: entrambe le cache indicizzano per
`{file_id}.jpg` e condividerle causerebbe collisioni fra l'artwork reale e la
proposta di un provider per lo stesso file.

96px per una miniatura da 32px = 3×, nitida su display retina.

### 1.3 `GET /api/files/{file_id}/thumb`

In `routers/library.py` (che ha già prefix `/api` ed è il router read-only del
frontend):

1. se `AudioFile.has_cover` è `True` → `thumbs.get_thumb(...)`;
2. altrimenti, o se il passo 1 non produce byte → `cover_cache.read_thumb(file_id)`
   (proposta provider);
3. altrimenti → **404**.

Risposta `image/jpeg` con `ETag` derivato dall'mtime **del file audio** e
`Cache-Control`, così lo scroll non ripete le richieste già servite e un apply
che riscrive i tag invalida anche la copia nel browser.

`has_cover` funziona da **cache negativa gratuita**: un file senza artwork non
viene mai riaperto da disco, a nessuna richiesta.

### 1.4 `FileRow.cover_source`

Nuovo campo in `schemas.py`: `"embedded" | "provider" | None`, calcolato nella
query di `list_files` con una scalar-subquery accanto a quelle già presenti per
`issue_count` / `worst_rank` / `in_dup`:

```
has_cover                              → "embedded"
esiste Issue(missing_cover, status=open) → "provider"
altrimenti                              → None
```

La seconda condizione è affidabile perché `covers.upsert_cover_issue` crea
l'issue **solo** quando un provider ha davvero trovato un'immagine, quindi
l'esistenza dell'issue implica una thumb in `cover_cache`.

Serve al frontend per disegnare il placeholder **senza fare la richiesta** e per
distinguere visivamente una proposta da una copertina reale.

Caso limite: se `has_cover` è `True` ma l'artwork è corrotto, `cover_source` dice
`"embedded"` mentre l'endpoint ricade sulla proposta provider, che viene quindi
mostrata senza il tratteggio. È un file rotto e un pixel di stile: non vale una
seconda interrogazione del disco per ogni riga.

**Trade-off accettato:** `cover_source` viene aggiunto **solo** a `FileRow`. In
DUPLICATES e PLAN la miniatura ricade su `onError → placeholder` e non distingue
proposta da embedded. Sono liste corte, dove la distinzione conta poco; il campo
si può propagare agli altri schemi in un secondo momento se serve.

## Feature 2 — Frontend: un componente, quattro tabelle

### 2.1 `components/cover-thumb.tsx` (nuovo)

```tsx
<CoverThumb fileId={r.id} size={32} source={r.cover_source} />
```

- `source === null` → placeholder, **nessuna richiesta HTTP**;
- `source === "provider"` → `<img>` con bordo tratteggiato + opacità ridotta:
  segnala "questa copertina non è (ancora) dentro il file";
- altrimenti `<img>` piena;
- sempre `loading="lazy"`, `decoding="async"`, `width`/`height` fissi (niente
  layout shift durante il caricamento), `onError` → placeholder.

Il **placeholder** riusa il dither a scacchiera già presente nel design system
(`conic-gradient` di `.eqm-rest` in `globals.css`): quadrato, monocromo,
coerente con le barre di avanzamento.

### 2.2 Integrazione

Prima colonna (larghezza minima) in:

- `files-table.tsx` — riga da ~26px a ~38px;
- `dup-group.tsx` — due copertine diverse nello stesso gruppo sono il segnale
  più rapido che non è la stessa release;
- `plan-ops.tsx` — riconoscere cosa si sta per rinominare/spostare prima
  dell'apply;
- `issues-table.tsx` — accanto alla UI già esistente per `missing_cover`.

Tutte a `size={32}`.

## Feature 3 — Path troncato a sinistra

La cella Path di `files-table.tsx` passa da `truncate` a `direction: rtl` +
`text-align: left`: l'ellissi finisce in testa e la coda si adatta alla larghezza
della colonna.

```
prima:  /Users/lucadenegri/Music/Libr…
dopo:   …/Techno/Adam Beyer/Adam Beyer - Your Mind.flac
```

Il trucco CSS ha un solo caso problematico noto — percorsi che *terminano* con
un carattere neutro (es. `/`), che il layout bidirezionale può riposizionare.
Qui non si presenta: un `AudioFile.path` finisce sempre con `nome.ext`.
L'attributo `title` con il percorso completo resta.

## Errori e degrado

- File sparito, permessi negati, artwork corrotto → l'endpoint risponde **404**
  e il frontend mostra il placeholder. Una miniatura non deve mai produrre un
  500 né rompere la riga.
- Pillow che fallisce sul singolo artwork (formato esotico) → trattato come
  "nessuna copertina": 404, placeholder.

## Invalidazione della cache

L'mtime del file audio è l'unica sorgente di verità:

- apply che embedda una cover → mtime cambia → thumb rigenerata;
- `remove_cover` dell'undo → idem;
- rinomina/spostamento → cambia il path ma **non** `file_id` né mtime: la cache
  resta valida, nessun lavoro sprecato dopo un apply grosso.

## Dipendenze

**Pillow**, unica dipendenza nuova, in `requirements.txt` e in
`DEPENDENCIES.md`. A differenza delle chiavi provider è **obbligatoria**: senza
ridimensionamento le copertine embeddate (che arrivano a diversi MB l'una)
renderebbero l'endpoint inutilizzabile.

`data/thumb_cache/` è già coperto dal `.gitignore` esistente (`backend/data/`).

## Test

- `read_cover` — round-trip con `write_cover` su mp3, flac, wav, aiff, m4a,
  riusando le fixture esistenti; file senza artwork → `None`; file illeggibile
  → `None`.
- `get_thumb` — genera e salva; seconda chiamata serve dalla cache; thumb più
  vecchia dell'mtime del file → rigenerata; lato lungo ≤ 96px.
- Endpoint — 200 con artwork embeddato; 200 con fallback provider quando
  `has_cover` è `False`; 404 quando non c'è nulla; `has_cover=False` non apre il
  file.
- `list_files` — `cover_source` corretto nei tre casi.

## Fuori scope (YAGNI)

- Pre-generazione delle miniature allo scan o job "prepara miniature" in
  Settings: l'on-demand riempie la cache da sé. Si aggiunge solo se lo scroll
  risulta lento nell'uso reale.
- Download al volo dai provider per le righe senza copertina: introdurrebbe
  chiamate di rete e rate-limit durante lo scroll.
- Vista a griglia / modalità "sfoglia copertine", toggle compatta-vs-cover.
- Anteprima full-res al click.
- `cover_source` sugli schemi di ISSUES, DUPLICATES e PLAN.
