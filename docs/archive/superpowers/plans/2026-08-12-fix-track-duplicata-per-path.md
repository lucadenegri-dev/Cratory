# Fix: `Track` duplicata per un path già posseduto — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Chiudere la causa della regressione trovata a fine F3b — l'indicizzazione libreria conia una `Track` nuova per un file che un'altra `Track` già rivendica — e riscrivere l'invariante di F3a che avrebbe dovuto prenderla e non poteva.

**Architecture:** `_find_track` guadagna un ramo sul `local_path`, in testa all'ordine di affidabilità, così la passata 2 dell'indicizzazione concorda con la passata 1 — che il path lo usa già. Poi si rifonde la traccia duplicata sui dati reali con lo strumento di F3a.

**Tech Stack:** Python 3.11.15, SQLAlchemy 2, SQLite, pytest.

**Prerequisito:** F3b completa su `feat/fusione-f1`.

**Da fare prima di F4**, che riscrive proprio questo codice: entrarci con una causa nota e non chiusa significa portarsela dentro la riscrittura.

## Il difetto, per intero

`library_index.py:240`, passata 1:

```python
known = db.scalar(select(Track).where(Track.local_path == resolved))
if (known is not None and known.local_mtime == stat.st_mtime
        and known.local_size == stat.st_size):
    ...  # fast-path: file invariato, niente ri-hash
```

La ricerca per path **esiste già**, ma serve solo da scorciatoia: se mtime o size sono cambiati si scende alla passata 2, e `known` viene buttato. La passata 2 chiama `_find_track(db, digest=…, tags=…)`, che il path non lo guarda.

La catena osservata sui dati reali:

1. Un Apply di Organize ritagga il file → **mtime e size cambiano**.
2. Indicizzazione: `known` trova la traccia, mtime/size non combaciano → scorciatoia saltata.
3. `audio_hash` ricalcolato: `dae6bd75…` contro il `c59683f0…` memorizzato sulla traccia → miss.
4. ISRC: il file non porta il tag ISRC → miss, benché la traccia abbia `BEZ350900033`.
5. Rami per nome: escludono di proposito le tracce che possiedono già un file → la traccia è fuori.
6. Si conia una `Track` `local_files` per il path che al passo 2 era già stato identificato.

Il grilletto è **l'Apply di Organize**: prima della fusione le due app scrivevano su database separati, ora il retag di una invalida il fast-path dell'altra. Non è un difetto introdotto da F3a o F3b — è preesistente in Cratory — ma la fusione lo rende raggiungibile di routine, ed è l'invariante di F3a ad averlo fatto emergere.

## Global Constraints

- Worktree **`.claude/worktrees/fusione-f1`**, branch `feat/fusione-f1`.
- **Commit senza `Co-Authored-By`.** Prima di ogni commit: `git status --porcelain` e `git branch --show-current`.
- **Ogni asserzione va provata rompendo il codice.** È il quarto controllo vacuo di questa fusione: nessun test di questo piano si dichiara verde senza aver visto il rosso corrispondente.
- Gli strumenti che toccano il DB stampano su quale DB stanno lavorando.

---

### Task 1: `_find_track` riconosce il path già posseduto

**Files:**
- Modify: `backend/app/services/library_index.py` (`_find_track` riga ~72, chiamante riga ~291)
- Test: `backend/tests/test_library_index.py` (un test nuovo)

**Interfaces:**
- `_find_track(db, *, digest: str, tags: dict, path: str) -> tuple[Track | None, str]` — il parametro `path` è nuovo e obbligatorio; il secondo elemento può ora valere `"path"`

- [ ] **Step 1: Scrivere il test di regressione**

In `backend/tests/test_library_index.py`, accanto agli altri, usando la fixture `fake_audio` già presente:

```python
def test_non_conia_una_track_per_un_path_gia_posseduto(db, fake_audio):
    """Regressione (fine F3b): un Apply di Organize cambia mtime e size, quindi
    il fast-path della passata 1 salta; l'hash ricalcolato non combacia più con
    quello memorizzato, il file non porta l'ISRC e i rami per nome escludono le
    tracce già possedute. Prima del fix si coniava una Track local_files per un
    path che un'altra Track rivendicava già."""
    from sqlalchemy import select

    from app.models import Track
    from app.services.library_index import index_library

    make, root = fake_audio
    p = make("Trance/R/R - Aqua Viva.mp3", digest="H_NUOVO", artist="R", title="Aqua Viva")
    t = Track(source_type="spotify", spotify_id="s1", isrc="BEZ350900033",
              artist="R", title="Aqua Viva", has_local_file=True,
              local_path=str(p.resolve()), audio_hash="H_VECCHIO")
    db.add(t)
    db.commit()

    report = index_library(db, root=root)

    assert report["created"] == 0
    assert len(db.scalars(select(Track)).all()) == 1
    db.refresh(t)
    assert t.audio_hash == "H_NUOVO"      # l'identità audio si aggiorna
    assert t.primary_file_id is None or t.has_local_file is True
```

`local_mtime` e `local_size` restano `None` sulla traccia, quindi il fast-path della passata 1 salta da solo: la condizione del bug si riproduce senza forzature.

- [ ] **Step 2: Lanciarlo e vederlo fallire**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/backend && \
.venv/bin/python -m pytest tests/test_library_index.py::test_non_conia_una_track_per_un_path_gia_posseduto -v
```

Atteso: FAIL con `report["created"] == 1` e due `Track` in tabella. **Se passa già, fermati**: il difetto non è quello descritto e il resto del piano non si applica.

- [ ] **Step 3: Aggiungere il ramo sul path**

In `_find_track` (riga ~72), la firma prende `path: str` e il primo controllo diventa:

```python
def _find_track(db: Session, *, digest: str, tags: dict, path: str) -> tuple[Track | None, str]:
    """Match nell'ordine di affidabilità. Ritorna (track, come)."""
    # Il path per primo: se una Track rivendica già QUESTO file, è quella. La
    # passata 1 usa lo stesso criterio per il fast-path (riga ~240) e lo scarta
    # appena mtime/size cambiano — cioè dopo ogni Apply di Organize; senza
    # questo ramo la passata 2 conia un doppione per un path già identificato.
    # Sta prima dell'hash di proposito: l'hash identifica l'AUDIO e sopravvive a
    # uno spostamento, il path identifica QUESTO file. Quando i due dissentono
    # (audio uguale a un'altra traccia, file già rivendicato) vince il path,
    # perché è l'unica delle due letture che non crea un secondo proprietario
    # dello stesso local_path.
    hit = db.scalar(select(Track).where(Track.local_path == path,
                                        Track.has_local_file.is_(True)))
    if hit:
        return hit, "path"
    hit = db.scalar(select(Track).where(Track.audio_hash == digest))
    if hit:
        return hit, "hash"
    ...  # il resto invariato
```

- [ ] **Step 4: Adeguare il chiamante**

Riga ~291:

```python
        track, how = _find_track(db, digest=digest, tags=tags, path=str(path.resolve()))
```

`how` oggi è assegnato e mai letto: lasciarlo com'è, non è compito di questo fix.

- [ ] **Step 5: Verificare che il test passi e che sappia fallire**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/backend && \
.venv/bin/python -m pytest tests/test_library_index.py::test_non_conia_una_track_per_un_path_gia_posseduto -v
```

Atteso: PASS.

Poi la prova che non è vacuo — commenta temporaneamente il ramo `path` appena aggiunto e rilancia:

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/backend && \
.venv/bin/python -m pytest tests/test_library_index.py::test_non_conia_una_track_per_un_path_gia_posseduto -v
```

Atteso: **FAIL**. Poi ripristina. Senza questo giro il test non conta come verificato.

- [ ] **Step 6: Suite completa**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/backend && .venv/bin/python -m pytest tests -q
```

Atteso: verde. Attenzione ai test che chiamavano `_find_track` direttamente: la firma è cambiata.

**Un test merita un secondo sguardo**: `test_riaggancio_per_audio_hash` semina `local_path="/vecchio/inbox/file.mp3"` e il file nuovo sta altrove, quindi il ramo `path` non scatta e il ramo `hash` resta quello esercitato. È il comportamento voluto — il riaggancio di un file spostato passa ancora dall'hash — ma verificalo invece di darlo per scontato.

- [ ] **Step 7: Commit**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1 && \
git add backend/app/services/library_index.py backend/tests/test_library_index.py && \
git commit -m "fix: l'indicizzazione non conia una Track per un path gia posseduto"
```

---

### Task 2: L'invariante di F3a riscritto perché sappia fallire

**Files:**
- Modify: `backend/tests/test_invarianti_libreria.py`

**Il difetto del test attuale.** `test_nessuna_traccia_condivide_il_local_path` semina due tracce con path **diversi** e poi verifica che non esistano duplicati. Non può fallire: nessuna modifica al codice di produzione lo farebbe diventare rosso. Era stato scritto per proteggere esattamente l'invariante che poi è regredito.

Un invariante si protegge in due modi, e servono entrambi: una query che sappia **riconoscere** il caso cattivo quando c'è, e un test che verifichi che il **codice** non lo produca.

- [ ] **Step 1: Riscrivere il file**

Sostituire il contenuto di `backend/tests/test_invarianti_libreria.py` con:

```python
"""Invarianti della libreria che il modello Track 1─N AudioFile dà per scontati."""

from sqlalchemy import func, select

from app.models import Track


def _duplicati_per_path(db) -> list:
    """Il rilevatore. Tenuto separato dai test perché entrambi lo usano: uno
    verifica che sappia vedere il caso cattivo, l'altro che il codice non lo crei."""
    return db.execute(
        select(Track.local_path, func.count())
        .where(Track.has_local_file.is_(True), Track.local_path.is_not(None))
        .group_by(Track.local_path)
        .having(func.count() > 1)
    ).all()


def test_il_rilevatore_vede_un_duplicato_quando_c_e(db):
    """Prima di fidarsi del rilevatore, verificare che sappia dire di no.
    La versione precedente di questo file seminava due path DIVERSI e poi
    asseriva l'assenza di duplicati: non poteva fallire."""
    db.add_all([
        Track(source_type="spotify", has_local_file=True, local_path="/lib/a.flac"),
        Track(source_type="local_files", has_local_file=True, local_path="/lib/a.flac"),
    ])
    db.commit()

    doppi = _duplicati_per_path(db)
    assert len(doppi) == 1
    assert doppi[0][0] == "/lib/a.flac"


def test_l_indicizzazione_non_crea_un_duplicato_per_path(db, fake_audio):
    """L'invariante vero: non che i duplicati si vedano, ma che il codice non
    li produca. Stesse condizioni della regressione di fine F3b — traccia
    posseduta, file con hash diverso, nessun ISRC nei tag."""
    from app.services.library_index import index_library

    make, root = fake_audio
    p = make("Trance/R/R - Aqua Viva.mp3", digest="H_NUOVO", artist="R", title="Aqua Viva")
    db.add(Track(source_type="spotify", spotify_id="s1", artist="R", title="Aqua Viva",
                 has_local_file=True, local_path=str(p.resolve()), audio_hash="H_VECCHIO"))
    db.commit()

    index_library(db, root=root)

    assert _duplicati_per_path(db) == []
```

La fixture `fake_audio` vive in `tests/test_library_index.py`: spostala in `tests/conftest.py` per renderla condivisa, oppure importala. **Spostarla è meglio** — la userà anche F4.

- [ ] **Step 2: Provare che entrambi sappiano fallire**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/backend && \
.venv/bin/python -m pytest tests/test_invarianti_libreria.py -v
```

Atteso: 2 passed.

Poi, uno alla volta:

- cambia il `having(func.count() > 1)` in `> 99` → **il primo test deve fallire**;
- commenta il ramo `path` del Task 1 → **il secondo test deve fallire**.

Ripristina dopo ciascuna prova. Un invariante che non si è visto fallire non è un invariante.

- [ ] **Step 3: Commit**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1 && \
git add backend/tests && \
git commit -m "test: l'invariante sui path duplicati sa fallire (prima era vacuo)"
```

---

### Task 3: Rifondere la traccia duplicata sui dati reali

**Files:** nessuno — è un'esecuzione

- [ ] **Step 1: Backup**

```bash
mkdir -p ~/Backup/fix-duplicati && \
cp ~/Develop/DJProject01/backend/data/djassistant.db ~/Backup/fix-duplicati/djassistant-pre-fix.db && \
ls -la ~/Backup/fix-duplicati/
```

- [ ] **Step 2: Elencare**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/backend && \
.venv/bin/python -m app.tools.merge_duplicate_tracks --db ~/Develop/DJProject01/backend/data/djassistant.db --elenca
```

Atteso: una riga sola, il path di *Aqua Viva* con le tracce `[150, 1197]`. Verifica che lo strumento stampi **su quale DB** sta lavorando: è la correzione aggiunta in F3a.

- [ ] **Step 3: Scegliere quale tenere**

Si tiene **150**: ha `spotify_id`, ISRC e `bpm_source=rekordbox`. La **1197** è la riga coniata dal difetto — `source_type=local_files`, nessuna identità, nessun BPM.

```bash
sqlite3 ~/Develop/DJProject01/backend/data/djassistant.db "
select id, source_type, spotify_id, isrc, bpm_source, rating,
  (select count(*) from playlist_tracks pt where pt.track_id=tracks.id) as playlist
from tracks where id in (150, 1197);"
```

**Se la 1197 avesse membership di playlist o un rating**, la fusione le sposta comunque su 150 — ma guardale prima, così sai cosa aspettarti dopo.

- [ ] **Step 4: Fondere**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/backend && \
.venv/bin/python -m app.tools.merge_duplicate_tracks --db ~/Develop/DJProject01/backend/data/djassistant.db --tenere 150 --scartare 1197 --apply
```

- [ ] **Step 5: Riallineare l'aggancio e verificare gli invarianti**

La fusione cancella la 1197, ma `audio_file.1260.track_id` puntava a lei. Riallinea:

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/backend && \
.venv/bin/python -c "
from app.db import SessionLocal, engine
from app.models import Track
from app.organize.services.file_link import aggiorna_primary
print('DB:', engine.url)
with SessionLocal() as db:
    t = db.get(Track, 150)
    aggiorna_primary(db, t)
    db.commit()
    print('traccia 150 -> primary_file_id', t.primary_file_id)
"
```

Poi gli invarianti:

```bash
sqlite3 ~/Develop/DJProject01/backend/data/djassistant.db "
select 'asimmetrie', count(*) from tracks t where t.primary_file_id is not null
    and not exists (select 1 from audio_file f where f.id=t.primary_file_id and f.track_id=t.id)
union all select 'primary orfani', count(*) from tracks t where t.primary_file_id is not null
    and not exists (select 1 from audio_file f where f.id=t.primary_file_id)
union all select 'track_id orfani', count(*) from audio_file f where f.track_id is not null
    and not exists (select 1 from tracks t where t.id=f.track_id)
union all select 'duplicati per path', count(*) from
    (select local_path from tracks where has_local_file=1 and local_path is not null
     group by local_path having count(*)>1);"
```

Atteso: **tutti 0**.

- [ ] **Step 6: La prova che la causa è chiusa**

Rilancia l'indicizzazione libreria sul DB vero e ricontrolla gli stessi quattro invarianti.

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/backend && \
.venv/bin/python -c "
from app.core.config import settings
from app.db import SessionLocal, engine
from app.services.library_index import index_library
print('DB:', engine.url, '| root:', settings.library_root)
with SessionLocal() as db:
    r = index_library(db, root=settings.library_root)
    db.commit()
    print({k: r[k] for k in ('created', 'relinked', 'unchanged') if k in r})
"
```

Atteso: `created: 0` — nessuna traccia nuova su una libreria già indicizzata — e i quattro invarianti ancora tutti a 0. Prima del fix era proprio questa corsa a produrre la 1197.

- [ ] **Step 7: Commit del riepilogo**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1 && \
git status --porcelain && git add -A docs && \
git commit -m "docs: chiusa la causa della Track duplicata per path"
```

---

## Definizione di "fix completo"

- `_find_track` guarda il `local_path` prima dell'hash, con la motivazione scritta accanto.
- Il test di regressione esiste, e lo si è visto fallire senza il fix.
- `test_invarianti_libreria.py` ha due test — il rilevatore sa vedere un duplicato, il codice non lo produce — ed entrambi si sono visti fallire.
- Sul DB reale: zero duplicati per path, zero asimmetrie, zero orfani nelle due direzioni.
- Una nuova indicizzazione della libreria non crea tracce e non rompe gli invarianti.
