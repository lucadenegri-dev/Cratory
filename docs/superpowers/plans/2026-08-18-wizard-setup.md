# Wizard di installazione e configurazione — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dare a Cratory un primo avvio guidato che rileva i componenti esterni, installa quelli sicuri, configura e verifica le chiavi API e spiega come attivarle presso ogni provider.

**Architecture:** Le credenziali diventano scrivibili a runtime estendendo `runtime_settings` (default `.env` → override in `AppState` → cache in memoria), esposte in sola lettura mascherata da `/api/settings/config`. Un nuovo router `/api/setup` aggiunge tre servizi indipendenti: un **probe** che rileva i componenti esterni da un registry dichiarativo, un **installer** che esegue solo ricette del registry attraverso un unico punto di esecuzione, e i **test** delle credenziali che riportano l'errore vero del provider. Il frontend monta una rotta `/setup` a schermo intero a sei passi, costruita su componenti condivisi che `/settings` riusa.

**Tech Stack:** Python 3.11 + FastAPI + SQLAlchemy/SQLite (backend), Next.js 16 App Router + React 19 + Tailwind 4 (frontend), pytest + vitest + Playwright (test). **Nessuna dipendenza nuova**, né backend né frontend.

**Spec:** `docs/superpowers/specs/2026-08-18-wizard-setup-design.md`

## Global Constraints

- **Nessuna dipendenza nuova.** `shutil`, `subprocess`, `httpx` (già presente) e stdlib. Non aggiungere righe a `backend/requirements.txt` né a `frontend/package.json`.
- **I segreti non escono mai dal backend.** Nessuna risposta HTTP può contenere il valore in chiaro di una chiave API. Solo `configured: bool`, `source: "env"|"db"` e `hint` (ultime 4 cifre).
- **Nessun testo user-facing nasce nel backend.** Il registry del probe e il router `setup` restituiscono solo chiavi; ogni stringa mostrata all'utente vive nei dizionari i18n del frontend, **in entrambe le lingue**. `frontend/lib/i18n/en.ts` è la fonte di verità dei tipi (`export type Dictionary = typeof en`): va modificato **per primo**, poi `it.ts` si adegua o TypeScript fallisce.
- **BPM/key restano fuori.** Il wizard non tocca Rekordbox né l'analisi Essentia se non per rilevare/installare il pacchetto.
- **Ricette di installazione:** `argv` come lista, `shell=False`, mai interpolazione di input utente. La ricetta Essentia deve contenere `--only-binary=:all:` ed essere pinnata a `essentia==2.1b6.dev1389`.
- **Next 16 non è il Next che conosci.** Prima di scrivere codice di routing o layout leggere la guida pertinente in `frontend/node_modules/next/dist/docs/` (vedi `frontend/CLAUDE.md`).
- **Commit:** un commit per task, messaggi in italiano, prefisso convenzionale (`feat(setup):`, `refactor(config):`, `docs(setup):`). **Mai** aggiungere trailer `Co-Authored-By`.
- **Comandi di test in questo worktree** (il worktree non ha un proprio `.venv`: si usa l'interprete del checkout principale con cwd sul backend del worktree):
  ```bash
  cd backend && /Users/lucadenegri/Develop/DJProject01/backend/.venv/bin/python -m pytest tests -q
  ```
  Frontend (il worktree deve avere un `npm install` reale, non un symlink a `node_modules`):
  ```bash
  cd frontend && npm run test:unit
  ```

---

## File Structure

**Backend — creati**

| File | Responsabilità |
|---|---|
| `backend/app/routers/setup.py` | Solo HTTP: stato del wizard, probe, install, test. Nessuna logica |
| `backend/app/services/system_probe.py` | Registry dichiarativo dei componenti + rilevamento + cache TTL |
| `backend/app/services/component_installer.py` | Job di installazione a istanza singola + `run_recipe` (unico punto di esecuzione processi) |
| `backend/app/services/credential_tests.py` | Una `check_*` per provider, ritorna `(ok, detail)` col messaggio del provider |
| `backend/tests/test_runtime_secrets.py` | Precedenza override/env dei segreti |
| `backend/tests/test_secrets_call_sites.py` | Ogni integrazione legge l'override, non `settings` |
| `backend/tests/test_config_secrets.py` | Mascheramento nella risposta HTTP, PATCH, azzeramento |
| `backend/tests/test_setup_state.py` | Flag `setup.completed` |
| `backend/tests/test_system_probe.py` | Rilevamento, `CRATORY_BIN_DIR`, cache |
| `backend/tests/test_component_installer.py` | Whitelist, `shell=False`, `--only-binary`, esiti |
| `backend/tests/test_credential_tests.py` | Esiti con `httpx.MockTransport` |

**Backend — modificati**

| File | Modifica |
|---|---|
| `backend/app/core/runtime_settings.py` | `SECRET_KEYS`, accessor per chiave, `ai_model` in `ENV_BACKED_KEYS` |
| `backend/app/routers/settings.py` | Blocco `secrets` + `spotify_redirect_uri` in `ConfigSettings`, campi nel `PATCH`, `_FIELD_KEYS` sostituito da `rs.ENV_BACKED_KEYS` |
| `backend/app/integrations/spotify.py`, `llm.py`, `discogs.py`, `slskd.py` | `settings.X` → `runtime_settings.X()` |
| `backend/app/organize/integrations/acoustid.py`, `discogs_meta.py`, `backend/app/organize/services/ai_tags.py` | idem |
| `backend/app/routers/services.py`, `backend/app/routers/spotify.py` | idem |
| `backend/app/main.py` | `include_router(setup.router)` |

**Frontend — creati**

| File | Responsabilità |
|---|---|
| `frontend/lib/api/setup.ts` | Client HTTP del wizard + tipi |
| `frontend/lib/setup-services.ts` | Mappa servizio → chiavi segrete richieste (dati, niente JSX) |
| `frontend/components/setup/credential-field.tsx` | Un campo segreto: input mascherato, salva |
| `frontend/components/setup/path-field.tsx` | Campo percorso/URL con dialog nativo. Condiviso fra passo libreria e passo slskd |
| `frontend/components/setup/service-guide.tsx` | Guida numerata + link + valore copiabile |
| `frontend/components/setup/service-card.tsx` | Guida + campi + Prova. **Usato sia da `/setup` sia da `/settings`** |
| `frontend/components/setup/component-row.tsx` | Riga del probe: stato, versione, installa o comando |
| `frontend/components/setup/setup-gate.tsx` | Redirect al primo avvio |
| `frontend/components/shell-switch.tsx` | `/setup` senza nav laterale |
| `frontend/app/setup/page.tsx` | Macchina a stati dei sei passi |
| `frontend/components/setup/steps/*.tsx` | Un file per passo (welcome, prerequisites, library, services, slskd, summary) |
| `frontend/tests/credential-field.test.tsx` | Il campo chiave non pre-riempie mai |
| `frontend/tests/setup-gate.test.tsx` | Redirect del primo avvio |
| `frontend/e2e/setup.spec.ts` | Il wizard renderizza e si salta |
| `frontend/e2e/global-setup.ts` | Marca il wizard completato prima della suite |

**Due vincoli del frontend da tenere presenti in tutti i task frontend:**

1. `vitest.config.ts` ha `include: ["tests/**/*.test.{ts,tsx}"]`: i test unitari vanno **solo** in `frontend/tests/`, non accanto al componente. Un test messo altrove non viene eseguito e sembra verde.
2. `JobsProvider` — che fa il polling globale dei job, indicizzazione compresa — è montato dentro `EditorialShell`, che il wizard **scavalca**. Su `/setup` non esiste: ogni polling di cui il wizard ha bisogno va fatto dal passo stesso.

**Frontend — modificati**

| File | Modifica |
|---|---|
| `frontend/lib/api.ts` | `export * from "./api/setup"` |
| `frontend/lib/i18n/en.ts`, `it.ts` | Sezione `setup` completa |
| `frontend/app/layout.tsx` | `ShellSwitch` + `SetupGate` |
| `frontend/components/settings/services-list.tsx` | Righe espandibili che montano `ServiceCard` |
| `frontend/app/settings/page.tsx` | Bottone "Riapri la configurazione guidata" |
| `frontend/playwright.config.ts` | `globalSetup` |
| `frontend/e2e/smoke.spec.ts` | `/setup` nell'elenco rotte |

---

## Task 1: Segreti in `runtime_settings`

**Files:**
- Modify: `backend/app/core/runtime_settings.py`
- Test: `backend/tests/test_runtime_secrets.py`

**Interfaces:**
- Consumes: `_resolved`, `apply`, `clear`, `source` già esistenti nel modulo.
- Produces: `SECRET_KEYS: tuple[str, ...]`; accessor senza argomenti `spotify_client_id()`, `spotify_client_secret()`, `ai_api_key()`, `discogs_token()`, `acoustid_api_key()`, `slskd_api_key()`, `ai_model()`, tutti `-> str`; `secret(key: str) -> str`.

**Nota di progetto (scostamento consapevole dallo spec §1):** lo spec elencava `ai_model` fra i `SECRET_KEYS` precisando che va esposto in chiaro. Qui `ai_model` entra invece in `ENV_BACKED_KEYS` (il gruppo dei campi in chiaro), così `SECRET_KEYS` non ha eccezioni e la funzione di mascheramento non ha casi speciali. Risultato identico per l'utente.

- [ ] **Step 1: Scrivere il test che fallisce**

Creare `backend/tests/test_runtime_secrets.py`:

```python
"""Le chiavi API devono essere scrivibili a runtime con la stessa semantica dei
path: override DB sopra il default .env, vuoto = torna al default."""
import pytest

from app.core import runtime_settings as rs
from app.core.config import settings


def test_ogni_chiave_segreta_ha_un_accessor():
    """SECRET_KEYS non deve diventare una costante decorativa come
    ENV_BACKED_KEYS: ogni chiave dichiarata deve avere la sua funzione."""
    for key in rs.SECRET_KEYS:
        assert callable(getattr(rs, key)), f"manca l'accessor per {key}"


def test_gruppi_disgiunti():
    assert not set(rs.SECRET_KEYS) & set(rs.ENV_BACKED_KEYS)


def test_override_vince_sul_default_env(db, monkeypatch):
    monkeypatch.setattr(settings, "ai_api_key", "chiave-env")
    assert rs.ai_api_key() == "chiave-env"
    rs.apply(db, "ai_api_key", "chiave-db")
    assert rs.ai_api_key() == "chiave-db"
    assert rs.source("ai_api_key") == "db"


def test_override_vuoto_torna_al_default(db, monkeypatch):
    monkeypatch.setattr(settings, "discogs_token", "token-env")
    rs.apply(db, "discogs_token", "token-db")
    rs.apply(db, "discogs_token", "")
    assert rs.discogs_token() == "token-env"
    assert rs.source("discogs_token") == "env"


def test_secret_rifiuta_chiavi_fuori_gruppo():
    with pytest.raises(KeyError):
        rs.secret("database_url")


def test_i_segreti_non_vengono_espansi_come_path(db):
    """Una chiave che comincia per '~' non deve diventare un path della home."""
    rs.apply(db, "acoustid_api_key", "~strana~chiave")
    assert rs.acoustid_api_key() == "~strana~chiave"
```

- [ ] **Step 2: Eseguire il test e verificare che fallisca**

```bash
cd backend && /Users/lucadenegri/Develop/DJProject01/backend/.venv/bin/python -m pytest tests/test_runtime_secrets.py -q
```

Atteso: FAIL con `AttributeError: module 'app.core.runtime_settings' has no attribute 'SECRET_KEYS'`.

- [ ] **Step 3: Implementare**

In `backend/app/core/runtime_settings.py`, dopo la definizione di `ENV_BACKED_KEYS`, aggiungere `ai_model` al gruppo in chiaro e dichiarare il gruppo segreti:

```python
# Campi editabili con default in `.env`. `share_library` è escluso: è un flag
# solo-DB, senza controparte env.
ENV_BACKED_KEYS = ("library_root", "archive_root", "slskd_download_dir",
                   "slskd_url", "slskd_config_path", "ai_model")

# Credenziali: stessa semantica (override DB > default .env), ma il valore non
# esce mai dal backend — il router le espone solo mascherate.
SECRET_KEYS = ("spotify_client_id", "spotify_client_secret", "ai_api_key",
               "discogs_token", "acoustid_api_key", "slskd_api_key")
```

In fondo al blocco degli accessor, accanto a `slskd_config_path()`, aggiungere:

```python
def ai_model() -> str:
    return _resolved("ai_model")


def spotify_client_id() -> str:
    return _resolved("spotify_client_id")


def spotify_client_secret() -> str:
    return _resolved("spotify_client_secret")


def ai_api_key() -> str:
    return _resolved("ai_api_key")


def discogs_token() -> str:
    return _resolved("discogs_token")


def acoustid_api_key() -> str:
    return _resolved("acoustid_api_key")


def slskd_api_key() -> str:
    return _resolved("slskd_api_key")


def secret(key: str) -> str:
    """Valore effettivo di una credenziale. `KeyError` fuori da `SECRET_KEYS`:
    un typo non deve poter leggere in silenzio un campo qualsiasi di Settings."""
    if key not in SECRET_KEYS:
        raise KeyError(key)
    return _resolved(key)
```

`_PATH_KEYS` non va toccato: nessuna di queste chiavi è un path, quindi `_resolved` non applica `expanduser`.

- [ ] **Step 4: Eseguire i test e verificare che passino**

```bash
cd backend && /Users/lucadenegri/Develop/DJProject01/backend/.venv/bin/python -m pytest tests/test_runtime_secrets.py -q
```

Atteso: `6 passed`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/runtime_settings.py backend/tests/test_runtime_secrets.py
git commit -m "feat(config): credenziali scrivibili a runtime (SECRET_KEYS)"
```

---

## Task 2: Migrazione dei 18 call-site

**Files:**
- Modify: `backend/app/integrations/spotify.py:68-73`, `backend/app/integrations/llm.py:69,82,134`, `backend/app/integrations/discogs.py:47`, `backend/app/integrations/slskd.py:57`, `backend/app/routers/services.py:31,51,68`, `backend/app/routers/spotify.py:48`, `backend/app/organize/integrations/acoustid.py:42,137,146`, `backend/app/organize/integrations/discogs_meta.py:25`, `backend/app/organize/services/ai_tags.py:37,46,361`
- Test: `backend/tests/test_secrets_call_sites.py`

**Interfaces:**
- Consumes: gli accessor del Task 1.
- Produces: nessuna nuova API. Dopo questo task, cambiare una credenziale via `runtime_settings.apply` ha effetto immediato su ogni integrazione, senza riavvio.

- [ ] **Step 1: Scrivere il test che fallisce**

Creare `backend/tests/test_secrets_call_sites.py`:

```python
"""Ogni integrazione deve leggere la credenziale da runtime_settings (override
DB), non da settings: è la proprietà che rende utile il wizard, perché salvare
una chiave ha effetto senza riavviare il backend."""
from app.core import runtime_settings as rs
from app.core.config import settings


def test_spotify_usa_override(db, monkeypatch):
    from app.integrations import spotify
    monkeypatch.setattr(settings, "spotify_client_id", "")
    monkeypatch.setattr(settings, "spotify_client_secret", "")
    rs.apply(db, "spotify_client_id", "id-db")
    rs.apply(db, "spotify_client_secret", "secret-db")
    assert spotify._require_credentials() == ("id-db", "secret-db")


def test_llm_configured_usa_override(db, monkeypatch):
    from app.integrations import llm
    monkeypatch.setattr(settings, "ai_api_key", "")
    assert llm.llm_configured() is False
    rs.apply(db, "ai_api_key", "sk-db")
    assert llm.llm_configured() is True


def test_ai_tags_configured_usa_override(db, monkeypatch):
    from app.organize.services import ai_tags
    monkeypatch.setattr(settings, "ai_api_key", "")
    assert ai_tags.is_configured() is False
    rs.apply(db, "ai_api_key", "sk-db")
    assert ai_tags.is_configured() is True


def test_discogs_client_prende_il_token_override(db, monkeypatch):
    from app.integrations.discogs import DiscogsClient
    monkeypatch.setattr(settings, "discogs_token", "")
    rs.apply(db, "discogs_token", "tok-db")
    client = DiscogsClient()
    try:
        assert client.token == "tok-db"
    finally:
        client.close()


def test_discogs_meta_prende_il_token_override(db, monkeypatch):
    from app.organize.integrations.discogs_meta import DiscogsMetaClient
    monkeypatch.setattr(settings, "discogs_token", "")
    rs.apply(db, "discogs_token", "tok-db")
    assert DiscogsMetaClient().token == "tok-db"


def test_acoustid_configured_usa_override(db, monkeypatch):
    from app.organize.integrations import acoustid
    monkeypatch.setattr(settings, "acoustid_api_key", "")
    assert acoustid.acoustid_configured() is False
    rs.apply(db, "acoustid_api_key", "aid-db")
    assert acoustid.acoustid_configured() is True


def test_slskd_client_prende_la_api_key_override(db, monkeypatch):
    from app.integrations.slskd import SlskdClient
    monkeypatch.setattr(settings, "slskd_api_key", "")
    rs.apply(db, "slskd_api_key", "key-db")
    client = SlskdClient(base_url="http://localhost:5030")
    try:
        assert client.api_key == "key-db"
    finally:
        client.close()
```

Se una firma di costruttore non combacia (`DiscogsClient()`, `DiscogsMetaClient()`, `SlskdClient(base_url=...)`), aprire il file e usare quella reale: il test verifica la lettura della credenziale, non la firma.

- [ ] **Step 2: Eseguire il test e verificare che fallisca**

```bash
cd backend && /Users/lucadenegri/Develop/DJProject01/backend/.venv/bin/python -m pytest tests/test_secrets_call_sites.py -q
```

Atteso: FAIL — le integrazioni leggono ancora `settings`, che il test ha svuotato.

- [ ] **Step 3: Implementare la migrazione, file per file**

`backend/app/integrations/spotify.py` — sostituire il corpo di `_require_credentials`:

```python
def _require_credentials() -> tuple[str, str]:
    client_id = runtime_settings.spotify_client_id()
    client_secret = runtime_settings.spotify_client_secret()
    if not client_id or not client_secret:
        raise SpotifyNotConfigured(
            "Credenziali Spotify mancanti: impostarle dalla configurazione guidata "
            "(/setup) o in backend/.env (app su developer.spotify.com)."
        )
    return client_id, client_secret
```

aggiungendo `from app.core import runtime_settings` agli import.

`backend/app/integrations/llm.py` — in `AnthropicLLMClient.__init__` e in `llm_configured`:

```python
        api_key = runtime_settings.ai_api_key()
        if not api_key:
            raise LLMNotConfigured(
                "Chiave Anthropic mancante: impostarla dalla configurazione guidata "
                "(/setup) o come ANTHROPIC_API_KEY in backend/.env."
            )
```
```python
        self.client = anthropic.Anthropic(
            api_key=api_key, timeout=settings.ai_timeout_seconds
        )
        self.model = model or runtime_settings.ai_model() or DEFAULT_MODEL
```
```python
def llm_configured() -> bool:
    return bool(runtime_settings.ai_api_key())
```

`ai_effort`, `ai_thinking`, `ai_timeout_seconds` restano su `settings`: sono env-only per decisione di spec.

`backend/app/integrations/discogs.py:47`:

```python
        self.token = token if token is not None else (runtime_settings.discogs_token() or None)
```

`backend/app/integrations/slskd.py:57`:

```python
        self.api_key = api_key if api_key is not None else runtime_settings.slskd_api_key()
```

`backend/app/organize/integrations/discogs_meta.py:25`: stessa riga di `discogs.py`.

`backend/app/organize/integrations/acoustid.py` — le tre occorrenze:

```python
def acoustid_configured() -> bool:
    return bool(runtime_settings.acoustid_api_key())
```
```python
def get_acoustid_client() -> AcoustIDClient:
    api_key = runtime_settings.acoustid_api_key()
    if not api_key:
        raise AcoustIDNotConfigured(
            "Chiave AcoustID mancante: impostarla dalla configurazione guidata "
            "(/setup) o come ACOUSTID_API_KEY in backend/.env."
        )
    if not fpcalc_available():
        raise AcoustIDNotConfigured(
            "Binario fpcalc (Chromaprint) non trovato: installa chromaprint "
            "(brew install chromaprint) o imposta la env FPCALC."
        )
    return AcoustIDClient(api_key)
```

`backend/app/organize/services/ai_tags.py` — `is_configured` e i due `Anthropic(api_key=...)`:

```python
def is_configured() -> bool:
    return bool(runtime_settings.ai_api_key())
```
```python
    client = Anthropic(api_key=runtime_settings.ai_api_key())
```

`backend/app/routers/services.py` — le tre letture:

```python
    spotify_configured = bool(runtime_settings.spotify_client_id()
                              and runtime_settings.spotify_client_secret())
```
```python
                "configured": bool(runtime_settings.ai_api_key()), "connected": None,
```
```python
                "optional_ok": bool(runtime_settings.discogs_token()),
```

e nella `detail` dell'AI sostituire `settings.ai_model` con `runtime_settings.ai_model()`.

`backend/app/routers/spotify.py:48`:

```python
    configured = bool(runtime_settings.spotify_client_id()
                      and runtime_settings.spotify_client_secret())
```

- [ ] **Step 4: Eseguire i test e verificare che passino**

```bash
cd backend && /Users/lucadenegri/Develop/DJProject01/backend/.venv/bin/python -m pytest tests/test_secrets_call_sites.py -q
```
Atteso: `7 passed`.

Poi la suite intera, perché questo task tocca integrazioni usate ovunque:

```bash
cd backend && /Users/lucadenegri/Develop/DJProject01/backend/.venv/bin/python -m pytest tests -q
```
Atteso: nessun fallimento nuovo rispetto al baseline. La fixture `_reset_runtime_settings` in `conftest.py` azzera la cache fra i test, quindi i `monkeypatch.setattr(settings, …)` già presenti nella suite continuano a valere.

- [ ] **Step 5: Commit**

```bash
git add backend/app backend/tests/test_secrets_call_sites.py
git commit -m "refactor(config): le integrazioni leggono le credenziali da runtime_settings"
```

---

## Task 3: Blocco `secrets` in `/api/settings/config`

**Files:**
- Modify: `backend/app/routers/settings.py:44-125`
- Test: `backend/tests/test_config_secrets.py`

**Interfaces:**
- Consumes: `rs.SECRET_KEYS`, `rs.ENV_BACKED_KEYS`, `rs.secret()`, `rs.apply()`, `rs.source()`.
- Produces: risposta di `GET|PATCH /api/settings/config` con due campi nuovi:
  `secrets: dict[str, SecretState]` dove `SecretState = {configured: bool, source: "env"|"db", hint: str | None}`, e `spotify_redirect_uri: str` (sola lettura). `ConfigPatch` accetta in più: `ai_model`, `spotify_client_id`, `spotify_client_secret`, `ai_api_key`, `discogs_token`, `acoustid_api_key`, `slskd_api_key`.

- [ ] **Step 1: Scrivere il test che fallisce**

Creare `backend/tests/test_config_secrets.py`:

```python
"""Le credenziali si configurano via HTTP ma non tornano mai in chiaro."""
import json

from fastapi.testclient import TestClient

from app.core import runtime_settings as rs
from app.core.config import settings
from app.db import get_db
from app.main import app


def _client(db):
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app)


def test_il_valore_in_chiaro_non_compare_mai_nella_risposta(db, monkeypatch):
    """Asserzione sul JSON serializzato, non sul singolo campo: se un giorno
    qualcuno aggiunge la chiave in un altro punto della risposta, questo test
    la becca lo stesso."""
    monkeypatch.setattr(settings, "ai_api_key", "sk-super-segreta-12345")
    body = _client(db).get("/api/settings/config").json()
    assert "sk-super-segreta-12345" not in json.dumps(body)
    app.dependency_overrides.clear()


def test_hint_mostra_le_ultime_quattro(db, monkeypatch):
    monkeypatch.setattr(settings, "ai_api_key", "sk-super-segreta-a3f9")
    body = _client(db).get("/api/settings/config").json()
    assert body["secrets"]["ai_api_key"] == {
        "configured": True, "source": "env", "hint": "••••a3f9",
    }
    app.dependency_overrides.clear()


def test_chiave_assente(db, monkeypatch):
    monkeypatch.setattr(settings, "discogs_token", "")
    body = _client(db).get("/api/settings/config").json()
    assert body["secrets"]["discogs_token"] == {
        "configured": False, "source": "env", "hint": None,
    }
    app.dependency_overrides.clear()


def test_patch_salva_e_azzera(db, monkeypatch):
    monkeypatch.setattr(settings, "discogs_token", "token-env")
    client = _client(db)

    body = client.patch("/api/settings/config", json={"discogs_token": "token-db"}).json()
    assert body["secrets"]["discogs_token"]["source"] == "db"
    assert rs.discogs_token() == "token-db"

    body = client.patch("/api/settings/config", json={"discogs_token": ""}).json()
    assert body["secrets"]["discogs_token"]["source"] == "env"
    assert rs.discogs_token() == "token-env"
    app.dependency_overrides.clear()


def test_gli_spazi_intorno_alla_chiave_vengono_tolti(db):
    """Una chiave incollata porta spesso uno \\n finale: se lo si salva,
    l'header HTTP verso il provider diventa invalido e l'errore è incomprensibile."""
    _client(db).patch("/api/settings/config", json={"ai_api_key": "  sk-abcd\n"})
    assert rs.ai_api_key() == "sk-abcd"
    app.dependency_overrides.clear()


def test_ogni_campo_env_backed_e_esposto(db):
    """ENV_BACKED_KEYS deve essere la sorgente vera dei campi esposti, non una
    costante decorativa: aggiungerci una chiave deve comparire nella risposta
    senza toccare il router."""
    body = _client(db).get("/api/settings/config").json()
    for key in rs.ENV_BACKED_KEYS:
        assert key in body, f"{key} non esposto"
    app.dependency_overrides.clear()


def test_redirect_uri_e_esposto_in_sola_lettura(db):
    body = _client(db).get("/api/settings/config").json()
    assert body["spotify_redirect_uri"] == settings.spotify_redirect_uri
    app.dependency_overrides.clear()
```

- [ ] **Step 2: Eseguire il test e verificare che fallisca**

```bash
cd backend && /Users/lucadenegri/Develop/DJProject01/backend/.venv/bin/python -m pytest tests/test_config_secrets.py -q
```
Atteso: FAIL con `KeyError: 'secrets'`.

- [ ] **Step 3: Implementare**

In `backend/app/routers/settings.py`, sostituire la definizione di `_FIELD_KEYS` (che duplicava `ENV_BACKED_KEYS`) e aggiungere il modello dei segreti:

```python
# Directory il cui override deve puntare a una cartella esistente (vuoto = feature
# disattiva, come il default `.env`).
_DIR_KEYS = ("library_root", "archive_root", "slskd_download_dir")
# Tutti i campi in chiaro editabili: la sorgente è `runtime_settings`, non una
# seconda lista da tenere allineata a mano.
_FIELD_KEYS = rs.ENV_BACKED_KEYS
```

```python
class SecretState(BaseModel):
    """Stato di una credenziale. Il valore non esce mai: solo presenza,
    provenienza e le ultime 4 cifre per riconoscerla."""
    configured: bool
    source: Literal["env", "db"]
    hint: str | None = None
```

`ConfigSettings` diventa (i campi in chiaro non si possono più elencare a mano uno per uno, perché `_FIELD_KEYS` ora include `ai_model`):

```python
class ConfigSettings(BaseModel):
    library_root: FieldState
    archive_root: FieldState
    slskd_download_dir: FieldState
    slskd_url: FieldState
    slskd_config_path: FieldState
    ai_model: FieldState
    secrets: dict[str, SecretState]
    spotify_redirect_uri: str
    share_library: bool
    download_slots: int
    warning: str | None = None
```

`ConfigPatch` guadagna i campi nuovi:

```python
class ConfigPatch(BaseModel):
    # Ogni campo è opzionale: assente = invariato; stringa vuota = azzera l'override.
    library_root: str | None = None
    archive_root: str | None = None
    slskd_download_dir: str | None = None
    slskd_url: str | None = None
    slskd_config_path: str | None = None
    ai_model: str | None = None
    spotify_client_id: str | None = None
    spotify_client_secret: str | None = None
    ai_api_key: str | None = None
    discogs_token: str | None = None
    acoustid_api_key: str | None = None
    slskd_api_key: str | None = None
```

Il mascheramento e lo snapshot:

```python
def _secret_state(key: str) -> SecretState:
    value = rs.secret(key)
    if not value:
        return SecretState(configured=False, source=rs.source(key), hint=None)
    hint = f"••••{value[-4:]}" if len(value) >= 4 else "••••"
    return SecretState(configured=True, source=rs.source(key), hint=hint)


def _snapshot(warning: str | None = None) -> ConfigSettings:
    return ConfigSettings(
        **{k: _field_state(k) for k in _FIELD_KEYS},
        secrets={k: _secret_state(k) for k in rs.SECRET_KEYS},
        spotify_redirect_uri=settings.spotify_redirect_uri,
        share_library=rs.share_library(),
        download_slots=rs.download_slots(),
        warning=warning,
    )
```

aggiungendo `from app.core.config import settings` agli import.

In `patch_config`, i valori vanno ripuliti dagli spazi prima di validare e persistere. Sostituire l'inizio della funzione:

```python
@router.patch("/config", response_model=ConfigSettings)
def patch_config(req: ConfigPatch, db: Session = Depends(get_db)):
    # `strip`: una chiave incollata porta spesso spazi o un newline finale, che
    # renderebbero invalido l'header verso il provider con un errore opaco.
    updates = {k: (v or "").strip() for k, v in req.model_dump(exclude_unset=True).items()}
    # Valida TUTTO prima di persistere qualsiasi cosa (niente stato parziale).
    for key, value in updates.items():
        valid, detail = _validate(key, value)
        if not valid:
            raise api_error(422, "invalid_setting",
                            f"{key}: {detail}", field=key, detail=detail)

    old_library = rs.library_root()
    for key, value in updates.items():
        rs.apply(db, key, value)
```

`_validate` non richiede modifiche: per una chiave non elencata ritorna già `(True, None)`, e per le credenziali non esiste un formato da validare — la verifica vera è il Task 7.

- [ ] **Step 4: Eseguire i test e verificare che passino**

```bash
cd backend && /Users/lucadenegri/Develop/DJProject01/backend/.venv/bin/python -m pytest tests/test_config_secrets.py tests/test_download_slots_setting.py -q
```
Atteso: tutti verdi (il secondo file protegge dalla regressione sugli altri campi dello stesso router).

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/settings.py backend/tests/test_config_secrets.py
git commit -m "feat(config): credenziali mascherate in GET/PATCH /api/settings/config"
```

---

## Task 4: Router `/api/setup` e stato del wizard

**Files:**
- Create: `backend/app/routers/setup.py`
- Modify: `backend/app/main.py:113-131`
- Test: `backend/tests/test_setup_state.py`

**Interfaces:**
- Consumes: `app.services.app_state.get_state/set_state`, `app.db.get_db`.
- Produces: `GET /api/setup/state` e `PUT /api/setup/state`, entrambi con corpo `{"completed": bool}`. Costante `SETUP_COMPLETED_KEY = "setup.completed"`. Il router è il punto di aggancio dei Task 5, 6, 7.

- [ ] **Step 1: Scrivere il test che fallisce**

Creare `backend/tests/test_setup_state.py`:

```python
"""Il flag che decide se il primo avvio porta al wizard."""
from fastapi.testclient import TestClient

from app.db import get_db
from app.main import app


def _client(db):
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app)


def test_di_default_il_wizard_non_e_completato(db):
    assert _client(db).get("/api/setup/state").json() == {"completed": False}
    app.dependency_overrides.clear()


def test_completamento_persistito(db):
    client = _client(db)
    assert client.put("/api/setup/state", json={"completed": True}).json() == {"completed": True}
    assert client.get("/api/setup/state").json() == {"completed": True}
    app.dependency_overrides.clear()


def test_si_puo_riaprire(db):
    """Riaprire il wizard da Impostazioni non deve essere un vicolo cieco."""
    client = _client(db)
    client.put("/api/setup/state", json={"completed": True})
    client.put("/api/setup/state", json={"completed": False})
    assert client.get("/api/setup/state").json() == {"completed": False}
    app.dependency_overrides.clear()
```

- [ ] **Step 2: Eseguire il test e verificare che fallisca**

```bash
cd backend && /Users/lucadenegri/Develop/DJProject01/backend/.venv/bin/python -m pytest tests/test_setup_state.py -q
```
Atteso: FAIL con status 404.

- [ ] **Step 3: Implementare**

Creare `backend/app/routers/setup.py`:

```python
"""Configurazione guidata (`/setup`): stato del wizard, rilevamento dei
componenti esterni, installazione di quelli sicuri, verifica delle credenziali.

Router HTTP-only: la logica sta in `services/system_probe.py`,
`services/component_installer.py` e `services/credential_tests.py`. Nessun
testo user-facing nasce qui — solo chiavi, che il frontend traduce.
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import get_db
from app.services.app_state import get_state, set_state

router = APIRouter(prefix="/api/setup", tags=["setup"])

SETUP_COMPLETED_KEY = "setup.completed"


class SetupState(BaseModel):
    completed: bool


@router.get("/state", response_model=SetupState)
def read_state(db: Session = Depends(get_db)) -> SetupState:
    return SetupState(completed=get_state(db, SETUP_COMPLETED_KEY) == "1")


@router.put("/state", response_model=SetupState)
def write_state(req: SetupState, db: Session = Depends(get_db)) -> SetupState:
    """Scritto sia al completamento sia allo skip: in entrambi i casi il wizard
    non deve ripresentarsi da solo."""
    set_state(db, SETUP_COMPLETED_KEY, "1" if req.completed else "")
    return SetupState(completed=req.completed)
```

In `backend/app/main.py`, aggiungere `setup` all'import dei router e registrarlo dopo `settings_router`:

```python
app.include_router(setup.router)
```

- [ ] **Step 4: Eseguire i test e verificare che passino**

```bash
cd backend && /Users/lucadenegri/Develop/DJProject01/backend/.venv/bin/python -m pytest tests/test_setup_state.py -q
```
Atteso: `3 passed`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/setup.py backend/app/main.py backend/tests/test_setup_state.py
git commit -m "feat(setup): router /api/setup e stato del wizard"
```

---

## Task 5: Probe dei componenti esterni

**Files:**
- Create: `backend/app/services/system_probe.py`
- Modify: `backend/app/routers/setup.py`
- Test: `backend/tests/test_system_probe.py`

**Interfaces:**
- Consumes: `runtime_settings.slskd_url()`.
- Produces: `resolve_binary(name: str, env_override: str | None = None) -> str | None`; `REGISTRY: tuple[Component, ...]`; `recipe_for(component: Component) -> list[str] | None`; `probe_all(force: bool = False) -> list[dict]`; `get(key: str) -> Component | None`; costante `BIN_DIR_ENV = "CRATORY_BIN_DIR"`. Endpoint `GET /api/setup/probe` → `{"platform": str, "components": [...]}`. Ogni elemento: `{key, kind, severity, present, version, source, auto_installable, install_command, unlocks}`.

- [ ] **Step 1: Scrivere il test che fallisce**

Creare `backend/tests/test_system_probe.py`:

```python
"""Rilevamento dei componenti esterni: è la base del passo 1 del wizard."""
import os
import stat
import sys

from app.services import system_probe as sp


def test_binario_assente(monkeypatch):
    monkeypatch.delenv(sp.BIN_DIR_ENV, raising=False)
    monkeypatch.setattr(sp.shutil, "which", lambda name: None)
    assert sp.resolve_binary("ffmpeg") is None


def test_binario_dal_path(monkeypatch):
    monkeypatch.delenv(sp.BIN_DIR_ENV, raising=False)
    monkeypatch.setattr(sp.shutil, "which", lambda name: "/usr/bin/" + name)
    assert sp.resolve_binary("ffmpeg") == "/usr/bin/ffmpeg"


def test_bin_dir_vince_sul_path(tmp_path, monkeypatch):
    """È il gancio Tauri: coi binari nel bundle, CRATORY_BIN_DIR deve avere la
    precedenza sul PATH di sistema."""
    fake = tmp_path / "ffmpeg"
    fake.write_text("#!/bin/sh\n")
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv(sp.BIN_DIR_ENV, str(tmp_path))
    monkeypatch.setattr(sp.shutil, "which", lambda name: "/usr/bin/" + name)
    assert sp.resolve_binary("ffmpeg") == str(fake)


def test_env_override_specifico(tmp_path, monkeypatch):
    """fpcalc ha già una sua env FPCALC letta da organize: il probe la rispetta."""
    fake = tmp_path / "fpcalc-custom"
    fake.write_text("")
    monkeypatch.delenv(sp.BIN_DIR_ENV, raising=False)
    monkeypatch.setenv("FPCALC", str(fake))
    monkeypatch.setattr(sp.shutil, "which", lambda name: None)
    assert sp.resolve_binary("fpcalc", env_override="FPCALC") == str(fake)


def test_ricetta_per_piattaforma(monkeypatch):
    ffmpeg = sp.get("ffmpeg")
    monkeypatch.setattr(sp.sys, "platform", "darwin")
    assert sp.recipe_for(ffmpeg) == ["brew", "install", "ffmpeg"]


def test_ricetta_jolly_vale_ovunque(monkeypatch):
    ytdlp = sp.get("yt-dlp")
    monkeypatch.setattr(sp.sys, "platform", "sunos5")
    assert sp.recipe_for(ytdlp) == [sys.executable, "-m", "pip", "install", "-U", "yt-dlp"]


def test_ricetta_assente_ritorna_none(monkeypatch):
    slskd = sp.get("slskd")
    monkeypatch.setattr(sp.sys, "platform", "darwin")
    assert sp.recipe_for(slskd) is None


# NOTA (aggiunta in esecuzione, 2026-08-18): questo file ha bisogno anche di una
# fixture autouse che forzi `settings.slskd_url = ""` e azzeri `sp._cache` prima e
# dopo ogni test. Senza, `probe_all` raggiunge `_probe_slskd`, che con una
# SLSKD_URL presente nell'ambiente fa una vera chiamata di rete: il test
# dipenderebbe dalla macchina. Vedi backend/tests/test_system_probe.py.


def test_probe_all_ha_una_voce_per_componente(monkeypatch):
    # `_run_version` va neutralizzato insieme a `which`: Essentia si rileva con
    # un import in subprocess, e su una macchina che ce l'ha davvero il test
    # passerebbe o fallirebbe a seconda dell'ambiente.
    monkeypatch.setattr(sp.shutil, "which", lambda name: None)
    monkeypatch.setattr(sp, "_run_version", lambda argv: None)
    result = sp.probe_all(force=True)
    assert [c["key"] for c in result] == [c.key for c in sp.REGISTRY]
    assert all(c["present"] is False for c in result if c["kind"] != "daemon")


def test_la_cache_evita_di_riesaminare_a_ogni_render(monkeypatch):
    chiamate = {"n": 0}

    def conta(name):
        chiamate["n"] += 1
        return None

    monkeypatch.setattr(sp.shutil, "which", conta)
    monkeypatch.setattr(sp, "_run_version", lambda argv: None)  # niente subprocess veri
    sp.probe_all(force=True)
    prime = chiamate["n"]
    sp.probe_all()
    assert chiamate["n"] == prime, "la seconda chiamata doveva usare la cache"
    sp.probe_all(force=True)
    assert chiamate["n"] > prime


def test_essentia_ha_il_pin_e_il_flag_only_binary():
    """Senza --only-binary pip compila da sorgente dove manca la wheel cp311:
    il wizard resterebbe appeso venti minuti su un log illeggibile."""
    recipe = sp.recipe_for(sp.get("essentia"))
    assert "--only-binary=:all:" in recipe
    assert "essentia==2.1b6.dev1389" in recipe
```

- [ ] **Step 2: Eseguire il test e verificare che fallisca**

```bash
cd backend && /Users/lucadenegri/Develop/DJProject01/backend/.venv/bin/python -m pytest tests/test_system_probe.py -q
```
Atteso: FAIL con `ModuleNotFoundError: No module named 'app.services.system_probe'`.

- [ ] **Step 3: Implementare il servizio**

Creare `backend/app/services/system_probe.py`:

```python
"""Rilevamento dei componenti esterni di cui Cratory ha bisogno.

Un registry dichiarativo, una voce per componente: come si rileva, che cosa
sblocca, se è installabile in automatico e con quale comando. Il registry NON
contiene prosa — solo chiavi: descrizioni e istruzioni vivono nei dizionari
i18n del frontend.

Confine Tauri: `resolve_binary` guarda prima `CRATORY_BIN_DIR`, poi il PATH.
Quando i binari arriveranno impacchettati nel bundle basterà far partire il
processo con quella variabile impostata — qui non cambia nulla.
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from app.core import runtime_settings

log = logging.getLogger(__name__)

BIN_DIR_ENV = "CRATORY_BIN_DIR"
_CACHE_TTL_S = 10.0
_PROBE_TIMEOUT_S = 5.0


@dataclass(frozen=True)
class Component:
    key: str
    kind: Literal["system", "venv", "daemon"]
    severity: Literal["required", "optional"]
    # Chiavi di feature, non prosa: il frontend le traduce.
    unlocks: tuple[str, ...]
    auto_installable: bool
    # `sys.platform` -> argv. La chiave "*" vale per ogni piattaforma.
    recipes: dict[str, list[str]] = field(default_factory=dict)
    binary: str | None = None
    version_flag: str = "--version"
    env_override: str | None = None


REGISTRY: tuple[Component, ...] = (
    Component(
        key="ffmpeg", kind="system", severity="required",
        unlocks=("audio_hash", "shazam", "soundcloud_download"),
        auto_installable=False,
        recipes={
            "darwin": ["brew", "install", "ffmpeg"],
            "linux": ["sudo", "apt", "install", "-y", "ffmpeg"],
            "win32": ["winget", "install", "-e", "--id", "Gyan.FFmpeg"],
        },
        binary="ffmpeg", version_flag="-version",
    ),
    Component(
        key="fpcalc", kind="system", severity="optional",
        unlocks=("acoustid_fingerprint",),
        auto_installable=False,
        recipes={
            "darwin": ["brew", "install", "chromaprint"],
            "linux": ["sudo", "apt", "install", "-y", "libchromaprint-tools"],
            "win32": ["winget", "install", "-e", "--id", "AcoustID.Chromaprint"],
        },
        binary="fpcalc", version_flag="-version", env_override="FPCALC",
    ),
    Component(
        key="yt-dlp", kind="venv", severity="optional",
        unlocks=("soundcloud_import", "soundcloud_download", "shazam"),
        auto_installable=True,
        recipes={"*": [sys.executable, "-m", "pip", "install", "-U", "yt-dlp"]},
        binary="yt-dlp",
    ),
    Component(
        key="essentia", kind="venv", severity="optional",
        unlocks=("analysis_bpm_key",),
        auto_installable=True,
        # `--only-binary=:all:`: il pin ha wheel solo per cp311/macOS-arm64.
        # Senza il flag, altrove pip compilerebbe da sorgente e l'installazione
        # resterebbe appesa; così fallisce subito e la UI mostra la ricetta.
        recipes={"*": [sys.executable, "-m", "pip", "install",
                       "--only-binary=:all:", "essentia==2.1b6.dev1389"]},
    ),
    Component(
        key="slskd", kind="daemon", severity="optional",
        unlocks=("soulseek_download", "library_share"),
        auto_installable=False,
    ),
)

_BY_KEY = {c.key: c for c in REGISTRY}


def get(key: str) -> Component | None:
    return _BY_KEY.get(key)


def resolve_binary(name: str, env_override: str | None = None) -> str | None:
    """Percorso del binario, o None. Ordine: env specifica del componente →
    CRATORY_BIN_DIR (bundle) → PATH."""
    if env_override:
        custom = os.environ.get(env_override)
        if custom and Path(custom).exists():
            return custom
    bundled = os.environ.get(BIN_DIR_ENV)
    if bundled:
        candidate = Path(bundled) / name
        if candidate.exists():
            return str(candidate)
    return shutil.which(name)


def recipe_for(component: Component) -> list[str] | None:
    """Comando di installazione per la piattaforma corrente, o None se non
    esiste (es. slskd, che è un demone da installare a parte)."""
    if not component.recipes:
        return None
    return component.recipes.get(sys.platform) or component.recipes.get("*")


def _run_version(argv: list[str]) -> str | None:
    try:
        proc = subprocess.run(argv, capture_output=True, text=True,
                              timeout=_PROBE_TIMEOUT_S, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        log.debug("probe: %s non eseguibile (%s)", argv[0], exc)
        return None
    output = (proc.stdout or proc.stderr or "").strip()
    return output.splitlines()[0][:120] if output else None


def _probe_binary(c: Component) -> dict:
    path = resolve_binary(c.binary or c.key, c.env_override)
    if not path:
        return {"present": False, "version": None, "source": None}
    bundled = os.environ.get(BIN_DIR_ENV)
    source = "bundle" if bundled and path.startswith(bundled) else "path"
    return {"present": True, "version": _run_version([path, c.version_flag]),
            "source": source}


def _probe_essentia() -> dict:
    """Import in subprocess: Essentia è pesante e ha già il suo worker
    separato — non va caricata nel processo che serve le richieste."""
    version = _run_version([sys.executable, "-c",
                            "import essentia; print(essentia.__version__)"])
    return {"present": version is not None, "version": version,
            "source": "venv" if version else None}


def _probe_slskd() -> dict:
    """Il demone non è un binario da cercare nel PATH: o risponde al suo URL
    o non c'è. L'URL vuoto significa 'feature disattiva', non 'errore'."""
    url = runtime_settings.slskd_url()
    if not url:
        return {"present": False, "version": None, "source": None}
    import httpx
    try:
        res = httpx.get(f"{url.rstrip('/')}/health", timeout=_PROBE_TIMEOUT_S)
        return {"present": res.status_code < 500, "version": None, "source": "daemon"}
    except httpx.HTTPError:
        return {"present": False, "version": None, "source": None}


def _probe_one(c: Component) -> dict:
    if c.key == "essentia":
        detected = _probe_essentia()
    elif c.kind == "daemon":
        detected = _probe_slskd()
    else:
        detected = _probe_binary(c)
    return {
        "key": c.key, "kind": c.kind, "severity": c.severity,
        "unlocks": list(c.unlocks), "auto_installable": c.auto_installable,
        "install_command": recipe_for(c), **detected,
    }


_cache: tuple[float, list[dict]] | None = None


def probe_all(force: bool = False) -> list[dict]:
    """Stato di tutti i componenti. Cache TTL breve: la pagina del wizard
    ricarica spesso e ogni giro lancia subprocess."""
    global _cache
    now = time.monotonic()
    if not force and _cache and now - _cache[0] < _CACHE_TTL_S:
        return _cache[1]
    result = [_probe_one(c) for c in REGISTRY]
    _cache = (now, result)
    return result
```

- [ ] **Step 4: Aggiungere l'endpoint**

In `backend/app/routers/setup.py`, aggiungere l'import e l'endpoint:

```python
import sys

from app.services import system_probe


@router.get("/probe")
def probe(force: bool = False) -> dict:
    """Stato dei componenti esterni. `force=true` bypassa la cache: lo usa il
    bottone "Ricontrolla" dopo un'installazione."""
    return {"platform": sys.platform, "components": system_probe.probe_all(force=force)}
```

- [ ] **Step 5: Eseguire i test e verificare che passino**

```bash
cd backend && /Users/lucadenegri/Develop/DJProject01/backend/.venv/bin/python -m pytest tests/test_system_probe.py -q
```
Atteso: `10 passed`.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/system_probe.py backend/app/routers/setup.py backend/tests/test_system_probe.py
git commit -m "feat(setup): probe dei componenti esterni con registry dichiarativo"
```

---

## Task 6: Installer

**Files:**
- Create: `backend/app/services/component_installer.py`
- Modify: `backend/app/routers/setup.py`
- Test: `backend/tests/test_component_installer.py`

**Interfaces:**
- Consumes: `system_probe.get()`, `system_probe.recipe_for()`, `app.services.job_spawn.spawn`.
- Produces: `run_recipe(argv: list[str]) -> Iterator[str]`; `start(key: str) -> dict`; `status() -> dict`; eccezioni `UnknownComponent`, `NotAutoInstallable`, `AlreadyRunning`, `InstallFailed`. Lo stato ha forma `{"key": str|None, "status": "idle"|"running"|"done"|"error", "log": list[str], "detail": str|None}`. Endpoint `POST /api/setup/install/{key}` (202) e `GET /api/setup/install/status`.

- [ ] **Step 1: Scrivere il test che fallisce**

Creare `backend/tests/test_component_installer.py`:

```python
"""L'installer esegue solo ricette del registry, mai una stringa di shell."""
import pytest
from fastapi.testclient import TestClient

from app.db import get_db
from app.main import app
from app.services import component_installer as ci


class _FakeProc:
    def __init__(self, righe, returncode=0):
        self.stdout = iter(righe)
        self.returncode = returncode

    def wait(self):
        return self.returncode


@pytest.fixture(autouse=True)
def _reset_installer():
    ci.reset()
    yield
    ci.reset()


def test_chiave_sconosciuta(db):
    app.dependency_overrides[get_db] = lambda: db
    res = TestClient(app).post("/api/setup/install/rm-rf")
    assert res.status_code == 400
    app.dependency_overrides.clear()


def test_componente_non_auto_installabile(db):
    """ffmpeg si installa a mano: il wizard mostra il comando, non lo esegue."""
    app.dependency_overrides[get_db] = lambda: db
    res = TestClient(app).post("/api/setup/install/ffmpeg")
    assert res.status_code == 400
    app.dependency_overrides.clear()


def test_esecuzione_mai_via_shell(monkeypatch):
    visti = {}

    def fake_popen(argv, **kwargs):
        visti["argv"] = argv
        visti["kwargs"] = kwargs
        return _FakeProc(["riga 1", "riga 2"])

    monkeypatch.setattr(ci.subprocess, "Popen", fake_popen)
    righe = list(ci.run_recipe(["echo", "ciao"]))

    assert righe == ["riga 1", "riga 2"]
    assert isinstance(visti["argv"], list), "argv deve restare una lista"
    assert visti["kwargs"].get("shell") in (None, False)


def test_returncode_non_zero_solleva(monkeypatch):
    monkeypatch.setattr(ci.subprocess, "Popen",
                        lambda argv, **kw: _FakeProc(["boom"], returncode=1))
    with pytest.raises(ci.InstallFailed):
        list(ci.run_recipe(["pip", "install", "niente"]))


def test_installazione_riuscita(monkeypatch):
    monkeypatch.setattr(ci.subprocess, "Popen",
                        lambda argv, **kw: _FakeProc(["Collecting yt-dlp", "Successfully installed"]))
    monkeypatch.setattr(ci, "spawn", lambda fn: fn())  # sincrono nei test
    ci.start("yt-dlp")
    stato = ci.status()
    assert stato["status"] == "done"
    assert stato["key"] == "yt-dlp"
    assert "Successfully installed" in stato["log"]


def test_installazione_fallita_registra_l_errore(monkeypatch):
    monkeypatch.setattr(ci.subprocess, "Popen",
                        lambda argv, **kw: _FakeProc(["ERROR: no matching distribution"], returncode=1))
    monkeypatch.setattr(ci, "spawn", lambda fn: fn())
    ci.start("essentia")
    stato = ci.status()
    assert stato["status"] == "error"
    assert stato["detail"]


def test_una_installazione_alla_volta(monkeypatch):
    monkeypatch.setattr(ci, "spawn", lambda fn: None)  # resta "running"
    ci.start("yt-dlp")
    with pytest.raises(ci.AlreadyRunning):
        ci.start("essentia")


def test_il_log_e_limitato(monkeypatch):
    monkeypatch.setattr(ci.subprocess, "Popen",
                        lambda argv, **kw: _FakeProc([f"riga {i}" for i in range(2000)]))
    monkeypatch.setattr(ci, "spawn", lambda fn: fn())
    ci.start("yt-dlp")
    assert len(ci.status()["log"]) <= ci.MAX_LOG_LINES
```

- [ ] **Step 2: Eseguire il test e verificare che fallisca**

```bash
cd backend && /Users/lucadenegri/Develop/DJProject01/backend/.venv/bin/python -m pytest tests/test_component_installer.py -q
```
Atteso: FAIL con `ModuleNotFoundError: No module named 'app.services.component_installer'`.

- [ ] **Step 3: Implementare il servizio**

Creare `backend/app/services/component_installer.py`:

```python
"""Installazione dei componenti che stanno nel perimetro dell'app (il venv).

Perimetro stretto per scelta: si installa solo ciò che è `auto_installable` nel
registry del probe — oggi `yt-dlp` ed `essentia`. I componenti di sistema
(ffmpeg, fpcalc) e il demone slskd non si installano da qui: il wizard mostra
il comando e lascia fare all'utente.

`run_recipe` è l'UNICO punto in cui questo modulo esegue un processo esterno:
in Tauri sarà quello da sostituire, non i suoi chiamanti.
"""
from __future__ import annotations

import logging
import subprocess
import threading
from typing import Iterator

from app.services import system_probe
from app.services.job_spawn import spawn

log = logging.getLogger(__name__)

MAX_LOG_LINES = 500


class InstallError(Exception):
    pass


class UnknownComponent(InstallError):
    pass


class NotAutoInstallable(InstallError):
    pass


class AlreadyRunning(InstallError):
    pass


class InstallFailed(InstallError):
    pass


_lock = threading.Lock()
_state: dict = {"key": None, "status": "idle", "log": [], "detail": None}


def reset() -> None:
    """Riporta l'installer a riposo (usato dai test)."""
    with _lock:
        _state.update({"key": None, "status": "idle", "log": [], "detail": None})


def status() -> dict:
    with _lock:
        return {**_state, "log": list(_state["log"])}


def run_recipe(argv: list[str]) -> Iterator[str]:
    """Esegue una ricetta e produce le righe di output.

    `shell=False` (default di Popen) e `argv` come lista: nessuna stringa viene
    mai interpretata da una shell, e nessun input utente entra qui — le ricette
    arrivano solo dal registry.
    """
    proc = subprocess.Popen(argv, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, bufsize=1)
    for line in proc.stdout:
        yield line.rstrip()
    returncode = proc.wait()
    if returncode != 0:
        raise InstallFailed(f"{argv[0]} è uscito con codice {returncode}")


def _append(line: str) -> None:
    with _lock:
        _state["log"].append(line)
        if len(_state["log"]) > MAX_LOG_LINES:
            del _state["log"][0:len(_state["log"]) - MAX_LOG_LINES]


def start(key: str) -> dict:
    """Avvia l'installazione di un componente. Solo ricette del registry."""
    component = system_probe.get(key)
    if component is None:
        raise UnknownComponent(key)
    if not component.auto_installable:
        raise NotAutoInstallable(key)
    recipe = system_probe.recipe_for(component)
    if recipe is None:
        raise NotAutoInstallable(key)

    with _lock:
        if _state["status"] == "running":
            raise AlreadyRunning(_state["key"])
        _state.update({"key": key, "status": "running", "log": [], "detail": None})

    def run() -> None:
        # NOTA (decisa in esecuzione, 2026-08-18): l'INTERO corpo sta dentro il
        # try, e c'e' un secondo ramo `except Exception`. Un'eccezione che sfugge
        # qui morirebbe nel thread senza spostare lo stato da "running", e
        # `start()` risponderebbe 409 a ogni richiesta successiva fino al riavvio
        # del backend. L'invalidazione della cache passa dal seam pubblico
        # `system_probe.invalidate_cache()`, non da `probe_all(force=True)`:
        # ri-sondare da questo thread lancerebbe i sottoprocessi del probe senza
        # bisogno.
        try:
            for line in run_recipe(recipe):
                _append(line)
            system_probe.invalidate_cache()
            with _lock:
                _state.update({"status": "done", "detail": None})
        except (InstallFailed, OSError) as exc:
            log.warning("installazione di %s fallita: %s", key, exc)
            with _lock:
                _state.update({"status": "error", "detail": str(exc)})
            return
        except Exception as exc:  # noqa: BLE001 - ampio di proposito
            log.exception("installazione di %s fallita in modo inatteso", key)
            with _lock:
                _state.update({"status": "error", "detail": str(exc)})
            return

    spawn(run)
    return status()
```

- [ ] **Step 4: Aggiungere gli endpoint**

In `backend/app/routers/setup.py`:

```python
from fastapi import APIRouter, Depends, Response

from app.core.http_errors import api_error
from app.services import component_installer


@router.post("/install/{key}", status_code=202)
def install(key: str, response: Response) -> dict:
    try:
        return component_installer.start(key)
    except component_installer.UnknownComponent as exc:
        raise api_error(400, "unknown_component", f"componente sconosciuto: {key}",
                        component=key) from exc
    except component_installer.NotAutoInstallable as exc:
        raise api_error(400, "not_auto_installable",
                        f"{key} va installato a mano", component=key) from exc
    except component_installer.AlreadyRunning as exc:
        raise api_error(409, "install_already_running",
                        "un'installazione è già in corso") from exc


@router.get("/install/status")
def install_status() -> dict:
    return component_installer.status()
```

- [ ] **Step 5: Eseguire i test e verificare che passino**

```bash
cd backend && /Users/lucadenegri/Develop/DJProject01/backend/.venv/bin/python -m pytest tests/test_component_installer.py tests/test_system_probe.py -q
```
Atteso: `18 passed`.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/component_installer.py backend/app/routers/setup.py backend/tests/test_component_installer.py
git commit -m "feat(setup): installer con whitelist di ricette e log in streaming"
```

---

## Task 7: Verifica delle credenziali

**Files:**
- Create: `backend/app/services/credential_tests.py`
- Modify: `backend/app/routers/setup.py`
- Test: `backend/tests/test_credential_tests.py`

**Interfaces:**
- Consumes: accessor di `runtime_settings`, `system_probe.resolve_binary`.
- Produces: `check(service: str, client: httpx.Client | None = None) -> dict` con forma `{"ok": bool, "detail": str, "code": str}`; `SERVICES: tuple[str, ...] = ("spotify", "anthropic", "discogs", "acoustid")`. Endpoint `POST /api/setup/test/{service}`.

**Nota (raffinamento dello spec §4):** slskd non ha una `check_` propria. Il passo 4 del wizard riusa `GET /api/slskd/status`, che già riporta `configured`/`reachable` e non richiede codice nuovo.

- [ ] **Step 1: Scrivere il test che fallisce**

Creare `backend/tests/test_credential_tests.py`:

```python
"""La prova di una credenziale deve riportare l'errore VERO del provider:
è la differenza fra un wizard che diagnostica e uno che dice 'errore'."""
import httpx
import pytest

from app.core import runtime_settings as rs
from app.core.config import settings
from app.services import credential_tests as ct


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_spotify_credenziali_valide(db, monkeypatch):
    monkeypatch.setattr(settings, "spotify_client_id", "")
    monkeypatch.setattr(settings, "spotify_client_secret", "")
    rs.apply(db, "spotify_client_id", "id")
    rs.apply(db, "spotify_client_secret", "secret")
    with _client(lambda req: httpx.Response(200, json={"access_token": "t"})) as c:
        assert ct.check("spotify", client=c)["ok"] is True


def test_spotify_riporta_il_messaggio_del_provider(db, monkeypatch):
    monkeypatch.setattr(settings, "spotify_client_id", "")
    monkeypatch.setattr(settings, "spotify_client_secret", "")
    rs.apply(db, "spotify_client_id", "id")
    rs.apply(db, "spotify_client_secret", "sbagliata")
    payload = {"error": "invalid_client", "error_description": "Invalid client secret"}
    with _client(lambda req: httpx.Response(400, json=payload)) as c:
        res = ct.check("spotify", client=c)
    assert res["ok"] is False
    assert "Invalid client secret" in res["detail"]


def test_servizio_non_configurato_non_chiama_la_rete(db, monkeypatch):
    monkeypatch.setattr(settings, "spotify_client_id", "")
    monkeypatch.setattr(settings, "spotify_client_secret", "")

    def esplodi(req):
        raise AssertionError("non doveva chiamare la rete")

    with _client(esplodi) as c:
        res = ct.check("spotify", client=c)
    assert res == {"ok": False, "code": "not_configured", "detail": ""}


def test_anthropic_ok(db, monkeypatch):
    monkeypatch.setattr(settings, "ai_api_key", "")
    rs.apply(db, "ai_api_key", "sk-test")
    with _client(lambda req: httpx.Response(200, json={"id": "msg_1"})) as c:
        assert ct.check("anthropic", client=c)["ok"] is True


def test_anthropic_chiave_invalida(db, monkeypatch):
    monkeypatch.setattr(settings, "ai_api_key", "")
    rs.apply(db, "ai_api_key", "sk-sbagliata")
    payload = {"error": {"message": "invalid x-api-key"}}
    with _client(lambda req: httpx.Response(401, json=payload)) as c:
        res = ct.check("anthropic", client=c)
    assert res["ok"] is False
    assert "invalid x-api-key" in res["detail"]


def test_discogs_senza_token_e_valido(db, monkeypatch):
    """Il dig funziona anche senza token, a rate ridotto: non è un errore."""
    monkeypatch.setattr(settings, "discogs_token", "")

    def esplodi(req):
        raise AssertionError("senza token non c'è niente da provare")

    with _client(esplodi) as c:
        res = ct.check("discogs", client=c)
    assert res == {"ok": True, "code": "no_token", "detail": ""}


def test_discogs_token_valido(db, monkeypatch):
    monkeypatch.setattr(settings, "discogs_token", "")
    rs.apply(db, "discogs_token", "tok")
    with _client(lambda req: httpx.Response(200, json={"username": "dj"})) as c:
        res = ct.check("discogs", client=c)
    assert res["ok"] is True
    assert "dj" in res["detail"]


def test_acoustid_senza_fpcalc_non_e_pronto(db, monkeypatch):
    """Chiave e binario servono entrambi: senza dirlo, l'utente mette la chiave
    e resta col bottone grigio senza capire perché."""
    monkeypatch.setattr(settings, "acoustid_api_key", "")
    rs.apply(db, "acoustid_api_key", "aid")
    monkeypatch.setattr(ct.system_probe, "resolve_binary", lambda *a, **k: None)

    def esplodi(req):
        raise AssertionError("senza fpcalc non serve chiamare AcoustID")

    with _client(esplodi) as c:
        res = ct.check("acoustid", client=c)
    assert res["ok"] is False
    assert res["code"] == "fpcalc_missing"


def test_acoustid_chiave_invalida(db, monkeypatch):
    monkeypatch.setattr(settings, "acoustid_api_key", "")
    rs.apply(db, "acoustid_api_key", "sbagliata")
    monkeypatch.setattr(ct.system_probe, "resolve_binary", lambda *a, **k: "/usr/bin/fpcalc")
    payload = {"status": "error", "error": {"message": "invalid API key"}}
    with _client(lambda req: httpx.Response(200, json=payload)) as c:
        res = ct.check("acoustid", client=c)
    assert res["ok"] is False


def test_acoustid_altro_errore_non_e_colpa_della_chiave(db, monkeypatch):
    """Una fingerprint finta fa protestare AcoustID: significa che la chiave
    è stata accettata."""
    monkeypatch.setattr(settings, "acoustid_api_key", "")
    rs.apply(db, "acoustid_api_key", "buona")
    monkeypatch.setattr(ct.system_probe, "resolve_binary", lambda *a, **k: "/usr/bin/fpcalc")
    payload = {"status": "error", "error": {"message": "invalid fingerprint"}}
    with _client(lambda req: httpx.Response(200, json=payload)) as c:
        assert ct.check("acoustid", client=c)["ok"] is True


def test_servizio_sconosciuto():
    with pytest.raises(KeyError):
        ct.check("pippo")


def test_errore_di_rete_non_propaga(db, monkeypatch):
    monkeypatch.setattr(settings, "ai_api_key", "")
    rs.apply(db, "ai_api_key", "sk-test")

    def timeout(req):
        raise httpx.ConnectTimeout("timeout")

    with _client(timeout) as c:
        res = ct.check("anthropic", client=c)
    assert res["ok"] is False
    assert res["code"] == "network_error"
```

- [ ] **Step 2: Eseguire il test e verificare che fallisca**

```bash
cd backend && /Users/lucadenegri/Develop/DJProject01/backend/.venv/bin/python -m pytest tests/test_credential_tests.py -q
```
Atteso: FAIL con `ModuleNotFoundError: No module named 'app.services.credential_tests'`.

- [ ] **Step 3: Implementare il servizio**

Creare `backend/app/services/credential_tests.py`:

```python
"""Prova reale delle credenziali: una chiamata minima per provider.

Il `detail` riporta il messaggio del provider così com'è, non una nostra
parafrasi: è quello che permette all'utente di capire se ha sbagliato il
segreto, se l'account non ha credito o se è la rete a non funzionare.

Le funzioni si chiamano `check_*` e non `test_*` di proposito: `test_*` in un
modulo importato dalla suite sarebbe raccolto da pytest come caso di test.
"""
from __future__ import annotations

import base64
import logging

import httpx

from app.core import runtime_settings
from app.integrations.llm import DEFAULT_MODEL
from app.services import system_probe

log = logging.getLogger(__name__)

SERVICES = ("spotify", "anthropic", "discogs", "acoustid")
_TIMEOUT_S = 15.0

_NOT_CONFIGURED = {"ok": False, "code": "not_configured", "detail": ""}


def _ok(detail: str = "", code: str = "ok") -> dict:
    return {"ok": True, "code": code, "detail": detail}


def _ko(detail: str, code: str = "invalid") -> dict:
    return {"ok": False, "code": code, "detail": detail}


def _provider_message(res: httpx.Response) -> str:
    """Messaggio d'errore del provider, qualunque forma abbia il suo JSON."""
    try:
        body = res.json()
    except ValueError:
        return res.text[:300] or f"HTTP {res.status_code}"
    if isinstance(body, dict):
        err = body.get("error")
        if isinstance(err, dict) and err.get("message"):
            return str(err["message"])
        if isinstance(err, str):
            return str(body.get("error_description") or err)
        if body.get("message"):
            return str(body["message"])
    return f"HTTP {res.status_code}"


def check_spotify(client: httpx.Client) -> dict:
    client_id = runtime_settings.spotify_client_id()
    client_secret = runtime_settings.spotify_client_secret()
    if not client_id or not client_secret:
        return dict(_NOT_CONFIGURED)
    basic = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    res = client.post(
        "https://accounts.spotify.com/api/token",
        data={"grant_type": "client_credentials"},
        headers={"Authorization": f"Basic {basic}"},
        timeout=_TIMEOUT_S,
    )
    if res.status_code == 200:
        return _ok()
    return _ko(_provider_message(res))


def check_anthropic(client: httpx.Client) -> dict:
    api_key = runtime_settings.ai_api_key()
    if not api_key:
        return dict(_NOT_CONFIGURED)
    res = client.post(
        "https://api.anthropic.com/v1/messages",
        headers={"x-api-key": api_key, "anthropic-version": "2023-06-01",
                 "content-type": "application/json"},
        json={"model": runtime_settings.ai_model() or DEFAULT_MODEL,
              "max_tokens": 1,
              "messages": [{"role": "user", "content": "ping"}]},
        timeout=_TIMEOUT_S,
    )
    if res.status_code == 200:
        return _ok()
    return _ko(_provider_message(res))


def check_discogs(client: httpx.Client) -> dict:
    """Senza token il dig funziona lo stesso, a rate ridotto: è un esito
    valido, non un errore da segnalare in rosso."""
    token = runtime_settings.discogs_token()
    if not token:
        return _ok(code="no_token")
    res = client.get(
        "https://api.discogs.com/oauth/identity",
        headers={"Authorization": f"Discogs token={token}"},
        timeout=_TIMEOUT_S,
    )
    if res.status_code == 200:
        try:
            return _ok(str(res.json().get("username", "")))
        except ValueError:
            return _ok()
    return _ko(_provider_message(res))


def check_acoustid(client: httpx.Client) -> dict:
    """Servono chiave E binario. La lookup viene mandata con una fingerprint
    non valida di proposito: se AcoustID protesta per la fingerprint vuol dire
    che la chiave l'ha accettata."""
    api_key = runtime_settings.acoustid_api_key()
    if not api_key:
        return dict(_NOT_CONFIGURED)
    if system_probe.resolve_binary("fpcalc", env_override="FPCALC") is None:
        return _ko("", code="fpcalc_missing")
    res = client.get(
        "https://api.acoustid.org/v2/lookup",
        params={"client": api_key, "duration": 120, "fingerprint": "sonda"},
        timeout=_TIMEOUT_S,
    )
    try:
        body = res.json()
    except ValueError:
        return _ko(f"HTTP {res.status_code}")
    if body.get("status") == "ok":
        return _ok()
    message = str((body.get("error") or {}).get("message", ""))
    if "api key" in message.lower():
        return _ko(message)
    return _ok(message, code="key_accepted")


_CHECKS = {
    "spotify": check_spotify,
    "anthropic": check_anthropic,
    "discogs": check_discogs,
    "acoustid": check_acoustid,
}


def check(service: str, client: httpx.Client | None = None) -> dict:
    """Esito della prova. Un errore di rete non deve propagare: il wizard deve
    poter mostrare 'non raggiungibile' invece di un 500."""
    if service not in _CHECKS:
        raise KeyError(service)
    owned = client is None
    client = client or httpx.Client()
    try:
        return _CHECKS[service](client)
    except httpx.HTTPError as exc:
        log.info("prova %s fallita: %s", service, exc)
        return _ko(str(exc), code="network_error")
    finally:
        if owned:
            client.close()
```

- [ ] **Step 4: Aggiungere l'endpoint**

In `backend/app/routers/setup.py`:

```python
from app.services import credential_tests


@router.post("/test/{service}")
def test_credential(service: str) -> dict:
    """Prova reale della credenziale. slskd non è qui: il suo stato vivo lo dà
    già `GET /api/slskd/status`."""
    try:
        return credential_tests.check(service)
    except KeyError as exc:
        raise api_error(400, "unknown_service", f"servizio sconosciuto: {service}",
                        service=service) from exc
```

- [ ] **Step 5: Eseguire i test e verificare che passino**

```bash
cd backend && /Users/lucadenegri/Develop/DJProject01/backend/.venv/bin/python -m pytest tests/test_credential_tests.py -q
```
Atteso: `12 passed`.

Poi la suite backend completa:

```bash
cd backend && /Users/lucadenegri/Develop/DJProject01/backend/.venv/bin/python -m pytest tests -q
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/credential_tests.py backend/app/routers/setup.py backend/tests/test_credential_tests.py
git commit -m "feat(setup): prova reale delle credenziali con l'errore del provider"
```

---

## Task 8: Client API e dizionari i18n

**Files:**
- Create: `frontend/lib/api/setup.ts`, `frontend/lib/setup-services.ts`
- Modify: `frontend/lib/api.ts`, `frontend/lib/i18n/en.ts`, `frontend/lib/i18n/it.ts`

**Interfaces:**
- Produces:
  - tipi `SecretState`, `ProbeComponent`, `ProbeResponse`, `InstallStatus`, `CredentialTestResult`, `SetupState`, `SecretKey`, `ServiceKey`;
  - funzioni `getSetupState()`, `setSetupCompleted(completed: boolean)`, `getProbe(force?: boolean)`, `startInstall(key: string)`, `getInstallStatus()`, `testCredential(service: string)`;
  - `SERVICE_FIELDS: Record<ServiceKey, SecretKey[]>` in `lib/setup-services.ts`;
  - sezione `t.setup` del dizionario.

- [ ] **Step 1: Scrivere il client API**

Creare `frontend/lib/api/setup.ts`:

```ts
import { apiGet, apiPost, apiPut } from "./client";

/** Stato di una credenziale: il valore non arriva mai dal backend. */
export type SecretState = {
  configured: boolean;
  source: "env" | "db";
  hint: string | null;
};

export type SecretKey =
  | "spotify_client_id" | "spotify_client_secret" | "ai_api_key"
  | "discogs_token" | "acoustid_api_key" | "slskd_api_key";

export type ProbeComponent = {
  key: string;
  kind: "system" | "venv" | "daemon";
  severity: "required" | "optional";
  present: boolean;
  version: string | null;
  source: "bundle" | "path" | "venv" | "daemon" | null;
  auto_installable: boolean;
  install_command: string[] | null;
  unlocks: string[];
};

export type ProbeResponse = { platform: string; components: ProbeComponent[] };

export type InstallStatus = {
  key: string | null;
  status: "idle" | "running" | "done" | "error";
  log: string[];
  detail: string | null;
};

export type CredentialTestResult = { ok: boolean; code: string; detail: string };

export type SetupState = { completed: boolean };

/** Il wizard è già stato completato o saltato? */
export function getSetupState() {
  return apiGet<SetupState>("/api/setup/state");
}

/** Segna il wizard come completato (o lo riapre). */
export function setSetupCompleted(completed: boolean) {
  return apiPut<SetupState>("/api/setup/state", { completed });
}

/** Stato dei componenti esterni. `force` bypassa la cache del backend. */
export function getProbe(force = false) {
  return apiGet<ProbeResponse>("/api/setup/probe", force ? { force: true } : undefined);
}

/** Avvia l'installazione di un componente auto-installabile. */
export function startInstall(key: string) {
  return apiPost<InstallStatus>(`/api/setup/install/${key}`);
}

export function getInstallStatus() {
  return apiGet<InstallStatus>("/api/setup/install/status");
}

/** Prova reale della credenziale presso il provider. */
export function testCredential(service: string) {
  return apiPost<CredentialTestResult>(`/api/setup/test/${service}`);
}
```

In `frontend/lib/api.ts`, aggiungere in fondo all'elenco:

```ts
export * from "./api/setup";
```

`ConfigSettings` in `frontend/lib/api/types.ts` va aggiornato coi campi nuovi. Aggiungere al tipo esistente:

```ts
  ai_model: FieldState;
  secrets: Record<SecretKey, SecretState>;
  spotify_redirect_uri: string;
```

e a `ConfigPatch`:

```ts
  ai_model?: string;
  spotify_client_id?: string;
  spotify_client_secret?: string;
  ai_api_key?: string;
  discogs_token?: string;
  acoustid_api_key?: string;
  slskd_api_key?: string;
```

importando i due tipi da `./setup` (`import type { SecretKey, SecretState } from "./setup";`).

- [ ] **Step 2: Scrivere la mappa servizio → campi**

Creare `frontend/lib/setup-services.ts`:

```ts
import type { SecretKey } from "@/lib/api";

/** Quali credenziali servono a ciascun servizio. Dati, non JSX: la stessa
 *  mappa serve al wizard e alla pagina Impostazioni. */
export type ServiceKey = "spotify" | "anthropic" | "discogs" | "acoustid" | "slskd";

export const SERVICE_FIELDS: Record<ServiceKey, SecretKey[]> = {
  spotify: ["spotify_client_id", "spotify_client_secret"],
  anthropic: ["ai_api_key"],
  discogs: ["discogs_token"],
  acoustid: ["acoustid_api_key"],
  slskd: ["slskd_api_key"],
};

/** I servizi che hanno una prova reale lato backend. slskd no: il suo stato
 *  vivo arriva da GET /api/slskd/status. */
export const TESTABLE: ServiceKey[] = ["spotify", "anthropic", "discogs", "acoustid"];
```

- [ ] **Step 3: Aggiungere la sezione `setup` a `en.ts`**

`en.ts` è la fonte di verità dei tipi: va per primo. Aggiungere dentro `export const en = {`, dopo la sezione `settings`:

```ts
  setup: {
    title: "Guided setup",
    subtitle: "Six steps to get Cratory working. Every step can be skipped.",
    stepOf: (n: number, total: number) => `Step ${n} of ${total}`,
    next: "Next",
    back: "Back",
    skip: "Skip this step",
    skipAll: "Skip setup",
    finish: "Enter the app",
    reopen: "Reopen guided setup",
    // Step 0
    welcomeTitle: "Welcome to Cratory",
    welcomeBody: "Cratory imports your streaming playlists, builds DJ sets from the tracks you own, digs for new music and keeps your library tidy. This wizard checks what is installed, sets up the external services and explains how to get each API key. Nothing here is mandatory: skip anything you don't need and come back from Settings.",
    languageLabel: "Language",
    // Step 1
    prereqTitle: "External components",
    prereqBody: "Cratory relies on a few programs that live outside the app. ffmpeg is the only one that is really needed; everything else only switches off the feature that uses it.",
    installButton: "Install",
    installing: "Installing…",
    installDone: "Installed",
    installFailed: "Installation failed",
    installManual: "Install it yourself, then press Recheck:",
    copyCommand: "Copy command",
    copied: "Copied",
    recheck: "Recheck",
    detected: (version: string) => `Found: ${version}`,
    notFound: "Not found",
    fromBundle: "Bundled with the app",
    severityRequired: "Required",
    severityOptional: "Optional",
    unlocksLabel: "Enables:",
    components: {
      ffmpeg: "Audio decoding. Without it Cratory cannot fingerprint your files, identify mixes or extract audio from SoundCloud.",
      fpcalc: "Chromaprint's fingerprint tool. Needed by AcoustID to identify a file from the sound itself.",
      "yt-dlp": "Reads SoundCloud pages: playlist and likes import, and per-track download.",
      essentia: "In-app BPM and key analysis, the alternative to importing them from Rekordbox.",
      slskd: "The Soulseek daemon that downloads files. It runs as a separate program.",
    },
    unlocks: {
      audio_hash: "file identity",
      shazam: "mix identification",
      soundcloud_download: "SoundCloud download",
      soundcloud_import: "SoundCloud import",
      acoustid_fingerprint: "acoustic fingerprint",
      analysis_bpm_key: "in-app BPM/key analysis",
      soulseek_download: "Soulseek download",
      library_share: "library sharing",
    },
    // Step 2
    libraryTitle: "Your library",
    libraryBody: "The library is the disk: the folder Cratory indexes is what you own. Streaming playlists are only leads until a file backs them. Cratory reads these files and never modifies them.",
    libraryRootLabel: "Library folder",
    archiveRootLabel: "Archive of passed tracks (optional)",
    choose: "Choose…",
    indexNow: "Index now",
    indexing: "Indexing…",
    indexDone: (n: number) => `${n} files indexed`,
    // Step 3
    servicesTitle: "External services",
    servicesBody: "Each service is optional and switches on one part of the app. Keys are stored on this machine, in Cratory's own database.",
    save: "Save",
    saved: "Saved",
    replace: "Replace",
    configuredAs: (hint: string) => `configured ${hint}`,
    testButton: "Test",
    testing: "Testing…",
    testOk: "Works",
    testKo: "Doesn't work",
    testNotConfigured: "Nothing to test yet",
    testNoToken: "Works without a token, at a lower rate limit",
    testFpcalcMissing: "Key saved, but fpcalc is missing — go back to step 1",
    testNetworkError: "Could not reach the provider",
    howTo: "How to get it",
    openProvider: "Open the provider",
    copyValue: "Copy",
    fieldLabels: {
      spotify_client_id: "Client ID",
      spotify_client_secret: "Client secret",
      ai_api_key: "API key",
      discogs_token: "Personal access token",
      acoustid_api_key: "API key",
      slskd_api_key: "API key (optional)",
    },
    guides: {
      spotify: {
        title: "Spotify",
        steps: [
          "Open the Spotify developer dashboard and log in.",
          "Create an app: any name and description will do.",
          "Paste this exact redirect URI into the app settings:",
          "Tick the Web API box, save, then copy Client ID and Client Secret here.",
          "Save, test, then press Connect account to authorise your own account.",
        ],
        note: "Spotify rejects `localhost`: it only accepts the loopback IP or an HTTPS address. Getting this wrong is the single most common setup failure.",
      },
      anthropic: {
        title: "Anthropic",
        steps: [
          "Open the Anthropic console and log in.",
          "Go to API keys and create a new key.",
          "Copy it here — it is shown only once.",
        ],
        note: "The account needs credit for the key to work. The AI only curates and explains: it never builds the tracklist and is never asked for BPM or key.",
      },
      discogs: {
        title: "Discogs",
        steps: [
          "Open your Discogs developer settings.",
          "Generate a personal access token (not an OAuth app).",
          "Paste it here.",
        ],
        note: "Optional. Digging works without a token at a lower rate limit; the token raises that limit and shows release covers.",
      },
      acoustid: {
        title: "AcoustID",
        steps: [
          "Register an application on acoustid.org to get an API key.",
          "Paste the key here.",
          "Make sure fpcalc is installed (step 1): the key alone is not enough.",
        ],
        note: "Used by Organize to identify a file from the sound itself, which gives the most reliable metadata match.",
      },
      slskd: {
        title: "slskd (Soulseek)",
        steps: [
          "Install and start slskd, then log in with your Soulseek account.",
          "Enter its URL below (for example http://localhost:5030).",
          "Set the folder where slskd writes completed downloads.",
          "If slskd requires an API key, paste it here too.",
        ],
        note: "slskd is a separate program with its own configuration file. Cratory only talks to it over HTTP.",
      },
    },
    slskdTitle: "Soulseek acquisition",
    slskdUrlLabel: "slskd URL",
    slskdDownloadDirLabel: "Download folder",
    slskdCheck: "Check daemon",
    slskdReachable: "Daemon reachable",
    slskdUnreachable: "Daemon unreachable",
    // Step 5
    summaryTitle: "You're set",
    summaryBody: "Here is what is on and what is off. Everything off can be switched on later from Settings.",
    summaryOn: "On",
    summaryOff: "Off",
  },
```

- [ ] **Step 4: Aggiungere la traduzione in `it.ts`**

Aggiungere in `frontend/lib/i18n/it.ts` la stessa sezione con le stesse chiavi (TypeScript fallisce se ne manca una):

```ts
  setup: {
    title: "Configurazione guidata",
    subtitle: "Sei passi per mettere Cratory in funzione. Ogni passo si può saltare.",
    stepOf: (n: number, total: number) => `Passo ${n} di ${total}`,
    next: "Avanti",
    back: "Indietro",
    skip: "Salta questo passo",
    skipAll: "Salta la configurazione",
    finish: "Entra nell'app",
    reopen: "Riapri la configurazione guidata",
    welcomeTitle: "Benvenuto in Cratory",
    welcomeBody: "Cratory importa le tue playlist di streaming, costruisce set DJ sulle tracce che possiedi, scava per trovare musica nuova e tiene in ordine la libreria. Questa procedura verifica cosa è installato, configura i servizi esterni e spiega come ottenere ogni chiave API. Niente qui è obbligatorio: salta quello che non ti serve e torna quando vuoi da Impostazioni.",
    languageLabel: "Lingua",
    prereqTitle: "Componenti esterni",
    prereqBody: "Cratory si appoggia a qualche programma che vive fuori dall'app. ffmpeg è l'unico davvero necessario; tutti gli altri, se mancano, spengono soltanto la funzione che li usa.",
    installButton: "Installa",
    installing: "Installazione in corso…",
    installDone: "Installato",
    installFailed: "Installazione fallita",
    installManual: "Installalo tu, poi premi Ricontrolla:",
    copyCommand: "Copia il comando",
    copied: "Copiato",
    recheck: "Ricontrolla",
    detected: (version: string) => `Trovato: ${version}`,
    notFound: "Non trovato",
    fromBundle: "Incluso nell'app",
    severityRequired: "Necessario",
    severityOptional: "Facoltativo",
    unlocksLabel: "Abilita:",
    components: {
      ffmpeg: "Decodifica audio. Senza, Cratory non può calcolare l'identità dei file, identificare i mix né estrarre l'audio da SoundCloud.",
      fpcalc: "Lo strumento di fingerprint di Chromaprint. Serve ad AcoustID per riconoscere un file dal suono.",
      "yt-dlp": "Legge le pagine di SoundCloud: import di playlist e like, e download per traccia.",
      essentia: "Analisi di BPM e tonalità dentro l'app, l'alternativa all'import da Rekordbox.",
      slskd: "Il demone Soulseek che scarica i file. Gira come programma separato.",
    },
    unlocks: {
      audio_hash: "identità dei file",
      shazam: "identificazione dei mix",
      soundcloud_download: "download da SoundCloud",
      soundcloud_import: "import da SoundCloud",
      acoustid_fingerprint: "fingerprint acustica",
      analysis_bpm_key: "analisi BPM/tonalità in-app",
      soulseek_download: "download da Soulseek",
      library_share: "condivisione della libreria",
    },
    libraryTitle: "La tua libreria",
    libraryBody: "La libreria è il disco: la cartella che Cratory indicizza è ciò che possiedi. Le playlist di streaming restano piste finché un file non le sostiene. Cratory legge questi file e non li modifica mai.",
    libraryRootLabel: "Cartella della libreria",
    archiveRootLabel: "Archivio delle scartate (facoltativo)",
    choose: "Scegli…",
    indexNow: "Indicizza ora",
    indexing: "Indicizzazione in corso…",
    indexDone: (n: number) => `${n} file indicizzati`,
    servicesTitle: "Servizi esterni",
    servicesBody: "Ogni servizio è facoltativo e accende una parte dell'app. Le chiavi restano su questa macchina, nel database di Cratory.",
    save: "Salva",
    saved: "Salvata",
    replace: "Sostituisci",
    configuredAs: (hint: string) => `configurata ${hint}`,
    testButton: "Prova",
    testing: "Verifica…",
    testOk: "Funziona",
    testKo: "Non funziona",
    testNotConfigured: "Non c'è ancora niente da provare",
    testNoToken: "Funziona senza token, con rate limit più basso",
    testFpcalcMissing: "Chiave salvata, ma manca fpcalc — torna al passo 1",
    testNetworkError: "Non è stato possibile raggiungere il provider",
    howTo: "Come ottenerla",
    openProvider: "Apri il provider",
    copyValue: "Copia",
    fieldLabels: {
      spotify_client_id: "Client ID",
      spotify_client_secret: "Client secret",
      ai_api_key: "Chiave API",
      discogs_token: "Personal access token",
      acoustid_api_key: "Chiave API",
      slskd_api_key: "Chiave API (facoltativa)",
    },
    guides: {
      spotify: {
        title: "Spotify",
        steps: [
          "Apri la dashboard sviluppatori di Spotify e accedi.",
          "Crea un'app: nome e descrizione sono liberi.",
          "Incolla nelle impostazioni dell'app esattamente questo redirect URI:",
          "Spunta la casella Web API, salva, poi copia qui Client ID e Client Secret.",
          "Salva, prova, e infine premi Connetti account per autorizzare il tuo account.",
        ],
        note: "Spotify rifiuta `localhost`: accetta solo l'IP di loopback o un indirizzo HTTPS. Sbagliare questo campo è di gran lunga l'errore più comune.",
      },
      anthropic: {
        title: "Anthropic",
        steps: [
          "Apri la console Anthropic e accedi.",
          "Vai in API keys e crea una chiave nuova.",
          "Copiala qui: viene mostrata una volta sola.",
        ],
        note: "Perché la chiave funzioni l'account deve avere credito. L'AI cura e spiega: non costruisce mai la scaletta e non le si chiedono mai BPM o tonalità.",
      },
      discogs: {
        title: "Discogs",
        steps: [
          "Apri le impostazioni sviluppatori del tuo account Discogs.",
          "Genera un personal access token (non un'app OAuth).",
          "Incollalo qui.",
        ],
        note: "Facoltativo. Il dig funziona anche senza token, con un rate limit più basso; il token lo alza e mostra le copertine.",
      },
      acoustid: {
        title: "AcoustID",
        steps: [
          "Registra un'applicazione su acoustid.org per ottenere una API key.",
          "Incolla qui la chiave.",
          "Assicurati che fpcalc sia installato (passo 1): la chiave da sola non basta.",
        ],
        note: "Lo usa Organize per riconoscere un file dal suono, che è il modo più affidabile di agganciare i metadati giusti.",
      },
      slskd: {
        title: "slskd (Soulseek)",
        steps: [
          "Installa e avvia slskd, poi accedi col tuo account Soulseek.",
          "Indica qui sotto il suo URL (per esempio http://localhost:5030).",
          "Imposta la cartella in cui slskd scrive i download completati.",
          "Se slskd richiede una API key, incolla anche quella.",
        ],
        note: "slskd è un programma separato, con un suo file di configurazione. Cratory ci parla soltanto via HTTP.",
      },
    },
    slskdTitle: "Acquisizione da Soulseek",
    slskdUrlLabel: "URL di slskd",
    slskdDownloadDirLabel: "Cartella dei download",
    slskdCheck: "Verifica il demone",
    slskdReachable: "Demone raggiungibile",
    slskdUnreachable: "Demone non raggiungibile",
    summaryTitle: "Tutto pronto",
    summaryBody: "Ecco cosa è acceso e cosa no. Tutto quello che è spento si può accendere più tardi da Impostazioni.",
    summaryOn: "Acceso",
    summaryOff: "Spento",
  },
```

- [ ] **Step 5: Verificare che i tipi combacino**

```bash
cd frontend && npx tsc --noEmit
```
Atteso: nessun errore. Se `it.ts` manca una chiave, TypeScript la segnala qui: aggiungerla.

```bash
cd frontend && npm run lint
```
Atteso: nessun errore.

- [ ] **Step 6: Commit**

```bash
git add frontend/lib/api/setup.ts frontend/lib/api.ts frontend/lib/api/types.ts frontend/lib/setup-services.ts frontend/lib/i18n/en.ts frontend/lib/i18n/it.ts
git commit -m "feat(setup): client API del wizard e dizionari i18n"
```

---

## Task 9: Componenti condivisi

**Files:**
- Create: `frontend/components/setup/credential-field.tsx`, `frontend/components/setup/service-guide.tsx`, `frontend/components/setup/service-card.tsx`, `frontend/components/setup/component-row.tsx`
- Test: `frontend/tests/credential-field.test.tsx` (vitest raccoglie solo `tests/**`)

**Interfaces:**
- Consumes: `patchConfigSettings`, `testCredential`, `SecretState`, `ProbeComponent`, `startInstall`, `getInstallStatus`, `SERVICE_FIELDS`, `TESTABLE`, `useT`.
- Produces:
  - `<CredentialField fieldKey={SecretKey} label={string} state={SecretState | undefined} onSaved={() => void} />`
  - `<ServiceGuide service={ServiceKey} copyValue={string | null} docsUrl={string} />`
  - `<ServiceCard service={ServiceKey} secrets={Record<SecretKey, SecretState>} redirectUri={string} docsUrl={string} onSaved={() => void} />`
  - `<ComponentRow c={ProbeComponent} onChanged={() => void} />`

- [ ] **Step 1: Scrivere il test che fallisce**

Creare `frontend/tests/credential-field.test.tsx`:

```tsx
import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { CredentialField } from "@/components/setup/credential-field";

// Il mock deve esporre OGNI export usato dal componente: vitest solleva
// "No 'errText' export is defined on the mock" al primo accesso mancante.
vi.mock("@/lib/api", async () => ({
  patchConfigSettings: vi.fn().mockResolvedValue({}),
  errText: (e: unknown) => String(e),
}));

const { patchConfigSettings } = await import("@/lib/api");

describe("CredentialField", () => {
  beforeEach(() => vi.clearAllMocks());

  it("non pre-riempie mai il campo con la chiave configurata", () => {
    render(
      <CredentialField
        fieldKey="ai_api_key"
        label="API key"
        state={{ configured: true, source: "db", hint: "••••a3f9" }}
        onSaved={() => {}}
      />,
    );
    // La chiave configurata si annuncia, ma non finisce dentro l'input.
    expect(screen.getByText(/a3f9/)).toBeTruthy();
    expect(screen.queryByRole("textbox")).toBeNull();
  });

  it("mostra il campo vuoto quando la chiave non è configurata", () => {
    render(
      <CredentialField
        fieldKey="ai_api_key"
        label="API key"
        state={{ configured: false, source: "env", hint: null }}
        onSaved={() => {}}
      />,
    );
    expect((screen.getByRole("textbox") as HTMLInputElement).value).toBe("");
  });

  it("salva il valore digitato e avvisa il chiamante", async () => {
    const onSaved = vi.fn();
    render(
      <CredentialField
        fieldKey="discogs_token"
        label="Token"
        state={{ configured: false, source: "env", hint: null }}
        onSaved={onSaved}
      />,
    );
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "tok-123" } });
    fireEvent.click(screen.getByRole("button", { name: /salva|save/i }));
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    expect(patchConfigSettings).toHaveBeenCalledWith({ discogs_token: "tok-123" });
  });
});
```

- [ ] **Step 2: Eseguire il test e verificare che fallisca**

```bash
cd frontend && npm run test:unit -- tests/credential-field.test.tsx
```
Atteso: FAIL — il modulo `../credential-field` non esiste.

- [ ] **Step 3: Implementare `CredentialField`**

Creare `frontend/components/setup/credential-field.tsx`:

```tsx
"use client";

import { useState } from "react";
import { patchConfigSettings, errText, type SecretKey, type SecretState } from "@/lib/api";
import { Button, Input } from "@/components/ui";
import { useT } from "@/lib/i18n";

/* Un campo credenziale. Non pre-riempie MAI l'input: il backend non manda il
   valore, e mostrare un finto valore mascherato dentro un campo editabile
   farebbe credere di poterlo leggere. Chiave presente = riga di stato + link
   "sostituisci"; chiave assente = input vuoto. */
export function CredentialField({ fieldKey, label, state, onSaved }: {
  fieldKey: SecretKey;
  label: string;
  state: SecretState | undefined;
  onSaved: () => void;
}) {
  const t = useT();
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const configured = state?.configured ?? false;

  const save = async () => {
    setSaving(true);
    setError(null);
    try {
      await patchConfigSettings({ [fieldKey]: value });
      setValue("");
      setEditing(false);
      onSaved();
    } catch (e) {
      setError(errText(e));
    } finally {
      setSaving(false);
    }
  };

  if (configured && !editing) {
    return (
      <div className="flex flex-wrap items-center gap-2 py-1.5">
        <span className="text-xs uppercase tracking-wider text-muted">{label}</span>
        <span className="text-xs text-fg-strong">{t.setup.configuredAs(state?.hint ?? "")}</span>
        <button
          type="button"
          onClick={() => setEditing(true)}
          className="text-xs text-fg underline-offset-4 hover:underline"
        >
          {t.setup.replace}
        </button>
      </div>
    );
  }

  return (
    <div className="py-1.5">
      <label className="mb-1 block text-xs uppercase tracking-wider text-muted">{label}</label>
      <div className="flex gap-2">
        <Input
          value={value}
          onChange={(e) => setValue(e.target.value)}
          autoComplete="off"
          spellCheck={false}
          className="flex-1"
        />
        <Button size="sm" variant="outline" disabled={saving || !value.trim()} onClick={save}>
          {t.setup.save}
        </Button>
      </div>
      {error && <p className="mt-1 text-xs text-danger">{error}</p>}
    </div>
  );
}
```

- [ ] **Step 4: Eseguire il test e verificare che passi**

```bash
cd frontend && npm run test:unit -- tests/credential-field.test.tsx
```
Atteso: `3 passed`.

- [ ] **Step 5: Implementare `ServiceGuide`**

Creare `frontend/components/setup/service-guide.tsx`:

```tsx
"use client";

import { useState } from "react";
import { Check, Copy, ExternalLink } from "lucide-react";
import { Button } from "@/components/ui";
import { useT } from "@/lib/i18n";
import type { ServiceKey } from "@/lib/setup-services";

/* La guida "come si attiva questa API": passi numerati, link al provider e,
   dove serve, un valore da copiare incastonato nel passo che lo richiede
   (il redirect URI di Spotify sta nel terzo passo, non in fondo). */
export function ServiceGuide({ service, copyValue, docsUrl, copyAfterStep = 2 }: {
  service: ServiceKey;
  copyValue?: string | null;
  docsUrl: string;
  copyAfterStep?: number;
}) {
  const t = useT();
  const [copied, setCopied] = useState(false);
  const guide = t.setup.guides[service];

  const copy = async () => {
    if (!copyValue) return;
    await navigator.clipboard.writeText(copyValue);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  return (
    <div className="border border-border bg-bg p-4">
      <div className="mb-2 flex items-center justify-between gap-3">
        <span className="text-[10px] uppercase tracking-wider text-muted">{t.setup.howTo}</span>
        <a href={docsUrl} target="_blank" rel="noreferrer">
          <Button size="sm" variant="ghost">
            <ExternalLink size={14} /> {t.setup.openProvider}
          </Button>
        </a>
      </div>
      <ol className="space-y-1.5">
        {guide.steps.map((step, i) => (
          <li key={i}>
            <p className="flex gap-2 text-sm text-muted">
              <span className="tnum text-faint">{String(i + 1).padStart(2, "0")}</span>
              <span>{step}</span>
            </p>
            {copyValue && i === copyAfterStep && (
              <div className="ml-7 mt-1.5 flex items-center gap-2">
                <code className="flex-1 break-all bg-elevated px-2 py-1 text-xs text-fg">{copyValue}</code>
                <Button size="sm" variant="outline" onClick={copy}>
                  {copied ? <Check size={14} /> : <Copy size={14} />}
                  {copied ? t.setup.copied : t.setup.copyValue}
                </Button>
              </div>
            )}
          </li>
        ))}
      </ol>
      <p className="mt-3 border-l-2 border-border pl-3 text-xs text-faint">{guide.note}</p>
    </div>
  );
}
```

- [ ] **Step 6: Implementare `ServiceCard`**

Creare `frontend/components/setup/service-card.tsx`:

```tsx
"use client";

import { useState, type ReactNode } from "react";
import { errText, testCredential, type CredentialTestResult, type SecretKey, type SecretState } from "@/lib/api";
import { Button } from "@/components/ui";
import { useT, type Dictionary } from "@/lib/i18n";
import { SERVICE_FIELDS, TESTABLE, type ServiceKey } from "@/lib/setup-services";
import { CredentialField } from "./credential-field";
import { ServiceGuide } from "./service-guide";

/* Guida + campi + prova. È l'unità condivisa fra il wizard (dove sta dentro un
   passo, in sequenza) e Impostazioni (dove sta dentro una riga espandibile):
   una sola implementazione, due inquadrature. */

function esitoTesto(res: CredentialTestResult, t: Dictionary): string {
  if (res.code === "no_token") return t.setup.testNoToken;
  if (res.code === "not_configured") return t.setup.testNotConfigured;
  if (res.code === "fpcalc_missing") return t.setup.testFpcalcMissing;
  if (res.code === "network_error") return `${t.setup.testNetworkError} — ${res.detail}`;
  if (res.ok) return res.detail ? `${t.setup.testOk} — ${res.detail}` : t.setup.testOk;
  return `${t.setup.testKo} — ${res.detail}`;
}

export function ServiceCard({ service, secrets, redirectUri, docsUrl, onSaved, children }: {
  service: ServiceKey;
  secrets: Record<SecretKey, SecretState> | undefined;
  redirectUri?: string | null;
  docsUrl: string;
  onSaved: () => void;
  children?: ReactNode;
}) {
  const t = useT();
  const [result, setResult] = useState<CredentialTestResult | null>(null);
  const [testing, setTesting] = useState(false);

  const runTest = async () => {
    setTesting(true);
    try {
      setResult(await testCredential(service));
    } catch (e) {
      setResult({ ok: false, code: "network_error", detail: errText(e) });
    } finally {
      setTesting(false);
    }
  };

  return (
    <div className="space-y-3">
      <ServiceGuide
        service={service}
        docsUrl={docsUrl}
        copyValue={service === "spotify" ? redirectUri : null}
      />
      <div>
        {SERVICE_FIELDS[service].map((key) => (
          <CredentialField
            key={key}
            fieldKey={key}
            label={t.setup.fieldLabels[key]}
            state={secrets?.[key]}
            onSaved={onSaved}
          />
        ))}
      </div>
      {children}
      {TESTABLE.includes(service) && (
        <div className="flex flex-wrap items-center gap-3">
          <Button size="sm" variant="outline" disabled={testing} onClick={runTest}>
            {testing ? t.setup.testing : t.setup.testButton}
          </Button>
          {result && (
            <span className={`text-xs ${result.ok ? "text-fg-strong" : "text-danger"}`}>
              {esitoTesto(result, t)}
            </span>
          )}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 7: Implementare `ComponentRow`**

Creare `frontend/components/setup/component-row.tsx`:

```tsx
"use client";

import { useEffect, useRef, useState } from "react";
import { Check, Copy } from "lucide-react";
import { errText, getInstallStatus, startInstall, type InstallStatus, type ProbeComponent } from "@/lib/api";
import { Button } from "@/components/ui";
import { useT } from "@/lib/i18n";

/* Una riga del probe. I componenti auto-installabili hanno il bottone; gli
   altri mostrano il comando da eseguire a mano, con copia. */
export function ComponentRow({ c, onChanged }: { c: ProbeComponent; onChanged: () => void }) {
  const t = useT();
  const [install, setInstall] = useState<InstallStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => () => { if (timer.current) clearInterval(timer.current); }, []);

  const run = async () => {
    setError(null);
    try {
      setInstall(await startInstall(c.key));
    } catch (e) {
      setError(errText(e));
      return;
    }
    timer.current = setInterval(async () => {
      const st = await getInstallStatus();
      setInstall(st);
      if (st.status !== "running") {
        if (timer.current) clearInterval(timer.current);
        onChanged();
      }
    }, 1000);
  };

  const copy = async () => {
    if (!c.install_command) return;
    await navigator.clipboard.writeText(c.install_command.join(" "));
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  const running = install?.status === "running" && install.key === c.key;
  const label = t.setup.components[c.key as keyof typeof t.setup.components] ?? c.key;

  return (
    <div className="border-b border-border p-4 last:border-0">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-baseline gap-x-2">
            <span className="text-sm font-semibold uppercase tracking-wide text-fg-strong">{c.key}</span>
            <span className="text-[10px] uppercase tracking-wider text-faint">
              {c.severity === "required" ? t.setup.severityRequired : t.setup.severityOptional}
            </span>
          </div>
          <p className="mt-1 text-sm text-muted">{label}</p>
          <p className="mt-1 text-xs text-faint">
            {t.setup.unlocksLabel}{" "}
            {c.unlocks.map((u) => t.setup.unlocks[u as keyof typeof t.setup.unlocks] ?? u).join(", ")}
          </p>
        </div>
        <div className="shrink-0 text-right">
          <div className={`text-[10px] uppercase tracking-wider ${c.present ? "text-fg-strong" : "text-muted"}`}>
            {c.present ? (c.version ? t.setup.detected(c.version) : t.setup.installDone) : t.setup.notFound}
          </div>
          {c.source === "bundle" && <div className="text-[10px] text-faint">{t.setup.fromBundle}</div>}
        </div>
      </div>

      {!c.present && c.auto_installable && (
        <div className="mt-3">
          <Button size="sm" variant="outline" disabled={running} onClick={run}>
            {running ? t.setup.installing : t.setup.installButton}
          </Button>
          {install && install.key === c.key && install.log.length > 0 && (
            <pre className="mt-2 max-h-40 overflow-auto bg-elevated p-2 text-[11px] leading-snug text-muted">
              {install.log.join("\n")}
            </pre>
          )}
          {install?.status === "error" && (
            <p className="mt-1 text-xs text-danger">{t.setup.installFailed} — {install.detail}</p>
          )}
          {error && <p className="mt-1 text-xs text-danger">{error}</p>}
        </div>
      )}

      {!c.present && !c.auto_installable && c.install_command && (
        <div className="mt-3">
          <p className="mb-1 text-xs text-muted">{t.setup.installManual}</p>
          <div className="flex items-center gap-2">
            <code className="flex-1 break-all bg-elevated px-2 py-1 text-xs text-fg">
              {c.install_command.join(" ")}
            </code>
            <Button size="sm" variant="outline" onClick={copy}>
              {copied ? <Check size={14} /> : <Copy size={14} />}
              {copied ? t.setup.copied : t.setup.copyCommand}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 8: Verificare lint e tipi**

```bash
cd frontend && npx tsc --noEmit && npm run lint
```
Atteso: nessun errore. Se `text-danger` non è una classe del design system, sostituirla con quella usata da `Alert tone="danger"` (leggere `frontend/components/ui.tsx`).

- [ ] **Step 9: Commit**

```bash
git add frontend/components/setup
git commit -m "feat(setup): componenti condivisi campo-chiave, guida e riga componente"
```

---

## Task 10: Rotta `/setup`, shell e gate

**Files:**
- Create: `frontend/app/setup/page.tsx`, `frontend/components/setup/setup-gate.tsx`, `frontend/components/shell-switch.tsx`, `frontend/components/setup/steps/welcome.tsx`, `frontend/components/setup/steps/summary.tsx`
- Modify: `frontend/app/layout.tsx`
- Test: `frontend/tests/setup-gate.test.tsx` (vitest raccoglie solo `tests/**`)

**Interfaces:**
- Consumes: `getSetupState`, `setSetupCompleted`, `servicesStatus`, `getProbe`, `usePathname`/`useRouter` di `next/navigation`.
- Produces: rotta `/setup`; `<SetupGate />`; `<ShellSwitch>{children}</ShellSwitch>`; `<WelcomeStep />`, `<SummaryStep />`.

**Prima di scrivere:** leggere la guida di routing in `frontend/node_modules/next/dist/docs/` (App Router, client components, `useRouter`). Next 16 differisce dalle versioni note.

- [ ] **Step 1: Scrivere il test che fallisce**

Creare `frontend/tests/setup-gate.test.tsx`:

```tsx
import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, waitFor } from "@testing-library/react";

const replace = vi.fn();
let pathname = "/";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace }),
  usePathname: () => pathname,
}));

const getSetupState = vi.fn();
vi.mock("@/lib/api", () => ({ getSetupState: (...a: unknown[]) => getSetupState(...a) }));

const { SetupGate } = await import("@/components/setup/setup-gate");

describe("SetupGate", () => {
  beforeEach(() => { replace.mockClear(); getSetupState.mockReset(); pathname = "/"; });

  it("porta al wizard al primo avvio", async () => {
    getSetupState.mockResolvedValue({ completed: false });
    render(<SetupGate />);
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/setup"));
  });

  it("non fa nulla se il wizard è già stato completato", async () => {
    getSetupState.mockResolvedValue({ completed: true });
    render(<SetupGate />);
    await waitFor(() => expect(getSetupState).toHaveBeenCalled());
    expect(replace).not.toHaveBeenCalled();
  });

  it("non reindirizza se si è già sul wizard", async () => {
    pathname = "/setup";
    getSetupState.mockResolvedValue({ completed: false });
    render(<SetupGate />);
    await waitFor(() => expect(getSetupState).toHaveBeenCalled());
    expect(replace).not.toHaveBeenCalled();
  });

  it("col backend giù non manda in un wizard che non può funzionare", async () => {
    getSetupState.mockRejectedValue(new Error("fetch failed"));
    render(<SetupGate />);
    await waitFor(() => expect(getSetupState).toHaveBeenCalled());
    expect(replace).not.toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Eseguire il test e verificare che fallisca**

```bash
cd frontend && npm run test:unit -- tests/setup-gate.test.tsx
```
Atteso: FAIL — `../setup-gate` non esiste.

- [ ] **Step 3: Implementare il gate**

Creare `frontend/components/setup/setup-gate.tsx`:

```tsx
"use client";

import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";
import { getSetupState } from "@/lib/api";

/* Al primo avvio porta al wizard. Reindirizza SOLO su risposta riuscita: col
   backend giù l'utente finirebbe in una procedura che non può funzionare, e
   quel caso ha già il suo messaggio in dashboard. */
export function SetupGate() {
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (pathname === "/setup") return;
    let annullato = false;
    getSetupState()
      .then(({ completed }) => {
        if (!annullato && !completed) router.replace("/setup");
      })
      .catch(() => { /* backend giù: si resta dove si è */ });
    return () => { annullato = true; };
  }, [pathname, router]);

  return null;
}
```

- [ ] **Step 4: Eseguire il test e verificare che passi**

```bash
cd frontend && npm run test:unit -- tests/setup-gate.test.tsx
```
Atteso: `4 passed`.

- [ ] **Step 5: Implementare `ShellSwitch` e montarlo**

Creare `frontend/components/shell-switch.tsx`:

```tsx
"use client";

import type { ReactNode } from "react";
import { usePathname } from "next/navigation";
import { EditorialShell } from "./editorial-shell";

/* Il wizard è a schermo intero: niente indice laterale. I children restano
   renderizzati dal server — qui si sceglie soltanto la cornice. */
export function ShellSwitch({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  if (pathname === "/setup") return <main className="min-h-screen">{children}</main>;
  return <EditorialShell>{children}</EditorialShell>;
}
```

In `frontend/app/layout.tsx`, sostituire l'uso di `EditorialShell` e aggiungere il gate:

```tsx
import { ShellSwitch } from "@/components/shell-switch";
import { SetupGate } from "@/components/setup/setup-gate";
```
```tsx
        <I18nProvider>
          <PlayerProvider>
            <SetupGate />
            <ShellSwitch>{children}</ShellSwitch>
            <DockedPlayer />
          </PlayerProvider>
        </I18nProvider>
```

- [ ] **Step 6: Implementare la pagina e i due passi estremi**

Creare `frontend/components/setup/steps/welcome.tsx`:

```tsx
"use client";

import { useI18n, useT } from "@/lib/i18n";
import { cn } from "@/lib/cn";

export function WelcomeStep() {
  const t = useT();
  const { lang, setLang } = useI18n();
  return (
    <div className="space-y-6">
      <p className="text-sm leading-relaxed text-muted">{t.setup.welcomeBody}</p>
      <div>
        <div className="mb-2 text-[10px] uppercase tracking-wider text-muted">{t.setup.languageLabel}</div>
        <div role="group" className="inline-flex border border-border bg-surface p-1">
          {(["it", "en"] as const).map((code) => (
            <button
              key={code}
              type="button"
              aria-pressed={lang === code}
              onClick={() => setLang(code)}
              className={cn("px-3 py-1 text-xs font-medium uppercase tracking-wider transition-colors",
                lang === code ? "bg-elevated text-fg" : "text-muted hover:text-fg")}
            >
              {code}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
```

Creare `frontend/components/setup/steps/summary.tsx`:

```tsx
"use client";

import { useEffect, useState } from "react";
import { getProbe, servicesStatus, type ProbeComponent, type ServiceStatus } from "@/lib/api";
import { Loading } from "@/components/ui";
import { useT } from "@/lib/i18n";

/* Il riepilogo non è decorativo: è l'elenco di cosa resta spento e perché,
   che è la domanda che l'utente si farà al primo uso. */
export function SummaryStep() {
  const t = useT();
  const [components, setComponents] = useState<ProbeComponent[] | null>(null);
  const [services, setServices] = useState<ServiceStatus[] | null>(null);

  useEffect(() => {
    getProbe(true).then((r) => setComponents(r.components)).catch(() => setComponents([]));
    servicesStatus().then((r) => setServices(r.services)).catch(() => setServices([]));
  }, []);

  if (!components || !services) return <Loading />;

  const righe = [
    ...components.map((c) => ({ key: c.key, on: c.present })),
    ...services.map((s) => ({ key: s.name, on: s.configured })),
  ];

  return (
    <div className="space-y-4">
      <p className="text-sm leading-relaxed text-muted">{t.setup.summaryBody}</p>
      <div className="border border-border">
        {righe.map((r) => (
          <div key={r.key} className="flex items-center justify-between border-b border-border px-4 py-2 last:border-0">
            <span className="text-sm text-fg">{r.key}</span>
            <span className={`text-[10px] uppercase tracking-wider ${r.on ? "text-fg-strong" : "text-muted"}`}>
              {r.on ? t.setup.summaryOn : t.setup.summaryOff}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
```

Creare `frontend/app/setup/page.tsx`:

```tsx
"use client";

import { useCallback, useState } from "react";
import { useRouter } from "next/navigation";
import { setSetupCompleted } from "@/lib/api";
import { Button } from "@/components/ui";
import { useT } from "@/lib/i18n";
import { WelcomeStep } from "@/components/setup/steps/welcome";
import { SummaryStep } from "@/components/setup/steps/summary";

/* Configurazione guidata: sei passi, nessuno bloccante. Lo stato di
   completamento vive nel backend (AppState), non in localStorage: è una
   proprietà dell'installazione, non del browser. */
const STEPS = ["welcome", "prerequisites", "library", "services", "slskd", "summary"] as const;

export default function SetupPage() {
  const t = useT();
  const router = useRouter();
  const [index, setIndex] = useState(0);
  const step = STEPS[index];

  const esci = useCallback(async () => {
    try {
      await setSetupCompleted(true);
    } finally {
      router.replace("/");
    }
  }, [router]);

  const titolo: Record<(typeof STEPS)[number], string> = {
    welcome: t.setup.welcomeTitle,
    prerequisites: t.setup.prereqTitle,
    library: t.setup.libraryTitle,
    services: t.setup.servicesTitle,
    slskd: t.setup.slskdTitle,
    summary: t.setup.summaryTitle,
  };

  return (
    <div className="mx-auto flex min-h-screen max-w-3xl flex-col px-6 py-10">
      <header className="mb-8">
        <div className="flex items-baseline justify-between gap-4">
          <h1 className="text-lg font-semibold uppercase tracking-wide text-fg-strong">{t.setup.title}</h1>
          <span className="tnum text-xs text-faint">{t.setup.stepOf(index + 1, STEPS.length)}</span>
        </div>
        <p className="mt-1 text-sm text-muted">{t.setup.subtitle}</p>
      </header>

      <h2 className="mb-4 text-sm font-semibold uppercase tracking-wide text-fg-strong">{titolo[step]}</h2>

      <div className="flex-1">
        {step === "welcome" && <WelcomeStep />}
        {step === "summary" && <SummaryStep />}
      </div>

      <footer className="mt-10 flex items-center justify-between gap-4 border-t border-border pt-5">
        <button type="button" onClick={esci} className="text-xs text-muted underline-offset-4 hover:underline">
          {t.setup.skipAll}
        </button>
        <div className="flex gap-2">
          {index > 0 && (
            <Button size="sm" variant="ghost" onClick={() => setIndex((i) => i - 1)}>{t.setup.back}</Button>
          )}
          {index < STEPS.length - 1 ? (
            <Button size="sm" variant="outline" onClick={() => setIndex((i) => i + 1)}>{t.setup.next}</Button>
          ) : (
            <Button size="sm" onClick={esci}>{t.setup.finish}</Button>
          )}
        </div>
      </footer>
    </div>
  );
}
```

I passi 1, 2, 3 e 4 restano vuoti fino ai Task 11 e 12: la navigazione e l'uscita sono già verificabili.

- [ ] **Step 7: Verificare**

```bash
cd frontend && npm run test:unit && npx tsc --noEmit && npm run lint
```
Atteso: tutto verde.

- [ ] **Step 8: Commit**

```bash
git add frontend/app/setup frontend/app/layout.tsx frontend/components/shell-switch.tsx frontend/components/setup
git commit -m "feat(setup): rotta /setup a schermo intero, gate del primo avvio"
```

---

## Task 11: Passi prerequisiti e libreria

**Files:**
- Create: `frontend/components/setup/steps/prerequisites.tsx`, `frontend/components/setup/path-field.tsx`, `frontend/components/setup/steps/library.tsx`
- Modify: `frontend/app/setup/page.tsx`

**Interfaces:**
- Consumes: `getProbe`, `ComponentRow`, `getConfigSettings`, `patchConfigSettings`, `pickerAvailability`, `pickPath`, `startLibraryIndex`, `libraryIndexStatus` (tutte funzioni già esistenti del client — non riscriverle).
- Produces: `<PrerequisitesStep />`, `<LibraryStep />`, e
  `<PathField fieldKey={"library_root"|"archive_root"|"slskd_download_dir"|"slskd_url"} label={string} value={string} detail={string | null} canPick={boolean} kind={"folder"|"text"} onSaved={(c: ConfigSettings) => void} />`.

**PathField è condiviso:** il Task 12 lo riusa per i campi di slskd. Va scritto una volta sola qui.

- [ ] **Step 1: Implementare il passo prerequisiti**

Creare `frontend/components/setup/steps/prerequisites.tsx`:

```tsx
"use client";

import { useCallback, useEffect, useState } from "react";
import { errText, getProbe, type ProbeComponent } from "@/lib/api";
import { Alert, Button, Loading } from "@/components/ui";
import { useT } from "@/lib/i18n";
import { ComponentRow } from "../component-row";

export function PrerequisitesStep() {
  const t = useT();
  const [components, setComponents] = useState<ProbeComponent[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback((force = false) => {
    getProbe(force)
      .then((r) => { setComponents(r.components); setError(null); })
      .catch((e) => setError(errText(e)));
  }, []);

  useEffect(() => load(), [load]);

  return (
    <div className="space-y-4">
      <p className="text-sm leading-relaxed text-muted">{t.setup.prereqBody}</p>
      {error && <Alert tone="danger">{error}</Alert>}
      {components ? (
        <>
          <div className="border border-border">
            {components.map((c) => (
              <ComponentRow key={c.key} c={c} onChanged={() => load(true)} />
            ))}
          </div>
          <Button size="sm" variant="ghost" onClick={() => load(true)}>{t.setup.recheck}</Button>
        </>
      ) : (
        !error && <Loading />
      )}
    </div>
  );
}
```

- [ ] **Step 2: Estrarre `PathField`**

Il pattern "campo + bottone Scegli + salva" serve al passo libreria (due volte) e al passo slskd (due volte): va scritto una volta sola. Creare `frontend/components/setup/path-field.tsx`:

```tsx
"use client";

import { useState } from "react";
import {
  errText, patchConfigSettings, pickPath, type ConfigSettings,
} from "@/lib/api";
import { Button, Input } from "@/components/ui";
import { useT } from "@/lib/i18n";

/* Campo di configurazione in chiaro (percorso o URL), con il dialog nativo
   dove è disponibile. Salva sul blur: un bottone Salva per campo, in una
   procedura a passi, aggiunge un gesto senza aggiungere informazione.
   Condiviso fra il passo libreria e il passo slskd. */
export type PathFieldKey = "library_root" | "archive_root" | "slskd_download_dir" | "slskd_url";

export function PathField({ fieldKey, label, value, detail, canPick, kind = "folder", onSaved }: {
  fieldKey: PathFieldKey;
  label: string;
  value: string;
  detail?: string | null;
  canPick: boolean;
  kind?: "folder" | "text";
  onSaved: (config: ConfigSettings) => void;
}) {
  const t = useT();
  const [error, setError] = useState<string | null>(null);

  const salva = async (next: string) => {
    if (next === value) return; // niente PATCH inutili a ogni blur
    try {
      onSaved(await patchConfigSettings({ [fieldKey]: next }));
      setError(null);
    } catch (e) {
      setError(errText(e));
    }
  };

  const scegli = async () => {
    const { path } = await pickPath("folder", value || undefined);
    if (path) await salva(path);
  };

  return (
    <div>
      <label className="mb-1 block text-xs uppercase tracking-wider text-muted">{label}</label>
      <div className="flex gap-2">
        <Input
          defaultValue={value}
          onBlur={(e) => salva(e.target.value.trim())}
          className="flex-1"
        />
        {kind === "folder" && canPick && (
          <Button size="sm" variant="outline" onClick={scegli}>{t.setup.choose}</Button>
        )}
      </div>
      {detail && <p className="mt-1 text-xs text-faint">{detail}</p>}
      {error && <p className="mt-1 text-xs text-danger">{error}</p>}
    </div>
  );
}
```

- [ ] **Step 3: Implementare il passo libreria**

Creare `frontend/components/setup/steps/library.tsx`, montando due `PathField` e l'azione di indicizzazione.

```tsx
"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  errText, getConfigSettings, libraryIndexStatus, pickerAvailability, startLibraryIndex,
  type ConfigSettings, type LibraryIndexJob,
} from "@/lib/api";
import { Alert, Button, Loading } from "@/components/ui";
import { useT } from "@/lib/i18n";
import { PathField } from "../path-field";

export function LibraryStep() {
  const t = useT();
  const [config, setConfig] = useState<ConfigSettings | null>(null);
  const [canPick, setCanPick] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    getConfigSettings().then(setConfig).catch((e) => setError(errText(e)));
  }, []);

  useEffect(() => {
    load();
    pickerAvailability().then((r) => setCanPick(r.available)).catch(() => setCanPick(false));
  }, [load]);

  if (!config) return error ? <Alert tone="danger">{error}</Alert> : <Loading />;

  return (
    <div className="space-y-4">
      <p className="text-sm leading-relaxed text-muted">{t.setup.libraryBody}</p>
      {error && <Alert tone="danger">{error}</Alert>}
      <PathField
        fieldKey="library_root"
        label={t.setup.libraryRootLabel}
        value={config.library_root.value}
        detail={config.library_root.detail}
        canPick={canPick}
        onSaved={setConfig}
      />
      <PathField
        fieldKey="archive_root"
        label={t.setup.archiveRootLabel}
        value={config.archive_root.value}
        detail={config.archive_root.detail}
        canPick={canPick}
        onSaved={setConfig}
      />
      <IndexAction disabled={!config.library_root.value} />
    </div>
  );
}
```

`IndexAction` va nello stesso file. Il polling è locale al componente **di proposito**: `JobsProvider`, che nel resto dell'app segue i job in corso, vive dentro `EditorialShell`, e su `/setup` la shell è scavalcata — quindi lì non esiste. Le funzioni del client (`startLibraryIndex`, `libraryIndexStatus`) sono quelle già in uso, non se ne creano di nuove:

```tsx
function IndexAction({ disabled }: { disabled: boolean }) {
  const t = useT();
  const [job, setJob] = useState<LibraryIndexJob | null>(null);
  const [error, setError] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => () => { if (timer.current) clearInterval(timer.current); }, []);

  const avvia = async () => {
    setError(null);
    try {
      setJob(await startLibraryIndex());
    } catch (e) {
      setError(errText(e));
      return;
    }
    timer.current = setInterval(async () => {
      const st = await libraryIndexStatus();
      setJob(st);
      if (st.status !== "running" && timer.current) clearInterval(timer.current);
    }, 1000);
  };

  const running = job?.status === "running";
  return (
    <div className="space-y-2">
      <Button size="sm" variant="outline" disabled={disabled || running} onClick={avvia}>
        {running ? t.setup.indexing : t.setup.indexNow}
      </Button>
      {running && (
        <p className="tnum text-xs text-muted">{job.processed} / {job.total}</p>
      )}
      {job?.status === "done" && (
        <p className="text-xs text-fg-strong">{t.setup.indexDone(job.processed)}</p>
      )}
      {job?.status === "error" && <p className="text-xs text-danger">{job.error}</p>}
      {error && <p className="text-xs text-danger">{error}</p>}
    </div>
  );
}
```

- [ ] **Step 4: Montare i due passi nella pagina**

In `frontend/app/setup/page.tsx`, aggiungere gli import e le due righe:

```tsx
import { PrerequisitesStep } from "@/components/setup/steps/prerequisites";
import { LibraryStep } from "@/components/setup/steps/library";
```
```tsx
        {step === "prerequisites" && <PrerequisitesStep />}
        {step === "library" && <LibraryStep />}
```

- [ ] **Step 5: Verificare nel browser**

Avviare il preview (`preview_start`), navigare su `/setup`, controllare console e rete: il passo 1 elenca i cinque componenti col loro stato reale, il passo 2 mostra i percorsi correnti. Verificare che un "Ricontrolla" dopo un'installazione aggiorni lo stato.

```bash
cd frontend && npm run test:unit && npx tsc --noEmit && npm run lint
```

- [ ] **Step 6: Commit**

```bash
git add frontend/components/setup frontend/app/setup/page.tsx
git commit -m "feat(setup): passi prerequisiti e libreria"
```

---

## Task 12: Passi servizi e slskd

**Files:**
- Create: `frontend/components/setup/steps/services.tsx`, `frontend/components/setup/steps/slskd.tsx`
- Modify: `frontend/app/setup/page.tsx`

**Interfaces:**
- Consumes: `ServiceCard`, `getConfigSettings`, `patchConfigSettings`, `servicesStatus`, `SPOTIFY_LOGIN_URL`, `slskdStatus`.
- Produces: `<ServicesStep />`, `<SlskdStep />`.

- [ ] **Step 1: Implementare il passo servizi**

Creare `frontend/components/setup/steps/services.tsx`:

```tsx
"use client";

import { useCallback, useEffect, useState } from "react";
import { ExternalLink } from "lucide-react";
import {
  errText, getConfigSettings, servicesStatus, SPOTIFY_LOGIN_URL,
  type ConfigSettings, type ServiceStatus,
} from "@/lib/api";
import { Alert, Button, Loading } from "@/components/ui";
import { useT } from "@/lib/i18n";
import type { ServiceKey } from "@/lib/setup-services";
import { ServiceCard } from "../service-card";

const ORDINE: ServiceKey[] = ["spotify", "anthropic", "discogs", "acoustid"];

export function ServicesStep() {
  const t = useT();
  const [config, setConfig] = useState<ConfigSettings | null>(null);
  const [services, setServices] = useState<ServiceStatus[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    getConfigSettings().then(setConfig).catch((e) => setError(errText(e)));
    servicesStatus().then((r) => setServices(r.services)).catch(() => setServices([]));
  }, []);

  useEffect(() => load(), [load]);

  if (!config || !services) return error ? <Alert tone="danger">{error}</Alert> : <Loading />;

  const docs = (key: string) => services.find((s) => s.key === key)?.docs ?? "";

  return (
    <div className="space-y-8">
      <p className="text-sm leading-relaxed text-muted">{t.setup.servicesBody}</p>
      {error && <Alert tone="danger">{error}</Alert>}
      {ORDINE.map((service) => (
        <section key={service} className="space-y-3">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-fg-strong">
            {t.setup.guides[service].title}
          </h3>
          <ServiceCard
            service={service}
            secrets={config.secrets}
            redirectUri={config.spotify_redirect_uri}
            docsUrl={docs(service)}
            onSaved={load}
          >
            {service === "spotify" && config.secrets.spotify_client_id.configured && (
              <a href={SPOTIFY_LOGIN_URL}>
                <Button size="sm" variant="outline">
                  <ExternalLink size={14} /> {t.settings.connectButton}
                </Button>
              </a>
            )}
          </ServiceCard>
        </section>
      ))}
    </div>
  );
}
```

- [ ] **Step 2: Implementare il passo slskd**

Creare `frontend/components/setup/steps/slskd.tsx`:

```tsx
"use client";

import { useCallback, useEffect, useState } from "react";
import {
  errText, getConfigSettings, pickerAvailability, slskdStatus,
  type ConfigSettings, type SlskdStatus,
} from "@/lib/api";
import { Alert, Button, Loading } from "@/components/ui";
import { useT } from "@/lib/i18n";
import { ServiceGuide } from "../service-guide";
import { CredentialField } from "../credential-field";
import { PathField } from "../path-field";

export function SlskdStep() {
  const t = useT();
  const [config, setConfig] = useState<ConfigSettings | null>(null);
  const [status, setStatus] = useState<SlskdStatus | null>(null);
  const [canPick, setCanPick] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    getConfigSettings().then(setConfig).catch((e) => setError(errText(e)));
  }, []);

  useEffect(() => {
    load();
    pickerAvailability().then((r) => setCanPick(r.available)).catch(() => setCanPick(false));
  }, [load]);

  const verifica = async () => {
    try {
      setStatus(await slskdStatus());
    } catch (e) {
      setError(errText(e));
    }
  };

  if (!config) return error ? <Alert tone="danger">{error}</Alert> : <Loading />;

  return (
    <div className="space-y-4">
      <ServiceGuide service="slskd" docsUrl="https://github.com/slskd/slskd" copyValue={null} />
      {error && <Alert tone="danger">{error}</Alert>}

      <PathField
        fieldKey="slskd_url"
        label={t.setup.slskdUrlLabel}
        value={config.slskd_url.value}
        detail={config.slskd_url.detail}
        canPick={false}
        kind="text"
        onSaved={setConfig}
      />

      <PathField
        fieldKey="slskd_download_dir"
        label={t.setup.slskdDownloadDirLabel}
        value={config.slskd_download_dir.value}
        detail={config.slskd_download_dir.detail}
        canPick={canPick}
        onSaved={setConfig}
      />

      <CredentialField
        fieldKey="slskd_api_key"
        label={t.setup.fieldLabels.slskd_api_key}
        state={config.secrets.slskd_api_key}
        onSaved={load}
      />

      <div className="flex flex-wrap items-center gap-3">
        <Button size="sm" variant="outline" onClick={verifica}>{t.setup.slskdCheck}</Button>
        {status && (
          <span className={`text-xs ${status.reachable ? "text-fg-strong" : "text-danger"}`}>
            {status.reachable ? t.setup.slskdReachable : t.setup.slskdUnreachable}
          </span>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Montare i due passi**

In `frontend/app/setup/page.tsx`:

```tsx
import { ServicesStep } from "@/components/setup/steps/services";
import { SlskdStep } from "@/components/setup/steps/slskd";
```
```tsx
        {step === "services" && <ServicesStep />}
        {step === "slskd" && <SlskdStep />}
```

- [ ] **Step 4: Aggiungere la copertura e2e**

Creare `frontend/e2e/global-setup.ts`:

```ts
/* La suite gira su un DB che parte vuoto: senza questo, il SetupGate
   reindirizzerebbe ogni rotta dello smoke test al wizard. Il flag si scrive
   con l'API vera, non con una scorciatoia. */
export default async function globalSetup() {
  const res = await fetch("http://127.0.0.1:8211/api/setup/state", {
    method: "PUT",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ completed: true }),
  });
  if (!res.ok) throw new Error(`setup state non impostato: HTTP ${res.status}`);
}
```

In `frontend/playwright.config.ts`, aggiungere dentro `defineConfig`:

```ts
  globalSetup: "./e2e/global-setup.ts",
```

Creare `frontend/e2e/setup.spec.ts`:

```ts
import { expect, test } from "@playwright/test";

/* Il wizard raggiunto direttamente: i sei passi si attraversano e l'uscita
   riporta in dashboard. Il redirect automatico del primo avvio è coperto dal
   test unitario di SetupGate: qui il flag è già a "completato" per non far
   dirottare tutta la suite. */
test("il wizard si attraversa e si esce", async ({ page }) => {
  await page.goto("/setup");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();

  for (let i = 0; i < 5; i++) {
    await page.getByRole("button", { name: /avanti|next/i }).click();
  }
  await page.getByRole("button", { name: /entra nell'app|enter the app/i }).click();
  await expect(page).toHaveURL(/\/$/);
});

test("si può saltare del tutto", async ({ page }) => {
  await page.goto("/setup");
  await page.getByRole("button", { name: /salta la configurazione|skip setup/i }).click();
  await expect(page).toHaveURL(/\/$/);
});
```

In `frontend/e2e/smoke.spec.ts`, aggiungere all'elenco `ROUTES`:

```ts
  { path: "/setup", title: null },
```

- [ ] **Step 5: Eseguire i test**

```bash
cd frontend && npm run test:unit && npx tsc --noEmit && npm run lint
```
```bash
cd frontend && npm run test:e2e
```
Atteso: tutto verde. L'e2e richiede un `backend/.venv` nel worktree; se manca, crearlo o eseguire la suite dal checkout principale.

- [ ] **Step 6: Commit**

```bash
git add frontend/components/setup frontend/app/setup/page.tsx frontend/e2e frontend/playwright.config.ts
git commit -m "feat(setup): passi servizi e slskd, copertura e2e del wizard"
```

---

## Task 13: Integrazione in Impostazioni

**Files:**
- Modify: `frontend/components/settings/services-list.tsx`, `frontend/app/settings/page.tsx`

**Interfaces:**
- Consumes: `ServiceCard`, `getConfigSettings`, `setSetupCompleted`, `SERVICE_FIELDS`.
- Produces: nessuna API nuova. Ogni riga di `ServicesList` con credenziali diventa espandibile e monta `ServiceCard`; la pagina guadagna il bottone di riapertura del wizard.

- [ ] **Step 1: Rendere espandibili le righe**

In `frontend/components/settings/services-list.tsx`, aggiungere lo stato di espansione e il caricamento della config. Dentro `ServicesList`:

```tsx
  const [expanded, setExpanded] = useState<string | null>(null);
  const [config, setConfig] = useState<ConfigSettings | null>(null);
  const loadConfig = useCallback(() => {
    getConfigSettings().then(setConfig).catch(() => setConfig(null));
  }, []);
  useEffect(loadConfig, [loadConfig]);
```

Nella colonna delle azioni di ogni riga, per i servizi che hanno credenziali:

```tsx
              {SERVICE_FIELDS[s.key as ServiceKey] && (
                <Button size="sm" variant="ghost"
                        onClick={() => setExpanded(expanded === s.key ? null : s.key)}>
                  {expanded === s.key ? t.settings.collapseKeys : t.settings.editKeys}
                </Button>
              )}
```

e sotto il blocco delle `*Extra` già presenti:

```tsx
          {expanded === s.key && config && (
            <div className="mt-4 border-t border-border pt-4">
              <ServiceCard
                service={s.key as ServiceKey}
                secrets={config.secrets}
                redirectUri={config.spotify_redirect_uri}
                docsUrl={s.docs}
                onSaved={loadConfig}
              />
            </div>
          )}
```

Aggiungere a `en.ts` e `it.ts`, dentro `settings`, le due chiavi nuove:

```ts
    editKeys: "Edit keys",       // it: "Modifica le chiavi"
    collapseKeys: "Close",       // it: "Chiudi"
```

Il widget del redirect URI in `SpotifyExtra` resta dov'è: è la scorciatoia per chi non apre la guida, e la guida completa arriva solo espandendo.

- [ ] **Step 2: Aggiungere il bottone di riapertura**

In `frontend/app/settings/page.tsx`, sotto la lista dei servizi:

```tsx
      <div className="mt-4">
        <Button size="sm" variant="outline" onClick={async () => {
          await setSetupCompleted(false);
          router.push("/setup");
        }}>
          {t.setup.reopen}
        </Button>
      </div>
```

con `const router = useRouter();` e gli import corrispondenti (`useRouter` da `next/navigation`, `setSetupCompleted` e `Button` dai rispettivi moduli).

- [ ] **Step 3: Verificare nel browser**

Aprire `/settings`: ogni servizio con credenziali mostra "Modifica le chiavi", l'espansione monta guida + campi + Prova, il salvataggio aggiorna lo stato della riga senza ricaricare la pagina. Controllare console e rete.

```bash
cd frontend && npm run test:unit && npx tsc --noEmit && npm run lint
```

- [ ] **Step 4: Commit**

```bash
git add frontend/components/settings frontend/app/settings/page.tsx frontend/lib/i18n
git commit -m "feat(settings): chiavi API modificabili dalle righe dei servizi"
```

---

## Task 14: Documentazione

**Files:**
- Modify: `docs/API.md`, `docs/ARCHITECTURE.md`, `docs/ROADMAP.md`, `README.md`, `PROGRESS.md`

- [ ] **Step 1: `docs/API.md`**

Aggiungere la sezione del router `setup` (`GET|PUT /api/setup/state`, `GET /api/setup/probe`, `POST /api/setup/install/{key}`, `GET /api/setup/install/status`, `POST /api/setup/test/{service}`) con la forma delle risposte, e aggiornare la sezione `settings` con il blocco `secrets`, il campo `spotify_redirect_uri` e i campi nuovi del `PATCH`. Scrivere esplicitamente che il valore di una credenziale non compare mai in una risposta.

- [ ] **Step 2: `docs/ARCHITECTURE.md`**

Aggiungere `setup` all'elenco dei router e `system_probe`, `component_installer`, `credential_tests` fra i servizi. Documentare i due confini Tauri: `CRATORY_BIN_DIR` in `resolve_binary` e `run_recipe` come unico punto di esecuzione di processi esterni. Aggiornare la descrizione di `runtime_settings` (ora copre anche le credenziali).

- [ ] **Step 3: `docs/ROADMAP.md`**

Aggiungere alla sezione "Current state" un paragrafo sulla configurazione guidata. Rimuovere dal backlog l'annotazione su `ENV_BACKED_KEYS` se ce l'hai messa, dato che il Task 3 le ha dato un consumatore reale.

- [ ] **Step 4: `README.md`**

Il setup non è più "edita `backend/.env`": riscrivere la sezione di configurazione indicando che al primo avvio l'app apre `/setup`, che `.env` resta valido come default e che le chiavi impostate dal wizard hanno la precedenza.

- [ ] **Step 5: `PROGRESS.md`**

Una voce di sintesi con la data.

- [ ] **Step 6: Verifica finale**

```bash
cd backend && /Users/lucadenegri/Develop/DJProject01/backend/.venv/bin/python -m pytest tests -q
```
```bash
cd frontend && npm run test:unit && npm run lint && npm run build
```
Atteso: tutto verde. Riportare l'output reale, non una previsione.

- [ ] **Step 7: Commit**

```bash
git add docs README.md PROGRESS.md
git commit -m "docs(setup): documenta la configurazione guidata e i confini Tauri"
```
