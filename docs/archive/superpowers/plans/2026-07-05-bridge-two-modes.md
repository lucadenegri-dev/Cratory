# Bridge Cratory a due modalità (Riempi/Importa) + match per path — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dare a "Suggerisci da Cratory" due modalità distinte — **Riempi** (colma solo i buchi, mai tocca un campo già valorizzato) e **Importa** (propone anche sovrascritture, solo con match certo, mai svuota) — e permettere il match certo anche senza ISRC, tramite il path assoluto del file collegato in Cratory.

**Architecture:** Il contratto HTTP `GET /api/tracks/lookup` di Cratory guadagna un parametro opzionale `path`, con priorità di match `path` > `isrc` > fuzzy artist+title. Il client bridge di DjOrganizer passa sempre il path assoluto del file. L'endpoint `POST /api/issues/bridge-suggest` di DjOrganizer accetta un body `{"mode": "fill"|"import"}`: `fill` è il comportamento attuale depurato (mai discrepanze), `import` aggiunge il check discrepanze esteso a tutti i file con match certo (path o ISRC) e a tutti e 6 i campi del contratto. Il frontend espone due pulsanti al posto di uno.

**Tech Stack:** FastAPI + SQLAlchemy + pytest (entrambi i backend), Next.js/React + TypeScript (frontend DjOrganizer). Nessuna nuova dipendenza.

## Global Constraints

- Priorità di match nel lookup Cratory: `path` > `isrc` > fuzzy artist+title (confidence 100/100/70).
- Modalità `import`: sovrascritture proposte **solo** con `match in ("path", "isrc")`. Mai con match fuzzy.
- Genere: sovrascrittura proposta solo se `genre_source ∈ {"manual", "provider"}` — sia in `fill` (già vero oggi per i mismatch) sia in `import`.
- Mai proporre un valore vuoto/null: se Cratory non ha il campo, quel campo si salta.
- Modalità `fill` = default se il body è assente (retro-compatibilità con la POST senza body).
- `mode` invalido → 422.
- Nessuna auto-accettazione: ogni suggerimento (fill o import) resta `status="open"`, da rivedere.
- Cratory irraggiungibile → rollback completo, risposta "non configurato" (comportamento invariato).
- I file `AudioFile.path` in DjOrganizer sono **già path assoluti** (costruiti da `os.walk(root.path)` in `scanner.py`, confermato dai fixture di test `path=f"/m/{file_id}.mp3"`): nessuna ricostruzione root+relativo necessaria.

---

## Repo A: DJProject01 (Cratory)

### Task 1: Lookup per path in Cratory

**Files:**
- Modify: `/Users/lucadenegri/Develop/DJProject01/backend/app/routers/tracks.py:80-116` (`lookup_track`)
- Modify: `/Users/lucadenegri/Develop/DJProject01/backend/app/schemas.py:98-112` (`TrackLookupOut`, solo commento `match`)
- Test: `/Users/lucadenegri/Develop/DJProject01/backend/tests/test_track_lookup.py`

**Interfaces:**
- Consumes: `Track.local_path` (già esistente, `models.py:46`), normalizzazione già usata in `acquisition.link_local_file` (`Path(path).expanduser()`).
- Produces: `GET /api/tracks/lookup?path=...` → stesso `TrackLookupOut` di oggi, con `match` che può valere anche `"path"` (confidence 100). Questo è ciò che il Task 3 (client DjOrganizer) consumerà.

- [ ] **Step 1: Scrivi i test falliti per il match per path**

Aggiungi in fondo a `backend/tests/test_track_lookup.py`:

```python
def test_match_per_path(lookup_db, client):
    lookup_db.add(Track(source_type="local_files", local_path="/music/Artist/Song.flac",
                        artist="Artist One", title="Song A", genre="Techno",
                        label="Ostgut Ton", year=2023))
    lookup_db.commit()
    r = client.get("/api/tracks/lookup", params={"path": "/music/Artist/Song.flac"})
    body = r.json()
    assert body["found"] is True
    assert body["match"] == "path" and body["confidence"] == 100
    assert body["genre"] == "Techno"


def test_match_per_path_espande_tilde_e_normalizza(lookup_db, client):
    lookup_db.add(Track(source_type="local_files",
                        local_path=str(Path("~/Music/Song.mp3").expanduser()),
                        artist="Someone", title="Track"))
    lookup_db.commit()
    r = client.get("/api/tracks/lookup", params={"path": "~/Music/Song.mp3"})
    assert r.json()["found"] is True and r.json()["match"] == "path"


def test_match_per_path_precede_isrc(lookup_db, client):
    """Stesso file collegato per path a una traccia diversa da quella con l'ISRC:
    il path vince (è il match più certo, deciso a mano da Luca in Cratory)."""
    lookup_db.add(Track(source_type="spotify", isrc="ISRC-OLD", artist="Old Artist",
                        title="Old Title"))
    lookup_db.add(Track(source_type="local_files", local_path="/music/real.flac",
                        isrc="ISRC-OLD", artist="Real Artist", title="Real Title"))
    lookup_db.commit()
    r = client.get("/api/tracks/lookup",
                    params={"path": "/music/real.flac", "isrc": "ISRC-OLD"})
    body = r.json()
    assert body["match"] == "path"
    assert body["artist"] == "Real Artist"


def test_match_per_path_non_trovato_ricade_su_isrc(lookup_db, client):
    _seed(lookup_db)
    r = client.get("/api/tracks/lookup",
                    params={"path": "/nessuno/qui.mp3", "isrc": "ISRC42"})
    body = r.json()
    assert body["match"] == "isrc"


def test_path_ignoto_senza_altre_chiavi_e_not_found(lookup_db, client):
    r = client.get("/api/tracks/lookup", params={"path": "/nessuno/qui.mp3"})
    body = r.json()
    assert body["found"] is False and body["match"] is None


def test_422_path_vuoto_senza_altre_chiavi(lookup_db, client):
    assert client.get("/api/tracks/lookup", params={"path": ""}).status_code == 422
```

Aggiungi l'import mancante in cima al file:

```python
from pathlib import Path
```

- [ ] **Step 2: Esegui i test e verifica che falliscano**

Run: `cd /Users/lucadenegri/Develop/DJProject01/backend && .venv/bin/python -m pytest tests/test_track_lookup.py -v`
Expected: FAIL su tutti i nuovi test (422 mancante per `path` da solo, `match` non contempla `"path"`, nessun confronto su `local_path`).

- [ ] **Step 3: Implementa il match per path**

In `backend/app/routers/tracks.py`, sostituisci la funzione `lookup_track`:

```python
@router.get("/tracks/lookup", response_model=TrackLookupOut)
def lookup_track(
    db: Session = Depends(get_db),
    path: str | None = None,
    isrc: str | None = None,
    artist: str | None = None,
    title: str | None = None,
):
    """Lookup read-only per il bridge DjOrganizer: path -> ISRC -> fuzzy artist+title.

    Sola lettura: nessuna scrittura, nessun side-effect. Mai 404: `found=false`.
    """
    if not path and not isrc and not (artist and title):
        raise HTTPException(
            status_code=422,
            detail="Servono path, isrc oppure artist+title.",
        )
    # limit(1): eventuali duplicati (stesso path/ISRC/artist+title) non devono
    # far fallire il lookup con MultipleResultsFound — si risponde col primo match.
    hit, how, conf = None, None, 0
    if path:
        normalized = str(Path(path).expanduser())
        hit = db.scalars(
            select(Track).where(Track.local_path == normalized).limit(1)
        ).first()
        if hit:
            how, conf = "path", 100
    if hit is None and isrc:
        hit = db.scalars(select(Track).where(Track.isrc == isrc).limit(1)).first()
        if hit:
            how, conf = "isrc", 100
    if hit is None and artist and title:
        hit = db.scalars(select(Track).where(
            Track.artist.ilike(artist), Track.title.ilike(title)).limit(1)).first()
        if hit:
            how, conf = "fuzzy", 70
    if hit is None:
        return TrackLookupOut(found=False)
    return TrackLookupOut(
        found=True, match=how, track_id=hit.id,
        artist=hit.artist, title=hit.title,
        genre=hit.genre, genre_secondary=hit.genre_secondary,
        genre_source=hit.genre_source, album=hit.album,
        label=hit.label, year=hit.year, confidence=conf,
    )
```

Aggiungi l'import in cima al file:

```python
from pathlib import Path
```

In `backend/app/schemas.py`, aggiorna solo il commento del campo `match` in `TrackLookupOut`:

```python
    match: str | None = None  # "path" | "isrc" | "fuzzy" | None
```

- [ ] **Step 4: Esegui i test e verifica che passino**

Run: `cd /Users/lucadenegri/Develop/DJProject01/backend && .venv/bin/python -m pytest tests/test_track_lookup.py -v`
Expected: PASS su tutti i test (vecchi e nuovi).

- [ ] **Step 5: Esegui l'intera suite di Cratory (nessuna regressione)**

Run: `cd /Users/lucadenegri/Develop/DJProject01/backend && .venv/bin/python -m pytest tests -q`
Expected: PASS, nessun fallimento.

- [ ] **Step 6: Aggiorna il contratto in API.md**

In `/Users/lucadenegri/Develop/DJProject01/docs/API.md`, sostituisci il paragrafo (righe 73-76):

```text
`GET /api/tracks/lookup` — lookup read-only per il bridge DjOrganizer (sola lettura,
mai 404). Query: `path` (path assoluto del file collegato via link-file/indicizzazione),
`isrc` oppure `artist`+`title` (almeno una chiave, altrimenti 422). Priorità di match:
path > isrc > fuzzy artist+title. Risposta:
`{found, match: "path"|"isrc"|"fuzzy"|null, track_id, artist, title, genre, genre_secondary,
genre_source, album, label, year, confidence}` — confidence: 100 path/ISRC, 70 fuzzy, 0 non trovata.
```

- [ ] **Step 7: Commit**

```bash
cd /Users/lucadenegri/Develop/DJProject01
git add backend/app/routers/tracks.py backend/app/schemas.py backend/tests/test_track_lookup.py docs/API.md
git commit -m "feat: lookup tracks per path assoluto (bridge DjOrganizer, match certo senza ISRC)"
```

---

## Repo B: DjOrganizer01

### Task 2: Client bridge — passa il path assoluto

**Files:**
- Modify: `backend/app/services/cratory_bridge.py`
- Test: `backend/tests/test_cratory_bridge.py`

**Interfaces:**
- Consumes: nessuna dipendenza da altri task di questo repo.
- Produces: `cratory_bridge.lookup(base_url, path=None, isrc=None, artist=None, title=None) -> dict`. Il Task 3 (endpoint) chiama sempre `lookup(base_url, path=f.path, isrc=..., artist=..., title=...)`.

- [ ] **Step 1: Scrivi i test falliti**

Aggiungi in fondo a `backend/tests/test_cratory_bridge.py`:

```python
def test_lookup_by_path(monkeypatch):
    captured = {}

    def fake_get(url, params=None, timeout=None):
        captured.update(url=url, params=params, timeout=timeout)
        return _resp(dict(BODY, match="path"))

    monkeypatch.setattr(cratory_bridge.httpx, "get", fake_get)
    body = cratory_bridge.lookup("http://localhost:8000", path="/music/song.flac")
    assert body["match"] == "path"
    assert captured["params"] == {"path": "/music/song.flac"}


def test_lookup_combina_path_isrc_e_artist_title(monkeypatch):
    """Tutte le chiavi disponibili vengono mandate insieme: Cratory applica la priorità."""
    captured = {}

    def fake_get(url, params=None, timeout=None):
        captured.update(params=params)
        return _resp(BODY)

    monkeypatch.setattr(cratory_bridge.httpx, "get", fake_get)
    cratory_bridge.lookup("http://localhost:8000", path="/m/1.mp3", isrc="X",
                          artist="A", title="T")
    assert captured["params"] == {"path": "/m/1.mp3", "isrc": "X",
                                  "artist": "A", "title": "T"}


def test_lookup_senza_identita_solleva_valueerror_anche_con_path_vuoto(monkeypatch):
    fake_get_called = []

    def fake_get(url, params=None, timeout=None):
        fake_get_called.append(True)
        return _resp(BODY)

    monkeypatch.setattr(cratory_bridge.httpx, "get", fake_get)
    with pytest.raises(ValueError):
        cratory_bridge.lookup("http://localhost:8000", path="")
    assert not fake_get_called
```

- [ ] **Step 2: Esegui i test e verifica che falliscano**

Run: `cd backend && .venv/bin/python -m pytest tests/test_cratory_bridge.py -v`
Expected: FAIL su `test_lookup_by_path` e `test_lookup_combina_path_isrc_e_artist_title` (`lookup()` non accetta ancora `path`).

- [ ] **Step 3: Implementa il parametro `path`**

Sostituisci in `backend/app/services/cratory_bridge.py` la firma e il corpo di `lookup`:

```python
def lookup(base_url: str, path: str | None = None, isrc: str | None = None,
           artist: str | None = None, title: str | None = None) -> dict:
    """GET {base_url}/api/tracks/lookup. Contratto: serve path, isrc oppure artist+title.

    Ritorna il body JSON del contratto:
    {"found": bool, "match": "path"|"isrc"|"fuzzy"|None, "track_id": int|None,
     "artist": ..., "title": ..., "genre": ..., "genre_secondary": ...,
     "genre_source": "manual"|"provider"|"ai"|"file_tag"|None,
     "album": ..., "label": ..., "year": ..., "confidence": 100|70|0}
    Solleva CratoryUnreachable su timeout, errore di rete o status != 2xx.
    Solleva ValueError se mancano path, isrc e artist+title.
    """
    # Guardia lato client: contratto Cratory richiede path, isrc oppure artist+title.
    if not path and not isrc and not (artist and title):
        raise ValueError("lookup richiede path, isrc oppure artist+title")

    params: dict[str, str] = {}
    if path:
        params["path"] = path
    if isrc:
        params["isrc"] = isrc
    if artist:
        params["artist"] = artist
    if title:
        params["title"] = title
    try:
        resp = httpx.get(f"{base_url.rstrip('/')}/api/tracks/lookup",
                         params=params, timeout=_TIMEOUT_S)
        resp.raise_for_status()
        return resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        # Cattura sia errori di rete/status che ValueError da json() malformato.
        raise CratoryUnreachable(str(exc)) from exc
```

Aggiorna anche il docstring del modulo (riga 2) sostituendo "Solo GET /api/tracks/lookup" con lo stesso testo (nessuna modifica di sostanza necessaria lì).

- [ ] **Step 4: Esegui i test e verifica che passino**

Run: `cd backend && .venv/bin/python -m pytest tests/test_cratory_bridge.py -v`
Expected: PASS su tutti i test (vecchi e nuovi).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/cratory_bridge.py backend/tests/test_cratory_bridge.py
git commit -m "feat: client bridge passa il path assoluto del file a Cratory"
```

---

### Task 3: Endpoint bridge-suggest a due modalità

**Files:**
- Modify: `backend/app/schemas.py` (nuovo `BridgeSuggestBody`)
- Modify: `backend/app/routers/issues.py:200-331`
- Test: `backend/tests/test_bridge_suggest_api.py`

**Interfaces:**
- Consumes: `cratory_bridge.lookup(base_url, path=, isrc=, artist=, title=)` dal Task 2.
- Produces: `POST /api/issues/bridge-suggest` con body opzionale `{"mode": "fill"|"import"}` (default `"fill"`). Risposta: `{"configured": bool, "mode": str, "files": int, "suggested": int, "unresolved": int, "mismatches": int}`. Il Task 4 (frontend) chiama `bridgeSuggest(mode)` e legge `mode` dalla risposta.

- [ ] **Step 1: Aggiungi lo schema del body**

In `backend/app/schemas.py`, aggiungi dopo `IssueFixBody` (riga 74):

```python
class BridgeSuggestBody(BaseModel):
    mode: str = "fill"
```

- [ ] **Step 2: Scrivi i test falliti per `mode=fill` (comportamento depurato, niente mismatch)**

In `backend/tests/test_bridge_suggest_api.py`, aggiungi in fondo al file. Nota: `FOUND` e `NOT_FOUND` vanno estesi con la chiave `"path"` mancante non serve (i mock non la leggono); i test esistenti restano tutti validi e continuano a passare invariati perché `mode` default è `"fill"` **solo per i test che non creano mismatch** — i test esistenti che verificano `mismatches` con ISRC (es. `test_bridge_mismatch_on_isrc_conflict`) vanno aggiornati per chiamare esplicitamente `mode=import`, dato che il default ora è `fill` e `fill` non genera mai mismatch.

Aggiorna queste chiamate esistenti da `client.post("/api/issues/bridge-suggest")` a `client.post("/api/issues/bridge-suggest", json={"mode": "import"})` nei seguenti test (sono gli unici che asseriscono `mismatches > 0` o testano la logica di discrepanza):
- `test_bridge_mismatch_on_isrc_conflict` (righe 177-197, incluso il secondo run idempotente riga 194)
- `test_bridge_mismatch_skipped_without_isrc` (righe 199-211)
- `test_bridge_mismatch_resolved_is_removed` (righe 214-228)
- `test_bridge_mismatch_dismissed_untouched_when_conflict_persists` (righe 251-276)
- `test_bridge_mismatch_open_row_updated_when_conflict_changes` (righe 279-305)
- `test_mismatch_genere_da_fonte_affidabile` (righe 343-356)
- `test_niente_mismatch_genere_da_fonte_debole` (righe 359-369)
- `test_niente_mismatch_genere_se_uguale_normalizzato` (righe 372-379)
- `test_mismatch_genere_salta_genere_assente` (righe 382-390)

Tutti gli altri test esistenti (fill di issue aperte, unresolved, unreachable, riempimento album) restano puro riempimento e in `mode=fill` si comportano identicamente **tranne due, che vanno riscritti** perché il client ora manda SEMPRE il path insieme a isrc/artist/title (non più una chiave sola per chiamata) e i loro mock hanno una firma esplicita che non accetta `path`:

In `test_bridge_fills_missing_metadata_via_isrc` (righe 38-68), sostituisci il blocco `fake`/asserzioni sulle chiamate:

```python
def fake(base_url, path=None, isrc=None, artist=None, title=None):
    calls.append({"base_url": base_url, "path": path, "isrc": isrc,
                  "artist": artist, "title": title})
    return dict(FOUND)

monkeypatch.setattr(cratory_bridge, "lookup", fake)
with TestClient(app) as client:
    r = client.post("/api/issues/bridge-suggest").json()
    assert r == {"configured": True, "mode": "fill", "files": 1, "suggested": 3,
                 "unresolved": 0, "mismatches": 0}
    # una sola chiamata HTTP per file (cache): path + isrc + artist/title insieme
    assert calls == [{"base_url": "http://localhost:8000", "path": "/m/1.mp3",
                      "isrc": "DEAB12300123", "artist": "Rataxes", "title": "Acid Face"}]
```

(il resto del test — lettura delle issue `missing_metadata` e relative asserzioni — resta invariato.)

In `test_bridge_fuzzy_fills_dirty_genre` (righe 89-109), sostituisci il blocco `fake`/asserzioni sulle chiamate:

```python
def fake(base_url, path=None, isrc=None, artist=None, title=None):
    calls.append({"path": path, "isrc": isrc, "artist": artist, "title": title})
    return dict(FOUND, match="fuzzy", confidence=70)

monkeypatch.setattr(cratory_bridge, "lookup", fake)
with TestClient(app) as client:
    r = client.post("/api/issues/bridge-suggest").json()
    assert r["suggested"] == 1 and r["mismatches"] == 0  # fuzzy: mai mismatch
    assert calls == [{"path": "/m/3.mp3", "isrc": None,
                      "artist": "Rataxes", "title": "Acid Face"}]
```

(il resto del test — lettura della issue `dirty_genre` — resta invariato.)

**`test_bridge_mismatch_orphan_removed_when_isrc_lost` (righe 231-248) va invece SOSTITUITO, non solo aggiornato nel mode.** Il suo presupposto ("il file perde l'ISRC quindi la riga diventa orfana") non vale più: ora la pulizia orfani (Step 2) dipende solo da `AudioFile.status != "present"`, non più dalla presenza dell'ISRC (il path è sempre disponibile e usabile come chiave). Sostituisci l'intero test con:

```python
def test_bridge_mismatch_orphan_removed_when_file_not_present(db, monkeypatch):
    """Riga bridge_mismatch il cui file non e' piu' 'present' (spostato/rimosso
    dal disco): la riga orfana (step 2) va ripulita in ENTRAMBE le modalita',
    a prescindere da ISRC/path — e' pulizia di stato, non ri-verifica."""
    _file(db, 12, artist="Sconosciuto", title="Acid Face", isrc=None,
          status="missing")
    db.add(Issue(file_id=12, type="bridge_mismatch", field="artist",
                 severity="warning", detail="vecchia discrepanza",
                 suggested_fix_json={"field": "artist", "action": "retag",
                                     "to": "Rataxes"},
                 status="open"))
    db.commit()
    _configure(db)
    monkeypatch.setattr(cratory_bridge, "lookup", lambda *a, **k: dict(FOUND))
    with TestClient(app) as client:
        client.post("/api/issues/bridge-suggest")  # default mode=fill: la pulizia orfani gira comunque
        rows = db.execute(
            select(Issue).where(Issue.file_id == 12, Issue.type == "bridge_mismatch")
        ).scalars().all()
        assert rows == []
```

Aggiungi anche l'aggiornamento delle costanti `EMPTY` in cima al file (riga 16-17), che ora deve includere `mode`. Sostituisci:

```python
EMPTY = {"configured": False, "files": 0, "suggested": 0,
         "unresolved": 0, "mismatches": 0}
```

con:

```python
EMPTY = {"configured": False, "files": 0, "suggested": 0,
         "unresolved": 0, "mismatches": 0}


def _empty_for(mode="fill"):
    return dict(EMPTY, mode=mode)
```

Questo helper serve solo al nuovo test `test_bridge_import_non_configurato` più sotto (`mode=import` non configurato); i due test esistenti che confrontavano con `EMPTY` restano con `dict(EMPTY, mode="fill")` inline (vedi le sostituzioni esatte più avanti in questo step).

Aggiungi questi nuovi test in fondo al file:

```python
def test_bridge_fill_non_crea_mismatch_anche_con_isrc_diverso(db, monkeypatch):
    """mode=fill (o default): mai discrepanze, anche se Cratory differisce via ISRC."""
    _configure(db)
    _file(db, 20, artist="Sconosciuto", title="Acid Face", genre="Acid Techno",
          year=2024, label="Bunker", isrc="DEAB12300123")
    db.commit()
    monkeypatch.setattr(cratory_bridge, "lookup", lambda *a, **k: dict(FOUND))
    with TestClient(app) as client:
        r = client.post("/api/issues/bridge-suggest").json()
        assert r["mode"] == "fill"
        assert r["mismatches"] == 0
        assert client.get("/api/issues", params={"type": "bridge_mismatch"}).json() == []


def test_bridge_fill_non_tocca_campo_gia_valorizzato(db, monkeypatch):
    """mode=fill non crea suggerimenti su campi con valore, solo su issue aperte."""
    _configure(db)
    _file(db, 21, artist="Rataxes", title="Acid Face", genre="Electro",
          isrc="DEAB12300123")
    db.commit()
    monkeypatch.setattr(cratory_bridge, "lookup", lambda *a, **k: dict(FOUND))
    with TestClient(app) as client:
        r = client.post("/api/issues/bridge-suggest", json={"mode": "fill"}).json()
        assert r["suggested"] == 0 and r["mismatches"] == 0


def test_bridge_mode_invalido_422(db):
    _configure(db)
    with TestClient(app) as client:
        assert client.post("/api/issues/bridge-suggest",
                           json={"mode": "boh"}).status_code == 422


def test_bridge_import_usa_il_path_assoluto_del_file(db, monkeypatch):
    _configure(db)
    _file(db, 22, path="/music/real/song.flac", artist="Rataxes", title="Acid Face",
          isrc=None)
    db.commit()
    calls = []

    def fake(base_url, path=None, isrc=None, artist=None, title=None):
        calls.append(path)
        return dict(NOT_FOUND)

    monkeypatch.setattr(cratory_bridge, "lookup", fake)
    with TestClient(app) as client:
        client.post("/api/issues/bridge-suggest", json={"mode": "import"})
        assert calls == ["/music/real/song.flac"]


def test_bridge_import_propone_sovrascrittura_con_match_path(db, monkeypatch):
    _configure(db)
    _file(db, 23, path="/music/real/song.flac", artist="Nome Vecchio",
          title="Acid Face", genre="Acid Techno", year=2024, label="Bunker",
          album="Bunker EP", isrc=None)
    db.commit()
    monkeypatch.setattr(cratory_bridge, "lookup",
                        lambda *a, **k: dict(FOUND, match="path"))
    with TestClient(app) as client:
        r = client.post("/api/issues/bridge-suggest", json={"mode": "import"}).json()
        assert r["mismatches"] == 1
        rows = client.get("/api/issues", params={"type": "bridge_mismatch"}).json()
        assert rows[0]["field"] == "artist"
        assert rows[0]["suggested_fix_json"]["to"] == "Rataxes"


def test_bridge_import_non_propone_con_match_fuzzy(db, monkeypatch):
    _configure(db)
    _file(db, 24, artist="Nome Vecchio", title="Acid Face", genre="Acid Techno",
          year=2024, label="Bunker", album="Bunker EP", isrc=None)
    db.commit()
    monkeypatch.setattr(cratory_bridge, "lookup",
                        lambda *a, **k: dict(FOUND, match="fuzzy", confidence=70))
    with TestClient(app) as client:
        r = client.post("/api/issues/bridge-suggest", json={"mode": "import"}).json()
        assert r["mismatches"] == 0


def test_bridge_import_sovrascrive_piu_campi_con_match_path(db, monkeypatch):
    """FOUND ha artist=Rataxes/title=Acid Face/genre=Acid Techno (provider)/
    year=2024/label=Bunker/album=Bunker EP. Il file allinea artist/title/genre
    e diverge solo su year/label/album: dimostra che il check e' esteso oltre
    i 3 campi originali (artist/title/genre) a tutti e 6."""
    _configure(db)
    _file(db, 25, path="/m/25.mp3", artist="Rataxes", title="Acid Face",
          genre="Acid Techno", year=1999, label="Vecchia Label",
          album="Vecchio Album", isrc=None)
    db.commit()
    monkeypatch.setattr(cratory_bridge, "lookup",
                        lambda *a, **k: dict(FOUND, match="path"))
    with TestClient(app) as client:
        r = client.post("/api/issues/bridge-suggest", json={"mode": "import"}).json()
        assert r["mismatches"] == 3  # year, label, album
        rows = client.get("/api/issues", params={"type": "bridge_mismatch"}).json()
        by_field = {i["field"]: i["suggested_fix_json"]["to"] for i in rows}
        assert by_field["year"] == 2024
        assert by_field["label"] == "Bunker"
        assert by_field["album"] == "Bunker EP"
        assert "artist" not in by_field and "genre" not in by_field  # gia' allineati


def test_bridge_import_non_svuota_campo_assente_in_cratory(db, monkeypatch):
    """Cratory non ha year: il file mantiene il suo, nessuna proposta di svuotamento."""
    _configure(db)
    _file(db, 26, path="/m/26.mp3", artist="Rataxes", title="Acid Face",
          genre="Acid Techno", year=2024, label="Bunker", isrc=None)
    db.commit()
    remote = dict(FOUND, match="path", year=None)
    monkeypatch.setattr(cratory_bridge, "lookup", lambda *a, **k: remote)
    with TestClient(app) as client:
        r = client.post("/api/issues/bridge-suggest", json={"mode": "import"}).json()
        rows = client.get("/api/issues", params={"type": "bridge_mismatch"}).json()
        assert all(i["field"] != "year" for i in rows)


def test_bridge_import_campo_vuoto_nel_file_non_e_mismatch(db, monkeypatch):
    """File senza album (campo vuoto): se Cratory ce l'ha, e' un buco da
    riempire (missing_metadata/Step 1), non una discrepanza da segnalare."""
    _configure(db)
    _file(db, 27, path="/m/27.mp3", artist="Rataxes", title="Acid Face",
          genre="Acid Techno", year=2024, label="Bunker", album=None, isrc=None)
    db.commit()
    monkeypatch.setattr(cratory_bridge, "lookup",
                        lambda *a, **k: dict(FOUND, match="path"))
    with TestClient(app) as client:
        r = client.post("/api/issues/bridge-suggest", json={"mode": "import"}).json()
        assert r["mismatches"] == 0
        assert client.get("/api/issues", params={"type": "bridge_mismatch"}).json() == []


def test_bridge_import_non_configurato(db):
    with TestClient(app) as client:
        r = client.post("/api/issues/bridge-suggest", json={"mode": "import"}).json()
        assert r == _empty_for("import")
```

Nota per l'implementatore: `_BRIDGE_FIELDS` resta `("artist", "title", "genre", "year", "label", "album")` — non aggiungere `album_artist`, che non è nel contratto Cratory (non è nel dict `FOUND`/`TrackLookupOut`).

- [ ] **Step 3: Esegui i test e verifica che falliscano**

Run: `cd backend && .venv/bin/python -m pytest tests/test_bridge_suggest_api.py -v`
Expected: FAIL su tutti i nuovi test e su quelli aggiornati (l'endpoint non legge ancora un body, non ha `mode`, i mismatch scattano sempre con ISRC indipendentemente dalla modalità, non c'è `_BRIDGE_FIELDS` genere-gated riusabile per campi generici, `path` non viene passato).

- [ ] **Step 4: Riscrivi la sezione bridge di `issues.py`**

Sostituisci l'intero blocco da `# --- Bridge Cratory ---` (riga 200) fino alla fine del file (riga 331) con:

```python
# --- Bridge Cratory ----------------------------------------------------------
# Precedenza valori (spec ecosistema): fix manuale > tag pulito nel file >
# suggerimento Cratory > AI-da-filename. Il bridge tocca SOLO issue aperte:
# un tag pulito non ha issue (mai toccato), un fix manuale/accettato ha
# status != "open" (mai toccato). Sovrascrive invece un suggerimento AI non
# ancora accettato (Cratory > AI); gli endpoint AI, che saltano le issue già
# suggerite, non sovrascrivono mai il bridge.
#
# Due modalita':
# - fill (default): riempie solo i buchi (issue aperte). Mai discrepanze.
# - import: fill + propone sovrascritture su campi gia' valorizzati, ma SOLO
#   con match certo (path o ISRC) e mai svuotando un campo assente in Cratory.

_BRIDGE_TYPES = ("missing_required_tag", "missing_metadata", "dirty_genre")
_BRIDGE_FIELDS = ("artist", "title", "genre", "year", "label", "album")
_MODES = ("fill", "import")


def _not_configured(mode: str) -> dict:
    return {"configured": False, "mode": mode, "files": 0, "suggested": 0,
            "unresolved": 0, "mismatches": 0}


def _norm(s) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _norm_value(field: str, value) -> str:
    """Normalizzazione per il confronto: year numerico, resto stringa case/spazi."""
    if field == "year":
        return str(value) if value is not None else ""
    return _norm(value)


@router.post("/bridge-suggest", response_model=dict)
def bridge_suggest(body: BridgeSuggestBody | None = None, db: Session = Depends(get_db)):
    mode = body.mode if body is not None else "fill"
    if mode not in _MODES:
        raise HTTPException(status_code=422, detail="mode deve essere 'fill' o 'import'")

    base_url = (planning.get_settings(db).cratory_base_url or "").strip()
    if not base_url:
        return _not_configured(mode)

    rows = db.execute(
        select(Issue, AudioFile)
        .join(AudioFile, Issue.file_id == AudioFile.id)
        .where(Issue.status == "open", Issue.type.in_(_BRIDGE_TYPES),
               Issue.field.in_(_BRIDGE_FIELDS))
    ).all()
    all_present_files = db.scalars(
        select(AudioFile).where(AudioFile.status == "present")
    ).all()

    cache: dict[int, dict | None] = {}

    def _lookup(f: AudioFile) -> dict | None:
        """Una sola lookup HTTP per file (cache). Manda sempre il path assoluto
        insieme a ISRC/artist+title se presenti; None solo se nessuna chiave e'
        disponibile (nessun path, nessun ISRC, niente artist+title)."""
        if f.id not in cache:
            has_isrc = bool((f.isrc or "").strip())
            has_tags = bool((f.artist or "").strip() and (f.title or "").strip())
            if f.path or has_isrc or has_tags:
                cache[f.id] = cratory_bridge.lookup(
                    base_url, path=f.path or None,
                    isrc=f.isrc.strip() if has_isrc else None,
                    artist=f.artist.strip() if has_tags else None,
                    title=f.title.strip() if has_tags else None,
                )
            else:
                cache[f.id] = None
        return cache[f.id]

    suggested = unresolved = mismatches = 0
    files_seen: set[int] = set()
    try:
        # 1) Riempi suggested_fix sulle issue aperte esistenti (mai su tag puliti:
        #    un tag pulito non ha issue). Mai auto-accettare: status resta open.
        #    Qualunque match (anche fuzzy) va bene per colmare un buco.
        for issue, f in rows:
            files_seen.add(f.id)
            res = _lookup(f)
            value = res.get(issue.field) if res and res.get("found") else None
            if isinstance(value, str):
                value = value.strip() or None
            if value is not None:
                issue.suggested_fix_json = {"field": issue.field,
                                            "action": "retag", "to": value}
                issue.updated_at = utcnow()
                suggested += 1
            else:
                unresolved += 1

        # 2) Pulisci le bridge_mismatch orfane (file non piu' presente): il
        #    merge dell'analisi le esenta dalla cancellazione, quindi la
        #    riconciliazione avviene qui, in entrambe le modalita'.
        for issue, f in db.execute(
            select(Issue, AudioFile).join(AudioFile, Issue.file_id == AudioFile.id)
            .where(Issue.type == "bridge_mismatch")
        ).all():
            if f.status != "present":
                db.delete(issue)

        # 3) Check discrepanze: solo in modalita' import, solo match certo
        #    (path o ISRC), mai fuzzy.
        if mode == "import":
            for f in all_present_files:
                res = _lookup(f)
                if res is None or not res.get("found") \
                        or res.get("match") not in ("path", "isrc"):
                    continue  # nessuna informazione certa: non toccare nulla
                expected: dict[str, object] = {}
                for field in ("artist", "title", "year", "label", "album"):
                    c_val = res.get(field)
                    if isinstance(c_val, str):
                        c_val = c_val.strip() or None
                    if c_val is None:
                        continue  # Cratory non ha il campo: mai proporre lo svuotamento
                    own_val = getattr(f, field)
                    if not _norm_value(field, own_val):
                        continue  # campo vuoto nel file: ci pensa missing_metadata, non il mismatch
                    if _norm_value(field, c_val) != _norm_value(field, own_val):
                        expected[field] = c_val
                # Genere: precedenza invertita (spec Lotto C) — il dato Cratory batte
                # il tag pulito, ma SOLO se la sua fonte e' affidabile (manual/provider);
                # ai/file_tag non sono meglio del file.
                c_genre = (res.get("genre") or "").strip()
                if c_genre and res.get("genre_source") in ("manual", "provider") \
                        and _norm(f.genre) and _norm(c_genre) != _norm(f.genre):
                    expected["genre"] = c_genre
                existing = {i.field: i for i in db.scalars(
                    select(Issue).where(Issue.file_id == f.id,
                                        Issue.type == "bridge_mismatch")).all()}
                for field, c_val in expected.items():
                    detail = (f"Cratory ({res.get('match')} match): {field} = '{c_val}', "
                              f"nel file = '{getattr(f, field)}'")
                    row = existing.get(field)
                    if row is None:
                        db.add(Issue(file_id=f.id, type="bridge_mismatch", field=field,
                                     severity="warning", detail=detail,
                                     suggested_fix_json={"field": field,
                                                         "action": "retag", "to": c_val},
                                     status="open"))
                        mismatches += 1
                    else:
                        if row.status == "open":  # le decisioni utente sono intoccabili
                            row.detail = detail
                            row.suggested_fix_json = {"field": field,
                                                      "action": "retag", "to": c_val}
                            row.updated_at = utcnow()
                            mismatches += 1
                for field, row in existing.items():
                    if field not in expected:
                        db.delete(row)  # discrepanza risolta (o non piu' confermata)
    except cratory_bridge.CratoryUnreachable:
        # Degradazione pulita: niente modifiche parziali, stessa UX del
        # non-configurato (come ai-suggest senza ANTHROPIC_API_KEY).
        db.rollback()
        return _not_configured(mode)

    db.commit()
    return {"configured": True, "mode": mode, "files": len(files_seen),
            "suggested": suggested, "unresolved": unresolved, "mismatches": mismatches}
```

Aggiungi l'import di `BridgeSuggestBody` nella riga degli import da `app.schemas` in cima al file (riga 12):

```python
from app.schemas import (
    BridgeSuggestBody, IssueBulkBody, IssueFixBody, IssueRead, IssueStatusBody,
)
```

Nota bene un dettaglio di comportamento cambiato consapevolmente rispetto a oggi: il conteggio `unresolved` in Step 1 ora può includere anche file la cui unica chiave è il path (prima, senza ISRC/tag, la issue restava "unresolved" senza nemmeno una chiamata; ora la chiamata parte comunque via path). Questo è desiderato: più file diventano risolvibili. Verifica che nessun test esistente in `test_bridge_suggest_api.py` assuma il vecchio conteggio per file senza ISRC/tag — il test `test_bridge_unresolved_without_key_or_match` usa file con `artist`/`title` parziali ma niente path esplicito (i fixture di default hanno comunque `path=f"/m/{file_id}.mp3"`, quindi ora la lookup PARTE anche per il file 6). Aggiorna quel test:

```python
def test_bridge_unresolved_without_key_or_match(db, monkeypatch):
    _configure(db)
    # File 6: niente ISRC, artist mancante, ma ha comunque un path -> la lookup
    # parte via path (nessuna chiave e' "niente" quando c'e' un path).
    _file(db, 6, artist=None, title="Solo Titolo", isrc=None)
    db.add(Issue(file_id=6, type="missing_required_tag", field="artist",
                 severity="error", detail="artist mancante",
                 suggested_fix_json=None, status="open"))
    # File 7: chiave fuzzy ma Cratory non trova nulla.
    _file(db, 7, artist="Ignoto", title="Mai Sentito", genre=None, isrc=None)
    db.add(Issue(file_id=7, type="missing_metadata", field="genre",
                 severity="warning", detail="genre mancante",
                 suggested_fix_json=None, status="open"))
    db.commit()
    monkeypatch.setattr(cratory_bridge, "lookup", lambda *a, **k: dict(NOT_FOUND))
    with TestClient(app) as client:
        r = client.post("/api/issues/bridge-suggest").json()
        assert r == {"configured": True, "mode": "fill", "files": 2, "suggested": 0,
                     "unresolved": 2, "mismatches": 0}
```

(la vecchia asserzione `assert calls == ["Ignoto"]` va rimossa: non è più vera che solo un file genera una chiamata, e non è quello che il test vuole dimostrare — il comportamento "unresolved" quando Cratory non trova nulla).

Le altre tre asserzioni per uguaglianza esatta del dict di risposta vanno aggiornate ad aggiungere la chiave `mode`:

In `test_bridge_not_configured` (riga 33-35), sostituisci:

```python
def test_bridge_not_configured(db):
    with TestClient(app) as client:
        assert client.post("/api/issues/bridge-suggest").json() == EMPTY
```

con:

```python
def test_bridge_not_configured(db):
    with TestClient(app) as client:
        assert client.post("/api/issues/bridge-suggest").json() == dict(EMPTY, mode="fill")
```

In `test_bridge_fills_missing_metadata_via_isrc` (riga 57), sostituisci:

```python
        assert r == {"configured": True, "files": 1, "suggested": 3,
                     "unresolved": 0, "mismatches": 0}
```

con:

```python
        assert r == {"configured": True, "mode": "fill", "files": 1, "suggested": 3,
                     "unresolved": 0, "mismatches": 0}
```

In `test_bridge_unreachable_degrades_cleanly` (riga 320), sostituisci:

```python
        assert client.post("/api/issues/bridge-suggest").json() == EMPTY
```

con:

```python
        assert client.post("/api/issues/bridge-suggest").json() == dict(EMPTY, mode="fill")
```

- [ ] **Step 5: Esegui i test e verifica che passino**

Run: `cd backend && .venv/bin/python -m pytest tests/test_bridge_suggest_api.py -v`
Expected: PASS su tutti i test.

- [ ] **Step 6: Esegui l'intera suite backend (nessuna regressione)**

Run: `cd backend && .venv/bin/python -m pytest tests -q`
Expected: PASS, nessun fallimento (in particolare `test_analysis_issues.py` e `test_settings_api.py`, che referenziano il bridge indirettamente).

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas.py backend/app/routers/issues.py backend/tests/test_bridge_suggest_api.py
git commit -m "feat: bridge-suggest a due modalità (fill/import), sovrascritture con match certo"
```

---

### Task 4: Frontend — due pulsanti

**Files:**
- Modify: `frontend/lib/api.ts:198-207`
- Modify: `frontend/app/issues/page.tsx:92-111` (onBridge), `:147` (props), `:195-247` (Marginalia)

**Interfaces:**
- Consumes: `POST /api/issues/bridge-suggest` con body `{mode}` dal Task 3, risposta con campo `mode`.
- Produces: nessuno (foglia della catena).

- [ ] **Step 1: Aggiorna `lib/api.ts`**

Sostituisci (righe 198-207):

```typescript
export interface BridgeSuggestResult {
  configured: boolean;
  mode: "fill" | "import";
  files: number;
  suggested: number;
  unresolved: number;
  mismatches: number;
}
export function bridgeSuggest(mode: "fill" | "import" = "fill") {
  return apiSend<BridgeSuggestResult>("POST", "/api/issues/bridge-suggest", { mode });
}
```

- [ ] **Step 2: Aggiorna `onBridge` in `issues/page.tsx`**

Sostituisci (righe 92-111):

```typescript
  const onBridge = async (mode: "fill" | "import") => {
    setActionError(null);
    setAiNote(null);
    setBridgeBusy(true);
    try {
      const r = await bridgeSuggest(mode);
      if (!r.configured) {
        setActionError("Configura l'URL di Cratory in Settings (e verifica che Cratory sia in esecuzione).");
      } else {
        load();
        const azione = mode === "fill" ? "riempiti" : "importati";
        setAiNote(
          `${r.suggested} suggerimenti ${azione} da Cratory${r.mismatches > 0 ? `, ${r.mismatches} sovrascritture proposte` : ""}${r.unresolved > 0 ? `, ${r.unresolved} non trovati` : ""} — rivedi e accetta col ✓.`,
        );
      }
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Errore");
    } finally {
      setBridgeBusy(false);
    }
  };
```

- [ ] **Step 3: Aggiorna il passaggio delle props a `Marginalia` (riga 147)**

Sostituisci:

```typescript
          onBridge={onBridge} bridgeBusy={bridgeBusy}
```

con:

```typescript
          onBridgeFill={() => onBridge("fill")} onBridgeImport={() => onBridge("import")}
          bridgeBusy={bridgeBusy}
```

- [ ] **Step 4: Aggiorna la firma e il markup di `Marginalia` (righe 195-247)**

Sostituisci la firma della funzione (righe 195-208):

```typescript
function Marginalia({ total, bySev, byType, accepted, onAcceptFixable, onDismissInfo, onAiSuggest, aiBusy, onAiGenres, genreBusy, onBridgeFill, onBridgeImport, bridgeBusy }: {
  total: number;
  bySev: Record<string, number>;
  byType: Record<string, number>;
  accepted: number;
  onAcceptFixable: () => void;
  onDismissInfo: () => void;
  onAiSuggest: () => void;
  aiBusy: boolean;
  onAiGenres: () => void;
  genreBusy: boolean;
  onBridgeFill: () => void;
  onBridgeImport: () => void;
  bridgeBusy: boolean;
}) {
```

Sostituisci il pulsante singolo del bridge (righe 239-241):

```typescript
        <Button variant="primary" size="sm" onClick={onBridge} disabled={bridgeBusy}>
          {bridgeBusy ? "Cratory in corso…" : "⇄ Suggerisci da Cratory"}
        </Button>
```

con due pulsanti:

```typescript
        <Button variant="primary" size="sm" onClick={onBridgeFill} disabled={bridgeBusy}>
          {bridgeBusy ? "Cratory in corso…" : "⇄ Riempi da Cratory"}
        </Button>
        <Button variant="primary" size="sm" onClick={onBridgeImport} disabled={bridgeBusy}>
          {bridgeBusy ? "Cratory in corso…" : "⇄ Importa da Cratory"}
        </Button>
```

- [ ] **Step 5: Verifica che il progetto compili**

Run: `cd frontend && npm run build`
Expected: build completata senza errori TypeScript (in particolare nessun riferimento residuo a `onBridge` singolo o a `BridgeSuggestResult` senza `mode`).

- [ ] **Step 6: Verifica manuale nel browser**

Avvia il backend (`cd backend && .venv/bin/python -m uvicorn app.main:app --reload`) e il frontend (`cd frontend && npm run dev -- -p 3001`), apri la pagina Issues, verifica che compaiano i due pulsanti "⇄ Riempi da Cratory" e "⇄ Importa da Cratory" nella colonna marginalia, e che cliccarli (con `cratory_base_url` configurato in Settings e Cratory in esecuzione) produca un messaggio coerente con la modalità.

- [ ] **Step 7: Commit**

```bash
git add frontend/lib/api.ts frontend/app/issues/page.tsx
git commit -m "feat: due pulsanti per il bridge Cratory (Riempi/Importa)"
```

---

### Task 5: Documentazione contratto in DjOrganizer

**Files:**
- Modify: `README.md:17-25`

**Interfaces:** nessuna (solo prosa).

- [ ] **Step 1: Aggiorna il paragrafo del bridge**

Nel `README.md`, individua il paragrafo che descrive il bridge (attorno alle righe 17-18, che menziona "Il bridge read-only verso Cratory suggerisce genere/etichetta/anno durante la pulizia dei tag") e integra la menzione delle due modalità e del match per path. Aggiungi, subito dopo quella frase:

```text
Due modalità: **Riempi** colma solo i campi mancanti (non tocca mai un valore
già presente); **Importa** propone sovrascritture anche su campi già
valorizzati, ma solo quando il match con Cratory è certo (via path assoluto del
file collegato, oppure ISRC) — mai con match approssimativo, e mai svuotando un
campo che Cratory non ha.
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: due modalità del bridge Cratory nel README"
```

---

## Task 6: Integrazione finale

**Files:** nessuno (solo comandi git/gh in entrambi i repo).

- [ ] **Step 1: Suite completa Cratory**

Run: `cd /Users/lucadenegri/Develop/DJProject01/backend && .venv/bin/python -m pytest tests -q`
Expected: PASS.

- [ ] **Step 2: Suite completa DjOrganizer + build frontend**

Run: `cd /Users/lucadenegri/Develop/DjOrganizer01/backend && .venv/bin/python -m pytest tests -q && cd ../frontend && npm run build`
Expected: PASS, build senza errori.

- [ ] **Step 3: Push di entrambi i repo su main**

Segui la preferenza standard dell'utente (integrazione = merge in main + push), su entrambi i repo:

```bash
cd /Users/lucadenegri/Develop/DJProject01 && git push origin main
cd /Users/lucadenegri/Develop/DjOrganizer01 && git push origin main
```
