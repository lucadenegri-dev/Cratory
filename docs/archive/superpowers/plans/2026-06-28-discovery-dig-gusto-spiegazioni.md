# Discovery dig — segnali di gusto + spiegazioni — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Arricchire il flusso Discovery "dig" (Discogs) con segnali di gusto deterministici e spiegazioni a chip, rispetto a un riferimento di gusto selezionabile (libreria intera o una playlist).

**Architecture:** Tutto deterministico nel servizio `discovery_dig.py`. Si introduce un `TasteProfile` costruito da una lista di `Track` (libreria o playlist), si estende lo scoring con familiarità graduata + affinità etichetta + affinità stile, e si emettono `Reason` (codice + payload) per ogni lead. Dedup sempre library-wide; affinità sul profilo scelto. Schema/router espongono `taste_playlist_id` e `reasons`; la UI rende i chip.

**Tech Stack:** Python 3 + FastAPI + Pydantic + SQLAlchemy (backend), pytest; Next.js 16 + React + TypeScript (frontend).

## Global Constraints

- Motore deterministico, **nessuna AI** in questo slice.
- **Nessuna nuova dipendenza esterna** e **nessuna nuova chiamata di rete** nel dig.
- BPM/key/feature di mixing fuori scope: il dig lavora per gusto, non per compatibilità tecnica.
- Il backend emette **reason code + payload**, mai testo di presentazione già composto (i18n-friendly); il testo dei chip sta nella UI.
- Non sovrascrivere il comportamento esistente di expand; toccare solo il dig.
- Stile commit del progetto: **niente** trailer `Co-Authored-By`.
- Default riferimento di gusto = tutta la libreria. Pesi taste: `W_ARTIST=0.5`, `W_LABEL=0.3`, `W_STYLE=0.2`. `FAMILIARITY_FULL_AT=3`.
- Comandi backend da `backend/` con venv attivo: `source .venv/bin/activate`.

---

## File Structure

- `backend/app/services/discovery_dig.py` — core: `TasteProfile`, `_style_tokens`, scoring esteso, `Reason`, `_reasons`, firma `dig()`.
- `backend/tests/test_discovery_dig.py` — test del core (helper `_lib` esteso).
- `backend/app/schemas.py` — `ReasonOut`, `reasons` su `DiscoveryLeadOut`, `taste_playlist_id` su `DiscoveryDigRequest`.
- `backend/app/routers/discovery.py` — `_lead_out` mappa `reasons`; `dig_endpoint` costruisce `taste_tracks` dalla playlist.
- `backend/tests/test_discovery.py` — test endpoint dig (router) per `reasons` e `taste_playlist_id` (se non già qui, usare il client di test esistente).
- `frontend/lib/api.ts` — `Reason`, `reasons` su `DiscoveryLead`, `taste_playlist_id` in `discoveryDig`.
- `frontend/app/discovery/page.tsx` — selettore riferimento di gusto + render chip.

---

## Task 1: `TasteProfile` + tokenizzazione stile

**Files:**
- Modify: `backend/app/services/discovery_dig.py`
- Test: `backend/tests/test_discovery_dig.py`

**Interfaces:**
- Produces:
  - `_style_tokens(value: str | None) -> set[str]`
  - `class TasteProfile` con campi `artist_counts: dict[str,int]`, `owned_labels: set[str]`, `genre_tokens: set[str]` e metodi:
    - `TasteProfile.from_tracks(tracks) -> TasteProfile`
    - `.familiarity(artist: str) -> float` (0..1, graduata su `FAMILIARITY_FULL_AT`)
    - `.artist_count(artist: str) -> int`
    - `.label_affinity(label: str | None) -> float` (0.0/1.0)
    - `.style_affinity(style: str | None) -> float` (0.0/1.0)
  - costanti `W_ARTIST`, `W_LABEL`, `W_STYLE`, `FAMILIARITY_FULL_AT`

- [ ] **Step 1: Estendi l'helper `_lib` nei test per supportare label/genre**

In `backend/tests/test_discovery_dig.py`, sostituisci l'attuale `_lib`:

```python
def _lib(*items):
    """Track finte. Ogni item: (artist, title) o (artist, title, {"label":..., "genre":...})."""
    out = []
    for it in items:
        extra = it[2] if len(it) > 2 else {}
        out.append(SimpleNamespace(
            artist=it[0], title=it[1],
            label=extra.get("label"), genre=extra.get("genre"),
        ))
    return out
```

- [ ] **Step 2: Scrivi i test falliti per `TasteProfile` e `_style_tokens`**

Aggiungi in fondo a `backend/tests/test_discovery_dig.py`:

```python
from app.services.discovery_dig import TasteProfile, _style_tokens, FAMILIARITY_FULL_AT


def test_style_tokens_normalizes_and_splits():
    assert _style_tokens("Deep House") == {"deep", "house"}
    assert _style_tokens("Tech-House / Minimal") == {"tech", "house", "minimal"}
    assert _style_tokens(None) == set()
    assert _style_tokens("") == set()


def test_taste_profile_from_tracks_aggregates():
    p = TasteProfile.from_tracks(_lib(
        ("Aphex Twin", "Xtal", {"label": "Warp", "genre": "IDM"}),
        ("Aphex Twin", "Ageispolis", {"label": "Warp", "genre": "IDM"}),
        ("Boards Of Canada", "Roygbiv", {"label": "Warp", "genre": "Downtempo"}),
    ))
    assert p.artist_count("aphex twin") == 2
    assert p.owned_labels == {"warp"}
    assert {"idm", "downtempo"} <= p.genre_tokens


def test_taste_profile_familiarity_is_graduated():
    p = TasteProfile.from_tracks(_lib(
        ("Solo", "A"),
        ("Trio", "A"), ("Trio", "B"), ("Trio", "C"),
    ))
    assert p.familiarity("Solo") == 1 / FAMILIARITY_FULL_AT
    assert p.familiarity("Trio") == 1.0          # 3 release: piena
    assert p.familiarity("Unknown") == 0.0


def test_taste_profile_affinities():
    p = TasteProfile.from_tracks(_lib(("A", "B", {"label": "Warp", "genre": "Acid House"})))
    assert p.label_affinity("Warp") == 1.0
    assert p.label_affinity("warp") == 1.0
    assert p.label_affinity("Other") == 0.0
    assert p.label_affinity(None) == 0.0
    assert p.style_affinity("Acid House") == 1.0     # token in comune
    assert p.style_affinity("Techno") == 0.0
    assert p.style_affinity(None) == 0.0
```

- [ ] **Step 3: Esegui i test per verificarne il fallimento**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_discovery_dig.py -k "style_tokens or taste_profile" -v`
Expected: FAIL con `ImportError`/`cannot import name 'TasteProfile'`.

- [ ] **Step 4: Implementa `_style_tokens`, le costanti e `TasteProfile`**

In `backend/app/services/discovery_dig.py`, dopo le costanti esistenti (sotto `_VARIANT_RE`), aggiungi:

```python
# Pesi del termine "gusto" nello score (somma 1.0). Tarabili.
W_ARTIST = 0.5
W_LABEL = 0.3
W_STYLE = 0.2
# Quante release di un artista nel riferimento bastano per familiarita' piena.
FAMILIARITY_FULL_AT = 3
```

Poi, dopo `_norm`/`_dedup_key` (cioè prima di `_lead_from_release`), aggiungi:

```python
def _style_tokens(value: Any) -> set[str]:
    """Token normalizzati di uno style/genere ('Deep House' -> {'deep','house'})."""
    return {tok for tok in re.split(r"[^a-z0-9]+", _norm(value)) if tok}


@dataclass
class TasteProfile:
    """Riassunto deterministico del gusto di un riferimento (libreria o playlist).

    Costruito da una lista di Track-like (servono artist, label, genre).
    Indipendente dalla dedup: misura affinita', non possesso.
    """
    artist_counts: dict[str, int] = field(default_factory=dict)
    owned_labels: set[str] = field(default_factory=set)
    genre_tokens: set[str] = field(default_factory=set)

    @classmethod
    def from_tracks(cls, tracks: list) -> "TasteProfile":
        artist_counts: dict[str, int] = {}
        owned_labels: set[str] = set()
        genre_tokens: set[str] = set()
        for t in tracks or []:
            a = _norm(getattr(t, "artist", None))
            if a:
                artist_counts[a] = artist_counts.get(a, 0) + 1
            lbl = _norm(getattr(t, "label", None))
            if lbl:
                owned_labels.add(lbl)
            genre_tokens |= _style_tokens(getattr(t, "genre", None))
        return cls(artist_counts, owned_labels, genre_tokens)

    def artist_count(self, artist: str) -> int:
        return self.artist_counts.get(_norm(artist), 0)

    def familiarity(self, artist: str) -> float:
        return min(self.artist_count(artist) / FAMILIARITY_FULL_AT, 1.0)

    def label_affinity(self, label: str | None) -> float:
        return 1.0 if label and _norm(label) in self.owned_labels else 0.0

    def style_affinity(self, style: str | None) -> float:
        return 1.0 if _style_tokens(style) & self.genre_tokens else 0.0
```

Nota: `_norm` e `_norm(getattr(...))` accettano `None` (ritorna `""`), quindi `_style_tokens(None) == set()`.

- [ ] **Step 5: Esegui i test per verificarne il successo**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_discovery_dig.py -k "style_tokens or taste_profile" -v`
Expected: PASS (4 test).

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/discovery_dig.py backend/tests/test_discovery_dig.py
git commit -m "feat(discovery): TasteProfile e tokenizzazione stile per il dig"
```

---

## Task 2: Scoring esteso con i segnali di gusto

**Files:**
- Modify: `backend/app/services/discovery_dig.py` (`_score`, `dig`)
- Test: `backend/tests/test_discovery_dig.py`

**Interfaces:**
- Consumes: `TasteProfile` (Task 1), costanti pesi (Task 1).
- Produces:
  - `_score(lead: DiscoveryLead, profile: TasteProfile, adventurousness: float, current_year: int) -> float`
  - `dig(db, *, seed_type, value, search_releases, library=None, taste_tracks=None, adventurousness=0.4, limit=DEFAULT_DIG_LIMIT) -> DigResult`
    (nuovo parametro keyword `taste_tracks`; default `None` ⇒ riferimento = `library`)

- [ ] **Step 1: Scrivi i test falliti per i nuovi segnali di gusto**

Aggiungi in `backend/tests/test_discovery_dig.py`:

```python
def test_dig_label_boost_changes_order():
    def search(**kw):
        return [
            _release("No Label Match - Track", rid=1, label="Unknown Lbl", have=20),
            _release("Followed - Track", rid=2, label="Warp", have=20),
        ]

    # Riferimento di gusto: possiedo qualcosa su Warp. adv basso => conta il gusto.
    res = dig(None, seed_type="genre", value="x", search_releases=search,
              library=[], taste_tracks=_lib(("Whoever", "Whatever", {"label": "Warp"})),
              adventurousness=0.1)
    assert res.leads[0].label == "Warp"


def test_dig_style_affinity_changes_order():
    def search(**kw):
        return [
            _release("Off Style - Track", rid=1, style="Trance", have=20),
            _release("On Style - Track", rid=2, style="Acid House", have=20),
        ]

    res = dig(None, seed_type="genre", value="x", search_releases=search,
              library=[], taste_tracks=_lib(("Whoever", "Whatever", {"genre": "Acid House"})),
              adventurousness=0.1)
    assert res.leads[0].style == "Acid House"


def test_dig_graduated_familiarity_prefers_more_collected():
    def search(**kw):
        return [
            _release("Once - Track", rid=1, have=20),
            _release("Thrice - Track", rid=2, have=20),
        ]

    # 'Thrice' lo possiedo 3 volte (familiarita' piena), 'Once' una volta sola.
    res = dig(None, seed_type="genre", value="x", search_releases=search,
              library=[],
              taste_tracks=_lib(
                  ("Once", "a"),
                  ("Thrice", "a"), ("Thrice", "b"), ("Thrice", "c"),
              ),
              adventurousness=0.1)
    assert res.leads[0].artist == "Thrice"


def test_dig_dedup_is_library_wide_even_with_playlist_taste():
    def search(**kw):
        return [_release("Owned Elsewhere - Track", rid=1)]

    # Il riferimento di gusto e' una playlist che NON contiene il brano,
    # ma il brano e' gia' in libreria: deve restare scartato (dedup library-wide).
    res = dig(None, seed_type="genre", value="x", search_releases=search,
              library=_lib(("Owned Elsewhere", "Track")),
              taste_tracks=_lib(("Other", "Thing")), limit=50)
    assert res.leads == []
```

- [ ] **Step 2: Esegui i test per verificarne il fallimento**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_discovery_dig.py -k "label_boost or style_affinity or graduated or library_wide" -v`
Expected: FAIL — `dig()` non accetta `taste_tracks` (TypeError) o ordinamento errato.

- [ ] **Step 3: Riscrivi `_score` per usare `TasteProfile`**

In `backend/app/services/discovery_dig.py`, sostituisci la funzione `_score` esistente con:

```python
def _score(lead: DiscoveryLead, profile: TasteProfile, adventurousness: float, current_year: int) -> float:
    """Scoperta (novita'+domanda) vs gusto (familiarita'+etichetta+stile), pesate da adventurousness.

    Il termine 'gusto' combina tre segnali deterministici dal riferimento scelto:
    quanto collezioni l'artista (graduato), se segui l'etichetta, se lo stile e' nei tuoi generi.
    """
    novelty = 1.0 - min(lead.have, _HAVE_CAP) / _HAVE_CAP
    demand = _demand(lead.have, lead.want)
    discovery = 0.5 * novelty + 0.5 * demand
    taste = (
        W_ARTIST * profile.familiarity(lead.artist)
        + W_LABEL * profile.label_affinity(lead.label)
        + W_STYLE * profile.style_affinity(lead.style)
    )
    recency = _recency(lead.year, current_year)
    return adventurousness * discovery + (1.0 - adventurousness) * taste + 0.2 * recency
```

- [ ] **Step 4: Aggiorna `dig()` — `taste_tracks` + profilo, rimuovi `owned_artists`**

In `backend/app/services/discovery_dig.py`, aggiorna la firma e il corpo di `dig`:

Firma (aggiungi `taste_tracks`):

```python
def dig(
    db: Session,
    *,
    seed_type: str,
    value: str,
    search_releases: SearchReleases,
    library: list | None = None,
    taste_tracks: list | None = None,
    adventurousness: float = 0.4,
    limit: int = DEFAULT_DIG_LIMIT,
) -> DigResult:
```

Nel corpo, sostituisci il blocco iniziale:

```python
    if library is None:
        library = _library_tracks(db)
    owned_keys = {_dedup_key(t.artist or "", t.title or "") for t in library if t.artist and t.title}
    owned_artists = {_norm(t.artist) for t in library if t.artist}
```

con (rimuove `owned_artists`, costruisce il profilo dal riferimento):

```python
    if library is None:
        library = _library_tracks(db)
    owned_keys = {_dedup_key(t.artist or "", t.title or "") for t in library if t.artist and t.title}
    profile = TasteProfile.from_tracks(library if taste_tracks is None else taste_tracks)
```

e nel ciclo di scoring sostituisci:

```python
    for lead in leads:
        lead.score = _score(lead, owned_artists, adv, current_year)
```

con:

```python
    for lead in leads:
        lead.score = _score(lead, profile, adv, current_year)
```

- [ ] **Step 5: Esegui tutta la suite del dig (nuovi + esistenti)**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_discovery_dig.py -v`
Expected: PASS — i 4 nuovi test e tutti gli esistenti (compresi `test_dig_familiar_first_when_safe`, `test_dig_adventurous_surfaces_deep_cuts`).

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/discovery_dig.py backend/tests/test_discovery_dig.py
git commit -m "feat(discovery): scoring dig con gusto (etichetta, stile, familiarita' graduata) su riferimento selezionabile"
```

---

## Task 3: Reason codes (spiegazioni deterministiche)

**Files:**
- Modify: `backend/app/services/discovery_dig.py` (`DiscoveryLead`, nuova `Reason`, `_reasons`, ciclo in `dig`)
- Test: `backend/tests/test_discovery_dig.py`

**Interfaces:**
- Consumes: `TasteProfile` (Task 1), `_demand`/`_recency` esistenti.
- Produces:
  - `class Reason` con `code: str`, `data: dict[str, Any]`
  - `DiscoveryLead.reasons: list[Reason]`
  - `_reasons(lead: DiscoveryLead, profile: TasteProfile, current_year: int) -> list[Reason]`
  - costanti soglia: `REASON_RARE_MIN_WANT`, `REASON_RARE_MIN_DEMAND`, `REASON_DEEP_CUT_MAX_HAVE`, `REASON_RECENT_MIN`

- [ ] **Step 1: Scrivi i test falliti per i reason codes**

Aggiungi in `backend/tests/test_discovery_dig.py`:

```python
from datetime import datetime, timezone


def _codes(lead):
    return {r.code for r in lead.reasons}


def test_dig_emits_rare_wanted_and_deep_cut():
    def search(**kw):
        return [_release("Cult - Grail", rid=1, have=3, want=120)]

    res = dig(None, seed_type="genre", value="x", search_releases=search, library=[])
    lead = res.leads[0]
    assert "rare_wanted" in _codes(lead)
    assert "deep_cut" in _codes(lead)
    rare = next(r for r in lead.reasons if r.code == "rare_wanted")
    assert rare.data == {"have": 3, "want": 120}


def test_dig_no_rare_wanted_when_not_demanded():
    def search(**kw):
        return [_release("Common - Tune", rid=1, have=4000, want=2)]

    res = dig(None, seed_type="genre", value="x", search_releases=search, library=[])
    codes = _codes(res.leads[0])
    assert "rare_wanted" not in codes
    assert "deep_cut" not in codes        # have=4000 > soglia


def test_dig_emits_taste_reason_codes():
    def search(**kw):
        return [_release("Followed - Track", rid=1, label="Warp", style="Acid House", have=20)]

    res = dig(None, seed_type="genre", value="x", search_releases=search, library=[],
              taste_tracks=_lib(("Followed", "Older", {"label": "Warp", "genre": "Acid House"})))
    lead = res.leads[0]
    codes = _codes(lead)
    assert {"label_followed", "artist_collected", "style_match"} <= codes
    art = next(r for r in lead.reasons if r.code == "artist_collected")
    assert art.data == {"artist": "Followed", "count": 1}


def test_dig_emits_recent_reason():
    cur = datetime.now(timezone.utc).year

    def search(**kw):
        return [_release("New - Drop", rid=1, year=cur, have=20)]

    res = dig(None, seed_type="genre", value="x", search_releases=search, library=[])
    assert "recent" in _codes(res.leads[0])
```

- [ ] **Step 2: Esegui i test per verificarne il fallimento**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_discovery_dig.py -k "reason or rare_wanted or recent or taste_reason" -v`
Expected: FAIL — `DiscoveryLead` non ha `reasons` / `_reasons` non esiste.

- [ ] **Step 3: Aggiungi `Reason`, soglie, campo `reasons`, `_reasons`**

In `backend/app/services/discovery_dig.py`:

(a) dopo le costanti pesi (Task 1) aggiungi le soglie:

```python
# Soglie per i reason code (spiegazioni). Costanti, deterministiche.
REASON_RARE_MIN_WANT = 10       # almeno 10 persone lo cercano
REASON_RARE_MIN_DEMAND = 0.5    # want/(have+want) >= 0.5
REASON_DEEP_CUT_MAX_HAVE = 50   # pochissimi lo possiedono
REASON_RECENT_MIN = 0.8         # recency alta (ultimi ~3 anni su span 15)
```

(b) aggiungi la dataclass `Reason` prima di `DiscoveryLead`:

```python
@dataclass
class Reason:
    """Spiegazione strutturata: codice + payload dati. Il testo lo compone la UI."""
    code: str
    data: dict[str, Any] = field(default_factory=dict)
```

(c) aggiungi il campo a `DiscoveryLead` (in fondo ai campi):

```python
    reasons: list[Reason] = field(default_factory=list)
```

(d) aggiungi la funzione `_reasons` dopo `_score`:

```python
def _reasons(lead: DiscoveryLead, profile: TasteProfile, current_year: int) -> list[Reason]:
    """Emette i reason code attivi per un lead, secondo soglie deterministiche."""
    out: list[Reason] = []
    if lead.want >= REASON_RARE_MIN_WANT and _demand(lead.have, lead.want) >= REASON_RARE_MIN_DEMAND:
        out.append(Reason("rare_wanted", {"have": lead.have, "want": lead.want}))
    if lead.have <= REASON_DEEP_CUT_MAX_HAVE:
        out.append(Reason("deep_cut", {"have": lead.have}))
    if profile.label_affinity(lead.label) > 0:
        out.append(Reason("label_followed", {"label": lead.label}))
    count = profile.artist_count(lead.artist)
    if count > 0:
        out.append(Reason("artist_collected", {"artist": lead.artist, "count": count}))
    if profile.style_affinity(lead.style) > 0:
        out.append(Reason("style_match", {"style": lead.style}))
    if _recency(lead.year, current_year) >= REASON_RECENT_MIN:
        out.append(Reason("recent", {"year": lead.year}))
    return out
```

- [ ] **Step 4: Popola `reasons` nel ciclo di `dig`**

In `dig`, sostituisci il ciclo di scoring:

```python
    for lead in leads:
        lead.score = _score(lead, profile, adv, current_year)
```

con:

```python
    for lead in leads:
        lead.score = _score(lead, profile, adv, current_year)
        lead.reasons = _reasons(lead, profile, current_year)
```

- [ ] **Step 5: Esegui i test per verificarne il successo**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_discovery_dig.py -v`
Expected: PASS (tutti, vecchi e nuovi).

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/discovery_dig.py backend/tests/test_discovery_dig.py
git commit -m "feat(discovery): reason code deterministici sui lead del dig"
```

---

## Task 4: API — `reasons` in output e `taste_playlist_id` in input

**Files:**
- Modify: `backend/app/schemas.py` (`ReasonOut`, `DiscoveryLeadOut`, `DiscoveryDigRequest`)
- Modify: `backend/app/routers/discovery.py` (`_lead_out`, `dig_endpoint`)
- Test: `backend/tests/test_discovery.py`

**Interfaces:**
- Consumes: `Reason`/`reasons` dal servizio (Task 3), `dig(..., taste_tracks=...)` (Task 2), `tracks_for_playlist` da `app.repositories`.
- Produces:
  - schema `ReasonOut(code: str, data: dict[str, Any])`
  - `DiscoveryLeadOut.reasons: list[ReasonOut]`
  - `DiscoveryDigRequest.taste_playlist_id: int | None`
  - endpoint `POST /api/discovery/dig` che onora `taste_playlist_id`.

- [ ] **Step 1: Scrivi il test d'integrazione fallito sul router**

In `backend/tests/test_discovery.py` (riusa il `client`/fixture già presenti nel file; se serve un TestClient locale, segui il pattern degli altri test del file). Aggiungi:

```python
def test_dig_endpoint_returns_reasons(monkeypatch):
    from app.integrations.discogs import DiscogsClient

    def fake_search(self, **kw):
        return [{
            "id": 1, "title": "Cult - Grail", "year": 2024,
            "label": ["Warp"], "style": ["Acid House"],
            "community": {"have": 3, "want": 120}, "format": ["Vinyl"],
            "uri": "/release/1", "cover_image": "http://img",
        }]

    monkeypatch.setattr(DiscogsClient, "search_releases", fake_search)
    resp = client.post("/api/discovery/dig", json={"seed_type": "genre", "value": "Acid House"})
    assert resp.status_code == 200
    leads = resp.json()["leads"]
    assert leads, "atteso almeno un lead"
    codes = {r["code"] for r in leads[0]["reasons"]}
    assert "rare_wanted" in codes and "deep_cut" in codes
```

(Se nel file il TestClient si chiama diversamente o serve un DB di test, allinea l'uso al resto di `test_discovery.py`.)

- [ ] **Step 2: Esegui il test per verificarne il fallimento**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_discovery.py -k reasons -v`
Expected: FAIL — la risposta non contiene `reasons` (KeyError) o lo schema lo scarta.

- [ ] **Step 3: Aggiungi `ReasonOut` e i campi agli schemi**

In `backend/app/schemas.py`:

(a) verifica che `Any` sia importato da `typing` in cima al file; se manca, aggiungi `Any` all'import esistente `from typing import ...`.

(b) prima di `class DiscoveryLeadOut(BaseModel)` aggiungi:

```python
class ReasonOut(BaseModel):
    """Spiegazione strutturata di un lead: codice + payload. Il testo lo rende la UI."""
    code: str
    data: dict[str, Any] = {}
```

(c) in `DiscoveryLeadOut` aggiungi il campo (in fondo):

```python
    reasons: list[ReasonOut] = []
```

(d) in `DiscoveryDigRequest` aggiungi il campo:

```python
    taste_playlist_id: int | None = None  # riferimento di gusto; None = tutta la libreria
```

- [ ] **Step 4: Mappa `reasons` e onora `taste_playlist_id` nel router**

In `backend/app/routers/discovery.py`:

(a) aggiorna l'import dello schema (aggiungi `ReasonOut` all'elenco da `app.schemas`).

(b) aggiorna `_lead_out` per mappare i reason:

```python
def _lead_out(lead: DiscoveryLead) -> DiscoveryLeadOut:
    return DiscoveryLeadOut(
        artist=lead.artist, title=lead.title, year=lead.year, label=lead.label,
        style=lead.style, source=lead.source, seed=lead.seed,
        discogs_url=lead.discogs_url, thumb_url=lead.thumb_url,
        have=lead.have, want=lead.want,
        reasons=[ReasonOut(code=r.code, data=r.data) for r in lead.reasons],
    )
```

(c) aggiorna `dig_endpoint` per costruire `taste_tracks` dalla playlist scelta:

```python
@router.post("/dig", response_model=DiscoveryDigResponse)
def dig_endpoint(req: DiscoveryDigRequest, db: Session = Depends(get_db)):
    """Lista-dig a volume da Discogs per genere/stile o etichetta (lead non risolti)."""
    from app.repositories import tracks_for_playlist

    taste_tracks = None
    if req.taste_playlist_id is not None:
        taste_tracks = tracks_for_playlist(db, req.taste_playlist_id)
    client = DiscogsClient()
    result = dig(
        db, seed_type=req.seed_type, value=req.value,
        search_releases=lambda **kw: client.search_releases(**kw),
        taste_tracks=taste_tracks,
        adventurousness=req.adventurousness, limit=req.limit,
    )
    return DiscoveryDigResponse(
        seed_type=result.seed_type, value=result.value,
        leads=[_lead_out(lead) for lead in result.leads],
    )
```

- [ ] **Step 5: Esegui i test (router + servizio)**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_discovery.py tests/test_discovery_dig.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas.py backend/app/routers/discovery.py backend/tests/test_discovery.py
git commit -m "feat(discovery): API dig espone reasons e accetta taste_playlist_id"
```

---

## Task 5: Frontend — riferimento di gusto + chip spiegazione

**Files:**
- Modify: `frontend/lib/api.ts` (`Reason`, `DiscoveryLead.reasons`, `discoveryDig` opts)
- Modify: `frontend/app/discovery/page.tsx` (selettore riferimento, render chip)

**Interfaces:**
- Consumes: API `POST /api/discovery/dig` con `taste_playlist_id` e `leads[].reasons` (Task 4); `playlists` già caricate nella pagina.
- Produces: nessun export nuovo verso altri file.

- [ ] **Step 1: Aggiorna i tipi e il client in `lib/api.ts`**

(a) aggiungi l'interfaccia `Reason` e il campo a `DiscoveryLead`:

```typescript
export interface Reason {
  code: string;
  data: Record<string, string | number>;
}

export interface DiscoveryLead {
  artist: string;
  title: string;
  year: number | null;
  label: string | null;
  style: string | null;
  source: string;
  seed: string | null;
  discogs_url: string | null;
  thumb_url: string | null;
  have: number;
  want: number;
  reasons: Reason[];
}
```

(b) estendi `discoveryDig` con `tastePlaylistId`:

```typescript
export function discoveryDig(
  seedType: "genre" | "label",
  value: string,
  opts?: { adventurousness?: number; limit?: number; tastePlaylistId?: number | null },
) {
  return apiPost<DiscoveryDigResponse>("/api/discovery/dig", {
    seed_type: seedType,
    value,
    adventurousness: opts?.adventurousness,
    limit: opts?.limit,
    taste_playlist_id: opts?.tastePlaylistId ?? null,
  });
}
```

- [ ] **Step 2: Aggiungi lo stato e il selettore "riferimento di gusto"**

In `frontend/app/discovery/page.tsx`, nello stato della sezione dig (vicino a `const [adventurousness, ...]`):

```tsx
  const [tasteRef, setTasteRef] = useState<number | null>(null); // null = tutta la libreria
```

In `runDig`, passa il riferimento (modifica la chiamata esistente):

```tsx
      setDig(await discoveryDig(digSeed, value, { adventurousness, tastePlaylistId: tasteRef }));
```

Nel blocco UI del dig (dentro `{mode === "dig" && ( ... )}`, vicino ai controlli di seme/audacia), aggiungi il selettore. `playlists` è già in stato:

```tsx
          <label className="block text-xs uppercase tracking-wide text-muted">
            Affinità rispetto a
            <Select
              className="mt-1"
              value={tasteRef ?? ""}
              onChange={(e) => setTasteRef(e.target.value ? Number(e.target.value) : null)}
              disabled={busy}
            >
              <option value="">Tutta la libreria</option>
              {playlists?.map((p) => (
                <option key={p.id} value={p.id}>{p.name}</option>
              ))}
            </Select>
          </label>
```

(Allinea wrapper/classi al markup vicino — usa lo stesso `Select` già importato nella pagina.)

- [ ] **Step 3: Rendi i chip in `LeadRow`**

In `frontend/app/discovery/page.tsx`, aggiungi una mappa codice→testo a livello modulo (vicino agli altri helper in cima al file):

```tsx
function reasonLabel(r: Reason): string {
  switch (r.code) {
    case "rare_wanted":
      return `raro & richiesto ${r.data.have}/${r.data.want}`;
    case "deep_cut":
      return "deep cut";
    case "label_followed":
      return `etichetta che segui${r.data.label ? ` · ${r.data.label}` : ""}`;
    case "artist_collected":
      return "artista che collezioni";
    case "style_match":
      return "stile che ascolti";
    case "recent":
      return `recente${r.data.year ? ` · ${r.data.year}` : ""}`;
    default:
      return r.code;
  }
}
```

Aggiungi l'import del tipo `Reason` dove sono importati gli altri tipi (`type DiscoveryLead`, ...):

```tsx
  type Reason,
```

In `LeadRow`, sotto la riga dei metadati (dopo il `<div className="mt-0.5 ...">...</div>` con style/label/have/want), aggiungi i chip:

```tsx
        {l.reasons.length > 0 && (
          <div className="mt-1.5 flex flex-wrap gap-1">
            {l.reasons.map((r, i) => (
              <span
                key={`${r.code}-${i}`}
                className="inline-flex items-center rounded-none border border-border px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-muted"
              >
                {reasonLabel(r)}
              </span>
            ))}
          </div>
        )}
```

- [ ] **Step 4: Lint + build**

Run: `cd frontend && npm run lint && npm run build`
Expected: nessun errore di lint, build OK. (Se la cache `.next` dà problemi visivi in dev, vedi memoria: `rm -rf .next`.)

- [ ] **Step 5: Verifica nel browser (preview)**

Avvia il dev server (preview_start) e la pagina `/discovery`. Con la sezione DIG: esegui uno scava per genere, conferma che (a) compare il selettore "Affinità rispetto a", (b) i lead mostrano i chip. Cattura uno screenshot come prova.

- [ ] **Step 6: Commit**

```bash
git add frontend/lib/api.ts frontend/app/discovery/page.tsx
git commit -m "feat(discovery): UI dig con riferimento di gusto e chip spiegazione"
```

---

## Task 6: Documentazione di stato

**Files:**
- Modify: `docs/ROADMAP.md`
- Modify: `PROGRESS.md`
- (Eventuale) Modify: `docs/API.md` se documenta il payload `/api/discovery/dig`.

- [ ] **Step 1: Aggiorna ROADMAP — punto 1 chiuso**

In `docs/ROADMAP.md`, sposta/segna come completato lo slice del punto 1: aggiungi sotto "Stato completato" una voce tipo:

```markdown
- Discovery dig: segnali di gusto (etichetta posseduta, affinità stile, familiarità
  graduata) su riferimento selezionabile (libreria|playlist), dedup library-wide, e
  spiegazioni a chip (reason code deterministici). Unificazione expand/dig resta backlog.
```

e in "Prossimi passi" riformula il punto 1 indicando che lo slice gusto+spiegazioni è chiuso; l'unificazione expand/dig e le sorgenti extra (Last.fm tag, tracklist per-release) restano nel backlog.

- [ ] **Step 2: Aggiorna PROGRESS — voce diario**

In `PROGRESS.md`, aggiungi una voce datata 2026-06-28 che riassume lo slice e indica i file toccati (`discovery_dig.py`, `schemas.py`, `routers/discovery.py`, frontend `discovery/page.tsx`, `lib/api.ts`).

- [ ] **Step 3: (Se serve) aggiorna API.md**

Se `docs/API.md` descrive `/api/discovery/dig`, aggiungi `taste_playlist_id` (request) e `reasons[]` con `code`/`data` (response).

- [ ] **Step 4: Esegui l'intera suite backend come verifica finale**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests -q`
Expected: PASS (nessuna regressione).

- [ ] **Step 5: Commit**

```bash
git add docs/ROADMAP.md PROGRESS.md docs/API.md
git commit -m "docs(status): chiuso lo slice gusto+spiegazioni del Discovery dig"
```

---

## Self-Review (eseguita)

**Spec coverage:**
- `TasteProfile` + riferimento selezionabile → Task 1, 2, 4 (param `taste_playlist_id`).
- Separazione dedup (library-wide) vs affinità (profilo) → Task 2 (`owned_keys` da `library`, profilo da `taste_tracks`) + test `test_dig_dedup_is_library_wide_even_with_playlist_taste`.
- Scoring esteso (familiarità graduata, label, style) → Task 2.
- Reason codes (code + payload, soglie costanti) → Task 3.
- API (`taste_playlist_id`, `reasons`) → Task 4.
- UI (selettore riferimento + chip) → Task 5.
- Fuori scope (unificazione, Last.fm tag, tracklist per-release, AI nel dig) → non implementati, ribaditi in ROADMAP (Task 6).

**Placeholder scan:** nessun TBD/TODO; ogni step di codice mostra il codice.

**Type consistency:** `TasteProfile`, `Reason`/`ReasonOut`, `_score(lead, profile, ...)`, `dig(..., taste_tracks=...)`, `discoveryDig(..., {tastePlaylistId})`, `DiscoveryLead.reasons`/`ReasonOut`/`Reason` coerenti tra i task. `reasonLabel`/`Reason` lato frontend coerenti con `data` (`have`/`want`/`label`/`year`).
