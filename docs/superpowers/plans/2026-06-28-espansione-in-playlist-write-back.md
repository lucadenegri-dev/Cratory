# Espansione playlist nel contesto Playlist + write-back Spotify — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Spostare "Espandi playlist" dal Discovery a una pagina dedicata nel contesto playlist (`/playlists/[id]/expand`) e far sì che "Aggiungi" attacchi il brano a quella playlist, propagandolo su Spotify dove possibile.

**Architecture:** Cambio principalmente frontend/IA + un nuovo endpoint backend playlist-scoped. Discovery diventa solo DIG; la nuova pagina riusa i componenti di risultato spostati in un componente condiviso; un nuovo `POST /api/playlists/{id}/discovered-tracks` importa il candidato, lo attacca alla playlist locale e (best-effort) lo aggiunge alla playlist Spotify via un nuovo metodo `add_tracks`.

**Tech Stack:** Python 3 + FastAPI + Pydantic + SQLAlchemy (backend), pytest; Next.js 16 (App Router) + React + TypeScript (frontend).

## Global Constraints

- Expand deterministico; AI solo per le spiegazioni, opzionale e **off all'autorun**.
- Non si inventano dati: candidati risolti via Spotify resolver (identità/ISRC).
- Spotify: identità/metadata + **destinazione di scrittura** della playlist (scope `playlist-modify-private playlist-modify-public` già concessi).
- Write-back **best-effort, mai bloccante**: se fallisce, l'add locale resta riuscito.
- Edge 1:1 (`Track.playlist_id` singolo, many-to-many è backlog): non spostare una traccia già appartenente ad altra playlist; tentare comunque il write-back.
- Stile commit: nessun trailer `Co-Authored-By`.
- Comandi backend da `backend/` con venv attivo: `source .venv/bin/activate`.
- Next.js 16: leggere i param di route con `const { id } = use(params)` dove `params: Promise<{ id: string }>` (vedi `app/playlists/[id]/page.tsx`).

---

## File Structure

- `backend/app/integrations/spotify.py` — nuovo metodo `add_tracks(playlist_id, track_ids)`.
- `backend/app/schemas.py` — `PlaylistAddTrackRequest`, `PlaylistAddTrackResponse`.
- `backend/app/routers/playlists.py` — endpoint `POST /{playlist_id}/discovered-tracks`.
- `backend/tests/test_playlist_add_track.py` — test nuovi (chiamata diretta al router + fixture `db`).
- `frontend/lib/api.ts` — `addDiscoveredTrackToPlaylist` + tipo risposta.
- `frontend/components/expand-results.tsx` — `ExpandResults` (sposta `Results`/`CandidateRow`/`SOURCE_LABEL`).
- `frontend/app/playlists/[id]/expand/page.tsx` — nuova pagina (autorun senza AI).
- `frontend/app/discovery/page.tsx` — ridotto a solo DIG.
- `frontend/app/playlists/[id]/page.tsx` — bottone → `/playlists/[id]/expand`.

---

## Task 1: Backend — `SpotifyWebClient.add_tracks`

**Files:**
- Modify: `backend/app/integrations/spotify.py`
- Test: `backend/tests/test_playlist_add_track.py` (nuovo)

**Interfaces:**
- Produces: `SpotifyWebClient.add_tracks(self, playlist_id: str, track_ids: list[str]) -> None`
  (POST `/playlists/{playlist_id}/tracks` a chunk di 100, `user=True`).

- [ ] **Step 1: Scrivi il test fallito (registra le chiamate `_call`)**

Crea `backend/tests/test_playlist_add_track.py`:

```python
"""Test add-to-playlist + write-back Spotify (nessuna rete: client finto)."""

from app.integrations.spotify import SpotifyWebClient


def test_add_tracks_posts_uris_in_chunks(monkeypatch):
    calls = []
    monkeypatch.setattr(
        SpotifyWebClient, "_call",
        lambda self, method, path, **kw: calls.append((method, path, kw.get("json"))),
    )
    client = SpotifyWebClient.__new__(SpotifyWebClient)  # niente db: _call e' patchato
    client.add_tracks("PL123", ["a", "b", "c"])
    assert calls == [
        ("POST", "/playlists/PL123/tracks", {"uris": ["spotify:track:a", "spotify:track:b", "spotify:track:c"]}),
    ]
    # i chunk sono da 100: una sola chiamata per 3 tracce
    assert len(calls) == 1
```

- [ ] **Step 2: Esegui il test (fallisce)**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_playlist_add_track.py -k add_tracks -v`
Expected: FAIL — `AttributeError: ... has no attribute 'add_tracks'`.

- [ ] **Step 3: Implementa `add_tracks`**

In `backend/app/integrations/spotify.py`, subito dopo `create_playlist` (intorno alla riga 305):

```python
    def add_tracks(self, playlist_id: str, track_ids: list[str]) -> None:
        """Aggiunge tracce a una playlist esistente dell'utente (chunk da 100)."""
        uris = [f"spotify:track:{tid}" for tid in track_ids]
        for i in range(0, len(uris), 100):
            self._call("POST", f"/playlists/{playlist_id}/tracks", user=True,
                       json={"uris": uris[i:i + 100]})
```

- [ ] **Step 4: Esegui il test (passa)**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_playlist_add_track.py -k add_tracks -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/integrations/spotify.py backend/tests/test_playlist_add_track.py
git commit -m "feat(spotify): add_tracks per aggiungere tracce a una playlist esistente"
```

---

## Task 2: Backend — schema + endpoint `POST /{id}/discovered-tracks`

**Files:**
- Modify: `backend/app/schemas.py`
- Modify: `backend/app/routers/playlists.py`
- Test: `backend/tests/test_playlist_add_track.py`

**Interfaces:**
- Consumes: `add_tracks` (Task 1); `import_single_track` da `app.services.playlist_import`; `get_playlist` da `app.repositories`; `track_out` da `app.serializers`.
- Produces:
  - `PlaylistAddTrackRequest(artist, title, spotify_id, isrc, duration_seconds, url, album_art_url)`
  - `PlaylistAddTrackResponse(created: bool, track: TrackOut, spotify_added: bool, spotify_error: str | None)`
  - endpoint `POST /api/playlists/{playlist_id}/discovered-tracks` → `add_discovered_track(playlist_id, req, db)`

- [ ] **Step 1: Scrivi i test falliti del router**

Aggiungi in `backend/tests/test_playlist_add_track.py`:

```python
from app.integrations.spotify import SpotifyError, SpotifyWebClient
from app.models import Playlist, Track
from app.routers.playlists import add_discovered_track
from app.schemas import PlaylistAddTrackRequest


def _req(**kw):
    base = dict(artist="A", title="B", spotify_id="sp1", isrc="ISRC1",
                duration_seconds=200, url="http://u", album_art_url="http://img")
    base.update(kw)
    return PlaylistAddTrackRequest(**base)


def test_add_to_spotify_playlist_attaches_and_writes_back(db, monkeypatch):
    pl = Playlist(platform="spotify", platform_playlist_id="PLspot", name="Mine")
    db.add(pl); db.commit()
    called = {}
    monkeypatch.setattr(SpotifyWebClient, "add_tracks",
                        lambda self, pid, ids: called.update(pid=pid, ids=ids))

    resp = add_discovered_track(pl.id, _req(), db)
    assert resp.created is True
    assert resp.spotify_added is True and resp.spotify_error is None
    assert called == {"pid": "PLspot", "ids": ["sp1"]}
    t = db.query(Track).filter_by(spotify_id="sp1").one()
    assert t.playlist_id == pl.id


def test_add_to_manual_playlist_local_only(db, monkeypatch):
    pl = Playlist(platform="manual", name="Manuale")
    db.add(pl); db.commit()
    monkeypatch.setattr(SpotifyWebClient, "add_tracks",
                        lambda self, pid, ids: (_ for _ in ()).throw(AssertionError("non chiamare")))

    resp = add_discovered_track(pl.id, _req(), db)
    assert resp.created is True and resp.spotify_added is False and resp.spotify_error is None
    assert db.query(Track).filter_by(spotify_id="sp1").one().playlist_id == pl.id


def test_add_unresolved_candidate_local_only(db, monkeypatch):
    pl = Playlist(platform="spotify", platform_playlist_id="PLspot", name="Mine")
    db.add(pl); db.commit()
    monkeypatch.setattr(SpotifyWebClient, "add_tracks",
                        lambda self, pid, ids: (_ for _ in ()).throw(AssertionError("non chiamare")))

    resp = add_discovered_track(pl.id, _req(spotify_id=None), db)
    assert resp.spotify_added is False and resp.spotify_error is None


def test_write_back_failure_is_non_blocking(db, monkeypatch):
    pl = Playlist(platform="spotify", platform_playlist_id="PLspot", name="Mine")
    db.add(pl); db.commit()
    def boom(self, pid, ids): raise SpotifyError("Account Spotify non collegato")
    monkeypatch.setattr(SpotifyWebClient, "add_tracks", boom)

    resp = add_discovered_track(pl.id, _req(), db)
    assert resp.created is True and resp.spotify_added is False
    assert "Spotify" in resp.spotify_error
    assert db.query(Track).filter_by(spotify_id="sp1").one().playlist_id == pl.id


def test_add_does_not_move_track_from_other_playlist(db, monkeypatch):
    other = Playlist(platform="spotify", platform_playlist_id="PLother", name="Other")
    target = Playlist(platform="spotify", platform_playlist_id="PLtarget", name="Target")
    db.add_all([other, target]); db.commit()
    db.add(Track(source_type="spotify", platform="spotify", platform_track_id="sp1",
                 spotify_id="sp1", artist="A", title="B", playlist_id=other.id))
    db.commit()
    monkeypatch.setattr(SpotifyWebClient, "add_tracks", lambda self, pid, ids: None)

    resp = add_discovered_track(target.id, _req(), db)
    assert resp.created is False
    # membership locale NON spostata (modello 1:1), ma write-back tentato
    assert db.query(Track).filter_by(spotify_id="sp1").one().playlist_id == other.id
    assert resp.spotify_added is True
```

- [ ] **Step 2: Esegui i test (falliscono)**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_playlist_add_track.py -v`
Expected: FAIL — `ImportError: cannot import name 'add_discovered_track'` / `PlaylistAddTrackRequest`.

- [ ] **Step 3: Aggiungi gli schemi**

In `backend/app/schemas.py`, dopo `DiscoveryAddResponse` (o vicino agli altri schemi playlist):

```python
class PlaylistAddTrackRequest(BaseModel):
    """Aggiunge una traccia scoperta (expand) a una playlist specifica."""

    artist: str
    title: str
    spotify_id: str | None = None
    isrc: str | None = None
    duration_seconds: int | None = None
    album_art_url: str | None = None
    url: str | None = None


class PlaylistAddTrackResponse(BaseModel):
    created: bool
    track: TrackOut
    spotify_added: bool = False
    spotify_error: str | None = None
```

- [ ] **Step 4: Implementa l'endpoint**

In `backend/app/routers/playlists.py`:

(a) estendi gli import:

```python
from app.schemas import (
    GapAnalysisResponse,
    GapOut,
    ManualImportRequest,
    PlaylistAddTrackRequest,
    PlaylistAddTrackResponse,
    PlaylistImportReport,
    PlaylistImportRequest,
    PlaylistOut,
    SpotifyPlaylistRef,
    TrackOut,
)
from app.services.playlist_import import import_playlist, import_single_track
```

(b) aggiungi l'endpoint (dopo `playlist_tracks`, intorno alla riga 218):

```python
@router.post("/{playlist_id}/discovered-tracks", response_model=PlaylistAddTrackResponse)
def add_discovered_track(playlist_id: int, req: PlaylistAddTrackRequest, db: Session = Depends(get_db)):
    """Aggiunge una traccia scoperta a questa playlist; write-back Spotify best-effort."""
    playlist = get_playlist(db, playlist_id)
    if playlist is None:
        raise HTTPException(status_code=404, detail="Playlist non trovata")

    platform = "spotify" if req.spotify_id else "manual"
    track, created = import_single_track(
        db, platform=platform, platform_track_id=req.spotify_id,
        title=req.title, artist=req.artist, isrc=req.isrc,
        duration_seconds=req.duration_seconds, url=req.url, artwork_url=req.album_art_url,
    )

    # Attacca alla playlist locale solo se la traccia non appartiene gia' ad un'altra
    # playlist (modello 1:1: non "rubarla" alla sua playlist attuale).
    attached = False
    if track.playlist_id is None:
        track.playlist_id = playlist_id
        attached = True
        playlist.track_count = (playlist.track_count or 0) + 1
        db.commit()

    spotify_added = False
    spotify_error: str | None = None
    if req.spotify_id and playlist.platform == "spotify" and playlist.platform_playlist_id:
        try:
            SpotifyWebClient(db).add_tracks(playlist.platform_playlist_id, [req.spotify_id])
            spotify_added = True
        except SpotifyError as exc:
            spotify_error = str(exc)
            logger.warning("Write-back Spotify fallito per playlist %s: %s", playlist_id, exc)

    return PlaylistAddTrackResponse(
        created=created, track=track_out(track),
        spotify_added=spotify_added, spotify_error=spotify_error,
    )
```

Nota: `attached` non è esposto nella risposta (il client usa `created` + lo stato UI); resta come variabile locale che governa l'aggiornamento di `track_count`.

- [ ] **Step 5: Esegui i test (passano)**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_playlist_add_track.py -v`
Expected: PASS (6 test).

- [ ] **Step 6: Esegui l'intera suite backend (nessuna regressione)**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas.py backend/app/routers/playlists.py backend/tests/test_playlist_add_track.py
git commit -m "feat(playlists): endpoint add traccia scoperta a playlist + write-back Spotify"
```

---

## Task 3: Frontend — API client `addDiscoveredTrackToPlaylist`

**Files:**
- Modify: `frontend/lib/api.ts`

**Interfaces:**
- Consumes: endpoint `POST /api/playlists/{id}/discovered-tracks` (Task 2); tipo `DiscoveryCandidate` (già definito).
- Produces:
  - `interface PlaylistAddTrackResult { created: boolean; track: Track; spotify_added: boolean; spotify_error: string | null }`
  - `addDiscoveredTrackToPlaylist(playlistId: number, c: DiscoveryCandidate): Promise<PlaylistAddTrackResult>`

- [ ] **Step 1: Aggiungi tipo e funzione**

In `frontend/lib/api.ts`, dopo `discoveryAddToLibrary` (intorno alla riga 512):

```typescript
export interface PlaylistAddTrackResult {
  created: boolean;
  track: Track;
  spotify_added: boolean;
  spotify_error: string | null;
}

export function addDiscoveredTrackToPlaylist(playlistId: number, c: DiscoveryCandidate) {
  return apiPost<PlaylistAddTrackResult>(`/api/playlists/${playlistId}/discovered-tracks`, {
    artist: c.artist,
    title: c.title,
    spotify_id: c.spotify_id,
    isrc: c.isrc,
    duration_seconds: c.duration_seconds,
    album_art_url: c.album_art_url,
    url: c.spotify_url,
  });
}
```

(Verifica che `Track` sia già esportato in `lib/api.ts`; lo è — usato in `getPlaylist`/`playlistTracks`.)

- [ ] **Step 2: Type-check rapido**

Run: `cd frontend && npx tsc --noEmit`
Expected: nessun errore relativo a `lib/api.ts`.

- [ ] **Step 3: Commit**

```bash
git add frontend/lib/api.ts
git commit -m "feat(api): addDiscoveredTrackToPlaylist (add a playlist + write-back)"
```

---

## Task 4: Frontend — componente condiviso `ExpandResults`

**Files:**
- Create: `frontend/components/expand-results.tsx`

**Interfaces:**
- Consumes: `DiscoveryResponse`, `DiscoveryCandidate`, `addDiscoveredTrackToPlaylist`, `fmtDuration` da `@/lib/api`; componenti UI da `@/components/ui`.
- Produces: `export function ExpandResults({ result, playlistId }: { result: DiscoveryResponse; playlistId: number })`

- [ ] **Step 1: Crea il componente (sposta `Results`/`CandidateRow`/`SOURCE_LABEL`)**

Crea `frontend/components/expand-results.tsx`:

```tsx
"use client";

import { useState } from "react";
import { ExternalLink, Plus, Check, Compass, Music2 } from "lucide-react";
import {
  addDiscoveredTrackToPlaylist,
  fmtDuration,
  type DiscoveryResponse,
  type DiscoveryCandidate,
} from "@/lib/api";
import { Card, Badge, Button, EmptyState, Spinner } from "@/components/ui";

function err(e: unknown): string {
  return String((e as { message?: string })?.message ?? e);
}

const SOURCE_LABEL: Record<DiscoveryCandidate["source"], string> = {
  similar_artist: "artista affine",
  similar_track: "traccia affine",
  tag: "genere",
  label: "etichetta",
};

export function ExpandResults({ result, playlistId }: { result: DiscoveryResponse; playlistId: number }) {
  if (result.candidates.length === 0) {
    return (
      <EmptyState icon={<Compass size={28} />} title="Nessun suggerimento">
        La fonte di similarità non ha restituito tracce nuove per questa playlist.
      </EmptyState>
    );
  }
  return (
    <div>
      <h2 className="mb-3 text-sm font-medium uppercase tracking-wide text-muted">
        {result.candidates.length} suggerimenti · {result.scope}
      </h2>
      <div className="grid gap-2">
        {result.candidates.map((c, i) => (
          <CandidateRow key={`${c.artist}-${c.title}-${i}`} c={c} playlistId={playlistId} />
        ))}
      </div>
    </div>
  );
}

function CandidateRow({ c, playlistId }: { c: DiscoveryCandidate; playlistId: number }) {
  const [adding, setAdding] = useState(false);
  const [added, setAdded] = useState(false);
  const [onSpotify, setOnSpotify] = useState(false);
  const [addError, setAddError] = useState<string | null>(null);

  const add = async () => {
    setAdding(true);
    setAddError(null);
    try {
      const res = await addDiscoveredTrackToPlaylist(playlistId, c);
      setAdded(true);
      setOnSpotify(res.spotify_added);
    } catch (e) {
      setAddError(err(e));
    } finally {
      setAdding(false);
    }
  };

  return (
    <Card className="flex items-center gap-3 p-3">
      {c.album_art_url ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={c.album_art_url} alt="" className="h-12 w-12 shrink-0 rounded-none object-cover" />
      ) : (
        <div className="grid h-12 w-12 shrink-0 place-items-center rounded-none bg-elevated text-faint">
          <Music2 size={18} />
        </div>
      )}
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="truncate text-sm font-medium">{c.artist} — {c.title}</span>
          {c.label_owned && c.label && <Badge tone="neutral">↳ {c.label}</Badge>}
        </div>
        <div className="mt-0.5 flex items-center gap-2 text-xs text-faint">
          <span>{SOURCE_LABEL[c.source]}</span>
          {c.seed && c.source !== "label" && <span className="truncate">· da {c.seed}</span>}
          {c.duration_seconds != null && <span>· {fmtDuration(c.duration_seconds)}</span>}
          {added && onSpotify && <span>· anche su Spotify</span>}
        </div>
        {c.explanation && <p className="mt-1 text-xs text-muted">{c.explanation}</p>}
        {addError && <p className="mt-1 text-xs text-danger">⚠ {addError}</p>}
      </div>
      <div className="flex shrink-0 items-center gap-1.5">
        {c.spotify_url && (
          <a
            href={c.spotify_url}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1 rounded-none border border-border-strong px-2.5 py-1.5 text-xs font-medium text-fg transition-colors hover:bg-elevated"
          >
            <ExternalLink size={13} /> Spotify
          </a>
        )}
        <Button size="sm" variant={added ? "ghost" : "outline"} onClick={add} disabled={adding || added}>
          {added ? <><Check size={14} /> Aggiunto</> : adding ? <Spinner /> : <><Plus size={14} /> Aggiungi</>}
        </Button>
      </div>
    </Card>
  );
}
```

- [ ] **Step 2: Type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: nessun errore in `components/expand-results.tsx`.

- [ ] **Step 3: Commit**

```bash
git add frontend/components/expand-results.tsx
git commit -m "feat(expand): componente ExpandResults (add alla playlist + nota Spotify)"
```

---

## Task 5: Frontend — pagina `/playlists/[id]/expand`

**Files:**
- Create: `frontend/app/playlists/[id]/expand/page.tsx`

**Interfaces:**
- Consumes: `getPlaylist`, `discoverExpand`, `discoveryStatus` da `@/lib/api`; `ExpandResults` (Task 4); `PageLayout`, UI.

- [ ] **Step 1: Crea la pagina (autorun senza AI, toggle AI, Ricalcola)**

Crea `frontend/app/playlists/[id]/expand/page.tsx`:

```tsx
"use client";

import Link from "next/link";
import { use, useCallback, useEffect, useState } from "react";
import { ArrowLeft, Wand2, Compass } from "lucide-react";
import {
  getPlaylist, discoverExpand, discoveryStatus,
  type Playlist, type DiscoveryResponse, type DiscoveryStatus,
} from "@/lib/api";
import { Alert, Button, Checkbox, EmptyState, Spinner } from "@/components/ui";
import { PageLayout } from "@/components/page-layout";
import { ExpandResults } from "@/components/expand-results";

function err(e: unknown): string {
  return String((e as { message?: string })?.message ?? e);
}

export default function ExpandPlaylistPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const pid = Number(id);

  const [playlist, setPlaylist] = useState<Playlist | null>(null);
  const [status, setStatus] = useState<DiscoveryStatus | null>(null);
  const [useAi, setUseAi] = useState(false); // autorun senza AI
  const [result, setResult] = useState<DiscoveryResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const aiEnabled = useAi && !!status?.ai_explanations;

  const run = useCallback(async (withAi: boolean) => {
    setBusy(true);
    setError(null);
    try {
      setResult(await discoverExpand(pid, { use_ai: withAi }));
    } catch (e) {
      setError(err(e));
    } finally {
      setBusy(false);
    }
  }, [pid]);

  useEffect(() => {
    getPlaylist(pid).then(setPlaylist).catch((e) => setError(err(e)));
    discoveryStatus().then(setStatus).catch(() => setStatus(null));
    run(false); // autorun senza AI
  }, [pid, run]);

  const marginalia = (
    <div className="space-y-3">
      <Checkbox
        label={status?.ai_explanations ? "Spiega con l'AI" : "Spiegazioni AI (configura AI_API_KEY)"}
        checked={aiEnabled}
        onChange={setUseAi}
        disabled={busy || !status?.ai_explanations}
      />
      <Button size="sm" variant="outline" className="w-full" onClick={() => run(aiEnabled)} disabled={busy}>
        {busy ? <Spinner /> : <Wand2 size={15} />} Ricalcola
      </Button>
    </div>
  );

  return (
    <PageLayout title="Espandi" meta={playlist?.name} marginaliaTitle="Opzioni" marginalia={marginalia}>
      <Link href={`/playlists/${pid}`} className="mb-4 inline-flex items-center gap-1.5 text-sm text-muted hover:text-fg">
        <ArrowLeft size={15} /> {playlist?.name ?? "Playlist"}
      </Link>

      {error && <Alert tone="danger">⚠ {error}</Alert>}

      {status && !status.configured && (
        <div className="mb-6">
          <Alert tone="info">
            Discovery non configurato: imposta <code className="font-mono">LASTFM_API_KEY</code> in
            <span className="font-medium"> backend/.env</span> (chiave gratuita su last.fm/api).
          </Alert>
        </div>
      )}

      {busy && !result && (
        <div className="flex items-center gap-2 text-sm text-muted"><Spinner /> Cerco tracce affini…</div>
      )}
      {result && <ExpandResults result={result} playlistId={pid} />}
      {!busy && !result && !error && (
        <EmptyState icon={<Compass size={28} />} title="Pronto per l'espansione">
          Premi “Ricalcola” per cercare tracce di gusto affine a questa playlist.
        </EmptyState>
      )}
    </PageLayout>
  );
}
```

Nota: verifica le prop di `PageLayout` (`title`, `meta`, `marginaliaTitle`, `marginalia`) come usate in `app/playlists/[id]/page.tsx`; se `meta` non accetta `undefined`, passare `meta={playlist?.name ?? ""}`.

- [ ] **Step 2: Type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: nessun errore in `app/playlists/[id]/expand/page.tsx`.

- [ ] **Step 3: Commit**

```bash
git add frontend/app/playlists/[id]/expand/page.tsx
git commit -m "feat(playlists): pagina dedicata espansione (autorun senza AI)"
```

---

## Task 6: Frontend — Discovery solo DIG + bottone playlist

**Files:**
- Modify: `frontend/app/discovery/page.tsx`
- Modify: `frontend/app/playlists/[id]/page.tsx`

**Interfaces:**
- Consumes: niente di nuovo. Rimuove l'uso di `discoverExpand`, `discoveryAddToLibrary`, `DiscoveryResponse`, `DiscoveryCandidate`, `Results`/`CandidateRow` (spostati in Task 4).

- [ ] **Step 1: Cambia il bottone nel dettaglio playlist**

In `frontend/app/playlists/[id]/page.tsx:233`, sostituisci:

```tsx
      <Link href="/discovery" className="block"><Button size="sm" variant="outline" className="w-full"><Compass size={15} /> Scopri musica simile</Button></Link>
```

con:

```tsx
      <Link href={`/playlists/${pid}/expand`} className="block"><Button size="sm" variant="outline" className="w-full"><Compass size={15} /> Scopri musica simile</Button></Link>
```

- [ ] **Step 2: Riduci `app/discovery/page.tsx` a solo DIG**

Applica queste modifiche in `frontend/app/discovery/page.tsx`:

(a) **Import** — rimuovi i simboli ora inutilizzati. Lascia solo ciò che serve al DIG. La lista import diventa:

```tsx
import { useEffect, useState } from "react";
import { ExternalLink, Music2, Plus, Check, Disc3, Search, Tags } from "lucide-react";
import {
  discoveryDig,
  discoveryAddLead,
  getDiscoveryGenres,
  listImportedPlaylists,
  getLabels,
  type DiscoveryDigResponse,
  type DiscoveryLead,
  type Reason,
  type DiscoveryGenres,
  type Playlist,
  type LabelStats,
} from "@/lib/api";
import { Card, Alert, Button, EmptyState, Spinner, Select, Input } from "@/components/ui";
import { PageLayout } from "@/components/page-layout";
import { useJobs } from "@/components/jobs-provider";
import { cn } from "@/lib/cn";
```

(Verifica a fine task con tsc/lint che nessuno di questi sia di troppo o mancante; aggiusta se serve. `Music2`, `Plus`, `Check`, `Search`, `ExternalLink` restano usati dai `LeadRow`.)

(b) **Tipo `Mode` e stato expand** — rimuovi:
- `type Mode = "expand" | "dig";`
- `const [mode, setMode] = useState<Mode>("dig");`
- `const [playlistId, setPlaylistId] = useState<number | null>(null);`
- `const [useAi, setUseAi] = useState(true);`
- `const [result, setResult] = useState<DiscoveryResponse | null>(null);`
- `const SOURCE_LABEL = ...` (spostato in Task 4)
- `const aiEnabled = ...`
- la funzione `switchMode`
- la funzione `runExpand`
- le derivate `noPlaylists`, `expandReady`

(c) **Effect** — `listImportedPlaylists()` resta (serve al selettore "Affinità rispetto a"); rimuovi solo l'assegnazione `setPlaylistId(pls[0].id)`:

```tsx
    listImportedPlaylists()
      .then(setPlaylists)
      .catch((e) => setError(err(e)));
```

(d) **Mode toggle** — rimuovi l'intero blocco `{/* Mode toggle */} <div ...> ... </div>` (le due voci dig/expand) e il `<p>` introduttivo cambialo in:

```tsx
      <p className="mb-4 text-sm text-muted">Scava nuova musica per genere o etichetta.</p>
```

(e) **Branch dig** — togli il wrapper condizionale `{mode === "dig" && ( <> ... </> )}` lasciando il contenuto sempre renderizzato (era il primo blocco). In pratica il JSX del dig diventa il corpo diretto del `PageLayout`.

(f) **Branch expand** — rimuovi tutto il blocco `{/* ESPANDI PLAYLIST */} {mode === "expand" && ( ... )}`.

(g) **Componenti** — rimuovi le funzioni `Results` e `CandidateRow` (spostate in Task 4). Mantieni `Chip`, `LeadResults`, `LeadRow`, `reasonLabel`.

- [ ] **Step 3: Lint + build**

Run: `cd frontend && npm run lint && npm run build`
Expected: 0 errori (warning `<img>` preesistenti ok); `/discovery` e `/playlists/[id]/expand` compilano.

- [ ] **Step 4: Commit**

```bash
git add frontend/app/discovery/page.tsx frontend/app/playlists/[id]/page.tsx
git commit -m "refactor(discovery): Discovery solo DIG; espansione lanciata dal dettaglio playlist"
```

---

## Task 7: Verifica nel browser + documentazione

**Files:**
- Modify: `docs/ROADMAP.md`, `PROGRESS.md`, `docs/API.md`

- [ ] **Step 1: Verifica nel browser (preview)**

Avvia il preview frontend (assicurati che il backend giri sul codice nuovo, porta 8000). Verifica:
1. `/discovery` mostra solo il flusso DIG (niente switcher DIG/Espandi).
2. Dal dettaglio di una playlist Spotify, "Scopri musica simile" porta a `/playlists/[id]/expand`, che **autoparte senza AI** e mostra i suggerimenti.
3. "Aggiungi" su un candidato → bottone passa a "Aggiunto"; per una playlist Spotify posseduta compare la nota "anche su Spotify".
Cattura uno screenshot come prova.

- [ ] **Step 2: Aggiorna ROADMAP**

In `docs/ROADMAP.md`, sotto "Stato completato" aggiungi:

```markdown
- Discovery solo DIG: l'espansione playlist è stata spostata nel contesto Playlist
  (pagina dedicata `/playlists/[id]/expand`, autorun senza AI). "Aggiungi" attacca il
  brano a quella playlist e, dove possibile, lo propaga sulla playlist Spotify
  (write-back best-effort).
```

- [ ] **Step 3: Aggiorna PROGRESS**

In `PROGRESS.md` aggiungi una milestone datata 2026-06-28 che riassume: nuovo endpoint `POST /api/playlists/{id}/discovered-tracks`, `add_tracks` su SpotifyWebClient, pagina expand, Discovery ridotto a DIG, bottone playlist. Aggiorna "Ultimo aggiornamento" a 2026-06-28.

- [ ] **Step 4: Aggiorna API.md**

In `docs/API.md`, nella sezione playlist, documenta `POST /api/playlists/{id}/discovered-tracks` (request = artist/title/spotify_id/isrc/duration/url/album_art_url; response = created/track/spotify_added/spotify_error). Nella sezione Discovery, nota che l'expand ora si lancia dal dettaglio playlist (l'endpoint `/api/discovery/expand` resta invariato).

- [ ] **Step 5: Suite backend finale**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add docs/ROADMAP.md PROGRESS.md docs/API.md
git commit -m "docs(status): espansione nel contesto playlist + write-back Spotify"
```

---

## Self-Review (eseguita)

**Spec coverage:**
- Pagina dedicata `/playlists/[id]/expand` + autorun senza AI → Task 5.
- Discovery solo DIG → Task 6.
- Bottone playlist → `/playlists/[id]/expand` → Task 6.
- Componente condiviso `ExpandResults` (sposta Results/CandidateRow/SOURCE_LABEL) → Task 4.
- Endpoint add-to-playlist + write-back + matrice → Task 2.
- `SpotifyWebClient.add_tracks` → Task 1.
- Schemi `PlaylistAddTrackRequest/Response` → Task 2.
- API client `addDiscoveredTrackToPlaylist` → Task 3.
- Edge 1:1 (non spostare, write-back comunque) → Task 2 (test `test_add_does_not_move_track_from_other_playlist`).
- Write-back non bloccante → Task 2 (test `test_write_back_failure_is_non_blocking`).
- Dedup best-effort UI ("Aggiunto") → Task 4.
- Docs → Task 7.

**Placeholder scan:** nessun TBD/TODO; ogni step di codice mostra il codice.

**Type consistency:** `add_tracks(playlist_id, track_ids)`, `PlaylistAddTrackRequest/Response`, `add_discovered_track(playlist_id, req, db)`, `addDiscoveredTrackToPlaylist(playlistId, c)`, `PlaylistAddTrackResult`, `ExpandResults({result, playlistId})` coerenti tra i task. Campi risposta (`created`, `track`, `spotify_added`, `spotify_error`) identici tra schema backend e tipo frontend.
