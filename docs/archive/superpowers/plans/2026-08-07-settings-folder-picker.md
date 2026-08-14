# Settings Folder Picker (dialog nativo macOS) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Pulsante "Sfoglia…" accanto ai campi percorso in Settings e all'input "percorso esatto" della modale "Collega file locale": fa aprire al backend il dialog nativo del Finder (osascript) e riporta il percorso scelto nel campo.

**Architecture:** Un servizio deterministico `native_picker` (osascript, lock anti-concorrenza, timeout) esposto dal router `files` come `GET /api/files/pick/availability` + `POST /api/files/pick`. Nel frontend un componente riusabile `PathPickerButton` (con hook `usePickerAvailability` condiviso) chiama l'endpoint e passa il percorso al genitore; lo montano `ConfigCard` in Settings (4 campi percorso) e la modale link file (percorso esatto), solo se il picker è disponibile. Salvataggio/collegamento restano manuali (validazione backend invariata).

**Tech Stack:** FastAPI + Pydantic (backend), pytest con monkeypatch (niente osascript reale nei test), Next.js 16 + React + vitest/@testing-library (frontend).

**Spec:** `docs/superpowers/specs/2026-08-07-settings-folder-picker-design.md`

## Global Constraints

- Solo macOS: su altre piattaforme il pulsante NON compare (availability `false`); nessun supporto Windows/headless.
- Il percorso scelto aggiorna SOLO la bozza del campo: niente auto-salvataggio.
- Router HTTP-only: la logica osascript vive in `services/` (regola di layering del progetto).
- Errori HTTP col pattern `api_error(status, code, message)` di `app/core/http_errors.py`: il frontend traduce `code` via il blocco `errors` dei dizionari i18n.
- Timeout dialog: 300 s, trattato come annullo. Dialog concorrenti: 409.
- Frontend: leggere `frontend/CLAUDE.md` prima di toccare pagine (Next 16 ha breaking changes); attenzione agli spazi JSX (Next 16 mangia lo spazio a fine riga: usare `{" "}` se serve).
- Commit frequenti, messaggi in stile repo (`feat(...)`, `test(...)`), **senza** Co-Authored-By.
- Test backend: dal checkout, `cd backend && source .venv/bin/activate && python -m pytest tests/<file> -v` (in un worktree: usare il venv del checkout principale con cwd nel backend del worktree).

---

### Task 1: Servizio backend `native_picker`

**Files:**
- Create: `backend/app/services/native_picker.py`
- Test: `backend/tests/test_native_picker.py`

**Interfaces:**
- Consumes: niente (solo stdlib: `subprocess`, `shutil`, `sys`, `threading`, `pathlib`).
- Produces (usati dal Task 2):
  - `picker_available() -> bool`
  - `pick_path(kind: str, start: str | None = None, prompt: str | None = None, *, runner=subprocess.run) -> str | None`
  - `class PickerBusyError(Exception)`, `class PickerUnavailableError(Exception)`
  - `build_script(kind: str, start: str | None, prompt: str | None) -> str` (interno ma testato)

- [ ] **Step 1: Scrivi i test (falliranno)**

Crea `backend/tests/test_native_picker.py`:

```python
"""Servizio native_picker: dialog macOS via osascript, subprocess sempre mockato."""
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
        raise subprocess.TimeoutExpired(cmd="osascript", timeout=np.TIMEOUT_SECONDS)

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


def test_runner_riceve_timeout_e_osascript(monkeypatch):
    _force_available(monkeypatch)
    seen: dict = {}

    def runner(cmd, **kwargs):
        seen["cmd"] = cmd
        seen["timeout"] = kwargs.get("timeout")
        return _proc(stdout="/x\n")

    np.pick_path("folder", runner=runner)
    assert seen["cmd"][0] == "osascript"
    assert seen["timeout"] == np.TIMEOUT_SECONDS


def test_build_script_folder_vs_file():
    assert "choose folder" in np.build_script("folder", None, None)
    assert "choose file" in np.build_script("file", None, None)


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

```bash
cd backend && source .venv/bin/activate && python -m pytest tests/test_native_picker.py -v
```

Expected: FAIL/ERROR con `ModuleNotFoundError: No module named 'app.services.native_picker'`.

- [ ] **Step 3: Implementa il servizio**

Crea `backend/app/services/native_picker.py`:

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
    `start` diventa `default location` solo se è una directory esistente."""
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
        f"POSIX path of ({choose})\n"
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
                capture_output=True, text=True, timeout=TIMEOUT_SECONDS,
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

```bash
cd backend && source .venv/bin/activate && python -m pytest tests/test_native_picker.py -v
```

Expected: tutti PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/native_picker.py backend/tests/test_native_picker.py
git commit -m "feat(files): servizio native_picker per il dialog macOS via osascript"
```

---

### Task 2: Endpoint `/api/files/pick` + `/api/files/pick/availability`

**Files:**
- Modify: `backend/app/routers/files.py` (attualmente 22 righe: solo `/search`)
- Test: `backend/tests/test_files_pick_router.py`

**Interfaces:**
- Consumes (dal Task 1): `native_picker.picker_available()`, `native_picker.pick_path(kind, start, prompt)`, `PickerBusyError`, `PickerUnavailableError`.
- Produces (usati dal Task 3):
  - `GET /api/files/pick/availability` → `{"available": bool}`
  - `POST /api/files/pick` body `{"kind": "folder"|"file", "start": str|null, "prompt": str|null}` → `{"path": str|null}`; 409 con code `picker_unavailable` o `picker_busy`; 422 su `kind` non valido.

- [ ] **Step 1: Scrivi i test (falliranno)**

Crea `backend/tests/test_files_pick_router.py`:

```python
"""Router /api/files/pick: il servizio native_picker è sempre monkeypatchato."""
from fastapi.testclient import TestClient

from app.main import app
from app.services import native_picker

client = TestClient(app)


def test_availability_riflette_il_servizio(monkeypatch):
    monkeypatch.setattr(native_picker, "picker_available", lambda: True)
    assert client.get("/api/files/pick/availability").json() == {"available": True}
    monkeypatch.setattr(native_picker, "picker_available", lambda: False)
    assert client.get("/api/files/pick/availability").json() == {"available": False}


def test_pick_ritorna_il_percorso(monkeypatch):
    seen: dict = {}

    def fake_pick(kind, start=None, prompt=None):
        seen.update(kind=kind, start=start, prompt=prompt)
        return "/Users/x/Music"

    monkeypatch.setattr(native_picker, "pick_path", fake_pick)
    r = client.post("/api/files/pick",
                    json={"kind": "folder", "start": "/Users/x", "prompt": "Libreria"})
    assert r.status_code == 200
    assert r.json() == {"path": "/Users/x/Music"}
    assert seen == {"kind": "folder", "start": "/Users/x", "prompt": "Libreria"}


def test_pick_annullato_ritorna_path_null(monkeypatch):
    monkeypatch.setattr(native_picker, "pick_path", lambda *a, **k: None)
    r = client.post("/api/files/pick", json={"kind": "file"})
    assert r.status_code == 200
    assert r.json() == {"path": None}


def test_pick_non_disponibile_409(monkeypatch):
    def raise_unavailable(*a, **k):
        raise native_picker.PickerUnavailableError

    monkeypatch.setattr(native_picker, "pick_path", raise_unavailable)
    r = client.post("/api/files/pick", json={"kind": "folder"})
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "picker_unavailable"


def test_pick_occupato_409(monkeypatch):
    def raise_busy(*a, **k):
        raise native_picker.PickerBusyError

    monkeypatch.setattr(native_picker, "pick_path", raise_busy)
    r = client.post("/api/files/pick", json={"kind": "folder"})
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "picker_busy"


def test_kind_non_valido_422():
    assert client.post("/api/files/pick", json={"kind": "symlink"}).status_code == 422
```

- [ ] **Step 2: Verifica che falliscano**

```bash
cd backend && source .venv/bin/activate && python -m pytest tests/test_files_pick_router.py -v
```

Expected: FAIL con 404 sugli endpoint (route inesistenti).

- [ ] **Step 3: Estendi il router**

In `backend/app/routers/files.py`, sostituisci l'intero contenuto con:

```python
"""HTTP per file locali: ricerca e dialog nativo di scelta percorso.
Nessuna logica di business qui."""
from typing import Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.core.http_errors import api_error
from app.services import native_picker
from app.services.file_search import search_audio_files

router = APIRouter(prefix="/api/files", tags=["files"])


class LocalFileOut(BaseModel):
    path: str
    name: str
    format: str | None = None
    size: int | None = None
    source: str


@router.get("/search", response_model=list[LocalFileOut])
def search_files(q: str = Query(default="")):
    """Cerca file audio per nome in LIBRARY_ROOT e nella cartella download slskd."""
    return [LocalFileOut(**h) for h in search_audio_files(q)]


class PickAvailabilityOut(BaseModel):
    available: bool


class PickIn(BaseModel):
    kind: Literal["folder", "file"]
    start: str | None = None
    prompt: str | None = None


class PickOut(BaseModel):
    path: str | None


@router.get("/pick/availability", response_model=PickAvailabilityOut)
def pick_availability():
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

- [ ] **Step 4: Verifica che passino, più il resto della suite**

```bash
cd backend && source .venv/bin/activate && python -m pytest tests/test_files_pick_router.py tests/test_native_picker.py -v && python -m pytest tests -q
```

Expected: tutti PASS (la suite completa conferma che il router esteso non rompe `/search`).

- [ ] **Step 5: Aggiorna docs/API.md**

In `docs/API.md`, nella sezione dei file locali (cerca `files/search`), aggiungi la descrizione dei due endpoint accanto a quella esistente di `/api/files/search`, nello stesso stile della sezione:

```markdown
- `GET /api/files/pick/availability` → `{available}`: il dialog nativo di scelta
  percorso è disponibile (solo macOS con osascript nel PATH).
- `POST /api/files/pick` `{kind: "folder"|"file", start?, prompt?}` → `{path}`:
  apre il dialog nativo (Finder) sulla macchina del backend e ritorna il percorso
  scelto; `path: null` se l'utente annulla o il dialog scade (300 s). 409
  `picker_unavailable` fuori da macOS, 409 `picker_busy` se un dialog è già aperto.
  Usato dal pulsante "Sfoglia…" dei Settings.
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers/files.py backend/tests/test_files_pick_router.py docs/API.md
git commit -m "feat(files): endpoint pick per il dialog nativo di scelta percorso"
```

---

### Task 3: Frontend — client API, i18n e componente `PathPickerButton`

**Files:**
- Modify: `frontend/lib/api/settings.ts` (aggiungi funzioni; oggi importa `apiGet, apiPatch, apiPut` da `./client`)
- Modify: `frontend/lib/i18n/en.ts` e `frontend/lib/i18n/it.ts` (blocchi `settings` ed `errors`)
- Create: `frontend/components/path-picker-button.tsx`
- Test: `frontend/tests/path-picker-button.test.tsx`

**Interfaces:**
- Consumes (dal Task 2): gli endpoint `/api/files/pick*`.
- Produces (usati dai Task 4 e 5):
  - `pickerAvailability(): Promise<{ available: boolean }>` e `pickPath(kind, start?, prompt?): Promise<{ path: string | null }>` esportati dal barrel `@/lib/api`
  - `<PathPickerButton kind start? prompt? onPick(path) onError(message) />` (il bottone interno è `type="button"`: montabile dentro un `<form>` senza scatenarne il submit)
  - `usePickerAvailability(): boolean` (fetch di availability al mount; errore = `false`)
  - chiave i18n `t.settings.browseButton`

- [ ] **Step 1: Client API**

In `frontend/lib/api/settings.ts`, aggiorna la riga di import e aggiungi in coda:

```ts
import { apiGet, apiPatch, apiPost, apiPut } from "./client";
```

```ts
/** Il dialog nativo di scelta percorso è disponibile? (solo backend su macOS) */
export function pickerAvailability() {
  return apiGet<{ available: boolean }>("/api/files/pick/availability");
}

/** Apre il dialog nativo sulla macchina del backend; path null = annullato. */
export function pickPath(kind: "folder" | "file", start?: string, prompt?: string) {
  return apiPost<{ path: string | null }>("/api/files/pick", {
    kind, start: start || null, prompt: prompt || null,
  });
}
```

- [ ] **Step 2: i18n**

In `frontend/lib/i18n/en.ts`, blocco `settings` (vicino a `saveButton`, riga ~75):

```ts
    browseButton: "Browse…",
```

Nel blocco `errors` (riga ~1119):

```ts
    picker_unavailable: "Native picker unavailable: it requires the backend on macOS.",
    picker_busy: "A picker dialog is already open on the backend machine.",
```

In `frontend/lib/i18n/it.ts`, stesse posizioni (blocco `settings` vicino a `saveButton`, blocco `errors`):

```ts
    browseButton: "Sfoglia…",
```

```ts
    picker_unavailable: "Dialog nativo non disponibile: richiede il backend su macOS.",
    picker_busy: "Un dialog di scelta è già aperto sulla macchina del backend.",
```

(`Dictionary` è il tipo di `en.ts`: aggiungere prima lì, poi lo speculare in `it.ts`.)

- [ ] **Step 3: Scrivi i test del componente (falliranno)**

Crea `frontend/tests/path-picker-button.test.tsx`:

```tsx
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { PathPickerButton } from "@/components/path-picker-button";

const pickPath = vi.fn();
vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<object>()),
  pickPath: (...args: unknown[]) => pickPath(...args),
}));

afterEach(() => {
  cleanup();
  pickPath.mockReset();
});

describe("PathPickerButton", () => {
  it("il click apre il picker con kind e start e riporta il percorso", async () => {
    pickPath.mockResolvedValue({ path: "/Users/x/Music" });
    const onPick = vi.fn();
    render(<PathPickerButton kind="folder" start="/Users/x" onPick={onPick} onError={() => {}} />);
    await act(async () => {
      fireEvent.click(screen.getByRole("button"));
    });
    expect(pickPath).toHaveBeenCalledWith("folder", "/Users/x", undefined);
    expect(onPick).toHaveBeenCalledWith("/Users/x/Music");
  });

  it("annullo (path null) non chiama onPick", async () => {
    pickPath.mockResolvedValue({ path: null });
    const onPick = vi.fn();
    render(<PathPickerButton kind="file" onPick={onPick} onError={() => {}} />);
    await act(async () => {
      fireEvent.click(screen.getByRole("button"));
    });
    expect(onPick).not.toHaveBeenCalled();
  });

  it("errore API va a onError", async () => {
    pickPath.mockRejectedValue(new Error("picker occupato"));
    const onError = vi.fn();
    render(<PathPickerButton kind="folder" onPick={() => {}} onError={onError} />);
    await act(async () => {
      fireEvent.click(screen.getByRole("button"));
    });
    expect(onError).toHaveBeenCalledWith("picker occupato");
  });

  it("mentre il dialog è aperto il pulsante è disabilitato", async () => {
    // Niente jest-dom nel setup vitest del repo: si legge `disabled` dal nodo.
    let resolvePick!: (v: { path: string | null }) => void;
    pickPath.mockImplementation(() => new Promise((res) => { resolvePick = res; }));
    render(<PathPickerButton kind="folder" onPick={() => {}} onError={() => {}} />);
    await act(async () => {
      fireEvent.click(screen.getByRole("button"));
    });
    expect((screen.getByRole("button") as HTMLButtonElement).disabled).toBe(true);
    await act(async () => {
      resolvePick({ path: null });
    });
    expect((screen.getByRole("button") as HTMLButtonElement).disabled).toBe(false);
  });
});
```

- [ ] **Step 4: Verifica che falliscano**

```bash
cd frontend && npx vitest run tests/path-picker-button.test.tsx
```

Expected: FAIL (modulo `@/components/path-picker-button` inesistente).

- [ ] **Step 5: Implementa il componente**

Crea `frontend/components/path-picker-button.tsx`:

```tsx
"use client";

import { useEffect, useState } from "react";
import { errText, pickerAvailability, pickPath } from "@/lib/api";
import { Button, Spinner } from "@/components/ui";
import { useT } from "@/lib/i18n";

/** Disponibilità del dialog nativo: fetch una volta al mount, errore = false
 *  (i pulsanti Sfoglia semplicemente non compaiono). Condiviso da Settings e
 *  dalla modale "Collega file locale". */
export function usePickerAvailability(): boolean {
  const [ok, setOk] = useState(false);
  useEffect(() => {
    pickerAvailability().then((r) => setOk(r.available)).catch(() => setOk(false));
  }, []);
  return ok;
}

/* Apre il dialog nativo del backend (macOS) e riporta il percorso scelto.
   Il genitore decide se montarlo (usePickerAvailability) e cosa farne: qui
   niente salvataggio, solo la scelta. type="button": il pulsante vive anche
   dentro form (modale link file) e non deve scatenarne il submit. */
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
      onError(errText(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Button type="button" size="sm" onClick={open} disabled={busy}>
      {busy ? <Spinner /> : t.settings.browseButton}
    </Button>
  );
}
```

- [ ] **Step 6: Verifica che passino**

```bash
cd frontend && npx vitest run tests/path-picker-button.test.tsx
```

Expected: 4 PASS.

- [ ] **Step 7: Commit**

```bash
git add frontend/lib/api/settings.ts frontend/lib/i18n/en.ts frontend/lib/i18n/it.ts frontend/components/path-picker-button.tsx frontend/tests/path-picker-button.test.tsx
git commit -m "feat(settings): componente PathPickerButton col client API del picker"
```

---

### Task 4: Estrazione di `ConfigCard`, pulsanti Sfoglia e verifica finale

La card va testata in isolamento, ma `page.tsx` in Next non può avere export
extra (il type-check del build li rifiuta): `ConfigCard` viene quindi estratta
in un componente suo — spostamento 1:1 del codice esistente più le aggiunte
del picker.

**Files:**
- Create: `frontend/components/settings/config-card.tsx`
- Modify: `frontend/app/settings/page.tsx` (rimuove `CONFIG_FIELDS` + `ConfigCard`, righe ~279-383, e importa il nuovo componente)
- Test: `frontend/tests/settings-config-card.test.tsx`

**Interfaces:**
- Consumes (dal Task 3): `pickerAvailability`, `pickPath` (via `PathPickerButton`), `t.settings.browseButton`.
- Produces: `export function ConfigCard()` da `@/components/settings/config-card`, resa da `page.tsx` esattamente dov'era (`<ConfigCard />` invariato nel JSX della pagina).

- [ ] **Step 1: Leggi `frontend/CLAUDE.md`** (obbligatorio prima di toccare pagine: Next 16).

- [ ] **Step 2: Scrivi i test della card (falliranno)**

Crea `frontend/tests/settings-config-card.test.tsx`:

```tsx
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ConfigCard } from "@/components/settings/config-card";
import type { ConfigSettings, FieldState } from "@/lib/api";

const getConfigSettings = vi.fn();
const patchConfigSettings = vi.fn();
const pickerAvailability = vi.fn();
const pickPath = vi.fn();

vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<object>()),
  getConfigSettings: (...a: unknown[]) => getConfigSettings(...a),
  patchConfigSettings: (...a: unknown[]) => patchConfigSettings(...a),
  setLibraryShare: vi.fn(),
  pickerAvailability: (...a: unknown[]) => pickerAvailability(...a),
  pickPath: (...a: unknown[]) => pickPath(...a),
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

const field = (value: string): FieldState =>
  ({ value, source: "env", valid: true, detail: null });

const CONFIG: ConfigSettings = {
  library_root: field("/Users/x/Music"),
  archive_root: field(""),
  slskd_download_dir: field("/Users/x/Downloads"),
  slskd_url: field("http://localhost:5030"),
  slskd_config_path: field(""),
  share_library: false,
  warning: null,
};

async function mount(available: boolean) {
  getConfigSettings.mockResolvedValue(CONFIG);
  pickerAvailability.mockResolvedValue({ available });
  await act(async () => {
    render(<ConfigCard />);
  });
}

describe("ConfigCard + picker", () => {
  it("con picker disponibile mostra Sfoglia sui 4 campi percorso", async () => {
    await mount(true);
    expect(screen.getAllByRole("button", { name: "Sfoglia…" })).toHaveLength(4);
  });

  it("senza picker nessun pulsante Sfoglia (resta l'input testuale)", async () => {
    await mount(false);
    expect(screen.queryByRole("button", { name: "Sfoglia…" })).toBeNull();
    expect(screen.getByDisplayValue("/Users/x/Music")).toBeTruthy();
  });

  it("il percorso scelto riempie la bozza senza salvare", async () => {
    await mount(true);
    pickPath.mockResolvedValue({ path: "/Volumes/Dischi/Musica" });
    await act(async () => {
      fireEvent.click(screen.getAllByRole("button", { name: "Sfoglia…" })[0]);
    });
    expect(screen.getByDisplayValue("/Volumes/Dischi/Musica")).toBeTruthy();
    expect(patchConfigSettings).not.toHaveBeenCalled();
  });

  it("annullo del dialog: la bozza non cambia", async () => {
    await mount(true);
    pickPath.mockResolvedValue({ path: null });
    await act(async () => {
      fireEvent.click(screen.getAllByRole("button", { name: "Sfoglia…" })[0]);
    });
    expect(screen.getByDisplayValue("/Users/x/Music")).toBeTruthy();
  });

  it("errore del picker mostrato nel banner della card", async () => {
    await mount(true);
    pickPath.mockRejectedValue(new Error("Un dialog di scelta è già aperto sulla macchina del backend."));
    await act(async () => {
      fireEvent.click(screen.getAllByRole("button", { name: "Sfoglia…" })[0]);
    });
    expect(screen.getByText(/già aperto/)).toBeTruthy();
  });
});
```

- [ ] **Step 3: Verifica che falliscano**

```bash
cd frontend && npx vitest run tests/settings-config-card.test.tsx
```

Expected: FAIL (modulo `@/components/settings/config-card` inesistente).

- [ ] **Step 4: Crea il componente estratto**

Crea `frontend/components/settings/config-card.tsx`. Il corpo di `ConfigCard` è
lo spostamento 1:1 delle righe ~284-383 di `page.tsx`; le parti nuove sono
marcate con `// NEW` (marcatori da NON copiare nel file finale):

```tsx
"use client";

import { useCallback, useEffect, useState } from "react";
import {
  errText, getConfigSettings, patchConfigSettings, setLibraryShare,
  type ConfigPatch, type ConfigSettings,
} from "@/lib/api";
import { Alert, Badge, Button, CardHeader, Checkbox, Field, Input, Loading, Spinner } from "@/components/ui";
import { PathPickerButton, usePickerAvailability } from "@/components/path-picker-button";
import { useT } from "@/lib/i18n";

const CONFIG_FIELDS = [
  "library_root", "archive_root", "slskd_download_dir", "slskd_url", "slskd_config_path",
] as const;
type ConfigFieldKey = (typeof CONFIG_FIELDS)[number];

// NEW: quali campi hanno "Sfoglia…" e con che dialog; slskd_url è un URL di
// rete, niente pulsante.
const PICK_KIND: Partial<Record<ConfigFieldKey, "folder" | "file">> = {
  library_root: "folder",
  archive_root: "folder",
  slskd_download_dir: "folder",
  slskd_config_path: "file",
};

export function ConfigCard() {
  const t = useT();
  const [config, setConfig] = useState<ConfigSettings | null>(null);
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [warning, setWarning] = useState<string | null>(null);
  const [shareBusy, setShareBusy] = useState(false);
  const [shareMsg, setShareMsg] = useState<string | null>(null);
  const pickerOk = usePickerAvailability(); // NEW

  const hydrate = useCallback((c: ConfigSettings) => {
    setConfig(c);
    setDraft(Object.fromEntries(CONFIG_FIELDS.map((k) => [k, c[k].value])));
    setWarning(c.warning);
  }, []);

  useEffect(() => {
    getConfigSettings().then(hydrate).catch((e) => setError(errText(e)));
  }, [hydrate]);

  const FIELD_LABEL: Record<ConfigFieldKey, string> = {
    library_root: t.settings.fieldLibraryRoot,
    archive_root: t.settings.fieldArchiveRoot,
    slskd_download_dir: t.settings.fieldDownloadsDir,
    slskd_url: t.settings.fieldSlskdUrl,
    slskd_config_path: t.settings.fieldSlskdConfig,
  };

  const dirty = config ? CONFIG_FIELDS.some((k) => draft[k] !== config[k].value) : false;

  const save = async () => {
    if (!config) return;
    const patch: ConfigPatch = {};
    for (const k of CONFIG_FIELDS) if (draft[k] !== config[k].value) patch[k] = draft[k];
    setSaving(true); setError(null); setSaved(false);
    try {
      hydrate(await patchConfigSettings(patch));
      setSaved(true); setTimeout(() => setSaved(false), 1500);
    } catch (e) { setError(errText(e)); }
    finally { setSaving(false); }
  };

  const toggleShare = async (enabled: boolean) => {
    setShareBusy(true); setError(null); setShareMsg(null);
    try {
      const r = await setLibraryShare(enabled);
      setConfig((c) => (c ? { ...c, share_library: r.share_library } : c));
      setShareMsg(!enabled ? t.settings.shareOff
        : r.rescan ? t.settings.shareOnRescan : t.settings.shareOnPending);
    } catch (e) { setError(errText(e)); }
    finally { setShareBusy(false); }
  };

  if (!config) {
    return (
      <div className="border border-border p-5">
        {error ? <Alert tone="danger">⚠ {error}</Alert> : <Loading />}
      </div>
    );
  }

  return (
    <div className="border border-border">
      <CardHeader title={t.settings.configHeading} subtitle={t.settings.configSubtitle} />
      <div className="space-y-4 p-5">
        {error && <Alert tone="danger">⚠ {error}</Alert>}
        {warning && <Alert tone="warning">{warning}</Alert>}
        {CONFIG_FIELDS.map((k) => {
          const f = config[k];
          const unchanged = draft[k] === f.value;
          const pickKind = PICK_KIND[k]; // NEW (variabile locale: TS non restringe PICK_KIND[k] tra due accessi)
          return (
            <Field key={k}
              label={
                <span className="flex flex-wrap items-center gap-2">
                  {FIELD_LABEL[k]}
                  {f.source === "db" && <Badge tone="info">{t.settings.overrideBadge}</Badge>}
                  {unchanged && !f.valid && <Badge tone="danger">{f.detail}</Badge>}
                </span>
              }
              hint={!unchanged ? t.settings.unsavedHint : f.valid ? (f.detail ?? undefined) : undefined}>
              <div className="flex items-center gap-2">{/* NEW: riga input+pulsante */}
                <Input className="flex-1" value={draft[k] ?? ""}
                  onChange={(e) => setDraft((d) => ({ ...d, [k]: e.target.value }))} />
                {pickerOk && pickKind && (
                  <PathPickerButton kind={pickKind} start={draft[k]} prompt={FIELD_LABEL[k]}
                    onPick={(p) => setDraft((d) => ({ ...d, [k]: p }))}
                    onError={setError} />
                )}
              </div>
            </Field>
          );
        })}
        <Button size="sm" onClick={save} disabled={saving || !dirty}>
          {saving ? <Spinner /> : null} {saved ? t.settings.savedLabel : t.settings.saveButton}
        </Button>

        <div className="border-t border-border pt-4">
          <Checkbox label={t.settings.shareLibraryLabel} checked={config.share_library}
            disabled={shareBusy} onChange={toggleShare} />
          <p className="mt-1.5 text-xs text-muted">{t.settings.shareLibraryHint}</p>
          {shareMsg && <p className="mt-1.5 text-xs text-fg">{shareMsg}</p>}
        </div>
      </div>
    </div>
  );
}
```

Nota: prima di scrivere il file confronta col sorgente reale di `page.tsx` —
se `ConfigCard` è cambiata rispetto a questo piano, vince il sorgente (lo
spostamento resta 1:1, le sole aggiunte sono le righe `// NEW`).

- [ ] **Step 5: Aggiorna `page.tsx`**

In `frontend/app/settings/page.tsx`:

1. Elimina il blocco da `const CONFIG_FIELDS = [` fino alla chiusura di `function ConfigCard()` (righe ~279-383).
2. Aggiungi l'import del componente estratto:

```tsx
import { ConfigCard } from "@/components/settings/config-card";
```

3. Ripulisci l'import da `@/lib/api` e da `@/components/ui` dai simboli rimasti
   inutilizzati nella pagina (candidati: `getConfigSettings`, `patchConfigSettings`,
   `setLibraryShare`, `ConfigPatch`, `ConfigSettings`, `Badge`, `Checkbox`,
   `Loading` — ma alcuni servono ad altre card della pagina: fai fede a
   `npm run lint`, che segnala ogni unused import).

Il JSX della pagina non cambia: `<ConfigCard />` era e resta il punto d'uso.

- [ ] **Step 6: Verifica che i test della card passino**

```bash
cd frontend && npx vitest run tests/settings-config-card.test.tsx
```

Expected: 5 PASS.

- [ ] **Step 7: Verifica frontend completa**

```bash
cd frontend && npm run lint && npm run test:unit && npm run build
```

Expected: lint pulito, tutti i test unit PASS, build ok.

- [ ] **Step 8: Verifica manuale nel browser (facoltativa ma raccomandata in locale)**

Avvia backend e frontend, apri Settings: accanto ai 4 campi percorso compare "Sfoglia…"; il click apre il Finder in primo piano; scegliere una cartella riempie il campo con hint "Modifica non salvata"; annullare non cambia nulla; Salva persiste come prima.

- [ ] **Step 9: Commit**

```bash
git add frontend/app/settings/page.tsx frontend/components/settings/config-card.tsx frontend/tests/settings-config-card.test.tsx
git commit -m "feat(settings): pulsante Sfoglia coi percorsi scelti dal dialog nativo"
```

---

### Task 5: Pulsante Sfoglia nella modale "Collega file locale"

**Files:**
- Modify: `frontend/components/link-local-file-modal.tsx` (funzione `LinkDialog`; l'input "percorso esatto" è nel secondo `<form>`, righe ~126-144)
- Test: `frontend/tests/link-local-file-modal.test.tsx`

**Interfaces:**
- Consumes (dal Task 3): `PathPickerButton` (già `type="button"`: dentro il form non scatena il submit), `usePickerAvailability`.
- Produces: UI finale; nessun consumer successivo.

- [ ] **Step 1: Scrivi i test (falliranno)**

Crea `frontend/tests/link-local-file-modal.test.tsx`:

```tsx
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { LinkLocalFileModal } from "@/components/link-local-file-modal";

const searchLocalFiles = vi.fn();
const linkLocalFile = vi.fn();
const pickerAvailability = vi.fn();
const pickPath = vi.fn();

vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<object>()),
  searchLocalFiles: (...a: unknown[]) => searchLocalFiles(...a),
  linkLocalFile: (...a: unknown[]) => linkLocalFile(...a),
  pickerAvailability: (...a: unknown[]) => pickerAvailability(...a),
  pickPath: (...a: unknown[]) => pickPath(...a),
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

const TARGET = { id: 5, artist: "Objekt", title: "Ganzfeld" };

async function mount(available: boolean) {
  pickerAvailability.mockResolvedValue({ available });
  await act(async () => {
    render(<LinkLocalFileModal target={TARGET} onClose={() => {}} onLinked={() => {}} />);
  });
}

describe("LinkLocalFileModal + picker", () => {
  it("con picker disponibile il percorso esatto ha Sfoglia", async () => {
    await mount(true);
    expect(screen.getByRole("button", { name: "Sfoglia…" })).toBeTruthy();
  });

  it("senza picker niente Sfoglia (resta l'input testuale)", async () => {
    await mount(false);
    expect(screen.queryByRole("button", { name: "Sfoglia…" })).toBeNull();
  });

  it("il file scelto riempie il percorso esatto senza collegare subito", async () => {
    // linkLocalFile mai chiamata = pinna anche il type=\"button\" del pulsante
    // (un submit del form partirebbe col percorso vuoto).
    await mount(true);
    pickPath.mockResolvedValue({ path: "/Users/x/Downloads/track.mp3" });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Sfoglia…" }));
    });
    expect(screen.getByDisplayValue("/Users/x/Downloads/track.mp3")).toBeTruthy();
    expect(linkLocalFile).not.toHaveBeenCalled();
  });

  it("annullo del dialog: il percorso esatto resta vuoto", async () => {
    await mount(true);
    pickPath.mockResolvedValue({ path: null });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Sfoglia…" }));
    });
    expect(screen.queryByDisplayValue("/Users/x/Downloads/track.mp3")).toBeNull();
    expect(linkLocalFile).not.toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Verifica che falliscano**

```bash
cd frontend && npx vitest run tests/link-local-file-modal.test.tsx
```

Expected: FAIL — il pulsante "Sfoglia…" non esiste ancora nella modale (i primi due test falliscono; il mock di `pickerAvailability` resta inerte finché la modale non lo usa).

- [ ] **Step 3: Monta il pulsante nella modale**

In `frontend/components/link-local-file-modal.tsx`:

1. Import (dopo gli import esistenti):

```tsx
import { PathPickerButton, usePickerAvailability } from "@/components/path-picker-button";
```

2. In `LinkDialog`, accanto agli altri hook (dopo `const [error, setError] = useState<string | null>(null);`):

```tsx
const pickerOk = usePickerAvailability();
```

3. Nel form del percorso esatto, dopo l'`<Input>` di `manualPath` e prima del `<Button type="submit">`:

```tsx
{pickerOk && (
  <PathPickerButton kind="file" prompt={t.tracks.exactPathLabel}
    onPick={setManualPath} onError={setError} />
)}
```

(Niente `start`: `manualPath` di solito è vuoto o è un file, e il backend usa
`start` solo se è una directory esistente.)

- [ ] **Step 4: Verifica che passino**

```bash
cd frontend && npx vitest run tests/link-local-file-modal.test.tsx
```

Expected: 4 PASS.

- [ ] **Step 5: Verifica frontend completa**

```bash
cd frontend && npm run lint && npm run test:unit && npm run build
```

Expected: lint pulito, tutti i test unit PASS, build ok.

- [ ] **Step 6: Aggiorna ROADMAP/PROGRESS**

- `docs/ROADMAP.md`: registra la feature (Settings + modale link file) come fatta secondo lo stile della sezione stato corrente.
- `PROGRESS.md`: voce diario in coda, stile delle voci esistenti, con data 2026-08-07 e rimando alla spec.

- [ ] **Step 7: Commit**

```bash
git add frontend/components/link-local-file-modal.tsx frontend/tests/link-local-file-modal.test.tsx docs/ROADMAP.md PROGRESS.md
git commit -m "feat(tracks): pulsante Sfoglia nella modale Collega file locale"
```
