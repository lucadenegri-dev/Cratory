# Cratory Bridge (disk-first 3b) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Aggiungere il "bridge Cratory": un client HTTP di sola lettura verso l'app sorella Cratory (`GET {cratory_base_url}/api/tracks/lookup`) che riempie `suggested_fix_json` sulle issue aperte (genere/label/anno/artista/titolo), segnala le discrepanze ISRC come nuova issue `bridge_mismatch`, ed espone `Settings.cratory_base_url` (colonna già esistente, dormiente) in API e frontend. In più un fix piccolo: lo Scanner salta le directory `.quarantine/` (e le nascoste in generale).

**Architecture:** Nuovo modulo `backend/app/services/cratory_bridge.py` (client httpx, timeout 3s, mockabile come `ai_tags`). Nuovo endpoint `POST /api/issues/bridge-suggest` nel router issues che rispecchia il pattern di `ai-suggest` (`{"configured": false}` quando non configurato O irraggiungibile, suggerimenti mai auto-accettati). Lettura ISRC end-to-end: `tagio.read_tags` (frame ID3 `TSRC`, vorbis `isrc`) → colonna `AudioFile.isrc` (ALTER in `ensure_schema`, niente Alembic) → Scanner. `analysis._merge_issues` esenta il tipo `bridge_mismatch` dalla cancellazione (non è calcolato dall'Inspector; lo riconcilia l'endpoint stesso). Frontend: campo Cratory in Settings, bottone "Suggerisci da Cratory" nella marginalia di Issues.

**Precedenza valori (spec ecosistema, non negoziabile):** fix manuale > tag pulito nel file > suggerimento Cratory > AI-da-filename. Implementata così: il bridge tocca SOLO issue con `status == "open"` (tag pulito ⇒ nessuna issue ⇒ mai toccato; fix manuale/accettato ⇒ `status != "open"` ⇒ mai toccato); sovrascrive un suggerimento AI non ancora accettato (Cratory > AI); gli endpoint AI esistenti saltano già le issue con `suggested_fix_json` valorizzato, quindi l'AI non sovrascrive mai il bridge.

**Tech Stack:** FastAPI, SQLAlchemy 2.0, Pydantic v2, `httpx` (già in requirements.txt: lo usa il TestClient), mutagen, pytest · Next 16 / React 19 / TypeScript.

## Global Constraints

- **Branch:** `feat/cratory-bridge` creato da `main` (Task 1, Step 1). Un commit per task, messaggi in italiano stile repo (`feat(api): …`, `feat(scan): …`, `feat(fe): …`).
- **Test backend:** `cd ~/Develop/DjOrganizer01/backend && .venv/bin/python -m pytest -q` — 148 test esistenti, tutti verdi, **pristine** (`pytest.ini` ha `filterwarnings = error`). Cratory NON deve mai essere chiamato nei test: monkeypatch su `cratory_bridge.lookup` (stesso pattern di `ai_tags.suggest`).
- **Frontend:** `cd ~/Develop/DjOrganizer01/frontend && npm run lint && npm run build` — entrambi verdi. Copy UI in italiano minuscolo (stile esistente: "salva template", "vuoto = niente sottocartelle").
- **Convenzioni osservate da rispettare:** router "sottili" con `response_model=dict` per gli endpoint suggest; il filtro `suggested_fix_json is None` si fa **in Python**, non in SQL (la colonna JSON serializza None come `'null'` — commento in `routers/issues.py`); i suggerimenti NON cambiano mai lo status (`open` resta `open`, accetta l'utente col ✓); formato fix: `{"field": <campo>, "action": "retag", "to": <valore>}` (consumato da `planner.effective_tags` e `_RETAGGABLE`); severità valide: `error` / `warning` / `info`; commenti nel codice in italiano.
- **Niente Alembic:** app locale — le colonne nuove su DB esistenti si aggiungono in `app/db.py::ensure_schema` con `ALTER TABLE` guardato (pattern già usato per `scan_root.target_root`).
- **Contratto Cratory (lato Cratory in sviluppo parallelo, trattarlo come dato):** `GET {base_url}/api/tracks/lookup?isrc=…` oppure `?artist=…&title=…` (serve isrc OPPURE artist+title, altrimenti 422). Con input valido sempre 200 con body `{"found": bool, "match": "isrc"|"fuzzy"|null, "track_id": int|null, "artist": str|null, "title": str|null, "genre": str|null, "genre_secondary": str|null, "label": str|null, "year": int|null, "confidence": 100|70|0}`.

---

### Task 1: Branch + Scanner — salta `.quarantine/` e le directory nascoste

**Files:**
- Modify: `backend/app/services/scanner.py` (`_iter_audio_files`)
- Test: `backend/tests/test_scanner.py`

**Interfaces:**
- Consumes: `os.walk(root_path)` — potatura in-place della lista `dirs`.
- Produces: `_iter_audio_files(root_path: str) -> Iterator[tuple[str, str]]` invariato nella firma; non visita più directory il cui nome inizia con `.` (quindi né `.quarantine` né altre nascoste).

- [ ] **Step 1: Crea il branch**

```bash
cd ~/Develop/DjOrganizer01
git checkout main
git pull
git checkout -b feat/cratory-bridge
```

- [ ] **Step 2: Test che fallisce**

In `backend/tests/test_scanner.py`, aggiungi in fondo:

```python
def test_scan_skips_quarantine_and_hidden_dirs(db, copy_fixture, tmp_path):
    """La .quarantine (creata dall'Apply per i DELETE) e le dir nascoste
    non devono rientrare nello scan: niente falsi 'nuovi file'."""
    root_dir = tmp_path / "lib"
    copy_fixture("mp3", root_dir / "a.mp3")
    copy_fixture("mp3", root_dir / ".quarantine" / "b.mp3")
    copy_fixture("mp3", root_dir / ".hidden" / "sub" / "c.mp3")
    root = ScanRoot(path=str(root_dir))
    db.add(root)
    db.commit()
    summary = scan(db, [root])
    assert summary.found == 1
    rows = db.scalars(select(AudioFile)).all()
    assert len(rows) == 1 and rows[0].path.endswith("a.mp3")
```

- [ ] **Step 3: Lancia, verifica FAIL**

Run: `cd ~/Develop/DjOrganizer01/backend && .venv/bin/python -m pytest tests/test_scanner.py::test_scan_skips_quarantine_and_hidden_dirs -q`
Expected: FAIL — `summary.found == 3` (oggi il walk entra ovunque).

- [ ] **Step 4: Implementa**

In `backend/app/services/scanner.py`, sostituisci `_iter_audio_files`:

```python
def _iter_audio_files(root_path: str) -> Iterator[tuple[str, str]]:
    for dirpath, dirs, names in os.walk(root_path):
        # Pota le directory nascoste (es. .quarantine dell'Apply): modificare
        # `dirs` in-place impedisce a os.walk di scenderci.
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for name in names:
            ext = os.path.splitext(name)[1].lower()
            if ext in settings.audio_exts:
                yield os.path.join(dirpath, name), ext
```

(Nota: il parametro prima si chiamava `_dirs`; ora serve mutarlo, quindi si rinomina `dirs`.)

- [ ] **Step 5: Lancia, verifica PASS**

Run: `cd ~/Develop/DjOrganizer01/backend && .venv/bin/python -m pytest tests/test_scanner.py -q`
Expected: PASS (tutti i test dello scanner, inclusi i preesistenti).

- [ ] **Step 6: Commit**

```bash
cd ~/Develop/DjOrganizer01
git add backend/app/services/scanner.py backend/tests/test_scanner.py
git commit -m "fix(scan): lo Scanner salta .quarantine e le directory nascoste"
```

---

### Task 2: ISRC end-to-end — tagio → modello → ensure_schema → Scanner

**Files:**
- Modify: `backend/app/integrations/tagio.py` (`TagData`, `_ID3_READ`, `read_tags`)
- Modify: `backend/app/models.py` (`AudioFile.isrc`)
- Modify: `backend/app/db.py` (`ensure_schema`)
- Modify: `backend/app/services/scanner.py` (`_TAG_FIELDS`, `_scan_file_fields`)
- Modify: `backend/tests/conftest.py` (`make_audio_file` default `isrc=None`)
- Test: `backend/tests/test_tagio.py`, `backend/tests/test_scanner.py`, `backend/tests/test_schema_chunk3.py`

**Interfaces:**
- Produces: `tagio.TagData.isrc: str | None` (letto da easy key `"isrc"` — EasyID3 la mappa su TSRC, vorbis/FLAC è la chiave nativa; per WAV/AIFF via `_ID3_READ["isrc"] = "TSRC"`; su m4a EasyMP4 non la mappa → resta `None`, best-effort accettato). `AudioFile.isrc: Mapped[str | None]`. Nessuna scrittura ISRC: il bridge è read-only.

- [ ] **Step 1: Test tagio che falliscono**

In `backend/tests/test_tagio.py`, aggiungi in cima agli import:

```python
from mutagen import File as MutagenFile
```

e in fondo al file:

```python
def test_read_isrc_flac(copy_fixture, tmp_path):
    f = copy_fixture("flac", tmp_path / "a.flac")
    audio = FLAC(f)
    audio["isrc"] = "DEAB12300123"
    audio.save()
    assert tagio.read_tags(f).isrc == "DEAB12300123"


def test_read_isrc_mp3(copy_fixture, tmp_path):
    f = copy_fixture("mp3", tmp_path / "a.mp3")
    audio = MutagenFile(f, easy=True)
    if audio.tags is None:
        audio.add_tags()
    audio["isrc"] = "DEAB12300123"  # EasyID3: 'isrc' -> frame TSRC
    audio.save()
    assert tagio.read_tags(f).isrc == "DEAB12300123"


def test_missing_isrc_is_none(copy_fixture, tmp_path):
    f = copy_fixture("flac", tmp_path / "a.flac")
    assert tagio.read_tags(f).isrc is None
```

- [ ] **Step 2: Lancia, verifica FAIL**

Run: `cd ~/Develop/DjOrganizer01/backend && .venv/bin/python -m pytest tests/test_tagio.py -q`
Expected: FAIL — `AttributeError: 'TagData' object has no attribute 'isrc'`.

- [ ] **Step 3: Implementa in `backend/app/integrations/tagio.py`**

Nella dataclass `TagData`, dopo `comment: str | None` aggiungi:

```python
    isrc: str | None
```

In `_ID3_READ` (lettura WAV/AIFF), aggiungi la voce:

```python
    "isrc": "TSRC",
```

In `read_tags`, nel costruttore `TagData(...)`, dopo `comment=_first(tags, "comment"),` aggiungi:

```python
        isrc=_first(tags, "isrc"),
```

- [ ] **Step 4: Lancia, verifica PASS**

Run: `cd ~/Develop/DjOrganizer01/backend && .venv/bin/python -m pytest tests/test_tagio.py -q`
Expected: PASS.

- [ ] **Step 5: Test modello+schema+scanner che falliscono**

In `backend/tests/test_schema_chunk3.py`, aggiungi in fondo:

```python
def test_ensure_schema_adds_isrc_to_old_db(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path}/old.db")
    with eng.begin() as conn:
        conn.execute(text(
            "CREATE TABLE audio_file (id INTEGER PRIMARY KEY, root_id INTEGER, "
            "path VARCHAR, ext VARCHAR)"
        ))
    ensure_schema(eng)
    assert "isrc" in {c["name"] for c in inspect(eng).get_columns("audio_file")}
```

In `backend/tests/test_scanner.py`, aggiungi in fondo:

```python
def test_scan_reads_isrc(db, copy_fixture, tmp_path):
    from mutagen.flac import FLAC

    root_dir = tmp_path / "lib"
    path = copy_fixture("flac", root_dir / "a.flac")
    audio = FLAC(path)
    audio["isrc"] = "DEAB12300123"
    audio.save()
    root = ScanRoot(path=str(root_dir))
    db.add(root)
    db.commit()
    scan(db, [root])
    row = db.scalar(select(AudioFile))
    assert row.isrc == "DEAB12300123"
```

- [ ] **Step 6: Lancia, verifica FAIL**

Run: `cd ~/Develop/DjOrganizer01/backend && .venv/bin/python -m pytest tests/test_schema_chunk3.py tests/test_scanner.py -q`
Expected: FAIL — `audio_file` non ha la colonna `isrc` / `AudioFile` non ha l'attributo.

- [ ] **Step 7: Implementa modello, schema, scanner, conftest**

In `backend/app/models.py`, dentro `AudioFile`, dopo `comment: Mapped[str | None] = mapped_column(Text)` aggiungi:

```python
    isrc: Mapped[str | None] = mapped_column(String)
```

In `backend/app/db.py`, in `ensure_schema`, dopo il blocco `scan_root`/`target_root` aggiungi:

```python
    if "audio_file" in inspector.get_table_names():
        cols = {c["name"] for c in inspector.get_columns("audio_file")}
        if "isrc" not in cols:
            with eng.begin() as conn:
                conn.execute(text("ALTER TABLE audio_file ADD COLUMN isrc VARCHAR"))
```

In `backend/app/services/scanner.py`, aggiorna `_TAG_FIELDS`:

```python
_TAG_FIELDS = (
    "bitrate", "sample_rate", "channels", "duration_s", "artist", "title", "album",
    "album_artist", "genre", "year", "label", "track_no", "comment", "isrc", "has_cover",
)
```

e in `_scan_file_fields`, nel `fields.update(...)`, cambia la riga finale:

```python
        label=tags.label, track_no=tags.track_no, comment=tags.comment,
        isrc=tags.isrc, has_cover=tags.has_cover,
```

In `backend/tests/conftest.py`, in `make_audio_file`, aggiorna la riga dei default tag:

```python
        artist=None, title=None, album=None, album_artist=None, genre=None,
        year=None, label=None, track_no=None, comment=None, isrc=None, has_cover=False,
```

- [ ] **Step 8: Lancia il modulo + suite intera**

Run: `cd ~/Develop/DjOrganizer01/backend && .venv/bin/python -m pytest tests/test_schema_chunk3.py tests/test_scanner.py tests/test_tagio.py -q`
Expected: PASS.
Run: `cd ~/Develop/DjOrganizer01/backend && .venv/bin/python -m pytest -q`
Expected: tutti verdi (l'aggiunta è additiva: nessun test esistente tocca `isrc`).

- [ ] **Step 9: Commit**

```bash
cd ~/Develop/DjOrganizer01
git add backend/app/integrations/tagio.py backend/app/models.py backend/app/db.py backend/app/services/scanner.py backend/tests/conftest.py backend/tests/test_tagio.py backend/tests/test_scanner.py backend/tests/test_schema_chunk3.py
git commit -m "feat(scan): lettura ISRC (TSRC/vorbis) end-to-end fino ad AudioFile.isrc"
```

---

### Task 3: Client HTTP `cratory_bridge`

**Files:**
- Create: `backend/app/services/cratory_bridge.py`
- Test: `backend/tests/test_cratory_bridge.py` (nuovo)

**Interfaces:**
- Produces: `cratory_bridge.lookup(base_url: str, isrc: str | None = None, artist: str | None = None, title: str | None = None) -> dict` — ritorna il body JSON del contratto; solleva `cratory_bridge.CratoryUnreachable` su timeout/errore di rete/status non-2xx. Timeout fisso `_TIMEOUT_S = 3.0`.
- Consumes: `httpx.get` (httpx è già in `requirements.txt`).

- [ ] **Step 1: Test che falliscono**

Crea `backend/tests/test_cratory_bridge.py`:

```python
import httpx
import pytest

from app.services import cratory_bridge

BODY = {"found": True, "match": "isrc", "track_id": 7, "artist": "Rataxes",
        "title": "Acid Face", "genre": "Acid Techno", "genre_secondary": None,
        "label": "Bunker", "year": 2024, "confidence": 100}


def _resp(json_body, url="http://localhost:8000/api/tracks/lookup"):
    return httpx.Response(200, json=json_body, request=httpx.Request("GET", url))


def test_lookup_by_isrc(monkeypatch):
    captured = {}

    def fake_get(url, params=None, timeout=None):
        captured.update(url=url, params=params, timeout=timeout)
        return _resp(BODY)

    monkeypatch.setattr(cratory_bridge.httpx, "get", fake_get)
    body = cratory_bridge.lookup("http://localhost:8000/", isrc="DEAB12300123")
    assert body["found"] is True and body["genre"] == "Acid Techno"
    assert captured["url"] == "http://localhost:8000/api/tracks/lookup"  # niente //
    assert captured["params"] == {"isrc": "DEAB12300123"}
    assert captured["timeout"] == 3.0


def test_lookup_by_artist_title(monkeypatch):
    captured = {}

    def fake_get(url, params=None, timeout=None):
        captured.update(url=url, params=params, timeout=timeout)
        return _resp(dict(BODY, match="fuzzy", confidence=70))

    monkeypatch.setattr(cratory_bridge.httpx, "get", fake_get)
    body = cratory_bridge.lookup("http://localhost:8000",
                                 artist="Rataxes", title="Acid Face")
    assert body["match"] == "fuzzy"
    assert captured["params"] == {"artist": "Rataxes", "title": "Acid Face"}


def test_lookup_unreachable_raises(monkeypatch):
    def fake_get(url, params=None, timeout=None):
        raise httpx.ConnectError("connessione rifiutata")

    monkeypatch.setattr(cratory_bridge.httpx, "get", fake_get)
    with pytest.raises(cratory_bridge.CratoryUnreachable):
        cratory_bridge.lookup("http://localhost:8000", isrc="X")


def test_lookup_http_error_raises(monkeypatch):
    def fake_get(url, params=None, timeout=None):
        return httpx.Response(500, json={"detail": "boom"},
                              request=httpx.Request("GET", url))

    monkeypatch.setattr(cratory_bridge.httpx, "get", fake_get)
    with pytest.raises(cratory_bridge.CratoryUnreachable):
        cratory_bridge.lookup("http://localhost:8000", isrc="X")
```

- [ ] **Step 2: Lancia, verifica FAIL**

Run: `cd ~/Develop/DjOrganizer01/backend && .venv/bin/python -m pytest tests/test_cratory_bridge.py -q`
Expected: FAIL — `ImportError: cannot import name 'cratory_bridge'` (modulo inesistente).

- [ ] **Step 3: Implementa**

Crea `backend/app/services/cratory_bridge.py`:

```python
"""Client HTTP read-only verso Cratory (app sorella, FastAPI su localhost:8000).
Solo GET /api/tracks/lookup: il bridge non scrive mai su Cratory. Mockabile nei
test (monkeypatch su cratory_bridge.lookup, come ai_tags.suggest)."""

import httpx

_TIMEOUT_S = 3.0


class CratoryUnreachable(Exception):
    """Cratory non raggiungibile (timeout/rete/status non-2xx): degradare, non rompere."""


def lookup(base_url: str, isrc: str | None = None, artist: str | None = None,
           title: str | None = None) -> dict:
    """GET {base_url}/api/tracks/lookup. Contratto: serve isrc OPPURE artist+title.

    Ritorna il body JSON del contratto:
    {"found": bool, "match": "isrc"|"fuzzy"|None, "track_id": int|None,
     "artist": ..., "title": ..., "genre": ..., "genre_secondary": ...,
     "label": ..., "year": ..., "confidence": 100|70|0}
    Solleva CratoryUnreachable su timeout, errore di rete o status != 2xx.
    """
    params: dict[str, str] = {}
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
    except httpx.HTTPError as exc:
        raise CratoryUnreachable(str(exc)) from exc
```

- [ ] **Step 4: Lancia, verifica PASS**

Run: `cd ~/Develop/DjOrganizer01/backend && .venv/bin/python -m pytest tests/test_cratory_bridge.py -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
cd ~/Develop/DjOrganizer01
git add backend/app/services/cratory_bridge.py backend/tests/test_cratory_bridge.py
git commit -m "feat(api): client read-only cratory_bridge.lookup (httpx, timeout 3s)"
```

---

### Task 4: Settings — esporre `cratory_base_url` in GET/PUT

**Files:**
- Modify: `backend/app/services/planning.py` (`update_settings`)
- Modify: `backend/app/schemas.py` (`SettingsRead`, `SettingsUpdate`)
- Modify: `backend/app/routers/settings.py` (`_read`, `put_settings`)
- Test: `backend/tests/test_settings_api.py`

**Interfaces:**
- Produces: `planning.update_settings(db, naming_template=None, folder_template=None, cratory_base_url=None) -> Settings` — `None` = non toccare, stringa vuota (o solo spazi) = disattiva il bridge (colonna a `NULL`). `GET/PUT /api/settings` ora includono `cratory_base_url: str | None`.
- Nota: la colonna `Settings.cratory_base_url` esiste già in `models.py` (dormiente) — nessuna migrazione necessaria.

- [ ] **Step 1: Test che fallisce**

In `backend/tests/test_settings_api.py`, aggiungi in fondo:

```python
def test_settings_cratory_base_url_roundtrip(db):
    with TestClient(app) as client:
        assert client.get("/api/settings").json()["cratory_base_url"] is None
        r = client.put("/api/settings", json={"cratory_base_url": "http://localhost:8000"})
        assert r.status_code == 200
        assert r.json()["cratory_base_url"] == "http://localhost:8000"
        # gli altri campi non vengono toccati
        assert r.json()["naming_template"] == "{artist} - {title}"
        # stringa vuota = bridge disattivato (torna NULL)
        r2 = client.put("/api/settings", json={"cratory_base_url": "  "})
        assert r2.json()["cratory_base_url"] is None
        # PUT senza il campo = non toccare
        client.put("/api/settings", json={"cratory_base_url": "http://localhost:8000"})
        r3 = client.put("/api/settings", json={"folder_template": "{genre}"})
        assert r3.json()["cratory_base_url"] == "http://localhost:8000"
```

- [ ] **Step 2: Lancia, verifica FAIL**

Run: `cd ~/Develop/DjOrganizer01/backend && .venv/bin/python -m pytest tests/test_settings_api.py -q`
Expected: FAIL — `KeyError: 'cratory_base_url'` (il campo non è nel body della risposta).

- [ ] **Step 3: Implementa**

In `backend/app/schemas.py`, sostituisci `SettingsRead` e `SettingsUpdate`:

```python
class SettingsRead(BaseModel):
    naming_template: str
    folder_template: str
    cratory_base_url: str | None
    roots: list[RootTargetRead]


class SettingsUpdate(BaseModel):
    naming_template: str | None = None
    folder_template: str | None = None
    cratory_base_url: str | None = None
```

In `backend/app/services/planning.py`, sostituisci `update_settings`:

```python
def update_settings(db: Session, naming_template=None, folder_template=None,
                    cratory_base_url=None) -> Settings:
    s = get_settings(db)
    if naming_template is not None:
        s.naming_template = naming_template
    if folder_template is not None:
        s.folder_template = folder_template
    if cratory_base_url is not None:
        # Stringa vuota = bridge disattivato (colonna a NULL).
        s.cratory_base_url = cratory_base_url.strip() or None
    s.updated_at = utcnow()
    db.commit()
    db.refresh(s)
    return s
```

In `backend/app/routers/settings.py`, in `_read`, sostituisci il `return`:

```python
    return SettingsRead(naming_template=s.naming_template,
                        folder_template=s.folder_template,
                        cratory_base_url=s.cratory_base_url, roots=roots)
```

e in `put_settings` sostituisci la chiamata:

```python
    planning.update_settings(db, naming_template=body.naming_template,
                             folder_template=body.folder_template,
                             cratory_base_url=body.cratory_base_url)
```

- [ ] **Step 4: Lancia, verifica PASS**

Run: `cd ~/Develop/DjOrganizer01/backend && .venv/bin/python -m pytest tests/test_settings_api.py -q`
Expected: PASS (i 4 test esistenti + il nuovo).

- [ ] **Step 5: Commit**

```bash
cd ~/Develop/DjOrganizer01
git add backend/app/schemas.py backend/app/services/planning.py backend/app/routers/settings.py backend/tests/test_settings_api.py
git commit -m "feat(api): Settings espone cratory_base_url in GET/PUT (vuoto = off)"
```

---

### Task 5: Analysis — `bridge_mismatch` sopravvive al recompute

**Files:**
- Modify: `backend/app/services/analysis.py` (`_merge_issues`)
- Test: `backend/tests/test_analysis_issues.py`

**Interfaces:**
- Produces: `_merge_issues` non cancella più le issue di tipo `bridge_mismatch` anche se l'Inspector non le ricalcola (non può: non conosce Cratory). Le riconcilia l'endpoint `bridge-suggest` (Task 6). Senza questa esenzione ogni scan (che ri-esegue l'analisi) spazzerebbe via le discrepanze appena segnalate.

- [ ] **Step 1: Test che fallisce**

In `backend/tests/test_analysis_issues.py`, aggiungi in fondo:

```python
def test_recompute_preserves_bridge_mismatch(db):
    # bridge_mismatch non è calcolata dall'Inspector (viene da Cratory):
    # il merge non deve cancellarla, la riconcilia /api/issues/bridge-suggest.
    _add_file(db, path="/m/a.mp3", artist="Sconosciuto", title="Acid Face",
              genre="Techno", year=2020, label="X",
              duration_s=200.0, bitrate=320000, content_hash="a", isrc="DEAB12300123")
    f = db.scalar(select(AudioFile))
    db.add(Issue(file_id=f.id, type="bridge_mismatch", field="artist",
                 severity="warning", detail="Cratory (ISRC): artist diverso",
                 suggested_fix_json={"field": "artist", "action": "retag", "to": "Rataxes"},
                 status="open"))
    db.commit()
    recompute(db)
    kept = db.scalars(select(Issue).where(Issue.type == "bridge_mismatch")).all()
    assert len(kept) == 1
    assert kept[0].suggested_fix_json == {"field": "artist", "action": "retag",
                                          "to": "Rataxes"}
    assert kept[0].status == "open"
```

- [ ] **Step 2: Lancia, verifica FAIL**

Run: `cd ~/Develop/DjOrganizer01/backend && .venv/bin/python -m pytest tests/test_analysis_issues.py::test_recompute_preserves_bridge_mismatch -q`
Expected: FAIL — `len(kept) == 0` (il merge la cancella perché l'Inspector non l'ha ricalcolata).

- [ ] **Step 3: Implementa in `backend/app/services/analysis.py`**

Sopra `_merge_issues` aggiungi la costante:

```python
# Issue di provenienza esterna (bridge Cratory): l'Inspector non le calcola,
# quindi il merge non deve cancellarle. Le riconcilia /api/issues/bridge-suggest.
_EXTERNAL_TYPES = {"bridge_mismatch"}
```

e in `_merge_issues` sostituisci il loop finale di cancellazione:

```python
    for key, row in existing.items():
        if key not in seen and row.type not in _EXTERNAL_TYPES:
            db.delete(row)
```

- [ ] **Step 4: Lancia, verifica PASS**

Run: `cd ~/Develop/DjOrganizer01/backend && .venv/bin/python -m pytest tests/test_analysis_issues.py -q`
Expected: PASS (tutti, inclusi i preesistenti sul merge).

- [ ] **Step 5: Commit**

```bash
cd ~/Develop/DjOrganizer01
git add backend/app/services/analysis.py backend/tests/test_analysis_issues.py
git commit -m "feat(api): il merge dell'analisi preserva le issue bridge_mismatch"
```

---

### Task 6: Endpoint `POST /api/issues/bridge-suggest`

**Files:**
- Modify: `backend/app/routers/issues.py`
- Test: `backend/tests/test_bridge_suggest_api.py` (nuovo)

**Interfaces:**
- Produces: `POST /api/issues/bridge-suggest` → `{"configured": bool, "files": int, "suggested": int, "unresolved": int, "mismatches": int}`. Un solo endpoint fa entrambe le cose (design più semplice coerente col router): (1) riempie `suggested_fix_json` sulle issue **aperte** di tipo `missing_required_tag` (field `artist`/`title`), `missing_metadata` (field `genre`/`year`/`label`) e `dirty_genre` (field `genre`) — questi sono i nomi reali in `services/inspector.py`; (2) apre/riconcilia le issue `bridge_mismatch` (severità `warning`, mai auto-applicate) per i file con ISRC il cui lookup ISRC su Cratory ritorna artist/title normalizzati diversi.
- Consumes: `planning.get_settings(db).cratory_base_url`, `cratory_bridge.lookup(...)` (una sola chiamata HTTP per file, con cache locale), `utcnow()`.
- Degradazione: `cratory_base_url` non impostato **oppure** `CratoryUnreachable` durante il run → `{"configured": false, ...}` con `db.rollback()` (nessuna modifica parziale), stessa UX di `ai-suggest` senza `ANTHROPIC_API_KEY`.
- Chiave di lookup per file: ISRC se presente, altrimenti artist+title se entrambi presenti, altrimenti nessuna chiamata (issue conteggiata `unresolved`). Il check discrepanze usa SOLO risposte con `match == "isrc"` (confidence 100), mai fuzzy; se il file non ha ISRC il check si salta.

- [ ] **Step 1: Test che falliscono**

Crea `backend/tests/test_bridge_suggest_api.py`:

```python
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.models import AudioFile, Issue, Settings
from app.services import cratory_bridge

FOUND = {"found": True, "match": "isrc", "track_id": 7, "artist": "Rataxes",
         "title": "Acid Face", "genre": "Acid Techno", "genre_secondary": None,
         "label": "Bunker", "year": 2024, "confidence": 100}
NOT_FOUND = {"found": False, "match": None, "track_id": None, "artist": None,
             "title": None, "genre": None, "genre_secondary": None, "label": None,
             "year": None, "confidence": 0}
EMPTY = {"configured": False, "files": 0, "suggested": 0,
         "unresolved": 0, "mismatches": 0}


def _configure(db, url="http://localhost:8000"):
    db.add(Settings(id=1, naming_template="{artist} - {title}",
                    folder_template="{genre}/{artist}", cratory_base_url=url))
    db.commit()


def _file(db, file_id, **kw):
    defaults = dict(root_id=1, path=f"/m/{file_id}.mp3", ext="mp3", size_bytes=1,
                    hash_method="file", status="present", has_cover=False)
    defaults.update(kw)
    db.add(AudioFile(id=file_id, **defaults))


def test_bridge_not_configured(db):
    with TestClient(app) as client:
        assert client.post("/api/issues/bridge-suggest").json() == EMPTY


def test_bridge_fills_missing_metadata_via_isrc(db, monkeypatch):
    _configure(db)
    _file(db, 1, artist="Rataxes", title="Acid Face", genre=None, year=None,
          label=None, isrc="DEAB12300123")
    for field in ("genre", "year", "label"):
        db.add(Issue(file_id=1, type="missing_metadata", field=field,
                     severity="warning", detail=f"{field} mancante",
                     suggested_fix_json=None, status="open"))
    db.commit()
    calls = []

    def fake(base_url, isrc=None, artist=None, title=None):
        calls.append({"base_url": base_url, "isrc": isrc,
                      "artist": artist, "title": title})
        return dict(FOUND)

    monkeypatch.setattr(cratory_bridge, "lookup", fake)
    with TestClient(app) as client:
        r = client.post("/api/issues/bridge-suggest").json()
        assert r == {"configured": True, "files": 1, "suggested": 3,
                     "unresolved": 0, "mismatches": 0}
        # una sola chiamata HTTP per file (cache), preferendo l'ISRC
        assert calls == [{"base_url": "http://localhost:8000",
                          "isrc": "DEAB12300123", "artist": None, "title": None}]
        rows = client.get("/api/issues", params={"type": "missing_metadata"}).json()
        by_field = {i["field"]: i for i in rows}
        assert by_field["genre"]["suggested_fix_json"] == {
            "field": "genre", "action": "retag", "to": "Acid Techno"}
        assert by_field["year"]["suggested_fix_json"]["to"] == 2024
        assert by_field["label"]["suggested_fix_json"]["to"] == "Bunker"
        assert all(i["status"] == "open" for i in rows)  # mai auto-accettate


def test_bridge_fills_artist_title_via_isrc(db, monkeypatch):
    _configure(db)
    _file(db, 2, artist=None, title=None, isrc="DEAB12300123")
    for field in ("artist", "title"):
        db.add(Issue(file_id=2, type="missing_required_tag", field=field,
                     severity="error", detail=f"{field} mancante",
                     suggested_fix_json=None, status="open"))
    db.commit()
    monkeypatch.setattr(cratory_bridge, "lookup", lambda base_url, **kw: dict(FOUND))
    with TestClient(app) as client:
        r = client.post("/api/issues/bridge-suggest").json()
        assert r["files"] == 1 and r["suggested"] == 2 and r["mismatches"] == 0
        rows = client.get("/api/issues", params={"type": "missing_required_tag"}).json()
        by_field = {i["field"]: i for i in rows}
        assert by_field["artist"]["suggested_fix_json"]["to"] == "Rataxes"
        assert by_field["title"]["suggested_fix_json"]["to"] == "Acid Face"


def test_bridge_fuzzy_fills_dirty_genre(db, monkeypatch):
    _configure(db)
    _file(db, 3, artist="Rataxes", title="Acid Face",
          genre="Techno, House, Acid", isrc=None)
    db.add(Issue(file_id=3, type="dirty_genre", field="genre", severity="warning",
                 detail="genere da normalizzare", suggested_fix_json=None,
                 status="open"))
    db.commit()
    calls = []

    def fake(base_url, isrc=None, artist=None, title=None):
        calls.append({"isrc": isrc, "artist": artist, "title": title})
        return dict(FOUND, match="fuzzy", confidence=70)

    monkeypatch.setattr(cratory_bridge, "lookup", fake)
    with TestClient(app) as client:
        r = client.post("/api/issues/bridge-suggest").json()
        assert r["suggested"] == 1 and r["mismatches"] == 0  # fuzzy: mai mismatch
        assert calls == [{"isrc": None, "artist": "Rataxes", "title": "Acid Face"}]
        rows = client.get("/api/issues", params={"type": "dirty_genre"}).json()
        assert rows[0]["suggested_fix_json"]["to"] == "Acid Techno"


def test_bridge_overwrites_open_ai_suggestion(db, monkeypatch):
    # Precedenza: Cratory > AI. Un suggerimento AI non ancora accettato
    # (status open) viene sovrascritto dal bridge.
    _configure(db)
    _file(db, 4, artist="Rataxes", title="Acid Face", genre=None, isrc=None)
    db.add(Issue(file_id=4, type="missing_metadata", field="genre", severity="warning",
                 detail="genre mancante",
                 suggested_fix_json={"field": "genre", "action": "retag", "to": "House"},
                 status="open"))
    db.commit()
    monkeypatch.setattr(cratory_bridge, "lookup",
                        lambda base_url, **kw: dict(FOUND, match="fuzzy", confidence=70))
    with TestClient(app) as client:
        r = client.post("/api/issues/bridge-suggest").json()
        assert r["suggested"] == 1
        rows = client.get("/api/issues", params={"type": "missing_metadata"}).json()
        assert rows[0]["suggested_fix_json"]["to"] == "Acid Techno"


def test_bridge_never_touches_accepted(db, monkeypatch):
    # Precedenza: fix manuale/accettato > Cratory. Status != open: intoccabile.
    _configure(db)
    _file(db, 5, artist="Rataxes", title="Acid Face", genre=None, isrc=None)
    db.add(Issue(file_id=5, type="missing_metadata", field="genre", severity="warning",
                 detail="genre mancante",
                 suggested_fix_json={"field": "genre", "action": "retag",
                                     "to": "Scelto A Mano"},
                 status="accepted"))
    db.commit()
    monkeypatch.setattr(cratory_bridge, "lookup", lambda base_url, **kw: dict(FOUND))
    with TestClient(app) as client:
        r = client.post("/api/issues/bridge-suggest").json()
        assert r["files"] == 0 and r["suggested"] == 0
        rows = client.get("/api/issues", params={"type": "missing_metadata"}).json()
        assert rows[0]["suggested_fix_json"]["to"] == "Scelto A Mano"
        assert rows[0]["status"] == "accepted"


def test_bridge_unresolved_without_key_or_match(db, monkeypatch):
    _configure(db)
    # File 6: niente ISRC, artist mancante -> nessuna chiave -> nessuna chiamata.
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
    calls = []

    def fake(base_url, isrc=None, artist=None, title=None):
        calls.append(artist)
        return dict(NOT_FOUND)

    monkeypatch.setattr(cratory_bridge, "lookup", fake)
    with TestClient(app) as client:
        r = client.post("/api/issues/bridge-suggest").json()
        assert r == {"configured": True, "files": 2, "suggested": 0,
                     "unresolved": 2, "mismatches": 0}
        assert calls == ["Ignoto"]  # per il file 6 nessuna chiamata (niente chiave)


def test_bridge_mismatch_on_isrc_conflict(db, monkeypatch):
    _configure(db)
    _file(db, 8, artist="Sconosciuto", title="Acid Face", genre="Acid Techno",
          year=2024, label="Bunker", isrc="DEAB12300123")
    db.commit()
    monkeypatch.setattr(cratory_bridge, "lookup", lambda base_url, **kw: dict(FOUND))
    with TestClient(app) as client:
        r = client.post("/api/issues/bridge-suggest").json()
        assert r["mismatches"] == 1
        rows = client.get("/api/issues", params={"type": "bridge_mismatch"}).json()
        assert len(rows) == 1
        assert rows[0]["field"] == "artist"
        assert rows[0]["severity"] == "warning"
        assert rows[0]["status"] == "open"  # mai auto-applicata
        assert rows[0]["suggested_fix_json"] == {"field": "artist", "action": "retag",
                                                 "to": "Rataxes"}
        # idempotente: un secondo run non duplica la issue
        client.post("/api/issues/bridge-suggest")
        rows2 = client.get("/api/issues", params={"type": "bridge_mismatch"}).json()
        assert len(rows2) == 1


def test_bridge_mismatch_skipped_without_isrc(db, monkeypatch):
    _configure(db)
    _file(db, 9, artist="Altro Artista", title="Altro Titolo", genre=None, isrc=None)
    db.add(Issue(file_id=9, type="missing_metadata", field="genre", severity="warning",
                 detail="genre mancante", suggested_fix_json=None, status="open"))
    db.commit()
    # Cratory risponde fuzzy con artist/title DIVERSI: senza ISRC niente mismatch.
    monkeypatch.setattr(cratory_bridge, "lookup",
                        lambda base_url, **kw: dict(FOUND, match="fuzzy", confidence=70))
    with TestClient(app) as client:
        r = client.post("/api/issues/bridge-suggest").json()
        assert r["mismatches"] == 0
        assert client.get("/api/issues", params={"type": "bridge_mismatch"}).json() == []


def test_bridge_mismatch_resolved_is_removed(db, monkeypatch):
    _configure(db)
    # Il tag ora coincide con Cratory: la vecchia discrepanza va rimossa.
    _file(db, 10, artist="Rataxes", title="Acid Face", isrc="DEAB12300123")
    db.add(Issue(file_id=10, type="bridge_mismatch", field="artist",
                 severity="warning", detail="vecchia discrepanza",
                 suggested_fix_json={"field": "artist", "action": "retag",
                                     "to": "Rataxes"},
                 status="open"))
    db.commit()
    monkeypatch.setattr(cratory_bridge, "lookup", lambda base_url, **kw: dict(FOUND))
    with TestClient(app) as client:
        r = client.post("/api/issues/bridge-suggest").json()
        assert r["mismatches"] == 0
        assert client.get("/api/issues", params={"type": "bridge_mismatch"}).json() == []


def test_bridge_unreachable_degrades_cleanly(db, monkeypatch):
    _configure(db)
    _file(db, 11, artist="Rataxes", title="Acid Face", genre=None, isrc="DEAB12300123")
    db.add(Issue(file_id=11, type="missing_metadata", field="genre", severity="warning",
                 detail="genre mancante", suggested_fix_json=None, status="open"))
    db.commit()

    def boom(base_url, **kw):
        raise cratory_bridge.CratoryUnreachable("timeout")

    monkeypatch.setattr(cratory_bridge, "lookup", boom)
    with TestClient(app) as client:
        assert client.post("/api/issues/bridge-suggest").json() == EMPTY
        # nessuna modifica parziale: il suggerimento resta vuoto
        rows = client.get("/api/issues", params={"type": "missing_metadata"}).json()
        assert rows[0]["suggested_fix_json"] is None
```

- [ ] **Step 2: Lancia, verifica FAIL**

Run: `cd ~/Develop/DjOrganizer01/backend && .venv/bin/python -m pytest tests/test_bridge_suggest_api.py -q`
Expected: FAIL — 404 su `/api/issues/bridge-suggest` (endpoint inesistente) ⇒ `json()` non combacia con `EMPTY` e simili.

- [ ] **Step 3: Implementa in `backend/app/routers/issues.py`**

Aggiorna gli import in testa al file:

```python
import os
import re

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import AudioFile, Issue, utcnow
from app.schemas import IssueBulkBody, IssueFixBody, IssueRead, IssueStatusBody
from app.services import ai_tags, cratory_bridge, planning
```

e aggiungi in fondo al file:

```python
# --- Bridge Cratory ----------------------------------------------------------
# Precedenza valori (spec ecosistema): fix manuale > tag pulito nel file >
# suggerimento Cratory > AI-da-filename. Il bridge tocca SOLO issue aperte:
# un tag pulito non ha issue (mai toccato), un fix manuale/accettato ha
# status != "open" (mai toccato). Sovrascrive invece un suggerimento AI non
# ancora accettato (Cratory > AI); gli endpoint AI, che saltano le issue già
# suggerite, non sovrascrivono mai il bridge.

_BRIDGE_TYPES = ("missing_required_tag", "missing_metadata", "dirty_genre")
_BRIDGE_FIELDS = ("artist", "title", "genre", "year", "label")
_NOT_CONFIGURED = {"configured": False, "files": 0, "suggested": 0,
                   "unresolved": 0, "mismatches": 0}


def _norm(s) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


@router.post("/bridge-suggest", response_model=dict)
def bridge_suggest(db: Session = Depends(get_db)):
    base_url = (planning.get_settings(db).cratory_base_url or "").strip()
    if not base_url:
        return dict(_NOT_CONFIGURED)

    rows = db.execute(
        select(Issue, AudioFile)
        .join(AudioFile, Issue.file_id == AudioFile.id)
        .where(Issue.status == "open", Issue.type.in_(_BRIDGE_TYPES),
               Issue.field.in_(_BRIDGE_FIELDS))
    ).all()
    isrc_files = [f for f in db.scalars(
        select(AudioFile).where(AudioFile.status == "present",
                                AudioFile.isrc.is_not(None))
    ).all() if (f.isrc or "").strip()]

    cache: dict[int, dict | None] = {}

    def _lookup(f: AudioFile) -> dict | None:
        """Una sola lookup HTTP per file (cache). None = nessuna chiave usabile."""
        if f.id not in cache:
            if (f.isrc or "").strip():
                cache[f.id] = cratory_bridge.lookup(base_url, isrc=f.isrc.strip())
            elif (f.artist or "").strip() and (f.title or "").strip():
                cache[f.id] = cratory_bridge.lookup(
                    base_url, artist=f.artist.strip(), title=f.title.strip())
            else:
                cache[f.id] = None
        return cache[f.id]

    suggested = unresolved = mismatches = 0
    files_seen: set[int] = set()
    try:
        # 1) Riempi suggested_fix sulle issue aperte esistenti (mai su tag puliti:
        #    un tag pulito non ha issue). Mai auto-accettare: status resta open.
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

        # 2) Pulisci le bridge_mismatch orfane (file non più presente o senza
        #    più ISRC): il merge dell'analisi le esenta dalla cancellazione,
        #    quindi la riconciliazione avviene qui.
        for issue, f in db.execute(
            select(Issue, AudioFile).join(AudioFile, Issue.file_id == AudioFile.id)
            .where(Issue.type == "bridge_mismatch")
        ).all():
            if f.status != "present" or not (f.isrc or "").strip():
                db.delete(issue)

        # 3) Check discrepanze: solo match ISRC (confidence 100), mai fuzzy.
        #    Senza ISRC nel file il check si salta.
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
            existing = {i.field: i for i in db.scalars(
                select(Issue).where(Issue.file_id == f.id,
                                    Issue.type == "bridge_mismatch")).all()}
            for field, c_val in expected.items():
                detail = (f"Cratory (ISRC {f.isrc.strip()}): {field} = '{c_val}', "
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
                    row.detail = detail
                    if row.status == "open":  # le decisioni utente sono intoccabili
                        row.suggested_fix_json = {"field": field,
                                                  "action": "retag", "to": c_val}
                        mismatches += 1
                    row.updated_at = utcnow()
            for field, row in existing.items():
                if field not in expected:
                    db.delete(row)  # discrepanza risolta (o non più confermata)
    except cratory_bridge.CratoryUnreachable:
        # Degradazione pulita: niente modifiche parziali, stessa UX del
        # non-configurato (come ai-suggest senza ANTHROPIC_API_KEY).
        db.rollback()
        return dict(_NOT_CONFIGURED)

    db.commit()
    return {"configured": True, "files": len(files_seen), "suggested": suggested,
            "unresolved": unresolved, "mismatches": mismatches}
```

- [ ] **Step 4: Lancia, verifica PASS**

Run: `cd ~/Develop/DjOrganizer01/backend && .venv/bin/python -m pytest tests/test_bridge_suggest_api.py -q`
Expected: PASS (11 passed).

- [ ] **Step 5: Suite intera backend**

Run: `cd ~/Develop/DjOrganizer01/backend && .venv/bin/python -m pytest -q`
Expected: tutti verdi, zero warning (i 148 preesistenti + i nuovi dei Task 1–6).

- [ ] **Step 6: Commit**

```bash
cd ~/Develop/DjOrganizer01
git add backend/app/routers/issues.py backend/tests/test_bridge_suggest_api.py
git commit -m "feat(api): POST /api/issues/bridge-suggest — suggerimenti e discrepanze da Cratory"
```

---

### Task 7: Frontend — Settings + bottone "Suggerisci da Cratory"

**Files:**
- Modify: `frontend/lib/api.ts`
- Modify: `frontend/app/settings/page.tsx`
- Modify: `frontend/app/issues/page.tsx`

**Interfaces:**
- Consumes: `GET/PUT /api/settings` (ora con `cratory_base_url`), `POST /api/issues/bridge-suggest`.
- Produces: `bridgeSuggest(): Promise<BridgeSuggestResult>`; campo Cratory nella pagina Settings (vuoto = off, pattern del form esistente); bottone "Suggerisci da Cratory" nella marginalia di Issues accanto ai bottoni AI (stessa UX degli endpoint AI: disabilitato mentre è in corso; se non configurato, l'endpoint risponde `configured:false` e la pagina mostra l'alert con l'istruzione — identico al pattern `ANTHROPIC_API_KEY`).

- [ ] **Step 1: `frontend/lib/api.ts` — tipi e client**

Nella sezione `--- SETTINGS ---`, sostituisci `Settings` e `updateSettings`:

```ts
export interface Settings {
  naming_template: string;
  folder_template: string;
  cratory_base_url: string | null;
  roots: RootTarget[];
}
export function getSettings() {
  return apiGet<Settings>("/api/settings");
}
export function updateSettings(body: {
  naming_template?: string;
  folder_template?: string;
  cratory_base_url?: string;
}) {
  return apiSend<Settings>("PUT", "/api/settings", body);
}
```

Nella sezione `--- ISSUES ---`, dopo `aiSuggestGenres`, aggiungi:

```ts
export interface BridgeSuggestResult {
  configured: boolean;
  files: number;
  suggested: number;
  unresolved: number;
  mismatches: number;
}
export function bridgeSuggest() {
  return apiSend<BridgeSuggestResult>("POST", "/api/issues/bridge-suggest");
}
```

- [ ] **Step 2: `frontend/app/settings/page.tsx` — campo Cratory**

Aggiungi lo state accanto a `naming`/`folder`:

```tsx
  const [cratory, setCratory] = useState("");
```

In `load`, estendi il `.then`:

```tsx
    getSettings()
      .then((s) => {
        setSettings(s); setNaming(s.naming_template); setFolder(s.folder_template);
        setCratory(s.cratory_base_url ?? ""); setOffline(false);
      })
      .catch(() => setOffline(true));
```

Dopo `saveTarget`, aggiungi:

```tsx
  const saveCratory = async () => {
    setError(null);
    try { setSettings(await updateSettings({ cratory_base_url: cratory.trim() })); }
    catch (e) { setError(e instanceof Error ? e.message : "Errore"); }
  };
```

Nel JSX, dopo il `<Button …>salva template</Button>` e prima del blocco "dove organizzare", aggiungi:

```tsx
            <label className="block">
              <span className="mb-1.5 block text-[10px] font-medium uppercase tracking-wider text-muted">cratory (bridge sola-lettura)</span>
              <input className="w-full border border-border bg-surface px-3 py-2 text-sm text-fg-strong focus:border-border-strong focus:outline-none"
                value={cratory} onChange={(e) => setCratory(e.target.value)} placeholder="http://localhost:8000" />
              <span className="mt-1.5 block text-xs text-faint">vuoto = bridge disattivato. Suggerisce genere/label/anno/artista/titolo dalla libreria di Cratory (deve essere in esecuzione).</span>
            </label>

            <Button variant="outline" size="sm" className="self-start" onClick={saveCratory}>salva cratory</Button>
```

- [ ] **Step 3: `frontend/app/issues/page.tsx` — bottone e nota**

Aggiorna l'import da `@/lib/api`:

```tsx
import {
  listIssues, listSources, setIssueStatus, fixIssue, bulkIssues, aiSuggestTags, aiSuggestGenres,
  bridgeSuggest, type Issue, type ScanRoot,
} from "@/lib/api";
```

Aggiungi lo state accanto a `genreBusy`:

```tsx
  const [bridgeBusy, setBridgeBusy] = useState(false);
```

Dopo `onAiGenres`, aggiungi:

```tsx
  const onBridge = async () => {
    setActionError(null);
    setAiNote(null);
    setBridgeBusy(true);
    try {
      const r = await bridgeSuggest();
      if (!r.configured) {
        setActionError("Configura l'URL di Cratory in Settings (e verifica che Cratory sia in esecuzione).");
      } else {
        load();
        setAiNote(
          `${r.suggested} suggerimenti da Cratory${r.mismatches > 0 ? `, ${r.mismatches} discrepanze ISRC segnalate` : ""}${r.unresolved > 0 ? `, ${r.unresolved} non trovati` : ""} — rivedi e accetta col ✓.`,
        );
      }
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Errore");
    } finally {
      setBridgeBusy(false);
    }
  };
```

Nell'invocazione di `<Marginalia …>`, aggiungi le due prop:

```tsx
          onAiGenres={onAiGenres} genreBusy={genreBusy}
          onBridge={onBridge} bridgeBusy={bridgeBusy}
```

Aggiorna la firma di `Marginalia` (parametri + tipi):

```tsx
function Marginalia({ total, bySev, byType, accepted, onAcceptFixable, onDismissInfo, onAiSuggest, aiBusy, onAiGenres, genreBusy, onBridge, bridgeBusy }: {
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
  onBridge: () => void;
  bridgeBusy: boolean;
}) {
```

e nel blocco dei bottoni, dopo il bottone "✨ Suggerisci genere" e prima di "✓ accetta tutti i fixabili", aggiungi:

```tsx
        <Button variant="primary" size="sm" onClick={onBridge} disabled={bridgeBusy}>
          {bridgeBusy ? "Cratory in corso…" : "⇄ Suggerisci da Cratory"}
        </Button>
```

- [ ] **Step 4: Lint + build**

Run: `cd ~/Develop/DjOrganizer01/frontend && npm run lint && npm run build`
Expected: entrambi verdi, zero errori TypeScript.

- [ ] **Step 5: Commit**

```bash
cd ~/Develop/DjOrganizer01
git add frontend/lib/api.ts frontend/app/settings/page.tsx frontend/app/issues/page.tsx
git commit -m "feat(fe): campo Cratory in Settings + bottone 'Suggerisci da Cratory' in Issues"
```

---

### Task 8: Verifica finale — suite completa + lint + build

**Files:**
- Nessuna modifica: solo verifica.

- [ ] **Step 1: Suite backend completa**

Run: `cd ~/Develop/DjOrganizer01/backend && .venv/bin/python -m pytest -q`
Expected: **tutti verdi, zero warning** (148 preesistenti + ~20 nuovi: 2 scanner, 3 tagio, 1 schema, 4 client bridge, 1 settings, 1 analysis, 11 endpoint bridge).

- [ ] **Step 2: Frontend lint + build**

Run: `cd ~/Develop/DjOrganizer01/frontend && npm run lint && npm run build`
Expected: entrambi verdi.

- [ ] **Step 3: Smoke test manuale di degradazione (opzionale ma raccomandato)**

Con il backend avviato (porta 8010) e **Cratory spento**:

```bash
curl -s -X POST http://localhost:8010/api/issues/bridge-suggest
```

Expected: `{"configured":false,"files":0,"suggested":0,"unresolved":0,"mismatches":0}` sia con `cratory_base_url` non impostato, sia impostato ma con Cratory spento (timeout ~3s al massimo per la prima chiamata). Tutto il resto dell'app funziona come oggi.

- [ ] **Step 4: Chiusura branch**

Il lavoro resta su `feat/cratory-bridge`; per l'integrazione usare superpowers:finishing-a-development-branch (merge su `main` o PR, a scelta dell'utente).

---

## Self-Review

**1. Copertura spec:**
- Precedenza manuale > tag pulito > Cratory > AI → solo issue `open`, sovrascrittura dei suggerimenti AI aperti, test `test_bridge_never_touches_accepted` + `test_bridge_overwrites_open_ai_suggestion` ✓
- Tipi issue reali (`missing_required_tag`, `missing_metadata`, `dirty_genre` — verificati in `services/inspector.py`) ✓
- `bridge_mismatch` warning, solo con ISRC + match `isrc`, mai auto-applicata, riconciliata (creazione/aggiornamento/rimozione) ✓; esenzione nel merge dell'analisi (Task 5) perché ogni scan ri-esegue `recompute` ✓
- `tagio.read_tags` oggi NON legge l'ISRC → aggiunto (TSRC/vorbis, Task 2) con colonna `AudioFile.isrc` e ALTER in `ensure_schema` (pattern `target_root`) ✓
- Degradazione: URL vuoto o `CratoryUnreachable` → `{"configured": false}` + rollback, timeout 3s ✓
- Settings GET/PUT + frontend ✓; bottone Issues con pattern UX identico agli endpoint AI ✓
- Scanner salta `.quarantine` e le dir nascoste, con test ✓

**2. Placeholder scan:** nessun TBD/TODO; ogni step mostra il codice reale completo.

**3. Coerenza tipi/nomi:**
- `suggested_fix_json = {"field", "action": "retag", "to"}` ↔ `planner.effective_tags` / `_RETAGGABLE` (artist/title/genre/year/label tutti retaggabili) ✓
- `year` suggerito come `int` dal contratto: `planner._render` fa `str(...)` e `tagio.write_tags` fa `str(value)` → ok ✓
- `Settings` (models) vs `SettingsRead/Update` (schemas) non confusi; il test dell'endpoint importa `Settings` da `app.models` ✓
- `httpx` già in `requirements.txt` (nessuna dipendenza nuova) ✓
- filtro JSON-null in Python (convenzione del codebase) — il bridge non filtra affatto su `suggested_fix_json` (sovrascrive gli open), gli AI restano invariati ✓

## Execution Handoff

Eseguire con superpowers:subagent-driven-development (un task per subagente, verificando i comandi Run/Expected) oppure superpowers:executing-plans inline. Branch: `feat/cratory-bridge` da `main`.
