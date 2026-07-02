# Lotto C (DjOrganizer) — Precedenza Genere dal Bridge — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Per il campo GENERE il dato di Cratory batte il tag del file (`manuale > bridge > AI locale > tag file`); il bridge propone anche l'`album`; l'AI locale resta solo fallback offline.

**Architecture:** Il check discrepanze di `POST /api/issues/bridge-suggest` (oggi solo artist/title su match ISRC) si estende al genere: se Cratory risponde con un genere di fonte affidabile (`genre_source` in `manual`/`provider`) diverso dal tag del file, nasce una issue `bridge_mismatch` con fix suggerito — anche se il tag del file è "pulito". `album` entra nei campi riempibili dal bridge. Nessun automatismo: tutto resta proposto-e-approvato nel ciclo issue → piano → apply.

**Tech Stack:** Python/FastAPI + SQLAlchemy + pytest (176 test). Spec: `~/Develop/docs/superpowers/specs/2026-07-02-metadati-stati-automazioni-design.md` (Lotto C). **Prerequisito: piano C-Cratory mergiato** (il lookup deve esporre `genre_source` e `album`).

## Global Constraints

- Repo: `/Users/lucadenegri/Develop/DjOrganizer01`, branch dedicato. Commenti in italiano.
- Test: `cd /Users/lucadenegri/Develop/DjOrganizer01/backend && <python del venv> -m pytest tests/ -q` (individuare il venv come in DJProject01: `backend/.venv/bin/python`; verificare con `ls backend/.venv/bin/`).
- Pattern test: monkeypatch di `cratory_bridge.lookup` come in `tests/test_bridge_suggest_api.py` (fixture `_configure`, `_file`, dict `FOUND`).
- Le decisioni utente sono intoccabili: issue con `status != "open"` non si toccano mai (invariante esistente, righe 200-207 di `routers/issues.py`).
- Limite deciso a spec: il mismatch genere scatta SOLO su match ISRC (mai fuzzy — il rischio di traccia sbagliata è troppo alto). Per i file senza ISRC il bridge continua a riempire solo le issue aperte (`missing_metadata`/`dirty_genre`), come oggi.

---

### Task 1: Contratto bridge esteso (`genre_source`, `album`)

**Files:**
- Modify: `backend/app/services/cratory_bridge.py` (docstring del contratto, righe 14-24)
- Test: `backend/tests/test_bridge_suggest_api.py` (dict `FOUND` esteso)

**Interfaces:**
- Consumes: risposta Cratory con `genre_source: str|None` e `album: str|None` (piano C-Cratory, Task 5).
- Produces: nessun cambio di codice runtime (il client ritorna il JSON as-is): si aggiorna il contratto documentato e il fixture dei test. I Task 2-3 leggono `res.get("genre_source")` / `res.get("album")`.

- [ ] **Step 1:** In `cratory_bridge.py` aggiorna la docstring del contratto:

```python
    Ritorna il body JSON del contratto:
    {"found": bool, "match": "isrc"|"fuzzy"|None, "track_id": int|None,
     "artist": ..., "title": ..., "genre": ..., "genre_secondary": ...,
     "genre_source": "manual"|"provider"|"ai"|"file_tag"|None,
     "album": ..., "label": ..., "year": ..., "confidence": 100|70|0}
```

- [ ] **Step 2:** In `tests/test_bridge_suggest_api.py` estendi il dict `FOUND` (riga ~8):

```python
FOUND = {"found": True, "match": "isrc", "track_id": 7, "artist": "Rataxes",
         "title": "Acid Face", "genre": "Acid Techno", "genre_secondary": None,
         "genre_source": "provider", "album": "Bunker EP",
         "label": "Bunker", "year": 2024, "confidence": 100}
```

- [ ] **Step 3: Verifica** — `pytest tests/test_bridge_suggest_api.py tests/test_cratory_bridge.py -q` → tutti PASS (nessun comportamento cambiato: chiavi extra ignorate).
- [ ] **Step 4: Commit** — `git commit -m "docs: contratto bridge esteso con genre_source e album"`

---

### Task 2: `album` nei campi riempibili dal bridge

**Files:**
- Modify: `backend/app/routers/issues.py` (`_BRIDGE_FIELDS`, riga ~210), `backend/app/services/inspector.py` (campi `missing_metadata`, riga ~85)
- Test: `backend/tests/test_bridge_suggest_api.py` (aggiunta)

**Interfaces:**
- Consumes: `album` nella risposta bridge (Task 1).
- Produces: issue `missing_metadata` anche per `album` (severity come genre/year/label); il bridge le riempie.

- [ ] **Step 1: Test che fallisce** — in `tests/test_bridge_suggest_api.py`, sul pattern di `test_bridge_fills_missing_metadata_via_isrc` (righe 36-66):

```python
def test_bridge_riempie_album_mancante(db, monkeypatch):
    _configure(db)
    _file(db, 1, artist="Rataxes", title="Acid Face", genre="Acid Techno",
          year=2024, label="Bunker", isrc="DEAB12300123")
    db.add(Issue(file_id=1, type="missing_metadata", field="album",
                 severity="info", detail="album mancante",
                 suggested_fix_json=None, status="open"))
    db.commit()
    monkeypatch.setattr(cratory_bridge, "lookup", lambda *a, **k: dict(FOUND))
    with TestClient(app) as client:
        r = client.post("/api/issues/bridge-suggest").json()
        assert r["suggested"] == 1
        rows = client.get("/api/issues", params={"type": "missing_metadata"}).json()
        assert rows[0]["suggested_fix_json"] == {
            "field": "album", "action": "retag", "to": "Bunker EP"}
```

(verificare la firma reale di `_file` nel file di test e completare i parametri obbligatori; se `_file` non accetta `album`, il default è già None.)

- [ ] **Step 2: Verifica FAIL** — l'issue album non viene riempita (`album` non è in `_BRIDGE_FIELDS`).

- [ ] **Step 3: Implementa**

`routers/issues.py`: `_BRIDGE_FIELDS = ("artist", "title", "genre", "year", "label", "album")`.

`services/inspector.py`, riga ~85: aggiungi `album` alla lista dei campi che generano `missing_metadata` (accanto a genre/year/label, stessa severity usata lì; se la severity è per-campo, usa `"info"` per album — è il campo meno critico).

- [ ] **Step 4: Verifica PASS + suite** — `pytest tests/ -q`. Se test dell'inspector contano le issue generate, aggiorna gli attesi (+1 per file senza album).
- [ ] **Step 5: Commit** — `git commit -m "feat: album riempibile dal bridge (issue missing_metadata)"`

---

### Task 3: Mismatch genere — il bridge vince sul tag pulito

**Files:**
- Modify: `backend/app/routers/issues.py` (blocco "3) Check discrepanze", righe ~279-310)
- Test: `backend/tests/test_bridge_suggest_api.py` (aggiunte)

**Interfaces:**
- Consumes: `genre_source` dalla risposta bridge (Task 1).
- Produces: su match ISRC, se Cratory ha genere con `genre_source` in (`manual`, `provider`) e il tag del file differisce (confronto normalizzato), nasce/si aggiorna una issue `bridge_mismatch` con field `genre` e fix suggerito. Fonti deboli (`ai`, `file_tag`, None) NON generano mismatch (il tag locale non è peggio del dato remoto).

- [ ] **Step 1: Test che falliscono** — in `tests/test_bridge_suggest_api.py`:

```python
def test_mismatch_genere_da_fonte_affidabile(db, monkeypatch):
    """Tag genre pulito ma diverso da Cratory (provider): nasce la issue."""
    _configure(db)
    _file(db, 1, artist="Rataxes", title="Acid Face", genre="Electro",
          year=2024, label="Bunker", isrc="DEAB12300123")
    db.commit()
    monkeypatch.setattr(cratory_bridge, "lookup", lambda *a, **k: dict(FOUND))
    with TestClient(app) as client:
        r = client.post("/api/issues/bridge-suggest").json()
        assert r["mismatches"] == 1
        rows = client.get("/api/issues", params={"type": "bridge_mismatch"}).json()
        assert rows[0]["field"] == "genre"
        assert rows[0]["suggested_fix_json"]["to"] == "Acid Techno"
        assert rows[0]["status"] == "open"  # mai auto-accettata


def test_niente_mismatch_genere_da_fonte_debole(db, monkeypatch):
    """genre_source ai/file_tag: il dato remoto non e' meglio del tag locale."""
    _configure(db)
    _file(db, 1, artist="Rataxes", title="Acid Face", genre="Electro",
          year=2024, label="Bunker", isrc="DEAB12300123")
    db.commit()
    weak = dict(FOUND, genre_source="file_tag")
    monkeypatch.setattr(cratory_bridge, "lookup", lambda *a, **k: weak)
    with TestClient(app) as client:
        r = client.post("/api/issues/bridge-suggest").json()
        assert r["mismatches"] == 0


def test_niente_mismatch_genere_se_uguale_normalizzato(db, monkeypatch):
    _configure(db)
    _file(db, 1, artist="Rataxes", title="Acid Face", genre="acid  techno",
          year=2024, label="Bunker", isrc="DEAB12300123")
    db.commit()
    monkeypatch.setattr(cratory_bridge, "lookup", lambda *a, **k: dict(FOUND))
    with TestClient(app) as client:
        assert client.post("/api/issues/bridge-suggest").json()["mismatches"] == 0
```

- [ ] **Step 2: Verifica FAIL** — `pytest tests/test_bridge_suggest_api.py -v` → `mismatches == 0` dove atteso 1 (oggi il check copre solo artist/title).

- [ ] **Step 3: Implementa** — in `routers/issues.py`, blocco "3) Check discrepanze" (righe ~279-310). Il loop attuale su `("artist", "title")` diventa:

```python
        # 3) Check discrepanze: solo match ISRC (confidence 100), mai fuzzy.
        #    artist/title: come sempre. genre: precedenza invertita (spec Lotto C) —
        #    il dato Cratory batte il tag pulito, ma SOLO se la sua fonte e'
        #    affidabile (manual/provider); ai/file_tag non sono meglio del file.
        for f in isrc_files:
            res = _lookup(f)
            if res is None or not res.get("found") or res.get("match") != "isrc":
                continue  # nessuna informazione certa: non toccare nulla
            expected: dict[str, str] = {}
            for field in ("artist", "title"):
                c_val = (res.get(field) or "").strip()
                if c_val and _norm(getattr(f, field)) \
                        and _norm(c_val) != _norm(getattr(f, field)):
                    expected[field] = c_val
            c_genre = (res.get("genre") or "").strip()
            if c_genre and res.get("genre_source") in ("manual", "provider") \
                    and _norm(c_genre) != _norm(f.genre):
                expected["genre"] = c_genre
```

Il resto del blocco (creazione/aggiornamento/cleanup delle `bridge_mismatch` esistenti, righe ~289-310) resta INVARIATO: itera già su `expected.items()` ed è già generico sul campo. Aggiorna solo il messaggio `detail` se cita esplicitamente artist/title (verificare: il formato attuale è generico, `f"Cratory (ISRC ...): {field} = ..."`).

NOTA: il caso `f.genre` vuoto/None è coperto dalle issue `missing_metadata` (parte 1 del bridge): il mismatch scatta anche a genre assente per via di `_norm(None) == ""` ≠ `_norm(c_genre)` — verifica che non nascano DOPPIE proposte (missing_metadata + bridge_mismatch) per lo stesso file+campo: se succede, aggiungi la guardia `and _norm(f.genre)` alla condizione (mismatch solo su genere PRESENTE; quello assente resta a missing_metadata).

- [ ] **Step 4: Verifica PASS + suite completa** — `pytest tests/ -q` (i 13 test bridge esistenti devono restare verdi: artist/title immutati, il genere entra solo con `genre_source` affidabile — il vecchio FOUND senza `genre_source` ora ce l'ha nel fixture, quindi controlla i test esistenti che assumevano `mismatches == 0` con genre diverso).
- [ ] **Step 5: Commit** — `git commit -m "feat: mismatch genere dal bridge (Cratory batte il tag pulito)"`

---

### Task 4: Verifica end-to-end manuale (checklist, nessun codice)

- [ ] Avvia Cratory (`:8000`) e DjOrganizer; in DjOrganizer Impostazioni verifica `cratory_base_url`.
- [ ] Scan di una cartella con un file dal genere sbagliato ma ISRC presente e traccia nota a Cratory → `POST /api/issues/bridge-suggest` (bottone in UI) → compare la issue `bridge_mismatch` sul genere con il valore Cratory.
- [ ] Accetta → piano → l'operazione è RETAG (+ MOVE se il template cartelle usa `{genre}`) → apply → il tag TCON è riscritto e il file spostato nella cartella giusta.
- [ ] In Cratory lancia una scansione → la traccia resta agganciata (riaggancio per hash) e `has_local_file=True`.
