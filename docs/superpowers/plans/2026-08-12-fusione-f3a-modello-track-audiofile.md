# Fusione Sortory → Cratory — F3a (modello `Track` 1─N `AudioFile`) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Introdurre la relazione strutturale fra la traccia e il suo file — `audio_file.track_id`, `audio_file.location`, `tracks.primary_file_id` — e agganciare i 625 file già posseduti, senza modificare una sola query esistente di Cratory.

**Architecture:** Le colonne nuove si aggiungono al modello e arrivano sul DB live tramite il macchinario model-derived di `ensure_schema`. La relazione si dichiara **dal lato Organize** (`AudioFile.track` con `backref("files")`), così `app/models.py` guadagna una sola colonna e nessun import. `location` si deriva dal prefisso del path contro le due cartelle di Settings. Il backfill è uno script con dry-run e assert su invarianti, stessa forma di quello di F2.

**Tech Stack:** Python 3.11.15, SQLAlchemy 2, SQLite, pytest.

**Spec di riferimento:** `docs/superpowers/specs/2026-08-11-fusione-sortory-cratory-design.md`, sezione "3. Modello dati".

**Prerequisito:** F2 completa su `feat/fusione-f1` (DB unico, `foreign_keys=ON` nel codice Organize).

## Perché questo piano è "F3a" e non "F3"

La tabella delle fasi della spec mette insieme due lavori di natura diversa:

1. le colonne nuove e il backfill degli agganci — **questo piano**;
2. la rimozione di `scan_root` — **83 riferimenti** fra `models`, `schemas`, cinque router, `planning.root_targets`, il controllo FK dello script di migrazione e la pagina frontend `/organize/sources`.

Il secondo non è un dettaglio del primo: è una modifica di superficie API e UI che merita il proprio piano e la propria milestone. Separandoli, F3a resta software funzionante e verificabile da solo — `scan_root` continua a esistere e `root_targets` a funzionare come oggi — e F3b diventa una potatura a modello già assestato.

## Global Constraints

- Worktree **`.claude/worktrees/fusione-f1`**, branch `feat/fusione-f1`. Non su `master`.
- **Commit senza `Co-Authored-By`.**
- Prima di ogni commit: `git status --porcelain` e `git branch --show-current`; stageare solo i propri file.
- Test: `backend/.venv/bin/python -m pytest tests` dal worktree.
- **`scan_root`, `root_id` e `root_targets` restano intatti.** Toccarli è F3b.
- **Nessuna query esistente di Cratory va modificata.** `has_local_file`, `local_path`, `local_format`, `local_bitrate` restano dove sono e continuano a significare quello che significavano: `primary_file_id` si affianca, non sostituisce.
- **Il DB reale si tocca solo tramite script con dry-run**, e solo dopo backup.
- **Ogni strumento prende il DB con `--db` esplicito e stampa su quale sta lavorando.**
  Il worktree ha un proprio `backend/.env` e un proprio `data/djassistant.db`: uno
  strumento che si affida a `SessionLocal` lì dentro legge il DB del *worktree*, non
  quello del checkout principale — e risponde "nessun duplicato" su un database quasi
  vuoto sembrando aver funzionato. È successo davvero eseguendo questo piano. Lo script
  di migrazione di F2 non ne soffriva perché prendeva `--src`/`--dest` assoluti.
  DB reale: `/Users/lucadenegri/Develop/DJProject01/backend/data/djassistant.db`.

## Vincolo tecnico da conoscere prima di iniziare

`_migrate_add_model_columns` (`app/db.py:61`) aggiunge le colonne nuove derivandole dal modello, ma **senza clausola `REFERENCES`** — è scritto nel suo docstring, riga 81:

> `- niente clausola REFERENCES: le colonne legacy con FK (Track.playlist_id, non droppabile, vedi _DEAD_LEAD_COLS) si ri-aggiungono come colonne semplici`

Conseguenza concreta: sul DB **già esistente** `track_id` e `primary_file_id` arrivano come `INTEGER` semplici, senza vincolo a livello SQLite. Su un DB creato da zero (i test) la FK c'è. Quindi:

- la coerenza va garantita **nel codice**, non dal database;
- i test che verificano la semantica di cancellazione devono girare a livello ORM, perché è l'unico livello attivo in entrambi gli scenari;
- **non** si rifà la tabella per aggiungere il vincolo: il progetto evita esplicitamente i rebuild di `tracks` (vedi il commento su `playlist_id` in `app/models.py`), e un rebuild è esattamente il tipo di operazione che su 677 tracce con playlist, set e rating non vale il rischio.

## Semantica di cancellazione (la domanda aperta, decisa qui)

| Cosa si cancella | Cosa deve succedere | Come si ottiene |
|---|---|---|
| una `Track` | i suoi `AudioFile` **sopravvivono** con `track_id = NULL` — il file è ancora sul disco | automatico: `backref("files")` su FK nullable, SQLAlchemy azzera il figlio |
| un `AudioFile` | la `Track` **sopravvive** come lead, con `primary_file_id = NULL` e `has_local_file` invariato | **non** automatico: nessuna relationship da quel lato → helper esplicito `stacca_file()`, chiamato dove si cancellano `AudioFile` |

La seconda riga è il motivo per cui esiste il Task 4. È la stessa famiglia di difetto delle sei coppie FK senza `relationship()` già trovate nell'audit: una FK che nessuno ordina è una FK che prima o poi lascia un orfano.

---

## File Structure

```
backend/
  app/
    models.py                          +1 colonna: Track.primary_file_id
    organize/
      models.py                        +2 colonne su AudioFile (track_id, location)
                                       +1 relationship AudioFile.track con backref files
      services/
        file_link.py                   NUOVO: derivazione location, stacca_file, aggiorna_primary
    services/
      library_index.py                 3 punti: primary_file_id accanto ai local_*
      acquisition.py                   1 punto: idem
    tools/
      merge_duplicate_tracks.py        NUOVO: fusione di due Track sullo stesso file
      backfill_track_files.py          NUOVO: location + track_id + primary_file_id
  tests/
    organize/
      test_file_link.py                NUOVO
      test_modello_track_file.py       NUOVO
    test_merge_duplicate_tracks.py     NUOVO
    test_backfill_track_files.py       NUOVO
    test_invarianti_libreria.py        NUOVO: nessuna Track condivide local_path
```

---

### Task 1: Fondere le due `Track` che puntano allo stesso file

**Files:**
- Create: `backend/app/tools/merge_duplicate_tracks.py`
- Test: `backend/tests/test_merge_duplicate_tracks.py`, `backend/tests/test_invarianti_libreria.py`

**Interfaces:**
- Consumes: `app.models.Track`, `app.models.playlist_tracks`
- Produces: `fondi(db, tenere_id: int, scartare_id: int) -> dict[str, int]` — restituisce `{"playlist_spostate": n, "setlist_spostate": n}`; `trova_duplicati_per_path(db) -> list[tuple[str, list[int]]]`

**Perché prima di tutto il resto.** Nei dati reali esistono 625 coppie `(audio_file, tracks)` ma solo **624 path distinti**: due `Track` puntano allo stesso file. `audio_file.track_id` è una FK singola, quindi senza questa fusione il backfill produce 625 `primary_file_id` e 624 `track_id`, e l'assert di simmetria fallisce su dati corretti.

Il duplicato, per nome: *Robert Leiner — Aqua Viva*.

| | `150` | `1157` |
|---|---|---|
| identità | `spotify_id` + ISRC | manual, nessuna |
| BPM/key | 139.86 / 4A, `bpm_source=rekordbox` | 139.86 / 4A, `bpm_source=cratory` |
| aggiunta | 2026-06-09 | 2026-08-08 |
| playlist | 3 — "muoviti senza aprire gli occhi" | 13 — "Discovery" (`added_by='cratory'`) |

Si tiene **150**: ha identità streaming e `bpm_source=rekordbox`, che nella gerarchia `manual > rekordbox > cratory` batte l'altro. La membership della playlist Discovery va spostata su 150 **prima** della cancellazione, altrimenti sparisce.

- [ ] **Step 1: Scrivere il test che fallisce**

Crea `backend/tests/test_merge_duplicate_tracks.py`:

```python
"""Fusione di due Track che puntano allo stesso file su disco."""

import pytest
from sqlalchemy import select

from app.models import Playlist, Track, playlist_tracks
from app.tools.merge_duplicate_tracks import fondi, trova_duplicati_per_path


@pytest.fixture()
def coppia(db):
    """Due tracce sullo stesso local_path, in due playlist diverse."""
    a = Track(source_type="spotify", platform="spotify", spotify_id="abc", isrc="IT1234567890",
              artist="Robert Leiner", title="Aqua Viva", bpm=139.86, camelot_key="4A",
              bpm_source="rekordbox", has_local_file=True, local_path="/lib/aqua.flac")
    b = Track(source_type="manual", platform="manual",
              artist="Robert Leiner", title="Aqua Viva", bpm=139.86, camelot_key="4A",
              bpm_source="cratory", has_local_file=True, local_path="/lib/aqua.flac")
    p1, p2 = Playlist(name="Set"), Playlist(name="Discovery")
    db.add_all([a, b, p1, p2])
    db.commit()
    db.execute(playlist_tracks.insert().values(playlist_id=p1.id, track_id=a.id))
    db.execute(playlist_tracks.insert().values(playlist_id=p2.id, track_id=b.id, added_by="cratory"))
    db.commit()
    return a, b, p1, p2


def test_trova_duplicati_per_path(db, coppia):
    a, b, _, _ = coppia
    dupes = trova_duplicati_per_path(db)
    assert len(dupes) == 1
    path, ids = dupes[0]
    assert path == "/lib/aqua.flac"
    assert set(ids) == {a.id, b.id}


def test_fusione_sposta_le_playlist_e_cancella_lo_scarto(db, coppia):
    a, b, p1, p2 = coppia
    esito = fondi(db, tenere_id=a.id, scartare_id=b.id)
    db.commit()

    assert esito["playlist_spostate"] == 1
    assert db.get(Track, b.id) is None

    playlists = set(db.scalars(
        select(playlist_tracks.c.playlist_id).where(playlist_tracks.c.track_id == a.id)
    ))
    assert playlists == {p1.id, p2.id}


def test_fusione_non_duplica_una_membership_gia_presente(db, coppia):
    """Se entrambe stanno nella stessa playlist, la fusione non viola la PK composta."""
    a, b, p1, _ = coppia
    db.execute(playlist_tracks.insert().values(playlist_id=p1.id, track_id=b.id))
    db.commit()

    fondi(db, tenere_id=a.id, scartare_id=b.id)
    db.commit()

    righe = db.execute(
        select(playlist_tracks).where(playlist_tracks.c.track_id == a.id,
                                      playlist_tracks.c.playlist_id == p1.id)
    ).all()
    assert len(righe) == 1


def test_rifiuta_di_fondere_una_traccia_con_se_stessa(db, coppia):
    a, _, _, _ = coppia
    with pytest.raises(ValueError, match="stessa traccia"):
        fondi(db, tenere_id=a.id, scartare_id=a.id)
```

E crea `backend/tests/test_invarianti_libreria.py` — l'invariante che deve restare vero per sempre:

```python
"""Invarianti della libreria che il modello Track 1─N AudioFile dà per scontati."""

from sqlalchemy import func, select

from app.models import Track


def test_nessuna_traccia_condivide_il_local_path(db):
    """Due Track sullo stesso file renderebbero ambiguo audio_file.track_id,
    che è una FK singola. Vedi la fusione in app/tools/merge_duplicate_tracks."""
    db.add_all([
        Track(source_type="manual", has_local_file=True, local_path="/lib/a.flac"),
        Track(source_type="manual", has_local_file=True, local_path="/lib/b.flac"),
    ])
    db.commit()

    doppi = db.execute(
        select(Track.local_path, func.count())
        .where(Track.has_local_file.is_(True), Track.local_path.is_not(None))
        .group_by(Track.local_path)
        .having(func.count() > 1)
    ).all()
    assert doppi == []
```

- [ ] **Step 2: Lanciare i test e verificarne il fallimento**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/backend && .venv/bin/python -m pytest tests/test_merge_duplicate_tracks.py -v
```

Atteso: FAIL con `ModuleNotFoundError: No module named 'app.tools.merge_duplicate_tracks'`.

- [ ] **Step 3: Scrivere lo strumento**

Crea `backend/app/tools/merge_duplicate_tracks.py`:

```python
"""Fusione di due Track che puntano allo stesso file su disco.

Serve perché `audio_file.track_id` è una FK singola: due tracce sullo stesso
file renderebbero l'aggancio ambiguo e romperebbero la simmetria
`primary_file_id ↔ track_id`. Vedi il piano F3a.

Uso:
    python -m app.tools.merge_duplicate_tracks --elenca
    python -m app.tools.merge_duplicate_tracks --tenere 150 --scartare 1157 --apply
"""

from __future__ import annotations

import argparse

from sqlalchemy import delete, func, insert, select
from sqlalchemy.orm import Session

from app.models import Track, playlist_tracks


def trova_duplicati_per_path(db: Session) -> list[tuple[str, list[int]]]:
    """Path posseduti da più di una Track, con gli id coinvolti."""
    doppi = db.execute(
        select(Track.local_path)
        .where(Track.has_local_file.is_(True), Track.local_path.is_not(None))
        .group_by(Track.local_path)
        .having(func.count() > 1)
    ).scalars().all()
    esito = []
    for path in doppi:
        ids = list(db.scalars(select(Track.id).where(Track.local_path == path)))
        esito.append((path, ids))
    return esito


def fondi(db: Session, *, tenere_id: int, scartare_id: int) -> dict[str, int]:
    """Sposta le membership di `scartare_id` su `tenere_id`, poi lo cancella.

    Non fa commit: il chiamante decide la transazione.
    """
    if tenere_id == scartare_id:
        raise ValueError("non si fonde una traccia con se stessa")
    tenere, scartare = db.get(Track, tenere_id), db.get(Track, scartare_id)
    if tenere is None or scartare is None:
        raise ValueError(f"traccia inesistente: {tenere_id if tenere is None else scartare_id}")

    gia_presenti = set(db.scalars(
        select(playlist_tracks.c.playlist_id).where(playlist_tracks.c.track_id == tenere_id)
    ))
    spostate = 0
    righe = db.execute(
        select(playlist_tracks).where(playlist_tracks.c.track_id == scartare_id)
    ).mappings().all()
    for riga in righe:
        if riga["playlist_id"] in gia_presenti:
            continue  # la PK composta (playlist_id, track_id) è già occupata
        db.execute(insert(playlist_tracks).values(
            playlist_id=riga["playlist_id"], track_id=tenere_id,
            added_at=riga["added_at"], added_by=riga["added_by"], position=riga["position"],
        ))
        spostate += 1
    db.execute(delete(playlist_tracks).where(playlist_tracks.c.track_id == scartare_id))
    db.delete(scartare)
    db.flush()
    return {"playlist_spostate": spostate}


def main() -> int:
    from app.db import SessionLocal

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--elenca", action="store_true", help="mostra i duplicati e esce")
    parser.add_argument("--tenere", type=int)
    parser.add_argument("--scartare", type=int)
    parser.add_argument("--apply", action="store_true", help="scrive davvero (default: dry-run)")
    args = parser.parse_args()

    with SessionLocal() as db:
        if args.elenca or not (args.tenere and args.scartare):
            for path, ids in trova_duplicati_per_path(db):
                print(f"{path}  →  tracce {ids}")
            return 0
        esito = fondi(db, tenere_id=args.tenere, scartare_id=args.scartare)
        print(f"membership spostate: {esito['playlist_spostate']}")
        if args.apply:
            db.commit()
            print("fusione applicata")
        else:
            db.rollback()
            print("dry-run: nulla scritto")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Lanciare i test**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/backend && .venv/bin/python -m pytest tests/test_merge_duplicate_tracks.py tests/test_invarianti_libreria.py -v
```

Atteso: 5 passed.

- [ ] **Step 5: Backup e fusione sui dati reali**

```bash
mkdir -p ~/Backup/fusione-f3a && \
cp /Users/lucadenegri/Develop/DJProject01/backend/data/djassistant.db ~/Backup/fusione-f3a/djassistant-pre-f3a.db && \
ls -la ~/Backup/fusione-f3a/
```

Poi elenca e fondi:

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/backend && \
.venv/bin/python -m app.tools.merge_duplicate_tracks \
  --db /Users/lucadenegri/Develop/DJProject01/backend/data/djassistant.db --elenca
```

Atteso: una riga sola, `/Users/lucadenegri/Music/Library/Trance/Robert Leiner/Robert Leiner - Aqua Viva.flac → tracce [150, 1157]`.

**Se compare più di una riga, fermati**: il piano ne prevedeva una, e le altre vanno decise una per una con lo stesso criterio (tiene chi ha identità streaming e la `bpm_source` più alta in gerarchia).

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/backend && \
.venv/bin/python -m app.tools.merge_duplicate_tracks \
  --db /Users/lucadenegri/Develop/DJProject01/backend/data/djassistant.db \
  --tenere 150 --scartare 1157 --apply
```

Atteso: `membership spostate: 1`, `fusione applicata`.

- [ ] **Step 6: Verificare sui dati reali**

```bash
sqlite3 /Users/lucadenegri/Develop/DJProject01/backend/data/djassistant.db "
select (select count(*) from tracks) as tracce,
       (select count(*) from tracks t join audio_file f on f.path = t.local_path where t.has_local_file=1) as coppie,
       (select count(distinct t.local_path) from tracks t join audio_file f on f.path = t.local_path where t.has_local_file=1) as path_distinti,
       (select count(*) from playlist_tracks where track_id = 150) as playlist_di_150;"
```

Atteso: `676 | 624 | 624 | 2`. Le coppie e i path distinti ora coincidono — è la precondizione del backfill.

- [ ] **Step 7: Commit**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1 && \
git status --porcelain && \
git add backend/app/tools/merge_duplicate_tracks.py backend/tests/test_merge_duplicate_tracks.py backend/tests/test_invarianti_libreria.py && \
git commit -m "feat(f3a): fusione delle Track duplicate sullo stesso file"
```

---

### Task 2: Le colonne nuove e la relazione

**Files:**
- Modify: `backend/app/models.py` (una colonna)
- Modify: `backend/app/organize/models.py` (due colonne, una relationship)
- Test: `backend/tests/organize/test_modello_track_file.py`

**Interfaces:**
- Produces:
  - `Track.primary_file_id: int | None`
  - `Track.files: list[AudioFile]` (dal backref)
  - `AudioFile.track_id: int | None`
  - `AudioFile.location: str` — `"inbox"` | `"library"`
  - `AudioFile.track: Track | None`

**La relazione si dichiara dal lato Organize.** `app/models.py` riceve **solo** la colonna `primary_file_id`, senza `relationship` e senza importare nulla da `app.organize`: la relazione vive su `AudioFile.track` con `backref("files")`, che popola `Track.files` a runtime. Così il modello core resta ignaro di Organize, ed è quello che rende vera la milestone "nessuna query esistente di Cratory modificata".

- [ ] **Step 1: Scrivere il test che fallisce**

Crea `backend/tests/organize/test_modello_track_file.py`:

```python
"""Modello Track 1─N AudioFile: colonne, relazione, semantica di cancellazione."""

import pytest
from sqlalchemy import inspect

from app.models import Track
from app.organize.models import AudioFile, ScanRoot


@pytest.fixture()
def radice(db):
    r = ScanRoot(path="/lib")
    db.add(r)
    db.flush()
    return r


def _file(radice, path: str, **kw) -> AudioFile:
    return AudioFile(root_id=radice.id, path=path, ext=".flac", size_bytes=1,
                     hash_method="stream", status="present", location="library", **kw)


def test_colonne_presenti():
    assert "primary_file_id" in inspect(Track).columns
    assert "track_id" in inspect(AudioFile).columns
    assert "location" in inspect(AudioFile).columns


def test_una_traccia_puo_avere_piu_file(db, radice):
    t = Track(source_type="manual", artist="A", title="B")
    db.add(t)
    db.flush()
    db.add_all([_file(radice, "/lib/a.flac", track_id=t.id),
                _file(radice, "/lib/a-copia.flac", track_id=t.id)])
    db.commit()
    db.refresh(t)
    assert {f.path for f in t.files} == {"/lib/a.flac", "/lib/a-copia.flac"}


def test_file_senza_traccia_e_legittimo(db, radice):
    """Un file nell'inbox non è ancora una traccia: track_id resta NULL."""
    f = _file(radice, "/inbox/x.mp3")
    f.location = "inbox"
    db.add(f)
    db.commit()
    assert f.track_id is None
    assert f.track is None


def test_cancellare_la_traccia_non_cancella_il_file(db, radice):
    """Il file è ancora sul disco: sopravvive con track_id azzerato."""
    t = Track(source_type="manual", artist="A", title="B")
    db.add(t)
    db.flush()
    f = _file(radice, "/lib/a.flac", track_id=t.id)
    db.add(f)
    db.commit()

    db.delete(t)
    db.commit()

    rimasto = db.get(AudioFile, f.id)
    assert rimasto is not None
    assert rimasto.track_id is None
```

- [ ] **Step 2: Lanciare il test e verificare che fallisca**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/backend && .venv/bin/python -m pytest tests/organize/test_modello_track_file.py -v
```

Atteso: FAIL — `primary_file_id` non è fra le colonne di `Track`.

- [ ] **Step 3: Aggiungere la colonna a `Track`**

In `backend/app/models.py`, dentro `class Track`, subito dopo il blocco dei campi `local_*` (accanto a `local_size`):

```python
    # File rappresentante fra quelli agganciati a questa traccia (Track 1─N
    # AudioFile). I local_* qui sopra restano la cache derivata, interrogata
    # ovunque nel codice: questa colonna dice DA QUALE file quella cache viene.
    # Nessuna relationship da questo lato — la relazione è dichiarata su
    # AudioFile.track con backref("files"), così il modello core non deve
    # importare app.organize.
    primary_file_id: Mapped[int | None] = mapped_column(
        ForeignKey("audio_file.id", use_alter=True, name="fk_tracks_primary_file"),
        index=True,
    )
```

`ForeignKey` è già importato in quel file.

**`use_alter=True` non è decorativo.** Le due FK formano un ciclo — `tracks.primary_file_id → audio_file.id` e `audio_file.track_id → tracks.id` — e SQLAlchemy non riesce a ordinare le tabelle per CREATE/DROP su un backend che non supporta l'ALTER, come SQLite:

> `Can't sort tables for DROP; an unresolvable foreign key dependency exists between tables: audio_file, tracks; and backend does not support ALTER.`

`use_alter=True` marca il ciclo come noto e lo esclude dall'ordinamento. Senza, ogni test che usa la fixture `db` (che fa `create_all`/`drop_all`) va in errore.

- [ ] **Step 4: Aggiungere colonne e relazione ad `AudioFile`**

In `backend/app/organize/models.py`, dentro `class AudioFile`, dopo `root_id`:

```python
    # Traccia di cui questo file è una copia. NULL = file non ancora
    # riconosciuto (tipicamente l'inbox, dove i file non sono ancora tracce).
    track_id: Mapped[int | None] = mapped_column(ForeignKey("tracks.id"), index=True)
    # Collocazione, derivata dal prefisso del path contro le due cartelle di
    # Settings: "inbox" (SLSKD_DOWNLOAD_DIR) o "library" (LIBRARY_ROOT).
    # Non esiste un terzo caso: lo scan cammina solo quelle due radici.
    location: Mapped[str] = mapped_column(String, default="inbox",
                                          server_default="inbox", index=True)
```

e, accanto alla relationship `root` già presente:

```python
    # foreign_keys esplicito: fra audio_file e tracks ci sono DUE percorsi FK
    # (track_id di qua, primary_file_id di là), e l'ORM da solo non sa quale
    # regge questa relazione.
    track: Mapped["Track | None"] = relationship(
        "Track", foreign_keys="AudioFile.track_id",
        backref=backref("files", passive_deletes=False),
    )
```

Senza `foreign_keys` la configurazione dei mapper fallisce con `Could not determine
join condition ... there are multiple foreign key paths linking the tables`: è la
seconda faccia dello stesso ciclo che `use_alter` risolve lato DDL.

In testa al file, aggiungere `backref` all'import `sqlalchemy.orm` già presente (che oggi porta `Mapped, mapped_column, relationship`) e importare `Track`:

```python
from sqlalchemy.orm import Mapped, backref, mapped_column, relationship

from app.models import Track  # risolve l'annotazione della relationship
```

**Attenzione all'ordine di import.** `app/organize/models.py` importa ora `app.models`; `app/models.py` non deve importare `app.organize.models` (altrimenti è un ciclo). La FK `Track.primary_file_id → audio_file.id` si risolve per nome di tabella al momento del `create_all`, e `ensure_schema` importa entrambi i moduli dalla F2 — quindi la tabella c'è sempre quando serve.

- [ ] **Step 5: Lanciare il test**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/backend && .venv/bin/python -m pytest tests/organize/test_modello_track_file.py -v
```

Atteso: 5 passed.

- [ ] **Step 6: Verificare che i mapper si configurino anche importando solo il modello core**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/backend && \
.venv/bin/python -c "
import app.models, app.organize.models
from sqlalchemy.orm import configure_mappers
configure_mappers()
from app.models import Track
print('Track.files ->', Track.files.property.mapper.class_.__name__)
print('mapper ok')
"
```

Atteso: `Track.files -> AudioFile` e `mapper ok`.

- [ ] **Step 7: Applicare lo schema al DB reale e verificare le colonne**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/backend && \
.venv/bin/python -c "
from app.db import ensure_schema, engine
ensure_schema()
print('schema aggiornato su', engine.url)
" && \
sqlite3 /Users/lucadenegri/Develop/DJProject01/backend/data/djassistant.db \
  "select count(*) from pragma_table_info('audio_file') where name in ('track_id','location');
   select count(*) from pragma_table_info('tracks') where name='primary_file_id';"
```

Atteso: `2` e `1`.

Le colonne arrivano **senza** clausola `REFERENCES`, come spiegato in testa al piano: verificalo e non sorprenderti.

```bash
sqlite3 /Users/lucadenegri/Develop/DJProject01/backend/data/djassistant.db "select count(*) from pragma_foreign_key_list('audio_file') where \"from\"='track_id';"
```

Atteso: `0`. È la ragione per cui la coerenza la garantisce il Task 4, non il database.

- [ ] **Step 8: Suite completa e commit**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/backend && .venv/bin/python -m pytest tests -q
```

Atteso: tutto verde.

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1 && \
git add backend/app/models.py backend/app/organize/models.py backend/tests/organize/test_modello_track_file.py && \
git commit -m "feat(f3a): Track 1-N AudioFile — track_id, location, primary_file_id"
```

---

### Task 3: Derivazione di `location` e helper di aggancio

**Files:**
- Create: `backend/app/organize/services/file_link.py`
- Test: `backend/tests/organize/test_file_link.py`

**Interfaces:**
- Produces:
  - `deriva_location(path: str, *, library_root: str, inbox_root: str) -> str` — solleva `ValueError` se il path non sta sotto nessuna delle due
  - `aggiorna_primary(db, track: Track) -> None` — allinea `track.primary_file_id` al file che corrisponde a `track.local_path`
  - `stacca_file(db, file_id: int) -> int` — azzera `primary_file_id` sulle tracce che puntano a quel file; restituisce quante ne ha toccate

- [ ] **Step 1: Scrivere il test che fallisce**

Crea `backend/tests/organize/test_file_link.py`:

```python
"""Derivazione della collocazione e manutenzione degli agganci."""

import pytest

from app.models import Track
from app.organize.models import AudioFile, ScanRoot
from app.organize.services.file_link import aggiorna_primary, deriva_location, stacca_file

LIB = "/Users/x/Music/Library"
INBOX = "/Users/x/Music/Downloads"


def test_deriva_location_library():
    assert deriva_location(f"{LIB}/Techno/a.flac", library_root=LIB, inbox_root=INBOX) == "library"


def test_deriva_location_inbox():
    assert deriva_location(f"{INBOX}/pack/b.mp3", library_root=LIB, inbox_root=INBOX) == "inbox"


def test_deriva_location_rifiuta_i_path_fuori_dalle_radici():
    with pytest.raises(ValueError, match="fuori"):
        deriva_location("/altrove/c.flac", library_root=LIB, inbox_root=INBOX)


def test_deriva_location_non_si_fa_ingannare_da_un_prefisso_parziale():
    """`/Music/LibraryVecchia` non sta dentro `/Music/Library`."""
    with pytest.raises(ValueError):
        deriva_location(f"{LIB}Vecchia/d.flac", library_root=LIB, inbox_root=INBOX)


@pytest.fixture()
def radice(db):
    r = ScanRoot(path=LIB)
    db.add(r)
    db.flush()
    return r


def test_aggiorna_primary_collega_traccia_e_file(db, radice):
    t = Track(source_type="manual", has_local_file=True, local_path=f"{LIB}/a.flac")
    f = AudioFile(root_id=radice.id, path=f"{LIB}/a.flac", ext=".flac", size_bytes=1,
                  hash_method="stream", status="present", location="library")
    db.add_all([t, f])
    db.flush()

    aggiorna_primary(db, t)
    db.flush()

    assert t.primary_file_id == f.id
    assert db.get(AudioFile, f.id).track_id == t.id


def test_aggiorna_primary_azzera_se_il_file_non_e_indicizzato(db, radice):
    t = Track(source_type="manual", has_local_file=True, local_path=f"{LIB}/mai-visto.flac",
              primary_file_id=None)
    db.add(t)
    db.flush()

    aggiorna_primary(db, t)
    assert t.primary_file_id is None


def test_stacca_file_azzera_le_tracce_che_lo_puntano(db, radice):
    f = AudioFile(root_id=radice.id, path=f"{LIB}/a.flac", ext=".flac", size_bytes=1,
                  hash_method="stream", status="present", location="library")
    db.add(f)
    db.flush()
    t = Track(source_type="manual", has_local_file=True, local_path=f"{LIB}/a.flac",
              primary_file_id=f.id)
    db.add(t)
    db.flush()

    toccate = stacca_file(db, f.id)
    db.flush()

    assert toccate == 1
    assert t.primary_file_id is None
    # has_local_file NON viene toccato: dire se la traccia è posseduta è
    # compito dell'indicizzazione libreria, non di questo helper.
    assert t.has_local_file is True
```

- [ ] **Step 2: Lanciare il test e verificare che fallisca**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/backend && .venv/bin/python -m pytest tests/organize/test_file_link.py -v
```

Atteso: FAIL con `ModuleNotFoundError: No module named 'app.organize.services.file_link'`.

- [ ] **Step 3: Scrivere il modulo**

Crea `backend/app/organize/services/file_link.py`:

```python
"""Aggancio fra la traccia e il suo file, e derivazione della collocazione.

`Track.primary_file_id` e `AudioFile.track_id` sono le due facce della stessa
relazione. La prima è la cache che dice da quale file arrivano i `local_*`; la
seconda è la proprietà del file. Vanno mantenute insieme: qui stanno le uniche
funzioni autorizzate a scriverle.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import Track
from app.organize.models import AudioFile


def _dentro(path: str, radice: str) -> bool:
    """True se `path` sta sotto `radice`. Confronto per componenti, non per
    prefisso di stringa: altrimenti `/Music/LibraryVecchia` risulterebbe dentro
    `/Music/Library`."""
    if not radice:
        return False
    try:
        Path(path).relative_to(Path(radice))
    except ValueError:
        return False
    return True


def deriva_location(path: str, *, library_root: str, inbox_root: str) -> str:
    """"library" o "inbox". Sollevare è voluto: un file fuori dalle due radici
    non dovrebbe esistere nell'indice, e inventargli una collocazione
    nasconderebbe una configurazione sbagliata."""
    if _dentro(path, library_root):
        return "library"
    if _dentro(path, inbox_root):
        return "inbox"
    raise ValueError(f"path fuori da entrambe le radici configurate: {path}")


def aggiorna_primary(db: Session, track: Track) -> None:
    """Allinea `track.primary_file_id` (e il `track_id` del file) al file che
    corrisponde a `track.local_path`. Se quel file non è indicizzato, azzera.

    Non fa commit: il chiamante decide la transazione."""
    if not track.local_path:
        track.primary_file_id = None
        return
    file = db.scalar(select(AudioFile).where(AudioFile.path == track.local_path))
    if file is None:
        track.primary_file_id = None
        return
    track.primary_file_id = file.id
    file.track_id = track.id


def stacca_file(db: Session, file_id: int) -> int:
    """Azzera `primary_file_id` sulle tracce che puntano a questo file.

    Da chiamare PRIMA di cancellare un AudioFile: la FK non ha una
    relationship() da quel lato, quindi nessuno azzera i figli al posto nostro —
    ed è la stessa classe di difetto delle sei coppie senza relationship trovate
    nell'audit di F2.

    NON tocca `has_local_file`: stabilire se la traccia è posseduta è compito
    dell'indicizzazione libreria."""
    esito = db.execute(
        update(Track).where(Track.primary_file_id == file_id).values(primary_file_id=None)
    )
    return esito.rowcount or 0
```

- [ ] **Step 4: Lanciare i test**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/backend && .venv/bin/python -m pytest tests/organize/test_file_link.py -v
```

Atteso: 7 passed.

- [ ] **Step 5: Commit**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1 && \
git add backend/app/organize/services/file_link.py backend/tests/organize/test_file_link.py && \
git commit -m "feat(f3a): file_link — derivazione location, aggancio e distacco"
```

---

### Task 4: Chiamare `stacca_file` dove si cancellano gli `AudioFile`

**Files:**
- Modify: `backend/app/organize/services/scanner.py` (intorno alla riga 135)
- Modify: `backend/app/organize/routers/sources.py` (cancellazione della sorgente)
- Test: `backend/tests/organize/test_stacca_su_cancellazione.py`

**Interfaces:**
- Consumes: `app.organize.services.file_link.stacca_file`

**Perché serve un task solo per questo.** Cancellare una `Track` azzera i `track_id` dei suoi file da solo, perché c'è la relationship. Il verso opposto no: `Track.primary_file_id` non ha nessuna relationship che lo ordini, e sul DB migrato non ha nemmeno il vincolo FK. Un `AudioFile` cancellato senza passare da `stacca_file` lascia una `Track` che punta a un id inesistente — esattamente le 158 righe orfane che la migrazione di F2 ha trovato, riprodotte da capo.

- [ ] **Step 1: Trovare tutti i punti che cancellano `AudioFile`**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/backend && \
grep -rn "delete(AudioFile)\|db.delete(" app/organize | grep -i "audiofile\|cand\|file"
```

Confronta l'elenco con i due punti previsti da questo task (`scanner.py`, `sources.py`). **Se ne trovi altri, aggiungili**: il piano ne prevedeva due sulla base dell'audit di F2, ma il codice è la fonte di verità.

- [ ] **Step 2: Scrivere il test che fallisce**

Crea `backend/tests/organize/test_stacca_su_cancellazione.py`:

```python
"""Cancellare un AudioFile non deve lasciare Track che lo puntano."""

from sqlalchemy import select

from app.models import Track
from app.organize.models import AudioFile, ScanRoot
from app.organize.services.file_link import stacca_file

LIB = "/lib"


def test_nessuna_traccia_punta_a_un_file_cancellato(db):
    r = ScanRoot(path=LIB)
    db.add(r)
    db.flush()
    f = AudioFile(root_id=r.id, path=f"{LIB}/a.flac", ext=".flac", size_bytes=1,
                  hash_method="stream", status="present", location="library")
    db.add(f)
    db.flush()
    t = Track(source_type="manual", has_local_file=True, local_path=f"{LIB}/a.flac",
              primary_file_id=f.id)
    db.add(t)
    db.commit()

    stacca_file(db, f.id)
    db.delete(f)
    db.commit()

    orfane = db.scalars(
        select(Track).where(Track.primary_file_id.is_not(None))
        .where(~Track.primary_file_id.in_(select(AudioFile.id)))
    ).all()
    assert orfane == []
    assert db.get(Track, t.id).primary_file_id is None
```

- [ ] **Step 3: Lanciare il test**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/backend && .venv/bin/python -m pytest tests/organize/test_stacca_su_cancellazione.py -v
```

Atteso: **passa già** — verifica l'helper, non i chiamanti. Serve come rete: se qualcuno cambierà `stacca_file`, questo test lo dice.

- [ ] **Step 4: Innestare la chiamata in `scanner.py`**

Alla riga ~135, dove c'è `db.delete(cand)`, anteporre:

```python
        # Il file esce dall'indice: nessuna Track deve restare a puntarlo.
        # Track.primary_file_id non ha relationship() che ordini la
        # cancellazione, e sul DB migrato non ha nemmeno il vincolo FK.
        stacca_file(db, cand.id)
        db.delete(cand)
```

con `from app.organize.services.file_link import stacca_file` in testa al modulo.

- [ ] **Step 5: Innestare la chiamata in `sources.py`**

Nella cancellazione della sorgente, dove si rimuovono gli `AudioFile` della radice, prima della `delete()` di massa:

```python
    # Stessa ragione di scanner.py: le Track che puntano a questi file vanno
    # staccate a mano, la FK non lo fa per noi.
    for file_id in db.scalars(select(AudioFile.id).where(AudioFile.root_id == root.id)):
        stacca_file(db, file_id)
```

- [ ] **Step 6: Suite completa**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/backend && .venv/bin/python -m pytest tests -q
```

Atteso: tutto verde.

- [ ] **Step 7: Commit**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1 && \
git add -A backend/app/organize backend/tests/organize && \
git commit -m "fix(f3a): stacca_file prima di ogni cancellazione di AudioFile"
```

---

### Task 5: Manutenzione di `primary_file_id` dove si scrivono i `local_*`

**Files:**
- Modify: `backend/app/services/library_index.py` (righe ~148, ~176, ~374)
- Modify: `backend/app/services/acquisition.py` (riga ~26)
- Test: `backend/tests/test_primary_file_id_cache.py`

**Interfaces:**
- Consumes: `app.organize.services.file_link.aggiorna_primary`

**Il contratto.** `primary_file_id` dice da quale file arrivano i `local_*`. Quindi ogni punto che scrive `local_path` deve allineare anche `primary_file_id`: sono quattro, e sono tutti già identificati.

| file | riga | cosa fa |
|---|---|---|
| `library_index.py` | ~148 `_own` | la traccia acquisisce il file |
| `library_index.py` | ~176 `_discard` | la traccia perde il possesso (file archiviato) |
| `library_index.py` | ~374 | spazzata dei file spariti |
| `acquisition.py` | ~26 | download Soulseek/SoundCloud agganciato alla traccia |

- [ ] **Step 1: Scrivere il test che fallisce**

Crea `backend/tests/test_primary_file_id_cache.py`:

```python
"""primary_file_id è la cache che dice DA QUALE file vengono i local_*:
ogni punto che scrive local_path deve allinearla."""

from app.models import Track
from app.organize.models import AudioFile, ScanRoot
from app.organize.services.file_link import aggiorna_primary

LIB = "/lib"


def _radice_e_file(db, path: str) -> AudioFile:
    r = ScanRoot(path=LIB)
    db.add(r)
    db.flush()
    f = AudioFile(root_id=r.id, path=path, ext=".flac", size_bytes=1,
                  hash_method="stream", status="present", location="library")
    db.add(f)
    db.flush()
    return f


def test_possesso_allinea_primary_file_id(db):
    f = _radice_e_file(db, f"{LIB}/a.flac")
    t = Track(source_type="manual")
    db.add(t)
    db.flush()

    t.local_path = f"{LIB}/a.flac"
    t.has_local_file = True
    aggiorna_primary(db, t)
    db.commit()

    assert t.primary_file_id == f.id


def test_perdita_del_possesso_azzera_primary_file_id(db):
    f = _radice_e_file(db, f"{LIB}/a.flac")
    t = Track(source_type="manual", has_local_file=True, local_path=f"{LIB}/a.flac",
              primary_file_id=f.id)
    db.add(t)
    db.commit()

    t.local_path = None
    t.has_local_file = False
    aggiorna_primary(db, t)
    db.commit()

    assert t.primary_file_id is None
```

- [ ] **Step 2: Lanciare il test e verificare che fallisca**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/backend && .venv/bin/python -m pytest tests/test_primary_file_id_cache.py -v
```

Atteso: FAIL sul primo test (`primary_file_id` resta `None`) se `aggiorna_primary` non è ancora chiamato — oppure PASS, dato che il test chiama l'helper direttamente. **Se passa già, va bene**: il valore di questo test è di rete, e il collegamento vero lo verifica lo Step 5.

- [ ] **Step 3: Innestare la chiamata nei quattro punti**

In `library_index.py`, in fondo a `_own` (dopo `track.local_bitrate = …`):

```python
    aggiorna_primary(db, track)
```

`_own` e `_discard` oggi non ricevono `db`: aggiungilo come primo parametro (`def _own(db: Session, track: Track, *, path: Path, digest: str)`) e aggiorna i chiamanti — sono nello stesso modulo.

Idem in fondo a `_discard`, e nella spazzata intorno alla riga 374, dentro il ciclo che azzera i `local_*`.

In `acquisition.py`, dopo `track.local_bitrate = …`:

```python
    aggiorna_primary(db, track)
```

Import in entrambi i moduli:

```python
from app.organize.services.file_link import aggiorna_primary
```

**Nota sulla direzione delle dipendenze**: qui `app/services/` importa da `app/organize/services/`. È il primo punto in cui il core dipende da Organize, e va bene perché `file_link` è per natura il ponte fra i due; ma è anche il motivo per cui quel modulo deve restare piccolo e senza importare altro da Organize, per non aprire un ciclo.

- [ ] **Step 4: Lanciare i test**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/backend && .venv/bin/python -m pytest tests/test_primary_file_id_cache.py tests -q
```

Atteso: tutto verde.

- [ ] **Step 5: Verificare il collegamento davvero, non solo l'helper**

Un'indicizzazione vera su una cartella temporanea, che è l'unico modo per sapere se le chiamate sono nei punti giusti:

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/backend && \
.venv/bin/python -m pytest tests -q -k "library_index"
```

Atteso: verdi. Se un test di `library_index` fallisce per la firma cambiata di `_own`/`_discard`, aggiornalo: è un cambio di firma voluto.

- [ ] **Step 6: Commit**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1 && \
git add -A backend/app/services backend/tests && \
git commit -m "feat(f3a): primary_file_id mantenuto dove si scrivono i local_*"
```

---

### Task 5b: Lo scanner deve derivare `location`

**Files:**
- Modify: `backend/app/organize/services/scanner.py`
- Test: `backend/tests/organize/test_scanner_location.py`

**Il buco che questo task chiude.** Il piano trattava `location` come se bastasse
il backfill una tantum. Non basta: lo scanner crea gli `AudioFile` senza passare
`location`, quindi cadono sul default del modello (`"inbox"`) — e un file nuovo in
`LIBRARY_ROOT` nasce etichettato `inbox`. Il campo si degrada **dal primo scan
dopo il backfill**, in silenzio, perché nessun invariante lo vede: "location vuota
= 0" resta vero, è il valore a essere sbagliato.

Due punti, non uno:

1. la creazione della riga;
2. il ramo `moved` del riconcilio, dove `row.path` cambia — un file può aver
   attraversato il confine inbox↔library, ed è esattamente ciò che fa un Apply.

Un path fuori da entrambe le radici non è libreria canonica per definizione:
`"inbox"` è la risposta conservativa, con un `logger.warning` che nomina il path,
così una `ScanRoot` incoerente emerge invece di passare muta. Con F3b, tolte le
ScanRoot, il caso sparisce.

- [ ] **Step 1: Test che fallisce** — due file veri, uno per radice, `scanner.scan`,
  e l'asserzione su `location`. L'entry point è `scanner.scan(db, roots)`.
- [ ] **Step 2: `_location_per(path)`** in `scanner.py`, che incapsula
  `deriva_location` più il fallback con warning.
- [ ] **Step 3: usarla** nella `AudioFile(...)` e nel ramo `moved`.
- [ ] **Step 4: suite completa e commit.**

---

### Task 6: Backfill sui dati reali

**Files:**
- Create: `backend/app/tools/backfill_track_files.py`
- Test: `backend/tests/test_backfill_track_files.py`

**Interfaces:**
- Produces: `backfill(db, *, library_root: str, inbox_root: str, dry_run: bool) -> Report`, dove `Report` ha `location_library`, `location_inbox`, `location_fuori`, `agganciati`, `primary`, `coppie_attese`, più `ok()` e `render()`
- CLI: `python -m app.tools.backfill_track_files [--apply]`

- [ ] **Step 1: Scrivere il test che fallisce**

Crea `backend/tests/test_backfill_track_files.py`:

```python
"""Backfill di location, track_id e primary_file_id sui dati esistenti."""

import pytest
from sqlalchemy import select

from app.models import Track
from app.organize.models import AudioFile, ScanRoot
from app.tools.backfill_track_files import backfill

LIB = "/lib"
INBOX = "/inbox"


@pytest.fixture()
def dati(db):
    r = ScanRoot(path=LIB)
    db.add(r)
    db.flush()
    files = [
        AudioFile(root_id=r.id, path=f"{LIB}/a.flac", ext=".flac", size_bytes=1,
                  hash_method="stream", status="present"),
        AudioFile(root_id=r.id, path=f"{LIB}/b.flac", ext=".flac", size_bytes=1,
                  hash_method="stream", status="present"),
        AudioFile(root_id=r.id, path=f"{INBOX}/c.mp3", ext=".mp3", size_bytes=1,
                  hash_method="stream", status="present"),
    ]
    db.add_all(files)
    # Solo il primo file ha una traccia che lo rivendica.
    db.add(Track(source_type="manual", has_local_file=True, local_path=f"{LIB}/a.flac"))
    db.commit()
    return files


def test_dry_run_non_scrive(db, dati):
    report = backfill(db, library_root=LIB, inbox_root=INBOX, dry_run=True)
    assert report.ok()
    assert report.agganciati == 1

    # backfill() ha già fatto rollback: gli oggetti in sessione sono scaduti e
    # rileggendo si torna allo stato committato dalla fixture.
    assert db.scalars(select(AudioFile.track_id)).all() == [None, None, None]


def test_backfill_assegna_location_e_agganci(db, dati):
    report = backfill(db, library_root=LIB, inbox_root=INBOX, dry_run=False)
    db.commit()

    assert report.location_library == 2
    assert report.location_inbox == 1
    assert report.location_fuori == 0
    assert report.agganciati == 1
    assert report.primary == report.agganciati  # simmetria

    a = db.scalar(select(AudioFile).where(AudioFile.path == f"{LIB}/a.flac"))
    t = db.scalar(select(Track).where(Track.local_path == f"{LIB}/a.flac"))
    assert a.track_id == t.id
    assert t.primary_file_id == a.id
    assert a.location == "library"


def test_un_path_fuori_dalle_radici_fa_fallire(db, dati):
    db.add(AudioFile(root_id=dati[0].root_id, path="/altrove/x.flac", ext=".flac",
                     size_bytes=1, hash_method="stream", status="present"))
    db.commit()

    report = backfill(db, library_root=LIB, inbox_root=INBOX, dry_run=True)
    assert report.location_fuori == 1
    assert not report.ok()
```

- [ ] **Step 2: Lanciare il test e verificare che fallisca**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/backend && .venv/bin/python -m pytest tests/test_backfill_track_files.py -v
```

Atteso: FAIL con `ModuleNotFoundError`.

- [ ] **Step 3: Scrivere lo script**

Crea `backend/app/tools/backfill_track_files.py`:

```python
"""Backfill di AudioFile.location, AudioFile.track_id e Track.primary_file_id.

Assert su invarianti, non su costanti: i numeri del DB reale cambiano a ogni
uso dell'app (in F2 erano già cambiati fra due misure nella stessa giornata).

Uso:
    python -m app.tools.backfill_track_files            # dry-run
    python -m app.tools.backfill_track_files --apply
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Track
from app.organize.models import AudioFile
from app.organize.services.file_link import deriva_location


@dataclass
class Report:
    location_library: int = 0
    location_inbox: int = 0
    location_fuori: int = 0
    agganciati: int = 0
    primary: int = 0
    coppie_attese: int = 0
    dry_run: bool = True

    def ok(self) -> bool:
        return (
            self.location_fuori == 0
            and self.agganciati == self.primary          # simmetria delle due facce
            and self.agganciati == self.coppie_attese    # nessuna coppia persa
        )

    def render(self) -> str:
        return "\n".join([
            f"{'DRY-RUN' if self.dry_run else 'BACKFILL'}",
            f"  location=library   {self.location_library:>6}",
            f"  location=inbox     {self.location_inbox:>6}",
            f"  fuori dalle radici {self.location_fuori:>6}   (deve essere 0)",
            f"  track_id assegnati {self.agganciati:>6} / {self.coppie_attese} attesi",
            f"  primary_file_id    {self.primary:>6}   (deve uguagliare i track_id)",
            f"  esito: {'OK' if self.ok() else 'FALLITO'}",
        ])


def backfill(db: Session, *, library_root: str, inbox_root: str, dry_run: bool) -> Report:
    report = Report(dry_run=dry_run)

    # Quante coppie ci aspettiamo: il join per path assoluto, calcolato PRIMA
    # di toccare qualsiasi cosa. È l'invariante contro cui si misura l'esito.
    report.coppie_attese = db.scalar(
        select(func.count())
        .select_from(Track)
        .join(AudioFile, AudioFile.path == Track.local_path)
        .where(Track.has_local_file.is_(True), Track.local_path.is_not(None))
    ) or 0

    per_path: dict[str, AudioFile] = {}
    for file in db.scalars(select(AudioFile)):
        try:
            loc = deriva_location(file.path, library_root=library_root, inbox_root=inbox_root)
        except ValueError:
            report.location_fuori += 1
            continue
        file.location = loc
        if loc == "library":
            report.location_library += 1
        else:
            report.location_inbox += 1
        per_path[file.path] = file

    for track in db.scalars(
        select(Track).where(Track.has_local_file.is_(True), Track.local_path.is_not(None))
    ):
        file = per_path.get(track.local_path)
        if file is None:
            continue
        file.track_id = track.id
        track.primary_file_id = file.id
        report.agganciati += 1
        report.primary += 1

    if dry_run or not report.ok():
        db.rollback()
    else:
        db.flush()
    return report


def main() -> int:
    from app.core.config import settings
    from app.db import SessionLocal

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    with SessionLocal() as db:
        report = backfill(db, library_root=settings.library_root,
                          inbox_root=settings.slskd_download_dir,
                          dry_run=not args.apply)
        print(report.render())
        if args.apply and report.ok():
            db.commit()
            print("backfill applicato")
    return 0 if report.ok() else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Lanciare i test**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/backend && .venv/bin/python -m pytest tests/test_backfill_track_files.py -v
```

Atteso: 3 passed.

- [ ] **Step 5: Dry-run sui dati reali**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/backend && \
.venv/bin/python -m app.tools.backfill_track_files \
  --db /Users/lucadenegri/Develop/DJProject01/backend/data/djassistant.db
```

Atteso, come ordine di grandezza: `library` intorno a 650, `inbox` intorno a 1128, `fuori` **0**, `track_id` e `primary_file_id` **624** e uguali fra loro, `esito: OK`.

`fuori` diverso da 0 significa che `LIBRARY_ROOT`/`SLSKD_DOWNLOAD_DIR` in `.env` non coprono le radici di `scan_root`: **fermati e riconcilia la configurazione**, non allargare il criterio.

- [ ] **Step 6: Backfill reale**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/backend && \
.venv/bin/python -m app.tools.backfill_track_files \
  --db /Users/lucadenegri/Develop/DJProject01/backend/data/djassistant.db --apply
```

Atteso: stesso report, `backfill applicato`.

- [ ] **Step 7: Commit**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1 && \
git add backend/app/tools/backfill_track_files.py backend/tests/test_backfill_track_files.py && \
git commit -m "feat(f3a): backfill di location, track_id e primary_file_id"
```

---

### Task 7: Verifica di fase

- [ ] **Step 1: Invarianti sul DB reale**

```bash
sqlite3 /Users/lucadenegri/Develop/DJProject01/backend/data/djassistant.db "
select 'file totali', count(*) from audio_file
union all select 'location=library', count(*) from audio_file where location='library'
union all select 'location=inbox', count(*) from audio_file where location='inbox'
union all select 'location vuota', count(*) from audio_file where location is null or location=''
union all select 'track_id valorizzati', count(*) from audio_file where track_id is not null
union all select 'primary_file_id', count(*) from tracks where primary_file_id is not null
union all select 'asimmetrie', count(*) from tracks t
    where t.primary_file_id is not null
      and not exists (select 1 from audio_file f where f.id=t.primary_file_id and f.track_id=t.id)
union all select 'primary orfani', count(*) from tracks t
    where t.primary_file_id is not null
      and not exists (select 1 from audio_file f where f.id=t.primary_file_id)
union all select 'track_id orfani', count(*) from audio_file f
    where f.track_id is not null
      and not exists (select 1 from tracks t where t.id=f.track_id);"
```

Atteso: `location vuota` **0**, `asimmetrie` **0**, `primary orfani` **0**, `track_id orfani` **0**, e `track_id valorizzati` uguale a `primary_file_id`.

- [ ] **Step 2: La milestone della spec — nessuna query di Cratory modificata**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1 && \
git diff --stat master..feat/fusione-f1 -- backend/app/routers backend/app/repositories.py backend/app/serializers.py
```

Atteso: **nessuna modifica** a `routers/` e `repositories.py` da parte di F3a. Se F1/F2 li avevano già toccati, isola il confronto ai commit di questa fase:

```bash
git diff --stat $(git log --format=%H -n1 --grep="f3a" --reverse)^..HEAD -- backend/app/routers backend/app/repositories.py
```

- [ ] **Step 3: Suite completa e frontend**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1/backend && .venv/bin/python -m pytest tests -q
cd ../frontend && npm run lint && npm run build && npm run test:unit
```

Atteso: tutti verdi. Riporta i conteggi.

- [ ] **Step 4: Verificare che qualcosa AGISCA, non solo che carichi**

La lezione di F1, applicata a questa fase: le colonne nuove non si vedono in nessuna UI, quindi l'unico modo di sapere se il modello regge è **esercitare i due versi della relazione** sui dati veri.

Avvia backend e frontend, poi:

1. Da `/library`, apri una traccia posseduta e verifica che suoni ancora e mostri BPM/key — è la prova che i `local_*` non si sono rotti.
2. Lancia uno scan da `/organize` e ricontrolla gli invarianti dello Step 1: uno scan che rigenera l'indice **non deve** creare asimmetrie né orfani.

```bash
sqlite3 /Users/lucadenegri/Develop/DJProject01/backend/data/djassistant.db "
select count(*) from tracks t where t.primary_file_id is not null
  and not exists (select 1 from audio_file f where f.id=t.primary_file_id and f.track_id=t.id);"
```

Atteso dopo lo scan: `0`. Se non lo è, manca una chiamata ad `aggiorna_primary` in un percorso dello scanner — ed è meglio scoprirlo qui che in F4, quando lo scanner verrà riscritto.

- [ ] **Step 5: Commit finale e riepilogo**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/fusione-f1 && \
git status --porcelain && git add -A docs && \
git commit -m "docs(f3a): F3a completata — modello Track 1-N AudioFile agganciato"
```

Riporta: numero di test verdi, i valori degli invarianti dello Step 1, e se lo scan dello Step 4 ha retto. Servono a F3b, che parte da qui per togliere `scan_root`.

---

## Definizione di "F3a completa"

- `Track.primary_file_id`, `AudioFile.track_id`, `AudioFile.location` esistono e sono valorizzate.
- Le due facce della relazione sono simmetriche: zero asimmetrie, zero orfani in entrambe le direzioni.
- Nessun `AudioFile` con `location` vuota; zero file fuori dalle due radici.
- `location` è **derivata anche dallo scanner**, non solo dal backfill: uno scan
  dopo il backfill non deve riportare file di `Library/` a `inbox`. Attenzione,
  l'invariante "location vuota = 0" non basta a vederlo — il default del modello
  è un valore valido ma sbagliato.
- Le due `Track` sullo stesso file sono una sola; l'invariante è protetto da un test.
- `stacca_file` è chiamata in ogni punto che cancella un `AudioFile`.
- `primary_file_id` è mantenuta nei quattro punti che scrivono i `local_*`.
- Uno scan reale non introduce asimmetrie.
- `routers/` e `repositories.py` di Cratory **non** sono stati toccati.
- `scan_root` e `root_targets` esistono ancora — è corretto: è F3b.
