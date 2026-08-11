# DjOrganizer — Chunk 1: Fondazione + Scanner

> Data: 2026-06-27 · Stato: design approvato, pronto per il plan.
> Spec del primo sub-progetto. Spec madre:
> [2026-06-27-djorganizer-design.md](2026-06-27-djorganizer-design.md).

## 1. Contesto e decomposizione

DjOrganizer (vedi spec madre) è troppo grande per un'unica spec/plan: 7 stage di
motore + 7 pagine + bridge + design system. Lo costruiamo **backend-first, bottom-up**,
spezzato in sub-progetti, ognuno col suo ciclo spec → plan → implementazione, nell'ordine
in cui i dati fluiscono:

| # | Sub-progetto | Contenuto | Rischio |
|---|---|---|---|
| **1** | **Fondazione + Scanner** | scaffold, `scan_root`/`audio_file`, `tagio`, `content_hash`, motore Scanner, job shell | basso |
| 2 | Inspector + Dedup | `issue` + `dup_group`, funzioni pure, nessuna mutazione FS | basso |
| 3 | Plan + Conflict | `plan`/`plan_op`, render template, validazione | basso |
| 4 | Apply + Undo | mutazione FS: ordine sicuro, quarantena, `undo_journal`, invariante apply→undo | alto |
| 5 | Bridge Cratory | client HTTP read-only `GET /api/tracks` | basso |
| 6 | Frontend | 7 pagine + design system copiato da Cratory | medio |

**Questa spec copre solo il chunk 1.** Gli stage successivi leggono ciò che il chunk 1
persiste; tre domande tecniche aperte della spec madre si distribuiscono: il
`content_hash` è chunk 1 (risolto qui); cross-volume move e invariante tag-level
appartengono al chunk 4.

L'app fratello **Cratory** (`~/Develop/DJProject01`) è il riferimento per layering,
convenzioni e pattern. DjOrganizer li ricalca; questa spec cita i pattern concreti da
riusare.

## 2. Scope del chunk 1

**Dentro:**

- Scaffold backend: FastAPI + SQLAlchemy 2.0 + SQLite, stile Cratory.
- Tabelle `scan_root` e `audio_file`.
- `integrations/tagio.py` — wrapper mutagen (lettura tag + info tecniche).
- `integrations/content_hash.py` — hash dello stream audio per-formato + fallback.
- `services/scanner.py` — il motore deterministico dello scan.
- `services/scan_job.py` — job shell async (thread + stato in memoria).
- `routers/sources.py` — CRUD radici + conteggi. `routers/scan.py` — avvio/stato job.
- Suite pytest con fixture audio reali.

**Fuori (chunk successivi):** Inspector/`issue`, Dedup, Plan, Conflict, Apply/Undo,
Bridge, tabella `settings`, frontend. Un file illeggibile **non** diventa ancora un
`issue` formale: viene registrato in modo leggero (vedi §6) e il chunk 2 lo promuoverà.

## 3. Decisioni chiave (con motivazione)

1. **Build strategy: backend-first, bottom-up.** Il motore deterministico è il cuore e
   la correttezza è prioritaria; la UI (a basso rischio, copiata da Cratory) arriva alla
   fine. Si parte dalla bedrock su cui legge tutto il resto.

2. **`content_hash` = pragmatico.** Hash dello **stream audio** (non dei tag), così un
   retag non cambia l'identità del file. Implementazione: stream-hash vero per **mp3** e
   **flac** (`hash_method=stream`); **full-file** hash come fallback per **m4a, wav,
   aiff** (`hash_method=file`), con la limitazione loggata. La *definizione* (hash dello
   stream) è corretta da subito — quindi il modello dati non andrà ri-scansionato quando
   si completerà la copertura. mp3/flac sono i formati dove il retag-instability
   morderebbe di più. Algoritmo: **BLAKE2b** (hashlib stdlib, veloce su file grandi),
   memorizzato come stringa esadecimale.

3. **Scan trigger: motore + job shell** (ricalca `enrichment_job.py` di Cratory). Il
   motore è una funzione con callback `on_progress`, testabile senza thread; il job è un
   thread con stato in memoria + lock (app mono-utente, un job alla volta). Scan non
   bloccante e template job riusabile da Apply (chunk 4) e dalla UI (chunk 6).

4. **Due campi extra su `audio_file`:** `hash_method` (onestà sulla retag-stabilità per
   riga) e `scan_error` (registra i fallimenti di lettura senza crashare).

5. **Riconciliazione file-spostato nel chunk 1.** È cheap (abbiamo già l'hash) e tiene
   il modello dati corretto fin da subito.

6. **Fixture audio reali nel repo.** Micro-file (~1s di silenzio, uno per formato) sotto
   `tests/fixtures/`. Rende affidabile il test di retag-stabilità (mutagen vero su file
   veri), che è il test più importante del chunk.

## 4. Struttura file (ricalca Cratory)

```text
backend/
  app/
    main.py                  # FastAPI app; ensure_schema() allo startup; include routers
    db.py                    # Base, engine, SessionLocal, ensure_schema, get_db (port da Cratory)
    core/
      config.py              # pydantic-settings: database_url, AUDIO_EXTS, ...
    models.py                # ScanRoot, AudioFile
    schemas.py               # Pydantic I/O validato
    integrations/
      tagio.py               # mutagen: leggi tag + info tecniche
      content_hash.py        # hash stream-audio per-formato + fallback full-file
    services/
      scanner.py             # IL MOTORE: scan(db, roots, on_progress) -> ScanSummary
      scan_job.py            # thread + stato in memoria (port da enrichment_job.py)
    routers/
      sources.py             # CRUD radici + conteggi
      scan.py                # POST /api/scan, GET /api/scan/status
  tests/
    fixtures/                # micro-file audio reali (mp3/flac/wav/aiff/m4a, ~1s)
    test_content_hash.py
    test_tagio.py
    test_scanner.py
    test_scan_job.py
    conftest.py              # fixture pytest condivise (db temp, root temp)
  requirements.txt           # fastapi, uvicorn, sqlalchemy, pydantic, pydantic-settings, mutagen, pytest, httpx
```

Moduli piccoli e a responsabilità singola: `tagio` legge tag, `content_hash` calcola
identità, `scanner` orchestra, `scan_job` fa da shell async, i router restano sottili.
Ognuno comprensibile e testabile in isolamento.

## 5. Data model (SQLite)

Pattern Cratory: **niente Alembic.** `Base.metadata.create_all()` + `ensure_schema()`
(con `ALTER TABLE` per colonne future). SQLAlchemy 2.0 (`Mapped`/`mapped_column`).
Timestamp via helper `utcnow()` timezone-aware.

**`scan_root`**

| Campo | Tipo | Note |
|---|---|---|
| `id` | int PK | |
| `path` | str, unique | radice assoluta normalizzata |
| `label` | str, nullable | etichetta leggibile |
| `last_scanned_at` | datetime, nullable | aggiornato a fine scan |

**`audio_file`** — output dello Scanner. Unique su `(root_id, path)`.

| Campo | Tipo | Origine |
|---|---|---|
| `id` | int PK | |
| `root_id` | FK → scan_root.id, indexed | |
| `path` | str, indexed | assoluto, normalizzato |
| `ext` | str | minuscolo, senza punto |
| `bitrate` | int, nullable | mutagen `.info` |
| `sample_rate` | int, nullable | mutagen `.info` |
| `channels` | int, nullable | mutagen `.info` |
| `duration_s` | float, nullable | mutagen `.info` |
| `size_bytes` | int | stat |
| `content_hash` | str, indexed, nullable | §7; null solo se i byte sono illeggibili |
| `hash_method` | str | `stream` \| `file` |
| `artist` | str, nullable | tag |
| `title` | str, nullable | tag |
| `album` | str, nullable | tag |
| `album_artist` | str, nullable | tag |
| `genre` | str, nullable | tag |
| `year` | int, nullable | tag (anno estratto da date) |
| `label` | str, nullable | tag |
| `track_no` | int, nullable | tag |
| `comment` | str, nullable | tag |
| `has_cover` | bool | presenza immagine embedded |
| `status` | str | `present` \| `missing` (`quarantined` arriva col chunk 4) |
| `scan_error` | str, nullable | messaggio se la lettura tag fallisce |
| `first_seen_at` | datetime | primo insert |
| `last_scanned_at` | datetime | ultimo scan che ha toccato la riga |

## 6. Integrazioni

### `tagio.py` (mutagen)

- `read_tags(path) -> TagData`: usa `mutagen.File(path, easy=True)` per i campi comuni
  (artist, title, album, genre, date→year, track_no, comment); fallback ai frame
  specifici per `album_artist`, `label` e per `has_cover` (APIC ID3 / PICTURE FLAC /
  `covr` atom MP4).
- `read_info(path) -> TechInfo`: bitrate, sample_rate, channels, duration_s da
  `mutagen.File(path).info`.
- Errore di parsing mutagen → solleva un'eccezione tipata `TagReadError`; lo Scanner la
  cattura e la registra in `scan_error` senza interrompersi.

### `content_hash.py`

`compute(path, ext) -> (hash_hex, method)` con **BLAKE2b**:

- **mp3** (`stream`): salta l'header ID3v2 (dimensione dai byte 6–9, synchsafe int) e gli
  eventuali tag in coda (ID3v1 "TAG" 128 byte, APEv2); hasha i frame MPEG rimanenti.
- **flac** (`stream`): dopo il marker `fLaC`, salta i metadata block (header 4 byte:
  flag last-block + tipo + lunghezza a 24 bit); hasha dal primo frame audio in poi.
- **m4a/aac, wav, aiff** (`file`): hash dell'intero file, `method='file'`, limitazione
  loggata a livello DEBUG/INFO.
- Byte illeggibili (permessi) → ritorna `None` come hash; lo Scanner lo registra in
  `scan_error` e prosegue.

## 7. Motore Scanner

`scan(db, roots, on_progress=None) -> ScanSummary`. Per ogni radice fa il walk del
filesystem; per ogni file con estensione in `AUDIO_EXTS`
(`.mp3 .flac .wav .aiff .aif .m4a .aac`, case-insensitive):

1. `size_bytes` da `os.stat`.
2. `content_hash` + `hash_method` via `content_hash.compute`.
3. Tag + info tecniche via `tagio` (se falliscono → `scan_error`, si prosegue).
4. **Upsert** su chiave `(root_id, path)`:
   - path nuovo → insert con `first_seen_at = last_scanned_at = utcnow()`, `status=present`.
   - path esistente → update di tag/info/hash/`size_bytes`, `last_scanned_at`,
     `status=present`.
5. `on_progress(processed, total, phase)` a ogni file (per il polling del job).

**Riconciliazione al ri-scan** (dopo aver processato tutte le radici):

- Righe della radice con path **non più presente** sul disco → `status='missing'` (la
  riga non viene cancellata: identità, storia e futuri riferimenti sopravvivono).
- Se un file **nuovo** ha `content_hash` uguale a una riga `missing` della stessa radice
  → trattato come **spostamento**: si aggiorna il `path` di quella riga invece di
  inserirne una nuova (preservando `id` e `first_seen_at`). Il match è sull'uguaglianza
  di `content_hash` (vale sia per `stream` sia per `file`); se più righe `missing`
  combaciano (hash ambiguo) si preferisce l'insert nuovo lasciando le altre `missing` —
  niente euristiche fragili.

`ScanSummary` (Pydantic): `roots` (lista dei `root_id` scansionati), `found`, `inserted`,
`updated`, `moved`, `missing`, `errors`, `started_at`, `finished_at`. Conteggi aggregati
su tutte le radici scansionate.

## 8. Job shell + endpoint

- `scan_job.py`: dict di stato sotto `threading.Lock` (`status` idle|running|done|error,
  `phase`, `processed`, `total`, `result`, `error`, timestamps). `start_job(root_ids)`
  avvia un thread che chiama `scan(...)` passando un `on_progress` che aggiorna lo stato;
  rifiuta l'avvio se un job è già `running`. `job_state()` ritorna lo snapshot. Port
  quasi verbatim da `enrichment_job.py`.
- `routers/scan.py`: `POST /api/scan` (body: root_ids opzionali; default tutte le
  radici) → avvia e ritorna subito; `GET /api/scan/status` → `job_state()`.
- `routers/sources.py`: `GET /api/sources` (lista radici + conteggio file e ultimo
  scan), `POST /api/sources` (aggiungi radice, valida che il path esista ed sia una
  cartella), `DELETE /api/sources/{id}`. Router sottili: logica nei services/repository.

## 9. Errori e sicurezza

- **Scanner resiliente:** errori di lettura/permessi per-file → `scan_error` sulla riga
  (+ hash se i byte sono leggibili), mai crash; il conteggio `errors` lo riporta.
- **Idempotenza:** ri-scan riconcilia (spostati via hash, mancanti → `missing`); nessun
  duplicato grazie all'unique `(root_id, path)`.
- **Nessuna mutazione dei file audio** in questo chunk: lo Scanner è sola lettura del FS
  + scrittura DB. Le mutazioni (retag/rename/move/delete) arrivano col chunk 4.
- **Path normalizzati e assoluti** per radici e file, per evitare doppioni di path.

## 10. Test (pytest, stile Cratory)

`conftest.py`: fixture per DB SQLite temporaneo (engine su file tmp + `ensure_schema`) e
per cartelle radice temporanee popolate copiando i fixture audio.

- **`test_content_hash.py`** (il più importante): copia un fixture, riscrive i tag con
  mutagen, verifica che l'hash **non cambi** per mp3 e flac (`stream`); documenta/asserisce
  il comportamento `file` per m4a/wav/aiff. Verifica due copie identiche → stesso hash.
- **`test_tagio.py`:** lettura corretta di tag/info sui fixture; file corrotto →
  `TagReadError` gestita.
- **`test_scanner.py`:** scan di cartelle temporanee → righe e `ScanSummary` attesi; file
  rotto → `scan_error` + scan completo; ri-scan idempotente; file spostato → riga
  riconciliata (stesso `id`/`first_seen_at`, nuovo path, `moved=1`); file rimosso →
  `status=missing`.
- **`test_scan_job.py`:** avvio → stato `running` → `done` con `result`; doppio avvio
  rifiutato mentre `running`.
- **Fixtures:** micro-file audio reali (~1s di silenzio), uno per formato MVP, committati
  sotto `tests/fixtures/`. Generati una volta (es. via ffmpeg/strumento esterno) e versionati.

Frontend: N/A in questo chunk.

## 11. Convenzioni (da rispettare, ereditate da Cratory)

- **Comandi backend:** `cd backend && source .venv/bin/activate`,
  `uvicorn app.main:app --reload --port 8000`, `python -m pytest tests`.
- **Motore deterministico**, nessuna AI nel percorso critico; **output validati Pydantic**.
- **Router sottili**, logica nei `services/`.
- SQLAlchemy 2.0 (`Mapped`/`mapped_column`), no Alembic (`create_all` + `ensure_schema`).
- Config via `pydantic-settings` in `core/config.py` (database_url di default sotto
  `backend/data/`, già git-ignored).

## 12. Definition of Done (chunk 1)

- `pytest tests` verde, incluso il test di retag-stabilità.
- Scan di una cartella reale popola `audio_file` correttamente; ri-scan idempotente.
- `POST /api/scan` + `GET /api/scan/status` funzionano end-to-end (avvio non bloccante +
  polling); `GET/POST/DELETE /api/sources` gestiscono le radici.
- Scaffold avviabile con uvicorn; `ensure_schema()` crea le tabelle allo startup.
