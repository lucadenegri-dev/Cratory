# Lotto D — Rifiniture UX — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Via l'import-da-cartella; playlist componibili dalla libreria; download dei mancanti lanciabile dalla playlist; stati di caricamento uniformi.

**Architecture:** Rimozione verticale (pagina + api client + endpoint + job dedicato) dell'import-cartella, tenendo `scan_folder` che serve a indice e pipeline. Nuovo endpoint `POST /api/playlists/create-from-tracks` e modalità "Dalla libreria" nella pagina di creazione manuale. Bottone "Scarica mancanti" nella marginalia della playlist (endpoint esistente). Componente `Loading` unico applicato alle pagine.

**Tech Stack:** Python/FastAPI + pytest; Next.js 16 (`npm run build`). Spec: `~/Develop/docs/superpowers/specs/2026-07-02-metadati-stati-automazioni-design.md` (Lotto D). **Prerequisito: Lotto B mergiato** (il conteggio "mancanti" esclude le scartate via `archived`).

## Global Constraints

- Repo: `/Users/lucadenegri/Develop/DJProject01`, branch dedicato. Commenti e stringhe UI in italiano.
- Test backend: `cd backend && .venv/bin/python -m pytest tests/ -q`. Frontend: `cd frontend && npm run build` + `npm run lint` (0 errori; i 13 warning preesistenti non aumentano).
- Prima di cancellare qualunque simbolo backend: `grep -rn "<simbolo>" backend/app backend/tests` e rimuovere solo ciò che resta orfano.

---

### Task 1: Rimozione "Importa da cartella"

**Files:**
- Delete: `frontend/app/playlists/import-local/page.tsx`
- Modify: `frontend/app/playlists/page.tsx` (riga ~83: link), `frontend/lib/api.ts` (righe ~508-518: `browseLocalFolder`, `startLocalImport`, `localImportStatus` + tipi `LocalBrowseResponse`, `LocalImportJobStatus` se non usati altrove)
- Modify: `backend/app/routers/playlists.py` (endpoint righe 186-213: `local/browse`, `import-local`, `import-local/status`)
- Delete (se orfani dopo grep): `backend/app/services/local_import_job.py`, `backend/tests/test_local_import_job.py`, `backend/tests/test_local_import_router.py`, `backend/tests/test_fs_browse.py`
- KEEP: `backend/app/services/local_import.py` (`scan_folder` è usato da indice e pipeline)

**Interfaces:**
- Consumes/Produces: solo rimozioni. `scan_folder` resta invariato.

- [ ] **Step 1: Mappa le dipendenze** — esegui e annota gli esiti:

```bash
cd /Users/lucadenegri/Develop/DJProject01
grep -rn "local_import_job\|import_local_folder\|browse_local\|LocalBrowseResponse\|LocalImportJobStatus\|LocalFolderImportRequest" backend/app backend/tests
grep -rn "import-local\|browseLocalFolder\|startLocalImport\|localImportStatus\|LocalBrowseResponse\|LocalImportJobStatus" frontend
```

Regola: si rimuove un simbolo solo se TUTTI i suoi usi sono nel perimetro rimosso. `services/local_import.py` NON si tocca se `scan_folder` o altre sue funzioni hanno usi fuori perimetro (indice, pipeline: ci sono di sicuro).

- [ ] **Step 2: Rimuovi frontend** — cancella la pagina, il link "Importa da cartella" in `playlists/page.tsx` (riga ~83, incluso l'import dell'icona `HardDriveDownload` se resta orfano), le tre funzioni e i tipi in `api.ts` (solo se il grep dello Step 1 non mostra altri usi).

- [ ] **Step 3: Rimuovi backend** — in `routers/playlists.py` elimina i tre endpoint (186-213) e gli import rimasti orfani (`LocalBrowseResponse`, `LocalFolderImportRequest`, `LocalImportJobStatus`, `local_import_job`, `browse_local_folder`...). Cancella `services/local_import_job.py` e i tre file di test SOLO se orfani (Step 1). Rimuovi gli schemi orfani da `schemas.py`.

- [ ] **Step 4: Verifica** — `cd backend && .venv/bin/python -m pytest tests/ -q` verde; `cd frontend && npm run build` verde; `grep -rn "import-local" frontend backend` → zero risultati.

- [ ] **Step 5: Commit** — `git commit -m "feat: rimosso import playlist da cartella (superato dal disk-first)"`

---

### Task 2: Endpoint `POST /api/playlists/create-from-tracks`

**Files:**
- Modify: `backend/app/schemas.py` (nuovo request model), `backend/app/routers/playlists.py`
- Test: `backend/tests/test_playlist_from_tracks.py` (nuovo)

**Interfaces:**
- Consumes: modelli `Playlist`, `Track`, tabella `playlist_tracks` esistenti; pattern creazione playlist manuale in `services/manual_import.py` (VERIFICARE come `import_manual` costruisce la Playlist — `source`/`platform`/campi obbligatori — e replicare).
- Produces: `POST /api/playlists/create-from-tracks` body `{"name": str, "track_ids": [int]}` → `PlaylistOut` 201. 422 se name vuoto o track_ids vuoto/inesistenti.

- [ ] **Step 1: Test che falliscono** — crea `backend/tests/test_playlist_from_tracks.py` (pattern `client` con `dependency_overrides` + `StaticPool` da `tests/test_pipeline_router.py`):

```python
"""POST /api/playlists/create-from-tracks: playlist componendo dalla libreria."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app
from app.models import Track


@pytest.fixture()
def client_db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    app.dependency_overrides[get_db] = lambda: session
    try:
        yield TestClient(app), session
    finally:
        app.dependency_overrides.pop(get_db, None)
        session.close()


def test_crea_playlist_da_tracce(client_db):
    client, db = client_db
    ids = []
    for i in range(3):
        t = Track(source_type="local_files", platform="local_files",
                  platform_track_id=f"d{i}", title=f"T{i}", artist="A")
        db.add(t); db.commit(); ids.append(t.id)

    r = client.post("/api/playlists/create-from-tracks",
                    json={"name": "Warmup", "track_ids": ids})
    assert r.status_code == 201
    body = r.json()
    assert body["name"] == "Warmup" and body["track_count"] == 3

    tracks = client.get(f"/api/playlists/{body['id']}/tracks").json()
    assert [t["title"] for t in tracks] == ["T0", "T1", "T2"]


def test_422_su_input_vuoti(client_db):
    client, _ = client_db
    assert client.post("/api/playlists/create-from-tracks",
                       json={"name": "", "track_ids": [1]}).status_code == 422
    assert client.post("/api/playlists/create-from-tracks",
                       json={"name": "X", "track_ids": []}).status_code == 422


def test_422_su_track_id_inesistente(client_db):
    client, _ = client_db
    r = client.post("/api/playlists/create-from-tracks",
                    json={"name": "X", "track_ids": [99999]})
    assert r.status_code == 422
```

(verificare che `PlaylistOut` esponga `track_count` e `id`; adeguare gli assert allo schema reale.)

- [ ] **Step 2: Verifica FAIL** — 404 sull'endpoint.

- [ ] **Step 3: Implementa** — `schemas.py`:

```python
class PlaylistFromTracksRequest(BaseModel):
    name: str = Field(min_length=1)
    track_ids: list[int] = Field(min_length=1)
```

(se `Field` non è già importato da pydantic in schemas.py, aggiungilo.)

`routers/playlists.py` (prima delle route `/{playlist_id}` per non collidere col path param — stessa ragione dell'ordine di `local/browse` oggi):

```python
@router.post("/create-from-tracks", response_model=PlaylistOut, status_code=201)
def create_from_tracks(req: PlaylistFromTracksRequest, db: Session = Depends(get_db)):
    """Crea una playlist componendo tracce gia' in libreria (disk-first)."""
    tracks = db.scalars(select(Track).where(Track.id.in_(req.track_ids))).all()
    by_id = {t.id: t for t in tracks}
    missing = [i for i in req.track_ids if i not in by_id]
    if missing:
        raise HTTPException(status_code=422, detail=f"Tracce inesistenti: {missing}")
    # Stessa costruzione delle playlist manuali (services/manual_import.py:61).
    playlist = Playlist(platform="manual", name=req.name.strip(), kind="manual")
    db.add(playlist)
    db.flush()  # serve playlist.id
    for track_id in req.track_ids:  # nell'ordine scelto dall'utente
        add_track_to_playlist(db, by_id[track_id], playlist)
    recount_playlist(db, playlist)
    db.commit()
    db.refresh(playlist)
    return playlist
```

Import da aggiungere in `routers/playlists.py` se mancanti: `Playlist`, `Track` da `app.models`; `add_track_to_playlist`, `recount_playlist` dallo stesso modulo da cui li importa `services/manual_import.py` (verificare: sono in `app.repositories`). Il `return playlist` diretto va bene se le altre route (es. `playlist_detail`) restituiscono l'ORM con `response_model=PlaylistOut`; altrimenti usare lo stesso serializer che usano loro. NOTA ordine tracce: `add_track_to_playlist` inserisce membership senza posizione — se `GET /{id}/tracks` non preserva l'ordine di inserimento, il test sull'ordine va adeguato a un confronto per insieme (`set`), e l'ordinamento fine si rimanda al Set Builder (fuori scope qui).

- [ ] **Step 4: Verifica PASS + suite** — `pytest tests/test_playlist_from_tracks.py -v && pytest tests/ -q`.
- [ ] **Step 5: Commit** — `git commit -m "feat: endpoint create-from-tracks (playlist dalla libreria)"`

---

### Task 3: UI "Dalla libreria" nella creazione manuale

**Files:**
- Modify: `frontend/lib/api.ts` (nuova funzione), `frontend/app/playlists/import-manual/page.tsx`

**Interfaces:**
- Consumes: endpoint Task 2; `GET /api/tracks` con filtri esistenti (`artist`, `title`, `has_local_file`).
- Produces: pagina con due modalità: "Incolla tracklist" (attuale, invariata) e "Dalla libreria" (ricerca + selezione multipla + crea).

- [ ] **Step 1: api.ts** — accanto a `importManualPlaylist` (riga ~627):

```ts
export function createPlaylistFromTracks(name: string, trackIds: number[]) {
  return apiPost<Playlist>("/api/playlists/create-from-tracks", { name, track_ids: trackIds });
}
```

- [ ] **Step 2: Pagina** — in `import-manual/page.tsx`:

Stato aggiuntivo:

```tsx
const [mode, setMode] = useState<"paste" | "library">("paste");
const [query, setQuery] = useState("");
const [ownedOnly, setOwnedOnly] = useState(true);
const [results, setResults] = useState<Track[]>([]);
const [picked, setPicked] = useState<Track[]>([]);
```

Toggle in testa alla card (sopra il campo nome, che resta comune):

```tsx
<div className="mb-4 flex gap-2">
  <Button size="sm" variant={mode === "paste" ? undefined : "outline"} onClick={() => setMode("paste")}>Incolla tracklist</Button>
  <Button size="sm" variant={mode === "library" ? undefined : "outline"} onClick={() => setMode("library")}>Dalla libreria</Button>
</div>
```

Modalità library (al posto della textarea quando `mode === "library"`): input di ricerca che chiama `apiGet<{ total: number; items: Track[] }>("/api/tracks", { title: query, has_local_file: ownedOnly ? "true" : undefined, limit: 30 })` (debounce ~300ms con `useEffect` su `query`), checkbox "solo possedute", lista risultati cliccabili che aggiungono a `picked` (dedup per id), lista `picked` riordinabile con bottoni ↑/↓ e rimozione ×, submit:

```tsx
const doCreateFromLibrary = async () => {
  setError(null); setBusy(true);
  try {
    await createPlaylistFromTracks(name.trim() || "Playlist manuale", picked.map((t) => t.id));
    router.push("/playlists");
  } catch (e) {
    setError(`Creazione fallita: ${err(e)}`); setBusy(false);
  }
};
```

Il flusso "paste" esistente resta INVARIATO. Riusare `Input`, `Button`, `Checkbox`, `Badge` da `components/ui`; ricerca per titolo O artista: due input o un input che riempie entrambi i param con lo stesso valore — usare `title` per semplicità e un secondo input opzionale "Artista".

- [ ] **Step 3: Verifica** — `npm run build` verde; visiva: cerca, seleziona 3 tracce, riordina, crea → la playlist appare in /playlists con le tracce in ordine.
- [ ] **Step 4: Commit** — `git commit -m "feat: creazione playlist componendo dalla libreria"`

---

### Task 4: "Scarica mancanti" dalla pagina playlist

**Files:**
- Modify: `frontend/app/playlists/[id]/page.tsx` (marginalia, righe ~230-245)

**Interfaces:**
- Consumes: `startPlaylistDownload(pid)` già in `lib/api.ts` (riga ~789, POST `/api/downloads/playlist/{id}`); campi `has_local_file`/`archived` sulle track della playlist.
- Produces: solo UI.

- [ ] **Step 1: Implementa** — nella pagina, calcolo accanto a `ownedCount` (riga ~208):

```tsx
const missing = tracks.filter((t) => !t.has_local_file && !t.archived).length;
```

Stato e azione:

```tsx
const [downloading, setDownloading] = useState(false);
const doDownloadMissing = async () => {
  setDownloading(true);
  try {
    await startPlaylistDownload(pid);
    router.push("/downloads");  // il monitor dei trasferimenti resta là
  } catch (e) {
    setError(`Download non avviato: ${err(e)}`);
    setDownloading(false);
  }
};
```

Bottone in marginalia tra "Scopri musica simile" e "Aggiorna da Spotify":

```tsx
{missing > 0 && (
  <Button size="sm" variant="outline" className="w-full" onClick={doDownloadMissing} disabled={downloading}>
    {downloading ? <Spinner /> : <Download size={15} />} Scarica mancanti ({missing})
  </Button>
)}
```

(import `Download` da lucide-react e `startPlaylistDownload` da api; verificare come la pagina gestisce `error`/`router` — esistono già per le altre azioni. Se `startPlaylistDownload` risponde 409/errore quando slskd non è configurato, il catch lo mostra: comportamento voluto.)

- [ ] **Step 2: Verifica** — `npm run build`; visiva su una playlist con mancanti: bottone visibile col conteggio giusto (le scartate non contano), click → redirect a /downloads col job avviato.
- [ ] **Step 3: Commit** — `git commit -m "feat: Scarica mancanti dalla pagina playlist"`

---

### Task 5: Loading uniformi

**Files:**
- Modify: `frontend/components/ui.tsx` (nuovo componente), poi le pagine (censimento sotto)

**Interfaces:**
- Produces: `Loading({ label? })` — trattamento standard: `Equalizer` + testo muted, centrato nel contenuto.

- [ ] **Step 1: Componente** — in `components/ui.tsx`, accanto a `Equalizer`:

```tsx
export function Loading({ label = "Caricamento…" }: { label?: string }) {
  return (
    <p className="flex items-center gap-2 py-8 text-sm text-muted" role="status">
      <Equalizer /> {label}
    </p>
  );
}
```

- [ ] **Step 2: Applica alle pagine** — censimento (stato attuale → intervento). In OGNI caso il pattern è: stato iniziale `null`, e nel JSX `X === null ? <Loading /> : ...`:

| Pagina | Oggi | Intervento |
|---|---|---|
| `app/page.tsx` (dashboard) | nessuno stato: pagina vuota finché arrivano stats | `{!stats && !error && <Loading />}` prima dei blocchi condizionali |
| `app/library/page.tsx` | tabella vuota indistinguibile dal "nessun risultato" | stato `items: Track[] \| null = null`; `items === null ? <Loading /> : ...`; il messaggio "nessun risultato" resta per `items.length === 0` |
| `app/playlists/page.tsx` | `imported === null` → niente | `imported === null ? <Loading /> : ...` |
| `app/sets/page.tsx` | `sets === null` → griglia vuota | `sets === null ? <Loading /> : ...` |
| `app/shazam/page.tsx` | `sets === null` → EmptyState subito | `sets === null ? <Loading /> : ...` (EmptyState solo a lista davvero vuota) |
| `app/labels/page.tsx` | già `Equalizer` + testo inline (riga 76) | sostituisci con `<Loading />` |
| `app/tracks/[id]/page.tsx` | `Equalizer` + "Caricamento…" (riga 58) | sostituisci con `<Loading />` |
| `app/playlists/[id]/page.tsx` | idem (riga 205) | sostituisci con `<Loading />` |
| `app/downloads/page.tsx` | testo nudo "Ricerca su Soulseek…" (riga 153) | `<Loading label="Ricerca su Soulseek…" />` |
| `app/discovery/page.tsx` | `Spinner` + "DIG in corso…" (riga 258) | `<Loading label="DIG in corso…" />` |

Per ciascuna pagina: import `Loading` da `@/components/ui`, applica, controlla a vista. NON toccare gli spinner nei bottoni (`<Spinner />` dentro `Button`: quello è feedback d'azione, non caricamento pagina).

- [ ] **Step 3: Verifica** — `npm run build` + `npm run lint` (warning ≤ 13); visiva con backend spento: ogni pagina mostra il Loading e poi l'errore, mai il bianco.
- [ ] **Step 4: Commit** — `git commit -m "feat: stati di caricamento uniformi (componente Loading)"`
