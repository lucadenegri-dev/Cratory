# Discovery dig — lead-disco con tracklist Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Il dig Discovery tratta ogni lead Discogs come un disco: si apre su una tracklist reale (fetch lazy da Discogs), e le azioni "Scarica ora" / "Per dopo" vivono per singola traccia dentro quel pannello, non più sul lead-riga.

**Architecture:** Backend: un nuovo metodo `DiscogsClient.get_release()` + endpoint `GET /api/discovery/release/{discogs_id}` normalizzano la tracklist reale; un `format_badge` deterministico si aggiunge a costo zero ai lead esistenti; una playlist di sistema "Scoperte" (idempotente, `kind="discovery"`) raccoglie le tracce "per dopo"; un nuovo job-starter `start_track_autopick_job` + endpoint `POST /api/downloads/track/auto` abilitano il download immediato di una singola traccia in auto-pick. Frontend: la griglia di copertine e il pannello tracklist sostituiscono la vecchia lista `LeadRow`; lo stato del form dig (seme/valore/adventurousness/riferimento gusto) vive nella query string.

**Tech Stack:** Backend Python/FastAPI/SQLAlchemy/SQLite (pytest, nessuna rete nei test — client HTTP iniettato/finto). Frontend Next.js 16 App Router + TypeScript + Tailwind (nessun framework di test e2e per questa pagina: verifica manuale via dev server).

## Global Constraints

- Motore deterministico, nessuna AI in questo slice.
- Nessuna tabella DB nuova, nessun job in background nuovo (solo una riga `Playlist` di sistema e due job-starter che riusano `_start`/`_run` esistenti).
- Fetch della tracklist Discogs lazy: solo all'apertura del pannello, mai in batch per tutta la griglia.
- Il modello `Track` e il download Soulseek restano per traccia singola.
- La modalità Expand (Last.fm, `services/discovery.py`, `routers/discovery.py` funzione `expand`) resta invariata: nessun task tocca quei percorsi.
- Riuso deliberato: `import_single_track`, `add_track_to_playlist`, il flusso "da sistemare" (`GET /api/downloads/pending`), il bulk download playlist (`POST /api/downloads/playlist/{playlist_id}`) — nessuno di questi si modifica.
- Design system "editorial archive": `rounded-none`, bordi hairline (`border-border`/`border-border-strong`), nessuna ombra. Riuso dei componenti esistenti in `frontend/components/ui.tsx` (`Modal`, `Card`, `Button`, `Alert`, `Spinner`/`Equalizer`).
- Frontend: leggere `frontend/CLAUDE.md` prima di toccare `frontend/app/discovery/page.tsx` — Next.js 16 in questo repo ha differenze rispetto al training data; l'API `useSearchParams`/`useRouter` di `next/navigation` usata in questo piano è verificata contro `frontend/node_modules/next/dist/docs/01-app/03-api-reference/04-functions/use-search-params.md` (stabile dalla v13, invariata in v16).
- Spec di riferimento: `docs/superpowers/specs/2026-07-09-discovery-dischi-tracklist-design.md`. Dove questo piano si discosta nei dettagli di schema (es. `DiscogsReleaseOut` non porta `format_badge`/community — vedi Task 3) è perché la spec demandava esplicitamente il dettaglio al piano.

---

### Task 1: `DiscogsClient.get_release()`

**Files:**
- Modify: `backend/app/integrations/discogs.py`
- Test: `backend/tests/test_discogs.py`

**Interfaces:**
- Produces: `DiscogsClient.get_release(release_id: int) -> dict[str, Any]` — GET `/releases/{release_id}`. A differenza di `search_releases`, **non** intercetta l'errore: solleva `DiscogsError` (già definita nel modulo) così il chiamante (Task 3) può distinguerlo e mostrarlo.

- [ ] **Step 1: Aggiungi `import pytest` e scrivi i test falliti**

`backend/tests/test_discogs.py` non importa `pytest` oggi (i test esistenti non ne hanno bisogno). Aggiungi l'import in testa al file e i due test in fondo:

```python
import pytest

from app.integrations.discogs import DiscogsClient, DiscogsError
```

(sostituisce la riga `from app.integrations.discogs import DiscogsClient` esistente in cima al file)

```python
def test_get_release_returns_payload():
    payload = {"id": 1, "title": "Selected Ambient Works 85-92"}
    http = _FakeHttp(payload)
    c = DiscogsClient(token=None, http=http)
    out = c.get_release(1)
    assert out == payload
    url, params = http.calls[0]
    assert url.endswith("/releases/1")


def test_get_release_error_raises():
    http = _FakeHttp({"error": "boom"}, status=500)
    c = DiscogsClient(token=None, http=http)
    with pytest.raises(DiscogsError):
        c.get_release(1)
```

- [ ] **Step 2: Esegui i test e verifica che falliscano**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_discogs.py -v`
Expected: FAIL — `AttributeError: 'DiscogsClient' object has no attribute 'get_release'`

- [ ] **Step 3: Implementa `get_release`**

In `backend/app/integrations/discogs.py`, subito dopo il metodo `search_releases` (fine del file):

```python
    def get_release(self, release_id: int) -> dict[str, Any]:
        """Dettaglio di una release, inclusa la tracklist reale.

        A differenza di search_releases (che degrada a lista vuota su errore:
        una ricerca fallita non deve rompere il dig), qui l'errore Discogs
        SOLLEVA DiscogsError: il chiamante (l'endpoint del Task 3) deve poterlo
        distinguere e mostrare, mai propagarlo come 500 grezzo.
        """
        return self._get(f"/releases/{release_id}")
```

- [ ] **Step 4: Esegui i test e verifica che passino**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_discogs.py -v`
Expected: PASS (tutti i test del file, inclusi quelli preesistenti)

- [ ] **Step 5: Commit**

```bash
git add backend/app/integrations/discogs.py backend/tests/test_discogs.py
git commit -m "feat(discogs): aggiungi get_release per il dettaglio di una release"
```

---

### Task 2: `format_badge` + `discogs_id` esposti sul lead

**Files:**
- Modify: `backend/app/services/discovery_dig.py`
- Modify: `backend/app/schemas.py`
- Modify: `backend/app/routers/discovery.py`
- Test: `backend/tests/test_discovery.py`

**Interfaces:**
- Consumes: nessuna dipendenza da Task 1.
- Produces: `DiscoveryLead.format_badge: str | None` (nuovo campo dataclass); `_format_badge(formats: set[str]) -> str | None` (funzione pura, per i test e per Task 3 se servisse riuso — qui resta locale a `discovery_dig.py`); `DiscoveryLeadOut.discogs_id: int | None` e `DiscoveryLeadOut.format_badge: str | None` (nuovi campi schema, consumati dal frontend in Task 7).

- [ ] **Step 1: Scrivi i test falliti**

In `backend/tests/test_discovery.py`, aggiungi (vicino agli altri test del dig, dopo `test_dig_endpoint_returns_reasons`):

```python
def test_format_badge_priority():
    from app.services.discovery_dig import _format_badge

    assert _format_badge({"vinyl", "ep"}) == "EP"
    assert _format_badge({"vinyl", "lp", "album"}) == "LP"  # LP ha priorità su Album
    assert _format_badge({"vinyl", "12\""}) == '12"'
    assert _format_badge({"vinyl"}) is None
    assert _format_badge(set()) is None


def test_dig_endpoint_exposes_discogs_id_and_format_badge(db, monkeypatch):
    release = {
        "id": 42, "title": "Cult - Grail", "year": 2024,
        "label": ["Lbl"], "style": ["Acid House"],
        "community": {"have": 3, "want": 120}, "format": ["Vinyl", "EP"],
        "uri": "/release/42", "cover_image": "http://img",
    }
    monkeypatch.setattr(
        DiscogsClient, "search_releases",
        lambda self, **kw: [release],
    )
    resp = dig_endpoint(DiscoveryDigRequest(seed_type="genre", value="Acid House"), db)
    lead = resp.leads[0]
    assert lead.discogs_id == 42
    assert lead.format_badge == "EP"
```

`DiscogsClient`, `dig_endpoint` e `DiscoveryDigRequest` sono già importati in cima al file (verifica: se non lo sono nel blocco dei test dig esistenti, aggiungi `from app.integrations.discogs import DiscogsClient`, `from app.routers.discovery import dig_endpoint`, `from app.schemas import DiscoveryDigRequest` — gli stessi import già usati da `test_dig_endpoint_returns_reasons` poco sopra nel file).

- [ ] **Step 2: Esegui i test e verifica che falliscano**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_discovery.py -k "format_badge or exposes_discogs_id" -v`
Expected: FAIL — `ImportError: cannot import name '_format_badge'` (primo test) e `AttributeError`/`ValidationError` su `lead.discogs_id`/`lead.format_badge` (secondo test)

- [ ] **Step 3: Implementa `_format_badge` e collegalo al lead**

In `backend/app/services/discovery_dig.py`, aggiungi vicino alle altre costanti di modulo (dopo `_VARIANT_RE`, prima del blocco pesi `W_ARTIST`):

```python
# Badge di formato per la UI (grid cell): primo match in ordine di priorità sui
# descrittori Discogs (lowercase, sostringa). Nessuna chiamata di rete aggiuntiva:
# il campo `format` e' gia' nella risposta di /database/search.
_FORMAT_BADGES = [
    ("ep", "EP"),
    ("lp", "LP"),
    ("album", "Album"),
    ("single", "Single"),
    ('12"', '12"'),
]


def _format_badge(formats: set[str]) -> str | None:
    for needle, badge in _FORMAT_BADGES:
        if any(needle in f for f in formats):
            return badge
    return None
```

Nella dataclass `DiscoveryLead`, aggiungi il campo dopo `want: int = 0`:

```python
    format_badge: str | None = None    # EP | LP | Album | Single | 12" | None
```

In `_lead_from_release`, passa `format_badge=_format_badge(formats)` al costruttore di `DiscoveryLead` (il set `formats` è già calcolato poche righe sopra per il filtro `_BAD_FORMATS`):

```python
    return DiscoveryLead(
        artist=artist, title=track_title,
        year=_parse_year(item.get("year")),
        label=_first(labels),
        style=_first(item.get("style")),
        source="discogs", seed=seed,
        discogs_id=item.get("id"),
        discogs_url=f"https://www.discogs.com{uri}" if uri.startswith("/") else (uri or None),
        thumb_url=item.get("cover_image") or item.get("thumb") or None,
        have=have, want=want,
        format_badge=_format_badge(formats),
    )
```

In `backend/app/schemas.py`, in `DiscoveryLeadOut` (dopo `reasons: list[ReasonOut] = []`):

```python
    discogs_id: int | None = None
    format_badge: str | None = None
```

In `backend/app/routers/discovery.py`, in `_lead_out`:

```python
def _lead_out(lead: DiscoveryLead) -> DiscoveryLeadOut:
    return DiscoveryLeadOut(
        artist=lead.artist, title=lead.title, year=lead.year, label=lead.label,
        style=lead.style, source=lead.source, seed=lead.seed,
        discogs_url=lead.discogs_url, thumb_url=lead.thumb_url,
        have=lead.have, want=lead.want,
        reasons=[ReasonOut(code=r.code, data=r.data) for r in lead.reasons],
        discogs_id=lead.discogs_id, format_badge=lead.format_badge,
    )
```

- [ ] **Step 4: Esegui i test e verifica che passino**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_discovery.py -v`
Expected: PASS (tutto il file, inclusi i test dig preesistenti)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/discovery_dig.py backend/app/schemas.py backend/app/routers/discovery.py backend/tests/test_discovery.py
git commit -m "feat(discovery): esponi discogs_id e format_badge sui lead del dig"
```

---

### Task 3: `GET /api/discovery/release/{discogs_id}`

**Files:**
- Modify: `backend/app/schemas.py`
- Modify: `backend/app/routers/discovery.py`
- Test: `backend/tests/test_discovery.py`

**Interfaces:**
- Consumes: `DiscogsClient.get_release(id)` (Task 1); `DiscogsError` (`app.integrations.discogs`).
- Produces: schema `DiscogsTrackOut{position: str, title: str, duration_seconds: int | None}`; schema `DiscogsReleaseOut{discogs_id: int, title: str, artist: str, thumb_url: str | None, discogs_url: str | None, year: int | None, label: str | None, tracks: list[DiscogsTrackOut]}`; endpoint `GET /api/discovery/release/{discogs_id}` (router function `get_release_detail`). Consumato dal frontend in Task 7/9.

Nota di scope rispetto alla spec: `DiscogsReleaseOut` **non** include `format_badge`/`community` — quei dati il frontend li ha già dal lead che ha aperto il pannello (grid cell), niente da ricalcolare (i due endpoint Discogs hanno forme diverse: `/database/search` usa `format`/community piatti, `/releases/{id}` usa `formats`/`community` annidati — ricalcolare qui duplicherebbe logica senza motivo).

- [ ] **Step 1: Scrivi i test falliti**

In `backend/tests/test_discovery.py`, aggiungi:

```python
_RELEASE_DETAIL = {
    "id": 249504,
    "title": "Selected Ambient Works 85-92",
    "artists": [{"name": "Aphex Twin (2)"}],
    "year": 1992,
    "labels": [{"name": "Apollo"}],
    "images": [{"type": "primary", "uri": "http://img/cover.jpg"}],
    "tracklist": [
        {"position": "A1", "type_": "track", "title": "Xtal", "duration": "4:56"},
        {"position": "", "type_": "heading", "title": "Side B"},
        {"position": "B1", "type_": "track", "title": "Tha", "duration": "4:35"},
        {"position": "B2", "type_": "track", "title": "Untitled", "duration": ""},
    ],
    "uri": "https://www.discogs.com/release/249504-Aphex-Twin-Selected-Ambient-Works-85-92",
}


def test_release_detail_normalizes_tracklist(db, monkeypatch):
    from app.routers.discovery import get_release_detail

    monkeypatch.setattr(DiscogsClient, "get_release", lambda self, rid: _RELEASE_DETAIL)
    out = get_release_detail(249504)
    assert out.discogs_id == 249504
    assert out.title == "Selected Ambient Works 85-92"
    assert out.artist == "Aphex Twin"  # suffisso di disambiguazione Discogs "(2)" rimosso
    assert out.label == "Apollo"
    assert out.thumb_url == "http://img/cover.jpg"
    assert out.discogs_url == _RELEASE_DETAIL["uri"]
    # la voce "heading" (Side B) e' esclusa: non e' una traccia
    assert [t.title for t in out.tracks] == ["Xtal", "Tha", "Untitled"]
    assert out.tracks[0].duration_seconds == 296  # "4:56" -> 4*60+56
    assert out.tracks[2].duration_seconds is None  # durata vuota -> None


def test_release_detail_502_on_discogs_error(monkeypatch):
    from fastapi import HTTPException
    from app.routers.discovery import get_release_detail

    def _raise(self, rid):
        raise DiscogsError("Discogs 500: boom")
    monkeypatch.setattr(DiscogsClient, "get_release", _raise)
    with pytest.raises(HTTPException) as exc_info:
        get_release_detail(249504)
    assert exc_info.value.status_code == 502
```

Aggiungi `import pytest` in cima a `test_discovery.py` se non già presente, e `from app.integrations.discogs import DiscogsClient, DiscogsError` (se `DiscogsError` non è già importato dal Task 2).

- [ ] **Step 2: Esegui i test e verifica che falliscano**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_discovery.py -k "release_detail" -v`
Expected: FAIL — `ImportError: cannot import name 'get_release_detail'`

- [ ] **Step 3: Implementa schemi + endpoint**

In `backend/app/schemas.py`, dopo `DiscoveryGenresOut`:

```python
class DiscogsTrackOut(BaseModel):
    position: str
    title: str
    duration_seconds: int | None = None


class DiscogsReleaseOut(BaseModel):
    discogs_id: int
    title: str
    artist: str
    thumb_url: str | None = None
    discogs_url: str | None = None
    year: int | None = None
    label: str | None = None
    tracks: list[DiscogsTrackOut] = []
```

In `backend/app/routers/discovery.py`:

1. Estendi l'import da `app.integrations.discogs`:

```python
from app.integrations.discogs import DiscogsClient, DiscogsError
```

2. Estendi l'import da `app.schemas` aggiungendo `DiscogsReleaseOut`, `DiscogsTrackOut`.

3. Aggiungi in testa al file, vicino a `_CURATED_STYLES`, la regex di pulizia artista e il parser durata:

```python
# Discogs disambigua artisti omonimi con un suffisso numerico ("Aphex Twin (2)"):
# rumore per la UI, va tolto.
_ARTIST_SUFFIX_RE = re.compile(r"\s*\(\d+\)\s*$")


def _clean_artist_name(name: str) -> str:
    return _ARTIST_SUFFIX_RE.sub("", name).strip()


def _parse_duration(value: str | None) -> int | None:
    """'mm:ss' -> secondi. Vuota o non parsabile -> None (il ranking Soulseek
    tratta l'ignoto come neutro, mai penalizzato)."""
    if not value:
        return None
    parts = value.strip().split(":")
    if len(parts) != 2:
        return None
    try:
        minutes, seconds = int(parts[0]), int(parts[1])
    except ValueError:
        return None
    return minutes * 60 + seconds
```

Aggiungi `import re` in cima al file se non già presente (verifica: `discovery_dig.py` lo importa, `routers/discovery.py` potrebbe non averlo — controlla e aggiungilo se manca).

4. Aggiungi l'endpoint, dopo `dig_endpoint`:

```python
@router.get("/release/{discogs_id}", response_model=DiscogsReleaseOut)
def get_release_detail(discogs_id: int):
    """Dettaglio di un disco del dig: tracklist reale, fetch lazy all'apertura
    del pannello (mai in batch per tutta la griglia)."""
    client = DiscogsClient()
    try:
        payload = client.get_release(discogs_id)
    except DiscogsError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    names = [a.get("name", "") for a in (payload.get("artists") or []) if a.get("name")]
    artist = _clean_artist_name(", ".join(names)) if names else "Sconosciuto"
    labels = payload.get("labels") or []
    images = payload.get("images") or []
    uri = payload.get("uri") or ""

    tracks = [
        DiscogsTrackOut(
            position=item.get("position") or "",
            title=item.get("title") or "",
            duration_seconds=_parse_duration(item.get("duration")),
        )
        for item in (payload.get("tracklist") or [])
        if item.get("type_") == "track"
    ]

    return DiscogsReleaseOut(
        discogs_id=discogs_id,
        title=payload.get("title") or "",
        artist=artist,
        thumb_url=images[0]["uri"] if images else None,
        discogs_url=f"https://www.discogs.com{uri}" if uri.startswith("/") else (uri or None),
        year=payload.get("year"),
        label=labels[0]["name"] if labels else None,
        tracks=tracks,
    )
```

- [ ] **Step 4: Esegui i test e verifica che passino**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_discovery.py -v`
Expected: PASS (tutto il file)

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas.py backend/app/routers/discovery.py backend/tests/test_discovery.py
git commit -m "feat(discovery): endpoint GET /api/discovery/release/{id} con tracklist reale"
```

---

### Task 4: Playlist di sistema "Scoperte"

**Files:**
- Modify: `backend/app/services/playlist_import.py`
- Test: `backend/tests/test_discovery.py`

**Interfaces:**
- Produces: `get_or_create_discovery_playlist(db: Session) -> Playlist` — idempotente, `Playlist(platform="manual", name="Scoperte", kind="discovery")`. Consumato da Task 5.

- [ ] **Step 1: Scrivi il test fallito**

In `backend/tests/test_discovery.py`:

```python
def test_get_or_create_discovery_playlist_is_idempotent(db):
    from app.services.playlist_import import get_or_create_discovery_playlist

    p1 = get_or_create_discovery_playlist(db)
    db.commit()
    p2 = get_or_create_discovery_playlist(db)
    assert p1.id == p2.id
    assert p1.name == "Scoperte"
    assert p1.kind == "discovery"
    assert p1.platform == "manual"
```

- [ ] **Step 2: Esegui il test e verifica che fallisca**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_discovery.py -k discovery_playlist_is_idempotent -v`
Expected: FAIL — `ImportError: cannot import name 'get_or_create_discovery_playlist'`

- [ ] **Step 3: Implementa l'helper**

In `backend/app/services/playlist_import.py`, dopo `_liked_playlist` (che segue lo stesso pattern "singleton per `kind`"):

```python
DISCOVERY_PLAYLIST_NAME = "Scoperte"


def get_or_create_discovery_playlist(db: Session) -> Playlist:
    """La playlist di sistema per le tracce 'per dopo' del dig Discovery.

    Ne esiste al più una (kind='discovery'), creata al primo uso — stesso
    pattern di _liked_playlist, ma qui va anche creata se assente (i liked
    nascono dall'import Spotify, 'Scoperte' nasce dal primo 'per dopo').
    """
    playlist = db.scalar(
        select(Playlist).where(Playlist.platform == "manual", Playlist.kind == "discovery")
    )
    if playlist is None:
        playlist = Playlist(platform="manual", name=DISCOVERY_PLAYLIST_NAME, kind="discovery")
        db.add(playlist)
        db.flush()
    return playlist
```

- [ ] **Step 4: Esegui il test e verifica che passi**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_discovery.py -v`
Expected: PASS (tutto il file)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/playlist_import.py backend/tests/test_discovery.py
git commit -m "feat(discovery): playlist di sistema Scoperte per il per-dopo del dig"
```

---

### Task 5: `POST /api/discovery/save-for-later`

**Files:**
- Modify: `backend/app/schemas.py`
- Modify: `backend/app/routers/discovery.py`
- Test: `backend/tests/test_discovery.py`

**Interfaces:**
- Consumes: `import_single_track` (`app.services.playlist_import`, già importato altrove nel router); `get_or_create_discovery_playlist` (Task 4); `add_track_to_playlist` (`app.repositories`, verifica se già importato nel router — se no aggiungilo).
- Produces: schema `DiscoverySaveForLaterRequest{artist: str, title: str, duration_seconds: int | None, album_art_url: str | None, url: str | None}`; schema `DiscoverySaveForLaterResponse{created: bool, track: TrackOut}`; endpoint `POST /api/discovery/save-for-later` (router function `save_for_later`). Consumato dal frontend in Task 7/9.

- [ ] **Step 1: Scrivi i test falliti**

In `backend/tests/test_discovery.py`:

```python
def test_save_for_later_imports_and_adds_to_discovery_playlist(db):
    from app.routers.discovery import save_for_later
    from app.schemas import DiscoverySaveForLaterRequest
    from app.services.playlist_import import get_or_create_discovery_playlist
    from app.repositories import tracks_for_playlist

    resp = save_for_later(DiscoverySaveForLaterRequest(
        artist="Voiron", title="Night Signal", duration_seconds=320,
    ), db)
    assert resp.created is True
    assert resp.track.title == "Night Signal"

    playlist = get_or_create_discovery_playlist(db)
    tracks = tracks_for_playlist(db, playlist.id)
    assert [t.title for t in tracks] == ["Night Signal"]

    # idempotente: stessa traccia (match per nome, niente ISRC/platform_track_id),
    # nessuna membership duplicata
    save_for_later(DiscoverySaveForLaterRequest(artist="Voiron", title="Night Signal"), db)
    assert len(tracks_for_playlist(db, playlist.id)) == 1
```

- [ ] **Step 2: Esegui il test e verifica che fallisca**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_discovery.py -k save_for_later -v`
Expected: FAIL — `ImportError: cannot import name 'save_for_later'`

- [ ] **Step 3: Implementa schema + endpoint**

In `backend/app/schemas.py`, dopo `DiscogsReleaseOut` (Task 3):

```python
class DiscoverySaveForLaterRequest(BaseModel):
    """Una traccia della tracklist di un disco, segnata 'per dopo'."""

    artist: str
    title: str
    duration_seconds: int | None = None
    album_art_url: str | None = None
    url: str | None = None


class DiscoverySaveForLaterResponse(BaseModel):
    created: bool
    track: TrackOut
```

In `backend/app/routers/discovery.py`:

1. Estendi l'import da `app.schemas` aggiungendo `DiscoverySaveForLaterRequest`, `DiscoverySaveForLaterResponse`.
2. Estendi l'import da `app.services.playlist_import`: `from app.services.playlist_import import get_or_create_discovery_playlist, import_single_track`.
3. Aggiungi `from app.repositories import add_track_to_playlist` (nuovo import; verifica che non sia già presente sotto altro nome).
4. Aggiungi l'endpoint, dopo `add_to_library`:

```python
@router.post("/save-for-later", response_model=DiscoverySaveForLaterResponse)
def save_for_later(req: DiscoverySaveForLaterRequest, db: Session = Depends(get_db)):
    """Importa una traccia della tracklist e la mette nella playlist di sistema
    'Scoperte'. Nessun download: solo per-dopo."""
    track, created = import_single_track(
        db, platform="manual", title=req.title, artist=req.artist,
        duration_seconds=req.duration_seconds, url=req.url, artwork_url=req.album_art_url,
    )
    playlist = get_or_create_discovery_playlist(db)
    add_track_to_playlist(db, track, playlist)
    db.commit()
    db.refresh(track)
    return DiscoverySaveForLaterResponse(created=created, track=track_out(track))
```

- [ ] **Step 4: Esegui i test e verifica che passino**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_discovery.py -v`
Expected: PASS (tutto il file)

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas.py backend/app/routers/discovery.py backend/tests/test_discovery.py
git commit -m "feat(discovery): endpoint save-for-later verso la playlist Scoperte"
```

---

### Task 6: Download immediato singola traccia (auto-pick)

**Files:**
- Modify: `backend/app/services/soulseek_download_job.py`
- Modify: `backend/app/routers/downloads.py`
- Test: `backend/tests/test_soulseek_download_job.py`
- Test: `backend/tests/test_downloads_router.py`

**Interfaces:**
- Produces: `start_track_autopick_job(track_id: int) -> dict` (job-starter, stesso pattern di `start_playlist_job`/`start_retry_job`: item `(track_id, None)` → `_process_item` fa la cascata di ricerca+auto-pick perché `chosen is None`); endpoint `POST /api/downloads/track/auto` (router function `download_track_auto`, schema `TrackAutopickIn{track_id: int}`). Consumato dal frontend in Task 7/9 per "Scarica ora".

- [ ] **Step 1: Scrivi il test fallito per il job-starter**

In `backend/tests/test_soulseek_download_job.py`, aggiungi in fondo al file:

```python
def test_start_track_autopick_job_builds_correct_items(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        job, "_start",
        lambda items, pid: captured.update(items=items, playlist_id=pid) or {"status": "running"},
    )
    job.start_track_autopick_job(42)
    assert captured["items"] == [(42, None)]
    assert captured["playlist_id"] is None
```

- [ ] **Step 2: Esegui il test e verifica che fallisca**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_soulseek_download_job.py -k autopick -v`
Expected: FAIL — `AttributeError: module 'app.services.soulseek_download_job' has no attribute 'start_track_autopick_job'`

- [ ] **Step 3: Implementa il job-starter**

In `backend/app/services/soulseek_download_job.py`, dopo `start_track_job`:

```python
def start_track_autopick_job(track_id: int) -> dict:
    """Auto-pick immediato per una singola traccia (es. 'Scarica ora' dalla
    tracklist di un lead Discovery): nessun candidato pre-scelto, stessa
    cascata di ricerca usata da start_playlist_job/start_retry_job."""
    return _start([(track_id, None)], None)
```

- [ ] **Step 4: Esegui il test del job-starter e verifica che passi**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_soulseek_download_job.py -v`
Expected: PASS (tutto il file)

- [ ] **Step 5: Scrivi i test falliti per l'endpoint**

In `backend/tests/test_downloads_router.py`, aggiungi in cima al file (dopo gli import esistenti) l'helper di engine per i test che toccano il DB — stesso pattern di `backend/tests/test_download_pending.py`:

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base


def _engine():
    e = create_engine("sqlite://", connect_args={"check_same_thread": False},
                      poolclass=StaticPool)
    Base.metadata.create_all(e)
    return e, sessionmaker(bind=e, expire_on_commit=False)
```

E in fondo al file:

```python
def test_track_auto_starts_autopick_job(monkeypatch):
    from app.routers import downloads as downloads_router
    from app.services import soulseek_download_job as job
    from app.models import Track

    engine, factory = _engine()
    db = factory()
    t = Track(source_type="manual", title="Night Signal", artist="Voiron")
    db.add(t)
    db.commit()

    monkeypatch.setattr(downloads_router, "slskd_configured", lambda: True)
    monkeypatch.setattr(downloads_router, "SessionLocal", factory)
    monkeypatch.setattr(job, "is_running", lambda: False)
    started = []
    monkeypatch.setattr(job, "_start", lambda items, pid: started.append(items) or {"status": "running"})

    r = client.post("/api/downloads/track/auto", json={"track_id": t.id})
    assert r.status_code == 202
    assert started == [[(t.id, None)]]


def test_track_auto_404_when_track_missing(monkeypatch):
    from app.routers import downloads as downloads_router
    from app.services import soulseek_download_job as job

    _, factory = _engine()
    monkeypatch.setattr(downloads_router, "slskd_configured", lambda: True)
    monkeypatch.setattr(downloads_router, "SessionLocal", factory)
    monkeypatch.setattr(job, "is_running", lambda: False)

    r = client.post("/api/downloads/track/auto", json={"track_id": 999})
    assert r.status_code == 404


def test_track_auto_409_when_not_configured(monkeypatch):
    from app.routers import downloads as downloads_router
    monkeypatch.setattr(downloads_router, "slskd_configured", lambda: False)
    r = client.post("/api/downloads/track/auto", json={"track_id": 1})
    assert r.status_code == 409
```

- [ ] **Step 6: Esegui i test e verifica che falliscano**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_downloads_router.py -k track_auto -v`
Expected: FAIL — 404 (route non esiste ancora) invece di 202/404/409 attesi

- [ ] **Step 7: Implementa l'endpoint**

In `backend/app/routers/downloads.py`:

1. Aggiungi lo schema, vicino a `TrackDownloadIn`:

```python
class TrackAutopickIn(BaseModel):
    track_id: int
```

2. Aggiungi l'endpoint, dopo `download_track`:

```python
@router.post("/track/auto", status_code=202)
def download_track_auto(req: TrackAutopickIn):
    """Download immediato in auto-pick di una singola traccia (es. 'Scarica
    ora' dalla tracklist di un lead Discovery): nessun candidato scelto
    dall'utente, stessa cascata di ricerca del job playlist."""
    if not slskd_configured():
        raise HTTPException(status_code=409, detail="slskd non configurato.")
    if job.is_running():
        raise HTTPException(status_code=409, detail="Un download e' gia' in corso.")
    db = SessionLocal()
    try:
        if get_track(db, req.track_id) is None:
            raise HTTPException(status_code=404, detail="Traccia non trovata.")
    finally:
        db.close()
    return {"available": True, **job.start_track_autopick_job(req.track_id)}
```

- [ ] **Step 8: Esegui i test e verifica che passino**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_downloads_router.py backend/tests/test_download_pending.py -v`
Expected: PASS (entrambi i file)

- [ ] **Step 9: Esegui l'intera suite backend**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests -v`
Expected: PASS (nessuna regressione sui task precedenti o sui test preesistenti)

- [ ] **Step 10: Commit**

```bash
git add backend/app/services/soulseek_download_job.py backend/app/routers/downloads.py backend/tests/test_soulseek_download_job.py backend/tests/test_downloads_router.py
git commit -m "feat(downloads): download immediato auto-pick di una singola traccia"
```

---

### Task 7: Client API frontend

**Files:**
- Modify: `frontend/lib/api.ts`

**Interfaces:**
- Consumes: endpoint dei Task 2, 3, 5, 6.
- Produces: `DiscoveryLead.discogs_id: number | null`, `DiscoveryLead.format_badge: string | null` (campi aggiunti); tipi `DiscogsTrack`, `DiscogsRelease`; funzioni `getDiscogsRelease(discogsId: number)`, `discoveryImportTrack(input: DiscoveryImportInput)`, `discoverySaveForLater(input: DiscoveryImportInput)`, `downloadTrackAuto(trackId: number)`. Consumato dai Task 9 (componenti griglia/pannello) e dalla riscrittura di `page.tsx`.

- [ ] **Step 1: Estendi l'interfaccia `DiscoveryLead`**

In `frontend/lib/api.ts`, nell'interfaccia `DiscoveryLead` esistente (blocco "Discovery v2: dig"), aggiungi due campi dopo `reasons: Reason[];`:

```typescript
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
  discogs_id: number | null;
  format_badge: string | null;
}
```

- [ ] **Step 2: Aggiungi i tipi `DiscogsTrack`/`DiscogsRelease` e le funzioni client**

Subito dopo la definizione di `discoveryDig` (che ritorna `DiscoveryDigResponse`), aggiungi:

```typescript
export interface DiscogsTrack {
  position: string;
  title: string;
  duration_seconds: number | null;
}

export interface DiscogsRelease {
  discogs_id: number;
  title: string;
  artist: string;
  thumb_url: string | null;
  discogs_url: string | null;
  year: number | null;
  label: string | null;
  tracks: DiscogsTrack[];
}

export function getDiscogsRelease(discogsId: number) {
  return apiGet<DiscogsRelease>(`/api/discovery/release/${discogsId}`);
}

export interface DiscoveryImportInput {
  artist: string;
  title: string;
  duration_seconds?: number | null;
  album_art_url?: string | null;
  url?: string | null;
}

export function discoveryImportTrack(input: DiscoveryImportInput) {
  return apiPost<DiscoveryAddResponse>("/api/discovery/add", input);
}

export function discoverySaveForLater(input: DiscoveryImportInput) {
  return apiPost<DiscoveryAddResponse>("/api/discovery/save-for-later", input);
}

export function downloadTrackAuto(trackId: number) {
  return apiPost<DownloadStatus>("/api/downloads/track/auto", { track_id: trackId });
}
```

- [ ] **Step 3: Rimuovi `discoveryAddLead`**

La funzione `discoveryAddLead(lead: DiscoveryLead)` (che postava `{artist, title, album_art_url: lead.thumb_url}` su `/api/discovery/add`) va **rimossa**: i suoi due soli chiamanti sono dentro `LeadRow`, che il Task 9 elimina. `discoveryImportTrack` la sostituisce con un input esplicito (non più legato a un intero `DiscoveryLead`, ma alla singola traccia della tracklist).

- [ ] **Step 4: Verifica i tipi**

Run: `cd frontend && npm run lint`
Expected: nessun errore sui file toccati (ci saranno errori/warning su `frontend/app/discovery/page.tsx` per `discoveryAddLead` non più esportata — sono attesi e si risolvono nel Task 9; se il linter segnala errori in ALTRI file, correggili prima di procedere)

- [ ] **Step 5: Commit**

```bash
git add frontend/lib/api.ts
git commit -m "feat(discovery): client API per tracklist, save-for-later e download auto"
```

---

### Task 8: Stato del dig in query string

**Files:**
- Modify: `frontend/app/discovery/page.tsx`

**Interfaces:**
- Consumes: `next/navigation` (`useRouter`, `useSearchParams`, `usePathname`) — verificato contro `frontend/node_modules/next/dist/docs/01-app/03-api-reference/04-functions/use-search-params.md`.
- Produces: nessuna nuova interfaccia esterna — questo task cambia solo il ciclo di vita interno del form (seed/valore/adventurousness/riferimento gusto), la resa dei risultati resta quella attuale (`LeadResults`/`LeadRow`) fino al Task 9.

- [ ] **Step 1: Leggi la guida Next.js locale prima di modificare**

`frontend/CLAUDE.md` impone di leggere `node_modules/next/dist/docs/` prima di toccare routing/pagine. Il pattern di lettura query param già in uso in questo repo (`frontend/app/library/page.tsx`, righe 1-35: `useSearchParams` + wrapper `<Suspense>`) è coerente con la documentazione ufficiale della v16 — replicalo per scrittura+lettura.

- [ ] **Step 2: Avvolgi il componente in Suspense e leggi i param all'avvio**

In `frontend/app/discovery/page.tsx`, rinomina il componente esportato in `DiscoveryInner` (non più `export default`) e aggiungi in fondo al file il wrapper:

```tsx
export default function DiscoveryPage() {
  return (
    <Suspense>
      <DiscoveryInner />
    </Suspense>
  );
}
```

Aggiungi `Suspense` all'import di `react` in cima al file:

```tsx
import { Suspense, useCallback, useEffect, useState } from "react";
```

(sostituisce `import { useEffect, useState } from "react";`)

Aggiungi l'import di navigazione:

```tsx
import { usePathname, useRouter, useSearchParams } from "next/navigation";
```

Dentro `DiscoveryInner`, subito dopo la riga `const jobs = useJobs();`, leggi i param e inizializza lo stato del form da essi invece che dai valori fissi attuali:

```tsx
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const initialSeed = (searchParams.get("seed") === "label" ? "label" : "genre") as DigSeed;
  const initialValue = searchParams.get("value") ?? "";
  const initialAdv = Number(searchParams.get("adv") ?? "0.45");
  const initialTaste = searchParams.get("taste");
```

- [ ] **Step 3: Sostituisci i valori iniziali di `useState` con quelli letti dai param**

Sostituisci le righe esistenti:

```tsx
  const [digSeed, setDigSeed] = useState<DigSeed>("genre");
```

con:

```tsx
  const [digSeed, setDigSeed] = useState<DigSeed>(initialSeed);
```

e:

```tsx
  const [adventurousness, setAdventurousness] = useState(0.45);
  const [tasteRef, setTasteRef] = useState<number | null>(null); // null = tutta la libreria
```

con:

```tsx
  const [adventurousness, setAdventurousness] = useState(
    Number.isFinite(initialAdv) ? Math.min(1, Math.max(0, initialAdv)) : 0.45,
  );
  const [tasteRef, setTasteRef] = useState<number | null>(initialTaste ? Number(initialTaste) : null);
```

Per `genre`, la riga esistente nell'`useEffect` di caricamento (`setGenre(g.library[0] ?? g.styles[0] ?? "")`) va condizionata: se `initialValue` è già valorizzato (arrivo da URL bookmarkata) non va sovrascritto col primo genere di libreria. Sostituisci quell'`useEffect` (il blocco `getDiscoveryGenres().then(...)`) con:

```tsx
    getDiscoveryGenres()
      .then((g) => {
        setGenres(g);
        if (!initialValue) setGenre(g.library[0] ?? g.styles[0] ?? "");
      })
      .catch(() => setGenres({ library: [], styles: [] }));
```

E per `label`, la selezione iniziale (`if (ls.length) setSelectedLabel(ls[0].label);`) va condizionata allo stesso modo — sostituisci con:

```tsx
    getLabels()
      .then((ls) => {
        setLabels(ls);
        if (!initialValue && ls.length) setSelectedLabel(ls[0].label);
      })
      .catch(() => setLabels([]));
```

Infine, inizializza `genre`/`selectedLabel` da `initialValue` in base al seme: sostituisci

```tsx
  const [genre, setGenre] = useState<string>("");
```

con

```tsx
  const [genre, setGenre] = useState<string>(initialSeed === "genre" ? initialValue : "");
```

e

```tsx
  const [selectedLabel, setSelectedLabel] = useState<string>("");
```

con

```tsx
  const [selectedLabel, setSelectedLabel] = useState<string>(initialSeed === "label" ? initialValue : "");
```

- [ ] **Step 4: Scrivi l'URL e ri-lancia il dig quando cambia**

Sostituisci la funzione `runDig` esistente in modo che, oltre a lanciare la ricerca, aggiorni la query string (usando `router.push`, così back/forward del browser passano tra i dig precedenti):

```tsx
  const runDig = async () => {
    const value = digSeed === "genre" ? genre.trim() : selectedLabel;
    if (!value) return;
    const params = new URLSearchParams();
    params.set("seed", digSeed);
    params.set("value", value);
    params.set("adv", String(adventurousness));
    if (tasteRef != null) params.set("taste", String(tasteRef));
    router.push(`${pathname}?${params.toString()}`, { scroll: false });
    setBusy(true);
    setError(null);
    setDig(null);
    jobs.startClientJob("dig", "Crate digging");
    jobs.updateClientJob("dig", { detail: `Discogs · ${value}` });
    try {
      setDig(await discoveryDig(digSeed, value, { adventurousness, tastePlaylistId: tasteRef }));
    } catch (e) {
      setError(err(e));
    } finally {
      setBusy(false);
      jobs.endClientJob("dig");
    }
  };
```

- [ ] **Step 5: Auto-lancia il dig se la pagina si apre già con i parametri in query string**

Aggiungi un nuovo `useEffect`, dopo quello esistente che carica playlist/generi/etichette (che gira una sola volta al mount, `[]`):

```tsx
  useEffect(() => {
    // Arrivo su un link bookmarkato/back-forward con un dig già specificato
    // (vale per entrambi i semi: initialValue è il genere o l'etichetta a
    // seconda di initialSeed): ri-lancia la stessa ricerca deterministica,
    // nessuna cache da invalidare.
    if (initialValue) runDig();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
```

- [ ] **Step 6: Verifica manuale in browser**

Run: `cd frontend && npm run dev` (o riusa il dev server già attivo)

Apri `http://localhost:3000/discovery?seed=genre&value=Acid%20House&adv=0.85`: il picker deve mostrare "Genere" attivo, il campo genere precompilato con "Acid House", il preset "Avventuroso" attivo, e il dig deve partire da solo. Premi "DIG" con un valore diverso: l'URL nella barra degli indirizzi deve aggiornarsi. Premi "Indietro" nel browser: l'URL torna al dig precedente (il dig si ri-lancia automaticamente perché `initialValue` cambia — se non si ri-lancia, verifica che `initialValue` derivi da `searchParams` reattivamente, non da uno snapshot preso solo al primo render).

- [ ] **Step 7: Lint**

Run: `cd frontend && npm run lint`
Expected: nessun errore nuovo sui file toccati

- [ ] **Step 8: Commit**

```bash
git add frontend/app/discovery/page.tsx
git commit -m "feat(discovery): stato del dig in query string, bookmarkabile"
```

---

### Task 9: Griglia "cassa di dischi" + pannello tracklist

**Files:**
- Create: `frontend/components/discovery-lead-grid.tsx`
- Create: `frontend/components/discovery-tracklist-panel.tsx`
- Modify: `frontend/app/discovery/page.tsx`

**Interfaces:**
- Consumes: `DiscoveryLead` (con `discogs_id`/`format_badge`, Task 7), `getDiscogsRelease`, `discoveryImportTrack`, `discoverySaveForLater`, `downloadTrackAuto`, `DiscogsRelease`, `DiscogsTrack` (Task 7); componenti `Modal`, `Alert`, `Button`, `Spinner` (`frontend/components/ui.tsx`, invariati).
- Produces: `DiscoveryLeadGrid({ dig: DiscoveryDigResponse })` — componente esportato, usato da `page.tsx` al posto di `LeadResults`. Riproduce anche il caso "zero lead" con lo stesso `EmptyState` contestuale che aveva `LeadResults`.

- [ ] **Step 1: Crea il pannello tracklist**

Crea `frontend/components/discovery-tracklist-panel.tsx`:

```tsx
"use client";

import { useEffect, useState } from "react";
import { Check, Disc3, Download, ExternalLink } from "lucide-react";
import {
  discoveryImportTrack, discoverySaveForLater, downloadTrackAuto, fmtDuration, getDiscogsRelease,
  type DiscogsRelease, type DiscoveryLead,
} from "@/lib/api";
import { Alert, Button, Modal, Spinner } from "@/components/ui";

function err(e: unknown): string {
  return String((e as { message?: string })?.message ?? e);
}

type PanelTrack = { position: string; title: string; duration_seconds: number | null };

export function DiscoveryTracklistPanel({ lead, onClose }: {
  lead: DiscoveryLead | null;
  onClose: () => void;
}) {
  const [release, setRelease] = useState<DiscogsRelease | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!lead?.discogs_id) {
      setRelease(null);
      return;
    }
    setLoading(true);
    setError(null);
    setRelease(null);
    getDiscogsRelease(lead.discogs_id)
      .then(setRelease)
      .catch((e) => setError(err(e)))
      .finally(() => setLoading(false));
  }, [lead?.discogs_id]);

  const tracks: PanelTrack[] = release
    ? release.tracks.length
      ? release.tracks
      : [{ position: "", title: release.title, duration_seconds: null }]
    : [];

  return (
    <Modal
      open={lead !== null}
      onClose={onClose}
      title={lead ? `${lead.artist} — ${lead.title}` : undefined}
      size="lg"
    >
      {error && <Alert tone="danger">⚠ {error}</Alert>}
      {loading && (
        <p className="flex items-center gap-2 py-6 text-sm text-muted">
          <Spinner /> Carico la tracklist…
        </p>
      )}
      {release && (
        <div>
          <div className="mb-3 flex items-center justify-between gap-3 border-b border-border pb-3">
            <div className="flex min-w-0 items-center gap-2 text-xs text-faint">
              {release.thumb_url ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={release.thumb_url} alt="" className="h-10 w-10 shrink-0 border border-border object-cover" />
              ) : (
                <div className="grid h-10 w-10 shrink-0 place-items-center border border-border bg-elevated text-faint">
                  <Disc3 size={16} />
                </div>
              )}
              <div className="min-w-0">
                {release.label && <span className="truncate">{release.label}</span>}
                {release.year != null && <span> · {release.year}</span>}
                {release.discogs_url && (
                  <a
                    href={release.discogs_url}
                    target="_blank"
                    rel="noreferrer"
                    className="ml-2 inline-flex items-center gap-1 text-fg hover:underline"
                  >
                    <ExternalLink size={12} /> Discogs
                  </a>
                )}
              </div>
            </div>
            <SaveAllButton release={release} tracks={tracks} />
          </div>
          <ul className="divide-y divide-border">
            {tracks.map((t, i) => (
              <TrackRow key={`${t.position}-${t.title}-${i}`} release={release} track={t} />
            ))}
          </ul>
        </div>
      )}
    </Modal>
  );
}

function SaveAllButton({ release, tracks }: { release: DiscogsRelease; tracks: PanelTrack[] }) {
  const [saving, setSaving] = useState(false);
  const [done, setDone] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const saveAll = async () => {
    setSaving(true);
    setSaveError(null);
    try {
      for (const t of tracks) {
        await discoverySaveForLater({
          artist: release.artist, title: t.title, duration_seconds: t.duration_seconds,
          album_art_url: release.thumb_url, url: release.discogs_url,
        });
      }
      setDone(true);
    } catch (e) {
      setSaveError(err(e));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="shrink-0 text-right">
      <Button size="sm" variant={done ? "ghost" : "outline"} onClick={saveAll} disabled={saving || done}>
        {done ? <><Check size={14} /> Tutte salvate</> : saving ? <Spinner /> : "Tutte per dopo"}
      </Button>
      {saveError && <p className="mt-1 text-xs text-danger">⚠ {saveError}</p>}
    </div>
  );
}

function TrackRow({ release, track }: { release: DiscogsRelease; track: PanelTrack }) {
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [downloaded, setDownloaded] = useState(false);
  const [rowError, setRowError] = useState<string | null>(null);

  const input = {
    artist: release.artist, title: track.title, duration_seconds: track.duration_seconds,
    album_art_url: release.thumb_url, url: release.discogs_url,
  };

  const saveForLater = async () => {
    setSaving(true);
    setRowError(null);
    try {
      await discoverySaveForLater(input);
      setSaved(true);
    } catch (e) {
      setRowError(err(e));
    } finally {
      setSaving(false);
    }
  };

  const downloadNow = async () => {
    setDownloading(true);
    setRowError(null);
    try {
      const { track: imported } = await discoveryImportTrack(input);
      await downloadTrackAuto(imported.id);
      setDownloaded(true);
    } catch (e) {
      setRowError(err(e));
    } finally {
      setDownloading(false);
    }
  };

  return (
    <li className="flex items-center justify-between gap-3 py-2">
      <div className="min-w-0">
        <div className="truncate text-sm text-fg">
          {track.position && <span className="tnum text-faint">{track.position} · </span>}
          {track.title}
        </div>
        <div className="tnum text-xs text-faint">{fmtDuration(track.duration_seconds)}</div>
        {rowError && <p className="mt-0.5 text-xs text-danger">⚠ {rowError}</p>}
      </div>
      <div className="flex shrink-0 items-center gap-1.5">
        <Button size="sm" variant={saved ? "ghost" : "outline"} onClick={saveForLater} disabled={saving || saved}>
          {saved ? <Check size={14} /> : saving ? <Spinner /> : "Per dopo"}
        </Button>
        <Button size="sm" variant={downloaded ? "ghost" : "outline"} onClick={downloadNow} disabled={downloading || downloaded}>
          {downloaded ? <><Check size={14} /> In coda</> : downloading ? <Spinner /> : <><Download size={13} /> Scarica ora</>}
        </Button>
      </div>
    </li>
  );
}
```

- [ ] **Step 2: Crea la griglia**

Crea `frontend/components/discovery-lead-grid.tsx`:

```tsx
"use client";

import { useMemo, useState } from "react";
import { Disc3 } from "lucide-react";
import { type DiscoveryDigResponse, type DiscoveryLead, type Reason } from "@/lib/api";
import { cn } from "@/lib/cn";
import { EmptyState } from "@/components/ui";
import { DiscoveryTracklistPanel } from "@/components/discovery-tracklist-panel";

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

const FORMAT_FILTERS = ["Tutti", "LP", "EP", "12\"", "Album", "Single"] as const;
type FormatFilter = (typeof FORMAT_FILTERS)[number];
type SortMode = "score" | "recent";
const SORT_OPTIONS: [SortMode, string][] = [["score", "Punteggio"], ["recent", "Più recenti"]];

export function DiscoveryLeadGrid({ dig }: { dig: DiscoveryDigResponse }) {
  const [format, setFormat] = useState<FormatFilter>("Tutti");
  const [sort, setSort] = useState<SortMode>("score");
  const [openLead, setOpenLead] = useState<DiscoveryLead | null>(null);

  const filtered = useMemo(() => {
    const base = format === "Tutti" ? dig.leads : dig.leads.filter((l) => l.format_badge === format);
    if (sort === "score") return base;
    return [...base].sort((a, b) => (b.year ?? 0) - (a.year ?? 0));
  }, [dig.leads, format, sort]);

  if (dig.leads.length === 0) {
    return (
      <EmptyState icon={<Disc3 size={28} />} title="Niente da scavare">
        Nessun brano nuovo per “{dig.value}”. Prova un altro {dig.seed_type === "label" ? "valore" : "stile"} o alza l’audacia.
      </EmptyState>
    );
  }

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap gap-1.5">
          {FORMAT_FILTERS.map((f) => (
            <button
              key={f}
              type="button"
              onClick={() => setFormat(f)}
              aria-pressed={format === f}
              className={cn(
                "rounded-none border px-2.5 py-1 text-xs transition-colors",
                format === f
                  ? "border-border-strong bg-elevated text-fg"
                  : "border-border bg-surface text-muted hover:border-border-strong hover:text-fg",
              )}
            >
              {f}
            </button>
          ))}
        </div>
        <div className="inline-flex rounded-none border border-border bg-surface p-0.5">
          {SORT_OPTIONS.map(([s, label]) => (
            <button
              key={s}
              type="button"
              onClick={() => setSort(s)}
              aria-pressed={sort === s}
              className={cn(
                "rounded-none px-2.5 py-1 text-xs font-medium transition-colors",
                sort === s ? "bg-elevated text-fg" : "text-muted hover:text-fg",
              )}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {filtered.length === 0 ? (
        <p className="py-8 text-center text-sm text-muted">Nessun disco con questo formato.</p>
      ) : (
        <div className="grid grid-cols-[repeat(auto-fill,minmax(120px,1fr))] gap-3">
          {filtered.map((l, i) => (
            <LeadCell key={`${l.discogs_id ?? l.artist}-${l.title}-${i}`} lead={l} onOpen={() => setOpenLead(l)} />
          ))}
        </div>
      )}

      <DiscoveryTracklistPanel lead={openLead} onClose={() => setOpenLead(null)} />
    </div>
  );
}

function LeadCell({ lead, onOpen }: { lead: DiscoveryLead; onOpen: () => void }) {
  return (
    <button
      type="button"
      onClick={onOpen}
      className="group relative flex flex-col gap-1.5 text-left outline-none focus-visible:ring-1 focus-visible:ring-fg"
    >
      <div className="relative aspect-square w-full overflow-hidden border border-border bg-elevated">
        {lead.thumb_url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={lead.thumb_url} alt="" className="h-full w-full object-cover" />
        ) : (
          <div className="grid h-full w-full place-items-center text-faint">
            <Disc3 size={22} />
          </div>
        )}
        {lead.format_badge && (
          <span className="absolute left-1 top-1 border border-border-strong bg-bg px-1 text-[9px] uppercase tracking-wide text-muted">
            {lead.format_badge}
          </span>
        )}
        <div className="pointer-events-none absolute inset-x-0 bottom-0 translate-y-full bg-bg/95 px-1.5 py-1 text-[10px] leading-tight text-muted opacity-0 transition-all duration-150 group-hover:translate-y-0 group-hover:opacity-100 group-focus-visible:translate-y-0 group-focus-visible:opacity-100">
          {lead.label && <div className="truncate">{lead.label}</div>}
          {lead.year != null && <div>{lead.year}</div>}
          {lead.reasons[0] && <div className="truncate text-faint">{reasonLabel(lead.reasons[0])}</div>}
        </div>
      </div>
      <div className="min-w-0">
        <div className="truncate text-xs font-medium text-fg">{lead.title}</div>
        <div className="truncate text-[11px] text-faint">{lead.artist}</div>
      </div>
    </button>
  );
}
```

- [ ] **Step 3: Collega la griglia in `page.tsx` e rimuovi il codice morto**

In `frontend/app/discovery/page.tsx`:

1. Aggiungi l'import: `import { DiscoveryLeadGrid } from "@/components/discovery-lead-grid";`

2. Sostituisci la riga `{dig && <LeadResults dig={dig} />}` con `{dig && <DiscoveryLeadGrid dig={dig} />}`.

3. **Rimuovi interamente**: la funzione `reasonLabel` (ora vive in `discovery-lead-grid.tsx`), la funzione `LeadResults`, la funzione `LeadRow` (tutto il blocco che include il vecchio modal di download `Modal open={dlOpen}...`), e la funzione `Chip` **solo se** non è più usata altrove nel file — verifica: `Chip` è usata anche dai picker genere/etichetta (`quickGenres.map((g) => <Chip .../>)` e `visibleLabels.map((l) => <Chip .../>)`), quindi **resta** — non rimuoverla.

4. Ripulisci gli import ora inutilizzati in testa al file. `Search` era usato SOLO dentro `LeadRow` (link "Spotify") e va rimosso; `Disc3` e `Tags` restano (usati dal picker seme/preset e dagli `EmptyState` di `DiscoveryInner`). Quindi da `lucide-react` l'import diventa:

```tsx
import { Disc3, Tags } from "lucide-react";
```

(rimuovi `ExternalLink, Plus, Check, Search, Download` — erano tutti usati solo dentro `LeadRow`/il vecchio modal; verifica comunque con una ricerca testuale nel file prima di toccare l'import, nel caso qualcuno sia referenziato altrove). Da `@/lib/api`, rimuovi `discoveryAddLead`, `downloadCandidates`, `downloadTrack`, `type DownloadCandidate`, `type DiscoveryLead`, `type Reason` (non più usati in questo file: `DiscoveryLeadGrid` ora prende l'intero `dig: DiscoveryDigResponse`, che resta importato — era già importato nel file originale — e `reasonLabel`/il suo tipo `Reason` si spostano in `discovery-lead-grid.tsx`). Da `@/components/ui`, `Card` e `Modal` erano usati SOLO dentro `LeadRow`/il vecchio modal di download — rimuovili entrambi dall'import (verifica comunque che `page.tsx` non li referenzi più altrove prima di toglierli).

- [ ] **Step 4: Verifica manuale in browser**

Run: `cd frontend && npm run dev` (o riusa il dev server già attivo), naviga su `/discovery`, lancia un DIG con un genere che sa di avere risultati.

Verifica:
- I risultati appaiono come griglia di copertine (non più lista), ogni cella con badge formato quando presente.
- Passando il mouse (o tabulando con la tastiera) su una cella appare la striscia con etichetta/anno/reason.
- Click (o Enter da tastiera) su una cella apre il pannello con la tracklist reale (titoli diversi dal titolo del lead, se il disco ha più tracce).
- "Per dopo" su una riga-traccia mostra "✓" e non è più cliccabile; "Scarica ora" idem con "In coda".
- "Tutte per dopo" segna tutte le righe.
- I chip di formato filtrano la griglia; l'ordinamento "Più recenti" la riordina per anno.
- Un disco senza tracklist valorizzata (verificabile forzando temporaneamente `tracklist: []` lato server per un test manuale, poi ripristinando) mostra comunque una riga di ripiego col titolo della release, non un pannello vuoto.

- [ ] **Step 5: Lint e build**

Run: `cd frontend && npm run lint`
Expected: nessun errore

Run: `cd frontend && npm run build`
Expected: build completata senza errori di tipo (il build Next.js include il type-check)

- [ ] **Step 6: Commit**

```bash
git add frontend/components/discovery-lead-grid.tsx frontend/components/discovery-tracklist-panel.tsx frontend/app/discovery/page.tsx
git commit -m "feat(discovery): griglia cassa di dischi + pannello tracklist per-traccia"
```

---

## Verifica finale

- [ ] **Suite backend completa**: `cd backend && source .venv/bin/activate && python -m pytest tests -v` → PASS, nessuna regressione.
- [ ] **Build frontend**: `cd frontend && npm run build` → PASS.
- [ ] **Percorso end-to-end manuale**: dal dev server, Discovery → Scava per genere → aprire un disco con più tracce → "Per dopo" su una traccia → verificare in Libreria/Playlist "Scoperte" che la traccia sia presente → "Scarica ora" su un'altra traccia → verificare che la barra job globale mostri il download in corso (link a `/downloads`).
