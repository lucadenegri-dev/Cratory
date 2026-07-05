# Audit Remediation — Piano a Lotti Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implementare le proposte funzionali (A), frontend (B) e tecniche (E) di `docs/AUDIT-2026-07-05.md` — codice morto (C) e documentazione (D) sono già stati applicati in quell'audit.

**Architecture:** Un lotto per sessione, ordinato per rapporto valore/sforzo. Ogni lotto è autonomo, testabile e mergeable indipendentemente. Il Lotto 0 contiene passi TDD completi pronti all'esecuzione; i Lotti 1-10 contengono task card con file/riga/codice esatti (verificati contro il codice attuale) da espandere in passi TDD con lo stesso pattern del Lotto 0 al momento dell'esecuzione.

**Tech Stack:** Backend Python/FastAPI/SQLAlchemy/pytest, Frontend Next.js 16/React/TypeScript, nessun test runner frontend (verifica manuale via preview per i cambi UI, come da `CLAUDE.md`).

## Global Constraints

- **Assegnazione modello per lotto/task** (vincolo esplicito del richiedente): **Sonnet 5** è il default per l'autoria di codice; **Haiku 4.5** solo per task marcati `[Haiku]` — meccanici, senza decisioni di design (header, aria-label, loading="lazy", costanti, rename, un'unica riga senza logica). **Opus 4.8 non scrive mai codice in questo piano — solo `[Opus review]`**: un passaggio di revisione a fine lotto prima del merge, mai in autoria.
- **BPM/key/feature musicali non si inventano** (CLAUDE.md regola 2): nessun task di questo piano deve introdurre stime euristiche di BPM/key senza `enrichment_source`/`enrichment_confidence`.
- **Non sovrascrivere BPM/key esistenti** (CLAUDE.md regola 3): ogni fix su `enrichment_source`/`enrichment_confidence` deve rispettare "manual" come autorevole.
- **Rekordbox resta fuori progetto** (CLAUDE.md regola 8): nessun task deve reintrodurre import/colonne Rekordbox.
- **Cratory non muta mai i file audio** (CLAUDE.md regola 9): i task su libreria/indicizzazione leggono, non scrivono, sui file audio.
- Ogni lotto backend termina con `cd backend && source .venv/bin/activate && python -m pytest tests -q` verde (432+ test) prima del merge.
- Ogni lotto frontend termina con `cd frontend && npm run lint && npm run build` puliti; per cambi visivi, verifica con `preview_start`/`preview_snapshot`/`preview_screenshot` prima di dichiarare fatto (niente claim "funziona" senza prova).
- Ogni commit segue lo stile esistente (git log): `feat:`/`fix:`/`refactor:` in italiano, imperativo, senza firma AI nel messaggio (vedi memoria `feedback_commit_style`).

---

## Lotto 0 — Quick win (Sonnet 5, 1 review Opus 4.8 a fine lotto)

**Obiettivo:** i 5 interventi con il miglior rapporto valore/sforzo del report, tutti a rischio di regressione basso. Pronto per esecuzione immediata via subagent-driven-development.

### Task 0.1: PRAGMA WAL/busy_timeout/foreign_keys su SQLite (E1)

**Files:**
- Modify: `backend/app/db.py:1-19` (import + `_make_engine`)
- Test: `backend/tests/test_db_pragmas.py` (nuovo)

**Interfaces:**
- Produces: `_make_engine(url)` continua a ritornare un `Engine` SQLAlchemy; nessun cambio di firma, solo comportamento aggiuntivo sulla connessione.

- [ ] **Step 1: Scrivi il test che fallisce**

```python
# backend/tests/test_db_pragmas.py
"""PRAGMA WAL/busy_timeout/foreign_keys attivi sulle connessioni SQLite (fix E1)."""
from sqlalchemy import text

from app.db import _make_engine


def test_sqlite_pragmas_applied(tmp_path):
    db_path = tmp_path / "test.db"
    engine = _make_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        assert conn.execute(text("PRAGMA journal_mode")).scalar() == "wal"
        assert conn.execute(text("PRAGMA foreign_keys")).scalar() == 1
        assert conn.execute(text("PRAGMA busy_timeout")).scalar() == 5000
```

- [ ] **Step 2: Esegui e verifica che fallisca**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_db_pragmas.py -v`
Expected: FAIL — `journal_mode` è `'delete'`, non `'wal'` (nessun PRAGMA applicato oggi).

- [ ] **Step 3: Implementa**

In `backend/app/db.py`, cambia l'import in cima al file:

```python
from sqlalchemy import create_engine, event, inspect, text
```

Poi sostituisci `_make_engine`:

```python
def _make_engine(url: str):
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    if url.startswith("sqlite:///"):
        db_path = Path(url.removeprefix("sqlite:///"))
        if not db_path.parent.exists():
            db_path.parent.mkdir(parents=True, exist_ok=True)
    eng = create_engine(url, connect_args=connect_args)
    if url.startswith("sqlite"):
        @event.listens_for(eng, "connect")
        def _set_sqlite_pragmas(dbapi_conn, _record):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()
    return eng
```

- [ ] **Step 4: Esegui e verifica che passi**

Run: `python -m pytest tests/test_db_pragmas.py -v`
Expected: PASS

- [ ] **Step 5: Suite completa (regressione FK)**

Run: `python -m pytest tests -q`
Expected: 432+ passed. Se qualche test fallisce per un vincolo FK ora rispettato (es. inserimento di un `SetlistTrack` con `setlist_id` inesistente), è un bug reale scoperto dal fix — non allentare il PRAGMA, correggi il test/fixture.

- [ ] **Step 6: Commit**

```bash
git add backend/app/db.py backend/tests/test_db_pragmas.py
git commit -m "fix: attiva WAL/busy_timeout/foreign_keys su SQLite

Elimina i 'database is locked' quando i job in background (indicizzazione,
enrichment) scrivono mentre l'utente naviga; foreign_keys=ON previene
orfani futuri in playlist_tracks/setlist_tracks."
```

### Task 0.2: `ensure_schema` crea gli indici mancanti sui DB esistenti (E1)

**Files:**
- Modify: `backend/app/db.py` — funzione `ensure_schema` (dopo il loop `additions`, prima di `_migrate_drop_legacy`)
- Test: `backend/tests/test_db_pragmas.py` (stesso file del Task 0.1, aggiungi un secondo test)

**Interfaces:**
- Consumes: `_make_engine` dal Task 0.1 (nessuna interazione: PRAGMA e indici sono ortogonali)

- [ ] **Step 1: Scrivi il test che fallisce**

Aggiungi a `backend/tests/test_db_pragmas.py`:

```python
from sqlalchemy import inspect

from app.db import Base, ensure_schema


def test_ensure_schema_creates_missing_indexes(tmp_path):
    db_path = tmp_path / "old.db"
    engine = _make_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    # Simula un DB "vecchio": rimuovi gli indici che create_all avrebbe
    # creato insieme alle tabelle, per isolare cosa fa (o non fa) ensure_schema.
    inspector = inspect(engine)
    with engine.begin() as conn:
        for idx in inspector.get_indexes("tracks"):
            conn.exec_driver_sql(f"DROP INDEX {idx['name']}")

    ensure_schema(engine)

    inspector = inspect(engine)
    index_cols = {tuple(idx["column_names"]) for idx in inspector.get_indexes("tracks")}
    assert ("archived",) in index_cols
    assert ("audio_hash",) in index_cols
    assert ("has_local_file",) in index_cols
    assert ("mbid",) in index_cols
```

- [ ] **Step 2: Esegui e verifica che fallisca**

Run: `python -m pytest tests/test_db_pragmas.py::test_ensure_schema_creates_missing_indexes -v`
Expected: FAIL — `index_cols` è vuoto perché `ensure_schema` oggi non ricrea gli indici droppati.

- [ ] **Step 3: Implementa**

In `backend/app/db.py`, dentro `ensure_schema`, subito dopo il blocco `with eng.begin() as conn:` che itera `additions.items()` e prima delle due chiamate `_migrate_drop_legacy(conn)` / `_migrate_playlist_memberships(conn)`, aggiungi:

```python
        for table in Base.metadata.tables.values():
            for idx in table.indexes:
                idx.create(bind=conn, checkfirst=True)
```

Il blocco finale di `ensure_schema` diventa:

```python
    with eng.begin() as conn:
        for table, cols in additions.items():
            existing = {c["name"] for c in inspector.get_columns(table)}
            for col, ddl in cols.items():
                if col not in existing:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}"))
        for table in Base.metadata.tables.values():
            for idx in table.indexes:
                idx.create(bind=conn, checkfirst=True)
        _migrate_drop_legacy(conn)
        _migrate_playlist_memberships(conn)
```

- [ ] **Step 4: Esegui e verifica che passi**

Run: `python -m pytest tests/test_db_pragmas.py -v`
Expected: PASS (entrambi i test del file)

- [ ] **Step 5: Verifica sul DB reale del progetto (manuale, non automatizzato)**

Run: `cd backend && source .venv/bin/activate && python -c "from app.db import ensure_schema; ensure_schema()"`
Poi: `sqlite3 data/djassistant.db "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='tracks'"` — conferma che compaiano `ix_tracks_archived`, `ix_tracks_audio_hash`, `ix_tracks_has_local_file`, `ix_tracks_mbid`.

- [ ] **Step 6: Commit**

```bash
git add backend/app/db.py backend/tests/test_db_pragmas.py
git commit -m "fix: ensure_schema crea gli indici mancanti sui DB esistenti

create_all salta gli indici delle tabelle già esistenti: i DB nati dopo
l'MVP divergevano per sempre dal modello (mancavano ix su archived,
audio_hash, has_local_file, mbid, album_id — colonne filtrate in ogni
query calda)."
```

### Task 0.3: Fix ordine route — `GET /api/playlists/library/gaps` (A6)

**Files:**
- Modify: `backend/app/routers/playlists.py:282-301` (sposta `library_gaps` prima di `playlist_gaps`)
- Modify: `frontend/lib/api.ts` (reintroduce `libraryGaps()`, rimossa come codice morto perché puntava a un endpoint irraggiungibile)
- Test: `backend/tests/test_playlist_gaps_router.py` (nuovo)

**Interfaces:**
- Produces: `frontend/lib/api.ts` esporta di nuovo `libraryGaps(): Promise<GapAnalysis>` — la usa il Task 7.x (dashboard "Lacune") in un lotto successivo.

- [ ] **Step 1: Scrivi il test che fallisce**

```python
# backend/tests/test_playlist_gaps_router.py
"""GET /api/playlists/library/gaps non deve essere catturato da /{playlist_id}/gaps (fix A6)."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app


@pytest.fixture()
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    app.dependency_overrides[get_db] = lambda: session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)
        session.close()


def test_library_gaps_not_shadowed_by_playlist_route(client):
    r = client.get("/api/playlists/library/gaps")
    assert r.status_code == 200
    body = r.json()
    assert body["scope"] == "library"
```

- [ ] **Step 2: Esegui e verifica che fallisca**

Run: `python -m pytest tests/test_playlist_gaps_router.py -v`
Expected: FAIL con 422 — FastAPI instrada su `/{playlist_id}/gaps` tentando di parsare `"library"` come `int`.

- [ ] **Step 3: Implementa (backend)**

In `backend/app/routers/playlists.py`, sposta la definizione di `library_gaps` (attualmente righe 294-301, dopo `playlist_gaps`) **prima** di `playlist_gaps`. Il blocco diventa (ordine invertito, corpo delle due funzioni invariato):

```python
@router.get("/library/gaps", response_model=GapAnalysisResponse)
def library_gaps(db: Session = Depends(get_db)):
    tracks = all_playable_tracks(db)
    gaps = analyze_gaps(tracks)
    return GapAnalysisResponse(
        scope="library", track_count=len(tracks),
        gaps=[GapOut(**g) for g in gaps],
    )


@router.get("/{playlist_id}/gaps", response_model=GapAnalysisResponse)
def playlist_gaps(playlist_id: int, db: Session = Depends(get_db)):
    if get_playlist(db, playlist_id) is None:
        raise HTTPException(status_code=404, detail="Playlist non trovata")
    tracks = tracks_for_playlist(db, playlist_id)
    gaps = analyze_gaps(tracks)
    return GapAnalysisResponse(
        scope="playlist", track_count=len(tracks),
        gaps=[GapOut(**g) for g in gaps],
    )
```

- [ ] **Step 4: Esegui e verifica che passi**

Run: `python -m pytest tests/test_playlist_gaps_router.py -v`
Expected: PASS

Run anche il test esistente per `/{playlist_id}/gaps` (cerca con `grep -rn "playlist_gaps\|/gaps" backend/tests/` il file che lo copre, es. dentro `test_library_query.py` o simile) per confermare che il riordino non ha rotto il caso con id valido.

- [ ] **Step 5: Reintroduci il client frontend**

In `frontend/lib/api.ts`, subito dopo `playlistGaps`:

```typescript
export function playlistGaps(id: number) {
  return apiGet<GapAnalysis>(`/api/playlists/${id}/gaps`);
}

export function libraryGaps() {
  return apiGet<GapAnalysis>("/api/playlists/library/gaps");
}
```

- [ ] **Step 6: Verifica build frontend**

Run: `cd frontend && npm run build`
Expected: nessun errore (la funzione non è ancora usata da nessuna pagina — verrà consumata nel Lotto 7, `libraryGaps` non chiamata è normale a questo punto e non genera warning TypeScript).

- [ ] **Step 7: Suite completa + commit**

Run: `cd backend && python -m pytest tests -q` → 432+ passed

```bash
git add backend/app/routers/playlists.py backend/tests/test_playlist_gaps_router.py frontend/lib/api.ts
git commit -m "fix: GET /api/playlists/library/gaps era catturato da /{playlist_id}/gaps

FastAPI instrada in ordine di registrazione: /library/gaps veniva parsato
come playlist_id='library' -> 422 sempre. Spostata la route library/gaps
prima di quella parametrica; reintrodotto il client frontend libraryGaps()."
```

### Task 0.4: Nav — aggiungi Transizioni e Set Builder (B3) `[Haiku]`

**Files:**
- Modify: `frontend/components/index-nav.tsx:29` (gruppo "Suona")

- [ ] **Step 1: Modifica il gruppo di navigazione**

In `frontend/components/index-nav.tsx`, sostituisci:

```typescript
  { title: "Suona", items: [{ href: "/sets", label: "Set" }] },
```

con:

```typescript
  {
    title: "Suona",
    items: [
      { href: "/set-builder", label: "Set Builder" },
      { href: "/sets", label: "Set" },
      { href: "/transitions", label: "Transizioni" },
    ],
  },
```

Nota: non serve toccare `isActive` — oggi non evidenzia nulla su `/set-builder` perché nessuna voce di nav puntava lì; aggiungendo la voce, `isActive("/set-builder")` (già `pathname.startsWith(href)`) la evidenzia correttamente da sola.

- [ ] **Step 2: Verifica manuale (nessun test automatico frontend)**

Avvia il dev server (`preview_start`), naviga su `/set-builder` e su `/transitions`, usa `preview_snapshot` per confermare che compaiano 3 voci sotto "Suona" e che quella attiva sia evidenziata (classe `text-fg-strong` sull'href corrente — verificabile anche con `preview_inspect` sul link attivo).

- [ ] **Step 3: Lint + build + commit**

Run: `cd frontend && npm run lint && npm run build`

```bash
git add frontend/components/index-nav.tsx
git commit -m "fix: Transizioni e Set Builder erano raggiungibili solo digitando l'URL

Aggiunte al gruppo 'Suona' della nav globale; isActive le evidenzia
automaticamente (nessun cambio a isActive necessario)."
```

### Task 0.5: Modal — Escape, `role=dialog`, focus iniziale (B6)

**Files:**
- Modify: `frontend/components/ui.tsx:1-15` (import), `:221-246` (componente `Modal`)

**Interfaces:**
- Produces: `Modal` mantiene la stessa firma di props (`open, onClose, title, children, footer, size`) — nessun consumer (TrackEditModal, LinkLocalFileModal, DownloadReviewModal, i modali di `sets/[id]/page.tsx`) richiede modifiche.

- [ ] **Step 1: Aggiungi gli hook React necessari**

In `frontend/components/ui.tsx`, cambia l'import in cima:

```typescript
import { X } from "lucide-react";
import { useEffect, useRef } from "react";
import { cn } from "@/lib/cn";
import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, SelectHTMLAttributes, TextareaHTMLAttributes } from "react";
```

- [ ] **Step 2: Riscrivi `Modal`**

Sostituisci l'intera funzione (righe 221-246):

```typescript
export function Modal({ open, onClose, title, children, footer, size = "md" }: {
  open: boolean; onClose: () => void; title?: ReactNode; children: ReactNode;
  footer?: ReactNode;
  size?: "md" | "lg";
}) {
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    panelRef.current?.focus();
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div
      className="fixed inset-0 z-50 grid place-items-start justify-center overflow-y-auto bg-black/70 p-4 pt-[10vh]"
      onClick={onClose}
    >
      <div
        ref={panelRef}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-labelledby={title ? "modal-title" : undefined}
        className={cn("w-full border border-border-strong bg-surface outline-none", size === "lg" ? "max-w-lg" : "max-w-md")}
        onClick={(e) => e.stopPropagation()}
      >
        {title && (
          <div className="flex items-center justify-between gap-4 border-b border-border px-5 py-3.5">
            <h3 id="modal-title" className="font-semibold uppercase tracking-wider text-fg-strong">{title}</h3>
            <button onClick={onClose} className="text-faint transition-colors hover:text-fg"><X size={18} /></button>
          </div>
        )}
        <div className="px-5 py-4">{children}</div>
        {footer && <div className="flex justify-end gap-2 border-t border-border px-5 py-3.5">{footer}</div>}
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Verifica manuale**

Avvia il dev server, apri un modal (es. "Modifica traccia" da `/tracks/[id]`), premi Escape → deve chiudersi. Con `preview_inspect` conferma `role="dialog"` e `aria-modal="true"` sul pannello. Ripeti su almeno un secondo consumer (es. modal di rinomina/eliminazione in `/sets/[id]`) per confermare che il fix centralizzato copre tutti i modali.

- [ ] **Step 4: Lint + build + commit**

Run: `cd frontend && npm run lint && npm run build`

```bash
git add frontend/components/ui.tsx
git commit -m "fix: Modal chiude con Escape e ha semantica role=dialog

Un solo intervento nel componente condiviso copre TrackEditModal,
LinkLocalFileModal, DownloadReviewModal e i modali di sets/[id]."
```

### Task 0.6: Spotify — il 401 non cancella più il refresh_token (E5)

**Files:**
- Modify: `backend/app/integrations/spotify.py:172-176`
- Test: `backend/tests/test_spotify_resilience.py` (estendi il file esistente)

**Interfaces:**
- Consumes: `SpotifyToken` da `app.models` (già importato in `spotify.py:22`), campi `kind`, `access_token`, `refresh_token`, `expires_at`, `scope`.

- [ ] **Step 1: Scrivi il test che fallisce**

Aggiungi a `backend/tests/test_spotify_resilience.py`:

```python
from datetime import datetime, timedelta, timezone

from app.models import SpotifyToken


def test_spotify_401_preserves_refresh_token(db, monkeypatch):
    token = SpotifyToken(
        kind="user", access_token="stale-token", refresh_token="refresh-abc",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    db.add(token)
    db.commit()

    client = SpotifyWebClient(db)

    class _FakeResp:
        def __init__(self, status_code, json_body=None, text=""):
            self.status_code = status_code
            self._json = json_body or {}
            self.text = text
            self.headers = {}

        def json(self):
            return self._json

    calls = {"n": 0}

    class _FakeHttp:
        def request(self, *_args, **_kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                return _FakeResp(401, text="expired")
            return _FakeResp(200, {"ok": True})

    client.http = _FakeHttp()
    refreshed = {}

    def fake_token_request(data):
        refreshed.update(data)
        return {"access_token": "fresh-token", "expires_in": 3600}

    monkeypatch.setattr(client, "_token_request", fake_token_request)

    result = client._call("GET", "/me", user=True)

    assert result == {"ok": True}
    # Il refresh_token originale e' stato usato: nessun re-login forzato.
    assert refreshed == {"grant_type": "refresh_token", "refresh_token": "refresh-abc"}
```

- [ ] **Step 2: Esegui e verifica che fallisca**

Run: `python -m pytest tests/test_spotify_resilience.py -v`
Expected: FAIL — oggi il 401 cancella la riga `SpotifyToken`, quindi `_access_token` al secondo tentativo trova `token is None` e solleva `SpotifyNotConnected`, non arriva mai a chiamare `fake_token_request`.

- [ ] **Step 3: Implementa**

In `backend/app/integrations/spotify.py`, sostituisci il blocco (righe 172-176):

```python
            if r.status_code == 401 and attempt == 0:
                # token revocato/scaduto lato server: forza refresh
                self.db.query(SpotifyToken).filter_by(kind="user" if user else "client").delete()
                self.db.commit()
                continue
```

con:

```python
            if r.status_code == 401 and attempt == 0:
                # token scaduto/revocato lato server: azzera solo l'access
                # token, cosi' _access_token imbocca il ramo refresh (kind
                # 'user' ha un refresh_token da preservare). Per kind='client'
                # (client credentials, nessun refresh possibile) la riga va
                # comunque ricreata da zero.
                kind = "user" if user else "client"
                token = self.db.query(SpotifyToken).filter_by(kind=kind).one_or_none()
                if user and token is not None and token.refresh_token:
                    token.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
                else:
                    self.db.query(SpotifyToken).filter_by(kind=kind).delete()
                self.db.commit()
                continue
```

- [ ] **Step 4: Esegui e verifica che passi**

Run: `python -m pytest tests/test_spotify_resilience.py -v`
Expected: PASS (entrambi i test del file)

- [ ] **Step 5: Suite completa + commit**

Run: `python -m pytest tests -q` → 432+ passed

```bash
git add backend/app/integrations/spotify.py backend/tests/test_spotify_resilience.py
git commit -m "fix: il 401 Spotify non cancella piu' il refresh_token

Azzera solo l'access token (expires_at nel passato): _access_token
imbocca il ramo refresh invece di forzare un re-login completo
dell'account. kind='client' (nessun refresh possibile) resta invariato."
```

### Task 0.7 [Opus review]: revisione di chiusura Lotto 0

Dispatch un agente Opus 4.8 **in sola lettura/review** (non scrive codice) con questo prompt:

> Rivedi il diff dei task 0.1-0.6 di questo lotto (`git diff master` sui file `backend/app/db.py`, `backend/app/routers/playlists.py`, `backend/app/integrations/spotify.py`, `frontend/components/index-nav.tsx`, `frontend/components/ui.tsx`, `frontend/lib/api.ts`). Verifica in particolare: (1) il PRAGMA `foreign_keys=ON` non rompe test esistenti con FK già violate nei fixture; (2) `idx.create(bind=conn, checkfirst=True)` dentro la stessa transazione del loop ALTER TABLE non causa lock su SQLite; (3) il fix Spotify 401 gestisce correttamente il caso `token is None` (nessun token mai salvato) senza sollevare eccezioni non gestite. Riporta solo problemi concreti con file:riga, nessun refactoring suggerito.

Applica eventuali fix segnalati (via Sonnet 5), rilancia `pytest tests -q`, poi apri la PR del lotto.

---

## Lotto 1 — Schema e resilienza DB (Sonnet 5)

**Obiettivo:** completare il cluster E1 lasciato fuori dai quick win: unique constraint su `EnrichmentCache`, migrazioni derivate dal modello, N+1 su `Track.playlists`, colonne legacy.

### Task 1.1: `UniqueConstraint(provider, lookup_key)` su `EnrichmentCache`

**Files:** `backend/app/models.py` (classe `EnrichmentCache`, vicino a riga 149-152), `backend/app/db.py` (`ensure_schema`, dedup difensiva prima del `CREATE UNIQUE INDEX`), test in `backend/tests/test_feature_provider.py` o nuovo `test_enrichment_cache_unique.py`.

Aggiungi al modello:
```python
__table_args__ = (UniqueConstraint("provider", "lookup_key", name="uq_enrichment_cache_provider_key"),)
```
In `ensure_schema`, prima della creazione degli indici (Task 0.2), dedup le righe esistenti per `(provider, lookup_key)` tenendo la più recente per `cached_at`, poi crea l'unique index con `CREATE UNIQUE INDEX IF NOT EXISTS`. Test: inserisci due righe con stessa coppia provider/lookup_key, verifica che il secondo insert sollevi `IntegrityError` dopo la migrazione.

### Task 1.2: Migrazioni derivate dal modello invece del dict `additions`

**Files:** `backend/app/db.py` (funzione `ensure_schema`).

Sostituisci il dict `additions` con un confronto automatico `inspector.get_columns(table.name)` vs `table.columns` per ogni tabella in `Base.metadata.tables`, generando `ALTER TABLE ... ADD COLUMN` per le colonne mancanti con default ricavato da `col.server_default` quando presente. Mantieni un piccolo dict solo per le eccezioni (default complessi non esprimibili come `server_default`). Test: rimuovi manualmente una colonna nota da un DB di test (es. `ALTER TABLE` non è reversibile in SQLite — ricrea la tabella senza la colonna via `CREATE TABLE ... AS SELECT` escludendola), esegui `ensure_schema`, verifica che la colonna ricompaia con lo stesso tipo del modello.

### Task 1.3: `selectinload(Track.playlists)` nei 3 loader N+1

**Files:** `backend/app/repositories.py` (`_SETLIST_TRACKS` vicino a riga 253, `all_playable_tracks` righe 150-159, `tracks_download_pending` righe 319-327).

```python
_SETLIST_TRACKS = selectinload(Setlist.tracks).selectinload(SetlistTrack.track).selectinload(Track.playlists)
```
Aggiungi `.options(selectinload(Track.playlists))` alle query di `all_playable_tracks` e `tracks_download_pending`. Test: usa `sqlalchemy.event.listens_for(engine, "before_cursor_execute")` per contare le query eseguite da `setlist_out(db, setlist_id)` su un set con N tracce, prima/dopo il fix (deve passare da N+1 a costante).

### Task 1.4: Rimuovi le colonne legacy `playlist_id`/`playlist_name` da `Track`

**Files:** `backend/app/models.py:69-70`, `backend/app/db.py:45-46` (dict `additions`, se non già derivato dal Task 1.2).

Verifica prima con `grep -rn "\.playlist_id\b\|\.playlist_name\b" backend/app backend/tests` che l'unico scrittore/lettore sia `_migrate_playlist_memberships` in `db.py` (la migrazione M2M stessa). Rimuovi le due colonne dal modello; aggiungi una micro-migrazione in `ensure_schema` che le droppa se ancora presenti su DB pre-esistenti (`ALTER TABLE tracks DROP COLUMN playlist_id` — richiede SQLite ≥3.35, disponibile nell'ambiente del progetto; droppa prima l'indice `ix_tracks_playlist_id`). Test: DB con le colonne legacy popolate da una fixture che simula lo stato pre-migrazione, esegui `ensure_schema`, verifica che `inspector.get_columns("tracks")` non le contenga più e che i dati siano stati spostati in `playlist_tracks` da `_migrate_playlist_memberships` (già testato altrove — verifica di non-regressione).

---

## Lotto 2 — Resilienza pipeline enrichment (Sonnet 5)

**Obiettivo:** E2, E3, E4 — il tema tecnico più impattante del report: gli errori transitori dei provider vengono cacheati come definitivi.

### Task 2.1: Commit incrementale in `enrich_features` e `fingerprint_tracks`

**Files:** `backend/app/services/feature_enrichment.py` (loop righe 290-332, commit unico riga 345), `backend/app/services/fingerprint.py` (loop, commit unico riga 127).

Sostituisci il singolo `db.commit()` finale con un commit ogni 20 tracce processate (contatore nel loop, `if processed % 20 == 0: db.commit()`), più un commit finale per il resto. In `backend/app/services/enrichment_job.py._run_job`, aggiungi un `db.commit()` nel ramo `except` prima di ri-sollevare/loggare l'errore, per salvare il lavoro già fatto. Test: monkeypatcha il provider per sollevare un'eccezione a metà batch (es. alla 25ª traccia su 50), verifica che le prime 20 abbiano `enrichment_source` popolato nel DB dopo l'eccezione (leggi da una sessione separata, non quella del job).

### Task 2.2: Non cacheare risultati parziali/errori transitori

**Files:** `backend/app/integrations/getsongbpm.py` (`ChainedFeatureProvider`, righe 296-328), `backend/app/services/feature_enrichment.py` (righe 306-316).

Fai annotare alla catena i provider falliti: `merged["_errors"] = [...]` in `ChainedFeatureProvider.lookup` quando un provider solleva `FeatureProviderError`. In `feature_enrichment.py`, non scrivere (o marca con un flag `partial=True`) le righe `EnrichmentCache` prodotte da un risultato con `_errors` non vuoto — stesso pattern già presente in `fingerprint.py:12-13`. Escludi dal merged il solo `mbid` ereditato dal context quando nessun provider ha risposto con dati propri. Test: fai fallire MusicBrainz nel fake provider chain, verifica che **non** venga scritta una riga `EnrichmentCache` (o che sia marcata ritentabile), e che un secondo run con `force=False` ritenti quella traccia.

### Task 2.3: `enrichment_source='manual'` non sovrascritto da apporti metadata-only

**Files:** `backend/app/services/feature_enrichment.py` (`_apply_features`, righe 157-160), `backend/app/repositories.py` (`update_track`, righe 133-143), `backend/app/services/track_status.py`.

In `_apply_features`, aggiorna `enrichment_source`/`enrichment_confidence` solo se `applied & {"bpm", "camelot_key"}` è non vuoto, e mai quando `track.enrichment_source == "manual"`. In `update_track`, marca `manual`/100 solo se almeno un campo feature riceve un valore non-`None`. Test: traccia con `enrichment_source="manual"`, `bpm`/`camelot_key` impostati; esegui `_apply_features` con un risultato che riempie solo `label` a confidence 40 — verifica che `enrichment_source` resti `"manual"` e lo `status` (via `compute_status`) resti `ready_for_set`, non `low_confidence`.

**Nota vincolo:** questo task tocca direttamente la regola CLAUDE.md #3 ("non sovrascrivere BPM/key esistenti, soprattutto se manual") — il test deve verificarla esplicitamente, non solo il comportamento di superficie.

### Task 2.4 [Haiku]: Cache key include la firma della catena

**Files:** `backend/app/services/feature_enrichment.py` (dove si costruisce `provider.name`, riga 278), `backend/app/integrations/getsongbpm.py` (riga 296).

Cambia `name = "chain"` in `name = "chain:" + "+".join(provider_names_attivi)` (deriva la lista dai provider effettivamente configurati, es. da `feature_provider_configured()` o dall'elenco già costruito in `get_feature_provider()`). Task meccanico — nessuna decisione di design, solo comporre una stringa da dati già disponibili.

---

## Lotto 3 — Integrazioni esterne: centralizzazione HTTP (Sonnet 5, 2 task Haiku)

**Obiettivo:** E11, E12 — 7 client duplicano lo stesso blocco retry/errore; nessun retry su 429/503 tranne Spotify.

### Task 3.1: `fetch_json` centralizzato in `_http.py`

**Files:** `backend/app/integrations/_http.py` (nuovo helper), `backend/app/integrations/{deezer,acousticbrainz,getsongbpm,lastfm,discogs,musicbrainz}.py` (migrazione al helper).

Estrai in `_http.py` una funzione `fetch_json(client, url, *, params=None, error_cls, not_found_status=None, retry_statuses=(429, 503))` che centralizza: retry con backoff su `retry_statuses` rispettando `Retry-After` (tetto massimo configurabile, pattern già in `spotify.py:163-175`), gestione `>=400` con `error_cls(f"... {status} ...")`, `404` opzionale come `None` legittimo (per AcousticBrainz), parse JSON con `ValueError` → `error_cls("risposta non JSON")`. Migra un provider alla volta (commit separato per provider, per isolare eventuali regressioni), a partire da quello con più test esistenti (`musicbrainz.py`) per validare il pattern. Ogni migrazione: esegui la suite dei test di quel provider (`pytest tests/test_<provider>.py -v`) prima e dopo, il comportamento osservabile non deve cambiare salvo il nuovo retry su 429/503.

### Task 3.2: `USER_AGENT` e `make_client` condivisi

**Files:** `backend/app/integrations/_http.py`, i 5 moduli che ridefiniscono `_USER_AGENT = "Cratory/0.1 (+http://localhost)"`.

Sposta la costante in `_http.py`, importala negli altri moduli. Aggiungi `make_client(timeout, user_agent=_USER_AGENT)` come factory condivisa per `httpx.Client`, usata a livello di modulo (non ricreata a ogni chiamata) per abilitare il riuso del connection pool (E12 — client mai chiusi/ricreati).

### Task 3.3: MusicBrainz — throttle e breaker di classe con lock

**Files:** `backend/app/integrations/musicbrainz.py` (`self._last_request`, `self._suspended`, righe 43-54).

Sposta `_last_request` e `_suspended` da attributi di istanza a variabili di classe protette da `threading.Lock()`, così tutte le istanze (create a ogni chiamata da `get_feature_provider()`) condividono il rate limit reale verso `musicbrainz.org`. Test: crea due istanze di `MusicBrainzProvider` in rapida successione, verifica che la seconda chiamata rispetti comunque l'intervallo minimo di 1.1s dal timestamp dell'ultima richiesta della *prima* istanza (usa `monkeypatch` su `time.monotonic`/`time.sleep` per non rallentare davvero il test).

### Task 3.4 [Haiku]: Last.fm User-Agent mancante

**Files:** `backend/app/integrations/lastfm.py` (riga 76).

Aggiungi `headers={"User-Agent": _USER_AGENT}` al client `httpx.Client(timeout=15)`. Una riga, nessuna decisione di design.

### Task 3.5 [Haiku]: MusicBrainz — escaping query Lucene

**Files:** `backend/app/integrations/musicbrainz.py` (riga 108).

Escapa `"` e `\` nei valori interpolati in `query = f'recording:"{title}" AND artist:"{artist}"'` prima della composizione (`title.replace("\\", "\\\\").replace('"', '\\"')`, idem per `artist`). Test: titolo con virgolette tipo `Say "Hello"`, verifica che la query costruita non contenga virgolette non scappate.

### Task 3.6: Deezer — quota (code 4) vs non-trovato (code 800)

**Files:** `backend/app/integrations/deezer.py` (righe 61-66).

Distingui `data["error"]["code"] == 4` (quota exceeded, HTTP 200) → solleva `FeatureProviderError` (transitorio, non cacheare — si collega al Task 2.2); `code == 800` (no data) → `None` legittimo. Test: fake response con `{"error": {"code": 4, ...}}`, verifica che sollevi l'eccezione invece di ritornare `None`.

---

## Lotto 4 — Acquisizione Soulseek e libreria (Sonnet 5)

**Obiettivo:** A7 (HIGH), E6, E7, E8, E9, A8, A19, A20 — il cluster con il bug funzionale più concreto.

### Task 4.1: Possesso non impostato quando il dedup ISRC fonde su traccia esistente (A7, HIGH)

**Files:** `backend/app/services/soulseek_download_job.py` (`_import_to_library`, righe 150-161), `backend/app/services/playlist_import.py` (`_find_existing`, righe 100-103).

Dopo `import_playlist`, risolvi la Track con la stessa catena di identità del dedup: prima `Track.isrc == nt.isrc` (se il file ha un tag ISRC), poi `platform_track_id == digest`, poi `Track.local_path == path`. Chiama `attach_local_file` sulla Track risolta, qualunque essa sia. Test: crea una Track esistente `platform="spotify"` con un dato ISRC; scarica (mock) un file con lo stesso ISRC nei tag; verifica che dopo il job `has_local_file=True` sulla Track esistente (non su una nuova Track `local_files` mai collegata).

### Task 4.2: Cancellazione transfer abbandonati + match per id (E6)

**Files:** `backend/app/integrations/slskd.py` (aggiungi `cancel_download`, `transfer_state` righe 114-120), `backend/app/services/soulseek_download_job.py` (righe 87-100, 193-202).

Aggiungi `SlskdClient.cancel_download(username, id)` (`DELETE /transfers/downloads/{username}/{id}?remove=true`). Chiamalo quando `_wait_for_download` abbandona un candidato prima di passare al successivo in `MAX_ATTEMPTS`. Cambia `transfer_state` per identificare il transfer per `id` (rileggere i download dopo l'enqueue e agganciare il record più recente con quel filename) invece che per solo filename. Test: mock client slskd con due record storici stesso filename (uno `Completed` vecchio, uno nuovo `InProgress`), verifica che `transfer_state` ritorni lo stato del nuovo record.

### Task 4.3: `needs_review` persiste il path + retry limitato (A8)

**Files:** `backend/app/services/soulseek_download_job.py` (`_attempt_download` righe 126-130, `start_retry_job` righe 304-312), `backend/app/repositories.py` (query `tracks_download_pending`, campo nuovo su `Track` o riuso di `last_download_reason` con path strutturato).

Persisti il path del file scaricato-ma-sospetto (nuova colonna `Track.last_download_path` o encoding nella reason). Esponi in `POST /api/tracks/{id}/link-file` (già esistente) la possibilità di "collegare comunque". Limita `retry-pending` agli esiti `not_found|failed` (escludi `needs_review` dal filtro di `tracks_download_pending` usato dal retry). Test: simula un esito `needs_review` con path noto, verifica che sia in `GET /api/tracks/{id}` (o endpoint equivalente) e che `retry-pending` non lo riprocessi.

### Task 4.4: Fuzzy match non ruba tracce già possedute (E7)

**Files:** `backend/app/services/library_index.py` (`_find_track`, righe 49-54).

Nel fallback fuzzy (e nel match ISRC), scarta i candidati con `has_local_file=True` e `audio_hash` valorizzato diverso dal digest corrente — in quel caso crea una nuova Track per il nuovo file invece di sovrascrivere. Sostituisci l'`ilike` non escapato con confronto `func.lower(col) == value.lower()` (introduce l'helper `ci_equals` condiviso, riusato anche in `manual_import.py` e `playlist_import.py` per il Task 4.6). Test: due file diversi (hash diversi) stesso artista+titolo; indicizza il primo (Track posseduta), poi il secondo — verifica che generi una NUOVA Track invece di sovrascrivere `local_path` della prima.

### Task 4.5: `attach_local_file` salva mtime/size + guardia possesso duplicato (E7)

**Files:** `backend/app/services/acquisition.py` (`attach_local_file`, righe 22-35), `backend/app/services/library_index.py` (`link_local_file`).

Valorizza `local_mtime`/`local_size` in `attach_local_file` (stessa semantica di `_own` in `library_index.py`). In `link_local_file`, prima di collegare, verifica che nessun'altra Track abbia già lo stesso `local_path` o `audio_hash`; se sì, solleva un errore esplicito invece di creare un doppione silenzioso. Test: collega lo stesso file a due Track diverse in sequenza, verifica che il secondo collegamento fallisca con un errore leggibile.

### Task 4.6: Path config con `~` espansi (E8)

**Files:** `backend/app/core/config.py` (campi `library_root`, `archive_root`, `slskd_download_dir`), helper `ci_equals` dal Task 4.4.

Aggiungi un `field_validator` Pydantic sui campi path che applichi `Path(v).expanduser()` quando non vuoti. Test: imposta `SLSKD_DOWNLOAD_DIR=~/Music/Downloads` in env, verifica che `settings.slskd_download_dir` sia già espanso alla home reale (non contenga `~`).

### Task 4.7 [Haiku]: `ilike` → `ci_equals` nei punti di dedup rimanenti

**Files:** `backend/app/services/manual_import.py` (righe 50-53), `backend/app/services/playlist_import.py` (righe 173-176), `backend/app/routers/tracks.py` (righe 104-105).

Sostituisci i 3 `ilike(value)` "esatti" rimanenti con l'helper `ci_equals` introdotto al Task 4.4 (import + call site, nessuna nuova logica).

### Task 4.8: Auto-pick — filtra per confidenza prima di ordinare per score (A19)

**Files:** `backend/app/services/soulseek_download_job.py` (`_process_item`, riga 189), `backend/app/services/soulseek_select.py` (`best_for_auto`, righe 200-207).

Filtra prima i candidati con `confidence >= AUTO_PICK_MIN_CONFIDENCE`, poi applica il fallback multi-utente su quella lista già ordinata per score. Vai in `needs_review` solo se nessun candidato supera la soglia. Test: due candidati, il primo per score con confidence bassa, il secondo con confidence alta ma score più basso — verifica che l'auto-pick scelga il secondo.

### Task 4.9: `DOWNLOAD_TIMEOUT` con stall-detection (A20)

**Files:** `backend/app/services/soulseek_download_job.py` (`_wait_for_download`, righe 87-100), `backend/app/integrations/slskd.py`.

Leggi `bytesTransferred` dal record transfer; arrenditi solo se il progresso è fermo per N secondi (es. 60s), azzerando il timer quando lo stato passa a `InProgress` con byte crescenti. Mantieni un tetto assoluto (es. 15 min) come backstop. Test: mock transfer con `bytesTransferred` crescente ogni poll, verifica che non scada prima del tetto assoluto anche oltre il vecchio `DOWNLOAD_TIMEOUT` di 180s.

---

## Lotto 5 — Scoring, set builder, discovery (Sonnet 5; `[Opus review]` sui task di scoring per il rischio di regressione sui numeri)

**Obiettivo:** A3, A4, A5, A21-A23, E10 — qualità dello scoring e delle transizioni, il cuore del Set Builder.

### Task 5.1: Scoring BPM con half/double-time (A4)

**Files:** `backend/app/services/scoring.py` (`_bpm_points` righe 199-209, `bpm_compatibility_score` righe 261-272).

Calcola la differenza come `min(|a-b|, |a*2-b|, |a/2-b|)` con una lieve penalità per il rapporto 2:1 (es. -5 punti se il match è half/double invece che diretto). Esprimi le soglie in percentuale del BPM di partenza invece di valori assoluti (`±8` fisso → `±4%`). Aggiorna `mixing_tip` (righe 96-139) per menzionare esplicitamente l'opzione half/double-time quando rilevante. **Attenzione:** `test_scoring.py::test_bpm_tiers_ordering` e `test_bpm_jump_warning` verificano ordinamenti relativi — vanno estesi con casi half-time (85→170), non riscritti (l'ordinamento `perfect > good > risky > hard` deve restare vero). Test nuovo: `bpm_compatibility_score(85, 170)` deve dare un punteggio alto (non 5/50 come oggi), inferiore a un match diretto identico ma superiore a un mismatch reale.

### Task 5.2: Semantica reale alle 5 strategie no-op (A3)

**Files:** `backend/app/services/set_generator.py` (`_STRATEGY_CURVE` righe 28-36, `_desired_bpm` righe 89-91).

Dai un esponente distinto a `contrast` (attiva implicitamente `allow_sharp_changes` + bonus su oscillazioni di energia), `experimental` (bonus cambi key/genere, riusa `genre_similarity_score`), `progressive` (vincolo di monotonia BPM), `closing` (curva discendente + energia in scarico). `peak_time` e `warm_up` restano invariati. Test: per ciascuna strategia, genera un set con lo stesso pool di tracce e verifica che la sequenza risultante differisca da quella di `smooth` in almeno una proprietà misurabile (es. `progressive` → BPM monotono crescente; `closing` → energia media dell'ultimo terzo < primo terzo).

### Task 5.3: Ranking multi-segnale per le 60 candidate senza seed/start_bpm (A5)

**Files:** `backend/app/services/ai_agent.py` (`_rank_candidates`, righe 108-122).

Quando `relevance=0` per tutte (nessun seed artista né start_bpm), applica un ranking di fallback: privilegia tracce con feature complete (bpm+key+energy), aderenza a `req.genre`/energy target se forniti, e campionamento stratificato sull'arco BPM e sulle chiavi Camelot. Test: pool di 200 tracce senza seed/start_bpm, verifica che le 60 selezionate coprano un range di BPM (es. deviazione standard > una soglia) invece di essere le prime 60 per id di inserimento.

### Task 5.4: Gap analysis con soglie derivate dalla distribuzione (A21)

**Files:** `backend/app/services/gap_analysis.py` (righe 17-19, `_check_bpm_bridges` righe 72-88).

Deriva `opener`/`peak` dai percentili BPM della playlist (25°/75°) invece delle costanti fisse 120/126, con fallback alle costanti quando le tracce con BPM sono poche (< 10). Soglia bridge in percentuale del BPM mediano invece di 6 BPM assoluti. Test: playlist DnB (tutte >170 BPM) non deve più generare "missing_openers" quando esiste una traccia relativamente più lenta delle altre.

### Task 5.5: Energia nello score composito di transizione (A23)

**Files:** `backend/app/services/scoring.py` (`score_transition` righe 223-252), `backend/app/services/alternatives.py` (righe 52-55).

Aggiungi un termine energia quando entrambe le tracce ce l'hanno, ribilanciando i pesi (es. 45 BPM / 35 key / 10 energia / 10 durata), comportamento invariato (neutro) quando il dato manca. Test esistenti in `test_scoring.py` sui pesi assoluti vanno aggiornati di conseguenza — verifica che l'ordinamento relativo bpm > key resti vero, aggiungi un test che un crollo di energia peggiori lo score a parità di BPM/key.

### Task 5.6: Ruoli e note stantie dopo edit del set (A22)

**Files:** `backend/app/services/set_editor.py` (`recompute_transitions`, righe 34-47), `backend/app/services/set_generator.py` (`assign_roles`).

In `recompute_transitions`, azzera `transition_note` sulle tracce la cui coppia prev→next è cambiata; richiama `assign_roles(len(ordered))` dopo ogni modifica alla sequenza (move/remove/replace). Test: sposta la prima traccia in fondo, verifica che il nuovo brano di apertura abbia `role="warmup"` (non il ruolo residuo della generazione originale) e che `transition_note` della coppia cambiata sia `None`.

### Task 5.7 [Haiku]: `/api/transitions` — elimina il doppio calcolo dello score (E10)

**Files:** `backend/app/routers/transitions.py` (`_score_out` righe 14-21, `_ranked` righe 24-35), `backend/app/services/scoring.py` (`classify_transition`, riga 62).

Fai accettare a `classify_transition` uno score già calcolato come parametro opzionale (`classify_transition(track_a, track_b, score=None)` — se `None`, calcola come oggi). In `_ranked`, prima passata solo `score_transition` per tutte le coppie, ordina e tronca a `limit`, seconda passata `classify_transition(..., score=already_computed)` solo sui top-N.

### Task 5.8 [Haiku]: `_explain` del Discovery con validazione Pydantic (E10)

**Files:** `backend/app/schemas.py` (nuovo `AIExplanationsOut`), `backend/app/services/discovery.py` (`_explain`, righe 260-281).

Definisci `class AIExplanationsOut(BaseModel): explanations: list[dict]` (o più tipizzato: `class Explanation(BaseModel): index: int; text: str`). In `_explain`, usa `AIExplanationsOut.model_validate(raw)` invece del parsing manuale via `.get()`, con lo stesso fallback best-effort su `ValidationError`.

---

## Lotto 6 — Flusso import/enrichment funzionale (Sonnet 5)

**Obiettivo:** A9-A18 — coda enrichment, dedup, sync Spotify, fingerprint→enrichment, set editor insert, dig.

### Task 6.1: Coda FIFO per l'enrichment concorrente (A9)

**Files:** `backend/app/services/enrichment_job.py` (`start_job`, righe 85-93).

Aggiungi una lista in-memory di scope pendenti (`playlist_id`/`track_ids`/`force`); se il job è `running`, accoda invece di ignorare, e ritorna `{"queued": True, ...stato attuale}`. A fine `_run_job`, se la coda non è vuota, drena il prossimo scope. Test: avvia un job lungo (mock provider con sleep), chiama `start_job` una seconda volta con scope diverso mentre il primo gira, verifica che la risposta abbia `queued=True` e che al termine del primo job il secondo scope venga processato senza intervento esterno.

### Task 6.2: Dedup livello 3 (artist+title+duration) nell'import (A11)

**Files:** `backend/app/services/playlist_import.py` (`_find_existing`, righe 98-115).

Aggiungi il terzo livello documentato in CLAUDE.md (`ISRC -> platform_track_id -> artist+title+duration -> fuzzy`): match esatto case-insensitive artist+title (+durata ±2s quando entrambe presenti), limitato alle tracce non `local_files` (l'identità locale resta l'hash). Riusa `ci_equals` dal Lotto 4. Test: importa una traccia via manual import, poi importa da Spotify (mock) la stessa traccia (stesso artist+title+durata, nessun ISRC comune) — verifica che si aggiorni la Track esistente invece di crearne una seconda.

### Task 6.3: Proteggi le tracce Discovery dalla prune del sync (A12)

**Files:** `backend/app/models.py` (nuova colonna `PlaylistTrack.added_by`), `backend/app/routers/playlists.py` (`add_discovered_track` righe 249-279, `sync_playlist`), `backend/app/services/playlist_import.py` (`prune`, righe 248-258).

Aggiungi `added_by: str = "sync"` (default) sulla tabella associativa `playlist_tracks`; imposta `"cratory"` quando la membership viene creata da `add_discovered_track`. In `prune`, salta le membership `added_by="cratory"` il cui `spotify_error` è valorizzato (write-back mai riuscito). Test: aggiungi una traccia via discovery con write-back Spotify fallito (mock), esegui `sync_playlist` con `prune=True`, verifica che la membership sopravviva.

### Task 6.4: MBID dal fingerprinting invalida la cache e avvia re-enrichment (A13)

**Files:** `backend/app/services/fingerprint.py` (`fingerprint_tracks`), `backend/app/services/fingerprint_job.py` (righe 58-77).

Raccogli gli id delle tracce identificate durante `fingerprint_tracks`; a fine job, cancella le loro righe `EnrichmentCache` (provider `chain:*` da Lotto 2) e chiama `enrichment_job.start_job(track_ids=identified, force=True)` — stesso pattern già usato in `library_index_job._autoenrich_created`. Test: traccia con cache "chain" pre-esistente senza mbid; dopo il fingerprint job, verifica che la cache per quella traccia sia stata invalidata e che l'enrichment sia stato ri-lanciato con `force=True`.

### Task 6.5: Endpoint `POST /api/sets/{id}/tracks` per inserire una traccia scelta (A14)

**Files:** `backend/app/routers/sets.py` (nuovo endpoint), `backend/app/services/set_editor.py` (nuova funzione `insert_track`, riusa `_renumber`/`recompute_transitions`).

`insert_track(db, setlist_id, track_id, position=None)`: default in coda, rispetta `owned_only` con 422 come già fa `replace_track`. Riusa `_renumber` (righe 29-47) e `recompute_transitions`. Test: inserisci una traccia in posizione 2 di un set da 5, verifica che le posizioni 2-6 si rinumerino e che le transizioni per le coppie coinvolte siano ricalcolate; verifica il 422 quando `owned_only=True` e la traccia non ha `local_path`.

### Task 6.6: Lead del dig salvano label/style/year (A15)

**Files:** `backend/app/schemas.py` (`DiscoveryAddRequest`, righe 395-404), `backend/app/services/playlist_import.py` (`import_single_track`, righe 148-159).

Estendi `DiscoveryAddRequest` con `label: str | None = None`, `genre: str | None = None`, `year: int | None = None` (opzionali, puliti con `_clean_label` già esistente). Passa questi campi da `import_single_track` alla Track creata/aggiornata. Test: salva un lead con `label="Ninja Tune"`, verifica che la Track risultante abbia `label="Ninja Tune"`.

### Task 6.7 [Haiku]: Discovery expand riusa `_dedup_key` del dig (A16)

**Files:** `backend/app/services/discovery.py` (`_drop_in_library`, righe 200-204), `backend/app/services/discovery_dig.py` (`_dedup_key`/`_dedup_title`, righe 104-116).

Sposta `_dedup_key` in un modulo condiviso (o importalo direttamente da `discovery_dig` in `discovery.py`) e usalo in `_drop_in_library` invece del confronto esatto artist+title. Nessuna nuova logica, solo riuso.

---

## Lotto 7 — Frontend: continuità di flusso (Sonnet 5)

**Obiettivo:** B1, B2, B4, B5 — le 4 rotture di flusso ad alta priorità del report.

### Task 7.1: Filtri/sort/paginazione della Libreria nell'URL (B1)

**Files:** `frontend/app/library/page.tsx` (stato in `useState`, righe 33-49).

Serializza filtri/sort/offset con `useSearchParams` + `router.replace` (shallow, senza rimontare la pagina) invece di `useState` locale; idrata lo stato iniziale da `searchParams` al mount. Applica lo stesso pattern a `frontend/app/downloads/issues/page.tsx` (filtro esito). Verifica manuale: applica un filtro, apri una traccia, premi "indietro" nel browser — i filtri devono essere ancora applicati.

### Task 7.2: Indicatore di possesso nel dettaglio playlist (B2)

**Files:** `frontend/app/playlists/[id]/page.tsx` (righe 307-368), riusa il badge `FILE`/`SCARTATA` già presente in `frontend/app/library/page.tsx:163-164`.

Aggiungi una colonna/badge di possesso per riga (stesso stile della Libreria) e il filtro "Possesso: tutte/possedute/wishlist" nella marginalia (righe 307-323), riusando il pattern già in `library/page.tsx:105-109`. Verifica manuale con `preview_screenshot` su una playlist con tracce miste possedute/non possedute.

### Task 7.3: Generazione set nella barra job globale (B4)

**Files:** `frontend/components/jobs-provider.tsx` (poller righe 110-113, API context righe 40-45), `frontend/app/set-builder/page.tsx` (mount effect righe 102-106, polling locale righe 126-146).

Aggiungi `generate-status` al `pollOnce` del provider (nuova riga job "Generazione set" con href `/set-builder`), esponendola nel context come già fatto per `download`/`libraryIndex`/`fingerprint`. Nel mount effect del builder, leggi lo stato dal provider invece di un polling locale: se `status==="running"`, mostra la card di progresso e riprendi a leggerlo dal context; se `"done"` recente, ricarica il setlist risultante. Elimina il polling locale duplicato. Verifica manuale: avvia una generazione, naviga via, torna su `/set-builder` — il progresso deve essere ancora visibile.

### Task 7.4: Link dal set generato al set modificabile (B5)

**Files:** `frontend/app/set-builder/page.tsx` (`SetResult`, righe 351-409), `frontend/app/sets/page.tsx`.

Nel `CardHeader` di `SetResult`, aggiungi un'azione primaria "Apri e modifica" verso `/sets/{setlist.id}`. Per la proliferazione di bozze: "Rigenera" con lo stesso set attivo sostituisce la bozza corrente (DELETE del vecchio setlist_id + create), un CTA esplicito "Conserva" la promuove (nessuna azione, resta semplicemente in `/sets`). Verifica manuale: genera un set, clicca "Apri e modifica", conferma di atterrare su `/sets/{id}` con tutte le azioni di editing disponibili.

---

## Lotto 8 — Frontend: UX media/bassa priorità (mix Sonnet 5 / Haiku)

**Obiettivo:** B7-B18 dal report (etichette stato, window.confirm, feedback azioni, riordino set, stati loading/empty, ecc.). Ogni task è indipendente — eseguibili in qualsiasi ordine, anche in parallelo da agenti diversi.

### Task 8.1: `lib/status.ts` condiviso per le etichette di stato (B8)

**Files:** nuovo `frontend/lib/status.ts`, consumer in `library/page.tsx:15-18`, `playlists/[id]/page.tsx:360`, `tracks/[id]/page.tsx:66,80-81`.

Esporta `STATUS_LABEL: Record<TrackStatus, string>` con label italiane brevi uniche (PRONTA, ARRICCHITA, IMPORTATA, NO FEATURE, BASSA CONF), sostituisci le tre rese incoerenti nei 3 file.

### Task 8.2: `ConfirmModal` riusabile per le azioni distruttive (B9)

**Files:** nuovo componente in `frontend/components/ui.tsx` (sopra il `Modal` esistente), consumer: `frontend/app/playlists/page.tsx:62`, `frontend/app/playlists/[id]/page.tsx:173`, `frontend/app/downloads/issues/page.tsx:65`, `frontend/app/shazam/page.tsx:84`.

Costruisci `ConfirmModal({open, onClose, onConfirm, title, body})` sul `Modal` del Lotto 0 (eredita Escape/focus/role gratis), bottone conferma `variant="danger"`. Sostituisci i 4 `window.confirm` con il componente.

### Task 8.3 [Haiku]: Import Spotify — auto-load elenco playlist (B10)

**Files:** `frontend/app/playlists/import-spotify/page.tsx` (righe 110-117).

Aggiungi `useEffect` che chiama il caricamento playlist quando `connected` diventa `true`, mantenendo "Carica" come refresh manuale.

### Task 8.4: Feedback dopo il grab Soulseek manuale (B11 parte 1)

**Files:** `frontend/app/downloads/page.tsx` (righe 110-118).

Stato per-candidato (`idle → "in coda ✓"`) con bottone disabilitato dopo il grab, per evitare doppio click prima che la barra job globale rifletta lo stato (fino a 2s di lag).

### Task 8.5: Provenienza enrichment nel dettaglio traccia (B11 parte 2)

**Files:** `frontend/app/tracks/[id]/page.tsx` (tabella Metadata righe 62-68, `enrich()` righe 41-51).

Aggiungi righe "Fonte enrichment" (`enrichment_source`) e "Confidenza" (`enrichment_confidence`) alla tabella — questi campi esistono già in `lib/api.ts:31-32`, sono già nella response API, mancava solo la resa. Dopo `enrich()`, confronta i campi chiave prima/dopo e mostra un esito ("Aggiornati BPM, key" oppure "Nessuna feature trovata").

### Task 8.6 [Haiku]: LinkLocalFileModal auto-avvia la ricerca (B11 parte 3)

**Files:** `frontend/components/link-local-file-modal.tsx` (righe 44-45).

`useEffect` al mount che chiama `runSearch()` se la query precompilata ha ≥2 caratteri.

### Task 8.7: Riordino set con drag-and-drop (o update ottimistico) (B12)

**Files:** `frontend/app/sets/[id]/page.tsx` (righe 73-75, 213-218).

Minimo: update ottimistico sulle frecce esistenti (swap locale immediato, sync in background con rollback su errore) per eliminare l'attesa percepita — non richiede drag-and-drop nativo per chiudere il finding.

### Task 8.8: Stati loading/empty/error su Transizioni (B13/B18)

**Files:** `frontend/app/transitions/page.tsx` (righe 32-35, 99-118).

Stato `results: TransitionCandidate[] | null`; `<Loading />` mentre `null`, `EmptyState` quando `[]`, `Alert tone="danger"` sull'errore (rimuovi il `catch → setResults([])` che ingoia l'errore).

### Task 8.9 [Haiku]: Barra job — errori persistenti (B14)

**Files:** `frontend/components/jobs-provider.tsx` (riga 58, `pushOutcome` righe 85-93).

Differenzia `OUTCOME_MS`: `done` resta transiente (4000ms), `error` diventa persistente con una × di dismiss manuale sulla riga.

### Task 8.10: Empty state Libreria — distingui filtri attivi da libreria vuota (B18 parte)

**Files:** `frontend/app/library/page.tsx` (righe 90-121, 177-179).

Se almeno un filtro è attivo, mostra "Nessuna traccia con questi filtri" + bottone "Azzera filtri" (reset di tutti gli state); solo a libreria realmente vuota suggerisci l'import.

---

## Lotto 9 — Frontend tecnico (Sonnet 5)

**Obiettivo:** B19-B28 — polling duplicato, AbortController, monolite api.ts, ApiError, lazy loading, URL relativo.

### Task 9.1: Elimina il polling duplicato (B19)

**Files:** `frontend/components/jobs-provider.tsx` (context righe 40-45, poller 110-113), `frontend/app/settings/page.tsx` (righe 206-216), `frontend/app/playlists/page.tsx` (righe 38-49), `frontend/app/playlists/[id]/page.tsx` (righe 82-93), `frontend/app/shazam/page.tsx` (righe 43-54).

Estendi `JobsApi` con `enrich: FeatureEnrichJob | null` e `shazam: ShazamIdentifyState | null` (il provider li polla già, mancava solo l'esposizione). Elimina i 4 `startPolling`/`stopPolling` duplicati, fai leggere le pagine da `useJobs()`.

### Task 9.2: `ApiError` con status code (B22)

**Files:** `frontend/lib/api.ts` (`handle`, righe 432-445), i 9 file con `err()` duplicato.

```typescript
export class ApiError extends Error {
  constructor(public status: number, detail: string) {
    super(detail);
  }
}
```
`handle()` lancia `ApiError` invece di `Error` piatto. Esporta `errMsg(e: unknown): string` unica, cancella le 9 copie locali di `err()`.

### Task 9.3: AbortController / guardia di sequenza (B20)

**Files:** `frontend/lib/api.ts` (`apiGet`/`apiPost`, aggiungi `{signal?: AbortSignal}`), `frontend/app/library/page.tsx` (effect righe 51-64), `frontend/app/tracks/[id]/page.tsx` (righe 53-57), `frontend/app/sets/[id]/page.tsx` (`loadAlternatives`, righe 58-71).

Aggiungi `signal` opzionale ad `apiGet`/`apiPost`/`apiSend`. Negli effect di library e tracks/[id], crea `AbortController` per richiesta e abortiscilo nel cleanup (ignora `AbortError`). Per `loadAlternatives`, un token di sequenza incrementale basta (confronta prima di `setAltItems`).

### Task 9.4 [Haiku]: `loading="lazy"` su tutte le `<img>` di copertina (B23 parte 1)

**Files:** `frontend/app/library/page.tsx:150`, `frontend/app/playlists/[id]/page.tsx:350`, `frontend/app/sets/[id]/page.tsx:196`, `frontend/app/shazam/page.tsx:138`, `frontend/app/playlists/page.tsx:121`, `frontend/app/discovery/page.tsx:374`.

Aggiungi `loading="lazy" decoding="async"` a ogni `<img>` di copertina nei 6 file. Task puramente meccanico.

### Task 9.5: API URL relativo + rewrite Next.js (B24)

**Files:** `frontend/lib/api.ts:1`, `frontend/next.config.ts`.

```typescript
const API = process.env.NEXT_PUBLIC_API_URL ?? "";
```
In `next.config.ts`, aggiungi `rewrites()` che proxya `/api/:path*` verso `${process.env.BACKEND_URL ?? "http://localhost:8000"}/api/:path*`. Verifica manuale: accedi all'app da un altro device della LAN, conferma che le chiamate funzionino (non più `localhost:8000` del device sbagliato).

### Task 9.6 [Haiku]: `cn()` con `tailwind-merge` (B25)

**Files:** `frontend/lib/cn.ts`.

```bash
npm install tailwind-merge
```
```typescript
import { twMerge } from "tailwind-merge";
export const cn = (...classes: (string | undefined | false)[]) =>
  twMerge(classes.filter(Boolean).join(" "));
```

---

## Lotto 10 — Chiusura flusso prodotto e copertura test (Sonnet 5)

**Obiettivo:** A1, A2 (i due findings "product" ad alta priorità) + E13-E15 (buchi di test).

### Task 10.1: Export set — M3U + download reale (A1)

**Files:** `backend/app/routers/sets.py` (`export`, righe 153-209), `frontend/app/sets/[id]/page.tsx` (righe 96-99, 223), `frontend/app/set-builder/page.tsx` (righe 181-184, 405), `frontend/lib/api.ts` (`exportSet`, righe 479-483).

Aggiungi `format=m3u` all'endpoint: `#EXTM3U`/`#EXTINF` con `local_path` per le tracce possedute, commento per quelle senza file. Includi `local_path`/`has_local_file` nel CSV esistente. Frontend: bottone "Copia" (`navigator.clipboard`, conferma ✓ come in `settings/page.tsx:92`) e "Scarica file" (Blob + `a[download]`). Fai passare `exportSet` da `handle()` per uniformare gli errori (bug collegato in B21). Test backend: `GET /api/sets/{id}/export?format=m3u` su un set con tracce miste possedute/non possedute, verifica header `#EXTM3U` e una riga `#EXTINF` per traccia posseduta con il suo `local_path`.

### Task 10.2: Shazam fase 2 lite — cross-match libreria + salva lead (A2)

**Files:** `backend/app/routers/dj_sets.py` (`GET /api/shazam/sets/{id}`), `backend/app/services/mix_identify.py`, riusa la catena dedup del Task 6.2 e `POST /api/discovery/add`.

Arricchisci la response del dettaglio set Shazam con un campo `in_library: "isrc" | "fuzzy" | null` e `has_local_file: bool` per traccia (riusa la stessa catena di dedup di `playlist_import._find_existing`, sola lettura — non crea Track). Frontend `frontend/app/shazam/[id]/page.tsx` (righe 59-81): badge IN LIBRERIA/POSSEDUTA/NUOVA per riga, bottone "Salva in libreria" (riusa `discoveryAddLead`), "Salva tutte le nuove". Test backend: `DjSetTrack` con ISRC che matcha una Track esistente, verifica che la response includa `in_library="isrc"`.

### Task 10.3: Test per `mix_identify_job.py` — copertura zero (E13)

**Files:** nuovo `backend/tests/test_mix_identify_job.py`, pattern da `backend/tests/test_soulseek_download_job.py`.

4 casi: (1) URL già `done` ritorna `cached=True` senza rianalisi; (2) URL con `status='error'` viene ripulito (tracce cancellate, error azzerato) e rianalizzato; (3) eccezione in `identify_set` persiste `DjSet.status='error'` con messaggio; (4) secondo `start_job` mentre `running` ritorna lo stato senza avviare un secondo thread.

### Task 10.4: Guardia anti doppio-avvio testata sui 5 job (E13)

**Files:** test aggiuntivi in `test_soulseek_download_job.py`, `test_library_index_router.py`, `test_fingerprint_router.py`, nuovo test per `enrichment_job.py` e `routers/sets.py generate-async`.

Per ogni modulo job: forza `_state["status"]="running"` (o blocca con `threading.Event`), verifica che un secondo `start_job` ritorni lo stato corrente senza rilanciare (contatore sul target monkeypatchato). Per `sets.py`: test `TestClient` su `generate-async` con 409 quando `use_ai` e AI non configurata.

### Task 10.5 [Haiku]: Rimuovi l'assert tautologico (E14)

**Files:** `backend/tests/test_set_editing.py:168`.

Sostituisci `assert target_pos is not None or True` con un test deterministico: seed esplicito di due tracce dello stesso artista (`seed_tracks` usa `Artist {i % 5}`, i duplicati esistono già), scegli una posizione con un'alternativa `same_artist` garantita, `assert alts` + corrispondenza artista.

### Task 10.6: Fixture condivisa `client_db` in conftest (E14)

**Files:** `backend/tests/conftest.py` (nuova fixture), migra progressivamente i 16 file duplicati quando li tocchi (non big-bang in questo task — solo introduci la fixture + autouse reset).

```python
@pytest.fixture()
def client_db():
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    from app.db import get_db
    from app.main import app

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    app.dependency_overrides[get_db] = lambda: session
    try:
        yield TestClient(app), session
    finally:
        app.dependency_overrides.pop(get_db, None)
        session.close()
```

Aggiungi anche una fixture `autouse` `_reset_job_state` che salva/ripristina i dict `_state` dei 5 moduli job a inizio/fine test.

---

## Note di sequenziamento

- I Lotti 0-4 sono indipendenti tra loro (nessuna dipendenza di file) — possono girare in sessioni separate in qualsiasi ordine dopo il Lotto 0.
- Il Lotto 5 dipende dal Lotto 2 solo per la naming convention `chain:*` del Task 2.4 (cosmetico, non blocca).
- Il Lotto 6 dipende dal Lotto 4 (`ci_equals`) e dal Lotto 2 (`chain:*` cache key per il Task 6.4).
- Il Lotto 7 dipende dal Task 0.3 (`libraryGaps()` reintrodotto) solo se si vuole aggiungere il blocco "Lacune" in dashboard — altrimenti indipendente.
- I Lotti 8-9 sono completamente indipendenti e paralleli tra loro e con tutto il resto.
- Il Lotto 10 dipende dal Lotto 6 (Task 6.2, catena dedup) per il Task 10.2.

Per l'esecuzione: `Workflow` con `subagent-driven-development` un lotto alla volta, oppure dispatch manuale di agenti Sonnet 5 per singolo task quando i lotti sono piccoli (Lotto 0, 8, 9).
