# Ricerca Soulseek integrata — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ricerca manuale Soulseek per traccia dentro Cratory: un modal unico (`SoulseekSearchModal`) con query modificabile, risultati grezzi e download del file scelto, che sostituisce `DownloadReviewModal`.

**Architecture:** Un endpoint nuovo `POST /api/downloads/search` esegue UNA ricerca slskd con la query letterale (niente cascata: quella resta all'auto-pick) e arricchisce i risultati con score/confidenza esistenti senza escludere nulla. Il frontend monta il nuovo modal da riga wishlist e dettaglio traccia; il download riusa `POST /api/downloads/track`.

**Tech Stack:** FastAPI + Pydantic, pytest (backend); Next.js 16 App Router, vitest + testing-library, Playwright (frontend).

**Spec:** `docs/superpowers/specs/2026-08-15-ricerca-soulseek-integrata-design.md`

## Global Constraints

- Worktree: `/Users/lucadenegri/Develop/DJProject01/.claude/worktrees/wishlist-section-org-105213` (branch `claude/wishlist-section-org-105213`). Tutti i path sotto sono relativi alla sua radice.
- Backend test: il worktree NON ha `.venv`; usare il venv del checkout principale con cwd nel backend del worktree:
  `cd backend && /Users/lucadenegri/Develop/DJProject01/backend/.venv/bin/python -m pytest tests/<file> -v`
- Frontend: prima del primo task frontend verificare che `frontend/node_modules` esista NEL worktree (`ls frontend/node_modules/.bin/vitest`); se manca, `cd frontend && npm install` (installazione reale, niente symlink: rompe Turbopack).
- i18n: OGNI testo user-facing nuovo va aggiunto sia in `frontend/lib/i18n/it.ts` sia in `frontend/lib/i18n/en.ts`.
- Commit frequenti, messaggio in italiano stile repo (`feat(wishlist): …`), MAI `Co-Authored-By: Claude`.
- Next.js 16 ha breaking changes: leggere `frontend/CLAUDE.md` prima di toccare pagine/routing.
- Correzione di spec decisa in fase di piano: il bottone primario di riga per `downloaded_unlinked` RESTA «Collega file» (il file è già su disco: cercarne un altro non è l'azione primaria); il nuovo modal per quello stato si apre dal menù `…`. Il Task 7 aggiorna la spec.

---

### Task 1: Backend — endpoint `POST /api/downloads/search`

**Files:**
- Modify: `backend/app/routers/downloads.py`
- Test: `backend/tests/test_downloads_search.py` (nuovo)

**Interfaces:**
- Consumes: `SlskdClient.search(artist, title, *, max_wait, search_timeout_ms)` (concatena `f"{artist} {title}".strip()` → passare `(req.query, "")` = query letterale); `rank_candidates`, `query_variants`, `QualityPreference`, `AUTO_PICK_MIN_CONFIDENCE` da `app.services.soulseek_select`; `get_track` da `app.repositories`.
- Produces: `POST /api/downloads/search` body `{query: str, track_id?: int}` → `{"variants": [str], "results": [SearchFileOut]}` con `SearchFileOut = {username, filename, size, bitrate, length, format, has_free_slot, queue_length, upload_speed, score|null, confidence|null, auto_ok: bool}`. Ordinati per score desc quando c'è `track_id`; senza `track_id` ordine slskd, `score/confidence = null`, `variants = []`.

- [ ] **Step 1: Scrivere i test che falliscono**

Creare `backend/tests/test_downloads_search.py` (stesso stile di `tests/test_downloads_router.py`: `TestClient(app)` a livello modulo, monkeypatch sul modulo router, `_engine()` con StaticPool per i casi con Track):

```python
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.main import app
from app.routers import downloads as downloads_router
from app.integrations.slskd import SlskdError, SlskdFile

client = TestClient(app)


def _engine():
    e = create_engine("sqlite://", connect_args={"check_same_thread": False},
                      poolclass=StaticPool)
    Base.metadata.create_all(e)
    return e, sessionmaker(bind=e, expire_on_commit=False)


def _override_db(factory):
    """get_db della app -> sessione sul DB in-memory del test."""
    from app.db import get_db

    def _db():
        db = factory()
        try:
            yield db
        finally:
            db.close()
    app.dependency_overrides[get_db] = _db


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    app.dependency_overrides.clear()


class _Client:
    """slskd finto: registra le query e restituisce file predefiniti."""

    def __init__(self, files):
        self.files = files
        self.queries = []
        self.closed = False

    def search(self, artist, title, **kwargs):
        self.queries.append(f"{artist} {title}".strip())
        return self.files

    def close(self):
        self.closed = True


def test_409_quando_slskd_non_configurato(monkeypatch):
    monkeypatch.setattr(downloads_router, "slskd_configured", lambda: False)
    r = client.post("/api/downloads/search", json={"query": "aphex twin"})
    assert r.status_code == 409


def test_query_letterale_una_sola_ricerca(monkeypatch):
    # La query dell'utente passa tal quale: UNA chiamata, nessuna cascata di varianti.
    fake = _Client([SlskdFile(username="u", filename="Aphex Twin - Xtal.flac", size=1,
                              bitrate=None, length=None, has_free_slot=True, queue_length=0)])
    monkeypatch.setattr(downloads_router, "slskd_configured", lambda: True)
    monkeypatch.setattr(downloads_router, "get_slskd_client", lambda: fake)
    r = client.post("/api/downloads/search", json={"query": "aphex twin xtal"})
    assert r.status_code == 200
    assert fake.queries == ["aphex twin xtal"]
    assert fake.closed is True
    body = r.json()
    assert body["variants"] == []
    assert body["results"][0]["username"] == "u"
    assert body["results"][0]["score"] is None
    assert body["results"][0]["auto_ok"] is False


def test_con_track_id_arricchisce_senza_escludere(monkeypatch):
    # Nome pessimo E bitrate sotto la soglia auto-pick: nei risultati manuali
    # devono comparire ENTRAMBI (nessun filtro a soglia), ordinati per score.
    from app.models import Track

    _, factory = _engine()
    db = factory()
    t = Track(source_type="manual", artist="Aphex Twin", title="Xtal", duration_seconds=294)
    db.add(t)
    db.commit()
    _override_db(factory)

    files = [
        SlskdFile(username="good", filename="Aphex Twin - Xtal.flac", size=1,
                  bitrate=None, length=294, has_free_slot=True, queue_length=0),
        SlskdFile(username="bad-name", filename="b1 untitled rip.mp3", size=1,
                  bitrate=320, length=None, has_free_slot=True, queue_length=0),
        SlskdFile(username="low-q", filename="Aphex Twin - Xtal.mp3", size=1,
                  bitrate=128, length=294, has_free_slot=True, queue_length=0),
    ]
    monkeypatch.setattr(downloads_router, "slskd_configured", lambda: True)
    monkeypatch.setattr(downloads_router, "get_slskd_client", lambda: _Client(files))
    r = client.post("/api/downloads/search", json={"query": "aphex twin xtal", "track_id": t.id})
    assert r.status_code == 200
    body = r.json()
    users = [f["username"] for f in body["results"]]
    assert set(users) == {"good", "bad-name", "low-q"}      # nessuno escluso
    assert users[0] == "good"                                # score desc
    top = body["results"][0]
    assert top["score"] is not None and top["confidence"] is not None
    assert top["auto_ok"] is True                            # flac nome+durata giusti
    bad = next(f for f in body["results"] if f["username"] == "bad-name")
    assert bad["auto_ok"] is False


def test_con_track_id_include_le_varianti(monkeypatch):
    from app.models import Track
    from app.services.soulseek_select import query_variants

    _, factory = _engine()
    db = factory()
    t = Track(source_type="manual", artist="Marco Faraone, UTO",
              title="Real Freak (Extended Mix)")
    db.add(t)
    db.commit()
    _override_db(factory)

    monkeypatch.setattr(downloads_router, "slskd_configured", lambda: True)
    monkeypatch.setattr(downloads_router, "get_slskd_client", lambda: _Client([]))
    r = client.post("/api/downloads/search", json={"query": "x", "track_id": t.id})
    assert r.status_code == 200
    assert r.json()["variants"] == query_variants("Marco Faraone, UTO",
                                                  "Real Freak (Extended Mix)")


def test_404_track_inesistente(monkeypatch):
    _, factory = _engine()
    _override_db(factory)
    monkeypatch.setattr(downloads_router, "slskd_configured", lambda: True)
    r = client.post("/api/downloads/search", json={"query": "x", "track_id": 999})
    assert r.status_code == 404


def test_502_su_errore_slskd(monkeypatch):
    class _Boom:
        def search(self, a, t, **k):
            raise SlskdError("daemon irraggiungibile")

        def close(self):
            pass

    monkeypatch.setattr(downloads_router, "slskd_configured", lambda: True)
    monkeypatch.setattr(downloads_router, "get_slskd_client", lambda: _Boom())
    r = client.post("/api/downloads/search", json={"query": "x"})
    assert r.status_code == 502
```

- [ ] **Step 2: Verificare che falliscano**

Run: `cd backend && /Users/lucadenegri/Develop/DJProject01/backend/.venv/bin/python -m pytest tests/test_downloads_search.py -v`
Expected: FAIL, tutti con 404 (route inesistente) o errori di assert sullo status code.

- [ ] **Step 3: Implementare l'endpoint**

In `backend/app/routers/downloads.py`:

Aggiornare l'import da `soulseek_select` (riga 18) e aggiungere i modelli dopo `CandidatesIn`:

```python
from app.services.soulseek_select import (
    AUTO_PICK_MIN_CONFIDENCE, QualityPreference, query_variants, rank_candidates,
    search_candidates,
)
```

```python
# Ricerca manuale: budget pieno come il job in background (l'utente sta
# guardando uno spinner e preferisce risultati completi ai 5s di /candidates).
MANUAL_SEARCH_MAX_WAIT = 15.0


class SearchIn(BaseModel):
    query: str
    # Con track_id i risultati vengono arricchiti con score/confidenza
    # (artista/titolo/durata attesa della Track) e la risposta include le
    # varianti di query dell'auto-pick come suggerimenti.
    track_id: int | None = None


class SearchFileOut(BaseModel):
    username: str
    filename: str
    size: int | None = None
    bitrate: int | None = None
    length: int | None = None
    format: str | None = None
    has_free_slot: bool = True
    queue_length: int | None = None
    upload_speed: int | None = None
    # Presenti solo con contesto traccia: guidano ordinamento e badge, MAI esclusioni.
    score: float | None = None
    confidence: float | None = None
    auto_ok: bool = False


class SearchOut(BaseModel):
    variants: list[str]
    results: list[SearchFileOut]


def _search_file_out(f: SlskdFile, *, score: float | None = None,
                     confidence: float | None = None) -> SearchFileOut:
    return SearchFileOut(
        username=f.username, filename=f.filename, size=f.size, bitrate=f.bitrate,
        length=f.length, format=f.extension or None, has_free_slot=f.has_free_slot,
        queue_length=f.queue_length, upload_speed=f.upload_speed,
        score=score, confidence=confidence,
        auto_ok=confidence is not None and confidence >= AUTO_PICK_MIN_CONFIDENCE,
    )
```

Endpoint (dopo `candidates`):

```python
@router.post("/search", response_model=SearchOut)
def search(req: SearchIn, db: Session = Depends(get_db)):
    """Ricerca manuale Soulseek: UNA ricerca con la query letterale dell'utente.

    Niente cascata di varianti (resta esclusiva dell'auto-pick) e niente filtro
    a soglia: comanda l'utente, il ranking e' solo una guida. Restano fuori i
    soli file non-audio (estensione sconosciuta).
    """
    if not slskd_configured():
        raise api_error(409, "slskd_not_configured",
                        "slskd not configured (SLSKD_URL/SLSKD_DOWNLOAD_DIR).")
    track = None
    if req.track_id is not None:
        track = get_track(db, req.track_id)
        if track is None:
            raise api_error(404, "track_not_found", "Track not found.")
    client = get_slskd_client()
    try:
        files = client.search(req.query, "", max_wait=MANUAL_SEARCH_MAX_WAIT,
                              search_timeout_ms=int((MANUAL_SEARCH_MAX_WAIT - 1.0) * 1000))
    except SlskdError as exc:
        raise api_error(502, "slskd_error", f"slskd error: {exc}", reason=str(exc)) from exc
    finally:
        client.close()
    if track is None:
        return SearchOut(variants=[], results=[_search_file_out(f) for f in files])
    # min_bitrate=1: anche la bassa qualita' deve comparire (tier>0);
    # min_name_score=0.0: anche i nomi pessimi. Il ranking ordina, non esclude.
    ranked = rank_candidates(files, artist=track.artist or "", title=track.title or "",
                             pref=QualityPreference(min_bitrate=1), min_name_score=0.0,
                             expected_duration=track.duration_seconds)
    return SearchOut(
        variants=query_variants(track.artist or "", track.title or ""),
        results=[_search_file_out(c.file, score=c.score, confidence=c.confidence)
                 for c in ranked],
    )
```

- [ ] **Step 4: Verificare che passino**

Run: `cd backend && /Users/lucadenegri/Develop/DJProject01/backend/.venv/bin/python -m pytest tests/test_downloads_search.py tests/test_downloads_router.py -v`
Expected: tutti PASS (anche i test esistenti del router: nessuna regressione).

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/downloads.py backend/tests/test_downloads_search.py
git commit -m "feat(downloads): endpoint di ricerca Soulseek manuale con query letterale"
```

---

### Task 2: Frontend — `SoulseekSearchModal` con API, i18n e test

**Files:**
- Modify: `frontend/lib/api/types.ts` (dopo `DownloadCandidate`, ~riga 675)
- Modify: `frontend/lib/api/downloads.ts`
- Modify: `frontend/lib/i18n/it.ts` e `frontend/lib/i18n/en.ts` (nuova sezione `downloads.search`, accanto a `downloads.review`)
- Create: `frontend/components/soulseek-search-modal.tsx`
- Test: `frontend/tests/soulseek-search-modal.test.tsx` (nuovo)

**Interfaces:**
- Consumes: `POST /api/downloads/search` (Task 1); `downloadTrack(trackId, candidate)`, `downloadReview`, `keepReview`, `discardReview`, `fmtDuration`, `fmtSize` da `@/lib/api`; `useJobs()` da `@/components/jobs-provider` (montato globalmente da `editorial-shell.tsx`); `Modal size="lg"`, `Button`, `Alert`, `Loading`, `Spinner`, `Badge`, `Input` da `@/components/ui`.
- Produces: `SoulseekSearchModal({ target, onClose, onPicked })` con `target: SoulseekSearchTarget | null` e `export type SoulseekSearchTarget = { track_id: number; artist: string | null; title: string | null }`; API `soulseekSearch(query: string, trackId?: number): Promise<SoulseekSearchResult>`; tipi `SoulseekSearchFile`, `SoulseekSearchResult`.

- [ ] **Step 1: Tipi e wrapper API**

In `frontend/lib/api/types.ts`, subito dopo `DownloadCandidate`:

```ts
/** Un file dai risultati della ricerca Soulseek manuale (POST /api/downloads/search). */
export type SoulseekSearchFile = {
  username: string;
  filename: string;
  size: number | null;
  bitrate: number | null;
  length: number | null;
  format: string | null;
  has_free_slot: boolean;
  queue_length: number | null;
  upload_speed: number | null;
  // Presenti solo se la ricerca aveva un track_id: guida, mai esclusione.
  score: number | null;
  confidence: number | null;
  auto_ok: boolean;
};

export type SoulseekSearchResult = { variants: string[]; results: SoulseekSearchFile[] };
```

In `frontend/lib/api/downloads.ts` (sezione "Download (Soulseek/slskd)"), import dei tipi nuovi da `./types` e:

```ts
/** Ricerca manuale Soulseek con la query letterale (nessuna cascata di varianti). */
export function soulseekSearch(query: string, trackId?: number) {
  return apiPost<SoulseekSearchResult>("/api/downloads/search",
    { query, track_id: trackId ?? undefined });
}
```

Verificare che `frontend/lib/api/index.ts` ri-esporti già `./downloads` e `./types` per intero (pattern esistente); altrimenti aggiungere gli export espliciti.

- [ ] **Step 2: Chiavi i18n**

In `frontend/lib/i18n/it.ts`, dentro `downloads`, accanto a `review`:

```ts
search: {
  modalTitle: "Cerca su Soulseek",
  searchButton: "Cerca",
  queryAria: "Query di ricerca Soulseek",
  variantsHint: "Prova anche:",
  searching: "Cerco su Soulseek… (fino a ~15 secondi)",
  noResults: "Nessun risultato per questa query. Prova una variante più corta qui sopra.",
  downloadThis: "Scarica questo",
  jobRunning: "Un download è già in corso: attendi che finisca.",
  autoOkBadge: "affidabile",
  queueInfo: (n: number) => `coda ${n}`,
  noSlot: "senza slot",
  vsExpected: "vs atteso",
},
```

In `frontend/lib/i18n/en.ts`, stessa struttura:

```ts
search: {
  modalTitle: "Search on Soulseek",
  searchButton: "Search",
  queryAria: "Soulseek search query",
  variantsHint: "Also try:",
  searching: "Searching Soulseek… (up to ~15 seconds)",
  noResults: "No results for this query. Try a shorter variant above.",
  downloadThis: "Download this",
  jobRunning: "A download is already running: wait for it to finish.",
  autoOkBadge: "reliable",
  queueInfo: (n: number) => `queue ${n}`,
  noSlot: "no slot",
  vsExpected: "vs expected",
},
```

- [ ] **Step 3: Scrivere i test del componente (falliscono)**

Creare `frontend/tests/soulseek-search-modal.test.tsx` (pattern di `tests/wishlist-row.test.tsx`: niente provider, default i18n "it"; mock del modulo api):

```tsx
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { SoulseekSearchModal } from "@/components/soulseek-search-modal";
import type { SoulseekSearchFile } from "@/lib/api";

afterEach(cleanup);

const file = (over: Partial<SoulseekSearchFile> = {}): SoulseekSearchFile => ({
  username: "user1", filename: "Music\\Aphex Twin\\Xtal.flac", size: 30_000_000,
  bitrate: null, length: 294, has_free_slot: true, queue_length: 0,
  upload_speed: null, score: 120, confidence: 0.9, auto_ok: true, ...over,
});

const mocks = vi.hoisted(() => ({
  soulseekSearch: vi.fn(),
  downloadReview: vi.fn(),
  downloadTrack: vi.fn(),
}));

// Si sostituiscono solo le funzioni usate dal modal; il resto del modulo resta vero
// (fmtDuration/fmtSize e i tipi servono davvero).
vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  soulseekSearch: mocks.soulseekSearch,
  downloadReview: mocks.downloadReview,
  downloadTrack: mocks.downloadTrack,
}));

const target = { track_id: 1, artist: "Aphex Twin", title: "Xtal" };

beforeEach(() => {
  vi.clearAllMocks();
  mocks.downloadReview.mockResolvedValue({
    expected: { artist: "Aphex Twin", title: "Xtal", duration_seconds: 294 },
    downloaded: null, reason: null,
  });
  mocks.soulseekSearch.mockResolvedValue({
    variants: ["Aphex Twin Xtal", "Aphex Twin"],
    results: [file(), file({ username: "user2", filename: "b1 rip.mp3", bitrate: 128,
                             score: 40, confidence: 0.3, auto_ok: false })],
  });
});

describe("SoulseekSearchModal", () => {
  it("all'apertura lancia la ricerca con la query precompilata", async () => {
    render(<SoulseekSearchModal target={target} onClose={vi.fn()} onPicked={vi.fn()} />);
    await waitFor(() => expect(mocks.soulseekSearch).toHaveBeenCalledWith("Aphex Twin Xtal", 1));
    expect(await screen.findByText("Xtal.flac")).toBeTruthy();
    expect(screen.getByText("b1 rip.mp3")).toBeTruthy();  // nessun filtro a soglia
    expect(screen.getByText("affidabile")).toBeTruthy();  // badge solo sul candidato auto_ok
  });

  it("le varianti compilano il campo e rilanciano la ricerca", async () => {
    render(<SoulseekSearchModal target={target} onClose={vi.fn()} onPicked={vi.fn()} />);
    await screen.findByText("Xtal.flac");
    fireEvent.click(screen.getByRole("button", { name: "Aphex Twin" }));
    await waitFor(() => expect(mocks.soulseekSearch).toHaveBeenLastCalledWith("Aphex Twin", 1));
    expect((screen.getByLabelText("Query di ricerca Soulseek") as HTMLInputElement).value)
      .toBe("Aphex Twin");
  });

  it("«Scarica questo» chiama downloadTrack col candidato giusto e poi onPicked", async () => {
    mocks.downloadTrack.mockResolvedValue({});
    const onPicked = vi.fn();
    render(<SoulseekSearchModal target={target} onClose={vi.fn()} onPicked={onPicked} />);
    await screen.findByText("Xtal.flac");
    fireEvent.click(screen.getAllByText("Scarica questo")[0]);
    await waitFor(() => expect(mocks.downloadTrack).toHaveBeenCalledWith(1,
      expect.objectContaining({ username: "user1", filename: "Music\\Aphex Twin\\Xtal.flac" })));
    await waitFor(() => expect(onPicked).toHaveBeenCalled());
  });

  it("mostra il delta durata rispetto all'attesa", async () => {
    mocks.soulseekSearch.mockResolvedValue({
      variants: [], results: [file({ length: 297 })],
    });
    render(<SoulseekSearchModal target={target} onClose={vi.fn()} onPicked={vi.fn()} />);
    // durata attesa 294 (dal review), file 297 -> "+3s vs atteso"
    expect(await screen.findByText(/\+3s/)).toBeTruthy();
  });

  it("blocco Tieni/Scarta presente quando c'e' un file dubbio", async () => {
    mocks.downloadReview.mockResolvedValue({
      expected: { artist: "Aphex Twin", title: "Xtal", duration_seconds: 294 },
      downloaded: { path: "/inbox/x.mp3", name: "x.mp3", format: "mp3", bitrate: 320,
                    duration_seconds: 250, size: 9_000_000 },
      reason: "durata non corrisponde",
    });
    render(<SoulseekSearchModal target={target} onClose={vi.fn()} onPicked={vi.fn()} />);
    expect(await screen.findByText("Tieni comunque")).toBeTruthy();
    expect(screen.getByText("Scarta")).toBeTruthy();
  });
});
```

Nota: il caso "bottoni disabilitati con job in corso" dipende da `useJobs()`; il default del context (nessun provider) espone `download: null` → `canDownload = true`. Il comportamento col job in corso è coperto dal disabled già testato in wishlist (pattern `downloadsAvailable`) e qui dal codice del componente; non serve mockare il provider.

- [ ] **Step 4: Verificare che falliscano**

Run: `cd frontend && npx vitest run tests/soulseek-search-modal.test.tsx`
Expected: FAIL — modulo `@/components/soulseek-search-modal` inesistente.

- [ ] **Step 5: Implementare il componente**

Creare `frontend/components/soulseek-search-modal.tsx`:

```tsx
"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Check, Download as DownloadIcon, Search, Trash2 } from "lucide-react";
import { Alert, Badge, Button, Input, Loading, Modal, Spinner } from "@/components/ui";
import { useJobs } from "@/components/jobs-provider";
import {
  discardReview, downloadReview, downloadTrack, errText, fmtDuration, fmtSize,
  keepReview, soulseekSearch, type DownloadCandidate, type DownloadReview,
  type SoulseekSearchFile,
} from "@/lib/api";
import { useT } from "@/lib/i18n";

export type SoulseekSearchTarget = { track_id: number; artist: string | null; title: string | null };

/** Wrapper: monta il dialog solo con un target e lo rigenera per ogni traccia. */
export function SoulseekSearchModal({ target, onClose, onPicked }: {
  target: SoulseekSearchTarget | null;
  onClose: () => void;
  onPicked: () => void;
}) {
  if (!target) return null;
  return <SearchDialog key={target.track_id} target={target} onClose={onClose} onPicked={onPicked} />;
}

/** DownloadCandidate per POST /api/downloads/track: score/tier non servono al
 *  download (il backend ricostruisce SlskdFile dai soli campi identita'). */
function toCandidate(f: SoulseekSearchFile): DownloadCandidate {
  return {
    username: f.username, filename: f.filename, size: f.size, bitrate: f.bitrate,
    length: f.length, format: f.format, name_score: 0, quality_tier: 0,
    confidence: f.confidence ?? 0,
  };
}

function baseName(filename: string): string {
  return filename.split("\\").pop()?.split("/").pop() ?? filename;
}

function SearchDialog({ target, onClose, onPicked }: {
  target: SoulseekSearchTarget;
  onClose: () => void;
  onPicked: () => void;
}) {
  const t = useT();
  const { download: jobStatus, refresh } = useJobs();
  const running = jobStatus?.status === "running";
  const available = jobStatus?.available ?? true;
  const canDownload = available && !running;

  const [query, setQuery] = useState(`${target.artist ?? ""} ${target.title ?? ""}`.trim());
  const [variants, setVariants] = useState<string[]>([]);
  const [results, setResults] = useState<SoulseekSearchFile[] | null>(null);
  const [searching, setSearching] = useState(false);
  const [review, setReview] = useState<DownloadReview | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const alive = useRef(true);
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);

  const search = useCallback(async (q: string) => {
    setSearching(true);
    setError(null);
    try {
      const r = await soulseekSearch(q, target.track_id);
      if (!alive.current) return;
      setResults(r.results);
      if (r.variants.length > 0) setVariants(r.variants);
    } catch (e) {
      if (alive.current) { setError(errText(e)); setResults([]); }
    } finally {
      if (alive.current) setSearching(false);
    }
  }, [target.track_id]);

  // All'apertura: blocco revisione (se esiste un file dubbio) + ricerca automatica
  // con la query precompilata. La ricerca non aspetta la review: partono insieme.
  useEffect(() => {
    downloadReview(target.track_id).then((r) => alive.current && setReview(r)).catch(() => undefined);
    void search(`${target.artist ?? ""} ${target.title ?? ""}`.trim());
  }, [target, search]);

  const runVariant = (v: string) => { setQuery(v); void search(v); };

  const act = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    try { await fn(); refresh(); onPicked(); } catch (e) { setError(errText(e)); }
    finally { if (alive.current) setBusy(false); }
  };

  const expDur = review?.expected.duration_seconds ?? null;
  const dl = review?.downloaded ?? null;
  const dlDelta = expDur != null && dl?.duration_seconds != null ? dl.duration_seconds - expDur : null;

  return (
    <Modal open onClose={onClose} title={t.downloads.search.modalTitle} size="lg">
      <div className="space-y-4 p-4">
        <p className="text-sm text-muted">
          {target.artist ?? "?"} — {target.title ?? "?"}
          {expDur != null && (
            <span className="ml-2 text-xs text-faint">{t.downloads.review.expectedDuration(fmtDuration(expDur))}</span>
          )}
        </p>
        {!canDownload && <Alert tone="info">{t.downloads.search.jobRunning}</Alert>}
        {error && <Alert tone="danger">⚠ {error}</Alert>}

        {/* File dubbio gia' scaricato: Tieni/Scarta (endpoint review invariati). */}
        {dl && (
          <div className="border border-border-strong p-3">
            <div className="mb-1.5 text-[10px] uppercase tracking-wider text-muted">
              {t.downloads.review.fileAlreadyDownloaded}
            </div>
            <div className="truncate font-mono text-xs">{dl.name}</div>
            <div className="mt-0.5 text-xs text-muted">
              {(dl.format ?? "?").toUpperCase()}
              {dl.bitrate ? ` · ${dl.bitrate} kbps` : ""}
              {dl.duration_seconds != null ? ` · ${fmtDuration(dl.duration_seconds)}` : ""}
              {dlDelta != null && (
                <span className="ml-1 text-fg-strong">
                  ({dlDelta > 0 ? "+" : ""}{dlDelta}s {t.downloads.review.vsExpected})
                </span>
              )}
              {dl.size ? ` · ${fmtSize(dl.size)}` : ""}
            </div>
            <div className="mt-2 flex gap-2">
              <Button size="sm" onClick={() => act(() => keepReview(target.track_id))} disabled={busy}>
                {busy ? <Spinner /> : <Check size={13} />} {t.downloads.review.keepAnywayButton}
              </Button>
              <Button size="sm" variant="danger"
                onClick={() => act(() => discardReview(target.track_id))} disabled={busy}>
                <Trash2 size={13} /> {t.downloads.review.discardButton}
              </Button>
            </div>
          </div>
        )}

        {/* Query modificabile + varianti dell'auto-pick come scorciatoie. */}
        <form className="flex items-center gap-2"
          onSubmit={(e) => { e.preventDefault(); void search(query); }}>
          <Input className="h-8 flex-1" value={query} aria-label={t.downloads.search.queryAria}
            onChange={(e) => setQuery(e.target.value)} />
          <Button type="submit" size="sm" disabled={searching || !query.trim()}>
            {searching ? <Spinner /> : <Search size={13} />} {t.downloads.search.searchButton}
          </Button>
        </form>
        {variants.length > 0 && (
          <div className="flex flex-wrap items-center gap-1.5 text-xs text-muted">
            <span>{t.downloads.search.variantsHint}</span>
            {variants.filter((v) => v !== query).map((v) => (
              <button key={v} type="button" onClick={() => runVariant(v)}
                className="border border-border px-1.5 py-px text-[11px] text-muted hover:text-fg">
                {v}
              </button>
            ))}
          </div>
        )}

        {/* Risultati grezzi: il ranking ordina e marca, non esclude. */}
        {searching && results === null && <Loading label={t.downloads.search.searching} />}
        {results?.length === 0 && !searching && (
          <p className="py-6 text-center text-sm text-muted">{t.downloads.search.noResults}</p>
        )}
        {results && results.length > 0 && (
          <ul className="max-h-80 divide-y divide-border overflow-y-auto border border-border">
            {results.map((f, i) => {
              const delta = expDur != null && f.length != null ? f.length - expDur : null;
              return (
                <li key={`${f.username}-${f.filename}-${i}`} className="flex items-center gap-3 px-3 py-2 text-sm">
                  <div className="min-w-0 flex-1">
                    <div className="truncate font-mono text-xs" title={f.filename}>{baseName(f.filename)}</div>
                    <div className="mt-0.5 text-xs text-muted">
                      {(f.format ?? "?").toUpperCase()}
                      {f.bitrate ? ` · ${f.bitrate} kbps` : ""}
                      {f.length != null ? ` · ${fmtDuration(f.length)}` : ""}
                      {delta != null && (
                        <span className="ml-1 text-fg-strong">
                          ({delta > 0 ? "+" : ""}{delta}s {t.downloads.search.vsExpected}{Math.abs(delta) > 20 ? " ⚠" : ""})
                        </span>
                      )}
                      {f.size ? ` · ${fmtSize(f.size)}` : ""}
                      {" · "}{f.username}
                      {!f.has_free_slot ? ` · ${t.downloads.search.noSlot}`
                        : (f.queue_length ?? 0) > 0 ? ` · ${t.downloads.search.queueInfo(f.queue_length ?? 0)}` : ""}
                    </div>
                  </div>
                  {f.auto_ok && <Badge tone="neutral">{t.downloads.search.autoOkBadge}</Badge>}
                  <Button size="sm" variant="outline" disabled={busy || !canDownload}
                    onClick={() => act(() => downloadTrack(target.track_id, toCandidate(f)))}>
                    {busy ? <Spinner /> : <DownloadIcon size={13} />} {t.downloads.search.downloadThis}
                  </Button>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </Modal>
  );
}
```

- [ ] **Step 6: Verificare che passino**

Run: `cd frontend && npx vitest run tests/soulseek-search-modal.test.tsx`
Expected: PASS (5 test).

- [ ] **Step 7: Commit**

```bash
git add frontend/lib/api/types.ts frontend/lib/api/downloads.ts frontend/lib/i18n/it.ts frontend/lib/i18n/en.ts frontend/components/soulseek-search-modal.tsx frontend/tests/soulseek-search-modal.test.tsx
git commit -m "feat(wishlist): SoulseekSearchModal — ricerca manuale integrata con risultati grezzi"
```

---

### Task 3: Wiring nella wishlist (riga + pagina) e ritiro del vecchio modal dalla pagina

**Files:**
- Modify: `frontend/components/wishlist-row.tsx`
- Modify: `frontend/app/wishlist/page.tsx`
- Modify: `frontend/lib/i18n/it.ts` e `frontend/lib/i18n/en.ts` (una chiave: `wishlist.searchSoulseek`)
- Test: `frontend/tests/wishlist-row.test.tsx` (aggiornare)

**Interfaces:**
- Consumes: `SoulseekSearchModal`, `SoulseekSearchTarget` (Task 2).
- Produces: `WishlistRowProps.onSearch: (t: Track) => void` (rinomina di `onReview`, ora usata anche dal menù `…` per tutti gli stati). Primario per stato: `never`→Scarica (auto), `not_found`/`failed`→Riprova (auto), `review`→Rivedi (apre il modal), `downloaded_unlinked`→Collega file (invariato).

- [ ] **Step 1: Aggiornare i test della riga (falliscono)**

In `frontend/tests/wishlist-row.test.tsx`: rinominare `onReview` in `onSearch` nell'oggetto `noop` e aggiungere il test del menù:

```tsx
const noop = { onDownload: vi.fn(), onSearch: vi.fn(), onLinkFile: vi.fn(), onClearOutcome: vi.fn(), onArchive: vi.fn(), onRestore: vi.fn() };
```

Nel test dell'azione primaria, il click su "Rivedi" ora deve chiamare `onSearch`:

```tsx
    rerender(<WishlistRow track={{ ...base, last_download_outcome: "needs_review" } as Track} downloadsAvailable from={from} {...noop} />);
    fireEvent.click(screen.getByText("Rivedi"));
    expect(noop.onSearch).toHaveBeenCalled();
```

Nuovo test in coda alla describe:

```tsx
  it("menu …: «Cerca su Soulseek» disponibile per ogni stato e chiama onSearch", () => {
    render(<WishlistRow track={base} downloadsAvailable from={from} {...noop} />);
    fireEvent.click(screen.getByLabelText("Altre azioni"));
    fireEvent.click(screen.getByText("Cerca su Soulseek"));
    expect(noop.onSearch).toHaveBeenCalled();
  });
```

Run: `cd frontend && npx vitest run tests/wishlist-row.test.tsx` — Expected: FAIL (prop inesistente / voce di menù assente).

- [ ] **Step 2: Aggiornare `wishlist-row.tsx`**

- In `WishlistRowProps`: rinominare `onReview: (t: Track) => void;` in `onSearch: (t: Track) => void;  // apre SoulseekSearchModal (primaria per review, voce menu per tutti)` e aggiornare la destrutturazione.
- Nel `primary`, caso `review`: `onClick={() => onSearch(track)}` (label resta `t.wishlist.reviewButton`). Caso `downloaded_unlinked`: INVARIATO (Collega file).
- Nel `DropdownMenu` del menù `…`, aggiungere come prima voce:

```tsx
              { key: "soulseek", label: t.wishlist.searchSoulseek, onSelect: () => onSearch(track) },
```

- In `frontend/lib/i18n/it.ts`, sezione `wishlist`: `searchSoulseek: "Cerca su Soulseek",` — in `en.ts`: `searchSoulseek: "Search on Soulseek",`.

- [ ] **Step 3: Aggiornare `wishlist/page.tsx`**

- Import: togliere `DownloadReviewModal, type ReviewTarget`; aggiungere `import { SoulseekSearchModal, type SoulseekSearchTarget } from "@/components/soulseek-search-modal";`.
- Stato: `const [review, setReview] = useState<ReviewTarget | null>(null);` → `const [searchTarget, setSearchTarget] = useState<SoulseekSearchTarget | null>(null);`.
- Nel render della riga: `onReview={(x) => setReview(...)}` → `onSearch={(x) => setSearchTarget({ track_id: x.id, artist: x.artist, title: x.title })}`.
- Montaggio: sostituire il blocco `<DownloadReviewModal …/>` con:

```tsx
      <SoulseekSearchModal target={searchTarget} onClose={() => setSearchTarget(null)}
        onPicked={() => { refresh(); setSearchTarget(null); load(); }} />
```

- Spostare la `<section>` "Soulseek / Apri slskd" (righe ~153-164) DOPO la `<section>` dei filtri+lista, come ultima sezione della pagina, sostituendo il testo hint: in `it.ts` `soulseekHint: "Riserva: se slskd non risponde o vuoi la sua interfaccia, aprila da qui."` — in `en.ts` `soulseekHint: "Fallback: if slskd is unreachable or you want its own UI, open it here."` (la ricerca manuale ora vive nel modal per traccia).

- [ ] **Step 4: Verificare**

Run: `cd frontend && npx vitest run tests/wishlist-row.test.tsx tests/soulseek-search-modal.test.tsx && npm run lint`
Expected: PASS, lint pulito.

- [ ] **Step 5: Commit**

```bash
git add frontend/components/wishlist-row.tsx frontend/app/wishlist/page.tsx frontend/lib/i18n/it.ts frontend/lib/i18n/en.ts frontend/tests/wishlist-row.test.tsx
git commit -m "feat(wishlist): il nuovo modal di ricerca sostituisce la revisione; slskd retrocesso a riserva"
```

---

### Task 4: Punto d'ingresso dal dettaglio traccia

**Files:**
- Modify: `frontend/app/tracks/[id]/page.tsx`

**Interfaces:**
- Consumes: `SoulseekSearchModal`, `SoulseekSearchTarget` (Task 2).
- Produces: il bottone esistente «Cerca su Soulseek» (card Disco, visibile se `!track.has_local_file`) apre il modal invece di lanciare l'auto-pick cieco.

- [ ] **Step 1: Sostituire l'auto-pick col modal**

In `frontend/app/tracks/[id]/page.tsx`:

- Aggiungere `import { SoulseekSearchModal, type SoulseekSearchTarget } from "@/components/soulseek-search-modal";` e stato `const [slskSearch, setSlskSearch] = useState<SoulseekSearchTarget | null>(null);`.
- Rimuovere la funzione `searchSoulseek` (quella che chiama `downloadTrackAuto`), lo stato `dlState`/`setDlState`/`dlError` e l'import di `downloadTrackAuto` se non più usato altrove nel file.
- Il bottone della card Disco diventa:

```tsx
                {!track.has_local_file && (
                  <Button size="sm" variant="outline"
                    onClick={() => setSlskSearch({ track_id: track.id, artist: track.artist, title: track.title })}>
                    <Download size={14} /> {t.tracks.searchSoulseek}
                  </Button>
                )}
```

- Montare in fondo alla pagina (accanto agli altri modal/al return principale):

```tsx
      <SoulseekSearchModal target={slskSearch} onClose={() => setSlskSearch(null)}
        onPicked={() => { setSlskSearch(null); refresh(); }} />
```

  dove `refresh` è la funzione già presente nella pagina (riga ~79) che rifà `apiGet<TrackDetail>` e setta `track`. Il progresso del download resta visibile nella job bar globale (jobs provider), quindi la perdita di `dlState`/`soulseekQueued` non toglie feedback.
- Se dopo la rimozione `t.tracks.soulseekQueued` non è più referenziato nel codebase (`grep -rn "soulseekQueued" frontend --include="*.tsx" --include="*.ts"` → solo i18n), togliere la chiave da `it.ts` e `en.ts`.
- ATTENZIONE Next 16: leggere `frontend/CLAUDE.md` prima di modificare la pagina.

- [ ] **Step 2: Verificare**

Run: `cd frontend && npm run lint && npx tsc --noEmit`
Expected: puliti. Poi verifica manuale rapida via dev server se disponibile (facoltativa: la e2e del Task 6 copre il flusso wishlist).

- [ ] **Step 3: Commit**

```bash
git add "frontend/app/tracks/[id]/page.tsx" frontend/lib/i18n/it.ts frontend/lib/i18n/en.ts
git commit -m "feat(tracks): «Cerca su Soulseek» apre la ricerca integrata invece dell'auto-pick cieco"
```

---

### Task 5: Eliminare `DownloadReviewModal`

**Files:**
- Delete: `frontend/components/download-review-modal.tsx`
- Modify (eventuale): `frontend/lib/i18n/it.ts`, `frontend/lib/i18n/en.ts`

**Interfaces:**
- Consumes: Task 3 e 4 completati (nessun import residuo).

- [ ] **Step 1: Verificare che sia orfano e cancellare**

Run: `grep -rn "download-review-modal\|DownloadReviewModal" frontend --include="*.tsx" --include="*.ts" | grep -v node_modules`
Expected: solo il file stesso. Poi `rm frontend/components/download-review-modal.tsx`.

Chiavi `t.downloads.review.*`: il nuovo modal usa ancora `expectedDuration`, `fileAlreadyDownloaded`, `vsExpected`, `keepAnywayButton`, `discardButton` — restano. Verificare le altre (`modalTitle`, `replaceWithHeading`, `chooseFileHeading`, `searchingCandidates`, `noCandidates`, `downloadButton`) con `grep -rn "<chiave>" frontend --include="*.tsx"`: rimuovere da `it.ts`/`en.ts` SOLO quelle a zero riferimenti.

- [ ] **Step 2: Verificare**

Run: `cd frontend && npm run lint && npx tsc --noEmit && npx vitest run`
Expected: tutto verde (nessun test referenzia più il vecchio modal).

- [ ] **Step 3: Commit**

```bash
git add -A frontend/components frontend/lib/i18n
git commit -m "chore(wishlist): via DownloadReviewModal, sostituito dalla ricerca integrata"
```

---

### Task 6: Test e2e del percorso felice

**Files:**
- Modify: `frontend/e2e/wishlist.spec.ts`

**Interfaces:**
- Consumes: UI dei Task 2-3. Backend reale con DB vuoto (setup e2e esistente) + `page.route` per stubbare le API: il test non dipende da slskd.

- [ ] **Step 1: Scrivere il test**

Aggiungere a `frontend/e2e/wishlist.spec.ts`:

```ts
test("ricerca Soulseek integrata: apri dal menu riga, cerca, scarica", async ({ page }) => {
  const track = {
    id: 1, artist: "Aphex Twin", title: "Xtal", has_local_file: false, archived: false,
    playlists: [], last_download_outcome: null, last_download_reason: null,
    last_download_path: null, album_art_url: null,
  };
  await page.route("**/api/tracks?*", (route) =>
    route.fulfill({ json: { total: 1, items: [track] } }));
  await page.route("**/api/downloads/review/1", (route) =>
    route.fulfill({ json: { expected: { artist: "Aphex Twin", title: "Xtal", duration_seconds: 294 }, downloaded: null, reason: null } }));
  await page.route("**/api/downloads/search", (route) =>
    route.fulfill({ json: { variants: ["Aphex Twin Xtal", "Aphex Twin"], results: [{
      username: "user1", filename: "Music\\Aphex Twin\\Xtal.flac", size: 30000000,
      bitrate: null, length: 294, has_free_slot: true, queue_length: 0,
      upload_speed: null, score: 120, confidence: 0.9, auto_ok: true,
    }] } }));
  const downloadCalls: unknown[] = [];
  await page.route("**/api/downloads/track", async (route) => {
    downloadCalls.push(route.request().postDataJSON());
    await route.fulfill({ status: 202, json: { available: true, status: "running" } });
  });

  await page.goto("/wishlist");
  await page.getByLabel("Altre azioni").click();
  await page.getByText("Cerca su Soulseek").click();
  await expect(page.getByText("Xtal.flac")).toBeVisible();
  await page.getByText("Scarica questo").click();
  await expect.poll(() => downloadCalls.length).toBe(1);
  expect(downloadCalls[0]).toMatchObject({ track_id: 1,
    candidate: { username: "user1", filename: "Music\\Aphex Twin\\Xtal.flac" } });
});
```

- [ ] **Step 2: Eseguire la e2e**

Prerequisito (memoria di progetto): la e2e Playwright richiede un `backend/.venv` nel worktree; se manca, seguire il setup annotato in `project-worktree-test-setup` (crearlo o riusare la config e2e esistente del repo).
Run: `cd frontend && npx playwright test e2e/wishlist.spec.ts`
Expected: PASS (3 test: i 2 esistenti + il nuovo).

- [ ] **Step 3: Commit**

```bash
git add frontend/e2e/wishlist.spec.ts
git commit -m "test(e2e): percorso felice della ricerca Soulseek integrata"
```

---

### Task 7: Documentazione e verifica finale

**Files:**
- Modify: `docs/API.md` (sezione downloads)
- Modify: `docs/superpowers/specs/2026-08-15-ricerca-soulseek-integrata-design.md`
- Modify: `PROGRESS.md` (riga di stato, stile esistente)

- [ ] **Step 1: Documentare l'endpoint**

In `docs/API.md`, accanto a `POST /api/downloads/candidates`, aggiungere:

```markdown
- `POST /api/downloads/search` — ricerca Soulseek manuale con la query letterale
  (nessuna cascata di varianti, nessun filtro a soglia; esclusi i soli file
  non-audio). Body `{query, track_id?}`. Con `track_id` i risultati portano
  `score`/`confidence`/`auto_ok` (contesto della Track: artista/titolo/durata
  attesa) e la risposta include le `variants` della cascata auto-pick come
  suggerimenti. Errori: 409 non configurato, 404 traccia, 502 daemon.
```

- [ ] **Step 2: Correggere la spec (decisione di piano)**

Nella spec, sezione "UX e flusso", sostituire la riga «riga wishlist: il bottone primario contestuale per `review` e `downloaded_unlinked` apre il nuovo modal; …» con:

```markdown
- riga wishlist: il bottone primario per `review` apre il nuovo modal;
  `downloaded_unlinked` mantiene «Collega file» come primaria (il file è già su
  disco); per tutti gli stati il menù `…` offre "Cerca su Soulseek";
```

Aggiornare `PROGRESS.md` con una riga nello stile delle esistenti (ricerca Soulseek integrata nella wishlist, review modal sostituito).

- [ ] **Step 3: Verifica finale completa**

```bash
cd backend && /Users/lucadenegri/Develop/DJProject01/backend/.venv/bin/python -m pytest tests
cd ../frontend && npm run lint && npx vitest run && npm run build
```

Expected: tutto verde (build Turbopack inclusa: richiede node_modules reale nel worktree).

- [ ] **Step 4: Commit**

```bash
git add docs/API.md docs/superpowers/specs/2026-08-15-ricerca-soulseek-integrata-design.md PROGRESS.md
git commit -m "docs: endpoint di ricerca Soulseek manuale + correzione spec downloaded_unlinked"
```
