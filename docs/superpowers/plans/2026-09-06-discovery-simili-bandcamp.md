# Discovery "Simili" su Bandcamp — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Da una traccia posseduta, mostrare in Discovery i lead Bandcamp imparentati con essa (stesso artista, stessa etichetta, opzionalmente stesso stile e periodo), non ancora posseduti.

**Architecture:** Un nuovo servizio `discovery_similar.py` affiancato a `discovery_dig.py` riusa deduplica, profilo di gusto e punteggio del dig, ma sostituisce la coppia probe/fetch con risoluzione + espansione lungo archi. L'unica sorgente è `BandcampSimilar`, che vive in `dig_sources/bandcamp.py` e condivide i mapper con `BandcampSource`. Il frontend riusa la pagina `/discovery` e la sua griglia: cambia solo l'intestazione, dalla barra dello scavo a un'intestazione "Partendo da".

**Tech Stack:** Python 3 + FastAPI + SQLAlchemy + Pydantic (backend), pytest; Next.js 16 App Router + React + Tailwind (frontend), vitest + Testing Library.

**Spec:** `docs/superpowers/specs/2026-09-06-discovery-simili-bandcamp-design.md`

## Global Constraints

- **Fonte unica Bandcamp.** `source` accetta solo `"bandcamp"`; qualsiasi altro valore è `400 discovery_bad_source`. Discogs è fuori scope.
- **Nessun fallback silenzioso.** Ogni arco assente porta un `absent_reason` fra `no_band | self_released | no_label | no_tag | no_year | off`. Ogni risoluzione porta `resolution` fra `"release" | "artist_only"`, oppure `origin=None`.
- **Errore del provider = 502 `discovery_provider_error`**, mai una lista vuota. "Nessun simile" e "Bandcamp giù" restano distinguibili.
- **`PERIOD_YEARS = 3`**: la finestra dell'arco stile è `|year - origin.year| <= 3`, su entrambi i lati.
- **Tag generici esclusi** dalla scelta del tag di stile: `{"electronic", "music", "dance"}`, più ogni tag con `isloc=True`.
- **Codici arco**: `same_artist`, `same_label`, `same_period_style`. Sono sia le chiavi di `edges` sia i `Reason.code` sui lead.
- **Testi utente in entrambi i dizionari**, `frontend/lib/i18n/it.ts` e `frontend/lib/i18n/en.ts`. Nessuna stringa hardcoded nei componenti.
- **Test non vacui**: ogni asserzione va provata rompendo il codice prima di considerarla buona (regola di progetto).
- **Commit senza `Co-Authored-By`.**
- **Prima di ogni commit**: `git status --porcelain` e stage dei soli file della task. Altre sessioni possono lavorare sullo stesso checkout.

**Comandi:**
- Backend test: `cd backend && source .venv/bin/activate && python -m pytest tests/<file> -v`
- Frontend test: `cd frontend && npm run test:unit -- <file>`
- Frontend lint: `cd frontend && npm run lint`

## File Structure

**Backend**
- `backend/app/services/discovery_similar.py` (nuovo) — `Origin`, `EdgeReport`, `SimilarResult`, `SimilarSource` Protocol, funzione `similar()`. Orchestrazione e ranking. Non conosce la forma dei dati Bandcamp.
- `backend/app/services/dig_sources/bandcamp.py` (modifica, in coda al file) — classe `BandcampSimilar`: `resolve`, `expand`, `to_lead`. È l'unico posto che conosce i payload Bandcamp.
- `backend/app/schemas.py` (modifica) — `OriginOut`, `EdgeReportOut`, `DiscoverySimilarResponse`.
- `backend/app/routers/discovery.py` (modifica) — endpoint `GET /similar`.
- `backend/tests/test_discovery_similar.py` (nuovo) — motore + sorgente, con client finto.
- `backend/tests/test_discovery_router_http.py` (modifica) — 404/400/502 dell'endpoint.

**Frontend**
- `frontend/lib/api/types.ts` (modifica) — `SimilarOrigin`, `SimilarEdge`, `DiscoverySimilarResponse`.
- `frontend/lib/api/discovery.ts` (modifica) — `discoverySimilar(trackId, opts)`.
- `frontend/components/discovery-similar-header.tsx` (nuovo) — intestazione "Partendo da".
- `frontend/components/discovery-lead-grid.tsx` (modifica) — generalizzazione delle props.
- `frontend/app/discovery/page.tsx` (modifica) — ramo modalità simili.
- `frontend/app/tracks/page.tsx` (modifica) — bottone "Simili".
- `frontend/lib/i18n/it.ts`, `en.ts` (modifica) — testi.
- `frontend/tests/discovery-similar-header.test.tsx` (nuovo), `frontend/tests/discovery-lead-grid.test.tsx` (nuovo).

**Docs**
- `docs/API.md`, `docs/ROADMAP.md`, `PROGRESS.md` (modifica).

L'ordine delle task va dal basso verso l'alto: tipi e motore, poi sorgente, poi endpoint, poi frontend. Ogni task lascia la suite verde.

---

### Task 1: Ossature del motore e risoluzione degli archi

**Files:**
- Create: `backend/app/services/discovery_similar.py`
- Test: `backend/tests/test_discovery_similar.py`

**Interfaces:**
- Consumes: da `app.services.discovery_dig` gli helper `_norm`, `_dedup_key`, `_owned_index`, `_is_owned`, `_library_tracks`, `_select`, `_weights`, `_score`, `TasteProfile`; da `app.services.dig_sources` `DiscoveryLead` e `Reason`.
- Produces: `Origin`, `EdgeReport`, `SimilarResult`, `SimilarSource` (Protocol), `similar(db, track, *, source, style_period, library=None) -> SimilarResult`, costante `PERIOD_YEARS = 3`.

- [ ] **Step 1: Write the failing test**

Crea `backend/tests/test_discovery_similar.py`:

```python
"""Il motore dei simili: orchestrazione, archi, ranking. Nessuna rete."""

import pytest

from app.models import Track
from app.services.dig_sources import DiscoveryLead
from app.services.discovery_similar import (
    EdgeReport,
    Origin,
    SimilarResult,
    similar,
)


def _track(**kw) -> Track:
    """Una Track non persistita: il motore legge solo gli attributi."""
    base = dict(id=1, artist="Jasmín", title="Bite The Hand", album="Bite The Hand",
                label="Hessle Audio", genre="Bass", year=2025, has_local_file=True)
    base.update(kw)
    return Track(**base)


def _lead(artist="Pearson Sound", title="Which Way Is Up", **kw) -> DiscoveryLead:
    return DiscoveryLead(artist=artist, artist_keys=[artist.lower()], title=title,
                         source="bandcamp", **kw)


class _FakeSource:
    """Sorgente finta: restituisce origine e archi prefissati, registra le chiamate."""

    name = "bandcamp"

    def __init__(self, origin=None, edges=None):
        self._origin = origin
        self._edges = edges or []
        self.expand_calls: list[dict] = []

    def resolve(self, track):
        return self._origin

    def expand(self, origin, *, style_period):
        self.expand_calls.append({"style_period": style_period})
        return list(self._edges)

    def to_lead(self, edge, raw):
        return raw


def _origin(**kw) -> Origin:
    base = dict(artist="Jasmín", band_id=637178087, title="Bite The Hand",
                tralbum_id=4024735967, tralbum_type="a", label="Hessle Audio",
                label_id=2788766970, tag="bass", year=2025,
                source_url="https://x.bandcamp.com/album/y", resolution="release",
                discography=[])
    base.update(kw)
    return Origin(**base)


def test_artist_absent_from_bandcamp_gives_no_origin_and_no_leads(db):
    source = _FakeSource(origin=None)
    result = similar(db, _track(), source=source, style_period=False, library=[])
    assert result.origin is None
    assert result.leads == []
    assert result.edges["same_artist"] == EdgeReport(count=None, absent_reason="no_band")
    assert result.edges["same_label"].absent_reason == "no_band"
    assert result.edges["same_period_style"].absent_reason == "no_band"
    # Nessuna espansione: senza band non c'è nulla da espandere.
    assert source.expand_calls == []


def test_leads_carry_one_reason_per_edge_that_reached_them(db):
    lead = _lead()
    source = _FakeSource(origin=_origin(), edges=[("same_artist", lead),
                                                  ("same_label", lead)])
    result = similar(db, _track(), source=source, style_period=False, library=[])
    assert len(result.leads) == 1
    codes = sorted(r.code for r in result.leads[0].reasons)
    assert codes == ["same_artist", "same_label"]


def test_edge_counts_report_leads_produced_after_dedup(db):
    source = _FakeSource(origin=_origin(), edges=[
        ("same_artist", _lead(title="A")),
        ("same_label", _lead(title="B")),
        ("same_label", _lead(title="C")),
    ])
    result = similar(db, _track(), source=source, style_period=False, library=[])
    assert result.edges["same_artist"].count == 1
    assert result.edges["same_label"].count == 2
    assert len(result.leads) == 3


def test_style_period_off_is_an_absent_edge_not_a_zero_count(db):
    source = _FakeSource(origin=_origin(), edges=[("same_artist", _lead())])
    result = similar(db, _track(), source=source, style_period=False, library=[])
    assert result.edges["same_period_style"] == EdgeReport(count=None, absent_reason="off")
    assert source.expand_calls == [{"style_period": False}]


def test_a_label_the_source_cannot_walk_is_absent_not_a_zero_count(db):
    # `label_id` uguale alla band: autoprodotto. L'arco non è percorribile, e dire
    # "0 dischi" affermerebbe di aver guardato.
    source = _FakeSource(origin=_origin(label_id=637178087, label="Jasmín"),
                         edges=[("same_artist", _lead())])
    result = similar(db, _track(), source=source, style_period=False, library=[])
    assert result.edges["same_label"] == EdgeReport(count=None,
                                                    absent_reason="self_released")


def test_a_missing_label_in_artist_only_is_absent_for_its_own_reason(db):
    source = _FakeSource(origin=_origin(resolution="artist_only", label=None,
                                        label_id=None, title=None, tralbum_id=None),
                         edges=[("same_artist", _lead())])
    result = similar(db, _track(), source=source, style_period=False, library=[])
    assert result.edges["same_label"].absent_reason == "no_label"


def test_one_artist_cannot_monopolise_the_grid(db):
    # La discografia dell'artista di partenza mangerebbe la griglia senza il tetto
    # che il dig applica già (_MAX_PER_ARTIST).
    edges = [("same_artist", _lead(title=f"Disco {i}")) for i in range(5)]
    source = _FakeSource(origin=_origin(), edges=edges)
    result = similar(db, _track(), source=source, style_period=False, library=[])
    assert len(result.leads) == 2
    # L'arco però ha davvero prodotto 5 lead: il tetto taglia la vista, non il conto.
    assert result.edges["same_artist"].count == 5


def test_owned_leads_are_dropped(db):
    owned = _track(id=2, artist="Pearson Sound", title="Which Way Is Up",
                   album="Which Way Is Up")
    source = _FakeSource(origin=_origin(), edges=[("same_artist", _lead())])
    result = similar(db, _track(), source=source, style_period=False,
                     library=[owned])
    assert result.leads == []
    assert result.edges["same_artist"].count == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_discovery_similar.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'app.services.discovery_similar'`

- [ ] **Step 3: Write minimal implementation**

Crea `backend/app/services/discovery_similar.py`:

```python
"""Discovery "Simili": i parenti di un disco che possiedi.

Stesso mestiere del dig — lead non posseduti, ordinati per gusto — ma il seme non è
un genere astratto: è una traccia della libreria. Al posto della coppia probe/fetch
c'è una coppia risolvi/espandi: la sorgente riconosce la release d'origine, poi
percorre gli archi (stesso artista, stessa etichetta, stesso stile nel periodo) e
restituisce i record grezzi etichettati con l'arco che li ha raggiunti.

Deduplica, profilo di gusto e punteggio sono quelli del dig: qui non si reinventa
niente, si cambia solo da dove arrivano i candidati.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol

from sqlalchemy.orm import Session

from app.services.dig_sources import DiscoveryLead, Reason
from app.services.discovery_dig import (
    TasteProfile,
    _dedup_key,
    _is_owned,
    _library_tracks,
    _owned_index,
    _score,
    _select,
    _weights,
)

logger = logging.getLogger(__name__)

# La semi-ampiezza della finestra temporale dell'arco stile, in anni.
PERIOD_YEARS = 3

# Gli archi, nell'ordine in cui si mostrano. Sono anche i `Reason.code` sui lead.
EDGES = ("same_artist", "same_label", "same_period_style")


@dataclass
class Origin:
    """Cosa la sorgente ha riconosciuto della traccia di partenza."""

    artist: str
    band_id: int
    title: str | None
    tralbum_id: int | None
    tralbum_type: str | None
    label: str | None
    label_id: int | None
    tag: str | None
    year: int | None
    source_url: str | None
    resolution: str  # "release" | "artist_only"
    # La discografia già scaricata da `resolve`: `expand` non la ricompra.
    discography: list[dict] = field(default_factory=list)


@dataclass(frozen=True)
class EdgeReport:
    """Quanti lead ha prodotto un arco, o perché non esiste.

    `count` e `absent_reason` si escludono: un arco percorso ha un conteggio (anche
    zero, se tutto era già posseduto), un arco assente ha un motivo. Confonderli
    farebbe dire alla UI "0 dischi" dove la verità è "non ho potuto guardare".
    """

    count: int | None = None
    absent_reason: str | None = None


@dataclass
class SimilarResult:
    origin: Origin | None
    leads: list[DiscoveryLead] = field(default_factory=list)
    edges: dict[str, EdgeReport] = field(default_factory=dict)


class SimilarSource(Protocol):
    """Una sorgente capace di riconoscere un disco e percorrerne le parentele."""

    name: str

    def resolve(self, track: Any) -> Origin | None: ...

    def expand(self, origin: Origin, *, style_period: bool) -> list[tuple[str, Any]]: ...

    def to_lead(self, edge: str, raw: Any) -> DiscoveryLead | None: ...


def similar(
    db: Session,
    track: Any,
    *,
    source: SimilarSource,
    style_period: bool = False,
    library: list | None = None,
) -> SimilarResult:
    """I lead non posseduti imparentati con `track`, ordinati per gusto."""
    if library is None:
        library = _library_tracks(db)

    origin = source.resolve(track)
    if origin is None:
        return SimilarResult(
            origin=None,
            edges={e: EdgeReport(absent_reason="no_band") for e in EDGES},
        )

    owned_tracks, owned_albums = _owned_index(library)
    profile = TasteProfile.from_tracks(library)

    raw_edges = source.expand(origin, style_period=style_period)

    # Un lead può essere raggiunto da più archi: si tiene una volta sola, con un
    # reason per ogni arco che l'ha raggiunto. La chiave è quella del dig, così
    # "(Original Mix)" e le ristampe collassano come là.
    by_key: dict[tuple[str, str], DiscoveryLead] = {}
    edge_hits: dict[str, int] = {e: 0 for e in EDGES}
    reached: dict[tuple[str, str], list[str]] = {}

    for edge, raw in raw_edges:
        lead = source.to_lead(edge, raw)
        if lead is None:
            continue
        key = _dedup_key(lead.artist_keys[0], lead.title)
        if _is_owned(lead, owned_tracks, owned_albums):
            continue
        if key not in by_key:
            by_key[key] = lead
            edge_hits[edge] += 1
            reached[key] = [edge]
        elif edge not in reached[key]:
            edge_hits[edge] += 1
            reached[key].append(edge)

    weights = _weights("genre", has_styles=False)
    current_year = datetime.now(timezone.utc).year
    leads: list[DiscoveryLead] = []
    for key, lead in by_key.items():
        lead.score = _score(lead, profile, weights, [])
        lead.reasons = [_edge_reason(edge, origin) for edge in reached[key]]
        leads.append(lead)

    selected = _select(leads)

    edges = {e: EdgeReport(count=edge_hits[e]) for e in EDGES}
    for edge, reason in _absent_edges(origin, style_period).items():
        edges[edge] = EdgeReport(absent_reason=reason)

    logger.info("Discovery similar %s track=%r: %s lead (archi %s)",
                source.name, origin.artist, len(selected), edges)
    return SimilarResult(origin=origin, leads=selected, edges=edges)


def _edge_reason(edge: str, origin: Origin) -> Reason:
    if edge == "same_label":
        return Reason(code=edge, data={"label": origin.label or ""})
    if edge == "same_period_style":
        year = origin.year or 0
        return Reason(code=edge, data={
            "tag": origin.tag or "",
            "year_from": year - PERIOD_YEARS,
            "year_to": year + PERIOD_YEARS,
        })
    return Reason(code=edge, data={})


def _absent_edges(origin: Origin, style_period: bool) -> dict[str, str]:
    """Quali archi NON sono stati percorsi, e perché.

    Deciso qui e non nella sorgente: è la stessa logica per qualsiasi sorgente, e
    tenerla accanto a `EDGES` impedisce che un arco nuovo resti senza motivo.

    La condizione deve rispecchiare ESATTAMENTE quando la sorgente riesce a
    percorrere l'arco, non solo quando i dati sono del tutto assenti: una release
    con un nome di etichetta ma senza `label_id`, o con `label_id` uguale alla band,
    non è percorribile, e riportarla come "0 dischi" direbbe che si è guardato.
    """
    absent: dict[str, str] = {}
    if origin.resolution == "release":
        # Percorribile solo con un `label_id` di una band DIVERSA dall'artista.
        if not origin.label_id or origin.label_id == origin.band_id:
            absent["same_label"] = "self_released"
    elif not origin.label:
        # `artist_only`: si passa dal nome nei tag del file, se c'è.
        absent["same_label"] = "no_label"
    if not style_period:
        absent["same_period_style"] = "off"
    elif not origin.tag:
        absent["same_period_style"] = "no_tag"
    elif origin.year is None:
        absent["same_period_style"] = "no_year"
    return absent
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_discovery_similar.py -v`
Expected: PASS, 8 test.

Se `db` non è una fixture disponibile, guarda `backend/tests/conftest.py` e usa il nome che i test del dig usano per la sessione; il motore la usa solo quando `library is None`, quindi in questi test può anche essere `None`.

- [ ] **Step 5: Verifica che i test non siano vacui**

Rompi una cosa alla volta e controlla che il test giusto fallisca:
1. In `similar`, sostituisci `EdgeReport(absent_reason="no_band")` con `EdgeReport(count=0)` → deve fallire `test_artist_absent_from_bandcamp_gives_no_origin_and_no_leads`.
2. Togli il ramo `elif edge not in reached[key]` → deve fallire `test_leads_carry_one_reason_per_edge_that_reached_them`.
3. Togli il `continue` su `_is_owned` → deve fallire `test_owned_leads_are_dropped`.
4. In `_absent_edges`, togli `or origin.label_id == origin.band_id` → deve fallire
   `test_a_label_the_source_cannot_walk_is_absent_not_a_zero_count`.
Ripristina dopo ogni prova.

- [ ] **Step 6: Commit**

```bash
git status --porcelain
git add backend/app/services/discovery_similar.py backend/tests/test_discovery_similar.py
git commit -m "feat(discovery): il motore dei simili, archi e ranking"
```

---

### Task 2: La sorgente Bandcamp — risoluzione

**Files:**
- Modify: `backend/app/services/dig_sources/bandcamp.py` (in coda al file)
- Test: `backend/tests/test_discovery_similar.py` (aggiunge una classe di test)

**Interfaces:**
- Consumes: `Origin` da Task 1; dal client `find_band(name)`, `band_discography(band_id)`, `tralbum(band_id=, tralbum_id=, tralbum_type=)`; gli helper già nel file `_clean_artist`, `_norm`, `_tag_norm`, `_bc_year_from_epoch`.
- Produces: `BandcampSimilar(client)` con `resolve(track) -> Origin | None`; costanti `GENERIC_TAGS`.

- [ ] **Step 1: Write the failing test**

Aggiungi in fondo a `backend/tests/test_discovery_similar.py`:

```python
from app.services.dig_sources.bandcamp import BandcampSimilar


# Payload catturati dall'API reale il 2026-09-06, ridotti ai campi usati.
DISCOGRAPHY_ITEM = {
    "item_id": 4024735967, "item_type": "album", "band_id": 637178087,
    "title": "Bite The Hand That Feeds You", "artist_name": "Jasmín",
    "band_name": "Jasmín", "art_id": 111, "release_date": "26 Jun 2026 00:00:00 GMT",
}

TRALBUM = {
    "label": "Hessle Audio", "label_id": 2788766970,
    "tags": [
        {"name": "Electronic", "norm_name": "electronic", "isloc": False},
        {"name": "Bristol", "norm_name": "bristol", "isloc": True},
        {"name": "bass", "norm_name": "bass", "isloc": False},
    ],
    "release_date": 1761091200,
    "bandcamp_url": "https://jasminhoek.bandcamp.com/album/bite-the-hand-that-feeds-you",
}


class _FakeClient:
    """Client Bandcamp finto: risposte prefissate, chiamate registrate."""

    def __init__(self, band=None, discographies=None, tralbum=None):
        self.band = band
        self.discographies = discographies or {}
        self._tralbum = tralbum or {}
        self.calls: list[tuple] = []

    def find_band(self, name):
        self.calls.append(("find_band", name))
        return self.band

    def band_discography(self, band_id):
        self.calls.append(("band_discography", band_id))
        return list(self.discographies.get(band_id, []))

    def tralbum(self, *, band_id, tralbum_id, tralbum_type="a"):
        self.calls.append(("tralbum", band_id, tralbum_id, tralbum_type))
        return dict(self._tralbum)


def _resolver(**kw) -> tuple[BandcampSimilar, _FakeClient]:
    client = _FakeClient(
        band={"id": 637178087, "name": "Jasmín"},
        discographies={637178087: [DISCOGRAPHY_ITEM]},
        tralbum=TRALBUM,
        **kw,
    )
    return BandcampSimilar(client), client


def test_resolve_matches_the_release_by_album_and_reads_its_details():
    src, client = _resolver()
    origin = src.resolve(_track())
    assert origin.resolution == "release"
    assert origin.band_id == 637178087
    assert origin.tralbum_id == 4024735967
    assert origin.tralbum_type == "a"   # "album" -> "a", non "album"
    assert origin.label == "Hessle Audio"
    assert origin.label_id == 2788766970
    assert origin.year == 2025          # da release_date epoch
    assert origin.source_url == TRALBUM["bandcamp_url"]


def test_resolve_skips_generic_and_location_tags_when_choosing_the_style_tag():
    src, _ = _resolver()
    assert src.resolve(_track()).tag == "bass"


def test_resolve_matches_by_title_when_the_album_tag_is_missing():
    src, _ = _resolver()
    origin = src.resolve(_track(album=None, title="Bite The Hand That Feeds You"))
    assert origin.resolution == "release"


def test_unresolved_release_falls_back_to_the_file_tags():
    src, client = _resolver()
    origin = src.resolve(_track(album="Un disco che non esiste", title="Nemmeno questo"))
    assert origin.resolution == "artist_only"
    assert origin.label == "Hessle Audio"   # dal tag del file
    assert origin.tag == "bass"             # da track.genre "Bass", normalizzato
    assert origin.year == 2025              # da track.year
    # Nessun dettaglio release chiesto: non c'è release da dettagliare.
    assert not any(c[0] == "tralbum" for c in client.calls)


def test_a_band_bandcamp_does_not_know_resolves_to_nothing():
    src = BandcampSimilar(_FakeClient(band=None))
    assert src.resolve(_track()) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_discovery_similar.py -v -k resolve`
Expected: FAIL con `ImportError: cannot import name 'BandcampSimilar'`

- [ ] **Step 3: Write minimal implementation**

Aggiungi in coda a `backend/app/services/dig_sources/bandcamp.py`:

```python
# Quanti item chiedere al discover per l'arco stile. `DISCOVER_PAGE_SIZE` (500) è la
# misura del dig, che deve riempire una finestra; qui l'arco è un rinforzo e la
# finestra temporale scarta già molto, quindi una batch corta basta e costa meno.
STYLE_EDGE_ITEMS = 120

# Tag troppo larghi per definire uno stile: non discriminano niente e il discover
# che ne uscirebbe è indistinguibile da un dig generico.
GENERIC_TAGS = {"electronic", "music", "dance"}

# `item_type` della discografia -> `tralbum_type` di tralbum_details. L'API rifiuta
# esplicitamente "album" ("Expected tralbum_type as 'a' or 't'"): la mappa non è
# cosmesi, senza di lei la risoluzione fallisce sempre.
_TRALBUM_TYPES = {"album": "a", "track": "t", "a": "a", "t": "t"}


class BandcampSimilar:
    """I parenti di un disco su Bandcamp: risoluzione e archi.

    L'unico punto che conosce la forma dei payload Bandcamp per i simili. Condivide
    con `BandcampSource` i mapper da record grezzo a lead: la discografia e il
    discover hanno due forme diverse, ed è già `BandcampSource` a saperlo.
    """

    name = "bandcamp"

    def __init__(self, client):
        self.client = client
        self._source = BandcampSource(client)

    # --- resolve -------------------------------------------------------------

    def resolve(self, track) -> Any:
        from app.services.discovery_similar import Origin

        artist_raw = (getattr(track, "artist", None) or "").strip()
        if not artist_raw:
            return None
        artist, _keys = _clean_artist(artist_raw)
        if not artist:
            return None
        band = self.client.find_band(artist)
        if not band or not band.get("id"):
            return None
        band_id = int(band["id"])
        discography = self.client.band_discography(band_id)

        item = self._match_release(discography, track)
        if item is None:
            # Release non riconosciuta: si tiene l'artista e si prendono dai tag del
            # file quel che la release avrebbe dato. Dichiarato, non nascosto.
            return Origin(
                artist=artist, band_id=band_id, title=None, tralbum_id=None,
                tralbum_type=None,
                label=(getattr(track, "label", None) or "").strip() or None,
                label_id=None,
                tag=(_tag_norm(getattr(track, "genre", None) or "") or None),
                year=getattr(track, "year", None),
                source_url=None, resolution="artist_only", discography=discography,
            )

        tralbum_type = _TRALBUM_TYPES.get(str(item.get("item_type") or "a"), "a")
        detail = self.client.tralbum(
            band_id=int(item.get("band_id") or band_id),
            tralbum_id=int(item["item_id"]),
            tralbum_type=tralbum_type,
        )
        label_id = detail.get("label_id")
        return Origin(
            artist=artist, band_id=band_id,
            title=(item.get("title") or "").strip() or None,
            tralbum_id=int(item["item_id"]), tralbum_type=tralbum_type,
            label=(detail.get("label") or "").strip() or None,
            label_id=int(label_id) if label_id else None,
            tag=self._style_tag(detail, track),
            year=_bc_year_from_epoch(detail.get("release_date"))
                 or getattr(track, "year", None),
            source_url=(detail.get("bandcamp_url") or "").split("?")[0] or None,
            resolution="release", discography=discography,
        )

    def _match_release(self, discography: list[dict], track) -> dict | None:
        """La release della discografia che corrisponde alla traccia.

        La discografia elenca RELEASE, non brani: si prova prima l'album (match
        diretto) e poi il titolo (funziona quando il brano è uscito come single o EP
        omonimo). Aprire ogni release per cercarci dentro il brano costerebbe una
        richiesta a release: fuori scope.
        """
        from app.services.discovery_dig import _dedup_title

        wanted = [_norm(_dedup_title(v)) for v in
                  ((getattr(track, "album", None) or ""), (getattr(track, "title", None) or ""))
                  if (v or "").strip()]
        for want in wanted:
            for item in discography:
                if _norm(_dedup_title(item.get("title") or "")) == want:
                    return item
        return None

    def _style_tag(self, detail: dict, track) -> str | None:
        """Il primo tag utile della release: né di luogo né generico."""
        for tag in detail.get("tags") or []:
            if tag.get("isloc"):
                continue
            norm = (tag.get("norm_name") or "").strip().lower()
            if norm and norm not in GENERIC_TAGS:
                return norm
        return _tag_norm(getattr(track, "genre", None) or "") or None
```

Aggiungi `from typing import Any` agli import del file se non c'è già (c'è: il file lo importa già).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_discovery_similar.py -v`
Expected: PASS, 13 test.

- [ ] **Step 5: Verifica che i test non siano vacui**

1. In `_TRALBUM_TYPES`, cambia `"album": "a"` in `"album": "album"` → deve fallire `test_resolve_matches_the_release_by_album_and_reads_its_details`.
2. In `_style_tag`, togli il `continue` su `isloc` → deve fallire `test_resolve_skips_generic_and_location_tags_when_choosing_the_style_tag` (uscirebbe "bristol").
3. In `_match_release`, togli il titolo dalla lista `wanted` → deve fallire `test_resolve_matches_by_title_when_the_album_tag_is_missing`.
Ripristina dopo ogni prova.

- [ ] **Step 6: Commit**

```bash
git status --porcelain
git add backend/app/services/dig_sources/bandcamp.py backend/tests/test_discovery_similar.py
git commit -m "feat(discovery): BandcampSimilar riconosce la release d'origine"
```

---

### Task 3: La sorgente Bandcamp — espansione degli archi

**Files:**
- Modify: `backend/app/services/dig_sources/bandcamp.py` (dentro `BandcampSimilar`)
- Test: `backend/tests/test_discovery_similar.py`

**Interfaces:**
- Consumes: `Origin` da Task 1; `BandcampSimilar.resolve` da Task 2; dal client `discover(tag=, cursor=, size=)`.
- Produces: `BandcampSimilar.expand(origin, *, style_period) -> list[tuple[str, dict]]`, `BandcampSimilar.to_lead(edge, raw) -> DiscoveryLead | None`, costante `STYLE_EDGE_ITEMS = 120`.

- [ ] **Step 1: Write the failing test**

Aggiungi in fondo a `backend/tests/test_discovery_similar.py`:

```python
DISCOVER_ITEM_2026 = {
    "item_id": 900001, "item_type": "a", "title": "Vicino nel tempo",
    "item_url": "https://x.bandcamp.com/album/vicino", "band_id": 42,
    "album_artist": "Altro Artista", "band_name": "Una Label",
    "primary_image": {"image_id": 5}, "track_count": 4,
    "featured_track": {"stream_url": "https://t4.bcbits.com/stream/x"},
    "release_date": "2026-01-01 00:00:00 UTC",
}
DISCOVER_ITEM_2010 = {**DISCOVER_ITEM_2026, "item_id": 900002, "title": "Lontano",
                      "release_date": "2010-01-01 00:00:00 UTC"}

LABEL_ITEM = {**DISCOGRAPHY_ITEM, "item_id": 777, "title": "Un disco dell'etichetta",
              "artist_name": "Pearson Sound", "band_name": "Hessle Audio"}


class _FakeClientWithDiscover(_FakeClient):
    def __init__(self, discover_batch=None, **kw):
        super().__init__(**kw)
        self.discover_batch = discover_batch or []

    def discover(self, *, tag, cursor="*", size=500):
        self.calls.append(("discover", tag, cursor, size))
        return list(self.discover_batch), None, len(self.discover_batch)


def test_the_artist_edge_reuses_the_discography_and_excludes_the_origin_release():
    other = {**DISCOGRAPHY_ITEM, "item_id": 555, "title": "Un altro disco"}
    client = _FakeClientWithDiscover(
        band={"id": 637178087, "name": "Jasmín"},
        discographies={637178087: [DISCOGRAPHY_ITEM, other], 2788766970: []},
        tralbum=TRALBUM,
    )
    src = BandcampSimilar(client)
    origin = src.resolve(_track())
    before = len(client.calls)
    edges = src.expand(origin, style_period=False)
    titles = [raw["title"] for edge, raw in edges if edge == "same_artist"]
    assert titles == ["Un altro disco"]
    # L'arco artista non ricompra la discografia: solo la chiamata dell'etichetta.
    assert [c[0] for c in client.calls[before:]] == ["band_discography"]


def test_the_label_edge_walks_the_label_discography():
    client = _FakeClientWithDiscover(
        band={"id": 637178087, "name": "Jasmín"},
        discographies={637178087: [DISCOGRAPHY_ITEM], 2788766970: [LABEL_ITEM]},
        tralbum=TRALBUM,
    )
    src = BandcampSimilar(client)
    edges = src.expand(src.resolve(_track()), style_period=False)
    assert [raw["title"] for edge, raw in edges if edge == "same_label"] == \
        ["Un disco dell'etichetta"]


def test_a_self_released_origin_has_no_label_edge_and_costs_no_request():
    client = _FakeClientWithDiscover(
        band={"id": 637178087, "name": "Jasmín"},
        discographies={637178087: [DISCOGRAPHY_ITEM]},
        tralbum={**TRALBUM, "label_id": 637178087, "label": "Jasmín"},
    )
    src = BandcampSimilar(client)
    origin = src.resolve(_track())
    before = len(client.calls)
    edges = src.expand(origin, style_period=False)
    assert [e for e, _ in edges if e == "same_label"] == []
    assert client.calls[before:] == []


def test_the_style_edge_keeps_only_releases_inside_the_period_window():
    client = _FakeClientWithDiscover(
        discover_batch=[DISCOVER_ITEM_2026, DISCOVER_ITEM_2010],
        band={"id": 637178087, "name": "Jasmín"},
        discographies={637178087: [DISCOGRAPHY_ITEM], 2788766970: []},
        tralbum=TRALBUM,
    )
    src = BandcampSimilar(client)
    edges = src.expand(src.resolve(_track()), style_period=True)
    # origin.year = 2025, PERIOD_YEARS = 3 -> 2026 dentro, 2010 fuori.
    assert [raw["title"] for edge, raw in edges if edge == "same_period_style"] == \
        ["Vicino nel tempo"]
    assert any(c[0] == "discover" and c[1] == "bass" for c in client.calls)


def test_the_style_edge_costs_no_request_when_switched_off():
    client = _FakeClientWithDiscover(
        discover_batch=[DISCOVER_ITEM_2026],
        band={"id": 637178087, "name": "Jasmín"},
        discographies={637178087: [DISCOGRAPHY_ITEM], 2788766970: []},
        tralbum=TRALBUM,
    )
    src = BandcampSimilar(client)
    src.expand(src.resolve(_track()), style_period=False)
    assert not any(c[0] == "discover" for c in client.calls)


def test_each_edge_maps_with_the_shape_its_endpoint_returns():
    src, _ = _resolver()
    from_discography = src.to_lead("same_artist", DISCOGRAPHY_ITEM)
    assert from_discography.artist == "Jasmín"
    assert from_discography.source_id == "637178087:4024735967"
    from_discover = src.to_lead("same_period_style", DISCOVER_ITEM_2026)
    assert from_discover.artist == "Altro Artista"
    assert from_discover.stream_url == "https://t4.bcbits.com/stream/x"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_discovery_similar.py -v -k "edge or maps"`
Expected: FAIL con `AttributeError: 'BandcampSimilar' object has no attribute 'expand'`

- [ ] **Step 3: Write minimal implementation**

Aggiungi dentro `BandcampSimilar`, dopo `_style_tag`:

```python
    # --- expand --------------------------------------------------------------

    def expand(self, origin, *, style_period: bool) -> list[tuple[str, dict]]:
        out: list[tuple[str, dict]] = []
        out.extend(("same_artist", item) for item in self._artist_edge(origin))
        out.extend(("same_label", item) for item in self._label_edge(origin))
        if style_period:
            out.extend(("same_period_style", item) for item in self._style_edge(origin))
        return out

    def _artist_edge(self, origin) -> list[dict]:
        """Le altre release dell'artista. Zero richieste: la discografia è già in mano."""
        return [item for item in origin.discography
                if str(item.get("item_id")) != str(origin.tralbum_id)]

    def _label_edge(self, origin) -> list[dict]:
        """La discografia dell'etichetta.

        Autoprodotto (`label_id` assente o uguale alla band) non è un errore: è un
        arco che non esiste, e non deve costare una richiesta.
        """
        if origin.label_id and origin.label_id != origin.band_id:
            return self.client.band_discography(origin.label_id)
        if origin.resolution == "artist_only" and origin.label:
            band = self.client.find_band(origin.label)
            if band and band.get("id"):
                return self.client.band_discography(int(band["id"]))
        return []

    def _style_edge(self, origin) -> list[dict]:
        """Il discover del tag, ristretto alla finestra temporale dell'origine.

        Una sola batch: l'arco è un rinforzo, non un dig, e la finestra scarta già
        molto. Il filtro sull'anno è sul client perché il discover non lo offre.
        """
        from app.services.discovery_similar import PERIOD_YEARS

        if not origin.tag or origin.year is None:
            return []
        try:
            batch, _cursor, _total = self.client.discover(
                tag=origin.tag, cursor="*", size=STYLE_EDGE_ITEMS)
        except BandcampError:
            raise
        lo, hi = origin.year - PERIOD_YEARS, origin.year + PERIOD_YEARS
        out = []
        for item in batch or []:
            year = _bc_year(item.get("release_date"))
            if year is not None and lo <= year <= hi:
                out.append(item)
        return out

    # --- mapping -------------------------------------------------------------

    def to_lead(self, edge: str, raw: dict):
        """Due archi, due forme: discografia (artista, etichetta) vs discover (stile).

        I mapper sono quelli di `BandcampSource`: il seme che gli si passa serve solo
        a marcare il lead, e qui è il nome dell'arco.
        """
        seed = Seed(type="label" if edge != "same_period_style" else "genre", value=edge)
        return self._source.to_lead(raw, seed)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_discovery_similar.py -v`
Expected: PASS, 19 test.

- [ ] **Step 5: Verifica che i test non siano vacui**

1. In `_artist_edge`, togli il filtro sull'`item_id` → deve fallire `test_the_artist_edge_reuses_the_discography_and_excludes_the_origin_release`.
2. In `_label_edge`, togli `and origin.label_id != origin.band_id` → deve fallire `test_a_self_released_origin_has_no_label_edge_and_costs_no_request`.
3. In `_style_edge`, allarga la finestra a `lo, hi = 0, 9999` → deve fallire `test_the_style_edge_keeps_only_releases_inside_the_period_window`.
Ripristina dopo ogni prova.

- [ ] **Step 6: Commit**

```bash
git status --porcelain
git add backend/app/services/dig_sources/bandcamp.py backend/tests/test_discovery_similar.py
git commit -m "feat(discovery): gli archi artista, etichetta e stile su Bandcamp"
```

---

### Task 4: Schemi ed endpoint HTTP

**Files:**
- Modify: `backend/app/schemas.py` (dopo `DiscoveryGenresOut`)
- Modify: `backend/app/routers/discovery.py` (dopo `dig_endpoint`)
- Test: `backend/tests/test_discovery_router_http.py`

**Interfaces:**
- Consumes: `similar`, `SimilarResult`, `Origin`, `EdgeReport` da Task 1; `BandcampSimilar` da Task 2 e 3; `_lead_out` già nel router; `api_error` da `app.core.http_errors`.
- Produces: `GET /api/discovery/similar?track_id=&source=&style_period=`; schemi `OriginOut`, `EdgeReportOut`, `DiscoverySimilarResponse`.

- [ ] **Step 1: Write the failing test**

Aggiungi in fondo a `backend/tests/test_discovery_router_http.py` (adatta il nome del client di test e delle fixture a quelli già usati nel file):

```python
def test_similar_of_an_unknown_track_is_404(client):
    c, _S = client
    r = c.get("/api/discovery/similar", params={"track_id": 999999})
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "track_not_found"


def test_similar_refuses_a_source_that_is_not_bandcamp(client):
    c, S = client
    track_id = _one_track(S)
    r = c.get("/api/discovery/similar",
              params={"track_id": track_id, "source": "discogs"})
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "discovery_bad_source"


def test_similar_turns_a_provider_failure_into_502(client, monkeypatch):
    from app.integrations.bandcamp import BandcampError
    import app.routers.discovery as mod

    c, S = client
    track_id = _one_track(S)

    def boom(*a, **kw):
        raise BandcampError("Bandcamp giù")

    monkeypatch.setattr(mod, "similar", boom)
    r = c.get("/api/discovery/similar", params={"track_id": track_id})
    assert r.status_code == 502
    assert r.json()["detail"]["code"] == "discovery_provider_error"
```

La fixture `client` di questo file restituisce la coppia `(TestClient, sessionmaker)`;
l'helper che crea la traccia va accanto alle altre funzioni del modulo:

```python
def _one_track(S) -> int:
    """Una traccia posseduta nel DB del TestClient. Ritorna il suo id."""
    db = S()
    tr = Track(artist="Jasmín", title="Bite The Hand", source_type="local",
               has_local_file=True)
    db.add(tr)
    db.commit()
    track_id = tr.id
    db.close()
    return track_id
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_discovery_router_http.py -v -k similar`
Expected: FAIL, 404 su rotta inesistente (il `detail` non ha il codice atteso).

- [ ] **Step 3: Write minimal implementation**

In `backend/app/schemas.py`, dopo `DiscoveryGenresOut`:

```python
class OriginOut(BaseModel):
    """La release riconosciuta come punto di partenza dei simili."""

    artist: str
    title: str | None = None
    label: str | None = None
    year: int | None = None
    tag: str | None = None
    source_url: str | None = None
    # "release" = release riconosciuta; "artist_only" = solo l'artista, il resto
    # viene dai tag del file.
    resolution: str


class EdgeReportOut(BaseModel):
    """Quanti lead ha prodotto un arco, o perché non è stato percorso."""

    count: int | None = None
    # no_band | self_released | no_label | no_tag | no_year | off
    absent_reason: str | None = None


class DiscoverySimilarResponse(BaseModel):
    track_id: int
    source: str = "bandcamp"
    # null quando la sorgente non conosce l'artista: non c'è nessun punto di partenza.
    origin: OriginOut | None = None
    edges: dict[str, EdgeReportOut] = {}
    leads: list[DiscoveryLeadOut] = []
```

In `backend/app/routers/discovery.py`, aggiungi agli import:

```python
from app.schemas import (
    ...,
    DiscoverySimilarResponse,
    EdgeReportOut,
    OriginOut,
)
from app.services.dig_sources.bandcamp import BandcampSimilar
from app.services.discovery_similar import similar
```

e l'endpoint dopo `dig_endpoint`:

```python
@router.get("/similar", response_model=DiscoverySimilarResponse)
def similar_endpoint(
    track_id: int,
    source: str = "bandcamp",
    style_period: bool = False,
    db: Session = Depends(get_db),
):
    """I lead Bandcamp imparentati con una traccia posseduta."""
    if source != "bandcamp":
        raise api_error(400, "discovery_bad_source",
                        f"Sorgente non supportata dai simili: {source}")
    track = db.get(Track, track_id)
    if track is None:
        raise api_error(404, "track_not_found", f"Traccia {track_id} inesistente")

    client = BandcampClient()
    try:
        result = similar(db, track, source=BandcampSimilar(client),
                         style_period=style_period)
    except BandcampError as exc:
        # Come nel dig: "non c'è niente" e "il provider non ha risposto" devono
        # restare distinguibili dal chiamante.
        raise api_error(502, "discovery_provider_error", f"Discovery provider error: {exc}",
                        reason=str(exc)) from exc
    finally:
        client.close()

    origin = result.origin
    return DiscoverySimilarResponse(
        track_id=track_id, source=source,
        origin=OriginOut(
            artist=origin.artist, title=origin.title, label=origin.label,
            year=origin.year, tag=origin.tag, source_url=origin.source_url,
            resolution=origin.resolution,
        ) if origin else None,
        edges={k: EdgeReportOut(count=v.count, absent_reason=v.absent_reason)
               for k, v in result.edges.items()},
        leads=[_lead_out(lead) for lead in result.leads],
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_discovery_router_http.py tests/test_discovery_similar.py -v`
Expected: PASS.

- [ ] **Step 5: Run the whole backend suite**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests -q`
Expected: nessuna regressione. Se qualcosa si rompe negli import di `dig_sources`, controlla di non aver introdotto un ciclo: `discovery_similar` importa da `discovery_dig`, e `bandcamp.py` importa `Origin`/`PERIOD_YEARS` **dentro le funzioni**, non a livello di modulo.

- [ ] **Step 6: Commit**

```bash
git status --porcelain
git add backend/app/schemas.py backend/app/routers/discovery.py backend/tests/test_discovery_router_http.py
git commit -m "feat(api): GET /api/discovery/similar"
```

---

### Task 5: Tipi e client API frontend

**Files:**
- Modify: `frontend/lib/api/types.ts` (dopo `DiscoveryDigResponse`)
- Modify: `frontend/lib/api/discovery.ts`
- Modify: `frontend/lib/discovery-dig.ts`
- Test: `frontend/tests/discovery-similar-href.test.ts`

**Interfaces:**
- Consumes: la risposta di Task 4.
- Produces: `SimilarOrigin`, `SimilarEdge`, `DiscoverySimilarResponse`, `discoverySimilar(trackId, opts?)`, `similarHref(trackId, stylePeriod)`.

- [ ] **Step 1: Write the types**

In `frontend/lib/api/types.ts`, dopo `DiscoveryDigResponse`:

```ts
export interface SimilarOrigin {
  artist: string;
  title: string | null;
  label: string | null;
  year: number | null;
  tag: string | null;
  source_url: string | null;
  /** "release" = release riconosciuta; "artist_only" = solo artista, resto dai tag. */
  resolution: "release" | "artist_only";
}

export interface SimilarEdge {
  /** Lead prodotti. `null` quando l'arco non è stato percorso. */
  count: number | null;
  absent_reason:
    | "no_band" | "self_released" | "no_label" | "no_tag" | "no_year" | "off" | null;
}

export interface DiscoverySimilarResponse {
  track_id: number;
  source: string;
  /** `null` quando Bandcamp non conosce l'artista: nessun punto di partenza. */
  origin: SimilarOrigin | null;
  edges: Record<string, SimilarEdge>;
  leads: DiscoveryLead[];
}
```

- [ ] **Step 2: Write the client function**

In `frontend/lib/api/discovery.ts`, aggiungi `DiscoverySimilarResponse` agli import di tipo e in fondo:

```ts
export function discoverySimilar(
  trackId: number,
  opts?: { stylePeriod?: boolean },
) {
  return apiGet<DiscoverySimilarResponse>("/api/discovery/similar", {
    track_id: trackId,
    style_period: opts?.stylePeriod ? "true" : "false",
  });
}
```

- [ ] **Step 3: Aggiungi la funzione pura che costruisce l'URL**

L'URL della modalità simili lo scrivono tre punti (il bottone nel dettaglio traccia,
l'interruttore, il rilancio): una sola funzione pura, come `applyLens` e
`pickSurprise`, così è testabile senza montare la pagina e non può divergere.

In `frontend/lib/discovery-dig.ts`, in fondo:

```ts
/** L'URL della modalità simili. Unica fonte per bottone, interruttore e rilancio. */
export function similarHref(trackId: number, stylePeriod: boolean): string {
  const params = new URLSearchParams();
  params.set("similar", String(trackId));
  params.set("style_period", stylePeriod ? "1" : "0");
  return `/discovery?${params.toString()}`;
}
```

- [ ] **Step 4: Write the test**

Crea `frontend/tests/discovery-similar-href.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { similarHref } from "@/lib/discovery-dig";

describe("similarHref", () => {
  it("porta l'id della traccia e l'interruttore spento", () => {
    expect(similarHref(42, false)).toBe("/discovery?similar=42&style_period=0");
  });

  it("accende l'interruttore nell'URL", () => {
    expect(similarHref(42, true)).toBe("/discovery?similar=42&style_period=1");
  });
});
```

Run: `cd frontend && npm run test:unit -- discovery-similar-href`
Expected: PASS, 2 test. Poi prova la non-vacuità: cambia `"1" : "0"` in `"1" : "1"` →
deve fallire il primo test.

- [ ] **Step 5: Verify it compiles**

Run: `cd frontend && npm run lint`
Expected: nessun errore.

- [ ] **Step 6: Commit**

```bash
git status --porcelain
git add frontend/lib/api/types.ts frontend/lib/api/discovery.ts frontend/lib/discovery-dig.ts frontend/tests/discovery-similar-href.test.ts
git commit -m "feat(frontend): tipi, client e URL dei simili"
```

---

### Task 6: Testi nei due dizionari

**Files:**
- Modify: `frontend/lib/i18n/it.ts` (dentro `discovery: {`)
- Modify: `frontend/lib/i18n/en.ts` (stessa posizione)

**Interfaces:**
- Produces: le chiavi `t.discovery.similar*` usate dalle Task 7, 8 e 9; `t.tracks.similar` usata dalla Task 9.

- [ ] **Step 1: Aggiungi le chiavi italiane**

In `frontend/lib/i18n/it.ts`, dentro l'oggetto `discovery`, dopo `readyBodyNotReady`:

```ts
    similarFrom: "Partendo da",
    similarIntro: "I parenti di questo disco su Bandcamp, che non hai già.",
    similarBackToTrack: "Torna alla traccia",
    similarResolvedRelease: "Release riconosciuta su Bandcamp",
    similarArtistOnly: "Release non riconosciuta su Bandcamp: uso i tag del file.",
    similarStylePeriod: "Stile e periodo",
    similarEdgeArtist: "Artista",
    similarEdgeLabel: "Etichetta",
    similarEdgeStyle: "Stile e periodo",
    similarAbsentNoBand: "Nessuna pagina Bandcamp per questo artista",
    similarAbsentSelfReleased: "Autoprodotto: nessuna etichetta da seguire",
    similarAbsentNoLabel: "Nessuna etichetta nei tag del file",
    similarAbsentNoTag: "Nessun tag di stile utilizzabile",
    similarAbsentNoYear: "Anno sconosciuto: non c'è un periodo da confrontare",
    similarAbsentOff: "Disattivato",
    similarNoBandTitle: (artist: string) => `Nessuna pagina Bandcamp per ${artist}`,
    similarNoBandBody:
      "I simili partono dall'artista su Bandcamp. Senza una sua pagina non c'è nessun disco da collegare: capita col catalogo major e col materiale solo vinile.",
    similarAllOwnedTitle: "Possiedi già tutto",
    similarAllOwnedBody: (artist: string) =>
      `Hai già tutto ciò che Bandcamp collega a ${artist}.`,
    similarAllOwnedHint: "Prova ad accendere “Stile e periodo” per allargare.",
    similarInProgress: "Cerco i simili…",
    similarJob: "Simili",
    reasonSameArtist: "stesso artista",
    reasonSameLabel: (label: string) => `stessa etichetta: ${label}`,
    reasonSamePeriodStyle: (tag: string, from: string | number, to: string | number) =>
      `${tag}, ${from}–${to}`,
```

- [ ] **Step 2: Aggiungi le stesse chiavi in inglese**

In `frontend/lib/i18n/en.ts`, stessa posizione:

```ts
    similarFrom: "Starting from",
    similarIntro: "This record's relatives on Bandcamp, minus what you own.",
    similarBackToTrack: "Back to the track",
    similarResolvedRelease: "Release matched on Bandcamp",
    similarArtistOnly: "Release not matched on Bandcamp: using the file's tags.",
    similarStylePeriod: "Style and period",
    similarEdgeArtist: "Artist",
    similarEdgeLabel: "Label",
    similarEdgeStyle: "Style and period",
    similarAbsentNoBand: "No Bandcamp page for this artist",
    similarAbsentSelfReleased: "Self-released: no label to follow",
    similarAbsentNoLabel: "No label in the file's tags",
    similarAbsentNoTag: "No usable style tag",
    similarAbsentNoYear: "Unknown year: no period to compare",
    similarAbsentOff: "Switched off",
    similarNoBandTitle: (artist: string) => `No Bandcamp page for ${artist}`,
    similarNoBandBody:
      "Similar records start from the artist on Bandcamp. Without a page there is nothing to connect: this happens with major-label catalogue and vinyl-only material.",
    similarAllOwnedTitle: "You own it all",
    similarAllOwnedBody: (artist: string) =>
      `You already own everything Bandcamp connects to ${artist}.`,
    similarAllOwnedHint: "Try switching “Style and period” on to widen the net.",
    similarInProgress: "Looking for similar records…",
    similarJob: "Similar",
    reasonSameArtist: "same artist",
    reasonSameLabel: (label: string) => `same label: ${label}`,
    reasonSamePeriodStyle: (tag: string, from: string | number, to: string | number) =>
      `${tag}, ${from}–${to}`,
```

- [ ] **Step 3: Aggiungi la chiave del bottone nel gruppo `tracks`**

In entrambi i file, dentro l'oggetto `tracks`, accanto a `editValues`:

```ts
    similar: "Simili",   // it.ts
    similar: "Similar",  // en.ts
```

- [ ] **Step 4: Verify it compiles**

Run: `cd frontend && npm run lint`
Expected: nessun errore. Se il dizionario inglese è tipizzato sul `Dictionary` derivato dall'italiano, i due devono avere esattamente le stesse chiavi.

- [ ] **Step 5: Commit**

```bash
git status --porcelain
git add frontend/lib/i18n/it.ts frontend/lib/i18n/en.ts
git commit -m "feat(i18n): i testi dei simili in italiano e inglese"
```

---

### Task 7: L'intestazione "Partendo da"

**Files:**
- Create: `frontend/components/discovery-similar-header.tsx`
- Test: `frontend/tests/discovery-similar-header.test.tsx`

**Interfaces:**
- Consumes: `DiscoverySimilarResponse`, `SimilarEdge` da Task 5; le chiavi `t.discovery.similar*` da Task 6.
- Produces: `DiscoverySimilarHeader({ data, track, stylePeriod, onStylePeriodChange, busy })`.

- [ ] **Step 1: Write the failing test**

Crea `frontend/tests/discovery-similar-header.test.tsx`:

```tsx
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { DiscoverySimilarHeader } from "@/components/discovery-similar-header";
import type { DiscoverySimilarResponse } from "@/lib/api/types";

const TRACK = { id: 1, artist: "Jasmín", title: "Bite The Hand",
                album_art_url: null } as never;

function data(over: Partial<DiscoverySimilarResponse> = {}): DiscoverySimilarResponse {
  return {
    track_id: 1,
    source: "bandcamp",
    origin: {
      artist: "Jasmín", title: "Bite The Hand That Feeds You",
      label: "Hessle Audio", year: 2025, tag: "bass",
      source_url: "https://x.bandcamp.com/album/y", resolution: "release",
    },
    edges: {
      same_artist: { count: 4, absent_reason: null },
      same_label: { count: 31, absent_reason: null },
      same_period_style: { count: null, absent_reason: "off" },
    },
    leads: [],
    ...over,
  };
}

describe("DiscoverySimilarHeader", () => {
  it("mostra la release riconosciuta con etichetta e anno", () => {
    render(<DiscoverySimilarHeader data={data()} track={TRACK} stylePeriod={false}
                                   onStylePeriodChange={() => {}} busy={false} />);
    expect(screen.getByText(/Bite The Hand That Feeds You/)).toBeInTheDocument();
    expect(screen.getByText(/Hessle Audio/)).toBeInTheDocument();
    expect(screen.getByText(/2025/)).toBeInTheDocument();
  });

  it("dice quando la release non è stata riconosciuta", () => {
    render(<DiscoverySimilarHeader
      data={data({ origin: { ...data().origin!, resolution: "artist_only", title: null } })}
      track={TRACK} stylePeriod={false} onStylePeriodChange={() => {}} busy={false} />);
    expect(screen.getByText(/Release non riconosciuta/)).toBeInTheDocument();
  });

  it("mostra il conteggio degli archi percorsi", () => {
    render(<DiscoverySimilarHeader data={data()} track={TRACK} stylePeriod={false}
                                   onStylePeriodChange={() => {}} busy={false} />);
    expect(screen.getByText(/Artista/)).toHaveTextContent("4");
    expect(screen.getByText(/Etichetta/)).toHaveTextContent("31");
  });

  it("un arco assente porta il motivo, non un conteggio a zero", () => {
    render(<DiscoverySimilarHeader
      data={data({ edges: { ...data().edges,
        same_label: { count: null, absent_reason: "self_released" } } })}
      track={TRACK} stylePeriod={false} onStylePeriodChange={() => {}} busy={false} />);
    const chip = screen.getByText(/Etichetta/);
    expect(chip).not.toHaveTextContent("0");
    expect(chip).toHaveAttribute("title", expect.stringContaining("Autoprodotto"));
  });

  it("l'interruttore stile e periodo avvisa il chiamante", async () => {
    const onChange = vi.fn();
    render(<DiscoverySimilarHeader data={data()} track={TRACK} stylePeriod={false}
                                   onStylePeriodChange={onChange} busy={false} />);
    await userEvent.click(screen.getByLabelText(/Stile e periodo/));
    expect(onChange).toHaveBeenCalledWith(true);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm run test:unit -- discovery-similar-header`
Expected: FAIL, modulo non trovato.

- [ ] **Step 3: Write minimal implementation**

Crea `frontend/components/discovery-similar-header.tsx`:

```tsx
"use client";

import Link from "next/link";
import { ArrowLeft, ExternalLink } from "lucide-react";

import { Checkbox, Chip } from "@/components/ui";
import { useT, type Dictionary } from "@/lib/i18n";
import type { DiscoverySimilarResponse, SimilarEdge, Track } from "@/lib/api/types";
import { cn } from "@/lib/cn";

function absentLabel(reason: SimilarEdge["absent_reason"], t: Dictionary): string {
  switch (reason) {
    case "no_band": return t.discovery.similarAbsentNoBand;
    case "self_released": return t.discovery.similarAbsentSelfReleased;
    case "no_label": return t.discovery.similarAbsentNoLabel;
    case "no_tag": return t.discovery.similarAbsentNoTag;
    case "no_year": return t.discovery.similarAbsentNoYear;
    case "off": return t.discovery.similarAbsentOff;
    default: return "";
  }
}

function EdgeChip({ label, edge, t }: { label: string; edge?: SimilarEdge; t: Dictionary }) {
  // Arco assente: NON si mostra "0". Zero vuol dire "ho guardato e non c'era
  // niente"; assente vuol dire "non ho potuto guardare", e sono due fatti diversi.
  const absent = !edge || edge.count === null;
  return (
    <span
      title={absent ? absentLabel(edge?.absent_reason ?? null, t) : undefined}
      className={cn(
        "border border-border px-1.5 py-0.5 text-[10px] uppercase tracking-wider",
        absent ? "text-faint line-through" : "text-muted",
      )}
    >
      {label}{absent ? "" : ` ${edge!.count}`}
    </span>
  );
}

export function DiscoverySimilarHeader({
  data, track, stylePeriod, onStylePeriodChange, busy,
}: {
  data: DiscoverySimilarResponse;
  track: Track;
  stylePeriod: boolean;
  onStylePeriodChange: (v: boolean) => void;
  busy: boolean;
}) {
  const t = useT();
  const origin = data.origin;

  return (
    <div className="mb-6 border border-border p-4">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="text-[10px] uppercase tracking-wider text-muted">
            {t.discovery.similarFrom}
          </div>
          <div className="mt-1 truncate text-sm text-fg">
            {track.artist} — {track.title}
          </div>
          {origin && origin.resolution === "release" ? (
            <div className="mt-1 text-xs text-faint">
              <span className="truncate">{origin.title}</span>
              {origin.label && <span> · {origin.label}</span>}
              {origin.year != null && <span> · {origin.year}</span>}
              {origin.source_url && (
                <a href={origin.source_url} target="_blank" rel="noreferrer"
                   className="ml-2 inline-flex items-center gap-1 text-fg hover:underline">
                  <ExternalLink size={12} /> Bandcamp
                </a>
              )}
            </div>
          ) : origin ? (
            <div className="mt-1 text-xs text-faint">{t.discovery.similarArtistOnly}</div>
          ) : null}
          <Link href={`/tracks?id=${track.id}`}
                className="mt-2 inline-flex items-center gap-1.5 text-xs text-muted hover:text-fg">
            <ArrowLeft size={13} /> {t.discovery.similarBackToTrack}
          </Link>
        </div>

        <div className="flex flex-col items-end gap-2">
          <label className="flex items-center gap-2 text-xs text-muted">
            <Checkbox
              checked={stylePeriod}
              onChange={() => onStylePeriodChange(!stylePeriod)}
              disabled={busy}
              aria-label={t.discovery.similarStylePeriod}
            />
            {t.discovery.similarStylePeriod}
          </label>
          <div className="flex flex-wrap gap-1.5">
            <EdgeChip label={t.discovery.similarEdgeArtist} edge={data.edges.same_artist} t={t} />
            <EdgeChip label={t.discovery.similarEdgeLabel} edge={data.edges.same_label} t={t} />
            <EdgeChip label={t.discovery.similarEdgeStyle} edge={data.edges.same_period_style} t={t} />
          </div>
        </div>
      </div>
    </div>
  );
}
```

Se `Checkbox` in `components/ui` ha una firma diversa (per esempio `onCheckedChange`), adattala e tieni l'`aria-label`: il test lo usa per trovare l'interruttore. Se `Chip` non serve, togli l'import.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npm run test:unit -- discovery-similar-header`
Expected: PASS, 5 test.

- [ ] **Step 5: Verifica che i test non siano vacui**

1. In `EdgeChip`, cambia `absent` in `const absent = false` → devono fallire il test dell'arco assente (mostrerebbe `null`).
2. Togli il ramo `origin.resolution === "release"` e lascia solo il ramo `artist_only` → deve fallire il primo test.
Ripristina dopo ogni prova.

- [ ] **Step 6: Commit**

```bash
git status --porcelain
git add frontend/components/discovery-similar-header.tsx frontend/tests/discovery-similar-header.test.tsx
git commit -m "feat(discovery): l'intestazione Partendo da"
```

---

### Task 8: Griglia generalizzata e modalità simili nella pagina

**Files:**
- Modify: `frontend/components/discovery-lead-grid.tsx:52-95`
- Modify: `frontend/app/discovery/page.tsx`
- Test: `frontend/tests/discovery-lead-grid.test.tsx`

**Interfaces:**
- Consumes: `DiscoverySimilarHeader` da Task 7; `discoverySimilar` da Task 5; i testi da Task 6.
- Produces: `DiscoveryLeadGrid({ source, leads, empty })` con `empty?: ReactNode`; il ramo `similar` della pagina Discovery.

- [ ] **Step 1: Write the failing test**

Crea `frontend/tests/discovery-lead-grid.test.tsx`:

```tsx
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import { DiscoveryLeadGrid } from "@/components/discovery-lead-grid";
import type { DiscoveryLead } from "@/lib/api/types";

const LEAD: DiscoveryLead = {
  artist: "Pearson Sound", title: "Which Way Is Up", year: 2024,
  label: "Hessle Audio", style: null, source: "bandcamp", seed: "same_label",
  source_id: "1:2", source_url: null, stream_url: null, thumb_url: null,
  have: 0, want: 0, reasons: [{ code: "same_label", data: { label: "Hessle Audio" } }],
  format_badge: "EP",
};

describe("DiscoveryLeadGrid", () => {
  it("rende i lead che riceve", () => {
    render(<DiscoveryLeadGrid source="bandcamp" leads={[LEAD]}
                              empty={<p>niente</p>} />);
    expect(screen.getByText("Which Way Is Up")).toBeInTheDocument();
    expect(screen.getByText("Pearson Sound")).toBeInTheDocument();
  });

  it("mostra lo stato vuoto che il chiamante le passa, senza inventarne uno", () => {
    render(<DiscoveryLeadGrid source="bandcamp" leads={[]}
                              empty={<p>stato vuoto del chiamante</p>} />);
    expect(screen.getByText("stato vuoto del chiamante")).toBeInTheDocument();
  });

  it("il reason della stessa etichetta nomina l'etichetta", () => {
    render(<DiscoveryLeadGrid source="bandcamp" leads={[LEAD]} empty={null} />);
    expect(screen.getByText(/Hessle Audio/)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm run test:unit -- discovery-lead-grid`
Expected: FAIL: il componente pretende ancora la prop `dig`.

- [ ] **Step 3: Generalizza la griglia**

In `frontend/components/discovery-lead-grid.tsx`:

1. Cambia la firma e togli gli stati vuoti interni:

```tsx
export function DiscoveryLeadGrid({ source, leads, empty }: {
  /** Sorgente di QUESTI lead, non quella selezionata ora: le stringhe che la
   *  nominano non devono mentire su un risultato che viene da una ricerca precedente. */
  source: string;
  /** La lista GIÀ passata dalla lente (formato+ordinamento+taglio, nel chiamante). */
  leads: DiscoveryLead[];
  /** Lo stato vuoto è del chiamante: dig e simili hanno cause diverse da spiegare. */
  empty: React.ReactNode;
}) {
  const [openLead, setOpenLead] = useState<DiscoveryLead | null>(null);

  return (
    <div>
      {leads.length === 0 ? empty : (
        <div className="grid grid-cols-[repeat(auto-fill,minmax(120px,1fr))] gap-3">
          {leads.map((l, i) => (
            <LeadCell key={`${l.source_id ?? l.artist}-${l.title}-${i}`} lead={l}
                      onOpen={() => setOpenLead(l)} />
          ))}
        </div>
      )}
      <DiscoveryTracklistPanel lead={openLead} onClose={() => setOpenLead(null)} />
    </div>
  );
}
```

`srcName` e i tre `EmptyState` interni spariscono da qui: il dig li ricostruisce nella sua pagina (passo 4).

2. Aggiungi i tre reason nuovi in `reasonLabel`:

```tsx
    case "same_artist":
      return t.discovery.reasonSameArtist;
    case "same_label":
      return t.discovery.reasonSameLabel(String(r.data.label ?? ""));
    case "same_period_style":
      return t.discovery.reasonSamePeriodStyle(
        String(r.data.tag ?? ""), r.data.year_from ?? "", r.data.year_to ?? "");
```

3. `import { EmptyState } from "@/components/ui"` non serve più qui: toglilo se resta inutilizzato, e togli `WINDOW_ITEMS` se non è più usato.

- [ ] **Step 4: Sposta gli stati vuoti del dig nella pagina**

In `frontend/app/discovery/page.tsx`, aggiungi una funzione che ricostruisce i due stati vuoti del dig e passala alla griglia:

```tsx
  const digEmpty = (d: DiscoveryDigResponse) => {
    const srcName = d.source === "bandcamp" ? t.discovery.sourceBandcamp : t.discovery.sourceDiscogs;
    // Zero lead ha due cause diverse, e dirle uguali mente: pila inesistente (seme
    // sconosciuto alla sorgente) contro pila esistente ma tutta già posseduta.
    if (d.pile_total === 0) {
      return (
        <EmptyState icon={<Disc3 size={28} />} title={t.discovery.deadSeedTitle(srcName)}>
          {t.discovery.deadSeedBody(d.value, srcName)}
        </EmptyState>
      );
    }
    if (d.leads.length === 0) {
      const shortPile = d.pile_reach <= WINDOW_ITEMS;
      return (
        <EmptyState icon={<Disc3 size={28} />} title={t.discovery.nothingToDigTitle}>
          {shortPile
            ? t.discovery.nothingToDigShortPile(d.value)
            : t.discovery.nothingToDigBody(d.value,
                d.seed_type === "label" ? t.discovery.seedTypeValue : t.discovery.seedTypeStyle)}
        </EmptyState>
      );
    }
    return <p className="py-8 text-center text-sm text-muted">{t.discovery.noFormatMatch}</p>;
  };
```

e cambia la chiamata:

```tsx
      {dig && <DiscoveryLeadGrid source={dig.source} leads={visible} empty={digEmpty(dig)} />}
```

Importa `WINDOW_ITEMS` e `similarHref` da `@/lib/discovery-dig` nella pagina se non ci sono già.

- [ ] **Step 5: Aggiungi il ramo modalità simili alla pagina**

Sempre in `frontend/app/discovery/page.tsx`, dentro `DiscoveryInner`:

```tsx
  const similarId = Number(searchParams.get("similar") ?? "");
  const isSimilar = Number.isFinite(similarId) && similarId > 0;
  const stylePeriod = searchParams.get("style_period") === "1";
  const [sim, setSim] = useState<DiscoverySimilarResponse | null>(null);
  const [simTrack, setSimTrack] = useState<Track | null>(null);
```

Un effect che risponde ai parametri dell'URL, con la stessa forma di quello del dig:

```tsx
  useEffect(() => {
    if (!isSimilar) return;
    setBusy(true);
    setError(null);
    setSim(null);
    jobs.startClientJob("dig", t.discovery.similarJob);
    Promise.all([
      discoverySimilar(similarId, { stylePeriod }),
      apiGet<Track>(`/api/tracks/${similarId}`),
    ])
      .then(([data, track]) => {
        setSim(data);
        setSimTrack(track);
        jobs.updateClientJob("dig", { detail: `${track.artist} — ${track.title}` });
      })
      .catch((e) => setError(errText(e)))
      .finally(() => {
        setBusy(false);
        jobs.endClientJob("dig");
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [paramsKey]);
```

L'interruttore riscrive l'URL, come fanno già i parametri del dig:

```tsx
  const setStylePeriod = (on: boolean) => {
    // `similarHref` è la stessa funzione che scrive il bottone nel dettaglio traccia:
    // un solo posto costruisce questo URL.
    router.push(similarHref(similarId, on), { scroll: false });
  };
```

La lente vale per entrambe le modalità:

```tsx
  const activeLeads = isSimilar ? (sim?.leads ?? []) : (dig?.leads ?? []);
  const { visible, total } = useMemo(
    () => applyLens(activeLeads, { format, sort, show }),
    [activeLeads, format, sort, show],
  );
```

Lo stato vuoto dei simili, con le sue tre cause:

```tsx
  const similarEmpty = (d: DiscoverySimilarResponse) => {
    if (!d.origin) {
      return (
        <EmptyState icon={<Disc3 size={28} />}
                    title={t.discovery.similarNoBandTitle(simTrack?.artist ?? "")}>
          {t.discovery.similarNoBandBody}
        </EmptyState>
      );
    }
    if (d.leads.length === 0) {
      return (
        <EmptyState icon={<Disc3 size={28} />} title={t.discovery.similarAllOwnedTitle}>
          {t.discovery.similarAllOwnedBody(d.origin.artist)}
          {!stylePeriod && ` ${t.discovery.similarAllOwnedHint}`}
        </EmptyState>
      );
    }
    return <p className="py-8 text-center text-sm text-muted">{t.discovery.noFormatMatch}</p>;
  };
```

Nel JSX: la barra dello scavo solo fuori dalla modalità simili, l'intestazione solo dentro.

```tsx
      {!isSimilar && <DiscoveryDigBar ... />}
      {isSimilar && sim && simTrack && (
        <DiscoverySimilarHeader data={sim} track={simTrack} stylePeriod={stylePeriod}
                                onStylePeriodChange={setStylePeriod} busy={busy} />
      )}
```

La riga delle lenti va mostrata quando c'è un risultato in una delle due modalità (`dig || sim`); il blocco `broadSeed` resta condizionato a `dig &&`, perché i simili non hanno una pila. Il titolo della pagina in modalità simili resta "Dig"; `t.discovery.intro` diventa `t.discovery.similarIntro`.

Infine la griglia:

```tsx
      {isSimilar
        ? sim && <DiscoveryLeadGrid source={sim.source} leads={visible} empty={similarEmpty(sim)} />
        : dig && <DiscoveryLeadGrid source={dig.source} leads={visible} empty={digEmpty(dig)} />}
```

L'effect del dig esistente va protetto: `if (isSimilar) return;` come prima riga, altrimenti in modalità simili tenta un dig col valore vuoto.

- [ ] **Step 6: Run tests**

Run: `cd frontend && npm run test:unit -- discovery`
Expected: PASS, inclusi i test esistenti `discovery-lens` e `discovery-dig-bar`.

Run: `cd frontend && npm run lint`
Expected: nessun errore.

- [ ] **Step 7: Commit**

```bash
git status --porcelain
git add frontend/components/discovery-lead-grid.tsx frontend/app/discovery/page.tsx frontend/tests/discovery-lead-grid.test.tsx
git commit -m "feat(discovery): la pagina serve anche la modalità simili"
```

---

### Task 9: Il bottone "Simili" nel dettaglio traccia

**Files:**
- Modify: `frontend/app/tracks/page.tsx:168`

**Interfaces:**
- Consumes: `t.tracks.similar` da Task 6; `similarHref` da Task 5; il ramo `similar` della pagina da Task 8.

- [ ] **Step 1: Aggiungi il bottone**

In `frontend/app/tracks/page.tsx`, subito dopo il bottone "Modifica valori" (riga 168), dentro lo stesso `div`:

```tsx
        {track.has_local_file && (
          <ButtonLink href={similarHref(track.id, false)} size="sm" variant="outline">
            <Sparkles size={14} /> {t.tracks.similar}
          </ButtonLink>
        )}
```

Aggiungi `Sparkles` agli import di `lucide-react`, `ButtonLink` da `@/components/button-link` e `similarHref` da `@/lib/discovery-dig`. Se `ButtonLink` non accetta `size`/`variant`, usa `<Link>` che avvolge un `<Button>` come fa il resto della pagina alle righe 189 e 192.

Il bottone è condizionato a `has_local_file`: i simili partono da un disco che possiedi, e offrirli su un lead della wishlist prometterebbe qualcosa che il backend non nega ma che non è il gesto pensato.

- [ ] **Step 2: Verify**

Run: `cd frontend && npm run lint && npm run test:unit`
Expected: nessun errore, suite verde.

- [ ] **Step 3: Verifica nel browser**

Avvia la preview del progetto (`preview_start` con la configurazione del dev server), apri il dettaglio di una traccia con file locale, premi "Simili" e controlla: l'intestazione mostra la release riconosciuta, i chip riportano i conteggi, l'interruttore rilancia la ricerca e cambia l'URL, le card suonano l'anteprima. Controlla la console e i log del server per errori.

- [ ] **Step 4: Commit**

```bash
git status --porcelain
git add frontend/app/tracks/page.tsx
git commit -m "feat(tracks): il bottone Simili sul dettaglio traccia"
```

---

### Task 10: Documentazione

**Files:**
- Modify: `docs/API.md` (sezione Discovery, dopo "Acquiring")
- Modify: `docs/ROADMAP.md:41-48` (la voce Discovery)
- Modify: `PROGRESS.md`

- [ ] **Step 1: Documenta l'endpoint**

In `docs/API.md`, nella sezione Discovery, aggiungi `GET /api/discovery/similar` al blocco degli endpoint in cima e questa sottosezione dopo "Acquiring":

```markdown
### Similar

`GET /api/discovery/similar?track_id=&source=&style_period=` returns the Bandcamp
leads related to a track you own — the digger's move "this one I like, give me its
relatives" — filtered against the whole library like the dig.

`source` accepts only `bandcamp` (`400 discovery_bad_source` otherwise): Discogs is a
map, not the shop this user buys from, and Bandcamp leads carry a real per-track
stream instead of an iTunes clip. An unknown `track_id` is `404 track_not_found`; a
provider failure is `502 discovery_provider_error`, never a silent empty list.

Resolution runs in three steps and degrades **explicitly**: band search on the cleaned
artist, then a match of the track's album (or title) against that band's discography,
then the release detail for label, tags and year. `origin.resolution` is `release`
when the release was matched and `artist_only` when it was not — in which case label,
style tag and year come from the file's own tags. `origin` is `null` when Bandcamp
does not know the artist at all: there is no starting point, and no fallback is
attempted.

Three edges produce the leads, and each one that reached a lead leaves a `Reason` on
it: `same_artist` (the rest of that discography, no extra request), `same_label` (the
label's discography, absent when the release is self-released), and
`same_period_style` (a `discover` on the release's first non-generic, non-location
tag, kept to `±3` years around the origin) which runs only with `style_period=true`.
`edges` reports each one as either a `count` — how many leads it produced after
dedup, `0` included — or an `absent_reason` (`no_band`, `self_released`, `no_label`,
`no_tag`, `no_year`, `off`). The two are never both set: "I looked and found nothing"
and "I could not look" are different facts, and the UI says which.

Leads are `DiscoveryLeadOut` exactly as the dig returns them, so preview, tracklist,
add and download work unchanged. Ranking is the dig's own: taste profile over the
whole library, per-artist cap, no demand signal (Bandcamp has none). Expect 4-6
Bandcamp requests per call; nothing is cached.
```

- [ ] **Step 2: Aggiorna la roadmap**

In `docs/ROADMAP.md`, alla voce Discovery, aggiungi in coda al paragrafo:

```markdown
  From a track you own, **"Similar"** (`/discovery?similar=<track_id>`) digs the
  graph around it on Bandcamp instead of a genre seed: the rest of the artist's
  discography, the label's, and — behind a switch — the same style within ±3 years.
  Resolution degrades explicitly (`release` → `artist_only` → no origin at all) and
  each edge reports its lead count or why it was not walked.
```

- [ ] **Step 3: Aggiorna PROGRESS.md**

Aggiungi una voce in cima alla sezione corrente, nello stile delle voci esistenti:

```markdown
- **Discovery "Simili" (2026-09-06).** Dal dettaglio di una traccia posseduta si
  arriva ai suoi parenti su Bandcamp: stessa discografia, stessa etichetta, e con un
  interruttore lo stesso stile nel periodo. Riusa dedup, gusto e griglia del dig; gli
  archi non percorsi dicono perché invece di mostrare uno zero.
```

- [ ] **Step 4: Commit**

```bash
git status --porcelain
git add docs/API.md docs/ROADMAP.md PROGRESS.md
git commit -m "docs: l'endpoint e la modalità Simili di Discovery"
```

---

## Verifica finale

- [ ] `cd backend && source .venv/bin/activate && python -m pytest tests -q` — suite verde
- [ ] `cd frontend && npm run test:unit` — suite verde
- [ ] `cd frontend && npm run lint` — pulito
- [ ] `cd frontend && npm run build` — compila
- [ ] Prova manuale nel browser: una traccia con release riconosciuta, una con `artist_only` (album assente dai tag), una con artista non su Bandcamp. I tre stati vuoti devono essere distinguibili.
