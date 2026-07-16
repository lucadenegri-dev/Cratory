# Discovery dig — motore + riga di scavo: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Far sì che il dig trovi musica che all'utente piace e che non ha — pescando nella pila Discogs ordinata per domanda invece che in un campione arbitrario dello 0,69% — ed esporre quel motore con una riga di controlli leggibile.

**Architecture:** Il bacino Discogs viene ordinato per `want` e `depth` sceglie **quale finestra di 3 pagine** scaricare (0.0 = il canone, 1.0 = il fondo della pila). Dentro la finestra la domanda è ~costante, quindi il punteggio diventa **solo gusto** (familiarità artista + affinità etichetta + affinità stile), sempre attivo. La UI espone due modificatori pari grado (profondità, gusto) su una riga, con un combobox unico che suggerisce generi ed etichette insieme e deduce il `seed_type`.

**Tech Stack:** Backend Python 3 + FastAPI + SQLAlchemy + Pydantic, test con pytest. Frontend Next.js 16 (App Router) + React + Tailwind, test con vitest (`frontend/tests/`) e Playwright (`frontend/e2e/`).

**Specs:** `docs/superpowers/specs/2026-07-16-discovery-dig-motore-design.md` e `docs/superpowers/specs/2026-07-16-discovery-riga-di-scavo-design.md` (rev. 2).

## Global Constraints

- **Il motore precede la UI.** I task 1–9 (backend) vanno completati prima dei task 10–17: la UI consuma `depth` e `pile_pages`, che non esistono finché il backend non li produce.
- **Nessuna nuova dipendenza** né backend né frontend.
- **Nessuna AI nel dig**: tutto deterministico (regola non negoziabile 1 del progetto, `CLAUDE.md`).
- **Nessuna rete nei test**: `search_releases` e `count_releases` sono iniettate in `dig()`. I test esistenti in `backend/tests/test_discovery_dig.py` seguono già questo schema.
- **Design system vincolante** (`docs/DESIGN.md`): monospace ovunque, `radius: 0` (mai `rounded-*`), filetti 1px, **nessuna ombra**, monocromia — l'unico colore è `danger`, e solo per errori/distruzione. Label uppercase tracked ~10px. Ogni componente deve leggere in **entrambi i temi** (dark e paper).
- **Next.js 16 ha breaking change**: leggere `frontend/CLAUDE.md` e `node_modules/next/dist/docs/` prima di toccare pagine o routing.
- **Commit message**: mai aggiungere Claude come co-autore.
- **Prima di ogni commit**: `git status` e stagere solo i file del task (possibili sessioni parallele sullo stesso checkout).
- Costanti già esistenti da non rinominare: `SEARCH_PER_PAGE = 100`, `DEFAULT_DIG_LIMIT = 80`, `_MAX_PER_ARTIST = 2`, `W_ARTIST = 0.5`, `W_LABEL = 0.3`, `W_STYLE = 0.2`, `FAMILIARITY_FULL_AT = 3`, `REASON_RARE_MIN_WANT = 10`, `REASON_RARE_MIN_DEMAND = 0.5`, `REASON_DEEP_CUT_MAX_HAVE = 50`, `REASON_RECENT_MIN = 0.8`.

---

## File Structure

**Backend**

| File | Responsabilità | Azione |
|---|---|---|
| `backend/app/integrations/discogs.py` | Client HTTP: `sort`/`page` espliciti + `count_releases` (la sonda) | Modifica |
| `backend/app/services/discovery_dig.py` | Motore: finestra, normalizzazione, possesso, punteggio, reason | Modifica |
| `backend/app/schemas.py` | DTO: `depth`, `pile_pages` | Modifica |
| `backend/app/routers/discovery.py` | Wiring HTTP | Modifica |
| `backend/tests/test_discogs.py` | Test del client | Modifica |
| `backend/tests/test_discovery_dig.py` | Test del motore | Modifica |
| `backend/tests/test_discovery_router_http.py` | Test del contratto HTTP | Modifica |

**Frontend**

| File | Responsabilità | Azione |
|---|---|---|
| `frontend/components/ui.tsx` | Primitive del DS: `Popover`, `Combobox`, `SegmentedControl`, `Chip` | Modifica |
| `frontend/components/discovery-dig-bar.tsx` | La riga di scavo (presentazionale) | **Crea** |
| `frontend/components/discovery-lead-grid.tsx` | Griglia lead; filtri sollevati verso l'alto | Modifica |
| `frontend/app/discovery/page.tsx` | Stato + URL + chiamata API | Modifica |
| `frontend/lib/api/discovery.ts` | Client API | Modifica |
| `frontend/lib/api/types.ts` | Tipi | Modifica |
| `frontend/lib/i18n/it.ts`, `en.ts` | Stringhe | Modifica |
| `frontend/tests/ui-primitives.test.tsx` | Test delle primitive | **Crea** |
| `frontend/tests/discovery-dig-bar.test.tsx` | Test della barra | **Crea** |
| `frontend/e2e/smoke.spec.ts` | Smoke E2E | Modifica |

---

### Task 1: La sonda e l'ordinamento nel client Discogs

Oggi `search_releases` non passa `sort` e pagina da sola 1→3. Deve invece scaricare **le pagine che il motore gli chiede**, ordinate per domanda. E serve un modo per sapere quanto è alta la pila prima di scegliere.

**Files:**
- Modify: `backend/app/integrations/discogs.py:30-34` (costanti), `:56-101` (`search_releases`)
- Test: `backend/tests/test_discogs.py`

**Interfaces:**
- Consumes: niente (primo task).
- Produces:
  - `DiscogsClient.search_releases(*, style=None, genre=None, label=None, query=None, pages: list[int] | None = None, sort: str | None = None, sort_order: str | None = None, per_page: int = SEARCH_PER_PAGE) -> list[dict[str, Any]]`
  - `DiscogsClient.count_releases(*, style=None, genre=None, label=None, query=None) -> int`
  - Costanti `SORT_WANT = "want"`, `SORT_DESC = "desc"`, `DISCOGS_MAX_PAGES = 100`.

- [ ] **Step 1: Write the failing tests**

In `backend/tests/test_discogs.py`, aggiungi in fondo:

```python
def test_count_releases_reads_pagination_items():
    calls = []

    def handler(url, params=None, **kw):
        calls.append(params)
        return _resp({"pagination": {"items": 43345, "pages": 100}, "results": []})

    client = DiscogsClient(token=None, http=_FakeHttp(handler))
    assert client.count_releases(style="Acid House") == 43345
    # la sonda deve essere ECONOMICA: una riga, non cento
    assert calls[0]["per_page"] == 1
    assert calls[0]["style"] == "Acid House"


def test_search_releases_fetches_requested_pages_sorted():
    seen_pages = []

    def handler(url, params=None, **kw):
        seen_pages.append(params["page"])
        return _resp({
            "pagination": {"items": 1000, "pages": 10},
            "results": [{"id": params["page"], "title": f"A - P{params['page']}"}],
        })

    client = DiscogsClient(token=None, http=_FakeHttp(handler))
    out = client.search_releases(style="Acid House", pages=[8, 9, 10],
                                 sort=SORT_WANT, sort_order=SORT_DESC)
    assert seen_pages == [8, 9, 10]
    assert [r["id"] for r in out] == [8, 9, 10]


def test_search_releases_sends_sort_params():
    captured = {}

    def handler(url, params=None, **kw):
        captured.update(params)
        return _resp({"pagination": {"items": 10, "pages": 1}, "results": []})

    client = DiscogsClient(token=None, http=_FakeHttp(handler))
    client.search_releases(label="Trax Records", pages=[1], sort=SORT_WANT, sort_order=SORT_DESC)
    assert captured["sort"] == "want"
    assert captured["sort_order"] == "desc"


def test_search_releases_stops_at_the_first_failed_later_page():
    def handler(url, params=None, **kw):
        if params["page"] == 2:
            raise httpx.HTTPError("boom")
        return _resp({"pagination": {"items": 500, "pages": 5},
                      "results": [{"id": params["page"], "title": "A - B"}]})

    client = DiscogsClient(token=None, http=_FakeHttp(handler))
    # Ci si FERMA, non si salta la pagina rotta: il modo di fallire dominante su
    # Discogs e' il rate limit (~25 req/min senza token), e allora anche la pagina
    # successiva fallirebbe. Tiene le pagine raccolte fino a li': solo la 1.
    assert len(client.search_releases(style="x", pages=[1, 2, 3])) == 1
```

Se `_resp` / `_FakeHttp` non esistono già in quel file, riusa lo helper HTTP finto già presente (leggi il file prima: la forma va imitata, non reinventata). Aggiungi in cima gli import mancanti: `import httpx` e `from app.integrations.discogs import DiscogsClient, SORT_WANT, SORT_DESC`.

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && source .venv/bin/activate && python -m pytest tests/test_discogs.py -v -k "count_releases or requested_pages or sort_params or degrades"
```
Expected: FAIL — `ImportError: cannot import name 'SORT_WANT'`.

- [ ] **Step 3: Implement**

In `backend/app/integrations/discogs.py`, sostituisci il blocco costanti (`:30-34`):

```python
SEARCH_PER_PAGE = 100  # max consentito da Discogs: massimizza il volume per chiamata
# Ordinamento del bacino: per DOMANDA. Senza `sort`, Discogs restituisce un ordine
# arbitrario: su style=Acid House (43k release) le prime 300 non contengono NEMMENO UNA
# release con have>1000 e il 46% ne ha meno di 5. Con sort=want la prima pagina e' il
# canone (Phuture, Underground Resistance). Misurato, non supposto.
SORT_WANT = "want"
SORT_DESC = "desc"
# Tetto duro di Discogs: pagina 101 -> 404. Con per_page=100 sono 10.000 release.
DISCOGS_MAX_PAGES = 100
```

Elimina `SEARCH_MAX_PAGES` (il motore passa ora le pagine esplicite) e sostituisci `search_releases` con:

```python
    def _filters(self, style, genre, label, query) -> dict[str, Any]:
        params: dict[str, Any] = {"type": "release"}
        if style:
            params["style"] = style
        if genre:
            params["genre"] = genre
        if label:
            params["label"] = label
        if query:
            params["q"] = query
        return params

    def count_releases(
        self, *, style: str | None = None, genre: str | None = None,
        label: str | None = None, query: str | None = None,
    ) -> int:
        """Quante release ha il seme. Sonda economica (per_page=1): serve a sapere
        quanto e' alta la pila PRIMA di scegliere in che punto pescare."""
        params = self._filters(style, genre, label, query)
        if len(params) == 1:  # solo `type`: nessun filtro
            return 0
        data = self._get("/database/search", params={**params, "per_page": 1, "page": 1})
        return int((data.get("pagination") or {}).get("items") or 0)

    def search_releases(
        self, *, style: str | None = None, genre: str | None = None,
        label: str | None = None, query: str | None = None,
        pages: list[int] | None = None, sort: str | None = None,
        sort_order: str | None = None, per_page: int = SEARCH_PER_PAGE,
    ) -> list[dict[str, Any]]:
        """Release da `/database/search`, per le PAGINE richieste dal chiamante.

        Il motore decide quali pagine (la finestra scelta da `depth`); il client le
        scarica e basta.

        Errori: la PRIMA pagina richiesta che fallisce SOLLEVA DiscogsError (rate limit o
        token mancante non devono sembrare 'zero risultati': il router li traduce in 502
        esplicito); una pagina successiva in errore degrada ai risultati gia' raccolti.
        """
        params = self._filters(style, genre, label, query)
        if len(params) == 1:
            return []
        params["per_page"] = per_page
        if sort:
            params["sort"] = sort
        if sort_order:
            params["sort_order"] = sort_order

        results: list[dict[str, Any]] = []
        for i, page in enumerate(pages or [1]):
            try:
                data = self._get("/database/search", params={**params, "page": page})
            except DiscogsError as exc:
                if i == 0:
                    raise
                logger.warning(
                    "Discogs search_releases(%s) pagina %d fallita: %s — "
                    "ritorno i %d risultati gia' raccolti",
                    params, page, exc, len(results),
                )
                break
            results.extend(data.get("results") or [])
        return results
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && source .venv/bin/activate && python -m pytest tests/test_discogs.py -v
```
Expected: PASS. Se un test preesistente si aspettava la paginazione automatica 1→3, aggiornalo: il contratto è cambiato apposta.

- [ ] **Step 5: Commit**

```bash
git add backend/app/integrations/discogs.py backend/tests/test_discogs.py
git commit -m "feat(discogs): ordinamento per domanda, pagine esplicite e sonda count_releases"
```

---

### Task 2: `_window` — dove affondare le mani

Pura aritmetica, nessuna rete. È il cuore del ribaltamento: `depth` sceglie il bacino.

**Files:**
- Modify: `backend/app/services/discovery_dig.py` (costanti in cima, nuova funzione)
- Test: `backend/tests/test_discovery_dig.py`

**Interfaces:**
- Consumes: `DISCOGS_MAX_PAGES`, `SEARCH_PER_PAGE` da Task 1.
- Produces: `_window(depth: float, total_items: int) -> list[int]`, costante `PAGES_PER_DIG = 3`.

- [ ] **Step 1: Write the failing test**

In `backend/tests/test_discovery_dig.py`, aggiungi in fondo:

```python
def test_window_depth_zero_is_the_canon():
    assert _window(0.0, 43345) == [1, 2, 3]


def test_window_depth_one_is_the_bottom_of_the_pile():
    # 43345 release -> 434 pagine, ma Discogs si ferma a 100 (pagina 101 -> 404)
    assert _window(1.0, 43345) == [98, 99, 100]


def test_window_is_always_three_pages():
    # regressione: una finestra di 4 pagine costa una richiesta di troppo a ogni dig
    for depth in (0.0, 0.15, 0.5, 0.85, 1.0):
        assert len(_window(depth, 43345)) == 3


def test_window_is_monotonic_in_depth():
    starts = [_window(d, 43345)[0] for d in (0.0, 0.15, 0.5, 0.85, 1.0)]
    assert starts == sorted(starts)
    assert starts == [1, 16, 49, 83, 98]


def test_window_short_pile_ignores_depth():
    # 150 release = 2 pagine: non c'e' profondita' da scegliere
    assert _window(0.0, 150) == [1, 2]
    assert _window(1.0, 150) == [1, 2]


def test_window_tiny_pile():
    assert _window(0.5, 40) == [1]


def test_window_empty_pile():
    assert _window(0.5, 0) == []
```

Aggiorna l'import in cima al file:

```python
from app.services.discovery_dig import _lead_from_release, _window, dig
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && source .venv/bin/activate && python -m pytest tests/test_discovery_dig.py -v -k window
```
Expected: FAIL — `ImportError: cannot import name '_window'`.

- [ ] **Step 3: Implement**

In `backend/app/services/discovery_dig.py`, aggiungi `import math` in cima e, sotto `DEFAULT_DIG_LIMIT`:

```python
from app.integrations.discogs import DISCOGS_MAX_PAGES, SEARCH_PER_PAGE

PAGES_PER_DIG = 3  # quante pagine scarica un dig: 3 richieste di contenuto


def _window(depth: float, total_items: int) -> list[int]:
    """Le pagine da scaricare dalla pila ordinata per domanda.

    depth 0 = il canone del seme, depth 1 = il fondo della pila. La pila regge per
    tutta la sua lunghezza: a rango 9901-10000 il `want` mediano e' ancora 89, e a
    NESSUNA profondita' esiste un disco con want<5 (misurato su style=Acid House).

    Su una pila piu' corta della finestra, `depth` non ha effetto: non c'e' profondita'
    da scegliere. Il chiamante lo segnala alla UI via `pile_pages`.
    """
    usable = min(math.ceil(total_items / SEARCH_PER_PAGE), DISCOGS_MAX_PAGES)
    if usable <= 0:
        return []
    start = 1 + round(max(0.0, min(1.0, depth)) * max(0, usable - PAGES_PER_DIG))
    # il `- 1` non e' cosmetico: senza, la finestra e' di 4 pagine e ogni dig
    # spende una richiesta di troppo.
    return list(range(start, min(start + PAGES_PER_DIG - 1, usable) + 1))
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd backend && source .venv/bin/activate && python -m pytest tests/test_discovery_dig.py -v -k window
```
Expected: PASS (7 test).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/discovery_dig.py backend/tests/test_discovery_dig.py
git commit -m "feat(dig): _window — la profondita' sceglie la finestra nella pila"
```

---

### Task 3: La grammatica di Discogs — normalizzazione degli artisti

`_norm` è `strip().lower()` e non sa che Discogs disambigua gli omonimi con `*` e `(N)`, e che mette più artisti in un campo. Misurato: **il 17% dei lead non può agganciare la libreria**. Metà del punteggio di gusto (`W_ARTIST = 0.5`) muore lì, e i dischi che possiedi di quegli artisti ti vengono riproposti.

**Files:**
- Modify: `backend/app/services/discovery_dig.py` (`DiscoveryLead`, `_lead_from_release:184-219`)
- Test: `backend/tests/test_discovery_dig.py`

**Interfaces:**
- Consumes: `_norm` da `app.services.discovery`.
- Produces:
  - `_clean_artist(raw: str) -> tuple[str, list[str]]` — (stringa da mostrare, chiavi normalizzate per il match).
  - `DiscoveryLead.artist_keys: list[str]` — interno al motore, **non** nel DTO.
  - `DiscoveryLead.styles: list[str]` sostituisce `style: str | None`.

- [ ] **Step 1: Write the failing test**

```python
def test_clean_artist_strips_discogs_disambiguation():
    # Discogs marca gli omonimi: Tyree* non e' un artista diverso da Tyree
    assert _clean_artist("Tyree*") == ("Tyree", ["tyree"])
    assert _clean_artist("Gravity Zero (4)") == ("Gravity Zero", ["gravity zero"])


def test_clean_artist_splits_multi_artist_fields():
    display, keys = _clean_artist("Nail* / Einzelkind")
    assert display == "Nail / Einzelkind"          # niente cruft nella UI
    assert keys == ["nail / einzelkind", "nail", "einzelkind"]


def test_clean_artist_keeps_ampersand_names_matchable_whole():
    # 'Above & Beyond' e' UN artista: la chiave intera deve esserci per prima
    display, keys = _clean_artist("Above & Beyond")
    assert display == "Above & Beyond"
    assert keys[0] == "above & beyond"


def test_clean_artist_does_not_split_band_names():
    # 'Earth, Wind & Fire' e' UN artista: spezzarlo darebbe chiavi generiche
    # ('fire', 'wind') che agganciano la libreria per sbaglio. Si spezza solo sui
    # separatori non ambigui; su '&' e ',' si accetta di perdere il credito dello
    # split vero pur di non rischiare l'aggancio falso.
    assert _clean_artist("Earth, Wind & Fire")[1] == ["earth, wind & fire"]
    _, keys = _clean_artist("OPTML, Gravity Zero (4) & RADD (3)")
    assert keys == ["optml, gravity zero & radd"]   # suffissi puliti, nessuno split


def test_lead_carries_clean_artist_and_all_styles():
    item = _release("Tyree* - Acid Crash", rid=7)
    item["style"] = ["Acid House", "Chicago House"]
    lead = _lead_from_release(item, "Acid House")
    assert lead.artist == "Tyree"
    assert lead.artist_keys == ["tyree"]
    assert lead.styles == ["Acid House", "Chicago House"]
```

Aggiorna l'import: `from app.services.discovery_dig import _clean_artist, _lead_from_release, _window, dig`.

Il test esistente `test_lead_parsing_and_various_skipped` asserisce `lead.style == "Acid House"`: cambialo in `lead.styles == ["Acid House"]`.

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && source .venv/bin/activate && python -m pytest tests/test_discovery_dig.py -v -k "clean_artist or all_styles"
```
Expected: FAIL — `ImportError: cannot import name '_clean_artist'`.

- [ ] **Step 3: Implement**

In `discovery_dig.py`, accanto agli altri regex:

```python
# Grammatica di Discogs: gli omonimi sono disambiguati con '*' o '(N)' — 'Tyree*',
# 'Gravity Zero (4)'. Non sono parte del nome: senza toglierli, il 17% dei lead non
# aggancia la libreria (misurato su style=Acid House).
_DISCOGS_CRUFT_RE = re.compile(r"\*|\s*\(\d+\)")
# Piu' artisti in un campo: 'Nail / Einzelkind'. SOLO separatori non ambigui: '/' con
# spazi attorno e' la convenzione Discogs per gli split. '&' e ',' sono esclusi apposta:
# separano artisti ('Yen Sung & Photonz') ma stanno anche dentro i nomi di band
# ('Earth, Wind & Fire') e non c'e' modo di distinguerli. Meglio mancare un match (il
# lead resta piu' in basso) che agganciare per sbaglio (un disco che non c'entra va in
# cima): il secondo e' l'errore che l'utente vede. La chiave intera viene comunque prima.
_ARTIST_SPLIT_RE = re.compile(r"\s+(?:/|feat\.?|vs\.?)\s+", re.IGNORECASE)


def _clean_artist(raw: str) -> tuple[str, list[str]]:
    """(stringa da mostrare, chiavi normalizzate per il match).

    La chiave INTERA viene per prima: 'Above & Beyond' e' un artista solo e deve
    poter matchare per intero. Le parti seguono, per gli split veri
    ('Nail / Einzelkind': se collezioni Einzelkind, il lead e' rilevante).
    """
    display = _DISCOGS_CRUFT_RE.sub("", raw or "").strip()
    parts = [p.strip() for p in _ARTIST_SPLIT_RE.split(display) if p.strip()]
    keys = [_norm(display), *(_norm(p) for p in parts)]
    return display, [k for k in dict.fromkeys(keys) if k]
```

In `DiscoveryLead` sostituisci `style: str | None = None` con:

```python
    styles: list[str] = field(default_factory=list)   # TUTTI gli style della release
    artist_keys: list[str] = field(default_factory=list)  # interno: match, non DTO
```

In `_lead_from_release`, sostituisci il parsing dell'artista e la costruzione:

```python
    artist_raw, _, track_title = title.partition(" - ")
    artist_raw, track_title = artist_raw.strip(), track_title.strip()
    if not artist_raw or not track_title or artist_raw.lower() in _VARIOUS:
        return None
    artist, artist_keys = _clean_artist(artist_raw)
    if not artist or not artist_keys:
        return None
```

e nel `return DiscoveryLead(...)` sostituisci `artist=artist, ... style=_first(item.get("style")),` con:

```python
        artist=artist, artist_keys=artist_keys, title=track_title,
        styles=[str(s) for s in (item.get("style") or [])],
```

`_first` resta in uso per `label`.

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && source .venv/bin/activate && python -m pytest tests/test_discovery_dig.py -v
```
Expected: i nuovi test PASS. Altri test falliranno ancora (`_score`/`TasteProfile` usano `lead.style`): li sistemano i Task 4 e 6. Se il modulo non importa, correggi i riferimenti a `.style` rimasti — l'attributo non esiste più.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/discovery_dig.py backend/tests/test_discovery_dig.py
git commit -m "feat(dig): normalizza la grammatica Discogs negli artisti (suffissi, split)"
```

---

### Task 4: `TasteProfile` — un gusto che discrimina

`style_affinity` fa match su **un solo token condiviso** contro un'**unione** di tutti i token della libreria: per un DJ house basta `house` per valere 1.0 su quasi tutto. `W_STYLE = 0.2` è peso morto e il badge "stile che ascolti" compare ovunque.

**Files:**
- Modify: `backend/app/services/discovery_dig.py:145-181` (`TasteProfile`)
- Test: `backend/tests/test_discovery_dig.py`

**Interfaces:**
- Consumes: `_style_tokens`, `_norm`, `_clean_artist` (Task 3).
- Produces:
  - `TasteProfile.genre_sets: list[set[str]]` sostituisce `genre_tokens: set[str]`.
  - `TasteProfile.style_affinity(styles: list[str]) -> float` — Jaccard massima, 0..1.
  - `TasteProfile.familiarity(artist_keys: list[str]) -> float` — massima tra le chiavi.
  - `TasteProfile.artist_count(artist_keys: list[str]) -> int` — massimo tra le chiavi.

- [ ] **Step 1: Write the failing test**

```python
def test_style_affinity_is_graduated_not_binary():
    p = TasteProfile.from_tracks(_lib(("A", "T", {"genre": "Deep House"})))
    assert p.style_affinity(["Deep House"]) == 1.0
    # {house} / {deep, house, acid} — un token condiviso NON vale 1.0
    assert p.style_affinity(["Acid House"]) == pytest.approx(1 / 3)
    assert p.style_affinity(["Drum n Bass"]) == 0.0


def test_style_affinity_uses_all_release_styles():
    p = TasteProfile.from_tracks(_lib(("A", "T", {"genre": "Chicago House"})))
    assert p.style_affinity(["Acid House", "Chicago House"]) == 1.0


def test_style_affinity_compares_per_genre_not_against_a_single_bag():
    # Regressione col valore PUNTUALE, non `< 1.0`: per-genere la Jaccard massima e'
    # contro 'Deep House' -> {house}/{acid,deep,house} = 1/3. Col sacco unico
    # {deep,house,drum,n,bass} sarebbe {house}/{acid,deep,house,drum,n,bass} = 1/6 —
    # che passerebbe `< 1.0`. Un test di regressione deve distinguere i due.
    p = TasteProfile.from_tracks(_lib(
        ("A", "T1", {"genre": "Deep House"}),
        ("B", "T2", {"genre": "Drum n Bass"}),
    ))
    assert p.style_affinity(["Acid House"]) == pytest.approx(1 / 3)


def test_familiarity_is_max_across_split_artists():
    p = TasteProfile.from_tracks(_lib(("Einzelkind", "T1"), ("Einzelkind", "T2"),
                                      ("Einzelkind", "T3")))
    _, keys = _clean_artist("Nail* / Einzelkind")
    assert p.familiarity(keys) == 1.0        # 3 tracce = familiarita' piena
    assert p.familiarity(["sconosciuto"]) == 0.0


def test_familiarity_is_graduated():
    p = TasteProfile.from_tracks(_lib(("Tyree", "T1")))
    assert p.familiarity(["tyree"]) == pytest.approx(1 / 3)
```

Aggiungi `import pytest` e `TasteProfile` all'import del modulo.

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && source .venv/bin/activate && python -m pytest tests/test_discovery_dig.py -v -k "style_affinity or familiarity"
```
Expected: FAIL — `TypeError` (`style_affinity` prende una stringa, non una lista).

- [ ] **Step 3: Implement**

Sostituisci `TasteProfile` (`:145-181`):

```python
@dataclass
class TasteProfile:
    """Riassunto deterministico del gusto di un riferimento (libreria o playlist).

    Costruito da una lista di Track-like (servono artist, label, genre).
    Indipendente dalla dedup: misura affinita', non possesso.
    """
    artist_counts: dict[str, int] = field(default_factory=dict)
    owned_labels: set[str] = field(default_factory=set)
    # Un set di token PER GENERE DISTINTO, non un'unione: contro un sacco unico
    # bastava 'house' per valere 1.0 su qualunque release house.
    genre_sets: list[set[str]] = field(default_factory=list)

    @classmethod
    def from_tracks(cls, tracks: list) -> "TasteProfile":
        artist_counts: dict[str, int] = {}
        owned_labels: set[str] = set()
        genres: set[str] = set()
        for t in tracks or []:
            a = _norm(getattr(t, "artist", None))
            if a:
                artist_counts[a] = artist_counts.get(a, 0) + 1
            lbl = _norm(getattr(t, "label", None))
            if lbl:
                owned_labels.add(lbl)
            g = _norm(getattr(t, "genre", None))
            if g:
                genres.add(g)
        genre_sets = [toks for toks in map(_style_tokens, genres) if toks]
        return cls(artist_counts, owned_labels, genre_sets)

    def artist_count(self, artist_keys: list[str]) -> int:
        return max((self.artist_counts.get(k, 0) for k in artist_keys), default=0)

    def familiarity(self, artist_keys: list[str]) -> float:
        return min(self.artist_count(artist_keys) / FAMILIARITY_FULL_AT, 1.0)

    def label_affinity(self, label: str | None) -> float:
        return 1.0 if label and _norm(label) in self.owned_labels else 0.0

    def style_affinity(self, styles: list[str]) -> float:
        """Jaccard massima tra gli style della release e i generi della libreria.

        'Deep House' vs libreria con 'Deep House' -> 1.0; vs sola 'Acid House' -> 0.33
        ({house} / {deep, house, acid}); vs sola 'Drum n Bass' -> 0.0.
        """
        best = 0.0
        for s in (toks for toks in map(_style_tokens, styles or []) if toks):
            for g in self.genre_sets:
                best = max(best, len(s & g) / len(s | g))
        return best
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && source .venv/bin/activate && python -m pytest tests/test_discovery_dig.py -v -k "style_affinity or familiarity"
```
Expected: PASS (5 test).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/discovery_dig.py backend/tests/test_discovery_dig.py
git commit -m "feat(dig): affinita' di stile graduata (Jaccard per genere) e familiarita' sugli split"
```

---

### Task 5: Il possesso — release contro tracce

`owned_keys` confronta il **titolo della release** Discogs con `Track.title`, che è un titolo di **traccia**. Il 9% dei titoli del bacino è un nome di EP (`Piercing Love EP`), il 2% sono due tracce in un campo. Funziona per i 12" in cui la release prende il nome del lato A — cioè per caso. `Track.album` esiste (`models.py:80`) e non è mai usato.

**Files:**
- Modify: `backend/app/services/discovery_dig.py` (`_dedup_title:126-133`, `dig:309-331`)
- Test: `backend/tests/test_discovery_dig.py`

**Interfaces:**
- Consumes: `_clean_artist` (Task 3), `_dedup_title`, `_norm`.
- Produces:
  - `_title_candidates(title: str) -> list[str]`
  - `_owned_index(library: list) -> tuple[set[tuple[str, str]], set[tuple[str, str]]]` — (tracce, album)
  - `_is_owned(lead: DiscoveryLead, owned_tracks: set, owned_albums: set) -> bool`

- [ ] **Step 1: Write the failing test**

Aggiorna prima lo helper `_lib` in cima al file, che oggi non conosce `album`:

```python
def _lib(*items):
    """Track finte. Ogni item: (artist, title) o (artist, title, {"label":..., "genre":..., "album":...})."""
    out = []
    for it in items:
        extra = it[2] if len(it) > 2 else {}
        out.append(SimpleNamespace(
            artist=it[0], title=it[1],
            label=extra.get("label"), genre=extra.get("genre"),
            album=extra.get("album"),
        ))
    return out
```

Poi aggiungi:

```python
def test_title_candidates_covers_format_suffix_and_splits():
    assert "Piercing Love" in _title_candidates("Piercing Love EP")
    assert "Sentipede" in _title_candidates("Sentipede / 808 Rhythm Traxx 3")
    assert "Acid Trax" in _title_candidates("Acid Trax (Original Mix)")


def test_owned_via_discogs_cruft_artist():
    # regressione: possiedi Tyree, Discogs lo chiama Tyree* -> te lo riproponeva
    tracks, albums = _owned_index(_lib(("Tyree", "Acid Crash")))
    lead = _lead_from_release(_release("Tyree* - Acid Crash", rid=1), "x")
    assert _is_owned(lead, tracks, albums) is True


def test_owned_via_album_when_release_is_an_ep():
    tracks, albums = _owned_index(_lib(("Fabien D'Estival", "Some Track",
                                        {"album": "Piercing Love EP"})))
    lead = _lead_from_release(_release("Fabien D'Estival - Piercing Love EP", rid=1), "x")
    assert _is_owned(lead, tracks, albums) is True


def test_owned_via_one_side_of_a_split_title():
    tracks, albums = _owned_index(_lib(("Nail", "Sentipede")))
    lead = _lead_from_release(_release("Nail* / Einzelkind - Sentipede / 808 Rhythm Traxx 3", rid=1), "x")
    assert _is_owned(lead, tracks, albums) is True


def test_not_owned_stays_not_owned():
    tracks, albums = _owned_index(_lib(("Tyree", "Acid Crash")))
    lead = _lead_from_release(_release("Armando - Land Of Confusion", rid=1), "x")
    assert _is_owned(lead, tracks, albums) is False
```

Estendi l'import con `_is_owned, _owned_index, _title_candidates`.

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && source .venv/bin/activate && python -m pytest tests/test_discovery_dig.py -v -k "title_candidates or owned"
```
Expected: FAIL — `ImportError: cannot import name '_title_candidates'`.

- [ ] **Step 3: Implement**

Accanto a `_VARIANT_RE`:

```python
# Suffisso di FORMATO: il titolo di una release Discogs e' spesso il nome di un EP/LP,
# mentre Track.title e' il titolo di una TRACCIA. Senza toglierlo, 'Piercing Love EP'
# non riconosce la traccia 'Piercing Love' che possiedi.
_FORMAT_SUFFIX_RE = re.compile(r"\s+(?:ep|lp|12\"|single)\s*$", re.IGNORECASE)
```

Dopo `_dedup_key`:

```python
def _title_candidates(title: str) -> list[str]:
    """Tutti i titoli sotto cui una release puo' essere gia' in libreria.

    Il titolo di una release non e' il titolo di una traccia: puo' essere un EP
    ('Piercing Love EP') o due lati in un campo ('Sentipede / 808 Rhythm Traxx 3').
    """
    sides = [s.strip() for s in title.split(" / ")] if " / " in title else []
    out: list[str] = []
    for raw in [title, *sides]:
        t = _dedup_title(raw)
        out.append(t)
        stripped = _FORMAT_SUFFIX_RE.sub("", t).strip()
        if stripped:
            out.append(stripped)
    return [x for x in dict.fromkeys(out) if x]


def _owned_index(library: list) -> tuple[set[tuple[str, str]], set[tuple[str, str]]]:
    """Due indici del posseduto: per titolo di traccia e per album.

    Gli artisti della libreria vengono da tag/streaming: niente grammatica Discogs
    da ripulire, `_norm` basta.
    """
    tracks: set[tuple[str, str]] = set()
    albums: set[tuple[str, str]] = set()
    for t in library or []:
        a = _norm(getattr(t, "artist", None))
        if not a:
            continue
        if getattr(t, "title", None):
            tracks.add((a, _norm(_dedup_title(t.title))))
        if getattr(t, "album", None):
            albums.add((a, _norm(_dedup_title(t.album))))
    return tracks, albums


def _is_owned(lead: DiscoveryLead, owned_tracks: set, owned_albums: set) -> bool:
    """Un falso positivo costa un lead in meno; un falso negativo mostra all'utente
    un disco che ha gia'. Il secondo e' l'errore che si vede: si preferisce escludere.
    """
    for a in lead.artist_keys:
        for t in _title_candidates(lead.title):
            k = (a, _norm(t))
            if k in owned_tracks or k in owned_albums:
                return True
    return False
```

In `dig()`, sostituisci la riga `owned_keys = {...}` (`:311`) con `owned_tracks, owned_albums = _owned_index(library)` e, nel loop, sostituisci il blocco:

```python
        k = _dedup_key(lead.artist_keys[0], lead.title)  # collassa varianti e pressature
        if k in seen or _is_owned(lead, owned_tracks, owned_albums):
            continue
        seen.add(k)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && source .venv/bin/activate && python -m pytest tests/test_discovery_dig.py -v -k "title_candidates or owned"
```
Expected: PASS (5 test).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/discovery_dig.py backend/tests/test_discovery_dig.py
git commit -m "feat(dig): possesso su titolo di release vs traccia e album"
```

---

### Task 6: Il punteggio è solo gusto

Dentro una finestra di 3 pagine il `want` è ~costante (pagina 30: mediana 287, minimo 284): `demand` non ordina nulla al suo interno. E `novelty` ha un'escursione di **0,161 sull'intera pagina** (mediana 0,997): `_HAVE_CAP = 5000` è tarato per un intervallo che i dati non occupano. Il termine `discovery` sparisce; resta il gusto, sempre attivo.

**Files:**
- Modify: `backend/app/services/discovery_dig.py:241-256` (`_score`), `:63-68` (pesi)
- Test: `backend/tests/test_discovery_dig.py`

**Interfaces:**
- Consumes: `TasteProfile` (Task 4).
- Produces:
  - `Weights` (dataclass frozen: `artist: float`, `label: float`, `style: float`)
  - `_weights(seed_type: str) -> Weights`
  - `_score(lead: DiscoveryLead, profile: TasteProfile, weights: Weights) -> float`

- [ ] **Step 1: Write the failing test**

```python
def test_weights_drop_the_label_signal_on_a_label_dig():
    # su un dig per etichetta TUTTI i lead hanno l'etichetta del seme: costante, non ordina
    w = _weights("label")
    assert w.label == 0.0
    assert w.artist + w.style == pytest.approx(1.0)   # il peso si redistribuisce
    g = _weights("genre")
    assert (g.artist, g.label, g.style) == (0.5, 0.3, 0.2)


def test_score_is_taste_only():
    profile = TasteProfile.from_tracks(_lib(("Tyree", "T1"), ("Tyree", "T2"), ("Tyree", "T3")))
    mine = _lead_from_release(_release("Tyree - New One", have=9999, want=0, year=1990, rid=1), "x")
    other = _lead_from_release(_release("Sconosciuto - Rare One", have=1, want=999, year=2026, rid=2), "x")
    w = _weights("genre")
    # have/want/anno non entrano piu' nel punteggio: solo il gusto ordina
    assert _score(mine, profile, w) > _score(other, profile, w)


def test_score_ignores_year():
    profile = TasteProfile.from_tracks(_lib(("Tyree", "T1")))
    old = _lead_from_release(_release("Tyree - A", year=1988, rid=1), "x")
    new = _lead_from_release(_release("Tyree - B", year=2026, rid=2), "x")
    assert _score(old, profile, _weights("genre")) == _score(new, profile, _weights("genre"))
```

(La stabilità del sort a gusto piatto si verifica end-to-end nel Task 8, dove `dig()`
accetta `depth`: qui `_score` da solo non la esercita.)

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && source .venv/bin/activate && python -m pytest tests/test_discovery_dig.py -v -k "weights or score_is_taste or ignores_year"
```
Expected: FAIL — `ImportError: cannot import name '_weights'`.

- [ ] **Step 3: Implement**

Rimuovi `_HAVE_CAP` dalle costanti (non serve più a nessuno) e sostituisci `_score` (`:241-256`):

```python
@dataclass(frozen=True)
class Weights:
    artist: float
    label: float
    style: float


def _weights(seed_type: str) -> Weights:
    """I segnali costanti per costruzione escono, e il peso si redistribuisce.

    Su un dig per etichetta ogni lead ha l'etichetta del seme: `label_affinity` vale
    1.0 per tutti. E' una costante additiva — non ordina, e dilava gli altri segnali.
    Su un dig per genere invece Discogs restituisce PIU' style per release, quindi lo
    style del seme non e' l'unico e `style_affinity` conserva potere discriminante.
    """
    if seed_type == "label":
        rest = W_ARTIST + W_STYLE
        return Weights(artist=W_ARTIST / rest, label=0.0, style=W_STYLE / rest)
    return Weights(artist=W_ARTIST, label=W_LABEL, style=W_STYLE)


def _score(lead: DiscoveryLead, profile: TasteProfile, weights: Weights) -> float:
    """Solo gusto. La domanda l'ha gia' codificata la finestra (`_window`): dentro una
    finestra il `want` e' ~costante, quindi non ordina. La profondita' sceglie il
    bacino, il gusto ordina — sempre, non come modalita'.
    """
    return (
        weights.artist * profile.familiarity(lead.artist_keys)
        + weights.label * profile.label_affinity(lead.label)
        + weights.style * profile.style_affinity(lead.styles)
    )
```

`_demand` e `_recency` **restano**: le usa ancora `_reasons` (Task 7).

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && source .venv/bin/activate && python -m pytest tests/test_discovery_dig.py -v -k "weights or score_is_taste or ignores_year"
```
Expected: PASS (3 test).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/discovery_dig.py backend/tests/test_discovery_dig.py
git commit -m "feat(dig): il punteggio e' solo gusto — via novelty, demand e recency"
```

---

### Task 7: I reason dicono il vero

`deep_cut` scatta sul **63% dei lead** (misurato): un badge su due terzi della lista non informa. E su un dig per etichetta `label_followed` compare su ogni card, informando zero.

**Files:**
- Modify: `backend/app/services/discovery_dig.py:70-74` (soglie), `:259-275` (`_reasons`)
- Test: `backend/tests/test_discovery_dig.py`

**Interfaces:**
- Consumes: `Weights`/`_weights` (Task 6), `TasteProfile` (Task 4).
- Produces: `_reasons(lead: DiscoveryLead, profile: TasteProfile, seed_type: str, current_year: int) -> list[Reason]`; costanti `REASON_DEEP_CUT_MIN_WANT = 5`, `REASON_STYLE_MATCH_MIN = 0.5`.

- [ ] **Step 1: Write the failing test**

```python
def _codes(lead, profile, seed_type="genre", year=2026):
    return {r.code for r in _reasons(lead, profile, seed_type, year)}


def test_deep_cut_requires_demand():
    p = TasteProfile.from_tracks([])
    # nessuno lo ha E nessuno lo cerca: non e' una gemma, e' rumore
    assert "deep_cut" not in _codes(_lead_from_release(_release("A - T", have=10, want=0, rid=1), "x"), p)
    assert "deep_cut" in _codes(_lead_from_release(_release("A - T", have=10, want=5, rid=2), "x"), p)
    assert "deep_cut" not in _codes(_lead_from_release(_release("A - T", have=200, want=50, rid=3), "x"), p)


def test_label_followed_not_emitted_on_a_label_dig():
    p = TasteProfile.from_tracks(_lib(("X", "Y", {"label": "Lbl"})))
    lead = _lead_from_release(_release("A - T", label="Lbl", rid=1), "Lbl")
    assert "label_followed" in _codes(lead, p, seed_type="genre")
    # su un dig per etichetta ce l'hanno TUTTI: informa zero
    assert "label_followed" not in _codes(lead, p, seed_type="label")


def test_style_match_needs_more_than_one_shared_token():
    p = TasteProfile.from_tracks(_lib(("A", "T", {"genre": "Deep House"})))
    exact = _lead_from_release(_release("A - T", style="Deep House", rid=1), "x")
    loose = _lead_from_release(_release("A - T", style="Acid House", rid=2), "x")
    assert "style_match" in _codes(exact, p)
    assert "style_match" not in _codes(loose, p)   # 0.33 < soglia 0.5


def test_recent_badge_survives_even_though_year_left_the_score():
    p = TasteProfile.from_tracks([])
    assert "recent" in _codes(_lead_from_release(_release("A - T", year=2025, rid=1), "x"), p, year=2026)
    assert "recent" not in _codes(_lead_from_release(_release("A - T", year=1988, rid=2), "x"), p, year=2026)
```

Estendi l'import con `_reasons`.

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && source .venv/bin/activate && python -m pytest tests/test_discovery_dig.py -v -k "deep_cut or label_followed or style_match or recent_badge"
```
Expected: FAIL — `TypeError: _reasons() takes 3 positional arguments but 4 were given`.

- [ ] **Step 3: Implement**

Nel blocco soglie (`:70-74`) aggiungi:

```python
REASON_DEEP_CUT_MIN_WANT = 5    # sotto, non c'e' domanda misurabile: rumore, non gemma
REASON_STYLE_MATCH_MIN = 0.5    # soglia sulla Jaccard: un token condiviso non basta
```

Sostituisci `_reasons`:

```python
def _reasons(lead: DiscoveryLead, profile: TasteProfile, seed_type: str,
             current_year: int) -> list[Reason]:
    """Badge a soglia, deterministici. NON sono i fattori del punteggio: sono calcolati
    a parte e non spiegano la posizione del lead in lista.
    """
    out: list[Reason] = []
    if lead.want >= REASON_RARE_MIN_WANT and _demand(lead.have, lead.want) >= REASON_RARE_MIN_DEMAND:
        out.append(Reason("rare_wanted", {"have": lead.have, "want": lead.want}))
    if lead.have <= REASON_DEEP_CUT_MAX_HAVE and lead.want >= REASON_DEEP_CUT_MIN_WANT:
        out.append(Reason("deep_cut", {"have": lead.have}))
    # su un dig per etichetta il badge ce l'avrebbero tutti: non emesso
    if seed_type != "label" and profile.label_affinity(lead.label) > 0:
        out.append(Reason("label_followed", {"label": lead.label}))
    count = profile.artist_count(lead.artist_keys)
    if count > 0:
        out.append(Reason("artist_collected", {"artist": lead.artist, "count": count}))
    if profile.style_affinity(lead.styles) >= REASON_STYLE_MATCH_MIN:
        out.append(Reason("style_match", {"style": lead.styles[0] if lead.styles else None}))
    if _recency(lead.year, current_year) >= REASON_RECENT_MIN:
        out.append(Reason("recent", {"year": lead.year}))
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && source .venv/bin/activate && python -m pytest tests/test_discovery_dig.py -v -k "deep_cut or label_followed or style_match or recent_badge"
```
Expected: PASS (4 test).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/discovery_dig.py backend/tests/test_discovery_dig.py
git commit -m "fix(dig): i reason smettono di scattare su tutto (deep_cut, label, style)"
```

---

### Task 8: `dig()` — il wiring del ribaltamento

**Files:**
- Modify: `backend/app/services/discovery_dig.py:106-110` (`DigResult`), `:293-341` (`dig`), docstring del modulo `:1-13`
- Test: `backend/tests/test_discovery_dig.py`

**Interfaces:**
- Consumes: tutto dai Task 1–7.
- Produces:
  - `DigResult.pile_pages: int`
  - `dig(db, *, seed_type: str, value: str, search_releases: SearchReleases, count_releases: CountReleases, library: list | None = None, taste_tracks: list | None = None, depth: float = 0.0, limit: int = DEFAULT_DIG_LIMIT) -> DigResult`
  - `CountReleases = Callable[..., int]`

- [ ] **Step 1: Write the failing test**

```python
def test_dig_picks_the_window_from_depth():
    seen = {}

    def search(**kw):
        seen.update(kw)
        return [_release("A - T", rid=1)]

    dig(None, seed_type="genre", value="Acid House", search_releases=search,
        count_releases=lambda **kw: 43345, library=[], depth=1.0)
    assert seen["pages"] == [98, 99, 100]
    assert seen["sort"] == "want" and seen["sort_order"] == "desc"
    assert seen["style"] == "Acid House"


def test_dig_reports_pile_pages():
    res = dig(None, seed_type="label", value="Piccola", search_releases=lambda **kw: [],
              count_releases=lambda **kw: 150, library=[], depth=0.5)
    assert res.pile_pages == 2       # 150 release = 2 pagine: niente profondita' da scegliere


def test_dig_genre_falls_back_to_genre_when_style_is_empty():
    probes = []

    def count(**kw):
        probes.append(kw)
        return 0 if "style" in kw else 500

    seen = {}

    def search(**kw):
        seen.update(kw)
        return []

    dig(None, seed_type="genre", value="Electronic", search_releases=search,
        count_releases=count, library=[], depth=0.0)
    assert "style" in probes[0] and "genre" in probes[1]
    assert seen.get("genre") == "Electronic" and "style" not in seen


def test_dig_empty_pile_makes_no_search_call():
    called = []

    dig(None, seed_type="label", value="Inesistente",
        search_releases=lambda **kw: called.append(kw) or [],
        count_releases=lambda **kw: 0, library=[], depth=0.0)
    assert called == []      # pila vuota: niente da scaricare, niente richieste sprecate


def test_flat_taste_preserves_pile_order():
    # libreria vuota: il sort stabile deve conservare l'ordine per domanda della pila.
    # E' il fallback giusto e gratuito: senza gusto, resta l'ordine di desiderabilita'.
    def search(**kw):
        return [_release("A1 - T1", rid=1), _release("A2 - T2", rid=2), _release("A3 - T3", rid=3)]

    res = dig(None, seed_type="genre", value="Acid House",
              search_releases=search, count_releases=lambda **kw: 300,
              library=[], depth=0.0)
    assert [lead.discogs_id for lead in res.leads] == [1, 2, 3]


def test_dig_excludes_owned_and_ranks_by_taste():
    def search(**kw):
        return [
            _release("Sconosciuto - Rare One", rid=1),
            _release("Tyree* - Owned Track", rid=2),     # gia' in libreria: fuori
            _release("Tyree* - New Track", rid=3),       # artista che collezioni: primo
        ]

    res = dig(None, seed_type="genre", value="Acid House", search_releases=search,
              count_releases=lambda **kw: 300,
              library=_lib(("Tyree", "Owned Track"), ("Tyree", "Other"), ("Tyree", "More")),
              depth=0.0)
    assert [lead.discogs_id for lead in res.leads] == [3, 1]
    assert res.leads[0].artist == "Tyree"     # niente cruft Discogs nella UI
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && source .venv/bin/activate && python -m pytest tests/test_discovery_dig.py -v -k "picks_the_window or pile_pages or falls_back or empty_pile"
```
Expected: FAIL — `TypeError: dig() got an unexpected keyword argument 'count_releases'`.

- [ ] **Step 3: Implement**

Aggiungi accanto a `SearchReleases`:

```python
CountReleases = Callable[..., int]
```

In `DigResult` aggiungi `pile_pages: int = 0`.

Sostituisci `dig` (`:293-341`):

```python
def dig(
    db: Session,
    *,
    seed_type: str,
    value: str,
    search_releases: SearchReleases,
    count_releases: CountReleases,
    library: list | None = None,
    taste_tracks: list | None = None,
    depth: float = 0.0,
    limit: int = DEFAULT_DIG_LIMIT,
) -> DigResult:
    """Lead non posseduti dal seme dato (genere|etichetta), ordinati per gusto.

    Due assi separati: `depth` sceglie DOVE pescare nella pila ordinata per domanda
    (0 = i classici del seme, 1 = il fondo); il gusto ordina SEMPRE dentro la finestra.

    Dedup sempre su tutta la `library`; l'affinita' di gusto usa `taste_tracks`
    (default: la libreria stessa), che puo' essere una playlist specifica.
    """
    if library is None:
        library = _library_tracks(db)
    owned_tracks, owned_albums = _owned_index(library)
    profile = TasteProfile.from_tracks(library if taste_tracks is None else taste_tracks)

    if seed_type == "label":
        filters: dict[str, Any] = {"label": value}
    elif seed_type == "genre":
        # Discogs distingue `style` (fine: 'Deep House') da `genre` (grosso:
        # 'Electronic'): si prova il piu' specifico e si ripiega.
        filters = {"style": value}
    else:
        return DigResult(seed_type=seed_type, value=value, pile_pages=0)

    total = count_releases(**filters)
    if total == 0 and seed_type == "genre":
        filters = {"genre": value}
        total = count_releases(**filters)

    usable = min(math.ceil(total / SEARCH_PER_PAGE), DISCOGS_MAX_PAGES) if total > 0 else 0
    pages = _window(depth, total)
    if not pages:
        return DigResult(seed_type=seed_type, value=value, pile_pages=0)

    items = search_releases(**filters, pages=pages, sort=SORT_WANT, sort_order=SORT_DESC)

    leads: list[DiscoveryLead] = []
    seen: set[tuple[str, str]] = set()
    for item in items or []:
        lead = _lead_from_release(item, value)
        if lead is None:
            continue
        k = _dedup_key(lead.artist_keys[0], lead.title)  # collassa varianti e pressature
        if k in seen or _is_owned(lead, owned_tracks, owned_albums):
            continue
        seen.add(k)
        leads.append(lead)

    weights = _weights(seed_type)
    current_year = datetime.now(timezone.utc).year
    for lead in leads:
        lead.score = _score(lead, profile, weights)
        lead.reasons = _reasons(lead, profile, seed_type, current_year)
    selected = _select(leads, limit)

    logger.info("Discovery dig %s=%r: %s lead (depth=%.2f, pagine %s di %s)",
                seed_type, value, len(selected), depth, pages, usable)
    return DigResult(seed_type=seed_type, value=value, leads=selected, pile_pages=usable)
```

In `_select` (`:283`), sostituisci `a = _norm(lead.artist)` con `a = lead.artist_keys[0]`.

Aggiorna la docstring del modulo (`:1-13`): il dig non ordina più "per profondita' + novita'", ordina **per gusto** dentro una finestra scelta da `depth`.

- [ ] **Step 4: Run the whole backend suite**

```bash
cd backend && source .venv/bin/activate && python -m pytest tests/test_discovery_dig.py -v
```
Expected: PASS, incluso `test_flat_taste_preserves_pile_order` del Task 6. I test preesistenti che passavano `adventurousness=` vanno aggiornati a `depth=` e devono ora passare anche `count_releases=`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/discovery_dig.py backend/tests/test_discovery_dig.py
git commit -m "feat(dig): depth sceglie la finestra, il gusto ordina, pile_pages in uscita"
```

---

### Task 9: Il contratto API

**Files:**
- Modify: `backend/app/schemas.py:527-543`, `backend/app/routers/discovery.py:216-224` (`_lead_out`), `:237-263` (`dig_endpoint`)
- Test: `backend/tests/test_discovery_router_http.py`

**Interfaces:**
- Consumes: `dig(..., depth=, count_releases=)` e `DigResult.pile_pages` (Task 8).
- Produces: `DiscoveryDigRequest.depth: float`, `DiscoveryDigResponse.pile_pages: int`.

- [ ] **Step 1: Write the failing test**

In `backend/tests/test_discovery_router_http.py` (imita lo stile già presente nel file per il client di test e il monkeypatch di `DiscogsClient`):

```python
def test_dig_endpoint_accepts_depth_and_returns_pile_pages(client, monkeypatch):
    captured = {}

    class _FakeClient:
        def search_releases(self, **kw):
            captured.update(kw)
            return []

        def count_releases(self, **kw):
            return 43345

        def close(self):
            pass

    monkeypatch.setattr("app.routers.discovery.DiscogsClient", lambda: _FakeClient())
    r = client.post("/api/discovery/dig", json={"seed_type": "genre", "value": "Acid House", "depth": 1.0})
    assert r.status_code == 200
    assert r.json()["pile_pages"] == 100
    assert captured["pages"] == [98, 99, 100]


def test_dig_endpoint_depth_defaults_to_the_canon(client, monkeypatch):
    captured = {}

    class _FakeClient:
        def search_releases(self, **kw):
            captured.update(kw)
            return []

        def count_releases(self, **kw):
            return 43345

        def close(self):
            pass

    monkeypatch.setattr("app.routers.discovery.DiscogsClient", lambda: _FakeClient())
    r = client.post("/api/discovery/dig", json={"seed_type": "genre", "value": "Acid House"})
    assert r.status_code == 200
    assert captured["pages"] == [1, 2, 3]     # default depth=0.0: i classici


def test_dig_endpoint_rejects_out_of_range_depth(client):
    r = client.post("/api/discovery/dig", json={"seed_type": "genre", "value": "x", "depth": 1.5})
    assert r.status_code == 422
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && source .venv/bin/activate && python -m pytest tests/test_discovery_router_http.py -v -k depth
```
Expected: FAIL — la risposta non ha `pile_pages`.

- [ ] **Step 3: Implement**

In `schemas.py`:

```python
class DiscoveryDigRequest(BaseModel):
    seed_type: Literal["genre", "label"]
    value: str = Field(min_length=1)
    # DOVE pescare nella pila ordinata per domanda: 0 = i classici del seme,
    # 1 = il fondo della cassa. Non e' un mix di ordinamento: sceglie il bacino.
    depth: float = Field(default=0.0, ge=0.0, le=1.0)
    limit: int = Field(default=80, ge=1, le=200)
    taste_playlist_id: int | None = None  # riferimento di gusto; None = tutta la libreria


class DiscoveryDigResponse(BaseModel):
    seed_type: str
    value: str
    leads: list[DiscoveryLeadOut] = []
    # Quante pagine utili ha la pila del seme. Se <= 3 la finestra e' l'intera pila e
    # `depth` non ha effetto: la UI deve poterlo dire invece di offrire un controllo inerte.
    pile_pages: int = 0
```

In `routers/discovery.py`, dentro `dig_endpoint`:

```python
        result = dig(
            db, seed_type=req.seed_type, value=req.value,
            search_releases=lambda **kw: client.search_releases(**kw),
            count_releases=lambda **kw: client.count_releases(**kw),
            taste_tracks=taste_tracks,
            depth=req.depth, limit=req.limit,
        )
```

e nel `return`:

```python
    return DiscoveryDigResponse(
        seed_type=result.seed_type, value=result.value,
        leads=[_lead_out(lead) for lead in result.leads],
        pile_pages=result.pile_pages,
    )
```

In `_lead_out` (`:216-224`), il DTO espone `style` singolare: sostituisci `style=lead.style` con:

```python
        style=lead.styles[0] if lead.styles else None,
```

- [ ] **Step 4: Run the whole backend suite**

```bash
cd backend && source .venv/bin/activate && python -m pytest tests -q
```
Expected: tutti PASS. **Non proseguire finché la suite non è verde**: il frontend parte da qui.

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas.py backend/app/routers/discovery.py backend/tests/test_discovery_router_http.py
git commit -m "feat(api): dig accetta depth e restituisce pile_pages"
```

---

### Task 10: `Popover` nel design system

Le primitive mancanti sono la ragione per cui il pannello di Discovery è finito com'è: ogni pagina se le è ricostruite a mano.

**Files:**
- Modify: `frontend/components/ui.tsx`
- Test: `frontend/tests/ui-primitives.test.tsx` (crea)

**Interfaces:**
- Produces: `Popover({ trigger, children, open, onOpenChange, align }: { trigger: ReactNode; children: ReactNode; open?: boolean; onOpenChange?: (v: boolean) => void; align?: "start" | "end" })`

- [ ] **Step 1: Write the failing test**

Crea `frontend/tests/ui-primitives.test.tsx`:

```tsx
import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { Popover } from "@/components/ui";

describe("Popover", () => {
  it("apre sul trigger", () => {
    render(<Popover trigger={<span>apri</span>}><p>contenuto</p></Popover>);
    expect(screen.queryByText("contenuto")).toBeNull();
    fireEvent.click(screen.getByText("apri"));
    expect(screen.getByText("contenuto")).toBeTruthy();
  });

  it("chiude su Escape", () => {
    render(<Popover trigger={<span>apri</span>}><p>contenuto</p></Popover>);
    fireEvent.click(screen.getByText("apri"));
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByText("contenuto")).toBeNull();
  });

  it("chiude su click esterno", () => {
    render(
      <div>
        <Popover trigger={<span>apri</span>}><p>contenuto</p></Popover>
        <button>fuori</button>
      </div>,
    );
    fireEvent.click(screen.getByText("apri"));
    fireEvent.mouseDown(screen.getByText("fuori"));
    expect(screen.queryByText("contenuto")).toBeNull();
  });

  it("notifica il cambio di stato", () => {
    const onOpenChange = vi.fn();
    render(<Popover trigger={<span>apri</span>} onOpenChange={onOpenChange}><p>c</p></Popover>);
    fireEvent.click(screen.getByText("apri"));
    expect(onOpenChange).toHaveBeenCalledWith(true);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd frontend && npm run test:unit -- ui-primitives
```
Expected: FAIL — `Popover` non è esportato da `@/components/ui`.

Se `@testing-library/react` non è installato, verifica come fanno i test esistenti (`frontend/tests/player.test.tsx`) e allineati: **non aggiungere dipendenze** senza che servano davvero.

- [ ] **Step 3: Implement**

In `frontend/components/ui.tsx`, dopo `Field`:

```tsx
/* ---------------------------------------------------------------- Popover */

export function Popover({ trigger, children, open, onOpenChange, align = "start" }: {
  trigger: ReactNode;
  children: ReactNode;
  open?: boolean;
  onOpenChange?: (v: boolean) => void;
  align?: "start" | "end";
}) {
  const [uncontrolled, setUncontrolled] = useState(false);
  const isOpen = open ?? uncontrolled;
  const ref = useRef<HTMLDivElement>(null);

  const set = useCallback((v: boolean) => {
    if (open === undefined) setUncontrolled(v);
    onOpenChange?.(v);
  }, [open, onOpenChange]);

  useEffect(() => {
    if (!isOpen) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") set(false); };
    const onDown = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node)) set(false);
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onDown);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onDown);
    };
  }, [isOpen, set]);

  return (
    <div ref={ref} className="relative inline-block">
      <div onClick={() => set(!isOpen)}>{trigger}</div>
      {isOpen && (
        <div
          className={cn(
            // The Hairline Rule: filetto, niente ombra, niente radius.
            "absolute top-full z-30 mt-1 min-w-full border border-border-strong bg-surface",
            align === "end" ? "right-0" : "left-0",
          )}
        >
          {children}
        </div>
      )}
    </div>
  );
}
```

Aggiungi `useCallback`, `useEffect`, `useRef`, `useState` all'import di React in cima al file, se non ci sono già. Il file potrebbe essere un Server Component: se manca, aggiungi `"use client";` in cima (verifica prima — `ui.tsx` ha già componenti interattivi come `Checkbox`).

- [ ] **Step 4: Run test to verify it passes**

```bash
cd frontend && npm run test:unit -- ui-primitives
```
Expected: PASS (4 test).

- [ ] **Step 5: Commit**

```bash
git add frontend/components/ui.tsx frontend/tests/ui-primitives.test.tsx
git commit -m "feat(ds): Popover — filetto, niente ombra, chiusura su Escape e click esterno"
```

---

### Task 11: `SegmentedControl` e `Chip` nel design system

Il pattern del segmented control è copiato **tre volte** (`page.tsx:175-193`, `page.tsx:261-278`, `discovery-lead-grid.tsx:82-96`); `Chip` è definito localmente e non esportato in `page.tsx:336-353`, e duplicato in `discovery-lead-grid.tsx:65-80`.

**Files:**
- Modify: `frontend/components/ui.tsx`
- Test: `frontend/tests/ui-primitives.test.tsx`

**Interfaces:**
- Produces:
  - `SegmentedControl<T extends string>({ value, onChange, options, disabled }: { value: T; onChange: (v: T) => void; options: { value: T; label: ReactNode; icon?: ReactNode; title?: string }[]; disabled?: boolean })`
  - `Chip({ on, onClick, disabled, children }: { on?: boolean; onClick?: () => void; disabled?: boolean; children: ReactNode })`

- [ ] **Step 1: Write the failing test**

Aggiungi a `frontend/tests/ui-primitives.test.tsx`:

```tsx
import { Chip, SegmentedControl } from "@/components/ui";

describe("SegmentedControl", () => {
  const opts = [
    { value: "a" as const, label: "Alpha" },
    { value: "b" as const, label: "Beta" },
  ];

  it("marca l'opzione attiva con aria-pressed", () => {
    render(<SegmentedControl value="a" onChange={() => {}} options={opts} />);
    expect(screen.getByText("Alpha").closest("button")?.getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByText("Beta").closest("button")?.getAttribute("aria-pressed")).toBe("false");
  });

  it("notifica il valore scelto", () => {
    const onChange = vi.fn();
    render(<SegmentedControl value="a" onChange={onChange} options={opts} />);
    fireEvent.click(screen.getByText("Beta"));
    expect(onChange).toHaveBeenCalledWith("b");
  });

  it("disabled blocca il cambio", () => {
    const onChange = vi.fn();
    render(<SegmentedControl value="a" onChange={onChange} options={opts} disabled />);
    fireEvent.click(screen.getByText("Beta"));
    expect(onChange).not.toHaveBeenCalled();
  });
});

describe("Chip", () => {
  it("riflette lo stato attivo", () => {
    render(<Chip on onClick={() => {}}>Acid House</Chip>);
    expect(screen.getByText("Acid House").getAttribute("aria-pressed")).toBe("true");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd frontend && npm run test:unit -- ui-primitives
```
Expected: FAIL — `SegmentedControl` non esportato.

- [ ] **Step 3: Implement**

In `frontend/components/ui.tsx`, dopo `Popover`:

```tsx
/* ------------------------------------------------- SegmentedControl / Chip */

export function SegmentedControl<T extends string>({ value, onChange, options, disabled }: {
  value: T;
  onChange: (v: T) => void;
  options: { value: T; label: ReactNode; icon?: ReactNode; title?: string }[];
  disabled?: boolean;
}) {
  return (
    <div className="inline-flex border border-border bg-surface p-0.5">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          onClick={() => onChange(o.value)}
          aria-pressed={value === o.value}
          disabled={disabled}
          title={o.title}
          className={cn(
            "inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium transition-colors",
            value === o.value ? "bg-elevated text-fg" : "text-muted hover:text-fg",
            disabled && "cursor-not-allowed opacity-50",
          )}
        >
          {o.icon}
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function Chip({ on, onClick, disabled, children }: {
  on?: boolean; onClick?: () => void; disabled?: boolean; children: ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={on}
      disabled={disabled}
      className={cn(
        "border px-2.5 py-1 text-xs transition-colors",
        on ? "border-border-strong bg-elevated text-fg" : "border-border text-muted hover:text-fg",
        disabled && "cursor-not-allowed opacity-50",
      )}
    >
      {children}
    </button>
  );
}
```

Nota: `disabled` su `<button>` blocca già il click nel browser; il test lo verifica come contratto.

- [ ] **Step 4: Run test to verify it passes**

```bash
cd frontend && npm run test:unit -- ui-primitives && npm run lint
```
Expected: PASS (8 test), lint pulito.

- [ ] **Step 5: Commit**

```bash
git add frontend/components/ui.tsx frontend/tests/ui-primitives.test.tsx
git commit -m "feat(ds): SegmentedControl e Chip — via tre copie del pattern"
```

---

### Task 12: `Combobox` — un campo solo per generi ed etichette

Sostituisce il toggle seed + `Input`/`datalist` + chip + "+N altre". Il `seed_type` si deduce dal gruppo della voce scelta: sparisce l'asimmetria genere/etichetta.

**Files:**
- Modify: `frontend/components/ui.tsx`
- Test: `frontend/tests/ui-primitives.test.tsx`

**Interfaces:**
- Consumes: `Popover` (Task 10).
- Produces:
  - `type ComboOption = { value: string; label: string; group: string; icon?: ReactNode }`
  - `Combobox({ value, onChange, onSelect, options, placeholder, disabled, cap }: { value: string; onChange: (v: string) => void; onSelect: (o: ComboOption) => void; options: ComboOption[]; placeholder?: string; disabled?: boolean; cap?: number })`

- [ ] **Step 1: Write the failing test**

```tsx
import { Combobox, type ComboOption } from "@/components/ui";

const OPTS: ComboOption[] = [
  { value: "Acid House", label: "Acid House", group: "genere" },
  { value: "Acid Techno", label: "Acid Techno", group: "genere" },
  { value: "Trax Records", label: "Trax Records", group: "etichetta" },
];

function setup(value = "") {
  const onSelect = vi.fn();
  const onChange = vi.fn();
  render(<Combobox value={value} onChange={onChange} onSelect={onSelect} options={OPTS} />);
  return { onSelect, onChange };
}

describe("Combobox", () => {
  it("filtra per sottostringa, case-insensitive", () => {
    setup();
    const input = screen.getByRole("combobox");
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: "trax" } });
    expect(screen.getByText("Trax Records")).toBeTruthy();
    expect(screen.queryByText("Acid House")).toBeNull();
  });

  it("mostra generi ed etichette insieme, generi prima", () => {
    setup();
    fireEvent.focus(screen.getByRole("combobox"));
    const labels = screen.getAllByRole("option").map((o) => o.textContent ?? "");
    expect(labels[0]).toContain("Acid House");
    expect(labels[labels.length - 1]).toContain("Trax Records");
  });

  it("Enter sceglie l'opzione evidenziata e riporta il gruppo", () => {
    const { onSelect } = setup();
    const input = screen.getByRole("combobox");
    fireEvent.focus(input);
    fireEvent.keyDown(input, { key: "ArrowDown" });
    fireEvent.keyDown(input, { key: "ArrowDown" });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(onSelect).toHaveBeenCalledWith(expect.objectContaining({ value: "Acid Techno", group: "genere" }));
  });

  it("Escape chiude senza selezionare", () => {
    const { onSelect } = setup();
    const input = screen.getByRole("combobox");
    fireEvent.focus(input);
    fireEvent.keyDown(input, { key: "Escape" });
    expect(screen.queryByRole("option")).toBeNull();
    expect(onSelect).not.toHaveBeenCalled();
  });

  it("accetta testo libero non presente tra i suggerimenti", () => {
    const { onChange } = setup();
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "Genere Inventato" } });
    expect(onChange).toHaveBeenCalledWith("Genere Inventato");
  });

  it("cappa le voci visibili", () => {
    const many: ComboOption[] = Array.from({ length: 30 }, (_, i) => ({
      value: `g${i}`, label: `g${i}`, group: "genere",
    }));
    render(<Combobox value="" onChange={() => {}} onSelect={() => {}} options={many} cap={12} />);
    fireEvent.focus(screen.getAllByRole("combobox")[0]);
    expect(screen.getAllByRole("option").length).toBe(12);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd frontend && npm run test:unit -- ui-primitives
```
Expected: FAIL — `Combobox` non esportato.

- [ ] **Step 3: Implement**

In `frontend/components/ui.tsx`, dopo `Chip`:

```tsx
/* ---------------------------------------------------------------- Combobox */

export type ComboOption = { value: string; label: string; group: string; icon?: ReactNode };

export function Combobox({ value, onChange, onSelect, options, placeholder, disabled, cap = 12 }: {
  value: string;
  onChange: (v: string) => void;
  onSelect: (o: ComboOption) => void;
  options: ComboOption[];
  placeholder?: string;
  disabled?: boolean;
  cap?: number;
}) {
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);

  const matches = useMemo(() => {
    const q = value.trim().toLowerCase();
    const hit = q ? options.filter((o) => o.label.toLowerCase().includes(q)) : options;
    return hit.slice(0, cap);
  }, [value, options, cap]);

  const choose = (o: ComboOption) => {
    onSelect(o);
    setOpen(false);
    setActive(-1);
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Escape") { setOpen(false); setActive(-1); return; }
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      setOpen(true);
      setActive((i) => {
        const next = e.key === "ArrowDown" ? i + 1 : i - 1;
        return Math.max(0, Math.min(matches.length - 1, next));
      });
      return;
    }
    if (e.key === "Enter" && open && active >= 0 && matches[active]) {
      e.preventDefault();   // non fa partire il submit del form: prima si sceglie
      choose(matches[active]);
    }
  };

  return (
    <div className="relative w-full">
      <Input
        role="combobox"
        aria-expanded={open}
        aria-controls="combobox-list"
        aria-activedescendant={active >= 0 ? `combobox-opt-${active}` : undefined}
        autoComplete="off"
        value={value}
        disabled={disabled}
        placeholder={placeholder}
        onFocus={() => setOpen(true)}
        onChange={(e) => { onChange(e.target.value); setOpen(true); setActive(-1); }}
        onKeyDown={onKeyDown}
        onBlur={() => window.setTimeout(() => setOpen(false), 120)}
      />
      {open && matches.length > 0 && (
        <ul
          id="combobox-list"
          role="listbox"
          className="absolute left-0 top-full z-30 mt-1 max-h-64 w-full overflow-y-auto border border-border-strong bg-surface"
        >
          {matches.map((o, i) => (
            <li
              key={`${o.group}-${o.value}`}
              id={`combobox-opt-${i}`}
              role="option"
              aria-selected={i === active}
              onMouseDown={(e) => { e.preventDefault(); choose(o); }}
              onMouseEnter={() => setActive(i)}
              className={cn(
                "flex cursor-pointer items-center justify-between gap-3 px-3 py-1.5 text-sm",
                i === active ? "bg-elevated text-fg" : "text-muted",
              )}
            >
              <span className="flex items-center gap-2 truncate">{o.icon}{o.label}</span>
              <span className="shrink-0 text-[10px] uppercase tracking-wider text-faint">{o.group}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
```

Aggiungi `useMemo` all'import di React. **L'ordinamento dei gruppi non è compito del `Combobox`**: arriva già ordinato in `options` (Task 15). Verifica che `Input` inoltri le props extra (`role`, `aria-*`, `onKeyDown`) al `<input>` sottostante; se non lo fa, estendine il tipo di props — non duplicare l'input.

- [ ] **Step 4: Run test to verify it passes**

```bash
cd frontend && npm run test:unit -- ui-primitives && npm run lint
```
Expected: PASS (14 test).

- [ ] **Step 5: Commit**

```bash
git add frontend/components/ui.tsx frontend/tests/ui-primitives.test.tsx
git commit -m "feat(ds): Combobox — generi ed etichette in un campo solo"
```

---

### Task 13: Client API e tipi

**Files:**
- Modify: `frontend/lib/api/discovery.ts:31-43`, `frontend/lib/api/types.ts:120-152`
- Test: nessuno (tipi e passacarte; li copre il Task 18 in E2E)

**Interfaces:**
- Consumes: contratto del Task 9.
- Produces: `discoveryDig(body: { seed_type: "genre" | "label"; value: string; depth?: number; limit?: number; taste_playlist_id?: number | null }): Promise<DiscoveryDigResponse>`; `DiscoveryDigResponse.pile_pages: number`.

- [ ] **Step 1: Aggiorna il tipo**

In `frontend/lib/api/types.ts`, nella dichiarazione di `DiscoveryDigResponse`, aggiungi:

```ts
  /** Quante pagine utili ha la pila del seme. <= 3 => `depth` non ha effetto. */
  pile_pages: number;
```

- [ ] **Step 2: Aggiorna il client**

In `frontend/lib/api/discovery.ts`, in `discoveryDig`, rinomina il campo `adventurousness` in `depth` nel corpo della richiesta e nella firma. Il parametro `limit` resta supportato ma non usato dalla pagina.

- [ ] **Step 3: Verifica che compili**

```bash
cd frontend && npx tsc --noEmit
```
Expected: errori **solo** in `app/discovery/page.tsx` (usa ancora `adventurousness`). Li chiude il Task 16.

- [ ] **Step 4: Commit**

```bash
git add frontend/lib/api/discovery.ts frontend/lib/api/types.ts
git commit -m "feat(api-client): depth e pile_pages nel dig"
```

---

### Task 14: Le stringhe

**Files:**
- Modify: `frontend/lib/i18n/it.ts` (~560-600), `frontend/lib/i18n/en.ts` (~558-598)
- Test: nessuno diretto

**Interfaces:**
- Produces: le chiavi sotto `t.discovery` usate dai Task 15–17.

- [ ] **Step 1: Sostituisci il blocco `discovery` in `it.ts`**

Rimuovi: `startFromLabel`, `seedGenre`, `seedLabel`, `noLabels`, `showMore`, `showLess`, `genrePlaceholder` (sostituito). Aggiungi/modifica:

```ts
    dig: "Scava",
    digLabel: "Scava",
    subjectPlaceholder: "Genere o etichetta… es. Acid House, Trax Records",
    groupGenre: "genere",
    groupLabel: "etichetta",
    depthLabel: "Profondità",
    depthSurface: "Superficie",
    depthMid: "A metà",
    depthDeep: "In fondo",
    depthSurfaceDesc: "I dischi più cercati del seme, meno quelli che hai già.",
    depthMidDesc: "Più a fondo: meno noti, ancora molto cercati.",
    depthDeepDesc: "Il fondo della cassa: oscuri, ma qualcuno li cerca ancora.",
    shortPile: "pila corta: tutta qui",
    affinityLabel: "Gusto",
    wholeLibraryOption: "Tutta la libreria",
    affinityHint: "Rispetto a cosa misurare l'affinità. Non filtra: i dischi che hai già restano esclusi comunque.",
    leadCount: (n: number) => `${n} lead`,
    formatLabel: "Formato",
    formatAll: "Tutti",
    sortLabel: "Ordine",
    sortScore: "Rilevanza",
    sortRecent: "Recenti",
```

Mantieni invariate le chiavi già esistenti e ancora usate: `intro`, `digInProgress`, `readyTitle`, `readyBodyReady`, `readyBodyNotReady`, e tutte le `reason*`.

- [ ] **Step 2: Rispecchia in `en.ts`**

Stesse chiavi, stessa forma. Traduzioni:

```ts
    dig: "Dig",
    digLabel: "Dig",
    subjectPlaceholder: "Genre or label… e.g. Acid House, Trax Records",
    groupGenre: "genre",
    groupLabel: "label",
    depthLabel: "Depth",
    depthSurface: "Surface",
    depthMid: "Halfway",
    depthDeep: "Bottom",
    depthSurfaceDesc: "The most wanted records for this seed, minus the ones you own.",
    depthMidDesc: "Deeper: less known, still much wanted.",
    depthDeepDesc: "The bottom of the crate: obscure, but someone still wants them.",
    shortPile: "short pile: this is all of it",
    affinityLabel: "Taste",
    wholeLibraryOption: "Whole library",
    affinityHint: "What to measure affinity against. It filters nothing: records you own stay excluded anyway.",
    leadCount: (n: number) => `${n} leads`,
    formatLabel: "Format",
    formatAll: "All",
    sortLabel: "Order",
    sortScore: "Relevance",
    sortRecent: "Recent",
```

- [ ] **Step 3: Verifica che i due file abbiano le stesse chiavi**

```bash
cd frontend && npx tsc --noEmit 2>&1 | grep -i i18n || echo "i18n allineati"
```
Expected: "i18n allineati" (il tipo di `en` è derivato da `it`, o viceversa: una chiave mancante è un errore di tipo).

- [ ] **Step 4: Commit**

```bash
git add frontend/lib/i18n/it.ts frontend/lib/i18n/en.ts
git commit -m "feat(i18n): stringhe della riga di scavo (profondita' reale, gusto pari grado)"
```

---

### Task 15: `DiscoveryDigBar` — la riga di scavo

**Files:**
- Create: `frontend/components/discovery-dig-bar.tsx`
- Test: `frontend/tests/discovery-dig-bar.test.tsx` (crea)

**Interfaces:**
- Consumes: `Combobox`, `ComboOption`, `SegmentedControl`, `Button`, `Select`, `Spinner` da `@/components/ui`; `t.discovery.*` dal Task 14.
- Produces:
  - `export const DEPTHS: { key: "surface" | "mid" | "deep"; value: number }[]` — valori `0.0 / 0.5 / 1.0`.
  - `DiscoveryDigBar(props)` come sotto.

- [ ] **Step 1: Write the failing test**

Crea `frontend/tests/discovery-dig-bar.test.tsx`:

```tsx
import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { DiscoveryDigBar } from "@/components/discovery-dig-bar";

const OPTIONS = {
  genres: ["Acid House"],
  labels: ["Trax Records"],
  playlists: [{ id: 1, name: "Warmup" }],
};

function setup(over: Partial<React.ComponentProps<typeof DiscoveryDigBar>> = {}) {
  const props = {
    subject: "", onSubjectChange: vi.fn(),
    depth: 0, onDepthChange: vi.fn(),
    tasteRef: null, onTasteRefChange: vi.fn(),
    options: OPTIONS, pilePages: null as number | null,
    busy: false, ready: true, onSubmit: vi.fn(),
    ...over,
  };
  render(<DiscoveryDigBar {...props} />);
  return props;
}

describe("DiscoveryDigBar", () => {
  it("suggerisce generi ed etichette nello stesso campo, generi prima", () => {
    setup();
    fireEvent.focus(screen.getByRole("combobox"));
    const opts = screen.getAllByRole("option").map((o) => o.textContent ?? "");
    expect(opts[0]).toContain("Acid House");
    expect(opts[1]).toContain("Trax Records");
  });

  it("scegliere un'etichetta riporta il seed_type label", () => {
    const p = setup();
    fireEvent.focus(screen.getByRole("combobox"));
    fireEvent.mouseDown(screen.getByText("Trax Records"));
    expect(p.onSubjectChange).toHaveBeenCalledWith("Trax Records", "label");
  });

  it("scegliere un genere riporta il seed_type genre", () => {
    const p = setup();
    fireEvent.focus(screen.getByRole("combobox"));
    fireEvent.mouseDown(screen.getByText("Acid House"));
    expect(p.onSubjectChange).toHaveBeenCalledWith("Acid House", "genre");
  });

  it("il testo libero e' un genere", () => {
    const p = setup();
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "Inventato" } });
    expect(p.onSubjectChange).toHaveBeenCalledWith("Inventato", "genre");
  });

  it("la profondita' notifica il valore del preset", () => {
    const p = setup();
    fireEvent.click(screen.getByText("In fondo"));
    expect(p.onDepthChange).toHaveBeenCalledWith(1);
  });

  it("su pila corta la profondita' e' inerte", () => {
    setup({ pilePages: 2 });
    expect(screen.getByText("Superficie").closest("button")?.hasAttribute("disabled")).toBe(true);
  });

  it("su pila lunga la profondita' e' attiva", () => {
    setup({ pilePages: 100 });
    expect(screen.getByText("Superficie").closest("button")?.hasAttribute("disabled")).toBe(false);
  });

  it("il gusto sparisce se non ci sono playlist", () => {
    setup({ options: { ...OPTIONS, playlists: [] } });
    expect(screen.queryByText("Gusto")).toBeNull();
  });

  it("Scava e' disabilitato finche' manca il soggetto", () => {
    setup({ ready: false });
    expect(screen.getByText("Scava").closest("button")?.hasAttribute("disabled")).toBe(true);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd frontend && npm run test:unit -- discovery-dig-bar
```
Expected: FAIL — il modulo non esiste.

- [ ] **Step 3: Implement**

Crea `frontend/components/discovery-dig-bar.tsx`:

```tsx
"use client";

import { useMemo } from "react";
import { Disc3, Shovel, Tags } from "lucide-react";

import { Button, Combobox, SegmentedControl, Select, Spinner, type ComboOption } from "@/components/ui";
import { useT } from "@/lib/i18n";

/** DOVE si pesca nella pila ordinata per domanda. Non e' un mix di ordinamento:
 *  sceglie il bacino (vedi spec del motore, `_window`). */
export const DEPTHS = [
  { key: "surface", value: 0.0 },
  { key: "mid", value: 0.5 },
  { key: "deep", value: 1.0 },
] as const;

export type SeedType = "genre" | "label";

export function DiscoveryDigBar({
  subject, onSubjectChange, depth, onDepthChange, tasteRef, onTasteRefChange,
  options, pilePages, busy, ready, onSubmit,
}: {
  subject: string;
  onSubjectChange: (value: string, seed: SeedType) => void;
  depth: number;
  onDepthChange: (v: number) => void;
  tasteRef: number | null;
  onTasteRefChange: (v: number | null) => void;
  options: { genres: string[]; labels: string[]; playlists: { id: number; name: string }[] };
  pilePages: number | null;
  busy: boolean;
  ready: boolean;
  onSubmit: () => void;
}) {
  const t = useT();

  // Generi prima, etichette poi: il Combobox non riordina, riceve gia' l'ordine giusto.
  const comboOptions: ComboOption[] = useMemo(() => [
    ...options.genres.map((g) => ({
      value: g, label: g, group: t.discovery.groupGenre, icon: <Disc3 size={13} />,
    })),
    ...options.labels.map((l) => ({
      value: l, label: l, group: t.discovery.groupLabel, icon: <Tags size={13} />,
    })),
  ], [options.genres, options.labels, t]);

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

  // pila piu' corta della finestra: `depth` non ha effetto, non offrire un controllo inerte
  const shortPile = pilePages !== null && pilePages <= 3;

  return (
    <form
      onSubmit={(e) => { e.preventDefault(); onSubmit(); }}
      className="mb-6 border border-border p-4"
    >
      <div className="flex flex-wrap items-center gap-x-4 gap-y-3">
        <div className="flex min-w-[240px] flex-1 items-center gap-2">
          <span className="shrink-0 text-[10px] uppercase tracking-wider text-muted">
            {t.discovery.digLabel}
          </span>
          <Combobox
            value={subject}
            options={comboOptions}
            disabled={busy}
            placeholder={t.discovery.subjectPlaceholder}
            onChange={(v) => onSubjectChange(v, "genre")}
            onSelect={(o) => onSubjectChange(o.value, o.group === t.discovery.groupLabel ? "label" : "genre")}
          />
        </div>

        <div className="flex items-center gap-2">
          <span className="text-[10px] uppercase tracking-wider text-muted">{t.discovery.depthLabel}</span>
          <SegmentedControl
            value={String(activeDepth.value)}
            onChange={(v) => onDepthChange(Number(v))}
            options={depthOptions}
            disabled={busy || shortPile}
          />
        </div>

        {options.playlists.length > 0 && (
          <div className="flex items-center gap-2">
            <span className="text-[10px] uppercase tracking-wider text-muted">{t.discovery.affinityLabel}</span>
            <div className="w-[220px]">
              <Select
                value={tasteRef ?? ""}
                disabled={busy}
                onChange={(e) => onTasteRefChange(e.target.value ? Number(e.target.value) : null)}
              >
                <option value="">{t.discovery.wholeLibraryOption}</option>
                {options.playlists.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
              </Select>
            </div>
          </div>
        )}

        <Button type="submit" disabled={busy || !ready} className="w-full sm:w-auto">
          {busy ? <Spinner /> : <Shovel size={15} />} {t.discovery.dig}
        </Button>
      </div>

      <p className="mt-2 text-xs text-muted">
        {shortPile ? t.discovery.shortPile : depthDesc}
      </p>
    </form>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd frontend && npm run test:unit -- discovery-dig-bar && npm run lint
```
Expected: PASS (9 test).

- [ ] **Step 5: Commit**

```bash
git add frontend/components/discovery-dig-bar.tsx frontend/tests/discovery-dig-bar.test.tsx
git commit -m "feat(discovery): DiscoveryDigBar — un campo per il soggetto, profondita' e gusto pari grado"
```

---

### Task 16: La riga della risposta e il wiring della pagina

I filtri di `discovery-lead-grid.tsx` risalgono nella riga della risposta: una sola barra di comando, non due pannelli che galleggiano.

**Files:**
- Modify: `frontend/components/discovery-lead-grid.tsx:60-100`, `frontend/app/discovery/page.tsx` (tutto il corpo del componente)
- Test: coperto dai Task 15 e 18

**Interfaces:**
- Consumes: `DiscoveryDigBar` (Task 15), `discoveryDig` (Task 13), `Chip`/`SegmentedControl` (Task 11).
- Produces: `DiscoveryLeadGrid({ dig, format, onFormatChange, sort, onSortChange })`.

- [ ] **Step 1: Solleva i filtri fuori dalla griglia**

In `frontend/components/discovery-lead-grid.tsx`:
- Cambia le props da `{ dig }` a `{ dig, format, onFormatChange, sort, onSortChange }`, con `format: string | null` e `sort: "score" | "recent"`.
- Rimuovi lo stato locale `useState` di formato e ordinamento e la fascia di controlli (`:65-96`).
- Rimuovi la `Chip` ad-hoc locale: ora arriva da `@/components/ui`.
- `FORMAT_VALUES` resta esportato: lo consuma la pagina.
- La griglia e `LeadCell` non si toccano.

- [ ] **Step 2: Riscrivi il corpo di `page.tsx`**

Sostituisci il markup inline del form (`:165-311`) con `<DiscoveryDigBar />` e la riga della risposta. Il `Chip` locale in fondo al file (`:336-353`) va **cancellato**.

Cambiamenti di stato:
- `digSeed` non è più scelto dall'utente: è **derivato** da `onSubjectChange(value, seed)`.
- `adventurousness` → `depth`, default `0.0`.
- `genre` / `selectedLabel` / `showAllGenres` / `showAllLabels` collassano in un unico `subject: string`.
- Nuovo stato locale: `format: string | null = null`, `sort: "score" | "recent" = "score"` — **fuori dall'URL**: sono lenti sui risultati già ottenuti, metterli nell'URL rilancerebbe il `useEffect` su `paramsKey` e rifarebbe la chiamata a Discogs.
- `pilePages` viene da `dig?.pile_pages ?? null`.

L'URL resta la source of truth: `runDig()` costruisce `?seed=&value=&depth=&taste=` e fa `router.push`; il `useEffect` su `paramsKey` esegue il dig. **Non toccare questa meccanica** (`:111-137`), solo il nome del parametro `adv` → `depth`.

Il parametro d'URL `adv` **non va tradotto**: `adv=0.85` significava "ordina per rarità", `depth=0.85` significa "pesca in fondo alla pila". Un `adv` non riconosciuto viene ignorato e `depth` cade sul default `0.0`.

La riga della risposta, subito sotto `<DiscoveryDigBar />`, visibile solo con `dig`:

```tsx
{dig && (
  <div className="mb-4 flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-border pb-3 text-xs">
    <span className="tnum text-muted">{t.discovery.leadCount(dig.leads.length)}</span>
    <div className="flex items-center gap-2">
      <span className="text-[10px] uppercase tracking-wider text-muted">{t.discovery.formatLabel}</span>
      <div className="flex flex-wrap gap-1.5">
        <Chip on={format === null} onClick={() => setFormat(null)}>{t.discovery.formatAll}</Chip>
        {FORMAT_VALUES.map((f) => (
          <Chip key={f} on={format === f} onClick={() => setFormat(f)}>{f}</Chip>
        ))}
      </div>
    </div>
    <div className="flex items-center gap-2">
      <span className="text-[10px] uppercase tracking-wider text-muted">{t.discovery.sortLabel}</span>
      <SegmentedControl
        value={sort}
        onChange={setSort}
        options={[
          { value: "score" as const, label: t.discovery.sortScore },
          { value: "recent" as const, label: t.discovery.sortRecent },
        ]}
      />
    </div>
  </div>
)}
```

`.tnum` sul conteggio: è la Tabular Rule del design system — ogni numero che si scorre è in cifre tabulari.

- [ ] **Step 3: Verifica che compili e giri**

```bash
cd frontend && npx tsc --noEmit && npm run lint && npm run test:unit
```
Expected: tutto pulito, nessun errore residuo su `adventurousness`.

- [ ] **Step 4: Verifica nel browser**

Avvia backend e frontend, apri `/discovery` e controlla di persona:
- il campo suggerisce generi **ed** etichette insieme;
- scegliere un'etichetta e scavare produce lead di quell'etichetta;
- "Superficie" restituisce i classici del genere, "In fondo" no (**la prova che il ribaltamento funziona**);
- su un'etichetta piccola la profondità è inerte e appare "pila corta: tutta qui";
- entrambi i temi (dark e paper) reggono.

Se le modifiche a `globals.css` non si vedono: è la cache `.next/dev`, serve `rm -rf .next`.

- [ ] **Step 5: Commit**

```bash
git add frontend/app/discovery/page.tsx frontend/components/discovery-lead-grid.tsx
git commit -m "feat(discovery): riga di scavo in pagina, filtri dei lead nell'intestazione dei risultati"
```

---

### Task 17: E2E e documentazione

**Files:**
- Modify: `frontend/e2e/smoke.spec.ts:23`, `docs/API.md`, `docs/ROADMAP.md`, `PROGRESS.md`
- Test: Playwright

- [ ] **Step 1: Aggiorna lo smoke E2E**

`frontend/e2e/smoke.spec.ts:23` copre già `/discovery`: aggiorna i selettori alla riga nuova (niente più toggle "Scava per"). Aggiungi un caso per il deep link:

```ts
test("deep link per etichetta precompila il soggetto", async ({ page }) => {
  await page.goto("/discovery?seed=label&value=Trax%20Records");
  await expect(page.getByRole("combobox")).toHaveValue("Trax Records");
});
```

- [ ] **Step 2: Esegui gli E2E**

```bash
cd frontend && npm run test:e2e
```
Expected: PASS.

- [ ] **Step 3: Aggiorna la documentazione**

`docs/API.md` è la fonte di verità sugli endpoint (`CLAUDE.md`, §Source of truth). Nella sezione discovery documenta: `depth` sostituisce `adventurousness` (semantica nuova: sceglie la finestra nella pila ordinata per domanda, non il mix di ordinamento); `pile_pages` in risposta; il costo di 4–5 richieste Discogs per dig (sonda + 3 pagine, +1 sonda sul fallback `style`→`genre`).

`docs/ROADMAP.md` è la fonte di verità sullo stato: segna chiuso il ridisegno del dig.

`PROGRESS.md` è il diario cronologico: aggiungi la voce con la data (2026-07-16) e il punto che conta — il dig pescava in un campione arbitrario dello 0,69% e ora pesca nella pila ordinata per domanda.

- [ ] **Step 4: Verifica finale, tutto insieme**

```bash
cd backend && source .venv/bin/activate && python -m pytest tests -q
cd ../frontend && npm run lint && npm run test:unit && npm run build
```
Expected: tutto verde. Riporta l'output vero: se qualcosa fallisce, dillo invece di dichiarare fatto.

- [ ] **Step 5: Commit**

```bash
git add frontend/e2e/smoke.spec.ts docs/API.md docs/ROADMAP.md PROGRESS.md
git commit -m "docs+e2e: recepisce il ridisegno del dig (depth, pile_pages, riga di scavo)"
```
