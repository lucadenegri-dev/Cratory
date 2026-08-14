# Settings editor + "Condividi libreria" — design

Data: 2026-07-23 · Stato: approvato, in implementazione

## Obiettivo

Dalla pagina Settings di Cratory:

1. **Modificare a runtime** (senza riavviare il backend) i path/URL oggi bloccati in
   `backend/.env`: `library_root`, `archive_root`, `slskd_download_dir`, `slskd_url`.
2. Un flag **"Condividi libreria"** che fa condividere `library_root` sulla rete Soulseek
   tramite slskd.

Decisioni prese (brainstorming 2026-07-23):

- Persistenza degli override: **tabella DB, letta a runtime** (no riavvio).
- Meccanismo share: **Cratory edita `slskd.yml`** (slskd non permette di cambiare le share
  via API a runtime; si persistono solo nello YAML). Round-trip sicuro + rescan forzato.
- Campi editabili: Library root, Downloads dir, slskd URL, Archive root (+ `slskd_config_path`,
  necessario perché Cratory sappia quale file editare).

## Vincoli / contesto

- slskd 0.26.0 (installato). `PATCH /api/v0/options` accetta a runtime solo
  `soulseek.listenPort/listenIpAddress` (effimeri): le share NON sono runtime-mutabili via
  API → unica via persistente = lo YAML. `PUT /api/v0/shares` forza il rescan.
- `slskd.yml` è chmod 600 e contiene credenziali: va editato preservando commenti/formato
  (ruamel.yaml, non PyYAML) e i permessi.
- I 4 settings oggi sono letti in ~15 punti (`main.py`, `routers/{services,slskd,downloads,
  tracks}.py`, `integrations/slskd.py`, `services/{file_search,soulseek_download_job,
  pipeline,library_index_job}.py`). Molti call-site non hanno una `Session` DB a portata.

## Architettura

### 1. Persistenza + lettura runtime

- **Storage**: si riusa la tabella `AppState` esistente (il router settings già segue la
  convenzione "AppState, niente tabella dedicata"). Chiavi con prefisso `cfg.` (es.
  `cfg.library_root`, `cfg.share_library`). `app_state.py` guadagna `delete_state` e
  `get_states_by_prefix`.
- **Modulo `app/core/runtime_settings.py`**: cache in memoria degli override.
  - `_overrides: dict[str,str]` (solo valori non vuoti; "cancella" = riga eliminata).
  - `load(db)` — popola la cache dal DB; chiamato all'avvio in `main.py` dopo `ensure_schema`.
  - Accessor per ogni campo: `library_root()`, `archive_root()`, `slskd_download_dir()`,
    `slskd_url()`, `slskd_config_path()` → `_overrides.get(key)` con fallback a
    `getattr(settings, key)`; i path passano da `Path(...).expanduser()`.
  - `share_library() -> bool` (solo DB, default False; nessun env).
  - `apply(db, key, value)` / `clear(db, key)` — aggiornano DB **e** cache insieme.
  - Fonte per campo: `source(key) -> "db" | "env"` (per la UI).
- **Refactor call-site**: sostituire `settings.X` con `runtime_settings.X()` nei ~15 punti.
  `settings` resta la fonte dei default (`.env`) e di tutti gli altri campi non editabili.

### 2. API settings — `app/routers/settings.py`

- `GET /api/settings` → per ogni campo editabile: `value` (effettivo), `source`
  (`env`|`db`), `valid` + `detail` (path: esiste/è dir; downloads: scrivibile; url: formato).
  Più: `share_library` (bool), `slskd_reachable` (probe non bloccante), `slskd_config`
  (path effettivo + `exists`/`writable`).
- `PATCH /api/settings` → body con i campi da aggiornare. Valore non vuoto = override;
  valore vuoto/`null` = cancella override (torna a `.env`). Validazione prima di persistere;
  `422` su path inesistente/non-dir. Ritorna lo stesso shape di `GET`.
- Validazioni: library/archive = dir esistente (o vuoto per disattivare via .env);
  downloads = dir esistente; slskd_url = schema http(s) valido; slskd_config_path = file
  esistente e scrivibile **se** si vuole usare la share.

### 3. Share toggle — `app/services/slskd_shares.py`

- `set_library_share(enabled: bool)`:
  - path del config = `runtime_settings.slskd_config_path()`; libreria =
    `runtime_settings.library_root()`.
  - Precondizioni: config esiste e scrivibile; se `enabled`, `library_root` non vuoto.
  - Backup `slskd.yml.bak` (copia) → carica con `ruamel.yaml` (round-trip) → assicura
    `shares.directories`; **on**: aggiunge il path se assente; **off**: lo rimuove →
    scrittura **atomica** (temp nella stessa dir + `os.replace`) preservando **chmod 600** →
    forza rescan `PUT /api/v0/shares` via `SlskdClient` (best-effort).
  - Idempotente (aggiungere due volte non duplica; rimuovere l'assente è no-op).
  - Daemon giù: lo YAML resta scritto (persistente); il rescan fallisce in modo soft →
    esito riportato `applied_to_yaml=true, rescan=false`.
- `SlskdClient` guadagna `rescan_shares()` → `PUT /api/v0/shares` (verificato: la route
  ammette `GET, PUT, DELETE`).
- Persistenza del flag: `share_library` in `app_settings`. Quando cambia `library_root`
  mentre il flag è on, la share va ri-applicata (il router lo fa dopo il PATCH).

### 4. Frontend

- Card "Configurazione" in `app/settings/page.tsx`: campi editabili (Library root, Archive
  root, Downloads dir, slskd URL, slskd config path) con validità inline e badge "override
  .env" quando diverso dal default; bottone Salva (PATCH). Toggle **Condividi libreria** con
  avviso una-tantum sull'esposizione dei file alla rete.
- `lib/api/settings.ts` (`getSettings`, `updateSettings`, `setLibraryShare`) + types +
  i18n it/en.

### 5. Dipendenza

- `ruamel.yaml` aggiunto ai requirements backend (round-trip preserva commenti/ordine del
  config con credenziali; PyYAML li distruggerebbe).

## Testing

- `test_app_settings.py`: precedenza env/db, set/clear, `load` popola la cache.
- `test_settings_router.py`: GET shape + source; PATCH valida (422 su path errato), persiste,
  clear torna a env; share toggle chiama l'editor.
- `test_slskd_shares.py`: aggiunta/rimozione idempotente, backup creato, **round-trip
  preserva commenti**, chmod 600 mantenuto, daemon-giù → `rescan=false` senza eccezione.
- Frontend: unit sulla card (render, validazione, toggle) se il pattern esistente lo copre.

## Doc / regole

- `docs/API.md`: sezione `/api/settings`.
- `docs/ARCHITECTURE.md`: la condivisione via slskd entra in scope (opt-in).
- `CLAUDE.md`: la riga "slskd usato SOLO come downloader, non si sfrutta la condivisione"
  diventa un opt-in esplicito controllato dal flag.
- Memory `slskd-local-setup`: annotare il flag e il path del config editato.

## Fuori scope

- Editare altri campi `.env` (AI, Spotify, Discogs) dalla UI.
- Gestire share con filtri/alias/mask avanzati di slskd (solo directory piena).
- LaunchAgent per slskd (follow-up separato).
