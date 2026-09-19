# Set manuale, tappa 4 (passaggi) — piano di implementazione

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Il DJ guarda il passaggio fra due tracce vicine — quanto pitch serve, che rapporto hanno le tonalità, cosa manca per saperlo — ci scrive un appunto che resta legato a quella coppia di tracce e non alla posizione, e dichiara «la suono a» quando in quel set non suona la traccia al suo tempo originale.

**Architecture:** Una tabella nuova, `SetlistPairNote`, indicizzata per coppia di **track id** (non di righe): il giudizio non si sposta e non si perde quando il percorso cambia. Una colonna nuova, `SetlistTrack.play_bpm`. La compatibilità non si salva mai: è calcolata a ogni lettura in un servizio nuovo, `manual_pairs.py`, che riusa `score_transition` e dichiara i dati mancanti invece di spacciare il punteggio neutro per un giudizio.

**Tech Stack:** Python 3 + FastAPI + SQLAlchemy 2 (SQLite, migrazioni idempotenti in `db.py`), Pydantic v2, pytest. Next.js 16 App Router, React, Tailwind, vitest + @testing-library/react, Playwright.

**Spec:** `docs/superpowers/specs/2026-09-15-set-builder-workbench.md` («Tappa 4 — Passaggi» per il perimetro, sezione 3 per il modello e le regole).

## Global Constraints

- Backend: `cd backend && .venv/bin/python -m pytest tests -q` deve restare verde. Baseline a inizio tappa: **2575 passed, 4 deselected**.
- Frontend baseline: **635 test in 103 file**, `npx tsc --noEmit` pulito, `npm run lint` senza errori (4 warning pre-esistenti non correlati), `npm run build` verde, e2e `set-builder.spec.ts` verde (2 test).
- Migrazioni: solo dentro `ensure_schema` in `backend/app/db.py`, idempotenti. La tabella nuova la crea `create_all`; la colonna nuova la aggiunge `_migrate_add_model_columns`. Nessun rebuild.
- Errori HTTP: sempre `api_error(status, code, message, **params)`; ogni `code` nuovo tradotto in `frontend/lib/i18n/en.ts` **e** `it.ts` sotto `errors`.
- I set `manual` non passano mai da `assign_roles`, `_reassign_roles`, `recompute_transitions`.
- Ogni mutazione controlla `expected_revision`, muta, salva uno snapshot e committa nella stessa transazione. Un conflitto lascia il database intatto.
- Le righe e i blocchi si identificano per id, mai per posizione. Gli appunti di coppia si identificano per **track id**, mai per riga.
- Nessuna chiamata AI: la compatibilità è deterministica, come tutto `services/scoring.py`.
- Frontend: leggere `frontend/CLAUDE.md`. Nessuna stringa user-facing fuori dai dizionari; chiavi in `en.ts` prima, poi `it.ts`. Spazi fra elementi inline: `{" "}` esplicito.
- Commit in italiano, stile `feat(sets): …`, nessun `Co-Authored-By`. Prima di ogni commit `git status --porcelain`, stage dei soli file del task; revertare `frontend/package-lock.json` e `frontend/tsconfig.json` se risultano modificati.

## Decisione di progetto che si discosta dalla spec

La spec dà a `SetlistPairNote` un campo `state` con tre valori (`unreviewed` / `to_try` / `tried`) e un filtro «da provare». **Lo stato non si fa**, per decisione dell'utente (2026-09-19): resta il solo appunto libero per coppia.

La ragione per cui non si tiene neanche mezzo stato: senza `tried`, «da provare» non si chiude mai. Sarebbe una lista di cose da fare che si riempie e non si svuota, cioè rumore. Quindi via il campo, via il filtro, via le etichette. Il modello diventa `(setlist_id, from_track_id, to_track_id, note)` con unicità sulla terna.

Conseguenza sulla verifica dichiarata dalla spec, che va letta senza la parola «stato»: **segno un appunto su A→B; sostituisco B con C: A→C non ha appunto; rimetto B e ritrovo l'appunto di A→B.** È il Task 3 a dimostrarla.

## Cosa questa tappa NON fa

Durata pianificata ed export (tappa 5), «riempi il varco» e la rimozione del vecchio generatore (tappa 6). Il cambio di tonalità indotto dal pitch **resta fuori** per scelta della spec: `play_bpm` cambia il tempo con cui si valutano i vicini, non la `camelot_key`. Nessun ascolto a due piatti: è un cantiere a sé.

---

## File structure

| File | Responsabilità |
|---|---|
| `backend/app/models.py` | `SetlistPairNote`; `SetlistTrack.play_bpm` |
| `backend/app/services/scoring.py` | `pitch_percent`: quanto pitch serve, in percentuale firmata |
| `backend/app/services/manual_pairs.py` (nuovo) | Compatibilità di un passaggio, con i dati mancanti dichiarati |
| `backend/app/services/manual_set.py` | `update_row` (nota + `play_bpm`), `set_pair_note` |
| `backend/app/services/manual_history.py` | Gli appunti di coppia dentro lo snapshot |
| `backend/app/repositories.py` | Ciclo di vita: orfani, non referenziate, `merge_tracks` |
| `backend/app/tools/clean_user_data.py` | `setlist_pair_notes` in `DATA_TABLES` |
| `backend/app/schemas.py`, `backend/app/serializers.py` | `ManualTransitionOut`, `play_bpm`, richieste |
| `backend/app/routers/sets.py` | `PUT /pair-notes`, `play_bpm` nella PATCH di riga |
| `backend/tests/test_set_manual_pairs.py` (nuovo) | Compatibilità, appunti di coppia, `play_bpm` |
| `frontend/components/set-builder/transition-panel.tsx` (nuovo) | Il passaggio in entrata e in uscita dalla riga |
| `frontend/components/set-builder/detail-panel.tsx` | «La suono a» e i due passaggi |
| `frontend/tests/set-builder-pairs.test.tsx` (nuovo) | I gesti della tappa |
| `docs/API.md`, `docs/ARCHITECTURE.md`, `PROGRESS.md`, `docs/ROADMAP.md`, `frontend/e2e/set-builder.spec.ts` | Documentazione e verifica |

---

### Task 1: Il modello, e il ciclo di vita che lo conosce

**Files:**
- Modify: `backend/app/models.py`, `backend/app/repositories.py`, `backend/app/tools/clean_user_data.py`
- Test: `backend/tests/test_set_manual_pairs.py` (nuovo), `backend/tests/test_clean_user_data.py` (in coda), `backend/tests/test_set_manual_lifecycle.py` (in coda)

**Interfaces:**
- Produces: `SetlistPairNote(id, setlist_id, from_track_id, to_track_id, note, setlist)`; `Setlist.pair_notes: list[SetlistPairNote]` (cascade all/delete-orphan); `SetlistTrack.play_bpm: float | None`.

**Perché il ciclo di vita va toccato subito, non alla fine.** `orphan_lead_ids` cancella i lead non su disco che non stanno in nessuna playlist né in nessun set. Un appunto su A→B sopravvive per progetto all'uscita di B dal percorso: se B è un lead senza file, la prima pulizia lo cancellerebbe e l'appunto resterebbe appeso a una traccia che non c'è più — esattamente la promessa che questa tappa fa e che non manterrebbe. Stessa ragione, stesso rimedio delle alternative nella tappa 2.

- [ ] **Step 1: Scrivi i test che falliscono**

`backend/tests/test_set_manual_pairs.py`:

```python
"""Passaggi del set manuale (tappa 4): appunti per coppia e «la suono a»."""
import pytest
from sqlalchemy import select

from app.models import Setlist, SetlistPairNote, SetlistTrack, Track


def _due_tracce(db):
    a = Track(source_type="spotify", title="A", bpm=124.0, camelot_key="8A",
              duration_seconds=300, has_local_file=True)
    b = Track(source_type="spotify", title="B", bpm=126.0, camelot_key="9A",
              duration_seconds=300, has_local_file=True)
    db.add_all([a, b])
    db.commit()
    return a, b


def test_un_appunto_di_coppia_appartiene_al_suo_set(db):
    a, b = _due_tracce(db)
    s = Setlist(name="M", kind="manual")
    db.add(s)
    db.flush()
    db.add(SetlistPairNote(setlist_id=s.id, from_track_id=a.id, to_track_id=b.id,
                           note="entra sul break"))
    db.commit()
    db.refresh(s)
    assert [p.note for p in s.pair_notes] == ["entra sul break"]


def test_cancellare_il_set_cancella_i_suoi_appunti_di_coppia(db):
    a, b = _due_tracce(db)
    s = Setlist(name="M", kind="manual")
    db.add(s)
    db.flush()
    db.add(SetlistPairNote(setlist_id=s.id, from_track_id=a.id, to_track_id=b.id, note="x"))
    db.commit()
    db.delete(s)
    db.commit()
    assert db.scalars(select(SetlistPairNote)).all() == []


def test_la_riga_porta_il_tempo_a_cui_la_suono(db):
    a, _ = _due_tracce(db)
    s = Setlist(name="M", kind="manual")
    db.add(s)
    db.flush()
    riga = SetlistTrack(setlist_id=s.id, position=1, track_id=a.id, play_bpm=126.5)
    db.add(riga)
    db.commit()
    db.refresh(riga)
    assert riga.play_bpm == 126.5
    # Il tempo della traccia non si tocca: `play_bpm` vale in questo set e basta.
    assert a.bpm == 124.0
```

In coda a `backend/tests/test_clean_user_data.py` (aggiungi `SetlistPairNote` all'import da `app.models`):

```python
def test_pulizia_libreria_svuota_anche_gli_appunti_di_coppia(db_su_file):
    """`setlist_pair_notes` e' figlia di `setlists` E di `tracks`: senza di lei
    in DATA_TABLES la DELETE sulle madri va in IntegrityError con le foreign
    key accese."""
    t = Track(source_type="spotify", title="T", has_local_file=True)
    db_su_file.add(t)
    db_su_file.flush()
    s = Setlist(name="M", kind="manual")
    db_su_file.add(s)
    db_su_file.flush()
    db_su_file.add(SetlistPairNote(setlist_id=s.id, from_track_id=t.id,
                                   to_track_id=t.id, note="x"))
    db_su_file.commit()

    report = clean_user_data.clean("library", preserve_tokens=True,
                                   include_backups=False, dry_run=False)

    assert report["after"]["setlists"] == 0
    assert db_su_file.execute(
        text("SELECT COUNT(*) FROM setlist_pair_notes")).scalar_one() == 0
```

In coda a `backend/tests/test_set_manual_lifecycle.py` — è il file che fa già lo stesso lavoro per le alternative (`test_traccia_fra_le_alternative_non_e_orfana`, `test_merge_non_duplica_una_alternativa_gia_presente`): leggilo e segui quei test. Aggiungi `SetlistPairNote` all'import da `app.models`; `orphan_lead_ids`, `unreferenced_track_ids` e `merge_tracks` sono già importati:

```python
def test_un_lead_giudicato_in_un_passaggio_non_e_orfano(db):
    """Un appunto su A->B sopravvive all'uscita di B dal percorso: se la pulizia
    cancellasse B, l'appunto resterebbe appeso al nulla."""
    a = Track(source_type="spotify", title="A", has_local_file=True)
    b = Track(source_type="spotify", title="B")  # lead, niente file
    db.add_all([a, b])
    db.flush()
    s = Setlist(name="M", kind="manual")
    db.add(s)
    db.flush()
    db.add(SetlistPairNote(setlist_id=s.id, from_track_id=a.id, to_track_id=b.id, note="x"))
    db.commit()

    assert b.id not in orphan_lead_ids(db)
    assert b.id not in unreferenced_track_ids(db)


def test_fondere_due_tracce_sposta_gli_appunti_di_coppia(db):
    a = Track(source_type="spotify", title="A", has_local_file=True)
    b = Track(source_type="spotify", title="B", has_local_file=True)
    doppione = Track(source_type="spotify", title="B bis", has_local_file=True)
    db.add_all([a, b, doppione])
    db.flush()
    s = Setlist(name="M", kind="manual")
    db.add(s)
    db.flush()
    db.add(SetlistPairNote(setlist_id=s.id, from_track_id=a.id, to_track_id=doppione.id,
                           note="dal doppione"))
    db.commit()

    merge_tracks(db, keep=b, drop=doppione)
    db.commit()

    righe = db.scalars(select(SetlistPairNote)).all()
    assert [(p.from_track_id, p.to_track_id) for p in righe] == [(a.id, b.id)]


def test_fondere_non_crea_due_appunti_sulla_stessa_coppia(db):
    """Se esistono gia' A->keep e A->drop, dopo la fusione ne resta uno solo:
    la terna (set, from, to) e' unica, e un UPDATE cieco violerebbe l'indice."""
    a = Track(source_type="spotify", title="A", has_local_file=True)
    b = Track(source_type="spotify", title="B", has_local_file=True)
    doppione = Track(source_type="spotify", title="B bis", has_local_file=True)
    db.add_all([a, b, doppione])
    db.flush()
    s = Setlist(name="M", kind="manual")
    db.add(s)
    db.flush()
    db.add_all([
        SetlistPairNote(setlist_id=s.id, from_track_id=a.id, to_track_id=b.id, note="tengo"),
        SetlistPairNote(setlist_id=s.id, from_track_id=a.id, to_track_id=doppione.id, note="cade"),
    ])
    db.commit()

    merge_tracks(db, keep=b, drop=doppione)
    db.commit()

    righe = db.scalars(select(SetlistPairNote)).all()
    assert [p.note for p in righe] == ["tengo"]
```

- [ ] **Step 2: Esegui e verifica che falliscano**

Run: `cd backend && .venv/bin/python -m pytest tests/test_set_manual_pairs.py tests/test_clean_user_data.py tests/test_set_manual_lifecycle.py -q -p no:cacheprovider`
Expected: FAIL con `ImportError: cannot import name 'SetlistPairNote'`.

- [ ] **Step 3: Il modello**

In `backend/app/models.py`, dentro `class SetlistTrack`, accanto a `note`:

```python
    # "La suono a": il tempo a cui il DJ suona QUESTA traccia in QUESTO set.
    # Non tocca `Track.bpm`, che resta il dato della traccia; serve a valutare
    # i vicini sul tempo vero di cabina (spec 2026-09-15, sezione 3).
    play_bpm: Mapped[float | None] = mapped_column(Float)
```

fra le relazioni di `Setlist`, accanto a `revisions`:

```python
    pair_notes: Mapped[list["SetlistPairNote"]] = relationship(
        back_populates="setlist", cascade="all, delete-orphan",
    )
```

e dopo `class SetlistRevision`:

```python
class SetlistPairNote(Base):
    """Appunto su un passaggio: dalla traccia `from` alla traccia `to`.

    La chiave sono le TRACCE, non le righe: il giudizio non si trasferisce e non
    si perde. Se dopo A finisce C, la coppia A->C semplicemente non ha riga qui;
    se si rimette B, l'appunto su A->B torna a galla da solo. La tappa 4 non ha
    stato ("provato" e' stato tolto, 2026-09-19): resta il solo testo.
    """

    __tablename__ = "setlist_pair_notes"
    __table_args__ = (
        UniqueConstraint("setlist_id", "from_track_id", "to_track_id",
                         name="uq_pair_note_per_coppia"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    setlist_id: Mapped[int] = mapped_column(ForeignKey("setlists.id"), index=True)
    from_track_id: Mapped[int] = mapped_column(ForeignKey("tracks.id"), index=True)
    to_track_id: Mapped[int] = mapped_column(ForeignKey("tracks.id"), index=True)
    note: Mapped[str | None] = mapped_column(Text)

    setlist: Mapped[Setlist] = relationship(back_populates="pair_notes")
```

`UniqueConstraint` va aggiunta all'import da `sqlalchemy` in cima al file, accanto a `Table`.

In `backend/app/tools/clean_user_data.py`, `DATA_TABLES` guadagna `"setlist_pair_notes"` subito dopo `"setlist_revisions"` (figlie prima delle madri).

- [ ] **Step 4: Il ciclo di vita**

In `backend/app/repositories.py`, aggiungi `SetlistPairNote` all'import da `app.models` (riga 11) e, **in entrambe** `orphan_lead_ids` (~riga 620) e `unreferenced_track_ids` (~riga 775), subito sotto la clausola delle alternative:

```python
        # Un appunto su un passaggio e' un giudizio del DJ su DUE tracce, e
        # sopravvive per progetto all'uscita di una delle due dal percorso:
        # senza queste due clausole la pulizia cancellerebbe la traccia e
        # lascerebbe l'appunto appeso al nulla.
        Track.id.not_in(select(SetlistPairNote.from_track_id)),
        Track.id.not_in(select(SetlistPairNote.to_track_id)),
```

In `merge_tracks`, subito dopo il blocco che sposta le alternative:

```python
    # Appunti di coppia: prima cadono quelli che duplicherebbero una coppia gia'
    # esistente su keep (la terna e' unica), poi gli altri si ripuntano.
    da_tenere = select(SetlistPairNote.setlist_id, SetlistPairNote.from_track_id,
                       SetlistPairNote.to_track_id)
    esistenti = {tuple(r) for r in db.execute(da_tenere).all()}
    for nota in db.scalars(select(SetlistPairNote).where(
            (SetlistPairNote.from_track_id == drop.id)
            | (SetlistPairNote.to_track_id == drop.id))).all():
        nuova = (nota.setlist_id,
                 keep.id if nota.from_track_id == drop.id else nota.from_track_id,
                 keep.id if nota.to_track_id == drop.id else nota.to_track_id)
        if nuova in esistenti:
            db.delete(nota)
            continue
        esistenti.add(nuova)
        nota.from_track_id, nota.to_track_id = nuova[1], nuova[2]
    db.flush()
```

- [ ] **Step 5: Esegui e verifica che passino**

Run: `cd backend && .venv/bin/python -m pytest tests/test_set_manual_pairs.py tests/test_clean_user_data.py tests/test_set_manual_lifecycle.py -q -p no:cacheprovider` → verdi.

Poi dimostra che mordono: togli le due clausole `SetlistPairNote` da `orphan_lead_ids` e verifica che `test_un_lead_giudicato_in_un_passaggio_non_e_orfano` fallisca; rimettile.

- [ ] **Step 6: Suite completa e commit**

Run: `cd backend && .venv/bin/python -m pytest tests -q -p no:cacheprovider` → 2582 passed (2575 + 3 del file nuovo + 1 di pulizia + 3 di ciclo di vita).

```bash
git add backend/app/models.py backend/app/repositories.py backend/app/tools/clean_user_data.py backend/tests/test_set_manual_pairs.py backend/tests/test_clean_user_data.py backend/tests/test_set_manual_lifecycle.py
git commit -m "feat(sets): appunti di coppia e «la suono a» nel modello del set manuale"
```

---

### Task 2: Quanto pitch serve, e la compatibilità di un passaggio

**Files:**
- Modify: `backend/app/services/scoring.py`
- Create: `backend/app/services/manual_pairs.py`
- Test: `backend/tests/test_scoring.py` (in coda), `backend/tests/test_set_manual_pairs.py` (in coda)

**Interfaces:**
- Produces:

```python
# scoring.py
def pitch_percent(from_bpm: float, to_bpm: float) -> tuple[float, bool]
    """Quanto pitch serve per portare `to_bpm` sulla griglia di `from_bpm`, in
    percentuale FIRMATA e arrotondata a un decimale, più un flag che dice se
    l'allineamento migliore e' a mezzo/doppio tempo."""

# manual_pairs.py
@dataclass(frozen=True)
class PairCompat:
    bpm_from: float | None      # il tempo usato: play_bpm se c'e', altrimenti Track.bpm
    bpm_to: float | None
    bpm_percent: float | None   # None se manca un BPM
    halftime: bool
    key_from: str | None
    key_to: str | None
    key_relation: str           # same | same_number | adjacent | weak | unknown
    score: int | None           # None se manca anche un solo dato
    missing: list[str]          # "bpm" e/o "key"

def pair_compat(from_row: SetlistTrack, to_row: SetlistTrack) -> PairCompat
def bpm_of(row: SetlistTrack) -> float | None
```

- [ ] **Step 1: Scrivi i test che falliscono**

In coda a `backend/tests/test_scoring.py` (importa `pitch_percent` dalla riga di import di `app.services.scoring` già presente):

```python
def test_il_pitch_e_una_percentuale_firmata():
    # L'esempio della spec: "124 -> 123, -0,8 %".
    assert pitch_percent(124.0, 123.0) == (-0.8, False)
    assert pitch_percent(124.0, 126.0) == (1.6, False)
    assert pitch_percent(128.0, 128.0) == (0.0, False)


def test_il_pitch_si_misura_sulla_griglia_allineata():
    """A mezzo/doppio tempo il pitch che serve non e' la differenza secca: da 140
    a 70 non si pitcha del -50 %, si suona 70 a griglia doppia e il pitch e' 0."""
    percento, piegato = pitch_percent(140.0, 70.0)
    assert piegato is True
    assert percento == 0.0
    percento, piegato = pitch_percent(140.0, 69.0)
    assert piegato is True
    assert percento == pytest.approx(-1.4, abs=0.05)
```

In coda a `backend/tests/test_set_manual_pairs.py`:

```python
from app.services.manual_pairs import bpm_of, pair_compat


def _riga(track=None, play_bpm=None, slot_kind="track"):
    return SetlistTrack(position=1, track=track, play_bpm=play_bpm, slot_kind=slot_kind)


def test_la_compatibilita_dice_pitch_e_tonalita(db):
    a, b = _due_tracce(db)          # 124 8A -> 126 9A
    c = pair_compat(_riga(a), _riga(b))
    assert (c.bpm_from, c.bpm_to) == (124.0, 126.0)
    assert c.bpm_percent == 1.6
    assert c.halftime is False
    assert c.key_relation == "adjacent"
    assert c.missing == []
    assert isinstance(c.score, int)


def test_un_dato_mancante_si_dichiara_invece_di_valere_neutro(db):
    """La spec lo chiede per nome: con BPM o tonalita' mancanti si mostra
    «sconosciuto», non il punteggio neutro che `score_transition` darebbe."""
    a, _ = _due_tracce(db)
    senza = Track(source_type="spotify", title="X", duration_seconds=300, has_local_file=True)
    db.add(senza)
    db.commit()
    c = pair_compat(_riga(a), _riga(senza))
    assert c.score is None
    assert sorted(c.missing) == ["bpm", "key"]
    assert c.bpm_percent is None
    assert c.key_relation == "unknown"


def test_la_suono_a_batte_il_bpm_della_traccia(db):
    a, b = _due_tracce(db)          # 124 -> 126
    assert bpm_of(_riga(a)) == 124.0
    assert bpm_of(_riga(a, play_bpm=126.0)) == 126.0
    # Portate allo stesso tempo, il pitch che serve e' zero.
    c = pair_compat(_riga(a, play_bpm=126.0), _riga(b))
    assert c.bpm_from == 126.0
    assert c.bpm_percent == 0.0


def test_un_varco_non_ha_compatibilita(db):
    """Regola della spec: finche' il varco e' aperto, le tracce ai suoi lati non
    sono vicine. Chi calcola non deve nemmeno essere chiamato: qui si verifica
    che una riga senza traccia non produca numeri inventati."""
    a, _ = _due_tracce(db)
    c = pair_compat(_riga(a), _riga(None, slot_kind="gap"))
    assert c.score is None
    assert sorted(c.missing) == ["bpm", "key"]
```

- [ ] **Step 2: Esegui e verifica che falliscano**

Run: `cd backend && .venv/bin/python -m pytest tests/test_scoring.py tests/test_set_manual_pairs.py -q -p no:cacheprovider`
Expected: FAIL con `ImportError` su `pitch_percent` e `ModuleNotFoundError: app.services.manual_pairs`.

- [ ] **Step 3: `pitch_percent`**

In `backend/app/services/scoring.py`, subito sotto `effective_bpm_diff`:

```python
def pitch_percent(from_bpm: float, to_bpm: float) -> tuple[float, bool]:
    """Quanto pitch serve per portare `to_bpm` sulla griglia di `from_bpm`.

    Firmata (negativa = rallentare) e in percentuale, non in BPM secchi: e' il
    numero che si legge sul fader, e a 90 o a 170 la stessa differenza assoluta
    non e' affatto lo stesso gesto. Il secondo valore dice se l'allineamento
    migliore e' a mezzo/doppio tempo, nel qual caso la percentuale e' gia'
    calcolata su quella griglia (140 -> 70 e' 0 %, non -50 %).
    """
    candidati = ((to_bpm, False), (to_bpm * 2, True), (to_bpm / 2, True))
    allineato, piegato = min(candidati, key=lambda c: abs(c[0] - from_bpm))
    return round((allineato - from_bpm) / from_bpm * 100, 1), piegato
```

- [ ] **Step 4: `manual_pairs.py`**

```python
# backend/app/services/manual_pairs.py
"""Compatibilita' tecnica di un passaggio del set manuale (tappa 4).

Non si salva niente: si calcola a ogni lettura dai metadati correnti. La regola
che governa tutto il modulo e' della spec: con un dato mancante si DICHIARA che
manca, non si mostra il punteggio neutro che `score_transition` restituirebbe —
un 50 su una traccia senza BPM sembra un giudizio e non lo e'.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.models import SetlistTrack
from app.services.camelot import parse_camelot
from app.services.scoring import pitch_percent, score_transition


@dataclass(frozen=True)
class PairCompat:
    bpm_from: float | None = None
    bpm_to: float | None = None
    bpm_percent: float | None = None
    halftime: bool = False
    key_from: str | None = None
    key_to: str | None = None
    key_relation: str = "unknown"
    score: int | None = None
    missing: list[str] = field(default_factory=list)


def bpm_of(row: SetlistTrack) -> float | None:
    """Il tempo a cui questa riga suona: «la suono a» se c'e', altrimenti quello
    della traccia. `play_bpm` vale in questo set e non tocca la libreria."""
    if row.play_bpm:
        return row.play_bpm
    return row.track.bpm if row.track is not None else None


def _relation(from_key: str | None, to_key: str | None) -> str:
    a, b = parse_camelot(from_key), parse_camelot(to_key)
    if a is None or b is None:
        return "unknown"
    if a == b:
        return "same"
    num_a, let_a = a
    num_b, let_b = b
    if num_a == num_b:
        return "same_number"
    if min((num_a - num_b) % 12, (num_b - num_a) % 12) == 1 and let_a == let_b:
        return "adjacent"
    return "weak"


def pair_compat(from_row: SetlistTrack, to_row: SetlistTrack) -> PairCompat:
    bpm_from, bpm_to = bpm_of(from_row), bpm_of(to_row)
    key_from = from_row.track.camelot_key if from_row.track is not None else None
    key_to = to_row.track.camelot_key if to_row.track is not None else None

    missing: list[str] = []
    if not bpm_from or not bpm_to:
        missing.append("bpm")
    relation = _relation(key_from, key_to)
    if relation == "unknown":
        missing.append("key")

    percento, piegato = (None, False)
    if "bpm" not in missing:
        percento, piegato = pitch_percent(bpm_from, bpm_to)

    score = None
    if not missing and from_row.track is not None and to_row.track is not None:
        # `score_transition` legge i BPM dalla traccia: «la suono a» va fatto
        # valere senza toccare gli oggetti caricati, che finirebbero al flush.
        score = score_transition(
            _AlTempoDi(from_row.track, bpm_from), _AlTempoDi(to_row.track, bpm_to)
        ).score

    return PairCompat(
        bpm_from=bpm_from, bpm_to=bpm_to, bpm_percent=percento, halftime=piegato,
        key_from=key_from, key_to=key_to, key_relation=relation,
        score=score, missing=missing,
    )


class _AlTempoDi:
    """La traccia vista al tempo di cabina. Delega tutto alla vera `Track` e
    sovrascrive il solo `bpm`: assegnarlo sull'oggetto caricato lo scriverebbe
    in libreria al primo flush, che e' esattamente cio' che `play_bpm` evita.
    """

    def __init__(self, track, bpm: float) -> None:
        self._track = track
        self.bpm = bpm

    def __getattr__(self, nome: str):
        return getattr(self._track, nome)
```

- [ ] **Step 5: Esegui e verifica**

Run: `cd backend && .venv/bin/python -m pytest tests/test_scoring.py tests/test_set_manual_pairs.py -q -p no:cacheprovider` → verdi.

Poi dimostra che il tempo di cabina non sporca la libreria: in una sessione `python -c`, carica una traccia, chiama `pair_compat` con `play_bpm` diverso, fai `db.commit()` e rileggi `Track.bpm` — deve essere invariato. Se hai dovuto scrivere `from_row.track.bpm = …` da qualche parte, è il difetto che questo passaggio cerca.

- [ ] **Step 6: Suite completa e commit**

```bash
git add backend/app/services/scoring.py backend/app/services/manual_pairs.py backend/tests/test_scoring.py backend/tests/test_set_manual_pairs.py
git commit -m "feat(sets): il pitch in percentuale e la compatibilità di un passaggio"
```

---

### Task 3: Le mutazioni — appunto di coppia e «la suono a»

**Files:**
- Modify: `backend/app/services/manual_set.py`, `backend/app/services/manual_history.py`
- Test: `backend/tests/test_set_manual_pairs.py` (in coda)

**Interfaces:**
- Consumes: Task 1 (`SetlistPairNote`, `play_bpm`), tappa 3 (`_commit_bumped(db, setlist, kind)`, `record`, `restore`).
- Produces:

```python
UNSET: object   # sentinella: "campo non toccato", diverso da None = "azzera"

def update_row(db, setlist_id, row_id, *, expected_revision,
               note: str | None | object = UNSET,
               play_bpm: float | None | object = UNSET) -> Setlist
def update_row_note(db, setlist_id, row_id, *, expected_revision, note) -> Setlist  # resta, delega
def set_pair_note(db, setlist_id, *, expected_revision, from_track_id: int,
                  to_track_id: int, note: str | None) -> Setlist
def pair_note_map(setlist) -> dict[tuple[int, int], str]
```

Lo snapshot della cronologia guadagna gli appunti di coppia, così annullare li riporta indietro come tutto il resto.

- [ ] **Step 1: Scrivi i test che falliscono**

In coda a `backend/tests/test_set_manual_pairs.py`:

```python
from app.services.manual_set import (
    create_manual_set, insert_rows, path_rows, pair_note_map, set_pair_note, undo,
    update_row, update_row_note,
)


def _set_con_due(db):
    a, b = _due_tracce(db)
    s = create_manual_set(db, name="M", playlist_id=None)
    s = insert_rows(db, s.id, expected_revision=0, track_ids=[a.id, b.id],
                    gap=False, after_row_id=None)
    return s, a, b


def test_l_appunto_di_coppia_si_scrive_e_si_rilegge(db):
    s, a, b = _set_con_due(db)
    s = set_pair_note(db, s.id, expected_revision=1, from_track_id=a.id,
                      to_track_id=b.id, note="  entra sul break  ")
    assert pair_note_map(s) == {(a.id, b.id): "entra sul break"}


def test_un_appunto_vuoto_toglie_la_riga(db):
    """Niente righe vuote in giro: svuotare il campo e' cancellare l'appunto."""
    s, a, b = _set_con_due(db)
    s = set_pair_note(db, s.id, expected_revision=1, from_track_id=a.id,
                      to_track_id=b.id, note="x")
    s = set_pair_note(db, s.id, expected_revision=2, from_track_id=a.id,
                      to_track_id=b.id, note="   ")
    assert pair_note_map(s) == {}


def test_riscrivere_la_stessa_coppia_non_crea_un_doppione(db):
    s, a, b = _set_con_due(db)
    s = set_pair_note(db, s.id, expected_revision=1, from_track_id=a.id,
                      to_track_id=b.id, note="primo")
    s = set_pair_note(db, s.id, expected_revision=2, from_track_id=a.id,
                      to_track_id=b.id, note="secondo")
    assert pair_note_map(s) == {(a.id, b.id): "secondo"}


def test_il_giudizio_non_si_trasferisce_e_non_si_perde(db):
    """La verifica dichiarata dalla spec, senza la parola «stato»: scrivo su
    A->B, sostituisco B con C e A->C non ha appunto; rimetto B e lo ritrovo."""
    s, a, b = _set_con_due(db)
    c = Track(source_type="spotify", title="C", bpm=125.0, camelot_key="8A",
              duration_seconds=300, has_local_file=True)
    db.add(c)
    db.commit()
    s = set_pair_note(db, s.id, expected_revision=1, from_track_id=a.id,
                      to_track_id=b.id, note="entra sul break")

    riga_b = path_rows(s)[1]
    from app.services.manual_set import add_alternatives, choose_alternative
    s = add_alternatives(db, s.id, riga_b.id, expected_revision=2, track_ids=[c.id])
    s = choose_alternative(db, s.id, riga_b.id,
                           path_rows(s)[1].alternatives[0].id, expected_revision=3)
    assert [r.track_id for r in path_rows(s)] == [a.id, c.id]
    assert (a.id, c.id) not in pair_note_map(s)      # A->C e' da valutare
    assert pair_note_map(s)[(a.id, b.id)] == "entra sul break"  # non persa

    riga_c = path_rows(s)[1]
    s = choose_alternative(db, s.id, riga_c.id,
                           path_rows(s)[1].alternatives[0].id, expected_revision=4)
    assert [r.track_id for r in path_rows(s)] == [a.id, b.id]
    assert pair_note_map(s)[(a.id, b.id)] == "entra sul break"  # ritrovata


def test_la_suono_a_si_scrive_sulla_riga(db):
    s, a, b = _set_con_due(db)
    riga = path_rows(s)[0]
    s = update_row(db, s.id, riga.id, expected_revision=1, play_bpm=126.0)
    assert path_rows(s)[0].play_bpm == 126.0
    assert a.bpm == 124.0  # la libreria non si tocca


def test_scrivere_l_appunto_non_azzera_la_suono_a(db):
    """Il difetto classico di una PATCH parziale: un campo non mandato non e'
    un campo da azzerare. Senza sentinella questo test cade."""
    s, a, b = _set_con_due(db)
    riga = path_rows(s)[0]
    s = update_row(db, s.id, riga.id, expected_revision=1, play_bpm=126.0)
    s = update_row(db, s.id, riga.id, expected_revision=2, note="ciao")
    assert path_rows(s)[0].play_bpm == 126.0
    assert path_rows(s)[0].note == "ciao"
    # E azzerare resta possibile, esplicitamente.
    s = update_row(db, s.id, riga.id, expected_revision=3, play_bpm=None)
    assert path_rows(s)[0].play_bpm is None


def test_annullare_riporta_indietro_un_appunto_di_coppia(db):
    s, a, b = _set_con_due(db)
    s = set_pair_note(db, s.id, expected_revision=1, from_track_id=a.id,
                      to_track_id=b.id, note="x")
    s = undo(db, s.id, expected_revision=2)
    assert pair_note_map(s) == {}
```

- [ ] **Step 2: Esegui e verifica che falliscano**

Run: `cd backend && .venv/bin/python -m pytest tests/test_set_manual_pairs.py -q -p no:cacheprovider`
Expected: FAIL con `ImportError` su `set_pair_note`.

- [ ] **Step 3: Gli appunti di coppia nello snapshot**

In `backend/app/services/manual_history.py`, importa `SetlistPairNote` da `app.models` e aggiungi a `snapshot_of`, dopo `"alts"`:

```python
        # Gli appunti di coppia stanno nella struttura come le note di riga: un
        # annulla che li lasciasse fuori riporterebbe indietro mezzo set.
        "pairs": [
            {"id": p.id, "from_track_id": p.from_track_id,
             "to_track_id": p.to_track_id, "note": p.note}
            for p in sorted(setlist.pair_notes, key=lambda p: p.id)
        ],
```

e a `restore`, insieme alle altre cancellazioni (`setlist.pair_notes.clear()` accanto a `setlist.tracks.clear()`) e, dopo il blocco che ricrea le alternative:

```python
    for p in snapshot.get("pairs", []):
        db.add(SetlistPairNote(id=p["id"], setlist_id=setlist.id,
                               from_track_id=p["from_track_id"],
                               to_track_id=p["to_track_id"], note=p["note"]))
    db.flush()
```

- [ ] **Step 4: Le mutazioni**

In `backend/app/services/manual_set.py`, importa `SetlistPairNote` da `app.models` e sostituisci `update_row_note` con:

```python
class _Unset:
    """Sentinella per le PATCH parziali: «campo non mandato» non e' «campo da
    azzerare», e None deve poter azzerare davvero."""

    def __repr__(self) -> str:  # pragma: no cover - solo per i messaggi d'errore
        return "UNSET"


UNSET = _Unset()


def update_row(db: Session, setlist_id: int, row_id: int, *, expected_revision: int,
               note: str | None | _Unset = UNSET,
               play_bpm: float | None | _Unset = UNSET) -> Setlist:
    """Aggiorna i campi MANDATI della riga. «La suono a» vale in questo set e
    non tocca `Track.bpm`."""
    setlist = load_manual_set(db, setlist_id)
    _check_revision(setlist, expected_revision)
    row = _row_of(setlist, row_id)
    if not isinstance(note, _Unset):
        row.note = (note or "").strip() or None
    if not isinstance(play_bpm, _Unset):
        if play_bpm is not None and not 20.0 <= play_bpm <= 300.0:
            raise ManualSetError(f"Play BPM {play_bpm} out of range 20..300")
        row.play_bpm = play_bpm
    return _commit_bumped(db, setlist, f"note:{row.id}")


def update_row_note(db: Session, setlist_id: int, row_id: int, *, expected_revision: int,
                    note: str | None) -> Setlist:
    """Compatibilita' con le tappe 1-3: la sola nota."""
    return update_row(db, setlist_id, row_id, expected_revision=expected_revision, note=note)
```

e, in fondo al file:

```python
# --- Passaggi (tappa 4) --------------------------------------------------------


def pair_note_map(setlist: Setlist) -> dict[tuple[int, int], str]:
    """Gli appunti del set indicizzati per coppia di tracce."""
    return {(p.from_track_id, p.to_track_id): p.note
            for p in setlist.pair_notes if p.note}


def set_pair_note(db: Session, setlist_id: int, *, expected_revision: int,
                  from_track_id: int, to_track_id: int, note: str | None) -> Setlist:
    """Scrive l'appunto sul passaggio fra due TRACCE (non fra due righe: il
    giudizio non si sposta col percorso). Un testo vuoto cancella la riga:
    niente appunti vuoti da collezionare."""
    setlist = load_manual_set(db, setlist_id)
    _check_revision(setlist, expected_revision)
    for tid in (from_track_id, to_track_id):
        if get_track(db, tid) is None:
            raise ManualSetError(f"Track {tid} not found")
    pulita = (note or "").strip() or None
    esistente = next((p for p in setlist.pair_notes
                      if p.from_track_id == from_track_id and p.to_track_id == to_track_id), None)
    if pulita is None:
        if esistente is not None:
            setlist.pair_notes.remove(esistente)
    elif esistente is not None:
        esistente.note = pulita
    else:
        setlist.pair_notes.append(SetlistPairNote(
            setlist_id=setlist.id, from_track_id=from_track_id,
            to_track_id=to_track_id, note=pulita))
    return _commit_bumped(db, setlist, f"pair:{from_track_id}:{to_track_id}")
```

Nota su `kind`: `f"pair:…"` **non** inizia con `note:` e quindi non si accorpa. È voluto per ora — ogni salvataggio dell'appunto di coppia è una revisione. Se durante la prova risultasse fastidioso (il campo salva al blur, non a ogni carattere, quindi non dovrebbe), la riga da cambiare è `MERGEABLE` in `manual_history.py`.

- [ ] **Step 5: Esegui e verifica**

Run: `cd backend && .venv/bin/python -m pytest tests/test_set_manual_pairs.py tests/test_set_manual_history.py tests/test_set_manual_service.py tests/test_set_manual_blocks.py -q -p no:cacheprovider` → verdi.

Poi dimostra che la sentinella morde: in `update_row`, sostituisci `if not isinstance(note, _Unset):` con `if True:` e verifica che `test_scrivere_l_appunto_non_azzera_la_suono_a` **non** basti da solo a intercettarlo (azzera la nota, non il `play_bpm`); poi fallo su `play_bpm` e verifica che il test fallisca. Ripristina.

Run: `cd backend && .venv/bin/python -m pytest tests -q -p no:cacheprovider` → verde.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/manual_set.py backend/app/services/manual_history.py backend/tests/test_set_manual_pairs.py
git commit -m "feat(sets): l'appunto sul passaggio e il tempo di cabina della riga"
```

---

### Task 4: API

**Files:**
- Modify: `backend/app/schemas.py`, `backend/app/serializers.py`, `backend/app/routers/sets.py`
- Test: `backend/tests/test_set_manual_api.py` (in coda)

**Interfaces:**
- Produces (HTTP):
  - `PUT /api/sets/{id}/pair-notes` body `{expected_revision, from_track_id, to_track_id, note}` → `ManualSetOut`
  - `PATCH /api/sets/{id}/rows/{row_id}` accetta ora anche `play_bpm` (20–300, `null` azzera); i campi non mandati non si toccano
  - `ManualRowOut` guadagna `play_bpm`; `ManualSetOut` guadagna `transitions: list[ManualTransitionOut]`
  - Codice errore nuovo: nessuno — traccia inesistente e `play_bpm` fuori scala cadono in `422 manual_set_error`

`ManualTransitionOut` esce **solo** per le coppie di righe `track` consecutive del percorso (varchi esclusi: regola della spec) e attraversa i confini fra sequenze, perché in cabina quelle due tracce si susseguono davvero.

- [ ] **Step 1: Scrivi i test** (in coda a `backend/tests/test_set_manual_api.py`)

```python
def test_passaggi_e_appunti_di_coppia_via_http(client_db):
    client, db = client_db
    _, t = _seed(db, n=3)   # T0/T1 hanno bpm 124; T2 e' senza file ma con bpm
    sid = client.post("/api/sets/manual", json={"name": "M"}).json()["id"]
    doc = client.post(f"/api/sets/{sid}/rows",
                      json={"expected_revision": 0, "track_ids": [t[0].id, t[1].id]}).json()
    assert len(doc["transitions"]) == 1
    passaggio = doc["transitions"][0]
    assert passaggio["from_track_id"] == t[0].id and passaggio["to_track_id"] == t[1].id
    assert passaggio["bpm_percent"] == 0.0        # stesso tempo: niente pitch
    assert passaggio["note"] is None

    r = client.put(f"/api/sets/{sid}/pair-notes", json={
        "expected_revision": 1, "from_track_id": t[0].id, "to_track_id": t[1].id,
        "note": "entra sul break"})
    assert r.status_code == 200, r.text
    assert r.json()["transitions"][0]["note"] == "entra sul break"

    r = client.put(f"/api/sets/{sid}/pair-notes", json={
        "expected_revision": 2, "from_track_id": 999999, "to_track_id": t[1].id, "note": "x"})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "manual_set_error"


def test_un_varco_spezza_il_passaggio(client_db):
    """Regola della spec: finche' il varco e' aperto, le tracce ai suoi lati non
    sono vicine e nessuna compatibilita' si calcola fra loro."""
    client, db = client_db
    _, t = _seed(db, n=2)
    sid = client.post("/api/sets/manual", json={"name": "M"}).json()["id"]
    doc = client.post(f"/api/sets/{sid}/rows",
                      json={"expected_revision": 0, "track_ids": [t[0].id, t[1].id]}).json()
    prima = _rows(doc)[0]
    doc = client.post(f"/api/sets/{sid}/rows", json={
        "expected_revision": 1, "gap": True, "after_row_id": prima["id"]}).json()
    assert doc["transitions"] == []


def test_la_suono_a_via_http_e_la_patch_parziale(client_db):
    client, db = client_db
    _, t = _seed(db, n=2)
    sid = client.post("/api/sets/manual", json={"name": "M"}).json()["id"]
    doc = client.post(f"/api/sets/{sid}/rows",
                      json={"expected_revision": 0, "track_ids": [t[0].id, t[1].id]}).json()
    riga = _rows(doc)[0]["id"]

    r = client.patch(f"/api/sets/{sid}/rows/{riga}",
                     json={"expected_revision": 1, "play_bpm": 130})
    assert r.status_code == 200, r.text
    assert _rows(r.json())[0]["play_bpm"] == 130.0
    # 124 -> 130 sul primo, il secondo resta a 124: serve pitch all'indietro.
    assert r.json()["transitions"][0]["bpm_from"] == 130.0

    r = client.patch(f"/api/sets/{sid}/rows/{riga}",
                     json={"expected_revision": 2, "note": "solo la nota"})
    assert _rows(r.json())[0]["play_bpm"] == 130.0   # non azzerato dalla PATCH parziale
    assert _rows(r.json())[0]["note"] == "solo la nota"

    r = client.patch(f"/api/sets/{sid}/rows/{riga}",
                     json={"expected_revision": 3, "play_bpm": 999})
    assert r.status_code == 422
```

- [ ] **Step 2: Esegui e verifica che falliscano**

Run: `cd backend && .venv/bin/python -m pytest tests/test_set_manual_api.py -q -p no:cacheprovider` → FAIL (`KeyError: 'transitions'`, 405/404 sulla PUT).

- [ ] **Step 3: Schemi**

In `backend/app/schemas.py`, accanto agli altri del set manuale:

```python
class ManualTransitionOut(BaseModel):
    """Il passaggio fra due righe `track` vicine. Calcolato a ogni lettura, mai
    salvato; `score` e `bpm_percent` sono `None` quando un dato manca, e
    `missing` dice quale — «sconosciuto», non un punteggio neutro."""

    from_row_id: int
    to_row_id: int
    from_track_id: int
    to_track_id: int
    bpm_from: float | None = None
    bpm_to: float | None = None
    bpm_percent: float | None = None
    halftime: bool = False
    key_from: str | None = None
    key_to: str | None = None
    key_relation: Literal["same", "same_number", "adjacent", "weak", "unknown"] = "unknown"
    score: int | None = None
    missing: list[str] = []
    note: str | None = None


class PairNoteRequest(BaseModel):
    expected_revision: int = Field(ge=0)
    from_track_id: int
    to_track_id: int
    note: str | None = Field(default=None, max_length=2000)
```

`ManualRowOut` guadagna, dopo `note`:

```python
    play_bpm: float | None = None  # "la suono a": vale in questo set, non in libreria
```

`ManualSetOut` guadagna, dopo `reserve`:

```python
    transitions: list[ManualTransitionOut] = []
```

`RowPatchRequest` guadagna:

```python
    play_bpm: float | None = Field(default=None, ge=20, le=300)
```

- [ ] **Step 4: Serializer**

In `backend/app/serializers.py`, aggiungi `ManualTransitionOut` al blocco di import da `app.schemas` (riga 9), importa `pair_note_map, path_rows` da `app.services.manual_set` e `pair_compat` da `app.services.manual_pairs`, aggiungi `play_bpm=st.play_bpm` dentro `row_out`, e prima del `return`:

```python
    # I passaggi: solo fra righe con traccia e consecutive NEL PERCORSO. Un
    # varco aperto spezza la coppia (regola della spec), mentre il confine fra
    # due sequenze no: in cabina quelle due tracce si susseguono davvero.
    note_coppie = pair_note_map(setlist)
    transitions = []
    percorso = path_rows(setlist)
    for prima, dopo in zip(percorso, percorso[1:]):
        if prima.track is None or dopo.track is None:
            continue
        c = pair_compat(prima, dopo)
        transitions.append(ManualTransitionOut(
            from_row_id=prima.id, to_row_id=dopo.id,
            from_track_id=prima.track_id, to_track_id=dopo.track_id,
            bpm_from=c.bpm_from, bpm_to=c.bpm_to, bpm_percent=c.bpm_percent,
            halftime=c.halftime, key_from=c.key_from, key_to=c.key_to,
            key_relation=c.key_relation, score=c.score, missing=c.missing,
            note=note_coppie.get((prima.track_id, dopo.track_id)),
        ))
```

e passa `transitions=transitions` a `ManualSetOut(...)`.

- [ ] **Step 5: Endpoint**

In `backend/app/routers/sets.py` aggiungi `PairNoteRequest` agli import da `app.schemas`, `set_pair_note` e `update_row` a quelli da `app.services.manual_set`, cambia il corpo della PATCH di riga in:

```python
@router.patch("/{setlist_id}/rows/{row_id}", response_model=ManualSetOut)
def rows_patch(setlist_id: int, row_id: int, req: RowPatchRequest, db: Session = Depends(get_db)):
    """Aggiorna i soli campi MANDATI: un campo assente non e' un campo da azzerare."""
    inviati = req.model_fields_set
    try:
        return manual_set_out(update_row(
            db, setlist_id, row_id, expected_revision=req.expected_revision,
            note=req.note if "note" in inviati else UNSET,
            play_bpm=req.play_bpm if "play_bpm" in inviati else UNSET), db)
    except ManualSetError as exc:
        raise _manual_error(exc) from exc
```

(`UNSET` si importa da `app.services.manual_set`.) E aggiungi:

```python
@router.put("/{setlist_id}/pair-notes", response_model=ManualSetOut)
def pair_notes_put(setlist_id: int, req: PairNoteRequest, db: Session = Depends(get_db)):
    """Appunto su un passaggio, legato alle due TRACCE: sopravvive a chi cambia
    idea sul percorso. Testo vuoto = cancella."""
    try:
        return manual_set_out(set_pair_note(
            db, setlist_id, expected_revision=req.expected_revision,
            from_track_id=req.from_track_id, to_track_id=req.to_track_id,
            note=req.note), db)
    except ManualSetError as exc:
        raise _manual_error(exc) from exc
```

- [ ] **Step 6: Esegui, suite, commit**

Run: `cd backend && .venv/bin/python -m pytest tests -q -p no:cacheprovider` → verde.

```bash
git add backend/app/schemas.py backend/app/serializers.py backend/app/routers/sets.py backend/tests/test_set_manual_api.py
git commit -m "feat(sets): endpoint dei passaggi e del tempo di cabina"
```

---

### Task 5: Frontend — il passaggio nel dettaglio

**Files:**
- Modify: `frontend/lib/api/types.ts`, `frontend/lib/api/manual-sets.ts`, `frontend/lib/i18n/{en,it}.ts`
- Create: `frontend/components/set-builder/transition-panel.tsx`
- Modify: `frontend/components/set-builder/detail-panel.tsx`, `frontend/app/sets/manual/page.tsx`
- Test: `frontend/tests/set-builder-pairs.test.tsx` (nuovo)

**Interfaces:**

```ts
export interface ManualTransition {
  from_row_id: number; to_row_id: number;
  from_track_id: number; to_track_id: number;
  bpm_from: number | null; bpm_to: number | null;
  bpm_percent: number | null; halftime: boolean;
  key_from: string | null; key_to: string | null;
  key_relation: "same" | "same_number" | "adjacent" | "weak" | "unknown";
  score: number | null; missing: string[]; note: string | null;
}
// ManualRow guadagna: play_bpm: number | null
// ManualSet guadagna: transitions: ManualTransition[]
setPairNote(id, body: { expected_revision: number; from_track_id: number; to_track_id: number; note: string | null }): Promise<ManualSet>
patchRow(id, rowId, body: { expected_revision: number; note?: string | null; play_bpm?: number | null }): Promise<ManualSet>
```

`patchRow` esiste già: il corpo diventa parziale, e **le due proprietà vanno omesse quando non si toccano** — mandare `note: undefined` va bene (JSON.stringify la salta), mandare `note: null` significa azzerare.

Comportamento della pagina:
- Nel dettaglio, sotto i dati della traccia: il campo «La suono a», numerico, con segnaposto il BPM della traccia; vuoto = nessun valore. Salva al blur solo se cambiato, come l'appunto.
- Sempre nel dettaglio, due blocchi: «Dal brano precedente» e «Al brano successivo», presenti solo se esiste il passaggio corrispondente in `transitions`. Ognuno mostra i due tempi con la percentuale di pitch firmata (`124 → 123 · −0,8 %`), le due tonalità, e un appunto salvato al blur. Dove `missing` contiene `bpm` o `key`, al posto del numero va «sconosciuto»: mai un punteggio al posto di un dato che non c'è.
- `halftime` aggiunge la dicitura «a mezzo tempo» accanto alla percentuale.

- [ ] **Step 1: Testi**

Chiavi nuove sotto `sets.manual` in `en.ts` poi `it.ts`: `playBpmLabel`, `playBpmHint`, `transitionInTitle`, `transitionOutTitle`, `transitionNotePlaceholder`, `halftimeLabel`, `pitchLabel`.

Traduzioni italiane: «La suono a», «Vuoto = al tempo della traccia.», «Dal brano precedente», «Al brano successivo», «Come ci entro, cosa taglio…», «a mezzo tempo», «pitch». `unknownValue` esiste già («sconosciuto»).

- [ ] **Step 2: Tipi e client** — come da blocco Interfaces sopra, sullo stesso stile dei metodi esistenti in `manual-sets.ts`.

- [ ] **Step 3: Scrivi il test**

`frontend/tests/set-builder-pairs.test.tsx`, sulla falsariga di `set-builder-blocks.test.tsx` (stessi mock di `@/lib/api` e `next/navigation`, stesso `mount()` dentro `PlayerProvider`; il fixture ha due righe in un blocco `main`, `transitions` con una voce e `can_undo`/`can_redo`). Casi:

1. selezionata la prima riga, il pannello del passaggio in uscita mostra `124`, `126` e `1.6`;
2. con `missing: ["bpm"]` al posto dei tempi compare «sconosciuto» e **nessun** punteggio;
3. scrivere nell'appunto del passaggio e uscire dal campo chiama `setPairNote` con i due `track_id` e `expected_revision`;
4. scrivere in «La suono a» e uscire chiama `patchRow` con `{expected_revision, play_bpm: 126}` **e senza la proprietà `note`** (asserire con `expect(api.patchRow).toHaveBeenCalledWith(7, 10, { expected_revision: 1, play_bpm: 126 })`, che fallisce se il componente manda anche `note`);
5. svuotare «La suono a» manda `play_bpm: null`;
6. un appunto di passaggio invariato al blur non chiama niente.

- [ ] **Step 4: Componenti e pagina** — `transition-panel.tsx` (`data-testid="transition-panel-in"` / `-out"`, presi da una prop `variant`), il dettaglio che lo monta due volte cercando in `set.transitions` le voci con `to_row_id === row.id` e `from_row_id === row.id`, la pagina che passa `set.transitions` al dettaglio e aggiunge `onSavePairNote` e `onSavePlayBpm` sopra `mutate`.

- [ ] **Step 5: Verifica**

Run: `cd frontend && npm run test:unit -- tests/set-builder-pairs.test.tsx`, poi `npx tsc --noEmit && npm run lint && npm run test:unit && npm run build`.
Attenzione: i fixture dei test già esistenti (`set-builder-workbench.test.tsx`, `set-builder-alternatives.test.tsx`, `set-builder-blocks.test.tsx`) vanno aggiornati con `transitions: []` e `play_bpm: null`, altrimenti la pagina non si disegna e i loro test cadono **solo nella suite intera**, non da soli — è già successo nelle tappe 2 e 3.

- [ ] **Step 6: Commit**

```bash
git add frontend/lib frontend/components/set-builder frontend/app/sets/manual/page.tsx frontend/tests
git commit -m "feat(frontend): il passaggio e «la suono a» nel dettaglio del set manuale"
```

---

### Task 6: Documentazione e verifica integrata

**Files:**
- Modify: `docs/API.md`, `docs/ARCHITECTURE.md`, `PROGRESS.md`, `docs/ROADMAP.md`, `frontend/e2e/set-builder.spec.ts`

- [ ] **Step 1: Documentazione**

`docs/API.md`, sezione «Set manuale»: il titolo diventa «tappe 1-4»; `PUT /api/sets/{id}/pair-notes` con il suo corpo; `play_bpm` nella PATCH di riga **con la regola della PATCH parziale** (un campo assente non si tocca, `null` azzera); `transitions` in `ManualSetOut` con il significato di `missing`, `bpm_percent` firmata e `halftime`; e che l'appunto di coppia è legato alle tracce, non alle righe. Aggiorna l'elenco finale di ciò che le tappe non fanno ancora (restano 5 e 6).

`docs/ARCHITECTURE.md`, sezione «Manual set»: il titolo diventa «tappe 1-4»; un paragrafo su `manual_pairs.py` — compatibilità calcolata a ogni lettura e mai salvata, dati mancanti dichiarati invece del neutro, `play_bpm` applicato con un oggetto di facciata per non scrivere `Track.bpm` al flush — e una riga su `SetlistPairNote` come giudizio per coppia di tracce, che è ciò che lo rende indipendente dal percorso. Dì anche, in una riga, che lo stato «provato» della spec non è stato fatto e perché.

`PROGRESS.md`: voce datata con cosa esiste e cosa no (restano le tappe 5-6).

`docs/ROADMAP.md`: la voce 3 del backlog passa da «tappe 1-3 shipped» a «tappe 1-4 shipped» e la tappa 4 esce dall'elenco di ciò che resta aperto, con la nota che lo stato «provato» è stato tolto per decisione dell'utente.

Vale la regola del progetto: ogni parentesi e ogni rimando va verificato per conto proprio.

- [ ] **Step 2: E2E**

Estendi `frontend/e2e/set-builder.spec.ts` con un terzo test: crea un set con tre tracce, seleziona la seconda riga, scrivi un appunto sul passaggio in entrata, ricarica e verifica che ci sia ancora; poi togli la prima traccia dal percorso, verifica che quel passaggio non compaia più, rimettila in testa e verifica che l'appunto sia tornato. È la verifica della spec fatta dal browser.

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
git add docs PROGRESS.md frontend/e2e
git commit -m "docs(sets): i passaggi del set manuale"
```
