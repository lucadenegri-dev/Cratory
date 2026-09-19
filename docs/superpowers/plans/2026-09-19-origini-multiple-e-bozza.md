# Origini multiple e set che nasce quando serve — piano di implementazione

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Un set può pescare da più playlist insieme, e le sue origini si aggiungono e si tolgono mentre si lavora; e «Prepara un set» non salva più niente finché non ci metti dentro qualcosa — la bozza vive nella pagina, il set nasce alla prima riga.

**Architecture:** Le origini diventano una tabella di raccordo, `SetlistSource`, con la posizione a tenerne l'ordine; `Setlist.source_playlist_id` resta finché la migrazione non ha travasato i set esistenti, poi sparisce. Il materiale si calcola già da una lista di playlist: cambia solo chi gliela passa. La bozza è interamente lato client — nessuno stato «non salvato» sul server — e il primo gesto che vuole una riga crea il set e poi esegue il gesto.

**Tech Stack:** Python 3 + FastAPI + SQLAlchemy 2 (SQLite, migrazioni idempotenti in `db.py`), Pydantic v2, pytest. Next.js 16 App Router, React, Tailwind, vitest + @testing-library/react, Playwright.

**Spec:** nessuna: è una richiesta dell'utente del 2026-09-19, successiva a `docs/superpowers/specs/2026-09-15-set-builder-workbench.md`. Vedi «Cosa cambia rispetto alla spec» qui sotto.

## Global Constraints

- Backend: `cd backend && .venv/bin/python -m pytest tests -q` deve restare verde. Baseline: **2464 passed, 4 deselected**.
- Frontend baseline: **655 test in 106 file**, `npx tsc --noEmit` pulito, `npm run lint` senza errori (4 warning pre-esistenti non correlati), `npm run build` verde, e2e **35 test** verdi.
- Migrazioni: solo dentro `ensure_schema` in `backend/app/db.py`, idempotenti. La tabella nuova la crea `create_all`; il travaso dei dati esistenti è una funzione dedicata, e **deve girare prima** che la colonna vecchia venga tolta.
- Errori HTTP: sempre `api_error(status, code, message, **params)`; ogni `code` nuovo tradotto in `frontend/lib/i18n/en.ts` **e** `it.ts` sotto `errors`.
- Ogni mutazione di un set esistente controlla `expected_revision`, muta, salva uno snapshot e committa nella stessa transazione.
- Nessuna chiamata AI, nessun pacchetto nuovo.
- Frontend: leggere `frontend/CLAUDE.md`. Nessuna stringa user-facing fuori dai dizionari; chiavi in `en.ts` prima, poi `it.ts`. Spazi fra elementi inline: `{" "}` esplicito.
- Commit in italiano, stile `feat(sets): …`, nessun `Co-Authored-By`. Prima di ogni commit `git status --porcelain`, stage dei soli file del task.

## Cosa cambia rispetto alla spec, e cosa no

La spec dice, fra le regole della sezione 3: **«Un set a mano può essere vuoto.»** Per quella riga, alla tappa 1, la pulizia legacy di `db.py` che elimina i `setlists` senza righe è stata limitata a `kind = generated`. L'utente ha deciso il contrario il 2026-09-19: un set che non ha mai avuto niente dentro non deve restare in giro.

**Non si fa cancellando i set vuoti**, e la distinzione è tutto il punto: un set che svuoti *dopo* è una decisione tua, e cancellartelo sotto il naso sarebbe perdere dati. Si fa non creandolo affatto finché non serve. Quindi:

- la pulizia legacy resta limitata a `kind = generated`, esattamente com'è;
- `POST /api/sets/manual` non viene chiamato all'apertura del banco, ma al primo gesto che ha bisogno di una riga;
- un set esistente e svuotato resta dov'è.

La spec dice anche che il materiale è «la playlist di origine letta aggiornata». Resta vero: cambia solo che le playlist possono essere più d'una.

---

## File structure

| File | Responsabilità |
|---|---|
| `backend/app/models.py` | `SetlistSource`; `Setlist.sources` |
| `backend/app/db.py` | Travaso di `source_playlist_id` nella tabella nuova |
| `backend/app/repositories.py` | `delete_playlist` toglie le righe di origine |
| `backend/app/services/manual_material.py` | Il materiale legge tutte le origini |
| `backend/app/services/manual_set.py` | `create_manual_set` con più playlist; `add_source`, `remove_source` |
| `backend/app/schemas.py`, `backend/app/serializers.py` | `sources` nel documento e nel materiale |
| `backend/app/routers/sets.py` | Endpoint delle origini; materiale della bozza |
| `backend/tests/test_set_manual_sources.py` (nuovo) | Origini multiple, ordine, ciclo di vita |
| `frontend/components/set-builder/sources-panel.tsx` (nuovo) | Le origini dentro il pannello materiale |
| `frontend/app/sets/manual/page.tsx` | La bozza, e il set che nasce alla prima riga |
| `frontend/app/sets/page.tsx` | «Prepara un set» apre la bozza invece di creare |
| `frontend/tests/set-builder-sources.test.tsx`, `set-builder-draft.test.tsx` (nuovi) | I due comportamenti |
| `docs/API.md`, `docs/ARCHITECTURE.md`, `PROGRESS.md`, `frontend/e2e/set-builder.spec.ts` | Documentazione e verifica |

---

### Task 1: Le origini nel modello, e i set che ci sono già

**Files:**
- Modify: `backend/app/models.py`, `backend/app/db.py`, `backend/app/repositories.py`, `backend/app/tools/clean_user_data.py`
- Test: `backend/tests/test_set_manual_sources.py` (nuovo)

**Interfaces:**
- Produces: `SetlistSource(id, setlist_id, playlist_id, position, setlist, playlist)`; `Setlist.sources: list[SetlistSource]` (cascade all/delete-orphan, ordinata per `position`).

**Il punto delicato è il travaso.** L'utente ha già dei set con `source_playlist_id` valorizzato. Se la tabella nuova nasce vuota, quei set perdono la loro origine in silenzio: il materiale si riduce alla ricerca in libreria e sembra che l'app abbia dimenticato da dove venivano. La migrazione copia prima, e solo dopo si può togliere la colonna — che in questo piano **non si toglie**, perché una colonna morta ma innocua è meglio di un travaso fatto a metà. La si toglie in un secondo momento, quando il travaso avrà girato su ogni database vivo.

- [ ] **Step 1: Scrivi i test che falliscono**

`backend/tests/test_set_manual_sources.py`:

```python
"""Origini multiple di un set (2026-09-19): modello, travaso, ciclo di vita."""
from sqlalchemy import select

from app.models import Playlist, Setlist, SetlistSource, Track
from app.repositories import add_track_to_playlist, delete_playlist


def _playlist(db, nome, n=2):
    pl = Playlist(platform="spotify", name=nome)
    db.add(pl)
    db.flush()
    for i in range(n):
        t = Track(source_type="spotify", title=f"{nome}-{i}", artist="A",
                  duration_seconds=300, bpm=124.0, camelot_key="8A", has_local_file=True)
        db.add(t)
        db.flush()
        add_track_to_playlist(db, t, pl, added_by="test")
    db.commit()
    return pl


def test_un_set_puo_avere_piu_origini_in_ordine(db):
    a, b = _playlist(db, "A"), _playlist(db, "B")
    s = Setlist(name="M", kind="manual")
    db.add(s)
    db.flush()
    db.add_all([
        SetlistSource(setlist_id=s.id, playlist_id=b.id, position=2),
        SetlistSource(setlist_id=s.id, playlist_id=a.id, position=1),
    ])
    db.commit()
    db.refresh(s)
    assert [src.playlist_id for src in s.sources] == [a.id, b.id]


def test_cancellare_il_set_cancella_le_sue_origini_non_le_playlist(db):
    a = _playlist(db, "A")
    s = Setlist(name="M", kind="manual")
    db.add(s)
    db.flush()
    db.add(SetlistSource(setlist_id=s.id, playlist_id=a.id, position=1))
    db.commit()
    db.delete(s)
    db.commit()
    assert db.scalars(select(SetlistSource)).all() == []
    assert db.get(Playlist, a.id) is not None


def test_cancellare_una_playlist_toglie_l_origine_e_lascia_il_set(db):
    """Regola di sempre: il set resta, il materiale si riduce. Prima la riga di
    origine veniva azzerata; ora va tolta, altrimenti resta appesa a una
    playlist che non c'e' piu'."""
    a, b = _playlist(db, "A"), _playlist(db, "B")
    s = Setlist(name="M", kind="manual")
    db.add(s)
    db.flush()
    db.add_all([SetlistSource(setlist_id=s.id, playlist_id=a.id, position=1),
                SetlistSource(setlist_id=s.id, playlist_id=b.id, position=2)])
    db.commit()

    delete_playlist(db, a.id)

    db.expire_all()
    s = db.get(Setlist, s.id)
    assert s is not None
    assert [src.playlist_id for src in s.sources] == [b.id]
```

In coda, il travaso:

```python
def test_un_set_vecchio_ritrova_la_sua_origine_dopo_la_migrazione(tmp_path):
    """Chi aggiorna ha set con `source_playlist_id`: se la tabella nuova nascesse
    vuota, il materiale si ridurrebbe alla ricerca in libreria e sembrerebbe che
    l'app abbia dimenticato da dove venivano."""
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import sessionmaker

    from app.db import Base, ensure_schema
    import app.models  # noqa: F401
    import app.organize.models  # noqa: F401

    eng = create_engine(f"sqlite:///{tmp_path / 'vecchio.db'}")
    Base.metadata.create_all(eng)
    with sessionmaker(bind=eng)() as sess:
        pl = Playlist(platform="spotify", name="Deep")
        sess.add(pl)
        sess.flush()
        sess.add(Setlist(name="Vecchio", kind="manual", source_playlist_id=pl.id))
        sess.commit()
        pl_id = pl.id
    # La tabella nuova nasce vuota, come su un database che aggiorna.
    with eng.begin() as conn:
        conn.execute(text("DELETE FROM setlist_sources"))

    ensure_schema(eng)

    with eng.begin() as conn:
        righe = conn.execute(text(
            "SELECT playlist_id, position FROM setlist_sources")).fetchall()
    assert [tuple(r) for r in righe] == [(pl_id, 1)]


def test_il_travaso_si_puo_rieseguire(tmp_path):
    """`ensure_schema` gira a ogni avvio: la seconda volta non deve duplicare."""
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import sessionmaker

    from app.db import Base, ensure_schema
    import app.models  # noqa: F401
    import app.organize.models  # noqa: F401

    eng = create_engine(f"sqlite:///{tmp_path / 'due-volte.db'}")
    Base.metadata.create_all(eng)
    with sessionmaker(bind=eng)() as sess:
        pl = Playlist(platform="spotify", name="Deep")
        sess.add(pl)
        sess.flush()
        sess.add(Setlist(name="Vecchio", kind="manual", source_playlist_id=pl.id))
        sess.commit()
    with eng.begin() as conn:
        conn.execute(text("DELETE FROM setlist_sources"))

    ensure_schema(eng)
    ensure_schema(eng)

    with eng.begin() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM setlist_sources")).scalar_one() == 1
```

- [ ] **Step 2: Esegui e verifica che falliscano**

Run: `cd backend && .venv/bin/python -m pytest tests/test_set_manual_sources.py -q -p no:cacheprovider`
Expected: FAIL con `ImportError: cannot import name 'SetlistSource'`.

- [ ] **Step 3: Il modello**

In `backend/app/models.py`, fra le relazioni di `Setlist`, accanto a `pair_notes`:

```python
    sources: Mapped[list["SetlistSource"]] = relationship(
        back_populates="setlist", cascade="all, delete-orphan",
        order_by="SetlistSource.position",
    )
```

e dopo `class SetlistPairNote`:

```python
class SetlistSource(Base):
    """Una playlist da cui il set pesca il suo materiale.

    Piu' d'una dal 2026-09-19. La membership NON si copia: la playlist si legge
    aggiornata a ogni apertura, come ha sempre fatto l'origine singola, e
    togliere un'origine toglie le sue tracce dal materiale ma non dal percorso —
    una traccia gia' scelta e' una decisione presa.
    """

    __tablename__ = "setlist_sources"
    __table_args__ = (
        UniqueConstraint("setlist_id", "playlist_id", name="uq_source_per_set"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    setlist_id: Mapped[int] = mapped_column(ForeignKey("setlists.id"), index=True)
    playlist_id: Mapped[int] = mapped_column(ForeignKey("playlists.id"), index=True)
    position: Mapped[int] = mapped_column(Integer, default=1)

    setlist: Mapped[Setlist] = relationship(back_populates="sources")
    playlist: Mapped["Playlist"] = relationship()
```

`Setlist.source_playlist_id` **resta**, con il commento aggiornato: è la colonna da cui il travaso legge, e si toglierà quando avrà girato ovunque.

In `backend/app/tools/clean_user_data.py`, `DATA_TABLES` guadagna `"setlist_sources"` subito dopo `"setlist_pair_notes"` (figlie prima delle madri).

- [ ] **Step 4: Il travaso**

In `backend/app/db.py`, accanto alle altre migrazioni, e chiamata in `ensure_schema` **dopo** `_migrate_add_model_columns`:

```python
def _migrate_setlist_sources(conn) -> None:
    """Travasa `setlists.source_playlist_id` in `setlist_sources`.

    Idempotente per costruzione: inserisce solo dove la coppia non c'e' gia',
    quindi la seconda esecuzione non duplica. La colonna vecchia NON si tocca:
    si toglie in un secondo momento, quando questo travaso avra' girato su ogni
    database vivo. Una colonna morta ma innocua e' meglio di un travaso a meta'.
    """
    colonne = {r[1] for r in conn.execute(text("PRAGMA table_info(setlists)")).fetchall()}
    if "source_playlist_id" not in colonne:
        return  # gia' tolta: il travaso ha finito il suo lavoro
    conn.execute(text(
        "INSERT INTO setlist_sources (setlist_id, playlist_id, position) "
        "SELECT s.id, s.source_playlist_id, 1 FROM setlists s "
        "WHERE s.source_playlist_id IS NOT NULL "
        "  AND NOT EXISTS (SELECT 1 FROM setlist_sources ss "
        "                  WHERE ss.setlist_id = s.id AND ss.playlist_id = s.source_playlist_id)"
    ))
```

- [ ] **Step 5: Il ciclo di vita**

In `backend/app/repositories.py`, importa `SetlistSource` e sostituisci il blocco di `delete_playlist`:

```python
    # Il set nato da questa playlist resta, senza quell'origine (il materiale si
    # riduce alle altre origini + cio' che e' nel set + la ricerca in libreria).
    db.execute(delete(SetlistSource).where(SetlistSource.playlist_id == playlist_id))
    db.execute(update(Setlist).where(Setlist.source_playlist_id == playlist_id)
               .values(source_playlist_id=None))
```

(La seconda riga resta finché resta la colonna: un `source_playlist_id` che punta a una playlist cancellata sarebbe una FK appesa.)

- [ ] **Step 6: Esegui e verifica**

Run: `cd backend && .venv/bin/python -m pytest tests/test_set_manual_sources.py -q -p no:cacheprovider` → verdi.

Poi dimostra che il travaso morde: togli la chiamata da `ensure_schema` e verifica che `test_un_set_vecchio_ritrova_la_sua_origine_dopo_la_migrazione` fallisca. Rimettila.

- [ ] **Step 7: Suite completa e commit**

Run: `cd backend && .venv/bin/python -m pytest tests -q -p no:cacheprovider` → 2469 passed.

```bash
git add backend/app/models.py backend/app/db.py backend/app/repositories.py backend/app/tools/clean_user_data.py backend/tests/test_set_manual_sources.py
git commit -m "feat(sets): le origini di un set diventano piu' d'una"
```

---

### Task 2: Il materiale legge tutte le origini

**Files:**
- Modify: `backend/app/services/manual_material.py`, `backend/app/services/manual_set.py`
- Test: `backend/tests/test_set_manual_sources.py` (in coda), `backend/tests/test_set_manual_material.py` (verificare che resti verde)

**Interfaces:**
- Produces:

```python
# manual_material
def material_for(db, setlist, *, q, owned, unused, reserved=False) -> list[tuple[Track, bool, bool, bool]]
    """Invariata nella firma: cambia solo che le playlist di partenza sono
    `setlist.sources` invece di una sola. Ordine: le origini nel loro ordine,
    senza ripetere una traccia che sta in due playlist."""

def material_for_playlists(db, playlist_ids: list[int], *, q, owned) -> list[tuple[Track, bool, bool, bool]]
    """Il materiale di una BOZZA, che un set non ce l'ha ancora: `in_set` e
    `in_reserve` sono sempre falsi."""

# manual_set
def create_manual_set(db, *, name, playlist_ids: list[int]) -> Setlist
def add_source(db, setlist_id, *, expected_revision, playlist_id) -> Setlist
def remove_source(db, setlist_id, *, expected_revision, playlist_id) -> Setlist
```

`create_manual_set` cambia firma: `playlist_id: int | None` diventa `playlist_ids: list[int]`. **Tutti i chiamanti vanno aggiornati**, test compresi — sono una manciata, e un alias di compatibilità qui non serve a nessuno.

- [ ] **Step 1: Scrivi i test** (in coda a `test_set_manual_sources.py`)

```python
from app.services.manual_material import material_for, material_for_playlists
from app.services.manual_set import (
    ManualSetError, add_source, create_manual_set, insert_rows, remove_source,
)


def test_il_materiale_unisce_le_playlist_senza_doppioni(db):
    a, b = _playlist(db, "A"), _playlist(db, "B")
    # Una traccia sta in tutt'e due: deve comparire una volta sola.
    comune = db.scalars(select(Track).where(Track.title == "A-0")).one()
    add_track_to_playlist(db, comune, b, added_by="test")
    db.commit()

    s = create_manual_set(db, name="M", playlist_ids=[a.id, b.id])
    titoli = [t.title for t, *_ in material_for(db, s, q=None, owned=False, unused=False)]
    assert titoli.count("A-0") == 1
    assert {"A-0", "A-1", "B-0", "B-1"} <= set(titoli)


def test_l_ordine_delle_origini_e_quello_del_materiale(db):
    a, b = _playlist(db, "A"), _playlist(db, "B")
    s = create_manual_set(db, name="M", playlist_ids=[b.id, a.id])
    titoli = [t.title for t, *_ in material_for(db, s, q=None, owned=False, unused=False)]
    assert titoli.index("B-0") < titoli.index("A-0")


def test_si_aggiunge_e_si_toglie_un_origine_mentre_si_lavora(db):
    a, b = _playlist(db, "A"), _playlist(db, "B")
    s = create_manual_set(db, name="M", playlist_ids=[a.id])
    s = add_source(db, s.id, expected_revision=0, playlist_id=b.id)
    assert [src.playlist_id for src in s.sources] == [a.id, b.id]

    s = remove_source(db, s.id, expected_revision=1, playlist_id=a.id)
    assert [src.playlist_id for src in s.sources] == [b.id]
    titoli = [t.title for t, *_ in material_for(db, s, q=None, owned=False, unused=False)]
    assert not any(t.startswith("A-") for t in titoli)


def test_togliere_un_origine_non_tocca_il_percorso(db):
    """Una traccia gia' scelta e' una decisione presa: sparisce dal materiale,
    non dal set."""
    a = _playlist(db, "A")
    s = create_manual_set(db, name="M", playlist_ids=[a.id])
    traccia = db.scalars(select(Track).where(Track.title == "A-0")).one()
    s = insert_rows(db, s.id, expected_revision=0, track_ids=[traccia.id],
                    gap=False, after_row_id=None)

    s = remove_source(db, s.id, expected_revision=1, playlist_id=a.id)
    from app.services.manual_set import path_rows
    assert [r.track_id for r in path_rows(s)] == [traccia.id]
    # E resta nel materiale, perche' e' nel set: solo non piu' "dalla playlist".
    voci = {t.title: from_pl for t, _in_set, from_pl, _ in
            material_for(db, s, q=None, owned=False, unused=False)}
    assert voci["A-0"] is False


def test_la_stessa_origine_non_si_aggiunge_due_volte(db):
    a = _playlist(db, "A")
    s = create_manual_set(db, name="M", playlist_ids=[a.id])
    with pytest.raises(ManualSetError):
        add_source(db, s.id, expected_revision=0, playlist_id=a.id)


def test_il_materiale_di_una_bozza_non_ha_un_set(db):
    """La bozza non ha ancora un set: il materiale si chiede per playlist, e
    nessuna traccia risulta «nel set»."""
    a, b = _playlist(db, "A"), _playlist(db, "B")
    voci = material_for_playlists(db, [a.id, b.id], q=None, owned=False)
    assert len(voci) == 4
    assert all(not in_set and not in_reserve for _t, in_set, _fp, in_reserve in voci)
```

(`import pytest` e `from app.repositories import add_track_to_playlist` vanno aggiunti in testa al file se non ci sono già.)

- [ ] **Step 2: Esegui e verifica che falliscano**

Run: `cd backend && .venv/bin/python -m pytest tests/test_set_manual_sources.py -q -p no:cacheprovider` → FAIL su `material_for_playlists` e `add_source`.

- [ ] **Step 3: Il materiale**

In `backend/app/services/manual_material.py`, sostituisci il blocco della playlist singola:

```python
    for source in setlist.sources:
        for track in tracks_for_playlist(db, source.playlist_id):
            push(track, True)
```

e aggiungi, in fondo al file:

```python
def material_for_playlists(db: Session, playlist_ids: list[int], *, q: str | None,
                           owned: bool) -> list[tuple[Track, bool, bool, bool]]:
    """Il materiale di una BOZZA: un set non c'e' ancora, quindi nessuna traccia
    e' «nel set» ne' «in riserva». Stessa forma di `material_for`, cosi' la
    pagina disegna lo stesso pannello prima e dopo che il set sia nato."""
    items: list[tuple[Track, bool, bool, bool]] = []
    seen: set[int] = set()

    def push(track: Track, from_playlist: bool) -> None:
        if track.id in seen:
            return
        seen.add(track.id)
        items.append((track, False, from_playlist, False))

    for playlist_id in playlist_ids:
        for track in tracks_for_playlist(db, playlist_id):
            push(track, True)
    query = (q or "").strip()
    if query:
        _, rows = list_tracks(db, limit=SEARCH_LIMIT, q=query)
        for track, _tags in rows:
            push(track, False)
        items = [it for it in items if _matches(it[0], query)]
    if owned:
        items = [it for it in items if it[0].has_local_file]
    return items
```

Nota: `unused` e `reserved` non hanno senso su una bozza (niente set, niente riserva) e infatti non sono nella firma. `SEARCH_LIMIT`, `list_tracks` e `_matches` sono già nel modulo: la ricerca è la stessa chiamata di `material_for`, non una simile.

- [ ] **Step 4: Le mutazioni**

In `backend/app/services/manual_set.py`, `create_manual_set` diventa:

```python
def create_manual_set(db: Session, *, name: str | None, playlist_ids: list[int]) -> Setlist:
    playlists = []
    for playlist_id in playlist_ids:
        playlist = get_playlist(db, playlist_id)
        if playlist is None:
            raise ManualSetError(f"Playlist {playlist_id} not found")
        playlists.append(playlist)
    clean = (name or "").strip() or (playlists[0].name if playlists else "Set")
    setlist = Setlist(name=clean, kind="manual", generated_by="manual")
    db.add(setlist)
    db.flush()
    for i, playlist in enumerate(playlists, start=1):
        setlist.sources.append(SetlistSource(setlist_id=setlist.id,
                                             playlist_id=playlist.id, position=i))
    record(db, setlist, "create")  # la revisione 0 e' il set vuoto
    db.commit()
    return get_setlist(db, setlist.id)
```

e in fondo al file:

```python
def add_source(db: Session, setlist_id: int, *, expected_revision: int,
               playlist_id: int) -> Setlist:
    """Aggiunge una playlist alle origini, in coda."""
    setlist = load_manual_set(db, setlist_id)
    _check_revision(setlist, expected_revision)
    if get_playlist(db, playlist_id) is None:
        raise ManualSetError(f"Playlist {playlist_id} not found")
    if any(s.playlist_id == playlist_id for s in setlist.sources):
        raise ManualSetError("That playlist is already a source of this set")
    setlist.sources.append(SetlistSource(
        setlist_id=setlist.id, playlist_id=playlist_id,
        position=len(setlist.sources) + 1))
    return _commit_bumped(db, setlist, "sources")


def remove_source(db: Session, setlist_id: int, *, expected_revision: int,
                  playlist_id: int) -> Setlist:
    """Toglie una playlist dalle origini. Il percorso non si tocca: una traccia
    gia' scelta e' una decisione presa, e sparisce dal materiale, non dal set."""
    setlist = load_manual_set(db, setlist_id)
    _check_revision(setlist, expected_revision)
    source = next((s for s in setlist.sources if s.playlist_id == playlist_id), None)
    if source is None:
        raise ManualSetError("That playlist is not a source of this set")
    setlist.sources.remove(source)
    for i, restante in enumerate(setlist.sources, start=1):
        restante.position = i
    return _commit_bumped(db, setlist, "sources")
```

Aggiorna i chiamanti di `create_manual_set` (il router e i test): `playlist_id=X` diventa `playlist_ids=[X]`, `playlist_id=None` diventa `playlist_ids=[]`.

**Sulle origini e l'annulla:** `_commit_bumped` salva uno snapshot, ma `snapshot_of` non conosce le origini, quindi un annulla **non** rimette un'origine tolta. È voluto: lo snapshot copre la struttura del percorso, e le origini sono la provenienza del materiale, non il set. Scrivilo nel docstring di `add_source` così nessuno lo scopre per caso.

- [ ] **Step 5: Esegui, suite, commit**

Run: `cd backend && .venv/bin/python -m pytest tests -q -p no:cacheprovider` → verde.

```bash
git add backend/app/services backend/tests
git commit -m "feat(sets): il materiale pesca da tutte le origini del set"
```

---

### Task 3: API

**Files:**
- Modify: `backend/app/schemas.py`, `backend/app/serializers.py`, `backend/app/routers/sets.py`
- Test: `backend/tests/test_set_manual_api.py` (in coda)

**Interfaces:**
- `POST /api/sets/manual` body `{name?, playlist_ids?}` — `playlist_id` singolo **non è più accettato**
- `POST /api/sets/{id}/sources` body `{expected_revision, playlist_id}` → `ManualSetOut`
- `DELETE /api/sets/{id}/sources/{playlist_id}?expected_revision=N` → `ManualSetOut`
- `GET /api/sets/material?playlist_ids=1&playlist_ids=2&q=&owned=` → `MaterialOut` (la bozza, senza set)
- `ManualSetOut.sources: list[SourceOut]` (`playlist_id`, `name`); `source_playlist_id`/`source_playlist_name` spariscono dal documento

- [ ] **Step 1: Scrivi i test** (in coda a `test_set_manual_api.py`)

```python
def test_origini_multiple_via_http(client_db):
    client, db = client_db
    pl_a, t = _seed(db, n=2)
    pl_b = Playlist(platform="spotify", name="Seconda")
    db.add(pl_b)
    db.flush()
    add_track_to_playlist(db, t[0], pl_b, added_by="test")
    db.commit()

    r = client.post("/api/sets/manual", json={"name": "M", "playlist_ids": [pl_a.id]})
    assert r.status_code == 201, r.text
    doc = r.json()
    assert [s["playlist_id"] for s in doc["sources"]] == [pl_a.id]
    sid = doc["id"]

    r = client.post(f"/api/sets/{sid}/sources",
                    json={"expected_revision": 0, "playlist_id": pl_b.id})
    assert r.status_code == 200, r.text
    assert [s["name"] for s in r.json()["sources"]] == ["Deep", "Seconda"]

    r = client.delete(f"/api/sets/{sid}/sources/{pl_a.id}?expected_revision=1")
    assert r.status_code == 200, r.text
    assert [s["playlist_id"] for s in r.json()["sources"]] == [pl_b.id]

    r = client.delete(f"/api/sets/{sid}/sources/{pl_a.id}?expected_revision=2")
    assert r.status_code == 422


def test_il_materiale_di_una_bozza_via_http(client_db):
    client, db = client_db
    pl, t = _seed(db, n=3)
    r = client.get(f"/api/sets/material?playlist_ids={pl.id}")
    assert r.status_code == 200, r.text
    doc = r.json()
    assert len(doc["items"]) == 3
    assert all(item["in_set"] is False for item in doc["items"])
```

- [ ] **Step 2: Esegui e verifica che falliscano**

Run: `cd backend && .venv/bin/python -m pytest tests/test_set_manual_api.py -q -p no:cacheprovider` → FAIL (404 sulle rotte nuove, `KeyError: 'sources'`).

- [ ] **Step 3: Schemi**

In `backend/app/schemas.py`:

```python
class SourceOut(BaseModel):
    """Una playlist da cui il set pesca. `name` e' None se la playlist e' stata
    cancellata mentre il documento veniva costruito: non capita, ma il client
    non deve rompersi se capita."""

    playlist_id: int
    name: str | None = None


class SourceAddRequest(BaseModel):
    expected_revision: int = Field(ge=0)
    playlist_id: int
```

`ManualSetCreate` cambia:

```python
class ManualSetCreate(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    playlist_ids: list[int] = Field(default_factory=list, max_length=20)
```

`ManualSetOut` perde `source_playlist_id` e `source_playlist_name`, guadagna `sources: list[SourceOut] = []`.

- [ ] **Step 4: Serializer, endpoint**

In `manual_set_out`, al posto della playlist singola:

```python
        sources=[SourceOut(playlist_id=s.playlist_id,
                           name=s.playlist.name if s.playlist is not None else None)
                 for s in setlist.sources],
```

In `backend/app/routers/sets.py`, `create_manual` passa `playlist_ids=req.playlist_ids`, e si aggiungono:

```python
@router.post("/{setlist_id}/sources", response_model=ManualSetOut)
def sources_add(setlist_id: int, req: SourceAddRequest, db: Session = Depends(get_db)):
    """Aggiunge una playlist alle origini del materiale."""
    try:
        return manual_set_out(add_source(
            db, setlist_id, expected_revision=req.expected_revision,
            playlist_id=req.playlist_id), db)
    except ManualSetError as exc:
        raise _manual_error(exc) from exc


@router.delete("/{setlist_id}/sources/{playlist_id}", response_model=ManualSetOut)
def sources_remove(setlist_id: int, playlist_id: int, expected_revision: int = Query(ge=0),
                   db: Session = Depends(get_db)):
    """Toglie un'origine. Il percorso non si tocca."""
    try:
        return manual_set_out(remove_source(
            db, setlist_id, expected_revision=expected_revision,
            playlist_id=playlist_id), db)
    except ManualSetError as exc:
        raise _manual_error(exc) from exc


@router.get("/material", response_model=MaterialOut)
def draft_material(playlist_ids: list[int] = Query(default=[]),
                   q: str | None = Query(default=None, max_length=200),
                   owned: bool = False, db: Session = Depends(get_db)):
    """Il materiale di una BOZZA: il set non esiste ancora (non si crea finche'
    non ci si mette dentro qualcosa), quindi si chiede per playlist."""
    voci = material_for_playlists(db, playlist_ids, q=q, owned=owned)
    return _material_out(db, voci, playlist_ids)
```

**Attenzione all'ordine delle rotte**: `GET /material` va dichiarata **prima** di qualunque `GET /{qualcosa}` che possa catturarla. Oggi non ce n'è (il dettaglio classico è sparito), ma mettila comunque in cima al gruppo e scrivi il perché, così chi aggiunge una rotta a parametro domani non la rompe in silenzio.

**Non esiste un serializer `material_out`**: il router costruisce `MaterialOut` inline (righe ~143-149). Dopo questo task i punti diventano due — il materiale del set e quello della bozza — con otto righe quasi uguali. Estrai un helper e chiamalo da entrambi:

```python
def _material_out(db: Session, voci, playlist_ids: list[int]) -> MaterialOut:
    """Il payload del materiale, uno solo per il set e per la bozza: due copie
    quasi uguali divergono al primo campo nuovo."""
    ft_map = file_tags_for_tracks(db, [t.id for t, _, _, _ in voci])
    fonti = []
    for pid in playlist_ids:
        playlist = get_playlist(db, pid)
        fonti.append(SourceOut(playlist_id=pid,
                               name=playlist.name if playlist is not None else None))
    return MaterialOut(
        sources=fonti,
        items=[MaterialItemOut(track=track_out(t, ft_map.get(t.id)), in_set=in_set,
                               from_playlist=fp, in_reserve=in_res)
               for t, in_set, fp, in_res in voci],
    )
```

`MaterialOut` perde `playlist_id`/`playlist_name` e guadagna `sources: list[SourceOut] = []`.

- [ ] **Step 5: Esegui, suite, commit**

Run: `cd backend && .venv/bin/python -m pytest tests -q -p no:cacheprovider` → verde.

```bash
git add backend/app backend/tests
git commit -m "feat(sets): endpoint delle origini e materiale della bozza"
```

---

### Task 4: Frontend — le origini, e il set che nasce quando serve

**Files:**
- Modify: `frontend/lib/api/{types,manual-sets}.ts`, `frontend/lib/i18n/{en,it}.ts`
- Create: `frontend/components/set-builder/sources-panel.tsx`
- Modify: `frontend/components/set-builder/material-panel.tsx`, `frontend/app/sets/manual/page.tsx`, `frontend/app/sets/page.tsx`
- Test: `frontend/tests/set-builder-sources.test.tsx`, `frontend/tests/set-builder-draft.test.tsx` (nuovi)

**Interfaces:**

```ts
// ManualSet: via source_playlist_id/source_playlist_name, entra sources: Source[]
export interface Source { playlist_id: number; name: string | null }
createManualSet(body: { name?: string; playlist_ids?: number[] }): Promise<ManualSet>
addSource(id, body: { expected_revision: number; playlist_id: number }): Promise<ManualSet>
removeSource(id, playlistId, expectedRevision): Promise<ManualSet>
draftMaterial(opts: { playlist_ids: number[]; q?: string; owned?: boolean }): Promise<Material>
```

**Comportamento della bozza.** `/sets/manual` senza `?id=` non è più un errore: è una bozza. La pagina tiene `setId: number | null` e `draftSources: number[]`. Finché `setId` è `null`:

- il materiale arriva da `draftMaterial(draftSources)`;
- le origini si aggiungono e si tolgono nello stato locale, senza chiamate;
- **il primo gesto che vuole una riga** crea il set con le origini scelte e poi esegue il gesto. Un unico punto: `assicuraSet()`, che restituisce l'id ed è chiamato da `mutate` quando `setId` è `null`.
- appena il set nasce, la pagina aggiorna l'URL con `router.replace` così un ricaricamento non perde più niente.

Se chiudi la pagina senza aver messo niente, non è rimasto niente: è esattamente ciò che l'utente ha chiesto. Un set **già esistente** che svuoti resta dov'è.

- [ ] **Step 1: Testi**

Chiavi nuove sotto `sets.manual` in `en.ts` poi `it.ts`: `sourcesTitle`, `sourcesEmpty`, `addSourceLabel`, `removeSourceTitle`, `draftBadge`, `draftHint`. In `errors`: nessun codice nuovo (le origini usano `manual_set_error`).

Traduzioni italiane: «Da dove pesco», «Nessuna playlist: il materiale è la sola ricerca in libreria.», «Aggiungi una playlist», «Togli questa origine», «bozza», «Il set viene salvato appena ci metti dentro la prima traccia.»

- [ ] **Step 2: Tipi e client** — come da blocco Interfaces sopra, sullo stesso stile dei metodi esistenti in `manual-sets.ts`.

- [ ] **Step 3: Scrivi i test**

`frontend/tests/set-builder-sources.test.tsx`, sulla falsariga di `set-builder-pairs.test.tsx` (stessi mock, `mount()` dentro `PlayerProvider`, fixture con `sources: [{playlist_id: 3, name: "Deep"}]`). Casi:

1. le origini del set compaiono nel pannello del materiale, col loro nome;
2. aggiungere una playlist chiama `addSource` con `expected_revision`;
3. togliere un'origine chiama `removeSource` con la revisione;
4. togliere l'ultima origine non svuota il percorso (la lista delle righe resta).

`frontend/tests/set-builder-draft.test.tsx` — `useSearchParams` restituisce una query **vuota**. Casi:

1. all'apertura non chiama `createManualSet` né `getManualSet`: il materiale arriva da `draftMaterial`;
2. scegliere una playlist nella bozza richiama `draftMaterial` con quel `playlist_ids`, **senza** chiamare `addSource` (non c'è ancora un set);
3. aggiungere la prima traccia chiama `createManualSet` con le origini scelte **e poi** `insertRows` con l'id tornato — asserire l'ordine con `mock.invocationCallOrder`, altrimenti il test passerebbe anche se il set nascesse dopo;
4. dopo la creazione, `router.replace` è stato chiamato con `/sets/manual?id=<id>`;
5. con `?id=7` in query, `createManualSet` non viene chiamato mai (il set c'è già).

- [ ] **Step 4: Componenti e pagina** — `sources-panel.tsx` (`data-testid="sources-panel"`, montato in testa a `material-panel.tsx`), la pagina con `setId`/`draftSources` e `assicuraSet()`, `/sets` che porta a `/sets/manual` senza creare niente.

- [ ] **Step 5: Verifica**

Run: `cd frontend && npm run test:unit -- tests/set-builder-sources.test.tsx tests/set-builder-draft.test.tsx`, poi `npx tsc --noEmit && npm run lint && npm run test:unit && npm run build`.
Attenzione: i fixture dei test già esistenti (`set-builder-workbench`, `-alternatives`, `-blocks`, `-pairs`, `-duration-export`, `-fill`) vanno aggiornati — `source_playlist_id`/`source_playlist_name` diventano `sources` — altrimenti cadono **solo nella suite intera**. È già successo a ogni tappa.

- [ ] **Step 6: Commit**

```bash
git add frontend/lib frontend/components/set-builder frontend/app/sets frontend/tests
git commit -m "feat(frontend): origini multiple e set che nasce alla prima traccia"
```

---

### Task 5: Documentazione e verifica integrata

**Files:**
- Modify: `docs/API.md`, `docs/ARCHITECTURE.md`, `PROGRESS.md`, `frontend/e2e/set-builder.spec.ts`

- [ ] **Step 1: Documentazione**

`docs/API.md`: `playlist_ids` in `POST /api/sets/manual`, i due endpoint delle origini, `GET /api/sets/material` con la ragione per cui esiste (la bozza), `sources` in `ManualSetOut` e in `MaterialOut` al posto della playlist singola.

`docs/ARCHITECTURE.md`: `SetlistSource` come raccordo, la membership **mai copiata**, l'annulla che non copre le origini e perché, e la bozza lato client con il set che nasce al primo gesto.

`PROGRESS.md`: voce datata. Dille chiaramente: un set non si crea più aprendo il banco, e un set già esistente che svuoti **resta** — sono due cose diverse e vanno distinte, o alla prossima lettura sembrerà che l'app cancelli i set vuoti.

- [ ] **Step 2: E2E**

Estendi `frontend/e2e/set-builder.spec.ts` con due test:

1. **La bozza non lascia residui:** conta i set con `GET /api/sets`, apri `/sets/manual` senza id, scegli una playlist, esci senza aggiungere niente, e verifica che il conteggio non sia cambiato. Poi rifallo aggiungendo una traccia: il conteggio sale di uno e l'URL ha `?id=`.
2. **Due origini:** crea due playlist, aprine una bozza con la prima, aggiungi la seconda dal pannello, verifica che il materiale contenga tracce di entrambe.

Run: `cd frontend && npm run test:e2e -- set-builder.spec.ts`

- [ ] **Step 3: Verifica finale**

```bash
cd backend && .venv/bin/python -m pytest tests -q
```

```bash
cd frontend && npm run lint && npm run test:unit && npm run build && npm run test:e2e
```

- [ ] **Step 4: Commit**

```bash
git add docs PROGRESS.md frontend/e2e
git commit -m "docs(sets): origini multiple e bozza del set manuale"
```
