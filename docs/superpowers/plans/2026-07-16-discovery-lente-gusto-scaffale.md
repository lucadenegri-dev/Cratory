# Discovery — lente sui lead, gusto senza manopola, scaffale dichiarato: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Quattro correzioni misurate sul dig già ridisegnato: il tetto degli 80 lead esce dall'API (lente client-side «MOSTRA» con conteggio «N di M»), il suggeritore scorre tutte le 319 voci, il gusto perde la manopola che mentiva su 7 playlist su 10, e un seme che ripiega sullo scaffale Discogs lo dichiara.

**Architecture:** Backend: `dig()` perde due parametri (`limit`, `taste_tracks`) e la risposta guadagna due campi (`seed_resolution`, `pile_total`) che il motore già conosce e oggi butta via. Frontend: il taglio/filtro/ordinamento diventa una funzione pura (`applyLens`) testabile in isolamento, usata da `page.tsx`; la griglia riceve la lista già pronta e smette di filtrare.

**Tech Stack:** Backend Python 3 + FastAPI + Pydantic, pytest (nessuna rete nei test — `search_releases`/`count_releases` iniettate). Frontend Next.js 16 + React, vitest in `frontend/tests/`, Playwright in `frontend/e2e/`.

**Spec:** `docs/superpowers/specs/2026-07-16-discovery-quanti-lead-e-suggeritore-completo-design.md`

## Global Constraints

- Branch: `feat/discovery-dig-riprogettato` (già attivo). Prima di ogni commit: `git status`, stagia SOLO i file del task (sessioni parallele sullo stesso checkout).
- Mai aggiungere Claude come co-autore nei commit.
- **Nessuna nuova dipendenza**, né backend né frontend.
- **Nessuna rete nei test backend**: la suite deve restare verde a rete bloccata (933+ oggi).
- `docs/DESIGN.md` vincolante: monospace, `radius: 0`, filetti 1px, nessuna ombra, monocromia (solo `danger`), due temi, `.tnum` su ogni numero scorso (The Tabular Rule).
- Next.js 16 ha breaking change: leggere `frontend/CLAUDE.md` prima di toccare pagine.
- Convenzione test frontend: `afterEach(cleanup)` in cima a ogni file di test.
- `it.ts` e `en.ts` devono avere le stesse chiavi (una manca = errore di tipo).
- **Il rischio ricorrente di questo progetto** (materializzato 4 volte): test che codificano il modello vecchio, aggiornati in modo cosmetico. Un test che asseriva il troncamento ora deve asserire che NON avviene — riscrittura semantica, con commento, mai rename.
- Microcopy dello scaffale, scelta dal committente, alla lettera: IT «Genere molto generico: {total} dischi su Discogs, ne vedi solo i {reachable} più cercati. Un sottogenere più preciso scava meglio.» / EN «Very broad genre: {total} records on Discogs, you only see the {reachable} most wanted. A more specific subgenre digs better.» I numeri sono parametri, mai cablati nella stringa.

---

## File Structure

| File | Responsabilità | Azione |
|---|---|---|
| `backend/app/services/discovery_dig.py` | Motore: via `limit`/`taste_tracks`, dentro `seed_resolution`/`pile_total` | Modifica |
| `backend/app/schemas.py` | Contratto: via `limit`/`taste_playlist_id`, dentro i due campi nuovi | Modifica |
| `backend/app/routers/discovery.py` | Wiring: via `tracks_for_playlist`, passa i campi nuovi | Modifica |
| `backend/tests/test_discovery_dig.py`, `test_discovery.py`, `test_discovery_router_http.py` | Riscritture semantiche | Modifica |
| `frontend/components/ui.tsx` | `Combobox`: via `cap`, dentro `scrollIntoView` | Modifica |
| `frontend/components/discovery-lead-grid.tsx` | `applyLens` (pura, esportata); la griglia rende ciò che riceve | Modifica |
| `frontend/components/discovery-dig-bar.tsx` | Via il selettore del gusto | Modifica |
| `frontend/app/discovery/page.tsx` | Via stato/URL `taste`; lente MOSTRA; conteggio «N di M»; messaggio scaffale | Modifica |
| `frontend/lib/api/discovery.ts`, `types.ts` | Client e tipi | Modifica |
| `frontend/lib/i18n/it.ts`, `en.ts` | Chiavi: −3 morte, +4 nuove | Modifica |
| `frontend/tests/ui-primitives.test.tsx`, `discovery-dig-bar.test.tsx` | Test primitive e barra | Modifica |
| `frontend/tests/discovery-lens.test.ts` | Test di `applyLens` | **Crea** |
| `docs/API.md`, `PROGRESS.md` | Fonti di verità | Modifica |

L'ordine è backend (1–3) → frontend (4–7) → docs/verifica (8). I task 1–3 toccano gli stessi file backend ma sono gate di review distinti: un reviewer può bocciare la rimozione del gusto approvando quella del limit.

---

### Task 1: `limit` esce dal motore e dall'API

Il tetto morde a ogni dig (misurato: 240 candidati, 80 mostrati, 160 buttati senza che nulla lo dica) e l'API non può nemmeno restituirli tutti (`le=200` < 240). La finestra di 3 pagine è già il limite naturale.

**Files:**
- Modify: `backend/app/services/discovery_dig.py:38` (`DEFAULT_DIG_LIMIT`), `:441` (`_select`), `:465-475` (`dig`)
- Modify: `backend/app/schemas.py` (`DiscoveryDigRequest.limit`)
- Modify: `backend/app/routers/discovery.py` (`limit=req.limit`)
- Test: `backend/tests/test_discovery_dig.py`, `backend/tests/test_discovery_router_http.py`

**Interfaces:**
- Consumes: stato attuale del branch (933 test verdi).
- Produces: `_select(leads: list[DiscoveryLead]) -> list[DiscoveryLead]` (senza `limit`); `dig(db, *, seed_type, value, search_releases, count_releases, library=None, taste_tracks=None, depth=0.0) -> DigResult`; `DiscoveryDigRequest` senza `limit`.

- [ ] **Step 1: Write the failing tests**

In `backend/tests/test_discovery_dig.py`:

```python
def test_select_does_not_truncate():
    # 240 candidati -> 240 lead. Il tetto di 80 nascondeva 160 lead a OGNI dig
    # (misurato su style=Acid House: la finestra ordinata per domanda e' pulita,
    # ne sopravvivono 244 su 300). La finestra e' gia' il limite naturale.
    leads = [_lead_from_release(_release(f"Artist{i} - T{i}", rid=i), "x") for i in range(240)]
    assert len(_select(leads)) == 240


def test_select_still_caps_per_artist():
    # Il cap anti-monopolio resta: e' l'unico taglio che _select deve ancora fare.
    leads = [_lead_from_release(_release(f"Same Artist - T{i}", rid=i), "x") for i in range(5)]
    assert len(_select(leads)) == 2
```

In `backend/tests/test_discovery_router_http.py`:

```python
def test_dig_endpoint_ignores_legacy_limit_field(client, monkeypatch):
    # Il campo `limit` non esiste piu' nel contratto. Pydantic (config del progetto)
    # ignora i campi sconosciuti: una richiesta vecchia non deve rompersi ne' troncare.
    # PRIMA di scrivere l'asserzione, verifica il comportamento REALE del modello
    # (model_config / Extra): se il progetto usa extra="forbid", l'atteso e' 422 —
    # testa quello che il codice fa, non quello che questo commento suppone.
    class _FakeClient:
        def search_releases(self, **kw):
            return [_fake_release(rid=i) for i in range(150)]

        def count_releases(self, **kw):
            return 43345

        def close(self):
            pass

    monkeypatch.setattr("app.routers.discovery.DiscogsClient", lambda: _FakeClient())
    r = client.post("/api/discovery/dig",
                    json={"seed_type": "genre", "value": "Acid House", "limit": 5})
    assert r.status_code == 200
    assert len(r.json()["leads"]) > 5   # nessun troncamento: il campo e' ignorato
```

Adatta `_fake_release` allo helper reale del file (leggilo prima): serve che generi release con artisti **distinti** per non far scattare il cap per artista.

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && source .venv/bin/activate && python -m pytest tests/test_discovery_dig.py -q -k "select_does_not_truncate or still_caps" 
```
Expected: FAIL — `TypeError: _select() missing 1 required positional argument: 'limit'`.

- [ ] **Step 3: Implement**

In `discovery_dig.py`:
- Rimuovi la costante `DEFAULT_DIG_LIMIT = 80` (verifica con `grep -rn DEFAULT_DIG_LIMIT backend/` che nessun altro la importi).
- `_select` perde il parametro e il break:

```python
def _select(leads: list[DiscoveryLead]) -> list[DiscoveryLead]:
    """Ordina per score e applica il cap per artista (no monopolio). NON tronca:
    la finestra di 3 pagine e' gia' il limite naturale (~300 release grezze), e il
    vecchio tetto di 80 nascondeva 160 lead a ogni dig senza che nulla lo dicesse.
    Quanti mostrarne e' una lente della UI, non un parametro del motore.

    Il sort DEVE restare stabile — `sorted` lo garantisce, ed e' su questa garanzia che
    poggia il fallback a gusto piatto: quando il riferimento e' vuoto (o nessun segnale
    aggancia) i lead pareggiano tutti, e l'ordine che sopravvive e' quello in cui sono
    entrati, cioe' l'ordine per domanda con cui Discogs ha risposto dentro la finestra.
    E' l'unico ordine sensato che resta quando il gusto non discrimina, ed e' voluto:
    sostituire `sorted` con un ordinamento instabile lo romperebbe in silenzio (nessun
    errore, solo lead in ordine arbitrario).
    """
    out: list[DiscoveryLead] = []
    per_artist: dict[str, int] = {}
    for lead in sorted(leads, key=lambda x: x.score, reverse=True):
        a = lead.artist_keys[0]
        if per_artist.get(a, 0) >= _MAX_PER_ARTIST:
            continue
        per_artist[a] = per_artist.get(a, 0) + 1
        out.append(lead)
    return out
```

(La parte sul sort stabile è la docstring esistente: conservala, non riscriverla.)

- `dig()`: rimuovi `limit: int = DEFAULT_DIG_LIMIT` dalla firma e chiama `_select(leads)`.

In `schemas.py`: rimuovi la riga `limit: int = Field(default=80, ge=1, le=200)`.

In `routers/discovery.py`: rimuovi `limit=req.limit` dalla chiamata.

- [ ] **Step 4: Riscrivi semanticamente i test che passavano `limit=`**

`grep -n "limit=" backend/tests/test_discovery_dig.py backend/tests/test_discovery.py backend/tests/test_discovery_router_http.py`. Per ognuno: se testava il troncamento, ora testa che non avviene (o è coperto da `test_select_does_not_truncate`: allora rimuovilo **con un commento nel commit message**); se passava `limit=` solo per abitudine, togli l'argomento. Nessun rename cosmetico.

- [ ] **Step 5: Run the whole backend suite**

```bash
cd backend && source .venv/bin/activate && python -m pytest tests -q
```
Expected: tutti PASS (il conteggio scende/sale a seconda dei test rimossi/aggiunti — riporta il numero vero).

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/discovery_dig.py backend/app/schemas.py backend/app/routers/discovery.py backend/tests/
git commit -m "feat(dig): via il tetto degli 80 lead — la finestra e' gia' il limite naturale"
```

---

### Task 2: il gusto perde la manopola

Misurato: con 7 playlist su 10 il riferimento azzera l'ordinamento in silenzio (80 lead su 80 a punteggio 0 con "Wallis b2b Blawan": 10 tracce, 0 etichette, 0 generi — i tag arrivano dai file, che le playlist di lead non hanno). Il profilo si costruisce sempre dalla libreria, dove è misurato che ordina.

**Files:**
- Modify: `backend/app/services/discovery_dig.py` (`dig()`: via `taste_tracks`), `backend/app/schemas.py` (via `taste_playlist_id`), `backend/app/routers/discovery.py` (via il blocco `tracks_for_playlist`)
- Test: `backend/tests/test_discovery_dig.py`, `backend/tests/test_discovery.py`

**Interfaces:**
- Consumes: `dig()` dal Task 1 (già senza `limit`).
- Produces: `dig(db, *, seed_type, value, search_releases, count_releases, library=None, depth=0.0) -> DigResult`; `DiscoveryDigRequest` = `{seed_type, value, depth}`.

- [ ] **Step 1: Write the failing test**

```python
def test_dig_profile_always_comes_from_library():
    # Il riferimento di gusto E' la libreria: la manopola della playlist e' stata
    # rimossa perche' su 7 playlist su 10 azzerava l'ordinamento in silenzio
    # (profilo quasi vuoto: etichette e generi arrivano dai tag dei file, che le
    # playlist di lead non hanno).
    def search(**kw):
        return [_release("Sconosciuto - X", rid=1), _release("Tyree* - Y", rid=2)]

    lib = _lib(("Tyree", "T1"), ("Tyree", "T2"), ("Tyree", "T3"))
    res = dig(None, seed_type="genre", value="Acid House", search_releases=search,
              count_releases=lambda **kw: 300, library=lib, depth=0.0)
    assert res.leads[0].artist == "Tyree"      # la familiarita' della LIBRERIA ordina
```

- [ ] **Step 2: Run test to verify it fails**

Fallirà solo dopo la rimozione se qualche test esistente passa `taste_tracks=`; questo test in sé passa già. Il rosso vero arriva dai test esistenti: eseguili prima (`pytest tests -q -k taste`) e annota quali sono.

- [ ] **Step 3: Implement**

- `dig()`: via `taste_tracks: list | None = None` dalla firma; `profile = TasteProfile.from_tracks(library)`. Docstring: via la frase su `taste_tracks`, dentro una riga che dice che riferimento del gusto e libreria del possesso ora coincidono per scelta (e perché).
- `schemas.py`: via `taste_playlist_id: int | None = None`.
- `routers/discovery.py`: via `from app.repositories import tracks_for_playlist`, il blocco `taste_tracks = ...` e l'argomento.

- [ ] **Step 4: Riscrivi semanticamente i test del taste**

`grep -n "taste" backend/tests/*.py`. `test_dig_endpoint_honors_taste_playlist_id` (in `test_discovery.py`) codifica il comportamento rimosso: sostituiscilo con un test che asserisce che il campo è ignorato (stesso pattern del legacy `limit` del Task 1), con un commento sul perché. I test di `discovery_dig.py` che passavano `taste_tracks=` vanno riscritti verso `library=` se l'intento sopravvive, o rimossi con motivazione nel report.

- [ ] **Step 5: Run suite + commit**

```bash
cd backend && source .venv/bin/activate && python -m pytest tests -q
git add backend/app backend/tests && git commit -m "feat(dig): il gusto perde la manopola — il profilo e' sempre la libreria"
```

---

### Task 3: `seed_resolution` e `pile_total` nel contratto

Il motore sa già come ha risolto il seme (il fallback `style`→`genre` è un ramo esplicito) e quanto è alta la pila grezza (la sonda restituisce `pagination.items`): oggi butta via entrambi. `pile_pages` non basta: vale 100 sia per `style=Acid House` (43k) sia per `genre=Electronic` (4,9M).

**Files:**
- Modify: `backend/app/services/discovery_dig.py:177-181` (`DigResult`), corpo di `dig()`
- Modify: `backend/app/schemas.py` (`DiscoveryDigResponse`), `backend/app/routers/discovery.py` (return)
- Test: `backend/tests/test_discovery_dig.py`, `backend/tests/test_discovery_router_http.py`

**Interfaces:**
- Consumes: `dig()` dai Task 1-2.
- Produces: `DigResult.seed_resolution: str | None` (`"style" | "genre" | "label" | None`), `DigResult.pile_total: int`; stessi campi su `DiscoveryDigResponse`.

- [ ] **Step 1: Write the failing tests**

```python
def test_dig_reports_style_resolution():
    res = dig(None, seed_type="genre", value="Acid House",
              search_releases=lambda **kw: [], count_releases=lambda **kw: 43345,
              library=[], depth=0.0)
    assert res.seed_resolution == "style"
    assert res.pile_total == 43345


def test_dig_reports_genre_fallback_resolution():
    # 'Electronic' non e' uno style: la sonda su style= torna 0 e si ripiega su
    # genre= — lo scaffale. Il contratto lo dice, cosi' la UI puo' avvertire.
    def count(**kw):
        return 0 if "style" in kw else 4_960_093

    res = dig(None, seed_type="genre", value="Electronic",
              search_releases=lambda **kw: [], count_releases=count,
              library=[], depth=0.0)
    assert res.seed_resolution == "genre"
    assert res.pile_total == 4_960_093    # il conteggio del filtro che ha VINTO


def test_dig_reports_label_resolution():
    res = dig(None, seed_type="label", value="Trax Records",
              search_releases=lambda **kw: [], count_releases=lambda **kw: 10096,
              library=[], depth=0.0)
    assert res.seed_resolution == "label"


def test_dead_seed_has_no_resolution():
    res = dig(None, seed_type="genre", value="Inesistente",
              search_releases=lambda **kw: [], count_releases=lambda **kw: 0,
              library=[], depth=0.0)
    assert res.seed_resolution is None
    assert res.pile_pages == 0
```

In `test_discovery_router_http.py` (imita il pattern `_FakeClient` esistente):

```python
def test_dig_endpoint_exposes_seed_resolution_and_pile_total(client, monkeypatch):
    class _FakeClient:
        def search_releases(self, **kw):
            return []

        def count_releases(self, **kw):
            return 0 if "style" in kw else 4_960_093

        def close(self):
            pass

    monkeypatch.setattr("app.routers.discovery.DiscogsClient", lambda: _FakeClient())
    r = client.post("/api/discovery/dig", json={"seed_type": "genre", "value": "Electronic"})
    assert r.status_code == 200
    assert r.json()["seed_resolution"] == "genre"
    assert r.json()["pile_total"] == 4_960_093
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && source .venv/bin/activate && python -m pytest tests -q -k "resolution or pile_total"
```
Expected: FAIL — `AttributeError: 'DigResult' object has no attribute 'seed_resolution'`.

- [ ] **Step 3: Implement**

`DigResult`:

```python
@dataclass
class DigResult:
    seed_type: str
    value: str
    leads: list[DiscoveryLead] = field(default_factory=list)
    pile_pages: int = 0
    # Com'e' stato risolto il seme: "style" | "genre" | "label" | None (pila vuota).
    # "genre" = il fallback sullo scaffale Discogs: la UI deve poterlo dire.
    seed_resolution: str | None = None
    # Conteggio grezzo della sonda (pagination.items) del filtro che ha vinto:
    # pile_pages e' cappato a 100 e non distingue 43k da 4,9M.
    pile_total: int = 0
```

In `dig()`, traccia la risoluzione accanto ai filtri (il ramo esiste già — aggiungi solo la variabile):

```python
    if seed_type == "label":
        filters: dict[str, Any] = {"label": value}
        resolution = "label"
    elif seed_type == "genre":
        filters = {"style": value}
        resolution = "style"
    else:
        return DigResult(seed_type=seed_type, value=value, pile_pages=0)

    total = count_releases(**filters)
    if total == 0 and seed_type == "genre":
        # Fallback sullo scaffale: 'Electronic' non e' uno style ma un genre.
        filters = {"genre": value}
        resolution = "genre"
        total = count_releases(**filters)
```

e nei due return: quello a pila vuota resta senza risoluzione (`pile_pages=0`); quello finale aggiunge `seed_resolution=resolution, pile_total=total`.

`DiscoveryDigResponse`:

```python
    # Com'e' stato risolto il seme ("style" | "genre" | "label" | null). "genre" =
    # scaffale Discogs (~15 categorie enormi): la UI avverte che si vede solo la cima.
    seed_resolution: str | None = None
    # Conteggio grezzo della sonda: serve al messaggio ("4.960.093 dischi").
    pile_total: int = 0
```

Router: `seed_resolution=result.seed_resolution, pile_total=result.pile_total` nel return.

- [ ] **Step 4: Run suite + commit**

```bash
cd backend && source .venv/bin/activate && python -m pytest tests -q
git add backend/app backend/tests && git commit -m "feat(api): seed_resolution e pile_total — il fallback sullo scaffale smette di essere muto"
```

---

### Task 4: il suggeritore scorre tutto

`cap = 12` contro 319 voci reali, con una lista che già scorre (`max-h-64 overflow-y-auto`): il tetto la contraddice. Toglierlo **obbliga** ad aggiungere `scrollIntoView`, che oggi manca: già con 12 voci la freccia giù porta l'evidenziazione fuori dai ~7 elementi visibili.

**Files:**
- Modify: `frontend/components/ui.tsx` (`Combobox`)
- Test: `frontend/tests/ui-primitives.test.tsx`

**Interfaces:**
- Consumes: `Combobox` attuale (controllato, senza stato ombra).
- Produces: `Combobox({ value, onChange, onSelect, options, placeholder, disabled })` — senza `cap`.

- [ ] **Step 1: Write the failing tests**

In `ui-primitives.test.tsx` (jsdom non implementa `scrollIntoView`: va stubbato):

```tsx
beforeAll(() => {
  // jsdom non implementa scrollIntoView: senza stub, il componente lancerebbe.
  Element.prototype.scrollIntoView = vi.fn();
});

describe("Combobox — lista completa e scroll da tastiera", () => {
  const MANY: ComboOption[] = Array.from({ length: 319 }, (_, i) => ({
    value: `g${i}`, label: `g${i}`, group: "genere",
  }));

  it("rende tutte le opzioni, nessun cap", () => {
    render(<Harness options={MANY} />);
    fireEvent.focus(screen.getByRole("combobox"));
    expect(screen.getAllByRole("option").length).toBe(319);
  });

  it("ArrowDown porta l'opzione attiva in vista", () => {
    const spy = vi.spyOn(Element.prototype, "scrollIntoView");
    render(<Harness options={MANY} />);
    const input = screen.getByRole("combobox");
    fireEvent.focus(input);
    fireEvent.keyDown(input, { key: "ArrowDown" });
    expect(spy).toHaveBeenCalledWith({ block: "nearest" });
    spy.mockRestore();
  });

  it("il mouse NON fa scrollare la lista", () => {
    // onMouseEnter cambia l'opzione attiva, ma l'utente sta gia' guardando quella
    // che tocca: farle saltare la lista sotto il cursore e' peggio del difetto curato.
    const spy = vi.spyOn(Element.prototype, "scrollIntoView");
    render(<Harness options={MANY} />);
    fireEvent.focus(screen.getByRole("combobox"));
    fireEvent.mouseEnter(screen.getAllByRole("option")[3]);
    expect(spy).not.toHaveBeenCalled();
    spy.mockRestore();
  });
});
```

Aggiorna il test esistente `"cappa le voci visibili"`: il cap non esiste più — sostituiscilo con `"rende tutte le opzioni"` qui sopra (che lo rimpiazza, non lo duplica). Riusa lo `Harness` già presente nel file.

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd frontend && npm run test:unit -- ui-primitives
```
Expected: FAIL — il cap taglia a 12 e `scrollIntoView` non viene chiamato.

- [ ] **Step 3: Implement**

In `Combobox`:
- Via `cap = 12` dalla firma e dal tipo; via `.slice(0, cap)` da `matches` e `cap` dalle dependency del `useMemo`.
- In `onKeyDown`, il ramo frecce diventa (calcolo dell'indice fuori dall'updater — niente side effect dentro `setActive`):

```tsx
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      setOpen(true);
      const next = Math.max(0, Math.min(matches.length - 1,
        e.key === "ArrowDown" ? active + 1 : active - 1));
      setActive(next);
      // Porta in vista SOLO da tastiera: onMouseEnter cambia `active` ma li'
      // l'utente sta gia' guardando l'opzione che tocca — farle saltare la lista
      // sotto il cursore sarebbe peggio del difetto che questo cura.
      document.getElementById(`combobox-opt-${next}`)?.scrollIntoView({ block: "nearest" });
      return;
    }
```

- [ ] **Step 4: Run tests + lint, commit**

```bash
cd frontend && npm run test:unit && npm run lint
git add frontend/components/ui.tsx frontend/tests/ui-primitives.test.tsx
git commit -m "feat(ds): il Combobox scorre tutte le voci — via il cap, dentro lo scroll da tastiera"
```

---

### Task 5: client API e tipi

**Files:**
- Modify: `frontend/lib/api/discovery.ts` (`discoveryDig`), `frontend/lib/api/types.ts` (`DiscoveryDigResponse`)

**Interfaces:**
- Consumes: contratto del Task 3.
- Produces: `discoveryDig(seedType, value, opts?: { depth?: number })`; `DiscoveryDigResponse` con `seed_resolution: "style" | "genre" | "label" | null` e `pile_total: number`; costante `DISCOGS_PAGE_SIZE = 100` esportata da `discovery.ts`.

- [ ] **Step 1: Implementa**

`discovery.ts`:

```ts
// Rispecchia SEARCH_PER_PAGE del backend (il massimo per pagina di Discogs).
// Serve alla UI per calcolare quante release sono raggiungibili
// (pile_pages × DISCOGS_PAGE_SIZE) senza cablare "10.000" nel testo.
export const DISCOGS_PAGE_SIZE = 100;

export function discoveryDig(
  seedType: "genre" | "label",
  value: string,
  opts?: { depth?: number },
) {
  return apiPost<DiscoveryDigResponse>("/api/discovery/dig", {
    seed_type: seedType,
    value,
    depth: opts?.depth,
  });
}
```

`types.ts`, su `DiscoveryDigResponse`:

```ts
  /** Com'è stato risolto il seme. "genre" = scaffale Discogs: la UI avverte. */
  seed_resolution: "style" | "genre" | "label" | null;
  /** Conteggio grezzo della sonda: pile_pages è cappato a 100 e non distingue 43k da 4,9M. */
  pile_total: number;
```

- [ ] **Step 2: Verifica che compili dove deve**

```bash
cd frontend && npx tsc --noEmit
```
Expected: errori **solo** in `app/discovery/page.tsx` (passa ancora `tastePlaylistId`). Attesi fino al Task 7 — annota quanti e quali.

- [ ] **Step 3: Commit**

```bash
git add frontend/lib/api/discovery.ts frontend/lib/api/types.ts
git commit -m "feat(api-client): via limit e taste, dentro seed_resolution e pile_total"
```

---

### Task 6: la barra perde il selettore del gusto

**Files:**
- Modify: `frontend/components/discovery-dig-bar.tsx`
- Test: `frontend/tests/discovery-dig-bar.test.tsx`

**Interfaces:**
- Consumes: niente di nuovo.
- Produces: `DiscoveryDigBar({ subject, onSubjectChange, depth, onDepthChange, options, pilePages, busy, ready, onSubmit })` con `options: { genres: { library: string[]; styles: string[] }; labels: string[] }` — senza `tasteRef`, `onTasteRefChange`, `playlists`.

- [ ] **Step 1: Write the failing test**

Nel file di test della barra: aggiorna `OPTIONS` (via `playlists`), via le prop `tasteRef`/`onTasteRefChange` da `setup()`, e sostituisci il test `"il gusto sparisce se non ci sono playlist"` con:

```tsx
  it("il selettore del gusto non esiste piu'", () => {
    // La manopola azzerava l'ordinamento in silenzio su 7 playlist su 10 (profilo
    // quasi vuoto: etichette e generi vengono dai tag dei file, che le playlist di
    // lead non hanno). Il gusto resta acceso sulla libreria, senza manopola.
    setup();
    expect(screen.getAllByRole("combobox").length).toBe(1);   // solo il soggetto
  });
```

Nota: lo helper `subjectInput()` con `getAllByRole("combobox")[0]` resta valido (ora c'è un solo combobox — il commento che spiegava l'ambiguità col `<select>` va aggiornato).

- [ ] **Step 2: Run to verify it fails, then implement**

Nella barra: via le prop `tasteRef`/`onTasteRefChange`/`options.playlists` dal tipo e dalla destrutturazione; via il blocco JSX del gusto (`affinityLabel` + `Select` + hint `affinityHint`); via l'import di `Select` se non resta usato (verifica). Le chiavi i18n restano fino al Task 7 (le rimuove chi rimuove l'ultimo consumatore).

- [ ] **Step 3: Run tests + commit**

```bash
cd frontend && npm run test:unit -- discovery-dig-bar
git add frontend/components/discovery-dig-bar.tsx frontend/tests/discovery-dig-bar.test.tsx
git commit -m "feat(discovery): la barra perde il selettore del gusto"
```

`tsc` avrà ancora errori in `page.tsx` (passa prop che non esistono più): attesi, li chiude il Task 7.

---

### Task 7: la lente MOSTRA, il conteggio «N di M», il messaggio scaffale

Il task che salda il frontend. Il taglio/filtro/ordinamento diventa una funzione pura testabile; la griglia rende ciò che riceve; la pagina compone.

**Files:**
- Modify: `frontend/components/discovery-lead-grid.tsx` (aggiunge `applyLens`, la griglia perde il filtro interno)
- Modify: `frontend/app/discovery/page.tsx` (via taste, dentro lente + conteggio + messaggio)
- Modify: `frontend/lib/i18n/it.ts`, `frontend/lib/i18n/en.ts`
- Test: `frontend/tests/discovery-lens.test.ts` (crea)

**Interfaces:**
- Consumes: `DISCOGS_PAGE_SIZE` (Task 5), barra (Task 6), campi del contratto (Task 3/5).
- Produces:
  - `applyLens(leads: DiscoveryLead[], opts: { format: string | null; sort: SortMode; show: number | "all" }): { visible: DiscoveryLead[]; total: number }` — esportata da `discovery-lead-grid.tsx`.
  - `DiscoveryLeadGrid({ dig, leads }: { dig: DiscoveryDigResponse; leads: DiscoveryLead[] })`.

- [ ] **Step 1: Write the failing tests**

Crea `frontend/tests/discovery-lens.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { applyLens } from "@/components/discovery-lead-grid";
import type { DiscoveryLead } from "@/lib/api/types";

function lead(over: Partial<DiscoveryLead>): DiscoveryLead {
  return { artist: "A", title: "T", year: 2000, label: null, style: null,
    source: "discogs", seed: null, discogs_url: null, thumb_url: null,
    have: 0, want: 0, reasons: [], discogs_id: null, format_badge: null, ...over };
}

describe("applyLens", () => {
  const LEADS = [
    ...Array.from({ length: 200 }, (_, i) => lead({ title: `lp${i}`, format_badge: "LP", year: 1990 + (i % 30) })),
    ...Array.from({ length: 40 }, (_, i) => lead({ title: `ep${i}`, format_badge: "EP" })),
  ];

  it("taglia DOPO il filtro di formato: i numeri non mentono", () => {
    const { visible, total } = applyLens(LEADS, { format: "EP", sort: "score", show: 80 });
    expect(total).toBe(40);            // "40 di 40", non "40 di 240"
    expect(visible.length).toBe(40);
  });

  it("show=40 su 240 lead: 40 visibili, total 240", () => {
    const { visible, total } = applyLens(LEADS, { format: null, sort: "score", show: 40 });
    expect(visible.length).toBe(40);
    expect(total).toBe(240);
  });

  it("show='all' mostra tutto", () => {
    expect(applyLens(LEADS, { format: null, sort: "score", show: "all" }).visible.length).toBe(240);
  });

  it("sort='recent' ordina per anno decrescente prima del taglio", () => {
    const { visible } = applyLens(LEADS, { format: "LP", sort: "recent", show: 40 });
    expect(visible[0].year).toBe(2019);
  });
});
```

Adatta la factory `lead()` ai campi reali di `DiscoveryLead` in `types.ts` (leggila prima: se un campo è opzionale, non serve elencarlo).

- [ ] **Step 2: Run to verify it fails**

```bash
cd frontend && npm run test:unit -- discovery-lens
```
Expected: FAIL — `applyLens` non esiste.

- [ ] **Step 3: Implement `applyLens` e la griglia**

In `discovery-lead-grid.tsx`:

```tsx
// La lente sui risultati gia' scaricati: formato -> ordinamento -> taglio.
// Il taglio viene DOPO il formato, cosi' "40 di 240" conta cio' che il filtro ha
// lasciato e i numeri non mentono. Pura e testabile: page.tsx la usa per la lista
// E per il conteggio, quindi i due non possono divergere.
export function applyLens(
  leads: DiscoveryLead[],
  opts: { format: string | null; sort: SortMode; show: number | "all" },
): { visible: DiscoveryLead[]; total: number } {
  const base = opts.format === null ? leads : leads.filter((l) => l.format_badge === opts.format);
  const sorted = opts.sort === "score" ? base : [...base].sort((a, b) => (b.year ?? 0) - (a.year ?? 0));
  return { visible: opts.show === "all" ? sorted : sorted.slice(0, opts.show), total: base.length };
}
```

La griglia: props da `{ dig, format, sort }` a `{ dig, leads }`; via il `useMemo` interno `filtered`; il corpo rende `leads`; gli empty state su `dig` restano identici (pila vuota → seme morto; `dig.leads.length === 0` → niente da scavare; `leads.length === 0` con `dig.leads.length > 0` → `noFormatMatch`). Esporta `SortMode` se non già esportato (serve a `page.tsx` e alla lente).

- [ ] **Step 4: Ricomponi `page.tsx`**

- Via: `initialTaste`, stato `tasteRef`, stato `playlists` + fetch `listImportedPlaylists()` (**verifica con grep che nella pagina non serva ad altro**; l'import va tolto), parametro `taste` da `runDig`/`paramsKey`/`useEffect`, `tastePlaylistId` dalla chiamata, prop `tasteRef`/`onTasteRefChange`/`playlists` alla barra.
- Dentro: `const [show, setShow] = useState<number | "all">(80);` (stato locale, fuori dall'URL — è una lente, non un parametro del dig).
- Composizione:

```tsx
  const { visible, total } = useMemo(
    () => applyLens(dig?.leads ?? [], { format, sort, show }),
    [dig, format, sort, show],
  );
```

- La riga della risposta: il conteggio diventa

```tsx
  <span className="tnum text-muted">
    {visible.length < total
      ? t.discovery.leadCountOf(visible.length, total)
      : t.discovery.leadCount(total)}
  </span>
```

e accanto a FORMATO/ORDINE entra MOSTRA:

```tsx
  <div className="flex items-center gap-2">
    <span className="text-[10px] uppercase tracking-wider text-muted">{t.discovery.showLabel}</span>
    <SegmentedControl
      value={show === "all" ? "all" : String(show)}
      onChange={(v) => setShow(v === "all" ? "all" : Number(v))}
      options={[
        { value: "40", label: "40" },
        { value: "80", label: "80" },
        { value: "all", label: t.discovery.showAll },
      ]}
    />
  </div>
```

- Il messaggio scaffale, nella stessa riga, solo quando serve e coi numeri veri (la guardia `pile_total > raggiungibili` evita di dire «ne vedi solo 10.000» quando la pila è tutta raggiungibile):

```tsx
  {dig.seed_resolution === "genre" && dig.pile_total > dig.pile_pages * DISCOGS_PAGE_SIZE && (
    <span className="tnum text-muted">
      {t.discovery.broadSeed(
        dig.pile_total.toLocaleString(),
        (dig.pile_pages * DISCOGS_PAGE_SIZE).toLocaleString(),
      )}
    </span>
  )}
```

- La griglia riceve la lista pronta: `<DiscoveryLeadGrid dig={dig} leads={visible} />`.

- [ ] **Step 5: i18n**

`it.ts`, sezione `discovery` — **rimuovi** `affinityLabel`, `affinityHint`, `wholeLibraryOption` (⚠️ esiste un altro `wholeLibraryOption` in un'altra sezione del file, ~riga 670: NON toccarlo). **Aggiungi**:

```ts
    showLabel: "Mostra",
    showAll: "tutti",
    leadCountOf: (shown: number, total: number) => `${shown} di ${total}`,
    broadSeed: (total: string, reachable: string) =>
      `Genere molto generico: ${total} dischi su Discogs, ne vedi solo i ${reachable} più cercati. Un sottogenere più preciso scava meglio.`,
```

`en.ts`, stesse chiavi:

```ts
    showLabel: "Show",
    showAll: "all",
    leadCountOf: (shown: number, total: number) => `${shown} of ${total}`,
    broadSeed: (total: string, reachable: string) =>
      `Very broad genre: ${total} records on Discogs, you only see the ${reachable} most wanted. A more specific subgenre digs better.`,
```

- [ ] **Step 6: Verifica completa frontend**

```bash
cd frontend && npx tsc --noEmit && npm run lint && npm run test:unit
```
Expected: `tsc` **pulito** (niente più errori attesi), lint 0 errori, test tutti verdi.

Nota onesta sul coverage: la **visibilità** del messaggio scaffale (compare solo con
`seed_resolution === "genre"`, mai con `style`/`label`, seme morto ha la precedenza) vive
in `page.tsx`, che in questo progetto non ha harness di test. La matematica della lente è
coperta da `applyLens`; la condizione del messaggio la verifica il controller **nel
browser** dopo il task (dig su «Electronic» → messaggio; su «Dub Techno» → niente;
su seme inesistente → empty state del seme morto, nessun messaggio). Dichiaralo nel
report, non fingere che sia coperto da unit test.

- [ ] **Step 7: Commit**

```bash
git add frontend/app/discovery/page.tsx frontend/components/discovery-lead-grid.tsx frontend/lib/i18n/ frontend/tests/discovery-lens.test.ts
git commit -m "feat(discovery): lente MOSTRA con conteggio onesto, via il taste, scaffale dichiarato"
```

---

### Task 8: E2E, documentazione, verifica finale

**Files:**
- Modify: `frontend/e2e/smoke.spec.ts` (se tocca il taste o il conteggio), `docs/API.md`, `PROGRESS.md`

- [ ] **Step 1: E2E**

`grep -n "taste\|combobox\|lead" frontend/e2e/smoke.spec.ts` — con il `<select>` del gusto sparito, il selettore `.first()` sul combobox resta valido ma il commento che lo giustificava va aggiornato; se un test asseriva la presenza del gusto, riscrivilo semanticamente. Poi:

```bash
cd frontend && npm run test:e2e
```
Expected: PASS. Se il dev server non parte, dillo nel report — non dichiarare verde ciò che non hai visto.

- [ ] **Step 2: Documentazione**

- `docs/API.md` (fonte di verità sugli endpoint): il dig non accetta più `limit` né `taste_playlist_id`; la risposta porta `seed_resolution` e `pile_total`; il costo di rete resta 4-5 richieste. Aggiorna la sezione discovery, imitando lingua e stile del file.
- `PROGRESS.md` (diario, in italiano, data 2026-07-16): la voce che conta — il tetto degli 80 nascondeva 160 lead a ogni dig, la manopola del gusto mentiva su 7 playlist su 10, e ora un seme che ripiega sullo scaffale Discogs lo dichiara.

- [ ] **Step 3: Verifica finale, tutto insieme**

```bash
cd backend && source .venv/bin/activate && python -m pytest tests -q
cd ../frontend && npx tsc --noEmit && npm run lint && npm run test:unit && npm run build
```
Expected: tutto verde. Riporta l'output vero.

- [ ] **Step 4: Commit**

```bash
git add frontend/e2e/smoke.spec.ts docs/API.md PROGRESS.md
git commit -m "docs+e2e: recepisce lente, gusto senza manopola e scaffale dichiarato"
```
