# Lookup read-only per il bridge (fetta 3a) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cratory espone `GET /api/tracks/lookup` (sola lettura): DjOrganizer lo interroga per suggerire genere/etichetta/anno/identità durante la pulizia dei tag.

**Architecture:** Un endpoint read-only nel router tracks, match `ISRC → fuzzy artist+title` (riusa la semantica di matching esistente), risposta piatta con confidenza. Nessuna autenticazione (app locali mono-utente); nessuna scrittura.

**Tech Stack:** FastAPI/Pydantic/SQLAlchemy, pytest.

## Global Constraints

- Contratto CONDIVISO con DjOrganizer (piano 3b — non cambiarlo unilateralmente):
  - `GET /api/tracks/lookup?isrc=&artist=&title=` — richiede `isrc` OPPURE (`artist` E `title`), altrimenti **422**.
  - Risposta sempre **200** (mai 404): `{found, match: "isrc"|"fuzzy"|null, track_id, artist, title, genre, genre_secondary, label, year, confidence}`; `confidence`: 100 ISRC, 70 fuzzy, 0 non trovata (campi null).
- **Ordine delle route:** l'endpoint va dichiarato PRIMA di `GET /tracks/{track_id}`, altrimenti FastAPI prova a fare il parse di "lookup" come int.
- Test: `cd backend && .venv/bin/python -m pytest tests -q`. Branch: `feat/lookup-endpoint` da `master` (nessuna dipendenza dalle fette 1-2).
- Commenti/messaggi in italiano.

---

### Task 0: Branch

- [ ] **Step 1:**

```bash
cd /Users/lucadenegri/Develop/DJProject01
git checkout master && git checkout -b feat/lookup-endpoint
```

---

### Task 1: Schema + endpoint lookup

**Files:**
- Modify: `backend/app/schemas.py` (nuovo schema, dopo `TrackUpdateIn` ~riga 86)
- Modify: `backend/app/routers/tracks.py` (endpoint PRIMA di `get_track_detail`, ~riga 60)
- Test: `backend/tests/test_track_lookup.py`

**Interfaces:**
- Produces: `TrackLookupOut(BaseModel)` e `GET /api/tracks/lookup` come da contratto nei Global Constraints. Match fuzzy = uguaglianza case-insensitive (`ilike` senza wildcard) su artist E title.

- [ ] **Step 1: Test fallenti**

```python
# backend/tests/test_track_lookup.py
"""GET /api/tracks/lookup: bridge read-only per DjOrganizer."""
from fastapi.testclient import TestClient

from app.db import get_db
from app.main import app
from app.models import Track


def _client(db):
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app)


def _seed(db):
    db.add(Track(source_type="spotify", isrc="ISRC42", artist="Artist One",
                 title="Song A", genre="Techno", genre_secondary="Dub Techno",
                 label="Ostgut Ton", year=2023))
    db.commit()


def test_match_per_isrc(db):
    _seed(db)
    r = _client(db).get("/api/tracks/lookup", params={"isrc": "ISRC42"})
    body = r.json()
    assert r.status_code == 200
    assert body["found"] is True and body["match"] == "isrc" and body["confidence"] == 100
    assert body["genre"] == "Techno" and body["label"] == "Ostgut Ton" and body["year"] == 2023


def test_match_fuzzy_case_insensitive(db):
    _seed(db)
    r = _client(db).get("/api/tracks/lookup",
                        params={"artist": "artist one", "title": "song a"})
    body = r.json()
    assert body["found"] is True and body["match"] == "fuzzy" and body["confidence"] == 70


def test_non_trovata(db):
    _seed(db)
    r = _client(db).get("/api/tracks/lookup", params={"artist": "X", "title": "Y"})
    body = r.json()
    assert r.status_code == 200
    assert body["found"] is False and body["match"] is None and body["confidence"] == 0
    assert body["genre"] is None


def test_422_senza_parametri_sufficienti(db):
    _seed(db)
    assert _client(db).get("/api/tracks/lookup").status_code == 422
    assert _client(db).get("/api/tracks/lookup", params={"artist": "solo artista"}).status_code == 422


def test_route_ordering_track_detail_intatto(db):
    """/tracks/lookup non deve rompere /tracks/{id}."""
    _seed(db)
    client = _client(db)
    tid = client.get("/api/tracks").json()["items"][0]["id"]
    assert client.get(f"/api/tracks/{tid}").status_code == 200
```

Nota: se il `TestClient`+`dependency_overrides` non è il pattern dei test router esistenti (es. `test_local_import_router.py`), uniformarsi a quello reale; pulire l'override a fine test (`app.dependency_overrides.clear()`), ad esempio con una fixture.

- [ ] **Step 2: Run** `cd backend && .venv/bin/python -m pytest tests/test_track_lookup.py -q` → FAIL (404 / 422 su tutto: la route non esiste e `{track_id}` cattura "lookup").

- [ ] **Step 3: Implementazione**

In `backend/app/schemas.py`, dopo `TrackUpdateIn`:

```python
class TrackLookupOut(BaseModel):
    """Risposta del lookup read-only (bridge DjOrganizer): mai 404, sempre questo schema."""

    found: bool
    match: str | None = None  # "isrc" | "fuzzy" | None
    track_id: int | None = None
    artist: str | None = None
    title: str | None = None
    genre: str | None = None
    genre_secondary: str | None = None
    label: str | None = None
    year: int | None = None
    confidence: int = 0  # 100 = ISRC, 70 = fuzzy, 0 = non trovata
```

In `backend/app/routers/tracks.py`: aggiungere `TrackLookupOut` all'import da `app.schemas`, `select` da sqlalchemy e `Track` da `app.models`; poi, SOPRA `get_track_detail` (l'ordine conta):

```python
@router.get("/tracks/lookup", response_model=TrackLookupOut)
def lookup_track(
    db: Session = Depends(get_db),
    isrc: str | None = None,
    artist: str | None = None,
    title: str | None = None,
):
    """Lookup read-only per il bridge DjOrganizer: ISRC → fuzzy artist+title.

    Sola lettura: nessuna scrittura, nessun side-effect. Mai 404: `found=false`.
    """
    from sqlalchemy import select

    from app.models import Track

    if not isrc and not (artist and title):
        raise HTTPException(
            status_code=422,
            detail="Servono isrc oppure artist+title.",
        )
    hit, how, conf = None, None, 0
    if isrc:
        hit = db.scalar(select(Track).where(Track.isrc == isrc))
        if hit:
            how, conf = "isrc", 100
    if hit is None and artist and title:
        hit = db.scalar(select(Track).where(
            Track.artist.ilike(artist), Track.title.ilike(title)))
        if hit:
            how, conf = "fuzzy", 70
    if hit is None:
        return TrackLookupOut(found=False)
    return TrackLookupOut(
        found=True, match=how, track_id=hit.id,
        artist=hit.artist, title=hit.title,
        genre=hit.genre, genre_secondary=hit.genre_secondary,
        label=hit.label, year=hit.year, confidence=conf,
    )
```

(Spostare gli import a inizio file se lo stile del router lo preferisce — sì: `select` e `Track` in testa, coerente col codebase.)

- [ ] **Step 4: Run** file di test → PASS. Poi suite intera → verde.

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas.py backend/app/routers/tracks.py backend/tests/test_track_lookup.py
git commit -m "feat(bridge): GET /api/tracks/lookup read-only per DjOrganizer (ISRC→fuzzy)"
```

---

### Task 2: Documentare l'endpoint

**Files:**
- Modify: `docs/API.md` (sezione Tracks)

- [ ] **Step 1:** Aggiungere alla sezione Tracks di `docs/API.md`:

```markdown
### GET /api/tracks/lookup

Lookup read-only per il bridge DjOrganizer (sola lettura, mai 404).
Query: `isrc` oppure `artist`+`title` (altrimenti 422).
Risposta: `{found, match: "isrc"|"fuzzy"|null, track_id, artist, title, genre,
genre_secondary, label, year, confidence}` — confidence: 100 ISRC, 70 fuzzy, 0 non trovata.
```

- [ ] **Step 2: Commit**

```bash
git add docs/API.md
git commit -m "docs(bridge): documenta GET /api/tracks/lookup"
```

---

### Task 3: Verifica finale

- [ ] **Step 1:** `cd backend && .venv/bin/python -m pytest tests -q` → tutti verdi.
- [ ] **Step 2:** merge dopo code review della fetta.
