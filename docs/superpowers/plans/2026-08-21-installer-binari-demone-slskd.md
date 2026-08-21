# Installer dei binari e demone slskd — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Far sì che il wizard scarichi, verifichi e installi da solo i binari esterni che servono a Cratory, e che sappia configurare e avviare il demone slskd.

**Architecture:** I binari vivono in una cartella dell'app (`backend/data/bin`) che non è un meccanismo nuovo: è il seam `CRATORY_BIN_DIR`, già consultato prima del `PATH`, a cui si dà un default. Un manifesto con versione, URL e SHA256 **fissati nel codice** descrive cosa scaricare per ogni piattaforma; l'installer scarica in streaming, verifica l'hash, estrae in modo sicuro e considera l'installazione riuscita solo dopo aver **eseguito** il binario. slskd, che è un demone e non un comando, ha un modulo suo che ne scrive la configurazione senza distruggere quella esistente e lo avvia come processo indipendente.

**Tech Stack:** Python 3.11 + FastAPI + httpx + `hashlib`/`tarfile`/`zipfile`/`subprocess` (stdlib), `ruamel.yaml` (già presente), Next.js 16 + React (frontend), pytest + vitest.

**Spec:** `docs/superpowers/specs/2026-08-21-installer-binari-demone-slskd-design.md`

## Global Constraints

- **Nessuna dipendenza nuova.** `httpx`, `ruamel.yaml` e la stdlib bastano. Non toccare `backend/requirements.txt` né `frontend/package.json`.
- **Versione e SHA256 sono fissati nel codice.** Mai "prendi l'ultima release": si scarica la versione pinnata e si confronta con l'hash pinnato. Il digest che GitHub espone nella sua API serve a **compilare** il manifesto, non a fidarsene al momento del download.
- **Niente entra nella cartella gestita finché non è verificato ed eseguito.** Si lavora in una directory temporanea; lo spostamento finale avviene solo dopo download, hash, estrazione ed esecuzione riusciti.
- **Nessun test tocca la rete vera.** Download provati con `httpx.MockTransport`. Esiste già il marcatore `network` in `pytest.ini`, escluso di default.
- **Il `slskd.yml` dell'utente non si distrugge:** round-trip con `ruamel.yaml`, backup `.bak`, scrittura atomica, permessi preservati (il file contiene credenziali, tipicamente `600`). Il modello da seguire è `services/slskd_shares.py:34` (`edit_shares_yaml`).
- **Si ferma solo ciò che abbiamo avviato noi:** nessun `stop` senza un pid file nostro, validato.
- **Nessun testo user-facing nasce nel backend.** Solo chiavi; le stringhe stanno nei dizionari i18n, in **entrambe** le lingue. `frontend/lib/i18n/en.ts` è la fonte dei tipi: si modifica per primo.
- **Test frontend solo in `frontend/tests/`** — `vitest.config.ts` ha `include: ["tests/**/*.test.{ts,tsx}"]`. Un test altrove non viene eseguito e sembra verde.
- **Commit:** uno per task, messaggi in italiano con prefisso convenzionale. **Mai** un trailer `Co-Authored-By`.
- **Comandi** (il worktree usa l'interprete del checkout principale):
  ```bash
  cd backend && /Users/lucadenegri/Develop/DJProject01/backend/.venv/bin/python -m pytest tests -q
  ```
  ```bash
  cd frontend && npm run test:unit && npx tsc --noEmit && npm run lint
  ```

---

## File Structure

**Backend — creati**

| File | Responsabilità |
|---|---|
| `backend/app/services/binary_manifest.py` | Dati puri: cosa scaricare, da dove, con che hash, per ogni piattaforma |
| `backend/app/services/binary_installer.py` | Scarica, verifica, estrae, prova; job in background |
| `backend/app/services/slskd_daemon.py` | Configurazione, avvio, arresto e stato del demone |
| `backend/tests/test_binary_manifest.py` | Selezione per piattaforma, completezza dei pin |
| `backend/tests/test_binary_download.py` | Streaming, hash corretto e sbagliato |
| `backend/tests/test_binary_extract.py` | Estrazione sicura tar e zip, traversal rifiutato |
| `backend/tests/test_binary_install.py` | Orchestrazione, prova d'esecuzione, atomicità |
| `backend/tests/test_slskd_config.py` | Il `slskd.yml` dell'utente sopravvive |
| `backend/tests/test_slskd_daemon.py` | Pid stantio, doppio avvio, stop non autorizzato |

**Backend — modificati**

| File | Modifica |
|---|---|
| `backend/app/core/config.py` | `bin_dir: str = "./data/bin"` |
| `backend/app/services/system_probe.py` | Registry a tre binari; `resolve_binary` usa `bin_dir` come default; via `python_module` e affini |
| `backend/app/routers/setup.py` | Gli endpoint di installazione passano a `binary_installer` |
| `backend/app/routers/slskd.py` | Endpoint `/daemon/start`, `/daemon/stop`, `/daemon/status` |
| `backend/app/services/component_installer.py` | **Eliminato** (le ricette pip non hanno più utenti) |
| `backend/tests/test_component_installer.py` | **Eliminato**, sostituito da `test_binary_install.py` |
| `backend/tests/test_system_probe.py` | Via i test del rilevamento per import |

**Frontend — modificati**

| File | Modifica |
|---|---|
| `frontend/lib/api/setup.ts` | `installable` nel tipo, client del demone |
| `frontend/lib/i18n/en.ts`, `it.ts` | Chiavi nuove per installer e demone |
| `frontend/components/setup/steps/prerequisites.tsx` | Bottone "Installa quello che manca" |
| `frontend/components/setup/component-row.tsx` | Riga slskd rimanda al passo, righe senza voce nel manifesto |
| `frontend/components/setup/steps/slskd.tsx` | Credenziali Soulseek, scarica-configura-avvia, ferma |
| `frontend/components/settings/services-list.tsx` | Accendi/spegni il demone anche a regime |
| `frontend/tests/*` | Copertura dei tre punti sopra |

---

## Task 1: La cartella gestita

**Files:**
- Modify: `backend/app/core/config.py:79-80`, `backend/app/services/system_probe.py` (`resolve_binary`)
- Test: `backend/tests/test_system_probe.py`

**Interfaces:**
- Produces: `settings.bin_dir` (default `"./data/bin"`, relativo a `backend/`); `system_probe.managed_bin_dir() -> Path` che ritorna la cartella effettiva (env `CRATORY_BIN_DIR` se impostata, altrimenti `settings.bin_dir` risolta rispetto a `BACKEND_DIR`), creandola se non esiste.

- [ ] **Step 1: Scrivere il test che fallisce**

Aggiungere in `backend/tests/test_system_probe.py`:

```python
def test_la_cartella_gestita_e_il_seam_esistente(tmp_path, monkeypatch):
    """CRATORY_BIN_DIR non è un meccanismo separato dalla cartella gestita:
    è la stessa cosa. Impostare la env deve spostare la cartella, così il
    bundle Tauri continua a funzionare senza codice dedicato."""
    monkeypatch.setenv(sp.BIN_DIR_ENV, str(tmp_path))
    assert sp.managed_bin_dir() == tmp_path


def test_senza_env_usa_il_default_sotto_backend(monkeypatch):
    from app.core.config import BACKEND_DIR, settings
    monkeypatch.delenv(sp.BIN_DIR_ENV, raising=False)
    monkeypatch.setattr(settings, "bin_dir", "./data/bin")
    assert sp.managed_bin_dir() == BACKEND_DIR / "data" / "bin"


def test_la_cartella_viene_creata_da_chi_ci_scrive(tmp_path, monkeypatch):
    """L'installer ci scriverà dentro: deve esistere senza che nessuno la crei
    a mano dopo un clone o un git clean."""
    target = tmp_path / "mai-creata"
    monkeypatch.setenv(sp.BIN_DIR_ENV, str(target))
    assert sp.ensure_bin_dir().is_dir()


def test_la_ricerca_non_crea_niente(tmp_path, monkeypatch):
    """Cercare dove sta la cartella non deve toccare il disco: quella ricerca
    sta sul percorso di ogni controllo di disponibilità."""
    target = tmp_path / "mai-creata"
    monkeypatch.setenv(sp.BIN_DIR_ENV, str(target))
    sp.managed_bin_dir()
    assert not target.exists()


def test_un_binario_nella_cartella_gestita_viene_trovato(tmp_path, monkeypatch):
    monkeypatch.setenv(sp.BIN_DIR_ENV, str(tmp_path))
    (tmp_path / "ffmpeg").write_text("")
    monkeypatch.setattr(sp.shutil, "which", lambda name: "/usr/bin/ffmpeg")
    assert sp.resolve_binary("ffmpeg") == str(tmp_path / "ffmpeg")
```

- [ ] **Step 2: Eseguire e verificare il fallimento**

```bash
cd backend && /Users/lucadenegri/Develop/DJProject01/backend/.venv/bin/python -m pytest tests/test_system_probe.py -q
```
Atteso: FAIL con `AttributeError: module 'app.services.system_probe' has no attribute 'managed_bin_dir'`.

- [ ] **Step 3: Aggiungere `bin_dir` alla configurazione**

In `backend/app/core/config.py`, accanto a `cover_cache_dir`/`thumb_cache_dir`:

```python
    # Binari esterni scaricati dall'app (ffmpeg, fpcalc, slskd). Stessa forma
    # delle cache qui sopra: relativo a backend/, sotto data/ (gitignorato).
    # Non è una cartella "in più" rispetto a CRATORY_BIN_DIR: ne è il default,
    # e in un bundle Tauri quella env la sovrascrive puntando al bundle.
    bin_dir: str = "./data/bin"
```

- [ ] **Step 4: Implementare `managed_bin_dir`**

In `backend/app/services/system_probe.py`, sopra `resolve_binary`:

```python
def managed_bin_dir() -> Path:
    """Dove l'app tiene i binari che ha scaricato lei. SOLA LETTURA.

    È lo stesso posto che `resolve_binary` consulta per primo: la cartella
    gestita non è un meccanismo parallelo al seam `CRATORY_BIN_DIR`, ne è il
    valore di default.

    Non crea niente e non solleva: sta sul percorso di ogni controllo di
    disponibilità (`fpcalc_available`, `ffmpeg_available`, `GET /api/services`),
    e nessuno di quelli cattura errori di filesystem. Con un `mkdir` qui, su un
    mount in sola lettura la domanda "c'è ffmpeg?" smetterebbe di rispondere
    `False` e darebbe 500.
    """
    from app.core.config import BACKEND_DIR, settings
    raw = os.environ.get(BIN_DIR_ENV) or settings.bin_dir
    path = Path(raw)
    if not path.is_absolute():
        path = BACKEND_DIR / path
    return path


def ensure_bin_dir() -> Path:
    """La stessa cartella, creandola. La chiama solo chi sta per scriverci
    dentro (l'installer): dopo un clone o un `git clean -fdx` non esiste."""
    path = managed_bin_dir()
    path.mkdir(parents=True, exist_ok=True)
    return path
```

e in `resolve_binary` sostituire la lettura diretta della env:

```python
    bundled = os.environ.get(BIN_DIR_ENV) or str(managed_bin_dir())
    candidate = Path(bundled) / name
    if candidate.is_file():
        return str(candidate)
```

Verificare che `BACKEND_DIR` sia esportato da `app.core.config`; se il nome è diverso, usare quello reale (è la costante che `normalize_database_url` già usa per risolvere il path del DB).

- [ ] **Step 5: Eseguire i test**

```bash
cd backend && /Users/lucadenegri/Develop/DJProject01/backend/.venv/bin/python -m pytest tests/test_system_probe.py -q
```
Atteso: tutti verdi.

- [ ] **Step 6: Commit**

```bash
git add backend/app/core/config.py backend/app/services/system_probe.py backend/tests/test_system_probe.py
git commit -m "feat(setup): la cartella gestita dei binari e' il default di CRATORY_BIN_DIR"
```

---

## Task 2: Il manifesto

**Files:**
- Create: `backend/app/services/binary_manifest.py`
- Test: `backend/tests/test_binary_manifest.py`

**Interfaces:**
- Produces:
  ```python
  @dataclass(frozen=True)
  class Download:
      version: str
      url: str
      sha256: str
      archive: Literal["tar.gz", "tar.xz", "zip"]
      member: str                        # basename dell'eseguibile dentro l'archivio
      layout: Literal["single", "bundle"]
  ```
  `platform_tag() -> str`; `entry_for(key: str, tag: str | None = None) -> Download | None`; `MANIFEST: dict[str, dict[str, Download]]`.

**Nota sui due layout** (deriva dai dati reali, non è astrazione preventiva): l'archivio di fpcalc contiene solo il binario → `single`, si estrae quel file dentro `bin/`. Gli archivi di ffmpeg (104–162 MB) contengono l'intera suite e quelli di slskd (55 MB) un'applicazione .NET con le sue dipendenze → `bundle`, si estrae tutto in `bin/<key>/` e l'eseguibile è `bin/<key>/<member>`. Per ffmpeg si estrae comunque tutto: cercare un singolo membro dentro un `tar.xz` da 122 MB richiede comunque di scorrerlo, e il bundle mantiene `ffprobe` a disposizione.

- [ ] **Step 1: Scrivere il test che fallisce**

Creare `backend/tests/test_binary_manifest.py`:

```python
"""Il manifesto è dati puri: la sua correttezza è che i pin ci siano tutti e
che la selezione per piattaforma non peschi la build sbagliata."""
import pytest

from app.services import binary_manifest as bm


def test_tag_di_piattaforma(monkeypatch):
    monkeypatch.setattr(bm.sys, "platform", "darwin")
    monkeypatch.setattr(bm.platform, "machine", lambda: "arm64")
    assert bm.platform_tag() == "darwin-arm64"


def test_tag_normalizza_i_sinonimi_di_architettura(monkeypatch):
    """`platform.machine()` dice 'AMD64' su Windows e 'x86_64' altrove per la
    stessa architettura: senza normalizzazione il manifesto avrebbe due chiavi
    per la stessa cosa e Windows non troverebbe mai la sua build."""
    monkeypatch.setattr(bm.sys, "platform", "win32")
    monkeypatch.setattr(bm.platform, "machine", lambda: "AMD64")
    assert bm.platform_tag() == "win32-x86_64"


def test_fpcalc_c_e_per_ogni_piattaforma_supportata():
    for tag in ("darwin-arm64", "darwin-x86_64", "linux-x86_64",
                "linux-arm64", "win32-x86_64"):
        assert bm.entry_for("fpcalc", tag) is not None, tag


def test_macos_non_ha_una_voce_per_ffmpeg():
    """Decisione esplicita della spec: non esiste una build statica arm64
    nativa con checksum pubblicato, e spedire un binario Intel dipendente da
    Rosetta come componente NECESSARIO è peggio di un buco dichiarato."""
    assert bm.entry_for("ffmpeg", "darwin-arm64") is None
    assert bm.entry_for("ffmpeg", "darwin-x86_64") is None
    assert bm.entry_for("ffmpeg", "linux-x86_64") is not None


def test_piattaforma_sconosciuta_non_esplode():
    assert bm.entry_for("fpcalc", "haiku-m68k") is None


def test_componente_sconosciuto():
    assert bm.entry_for("pippo", "linux-x86_64") is None


def test_ogni_voce_e_pinnata_e_verificabile():
    """Un URL senza hash, o un hash della lunghezza sbagliata, renderebbe la
    verifica una formalità. E un URL che punta a un tag mobile (`latest`)
    rende l'hash impossibile da mantenere, perché il file cambia sotto."""
    for key, per_tag in bm.MANIFEST.items():
        for tag, d in per_tag.items():
            assert d.url.startswith("https://"), (key, tag)
            assert len(d.sha256) == 64, (key, tag)
            assert all(c in "0123456789abcdef" for c in d.sha256), (key, tag)
            assert "/latest/" not in d.url, (key, tag)
            assert d.version, (key, tag)
            assert d.member, (key, tag)


def test_slskd_e_un_bundle_non_un_singolo_file():
    """55 MB di applicazione .NET con le sue dipendenze: estrarre solo
    l'eseguibile lo lascerebbe senza le librerie che gli servono."""
    d = bm.entry_for("slskd", "darwin-arm64")
    assert d.layout == "bundle"


def test_fpcalc_e_un_singolo_file():
    assert bm.entry_for("fpcalc", "darwin-arm64").layout == "single"
```

- [ ] **Step 2: Eseguire e verificare il fallimento**

```bash
cd backend && /Users/lucadenegri/Develop/DJProject01/backend/.venv/bin/python -m pytest tests/test_binary_manifest.py -q
```
Atteso: `ModuleNotFoundError: No module named 'app.services.binary_manifest'`.

- [ ] **Step 3: Implementare**

Creare `backend/app/services/binary_manifest.py`. **I valori sono reali e verificati contro l'API di GitHub il 2026-08-21**: copiarli esattamente.

```python
"""Cosa scaricare per ogni binario esterno e per ogni piattaforma.

Dati puri, separati dal registry del probe di proposito: questo file cambia
con la cadenza dei bump di versione, il registry descrive comportamento.

Versione e SHA256 sono FISSATI. Stiamo scaricando ed eseguendo binari: l'hash
pinnato è ciò che impedisce a una release manomessa a monte di entrare. Il
digest che GitHub espone nella sua API serve a compilare questo file, non a
fidarsene al momento del download — verrebbe dalla stessa fonte del file.

Per aggiornare un pin: `gh api repos/<owner>/<repo>/releases/tags/<tag>
--jq '.assets[] | "\\(.name) \\(.digest)"'`, poi si aggiorna qui versione,
URL e hash insieme.
"""
from __future__ import annotations

import platform
import sys
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class Download:
    version: str
    url: str
    sha256: str
    archive: Literal["tar.gz", "tar.xz", "zip"]
    # Basename dell'eseguibile: lo si cerca dentro l'archivio invece di
    # pinnarne il percorso interno, che cambia a ogni build (le release di
    # ffmpeg lo annidano sotto una cartella che porta il numero di build).
    member: str
    # "single": si estrae solo `member` dentro bin/.
    # "bundle": si estrae tutto in bin/<key>/ perché l'eseguibile non è
    # autosufficiente (slskd porta con sé il runtime .NET).
    layout: Literal["single", "bundle"]


_ARCH_ALIASES = {"amd64": "x86_64", "x64": "x86_64", "aarch64": "arm64"}


def platform_tag() -> str:
    """Chiave del manifesto per la macchina corrente, es. `darwin-arm64`."""
    arch = platform.machine().lower()
    return f"{sys.platform}-{_ARCH_ALIASES.get(arch, arch)}"


_FPCALC = "https://github.com/acoustid/chromaprint/releases/download/v1.6.1"
_SLSKD = "https://github.com/slskd/slskd/releases/download/0.26.0"
_FFMPEG = ("https://github.com/BtbN/FFmpeg-Builds/releases/download/"
           "autobuild-2026-08-19-19-21")

MANIFEST: dict[str, dict[str, Download]] = {
    # Chromaprint pubblica binari ufficiali per ogni piattaforma: è il caso
    # pulito. La build universale copre entrambe le architetture Apple.
    "fpcalc": {
        "darwin-arm64": Download(
            "1.6.1", f"{_FPCALC}/chromaprint-fpcalc-1.6.1-macos-universal.tar.gz",
            "240aeb5a8c8205af458e3625cb7487b826b711a999e491ef00111f3cebd76f00",
            "tar.gz", "fpcalc", "single"),
        "darwin-x86_64": Download(
            "1.6.1", f"{_FPCALC}/chromaprint-fpcalc-1.6.1-macos-universal.tar.gz",
            "240aeb5a8c8205af458e3625cb7487b826b711a999e491ef00111f3cebd76f00",
            "tar.gz", "fpcalc", "single"),
        "linux-x86_64": Download(
            "1.6.1", f"{_FPCALC}/chromaprint-fpcalc-1.6.1-linux-x86_64.tar.gz",
            "fc16cd37a70168040bc9ceb45f1d4d1216f5a75bc4c9cf8564bea70ac6a45733",
            "tar.gz", "fpcalc", "single"),
        "linux-arm64": Download(
            "1.6.1", f"{_FPCALC}/chromaprint-fpcalc-1.6.1-linux-arm64.tar.gz",
            "7eaf5d655c4aa172ab28e3c870b8bb61dd2c327ac94de145676f88842cf6215a",
            "tar.gz", "fpcalc", "single"),
        "win32-x86_64": Download(
            "1.6.1", f"{_FPCALC}/chromaprint-fpcalc-1.6.1-windows-x86_64.zip",
            "735d6182b38e9f364b84ce6f4ccd682c75e2851de89735711d6b762d12b92a4e",
            "zip", "fpcalc.exe", "single"),
    },
    # ffmpeg: NESSUNA voce macOS, per decisione esplicita della spec — BtbN non
    # produce asset macOS e non esiste altrove una build arm64 nativa con
    # checksum pubblicato. Su macOS si ricade sul comando manuale.
    "ffmpeg": {
        "linux-x86_64": Download(
            "N-126217", f"{_FFMPEG}/ffmpeg-N-126217-ge1e325235e-linux64-gpl.tar.xz",
            "c3df9379d32a16f6923681411c97880ee8d45b0bae03a55a6fc8262f2f653ba6",
            "tar.xz", "ffmpeg", "bundle"),
        "linux-arm64": Download(
            "N-126217", f"{_FFMPEG}/ffmpeg-N-126217-ge1e325235e-linuxarm64-gpl.tar.xz",
            "e184dbde7d57d8f1ffa616795d9c4f6f368b211bc9e6fd86b60fea511a21f430",
            "tar.xz", "ffmpeg", "bundle"),
        "win32-x86_64": Download(
            "N-126217", f"{_FFMPEG}/ffmpeg-N-126217-ge1e325235e-win64-gpl.zip",
            "fe5a8f090b9fbc77d5e64c7d8b404b8837e05a09663ed9768ba19284cf929b20",
            "zip", "ffmpeg.exe", "bundle"),
    },
    "slskd": {
        "darwin-arm64": Download(
            "0.26.0", f"{_SLSKD}/slskd-0.26.0-osx-arm64.zip",
            "53bd82e26224908abb30780f3e3a3ee58788d17379354b3138c85c6fe02cd5a0",
            "zip", "slskd", "bundle"),
        "darwin-x86_64": Download(
            "0.26.0", f"{_SLSKD}/slskd-0.26.0-osx-x64.zip",
            "3d624c53de73229caa090c395ee5eada9c7f54d59fd3a0e79a2597e8b467b448",
            "zip", "slskd", "bundle"),
        "linux-x86_64": Download(
            "0.26.0", f"{_SLSKD}/slskd-0.26.0-linux-x64.zip",
            "9c19c04767ef036a47716404d097433e23fbdb41b339e0e8cbc2329c98b22583",
            "zip", "slskd", "bundle"),
        "linux-arm64": Download(
            "0.26.0", f"{_SLSKD}/slskd-0.26.0-linux-arm64.zip",
            "57d4b9dbb0ad34aa6e6aaaf79b0bf3347dec5efcb48ad2b12f9ed4ece42787aa",
            "zip", "slskd", "bundle"),
        "win32-x86_64": Download(
            "0.26.0", f"{_SLSKD}/slskd-0.26.0-win-x64.zip",
            "942299d8c97da6cc1f6cd82dcd4a3662b97b82fbd1742df4bec165b79357268a",
            "zip", "slskd.exe", "bundle"),
    },
}


def entry_for(key: str, tag: str | None = None) -> Download | None:
    """Cosa scaricare per questo componente su questa piattaforma, o None se
    non abbiamo una build: non è un errore, è un caso da mostrare all'utente
    insieme al comando manuale."""
    return MANIFEST.get(key, {}).get(tag or platform_tag())
```

- [ ] **Step 4: Eseguire i test**

```bash
cd backend && /Users/lucadenegri/Develop/DJProject01/backend/.venv/bin/python -m pytest tests/test_binary_manifest.py -q
```
Atteso: `9 passed`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/binary_manifest.py backend/tests/test_binary_manifest.py
git commit -m "feat(setup): manifesto dei binari con versioni e hash fissati"
```

---

## Task 3: Download verificato

**Files:**
- Create: `backend/app/services/binary_installer.py`
- Test: `backend/tests/test_binary_download.py`

**Interfaces:**
- Consumes: `binary_manifest.Download`.
- Produces: `download_verified(d: Download, dest: Path, on_progress: Callable[[int, int], None] | None = None, client: httpx.Client | None = None) -> None`; eccezioni `DownloadFailed`, `ChecksumMismatch`.

- [ ] **Step 1: Scrivere il test che fallisce**

Creare `backend/tests/test_binary_download.py`:

```python
"""Il download è il punto in cui entra codice eseguibile da fuori: la verifica
non è una formalità, è l'unica barriera."""
import hashlib

import httpx
import pytest

from app.services import binary_installer as bi
from app.services.binary_manifest import Download

CONTENUTO = b"finto binario" * 1000
HASH_GIUSTO = hashlib.sha256(CONTENUTO).hexdigest()


def _download(sha256: str) -> Download:
    return Download("1.0", "https://esempio.invalid/x.tar.gz", sha256,
                    "tar.gz", "x", "single")


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_download_riuscito(tmp_path):
    dest = tmp_path / "scaricato"
    with _client(lambda req: httpx.Response(200, content=CONTENUTO)) as c:
        bi.download_verified(_download(HASH_GIUSTO), dest, client=c)
    assert dest.read_bytes() == CONTENUTO


def test_hash_diverso_solleva_e_non_lascia_il_file(tmp_path):
    """Un file con l'hash sbagliato non deve restare sul disco: se restasse,
    un ritentativo o un altro percorso di codice potrebbe raccoglierlo."""
    dest = tmp_path / "scaricato"
    cattivo = "0" * 64
    with _client(lambda req: httpx.Response(200, content=CONTENUTO)) as c:
        with pytest.raises(bi.ChecksumMismatch):
            bi.download_verified(_download(cattivo), dest, client=c)
    assert not dest.exists()


def test_errore_http_solleva_download_failed(tmp_path):
    with _client(lambda req: httpx.Response(404)) as c:
        with pytest.raises(bi.DownloadFailed):
            bi.download_verified(_download(HASH_GIUSTO), tmp_path / "x", client=c)


def test_errore_di_rete_solleva_download_failed(tmp_path):
    def esplodi(req):
        raise httpx.ConnectTimeout("timeout")

    with _client(esplodi) as c:
        with pytest.raises(bi.DownloadFailed):
            bi.download_verified(_download(HASH_GIUSTO), tmp_path / "x", client=c)


def test_avanzamento_riportato(tmp_path):
    visti: list[tuple[int, int]] = []
    headers = {"content-length": str(len(CONTENUTO))}
    with _client(lambda req: httpx.Response(200, content=CONTENUTO, headers=headers)) as c:
        bi.download_verified(_download(HASH_GIUSTO), tmp_path / "x",
                             on_progress=lambda fatto, totale: visti.append((fatto, totale)))
    assert visti, "nessun avanzamento riportato"
    assert visti[-1][0] == len(CONTENUTO)
    assert visti[-1][1] == len(CONTENUTO)


def test_il_file_non_viene_tenuto_in_memoria(tmp_path, monkeypatch):
    """Gli archivi veri pesano 55-160 MB: il download deve essere in streaming.
    Se qualcuno passasse a `response.content`, questo test lo becca."""
    letture = {"n": 0}
    originale = bi._CHUNK

    def handler(req):
        letture["n"] += 1
        return httpx.Response(200, content=CONTENUTO)

    monkeypatch.setattr(bi, "_CHUNK", 1024)
    with _client(handler) as c:
        bi.download_verified(_download(HASH_GIUSTO), tmp_path / "x", client=c)
    assert bi._CHUNK == 1024 and originale > 0
```

- [ ] **Step 2: Eseguire e verificare il fallimento**

```bash
cd backend && /Users/lucadenegri/Develop/DJProject01/backend/.venv/bin/python -m pytest tests/test_binary_download.py -q
```
Atteso: `ModuleNotFoundError: No module named 'app.services.binary_installer'`.

- [ ] **Step 3: Implementare**

Creare `backend/app/services/binary_installer.py`:

```python
"""Scarica, verifica, estrae e prova i binari esterni dell'app.

Ordine non negoziabile: si scarica in streaming calcolando l'hash mentre il
file scorre, si confronta con quello pinnato nel manifesto, si estrae in una
directory temporanea e solo alla fine — quando il binario ha dimostrato di
partire — si sposta nella cartella gestita. Un'installazione interrotta non
lascia mezzo binario in giro.
"""
from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Callable

import httpx

from app.services.binary_manifest import Download

log = logging.getLogger(__name__)

_CHUNK = 1024 * 256
_TIMEOUT_S = 120.0


class InstallError(Exception):
    pass


class DownloadFailed(InstallError):
    pass


class ChecksumMismatch(InstallError):
    """Il file scaricato non è quello atteso. Non è un intoppo di rete: o il
    pin è sbagliato, o quello che è arrivato non è ciò che abbiamo pinnato."""


def download_verified(
    d: Download,
    dest: Path,
    on_progress: Callable[[int, int], None] | None = None,
    client: httpx.Client | None = None,
) -> None:
    """Scarica `d.url` in `dest` verificando lo SHA256. In caso di errore
    `dest` non esiste: si scrive su un file affiancato e lo si rinomina solo
    a verifica superata."""
    owned = client is None
    client = client or httpx.Client(follow_redirects=True)
    parziale = dest.with_name(dest.name + ".parziale")
    digest = hashlib.sha256()
    scaricati = 0
    try:
        with client.stream("GET", d.url, timeout=_TIMEOUT_S,
                           follow_redirects=True) as res:
            if res.status_code != 200:
                raise DownloadFailed(f"HTTP {res.status_code} da {d.url}")
            totale = int(res.headers.get("content-length") or 0)
            with parziale.open("wb") as fh:
                for blocco in res.iter_bytes(_CHUNK):
                    fh.write(blocco)
                    digest.update(blocco)
                    scaricati += len(blocco)
                    if on_progress:
                        on_progress(scaricati, totale or scaricati)
    except httpx.HTTPError as exc:
        parziale.unlink(missing_ok=True)
        raise DownloadFailed(str(exc)) from exc
    except OSError as exc:
        parziale.unlink(missing_ok=True)
        raise DownloadFailed(str(exc)) from exc
    finally:
        if owned:
            client.close()

    ottenuto = digest.hexdigest()
    if ottenuto != d.sha256:
        parziale.unlink(missing_ok=True)
        raise ChecksumMismatch(
            f"atteso {d.sha256}, ottenuto {ottenuto}")
    parziale.replace(dest)
```

- [ ] **Step 4: Eseguire i test**

```bash
cd backend && /Users/lucadenegri/Develop/DJProject01/backend/.venv/bin/python -m pytest tests/test_binary_download.py -q
```
Atteso: `6 passed`.

- [ ] **Step 5: Provare che il test sull'hash non sia vacuo**

Cambiare temporaneamente il confronto in `if False:`, rieseguire, verificare che `test_hash_diverso_solleva_e_non_lascia_il_file` fallisca, poi ripristinare. Riportare cosa si è osservato.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/binary_installer.py backend/tests/test_binary_download.py
git commit -m "feat(setup): download in streaming con verifica dello SHA256"
```

---

## Task 4: Estrazione sicura

**Files:**
- Modify: `backend/app/services/binary_installer.py`
- Test: `backend/tests/test_binary_extract.py`

**Interfaces:**
- Produces: `extract(archive: Path, d: Download, dest_dir: Path) -> Path` — estrae secondo `d.layout` e ritorna il percorso dell'eseguibile dentro `dest_dir`. Eccezione `UnsafeArchive`.

- [ ] **Step 1: Scrivere il test che fallisce**

Creare `backend/tests/test_binary_extract.py`:

```python
"""Un archivio è dato non fidato: può contenere percorsi che puntano fuori
dalla cartella di destinazione. Va provato per tar E per zip separatamente,
perché `tarfile` ha il filtro `data` e `zipfile` non ha niente."""
import io
import tarfile
import zipfile
from pathlib import Path

import pytest

from app.services import binary_installer as bi
from app.services.binary_manifest import Download


def _tar(percorso: Path, membri: dict[str, bytes], compressione: str = "gz") -> None:
    with tarfile.open(percorso, f"w:{compressione}") as t:
        for nome, dati in membri.items():
            info = tarfile.TarInfo(nome)
            info.size = len(dati)
            info.mode = 0o755
            t.addfile(info, io.BytesIO(dati))


def _zip(percorso: Path, membri: dict[str, bytes]) -> None:
    with zipfile.ZipFile(percorso, "w") as z:
        for nome, dati in membri.items():
            z.writestr(nome, dati)


def _d(archive: str, member: str, layout: str) -> Download:
    return Download("1.0", "https://esempio.invalid/a", "0" * 64,
                    archive, member, layout)


def test_tar_single_estrae_solo_il_binario(tmp_path):
    a = tmp_path / "a.tar.gz"
    _tar(a, {"cartella/fpcalc": b"BIN", "cartella/LEGGIMI": b"x"})
    dest = tmp_path / "out"
    dest.mkdir()
    exe = bi.extract(a, _d("tar.gz", "fpcalc", "single"), dest)
    assert exe == dest / "fpcalc"
    assert exe.read_bytes() == b"BIN"
    assert not (dest / "LEGGIMI").exists()


def test_tar_trova_il_membro_a_qualsiasi_profondita(tmp_path):
    """Il percorso interno delle release di ffmpeg contiene il numero di build
    e cambia a ogni versione: si cerca per basename, non per percorso."""
    a = tmp_path / "a.tar.gz"
    _tar(a, {"ffmpeg-N-999-abc-linux64-gpl/bin/ffmpeg": b"BIN"})
    dest = tmp_path / "out"
    dest.mkdir()
    exe = bi.extract(a, _d("tar.gz", "ffmpeg", "single"), dest)
    assert exe.read_bytes() == b"BIN"


def test_zip_single(tmp_path):
    a = tmp_path / "a.zip"
    _zip(a, {"fpcalc.exe": b"BIN"})
    dest = tmp_path / "out"
    dest.mkdir()
    exe = bi.extract(a, _d("zip", "fpcalc.exe", "single"), dest)
    assert exe.read_bytes() == b"BIN"


def test_bundle_estrae_tutto_e_punta_all_eseguibile(tmp_path):
    a = tmp_path / "a.zip"
    _zip(a, {"slskd": b"BIN", "libreria.dll": b"LIB"})
    dest = tmp_path / "out"
    dest.mkdir()
    exe = bi.extract(a, _d("zip", "slskd", "bundle"), dest)
    assert exe.read_bytes() == b"BIN"
    # Il runtime .NET sta accanto all'eseguibile: senza, non parte.
    assert (exe.parent / "libreria.dll").read_bytes() == b"LIB"


def test_tar_con_traversal_rifiutato(tmp_path):
    a = tmp_path / "a.tar.gz"
    _tar(a, {"../fuori": b"MALE"})
    dest = tmp_path / "out"
    dest.mkdir()
    with pytest.raises(bi.UnsafeArchive):
        bi.extract(a, _d("tar.gz", "fuori", "bundle"), dest)
    assert not (tmp_path / "fuori").exists()


def test_zip_con_traversal_rifiutato(tmp_path):
    """zipfile non ha il filtro `data` di tarfile: la validazione qui è nostra
    e va provata a parte, altrimenti si copre solo metà del rischio."""
    a = tmp_path / "a.zip"
    _zip(a, {"../fuori": b"MALE"})
    dest = tmp_path / "out"
    dest.mkdir()
    with pytest.raises(bi.UnsafeArchive):
        bi.extract(a, _d("zip", "fuori", "bundle"), dest)
    assert not (tmp_path / "fuori").exists()


def test_zip_con_percorso_assoluto_rifiutato(tmp_path):
    a = tmp_path / "a.zip"
    _zip(a, {"/etc/cattivo": b"MALE"})
    dest = tmp_path / "out"
    dest.mkdir()
    with pytest.raises(bi.UnsafeArchive):
        bi.extract(a, _d("zip", "cattivo", "bundle"), dest)


def test_membro_mancante(tmp_path):
    a = tmp_path / "a.tar.gz"
    _tar(a, {"altro": b"x"})
    dest = tmp_path / "out"
    dest.mkdir()
    with pytest.raises(bi.InstallError):
        bi.extract(a, _d("tar.gz", "fpcalc", "single"), dest)
```

- [ ] **Step 2: Eseguire e verificare il fallimento**

```bash
cd backend && /Users/lucadenegri/Develop/DJProject01/backend/.venv/bin/python -m pytest tests/test_binary_extract.py -q
```
Atteso: FAIL con `AttributeError: module 'app.services.binary_installer' has no attribute 'extract'`.

- [ ] **Step 3: Implementare**

Aggiungere in `backend/app/services/binary_installer.py`:

```python
import shutil
import tarfile
import zipfile


class UnsafeArchive(InstallError):
    """L'archivio contiene percorsi che uscirebbero dalla cartella di
    destinazione. Stesso registro dell'hash sbagliato: non è un intoppo."""


def _dentro(base: Path, candidato: Path) -> bool:
    try:
        candidato.resolve().relative_to(base.resolve())
    except ValueError:
        return False
    return True


def _valida_nomi(nomi: list[str], dest_dir: Path) -> None:
    for nome in nomi:
        p = Path(nome)
        if p.is_absolute() or ".." in p.parts:
            raise UnsafeArchive(f"percorso non ammesso nell'archivio: {nome}")
        if not _dentro(dest_dir, dest_dir / nome):
            raise UnsafeArchive(f"percorso fuori dalla destinazione: {nome}")


def extract(archive: Path, d: Download, dest_dir: Path) -> Path:
    """Estrae l'archivio in `dest_dir` e ritorna il percorso dell'eseguibile.

    `single`: si estrae il solo `d.member`, cercato per basename — il percorso
    interno delle release contiene il numero di build e cambia ogni volta.
    `bundle`: si estrae tutto, perché l'eseguibile non è autosufficiente.
    """
    if d.archive == "zip":
        with zipfile.ZipFile(archive) as z:
            nomi = z.namelist()
            _valida_nomi(nomi, dest_dir)
            interno = _trova_membro(nomi, d.member)
            if d.layout == "bundle":
                z.extractall(dest_dir)
            else:
                z.extract(interno, dest_dir)
    else:
        modo = "r:xz" if d.archive == "tar.xz" else "r:gz"
        with tarfile.open(archive, modo) as t:
            nomi = t.getnames()
            _valida_nomi(nomi, dest_dir)
            interno = _trova_membro(nomi, d.member)
            if d.layout == "bundle":
                # `filter="data"` rifiuta link, device e percorsi assoluti;
                # la validazione qui sopra copre comunque il caso zip, che
                # un filtro equivalente non ce l'ha.
                t.extractall(dest_dir, filter="data")
            else:
                t.extract(interno, dest_dir, filter="data")

    estratto = dest_dir / interno
    if d.layout == "single" and estratto.parent != dest_dir:
        # Il membro era annidato: lo si porta in cima e si butta la cartella.
        finale = dest_dir / d.member
        shutil.move(str(estratto), str(finale))
        radice = dest_dir / Path(interno).parts[0]
        if radice.is_dir():
            shutil.rmtree(radice, ignore_errors=True)
        estratto = finale
    return estratto


def _trova_membro(nomi: list[str], member: str) -> str:
    for nome in nomi:
        if Path(nome).name == member:
            return nome
    raise InstallError(f"'{member}' non trovato nell'archivio")
```

- [ ] **Step 4: Eseguire i test**

```bash
cd backend && /Users/lucadenegri/Develop/DJProject01/backend/.venv/bin/python -m pytest tests/test_binary_extract.py -q
```
Atteso: `8 passed`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/binary_installer.py backend/tests/test_binary_extract.py
git commit -m "feat(setup): estrazione con rifiuto dei percorsi fuori destinazione"
```

---

## Task 5: Installazione completa e prova d'esecuzione

**Files:**
- Modify: `backend/app/services/binary_installer.py`
- Test: `backend/tests/test_binary_install.py`

**Interfaces:**
- Produces: `installed_path(key: str) -> Path | None`; `install(key: str, client: httpx.Client | None = None) -> Path`; `start(key: str) -> dict`; `status() -> dict`; `reset() -> None`; eccezioni `NoBuildForPlatform`, `DoesNotRun`, `AlreadyRunning`, `UnknownComponent`. Lo stato ha la forma `{"key": str|None, "status": "idle"|"running"|"done"|"error", "log": list[str], "detail": str|None}` — **identica** a quella di `component_installer` di oggi, così il frontend non cambia forma.

- [ ] **Step 1: Scrivere il test che fallisce**

Creare `backend/tests/test_binary_install.py`:

```python
"""L'installazione riesce solo se il binario parte: download, hash ed
estrazione riusciti non bastano — un file può ancora non eseguire per firma
o architettura sbagliata."""
import hashlib
import io
import tarfile
from pathlib import Path

import httpx
import pytest

from app.services import binary_installer as bi
from app.services import binary_manifest as bm
from app.services import system_probe as sp
from app.services.binary_manifest import Download


def _archivio(contenuto: bytes = b"#!/bin/sh\necho ok\n") -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as t:
        info = tarfile.TarInfo("fpcalc")
        info.size = len(contenuto)
        info.mode = 0o755
        t.addfile(info, io.BytesIO(contenuto))
    return buf.getvalue()


@pytest.fixture(autouse=True)
def _pulisci():
    bi.reset()
    yield
    bi.reset()


@pytest.fixture
def bin_dir(tmp_path, monkeypatch):
    monkeypatch.setenv(sp.BIN_DIR_ENV, str(tmp_path))
    return tmp_path


def _manifest(monkeypatch, sha: str):
    d = Download("1.0", "https://esempio.invalid/a.tar.gz", sha,
                 "tar.gz", "fpcalc", "single")
    monkeypatch.setattr(bm, "MANIFEST", {"fpcalc": {"test": d}})
    monkeypatch.setattr(bm, "platform_tag", lambda: "test")
    return d


def test_installazione_riuscita(bin_dir, monkeypatch):
    dati = _archivio()
    _manifest(monkeypatch, hashlib.sha256(dati).hexdigest())
    monkeypatch.setattr(bi, "_prova_esecuzione", lambda percorso: "fpcalc 1.0")
    with httpx.Client(transport=httpx.MockTransport(
            lambda req: httpx.Response(200, content=dati))) as c:
        percorso = bi.install("fpcalc", client=c)
    assert percorso == bin_dir / "fpcalc"
    assert percorso.is_file()


def test_il_binario_installato_e_eseguibile(bin_dir, monkeypatch):
    dati = _archivio()
    _manifest(monkeypatch, hashlib.sha256(dati).hexdigest())
    monkeypatch.setattr(bi, "_prova_esecuzione", lambda percorso: "ok")
    with httpx.Client(transport=httpx.MockTransport(
            lambda req: httpx.Response(200, content=dati))) as c:
        percorso = bi.install("fpcalc", client=c)
    assert percorso.stat().st_mode & 0o111, "manca il bit di esecuzione"


def test_hash_sbagliato_non_lascia_niente_nella_cartella(bin_dir, monkeypatch):
    """L'invariante che conta: la cartella gestita non deve MAI contenere
    qualcosa che non ha superato tutti i controlli."""
    dati = _archivio()
    _manifest(monkeypatch, "0" * 64)
    with httpx.Client(transport=httpx.MockTransport(
            lambda req: httpx.Response(200, content=dati))) as c:
        with pytest.raises(bi.ChecksumMismatch):
            bi.install("fpcalc", client=c)
    assert list(bin_dir.iterdir()) == []


def test_binario_che_non_parte_fa_fallire_l_installazione(bin_dir, monkeypatch):
    """È la lezione della prova su fpcalc: scaricato, integro ed estratto può
    ancora non eseguire (firma assente, architettura sbagliata)."""
    dati = _archivio()
    _manifest(monkeypatch, hashlib.sha256(dati).hexdigest())

    def non_parte(percorso):
        raise bi.DoesNotRun("Bad CPU type in executable")

    monkeypatch.setattr(bi, "_prova_esecuzione", non_parte)
    with httpx.Client(transport=httpx.MockTransport(
            lambda req: httpx.Response(200, content=dati))) as c:
        with pytest.raises(bi.DoesNotRun):
            bi.install("fpcalc", client=c)
    assert list(bin_dir.iterdir()) == []


def test_piattaforma_senza_build_non_tocca_la_rete(bin_dir, monkeypatch):
    monkeypatch.setattr(bm, "MANIFEST", {"ffmpeg": {}})
    monkeypatch.setattr(bm, "platform_tag", lambda: "darwin-arm64")

    def esplodi(req):
        raise AssertionError("non doveva scaricare niente")

    with httpx.Client(transport=httpx.MockTransport(esplodi)) as c:
        with pytest.raises(bi.NoBuildForPlatform):
            bi.install("ffmpeg", client=c)


def test_componente_sconosciuto():
    with pytest.raises(bi.UnknownComponent):
        bi.install("pippo")


def test_un_job_alla_volta(bin_dir, monkeypatch):
    monkeypatch.setattr(bi, "spawn", lambda fn: None)  # resta "running"
    _manifest(monkeypatch, "0" * 64)
    bi.start("fpcalc")
    with pytest.raises(bi.AlreadyRunning):
        bi.start("fpcalc")


def test_il_job_riporta_l_errore_invece_di_restare_appeso(bin_dir, monkeypatch):
    """Se il thread muore senza spostare lo stato, ogni richiesta successiva
    riceve 409 finché non si riavvia il backend."""
    _manifest(monkeypatch, "0" * 64)
    monkeypatch.setattr(bi, "spawn", lambda fn: fn())
    # `**kw` e non `client=None`: `start()` chiama `install(key, on_log=…)`,
    # e una firma piu' stretta farebbe fallire il test per il motivo sbagliato.
    monkeypatch.setattr(bi, "install",
                        lambda key, **kw: (_ for _ in ()).throw(RuntimeError("boom")))
    bi.start("fpcalc")
    assert bi.status()["status"] == "error"
    assert "boom" in bi.status()["detail"]


def test_installed_path_conosce_il_layout(bin_dir, monkeypatch):
    d = Download("1.0", "https://esempio.invalid/a.zip", "0" * 64,
                 "zip", "slskd", "bundle")
    monkeypatch.setattr(bm, "MANIFEST", {"slskd": {"test": d}})
    monkeypatch.setattr(bm, "platform_tag", lambda: "test")
    (bin_dir / "slskd").mkdir()
    (bin_dir / "slskd" / "slskd").write_text("")
    assert bi.installed_path("slskd") == bin_dir / "slskd" / "slskd"
```

- [ ] **Step 2: Eseguire e verificare il fallimento**

```bash
cd backend && /Users/lucadenegri/Develop/DJProject01/backend/.venv/bin/python -m pytest tests/test_binary_install.py -q
```
Atteso: FAIL — `install`, `start`, `installed_path` non esistono.

- [ ] **Step 3: Implementare**

Aggiungere in `backend/app/services/binary_installer.py`:

```python
import os
import stat
import subprocess
import tempfile
import threading

from app.services import binary_manifest, system_probe
from app.services.job_spawn import spawn

MAX_LOG_LINES = 500
_PROVA_TIMEOUT_S = 20.0


class UnknownComponent(InstallError):
    pass


class NoBuildForPlatform(InstallError):
    """Non abbiamo una build per questa piattaforma. Non è un errore da
    nascondere: la UI mostra il comando manuale."""


class DoesNotRun(InstallError):
    """Installato ma non eseguibile: firma o architettura."""


class AlreadyRunning(InstallError):
    pass


def _prova_esecuzione(percorso: Path) -> str:
    """Esegue il binario appena installato. È il vero criterio di riuscita:
    download, hash ed estrazione possono essere andati e il file può ancora
    non partire."""
    try:
        proc = subprocess.run([str(percorso), "-version"], capture_output=True,
                              text=True, timeout=_PROVA_TIMEOUT_S, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        raise DoesNotRun(str(exc)) from exc
    if proc.returncode != 0:
        raise DoesNotRun((proc.stderr or proc.stdout or "").strip()[:200]
                         or f"uscito con {proc.returncode}")
    return (proc.stdout or proc.stderr or "").strip().splitlines()[0][:120]


def installed_path(key: str) -> Path | None:
    """Dove sta l'eseguibile di questo componente nella cartella gestita, se
    c'è. Conosce il layout: i bundle stanno in una sottocartella loro."""
    d = binary_manifest.entry_for(key)
    if d is None:
        return None
    base = system_probe.managed_bin_dir()
    percorso = (base / key / d.member) if d.layout == "bundle" else (base / d.member)
    return percorso if percorso.is_file() else None


def install(key: str, client: httpx.Client | None = None,
            on_log: Callable[[str], None] | None = None) -> Path:
    """Scarica, verifica, estrae, prova e infine installa. Tutto avviene in
    una directory temporanea: nella cartella gestita si sposta solo alla fine."""
    if key not in binary_manifest.MANIFEST:
        raise UnknownComponent(key)
    d = binary_manifest.entry_for(key)
    if d is None:
        raise NoBuildForPlatform(f"{key}: nessuna build per {binary_manifest.platform_tag()}")

    def log_riga(msg: str) -> None:
        if on_log:
            on_log(msg)

    destinazione = system_probe.ensure_bin_dir()  # qui si scrive: va creata
    with tempfile.TemporaryDirectory(prefix="cratory-install-") as tmp:
        tmpdir = Path(tmp)
        archivio = tmpdir / "archivio"
        log_riga(f"scarico {d.url}")
        download_verified(
            d, archivio, client=client,
            on_progress=lambda fatto, totale: log_riga(
                f"scaricati {fatto // 1024} / {totale // 1024} KB"),
        )
        log_riga(f"hash verificato ({d.sha256[:12]}…)")

        lavoro = tmpdir / "estratto"
        lavoro.mkdir()
        exe = extract(archivio, d, lavoro)
        log_riga("estratto")

        exe.chmod(exe.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        versione = _prova_esecuzione(exe)
        log_riga(f"il binario parte: {versione}")

        finale = (destinazione / key) if d.layout == "bundle" else (destinazione / d.member)
        if d.layout == "bundle":
            if finale.exists():
                shutil.rmtree(finale)
            shutil.move(str(exe.parent), str(finale))
            finale = finale / d.member
        else:
            shutil.move(str(exe), str(finale))
        log_riga(f"installato in {finale}")

    system_probe.invalidate_cache()
    return finale


_lock = threading.Lock()
_state: dict = {"key": None, "status": "idle", "log": [], "detail": None}


def reset() -> None:
    with _lock:
        _state.update({"key": None, "status": "idle", "log": [], "detail": None})


def status() -> dict:
    with _lock:
        return {**_state, "log": list(_state["log"])}


def _append(line: str) -> None:
    with _lock:
        _state["log"].append(line)
        if len(_state["log"]) > MAX_LOG_LINES:
            del _state["log"][0:len(_state["log"]) - MAX_LOG_LINES]


def start(key: str) -> dict:
    """Avvia l'installazione in background. Un job alla volta."""
    if key not in binary_manifest.MANIFEST:
        raise UnknownComponent(key)
    with _lock:
        if _state["status"] == "running":
            raise AlreadyRunning(_state["key"])
        _state.update({"key": key, "status": "running", "log": [], "detail": None})

    def run() -> None:
        try:
            install(key, on_log=_append)
            with _lock:
                _state.update({"status": "done", "detail": None})
        except Exception as exc:  # noqa: BLE001 - ampio di proposito
            # Qualunque eccezione non gestita qui morirebbe in questo thread
            # lasciando lo stato su "running": ogni richiesta successiva
            # riceverebbe 409 fino al riavvio del backend.
            log.warning("installazione di %s fallita: %s", key, exc)
            with _lock:
                _state.update({"status": "error", "detail": str(exc)})

    spawn(run)
    return status()
```

- [ ] **Step 4: Eseguire i test**

```bash
cd backend && /Users/lucadenegri/Develop/DJProject01/backend/.venv/bin/python -m pytest tests/test_binary_install.py -q
```
Atteso: `9 passed`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/binary_installer.py backend/tests/test_binary_install.py
git commit -m "feat(setup): installazione atomica, valida solo se il binario parte"
```

---

## Task 6: Il registry passa a tre binari

**Files:**
- Modify: `backend/app/services/system_probe.py`, `backend/app/routers/setup.py`
- Delete: `backend/app/services/component_installer.py`, `backend/tests/test_component_installer.py`
- Test: `backend/tests/test_system_probe.py`, `backend/tests/test_setup_install_router.py` (nuovo)

**Interfaces:**
- Consumes: `binary_installer.start/status`, `binary_manifest.entry_for`.
- Produces: il payload del probe guadagna `installable: bool` (esiste una voce nel manifesto per questa piattaforma) e perde nulla. `auto_installable` resta e significa "l'app sa installarlo": per i tre binari è `True` se e solo se `installable`.

- [ ] **Step 1: Scrivere i test che falliscono**

Sostituire in `backend/tests/test_system_probe.py` i test del rilevamento per import (`test_modulo_python_assente_non_risulta_presente`, `test_modulo_python_presente_risulta_presente`, `test_yt_dlp_rilevato_per_import_non_per_binario`, `test_dispatch_non_dipende_dalla_chiave`, e la funzione `_finto`) con:

```python
def test_il_registry_contiene_solo_i_tre_binari_esterni():
    """yt-dlp ed essentia sono in requirements.txt: li installa pip, non il
    wizard. Tenerli qui significava mostrare due righe già a posto e dare
    all'installer un lavoro che non è suo."""
    assert [c.key for c in sp.REGISTRY] == ["ffmpeg", "fpcalc", "slskd"]


def test_il_probe_dice_se_sappiamo_installarlo(monkeypatch):
    """Su macOS ffmpeg non ha una build nel manifesto: la UI deve poterlo
    sapere per non offrire un bottone che non può funzionare."""
    monkeypatch.setattr(sp.shutil, "which", lambda name: None)
    monkeypatch.setattr(sp.binary_manifest, "platform_tag", lambda: "darwin-arm64")
    per_chiave = {r["key"]: r for r in sp.probe_all(force=True)}
    assert per_chiave["fpcalc"]["installable"] is True
    assert per_chiave["ffmpeg"]["installable"] is False


def test_su_linux_ffmpeg_e_installabile(monkeypatch):
    monkeypatch.setattr(sp.shutil, "which", lambda name: None)
    monkeypatch.setattr(sp.binary_manifest, "platform_tag", lambda: "linux-x86_64")
    per_chiave = {r["key"]: r for r in sp.probe_all(force=True)}
    assert per_chiave["ffmpeg"]["installable"] is True
```

Creare `backend/tests/test_setup_install_router.py`:

```python
"""Gli endpoint di installazione ora guidano il download dei binari."""
import pytest
from fastapi.testclient import TestClient

from app.db import get_db
from app.main import app
from app.services import binary_installer as bi


@pytest.fixture(autouse=True)
def _pulisci():
    bi.reset()
    yield
    bi.reset()


def _client(db):
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app)


def test_chiave_sconosciuta(db):
    assert _client(db).post("/api/setup/install/rm-rf").status_code == 400
    app.dependency_overrides.clear()


def test_piattaforma_senza_build(db, monkeypatch):
    monkeypatch.setattr(bi.binary_manifest, "platform_tag", lambda: "darwin-arm64")
    monkeypatch.setattr(bi, "spawn", lambda fn: fn())
    res = _client(db).post("/api/setup/install/ffmpeg")
    assert res.status_code == 202
    assert bi.status()["status"] == "error"
    app.dependency_overrides.clear()


def test_stato_esposto(db):
    body = _client(db).get("/api/setup/install/status").json()
    assert body["status"] == "idle"
    app.dependency_overrides.clear()
```

- [ ] **Step 2: Eseguire e verificare il fallimento**

```bash
cd backend && /Users/lucadenegri/Develop/DJProject01/backend/.venv/bin/python -m pytest tests/test_system_probe.py tests/test_setup_install_router.py -q
```
Atteso: FAIL (il registry ha ancora cinque voci, `installable` non esiste).

- [ ] **Step 3: Ridurre il registry**

In `backend/app/services/system_probe.py`:

1. Rimuovere dal `REGISTRY` le voci `yt-dlp` ed `essentia`.
2. Rimuovere dal dataclass `Component` il campo `python_module`, e cancellare `_VERSION_SNIPPET`, `_import_version`, `_probe_python_module`.
3. In `_probe_one`, il dispatch torna a due rami e guadagna `installable`:

```python
def _probe_one(c: Component) -> dict:
    if c.kind == "daemon":
        detected = _probe_slskd()
    else:
        detected = _probe_binary(c)
    installabile = binary_manifest.entry_for(c.key) is not None
    return {
        "key": c.key, "kind": c.kind, "severity": c.severity,
        "unlocks": list(c.unlocks),
        # `auto_installable` ora significa "l'app sa installarlo da sola", e
        # per un binario esterno questo dipende solo dall'avere una build per
        # questa piattaforma: niente build, niente bottone.
        "auto_installable": installabile,
        "installable": installabile,
        "install_command": recipe_for(c), "docs": c.docs, **detected,
    }
```

4. Rimuovere dal dataclass il campo `auto_installable` (ora è derivato) e le sue occorrenze nel registry.

4-bis. **Dire quando stiamo scavalcando una copia di sistema.** La spec (§1)
lascia aperto un caso: se l'utente installa ffmpeg con brew **dopo** che ne
abbiamo scaricato uno nostro, il nostro continua a vincere e può essere più
vecchio, senza che niente lo dica. Il probe deve segnalarlo. In `_probe_binary`,
quando il binario risolto viene dalla cartella gestita, si guarda anche se il
`PATH` ne ha un altro:

```python
def _probe_binary(c: Component) -> dict:
    path = resolve_binary(c.binary or c.key, c.env_override)
    if not path:
        return {"present": False, "version": None, "source": None,
                "shadowing": None}
    gestita = managed_bin_dir()
    nostro = Path(path).parent == gestita
    # Se stiamo usando la nostra copia ma il sistema ne ha un'altra, la UI deve
    # poterlo dire: altrimenti l'utente installa ffmpeg con brew, non vede
    # cambiare niente e non ha modo di capire perché.
    di_sistema = shutil.which(c.binary or c.key) if nostro else None
    return {"present": True, "version": _run_version([path, c.version_flag]),
            "source": "bundle" if nostro else "path",
            "shadowing": di_sistema}
```

e `shadowing: str | None` entra nel payload di `_probe_one`. Il test:

```python
def test_dice_se_stiamo_scavalcando_una_copia_di_sistema(tmp_path, monkeypatch):
    """L'utente installa ffmpeg con brew dopo di noi: il nostro continua a
    vincere. Silenzio qui significa un utente che non capisce perché la sua
    installazione non ha effetto."""
    monkeypatch.setenv(sp.BIN_DIR_ENV, str(tmp_path))
    (tmp_path / "ffmpeg").write_text("")
    monkeypatch.setattr(sp.shutil, "which", lambda name: "/opt/homebrew/bin/ffmpeg")
    monkeypatch.setattr(sp, "_run_version", lambda argv: "ffmpeg 1.0")
    esito = sp._probe_binary(sp.get("ffmpeg"))
    assert esito["source"] == "bundle"
    assert esito["shadowing"] == "/opt/homebrew/bin/ffmpeg"


def test_niente_da_segnalare_se_usiamo_quella_di_sistema(monkeypatch):
    monkeypatch.delenv(sp.BIN_DIR_ENV, raising=False)
    monkeypatch.setattr(sp.shutil, "which", lambda name: "/opt/homebrew/bin/ffmpeg")
    monkeypatch.setattr(sp, "_run_version", lambda argv: "ffmpeg 1.0")
    assert sp._probe_binary(sp.get("ffmpeg"))["shadowing"] is None
```

Nel frontend (Task 11) il tipo `ProbeComponent` guadagna `shadowing: string | null`
e la riga, quando è valorizzato, mostra sotto lo stato:
`t.setup.shadowingSystem(shadowing)` — chiave nuova da aggiungere in entrambe le
lingue nel Task 10:

```ts
    // en.ts
    shadowingSystem: (path: string) => `Using our copy; a system one exists at ${path}`,
    // it.ts
    shadowingSystem: (path: string) => `Stiamo usando la nostra copia; ce n'è una di sistema in ${path}`,
```
5. Aggiungere `from app.services import binary_manifest` agli import.
6. `resolve_binary` perde il parametro `venv` e il ramo dell'interprete: serviva solo a `yt-dlp`. Rimuovere anche il passaggio `venv=True` dai chiamanti (cercarli con `rg "venv=True" backend/app`).

- [ ] **Step 4: Spostare il router sul nuovo installer**

In `backend/app/routers/setup.py` sostituire `component_installer` con `binary_installer`:

```python
from app.services import binary_installer


@router.post("/install/{key}", status_code=202)
def install(key: str) -> dict:
    try:
        return binary_installer.start(key)
    except binary_installer.UnknownComponent as exc:
        raise api_error(400, "unknown_component", f"componente sconosciuto: {key}",
                        component=key) from exc
    except binary_installer.AlreadyRunning as exc:
        raise api_error(409, "install_already_running",
                        "un'installazione è già in corso") from exc


@router.get("/install/status")
def install_status() -> dict:
    return binary_installer.status()
```

Il caso "nessuna build per questa piattaforma" **non** è un `400`: il job parte e finisce in `error` con il dettaglio, così il frontend lo mostra nello stesso posto degli altri fallimenti, insieme al comando manuale.

- [ ] **Step 5: Cancellare il codice morto**

```bash
git rm backend/app/services/component_installer.py backend/tests/test_component_installer.py
```

Verificare che non resti nessun riferimento:

```bash
rg -n "component_installer" backend/ frontend/
```
Atteso: nessun risultato.

- [ ] **Step 5-bis: Togliere le chiavi i18n rimaste orfane**

Con yt-dlp ed essentia fuori dal registry, nessun componente dichiara più
`soundcloud_import` né `analysis_bpm_key` fra gli `unlocks`, e restano lì le
loro descrizioni. Sono **quattro chiavi in due lingue**: testo che non
raggiunge più nessuno schermo e che confonderà il prossimo che legge il
dizionario.

In `frontend/lib/i18n/en.ts` e `frontend/lib/i18n/it.ts`, dentro `setup`,
rimuovere:

- da `components`: le voci `"yt-dlp"` ed `essentia`;
- da `unlocks`: le voci `soundcloud_import` e `analysis_bpm_key`.

**Non** toccare le altre voci di `unlocks`: `audio_hash`, `shazam`,
`soundcloud_download`, `acoustid_fingerprint`, `soulseek_download` e
`library_share` sono tutte ancora dichiarate dai tre binari superstiti.

Poi il test che tiene allineati dizionario e registry — creare
`frontend/tests/setup-dictionary.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { it as dizionarioIt } from "@/lib/i18n/it";
import { en } from "@/lib/i18n/en";

/* Il dizionario e il registry del probe vivono ai due lati di un confine HTTP:
   niente li tiene allineati da solo. Questo test becca il caso che si verifica
   davvero — un componente tolto dal backend che lascia il suo testo qui — e
   non l'inverso: una chiave mancante degrada già da sola, perché la UI ripiega
   sul nome del componente (`?? c.key`). */
const COMPONENTI_VIVI = ["ffmpeg", "fpcalc", "slskd"];
const UNLOCKS_VIVI = [
  "audio_hash", "shazam", "soundcloud_download",
  "acoustid_fingerprint", "soulseek_download", "library_share",
];

describe("dizionario del wizard", () => {
  for (const [nome, d] of [["it", dizionarioIt], ["en", en]] as const) {
    it(`${nome}: nessuna descrizione di componenti che non esistono più`, () => {
      expect(Object.keys(d.setup.components).sort()).toEqual([...COMPONENTI_VIVI].sort());
    });

    it(`${nome}: nessuna voce unlocks orfana`, () => {
      expect(Object.keys(d.setup.unlocks).sort()).toEqual([...UNLOCKS_VIVI].sort());
    });
  }
});
```

Eseguirlo e verificare che passi **solo dopo** aver rimosso le quattro chiavi:

```bash
cd frontend && npm run test:unit -- tests/setup-dictionary.test.ts
```

Provare che non sia vacuo: rimettere `essentia` in `components` di `it.ts`,
rieseguire, verificare che il test cada, poi toglierla di nuovo.

- [ ] **Step 6: Eseguire l'intera suite backend**

```bash
cd backend && /Users/lucadenegri/Develop/DJProject01/backend/.venv/bin/python -m pytest tests -q
```
Atteso: tutto verde. I test che citavano `yt-dlp`/`essentia` nel registry vanno aggiornati, non cancellati, se verificano altro.

- [ ] **Step 7: Commit**

```bash
git add -A backend frontend/lib/i18n frontend/tests/setup-dictionary.test.ts
git commit -m "feat(setup): il registry passa ai tre binari esterni, via le ricette pip"
```

---

## Task 7: Scrivere il `slskd.yml` senza distruggerlo

**Files:**
- Create: `backend/app/services/slskd_daemon.py`
- Test: `backend/tests/test_slskd_config.py`

**Interfaces:**
- Produces: `write_config(config_path: Path, *, username: str, password: str, port: int, download_dir: str) -> None`; `read_username(config_path: Path) -> str | None`; `default_config_path() -> Path`.

- [ ] **Step 1: Scrivere il test che fallisce**

Creare `backend/tests/test_slskd_config.py`:

```python
"""Il file di configurazione è dell'utente, non nostro: scriverci dentro non
deve fargli perdere niente."""
from pathlib import Path

from ruamel.yaml import YAML

from app.services import slskd_daemon as sd

ESISTENTE = """\
# La mia configurazione, scritta a mano
soulseek:
  username: vecchio
  password: vecchia
  description: "Ciao dal mio slskd"
shares:
  directories:
    - /Users/io/Musica
web:
  port: 5030
  authentication:
    api_keys:
      cratory:
        key: abc123
"""


def _carica(p: Path) -> dict:
    return YAML().load(p.read_text())


def test_le_chiavi_non_nostre_sopravvivono(tmp_path):
    """L'invariante che protegge la configurazione dell'utente: si verifica
    sul contenuto integrale, non sulle quattro chiavi che tocchiamo."""
    cfg = tmp_path / "slskd.yml"
    cfg.write_text(ESISTENTE)
    sd.write_config(cfg, username="nuovo", password="nuova",
                    port=5030, download_dir="/tmp/dl")
    data = _carica(cfg)
    assert data["soulseek"]["description"] == "Ciao dal mio slskd"
    assert data["shares"]["directories"] == ["/Users/io/Musica"]
    assert data["web"]["authentication"]["api_keys"]["cratory"]["key"] == "abc123"


def test_le_chiavi_nostre_vengono_aggiornate(tmp_path):
    cfg = tmp_path / "slskd.yml"
    cfg.write_text(ESISTENTE)
    sd.write_config(cfg, username="nuovo", password="nuova",
                    port=5031, download_dir="/tmp/dl")
    data = _carica(cfg)
    assert data["soulseek"]["username"] == "nuovo"
    assert data["soulseek"]["password"] == "nuova"
    assert data["web"]["port"] == 5031
    assert data["directories"]["downloads"] == "/tmp/dl"


def test_i_commenti_sopravvivono(tmp_path):
    """ruamel in round-trip li preserva: se qualcuno passasse a PyYAML,
    l'utente perderebbe i propri commenti senza accorgersene."""
    cfg = tmp_path / "slskd.yml"
    cfg.write_text(ESISTENTE)
    sd.write_config(cfg, username="n", password="p", port=5030, download_dir="/tmp/dl")
    assert "# La mia configurazione, scritta a mano" in cfg.read_text()


def test_config_assente_viene_creata(tmp_path):
    cfg = tmp_path / "nuova" / "slskd.yml"
    sd.write_config(cfg, username="io", password="segreta",
                    port=5030, download_dir="/tmp/dl")
    data = _carica(cfg)
    assert data["soulseek"]["username"] == "io"


def test_il_file_non_e_leggibile_da_altri(tmp_path):
    """Contiene la password Soulseek in chiaro: è così che funziona slskd,
    ma i permessi devono almeno rifletterlo."""
    import stat as st
    cfg = tmp_path / "slskd.yml"
    sd.write_config(cfg, username="io", password="segreta",
                    port=5030, download_dir="/tmp/dl")
    assert st.S_IMODE(cfg.stat().st_mode) == 0o600


def test_il_backup_conserva_l_originale(tmp_path):
    cfg = tmp_path / "slskd.yml"
    cfg.write_text(ESISTENTE)
    sd.write_config(cfg, username="n", password="p", port=5030, download_dir="/tmp/dl")
    assert cfg.with_suffix(".yml.bak").read_text() == ESISTENTE


def test_rilettura_dell_username(tmp_path):
    cfg = tmp_path / "slskd.yml"
    cfg.write_text(ESISTENTE)
    assert sd.read_username(cfg) == "vecchio"


def test_rilettura_su_file_assente(tmp_path):
    assert sd.read_username(tmp_path / "manca.yml") is None
```

- [ ] **Step 2: Eseguire e verificare il fallimento**

```bash
cd backend && /Users/lucadenegri/Develop/DJProject01/backend/.venv/bin/python -m pytest tests/test_slskd_config.py -q
```
Atteso: `ModuleNotFoundError: No module named 'app.services.slskd_daemon'`.

- [ ] **Step 3: Implementare**

Creare `backend/app/services/slskd_daemon.py`. Il modello di scrittura è `services/slskd_shares.py:34` (`edit_shares_yaml`): round-trip, backup, scrittura atomica, permessi preservati.

```python
"""Configurazione, avvio, arresto e stato del demone slskd.

Deroga consapevole al confine "slskd è un servizio esterno raggiunto via
HTTP": qui Cratory lo configura e lo avvia. Due regole tengono la deroga
sotto controllo — non si distrugge la configurazione dell'utente, e non si
ferma mai un processo che non abbiamo avviato noi.
"""
from __future__ import annotations

import io
import logging
import os
import stat
from pathlib import Path

from ruamel.yaml import YAML

from app.core import runtime_settings
from app.core.config import BACKEND_DIR

log = logging.getLogger(__name__)

DEFAULT_PORT = 5030


class DaemonError(Exception):
    pass


def _yaml() -> YAML:
    yaml = YAML()  # round-trip: preserva commenti e formato
    yaml.preserve_quotes = True
    return yaml


def default_config_path() -> Path:
    """Il percorso configurato, se c'è; altrimenti quello nostro sotto data/."""
    configurato = runtime_settings.slskd_config_path()
    return Path(configurato) if configurato else BACKEND_DIR / "data" / "slskd.yml"


def read_username(config_path: Path | str) -> str | None:
    """L'username non è un segreto come la password: si può rileggere e
    mostrare, così l'utente vede con quale account è configurato."""
    config_path = Path(config_path)
    if not config_path.is_file():
        return None
    try:
        data = _yaml().load(config_path.read_text()) or {}
    except Exception as exc:  # noqa: BLE001 - un yaml rotto non deve dare 500
        log.warning("slskd.yml illeggibile: %s", exc)
        return None
    return (data.get("soulseek") or {}).get("username")


def write_config(config_path: Path | str, *, username: str, password: str,
                 port: int, download_dir: str) -> None:
    """Scrive SOLO le quattro chiavi che ci servono. Il resto del file resta
    intatto: è dell'utente, e può contenere share, api key e commenti suoi."""
    config_path = Path(config_path)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    yaml = _yaml()

    if config_path.is_file():
        originale = config_path.read_text()
        data = yaml.load(originale) or {}
        modo = stat.S_IMODE(os.stat(config_path).st_mode)
        config_path.with_suffix(config_path.suffix + ".bak").write_text(originale)
    else:
        data = {}
        modo = 0o600  # il file contiene la password Soulseek in chiaro

    data.setdefault("soulseek", {})
    data["soulseek"]["username"] = username
    data["soulseek"]["password"] = password
    data.setdefault("web", {})
    data["web"]["port"] = port
    data.setdefault("directories", {})
    data["directories"]["downloads"] = download_dir

    buf = io.StringIO()
    yaml.dump(data, buf)
    tmp = config_path.with_suffix(config_path.suffix + ".tmp")
    tmp.write_text(buf.getvalue())
    os.chmod(tmp, modo)
    os.replace(tmp, config_path)
```

Se `BACKEND_DIR` non è esportato da `app.core.config` con quel nome, usare quello reale.

- [ ] **Step 4: Eseguire i test**

```bash
cd backend && /Users/lucadenegri/Develop/DJProject01/backend/.venv/bin/python -m pytest tests/test_slskd_config.py -q
```
Atteso: `8 passed`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/slskd_daemon.py backend/tests/test_slskd_config.py
git commit -m "feat(slskd): scrittura della configurazione senza distruggere quella esistente"
```

---

## Task 8: Avvio, arresto e stato del demone

**Files:**
- Modify: `backend/app/services/slskd_daemon.py`
- Test: `backend/tests/test_slskd_daemon.py`

**Interfaces:**
- Produces: `pid_file() -> Path`; `is_reachable(client: httpx.Client | None = None) -> bool`; `owned_pid() -> int | None`; `start(client: httpx.Client | None = None) -> dict`; `stop() -> dict`; `daemon_status(client: httpx.Client | None = None) -> dict` con forma `{"reachable": bool, "owned": bool, "pid": int | None}`; eccezioni `NotInstalled`, `AlreadyUp`, `NotOurs`, `StartFailed`.

- [ ] **Step 1: Scrivere il test che fallisce**

Creare `backend/tests/test_slskd_daemon.py`:

```python
"""Le due regole della deroga: non si avvia un secondo demone se ce n'è già
uno, e non si ferma mai un processo che non abbiamo avviato noi."""
import httpx
import pytest

from app.services import slskd_daemon as sd


@pytest.fixture(autouse=True)
def _pid_isolato(tmp_path, monkeypatch):
    monkeypatch.setattr(sd, "pid_file", lambda: tmp_path / "slskd.pid")
    return tmp_path


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_gia_in_ascolto_non_avvia_un_secondo_processo(monkeypatch):
    """Il caso normale è che slskd ci sia già, installato dall'utente: non
    dobbiamo scaricarlo né avviarlo, e soprattutto non affiancargliene un altro."""
    monkeypatch.setattr(sd.runtime_settings, "slskd_url", lambda: "http://x:5030")

    def esplodi(argv, **kw):
        raise AssertionError("non doveva lanciare niente")

    monkeypatch.setattr(sd.subprocess, "Popen", esplodi)
    with _client(lambda req: httpx.Response(200)) as c:
        with pytest.raises(sd.AlreadyUp):
            sd.start(client=c)


def test_pid_di_un_processo_inesistente_e_stantio(_pid_isolato, monkeypatch):
    sd.pid_file().write_text("999999")
    monkeypatch.setattr(sd, "_processo_e_slskd", lambda pid: False)
    assert sd.owned_pid() is None
    assert not sd.pid_file().exists(), "il file stantio va rimosso"


def test_pid_riassegnato_a_un_altro_processo_non_e_nostro(_pid_isolato, monkeypatch):
    """Un PID può essere stato riciclato dal sistema: fermarlo alla cieca
    significherebbe uccidere un processo qualsiasi dell'utente."""
    sd.pid_file().write_text("1234")
    monkeypatch.setattr(sd, "_riga_di_comando", lambda pid: "/usr/bin/qualcosaltro")
    assert sd.owned_pid() is None


def test_pid_valido_e_nostro(_pid_isolato, monkeypatch):
    sd.pid_file().write_text("1234")
    monkeypatch.setattr(sd, "_riga_di_comando", lambda pid: "/app/data/bin/slskd/slskd")
    assert sd.owned_pid() == 1234


def test_stop_rifiutato_senza_pid_nostro(_pid_isolato):
    with pytest.raises(sd.NotOurs):
        sd.stop()


def test_stop_termina_solo_il_nostro(_pid_isolato, monkeypatch):
    sd.pid_file().write_text("1234")
    monkeypatch.setattr(sd, "_riga_di_comando", lambda pid: "/app/data/bin/slskd/slskd")
    uccisi = []
    monkeypatch.setattr(sd.os, "kill", lambda pid, sig: uccisi.append((pid, sig)))
    monkeypatch.setattr(sd, "_processo_vivo", lambda pid: False)  # muore subito
    sd.stop()
    assert uccisi[0][0] == 1234
    assert not sd.pid_file().exists()


def test_avvio_senza_binario_installato(monkeypatch):
    monkeypatch.setattr(sd.runtime_settings, "slskd_url", lambda: "")
    monkeypatch.setattr(sd.binary_installer, "installed_path", lambda key: None)
    with pytest.raises(sd.NotInstalled):
        sd.start()


def test_avvio_che_non_risponde_e_un_fallimento(tmp_path, monkeypatch):
    """Non ci si fida dello spawn: se /health non risponde mai, l'avvio è
    fallito e va mostrata la coda del log, dove si legge la porta occupata."""
    monkeypatch.setattr(sd.runtime_settings, "slskd_url", lambda: "http://x:5030")
    monkeypatch.setattr(sd.binary_installer, "installed_path",
                        lambda key: tmp_path / "slskd")
    monkeypatch.setattr(sd, "_ATTESA_AVVIO_S", 0.05)
    monkeypatch.setattr(sd, "_INTERVALLO_S", 0.01)

    class FintoProc:
        pid = 4321

        def poll(self):
            return None

    monkeypatch.setattr(sd.subprocess, "Popen", lambda *a, **kw: FintoProc())
    with _client(lambda req: httpx.Response(503)) as c:
        with pytest.raises(sd.StartFailed):
            sd.start(client=c)


def test_stato_riporta_raggiungibile_e_proprieta(_pid_isolato, monkeypatch):
    monkeypatch.setattr(sd.runtime_settings, "slskd_url", lambda: "http://x:5030")
    with _client(lambda req: httpx.Response(200)) as c:
        stato = sd.daemon_status(client=c)
    assert stato == {"reachable": True, "owned": False, "pid": None}
```

- [ ] **Step 2: Eseguire e verificare il fallimento**

```bash
cd backend && /Users/lucadenegri/Develop/DJProject01/backend/.venv/bin/python -m pytest tests/test_slskd_daemon.py -q
```
Atteso: FAIL — `pid_file`, `start`, `stop` non esistono.

- [ ] **Step 3: Implementare**

Aggiungere in `backend/app/services/slskd_daemon.py`:

```python
import signal
import subprocess
import time

import httpx

from app.services import binary_installer

_ATTESA_AVVIO_S = 20.0
_INTERVALLO_S = 0.5
_TIMEOUT_HTTP_S = 3.0


class NotInstalled(DaemonError):
    pass


class AlreadyUp(DaemonError):
    """Qualcosa risponde già all'URL: non ne avviamo un secondo."""


class NotOurs(DaemonError):
    """Non abbiamo un PID nostro valido: non fermiamo processi altrui."""


class StartFailed(DaemonError):
    pass


def pid_file() -> Path:
    return BACKEND_DIR / "data" / "slskd.pid"


def log_file() -> Path:
    return BACKEND_DIR / "data" / "slskd.log"


def is_reachable(client: httpx.Client | None = None) -> bool:
    url = runtime_settings.slskd_url()
    if not url:
        return False
    owned = client is None
    client = client or httpx.Client()
    try:
        res = client.get(f"{url.rstrip('/')}/health", timeout=_TIMEOUT_HTTP_S)
        return res.status_code < 500
    except httpx.HTTPError:
        return False
    finally:
        if owned:
            client.close()


def _riga_di_comando(pid: int) -> str:
    """La riga di comando del processo, o stringa vuota. Serve a distinguere
    'il nostro slskd' da 'un processo qualsiasi che ha ereditato quel PID'."""
    try:
        proc = subprocess.run(["ps", "-p", str(pid), "-o", "command="],
                              capture_output=True, text=True, timeout=5, check=False)
    except (OSError, subprocess.SubprocessError):
        return ""
    return proc.stdout.strip()


def _processo_e_slskd(pid: int) -> bool:
    return "slskd" in _riga_di_comando(pid)


def _processo_vivo(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def owned_pid() -> int | None:
    """Il PID del demone che abbiamo avviato noi, se esiste ed è ancora lui.

    Un PID vecchio può essere stato riassegnato dal sistema a tutt'altro:
    prima di considerarlo nostro si controlla che la riga di comando parli
    davvero di slskd. Se non torna, il file è stantio e va via.
    """
    f = pid_file()
    if not f.is_file():
        return None
    try:
        pid = int(f.read_text().strip())
    except ValueError:
        f.unlink(missing_ok=True)
        return None
    if not _processo_e_slskd(pid):
        f.unlink(missing_ok=True)
        return None
    return pid


def daemon_status(client: httpx.Client | None = None) -> dict:
    pid = owned_pid()
    return {"reachable": is_reachable(client), "owned": pid is not None, "pid": pid}


def start(client: httpx.Client | None = None) -> dict:
    """Avvia il demone come processo indipendente, poi verifica che risponda.

    `start_new_session=True`: deve sopravvivere alla chiusura di Cratory,
    altrimenti una coda di download lunga si interromperebbe chiudendo l'app.
    """
    if is_reachable(client):
        raise AlreadyUp("slskd risponde già all'URL configurato")
    exe = binary_installer.installed_path("slskd")
    if exe is None:
        raise NotInstalled("slskd non è installato nella cartella dell'app")

    config = default_config_path()
    with log_file().open("ab") as out:
        proc = subprocess.Popen(
            [str(exe), "--config", str(config)],
            stdout=out, stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    pid_file().write_text(str(proc.pid))

    scadenza = time.monotonic() + _ATTESA_AVVIO_S
    while time.monotonic() < scadenza:
        if is_reachable(client):
            return daemon_status(client)
        if proc.poll() is not None:
            break
        time.sleep(_INTERVALLO_S)

    pid_file().unlink(missing_ok=True)
    coda = ""
    if log_file().is_file():
        coda = "\n".join(log_file().read_text(errors="replace").splitlines()[-15:])
    raise StartFailed(coda or "slskd non ha risposto entro il tempo previsto")


def stop() -> dict:
    """Ferma SOLO il demone che abbiamo avviato noi."""
    pid = owned_pid()
    if pid is None:
        raise NotOurs("nessun demone avviato da Cratory")
    os.kill(pid, signal.SIGTERM)
    scadenza = time.monotonic() + 10
    while time.monotonic() < scadenza and _processo_vivo(pid):
        time.sleep(_INTERVALLO_S)
    if _processo_vivo(pid):
        os.kill(pid, signal.SIGKILL)
    pid_file().unlink(missing_ok=True)
    return {"reachable": False, "owned": False, "pid": None}
```

- [ ] **Step 4: Eseguire i test**

```bash
cd backend && /Users/lucadenegri/Develop/DJProject01/backend/.venv/bin/python -m pytest tests/test_slskd_daemon.py -q
```
Atteso: `9 passed`.

- [ ] **Step 5: Provare che il test sul PID riassegnato non sia vacuo**

Rimuovere temporaneamente il controllo `_processo_e_slskd` da `owned_pid`, rieseguire, verificare che `test_pid_riassegnato_a_un_altro_processo_non_e_nostro` fallisca, ripristinare. Riportare cosa si è osservato.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/slskd_daemon.py backend/tests/test_slskd_daemon.py
git commit -m "feat(slskd): avvio staccato con verifica e arresto solo del processo nostro"
```

---

## Task 9: Endpoint del demone

**Files:**
- Modify: `backend/app/routers/slskd.py`
- Test: `backend/tests/test_slskd_daemon_router.py`

**Interfaces:**
- Produces: `GET /api/slskd/daemon/status` → `{reachable, owned, pid}`; `POST /api/slskd/daemon/start` → stesso corpo, `409` se già acceso, `409` se non installato, `502` se non risponde; `POST /api/slskd/daemon/stop` → stesso corpo, `409` se non è nostro; `PUT /api/slskd/daemon/config` con corpo `{username, password, port, download_dir}` → `{configured: true, username: str}`.

- [ ] **Step 1: Scrivere il test che fallisce**

Creare `backend/tests/test_slskd_daemon_router.py`:

```python
"""Gli endpoint del demone traducono in HTTP le due regole del servizio."""
import pytest
from fastapi.testclient import TestClient

from app.db import get_db
from app.main import app
from app.services import slskd_daemon as sd


def _client(db):
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app)


def test_stato(db, monkeypatch):
    monkeypatch.setattr(sd, "daemon_status",
                        lambda client=None: {"reachable": False, "owned": False, "pid": None})
    assert _client(db).get("/api/slskd/daemon/status").json()["reachable"] is False
    app.dependency_overrides.clear()


def test_start_quando_e_gia_acceso(db, monkeypatch):
    def gia_su(client=None):
        raise sd.AlreadyUp("già acceso")

    monkeypatch.setattr(sd, "start", gia_su)
    assert _client(db).post("/api/slskd/daemon/start").status_code == 409
    app.dependency_overrides.clear()


def test_start_senza_binario(db, monkeypatch):
    def non_installato(client=None):
        raise sd.NotInstalled("manca")

    monkeypatch.setattr(sd, "start", non_installato)
    assert _client(db).post("/api/slskd/daemon/start").status_code == 409
    app.dependency_overrides.clear()


def test_start_che_non_risponde(db, monkeypatch):
    def fallisce(client=None):
        raise sd.StartFailed("porta occupata")

    monkeypatch.setattr(sd, "start", fallisce)
    res = _client(db).post("/api/slskd/daemon/start")
    assert res.status_code == 502
    assert "porta occupata" in res.text
    app.dependency_overrides.clear()


def test_stop_di_un_demone_non_nostro(db, monkeypatch):
    def non_nostro():
        raise sd.NotOurs("non nostro")

    monkeypatch.setattr(sd, "stop", non_nostro)
    assert _client(db).post("/api/slskd/daemon/stop").status_code == 409
    app.dependency_overrides.clear()


def test_la_password_non_torna_indietro(db, monkeypatch, tmp_path):
    """Stessa regola delle altre credenziali: entra, non esce."""
    monkeypatch.setattr(sd, "default_config_path", lambda: tmp_path / "slskd.yml")
    res = _client(db).put("/api/slskd/daemon/config", json={
        "username": "io", "password": "segretissima",
        "port": 5030, "download_dir": "/tmp/dl"})
    assert res.status_code == 200
    assert "segretissima" not in res.text
    assert res.json()["username"] == "io"
    app.dependency_overrides.clear()
```

- [ ] **Step 2: Eseguire e verificare il fallimento**

```bash
cd backend && /Users/lucadenegri/Develop/DJProject01/backend/.venv/bin/python -m pytest tests/test_slskd_daemon_router.py -q
```
Atteso: `404` su tutte le rotte.

- [ ] **Step 3: Implementare**

In `backend/app/routers/slskd.py`, in fondo:

```python
from pydantic import BaseModel

from app.services import slskd_daemon


class DaemonStatus(BaseModel):
    reachable: bool
    owned: bool
    pid: int | None = None


class DaemonConfig(BaseModel):
    username: str
    password: str
    port: int = slskd_daemon.DEFAULT_PORT
    download_dir: str = ""


class DaemonConfigResult(BaseModel):
    configured: bool
    username: str


@router.get("/daemon/status", response_model=DaemonStatus)
def daemon_status() -> DaemonStatus:
    return DaemonStatus(**slskd_daemon.daemon_status())


@router.post("/daemon/start", response_model=DaemonStatus)
def daemon_start() -> DaemonStatus:
    try:
        return DaemonStatus(**slskd_daemon.start())
    except slskd_daemon.AlreadyUp as exc:
        raise api_error(409, "slskd_already_up", str(exc)) from exc
    except slskd_daemon.NotInstalled as exc:
        raise api_error(409, "slskd_not_installed", str(exc)) from exc
    except slskd_daemon.StartFailed as exc:
        raise api_error(502, "slskd_start_failed", str(exc), reason=str(exc)) from exc


@router.post("/daemon/stop", response_model=DaemonStatus)
def daemon_stop() -> DaemonStatus:
    try:
        return DaemonStatus(**slskd_daemon.stop())
    except slskd_daemon.NotOurs as exc:
        raise api_error(409, "slskd_not_ours", str(exc)) from exc


@router.put("/daemon/config", response_model=DaemonConfigResult)
def daemon_config(req: DaemonConfig) -> DaemonConfigResult:
    """La password entra e non esce: non ne teniamo copia e non la
    rispondiamo. L'username sì, si rilegge dal file."""
    config = slskd_daemon.default_config_path()
    slskd_daemon.write_config(
        config, username=req.username, password=req.password,
        port=req.port, download_dir=req.download_dir or runtime_settings.slskd_download_dir(),
    )
    return DaemonConfigResult(configured=True, username=req.username)
```

- [ ] **Step 4: Eseguire i test**

```bash
cd backend && /Users/lucadenegri/Develop/DJProject01/backend/.venv/bin/python -m pytest tests/test_slskd_daemon_router.py -q
```
Atteso: `6 passed`.

- [ ] **Step 5: Suite completa**

```bash
cd backend && /Users/lucadenegri/Develop/DJProject01/backend/.venv/bin/python -m pytest tests -q
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers/slskd.py backend/tests/test_slskd_daemon_router.py
git commit -m "feat(slskd): endpoint di configurazione, avvio e arresto del demone"
```

---

## Task 10: Client API e dizionari

**Files:**
- Modify: `frontend/lib/api/setup.ts`, `frontend/lib/api/slskd.ts`, `frontend/lib/i18n/en.ts`, `frontend/lib/i18n/it.ts`

**Interfaces:**
- Produces: `ProbeComponent` guadagna `installable: boolean`; `daemonStatus()`, `daemonStart()`, `daemonStop()`, `daemonConfig(body)` con tipo `SlskdDaemonStatus = {reachable: boolean; owned: boolean; pid: number | null}`; chiavi i18n nuove.

- [ ] **Step 1: Aggiornare i tipi e il client**

In `frontend/lib/api/setup.ts`, dentro `ProbeComponent`:

```ts
  /** Esiste una build nel manifesto per questa piattaforma: se è false, il
   *  bottone Installa non ha senso e si mostra il comando manuale. */
  installable: boolean;
```

In `frontend/lib/api/slskd.ts`:

```ts
export type SlskdDaemonStatus = { reachable: boolean; owned: boolean; pid: number | null };

/** Stato del demone: raggiungibile via HTTP, e se l'abbiamo avviato noi. */
export function daemonStatus() {
  return apiGet<SlskdDaemonStatus>("/api/slskd/daemon/status");
}

/** Avvia il demone. 409 se è già acceso o se il binario non c'è, 502 se non risponde. */
export function daemonStart() {
  return apiPost<SlskdDaemonStatus>("/api/slskd/daemon/start");
}

/** Ferma il demone — solo se l'abbiamo avviato noi (409 altrimenti). */
export function daemonStop() {
  return apiPost<SlskdDaemonStatus>("/api/slskd/daemon/stop");
}

/** Scrive le credenziali Soulseek nel slskd.yml. La password non torna indietro. */
export function daemonConfig(body: {
  username: string; password: string; port?: number; download_dir?: string;
}) {
  return apiPut<{ configured: boolean; username: string }>("/api/slskd/daemon/config", body);
}
```

- [ ] **Step 2: Aggiungere le chiavi i18n**

In `frontend/lib/i18n/en.ts`, dentro `setup`, accanto alle chiavi di installazione:

```ts
    installAllMissing: "Install what's missing",
    installNoBuild: "We don't have a build for this platform.",
    installConfigure: "Configure",
    daemonTitle: "Soulseek daemon",
    daemonRunning: "Running",
    daemonRunningElsewhere: "Already running — started outside Cratory",
    daemonStopped: "Not running",
    daemonInstallAndStart: "Download, configure and start",
    daemonStarting: "Starting…",
    daemonStop: "Stop",
    daemonUsername: "Soulseek username",
    daemonPassword: "Soulseek password",
    daemonCredentialsNote: "These go into slskd's own configuration file. Cratory keeps no copy.",
```

e in `frontend/lib/i18n/it.ts` le stesse chiavi:

```ts
    installAllMissing: "Installa quello che manca",
    installNoBuild: "Non abbiamo una build per questa piattaforma.",
    installConfigure: "Configura",
    daemonTitle: "Demone Soulseek",
    daemonRunning: "In esecuzione",
    daemonRunningElsewhere: "Già in esecuzione — avviato fuori da Cratory",
    daemonStopped: "Non in esecuzione",
    daemonInstallAndStart: "Scarica, configura e avvia",
    daemonStarting: "Avvio in corso…",
    daemonStop: "Ferma",
    daemonUsername: "Username Soulseek",
    daemonPassword: "Password Soulseek",
    daemonCredentialsNote: "Finiscono nel file di configurazione di slskd. Cratory non ne tiene copia.",
```

Aggiungere anche le chiavi d'errore nuove in `errors`, in entrambe le lingue: `slskd_already_up`, `slskd_not_installed`, `slskd_start_failed`, `slskd_not_ours`.

- [ ] **Step 3: Verificare**

```bash
cd frontend && npx tsc --noEmit && npm run lint
```
Atteso: pulito. Se `it.ts` manca una chiave, TypeScript lo dice qui.

- [ ] **Step 4: Commit**

```bash
git add frontend/lib
git commit -m "feat(setup): client del demone e chiavi i18n dell'installer"
```

---

## Task 11: Il passo 1 installa davvero

**Files:**
- Modify: `frontend/components/setup/steps/prerequisites.tsx`, `frontend/components/setup/component-row.tsx`
- Test: `frontend/tests/component-row.test.tsx`, `frontend/tests/prerequisites-step.test.tsx` (nuovo)

**Interfaces:**
- Consumes: `ProbeComponent.installable`, `startInstall`, `getInstallStatus`.
- Produces: `<PrerequisitesStep onGoToSlskd={() => void} />`; `ComponentRow` mostra "Configura" per `kind === "daemon"`.

- [ ] **Step 1: Scrivere i test che falliscono**

Aggiungere in `frontend/tests/component-row.test.tsx` (il factory `comp` guadagna `installable: true`):

```tsx
describe("ComponentRow: installabilità", () => {
  beforeEach(() => vi.clearAllMocks());
  afterEach(cleanup);

  it("senza build per la piattaforma non offre il bottone", () => {
    render(<ComponentRow c={comp({
      key: "ffmpeg", installable: false, auto_installable: false,
      install_command: ["brew", "install", "ffmpeg"],
    })} onChanged={() => {}} />);
    expect(screen.queryByRole("button", { name: /installa|install/i })).toBeNull();
    expect(screen.getByText(/brew install ffmpeg/)).toBeTruthy();
  });

  it("il demone rimanda al suo passo invece di installarsi alla cieca", () => {
    const onConfigure = vi.fn();
    render(<ComponentRow c={comp({
      key: "slskd", kind: "daemon", installable: true, auto_installable: true,
      install_command: null,
    })} onChanged={() => {}} onConfigure={onConfigure} />);
    fireEvent.click(screen.getByRole("button", { name: /configura|configure/i }));
    expect(onConfigure).toHaveBeenCalled();
  });
});
```

Creare `frontend/tests/prerequisites-step.test.tsx`:

```tsx
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { PrerequisitesStep } from "@/components/setup/steps/prerequisites";
import type { ProbeComponent } from "@/lib/api";

const getProbe = vi.fn();
const startInstall = vi.fn();
const getInstallStatus = vi.fn();
vi.mock("@/lib/api", () => ({
  errText: (e: unknown) => String((e as Error)?.message ?? e),
  getProbe: (...a: unknown[]) => getProbe(...a),
  startInstall: (...a: unknown[]) => startInstall(...a),
  getInstallStatus: (...a: unknown[]) => getInstallStatus(...a),
}));

function comp(over: Partial<ProbeComponent>): ProbeComponent {
  return {
    key: "fpcalc", kind: "system", severity: "optional", present: false,
    version: null, source: null, auto_installable: true, installable: true,
    install_command: null, unlocks: [], docs: "https://esempio.invalid",
    ...over,
  };
}

describe("PrerequisitesStep", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    startInstall.mockResolvedValue({ key: "fpcalc", status: "running", log: [], detail: null });
    getInstallStatus.mockResolvedValue({ key: "fpcalc", status: "done", log: [], detail: null });
  });
  afterEach(cleanup);

  it("installa in sequenza solo ciò che manca ed è installabile", async () => {
    getProbe.mockResolvedValue({ platform: "darwin-arm64", components: [
      comp({ key: "ffmpeg", present: false, installable: false }),
      comp({ key: "fpcalc", present: false, installable: true }),
      comp({ key: "slskd", kind: "daemon", present: true, installable: true }),
    ]});
    render(<PrerequisitesStep onGoToSlskd={() => {}} />);
    const bottone = await screen.findByRole("button", { name: /installa quello che manca|install what/i });
    fireEvent.click(bottone);
    // ffmpeg non ha build su questa piattaforma, slskd c'è già: resta fpcalc.
    await waitFor(() => expect(startInstall).toHaveBeenCalledTimes(1));
    expect(startInstall).toHaveBeenCalledWith("fpcalc");
  });

  it("il bottone è spento quando non c'è niente da installare", async () => {
    getProbe.mockResolvedValue({ platform: "darwin-arm64", components: [
      comp({ present: true }),
    ]});
    render(<PrerequisitesStep onGoToSlskd={() => {}} />);
    const bottone = await screen.findByRole("button", { name: /installa quello che manca|install what/i });
    expect((bottone as HTMLButtonElement).disabled).toBe(true);
  });
});
```

- [ ] **Step 2: Eseguire e verificare il fallimento**

```bash
cd frontend && npm run test:unit -- tests/prerequisites-step.test.tsx tests/component-row.test.tsx
```
Atteso: FAIL (il bottone non esiste, `onConfigure` non esiste).

- [ ] **Step 3: Aggiornare `ComponentRow`**

In `frontend/components/setup/component-row.tsx`:

1. La firma guadagna `onConfigure?: () => void`.
2. Il bottone Installa compare quando `!c.present && c.installable && c.kind !== "daemon"`.
3. Per `kind === "daemon"` non presente, al suo posto:

```tsx
      {!c.present && c.kind === "daemon" && (
        <div className="mt-3">
          <Button size="sm" variant="outline" onClick={onConfigure}>
            {t.setup.installConfigure}
          </Button>
        </div>
      )}
```

4. Quando `!c.present && !c.installable`, sopra il comando manuale:

```tsx
          <p className="mb-1 text-xs text-muted">{t.setup.installNoBuild}</p>
```

- [ ] **Step 4: Aggiungere il bottone al passo**

In `frontend/components/setup/steps/prerequisites.tsx`, la firma diventa `({ onGoToSlskd }: { onGoToSlskd: () => void })` e sopra la lista:

```tsx
  const mancanti = (components ?? []).filter(
    (c) => !c.present && c.installable && c.kind !== "daemon",
  );

  const installaTutto = async () => {
    // In sequenza, non in parallelo: il backend esegue un job alla volta e
    // risponderebbe 409 al secondo. Lo stesso lucchetto che disabilita i
    // bottoni delle righe vale qui.
    setBusyKey("__tutti__");
    try {
      for (const c of mancanti) {
        await startInstall(c.key);
        // eslint-disable-next-line no-await-in-loop
        while ((await getInstallStatus()).status === "running") {
          await new Promise((r) => setTimeout(r, 1000));
        }
      }
    } finally {
      setBusyKey(null);
      load(true);
    }
  };
```

e nel JSX, sopra il riquadro delle righe:

```tsx
          <Button size="sm" variant="outline"
                  disabled={mancanti.length === 0 || busyKey !== null}
                  onClick={installaTutto}>
            {t.setup.installAllMissing}
          </Button>
```

passando `onConfigure={onGoToSlskd}` a ogni `ComponentRow`.

In `frontend/app/setup/page.tsx`, passare `onGoToSlskd={() => setIndex(STEPS.indexOf("slskd"))}`.

- [ ] **Step 5: Eseguire i test**

```bash
cd frontend && npm run test:unit && npx tsc --noEmit && npm run lint
```
Atteso: tutto verde.

- [ ] **Step 6: Commit**

```bash
git add frontend/components/setup frontend/app/setup frontend/tests
git commit -m "feat(setup): un bottone installa tutti i binari mancanti"
```

---

## Task 12: Il passo slskd e i comandi in Impostazioni

**Files:**
- Modify: `frontend/components/setup/steps/slskd.tsx`, `frontend/components/settings/services-list.tsx`
- Test: `frontend/tests/slskd-step.test.tsx` (nuovo)

**Interfaces:**
- Consumes: `daemonStatus`, `daemonStart`, `daemonStop`, `daemonConfig`, `startInstall`, `getInstallStatus`.

- [ ] **Step 1: Scrivere il test che fallisce**

Creare `frontend/tests/slskd-step.test.tsx`:

```tsx
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { SlskdStep } from "@/components/setup/steps/slskd";

const daemonStatus = vi.fn();
const daemonStart = vi.fn();
const daemonStop = vi.fn();
const daemonConfig = vi.fn();
vi.mock("@/lib/api", () => ({
  errText: (e: unknown) => String((e as Error)?.message ?? e),
  getConfigSettings: vi.fn().mockResolvedValue({
    slskd_url: { value: "http://localhost:5030", source: "env", detail: null },
    slskd_download_dir: { value: "/tmp/dl", source: "env", detail: null },
    secrets: { slskd_api_key: { configured: false, source: "env", hint: null } },
  }),
  patchConfigSettings: vi.fn(),
  pickerAvailability: vi.fn().mockResolvedValue({ available: false }),
  pickPath: vi.fn(),
  slskdStatus: vi.fn().mockResolvedValue({ configured: true, reachable: false }),
  daemonStatus: (...a: unknown[]) => daemonStatus(...a),
  daemonStart: (...a: unknown[]) => daemonStart(...a),
  daemonStop: (...a: unknown[]) => daemonStop(...a),
  daemonConfig: (...a: unknown[]) => daemonConfig(...a),
  startInstall: vi.fn().mockResolvedValue({ status: "running" }),
  getInstallStatus: vi.fn().mockResolvedValue({ status: "done" }),
}));

describe("SlskdStep", () => {
  beforeEach(() => vi.clearAllMocks());
  afterEach(cleanup);

  it("demone acceso da altri: nessun bottone Ferma", async () => {
    // Non spegniamo un processo che non abbiamo avviato noi: il bottone non
    // deve nemmeno comparire.
    daemonStatus.mockResolvedValue({ reachable: true, owned: false, pid: null });
    render(<SlskdStep />);
    await waitFor(() => expect(daemonStatus).toHaveBeenCalled());
    expect(screen.queryByRole("button", { name: /ferma|stop/i })).toBeNull();
  });

  it("demone avviato da noi: il bottone Ferma c'è", async () => {
    daemonStatus.mockResolvedValue({ reachable: true, owned: true, pid: 42 });
    render(<SlskdStep />);
    expect(await screen.findByRole("button", { name: /ferma|stop/i })).toBeTruthy();
  });

  it("la password non resta nel campo dopo il salvataggio", async () => {
    daemonStatus.mockResolvedValue({ reachable: false, owned: false, pid: null });
    daemonConfig.mockResolvedValue({ configured: true, username: "io" });
    daemonStart.mockResolvedValue({ reachable: true, owned: true, pid: 7 });
    render(<SlskdStep />);
    const pwd = await screen.findByLabelText(/password/i) as HTMLInputElement;
    fireEvent.change(pwd, { target: { value: "segretissima" } });
    fireEvent.change(await screen.findByLabelText(/username/i), { target: { value: "io" } });
    fireEvent.click(screen.getByRole("button", { name: /scarica, configura e avvia|download, configure/i }));
    await waitFor(() => expect(daemonConfig).toHaveBeenCalled());
    expect(pwd.value).toBe("");
  });
});
```

- [ ] **Step 2: Eseguire e verificare il fallimento**

```bash
cd frontend && npm run test:unit -- tests/slskd-step.test.tsx
```
Atteso: FAIL — il componente non ha ancora i campi né i bottoni.

- [ ] **Step 3: Implementare il passo**

In `frontend/components/setup/steps/slskd.tsx`, aggiungere sotto i campi esistenti:

```tsx
  const [daemon, setDaemon] = useState<SlskdDaemonStatus | null>(null);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [avvio, setAvvio] = useState(false);
  const [erroreDemone, setErroreDemone] = useState<string | null>(null);

  useEffect(() => { daemonStatus().then(setDaemon).catch(() => setDaemon(null)); }, []);

  const scaricaEAvvia = async () => {
    setAvvio(true);
    setErroreDemone(null);
    try {
      await daemonConfig({ username, password });
      setPassword("");   // non resta in memoria oltre l'invio
      await startInstall("slskd");
      while ((await getInstallStatus()).status === "running") {
        await new Promise((r) => setTimeout(r, 1000));
      }
      setDaemon(await daemonStart());
    } catch (e) {
      setErroreDemone(errText(e));
    } finally {
      setAvvio(false);
    }
  };
```

e nel JSX:

```tsx
      {daemon?.reachable ? (
        <div className="flex items-center gap-3">
          <span className="text-xs text-fg-strong">
            {daemon.owned ? t.setup.daemonRunning : t.setup.daemonRunningElsewhere}
          </span>
          {daemon.owned && (
            <Button size="sm" variant="outline"
                    onClick={async () => setDaemon(await daemonStop())}>
              {t.setup.daemonStop}
            </Button>
          )}
        </div>
      ) : (
        <div className="space-y-2">
          <Field label={t.setup.daemonUsername}>
            <Input value={username} onChange={(e) => setUsername(e.target.value)} />
          </Field>
          <Field label={t.setup.daemonPassword}>
            <Input type="password" value={password}
                   onChange={(e) => setPassword(e.target.value)} />
          </Field>
          <p className="text-xs text-faint">{t.setup.daemonCredentialsNote}</p>
          <Button size="sm" variant="outline" disabled={avvio || !username || !password}
                  onClick={scaricaEAvvia}>
            {avvio ? t.setup.daemonStarting : t.setup.daemonInstallAndStart}
          </Button>
          {erroreDemone && <Alert tone="danger">{erroreDemone}</Alert>}
        </div>
      )}
```

`Field` di `@/components/ui` associa la label all'input: serve perché il test usa `findByLabelText`, e serve all'accessibilità.

- [ ] **Step 4: Aggiungere i comandi in Impostazioni**

In `frontend/components/settings/services-list.tsx`, dentro `SlskdExtra`,
aggiungere lo stato del demone e i comandi. Vale la stessa regola del wizard:
il bottone Ferma esiste solo se il demone è nostro.

```tsx
  const [daemon, setDaemon] = useState<SlskdDaemonStatus | null>(null);
  const [inCorso, setInCorso] = useState(false);
  const [erroreDemone, setErroreDemone] = useState<string | null>(null);

  useEffect(() => { daemonStatus().then(setDaemon).catch(() => setDaemon(null)); }, []);

  const comanda = async (azione: () => Promise<SlskdDaemonStatus>) => {
    setInCorso(true);
    setErroreDemone(null);
    try {
      setDaemon(await azione());
    } catch (e) {
      setErroreDemone(errText(e));
    } finally {
      setInCorso(false);
    }
  };
```

e nel JSX di `SlskdExtra`:

```tsx
      {daemon && (
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <span className="text-[10px] uppercase tracking-wider text-muted">
            {daemon.reachable
              ? (daemon.owned ? t.setup.daemonRunning : t.setup.daemonRunningElsewhere)
              : t.setup.daemonStopped}
          </span>
          {daemon.reachable && daemon.owned && (
            <Button size="sm" variant="outline" disabled={inCorso}
                    onClick={() => comanda(daemonStop)}>
              {t.setup.daemonStop}
            </Button>
          )}
          {!daemon.reachable && (
            <Button size="sm" variant="outline" disabled={inCorso}
                    onClick={() => comanda(daemonStart)}>
              {t.setup.daemonInstallAndStart}
            </Button>
          )}
          {erroreDemone && <span className="text-xs text-danger">{erroreDemone}</span>}
        </div>
      )}
```

Nota: qui il bottone di avvio **non** riconfigura né riscarica — a regime le
credenziali ci sono già e il binario pure. Se manca il binario, il backend
risponde `409 slskd_not_installed` e il messaggio tradotto rimanda al wizard.

- [ ] **Step 5: Verificare nel browser**

Avviare il preview, aprire `/setup`, arrivare al passo slskd. Con il demone dell'utente acceso deve dire "già in esecuzione, avviato fuori da Cratory" e non mostrare Ferma. Controllare console e rete.

```bash
cd frontend && npm run test:unit && npx tsc --noEmit && npm run lint && npm run build
```

- [ ] **Step 6: Commit**

```bash
git add frontend
git commit -m "feat(slskd): configurazione, avvio e arresto del demone dalla UI"
```

---

## Task 13: Documentazione

**Files:**
- Modify: `docs/ARCHITECTURE.md`, `docs/API.md`, `docs/DEPENDENCIES.md`, `docs/ROADMAP.md`, `PROGRESS.md`

- [ ] **Step 1: `docs/ARCHITECTURE.md`**

Tre modifiche, tutte sostanziali:

1. Il paragrafo sul probe descrive ancora cinque componenti e il rilevamento per import: va riscritto sui tre binari, sulla cartella gestita (`bin_dir` come default di `CRATORY_BIN_DIR`) e sul manifesto pinnato. Spiegare **perché macOS non ha una voce per ffmpeg** — è una decisione, non una dimenticanza.
2. `component_installer.py` non esiste più: sostituirlo con `binary_installer.py` e `binary_manifest.py`, dicendo che l'installazione è valida solo dopo la prova d'esecuzione.
3. **Il confine su slskd si è spostato.** Dove il documento dice che slskd è un servizio esterno raggiunto via HTTP, aggiungere che Cratory ora lo scarica, lo configura e lo avvia come processo indipendente, e le due regole che tengono la deroga sotto controllo: non si distrugge la configurazione dell'utente, non si ferma un processo che non abbiamo avviato.

- [ ] **Step 2: `docs/API.md`**

Aggiungere i quattro endpoint `/api/slskd/daemon/*` con i codici d'errore (`409` già acceso / non installato / non nostro, `502` non risponde). Aggiornare la sezione `setup` con `installable` nel payload del probe.

- [ ] **Step 3: `docs/DEPENDENCIES.md`**

ffmpeg, fpcalc e slskd possono ora arrivare dall'app: indicare da dove (Chromaprint upstream, BtbN, release slskd), con quali versioni pinnate, e che su macOS ffmpeg resta manuale.

- [ ] **Step 4: `docs/ROADMAP.md` e `PROGRESS.md`**

Una voce ciascuno, con la data.

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
git add docs PROGRESS.md
git commit -m "docs(setup): installer dei binari, manifesto pinnato e deroga su slskd"
```
