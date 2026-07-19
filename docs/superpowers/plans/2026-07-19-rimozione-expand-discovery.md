# Rimozione del flusso Discovery "expand" (Last.fm) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rimuovere completamente il flusso di discovery "espansione playlist" (Last.fm) da backend, frontend, test e documentazione, lasciando come unico flusso il dig "Scava" (Discogs).

**Architecture:** Taglio in cascata dai consumatori alle dipendenze, così che ogni task lasci l'albero verde: prima si spoglia il router `discovery` del ramo expand, poi si scioglie l'accoppiamento fra i due service e si elimina `services/discovery.py`, poi schemas/playlists/integrations/config, infine frontend e docs.

**Tech Stack:** Backend Python 3 + FastAPI + SQLAlchemy + Pydantic (pytest). Frontend Next.js 16 + React + TypeScript (npm lint/build).

## Global Constraints

- **Commit senza co-autore.** Nessun trailer `Co-Authored-By` nei messaggi di commit.
- **Branch di lavoro:** `feat/rimozione-expand-discovery` (già creato; lo spec è il primo commit).
- **Non toccare** il dig "Scava": endpoint `/genres`, `/dig`, `/release/{id}`, `/preview`, `/add`, `/save-for-later`; pagina `/discovery` e i suoi componenti; il player docked.
- **Non riscrivere** i documenti storici sotto `docs/superpowers/plans/` e `docs/superpowers/specs/` (sono verbali datati). Le modifiche docs riguardano solo i documenti di stato corrente (README, CLAUDE.md, docs/ARCHITECTURE.md, docs/API.md, docs/ROADMAP.md, docs/DEPENDENCIES.md, docs/architettura.svg, PROGRESS.md).
- **Comandi backend:** da `backend/`, con venv attivo (`source .venv/bin/activate`), test con `python -m pytest tests`.
- **Comandi frontend:** da `frontend/`, `npm run lint` e `npm run build`.
- **Spec di riferimento:** `docs/superpowers/specs/2026-07-19-rimozione-expand-discovery-design.md`.

---

### Task 1: Router discovery — rimuovere il ramo expand (`/expand`, `/status`)

Rimuove dal router discovery tutto ciò che serve solo all'expand, lasciando intatto il dig. Da fare **per primo**: dopo questo task nessuno importa più `discover_for_playlist`, così `services/discovery.py` diventa cancellabile al Task 2.

**Files:**
- Modify: `backend/app/routers/discovery.py`
- Modify: `backend/tests/test_discovery_router_http.py`

**Interfaces:**
- Consumes: niente dai task successivi.
- Produces: il router espone solo gli endpoint dig (`/genres`, `/dig`, `/release/{id}`, `/preview`, `/add`, `/save-for-later`). Nessun import residuo da `app.services.discovery`, `app.integrations.lastfm`, `app.integrations.llm`, `app.integrations.spotify`, `app.services.labels`, `app.core.config`.

- [ ] **Step 1: Rimuovere i test HTTP di `/status` e `/expand`**

In `backend/tests/test_discovery_router_http.py` elimina i test dell'expand e dello status, tenendo i test del dig. Rimuovi:
- `test_status_riflette_lastfm_spotify_ai` (intorno a riga 42).
- Tutti i test sotto il commento `# --- /expand ---` (riga ~165 in poi): `test_expand_409_senza_lastfm`, `test_expand_404_playlist_inesistente`, `test_expand_200_via_http`, e le fixture/helper usate solo da questi (es. `_EmptySimilarity`, `_FakeSimilarity`, `_make_playlist` se locale e non usato altrove nel file).
- Aggiorna il docstring del modulo di test se cita `/expand`.

Verifica quali simboli restano usati prima di cancellarli:

```bash
cd backend && grep -n "_EmptySimilarity\|_FakeSimilarity\|_make_playlist\|lastfm\|expand\|discovery/status" tests/test_discovery_router_http.py
```

- [ ] **Step 2: Rimuovere il ramo expand dal router**

In `backend/app/routers/discovery.py`:

(a) **Docstring modulo** (righe 1-9): sostituisci con una che descrive solo il dig, es.:

```python
"""Discovery mode: crate digging via Discogs ("Scava").

Endpoint dig: genera lead per genere/etichetta, ne apre la tracklist, offre una
preview audio effimera e importa/salva-per-dopo i lead scelti. La sorgente e'
Discogs (integrations/discogs); iTunes/YouTube servono solo la preview.
"""
```

(b) **Import** — rimuovi queste righe/bloacchi interi:
- `from app.core.config import settings`
- `from app.integrations.lastfm import (LastFMError, get_lastfm_client, lastfm_configured,)`
- `from app.integrations.llm import get_llm_client, llm_configured`
- `from app.integrations.spotify import SpotifyWebClient`
- `from app.services.labels import _clean_label, album_label, labels_overview`
- `from app.services.discovery import (DiscoveryCandidate, DiscoveryResult, discover_for_playlist,)`
- dal blocco `from app.schemas import (...)` togli le tre voci: `DiscoveryCandidateOut`, `DiscoveryExpandRequest`, `DiscoveryResponse` (lascia tutte le altre, incluse `DiscoveryAddRequest/Response` e le dig).

(c) **Helper solo-expand** — elimina interamente queste funzioni: `_spotify_configured` (129-130), `_resolver` (133-140), `_maybe_llm` (143-150), `_candidate_out` (153-159), `_owned_labels` (162-164), `_response` (167-171), `_require_lastfm` (174-179).

(d) **Handler** — elimina interamente `@router.get("/status")` / `def status()` (182-188) e `@router.post("/expand", ...)` / `def expand(...)` (191-225).

Attenzione a cosa **resta** e non va toccato: `add_track_to_playlist` (lo usa `save_for_later`), `Track`/`select` (li usa `discovery_genres`), `time`/`re`/`ItunesClient`/`DiscogsClient`, gli helper `_cached_get_release`/`_clean_artist_name`/`_parse_duration`/`_lead_out`, e tutti gli handler dig.

- [ ] **Step 3: Verificare che non restino import orfani**

```bash
cd backend && grep -n "settings\|lastfm\|SpotifyWebClient\|llm_configured\|get_llm_client\|_clean_label\|album_label\|labels_overview\|discover_for_playlist\|DiscoveryResponse\|DiscoveryCandidate\|DiscoveryExpandRequest\|_require_lastfm\|_resolver\|_maybe_llm\|_owned_labels\|_response\|_candidate_out\|_spotify_configured" app/routers/discovery.py
```
Expected: nessun output (tutti i riferimenti expand spariti).

- [ ] **Step 4: Eseguire i test del router**

Run: `cd backend && python -m pytest tests/test_discovery_router_http.py -q`
Expected: PASS (solo i test dig restano).

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/discovery.py backend/tests/test_discovery_router_http.py
git commit -m "refactor(discovery): rimuovi il ramo expand dal router (resta il dig)"
```

---

### Task 2: Service — sciogliere l'accoppiamento ed eliminare `services/discovery.py`

Sposta i due helper generici che il dig importa dall'expand, poi cancella il modulo expand.

**Files:**
- Modify: `backend/app/services/discovery_dig.py`
- Delete: `backend/app/services/discovery.py`
- Modify: `backend/tests/test_discovery.py`
- Delete: `backend/tests/test_expand_variant_dedup.py`
- Modify: `backend/tests/test_archived.py`

**Interfaces:**
- Consumes: niente.
- Produces: `discovery_dig.py` definisce localmente `_norm(value: str | None) -> str` e `_library_tracks(db: Session) -> list[Track]`; non importa più nulla da `app.services.discovery`. Il modulo `app.services.discovery` non esiste più.

- [ ] **Step 1: Spostare `_norm` e `_library_tracks` in `discovery_dig.py`**

In `backend/app/services/discovery_dig.py`:

(a) Rimuovi la riga `from app.services.discovery import _library_tracks, _norm` (riga 34).

(b) Aggiungi gli import necessari in cima al file (accanto agli altri): assicurati che ci siano `from sqlalchemy import select` e `from app.models import Track` (l'import di `Session` da `sqlalchemy.orm` c'è già alla riga 26).

(c) Aggiungi le due funzioni subito dopo gli import / prima del loro primo uso (p.es. sopra `PAGES_PER_DIG`):

```python
def _norm(value: str | None) -> str:
    return (value or "").strip().lower()


def _library_tracks(db: Session) -> list[Track]:
    return list(db.scalars(select(Track)).all())
```

- [ ] **Step 2: Eliminare il modulo expand**

```bash
cd backend && rm app/services/discovery.py
```

- [ ] **Step 3: Ripulire `test_discovery.py`**

In `backend/tests/test_discovery.py`:
- Rimuovi gli import di modulo `from app.integrations.lastfm import LastFMClient` (riga 5) e `from app.services.discovery import discover_for_playlist` (riga 6).
- Rimuovi tutti i test che usano `LastFMClient` o `discover_for_playlist`: `test_lastfm_similar_artists_parsing`, `test_lastfm_normalizes_single_dict`, `test_expand_collects_and_ranks`, `test_expand_drops_tracks_already_in_library`, `test_expand_annotates_owned_label`, `test_resolution_is_bounded`, e ogni altro test/fixture (`FakeSimilarity`, `_make_playlist`, `ManySimilarity`, ecc.) usato solo da questi.
- **Tieni** `test_add_discovered_track_to_library` (righe 300-321): nonostante il nome, testa `import_single_track` (idempotenza libreria), che serve al dig `/add`. Usa import locali propri, non dipende da nulla di rimosso.
- Se il file resta col solo `test_add_discovered_track_to_library`, va bene lasciarlo lì (oppure spostarlo in un `tests/test_playlist_import.py` — opzionale, non richiesto).

Verifica cosa resta usato prima di cancellare le fixture:

```bash
cd backend && grep -n "def test_\|FakeSimilarity\|_make_playlist\|ManySimilarity\|discover_for_playlist\|LastFMClient" tests/test_discovery.py
```

- [ ] **Step 3b: Rimuovere gli altri test che importano `app.services.discovery`**

Altri due file di test dipendono dal modulo expand (scoperti in esecuzione):

- `backend/tests/test_expand_variant_dedup.py`: è interamente expand (feature A16, testa `_drop_in_library`/`_key`/`DiscoveryCandidate`). **Eliminalo intero:** `cd backend && rm tests/test_expand_variant_dedup.py`.
- `backend/tests/test_archived.py`: testa la feature "traccia scartata" in generale — quasi tutto resta. Rimuovi **solo** il test `test_discovery_non_ripropone_scartate` (righe ~164-169) e la sua riga di import locale `from app.services.discovery import DiscoveryCandidate, _drop_in_library, _key`. **Non toccare** gli altri 11 test del file. (La garanzia "il dig non ripropone le scartate" resta comunque valida via `_library_tracks`, che include le archiviate nell'owned-index del dig; un eventuale test dig-level è follow-up, non parte di questo task.)

- [ ] **Step 4: Eseguire i test discovery + del dig**

Run: `cd backend && python -m pytest tests/test_discovery.py tests/test_discovery_dig.py -q`
Expected: PASS. (Se `tests/test_discovery_dig.py` non esiste con questo nome, lancia comunque `python -m pytest tests -q -k discovery` per coprire il dig.)

- [ ] **Step 5: Verificare che nessuno importi più `services.discovery`**

```bash
cd backend && grep -rn "from app.services.discovery import\|import app.services.discovery\b\|app.services.discovery\." app tests
```
Expected: nessun output (solo `discovery_dig` deve comparire, non `discovery`).

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/discovery_dig.py backend/tests/test_discovery.py backend/tests/test_archived.py
git rm backend/app/services/discovery.py backend/tests/test_expand_variant_dedup.py
git commit -m "refactor(discovery): sposta _norm/_library_tracks nel dig ed elimina services/discovery"
```

---

### Task 3: Schemas — rimuovere gli schemi expand e discovered-tracks

**Files:**
- Modify: `backend/app/schemas.py`

**Interfaces:**
- Consumes: niente.
- Produces: `schemas.py` non definisce più `DiscoveryCandidateOut`, `DiscoveryResponse`, `PlaylistAddTrackRequest`, `PlaylistAddTrackResponse`, `DiscoveryExpandRequest`. Restano `DiscoveryAddRequest`/`DiscoveryAddResponse` (dig) e tutti gli schemi dig.

- [ ] **Step 1: Eliminare le classi expand/discovered-tracks**

In `backend/app/schemas.py` elimina interamente queste classi (lasciando intatte `DiscoveryAddRequest` righe 456-465 e `DiscoveryAddResponse` righe 468-470, che sono del dig):
- `class DiscoveryCandidateOut(BaseModel):` (433-446)
- `class DiscoveryResponse(BaseModel):` (449-453)
- `class PlaylistAddTrackRequest(BaseModel):` (473-482)
- `class PlaylistAddTrackResponse(BaseModel):` (485-489)
- `class DiscoveryExpandRequest(BaseModel):` (492-495)

- [ ] **Step 2: Verificare che nulla nel backend importi gli schemi rimossi**

```bash
cd backend && grep -rn "DiscoveryCandidateOut\|DiscoveryResponse\|PlaylistAddTrackRequest\|PlaylistAddTrackResponse\|DiscoveryExpandRequest" app tests
```
Expected: nessun output. (Se compare qualcosa in `routers/playlists.py`, verrà rimosso al Task 4 — in tal caso esegui prima il Task 4; ma se il Task 1 è fatto, il router discovery è già pulito.)

- [ ] **Step 3: Import check del backend**

Run: `cd backend && python -c "import app.schemas; import app.routers.discovery"`
Expected: nessun errore.

- [ ] **Step 4: Commit**

```bash
git add backend/app/schemas.py
git commit -m "refactor(schemas): rimuovi gli schemi expand e discovered-tracks"
```

---

### Task 4: Router playlists — rimuovere l'endpoint `discovered-tracks`

**Files:**
- Modify: `backend/app/routers/playlists.py`
- Delete: `backend/tests/test_playlist_add_track.py`
- Modify: `backend/tests/test_membership_provenance.py`

**Interfaces:**
- Consumes: schemi rimossi al Task 3.
- Produces: nessun endpoint `POST /api/playlists/{id}/discovered-tracks`. Il router non importa più `PlaylistAddTrackRequest`/`PlaylistAddTrackResponse` né `import_single_track` (se orfano).

- [ ] **Step 1: Rimuovere i test dell'endpoint**

```bash
cd backend && rm tests/test_playlist_add_track.py
```

In `backend/tests/test_membership_provenance.py`:
- Rimuovi `test_endpoint_discovered_tracks_marca_cratory` (riga ~140) e l'import `from app.routers.playlists import add_discovered_track` (riga 17), **solo** se non usato da altri test del file. Verifica:

```bash
cd backend && grep -n "add_discovered_track" tests/test_membership_provenance.py
```
Se compare solo nel test rimosso e nell'import, togli entrambi.

- [ ] **Step 2: Rimuovere l'handler e gli import orfani**

In `backend/app/routers/playlists.py`:
- Elimina l'handler `@router.post("/{playlist_id}/discovered-tracks", ...)` / `def add_discovered_track(...)` (righe 235-271).
- Dal blocco `from app.schemas import (...)` togli `PlaylistAddTrackRequest` e `PlaylistAddTrackResponse` (righe 39-40).
- `import_single_track` (import riga 55) è usato **solo** dall'handler rimosso: toglilo dal suo blocco import. Verifica prima:

```bash
cd backend && grep -n "import_single_track" app/routers/playlists.py
```
Se l'unica occorrenza rimasta è la riga di import, rimuovila.
- **Non** toccare `SpotifyWebClient`, `SpotifyError`, `add_track_to_playlist`, `recount_playlist`, `logger`: restano usati da altri handler (`_http_error`, import Spotify, `create_playlist_from_tracks`, ecc.). Conferma:

```bash
cd backend && grep -n "SpotifyWebClient\|SpotifyError\|add_track_to_playlist\|recount_playlist\|logger" app/routers/playlists.py
```
Expected: più occorrenze fuori dall'handler rimosso (quindi si tengono).

- [ ] **Step 3: Eseguire i test playlist + provenance**

Run: `cd backend && python -m pytest tests/test_membership_provenance.py -q && python -c "import app.routers.playlists"`
Expected: PASS e nessun errore di import.

- [ ] **Step 4: Commit**

```bash
git add backend/app/routers/playlists.py backend/tests/test_membership_provenance.py
git rm backend/tests/test_playlist_add_track.py
git commit -m "refactor(playlists): rimuovi l'endpoint discovered-tracks (era l'add dell'expand)"
```

---

### Task 5: Integrations/config — eliminare Last.fm e il write-back Spotify orfano

**Files:**
- Delete: `backend/app/integrations/lastfm.py`
- Delete: `backend/tests/test_lastfm_cache.py`
- Modify: `backend/app/integrations/__init__.py`
- Modify: `backend/app/integrations/spotify.py`
- Modify: `backend/app/core/config.py`
- Modify: `backend/app/routers/services.py`

**Interfaces:**
- Consumes: niente.
- Produces: nessun `LastFMClient`/`SimilarityClient`; nessun `settings.lastfm_api_key`; nessuna card `"lastfm"` in `/api/services/status`; nessun `SpotifyWebClient.add_tracks`.

- [ ] **Step 1: Eliminare l'integration Last.fm e i suoi test**

```bash
cd backend && rm app/integrations/lastfm.py tests/test_lastfm_cache.py
```

- [ ] **Step 2: Rimuovere l'interfaccia `SimilarityClient`**

`SimilarityClient` (in `backend/app/integrations/__init__.py`, righe 53-77) era implementata solo da `LastFMClient`. Verifica che non abbia altri usi:

```bash
cd backend && grep -rn "SimilarityClient" app tests
```
Expected: nessun output dopo aver rimosso `lastfm.py`. Se confermato:
- elimina la classe `class SimilarityClient(ABC): ...` (53-77);
- nel docstring del modulo (riga 10) togli il riferimento a Last.fm, es. sostituisci la riga con:

```
- Discogs: crate digging per genere/etichetta (Discovery).
```

- [ ] **Step 3: Rimuovere `SpotifyWebClient.add_tracks`**

`add_tracks` (in `backend/app/integrations/spotify.py`, riga ~291) era usato solo dall'endpoint discovered-tracks (rimosso al Task 4). Verifica e rimuovi:

```bash
cd backend && grep -rn "add_tracks" app tests
```
Expected: dopo il Task 4, l'unica occorrenza è la definizione in `spotify.py`. Elimina il metodo `def add_tracks(self, playlist_id: str, track_ids: list[str]) -> None:` e il suo corpo.

- [ ] **Step 4: Rimuovere il campo di config**

In `backend/app/core/config.py` elimina la riga `lastfm_api_key: str = ""` (riga 35).

- [ ] **Step 5: Rimuovere la card Last.fm da Impostazioni**

In `backend/app/routers/services.py` elimina la voce dizionario con `"key": "lastfm"` (righe 44-50, l'oggetto `{...}` completo, virgola inclusa).

- [ ] **Step 6: Verifica globale backend + suite completa**

```bash
cd backend && grep -rn -i "lastfm\|last\.fm" app
```
Expected: solo commenti generici in `integrations/_http.py`/`slskd.py`/`spotify.py` che citano "lastfm" come esempio storico di comportamento HTTP; **nessun** riferimento vivo a `LastFMClient`, `lastfm_api_key`, `get_lastfm_client`, `lastfm_configured`. (Ripulisci quei commenti se banale, altrimenti lasciali: non sono codice.)

Run: `cd backend && python -m pytest tests -q`
Expected: PASS, intera suite verde.

- [ ] **Step 7: Commit**

```bash
git add backend/app/integrations/__init__.py backend/app/integrations/spotify.py backend/app/core/config.py backend/app/routers/services.py
git rm backend/app/integrations/lastfm.py backend/tests/test_lastfm_cache.py
git commit -m "refactor(integrations): elimina Last.fm, SimilarityClient e il write-back Spotify orfano"
```

---

### Task 6: Frontend — rimuovere pagina, componente, client, tipi e i18n dell'expand

**Files:**
- Delete: `frontend/app/playlists/[id]/expand/page.tsx` (intera cartella `expand/`)
- Delete: `frontend/components/expand-results.tsx`
- Modify: `frontend/app/playlists/[id]/page.tsx`
- Modify: `frontend/lib/api/discovery.ts`
- Modify: `frontend/lib/api/playlists.ts`
- Modify: `frontend/lib/api/types.ts`
- Modify: `frontend/lib/i18n/it.ts`
- Modify: `frontend/lib/i18n/en.ts`

**Interfaces:**
- Consumes: gli endpoint backend rimossi (Task 1/4).
- Produces: nessun riferimento a `discoverExpand`, `discoveryStatus`, `addDiscoveredTrackToPlaylist`, `ExpandResults`, `DiscoveryStatus`, `DiscoveryResponse`, `DiscoveryCandidate`, `PlaylistAddTrackResult`, o alla route `/playlists/[id]/expand`.

> **Nota Next 16 (leggi `frontend/CLAUDE.md`):** non serve rigenerare routing per una cancellazione di route, ma se il dev server gira e i CSS/route sembrano stantii, `rm -rf .next` prima del build.

- [ ] **Step 1: Eliminare pagina e componente**

```bash
cd frontend && rm -rf "app/playlists/[id]/expand" && rm components/expand-results.tsx
```

- [ ] **Step 2: Togliere il bottone dalla pagina playlist**

In `frontend/app/playlists/[id]/page.tsx`:
- Elimina la riga 252 (il `<ButtonLink href={`/playlists/${pid}/expand`} ...>...{t.playlists.discoverSimilarButton}</ButtonLink>`).
- Rimuovi `Compass` dall'import di `lucide-react` (riga 7): l'icona era usata solo da quel bottone. Verifica:

```bash
cd frontend && grep -n "Compass" "app/playlists/[id]/page.tsx"
```
Se l'unica occorrenza rimasta è l'import, togli `Compass` dalla lista.

- [ ] **Step 3: Ripulire il client API discovery**

In `frontend/lib/api/discovery.ts`:
- Elimina le funzioni `discoveryStatus` (15-17) e `discoverExpand` (19-25).
- Dal blocco `import type { ... } from "./types";` togli `DiscoveryResponse` e `DiscoveryStatus` (lascia `DiscoveryAddResponse`, `DiscoveryDigResponse`, `DiscoveryGenres`, `DiscoveryImportInput`, `DiscoveryPreview`, `DiscogsRelease`).
- Puoi aggiornare il commento `// --- Discovery (Fase F) ---` (riga 13) se vuoi, ma non è necessario.

- [ ] **Step 4: Ripulire il client API playlists**

In `frontend/lib/api/playlists.ts`:
- Elimina la funzione `addDiscoveredTrackToPlaylist` (76-...).
- Dal blocco import type togli `DiscoveryCandidate` (riga 3) e `PlaylistAddTrackResult` (riga 7).

- [ ] **Step 5: Rimuovere i tipi orfani**

In `frontend/lib/api/types.ts` elimina le interfacce:
- `DiscoveryStatus` (86-90)
- `DiscoveryCandidate` (92-107) — usata solo da expand-results/playlists client/DiscoveryResponse, tutti rimossi.
- `DiscoveryResponse` (109-114)
- `PlaylistAddTrackResult` (474-479)

**Tieni** `DiscoveryAddResponse` (116-119) e tutti i tipi dig.

- [ ] **Step 6: Rimuovere le stringhe i18n**

In `frontend/lib/i18n/it.ts`:
- Riga 441: `discoverSimilarButton: "Scopri musica simile",`
- Blocco `expand: { ... }` (459-482, incluse le graffe e la virgola finale).
- Riga 1052: chiave `lastfm_not_configured: ...`.

In `frontend/lib/i18n/en.ts`:
- Riga 439: `discoverSimilarButton: "Discover similar music",`
- Blocco `expand: { ... }` (457-480).
- Riga 1051: chiave `lastfm_not_configured: ...`.

- [ ] **Step 7: Verificare che non restino riferimenti vivi**

```bash
cd frontend && grep -rn -i "discoverExpand\|discoveryStatus\|addDiscoveredTrackToPlaylist\|ExpandResults\|expand-results\|/expand\|discoverSimilarButton\|\.expand\b\|lastfm\|last\.fm\|PlaylistAddTrackResult\|DiscoveryStatus\|DiscoveryResponse\|DiscoveryCandidate" app components lib | grep -v node_modules
```
Expected: nessun output. (Attenzione ai falsi positivi legittimi come `aria-expanded` nei componenti UI: quello NON va toccato — se compare, ignoralo.)

- [ ] **Step 8: Lint + build**

Run: `cd frontend && npm run lint && npm run build`
Expected: 0 errori (eventuali warning `<img>` preesistenti sono ok).

- [ ] **Step 9: Commit**

```bash
git add frontend/app/playlists frontend/components frontend/lib
git commit -m "refactor(frontend): rimuovi pagina/componente/client/i18n dell'expand playlist"
```

---

### Task 7: Documentazione — aggiornare lo stato corrente

Aggiorna solo i documenti di stato corrente. Non toccare `docs/superpowers/plans|specs/` storici.

**Files:**
- Modify: `README.md`, `CLAUDE.md`, `docs/ARCHITECTURE.md`, `docs/architettura.svg`, `docs/API.md`, `docs/ROADMAP.md`, `docs/DEPENDENCIES.md`, `PROGRESS.md`

- [ ] **Step 1: README.md**

- Riga 51-53: la voce "Discovery by taste" diventa solo dig, es.: `- Discovery by taste: crate-dig by genre/label via Discogs ("Scava").`
- Riga 84: nella riga "External:" togli `Last.fm` dall'elenco provider.
- Riga 137: togli la riga `LASTFM_API_KEY=` dall'esempio `.env`.
- Riga 201-202: nel workflow togli "expand, or" — resta `use Discovery ("Scava" by genre/label via Discogs)`.

- [ ] **Step 2: CLAUDE.md**

- Riga 90: nell'elenco provider Discovery togli `Last.fm (similarity)`, lascia Discogs e Spotify (resolver).
- Righe 93-96: riscrivi il paragrafo "Discovery works by taste…": togli "playlist expansion is Last.fm-centric… with a Spotify resolver via `/search`"; resta la descrizione del solo dig Discogs per genere/label.

- [ ] **Step 3: docs/ARCHITECTURE.md + architettura.svg**

- `docs/ARCHITECTURE.md`: righe 26, 77 (`-> Last.fm similarity`), 85, 447 (riga tabella `| Last.fm | active | ...`), 457 — rimuovi il ramo expand/Last.fm dal diagramma testuale e dalla tabella provider; lascia il dig. Riga 436 (menzione storica del legacy enrichment) può restare.
- `docs/architettura.svg`: righe 73-74 (box `DISCOVERY · EXPAND` e il suo sottotitolo `Last.fm similarity → resolver Spotify…`): rimuovi il box o riconvertilo. Se il layout SVG è a coordinate fisse, la scelta più sicura è **eliminare i due `<text>` del box expand** e, se resta uno spazio evidente, nessun riposizionamento obbligatorio (è un diagramma statico). Apri il file e valuta; se il riposizionamento è oneroso, elimina solo le due righe di testo del box expand.

- [ ] **Step 4: docs/API.md**

- Riga 164: togli la frase su `/playlists/[id]/expand` e `POST /api/discovery/expand`.
- Righe 347-367: rimuovi dalla lista endpoint `POST /api/discovery/expand` e `GET /api/discovery/status`, e la sezione descrittiva `expand` (360-367).
- Righe 431-434: aggiorna la nota finale: Discovery = solo dig; togli il riferimento a expand e a "these three providers (Last.fm, …)" → resta Discogs + Spotify-as-resolver.
- Se `discovered-tracks` è documentato nella sezione playlist, rimuovine la voce.

- [ ] **Step 5: docs/ROADMAP.md**

- Righe 29-30: "Discovery operational (Last.fm expand + Discogs dig)" → "Discovery operational (Discogs dig)".
- Righe 55, 88, 194: la voce backlog "Last.fm tags as a 2nd dig source (parked)" e "unificazione expand/dig" diventano **chiuse/non applicabili** — l'expand non esiste più. Rimuovile o marcale come chiuse con data 2026-07-19.
- Riga 231: la riga tabella "Spotify recommendation unavailable | Discovery based on Last.fm and the Spotify `/search` resolver" → aggiorna a "Discovery based on Discogs crate digging".

- [ ] **Step 6: docs/DEPENDENCIES.md**

- Riga 74: elimina la riga tabella `| Last.fm API | Discovery (playlist expand, similarity) | Optional (Discovery) |`.
- Riga 81: nella frase "None of Last.fm/Discogs/Spotify feed BPM/key/genre…" togli `Last.fm/` (resta Discogs/Spotify).
- Riga 29: nella riga `httpx` che elenca "Spotify, Last.fm, Discogs, slskd" togli `Last.fm,`.

- [ ] **Step 7: PROGRESS.md**

Aggiungi in cima (o dove vanno le milestone recenti) una voce datata **2026-07-19** che riassume: rimozione completa del flusso Discovery expand (Last.fm) da backend/frontend/test/docs; eliminati `services/discovery.py`, `integrations/lastfm.py`, `SimilarityClient`, l'endpoint `discovered-tracks` e `SpotifyWebClient.add_tracks`, il campo `lastfm_api_key` e la card Last.fm in Impostazioni; `_norm`/`_library_tracks` spostati nel dig. Discovery = solo Scava/Discogs. Aggiorna "Ultimo aggiornamento" a 2026-07-19. Non riscrivere le entry storiche.

- [ ] **Step 8: Verifica docs**

```bash
grep -rn -i "lastfm\|last\.fm\|/api/discovery/expand\|discovered-tracks\|expand playlist\|espansione playlist" README.md CLAUDE.md docs/ARCHITECTURE.md docs/API.md docs/ROADMAP.md docs/DEPENDENCIES.md PROGRESS.md
```
Expected: solo eventuali menzioni **storiche** intenzionali in PROGRESS.md (le milestone datate precedenti restano). Nessun riferimento a expand come feature corrente/attiva.

- [ ] **Step 9: Commit**

```bash
git add README.md CLAUDE.md docs/ARCHITECTURE.md docs/architettura.svg docs/API.md docs/ROADMAP.md docs/DEPENDENCIES.md PROGRESS.md
git commit -m "docs: Discovery = solo dig Discogs; rimosso ogni riferimento all'expand Last.fm"
```

---

### Task 8: Verifica end-to-end

**Files:** nessuna modifica (solo verifica; eventuali fix tornano al task pertinente).

- [ ] **Step 1: Suite backend completa**

Run: `cd backend && python -m pytest tests -q`
Expected: PASS, nessun test rotto, nessun import error.

- [ ] **Step 2: Lint + build frontend**

Run: `cd frontend && npm run lint && npm run build`
Expected: 0 errori.

- [ ] **Step 3: Grep finale su codice vivo**

```bash
cd /Users/lucadenegri/Develop/DJProject01
grep -rn -i "lastfm\|discoverExpand\|discovered-tracks\|expand-results\|discover_for_playlist\|SimilarityClient\|add_tracks" backend/app frontend/app frontend/components frontend/lib | grep -v node_modules
```
Expected: nessun riferimento vivo (solo eventuali commenti HTTP storici in `backend/app/integrations/_http.py`/`slskd.py` se lasciati di proposito).

- [ ] **Step 4: Verifica nel browser (dev server)**

Avvia backend (`uvicorn app.main:app --reload --port 8000`) e frontend (dev server via lo strumento di preview del progetto), poi:
- Apri il dettaglio di una playlist: **non** deve più esserci il bottone "Scopri musica simile" e nessun errore in console/network.
- Apri `/discovery` (Scava): il dig funziona (seed genere/label, lead, preview, tracklist).
- Apri Impostazioni: **non** compare più la card Last.fm; compaiono Spotify, Anthropic, Discogs, slskd.
- Naviga direttamente a `/playlists/<id>/expand`: deve dare 404 (route rimossa), non un crash.

- [ ] **Step 5: Chiudere il branch**

Con tutta la suite verde e la verifica browser ok, usa la skill `superpowers:finishing-a-development-branch` per decidere merge/PR.

---

## Self-Review

**Spec coverage:** ogni intervento dello spec ha un task — service untangle + delete (T2), router discovery (T1), schemas (T3), playlists/discovered-tracks (T4), lastfm integration + SimilarityClient + config + services card + add_tracks (T5), frontend pagina/componente/button/client/tipi/i18n (T6), docs (T7), verifica (T8). Il taglio di `discovered-tracks` e `add_tracks` (deciso in brainstorming) è coperto da T4+T5.

**Ordine di sicurezza:** T1 (togli l'importatore di `discover_for_playlist`) precede T2 (cancella `services/discovery.py`); T3/T4 (schemi/handler) dopo T1; T5 dopo T4 (così `add_tracks` è già orfano). Ogni task chiude con suite/build verde.

**Type consistency:** `_norm`/`_library_tracks` mantengono firma identica nel nuovo file; `discovery_dig.dig`/`DiscoveryLead` invariati; nel frontend i tipi rimossi (`DiscoveryStatus`, `DiscoveryResponse`, `DiscoveryCandidate`, `PlaylistAddTrackResult`) non hanno consumatori residui dopo T6 (verificato con grep negli step).
