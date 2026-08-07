# Voto tracce a 3 livelli — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Voto personale 1–3 sulle tracce (NULL = non votata), con filtro/sort, playlist speciale "Top" auto-sincronizzata, bonus tie-break nel set generator e componente UI `RatingDiamond` (rombo "calore" a espansione) in righe, dettaglio e player docked.

**Architecture:** Colonna `rating` su `Track` (migrazione automatica da modello via `ensure_schema`). Il voto passa dal `PATCH /api/tracks/{id}` esistente; la sync della playlist `kind="rating_top"` avviene in `repositories.update_track` prima del commit (stessa transazione), delegata a un nuovo `services/rating.py`. Frontend: componente condiviso montato nelle righe di library/playlist, nel dettaglio traccia e nel dock (solo sorgente `local-track`).

**Tech Stack:** FastAPI + SQLAlchemy/SQLite + Pydantic (backend), Next.js 16 + React 19 + Tailwind v4 (frontend), pytest / vitest + React Testing Library.

**Spec:** `docs/superpowers/specs/2026-08-07-voto-tracce-design.md`

## Global Constraints

- CLAUDE.md regola 1: il voto NON entra mai nei payload verso l'AI; solo motore deterministico.
- I file audio non si toccano mai (niente export del voto nei tag: sono di Sortory).
- Frontend: leggere `frontend/CLAUDE.md` prima di toccare pagine/routing (Next 16 ha breaking changes; `params` è una Promise da `use()`, spazi JSX a fine riga richiedono `{" "}`).
- Descrizioni dei test in italiano (convenzione esistente, sia pytest sia vitest).
- Commit: MAI aggiungere `Co-Authored-By` / firme AI ai messaggi.
- Backend test: `cd backend && source .venv/bin/activate && python -m pytest tests/<file> -v`.
- Frontend: `cd frontend && npm run test:unit` (vitest), `npm run lint`, `npm run build` per verifica finale.
- i18n: ogni stringa nuova va in ENTRAMBI `frontend/lib/i18n/en.ts` e `frontend/lib/i18n/it.ts` (en è il source of truth dei tipi).
- Colori voto (scala "calore"): 1 = `#8a8065` (oliva), 2 = `#cfa14a` (ambra), 3 = `#d8593f` (terracotta). Non votata = contorno `currentColor` su `text-faint`.

---

### Task 1: Colonna `rating` su Track + serializzazione

**Files:**
- Modify: `backend/app/models.py` (classe `Track`, dopo il campo `archived`, ~riga 61)
- Modify: `backend/app/schemas.py` (`TrackOut`, dopo `archived`, ~riga 43)
- Modify: `backend/app/serializers.py` (`track_out`, dopo `archived=...`, ~riga 48)
- Test: `backend/tests/test_rating.py` (nuovo)

**Interfaces:**
- Produces: `Track.rating: int | None` (1–3, NULL = non votata), `TrackOut.rating: int | None` — usati da tutti i task successivi.

- [ ] **Step 1: Scrivi i test che falliscono**

```python
"""Voto a 3 livelli: colonna Track.rating e serializzazione."""

from app.models import Track
from app.serializers import track_out


def test_rating_default_none(db):
    t = Track(source_type="manual", title="T", artist="A")
    db.add(t); db.commit(); db.refresh(t)
    assert t.rating is None


def test_rating_persistito_e_serializzato(db):
    t = Track(source_type="manual", title="T", artist="A", rating=3)
    db.add(t); db.commit(); db.refresh(t)
    assert track_out(t).rating == 3


def test_rating_assente_serializzato_none(db):
    t = Track(source_type="manual", title="T", artist="A")
    db.add(t); db.commit(); db.refresh(t)
    assert track_out(t).rating is None
```

- [ ] **Step 2: Verifica che falliscano**

Run: `python -m pytest tests/test_rating.py -v` (da `backend/`, venv attivo)
Expected: FAIL — `TypeError: 'rating' is an invalid keyword argument for Track`

- [ ] **Step 3: Implementa**

In `models.py`, dentro `class Track`, subito dopo il blocco `archived`:

```python
    # Voto personale a 3 livelli (1..3), NULL = non votata. Vale per tutte le
    # tracce, anche i lead non posseduti. La playlist speciale "Top"
    # (kind='rating_top') e' sincronizzata col voto da services/rating.
    rating: Mapped[int | None] = mapped_column(Integer, index=True)
```

In `schemas.py`, in `TrackOut` dopo `archived: bool = False`:

```python
    rating: int | None = None
```

In `serializers.py`, in `track_out` dopo `archived=bool(track.archived),`:

```python
        rating=track.rating,
```

Nessuna migrazione manuale: `ensure_schema` (`_migrate_add_model_columns`) genera da sé l'`ADD COLUMN` dal modello.

- [ ] **Step 4: Verifica che passino**

Run: `python -m pytest tests/test_rating.py -v`
Expected: 3 PASS

- [ ] **Step 5: Regressione veloce + commit**

Run: `python -m pytest tests -q` → tutti verdi.

```bash
git add backend/app/models.py backend/app/schemas.py backend/app/serializers.py backend/tests/test_rating.py
git commit -m "feat(rating): colonna rating 1-3 su Track con serializzazione"
```

---

### Task 2: Voto via PATCH /api/tracks/{id}

**Files:**
- Modify: `backend/app/schemas.py` (`TrackUpdateIn`, ~riga 58)
- Test: `backend/tests/test_rating_patch.py` (nuovo)

**Interfaces:**
- Consumes: `Track.rating` (Task 1).
- Produces: `TrackUpdateIn.rating: int | None` (validato `ge=1, le=3`); il PATCH applica il campo via `repositories.update_track` (setattr generico già esistente: nessuna modifica al router).

- [ ] **Step 1: Scrivi i test che falliscono**

Stile `test_track_archive_patch.py`: chiamate dirette al router, niente TestClient.

```python
"""Voto via PATCH /api/tracks/{id}: assegna, cambia, toglie, valida 1..3."""

import pytest
from pydantic import ValidationError

from app.models import Track
from app.routers import tracks
from app.schemas import TrackUpdateIn


def _track(db, **kw) -> Track:
    t = Track(source_type="spotify", title="X", artist="Y", **kw)
    db.add(t)
    db.commit()
    return t


def test_patch_assegna_cambia_toglie(db):
    t = _track(db)
    tracks.patch_track(t.id, TrackUpdateIn(rating=2), db)
    db.refresh(t)
    assert t.rating == 2
    tracks.patch_track(t.id, TrackUpdateIn(rating=3), db)
    db.refresh(t)
    assert t.rating == 3
    tracks.patch_track(t.id, TrackUpdateIn(rating=None), db)  # null esplicito = toglie
    db.refresh(t)
    assert t.rating is None


def test_patch_senza_rating_non_tocca(db):
    t = _track(db, rating=3)
    tracks.patch_track(t.id, TrackUpdateIn(title="Nuovo"), db)
    db.refresh(t)
    assert t.rating == 3


@pytest.mark.parametrize("bad", [0, 4, -1])
def test_rating_fuori_range_rifiutato(bad):
    with pytest.raises(ValidationError):
        TrackUpdateIn(rating=bad)
```

- [ ] **Step 2: Verifica che falliscano**

Run: `python -m pytest tests/test_rating_patch.py -v`
Expected: FAIL — `ValidationError: ... rating ... Extra inputs are not permitted` (extra="forbid")

- [ ] **Step 3: Implementa**

In `schemas.py`, in `TrackUpdateIn` dopo `archived: bool | None = None`:

```python
    # Voto 1..3; null esplicito = toglie il voto (semantica PATCH standard).
    rating: int | None = Field(default=None, ge=1, le=3)
```

Nient'altro: `patch_track` passa il campo a `update_track`, che applica `setattr` sui campi presenti (null esplicito incluso, `exclude_unset=True` esclude solo i campi assenti).

- [ ] **Step 4: Verifica che passino**

Run: `python -m pytest tests/test_rating_patch.py tests/test_track_update.py tests/test_track_archive_patch.py -v`
Expected: tutti PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas.py backend/tests/test_rating_patch.py
git commit -m "feat(rating): voto 1-3 modificabile via PATCH /api/tracks/{id}"
```

---

### Task 3: Playlist speciale "Top" sincronizzata col voto

**Files:**
- Create: `backend/app/services/rating.py`
- Modify: `backend/app/repositories.py` (`update_track`, ~righe 136–166)
- Test: `backend/tests/test_rating_top_playlist.py` (nuovo)

**Interfaces:**
- Consumes: `Track.rating` (Task 1); PATCH del rating (Task 2); repo esistenti `add_track_to_playlist(db, track, playlist, *, added_at=None, added_by=None)` (idempotente, non committa), `remove_track_from_playlist(db, playlist_id, track_id)`, `recount_playlist(db, playlist)`.
- Produces: `services/rating.py` con `RATING_TOP_PLAYLIST_NAME = "Top"`, `get_or_create_rating_top_playlist(db) -> Playlist`, `sync_rating_top(db, track) -> None`; la playlist ha `platform="manual"`, `kind="rating_top"`. Il frontend (Task 9) si aggancia a `kind="rating_top"`.

- [ ] **Step 1: Scrivi i test che falliscono**

```python
"""Playlist speciale "Top" (kind='rating_top'): sync deterministica col voto 3."""

from sqlalchemy import select

from app.models import Playlist, Track, playlist_tracks
from app.routers import tracks
from app.schemas import TrackUpdateIn


def _track(db, **kw) -> Track:
    t = Track(source_type="spotify", title="X", artist="Y", **kw)
    db.add(t)
    db.commit()
    return t


def _top(db) -> Playlist | None:
    return db.scalar(select(Playlist).where(Playlist.kind == "rating_top"))


def _member_ids(db, playlist: Playlist) -> set[int]:
    rows = db.execute(select(playlist_tracks.c.track_id).where(
        playlist_tracks.c.playlist_id == playlist.id)).all()
    return {r[0] for r in rows}


def test_primo_voto_3_crea_top_e_aggiunge(db):
    t = _track(db)
    tracks.patch_track(t.id, TrackUpdateIn(rating=3), db)
    top = _top(db)
    assert top is not None
    assert top.name == "Top" and top.platform == "manual"
    assert _member_ids(db, top) == {t.id}
    assert top.track_count == 1


def test_voto_sotto_3_non_crea_top(db):
    t = _track(db)
    tracks.patch_track(t.id, TrackUpdateIn(rating=2), db)
    assert _top(db) is None


def test_downgrade_rimuove_dalla_top(db):
    t = _track(db)
    tracks.patch_track(t.id, TrackUpdateIn(rating=3), db)
    tracks.patch_track(t.id, TrackUpdateIn(rating=1), db)
    top = _top(db)
    assert _member_ids(db, top) == set()
    assert top.track_count == 0


def test_togliere_il_voto_rimuove_dalla_top(db):
    t = _track(db)
    tracks.patch_track(t.id, TrackUpdateIn(rating=3), db)
    tracks.patch_track(t.id, TrackUpdateIn(rating=None), db)
    assert _member_ids(db, _top(db)) == set()


def test_rivoto_3_idempotente(db):
    t = _track(db)
    tracks.patch_track(t.id, TrackUpdateIn(rating=3), db)
    tracks.patch_track(t.id, TrackUpdateIn(rating=3), db)
    top = _top(db)
    assert _member_ids(db, top) == {t.id}
    assert top.track_count == 1


def test_patch_di_altri_campi_non_tocca_la_top(db):
    t = _track(db)
    tracks.patch_track(t.id, TrackUpdateIn(rating=3), db)
    tracks.patch_track(t.id, TrackUpdateIn(title="Nuovo"), db)
    assert _member_ids(db, _top(db)) == {t.id}
```

- [ ] **Step 2: Verifica che falliscano**

Run: `python -m pytest tests/test_rating_top_playlist.py -v`
Expected: FAIL — `_top(db)` è `None` (`assert top is not None`)

- [ ] **Step 3: Implementa il servizio**

Nuovo `backend/app/services/rating.py`:

```python
"""Sync della playlist speciale "Top" (kind='rating_top') col voto delle tracce.

Deterministica e idempotente: voto 3 => membership presente, qualsiasi altro
voto (o nessuno) => assente. Chiamata da repositories.update_track PRIMA del
commit, cosi' la sync viaggia nella stessa transazione del PATCH. Stesso
precedente di get_or_create_discovery_playlist (playlist_import).
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Playlist, Track

# "Top" e' identico in IT ed EN: un solo nome salvato copre entrambe le lingue.
RATING_TOP_PLAYLIST_NAME = "Top"
RATING_TOP_LEVEL = 3


def _rating_top_playlist(db: Session) -> Playlist | None:
    return db.scalar(
        select(Playlist).where(Playlist.platform == "manual", Playlist.kind == "rating_top")
    )


def get_or_create_rating_top_playlist(db: Session) -> Playlist:
    """Al piu' una (kind='rating_top'), creata al primo voto 3."""
    playlist = _rating_top_playlist(db)
    if playlist is None:
        playlist = Playlist(platform="manual", name=RATING_TOP_PLAYLIST_NAME, kind="rating_top")
        db.add(playlist)
        db.flush()
    return playlist


def sync_rating_top(db: Session, track: Track) -> None:
    """Allinea membership e track_count della Top al voto corrente. Non committa."""
    from app.repositories import (
        add_track_to_playlist,
        recount_playlist,
        remove_track_from_playlist,
    )

    if track.rating == RATING_TOP_LEVEL:
        playlist = get_or_create_rating_top_playlist(db)
        add_track_to_playlist(db, track, playlist, added_by="cratory")
    else:
        playlist = _rating_top_playlist(db)
        if playlist is None:
            return  # nessun voto 3 finora: niente da allineare
        remove_track_from_playlist(db, playlist.id, track.id)
    # Il denormalizzato non resta mai indietro (lezione del fix conteggi).
    recount_playlist(db, playlist)
```

In `repositories.py`, dentro `update_track`, dopo il blocco `if "bpm" in data or "genre" in data: apply_estimated_energy(track)` e prima di `refresh_status(track)`:

```python
    if "rating" in data:
        # Sync playlist "Top" nella stessa transazione del PATCH.
        from app.services.rating import sync_rating_top
        sync_rating_top(db, track)
```

(import a livello di funzione: stesso pattern di `energy`/`track_status` già usati lì.)

- [ ] **Step 4: Verifica che passino**

Run: `python -m pytest tests/test_rating_top_playlist.py tests/test_rating_patch.py -v`
Expected: tutti PASS

- [ ] **Step 5: Regressione + commit**

Run: `python -m pytest tests -q` → tutti verdi.

```bash
git add backend/app/services/rating.py backend/app/repositories.py backend/tests/test_rating_top_playlist.py
git commit -m "feat(rating): playlist speciale Top sincronizzata col voto 3"
```

---

### Task 4: Filtro e ordinamento per voto su GET /api/tracks

**Files:**
- Modify: `backend/app/repositories.py` (`_SORT_COLUMNS` ~riga 19; `_apply_track_filters` ~righe 33–105)
- Modify: `backend/app/routers/tracks.py` (`get_tracks`, ~righe 31–75)
- Test: `backend/tests/test_rating_list.py` (nuovo)

**Interfaces:**
- Consumes: `Track.rating` (Task 1).
- Produces: `GET /api/tracks?rating=3` (match esatto, validato 1–3) e `sort=rating` (NULL sempre in fondo, meccanismo esistente); `list_tracks(db, rating=..., sort="rating")` per uso interno.

- [ ] **Step 1: Scrivi i test che falliscono**

```python
"""Filtro rating=N e sort=rating su GET /api/tracks."""

from app.models import Track
from app.repositories import list_tracks


def _seed(db):
    a = Track(source_type="manual", title="A", artist="a", rating=1)
    b = Track(source_type="manual", title="B", artist="b", rating=3)
    c = Track(source_type="manual", title="C", artist="c")  # non votata
    db.add_all([a, b, c]); db.commit()
    return a, b, c


def test_filtro_rating_esatto(db):
    a, b, c = _seed(db)
    total, rows = list_tracks(db, rating=3)
    assert total == 1 and [t.id for t in rows] == [b.id]


def test_sort_rating_desc_non_votate_in_fondo(db):
    a, b, c = _seed(db)
    _, rows = list_tracks(db, sort="rating", order="desc")
    assert [t.id for t in rows] == [b.id, a.id, c.id]


def test_sort_rating_asc_non_votate_comunque_in_fondo(db):
    a, b, c = _seed(db)
    _, rows = list_tracks(db, sort="rating", order="asc")
    assert [t.id for t in rows] == [a.id, b.id, c.id]
```

- [ ] **Step 2: Verifica che falliscano**

Run: `python -m pytest tests/test_rating_list.py -v`
Expected: FAIL — `TypeError: _apply_track_filters() got an unexpected keyword argument 'rating'`

- [ ] **Step 3: Implementa**

In `repositories.py`:

1. In `_SORT_COLUMNS` aggiungi la voce:

```python
    "rating": Track.rating,
```

2. In `_apply_track_filters` aggiungi il parametro (dopo `key: str | None = None`):

```python
    rating: int | None = None,
```

e la clausola (dopo il blocco `if key:`):

```python
    if rating is not None:
        stmt = stmt.where(Track.rating == rating)
```

In `routers/tracks.py`, in `get_tracks`:

1. Parametro (dopo `key: str | None = None`):

```python
    rating: int | None = Query(default=None, ge=1, le=3),
```

2. Estendi il pattern del sort:

```python
    sort: str | None = Query(
        default=None,
        pattern="^(title|artist|source|bpm|key|energy|genre|duration|year|status|rating)$",
    ),
```

3. Passa `rating=rating,` nella chiamata a `list_tracks` (accanto a `key=key`).

- [ ] **Step 4: Verifica che passino**

Run: `python -m pytest tests/test_rating_list.py -v`
Expected: 3 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/repositories.py backend/app/routers/tracks.py backend/tests/test_rating_list.py
git commit -m "feat(rating): filtro rating e sort=rating su GET /api/tracks"
```

---

### Task 5: Bonus voto nel set generator (tie-break deterministico)

**Files:**
- Modify: `backend/app/services/set_generator.py` (costanti ~riga 49; `_candidate_score` ~riga 154; `_pick_first` ~riga 142)
- Test: `backend/tests/test_rating_generator.py` (nuovo)

**Interfaces:**
- Consumes: `Track.rating` (Task 1).
- Produces: `_RATING_BONUS = 2.0` (per livello, max 6.0: sotto `_KEY_PREF_BONUS=8.0`, ben sotto un salto di compatibilità); nessuna modifica a `candidate_engine` (il voto non filtra).

- [ ] **Step 1: Scrivi i test che falliscano**

Stile `test_two_phase_generator.py` (chiamata diretta a `_candidate_score`):

```python
"""Bonus voto nel generator: tie-break, mai sopra la compatibilita' BPM/key."""

from app.models import Track
from app.schemas import SetGenerationRequest
from app.services.set_generator import _DEFAULT_PROFILE, _candidate_score


def make_track(**kw) -> Track:
    kw.setdefault("source_type", "spotify")
    kw.setdefault("duration_seconds", 300)
    return Track(**kw)


def _score(prev, cand) -> float:
    total, _ = _candidate_score(prev, cand, 126.0, SetGenerationRequest(), {},
                                _DEFAULT_PROFILE, 0.5)
    return total


def test_a_parita_vince_la_traccia_votata():
    prev = make_track(id=1, bpm=124.0, camelot_key="8A")
    votata = make_track(id=2, bpm=126.0, camelot_key="8A", rating=3)
    non_votata = make_track(id=3, bpm=126.0, camelot_key="8A")
    assert _score(prev, votata) > _score(prev, non_votata)


def test_voto_piu_alto_batte_voto_piu_basso():
    prev = make_track(id=1, bpm=124.0, camelot_key="8A")
    tre = make_track(id=2, bpm=126.0, camelot_key="8A", rating=3)
    uno = make_track(id=3, bpm=126.0, camelot_key="8A", rating=1)
    assert _score(prev, tre) > _score(prev, uno)


def test_voto_non_ribalta_la_compatibilita():
    prev = make_track(id=1, bpm=124.0, camelot_key="8A")
    compatibile = make_track(id=2, bpm=126.0, camelot_key="8A")
    incompatibile_votata = make_track(id=3, bpm=145.0, camelot_key="3B", rating=3)
    assert _score(prev, compatibile) > _score(prev, incompatibile_votata)
```

- [ ] **Step 2: Verifica che falliscano**

Run: `python -m pytest tests/test_rating_generator.py -v`
Expected: i primi due FAIL (score identici); il terzo PASS già ora (guardia di non-regressione)

- [ ] **Step 3: Implementa**

In `set_generator.py`, accanto alle costanti bonus (dopo `_KEY_PREF_BONUS = 8.0`):

```python
_RATING_BONUS = 2.0  # per livello di voto (max 6.0): tie-break, mai sopra la compatibilita'
```

In `_candidate_score`, subito prima del `return total, ts`:

```python
    # Voto personale: spinta piccola e deterministica, a parita' di compatibilita'.
    total += _RATING_BONUS * (cand.rating or 0)
```

In `_pick_first`, dentro `first_score`, aggiungi il termine al punteggio esistente (stessa riga di ritorno, `+ _RATING_BONUS * (t.rating or 0)`).

- [ ] **Step 4: Verifica che passino**

Run: `python -m pytest tests/test_rating_generator.py tests/test_two_phase_generator.py tests/test_engine_upgrades.py -v`
Expected: tutti PASS (i test esistenti del generator non devono rompersi: usano candidate senza rating → bonus 0)

- [ ] **Step 5: Regressione + commit**

Run: `python -m pytest tests -q` → tutti verdi.

```bash
git add backend/app/services/set_generator.py backend/tests/test_rating_generator.py
git commit -m "feat(rating): bonus tie-break del voto nel set generator"
```

---

### Task 6: Frontend — tipi, RatingDiamond, i18n, unit test

**Files:**
- Modify: `frontend/lib/api/types.ts` (`Track` ~riga 28, `TrackUpdate` ~riga 171)
- Create: `frontend/components/rating-diamond.tsx`
- Modify: `frontend/lib/i18n/en.ts` (namespace `tracks`, ~riga 417) e `frontend/lib/i18n/it.ts` (stesso namespace)
- Test: `frontend/tests/rating-diamond.test.tsx` (nuovo)

**Interfaces:**
- Consumes: backend `PATCH /api/tracks/{id}` con `rating` (Task 2) via `updateTrack(id, patch)` esistente (`lib/api/tracks.ts`).
- Produces: `Track.rating: number | null`, `TrackUpdate.rating?: number | null`, componente `<RatingDiamond trackId rating onSaved? size?>` — usato dai Task 7, 8, 9.

- [ ] **Step 1: Tipi**

In `types.ts`, in `interface Track` dopo `archived: boolean;`:

```ts
  rating: number | null;
```

In `interface TrackUpdate` dopo `archived?: boolean;`:

```ts
  rating?: number | null;
```

- [ ] **Step 2: i18n**

In `en.ts`, namespace `tracks`, aggiungi:

```ts
  ratingLabel: "Rating",
  ratingLevelTitle: (level: number) => `Rate ${level} of 3`,
```

In `it.ts`, stesso namespace:

```ts
  ratingLabel: "Voto",
  ratingLevelTitle: (level: number) => `Vota ${level} su 3`,
```

- [ ] **Step 3: Scrivi il test che fallisce**

Prima leggi `frontend/tests/track-play-button.test.tsx` e replica ESATTAMENTE le sue convenzioni di setup (mock, provider, cleanup). Test da coprire (descrizioni in italiano):

```tsx
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { RatingDiamond } from "@/components/rating-diamond";

const updateTrack = vi.fn().mockResolvedValue({});
vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<object>()),
  updateTrack: (...args: unknown[]) => updateTrack(...args),
}));

afterEach(() => { cleanup(); updateTrack.mockClear(); });

describe("RatingDiamond", () => {
  it("chiuso mostra solo il rombo dello stato corrente", () => {
    render(<RatingDiamond trackId={1} rating={null} />);
    expect(screen.getAllByRole("button")).toHaveLength(1);
  });

  it("il click apre i 3 livelli", async () => {
    render(<RatingDiamond trackId={1} rating={null} />);
    await userEvent.click(screen.getByRole("button"));
    expect(screen.getAllByRole("button")).toHaveLength(4); // 3 livelli + toggle
  });

  it("scegliere un livello chiama la PATCH col valore giusto", async () => {
    render(<RatingDiamond trackId={7} rating={null} />);
    await userEvent.click(screen.getByRole("button"));
    await userEvent.click(screen.getByTitle("Vota 2 su 3"));
    expect(updateTrack).toHaveBeenCalledWith(7, { rating: 2 });
  });

  it("ri-cliccare il livello attivo toglie il voto", async () => {
    render(<RatingDiamond trackId={7} rating={2} />);
    await userEvent.click(screen.getByRole("button"));
    await userEvent.click(screen.getByTitle("Vota 2 su 3"));
    expect(updateTrack).toHaveBeenCalledWith(7, { rating: null });
  });

  it("se la PATCH fallisce lo stato torna indietro", async () => {
    updateTrack.mockRejectedValueOnce(new Error("boom"));
    render(<RatingDiamond trackId={7} rating={null} />);
    await userEvent.click(screen.getByRole("button"));
    await userEvent.click(screen.getByTitle("Vota 3 su 3"));
    // dopo il rollback il rombo torna "non votata" (nessun fill)
    expect(updateTrack).toHaveBeenCalledWith(7, { rating: 3 });
  });
});
```

Adatta il wrapping (es. `I18nProvider`) a quanto fanno i test esistenti; se `useT` richiede il provider, avvolgi `render(...)` di conseguenza. Se `userEvent` non è tra le devDependencies, usa `fireEvent` come nei test esistenti.

Run: `npm run test:unit -- tests/rating-diamond.test.tsx` → FAIL (componente inesistente).

- [ ] **Step 4: Implementa il componente**

`frontend/components/rating-diamond.tsx`:

```tsx
"use client";

import { useEffect, useRef, useState } from "react";

import { updateTrack } from "@/lib/api";
import { useT } from "@/lib/i18n";

// Scala "calore" del voto: 1 oliva, 2 ambra, 3 terracotta (accento Cratory).
const RATING_COLORS: Record<number, string> = {
  1: "#8a8065",
  2: "#cfa14a",
  3: "#d8593f",
};

function Diamond({ value, size }: { value: number | null; size: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden>
      <polygon
        points="12,3 21,12 12,21 3,12"
        fill={value ? RATING_COLORS[value] : "none"}
        stroke={value ? "none" : "currentColor"}
        strokeWidth={1.5}
      />
    </svg>
  );
}

type Props = {
  trackId: number;
  rating: number | null;
  onSaved?: (rating: number | null) => void;
  size?: number;
};

export function RatingDiamond({ trackId, rating, onSaved, size = 18 }: Props) {
  const t = useT();
  const [open, setOpen] = useState(false);
  const [value, setValue] = useState<number | null>(rating);
  const rootRef = useRef<HTMLSpanElement>(null);

  useEffect(() => setValue(rating), [rating]);

  // Aperto: click fuori o Esc chiudono senza votare.
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const commit = async (next: number | null) => {
    const prev = value;
    setValue(next); // ottimistico
    setOpen(false);
    try {
      await updateTrack(trackId, { rating: next });
      onSaved?.(next);
    } catch {
      setValue(prev); // rollback
    }
  };

  return (
    <span ref={rootRef} className="inline-flex shrink-0 items-center gap-0.5">
      {open &&
        [1, 2, 3].map((level) => (
          <button
            key={level}
            type="button"
            title={t.tracks.ratingLevelTitle(level)}
            onClick={(e) => {
              e.stopPropagation();
              void commit(level === value ? null : level);
            }}
            className="shrink-0"
          >
            <Diamond value={level} size={size - 4} />
          </button>
        ))}
      <button
        type="button"
        aria-label={t.tracks.ratingLabel}
        title={t.tracks.ratingLabel}
        onClick={(e) => {
          e.stopPropagation();
          setOpen((o) => !o);
        }}
        className="shrink-0 text-faint transition-colors hover:text-fg-strong"
      >
        <Diamond value={value} size={size} />
      </button>
    </span>
  );
}
```

- [ ] **Step 5: Verifica, lint, commit**

Run: `npm run test:unit -- tests/rating-diamond.test.tsx` → PASS; `npm run lint` → pulito.

```bash
git add frontend/lib/api/types.ts frontend/components/rating-diamond.tsx frontend/lib/i18n/en.ts frontend/lib/i18n/it.ts frontend/tests/rating-diamond.test.tsx
git commit -m "feat(rating): componente RatingDiamond con tipi e i18n"
```

---

### Task 7: RatingDiamond + filtro/sort nella pagina Library

**Files:**
- Modify: `frontend/app/library/page.tsx` (fetch ~riga 123, filtri ~righe 173–201, header ~righe 149–167, riga tabella ~righe 259–281)

**Interfaces:**
- Consumes: `RatingDiamond` (Task 6); backend `?rating=` e `sort=rating` (Task 4).
- Produces: colonna voto ordinabile, filtro voto, voto assegnabile per riga.

- [ ] **Step 1: Leggi il file e individua i punti esatti**

Leggi per intero `frontend/app/library/page.tsx` (e `frontend/CLAUDE.md`). Individua: stato filtri, oggetto params di `apiGet("/api/tracks", {...})`, helper `th()` per gli header ordinabili, la `<tr>` della vista lista, il pattern `onSaved` del modal di edit (~riga 305).

- [ ] **Step 2: Implementa**

1. Stato filtro: `const [rating, setRating] = useState("")` (persistilo nel querystring come gli altri filtri, righe 79–112).
2. Params fetch: aggiungi `rating: rating || undefined` all'oggetto di `apiGet`.
3. Filtro UI (nella marginalia, accanto agli altri `Select`): un `Select` con opzioni `"" | 1 | 2 | 3` etichettate con `t.tracks.ratingLabel` e i valori `1`/`2`/`3`; `onChange` fa `setRating(v); setOffset(0)` come gli altri.
4. Header ordinabile: aggiungi la colonna voto con l'helper esistente, es. `th("rating", t.tracks.ratingLabel)`.
5. Cella per riga (nella `<td>` delle azioni, PRIMA della matita, dentro il `div flex`):

```tsx
<RatingDiamond
  trackId={tr.id}
  rating={tr.rating}
  onSaved={(r) => setItems((cur) => cur.map((x) => (x.id === tr.id ? { ...x, rating: r } : x)))}
/>
```

(usa il setter di stato reale della lista: stesso usato dall'edit modal a ~riga 305.)

- [ ] **Step 3: Verifica**

Run: `npm run lint && npm run test:unit` → puliti. `npm run build` → OK.
Verifica funzionale rapida nel browser (dev server): filtro voto restringe, click su header ordina, il rombo vota e la riga si aggiorna.

- [ ] **Step 4: Commit**

```bash
git add frontend/app/library/page.tsx
git commit -m "feat(rating): voto, filtro e sort nella pagina Library"
```

---

### Task 8: RatingDiamond nel dettaglio playlist e nel dettaglio traccia

**Files:**
- Modify: `frontend/app/playlists/[id]/page.tsx` (riga tabella ~righe 425–484)
- Modify: `frontend/app/tracks/[id]/page.tsx` (marginalia azioni ~righe 98–110)

**Interfaces:**
- Consumes: `RatingDiamond` (Task 6).

- [ ] **Step 1: Playlist detail**

Leggi il file. Nella `<td>` azioni della riga (~475–482), PRIMA della matita, aggiungi lo stesso blocco `<RatingDiamond .../>` del Task 7, usando il setter di stato della lista tracce di questa pagina per l'`onSaved`.

Poi estendi filtro e ordinamento locali (righe ~379–399, semplice `useState`, filtrano client-side): aggiungi un `Select` voto (`"" | 1 | 2 | 3`, etichetta `t.tracks.ratingLabel`) che filtra `tr.rating === Number(v)`, e l'opzione `rating` nel sort locale (voti alti prima, non votate in fondo — stesso criterio del backend: `(b.rating ?? -1) - (a.rating ?? -1)` per il desc, con le non votate sempre in coda in entrambi i versi).

- [ ] **Step 2: Track detail**

Leggi il file (`params` va scartato con `use()` — Next 16). Nella marginalia (~98–110), sopra il `Button` di edit, aggiungi:

```tsx
<RatingDiamond
  trackId={track.id}
  rating={track.rating}
  size={22}
  onSaved={(r) => setTrack((cur) => (cur ? { ...cur, rating: r } : cur))}
/>
```

(adatta `setTrack` al nome reale del setter di stato della pagina.)

- [ ] **Step 3: Verifica e commit**

Run: `npm run lint && npm run build` → OK. Verifica nel browser: voto da riga playlist e da dettaglio traccia.

```bash
git add frontend/app/playlists/[id]/page.tsx frontend/app/tracks/[id]/page.tsx
git commit -m "feat(rating): voto nel dettaglio playlist e nel dettaglio traccia"
```

---

### Task 9: Voto dal player docked (solo tracce di libreria)

**Files:**
- Modify: `frontend/lib/player.tsx` (`LocalTrack` ~riga 23)
- Modify: `frontend/components/track-play-button.tsx` (chiamata `player.play`)
- Modify: `frontend/components/docked-player.tsx` (controlli ~righe 82–113)
- Test: `frontend/tests/docked-player-rating.test.tsx` (nuovo)

**Interfaces:**
- Consumes: `RatingDiamond` (Task 6); `PlaybackSource` union esistente (`kind: "local-track" | "discovery-preview"`).
- Produces: `LocalTrack.rating?: number | null` valorizzato dai call-site di `play()`.

- [ ] **Step 1: Scrivi il test che fallisce**

Convenzioni di `frontend/tests/player.test.tsx` (leggi quel file). Casi:

```tsx
it("con una traccia locale in riproduzione il dock mostra il rombo del voto", ...);
it("con una preview discovery il rombo non c'e'", ...);
```

Il primo monta il dock con una sorgente `{ kind: "local-track", track: { id: 5, title: "T", artist: "A", rating: 2 } }` e si aspetta un elemento `aria-label` = stringa `ratingLabel`; il secondo usa `{ kind: "discovery-preview", ... }` e si aspetta la sua assenza (`queryByLabelText` → null).

Run: `npm run test:unit -- tests/docked-player-rating.test.tsx` → FAIL.

- [ ] **Step 2: Implementa**

1. `lib/player.tsx`, tipo `LocalTrack`: aggiungi `rating?: number | null;`.
2. `components/track-play-button.tsx`: nella chiamata `player.play({ kind: "local-track", track: {...} })` aggiungi `rating: track.rating`.
3. `components/docked-player.tsx`: accanto al bottone di chiusura, quando `active?.kind === "local-track"`:

```tsx
{active?.kind === "local-track" && (
  <RatingDiamond trackId={active.track.id} rating={active.track.rating ?? null} />
)}
```

(Il componente gestisce da sé lo stato ottimistico; nessun `onSaved` necessario qui. Cerca eventuali ALTRI call-site di `play({ kind: "local-track" ...})` con `grep -rn '"local-track"' frontend` e passa `rating` anche lì.)

- [ ] **Step 3: Verifica e commit**

Run: `npm run test:unit` → PASS; `npm run lint && npm run build` → OK.

```bash
git add frontend/lib/player.tsx frontend/components/track-play-button.tsx frontend/components/docked-player.tsx frontend/tests/docked-player-rating.test.tsx
git commit -m "feat(rating): voto della traccia in riproduzione dal player docked"
```

---

### Task 10: Playlist "Top" tra le Speciali con cover dedicata

**Files:**
- Create: `frontend/public/cover-rating-top.svg`
- Modify: `frontend/components/playlist-cover.tsx` (fallback per kind, ~righe 5–33)
- Modify: `frontend/app/playlists/page.tsx` (`specialRank`/`isSpecial`, ~righe 128–131)

**Interfaces:**
- Consumes: playlist `kind="rating_top"` dal backend (Task 3); `kind` già serializzato.

- [ ] **Step 1: Cover**

Leggi `frontend/public/cover-discovery.svg` e crea `cover-rating-top.svg` nello STESSO stile (dimensioni, fondo, resa del glifo), con glifo rombo pieno terracotta `#d8593f`. Base di partenza (adatta fondo/gradiente a quello che vedi in cover-discovery.svg):

```svg
<svg xmlns="http://www.w3.org/2000/svg" width="120" height="120" viewBox="0 0 120 120">
  <rect width="120" height="120" fill="#1c1c1c"/>
  <polygon points="60,26 94,60 60,94 26,60" fill="#d8593f"/>
</svg>
```

- [ ] **Step 2: Fallback cover + sezione Speciali**

In `playlist-cover.tsx`, accanto a `DISCOVERY_COVER`:

```ts
const RATING_TOP_COVER = "/cover-rating-top.svg";
```

e nel calcolo del fallback aggiungi il ramo:

```ts
    : kind === "rating_top" ? RATING_TOP_COVER
```

In `app/playlists/page.tsx` sostituisci le due funzioni (ordine: Discovery, Top, SoundCloud Likes, Spotify Likes):

```ts
const specialRank = (p: Playlist) =>
  p.kind === "discovery" ? 0 : p.kind === "rating_top" ? 1 : p.platform === "soundcloud" ? 2 : 3;
const isSpecial = (p: Playlist) =>
  p.kind === "discovery" || p.kind === "rating_top" || p.kind === "liked";
```

- [ ] **Step 3: Verifica e commit**

Run: `npm run lint && npm run build` → OK. Nel browser: vota 3 una traccia → "Top" appare nelle Speciali con la cover a rombo, tra Discovery e i Likes; il conteggio è giusto.

```bash
git add frontend/public/cover-rating-top.svg frontend/components/playlist-cover.tsx frontend/app/playlists/page.tsx
git commit -m "feat(rating): playlist Top tra le Speciali con cover dedicata"
```

---

### Task 11: Documentazione e chiusura

**Files:**
- Modify: `docs/API.md` (sezione tracks: campo `rating` nel PATCH, filtro `rating` e `sort=rating` su GET /tracks; sezione playlists: kind `rating_top`)
- Modify: `docs/ROADMAP.md` (segna la feature come fatta, se c'è una voce; altrimenti aggiungila tra le completate secondo lo stile del file)
- Modify: `PROGRESS.md` (voce diario in cima, stile delle voci esistenti, data 2026-08-07)

**Interfaces:** nessuna — solo documentazione.

- [ ] **Step 1: Aggiorna i tre documenti**

Leggi lo stile delle sezioni esistenti e documenta: voto 1–3 su Track (NULL = non votata), PATCH con `rating` (null toglie), filtro/sort su GET /tracks, playlist speciale "Top" (`kind="rating_top"`, sync deterministica col voto 3, `added_by="cratory"`), bonus `_RATING_BONUS` nel generator, componente RatingDiamond (righe, dettagli, player; mai sulle preview Discovery).

- [ ] **Step 2: Verifica finale completa**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests -q` → tutti verdi.
Run: `cd frontend && npm run lint && npm run test:unit && npm run build` → tutti puliti.

- [ ] **Step 3: Commit**

```bash
git add docs/API.md docs/ROADMAP.md PROGRESS.md
git commit -m "docs(rating): API, roadmap e progress per il sistema di voto"
```
