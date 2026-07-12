# Vista griglia libreria + motivo dei download falliti

Data: 2026-07-12
Stato: design approvato, pronto per il piano di implementazione.

Due feature indipendenti, sviluppabili in qualsiasi ordine:

1. **Vista griglia della libreria** — presentazione alternativa (card cover-centriche
   come i risultati Discovery), selezionabile e ricordata tra le sessioni.
2. **Perché un download è fallito** — il backend cattura e propaga il motivo reale
   del fallimento; il frontend lo mostra tradotto (IT/EN).

---

## Feature 1 — Vista griglia della libreria

### Obiettivo

Offrire, accanto alla tabella densa attuale, una vista a griglia di card centrate
sulla cover — lo stesso linguaggio visivo dei risultati Discovery
(`DiscoveryLeadGrid`). L'utente sceglie la vista con un toggle; la scelta persiste
in `localStorage`.

### Cosa mostra una card

- **Cover** quadrata (`aspect-square`) via `TrackCover`, che linka a `/tracks/{id}`.
- **Badge BPM·Key** in overlay nell'angolo basso della cover (stesso stile del
  `format_badge` di Discovery, `absolute … border border-border-strong bg-bg`).
  Formato `128 · 7A`, `tnum`. Mostrato solo se `bpm` e/o `camelot_key` presenti;
  se manca uno dei due si mostra solo l'altro; se mancano entrambi, nessun badge.
- Sotto la cover: **titolo** (`truncate`, `font-medium`) e **artista** (`text-faint`),
  identico all'impaginato di `LeadCell`. Titolo mancante → «senza titolo» in corsivo
  (riusa `t.library.untitledTrack`).
- **Pencil di modifica** su hover nell'angolo alto destro della cover → chiama
  `onEdit(track)`, per parità funzionale con la lista. Visibile solo su
  hover/focus (`opacity-0 group-hover:opacity-100`), come l'overlay di Discovery.

### Nuovo componente

`frontend/components/library-track-grid.tsx`

```
export function LibraryTrackGrid({
  tracks,          // Track[]
  onEdit,          // (t: Track) => void
}: { tracks: Track[]; onEdit: (t: Track) => void })
```

- Contenitore: `grid grid-cols-[repeat(auto-fill,minmax(120px,1fr))] gap-3`
  (identico a `DiscoveryLeadGrid`).
- Sotto-componente `LibraryTrackCard` per la singola card (pattern `LeadCell`).
- Il componente rende **solo** la griglia delle card. Stati loading/empty e
  paginazione restano nella pagina (condivisi con la lista).
- Nessuna chiamata dati propria: riceve `tracks` già filtrati/paginati.

### Modifiche alla pagina `frontend/app/library/page.tsx`

- Nuovo state `view: "list" | "grid"`, default `"list"`.
- **Persistenza `localStorage`** chiave `cratory:library:view`:
  - Lettura in un `useEffect` on-mount (mai durante il render/SSR → niente
    hydration mismatch). Valore non valido → si resta su `"list"`.
  - Scrittura in un `useEffect` su ogni cambio di `view`.
- **Toggle**: piccola toolbar sopra il contenitore risultati, con un segmented
  control allineato a destra (due bottoni icona lucide `List` / `LayoutGrid`),
  `aria-pressed`, stesso stile dei toggle sort di Discovery
  (`inline-flex rounded-none border border-border bg-surface p-0.5`).
  `title`/`aria-label` da i18n.
- **Render condizionale** del corpo risultati:
  - `view === "list"` → la `<table>` attuale, invariata.
  - `view === "grid"` → `<LibraryTrackGrid tracks={items} onEdit={setEditing} />`.
  - `items === null` (loading) e `items.length === 0` (empty) gestiti **una volta
    sola, fuori dal ramo**, così entrambe le viste mostrano lo stesso
    `<Loading />` / empty state.
- **Invariati e condivisi**: filtri (marginalia), paginazione, `TrackEditModal`,
  `error`. Il toggle cambia solo la presentazione, non i dati né i filtri attivi.

### i18n

Sezione `library` in `frontend/lib/i18n/it.ts` e `en.ts`:

- `viewListLabel` — IT «Lista» · EN "List"
- `viewGridLabel` — IT «Griglia» · EN "Grid"

(usati per `title`/`aria-label` dei bottoni del toggle)

---

## Feature 2 — Perché un download è fallito

### Problema

Oggi ogni esito `failed` viene persistito con `last_download_reason = None`
(vedi `soulseek_download_job.py`: `_attempt_download` ritorna `("failed", None,
None)`, `_process_item` collassa la cascata a `("failed", None, None)`, e il
fallback d'eccezione in `_run` non imposta alcun motivo). In UI la riga mostra
solo il badge rosso «fallita», senza spiegazione. L'informazione sul *perché*
esiste dentro `_wait_for_download`/`_download_candidate` ma viene scartata.

`not_found` e `needs_review` **restano invariati**: il primo è auto-esplicativo,
il secondo porta già un motivo in prosa. Interveniamo **solo su `failed`**.

### Approccio

Il backend propaga un **codice motivo** stabile fino a `track.last_download_reason`
(solo per l'esito `failed`). Il frontend mappa il codice a una stringa bilingue.
Usare un codice (non prosa) mantiene la coerenza con l'i18n IT/EN già in essere e
non lascia italiano grezzo in modalità EN.

### Codici motivo

| Codice                  | Quando                                                            |
|-------------------------|------------------------------------------------------------------|
| `transfer_failed`       | `classify_transfer_state` → `failed` (errored/cancelled/rejected)|
| `queue_timeout`         | Bloccato in coda oltre `QUEUE_PATIENCE`                           |
| `download_timeout`      | In trasferimento ma oltre `DOWNLOAD_TIMEOUT`                      |
| `enqueue_rejected`      | `enqueue_download` solleva eccezione                             |
| `file_missing`          | Transfer completato ma path non risolto su disco                 |
| `all_candidates_failed` | Cascata: tutti i candidati provati sono falliti (nessun code specifico dall'ultimo tentativo) |
| `error`                 | Eccezione imprevista in `_run`                                   |

### Modifiche backend — `backend/app/services/soulseek_download_job.py`

Cambia la firma delle funzioni interne per trasportare il codice; nessuna modifica
a modelli/schema/DB (il campo `last_download_reason` esiste già).

- `_wait_for_download(client, file) -> tuple[str, str | None]`
  - success → `("completed", None)`
  - stato slskd fallito → `("failed", "transfer_failed")`
  - coda oltre pazienza → `("failed", "queue_timeout")`
  - timeout globale → `("failed", "download_timeout")`
- `_download_candidate(client, download_dir, file) -> tuple[str | None, str | None]`
  - enqueue in errore → `(None, "enqueue_rejected")`
  - wait non completato → `(None, <code dal wait>)`
  - completato ma `_resolve_local_path` None → `(None, "file_missing")`
  - ok → `(path, None)`
- `_attempt_download(...) -> tuple[str, str | None, str | None]`
  - path None → `("failed", <code>, None)` (usa il code di `_download_candidate`)
  - resto invariato (`needs_review` durata, `downloaded`).
- `_process_item(...)`
  - `not_found` invariato (`("not_found", None, None)`).
  - candidato già scelto (discovery/singola) → ritorna l'esito di `_attempt_download`
    (con il suo code se `failed`).
  - cascata: memorizza il code dell'ultimo tentativo fallito; se tutti falliscono →
    `("failed", last_code or "all_candidates_failed", None)`.
- `_run(...)`: nel fallback `except Exception` per singola traccia, imposta
  `reason = "error"` prima di persistere (oggi resta `None`).

`SlskdError` (daemon giù/disconnesso) resta ri-sollevato e fa fallire l'intero
job con banner globale: **fuori scope** per il motivo per-traccia.

### Modifiche frontend — `frontend/app/downloads/page.tsx`

La riga del work-list oggi fa:

```tsx
{tr.last_download_reason && <div className="text-xs text-muted">{tr.last_download_reason}</div>}
```

Diventa: per l'esito `failed`, mostra la stringa tradotta dal codice, con fallback
generico se il codice è assente o sconosciuto; per gli altri esiti, mostra il
motivo grezzo come oggi.

```tsx
const detail = outcome === "failed"
  ? t.downloads.failedReason(tr.last_download_reason)   // gestisce null/sconosciuto → generico
  : tr.last_download_reason;
{detail && <div className="text-xs text-muted">{detail}</div>}
```

### i18n

Sezione `downloads` in `it.ts` e `en.ts`: funzione `failedReason(code: string | null)`
che mappa i codici a stringhe bilingui, con fallback generico.

- `transfer_failed` — IT «Trasferimento interrotto dall'utente remoto.» · EN "Transfer interrupted by the remote peer."
- `queue_timeout` — IT «Rimasto troppo a lungo in coda (utente lento o offline).» · EN "Stuck in the queue too long (peer slow or offline)."
- `download_timeout` — IT «Trasferimento troppo lento: superato il tempo massimo.» · EN "Transfer too slow: exceeded the time limit."
- `enqueue_rejected` — IT «Richiesta di download rifiutata dall'utente remoto.» · EN "Download request rejected by the remote peer."
- `file_missing` — IT «Download completato ma file non trovato su disco.» · EN "Download completed but the file wasn't found on disk."
- `all_candidates_failed` — IT «Nessun candidato ha completato il download.» · EN "No candidate completed the download."
- `error` — IT «Errore imprevisto durante il download.» · EN "Unexpected error during the download."
- fallback (null/sconosciuto) — IT «Download non riuscito.» · EN "Download failed."

### Test — `backend/tests/test_soulseek_download_job.py`

Estendere il fake client esistente per pilotare gli stati transfer e coprire:

- transfer che riporta stato fallito → `last_download_outcome == "failed"` e
  `last_download_reason == "transfer_failed"`.
- transfer che resta `Queued` oltre la pazienza → `"queue_timeout"`
  (con `QUEUE_PATIENCE`/`POLL_INTERVAL` ridotti via monkeypatch).
- `enqueue_download` che solleva → `"enqueue_rejected"`.
- cascata con tutti i candidati falliti → `"all_candidates_failed"`.
- happy path invariato (`downloaded`, reason `None`).

---

## Fuori scope (possibili follow-up)

- Traduzione IT/EN dei motivi in prosa già esistenti per `needs_review`
  («durata non corrisponde…», «confidenza sotto soglia…»): richiederebbe di
  strutturarli come codici anch'essi.
- Motivo per-traccia quando l'intero job fallisce per daemon slskd irraggiungibile
  (oggi surfacing solo via banner globale).
