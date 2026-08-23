# slskd come servizio — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Una sola riga in tutta l'app sa configurare slskd dall'inizio alla fine, e il wizard smette di chiedere ciò che nel bundle è già risolto.

**Architecture:** slskd esce da `system_probe.REGISTRY` e resta soltanto un servizio esterno. Le due metà che oggi si dividono il lavoro — il wizard sa scaricare e configurare, Impostazioni sa collegare e avviare — si uniscono in un componente condiviso, montato da entrambi. Il passo *Prerequisiti* del wizard resta per ffmpeg e fpcalc e non si monta quando entrambi vengono dal bundle.

**Tech Stack:** Python + FastAPI + Pydantic (backend), React + TypeScript (frontend), pytest, vitest.

Spec: `docs/superpowers/specs/2026-08-24-slskd-servizio-design.md`.

## Global Constraints

- **Inglese** in `README.md`, `docs/*.md` e `PROGRESS.md`; **italiano** in codice, commenti, nomi di funzione e messaggi di commit.
- **I testi user-facing vivono nei dizionari**, in **entrambe** le lingue (`frontend/lib/i18n/en.ts` è la fonte del tipo, `it.ts` deve soddisfarlo).
- **La password Soulseek non torna mai indietro dal backend.** `read_username` restituisce l'utente, non la password; il campo si comporta come gli altri campi segreti.
- **Nessuna modifica** a `binary_manifest`, all'avvio/arresto del demone, alla scrittura dello YAML: cambia chi li chiama, non cosa fanno.
- **Ogni asserzione va provata rompendo il codice che sorveglia.** In particolare i test che oggi citano `slskd` nel probe **devono** diventare rossi: se restano verdi non stavano provando quello che dichiarano.
- Comandi: backend `cd backend && ./.venv/bin/python -m pytest tests`; frontend `cd frontend && npm run lint && npm run test:unit && npm run build`.

---

### Task 1: I tre campi che dicono a che punto siamo

**Files:**
- Modify: `backend/app/routers/slskd.py:125-129` (modello `DaemonStatus`) e `daemon_status()` a riga 148
- Test: `backend/tests/test_slskd_daemon_status.py` (create)

**Interfaces:**
- Consumes: `binary_installer.installed_path("slskd") -> Path | None`, `slskd_daemon.default_config_path() -> Path`, `slskd_daemon.read_username(path) -> str | None` (tutte già esistenti).
- Produces, per i Task 3 e 5: `GET /api/slskd/daemon/status` risponde `{reachable, owned, pid, installed, configured, username}`.

- [ ] **Step 1: Scrivere i test**

Creare `backend/tests/test_slskd_daemon_status.py`:

```python
"""Lo stato del demone deve dire a che punto è il percorso, non solo se
risponde: la riga che lo mostra sceglie l'unica azione sensata a partire da
questi campi, e senza `installed`/`configured` non può distinguere "da
scaricare" da "da configurare"."""
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.services import slskd_daemon

client = TestClient(app)


def _stato() -> dict:
    risposta = client.get("/api/slskd/daemon/status")
    assert risposta.status_code == 200
    return risposta.json()


def test_binario_assente_lo_dice(monkeypatch):
    monkeypatch.setattr("app.services.binary_installer.installed_path", lambda k: None)
    assert _stato()["installed"] is False


def test_binario_presente_lo_dice(monkeypatch):
    monkeypatch.setattr(
        "app.services.binary_installer.installed_path", lambda k: Path("/finto/slskd")
    )
    assert _stato()["installed"] is True


def test_configurazione_assente_lo_dice(monkeypatch, tmp_path):
    monkeypatch.setattr(slskd_daemon, "default_config_path", lambda: tmp_path / "manca.yml")
    stato = _stato()
    assert stato["configured"] is False
    assert stato["username"] is None


def test_configurazione_presente_porta_lo_username(monkeypatch, tmp_path):
    config = tmp_path / "slskd.yml"
    config.write_text("soulseek:\n  username: dj_test\n  password: segreta\n")
    monkeypatch.setattr(slskd_daemon, "default_config_path", lambda: config)
    stato = _stato()
    assert stato["configured"] is True
    assert stato["username"] == "dj_test"


def test_la_password_non_esce_mai(monkeypatch, tmp_path):
    """Il file la contiene, la risposta no: nessun campo la trasporta, e
    nemmeno per sbaglio dentro un altro."""
    config = tmp_path / "slskd.yml"
    config.write_text("soulseek:\n  username: dj_test\n  password: segretissima\n")
    monkeypatch.setattr(slskd_daemon, "default_config_path", lambda: config)
    assert "segretissima" not in client.get("/api/slskd/daemon/status").text
```

- [ ] **Step 2: Eseguirli e vederli fallire**

```bash
cd backend && ./.venv/bin/python -m pytest tests/test_slskd_daemon_status.py -v
```

Atteso: FAIL — `KeyError: 'installed'` sui primi quattro. L'ultimo passa già (nessun campo trasporta la password): è un guardiano, non una funzionalità da scrivere.

- [ ] **Step 3: Estendere il modello e la risposta**

In `backend/app/routers/slskd.py`, il modello diventa:

```python
class DaemonStatus(BaseModel):
    reachable: bool
    owned: bool | None
    pid: int | None = None
    # A che punto è il percorso, non solo se il demone risponde: la riga nella
    # UI sceglie da qui l'unica azione sensata (scaricare, configurare,
    # avviare, collegare). Additivi: nessun campo esistente cambia significato.
    installed: bool = False
    configured: bool = False
    username: str | None = None
```

E in `daemon_status()`, prima di costruire la risposta:

```python
    from app.services import binary_installer

    percorso_config = slskd_daemon.default_config_path()
    configurato = percorso_config.is_file()
    return DaemonStatus(
        reachable=...,   # invariato, come già calcolato
        owned=...,       # invariato
        pid=...,         # invariato
        installed=binary_installer.installed_path("slskd") is not None,
        configured=configurato,
        # Lo username sta nel file e serve a mostrarlo senza richiederlo; la
        # password resta dov'è.
        username=slskd_daemon.read_username(percorso_config) if configurato else None,
    )
```

- [ ] **Step 4: Rieseguire i test**

```bash
cd backend && ./.venv/bin/python -m pytest tests/test_slskd_daemon_status.py -v
```

Atteso: 5 passed.

- [ ] **Step 5: Provarli rompendo il codice**

Sostituire `installed=binary_installer.installed_path("slskd") is not None` con `installed=True`: *test_binario_assente_lo_dice* deve fallire. Rimettere.

- [ ] **Step 6: Aggiornare `docs/API.md`**

Nella sezione degli endpoint slskd, aggiungere i tre campi alla risposta di `GET /api/slskd/daemon/status`, dicendo a cosa servono: `installed` (il binario è nella cartella gestita dall'app), `configured` (il file YAML esiste), `username` (letto dal file, la password non esce mai).

- [ ] **Step 7: Commit**

```bash
git add backend/app/routers/slskd.py backend/tests/test_slskd_daemon_status.py docs/API.md
git commit -m "feat(slskd): lo stato del demone dice a che punto e' il percorso"
```

---

### Task 2: slskd esce dai componenti di sistema

**Files:**
- Modify: `backend/app/services/system_probe.py` (voce `slskd` in `REGISTRY` riga 79, `_probe_slskd` riga 244, ramo `kind == "daemon"` riga 271, tipo `kind` riga 42)
- Modify: `backend/tests/test_system_probe.py:233`
- Test: `backend/tests/test_system_probe.py` (modifiche) e `backend/tests/test_setup_install_router.py` (verifica)

**Interfaces:**
- Consumes: niente dal Task 1.
- Produces, per i Task 3-5: `probe_all()` restituisce **due** componenti (`ffmpeg`, `fpcalc`), entrambi `kind == "system"`. `POST /api/setup/install/slskd` resta valido perché `binary_installer` valida contro `binary_manifest.MANIFEST`, non contro `REGISTRY`.

- [ ] **Step 1: Aggiornare il test che fissa l'elenco**

In `backend/tests/test_system_probe.py`, riga 233, l'asserzione diventa:

```python
def test_il_registry_contiene_solo_binari_di_sistema():
    """slskd non è qui: la sua presenza non è un file su PATH ma una risposta
    HTTP, e configurarlo vuol dire credenziali, YAML e un demone — cose da
    servizio, non da componente. Vive in `routers/services.py`."""
    assert [c.key for c in sp.REGISTRY] == ["ffmpeg", "fpcalc"]
    assert {c.kind for c in sp.REGISTRY} == {"system"}
```

- [ ] **Step 2: Aggiungere il test che protegge l'installazione**

In `backend/tests/test_setup_install_router.py`, in fondo:

```python
def test_slskd_resta_installabile_anche_se_non_e_piu_un_componente(client):
    """L'installer valida le chiavi contro il manifest dei binari, non contro
    il registry del probe. È ciò che regge la riga del servizio: senza, uscire
    dal registry vorrebbe dire perdere il download."""
    from app.services import binary_manifest

    assert binary_manifest.entry_for("slskd") is not None
    risposta = client.post("/api/setup/install/slskd")
    # 202 se parte, 409 se un'installazione è già in corso o il demone gira:
    # mai 400 `unknown_component`, che è il fallimento che questo test cerca.
    assert risposta.status_code in (202, 409)
```

- [ ] **Step 3: Eseguirli e vedere il primo fallire**

```bash
cd backend && ./.venv/bin/python -m pytest tests/test_system_probe.py tests/test_setup_install_router.py -v
```

Atteso: *test_il_registry_contiene_solo_binari_di_sistema* FAIL (il registry contiene ancora tre voci); il test dell'installazione passa già, ed è giusto così — descrive un invariante che non deve rompersi.

- [ ] **Step 4: Togliere slskd dal probe**

In `backend/app/services/system_probe.py`:

1. Eliminare l'intera voce `Component(key="slskd", ...)` da `REGISTRY`.
2. Eliminare la funzione `_probe_slskd` per intero.
3. In `_probe_one`, il ramo diventa una riga sola:

```python
def _probe_one(c: Component) -> dict:
    detected = _probe_binary(c)
```

4. Il tipo del campo diventa `kind: Literal["system"]`, e sopra la dichiarazione va detto perché resta un campo con un valore solo:

```python
    # Un valore solo, per ora: il campo resta perche' la UI lo legge e perche'
    # un secondo tipo di componente e' plausibile. slskd non lo era: la sua
    # presenza non e' un file ma una risposta HTTP.
    kind: Literal["system"]
```

- [ ] **Step 5: Rieseguire i test del probe**

```bash
cd backend && ./.venv/bin/python -m pytest tests/test_system_probe.py tests/test_setup_install_router.py -v
```

Atteso: tutti verdi. Se un altro test di questo file fallisce citando slskd, **leggerlo prima di aggiustarlo**: se asseriva qualcosa su slskd-come-componente va rimosso, se asseriva qualcosa sull'installazione va tenuto.

- [ ] **Step 6: Suite backend intera**

```bash
cd backend && ./.venv/bin/python -m pytest tests -q
```

Atteso: tutti verdi. `conftest.py:163` itera su `system_probe.REGISTRY`: continua a funzionare con due voci. Se qualche test fallisce, è nell'elenco che la spec prevedeva (§6, terzo rischio).

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/system_probe.py backend/tests/
git commit -m "refactor(slskd): non e' un componente di sistema, e' un servizio"
```

---

### Task 3: La riga che sa tutto il percorso

**Files:**
- Create: `frontend/components/slskd-row.tsx`
- Modify: `frontend/lib/i18n/en.ts`, `frontend/lib/i18n/it.ts`
- Test: `frontend/tests/slskd-row.test.tsx` (create)

**Interfaces:**
- Consumes: dal Task 1 `daemonStatus() -> {reachable, owned, pid, installed, configured, username}`; API già esistenti `daemonConfig({username, password})`, `daemonStart()`, `daemonStop()`, `slskdStatus()`, `slskdConnect()`, `slskdDisconnect()`, `startInstall(key)`, `getInstallStatus()`.
- Produces, per il Task 4: `<SlskdRow />`, senza props, che si carica lo stato da sé.

- [ ] **Step 1: Le chiavi i18n**

In `frontend/lib/i18n/en.ts`, dentro `settings`, dopo le chiavi `soulseek*` esistenti:

```ts
    slskdDownload: "Download slskd",
    slskdDownloading: "Downloading…",
    slskdSaveConfig: "Save configuration",
    slskdSaving: "Saving…",
    slskdStepDownload: "slskd is not installed yet. Cratory can fetch it.",
    slskdStepConfigure: "Enter your Soulseek account: Cratory writes slskd's configuration file, keeping a backup of the existing one.",
    slskdStepStart: "Configured. The daemon is not running.",
    slskdStepConnect: "The daemon is running but Cratory is not connected to it.",
```

In `frontend/lib/i18n/it.ts`, nello stesso punto:

```ts
    slskdDownload: "Scarica slskd",
    slskdDownloading: "Scaricamento…",
    slskdSaveConfig: "Salva configurazione",
    slskdSaving: "Salvataggio…",
    slskdStepDownload: "slskd non è ancora installato. Cratory può scaricarlo.",
    slskdStepConfigure: "Inserisci il tuo account Soulseek: Cratory scrive il file di configurazione di slskd, tenendo una copia di quello esistente.",
    slskdStepStart: "Configurato. Il demone non è in esecuzione.",
    slskdStepConnect: "Il demone è in esecuzione ma Cratory non è collegata.",
```

- [ ] **Step 2: Scrivere i test**

Creare `frontend/tests/slskd-row.test.tsx`:

```tsx
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";

const finto = vi.hoisted(() => ({
  daemon: { reachable: false, owned: null, pid: null, installed: false, configured: false, username: null },
  slskd: { configured: false, reachable: false, is_connected: false, is_logged_in: false, is_connecting: false, is_transitioning: false, username: null },
  startInstall: vi.fn(),
  daemonConfig: vi.fn(),
  daemonStart: vi.fn(),
  daemonStop: vi.fn(),
  slskdConnect: vi.fn(),
  slskdDisconnect: vi.fn(),
}));

vi.mock("@/lib/api", () => ({
  errText: (e: unknown) => String(e),
  daemonStatus: () => Promise.resolve(finto.daemon),
  slskdStatus: () => Promise.resolve(finto.slskd),
  startInstall: (k: string) => finto.startInstall(k),
  getInstallStatus: () => Promise.resolve({ status: "done", detail: null, error_code: null }),
  daemonConfig: (b: unknown) => finto.daemonConfig(b),
  daemonStart: () => finto.daemonStart(),
  daemonStop: () => finto.daemonStop(),
  slskdConnect: () => finto.slskdConnect(),
  slskdDisconnect: () => finto.slskdDisconnect(),
}));

import { SlskdRow } from "@/components/slskd-row";

beforeEach(() => {
  finto.daemon = { reachable: false, owned: null, pid: null, installed: false, configured: false, username: null };
  finto.slskd = { configured: false, reachable: false, is_connected: false, is_logged_in: false, is_connecting: false, is_transitioning: false, username: null };
});
afterEach(cleanup);

/* Il valore della riga è che mostri UNA azione: quella giusta per il punto in
   cui si è. Ogni test verifica anche che le altre non ci siano — senza, la
   riga potrebbe mostrarle tutte e passare lo stesso. */

describe("riga slskd", () => {
  it("binario assente: offre il download e nient'altro", async () => {
    render(<SlskdRow />);
    await waitFor(() => expect(screen.getByText("Scarica slskd")).toBeTruthy());
    expect(screen.queryByText("Salva configurazione")).toBeNull();
    expect(screen.queryByText("Avvia")).toBeNull();
  });

  it("installato ma non configurato: chiede le credenziali", async () => {
    finto.daemon = { ...finto.daemon, installed: true };
    render(<SlskdRow />);
    await waitFor(() => expect(screen.getByText("Salva configurazione")).toBeTruthy());
    expect(screen.queryByText("Scarica slskd")).toBeNull();
  });

  it("configurato ma fermo: offre l'avvio, e mostra chi sei senza richiederlo", async () => {
    finto.daemon = { ...finto.daemon, installed: true, configured: true, username: "dj_test" };
    render(<SlskdRow />);
    await waitFor(() => expect(screen.getByText("Avvia")).toBeTruthy());
    expect(screen.getByText(/dj_test/)).toBeTruthy();
    expect(screen.queryByText("Salva configurazione")).toBeNull();
  });

  it("demone attivo ma non collegato: offre il collegamento", async () => {
    finto.daemon = { ...finto.daemon, installed: true, configured: true, reachable: true, owned: true };
    finto.slskd = { ...finto.slskd, configured: true, reachable: true };
    render(<SlskdRow />);
    await waitFor(() => expect(screen.getByText(/Collega/)).toBeTruthy());
    expect(screen.queryByText("Avvia")).toBeNull();
  });

  it("collegato: offre scollega e ferma", async () => {
    finto.daemon = { ...finto.daemon, installed: true, configured: true, reachable: true, owned: true };
    finto.slskd = { ...finto.slskd, configured: true, reachable: true, is_connected: true, is_logged_in: true, username: "dj_test" };
    render(<SlskdRow />);
    await waitFor(() => expect(screen.getByText(/Scollega/)).toBeTruthy());
    expect(screen.getByText("Ferma")).toBeTruthy();
    expect(screen.queryByText(/^Collega/)).toBeNull();
  });

  it("non manda mai la password a chi non l'ha chiesta", async () => {
    finto.daemon = { ...finto.daemon, installed: true };
    render(<SlskdRow />);
    await waitFor(() => expect(screen.getByText("Salva configurazione")).toBeTruthy());
    // Il campo password è di tipo password e parte vuoto: nessun valore
    // precompilato può arrivare dal backend, che non lo restituisce.
    const campo = document.querySelector('input[type="password"]') as HTMLInputElement;
    expect(campo.value).toBe("");
  });
});
```

- [ ] **Step 3: Eseguirli e vederli fallire**

```bash
cd frontend && npx vitest run tests/slskd-row.test.tsx
```

Atteso: FAIL — `Failed to resolve import "@/components/slskd-row"`.

- [ ] **Step 4: Scrivere la riga**

Creare `frontend/components/slskd-row.tsx`:

```tsx
"use client";

/* slskd, dall'inizio alla fine, in un posto solo.
 *
 * Prima questo percorso era diviso in due: il wizard sapeva scaricare il
 * binario e scrivere la configurazione, Impostazioni sapeva collegare e
 * avviare — e la riga di Impostazioni, quando il binario mancava, rimandava
 * al wizard perche' davvero non sapeva installarlo. Non erano due copie della
 * stessa cosa: erano due meta'. Qui stanno insieme, e mostrano UNA azione:
 * quella che ha senso adesso. */

import { useCallback, useEffect, useState } from "react";
import { Plug, Unplug } from "lucide-react";
import {
  daemonConfig, daemonStart, daemonStatus, daemonStop, errText, getInstallStatus,
  slskdConnect, slskdDisconnect, slskdStatus, startInstall,
  type SlskdDaemonStatus, type SlskdStatus,
} from "@/lib/api";
import { Alert, Button, Input, Spinner } from "@/components/ui";
import { useT } from "@/lib/i18n";

type Fase = "caricamento" | "scarica" | "configura" | "avvia" | "collega" | "collegato";

function fase(d: SlskdDaemonStatus | null, s: SlskdStatus | null): Fase {
  if (!d) return "caricamento";
  if (!d.installed) return "scarica";
  if (!d.configured) return "configura";
  if (!d.reachable) return "avvia";
  return s?.is_connected && s?.is_logged_in ? "collegato" : "collega";
}

export function SlskdRow() {
  const t = useT();
  const [daemon, setDaemon] = useState<SlskdDaemonStatus | null>(null);
  const [slskd, setSlskd] = useState<SlskdStatus | null>(null);
  const [utente, setUtente] = useState("");
  const [password, setPassword] = useState("");
  const [inCorso, setInCorso] = useState(false);
  const [errore, setErrore] = useState<string | null>(null);

  const ricarica = useCallback(async () => {
    try {
      setDaemon(await daemonStatus());
    } catch (e) {
      setErrore(errText(e));
    }
    // Lo stato del login non è raggiungibile finché il demone non risponde:
    // il suo fallimento qui non è una notizia, è la normalità delle prime fasi.
    slskdStatus().then(setSlskd).catch(() => setSlskd(null));
  }, []);

  useEffect(() => { void ricarica(); }, [ricarica]);

  const azione = async (fn: () => Promise<unknown>) => {
    setInCorso(true);
    setErrore(null);
    try {
      await fn();
    } catch (e) {
      setErrore(errText(e));
    } finally {
      setInCorso(false);
      await ricarica();
    }
  };

  const scarica = () =>
    azione(async () => {
      await startInstall("slskd");
      let stato = await getInstallStatus();
      while (stato.status === "running") {
        await new Promise((r) => setTimeout(r, 1000));
        stato = await getInstallStatus();
      }
      if (stato.status === "error") throw new Error(stato.detail ?? "");
    });

  const salva = () =>
    azione(async () => {
      await daemonConfig({ username: utente, password });
      setPassword(""); // non resta in memoria oltre l'invio
    });

  const f = fase(daemon, slskd);

  return (
    <div className="mt-3 border border-border bg-bg p-3">
      {f === "caricamento" && <Spinner />}

      {f === "scarica" && (
        <div className="space-y-2">
          <p className="text-xs text-muted">{t.settings.slskdStepDownload}</p>
          <Button size="sm" disabled={inCorso} onClick={scarica}>
            {inCorso ? t.settings.slskdDownloading : t.settings.slskdDownload}
          </Button>
        </div>
      )}

      {f === "configura" && (
        <div className="space-y-2">
          <p className="text-xs text-muted">{t.settings.slskdStepConfigure}</p>
          <Input value={utente} onChange={(e) => setUtente(e.target.value)}
                 placeholder={t.setup.daemonUsername} disabled={inCorso} />
          <Input type="password" value={password} onChange={(e) => setPassword(e.target.value)}
                 placeholder={t.setup.daemonPassword} disabled={inCorso} />
          <Button size="sm" disabled={inCorso || !utente || !password} onClick={salva}>
            {inCorso ? t.settings.slskdSaving : t.settings.slskdSaveConfig}
          </Button>
        </div>
      )}

      {f === "avvia" && (
        <div className="space-y-2">
          <p className="text-xs text-muted">{t.settings.slskdStepStart}</p>
          {daemon?.username && (
            <p className="text-xs text-faint">{t.settings.soulseekConnectedAs(daemon.username)}</p>
          )}
          <Button size="sm" disabled={inCorso} onClick={() => azione(daemonStart)}>
            {t.setup.daemonStart}
          </Button>
        </div>
      )}

      {f === "collega" && (
        <div className="space-y-2">
          <p className="text-xs text-muted">{t.settings.slskdStepConnect}</p>
          <div className="flex flex-wrap gap-2">
            <Button size="sm" disabled={inCorso} onClick={() => azione(slskdConnect)}>
              <Plug size={14} /> {t.settings.soulseekConnect}
            </Button>
            {daemon?.owned === true && (
              <Button size="sm" variant="outline" disabled={inCorso} onClick={() => azione(daemonStop)}>
                {t.setup.daemonStop}
              </Button>
            )}
          </div>
        </div>
      )}

      {f === "collegato" && (
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="text-sm text-fg-strong">
            {slskd?.username ? t.settings.soulseekConnectedAs(slskd.username) : t.settings.soulseekConnected}
          </span>
          <div className="flex gap-2">
            <Button size="sm" variant="outline" disabled={inCorso} onClick={() => azione(slskdDisconnect)}>
              <Unplug size={14} /> {t.settings.soulseekDisconnect}
            </Button>
            {daemon?.owned === true && (
              <Button size="sm" variant="outline" disabled={inCorso} onClick={() => azione(daemonStop)}>
                {t.setup.daemonStop}
              </Button>
            )}
          </div>
        </div>
      )}

      {errore && <Alert tone="danger">{errore}</Alert>}
    </div>
  );
}
```

Il tipo `SlskdDaemonStatus` in `frontend/lib/api/slskd.ts` va esteso con i tre campi nuovi:

```ts
export type SlskdDaemonStatus = {
  reachable: boolean;
  owned: boolean | null;
  pid: number | null;
  installed: boolean;
  configured: boolean;
  username: string | null;
};
```

- [ ] **Step 5: Rieseguire i test**

```bash
cd frontend && npx vitest run tests/slskd-row.test.tsx
```

Atteso: 6 passed. Poi provarli: in `fase()`, far restituire sempre `"collega"`; almeno quattro test devono fallire. Rimettere.

- [ ] **Step 6: Commit**

```bash
git add frontend/components/slskd-row.tsx frontend/lib/api/slskd.ts frontend/lib/i18n frontend/tests/slskd-row.test.tsx
git commit -m "feat(slskd): una riga che copre scarica, configura, avvia e collega"
```

---

### Task 4: Montare la riga e togliere le due metà

**Files:**
- Modify: `frontend/components/settings/services-list.tsx` (rimuovere `SlskdExtra`, montare `SlskdRow`)
- Modify: `frontend/components/setup/steps/services.tsx` (aggiungere `slskd` a `ORDINE`)
- Modify: `frontend/components/setup/component-row.tsx` (rimuovere i rami `kind === "daemon"`)
- Modify: `frontend/components/setup/steps/prerequisites.tsx:52`, `frontend/components/setup/steps/summary.tsx:36`
- Modify: `frontend/lib/api/setup.ts:16,20`

**Interfaces:**
- Consumes: `<SlskdRow />` dal Task 3; il probe a due voci dal Task 2.
- Produces: nessuna interfaccia nuova.

- [ ] **Step 1: Sostituire `SlskdExtra` in Impostazioni**

In `frontend/components/settings/services-list.tsx`:

1. Sostituire `{s.key === "slskd" && <SlskdExtra t={t} />}` (riga 96) con `{s.key === "slskd" && <SlskdRow />}`.
2. Eliminare l'intera funzione `SlskdExtra` (righe 153-~270) e gli import che restano inutilizzati (`daemonStart`, `daemonStatus`, `daemonStop`, `slskdConnect`, `slskdDisconnect`, `slskdStatus`, `Plug`, `Unplug`, `Spinner` se non usati altrove nel file).
3. Aggiungere `import { SlskdRow } from "@/components/slskd-row";`.

Il commento alle righe 165-169 che rimanda al wizard sparisce con la funzione: non c'è più un wizard a cui rimandare.

- [ ] **Step 2: Aggiungere slskd al passo Servizi del wizard**

In `frontend/components/setup/steps/services.tsx`, riga 15:

```ts
const ORDINE: ServiceKey[] = ["spotify", "anthropic", "discogs", "acoustid", "slskd"];
```

E nella `<section>` di quel servizio, sotto la `ServiceCard`, montare la riga: `{service === "slskd" && <SlskdRow />}`. Se `ServiceKey` non contiene `"slskd"`, aggiungerlo in `frontend/lib/setup-services.ts`.

- [ ] **Step 3: Togliere i rami daemon da `component-row.tsx`**

Eliminare:

1. il blocco `{c.present && c.kind === "daemon" && (...)}` (riga ~218);
2. il blocco `{!c.present && c.kind === "daemon" && (...)}` con i campi credenziali (riga ~225);
3. la funzione `installaDemone` (righe 123-~160) e gli stati `username`, `password`, `avvioDemone`, `erroreDemone` che diventano inutilizzati;
4. le condizioni `c.kind !== "daemon"` alle righe ~245, ~286, ~314, che ora sono sempre vere.

- [ ] **Step 4: Ripulire prerequisiti, riepilogo e tipi**

In `steps/prerequisites.tsx:52` il filtro diventa:

```ts
  const mancanti = (components ?? []).filter((c) => !c.present && c.installable);
```

In `steps/summary.tsx:36`, eliminare `daemonKeys` e l'uso che ne viene fatto: non esistono più componenti di tipo demone.

In `lib/api/setup.ts`:

```ts
  kind: "system";
  source: "bundle" | "path" | "override" | null;
```

- [ ] **Step 5: Verificare che non resti nulla di orfano**

```bash
cd frontend && grep -rn '"daemon"' components lib app | grep -v slskd-row
```

Atteso: nessun risultato. Poi:

```bash
cd frontend && npm run lint && npm run test:unit
```

Atteso: lint senza errori (le variabili non più usate lo farebbero fallire), tutti i test verdi.

- [ ] **Step 6: Commit**

```bash
git add frontend/components frontend/lib
git commit -m "refactor(slskd): una riga sola, montata da Impostazioni e dal wizard"
```

---

### Task 5: Il passo che si salta quando non ha niente da chiedere

**Files:**
- Create: `frontend/lib/setup-steps.ts`
- Modify: `frontend/app/setup/page.tsx:20` (usa la funzione invece della costante)
- Test: `frontend/tests/setup-steps.test.tsx` (create)

**Perché un modulo separato:** `app/setup/page.tsx` è un file di route, e Next.js
valida quali export sono ammessi lì dentro (`default`, `metadata`, `dynamic`, …).
Esportare `passiDelWizard` dalla pagina farebbe fallire `npm run build` con un
errore di export non valido, e il test non avrebbe da dove importarla.

**Interfaces:**
- Consumes: `getProbe()` da `@/lib/api`, che dal Task 2 restituisce due componenti con `source` fra `"bundle" | "path" | "override" | null`.
- Produces: nessuna interfaccia nuova.

- [ ] **Step 1: Scrivere i test**

Creare `frontend/tests/setup-steps.test.tsx`:

```tsx
import { describe, expect, it } from "vitest";
import { passiDelWizard } from "@/lib/setup-steps";

/* Il passo dei prerequisiti esiste per far installare qualcosa. Quando non
   c'è niente da installare — l'app impacchettata porta i binari con sé — non
   ha ragione di esistere, e il contatore "passo N di M" deve restare onesto
   invece di saltare un numero. */

const daBundle = [
  { key: "ffmpeg", present: true, source: "bundle" },
  { key: "fpcalc", present: true, source: "bundle" },
];

describe("passi del wizard", () => {
  it("nel bundle sono quattro e i prerequisiti non ci sono", () => {
    const passi = passiDelWizard(daBundle);
    expect(passi).toEqual(["welcome", "library", "services", "summary"]);
  });

  it("da checkout restano cinque", () => {
    const passi = passiDelWizard([
      { key: "ffmpeg", present: true, source: "path" },
      { key: "fpcalc", present: false, source: null },
    ]);
    expect(passi).toContain("prerequisites");
    expect(passi).toHaveLength(5);
  });

  it("un solo componente non dal bundle basta a tenere il passo", () => {
    const passi = passiDelWizard([
      { key: "ffmpeg", present: true, source: "bundle" },
      { key: "fpcalc", present: true, source: "path" },
    ]);
    expect(passi).toContain("prerequisites");
  });

  it("finché il probe non ha risposto il passo resta", () => {
    // Toglierlo e rimetterlo mentre l'utente guarda sarebbe peggio che
    // mostrarlo un istante di troppo.
    expect(passiDelWizard(null)).toContain("prerequisites");
  });
});
```

- [ ] **Step 2: Eseguirli e vederli fallire**

```bash
cd frontend && npx vitest run tests/setup-steps.test.tsx
```

Atteso: FAIL — `Failed to resolve import "@/lib/setup-steps"`.

- [ ] **Step 3: Implementare**

Creare `frontend/lib/setup-steps.ts`:

```tsx
const TUTTI = ["welcome", "prerequisites", "library", "services", "summary"] as const;
export type Passo = (typeof TUTTI)[number];

/* Il passo dei prerequisiti esiste per far installare ffmpeg e fpcalc. Nel
   bundle viaggiano dentro l'app: non c'e' niente da installare e niente da
   scegliere, quindi il passo non si monta affatto — cosi' il contatore
   "passo N di M" resta onesto invece di saltare un numero. Basta un
   componente che NON venga dal bundle perche' il passo torni. */
export function passiDelWizard(
  componenti: { present: boolean; source: string | null }[] | null,
): Passo[] {
  const tuttoDalBundle =
    componenti !== null &&
    componenti.length > 0 &&
    componenti.every((c) => c.present && c.source === "bundle");
  return TUTTI.filter((p) => p !== "prerequisites" || !tuttoDalBundle);
}
```

In `frontend/app/setup/page.tsx`, togliere la costante `STEPS`, importare
`passiDelWizard` e `type Passo` da `@/lib/setup-steps`, leggere il probe una
volta e comporre i passi:

```tsx
  const [componenti, setComponenti] = useState<{ present: boolean; source: string | null }[] | null>(null);
  useEffect(() => {
    getProbe().then((r) => setComponenti(r.components)).catch(() => setComponenti(null));
  }, []);
  const STEPS = passiDelWizard(componenti);
```

Il resto della pagina non cambia: `STEPS[index]`, `STEPS.length` e la mappa dei titoli continuano a funzionare.

- [ ] **Step 4: Rieseguire i test**

```bash
cd frontend && npx vitest run tests/setup-steps.test.tsx
```

Atteso: 4 passed. Poi provarli: sostituire `c.source === "bundle"` con `c.present`; il test *"da checkout restano cinque"* deve fallire. Rimettere.

- [ ] **Step 5: Suite frontend intera**

```bash
cd frontend && npm run lint && npm run test:unit && npm run build
```

Atteso: tutto verde.

- [ ] **Step 6: Commit**

```bash
git add frontend/lib/setup-steps.ts frontend/app/setup/page.tsx frontend/tests/setup-steps.test.tsx
git commit -m "feat(setup): nel bundle il passo dei prerequisiti non ha niente da chiedere"
```

---

### Task 6: La documentazione e la prova nel bundle

**Files:**
- Modify: `docs/ARCHITECTURE.md` (sezione setup/probe), `docs/ROADMAP.md`, `PROGRESS.md`, `README.md` se descrive i passi del wizard

- [ ] **Step 1: Verificare cosa dicono oggi i documenti**

```bash
grep -rn "slskd" README.md docs/ARCHITECTURE.md | grep -iE "wizard|prerequisit|component" | head
```

Correggere ogni punto che descriva slskd come componente da installare dal wizard.

- [ ] **Step 2: `docs/ARCHITECTURE.md`**

Nella sezione del wizard/probe: il registry contiene due binari di sistema; slskd è un servizio e la sua riga copre l'intero percorso (scarica, configura, avvia, collega); il passo dei prerequisiti non si monta quando tutto viene dal bundle. Dire **perché** slskd non è un componente: la sua presenza è una risposta HTTP, non un file su `PATH`.

- [ ] **Step 3: `docs/ROADMAP.md` e `PROGRESS.md`**

Una voce datata 2026-08-24 che dica cosa è cambiato e cosa si è scoperto: le due interfacce non erano duplicati ma due metà complementari, e unirle era l'unico modo di togliere il rimando al wizard senza perdere installazione e configurazione.

- [ ] **Step 4: La prova nel bundle**

Costruire e verificare a mano, perché è il caso che ha originato il lavoro:

```bash
unset CRATORY_TAURI_EXTRA_CONFIG && export PATH="$HOME/.cargo/bin:$PATH" && export TAURI_SIGNING_PRIVATE_KEY="$(cat ~/.tauri/cratory.key)" && read -rs "?Password della chiave: " TAURI_SIGNING_PRIVATE_KEY_PASSWORD && export TAURI_SIGNING_PRIVATE_KEY_PASSWORD && python3 src-tauri/scripts/assembla.py
```

Poi, nell'app installata: il wizard ha **quattro** passi, non contiene *Prerequisiti*, e slskd si configura interamente dal passo *Servizi* — con l'account Soulseek già presente riconosciuto senza richiederlo.

- [ ] **Step 5: Suite complete e commit**

```bash
cd backend && ./.venv/bin/python -m pytest tests -q
cd ../frontend && npm run lint && npm run test:unit && npm run build
cd ../src-tauri && export PATH="$HOME/.cargo/bin:$PATH" && cargo test
```

```bash
git add README.md docs PROGRESS.md
git commit -m "docs: slskd e' un servizio, e il wizard smette di chiedere cio' che e' gia' risolto"
```
