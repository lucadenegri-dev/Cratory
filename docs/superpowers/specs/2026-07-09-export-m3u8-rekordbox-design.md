# Export set M3U8 per Rekordbox

Data: 2026-07-09 · Backlog: ROADMAP item A1 ("Chiudere il flusso set → console")

## Obiettivo

Esportare un DJ set in un file `.m3u8` importabile in Rekordbox come playlist,
puntando ai file audio locali già in libreria (`Track.local_path`). Chiude il
flusso "set → console" senza scope aggiuntivo (beatgrid/cue restano fuori;
Rekordbox resta la fonte di BPM/key, non li scriviamo noi).

## Formato

M3U esteso, encoding UTF-8 (→ estensione `.m3u8`):

```
#EXTM3U
# <N> tracce senza file locale non incluse   ← solo se N > 0
#EXTINF:210,Artist — Title
/Users/luca/Music/…/track.aiff
```

- `#EXTINF:<durata_secondi>,<artist> — <title>` — durata intera in secondi,
  `-1` se sconosciuta. Separatore artist/title: ` — ` (coerente con gli altri export).
- La riga successiva a ogni `#EXTINF` è il `local_path` **assoluto** della traccia.
- Rekordbox ignora le righe `#` che non sono direttive: la riga di commento con
  il conteggio delle tracce saltate è informativa e innocua.

## Regole

- **Tracce senza `local_path`**: escluse dal file. Se ne sono state escluse N>0,
  una riga di commento `# N tracce senza file locale non incluse` va in testa
  (dopo `#EXTM3U`). Scelta: una playlist Rekordbox punta a file su disco, quindi
  una traccia senza file non può farne parte senza risultare "mancante".
- Ordine tracce = ordine del set (`SetlistTrack.position`).
- Nessuna scrittura su disco lato Cratory: si genera solo il testo del file.

## Implementazione

### Backend

- `backend/app/routers/sets.py` → `export()`: aggiungere il ramo `format=m3u8`.
  - Pattern del query param: `^(text|csv|markdown|m3u8)$`.
  - Media type risposta: `audio/x-mpegurl`.
  - Riusa `PlainTextResponse` come gli altri formati (test lo chiamano diretto).
- `docs/API.md`: aggiornare l'elenco formati dell'endpoint export.

### Frontend

- `frontend/lib/api.ts` → `exportSet()`: estendere il tipo `format` con `"m3u8"`.
- `frontend/app/sets/[id]/page.tsx`:
  - `doExport()`: accettare `"m3u8"`, mappare estensione `.m3u8`.
  - Aggiungere un quarto bottone export ("Rekordbox") accanto a TXT · CSV · MD.

## Test (TDD)

`backend/tests/test_set_texts.py` (o file dedicato):

1. **Happy path**: set con tracce aventi `local_path` → il body contiene `#EXTM3U`,
   una riga `#EXTINF:<sec>,<artist> — <title>` per traccia e il `local_path` assoluto
   sulla riga seguente, nell'ordine del set.
2. **Tracce senza file**: mix di tracce con/senza `local_path` → solo quelle con file
   sono incluse; presente la riga di commento con il conteggio corretto delle escluse.
3. **Durata assente** → `#EXTINF:-1,…`.

## Fuori scope

- Aggiunta di `local_path` al CSV esistente (item A1 secondario, rimandato).
- Export XML nativo Rekordbox (collection format).
