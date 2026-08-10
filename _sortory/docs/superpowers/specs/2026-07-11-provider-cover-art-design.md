# Provider Cover Art — Design

**Data:** 2026-07-11
**Stato:** approvato (brainstorming)

## Obiettivo

Durante l'arricchimento da provider, recuperare anche la **copertina** (cover art) del
brano e **embeddarla nei tag del file** (APIC / `covr` / FLAC pictures), passando per il
solito flusso rivedibile **ISSUES → PLAN → apply** con write per-op.

Oggi l'arricchimento (MusicBrainz → Discogs, fingerprint AcoustID, Haiku) recupera solo
testo (artist, title, album, label, genre, year). Le immagini non sono mai scaricate:
esiste solo `AudioFile.has_cover` come booleano usato per il dedup, che non arriva
nemmeno alla UI.

## Decisioni (dal brainstorming)

1. **Destinazione:** embed nei tag del file (no `cover.jpg` su disco, no solo-anteprima).
2. **Ambito:** solo file **senza copertina** (`has_cover = false`). Non si sostituiscono
   cover esistenti.
3. **Fonte + soglia:** **Cover Art Archive** (via MBID) sui match **"alta"** +
   **Discogs** `cover_image` come **fallback** sui match **"testuali"**. CAA ha precedenza.
   Nessuna proposta su match sotto soglia.
4. **Review:** **thumbnail inline** nella ISSUES table (~44px), click per ingrandire.
   Accetta/ignora come ogni altro fix.
5. **Timing byte:** **thumb cache alla proposta, full-res all'apply.** Alla proposta si
   scarica e cacha solo la thumbnail (pochi KB, anteprima stabile); la full-res si scarica
   solo per le cover accettate, al momento dell'apply. Se il link è morto in quel momento,
   l'op si **skippa** (pattern per-op esistente).

## Architettura

### Fonte e matching — `backend/app/integrations/cover_art.py` (nuovo)

Due lookup + un orchestratore che rispecchia `text_providers.lookup_with_conf`:

- **Cover Art Archive**: keyed sul **release-MBID**. Restituisce cover solo su match
  confidenza `"high"`. Endpoint `https://coverartarchive.org/release/{mbid}/front`
  (e `/front-250` per la thumb).
- **Discogs**: `cover_image` / `thumb` dalla risposta search già usata in
  `discogs_meta.py`. Usato solo come fallback quando CAA non trova nulla, su match `"text"`.
- **Orchestratore**: `lookup_cover(track) -> CoverResult | None` con
  `{thumb_bytes, full_url, source, confidence}`. CAA precede Discogs.

**Nota MBID:** CAA è indicizzato per **release-MBID**. Il valore in `AudioFile.mbid` va
verificato (recording vs release). Se è un recording MBID, si aggiunge un passo
`recording → release` via MusicBrainz (già interrogato). Da confermare in implementazione
leggendo cosa scrive `musicbrainz.py` in `mbid`.

### Modello dati e staging

Nuovo tipo di issue **`missing_cover`** — una riga per file con `has_cover = false`.
La proposta vive in `Issue.suggested_fix_json`, come gli altri fix:

```json
{
  "field": "cover",
  "source": "caa" | "discogs",
  "confidence": "high" | "text",
  "full_url": "https://…",
  "thumb_ref": "cover_cache/<file_id>.jpg"
}
```

- La **thumbnail** cachata alla proposta va su disco in `<data_dir>/cover_cache/<file_id>.jpg`
  (non nel DB → DB leggero, servibile come file statico).
- **Nessuna nuova colonna** in `AudioFile`. `has_cover` diventa `true` dopo l'apply
  (aggiornato dalla scansione o esplicitamente in fase di apply).

### Backend — flusso ed endpoint

Si **estende** il flusso provider esistente, non se ne crea uno nuovo.

- **Proposta** — `POST /api/issues/provider-suggest` guadagna un flag per cercare anche la
  cover (default on). Per ogni file `has_cover = false`, dopo aver risolto testo/MBID:
  chiama `lookup_cover()`, scarica la **thumb**, la salva in `cover_cache/`, crea/aggiorna
  un issue `missing_cover` con il `suggested_fix_json` sopra. Riusa throttle/breaker già
  presenti sui provider.
- **Servire la thumb** — `GET /api/issues/cover-thumb/{file_id}` restituisce il jpg cachato
  per l'anteprima (o static mount della cache dir).
- **Apply** — un `PlanOp` di tipo cover: al momento dell'apply scarica `full_url` e la
  embedda con una nuova funzione in `tagio.py` — `write_cover(path, jpg_bytes)` che scrive
  APIC (ID3), `covr` (MP4), `pictures` (FLAC/AIFF). Coerente con `write_tags`. Se il
  download fallisce → op **skippata**, non fa fallire il batch.
- **Undo** — lo stato "prior" è "nessuna immagine": l'undo **rimuove** la cover embeddata,
  coerente con `UndoJournal`.

### Frontend

- **`issues-table.tsx`**: righe `missing_cover` con **thumbnail inline** (~44px) da
  `/api/issues/cover-thumb/{file_id}`, accanto al `ConfBadge` "alta"/"testuale". Click →
  ingrandimento (lightbox semplice). Accetta ✓ / ignora ✕ come gli altri fix.
- **Toolbar ISSUES**: le cover sono incluse automaticamente nella ricerca provider (solo
  file senza copertina). Checkbox opzionale "cerca anche copertine", default **on**.
- **`plan-ops.tsx`**: l'op cover appare con una miniatura per riconoscerla (no secondo
  checkpoint pesante — la review vera è in ISSUES).
- **`lib/api.ts`**: `providerSuggest` guadagna il flag cover; helper per l'URL della thumb;
  `ProviderSuggestResult` riporta anche il conteggio cover trovate.

## Testing

Backend con `backend/.venv/bin/python` (3.11), HTTP dei provider mockato:

- `cover_art.lookup_cover`: CAA hit, fallback Discogs, nessun match.
- `tagio.write_cover` per FLAC / MP3 / M4A / AIFF: round-trip embed → `_detect_cover` = true.
- Flusso propose → apply → undo (undo rimuove la cover).
- Skip op quando il download full-res fallisce (batch non fallisce).

## Fuori scope (YAGNI)

- Sostituzione di cover già esistenti.
- Salvataggio `cover.jpg` su disco.
- Selezione manuale tra più cover candidate.
- Upscaling / ritocco immagini.
