# Dig ridisegnato: semi multipli, simili in barra, Discogs opzionale — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** La pagina Dig scava per più semi insieme (unione), offre i simili dalla stessa barra con una ricerca traccia, permette di spegnere Discogs dalle impostazioni, e i simili smettono di collassare a due lead.

**Architecture:** Il motore `dig()` prende una lista di `Seed` e fonde le pile con un budget di 300 item diviso fra i semi; il contratto HTTP passa da `seed_type/value` a `seeds[]` con `piles[]` per seme. Nel frontend la barra diventa un componente-cornice con due modi (`seeds` | `track`) che delega a un selettore di semi a chip (con tavolozza) e a una ricerca traccia; la modalità è stato locale, l'URL si muove solo quando parte una ricerca. Una preferenza in `AppState` nasconde Discogs dalla barra senza toccare il backend.

**Tech Stack:** Python 3 / FastAPI / SQLAlchemy / Pydantic (backend, pytest); Next.js 16 App Router / React / Tailwind (frontend, Vitest + Testing Library).

**Spec:** `docs/superpowers/specs/2026-09-06-dig-semi-multipli-e-simili-design.md`

## Global Constraints

- Budget di uno scavo: **300 item totali** (`WINDOW_ITEMS`), diviso per il numero di semi (`WINDOW_ITEMS // len(seeds)`), mai moltiplicato.
- Cap semi per scavo: **4** (`MAX_SEEDS`). Oltre → `422` in HTTP, `ValueError` nel motore.
- Semi misti (genere + etichetta insieme) sono legittimi; il peso `label` si azzera solo se **tutti** i semi sono etichette.
- Preferenza Discogs: chiave `AppState` `discovery.discogs_enabled`, valori `"1"`/`"0"`, **default acceso**; il backend resta permissivo (nessun rifiuto su `source=discogs`).
- Non toccare `backend/app/organize/` né il token Discogs in Servizi esterni.
- Nei simili: cap per artista esente per i lead raggiunti da `same_artist`; i conteggi degli archi si calcolano sui lead **selezionati**.
- URL della pagina: `?seeds=<type>:<value>,<type>:<value>&depth=&source=`; `:` e `,` codificati **dentro il valore** con `encodeURIComponent`; il parser splitta sul primo `:` e scarta tipi che non siano `genre`/`label`.
- Testi utente in entrambi i dizionari (`frontend/lib/i18n/it.ts` e `en.ts`): `Dictionary = typeof en`, quindi ogni chiave nuova va prima in `en.ts` o `tsc` fallisce.
- Commit: **niente `Co-Authored-By`**. Prima di ogni commit: `git status --porcelain` e stage solo dei file del task (altre sessioni lavorano sullo stesso checkout).
- Comandi: backend `cd backend && source .venv/bin/activate && python -m pytest tests/<file> -q`; frontend `cd frontend && npx vitest run tests/<file>` e `npx tsc --noEmit`.
- Frontend: Next.js 16 ha rotture rispetto alle versioni note — la pagina usa solo `useRouter/usePathname/useSearchParams` da `next/navigation` e `Link`, già presenti; non introdurre altre API di routing.

---

## File map

**Backend — modificati**
- `backend/app/repositories.py` — `_apply_track_filters(q=…)`: OR su artista/titolo.
- `backend/app/routers/tracks.py` — parametro `q` su `GET /api/tracks`.
- `backend/app/services/app_state.py` — `DISCOGS_ENABLED_KEY`, `get_discogs_enabled`.
- `backend/app/routers/settings.py` — `GET/PUT /api/settings/discovery`.
- `backend/app/services/discovery_dig.py` — `MAX_SEEDS`, `_budget`, `_window(budget)`, `_styles_beyond_seed(set)`, `_dominant_type`, `_sort_by_score`, `_cap_per_artist(exempt)`, `PileInfo`, `DigResult(seeds, piles)`, `dig(seeds=…)`.
- `backend/app/services/discovery_similar.py` — esenzione dell'arco artista dal cap; conteggi sui selezionati.
- `backend/app/schemas.py` — `DiscoverySeedIn`, `DiscoveryPileOut`, `DiscoveryDigRequest/Response` nuovi.
- `backend/app/routers/discovery.py` — `dig_endpoint` sul contratto nuovo.
- `backend/tests/test_discovery_dig.py`, `test_discovery.py`, `test_discovery_router_http.py`, `test_discovery_similar.py` — aggiornati.
- `docs/API.md` — sezioni dig, similar, tracks, settings.

**Backend — creati**
- `backend/tests/test_tracks_q_filter.py`
- `backend/tests/test_settings_discovery_router.py`

**Frontend — creati**
- `frontend/lib/discovery-seeds.ts` — vocabolario dei semi: tipo, chiave, codifica URL, add/remove.
- `frontend/components/discovery-seed-picker.tsx` — chip + combobox + tavolozza.
- `frontend/components/discovery-track-search.tsx` — ricerca traccia della libreria.
- `frontend/components/settings/discovery-section.tsx` — interruttore Discogs.
- `frontend/tests/discovery-seeds.test.ts`, `discovery-seed-picker.test.tsx`, `discovery-track-search.test.tsx`, `settings-discovery-section.test.tsx`.

**Frontend — modificati**
- `frontend/lib/api/types.ts`, `lib/api/discovery.ts`, `lib/api/tracks.ts`, `lib/api/settings.ts`.
- `frontend/lib/discovery-surprise.ts` (+ test) — esclude una lista di valori, non uno.
- `frontend/lib/i18n/en.ts`, `it.ts`.
- `frontend/components/discovery-dig-bar.tsx` (+ test) — riscritta.
- `frontend/components/discovery-similar-header.tsx` (+ test) — perde l'interruttore.
- `frontend/app/discovery/page.tsx` (+ `tests/discovery-page-modalita.test.tsx`).
- `frontend/app/settings/page.tsx`.
- `docs/ROADMAP.md`, `PROGRESS.md`.

---

### Task 1: Lavoro zero — HEAD torna a compilare

> **Già fatto** da `14510b76` (altra sessione): `tsc` pulito. Nessuna azione.

**Files:**
- Modify: `frontend/app/discovery/page.tsx:355-362`

- [x] **Step 1: Verifica che il build sia rotto**

Run: `cd frontend && npx tsc --noEmit`
Expected: `app/discovery/page.tsx(359,11): error TS2322 ... Property 'backHref' does not exist`

- [x] **Step 2: Togli la prop dal punto di chiamata**

In `frontend/app/discovery/page.tsx`, dentro `{isSimilar && sim && simTrack && (<DiscoverySimilarHeader …>)}` elimina la riga `backHref={similarBackHref}`. `similarBackHref` resta: lo usa il `Link` in cima alla pagina.

- [x] **Step 3: Verifica**

Run: `cd frontend && npx tsc --noEmit && npx vitest run tests/discovery-page-modalita.test.tsx`
Expected: nessun errore tsc; 9 test verdi.

- [x] **Step 4: Commit**

```bash
git status --porcelain
git add frontend/app/discovery/page.tsx
git commit -m "fix(discovery): la pagina non passa più backHref all'intestazione dei simili

4ef52f7d ha tolto la prop dal componente ma non dal chiamante: tsc falliva,
i test no, perché tsc non gira nella suite Vitest."
```

---

### Task 2: `q` su `GET /api/tracks` — ricerca libera su artista e titolo

**Files:**
- Modify: `backend/app/repositories.py:94-120` (`_apply_track_filters`), riga 6 (import)
- Modify: `backend/app/routers/tracks.py:38-84`
- Create: `backend/tests/test_tracks_q_filter.py`

**Interfaces:**
- Produces: `GET /api/tracks?q=<str>` → `TrackListOut`, match `ilike %q%` su `Track.artist` **oppure** `Track.title`. Non altera `artist=`/`title=` espliciti.

- [ ] **Step 1: Scrivi il test che fallisce**

```python
# backend/tests/test_tracks_q_filter.py
"""GET /api/tracks?q=: un campo solo che cerca su artista O titolo.

Serve alla ricerca traccia della barra del Dig, che ha un campo di testo e
non due. `artist=` e `title=` restano separati e restrittivi."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app
from app.models import Track


@pytest.fixture()
def client_db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    app.dependency_overrides[get_db] = lambda: session
    try:
        yield TestClient(app), session
    finally:
        app.dependency_overrides.pop(get_db, None)
        session.close()


def _tr(db, artist, title):
    t = Track(source_type="local_files", platform="local_files", artist=artist, title=title)
    db.add(t)
    db.flush()
    return t


def _titles(r):
    return sorted(t["title"] for t in r.json()["items"])


def test_q_cerca_su_artista_o_titolo(client_db):
    client, db = client_db
    _tr(db, "Jasmín", "Bite The Hand")
    _tr(db, "Pearson Sound", "Jasmine Tea")      # il titolo contiene la query
    _tr(db, "Objekt", "Theme From Q")
    db.commit()

    r = client.get("/api/tracks", params={"q": "jasm"})
    assert r.status_code == 200
    assert _titles(r) == ["Bite The Hand", "Jasmine Tea"]


def test_q_non_interferisce_con_artist_esplicito(client_db):
    client, db = client_db
    _tr(db, "Jasmín", "Bite The Hand")
    _tr(db, "Pearson Sound", "Jasmine Tea")
    db.commit()

    # `artist=` resta un filtro a sé: la riga con "jasm" solo nel titolo non passa.
    r = client.get("/api/tracks", params={"q": "jasm", "artist": "Pearson"})
    assert _titles(r) == []
    r = client.get("/api/tracks", params={"artist": "Pearson"})
    assert _titles(r) == ["Jasmine Tea"]


def test_q_vuoto_non_filtra(client_db):
    client, db = client_db
    _tr(db, "A", "x")
    _tr(db, "B", "y")
    db.commit()
    r = client.get("/api/tracks", params={"q": ""})
    assert _titles(r) == ["x", "y"]
```

- [ ] **Step 2: Verifica che fallisca**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_tracks_q_filter.py -q`
Expected: `test_q_cerca_su_artista_o_titolo` FAIL (`q` ignorato: tornano 3 titoli).

- [ ] **Step 3: Implementa**

In `backend/app/repositories.py`, riga 6: `from sqlalchemy import delete, func, or_, select, update`.

In `_apply_track_filters`, aggiungi il parametro dopo `title`:

```python
    title: str | None = None,
    q: str | None = None,
```

e il ramo dopo `if title:`:

```python
    if q:
        # Un campo solo per la ricerca traccia del Dig: artista O titolo. Non
        # sostituisce `artist`/`title`, che restano filtri separati e in AND.
        like = f"%{q}%"
        stmt = stmt.where(or_(Track.artist.ilike(like), Track.title.ilike(like)))
```

In `backend/app/routers/tracks.py`, `get_tracks`: aggiungi `q: str | None = None,` dopo `title: str | None = None,` e passa `q=q,` a `list_tracks` (accanto a `title=title`).

- [ ] **Step 4: Verifica**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_tracks_q_filter.py tests/test_tracks_in_playlist_filter.py -q`
Expected: tutti verdi.

- [ ] **Step 5: Commit**

```bash
git add backend/app/repositories.py backend/app/routers/tracks.py backend/tests/test_tracks_q_filter.py
git commit -m "feat(tracks): q su GET /api/tracks, un campo per artista o titolo

Serve alla ricerca traccia della barra del Dig. artist= e title= restano
filtri separati."
```

---

### Task 3: Preferenza Discogs — `GET/PUT /api/settings/discovery`

**Files:**
- Modify: `backend/app/services/app_state.py` (in coda)
- Modify: `backend/app/routers/settings.py:20-40`
- Create: `backend/tests/test_settings_discovery_router.py`

**Interfaces:**
- Produces: `get_discogs_enabled(db) -> bool` in `app.services.app_state`; `DISCOGS_ENABLED_KEY = "discovery.discogs_enabled"`; endpoint `{ "discogs_enabled": bool }`.

- [ ] **Step 1: Test che fallisce**

```python
# backend/tests/test_settings_discovery_router.py
"""GET/PUT /api/settings/discovery: Discogs come sorgente della barra del Dig.

Preferenza di interfaccia su AppState (`discovery.discogs_enabled`), default
acceso. Il backend non la fa rispettare: /dig accetta source=discogs comunque."""
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app
from app.models import AppState
from app.services.app_state import DISCOGS_ENABLED_KEY, get_discogs_enabled

client = TestClient(app)
_factory = None


def _override_db():
    global _factory
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    _factory = sessionmaker(bind=engine, expire_on_commit=False)

    def _get_db():
        db = _factory()
        try:
            yield db
        finally:
            db.close()

    return _get_db


def setup_function():
    app.dependency_overrides[get_db] = _override_db()


def teardown_function():
    app.dependency_overrides.clear()


def test_default_acceso():
    r = client.get("/api/settings/discovery")
    assert r.status_code == 200
    assert r.json() == {"discogs_enabled": True}


def test_put_spegne_e_persiste():
    r = client.put("/api/settings/discovery", json={"discogs_enabled": False})
    assert r.status_code == 200
    assert r.json() == {"discogs_enabled": False}
    assert client.get("/api/settings/discovery").json() == {"discogs_enabled": False}
    with _factory() as db:
        assert db.get(AppState, DISCOGS_ENABLED_KEY).value == "0"


def test_put_riaccende():
    client.put("/api/settings/discovery", json={"discogs_enabled": False})
    client.put("/api/settings/discovery", json={"discogs_enabled": True})
    assert client.get("/api/settings/discovery").json() == {"discogs_enabled": True}


def test_valore_ignoto_vale_acceso():
    # Una riga corrotta non deve spegnere Discogs in silenzio: solo "0" spegne.
    with _factory() as db:
        db.add(AppState(key=DISCOGS_ENABLED_KEY, value="boh"))
        db.commit()
        assert get_discogs_enabled(db) is True
```

- [ ] **Step 2: Verifica che fallisca**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_settings_discovery_router.py -q`
Expected: ImportError su `DISCOGS_ENABLED_KEY`.

- [ ] **Step 3: Implementa**

In coda a `backend/app/services/app_state.py`:

```python
DISCOGS_ENABLED_KEY = "discovery.discogs_enabled"


def get_discogs_enabled(db: Session) -> bool:
    """Discogs come sorgente nella barra del Dig. È una preferenza di
    interfaccia: il backend resta permissivo e `/api/discovery/dig` accetta
    `source=discogs` comunque, così un link salvato torna a funzionare appena
    si riaccende. Default acceso; solo "0" spegne, una riga con un valore
    inatteso non spegne niente in silenzio."""
    return get_state(db, DISCOGS_ENABLED_KEY) != "0"
```

In `backend/app/routers/settings.py`: import `DISCOGS_ENABLED_KEY, get_discogs_enabled` accanto a `LANGUAGE_KEY, get_language, set_state`; dopo `write_language` aggiungi:

```python
class DiscoverySettings(BaseModel):
    discogs_enabled: bool


@router.get("/discovery", response_model=DiscoverySettings)
def read_discovery(db: Session = Depends(get_db)):
    return DiscoverySettings(discogs_enabled=get_discogs_enabled(db))


@router.put("/discovery", response_model=DiscoverySettings)
def write_discovery(req: DiscoverySettings, db: Session = Depends(get_db)):
    set_state(db, DISCOGS_ENABLED_KEY, "1" if req.discogs_enabled else "0")
    return req
```

Aggiorna il docstring del modulo (riga 3-6): aggiungi `- /discovery: Discogs come sorgente nella barra del Dig (preferenza di interfaccia).`

- [ ] **Step 4: Verifica**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_settings_discovery_router.py tests/test_settings_router.py -q`
Expected: verdi.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/app_state.py backend/app/routers/settings.py backend/tests/test_settings_discovery_router.py
git commit -m "feat(settings): Discogs spegnibile come sorgente del Dig, default acceso

Preferenza di interfaccia in AppState. Il backend non la fa rispettare:
rifiutare source=discogs romperebbe i link salvati senza proteggere da nulla.
Non tocca il client Discogs di Organize né il token."
```

---

### Task 4: I simili — l'arco artista non è tagliato, i conteggi non mentono

**Files:**
- Modify: `backend/app/services/discovery_dig.py:359-382` (`_select`)
- Modify: `backend/app/services/discovery_similar.py:19-30, 108-150`
- Modify: `backend/tests/test_discovery_similar.py:78-127`

**Interfaces:**
- Produces: `_sort_by_score(leads) -> list`, `_cap_per_artist(leads, *, exempt: Callable[[DiscoveryLead], bool] | None = None) -> list`; `_select(leads)` resta uguale (`_cap_per_artist(_sort_by_score(leads))`) per il dig e i test esistenti.

- [ ] **Step 1: Riscrivi il test del monopolio e aggiungine due**

In `backend/tests/test_discovery_similar.py` sostituisci `test_one_artist_cannot_monopolise_the_grid` con:

```python
def test_the_artist_edge_is_not_capped(db):
    # La sonda della diagnosi, come test permanente. `_MAX_PER_ARTIST` del dig
    # tagliava a 2 un arco che è per costruzione un artista solo: "i simili
    # danno due risultati" veniva da qui, non dall'interruttore stile/periodo.
    edges = [("same_artist", _lead(artist="Jasmín", title=f"Disco {i}")) for i in range(10)]
    source = _FakeSource(origin=_origin(), edges=edges)
    result = similar(db, _track(), source=source, style_period=False, library=[])
    assert len(result.leads) == 10
    assert result.edges["same_artist"].count == 10


def test_the_label_edge_is_still_capped(db):
    # Sull'etichetta il monopolio è un rischio vero: un artista prolifico del
    # catalogo non deve mangiarsi la griglia. Il cap resta lì.
    edges = [("same_label", _lead(artist="Prolific", title=f"Disco {i}")) for i in range(5)]
    source = _FakeSource(origin=_origin(), edges=edges)
    result = similar(db, _track(), source=source, style_period=False, library=[])
    assert len(result.leads) == 2


def test_edge_counts_describe_the_leads_shown_not_the_candidates(db):
    # Il chip "ETICHETTA 5" con due card a schermo mentiva: contava prima del cap.
    edges = [("same_label", _lead(artist="Prolific", title=f"Disco {i}")) for i in range(5)]
    source = _FakeSource(origin=_origin(), edges=edges)
    result = similar(db, _track(), source=source, style_period=False, library=[])
    assert result.edges["same_label"].count == len(result.leads) == 2


def test_a_lead_reached_by_artist_and_label_is_exempt(db):
    # La parentela più forte vince: raggiunto anche dall'artista, non si taglia.
    edges = [("same_artist", _lead(artist="Jasmín", title=f"Disco {i}")) for i in range(3)]
    edges += [("same_label", _lead(artist="Jasmín", title=f"Disco {i}")) for i in range(3)]
    source = _FakeSource(origin=_origin(), edges=edges)
    result = similar(db, _track(), source=source, style_period=False, library=[])
    assert len(result.leads) == 3
    assert result.edges["same_artist"].count == 3
    assert result.edges["same_label"].count == 3
```

- [ ] **Step 2: Verifica che fallisca**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_discovery_similar.py -q -k "capped or counts or exempt"`
Expected: `test_the_artist_edge_is_not_capped` FAIL (`2 == 10`), `test_edge_counts_describe…` FAIL (`5 == 2`), `test_a_lead_reached…` FAIL.

- [ ] **Step 3: Spezza `_select` in `discovery_dig.py`**

Aggiungi `from collections.abc import Callable` agli import. Sostituisci `_select` (riga 359-382) con:

```python
def _sort_by_score(leads: list[DiscoveryLead]) -> list[DiscoveryLead]:
    """Il sort DEVE restare stabile — `sorted` lo garantisce, ed e' su questa
    garanzia che poggia il fallback a gusto piatto: quando il riferimento e' vuoto
    (o nessun segnale aggancia) i lead pareggiano tutti, e l'ordine che sopravvive
    e' quello in cui sono entrati, cioe' l'ordine con cui la sorgente ha risposto
    dentro la finestra (per Discogs, quello per domanda). Sostituire `sorted` con
    un ordinamento instabile lo romperebbe in silenzio."""
    return sorted(leads, key=lambda x: x.score, reverse=True)


def _cap_per_artist(
    leads: list[DiscoveryLead],
    *,
    exempt: Callable[[DiscoveryLead], bool] | None = None,
) -> list[DiscoveryLead]:
    """Il cap anti-monopolio (`_MAX_PER_ARTIST`), sull'ordine gia' dato. NON tronca:
    la finestra e' gia' il limite naturale; quanti mostrarne e' una lente della UI.

    `exempt` esclude dal cap i lead per cui il "monopolio" e' il risultato chiesto:
    nei simili l'arco artista e' per costruzione un artista solo, e senza esenzione
    l'intera discografia collassava a due card."""
    out: list[DiscoveryLead] = []
    per_artist: dict[str, int] = {}
    for lead in leads:
        if exempt is not None and exempt(lead):
            out.append(lead)
            continue
        a = lead.artist_keys[0]
        if per_artist.get(a, 0) >= _MAX_PER_ARTIST:
            continue
        per_artist[a] = per_artist.get(a, 0) + 1
        out.append(lead)
    return out


def _select(leads: list[DiscoveryLead]) -> list[DiscoveryLead]:
    """Ordina per score e applica il cap per artista: la sequenza del dig."""
    return _cap_per_artist(_sort_by_score(leads))
```

- [ ] **Step 4: Usa le due meta' in `discovery_similar.py`**

Import: sostituisci `_select,` con `_cap_per_artist,` e `_sort_by_score,` (ordine alfabetico nel blocco). Nel corpo di `similar()`:

- nel ciclo `for edge, raw in raw_edges:` elimina le due righe `edge_hits[edge] += 1` e la riga `edge_hits: dict[str, int] = {e: 0 for e in EDGES}` che lo precede;
- sostituisci `selected = _select(leads)` con:

```python
    # Il cap anti-monopolio resta sugli archi etichetta e stile. L'arco artista
    # ne e' esente: e' un artista solo per costruzione, e il cap lo riduceva a
    # due card qualunque fosse la discografia. Raggiunto anche dall'artista, un
    # lead e' esente: la parentela piu' forte vince.
    selected = _cap_per_artist(
        _sort_by_score(leads),
        exempt=lambda lead: any(r.code == "same_artist" for r in lead.reasons),
    )

    # I conteggi descrivono i lead RESI, non i candidati: "ETICHETTA 5" con due
    # card a schermo era una bugia.
    edge_hits: dict[str, int] = {e: 0 for e in EDGES}
    for lead in selected:
        for r in lead.reasons:
            edge_hits[r.code] += 1
```

Aggiorna il commento di `test_edge_counts_report_leads_produced_after_dedup` (riga 80-84) che cita il tetto: sostituiscilo con `# Artisti diversi: qui si misura il conteggio per arco, non il cap (che ha i suoi test sotto).`

- [ ] **Step 5: Verifica**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_discovery_similar.py tests/test_discovery_dig.py -q`
Expected: tutti verdi (compresi `test_select_still_caps_per_artist`, `test_select_does_not_truncate`, `test_flat_taste_preserves_pile_order`).

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/discovery_dig.py backend/app/services/discovery_similar.py backend/tests/test_discovery_similar.py
git commit -m "fix(discovery): i simili non collassano più a due lead

similar() riusava _select() del dig, che taglia a due lead per artista, su
un arco che è per costruzione un artista solo. Misurato: due lead su dieci
release non possedute, flag OFF. Il cap resta su etichetta e stile, dove il
monopolio è un rischio vero. I conteggi degli archi si fanno sui lead resi."
```

---

### Task 5: Il motore scava per più semi, con budget diviso

**Files:**
- Modify: `backend/app/services/discovery_dig.py:57-73` (`_window`), `312-324` (`_styles_beyond_seed`), `385-465` (`DigResult`, `dig`)
- Modify: `backend/tests/test_discovery_dig.py` (call site di `dig`, asserzioni su `res.*`, test nuovi)

**Interfaces:**
- Produces:
  - `MAX_SEEDS = 4`
  - `_budget(n_seeds: int) -> int` = `WINDOW_ITEMS // max(1, n_seeds)`
  - `_window(depth: float, pile: Pile, budget: int = WINDOW_ITEMS) -> tuple[int, int]`
  - `_styles_beyond_seed(styles: list[str], seed_norms: set[str]) -> list[str]`
  - `_dominant_type(seeds: list[Seed]) -> str` (`"label"` solo se tutti label, altrimenti `"genre"`)
  - `@dataclass PileInfo(seed: Seed, total: int = 0, reach: int = 0, resolution: str | None = None)`
  - `@dataclass DigResult(seeds: list[Seed], leads: list[DiscoveryLead] = [], piles: list[PileInfo] = [])`
  - `dig(db, *, seeds: list[Seed], source: DigSource, library=None, depth=0.0) -> DigResult`; `ValueError` su lista vuota o `> MAX_SEEDS`.

- [ ] **Step 1: Adatta i test esistenti al contratto nuovo**

In `backend/tests/test_discovery_dig.py`, subito dopo `_src(...)` (riga ~70) aggiungi:

```python
def _dig(seed_type, value, **kw):
    """Un solo seme, nella forma nuova: la maggior parte dei test misura il
    motore su un seme, e il contratto a lista non deve farli riscrivere."""
    return dig(None, seeds=[Seed(seed_type, value)], **kw)
```

Poi i tre `sed` (macOS: `sed -i ''`):

```bash
cd backend
sed -i '' -E 's/\bdig\(None, seed_type=("[a-z]+"), value=/_dig(\1, /g' tests/test_discovery_dig.py
sed -i '' -E 's/res\.pile_total/res.piles[0].total/g; s/res\.pile_reach/res.piles[0].reach/g; s/res\.seed_resolution/res.piles[0].resolution/g' tests/test_discovery_dig.py
grep -n "res.seed_type\|res.value\|seed_type=" tests/test_discovery_dig.py
```

L'ultimo grep deve mostrare solo: la riga `assert res.seed_type == "genre" and res.value == "Acid House"` (in `test_dig_dedup_vs_library_and_pressings`) → sostituiscila con `assert res.seeds == [Seed("genre", "Acid House")]`; e le occorrenze in `_reason_codes(... seed_type=...)` (riga ~520-558), che restano com'erano: `_reasons` conserva la firma.

- [ ] **Step 2: Aggiungi i test nuovi in coda al file**

```python
# --- semi multipli: unione delle pile, budget diviso -------------------------


def test_dig_unites_the_piles_and_dedups_across_them():
    calls = []

    def search(**kw):
        calls.append(kw.get("style"))
        if kw.get("style") == "Deep House":
            return [_release("A - Shared", rid=1), _release("B - Only Deep", rid=2)]
        return [_release("A - Shared", rid=3), _release("C - Only Electro", rid=4)]

    res = dig(None, seeds=[Seed("genre", "Deep House"), Seed("genre", "Electro")],
              source=_src(search, total=300), library=[])
    pairs = sorted((l.artist, l.title) for l in res.leads)
    # Un disco raggiunto da due generi compare una volta sola.
    assert pairs == [("A", "Shared"), ("B", "Only Deep"), ("C", "Only Electro")]
    assert calls == ["Deep House", "Electro"]     # una sfogliata per seme, nell'ordine dato


def test_dig_splits_the_budget_between_the_seeds():
    seen: list[dict] = []

    def search(**kw):
        seen.append(dict(kw))
        return []

    dig(None, seeds=[Seed("genre", "A"), Seed("genre", "B")],
        source=_src(search, total=43345), library=[], depth=0.0)
    # 300 // 2 = 150 item a seme: due pagine Discogs da 100, non tre.
    assert [s["pages"] for s in seen] == [[1, 2], [1, 2]]


def test_dig_reports_one_pile_per_seed_including_the_dead_one():
    def count(**kw):
        # Morto su ENTRAMBE le sonde: style= e il ripiego su genre=.
        return 0 if "Inesistente" in kw.values() else 5000

    class _Client:
        def count_releases(self, **kw):
            return count(**kw)

        def search_releases(self, **kw):
            return []

    res = dig(None, seeds=[Seed("genre", "Acid House"), Seed("genre", "Inesistente")],
              source=DiscogsSource(_Client()), library=[])
    assert [p.seed.value for p in res.piles] == ["Acid House", "Inesistente"]
    assert res.piles[0].total == 5000 and res.piles[0].resolution == "style"
    # Il seme morto e' riportato per nome, non nascosto dentro un totale.
    assert res.piles[1].total == 0 and res.piles[1].reach == 0
    assert res.piles[1].resolution is None


def test_dig_mixed_seeds_keep_the_label_weight():
    # Con un genere e un'etichetta insieme il segnale etichetta discrimina di
    # nuovo (non e' piu' costante per costruzione): resta nel punteggio.
    def search(**kw):
        return [_release("X - On Warp", rid=1, label="Warp"),
                _release("Y - Elsewhere", rid=2, label="Other")]

    res = dig(None, seeds=[Seed("genre", "IDM"), Seed("label", "Warp")],
              source=_src(search, total=300),
              library=_lib(("Someone", "Track", {"label": "Warp"})))
    assert res.leads[0].title == "On Warp"
    assert "label_followed" in {r.code for r in res.leads[0].reasons}


def test_dig_all_label_seeds_drop_the_label_weight():
    from app.services.discovery_dig import _dominant_type
    assert _dominant_type([Seed("label", "Warp"), Seed("label", "Ninja")]) == "label"
    assert _dominant_type([Seed("label", "Warp"), Seed("genre", "IDM")]) == "genre"
    assert _dominant_type([Seed("genre", "IDM")]) == "genre"


def test_dig_style_floor_excludes_every_seed():
    # Con due semi, lo style del SECONDO non deve valere come affinita' extra.
    from app.services.discovery_dig import _styles_beyond_seed
    assert _styles_beyond_seed(["Deep House", "Electro", "Techno"],
                               {"deep house", "electro"}) == ["Techno"]


def test_dig_refuses_no_seeds_and_too_many():
    with pytest.raises(ValueError):
        dig(None, seeds=[], source=_src(lambda **kw: [], total=300), library=[])
    with pytest.raises(ValueError):
        dig(None, seeds=[Seed("genre", str(i)) for i in range(5)],
            source=_src(lambda **kw: [], total=300), library=[])


def test_window_honours_a_smaller_budget():
    assert _window(0.0, _discogs_pile(43345), 150) == (0, 150)
    assert _window(1.0, _discogs_pile(43345), 150) == (9850, 150)
    assert _window(0.5, _discogs_pile(120), 150) == (0, 120)   # pila piu' corta del budget
```

- [ ] **Step 3: Verifica che fallisca**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_discovery_dig.py -q 2>&1 | tail -5`
Expected: errori `TypeError: dig() got an unexpected keyword argument 'seeds'`.

- [ ] **Step 4: Implementa in `discovery_dig.py`**

Dopo `WINDOW_ITEMS` negli import aggiungi la costante, sotto `logger`:

```python
# Quanti semi puo' avere uno scavo. Oltre, il budget per seme scende sotto la
# soglia in cui la finestra smette di dire qualcosa (300 // 5 = 60 item).
MAX_SEEDS = 4


def _budget(n_seeds: int) -> int:
    """Quanti item spettano a ogni seme. Il budget di uno scavo resta
    WINDOW_ITEMS in tutto, DIVISO fra i semi, mai moltiplicato: il costo di
    uno scavo non deve crescere col numero di generi scelti."""
    return WINDOW_ITEMS // max(1, n_seeds)
```

`_window` diventa:

```python
def _window(depth: float, pile: Pile, budget: int = WINDOW_ITEMS) -> tuple[int, int]:
    """La finestra (offset, count) da pescare nella pila.

    depth 0 = la cima (il canone del seme), depth 1 = il fondo di cio' che la sorgente
    RAGGIUNGE — che non e' il fondo della pila quando `reach < height`. Su una pila piu'
    corta del budget `depth` non ha effetto: non c'e' profondita' da scegliere, e il
    chiamante lo segnala alla UI via `reach`. `budget` e' la quota di questo seme
    (`_budget`): con un seme solo e' l'intera finestra.
    """
    reach = _reach(pile)
    if reach <= 0:
        return 0, 0
    start = round(max(0.0, min(1.0, depth)) * max(0, reach - budget))
    return start, min(budget, reach - start)
```

`_styles_beyond_seed`:

```python
def _styles_beyond_seed(styles: list[str], seed_norms: set[str]) -> list[str]:
    """Gli style della release OLTRE i semi del dig.

    Su un dig per genere ogni release contiene lo style del seme per costruzione
    (e' il filtro `style=value` della ricerca): la sua somiglianza con la libreria
    e' un PAVIMENTO comune a tutti i lead. Con piu' semi il pavimento e' l'unione:
    lo style del secondo seme non e' affinita' extra piu' di quanto lo sia il primo.
    Sui semi etichetta e' un no-op: nessuno style si chiama come l'etichetta.
    """
    return [s for s in styles if _norm(s) not in seed_norms]


def _dominant_type(seeds: list[Seed]) -> str:
    """Il tipo che governa pesi e badge. 'label' SOLO se ogni seme e' un'etichetta:
    con semi misti il segnale etichetta discrimina di nuovo (non e' piu' costante
    per costruzione) e va tenuto."""
    return "label" if seeds and all(s.type == "label" for s in seeds) else "genre"
```

`DigResult` e `dig`:

```python
@dataclass
class PileInfo:
    """La pila di UN seme, come la UI deve poterla raccontare: un seme morto
    (`total == 0`) si dice per nome, non si nasconde in un totale."""
    seed: Seed
    total: int = 0
    reach: int = 0
    # Com'e' stato risolto il seme: "style"|"genre"|"label"|"tag"|"discography"|None.
    resolution: str | None = None


@dataclass
class DigResult:
    seeds: list[Seed]
    leads: list[DiscoveryLead] = field(default_factory=list)
    piles: list[PileInfo] = field(default_factory=list)


def dig(
    db: Session,
    *,
    seeds: list[Seed],
    source: DigSource,
    library: list | None = None,
    depth: float = 0.0,
) -> DigResult:
    """Lead non posseduti dall'UNIONE dei semi dati, ordinati per gusto.

    Ogni seme scava la propria pila (probe -> finestra -> fetch) con la sua quota
    del budget; dedup, punteggio e selezione sono una passata sola sull'unione.
    `depth` vale per tutte le pile. Il profilo di gusto e la dedup del posseduto
    usano la STESSA `library`.
    """
    if not seeds:
        raise ValueError("dig: serve almeno un seme")
    if len(seeds) > MAX_SEEDS:
        raise ValueError(f"dig: al massimo {MAX_SEEDS} semi, ricevuti {len(seeds)}")
    if library is None:
        library = _library_tracks(db)
    owned_tracks, owned_albums = _owned_index(library)
    profile = TasteProfile.from_tracks(library)
    budget = _budget(len(seeds))

    piles: list[PileInfo] = []
    leads: list[DiscoveryLead] = []
    seen: set[tuple[str, str]] = set()
    for seed in seeds:
        pile = source.probe(seed)
        reach = _reach(pile)
        piles.append(PileInfo(seed=seed, total=pile.height, reach=reach,
                              resolution=pile.resolution))
        offset, count = _window(depth, pile, budget)
        if count <= 0:
            continue
        for item in source.fetch(seed, pile, offset, count) or []:
            lead = source.to_lead(item, seed)
            if lead is None:
                continue
            k = _dedup_key(lead.artist_keys[0], lead.title)  # collassa varianti, pressature e semi
            if k in seen or _is_owned(lead, owned_tracks, owned_albums):
                continue
            seen.add(k)
            leads.append(lead)

    # Quali segnali esistono lo dicono i DATI, non il nome della sorgente.
    has_styles = any(lead.styles for lead in leads)
    kind = _dominant_type(seeds)
    weights = _weights(kind, has_styles=has_styles)
    current_year = datetime.now(timezone.utc).year
    seed_norms = {_norm(s.value) for s in seeds}
    for lead in leads:
        extra_styles = _styles_beyond_seed(lead.styles, seed_norms)
        lead.score = _score(lead, profile, weights, extra_styles)
        lead.reasons = _reasons(lead, profile, kind, current_year, extra_styles)
    selected = _select(leads)

    logger.info("Discovery dig %s %s: %s lead (depth=%.2f, budget %s/seme, pile %s)",
                source.name, [f"{s.type}={s.value!r}" for s in seeds], len(selected),
                depth, budget, [(p.reach, p.total) for p in piles])
    return DigResult(seeds=list(seeds), leads=selected, piles=piles)
```

Aggiorna il docstring del modulo (riga 1-19): sostituisci la prima frase con `Discovery v2 — "crate digging": lista-dig a volume dall'UNIONE delle pile di uno o piu' semi (`Seed`), con un budget di WINDOW_ITEMS diviso fra loro.`

- [ ] **Step 5: Verifica**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_discovery_dig.py tests/test_discovery_similar.py -q`
Expected: tutti verdi. (`test_discovery.py` e `test_discovery_router_http.py` restano rossi fino al Task 6: il router chiama ancora `dig(seed_type=…)`.)

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/discovery_dig.py backend/tests/test_discovery_dig.py
git commit -m "feat(discovery): il motore scava l'unione di più semi, budget diviso

dig() prende una lista di Seed; ogni seme ha la sua quota dei 300 item
(mai moltiplicati), la dedup è una passata sola sull'unione, e la risposta
porta una pila per seme così un seme morto si dice per nome."
```

---

### Task 6: Il contratto HTTP — `seeds[]` e `piles[]`

**Files:**
- Modify: `backend/app/schemas.py:554-575`
- Modify: `backend/app/routers/discovery.py:1-7` (docstring), `40-56` (import), `190-215` (`dig_endpoint`)
- Modify: `backend/tests/test_discovery.py:47, 75, 108, 162`
- Modify: `backend/tests/test_discovery_router_http.py:88-135, 175-270`
- Modify: `docs/API.md:619-720, 752-760`

**Interfaces:**
- Produces:
  - `POST /api/discovery/dig` body `{ seeds: [{type, value}], depth?, source? }`, `422` se `seeds` vuoto o `> 4`.
  - Risposta `{ seeds: [{type, value}], source, leads: [...], piles: [{seed_type, value, total, reach, resolution}] }`.
  - Pydantic: `DiscoverySeedIn`, `DiscoveryPileOut`.

- [ ] **Step 1: Aggiorna i test HTTP**

In `backend/tests/test_discovery.py` riga 47: `from app.schemas import DiscoveryDigRequest, DiscoverySeedIn`. Poi:

```bash
cd backend
sed -i '' 's/DiscoveryDigRequest(seed_type="genre", value="Acid House")/DiscoveryDigRequest(seeds=[DiscoverySeedIn(type="genre", value="Acid House")])/g' tests/test_discovery.py
```

In `backend/tests/test_discovery_router_http.py`:

```bash
sed -i '' -E 's/json=\{"seed_type": "([a-z_]+)", "value": "([^"]+)"/json={"seeds": [{"type": "\1", "value": "\2"}]/g' tests/test_discovery_router_http.py
grep -n "seed_type\|pile_total\|pile_reach\|seed_resolution\|body\[\"value\"\]" tests/test_discovery_router_http.py
```

Poi a mano, per ogni riga rimasta nel grep:

- `test_dig_200_via_http`: `assert body["seed_type"] == "genre"` e `assert body["value"] == "Acid House"` → `assert body["seeds"] == [{"type": "genre", "value": "Acid House"}]`.
- `test_dig_422_seed_type_non_valido`: il body è ora `{"seeds": [{"type": "not_a_seed_type", "value": "x"}]}` (il sed lo ha già fatto); rinominalo `test_dig_422_seed_type_non_valido` → resta, aggiungi sotto:

```python
def test_dig_422_senza_semi_e_oltre_quattro(client):
    c, _ = client
    assert c.post("/api/discovery/dig", json={"seeds": []}).status_code == 422
    five = [{"type": "genre", "value": str(i)} for i in range(5)]
    assert c.post("/api/discovery/dig", json={"seeds": five}).status_code == 422
```

- `test_dig_endpoint_accepts_depth_and_returns_pile_reach`: `assert r.json()["pile_reach"] == 10_000` → `assert r.json()["piles"][0]["reach"] == 10_000`.
- `test_dig_endpoint_exposes_seed_resolution_and_pile_total`: `r.json()["seed_resolution"] == "genre"` → `r.json()["piles"][0]["resolution"] == "genre"`; `r.json()["pile_total"] == 4_960_093` → `r.json()["piles"][0]["total"] == 4_960_093`.
- `test_dig_response_speaks_items_not_pages`: il `DigResult` finto diventa

```python
    from app.services.dig_sources import Seed
    from app.services.discovery_dig import DigResult, PileInfo

    def _fake_dig(db, **kw):
        seed = Seed("genre", "Acid House")
        return DigResult(
            seeds=[seed],
            leads=[DiscoveryLead(artist="A", title="B", source="discogs",
                                 source_id="7", source_url="https://discogs/7")],
            piles=[PileInfo(seed=seed, total=43345, reach=10_000, resolution="style")],
        )
```

  e le asserzioni: `body["pile_total"] == 43345` → `body["piles"] == [{"seed_type": "genre", "value": "Acid House", "total": 43345, "reach": 10_000, "resolution": "style"}]`; elimina `body["pile_reach"]`; tieni `"pile_pages" not in body`.
- `test_dig_with_source_bandcamp_uses_the_bandcamp_source`: il `DigResult` finto diventa `DigResult(seeds=[Seed("genre", "Techno")], leads=[], piles=[PileInfo(seed=Seed("genre", "Techno"), total=434149, reach=3000, resolution="tag")])` (con gli import come sopra); `r.json()["pile_reach"] == 3000` → `r.json()["piles"][0]["reach"] == 3000`.
- Aggiungi un test che il router passa i semi al motore nell'ordine e col tipo giusto:

```python
def test_dig_passes_every_seed_to_the_engine(client, monkeypatch):
    from app.routers import discovery as router_mod
    from app.services.dig_sources import Seed
    from app.services.discovery_dig import DigResult

    seen = {}

    def _fake_dig(db, **kw):
        seen["seeds"] = kw["seeds"]
        return DigResult(seeds=kw["seeds"], leads=[], piles=[])

    monkeypatch.setattr(router_mod, "dig", _fake_dig)
    c, _ = client
    r = c.post("/api/discovery/dig", json={"seeds": [
        {"type": "genre", "value": "Deep House"}, {"type": "label", "value": "Hessle Audio"}]})
    assert r.status_code == 200
    assert seen["seeds"] == [Seed("genre", "Deep House"), Seed("label", "Hessle Audio")]
    assert r.json()["seeds"] == [{"type": "genre", "value": "Deep House"},
                                 {"type": "label", "value": "Hessle Audio"}]
```

- [ ] **Step 2: Verifica che fallisca**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_discovery.py tests/test_discovery_router_http.py -q 2>&1 | tail -5`
Expected: ImportError `DiscoverySeedIn` / ValidationError su `seeds`.

- [ ] **Step 3: Schemi**

In `backend/app/schemas.py` sostituisci `DiscoveryDigRequest` e `DiscoveryDigResponse` (riga 554-575) con:

```python
class DiscoverySeedIn(BaseModel):
    type: Literal["genre", "label"]
    value: str = Field(min_length=1)


class DiscoveryDigRequest(BaseModel):
    # Piu' semi = UNIONE delle loro pile, col budget di 300 item diviso fra loro.
    # Misti (genere + etichetta) sono legittimi. Cap a 4: oltre, la quota per
    # seme scende sotto la soglia in cui la finestra dice qualcosa.
    seeds: list[DiscoverySeedIn] = Field(min_length=1, max_length=4)
    # DOVE pescare nella pila della sorgente: 0 = la cima, 1 = il fondo di cio' che
    # la sorgente raggiunge. Non e' un mix di ordinamento: sceglie il bacino.
    depth: float = Field(default=0.0, ge=0.0, le=1.0)
    source: Literal["discogs", "bandcamp"] = "discogs"


class DiscoveryPileOut(BaseModel):
    """La pila di un seme. `total == 0` = seme che la sorgente non conosce;
    `reach <= 300 // len(seeds)` = la finestra e' l'intera pila e `depth` non
    ha effetto; `reach < total` = si vede solo una porzione."""
    seed_type: str
    value: str
    total: int = 0
    reach: int = 0
    # "style"|"genre"|"label"|"tag"|"discography"|null
    resolution: str | None = None


class DiscoveryDigResponse(BaseModel):
    seeds: list[DiscoverySeedIn]
    source: str = "discogs"
    leads: list[DiscoveryLeadOut] = []
    piles: list[DiscoveryPileOut] = []
```

- [ ] **Step 4: Router**

In `backend/app/routers/discovery.py`: aggiungi `DiscoveryPileOut,` agli import da `app.schemas` (ordine alfabetico, dopo `DiscoveryLeadOut`); aggiungi `from app.services.dig_sources import Seed` dopo l'import di `bandcamp`. Sostituisci `dig_endpoint`:

```python
@router.post("/dig", response_model=DiscoveryDigResponse)
def dig_endpoint(req: DiscoveryDigRequest, db: Session = Depends(get_db)):
    """Lista-dig a volume dall'unione dei semi (generi/etichette): lead non risolti."""
    client = BandcampClient() if req.source == "bandcamp" else DiscogsClient()
    source = BandcampSource(client) if req.source == "bandcamp" else DiscogsSource(client)
    seeds = [Seed(type=s.type, value=s.value) for s in req.seeds]
    try:
        result = dig(db, seeds=seeds, source=source, depth=req.depth)
    except (DiscogsError, BandcampError) as exc:
        # Rate limit / token mancante / endpoint cambiato: 502 esplicito, mai uno
        # "zero risultati" muto — l'utente deve poter distinguere "non c'e' niente"
        # da "il provider non ha risposto".
        raise api_error(502, "discovery_provider_error", f"Discovery provider error: {exc}",
                        reason=str(exc)) from exc
    finally:
        client.close()
    return DiscoveryDigResponse(
        seeds=req.seeds, source=req.source,
        leads=[_lead_out(lead) for lead in result.leads],
        piles=[DiscoveryPileOut(seed_type=p.seed.type, value=p.seed.value,
                                total=p.total, reach=p.reach, resolution=p.resolution)
               for p in result.piles],
    )
```

Docstring del modulo, riga 3: `Endpoint dig: genera lead dall'unione di uno o piu' semi genere/etichetta, …`.

- [ ] **Step 5: Verifica tutta la suite backend**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests -q 2>&1 | tail -3`
Expected: tutti verdi.

- [ ] **Step 6: `docs/API.md`**

Nella sezione dig (dopo `The dig ("Scava") does crate digging by genre or label…`, riga ~666) sostituisci il primo paragrafo con:

```markdown
The dig ("Scava") does crate digging by genre and/or label and returns releases and
tracks not yet owned. The request carries **one to four seeds**
(`seeds: [{type: "genre"|"label", value}]`, mixed types allowed); the engine digs
each seed's pile and returns the **union**, deduplicated across seeds. Two sources
sit behind a shared `DigSource` protocol — **Discogs** (`source="discogs"`, the
default) and **Bandcamp** (`source="bandcamp"`) — chosen per request.

The window budget is **300 items per dig, divided between the seeds** (`300 // n`),
never multiplied: three genres cost three round trips and 300 items, not nine and
900. Five seeds or an empty list is `422`.
```

Nella sottosezione "The response reports, source-neutral, in items:" sostituisci le voci `pile_total`/`pile_reach`/`seed_resolution` con:

```markdown
- `piles[]`, one per seed in request order: `{seed_type, value, total, reach,
  resolution}`. `total == 0` is a seed the source does not know (reported by name,
  never folded into a sum); `reach <= 300 // len(seeds)` means the window is the
  whole pile and `depth` has no effect; `reach < total` means only a slice is
  visible. `resolution` is `style|genre|label` (Discogs), `tag|discography`
  (Bandcamp) or `null` for a dead seed.
```

Nella sezione Similar, in coda aggiungi:

```markdown
The dig's per-artist cap (two leads per artist) applies to the label and style edges
only: the `same_artist` edge is one artist by construction, and capping it collapsed
a whole discography to two cards. `edges[*].count` describes the leads **returned**,
not the candidates before the cap.
```

Nella sezione tracks (`GET /api/tracks`), accanto ai filtri `artist`/`title`, aggiungi: `` `q` — one free-text field matching `artist` **or** `title` (`ilike`), for the Dig's track search; `artist`/`title` stay separate AND filters. ``

Nella sezione settings aggiungi: `` `GET/PUT /api/settings/discovery` → `{discogs_enabled: bool}`: whether the Dig bar offers Discogs as a source. UI preference only (default `true`); the backend keeps accepting `source=discogs`, and nothing in Organize is touched. ``

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas.py backend/app/routers/discovery.py backend/tests/test_discovery.py backend/tests/test_discovery_router_http.py docs/API.md
git commit -m "feat(discovery): POST /dig prende seeds[] e risponde piles[]

Rottura pulita del contratto: app locale mono-utente, nessun lettore esterno
da proteggere. Cap a quattro semi in Pydantic."
```

---

### Task 7: Vocabolario frontend — semi, API, tipi, dizionari

**Files:**
- Create: `frontend/lib/discovery-seeds.ts`, `frontend/tests/discovery-seeds.test.ts`
- Modify: `frontend/lib/discovery-dig.ts` (tipo `SeedType` resta; `WINDOW_ITEMS` resta)
- Modify: `frontend/lib/api/types.ts:165-175, 204-207`, `lib/api/discovery.ts:20-32`, `lib/api/tracks.ts`, `lib/api/settings.ts`
- Modify: `frontend/lib/discovery-surprise.ts`, `frontend/tests/discovery-surprise.test.ts`
- Modify: `frontend/lib/i18n/en.ts`, `frontend/lib/i18n/it.ts` (blocchi `discovery`, `settings`)

**Interfaces:**
- Produces (`lib/discovery-seeds.ts`):
  - `type DigSeed = { type: SeedType; value: string }`
  - `MAX_SEEDS = 4`
  - `seedKey(s: DigSeed): string` = `${type}:${value.trim().toLowerCase()}`
  - `sameSeeds(a: DigSeed[], b: DigSeed[]): boolean` (stesse chiavi, stesso ordine)
  - `addSeed(list: DigSeed[], seed: DigSeed): { seeds: DigSeed[]; duplicate: DigSeed | null; full: boolean }`
  - `removeSeed(list: DigSeed[], seed: DigSeed): DigSeed[]`
  - `encodeSeeds(seeds: DigSeed[]): string`, `parseSeeds(raw: string | null): DigSeed[]`
  - `digHref(pathname: string, seeds: DigSeed[], depth: number, source: DigSourceKey): string`
- Produces (`lib/api`):
  - `discoveryDig(seeds: DigSeed[], opts?: { depth?: number; source?: DigSourceKey })`
  - `searchTracks(q: string, limit = 8): Promise<Track[]>`
  - `getDiscoverySettings(): Promise<DiscoverySettings>`, `setDiscoverySettings(s: DiscoverySettings)`
  - tipi `DiscoverySeed`, `DiscoveryPile`, `DiscoveryDigResponse { seeds, source, leads, piles }`, `DiscoverySettings { discogs_enabled: boolean }`, `GenreCount { genre: string; count: number }`
- Produces (`lib/discovery-surprise.ts`): `pickSurprise(pool, exclude: string[], rng?)`.

- [ ] **Step 1: Test dei semi**

```ts
// frontend/tests/discovery-seeds.test.ts
import { describe, expect, it } from "vitest";

import {
  addSeed, digHref, encodeSeeds, MAX_SEEDS, parseSeeds, removeSeed, sameSeeds, seedKey,
  type DigSeed,
} from "@/lib/discovery-seeds";

const DEEP: DigSeed = { type: "genre", value: "Deep House" };
const HESSLE: DigSeed = { type: "label", value: "Hessle Audio" };

describe("i semi dello scavo", () => {
  it("la chiave ignora maiuscole e spazi ai bordi", () => {
    expect(seedKey({ type: "genre", value: "  deep HOUSE " })).toBe(seedKey(DEEP));
    expect(seedKey({ type: "label", value: "Deep House" })).not.toBe(seedKey(DEEP));
  });

  it("aggiungere un seme già presente non lo sdoppia e lo indica", () => {
    const r = addSeed([DEEP], { type: "genre", value: "deep house" });
    expect(r.seeds).toEqual([DEEP]);
    expect(r.duplicate).toEqual(DEEP);
    expect(r.full).toBe(false);
  });

  it("aggiunge in coda, col valore ripulito", () => {
    const r = addSeed([DEEP], { type: "label", value: " Hessle Audio " });
    expect(r.seeds).toEqual([DEEP, HESSLE]);
    expect(r.duplicate).toBeNull();
  });

  it("al quinto seme rifiuta e lo dice", () => {
    const four = Array.from({ length: MAX_SEEDS }, (_, i) => ({ type: "genre" as const, value: `G${i}` }));
    const r = addSeed(four, { type: "genre", value: "Uno di troppo" });
    expect(r.seeds).toEqual(four);
    expect(r.full).toBe(true);
  });

  it("un valore vuoto non entra", () => {
    expect(addSeed([], { type: "genre", value: "   " }).seeds).toEqual([]);
  });

  it("toglie per chiave, non per identità", () => {
    expect(removeSeed([DEEP, HESSLE], { type: "genre", value: "deep house" })).toEqual([HESSLE]);
  });

  it("URL: codifica i due punti e la virgola DENTRO il valore", () => {
    const seeds: DigSeed[] = [{ type: "genre", value: "Nu-Disco, Italo" }, { type: "label", value: "R:S" }];
    const raw = encodeSeeds(seeds);
    expect(raw).toBe("genre:Nu-Disco%2C%20Italo,label:R%3AS");
    expect(parseSeeds(raw)).toEqual(seeds);
  });

  it("URL: round-trip attraverso URLSearchParams", () => {
    const seeds: DigSeed[] = [DEEP, HESSLE];
    const href = digHref("/discovery", seeds, 0.5, "bandcamp");
    const params = new URLSearchParams(href.split("?")[1]);
    expect(parseSeeds(params.get("seeds"))).toEqual(seeds);
    expect(params.get("depth")).toBe("0.5");
    expect(params.get("source")).toBe("bandcamp");
  });

  it("il parser scarta tipi sconosciuti, valori vuoti e semi oltre il cap", () => {
    expect(parseSeeds("track:5,genre:House,label:")).toEqual([{ type: "genre", value: "House" }]);
    expect(parseSeeds(null)).toEqual([]);
    expect(parseSeeds("")).toEqual([]);
    const six = Array.from({ length: 6 }, (_, i) => `genre:G${i}`).join(",");
    expect(parseSeeds(six)).toHaveLength(MAX_SEEDS);
  });

  it("il parser non si rompe su una codifica malformata", () => {
    expect(parseSeeds("genre:%E0%A4%A")).toEqual([]);
  });

  it("sameSeeds confronta chiavi e ordine", () => {
    expect(sameSeeds([DEEP, HESSLE], [{ type: "genre", value: "deep house" }, HESSLE])).toBe(true);
    expect(sameSeeds([DEEP, HESSLE], [HESSLE, DEEP])).toBe(false);
    expect(sameSeeds([DEEP], [])).toBe(false);
  });
});
```

- [ ] **Step 2: Verifica che fallisca**

Run: `cd frontend && npx vitest run tests/discovery-seeds.test.ts`
Expected: modulo non trovato.

- [ ] **Step 3: `lib/discovery-seeds.ts`**

```ts
// I semi di uno scavo: un genere o un'etichetta per voce, fino a MAX_SEEDS.
// Vive in lib/ perché barra, pagina e URL parlino la stessa lingua senza che
// la lib importi da un componente (stesso criterio di discovery-dig.ts).

import type { DigSourceKey, SeedType } from "@/lib/discovery-dig";

export type DigSeed = { type: SeedType; value: string };

/** Rispecchia MAX_SEEDS del backend: oltre, la quota di finestra per seme
 *  (300 // n) smette di dire qualcosa. */
export const MAX_SEEDS = 4;

const TYPES: readonly SeedType[] = ["genre", "label"];

function clean(seed: DigSeed): DigSeed {
  return { type: seed.type, value: seed.value.trim() };
}

/** Identità di un seme: tipo + valore, case-insensitive. "Deep House" e
 *  "deep house" sono lo stesso seme; il genere "Warp" e l'etichetta "Warp" no. */
export function seedKey(seed: DigSeed): string {
  return `${seed.type}:${seed.value.trim().toLowerCase()}`;
}

export function sameSeeds(a: DigSeed[], b: DigSeed[]): boolean {
  return a.length === b.length && a.every((s, i) => seedKey(s) === seedKey(b[i]));
}

/** Aggiunge in coda. Un duplicato non entra e viene restituito (il chiamante
 *  lo fa lampeggiare invece di sdoppiarlo); al cap `full` è vero e la lista
 *  resta com'era. Un valore vuoto non è un seme. */
export function addSeed(
  list: DigSeed[],
  seed: DigSeed,
): { seeds: DigSeed[]; duplicate: DigSeed | null; full: boolean } {
  const next = clean(seed);
  if (!next.value) return { seeds: list, duplicate: null, full: false };
  const key = seedKey(next);
  const duplicate = list.find((s) => seedKey(s) === key) ?? null;
  if (duplicate) return { seeds: list, duplicate, full: false };
  if (list.length >= MAX_SEEDS) return { seeds: list, duplicate: null, full: true };
  return { seeds: [...list, next], duplicate: null, full: false };
}

export function removeSeed(list: DigSeed[], seed: DigSeed): DigSeed[] {
  const key = seedKey(seed);
  return list.filter((s) => seedKey(s) !== key);
}

/** `type:value,type:value`. I due punti e la virgola compaiono nei nomi veri
 *  («Nu-Disco, Italo»), quindi il valore si codifica PRIMA di comporre la
 *  lista: la sola codifica della query string li lascerebbe passare tali e
 *  quali e spezzerebbe il parsing. */
export function encodeSeeds(seeds: DigSeed[]): string {
  return seeds.map((s) => `${s.type}:${encodeURIComponent(s.value)}`).join(",");
}

/** Il rovescio di `encodeSeeds`. Splitta sul PRIMO `:` soltanto; scarta tipi
 *  che non siano genre/label, valori vuoti e codifiche rotte: la stringa
 *  arriva dall'URL, e chi lo scrive non è per forza l'app. Tronca al cap. */
export function parseSeeds(raw: string | null): DigSeed[] {
  if (!raw) return [];
  const out: DigSeed[] = [];
  for (const part of raw.split(",")) {
    const i = part.indexOf(":");
    if (i <= 0) continue;
    const type = part.slice(0, i) as SeedType;
    if (!TYPES.includes(type)) continue;
    let value: string;
    try {
      value = decodeURIComponent(part.slice(i + 1)).trim();
    } catch {
      continue;
    }
    if (!value) continue;
    const r = addSeed(out, { type, value });
    if (r.full) break;
    out.splice(0, out.length, ...r.seeds);
  }
  return out;
}

/** L'URL di uno scavo. Unica fonte per il bottone Scava, Sorprendimi e il reroll. */
export function digHref(
  pathname: string,
  seeds: DigSeed[],
  depth: number,
  source: DigSourceKey,
): string {
  const params = new URLSearchParams();
  params.set("seeds", encodeSeeds(seeds));
  params.set("depth", String(depth));
  params.set("source", source);
  return `${pathname}?${params.toString()}`;
}
```

- [ ] **Step 4: API e tipi**

`frontend/lib/api/types.ts`: sostituisci `DiscoveryDigResponse` (riga 165-175) con:

```ts
export interface DiscoverySeed {
  type: "genre" | "label";
  value: string;
}

/** La pila di UN seme. `total === 0` => seme che la sorgente non conosce;
 *  `reach <= WINDOW_ITEMS / seeds.length` => `depth` non ha effetto. */
export interface DiscoveryPile {
  seed_type: "genre" | "label";
  value: string;
  total: number;
  reach: number;
  resolution: "style" | "genre" | "label" | "tag" | "discography" | null;
}

export interface DiscoveryDigResponse {
  seeds: DiscoverySeed[];
  source: string;
  leads: DiscoveryLead[];
  piles: DiscoveryPile[];
}
```

Dopo `DiscoveryGenres` aggiungi:

```ts
export interface DiscoverySettings {
  /** Discogs come sorgente nella barra del Dig. Solo interfaccia: il backend
   *  accetta `source=discogs` comunque. */
  discogs_enabled: boolean;
}

export interface GenreCount {
  genre: string;
  count: number;
}
```

`frontend/lib/api/discovery.ts`: sostituisci `discoveryDig`:

```ts
import type { DigSeed } from "../discovery-seeds";
// (aggiungi all'elenco degli import da "./types": DiscoverySettings non serve qui)

export function discoveryDig(
  seeds: DigSeed[],
  opts?: { depth?: number; source?: DigSourceKey },
) {
  return apiPost<DiscoveryDigResponse>("/api/discovery/dig", {
    seeds,
    depth: opts?.depth,
    source: opts?.source,
  });
}
```

`frontend/lib/api/tracks.ts`: aggiungi `Track` all'import da `./types` (non esiste un tipo `TrackList` in `types.ts`: la forma della lista si scrive inline). Poi:

```ts
/** Ricerca libera su artista o titolo, per la barra del Dig (modo Traccia). */
export function searchTracks(q: string, limit = 8) {
  return apiGet<{ total: number; items: Track[] }>("/api/tracks", { q, limit })
    .then((r) => r.items);
}
```

`frontend/lib/api/settings.ts`: `apiGet` e `apiPut` sono già importati lì (li usa `setLibraryShare`); aggiungi `DiscoverySettings` all'import da `./types` e:

```ts
export function getDiscoverySettings() {
  return apiGet<DiscoverySettings>("/api/settings/discovery");
}

export function setDiscoverySettings(s: DiscoverySettings) {
  return apiPut<DiscoverySettings>("/api/settings/discovery", s);
}
```

- [ ] **Step 5: Sorprendimi esclude una lista**

`frontend/lib/discovery-surprise.ts`: cambia la firma in `pickSurprise(pool, exclude: string[], rng = Math.random)` e il corpo:

```ts
  const cur = new Set(exclude.map((v) => v.trim().toLowerCase()).filter(Boolean));
  const filtered = cur.size ? entries.filter((e) => !cur.has(e.value.trim().toLowerCase())) : entries;
```

Aggiorna il docstring: «`exclude` (i semi già in barra) viene escluso per non ripetere un colpo appena fatto». In `frontend/tests/discovery-surprise.test.ts` sostituisci ogni `null` come secondo argomento con `[]` e `"acid house"` con `["acid house"]`; aggiungi:

```ts
  it("esclude TUTTI i semi in barra, non solo uno", () => {
    const pick = pickSurprise(POOL, ["Acid House", "techno"], seqRng([0, 0]));
    expect(pick?.value).toBe("Trax Records");
  });
```

- [ ] **Step 6: Dizionari**

In `frontend/lib/i18n/en.ts`, blocco `discovery`, sostituisci `intro` e `readyBodyNotReady` e aggiungi le chiavi nuove (in coda al blocco):

```ts
    intro: "Dig for new music by genre or label, or start from a track you own.",
    readyBodyNotReady: "Add at least one genre or label above, then press “Dig”.",
    modeLabel: "Mode",
    modeSeeds: "Genres & labels",
    modeTrack: "Track",
    seedsPlaceholder: "Add a genre or label… or type your own",
    seedsFull: (n: number) => `At most ${n} seeds per dig`,
    removeSeed: (value: string) => `Remove ${value}`,
    paletteLibrary: "In your library",
    paletteStyles: "Other styles",
    paletteShow: "show",
    paletteHide: "hide",
    trackSearchPlaceholder: "Search a track in your library…",
    trackSearchEmpty: "No track found",
    trackSearchHint: "Pick a track you own: its relatives on Bandcamp start from there.",
    deadSeeds: (names: string, src: string) => `${src} does not know ${names}: no pile for that seed.`,
    broadSeeds: (details: string, src: string) => `Very broad seeds on ${src}: ${details}. You only see the top.`,
    broadSeedDetail: (value: string, total: string, reachable: string) => `${value} (${total} records, ${reachable} reachable)`,
    nothingToDigSeeds: (names: string) => `Nothing new for ${names}. Try other seeds or go deeper into the pile.`,
```

In `settings` (en.ts) aggiungi:

```ts
    discoveryHeading: "Discovery",
    discoveryDiscogs: "Offer Discogs as a dig source",
    discoveryDiscogsHint: "Off, the Dig bar only offers Bandcamp. Organize and the Discogs token are untouched.",
```

Stesse chiavi in `it.ts`:

```ts
    intro: "Scava nuova musica per genere o etichetta, o parti da una traccia che possiedi.",
    readyBodyNotReady: "Aggiungi almeno un genere o un'etichetta qui sopra, poi premi “Scava”.",
    modeLabel: "Modo",
    modeSeeds: "Generi ed etichette",
    modeTrack: "Traccia",
    seedsPlaceholder: "Aggiungi un genere o un'etichetta… o scrivilo tu",
    seedsFull: (n: number) => `Al massimo ${n} semi per scavo`,
    removeSeed: (value: string) => `Togli ${value}`,
    paletteLibrary: "In libreria",
    paletteStyles: "Altri stili",
    paletteShow: "mostra",
    paletteHide: "nascondi",
    trackSearchPlaceholder: "Cerca una traccia della libreria…",
    trackSearchEmpty: "Nessuna traccia trovata",
    trackSearchHint: "Scegli una traccia posseduta: i suoi parenti su Bandcamp partono da lì.",
    deadSeeds: (names: string, src: string) => `${src} non conosce ${names}: quel seme non ha una pila.`,
    broadSeeds: (details: string, src: string) => `Semi molto ampi su ${src}: ${details}. Ne vedi solo la cima.`,
    broadSeedDetail: (value: string, total: string, reachable: string) => `${value} (${total} dischi, ne raggiungi ${reachable})`,
    nothingToDigSeeds: (names: string) => `Nessun brano nuovo per ${names}. Prova altri semi o vai più a fondo nella pila.`,
```

```ts
    discoveryHeading: "Discovery",
    discoveryDiscogs: "Offri Discogs come sorgente dello scavo",
    discoveryDiscogsHint: "Spento, la barra del Dig offre solo Bandcamp. Organize e il token Discogs non c'entrano.",
```

- [ ] **Step 7: Verifica**

Run: `cd frontend && npx vitest run tests/discovery-seeds.test.ts tests/discovery-surprise.test.ts && npx tsc --noEmit 2>&1 | head`
Expected: test verdi. `tsc` segnalerà errori SOLO in `app/discovery/page.tsx` e `components/discovery-dig-bar.tsx` (vecchio contratto: `discoveryDig(seed, value…)`, `dig.pile_total`, `pickSurprise(…, string)`): sono i file dei Task 10-11. Nessun altro errore.

- [ ] **Step 8: Commit**

```bash
git add frontend/lib/discovery-seeds.ts frontend/tests/discovery-seeds.test.ts frontend/lib/api/types.ts frontend/lib/api/discovery.ts frontend/lib/api/tracks.ts frontend/lib/api/settings.ts frontend/lib/discovery-surprise.ts frontend/tests/discovery-surprise.test.ts frontend/lib/i18n/en.ts frontend/lib/i18n/it.ts
git commit -m "feat(discovery): il vocabolario dei semi multipli nel frontend

Chiave, codifica URL con : e , dentro il valore, add/remove col cap a 4;
API e tipi sul contratto seeds[]/piles[]; Sorprendimi esclude tutti i semi
in barra; le stringhe nuove in entrambe le lingue."
```

---

### Task 8: `DiscoverySeedPicker` — chip, combobox, tavolozza

**Files:**
- Create: `frontend/components/discovery-seed-picker.tsx`, `frontend/tests/discovery-seed-picker.test.tsx`

**Interfaces:**
- Consumes: `addSeed/removeSeed/seedKey/MAX_SEEDS/DigSeed` (Task 7); `Combobox, Chip` da `@/components/ui`; `t.discovery.*` (Task 7).
- Produces:

```ts
export function DiscoverySeedPicker(props: {
  seeds: DigSeed[];
  onChange: (seeds: DigSeed[]) => void;
  options: { genres: { library: string[]; styles: string[] }; labels: string[]; genreCounts: GenreCount[] };
  disabled?: boolean;
}): JSX.Element
```

- [ ] **Step 1: Test**

```tsx
// frontend/tests/discovery-seed-picker.test.tsx
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

import { DiscoverySeedPicker } from "@/components/discovery-seed-picker";
import type { DigSeed } from "@/lib/discovery-seeds";

afterEach(cleanup);

const OPTIONS = {
  genres: { library: ["Acid House", "Techno"], styles: ["Deep House", "Acid House"] },
  labels: ["Trax Records"],
  genreCounts: [{ genre: "Techno", count: 388 }, { genre: "Acid House", count: 41 }],
};
const DEEP: DigSeed = { type: "genre", value: "Deep House" };

function setup(seeds: DigSeed[] = [], over: Partial<React.ComponentProps<typeof DiscoverySeedPicker>> = {}) {
  const onChange = vi.fn();
  render(<DiscoverySeedPicker seeds={seeds} onChange={onChange} options={OPTIONS} {...over} />);
  return onChange;
}

const input = () => screen.getByRole("combobox") as HTMLInputElement;

describe("DiscoverySeedPicker", () => {
  it("rende i semi come chip con l'azione di rimozione", () => {
    const onChange = setup([DEEP, { type: "label", value: "Trax Records" }]);
    fireEvent.click(screen.getByLabelText("Togli Deep House"));
    expect(onChange).toHaveBeenCalledWith([{ type: "label", value: "Trax Records" }]);
  });

  it("scegliere dal menu aggiunge col tipo del gruppo", () => {
    const onChange = setup([DEEP]);
    fireEvent.focus(input());
    fireEvent.mouseDown(screen.getByText("Trax Records"));
    expect(onChange).toHaveBeenCalledWith([DEEP, { type: "label", value: "Trax Records" }]);
  });

  it("Invio sul testo libero aggiunge un GENERE e svuota il campo", () => {
    const onChange = setup([]);
    fireEvent.change(input(), { target: { value: "Inventato" } });
    fireEvent.keyDown(input(), { key: "Enter" });
    expect(onChange).toHaveBeenCalledWith([{ type: "genre", value: "Inventato" }]);
    expect(input().value).toBe("");
  });

  it("un duplicato non entra: il chip esistente lampeggia", () => {
    const onChange = setup([DEEP]);
    fireEvent.change(input(), { target: { value: "deep house" } });
    fireEvent.keyDown(input(), { key: "Enter" });
    expect(onChange).not.toHaveBeenCalled();
    expect(screen.getByText("Deep House").closest("[data-flash]")).toBeTruthy();
  });

  it("al cap il campo è disabilitato e lo spiega", () => {
    const four = Array.from({ length: 4 }, (_, i) => ({ type: "genre" as const, value: `G${i}` }));
    setup(four);
    expect(input().disabled).toBe(true);
    expect(screen.getByText("Al massimo 4 semi per scavo")).toBeTruthy();
  });

  it("la tavolozza mostra i generi in libreria col conteggio, poi gli stili senza doppioni", () => {
    setup([]);
    const lib = screen.getByText("In libreria").parentElement!;
    expect(lib.textContent).toContain("Techno");
    expect(lib.textContent).toContain("388");
    const styles = screen.getByText("Altri stili").parentElement!;
    expect(styles.textContent).toContain("Deep House");
    expect(styles.textContent).not.toContain("Acid House");   // già in libreria
  });

  it("un chip della tavolozza commuta il seme nei due versi", () => {
    const onChange = setup([]);
    fireEvent.click(screen.getByRole("button", { name: /^Techno/ }));
    expect(onChange).toHaveBeenLastCalledWith([{ type: "genre", value: "Techno" }]);
    cleanup();
    const onChange2 = setup([{ type: "genre", value: "Techno" }]);
    fireEvent.click(screen.getByText("mostra"));   // con un seme la tavolozza parte chiusa
    fireEvent.click(screen.getByRole("button", { name: /^Techno/ }));
    expect(onChange2).toHaveBeenLastCalledWith([]);
  });

  it("la tavolozza è aperta a barra vuota e chiusa col primo seme, ma si riapre", () => {
    setup([DEEP]);
    expect(screen.queryByText("In libreria")).toBeNull();
    fireEvent.click(screen.getByText("mostra"));
    expect(screen.getByText("In libreria")).toBeTruthy();
  });

  it("disabilitato: niente campo, niente rimozione", () => {
    setup([DEEP], { disabled: true });
    expect(input().disabled).toBe(true);
    expect((screen.getByLabelText("Togli Deep House") as HTMLButtonElement).disabled).toBe(true);
  });
});
```

- [ ] **Step 2: Verifica che fallisca**

Run: `cd frontend && npx vitest run tests/discovery-seed-picker.test.tsx`
Expected: modulo non trovato.

- [ ] **Step 3: Implementa**

```tsx
// frontend/components/discovery-seed-picker.tsx
"use client";

import { useEffect, useMemo, useState } from "react";
import { Disc3, Tags, X } from "lucide-react";

import { Chip, Combobox, type ComboOption } from "@/components/ui";
import { useT } from "@/lib/i18n";
import type { GenreCount } from "@/lib/api/types";
import { addSeed, MAX_SEEDS, removeSeed, seedKey, type DigSeed } from "@/lib/discovery-seeds";
import { cn } from "@/lib/cn";

const FLASH_MS = 600;

/* I semi scelti come chip, un campo per aggiungerne (dal menu o a mano) e una
   tavolozza di quello che c'è già: la cura per "la selezione è scomoda" è
   vedere cosa si ha PRIMA di digitare. Il Combobox resta quello del DS: il
   testo libero confermato con Invio è un genere, come prima. */
export function DiscoverySeedPicker({ seeds, onChange, options, disabled }: {
  seeds: DigSeed[];
  onChange: (seeds: DigSeed[]) => void;
  options: {
    genres: { library: string[]; styles: string[] };
    labels: string[];
    genreCounts: GenreCount[];
  };
  disabled?: boolean;
}) {
  const t = useT();
  const [text, setText] = useState("");
  const [flash, setFlash] = useState<string | null>(null);
  // Aperta a barra vuota, chiusa col primo seme: chi ha già scelto vuole i
  // risultati, non la tavolozza. Ma si riapre, e resta come la si è messa.
  const [paletteOpen, setPaletteOpen] = useState(seeds.length === 0);
  const full = seeds.length >= MAX_SEEDS;

  useEffect(() => {
    if (flash === null) return;
    const id = window.setTimeout(() => setFlash(null), FLASH_MS);
    return () => window.clearTimeout(id);
  }, [flash]);

  const add = (seed: DigSeed) => {
    const r = addSeed(seeds, seed);
    if (r.duplicate) { setFlash(seedKey(r.duplicate)); return; }
    if (r.full) return;
    onChange(r.seeds);
    setText("");
    if (r.seeds.length === 1) setPaletteOpen(false);
  };

  const toggle = (seed: DigSeed) => {
    const key = seedKey(seed);
    if (seeds.some((s) => seedKey(s) === key)) onChange(removeSeed(seeds, seed));
    else add(seed);
  };

  // Stesso ordine e stessa dedup di prima: libreria, etichette, stili curati;
  // un genere presente in entrambe le liste compare una volta, con la grafia
  // della libreria.
  const comboOptions: ComboOption[] = useMemo(() => {
    const seen = new Set<string>();
    const genres = (list: string[]) => list
      .filter((g) => { const k = g.trim().toLowerCase(); if (!k || seen.has(k)) return false; seen.add(k); return true; })
      .map((g) => ({ value: g, label: g, group: t.discovery.groupGenre, icon: <Disc3 size={13} /> }));
    return [
      ...genres(options.genres.library),
      ...options.labels.map((l) => ({ value: l, label: l, group: t.discovery.groupLabel, icon: <Tags size={13} /> })),
      ...genres(options.genres.styles),
    ];
  }, [options, t]);

  const libraryKeys = useMemo(
    () => new Set(options.genres.library.map((g) => g.trim().toLowerCase())), [options.genres.library]);
  const counts = useMemo(
    () => new Map(options.genreCounts.map((c) => [c.genre.trim().toLowerCase(), c.count])), [options.genreCounts]);
  const styleChips = options.genres.styles.filter((s) => !libraryKeys.has(s.trim().toLowerCase()));
  const isOn = (seed: DigSeed) => seeds.some((s) => seedKey(s) === seedKey(seed));

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        {seeds.map((s) => {
          const key = seedKey(s);
          return (
            <span
              key={key}
              data-flash={flash === key ? "" : undefined}
              className={cn(
                "inline-flex items-center gap-1.5 border border-border-strong bg-elevated px-2 py-1 text-xs text-fg",
                flash === key && "animate-pulse",
              )}
            >
              {s.type === "label" ? <Tags size={12} /> : <Disc3 size={12} />}
              {s.value}
              <button
                type="button"
                aria-label={t.discovery.removeSeed(s.value)}
                disabled={disabled}
                onClick={() => onChange(removeSeed(seeds, s))}
                className="ml-0.5 text-muted hover:text-fg disabled:opacity-50"
              >
                <X size={12} />
              </button>
            </span>
          );
        })}
        <div
          className="min-w-[240px] flex-1"
          // Il Combobox fa preventDefault solo quando SCEGLIE un'opzione: se
          // l'evento arriva qui intatto, Invio ha trovato solo testo libero.
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.defaultPrevented && text.trim()) {
              e.preventDefault();
              add({ type: "genre", value: text });
            }
          }}
        >
          <Combobox
            value={text}
            options={comboOptions}
            disabled={disabled || full}
            placeholder={full ? t.discovery.seedsFull(MAX_SEEDS) : t.discovery.seedsPlaceholder}
            onChange={setText}
            onSelect={(o) => add({ type: o.group === t.discovery.groupLabel ? "label" : "genre", value: o.value })}
          />
        </div>
      </div>
      {full && <p className="text-xs text-muted">{t.discovery.seedsFull(MAX_SEEDS)}</p>}

      <div className="border-t border-border pt-3">
        <button
          type="button"
          onClick={() => setPaletteOpen((v) => !v)}
          className="text-[10px] uppercase tracking-wider text-muted hover:text-fg"
        >
          {paletteOpen ? t.discovery.paletteHide : t.discovery.paletteShow}
        </button>
        {paletteOpen && (
          <div className="mt-2 flex flex-col gap-2">
            {options.genres.library.length > 0 && (
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="mr-1 text-[10px] uppercase tracking-wider text-muted">{t.discovery.paletteLibrary}</span>
                {options.genres.library.map((g) => {
                  const n = counts.get(g.trim().toLowerCase());
                  return (
                    <Chip key={g} on={isOn({ type: "genre", value: g })} disabled={disabled}
                          onClick={() => toggle({ type: "genre", value: g })}>
                      {g}{n != null && <span className="tnum ml-1 text-faint">{n}</span>}
                    </Chip>
                  );
                })}
              </div>
            )}
            {styleChips.length > 0 && (
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="mr-1 text-[10px] uppercase tracking-wider text-muted">{t.discovery.paletteStyles}</span>
                {styleChips.map((s) => (
                  <Chip key={s} on={isOn({ type: "genre", value: s })} disabled={disabled}
                        onClick={() => toggle({ type: "genre", value: s })}>
                    {s}
                  </Chip>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Verifica**

Run: `cd frontend && npx vitest run tests/discovery-seed-picker.test.tsx`
Expected: 9 verdi. Se "un chip della tavolozza commuta" non trova il bottone, il conteggio dentro il chip cambia il nome accessibile: il matcher `/^Techno/` lo tollera; non cambiare il test per farlo passare.

- [ ] **Step 5: Commit**

```bash
git add frontend/components/discovery-seed-picker.tsx frontend/tests/discovery-seed-picker.test.tsx
git commit -m "feat(discovery): il selettore dei semi — chip, campo e tavolozza"
```

---

### Task 9: `DiscoveryTrackSearch` — la ricerca traccia

**Files:**
- Create: `frontend/components/discovery-track-search.tsx`, `frontend/tests/discovery-track-search.test.tsx`

**Interfaces:**
- Consumes: `Track` da `@/lib/api/types`; `TrackCover` da `@/components/track-cover`; `Input` da `@/components/ui`.
- Produces:

```ts
export function DiscoveryTrackSearch(props: {
  search: (q: string) => Promise<Track[]>;
  onPick: (track: Track) => void;
  disabled?: boolean;
}): JSX.Element
```

- [ ] **Step 1: Test**

```tsx
// frontend/tests/discovery-track-search.test.tsx
import { afterEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

import { DiscoveryTrackSearch } from "@/components/discovery-track-search";

afterEach(() => { cleanup(); vi.useRealTimers(); });

const A = { id: 5, artist: "Jasmín", title: "Bite The Hand", album_art_url: null, has_local_file: true } as never;
const B = { id: 9, artist: "Pearson Sound", title: "Jasmine Tea", album_art_url: null, has_local_file: true } as never;

function setup(results = [A, B]) {
  const search = vi.fn().mockResolvedValue(results);
  const onPick = vi.fn();
  render(<DiscoveryTrackSearch search={search} onPick={onPick} />);
  return { search, onPick };
}

const input = () => screen.getByRole("combobox") as HTMLInputElement;

describe("DiscoveryTrackSearch", () => {
  it("cerca dopo una pausa, non a ogni tasto", async () => {
    vi.useFakeTimers();
    const { search } = setup();
    fireEvent.change(input(), { target: { value: "j" } });
    fireEvent.change(input(), { target: { value: "ja" } });
    fireEvent.change(input(), { target: { value: "jas" } });
    expect(search).not.toHaveBeenCalled();
    await act(async () => { vi.advanceTimersByTime(300); });
    expect(search).toHaveBeenCalledTimes(1);
    expect(search).toHaveBeenCalledWith("jas");
  });

  it("mostra artista — titolo e sceglie al click", async () => {
    const { onPick } = setup();
    fireEvent.change(input(), { target: { value: "jas" } });
    await waitFor(() => expect(screen.getByText(/Bite The Hand/)).toBeTruthy());
    fireEvent.mouseDown(screen.getByText(/Jasmine Tea/));
    expect(onPick).toHaveBeenCalledWith(B);
  });

  it("frecce e Invio scelgono da tastiera", async () => {
    const { onPick } = setup();
    fireEvent.change(input(), { target: { value: "jas" } });
    await waitFor(() => expect(screen.getAllByRole("option")).toHaveLength(2));
    fireEvent.keyDown(input(), { key: "ArrowDown" });
    fireEvent.keyDown(input(), { key: "ArrowDown" });
    fireEvent.keyDown(input(), { key: "Enter" });
    expect(onPick).toHaveBeenCalledWith(B);
  });

  it("nessun risultato lo dice", async () => {
    setup([]);
    fireEvent.change(input(), { target: { value: "zzz" } });
    await waitFor(() => expect(screen.getByText("Nessuna traccia trovata")).toBeTruthy());
  });

  it("una risposta arrivata in ritardo per una query vecchia non sovrascrive", async () => {
    let releaseOld: (v: unknown[]) => void = () => {};
    const search = vi.fn()
      .mockImplementationOnce(() => new Promise((res) => { releaseOld = res; }))
      .mockResolvedValueOnce([B]);
    render(<DiscoveryTrackSearch search={search} onPick={() => {}} />);
    fireEvent.change(input(), { target: { value: "ja" } });
    await waitFor(() => expect(search).toHaveBeenCalledTimes(1));
    fireEvent.change(input(), { target: { value: "jasmine" } });
    await waitFor(() => expect(screen.getByText(/Jasmine Tea/)).toBeTruthy());
    await act(async () => { releaseOld([A]); });
    expect(screen.queryByText(/Bite The Hand/)).toBeNull();
  });

  it("campo vuoto: niente ricerca, niente lista", async () => {
    const { search } = setup();
    fireEvent.change(input(), { target: { value: "  " } });
    await new Promise((r) => setTimeout(r, 320));
    expect(search).not.toHaveBeenCalled();
    expect(screen.queryByRole("listbox")).toBeNull();
  });
});
```

- [ ] **Step 2: Verifica che fallisca**

Run: `cd frontend && npx vitest run tests/discovery-track-search.test.tsx`
Expected: modulo non trovato.

- [ ] **Step 3: Implementa**

```tsx
// frontend/components/discovery-track-search.tsx
"use client";

import { useEffect, useId, useRef, useState } from "react";

import { TrackCover } from "@/components/track-cover";
import { Input } from "@/components/ui";
import { useT } from "@/lib/i18n";
import type { Track } from "@/lib/api/types";
import { cn } from "@/lib/cn";

const DEBOUNCE_MS = 250;

/* Un campo di testo sulla libreria: i simili partono da una traccia posseduta,
   e qui la si trova per artista o titolo. Il Combobox del DS filtra una lista
   già in mano; qui la lista arriva dal backend a ogni pausa di digitazione, e
   una risposta vecchia non deve sovrascrivere quella nuova (contatore di giro). */
export function DiscoveryTrackSearch({ search, onPick, disabled }: {
  search: (q: string) => Promise<Track[]>;
  onPick: (track: Track) => void;
  disabled?: boolean;
}) {
  const t = useT();
  const [q, setQ] = useState("");
  const [results, setResults] = useState<Track[] | null>(null);
  const [active, setActive] = useState(-1);
  const [open, setOpen] = useState(false);
  const listId = useId();
  const turn = useRef(0);
  const blurTimer = useRef<number | null>(null);
  useEffect(() => () => { if (blurTimer.current != null) window.clearTimeout(blurTimer.current); }, []);

  useEffect(() => {
    const term = q.trim();
    const mine = ++turn.current;
    if (!term) { setResults(null); return; }
    const id = window.setTimeout(() => {
      search(term)
        .then((rows) => { if (turn.current === mine) { setResults(rows); setActive(-1); setOpen(true); } })
        .catch(() => { if (turn.current === mine) setResults([]); });
    }, DEBOUNCE_MS);
    return () => window.clearTimeout(id);
  }, [q, search]);

  const choose = (track: Track) => {
    onPick(track);
    setOpen(false);
    setActive(-1);
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (!results) return;
    if (e.key === "Escape") { setOpen(false); return; }
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      setOpen(true);
      setActive((a) => Math.max(0, Math.min(results.length - 1, e.key === "ArrowDown" ? a + 1 : a - 1)));
      return;
    }
    if (e.key === "Enter" && open && active >= 0 && results[active]) {
      e.preventDefault();
      choose(results[active]);
    }
  };

  return (
    <div className="relative w-full">
      <Input
        role="combobox"
        aria-expanded={open}
        aria-controls={listId}
        aria-activedescendant={active >= 0 ? `${listId}-opt-${active}` : undefined}
        autoComplete="off"
        value={q}
        disabled={disabled}
        placeholder={t.discovery.trackSearchPlaceholder}
        onFocus={() => setOpen(true)}
        onChange={(e) => setQ(e.target.value)}
        onKeyDown={onKeyDown}
        onBlur={() => { blurTimer.current = window.setTimeout(() => setOpen(false), 120); }}
      />
      <p className="mt-1 text-xs text-muted">{t.discovery.trackSearchHint}</p>
      {open && results !== null && (
        results.length === 0 ? (
          <p className="mt-1 text-xs text-faint">{t.discovery.trackSearchEmpty}</p>
        ) : (
          <ul
            id={listId}
            role="listbox"
            className="absolute left-0 top-10 z-30 mt-1 max-h-72 w-full overflow-y-auto border border-border-strong bg-surface"
          >
            {results.map((track, i) => (
              <li
                key={track.id}
                id={`${listId}-opt-${i}`}
                role="option"
                aria-selected={i === active}
                onMouseDown={(e) => { e.preventDefault(); choose(track); }}
                onMouseEnter={() => setActive(i)}
                className={cn(
                  "flex cursor-pointer items-center gap-3 px-3 py-1.5 text-sm",
                  i === active ? "bg-elevated text-fg" : "text-muted",
                )}
              >
                <TrackCover track={track} className="h-8 w-8 shrink-0" iconSize={12} />
                <span className="truncate">{track.artist} — {track.title}</span>
              </li>
            ))}
          </ul>
        )
      )}
    </div>
  );
}
```

- [ ] **Step 4: Verifica**

Run: `cd frontend && npx vitest run tests/discovery-track-search.test.tsx`
Expected: 6 verdi. Se `TrackCover` prova a caricare un'immagine e jsdom si lamenta, è un warning, non un errore: non mockarlo.

- [ ] **Step 5: Commit**

```bash
git add frontend/components/discovery-track-search.tsx frontend/tests/discovery-track-search.test.tsx
git commit -m "feat(discovery): la ricerca traccia per i simili, dalla barra"
```

---

### Task 10: `DiscoveryDigBar` riscritta, e l'intestazione dei simili perde l'interruttore

**Files:**
- Rewrite: `frontend/components/discovery-dig-bar.tsx`, `frontend/tests/discovery-dig-bar.test.tsx`
- Modify: `frontend/components/discovery-similar-header.tsx:44-52, 96-110`, `frontend/tests/discovery-similar-header.test.tsx`

**Interfaces:**
- Consumes: `DiscoverySeedPicker` (Task 8), `DiscoveryTrackSearch` (Task 9), `DigSeed/MAX_SEEDS` (Task 7), `DiscoveryPile/GenreCount/Track` (Task 7), `DEPTHS/WINDOW_ITEMS/DigSourceKey` da `@/lib/discovery-dig`.
- Produces:

```ts
export type DigMode = "seeds" | "track";

export function DiscoveryDigBar(props: {
  mode: DigMode; onModeChange: (m: DigMode) => void;
  seeds: DigSeed[]; onSeedsChange: (s: DigSeed[]) => void;
  depth: number; onDepthChange: (v: number) => void;
  source: DigSourceKey; onSourceChange: (s: DigSourceKey) => void;
  discogsEnabled: boolean;
  stylePeriod: boolean; onStylePeriodChange: (v: boolean) => void;
  options: { genres: { library: string[]; styles: string[] }; labels: string[]; genreCounts: GenreCount[] };
  piles: DiscoveryPile[] | null;
  busy: boolean;
  onSubmit: () => void; onSurprise: () => void; canSurprise: boolean;
  onPickTrack: (t: Track) => void;
  searchTracks: (q: string) => Promise<Track[]>;
}): JSX.Element
```

- `DiscoverySimilarHeader` props: `{ data; track }` soltanto.

- [ ] **Step 1: Riscrivi il test della barra**

Sostituisci per intero `frontend/tests/discovery-dig-bar.test.tsx`:

```tsx
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

import { DiscoveryDigBar } from "@/components/discovery-dig-bar";
import type { DigSeed } from "@/lib/discovery-seeds";
import type { DiscoveryPile } from "@/lib/api/types";

afterEach(cleanup);

const OPTIONS = {
  genres: { library: ["Acid House"], styles: [] },
  labels: ["Trax Records"],
  genreCounts: [{ genre: "Acid House", count: 3 }],
};
const DEEP: DigSeed = { type: "genre", value: "Deep House" };
const pile = (value: string, total: number, reach: number): DiscoveryPile =>
  ({ seed_type: "genre", value, total, reach, resolution: total ? "style" : null });

function setup(over: Partial<React.ComponentProps<typeof DiscoveryDigBar>> = {}) {
  const props = {
    mode: "seeds" as const, onModeChange: vi.fn(),
    seeds: [DEEP], onSeedsChange: vi.fn(),
    depth: 0, onDepthChange: vi.fn(),
    source: "discogs" as const, onSourceChange: vi.fn(), discogsEnabled: true,
    stylePeriod: false, onStylePeriodChange: vi.fn(),
    options: OPTIONS, piles: null as DiscoveryPile[] | null,
    busy: false, onSubmit: vi.fn(), onSurprise: vi.fn(), canSurprise: true,
    onPickTrack: vi.fn(), searchTracks: vi.fn().mockResolvedValue([]),
    ...over,
  };
  render(<DiscoveryDigBar {...props} />);
  return props;
}

describe("DiscoveryDigBar, modo semi", () => {
  it("mostra il selettore di modo, la sorgente e la profondità", () => {
    setup();
    expect(screen.getByText("Generi ed etichette")).toBeTruthy();
    expect(screen.getByText("Traccia")).toBeTruthy();
    expect(screen.getByText("Discogs")).toBeTruthy();
    expect(screen.getByText("Superficie")).toBeTruthy();
    expect(screen.queryByLabelText(/Stile e periodo/)).toBeNull();
  });

  it("commutare il modo avvisa il chiamante", () => {
    const p = setup();
    fireEvent.click(screen.getByText("Traccia"));
    expect(p.onModeChange).toHaveBeenCalledWith("track");
  });

  it("a Discogs spento il selettore sorgente non c'è", () => {
    setup({ discogsEnabled: false, source: "bandcamp" });
    expect(screen.queryByText("Discogs")).toBeNull();
  });

  it("Scava è disabilitato senza semi", () => {
    setup({ seeds: [] });
    expect(screen.getByText("Scava").closest("button")?.hasAttribute("disabled")).toBe(true);
  });

  it("il submit del form chiama onSubmit", () => {
    const p = setup();
    fireEvent.click(screen.getByText("Scava"));
    expect(p.onSubmit).toHaveBeenCalledTimes(1);
  });

  it("la profondità notifica il valore del preset", () => {
    const p = setup();
    fireEvent.click(screen.getByText("In fondo"));
    expect(p.onDepthChange).toHaveBeenCalledWith(1);
  });

  it("su pile tutte corte la profondità è inerte", () => {
    setup({ piles: [pile("Deep House", 200, 200)] });
    expect(screen.getByText("Superficie").closest("button")?.hasAttribute("disabled")).toBe(true);
    expect(screen.getByText("pila corta: tutta qui")).toBeTruthy();
  });

  it("la soglia di pila corta è il budget per seme, non 300", () => {
    // Due semi: 150 item a testa. Una pila da 200 NON è più corta.
    const seeds = [DEEP, { type: "genre" as const, value: "Electro" }];
    setup({ seeds, piles: [pile("Deep House", 200, 200), pile("Electro", 200, 200)] });
    expect(screen.getByText("Superficie").closest("button")?.hasAttribute("disabled")).toBe(false);
  });

  it("pile tutte vuote: seme sconosciuto, non pila corta", () => {
    setup({ piles: [pile("Deep House", 0, 0)] });
    expect(screen.getByText("nessuna pila: Discogs non conosce questo seme")).toBeTruthy();
    expect(screen.queryByText("pila corta: tutta qui")).toBeNull();
  });

  it("un seme morto fra altri vivi si dice per nome", () => {
    const seeds = [DEEP, { type: "genre" as const, value: "Inesistente" }];
    setup({ seeds, piles: [pile("Deep House", 5000, 5000), pile("Inesistente", 0, 0)] });
    expect(screen.getByText(/non conosce “Inesistente”/)).toBeTruthy();
    expect(screen.getByText("Superficie").closest("button")?.hasAttribute("disabled")).toBe(false);
  });

  it("Sorprendimi chiama onSurprise ed è spento a pool vuoto", () => {
    const p = setup();
    fireEvent.click(screen.getByText("Sorprendimi"));
    expect(p.onSurprise).toHaveBeenCalledTimes(1);
    cleanup();
    setup({ canSurprise: false });
    expect(screen.getByText("Sorprendimi").closest("button")?.hasAttribute("disabled")).toBe(true);
  });

  it("propaga il cambio di sorgente", () => {
    const p = setup();
    fireEvent.click(screen.getByText("Bandcamp"));
    expect(p.onSourceChange).toHaveBeenCalledWith("bandcamp");
  });
});

describe("DiscoveryDigBar, modo traccia", () => {
  it("mostra la ricerca e l'interruttore, nasconde sorgente, profondità e bottoni", () => {
    setup({ mode: "track" });
    expect(screen.getByPlaceholderText("Cerca una traccia della libreria…")).toBeTruthy();
    expect(screen.getByLabelText(/Stile e periodo/)).toBeTruthy();
    expect(screen.queryByText("Discogs")).toBeNull();
    expect(screen.queryByText("Superficie")).toBeNull();
    expect(screen.queryByText("Scava")).toBeNull();
    expect(screen.queryByText("Sorprendimi")).toBeNull();
  });

  it("l'interruttore avvisa il chiamante", () => {
    const p = setup({ mode: "track" });
    fireEvent.click(screen.getByLabelText(/Stile e periodo/));
    expect(p.onStylePeriodChange).toHaveBeenCalledWith(true);
  });

  it("busy disabilita l'interruttore", () => {
    setup({ mode: "track", busy: true });
    expect((screen.getByLabelText(/Stile e periodo/) as HTMLInputElement).disabled).toBe(true);
  });
});
```

- [ ] **Step 2: Riscrivi la barra**

Sostituisci per intero `frontend/components/discovery-dig-bar.tsx`:

```tsx
"use client";

import { Dices, Shovel } from "lucide-react";

import { Button, Checkbox, SegmentedControl, Spinner } from "@/components/ui";
import { DiscoverySeedPicker } from "@/components/discovery-seed-picker";
import { DiscoveryTrackSearch } from "@/components/discovery-track-search";
import { useI18n } from "@/lib/i18n";
import type { DiscoveryPile, GenreCount, Track } from "@/lib/api/types";
import { DEPTHS, WINDOW_ITEMS, type DigSourceKey } from "@/lib/discovery-dig";
import type { DigSeed } from "@/lib/discovery-seeds";

export type DigMode = "seeds" | "track";

/* Un riquadro, tre righe: i controlli del modo, il soggetto (semi o traccia),
   la tavolozza. Il modo è stato locale della pagina, non URL: commutarlo cambia
   solo quale campo si vede. In modo traccia sorgente e profondità lasciano il
   posto all'interruttore stile/periodo (i simili sono solo Bandcamp). */
export function DiscoveryDigBar({
  mode, onModeChange, seeds, onSeedsChange, depth, onDepthChange,
  source, onSourceChange, discogsEnabled, stylePeriod, onStylePeriodChange,
  options, piles, busy, onSubmit, onSurprise, canSurprise, onPickTrack, searchTracks,
}: {
  mode: DigMode;
  onModeChange: (m: DigMode) => void;
  seeds: DigSeed[];
  onSeedsChange: (s: DigSeed[]) => void;
  depth: number;
  onDepthChange: (v: number) => void;
  source: DigSourceKey;
  onSourceChange: (s: DigSourceKey) => void;
  discogsEnabled: boolean;
  stylePeriod: boolean;
  onStylePeriodChange: (v: boolean) => void;
  options: {
    genres: { library: string[]; styles: string[] };
    labels: string[];
    genreCounts: GenreCount[];
  };
  piles: DiscoveryPile[] | null;
  busy: boolean;
  onSubmit: () => void;
  onSurprise: () => void;
  canSurprise: boolean;
  onPickTrack: (t: Track) => void;
  searchTracks: (q: string) => Promise<Track[]>;
}) {
  const { t, lang } = useI18n();
  const srcName = source === "bandcamp" ? t.discovery.sourceBandcamp : t.discovery.sourceDiscogs;

  const depthOptions = DEPTHS.map((d) => ({
    value: String(d.value),
    label: t.discovery[d.key === "surface" ? "depthSurface" : d.key === "mid" ? "depthMid" : "depthDeep"],
  }));
  const activeDepth = DEPTHS.reduce((best, d) =>
    Math.abs(d.value - depth) < Math.abs(best.value - depth) ? d : best, DEPTHS[0]);
  const depthDesc = t.discovery[
    activeDepth.key === "surface" ? "depthSurfaceDesc"
      : activeDepth.key === "mid" ? "depthMidDesc" : "depthDeepDesc"
  ];

  // La soglia di "pila corta" è la quota di finestra di QUESTO scavo (300 diviso
  // i semi), non 300: con due semi una pila da 200 non è corta.
  const budget = Math.floor(WINDOW_ITEMS / Math.max(1, seeds.length));
  const live = piles?.filter((p) => p.total > 0) ?? [];
  const dead = piles?.filter((p) => p.total === 0) ?? [];
  const emptyPile = piles != null && piles.length > 0 && live.length === 0;
  const shortPile = live.length > 0 && live.every((p) => p.reach <= budget);
  const depthInert = emptyPile || shortPile;

  const hint = emptyPile
    ? t.discovery.emptyPile(srcName)
    : shortPile
      ? t.discovery.shortPile
      : dead.length > 0
        ? t.discovery.deadSeeds(dead.map((p) => `“${p.value}”`).join(", "), srcName)
        : depthDesc;

  return (
    <form
      onSubmit={(e) => { e.preventDefault(); if (mode === "seeds") onSubmit(); }}
      className="mb-6 border border-border p-4"
    >
      <div className="flex flex-wrap items-center gap-x-4 gap-y-3">
        <div className="flex items-center gap-2">
          <span className="text-[10px] uppercase tracking-wider text-muted">{t.discovery.modeLabel}</span>
          <SegmentedControl<DigMode>
            value={mode}
            onChange={onModeChange}
            options={[
              { value: "seeds", label: t.discovery.modeSeeds },
              { value: "track", label: t.discovery.modeTrack },
            ]}
            disabled={busy}
          />
        </div>

        {mode === "seeds" && discogsEnabled && (
          <div className="flex items-center gap-2">
            <span className="text-[10px] uppercase tracking-wider text-muted">{t.discovery.sourceLabel}</span>
            <SegmentedControl
              value={source}
              onChange={onSourceChange}
              options={[
                { value: "discogs", label: t.discovery.sourceDiscogs },
                { value: "bandcamp", label: t.discovery.sourceBandcamp },
              ]}
              disabled={busy}
            />
          </div>
        )}

        {mode === "seeds" ? (
          <div className="flex items-center gap-2">
            <span className="text-[10px] uppercase tracking-wider text-muted">{t.discovery.depthLabel}</span>
            <SegmentedControl
              value={String(activeDepth.value)}
              onChange={(v) => onDepthChange(Number(v))}
              options={depthOptions}
              disabled={busy || depthInert}
            />
          </div>
        ) : (
          <Checkbox
            label={t.discovery.similarStylePeriod}
            checked={stylePeriod}
            onChange={onStylePeriodChange}
            disabled={busy}
          />
        )}
      </div>

      <div className="mt-4">
        {mode === "seeds" ? (
          <div className="flex flex-col gap-3">
            <DiscoverySeedPicker seeds={seeds} onChange={onSeedsChange} options={options} disabled={busy} />
            <div className="flex flex-wrap items-center gap-2">
              <Button type="submit" disabled={busy || seeds.length === 0} className="w-full sm:w-auto">
                {busy ? <Spinner /> : <Shovel size={15} />} {t.discovery.dig}
              </Button>
              <Button
                type="button"
                variant="outline"
                onClick={onSurprise}
                disabled={busy || !canSurprise}
                title={canSurprise ? undefined : t.discovery.surpriseEmpty}
                className="w-full sm:w-auto"
              >
                <Dices size={15} /> {t.discovery.surprise}
              </Button>
              <p className="text-xs text-muted">{hint}</p>
            </div>
          </div>
        ) : (
          <DiscoveryTrackSearch search={searchTracks} onPick={onPickTrack} disabled={busy} />
        )}
      </div>
    </form>
  );
}
```

(`lang` non è usato: rimuovilo dalla destrutturazione se ESLint lo segnala — resta `const { t } = useI18n();`.)

- [ ] **Step 3: L'intestazione perde l'interruttore**

In `frontend/components/discovery-similar-header.tsx`: rimuovi `Checkbox` dall'import; la firma diventa `({ data, track }: { data: DiscoverySimilarResponse; track: Track })`; elimina il blocco `<Checkbox … />` lasciando i chip degli archi dentro `<div className="flex flex-col items-end gap-2">`. Aggiorna il commento in cima al componente: «L'interruttore stile/periodo sta nella barra (modo Traccia): qui solo l'origine e gli archi».

In `frontend/tests/discovery-similar-header.test.tsx`: in ogni `render(...)` togli `stylePeriod={false} onStylePeriodChange={…} busy={false}`; elimina il test `"l'interruttore stile e periodo avvisa il chiamante"` (ora è coperto da `discovery-dig-bar.test.tsx`, modo traccia).

- [ ] **Step 4: Verifica**

Run: `cd frontend && npx vitest run tests/discovery-dig-bar.test.tsx tests/discovery-similar-header.test.tsx`
Expected: tutti verdi. `tsc` resta rosso solo su `app/discovery/page.tsx` (Task 11).

- [ ] **Step 5: Commit**

```bash
git add frontend/components/discovery-dig-bar.tsx frontend/tests/discovery-dig-bar.test.tsx frontend/components/discovery-similar-header.tsx frontend/tests/discovery-similar-header.test.tsx
git commit -m "feat(discovery): la barra a due modi — semi con tavolozza, o traccia

Il selettore sorgente sparisce a Discogs spento e in modo traccia; la
profondità lascia il posto all'interruttore stile/periodo, che esce
dall'intestazione dei simili. La soglia di pila corta è la quota per seme."
```

---

### Task 11: La pagina — semi nell'URL, simili dalla barra, Discogs spento

**Files:**
- Modify: `frontend/app/discovery/page.tsx` (riscrittura della parte di stato e della render)
- Modify: `frontend/tests/discovery-page-modalita.test.tsx`

**Interfaces:**
- Consumes: tutto dei Task 7-10; `getDiscoverySettings`, `searchTracks`, `apiGet<GenreCount[]>("/api/library/genres")`.
- Comportamenti da rispettare (dal test):
  - `?seeds=…` avvia lo scavo; `?seed=&value=` non esiste più (nessun dig).
  - Il dig NON parte finché la preferenza Discogs non è nota; `source=discogs` con Discogs spento degrada a `bandcamp` nella chiamata.
  - Scegliere una traccia → `router.push(similarHref(id, stylePeriodLocale, null))`.
  - `Modo` locale: entrare in `?similar=` mostra la barra in modo traccia; commutare a semi non cambia l'URL e non azzera i risultati.
  - Sorprendimi mette UN seme in barra e naviga.

- [ ] **Step 1: Aggiorna i test di pagina**

In `frontend/tests/discovery-page-modalita.test.tsx`:

1. Nel mock di `@/lib/api` aggiungi:

```ts
  getDiscoverySettings: () => Promise.resolve({ discogs_enabled: true }),
  searchTracks: (...a: unknown[]) => searchTracks(...a),
```

con `const searchTracks = vi.fn();` accanto agli altri, e fai sì che `apiGet` risponda per `/api/library/genres`: sostituisci `apiGet.mockResolvedValue(TRACK)` ovunque con `apiGet.mockImplementation((path: string) => Promise.resolve(path === "/api/library/genres" ? [] : TRACK))`.

2. `DIG` diventa:

```ts
const DIG: DiscoveryDigResponse = {
  seeds: [{ type: "label", value: "Warp Records" }], source: "discogs", leads: [],
  piles: [{ seed_type: "label", value: "Warp Records", total: 5000, reach: 500, resolution: "label" }],
};
```

e `AVVISO_PILA` diventa `dict.discovery.broadSeeds(dict.discovery.broadSeedDetail("Warp Records", (5000).toLocaleString("it"), (500).toLocaleString("it")), dict.discovery.sourceDiscogs)`.

3. Ogni `new URLSearchParams("seed=label&value=Warp Records&depth=0&source=discogs")` → `new URLSearchParams("seeds=label:Warp%20Records&depth=0&source=discogs")`.

4. Nel test `"un'altra traccia invece azzera il risultato e mostra lo spinner"` l'asserzione `expect(screen.queryByLabelText(INTERRUTTORE)).toBeNull()` diventa `expect(screen.queryByText(dict.discovery.similarFrom)).toBeNull()`: l'interruttore ora vive nella barra, sempre montata; è l'intestazione a sparire. In cima al file aggiungi `import { digHref } from "@/lib/discovery-seeds";` accanto all'import di `similarHref` (serve al describe nuovo).

5. Aggiungi in coda un terzo `describe`:

```tsx
describe("pagina Discovery, la barra a due modi", () => {
  it("scegliere una traccia porta ai simili con l'interruttore locale", async () => {
    searchTracks.mockResolvedValue([TRACK]);
    query = new URLSearchParams();
    push.mockClear();
    render(<DiscoveryPage />);
    fireEvent.click(screen.getByText(dict.discovery.modeTrack));
    fireEvent.click(screen.getByLabelText(INTERRUTTORE));      // acceso, ma solo in locale
    expect(push).not.toHaveBeenCalled();
    fireEvent.change(screen.getByPlaceholderText(dict.discovery.trackSearchPlaceholder), { target: { value: "jas" } });
    await waitFor(() => expect(screen.getByText(/Bite The Hand/)).toBeTruthy());
    fireEvent.mouseDown(screen.getByText(/Bite The Hand/));
    expect(push).toHaveBeenCalledWith(similarHref(5, true, null), { scroll: false });
  });

  it("in ?similar= la barra è in modo traccia e commutare a semi non tocca l'URL", async () => {
    discoverySimilar.mockResolvedValue(SIM);
    query = new URLSearchParams("similar=5");
    push.mockClear();
    render(<DiscoveryPage />);
    await waitFor(() => expect(screen.getByText(dict.discovery.similarFrom)).toBeTruthy());
    expect(screen.getByPlaceholderText(dict.discovery.trackSearchPlaceholder)).toBeTruthy();
    fireEvent.click(screen.getByText(dict.discovery.modeSeeds));
    expect(push).not.toHaveBeenCalled();
    expect(screen.getByText(dict.discovery.similarFrom)).toBeTruthy();   // i risultati restano
  });

  it("Scava scrive i semi nell'URL", async () => {
    query = new URLSearchParams();
    push.mockClear();
    render(<DiscoveryPage />);
    const campo = screen.getAllByRole("combobox")[0];
    fireEvent.change(campo, { target: { value: "Deep House" } });
    fireEvent.keyDown(campo, { key: "Enter" });
    fireEvent.change(campo, { target: { value: "Electro" } });
    fireEvent.keyDown(campo, { key: "Enter" });
    fireEvent.click(screen.getByText(dict.discovery.dig));
    expect(push).toHaveBeenCalledWith(
      digHref("/discovery", [{ type: "genre", value: "Deep House" }, { type: "genre", value: "Electro" }], 0, "discogs"),
      { scroll: false });
  });

  it("il vecchio ?seed=&value= non fa partire nulla", () => {
    query = new URLSearchParams("seed=genre&value=House");
    render(<DiscoveryPage />);
    expect(discoveryDig).not.toHaveBeenCalled();
  });
});

describe("pagina Discovery, Discogs spento", () => {
  it("un URL con source=discogs scava su Bandcamp e non mostra il selettore", async () => {
    vi.doMock("@/lib/api", async (importOriginal) => ({
      ...(await importOriginal<Record<string, unknown>>()),
      discoveryDig: (...a: unknown[]) => discoveryDig(...a),
      discoverySimilar: (...a: unknown[]) => discoverySimilar(...a),
      apiGet: (...a: unknown[]) => apiGet(...a),
      getDiscoveryGenres: () => Promise.resolve({ library: [], styles: [] }),
      getLabels: () => Promise.resolve([]),
      getDiscoverySettings: () => Promise.resolve({ discogs_enabled: false }),
      searchTracks: (...a: unknown[]) => searchTracks(...a),
    }));
    vi.resetModules();
    const { default: Page } = await import("@/app/discovery/page");
    discoveryDig.mockClear();
    discoveryDig.mockResolvedValue({ ...DIG, source: "bandcamp" });
    query = new URLSearchParams("seeds=label:Warp%20Records&depth=0&source=discogs");
    render(<Page />);
    await waitFor(() => expect(discoveryDig).toHaveBeenCalled());
    expect(discoveryDig).toHaveBeenCalledWith(
      [{ type: "label", value: "Warp Records" }], { depth: 0, source: "bandcamp" });
    expect(screen.queryByText(dict.discovery.sourceDiscogs)).toBeNull();
    vi.doUnmock("@/lib/api");
    vi.resetModules();
  });
});
```

Aggiungi in cima `let discoveryDig`/`searchTracks` come già fatto per gli altri mock, e in ogni test esistente che parte da `?seeds=` assicurati che `discoveryDig.mockClear()` non sia necessario (i test asseriscono su `push` e sul DOM).

- [ ] **Step 2: Verifica che fallisca**

Run: `cd frontend && npx vitest run tests/discovery-page-modalita.test.tsx 2>&1 | tail -15`
Expected: falliscono i test nuovi e quelli col nuovo `?seeds=`.

- [ ] **Step 3: Riscrivi la pagina**

In `frontend/app/discovery/page.tsx` sostituisci gli import e la parte di stato/logica. Import:

```tsx
import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { ArrowLeft, Disc3 } from "lucide-react";
import {
  apiGet,
  discoveryDig,
  discoverySimilar,
  errText,
  getDiscoveryGenres,
  getDiscoverySettings,
  getLabels,
  searchTracks,
  type DiscoveryDigResponse,
  type DiscoveryGenres,
  type DiscoverySimilarResponse,
  type GenreCount,
  type LabelStats,
  type Track,
  type TrackDetail,
} from "@/lib/api";
import { Alert, Chip, EmptyState, Loading, SegmentedControl } from "@/components/ui";
import { PageLayout } from "@/components/page-layout";
import { useJobs } from "@/components/jobs-provider";
import { applyLens, DiscoveryLeadGrid, FORMAT_VALUES, type SortMode } from "@/components/discovery-lead-grid";
import { DiscoveryDigBar, type DigMode } from "@/components/discovery-dig-bar";
import { DiscoverySimilarHeader } from "@/components/discovery-similar-header";
import { similarHref, WINDOW_ITEMS, type DigSourceKey } from "@/lib/discovery-dig";
import { digHref, parseSeeds, sameSeeds, type DigSeed } from "@/lib/discovery-seeds";
import { isInternalPath, withFrom } from "@/lib/back-link";
import { pickSurprise } from "@/lib/discovery-surprise";
import { useI18n } from "@/lib/i18n";
```

Stato (sostituisce da `const initialSeed` fino a `const [dig, setDig]` incluso):

```tsx
  const initialDepthRaw = Number(searchParams.get("depth") ?? "0");
  const initialDepth = Number.isFinite(initialDepthRaw) ? Math.min(1, Math.max(0, initialDepthRaw)) : 0;
  const initialSource: DigSourceKey =
    searchParams.get("source") === "bandcamp" ? "bandcamp" : "discogs";
  const [genres, setGenres] = useState<DiscoveryGenres | null>(null);
  const [labels, setLabels] = useState<LabelStats[] | null>(null);
  const [genreCounts, setGenreCounts] = useState<GenreCount[]>([]);
  // `null` = preferenza non ancora letta: lo scavo aspetta, perché un URL con
  // source=discogs a Discogs spento deve degradare a Bandcamp PRIMA di partire.
  const [discogsEnabled, setDiscogsEnabled] = useState<boolean | null>(null);

  // I semi in barra: stato locale, la verità dello scavo è nell'URL (`seeds=`).
  const [seeds, setSeeds] = useState<DigSeed[]>(() => parseSeeds(searchParams.get("seeds")));
  const [depth, setDepth] = useState(initialDepth);
  const [source, setSource] = useState<DigSourceKey>(initialSource);
  const [dig, setDig] = useState<DiscoveryDigResponse | null>(null);
```

Dopo `const stylePeriod = searchParams.get("style_period") === "1";` (che diventa `const urlStylePeriod = …`) aggiungi:

```tsx
  // Il modo è stato locale: commutarlo cambia solo quale campo si vede. L'URL
  // si muove quando parte una ricerca. All'apertura si deduce da cosa c'è.
  const [mode, setMode] = useState<DigMode>(isSimilar ? "track" : "seeds");
  // L'interruttore vive nell'URL quando c'è una traccia (come prima), in locale
  // prima di sceglierla: così si accende PRIMA di cercare e viaggia col push.
  const [localStylePeriod, setLocalStylePeriod] = useState(urlStylePeriod);
  const stylePeriod = isSimilar ? urlStylePeriod : localStylePeriod;
```

e rinomina ogni uso successivo di `stylePeriod` nella pagina per coerenza (l'effect dei simili e `similarEmpty` leggono `stylePeriod`: resta corretto).

`surprisePool`/`canSurprise` invariati. L'effect di caricamento diventa:

```tsx
  useEffect(() => {
    getDiscoveryGenres().then(setGenres).catch(() => setGenres({ library: [], styles: [] }));
    getLabels().then(setLabels).catch(() => setLabels([]));
    apiGet<GenreCount[]>("/api/library/genres").then(setGenreCounts).catch(() => setGenreCounts([]));
    getDiscoverySettings()
      .then((s) => setDiscogsEnabled(s.discogs_enabled))
      .catch(() => setDiscogsEnabled(true));
  }, []);
```

`executeDig`:

```tsx
  const executeDig = useCallback(
    async (list: DigSeed[], d: number, src: DigSourceKey) => {
      setBusy(true);
      setError(null);
      setDig(null);
      const sourceName = src === "bandcamp" ? t.discovery.sourceBandcamp : t.discovery.sourceDiscogs;
      jobs.startClientJob("dig", t.jobs.dig);
      jobs.updateClientJob("dig", { detail: `${sourceName} · ${list.map((s) => s.value).join(", ")}` });
      try {
        setDig(await discoveryDig(list, { depth: d, source: src }));
      } catch (e) {
        setError(errText(e));
      } finally {
        setBusy(false);
        jobs.endClientJob("dig");
      }
    },
    [jobs, t],
  );
```

L'effect dello scavo:

```tsx
  const paramsKey = searchParams.toString();
  useEffect(() => {
    if (isSimilar) return;
    if (discogsEnabled === null) return;   // la preferenza decide la sorgente: si aspetta
    const list = parseSeeds(searchParams.get("seeds"));
    if (list.length === 0) return;         // pagina aperta senza uno scavo: empty state
    const depthRaw = Number(searchParams.get("depth") ?? "0");
    const d = Number.isFinite(depthRaw) ? Math.min(1, Math.max(0, depthRaw)) : 0;
    const wanted: DigSourceKey = searchParams.get("source") === "bandcamp" ? "bandcamp" : "discogs";
    // Discogs spento: un link con source=discogs degrada, non fallisce.
    const src: DigSourceKey = !discogsEnabled && wanted === "discogs" ? "bandcamp" : wanted;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- il dig è l'external system: l'effect risincronizza i risultati sull'URL (query string), non su state locale
    executeDig(list, d, src);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [paramsKey, discogsEnabled]);
```

Aggiungi, dopo il caricamento della preferenza, l'allineamento della sorgente in barra:

```tsx
  // A Discogs spento la barra offre solo Bandcamp: la sorgente locale si
  // allinea, così il prossimo Scava non scrive un source che la barra non mostra.
  useEffect(() => {
    if (discogsEnabled === false && source === "discogs") setSource("bandcamp");
  }, [discogsEnabled, source]);
```

`setStylePeriod`:

```tsx
  const setStylePeriod = (on: boolean) => {
    setLocalStylePeriod(on);
    if (isSimilar) router.push(similarHref(similarId, on, from), { scroll: false });
  };
```

`runDig`, `navigateDig`, `runSurprise`:

```tsx
  const runDig = () => {
    if (seeds.length === 0) return;
    surpriseRef.current = false;
    surpriseRerolledRef.current = false;
    const href = digHref(pathname, seeds, depth, source);
    // Stesso URL: ricerca deterministica, stesso risultato. Niente voce doppia
    // nella cronologia.
    if (href === `${pathname}?${searchParams.toString()}`) return;
    router.push(href, { scroll: false });
  };

  const navigateDig = (seed: DigSeed, d: number) => {
    // Sorprendimi (e il reroll) mettono UN seme in barra e aggiornano l'URL: il
    // componente non rimonta, quindi lo state va allineato a mano. La sorgente
    // resta quella scelta: si pesca un seme, non una sorgente.
    setSeeds([seed]);
    setDepth(d);
    router.push(digHref(pathname, [seed], d, source), { scroll: false });
  };

  const runSurprise = () => {
    const pick = pickSurprise(surprisePool, seeds.map((s) => s.value));
    if (!pick) return;
    surpriseRef.current = true;
    surpriseRerolledRef.current = false;
    navigateDig({ type: pick.seedType, value: pick.value }, pick.depth);
  };
```

Nell'effect del reroll: `const pick = pickSurprise(surprisePool, dig.seeds.map((s) => s.value));` e `navigateDig({ type: pick.seedType, value: pick.value }, pick.depth);`.

`pile` diventa:

```tsx
  // Le pile valgono per i semi CORRENTI in barra: cambiato un seme, la
  // profondità torna attiva finché non si riscava.
  const piles = dig && sameSeeds(dig.seeds, seeds) ? dig.piles : null;
```

`digEmpty`:

```tsx
  const digEmpty = (d: DiscoveryDigResponse) => {
    const srcName = d.source === "bandcamp" ? t.discovery.sourceBandcamp : t.discovery.sourceDiscogs;
    const names = d.seeds.map((s) => `“${s.value}”`).join(", ");
    const live = d.piles.filter((p) => p.total > 0);
    if (live.length === 0) {
      return (
        <EmptyState icon={<Disc3 size={28} />} title={t.discovery.deadSeedTitle(srcName)}>
          {t.discovery.deadSeedBody(names, srcName)}
        </EmptyState>
      );
    }
    if (d.leads.length === 0) {
      const budget = Math.floor(WINDOW_ITEMS / Math.max(1, d.seeds.length));
      const shortPile = live.every((p) => p.reach <= budget);
      return (
        <EmptyState icon={<Disc3 size={28} />} title={t.discovery.nothingToDigTitle}>
          {shortPile ? t.discovery.nothingToDigShortPile(names) : t.discovery.nothingToDigSeeds(names)}
        </EmptyState>
      );
    }
    return <p className="py-8 text-center text-sm text-muted">{t.discovery.noFormatMatch}</p>;
  };
```

Render — la barra è sempre montata; l'intestazione dei simili sotto; l'avviso "seme largo" dalle pile:

```tsx
      <DiscoveryDigBar
        mode={mode}
        onModeChange={setMode}
        seeds={seeds}
        onSeedsChange={setSeeds}
        depth={depth}
        onDepthChange={setDepth}
        source={source}
        onSourceChange={setSource}
        discogsEnabled={discogsEnabled !== false}
        stylePeriod={stylePeriod}
        onStylePeriodChange={setStylePeriod}
        options={{
          genres: genres ?? { library: [], styles: [] },
          labels: labels?.map((l) => l.label) ?? [],
          genreCounts,
        }}
        piles={piles}
        busy={busy}
        onSubmit={runDig}
        onSurprise={runSurprise}
        canSurprise={canSurprise}
        onPickTrack={(track: Track) => router.push(similarHref(track.id, localStylePeriod, null), { scroll: false })}
        searchTracks={searchTracks}
      />

      {isSimilar && sim && simTrack && (
        <DiscoverySimilarHeader data={sim} track={simTrack} />
      )}
```

e l'avviso sulla pila (dentro la riga delle lenti) diventa:

```tsx
          {!isSimilar && dig && dig.piles.some((p) => p.total > p.reach) && (
            <span className="tnum text-muted">
              {t.discovery.broadSeeds(
                dig.piles
                  .filter((p) => p.total > p.reach)
                  .map((p) => t.discovery.broadSeedDetail(
                    p.value, p.total.toLocaleString(lang), p.reach.toLocaleString(lang)))
                  .join("; "),
                dig.source === "bandcamp" ? t.discovery.sourceBandcamp : t.discovery.sourceDiscogs,
              )}
            </span>
          )}
```

L'empty state "pronto per scavare" resta per `!isSimilar && !busy && !dig`, con `seeds.length > 0 ? readyBodyReady : readyBodyNotReady`. Le chiavi `broadSeed`, `broadSeedLabel`, `nothingToDigBody`, `seedTypeValue`, `seedTypeStyle` in `it.ts`/`en.ts` non sono più usate: rimuovile da entrambi (`tsc` conferma che nessuno le legge).

- [ ] **Step 4: Verifica**

Run: `cd frontend && npx tsc --noEmit && npx vitest run && npm run lint`
Expected: tsc pulito, tutta la suite verde, lint pulito. Se lint segnala `react-hooks/exhaustive-deps` sull'effect di allineamento sorgente, le dipendenze `[discogsEnabled, source]` sono complete: non aggiungere disable.

- [ ] **Step 5: Verifica nel browser**

Con backend e frontend avviati (`preview_start`), apri `/discovery`:
1. Aggiungi due generi dalla tavolozza, Scava → l'URL ha `seeds=`, i lead arrivano, l'avviso sulla pila nomina entrambi se larghi.
2. Modo Traccia → cerca una traccia posseduta → click → `?similar=` con la barra ancora visibile in modo traccia e l'intestazione sotto.
3. Commuta a Generi ed etichette: i risultati dei simili restano.
Screenshot dei tre stati.

- [ ] **Step 6: Commit**

```bash
git add frontend/app/discovery/page.tsx frontend/tests/discovery-page-modalita.test.tsx frontend/lib/i18n/en.ts frontend/lib/i18n/it.ts
git commit -m "feat(discovery): la pagina Dig sui semi multipli, coi simili dalla barra

L'URL porta seeds=; il modo è stato locale e la barra resta montata anche
nei simili. Lo scavo aspetta la preferenza Discogs, così source=discogs a
Discogs spento degrada a Bandcamp prima di partire."
```

---

### Task 12: Impostazioni — il gruppo Discovery

**Files:**
- Create: `frontend/components/settings/discovery-section.tsx`, `frontend/tests/settings-discovery-section.test.tsx`
- Modify: `frontend/app/settings/page.tsx:67-70`

**Interfaces:**
- Consumes: `getDiscoverySettings`, `setDiscoverySettings` (Task 7); `t.settings.discovery*` (Task 7); `Checkbox, Loading, Alert` da `@/components/ui`.

- [ ] **Step 1: Test**

```tsx
// frontend/tests/settings-discovery-section.test.tsx
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

const getDiscoverySettings = vi.fn();
const setDiscoverySettings = vi.fn();
vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  getDiscoverySettings: () => getDiscoverySettings(),
  setDiscoverySettings: (s: unknown) => setDiscoverySettings(s),
}));

const { DiscoverySection } = await import("@/components/settings/discovery-section");

afterEach(cleanup);

describe("DiscoverySection", () => {
  it("legge la preferenza e la mostra", async () => {
    getDiscoverySettings.mockResolvedValue({ discogs_enabled: false });
    render(<DiscoverySection />);
    await waitFor(() =>
      expect((screen.getByLabelText(/Offri Discogs/) as HTMLInputElement).checked).toBe(false));
  });

  it("il click salva e riflette la risposta", async () => {
    getDiscoverySettings.mockResolvedValue({ discogs_enabled: true });
    setDiscoverySettings.mockResolvedValue({ discogs_enabled: false });
    render(<DiscoverySection />);
    await waitFor(() => expect(screen.getByLabelText(/Offri Discogs/)).toBeTruthy());
    fireEvent.click(screen.getByLabelText(/Offri Discogs/));
    expect(setDiscoverySettings).toHaveBeenCalledWith({ discogs_enabled: false });
    await waitFor(() =>
      expect((screen.getByLabelText(/Offri Discogs/) as HTMLInputElement).checked).toBe(false));
  });

  it("un salvataggio fallito lo dice e non cambia lo stato", async () => {
    getDiscoverySettings.mockResolvedValue({ discogs_enabled: true });
    setDiscoverySettings.mockRejectedValue(new Error("boom"));
    render(<DiscoverySection />);
    await waitFor(() => expect(screen.getByLabelText(/Offri Discogs/)).toBeTruthy());
    fireEvent.click(screen.getByLabelText(/Offri Discogs/));
    await waitFor(() => expect(screen.getByText(/boom/)).toBeTruthy());
    expect((screen.getByLabelText(/Offri Discogs/) as HTMLInputElement).checked).toBe(true);
  });
});
```

- [ ] **Step 2: Verifica che fallisca**

Run: `cd frontend && npx vitest run tests/settings-discovery-section.test.tsx`
Expected: modulo non trovato.

- [ ] **Step 3: Implementa**

```tsx
// frontend/components/settings/discovery-section.tsx
"use client";

import { useEffect, useState } from "react";

import { errText, getDiscoverySettings, setDiscoverySettings } from "@/lib/api";
import { Alert, Checkbox, Loading } from "@/components/ui";
import { useT } from "@/lib/i18n";

/* Il gruppo Discovery delle Impostazioni: per ora una sola preferenza, Discogs
   come sorgente nella barra del Dig. È presentazione: il backend accetta
   source=discogs comunque, e Organize col suo client Discogs non c'entra. */
export function DiscoverySection() {
  const t = useT();
  const [enabled, setEnabled] = useState<boolean | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getDiscoverySettings()
      .then((s) => setEnabled(s.discogs_enabled))
      .catch((e) => setError(errText(e)));
  }, []);

  const toggle = async (v: boolean) => {
    setError(null);
    try {
      setEnabled((await setDiscoverySettings({ discogs_enabled: v })).discogs_enabled);
    } catch (e) {
      setError(errText(e));
    }
  };

  return (
    <div className="border border-border p-5">
      {error && <div className="mb-3"><Alert tone="danger">{error}</Alert></div>}
      {enabled === null && !error ? <Loading /> : enabled !== null && (
        <>
          <Checkbox label={t.settings.discoveryDiscogs} checked={enabled} onChange={toggle} />
          <p className="mt-1 text-xs text-faint">{t.settings.discoveryDiscogsHint}</p>
        </>
      )}
    </div>
  );
}
```

In `frontend/app/settings/page.tsx`: import `DiscoverySection`; fra il blocco Lingua e `pathsHeading` inserisci:

```tsx
      <div className="mb-2 mt-8 text-[10px] uppercase tracking-wider text-muted">{t.settings.discoveryHeading}</div>
      <DiscoverySection />
```

Aggiorna il commento in cima alla pagina: «5 gruppi: Generale · Discovery · Percorsi e libreria · Servizi esterni · Organize».

- [ ] **Step 4: Verifica**

Run: `cd frontend && npx vitest run tests/settings-discovery-section.test.tsx && npx tsc --noEmit`
Expected: verdi, tsc pulito. Nel browser: `/settings` mostra il gruppo; spegnere Discogs e tornare su `/discovery` nasconde il selettore sorgente.

- [ ] **Step 5: Commit**

```bash
git add frontend/components/settings/discovery-section.tsx frontend/tests/settings-discovery-section.test.tsx frontend/app/settings/page.tsx
git commit -m "feat(settings): il gruppo Discovery, con l'interruttore Discogs"
```

---

### Task 13: Documentazione di stato

**Files:**
- Modify: `docs/ROADMAP.md:41-53`
- Modify: `PROGRESS.md:11-15`

- [ ] **Step 1: ROADMAP**

Nel bullet **Discovery ("Dig")** sostituisci `Seeds on a genre or a label and digs into Discogs or Bandcamp` con `Seeds on one to four genres and/or labels (the union of their piles, with the 300-item window split between them) and digs into Discogs or Bandcamp`. Dopo `each edge reports its lead count or why it was not walked.` aggiungi: `The "Similar" search is reachable from the Dig bar too (mode "Track", a free-text search over the library); the dig's per-artist cap exempts the artist edge, which is one artist by construction. Discogs can be hidden as a dig source from Settings (UI preference, default on; Organize's own Discogs client is untouched).`

- [ ] **Step 2: PROGRESS**

In cima a "Current state by area" aggiungi:

```markdown
- **Dig ridisegnato (2026-09-06).** La barra scava per più semi insieme (unione,
  fino a quattro, budget di 300 item diviso fra loro), con i semi come chip e una
  tavolozza dei generi in libreria; i simili si raggiungono anche da lì, con una
  ricerca traccia. Discogs si spegne dalle impostazioni. I simili non collassano
  più a due lead: il cap per artista del dig si applicava all'arco artista, che è
  un artista solo per costruzione — misurato, due su dieci — e i conteggi degli
  archi ora descrivono i lead resi.
```

- [ ] **Step 3: Commit**

```bash
git add docs/ROADMAP.md PROGRESS.md
git commit -m "docs: stato del Dig ridisegnato in ROADMAP e PROGRESS"
```

---

## Self-review

**Spec coverage.** Lavoro zero → Task 1. Barra a tre righe, modo locale, tavolozza, chip con tipo, testo libero = genere, dedup che lampeggia → Task 8, 10, 11. Ricerca traccia + `q` → Task 2, 9. Intestazione sotto la barra, freccia in cima invariata → Task 10, 11. Contratto `seeds[]`/`piles[]`, cap 4, budget diviso, dedup globale, `_styles_beyond_seed` a insieme, pesi misti → Task 5, 6. Tabella dei testi UI (seme morto per nome, tutti morti, seme largo, profondità inerte a `300/n`) → Task 7 (chiavi), 10 (barra), 11 (pagina). Codifica URL → Task 7. Discogs opzionale, default acceso, backend permissivo, gruppo Impostazioni → Task 3, 11, 12. Cap esente e conteggi → Task 4. `style_period` spento di default → invariato (Task 11 lo lascia a `urlStylePeriod`/`false`). Test elencati nella spec → tutti presenti; "ogni asserzione va provata rompendo il codice" resta un obbligo dell'esecutore in ogni step di verifica.

**Placeholder scan.** Nessun TBD/TODO. Il tipo lista tracce e l'helper PUT del Task 7 sono stati verificati sul repo (`TrackList` non esiste → forma inline; `apiPut` è già importato in `settings.ts`).

**Type consistency.** `DigSeed {type, value}` (frontend) ↔ `DiscoverySeedIn {type, value}` (backend) ↔ `Seed(type, value)` (motore). `DiscoveryPile {seed_type, value, total, reach, resolution}` ↔ `DiscoveryPileOut` ↔ `PileInfo {seed, total, reach, resolution}` (il router traduce `seed.type` → `seed_type`). `pickSurprise(pool, exclude: string[])` usato così nel Task 11. `DiscoverySimilarHeader({ data, track })` nei Task 10 e 11. `searchTracks(q)` restituisce `Track[]`: firma della prop `search` nel Task 9 e 10.
