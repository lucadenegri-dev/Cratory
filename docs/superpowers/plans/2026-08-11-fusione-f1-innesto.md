# Fusione Sortory → Cratory — F1 (Innesto meccanico) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Portare tutto il codice di Sortory dentro il repo Cratory sotto il namespace `organize`, con storia git preservata, un venv, un `package.json`, un processo FastAPI e un frontend soli — lasciando ancora separati i due database.

**Architecture:** Il codice Sortory atterra via subtree merge, poi viene spostato con `git mv` sotto `backend/app/organize/` e `frontend/app/organize/`. Gli import interni vengono riscritti meccanicamente (`app.X` → `app.organize.X`, tranne `app.main`). I router Sortory vengono rimontati sotto `/api/organize/*` perché `/api/settings`, `/api/files` e `/api/library` collidono con Cratory. `app.organize.db` mantiene un proprio `Base`/engine e un proprio file SQLite: l'unificazione del DB è F2.

**Tech Stack:** Python 3.11.15, FastAPI, SQLAlchemy 2, Pydantic 2, SQLite, pytest — Next 16.2.9, React 19.2.4, Tailwind v4, TypeScript, vitest, Playwright.

**Spec di riferimento:** `docs/superpowers/specs/2026-08-11-fusione-sortory-cratory-design.md` (fase F1).

## Global Constraints

- **Worktree isolato**: il lavoro NON si fa su `master` del checkout principale. Il worktree ha `npm install` reale (mai symlink a `node_modules`: rompe Turbopack) e un `backend/.venv` proprio.
- **Python 3.11.15** in entrambi i progetti: nessun problema di versione, un solo venv.
- **Commit senza `Co-Authored-By`**: mai aggiungere Claude come co-autore.
- **Prima di ogni commit**: `git status --porcelain` e `git branch --show-current`; stageare solo i propri file (possono girare sessioni parallele sullo stesso checkout).
- **Frontend**: leggere `frontend/CLAUDE.md` prima di toccare pagine o routing (Next 16 ha breaking change rispetto alle versioni note; in particolare lo spazio JSX dopo un elemento inline sparisce se il testo va a capo nel sorgente → serve `{" "}` esplicito).
- **In F1 il DB resta doppio**: `data/djassistant.db` (Cratory) e `data/djorganizer.db` (Organize). Nessuna migrazione dati in questa fase.
- **In F1 il prefisso `DJORG_` resta**: le chiavi di configurazione Organize continuano a chiamarsi `DJORG_*`, lette dallo stesso `backend/.env`. La rimozione del prefisso è F2.
- **In F1 `AudioFile` resta in `app/organize/models.py`**: la promozione a modello core è F3.
- Percorsi assoluti nel piano: checkout principale Cratory `/Users/lucadenegri/Develop/DJProject01`, checkout Sortory `/Users/lucadenegri/Develop/DjOrganizer01` (branch `main`).

---

## File Structure

Alla fine di F1 il worktree contiene:

```
backend/
  requirements.txt              modificato: unione delle due liste
  pytest.ini                    modificato: markers + addopts + filterwarnings
  .env                          modificato: chiavi DJORG_* aggiunte
  app/
    main.py                     modificato: monta i router organize + ensure_schema organize
    db.py, models.py, …         invariati (Cratory)
    services/                   invariati (Cratory)
    organize/
      __init__.py               nuovo
      db.py                     da Sortory app/db.py (Base/engine propri)
      models.py                 da Sortory app/models.py
      schemas.py                da Sortory app/schemas.py
      core/                     da Sortory app/core/ (config.py, http_errors.py)
      routers/                  da Sortory app/routers/ (prefissi → /api/organize/*)
      services/                 da Sortory app/services/
      integrations/             da Sortory app/integrations/
  tests/
    conftest.py                 invariato (Cratory)
    test_*.py                   invariati (Cratory)
    organize/
      conftest.py               da Sortory tests/conftest.py
      fixtures/                 da Sortory tests/fixtures/
      test_*.py                 da Sortory tests/ (path HTTP → /api/organize/*)
frontend/
  package.json                  invariato (Cratory: è già il superset)
  app/
    organize/
      page.tsx                  da Sortory app/page.tsx
      files/page.tsx            da Sortory app/files/page.tsx
      issues/page.tsx           da Sortory app/issues/page.tsx
      duplicates/page.tsx       da Sortory app/duplicates/page.tsx
      plan/page.tsx             da Sortory app/plan/page.tsx
      history/page.tsx          da Sortory app/history/page.tsx
      sources/page.tsx          da Sortory app/sources/page.tsx
      settings/page.tsx         da Sortory app/settings/page.tsx
      layout.tsx                nuovo: monta OrganizeI18nProvider
  components/organize/          da Sortory components/ (meno quelli condivisi)
  lib/organize/
    api.ts                      da Sortory lib/api.ts (base → /api/organize)
    i18n/                       da Sortory lib/i18n/
```

**Non entrano** (i loro equivalenti Cratory vincono già in F1): `frontend/app/layout.tsx`, `frontend/app/globals.css`, `frontend/app/icon.svg`, `frontend/lib/cn.ts`, `frontend/next.config.ts`, `frontend/tsconfig.json`, `frontend/postcss.config.mjs`, `frontend/eslint.config.mjs`, `backend/app/main.py` di Sortory.

**Restano duplicati fino a F5** (dichiarato, non dimenticato): `components/organize/index-nav.tsx`, `editorial-shell`, `page-layout`, `theme-toggle`, `clock`, `path-picker-button`, `ui.tsx`, `jobs-provider`, e `lib/organize/i18n/`. F5 li deduplica.

---

### Task 1: Worktree isolato e innesto git

**Files:**
- Create: worktree `/Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1`
- Modify: (nessun file sorgente — solo alberi git)

**Interfaces:**
- Consumes: niente
- Produces: worktree su branch `feat/fusione-f1`, con l'albero Sortory sotto `_sortory/` e la sua storia raggiungibile da `git log --follow`

- [ ] **Step 1: Verificare che il checkout principale sia pulito**

```bash
cd /Users/lucadenegri/Develop/DJProject01 && git branch --show-current && git status --porcelain
```

Atteso: `master` e nessun output da `status`. Se ci sono modifiche non tue, **fermati**: possono essere di una sessione parallela.

- [ ] **Step 2: Creare il worktree**

```bash
cd /Users/lucadenegri/Develop/DJProject01 && git worktree add .claude/worktrees/fusione-f1 -b feat/fusione-f1
```

Atteso: `Preparing worktree (new branch 'feat/fusione-f1')`.

- [ ] **Step 3: Agganciare il repo Sortory come remote e fetchare**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1 && git remote add sortory /Users/lucadenegri/Develop/DjOrganizer01 && git fetch sortory main
```

Atteso: `* branch main -> FETCH_HEAD` e l'elenco degli oggetti scaricati.

- [ ] **Step 4: Subtree merge con storia preservata**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1 && \
git merge -s ours --no-commit --allow-unrelated-histories sortory/main && \
git read-tree --prefix=_sortory/ -u sortory/main && \
git commit -m "chore: innesto del repo Sortory sotto _sortory/ (subtree merge, storia preservata)"
```

Atteso: `Automatic merge went well` seguito dal commit. Il flag `-s ours` fa sì che il merge non porti nulla nella root; `read-tree --prefix` deposita l'albero Sortory sotto `_sortory/`.

- [ ] **Step 5: Verificare che la storia di Sortory sia raggiungibile**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1 && \
git merge-base --is-ancestor sortory/main HEAD && echo "sortory/main è antenato di HEAD" && \
git rev-list HEAD ^master | wc -l
```

Atteso: il messaggio `sortory/main è antenato di HEAD`, e un conteggio di **321** (i 320 commit Sortory più il commit di merge). Se `--is-ancestor` fallisce, il merge ha perso la storia: rifare dallo Step 4.

**Non** usare `git log --follow` per questa verifica: `--follow` non attraversa i commit di merge e non può vedere un path che prima del merge non esisteva con quel nome, quindi restituisce `0` anche quando la storia è perfettamente preservata. Per leggere la storia di un singolo file Sortory si parte dal ref di origine:

```bash
git log --oneline sortory/main -- backend/app/models.py
```

- [ ] **Step 6: Verificare che i due alberi convivano**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1 && ls && ls _sortory
```

Atteso: nella root `backend frontend docs …` più `_sortory`; dentro `_sortory` la struttura di Sortory (`backend frontend docs CLAUDE.md …`).

---

### Task 2: Ambiente unificato (dipendenze + venv + node_modules)

**Files:**
- Modify: `backend/requirements.txt`
- Create: `backend/.venv/` (nel worktree), `frontend/node_modules/` (nel worktree)
- Test: `backend/tests/organize/test_env_smoke.py`

**Interfaces:**
- Consumes: worktree di Task 1
- Produces: un venv in cui sono importabili sia le dipendenze Cratory sia `mutagen`, `acoustid`, `PIL`; `npm run build` funzionante

- [ ] **Step 1: Scrivere il test che fallisce**

Crea `backend/tests/organize/test_env_smoke.py`:

```python
"""Le dipendenze esclusive di Organize devono essere importabili nel venv unico."""


def test_mutagen_importabile():
    import mutagen  # noqa: F401


def test_acoustid_importabile():
    import acoustid  # noqa: F401


def test_pillow_importabile():
    from PIL import Image  # noqa: F401
```

Serve anche `backend/tests/organize/__init__.py` vuoto (la suite Sortory usa package con `__init__.py`).

- [ ] **Step 2: Creare il venv e installare le dipendenze attuali**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/backend && python3.11 -m venv .venv && .venv/bin/pip install -q -r requirements.txt
```

Atteso: nessun errore. `python3.11 -V` deve dare `Python 3.11.15`.

- [ ] **Step 3: Lanciare il test e verificare che fallisca**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/backend && .venv/bin/python -m pytest tests/organize/test_env_smoke.py -v
```

Atteso: `test_acoustid_importabile` e `test_pillow_importabile` FALLISCONO con `ModuleNotFoundError`. (`mutagen` passa già: è in entrambi i requirements.)

- [ ] **Step 4: Unire i requirements**

In `backend/requirements.txt`, aggiungere in fondo:

```
# --- Organize (ex Sortory) -------------------------------------------------
# Fingerprint acustico AcoustID/MusicBrainz. Richiede anche il binario di
# sistema `fpcalc` (chromaprint): senza, il provider fingerprint resta inattivo.
pyacoustid
# Thumbnail delle cover (proposte dai provider e embeddate nei file).
Pillow
```

`mutagen`, `anthropic`, `httpx`, `pytest`, `python-dotenv` sono già presenti o coperti dalle versioni Cratory: non vanno duplicati.

- [ ] **Step 5: Installare e verificare che il test passi**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/backend && .venv/bin/pip install -q -r requirements.txt && .venv/bin/python -m pytest tests/organize/test_env_smoke.py -v
```

Atteso: 3 passed.

- [ ] **Step 6: Verificare la presenza di `fpcalc`**

```bash
which fpcalc || echo "ASSENTE"
```

Se stampa `ASSENTE`, **non è un blocco per F1**: il provider fingerprint degrada a inattivo, come già documentato in `DEPENDENCIES.md` di Sortory. Annotalo nel commit message.

- [ ] **Step 7: Installare node_modules reali nel worktree**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/frontend && npm install
```

Atteso: installazione completata. **Mai** sostituire con un symlink a `node_modules` del checkout principale: rompe la build Turbopack.

- [ ] **Step 8: Verificare che la build frontend parta dalla base sana**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/frontend && npm run build
```

Atteso: build completata senza errori (è ancora il solo frontend Cratory).

- [ ] **Step 9: Commit**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1 && \
git add backend/requirements.txt backend/tests/organize/__init__.py backend/tests/organize/test_env_smoke.py && \
git commit -m "chore(f1): venv unico con le dipendenze di Organize (pyacoustid, Pillow)"
```

---

### Task 3: Codice backend sotto `app/organize/`

**Files:**
- Create: `backend/app/organize/__init__.py`
- Move: `_sortory/backend/app/{db,models,schemas}.py` → `backend/app/organize/`
- Move: `_sortory/backend/app/{core,routers,services,integrations}/` → `backend/app/organize/`
- Delete: `_sortory/backend/app/main.py` (assorbito in Task 5)
- Test: `backend/tests/organize/test_import_smoke.py`

**Interfaces:**
- Consumes: venv di Task 2
- Produces: `app.organize.db.Base`, `app.organize.db.engine`, `app.organize.db.SessionLocal`, `app.organize.db.ensure_schema()`, `app.organize.db.get_db()`, `app.organize.core.config.settings` (prefisso env `DJORG_`), i moduli `app.organize.{models,schemas,routers,services,integrations}`

- [ ] **Step 1: Scrivere il test che fallisce**

Crea `backend/tests/organize/test_import_smoke.py`:

```python
"""Il codice Organize deve essere importabile dal namespace app.organize e
mantenere un proprio Base/engine distinto da quello di Cratory (F1: due DB)."""


def test_moduli_organize_importabili():
    from app.organize import db, models, schemas  # noqa: F401
    from app.organize.core import config  # noqa: F401


def test_base_organize_distinto_da_quello_cratory():
    from app.db import Base as BaseCratory
    from app.organize.db import Base as BaseOrganize

    assert BaseOrganize is not BaseCratory


def test_audio_file_registrato_solo_sul_base_organize():
    import app.models  # noqa: F401
    import app.organize.models  # noqa: F401
    from app.db import Base as BaseCratory
    from app.organize.db import Base as BaseOrganize

    assert "audio_file" in BaseOrganize.metadata.tables
    assert "audio_file" not in BaseCratory.metadata.tables
    assert "tracks" in BaseCratory.metadata.tables
```

- [ ] **Step 2: Lanciare il test e verificare che fallisca**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/backend && .venv/bin/python -m pytest tests/organize/test_import_smoke.py -v
```

Atteso: FAIL con `ModuleNotFoundError: No module named 'app.organize'`.

- [ ] **Step 3: Spostare i file con `git mv`**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1 && \
mkdir -p backend/app/organize && \
touch backend/app/organize/__init__.py && \
git mv _sortory/backend/app/db.py       backend/app/organize/db.py && \
git mv _sortory/backend/app/models.py   backend/app/organize/models.py && \
git mv _sortory/backend/app/schemas.py  backend/app/organize/schemas.py && \
git mv _sortory/backend/app/core        backend/app/organize/core && \
git mv _sortory/backend/app/routers     backend/app/organize/routers && \
git mv _sortory/backend/app/services    backend/app/organize/services && \
git mv _sortory/backend/app/integrations backend/app/organize/integrations && \
git rm -q _sortory/backend/app/main.py
```

`git mv` preserva la storia (`git log --follow` continua a funzionare).

- [ ] **Step 4: Riscrivere gli import interni**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/backend/app/organize && \
find . -name '*.py' -print0 | xargs -0 sed -i '' -E 's/\bapp\.(services|models|integrations|core|db|schemas|routers)\b/app.organize.\1/g'
```

Il pattern elenca le sette radici **esplicitamente** e lascia fuori `app.main`: in F1 `app.main` è l'unico entrypoint FastAPI (quello di Cratory), quindi i riferimenti a `app.main` devono continuare a puntare lì.

- [ ] **Step 5: Verificare che non sia rimasto nessun import vecchio**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/backend/app/organize && \
grep -rnE "(from|import) app\.(services|models|integrations|core|db|schemas|routers)\b" . | grep -v "app\.organize" | head
```

Atteso: **nessun output**. Se ne compare qualcuno, la sed non l'ha preso (import su più righe con parentesi): correggilo a mano.

- [ ] **Step 6: Puntare il DB di Organize dentro `backend/data/`**

In `backend/app/organize/core/config.py`, sostituire la riga del default:

```python
    database_url: str = "sqlite:///./data/djorganizer.db"
```

con:

```python
    # Path assoluto: il default relativo dipendeva dal cwd (Sortory si lanciava
    # da backend/). Nel processo unico il cwd non è garantito. F2 unificherà
    # questo DB con quello di Cratory.
    database_url: str = f"sqlite:///{(Path(__file__).resolve().parents[3] / 'data' / 'djorganizer.db').as_posix()}"
```

e aggiungere in cima al file:

```python
from pathlib import Path
```

Nella stessa classe, cambiare `env_file=".env"` in un path assoluto, così legge lo stesso `backend/.env` di Cratory a prescindere dal cwd:

```python
    model_config = SettingsConfigDict(
        env_prefix="DJORG_",
        env_file=Path(__file__).resolve().parents[3] / ".env",
        extra="ignore",
    )
```

`parents[3]` da `backend/app/organize/core/config.py` è `backend/`.

- [ ] **Step 7: Lanciare il test e verificare che passi**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/backend && .venv/bin/python -m pytest tests/organize/test_import_smoke.py -v
```

Atteso: 3 passed.

- [ ] **Step 8: Verificare che la suite Cratory non si sia rotta**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/backend && .venv/bin/python -m pytest tests -q --ignore=tests/organize
```

Atteso: la suite Cratory passa come prima (nessun test toccato).

- [ ] **Step 9: Commit**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1 && \
git add -A backend/app/organize backend/tests/organize _sortory && \
git commit -m "feat(f1): codice backend Organize sotto app/organize/ con import riscritti"
```

---

### Task 4: Suite di test Organize sotto `tests/organize/`

**Files:**
- Move: `_sortory/backend/tests/*` → `backend/tests/organize/`
- Modify: `backend/tests/organize/conftest.py`
- Modify: `backend/pytest.ini`

**Interfaces:**
- Consumes: `app.organize.*` di Task 3
- Produces: `backend/tests/organize/` eseguibile insieme a `backend/tests/`, con DB temporaneo proprio

- [ ] **Step 1: Spostare i test**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1 && \
git mv _sortory/backend/tests/conftest.py backend/tests/organize/conftest.py && \
git mv _sortory/backend/tests/fixtures    backend/tests/organize/fixtures && \
for f in _sortory/backend/tests/test_*.py; do git mv "$f" "backend/tests/organize/$(basename $f)"; done && \
git rm -q _sortory/backend/tests/__init__.py
```

- [ ] **Step 2: Riscrivere gli import nei test**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/backend/tests/organize && \
find . -name '*.py' -print0 | xargs -0 sed -i '' -E 's/\bapp\.(services|models|integrations|core|db|schemas|routers)\b/app.organize.\1/g'
```

Anche qui `app.main` resta intatto: i test HTTP di Organize useranno l'app unificata.

- [ ] **Step 3: Adeguare il conftest di Organize**

In `backend/tests/organize/conftest.py`, la variabile d'ambiente e il commento in testa diventano:

```python
"""Fixture pytest di Organize. Il DB punta a un file temporaneo per-sessione.

Nota: il conftest di livello superiore (backend/tests/conftest.py) resta attivo
anche qui — le sue fixture autouse (reset runtime_settings, no-LLM, no-scan,
reset job state) toccano solo moduli Cratory e sono innocue per questi test.
"""

import os
import tempfile

# DEVE precedere qualsiasi import di app.organize.*: le settings leggono l'env
# al momento dell'import del modulo.
_TMP_DB = os.path.join(tempfile.mkdtemp(prefix="organize-test-"), "test.db")
os.environ["DJORG_DATABASE_URL"] = f"sqlite:///{_TMP_DB}"

import pytest  # noqa: E402

from app.organize.db import Base, SessionLocal, engine  # noqa: E402
```

e più sotto, nella fixture `_fresh_db`, l'import diventa `import app.organize.models`.

L'ultima riga del file (`from app.models import AudioFile`) diventa `from app.organize.models import AudioFile`; la sed dello Step 2 l'ha già fatto — verificalo.

- [ ] **Step 4: Verificare che la fixture `db` di Cratory non venga ereditata per sbaglio**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/backend && \
grep -n "def db" tests/conftest.py tests/organize/conftest.py
```

Atteso: **entrambi** definiscono `db`. Quello in `tests/organize/conftest.py` ha precedenza per i test di quella cartella (pytest risolve la fixture dal conftest più vicino). Nessuna azione: serve solo confermare che la definizione più vicina esista, altrimenti i test Organize riceverebbero una sessione sul `Base` sbagliato.

- [ ] **Step 4b: Verificare che i nomi di test omonimi non collidano**

Tre file esistono con lo stesso nome nelle due suite: `test_http_errors.py`, `test_native_picker.py`, `test_rating.py`. Senza precauzioni pytest fallirebbe la raccolta con `import file mismatch`. La precauzione c'è già — `backend/tests/organize/__init__.py` (creato in Task 2) rende Organize un package, mentre `backend/tests/` non lo è, quindi i moduli si chiamano `organize.test_rating` e `test_rating`. Conferma:

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/backend && \
ls tests/organize/__init__.py && ls tests/__init__.py 2>&1 | head -1 && \
.venv/bin/python -m pytest tests --collect-only -q 2>&1 | tail -3
```

Atteso: `tests/organize/__init__.py` esiste, `tests/__init__.py` **non** esiste, e la raccolta termina senza errori di import. Se compare `import file mismatch`, **non** rinominare i test: manca l'`__init__.py` in `tests/organize/`.

- [ ] **Step 5: Lanciare la sola suite Organize**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/backend && .venv/bin/python -m pytest tests/organize -q
```

Atteso: i test non-HTTP passano. **I test che fanno richieste HTTP falliscono con 404**: chiamano `/api/sources`, `/api/issues`, … che Task 5 monterà sotto `/api/organize/`. È il comportamento previsto a questo punto — non aggiustarli qui.

Annota il numero di fallimenti: servirà da confronto nello Step 5 di Task 5.

- [ ] **Step 6: Unificare `pytest.ini`**

Sostituire il contenuto di `backend/pytest.ini` con:

```ini
[pytest]
testpaths = tests
markers =
    network: tocca la rete reale; escluso di default
addopts = -m 'not network'
filterwarnings =
    error
    ignore:Using `httpx` with `starlette\.testclient` is deprecated:starlette.exceptions.StarletteDeprecationWarning:fastapi.testclient
```

- [ ] **Step 7: Misurare l'impatto di `filterwarnings = error` sulla suite Cratory**

Questo è il controllo di rischio dichiarato nella spec.

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/backend && \
.venv/bin/python -m pytest tests -q --ignore=tests/organize 2>&1 | tail -30
```

Decisione in base all'esito:

- **Nessun fallimento nuovo** → non fare nulla, la strictness vale per tutti.
- **Pochi fallimenti (≤ 5)** → sistemarli qui, uno per uno, e annotarlo nel commit.
- **Molti fallimenti (> 5)** → NON sistemarli in F1. Restringere la strictness a Organize sostituendo il blocco `filterwarnings` con:

```ini
filterwarnings =
    default
    ignore:Using `httpx` with `starlette\.testclient` is deprecated:starlette.exceptions.StarletteDeprecationWarning:fastapi.testclient
```

e aggiungendo in `backend/tests/organize/conftest.py`, subito dopo gli import:

```python
def pytest_collection_modifyitems(items):
    """Strictness sui warning ristretta ai test Organize finché la suite Cratory
    non è ripulita (vedi spec F1). Rimuovere quando `filterwarnings = error`
    varrà per tutta la suite."""
    for item in items:
        item.add_marker(pytest.mark.filterwarnings("error"))
```

Qualunque strada prendi, **scrivila nel commit message**: è un'informazione che serve a F2.

- [ ] **Step 8: Commit**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1 && \
git add -A backend/tests backend/pytest.ini _sortory && \
git commit -m "test(f1): suite Organize sotto tests/organize/ e pytest.ini unificato"
```

---

### Task 5: Router Organize sotto `/api/organize/*` e wiring in `main.py`

**Files:**
- Modify: `backend/app/organize/routers/*.py` (14 file, riga del prefisso)
- Modify: `backend/app/main.py`
- Modify: `backend/tests/organize/test_*.py` (path HTTP)
- Test: `backend/tests/organize/test_route_prefix.py`

**Interfaces:**
- Consumes: `app.organize.routers.*` di Task 3, `app.organize.db.ensure_schema` di Task 3
- Produces: tutte le rotte Organize sotto `/api/organize/…`; `/api/settings`, `/api/files`, `/api/library` restano a Cratory

**Perché il prefisso è obbligatorio e non cosmetico:** i due backend collidono su `/api/settings` (entrambi), `/api/files` (Cratory `prefix="/api/files"`, Sortory `GET /api/files` e `POST /api/files/{id}/tags`) e `/api/library` (Cratory `/api/library/index`, Sortory `/api/library/stats`). Senza prefisso l'ordine di `include_router` deciderebbe silenziosamente chi vince.

- [ ] **Step 1: Scrivere il test che fallisce**

Crea `backend/tests/organize/test_route_prefix.py`:

```python
"""Le rotte Organize vivono sotto /api/organize; le omonime di Cratory restano
al loro posto (nessuna collisione silenziosa)."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _paths() -> set[str]:
    return {r.path for r in app.routes}


def test_rotte_organize_prefissate():
    paths = _paths()
    assert "/api/organize/sources" in paths
    assert "/api/organize/issues" in paths
    assert "/api/organize/settings" in paths
    assert "/api/organize/plan" in paths


def test_nessuna_rotta_organize_fuori_dal_prefisso():
    paths = _paths()
    assert "/api/sources" not in paths
    assert "/api/issues" not in paths
    assert "/api/duplicates" not in paths


def test_rotte_cratory_intatte():
    paths = _paths()
    assert "/api/settings" in paths
    assert "/api/tracks" in paths
    assert "/api/library/index" in paths


def test_endpoint_organize_risponde():
    res = client.get("/api/organize/sources")
    assert res.status_code == 200
    assert isinstance(res.json(), list)
```

- [ ] **Step 2: Lanciare il test e verificare che fallisca**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/backend && .venv/bin/python -m pytest tests/organize/test_route_prefix.py -v
```

Atteso: FAIL — `/api/organize/sources` non è tra le rotte (i router Organize non sono ancora montati).

- [ ] **Step 3: Riscrivere i prefissi dei router**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/backend/app/organize/routers && \
sed -i '' -E 's|prefix="/api"|prefix="/api/organize"|; s|prefix="/api/([a-z-]+)"|prefix="/api/organize/\1"|' *.py && \
grep -h -o 'prefix="[^"]*"' *.py | sort -u
```

Atteso dal `grep` finale: solo path che iniziano con `/api/organize`. I tre router con `prefix="/api"` (`files.py`, `library.py`, `providers.py`) diventano `prefix="/api/organize"`, quindi le loro rotte finiscono su `/api/organize/files`, `/api/organize/library/stats`, `/api/organize/providers`.

- [ ] **Step 4: Montare i router in `main.py`**

In `backend/app/main.py`, dopo il blocco `from app.routers import settings as settings_router` (riga 30), aggiungere:

```python
from app.organize.db import ensure_schema as ensure_schema_organize
from app.organize.routers import (
    analyze as organize_analyze,
    apply as organize_apply,
    duplicates as organize_duplicates,
    files as organize_files,
    fingerprint as organize_fingerprint,
    genre_review as organize_genre_review,
    history as organize_history,
    issues as organize_issues,
    library as organize_library,
    picker as organize_picker,
    plan as organize_plan,
    providers as organize_providers,
    scan as organize_scan,
    settings as organize_settings,
    sources as organize_sources,
)
```

Dentro `lifespan`, subito dopo `ensure_schema()` (riga 38), aggiungere:

```python
    # F1: Organize ha ancora un proprio Base/engine e un proprio file SQLite.
    # F2 unificherà i due schemi su un engine solo.
    ensure_schema_organize()
```

In fondo al blocco degli `include_router` (dopo la riga `app.include_router(settings_router.router)`), aggiungere:

```python
for _organize_router in (
    organize_sources, organize_scan, organize_analyze, organize_issues,
    organize_duplicates, organize_settings, organize_plan, organize_apply,
    organize_history, organize_library, organize_files, organize_fingerprint,
    organize_providers, organize_picker, organize_genre_review,
):
    app.include_router(_organize_router.router)
```

- [ ] **Step 5: Aggiornare i path HTTP nei test di Organize**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/backend/tests/organize && \
find . -name 'test_*.py' -print0 | xargs -0 sed -i '' -E 's|"/api/|"/api/organize/|g' && \
grep -rn '"/api/organize/organize/' . | head
```

Atteso dal `grep`: **nessun output** (nessun doppio prefisso). Se ne compare, quel file era già stato passato dalla sed: correggi a mano.

- [ ] **Step 6: Lanciare i test di prefisso**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/backend && .venv/bin/python -m pytest tests/organize/test_route_prefix.py -v
```

Atteso: 4 passed.

- [ ] **Step 7: Lanciare tutta la suite Organize**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/backend && .venv/bin/python -m pytest tests/organize -q
```

Atteso: **0 fallimenti**. I 404 annotati allo Step 5 di Task 4 devono essere spariti. Se ne resta qualcuno, è un path che la sed non ha preso perché costruito con f-string o variabile: cercalo con

```bash
grep -rn 'client\.\(get\|post\|put\|patch\|delete\)(f\?"' tests/organize | grep -v "/api/organize/"
```

- [ ] **Step 8: Lanciare la suite intera**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/backend && .venv/bin/python -m pytest tests -q
```

Atteso: tutto verde (Cratory + Organize insieme).

- [ ] **Step 9: Commit**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1 && \
git add -A backend && \
git commit -m "feat(f1): router Organize montati sotto /api/organize nel processo unico"
```

---

### Task 6: Frontend Organize sotto `/organize/*`

**Files:**
- Move: `_sortory/frontend/app/*/page.tsx` → `frontend/app/organize/*/page.tsx`
- Move: `_sortory/frontend/components/*` → `frontend/components/organize/`
- Move: `_sortory/frontend/lib/api.ts` → `frontend/lib/organize/api.ts`
- Move: `_sortory/frontend/lib/i18n/` → `frontend/lib/organize/i18n/`
- Create: `frontend/app/organize/layout.tsx`
- Test: `frontend/tests/organize-api-base.test.ts`

**Interfaces:**
- Consumes: rotte `/api/organize/*` di Task 5
- Produces: pagine navigabili su `/organize`, `/organize/files`, `/organize/issues`, `/organize/duplicates`, `/organize/plan`, `/organize/history`, `/organize/sources`, `/organize/settings`

**Prima di iniziare:** leggere `frontend/CLAUDE.md`.

- [ ] **Step 1: Spostare i file**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1 && \
mkdir -p frontend/app/organize frontend/components/organize frontend/lib/organize && \
git mv _sortory/frontend/app/page.tsx frontend/app/organize/page.tsx && \
for d in files issues duplicates plan history sources settings; do \
  mkdir -p frontend/app/organize/$d && \
  git mv _sortory/frontend/app/$d/page.tsx frontend/app/organize/$d/page.tsx; \
done && \
git mv _sortory/frontend/lib/api.ts frontend/lib/organize/api.ts && \
git mv _sortory/frontend/lib/i18n  frontend/lib/organize/i18n && \
for f in _sortory/frontend/components/*.tsx; do git mv "$f" "frontend/components/organize/$(basename $f)"; done
```

- [ ] **Step 2: Eliminare i file Sortory che non entrano**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1 && git rm -r -q _sortory/frontend
```

Cadono `layout.tsx`, `globals.css`, `icon.svg`, `lib/cn.ts`, `next.config.ts`, `tsconfig.json`, `package.json`, `postcss.config.mjs`, `eslint.config.mjs` di Sortory: gli equivalenti Cratory sono già in piedi (`ui.tsx`, `cn.ts` e compagnia verranno deduplicati in F5).

- [ ] **Step 3: Scrivere il test che fallisce**

Crea `frontend/tests/organize-api-base.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const source = readFileSync(resolve(__dirname, "../lib/organize/api.ts"), "utf8");

describe("client API Organize", () => {
  it("punta al backend unico, non alla vecchia porta 8010", () => {
    expect(source).not.toContain("8010");
    expect(source).toContain("http://localhost:8000");
  });

  it("prefissa tutte le chiamate con /api/organize", () => {
    expect(source).toContain("/api/organize");
  });

  it("non contiene più path che iniziano con /api/ non prefissati", () => {
    const nudi = source.match(/"\/api\/(?!organize)[a-z-]+/g) ?? [];
    expect(nudi).toEqual([]);
  });
});
```

- [ ] **Step 4: Lanciare il test e verificare che fallisca**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/frontend && npx vitest run tests/organize-api-base.test.ts
```

Atteso: FAIL sul primo assert (`8010` è ancora nel file).

- [ ] **Step 5: Ripuntare il client API**

In `frontend/lib/organize/api.ts`, sostituire la riga 3:

```ts
const API = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8010";
```

con:

```ts
const API_ROOT = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";
/* Le rotte Organize vivono sotto /api/organize: i path passati a apiGet/apiSend
   sono relativi a questa base (es. "/sources" → /api/organize/sources). */
const API = `${API_ROOT}/api/organize`;
```

Poi accorciare i 35 path dei call site (che oggi iniziano con `/api/`):

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/frontend && \
sed -i '' -E 's|\("/api/|("/|g' lib/organize/api.ts && \
sed -i '' -E 's|\$\{API\}/api/|${API}/|g' lib/organize/api.ts && \
grep -n '/api/' lib/organize/api.ts
```

Atteso dal `grep`: solo le due righe della costante `API`/`API_ROOT`.

- [ ] **Step 6: Lanciare il test e verificare che passi**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/frontend && npx vitest run tests/organize-api-base.test.ts
```

Atteso: 3 passed.

- [ ] **Step 7: Riscrivere gli import `@/` delle pagine e dei componenti Organize**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/frontend && \
find app/organize components/organize -name '*.tsx' -print0 | xargs -0 sed -i '' \
  -e 's|@/lib/api|@/lib/organize/api|g' \
  -e 's|@/lib/i18n|@/lib/organize/i18n|g' \
  -e 's|@/components/|@/components/organize/|g' && \
find lib/organize -name '*.ts*' -print0 | xargs -0 sed -i '' \
  -e 's|@/lib/api|@/lib/organize/api|g' \
  -e 's|@/lib/i18n|@/lib/organize/i18n|g'
```

I componenti Organize importano `@/lib/cn` in 8 punti: quel modulo **non** è stato duplicato e le sed sopra non lo toccano (riscrivono solo `@/lib/api` e `@/lib/i18n`), quindi continuano a puntare al `cn.ts` condiviso di Cratory. Verificalo:

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/frontend && \
grep -rn '@/lib/organize/cn' components/organize app/organize | head
```

Atteso: **nessun output**. Se ne compare, una sed è stata troppo larga: correggi riportando l'import a `@/lib/cn`.

- [ ] **Step 8: Aggiornare i due link interni**

In `frontend/app/organize/**` e `frontend/components/organize/**` esistono esattamente due `href` interni, `"/files"` e `"/settings"`:

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/frontend && \
sed -i '' -E 's|href="/(files\|settings)"|href="/organize/\1"|g' app/organize/*/page.tsx app/organize/page.tsx components/organize/*.tsx && \
grep -rn 'href="/' app/organize components/organize | grep -v '/organize/'
```

Atteso dal `grep`: nessun output residuo che punti fuori da `/organize/` (a parte eventuali link volutamente esterni, che vanno lasciati).

- [ ] **Step 9: Creare il layout della sezione con il provider i18n di Organize**

Crea `frontend/app/organize/layout.tsx`:

```tsx
import { I18nProvider as OrganizeI18nProvider } from "@/lib/organize/i18n";

/* F1: Organize porta ancora il proprio dizionario e il proprio provider,
   annidato dentro quello di Cratory nel root layout. F5 fonde i due dizionari
   sotto la chiave `organize.*` e questo layout sparisce. */
export default function OrganizeLayout({ children }: { children: React.ReactNode }) {
  return <OrganizeI18nProvider>{children}</OrganizeI18nProvider>;
}
```

- [ ] **Step 10: Verificare che i due provider i18n non si calpestino**

Il provider Organize non costruisce URL a mano: `lib/organize/i18n/index.tsx` importa `getLanguage`/`setLanguage` da `@/lib/api`, che la sed dello Step 7 ha già ripuntato a `@/lib/organize/api`. Passa quindi automaticamente per `/api/organize/settings/language`. Nessuna modifica necessaria — solo due conferme:

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/frontend && \
grep -n 'from "@/lib' lib/organize/i18n/index.tsx && \
grep -n 'STORAGE_KEY' lib/organize/i18n/runtime.ts lib/i18n/runtime.ts
```

Atteso: l'import punta a `@/lib/organize/api`, e le due `STORAGE_KEY` sono **diverse** (`"sortory-lang"` per Organize, `"cratory-lang"` per Cratory). Chiavi distinte significa che i due provider annidati non si sovrascrivono a vicenda in `localStorage`: in F1 le due sezioni possono avere lingua diversa, ed è accettabile — F5 le unifica sotto un provider solo.

- [ ] **Step 11: Typecheck e lint**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/frontend && npx tsc --noEmit && npm run lint
```

Atteso: nessun errore. Se `tsc` segnala import non risolti, è un path della sed dello Step 7 rimasto scoperto: correggilo e rilancia.

- [ ] **Step 12: Build**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/frontend && npm run build
```

Atteso: build completata, con le rotte `/organize`, `/organize/files`, `/organize/issues`, `/organize/duplicates`, `/organize/plan`, `/organize/history`, `/organize/sources`, `/organize/settings` nell'elenco stampato.

- [ ] **Step 13: Unit test frontend**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/frontend && npm run test:unit
```

Atteso: tutti verdi (i test Cratory esistenti più il nuovo).

- [ ] **Step 14: Commit**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1 && \
git add -A frontend _sortory && \
git commit -m "feat(f1): pagine Organize sotto /organize con client API sul backend unico"
```

---

### Task 7: Verifica di fase e chiusura di F1

**Files:**
- Delete: `_sortory/` (residui: docs, README, CLAUDE.md, beets, data di Sortory)
- Modify: `backend/.env`
- Test: nessun file nuovo — è la milestone di fase

**Interfaces:**
- Consumes: tutto quanto sopra
- Produces: worktree con F1 completa e verificata

- [ ] **Step 1: Portare le chiavi `DJORG_*` nel `.env` unico**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1 && grep -E "^DJORG_|^ANTHROPIC" _sortory/backend/.env 2>/dev/null || echo "nessun .env in _sortory (non è versionato: copialo a mano dal checkout Sortory)"
```

Se il file non è versionato, prendi le chiavi da `/Users/lucadenegri/Develop/DjOrganizer01/backend/.env` e appendile a `backend/.env` del worktree, sotto un separatore:

```
# --- Organize (ex Sortory) — il prefisso DJORG_ cade in F2 -------------------
```

Non committare `backend/.env` (è git-ignored): verificalo con `git check-ignore backend/.env`.

- [ ] **Step 2: Rimuovere i residui di `_sortory/`**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1 && ls -R _sortory | head -30
```

Guarda cosa è rimasto (README, CLAUDE.md, docs/, DEPENDENCIES.md, PRODUCT.md, beets/, data/). **`docs/` e `DEPENDENCIES.md` servono a F6**: spostali invece di cancellarli.

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1 && \
mkdir -p docs/organize && \
git mv _sortory/DEPENDENCIES.md docs/organize/DEPENDENCIES.md && \
git mv _sortory/PRODUCT.md      docs/organize/PRODUCT.md && \
git mv _sortory/CLAUDE.md       docs/organize/CLAUDE-sortory-storico.md && \
git mv _sortory/README.md       docs/organize/README-sortory-storico.md && \
for d in _sortory/docs/superpowers/specs _sortory/docs/superpowers/plans; do \
  [ -d "$d" ] && for f in $d/*; do git mv "$f" "docs/superpowers/$(basename $(dirname $f))/$(basename $f)"; done; \
done; \
git rm -r -q _sortory
```

- [ ] **Step 3: Verificare che `_sortory/` sia sparito e nulla lo referenzi**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1 && \
ls _sortory 2>&1 | head -1 && grep -rn "_sortory" backend/app backend/tests frontend/app frontend/lib frontend/components 2>/dev/null | head
```

Atteso: `ls` dice che non esiste, il `grep` non produce output.

- [ ] **Step 4: Suite backend completa**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/backend && .venv/bin/python -m pytest tests -q
```

Atteso: tutto verde, ~240 file di test tra le due suite. **Riporta il conteggio reale** (passed/failed) nel messaggio finale: è la milestone.

- [ ] **Step 5: Lint e build frontend**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/frontend && npm run lint && npm run build && npm run test:unit
```

Atteso: tutti e tre verdi.

- [ ] **Step 6: End-to-end Playwright**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/frontend && npm run test:e2e
```

Atteso: la suite smoke passa. Usa porte dedicate (8211/3211), quindi non collide con eventuali server di sviluppo aperti.

- [ ] **Step 7: Avvio reale e verifica a mano delle pagine Organize**

Avvia il backend:

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/backend && .venv/bin/uvicorn app.main:app --port 8000
```

e in un'altra shell il frontend:

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/frontend && npm run dev
```

Poi verifica che rispondano:

```bash
curl -s localhost:8000/api/health && curl -s localhost:8000/api/organize/sources && curl -s localhost:8000/api/settings/language
```

Atteso: `{"status":"ok"}`, la lista delle sorgenti Organize, e la lingua di Cratory — cioè i due mondi vivi nello stesso processo senza calpestarsi.

Infine apri nel browser `http://localhost:3000/organize`, `/organize/files`, `/organize/issues`, `/organize/plan`, `/organize/history` e conferma che caricano dati veri.

- [ ] **Step 8: Commit finale di fase**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1 && \
git status --porcelain && \
git add -A && \
git commit -m "chore(f1): rimossi i residui di _sortory/, docs Sortory sotto docs/organize/"
```

- [ ] **Step 9: Riepilogo per F2**

Scrivi (nel messaggio all'utente, non in un file) l'esito dei tre punti che F2 eredita:

1. Esito dello Step 7 di Task 4 — `filterwarnings = error` esteso a tutti o ristretto a Organize, e quanti warning erano.
2. Presenza o assenza di `fpcalc` (Step 6 di Task 2).
3. Conteggio finale dei test (Step 4 di questo task).

---

## Definizione di "F1 completa"

- `.claude/worktrees/fusione-f1` sul branch `feat/fusione-f1`, `_sortory/` sparito.
- Un `requirements.txt`, un `.venv`, un `package.json`, un `node_modules`.
- `pytest tests` verde su entrambe le suite insieme.
- `npm run lint`, `npm run build`, `npm run test:unit`, `npm run test:e2e` verdi.
- Un processo `uvicorn app.main:app` che serve sia `/api/tracks` sia `/api/organize/sources`.
- `http://localhost:3000/organize` e le sue sette sottopagine caricano dati reali.
- Due file SQLite ancora distinti (`djassistant.db`, `djorganizer.db`) — **corretto in F1**, li unifica F2.
