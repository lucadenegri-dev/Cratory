# Versione dell'app e controllo aggiornamenti — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dare a Cratory una versione unica e un bottone in Impostazioni che dica, onestamente, se ne esiste una più recente.

**Architecture:** Un file `VERSION` nella radice del repository è l'unica fonte; il backend lo legge (con `CRATORY_VERSION` come scavalco per il futuro bundle Tauri) e lo espone via API. Un servizio interroga l'API pubblica delle release di GitHub e confronta le due versioni **numericamente**, non come stringhe. Il risultato ha tre esiti che restano distinti: aggiornato, disponibile, oppure non verificabile — quest'ultimo non deve mai somigliare al primo.

**Tech Stack:** Python + FastAPI + httpx (già presenti), Next.js 16 + React, pytest + vitest.

**Spec:** `docs/superpowers/specs/2026-08-22-versione-e-controllo-aggiornamenti-design.md`

## Global Constraints

- **Nessuna dipendenza nuova.** `httpx` c'è già; il confronto di versioni sono poche righe di stdlib.
- **Nessun test tocca la rete vera.** Le risposte di GitHub si simulano con `httpx.MockTransport`.
- **"Non lo so" non è "sei aggiornato".** Nessun percorso di errore può produrre `update_available: false`.
- **Nessun testo user-facing nasce nel backend** — solo codici, che il frontend traduce. L'unica eccezione sono le note di rilascio: sono testo di GitHub, contenuto di terzi, e vanno mostrate come tali.
- **Le due lingue restano allineate**: `frontend/lib/i18n/en.ts` è la fonte dei tipi, si modifica per prima.
- **Test frontend solo in `frontend/tests/`** — `vitest.config.ts` ha `include: ["tests/**"]`; un test altrove non viene eseguito e sembra verde. Ogni file di test ha `afterEach(cleanup)`, e un `vi.mock("@/lib/api", …)` deve esporre **ogni** export che il componente importa.
- **Commit:** uno per task, messaggi in italiano con prefisso convenzionale. **Mai** un trailer `Co-Authored-By`.
- **Comandi** (il worktree usa l'interprete del checkout principale):
  ```bash
  cd backend && /Users/lucadenegri/Develop/DJProject01/backend/.venv/bin/python -m pytest tests -q
  ```
  ```bash
  cd frontend && npm run test:unit && npx tsc --noEmit && npm run lint
  ```
- Dopo ogni mutation check, ripulire i bytecode prima di rieseguire:
  ```bash
  find backend -name __pycache__ -type d -exec rm -rf {} +
  ```
  Una modifica della stessa lunghezza annullata nello stesso secondo lascia `mtime` e dimensione invariati: Python continua a servire il bytecode della mutazione e il test mente.

---

## File Structure

| File | Responsabilità |
|---|---|
| `VERSION` (creato, radice) | Il numero, e nient'altro |
| `backend/app/core/version.py` (creato) | Legge la versione; confronta due versioni |
| `backend/app/services/update_check.py` (creato) | Interroga GitHub, decide i tre esiti |
| `backend/app/routers/updates.py` (creato) | HTTP: `/api/version`, `/api/updates/check` |
| `backend/app/main.py` (modificato) | Registra il router |
| `backend/tests/test_app_version.py` (creato) | Lettura, scavalco, default |
| `backend/tests/test_version_compare.py` (creato) | Il confronto numerico, col caso 0.10 vs 0.9 |
| `backend/tests/test_update_check.py` (creato) | I tre esiti, col `404` ambiguo |
| `frontend/lib/api/updates.ts` (creato) | Client |
| `frontend/components/settings/version-card.tsx` (creato) | La riga e il bottone |
| `frontend/lib/i18n/{en,it}.ts` (modificati) | I testi dei tre esiti |
| `frontend/app/settings/page.tsx` (modificato) | Monta la sezione |
| `frontend/tests/version-card.test.tsx` (creato) | I tre esiti nella UI |

---

## Task 1: La versione, da un'unica fonte

**Files:**
- Create: `VERSION`, `backend/app/core/version.py`, `backend/app/routers/updates.py`, `backend/tests/test_app_version.py`
- Modify: `backend/app/main.py`

**Interfaces:**
- Produces: `app_version() -> str`; costante `VERSION_ENV = "CRATORY_VERSION"`; `GET /api/version` → `{"version": str}`.

- [ ] **Step 1: Scrivere i test che falliscono**

Creare `backend/tests/test_app_version.py`:

```python
"""La versione ha una fonte sola. Il file nella radice, con l'ambiente che lo
scavalca: in un bundle Tauri quella radice non esiste."""
from fastapi.testclient import TestClient

from app.core import version as v
from app.main import app


def test_legge_il_file_della_radice(monkeypatch):
    monkeypatch.delenv(v.VERSION_ENV, raising=False)
    assert v.app_version() == "0.9.0"


def test_l_ambiente_scavalca_il_file(monkeypatch):
    """È il seam per il packager: nel bundle il numero arriva da fuori."""
    monkeypatch.setenv(v.VERSION_ENV, "1.2.3")
    assert v.app_version() == "1.2.3"


def test_ambiente_vuoto_non_conta(monkeypatch):
    monkeypatch.setenv(v.VERSION_ENV, "   ")
    assert v.app_version() == "0.9.0"


def test_senza_file_ne_ambiente_non_esplode(monkeypatch, tmp_path):
    """Un checkout incompleto deve poter avviare l'app: la versione è
    un'informazione, non una precondizione."""
    monkeypatch.delenv(v.VERSION_ENV, raising=False)
    monkeypatch.setattr(v, "_percorso_version", lambda: tmp_path / "manca")
    assert v.app_version() == "0.0.0-dev"


def test_endpoint(monkeypatch):
    monkeypatch.delenv(v.VERSION_ENV, raising=False)
    assert TestClient(app).get("/api/version").json() == {"version": "0.9.0"}


def test_package_json_non_diverge():
    """Due numeri che raccontano cose diverse sono peggio di un numero solo."""
    import json
    from pathlib import Path
    radice = Path(__file__).resolve().parent.parent.parent
    pkg = json.loads((radice / "frontend" / "package.json").read_text())
    assert pkg["version"] == (radice / "VERSION").read_text().strip()
```

- [ ] **Step 2: Eseguire e verificare il fallimento**

```bash
cd backend && /Users/lucadenegri/Develop/DJProject01/backend/.venv/bin/python -m pytest tests/test_app_version.py -q
```
Atteso: `ModuleNotFoundError: No module named 'app.core.version'`.

- [ ] **Step 3: Creare il file `VERSION`**

Nella radice del repository, un file `VERSION` contenente esattamente:

```
0.9.0
```

Una riga, nessun commento, nessun prefisso `v` (il prefisso vive solo sui tag git).

Verificare che `frontend/package.json` dica già `"version": "0.9.0"`; se dice altro, allinearlo — il test sopra lo pretende.

- [ ] **Step 4: Implementare la lettura**

Creare `backend/app/core/version.py`:

```python
"""La versione dell'app, da un'unica fonte.

Il file `VERSION` nella radice del repository è quella fonte. La variabile
d'ambiente lo scavalca per lo stesso motivo per cui esiste `CRATORY_BIN_DIR`:
in un bundle Tauri non c'è nessuna radice di repository da cui leggere, e il
packager passa il numero dall'ambiente.
"""
from __future__ import annotations

import os
from pathlib import Path

from app.core.config import BACKEND_DIR

VERSION_ENV = "CRATORY_VERSION"
FALLBACK = "0.0.0-dev"


def _percorso_version() -> Path:
    """Il file sta nella radice del repository, un livello sopra `backend/`."""
    return BACKEND_DIR.parent / "VERSION"


def app_version() -> str:
    """Ambiente → file → default. Non solleva mai: un checkout senza il file
    deve poter avviare l'app, perché la versione è un'informazione e non una
    precondizione per funzionare."""
    dall_ambiente = (os.environ.get(VERSION_ENV) or "").strip()
    if dall_ambiente:
        return dall_ambiente
    try:
        letto = _percorso_version().read_text().strip()
    except OSError:
        return FALLBACK
    return letto or FALLBACK
```

- [ ] **Step 5: Esporre l'endpoint**

Creare `backend/app/routers/updates.py`:

```python
"""Versione dell'app e controllo degli aggiornamenti.

Router senza prefisso: `/api/version` e `/api/updates/*` non condividono una
radice, e scrivere i percorsi per intero è più chiaro di due router separati
per un endpoint ciascuno.
"""
from fastapi import APIRouter
from pydantic import BaseModel

from app.core.version import app_version

router = APIRouter(tags=["updates"])


class Version(BaseModel):
    version: str


@router.get("/api/version", response_model=Version)
def read_version() -> Version:
    return Version(version=app_version())
```

In `backend/app/main.py`, aggiungere `updates` all'import dei router e registrarlo accanto agli altri:

```python
app.include_router(updates.router)
```

- [ ] **Step 6: Eseguire i test**

```bash
cd backend && /Users/lucadenegri/Develop/DJProject01/backend/.venv/bin/python -m pytest tests/test_app_version.py -q
```
Atteso: `6 passed`.

- [ ] **Step 7: Commit**

```bash
git add VERSION backend/app/core/version.py backend/app/routers/updates.py backend/app/main.py backend/tests/test_app_version.py
git commit -m "feat(updates): una versione sola per tutta l'app, esposta via API"
```

---

## Task 2: Confrontare due versioni

**Files:**
- Modify: `backend/app/core/version.py`
- Test: `backend/tests/test_version_compare.py`

**Interfaces:**
- Produces: `parse_version(raw: str) -> tuple[int, int, int] | None`; `is_newer(candidate: str, current: str) -> bool`.

- [ ] **Step 1: Scrivere i test che falliscono**

Creare `backend/tests/test_version_compare.py`:

```python
"""Il confronto è numerico, non testuale. È il difetto classico di questa
funzione e vale la pena avere un test che lo nomina."""
from app.core.version import is_newer, parse_version


def test_dieci_viene_dopo_nove():
    """Come stringhe "0.10.0" < "0.9.0": un confronto testuale direbbe che
    la 0.10.0 è più vecchia, e l'utente non vedrebbe mai l'aggiornamento."""
    assert is_newer("0.10.0", "0.9.0") is True
    assert is_newer("0.9.0", "0.10.0") is False


def test_uguale_non_e_piu_recente():
    assert is_newer("0.9.0", "0.9.0") is False


def test_il_prefisso_v_dei_tag_viene_tolto():
    """I tag git portano la `v`, il file VERSION no: il confronto avviene fra
    cose che devono prima essere ridotte alla stessa forma."""
    assert parse_version("v0.9.0") == (0, 9, 0)
    assert is_newer("v0.10.0", "0.9.0") is True


def test_maggiore_su_ogni_posizione():
    assert is_newer("1.0.0", "0.99.99") is True
    assert is_newer("0.9.1", "0.9.0") is True


def test_il_suffisso_di_prerelease_non_rompe():
    assert parse_version("1.0.0-beta.1") == (1, 0, 0)


def test_versione_malformata_non_solleva():
    """Un tag lo scrive una persona a mano: può essere qualunque cosa."""
    for scritto_male in ("", "boh", "1.2", "1.2.3.4", "v", "x.y.z"):
        assert parse_version(scritto_male) is None
        assert is_newer(scritto_male, "0.9.0") is False
        assert is_newer("0.9.0", scritto_male) is False
```

- [ ] **Step 2: Eseguire e verificare il fallimento**

```bash
cd backend && /Users/lucadenegri/Develop/DJProject01/backend/.venv/bin/python -m pytest tests/test_version_compare.py -q
```
Atteso: `ImportError: cannot import name 'is_newer'`.

- [ ] **Step 3: Implementare**

Aggiungere in `backend/app/core/version.py`:

```python
def parse_version(raw: str) -> tuple[int, int, int] | None:
    """`v0.10.0` e `0.10.0` danno lo stesso risultato. `None` se non è una
    versione su cui si possa ragionare: un tag lo scrive una persona a mano,
    e non deve poter far esplodere il controllo aggiornamenti."""
    testo = (raw or "").strip().lstrip("vV")
    numeri = testo.split("+", 1)[0].split("-", 1)[0].split(".")
    if len(numeri) != 3:
        return None
    try:
        maggiore, minore, patch = (int(n) for n in numeri)
    except ValueError:
        return None
    return maggiore, minore, patch


def is_newer(candidate: str, current: str) -> bool:
    """True se `candidate` è più recente di `current`.

    Confronto fra numeri, non fra stringhe: "0.10.0" < "0.9.0" in ordine
    testuale, e chi lo confrontasse così non mostrerebbe mai un aggiornamento
    dopo la nona minor. Se una delle due non è leggibile la risposta è False:
    meglio non annunciare un aggiornamento che annunciarne uno inventato.
    """
    a = parse_version(candidate)
    b = parse_version(current)
    if a is None or b is None:
        return False
    return a > b
```

- [ ] **Step 4: Eseguire i test**

```bash
cd backend && /Users/lucadenegri/Develop/DJProject01/backend/.venv/bin/python -m pytest tests/test_version_compare.py -q
```
Atteso: `6 passed`.

- [ ] **Step 5: Provare che il test sul confronto non sia vacuo**

Sostituire il corpo di `is_newer` con un confronto fra stringhe (`return candidate > current`), rieseguire, verificare che `test_dieci_viene_dopo_nove` fallisca, ripristinare, ripulire i `__pycache__` e rieseguire. Riportare cosa si è osservato.

- [ ] **Step 6: Commit**

```bash
git add backend/app/core/version.py backend/tests/test_version_compare.py
git commit -m "feat(updates): confronto di versioni numerico, non testuale"
```

---

## Task 3: Il controllo remoto e i suoi tre esiti

**Files:**
- Create: `backend/app/services/update_check.py`, `backend/tests/test_update_check.py`
- Modify: `backend/app/routers/updates.py`

**Interfaces:**
- Consumes: `app_version()`, `is_newer()`.
- Produces: `GITHUB_REPO = "lucadenegri-dev/Cratory"`; `check(client: httpx.Client | None = None) -> dict` con chiavi `current`, `latest`, `update_available`, `url`, `notes`; eccezioni `UpdateCheckFailed`, `NoReleasePublished`. Endpoint `GET /api/updates/check` → `200` con quel corpo, oppure `502` con codice `update_check_failed` o `update_no_release`.

- [ ] **Step 1: Scrivere i test che falliscono**

Creare `backend/tests/test_update_check.py`:

```python
"""Tre esiti, e restano tre. Il terzo — "non è stato possibile controllare" —
non deve mai assomigliare al primo."""
import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import update_check as uc


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def _release(tag: str) -> dict:
    return {"tag_name": tag, "html_url": f"https://esempio.invalid/{tag}",
            "body": "note di rilascio"}


def test_ce_ne_una_piu_recente(monkeypatch):
    monkeypatch.setattr(uc, "app_version", lambda: "0.9.0")
    with _client(lambda r: httpx.Response(200, json=_release("v0.10.0"))) as c:
        esito = uc.check(client=c)
    assert esito["update_available"] is True
    assert esito["latest"] == "0.10.0"
    assert esito["current"] == "0.9.0"
    assert esito["url"].endswith("v0.10.0")
    assert esito["notes"] == "note di rilascio"


def test_siamo_aggiornati(monkeypatch):
    monkeypatch.setattr(uc, "app_version", lambda: "0.9.0")
    with _client(lambda r: httpx.Response(200, json=_release("v0.9.0"))) as c:
        esito = uc.check(client=c)
    assert esito["update_available"] is False
    assert esito["latest"] == "0.9.0"


def test_una_release_piu_vecchia_non_e_un_aggiornamento(monkeypatch):
    monkeypatch.setattr(uc, "app_version", lambda: "0.10.0")
    with _client(lambda r: httpx.Response(200, json=_release("v0.9.0"))) as c:
        assert uc.check(client=c)["update_available"] is False


def test_il_404_non_diventa_mai_sei_aggiornato(monkeypatch):
    """GitHub risponde 404 sia per un repository irraggiungibile sia per uno
    pubblico senza release, e le due cose non si distinguono. Dire "sei
    aggiornato" a chi non ha potuto verificare niente è l'errore che questa
    separazione esiste per impedire."""
    monkeypatch.setattr(uc, "app_version", lambda: "0.9.0")
    with _client(lambda r: httpx.Response(404, json={"message": "Not Found"})) as c:
        with pytest.raises(uc.NoReleasePublished):
            uc.check(client=c)


def test_errore_di_rete(monkeypatch):
    monkeypatch.setattr(uc, "app_version", lambda: "0.9.0")

    def esplodi(r):
        raise httpx.ConnectTimeout("timeout")

    with _client(esplodi) as c:
        with pytest.raises(uc.UpdateCheckFailed):
            uc.check(client=c)


def test_rate_limit(monkeypatch):
    monkeypatch.setattr(uc, "app_version", lambda: "0.9.0")
    with _client(lambda r: httpx.Response(403, json={"message": "rate limit"})) as c:
        with pytest.raises(uc.UpdateCheckFailed):
            uc.check(client=c)


def test_tag_illeggibile_non_e_un_aggiornamento(monkeypatch):
    monkeypatch.setattr(uc, "app_version", lambda: "0.9.0")
    with _client(lambda r: httpx.Response(200, json=_release("release-di-prova"))) as c:
        esito = uc.check(client=c)
    assert esito["update_available"] is False


def test_endpoint_esito_positivo(monkeypatch):
    monkeypatch.setattr(uc, "app_version", lambda: "0.9.0")
    monkeypatch.setattr(uc, "check", lambda client=None: {
        "current": "0.9.0", "latest": "0.10.0", "update_available": True,
        "url": "https://esempio.invalid/v0.10.0", "notes": "note"})
    body = TestClient(app).get("/api/updates/check").json()
    assert body["update_available"] is True


def test_endpoint_non_verificabile(monkeypatch):
    def fallisci(client=None):
        raise uc.UpdateCheckFailed("rete assente")

    monkeypatch.setattr(uc, "check", fallisci)
    res = TestClient(app).get("/api/updates/check")
    assert res.status_code == 502
    assert res.json()["detail"]["code"] == "update_check_failed"


def test_endpoint_nessuna_release(monkeypatch):
    def nessuna(client=None):
        raise uc.NoReleasePublished("404")

    monkeypatch.setattr(uc, "check", nessuna)
    res = TestClient(app).get("/api/updates/check")
    assert res.status_code == 502
    assert res.json()["detail"]["code"] == "update_no_release"
```

- [ ] **Step 2: Eseguire e verificare il fallimento**

```bash
cd backend && /Users/lucadenegri/Develop/DJProject01/backend/.venv/bin/python -m pytest tests/test_update_check.py -q
```
Atteso: `ModuleNotFoundError: No module named 'app.services.update_check'`.

- [ ] **Step 3: Implementare il servizio**

Creare `backend/app/services/update_check.py`:

```python
"""Esiste una versione più recente di quella in esecuzione?

Tre esiti, e devono restare tre: aggiornato, disponibile, non verificabile.
Il terzo non può mai degradare nel primo — dire "sei aggiornato" a chi non ha
potuto controllare niente è il modo in cui questa funzione fallisce peggio.
"""
from __future__ import annotations

import logging

import httpx

from app.core.version import app_version, is_newer, parse_version

log = logging.getLogger(__name__)

# Costante, non configurazione: cambiarla è un cambio di codice.
GITHUB_REPO = "lucadenegri-dev/Cratory"
_TIMEOUT_S = 10.0


class UpdateCheckFailed(Exception):
    """Non è stato possibile stabilire se ci sono aggiornamenti."""


class NoReleasePublished(UpdateCheckFailed):
    """GitHub ha risposto 404. Ambiguo per costruzione: o il repository non è
    raggiungibile, o è pubblico ma non ha ancora nessuna release. Non si
    distinguono dalla risposta, e nessuna delle due autorizza a dire che si è
    aggiornati."""


def check(client: httpx.Client | None = None) -> dict:
    corrente = app_version()
    proprio = client is None
    client = client or httpx.Client(follow_redirects=True)
    try:
        res = client.get(
            f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest",
            headers={"Accept": "application/vnd.github+json"},
            timeout=_TIMEOUT_S,
        )
    except httpx.HTTPError as exc:
        log.info("controllo aggiornamenti fallito: %s", exc)
        raise UpdateCheckFailed(str(exc)) from exc
    finally:
        if proprio:
            client.close()

    if res.status_code == 404:
        raise NoReleasePublished("nessuna release pubblicata, o repository non raggiungibile")
    if res.status_code != 200:
        raise UpdateCheckFailed(f"HTTP {res.status_code}")

    try:
        corpo = res.json()
    except ValueError as exc:
        raise UpdateCheckFailed("risposta non leggibile") from exc

    tag = str(corpo.get("tag_name") or "")
    numeri = parse_version(tag)
    return {
        "current": corrente,
        # Il tag porta la `v`, la versione dell'app no: si normalizza qui, una
        # volta, invece di lasciare che ogni chiamante se ne ricordi.
        "latest": ".".join(str(n) for n in numeri) if numeri else None,
        "update_available": is_newer(tag, corrente),
        "url": corpo.get("html_url"),
        "notes": corpo.get("body") or None,
    }
```

- [ ] **Step 4: Esporre l'endpoint**

Aggiungere in `backend/app/routers/updates.py`:

```python
from app.core.http_errors import api_error
from app.services import update_check


class UpdateCheck(BaseModel):
    current: str
    latest: str | None = None
    update_available: bool = False
    url: str | None = None
    # Testo scritto su GitHub, non nostro: è l'unica prosa che il backend
    # trasmette, ed è contenuto di terzi (come la coda del log di slskd).
    notes: str | None = None


@router.get("/api/updates/check", response_model=UpdateCheck)
def check_updates() -> UpdateCheck:
    try:
        return UpdateCheck(**update_check.check())
    except update_check.NoReleasePublished as exc:
        raise api_error(502, "update_no_release", str(exc)) from exc
    except update_check.UpdateCheckFailed as exc:
        raise api_error(502, "update_check_failed", str(exc), reason=str(exc)) from exc
```

L'ordine dei due `except` conta: `NoReleasePublished` eredita da `UpdateCheckFailed`, quindi se venisse dopo non verrebbe mai raggiunto e il `404` perderebbe il suo codice.

- [ ] **Step 5: Eseguire i test**

```bash
cd backend && /Users/lucadenegri/Develop/DJProject01/backend/.venv/bin/python -m pytest tests/test_update_check.py -q
```
Atteso: `10 passed`.

- [ ] **Step 6: Provare che l'invariante regga**

Cambiare il ramo del `404` perché ritorni `{"update_available": False, …}` invece di sollevare, rieseguire, verificare che `test_il_404_non_diventa_mai_sei_aggiornato` fallisca, ripristinare, ripulire i `__pycache__`. Riportare cosa si è osservato.

- [ ] **Step 7: Suite intera e commit**

```bash
cd backend && /Users/lucadenegri/Develop/DJProject01/backend/.venv/bin/python -m pytest tests -q
```

```bash
git add backend/app/services/update_check.py backend/app/routers/updates.py backend/tests/test_update_check.py
git commit -m "feat(updates): controllo aggiornamenti con i tre esiti distinti"
```

---

## Task 4: Il bottone in Impostazioni

**Files:**
- Create: `frontend/lib/api/updates.ts`, `frontend/components/settings/version-card.tsx`, `frontend/tests/version-card.test.tsx`
- Modify: `frontend/lib/api.ts`, `frontend/lib/i18n/en.ts`, `frontend/lib/i18n/it.ts`, `frontend/app/settings/page.tsx`

**Interfaces:**
- Consumes: `GET /api/version`, `GET /api/updates/check`.
- Produces: `getAppVersion(): Promise<{version: string}>`; `checkUpdates(): Promise<UpdateCheckResult>` con `UpdateCheckResult = {current: string; latest: string | null; update_available: boolean; url: string | null; notes: string | null}`; `<VersionCard />`.

- [ ] **Step 1: Scrivere il test che fallisce**

Creare `frontend/tests/version-card.test.tsx`:

```tsx
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { VersionCard } from "@/components/settings/version-card";

const getAppVersion = vi.fn();
const checkUpdates = vi.fn();
vi.mock("@/lib/api", () => ({
  errText: (e: unknown) => String((e as Error)?.message ?? e),
  getAppVersion: () => getAppVersion(),
  checkUpdates: () => checkUpdates(),
}));

describe("VersionCard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getAppVersion.mockResolvedValue({ version: "0.9.0" });
  });
  afterEach(cleanup);

  it("mostra la versione in uso senza che si prema niente", async () => {
    render(<VersionCard />);
    expect(await screen.findByText(/0\.9\.0/)).toBeTruthy();
  });

  it("quando c'è una versione nuova mostra numero, note e link", async () => {
    checkUpdates.mockResolvedValue({
      current: "0.9.0", latest: "0.10.0", update_available: true,
      url: "https://esempio.invalid/v0.10.0", notes: "cose nuove",
    });
    render(<VersionCard />);
    fireEvent.click(await screen.findByRole("button"));
    expect(await screen.findByText(/0\.10\.0/)).toBeTruthy();
    expect(screen.getByText(/cose nuove/)).toBeTruthy();
    const link = screen.getByRole("link") as HTMLAnchorElement;
    expect(link.href).toContain("v0.10.0");
  });

  it("quando si è aggiornati lo dice e non mostra link", async () => {
    checkUpdates.mockResolvedValue({
      current: "0.9.0", latest: "0.9.0", update_available: false,
      url: null, notes: null,
    });
    render(<VersionCard />);
    fireEvent.click(await screen.findByRole("button"));
    await waitFor(() => expect(checkUpdates).toHaveBeenCalled());
    expect(screen.queryByRole("link")).toBeNull();
  });

  it("un controllo fallito NON viene presentato come 'sei aggiornato'", async () => {
    // È l'invariante della funzione: "non lo so" e "sei a posto" sono cose
    // diverse, e confonderle è il modo in cui questa schermata mente.
    checkUpdates.mockRejectedValue(new Error("Impossibile controllare"));
    render(<VersionCard />);
    fireEvent.click(await screen.findByRole("button"));
    expect(await screen.findByText(/impossibile controllare/i)).toBeTruthy();
    expect(screen.queryByText(/aggiornato|up to date/i)).toBeNull();
  });
});
```

- [ ] **Step 2: Eseguire e verificare il fallimento**

```bash
cd frontend && npm run test:unit -- tests/version-card.test.tsx
```
Atteso: FAIL — il componente non esiste.

- [ ] **Step 3: Il client**

Creare `frontend/lib/api/updates.ts`:

```ts
import { apiGet } from "./client";

export type UpdateCheckResult = {
  current: string;
  latest: string | null;
  update_available: boolean;
  url: string | null;
  /** Note scritte su GitHub: contenuto di terzi, non testo dell'app. */
  notes: string | null;
};

/** La versione in esecuzione. */
export function getAppVersion() {
  return apiGet<{ version: string }>("/api/version");
}

/** Esiste una versione più recente? Solleva se non è stato possibile
 *  stabilirlo — "non lo so" non deve somigliare a "sei aggiornato". */
export function checkUpdates() {
  return apiGet<UpdateCheckResult>("/api/updates/check");
}
```

In `frontend/lib/api.ts`, aggiungere in fondo all'elenco:

```ts
export * from "./api/updates";
```

- [ ] **Step 4: I testi, in entrambe le lingue**

In `frontend/lib/i18n/en.ts`, dentro `settings`:

```ts
    versionHeading: "Version",
    versionCurrent: (v: string) => `You are running ${v}`,
    versionCheck: "Check for updates",
    versionChecking: "Checking…",
    versionUpToDate: "You are on the latest version",
    versionAvailable: (v: string) => `Version ${v} is available`,
    versionOpenRelease: "Open the release",
    versionNotesHeading: "Release notes",
```

e in `frontend/lib/i18n/it.ts`:

```ts
    versionHeading: "Versione",
    versionCurrent: (v: string) => `Stai usando la ${v}`,
    versionCheck: "Controlla aggiornamenti",
    versionChecking: "Controllo in corso…",
    versionUpToDate: "Sei all'ultima versione",
    versionAvailable: (v: string) => `È disponibile la versione ${v}`,
    versionOpenRelease: "Apri il rilascio",
    versionNotesHeading: "Note di rilascio",
```

Aggiungere anche i due codici d'errore, in `errors`, in entrambe le lingue:

```ts
    // en.ts
    update_check_failed: (p: Record<string, string>) =>
      `Could not check for updates: ${p.reason ?? ""}`,
    update_no_release: "Could not check: no release has been published yet, or the repository is unreachable.",
    // it.ts
    update_check_failed: (p: Record<string, string>) =>
      `Impossibile controllare gli aggiornamenti: ${p.reason ?? ""}`,
    update_no_release: "Impossibile controllare: non è ancora stata pubblicata nessuna release, oppure il repository non è raggiungibile.",
```

**`update_check_failed` è una funzione, non una stringa, e non è un dettaglio.**
Il backend lo solleva con un parametro `reason` che porta la causa vera (un
timeout, un `HTTP 403` di rate limit). Una voce statica farebbe scartare quel
parametro dal livello di traduzione, e il risultato sarebbe **peggiore che non
avere la voce**: senza, il fallback mostrerebbe il messaggio del backend, che la
causa ce l'ha. È lo stesso difetto già trovato una volta su
`slskd_start_failed`; guardare come è scritta quella voce prima di scrivere
questa. `update_no_release` invece resta statica, perché non porta parametri:
il suo testo dice già tutto quello che si sa.

- [ ] **Step 5: Il componente**

Creare `frontend/components/settings/version-card.tsx`:

```tsx
"use client";

import { useEffect, useState } from "react";
import { ExternalLink } from "lucide-react";
import { checkUpdates, errText, getAppVersion, type UpdateCheckResult } from "@/lib/api";
import { Button } from "@/components/ui";
import { useT } from "@/lib/i18n";

/* La versione in uso e il controllo degli aggiornamenti.

   Tre esiti e restano tre: aggiornato, disponibile, non verificabile. Il terzo
   ha il suo posto e il suo tono — presentarlo come "sei aggiornato" farebbe
   dire alla schermata una cosa che non sa. */
export function VersionCard() {
  const t = useT();
  const [versione, setVersione] = useState<string | null>(null);
  const [esito, setEsito] = useState<UpdateCheckResult | null>(null);
  const [errore, setErrore] = useState<string | null>(null);
  const [inCorso, setInCorso] = useState(false);

  useEffect(() => {
    getAppVersion().then((r) => setVersione(r.version)).catch(() => setVersione(null));
  }, []);

  const controlla = async () => {
    setInCorso(true);
    setErrore(null);
    setEsito(null);
    try {
      setEsito(await checkUpdates());
    } catch (e) {
      setErrore(errText(e));
    } finally {
      setInCorso(false);
    }
  };

  return (
    <div className="border border-border p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <span className="text-sm text-fg">
          {versione ? t.settings.versionCurrent(versione) : "—"}
        </span>
        <Button size="sm" variant="outline" disabled={inCorso} onClick={controlla}>
          {inCorso ? t.settings.versionChecking : t.settings.versionCheck}
        </Button>
      </div>

      {errore && <p className="mt-3 text-xs text-danger">{errore}</p>}

      {esito && !esito.update_available && (
        <p className="mt-3 text-xs text-muted">{t.settings.versionUpToDate}</p>
      )}

      {esito?.update_available && (
        <div className="mt-3 border-t border-border pt-3">
          <p className="text-sm text-fg-strong">{t.settings.versionAvailable(esito.latest ?? "")}</p>
          {esito.notes && (
            <>
              <p className="mt-2 text-[10px] uppercase tracking-wider text-faint">
                {t.settings.versionNotesHeading}
              </p>
              {/* Testo di GitHub, non nostro: si mostra come citazione. */}
              <pre className="mt-1 max-h-40 overflow-auto whitespace-pre-wrap border-l-2 border-border pl-3 text-xs text-muted">
                {esito.notes}
              </pre>
            </>
          )}
          {esito.url && (
            <a href={esito.url} target="_blank" rel="noreferrer" className="mt-2 inline-block">
              <Button size="sm" variant="outline">
                <ExternalLink size={14} /> {t.settings.versionOpenRelease}
              </Button>
            </a>
          )}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 6: Montarlo nella pagina**

In `frontend/app/settings/page.tsx`, seguendo il pattern delle altre sezioni (un'intestazione minuscola seguita dal contenuto), aggiungere in fondo:

```tsx
      <div className="mb-2 mt-8 text-[10px] uppercase tracking-wider text-muted">{t.settings.versionHeading}</div>
      <VersionCard />
```

con l'import corrispondente.

- [ ] **Step 7: Verificare**

```bash
cd frontend && npm run test:unit && npx tsc --noEmit && npm run lint && npm run build
```
Atteso: tutto verde; lint coi soli 4 warning preesistenti in file non toccati.

- [ ] **Step 8: Commit**

```bash
git add frontend/lib frontend/components/settings/version-card.tsx frontend/app/settings/page.tsx frontend/tests/version-card.test.tsx
git commit -m "feat(updates): versione e controllo aggiornamenti in Impostazioni"
```

---

## Task 5: Documentazione

**Files:**
- Modify: `docs/API.md`, `docs/ARCHITECTURE.md`, `README.md`, `PROGRESS.md`

- [ ] **Step 1: `docs/API.md`**

Aggiungere `GET /api/version` e `GET /api/updates/check`, con la forma della risposta e **i due codici d'errore**, spiegando perché il `404` di GitHub non diventa "nessun aggiornamento".

- [ ] **Step 2: `docs/ARCHITECTURE.md`**

Una voce breve: la versione ha una fonte sola (`VERSION` nella radice), il seam `CRATORY_VERSION` esiste per il bundle Tauri come `CRATORY_BIN_DIR` esiste per i binari, e il confronto è numerico.

- [ ] **Step 3: `README.md`**

Nella sezione dei rilasci — o creandone una — dire come si pubblica una versione: si aggiorna `VERSION` e `frontend/package.json` insieme, si tagga `vX.Y.Z`, si crea la release su GitHub con le note. Dire anche che il controllo dal bottone funziona solo con il repository pubblico.

- [ ] **Step 4: `PROGRESS.md`**

Una voce con la data.

- [ ] **Step 5: Verifica finale**

```bash
cd backend && /Users/lucadenegri/Develop/DJProject01/backend/.venv/bin/python -m pytest tests -q
```
```bash
cd frontend && npm run test:unit && npm run lint && npm run build
```
Riportare l'output reale, non una previsione.

- [ ] **Step 6: Commit**

```bash
git add docs README.md PROGRESS.md
git commit -m "docs(updates): versione unica, rilasci e controllo aggiornamenti"
```
