# Set manuale, tappa 2 (alternative, riserve, confronto) — piano di implementazione

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Su un punto del percorso il DJ tiene due o tre candidate, le ascolta una dopo l'altra, ne sceglie una e le altre restano lì; le tracce «da avere in tasca» per la serata vivono in una riserva accanto al percorso.

**Architecture:** Nessun modello nuovo oltre a una tabella: `SetlistAlternative` (candidata su una riga). L'attiva resta `SetlistTrack.track_id`, e sceglierne un'altra è uno scambio che conserva la precedente. Le riserve non hanno tabella: sono righe con `block_id NULL`, già previste dal modello della tappa 1. Il servizio `manual_set.py` guadagna le mutazioni corrispondenti, tutte con lo stesso contratto di revisione; il router estende gli endpoint esistenti; la pagina guadagna il confronto nel pannello di dettaglio e una lista riserve sotto il percorso.

**Tech Stack:** Python 3 + FastAPI + SQLAlchemy 2 (SQLite, migrazioni idempotenti in `db.py`), Pydantic v2, pytest. Next.js 16 App Router, React, Tailwind (design system in `docs/DESIGN.md`), vitest + @testing-library/react, Playwright.

**Spec:** `docs/superpowers/specs/2026-09-15-set-builder-workbench.md` (sezione 3 per il modello e le regole, "Tappa 2" per il perimetro).

## Global Constraints

- Backend: `cd backend && .venv/bin/python -m pytest tests -q` deve restare verde. Baseline a inizio tappa: **2520 passed, 4 deselected**. I test usano la fixture `db` di `conftest.py` (SQLite in memoria, foreign key accese) o `TestClient(app)` con `app.dependency_overrides[get_db]`. Mai il DB personale.
- Frontend baseline: **614 test in 101 file**, `npx tsc --noEmit` pulito, `npm run lint` senza errori (4 warning pre-esistenti non correlati), `npm run build` verde.
- Migrazioni: solo dentro `ensure_schema` in `backend/app/db.py`, idempotenti. La tabella nuova la crea `Base.metadata.create_all`; non serve alcun rebuild.
- Errori HTTP: sempre `api_error(status, code, message, **params)` da `app/core/http_errors.py`; ogni `code` nuovo va tradotto in `frontend/lib/i18n/en.ts` **e** `it.ts` sotto `errors`.
- I set `manual` non passano mai da `assign_roles`, `_reassign_roles`, `recompute_transitions`.
- Ogni mutazione controlla `expected_revision`, muta, incrementa `Setlist.revision`, committa e ritorna il set ricaricato. Un conflitto lascia il database intatto.
- Le righe si identificano per id, mai per posizione.
- Frontend: leggere `frontend/CLAUDE.md` (Next 16 ha API diverse dalla memoria del modello). Nessuna stringa user-facing fuori dai dizionari; chiavi in `en.ts` prima, poi `it.ts`. Spazi fra elementi inline: `{" "}` esplicito.
- Commit in italiano, stile `feat(sets): …`, nessun `Co-Authored-By`. Prima di ogni commit `git status --porcelain`, stage dei soli file del task; se `frontend/package-lock.json` o `frontend/tsconfig.json` risultano modificati, revertarli.
- Nessuna chiamata AI, nessun pacchetto nuovo.

## Cosa questa tappa NON fa

Sequenze nominate e banco (`placement='bench'`), annulla e ripeti, note di coppia e stati «provato», `play_bpm`, durata pianificata, export dedicati, «riempi il varco». Sono le tappe 3-6.

---

## Inventario dei punti d'integrazione (fatto, non da rifare)

La revisione finale della tappa 1 ha chiesto che il task sul ciclo di vita parta da un grep, non da una lista di righe scritta a mano. Il grep è stato eseguito il 2026-09-19 su `backend/app`. Ogni punto che legge le righe di un set o nomina le sue tabelle:

| Punto | File:riga | Cosa deve fare con `SetlistAlternative` |
|---|---|---|
| `orphan_lead_ids` | `repositories.py:625` | Una traccia usata come alternativa NON è orfana: va aggiunta all'esclusione |
| `unreferenced_track_ids` | `repositories.py:757` | Idem, stessa forma |
| `merge_tracks` | `repositories.py:730` | Sposta le alternative da `drop` a `keep` e deduplica (stessa riga + stessa traccia due volte è impossibile) |
| `clean_user_data.DATA_TABLES` | `tools/clean_user_data.py:24` | `setlist_alternatives` PRIMA di `setlist_tracks` (figlia) |
| `detach_track_dependencies` | `repositories.py:767` | Nessuna modifica: le alternative rendono la traccia non-orfana, come le membership, e i chiamanti cancellano solo tracce non referenziate |
| backup | `services/backup.py` | Nessuna modifica: copia l'intero file del database |

---

## File structure

| File | Responsabilità |
|---|---|
| `backend/app/models.py` | `SetlistAlternative`, relazione `SetlistTrack.alternatives` |
| `backend/app/repositories.py` | I tre punti del ciclo di vita sopra |
| `backend/app/tools/clean_user_data.py` | La tabella nuova in `DATA_TABLES` |
| `backend/app/services/manual_set.py` | `reserve_rows`, `add_alternatives`, `remove_alternative`, `choose_alternative`, `move_row` esteso alla riserva |
| `backend/app/services/manual_material.py` | Il flag `in_reserve` e il filtro `reserved` |
| `backend/app/schemas.py` | `ManualAlternativeOut`; `alternatives` su `ManualRowOut`; `reserve` su `ManualSetOut`; `in_reserve` su `MaterialItemOut`; `AlternativesAddRequest`; `reserve` su `RowsInsertRequest`; `to` su `RowMoveRequest` |
| `backend/app/serializers.py` | `manual_set_out` espone alternative e riserva |
| `backend/app/routers/sets.py` | Endpoint delle alternative e della riserva |
| `backend/tests/test_set_manual_alternatives.py` | Servizio e API delle alternative |
| `backend/tests/test_set_manual_reserve.py` | Servizio e API della riserva |
| `backend/tests/test_set_manual_lifecycle.py` | Aggiunte: i tre punti del ciclo di vita |
| `frontend/lib/api/types.ts`, `manual-sets.ts`, `frontend/lib/i18n/{en,it}.ts` | Tipi, client, testi |
| `frontend/components/set-builder/compare-panel.tsx` | Il confronto 2-4 |
| `frontend/components/set-builder/detail-panel.tsx` | Le alternative dello slot selezionato |
| `frontend/components/set-builder/reserve-panel.tsx` | La riserva |
| `frontend/app/sets/manual/page.tsx` | Stato e orchestrazione |
| `frontend/tests/set-builder-alternatives.test.tsx` | Gesti di alternative, confronto, riserva |
| `docs/API.md`, `docs/ARCHITECTURE.md`, `PROGRESS.md`, `frontend/e2e/set-builder.spec.ts` | Documentazione e verifica |

---

### Task 1: Il modello delle alternative e il ciclo di vita

**Files:**
- Modify: `backend/app/models.py` (dopo `SetlistTrack`)
- Modify: `backend/app/repositories.py:625`, `:730`, `:757`
- Modify: `backend/app/tools/clean_user_data.py:24`
- Test: `backend/tests/test_set_manual_lifecycle.py` e `backend/tests/test_clean_user_data.py` (in coda ai file esistenti)

**Interfaces:**
- Produces: `SetlistAlternative(id, setlist_track_id, track_id, position, note, row, track)`; `SetlistTrack.alternatives: list[SetlistAlternative]` (cascade all/delete-orphan, ordinata per `position`).

- [ ] **Step 1: Scrivi i test che falliscono**

In coda a `backend/tests/test_set_manual_lifecycle.py`:

```python
def _manual_with_alternative(db, active, candidate):
    """Set manuale con una riga attiva su `active` e `candidate` fra le sue alternative."""
    s = Setlist(name="M", kind="manual")
    db.add(s)
    db.flush()
    b = SetlistBlock(setlist_id=s.id, position=1)
    db.add(b)
    db.flush()
    row = SetlistTrack(setlist_id=s.id, block_id=b.id, position=1, track_id=active.id)
    db.add(row)
    db.flush()
    db.add(SetlistAlternative(setlist_track_id=row.id, track_id=candidate.id, position=1))
    db.commit()
    return s, row


def test_traccia_fra_le_alternative_non_e_orfana(db):
    attiva = Track(source_type="spotify", title="Attiva", has_local_file=True)
    candidata = Track(source_type="spotify", title="Candidata", has_local_file=False)
    db.add_all([attiva, candidata])
    db.commit()
    _manual_with_alternative(db, attiva, candidata)
    assert orphan_lead_ids(db, [candidata.id]) == []


def test_traccia_fra_le_alternative_e_referenziata(db):
    from app.repositories import unreferenced_track_ids
    attiva = Track(source_type="spotify", title="Attiva", has_local_file=True)
    candidata = Track(source_type="spotify", title="Candidata", has_local_file=True)
    db.add_all([attiva, candidata])
    db.commit()
    _manual_with_alternative(db, attiva, candidata)
    assert candidata.id not in unreferenced_track_ids(db, [candidata.id])


def test_merge_sposta_le_alternative_sulla_traccia_che_resta(db):
    from app.repositories import merge_tracks
    attiva = Track(source_type="spotify", title="Attiva", has_local_file=True)
    keep = Track(source_type="spotify", title="Keep", has_local_file=True)
    drop = Track(source_type="spotify", title="Drop", has_local_file=True)
    db.add_all([attiva, keep, drop])
    db.commit()
    s, row = _manual_with_alternative(db, attiva, drop)
    merge_tracks(db, keep, drop)
    db.refresh(row)
    assert [a.track_id for a in row.alternatives] == [keep.id]


def test_merge_non_duplica_una_alternativa_gia_presente(db):
    from app.repositories import merge_tracks
    attiva = Track(source_type="spotify", title="Attiva", has_local_file=True)
    keep = Track(source_type="spotify", title="Keep", has_local_file=True)
    drop = Track(source_type="spotify", title="Drop", has_local_file=True)
    db.add_all([attiva, keep, drop])
    db.commit()
    s, row = _manual_with_alternative(db, attiva, keep)
    db.add(SetlistAlternative(setlist_track_id=row.id, track_id=drop.id, position=2))
    db.commit()
    merge_tracks(db, keep, drop)
    db.refresh(row)
    assert [a.track_id for a in row.alternatives] == [keep.id]  # una sola, non due


```

Aggiungi `SetlistAlternative` all'import da `app.models` in cima al file; `orphan_lead_ids` è già importato.

E in coda a `backend/tests/test_clean_user_data.py`, accanto al gemello della tappa 1 (`test_pulizia_libreria_svuota_i_set_manuali_coi_blocchi`, che usa la fixture `db_su_file` e chiama davvero il tool — copia quella forma, non asserire sull'ordine della tupla):

```python
def test_pulizia_libreria_svuota_anche_le_alternative(db_su_file):
    """`setlist_alternatives` è figlia di `setlist_tracks`: se manca da
    `DATA_TABLES` la DELETE sulla madre va in IntegrityError con le foreign
    key accese."""
    t = Track(source_type="spotify", title="T", has_local_file=True)
    db_su_file.add(t)
    db_su_file.flush()
    s = Setlist(name="M", kind="manual")
    db_su_file.add(s)
    db_su_file.flush()
    b = SetlistBlock(setlist_id=s.id, position=1)
    db_su_file.add(b)
    db_su_file.flush()
    row = SetlistTrack(setlist_id=s.id, block_id=b.id, position=1, track_id=t.id)
    db_su_file.add(row)
    db_su_file.flush()
    db_su_file.add(SetlistAlternative(setlist_track_id=row.id, track_id=t.id, position=1))
    db_su_file.commit()

    report = clean_user_data.clean("library", preserve_tokens=True,
                                   include_backups=False, dry_run=False)

    assert report["after"]["setlists"] == 0
    assert db_su_file.execute(
        text("SELECT COUNT(*) FROM setlist_alternatives")).scalar_one() == 0
```

Aggiungi `SetlistAlternative` e `SetlistTrack` agli import di quel file.

- [ ] **Step 2: Esegui e verifica che falliscano**

Run: `cd backend && .venv/bin/python -m pytest tests/test_set_manual_lifecycle.py -q -p no:cacheprovider`
Expected: FAIL con `ImportError: cannot import name 'SetlistAlternative'`.

- [ ] **Step 3: Il modello**

In `backend/app/models.py`, subito dopo la classe `SetlistTrack`:

```python
class SetlistAlternative(Base):
    """Candidata su una riga del set manuale. L'attiva NON sta qui: è
    `SetlistTrack.track_id`. Scegliere una candidata è uno scambio, e la
    traccia che lascia il posto torna in questa lista (spec 2026-09-15)."""

    __tablename__ = "setlist_alternatives"

    id: Mapped[int] = mapped_column(primary_key=True)
    setlist_track_id: Mapped[int] = mapped_column(ForeignKey("setlist_tracks.id"), index=True)
    track_id: Mapped[int] = mapped_column(ForeignKey("tracks.id"), index=True)
    position: Mapped[int] = mapped_column(Integer, default=1)
    note: Mapped[str | None] = mapped_column(Text)

    row: Mapped["SetlistTrack"] = relationship(back_populates="alternatives")
    track: Mapped[Track] = relationship()
```

e dentro `SetlistTrack`, accanto alle altre relazioni:

```python
    alternatives: Mapped[list["SetlistAlternative"]] = relationship(
        back_populates="row", cascade="all, delete-orphan",
        order_by="SetlistAlternative.position",
    )
```

- [ ] **Step 4: Il ciclo di vita**

In `backend/app/repositories.py`, importa `SetlistAlternative` dal blocco `app.models` in cima.

In `orphan_lead_ids` (riga ~625), sotto l'esclusione esistente su `SetlistTrack`:

```python
        # Una candidata tenuta su una riga è una decisione del DJ, non un residuo:
        # conta come riferimento esattamente come una membership.
        Track.id.not_in(select(SetlistAlternative.track_id)),
```

La stessa riga in `unreferenced_track_ids` (riga ~757). `SetlistAlternative.track_id` è NOT NULL, quindi qui la guardia `is_not(None)` non serve — ed è proprio perché la colonna è NOT NULL che non serve, non per distrazione.

In `merge_tracks`, accanto all'`update(SetlistTrack)` esistente (riga ~730):

```python
    # Alternative: sposta quelle di `drop` su `keep`, ma solo dove `keep` non è
    # già candidata sulla stessa riga — altrimenti la riga si ritroverebbe la
    # stessa traccia due volte fra le candidate.
    righe_con_keep = select(SetlistAlternative.setlist_track_id).where(
        SetlistAlternative.track_id == keep.id
    )
    db.execute(
        delete(SetlistAlternative).where(
            SetlistAlternative.track_id == drop.id,
            SetlistAlternative.setlist_track_id.in_(righe_con_keep),
        )
    )
    db.execute(
        update(SetlistAlternative).where(SetlistAlternative.track_id == drop.id)
        .values(track_id=keep.id)
    )
```

In `backend/app/tools/clean_user_data.py`, `DATA_TABLES` diventa:

```python
DATA_TABLES = ("setlist_alternatives", "setlist_tracks", "setlist_blocks", "setlists", "download_queue_items",
```

(il resto della tupla invariato; l'ordine è figlia prima della madre, come `setlist_tracks` prima di `setlists`).

- [ ] **Step 5: Esegui e verifica che passino**

Run: `cd backend && .venv/bin/python -m pytest tests/test_set_manual_lifecycle.py tests/test_clean_user_data.py -q -p no:cacheprovider`
Expected: tutti verdi.

- [ ] **Step 6: Suite completa**

Run: `cd backend && .venv/bin/python -m pytest tests -q -p no:cacheprovider`
Expected: 2525 passed, 4 deselected.

- [ ] **Step 7: Commit**

```bash
git add backend/app/models.py backend/app/repositories.py backend/app/tools/clean_user_data.py backend/tests/test_set_manual_lifecycle.py backend/tests/test_clean_user_data.py
git commit -m "feat(sets): le alternative del set manuale, e il ciclo di vita che le conosce"
```

---

### Task 2: Il servizio — alternative e riserve

**Files:**
- Modify: `backend/app/services/manual_set.py`
- Test: `backend/tests/test_set_manual_alternatives.py` (nuovo), `backend/tests/test_set_manual_reserve.py` (nuovo)

**Interfaces:**
- Consumes: Task 1; le funzioni già presenti `load_manual_set`, `_check_revision`, `_row_of`, `_commit_bumped`, `_renumber`, `main_block`, `path_rows`, e le eccezioni `ManualSetError`, `RowNotFound`, `RevisionConflict`.
- Produces:

```python
class AlternativeNotFound(ManualSetError): ...   # 404

def reserve_rows(setlist: Setlist) -> list[SetlistTrack]
    """Le righe della riserva (block_id NULL) in ordine di position."""

def insert_rows(db, setlist_id, *, expected_revision, track_ids, gap,
                after_row_id, reserve: bool = False) -> Setlist
    """reserve=True inserisce in coda alla riserva; un varco in riserva non
    ha senso e viene rifiutato."""

def move_row(db, setlist_id, row_id, *, expected_revision, position,
             to_reserve: bool | None = None) -> Setlist
    """to_reserve=None sposta dentro la destinazione corrente; True porta la
    riga in riserva, False la riporta nel percorso."""

def add_alternatives(db, setlist_id, row_id, *, expected_revision,
                     track_ids: list[int]) -> Setlist
def remove_alternative(db, setlist_id, row_id, alt_id, *, expected_revision) -> Setlist
def choose_alternative(db, setlist_id, row_id, alt_id, *, expected_revision) -> Setlist
    """La candidata diventa attiva; la traccia che lascia il posto prende il
    suo posto fra le alternative. Su un varco non c'è traccia da conservare:
    lo slot diventa `track` mantenendo id e nota."""
```

- [ ] **Step 1: Scrivi i test delle alternative**

`backend/tests/test_set_manual_alternatives.py`:

```python
"""Alternative del set manuale (tappa 2): aggiunta, scelta con scambio,
rimozione, varco che diventa traccia. DB in memoria, nessuna rete."""
import pytest

from app.models import Track
from app.services.manual_set import (
    AlternativeNotFound,
    ManualSetError,
    RevisionConflict,
    add_alternatives,
    choose_alternative,
    create_manual_set,
    insert_rows,
    path_rows,
    remove_alternative,
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


def _set_con_una_riga(db, track):
    s = create_manual_set(db, name="M", playlist_id=None)
    s = insert_rows(db, s.id, expected_revision=0, track_ids=[track.id], gap=False, after_row_id=None)
    return s, path_rows(s)[0]


def test_aggiungi_alternative_in_ordine(db):
    t = _tracks(db, 3)
    s, row = _set_con_una_riga(db, t[0])
    s = add_alternatives(db, s.id, row.id, expected_revision=1, track_ids=[t[1].id, t[2].id])
    alts = path_rows(s)[0].alternatives
    assert [a.track_id for a in alts] == [t[1].id, t[2].id]
    assert [a.position for a in alts] == [1, 2]
    assert s.revision == 2


def test_la_traccia_attiva_non_puo_essere_anche_sua_alternativa(db):
    t = _tracks(db, 2)
    s, row = _set_con_una_riga(db, t[0])
    with pytest.raises(ManualSetError):
        add_alternatives(db, s.id, row.id, expected_revision=1, track_ids=[t[0].id])


def test_la_stessa_candidata_non_si_aggiunge_due_volte(db):
    t = _tracks(db, 2)
    s, row = _set_con_una_riga(db, t[0])
    s = add_alternatives(db, s.id, row.id, expected_revision=1, track_ids=[t[1].id])
    with pytest.raises(ManualSetError):
        add_alternatives(db, s.id, row.id, expected_revision=2, track_ids=[t[1].id])


def test_scegliere_scambia_e_conserva_la_precedente(db):
    t = _tracks(db, 3)
    s, row = _set_con_una_riga(db, t[0])
    s = add_alternatives(db, s.id, row.id, expected_revision=1, track_ids=[t[1].id, t[2].id])
    alt = path_rows(s)[0].alternatives[0]
    s = choose_alternative(db, s.id, row.id, alt.id, expected_revision=2)
    riga = path_rows(s)[0]
    assert riga.track_id == t[1].id                       # la candidata è attiva
    # Anche l'oggetto collegato: è `row.track` che il serializer legge, e la
    # sola chiave lo lascerebbe sulla traccia uscente (test verde per il
    # motivo sbagliato, verificato il 2026-09-19).
    assert riga.track is not None and riga.track.id == t[1].id
    assert t[0].id in [a.track_id for a in riga.alternatives]  # la precedente è conservata
    assert t[2].id in [a.track_id for a in riga.alternatives]  # l'altra resta
    assert len(riga.alternatives) == 2
    assert [a.position for a in riga.alternatives] == [1, 2]


def test_scegliere_su_un_varco_lo_trasforma_in_traccia(db):
    t = _tracks(db, 2)
    s, row = _set_con_una_riga(db, t[0])
    s = insert_rows(db, s.id, expected_revision=1, track_ids=[], gap=True, after_row_id=row.id)
    varco = path_rows(s)[1]
    assert varco.slot_kind == "gap"
    s = add_alternatives(db, s.id, varco.id, expected_revision=2, track_ids=[t[1].id])
    alt = path_rows(s)[1].alternatives[0]
    s = choose_alternative(db, s.id, varco.id, alt.id, expected_revision=3)
    riga = path_rows(s)[1]
    assert riga.id == varco.id and riga.slot_kind == "track" and riga.track_id == t[1].id
    assert riga.alternatives == []  # non c'era traccia da conservare


def test_rimuovi_una_alternativa_rinumera(db):
    t = _tracks(db, 4)
    s, row = _set_con_una_riga(db, t[0])
    s = add_alternatives(db, s.id, row.id, expected_revision=1,
                         track_ids=[t[1].id, t[2].id, t[3].id])
    alt = path_rows(s)[0].alternatives[1]
    s = remove_alternative(db, s.id, row.id, alt.id, expected_revision=2)
    alts = path_rows(s)[0].alternatives
    assert [a.track_id for a in alts] == [t[1].id, t[3].id]
    assert [a.position for a in alts] == [1, 2]


def test_alternativa_di_un_altra_riga_non_si_tocca(db):
    t = _tracks(db, 3)
    s, row = _set_con_una_riga(db, t[0])
    s = insert_rows(db, s.id, expected_revision=1, track_ids=[t[1].id], gap=False, after_row_id=None)
    prima, seconda = path_rows(s)
    s = add_alternatives(db, s.id, prima.id, expected_revision=2, track_ids=[t[2].id])
    alt = path_rows(s)[0].alternatives[0]
    with pytest.raises(AlternativeNotFound):
        remove_alternative(db, s.id, seconda.id, alt.id, expected_revision=3)


def test_traccia_inesistente_fra_le_candidate(db):
    t = _tracks(db, 1)
    s, row = _set_con_una_riga(db, t[0])
    with pytest.raises(ManualSetError):
        add_alternatives(db, s.id, row.id, expected_revision=1, track_ids=[999])


def test_conflitto_di_revisione_sulle_alternative(db):
    t = _tracks(db, 2)
    s, row = _set_con_una_riga(db, t[0])
    with pytest.raises(RevisionConflict):
        add_alternatives(db, s.id, row.id, expected_revision=0, track_ids=[t[1].id])
    assert path_rows(s)[0].alternatives == []
```

- [ ] **Step 2: Scrivi i test della riserva**

`backend/tests/test_set_manual_reserve.py`:

```python
"""Riserva del set manuale (tappa 2): righe con block_id NULL, spostamenti
fra riserva e percorso. DB in memoria, nessuna rete."""
import pytest

from app.models import Track
from app.services.manual_set import (
    ManualSetError,
    create_manual_set,
    insert_rows,
    move_row,
    path_rows,
    remove_row,
    reserve_rows,
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


def test_inserisci_in_riserva(db):
    t = _tracks(db, 2)
    s = create_manual_set(db, name="M", playlist_id=None)
    s = insert_rows(db, s.id, expected_revision=0, track_ids=[t[0].id, t[1].id],
                    gap=False, after_row_id=None, reserve=True)
    assert path_rows(s) == []
    ris = reserve_rows(s)
    assert [r.track_id for r in ris] == [t[0].id, t[1].id]
    assert [r.position for r in ris] == [1, 2]
    assert all(r.block_id is None for r in ris)


def test_un_varco_in_riserva_non_ha_senso(db):
    s = create_manual_set(db, name="M", playlist_id=None)
    with pytest.raises(ManualSetError):
        insert_rows(db, s.id, expected_revision=0, track_ids=[], gap=True,
                    after_row_id=None, reserve=True)


def test_la_stessa_traccia_puo_stare_in_riserva_e_nel_percorso(db):
    """Spec: il vincolo di unicità vale dentro il percorso, non fra percorso e riserva."""
    t = _tracks(db, 1)
    s = create_manual_set(db, name="M", playlist_id=None)
    s = insert_rows(db, s.id, expected_revision=0, track_ids=[t[0].id], gap=False, after_row_id=None)
    s = insert_rows(db, s.id, expected_revision=1, track_ids=[t[0].id], gap=False,
                    after_row_id=None, reserve=True)
    assert [r.track_id for r in path_rows(s)] == [t[0].id]
    assert [r.track_id for r in reserve_rows(s)] == [t[0].id]


def test_porta_una_riga_dal_percorso_alla_riserva(db):
    t = _tracks(db, 3)
    s = create_manual_set(db, name="M", playlist_id=None)
    s = insert_rows(db, s.id, expected_revision=0, track_ids=[x.id for x in t],
                    gap=False, after_row_id=None)
    seconda = path_rows(s)[1]
    s = move_row(db, s.id, seconda.id, expected_revision=1, position=1, to_reserve=True)
    assert [r.track_id for r in path_rows(s)] == [t[0].id, t[2].id]
    assert [r.position for r in path_rows(s)] == [1, 2]      # il percorso si rinumera
    assert [r.track_id for r in reserve_rows(s)] == [t[1].id]


def test_riporta_una_riga_dalla_riserva_al_percorso(db):
    t = _tracks(db, 2)
    s = create_manual_set(db, name="M", playlist_id=None)
    s = insert_rows(db, s.id, expected_revision=0, track_ids=[t[0].id], gap=False, after_row_id=None)
    s = insert_rows(db, s.id, expected_revision=1, track_ids=[t[1].id], gap=False,
                    after_row_id=None, reserve=True)
    in_riserva = reserve_rows(s)[0]
    s = move_row(db, s.id, in_riserva.id, expected_revision=2, position=1, to_reserve=False)
    assert [r.track_id for r in path_rows(s)] == [t[1].id, t[0].id]
    assert reserve_rows(s) == []


def test_riportare_nel_percorso_una_traccia_gia_presente_e_un_conflitto(db):
    t = _tracks(db, 1)
    s = create_manual_set(db, name="M", playlist_id=None)
    s = insert_rows(db, s.id, expected_revision=0, track_ids=[t[0].id], gap=False, after_row_id=None)
    s = insert_rows(db, s.id, expected_revision=1, track_ids=[t[0].id], gap=False,
                    after_row_id=None, reserve=True)
    in_riserva = reserve_rows(s)[0]
    with pytest.raises(ManualSetError):
        move_row(db, s.id, in_riserva.id, expected_revision=2, position=1, to_reserve=False)


def test_togliere_una_riga_di_riserva_rinumera_la_riserva(db):
    t = _tracks(db, 3)
    s = create_manual_set(db, name="M", playlist_id=None)
    s = insert_rows(db, s.id, expected_revision=0, track_ids=[x.id for x in t],
                    gap=False, after_row_id=None, reserve=True)
    s = remove_row(db, s.id, reserve_rows(s)[0].id, expected_revision=1)
    ris = reserve_rows(s)
    assert [r.track_id for r in ris] == [t[1].id, t[2].id]
    assert [r.position for r in ris] == [1, 2]
```

- [ ] **Step 3: Esegui e verifica che falliscano**

Run: `cd backend && .venv/bin/python -m pytest tests/test_set_manual_alternatives.py tests/test_set_manual_reserve.py -q -p no:cacheprovider`
Expected: FAIL con `ImportError` su `add_alternatives` e `reserve_rows`.

- [ ] **Step 4: Implementa il servizio**

In `backend/app/services/manual_set.py`. Importa `SetlistAlternative` dal blocco `app.models`. Aggiungi l'eccezione accanto alle altre:

```python
class AlternativeNotFound(ManualSetError):
    pass
```

Accanto a `path_rows`:

```python
def reserve_rows(setlist: Setlist) -> list[SetlistTrack]:
    """Le tracce messe da parte per la serata: righe senza blocco, in ordine."""
    return sorted((r for r in setlist.tracks if r.block_id is None),
                  key=lambda r: r.position)
```

Sostituisci `insert_rows` con questa versione (la firma guadagna `reserve`):

```python
def insert_rows(db: Session, setlist_id: int, *, expected_revision: int,
                track_ids: list[int], gap: bool, after_row_id: int | None,
                reserve: bool = False) -> Setlist:
    """Inserisce tracce (nell'ordine dato) oppure un varco. `reserve=True` le
    mette in coda alla riserva invece che nel percorso; il vincolo «una traccia
    una volta sola» vale dentro il percorso, non fra percorso e riserva."""
    if gap == bool(track_ids):
        raise ManualSetError("Give either track_ids or gap")
    if gap and reserve:
        raise ManualSetError("A gap belongs to the path, not to the reserve")
    setlist = load_manual_set(db, setlist_id)
    _check_revision(setlist, expected_revision)
    if reserve:
        rows = reserve_rows(setlist)
        at = len(rows)
        block_id = None
        present: set[int] = set()  # in riserva una traccia può ripetersi dal percorso
    else:
        block = main_block(db, setlist)
        rows = [r for r in path_rows(setlist) if r.block_id == block.id]
        at = len(rows)
        if after_row_id is not None:
            anchor = _row_of(setlist, after_row_id)
            if anchor not in rows:
                raise ManualSetError(f"Row {after_row_id} is not in the main block")
            at = rows.index(anchor) + 1
        block_id = block.id
        present = {r.track_id for r in rows if r.track_id is not None}
    new_rows: list[SetlistTrack] = []
    if gap:
        new_rows.append(SetlistTrack(setlist_id=setlist.id, block_id=block_id,
                                     position=0, slot_kind="gap"))
    else:
        for tid in track_ids:
            if get_track(db, tid) is None:
                raise ManualSetError(f"Track {tid} not found")
            if tid in present:
                raise ManualSetError(f"Track {tid} is already in the path")
            present.add(tid)
            new_rows.append(SetlistTrack(setlist_id=setlist.id, block_id=block_id, position=0,
                                         slot_kind="track", track_id=tid))
    rows[at:at] = new_rows
    for row in new_rows:
        db.add(row)
        setlist.tracks.append(row)
    _renumber(rows)
    return _commit_bumped(db, setlist)
```

Sostituisci `move_row` con questa versione:

```python
def move_row(db: Session, setlist_id: int, row_id: int, *, expected_revision: int,
             position: int, to_reserve: bool | None = None) -> Setlist:
    """Sposta la riga alla posizione 1-based. `to_reserve` la cambia di
    destinazione: True la porta in riserva, False la riporta nel percorso,
    None la lascia dov'è."""
    setlist = load_manual_set(db, setlist_id)
    _check_revision(setlist, expected_revision)
    row = _row_of(setlist, row_id)
    era_in_riserva = row.block_id is None
    va_in_riserva = era_in_riserva if to_reserve is None else to_reserve
    if va_in_riserva and row.slot_kind == "gap":
        raise ManualSetError("A gap belongs to the path, not to the reserve")

    origine = reserve_rows(setlist) if era_in_riserva else [
        r for r in path_rows(setlist) if r.block_id == row.block_id
    ]
    if va_in_riserva == era_in_riserva:
        destinazione = origine
    else:
        origine = [r for r in origine if r.id != row.id]
        if va_in_riserva:
            destinazione = reserve_rows(setlist)
            row.block_id = None
        else:
            block = main_block(db, setlist)
            presenti = {r.track_id for r in path_rows(setlist)
                        if r.block_id == block.id and r.track_id is not None}
            if row.track_id in presenti:
                raise ManualSetError(f"Track {row.track_id} is already in the path")
            destinazione = [r for r in path_rows(setlist) if r.block_id == block.id]
            row.block_id = block.id
        _renumber(origine)
        destinazione = [r for r in destinazione if r.id != row.id]

    if not 1 <= position <= len(destinazione) + (0 if row in destinazione else 1):
        raise ManualSetError(f"Position {position} out of range")
    if row in destinazione:
        destinazione.remove(row)
    destinazione.insert(position - 1, row)
    _renumber(destinazione)
    return _commit_bumped(db, setlist)
```

`remove_row` va reso consapevole della riserva: sostituisci la riga che calcola `rows` con

```python
    rows = (reserve_rows(setlist) if row.block_id is None
            else [r for r in path_rows(setlist) if r.block_id == row.block_id])
    rows = [r for r in rows if r.id != row.id]
```

Infine, in fondo al file, le tre funzioni delle alternative:

```python
def _alt_of(row: SetlistTrack, alt_id: int) -> SetlistAlternative:
    for alt in row.alternatives:
        if alt.id == alt_id:
            return alt
    raise AlternativeNotFound("Alternative not found")


def _renumber_alts(alts: list[SetlistAlternative]) -> None:
    for i, alt in enumerate(alts, start=1):
        alt.position = i


def add_alternatives(db: Session, setlist_id: int, row_id: int, *, expected_revision: int,
                     track_ids: list[int]) -> Setlist:
    """Candidate in coda alla riga. La traccia attiva non può essere candidata
    di sé stessa, e la stessa candidata non si ripete sulla stessa riga."""
    setlist = load_manual_set(db, setlist_id)
    _check_revision(setlist, expected_revision)
    row = _row_of(setlist, row_id)
    presenti = {a.track_id for a in row.alternatives}
    alts = list(row.alternatives)
    for tid in track_ids:
        if get_track(db, tid) is None:
            raise ManualSetError(f"Track {tid} not found")
        if tid == row.track_id:
            raise ManualSetError(f"Track {tid} is already the active one on this row")
        if tid in presenti:
            raise ManualSetError(f"Track {tid} is already an alternative on this row")
        presenti.add(tid)
        alt = SetlistAlternative(setlist_track_id=row.id, track_id=tid, position=0)
        db.add(alt)
        row.alternatives.append(alt)
        alts.append(alt)
    _renumber_alts(alts)
    return _commit_bumped(db, setlist)


def remove_alternative(db: Session, setlist_id: int, row_id: int, alt_id: int, *,
                       expected_revision: int) -> Setlist:
    setlist = load_manual_set(db, setlist_id)
    _check_revision(setlist, expected_revision)
    row = _row_of(setlist, row_id)
    alt = _alt_of(row, alt_id)
    row.alternatives.remove(alt)  # delete-orphan: la candidata sparisce
    _renumber_alts(list(row.alternatives))
    return _commit_bumped(db, setlist)


def choose_alternative(db: Session, setlist_id: int, row_id: int, alt_id: int, *,
                       expected_revision: int) -> Setlist:
    """La candidata prende il posto dell'attiva, e l'attiva prende il suo posto
    fra le candidate. Su un varco non c'è nulla da conservare: lo slot diventa
    `track` mantenendo id e appunto (spec, sezione 3)."""
    setlist = load_manual_set(db, setlist_id)
    _check_revision(setlist, expected_revision)
    row = _row_of(setlist, row_id)
    alt = _alt_of(row, alt_id)
    uscente = row.track_id
    # La relationship va assegnata insieme alla foreign key: `row.track` è già
    # caricata, e il serializer legge quella — con la sola chiave la risposta
    # mostrerebbe ancora la traccia uscente. Stesso accorgimento di
    # set_editor.add_track.
    row.track_id = alt.track_id
    row.track = alt.track
    row.slot_kind = "track"
    row.alternatives.remove(alt)
    if uscente is not None:
        row.alternatives.append(
            SetlistAlternative(setlist_track_id=row.id, track_id=uscente, position=0)
        )
    _renumber_alts(list(row.alternatives))
    return _commit_bumped(db, setlist)
```

- [ ] **Step 5: Esegui i test mirati**

Run: `cd backend && .venv/bin/python -m pytest tests/test_set_manual_alternatives.py tests/test_set_manual_reserve.py tests/test_set_manual_service.py -q -p no:cacheprovider`
Expected: tutti verdi. `test_set_manual_service.py` (tappa 1) deve restare verde senza modifiche: `insert_rows` e `move_row` hanno guadagnato parametri con default, non cambiato comportamento.

- [ ] **Step 6: Suite completa e commit**

Run: `cd backend && .venv/bin/python -m pytest tests -q -p no:cacheprovider` → verde.

```bash
git add backend/app/services/manual_set.py backend/tests/test_set_manual_alternatives.py backend/tests/test_set_manual_reserve.py
git commit -m "feat(sets): servizio delle alternative e della riserva"
```

---

### Task 3: Schemi, serializer, endpoint e materiale

**Files:**
- Modify: `backend/app/schemas.py` (blocco manual, righe ~239-310)
- Modify: `backend/app/serializers.py` (`manual_set_out`)
- Modify: `backend/app/routers/sets.py`
- Modify: `backend/app/services/manual_material.py`
- Test: `backend/tests/test_set_manual_api.py` (in coda)

**Interfaces:**
- Consumes: Task 2 (`reserve_rows`, `add_alternatives`, `remove_alternative`, `choose_alternative`, `AlternativeNotFound`, e i parametri nuovi di `insert_rows`/`move_row`).
- Produces (HTTP):
  - `POST /api/sets/{id}/rows` accetta `reserve: bool = false`
  - `POST /api/sets/{id}/rows/{row_id}/move` accetta `to_reserve: bool | null = null`
  - `POST /api/sets/{id}/rows/{row_id}/alternatives` body `{expected_revision, track_ids}`
  - `DELETE /api/sets/{id}/rows/{row_id}/alternatives/{alt_id}?expected_revision=N`
  - `POST /api/sets/{id}/rows/{row_id}/alternatives/{alt_id}/choose` body `{expected_revision}`
  - `GET /api/sets/{id}/material?reserved=true` filtra le tracce in riserva
  - `ManualSetOut.reserve: list[ManualRowOut]`; `ManualRowOut.alternatives: list[ManualAlternativeOut]`; `MaterialItemOut.in_reserve: bool`
  - Codice errore nuovo: `set_alternative_not_found` (404)

**Nota sul nome:** esiste già `POST /api/sets/{id}/alternatives` — sono le alternative *calcolate* dal vecchio generatore (F9), riservate ai set generati da `_require_generated`. Le nuove stanno sotto `/rows/{row_id}/alternatives` e non collidono. Non toccare l'endpoint vecchio.

- [ ] **Step 1: Scrivi i test**

In coda a `backend/tests/test_set_manual_api.py`:

```python
def test_alternative_via_http(client_db):
    client, db = client_db
    _, t = _seed(db, n=4)
    sid = client.post("/api/sets/manual", json={"name": "M"}).json()["id"]
    doc = client.post(f"/api/sets/{sid}/rows", json={"expected_revision": 0, "track_ids": [t[0].id]}).json()
    row = _rows(doc)[0]

    r = client.post(f"/api/sets/{sid}/rows/{row['id']}/alternatives",
                    json={"expected_revision": 1, "track_ids": [t[1].id, t[2].id]})
    assert r.status_code == 200, r.text
    doc = r.json()
    alts = _rows(doc)[0]["alternatives"]
    assert [a["track"]["id"] for a in alts] == [t[1].id, t[2].id]
    assert doc["revision"] == 2

    r = client.post(f"/api/sets/{sid}/rows/{row['id']}/alternatives/{alts[0]['id']}/choose",
                    json={"expected_revision": 2})
    riga = _rows(r.json())[0]
    assert riga["track"]["id"] == t[1].id
    assert t[0].id in [a["track"]["id"] for a in riga["alternatives"]]

    alt_id = riga["alternatives"][0]["id"]
    r = client.delete(f"/api/sets/{sid}/rows/{row['id']}/alternatives/{alt_id}",
                      params={"expected_revision": 3})
    assert r.status_code == 200
    assert alt_id not in [a["id"] for a in _rows(r.json())[0]["alternatives"]]

    r = client.delete(f"/api/sets/{sid}/rows/{row['id']}/alternatives/999999",
                      params={"expected_revision": 4})
    assert r.status_code == 404 and r.json()["detail"]["code"] == "set_alternative_not_found"


def test_riserva_via_http(client_db):
    client, db = client_db
    _, t = _seed(db, n=3)
    sid = client.post("/api/sets/manual", json={"name": "M"}).json()["id"]
    r = client.post(f"/api/sets/{sid}/rows",
                    json={"expected_revision": 0, "track_ids": [t[0].id], "reserve": True})
    doc = r.json()
    assert _rows(doc) == []
    assert [x["track"]["id"] for x in doc["reserve"]] == [t[0].id]
    assert doc["track_count"] == 0  # la riserva non è il set

    riga = doc["reserve"][0]
    r = client.post(f"/api/sets/{sid}/rows/{riga['id']}/move",
                    json={"expected_revision": 1, "position": 1, "to_reserve": False})
    doc = r.json()
    assert [x["track"]["id"] for x in _rows(doc)] == [t[0].id]
    assert doc["reserve"] == [] and doc["track_count"] == 1


def test_materiale_distingue_percorso_e_riserva(client_db):
    client, db = client_db
    pl, t = _seed(db, n=3)
    sid = client.post("/api/sets/manual", json={"playlist_id": pl.id}).json()["id"]
    client.post(f"/api/sets/{sid}/rows", json={"expected_revision": 0, "track_ids": [t[0].id]})
    client.post(f"/api/sets/{sid}/rows",
                json={"expected_revision": 1, "track_ids": [t[1].id], "reserve": True})

    items = client.get(f"/api/sets/{sid}/material").json()["items"]
    by_id = {it["track"]["id"]: it for it in items}
    assert by_id[t[0].id]["in_set"] is True and by_id[t[0].id]["in_reserve"] is False
    assert by_id[t[1].id]["in_set"] is False and by_id[t[1].id]["in_reserve"] is True

    solo_riserva = client.get(f"/api/sets/{sid}/material", params={"reserved": "true"}).json()["items"]
    assert [it["track"]["id"] for it in solo_riserva] == [t[1].id]
```

`_seed` della tappa 1 accetta già `n`; se nel file corrente la firma è `_seed(db, n=3)`, lasciala com'è e chiama `_seed(db, n=4)` dove serve.

- [ ] **Step 2: Esegui e verifica che falliscano**

Run: `cd backend && .venv/bin/python -m pytest tests/test_set_manual_api.py -q -p no:cacheprovider`
Expected: FAIL (404/422 sugli endpoint mancanti, `KeyError: 'reserve'`).

- [ ] **Step 3: Schemi**

In `backend/app/schemas.py`, nel blocco del set manuale:

```python
class ManualAlternativeOut(BaseModel):
    id: int
    position: int
    track: TrackOut
    note: str | None = None
```

`ManualRowOut` guadagna, dopo `note`:

```python
    alternatives: list[ManualAlternativeOut] = []
```

`ManualSetOut` guadagna, dopo `blocks`:

```python
    reserve: list[ManualRowOut] = []  # righe senza blocco: le tracce tenute in tasca
```

`RowsInsertRequest` guadagna, dopo `after_row_id`:

```python
    reserve: bool = False  # in coda alla riserva invece che nel percorso
```

e il suo validator diventa:

```python
    @model_validator(mode="after")
    def _exactly_one(self) -> "RowsInsertRequest":
        if self.gap == bool(self.track_ids):
            raise ValueError("Give either track_ids or gap")
        if self.gap and self.reserve:
            raise ValueError("A gap belongs to the path, not to the reserve")
        return self
```

`RowMoveRequest` guadagna:

```python
    to_reserve: bool | None = None  # None = resta dov'è
```

`MaterialItemOut` guadagna, dopo `in_set`:

```python
    in_reserve: bool
```

e nasce la richiesta delle alternative:

```python
class AlternativesAddRequest(BaseModel):
    expected_revision: int = Field(ge=0)
    track_ids: list[int] = Field(min_length=1, max_length=20)


class AlternativeChooseRequest(BaseModel):
    expected_revision: int = Field(ge=0)
```

- [ ] **Step 4: Serializer**

In `backend/app/serializers.py` importa `ManualAlternativeOut` da `app.schemas`. NON importare `reserve_rows` dal servizio: il serializer non deve dipendere da `services.manual_set`, e la riserva è una riga senza blocco, un fatto del modello. Dentro `manual_set_out`, la costruzione delle righe diventa una funzione locale riusata da blocchi e riserva:

```python
def manual_set_out(setlist: Setlist, db: Session) -> ManualSetOut:
    """Documento del set manuale: blocchi in ordine, righe in ordine, riserva,
    candidate per riga, tag effettivi dei file come nel resto dell'app."""
    track_ids = [st.track_id for st in setlist.tracks if st.track_id is not None]
    track_ids += [a.track_id for st in setlist.tracks for a in st.alternatives]
    ft_map = file_tags_for_tracks(db, track_ids)

    def row_out(st) -> ManualRowOut:
        return ManualRowOut(
            id=st.id, block_id=st.block_id, position=st.position, slot_kind=st.slot_kind,
            track=track_out(st.track, ft_map.get(st.track_id)) if st.track is not None else None,
            note=st.note,
            alternatives=[ManualAlternativeOut(
                id=a.id, position=a.position, note=a.note,
                track=track_out(a.track, ft_map.get(a.track_id)),
            ) for a in sorted(st.alternatives, key=lambda a: a.position)],
        )

    blocks = []
    for block in sorted(setlist.blocks, key=lambda b: b.position):
        rows = sorted((st for st in setlist.tracks if st.block_id == block.id),
                      key=lambda st: st.position)
        blocks.append(ManualBlockOut(
            id=block.id, name=block.name, placement=block.placement, position=block.position,
            rows=[row_out(st) for st in rows],
        ))
    # Il conteggio e la durata restano quelli del PERCORSO: la riserva non è il set.
    with_track = [st for st in setlist.tracks
                  if st.track is not None and st.block_id is not None]
    playlist = get_playlist(db, setlist.source_playlist_id) if setlist.source_playlist_id else None
    return ManualSetOut(
        id=setlist.id, name=setlist.name, kind=setlist.kind, revision=setlist.revision,
        source_playlist_id=setlist.source_playlist_id,
        source_playlist_name=playlist.name if playlist is not None else None,
        notes=setlist.notes, blocks=blocks,
        reserve=[row_out(st) for st in sorted(
            (st for st in setlist.tracks if st.block_id is None), key=lambda st: st.position)],
        track_count=len(with_track),
        total_file_seconds=sum(st.track.duration_seconds or 0 for st in with_track),
        created_at=_naive(setlist.created_at), updated_at=_naive(setlist.updated_at),
    )
```

**Attenzione:** `with_track` ora esclude le righe di riserva (`st.block_id is not None`). Senza quel filtro il conteggio del set gonfierebbe con le tracce tenute in tasca, e un test della tappa 1 (`test_riepilogo_conta_solo_le_tracce_e_porta_il_kind`) non lo coprirebbe perché non usa la riserva.

- [ ] **Step 5: Materiale**

In `backend/app/services/manual_material.py`, `material_for` distingue percorso e riserva:

```python
def material_for(db: Session, setlist: Setlist, *, q: str | None, owned: bool, unused: bool,
                 reserved: bool = False,
                 ) -> list[tuple[Track, bool, bool, bool]]:
    """Ritorna (track, in_set, from_playlist, in_reserve) in ordine: playlist,
    poi tracce del set fuori playlist, poi risultati di ricerca."""
    in_set = {st.track_id for st in setlist.tracks
              if st.track_id is not None and st.block_id is not None}
    in_reserve = {st.track_id for st in setlist.tracks
                  if st.track_id is not None and st.block_id is None}
    items: list[tuple[Track, bool, bool, bool]] = []
    seen: set[int] = set()

    def push(track: Track, from_playlist: bool) -> None:
        if track.id in seen:
            return
        seen.add(track.id)
        items.append((track, track.id in in_set, from_playlist, track.id in in_reserve))
    ...
```

Il resto del corpo resta identico, salvo i filtri finali, dove `it[1]` è `in_set` e `it[3]` è `in_reserve`:

```python
    if owned:
        items = [it for it in items if it[0].has_local_file]
    if unused:
        items = [it for it in items if not it[1]]
    if reserved:
        items = [it for it in items if it[3]]
    return items
```

- [ ] **Step 6: Endpoint**

In `backend/app/routers/sets.py`: aggiungi `AlternativeNotFound`, `add_alternatives`, `remove_alternative`, `choose_alternative` all'import da `app.services.manual_set`, e `AlternativesAddRequest`, `AlternativeChooseRequest` a quello da `app.schemas`.

In `_manual_error`, prima del `RowNotFound`:

```python
    if isinstance(exc, AlternativeNotFound):
        return api_error(404, "set_alternative_not_found", "Alternative not found")
```

`rows_insert` passa il campo nuovo:

```python
        return manual_set_out(insert_rows(
            db, setlist_id, expected_revision=req.expected_revision,
            track_ids=req.track_ids, gap=req.gap, after_row_id=req.after_row_id,
            reserve=req.reserve), db)
```

`rows_move` idem con `to_reserve=req.to_reserve`.

`get_material` guadagna il parametro e il campo:

```python
@router.get("/{setlist_id}/material", response_model=MaterialOut)
def get_material(setlist_id: int, q: str | None = Query(default=None, max_length=200),
                 owned: bool = False, unused: bool = False, reserved: bool = False,
                 db: Session = Depends(get_db)):
    """Playlist di origine aggiornata + tracce nel set + (con q) ricerca in libreria."""
    try:
        setlist = load_manual_set(db, setlist_id)
    except ManualSetError as exc:
        raise _manual_error(exc) from exc
    items = material_for(db, setlist, q=q, owned=owned, unused=unused, reserved=reserved)
    ft_map = file_tags_for_tracks(db, [t.id for t, _, _, _ in items])
    playlist = get_playlist(db, setlist.source_playlist_id) if setlist.source_playlist_id else None
    return MaterialOut(
        playlist_id=setlist.source_playlist_id,
        playlist_name=playlist.name if playlist is not None else None,
        items=[MaterialItemOut(track=track_out(t, ft_map.get(t.id)), in_set=in_set,
                               from_playlist=fp, in_reserve=in_res)
               for t, in_set, fp, in_res in items],
    )
```

E in coda ai `rows_*`, i tre endpoint nuovi:

```python
@router.post("/{setlist_id}/rows/{row_id}/alternatives", response_model=ManualSetOut)
def alternatives_add(setlist_id: int, row_id: int, req: AlternativesAddRequest,
                     db: Session = Depends(get_db)):
    """Candidate su una riga: quelle che il DJ tiene lì accanto, non quelle
    calcolate dal generatore (vedi POST /{id}/alternatives, per i set generati)."""
    try:
        return manual_set_out(add_alternatives(
            db, setlist_id, row_id, expected_revision=req.expected_revision,
            track_ids=req.track_ids), db)
    except ManualSetError as exc:
        raise _manual_error(exc) from exc


@router.delete("/{setlist_id}/rows/{row_id}/alternatives/{alt_id}", response_model=ManualSetOut)
def alternatives_remove(setlist_id: int, row_id: int, alt_id: int,
                        expected_revision: int = Query(ge=0), db: Session = Depends(get_db)):
    try:
        return manual_set_out(remove_alternative(
            db, setlist_id, row_id, alt_id, expected_revision=expected_revision), db)
    except ManualSetError as exc:
        raise _manual_error(exc) from exc


@router.post("/{setlist_id}/rows/{row_id}/alternatives/{alt_id}/choose",
             response_model=ManualSetOut)
def alternatives_choose(setlist_id: int, row_id: int, alt_id: int,
                        req: AlternativeChooseRequest, db: Session = Depends(get_db)):
    try:
        return manual_set_out(choose_alternative(
            db, setlist_id, row_id, alt_id, expected_revision=req.expected_revision), db)
    except ManualSetError as exc:
        raise _manual_error(exc) from exc
```

- [ ] **Step 7: Esegui i test e la suite**

Run: `cd backend && .venv/bin/python -m pytest tests/test_set_manual_api.py -q -p no:cacheprovider` → verde.
Run: `cd backend && .venv/bin/python -m pytest tests -q -p no:cacheprovider` → verde.

- [ ] **Step 8: Commit**

```bash
git add backend/app/schemas.py backend/app/serializers.py backend/app/routers/sets.py backend/app/services/manual_material.py backend/tests/test_set_manual_api.py
git commit -m "feat(sets): endpoint delle alternative e della riserva, materiale che le distingue"
```

---

### Task 4: Client, tipi e testi

**Files:**
- Modify: `frontend/lib/api/types.ts`, `frontend/lib/api/manual-sets.ts`
- Modify: `frontend/lib/i18n/en.ts`, poi `frontend/lib/i18n/it.ts`

**Interfaces:**
- Produces:

```ts
export interface ManualAlternative { id: number; position: number; track: Track; note: string | null }
// ManualRow guadagna: alternatives: ManualAlternative[]
// ManualSet guadagna: reserve: ManualRow[]
// MaterialItem guadagna: in_reserve: boolean

addAlternatives(id: number, rowId: number, body: { expected_revision: number; track_ids: number[] }): Promise<ManualSet>
removeAlternative(id: number, rowId: number, altId: number, expectedRevision: number): Promise<ManualSet>
chooseAlternative(id: number, rowId: number, altId: number, body: { expected_revision: number }): Promise<ManualSet>
// insertRows guadagna `reserve?: boolean`; moveRow guadagna `to_reserve?: boolean | null`
// getMaterial guadagna `reserved?: boolean`
```

- [ ] **Step 1: Tipi**

In `frontend/lib/api/types.ts`, nella sezione del set manuale:

```ts
export interface ManualAlternative {
  id: number;
  position: number;
  track: Track;
  note: string | null;
}
```

`ManualRow` guadagna `alternatives: ManualAlternative[];`, `ManualSet` guadagna `reserve: ManualRow[];`, `MaterialItem` guadagna `in_reserve: boolean;`.

- [ ] **Step 2: Client**

In `frontend/lib/api/manual-sets.ts`, estendi le due firme esistenti e aggiungi le tre nuove:

```ts
export function insertRows(
  id: number,
  body: { expected_revision: number; track_ids?: number[]; gap?: boolean; after_row_id?: number | null; reserve?: boolean },
) {
  return apiPost<ManualSet>(`/api/sets/${id}/rows`, body);
}

export function moveRow(
  id: number,
  rowId: number,
  body: { expected_revision: number; position: number; to_reserve?: boolean | null },
) {
  return apiPost<ManualSet>(`/api/sets/${id}/rows/${rowId}/move`, body);
}

export function getMaterial(
  id: number,
  opts: { q?: string; owned?: boolean; unused?: boolean; reserved?: boolean } = {},
) {
  const p = new URLSearchParams();
  if (opts.q) p.set("q", opts.q);
  if (opts.owned) p.set("owned", "true");
  if (opts.unused) p.set("unused", "true");
  if (opts.reserved) p.set("reserved", "true");
  const qs = p.toString();
  return apiGet<Material>(`/api/sets/${id}/material${qs ? `?${qs}` : ""}`);
}

/** Candidate tenute dal DJ su una riga: non sono le alternative calcolate dal
 *  vecchio generatore, che vivono su un altro endpoint e altri set. */
export function addAlternatives(id: number, rowId: number, body: { expected_revision: number; track_ids: number[] }) {
  return apiPost<ManualSet>(`/api/sets/${id}/rows/${rowId}/alternatives`, body);
}

export function removeAlternative(id: number, rowId: number, altId: number, expectedRevision: number) {
  return apiDelete<ManualSet>(`/api/sets/${id}/rows/${rowId}/alternatives/${altId}?expected_revision=${expectedRevision}`);
}

export function chooseAlternative(id: number, rowId: number, altId: number, body: { expected_revision: number }) {
  return apiPost<ManualSet>(`/api/sets/${id}/rows/${rowId}/alternatives/${altId}/choose`, body);
}
```

- [ ] **Step 3: Testi**

In `frontend/lib/i18n/en.ts`, dentro `sets.manual`:

```ts
      alternativesTitle: "Alternatives",
      alternativesEmpty: "No alternatives on this row yet.",
      addAlternativeTitle: "Keep as an alternative",
      activeBadge: "active",
      useAlternativeButton: "Use",
      removeAlternativeTitle: "Remove from the alternatives",
      compareButton: (n: number) => `Compare the ${n}`,
      compareTitle: "Comparison",
      compareCloseButton: "Close",
      compareHint: "Listen to them one at a time, then pick the one that stays.",
      reserveTitle: "Reserve",
      reserveEmpty: "Nothing set aside. Use «Set aside» on a track in the material.",
      reserveAddTitle: "Set aside for the night",
      toReserveTitle: "Move to the reserve",
      toPathTitle: "Put back in the path",
      filterReserved: "set aside",
      reserveMeta: (n: number) => (n === 1 ? "1 track set aside" : `${n} tracks set aside`),
```

e in `errors`:

```ts
    set_alternative_not_found: "Alternative not found",
```

In `frontend/lib/i18n/it.ts`, le stesse chiavi:

```ts
      alternativesTitle: "Alternative",
      alternativesEmpty: "Nessuna alternativa su questa riga.",
      addAlternativeTitle: "Tieni come alternativa",
      activeBadge: "attiva",
      useAlternativeButton: "Usa",
      removeAlternativeTitle: "Togli dalle alternative",
      compareButton: (n: number) => `Confronta le ${n}`,
      compareTitle: "Confronto",
      compareCloseButton: "Chiudi",
      compareHint: "Ascoltale una alla volta, poi scegli quella che resta.",
      reserveTitle: "Riserva",
      reserveEmpty: "Niente da parte. Usa «Metti da parte» su una traccia del materiale.",
      reserveAddTitle: "Metti da parte per la serata",
      toReserveTitle: "Sposta in riserva",
      toPathTitle: "Rimetti nel percorso",
      filterReserved: "da parte",
      reserveMeta: (n: number) => (n === 1 ? "1 traccia da parte" : `${n} tracce da parte`),
```

e in `errors`:

```ts
    set_alternative_not_found: "Alternativa non trovata",
```

- [ ] **Step 4: Verifica e commit**

Run: `cd frontend && npx tsc --noEmit && npm run lint && npm run test:unit`
Expected: tsc pulito, lint invariato, 614 test verdi (nessun test nuovo in questo task: il tipo è la verifica, e i gesti li prova il Task 5).

```bash
git add frontend/lib/api/types.ts frontend/lib/api/manual-sets.ts frontend/lib/i18n/en.ts frontend/lib/i18n/it.ts
git commit -m "feat(frontend): client, tipi e testi di alternative e riserva"
```

---

### Task 5: La pagina — alternative, confronto, riserva

**Files:**
- Create: `frontend/components/set-builder/compare-panel.tsx`
- Create: `frontend/components/set-builder/reserve-panel.tsx`
- Modify: `frontend/components/set-builder/detail-panel.tsx`
- Modify: `frontend/components/set-builder/material-panel.tsx`
- Modify: `frontend/components/set-builder/path-panel.tsx`
- Modify: `frontend/app/sets/manual/page.tsx`
- Test: `frontend/tests/set-builder-alternatives.test.tsx` (nuovo)

**Interfaces:**
- Consumes: Task 4 (`addAlternatives`, `removeAlternative`, `chooseAlternative`, `insertRows` con `reserve`, `moveRow` con `to_reserve`, `getMaterial` con `reserved`, i tipi `ManualAlternative`, `ManualRow`, `ManualSet`, `MaterialItem`).
- La pagina possiede lo stato; i pannelli restano presentazionali, come nella tappa 1.

Comportamento richiesto:
- Nel materiale, accanto a «Aggiungi al percorso», un secondo comando «Metti da parte» che chiama `insertRows` con `reserve: true`; e un terzo filtro, «da parte», che chiama `getMaterial` con `reserved: true`.
- Sotto il percorso, la riserva: ogni riga con un comando «Rimetti nel percorso» (`moveRow` con `to_reserve: false`, `position: 1`) e uno per toglierla.
- Nel percorso, su ogni riga un comando «Sposta in riserva» (`moveRow` con `to_reserve: true`, `position: 1`).
- Nel dettaglio della riga selezionata, sotto l'appunto: la traccia attiva marcata «attiva», le alternative con «Usa» e «Togli», e un comando di confronto attivo quando attiva + alternative fanno da 2 a 4.
- Il confronto è un pannello che elenca affiancate le 2-4 candidate con artista, titolo, BPM, tonalità e durata, scrivendo «sconosciuto» dove manca il dato, con «Usa» su ciascuna e un pulsante di chiusura. Il contesto di ascolto è esplicito: le tracce in confronto, passate a `TrackPlayButton` come `context`.
- Ogni mutazione manda `expected_revision`, rimpiazza lo stato con la risposta e ricarica il materiale, esattamente come i gesti della tappa 1; un 409 mostra il banner di conflitto esistente.

- [ ] **Step 1: Scrivi il test**

`frontend/tests/set-builder-alternatives.test.tsx`:

```tsx
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";

const api = vi.hoisted(() => ({
  getManualSet: vi.fn(),
  getMaterial: vi.fn(),
  insertRows: vi.fn(),
  moveRow: vi.fn(),
  patchRow: vi.fn(),
  removeRow: vi.fn(),
  addAlternatives: vi.fn(),
  removeAlternative: vi.fn(),
  chooseAlternative: vi.fn(),
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
import { PlayerProvider } from "@/lib/player";

const mount = () => render(<PlayerProvider><ManualSetPage /></PlayerProvider>);

const track = (id: number, extra = {}) => ({
  id, spotify_id: null, soundcloud_id: null, source_type: "spotify", platform: "spotify",
  title: `Traccia ${id}`, artist: "Artista", album: null, genre: null, year: null,
  duration_seconds: 300, bpm: id === 3 ? null : 124, camelot_key: id === 3 ? null : "8A",
  energy: null, label: null, status: "imported", url: null, isrc: null, playlists: [],
  added_at: null, spotify_url: null, album_art_url: null, has_local_file: true, rating: null, ...extra,
});

const alt = (id: number, trackId: number) => ({ id, position: id, track: track(trackId), note: null });

const set = (opts: { revision?: number; alts?: number[]; reserve?: number[] } = {}) => ({
  id: 7, name: "Sabato", kind: "manual", revision: opts.revision ?? 1,
  source_playlist_id: 3, source_playlist_name: "Deep", notes: null,
  track_count: 1, total_file_seconds: 300,
  created_at: "2026-09-19T10:00:00", updated_at: "2026-09-19T10:00:00",
  blocks: [{
    id: 1, name: null, placement: "main" as const, position: 1,
    rows: [{
      id: 10, block_id: 1, position: 1, slot_kind: "track" as const, track: track(1), note: null,
      alternatives: (opts.alts ?? []).map((tid, i) => alt(i + 1, tid)),
    }],
  }],
  reserve: (opts.reserve ?? []).map((tid, i) => ({
    id: 90 + i, block_id: null, position: i + 1, slot_kind: "track" as const,
    track: track(tid), note: null, alternatives: [],
  })),
});

const material = () => ({
  playlist_id: 3, playlist_name: "Deep",
  items: [1, 2, 3].map((id) => ({
    track: track(id), in_set: id === 1, from_playlist: true, in_reserve: false,
  })),
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

describe("alternative", () => {
  it("tiene una traccia del materiale come alternativa della riga selezionata", async () => {
    api.addAlternatives.mockResolvedValue(set({ revision: 2, alts: [2] }));
    mount();
    fireEvent.click((await screen.findAllByText(/Traccia 1/)).find((el) => el.closest("button"))!);
    fireEvent.click(screen.getAllByTitle("Tieni come alternativa")[0]);
    await waitFor(() => expect(api.addAlternatives).toHaveBeenCalledWith(7, 10, {
      expected_revision: 1, track_ids: [2],
    }));
  });

  it("«Usa» scambia l'attiva e il pannello mostra la precedente fra le alternative", async () => {
    api.getManualSet.mockResolvedValue(set({ alts: [2] }));
    api.chooseAlternative.mockResolvedValue(set({ revision: 2, alts: [1] }));
    mount();
    fireEvent.click((await screen.findAllByText(/Traccia 1/)).find((el) => el.closest("button"))!);
    const dettaglio = within(screen.getByTestId("detail-panel"));
    fireEvent.click(dettaglio.getByText("Usa"));
    await waitFor(() => expect(api.chooseAlternative).toHaveBeenCalledWith(7, 10, 1, {
      expected_revision: 1,
    }));
  });

  it("il confronto mostra le candidate con «sconosciuto» sui dati mancanti", async () => {
    api.getManualSet.mockResolvedValue(set({ alts: [2, 3] }));
    mount();
    fireEvent.click((await screen.findAllByText(/Traccia 1/)).find((el) => el.closest("button"))!);
    fireEvent.click(screen.getByText(/Confronta le 3/));
    const confronto = within(await screen.findByTestId("compare-panel"));
    expect(confronto.getAllByText(/Traccia/).length).toBe(3);
    expect(confronto.getAllByText("sconosciuto").length).toBe(2); // BPM e tonalità della terza
  });
});

describe("riserva", () => {
  it("mette da parte una traccia del materiale", async () => {
    api.insertRows.mockResolvedValue(set({ revision: 2, reserve: [2] }));
    mount();
    await screen.findAllByText(/Traccia 2/);
    fireEvent.click(screen.getAllByTitle("Metti da parte per la serata")[0]);
    await waitFor(() => expect(api.insertRows).toHaveBeenCalledWith(7, {
      expected_revision: 1, track_ids: [2], reserve: true,
    }));
  });

  it("cambiare i filtri del materiale non cambia ciò che sta suonando", async () => {
    // Verifica dichiarata dalla spec per questa tappa. Il contesto di ascolto è
    // uno snapshot preso all'avvio: filtrare la lista non lo tocca.
    api.getManualSet.mockResolvedValue(set({ reserve: [2] }));
    mount();
    await screen.findAllByText(/Traccia 1/);
    const prima = screen.getAllByTitle(/Ascolta|Riproduci|Play/i)[0];
    fireEvent.click(prima);
    const suonando = screen.getByTestId("reserve-panel").textContent;
    fireEvent.click(screen.getByText("da parte"));
    await waitFor(() => expect(api.getMaterial).toHaveBeenCalledWith(7, expect.objectContaining({ reserved: true })));
    expect(screen.getByTestId("reserve-panel").textContent).toBe(suonando);
  });

  it("rimette nel percorso una traccia della riserva", async () => {
    api.getManualSet.mockResolvedValue(set({ reserve: [2] }));
    api.moveRow.mockResolvedValue(set({ revision: 2 }));
    mount();
    const riserva = within(await screen.findByTestId("reserve-panel"));
    fireEvent.click(riserva.getByTitle("Rimetti nel percorso"));
    await waitFor(() => expect(api.moveRow).toHaveBeenCalledWith(7, 90, {
      expected_revision: 1, position: 1, to_reserve: false,
    }));
  });
});
```

- [ ] **Step 2: Esegui e verifica che fallisca**

Run: `cd frontend && npm run test:unit -- tests/set-builder-alternatives.test.tsx`
Expected: FAIL (i comandi non esistono ancora).

- [ ] **Step 3: Il pannello di confronto**

`frontend/components/set-builder/compare-panel.tsx`:

```tsx
"use client";

import { X } from "lucide-react";
import { type ManualAlternative, type ManualRow, type Track, fmtDuration } from "@/lib/api";
import { Button } from "@/components/ui";
import { TrackPlayButton } from "@/components/track-play-button";
import { useT } from "@/lib/i18n";

type Candidate = { key: string; track: Track; alt: ManualAlternative | null };

type Props = {
  row: ManualRow;
  onUse: (alt: ManualAlternative) => void;
  onClose: () => void;
};

/** Confronto 2-4 candidate di una riga: l'attiva e le sue alternative, con i
 *  dati tecnici affiancati e "sconosciuto" dove manca un valore. Il contesto
 *  di ascolto è esplicito: le tracce in confronto, nessun'altra. */
export function ComparePanel({ row, onUse, onClose }: Props) {
  const t = useT();
  const candidates: Candidate[] = [
    ...(row.track ? [{ key: "active", track: row.track, alt: null }] : []),
    ...row.alternatives.map((a) => ({ key: `alt-${a.id}`, track: a.track, alt: a })),
  ];
  const context = candidates.filter((c) => c.track.has_local_file).map((c) => c.track);
  return (
    <div data-testid="compare-panel" className="mt-3 border border-border p-3">
      <div className="mb-2 flex items-center justify-between">
        <span className="text-xs uppercase tracking-wider text-muted">{t.sets.manual.compareTitle}</span>
        <button type="button" onClick={onClose} title={t.sets.manual.compareCloseButton} className="text-muted hover:text-fg">
          <X size={14} />
        </button>
      </div>
      <p className="mb-2 text-xs text-muted">{t.sets.manual.compareHint}</p>
      <ul className="grid gap-2 sm:grid-cols-2">
        {candidates.map((c) => (
          <li key={c.key} className="border border-border p-2">
            <div className="mb-1 flex items-center gap-2">
              <TrackPlayButton track={c.track} context={context} />
              <span className="min-w-0 flex-1 truncate text-sm">{c.track.artist} – {c.track.title}</span>
            </div>
            <dl className="flex flex-wrap gap-x-3 text-xs text-muted">
              <span className="tnum">{c.track.bpm ?? t.sets.manual.unknownValue}</span>
              <span>{c.track.camelot_key ?? t.sets.manual.unknownValue}</span>
              <span className="tnum">{c.track.duration_seconds ? fmtDuration(c.track.duration_seconds) : t.sets.manual.unknownValue}</span>
            </dl>
            <div className="mt-2">
              {c.alt
                ? <Button size="sm" variant="outline" onClick={() => onUse(c.alt!)}>{t.sets.manual.useAlternativeButton}</Button>
                : <span className="text-xs text-muted">{t.sets.manual.activeBadge}</span>}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
```

- [ ] **Step 4: Il pannello della riserva**

`frontend/components/set-builder/reserve-panel.tsx`:

```tsx
"use client";

import { CornerUpLeft, Trash2 } from "lucide-react";
import { type ManualRow } from "@/lib/api";
import { TrackPlayButton } from "@/components/track-play-button";
import { useT } from "@/lib/i18n";

type Props = {
  rows: ManualRow[];
  onToPath: (row: ManualRow) => void;
  onRemove: (row: ManualRow) => void;
};

/** Le tracce tenute in tasca per la serata: non sono nel percorso e non
 *  contano nella durata del set. */
export function ReservePanel({ rows, onToPath, onRemove }: Props) {
  const t = useT();
  const playable = rows.filter((r) => r.track?.has_local_file).map((r) => r.track!);
  return (
    <div data-testid="reserve-panel">
      <div className="mb-1 mt-4 flex items-baseline justify-between">
        <span className="text-xs uppercase tracking-wider text-muted">{t.sets.manual.reserveTitle}</span>
        {rows.length > 0 && <span className="text-xs text-muted">{t.sets.manual.reserveMeta(rows.length)}</span>}
      </div>
      {rows.length === 0 && <p className="text-sm text-muted">{t.sets.manual.reserveEmpty}</p>}
      <ul className="divide-y divide-border">
        {rows.map((row) => (
          <li key={row.id} className="flex items-center gap-2 py-1.5">
            {row.track && <TrackPlayButton track={row.track} context={playable} />}
            <span className="min-w-0 flex-1 truncate text-sm">{row.track?.artist} – {row.track?.title}</span>
            <span className="tnum hidden text-xs text-muted sm:inline">
              {row.track?.bpm ?? t.sets.manual.unknownValue} · {row.track?.camelot_key ?? t.sets.manual.unknownValue}
            </span>
            <button type="button" title={t.sets.manual.toPathTitle} onClick={() => onToPath(row)} className="text-muted hover:text-fg">
              <CornerUpLeft size={14} />
            </button>
            <button type="button" title={t.sets.manual.removeTitle} onClick={() => onRemove(row)} className="text-muted hover:text-danger">
              <Trash2 size={14} />
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
```

- [ ] **Step 5: Dettaglio, materiale, percorso**

In `detail-panel.tsx`, le props diventano:

```tsx
type Props = {
  row: ManualRow | null;
  saveState: SaveState;
  onSaveNote: (row: ManualRow, note: string) => void;
  onUseAlternative: (row: ManualRow, alt: ManualAlternative) => void;
  onRemoveAlternative: (row: ManualRow, alt: ManualAlternative) => void;
  onCompare: (row: ManualRow) => void;
};
```

e sotto il blocco dell'appunto, prima della chiusura del componente:

```tsx
      <div className="border-t border-border pt-3">
        <div className="mb-2 flex items-baseline justify-between">
          <span className="text-xs uppercase tracking-wider text-muted">{t.sets.manual.alternativesTitle}</span>
          {row.alternatives.length > 0 && row.alternatives.length + (row.track ? 1 : 0) <= 4 && (
            <button type="button" onClick={() => onCompare(row)} className="text-xs text-muted underline-offset-4 hover:text-fg hover:underline">
              {t.sets.manual.compareButton(row.alternatives.length + (row.track ? 1 : 0))}
            </button>
          )}
        </div>
        {row.alternatives.length === 0 && <p className="text-sm text-muted">{t.sets.manual.alternativesEmpty}</p>}
        <ul className="divide-y divide-border">
          {row.track && (
            <li className="flex items-center gap-2 py-1.5">
              <span className="min-w-0 flex-1 truncate text-sm">{row.track.artist} – {row.track.title}</span>
              <Badge>{t.sets.manual.activeBadge}</Badge>
            </li>
          )}
          {row.alternatives.map((a) => (
            <li key={a.id} className="flex items-center gap-2 py-1.5">
              <TrackPlayButton track={a.track} context={[a.track]} />
              <span className="min-w-0 flex-1 truncate text-sm">{a.track.artist} – {a.track.title}</span>
              <Button size="sm" variant="outline" onClick={() => onUseAlternative(row, a)}>{t.sets.manual.useAlternativeButton}</Button>
              <button type="button" title={t.sets.manual.removeAlternativeTitle} onClick={() => onRemoveAlternative(row, a)} className="text-muted hover:text-danger">
                <Trash2 size={14} />
              </button>
            </li>
          ))}
        </ul>
      </div>
```

Aggiungi gli import mancanti in testa al file: `Trash2` da `lucide-react`, `Badge` e `Button` da `@/components/ui`, `TrackPlayButton`, e i tipi `ManualAlternative`.

In `material-panel.tsx`, le props guadagnano `onReserve: (item: MaterialItem) => void`, `onAddAlternative: (item: MaterialItem) => void`, `reserved: boolean`, `onReserved: (v: boolean) => void`, `canAddAlternative: boolean`. Accanto al chip esistenti:

```tsx
        <Chip on={reserved} onClick={() => onReserved(!reserved)}>{t.sets.manual.filterReserved}</Chip>
```

e accanto al pulsante «+» di ogni riga:

```tsx
            <button type="button" title={t.sets.manual.reserveAddTitle} onClick={() => onReserve(it)}
              className="grid h-7 w-7 place-items-center border border-border text-muted hover:text-fg">
              <Bookmark size={14} />
            </button>
            {canAddAlternative && (
              <button type="button" title={t.sets.manual.addAlternativeTitle} onClick={() => onAddAlternative(it)}
                className="grid h-7 w-7 place-items-center border border-border text-muted hover:text-fg">
                <Layers size={14} />
              </button>
            )}
```

(`Bookmark` e `Layers` da `lucide-react`. `canAddAlternative` è vero quando la pagina ha una riga selezionata.)

In `path-panel.tsx`, le props guadagnano `onToReserve: (row: ManualRow) => void`, e accanto agli altri comandi di riga:

```tsx
          <button type="button" title={t.sets.manual.toReserveTitle} onClick={() => onToReserve(row)} className="text-muted"><Bookmark size={14} /></button>
```

- [ ] **Step 6: La pagina**

In `frontend/app/sets/manual/page.tsx`: importa le funzioni nuove dal client, `ComparePanel`, `ReservePanel` e il tipo `ManualAlternative`; aggiungi lo stato `const [reserved, setReserved] = useState(false);` e `const [compareRowId, setCompareRowId] = useState<number | null>(null);`; includi `reserved` nella chiamata a `getMaterial` e nelle dipendenze del debounce.

I gesti nuovi, accanto a quelli esistenti:

```tsx
  const onReserve = (item: MaterialItem) => mutate((rev) => insertRows(id, { expected_revision: rev, track_ids: [item.track.id], reserve: true }));
  const onAddAlternative = (item: MaterialItem) => selected && mutate((rev) => addAlternatives(id, selected.id, { expected_revision: rev, track_ids: [item.track.id] }));
  const onUseAlternative = (row: ManualRow, alt: ManualAlternative) => mutate((rev) => chooseAlternative(id, row.id, alt.id, { expected_revision: rev }));
  const onRemoveAlternative = (row: ManualRow, alt: ManualAlternative) => mutate((rev) => removeAlternative(id, row.id, alt.id, rev));
  const onToReserve = (row: ManualRow) => mutate((rev) => moveRow(id, row.id, { expected_revision: rev, position: 1, to_reserve: true }));
  const onToPath = (row: ManualRow) => mutate((rev) => moveRow(id, row.id, { expected_revision: rev, position: 1, to_reserve: false }));
```

Il confronto si chiude da sé quando la riga cambia:

```tsx
  const compareRow = rows.find((r) => r.id === compareRowId) ?? null;
```

e si rende sotto il dettaglio:

```tsx
            <DetailPanel row={selected} saveState={saveState} onSaveNote={(r, n) => void onSaveNote(r, n)}
              onUseAlternative={(r, a) => void onUseAlternative(r, a)}
              onRemoveAlternative={(r, a) => void onRemoveAlternative(r, a)}
              onCompare={(r) => setCompareRowId(r.id)} />
            {compareRow && (
              <ComparePanel row={compareRow} onClose={() => setCompareRowId(null)}
                onUse={(a) => void onUseAlternative(compareRow, a)} />
            )}
```

La riserva va sotto il percorso, dentro la stessa Card:

```tsx
            <ReservePanel rows={set.reserve} onToPath={(r) => void onToPath(r)} onRemove={(r) => void onRemove(r)} />
```

- [ ] **Step 7: Esegui il test, i tipi, il lint, la suite e la build**

Run: `cd frontend && npm run test:unit -- tests/set-builder-alternatives.test.tsx` → 6 verdi.
Run: `cd frontend && npx tsc --noEmit && npm run lint && npm run test:unit && npm run build` → tutto verde, 620 test.

Il titolo del pulsante di ascolto nel test («Ascolta / Riproduci / Play») va allineato alla chiave i18n reale di `TrackPlayButton`: leggila prima di scrivere il selettore, e usa quella, non la regex di comodo.

- [ ] **Step 8: Commit**

```bash
git add frontend/components/set-builder frontend/app/sets/manual/page.tsx frontend/tests/set-builder-alternatives.test.tsx
git commit -m "feat(frontend): alternative, confronto e riserva nella pagina del set manuale"
```

---

### Task 6: Documentazione e verifica integrata

**Files:**
- Modify: `docs/API.md`, `docs/ARCHITECTURE.md`, `PROGRESS.md`
- Create: `frontend/e2e/set-builder.spec.ts` (oggi `frontend/e2e/` contiene solo downloads-queue, settings, setup, smoke e wishlist: il percorso del set manuale non ha ancora un suo file)

- [ ] **Step 1: Documentazione**

`docs/API.md`: nella sezione del set manuale, i tre endpoint delle alternative con i loro parametri e il codice `set_alternative_not_found`; il campo `reserve` su `RowsInsertRequest`, `to_reserve` su `RowMoveRequest`, `reserved` su `/material`; i campi nuovi delle risposte (`alternatives`, `reserve`, `in_reserve`). Verifica ogni firma contro `backend/app/routers/sets.py` prima di scriverla.

`docs/ARCHITECTURE.md`: due frasi nella sezione Set Builder — l'attiva è `SetlistTrack.track_id` e le candidate stanno in `setlist_alternatives`, sceglierne una è uno scambio che conserva la precedente; la riserva è righe senza blocco e non entra nel conteggio del set.

`PROGRESS.md`: voce datata con cosa esiste ora e cosa no (niente sequenze, banco, annulla: tappa 3).

**La regola del progetto sulla documentazione**, da `docs/ROADMAP.md`, vincola questo step: ogni parentesi e ogni rimando va verificato per conto proprio, separatamente dalla frase che lo ospita. Non rivendicare nulla che questa tappa non consegni.

- [ ] **Step 2: E2E**

Crea `frontend/e2e/set-builder.spec.ts` seguendo la forma degli spec esistenti (`wishlist.spec.ts` è il più vicino: backend e frontend su porte dedicate con DB vuoto, avviati dalla configurazione Playwright). Il percorso: crea un set a mano, aggiungi due tracce dal materiale, tieni la seconda come alternativa della prima, usa l'alternativa e verifica lo scambio, metti una traccia da parte, ricarica la pagina e verifica che alternativa e riserva ci siano ancora.

Con un DB vuoto non esistono playlist né tracce: crea il set senza playlist (`POST /api/sets/manual` con il solo nome, dalla pagina) e porta le tracce con la ricerca in libreria, oppure semina il DB come fanno gli altri spec. Se l'ambiente non consente di avviare la suite, riportalo come concern con l'errore esatto invece di forzare.

Run: `cd frontend && npm run test:e2e -- set-builder.spec.ts`

- [ ] **Step 3: Verifica finale**

```bash
cd backend && .venv/bin/python -m pytest tests -q
```

```bash
cd frontend && npm run lint && npm run test:unit && npm run build
```

- [ ] **Step 4: Commit**

```bash
git add docs/API.md docs/ARCHITECTURE.md PROGRESS.md frontend/e2e
git commit -m "docs(sets): alternative e riserva del set manuale"
```
