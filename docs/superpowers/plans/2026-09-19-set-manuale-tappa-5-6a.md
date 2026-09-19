# Set manuale, tappa 5 e «riempi il varco» — piano di implementazione

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Il set preparato a mano sa dire quanto dura davvero e quando la stima è incompleta; si esporta come i set generati, più una scheda di preparazione e l'elenco delle riserve, con l'anteprima identica al file; e un varco si può far riempire dal generatore, che propone N tracce fra le due ai suoi lati — proposte che entrano come righe normali, modificabili e annullabili.

**Architecture:** Un concetto solo, il **percorso risolto** (blocchi `main` in ordine, sole righe `track`, i varchi interrompono l'adiacenza), calcolato in un posto solo e usato da durata, export e riempimento. La durata è `planned_seconds` per riga con fallback sulla durata del file. Gli export esistenti smettono di essere riservati ai set generati e imparano a leggere il percorso risolto. «Riempi il varco» non è un generatore nuovo: è `_beam_search_span`, già in `set_generator.py`, con un criterio di stop a conteggio accanto a quello a secondi.

**Tech Stack:** Python 3 + FastAPI + SQLAlchemy 2 (SQLite, migrazioni idempotenti in `db.py`), Pydantic v2, pytest. Next.js 16 App Router, React, Tailwind, vitest + @testing-library/react, Playwright.

**Spec:** `docs/superpowers/specs/2026-09-15-set-builder-workbench.md` («Tappa 5 — Durata ed export», la prima metà di «Tappa 6 — Il generatore come strumento», e la definizione di *percorso risolto* in fondo alla sezione 4).

## Global Constraints

- Backend: `cd backend && .venv/bin/python -m pytest tests -q` deve restare verde. Baseline a inizio tappa: **2598 passed, 4 deselected**.
- Frontend baseline: **643 test in 104 file**, `npx tsc --noEmit` pulito, `npm run lint` senza errori (4 warning pre-esistenti non correlati), `npm run build` verde, e2e `set-builder.spec.ts` verde (3 test).
- Migrazioni: solo dentro `ensure_schema` in `backend/app/db.py`, idempotenti. La colonna nuova la aggiunge `_migrate_add_model_columns`. Nessun rebuild, nessuna tabella nuova in questo piano.
- Errori HTTP: sempre `api_error(status, code, message, **params)`; ogni `code` nuovo tradotto in `frontend/lib/i18n/en.ts` **e** `it.ts` sotto `errors`.
- I set `manual` non passano mai da `assign_roles`, `_reassign_roles`, `recompute_transitions`. **Nemmeno «riempi il varco» li fa passare di lì**: propone tracce, non assegna ruoli né punteggi salvati.
- Ogni mutazione controlla `expected_revision`, muta, salva uno snapshot e committa nella stessa transazione. Un conflitto lascia il database intatto.
- Le righe e i blocchi si identificano per id, mai per posizione.
- **Nessuna chiamata AI.** `_beam_search_span` accetta `mood_scores`, che è il gancio della curatela: «riempi il varco» passa sempre `None`. Con o senza chiave AI configurata, questo piano non fa partire nessuna richiesta.
- Frontend: leggere `frontend/CLAUDE.md`. Nessuna stringa user-facing fuori dai dizionari; chiavi in `en.ts` prima, poi `it.ts`. Spazi fra elementi inline: `{" "}` esplicito.
- Commit in italiano, stile `feat(sets): …`, nessun `Co-Authored-By`. Prima di ogni commit `git status --porcelain`, stage dei soli file del task; revertare `frontend/package-lock.json` e `frontend/tsconfig.json` se risultano modificati.

## Cosa questa tappa NON fa, e perché

**La demolizione del vecchio generatore e della curatela AI resta fuori.** La spec la mette nella tappa 6 insieme a «riempi il varco», ma sono due lavori di natura opposta: uno aggiunge, l'altro toglie 12 file sorgente, 12 file di test, quattro colonne del modello e una pagina intera. Si fa dopo, con un piano suo, quando il sostituto è in piedi e provato — perché è «riempi il varco» a giustificare la sopravvivenza del beam search, e smontare per primo lascerebbe senza rete. Deciso con l'utente il 2026-09-19.

Fuori anche: l'ascolto a due piatti (cantiere a sé) e ogni forma di ruolo o punteggio salvato sulle righe di un set manuale.

---

## File structure

| File | Responsabilità |
|---|---|
| `backend/app/models.py` | `SetlistTrack.planned_seconds` |
| `backend/app/services/manual_set.py` | `resolved_path`, `set_duration`, `planned_seconds` in `update_row` |
| `backend/app/services/manual_fill.py` (nuovo) | «Riempi il varco»: contesto, proposta, applicazione |
| `backend/app/services/set_generator.py` | `_beam_search_span` impara a fermarsi a conteggio |
| `backend/app/services/manual_export.py` (nuovo) | I formati del set manuale, uno per funzione |
| `backend/app/routers/sets.py` | Export che accetta i manual, `fill-gap`, `planned_seconds` |
| `backend/app/schemas.py`, `backend/app/serializers.py` | Durata, stima incompleta, proposta |
| `backend/tests/test_set_manual_duration.py` (nuovo) | Durata e stima incompleta |
| `backend/tests/test_set_manual_export.py` (nuovo) | I formati, e l'anteprima uguale al file |
| `backend/tests/test_set_manual_fill.py` (nuovo) | Proposta, vincoli, applicazione, annulla |
| `frontend/components/set-builder/fill-gap-panel.tsx` (nuovo) | La proposta da accettare o scartare |
| `frontend/components/set-builder/export-menu.tsx` (nuovo) | Export con anteprima |
| `frontend/app/sets/manual/page.tsx` | Durata in testa, export, riempimento |
| `frontend/tests/set-builder-duration-export.test.tsx`, `set-builder-fill.test.tsx` (nuovi) | I gesti |
| `docs/API.md`, `docs/ARCHITECTURE.md`, `PROGRESS.md`, `docs/ROADMAP.md`, `frontend/e2e/set-builder.spec.ts` | Documentazione e verifica |

---

### Task 1: Il percorso risolto e la durata

**Files:**
- Modify: `backend/app/models.py`, `backend/app/services/manual_set.py`
- Test: `backend/tests/test_set_manual_duration.py` (nuovo)

**Interfaces:**
- Produces:

```python
# models
SetlistTrack.planned_seconds: int | None   # contributo netto alla durata

# manual_set
@dataclass(frozen=True)
class SetDuration:
    seconds: int          # somma dei contributi noti
    incomplete: bool      # manca un valore, o c'e' un varco aperto
    unknown_rows: int     # righe track senza durata ne' planned_seconds
    open_gaps: int

def resolved_path(setlist) -> list[SetlistTrack]
    """La proiezione che contano export, durata e compatibilita': blocchi `main`
    in ordine, SOLE righe `track` con la traccia attiva. Banco, riserva e
    alternative non ci entrano; i varchi non ci entrano come righe, ma la loro
    presenza resta leggibile da `set_duration`."""

def set_duration(setlist) -> SetDuration
```

`update_row` guadagna `planned_seconds`, con la stessa sentinella `UNSET` di `note` e `play_bpm`.

**Perché `resolved_path` non è `path_rows`.** `path_rows` (tappa 1) include i varchi, e serve così a chi disegna il percorso. Export e durata vogliono invece la proiezione senza varchi. Due nomi diversi per due cose diverse: fonderli obbligherebbe ogni chiamante a ricordarsi di filtrare, e prima o poi qualcuno se ne dimentica.

- [ ] **Step 1: Scrivi i test che falliscono**

`backend/tests/test_set_manual_duration.py`:

```python
"""Durata del set manuale (tappa 5): percorso risolto e stima incompleta."""
from app.models import Track
from app.services.manual_set import (
    create_manual_set, insert_rows, path_rows, resolved_path, set_duration, update_row,
)


def _tracce(db, n, durata=300):
    out = []
    for i in range(n):
        t = Track(source_type="spotify", title=f"T{i}", bpm=124.0, camelot_key="8A",
                  duration_seconds=durata, has_local_file=True)
        db.add(t)
        out.append(t)
    db.commit()
    return out


def _set(db, tracce):
    s = create_manual_set(db, name="M", playlist_id=None)
    return insert_rows(db, s.id, expected_revision=0, track_ids=[t.id for t in tracce],
                       gap=False, after_row_id=None)


def test_il_percorso_risolto_lascia_fuori_varchi_riserva_e_banco(db):
    t = _tracce(db, 2)
    s = _set(db, t)
    riga = path_rows(s)[0]
    s = insert_rows(db, s.id, expected_revision=1, track_ids=[], gap=True, after_row_id=riga.id)
    da_parte = _tracce(db, 1)[0]
    s = insert_rows(db, s.id, expected_revision=2, track_ids=[da_parte.id], gap=False,
                    after_row_id=None, reserve=True)
    assert len(path_rows(s)) == 3            # il varco c'e', per chi disegna
    assert [r.track_id for r in resolved_path(s)] == [t[0].id, t[1].id]


def test_la_durata_somma_i_file(db):
    t = _tracce(db, 3, durata=300)
    s = _set(db, t)
    d = set_duration(s)
    assert d.seconds == 900
    assert d.incomplete is False
    assert (d.unknown_rows, d.open_gaps) == (0, 0)


def test_la_durata_pianificata_batte_quella_del_file(db):
    """`planned_seconds` e' il contributo NETTO: la traccia dura 5 minuti ma in
    questo set la si tiene due, e il totale deve dire due."""
    t = _tracce(db, 2, durata=300)
    s = _set(db, t)
    riga = path_rows(s)[0]
    s = update_row(db, s.id, riga.id, expected_revision=1, planned_seconds=120)
    assert set_duration(s).seconds == 420     # 120 + 300


def test_una_traccia_senza_durata_rende_la_stima_incompleta(db):
    t = _tracce(db, 2, durata=300)
    senza = Track(source_type="spotify", title="X", has_local_file=True)
    db.add(senza)
    db.commit()
    s = _set(db, t + [senza])
    d = set_duration(s)
    assert d.seconds == 600        # somma solo cio' che sa
    assert d.incomplete is True
    assert d.unknown_rows == 1


def test_una_durata_pianificata_salva_la_stima_di_una_traccia_senza_file(db):
    t = _tracce(db, 1, durata=300)
    senza = Track(source_type="spotify", title="X", has_local_file=True)
    db.add(senza)
    db.commit()
    s = _set(db, t + [senza])
    riga = path_rows(s)[1]
    s = update_row(db, s.id, riga.id, expected_revision=1, planned_seconds=240)
    d = set_duration(s)
    assert (d.seconds, d.incomplete, d.unknown_rows) == (540, False, 0)


def test_un_varco_aperto_rende_la_stima_incompleta(db):
    t = _tracce(db, 2, durata=300)
    s = _set(db, t)
    riga = path_rows(s)[0]
    s = insert_rows(db, s.id, expected_revision=1, track_ids=[], gap=True, after_row_id=riga.id)
    d = set_duration(s)
    assert d.seconds == 600
    assert d.incomplete is True
    assert d.open_gaps == 1


def test_la_durata_pianificata_si_azzera(db):
    t = _tracce(db, 1, durata=300)
    s = _set(db, t)
    riga = path_rows(s)[0]
    s = update_row(db, s.id, riga.id, expected_revision=1, planned_seconds=120)
    s = update_row(db, s.id, riga.id, expected_revision=2, planned_seconds=None)
    assert set_duration(s).seconds == 300


def test_scrivere_l_appunto_non_azzera_la_durata_pianificata(db):
    """Terza proprieta' sulla stessa PATCH parziale: la sentinella vale anche qui."""
    t = _tracce(db, 1, durata=300)
    s = _set(db, t)
    riga = path_rows(s)[0]
    s = update_row(db, s.id, riga.id, expected_revision=1, planned_seconds=120)
    s = update_row(db, s.id, riga.id, expected_revision=2, note="ciao")
    assert path_rows(s)[0].planned_seconds == 120
```

- [ ] **Step 2: Esegui e verifica che falliscano**

Run: `cd backend && .venv/bin/python -m pytest tests/test_set_manual_duration.py -q -p no:cacheprovider`
Expected: FAIL con `ImportError: cannot import name 'resolved_path'`.

- [ ] **Step 3: Il modello**

In `backend/app/models.py`, dentro `class SetlistTrack`, subito dopo `play_bpm`:

```python
    # Contributo NETTO alla durata del set: quanto si tiene questa traccia in
    # questo set. None = la durata del file. Non tocca `Track.duration_seconds`.
    planned_seconds: Mapped[int | None] = mapped_column(Integer)
```

- [ ] **Step 4: Percorso risolto e durata**

In `backend/app/services/manual_set.py`, importa `from dataclasses import dataclass` in cima e aggiungi, subito dopo `path_rows`:

```python
def resolved_path(setlist: Setlist) -> list[SetlistTrack]:
    """La proiezione che contano export, durata e compatibilita': blocchi `main`
    in ordine, SOLE righe con la traccia attiva.

    Diverso da `path_rows`, che tiene i varchi perche' chi disegna il percorso
    deve vederli. Tenerli separati evita che ogni chiamante si ricordi di
    filtrare — e prima o poi qualcuno se ne dimentica.
    """
    return [r for r in path_rows(setlist) if r.track is not None]


@dataclass(frozen=True)
class SetDuration:
    seconds: int
    incomplete: bool
    unknown_rows: int
    open_gaps: int


def set_duration(setlist: Setlist) -> SetDuration:
    """Durata del percorso. `planned_seconds` vince sulla durata del file; una
    riga senza ne' l'uno ne' l'altra non si inventa, si dichiara."""
    seconds = 0
    unknown = 0
    for row in resolved_path(setlist):
        contributo = row.planned_seconds
        if contributo is None:
            contributo = row.track.duration_seconds
        if contributo is None:
            unknown += 1
            continue
        seconds += contributo
    gaps = sum(1 for r in path_rows(setlist) if r.track is None)
    return SetDuration(seconds=seconds, incomplete=bool(unknown or gaps),
                       unknown_rows=unknown, open_gaps=gaps)
```

e in `update_row`, dopo il blocco di `play_bpm`:

```python
    if not isinstance(planned_seconds, _Unset):
        if planned_seconds is not None and not 1 <= planned_seconds <= 3600:
            raise ManualSetError(f"Planned seconds {planned_seconds} out of range 1..3600")
        row.planned_seconds = planned_seconds
```

con la firma che guadagna `planned_seconds: int | None | _Unset = UNSET`.

- [ ] **Step 5: Esegui e verifica**

Run: `cd backend && .venv/bin/python -m pytest tests/test_set_manual_duration.py -q -p no:cacheprovider` → verdi.

Poi dimostra che mordono: in `set_duration`, sostituisci `contributo = row.planned_seconds` con `contributo = None` e verifica che `test_la_durata_pianificata_batte_quella_del_file` fallisca; poi togli `or gaps` da `incomplete` e verifica che cada `test_un_varco_aperto_rende_la_stima_incompleta`. Ripristina.

- [ ] **Step 6: Suite completa e commit**

Run: `cd backend && .venv/bin/python -m pytest tests -q -p no:cacheprovider` → 2606 passed (2598 + gli 8 del file nuovo).

```bash
git add backend/app/models.py backend/app/services/manual_set.py backend/tests/test_set_manual_duration.py
git commit -m "feat(sets): il percorso risolto e la durata del set manuale"
```

---

### Task 2: Gli export del set manuale

**Files:**
- Create: `backend/app/services/manual_export.py`
- Modify: `backend/app/routers/sets.py`, `backend/app/schemas.py`, `backend/app/serializers.py`
- Test: `backend/tests/test_set_manual_export.py` (nuovo), `backend/tests/test_set_manual_api.py` (in coda)

**Interfaces:**
- Consumes: Task 1 (`resolved_path`, `set_duration`).
- Produces:

```python
MANUAL_FORMATS = ("text", "csv", "markdown", "m3u8", "prep", "reserve")

def render_manual(setlist: Setlist, fmt: str, lang: str) -> tuple[str, str]
    """(contenuto, media_type). `prep` e' la scheda di preparazione (sequenze,
    alternative, appunti, varchi); `reserve` e' l'elenco delle riserve."""
```

L'endpoint export esistente smette di rifiutare i set manuali: per `kind == "manual"` delega a `render_manual`, per gli altri resta esattamente com'è. **L'anteprima non è un secondo renderer**: la pagina chiede lo stesso endpoint e mostra ciò che riceve, così «anteprima uguale al file prodotto» è vero per costruzione e non per disciplina.

**Sui file mancanti.** L'M3U8 punta ai file su disco: una riga senza file non può starci. Come per i set generati, si esclude e si dichiara nel commento di testa. Nella scheda di preparazione, invece, una traccia senza file si segna «non disponibile» ma **resta**: è una decisione del DJ, e l'export che la nascondesse mentirebbe.

- [ ] **Step 1: Scrivi i test che falliscono**

`backend/tests/test_set_manual_export.py`:

```python
"""Export del set manuale (tappa 5): i formati, e cio' che l'anteprima mostra."""
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


def _set_ricco(client, db):
    """Un set con tutto dentro: due tracce (una senza file), un varco, una
    riserva, una sequenza con nome, una alternativa e un appunto."""
    tracce = []
    for i in range(4):
        t = Track(source_type="spotify", title=f"T{i}", artist=f"A{i}", bpm=124.0,
                  camelot_key="8A", duration_seconds=300, has_local_file=(i != 1),
                  local_path=(f"/lib/t{i}.mp3" if i != 1 else None))
        db.add(t)
        tracce.append(t)
    db.commit()
    sid = client.post("/api/sets/manual", json={"name": "Sabato"}).json()["id"]
    doc = client.post(f"/api/sets/{sid}/rows", json={
        "expected_revision": 0, "track_ids": [tracce[0].id, tracce[1].id]}).json()
    righe = [r for b in doc["blocks"] if b["placement"] == "main" for r in b["rows"]]
    doc = client.patch(f"/api/sets/{sid}/rows/{righe[0]['id']}", json={
        "expected_revision": 1, "note": "apre piano"}).json()
    doc = client.post(f"/api/sets/{sid}/rows", json={
        "expected_revision": 2, "gap": True, "after_row_id": righe[0]["id"]}).json()
    doc = client.post(f"/api/sets/{sid}/rows", json={
        "expected_revision": 3, "track_ids": [tracce[2].id], "reserve": True}).json()
    doc = client.post(f"/api/sets/{sid}/rows/{righe[0]['id']}/alternatives", json={
        "expected_revision": 4, "track_ids": [tracce[3].id]}).json()
    doc = client.post(f"/api/sets/{sid}/blocks", json={
        "expected_revision": 5, "row_ids": [righe[0]["id"], righe[1]["id"]],
        "name": "Apertura"}).json()
    return sid, tracce


def test_il_testo_elenca_il_percorso_risolto(client_db):
    client, db = client_db
    sid, t = _set_ricco(client, db)
    r = client.post(f"/api/sets/{sid}/export?format=text")
    assert r.status_code == 200, r.text
    testo = r.text
    assert "T0" in testo and "T1" in testo
    assert "T2" not in testo          # la riserva non e' il set


def test_l_m3u8_esclude_i_file_mancanti_e_lo_dice(client_db):
    client, db = client_db
    sid, t = _set_ricco(client, db)
    r = client.post(f"/api/sets/{sid}/export?format=m3u8")
    corpo = r.text
    assert "/lib/t0.mp3" in corpo
    assert "/lib/t1.mp3" not in corpo   # quella traccia non ha file
    assert "1" in corpo                  # il conteggio dichiarato nel commento


def test_la_scheda_di_preparazione_porta_tutto_cio_che_serve_in_cabina(client_db):
    client, db = client_db
    sid, t = _set_ricco(client, db)
    r = client.post(f"/api/sets/{sid}/export?format=prep")
    md = r.text
    assert "Apertura" in md          # la sequenza col suo nome
    assert "apre piano" in md        # l'appunto di riga
    assert "T3" in md                # l'alternativa tenuta da parte
    assert "T1" in md                # la traccia senza file RESTA
    # ...e si dichiara, invece di sparire.
    assert md.count("—") >= 0 and "T1" in md


def test_l_export_delle_riserve_elenca_solo_quelle(client_db):
    client, db = client_db
    sid, t = _set_ricco(client, db)
    r = client.post(f"/api/sets/{sid}/export?format=reserve")
    corpo = r.text
    assert "T2" in corpo
    assert "T0" not in corpo


def test_un_formato_sconosciuto_si_rifiuta(client_db):
    client, db = client_db
    sid, _ = _set_ricco(client, db)
    assert client.post(f"/api/sets/{sid}/export?format=inventato").status_code == 422


def test_i_formati_del_generato_non_cambiano(client_db):
    """La regressione da evitare: l'export dei set generati passa dallo stesso
    endpoint e non deve accorgersi di niente."""
    client, db = client_db
    from app.models import Setlist, SetlistTrack
    t = Track(source_type="spotify", title="G", artist="A", bpm=124.0,
              camelot_key="8A", duration_seconds=300, has_local_file=True,
              local_path="/lib/g.mp3")
    db.add(t)
    s = Setlist(name="Generato", kind="generated")
    db.add(s)
    db.flush()
    db.add(SetlistTrack(setlist_id=s.id, position=1, track_id=t.id))
    db.commit()
    for fmt in ("text", "csv", "markdown", "m3u8"):
        r = client.post(f"/api/sets/{s.id}/export?format={fmt}")
        assert r.status_code == 200, (fmt, r.text)
        assert "G" in r.text
    # I formati nuovi sono del banco: su un generato non hanno senso.
    assert client.post(f"/api/sets/{s.id}/export?format=prep").status_code == 422
```

- [ ] **Step 2: Esegui e verifica che falliscano**

Run: `cd backend && .venv/bin/python -m pytest tests/test_set_manual_export.py -q -p no:cacheprovider`
Expected: FAIL con 409 `set_not_manual` sui primi (l'endpoint oggi rifiuta i manual) e 422 sui formati nuovi.

- [ ] **Step 3: Implementa il renderer**

```python
# backend/app/services/manual_export.py
"""Export del set manuale (tappa 5).

Un solo renderer per formato, che l'anteprima e il download chiamano allo stesso
modo: l'anteprima e' la stessa risposta dell'endpoint, quindi «l'anteprima
coincide con cio' che esporto» e' vero per costruzione e non per disciplina.

Tutto legge il PERCORSO RISOLTO (`manual_set.resolved_path`): banco, riserva e
alternative non sono il set. Le due eccezioni sono dichiarate: la scheda di
preparazione mostra anche alternative e varchi, perche' servono in cabina, e
l'export "reserve" e' fatto apposta per la riserva.
"""

from __future__ import annotations

import csv
import io

from app.models import Setlist
from app.services.manual_pairs import bpm_of, pair_compat
from app.services.manual_set import (
    blocks_of, pair_note_map, path_rows, reserve_rows, resolved_path, set_duration,
)
from app.services.export_render import fmt_duration

MANUAL_FORMATS = ("text", "csv", "markdown", "m3u8", "prep", "reserve")

_IGNOTO = "—"


def _label(track) -> str:
    return f"{track.artist or '?'} - {track.title or '?'}"


def _render_text(setlist: Setlist, lang: str) -> str:
    righe = [f"# {setlist.name}", ""]
    for i, row in enumerate(resolved_path(setlist), start=1):
        t = row.track
        tempo = bpm_of(row)
        meta = f"[{tempo:.0f} BPM, {t.camelot_key or '?'}]" if tempo else f"[{t.camelot_key or '?'}]"
        righe.append(f"{i:2d}. {_label(t)} {meta}")
    return "\n".join(righe)


def _render_csv(setlist: Setlist, lang: str) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["position", "title", "artist", "bpm", "play_bpm", "key",
                "duration_seconds", "planned_seconds", "note", "local_path"])
    for i, row in enumerate(resolved_path(setlist), start=1):
        t = row.track
        w.writerow([i, t.title or "", t.artist or "", t.bpm or "", row.play_bpm or "",
                    t.camelot_key or "", t.duration_seconds or "", row.planned_seconds or "",
                    row.note or "", t.local_path or ""])
    return buf.getvalue()


def _render_markdown(setlist: Setlist, lang: str) -> str:
    md = [f"# {setlist.name}", "",
          "| # | Traccia | BPM | Key | Durata |", "|--:|---|--:|---|--:|"]
    for i, row in enumerate(resolved_path(setlist), start=1):
        t = row.track
        tempo = bpm_of(row)
        md.append(f"| {i} | {_label(t)} | {tempo:.0f} | {t.camelot_key or '?'} | "
                  f"{fmt_duration(row.planned_seconds or t.duration_seconds)} |"
                  if tempo else
                  f"| {i} | {_label(t)} | {_IGNOTO} | {t.camelot_key or '?'} | "
                  f"{fmt_duration(row.planned_seconds or t.duration_seconds)} |")
    return "\n".join(md)


def _render_m3u8(setlist: Setlist, lang: str) -> str:
    from app.services.exporters import render_m3u8

    righe = resolved_path(setlist)
    posseduti = [r.track for r in righe if r.track.local_path]
    return render_m3u8(posseduti, len(righe))


def _render_prep(setlist: Setlist, lang: str) -> str:
    """La scheda che il DJ si porta in cabina: sequenze, appunti, alternative,
    varchi e passaggi. Una traccia senza file resta e si dichiara — e' una
    decisione presa, e nasconderla sarebbe una bugia."""
    d = set_duration(setlist)
    md = [f"# {setlist.name}", ""]
    md.append(f"{len(resolved_path(setlist))} tracce · {fmt_duration(d.seconds)}"
              + (" (stima incompleta)" if d.incomplete else ""))
    md.append("")

    note_coppie = pair_note_map(setlist)
    precedente = None
    for block in blocks_of(setlist, "main"):
        md += [f"## {block.name or 'senza nome'}", ""]
        for row in sorted(block.rows, key=lambda r: r.position):
            if row.track is None:
                md.append("- **[varco]** " + (row.note or ""))
                precedente = None
                continue
            t = row.track
            tempo = bpm_of(row)
            pezzi = [f"{tempo:.0f} BPM" if tempo else _IGNOTO, t.camelot_key or _IGNOTO]
            if row.play_bpm:
                pezzi.append(f"la suono a {row.play_bpm:.0f}")
            if not t.has_local_file:
                pezzi.append("non disponibile")
            md.append(f"- **{_label(t)}** — {' · '.join(pezzi)}")
            if precedente is not None:
                c = pair_compat(precedente, row)
                passaggio = (f"{c.bpm_percent:+.1f} %" if c.bpm_percent is not None else _IGNOTO)
                appunto = note_coppie.get((precedente.track_id, row.track_id))
                md.append(f"  - passaggio: pitch {passaggio}"
                          + (f" — {appunto}" if appunto else ""))
            if row.note:
                md.append(f"  - appunto: {row.note}")
            for alt in sorted(row.alternatives, key=lambda a: a.position):
                md.append(f"  - alternativa: {_label(alt.track)}")
            precedente = row
        md.append("")

    banco = blocks_of(setlist, "bench")
    if banco:
        md += ["## Banco", ""]
        for block in banco:
            md.append(f"- **{block.name or 'senza nome'}**: "
                      + ", ".join(_label(r.track) for r in block.rows if r.track))
        md.append("")

    riserva = reserve_rows(setlist)
    if riserva:
        md += ["## Riserva", ""]
        md += [f"- {_label(r.track)}" for r in riserva if r.track]
    return "\n".join(md)


def _render_reserve(setlist: Setlist, lang: str) -> str:
    righe = [f"# {setlist.name} — riserva", ""]
    for row in reserve_rows(setlist):
        if row.track is None:
            continue
        t = row.track
        meta = f"[{t.bpm:.0f} BPM, {t.camelot_key or '?'}]" if t.bpm else f"[{t.camelot_key or '?'}]"
        righe.append(f"- {_label(t)} {meta}")
    return "\n".join(righe)


_RENDERERS = {
    "text": (_render_text, "text/plain"),
    "csv": (_render_csv, "text/csv"),
    "markdown": (_render_markdown, "text/markdown"),
    "m3u8": (_render_m3u8, "audio/x-mpegurl"),
    "prep": (_render_prep, "text/markdown"),
    "reserve": (_render_reserve, "text/markdown"),
}


def render_manual(setlist: Setlist, fmt: str, lang: str) -> tuple[str, str]:
    render, media = _RENDERERS[fmt]
    return render(setlist, lang), media
```

`fmt_duration` e `render_m3u8` stanno entrambi in `app.services.export_render` (è da lì che li importa `routers/sets.py`, riga 91): l'import locale dentro `_render_m3u8` serve solo a tenere il modulo leggero, si può anche portare in testa.

- [ ] **Step 4: Durata e durata pianificata nel documento**

Senza questo la pagina non può disegnare niente di ciò che il Task 1 ha calcolato.

In `backend/app/schemas.py`, `ManualRowOut` guadagna dopo `play_bpm`:

```python
    planned_seconds: int | None = None  # quanto la si tiene in questo set
```

e accanto a `ManualTransitionOut`:

```python
class SetDurationOut(BaseModel):
    """Durata del percorso risolto. `incomplete` non e' un dettaglio estetico:
    dice che il totale e' una somma parziale, e i due conteggi dicono perche'."""

    seconds: int = 0
    incomplete: bool = False
    unknown_rows: int = 0
    open_gaps: int = 0
```

con `ManualSetOut` che guadagna, dopo `total_file_seconds`:

```python
    duration: SetDurationOut = SetDurationOut()
```

In `backend/app/serializers.py`, importa `SetDurationOut` e `set_duration`, e passa:

```python
        planned_seconds=st.planned_seconds,   # dentro row_out
```

```python
        duration=SetDurationOut(**vars(set_duration(setlist))),
```

In coda a `backend/tests/test_set_manual_api.py`:

```python
def test_la_durata_esce_nel_documento(client_db):
    client, db = client_db
    _, t = _seed(db, n=2)   # due tracce da 300 secondi
    sid = client.post("/api/sets/manual", json={"name": "M"}).json()["id"]
    doc = client.post(f"/api/sets/{sid}/rows",
                      json={"expected_revision": 0, "track_ids": [x.id for x in t]}).json()
    assert doc["duration"]["seconds"] == 600
    assert doc["duration"]["incomplete"] is False

    riga = _rows(doc)[0]["id"]
    doc = client.patch(f"/api/sets/{sid}/rows/{riga}",
                       json={"expected_revision": 1, "planned_seconds": 120}).json()
    assert _rows(doc)[0]["planned_seconds"] == 120
    assert doc["duration"]["seconds"] == 420

    doc = client.post(f"/api/sets/{sid}/rows", json={
        "expected_revision": 2, "gap": True, "after_row_id": riga}).json()
    assert doc["duration"]["incomplete"] is True and doc["duration"]["open_gaps"] == 1
```

- [ ] **Step 5: L'endpoint**

In `backend/app/routers/sets.py`, l'export cambia solo in testa: il pattern del `format` accetta i due formati nuovi, e prima di `_require_generated` si dirotta il manuale.

```python
@router.post("/{setlist_id}/export", response_class=PlainTextResponse)
def export(
    setlist_id: int,
    format: str = Query(default="text", pattern="^(text|csv|markdown|m3u8|prep|reserve)$"),
    db: Session = Depends(get_db),
):
    """Export del set. I set generati usano i quattro formati storici; quelli
    preparati a mano leggono il PERCORSO RISOLTO e hanno in piu' la scheda di
    preparazione (`prep`) e l'elenco delle riserve (`reserve`)."""
    setlist = get_setlist(db, setlist_id)
    if setlist is None:
        raise api_error(404, "set_not_found", "Set not found")
    lang = get_language(db)
    if setlist.kind == "manual":
        contenuto, media = render_manual(setlist, format, lang)
        return PlainTextResponse(contenuto, media_type=media)
    if format in ("prep", "reserve"):
        raise api_error(422, "set_format_not_available",
                        "This format belongs to a hand-prepared set")
    _require_generated(setlist)
    ...  # il resto del corpo attuale, invariato
```

- [ ] **Step 6: Esegui e verifica**

Run: `cd backend && .venv/bin/python -m pytest tests/test_set_manual_export.py tests/test_effective_tags_read_paths.py -q -p no:cacheprovider` → verdi. Il secondo file è quello che esercita l'export CSV dei set **generati** (`test_export_csv_passa_il_genere_effettivo_a_classify_transition`): è la prova che il ramo generato non è cambiato.

Run: `cd backend && .venv/bin/python -m pytest tests -q -p no:cacheprovider` → verde.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/manual_export.py backend/app/routers/sets.py backend/app/schemas.py backend/app/serializers.py backend/tests/test_set_manual_export.py backend/tests/test_set_manual_api.py
git commit -m "feat(sets): export del set manuale, scheda di preparazione e riserve"
```

---

### Task 3: Il beam search impara a fermarsi a conteggio

**Files:**
- Modify: `backend/app/services/set_generator.py`
- Test: `backend/tests/test_two_phase_generator.py` (in coda — è l'unico file che esercita già `_beam_search_span`)

**Interfaces:**
- Produces: `_beam_search_span(..., max_count: int | None = None)` — quando è dato, lo span si ferma appena ha scelto `max_count` tracce, indipendentemente dai secondi.

**Perché un parametro e non una funzione nuova.** Il beam è lo stesso: stessi punteggi, stessa convergenza verso l'anchor, stessi vincoli per artista. Cambia solo quando si dichiara finito. Duplicarlo vorrebbe dire due motori da tenere allineati per sempre.

- [ ] **Step 1: Scrivi il test che fallisce**

In coda al file dei test del generatore:

```python
def test_lo_span_si_puo_fermare_a_conteggio(db):
    """«Riempi il varco» vuole N tracce, non N secondi: il criterio a conteggio
    affianca quello a secondi senza sostituirlo."""
    from app.services.set_generator import _beam_search_span
    from app.services.set_skeleton import strategy_profile
    from app.schemas import SetGenerationRequest

    tracce = []
    for i in range(10):
        t = Track(source_type="spotify", title=f"T{i}", artist=f"A{i}", bpm=124.0 + i,
                  camelot_key="8A", duration_seconds=300, has_local_file=True)
        db.add(t)
        tracce.append(t)
    db.commit()

    req = SetGenerationRequest(target_duration_minutes=60)
    fillers = _beam_search_span(
        tracce[0], tracce[1:], req, strategy_profile("smooth"),
        start_bpm=124.0, end_bpm=130.0, target_seconds=3600,
        elapsed_secs=300, fill_until_secs=3600, max_count=3)
    assert len(fillers) == 3
    # I secondi non c'entrano: con lo stesso span e nessun conteggio ne sceglie molte di piu'.
    senza = _beam_search_span(
        tracce[0], tracce[1:], req, strategy_profile("smooth"),
        start_bpm=124.0, end_bpm=130.0, target_seconds=3600,
        elapsed_secs=300, fill_until_secs=3600)
    assert len(senza) > 3
```

- [ ] **Step 2: Esegui e verifica che fallisca**

Run: `cd backend && .venv/bin/python -m pytest tests/test_two_phase_generator.py -q -p no:cacheprovider -k conteggio`
Expected: FAIL con `TypeError: unexpected keyword argument 'max_count'`.

- [ ] **Step 3: Implementa**

In `_beam_search_span`, aggiungi il parametro in fondo alla firma:

```python
    max_count: int | None = None,
```

documentalo nel docstring:

```
    max_count: se dato, lo span si chiude appena ha scelto quel numero di tracce,
    a prescindere dai secondi. Serve a "riempi il varco" (tappa 6), che ragiona
    in slot e non in durata; None lascia il comportamento a secondi di sempre.
```

e nella funzione interna `new_beam` la condizione di chiusura diventa:

```python
                "done": _span_finito(elapsed_secs, 0),
```

con, subito sopra `new_beam`:

```python
    def _span_finito(secs: int, quanti: int) -> bool:
        if max_count is not None:
            return quanti >= max_count
        return secs >= fill_until_secs
```

Ogni altro punto che oggi scrive `b["secs"] >= fill_until_secs` (o equivalente) per marcare `done` usa `_span_finito(b["secs"], len(b["chosen"]))`. **Leggi tutta la funzione prima di modificarla** e cambia tutte le occorrenze: lasciarne una sola col vecchio criterio produrrebbe uno span che si ferma quando capita.

- [ ] **Step 4: Esegui e verifica**

Run: `cd backend && .venv/bin/python -m pytest tests -q -p no:cacheprovider` → verde. Il generatore esistente non passa mai `max_count`, quindi il suo comportamento deve essere identico: se qualche test del generatore cambia risultato, hai toccato il ramo a secondi.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/set_generator.py backend/tests/test_two_phase_generator.py
git commit -m "feat(sets): il beam search sa fermarsi a conteggio, non solo a tempo"
```

---

### Task 4: «Riempi il varco»

**Files:**
- Create: `backend/app/services/manual_fill.py`
- Modify: `backend/app/services/manual_set.py`, `backend/app/schemas.py`, `backend/app/serializers.py`, `backend/app/routers/sets.py`
- Test: `backend/tests/test_set_manual_fill.py` (nuovo)

**Interfaces:**
- Consumes: Task 1 (`resolved_path`), Task 3 (`max_count`).
- Produces:

```python
# manual_fill.py
class FillError(ManualSetError): ...

def propose_fill(db, setlist, row_id: int, *, count: int) -> list[Track]
    """Le `count` tracce che il generatore propone per quel varco, in ordine.
    Opener = la traccia PRIMA del varco, `converge_to` = quella DOPO; se manca
    un lato, lo span parte o finisce libero. Pool: il materiale del set meno
    tutto cio' che e' gia' nel percorso. Nessuna AI: `mood_scores` resta None."""

# manual_set.py
def fill_gap(db, setlist_id, row_id, *, expected_revision, count: int) -> Setlist
    """Applica la proposta: il varco diventa la PRIMA riga proposta (tenendo id
    e appunto, come `choose_alternative`) e le altre entrano dopo di lui come
    righe normali. Una revisione sola: annullare rimette il varco aperto."""
```

**Le regole che il test impone.** La proposta non contiene tracce già nel percorso; non tocca la riserva né il banco; entra come righe normali (modificabili, spostabili, cancellabili); un varco senza vicini da nessuna parte è comunque riempibile; e l'intera operazione è **una** revisione, così un annulla riporta il varco esattamente com'era.

- [ ] **Step 1: Scrivi i test che falliscono**

`backend/tests/test_set_manual_fill.py`:

```python
"""«Riempi il varco» (prima meta' della tappa 6): il generatore come strumento."""
import pytest

from app.models import Playlist, Track
from app.repositories import add_track_to_playlist
from app.services.manual_set import (
    ManualSetError, create_manual_set, fill_gap, insert_rows, path_rows, resolved_path, undo,
)


def _libreria(db, n=10):
    pl = Playlist(platform="spotify", name="Deep")
    db.add(pl)
    db.flush()
    tracce = []
    for i in range(n):
        t = Track(source_type="spotify", title=f"T{i}", artist=f"A{i}", bpm=124.0 + i * 0.5,
                  camelot_key="8A", duration_seconds=300, has_local_file=True)
        db.add(t)
        db.flush()
        add_track_to_playlist(db, t, pl, added_by="test")
        tracce.append(t)
    db.commit()
    return pl, tracce


def _set_con_varco(db, pl, tracce):
    """Due tracce con un varco in mezzo."""
    s = create_manual_set(db, name="M", playlist_id=pl.id)
    s = insert_rows(db, s.id, expected_revision=0, track_ids=[tracce[0].id, tracce[1].id],
                    gap=False, after_row_id=None)
    prima = path_rows(s)[0]
    s = insert_rows(db, s.id, expected_revision=1, track_ids=[], gap=True, after_row_id=prima.id)
    return s


def test_riempire_un_varco_mette_il_numero_di_tracce_chiesto(db):
    pl, t = _libreria(db)
    s = _set_con_varco(db, pl, t)
    varco = path_rows(s)[1]
    assert varco.track_id is None

    s = fill_gap(db, s.id, varco.id, expected_revision=2, count=3)
    righe = path_rows(s)
    assert len(righe) == 5                       # 2 di prima + 3 proposte
    assert all(r.track_id is not None for r in righe)   # nessun varco rimasto
    # Il varco e' diventato la prima proposta, tenendo il suo id.
    assert righe[1].id == varco.id


def test_la_proposta_non_ripesca_cio_che_e_gia_nel_percorso(db):
    pl, t = _libreria(db)
    s = _set_con_varco(db, pl, t)
    gia_dentro = {r.track_id for r in resolved_path(s)}
    varco = path_rows(s)[1]

    s = fill_gap(db, s.id, varco.id, expected_revision=2, count=3)
    proposte = [r.track_id for r in path_rows(s)[1:4]]
    assert not (set(proposte) & gia_dentro)
    assert len(set(proposte)) == 3               # nemmeno doppioni fra loro


def test_riempire_e_una_sola_revisione_e_l_annulla_riapre_il_varco(db):
    pl, t = _libreria(db)
    s = _set_con_varco(db, pl, t)
    varco = path_rows(s)[1]

    s = fill_gap(db, s.id, varco.id, expected_revision=2, count=3)
    assert s.revision == 3                       # una sola, non tre

    s = undo(db, s.id, expected_revision=3)
    righe = path_rows(s)
    assert len(righe) == 3
    assert righe[1].id == varco.id and righe[1].track_id is None   # varco com'era


def test_un_varco_in_testa_si_riempie_lo_stesso(db):
    """Senza traccia prima, lo span parte libero: non e' un errore, e' un varco
    all'inizio del set."""
    pl, t = _libreria(db)
    s = create_manual_set(db, name="M", playlist_id=pl.id)
    s = insert_rows(db, s.id, expected_revision=0, track_ids=[t[0].id], gap=False,
                    after_row_id=None)
    s = insert_rows(db, s.id, expected_revision=1, track_ids=[], gap=True, after_row_id=None)
    # Il varco e' in coda: lo sposto in testa.
    from app.services.manual_set import move_row
    varco = path_rows(s)[1]
    s = move_row(db, s.id, varco.id, expected_revision=2, position=1)
    varco = path_rows(s)[0]

    s = fill_gap(db, s.id, varco.id, expected_revision=3, count=2)
    assert all(r.track_id is not None for r in path_rows(s))


def test_non_si_riempie_una_riga_che_non_e_un_varco(db):
    pl, t = _libreria(db)
    s = _set_con_varco(db, pl, t)
    riga = path_rows(s)[0]
    with pytest.raises(ManualSetError):
        fill_gap(db, s.id, riga.id, expected_revision=2, count=2)


def test_senza_materiale_il_varco_resta_aperto(db):
    """Meglio un rifiuto esplicito che un varco chiuso con niente dentro."""
    pl = Playlist(platform="spotify", name="Vuota")
    db.add(pl)
    db.flush()
    a = Track(source_type="spotify", title="A", bpm=124.0, camelot_key="8A",
              duration_seconds=300, has_local_file=True)
    db.add(a)
    db.flush()
    add_track_to_playlist(db, a, pl, added_by="test")
    db.commit()
    s = create_manual_set(db, name="M", playlist_id=pl.id)
    s = insert_rows(db, s.id, expected_revision=0, track_ids=[a.id], gap=False, after_row_id=None)
    s = insert_rows(db, s.id, expected_revision=1, track_ids=[], gap=True, after_row_id=None)
    varco = path_rows(s)[1]
    with pytest.raises(ManualSetError):
        fill_gap(db, s.id, varco.id, expected_revision=2, count=2)
    assert path_rows(s)[1].track_id is None      # ancora aperto


def test_riempire_non_chiama_nessuna_ai(db, monkeypatch):
    """Vincolo di progetto: il generatore-strumento e' deterministico. Se
    qualcuno agganciasse la curatela qui, questo test lo direbbe subito."""
    import app.services.ai_curation as curation
    chiamate = []
    for nome in dir(curation):
        attr = getattr(curation, nome)
        if callable(attr) and not nome.startswith("_"):
            monkeypatch.setattr(curation, nome,
                                lambda *a, _n=nome, **k: chiamate.append(_n))
    pl, t = _libreria(db)
    s = _set_con_varco(db, pl, t)
    varco = path_rows(s)[1]
    fill_gap(db, s.id, varco.id, expected_revision=2, count=2)
    assert chiamate == []
```

- [ ] **Step 2: Esegui e verifica che falliscano**

Run: `cd backend && .venv/bin/python -m pytest tests/test_set_manual_fill.py -q -p no:cacheprovider`
Expected: FAIL con `ImportError: cannot import name 'fill_gap'`.

- [ ] **Step 3: Il servizio di proposta**

```python
# backend/app/services/manual_fill.py
"""«Riempi il varco»: il generatore come strumento dentro un set preparato a mano.

Non e' un generatore nuovo — e' `_beam_search_span`, lo stesso del set builder,
con il criterio di stop a conteggio. Deterministico e senza AI: `mood_scores`
resta None, che e' l'unico gancio da cui la curatela potrebbe entrare.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import Setlist, SetlistTrack, Track
from app.schemas import SetGenerationRequest
from app.services.manual_material import material_for
from app.services.manual_set import ManualSetError, path_rows, resolved_path
from app.services.set_generator import _beam_search_span
from app.services.set_skeleton import strategy_profile


class FillError(ManualSetError):
    pass


def _vicini(setlist: Setlist, gap: SetlistTrack) -> tuple[SetlistTrack | None, SetlistTrack | None]:
    """Le righe con traccia che stanno subito prima e subito dopo il varco, nel
    percorso. Un varco in testa o in coda ne ha una sola, e va benissimo."""
    righe = path_rows(setlist)
    at = next(i for i, r in enumerate(righe) if r.id == gap.id)
    prima = next((r for r in reversed(righe[:at]) if r.track is not None), None)
    dopo = next((r for r in righe[at + 1:] if r.track is not None), None)
    return prima, dopo


def propose_fill(db: Session, setlist: Setlist, gap: SetlistTrack, *, count: int) -> list[Track]:
    # material_for ritorna tuple (track, in_set, from_playlist, in_reserve),
    # NON un oggetto con .items: quello e' il MaterialOut del serializer.
    materiale = material_for(db, setlist, q=None, owned=False, unused=False, reserved=False)
    gia_nel_percorso = {r.track_id for r in resolved_path(setlist)}
    pool = [track for track, *_ in materiale if track.id not in gia_nel_percorso]
    if not pool:
        raise FillError("No material left to fill this gap")

    prima, dopo = _vicini(setlist, gap)
    opener = prima.track if prima is not None else pool[0]
    if prima is None:
        pool = pool[1:]
        if not pool:
            raise FillError("No material left to fill this gap")

    start = (prima.play_bpm or prima.track.bpm) if prima is not None else (opener.bpm or 124.0)
    end = (dopo.play_bpm or dopo.track.bpm) if dopo is not None else start
    req = SetGenerationRequest(target_duration_minutes=60)
    fillers = _beam_search_span(
        opener, pool, req, strategy_profile("smooth"),
        start_bpm=start or 124.0, end_bpm=end or start or 124.0,
        target_seconds=3600, elapsed_secs=0, fill_until_secs=3600,
        converge_to=dopo.track if dopo is not None else None,
        mood_scores=None,           # nessuna AI: e' il gancio della curatela
        max_count=count,
    )
    proposte = [t for t, _ in fillers]
    if prima is None:
        proposte = [opener] + proposte
    if not proposte:
        raise FillError("The generator found nothing for this gap")
    return proposte[:count]
```

- [ ] **Step 4: L'applicazione**

In `backend/app/services/manual_set.py`, in fondo:

```python
def fill_gap(db: Session, setlist_id: int, row_id: int, *, expected_revision: int,
             count: int) -> Setlist:
    """Riempie un varco con le tracce proposte dal generatore. Il varco diventa
    la prima proposta — tenendo id e appunto, come `choose_alternative` — e le
    altre entrano dopo di lui. UNA revisione sola: annullare riapre il varco."""
    from app.services.manual_fill import propose_fill  # import qui: manual_fill importa questo modulo

    setlist = load_manual_set(db, setlist_id)
    _check_revision(setlist, expected_revision)
    gap = _row_of(setlist, row_id)
    if gap.slot_kind != "gap" or gap.track_id is not None:
        raise ManualSetError("That row is not an open gap")

    proposte = propose_fill(db, setlist, gap, count=count)

    # La prima prende il posto del varco: la relationship insieme alla chiave,
    # come in choose_alternative, o al flush vincerebbe quella caricata.
    gap.track_id = proposte[0].id
    gap.track = proposte[0]
    gap.slot_kind = "track"

    vicine = [r for r in path_rows(setlist) if r.block_id == gap.block_id]
    at = vicine.index(gap) + 1
    nuove: list[SetlistTrack] = []
    for track in proposte[1:]:
        riga = SetlistTrack(setlist_id=setlist.id, block_id=gap.block_id, position=0,
                            slot_kind="track", track_id=track.id)
        riga.track = track
        db.add(riga)
        setlist.tracks.append(riga)
        nuove.append(riga)
    vicine[at:at] = nuove
    _renumber(vicine)
    return _commit_bumped(db, setlist, "fill")
```

- [ ] **Step 5: API**

In `backend/app/schemas.py`:

```python
class FillGapRequest(BaseModel):
    expected_revision: int = Field(ge=0)
    count: int = Field(default=1, ge=1, le=10)
```

In `backend/app/routers/sets.py` (import di `FillGapRequest`, `fill_gap`, `FillError`), accanto agli altri endpoint del set manuale:

```python
@router.post("/{setlist_id}/rows/{row_id}/fill-gap", response_model=ManualSetOut)
def rows_fill_gap(setlist_id: int, row_id: int, req: FillGapRequest,
                  db: Session = Depends(get_db)):
    """Il generatore propone `count` tracce per quel varco e le inserisce come
    righe normali: si spostano, si cambiano, si cancellano, e un annulla riapre
    il varco. Deterministico, nessuna chiamata AI."""
    try:
        return manual_set_out(fill_gap(
            db, setlist_id, row_id, expected_revision=req.expected_revision,
            count=req.count), db)
    except ManualSetError as exc:
        raise _manual_error(exc) from exc
```

e in `_manual_error`, sopra il caso generico:

```python
    if isinstance(exc, FillError):
        return api_error(422, "set_fill_failed", f"Could not fill the gap: {exc}", reason=str(exc))
```

- [ ] **Step 6: Esegui, suite, commit**

Run: `cd backend && .venv/bin/python -m pytest tests -q -p no:cacheprovider` → verde.

Poi dimostra che il test anti-AI morde: in `propose_fill`, aggiungi una chiamata a una funzione qualunque di `ai_curation` e verifica che `test_riempire_non_chiama_nessuna_ai` fallisca. Toglila.

```bash
git add backend/app/services/manual_fill.py backend/app/services/manual_set.py backend/app/schemas.py backend/app/routers/sets.py backend/tests/test_set_manual_fill.py
git commit -m "feat(sets): «riempi il varco», il generatore come strumento del set manuale"
```

---

### Task 5: Frontend — durata, export, riempimento

**Files:**
- Modify: `frontend/lib/api/types.ts`, `frontend/lib/api/manual-sets.ts`, `frontend/lib/i18n/{en,it}.ts`
- Create: `frontend/components/set-builder/export-menu.tsx`, `frontend/components/set-builder/fill-gap-panel.tsx`
- Modify: `frontend/components/set-builder/{path-panel,detail-panel}.tsx`, `frontend/app/sets/manual/page.tsx`
- Test: `frontend/tests/set-builder-duration-export.test.tsx`, `frontend/tests/set-builder-fill.test.tsx` (nuovi)

**Interfaces:**

```ts
// ManualRow guadagna: planned_seconds: number | null
// ManualSet guadagna: duration: { seconds: number; incomplete: boolean; unknown_rows: number; open_gaps: number }
exportManualSet(id, format: "text" | "csv" | "markdown" | "m3u8" | "prep" | "reserve"): Promise<string>
fillGap(id, rowId, body: { expected_revision: number; count: number }): Promise<ManualSet>
patchRow(id, rowId, body: { expected_revision: number; note?: string | null; play_bpm?: number | null; planned_seconds?: number | null })
```

Comportamento della pagina:
- In testa, accanto al conteggio, la durata: `2 h 14 · 18 tracce`, e quando `incomplete` è vero la dicitura «stima incompleta» con il perché (`n` tracce senza durata, `n` varchi aperti). Non un'icona muta: il DJ deve sapere *cosa* manca.
- Nel dettaglio, sotto «La suono a», il campo «Quanto la tengo» (`planned_seconds`, in secondi), salvato al blur come gli altri e con lo stesso confronto sul valore invariato.
- Un menù «Esporta» con i sei formati: al clic mostra l'**anteprima** — cioè la risposta dell'endpoint — con un pulsante per scaricarla. Nessun secondo renderer lato client.
- Sulla riga di un varco, un comando «Riempi» con un selettore del numero (1–10); la risposta rimpiazza lo stato come ogni altra mutazione. L'errore `set_fill_failed` si mostra nel banner esistente.

- [ ] **Step 1: Testi**

Chiavi nuove sotto `sets.manual` in `en.ts` poi `it.ts`: `durationLabel`, `durationIncomplete`, `durationIncompleteWhy(rows, gaps)`, `plannedSecondsLabel`, `plannedSecondsHint`, `exportButton`, `exportPreviewTitle`, `exportDownloadButton`, `exportFormatText`, `exportFormatCsv`, `exportFormatMarkdown`, `exportFormatM3u8`, `exportFormatPrep`, `exportFormatReserve`, `fillGapTitle`, `fillGapCountLabel`, `fillGapButton`. In `errors`: `set_fill_failed`, `set_format_not_available`.

Traduzioni italiane: «Durata», «stima incompleta», `(righe, varchi) => [righe && \`${righe} senza durata\`, varchi && \`${varchi} varchi aperti\`].filter(Boolean).join(" · ")`, «Quanto la tengo», «Vuoto = la durata del file.», «Esporta», «Anteprima», «Scarica», «Testo», «CSV», «Markdown», «M3U8 (Rekordbox)», «Scheda di preparazione», «Riserve», «Riempi il varco», «Quante tracce», «Riempi».

- [ ] **Step 2: Tipi e client** — come da blocco Interfaces sopra, sullo stesso stile dei metodi esistenti in `manual-sets.ts`. `exportManualSet` riusa la forma di `exportSet` in `lib/api/sets.ts` (una `fetch` che legge il testo, non `apiPost`).

- [ ] **Step 3: Scrivi i test**

`frontend/tests/set-builder-duration-export.test.tsx`, sulla falsariga di `set-builder-pairs.test.tsx` (stessi mock, stesso `mount()` dentro `PlayerProvider`; il fixture ha `duration` e due righe). Casi:

1. la durata compare in testa, formattata;
2. con `incomplete: true`, `unknown_rows: 1`, `open_gaps: 2`, compare «stima incompleta» **e** il dettaglio del perché (il test asserisce su entrambi i numeri: una dicitura senza il motivo non basta);
3. «Quanto la tengo» chiama `patchRow` con `{expected_revision, planned_seconds: 120}` **e senza le altre proprietà**;
4. il menù export chiama `exportManualSet(7, "prep")` e mostra nell'anteprima esattamente il testo tornato dal mock — nessuna rielaborazione;
5. un valore invariato al blur non chiama niente.

`frontend/tests/set-builder-fill.test.tsx`. Casi:

1. sulla riga di un varco compare «Riempi il varco», sulle altre no;
2. il clic chiama `fillGap(7, <id del varco>, {expected_revision, count})` col numero scelto;
3. un `set_fill_failed` mostra il messaggio e **non** lascia la pagina in uno stato a metà (il varco è ancora lì).

- [ ] **Step 4: Componenti e pagina** — `export-menu.tsx` (`data-testid="export-menu"`, l'anteprima in un `Modal` come la conferma di eliminazione), `fill-gap-panel.tsx` (`data-testid="fill-gap"`, montato dalla riga varco del percorso), il campo nel dettaglio, la durata in testa alla pagina.

- [ ] **Step 5: Verifica**

Run: `cd frontend && npm run test:unit -- tests/set-builder-duration-export.test.tsx tests/set-builder-fill.test.tsx`, poi `npx tsc --noEmit && npm run lint && npm run test:unit && npm run build`.
Attenzione: i fixture dei test già esistenti (`set-builder-workbench`, `-alternatives`, `-blocks`, `-pairs`) vanno aggiornati con `duration` e `planned_seconds`, altrimenti la pagina non si disegna e i loro test cadono **solo nella suite intera**, non da soli — è già successo nelle tappe 2, 3 e 4.

- [ ] **Step 6: Commit**

```bash
git add frontend/lib frontend/components/set-builder frontend/app/sets/manual/page.tsx frontend/tests
git commit -m "feat(frontend): durata, export e riempimento del varco nel set manuale"
```

---

### Task 6: Documentazione e verifica integrata

**Files:**
- Modify: `docs/API.md`, `docs/ARCHITECTURE.md`, `PROGRESS.md`, `docs/ROADMAP.md`, `frontend/e2e/set-builder.spec.ts`

- [ ] **Step 1: Documentazione**

`docs/API.md`: l'export non è più riservato ai generati — i due formati nuovi, cosa contengono e la regola che l'anteprima è la stessa risposta; `planned_seconds` nella PATCH parziale; `duration` in `ManualSetOut` con il significato di `incomplete`; `POST .../rows/{row_id}/fill-gap` con `count` e i codici `set_fill_failed`, `set_format_not_available`; e la definizione di **percorso risolto**, che da qui in poi è il termine che l'API usa.

`docs/ARCHITECTURE.md`: un paragrafo sul percorso risolto come proiezione unica di export/durata/compatibilità e sul perché resta separato da `path_rows`; uno su `manual_export.py` (un renderer per formato, l'anteprima che è la risposta stessa); uno su `manual_fill.py` — stesso beam del generatore, stop a conteggio, `mood_scores` sempre `None`, proposte che entrano come righe normali in una revisione sola.

`PROGRESS.md`: voce datata con cosa esiste e cosa no (resta solo la demolizione del vecchio generatore).

`docs/ROADMAP.md`: la voce 3 passa a «tappe 1-5 shipped, più il generatore-strumento»; resta aperta la sola rimozione del vecchio form e della curatela AI, con la nota che è stata separata apposta.

Vale la regola del progetto: ogni parentesi e ogni rimando va verificato per conto proprio.

- [ ] **Step 2: E2E**

Estendi `frontend/e2e/set-builder.spec.ts` con un quarto test: crea un set da una playlist di sei tracce, mettine due nel percorso con un varco in mezzo, riempi il varco con due tracce e verifica che il percorso ne abbia quattro e nessun varco; annulla e verifica che il varco sia tornato; apri l'export «scheda di preparazione» e verifica che l'anteprima contenga il nome della sequenza e una delle tracce.

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
git commit -m "docs(sets): durata, export e riempimento del varco"
```
