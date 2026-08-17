# Wizard di installazione e configurazione

Data: 2026-08-18. Stato: approvata a voce.

## Problema

Cratory oggi non ha nessun primo avvio. Chi installa l'app trova una dashboard
vuota e nessuna indicazione su cosa manchi: le chiavi API esistono **solo** come
campi di `backend/.env` (`spotify_client_id`, `ai_api_key`, `discogs_token`,
`acoustid_api_key` non passano da `runtime_settings`, quindi non c'è alcun canale
di scrittura a runtime), i binari di sistema (ffmpeg, fpcalc, yt-dlp, Essentia,
il demone slskd) non hanno nessun rilevamento centralizzato, e la documentazione
su come attivare le API presso i provider non esiste da nessuna parte —
`/api/services/status` si ferma a un link alla dashboard del provider.

La pagina `/settings` mostra lo stato dei servizi ma non permette di modificare
nulla che non sia un path o l'URL di slskd. Per configurare l'app bisogna
editare `.env` a mano e riavviare il backend.

Questo diventa bloccante in vista del packaging con **Tauri**: in un'app
impacchettata non esiste un `backend/.env` da editare a mano, e la
configurazione deve poter avvenire interamente dentro l'interfaccia.

## Decisioni chiave

- **Rotta dedicata `/setup` a schermo intero**, a passi, lanciata
  automaticamente al primo avvio e ri-apribile da Impostazioni. Non un modale,
  non una modalità della pagina Impostazioni: i contenuti didattici (istruzioni
  per provider, comandi shell, log di installazione) sono troppo lunghi per un
  overlay.
- **Le credenziali si scrivono nel DB**, estendendo `runtime_settings` con un
  gruppo segreti. Stesso schema già collaudato dei path: default `.env` →
  override in `AppState` → cache in memoria. Niente keychain (dipendenza in più,
  diversa per piattaforma, illeggibile da un backend headless), niente
  riscrittura di `.env` (richiederebbe un riavvio dentro il wizard).
- **Installazione ibrida**: il wizard installa automaticamente solo ciò che sta
  nel perimetro dell'app (il venv Python); per i componenti di sistema rileva e
  mostra il comando esatto, senza eseguirlo.
- **Verifica reale delle chiavi**: ogni credenziale salvata viene provata con una
  chiamata minima al provider, e il verdetto riporta l'errore vero del provider.
- **Ciclo di vita doppio**: primo avvio *e* strumento diagnostico permanente.
- **Confini espliciti per Tauri, zero codice Tauri.** Nessuna astrazione
  pluggable costruita su un solo caso reale: due servizi backend isolati (probe e
  installer) e due punti di sostituzione dichiarati.

## Ambito

Dentro:

- rilevamento dei componenti esterni e installazione di quelli sicuri;
- configurazione e verifica delle chiavi API (Spotify, Anthropic, Discogs,
  AcoustID) e di slskd;
- scelta della libreria su disco e prima indicizzazione;
- didattica su come attivare le API presso ogni provider.

Fuori:

- **Rekordbox** (import `collection.xml`): è un'operazione ricorrente, non di
  setup, e resta dov'è;
- installazione automatica di ffmpeg, fpcalc, slskd;
- keychain di sistema, aggiornamento automatico dei componenti, codice Tauri,
  multi-utente.

Nessuna dipendenza nuova, né backend né frontend: `shutil` e `subprocess` sono
stdlib, tutto il resto esiste già.

---

## 1. Credenziali scrivibili a runtime

### Modello

`backend/app/core/runtime_settings.py` guadagna un secondo gruppo di chiavi
accanto a `ENV_BACKED_KEYS`:

```python
SECRET_KEYS = ("spotify_client_id", "spotify_client_secret", "ai_api_key",
               "ai_model", "discogs_token", "acoustid_api_key", "slskd_api_key")
```

`slskd_api_key` entra qui per correggere un'asimmetria esistente: `slskd_url` e
`slskd_download_dir` sono già overridabili, la sua API key no.

Nota: `ENV_BACKED_KEYS`, oggi, non è letto da nessuno — è una costante
decorativa (l'elenco vero dei campi editabili è `_FIELD_KEYS` in
`routers/settings.py`). `SECRET_KEYS` non deve nascere allo stesso modo: deve
essere la **sola** sorgente da cui il router costruisce il blocco `secrets` e
valida il `PATCH`, con un test che lo dimostri (aggiungere una chiave alla
tupla deve comparire nella risposta senza toccare il router). Nella stessa
occasione o si dà un consumatore a `ENV_BACKED_KEYS` o si cancella.

Semantica identica ai path: `_resolved()` (override in cache se non vuoto,
altrimenti il default `.env`), `apply`/`clear` scrivono DB e cache insieme.
`ai_model` non è un segreto ma segue lo stesso canale perché è configurazione
utente della stessa scheda; viene esposto in chiaro.

Restano env-only, perché non sono configurazione da wizard: `ai_effort`,
`ai_thinking`, `ai_timeout_seconds`, `database_url`, `frontend_origin`,
`audio_exts` e le soglie di Organize.

### Call-site

18 letture dirette passano da `settings.X` a `runtime_settings.X()`:

| file | occorrenze |
|---|---|
| `integrations/spotify.py` | 3 (`_credentials`) |
| `integrations/llm.py` | 3 (`AnthropicLLMClient.__init__`, `llm_configured`) |
| `integrations/discogs.py` | 1 |
| `integrations/slskd.py` | 1 |
| `routers/services.py` | 3 |
| `routers/spotify.py` | 1 |
| `organize/integrations/acoustid.py` | 3 |
| `organize/integrations/discogs_meta.py` | 1 |
| `organize/services/ai_tags.py` | 3 |

Nessuno di questi client è cachato a livello di modulo — `AnthropicLLMClient`,
`SpotifyWebClient`, `DiscogsClient`, `AcoustIDClient` si costruiscono per
chiamata — quindi **cambiare una chiave ha effetto senza riavvio**, senza
bisogno di invalidare nulla. È la proprietà che rende sensato un wizard che
salva e prova nello stesso gesto.

### API

`GET /api/settings/config` guadagna un blocco `secrets` con una forma **diversa**
da `FieldState`, perché il valore non deve uscire:

```python
class SecretState(BaseModel):
    configured: bool
    source: Literal["env", "db"]
    hint: str | None      # ultime 4 cifre, es. "••••a3f9"; None se non configurata
```

`ConfigPatch` accetta gli stessi campi in scrittura; stringa vuota = azzera
l'override e torna al default `.env` (come già fanno i path).

`spotify_redirect_uri` viene esposto **in sola lettura** dentro la risposta: è
il valore che l'utente deve incollare nella dashboard Spotify, e va mostrato
sempre vero anche se la porta cambia.

Non nasce nessun endpoint di scrittura nuovo: la configurazione ha un solo
scrittore, `PATCH /api/settings/config`.

---

## 2. Probe di sistema

Nuovo `backend/app/services/system_probe.py`, con un registry dichiarativo — una
voce per componente:

```python
@dataclass(frozen=True)
class Component:
    key: str                       # "ffmpeg", "fpcalc", "yt-dlp", "essentia", "slskd"
    kind: Literal["system", "venv", "daemon"]
    provided_by: Literal["system", "venv", "bundle"]
    severity: Literal["required", "optional"]
    detect: Callable[[], ProbeResult]
    auto_installable: bool
    recipes: dict[str, list[str]]  # piattaforma -> argv
    unlocks: tuple[str, ...]       # chiavi di feature, non prosa
```

Componenti e rilevamento:

| key | kind | severity | rilevamento |
|---|---|---|---|
| `ffmpeg` | system | **required** | `which` + `-version` |
| `fpcalc` | system | optional | `which` (con override `FPCALC` già letto da `organize/integrations/acoustid.py`) + `-version` |
| `yt-dlp` | venv | optional | `which` + `--version` |
| `essentia` | venv | optional | import in **subprocess** (è pesante e ha già un worker separato: non va caricata nel processo API) |
| `slskd` | daemon | optional | ping HTTP su `runtime_settings.slskd_url()` |

`ffmpeg` è l'unico `required`: senza, saltano l'`audio_hash` che dà identità ai
file, la fingerprint Shazam e l'estrazione MP3 di yt-dlp.

**Il registry non contiene prosa.** Solo chiavi: descrizioni, istruzioni e testi
di `unlocks` vivono nei dizionari i18n del frontend, come già fa `servicesMeta`.

### Il gancio Tauri

La risoluzione di ogni binario guarda **prima** una directory da variabile
d'ambiente `CRATORY_BIN_DIR`, poi il `PATH`:

```python
def resolve_binary(name: str) -> str | None:
    bundled = os.environ.get("CRATORY_BIN_DIR")
    if bundled and (p := Path(bundled) / name).exists():
        return str(p)
    return shutil.which(name)
```

Una riga oggi. Quando arriverà Tauri con i binari impacchettati, basterà che il
processo sidecar parta con quella variabile impostata: la UI del wizard e il
resto del backend non cambiano.

`GET /api/setup/probe` restituisce l'elenco degli stati, con cache TTL ~10s per
non lanciare `subprocess` a ogni render della pagina.

---

## 3. Installer

`POST /api/setup/install/{key}` (202) + `GET /api/setup/install/status`: job
singolo in-flight, log bufferizzato riga per riga, polling a 1s dal frontend.
Riusa `services/job_spawn.py` come gli altri job dell'app.

Regole non negoziabili:

1. **Solo ricette dal registry.** `argv` come lista, `shell=False`, nessuna
   interpolazione di input utente in nessun punto. Chiave sconosciuta → `400`.
2. **`auto_installable` solo per il venv**: `yt-dlp` ed `essentia`.
   `ffmpeg`, `fpcalc`, `slskd` non sono mai automatici — comando copiabile e
   link alla documentazione.
3. **Essentia si installa con `--only-binary=:all:`**:

   ```
   [sys.executable, "-m", "pip", "install", "--only-binary=:all:",
    "essentia==2.1b6.dev1389"]
   ```

   Il pin ha wheel solo per cp311/macOS-arm64. Senza quel flag, su ogni altra
   piattaforma pip parte a compilare da sorgente e il wizard resta appeso venti
   minuti su un log illeggibile. Con il flag fallisce in pochi secondi con un
   messaggio comprensibile, e la UI degrada a "installazione manuale" mostrando
   la ricetta.

L'esecuzione passa tutta da una funzione sola:

```python
def run_recipe(argv: list[str]) -> Iterator[str]:
    """Esegue una ricetta del registry e produce le righe di log.
    UNICO punto di esecuzione di processi esterni del wizard: in Tauri
    è questo che verrà sostituito, non i chiamanti."""
```

---

## 4. Verifica delle credenziali

`POST /api/setup/test/{service}` → `{ok: bool, detail: str}`. `detail` riporta
**l'errore vero del provider**, non un messaggio nostro: è la differenza tra un
wizard che diagnostica e uno che dice "qualcosa è andato storto".

| servizio | prova |
|---|---|
| `spotify` | token client-credentials. Non tocca l'OAuth utente, che è un passo a sé |
| `anthropic` | chiamata minima con `max_tokens: 1` |
| `discogs` | `/oauth/identity` col token; senza token, una search che conferma il funzionamento a rate ridotto |
| `acoustid` | lookup minima: "invalid api key" = rosso, altri esiti = verde. Verde **solo se** anche `fpcalc` risulta presente al probe: servono entrambi |
| `slskd` | riusa `POST /api/slskd/connect`, già esistente |

Nuovo router `backend/app/routers/setup.py`, prefisso `/api/setup`, tag
`setup`: `GET /state`, `PUT /state`, `GET /probe`, `POST /install/{key}`,
`GET /install/status`, `POST /test/{service}`. Il router è HTTP-only: probe,
installer e test vivono in `services/`.

---

## 5. La rotta `/setup`

Sei passi, ciascuno saltabile, nessuno bloccante:

| # | Passo | Contenuto |
|---|---|---|
| 0 | Benvenuto | Lingua (IT/EN) e cosa sta per succedere. Unico passo senza stato da salvare |
| 1 | Prerequisiti | La lista del probe. Per ognuno: stato, versione trovata, **cosa sblocca**, e o il bottone Installa o il comando copiabile |
| 2 | Libreria | `library_root` col picker Finder nativo esistente (`POST /api/files/pick`), `archive_root` opzionale, poi prima indicizzazione con avanzamento in-place (`POST /api/library/index` + `GET /api/library/index/status`) |
| 3 | Servizi | Una scheda per Spotify, Anthropic, Discogs, AcoustID: guida numerata → campi → Prova → verdetto. Spotify chiude col bottone OAuth "Connetti account" (`GET /api/spotify/login`), che è cosa diversa dall'avere le chiavi |
| 4 | slskd | URL, API key, cartella download, verifica del demone. Se non risponde, istruzioni per installarlo e avviarlo |
| 5 | Riepilogo | Cosa è attivo e cosa no, con le feature ancora spente e il perché. Da qui si entra nell'app |

La pagina è a schermo intero, senza la nav laterale: non usa `PageLayout`.

### Ingresso automatico

Un componente client `SetupGate` montato nel layout legge `/api/setup/state` una
volta e reindirizza a `/setup` se `completed` è falso e il pathname non è già
`/setup`. Reindirizza **solo su risposta riuscita**: se il backend è giù, non
deve mandare l'utente in un wizard che non può funzionare — quel caso ha già il
suo messaggio in dashboard (`t.dashboard.backendDown`).

Lo stato vive in `AppState` con chiave `setup.completed`, accanto a `language` e
`last_index_at`. Il valore si scrive quando l'utente completa **o** salta il
wizard: in entrambi i casi non deve ripresentarsi da solo.

Next 16 ha comportamenti propri su routing e client components: leggere
`frontend/CLAUDE.md` prima di scrivere il gate.

---

## 6. Nessun doppione con Impostazioni

Tre componenti in `frontend/components/setup/`, scritti una volta e usati da
entrambe le pagine:

- **`CredentialField`** — input mascherato, salva, prova, verdetto. L'input
  **non si pre-riempie mai**: se la chiave è configurata mostra
  `configurata ••••a3f9` e un link "sostituisci".
- **`ServiceGuide`** — guida numerata, link al provider, valori da copiare.
- **`ComponentRow`** — la riga del probe (stato, versione, azione).

In `/settings` le righe di `ServicesList` diventano espandibili e dentro
montano esattamente questi. Così cambiare la chiave Spotify non richiede di
rifare il wizard, e non esistono due implementazioni del campo-chiave che
divergono nel tempo. Impostazioni guadagna inoltre un bottone "Riapri la
configurazione guidata".

---

## 7. La didattica

È il contenuto che oggi non esiste da nessuna parte, ed è il valore vero del
wizard. Tutto nei dizionari i18n, **in entrambe le lingue**:

- **Spotify** — dashboard → Create app → **Redirect URI esattamente**
  `http://127.0.0.1:8000/api/spotify/callback`, con bottone copia e la nota che
  Spotify rifiuta `localhost` e accetta solo l'IP di loopback o HTTPS. È
  l'errore n.1 di quel setup. Il valore arriva dal backend, non è hardcodato nel
  dizionario.
- **Anthropic** — console → API keys → serve credito sull'account. Modello di
  default (`claude-opus-4-8`) e come cambiarlo.
- **Discogs** — settings/developers → *personal access token*, non OAuth. Detto
  chiaro che il dig funziona anche senza: il token alza il rate limit e aggiunge
  le copertine.
- **AcoustID** — registrazione dell'applicazione → API key, **più** il binario
  `fpcalc`, con rimando al passo 1 che lo rileva. Servono entrambi: senza dirlo,
  l'utente mette la chiave e resta col bottone grigio.
- **slskd** — non è un binario one-shot ma un demone separato: installazione,
  `slskd.yml`, API key opzionale, cartella download. Il flag "Condividi
  libreria" resta dov'è, in Impostazioni.

Regola di progetto rispettata: nessun testo user-facing nasce nel backend: il
registry del probe e il router `setup` restituiscono solo chiavi.

---

## 8. Verifica

Backend:

- **probe** — `which` e `subprocess` falsificati: componente presente, assente,
  versione illeggibile. E che `CRATORY_BIN_DIR` **vinca** sul `PATH`: è il gancio
  Tauri, va protetto da subito.
- **installer** — chiave fuori registry → `400`; nessuna ricetta usa
  `shell=True`; e un test di regressione che asserisce `--only-binary=:all:`
  nella ricetta Essentia, altrimenti il flag sparisce al primo refactor e il
  wizard torna a compilare da sorgente.
- **segreti** — asserzione sul **JSON serializzato** di
  `GET /api/settings/config`: il valore in chiaro non deve comparirci, mai (non
  basta controllare il campo, che potrebbe essere aggiunto altrove). Più:
  precedenza override → env, e azzeramento con stringa vuota che torna al `.env`.
- **test credenziali** — `httpx.MockTransport`: un `401` dal provider produce
  `{ok: false}` col detail del provider.

Frontend:

- **unit** — gating dei passi e stato "saltato"; `CredentialField` non
  pre-riempie l'input quando `configured` è vero.
- **e2e** — su DB vuoto `/setup` si apre da solo; si salta; dopo non reindirizza
  più.

I test si scrivono prima dell'implementazione (TDD), passo per passo.

---

## 9. Ordine di implementazione

1. `runtime_settings` + segreti, migrazione dei 18 call-site, `SecretState` in
   `/api/settings/config`.
2. `system_probe` + registry + `GET /api/setup/probe`.
3. Installer + `run_recipe` + endpoint di installazione.
4. Endpoint di test delle credenziali.
5. Componenti condivisi (`CredentialField`, `ServiceGuide`, `ComponentRow`) e
   dizionari i18n.
6. Rotta `/setup`, i sei passi, `SetupGate`.
7. Integrazione in `/settings` (righe espandibili, bottone di riapertura).
8. Documentazione: `docs/API.md` (router `setup` e blocco `secrets`),
   `docs/ARCHITECTURE.md` (probe e installer nei layer, il confine Tauri),
   `docs/ROADMAP.md`, `README.md` (il setup non è più "edita `.env`").

Ogni passo da 1 a 4 è indipendente e verificabile da solo; dal 5 in poi la UI
consuma quello che i primi quattro espongono.
