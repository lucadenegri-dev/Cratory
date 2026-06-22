# Discovery con Etichette — Design & Implementation Spec

> Spec auto-contenuto (sopravvive alla compattazione del contesto). Implementa
> la direzione **C**: Radar Etichette (nuova sorgente) + segnale-etichetta sulla
> discovery da similarità, più la rimozione della "compatibilità tecnica" dalla
> discovery. Stato: **approvato dall'utente, da implementare.**

## 0. Contesto attuale (verificato nel codice)

Discovery oggi (`backend/app/services/discovery.py`, `routers/discovery.py`):
pipeline deterministica → seed (artisti/tracce playlist) → similarità **Last.fm**
→ dedup vs libreria → resolve via Spotify `/search` → rank per `match` →
spiegazione AI opzionale. Endpoint: `POST /api/discovery/expand`,
`POST /api/discovery/add`, `GET /api/discovery/status`.

- Il campo `compatibility` (in `DiscoveryCandidate`/`DiscoveryCandidateOut`) è
  semplicemente `round(match*100)` — **la similarità Last.fm, non una
  compatibilità tecnica** (BPM/key). La UI la mostra come "X% compat".
- `Track.label` esiste (backfill da copyright). I nomi possono essere verbosi
  (es. "Ridge Valley Digital under exclusive licence to Warp Records Limited").
- **Verificato**: Spotify `/search?q=label:"<label>"&type=track` funziona col
  token dev-mode (Warp/Kompakt/AD 93 → risultati reali).

## 1. Obiettivi

1. **Rimuovere la "compatibilità tecnica" dalla discovery.** La discovery serve
   ad aggiungere alla playlist altre tracce *di gusto affine*; la parte tecnica
   (BPM/key/transizioni) la fa il Set Builder a valle. → Eliminare il campo/badge
   `compatibility` (`% compat`) da API e UI. Il ranking interno resta per gusto
   (match Last.fm + risolvibilità per la similarità; affinità per le etichette).
2. **Radar Etichette (nuova sorgente).** Da una o più etichette (default: le top
   della libreria), trova su Spotify tracce di quelle label che non hai ancora.
3. **Segnale-etichetta sulla similarità.** Annota i candidati expand con la loro
   etichetta; badge + boost se è un'etichetta che già collezioni.
4. **Normalizzazione nomi etichetta** (`_clean_label`): nomi puliti per ricerca e
   per la pagina Etichette (merge delle varianti).

## 2. Backend

### 2.1 `app/services/labels.py` — normalizzazione

Aggiungere e usare `_clean_label`:

```python
import re

_LICENCE_RE = re.compile(r".*\bunder exclusive licen[cs]e to\s+", re.IGNORECASE)
_LEGAL_SUFFIX_RE = re.compile(
    r"[\s,]+(?:Limited|Ltd\.?|LLC|Inc\.?|GmbH|B\.?V\.?|S\.?r\.?l\.?|S\.?A\.?|Pty\.?\s*Ltd\.?|Co\.?)\s*$",
    re.IGNORECASE,
)

def _clean_label(raw: str | None) -> str | None:
    """Normalizza il nome etichetta da copyright verboso.

    - "X under exclusive licence to Y" -> Y (l'etichetta del master).
    - rimuove suffissi societari finali (Limited/Ltd/LLC/Inc/GmbH/...).
    """
    if not raw:
        return None
    s = raw.strip()
    s = _LICENCE_RE.sub("", s)          # tieni solo cio' dopo "under ... licence to"
    prev = None
    while prev != s:                    # strip ripetuto (es. "Records Limited Ltd")
        prev = s
        s = _LEGAL_SUFFIX_RE.sub("", s).strip()
    return s or None
```

- In `_label_from_copyrights`: ritorna `_clean_label(<estratto>)` (nuove
  derivazioni già pulite).
- In `labels_overview`: raggruppare per `_clean_label(t.label) or t.label`
  (merge varianti dello stesso label nella pagina Etichette, senza migrazione
  dati). La chiave del bucket usa il nome pulito.
- Nuova funzione riusabile per recuperare l'etichetta di un album (cache):
  ```python
  def album_label(db: Session, client, album_id: str) -> str | None:
      """Etichetta pulita di un album Spotify, con cache EnrichmentCache."""
      cached = _cached_album(db, album_id)
      if cached is not None:
          return _clean_label((cached.result_json or {}).get("label"))
      try:
          obj = client.get_album(album_id)
      except SpotifyError:
          return None
      label = obj.get("label") or _label_from_copyrights(obj.get("copyrights"))
      _cache_album_label(db, album_id, label)
      db.commit()
      return _clean_label(label)
  ```
  (`_label_from_copyrights` già applica `_clean_label`; doppia pulizia è
  idempotente.)

### 2.2 `app/integrations/spotify.py` — ricerca per etichetta

```python
def search_by_label(self, label: str, *, limit: int = 20) -> list[dict[str, Any]]:
    """Tracce di un'etichetta via filtro `label:` (funziona in dev mode)."""
    if not label:
        return []
    try:
        data = self._get("/search", params={"q": f'label:"{label}"', "type": "track", "limit": limit})
    except SpotifyError as exc:
        logger.warning("Spotify search_by_label(%r) fallito: %s", label, exc)
        return []
    return (data.get("tracks") or {}).get("items") or []
```

### 2.3 `app/services/discovery.py`

**Dataclass `DiscoveryCandidate`:** rimuovere `compatibility`; aggiungere:
```python
    album_id: str | None = None
    label: str | None = None
    label_owned: bool = False
```
Introdurre un punteggio interno di ordinamento `score: float = 0.0` (non esposto)
al posto di `compatibility`.

**Rimuovere compatibility dal ranking** (`_rank`): ordinare per
`(resolved, score, match)` desc, dove `score` = `match` per la similarità.
Non popolare più `compatibility`.

**Annotazione etichetta (similarità, Part 3.3):** dopo `_finalize`, per i
candidati risolti (con `album_id`):
```python
def _annotate_labels(candidates, album_label_fn, owned_labels: set[str]) -> None:
    for c in candidates:
        if not c.album_id:
            continue
        lbl = album_label_fn(c.album_id)   # già pulito
        if lbl:
            c.label = lbl
            c.label_owned = lbl.lower() in owned_labels
```
`owned_labels` = `{ _clean_label(t.label).lower() ... }` dalla libreria.
In `_resolve_all` salvare `c.album_id = (item.get("album") or {}).get("id")`.
Boost: ri-ordino finale stabile con `label_owned` come chiave prioritaria
(i candidati su etichette già collezionate salgono leggermente):
`candidates.sort(key=lambda c: (c.resolved, c.label_owned, c.score), reverse=True)`.

**Radar Etichette (nuova sorgente):**
```python
def discover_by_labels(
    db, *, labels: list[str], search_by_label, album_label_fn=None,
    library: list[Track] | None = None, limit: int = DEFAULT_LIMIT,
) -> DiscoveryResult:
    """Tracce non possedute dalle etichette date, ordinate per affinità di gusto."""
```
Logica:
- `library` = tutte le tracce; `owned_keys` = set `_key(artist,title)`;
  `owned_isrcs`; `label_counts` = quante tracce hai per etichetta pulita.
- Per ogni `label` in `labels`: `items = search_by_label(label, limit=...)`.
  Per ogni item costruisci un candidato **già risolto** (i campi Spotify ci sono):
  `artist = item["artists"][0]["name"]`, `title = item["name"]`,
  `spotify_id`, `spotify_url`, `album_art_url`, `isrc`, `duration_seconds`,
  `album_id`, `source="label"`, `seed=label`, `label=label`, `label_owned=True`.
- Dedup: scarta se `_key` in `owned_keys` o `isrc` in `owned_isrcs` o duplicati
  tra candidati.
- **Affinità (no tecnica):** `score = label_affinity + artist_overlap + recency`:
  - `label_affinity = min(label_counts[label], 10) / 10` (0–1): quanto segui la label.
  - `artist_overlap = 0.3` se l'artista è già in libreria, altrimenti 0.
  - `recency`: bonus piccolo `0..0.2` da `release_date` (più recente → più alto;
    parse anno da `item["album"]["release_date"]`).
- **Interleave round-robin** tra le etichette (nessuna label domina), poi
  troncamento a `limit`.
- Ritorna `DiscoveryResult(mode="labels", scope="; ".join(labels)[:60], ...)`.

`album_label_fn` non serve nel radar (la label è il seed stesso).

### 2.4 `app/schemas.py`

`DiscoveryCandidateOut`: **rimuovere** `compatibility`; **aggiungere**
`label: str | None = None`, `label_owned: bool = False`. Commento `source` +=
"| label". Nuovo:
```python
class DiscoveryLabelsRequest(BaseModel):
    labels: list[str] | None = None   # None -> top etichette della libreria
    limit: int = Field(default=20, ge=1, le=50)
```

### 2.5 `app/routers/discovery.py`

- `_candidate_out`: togliere `compatibility`, aggiungere `label`, `label_owned`.
- `/expand`: passare l'annotazione etichetta. Costruire
  `album_label_fn = lambda aid: album_label(db, SpotifyWebClient(db), aid)` (solo
  se Spotify configurato) e `owned_labels` dalla libreria; passarli a
  `discover_for_playlist` (che internamente chiama `_annotate_labels`).
- Nuovo endpoint:
  ```python
  @router.post("/labels", response_model=DiscoveryResponse)
  def labels_radar(req: DiscoveryLabelsRequest, db=Depends(get_db)):
      if not _spotify_configured():
          raise HTTPException(409, "Spotify non configurato: serve per il Radar etichette.")
      labels = req.labels or [o["label"] for o in labels_overview(db)[:6]]
      if not labels:
          raise HTTPException(409, "Nessuna etichetta in libreria: recuperale prima da Spotify.")
      client = SpotifyWebClient(db)
      result = discover_by_labels(
          db, labels=labels, search_by_label=lambda l, **k: client.search_by_label(l, **k),
          limit=req.limit,
      )
      return _response(result)
  ```
- `discover_for_playlist`: nuovo parametro opzionale
  `album_label_fn=None, owned_labels: set[str] | None = None`; se presenti,
  chiama `_annotate_labels(ranked, album_label_fn, owned_labels)` prima del
  ritorno.

### 2.6 Test (`backend/tests/`)

- `test_labels.py`: `_clean_label` (licence-to, suffissi, idempotenza, None);
  `labels_overview` merge di varianti nello stesso bucket.
- `test_discovery.py` (estendere; ci sono già `FakeSimilarity`/`FakeLLM`):
  - aggiornare gli assert che usano `compatibility` (rimosso).
  - `discover_by_labels`: con un fake `search_by_label`, verifica dedup vs
    libreria, `label_owned=True`, ranking per affinità (label più seguita prima),
    interleave tra label.
  - annotazione etichetta su expand: fake `album_label_fn` → `label`/`label_owned`.
- `test_spotify_resilience.py` o nuovo: `search_by_label` costruisce la query
  `label:"..."` e gestisce SpotifyError → `[]` (con http fake).

## 3. Frontend

### 3.1 `lib/api.ts`
- `DiscoveryCandidate`: rimuovere `compatibility`; aggiungere
  `label?: string | null`, `label_owned?: boolean`. `source` include `"label"`.
- Nuovo: `discoverByLabels(labels?: string[], limit = 20)` →
  `apiPost<DiscoveryResponse>("/api/discovery/labels", { labels, limit })`.

### 3.2 `app/discovery/page.tsx`
- **Mode toggle editoriale** (come lo "Stile AI" del set-builder): due modi
  `Espandi playlist` | `Radar etichette`.
- **Espandi playlist** (esistente): rimuovere il badge `% compat`. Ogni
  candidato mostra il segnale sorgente (`artista affine`/`traccia affine`) e, se
  `label_owned`, un badge neutro `↳ <label>` ("anche su un'etichetta che segui").
- **Radar etichette** (nuovo): selettore etichette (default: prime ~6 da
  `getLabels()`, selezionabili/deselezionabili come chip) + bottone "Scopri" →
  `discoverByLabels(selected)`. Ogni candidato: `artista — titolo`, label come
  segnale (`<label>`), badge se affine, pulsante "Aggiungi" (riusa
  `discoveryAddToLibrary`). Nessuna percentuale.
- `CandidateRow`: rimuovere `compatibility`; aggiungere il badge label.
- Job lunghi: il radar è sincrono (~1 ricerca per label); mostra `Spinner`
  inline; opzionalmente registrarlo nella barra globale via `useJobs`
  `startClientJob/endClientJob` (coerente col backfill etichette).

### 3.3 Estetica
Monocromatica editoriale invariata; nessun colore nuovo; badge neutri; dark+paper.

## 4. Testing & verifica
- Backend: `pytest backend/tests` verde (nuovi test + esistenti aggiornati).
- Frontend: `npm run lint` (0 errori) + `npm run build` puliti.
- Verifica reale: riavviare backend; `POST /api/discovery/labels` con le top
  etichette → candidati reali non posseduti; `/expand` senza `compatibility` e
  con badge label; UI nei due temi (radar + espandi, stato vuoto/errore).

## 5. Fuori scope
- Nessun nuovo provider oltre Spotify `search_by_label`.
- Nessuna migrazione dati su `Track.label` (la pulizia è a read-time in
  `labels_overview` + a derivazione per i nuovi backfill).
- Nessun cambiamento al Set Builder (la parte tecnica resta sua).

## 6. Ordine di implementazione
A) `_clean_label` + `album_label` + `labels_overview` merge (+ test).
B) `search_by_label` (+ test).
C) `discover_by_labels` + rimozione `compatibility` + `_annotate_labels`
   (service) (+ test).
D) Schemi + router `/labels` + wiring annotazione su `/expand` (+ test).
E) `lib/api.ts` tipi + `discoverByLabels`.
F) `app/discovery/page.tsx`: toggle modi, Radar etichette, rimozione compat,
   badge label.
G) Verifica reale (backend riavviato) + lint/build + screenshot due temi.
Ogni fase lascia `pytest`/`lint`/`build` verdi.
