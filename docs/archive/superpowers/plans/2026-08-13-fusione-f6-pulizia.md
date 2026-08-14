# Fusione Sortory → Cratory — F6 (pulizia) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Chiudere la fusione: togliere dal codice e dalla documentazione l'ultima traccia di due applicazioni separate, saldare i tre follow-up tecnici rimasti, e decidere `scan_root` invece di rimandarlo ancora.

**Architecture:** Nessuna modifica strutturale. Si rimuove `organizer_url` (il link "Apri Sortory" in dashboard, l'unico punto in cui l'app punta ancora a un'altra app), si tipizza `ScanSummary.linking`, si disambigua `linking.unchanged`, si rende monotono il progresso, e si riscrivono i documenti operativi per un prodotto solo — **senza riscrivere la storia**, che deve continuare a dire cosa era vero quando è stata scritta.

**Tech Stack:** Python 3.11.15, FastAPI, SQLAlchemy 2 — Next 16, React 19, TypeScript.

**Spec di riferimento:** `docs/superpowers/specs/2026-08-11-fusione-sortory-cratory-design.md`, fase F6.

**Prerequisito:** F5 mergiata su `master` (`3971d39`). Si continua su `feat/fusione-f1`.

## Cosa resta davvero, misurato

| | |
|---|---:|
| punti di codice che usano `organizer_url` | 8 |
| occorrenze di "Sortory" nei documenti operativi | 32 |
| occorrenze in `PROGRESS.md` (storia, **non** si riscrive) | 17 |
| documenti operativi da rivedere | 7 |

E una domanda che si può chiudere: **F4 non ha toccato lo schema di `audio_file`**. `root_id` è ancora `NOT NULL`, dentro `uq_audio_root_path` e con la FK verso `scan_root`. Il vincolo che rendeva impossibile il `DROP COLUMN` è identico a quello di F3b, quindi la conclusione è identica — ma va scritta come decisione, non lasciata come rinvio perpetuo.

## Global Constraints

- Worktree **`.claude/worktrees/fusione-f1`**, branch `feat/fusione-f1`.
- **Commit senza `Co-Authored-By`.** Prima di ogni commit: `git status --porcelain` e `git branch --show-current`, e **stageare solo i propri file** — sul worktree c'è una modifica altrui a `docs/superpowers/plans/2026-08-07-voto-tracce.md` che non va toccata né committata.
- **Ogni asserzione va accompagnata dal sabotaggio che la prova**, e dopo il ripristino si verifica `git diff` vuoto. Vale per i Task 1-3; il Task 4 è documentazione e si verifica con i grep descritti lì.
- **La storia non si riscrive.** `PROGRESS.md` e i piani/spec sotto `docs/superpowers/` sono documenti datati: dicevano il vero quando sono stati scritti. Si aggiorna ciò che **istruisce** (`CLAUDE.md`, `README.md`, `docs/*.md`), non ciò che **racconta**.
- **Archiviare il repo su GitHub non lo faccio io** (Task 5): è un'azione verso l'esterno, semi-permanente, e la fai tu.

---

### Task 1: Via `organizer_url`, l'ultimo puntatore a un'altra app

**Files:**
- Modify: `backend/app/core/config.py` (campo + validator), `backend/app/schemas.py:771`, `backend/app/services/pipeline.py:87`
- Modify: `frontend/lib/api/types.ts:298`, `frontend/components/dashboard/pipeline.tsx` (righe ~98-101)
- Modify: `backend/.env.example`
- Test: `backend/tests/test_pipeline_senza_organizer_url.py`

**Inventario di cosa fornisce prima di sparire** — la disciplina che in F1 è costata due Critical:

| cosa fornisce | destino |
|---|---|
| `settings.organizer_url` + il suo `field_validator` (rende assoluto un `localhost:3010` senza schema) | eliminati: non esiste più un'altra app da raggiungere |
| il campo `organizer_url` nella risposta di `/api/pipeline` | eliminato dallo schema |
| il link "Apri Sortory" nella card pipeline della dashboard | **sostituito** da un link interno a `/organize/files` |
| `ORGANIZER_URL` in `.env.example` | eliminato |

Il quarto punto è quello da non sbagliare: la card della pipeline racconta la catena `Downloads → Organize → Library`, e il link ci serve ancora — cambia solo destinazione, da un'altra app a una sezione di questa.

- [ ] **Step 1: Scrivere il test che fallisce**

Crea `backend/tests/test_pipeline_senza_organizer_url.py`:

```python
"""La pipeline non punta più a un'app esterna: Organize è una sezione."""

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_settings_non_ha_piu_organizer_url():
    from app.core.config import settings

    assert not hasattr(settings, "organizer_url")


def test_la_risposta_pipeline_non_espone_organizer_url():
    res = client.get("/api/pipeline")
    assert res.status_code == 200
    assert "organizer_url" not in res.json()


def test_lo_schema_non_dichiara_piu_il_campo():
    from app.schemas import PipelineOut

    assert "organizer_url" not in PipelineOut.model_fields
```

Verifica il nome reale dello schema con `grep -n "organizer_url" -B 20 backend/app/schemas.py | grep class` e correggilo se non è `PipelineOut`.

- [ ] **Step 2: Lanciarlo e vederlo fallire**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/backend && \
.venv/bin/python -m pytest tests/test_pipeline_senza_organizer_url.py -v
```

Atteso: 3 failed.

- [ ] **Step 3: Rimuovere lato backend**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/backend && \
grep -rn "organizer_url\|ORGANIZER_URL" app .env.example
```

Rimuovere ognuno: il campo e il `field_validator` in `core/config.py`, la riga in `schemas.py`, la chiave in `services/pipeline.py`, la voce in `.env.example`.

- [ ] **Step 4: Sostituire il link nel frontend**

In `frontend/components/dashboard/pipeline.tsx`, il blocco condizionato su `p.organizer_url` (righe ~98-101) diventa un link interno **non condizionato** — la sezione esiste sempre:

```tsx
<Link href="/organize/files" className={/* stesse classi dell'ancora precedente */}>
  {t.organize.nav.files}
</Link>
```

Usare `Link` di `next/link`, non un `<a>` con `target="_blank"`: è navigazione interna.

Poi togliere `organizer_url` da `frontend/lib/api/types.ts`.

- [ ] **Step 5: Verde, sabotaggio, suite**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/backend && \
.venv/bin/python -m pytest tests/test_pipeline_senza_organizer_url.py -v && \
.venv/bin/python -m pytest tests -q
cd ../frontend && npx tsc --noEmit && npm run lint && npm run build && npm run test:unit
```

Sabotaggio: rimetti `organizer_url: str = ""` in `core/config.py` → **il primo test deve fallire**. Ripristina e verifica `git diff` vuoto su quel file.

- [ ] **Step 6: Verificare che il link porti davvero da qualche parte**

Non basta che compili: con l'app avviata, dalla dashboard il link della card pipeline deve **aprire `/organize/files`** restando nella stessa app. La lezione di F1 vale anche per un'ancora.

- [ ] **Step 7: Commit**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1 && \
git status --porcelain && git add backend frontend && \
git commit -m "feat(f6): via organizer_url, la pipeline punta alla sezione Organize"
```

---

### Task 2: I tre follow-up tecnici

**Files:**
- Modify: `backend/app/organize/services/scanner.py` (tipo di `linking`), `backend/app/services/library_index.py` (chiavi del report, progresso)
- Modify: `frontend/lib/api/types.ts` (il tipo che rispecchia `linking`)
- Test: `backend/tests/test_report_scan.py`

Tre difetti lasciati aperti e dichiarati da F4/F5, tutti nello stesso report.

**a. `ScanSummary.linking` è un dict non tipizzato** esposto in JSON con tre forme possibili (assente, `null` per uno scan ristretto all'inbox, popolato). Un `TypedDict` lo rende verificabile a compile-time da entrambe le sponde.

**b. `linking.unchanged` somma due cose sotto la stessa chiave**: `library_index.py:601` fa `report["unchanged"] += arc_report["unchanged"]`, cioè righe di libreria invariate **più** file d'archivio invariati. Finché il numero resta un contatore aggregato nella barra regge, ma è un numero che non significa una cosa sola.

**c. Il progresso non è monotono**: due `total` diversi sulla stessa callback, e una fase che non emette progresso.

- [ ] **Step 1: Scrivere i test che falliscono**

Crea `backend/tests/test_report_scan.py`:

```python
"""Il report dello scan: forma tipizzata, contatori che significano una cosa sola,
progresso che non torna indietro."""

from app.organize.services.scanner import ScanSummary


def test_linking_e_tipizzato():
    from app.organize.services.scanner import LinkingReport  # TypedDict

    campi = set(LinkingReport.__annotations__)
    assert {"created", "relinked", "unchanged", "failed"} <= campi


def test_unchanged_di_libreria_e_archivio_sono_separati(db, fake_audio, monkeypatch, tmp_path):
    """Un solo contatore per due cose diverse non e' un contatore.

    Si esercita il report VERO: un file in libreria gia' agganciato (unchanged
    di libreria) piu' un file in archivio gia' visto (unchanged d'archivio).
    Prima della correzione i due finivano sommati sotto la stessa chiave, e il
    test non poteva distinguerli — che e' esattamente il difetto."""
    from app.core.config import settings
    from app.services.library_index import collega_tracce, indicizza_archivio

    make, root = fake_audio
    monkeypatch.setattr(settings, "library_root", str(root))
    p = make("Techno/A/A - T.mp3", digest="H0", artist="A", title="T")
    # prima corsa: crea; seconda: la stessa riga risulta invariata
    collega_tracce(db)
    db.commit()
    report = collega_tracce(db)

    assert report["unchanged"] >= 1
    assert report.get("archive_unchanged", 0) == 0, (
        "l'unchanged d'archivio non deve confluire in quello di libreria"
    )
    assert p.exists()


def test_il_progresso_non_torna_indietro(db, fake_audio, monkeypatch):
    """Due total diversi sulla stessa callback facevano scendere la percentuale."""
    from app.core.config import settings
    from app.organize.services.roots import radici
    from app.organize.services.scanner import scan

    make, root = fake_audio
    monkeypatch.setattr(settings, "library_root", str(root))
    monkeypatch.setattr(settings, "slskd_download_dir", "")
    for i in range(4):
        make(f"Techno/A/A - T{i}.mp3", digest=f"H{i}", artist="A", title=f"T{i}")

    percentuali: list[float] = []

    def on_progress(processed: int, total: int, phase: str) -> None:
        if total:
            percentuali.append(processed / total)

    scan(db, [radici(db)["library"]], on_progress=on_progress)

    assert percentuali == sorted(percentuali), f"progresso non monotono: {percentuali}"
```

- [ ] **Step 2: Lanciarli e vederli fallire**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/backend && \
.venv/bin/python -m pytest tests/test_report_scan.py -v
```

Atteso: i primi due falliscono su `ImportError`; il terzo dice quale percentuale è tornata indietro — **annota la sequenza**, serve a capire quale fase la rompe.

- [ ] **Step 3: Tipizzare il report**

In `scanner.py`, accanto a `ScanSummary`:

```python
class LinkingReport(TypedDict):
    """Esito della fase 2 (aggancio tracce). `None` su ScanSummary significa
    'fase non eseguita' — uno scan ristretto all'inbox si ferma alla fase 1."""
    created: int
    relinked: int
    unchanged: int          # righe di libreria invariate
    archive_unchanged: int  # file d'archivio invariati: contatore distinto
    failed: int
    duplicates: int
    lost: int
```

e `linking: LinkingReport | None`. Rispecchiare il tipo in `frontend/lib/api/types.ts`, sostituendo il dict generico.

- [ ] **Step 4: Separare i due `unchanged`**

In `library_index.py`, la riga ~601 non somma più: assegna a una chiave propria.

```python
    report["archive_unchanged"] = arc_report["unchanged"]
```

Chi legge il totale aggregato (la barra dei job) somma esplicitamente le due chiavi, così la somma è una scelta di chi mostra, non un'ambiguità di chi conta.

- [ ] **Step 5: Rendere monotono il progresso**

I punti di chiamata sono dodici, e i `total` che si contraddicono sono questi:

| dove | `total` usato | fase |
|---|---|---|
| `scanner.py:197,221` | `summary.found` (file trovati sul disco) | `scanning` |
| `scanner.py:298` | il `total` della fase 2 (righe da agganciare) | `linking` |
| `library_index.py:270-358` | `total` della passata 1 e 2 | (nessuna, callback a 2 argomenti) |
| `library_index.py:436,457` | `total` dell'archivio | `archive` |

Quando lo scan passa da `scanning` a `linking` il denominatore cambia sotto i piedi della barra, e la percentuale scende.

La correzione minima, che **non** richiede di riscrivere le fasi: `scan()` calcola un `total` complessivo una volta sola (file da scansionare + righe da agganciare) e avvolge le callback di ogni fase in un adattatore che somma l'offset delle fasi già concluse. Le funzioni interne continuano a contare per conto proprio; è l'adattatore a tradurre.

La fase che non emette progresso (`riconcilia_possessi`) può restare muta — una fase silenziosa è accettabile, una percentuale che scende no. Ma va dichiarato con un commento accanto, altrimenti il prossimo che legge pensa a una dimenticanza.

- [ ] **Step 6: Verde, sabotaggio, suite**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/backend && \
.venv/bin/python -m pytest tests/test_report_scan.py -v && .venv/bin/python -m pytest tests -q
```

Sabotaggio: rimetti la somma `report["unchanged"] += arc_report["unchanged"]` → **il secondo test deve fallire**. E rimetti il `total` locale in una fase → **il terzo deve fallire**. Ripristina entrambi, `git diff` vuoto.

- [ ] **Step 7: Commit**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1 && \
git add backend frontend && \
git commit -m "fix(f6): report dello scan tipizzato, contatori distinti, progresso monotono"
```

---

### Task 3: `scan_root` — chiudere la decisione

**Files:**
- Modify: `backend/app/organize/models.py` (il commento di schema morto)
- Modify: `docs/superpowers/specs/2026-08-11-fusione-sortory-cratory-design.md`

F3b aveva rimandato la rimozione **di schema** a "dopo F4, se lo scanner richiederà comunque un rebuild di `audio_file`". F4 è passata e **non l'ha richiesto**.

- [ ] **Step 1: Verificare che il vincolo sia davvero immutato**

```bash
sqlite3 ~/Develop/DJProject01/backend/data/djassistant.db ".schema audio_file" | grep -E "root_id|UNIQUE|FOREIGN"
```

Atteso: `root_id INTEGER NOT NULL`, `CONSTRAINT uq_audio_root_path UNIQUE (root_id, path)`, `FOREIGN KEY(root_id) REFERENCES scan_root (id)` — identici a F3b.

- [ ] **Step 2: Registrare la decisione, non il rinvio**

Il vincolo è identico, quindi la conclusione è identica: **non si rimuove**. Ma va scritto come scelta chiusa, con la condizione che la riaprirebbe. Nel commento di schema morto in `app/organize/models.py`, sostituire il rinvio a F4 con:

```python
# SCHEMA MORTO — decisione chiusa in F6. F4 è passata senza richiedere un
# rebuild di `audio_file`, quindi il vincolo che impedisce il DROP COLUMN è
# immutato: root_id è NOT NULL, dentro uq_audio_root_path (indice interno non
# droppabile) e in una FK. Rimuoverlo richiederebbe un rebuild della tabella
# con quattro figlie (issue, dup_member, plan_op, undo_journal) — lo stesso
# rebuild che il progetto evita per tracks.
# La decisione si riapre solo se una modifica futura richiede COMUNQUE quel
# rebuild per altri motivi: in quel caso root_id e scan_root escono insieme,
# a costo marginale zero.
```

Aggiornare la nota corrispondente nella spec.

- [ ] **Step 3: Commit**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1 && \
git add backend/app/organize/models.py docs/superpowers/specs && \
git commit -m "docs(f6): scan_root resta schema morto — decisione chiusa, non rinviata"
```

---

### Task 4: La documentazione che istruisce

**Files:**
- Modify: `CLAUDE.md` (5 occorrenze), `README.md` (8), `docs/ARCHITECTURE.md` (6), `docs/ROADMAP.md` (6), `docs/DESIGN.md` (3), `docs/API.md` (2), `docs/DEPENDENCIES.md` (2)
- Modify/Delete: `docs/organize/`

**La distinzione che governa questo task**: si aggiorna ciò che **istruisce**, non ciò che **racconta**. `PROGRESS.md` e i documenti sotto `docs/superpowers/` sono datati e dicevano il vero quando sono stati scritti: **non si toccano** (li copre il Task 5).

**Le quattro regole, dopo la fusione:**

| regola | esito |
|---|---|
| "le due app non si parlano via rete, l'unica interfaccia è il disco" | **decade**: non ci sono più due app. Va rimossa, non riformulata |
| "Sortory è l'unico che scrive i tag testuali" | **resta**, con l'attore rinominato: è la sezione **Organize**. Nessun'altra parte del codice tocca i tag |
| "BPM/key: Rekordbox primario, analisi in-app alternativa deterministica" | **resta**, invariata |
| "ogni operazione sui file è prima un piano approvato, con quarantena e undo" | **resta**, invariata — ed è ora una garanzia dell'app intera, non di un'app sorella |

- [ ] **Step 1: Riscrivere `CLAUDE.md`**

È il documento che conta di più: è la guida operativa. I punti da correggere:

- il paragrafo *Project* descrive Cratory come app che delega a Sortory: ora Organize è una sua sezione;
- **regola 7** ("The library is the disk") dice *"tags are written only by Sortory"* → *"solo dalla sezione Organize"*;
- la sezione *Stack and layout* elenca i router senza `organize/`: aggiungerlo;
- *Source of truth*: aggiungere che i documenti storici di Sortory stanno in `docs/organize/`.

- [ ] **Step 2: Gli altri documenti operativi**

Per ognuno, sostituire "Sortory" con "la sezione Organize" **dove indica un attore**, e riformulare dove indica un'app separata. `docs/API.md` va controllato a parte: le sue 2 occorrenze potrebbero essere in una descrizione di endpoint, e lì conta il prefisso `/api/organize/`.

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1 && \
for f in CLAUDE.md README.md docs/ARCHITECTURE.md docs/ROADMAP.md docs/DESIGN.md docs/API.md docs/DEPENDENCIES.md; do
  echo "=== $f"; grep -n "Sortory" "$f"
done
```

**Non usare una sed globale**: le occorrenze hanno significati diversi (attore, app, nome storico) e vanno lette una per una. Sono 32 in sette file.

- [ ] **Step 3: `docs/organize/`**

Contiene quattro file portati dentro da F1: `CLAUDE-sortory-storico.md`, `README-sortory-storico.md`, `PRODUCT.md`, `DEPENDENCIES.md`.

- i due `*-storico.md` **restano** e prendono in testa una riga che dice cosa sono: la documentazione di Sortory come app autonoma, conservata per riferimento, non più operativa;
- `PRODUCT.md` va letto: se contiene contesto di prodotto ancora valido, confluisce in `docs/DESIGN.md`; altrimenti diventa storico come gli altri;
- `DEPENDENCIES.md` va **fuso** in `docs/DEPENDENCIES.md` (le dipendenze sono già unificate dalla F1) e poi rimosso.

- [ ] **Step 4: Verificare che non resti nulla che dica "due app"**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1 && \
grep -rn "Sortory" CLAUDE.md README.md docs/*.md | grep -v "docs/organize/"
```

Ogni riga rimasta deve essere una menzione **storica esplicita** (del tipo "prima della fusione…"), non un'istruzione al presente. Se una riga dice cosa fare oggi e nomina Sortory come app, non è finita.

```bash
grep -rn "porta 8010\|:8010\|djorganizer.db\|DJORG_" CLAUDE.md README.md docs/*.md | grep -v docs/organize
```

Atteso: nessun output.

- [ ] **Step 5: Commit**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1 && \
git status --porcelain && git add CLAUDE.md README.md docs && \
git commit -m "docs(f6): la documentazione operativa descrive un prodotto solo"
```

---

### Task 5: L'archivio del repo Sortory

**Files:** nessuno — è un'azione su GitHub, e la fai tu

- [ ] **Step 1: Chiudere il repo locale**

Il checkout `/Users/lucadenegri/Develop/DjOrganizer01` non serve più al lavoro quotidiano, ma **contiene il `.env` con le chiavi** che F2 ha traslocato e il `djorganizer.db` sorgente della migrazione. Non cancellarlo: verificare che i backup esistano.

```bash
ls -la ~/Backup/fusione-f2/ ~/Backup/fusione-f3a/ 2>/dev/null
```

Atteso: i `.db` pre-migrazione. Se mancano, **fermarsi**: il DB di Sortory è l'unica copia dei dati pre-fusione.

- [ ] **Step 2: Archiviare su GitHub — lo fai tu**

Su `https://github.com/lucadenegri-dev/Sortory` → Settings → Archive this repository.

**Archiviare, non cancellare**: i 320 commit sono raggiungibili da `HEAD` di Cratory grazie al subtree merge (D3), ma il repo resta il riferimento più comodo per la storia di un singolo file, dato che `git log --follow` non attraversa i merge.

Aggiungere in testa al `README.md` di quel repo una riga che rimanda a Cratory.

- [ ] **Step 3: Registrare che è fatto**

Quando l'archiviazione è avvenuta, aggiornare la riga F6 nella spec.

---

### Task 6: Verifica di fase

- [ ] **Step 1: Le suite**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/backend && .venv/bin/python -m pytest tests -q
cd ../frontend && npm run lint && npm run build && npm run test:unit && npm run test:e2e
```

Atteso: tutto verde. Riferimento post-F5: **1882** backend, **161** unit, **21** e2e.

**Se il build fallisce con `Type error: Type 'Route' does not satisfy the constraint`** in `.next/types/` o `.next-e2e/dev/types/`, non è il codice: sono i tipi generati di una rotta cancellata. `rm -rf frontend/.next frontend/.next-e2e` e ricostruire — `.next-e2e` sopravvive a un `rm -rf .next` da sola.

- [ ] **Step 2: L'app, avviata davvero**

```bash
./start-dev.sh
```

Verificare che lo script **non** avvii nulla su `:8010` (F1 l'ha già tolto, qui si conferma), e che dalla dashboard il link della card pipeline porti a `/organize/files` restando nell'app.

- [ ] **Step 3: L'ultima lettura, a mente fredda**

Aprire `CLAUDE.md` e leggerlo come se non si sapesse nulla del progetto. La domanda: **si capisce che è un prodotto solo?** Se un paragrafo lascia pensare che esista un'altra applicazione da installare o avviare, non è finita.

- [ ] **Step 4: Spuntare la spec e chiudere**

Riga **F6**: completamento, conteggio dei test, e se l'archiviazione su GitHub è avvenuta.

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1 && \
git status --porcelain && git add docs && \
git commit -m "docs(f6): F6 completata — la fusione e' chiusa"
```

- [ ] **Step 5: Riepilogo finale della fusione**

Riportare, per l'intera fusione F1→F6: fasi, conteggio finale dei test, e i follow-up che restano aperti — se ne restano, dichiarati e non dimenticati.

---

## Definizione di "F6 completa"

- Nessun `organizer_url` nel codice; il link della pipeline porta a `/organize/files` e funziona.
- `ScanSummary.linking` è tipizzato, i due `unchanged` sono contatori distinti, il progresso non torna indietro.
- `scan_root` è documentato come decisione chiusa, con la condizione che la riaprirebbe.
- `CLAUDE.md`, `README.md` e `docs/*.md` descrivono un prodotto solo; nessuna menzione di `:8010`, `djorganizer.db` o `DJORG_` fuori dai documenti storici.
- `PROGRESS.md` e `docs/superpowers/` **non** sono stati riscritti.
- Il repo Sortory è archiviato su GitHub, con un rimando a Cratory.
- Tutte le suite verdi.
