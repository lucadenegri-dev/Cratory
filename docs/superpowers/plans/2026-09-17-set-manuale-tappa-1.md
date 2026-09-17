# Set manuale, tappa 1 (il gesto base) — piano di implementazione

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Un DJ apre una playlist, preme "Prepara un set", mette in fila tracce, le sposta, le toglie, lascia un varco, scrive un appunto per riga, riavvia e ritrova tutto. Il materiale è la playlist letta aggiornata più la ricerca in libreria.

**Architecture:** Nessun modello nuovo: `Setlist` guadagna `kind`, `source_playlist_id`, `notes`, `revision`; `SetlistTrack` diventa nullable su `track_id` (varco) e guadagna `slot_kind`, `block_id`, `note`; nasce `SetlistBlock`. Un servizio deterministico `services/manual_set.py` fa tutte le mutazioni in una transazione e incrementa `revision`; il router `routers/sets.py` espone gli endpoint nuovi con righe identificate **per id** e 409 su `expected_revision` non coincidente. Il frontend aggiunge una pagina `/sets/manual?id=…` con tre pannelli (materiale, percorso, dettaglio) sopra il player esistente.

**Tech Stack:** Python 3 + FastAPI + SQLAlchemy 2 (SQLite, migrazioni idempotenti in `db.py`, niente Alembic), Pydantic v2, pytest. Next.js 16 App Router, React, Tailwind (design system in `docs/DESIGN.md`), vitest + @testing-library/react, Playwright.

**Spec:** `docs/superpowers/specs/2026-09-15-set-builder-workbench.md` (sezioni 1, 3, 4 e "Tappa 1").

## Global Constraints

- Backend: `cd backend && .venv/bin/python -m pytest tests -q` deve restare verde. I test usano DB in memoria (`db` fixture di `conftest.py`, foreign key accese) o `TestClient(app)` con `app.dependency_overrides[get_db]`. Mai il DB personale.
- Migrazioni: solo dentro `ensure_schema` in `backend/app/db.py`, idempotenti; le colonne nuove le aggiunge da sola `_migrate_add_model_columns`.
- Errori HTTP: sempre `api_error(status, code, message, **params)` da `app/core/http_errors.py`; ogni `code` nuovo va tradotto in `frontend/lib/i18n/en.ts` **e** `it.ts` sotto `errors`.
- I set `manual` non passano mai da `assign_roles`, `_reassign_roles`, `recompute_transitions` (spec, sezione "Regole").
- Frontend: leggere `frontend/CLAUDE.md` (Next 16 ha API diverse dalla memoria del modello). Pagine con `?id=` usano `Suspense` + `useSearchParams` come `app/sets/detail/page.tsx`. Spazi fra elementi inline: `{" "}` esplicito.
- Testi: nessuna stringa italiana hardcoded nel frontend; chiavi in `en.ts` prima, poi `it.ts` (il tipo `Dictionary` deriva da `en`).
- Commit: messaggi in italiano, stile `feat(sets): …`, nessun `Co-Authored-By`. Prima di ogni commit `git status --porcelain` e stage solo dei file del task.
- Nessuna chiamata AI, nessun nuovo pacchetto.

---

## File structure

| File | Responsabilità |
|---|---|
| `backend/app/models.py` | Colonne nuove su `Setlist`/`SetlistTrack`, tabella `SetlistBlock` |
| `backend/app/db.py` | `_migrate_setlist_tracks_nullable_track` (rebuild una tantum); pulizia set vuoti limitata a `kind='generated'` |
| `backend/app/repositories.py` | `orphan_lead_ids` ignora le righe varco; `delete_playlist` azzera `source_playlist_id`; `get_setlist` carica i blocchi |
| `backend/app/services/manual_set.py` (nuovo) | Tutte le mutazioni del set manuale: crea, inserisci righe/varco, sposta, togli, appunto; controllo `revision` |
| `backend/app/services/manual_material.py` (nuovo) | Il materiale: playlist aggiornata ∪ tracce nel set ∪ ricerca libreria, con flag |
| `backend/app/schemas.py` | `ManualSetCreate`, `ManualSetOut`, `ManualBlockOut`, `ManualRowOut`, `RowsInsertRequest`, `RowMoveRequest`, `RowPatchRequest`, `MaterialOut`, `MaterialItemOut`; `kind` su `SetlistSummaryOut` |
| `backend/app/serializers.py` | `manual_set_out`; `setlist_summary_out` robusto ai varchi |
| `backend/app/routers/sets.py` | Endpoint `/manual`, `/{id}/manual`, `/{id}/material`, `/{id}/rows…`; mappa `ManualSetError` → HTTP |
| `backend/tests/test_set_manual_schema.py` | Migrazione e modello |
| `backend/tests/test_set_manual_lifecycle.py` | Orfani, summary, delete_playlist, pulizia legacy |
| `backend/tests/test_set_manual_service.py` | Servizio |
| `backend/tests/test_set_manual_api.py` | Endpoint e materiale |
| `frontend/lib/api/types.ts`, `frontend/lib/api/manual-sets.ts` (nuovo), `frontend/lib/api.ts` | Tipi e client |
| `frontend/lib/i18n/en.ts`, `it.ts` | Chiavi `sets.manual.*` ed `errors.*` |
| `frontend/components/set-builder/material-panel.tsx`, `path-panel.tsx`, `detail-panel.tsx` (nuovi) | I tre pannelli |
| `frontend/app/sets/manual/page.tsx` (nuovo) | La pagina che li compone e tiene lo stato |
| `frontend/app/set-builder/page.tsx`, `frontend/app/playlists/detail/page.tsx`, `frontend/app/sets/page.tsx` | Ingressi e instradamento per `kind` |
| `frontend/tests/set-builder-workbench.test.tsx`, `frontend/tests/sets-list-kind.test.tsx` (nuovi), `frontend/e2e/smoke.spec.ts` | Test |
| `docs/API.md`, `docs/ARCHITECTURE.md`, `PROGRESS.md` | Documentazione della tappa consegnata |

---

### Task 1: Modello e migrazione

**Files:**
- Modify: `backend/app/models.py` (classi `Setlist` riga ~194 e `SetlistTrack` riga ~221)
- Modify: `backend/app/db.py` (`ensure_schema` riga ~35; `_migrate_drop_legacy` riga ~228)
- Test: `backend/tests/test_set_manual_schema.py`

**Interfaces:**
- Produces: `Setlist.kind: str` (`"generated"|"manual"`), `Setlist.source_playlist_id: int|None`, `Setlist.notes: str|None`, `Setlist.revision: int`, `Setlist.blocks: list[SetlistBlock]`; `SetlistBlock(id, setlist_id, name, placement, position, rows)`; `SetlistTrack.track_id: int|None`, `SetlistTrack.slot_kind: str` (`"track"|"gap"`), `SetlistTrack.block_id: int|None`, `SetlistTrack.note: str|None`, `SetlistTrack.block`, `SetlistTrack.track: Track|None`.

- [ ] **Step 1: Scrivi i test che falliscono**

```python
# backend/tests/test_set_manual_schema.py
"""Banco di preparazione, tappa 1: colonne nuove, tabella setlist_blocks e il
rebuild una tantum che rende nullable setlist_tracks.track_id (varco)."""
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import ensure_schema
from app.models import Setlist, SetlistBlock, SetlistTrack, Track


def _engine():
    return create_engine("sqlite://", connect_args={"check_same_thread": False},
                         poolclass=StaticPool)


def _notnull(conn, table: str, col: str) -> bool:
    return {r[1]: bool(r[3]) for r in conn.execute(text(f'PRAGMA table_info("{table}")'))}[col]


def test_db_nuovo_ha_colonne_e_track_id_nullable():
    e = _engine()
    ensure_schema(e)
    with e.connect() as c:
        assert _notnull(c, "setlist_tracks", "track_id") is False
        cols = {r[1] for r in c.execute(text('PRAGMA table_info("setlist_tracks")'))}
        assert {"slot_kind", "block_id", "note"} <= cols
        scols = {r[1] for r in c.execute(text('PRAGMA table_info("setlists")'))}
        assert {"kind", "source_playlist_id", "notes", "revision"} <= scols
        assert c.execute(text(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='setlist_blocks'"
        )).first()


_LEGACY_SETLIST_TRACKS = """
CREATE TABLE setlist_tracks (
  id INTEGER NOT NULL PRIMARY KEY,
  setlist_id INTEGER NOT NULL REFERENCES setlists (id),
  track_id INTEGER NOT NULL REFERENCES tracks (id),
  position INTEGER NOT NULL,
  role VARCHAR, transition_score FLOAT, transition_reason TEXT, transition_note TEXT,
  ai_reason TEXT, risk_level VARCHAR, mood_tags JSON, created_at DATETIME
)"""


def test_db_esistente_ricostruito_conservando_le_righe():
    e = _engine()
    ensure_schema(e)
    S = sessionmaker(bind=e, expire_on_commit=False)
    with S() as s:
        s.add(Track(source_type="spotify", title="A"))
        s.add(Setlist(name="S"))
        s.commit()
    with e.begin() as c:
        c.execute(text("DROP TABLE setlist_tracks"))
        c.execute(text(_LEGACY_SETLIST_TRACKS))
        c.execute(text("INSERT INTO setlist_tracks (setlist_id, track_id, position, created_at) "
                       "VALUES (1, 1, 1, '2026-01-01 00:00:00')"))
    with e.connect() as c:
        assert _notnull(c, "setlist_tracks", "track_id") is True  # premessa del test

    ensure_schema(e)

    with e.connect() as c:
        assert _notnull(c, "setlist_tracks", "track_id") is False
        row = c.execute(text(
            "SELECT setlist_id, track_id, position, slot_kind FROM setlist_tracks"
        )).one()
        assert tuple(row) == (1, 1, 1, "track")
        assert not c.execute(text(
            "SELECT 1 FROM sqlite_master WHERE name='setlist_tracks__rebuild'"
        )).first()
        idx = {r[1] for r in c.execute(text('PRAGMA index_list("setlist_tracks")'))}
        assert "ix_setlist_tracks_track_id" in idx
    ensure_schema(e)  # idempotente: seconda run senza errori
    with e.connect() as c:
        assert c.execute(text("SELECT count(*) FROM setlist_tracks")).scalar() == 1


def test_riga_varco_senza_traccia_e_blocco(db):
    s = Setlist(name="Manuale", kind="manual")
    db.add(s)
    db.flush()
    b = SetlistBlock(setlist_id=s.id, position=1)
    db.add(b)
    db.flush()
    db.add(SetlistTrack(setlist_id=s.id, block_id=b.id, position=1, slot_kind="gap"))
    db.commit()
    db.refresh(s)
    assert s.tracks[0].track is None and s.tracks[0].slot_kind == "gap"
    assert s.blocks[0].rows[0].id == s.tracks[0].id
    assert s.revision == 0 and s.kind == "manual"


def test_cancellare_il_set_cancella_blocchi_e_righe(db):
    s = Setlist(name="Manuale", kind="manual")
    db.add(s)
    db.flush()
    b = SetlistBlock(setlist_id=s.id, position=1)
    db.add(b)
    db.flush()
    db.add(SetlistTrack(setlist_id=s.id, block_id=b.id, position=1, slot_kind="gap"))
    db.commit()
    db.delete(s)
    db.commit()
    assert db.query(SetlistBlock).count() == 0
    assert db.query(SetlistTrack).count() == 0
```

- [ ] **Step 2: Esegui i test e verifica che falliscano**

Run: `cd backend && .venv/bin/python -m pytest tests/test_set_manual_schema.py -q`
Expected: FAIL (`ImportError: cannot import name 'SetlistBlock'`).

- [ ] **Step 3: Modifica i modelli**

In `backend/app/models.py`, dentro `class Setlist` dopo `updated_at`:

```python
    # Banco di preparazione (spec 2026-09-15): generated = nato dal generatore,
    # manual = preparato a mano. I set manual non passano mai da assign_roles.
    kind: Mapped[str] = mapped_column(String, default="generated", server_default="generated", index=True)
    # Playlist di origine, letta AGGIORNATA come materiale (nessuna copia della
    # membership). Azzerata da repositories.delete_playlist: sui DB migrati la
    # colonna nasce senza REFERENCES (vedi db._migrate_add_model_columns).
    source_playlist_id: Mapped[int | None] = mapped_column(ForeignKey("playlists.id"), index=True)
    notes: Mapped[str | None] = mapped_column(Text)
    # Cambia a ogni modifica strutturale: il client la rimanda come
    # expected_revision e il server risponde 409 se non coincide.
    revision: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    blocks: Mapped[list["SetlistBlock"]] = relationship(
        back_populates="setlist", cascade="all, delete-orphan", order_by="SetlistBlock.position"
    )
```

Subito dopo `class Setlist` aggiungi:

```python
class SetlistBlock(Base):
    """Sequenza di un set manuale. placement: main (nel percorso) | bench (banco).
    Le righe (SetlistTrack) puntano al blocco; block_id NULL = riserva."""

    __tablename__ = "setlist_blocks"

    id: Mapped[int] = mapped_column(primary_key=True)
    setlist_id: Mapped[int] = mapped_column(ForeignKey("setlists.id"), index=True)
    name: Mapped[str | None] = mapped_column(String)
    placement: Mapped[str] = mapped_column(String, default="main", server_default="main")
    position: Mapped[int] = mapped_column(Integer, default=1)

    setlist: Mapped[Setlist] = relationship(back_populates="blocks")
    rows: Mapped[list["SetlistTrack"]] = relationship(
        back_populates="block", order_by="SetlistTrack.position"
    )
```

In `class SetlistTrack` sostituisci la riga `track_id` e aggiungi le colonne/relazioni:

```python
    # Nullable dal banco di preparazione: un varco (slot_kind='gap') e' una riga
    # senza traccia. Sui DB esistenti la NOT NULL cade con un rebuild una tantum
    # (db._migrate_setlist_tracks_nullable_track).
    track_id: Mapped[int | None] = mapped_column(ForeignKey("tracks.id"), index=True)
    # Posizione dentro il blocco (o dentro la riserva). Sui set generated,
    # senza blocchi, e' l'ordine del set come sempre.
    position: Mapped[int] = mapped_column(Integer)
    slot_kind: Mapped[str] = mapped_column(String, default="track", server_default="track")
    block_id: Mapped[int | None] = mapped_column(ForeignKey("setlist_blocks.id"), index=True)
    note: Mapped[str | None] = mapped_column(Text)
```

e in fondo alla classe:

```python
    block: Mapped["SetlistBlock | None"] = relationship(back_populates="rows")
    track: Mapped[Track | None] = relationship()
```

(La riga `position` esisteva già: aggiorna solo il commento. Il commento su `role` resta.)

- [ ] **Step 4: Aggiungi la migrazione in `db.py`**

Sotto `_column_add_ddl` aggiungi:

```python
def _migrate_setlist_tracks_nullable_track(conn) -> None:
    """Banco di preparazione: `setlist_tracks.track_id` deve accettare NULL (varco).

    SQLite non cambia la nullabilita' con ALTER: rebuild una tantum
    crea-copia-drop-rename. Oggi nessuna tabella referenzia `setlist_tracks`
    (le alternative arrivano in una tappa successiva e verranno create da
    create_all DOPO questa funzione), quindi il RENAME non riscrive REFERENCES
    altrui. Va eseguita dopo `_migrate_add_model_columns` (che ha gia' aggiunto
    le colonne nuove alla tabella vecchia) e PRIMA della ricreazione degli
    indici in `ensure_schema`: gli indici cadono col DROP e il loop del modello
    li rifa' sulla tabella ricostruita. Idempotente: no-op se gia' nullable.
    """
    from sqlalchemy.schema import CreateTable

    from app.models import SetlistTrack  # import differito: models importa db.Base

    info = conn.execute(text('PRAGMA table_info("setlist_tracks")')).fetchall()
    if not info:
        return
    notnull = {r[1]: bool(r[3]) for r in info}
    if not notnull.get("track_id", False):
        return
    tmp = "setlist_tracks__rebuild"
    conn.execute(text(f'DROP TABLE IF EXISTS "{tmp}"'))  # run precedente interrotta
    ddl = str(CreateTable(SetlistTrack.__table__).compile(dialect=conn.dialect))
    ddl = ddl.replace("CREATE TABLE setlist_tracks", f'CREATE TABLE "{tmp}"', 1)
    conn.execute(text(ddl))
    live = {r[1] for r in info}
    cols = ", ".join(f'"{c}"' for c in SetlistTrack.__table__.columns.keys() if c in live)
    conn.execute(text(f'INSERT INTO "{tmp}" ({cols}) SELECT {cols} FROM setlist_tracks'))
    conn.execute(text("DROP TABLE setlist_tracks"))
    conn.execute(text(f'ALTER TABLE "{tmp}" RENAME TO setlist_tracks'))
```

In `ensure_schema`, subito dopo `_migrate_add_model_columns(conn, eng.dialect)` e prima del `for table in Base.metadata.tables.values():`, aggiungi:

```python
        _migrate_setlist_tracks_nullable_track(conn)
```

In `_migrate_drop_legacy`, sostituisci l'ultima `DELETE FROM setlists …` con:

```python
    # Un set manuale puo' essere vuoto per scelta (spec banco di preparazione):
    # la potatura dei set senza righe riguarda solo quelli del generatore.
    conn.execute(text(
        "DELETE FROM setlists WHERE kind = 'generated' "
        "AND id NOT IN (SELECT setlist_id FROM setlist_tracks)"
    ))
```

- [ ] **Step 5: Esegui i test e verifica che passino**

Run: `cd backend && .venv/bin/python -m pytest tests/test_set_manual_schema.py -q`
Expected: 4 passed.

- [ ] **Step 6: Suite completa backend**

Run: `cd backend && .venv/bin/python -m pytest tests -q`
Expected: tutto verde. Se `test_set_editing*.py` o i test del generatore rompono su `st.track` None, fermati: significa che qualche codice itera righe senza traccia, non deve succedere sui set generated.

- [ ] **Step 7: Commit**

```bash
git add backend/app/models.py backend/app/db.py backend/tests/test_set_manual_schema.py
git commit -m "feat(sets): colonne del set manuale, SetlistBlock e rebuild di setlist_tracks (track_id nullable)"
```

---

### Task 2: Ciclo di vita delle tracce e dei set

**Files:**
- Modify: `backend/app/repositories.py` (`_SETLIST_TRACKS` riga ~457, `orphan_lead_ids` riga ~614, `delete_playlist` riga ~863)
- Modify: `backend/app/serializers.py` (`setlist_summary_out` riga ~141)
- Modify: `backend/app/schemas.py` (`SetlistSummaryOut` riga ~193)
- Test: `backend/tests/test_set_manual_lifecycle.py`

**Interfaces:**
- Produces: `SetlistSummaryOut.kind: str`; `get_setlist` e `list_setlists` caricano anche `Setlist.blocks` e `SetlistTrack.block`.

- [ ] **Step 1: Scrivi i test che falliscono**

```python
# backend/tests/test_set_manual_lifecycle.py
"""Il set manuale nel ciclo di vita esistente: lead orfani con righe varco,
riepilogo con varchi, cancellazione della playlist di origine, pulizia legacy."""
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import _migrate_drop_legacy, ensure_schema
from app.models import Playlist, Setlist, SetlistBlock, SetlistTrack, Track
from app.repositories import delete_playlist, get_setlist, orphan_lead_ids
from app.serializers import setlist_summary_out


def _manual_with_gap(db, track=None):
    s = Setlist(name="M", kind="manual")
    db.add(s)
    db.flush()
    b = SetlistBlock(setlist_id=s.id, position=1)
    db.add(b)
    db.flush()
    db.add(SetlistTrack(setlist_id=s.id, block_id=b.id, position=1, slot_kind="gap"))
    if track is not None:
        db.add(SetlistTrack(setlist_id=s.id, block_id=b.id, position=2, track_id=track.id))
    db.commit()
    return s


def test_lead_orfano_trovato_anche_se_esiste_una_riga_varco(db):
    lead = Track(source_type="spotify", title="Lead", has_local_file=False)
    db.add(lead)
    db.commit()
    _manual_with_gap(db)
    # NOT IN con un NULL nel sottoinsieme non trova mai nulla: la guardia sul
    # NULL deve esserci, altrimenti nessun lead sarebbe piu' orfano.
    assert orphan_lead_ids(db, [lead.id]) == [lead.id]


def test_lead_nel_set_manuale_non_e_orfano(db):
    lead = Track(source_type="spotify", title="Lead", has_local_file=False)
    db.add(lead)
    db.commit()
    _manual_with_gap(db, track=lead)
    assert orphan_lead_ids(db, [lead.id]) == []


def test_riepilogo_conta_solo_le_tracce_e_porta_il_kind(db):
    tr = Track(source_type="spotify", title="A", duration_seconds=300, has_local_file=True)
    db.add(tr)
    db.commit()
    s = _manual_with_gap(db, track=tr)
    out = setlist_summary_out(get_setlist(db, s.id))
    assert out.kind == "manual"
    assert out.track_count == 1
    assert out.total_duration_seconds == 300


def test_cancellare_la_playlist_azzera_l_origine_del_set(db):
    pl = Playlist(platform="spotify", name="Deep")
    db.add(pl)
    db.flush()
    s = Setlist(name="M", kind="manual", source_playlist_id=pl.id)
    db.add(s)
    db.commit()
    delete_playlist(db, pl.id)
    assert get_setlist(db, s.id).source_playlist_id is None


def test_pulizia_legacy_non_cancella_i_set_manuali_vuoti():
    e = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    ensure_schema(e)
    S = sessionmaker(bind=e, expire_on_commit=False)
    with S() as s:
        s.add(Setlist(name="vuoto manuale", kind="manual"))
        s.add(Setlist(name="vuoto generato", kind="generated"))
        s.commit()
    with e.begin() as c:
        # Una colonna morta su tracks fa scattare il ramo di pulizia legacy.
        c.execute(text("ALTER TABLE tracks ADD COLUMN tonality VARCHAR"))
        _migrate_drop_legacy(c)
    with S() as s:
        names = set(s.scalars(select(Setlist.name)).all())
    assert names == {"vuoto manuale"}
```

- [ ] **Step 2: Esegui i test e verifica che falliscano**

Run: `cd backend && .venv/bin/python -m pytest tests/test_set_manual_lifecycle.py -q`
Expected: FAIL su `orphan_lead_ids` (ritorna `[]`), su `out.kind` (attributo assente), su `source_playlist_id` (resta valorizzato). L'ultimo test passa già se Task 1 è fatto: va bene, resta come guardia.

- [ ] **Step 3: Implementa**

In `backend/app/repositories.py`:

```python
_SETLIST_TRACKS = (
    selectinload(Setlist.tracks)
    .selectinload(SetlistTrack.track)
    .selectinload(Track.playlists),
    selectinload(Setlist.blocks),
)
```

e aggiorna `get_setlist`/`list_setlists` da `.options(_SETLIST_TRACKS)` a `.options(*_SETLIST_TRACKS)`. Cerca altri usi con `grep -n "_SETLIST_TRACKS" backend/app/repositories.py` e adeguali allo stesso modo.

In `orphan_lead_ids`:

```python
        # Le righe varco del set manuale hanno track_id NULL: senza questa
        # guardia il NOT IN non troverebbe mai nulla (NULL nel sottoinsieme).
        Track.id.not_in(select(SetlistTrack.track_id).where(SetlistTrack.track_id.is_not(None))),
```

In `delete_playlist`, dopo la riga che aggiorna `DjSet`:

```python
    # Il set manuale nato da questa playlist resta, senza origine (spec: il
    # materiale si riduce a cio' che e' nel set + la ricerca in libreria).
    db.execute(update(Setlist).where(Setlist.source_playlist_id == playlist_id)
               .values(source_playlist_id=None))
```

In `backend/app/schemas.py`, `SetlistSummaryOut` aggiunge:

```python
    kind: str = "generated"  # generated | manual: la lista instrada alla pagina giusta
```

In `backend/app/serializers.py`, `setlist_summary_out`:

```python
def setlist_summary_out(setlist: Setlist) -> SetlistSummaryOut:
    with_track = [st for st in setlist.tracks if st.track is not None]  # i varchi non contano
    return SetlistSummaryOut(
        id=setlist.id,
        name=setlist.name,
        kind=setlist.kind or "generated",
        strategy=setlist.strategy,
        target_duration_minutes=setlist.target_duration_minutes,
        track_count=len(with_track),
        total_duration_seconds=sum(st.track.duration_seconds or 0 for st in with_track),
        generated_by=setlist.generated_by or "algorithmic",
        created_at=setlist.created_at,
    )
```

- [ ] **Step 4: Esegui i test e verifica che passino**

Run: `cd backend && .venv/bin/python -m pytest tests/test_set_manual_lifecycle.py tests/test_set_manual_schema.py -q`
Expected: tutti verdi.

- [ ] **Step 5: Suite completa e commit**

Run: `cd backend && .venv/bin/python -m pytest tests -q` → verde.

```bash
git add backend/app/repositories.py backend/app/serializers.py backend/app/schemas.py backend/tests/test_set_manual_lifecycle.py
git commit -m "feat(sets): il set manuale nel ciclo di vita: orfani, riepilogo, playlist di origine"
```

---

### Task 3: Il servizio `manual_set.py`

**Files:**
- Create: `backend/app/services/manual_set.py`
- Test: `backend/tests/test_set_manual_service.py`

**Interfaces:**
- Consumes: modelli del Task 1; `get_setlist`, `get_playlist`, `get_track` da `app.repositories`.
- Produces:

```python
class ManualSetError(Exception): ...            # messaggio in inglese, mappato dal router
class ManualSetNotFound(ManualSetError): ...     # 404
class ManualSetNotManual(ManualSetError): ...    # 409: il set esiste ma non e' manual
class RowNotFound(ManualSetError): ...           # 404
class RevisionConflict(ManualSetError):          # 409, porta la revisione corrente
    def __init__(self, current: int): ...
    current: int

def create_manual_set(db, *, name: str | None, playlist_id: int | None) -> Setlist
def load_manual_set(db, setlist_id: int) -> Setlist          # solleva NotFound / NotManual
def main_block(db, setlist: Setlist) -> SetlistBlock          # crea il blocco main se manca (non committa)
def path_rows(setlist: Setlist) -> list[SetlistTrack]         # righe del percorso in ordine
def insert_rows(db, setlist_id: int, *, expected_revision: int,
                track_ids: list[int], gap: bool, after_row_id: int | None) -> Setlist
def move_row(db, setlist_id: int, row_id: int, *, expected_revision: int, position: int) -> Setlist
def remove_row(db, setlist_id: int, row_id: int, *, expected_revision: int) -> Setlist
def update_row_note(db, setlist_id: int, row_id: int, *, expected_revision: int, note: str | None) -> Setlist
```

Ogni funzione che muta: controlla `expected_revision`, muta, `setlist.revision += 1`, `db.commit()`, ritorna il set ricaricato con `get_setlist`.

- [ ] **Step 1: Scrivi i test che falliscono**

```python
# backend/tests/test_set_manual_service.py
"""Servizio del set manuale (tappa 1): creazione, righe, varco, spostamento,
rimozione, appunto, revisione. DB in memoria, nessuna rete."""
import pytest

from app.models import Playlist, Track
from app.repositories import add_track_to_playlist, get_setlist
from app.services.manual_set import (
    ManualSetNotFound,
    ManualSetNotManual,
    RevisionConflict,
    RowNotFound,
    ManualSetError,
    create_manual_set,
    insert_rows,
    move_row,
    path_rows,
    remove_row,
    update_row_note,
)


def _tracks(db, n=4):
    out = []
    for i in range(n):
        t = Track(source_type="spotify", title=f"T{i}", artist="A", duration_seconds=300,
                  bpm=124.0, has_local_file=True)
        db.add(t)
        out.append(t)
    db.commit()
    return out


def _playlist(db, tracks):
    pl = Playlist(platform="spotify", name="Deep")
    db.add(pl)
    db.flush()
    for t in tracks:
        add_track_to_playlist(db, t, pl, added_by="test")
    db.commit()
    return pl


def _ids(setlist):
    return [r.track_id for r in path_rows(setlist)]


def test_crea_vuoto_da_playlist(db):
    pl = _playlist(db, _tracks(db, 2))
    s = create_manual_set(db, name=None, playlist_id=pl.id)
    assert s.kind == "manual" and s.source_playlist_id == pl.id
    assert s.name == "Deep"  # default: il nome della playlist
    assert s.revision == 0 and s.tracks == [] and s.blocks == []


def test_crea_senza_playlist_con_nome(db):
    s = create_manual_set(db, name="  Sabato  ", playlist_id=None)
    assert s.name == "Sabato" and s.source_playlist_id is None


def test_crea_con_playlist_inesistente(db):
    with pytest.raises(ManualSetError):
        create_manual_set(db, name=None, playlist_id=999)


def test_inserisci_crea_il_blocco_main_e_incrementa_la_revisione(db):
    t = _tracks(db, 3)
    s = create_manual_set(db, name="M", playlist_id=None)
    s = insert_rows(db, s.id, expected_revision=0, track_ids=[t[0].id, t[1].id], gap=False, after_row_id=None)
    assert s.revision == 1
    assert [b.placement for b in s.blocks] == ["main"]
    assert _ids(s) == [t[0].id, t[1].id]
    assert [r.position for r in path_rows(s)] == [1, 2]


def test_inserisci_dopo_una_riga(db):
    t = _tracks(db, 3)
    s = create_manual_set(db, name="M", playlist_id=None)
    s = insert_rows(db, s.id, expected_revision=0, track_ids=[t[0].id, t[1].id], gap=False, after_row_id=None)
    first = path_rows(s)[0]
    s = insert_rows(db, s.id, expected_revision=1, track_ids=[t[2].id], gap=False, after_row_id=first.id)
    assert _ids(s) == [t[0].id, t[2].id, t[1].id]
    assert [r.position for r in path_rows(s)] == [1, 2, 3]


def test_inserisci_un_varco(db):
    t = _tracks(db, 2)
    s = create_manual_set(db, name="M", playlist_id=None)
    s = insert_rows(db, s.id, expected_revision=0, track_ids=[t[0].id, t[1].id], gap=False, after_row_id=None)
    first = path_rows(s)[0]
    s = insert_rows(db, s.id, expected_revision=1, track_ids=[], gap=True, after_row_id=first.id)
    rows = path_rows(s)
    assert [r.slot_kind for r in rows] == ["track", "gap", "track"]
    assert rows[1].track_id is None and rows[1].track is None


def test_inserisci_rifiuta_la_stessa_traccia_due_volte_nel_percorso(db):
    t = _tracks(db, 1)
    s = create_manual_set(db, name="M", playlist_id=None)
    s = insert_rows(db, s.id, expected_revision=0, track_ids=[t[0].id], gap=False, after_row_id=None)
    with pytest.raises(ManualSetError):
        insert_rows(db, s.id, expected_revision=1, track_ids=[t[0].id], gap=False, after_row_id=None)


def test_inserisci_traccia_senza_bpm_ne_tonalita(db):
    """Spec: nel percorso entra anche chi non ha dati tecnici (file locale basta)."""
    t = Track(source_type="spotify", title="Grezza", has_local_file=True)
    db.add(t)
    db.commit()
    s = create_manual_set(db, name="M", playlist_id=None)
    s = insert_rows(db, s.id, expected_revision=0, track_ids=[t.id], gap=False, after_row_id=None)
    assert _ids(s) == [t.id]


def test_inserisci_traccia_inesistente(db):
    s = create_manual_set(db, name="M", playlist_id=None)
    with pytest.raises(ManualSetError):
        insert_rows(db, s.id, expected_revision=0, track_ids=[999], gap=False, after_row_id=None)


def test_sposta_a_posizione(db):
    t = _tracks(db, 3)
    s = create_manual_set(db, name="M", playlist_id=None)
    s = insert_rows(db, s.id, expected_revision=0, track_ids=[x.id for x in t], gap=False, after_row_id=None)
    last = path_rows(s)[2]
    s = move_row(db, s.id, last.id, expected_revision=1, position=1)
    assert _ids(s) == [t[2].id, t[0].id, t[1].id]
    assert [r.position for r in path_rows(s)] == [1, 2, 3]
    assert s.revision == 2


def test_sposta_posizione_fuori_range(db):
    t = _tracks(db, 2)
    s = create_manual_set(db, name="M", playlist_id=None)
    s = insert_rows(db, s.id, expected_revision=0, track_ids=[x.id for x in t], gap=False, after_row_id=None)
    with pytest.raises(ManualSetError):
        move_row(db, s.id, path_rows(s)[0].id, expected_revision=1, position=5)


def test_togli_rinumera(db):
    t = _tracks(db, 3)
    s = create_manual_set(db, name="M", playlist_id=None)
    s = insert_rows(db, s.id, expected_revision=0, track_ids=[x.id for x in t], gap=False, after_row_id=None)
    s = remove_row(db, s.id, path_rows(s)[1].id, expected_revision=1)
    assert _ids(s) == [t[0].id, t[2].id]
    assert [r.position for r in path_rows(s)] == [1, 2]


def test_appunto_su_riga(db):
    t = _tracks(db, 1)
    s = create_manual_set(db, name="M", playlist_id=None)
    s = insert_rows(db, s.id, expected_revision=0, track_ids=[t[0].id], gap=False, after_row_id=None)
    row = path_rows(s)[0]
    s = update_row_note(db, s.id, row.id, expected_revision=1, note="  entra sul break  ")
    assert path_rows(s)[0].note == "entra sul break"
    s = update_row_note(db, s.id, row.id, expected_revision=2, note="")
    assert path_rows(s)[0].note is None


def test_revisione_sbagliata_solleva_conflitto_e_non_muta(db):
    t = _tracks(db, 2)
    s = create_manual_set(db, name="M", playlist_id=None)
    s = insert_rows(db, s.id, expected_revision=0, track_ids=[t[0].id], gap=False, after_row_id=None)
    with pytest.raises(RevisionConflict) as exc:
        insert_rows(db, s.id, expected_revision=0, track_ids=[t[1].id], gap=False, after_row_id=None)
    assert exc.value.current == 1
    assert _ids(get_setlist(db, s.id)) == [t[0].id]


def test_riga_inesistente(db):
    s = create_manual_set(db, name="M", playlist_id=None)
    with pytest.raises(RowNotFound):
        remove_row(db, s.id, 999, expected_revision=0)


def test_set_inesistente_e_set_non_manuale(db, seed_tracks):
    from app.schemas import SetGenerationRequest
    from app.services.set_generator import generate_set
    seed_tracks(n=40)
    generated = generate_set(db, SetGenerationRequest(target_duration_minutes=30, start_bpm=128))
    with pytest.raises(ManualSetNotFound):
        remove_row(db, 999, 1, expected_revision=0)
    with pytest.raises(ManualSetNotManual):
        insert_rows(db, generated.id, expected_revision=0, track_ids=[], gap=True, after_row_id=None)
```

- [ ] **Step 2: Esegui i test e verifica che falliscano**

Run: `cd backend && .venv/bin/python -m pytest tests/test_set_manual_service.py -q`
Expected: FAIL (`ModuleNotFoundError: app.services.manual_set`).

- [ ] **Step 3: Scrivi il servizio**

```python
# backend/app/services/manual_set.py
"""Set manuale (banco di preparazione, tappa 1): le mutazioni del percorso.

Deterministico, senza AI. Ogni funzione che muta controlla `expected_revision`,
applica la modifica, incrementa `Setlist.revision` e committa nella stessa
transazione. Le righe si identificano per id, mai per posizione. I set manual
non passano mai da assign_roles / recompute_transitions (spec 2026-09-15).
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import Setlist, SetlistBlock, SetlistTrack
from app.repositories import get_playlist, get_setlist, get_track


class ManualSetError(Exception):
    """Errore di dominio (422 dal router, salvo le sottoclassi)."""


class ManualSetNotFound(ManualSetError):
    pass


class ManualSetNotManual(ManualSetError):
    pass


class RowNotFound(ManualSetError):
    pass


class RevisionConflict(ManualSetError):
    def __init__(self, current: int):
        super().__init__(f"Revision mismatch: current is {current}")
        self.current = current


def create_manual_set(db: Session, *, name: str | None, playlist_id: int | None) -> Setlist:
    playlist = None
    if playlist_id is not None:
        playlist = get_playlist(db, playlist_id)
        if playlist is None:
            raise ManualSetError("Playlist not found")
    clean = (name or "").strip() or (playlist.name if playlist is not None else "Set")
    setlist = Setlist(name=clean, kind="manual", source_playlist_id=playlist_id, generated_by="manual")
    db.add(setlist)
    db.commit()
    return get_setlist(db, setlist.id)


def load_manual_set(db: Session, setlist_id: int) -> Setlist:
    setlist = get_setlist(db, setlist_id)
    if setlist is None:
        raise ManualSetNotFound("Set not found")
    if setlist.kind != "manual":
        raise ManualSetNotManual("Set is not a manual set")
    return setlist


def _check_revision(setlist: Setlist, expected: int) -> None:
    if setlist.revision != expected:
        raise RevisionConflict(setlist.revision)


def main_block(db: Session, setlist: Setlist) -> SetlistBlock:
    """Il blocco `main` del set (tappa 1: uno solo), creato al primo inserimento."""
    for block in setlist.blocks:
        if block.placement == "main":
            return block
    block = SetlistBlock(setlist_id=setlist.id, placement="main", position=1)
    db.add(block)
    db.flush()
    setlist.blocks.append(block)
    return block


def path_rows(setlist: Setlist) -> list[SetlistTrack]:
    """Righe del percorso in ordine: blocchi main per posizione, righe per posizione."""
    rows: list[SetlistTrack] = []
    for block in sorted(setlist.blocks, key=lambda b: b.position):
        if block.placement != "main":
            continue
        rows.extend(sorted((r for r in setlist.tracks if r.block_id == block.id),
                           key=lambda r: r.position))
    return rows


def _renumber(rows: list[SetlistTrack]) -> None:
    for i, row in enumerate(rows, start=1):
        row.position = i


def _row_of(setlist: Setlist, row_id: int) -> SetlistTrack:
    for row in setlist.tracks:
        if row.id == row_id:
            return row
    raise RowNotFound("Row not found")


def _commit_bumped(db: Session, setlist: Setlist) -> Setlist:
    setlist.revision += 1
    db.commit()
    return get_setlist(db, setlist.id)


def insert_rows(db: Session, setlist_id: int, *, expected_revision: int,
                track_ids: list[int], gap: bool, after_row_id: int | None) -> Setlist:
    """Inserisce tracce (nell'ordine dato) oppure un varco, dopo `after_row_id`
    (None = in coda). Una traccia compare al piu' una volta nel percorso."""
    if gap == bool(track_ids):
        raise ManualSetError("Give either track_ids or gap")
    setlist = load_manual_set(db, setlist_id)
    _check_revision(setlist, expected_revision)
    block = main_block(db, setlist)
    rows = [r for r in path_rows(setlist) if r.block_id == block.id]
    at = len(rows)
    if after_row_id is not None:
        anchor = _row_of(setlist, after_row_id)
        at = rows.index(anchor) + 1
    present = {r.track_id for r in rows if r.track_id is not None}
    new_rows: list[SetlistTrack] = []
    if gap:
        new_rows.append(SetlistTrack(setlist_id=setlist.id, block_id=block.id, position=0, slot_kind="gap"))
    else:
        for tid in track_ids:
            if get_track(db, tid) is None:
                raise ManualSetError(f"Track {tid} not found")
            if tid in present:
                raise ManualSetError(f"Track {tid} is already in the path")
            present.add(tid)
            new_rows.append(SetlistTrack(setlist_id=setlist.id, block_id=block.id, position=0,
                                         slot_kind="track", track_id=tid))
    rows[at:at] = new_rows
    for row in new_rows:
        db.add(row)
        setlist.tracks.append(row)
    _renumber(rows)
    return _commit_bumped(db, setlist)


def move_row(db: Session, setlist_id: int, row_id: int, *, expected_revision: int, position: int) -> Setlist:
    """Sposta la riga alla posizione 1-based dentro il blocco main."""
    setlist = load_manual_set(db, setlist_id)
    _check_revision(setlist, expected_revision)
    row = _row_of(setlist, row_id)
    rows = [r for r in path_rows(setlist) if r.block_id == row.block_id]
    if not 1 <= position <= len(rows):
        raise ManualSetError(f"Position {position} out of range 1..{len(rows)}")
    rows.remove(row)
    rows.insert(position - 1, row)
    _renumber(rows)
    return _commit_bumped(db, setlist)


def remove_row(db: Session, setlist_id: int, row_id: int, *, expected_revision: int) -> Setlist:
    setlist = load_manual_set(db, setlist_id)
    _check_revision(setlist, expected_revision)
    row = _row_of(setlist, row_id)
    rows = [r for r in path_rows(setlist) if r.block_id == row.block_id and r.id != row.id]
    setlist.tracks.remove(row)  # delete-orphan sulla relazione: la riga sparisce
    _renumber(rows)
    return _commit_bumped(db, setlist)


def update_row_note(db: Session, setlist_id: int, row_id: int, *, expected_revision: int,
                    note: str | None) -> Setlist:
    setlist = load_manual_set(db, setlist_id)
    _check_revision(setlist, expected_revision)
    row = _row_of(setlist, row_id)
    row.note = (note or "").strip() or None
    return _commit_bumped(db, setlist)
```

- [ ] **Step 4: Esegui i test e verifica che passino**

Run: `cd backend && .venv/bin/python -m pytest tests/test_set_manual_service.py -q`
Expected: 16 passed. Se `test_set_inesistente_e_set_non_manuale` fallisce perché `generate_set` scrive `generated_by="algorithmic"` e non `kind`: bene, `kind` ha default `generated`, il test deve passare senza toccare il generatore.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/manual_set.py backend/tests/test_set_manual_service.py
git commit -m "feat(sets): servizio del set manuale: righe per id, varco, revisione"
```

---

### Task 4: Schemi, serializer ed endpoint del set manuale

**Files:**
- Modify: `backend/app/schemas.py` (dopo `AddTrackRequest`, riga ~233)
- Modify: `backend/app/serializers.py` (dopo `setlist_summary_out`)
- Modify: `backend/app/routers/sets.py` (import; dopo `get_one`, riga ~133)
- Test: `backend/tests/test_set_manual_api.py`

**Interfaces:**
- Consumes: Task 3 (`create_manual_set`, `load_manual_set`, `insert_rows`, `move_row`, `remove_row`, `update_row_note`, `path_rows`, eccezioni).
- Produces (HTTP):
  - `POST /api/sets/manual` body `{name?, playlist_id?}` → `ManualSetOut` (201)
  - `GET /api/sets/{id}/manual` → `ManualSetOut`
  - `POST /api/sets/{id}/rows` body `{expected_revision, track_ids?: int[], gap?: bool, after_row_id?: int}` → `ManualSetOut`
  - `POST /api/sets/{id}/rows/{row_id}/move` body `{expected_revision, position}` → `ManualSetOut`
  - `PATCH /api/sets/{id}/rows/{row_id}` body `{expected_revision, note}` → `ManualSetOut`
  - `DELETE /api/sets/{id}/rows/{row_id}?expected_revision=N` → `ManualSetOut`
  - `GET /api/sets/{id}` su un set manual → 409 `set_is_manual`
  - Codici errore nuovi: `set_is_manual` (409), `set_not_manual` (409), `set_revision_conflict` (409, `params.current`), `set_row_not_found` (404), `manual_set_error` (422, `params.reason`). `set_not_found` e `playlist_not_found` esistono già.

```python
class ManualRowOut(BaseModel):
    id: int; block_id: int | None; position: int
    slot_kind: Literal["track", "gap"]
    track: TrackOut | None = None
    note: str | None = None

class ManualBlockOut(BaseModel):
    id: int; name: str | None; placement: Literal["main", "bench"]; position: int
    rows: list[ManualRowOut]

class ManualSetOut(BaseModel):
    id: int; name: str; kind: str; revision: int
    source_playlist_id: int | None; source_playlist_name: str | None
    notes: str | None
    blocks: list[ManualBlockOut]
    track_count: int; total_file_seconds: int
    created_at: datetime; updated_at: datetime
```

- [ ] **Step 1: Scrivi i test che falliscono**

```python
# backend/tests/test_set_manual_api.py
"""Endpoint del set manuale (tappa 1). TestClient con DB in memoria."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app
from app.models import Playlist, Track
from app.repositories import add_track_to_playlist


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


def _seed(db, n=3):
    pl = Playlist(platform="spotify", name="Deep")
    db.add(pl)
    db.flush()
    tracks = []
    for i in range(n):
        t = Track(source_type="spotify", title=f"T{i}", artist="A", duration_seconds=300,
                  bpm=124.0, has_local_file=(i != 2))
        db.add(t)
        db.flush()
        add_track_to_playlist(db, t, pl, added_by="test")
        tracks.append(t)
    db.commit()
    return pl, tracks


def _rows(doc):
    return [r for b in doc["blocks"] if b["placement"] == "main" for r in b["rows"]]


def test_crea_da_playlist_e_rileggi(client_db):
    client, db = client_db
    pl, _ = _seed(db)
    r = client.post("/api/sets/manual", json={"playlist_id": pl.id})
    assert r.status_code == 201, r.text
    doc = r.json()
    assert doc["kind"] == "manual" and doc["name"] == "Deep"
    assert doc["source_playlist_name"] == "Deep" and doc["revision"] == 0
    assert doc["blocks"] == [] and doc["track_count"] == 0
    assert client.get(f"/api/sets/{doc['id']}/manual").json() == doc
    assert client.get("/api/sets").json()[0]["kind"] == "manual"


def test_crea_con_playlist_inesistente(client_db):
    client, _ = client_db
    r = client.post("/api/sets/manual", json={"playlist_id": 999})
    assert r.status_code == 404 and r.json()["detail"]["code"] == "playlist_not_found"


def test_dettaglio_classico_rifiuta_il_set_manuale(client_db):
    client, db = client_db
    sid = client.post("/api/sets/manual", json={"name": "M"}).json()["id"]
    r = client.get(f"/api/sets/{sid}")
    assert r.status_code == 409 and r.json()["detail"]["code"] == "set_is_manual"


def test_righe_inserisci_varco_sposta_appunto_togli(client_db):
    client, db = client_db
    _, t = _seed(db)
    sid = client.post("/api/sets/manual", json={"name": "M"}).json()["id"]

    r = client.post(f"/api/sets/{sid}/rows", json={"expected_revision": 0, "track_ids": [t[0].id, t[1].id]})
    assert r.status_code == 200, r.text
    doc = r.json()
    assert doc["revision"] == 1 and doc["track_count"] == 2 and doc["total_file_seconds"] == 600
    rows = _rows(doc)
    assert [x["track"]["id"] for x in rows] == [t[0].id, t[1].id]

    r = client.post(f"/api/sets/{sid}/rows", json={"expected_revision": 1, "gap": True, "after_row_id": rows[0]["id"]})
    rows = _rows(r.json())
    assert [x["slot_kind"] for x in rows] == ["track", "gap", "track"]
    assert rows[1]["track"] is None

    r = client.post(f"/api/sets/{sid}/rows/{rows[2]['id']}/move", json={"expected_revision": 2, "position": 1})
    rows = _rows(r.json())
    assert [x["slot_kind"] for x in rows] == ["track", "track", "gap"]
    assert [x["position"] for x in rows] == [1, 2, 3]

    r = client.patch(f"/api/sets/{sid}/rows/{rows[0]['id']}", json={"expected_revision": 3, "note": "apre bene"})
    assert _rows(r.json())[0]["note"] == "apre bene"

    r = client.delete(f"/api/sets/{sid}/rows/{rows[2]['id']}", params={"expected_revision": 4})
    doc = r.json()
    assert [x["slot_kind"] for x in _rows(doc)] == ["track", "track"] and doc["revision"] == 5


def test_conflitto_di_revisione(client_db):
    client, db = client_db
    _, t = _seed(db)
    sid = client.post("/api/sets/manual", json={"name": "M"}).json()["id"]
    client.post(f"/api/sets/{sid}/rows", json={"expected_revision": 0, "track_ids": [t[0].id]})
    r = client.post(f"/api/sets/{sid}/rows", json={"expected_revision": 0, "track_ids": [t[1].id]})
    assert r.status_code == 409
    d = r.json()["detail"]
    assert d["code"] == "set_revision_conflict" and d["params"]["current"] == 1


def test_errori_di_dominio(client_db):
    client, db = client_db
    _, t = _seed(db)
    sid = client.post("/api/sets/manual", json={"name": "M"}).json()["id"]
    r = client.post(f"/api/sets/{sid}/rows", json={"expected_revision": 0})
    assert r.status_code == 422  # ne' track_ids ne' gap: validazione Pydantic
    r = client.post(f"/api/sets/{sid}/rows", json={"expected_revision": 0, "track_ids": [999]})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "manual_set_error"
    r = client.delete(f"/api/sets/{sid}/rows/999", params={"expected_revision": 0})
    assert r.status_code == 404 and r.json()["detail"]["code"] == "set_row_not_found"
    r = client.get("/api/sets/999/manual")
    assert r.status_code == 404 and r.json()["detail"]["code"] == "set_not_found"


def test_endpoint_manuali_rifiutano_un_set_generato(client_db):
    client, db = client_db
    from app.schemas import SetGenerationRequest
    from app.services.set_generator import generate_set
    for i in range(40):
        db.add(Track(source_type="spotify", title=f"G{i}", artist=f"A{i % 5}", duration_seconds=300,
                     bpm=128.0 + (i % 6), camelot_key="8A", has_local_file=True))
    db.commit()
    generated = generate_set(db, SetGenerationRequest(target_duration_minutes=30, start_bpm=128))
    r = client.get(f"/api/sets/{generated.id}/manual")
    assert r.status_code == 409 and r.json()["detail"]["code"] == "set_not_manual"
```

- [ ] **Step 2: Esegui i test e verifica che falliscano**

Run: `cd backend && .venv/bin/python -m pytest tests/test_set_manual_api.py -q`
Expected: FAIL con 404/405 sugli endpoint mancanti.

- [ ] **Step 3: Schemi**

In `backend/app/schemas.py`, dopo `AddTrackRequest`:

```python
# --- Set manuale (banco di preparazione, tappa 1) ------------------------------


class ManualSetCreate(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    playlist_id: int | None = None


class ManualRowOut(BaseModel):
    id: int
    block_id: int | None = None
    position: int
    slot_kind: Literal["track", "gap"]
    track: TrackOut | None = None  # None sui varchi
    note: str | None = None


class ManualBlockOut(BaseModel):
    id: int
    name: str | None = None
    placement: Literal["main", "bench"]
    position: int
    rows: list[ManualRowOut] = []


class ManualSetOut(BaseModel):
    id: int
    name: str
    kind: str
    revision: int
    source_playlist_id: int | None = None
    source_playlist_name: str | None = None  # None se la playlist e' stata cancellata
    notes: str | None = None
    blocks: list[ManualBlockOut] = []
    track_count: int = 0
    total_file_seconds: int = 0  # somma delle durate dei file, i varchi non contano
    created_at: datetime
    updated_at: datetime


class RowsInsertRequest(BaseModel):
    """Tracce (nell'ordine dato) oppure un varco; esattamente uno dei due."""

    expected_revision: int = Field(ge=0)
    track_ids: list[int] = []
    gap: bool = False
    after_row_id: int | None = None  # None = in coda

    @model_validator(mode="after")
    def _exactly_one(self) -> "RowsInsertRequest":
        if self.gap == bool(self.track_ids):
            raise ValueError("Give either track_ids or gap")
        return self


class RowMoveRequest(BaseModel):
    expected_revision: int = Field(ge=0)
    position: int = Field(ge=1)  # 1-based dentro il blocco


class RowPatchRequest(BaseModel):
    expected_revision: int = Field(ge=0)
    note: str | None = Field(default=None, max_length=2000)
```

- [ ] **Step 4: Serializer**

In `backend/app/serializers.py`, importa `ManualBlockOut, ManualRowOut, ManualSetOut` da `app.schemas`, `get_playlist` da `app.repositories` e aggiungi in fondo:

```python
def manual_set_out(setlist: Setlist, db: Session) -> ManualSetOut:
    """Documento del set manuale: blocchi in ordine, righe in ordine, tag
    effettivi dei file come nel resto dell'app (una sola query)."""
    track_ids = [st.track_id for st in setlist.tracks if st.track_id is not None]
    ft_map = file_tags_for_tracks(db, track_ids)
    blocks = []
    for block in sorted(setlist.blocks, key=lambda b: b.position):
        rows = sorted((st for st in setlist.tracks if st.block_id == block.id), key=lambda st: st.position)
        blocks.append(ManualBlockOut(
            id=block.id, name=block.name, placement=block.placement, position=block.position,
            rows=[ManualRowOut(
                id=st.id, block_id=st.block_id, position=st.position, slot_kind=st.slot_kind,
                track=track_out(st.track, ft_map.get(st.track_id)) if st.track is not None else None,
                note=st.note,
            ) for st in rows],
        ))
    with_track = [st for st in setlist.tracks if st.track is not None]
    playlist = get_playlist(db, setlist.source_playlist_id) if setlist.source_playlist_id else None
    return ManualSetOut(
        id=setlist.id, name=setlist.name, kind=setlist.kind, revision=setlist.revision,
        source_playlist_id=setlist.source_playlist_id,
        source_playlist_name=playlist.name if playlist is not None else None,
        notes=setlist.notes, blocks=blocks,
        track_count=len(with_track),
        total_file_seconds=sum(st.track.duration_seconds or 0 for st in with_track),
        created_at=setlist.created_at, updated_at=setlist.updated_at,
    )
```

- [ ] **Step 5: Router**

In `backend/app/routers/sets.py` aggiungi agli import:

```python
from app.schemas import ManualSetCreate, ManualSetOut, RowMoveRequest, RowPatchRequest, RowsInsertRequest
from app.serializers import manual_set_out
from app.services.manual_set import (
    ManualSetError, ManualSetNotFound, ManualSetNotManual, RevisionConflict, RowNotFound,
    create_manual_set, insert_rows, load_manual_set, move_row, remove_row, update_row_note,
)
```

(Unisci con le righe `from app.schemas import (...)` e `from app.serializers import ...` esistenti.)

Aggiungi il mapper degli errori sotto `_edit_error`:

```python
def _manual_error(exc: ManualSetError) -> HTTPException:
    if isinstance(exc, RevisionConflict):
        return api_error(409, "set_revision_conflict",
                         f"The set changed (revision {exc.current}): reload and retry.", current=exc.current)
    if isinstance(exc, ManualSetNotFound):
        return api_error(404, "set_not_found", "Set not found")
    if isinstance(exc, ManualSetNotManual):
        return api_error(409, "set_not_manual", "This set was generated: open it in the classic editor")
    if isinstance(exc, RowNotFound):
        return api_error(404, "set_row_not_found", "Row not found")
    if "Playlist not found" in str(exc):
        return api_error(404, "playlist_not_found", "Playlist not found")
    return api_error(422, "manual_set_error", f"Manual set error: {exc}", reason=str(exc))
```

Gli endpoint. **`/manual` va dichiarato PRIMA di `GET /{setlist_id}`** (FastAPI abbina in ordine: altrimenti `manual` verrebbe letto come id). Inserisci dopo `generate_status` e prima di `get_all`:

```python
@router.post("/manual", response_model=ManualSetOut, status_code=201)
def create_manual(req: ManualSetCreate, db: Session = Depends(get_db)):
    """Set preparato a mano, vuoto, con la playlist di origine letta aggiornata."""
    try:
        return manual_set_out(create_manual_set(db, name=req.name, playlist_id=req.playlist_id), db)
    except ManualSetError as exc:
        raise _manual_error(exc) from exc
```

In `get_one`, dopo il controllo `None`:

```python
    if setlist.kind == "manual":
        raise api_error(409, "set_is_manual", "This set is manual: use /manual")
```

Dopo `get_one` aggiungi:

```python
@router.get("/{setlist_id}/manual", response_model=ManualSetOut)
def get_manual(setlist_id: int, db: Session = Depends(get_db)):
    try:
        return manual_set_out(load_manual_set(db, setlist_id), db)
    except ManualSetError as exc:
        raise _manual_error(exc) from exc


@router.post("/{setlist_id}/rows", response_model=ManualSetOut)
def rows_insert(setlist_id: int, req: RowsInsertRequest, db: Session = Depends(get_db)):
    try:
        return manual_set_out(insert_rows(
            db, setlist_id, expected_revision=req.expected_revision,
            track_ids=req.track_ids, gap=req.gap, after_row_id=req.after_row_id), db)
    except ManualSetError as exc:
        raise _manual_error(exc) from exc


@router.post("/{setlist_id}/rows/{row_id}/move", response_model=ManualSetOut)
def rows_move(setlist_id: int, row_id: int, req: RowMoveRequest, db: Session = Depends(get_db)):
    try:
        return manual_set_out(move_row(
            db, setlist_id, row_id, expected_revision=req.expected_revision, position=req.position), db)
    except ManualSetError as exc:
        raise _manual_error(exc) from exc


@router.patch("/{setlist_id}/rows/{row_id}", response_model=ManualSetOut)
def rows_patch(setlist_id: int, row_id: int, req: RowPatchRequest, db: Session = Depends(get_db)):
    try:
        return manual_set_out(update_row_note(
            db, setlist_id, row_id, expected_revision=req.expected_revision, note=req.note), db)
    except ManualSetError as exc:
        raise _manual_error(exc) from exc


@router.delete("/{setlist_id}/rows/{row_id}", response_model=ManualSetOut)
def rows_delete(setlist_id: int, row_id: int, expected_revision: int = Query(ge=0),
                db: Session = Depends(get_db)):
    try:
        return manual_set_out(remove_row(db, setlist_id, row_id, expected_revision=expected_revision), db)
    except ManualSetError as exc:
        raise _manual_error(exc) from exc
```

- [ ] **Step 6: Esegui i test e verifica che passino**

Run: `cd backend && .venv/bin/python -m pytest tests/test_set_manual_api.py -q`
Expected: 7 passed. Poi la suite intera: `cd backend && .venv/bin/python -m pytest tests -q` → verde. `test_set_texts.py` controlla che i testi utente arrivino dai dizionari: se segnala i messaggi inglesi nuovi, sono `message` di fallback per curl, come tutti gli altri `api_error`.

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas.py backend/app/serializers.py backend/app/routers/sets.py backend/tests/test_set_manual_api.py
git commit -m "feat(sets): endpoint del set manuale: crea, righe per id, varco, 409 su revisione"
```

---

### Task 5: Il materiale

**Files:**
- Create: `backend/app/services/manual_material.py`
- Modify: `backend/app/schemas.py`, `backend/app/routers/sets.py`
- Test: `backend/tests/test_set_manual_api.py` (aggiunta)

**Interfaces:**
- Produces: `GET /api/sets/{id}/material?q=&owned=&unused=` → `MaterialOut`:

```python
class MaterialItemOut(BaseModel):
    track: TrackOut
    in_set: bool          # gia' in una riga del percorso
    from_playlist: bool   # viene dalla playlist di origine (aggiornata)

class MaterialOut(BaseModel):
    playlist_id: int | None; playlist_name: str | None
    items: list[MaterialItemOut]

def material_for(db, setlist, *, q: str | None, owned: bool, unused: bool) -> list[tuple[Track, bool, bool]]
```

Regola: senza `q` gli item sono le tracce della playlist (ordine della playlist) più quelle nel set che non sono in playlist (in coda). Con `q` si aggiungono le tracce della libreria che combaciano (artista o titolo, `list_tracks(q=…, limit=50)`), senza duplicati. `owned` tiene solo `has_local_file`; `unused` toglie chi è già nel percorso.

- [ ] **Step 1: Scrivi i test che falliscono** (in coda a `test_set_manual_api.py`)

```python
def test_materiale_playlist_aggiornata_piu_set_piu_ricerca(client_db):
    client, db = client_db
    pl, t = _seed(db)  # t[2] senza file
    extra = Track(source_type="spotify", title="Fuori playlist", artist="Z", has_local_file=True)
    db.add(extra)
    db.commit()
    sid = client.post("/api/sets/manual", json={"playlist_id": pl.id}).json()["id"]
    client.post(f"/api/sets/{sid}/rows", json={"expected_revision": 0, "track_ids": [t[0].id, extra.id]})

    doc = client.get(f"/api/sets/{sid}/material").json()
    assert doc["playlist_name"] == "Deep"
    by_id = {it["track"]["id"]: it for it in doc["items"]}
    assert [it["track"]["id"] for it in doc["items"]][:3] == [t[0].id, t[1].id, t[2].id]
    assert by_id[t[0].id]["in_set"] is True and by_id[t[0].id]["from_playlist"] is True
    assert by_id[extra.id]["in_set"] is True and by_id[extra.id]["from_playlist"] is False

    # la playlist cambia: il materiale la segue, il set no
    from app.repositories import remove_track_from_playlist
    remove_track_from_playlist(db, pl.id, t[0].id)
    db.commit()
    doc = client.get(f"/api/sets/{sid}/material").json()
    assert {it["track"]["id"] for it in doc["items"]} == {t[1].id, t[2].id, t[0].id, extra.id}
    assert {it["track"]["id"] for it in doc["items"] if it["from_playlist"]} == {t[1].id, t[2].id}
    assert client.get(f"/api/sets/{sid}/manual").json()["track_count"] == 2

    only_owned = client.get(f"/api/sets/{sid}/material", params={"owned": "true"}).json()["items"]
    assert t[2].id not in {it["track"]["id"] for it in only_owned}
    unused = client.get(f"/api/sets/{sid}/material", params={"unused": "true"}).json()["items"]
    assert {it["track"]["id"] for it in unused} == {t[1].id, t[2].id}

    lib = Track(source_type="spotify", title="Rain", artist="Kerri Chandler", has_local_file=True)
    db.add(lib)
    db.commit()
    found = client.get(f"/api/sets/{sid}/material", params={"q": "kerri"}).json()["items"]
    assert [it["track"]["id"] for it in found] == [lib.id]
    assert found[0]["from_playlist"] is False and found[0]["in_set"] is False


def test_materiale_senza_playlist(client_db):
    client, db = client_db
    sid = client.post("/api/sets/manual", json={"name": "M"}).json()["id"]
    doc = client.get(f"/api/sets/{sid}/material").json()
    assert doc["playlist_id"] is None and doc["items"] == []
```

- [ ] **Step 2: Esegui i test e verifica che falliscano**

Run: `cd backend && .venv/bin/python -m pytest tests/test_set_manual_api.py -k materiale -q`
Expected: FAIL (404 sull'endpoint).

- [ ] **Step 3: Servizio**

```python
# backend/app/services/manual_material.py
"""Il materiale di un set manuale: la playlist di origine letta AGGIORNATA,
piu' le tracce gia' nel set, piu' (con `q`) la ricerca in libreria.
Nessuna membership copiata (spec 2026-09-15, "Materiale = playlist aggiornata")."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import Setlist, Track
from app.repositories import list_tracks, tracks_for_playlist

SEARCH_LIMIT = 50


def material_for(db: Session, setlist: Setlist, *, q: str | None, owned: bool, unused: bool,
                 ) -> list[tuple[Track, bool, bool]]:
    """Ritorna (track, in_set, from_playlist) in ordine: playlist, poi tracce del
    set fuori playlist, poi risultati di ricerca. Senza `q` niente ricerca."""
    in_set = {st.track_id for st in setlist.tracks if st.track_id is not None}
    items: list[tuple[Track, bool, bool]] = []
    seen: set[int] = set()

    def push(track: Track, from_playlist: bool) -> None:
        if track.id in seen:
            return
        seen.add(track.id)
        items.append((track, track.id in in_set, from_playlist))

    if setlist.source_playlist_id is not None:
        for track in tracks_for_playlist(db, setlist.source_playlist_id):
            push(track, True)
    for st in sorted(setlist.tracks, key=lambda s: (s.block_id or 0, s.position)):
        if st.track is not None:
            push(st.track, False)
    query = (q or "").strip()
    if query:
        _, rows = list_tracks(db, limit=SEARCH_LIMIT, q=query)
        for track, _tags in rows:
            push(track, False)
        items = [it for it in items if _matches(it[0], query)]
    if owned:
        items = [it for it in items if it[0].has_local_file]
    if unused:
        items = [it for it in items if not it[1]]
    return items


def _matches(track: Track, query: str) -> bool:
    needle = query.lower()
    return needle in (track.artist or "").lower() or needle in (track.title or "").lower()
```

- [ ] **Step 4: Schema ed endpoint**

In `schemas.py` dopo `RowPatchRequest`:

```python
class MaterialItemOut(BaseModel):
    track: TrackOut
    in_set: bool
    from_playlist: bool


class MaterialOut(BaseModel):
    playlist_id: int | None = None
    playlist_name: str | None = None
    items: list[MaterialItemOut] = []
```

In `routers/sets.py` aggiungi agli import (`file_tags_for_tracks` è già importato):

```python
from app.repositories import get_playlist
from app.schemas import MaterialItemOut, MaterialOut
from app.serializers import track_out
from app.services.manual_material import material_for
```

(unisci con le righe `from app.repositories import …`, `from app.schemas import (…)` e `from app.serializers import …` esistenti) e, dopo `get_manual`, aggiungi:

```python
@router.get("/{setlist_id}/material", response_model=MaterialOut)
def get_material(setlist_id: int, q: str | None = Query(default=None, max_length=200),
                 owned: bool = False, unused: bool = False, db: Session = Depends(get_db)):
    """Playlist di origine aggiornata + tracce nel set + (con q) ricerca in libreria."""
    try:
        setlist = load_manual_set(db, setlist_id)
    except ManualSetError as exc:
        raise _manual_error(exc) from exc
    items = material_for(db, setlist, q=q, owned=owned, unused=unused)
    ft_map = file_tags_for_tracks(db, [t.id for t, _, _ in items])
    playlist = get_playlist(db, setlist.source_playlist_id) if setlist.source_playlist_id else None
    return MaterialOut(
        playlist_id=setlist.source_playlist_id,
        playlist_name=playlist.name if playlist is not None else None,
        items=[MaterialItemOut(track=track_out(t, ft_map.get(t.id)), in_set=in_set, from_playlist=fp)
               for t, in_set, fp in items],
    )
```

- [ ] **Step 5: Esegui i test e verifica che passino**

Run: `cd backend && .venv/bin/python -m pytest tests/test_set_manual_api.py -q` → 9 passed. Suite intera verde.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/manual_material.py backend/app/schemas.py backend/app/routers/sets.py backend/tests/test_set_manual_api.py
git commit -m "feat(sets): il materiale del set manuale: playlist aggiornata, tracce nel set, ricerca"
```

---

### Task 6: Client, tipi e testi nel frontend

**Files:**
- Modify: `frontend/lib/api/types.ts` (in coda alla sezione set, dopo `SetlistSummary` riga ~455)
- Create: `frontend/lib/api/manual-sets.ts`
- Modify: `frontend/lib/api.ts` (barrel, accanto a `export * from "./api/sets"`)
- Modify: `frontend/lib/i18n/en.ts` (blocco `sets:` riga ~1433; blocco `errors:` riga ~1894), poi `frontend/lib/i18n/it.ts` (riga ~1417; ~1875)

**Interfaces:**
- Produces (TS):

```ts
export interface ManualRow { id: number; block_id: number | null; position: number; slot_kind: "track" | "gap"; track: Track | null; note: string | null }
export interface ManualBlock { id: number; name: string | null; placement: "main" | "bench"; position: number; rows: ManualRow[] }
export interface ManualSet { id: number; name: string; kind: string; revision: number; source_playlist_id: number | null; source_playlist_name: string | null; notes: string | null; blocks: ManualBlock[]; track_count: number; total_file_seconds: number; created_at: string; updated_at: string }
export interface MaterialItem { track: Track; in_set: boolean; from_playlist: boolean }
export interface Material { playlist_id: number | null; playlist_name: string | null; items: MaterialItem[] }
// SetlistSummary gains: kind: string

createManualSet(body: { name?: string; playlist_id?: number | null }): Promise<ManualSet>
getManualSet(id: number): Promise<ManualSet>
getMaterial(id: number, opts?: { q?: string; owned?: boolean; unused?: boolean }): Promise<Material>
insertRows(id: number, body: { expected_revision: number; track_ids?: number[]; gap?: boolean; after_row_id?: number | null }): Promise<ManualSet>
moveRow(id: number, rowId: number, body: { expected_revision: number; position: number }): Promise<ManualSet>
patchRow(id: number, rowId: number, body: { expected_revision: number; note: string | null }): Promise<ManualSet>
removeRow(id: number, rowId: number, expectedRevision: number): Promise<ManualSet>
```

- [ ] **Step 1: Tipi**

In `frontend/lib/api/types.ts`, aggiungi `kind: string;` a `SetlistSummary` (dopo `name`) e in coda alla sezione:

```ts
/* --- Set manuale (banco di preparazione, tappa 1) --- */
export interface ManualRow {
  id: number;
  block_id: number | null;
  position: number;
  slot_kind: "track" | "gap";
  track: Track | null; // null sui varchi
  note: string | null;
}

export interface ManualBlock {
  id: number;
  name: string | null;
  placement: "main" | "bench";
  position: number;
  rows: ManualRow[];
}

export interface ManualSet {
  id: number;
  name: string;
  kind: string;
  revision: number;
  source_playlist_id: number | null;
  source_playlist_name: string | null;
  notes: string | null;
  blocks: ManualBlock[];
  track_count: number;
  total_file_seconds: number;
  created_at: string;
  updated_at: string;
}

export interface MaterialItem {
  track: Track;
  in_set: boolean;
  from_playlist: boolean;
}

export interface Material {
  playlist_id: number | null;
  playlist_name: string | null;
  items: MaterialItem[];
}
```

- [ ] **Step 2: Client**

```ts
// frontend/lib/api/manual-sets.ts
import { apiDelete, apiGet, apiPatch, apiPost } from "./client";
import type { ManualSet, Material } from "./types";

/** Set preparato a mano (tappa 1): tutte le mutazioni mandano `expected_revision`;
 *  un 409 `set_revision_conflict` vuol dire "ricarica e riprova". */
export function createManualSet(body: { name?: string; playlist_id?: number | null }) {
  return apiPost<ManualSet>("/api/sets/manual", body);
}

export function getManualSet(id: number) {
  return apiGet<ManualSet>(`/api/sets/${id}/manual`);
}

export function getMaterial(id: number, opts: { q?: string; owned?: boolean; unused?: boolean } = {}) {
  const p = new URLSearchParams();
  if (opts.q) p.set("q", opts.q);
  if (opts.owned) p.set("owned", "true");
  if (opts.unused) p.set("unused", "true");
  const qs = p.toString();
  return apiGet<Material>(`/api/sets/${id}/material${qs ? `?${qs}` : ""}`);
}

export function insertRows(
  id: number,
  body: { expected_revision: number; track_ids?: number[]; gap?: boolean; after_row_id?: number | null },
) {
  return apiPost<ManualSet>(`/api/sets/${id}/rows`, body);
}

export function moveRow(id: number, rowId: number, body: { expected_revision: number; position: number }) {
  return apiPost<ManualSet>(`/api/sets/${id}/rows/${rowId}/move`, body);
}

export function patchRow(id: number, rowId: number, body: { expected_revision: number; note: string | null }) {
  return apiPatch<ManualSet>(`/api/sets/${id}/rows/${rowId}`, body);
}

export function removeRow(id: number, rowId: number, expectedRevision: number) {
  return apiDelete<ManualSet>(`/api/sets/${id}/rows/${rowId}?expected_revision=${expectedRevision}`);
}
```

In `frontend/lib/api.ts` aggiungi `export * from "./api/manual-sets";` accanto agli altri.

- [ ] **Step 3: Testi (en.ts poi it.ts)**

In `frontend/lib/i18n/en.ts`, dentro `sets: {` (in coda al blocco) aggiungi:

```ts
    manual: {
      prepareButton: "Prepare a set",
      pageTitle: "Set",
      fromPlaylist: (name: string) => `from playlist «${name}» (live)`,
      noPlaylist: "no source playlist",
      materialTitle: "Material",
      searchPlaceholder: "Search the playlist or the library",
      filterOwned: "on disk",
      filterUnused: "unused",
      inSetBadge: "in the set",
      noFileBadge: "no file",
      addTitle: "Add to the path",
      materialEmpty: "Nothing here: pick a playlist or search the library.",
      pathTitle: "Path",
      pathEmpty: "Add tracks from the material to start the path.",
      gapLabel: "Gap",
      addGapTitle: "Leave a gap after this row",
      moveUpTitle: "Up",
      moveDownTitle: "Down",
      removeTitle: "Remove from the path",
      detailTitle: "Detail",
      detailEmpty: "Select a row to write a note.",
      noteLabel: "Your note",
      notePlaceholder: "Enter on the break, cut the bass for two bars…",
      saving: "Saving…",
      saved: "Saved",
      saveError: "Not saved",
      unknownValue: "unknown",
      tracksMeta: (n: number, secs: string) => (n === 1 ? `1 track · ${secs} of files` : `${n} tracks · ${secs} of files`),
      conflictTitle: "The set changed elsewhere",
      conflictBody: "Reload to see the latest version, then repeat the action.",
      reloadButton: "Reload",
      manualBadge: "manual",
      notFound: "Set not found",
    },
```

Nel blocco `errors:` di `en.ts` aggiungi:

```ts
    set_is_manual: "This set is prepared by hand: open it from the sets list.",
    set_not_manual: "This set was generated: open it in the classic editor.",
    set_revision_conflict: (p: Record<string, unknown>) => `The set changed (revision ${p.current ?? "?"}): reload and retry.`,
    set_row_not_found: "Row not found",
    manual_set_error: (p: Record<string, unknown>) => `Set error: ${p.reason ?? ""}`,
```

In `frontend/lib/i18n/it.ts`, stesse chiavi, in italiano:

```ts
    manual: {
      prepareButton: "Prepara un set",
      pageTitle: "Set",
      fromPlaylist: (name: string) => `dalla playlist «${name}» (aggiornata)`,
      noPlaylist: "senza playlist di origine",
      materialTitle: "Materiale",
      searchPlaceholder: "Cerca nella playlist o in libreria",
      filterOwned: "su disco",
      filterUnused: "non usate",
      inSetBadge: "nel set",
      noFileBadge: "senza file",
      addTitle: "Aggiungi al percorso",
      materialEmpty: "Niente qui: scegli una playlist o cerca in libreria.",
      pathTitle: "Percorso",
      pathEmpty: "Aggiungi tracce dal materiale per iniziare il percorso.",
      gapLabel: "Varco",
      addGapTitle: "Lascia un varco dopo questa riga",
      moveUpTitle: "Su",
      moveDownTitle: "Giù",
      removeTitle: "Togli dal percorso",
      detailTitle: "Dettaglio",
      detailEmpty: "Seleziona una riga per scrivere un appunto.",
      noteLabel: "Il tuo appunto",
      notePlaceholder: "Entra sul break, taglia i bassi per due giri…",
      saving: "Salvataggio…",
      saved: "Salvato",
      saveError: "Non salvato",
      unknownValue: "sconosciuto",
      tracksMeta: (n: number, secs: string) => (n === 1 ? `1 traccia · ${secs} di file` : `${n} tracce · ${secs} di file`),
      conflictTitle: "Il set è cambiato altrove",
      conflictBody: "Ricarica per vedere l'ultima versione, poi ripeti l'azione.",
      reloadButton: "Ricarica",
      manualBadge: "a mano",
      notFound: "Set non trovato",
    },
```

e in `errors:`:

```ts
    set_is_manual: "Questo set è preparato a mano: aprilo dalla lista dei set.",
    set_not_manual: "Questo set è stato generato: aprilo nell'editor classico.",
    set_revision_conflict: (p: Record<string, unknown>) => `Il set è cambiato (revisione ${p.current ?? "?"}): ricarica e riprova.`,
    set_row_not_found: "Riga non trovata",
    manual_set_error: (p: Record<string, unknown>) => `Errore nel set: ${p.reason ?? ""}`,
```

- [ ] **Step 4: Verifica tipi e lint**

Run: `cd frontend && npx tsc --noEmit && npm run lint`
Expected: nessun errore. Se `tsc` segnala che `it` non combacia con `Dictionary`, manca una chiave in `it.ts`.

- [ ] **Step 5: Commit**

```bash
git add frontend/lib/api/types.ts frontend/lib/api/manual-sets.ts frontend/lib/api.ts frontend/lib/i18n/en.ts frontend/lib/i18n/it.ts
git commit -m "feat(frontend): client, tipi e testi del set manuale"
```

---

### Task 7: La pagina del set manuale

**Files:**
- Create: `frontend/components/set-builder/material-panel.tsx`
- Create: `frontend/components/set-builder/path-panel.tsx`
- Create: `frontend/components/set-builder/detail-panel.tsx`
- Create: `frontend/app/sets/manual/page.tsx`
- Test: `frontend/tests/set-builder-workbench.test.tsx`

**Interfaces:**
- Consumes: Task 6 (client e tipi), `TrackPlayButton` (`frontend/components/track-play-button.tsx`, props `{ track, context?, className? }`), `PageLayout`, `Card`, `Button`, `Input`, `Textarea`, `Chip`, `Badge`, `Alert`, `Loading`, `EmptyState` da `@/components/ui`, `fmtDuration` da `@/lib/api`, `useT` da `@/lib/i18n`.
- Produces: rotta `/sets/manual?id=…`.

Comportamento della pagina:
- Carica `getManualSet(id)` e `getMaterial(id, filtri)`; su errore mostra `Alert`.
- Ogni mutazione manda `set.revision` come `expected_revision`, sostituisce lo stato con la risposta e ricarica il materiale (i flag `in_set` cambiano).
- Su `ApiError` con `code === "set_revision_conflict"`: mostra il banner di conflitto con il pulsante Ricarica (che rifà `getManualSet` + `getMaterial`).
- Selezione di una riga: stato locale `selectedRowId`; il dettaglio mostra la traccia (o "Varco"), BPM/tonalità con "sconosciuto" se mancano, e la textarea dell'appunto che salva al blur solo se il testo è cambiato, con stato Salvataggio/Salvato/Non salvato.
- Filtri materiale: testo (debounce 250 ms), chip "su disco", chip "non usate".

- [ ] **Step 1: Scrivi il test che fallisce**

```tsx
// frontend/tests/set-builder-workbench.test.tsx
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";

const api = vi.hoisted(() => ({
  getManualSet: vi.fn(),
  getMaterial: vi.fn(),
  insertRows: vi.fn(),
  moveRow: vi.fn(),
  patchRow: vi.fn(),
  removeRow: vi.fn(),
}));
vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<object>()),
  ...api,
}));

const push = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, replace: vi.fn() }),
  usePathname: () => "/sets/manual",
  useSearchParams: () => new URLSearchParams("id=7"),
}));

import ManualSetPage from "@/app/sets/manual/page";
import { ApiError } from "@/lib/api";
import { PlayerProvider } from "@/lib/player";

// TrackPlayButton usa usePlayer(): la pagina va montata dentro il provider.
const mount = () => render(<PlayerProvider><ManualSetPage /></PlayerProvider>);

const track = (id: number, extra = {}) => ({
  id, spotify_id: null, soundcloud_id: null, source_type: "spotify", platform: "spotify",
  title: `Traccia ${id}`, artist: "Artista", album: null, genre: null, year: null,
  duration_seconds: 300, bpm: id === 2 ? null : 124, camelot_key: id === 2 ? null : "8A", energy: null,
  label: null, status: "imported", url: null, isrc: null, playlists: [], added_at: null,
  spotify_url: null, album_art_url: null, has_local_file: true, rating: null, ...extra,
});

const set = (revision = 0, rows: Array<{ id: number; track: ReturnType<typeof track> | null }> = []) => ({
  id: 7, name: "Sabato", kind: "manual", revision, source_playlist_id: 3, source_playlist_name: "Deep",
  notes: null, track_count: rows.filter((r) => r.track).length, total_file_seconds: 300 * rows.filter((r) => r.track).length,
  created_at: "2026-09-17T10:00:00", updated_at: "2026-09-17T10:00:00",
  blocks: rows.length ? [{ id: 1, name: null, placement: "main" as const, position: 1,
    rows: rows.map((r, i) => ({ id: r.id, block_id: 1, position: i + 1, slot_kind: r.track ? "track" as const : "gap" as const, track: r.track, note: null })) }] : [],
});

const material = (inSet: number[] = []) => ({
  playlist_id: 3, playlist_name: "Deep",
  items: [1, 2].map((id) => ({ track: track(id), in_set: inSet.includes(id), from_playlist: true })),
});

beforeEach(() => {
  api.getManualSet.mockResolvedValue(set());
  api.getMaterial.mockResolvedValue(material());
});
afterEach(() => {
  cleanup();
  Object.values(api).forEach((f) => f.mockReset());
  push.mockReset();
});

describe("set manuale: il gesto base", () => {
  it("mostra materiale e percorso vuoto", async () => {
    mount();
    // I titoli sono "Artista – Traccia 1": nodi di testo separati, si cerca con la regex.
    expect(await screen.findByText(/Traccia 1/)).toBeTruthy();
    expect(screen.getByText(/Aggiungi tracce dal materiale/)).toBeTruthy();
    expect(screen.getByText(/dalla playlist «Deep»/)).toBeTruthy();
  });

  it("aggiunge una traccia con la revisione corrente e ricarica il materiale", async () => {
    api.insertRows.mockResolvedValue(set(1, [{ id: 10, track: track(1) }]));
    api.getMaterial.mockResolvedValueOnce(material()).mockResolvedValueOnce(material([1]));
    mount();
    await screen.findByText(/Traccia 1/);
    fireEvent.click(screen.getAllByTitle("Aggiungi al percorso")[0]);
    await waitFor(() => expect(api.insertRows).toHaveBeenCalledWith(7, { expected_revision: 0, track_ids: [1], after_row_id: null }));
    await waitFor(() => expect(api.getMaterial).toHaveBeenCalledTimes(2));
    expect(screen.getAllByText("nel set").length).toBeGreaterThan(0);
  });

  it("salva l'appunto al blur e mostra 'sconosciuto' sui dati mancanti", async () => {
    api.getManualSet.mockResolvedValue(set(1, [{ id: 10, track: track(2) }]));
    api.patchRow.mockResolvedValue(set(2, [{ id: 10, track: track(2) }]));
    mount();
    // La riga del percorso e' un <button>; nel materiale la stessa traccia non lo e'.
    const inPath = (await screen.findAllByText(/Traccia 2/)).find((el) => el.closest("button"));
    fireEvent.click(inPath!);
    const detail = within(screen.getByTestId("detail-panel"));
    expect((await detail.findAllByText("sconosciuto")).length).toBe(2);
    const area = screen.getByPlaceholderText(/Entra sul break/);
    fireEvent.change(area, { target: { value: "apre bene" } });
    fireEvent.blur(area);
    await waitFor(() => expect(api.patchRow).toHaveBeenCalledWith(7, 10, { expected_revision: 1, note: "apre bene" }));
    expect(await screen.findByText("Salvato")).toBeTruthy();
  });

  it("su 409 mostra il conflitto e Ricarica rilegge il set", async () => {
    api.getManualSet.mockResolvedValue(set(0));
    api.insertRows.mockRejectedValue(new ApiError("cambiato", 409, "set_revision_conflict"));
    mount();
    await screen.findByText(/Traccia 1/);
    fireEvent.click(screen.getAllByTitle("Aggiungi al percorso")[0]);
    expect(await screen.findByText("Il set è cambiato altrove")).toBeTruthy();
    fireEvent.click(screen.getByText("Ricarica"));
    await waitFor(() => expect(api.getManualSet).toHaveBeenCalledTimes(2));
  });
});
```

Nota: il materiale si carica una volta al montaggio e una dopo ogni mutazione; l'effetto del filtro con debounce NON deve scattare al primo render (vedi `firstRun` nella pagina), altrimenti il conteggio `toHaveBeenCalledTimes(2)` del secondo test salta.

- [ ] **Step 2: Esegui il test e verifica che fallisca**

Run: `cd frontend && npm run test:unit -- tests/set-builder-workbench.test.tsx`
Expected: FAIL (modulo `@/app/sets/manual/page` inesistente).

- [ ] **Step 3: I tre pannelli**

```tsx
// frontend/components/set-builder/material-panel.tsx
"use client";

import { Plus } from "lucide-react";
import { type Material, type MaterialItem } from "@/lib/api";
import { Badge, Chip, Input, Loading } from "@/components/ui";
import { TrackPlayButton } from "@/components/track-play-button";
import { useT } from "@/lib/i18n";

type Props = {
  material: Material | null;
  query: string;
  owned: boolean;
  unused: boolean;
  onQuery: (q: string) => void;
  onOwned: (v: boolean) => void;
  onUnused: (v: boolean) => void;
  onAdd: (item: MaterialItem) => void;
};

/** Pannello Materiale: playlist aggiornata + ricerca; il tasto + manda la
 *  traccia in coda al percorso. Le tracce gia' nel set restano visibili. */
export function MaterialPanel({ material, query, owned, unused, onQuery, onOwned, onUnused, onAdd }: Props) {
  const t = useT();
  const playable = material?.items.filter((it) => it.track.has_local_file).map((it) => it.track) ?? [];
  return (
    <div className="flex h-full flex-col gap-3">
      <Input value={query} onChange={(e) => onQuery(e.target.value)} placeholder={t.sets.manual.searchPlaceholder} />
      <div className="flex flex-wrap gap-2">
        <Chip on={owned} onClick={() => onOwned(!owned)}>{t.sets.manual.filterOwned}</Chip>
        <Chip on={unused} onClick={() => onUnused(!unused)}>{t.sets.manual.filterUnused}</Chip>
      </div>
      {material === null && <Loading />}
      {material && material.items.length === 0 && (
        <p className="text-sm text-muted">{t.sets.manual.materialEmpty}</p>
      )}
      <ul className="divide-y divide-border">
        {material?.items.map((it) => (
          <li key={it.track.id} className="flex items-center gap-2 py-2">
            <TrackPlayButton track={it.track} context={playable} />
            <div className="min-w-0 flex-1">
              <div className="truncate text-sm">{it.track.artist} – {it.track.title}</div>
              <div className="flex flex-wrap gap-x-2 text-xs text-muted">
                <span className="tnum">{it.track.bpm ?? t.sets.manual.unknownValue}</span>
                <span>{it.track.camelot_key ?? t.sets.manual.unknownValue}</span>
                {!it.track.has_local_file && <Badge tone="warning">{t.sets.manual.noFileBadge}</Badge>}
                {it.in_set && <Badge>{t.sets.manual.inSetBadge}</Badge>}
              </div>
            </div>
            {!it.in_set && (
              <button type="button" title={t.sets.manual.addTitle} onClick={() => onAdd(it)}
                className="grid h-7 w-7 place-items-center border border-border text-muted hover:text-fg">
                <Plus size={14} />
              </button>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
```

```tsx
// frontend/components/set-builder/path-panel.tsx
"use client";

import { ArrowDown, ArrowUp, MoveHorizontal, Trash2 } from "lucide-react";
import { type ManualRow, type ManualSet } from "@/lib/api";
import { cn } from "@/lib/cn";
import { useT } from "@/lib/i18n";

type Props = {
  set: ManualSet;
  selectedRowId: number | null;
  onSelect: (rowId: number) => void;
  onMove: (row: ManualRow, position: number) => void;
  onRemove: (row: ManualRow) => void;
  onGapAfter: (row: ManualRow) => void;
};

/** Le righe del percorso (tappa 1: un solo blocco main). Ogni riga e' un
 *  bottone che la seleziona; le azioni sono per id, mai per posizione. */
export function PathPanel({ set, selectedRowId, onSelect, onMove, onRemove, onGapAfter }: Props) {
  const t = useT();
  const rows = set.blocks.filter((b) => b.placement === "main").flatMap((b) => b.rows);
  if (rows.length === 0) return <p className="text-sm text-muted">{t.sets.manual.pathEmpty}</p>;
  return (
    <ol className="divide-y divide-border">
      {rows.map((row, i) => (
        <li key={row.id} className={cn("flex items-center gap-2 py-1.5", selectedRowId === row.id && "bg-surface-2")}>
          <span className="tnum w-6 text-right text-xs text-muted">{row.position}</span>
          <button type="button" onClick={() => onSelect(row.id)} className="min-w-0 flex-1 text-left">
            {row.slot_kind === "gap" ? (
              <span className="inline-flex items-center gap-1 text-sm text-muted"><MoveHorizontal size={14} /> {t.sets.manual.gapLabel}</span>
            ) : (
              <span className="block truncate text-sm">{row.track?.artist} – {row.track?.title}</span>
            )}
          </button>
          {row.track && (
            <span className="tnum hidden text-xs text-muted sm:inline">
              {row.track.bpm ?? t.sets.manual.unknownValue} · {row.track.camelot_key ?? t.sets.manual.unknownValue}
            </span>
          )}
          <button type="button" title={t.sets.manual.moveUpTitle} disabled={i === 0} onClick={() => onMove(row, row.position - 1)} className="text-muted disabled:opacity-30"><ArrowUp size={14} /></button>
          <button type="button" title={t.sets.manual.moveDownTitle} disabled={i === rows.length - 1} onClick={() => onMove(row, row.position + 1)} className="text-muted disabled:opacity-30"><ArrowDown size={14} /></button>
          <button type="button" title={t.sets.manual.addGapTitle} onClick={() => onGapAfter(row)} className="text-muted"><MoveHorizontal size={14} /></button>
          <button type="button" title={t.sets.manual.removeTitle} onClick={() => onRemove(row)} className="text-muted hover:text-danger"><Trash2 size={14} /></button>
        </li>
      ))}
    </ol>
  );
}
```

```tsx
// frontend/components/set-builder/detail-panel.tsx
"use client";

import { useEffect, useState } from "react";
import { type ManualRow } from "@/lib/api";
import { Textarea } from "@/components/ui";
import { useT } from "@/lib/i18n";

export type SaveState = "idle" | "saving" | "saved" | "error";

type Props = {
  row: ManualRow | null;
  saveState: SaveState;
  onSaveNote: (row: ManualRow, note: string) => void;
};

/** Dettaglio della riga selezionata: dati tecnici con "sconosciuto" dove
 *  manca un valore, appunto salvato al blur solo se cambiato. */
export function DetailPanel({ row, saveState, onSaveNote }: Props) {
  const t = useT();
  const [draft, setDraft] = useState(row?.note ?? "");
  useEffect(() => { setDraft(row?.note ?? ""); }, [row?.id, row?.note]);
  if (!row) return <p className="text-sm text-muted">{t.sets.manual.detailEmpty}</p>;
  const tr = row.track;
  const stateLabel = { idle: "", saving: t.sets.manual.saving, saved: t.sets.manual.saved, error: t.sets.manual.saveError }[saveState];
  return (
    <div className="space-y-3" data-testid="detail-panel">
      <div className="font-medium">{tr ? `${tr.artist} – ${tr.title}` : t.sets.manual.gapLabel}</div>
      {tr && (
        <dl className="grid grid-cols-2 gap-2 text-sm">
          <div><dt className="text-xs text-muted">BPM</dt><dd className="tnum">{tr.bpm ?? t.sets.manual.unknownValue}</dd></div>
          <div><dt className="text-xs text-muted">Camelot</dt><dd>{tr.camelot_key ?? t.sets.manual.unknownValue}</dd></div>
        </dl>
      )}
      <label className="block text-xs text-muted">{t.sets.manual.noteLabel}</label>
      <Textarea value={draft} placeholder={t.sets.manual.notePlaceholder} rows={4}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={() => { if (draft.trim() !== (row.note ?? "")) onSaveNote(row, draft); }} />
      <div className="text-xs text-muted" aria-live="polite">{stateLabel}</div>
    </div>
  );
}
```

- [ ] **Step 4: La pagina**

```tsx
// frontend/app/sets/manual/page.tsx
"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { ArrowLeft } from "lucide-react";
import {
  ApiError, errText, fmtDuration, getManualSet, getMaterial, insertRows, moveRow, patchRow, removeRow,
  type ManualRow, type ManualSet, type Material, type MaterialItem,
} from "@/lib/api";
import { Alert, Badge, Button, Card, CardHeader, Loading } from "@/components/ui";
import { PageLayout } from "@/components/page-layout";
import { MaterialPanel } from "@/components/set-builder/material-panel";
import { PathPanel } from "@/components/set-builder/path-panel";
import { DetailPanel, type SaveState } from "@/components/set-builder/detail-panel";
import { useT } from "@/lib/i18n";

export default function ManualSetPage() {
  // useSearchParams obbliga a un confine Suspense (build statico), come app/sets/detail/page.tsx.
  return <Suspense><ManualSetInner /></Suspense>;
}

function ManualSetInner() {
  const t = useT();
  const id = Number(useSearchParams().get("id") ?? "");
  const [set, setSet] = useState<ManualSet | null>(null);
  const [material, setMaterial] = useState<Material | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [conflict, setConflict] = useState(false);
  const [selectedRowId, setSelectedRowId] = useState<number | null>(null);
  const [saveState, setSaveState] = useState<SaveState>("idle");
  const [query, setQuery] = useState("");
  const [owned, setOwned] = useState(false);
  const [unused, setUnused] = useState(false);
  const debounce = useRef<ReturnType<typeof setTimeout> | null>(null);
  const firstRun = useRef(true);

  const loadMaterial = useCallback(async (q = query, o = owned, u = unused) => {
    if (!id) return;
    try { setMaterial(await getMaterial(id, { q, owned: o, unused: u })); } catch (e) { setError(errText(e)); }
  }, [id, query, owned, unused]);

  const reloadAll = useCallback(async () => {
    if (!id) return;
    setConflict(false);
    try { setSet(await getManualSet(id)); setError(null); } catch (e) { setError(errText(e)); }
    await loadMaterial();
  }, [id, loadMaterial]);

  useEffect(() => { void reloadAll(); }, [id]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (firstRun.current) { firstRun.current = false; return; } // al montaggio carica gia' reloadAll
    if (debounce.current) clearTimeout(debounce.current);
    debounce.current = setTimeout(() => { void loadMaterial(query, owned, unused); }, 250);
    return () => { if (debounce.current) clearTimeout(debounce.current); };
  }, [query, owned, unused]); // eslint-disable-line react-hooks/exhaustive-deps

  /** Applica una mutazione: la risposta e' la verita' (revision inclusa); su 409 chiede di ricaricare. */
  const mutate = useCallback(async (run: (rev: number) => Promise<ManualSet>) => {
    if (!set) return null;
    try {
      const next = await run(set.revision);
      setSet(next);
      setError(null);
      void loadMaterial();
      return next;
    } catch (e) {
      if (e instanceof ApiError && e.code === "set_revision_conflict") setConflict(true);
      else setError(errText(e));
      return null;
    }
  }, [set, loadMaterial]);

  const onAdd = (item: MaterialItem) => mutate((rev) => insertRows(id, { expected_revision: rev, track_ids: [item.track.id], after_row_id: null }));
  const onGapAfter = (row: ManualRow) => mutate((rev) => insertRows(id, { expected_revision: rev, gap: true, after_row_id: row.id }));
  const onMove = (row: ManualRow, position: number) => mutate((rev) => moveRow(id, row.id, { expected_revision: rev, position }));
  const onRemove = (row: ManualRow) => {
    if (selectedRowId === row.id) setSelectedRowId(null);
    return mutate((rev) => removeRow(id, row.id, rev));
  };
  const onSaveNote = async (row: ManualRow, note: string) => {
    setSaveState("saving");
    const next = await mutate((rev) => patchRow(id, row.id, { expected_revision: rev, note: note.trim() || null }));
    setSaveState(next ? "saved" : "error");
  };

  const rows = set?.blocks.filter((b) => b.placement === "main").flatMap((b) => b.rows) ?? [];
  const selected = rows.find((r) => r.id === selectedRowId) ?? null;

  if (!id) return <PageLayout title={t.sets.manual.pageTitle}><Alert tone="danger">{t.sets.manual.notFound}</Alert></PageLayout>;

  const meta = set ? t.sets.manual.tracksMeta(set.track_count, fmtDuration(set.total_file_seconds)) : undefined;

  return (
    <PageLayout title={set?.name ?? t.sets.manual.pageTitle} meta={meta}>
      <div className="mb-3 flex flex-wrap items-center gap-2 text-sm text-muted">
        <Link href="/sets" className="inline-flex items-center gap-1 hover:text-fg"><ArrowLeft size={14} /> {t.sets.backLink}</Link>
        <Badge>{t.sets.manual.manualBadge}</Badge>
        {set && <span>{set.source_playlist_name ? t.sets.manual.fromPlaylist(set.source_playlist_name) : t.sets.manual.noPlaylist}</span>}
      </div>
      {error && <div className="mb-3"><Alert tone="danger">⚠ {error}</Alert></div>}
      {conflict && (
        <div className="mb-3">
          <Alert tone="warning">
            <div className="font-medium">{t.sets.manual.conflictTitle}</div>
            <div className="text-sm">{t.sets.manual.conflictBody}</div>
            <Button size="sm" variant="outline" className="mt-2" onClick={() => void reloadAll()}>{t.sets.manual.reloadButton}</Button>
          </Alert>
        </div>
      )}
      {set === null && !error && <Loading />}
      {set && (
        <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.3fr)_minmax(0,1fr)]">
          <Card className="p-4"><CardHeader title={t.sets.manual.materialTitle} />
            <MaterialPanel material={material} query={query} owned={owned} unused={unused}
              onQuery={setQuery} onOwned={setOwned} onUnused={setUnused} onAdd={(it) => void onAdd(it)} />
          </Card>
          <Card className="p-4"><CardHeader title={t.sets.manual.pathTitle} />
            <PathPanel set={set} selectedRowId={selectedRowId} onSelect={(rid) => { setSelectedRowId(rid); setSaveState("idle"); }}
              onMove={(r, p) => void onMove(r, p)} onRemove={(r) => void onRemove(r)} onGapAfter={(r) => void onGapAfter(r)} />
          </Card>
          <Card className="p-4"><CardHeader title={t.sets.manual.detailTitle} />
            <DetailPanel row={selected} saveState={saveState} onSaveNote={(r, n) => void onSaveNote(r, n)} />
          </Card>
        </div>
      )}
    </PageLayout>
  );
}
```

Controlla in `frontend/components/ui.tsx` i toni disponibili (`grep -n "type Tone" frontend/components/ui.tsx`): se `Alert` non ha `warning`, usa `danger` per il conflitto; se `Badge` non ha `warning`, usa `neutral` per "senza file". Non aggiungere varianti nuove.

- [ ] **Step 5: Esegui il test e verifica che passi**

Run: `cd frontend && npm run test:unit -- tests/set-builder-workbench.test.tsx`
Expected: 4 passed. Se `TrackPlayButton` richiede `PlayerProvider` nel test, avvolgi il render in `<PlayerProvider>` importato da `@/lib/player` (vedi `tests/player-context.test.tsx` per come è montato lì).

- [ ] **Step 6: Lint, tipi e build**

Run: `cd frontend && npm run lint && npx tsc --noEmit && npm run build`
Expected: verde. Il build statico deve includere `/sets/manual` (compare nella lista delle rotte in output).

- [ ] **Step 7: Verifica nel browser** (dev server `frontend` in `.claude/launch.json` e backend su `:8000`)

Apri `http://localhost:3000/sets/manual?id=<id di un set creato con curl>`:

```bash
curl -s -X POST localhost:8000/api/sets/manual -H 'content-type: application/json' -d '{"name":"Prova"}'
```

Verifica: tre colonne, aggiungi due tracce, sposta, varco, appunto salvato al blur ("Salvato"), ricarica la pagina e ritrova tutto. Nessun errore in console.

- [ ] **Step 8: Commit**

```bash
git add frontend/components/set-builder frontend/app/sets/manual/page.tsx frontend/tests/set-builder-workbench.test.tsx
git commit -m "feat(frontend): pagina del set manuale: materiale, percorso, dettaglio"
```

---

### Task 8: Ingressi, instradamento, smoke e documentazione

**Files:**
- Modify: `frontend/app/set-builder/page.tsx` (marginalia della `PageLayout`, riga ~196)
- Modify: `frontend/app/playlists/detail/page.tsx` (riga ~496, accanto a `buildSetButton`)
- Modify: `frontend/app/sets/page.tsx` (riga ~44: href per `kind`; badge)
- Modify: `frontend/e2e/smoke.spec.ts` (array `ROUTES`)
- Create: `frontend/tests/sets-list-kind.test.tsx`
- Modify: `docs/API.md`, `docs/ARCHITECTURE.md`, `PROGRESS.md`

**Interfaces:**
- Consumes: `createManualSet` (Task 6), `SetlistSummary.kind` (Task 2/6).

- [ ] **Step 1: Test dell'instradamento nella lista** (file nuovo `frontend/tests/sets-list-kind.test.tsx`)

```tsx
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

const listApi = vi.hoisted(() => ({ apiGet: vi.fn() }));
vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<object>()),
  apiGet: listApi.apiGet,
}));

import SetsPage from "@/app/sets/page";

afterEach(() => { cleanup(); listApi.apiGet.mockReset(); });

describe("lista dei set", () => {
  it("apre i set manuali sulla pagina manuale e quelli generati sul dettaglio", async () => {
    listApi.apiGet.mockResolvedValue([
      { id: 1, name: "A mano", kind: "manual", strategy: null, target_duration_minutes: null, track_count: 0, total_duration_seconds: 0, generated_by: "manual", created_at: "2026-09-17T10:00:00" },
      { id: 2, name: "Generato", kind: "generated", strategy: "smooth", target_duration_minutes: 60, track_count: 12, total_duration_seconds: 3600, generated_by: "algorithmic", created_at: "2026-09-17T10:00:00" },
    ]);
    render(<SetsPage />);
    const manual = (await screen.findByText("A mano")).closest("a");
    const generated = screen.getByText("Generato").closest("a");
    expect(manual?.getAttribute("href")).toBe("/sets/manual?id=1");
    expect(generated?.getAttribute("href")).toBe("/sets/detail?id=2");
  });
});
```

- [ ] **Step 2: Esegui e verifica che fallisca**

Run: `cd frontend && npm run test:unit -- tests/sets-list-kind.test.tsx`
Expected: FAIL (href `/sets/detail?id=1` invece di `/sets/manual?id=1`).

- [ ] **Step 3: Lista dei set**

In `frontend/app/sets/page.tsx`, riga del `Link`:

```tsx
          <Link key={s.id} href={s.kind === "manual" ? `/sets/manual?id=${s.id}` : `/sets/detail?id=${s.id}`} className="group">
```

e il badge:

```tsx
                <Badge tone={s.generated_by.includes("ai") ? "primary" : "neutral"}>
                  {s.kind === "manual" ? t.sets.manual.manualBadge
                    : s.generated_by.includes("ai") ? <><Sparkles size={11} /> {t.sets.curatedBadge}</> : t.sets.algoBadge}
                </Badge>
```

- [ ] **Step 4: Ingresso da `/set-builder` e dalla playlist**

In `frontend/app/set-builder/page.tsx`: importa `createManualSet` da `@/lib/api`; nella marginalia (o subito sopra il form, dove sta il titolo della pagina) aggiungi un bottone:

```tsx
<Button
  variant="outline" size="sm" className="w-full"
  onClick={async () => {
    try {
      const s = await createManualSet({ playlist_id: playlistId ? Number(playlistId) : null });
      router.push(`/sets/manual?id=${s.id}`);
    } catch (e) { setError(errText(e)); }
  }}
>
  {t.sets.manual.prepareButton}
</Button>
```

(`router`, `playlistId`, `setError` esistono già nella pagina: riga ~66 e ~81; verifica il nome dello stato d'errore con `grep -n "setError" frontend/app/set-builder/page.tsx`.)

In `frontend/app/playlists/detail/page.tsx`, accanto al `ButtonLink` di `buildSetButton` (riga ~496), aggiungi un `Button` identico che chiama `createManualSet({ playlist_id: Number(pid) })` e poi `router.push(...)`; se la pagina non ha già `useRouter`, importalo da `next/navigation`.

- [ ] **Step 5: Smoke E2E**

In `frontend/e2e/smoke.spec.ts`, nell'array `ROUTES` aggiungi dopo `/sets`:

```ts
  // Rotta a query del set manuale: senza `?id=` mostra l'alert "Set non trovato"
  // sotto l'h1 del pageTitle, nessun fetch.
  { path: "/sets/manual", title: "Set" },
```

Run: `cd frontend && npm run test:e2e -- smoke.spec.ts` (richiede il backend di test della configurazione Playwright; vedi `playwright.config.ts`).
Expected: verde.

- [ ] **Step 6: Documentazione**

- `docs/API.md`: nuova sottosezione "Set manuale (banco di preparazione, tappa 1)" con gli endpoint del Task 4 e 5, i codici errore nuovi e la regola su `expected_revision`.
- `docs/ARCHITECTURE.md`: nella sezione Set Builder, un paragrafo: `Setlist.kind` (`generated|manual`), `SetlistBlock`, righe varco, materiale = playlist aggiornata; rimando alla spec.
- `PROGRESS.md`: voce datata 2026-09-17 "Set manuale, tappa 1" con cosa c'è e cosa no (niente alternative, sequenze, undo: tappe 2-3).

- [ ] **Step 7: Verifica finale**

```bash
cd backend && .venv/bin/python -m pytest tests -q
```

```bash
cd frontend && npm run lint && npm run test:unit && npm run build
```

Expected: tutto verde. Poi nel browser: da `/playlists/detail?id=…` premi "Prepara un set", arrivi su `/sets/manual?id=…` con il materiale della playlist; torna su `/sets` e il set appare con il badge "a mano".

- [ ] **Step 8: Commit**

```bash
git add frontend/app/sets/page.tsx frontend/app/set-builder/page.tsx frontend/app/playlists/detail/page.tsx frontend/e2e/smoke.spec.ts frontend/tests docs/API.md docs/ARCHITECTURE.md PROGRESS.md
git commit -m "feat(sets): ingressi al set manuale, instradamento per kind, smoke e documentazione"
```

---

## Cosa NON fa questa tappa (per non farlo per sbaglio)

- Niente alternative, riserve, confronto (tappa 2). `block_id NULL` esiste nel modello ma nessun endpoint lo scrive.
- Niente sequenze multiple, banco, undo/redo (tappa 3). `SetlistBlock.placement="bench"` esiste nel modello, nessun endpoint lo crea.
- Niente note di coppia, stati "provato", `play_bpm`, percentuale di pitch (tappa 4).
- Niente durata pianificata ed export dedicati (tappa 5): gli export esistenti restano sui set generati.
- Niente "riempi il varco", nessuna rimozione del form vecchio e dell'AI (tappa 6).
- Nessuna conversione dei set generati esistenti.
