# Folder Picker (dialog nativo macOS, porting da Cratory) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Pulsante "Sfoglia…" accanto ai due campi a percorso assoluto di Sortory (path in "Add root" e destinazione per-root in Settings) che fa aprire al backend il dialog nativo del Finder e riporta il percorso scelto nel campo.

**Architecture:** Porting 1:1 del servizio `native_picker` di Cratory (versione post-fix, con `with timeout of 300 seconds` nello script) esposto da un router nuovo `picker.py` (`GET /api/picker/availability`, `POST /api/picker/pick`). Frontend: componente riusabile `PathPickerButton` + hook `usePickerAvailability`, montato in `AddSource` e nella riga destinazione (`RootRow`) di Settings. Niente auto-salvataggio: il pick riempie solo l'input.

**Tech Stack:** FastAPI + Pydantic, pytest con monkeypatch (osascript mai eseguito nei test), Next.js 16 + React 19. NIENTE vitest: il frontend di Sortory non ha unit test e questo piano non li introduce (lint + build + verifica live).

**Spec:** `docs/superpowers/specs/2026-08-08-folder-picker-design.md`
**Sorgente del porting (fonte di verità):** `/Users/lucadenegri/Develop/DJProject01/backend/app/services/native_picker.py` e `/Users/lucadenegri/Develop/DJProject01/backend/tests/test_native_picker.py` (Cratory, post-fix review). Il codice è riportato per intero qui sotto; se differisce dai file Cratory, vincono i file Cratory.

## Global Constraints

- Solo macOS: su altre piattaforme `availability` è `false` e i pulsanti NON compaiono.
- Il percorso scelto riempie SOLO l'input del campo: add/save restano manuali; in Settings, `target_root` vuoto continua a significare "rename only".
- Router HTTP-only; logica osascript in `services/`.
- Errori col pattern `api_error(status, code, message)` di `app/core/http_errors.py`, codici `picker_unavailable` e `picker_busy` (409); 422 su `kind` non valido.
- Timeout: `TIMEOUT_SECONDS = 300.0` dichiarato ANCHE nello script AppleScript (`with timeout of 300 seconds` — il default degli Apple Event è 120s); `SUBPROCESS_TIMEOUT_SECONDS = TIMEOUT_SECONDS + 10.0` come rete di sicurezza.
- i18n: `Dictionary` è il tipo di `en.ts` — chiavi prima lì, poi speculari in `it.ts`. Nuove chiavi: `common.browseButton` e nel blocco `errors` `picker_unavailable`/`picker_busy`.
- Next 16: leggere `frontend/CLAUDE.md` se esiste; in ogni caso non riformattare gli a-capo JSX esistenti (Next 16 mangia lo spazio a fine riga tra inline element e testo).
- Commit frequenti stile repo (`feat(...)`), SENZA alcun trailer Co-Authored-By.
- Test backend: `cd /Users/lucadenegri/Develop/DjOrganizer01/backend && .venv/bin/python -m pytest tests/<file> -v` (suite completa: `... -m pytest tests -q`, ~295 test).

---

### Task 1: Servizio backend `native_picker` (porting)

**Files:**
- Create: `backend/app/services/native_picker.py`
- Test: `backend/tests/test_native_picker.py`

**Interfaces:**
- Consumes: niente (solo stdlib).
- Produces (usati dal Task 2): `picker_available() -> bool`; `pick_path(kind: str, start: str | None = None, prompt: str | None = None, *, runner=subprocess.run) -> str | None`; `build_script(kind, start, prompt) -> str`; costanti `TIMEOUT_SECONDS`, `SUBPROCESS_TIMEOUT_SECONDS`; eccezioni `PickerBusyError`, `PickerUnavailableError`.

- [ ] **Step 1: Scrivi i test (falliranno)**

Crea `backend/tests/test_native_picker.py`:

```python
"""Servizio native_picker (porting da Cratory): subprocess sempre mockato."""
import subprocess

import pytest

from app.services import native_picker as np


def _proc(returncode: int = 0, stdout: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=returncode,
                                       stdout=stdout, stderr="")


def _force_available(monkeypatch):
    monkeypatch.setattr(np, "picker_available", lambda: True)


def test_available_solo_su_darwin_con_osascript(monkeypatch):
    monkeypatch.setattr(np.sys, "platform", "darwin")
    monkeypatch.setattr(np.shutil, "which", lambda _: "/usr/bin/osascript")
    assert np.picker_available() is True


def test_available_falso_senza_osascript(monkeypatch):
    monkeypatch.setattr(np.sys, "platform", "darwin")
    monkeypatch.setattr(np.shutil, "which", lambda _: None)
    assert np.picker_available() is False


def test_available_falso_su_linux(monkeypatch):
    monkeypatch.setattr(np.sys, "platform", "linux")
    monkeypatch.setattr(np.shutil, "which", lambda _: "/usr/bin/osascript")
    assert np.picker_available() is False


def test_pick_folder_strippa_newline_e_slash_finale(monkeypatch):
    _force_available(monkeypatch)
    got = np.pick_path("folder", runner=lambda *a, **k: _proc(stdout="/Users/x/Music/\n"))
    assert got == "/Users/x/Music"


def test_pick_file_non_strippa_il_nome(monkeypatch):
    _force_available(monkeypatch)
    got = np.pick_path("file", runner=lambda *a, **k: _proc(stdout="/Users/x/slskd.yml\n"))
    assert got == "/Users/x/slskd.yml"


def test_pick_folder_root_resta_root(monkeypatch):
    _force_available(monkeypatch)
    got = np.pick_path("folder", runner=lambda *a, **k: _proc(stdout="/\n"))
    assert got == "/"


def test_annullo_utente_ritorna_none(monkeypatch):
    # osascript esce con codice 1 (error -128) quando l'utente annulla
    _force_available(monkeypatch)
    assert np.pick_path("folder", runner=lambda *a, **k: _proc(returncode=1)) is None


def test_timeout_ritorna_none(monkeypatch):
    _force_available(monkeypatch)

    def runner(*a, **k):
        raise subprocess.TimeoutExpired(cmd="osascript", timeout=np.SUBPROCESS_TIMEOUT_SECONDS)

    assert np.pick_path("folder", runner=runner) is None


def test_non_disponibile_solleva(monkeypatch):
    monkeypatch.setattr(np, "picker_available", lambda: False)
    with pytest.raises(np.PickerUnavailableError):
        np.pick_path("folder")


def test_lock_occupato_solleva_busy(monkeypatch):
    _force_available(monkeypatch)
    assert np._lock.acquire(blocking=False)
    try:
        with pytest.raises(np.PickerBusyError):
            np.pick_path("folder", runner=lambda *a, **k: _proc(stdout="/x\n"))
    finally:
        np._lock.release()


def test_lock_rilasciato_dopo_il_pick(monkeypatch):
    _force_available(monkeypatch)
    np.pick_path("folder", runner=lambda *a, **k: _proc(stdout="/x\n"))
    assert np._lock.acquire(blocking=False)  # se il lock fosse rimasto preso, fallirebbe
    np._lock.release()


def test_runner_riceve_subprocess_timeout_e_osascript(monkeypatch):
    _force_available(monkeypatch)
    seen: dict = {}

    def runner(cmd, **kwargs):
        seen["cmd"] = cmd
        seen["timeout"] = kwargs.get("timeout")
        return _proc(stdout="/x\n")

    np.pick_path("folder", runner=runner)
    assert seen["cmd"][0] == "osascript"
    assert seen["timeout"] == np.SUBPROCESS_TIMEOUT_SECONDS


def test_build_script_folder_vs_file():
    assert "choose folder" in np.build_script("folder", None, None)
    assert "choose file" in np.build_script("file", None, None)


def test_build_script_contiene_timeout_esplicito_a_300s():
    for kind in ("folder", "file"):
        script = np.build_script(kind, None, None)
        assert "with timeout of 300 seconds" in script
        assert "end timeout" in script


def test_build_script_start_esistente_diventa_default_location(tmp_path):
    script = np.build_script("folder", str(tmp_path), None)
    assert f'default location (POSIX file "{tmp_path}")' in script


def test_build_script_start_inesistente_ignorato():
    script = np.build_script("folder", "/nope/does/not/exist", None)
    assert "default location" not in script


def test_build_script_prompt_con_escape_dei_doppi_apici():
    script = np.build_script("folder", None, 'Cartella "libreria"')
    assert 'with prompt "Cartella \\"libreria\\""' in script
```

- [ ] **Step 2: Verifica che falliscano**

Run: `cd /Users/lucadenegri/Develop/DjOrganizer01/backend && .venv/bin/python -m pytest tests/test_native_picker.py -v`
Expected: ERROR `ModuleNotFoundError: No module named 'app.services.native_picker'`.

- [ ] **Step 3: Implementa il servizio**

Crea `backend/app/services/native_picker.py` — copia 1:1 da `/Users/lucadenegri/Develop/DJProject01/backend/app/services/native_picker.py`; il contenuto atteso è:

```python
"""Dialog nativo macOS (Finder) per scegliere cartelle o file, via osascript.

Solo macOS: `picker_available()` fa da guardia. Il dialog è un'interazione
utente sulla macchina del backend: un lock di modulo impedisce due dialog
contemporanei, il timeout evita worker appesi se il dialog resta ignorato.
Annullo e timeout diventano `None` (nessuna scelta), mai eccezioni.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import threading
from pathlib import Path

TIMEOUT_SECONDS = 300.0
# Leggermente sopra TIMEOUT_SECONDS: lascia il tempo allo script AppleScript
# (con il suo `with timeout of` interno) di uscire da solo prima che il kill
# del subprocess intervenga.
SUBPROCESS_TIMEOUT_SECONDS = TIMEOUT_SECONDS + 10.0

_lock = threading.Lock()


class PickerBusyError(Exception):
    """Un dialog di scelta è già aperto."""


class PickerUnavailableError(Exception):
    """Piattaforma non macOS oppure osascript assente."""


def picker_available() -> bool:
    return sys.platform == "darwin" and shutil.which("osascript") is not None


def _escape(text: str) -> str:
    """Escape per stringhe AppleScript tra doppi apici."""
    return text.replace("\\", "\\\\").replace('"', '\\"')


def build_script(kind: str, start: str | None, prompt: str | None) -> str:
    """AppleScript `choose folder`/`choose file` dentro System Events attivato:
    porta il dialog in primo piano anche se il backend gira in background.
    `start` diventa `default location` solo se è una directory esistente.

    Il `choose` gira dentro un blocco `with timeout of` esplicito: l'Apple
    Event verso System Events ha di default un reply timeout di 120s, troppo
    poco se l'utente lascia il dialog aperto più a lungo. Lo estendiamo a
    `TIMEOUT_SECONDS` per allinearlo al timeout del subprocess."""
    choose = "choose folder" if kind == "folder" else "choose file"
    if prompt:
        choose += f' with prompt "{_escape(prompt)}"'
    if start:
        start_dir = Path(start).expanduser()
        if start_dir.is_dir():
            choose += f' default location (POSIX file "{_escape(str(start_dir))}")'
    return (
        'tell application "System Events"\n'
        "activate\n"
        f"with timeout of {int(TIMEOUT_SECONDS)} seconds\n"
        f"POSIX path of ({choose})\n"
        "end timeout\n"
        "end tell"
    )


def pick_path(kind: str, start: str | None = None, prompt: str | None = None,
              *, runner=subprocess.run) -> str | None:
    """Percorso scelto nel dialog, o `None` se l'utente annulla o il dialog scade.

    `runner` ha la firma di `subprocess.run` ed è iniettabile nei test:
    osascript reale mai eseguito in CI."""
    if not picker_available():
        raise PickerUnavailableError
    if not _lock.acquire(blocking=False):
        raise PickerBusyError
    try:
        try:
            proc = runner(
                ["osascript", "-e", build_script(kind, start, prompt)],
                capture_output=True, text=True, timeout=SUBPROCESS_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired:
            return None
        if proc.returncode != 0:  # annullo utente (error -128) o errore script
            return None
        path = proc.stdout.strip()
        if kind == "folder":
            path = path.rstrip("/") or "/"  # `choose folder` termina con "/"
        return path or None
    finally:
        _lock.release()
```

- [ ] **Step 4: Verifica che passino**

Run: `cd /Users/lucadenegri/Develop/DjOrganizer01/backend && .venv/bin/python -m pytest tests/test_native_picker.py -v`
Expected: 16 PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/native_picker.py backend/tests/test_native_picker.py
git commit -m "feat(picker): servizio native_picker portato da Cratory"
```

---

### Task 2: Router `/api/picker`

**Files:**
- Create: `backend/app/routers/picker.py`
- Modify: `backend/app/main.py` (import dei router e blocco `include_router`, righe ~39-51)
- Test: `backend/tests/test_picker_router.py`

**Interfaces:**
- Consumes (dal Task 1): `native_picker.picker_available()`, `native_picker.pick_path(kind, start, prompt)`, `PickerBusyError`, `PickerUnavailableError`.
- Produces (usati dal Task 3): `GET /api/picker/availability` → `{"available": bool}`; `POST /api/picker/pick` `{kind, start?, prompt?}` → `{"path": str|null}`; 409 `picker_unavailable`/`picker_busy`; 422 su kind non valido.

- [ ] **Step 1: Scrivi i test (falliranno)**

Crea `backend/tests/test_picker_router.py`:

```python
"""Router /api/picker: il servizio native_picker è sempre monkeypatchato."""
from fastapi.testclient import TestClient

from app.main import app
from app.services import native_picker

client = TestClient(app)


def test_availability_riflette_il_servizio(monkeypatch):
    monkeypatch.setattr(native_picker, "picker_available", lambda: True)
    assert client.get("/api/picker/availability").json() == {"available": True}
    monkeypatch.setattr(native_picker, "picker_available", lambda: False)
    assert client.get("/api/picker/availability").json() == {"available": False}


def test_pick_ritorna_il_percorso(monkeypatch):
    seen: dict = {}

    def fake_pick(kind, start=None, prompt=None):
        seen.update(kind=kind, start=start, prompt=prompt)
        return "/Users/x/Music"

    monkeypatch.setattr(native_picker, "pick_path", fake_pick)
    r = client.post("/api/picker/pick",
                    json={"kind": "folder", "start": "/Users/x", "prompt": "Libreria"})
    assert r.status_code == 200
    assert r.json() == {"path": "/Users/x/Music"}
    assert seen == {"kind": "folder", "start": "/Users/x", "prompt": "Libreria"}


def test_pick_annullato_ritorna_path_null(monkeypatch):
    monkeypatch.setattr(native_picker, "pick_path", lambda *a, **k: None)
    r = client.post("/api/picker/pick", json={"kind": "file"})
    assert r.status_code == 200
    assert r.json() == {"path": None}


def test_pick_non_disponibile_409(monkeypatch):
    def raise_unavailable(*a, **k):
        raise native_picker.PickerUnavailableError

    monkeypatch.setattr(native_picker, "pick_path", raise_unavailable)
    r = client.post("/api/picker/pick", json={"kind": "folder"})
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "picker_unavailable"


def test_pick_occupato_409(monkeypatch):
    def raise_busy(*a, **k):
        raise native_picker.PickerBusyError

    monkeypatch.setattr(native_picker, "pick_path", raise_busy)
    r = client.post("/api/picker/pick", json={"kind": "folder"})
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "picker_busy"


def test_kind_non_valido_422():
    assert client.post("/api/picker/pick", json={"kind": "symlink"}).status_code == 422
```

- [ ] **Step 2: Verifica che falliscano**

Run: `cd /Users/lucadenegri/Develop/DjOrganizer01/backend && .venv/bin/python -m pytest tests/test_picker_router.py -v`
Expected: FAIL con 404 (route inesistenti).

- [ ] **Step 3: Crea il router e registralo**

Crea `backend/app/routers/picker.py`:

```python
"""HTTP per il dialog nativo di scelta percorso. Nessuna logica di business qui."""
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.http_errors import api_error
from app.services import native_picker

router = APIRouter(prefix="/api/picker", tags=["picker"])


class PickAvailabilityOut(BaseModel):
    available: bool


class PickIn(BaseModel):
    kind: Literal["folder", "file"]
    start: str | None = None
    prompt: str | None = None


class PickOut(BaseModel):
    path: str | None


@router.get("/availability", response_model=PickAvailabilityOut)
def availability():
    """Il dialog nativo esiste solo su macOS con osascript nel PATH."""
    return PickAvailabilityOut(available=native_picker.picker_available())


@router.post("/pick", response_model=PickOut)
def pick(body: PickIn):
    """Apre il dialog nativo sulla macchina del backend; path null = annullato."""
    try:
        return PickOut(path=native_picker.pick_path(body.kind, body.start, body.prompt))
    except native_picker.PickerUnavailableError:
        raise api_error(409, "picker_unavailable",
                        "Native picker requires macOS with osascript")
    except native_picker.PickerBusyError:
        raise api_error(409, "picker_busy", "A picker dialog is already open")
```

In `backend/app/main.py`: aggiungi `picker` all'import esistente dei router (`from app.routers import …`) e, dopo `app.include_router(providers.router)` (riga ~51), aggiungi:

```python
app.include_router(picker.router)
```

- [ ] **Step 4: Verifica che passino, più la suite completa**

Run: `cd /Users/lucadenegri/Develop/DjOrganizer01/backend && .venv/bin/python -m pytest tests/test_picker_router.py tests/test_native_picker.py -v && .venv/bin/python -m pytest tests -q`
Expected: tutti PASS (suite ~295+22).

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/picker.py backend/app/main.py backend/tests/test_picker_router.py
git commit -m "feat(picker): endpoint /api/picker per il dialog nativo"
```

---

### Task 3: Frontend — client API, i18n e componente `PathPickerButton`

**Files:**
- Modify: `frontend/lib/api.ts` (aggiungi una sezione PICKER in coda alle funzioni; il file ha `apiGet` e `apiSend(method, path, body)` interni)
- Modify: `frontend/lib/i18n/en.ts` (blocco `common` riga ~29, quello con `save`/`cancel`; blocco `errors` riga ~446) e `frontend/lib/i18n/it.ts` (stessi blocchi, speculari)
- Create: `frontend/components/path-picker-button.tsx`

**Interfaces:**
- Consumes (dal Task 2): gli endpoint `/api/picker/*`.
- Produces (usati dal Task 4): `pickerAvailability(): Promise<{available: boolean}>` e `pickPath(kind: "folder"|"file", start?, prompt?): Promise<{path: string|null}>` esportate da `@/lib/api`; `<PathPickerButton kind start? prompt? onPick(path) onError(message) />` (bottone interno `type="button"`); `usePickerAvailability(): boolean`; chiave `t.common.browseButton`.

Nessun unit test frontend (vincolo di piano): la verifica di questo task è `npm run lint && npm run build`.

- [ ] **Step 1: Client API**

In `frontend/lib/api.ts`, in coda alle funzioni esistenti aggiungi:

```ts
// --- PICKER -----------------------------------------------------------------
/** Il dialog nativo di scelta percorso è disponibile? (solo backend su macOS) */
export function pickerAvailability() {
  return apiGet<{ available: boolean }>("/api/picker/availability");
}
/** Apre il dialog nativo sulla macchina del backend; path null = annullato. */
export function pickPath(kind: "folder" | "file", start?: string, prompt?: string) {
  return apiSend<{ path: string | null }>("POST", "/api/picker/pick", {
    kind, start: start || null, prompt: prompt || null,
  });
}
```

- [ ] **Step 2: i18n**

In `frontend/lib/i18n/en.ts`, nel blocco `common` (vicino a `save: "Save"`):

```ts
    browseButton: "Browse…",
```

Nel blocco `errors` (riga ~446):

```ts
    picker_unavailable: "Native picker unavailable: it requires the backend on macOS.",
    picker_busy: "A picker dialog is already open on the backend machine.",
```

In `frontend/lib/i18n/it.ts`, stessi blocchi:

```ts
    browseButton: "Sfoglia…",
```

```ts
    picker_unavailable: "Dialog nativo non disponibile: richiede il backend su macOS.",
    picker_busy: "Un dialog di scelta è già aperto sulla macchina del backend.",
```

- [ ] **Step 3: Componente**

Crea `frontend/components/path-picker-button.tsx`:

```tsx
"use client";

import { useEffect, useState } from "react";
import { pickerAvailability, pickPath } from "@/lib/api";
import { Button, Spinner } from "./ui";
import { useT } from "@/lib/i18n";

/** Disponibilità del dialog nativo: fetch una volta al mount, errore = false
 *  (i pulsanti Sfoglia semplicemente non compaiono). */
export function usePickerAvailability(): boolean {
  const [ok, setOk] = useState(false);
  useEffect(() => {
    pickerAvailability().then((r) => setOk(r.available)).catch(() => setOk(false));
  }, []);
  return ok;
}

/* Apre il dialog nativo del backend (macOS) e riporta il percorso scelto.
   Il genitore decide se montarlo (usePickerAvailability) e cosa farne: qui
   niente salvataggio, solo la scelta. type="button": il pulsante può vivere
   dentro form senza scatenarne il submit. */
export function PathPickerButton({ kind, start, prompt, onPick, onError }: {
  kind: "folder" | "file";
  start?: string;
  prompt?: string;
  onPick: (path: string) => void;
  onError: (message: string) => void;
}) {
  const t = useT();
  const [busy, setBusy] = useState(false);

  const open = async () => {
    setBusy(true);
    try {
      const r = await pickPath(kind, start, prompt);
      if (r.path) onPick(r.path);
    } catch (e) {
      onError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Button type="button" size="sm" onClick={open} disabled={busy}>
      {busy ? <Spinner /> : t.common.browseButton}
    </Button>
  );
}
```

- [ ] **Step 4: Verifica lint+build**

Run: `cd /Users/lucadenegri/Develop/DjOrganizer01/frontend && npm run lint && npm run build`
Expected: lint senza nuovi errori, build ok (il componente non è ancora usato da nessuna pagina: è atteso che compili senza warning di unused perché è un modulo esportato).

- [ ] **Step 5: Commit**

```bash
git add frontend/lib/api.ts frontend/lib/i18n/en.ts frontend/lib/i18n/it.ts frontend/components/path-picker-button.tsx
git commit -m "feat(picker): client API, i18n e componente PathPickerButton"
```

---

### Task 4: Montaggio in AddSource e Settings + verifica finale

**Files:**
- Modify: `frontend/components/add-source.tsx` (input del path, righe ~34-42)
- Modify: `frontend/app/settings/page.tsx` (componente `RootRow`, righe ~226-268)

**Interfaces:**
- Consumes (dal Task 3): `PathPickerButton`, `usePickerAvailability`, `t.common.browseButton`.
- Produces: UI finale; nessun consumer successivo.

- [ ] **Step 1: Monta in AddSource**

In `frontend/components/add-source.tsx`:

1. Import (dopo gli import esistenti):

```tsx
import { PathPickerButton, usePickerAvailability } from "./path-picker-button";
```

2. In cima al componente, accanto agli altri `useState`:

```tsx
const pickerOk = usePickerAvailability();
```

3. L'`<Input>` del path (righe ~36-42, quello con `placeholder={t.sources.pathPlaceholder}` e `className="w-full"`) va avvolto in una riga flex col pulsante (il path resta a piena larghezza sulla sua riga, come da commento esistente):

```tsx
<div className="flex items-center gap-2">
  <Input
    value={path}
    onChange={(e) => setPath(e.target.value)}
    onKeyDown={(e) => e.key === "Enter" && submit()}
    placeholder={t.sources.pathPlaceholder}
    className="flex-1"
  />
  {pickerOk && (
    <PathPickerButton kind="folder" start={path} prompt={t.sources.addRoot}
      onPick={setPath} onError={setError} />
  )}
</div>
```

(`onError={setError}`: riusa il `<p>` d'errore già presente in fondo al componente. `className` dell'Input passa da `w-full` a `flex-1`.)

- [ ] **Step 2: Monta in Settings (`RootRow`)**

In `frontend/app/settings/page.tsx`:

1. Import (accanto agli import dei componenti):

```tsx
import { PathPickerButton, usePickerAvailability } from "@/components/path-picker-button";
```

2. In `RootRow` (riga ~226), accanto agli altri `useState` aggiungi disponibilità e stato d'errore locale (la riga non ha un banner: lo aggiungiamo piccolo, stile add-source):

```tsx
const pickerOk = usePickerAvailability();
const [pickError, setPickError] = useState<string | null>(null);
```

3. Nella riga dell'input destinazione (righe ~252-259, quella con `placeholder={t.settings.targetPlaceholder}` dentro `<div className="flex items-center gap-2">`), aggiungi il pulsante tra l'`<input>` e il `<Button>` Save:

```tsx
{pickerOk && (
  <PathPickerButton kind="folder" start={target} prompt={t.settings.rowDestination}
    onPick={(p) => { setPickError(null); setTarget(p); }}
    onError={setPickError} />
)}
```

4. Subito dopo la chiusura di quel `<div>` riga input+bottoni, aggiungi:

```tsx
{pickError && <p className="mt-1 text-xs text-danger">{pickError}</p>}
```

- [ ] **Step 3: Verifica lint+build**

Run: `cd /Users/lucadenegri/Develop/DjOrganizer01/frontend && npm run lint && npm run build`
Expected: lint pulito, build ok.

- [ ] **Step 4: Verifica osacompile (script reale, nessun dialog)**

```bash
cd /Users/lucadenegri/Develop/DjOrganizer01/backend && .venv/bin/python -c "
from app.services.native_picker import build_script
import subprocess, tempfile, os
for kind in ('folder','file'):
    s = build_script(kind, None, 'x')
    out = tempfile.mktemp(suffix='.scpt')
    r = subprocess.run(['osacompile','-e',s,'-o',out], capture_output=True, text=True)
    print(kind, r.returncode, r.stderr.strip()); os.path.exists(out) and os.remove(out)
"
```

Expected: `folder 0` e `file 0`.

- [ ] **Step 5: Verifica manuale nel browser (facoltativa ma raccomandata in locale)**

Backend+frontend su, pagina Sources: accanto all'input path compare "Sfoglia…"/"Browse…"; il click apre il Finder; la scelta riempie l'input senza aggiungere la root. Pagina Settings: idem sulla riga destinazione, il salvataggio resta sul pulsante Save.

- [ ] **Step 6: Commit**

```bash
git add frontend/components/add-source.tsx frontend/app/settings/page.tsx
git commit -m "feat(picker): pulsante Sfoglia in Add root e nella destinazione per-root"
```
