# Settings Unificata Post-Fusione — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminare le ridondanze della pagina `/settings` (due liste provider, due chiavi AI, slskd in tre punti) unificando endpoint, semantica di stato e struttura della pagina in 4 gruppi.

**Architecture:** `GET /api/services/status` diventa l'unica fonte (7 voci, campi `optional_env`/`optional_ok` nuovi); `/api/organize/providers` viene rimosso; la chiave AI converge su `ANTHROPIC_API_KEY` (fallback `AI_API_KEY`). Il frontend passa a 4 gruppi (Generale / Percorsi e libreria / Servizi esterni / Organize) con le azioni inline sulle righe della lista servizi.

**Tech Stack:** FastAPI + Pydantic Settings (backend), Next.js 16 App Router + React + Tailwind (frontend), pytest, vitest + @testing-library/react.

**Spec:** `docs/superpowers/specs/2026-08-13-settings-unificata-design.md`

## Global Constraints

- Frontend: Next.js 16 ha breaking changes — leggere `frontend/CLAUDE.md` e, in caso di dubbi su API/routing, `node_modules/next/dist/docs/` prima di toccare pagine.
- Commit: MAI aggiungere `Co-Authored-By: Claude` nei messaggi (preferenza utente).
- Git: prima di ogni commit `git status --porcelain` e stagere SOLO i file del task (possibili sessioni parallele sullo stesso checkout); verificare di essere su `master`.
- Comandi backend: `cd backend && source .venv/bin/activate` poi `python -m pytest tests`.
- Comandi frontend: `cd frontend` poi `npm run lint` / `npm run build` / `npx vitest run tests/<file>`.
- La UI dei servizi mostra testi backend in italiano (comportamento esistente, invariato); le etichette di stato sono in `t.settings` (IT + EN sempre in coppia: `lib/i18n/it.ts` e `lib/i18n/en.ts`).
- Ogni asserzione di test va provata rompendo il codice almeno mentalmente: niente test che passano per il motivo sbagliato (regola utente).

---

### Task 1: Chiave AI unica nel backend

**Files:**
- Test (create): `backend/tests/test_ai_key_unificata.py`
- Modify: `backend/app/core/config.py:45`
- Modify: `backend/app/organize/services/ai_tags.py:6,35-36,45,360`
- Modify: `backend/app/routers/sets.py:106-107`
- Modify: `backend/app/integrations/llm.py:71`
- Modify: `backend/tests/organize/test_genre_review_api.py`, `backend/tests/organize/test_ai_suggest_api.py` (setenv → setattr)

**Interfaces:**
- Consumes: `app.core.config.settings` (esistente).
- Produces: `settings.ai_api_key` valorizzata da `ANTHROPIC_API_KEY` (precedenza) o `AI_API_KEY` (fallback); `ai_tags.is_configured()` e i client `Anthropic(...)` di `ai_tags` leggono `settings.ai_api_key` (non più `os.environ`). I task 2+ e i test usano `monkeypatch.setattr(settings, "ai_api_key", ...)`.

- [ ] **Step 1: Scrivere il test che fallisce**

Creare `backend/tests/test_ai_key_unificata.py`:

```python
"""La chiave AI e' una sola: ANTHROPIC_API_KEY, con fallback su AI_API_KEY
(retrocompatibilita' degli .env esistenti). Precedenza a ANTHROPIC_API_KEY."""

from app.core.config import Settings
from app.organize.services import ai_tags


def _fresh_settings(monkeypatch, **env):
    for k in ("ANTHROPIC_API_KEY", "AI_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    # _env_file=None: il test non deve leggere il backend/.env reale dello sviluppatore
    return Settings(_env_file=None)


def test_anthropic_api_key_letta(monkeypatch):
    assert _fresh_settings(monkeypatch, ANTHROPIC_API_KEY="nuova").ai_api_key == "nuova"


def test_fallback_su_ai_api_key(monkeypatch):
    assert _fresh_settings(monkeypatch, AI_API_KEY="vecchia").ai_api_key == "vecchia"


def test_precedenza_ad_anthropic(monkeypatch):
    s = _fresh_settings(monkeypatch, ANTHROPIC_API_KEY="nuova", AI_API_KEY="vecchia")
    assert s.ai_api_key == "nuova"


def test_senza_chiavi_vuota(monkeypatch):
    assert _fresh_settings(monkeypatch).ai_api_key == ""


def test_ai_tags_usa_il_setting_condiviso(monkeypatch):
    """is_configured() deve leggere settings.ai_api_key, non os.environ:
    altrimenti un .env con solo AI_API_KEY lascerebbe i tag AI spenti."""
    from app.core.config import settings
    monkeypatch.setattr(settings, "ai_api_key", "test")
    assert ai_tags.is_configured() is True
    monkeypatch.setattr(settings, "ai_api_key", "")
    assert ai_tags.is_configured() is False
```

- [ ] **Step 2: Eseguire il test e verificarne il fallimento**

Run: `python -m pytest tests/test_ai_key_unificata.py -v` (da `backend/`, venv attivo)
Expected: FAIL — `test_fallback_su_ai_api_key` e `test_anthropic_api_key_letta` falliscono (oggi il campo legge solo l'env `AI_API_KEY`); `test_ai_tags_usa_il_setting_condiviso` fallisce (oggi legge `os.environ`). NOTA: `test_anthropic_api_key_letta` oggi fallisce perché `ANTHROPIC_API_KEY` non è mappata sul campo.

- [ ] **Step 3: Implementare l'alias in config.py**

In `backend/app/core/config.py`, riga 5, estendere l'import pydantic:

```python
from pydantic import AliasChoices, Field, field_validator
```

Riga 45, sostituire `ai_api_key: str = ""` con:

```python
    # Chiave AI unica per tutta l'app (Set Agent + tag/generi di Organize).
    # ANTHROPIC_API_KEY e' il nome standard dell'SDK; AI_API_KEY resta letta
    # come fallback per gli .env scritti prima della fusione.
    ai_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("ANTHROPIC_API_KEY", "AI_API_KEY"),
    )
```

- [ ] **Step 4: Far leggere il setting ad ai_tags**

In `backend/app/organize/services/ai_tags.py`:

1. Rimuovere `import os` (riga 6) e aggiungere dopo gli import:

```python
from app.core.config import settings
```

2. Sostituire `is_configured` (righe 35-36) con:

```python
def is_configured() -> bool:
    return bool(settings.ai_api_key)
```

3. In `suggest()` (riga 45) sostituire `client = Anthropic()` con:

```python
    client = Anthropic(api_key=settings.ai_api_key)
```

4. In `review_genres()` (riga 360) sostituire `client = Anthropic()` con:

```python
    client = Anthropic(api_key=settings.ai_api_key)
```

(Motivo dei punti 3-4: `Anthropic()` senza argomenti legge SOLO l'env `ANTHROPIC_API_KEY`; con un .env che ha solo `AI_API_KEY` il client fallirebbe pur con `is_configured()` a True.)

- [ ] **Step 5: Aggiornare i messaggi d'errore**

`backend/app/routers/sets.py` righe 106-107, sostituire:

```python
        raise api_error(409, "ai_not_configured", "AI not configured: ANTHROPIC_API_KEY missing.",
                         reason="ANTHROPIC_API_KEY mancante")
```

`backend/app/integrations/llm.py` riga 71, sostituire la stringa del `LLMNotConfigured`:

```python
                "ANTHROPIC_API_KEY mancante in backend/.env: impostare la chiave API Anthropic "
```

- [ ] **Step 6: Migrare i test Organize da setenv a setattr**

I test che oggi attivano/disattivano l'AI via env non funzionano più (il fixture autouse `_no_real_llm` in `tests/conftest.py:90` azzera `settings.ai_api_key`, e `is_configured()` ora legge il setting). Sostituzioni:

In `backend/tests/organize/test_genre_review_api.py` (aggiungere `from app.core.config import settings` agli import se assente):
- riga 20: `monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)` → `monkeypatch.setattr(settings, "ai_api_key", "")`
- righe 34, 56, 67: `monkeypatch.setenv("ANTHROPIC_API_KEY", "test")` → `monkeypatch.setattr(settings, "ai_api_key", "test")`

In `backend/tests/organize/test_ai_suggest_api.py` (stesso import):
- righe 21, 46, 61: `monkeypatch.setenv("ANTHROPIC_API_KEY", "test")` → `monkeypatch.setattr(settings, "ai_api_key", "test")`
- riga 37: `monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)` → `monkeypatch.setattr(settings, "ai_api_key", "")`

- [ ] **Step 7: Eseguire i test e verificare che passino**

Run: `python -m pytest tests/test_ai_key_unificata.py tests/organize/test_genre_review_api.py tests/organize/test_ai_suggest_api.py tests/test_services_status.py -v`
Expected: PASS tutti. Poi l'intera suite: `python -m pytest tests -q` — Expected: PASS (nessuna regressione).

- [ ] **Step 8: Commit**

```bash
git add backend/app/core/config.py backend/app/organize/services/ai_tags.py backend/app/routers/sets.py backend/app/integrations/llm.py backend/tests/test_ai_key_unificata.py backend/tests/organize/test_genre_review_api.py backend/tests/organize/test_ai_suggest_api.py
git commit -m "feat(settings): chiave AI unica ANTHROPIC_API_KEY con fallback AI_API_KEY"
```

---

### Task 2: Endpoint servizi unificato, `/api/organize/providers` rimosso

**Files:**
- Test (modify): `backend/tests/test_services_status.py`
- Delete: `backend/tests/organize/test_providers_api.py`, `backend/app/organize/routers/providers.py`
- Modify: `backend/app/routers/services.py` (riscrittura), `backend/app/main.py:49,126`, `backend/app/organize/schemas.py:306-315` (rimozione `ProviderInfo`)

**Interfaces:**
- Consumes: `settings.ai_api_key` dal Task 1; `app.organize.integrations.acoustid.acoustid_configured()/fpcalc_available()`; `app.integrations.soundcloud.soundcloud_available()`.
- Produces: `GET /api/services/status` → `{"services": [...]}` con 7 voci in quest'ordine di `key`: `spotify, anthropic, discogs, musicbrainz, acoustid, slskd, soundcloud`. Ogni voce: `key, name, category, configured (bool), connected (bool|null), detail, env (list[str]), optional_env (list[str]), optional_ok (bool|null), docs`. `GET /api/organize/providers` → 404.

- [ ] **Step 1: Scrivere i test che falliscono**

In `backend/tests/test_services_status.py` aggiungere in coda (il fixture `client` esistente resta invariato):

```python
def test_elenco_unificato_sette_voci(client):
    r = client.get("/api/services/status")
    assert r.status_code == 200
    services = r.json()["services"]
    assert [s["key"] for s in services] == [
        "spotify", "anthropic", "discogs", "musicbrainz", "acoustid",
        "slskd", "soundcloud",
    ]
    for s in services:
        assert isinstance(s["env"], list)
        assert isinstance(s["optional_env"], list)
        assert s["optional_ok"] in (True, False, None)
        assert s["docs"].startswith("http")


def test_discogs_configurato_di_suo_token_opzionale(client, monkeypatch):
    monkeypatch.setattr(settings, "discogs_token", "")
    d = next(s for s in client.get("/api/services/status").json()["services"]
             if s["key"] == "discogs")
    assert d["configured"] is True          # funziona senza token
    assert d["optional_env"] == ["DISCOGS_TOKEN"]
    assert d["optional_ok"] is False        # token consigliato, non presente
    monkeypatch.setattr(settings, "discogs_token", "tok")
    d = next(s for s in client.get("/api/services/status").json()["services"]
             if s["key"] == "discogs")
    assert d["optional_ok"] is True


def test_musicbrainz_sempre_attivo(client):
    mb = next(s for s in client.get("/api/services/status").json()["services"]
              if s["key"] == "musicbrainz")
    assert mb["configured"] is True and mb["connected"] is None


def test_acoustid_richiede_chiave_e_fpcalc(client, monkeypatch):
    monkeypatch.setattr("app.routers.services.acoustid.acoustid_configured", lambda: True)
    monkeypatch.setattr("app.routers.services.acoustid.fpcalc_available", lambda: True)
    a = next(s for s in client.get("/api/services/status").json()["services"]
             if s["key"] == "acoustid")
    assert a["configured"] is True
    monkeypatch.setattr("app.routers.services.acoustid.fpcalc_available", lambda: False)
    a = next(s for s in client.get("/api/services/status").json()["services"]
             if s["key"] == "acoustid")
    assert a["configured"] is False


def test_anthropic_documenta_la_chiave_nuova(client, monkeypatch):
    monkeypatch.setattr(settings, "ai_api_key", "k")
    a = next(s for s in client.get("/api/services/status").json()["services"]
             if s["key"] == "anthropic")
    assert a["configured"] is True
    assert a["env"] == ["ANTHROPIC_API_KEY"]
    assert "AI_API_KEY" not in a["env"]     # la UI documenta solo il nome nuovo
    monkeypatch.setattr(settings, "ai_api_key", "")
    a = next(s for s in client.get("/api/services/status").json()["services"]
             if s["key"] == "anthropic")
    assert a["configured"] is False


def test_soundcloud_riflette_ytdlp(client, monkeypatch):
    monkeypatch.setattr("app.routers.services.soundcloud_available", lambda: True)
    sc = next(s for s in client.get("/api/services/status").json()["services"]
              if s["key"] == "soundcloud")
    assert sc["configured"] is True
    monkeypatch.setattr("app.routers.services.soundcloud_available", lambda: False)
    sc = next(s for s in client.get("/api/services/status").json()["services"]
              if s["key"] == "soundcloud")
    assert sc["configured"] is False


def test_organize_providers_rimosso(client):
    """Il vecchio duplicato non deve rispondere: la fonte e' una sola."""
    assert client.get("/api/organize/providers").status_code == 404
```

- [ ] **Step 2: Eseguire i test e verificarne il fallimento**

Run: `python -m pytest tests/test_services_status.py -v`
Expected: FAIL — i test nuovi falliscono (voci mancanti, `optional_env` assente, `/api/organize/providers` risponde 200); i 2 test slskd esistenti restano PASS.

- [ ] **Step 3: Riscrivere services.py**

Sostituire l'intero contenuto di `backend/app/routers/services.py` con:

```python
"""Stato unificato di TUTTE le integrazioni esterne (per la pagina Impostazioni).

Un solo elenco per l'intera app (fusione F1-F6): comprende anche i provider di
metadati della sezione Organize (MusicBrainz, AcoustID), che prima vivevano nel
duplicato /api/organize/providers. Semantica dei campi, uguale per ogni voce:

- configured: la configurazione NECESSARIA e' presente (True di suo per i
  servizi senza chiave obbligatoria, es. Discogs e MusicBrainz);
- connected: stato vivo di sessione dove esiste (OAuth Spotify), None dove il
  concetto non si applica. Per slskd lo stato vivo lo da' /api/slskd/status,
  interrogato dalla riga della UI: qui niente chiamate HTTP al demone;
- env: variabili necessarie; optional_env: variabili facoltative;
- optional_ok: True/False = facoltative presenti/assenti, None = nessuna.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core import runtime_settings
from app.core.config import settings
from app.db import get_db
from app.integrations.soundcloud import soundcloud_available
from app.integrations.spotify import SpotifyWebClient
from app.organize.integrations import acoustid

router = APIRouter(prefix="/api/services", tags=["services"])


@router.get("/status")
def services_status(db: Session = Depends(get_db)):
    spotify_configured = bool(settings.spotify_client_id and settings.spotify_client_secret)
    user_connected = False
    if spotify_configured:
        client = SpotifyWebClient(db)
        try:
            user_connected = client.user_connected()
        finally:
            client.close()
    return {
        "services": [
            {
                "key": "spotify", "name": "Spotify", "category": "Streaming",
                "configured": spotify_configured, "connected": user_connected,
                "detail": "Import playlist, brani salvati e creazione playlist. Richiede login OAuth.",
                "env": ["SPOTIFY_CLIENT_ID", "SPOTIFY_CLIENT_SECRET"],
                "optional_env": [], "optional_ok": None,
                "docs": "https://developer.spotify.com/dashboard",
            },
            {
                "key": "anthropic", "name": "Anthropic — AI", "category": "AI",
                "configured": bool(settings.ai_api_key), "connected": None,
                "detail": "Una chiave sola per tutta l'AI: Set Agent (modello: "
                          f"{settings.ai_model or 'claude-opus-4-8'}), suggerimenti "
                          "artista/titolo e revisione generi in Organize.",
                "env": ["ANTHROPIC_API_KEY"],
                "optional_env": ["AI_MODEL"], "optional_ok": True,
                "docs": "https://console.anthropic.com",
            },
            {
                "key": "discogs", "name": "Discogs", "category": "Discovery · Metadati",
                # Usabile anche senza token (rate ridotto); il token alza il rate
                # limit e mostra le copertine.
                "configured": True, "connected": None,
                "detail": "Crate digging per il Discovery (genere/stile, etichetta) e "
                          "label/genere/anno per i tag di Organize. Funziona senza "
                          "token; DISCOGS_TOKEN alza il rate limit e mostra le copertine.",
                "env": [], "optional_env": ["DISCOGS_TOKEN"],
                "optional_ok": bool(settings.discogs_token),
                "docs": "https://www.discogs.com/settings/developers",
            },
            {
                "key": "musicbrainz", "name": "MusicBrainz", "category": "Metadati",
                "configured": True, "connected": None,
                "detail": "Identita' del brano + label, genere (via tag) e anno per i "
                          "tag di Organize. Nessuna chiave richiesta (~1 richiesta/secondo).",
                "env": [], "optional_env": ["MUSICBRAINZ_USER_AGENT"], "optional_ok": True,
                "docs": "https://musicbrainz.org/doc/MusicBrainz_API",
            },
            {
                "key": "acoustid", "name": "AcoustID / Chromaprint", "category": "Fingerprint",
                "configured": acoustid.acoustid_configured() and acoustid.fpcalc_available(),
                "connected": None,
                "detail": "Identita' acustica del file → MBID (match MusicBrainz esatto, "
                          "alta confidenza). Richiede la chiave AcoustID e il binario fpcalc.",
                "env": ["ACOUSTID_API_KEY", "FPCALC"],
                "optional_env": [], "optional_ok": None,
                "docs": "https://acoustid.org/",
            },
            {
                "key": "slskd", "name": "slskd (Soulseek)", "category": "Download",
                # Configurato = URL + cartella download presenti; l'API key e' opzionale
                # (slskd puo' girare senza auth). Stessa condizione di slskd_configured().
                "configured": bool(runtime_settings.slskd_url() and runtime_settings.slskd_download_dir()),
                "connected": None,
                "detail": "Acquisizione file via Soulseek: scarica le tracce di una playlist e "
                          "collega il file alla libreria. SLSKD_API_KEY opzionale.",
                "env": ["SLSKD_URL", "SLSKD_API_KEY", "SLSKD_DOWNLOAD_DIR"],
                "optional_env": [], "optional_ok": None,
                "docs": "https://github.com/slskd/slskd",
            },
            {
                "key": "soundcloud", "name": "SoundCloud", "category": "Download",
                "configured": soundcloud_available(), "connected": None,
                "detail": "Import dei like e download per-traccia via yt-dlp. "
                          "L'username si imposta qui nella riga.",
                "env": [], "optional_env": [], "optional_ok": None,
                "docs": "https://github.com/yt-dlp/yt-dlp",
            },
        ]
    }
```

- [ ] **Step 4: Rimuovere il router providers di Organize**

1. `rm backend/app/organize/routers/providers.py`
2. `rm backend/tests/organize/test_providers_api.py`
3. In `backend/app/main.py` riga 49: togliere `providers as organize_providers,` dall'import; riga 126: togliere `organize_providers, ` dalla tupla dei router montati.
4. In `backend/app/organize/schemas.py` righe 306-315: rimuovere per intero la classe `ProviderInfo` (col suo docstring). Verificare che non resti referenziata: `grep -rn "ProviderInfo" backend/app backend/tests` → Expected: nessun risultato.

- [ ] **Step 5: Eseguire i test e verificare che passino**

Run: `python -m pytest tests/test_services_status.py -v` — Expected: PASS tutti (9).
Run: `python -m pytest tests -q` — Expected: PASS, nessun riferimento rotto a providers.

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers/services.py backend/app/main.py backend/app/organize/schemas.py backend/tests/test_services_status.py
git rm backend/app/organize/routers/providers.py backend/tests/organize/test_providers_api.py
git commit -m "feat(settings): /api/services/status unificato a 7 voci, /api/organize/providers rimosso"
```

---

### Task 3: Lista "Servizi esterni" unificata con azioni inline (frontend)

**Files:**
- Test (create): `frontend/tests/services-list.test.tsx`
- Create: `frontend/components/settings/services-list.tsx`
- Modify: `frontend/lib/api/types.ts:311-320` (campi nuovi su `ServiceStatus`)
- Modify: `frontend/lib/organize/api.ts:196-209` (rimozione `ProviderInfo`/`listProviders`)
- Modify: `frontend/lib/i18n/it.ts` e `frontend/lib/i18n/en.ts` (chiavi in `t.settings`)

**Interfaces:**
- Consumes: `servicesStatus()`, `slskdStatus/slskdConnect/slskdDisconnect`, `soundcloudStatus/setSoundcloudUsername`, `SPOTIFY_LOGIN_URL` da `@/lib/api`; `runFingerprint` + `FingerprintResult` da `@/lib/organize/api`; endpoint del Task 2.
- Produces: `ServicesList({ services, spotify })` esportata da `@/components/settings/services-list` — il Task 4 la monta nella pagina. `ServiceStatus` con `optional_env: string[]` e `optional_ok: boolean | null`.

- [ ] **Step 1: Aggiornare il tipo ServiceStatus**

In `frontend/lib/api/types.ts` (righe 311-320) sostituire l'interfaccia con:

```ts
export interface ServiceStatus {
  key: string;
  name: string;
  category: string;
  configured: boolean;
  connected: boolean | null;  // null = il servizio non ha un concetto di "login"
  detail: string;
  env: string[];
  /** Variabili facoltative (es. DISCOGS_TOKEN): la loro assenza non rende il
   *  servizio "non configurato", solo "token consigliato". */
  optional_env: string[];
  /** true/false = facoltative presenti/assenti; null = il servizio non ne ha. */
  optional_ok: boolean | null;
}
```

- [ ] **Step 2: Aggiungere le chiavi i18n**

In `frontend/lib/i18n/it.ts`, dentro `settings: {` (dopo `statusNotConfigured`, riga 79), aggiungere/modificare:

```ts
    statusActive: "Attiva",
    statusOptionalToken: "Attiva · token consigliato",
    optionalBadge: "opzionale",
    identifyNow: "Identifica ora",
    identifyBusy: "Identificazione…",
    fpResult: (identified: number, below: number, notFound: number, errors: number, total: number) =>
      `${identified} identificati, ${below} sotto soglia, ${notFound} non trovati${errors > 0 ? `, ${errors} errori` : ""} (su ${total}).`,
```

e cambiare `servicesHeading: "Servizi & API"` → `servicesHeading: "Servizi esterni"`, `statusNotConfigured: "Non configurato"` → `"Non configurata"`.

In `frontend/lib/i18n/en.ts`, stessa posizione strutturale (il file EN replica le chiavi IT):

```ts
    statusActive: "Active",
    statusOptionalToken: "Active · token recommended",
    optionalBadge: "optional",
    identifyNow: "Identify now",
    identifyBusy: "Identifying…",
    fpResult: (identified: number, below: number, notFound: number, errors: number, total: number) =>
      `${identified} identified, ${below} below threshold, ${notFound} not found${errors > 0 ? `, ${errors} errors` : ""} (of ${total}).`,
```

e `servicesHeading` → `"External services"`, `statusNotConfigured` → `"Not configured"` (già così in EN: verificare e lasciare).

- [ ] **Step 3: Scrivere il test del componente (fallisce: il componente non esiste)**

Creare `frontend/tests/services-list.test.tsx`:

```tsx
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ServiceStatus, SlskdStatus, SoundCloudStatus } from "@/lib/api";

const slskdStatusFn = vi.fn<() => Promise<SlskdStatus>>();
const slskdConnect = vi.fn();
const slskdDisconnect = vi.fn();
const soundcloudStatusFn = vi.fn<() => Promise<SoundCloudStatus>>();
const setSoundcloudUsername = vi.fn();
const runFingerprint = vi.fn();

vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  slskdStatus: (...a: unknown[]) => slskdStatusFn(...(a as [])),
  slskdConnect: (...a: unknown[]) => slskdConnect(...(a as [])),
  slskdDisconnect: (...a: unknown[]) => slskdDisconnect(...(a as [])),
  soundcloudStatus: (...a: unknown[]) => soundcloudStatusFn(...(a as [])),
  setSoundcloudUsername: (...a: unknown[]) => setSoundcloudUsername(...(a as [])),
}));
vi.mock("@/lib/organize/api", async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  runFingerprint: (...a: unknown[]) => runFingerprint(...(a as [])),
}));

const { ServicesList } = await import("@/components/settings/services-list");

function svc(over: Partial<ServiceStatus>): ServiceStatus {
  return {
    key: "x", name: "X", category: "Cat", configured: true, connected: null,
    detail: "d", env: [], optional_env: [], optional_ok: null,
    docs: "https://example.com", ...over,
  } as ServiceStatus;
}

const SEVEN: ServiceStatus[] = [
  svc({ key: "spotify", name: "Spotify", connected: false }),
  svc({ key: "anthropic", name: "Anthropic — AI", env: ["ANTHROPIC_API_KEY"] }),
  svc({ key: "discogs", name: "Discogs", optional_env: ["DISCOGS_TOKEN"], optional_ok: false }),
  svc({ key: "musicbrainz", name: "MusicBrainz" }),
  svc({ key: "acoustid", name: "AcoustID / Chromaprint" }),
  svc({ key: "slskd", name: "slskd (Soulseek)" }),
  svc({ key: "soundcloud", name: "SoundCloud" }),
];

beforeEach(() => {
  slskdStatusFn.mockResolvedValue({
    configured: true, reachable: true, is_connected: false, is_logged_in: false,
    is_connecting: false, is_transitioning: false, state: null, username: null,
    web_url: null,
  });
  soundcloudStatusFn.mockResolvedValue({ available: true, ytdlp_version: "2026.1", username: "luca" });
});
afterEach(() => { cleanup(); vi.clearAllMocks(); });

describe("ServicesList", () => {
  it("rende una riga per ogni servizio", async () => {
    render(<ServicesList services={SEVEN} spotify={null} />);
    for (const s of SEVEN) expect(screen.getByText(s.name)).toBeTruthy();
  });

  it("token opzionale mancante → 'token consigliato', non 'non configurata'", async () => {
    render(<ServicesList services={SEVEN} spotify={null} />);
    expect(screen.getByText(/token consigliato|token recommended/i)).toBeTruthy();
    expect(screen.queryByText(/non configurata|not configured/i)).toBeNull();
  });

  it("slskd: il bottone Connetti chiama slskdConnect", async () => {
    slskdConnect.mockResolvedValue({
      configured: true, reachable: true, is_connected: true, is_logged_in: true,
      is_connecting: false, is_transitioning: false, state: null, username: "u",
      web_url: null,
    });
    render(<ServicesList services={SEVEN} spotify={null} />);
    const btn = await screen.findByRole("button", { name: /connetti|connect/i });
    fireEvent.click(btn);
    await waitFor(() => expect(slskdConnect).toHaveBeenCalledTimes(1));
  });

  it("soundcloud: salva l'username col valore ripulito", async () => {
    setSoundcloudUsername.mockResolvedValue({ available: true, ytdlp_version: "2026.1", username: "nuovo-nome" });
    render(<ServicesList services={SEVEN} spotify={null} />);
    const input = await screen.findByDisplayValue("luca");
    fireEvent.change(input, { target: { value: "  nuovo-nome " } });
    fireEvent.click(screen.getByRole("button", { name: /salva|save/i }));
    await waitFor(() => expect(setSoundcloudUsername).toHaveBeenCalledWith("nuovo-nome"));
  });

  it("acoustid configurato: 'Identifica ora' chiama runFingerprint", async () => {
    runFingerprint.mockResolvedValue({ configured: true, identified: 1, below_threshold: 0, not_found: 0, errors: 0, total: 1 });
    render(<ServicesList services={SEVEN} spotify={null} />);
    fireEvent.click(screen.getByRole("button", { name: /identifica ora|identify now/i }));
    await waitFor(() => expect(runFingerprint).toHaveBeenCalledTimes(1));
  });
});
```

- [ ] **Step 4: Eseguire il test e verificarne il fallimento**

Run: `npx vitest run tests/services-list.test.tsx` (da `frontend/`)
Expected: FAIL — `Cannot find module '@/components/settings/services-list'` (o import error equivalente).

- [ ] **Step 5: Implementare services-list.tsx**

Creare `frontend/components/settings/services-list.tsx`:

```tsx
"use client";

import { useCallback, useEffect, useState } from "react";
import { Check, Copy, ExternalLink, Plug, Unplug } from "lucide-react";
import {
  setSoundcloudUsername, slskdConnect, slskdDisconnect, slskdStatus,
  soundcloudStatus, SPOTIFY_LOGIN_URL,
  type ServiceStatus, type SlskdStatus, type SoundCloudStatus, type SpotifyStatus,
} from "@/lib/api";
import { runFingerprint, type FingerprintResult } from "@/lib/organize/api";
import { Alert, Button, Input, Spinner } from "@/components/ui";
import { useT, type Dictionary } from "@/lib/i18n";

/* La lista unificata dei servizi esterni: una riga per servizio, semantica di
   stato unica, azioni inline dove servono (OAuth Spotify, login slskd,
   username SoundCloud, fingerprint AcoustID). Sostituisce la vecchia coppia
   lista Servizi + ProviderList di Organize e le card SoulseekCard e
   SoundCloudCard (fusione F1-F6: un prodotto, una lista). */

function statusLabel(s: ServiceStatus, t: Dictionary): { text: string; strong: boolean } {
  if (s.connected === true) return { text: t.settings.statusConnected, strong: true };
  if (s.connected === false) return { text: t.settings.statusToConnect, strong: false };
  if (s.configured && s.optional_ok === false) return { text: t.settings.statusOptionalToken, strong: true };
  if (s.configured) return { text: t.settings.statusActive, strong: true };
  return { text: t.settings.statusNotConfigured, strong: false };
}

export function ServicesList({ services, spotify }: {
  services: ServiceStatus[];
  spotify: SpotifyStatus | null;
}) {
  const t = useT();
  return (
    <div className="border border-border">
      {services.map((s, i) => (
        <div key={s.key} className="border-b border-border p-5 last:border-0">
          <div className="flex items-start justify-between gap-4">
            <div className="flex min-w-0 gap-3">
              <span className="tnum mt-0.5 text-xs text-faint">{String(i + 1).padStart(2, "0")}</span>
              <div className="min-w-0">
                <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
                  <span className="text-sm font-semibold uppercase tracking-wide text-fg-strong">{s.name}</span>
                  <span className="text-[10px] uppercase tracking-wider text-faint">{s.category}</span>
                </div>
                <p className="mt-1 text-sm text-muted">{s.detail}</p>
                <p className="mt-1.5 flex flex-wrap items-center gap-1.5 text-xs text-faint">
                  {s.env.map((e) => <code key={e} className="rounded-none bg-elevated px-1">{e}</code>)}
                  {s.optional_env.map((e) => (
                    <code key={e} className="rounded-none bg-elevated px-1 opacity-70">
                      {e} <span className="text-[9px] uppercase">{t.settings.optionalBadge}</span>
                    </code>
                  ))}
                  <a href={s.docs} target="_blank" rel="noreferrer" className="text-fg underline-offset-4 hover:underline">docs ↗</a>
                </p>
              </div>
            </div>
            <div className="flex shrink-0 flex-col items-end gap-2">
              {s.key !== "slskd" && (() => {
                const st = statusLabel(s, t);
                return <span className={`text-[10px] uppercase tracking-wider ${st.strong ? "text-fg-strong" : "text-muted"}`}>{st.text}</span>;
              })()}
              {s.key === "spotify" && (
                <a href={SPOTIFY_LOGIN_URL}>
                  <Button size="sm" variant="outline"><ExternalLink size={14} /> {s.connected ? t.settings.reconnectButton : t.settings.connectButton}</Button>
                </a>
              )}
            </div>
          </div>
          {s.key === "spotify" && <SpotifyExtra s={s} spotify={spotify} t={t} />}
          {s.key === "slskd" && <SlskdExtra t={t} />}
          {s.key === "soundcloud" && <SoundCloudExtra t={t} />}
          {s.key === "acoustid" && s.configured && <AcoustidExtra t={t} />}
        </div>
      ))}
    </div>
  );
}

function SpotifyExtra({ s, spotify, t }: { s: ServiceStatus; spotify: SpotifyStatus | null; t: Dictionary }) {
  const [copied, setCopied] = useState(false);
  if (!spotify?.configured) return null;
  const copyRedirect = async () => {
    await navigator.clipboard.writeText(spotify.redirect_uri);
    setCopied(true); setTimeout(() => setCopied(false), 1500);
  };
  return (
    <div className="mt-3 border border-border bg-bg p-3">
      <p className="mb-1.5 text-xs text-muted">{t.settings.redirectUriPrefix} <strong>{t.settings.redirectUriExactTerm}</strong> {t.settings.redirectUriSuffix}</p>
      <div className="flex items-center gap-2">
        <code className="flex-1 break-all bg-elevated px-2 py-1 text-xs text-fg">{spotify.redirect_uri}</code>
        <Button size="sm" variant="outline" onClick={copyRedirect}>{copied ? <><Check size={14} /> {t.settings.copiedLabel}</> : <><Copy size={14} /> {t.settings.copyButton}</>}</Button>
      </div>
      {s.connected && (
        <p className="mt-2 text-xs text-muted">
          {t.settings.reauthorizeHintPrefix} <code className="rounded-none bg-elevated px-1">403</code>, {t.settings.reauthorizeHintMiddle} <strong>{t.settings.reconnectButton}</strong> {t.settings.reauthorizeHintSuffix}
        </p>
      )}
    </div>
  );
}

function SlskdExtra({ t }: { t: Dictionary }) {
  const [status, setStatus] = useState<SlskdStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    slskdStatus()
      .then((s) => { setStatus(s); setError(null); })
      .catch((e) => setError(String((e as Error).message ?? e)));
  }, []);
  useEffect(load, [load]);

  // Dopo connect/disconnect slskd resta "in transizione" per qualche secondo
  // (Connecting → LoggingIn → LoggedIn): polling breve e limitato finche' lo
  // stato si stabilizza, pulsanti disabilitati nel frattempo.
  const act = async (fn: () => Promise<SlskdStatus>) => {
    setBusy(true); setError(null);
    try {
      let s = await fn();
      setStatus(s);
      for (let i = 0; i < 10 && (s.is_transitioning || s.is_connecting); i++) {
        await new Promise((r) => setTimeout(r, 1000));
        s = await slskdStatus();
        setStatus(s);
      }
    } catch (e) {
      setError(String((e as Error).message ?? e));
    } finally {
      setBusy(false);
    }
  };

  const st = ((): { text: string; strong: boolean } => {
    if (!status) return { text: "—", strong: false };
    if (!status.configured) return { text: t.settings.soulseekNotConfigured, strong: false };
    if (!status.reachable) return { text: t.settings.soulseekUnreachable, strong: false };
    if (status.is_connecting || status.is_transitioning) return { text: t.settings.soulseekConnecting, strong: false };
    if (status.is_connected && status.is_logged_in) {
      return { text: status.username ? t.settings.soulseekConnectedAs(status.username) : t.settings.soulseekConnected, strong: true };
    }
    return { text: t.settings.soulseekDisconnected, strong: false };
  })();

  const canAct = !!status?.configured && !!status?.reachable;
  const connected = !!status?.is_connected && !!status?.is_logged_in;

  return (
    <div className="mt-3 flex items-center justify-between gap-4 border border-border bg-bg p-3">
      <span className={`text-sm ${st.strong ? "text-fg-strong" : "text-muted"}`}>{st.text}</span>
      {canAct && (
        connected ? (
          <Button size="sm" variant="outline" onClick={() => act(slskdDisconnect)} disabled={busy}>
            {busy ? <Spinner /> : <Unplug size={14} />} {t.settings.soulseekDisconnect}
          </Button>
        ) : (
          <Button size="sm" onClick={() => act(slskdConnect)} disabled={busy}>
            {busy ? <Spinner /> : <Plug size={14} />} {t.settings.soulseekConnect}
          </Button>
        )
      )}
      {error && <Alert tone="danger">⚠ {error}</Alert>}
    </div>
  );
}

function SoundCloudExtra({ t }: { t: Dictionary }) {
  const [status, setStatus] = useState<SoundCloudStatus | null>(null);
  const [username, setUsername] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    soundcloudStatus()
      .then((s) => { setStatus(s); setUsername(s.username ?? ""); })
      .catch(() => setStatus(null));
  }, []);

  const save = async () => {
    setError(null); setSaving(true);
    try { setStatus(await setSoundcloudUsername(username.trim())); }
    catch (e) { setError(String((e as { message?: string })?.message ?? e)); }
    finally { setSaving(false); }
  };

  return (
    <div className="mt-3 grid gap-2 border border-border bg-bg p-3">
      {status && !status.available && <Alert tone="warning">{t.settings.soundcloudYtdlpUnavailable}</Alert>}
      {error && <Alert tone="danger">⚠ {error}</Alert>}
      <div className="flex items-center gap-2">
        <span className="shrink-0 text-xs text-muted">{t.settings.usernameLabel}</span>
        <Input className="flex-1" value={username}
          onChange={(e) => setUsername(e.target.value)}
          placeholder={t.settings.usernamePlaceholder} disabled={saving} />
        <Button size="sm" onClick={save} disabled={saving || username.trim() === ""}>
          {saving ? <Spinner /> : t.common.save}
        </Button>
      </div>
      {status?.ytdlp_version && <p className="text-xs text-faint">yt-dlp {status.ytdlp_version}</p>}
    </div>
  );
}

function AcoustidExtra({ t }: { t: Dictionary }) {
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<FingerprintResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const identify = async () => {
    setError(null); setBusy(true);
    try { setResult(await runFingerprint()); }
    catch (e) { setError(String((e as { message?: string })?.message ?? e)); }
    finally { setBusy(false); }
  };

  return (
    <div className="mt-3 flex flex-wrap items-center gap-3 border border-border bg-bg p-3">
      <Button size="sm" variant="outline" onClick={identify} disabled={busy}>
        {busy ? <><Spinner /> {t.settings.identifyBusy}</> : t.settings.identifyNow}
      </Button>
      {result && (
        <span className="text-xs text-muted">
          {t.settings.fpResult(result.identified, result.below_threshold, result.not_found, result.errors, result.total)}
        </span>
      )}
      {error && <Alert tone="danger">⚠ {error}</Alert>}
    </div>
  );
}
```

Nota per l'implementatore: se `t.common.save` non esiste nel dizionario, usare `t.settings.saveButton` (esiste: "Salva"/"Save") — verificare con `grep -n "save:" frontend/lib/i18n/it.ts` dentro il blocco `common`. La `SoundCloudCard` attuale usa `t.common.save`: replicarne la scelta.

- [ ] **Step 6: Rimuovere ProviderInfo/listProviders dal client Organize**

In `frontend/lib/organize/api.ts` eliminare il blocco `// --- PROVIDERS ---` (righe 196-209: interfaccia `ProviderInfo` e funzione `listProviders`). `FingerprintResult`, `runFingerprint` e `fingerprintStatus` restano.

- [ ] **Step 7: Eseguire i test e verificare che passino**

Run: `npx vitest run tests/services-list.test.tsx` — Expected: PASS (5 test).
Run: `npm run lint` — Expected: PASS (in particolare nessun uso residuo di `listProviders`).

- [ ] **Step 8: Commit**

```bash
git add frontend/components/settings/services-list.tsx frontend/tests/services-list.test.tsx frontend/lib/api/types.ts frontend/lib/organize/api.ts frontend/lib/i18n/it.ts frontend/lib/i18n/en.ts
git commit -m "feat(settings): lista Servizi esterni unificata con azioni inline"
```

---

### Task 4: Pagina a 4 gruppi, OrganizeSection ridotta, pulizia i18n

**Files:**
- Test (modify): `frontend/tests/settings-unica.test.tsx`
- Modify: `frontend/app/settings/page.tsx` (riscrittura), `frontend/components/settings/config-card.tsx` (assorbe l'indicizzazione), `frontend/components/settings/organize-section.tsx` (via ProviderList), `frontend/lib/i18n/it.ts`, `frontend/lib/i18n/en.ts`

**Interfaces:**
- Consumes: `ServicesList` dal Task 3; `useJobs()` da `@/components/jobs-provider`; `startLibraryIndex` da `@/lib/api`.
- Produces: pagina `/settings` con 4 gruppi; `ConfigCard` che include la sezione indicizzazione; `OrganizeSection` senza provider.

- [ ] **Step 1: Aggiornare il test di pagina (fallisce)**

Sostituire in `frontend/tests/settings-unica.test.tsx` il mock e aggiungere le asserzioni di struttura. Il mock di `@/lib/organize/api` diventa (via `listProviders` e `runFingerprint`, che `OrganizeSection` non importa più):

```tsx
const getSettings = vi.fn<() => Promise<Settings>>();
const updateSettings = vi.fn();

vi.mock("@/lib/organize/api", () => ({
  getSettings: (...a: unknown[]) => getSettings(...(a as [])),
  updateSettings: (...a: unknown[]) => updateSettings(...(a as [])),
}));
```

Nel `describe`, sostituire il test `"la sezione Organize è montata nella pagina unica, sotto la sua intestazione"` con questa versione estesa e aggiungerne due:

```tsx
  it("la sezione Organize è montata nella pagina unica, sotto la sua intestazione", () => {
    const page = readFileSync(resolve(__dirname, "../app/settings/page.tsx"), "utf8");
    expect(page).toContain("<OrganizeSection />");
    expect(page).toMatch(/groupOrganize[\s\S]{0,120}<OrganizeSection \/>/);
  });

  it("la pagina usa la lista servizi unificata, senza card sciolte", () => {
    const page = readFileSync(resolve(__dirname, "../app/settings/page.tsx"), "utf8");
    expect(page).toContain("<ServicesList");
    expect(page).not.toMatch(/SoulseekCard|SoundCloudCard|LibraryIndexCard/);
  });

  it("OrganizeSection non ha più la lista provider (vive nei Servizi esterni)", () => {
    const section = readFileSync(
      resolve(__dirname, "../components/settings/organize-section.tsx"), "utf8");
    expect(section).not.toMatch(/ProviderList|listProviders|StatusBadge/);
  });
```

- [ ] **Step 2: Eseguire il test e verificarne il fallimento**

Run: `npx vitest run tests/settings-unica.test.tsx`
Expected: FAIL — i 2 test nuovi falliscono (la pagina usa ancora le card; OrganizeSection contiene ProviderList). I test dei template devono restare PASS.

- [ ] **Step 3: ConfigCard assorbe l'indicizzazione**

In `frontend/components/settings/config-card.tsx`:

1. Estendere gli import:

```tsx
import {
  errText, getConfigSettings, patchConfigSettings, setLibraryShare, startLibraryIndex,
  type ConfigPatch, type ConfigSettings,
} from "@/lib/api";
import { useJobs } from "@/components/jobs-provider";
```

2. In fondo al JSX del componente, dopo il `<div className="border-t border-border pt-4">` di `share_library` (righe 125-130), aggiungere come fratello successivo:

```tsx
        <div className="border-t border-border pt-4">
          <LibraryIndexSection />
        </div>
```

3. In fondo al file aggiungere il componente (logica identica alla vecchia `LibraryIndexCard` di page.tsx, senza il bordo esterno):

```tsx
/* Indicizzazione della libreria canonica: vive dentro la card dei percorsi
   perche' LIBRARY_ROOT e "Indicizza ora" sono la stessa cosa vista da due
   lati (il path e l'azione che lo legge). Stato dal poller globale
   (JobsProvider): niente polling locale. */
function LibraryIndexSection() {
  const t = useT();
  const { libraryIndex: libJob, refresh } = useJobs();
  const [libError, setLibError] = useState<string | null>(null);

  const runIndex = () => {
    setLibError(null);
    startLibraryIndex().then(() => refresh()).catch((e) => setLibError(String(e.message ?? e)));
  };

  const busy = libJob?.status === "running";

  return (
    <div className="space-y-3 text-sm">
      <div>
        <div className="text-sm font-semibold uppercase tracking-wide text-fg-strong">{t.settings.canonicalLibraryTitle}</div>
        <p className="mt-1 text-sm text-muted">{t.settings.canonicalLibraryBody}</p>
      </div>
      {libError && <Alert tone="danger">⚠ {libError}</Alert>}
      {libJob?.status === "error" && <Alert tone="danger">⚠ {libJob.error ?? t.settings.indexFailedFallback}</Alert>}
      <Button size="sm" onClick={runIndex} disabled={busy}>{busy ? t.settings.indexingLabel : t.settings.indexNowButton}</Button>
      {busy && (
        <p className="tnum text-sm text-muted">{t.settings.indexingProgress(libJob.processed, libJob.total)}</p>
      )}
      {libJob?.status === "done" && libJob.result?.linking && (
        <p className="text-sm text-fg">
          {t.settings.indexResultSummary(
            libJob.result.linking.scanned, libJob.result.linking.matched, libJob.result.linking.created,
            libJob.result.linking.duplicates, libJob.result.linking.relinked, libJob.result.linking.lost,
            libJob.result.linking.failed,
          )}
        </p>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Riscrivere page.tsx a 4 gruppi**

Sostituire l'intero contenuto di `frontend/app/settings/page.tsx` con:

```tsx
"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { apiGet, servicesStatus, type ServiceStatus, type SpotifyStatus } from "@/lib/api";
import { Alert, Loading } from "@/components/ui";
import { PageLayout } from "@/components/page-layout";
import { ConfigCard } from "@/components/settings/config-card";
import { OrganizeSection } from "@/components/settings/organize-section";
import { ServicesList } from "@/components/settings/services-list";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/cn";

/* Impostazioni: 4 gruppi (fusione F1-F6, un prodotto solo).
   Generale · Percorsi e libreria · Servizi esterni · Organize. */

function SettingsInner() {
  const { lang, setLang, t } = useI18n();
  const params = useSearchParams();
  const oauth = params.get("spotify");
  const [services, setServices] = useState<ServiceStatus[] | null>(null);
  const [spotify, setSpotify] = useState<SpotifyStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    servicesStatus().then((r) => { setServices(r.services); setError(null); }).catch((e) => { setServices(null); setError(String(e.message ?? e)); });
    apiGet<SpotifyStatus>("/api/spotify/status").then(setSpotify).catch(() => setSpotify(null));
  }, []);
  useEffect(load, [load]);

  const marginalia = (
    <div className="space-y-2 text-xs leading-relaxed text-muted">
      <p>{t.settings.marginaliaPrefix} <code className="rounded-none bg-elevated px-1">backend/.env</code> {t.settings.marginaliaSuffix}</p>
    </div>
  );

  return (
    <PageLayout title={t.settings.pageTitle} marginaliaTitle={t.settings.helpTitle} marginalia={marginalia}>
      {oauth === "connected" && <div className="mb-4"><Alert tone="info">{t.settings.spotifyConnected}</Alert></div>}
      {oauth === "error" && <div className="mb-4"><Alert tone="danger">{t.settings.spotifyLoginFailed(params.get("detail") ?? "")}</Alert></div>}
      {error && <div className="mb-4"><Alert tone="danger">{t.dashboard.backendDown(error)}</Alert></div>}

      <div className="mb-2 text-[10px] uppercase tracking-wider text-muted">{t.settings.languageLabel}</div>
      <div className="border border-border p-5">
        <div role="group" aria-label={t.settings.languageLabel} className="inline-flex rounded-none border border-border bg-surface p-1">
          <button
            type="button"
            aria-pressed={lang === "it"}
            onClick={() => setLang("it")}
            className={cn("rounded-none px-3 py-1 text-xs font-medium uppercase tracking-wider transition-colors",
              lang === "it" ? "bg-elevated text-fg" : "text-muted hover:text-fg")}
          >
            {t.settings.languageIt}
          </button>
          <button
            type="button"
            aria-pressed={lang === "en"}
            onClick={() => setLang("en")}
            className={cn("rounded-none px-3 py-1 text-xs font-medium uppercase tracking-wider transition-colors",
              lang === "en" ? "bg-elevated text-fg" : "text-muted hover:text-fg")}
          >
            {t.settings.languageEn}
          </button>
        </div>
      </div>

      <div className="mb-2 mt-8 text-[10px] uppercase tracking-wider text-muted">{t.settings.pathsHeading}</div>
      <ConfigCard />

      <div className="mb-2 mt-8 text-[10px] uppercase tracking-wider text-muted">{t.settings.servicesHeading}</div>
      {services ? <ServicesList services={services} spotify={spotify} /> : (
        <div className="border border-border">{!error && <div className="px-5"><Loading /></div>}</div>
      )}

      <div className="mb-2 mt-8 text-[10px] uppercase tracking-wider text-muted">{t.nav.groupOrganize}</div>
      <OrganizeSection />
    </PageLayout>
  );
}

export default function Settings() {
  return <Suspense><SettingsInner /></Suspense>;
}
```

- [ ] **Step 5: Ridurre OrganizeSection ai soli template**

In `frontend/components/settings/organize-section.tsx`:

1. Import: togliere `runFingerprint, listProviders` e i tipi `FingerprintResult, ProviderInfo` (restano `getSettings, updateSettings, type Settings`).
2. Stato: rimuovere `providers`, `fpResult`, `fpBusy` e i relativi `useEffect`/`onIdentify`.
3. JSX: rimuovere `<ProviderList ... />` (righe 121-123) e le funzioni `StatusBadge` e `ProviderList` per intero (righe 130-187).
4. Aggiornare il commento di testa del file: la lista provider ora vive nella lista Servizi esterni della stessa pagina.

- [ ] **Step 6: Pulizia i18n**

Prima verificare che le chiavi da rimuovere non abbiano altri usi:

Run: `grep -rn "guideProvider\|guideL1\|guideTemplate\|guideL2\|providersMeta\|providerTitle\|providerHintPre\|providerHintPost\|statusMissing\|organize.settings.identifyNow\|organize.settings.fpResult\|libraryHeading" frontend/app frontend/components frontend/lib --include="*.tsx" --include="*.ts" | grep -v i18n/`
Expected: nessun risultato (dopo gli step 3-5).

Poi in ENTRAMBI `frontend/lib/i18n/it.ts` e `frontend/lib/i18n/en.ts`:

1. In `t.settings` (blocco Cratory): rimuovere `libraryHeading` (l'indicizzazione ora sta dentro ConfigCard) e `soulseekSubtitle`/`soundcloudSubtitle` SOLO SE non più referenziate (verificare con grep; la lista unificata usa `detail` dal backend). Aggiungere `pathsHeading`:
   - it: `pathsHeading: "Percorsi e libreria",`
   - en: `pathsHeading: "Paths & library",`
2. In `t.organize.settings`: rimuovere `statusConfigured`, `statusConnected`, `statusMissing`, `providerTitle`, `providerHintPre`, `providerHintPost`, `identifyBusy`, `identifyNow`, `fpResult`, `providersMeta`, `guideL1`, `guideTemplate`, `guideL2`, `guideProviderPre`, `guideProvider`, `guideProviderPost` (le guide erano della pagina `/organize/settings` sparita in F5; verificare col grep sopra prima di ogni rimozione — se una chiave risulta usata, lasciarla e annotarlo nel commit).

- [ ] **Step 7: Eseguire i test e verificare che passino**

Run: `npx vitest run tests/settings-unica.test.tsx tests/services-list.test.tsx` — Expected: PASS tutti.
Run: `npm run lint` — Expected: PASS (intercetta chiavi i18n rimosse ma ancora usate e import morti).
Run: `npm run build` — Expected: PASS (i dizionari IT/EN condividono il tipo `Dictionary`: una chiave rimossa da un file solo fa fallire il typecheck).

- [ ] **Step 8: Commit**

```bash
git add frontend/app/settings/page.tsx frontend/components/settings/config-card.tsx frontend/components/settings/organize-section.tsx frontend/tests/settings-unica.test.tsx frontend/lib/i18n/it.ts frontend/lib/i18n/en.ts
git commit -m "feat(settings): pagina a 4 gruppi, card sciolte assorbite, OrganizeSection ridotta ai template"
```

---

### Task 5: Documentazione e verifica finale

**Files:**
- Modify: `docs/API.md` (sezione `/api/services/status`, ~riga 771), `README.md:139`, `docs/ROADMAP.md`, `PROGRESS.md`

**Interfaces:**
- Consumes: il comportamento consegnato dai task 1-4.
- Produces: documentazione allineata; verifica end-to-end su browser.

- [ ] **Step 1: Aggiornare docs/API.md**

Nella sezione di `GET /api/services/status` (~riga 771): documentare le 7 voci (`spotify, anthropic, discogs, musicbrainz, acoustid, slskd, soundcloud`) e i campi nuovi `optional_env` (variabili facoltative) e `optional_ok` (true/false = presenti/assenti, null = nessuna), con la semantica unificata di `configured`/`connected` (necessaria presente / sessione viva, null dove non si applica; per slskd lo stato vivo resta su `GET /api/slskd/status`). Aggiungere una riga: `/api/organize/providers` rimosso (assorbito qui). Se `docs/API.md` elenca gli endpoint Organize, togliere la voce providers da lì.

- [ ] **Step 2: Aggiornare README e diario**

- `README.md` riga 139: `AI_API_KEY=` → `ANTHROPIC_API_KEY=` e, se il testo circostante spiega la variabile, citare il fallback (`AI_API_KEY` ancora letta per retrocompatibilità).
- `docs/ROADMAP.md`: aggiungere lo stato del lavoro "Settings unificata post-fusione" (fatto, data 2026-08-13) secondo il formato esistente del file.
- `PROGRESS.md`: voce di diario con data 2026-08-13: endpoint unificato, chiave AI unica, pagina a 4 gruppi, cosa è stato rimosso.

- [ ] **Step 3: Verifica completa backend + frontend**

```bash
cd backend && source .venv/bin/activate && python -m pytest tests -q
```
Expected: PASS tutti.

```bash
cd frontend && npm run lint && npm run build && npx vitest run
```
Expected: PASS tutti (lint, build, unit).

- [ ] **Step 4: Verifica visiva nel browser**

Avviare il dev server via preview (config launch.json esistente o backend `uvicorn app.main:app --reload --port 8000` + frontend dev) e aprire `/settings`. Verificare:
1. 4 gruppi nell'ordine: Lingua → Percorsi e libreria (con "Indicizza ora" in fondo alla card) → Servizi esterni (7 righe) → Organize (soli template).
2. Discogs senza token mostra "Attiva · token consigliato" e il chip `DISCOGS_TOKEN opzionale`.
3. La riga slskd mostra lo stato vivo e Connetti/Disconnetti funziona (se slskd locale attivo su :5030).
4. La riga SoundCloud salva l'username; la riga AcoustID (se configurata) esegue "Identifica ora".
5. Switch lingua IT/EN: nessuna chiave mancante (nessun testo "undefined").
Fare uno screenshot della pagina come prova.

- [ ] **Step 5: Commit finale**

```bash
git add docs/API.md README.md docs/ROADMAP.md PROGRESS.md
git commit -m "docs(settings): documentazione allineata alla settings unificata"
```
