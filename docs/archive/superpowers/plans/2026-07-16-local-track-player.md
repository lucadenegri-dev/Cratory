# Player audio tracce possedute — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Riprodurre in-app (audizione rapida: play/pausa/seek, una traccia per volta) i file audio delle tracce che l'utente possiede su disco (`has_local_file=true`), da qualunque riga-traccia.

**Architecture:** Un endpoint backend `GET /api/tracks/{id}/audio` serve il file locale in sola lettura via `FileResponse` (Range/seek nativi), con un controllo di sicurezza che confina il path alle cartelle consentite. Sul frontend, il player preview di Discovery viene generalizzato in **un unico player docked condiviso** (sorgente = preview di terzi *oppure* traccia locale), montato nell'app shell, più un componente `<TrackPlayButton>` riusabile.

**Tech Stack:** Backend FastAPI + Starlette `FileResponse`, SQLAlchemy, pytest (+ `TestClient` per Range). Frontend Next.js 16 / React, context+hook, vitest + Testing Library.

## Global Constraints

- **Sola lettura del disco.** Il file non viene MAI modificato (i tag restano di Sortory). Coerente con "the library is the disk".
- **Nessuna transcodifica.** Stream raw; i formati non riproducibili dal browser mostrano un messaggio, non aggiungiamo ffmpeg.
- **Nessuna dipendenza nuova** (backend o frontend).
- **Sicurezza path:** l'endpoint accetta solo `track_id`; il path servito deve risolvere dentro le root di `file_search.search_roots()` (`LIBRARY_ROOT` + download slskd). Mai un path da input utente.
- **Un player alla volta:** una sola sorgente audio attiva; far partire una sorgente sostituisce la precedente.
- **Stile commit del progetto:** niente `Co-Authored-By`, messaggi in italiano come lo storico.
- **i18n:** ogni stringa UI va sia in `lib/i18n/it.ts` sia in `lib/i18n/en.ts` (il tipo `Dictionary` deriva da `en.ts`; `it.ts` deve conformarsi).
- **Docs dopo il codice:** l'allineamento dei docs (Task 7) è l'ultimo task, ma è in scope e non va saltato.

Comandi:
- Backend test: `cd backend && source .venv/bin/activate && python -m pytest tests/<file> -v`
- Frontend unit test: `cd frontend && npx vitest run tests/<file>`
- Frontend build/lint: `cd frontend && npm run build` / `npm run lint`

---

## File Structure

**Backend**
- Modifica `backend/app/services/file_search.py` — nuovo helper puro `path_within_roots`.
- Modifica `backend/app/routers/tracks.py` — nuovo endpoint `GET /tracks/{id}/audio`.
- Crea `backend/tests/test_track_audio.py` — test helper + endpoint.

**Frontend**
- Rinomina `lib/preview-player.tsx` → `lib/player.tsx` — context generico (`PlayerProvider`, `usePlayer`, `PlaybackSource`).
- Rinomina `components/docked-preview-player.tsx` → `components/docked-player.tsx` — barra unica (preview + locale).
- Crea `components/track-play-button.tsx` — bottone riusabile.
- Modifica `lib/api/tracks.ts` — helper `trackAudioUrl`.
- Modifica `lib/i18n/it.ts` + `lib/i18n/en.ts` — blocco `player`.
- Modifica `app/discovery/page.tsx`, `components/discovery-lead-grid.tsx`, `components/discovery-tracklist-panel.tsx` — migrazione all'hook/firma nuovi.
- Modifica `app/layout.tsx` — mount globale del player.
- Modifica `components/track-state-icons.tsx`, `app/tracks/[id]/page.tsx` — innesto del play button.
- Rinomina `tests/preview-player.test.tsx` → `tests/player.test.tsx`; crea `tests/track-play-button.test.tsx`.

**Docs**
- `CLAUDE.md`, `docs/API.md`, `docs/ARCHITECTURE.md`, `docs/ROADMAP.md`, `PROGRESS.md`.

---

## Task 1: Helper di sicurezza `path_within_roots` (backend)

**Files:**
- Modify: `backend/app/services/file_search.py`
- Test: `backend/tests/test_track_audio.py` (creazione)

**Interfaces:**
- Produces: `path_within_roots(path: Path, roots: list[str]) -> bool` — `True` se `path`, risolto, è contenuto in una delle `roots` (risolte). `False` con `roots` vuota, path fuori root, symlink verso l'esterno o path non risolvibile.

- [ ] **Step 1: Scrivi i test che falliscono**

Crea `backend/tests/test_track_audio.py`:

```python
"""Player tracce possedute: sicurezza del path e endpoint di streaming."""
from pathlib import Path

from app.services.file_search import path_within_roots


def test_path_within_roots_accetta_file_dentro_la_root(tmp_path):
    f = tmp_path / "song.mp3"
    f.write_bytes(b"x")
    assert path_within_roots(f, [str(tmp_path)]) is True


def test_path_within_roots_rifiuta_file_fuori_dalla_root(tmp_path):
    root = tmp_path / "library"
    root.mkdir()
    outside = tmp_path / "secret.mp3"
    outside.write_bytes(b"x")
    assert path_within_roots(outside, [str(root)]) is False


def test_path_within_roots_rifiuta_traversal(tmp_path):
    root = tmp_path / "library"
    root.mkdir()
    outside = tmp_path / "secret.mp3"
    outside.write_bytes(b"x")
    traversal = root / ".." / "secret.mp3"
    assert path_within_roots(traversal, [str(root)]) is False


def test_path_within_roots_rifiuta_symlink_verso_esterno(tmp_path):
    root = tmp_path / "library"
    root.mkdir()
    outside = tmp_path / "secret.mp3"
    outside.write_bytes(b"x")
    link = root / "link.mp3"
    link.symlink_to(outside)
    assert path_within_roots(link, [str(root)]) is False


def test_path_within_roots_con_roots_vuota_e_falso(tmp_path):
    f = tmp_path / "song.mp3"
    f.write_bytes(b"x")
    assert path_within_roots(f, []) is False
```

- [ ] **Step 2: Esegui i test — devono fallire**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_track_audio.py -v`
Expected: FAIL con `ImportError: cannot import name 'path_within_roots'`.

- [ ] **Step 3: Implementa l'helper**

In `backend/app/services/file_search.py`, dopo `search_roots()`, aggiungi:

```python
def path_within_roots(path: Path, roots: list[str]) -> bool:
    """True se `path`, risolto, è contenuto in una delle `roots` (anch'esse risolte).
    Difesa contro traversal/symlink verso file fuori dalle cartelle consentite.
    Segue i symlink (resolve): un link dentro root ma che punta fuori è rifiutato.
    Con `roots` vuota ritorna sempre False."""
    try:
        resolved = path.resolve()
    except OSError:
        return False
    for root in roots:
        try:
            resolved.relative_to(Path(root).resolve())
            return True
        except ValueError:
            continue
    return False
```

- [ ] **Step 4: Esegui i test — devono passare**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_track_audio.py -v`
Expected: PASS (5 test).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/file_search.py backend/tests/test_track_audio.py
git commit -m "feat(files): helper path_within_roots per confinare i file alle root consentite"
```

---

## Task 2: Endpoint `GET /api/tracks/{id}/audio` (backend)

**Files:**
- Modify: `backend/app/routers/tracks.py`
- Test: `backend/tests/test_track_audio.py` (append)

**Interfaces:**
- Consumes: `path_within_roots` (Task 1), `search_roots` (esistente), `get_track`, `api_error`.
- Produces: rotta `GET /api/tracks/{track_id}/audio` → `FileResponse` (200; 206 su header `Range`). Errori `404` con `detail["code"]`: `track_not_found`, `track_no_local_file`, `track_file_not_allowed`, `track_file_missing`.

- [ ] **Step 1: Scrivi i test che falliscono**

Append a `backend/tests/test_track_audio.py`:

```python
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.db import Base, get_db
from app.main import app
from app.models import Track
from app.routers import tracks


def _owned_track(db, path: str) -> Track:
    t = Track(source_type="local_files", platform="local_files", platform_track_id="d1",
              title="T", artist="A", has_local_file=True, local_path=path)
    db.add(t)
    db.commit()
    return t


def test_audio_404_se_traccia_inesistente(db):
    with pytest.raises(HTTPException) as ei:
        tracks.get_track_audio(9999, db)
    assert ei.value.status_code == 404
    assert ei.value.detail["code"] == "track_not_found"


def test_audio_404_se_non_posseduta(db):
    t = Track(source_type="spotify", title="T", artist="A", has_local_file=False)
    db.add(t); db.commit()
    with pytest.raises(HTTPException) as ei:
        tracks.get_track_audio(t.id, db)
    assert ei.value.status_code == 404
    assert ei.value.detail["code"] == "track_no_local_file"


def test_audio_404_se_path_fuori_root(db, tmp_path, monkeypatch):
    root = tmp_path / "library"; root.mkdir()
    outside = tmp_path / "secret.mp3"; outside.write_bytes(b"data")
    monkeypatch.setattr(settings, "library_root", str(root))
    monkeypatch.setattr(settings, "slskd_download_dir", "")
    t = _owned_track(db, str(outside))
    with pytest.raises(HTTPException) as ei:
        tracks.get_track_audio(t.id, db)
    assert ei.value.status_code == 404
    assert ei.value.detail["code"] == "track_file_not_allowed"


def test_audio_404_se_file_mancante(db, tmp_path, monkeypatch):
    root = tmp_path / "library"; root.mkdir()
    monkeypatch.setattr(settings, "library_root", str(root))
    monkeypatch.setattr(settings, "slskd_download_dir", "")
    t = _owned_track(db, str(root / "ghost.mp3"))  # dentro root ma non esiste
    with pytest.raises(HTTPException) as ei:
        tracks.get_track_audio(t.id, db)
    assert ei.value.status_code == 404
    assert ei.value.detail["code"] == "track_file_missing"


@pytest.fixture()
def client_db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    app.dependency_overrides[get_db] = lambda: session
    try:
        yield TestClient(app), session
    finally:
        app.dependency_overrides.pop(get_db, None)
        session.close()


def test_audio_200_serve_il_file(client_db, tmp_path, monkeypatch):
    client, db = client_db
    root = tmp_path / "library"; root.mkdir()
    f = root / "song.mp3"; f.write_bytes(b"ABCDEFGHIJ")
    monkeypatch.setattr(settings, "library_root", str(root))
    monkeypatch.setattr(settings, "slskd_download_dir", "")
    t = _owned_track(db, str(f))
    r = client.get(f"/api/tracks/{t.id}/audio")
    assert r.status_code == 200
    assert r.content == b"ABCDEFGHIJ"
    assert r.headers["content-type"] == "audio/mpeg"


def test_audio_206_su_range_request(client_db, tmp_path, monkeypatch):
    client, db = client_db
    root = tmp_path / "library"; root.mkdir()
    f = root / "song.mp3"; f.write_bytes(b"ABCDEFGHIJ")
    monkeypatch.setattr(settings, "library_root", str(root))
    monkeypatch.setattr(settings, "slskd_download_dir", "")
    t = _owned_track(db, str(f))
    r = client.get(f"/api/tracks/{t.id}/audio", headers={"Range": "bytes=0-3"})
    assert r.status_code == 206
    assert r.content == b"ABCD"
    assert "content-range" in {k.lower() for k in r.headers}
```

- [ ] **Step 2: Esegui i test — devono fallire**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_track_audio.py -v`
Expected: FAIL (`AttributeError: module 'app.routers.tracks' has no attribute 'get_track_audio'` e 404 mancanti).

- [ ] **Step 3: Implementa l'endpoint**

In `backend/app/routers/tracks.py`, aggiungi agli import in cima:

```python
from fastapi.responses import FileResponse
from app.services.file_search import path_within_roots, search_roots
```

Poi, subito dopo la funzione `get_track_cover`, aggiungi:

```python
# Content-Type per estensione: `mimetypes` non conosce bene .flac/.aiff, quindi
# mappiamo esplicitamente i formati audio comuni; fallback binario generico.
_AUDIO_MIME = {
    ".mp3": "audio/mpeg", ".m4a": "audio/mp4", ".mp4": "audio/mp4", ".aac": "audio/aac",
    ".flac": "audio/flac", ".wav": "audio/wav", ".aif": "audio/aiff", ".aiff": "audio/aiff",
    ".ogg": "audio/ogg", ".opus": "audio/ogg",
}


@router.get("/tracks/{track_id}/audio")
def get_track_audio(track_id: int, db: Session = Depends(get_db)):
    """Streaming del file locale di una traccia posseduta, per audizione rapida.
    Sola lettura: il file non viene MAI modificato. `FileResponse` gestisce le
    Range request (seek) e risponde 206 al `Range`. 404 se la traccia non esiste,
    non è posseduta, il file risolve fuori dalle cartelle consentite o è mancante."""
    track = get_track(db, track_id)
    if track is None:
        raise api_error(404, "track_not_found", "Track not found")
    if not track.has_local_file or not track.local_path:
        raise api_error(404, "track_no_local_file", "Track has no local file")
    path = Path(track.local_path)
    roots = [root for _, root in search_roots()]
    if not path_within_roots(path, roots):
        raise api_error(404, "track_file_not_allowed", "File outside allowed roots")
    if not path.exists():
        raise api_error(404, "track_file_missing", "File not found")
    media_type = _AUDIO_MIME.get(path.suffix.lower(), "application/octet-stream")
    return FileResponse(path, media_type=media_type)
```

- [ ] **Step 4: Esegui i test — devono passare**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_track_audio.py -v`
Expected: PASS (11 test totali nel file).

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/tracks.py backend/tests/test_track_audio.py
git commit -m "feat(tracks): endpoint GET /api/tracks/{id}/audio (stream file posseduto, Range/seek, read-only)"
```

---

## Task 3: Player unico condiviso — context + barra docked + i18n (frontend)

**Files:**
- Rename+rewrite: `frontend/lib/preview-player.tsx` → `frontend/lib/player.tsx`
- Rename+rewrite: `frontend/components/docked-preview-player.tsx` → `frontend/components/docked-player.tsx`
- Modify: `frontend/lib/api/tracks.ts` (helper `trackAudioUrl`)
- Modify: `frontend/lib/i18n/en.ts`, `frontend/lib/i18n/it.ts` (blocco `player`)
- Modify: `frontend/components/discovery-lead-grid.tsx`, `frontend/components/discovery-tracklist-panel.tsx`, `frontend/app/discovery/page.tsx`
- Rename+update: `frontend/tests/preview-player.test.tsx` → `frontend/tests/player.test.tsx`

**Interfaces:**
- Produces: `PlayerProvider`, `usePlayer(): { active: PlaybackSource | null; status; data; play; stop }`, tipi `PlaybackSource`, `PreviewItem`, `LocalTrack` da `@/lib/player`; `DockedPlayer` da `@/components/docked-player`; `trackAudioUrl(id: number): string` da `@/lib/api`.
- `PlaybackSource = { kind: "discovery-preview"; item: PreviewItem } | { kind: "local-track"; track: LocalTrack }`.
- `LocalTrack = { id: number; title: string; artist: string }`.

- [ ] **Step 1: Aggiorna il test esistente (deve fallire con i nomi nuovi)**

Rinomina il file e aggiorna import/firme:

```bash
cd frontend && git mv tests/preview-player.test.tsx tests/player.test.tsx
```

In `tests/player.test.tsx` sostituisci gli import e le chiamate `play`:
- import: `import { DockedPlayer } from "@/components/docked-player";` e `import { PlayerProvider, usePlayer } from "@/lib/player";`
- `const p = usePreviewPlayer();` → `const p = usePlayer();`
- `<PreviewPlayerProvider>` → `<PlayerProvider>`, `</PreviewPlayerProvider>` → `</PlayerProvider>`
- `<DockedPreviewPlayer />` → `<DockedPlayer />`
- Ogni `p.play({ key: ..., artist: ..., title: ..., discogsId: ..., level: ..., label: ... })` diventa:
  `p.play({ kind: "discovery-preview", item: { key: ..., artist: ..., title: ..., discogsId: ..., level: ..., label: ... } })`

Esempio delle due chiamate nel `Harness`:

```tsx
<button onClick={() => p.play({ kind: "discovery-preview", item: { key: "a", artist: "Artist", title: "Acid Trip", discogsId: 42, level: "track", label: "Acid Trip" } })}>
  play-a
</button>
<button onClick={() => p.play({ kind: "discovery-preview", item: { key: "b", artist: "Artist", title: "Other", discogsId: 42, level: "track", label: "Other" } })}>
  play-b
</button>
```

E nel test "supersedes", `resolveA(...)` resta invariato (è il valore risolto della fetch, non una `play`). Le asserzioni su `preview-audio`/`preview-iframe`/`status` restano identiche.

- [ ] **Step 2: Esegui il test — deve fallire**

Run: `cd frontend && npx vitest run tests/player.test.tsx`
Expected: FAIL (moduli `@/lib/player` e `@/components/docked-player` inesistenti).

- [ ] **Step 3: Crea il context generico `lib/player.tsx`**

```bash
cd frontend && git mv lib/preview-player.tsx lib/player.tsx
```

Sostituisci l'intero contenuto di `lib/player.tsx` con:

```tsx
"use client";

import { createContext, useCallback, useContext, useRef, useState } from "react";

import { discoveryPreview, type DiscoveryPreview } from "@/lib/api";

export type PreviewItem = {
  key: string;
  artist: string;
  title: string;
  discogsId: number | null;
  level: "release" | "track";
  label: string;
};

export type LocalTrack = {
  id: number;
  title: string;
  artist: string;
};

export type PlaybackSource =
  | { kind: "discovery-preview"; item: PreviewItem }
  | { kind: "local-track"; track: LocalTrack };

type Status = "idle" | "loading" | "playing" | "unavailable";

type Ctx = {
  active: PlaybackSource | null;
  status: Status;
  data: DiscoveryPreview | null;
  play: (source: PlaybackSource) => void;
  stop: () => void;
};

const PlayerCtx = createContext<Ctx | null>(null);

export function PlayerProvider({ children }: { children: React.ReactNode }) {
  const [active, setActive] = useState<PlaybackSource | null>(null);
  const [status, setStatus] = useState<Status>("idle");
  const [data, setData] = useState<DiscoveryPreview | null>(null);
  const reqId = useRef(0);

  const play = useCallback((source: PlaybackSource) => {
    const id = ++reqId.current; // invalida qualunque risoluzione preview in volo
    setActive(source);
    setData(null);
    if (source.kind === "local-track") {
      setStatus("playing"); // stream diretto: nessuna risoluzione async
      return;
    }
    // discovery-preview: risoluzione async della sorgente di terzi (iTunes/YouTube)
    setStatus("loading");
    const item = source.item;
    discoveryPreview({ artist: item.artist, title: item.title, discogsId: item.discogsId, level: item.level })
      .then((res) => {
        if (id !== reqId.current) return; // richiesta superata da un nuovo play
        setData(res);
        setStatus(res.kind === "none" ? "unavailable" : "playing");
      })
      .catch(() => {
        if (id !== reqId.current) return;
        setStatus("unavailable");
      });
  }, []);

  const stop = useCallback(() => {
    reqId.current++;
    setActive(null);
    setStatus("idle");
    setData(null);
  }, []);

  return <PlayerCtx.Provider value={{ active, status, data, play, stop }}>{children}</PlayerCtx.Provider>;
}

export function usePlayer(): Ctx {
  const ctx = useContext(PlayerCtx);
  if (!ctx) throw new Error("usePlayer must be used within PlayerProvider");
  return ctx;
}
```

- [ ] **Step 4: Aggiungi l'helper `trackAudioUrl`**

In `frontend/lib/api/tracks.ts`, dopo `trackCoverSrc`, aggiungi:

```ts
/** URL di streaming del file locale di una traccia posseduta (audizione rapida). */
export function trackAudioUrl(id: number): string {
  return `${API}/api/tracks/${id}/audio`;
}
```

(`API` è già importato in cima al file.)

- [ ] **Step 5: Aggiungi il blocco i18n `player`**

In `frontend/lib/i18n/en.ts`, aggiungi una nuova proprietà top-level `player` all'oggetto dizionario (accanto a `discovery`):

```ts
  player: {
    play: "Play",
    stop: "Stop",
    close: "Close player",
    unsupportedFormat: "Format not playable in the browser",
  },
```

In `frontend/lib/i18n/it.ts`, aggiungi la corrispondente (stesse chiavi):

```ts
  player: {
    play: "Ascolta",
    stop: "Ferma",
    close: "Chiudi player",
    unsupportedFormat: "Formato non riproducibile nel browser",
  },
```

- [ ] **Step 6: Crea la barra docked `components/docked-player.tsx`**

```bash
cd frontend && git mv components/docked-preview-player.tsx components/docked-player.tsx
```

Sostituisci l'intero contenuto di `components/docked-player.tsx` con:

```tsx
"use client";

import { useEffect, useState } from "react";
import { X } from "lucide-react";

import { trackAudioUrl } from "@/lib/api";
import { useT } from "@/lib/i18n";
import { usePlayer } from "@/lib/player";

export function DockedPlayer() {
  const { active, status, data, stop } = usePlayer();
  const t = useT();
  // Errore di riproduzione del file locale (formato non supportato dal browser
  // o file sparito): stato locale, si azzera quando cambia la traccia attiva.
  const [localError, setLocalError] = useState(false);
  const activeLocalId = active?.kind === "local-track" ? active.track.id : null;
  useEffect(() => {
    setLocalError(false);
  }, [activeLocalId]);

  if (!active || status === "idle") return null;

  const title = active.kind === "local-track" ? active.track.title : active.item.title;
  const artist = active.kind === "local-track" ? active.track.artist : active.item.artist;

  return (
    <div className="fixed bottom-4 right-4 z-[60] w-80 max-w-[calc(100vw-2rem)] rounded-none border border-border-strong bg-surface p-3">
      <div className="mb-2 flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="truncate text-sm text-fg">{title}</div>
          <div className="truncate text-xs text-faint">{artist}</div>
        </div>
        <button aria-label={t.player.close} onClick={stop} className="shrink-0 text-faint hover:text-fg">
          <X size={16} />
        </button>
      </div>

      {active.kind === "local-track" &&
        (localError ? (
          <div className="py-2 text-xs text-faint">{t.player.unsupportedFormat}</div>
        ) : (
          <audio
            data-testid="local-audio"
            src={trackAudioUrl(active.track.id)}
            controls
            autoPlay
            onError={() => setLocalError(true)}
            className="w-full"
          />
        ))}

      {active.kind === "discovery-preview" && (
        <>
          {status === "loading" && <div className="py-2 text-xs text-faint">{t.discovery.previewLoading}</div>}
          {status === "unavailable" && <div className="py-2 text-xs text-faint">{t.discovery.noPreview}</div>}
          {status === "playing" && data?.kind === "itunes" && data.audio_url && (
            <audio data-testid="preview-audio" src={data.audio_url} controls autoPlay className="w-full" />
          )}
          {status === "playing" && data?.kind === "youtube" && data.youtube_video_id && (
            <div className="aspect-video w-full overflow-hidden">
              <iframe
                data-testid="preview-iframe"
                className="h-full w-full"
                src={`https://www.youtube-nocookie.com/embed/${data.youtube_video_id}?autoplay=1`}
                title={active.item.title}
                allow="autoplay; encrypted-media"
                allowFullScreen
              />
            </div>
          )}
        </>
      )}
    </div>
  );
}
```

- [ ] **Step 7: Migra i call-site di Discovery**

In `frontend/components/discovery-lead-grid.tsx`:
- import: `import { usePreviewPlayer } from "@/lib/preview-player";` → `import { usePlayer } from "@/lib/player";`
- `const player = usePreviewPlayer();` → `const player = usePlayer();`
- la chiamata `player.play({ key: ..., artist: ..., title: ..., discogsId: ..., level: "release", label: ... })` diventa:

```tsx
            player.play({
              kind: "discovery-preview",
              item: {
                key: `r:${lead.discogs_id ?? "x"}`,
                artist: lead.artist,
                title: lead.title,
                discogsId: lead.discogs_id,
                level: "release",
                label: lead.title,
              },
            });
```

In `frontend/components/discovery-tracklist-panel.tsx`:
- import: `usePreviewPlayer` da `@/lib/preview-player` → `usePlayer` da `@/lib/player`
- `const player = usePreviewPlayer();` → `const player = usePlayer();`
- la chiamata `player.play({ key: ..., artist: ..., title: ..., discogsId: ..., level: "track", label: ... })` diventa:

```tsx
            player.play({
              kind: "discovery-preview",
              item: {
                key: `t:${release.discogs_id}:${track.position}:${track.title}`,
                artist: release.artist,
                title: track.title,
                discogsId: release.discogs_id,
                level: "track",
                label: track.title,
              },
            })
```

In `frontend/app/discovery/page.tsx` (mount temporaneo, verrà spostato al Task 4):
- `import { DockedPreviewPlayer } from "@/components/docked-preview-player";` → `import { DockedPlayer } from "@/components/docked-player";`
- `import { PreviewPlayerProvider } from "@/lib/preview-player";` → `import { PlayerProvider } from "@/lib/player";`
- `<PreviewPlayerProvider>` → `<PlayerProvider>`, `</PreviewPlayerProvider>` → `</PlayerProvider>`
- `<DockedPreviewPlayer />` → `<DockedPlayer />`

- [ ] **Step 8: Esegui i test — devono passare**

Run: `cd frontend && npx vitest run tests/player.test.tsx`
Expected: PASS (i 4 test preview preservati sotto i nomi nuovi).

- [ ] **Step 9: Verifica build e lint**

Run: `cd frontend && npm run lint && npm run build`
Expected: nessun errore; nessun riferimento residuo a `preview-player`/`docked-preview-player`/`usePreviewPlayer`.

- [ ] **Step 10: Commit**

```bash
git add frontend/lib/player.tsx frontend/components/docked-player.tsx frontend/lib/api/tracks.ts \
        frontend/lib/i18n/en.ts frontend/lib/i18n/it.ts frontend/components/discovery-lead-grid.tsx \
        frontend/components/discovery-tracklist-panel.tsx frontend/app/discovery/page.tsx frontend/tests/player.test.tsx
git commit -m "refactor(player): player docked unico condiviso (preview terzi + traccia locale) con sorgente discriminata"
```

---

## Task 4: Mount globale del player nell'app shell (frontend)

**Files:**
- Modify: `frontend/app/layout.tsx`
- Modify: `frontend/app/discovery/page.tsx`

**Interfaces:**
- Consumes: `PlayerProvider`, `DockedPlayer` (Task 3).
- Produces: player disponibile in ogni pagina (`usePlayer` risolve ovunque).

- [ ] **Step 1: Monta provider + barra nel root layout**

In `frontend/app/layout.tsx`, aggiungi gli import:

```tsx
import { DockedPlayer } from "@/components/docked-player";
import { PlayerProvider } from "@/lib/player";
```

e avvolgi la shell:

```tsx
        <I18nProvider>
          <PlayerProvider>
            <EditorialShell>{children}</EditorialShell>
            <DockedPlayer />
          </PlayerProvider>
        </I18nProvider>
```

- [ ] **Step 2: Rimuovi il mount locale da Discovery**

In `frontend/app/discovery/page.tsx`:
- rimuovi gli import `DockedPlayer` (da `@/components/docked-player`) e `PlayerProvider` (da `@/lib/player`)
- rimuovi il wrapper `<PlayerProvider>…</PlayerProvider>` lasciando i figli al loro posto
- rimuovi la riga `<DockedPlayer />`

(La pagina continua a usare `usePlayer()` nei componenti figli: ora risolve dal provider dell'app shell.)

- [ ] **Step 3: Verifica build**

Run: `cd frontend && npm run lint && npm run build`
Expected: nessun errore; nessun doppio provider.

- [ ] **Step 4: Verifica manuale nel browser (preview Discovery ancora funzionante)**

Avvia il dev server e apri `/discovery`. Premi play su una card lead: la barra docked appare in basso a destra e la preview parte (o mostra "Nessuna anteprima"). Conferma che non ci sono errori in console.

- [ ] **Step 5: Commit**

```bash
git add frontend/app/layout.tsx frontend/app/discovery/page.tsx
git commit -m "feat(player): monta il player docked nell'app shell (disponibile in ogni pagina)"
```

---

## Task 5: Componente riusabile `TrackPlayButton` (frontend)

**Files:**
- Create: `frontend/components/track-play-button.tsx`
- Test: `frontend/tests/track-play-button.test.tsx`

**Interfaces:**
- Consumes: `usePlayer` (Task 3), `trackAudioUrl` (indiretto via docked), `t.player.*` (Task 3), `DockedPlayer`.
- Produces: `<TrackPlayButton track={{ id, title, artist, has_local_file }} className? />`. Renderizza nulla se `has_local_file` è falsy.

- [ ] **Step 1: Scrivi i test che falliscono**

Crea `frontend/tests/track-play-button.test.tsx`:

```tsx
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { DockedPlayer } from "@/components/docked-player";
import { TrackPlayButton } from "@/components/track-play-button";
import { PlayerProvider } from "@/lib/player";

function renderButton(track: { id: number; title: string; artist: string; has_local_file: boolean }) {
  return render(
    <PlayerProvider>
      <TrackPlayButton track={track} />
      <DockedPlayer />
    </PlayerProvider>,
  );
}

describe("track play button", () => {
  afterEach(cleanup);

  it("non si renderizza senza file locale", () => {
    renderButton({ id: 5, title: "T", artist: "A", has_local_file: false });
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("riproduce la traccia: l'audio docked punta all'endpoint di streaming", async () => {
    renderButton({ id: 5, title: "T", artist: "A", has_local_file: true });
    await act(async () => {
      screen.getByRole("button").click();
    });
    expect(screen.getByTestId("local-audio").getAttribute("src")).toBe("/api/tracks/5/audio");
  });

  it("mostra il messaggio di formato non supportato quando l'audio va in errore", async () => {
    renderButton({ id: 7, title: "T", artist: "A", has_local_file: true });
    await act(async () => {
      screen.getByRole("button").click();
    });
    const audio = screen.getByTestId("local-audio");
    await act(async () => {
      fireEvent.error(audio);
    });
    expect(screen.queryByTestId("local-audio")).toBeNull();
    expect(screen.getByText(/browser/i)).toBeTruthy();
  });
});
```

(Nota: `trackAudioUrl` usa `API = process.env.NEXT_PUBLIC_API_URL ?? ""`, quindi nei test l'URL è `/api/tracks/5/audio`. `useT` fuori da `I18nProvider` ripiega sul dizionario `it` di default, quindi il messaggio è "Formato non riproducibile nel browser" — contiene "browser".)

- [ ] **Step 2: Esegui i test — devono fallire**

Run: `cd frontend && npx vitest run tests/track-play-button.test.tsx`
Expected: FAIL (`@/components/track-play-button` inesistente).

- [ ] **Step 3: Implementa il componente**

Crea `frontend/components/track-play-button.tsx`:

```tsx
"use client";

import { Pause, Play } from "lucide-react";

import { useT } from "@/lib/i18n";
import { usePlayer } from "@/lib/player";

type Props = {
  track: { id: number; title: string | null; artist: string | null; has_local_file?: boolean | null };
  className?: string;
};

/** Play/pausa dell'audizione rapida di una traccia posseduta. Non renderizza
 *  nulla se la traccia non ha un file locale. Riusabile in ogni riga-traccia. */
export function TrackPlayButton({ track, className }: Props) {
  const player = usePlayer();
  const t = useT();
  if (!track.has_local_file) return null;

  const isActive = player.active?.kind === "local-track" && player.active.track.id === track.id;

  const toggle = (e: React.MouseEvent) => {
    e.stopPropagation(); // non attivare la navigazione della riga
    if (isActive) {
      player.stop();
    } else {
      player.play({
        kind: "local-track",
        track: { id: track.id, title: track.title ?? "", artist: track.artist ?? "" },
      });
    }
  };

  return (
    <button
      type="button"
      aria-label={isActive ? t.player.stop : t.player.play}
      onClick={toggle}
      className={className ?? "shrink-0 text-faint transition-colors hover:text-fg"}
    >
      {isActive ? <Pause size={14} /> : <Play size={14} />}
    </button>
  );
}
```

- [ ] **Step 4: Esegui i test — devono passare**

Run: `cd frontend && npx vitest run tests/track-play-button.test.tsx`
Expected: PASS (3 test).

- [ ] **Step 5: Commit**

```bash
git add frontend/components/track-play-button.tsx frontend/tests/track-play-button.test.tsx
git commit -m "feat(player): componente riusabile TrackPlayButton per l'audizione delle tracce possedute"
```

---

## Task 6: Innesto del play button nelle righe-traccia (frontend)

**Files:**
- Modify: `frontend/components/track-state-icons.tsx` (copre Libreria, Playlist, Labels)
- Modify: `frontend/app/tracks/[id]/page.tsx` (pagina dettaglio)

**Interfaces:**
- Consumes: `TrackPlayButton` (Task 5). Il player è già montato nell'app shell (Task 4), quindi `usePlayer` risolve.

- [ ] **Step 1: Aggiungi il play button nel componente condiviso**

In `frontend/components/track-state-icons.tsx`, aggiungi l'import:

```tsx
import { TrackPlayButton } from "./track-play-button";
```

e inserisci il bottone come primo figlio del contenitore, prima dell'icona `HardDrive`:

```tsx
    <div className="flex items-center gap-2 text-faint">
      <TrackPlayButton track={track} />
      {track.status === "ready_for_set" && (
```

(`TrackPlayButton` non renderizza nulla se `has_local_file` è falso, quindi le righe senza file restano invariate. `TrackStateIcons` riceve già `track: Track` completo, con `id`/`title`/`artist`/`has_local_file`.)

- [ ] **Step 2: Verifica build e test**

Run: `cd frontend && npm run lint && npm run build && npx vitest run`
Expected: nessun errore; tutti i test verdi.

- [ ] **Step 3: Aggiungi il play button nella pagina dettaglio traccia**

In `frontend/app/tracks/[id]/page.tsx`, aggiungi l'import:

```tsx
import { TrackPlayButton } from "@/components/track-play-button";
```

e inserisci `<TrackPlayButton track={track} />` accanto al badge "posseduta" (vicino a `t.tracks.badgeOwned`, riga ~152). Esempio, mettendolo prima del badge:

```tsx
              <TrackPlayButton track={track} />
              {track.has_local_file ? <Badge tone="success">{t.tracks.badgeOwned}</Badge>
```

(Adatta all'esatta struttura JSX locale; l'importante è che sia dentro l'app shell — lo è — e riceva l'oggetto `track`.)

- [ ] **Step 4: Verifica manuale nel browser**

Avvia il dev server, apri `/library`: le tracce con badge "file su disco" mostrano un pulsante play. Premilo su una traccia MP3/FLAC posseduta → la barra docked appare e riproduce; lo scrubber consente il seek. Premi play su una traccia AIFF su Chrome → compare "Formato non riproducibile nel browser". Premendo play su una seconda traccia, la prima si ferma (una sola sorgente).

- [ ] **Step 5: Commit**

```bash
git add frontend/components/track-state-icons.tsx frontend/app/tracks/[id]/page.tsx
git commit -m "feat(player): pulsante play sulle righe-traccia possedute (libreria, playlist, labels, dettaglio)"
```

**Nota (opzionale, stesso pattern):** `app/sets/[id]/page.tsx:486` e `app/transitions/page.tsx:166` renderizzano un badge condizionato a `has_local_file` senza passare da `TrackStateIcons`. Se si vuole il play anche lì, aggiungere `<TrackPlayButton track={tr} />` accanto a quel badge con lo stesso import. Fuori dal deliverable minimo di questo task.

---

## Task 7: Allineamento documentazione

**Files:**
- Modify: `CLAUDE.md`, `docs/API.md`, `docs/ARCHITECTURE.md`, `docs/ROADMAP.md`, `PROGRESS.md`

**Interfaces:** nessuna (solo docs).

- [ ] **Step 1: Emenda la regola non-negoziabile in `CLAUDE.md`**

Nel paragrafo "Project" e nella regola 7 ("The library is the disk"), aggiungi l'eccezione: Cratory ora **riproduce in sola lettura i file delle tracce possedute** (`has_local_file`) per audizione rapida, senza mai modificarli (i tag restano di Sortory), accanto alle eccezioni già presenti (Shazam temporaneo, preview effimera di Discovery). Chiarisci che "does not play audio" non vale più in senso assoluto: resta il divieto di transcodifica/persistenza di audio di terzi, ma la libreria posseduta è riproducibile.

- [ ] **Step 2: Documenta l'endpoint in `docs/API.md`**

Aggiungi `GET /api/tracks/{id}/audio`: streaming del file locale di una traccia posseduta (sola lettura, `FileResponse` con Range/seek); errori `404` `track_not_found` / `track_no_local_file` / `track_file_not_allowed` / `track_file_missing`; sicurezza del path via `search_roots()`.

- [ ] **Step 3: Nota in `docs/ARCHITECTURE.md` e `docs/ROADMAP.md`**

Registra la nuova capacità "player audizione rapida delle tracce possedute" e il suo scope (una traccia per volta, stream raw, player docked unico condiviso con la preview di Discovery). Nessuna feature DJ (waveform/cue) — resta al Set Builder / Rekordbox.

- [ ] **Step 4: Voce in `PROGRESS.md`**

Aggiungi una voce di diario datata 2026-07-16 che riassume: endpoint `/audio`, player unico condiviso, `TrackPlayButton`, cambio di rotta recepito nei docs.

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md docs/API.md docs/ARCHITECTURE.md docs/ROADMAP.md PROGRESS.md
git commit -m "docs: recepisce il player delle tracce possedute (regola read-only, endpoint, roadmap)"
```

---

## Self-Review (eseguita)

**Spec coverage:**
- §1 endpoint streaming → Task 1 (sicurezza) + Task 2 (endpoint). ✓
- §2.1 context generico → Task 3. ✓ §2.2 barra docked → Task 3. ✓ §2.3 componente play → Task 5. ✓ §2.4 mount app shell → Task 4. ✓ §2.5 punti di innesto → Task 6. ✓
- §3 client API `trackAudioUrl` → Task 3 Step 4. ✓
- §4 i18n → Task 3 Step 5. ✓
- §5 test backend (200/206/404×4/traversal) → Task 1+2. Test frontend (una-sola-sorgente, gate has_local_file, onError) → Task 3 (preserva race-guard) + Task 5. ✓
- §6 docs → Task 7. ✓

**Placeholder scan:** nessun "TBD"/"come sopra"; ogni step di codice mostra il codice completo. L'unico punto adattivo è l'esatta posizione JSX nella pagina dettaglio (Task 6 Step 3), con ancora di riga esplicita.

**Type consistency:** `PlayerProvider`/`usePlayer`/`DockedPlayer`/`PlaybackSource`/`LocalTrack`/`trackAudioUrl` usati coerentemente in Task 3→6; `get_track_audio`/`path_within_roots` coerenti in Task 1→2; codici errore `track_no_local_file`/`track_file_not_allowed`/`track_file_missing`/`track_not_found` identici tra endpoint e test.
