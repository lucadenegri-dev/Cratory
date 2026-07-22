# Dig Bandcamp Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Aggiungere Bandcamp come seconda sorgente del dig, dietro un protocollo
`DigSource`, senza cambiare il comportamento del dig Discogs.

**Architecture:** Il motore (`discovery_dig.py`) smette di ragionare in pagine Discogs e
ragiona in **item**: chiede a una `DigSource` quanto è alta la pila (`probe`), calcola una
finestra `(offset, count)` da `depth`, e si fa restituire i record grezzi (`fetch`) che la
sorgente stessa mappa su `DiscoveryLead` (`to_lead`). Discogs traduce l'offset in numeri
di pagina, Bandcamp in una sfogliata col cursore. Dedup, esclusione del posseduto, profilo
di gusto, punteggio, reason code e selezione restano nel motore e non sanno chi c'è dietro.

**Tech Stack:** Python 3 + FastAPI + SQLAlchemy + Pydantic (backend), `httpx` per l'HTTP
esterno, pytest. Next.js 16 App Router + React + Tailwind (frontend), vitest + Playwright.

## Global Constraints

- **Spec di riferimento:** `docs/superpowers/specs/2026-07-22-dig-bandcamp-design.md`.
  In caso di divergenza fra questo piano e la spec, **fermarsi e chiedere**, non decidere.
- **Il dig Discogs non cambia comportamento**, con una sola eccezione approvata: la
  finestra può scivolare rispetto alla vecchia formula a pagine, **fino a 2 pagine, a
  qualunque altezza di pila**. Misurato per esaustione (totali 1..20.000 × 1.001
  profondità, più campionamento fino a 5 milioni) e approvato il 2026-07-22: il vecchio
  modello misurava lo scarto in pagine e su una pila non tonda prometteva una profondità
  che la pila non aveva (a `depth=1.0` su 401 release pescava 206 item veri dichiarandone
  300). Il limite è fissato dal test
  `test_window_stays_within_two_pages_of_the_retired_page_formula`, non dalla prosa.
  Filtri, ordinamento e composizione della finestra non cambiano. Nessun'altra differenza
  è accettabile.
- **I due pesi Discogs restano esatti:** seme etichetta → artista `0.5/0.7 = 0.714…`,
  stile `0.2/0.7 = 0.286…`. È un'invariante con un test dedicato.
- **Nessuna chiamata di rete nei test**, tranne quelli marcati `@pytest.mark.network`, che
  sono esclusi dalla suite. Tutte le fixture di questo piano sono già scritte qui dentro,
  catturate dall'API reale il 2026-07-22.
- **Niente URL attraversa il confine HTTP verso il backend.** Il dettaglio release accetta
  solo id numerici: è la scelta che elimina la superficie SSRF (spec §3 e §4).
- **Lingua:** commenti e docstring in italiano, come il resto di `backend/app/services`.
  I commenti spiegano il *perché*, non il *cosa*.
- **Commit:** nessun `Co-Authored-By`. Prima di ogni commit, `git status --porcelain` e
  stage dei soli file della task (il checkout può ospitare sessioni parallele).
- **Frontend:** Next.js 16 ha breaking change rispetto alle versioni note. Prima di
  toccare pagine o routing leggere `frontend/CLAUDE.md` e i doc in `node_modules/next/dist/docs/`.

### Comandi

**Questo è un worktree e NON ha un proprio `backend/.venv`.** Si usa l'interprete del
checkout principale, con la working directory nel backend del worktree:

```bash
cd <worktree>/backend
/Users/lucadenegri/Develop/DJProject01/backend/.venv/bin/python -m pytest tests -q
```

Dove il piano scrive `cd backend && python -m pytest ...`, intende quel comando.
**Baseline verificata prima di iniziare: 1028 test passati in ~13s.** Ogni task deve
finire con almeno 1028 test verdi più i propri; un numero inferiore è una regressione,
non una task finita.

Il worktree non ha nemmeno `frontend/node_modules`: la prima task che tocca il
frontend (Task 5) deve eseguire `npm install` reale nel worktree. **Un symlink al
`node_modules` del checkout principale regge `tsc`/`eslint` ma rompe la build e il dev
server di Turbopack:** non usarlo.

```bash
cd <worktree>/frontend && npm run lint && npx tsc --noEmit && npm run test:unit
```

---

## File Structure

**Nuovi:**

| File | Responsabilità |
|---|---|
| `backend/app/services/dig_sources/__init__.py` | Il confine: `Seed`, `Pile`, `DigSource`, `DiscoveryLead`, `Reason`, `WINDOW_ITEMS` |
| `backend/app/services/dig_sources/discogs.py` | `DiscogsSource`: offset → pagine, record Discogs → lead |
| `backend/app/services/dig_sources/bandcamp.py` | `BandcampSource`: offset → sfogliata col cursore, due mapping (discover, discografia) |
| `backend/app/integrations/bandcamp.py` | Client HTTP Bandcamp, `httpx` iniettabile |
| `backend/tests/test_dig_sources_discogs.py` | Traduzione della finestra in pagine, mapping Discogs |
| `backend/tests/test_bandcamp_client.py` | Client su `httpx.MockTransport` |
| `backend/tests/test_dig_sources_bandcamp.py` | Probe, sfogliata, mapping, alias, badge |
| `backend/tests/test_bandcamp_contract.py` | `@pytest.mark.network`, escluso dalla suite |

**Modificati:** `backend/app/services/discovery_dig.py` (il motore, alleggerito),
`backend/app/integrations/_http.py` (`post_json`), `backend/app/routers/discovery.py`,
`backend/app/schemas.py`, `frontend/lib/api/{discovery.ts,types.ts}`,
`frontend/lib/discovery-dig.ts`, `frontend/lib/player.tsx`,
`frontend/app/discovery/page.tsx`, `frontend/components/{discovery-dig-bar,discovery-lead-grid,discovery-tracklist-panel}.tsx`,
`frontend/lib/i18n/{it,en}.ts`.

**Perché il pacchetto e non un file solo:** `discovery_dig.py` è già a 588 righe.
Aggiungerci Bandcamp lo porterebbe oltre 800, e le due sorgenti non condividono niente
oltre al protocollo — sono esattamente il tipo di cosa che sta meglio in file separati.

---

### Task 1: Il seam `DigSource` (refactor, zero comportamento nuovo)

Il contratto HTTP **non cambia** in questa task: il router continua a esporre
`pile_pages` e `discogs_id`, calcolandoli dai nuovi campi. Il frontend non si tocca.

**Files:**
- Create: `backend/app/services/dig_sources/__init__.py`
- Create: `backend/app/services/dig_sources/discogs.py`
- Create: `backend/tests/test_dig_sources_discogs.py`
- Modify: `backend/app/services/discovery_dig.py`
- Modify: `backend/app/routers/discovery.py`
- Modify: `backend/tests/test_discovery_dig.py` (le asserzioni su `_window`, righe 566-597)

**Interfaces:**
- Produces: `Seed(type, value)`, `Pile(height, reach, resolution, handle)`,
  `DigSource` (Protocol con `name`, `probe`, `fetch`, `to_lead`),
  `DiscoveryLead` (con `source_id: str | None`, `source_url`, `stream_url`),
  `Reason`, `WINDOW_ITEMS = 300`, `DiscogsSource(client)`,
  `_window(depth, pile) -> tuple[int, int]`,
  `dig(db, *, seed_type, value, source, library=None, depth=0.0) -> DigResult`,
  `DigResult(seed_type, value, leads, pile_total, pile_reach, seed_resolution)`.

- [ ] **Step 1: Scrivere i test della finestra in item (falliscono)**

In `backend/tests/test_discovery_dig.py`, **sostituire** il blocco di asserzioni su
`_window` (righe ~566-597) con questo. Aggiungere in cima al file
`from app.services.dig_sources import Pile, WINDOW_ITEMS`.

```python
def _discogs_pile(total: int) -> Pile:
    """La pila che DiscogsSource dichiara: alta quanto il seme, raggiungibile fino a
    pagina 100 (il tetto oltre cui Discogs risponde 404)."""
    return Pile(height=total, reach=10_000)


def test_window_surface_is_the_top_of_the_pile():
    assert _window(0.0, _discogs_pile(43345)) == (0, WINDOW_ITEMS)


def test_window_deep_is_the_bottom_of_what_the_source_reaches():
    assert _window(1.0, _discogs_pile(43345)) == (9700, WINDOW_ITEMS)


def test_window_keeps_its_size_at_every_depth_of_a_tall_pile():
    for depth in (0.0, 0.25, 0.5, 0.75, 1.0):
        assert _window(depth, _discogs_pile(43345))[1] == WINDOW_ITEMS


def test_window_moves_monotonically_with_depth():
    starts = [_window(d, _discogs_pile(43345))[0] for d in (0.0, 0.15, 0.5, 0.85, 1.0)]
    assert starts == sorted(starts)
    assert starts[0] < starts[-1]


def test_window_on_a_pile_shorter_than_itself_ignores_depth():
    # Niente profondita' da scegliere: la finestra E' tutta la pila.
    assert _window(0.0, _discogs_pile(150)) == (0, 150)
    assert _window(1.0, _discogs_pile(150)) == (0, 150)


def test_window_on_an_empty_pile_is_empty():
    assert _window(0.5, _discogs_pile(0)) == (0, 0)


def test_window_is_capped_by_what_the_source_reaches_not_by_the_pile():
    # 434.149 item esistono, ma la sorgente ne raggiunge 3.000: il fondo e' li'.
    assert _window(1.0, Pile(height=434_149, reach=3_000)) == (2700, WINDOW_ITEMS)
```

- [ ] **Step 2: Eseguire i test per vederli fallire**

Run: `cd backend && python -m pytest tests/test_discovery_dig.py -q -k window`
Expected: FAIL con `ImportError: cannot import name 'Pile' from 'app.services.dig_sources'`
(il modulo non esiste ancora).

- [ ] **Step 3: Creare il confine**

Create `backend/app/services/dig_sources/__init__.py`:

```python
"""Il confine fra il motore del dig e le sorgenti che lo alimentano.

Il motore ragiona in ITEM — una finestra (offset, count) dentro la pila di un seme —
e ogni sorgente traduce quella finestra nella PROPRIA paginazione: numeri di pagina
per Discogs, sfogliata col cursore per Bandcamp. Senza questo confine il motore
dovrebbe conoscere la granularita' di ognuna, che e' esattamente cio' che rende
impossibile aggiungerne una terza.

`DiscoveryLead` e `Reason` vivono qui e non nel motore perche' sono la lingua franca
fra i due: se stessero in `discovery_dig`, ogni sorgente dovrebbe importare dal
modulo che la usa e l'import sarebbe circolare.
"""

from dataclasses import dataclass, field
from typing import Any, Protocol

# Quanti item scarica un dig. Sono le 3 pagine da 100 del vecchio motore Discogs,
# dette in un'unita' che vale per tutte le sorgenti.
WINDOW_ITEMS = 300


@dataclass(frozen=True)
class Seed:
    type: str      # "genre" | "label"
    value: str


@dataclass
class Pile:
    """Quanto e' alta la pila di un seme e quanto ne raggiunge la sorgente.

    `height` e' il conteggio dichiarato dal provider; `reach` e' il tetto oltre cui
    QUELLA sorgente non sa andare (pagina 101 su Discogs, il costo della sfogliata su
    Bandcamp). Tenerli separati e' l'unico modo per dire "ce ne sono 434.149, ne vedi
    3.000" invece di far credere che la pila sia corta.

    `handle` e' lo stato che `probe` ha gia' pagato e `fetch` non deve ricomprare: i
    filtri Discogs gia' risolti, il tag normalizzato, la discografia gia' scaricata.
    """
    height: int
    reach: int
    resolution: str | None = None
    handle: Any = None


@dataclass
class Reason:
    """Spiegazione strutturata: codice + payload dati. Il testo lo compone la UI."""
    code: str
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class DiscoveryLead:
    artist: str
    title: str
    year: int | None = None
    label: str | None = None
    styles: list[str] = field(default_factory=list)   # tutti gli style della release
    artist_keys: list[str] = field(default_factory=list)  # interno: match, non DTO
    source: str = "discogs"
    seed: str | None = None
    # Neutro per costruzione: due sorgenti non possono convivere in un campo che si
    # chiama `discogs_id`. E' una stringa perche' Bandcamp ci mette una coppia
    # "band_id:item_id" — il dettaglio release ha bisogno di entrambi.
    source_id: str | None = None
    source_url: str | None = None
    thumb_url: str | None = None
    # Stream diretto, quando la sorgente lo regala col risultato (Bandcamp). Se manca,
    # la preview si risolve come sempre (iTunes/YouTube).
    stream_url: str | None = None
    have: int = 0
    want: int = 0
    format_badge: str | None = None    # EP | LP | Album | Single | 12" | None
    isrc: str | None = None
    score: float = 0.0
    reasons: list[Reason] = field(default_factory=list)


class DigSource(Protocol):
    """Una pila da cui scavare.

    `probe` misura e risolve il seme (una sola volta: cio' che ha pagato lo lascia in
    `Pile.handle`). `fetch` restituisce i record grezzi della finestra chiesta.
    `to_lead` li mappa, ed e' l'unico posto che conosce la forma dei dati del provider.
    """
    name: str

    def probe(self, seed: Seed) -> Pile: ...

    def fetch(self, seed: Seed, pile: Pile, offset: int, count: int) -> list[Any]: ...

    def to_lead(self, raw: Any, seed: Seed) -> DiscoveryLead | None: ...
```

- [ ] **Step 4: Riscrivere `_window` nel motore**

In `backend/app/services/discovery_dig.py`: **cancellare** `_usable_pages` e la vecchia
`_window`, e togliere l'import di `DISCOGS_MAX_PAGES`/`SEARCH_PER_PAGE` da
`app.integrations.discogs`. Aggiungere l'import del confine e la nuova funzione:

```python
from app.services.dig_sources import (
    WINDOW_ITEMS,
    DigSource,
    DiscoveryLead,
    Pile,
    Reason,
    Seed,
)


def _window(depth: float, pile: Pile) -> tuple[int, int]:
    """La finestra (offset, count) da pescare nella pila.

    depth 0 = la cima (il canone del seme), depth 1 = il fondo di cio' che la sorgente
    RAGGIUNGE — che non e' il fondo della pila quando `reach < height`. Su una pila piu'
    corta della finestra `depth` non ha effetto: non c'e' profondita' da scegliere, e il
    chiamante lo segnala alla UI via `pile_reach`.
    """
    reach = max(0, min(pile.height, pile.reach))
    if reach <= 0:
        return 0, 0
    start = round(max(0.0, min(1.0, depth)) * max(0, reach - WINDOW_ITEMS))
    return start, min(WINDOW_ITEMS, reach - start)
```

- [ ] **Step 5: Eseguire i test della finestra**

Run: `cd backend && python -m pytest tests/test_discovery_dig.py -q -k window`
Expected: PASS (7 test).

- [ ] **Step 6: Scrivere il test della traduzione in pagine (fallisce)**

Create `backend/tests/test_dig_sources_discogs.py`:

```python
"""La sorgente Discogs: traduzione della finestra in pagine e mapping dei record."""

from app.services.dig_sources import Pile, Seed
from app.services.dig_sources.discogs import DiscogsSource


class _FakeDiscogs:
    """Client Discogs finto: registra le chiamate, non tocca la rete."""

    def __init__(self, items=None, total=43345):
        self.items = items if items is not None else []
        self.total = total
        self.calls: list[dict] = []

    def count_releases(self, **kw):
        self.calls.append({"op": "count", **kw})
        return self.total

    def search_releases(self, **kw):
        self.calls.append({"op": "search", **kw})
        return self.items


def _release(title, *, rid=1, style="Acid House"):
    return {
        "id": rid, "title": title, "year": 2020, "label": ["Lbl"], "style": [style],
        "community": {"have": 100, "want": 10}, "format": [],
        "uri": f"/release/{rid}", "cover_image": "http://img",
    }


def test_probe_resolves_style_first():
    fake = _FakeDiscogs()
    pile = DiscogsSource(fake).probe(Seed("genre", "Acid House"))
    assert fake.calls[0] == {"op": "count", "style": "Acid House"}
    assert pile.height == 43345 and pile.reach == 10_000
    assert pile.resolution == "style"


def test_probe_falls_back_to_the_discogs_shelf_when_the_style_is_unknown():
    # 'Electronic' non e' uno style ma un genre: la sonda ripiega e lo dichiara.
    class _Fake(_FakeDiscogs):
        def count_releases(self, **kw):
            self.calls.append({"op": "count", **kw})
            return 0 if "style" in kw else 4_960_093

    fake = _Fake()
    pile = DiscogsSource(fake).probe(Seed("genre", "Electronic"))
    assert pile.resolution == "genre" and pile.height == 4_960_093


def test_probe_of_an_unknown_seed_type_is_an_empty_pile_and_costs_nothing():
    fake = _FakeDiscogs()
    pile = DiscogsSource(fake).probe(Seed("playlist", "x"))
    assert (pile.height, pile.reach) == (0, 0)
    assert fake.calls == []


def test_fetch_asks_for_exactly_three_pages_whatever_the_offset():
    # 3 pagine da 100 = i 300 item della finestra. Una quarta sarebbe una richiesta
    # sprecata a ogni dig.
    fake = _FakeDiscogs()
    src = DiscogsSource(fake)
    pile = Pile(height=43345, reach=10_000, resolution="style", handle={"style": "Acid House"})
    for offset, expected in [(0, [1, 2, 3]), (4850, [49, 50, 51]), (9700, [98, 99, 100])]:
        fake.calls.clear()
        src.fetch(Seed("genre", "Acid House"), pile, offset, 300)
        assert fake.calls[-1]["pages"] == expected


def test_fetch_reuses_the_filters_probe_already_resolved():
    fake = _FakeDiscogs()
    pile = Pile(height=300, reach=10_000, resolution="label", handle={"label": "Warp"})
    DiscogsSource(fake).fetch(Seed("label", "Warp"), pile, 0, 300)
    assert fake.calls[-1]["label"] == "Warp"
    assert not any(c["op"] == "count" for c in fake.calls)   # nessuna ri-sonda


def test_to_lead_carries_the_neutral_identity_fields():
    lead = DiscogsSource(_FakeDiscogs()).to_lead(
        _release("Aphex Twin - Xtal", rid=7), Seed("genre", "Acid House"))
    assert lead.source == "discogs"
    assert lead.source_id == "7"
    assert lead.source_url == "https://www.discogs.com/release/7"
    assert lead.stream_url is None
```

- [ ] **Step 7: Eseguire per vederlo fallire**

Run: `cd backend && python -m pytest tests/test_dig_sources_discogs.py -q`
Expected: FAIL con `ModuleNotFoundError: No module named 'app.services.dig_sources.discogs'`.

- [ ] **Step 8: Creare `DiscogsSource` spostandoci il codice Discogs del motore**

Create `backend/app/services/dig_sources/discogs.py`. **Spostare** da
`discovery_dig.py` (cancellandoli da lì): `_lead_from_release`, `_format_badge`,
`_FORMAT_BADGES`, `_BAD_FORMATS`, `_SELF_RELEASED_RE`, `_is_self_released`, `_first`.
Restano nel motore `_norm`, `_parse_year`, `_clean_artist`, `_VARIOUS` e le loro regex:
li usano entrambe le sorgenti.

```python
"""Discogs come sorgente del dig: profondita' e segnale di rarita' (have/want).

Traduce la finestra in item del motore nella paginazione di Discogs (pagine da 100,
tetto a pagina 100) e mappa i record di `/database/search` su `DiscoveryLead`.
"""

import logging
import math
import re
from typing import Any

from app.integrations.discogs import (
    DISCOGS_MAX_PAGES,
    SEARCH_PER_PAGE,
    SORT_DESC,
    SORT_WANT,
)
from app.services.dig_sources import DiscoveryLead, Pile, Seed
# Il motore e le altre sorgenti condividono queste utility: stanno nel motore per non
# duplicarle. Nessun ciclo: `dig_sources/__init__` non importa il motore, e il motore
# non importa le sorgenti concrete (le costruisce il router).
from app.services.discovery_dig import _VARIOUS, _clean_artist, _norm, _parse_year

logger = logging.getLogger(__name__)

# Formati che un DJ NON vuole tra i lead (vuole release singole, non mix gia' fatti).
_BAD_FORMATS = {"compilation", "dj mix", "mixed", "mixtape"}
# Etichetta "non etichetta": segnale di autoproduzione.
_SELF_RELEASED_RE = re.compile(r"not on label|self[- ]released", re.IGNORECASE)

# Badge di formato per la UI. Match ESATTO (intersezione di insiemi), non per
# sostringa: 'ep' e' sottostringa di 'repress' e le ristampe sono frequentissime nel
# crate digging — una ristampa LP verrebbe marcata "EP".
_FORMAT_BADGES = [
    ({"ep"}, "EP"),
    ({"lp"}, "LP"),
    ({"album"}, "Album"),
    ({"single"}, "Single"),
    ({'12"'}, '12"'),
]


def _format_badge(formats: set[str]) -> str | None:
    for needles, badge in _FORMAT_BADGES:
        if needles & formats:
            return badge
    return None


def _first(seq: Any) -> str | None:
    return seq[0] if isinstance(seq, list) and seq else None


def _is_self_released(labels: Any) -> bool:
    return any(_SELF_RELEASED_RE.search(str(label)) for label in (labels or []))


class DiscogsSource:
    """La pila Discogs di un seme, ordinata per DOMANDA (`sort=want desc`).

    Senza `sort` Discogs risponde in un ordine arbitrario: su style=Acid House (43k
    release) le prime 300 non contengono NEMMENO UNA release con have>1000 e il 46%
    ne ha meno di 5. Misurato, non supposto.
    """

    name = "discogs"

    def __init__(self, client):
        self.client = client

    def probe(self, seed: Seed) -> Pile:
        if seed.type == "label":
            filters: dict[str, Any] = {"label": seed.value}
            resolution = "label"
        elif seed.type == "genre":
            # Discogs distingue `style` (fine: 'Deep House') da `genre` (grosso:
            # 'Electronic'): si prova il piu' specifico e si ripiega.
            filters = {"style": seed.value}
            resolution = "style"
        else:
            return Pile(height=0, reach=0)

        total = self.client.count_releases(**filters)
        if total == 0 and seed.type == "genre":
            filters = {"genre": seed.value}
            resolution = "genre"
            total = self.client.count_releases(**filters)

        return Pile(
            height=total,
            # Tetto duro di Discogs: pagina 101 -> 404.
            reach=DISCOGS_MAX_PAGES * SEARCH_PER_PAGE,
            resolution=resolution if total else None,
            handle=filters,
        )

    def fetch(self, seed: Seed, pile: Pile, offset: int, count: int) -> list[dict]:
        if count <= 0:
            return []
        # Quante pagine servono per `count` item, a partire da quella che contiene
        # l'offset. Contare invece le pagine "toccate" dall'intervallo ne chiederebbe
        # una quarta quando l'offset non e' allineato al centinaio: una richiesta
        # sprecata a ogni dig profondo.
        first = offset // SEARCH_PER_PAGE + 1
        pages = [p for p in range(first, first + math.ceil(count / SEARCH_PER_PAGE))
                 if p <= DISCOGS_MAX_PAGES]
        return self.client.search_releases(
            **(pile.handle or {}), pages=pages, sort=SORT_WANT, sort_order=SORT_DESC,
        )

    def to_lead(self, raw: dict, seed: Seed) -> DiscoveryLead | None:
        """Lead da un result di `/database/search`, con filtri anti-rumore.

        Scarta: titoli non splittabili, Various, formati off-target (compilation/DJ
        mix) e i self-released 'morti' (nessuno li ha ne' li cerca).
        """
        title = raw.get("title") or ""
        if " - " not in title:
            return None
        artist_raw, _, track_title = title.partition(" - ")
        artist_raw, track_title = artist_raw.strip(), track_title.strip()
        if not artist_raw or not track_title or artist_raw.lower() in _VARIOUS:
            return None
        artist, artist_keys = _clean_artist(artist_raw)
        if not artist or not artist_keys:
            return None
        formats = {str(f).lower() for f in (raw.get("format") or [])}
        if formats & _BAD_FORMATS:
            return None
        community = raw.get("community") or {}
        have = int(community.get("have") or 0)
        want = int(community.get("want") or 0)
        labels = raw.get("label") or []
        # self-released che nessuno ha ne' cerca: rumore, non una gemma rara.
        if have == 0 and want == 0 and _is_self_released(labels):
            return None
        uri = raw.get("uri") or ""
        rid = raw.get("id")
        return DiscoveryLead(
            artist=artist, artist_keys=artist_keys, title=track_title,
            year=_parse_year(raw.get("year")),
            label=_first(labels),
            styles=[str(s) for s in (raw.get("style") or [])],
            source="discogs", seed=seed.value,
            source_id=str(rid) if rid is not None else None,
            source_url=(f"https://www.discogs.com{uri}" if uri.startswith("/")
                        else (uri or None)),
            thumb_url=raw.get("cover_image") or raw.get("thumb") or None,
            have=have, want=want,
            format_badge=_format_badge(formats),
        )
```

Nota sulla direzione degli import: `dig_sources/__init__.py` non importa niente da
`discovery_dig`, e `discovery_dig` non importa le sorgenti concrete (le costruisce il
router). Quindi `dig_sources/discogs.py` può importare da entrambi in cima al file
senza ciclo. **Se durante l'implementazione emergesse comunque un `ImportError`
circolare, non aggirarlo con un import posticipato:** spostare `_norm`, `_parse_year`,
`_clean_artist`, `_VARIOUS` e le loro regex in `dig_sources/__init__.py`, e lasciare
che `discovery_dig` li re-esporti per non rompere i test esistenti.

- [ ] **Step 9: Eseguire i test della sorgente Discogs**

Run: `cd backend && python -m pytest tests/test_dig_sources_discogs.py -q`
Expected: PASS (6 test).

- [ ] **Step 10: Rifare `dig()` sul protocollo**

In `backend/app/services/discovery_dig.py`, sostituire `DigResult` e `dig()`:

```python
@dataclass
class DigResult:
    seed_type: str
    value: str
    leads: list[DiscoveryLead] = field(default_factory=list)
    # Quanto e' alta la pila del seme (0 = seme che la sorgente non conosce).
    pile_total: int = 0
    # Quanti item la sorgente raggiunge davvero. Se <= WINDOW_ITEMS la finestra e'
    # l'intera pila e `depth` non ha effetto: la UI deve poterlo dire invece di
    # offrire un controllo inerte. Se < pile_total, la UI avverte che si vede
    # solo una porzione.
    pile_reach: int = 0
    # Com'e' stato risolto il seme: "style"|"genre"|"label"|"tag"|"discography"|None.
    seed_resolution: str | None = None


def dig(
    db: Session,
    *,
    seed_type: str,
    value: str,
    source: DigSource,
    library: list | None = None,
    depth: float = 0.0,
) -> DigResult:
    """Lead non posseduti dal seme dato (genere|etichetta), ordinati per gusto.

    Due assi separati: `depth` sceglie DOVE pescare nella pila della sorgente (0 = la
    cima, 1 = il fondo di cio' che raggiunge); il gusto ordina SEMPRE dentro la
    finestra.

    Il profilo di gusto e la dedup del posseduto usano la STESSA `library`, per
    scelta: il riferimento per-playlist e' stato rimosso perche' su una playlist magra
    il gusto si azzerava in silenzio e la lista ricadeva sull'ordine della pila senza
    che nulla lo dicesse.
    """
    if library is None:
        library = _library_tracks(db)
    owned_tracks, owned_albums = _owned_index(library)
    profile = TasteProfile.from_tracks(library)

    seed = Seed(type=seed_type, value=value)
    pile = source.probe(seed)
    offset, count = _window(depth, pile)
    reach = max(0, min(pile.height, pile.reach))
    if count <= 0:
        return DigResult(seed_type=seed_type, value=value, pile_total=pile.height,
                         pile_reach=reach, seed_resolution=pile.resolution)

    items = source.fetch(seed, pile, offset, count)

    leads: list[DiscoveryLead] = []
    seen: set[tuple[str, str]] = set()
    for item in items or []:
        lead = source.to_lead(item, seed)
        if lead is None:
            continue
        k = _dedup_key(lead.artist_keys[0], lead.title)  # collassa varianti e pressature
        if k in seen or _is_owned(lead, owned_tracks, owned_albums):
            continue
        seen.add(k)
        leads.append(lead)

    # Quali segnali esistono lo dicono i DATI, non il nome della sorgente: se un
    # giorno Bandcamp restituisse gli stili nella lista, il peso torna da solo.
    has_styles = any(lead.styles for lead in leads)
    weights = _weights(seed_type, has_styles=has_styles)
    current_year = datetime.now(timezone.utc).year
    seed_norm = _norm(value)
    for lead in leads:
        extra_styles = _styles_beyond_seed(lead.styles, seed_norm)
        lead.score = _score(lead, profile, weights, extra_styles)
        lead.reasons = _reasons(lead, profile, seed_type, current_year, extra_styles)
    selected = _select(leads)

    logger.info("Discovery dig %s %s=%r: %s lead (depth=%.2f, offset %s, pila %s/%s)",
                source.name, seed_type, value, len(selected), depth, offset,
                reach, pile.height)
    return DigResult(seed_type=seed_type, value=value, leads=selected,
                     pile_total=pile.height, pile_reach=reach,
                     seed_resolution=pile.resolution)
```

- [ ] **Step 11: Generalizzare `_weights` da "quale seme" a "quali segnali"**

Sostituire `_weights` in `discovery_dig.py`:

```python
def _weights(seed_type: str, *, has_styles: bool = True) -> Weights:
    """I segnali costanti per costruzione escono, e il peso si redistribuisce.

    Su un dig per etichetta ogni lead ha l'etichetta del seme: `label_affinity` vale
    1.0 per tutti. E' una costante additiva — non ordina, e dilava gli altri segnali.
    Stessa malattia quando la sorgente non porta gli stili nella lista (Bandcamp): un
    peso su un segnale sempre nullo e' peso buttato.

    Il seme `genre` NON perde il peso `style` per la ragione simmetrica, anche se ogni
    release del dig contiene lo style del seme per costruzione: li' la cura non e'
    azzerare il peso (si butterebbe anche il segnale buono) ma `_styles_beyond_seed`,
    che esclude il seme dal calcolo lasciando solo l'affinita' EXTRA.
    """
    artist, label, style = W_ARTIST, W_LABEL, W_STYLE
    if seed_type == "label":
        label = 0.0
    if not has_styles:
        style = 0.0
    total = artist + label + style
    if total <= 0:
        return Weights(artist=1.0, label=0.0, style=0.0)
    return Weights(artist=artist / total, label=label / total, style=style / total)
```

- [ ] **Step 12: Scrivere il test dell'invariante sui pesi**

In `backend/tests/test_discovery_dig.py`, in fondo:

```python
from app.services.discovery_dig import _weights


def test_label_seed_weights_are_unchanged():
    # INVARIANTE: il dig Discogs per etichetta pesa esattamente come prima del seam.
    w = _weights("label")
    assert w.artist == pytest.approx(0.5 / 0.7)
    assert w.label == 0.0
    assert w.style == pytest.approx(0.2 / 0.7)


def test_genre_seed_weights_are_unchanged():
    w = _weights("genre")
    assert (w.artist, w.label, w.style) == (0.5, 0.3, 0.2)


def test_without_styles_the_style_weight_moves_onto_the_others():
    w = _weights("genre", has_styles=False)
    assert w.artist == pytest.approx(0.625)
    assert w.label == pytest.approx(0.375)
    assert w.style == 0.0


def test_label_seed_without_styles_leaves_only_the_artist():
    w = _weights("label", has_styles=False)
    assert (w.artist, w.label, w.style) == (1.0, 0.0, 0.0)
```

- [ ] **Step 13: Adeguare i test esistenti che chiamano `dig()`**

In `backend/tests/test_discovery_dig.py` tutte le chiamate a `dig(...)` passano
`search_releases=` e `count_releases=`. Sostituirle con una `DigSource` finta.
Aggiungere questo helper vicino a `_lib` e riscrivere ogni chiamata come
`dig(None, seed_type=..., value=..., source=_src(search, total=...), library=...)`:

```python
from app.services.dig_sources.discogs import DiscogsSource


def _src(search, *, total=300):
    """DiscogsSource su un client finto: stessa sorgente vera, zero rete.

    Si usa la sorgente REALE e non un finto protocollo, cosi' questi test coprono
    anche la traduzione della finestra e il mapping, non solo il motore.
    """
    class _Client:
        def count_releases(self, **kw):
            return total

        def search_releases(self, **kw):
            return search(**kw)

    return DiscogsSource(_Client())
```

`test_dig_label_seed_uses_label_filter` continua a valere: `seen` registrerà
`label="Warp"` perché `DiscogsSource.fetch` passa i filtri di `pile.handle`.

- [ ] **Step 14: Adeguare il router senza cambiare il contratto HTTP**

In `backend/app/routers/discovery.py`:

```python
from app.integrations.discogs import SEARCH_PER_PAGE
from app.services.dig_sources.discogs import DiscogsSource
```

`dig_endpoint`: costruire la sorgente e mappare i nuovi campi su quelli vecchi.

```python
    client = DiscogsClient()
    try:
        result = dig(db, seed_type=req.seed_type, value=req.value,
                     source=DiscogsSource(client), depth=req.depth)
    except DiscogsError as exc:
        ...
    finally:
        client.close()
    return DiscoveryDigResponse(
        seed_type=result.seed_type, value=result.value,
        leads=[_lead_out(lead) for lead in result.leads],
        # Il contratto HTTP non cambia in questa task: `pile_pages` si ricava dagli
        # item. La Task 5 lo sostituisce con pile_total/pile_reach.
        pile_pages=result.pile_reach // SEARCH_PER_PAGE,
        seed_resolution=result.seed_resolution, pile_total=result.pile_total,
    )
```

`_lead_out`: `discogs_url=lead.source_url` e
`discogs_id=int(lead.source_id) if lead.source_id else None`.

- [ ] **Step 15: Eseguire tutta la suite backend**

Run: `cd backend && python -m pytest tests -q`
Expected: PASS, stesso numero di test di prima più i 17 nuovi. Zero fallimenti.

- [ ] **Step 16: Commit**

```bash
git status --porcelain
git add backend/app/services/dig_sources backend/app/services/discovery_dig.py \
        backend/app/routers/discovery.py backend/tests/test_dig_sources_discogs.py \
        backend/tests/test_discovery_dig.py
git commit -m "refactor(dig): il motore ragiona in item, Discogs diventa una DigSource

Il confine dig_sources (Seed/Pile/DigSource) sposta la paginazione dentro la
sorgente: il motore chiede una finestra (offset, count) e non sa piu' cosa sia
una pagina Discogs. Contratto HTTP invariato.

Unica differenza di comportamento, approvata in spec: a parita' di depth la
finestra puo' scivolare di una pagina (depth=0.5 su 43.345 release: pagina 50
-> 49)."
```

---

### Task 2: Client Bandcamp

**Files:**
- Create: `backend/app/integrations/bandcamp.py`
- Create: `backend/tests/test_bandcamp_client.py`
- Create: `backend/tests/test_bandcamp_contract.py`
- Modify: `backend/app/integrations/_http.py`
- Create: `backend/pytest.ini` (marker `network`, vedi Step 7)

**Interfaces:**
- Consumes: `ClosableHttpClient`, `raise_for_status`, `parse_json`, `_request_with_retries`
  da `app.integrations._http`.
- Produces: `BandcampError`; `BandcampClient` con
  `discover(*, tag, cursor="*", size=DISCOVER_PAGE_SIZE) -> tuple[list[dict], str | None, int]`
  (risultati, cursore successivo, `result_count`),
  `find_band(name) -> dict | None`, `band_discography(band_id) -> list[dict]`,
  `tralbum(*, band_id, tralbum_id, tralbum_type="a") -> dict`;
  costanti `DISCOVER_PAGE_SIZE = 500`, `DISCOVER_SLICE = "top"`.
- Produces in `_http.py`: `post_json(client, url, *, json_body, error_cls, name, ...)`.

- [ ] **Step 1: Scrivere il test di `post_json` (fallisce)**

In `backend/tests/test_bandcamp_client.py`:

```python
"""Client Bandcamp su trasporto finto: nessuna rete."""

import httpx
import pytest

from app.integrations.bandcamp import BandcampClient, BandcampError


def _client(handler) -> BandcampClient:
    return BandcampClient(http=httpx.Client(transport=httpx.MockTransport(handler)))


DISCOVER_PAYLOAD = {
    "result_count": 434149,
    "batch_result_count": 1,
    "cursor": "AoMIQM2BBnDXhZHEngMrYTIxNzc4MDQ0NDQ=",
    "results": [{"item_id": 503240863, "title": "Dārin"}],
}


def test_discover_sends_the_documented_body_and_unpacks_the_response():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = __import__("json").loads(request.content)
        return httpx.Response(200, json=DISCOVER_PAYLOAD)

    results, cursor, total = _client(handler).discover(tag="techno", cursor="*", size=60)
    assert seen["url"] == "https://bandcamp.com/api/discover/1/discover_web"
    assert seen["body"] == {
        "category_id": 0, "tag_norm_names": ["techno"], "geoname_id": 0,
        "slice": "top", "include_result_types": ["a"], "size": 60, "cursor": "*",
    }
    assert results == DISCOVER_PAYLOAD["results"]
    assert cursor == DISCOVER_PAYLOAD["cursor"]
    assert total == 434149


def test_discover_of_an_unknown_tag_is_an_empty_pile_not_an_error():
    handler = lambda r: httpx.Response(200, json={"result_count": 0, "results": [], "cursor": None})
    results, cursor, total = _client(handler).discover(tag="zzzznotatag")
    assert (results, cursor, total) == ([], None, 0)


def test_http_error_becomes_a_typed_bandcamp_error():
    handler = lambda r: httpx.Response(503, text="upstream down")
    with pytest.raises(BandcampError):
        _client(handler).discover(tag="techno")


def test_rate_limit_says_so():
    handler = lambda r: httpx.Response(429, text="slow down")
    with pytest.raises(BandcampError, match="rate limit"):
        _client(handler).discover(tag="techno")


def test_find_band_returns_the_first_band_result():
    payload = {"auto": {"results": [
        {"type": "t", "id": 1, "name": "una traccia"},
        {"type": "b", "id": 2920024821, "name": "Ostgut Ton",
         "item_url_root": "https://ostgut.bandcamp.com"},
    ]}}
    band = _client(lambda r: httpx.Response(200, json=payload)).find_band("Ostgut Ton")
    assert band["id"] == 2920024821


def test_find_band_of_an_unknown_name_is_none():
    payload = {"auto": {"results": [{"type": "t", "id": 1, "name": "x"}]}}
    assert _client(lambda r: httpx.Response(200, json=payload)).find_band("zzz") is None


def test_a_payload_level_error_is_raised_even_with_http_200():
    # Bandcamp risponde 200 con {"error": true}: senza questo controllo un band_id
    # sbagliato sembrerebbe un'etichetta senza dischi.
    handler = lambda r: httpx.Response(200, json={"error": True, "error_message": "bad id"})
    with pytest.raises(BandcampError, match="bad id"):
        _client(handler).band_discography(1)


def test_band_discography_returns_the_items():
    payload = {"discography": [
        {"item_id": 1022287860, "artist_name": "Inox Traxx", "title": "Love Letter"},
    ]}
    items = _client(lambda r: httpx.Response(200, json=payload)).band_discography(2920024821)
    assert items[0]["artist_name"] == "Inox Traxx"


def test_tralbum_returns_the_detail():
    payload = {"title": "Love Letter", "bandcamp_url": "https://ostgut.bandcamp.com/album/love-letter",
               "tracks": [{"track_num": 1, "title": "Love Letter"}]}
    d = _client(lambda r: httpx.Response(200, json=payload)).tralbum(
        band_id=2920024821, tralbum_id=1022287860)
    assert d["bandcamp_url"].endswith("/album/love-letter")
```

- [ ] **Step 2: Eseguire per vederlo fallire**

Run: `cd backend && python -m pytest tests/test_bandcamp_client.py -q`
Expected: FAIL con `ModuleNotFoundError: No module named 'app.integrations.bandcamp'`.

- [ ] **Step 3: Aggiungere `post_json` a `_http.py`**

In `backend/app/integrations/_http.py`, dopo `get_json`:

```python
def post_with_retries(
    client: httpx.Client,
    url: str,
    *,
    json_body: dict,
    error_cls: type[Exception],
    retries: int = DEFAULT_RETRIES,
    backoff: float = DEFAULT_BACKOFF,
) -> httpx.Response:
    """Come `get_with_retries`, per le API che parlano solo POST (Bandcamp)."""
    return _request_with_retries(
        lambda: client.post(url, json=json_body), "POST", url,
        error_cls=error_cls, retries=retries, backoff=backoff,
    )


def post_json(
    client: httpx.Client,
    url: str,
    *,
    json_body: dict,
    error_cls: type[Exception],
    name: str,
    rate_limit_message: str | None = None,
    text_preview: int = 160,
    context: str = "",
    json_error_message: str | None = None,
    retries: int = DEFAULT_RETRIES,
    backoff: float = DEFAULT_BACKOFF,
):
    """POST + retry di trasporto + mappatura status + parsing JSON, in un colpo.

    Gemello di `get_json`: stessa composizione, stessi messaggi, verbo diverso.
    """
    response = post_with_retries(client, url, json_body=json_body, error_cls=error_cls,
                                 retries=retries, backoff=backoff)
    raise_for_status(response, error_cls, name=name, rate_limit_message=rate_limit_message,
                     text_preview=text_preview, context=context)
    return parse_json(response, error_cls, message=json_error_message or f"{name}: risposta non JSON")
```

- [ ] **Step 4: Creare il client**

Create `backend/app/integrations/bandcamp.py`:

```python
"""Bandcamp: seconda sorgente del dig, accanto a Discogs.

Cosa da' / cosa NON da':
- Pile enormi per tag (`techno` = 434.149 release), data di uscita esatta, etichetta,
  prezzo e — regalato dentro il risultato della ricerca — lo STREAM mp3 del brano in
  evidenza. Il dettaglio release da' la tracklist con uno stream per traccia.
- NON da' have/want (nessun segnale di rarita'), non da' gli stili nella lista (solo
  nel dettaglio) e non da' un formato dichiarato.

ATTENZIONE: sono endpoint INTERNI e non documentati, quelli dietro
`bandcamp.com/discover`. Possono cambiare senza preavviso. La difesa e' il confinamento
(tutto l'HTTP sta qui), il parsing difensivo a valle e il test di contratto in
`tests/test_bandcamp_contract.py`, che si lancia a mano quando qualcosa non torna.

httpx iniettabile -> test senza rete.
"""

import logging
from typing import Any

import httpx

from app.integrations._http import ClosableHttpClient, post_json

logger = logging.getLogger(__name__)

BASE = "https://bandcamp.com"
_USER_AGENT = "Mozilla/5.0 (compatible; Cratory/0.1)"

# Massimo osservato per `size`, e il tempo cresce meno che linearmente: 60 risultati
# in 0,8s, 500 in 3,2s (misurato 2026-07-22). Sfogliare in profondita' e' quindi
# molto piu' economico che a batch piccole.
DISCOVER_PAGE_SIZE = 500
# L'equivalente piu' vicino a `sort=want` di Discogs. "new" funziona ma sarebbe un
# asse diverso; "rec" non risponde.
DISCOVER_SLICE = "top"


class BandcampError(Exception):
    pass


class BandcampClient(ClosableHttpClient):
    def __init__(self, http: httpx.Client | None = None):
        self.http = http or httpx.Client(
            timeout=25, follow_redirects=True,
            headers={"User-Agent": _USER_AGENT, "Content-Type": "application/json"},
        )

    def _post(self, path: str, body: dict) -> dict[str, Any]:
        return post_json(
            self.http, f"{BASE}{path}", json_body=body,
            error_cls=BandcampError, name="Bandcamp",
            rate_limit_message="Bandcamp: rate limit (riprova piu' tardi).",
        )

    @staticmethod
    def _checked(payload: dict[str, Any], what: str) -> dict[str, Any]:
        """Bandcamp risponde 200 anche quando fallisce, con {"error": true}.

        Senza questo controllo un band_id sbagliato sembrerebbe un'etichetta senza
        dischi, cioe' un seme morto: l'utente incolperebbe il proprio seme.
        """
        if payload.get("error"):
            raise BandcampError(f"Bandcamp {what}: {payload.get('error_message') or 'errore'}")
        return payload

    def discover(
        self, *, tag: str, cursor: str = "*", size: int = DISCOVER_PAGE_SIZE,
    ) -> tuple[list[dict], str | None, int]:
        """Una batch della pila di un tag. Ritorna (risultati, cursore, altezza pila).

        Il cursore e' opaco e va sfogliato in sequenza: non esiste un salto a pagina N.
        """
        data = self._checked(self._post("/api/discover/1/discover_web", {
            "category_id": 0,
            "tag_norm_names": [tag],
            "geoname_id": 0,
            "slice": DISCOVER_SLICE,
            # Solo album: con ["t"] la risposta non contiene affatto `results`.
            "include_result_types": ["a"],
            "size": size,
            "cursor": cursor,
        }), "discover")
        return (
            list(data.get("results") or []),
            data.get("cursor") or None,
            int(data.get("result_count") or 0),
        )

    def find_band(self, name: str) -> dict[str, Any] | None:
        """L'etichetta (o l'artista) che meglio corrisponde al nome. `None` se non c'e'.

        Il filtro `b` chiede solo le band; i risultati di altro tipo si scartano
        comunque, perche' l'ordine non e' garantito.
        """
        data = self._checked(self._post("/api/bcsearch_public_api/1/autocomplete_elastic", {
            "search_text": name, "search_filter": "b", "full_page": False, "fan_id": None,
        }), "search")
        for item in ((data.get("auto") or {}).get("results") or []):
            if item.get("type") == "b" and item.get("id"):
                return item
        return None

    def band_discography(self, band_id: int) -> list[dict]:
        """Le release pubblicate da una band/etichetta.

        Forma DIVERSA dai risultati di `discover`: l'artista sta in `artist_name`, non
        ci sono ne' stream ne' conteggio tracce, e la data e' '26 Jun 2026 ...'.
        """
        data = self._checked(self._post("/api/mobile/24/band_details", {"band_id": band_id}),
                             "band_details")
        return list(data.get("discography") or [])

    def tralbum(self, *, band_id: int, tralbum_id: int, tralbum_type: str = "a") -> dict[str, Any]:
        """Dettaglio di una release: `bandcamp_url`, `tags`, `price` e le tracce con
        `streaming_url["mp3-128"]`.

        Sostituisce lo scraping dell'attributo `data-tralbum` dalla pagina album (337KB
        di HTML per release) e, lavorando su id numerici, evita che un URL debba
        attraversare il confine HTTP verso il backend.
        """
        return self._checked(self._post("/api/mobile/24/tralbum_details", {
            "band_id": band_id, "tralbum_id": tralbum_id, "tralbum_type": tralbum_type,
        }), "tralbum_details")
```

- [ ] **Step 5: Eseguire i test del client**

Run: `cd backend && python -m pytest tests/test_bandcamp_client.py -q`
Expected: PASS (9 test).

- [ ] **Step 6: Scrivere il test di contratto (escluso dalla suite)**

Create `backend/tests/test_bandcamp_contract.py`:

```python
"""Contratto con l'API REALE di Bandcamp. ESCLUSO dalla suite: tocca la rete.

Non verifica il nostro codice ma la FORMA della risposta di un provider che puo'
cambiare senza preavviso. Si lancia a mano quando il dig Bandcamp smette di funzionare,
per sapere in due secondi se e' colpa nostra o loro:

    python -m pytest tests/test_bandcamp_contract.py -m network -q
"""

import pytest

from app.integrations.bandcamp import BandcampClient

pytestmark = pytest.mark.network


@pytest.fixture()
def client():
    c = BandcampClient()
    yield c
    c.close()


def test_discover_still_returns_results_cursor_and_count(client):
    results, cursor, total = client.discover(tag="techno", size=5)
    assert total > 1000, "la pila di 'techno' non dovrebbe mai essere piccola"
    assert cursor, "senza cursore non si puo' sfogliare in profondita'"
    item = results[0]
    for key in ("item_id", "title", "band_name", "item_url", "primary_image",
                "release_date", "track_count", "featured_track"):
        assert key in item, f"campo sparito dalla risposta discover: {key}"
    assert "stream_url" in item["featured_track"]


def test_an_unknown_tag_is_still_an_empty_pile(client):
    _, _, total = client.discover(tag="zzzznotatag", size=1)
    assert total == 0


def test_label_search_and_discography_still_work(client):
    band = client.find_band("Ostgut Ton")
    assert band and band.get("id")
    items = client.band_discography(int(band["id"]))
    assert items, "l'etichetta non dovrebbe avere discografia vuota"
    for key in ("item_id", "band_id", "title", "artist_name", "art_id", "release_date"):
        assert key in items[0], f"campo sparito dalla discografia: {key}"


def test_tralbum_still_carries_url_tags_and_streams(client):
    band = client.find_band("Ostgut Ton")
    items = client.band_discography(int(band["id"]))
    detail = client.tralbum(band_id=int(band["id"]), tralbum_id=int(items[0]["item_id"]))
    assert detail.get("bandcamp_url")
    assert isinstance(detail.get("tracks"), list) and detail["tracks"]
    assert "mp3-128" in (detail["tracks"][0].get("streaming_url") or {})
```

- [ ] **Step 7: Registrare il marker ed escluderlo di default**

Il backend **non ha oggi nessun file di configurazione pytest** (verificato: né
`pyproject.toml`, né `pytest.ini`, né `setup.cfg`). Crearne uno nuovo: usare
`backend/pytest.ini`, **non** `pyproject.toml` — introdurre un `pyproject.toml` dove
non c'è cambierebbe anche come il pacchetto viene scoperto, ed è un effetto collaterale
che questa task non vuole.

```ini
[pytest]
markers =
    network: tocca la rete reale; escluso di default
addopts = -m 'not network'
```

- [ ] **Step 8: Verificare che il test di contratto sia davvero escluso**

Run: `cd backend && python -m pytest tests -q`
Expected: PASS, e nell'output **nessun** test di `test_bandcamp_contract.py`
(compaiono come `deselected`).

Run: `cd backend && python -m pytest tests/test_bandcamp_contract.py -m network -q`
Expected: PASS (4 test, con rete). Se fallisce, l'API è cambiata: **fermarsi e
segnalarlo**, non adattare il client alla cieca.

- [ ] **Step 9: Commit**

```bash
git status --porcelain
git add backend/app/integrations/bandcamp.py backend/app/integrations/_http.py \
        backend/tests/test_bandcamp_client.py backend/tests/test_bandcamp_contract.py \
        backend/pytest.ini
git commit -m "feat(bandcamp): client HTTP per discover, ricerca band, discografia e dettaglio

Endpoint interni non documentati, confinati in un solo modulo con parsing
difensivo: Bandcamp risponde 200 anche sugli errori, quindi il payload va
controllato oltre allo status. post_json affianca get_json in _http.

Test di contratto contro l'API vera, marcato network ed escluso dalla suite."
```

---

### Task 3: Sorgente Bandcamp, seme genere (tag)

**Files:**
- Create: `backend/app/services/dig_sources/bandcamp.py`
- Create: `backend/tests/test_dig_sources_bandcamp.py`

**Interfaces:**
- Consumes: `BandcampClient`, `BandcampError`, `DISCOVER_PAGE_SIZE` (Task 2);
  `Seed`, `Pile`, `DiscoveryLead` (Task 1); `_clean_artist`, `_norm`, `_VARIOUS`
  dal motore.
- Produces: `BandcampSource(client)` con `name = "bandcamp"`, `probe`, `fetch`,
  `to_lead`; costanti `BANDCAMP_REACH = 3000`, `_TAG_ALIASES`; helper `_tag_norm(value)`.

- [ ] **Step 1: Scrivere i test (falliscono)**

Create `backend/tests/test_dig_sources_bandcamp.py`:

```python
"""La sorgente Bandcamp: normalizzazione dei tag, sfogliata col cursore, mapping."""

import pytest

from app.integrations.bandcamp import BandcampError
from app.services.dig_sources import Pile, Seed
from app.services.dig_sources.bandcamp import BANDCAMP_REACH, BandcampSource, _tag_norm


# Un risultato di `discover_web`, ridotto ai campi che il mapping usa.
# Catturato dall'API reale il 2026-07-22.
DISCOVER_ITEM = {
    "item_id": 503240863,
    "item_type": "a",
    "title": "Dārin",
    "item_url": "https://mutual-rytm.bandcamp.com/album/d-rin?from=discover_page",
    "primary_image": {"image_id": 68920540, "is_art": True},
    "band_id": 2554223401,
    "album_artist": "Phil Berg",
    "band_name": "Mutual Rytm",
    "price": {"amount": 800, "currency": "EUR"},
    "featured_track": {
        "id": 1185648549, "title": "Mephisto", "duration": 298.365,
        "stream_url": "https://t4.bcbits.com/stream/xxx/mp3-128/1185648549?p=0",
    },
    "release_date": "2026-07-17 00:00:00 UTC",
    "track_count": 7,
}


class _FakeBandcamp:
    """Client Bandcamp finto: serve batch prefissate, registra le chiamate."""

    def __init__(self, batches=None, total=434149):
        self.batches = list(batches or [])
        self.total = total
        self.calls: list[dict] = []

    def discover(self, *, tag, cursor="*", size=500):
        self.calls.append({"tag": tag, "cursor": cursor, "size": size})
        if not self.batches:
            return [], None, self.total
        batch = self.batches.pop(0)
        return batch, (f"cur{len(self.calls)}" if self.batches else None), self.total


def _item(n: int) -> dict:
    return {**DISCOVER_ITEM, "item_id": n, "title": f"Release {n}"}


# --- normalizzazione dei tag -------------------------------------------------

def test_tag_norm_lowercases_and_hyphenates():
    assert _tag_norm("Deep House") == "deep-house"
    assert _tag_norm("UK Garage") == "uk-garage"
    assert _tag_norm("IDM") == "idm"
    assert _tag_norm("Italo-Disco") == "italo-disco"


def test_tag_norm_collapses_punctuation_runs():
    # 'Funk / Soul' -> 'funk-soul' (1.630 release). Sostituire solo gli spazi darebbe
    # 'funk-/-soul', che su Bandcamp non esiste: zero risultati.
    assert _tag_norm("Funk / Soul") == "funk-soul"


def test_tag_norm_uses_an_alias_where_the_naive_form_finds_the_wrong_pile():
    # 'drum-n-bass' esiste (9.745) ma il tag vero e' 'drum-and-bass' (37.264):
    # senza alias si scava nella pila sbagliata, non in una pila vuota.
    assert _tag_norm("Drum n Bass") == "drum-and-bass"


def test_tag_norm_of_an_empty_seed_is_empty():
    assert _tag_norm("   ") == ""


# --- probe -------------------------------------------------------------------

def test_probe_measures_the_pile_and_declares_the_reach():
    fake = _FakeBandcamp(total=434149)
    pile = BandcampSource(fake).probe(Seed("genre", "Techno"))
    assert pile.height == 434149
    assert pile.reach == BANDCAMP_REACH
    assert pile.resolution == "tag"
    assert pile.handle == "techno"
    assert fake.calls[0]["size"] == 1      # la sonda deve costare il minimo


def test_probe_of_a_seed_bandcamp_does_not_know_is_an_empty_pile():
    fake = _FakeBandcamp(total=0)
    pile = BandcampSource(fake).probe(Seed("genre", "zzzznotatag"))
    assert pile.height == 0 and pile.resolution is None


def test_probe_of_an_unknown_seed_type_costs_nothing():
    fake = _FakeBandcamp()
    pile = BandcampSource(fake).probe(Seed("playlist", "x"))
    assert (pile.height, pile.reach) == (0, 0)
    assert fake.calls == []


# --- sfogliata col cursore ---------------------------------------------------

def _tag_pile() -> Pile:
    return Pile(height=434149, reach=BANDCAMP_REACH, resolution="tag", handle="techno")


def test_fetch_at_the_surface_takes_the_first_items():
    fake = _FakeBandcamp(batches=[[_item(i) for i in range(500)]])
    got = BandcampSource(fake).fetch(Seed("genre", "Techno"), _tag_pile(), 0, 300)
    assert len(got) == 300
    assert got[0]["item_id"] == 0


def test_fetch_consumes_the_offset_before_collecting():
    # L'offset e' in ITEM: la sfogliata deve scartarne 600 (due batch da 500 meno il
    # resto) e cominciare a raccogliere esattamente da li'.
    fake = _FakeBandcamp(batches=[[_item(i) for i in range(500)],
                                  [_item(i) for i in range(500, 1000)]])
    got = BandcampSource(fake).fetch(Seed("genre", "Techno"), _tag_pile(), 600, 300)
    assert [g["item_id"] for g in got[:3]] == [600, 601, 602]
    assert len(got) == 300


def test_fetch_follows_the_cursor_instead_of_restarting():
    fake = _FakeBandcamp(batches=[[_item(i) for i in range(500)],
                                  [_item(i) for i in range(500, 1000)]])
    BandcampSource(fake).fetch(Seed("genre", "Techno"), _tag_pile(), 600, 300)
    assert fake.calls[0]["cursor"] == "*"
    assert fake.calls[1]["cursor"] == "cur1"


def test_fetch_stops_when_the_pile_runs_out():
    fake = _FakeBandcamp(batches=[[_item(i) for i in range(40)]])
    got = BandcampSource(fake).fetch(Seed("genre", "Techno"), _tag_pile(), 0, 300)
    assert len(got) == 40


def test_an_error_during_the_skip_is_raised_not_swallowed():
    # Degradare qui restituirebbe lead da una profondita' DIVERSA da quella chiesta:
    # la lista sembrerebbe un dig profondo ed e' la cima della pila.
    class _Failing(_FakeBandcamp):
        def discover(self, **kw):
            raise BandcampError("rate limit")

    with pytest.raises(BandcampError):
        BandcampSource(_Failing()).fetch(Seed("genre", "Techno"), _tag_pile(), 600, 300)


def test_an_error_after_the_window_started_degrades_to_what_was_collected():
    class _FailsLater(_FakeBandcamp):
        def discover(self, **kw):
            self.calls.append(kw)
            if len(self.calls) == 1:
                return [_item(i) for i in range(500)], "cur1", self.total
            raise BandcampError("rate limit")

    got = BandcampSource(_FailsLater()).fetch(Seed("genre", "Techno"), _tag_pile(), 400, 300)
    assert 0 < len(got) < 300      # i 100 raccolti prima del guasto, non un errore


# --- mapping -----------------------------------------------------------------

def test_lead_from_discover_maps_the_documented_fields():
    lead = BandcampSource(_FakeBandcamp()).to_lead(DISCOVER_ITEM, Seed("genre", "Techno"))
    assert lead.artist == "Phil Berg"
    # band_name e' l'ETICHETTA quando differisce dall'artista: su Bandcamp
    # l'etichetta e' la band che ospita.
    assert lead.label == "Mutual Rytm"
    assert lead.title == "Dārin"
    assert lead.year == 2026
    assert lead.source == "bandcamp"
    assert lead.source_id == "2554223401:503240863"   # band_id:item_id, serve al dettaglio
    assert lead.source_url == "https://mutual-rytm.bandcamp.com/album/d-rin"
    assert lead.thumb_url == "https://f4.bcbits.com/img/a68920540_9.jpg"
    assert lead.stream_url.startswith("https://t4.bcbits.com/stream/")
    assert lead.styles == []          # i tag stanno solo nel dettaglio release
    assert (lead.have, lead.want) == (0, 0)


def test_a_self_released_album_has_no_label():
    raw = {**DISCOVER_ITEM, "album_artist": "Phil Berg", "band_name": "Phil Berg"}
    lead = BandcampSource(_FakeBandcamp()).to_lead(raw, Seed("genre", "Techno"))
    assert lead.label is None


def test_the_artist_falls_back_to_the_band_when_there_is_no_album_artist():
    raw = {**DISCOVER_ITEM, "album_artist": ""}
    lead = BandcampSource(_FakeBandcamp()).to_lead(raw, Seed("genre", "Techno"))
    assert lead.artist == "Mutual Rytm"


@pytest.mark.parametrize("count,badge", [(1, "Single"), (2, "EP"), (5, "EP"), (6, "Album"), (12, "Album")])
def test_the_format_badge_is_derived_from_the_track_count(count, badge):
    # DERIVATO, non dichiarato: Bandcamp non ha un campo formato. Serve perche' i
    # chip di filtro della griglia esistono gia' e senza badge nasconderebbero tutto.
    raw = {**DISCOVER_ITEM, "track_count": count}
    assert BandcampSource(_FakeBandcamp()).to_lead(raw, Seed("genre", "T")).format_badge == badge


@pytest.mark.parametrize("broken", [
    {"title": ""},
    {"album_artist": "", "band_name": ""},
    {"album_artist": "Various Artists", "band_name": "Various Artists"},
    {"track_count": 0},
    {"featured_track": {}},
])
def test_structurally_broken_items_are_dropped_not_crashed(broken):
    # Il de-noise vero (have/want, formati off-target) su Bandcamp non esiste: restano
    # solo gli scarti strutturali. Un campo mancante scarta il lead, non solleva.
    assert BandcampSource(_FakeBandcamp()).to_lead({**DISCOVER_ITEM, **broken},
                                                   Seed("genre", "T")) is None
```

- [ ] **Step 2: Eseguire per vederli fallire**

Run: `cd backend && python -m pytest tests/test_dig_sources_bandcamp.py -q`
Expected: FAIL con `ModuleNotFoundError: No module named 'app.services.dig_sources.bandcamp'`.

- [ ] **Step 3: Creare la sorgente**

Create `backend/app/services/dig_sources/bandcamp.py`:

```python
"""Bandcamp come sorgente del dig: un'altra pila da cui pescare.

Differenze strutturali da Discogs, tutte volute e tutte visibili qui:
- la pila si sfoglia SOLO in sequenza (cursore opaco), quindi la profondita' costa
  richieste invece di essere un salto: `BANDCAMP_REACH` e' il tetto che tiene il dig
  peggiore sotto i ~20s;
- non esiste have/want, quindi niente segnale di rarita' e niente de-noise per
  domanda: restano solo gli scarti strutturali;
- gli stili non ci sono nella lista (solo nel dettaglio release), quindi il peso
  `style` esce e si redistribuisce — se ne occupa `_weights` nel motore, guardando i
  dati e non il nome della sorgente.
"""

import logging
import re
from typing import Any

from app.integrations.bandcamp import DISCOVER_PAGE_SIZE, BandcampError
from app.services.dig_sources import DiscoveryLead, Pile, Seed
from app.services.discovery_dig import _VARIOUS, _clean_artist, _norm

logger = logging.getLogger(__name__)

# Quanti item della pila la sorgente raggiunge davvero. Non e' un limite di Bandcamp
# ma una scelta di costo: l'offset si consuma sfogliando, e ogni batch da 500 costa
# ~3,2s. A 3.000 il dig piu' profondo sta in 6 richieste (~20s), quello in superficie
# in 2. Tarabile: alzarlo allunga solo i dig profondi.
BANDCAMP_REACH = 3000

# I semi curati sono vocabolario DISCOGS. Misurati tutti e 25 contro l'API il
# 2026-07-22: 24 funzionano con la sola normalizzazione. L'unico alias serve dove la
# forma naive trova una pila VERA ma sbagliata — 'drum-n-bass' esiste (9.745) e
# quindi nessun controllo su "zero risultati" lo intercetterebbe mai.
# Come `_CURATED_STYLES`, questa tabella marcira': la difesa e' che un seme senza
# pila si dichiara tale (`result_count: 0`), non che la tabella resti giusta.
_TAG_ALIASES = {
    "drum n bass": "drum-and-bass",
}

# Soglie del badge derivato dal numero di tracce. Bandcamp non dichiara un formato:
# e' l'unico punto in cui questa sorgente inferisce invece di leggere.
_EP_MAX_TRACKS = 5


def _tag_norm(value: str) -> str:
    """Il tag Bandcamp corrispondente a un seme.

    Minuscolo e trattini: ogni corsa di caratteri non alfanumerici diventa un solo
    trattino, cosi' 'Funk / Soul' -> 'funk-soul' e non 'funk-/-soul' (che non esiste).
    """
    key = " ".join((value or "").strip().lower().split())
    if key in _TAG_ALIASES:
        return _TAG_ALIASES[key]
    return re.sub(r"[^a-z0-9]+", "-", key).strip("-")


def _bc_year(value: Any) -> int | None:
    """L'anno da una data Bandcamp.

    Serve un parser dedicato: le due forme che l'API restituisce sono
    '2026-07-17 00:00:00 UTC' e '26 Jun 2026 00:00:00 GMT', e `_parse_year` del motore
    ancora la regex all'inizio della stringa — sulla seconda tornerebbe None.
    """
    m = re.search(r"\b(\d{4})\b", str(value or ""))
    return int(m.group(1)) if m else None


def _art_url(art_id: Any, size: str = "9") -> str | None:
    """La copertina da un id immagine. `_9` e' ~15KB (griglia), `_16` ~50KB (pannello)."""
    return f"https://f4.bcbits.com/img/a{art_id}_{size}.jpg" if art_id else None


def _badge(track_count: int) -> str | None:
    if track_count <= 0:
        return None
    if track_count == 1:
        return "Single"
    return "EP" if track_count <= _EP_MAX_TRACKS else "Album"


class BandcampSource:
    name = "bandcamp"

    def __init__(self, client):
        self.client = client

    # --- probe ---------------------------------------------------------------

    def probe(self, seed: Seed) -> Pile:
        if seed.type != "genre":
            return Pile(height=0, reach=0)
        tag = _tag_norm(seed.value)
        if not tag:
            return Pile(height=0, reach=0)
        # size=1: la sonda serve solo a sapere quanto e' alta la pila.
        _, _, total = self.client.discover(tag=tag, cursor="*", size=1)
        return Pile(height=total, reach=BANDCAMP_REACH,
                    resolution="tag" if total else None, handle=tag)

    # --- fetch ---------------------------------------------------------------

    def fetch(self, seed: Seed, pile: Pile, offset: int, count: int) -> list[dict]:
        if count <= 0 or not pile.handle:
            return []
        tag = pile.handle
        cursor: str | None = "*"
        seen = 0
        out: list[dict] = []
        while len(out) < count:
            try:
                batch, cursor, _ = self.client.discover(
                    tag=tag, cursor=cursor, size=DISCOVER_PAGE_SIZE)
            except BandcampError:
                # Durante lo skip non c'e' ancora NIENTE di valido in mano: degradare
                # restituirebbe lead da una profondita' diversa da quella chiesta,
                # cioe' mentirebbe sul contratto. Dopo, i risultati raccolti sono
                # comunque quelli giusti e si tengono.
                if not out:
                    raise
                logger.warning(
                    "Bandcamp: sfogliata di %r interrotta, torno i %d item gia' raccolti",
                    tag, len(out),
                )
                break
            if not batch:
                break
            for item in batch:
                if seen >= offset:
                    out.append(item)
                seen += 1
                if len(out) >= count:
                    break
            if not cursor:
                break
        return out

    # --- mapping -------------------------------------------------------------

    def to_lead(self, raw: dict, seed: Seed) -> DiscoveryLead | None:
        return self._lead_from_discover(raw, seed)

    def _lead_from_discover(self, raw: dict, seed: Seed) -> DiscoveryLead | None:
        title = (raw.get("title") or "").strip()
        band = (raw.get("band_name") or "").strip()
        album_artist = (raw.get("album_artist") or "").strip()
        artist_raw = album_artist or band
        if not title or not artist_raw or artist_raw.lower() in _VARIOUS:
            return None
        track_count = int(raw.get("track_count") or 0)
        if track_count <= 0:
            return None
        stream = ((raw.get("featured_track") or {}).get("stream_url") or "").strip()
        if not stream:
            # Senza brano in evidenza la card non ha niente da far sentire, ed e' il
            # segnale piu' affidabile che la release sia vuota o non pubblicata.
            return None
        artist, artist_keys = _clean_artist(artist_raw)
        if not artist or not artist_keys:
            return None
        # L'etichetta e' la band che OSPITA, quando non coincide con l'artista.
        label = band if album_artist and _norm(band) != _norm(album_artist) else None
        band_id, item_id = raw.get("band_id"), raw.get("item_id")
        return DiscoveryLead(
            artist=artist, artist_keys=artist_keys, title=title,
            year=_bc_year(raw.get("release_date")),
            label=label,
            styles=[],
            source="bandcamp", seed=seed.value,
            source_id=(f"{band_id}:{item_id}" if band_id and item_id else None),
            source_url=(raw.get("item_url") or "").split("?")[0] or None,
            thumb_url=_art_url((raw.get("primary_image") or {}).get("image_id")),
            stream_url=stream,
            format_badge=_badge(track_count),
        )
```

- [ ] **Step 4: Eseguire i test della sorgente**

Run: `cd backend && python -m pytest tests/test_dig_sources_bandcamp.py -q`
Expected: PASS (25 test, contando i parametrizzati).

- [ ] **Step 5: Eseguire tutta la suite**

Run: `cd backend && python -m pytest tests -q`
Expected: PASS, nessuna regressione.

- [ ] **Step 6: Commit**

```bash
git status --porcelain
git add backend/app/services/dig_sources/bandcamp.py backend/tests/test_dig_sources_bandcamp.py
git commit -m "feat(dig): sorgente Bandcamp per il seme genere

La finestra in item diventa una sfogliata col cursore: l'offset si consuma a
batch da 500 (reach 3.000, il dig piu' profondo in 6 richieste). Un errore
durante lo skip solleva, dopo degrada: restituire lead da una profondita'
diversa da quella chiesta sarebbe una bugia silenziosa.

Il badge di formato e' derivato dal numero di tracce: unico punto in cui la
sorgente inferisce invece di leggere, perche' Bandcamp non dichiara un formato."
```

---

### Task 4: Sorgente Bandcamp, seme etichetta

La discografia ha una **forma diversa** dai risultati di `discover` e richiede un
mapping separato: l'artista sta in `artist_name`, mancano stream, conteggio tracce e
URL, e la data è in un altro formato.

**Files:**
- Modify: `backend/app/services/dig_sources/bandcamp.py`
- Modify: `backend/tests/test_dig_sources_bandcamp.py`

**Interfaces:**
- Produces: `BandcampSource.probe` gestisce `Seed(type="label")` (handle = la
  discografia già scaricata); `BandcampSource.fetch` la affetta senza richieste.

- [ ] **Step 1: Scrivere i test (falliscono)**

Aggiungere in fondo a `backend/tests/test_dig_sources_bandcamp.py`:

```python
# --- seme etichetta ----------------------------------------------------------

# Un item di `band_details`, catturato dall'API reale il 2026-07-22. Forma DIVERSA
# dai risultati di discover: artist_name, nessuno stream, nessun track_count,
# nessun URL, e una data in un altro formato.
DISCOGRAPHY_ITEM = {
    "item_id": 1022287860,
    "item_type": "album",
    "artist_name": "Inox Traxx",
    "band_name": "Ostgut Ton",
    "title": "Love Letter",
    "art_id": 2027095290,
    "release_date": "26 Jun 2026 00:00:00 GMT",
    "is_purchasable": True,
    "band_id": 2920024821,
}


class _FakeLabelBandcamp(_FakeBandcamp):
    def __init__(self, band=None, discography=None):
        super().__init__()
        self.band = band if band is not None else {"id": 2920024821, "name": "Ostgut Ton"}
        self.discography = discography if discography is not None else [DISCOGRAPHY_ITEM]

    def find_band(self, name):
        self.calls.append({"op": "find_band", "name": name})
        return self.band

    def band_discography(self, band_id):
        self.calls.append({"op": "discography", "band_id": band_id})
        return self.discography


def test_label_probe_resolves_the_band_and_keeps_the_discography():
    fake = _FakeLabelBandcamp(discography=[DISCOGRAPHY_ITEM] * 153)
    pile = BandcampSource(fake).probe(Seed("label", "Ostgut Ton"))
    assert pile.height == 153
    # La pila E' la discografia: non c'e' un fondo oltre cui andare.
    assert pile.reach == 153
    assert pile.resolution == "discography"
    assert len(pile.handle) == 153
    assert [c["op"] for c in fake.calls] == ["find_band", "discography"]


def test_a_label_bandcamp_does_not_host_is_a_dead_seed():
    fake = _FakeLabelBandcamp(band=None)
    pile = BandcampSource(fake).probe(Seed("label", "Etichetta Inesistente"))
    assert (pile.height, pile.reach) == (0, 0)
    assert pile.resolution is None


def test_label_fetch_slices_the_discography_without_any_request():
    fake = _FakeLabelBandcamp()
    items = [{**DISCOGRAPHY_ITEM, "item_id": i} for i in range(100)]
    pile = Pile(height=100, reach=100, resolution="discography", handle=items)
    got = BandcampSource(fake).fetch(Seed("label", "Ostgut Ton"), pile, 0, 300)
    assert len(got) == 100
    assert fake.calls == []      # probe aveva gia' pagato


def test_lead_from_discography_reads_artist_name_not_artist():
    lead = BandcampSource(_FakeLabelBandcamp()).to_lead(
        DISCOGRAPHY_ITEM, Seed("label", "Ostgut Ton"))
    assert lead.artist == "Inox Traxx"
    assert lead.label == "Ostgut Ton"
    assert lead.title == "Love Letter"
    assert lead.source_id == "2920024821:1022287860"
    assert lead.thumb_url == "https://f4.bcbits.com/img/a2027095290_9.jpg"


def test_lead_from_discography_parses_the_other_date_format():
    # '26 Jun 2026 ...' non e' ancorabile all'inizio: l'anno va cercato nella stringa.
    lead = BandcampSource(_FakeLabelBandcamp()).to_lead(
        DISCOGRAPHY_ITEM, Seed("label", "Ostgut Ton"))
    assert lead.year == 2026


def test_lead_from_discography_has_no_stream_badge_or_url():
    # Nessuna delle tre e' visibile in griglia: la card non rende link esterni, e il
    # play ricade sulla risoluzione iTunes che non ha bisogno di un id di sorgente.
    # Il pannello, che apre tralbum_details, ha comunque URL, tag e stream veri.
    lead = BandcampSource(_FakeLabelBandcamp()).to_lead(
        DISCOGRAPHY_ITEM, Seed("label", "Ostgut Ton"))
    assert lead.stream_url is None
    assert lead.format_badge is None
    assert lead.source_url is None


@pytest.mark.parametrize("broken", [{"title": ""}, {"artist_name": ""},
                                    {"artist_name": "Various Artists"}])
def test_broken_discography_items_are_dropped(broken):
    assert BandcampSource(_FakeLabelBandcamp()).to_lead(
        {**DISCOGRAPHY_ITEM, **broken}, Seed("label", "Ostgut Ton")) is None
```

- [ ] **Step 2: Eseguire per vederli fallire**

Run: `cd backend && python -m pytest tests/test_dig_sources_bandcamp.py -q -k "label or discography"`
Expected: FAIL — `probe` di un seme `label` restituisce oggi `Pile(0, 0)`.

- [ ] **Step 3: Estendere `probe` e `fetch`**

In `backend/app/services/dig_sources/bandcamp.py`, sostituire `probe` e l'inizio di
`fetch`:

```python
    def probe(self, seed: Seed) -> Pile:
        if seed.type == "label":
            return self._probe_label(seed)
        if seed.type != "genre":
            return Pile(height=0, reach=0)
        tag = _tag_norm(seed.value)
        if not tag:
            return Pile(height=0, reach=0)
        # size=1: la sonda serve solo a sapere quanto e' alta la pila.
        _, _, total = self.client.discover(tag=tag, cursor="*", size=1)
        return Pile(height=total, reach=BANDCAMP_REACH,
                    resolution="tag" if total else None, handle=tag)

    def _probe_label(self, seed: Seed) -> Pile:
        """L'etichetta non e' un filtro del discover: si passa dalla sua discografia.

        Due richieste (cerca il nome, scarica la discografia) e la lista finisce in
        `handle`: `fetch` diventa una fetta, zero richieste. La pila e' quindi corta
        per costruzione, e `reach == height` perche' non esiste un fondo oltre a
        quello che l'etichetta ha pubblicato.
        """
        band = self.client.find_band(seed.value)
        if not band or not band.get("id"):
            return Pile(height=0, reach=0)
        discography = self.client.band_discography(int(band["id"]))
        return Pile(height=len(discography), reach=len(discography),
                    resolution="discography" if discography else None,
                    handle=discography)

    def fetch(self, seed: Seed, pile: Pile, offset: int, count: int) -> list[dict]:
        if count <= 0 or not pile.handle:
            return []
        if seed.type == "label":
            return list(pile.handle)[offset:offset + count]
        ...   # il resto della sfogliata col cursore resta invariato
```

- [ ] **Step 4: Aggiungere il mapping della discografia**

Sostituire `to_lead` e aggiungere `_lead_from_discography`:

```python
    def to_lead(self, raw: dict, seed: Seed) -> DiscoveryLead | None:
        # Due endpoint, due forme: il discover porta stream e conteggio tracce, la
        # discografia porta `artist_name` e nient'altro di riproducibile.
        if seed.type == "label":
            return self._lead_from_discography(raw, seed)
        return self._lead_from_discover(raw, seed)

    def _lead_from_discography(self, raw: dict, seed: Seed) -> DiscoveryLead | None:
        title = (raw.get("title") or "").strip()
        artist_raw = (raw.get("artist_name") or "").strip()
        if not title or not artist_raw or artist_raw.lower() in _VARIOUS:
            return None
        artist, artist_keys = _clean_artist(artist_raw)
        if not artist or not artist_keys:
            return None
        band_id, item_id = raw.get("band_id"), raw.get("item_id")
        return DiscoveryLead(
            artist=artist, artist_keys=artist_keys, title=title,
            year=_bc_year(raw.get("release_date")),
            label=(raw.get("band_name") or "").strip() or None,
            styles=[],
            source="bandcamp", seed=seed.value,
            source_id=(f"{band_id}:{item_id}" if band_id and item_id else None),
            # La discografia non porta l'URL della pagina: lo risolve il pannello,
            # che apre `tralbum_details` e riceve `bandcamp_url`.
            source_url=None,
            thumb_url=_art_url(raw.get("art_id")),
            stream_url=None,
            format_badge=None,
        )
```

- [ ] **Step 5: Eseguire i test**

Run: `cd backend && python -m pytest tests/test_dig_sources_bandcamp.py -q`
Expected: PASS (33 test).

- [ ] **Step 6: Commit**

```bash
git status --porcelain
git add backend/app/services/dig_sources/bandcamp.py backend/tests/test_dig_sources_bandcamp.py
git commit -m "feat(dig): seme etichetta su Bandcamp via discografia

Non esiste un filtro label nel discover: si cerca la band e si scarica la sua
discografia, che finisce in Pile.handle — fetch diventa una fetta, zero
richieste. La pila e' corta per costruzione e la profondita' si spegne da
sola, col meccanismo che gia' esiste.

La discografia ha una forma diversa dal discover (artist_name, altra data,
niente stream): mapping separato, non un ramo dentro quello del discover."
```

---

### Task 5: Il contratto HTTP diventa neutro rispetto alla sorgente

Backend e frontend insieme: è **un solo cambio di contratto**, e separarli lascerebbe
la UI rotta fra due commit. Nessun comportamento nuovo — il dig resta Discogs.

**Files:**
- Modify: `backend/app/schemas.py`
- Modify: `backend/app/routers/discovery.py`
- Modify: `frontend/lib/api/types.ts`, `frontend/lib/api/discovery.ts`
- Modify: `frontend/lib/discovery-dig.ts`
- Modify: `frontend/app/discovery/page.tsx`
- Modify: `frontend/components/discovery-dig-bar.tsx`, `frontend/components/discovery-lead-grid.tsx`
- Modify: `frontend/tests/discovery-dig-bar.test.tsx`
- Modify: `backend/tests/test_discovery_router_http.py`, `backend/tests/test_discovery.py`

**Interfaces:**
- Produces (HTTP): `DiscoveryDigRequest` con `source: Literal["discogs","bandcamp"] = "discogs"`;
  `DiscoveryDigResponse` con `source: str`, `pile_total: int`, `pile_reach: int`
  (via `pile_pages`); `DiscoveryLeadOut` con `source_id: str | None`,
  `source_url: str | None`, `stream_url: str | None` (via `discogs_id`/`discogs_url`).
- Produces (frontend): `WINDOW_ITEMS = 300` esportato da `lib/discovery-dig.ts`;
  `discoveryDig(seedType, value, {depth, source})`.

- [ ] **Step 1: Scrivere il test HTTP del nuovo contratto (fallisce)**

In `backend/tests/test_discovery_router_http.py`, aggiungere:

```python
def test_dig_response_speaks_items_not_pages(client, monkeypatch):
    from app.routers import discovery as router_mod
    from app.services.dig_sources import DiscoveryLead
    from app.services.discovery_dig import DigResult

    def _fake_dig(db, **kw):
        return DigResult(
            seed_type="genre", value="Acid House",
            leads=[DiscoveryLead(artist="A", title="B", source="discogs",
                                 source_id="7", source_url="https://discogs/7")],
            pile_total=43345, pile_reach=10_000, seed_resolution="style",
        )

    monkeypatch.setattr(router_mod, "dig", _fake_dig)
    c, _ = client
    r = c.post("/api/discovery/dig", json={"seed_type": "genre", "value": "Acid House"})
    assert r.status_code == 200
    body = r.json()
    assert body["pile_total"] == 43345
    assert body["pile_reach"] == 10_000
    assert "pile_pages" not in body
    assert body["source"] == "discogs"
    lead = body["leads"][0]
    assert lead["source_id"] == "7" and lead["source_url"] == "https://discogs/7"
    assert lead["stream_url"] is None
    assert "discogs_id" not in lead


def test_dig_rejects_an_unknown_source(client):
    c, _ = client
    r = c.post("/api/discovery/dig",
               json={"seed_type": "genre", "value": "x", "source": "soundcloud"})
    assert r.status_code == 422
```

- [ ] **Step 2: Eseguire per vederlo fallire**

Run: `cd backend && python -m pytest tests/test_discovery_router_http.py -q -k "items_not_pages or unknown_source"`
Expected: FAIL — `pile_pages` è ancora nel body e `source` non esiste.

- [ ] **Step 3: Aggiornare gli schemi**

In `backend/app/schemas.py`, sostituire le tre classi:

```python
class DiscoveryLeadOut(BaseModel):
    """Lead leggero NON risolto: l'identita' Spotify si ricava al salvataggio."""

    artist: str
    title: str
    year: int | None = None
    label: str | None = None
    style: str | None = None
    source: str = "discogs"
    seed: str | None = None
    # Neutro: due sorgenti non stanno in un campo che si chiama `discogs_id`. Stringa
    # perche' Bandcamp ci mette una coppia "band_id:item_id".
    source_id: str | None = None
    source_url: str | None = None
    # Stream diretto quando la sorgente lo regala (Bandcamp): il player salta la
    # risoluzione iTunes/YouTube e suona.
    stream_url: str | None = None
    thumb_url: str | None = None
    have: int = 0
    want: int = 0
    reasons: list[ReasonOut] = []
    format_badge: str | None = None


class DiscoveryDigRequest(BaseModel):
    seed_type: Literal["genre", "label"]
    value: str = Field(min_length=1)
    # DOVE pescare nella pila della sorgente: 0 = la cima, 1 = il fondo di cio' che
    # la sorgente raggiunge. Non e' un mix di ordinamento: sceglie il bacino.
    depth: float = Field(default=0.0, ge=0.0, le=1.0)
    source: Literal["discogs", "bandcamp"] = "discogs"


class DiscoveryDigResponse(BaseModel):
    seed_type: str
    value: str
    source: str = "discogs"
    leads: list[DiscoveryLeadOut] = []
    # Quanto e' alta la pila (0 = seme che la sorgente non conosce).
    pile_total: int = 0
    # Quanti item la sorgente raggiunge. <= 300 => la finestra e' l'intera pila e
    # `depth` non ha effetto. < pile_total => la UI avverte che si vede una porzione.
    pile_reach: int = 0
    # "style"|"genre"|"label"|"tag"|"discography"|null
    seed_resolution: str | None = None
```

- [ ] **Step 4: Aggiornare il router**

In `backend/app/routers/discovery.py`, `_lead_out` e `dig_endpoint`:

```python
def _lead_out(lead: DiscoveryLead) -> DiscoveryLeadOut:
    return DiscoveryLeadOut(
        artist=lead.artist, title=lead.title, year=lead.year, label=lead.label,
        style=lead.styles[0] if lead.styles else None, source=lead.source, seed=lead.seed,
        source_id=lead.source_id, source_url=lead.source_url, stream_url=lead.stream_url,
        thumb_url=lead.thumb_url, have=lead.have, want=lead.want,
        reasons=[ReasonOut(code=r.code, data=r.data) for r in lead.reasons],
        format_badge=lead.format_badge,
    )
```

In `dig_endpoint`, il `return`:

```python
    return DiscoveryDigResponse(
        seed_type=result.seed_type, value=result.value, source=req.source,
        leads=[_lead_out(lead) for lead in result.leads],
        pile_total=result.pile_total, pile_reach=result.pile_reach,
        seed_resolution=result.seed_resolution,
    )
```

(La costruzione della sorgente resta `DiscogsSource(client)`: il ramo Bandcamp arriva
nella Task 7.)

- [ ] **Step 5: Eseguire i test backend**

Run: `cd backend && python -m pytest tests -q`
Expected: PASS. Se `test_discovery.py` asserisce su `pile_pages` o `discogs_id`,
aggiornare quelle asserzioni ai nuovi nomi — **senza** cambiare cosa verificano.

- [ ] **Step 6: Aggiornare i tipi del frontend**

In `frontend/lib/api/types.ts`:

```ts
export interface DiscoveryLead {
  artist: string;
  title: string;
  year: number | null;
  label: string | null;
  style: string | null;
  source: string;
  seed: string | null;
  /** Id neutro. Discogs: "123". Bandcamp: "band_id:item_id" (il dettaglio vuole entrambi). */
  source_id: string | null;
  source_url: string | null;
  /** Stream diretto quando la sorgente lo regala: il player salta la risoluzione. */
  stream_url: string | null;
  thumb_url: string | null;
  have: number;
  want: number;
  reasons: Reason[];
  format_badge: string | null;
}

export interface DiscoveryDigResponse {
  seed_type: string;
  value: string;
  source: string;
  leads: DiscoveryLead[];
  /** Quanto è alta la pila. 0 => seme che la sorgente non conosce. */
  pile_total: number;
  /** Quanti item la sorgente raggiunge. <= WINDOW_ITEMS => `depth` non ha effetto. */
  pile_reach: number;
  seed_resolution: "style" | "genre" | "label" | "tag" | "discography" | null;
}
```

In `frontend/lib/api/discovery.ts`: **cancellare** `DISCOGS_PAGE_SIZE` e passare `source`:

```ts
export function discoveryDig(
  seedType: "genre" | "label",
  value: string,
  opts?: { depth?: number; source?: DigSourceKey },
) {
  return apiPost<DiscoveryDigResponse>("/api/discovery/dig", {
    seed_type: seedType,
    value,
    depth: opts?.depth,
    source: opts?.source,
  });
}
```

In `frontend/lib/discovery-dig.ts`, aggiungere:

```ts
export type DigSourceKey = "discogs" | "bandcamp";

/** Quanti item scarica un dig: rispecchia WINDOW_ITEMS del backend. Sotto questa
 *  soglia la finestra è l'intera pila e la profondità non ha niente da scegliere. */
export const WINDOW_ITEMS = 300;
```

Esportare `DigSourceKey` da `frontend/lib/api/index.ts` (o dove il barrel ri-esporta i
tipi) se `discovery.ts` non può importarlo direttamente da `lib/discovery-dig`.

- [ ] **Step 7: Aggiornare i consumatori nel frontend**

`frontend/components/discovery-dig-bar.tsx`: la prop `pilePages: number | null`
diventa `pile: { total: number; reach: number } | null`, e le due condizioni:

```tsx
  // Due casi diversi, non uno. La pila NON ESISTE (seme che la sorgente non conosce)
  // e' altra cosa da una pila CORTA (seme vero ma con pochi dischi): confonderli fa
  // dire alla UI "tutta qui" su un seme che non ha mai avuto niente.
  const emptyPile = pile?.total === 0;
  const shortPile = pile != null && pile.reach > 0 && pile.reach <= WINDOW_ITEMS;
  const depthInert = emptyPile || shortPile;
```

`frontend/components/discovery-lead-grid.tsx`:

```tsx
  if (dig.pile_total === 0) { /* seme morto, invariato */ }
  ...
  const shortPile = dig.pile_reach <= WINDOW_ITEMS;
```

`frontend/app/discovery/page.tsx`: sostituire il calcolo di `pilePages` con

```tsx
  const pile =
    dig && dig.seed_type === seedType && dig.value === subject.trim()
      ? { total: dig.pile_total, reach: dig.pile_reach }
      : null;
```

e passare `pile={pile}` alla barra. Il messaggio del seme largo diventa:

```tsx
          {dig.pile_total > dig.pile_reach && (
            <span className="tnum text-muted">
              {t.discovery.broadSeed(
                dig.pile_total.toLocaleString(lang),
                dig.pile_reach.toLocaleString(lang),
              )}
            </span>
          )}
```

Togliere l'import di `DISCOGS_PAGE_SIZE` e aggiungere quello di `WINDOW_ITEMS`.

- [ ] **Step 8: Aggiornare il test della barra**

In `frontend/tests/discovery-dig-bar.test.tsx`, sostituire ogni `pilePages={N}` con
`pile={{ total: N * 100, reach: N * 100 }}` e `pilePages={0}` con
`pile={{ total: 0, reach: 0 }}`. Le asserzioni su cosa la barra mostra non cambiano.

- [ ] **Step 9: Verificare il frontend**

Run: `cd frontend && npm run lint && npx tsc --noEmit && npm run test:unit`
Expected: tutto verde, zero errori di tipo.

- [ ] **Step 10: Verificare il dig nel browser**

Avviare backend e frontend, aprire `/discovery`, scavare `Acid House` a profondità
"Superficie" e "In fondo".
Expected: stesse card di prima, il controllo di profondità attivo, e su un seme
inesistente (es. `zzzz`) l'empty state "seme sconosciuto".

- [ ] **Step 11: Commit**

```bash
git status --porcelain
git add backend/app/schemas.py backend/app/routers/discovery.py backend/tests \
        frontend/lib frontend/app/discovery/page.tsx frontend/components frontend/tests
git commit -m "refactor(api): il contratto del dig diventa neutro rispetto alla sorgente

pile_pages -> pile_total + pile_reach (item, non pagine): 'seme morto',
'pila corta' e 'ne vedi solo N di M' diventano una sola regola valida per
tutte le sorgenti, e DISCOGS_PAGE_SIZE sparisce dal frontend.

discogs_id/discogs_url -> source_id/source_url, piu' stream_url. La richiesta
di dig accetta source, per ora solo discogs. Comportamento invariato."
```

---

### Task 6: Dettaglio release per entrambe le sorgenti

**Files:**
- Modify: `backend/app/schemas.py`, `backend/app/routers/discovery.py`
- Modify: `frontend/lib/api/{types.ts,discovery.ts}`
- Modify: `frontend/components/discovery-tracklist-panel.tsx`
- Modify: `backend/tests/test_discovery.py` (o `test_discovery_router_http.py`)

**Interfaces:**
- Produces (HTTP): `GET /api/discovery/release?source=discogs&id=<int>` e
  `GET /api/discovery/release?source=bandcamp&id=<band_id>:<item_id>`, risposta
  `DiscoveryReleaseOut { source, source_id, source_url, title, artist, thumb_url,
  year, label, tracks: [{position, title, duration_seconds, stream_url}], videos }`.
- Produces (frontend): `getDiscoveryRelease(source, sourceId)`.

- [ ] **Step 1: Scrivere i test del router (falliscono)**

In `backend/tests/test_discovery_router_http.py`:

```python
def test_release_detail_of_a_bandcamp_lead(client, monkeypatch):
    from app.routers import discovery as router_mod

    class _FakeBandcamp:
        def tralbum(self, *, band_id, tralbum_id, tralbum_type="a"):
            assert (band_id, tralbum_id) == (2920024821, 1022287860)
            return {
                "title": "Love Letter", "tralbum_artist": "Inox Traxx",
                "bandcamp_url": "https://ostgut.bandcamp.com/album/love-letter",
                "art_id": 2027095290, "label": "Ostgut Ton", "release_date": 1782432000,
                "tags": [{"name": "techno"}],
                "tracks": [{"track_num": 1, "title": "Love Letter", "duration": 212.012,
                            "streaming_url": {"mp3-128": "https://bandcamp/stream/1"}}],
            }

        def close(self):
            pass

    monkeypatch.setattr(router_mod, "BandcampClient", lambda: _FakeBandcamp())
    c, _ = client
    r = c.get("/api/discovery/release", params={"source": "bandcamp",
                                                "id": "2920024821:1022287860"})
    assert r.status_code == 200
    body = r.json()
    assert body["source"] == "bandcamp"
    assert body["artist"] == "Inox Traxx"
    assert body["source_url"].endswith("/album/love-letter")
    assert body["tracks"][0]["stream_url"] == "https://bandcamp/stream/1"
    assert body["tracks"][0]["duration_seconds"] == 212
    assert body["videos"] == []


@pytest.mark.parametrize("bad", ["notanumber", "1:2:3", "abc:1", ""])
def test_release_detail_rejects_a_malformed_id(client, bad):
    c, _ = client
    r = c.get("/api/discovery/release", params={"source": "bandcamp", "id": bad})
    assert r.status_code == 400
```

- [ ] **Step 2: Eseguire per vederli fallire**

Run: `cd backend && python -m pytest tests/test_discovery_router_http.py -q -k release_detail`
Expected: FAIL 404 — la rotta è ancora `/release/{discogs_id}`.

- [ ] **Step 3: Rinominare gli schemi del dettaglio**

In `backend/app/schemas.py`, sostituire `DiscogsTrackOut` e `DiscogsReleaseOut`
(mantenendo `DiscogsVideoOut` com'è):

```python
class DiscoveryTrackOut(BaseModel):
    position: str
    title: str
    duration_seconds: int | None = None
    # Popolato solo da Bandcamp: le tracce Discogs non hanno audio.
    stream_url: str | None = None


class DiscoveryReleaseOut(BaseModel):
    source: str
    source_id: str
    source_url: str | None = None
    title: str
    artist: str
    thumb_url: str | None = None
    year: int | None = None
    label: str | None = None
    tracks: list[DiscoveryTrackOut] = []
    # Video YouTube della release: solo Discogs. Su Bandcamp e' sempre vuota, perche'
    # le tracce hanno gia' lo stream vero.
    videos: list[DiscogsVideoOut] = []
```

Aggiornare gli import in `backend/app/routers/discovery.py`.

- [ ] **Step 4: Riscrivere l'endpoint**

In `backend/app/routers/discovery.py`, sostituire `get_release_detail`:

```python
def _bandcamp_ids(raw: str) -> tuple[int, int]:
    """"band_id:item_id" -> (band_id, item_id).

    Solo interi: nessun URL attraversa il confine, quindi non c'e' niente da far
    seguire al backend e nessun allowlist di host da tenere corretto per sempre.
    """
    parts = (raw or "").split(":")
    if len(parts) != 2 or not all(p.isdigit() for p in parts):
        raise api_error(400, "discovery_bad_id",
                        "Id Bandcamp non valido: atteso 'band_id:item_id'.")
    return int(parts[0]), int(parts[1])


@router.get("/release", response_model=DiscoveryReleaseOut)
def get_release_detail(source: str = "discogs", id: str = ""):
    """Dettaglio di un disco del dig: tracklist reale, fetch lazy all'apertura del
    pannello (mai in batch per tutta la griglia)."""
    if source == "bandcamp":
        return _bandcamp_release(*_bandcamp_ids(id))
    if not id.isdigit():
        raise api_error(400, "discovery_bad_id", "Id Discogs non valido.")
    return _discogs_release(int(id))
```

`_discogs_release(discogs_id)` è il corpo attuale di `get_release_detail`, con il
`return` adattato:

```python
    return DiscoveryReleaseOut(
        source="discogs", source_id=str(discogs_id),
        source_url=f"https://www.discogs.com{uri}" if uri.startswith("/") else (uri or None),
        title=payload.get("title") or "", artist=artist,
        thumb_url=images[0].get("uri") if images else None,
        year=payload.get("year"), label=labels[0].get("name") if labels else None,
        tracks=tracks, videos=[DiscogsVideoOut(**v) for v in extract_youtube_videos(payload)],
    )
```

E il nuovo ramo Bandcamp:

```python
def _bandcamp_release(band_id: int, item_id: int) -> DiscoveryReleaseOut:
    client = BandcampClient()
    try:
        payload = client.tralbum(band_id=band_id, tralbum_id=item_id)
    except BandcampError as exc:
        raise api_error(502, "discovery_provider_error",
                        f"Discovery provider error: {exc}", reason=str(exc)) from exc
    finally:
        client.close()

    tracks = [
        DiscoveryTrackOut(
            position=str(item.get("track_num") or ""),
            title=item.get("title") or "",
            duration_seconds=(int(item["duration"]) if item.get("duration") else None),
            stream_url=(item.get("streaming_url") or {}).get("mp3-128"),
        )
        for item in (payload.get("tracks") or [])
        if item.get("title")
    ]
    return DiscoveryReleaseOut(
        source="bandcamp", source_id=f"{band_id}:{item_id}",
        source_url=payload.get("bandcamp_url"),
        title=payload.get("title") or "",
        artist=payload.get("tralbum_artist") or "Sconosciuto",
        thumb_url=_art_url(payload.get("art_id"), size="16"),
        year=_bc_year_from_epoch(payload.get("release_date")),
        label=payload.get("label"),
        tracks=tracks,
        videos=[],
    )
```

`_art_url` si importa da `app.services.dig_sources.bandcamp`.
`_bc_year_from_epoch` va aggiunto lì accanto a `_bc_year`:

```python
def _bc_year_from_epoch(value: Any) -> int | None:
    """`tralbum_details` da' la data come timestamp unix, non come stringa."""
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc).year
    except (TypeError, ValueError, OSError):
        return None
```

- [ ] **Step 5: Eseguire i test backend**

Run: `cd backend && python -m pytest tests -q`
Expected: PASS. I test esistenti che chiamano `/api/discovery/release/{id}` vanno
aggiornati alla nuova rotta con query.

- [ ] **Step 6: Aggiornare il frontend del pannello**

In `frontend/lib/api/types.ts`: rinominare `DiscogsRelease` → `DiscoveryRelease` con i
nuovi campi (`source`, `source_id`, `source_url`, tracce con `stream_url`).
In `frontend/lib/api/discovery.ts`:

```ts
export function getDiscoveryRelease(source: string, sourceId: string) {
  return apiGet<DiscoveryRelease>("/api/discovery/release", { source, id: sourceId });
}
```

In `frontend/components/discovery-tracklist-panel.tsx`:
- la guardia diventa `lead?.source_id != null`, e `PanelBody` si chiave su
  `lead.source_id`;
- il fetch diventa `getDiscoveryRelease(lead.source, lead.source_id!)`;
- il link esterno usa `release.source_url` e come etichetta il nome della sorgente
  (`release.source === "bandcamp" ? "Bandcamp" : "Discogs"`);
- `SaveAllButton` e `TrackRow` usano `release.source_url` al posto di
  `release.discogs_url`;
- in `TrackRow`, l'item passato al player porta lo stream della traccia quando c'è:

```tsx
              item: {
                key: `t:${release.source_id}:${track.position}:${track.title}`,
                artist: release.artist,
                title: track.title,
                sourceId: release.source_id,
                source: release.source,
                streamUrl: track.stream_url,
                level: "track",
                label: track.title,
                addInput: input,
              },
```

(Il campo `streamUrl` di `PreviewItem` arriva nella Task 7; se questa task viene
eseguita prima, aggiungerlo qui come opzionale e lasciarlo inutilizzato.)

- [ ] **Step 7: Verificare il frontend**

Run: `cd frontend && npm run lint && npx tsc --noEmit && npm run test:unit`
Expected: verde.

- [ ] **Step 8: Verificare nel browser**

Aprire `/discovery`, scavare `Acid House`, cliccare una card.
Expected: il pannello mostra la tracklist come prima, col link "Discogs".

- [ ] **Step 9: Commit**

```bash
git status --porcelain
git add backend/app/schemas.py backend/app/routers/discovery.py \
        backend/app/services/dig_sources/bandcamp.py backend/tests \
        frontend/lib frontend/components/discovery-tracklist-panel.tsx
git commit -m "feat(dig): dettaglio release per entrambe le sorgenti

GET /release?source=&id= al posto di /release/{discogs_id}. Bandcamp passa da
tralbum_details: id numerici soltanto, nessun URL attraversa il confine e
quindi nessuna superficie SSRF. Le tracce guadagnano stream_url, popolato
solo da Bandcamp."
```

---

### Task 7: Bandcamp accesa nella UI

La prima task in cui l'utente vede Bandcamp.

**Files:**
- Modify: `backend/app/routers/discovery.py`
- Modify: `frontend/lib/player.tsx`, `frontend/components/docked-player.tsx`
- Modify: `frontend/components/discovery-dig-bar.tsx`, `frontend/components/discovery-lead-grid.tsx`
- Modify: `frontend/app/discovery/page.tsx`
- Modify: `frontend/lib/i18n/{it,en}.ts`
- Modify: `frontend/tests/discovery-dig-bar.test.tsx`

**Interfaces:**
- Consumes: `BandcampSource` (Task 3-4), `DigSourceKey`/`WINDOW_ITEMS` (Task 5),
  `stream_url` sul lead (Task 5).
- Produces: `PreviewItem` con `source: string`, `sourceId: string | null`,
  `streamUrl?: string | null`; `t.discovery.sourceLabel`, `sourceDiscogs`,
  `sourceBandcamp`, e le stringhe del seme morto parametrizzate sul nome sorgente.

- [ ] **Step 1: Scrivere il test del router (fallisce)**

In `backend/tests/test_discovery_router_http.py`:

```python
def test_dig_with_source_bandcamp_uses_the_bandcamp_source(client, monkeypatch):
    from app.routers import discovery as router_mod

    seen = {}

    def _fake_dig(db, **kw):
        seen["source"] = kw["source"].name
        from app.services.discovery_dig import DigResult
        return DigResult(seed_type="genre", value="Techno", leads=[],
                         pile_total=434149, pile_reach=3000, seed_resolution="tag")

    monkeypatch.setattr(router_mod, "dig", _fake_dig)
    c, _ = client
    r = c.post("/api/discovery/dig",
               json={"seed_type": "genre", "value": "Techno", "source": "bandcamp"})
    assert r.status_code == 200
    assert seen["source"] == "bandcamp"
    assert r.json()["pile_reach"] == 3000


def test_a_bandcamp_provider_error_is_a_502_not_a_500(client, monkeypatch):
    from app.integrations.bandcamp import BandcampError
    from app.routers import discovery as router_mod

    def _boom(db, **kw):
        raise BandcampError("rate limit")

    monkeypatch.setattr(router_mod, "dig", _boom)
    c, _ = client
    r = c.post("/api/discovery/dig",
               json={"seed_type": "genre", "value": "Techno", "source": "bandcamp"})
    assert r.status_code == 502
```

- [ ] **Step 2: Eseguire per vederli fallire**

Run: `cd backend && python -m pytest tests/test_discovery_router_http.py -q -k bandcamp`
Expected: FAIL — il router costruisce sempre `DiscogsSource`.

- [ ] **Step 3: Ramificare il router sulla sorgente**

In `backend/app/routers/discovery.py`, sostituire il corpo di `dig_endpoint`:

```python
@router.post("/dig", response_model=DiscoveryDigResponse)
def dig_endpoint(req: DiscoveryDigRequest, db: Session = Depends(get_db)):
    """Lista-dig a volume per genere/stile o etichetta (lead non risolti)."""
    client = BandcampClient() if req.source == "bandcamp" else DiscogsClient()
    source = BandcampSource(client) if req.source == "bandcamp" else DiscogsSource(client)
    try:
        result = dig(db, seed_type=req.seed_type, value=req.value,
                     source=source, depth=req.depth)
    except (DiscogsError, BandcampError) as exc:
        # Rate limit / token mancante / endpoint cambiato: 502 esplicito, mai uno
        # "zero risultati" muto — l'utente deve poter distinguere "non c'e' niente"
        # da "il provider non ha risposto".
        raise api_error(502, "discovery_provider_error", f"Discovery provider error: {exc}",
                        reason=str(exc)) from exc
    finally:
        client.close()
    return DiscoveryDigResponse(...)   # invariato dalla Task 5
```

- [ ] **Step 4: Eseguire i test backend**

Run: `cd backend && python -m pytest tests -q`
Expected: PASS.

- [ ] **Step 5: Far suonare lo stream diretto**

In `frontend/lib/player.tsx`, estendere `PreviewItem` e `play`:

```tsx
export type PreviewItem = {
  key: string;
  artist: string;
  title: string;
  source: string;
  sourceId: string | null;
  /** Stream diretto quando la sorgente lo regala (Bandcamp): niente risoluzione. */
  streamUrl?: string | null;
  level: "release" | "track";
  label: string;
  addInput?: DiscoveryImportInput;
};
```

In `play`, prima della risoluzione async:

```tsx
    const item = source.item;
    // Bandcamp regala lo stream dentro il risultato del dig: suonarlo subito evita
    // un round-trip e da' il brano intero invece dei 30s di iTunes.
    if (item.streamUrl) {
      setData({ kind: "itunes", audio_url: item.streamUrl, youtube_video_id: null,
                source_url: null, matched_title: item.title });
      setStatus("playing");
      return;
    }
    setStatus("loading");
    discoveryPreview({ artist: item.artist, title: item.title,
                       discogsId: item.source === "discogs" && item.sourceId
                         ? Number(item.sourceId) : null,
                       level: item.level })
```

Il `kind: "itunes"` riusa il ramo `<audio>` del dock, che è esattamente ciò che serve
per un mp3 diretto. Se preferisci un nome onesto, aggiungi `"stream"` al tipo
`DiscoveryPreview["kind"]` in `types.ts` e trattalo come `"itunes"` in
`docked-player.tsx` (riga ~119): **una sola condizione da cambiare**.

- [ ] **Step 6: Aggiornare i chiamanti del player**

In `frontend/components/discovery-lead-grid.tsx`, `LeadCell`:

```tsx
              item: {
                key: `r:${lead.source_id ?? "x"}`,
                artist: lead.artist,
                title: lead.title,
                source: lead.source,
                sourceId: lead.source_id,
                streamUrl: lead.stream_url,
                level: "release",
                label: lead.title,
                addInput: {
                  artist: lead.artist,
                  title: lead.title,
                  album_art_url: lead.thumb_url,
                  url: lead.source_url,
                },
              },
```

- [ ] **Step 7: Aggiungere il selettore di sorgente**

In `frontend/components/discovery-dig-bar.tsx`, nuove prop `source: DigSourceKey` e
`onSourceChange: (s: DigSourceKey) => void`, e un `SegmentedControl` prima del
Combobox:

```tsx
        <div className="flex items-center gap-2">
          <span className="text-[10px] uppercase tracking-wider text-muted">
            {t.discovery.sourceLabel}
          </span>
          <SegmentedControl
            value={source}
            onChange={(v) => onSourceChange(v as DigSourceKey)}
            options={[
              { value: "discogs", label: t.discovery.sourceDiscogs },
              { value: "bandcamp", label: t.discovery.sourceBandcamp },
            ]}
            disabled={busy}
          />
        </div>
```

In `frontend/app/discovery/page.tsx`: `source` entra nello stato **e nell'URL**, come
`seed`/`value`/`depth` — così il dig si rilancia da solo tramite `paramsKey`, senza
effetti nuovi.

```tsx
  const initialSource: DigSourceKey =
    searchParams.get("source") === "bandcamp" ? "bandcamp" : "discogs";
  const [source, setSource] = useState<DigSourceKey>(initialSource);
```

`executeDig` prende la sorgente e la passa sia a `discoveryDig` sia all'etichetta del
job (`jobs.updateClientJob("dig", { detail: \`${sourceName} · ${value}\` })`);
`runDig` e `navigateDig` scrivono `params.set("source", source)`; l'effect su
`paramsKey` legge `source` dall'URL e risincronizza lo stato come già fa per gli altri.

`pickSurprise` non cambia: "Sorprendimi" pesca un seme, non una sorgente, e resta
sulla sorgente selezionata.

- [ ] **Step 8: Parametrizzare le stringhe che nominano Discogs**

In `frontend/lib/i18n/it.ts`, nella sezione `discovery`:

```ts
    sourceLabel: "Sorgente",
    sourceDiscogs: "Discogs",
    sourceBandcamp: "Bandcamp",
    emptyPile: (src: string) => `nessuna pila: ${src} non conosce questo seme`,
    deadSeedTitle: (src: string) => `Seme sconosciuto a ${src}`,
    deadSeedBody: (value: string, src: string) =>
      `${src} non ha nessun disco catalogato come “${value}”: quel nome non esiste nel suo vocabolario. Non c'entra la tua libreria, e cambiare profondità non aiuta. Scegli una voce dai suggerimenti del campo.`,
    broadSeed: (total: string, reachable: string, src: string) =>
      `Seme molto ampio: ${total} dischi su ${src}, ne vedi solo i ${reachable} più in cima. Un sottogenere più preciso scava meglio.`,
```

Stesse chiavi in `en.ts`, tradotte. Aggiornare i tre punti d'uso
(`discovery-dig-bar.tsx`, `discovery-lead-grid.tsx`, `page.tsx`) passando il nome
leggibile della sorgente, ricavato da `dig.source`.

- [ ] **Step 9: Aggiornare il test della barra**

In `frontend/tests/discovery-dig-bar.test.tsx` aggiungere `source="discogs"` e
`onSourceChange={() => {}}` a ogni render, più un test nuovo:

```tsx
it("propaga il cambio di sorgente", async () => {
  const onSourceChange = vi.fn();
  render(<DiscoveryDigBar {...baseProps} source="discogs" onSourceChange={onSourceChange} />);
  await userEvent.click(screen.getByText("Bandcamp"));
  expect(onSourceChange).toHaveBeenCalledWith("bandcamp");
});
```

- [ ] **Step 10: Verificare il frontend**

Run: `cd frontend && npm run lint && npx tsc --noEmit && npm run test:unit`
Expected: verde.

- [ ] **Step 11: Verificare il giro completo nel browser**

Con backend e frontend avviati, su `/discovery`:

1. sorgente **Bandcamp**, seme `Techno`, profondità "Superficie" → card con copertine,
   e la riga della risposta dice che la pila è molto più alta di quanto se ne vede;
2. play su una card → **parte subito**, senza attesa di risoluzione;
3. profondità "In fondo" → il dig ci mette ~20s e restituisce card diverse;
4. click su una card → il pannello mostra la tracklist con le durate e il link
   "Bandcamp";
5. sorgente Bandcamp, seme **etichetta** (es. `Ostgut Ton`) → lead, e il controllo di
   profondità è **disabilitato** con la nota "pila corta";
6. seme `zzzznotatag` → empty state "seme sconosciuto a Bandcamp";
7. tornare su **Discogs** con lo stesso seme → il dig di prima, invariato.

Expected: tutti e sette. Allegare uno screenshot del punto 1 e del punto 5.

- [ ] **Step 12: Commit**

```bash
git status --porcelain
git add backend/app/routers/discovery.py backend/tests frontend/lib frontend/components \
        frontend/app/discovery/page.tsx frontend/tests
git commit -m "feat(dig): Bandcamp selezionabile dalla barra di scavo

La sorgente entra nell'URL come seme e profondita', quindi il dig si rilancia
col meccanismo che c'e' gia'. Il player suona lo stream Bandcamp diretto senza
risoluzione: brano intero invece dei 30s di iTunes.

Le stringhe che nominavano Discogs prendono il nome della sorgente: dire
'Discogs non conosce questo seme' dopo un dig Bandcamp sarebbe una bugia."
```

---

### Task 8: Documentazione

**Files:**
- Modify: `CLAUDE.md`, `README.md`, `docs/API.md`, `docs/ARCHITECTURE.md`,
  `docs/DEPENDENCIES.md`, `docs/ROADMAP.md`, `PROGRESS.md`

- [ ] **Step 1: `docs/API.md`**

Nella sezione Discovery: `POST /api/discovery/dig` guadagna `source`; la risposta
espone `pile_total`/`pile_reach` al posto di `pile_pages` (spiegando che sono item e
che `pile_reach <= 300` significa profondità inerte); i lead espongono
`source_id`/`source_url`/`stream_url`; `GET /api/discovery/release/{id}` diventa
`GET /api/discovery/release?source=&id=`, documentando il formato
`band_id:item_id` per Bandcamp e il 400 su id malformato.

- [ ] **Step 2: `docs/ARCHITECTURE.md`**

Nella pipeline di Discovery: il dig ha due sorgenti dietro il protocollo `DigSource`;
il motore ragiona in item e ogni sorgente traduce nella propria paginazione. Citare i
tre limiti misurati di Bandcamp: niente have/want, niente stili in lista, `reach` di
3.000 item per costo di sfogliata.

- [ ] **Step 3: `docs/DEPENDENCIES.md`**

Nuova voce Bandcamp: endpoint interni non documentati, nessuna chiave né token, uso
personale, e il test di contratto `-m network` come strumento diagnostico quando
smette di funzionare.

- [ ] **Step 4: `CLAUDE.md`**

Aggiornare la riga "The remaining external providers serve **Discovery only**: Discogs
(dig "Scava"), Spotify (resolver)" includendo Bandcamp, e la nota sulla preview
effimera: oltre a iTunes/YouTube ora c'è lo stream Bandcamp, ugualmente effimero e mai
scaricato.

- [ ] **Step 5: `README.md`**

Nel racconto della Discovery, una riga: il dig ha due casse, Discogs (profondità e
rarità) e Bandcamp (comprabile, con l'ascolto vero).

- [ ] **Step 6: `docs/ROADMAP.md` e `PROGRESS.md`**

ROADMAP, sezione stato/decisioni: dig Bandcamp completato (2026-07-22), col seam
`DigSource` e i limiti accettati (più rumoroso, badge derivato, endpoint interni).
PROGRESS: voce datata con il percorso, le misure fatte contro l'API e lo scivolamento
di una pagina del dig Discogs.

- [ ] **Step 7: Verifica finale**

```bash
cd backend && python -m pytest tests -q
cd ../frontend && npm run lint && npx tsc --noEmit && npm run test:unit && npm run test:e2e
```
Expected: tutto verde. Se `test:e2e` richiede un `backend/.venv` nel worktree e non
c'è, dirlo esplicitamente invece di dare l'e2e per passato.

- [ ] **Step 8: Commit**

```bash
git status --porcelain
git add CLAUDE.md README.md docs PROGRESS.md
git commit -m "docs: il dig ha due sorgenti

API (source, pile_total/pile_reach, source_id/source_url/stream_url, nuovo
endpoint release), architettura (il seam DigSource), dipendenze (endpoint
interni Bandcamp e test di contratto), roadmap e diario."
```

---

## Self-Review

**Copertura della spec.** §1 seam → Task 1. §2 sorgente Bandcamp: semi tag → Task 3,
seme etichetta → Task 4, profondità/costo → Task 3 (`BANDCAMP_REACH`, sfogliata),
mapping → Task 3-4, de-noise → Task 3 (scarti strutturali), gusto → Task 1
(`_weights`), spiegazioni → nessuna task, **e va detto perché**: i reason code
degradano da soli senza una riga di codice (`rare_wanted` e `deep_cut` leggono
`have`/`want` che restano 0, `style_match` legge stili che restano vuoti). Il test
che lo dimostra è in Task 3 fra i mapping (`(lead.have, lead.want) == (0, 0)` e
`lead.styles == []`). §3 preview → Task 7, pannello → Task 6. §4 API → Task 5 e 6.
§5 frontend → Task 5 e 7. §6 errori e tenuta → Task 2 (client, contratto) e Task 3
(regola dello skip) e Task 7 (502). §7 test → distribuiti. §8 rischio → Task 8 (docs).

**Placeholder.** Nessun "TBD"/"simile alla Task N": il codice è ripetuto per esteso
dove serve. Tre punti restano deliberatamente aperti, e ognuno dice cosa fare:
l'import circolare in Task 1 Step 8 (con la soluzione alternativa scritta), il nome
del file di configurazione pytest in Task 2 Step 7 (con il fallback), e la scelta fra
riusare `kind: "itunes"` o aggiungere `"stream"` in Task 7 Step 5 (con l'unica riga da
cambiare).

**Coerenza dei tipi.** `source_id` è `str` ovunque (dataclass, DTO, TS, query
dell'endpoint release) e per Bandcamp vale sempre `"band_id:item_id"`, prodotto in
Task 3 e 4 e consumato in Task 6. `Pile.handle` è `dict` per Discogs (i filtri),
`str` per il tag Bandcamp, `list` per la discografia: è dichiarato `Any` e documentato
nel docstring. `_window` restituisce `(offset, count)` in Task 1 ed è consumato solo
da `dig()`. `WINDOW_ITEMS` è 300 sia in `dig_sources/__init__.py` sia in
`lib/discovery-dig.ts`, e i due punti si citano a vicenda.
