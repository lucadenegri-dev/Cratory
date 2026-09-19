# Rimozione del vecchio generatore e della curatela AI — piano di implementazione

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cratory smette di generare set interi e smette di chiamare l'AI per curarli. Restano il beam search e lo scoring delle transizioni, che ora servono «riempi il varco» e la pagina Transizioni; spariscono la curatela, il form, il job, i due endpoint di generazione, l'editor classico dei set generati e le colonne che li descrivevano.

**Architecture:** Demolizione dall'alto verso il basso: prima si staccano gli ingressi (pagine e endpoint), poi i servizi che restano senza chiamanti, poi le colonne. Ogni task lascia la suite verde, così un passo falso si vede subito e non alla fine. Il confine da difendere è uno solo: `_beam_search_span` e `_candidate_score` devono continuare a funzionare identici, perché `manual_fill.py` ci sta sopra.

**Tech Stack:** Python 3 + FastAPI + SQLAlchemy 2 (SQLite, migrazioni idempotenti in `db.py`), Pydantic v2, pytest. Next.js 16 App Router, React, Tailwind, vitest + @testing-library/react, Playwright.

**Spec:** `docs/superpowers/specs/2026-09-15-set-builder-workbench.md`, seconda metà di «Tappa 6 — Il generatore come strumento».

## Global Constraints

- Backend: `cd backend && .venv/bin/python -m pytest tests -q` deve restare verde **a ogni task**. Baseline a inizio lavoro: **2622 passed, 4 deselected**. Qui la suite *cala*: ogni task dichiara di quanto e perché.
- Frontend baseline: **652 test in 106 file**, `npx tsc --noEmit` pulito, `npm run lint` senza errori (4 warning pre-esistenti non correlati), `npm run build` verde, e2e `set-builder.spec.ts` verde (4 test).
- Migrazioni: solo dentro `ensure_schema` in `backend/app/db.py`, idempotenti. Attenzione: `_migrate_drop_legacy` è model-derived **solo per `tracks`**, quindi le colonne di `setlists`/`setlist_tracks` vanno tolte con una migrazione dedicata (Task 3). `ALTER TABLE ... DROP COLUMN`, nessun rebuild scritto a mano.
- **Il beam search non si tocca.** `_beam_search_span`, `_candidate_score`, `_desired_bpm`, `_desired_energy` e lo scoring in `services/scoring.py` restano identici: `manual_fill.py` ci sta sopra e la pagina Transizioni pure. Se un test del riempimento cambia risultato, hai tagliato troppo.
- Frontend: leggere `frontend/CLAUDE.md`. Nessuna stringa user-facing fuori dai dizionari; le chiavi che restano orfane si tolgono da `en.ts` **e** `it.ts`.
- Commit in italiano, stile `refactor(sets): …` o `feat(sets): …`, nessun `Co-Authored-By`. Prima di ogni commit `git status --porcelain`, stage dei soli file del task.
- Nessuna cancellazione di dati dell'utente da parte del codice: le colonne spariscono dallo schema, i set restano. Chi vuole cancellare un set lo cancella a mano.

## Decisioni prese con l'utente (2026-09-19)

1. **Via anche la generazione automatica**, non solo la curatela: form, job, `/generate-async`, `/generate-status`, `generate_set`, lo scheletro e gli ancoraggi. Il generatore sopravvive come *strumento dentro il set* («riempi il varco») e come *scoring* (Transizioni), non come modo di fare set.
2. **Via anche la superficie dei set generati**: pagina di dettaglio classica, comandi di modifica per posizione, alternative calcolate. L'utente cancella a mano il set generato che ha in archivio **prima** che questo lavoro venga rilasciato.

**Conseguenza da gestire, non da ignorare:** finché quel set esiste, `/sets` lo elencherebbe senza una pagina dove aprirlo. Il Task 5 lo rende esplicito — riga marcata «vecchio formato», con il solo comando per cancellarla — invece di lasciare un clic che non porta da nessuna parte. Non è una funzione nuova: è non lasciare una trappola.

## Cosa NON si tocca

`services/scoring.py` (Transizioni, compatibilità dei passaggi, `mixing_tip`), `services/gap_analysis.py`, `services/transitions`, Discovery, Organize, Shazam, il player. `integrations/llm.py` **resta**: lo usano `routers/ai.py` e `credential_tests.py`, che sono fuori da questo perimetro.

---

## File structure

| File | Cosa gli succede |
|---|---|
| `frontend/app/set-builder/page.tsx` | Da form di generazione a lista dei set con «Prepara un set» |
| `frontend/app/set-builder/guida/page.tsx` | Cancellato: spiega un flusso che non esiste più |
| `frontend/app/sets/detail/page.tsx` | Cancellato con la sua rotta |
| `frontend/app/sets/page.tsx` | Instrada solo i set a mano; i generati sono righe di sola cancellazione |
| `frontend/components/jobs-provider.tsx` | Via il poller della generazione |
| `frontend/lib/api/sets.ts`, `types.ts`, `i18n/{en,it}.ts` | Via client, tipi e testi orfani |
| `backend/app/routers/sets.py` | Via generazione, editor classico, alternative calcolate |
| `backend/app/services/ai_curation.py` | Cancellato |
| `backend/app/services/set_generator.py` | Resta il solo beam: via `generate_set`, `assign_roles`, ancoraggi |
| `backend/app/services/set_skeleton.py` | Resta `strategy_profile`; via scheletro e segmenti |
| `backend/app/services/alternatives.py` | Cancellato |
| `backend/app/services/set_editor.py` | Restano `rename_set` e `delete_set`; via il resto |
| `backend/app/services/candidate_engine.py` | Cancellato se resta senza chiamanti (verificarlo, non assumerlo) |
| `backend/app/models.py` | Via `Setlist.curation`, `SetlistTrack.mood_tags`, `SetlistTrack.ai_reason` |
| `backend/app/schemas.py` | Via `SetGenerationRequest` come corpo HTTP: diventa il parametro del beam |
| `backend/tests/*` | Cancellati quelli del generatore/curatela; alleggeriti quelli misti |
| `docs/*`, `PROGRESS.md`, `README.md`, `CLAUDE.md` | La regola 1 del progetto cambia significato: va riscritta |

---

### Task 1: Staccare gli ingressi HTTP

**Files:**
- Modify: `backend/app/routers/sets.py`
- Test: `backend/tests/test_generate_async.py` (cancellato), `backend/tests/test_set_editing*.py`, `test_set_add_track.py`, `test_job_response_schemas.py`, `test_set_builder_phase_c.py` (potati)

**Perché prima gli endpoint.** Finché un endpoint esiste, non si sa se un servizio è morto o solo silenzioso. Tolti gli ingressi, ciò che resta senza chiamanti è dimostrabilmente morto, e il Task 2 può togliere senza indovinare.

Endpoint che spariscono:

```text
POST   /api/sets/generate-async
GET    /api/sets/generate-status
GET    /api/sets/{id}                     (dettaglio classico, SetlistOut)
DELETE /api/sets/{id}/tracks/{position}
POST   /api/sets/{id}/tracks
POST   /api/sets/{id}/tracks/{position}/move
POST   /api/sets/{id}/tracks/{position}/replace
POST   /api/sets/{id}/alternatives        (le proposte calcolate del generatore)
```

Restano: `GET /api/sets` (la lista), `POST /api/sets/manual`, tutta la famiglia `/manual`, `PATCH /api/sets/{id}` (rinomina), `DELETE /api/sets/{id}`, `POST /api/sets/{id}/export`.

- [ ] **Step 1: Scrivi il test che descrive la superficie nuova**

`backend/tests/test_set_surface.py` (nuovo) — è il test che impedisce a qualcuno di rimettere in piedi il vecchio mondo per sbaglio:

```python
"""La superficie HTTP dei set dopo la rimozione del generatore (2026-09-19).

Non un test di regressione qualunque: e' l'elenco di cio' che esiste e di cio'
che NON deve tornare a esistere. Un endpoint di generazione che riappare qui si
vede subito.
"""
from app.main import app

ATTESI = {
    ("POST", "/api/sets/manual"),
    ("GET", "/api/sets"),
    ("GET", "/api/sets/{setlist_id}/manual"),
    ("GET", "/api/sets/{setlist_id}/material"),
    ("PATCH", "/api/sets/{setlist_id}"),
    ("DELETE", "/api/sets/{setlist_id}"),
    ("POST", "/api/sets/{setlist_id}/export"),
}

SPARITI = {
    ("POST", "/api/sets/generate-async"),
    ("GET", "/api/sets/generate-status"),
    ("GET", "/api/sets/{setlist_id}"),
    ("POST", "/api/sets/{setlist_id}/tracks"),
    ("DELETE", "/api/sets/{setlist_id}/tracks/{position}"),
    ("POST", "/api/sets/{setlist_id}/tracks/{position}/move"),
    ("POST", "/api/sets/{setlist_id}/tracks/{position}/replace"),
    ("POST", "/api/sets/{setlist_id}/alternatives"),
}


def _rotte() -> set[tuple[str, str]]:
    out = set()
    for r in app.routes:
        for metodo in getattr(r, "methods", set()) - {"HEAD", "OPTIONS"}:
            out.add((metodo, r.path))
    return out


def test_la_superficie_dei_set_e_quella_del_banco():
    rotte = _rotte()
    assert ATTESI <= rotte, ATTESI - rotte


def test_il_vecchio_generatore_non_ha_piu_endpoint():
    rotte = _rotte()
    assert not (SPARITI & rotte), SPARITI & rotte
```

- [ ] **Step 2: Esegui e verifica che fallisca**

Run: `cd backend && .venv/bin/python -m pytest tests/test_set_surface.py -q -p no:cacheprovider`
Expected: FAIL sul secondo test, con gli otto endpoint ancora presenti.

- [ ] **Step 3: Togli gli endpoint**

In `backend/app/routers/sets.py` cancella, con i loro import diventati orfani:

- `generate_async`, `generate_status`, la funzione di job che chiama `run_curated_generation`/`generate_set` e lo stato globale del job;
- `get_one` (il `GET /{setlist_id}` con `SetlistOut`), insieme a `_require_generated`, che esisteva solo per difendere quelle rotte;
- `tracks_remove`, `tracks_add`, `tracks_move`, `tracks_replace`;
- `alternatives` (quello del generatore, `POST /{setlist_id}/alternatives`) — **attenzione a non toccare** `POST /{setlist_id}/rows/{row_id}/alternatives`, che è delle candidate del DJ ed è tutt'altra cosa.

Nell'export, il ramo `if setlist.kind == "manual"` resta e quello dei set generati **resta anche lui**: un set generato ancora in archivio deve potersi esportare prima di essere cancellato. Togli invece la riga `_require_generated(setlist)` e sostituiscila con niente: senza quella funzione, il ramo generato è semplicemente l'`else`.

- [ ] **Step 4: Pota i test che esercitavano quegli endpoint**

Cancella `backend/tests/test_generate_async.py` (3 test: erano il job).

In `test_set_editing.py`, `test_set_editing_owned.py`, `test_set_editing_roles.py`, `test_set_add_track.py`, `test_set_builder_phase_c.py`, `test_job_response_schemas.py`: togli i test che chiamano gli endpoint spariti. **Non cancellare i file interi senza guardarli**: alcuni contengono anche test di cose che restano (l'export, la rinomina, la cancellazione, lo scoring). Per ciascuno, apri il file e decidi test per test.

Regola per decidere: se il test esercita *solo* un endpoint sparito, va via col suo endpoint; se esercita una funzione che resta, resta anche lui.

- [ ] **Step 5: Esegui, dichiara il calo, commit**

Run: `cd backend && .venv/bin/python -m pytest tests -q -p no:cacheprovider` → verde. **Annota il numero**: scenderà di parecchie decine. Scrivi nel messaggio di commit quanti test sono spariti e perché, così la differenza non sembra una perdita.

```bash
git add backend/app/routers/sets.py backend/tests
git commit -m "refactor(sets): via gli endpoint di generazione e l'editor classico"
```

---

### Task 2: I servizi rimasti senza chiamanti

**Files:**
- Delete: `backend/app/services/ai_curation.py`, `backend/app/services/alternatives.py`
- Modify: `backend/app/services/set_generator.py`, `set_skeleton.py`, `set_editor.py`
- Delete/Modify: i test relativi

**Interfaces:**
- Sopravvivono, identici: `_beam_search_span`, `_candidate_score`, `_desired_bpm`, `_desired_energy`, `strategy_profile`, `StrategyProfile`, `rename_set`, `delete_set`.
- Spariscono: `generate_set`, `assign_roles`, `run_curated_generation`, `compile_intent`, `score_mood_fit`, `find_alternatives`, `build_skeleton` e gli ancoraggi, `recompute_transitions`, `_reassign_roles`, `_clear_ai_notes`, `remove_track`, `move_track`, `move_track_to`, `add_track`, `replace_track`.

- [ ] **Step 1: Verifica che siano davvero morti, non assumerlo**

Run, uno per nome:

```bash
cd backend && for n in generate_set assign_roles run_curated_generation find_alternatives select_candidates recompute_transitions add_track replace_track; do
  echo "--- $n"; grep -rn "\b$n\b" app | grep -v "def $n"; done
```

Ogni riga che compare è un chiamante vivo: o è dentro un file che stai per cancellare, o è un problema. `select_candidates` merita un occhio in più: se dopo il taglio non lo usa più nessuno, `candidate_engine.py` va cancellato; se lo usa qualcuno fuori perimetro, resta.

- [ ] **Step 2: Cancella e pota**

```bash
git rm backend/app/services/ai_curation.py backend/app/services/alternatives.py
git rm backend/tests/test_ai_curation.py backend/tests/test_curated_generation.py backend/tests/test_ai_candidate_ranking.py
```

In `set_generator.py`: resta il blocco del beam e i suoi helper di scoring. Vanno via `generate_set`, `assign_roles`, la costruzione dello scheletro e tutto ciò che serviva solo a loro. **Rileggi il file dopo il taglio**: se un helper è rimasto senza chiamanti, va via anche lui; se uno serve al beam, resta.

In `set_skeleton.py`: restano `StrategyProfile`, `_STRATEGY_PROFILES`, `strategy_profile`. Il resto (scheletro, ancoraggi, segmenti, riserve) va via. Se quello che resta sta in venti righe, valuta di portarlo dentro `set_generator.py` e cancellare il file — ma solo se l'import in `manual_fill.py` resta leggibile.

In `set_editor.py`: restano `_require`, `rename_set`, `delete_set`. Tutto il resto va via.

- [ ] **Step 3: Esegui**

Run: `cd backend && .venv/bin/python -m pytest tests -q -p no:cacheprovider` → verde.

**Il test che conta davvero qui** è `tests/test_set_manual_fill.py`: se «riempi il varco» resta verde, il beam è intatto. Se cambia risultato, hai tagliato un pezzo che serviva.

- [ ] **Step 4: Commit**

```bash
git add -A backend/app backend/tests
git commit -m "refactor(sets): via la curatela AI, il generatore di set e l'editor classico"
```

---

### Task 3: Le colonne

**Files:**
- Modify: `backend/app/models.py`, `backend/app/schemas.py`, `backend/app/serializers.py`, `backend/app/db.py` (solo se serve)
- Test: `backend/tests/test_curation_columns.py` (cancellato), `backend/tests/test_set_manual_schema.py` (verificato)

**Interfaces:**
- Spariscono dal modello: `Setlist.curation`, `SetlistTrack.mood_tags`, `SetlistTrack.ai_reason`.
- Restano: `Setlist.prompt`, `strategy`, `global_explanation`, `generated_by`, `validation`, `target_duration_minutes`, `start_bpm`, `end_bpm`, `owned_only` — **non** perché servano, ma perché sono dati dei set generati che l'utente ha ancora in archivio, e questo lavoro non cancella dati. Vanno via quando i set generati vanno via.

**`_migrate_drop_legacy` NON basta, e sapere perché è il punto di questo task.** È model-derived, sì, ma **solo per la tabella `tracks`**: legge `PRAGMA table_info(tracks)` e confronta con `Track.__table__.columns` (`db.py`, riga ~224). Su `setlists` e `setlist_tracks` non passa. Togliere le colonne dal modello le farebbe sparire dai DB *nuovi* e le lascerebbe per sempre in quello di chi aggiorna: colonne morte che nessuno legge e che nessuno sa più perché ci sono.

Serve quindi una migrazione esplicita, una tantum, che le droppi da quelle due tabelle. Esplicita e non generalizzata: una funzione che dice per nome cosa distrugge è la cosa giusta per una migrazione distruttiva, molto più di un meccanismo furbo che un domani potrebbe droppare una colonna che qualcuno voleva tenere.

- [ ] **Step 1: Scrivi il test che falliscono**

`backend/tests/test_set_surface.py`, in coda:

```python
def test_le_colonne_della_curatela_non_esistono_piu(db):
    from app.models import Setlist, SetlistTrack
    assert not hasattr(Setlist, "curation")
    assert not hasattr(SetlistTrack, "mood_tags")
    assert not hasattr(SetlistTrack, "ai_reason")


def test_un_database_vecchio_perde_le_colonne_all_avvio(tmp_path):
    """Il DB di chi aggiorna deve ritrovarsi senza quelle colonne. Si parte
    dallo schema CORRENTE e si ri-aggiungono a mano le tre colonne morte: e'
    esattamente la forma che ha il database di chi installa l'aggiornamento."""
    from sqlalchemy import create_engine, inspect, text

    from app.db import Base, ensure_schema
    import app.models  # noqa: F401
    import app.organize.models  # noqa: F401

    path = tmp_path / "vecchio.db"
    eng = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(eng)
    with eng.begin() as conn:
        conn.execute(text("ALTER TABLE setlists ADD COLUMN curation JSON"))
        conn.execute(text("ALTER TABLE setlist_tracks ADD COLUMN mood_tags JSON"))
        conn.execute(text("ALTER TABLE setlist_tracks ADD COLUMN ai_reason TEXT"))
        conn.execute(text("INSERT INTO setlists (name, kind) VALUES ('vecchio', 'generated')"))

    ensure_schema(eng)   # accetta un engine: vedi db.py riga 35

    assert "curation" not in {c["name"] for c in inspect(eng).get_columns("setlists")}
    righe = {c["name"] for c in inspect(eng).get_columns("setlist_tracks")}
    assert "mood_tags" not in righe and "ai_reason" not in righe
    # Il set c'e' ancora: si tolgono colonne, non i dati dell'utente.
    with eng.begin() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM setlists")).scalar_one() == 1


def test_la_migrazione_delle_colonne_si_puo_rieseguire(tmp_path):
    """Idempotenza: `ensure_schema` gira a ogni avvio."""
    from sqlalchemy import create_engine

    from app.db import Base, ensure_schema
    import app.models  # noqa: F401
    import app.organize.models  # noqa: F401

    eng = create_engine(f"sqlite:///{tmp_path / 'due-volte.db'}")
    Base.metadata.create_all(eng)
    ensure_schema(eng)
    ensure_schema(eng)   # non deve sollevare
```


- [ ] **Step 2: Esegui e verifica che falliscano**

Run: `cd backend && .venv/bin/python -m pytest tests/test_set_surface.py -q -p no:cacheprovider` → FAIL sui due nuovi.

- [ ] **Step 3: Togli le colonne e scrivi la migrazione**

In `backend/app/models.py`, cancella le tre colonne con i loro commenti.

In `schemas.py` e `serializers.py`, cancella i campi che le esponevano (`SetlistOut.curation`, `SetlistTrackOut.mood_tags`/`ai_reason` e simili). **`SetlistOut` NON si cancella**: lo usa ancora `PATCH /api/sets/{id}` (la rinomina), che resta. Verificalo con `grep -rn "SetlistOut" backend/app` prima di toccarlo.

In `backend/app/db.py`, accanto alle altre migrazioni:

```python
# Colonne della curatela AI, tolte col generatore (2026-09-19). Esplicite e per
# nome: una migrazione distruttiva deve dire cosa distrugge, non dedurlo.
_CURATION_COLS = {
    "setlists": ("curation",),
    "setlist_tracks": ("mood_tags", "ai_reason"),
}


def _migrate_drop_curation_cols(conn) -> None:
    """Droppa le colonne della curatela AI dai DB che le hanno ancora.

    `_migrate_drop_legacy` e' model-derived ma guarda SOLO `tracks`: senza
    questa funzione le tre colonne resterebbero per sempre nel database di chi
    aggiorna. Idempotente: ogni DROP COLUMN e' atomico e una run successiva
    trova solo cio' che resta.
    """
    for tabella, colonne in _CURATION_COLS.items():
        presenti = {r[1] for r in conn.execute(text(f"PRAGMA table_info({tabella})")).fetchall()}
        if not presenti:
            continue  # tabella non ancora creata: create_all la fara' gia' giusta
        for col in colonne:
            if col not in presenti:
                continue
            # SQLite rifiuta il DROP COLUMN su una colonna indicizzata: stesso
            # accorgimento di _migrate_drop_legacy.
            for (idx,) in conn.execute(text(
                "SELECT name FROM sqlite_master WHERE type='index' "
                f"AND tbl_name='{tabella}' AND sql IS NOT NULL"
            )).fetchall():
                coperte = {r[2] for r in conn.execute(text(f'PRAGMA index_info("{idx}")')).fetchall()}
                if col in coperte:
                    conn.execute(text(f'DROP INDEX IF EXISTS "{idx}"'))
            conn.execute(text(f'ALTER TABLE {tabella} DROP COLUMN "{col}"'))
```

e chiamala in `ensure_schema`, **dopo** `_migrate_add_model_columns` e accanto alle altre `_migrate_drop_*`.

- [ ] **Step 4: Esegui, cancella il test diventato falso, commit**

`backend/tests/test_curation_columns.py` (3 test) esercitava colonne che non esistono più: `git rm`.

Run: `cd backend && .venv/bin/python -m pytest tests -q -p no:cacheprovider` → verde.

```bash
git add -A backend
git commit -m "refactor(sets): via le colonne della curatela AI"
```

---

### Task 4: `SetGenerationRequest` non è più una richiesta

**Files:**
- Modify: `backend/app/schemas.py`, `backend/app/services/set_generator.py`, `backend/app/services/manual_fill.py`
- Test: `backend/tests/test_set_manual_fill.py`, `test_two_phase_generator.py`

**Il problema da risolvere.** `_beam_search_span` e `_candidate_score` leggono i loro parametri da un `SetGenerationRequest`: `max_tracks_per_artist`, `prefer_progressive_bpm`, `allow_sharp_changes`, `preferred_keys`, `seed_artists`, `genres`, `start_bpm`/`end_bpm`, `target_duration_minutes`, `owned_only`, `strategy`, `prompt`. Senza endpoint di generazione, quello schema non è più il corpo di nessuna richiesta HTTP: è il **parametro del beam**. Lasciarlo in `schemas.py` fra i corpi delle richieste direbbe una bugia a chi legge.

**Cosa fare:** spostarlo in `backend/app/services/set_generator.py`, rinominato `BeamParams`, con i soli campi che il beam legge davvero e i valori di default che oggi arrivano dal form. Tenere un alias non serve a nessuno: i chiamanti sono due, e questo piano li tocca entrambi.

- [ ] **Step 1: Trova i campi davvero letti**

```bash
cd backend && grep -n "req\." app/services/set_generator.py | sed 's/.*req\.\([a-z_]*\).*/\1/' | sort -u
```

L'elenco che esce è la definizione di `BeamParams`. Non aggiungere campi "per sicurezza": quelli che non compaiono non servono.

- [ ] **Step 2: Definisci `BeamParams` e cambia le firme**

In `set_generator.py`, sopra il beam:

```python
@dataclass(frozen=True)
class BeamParams:
    """I parametri del beam search. Era `SetGenerationRequest`, il corpo della
    vecchia richiesta di generazione; da quando il generatore e' solo uno
    strumento dentro il set (2026-09-19) non e' piu' il corpo di niente, e
    stare fra gli schemi HTTP avrebbe detto una bugia a chi legge.
    """

    target_duration_minutes: int = 60
    max_tracks_per_artist: int = 2
    prefer_progressive_bpm: bool = True
    allow_sharp_changes: bool = False
    preferred_keys: list[str] = field(default_factory=list)
    seed_artists: list[str] = field(default_factory=list)
    genres: list[str] = field(default_factory=list)
    strategy: str = "smooth"
    # ...e gli altri che lo Step 1 ha trovato, con gli stessi default del form.
```

Sostituisci `req: SetGenerationRequest` con `req: BeamParams` nelle firme del beam e dello scoring. In `manual_fill.py`, `SetGenerationRequest(target_duration_minutes=60)` diventa `BeamParams()`.

Cancella `SetGenerationRequest` da `schemas.py` con gli schemi che esistevano solo per la generazione (`GenerateAsyncStartOut`, `GenerateStatusOut`, `AlternativesRequest`, `AlternativesResponse`, `AlternativeOut`) — **verificando** per ciascuno che non lo usi nessun altro.

- [ ] **Step 3: Esegui**

Run: `cd backend && .venv/bin/python -m pytest tests -q -p no:cacheprovider` → verde.

I test rimasti in `test_two_phase_generator.py`, `test_engine_upgrades.py`, `test_genre_coherence.py` costruiscono `SetGenerationRequest`: vanno aggiornati a `BeamParams`. Quelli fra loro che esercitavano `generate_set` sono già spariti col Task 2; quelli che restano esercitano il beam e lo scoring, e devono restare verdi **con gli stessi risultati**.

- [ ] **Step 4: Commit**

```bash
git add -A backend
git commit -m "refactor(sets): SetGenerationRequest diventa BeamParams, parametro del beam"
```

---

### Task 5: Il frontend

**Files:**
- Rewrite: `frontend/app/set-builder/page.tsx`
- Delete: `frontend/app/set-builder/guida/page.tsx`, `frontend/app/sets/detail/page.tsx`
- Modify: `frontend/app/sets/page.tsx`, `frontend/components/jobs-provider.tsx`, `frontend/lib/api/{sets,types}.ts`, `frontend/lib/i18n/{en,it}.ts`, e ogni pagina che linkava alle rotte sparite
- Test: `frontend/tests/sets-list-kind.test.tsx`, `rotte-query-string.test.ts`, `back-link.test.ts`, più i test delle pagine cancellate

**Comportamento:**
- `/set-builder` diventa la lista dei set con «Prepara un set». Niente form, niente strategie, niente `use_ai`. Chi arrivava lì da `/playlists/detail` o `/labels/detail` ci trova la stessa cosa che trova in `/sets`: valuta se la rotta deve restare come alias o se quei link vanno puntati a `/sets` — e se la fai sparire, aggiungi un redirect, non un 404.
- `/sets` instrada un set `manual` su `/sets/manual?id=…`. Un set `generated` **non è più apribile**: la riga si marca «vecchio formato» e offre solo l'eliminazione. È il punto deciso con l'utente: meglio una riga che dice la verità di un clic che non porta da nessuna parte.
- `jobs-provider` smette di interrogare `generateStatus`: via la chiamata, via il campo dallo stato, via l'eventuale badge.
- Due chiavi nuove nei dizionari (in `en.ts` prima, poi `it.ts`), sotto `sets`: `legacyBadge` («vecchio formato» / "old format") e `legacyHint` («Creato dal vecchio generatore: si può solo esportare o eliminare.» / "Made by the old generator: you can only export or delete it."). Sono testo nuovo, non riciclato: dicono una cosa che prima non esisteva.

- [ ] **Step 1: Scrivi i test**

In `frontend/tests/sets-list-kind.test.tsx`, sostituisci il caso che apre un set generato con:

Il file ha un test solo, che oggi verifica che un set generato apra `/sets/detail`. Sostituiscilo:

```tsx
describe("lista dei set", () => {
  const dueSet = [
    { id: 1, name: "A mano", kind: "manual", strategy: null, target_duration_minutes: null, track_count: 0, total_duration_seconds: 0, generated_by: "manual", created_at: "2026-09-17T10:00:00" },
    { id: 2, name: "Generato", kind: "generated", strategy: "smooth", target_duration_minutes: 60, track_count: 12, total_duration_seconds: 3600, generated_by: "algorithmic", created_at: "2026-09-17T10:00:00" },
  ];

  it("apre i set a mano sulla loro pagina", async () => {
    listApi.apiGet.mockResolvedValue(dueSet);
    render(<SetsPage />);
    const manual = (await screen.findByText("A mano")).closest("a");
    expect(manual?.getAttribute("href")).toBe("/sets/manual?id=1");
  });

  it("un set generato non si apre più: si può solo cancellare", async () => {
    // Deciso il 2026-09-19 con l'utente: la pagina di dettaglio classica non
    // esiste piu'. Meglio una riga che dice la verita' di un clic che porta
    // a una pagina che non c'e'.
    listApi.apiGet.mockResolvedValue(dueSet);
    render(<SetsPage />);
    await screen.findByText("Generato");
    expect(screen.getByText("Generato").closest("a")).toBeNull();
    expect(screen.getByText(/vecchio formato/i)).toBeTruthy();
    expect(screen.getByTitle(/Elimina/i)).toBeTruthy();
  });
});
```

In `frontend/tests/rotte-query-string.test.ts` e `back-link.test.ts`: togli le rotte sparite dalle tabelle. Sono test che elencano rotte, quindi si aggiornano cancellando righe.

- [ ] **Step 2: Esegui e verifica che falliscano**

Run: `cd frontend && npx vitest run tests/sets-list-kind.test.tsx`

- [ ] **Step 3: Riscrivi e cancella**

```bash
cd frontend
git rm app/set-builder/guida/page.tsx
git rm -r app/sets/detail
```

Riscrivi `app/set-builder/page.tsx`: lista dei set + «Prepara un set», riusando i componenti di `app/sets/page.tsx` invece di duplicarli. Se a fine lavoro le due pagine fanno la stessa cosa, **dillo e proponi di tenerne una sola con un redirect** invece di lasciarne due identiche.

Togli da `lib/api/sets.ts` le funzioni orfane (`generateStatus`, `generateAsync`, `addTrackToSet`, `moveTrack`, `replaceTrack`, `removeTrack`, le alternative calcolate), da `lib/api/types.ts` i tipi che restano senza uso (`GenStatus`, `Setlist` se davvero non lo legge più nessuno), e dai due dizionari le chiavi orfane.

**Sulle chiavi i18n**: `npx tsc --noEmit` non segnala una chiave inutilizzata. Trovale con un grep per nome, una per una; e se una chiave la usa ancora qualcuno, resta.

- [ ] **Step 4: Verifica**

Run: `cd frontend && npx tsc --noEmit && npm run lint && npm run test:unit && npm run build`, poi `npm run test:e2e`.

**Attenzione al build**: una pagina cancellata a cui qualcuno linka ancora non rompe il build di Next, rompe l'esperienza. Cerca i riferimenti rimasti con `grep -rn "sets/detail\|set-builder/guida" app components lib` e sistemali tutti.

- [ ] **Step 5: Commit**

```bash
git add -A frontend
git commit -m "feat(frontend): il set builder è la lista dei set, via il vecchio form"
```

---

### Task 6: La documentazione, e la regola che cambia

**Files:**
- Modify: `CLAUDE.md`, `README.md`, `docs/ARCHITECTURE.md`, `docs/API.md`, `docs/ROADMAP.md`, `PROGRESS.md`, `docs/DESIGN.md` (se nomina il flusso)

**Questo non è il solito task di documentazione.** La **regola 1** del progetto dice oggi: «L'AI interpreta l'intento, cura il pool e racconta — mai sequenzia: il motore deterministico costruisce sempre la tracklist». Dopo questo lavoro l'AI non fa più niente di tutto questo sui set: la regola va riscritta, non ritoccata. Il perimetro che resta all'AI in Cratory è fuori dai set (Organize, i suggerimenti, ciò che `routers/ai.py` espone).

- [ ] **Step 1: `CLAUDE.md`**

Riscrivi la regola 1 dicendo cosa è vero adesso: i set si preparano a mano, il motore deterministico è uno strumento dentro il set («riempi il varco») e lo scoring delle transizioni, e sui set non c'è AI. Aggiorna l'elenco dei router e dei servizi nella mappa dei layer, togliendo quelli spariti.

- [ ] **Step 2: `README.md` e `docs/DESIGN.md`**

Cerca ogni frase che promette la generazione di set (`grep -rn -i "genera\|generation\|curation\|use_ai" README.md docs/DESIGN.md`) e riscrivila. Il README è la vetrina: se dice che l'app genera set, mente.

- [ ] **Step 3: `docs/API.md` e `docs/ARCHITECTURE.md`**

Via le sezioni degli endpoint spariti; la sezione del generatore diventa la descrizione di ciò che resta (beam come strumento, scoring). In `ARCHITECTURE.md` spiega **perché** il beam è sopravvissuto alla rimozione del generatore: è il motore di «riempi il varco», non un residuo.

- [ ] **Step 4: `docs/ROADMAP.md` e `PROGRESS.md`**

La voce 3 del backlog si chiude: tutta la spec è fatta. Nel `PROGRESS.md`, una voce datata che dice cosa è sparito e, soprattutto, **cosa fare del set generato eventualmente ancora in archivio**.

- [ ] **Step 5: Verifica finale**

```bash
cd backend && .venv/bin/python -m pytest tests -q
```

```bash
cd frontend && npm run lint && npm run test:unit && npm run build && npm run test:e2e
```

- [ ] **Step 6: Commit**

```bash
git add -A docs PROGRESS.md README.md CLAUDE.md
git commit -m "docs: i set si preparano a mano, il generatore è uno strumento"
```
