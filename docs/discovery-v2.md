# Discovery v2 — "Crate digging" (spec di lavoro)

> File temporaneo: rimuovere a implementazione conclusa (la sostanza confluisce in
> ARCHITECTURE/ROADMAP). Approvato dall'utente, in implementazione.

## Contesto

La Discovery oggi risolve ~20 candidati su Spotify (1 chiamata l'uno, cap dev-mode).
L'utente fa il DJ e gli serve **profondità nello stesso genere/etichetta**: tanti
brani da esplorare. Spotify dev-mode è limitato (search `label:` cap 10) e mainstream;
SoundCloud ha catalogo migliore ma API chiusa a nuove app. **Discogs** è aperto, gratis
(token alza il rate a 60/min) e profondissimo — verificato dal vivo:

- `labels/23528/releases` (Warp) → **8.451** release. `artists/45/releases` (Aphex
  Twin) → **1.311**. `database/search?style=...` → HTTP 200. Release detail → generi +
  **stili** + etichette + **tracklist**.

Discogs dà identità + metadati, NON audio/BPM: l'audio si risolve su Spotify solo
quando salvi.

## Obiettivi

1. Tre semi a scelta: **Playlist**, **Etichette**, **Generi**.
2. Output **lista-dig a volume**: tanti lead leggeri, risoluzione Spotify solo al salvataggio.
3. Ranking **profondità + novità** (deep cut), con cursore *familiare ↔ avventuroso*.
4. Profondità reale per Generi/Etichette via Discogs.

## Architettura

Separazione netta come oggi: **sorgente** (Discogs/Last.fm) ≠ **resolver identità**
(Spotify, solo al salvataggio). Due capacità:

- **dig** (nuovo, volume, Discogs): semi **Genere** ed **Etichetta** → lead non risolti.
- **expand** (esistente, curato, Last.fm→Spotify): seme **Playlist** → invariato.

### Backend

**`app/integrations/discogs.py`** — `DiscogsClient`:
- httpx con `User-Agent` obbligatorio; `token` opzionale da `settings.discogs_token`
  (header `Authorization: Discogs token=...`) per alzare il rate limit.
- `search_releases(*, style=None, genre=None, label=None, query=None, page=1, per_page=50) -> list[dict]`
  → `GET /database/search?type=release&...` con `sort` di default; ritorna `results`.
- `label_id(name) -> int | None` → `GET /database/search?type=label&q=name`, primo match.
- `releases_by_label_name(name, *, page, per_page)` → risolve id poi `GET /labels/{id}/releases`.
- Cache via `EnrichmentCache` (provider `discogs_v1`, lookup_key = query normalizzata),
  come gli altri provider. Errori → lista vuota + log (mai eccezione verso il router).

**`app/services/discovery_dig.py`** (nuovo, per non gonfiare `discovery.py`):
- `@dataclass DiscoveryLead`: `artist, title, year, label, style, source ("discogs"),
  seed, discogs_id, discogs_url, thumb_url, have, want, isrc=None, score=0.0`.
- `_lead_from_release(item, seed) -> DiscoveryLead | None`: lo split di `item["title"]`
  ("Artista - Titolo") in artist/title; `year`, `label`(primo), `style`(primo),
  `community.have/want`, `thumb`, `resource_url`→`discogs_url`. Scarta i "Various"/senza split.
- `dig(db, *, seed_type, value, search_fn, library=None, adventurousness=0.4, limit=80) -> DigResult`:
  - `seed_type` ∈ {`genre`, `label`}; `value` = stile/genere o nome etichetta.
  - Raccoglie release (1-2 pagine Discogs), costruisce lead, dedup vs libreria
    (`_key(artist,title)`) e tra lead.
  - **Ranking profondità+novità**: `score = on_target + novelty*adv + recency*(1-adv*0.5)`
    dove `novelty = 1 - clamp(have/HAVE_CAP)` (meno copie possedute nel mondo = più deep
    cut), `recency` da `year`, `on_target` base. `adventurousness∈[0,1]` pesa novità vs
    sicurezza. Ordina per score desc, taglia a `limit`.
  - Ritorna `DigResult(seed_type, value, leads)`.

### Schemi (`app/schemas.py`)

```python
class DiscoveryLeadOut(BaseModel):
    artist: str; title: str
    year: int | None = None
    label: str | None = None
    style: str | None = None
    source: str = "discogs"
    seed: str | None = None
    discogs_url: str | None = None
    thumb_url: str | None = None

class DiscoveryDigRequest(BaseModel):
    seed_type: Literal["genre", "label"]
    value: str
    adventurousness: float = Field(default=0.4, ge=0.0, le=1.0)
    limit: int = Field(default=80, ge=1, le=200)

class DiscoveryDigResponse(BaseModel):
    seed_type: str; value: str
    leads: list[DiscoveryLeadOut] = []

class DiscoveryGenresOut(BaseModel):
    library: list[str] = []     # generi presenti in libreria
    styles: list[str] = []      # stili curati (sottoinsieme Discogs, statico)
```

### Router (`app/routers/discovery.py`)

- `GET /api/discovery/genres` → generi libreria (da `Track.genre` distinti) + lista
  statica di stili curati.
- `POST /api/discovery/dig` → richiede Discogs configurato? No: funziona anche senza
  token (rate ridotto). Costruisce `DiscogsClient`, chiama `dig(...)`, ritorna lead.
- Salvataggio: riusa `POST /api/discovery/add` (import manuale per nome → enrichment
  completa identità/feature dopo). Nessuna chiamata Spotify per-lead nel dig.

### Frontend

- `lib/api.ts`: `DiscoveryLead`, `discoveryDig(seedType, value, opts)`, `getDiscoveryGenres()`.
- `app/discovery/page.tsx`: terza modalità **Generi** (+ Etichette può usare dig).
  - Selettore: per Generi, chip dai generi libreria + ricerca stile libera.
  - **Lista-dig**: righe leggere (artista — titolo · stile · etichetta · anno), link
    "apri su Discogs" + "cerca su Spotify" (URL costruiti, zero API), bottone "Salva"
    (riusa `discoveryAddToLibrary`).
  - **Slider** adventurousness (familiare ↔ avventuroso) passato a `discoveryDig`.
- Settings/status: riga **Discogs** (`DISCOGS_TOKEN`, opzionale) in `services/status`.

## Test

- `tests/test_discogs.py`: parsing release→lead, split "Artist - Title", cache,
  errori→[]; query costruite (style/label/q) con http fake.
- `tests/test_discovery_dig.py`: dedup vs libreria, ranking (deep cut sale con
  adventurousness alto; recente sale; on-target), troncamento a limit, "Various" scartati.

## Fuori scope (v2.0)

- Niente BPM/key da Discogs (resta enrichment). Niente preview audio in-app.
- Niente SoundCloud. Playlist-expand resta sul flusso attuale (unificazione futura).
- Tracklist per-release (espansione del singolo release in tracce) rimandata: i lead
  sono a granularità release (unità di digging normale).

## Bug collegato (fix separato, stesso ciclo)

`delete_playlist` fa hard-delete dei brani (`playlist_id ==`), e l'import sovrascrive
`Track.playlist_id` (FK singola) → cancellare una playlist cancella brani condivisi.
Fix v1 (sicurezza): `delete_playlist` **scollega** invece di cancellare. Fix v2
(modello many-to-many `playlist_tracks`) rimandato a design dedicato.
