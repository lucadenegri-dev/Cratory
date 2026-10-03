# Ascolto a due deck nel banco — piano di implementazione

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dal banco manuale, su un passaggio fra due righe, aprire due deck con waveform, griglia dei battiti calcolata da Essentia, pitch con master tempo, sync di tempo e fase, volume, taglio bassi e memory cue salvate per traccia.

**Architecture:** Il backend aggiunge tre colonne di griglia su `Track` (scritte solo dal job di analisi), due tabelle (`track_waveforms`, `track_cues`) e un router `deck.py` con quattro gruppi di endpoint. Il frontend aggiunge un motore Web Audio imperativo (`lib/deck/engine.ts`), la matematica pura della griglia (`lib/deck/grid.ts`) e un dock fisso in basso (`components/deck/*`) montato dalla pagina del banco; wavesurfer.js disegna la waveform sull'`<audio>` di ogni deck con i picchi precalcolati dal backend.

**Tech Stack:** FastAPI + SQLAlchemy + Pydantic, numpy e ffmpeg (già presenti), Essentia (già presente), Next.js 16 + React 19, wavesurfer.js 8 (BSD-3), vitest + Testing Library, Playwright.

**Spec:** `docs/superpowers/specs/2026-10-03-two-deck-audition-design.md`

## Global Constraints

- Nessun codice dei deck scrive `Track.bpm`, `Track.camelot_key`, `bpm_source` o `key_source` (regola 2 di CLAUDE.md): un grep di `bpm_source`/`key_source` nei file nuovi deve dare zero.
- La griglia viene SOLO da Essentia (`RhythmExtractor2013`); il nodo `TEMPO` dell'XML Rekordbox resta ignorato.
- Picchi: cento al secondo, un byte ciascuno (0–255), dal PCM mono 22050 Hz s16le dell'intera traccia; invalidati quando `audio_hash` cambia.
- Cue: massimo dieci per traccia (`TrackCue.MAX_PER_TRACK = 10`), nome al massimo sessanta caratteri, posizione ≥ 0 e ≤ durata + 1 s quando la durata è nota.
- Pitch: corsa ±8 % di default, ±16 % selezionabile; il rate è sempre bloccato nella corsa scelta. Master tempo = `preservesPitch`, acceso di default.
- Taglio bassi: passa-alto Biquad a 10 Hz spento, 300 Hz acceso, Q 0,7. Volume: `GainNode` per deck più gain master.
- Zoom condiviso fra i due deck: livelli 20, 40, 80, 160 px/s, default 80.
- Un solo `AudioContext`: quello di `lib/audio-analyser.ts`.
- I deck non registrano comandi Media Session; nessuna scorciatoia da tastiera; niente loop, EQ, cuffia, crossfader.
- Testi utente in ENTRAMBI i dizionari (`lib/i18n/en.ts` è la fonte dei tipi, `it.ts` lo rispecchia).
- Next.js 16: leggere `frontend/CLAUDE.md` e `node_modules/next/dist/docs/` prima di toccare pagine o routing.
- Messaggi di commit nello stile del repo (`feat(deck): …`, `test(deck): …`, `docs(…): …`, in italiano), SENZA trailer `Co-Authored-By`.
- Comandi di test: backend `cd backend && .venv/bin/python -m pytest tests/<file> -v`; frontend `cd frontend && npx vitest run tests/<file>`; e2e `cd frontend && npm run test:e2e -- e2e/deck.spec.ts`.

## Review Focus

1. **PCM a lunghezza dispari** (ffmpeg interrotto a metà campione): `np.frombuffer` con `<i2` solleva su un numero dispari di byte. Atteso: l'ultimo byte orfano si scarta e i picchi si calcolano lo stesso. Test in Task 5.
2. **Stessa traccia su entrambi i deck** (una traccia che compare due volte nel percorso): le cue sono per traccia, quindi aggiungerne una sul deck A deve comparire anche sul deck B. Test in Task 13.
3. **Seek negativo dopo l'allineamento di fase** (deck fermo a 0 e spostamento negativo): `currentTime` non può andare sotto zero. Atteso: bloccato a 0. Test in Task 10.
4. **Cambio di corsa da ±16 a ±8 con rate 1,12**: il rate deve rientrare a 1,08, non restare fuori corsa. Test in Task 13.
5. **Waveform con zero picchi** (file vuoto o decodifica che restituisce zero byte): wavesurfer con `peaks: [[]]` e `duration: 0` non deve montare. Atteso: trattata come assente, il deck mostra "waveform non disponibile: decodifica fallita". Test in Task 13.

---

## Struttura dei file

**Backend (`backend/app/`)**

| File | Responsabilità |
|---|---|
| `services/beatgrid.py` (nuovo) | `fit(ticks) -> Grid`, `GridError`, `clear(track)`: la griglia a tempo costante, pura |
| `services/waveform.py` (nuovo) | `peaks_from_pcm`, `is_fresh`, `ensure_waveform`: i picchi |
| `services/deck_cues.py` (nuovo) | `list_cues`, `add_cue`, `update_cue`, errori di limite e bordi |
| `routers/deck.py` (nuovo) | `GET /deck`, `POST /deck/prepare`, `POST/PATCH/DELETE /cues` |
| `models.py` | colonne `grid_*` su `Track`; `TrackWaveform`, `TrackCue` |
| `schemas.py` | `DeckOut`, `DeckPrepareOut`, `CueIn`, `CueUpdateIn`, `CueOut` e i sotto-modelli |
| `integrations/essentia_engine.py`, `integrations/essentia_worker.py` | `AnalysisResult.ticks` |
| `integrations/local_files.py` | `ffmpeg_path()`, `decode_pcm_full(path)` |
| `services/audio_analysis_job.py` | scrive la griglia a ogni traccia analizzata |
| `services/library_index.py`, `services/acquisition.py` | azzerano la griglia quando il file cambia o sparisce |
| `repositories.py` | `merge_tracks` sposta le cue e scarta la waveform; `detach_track_dependencies` cancella cue e waveform |
| `main.py` | registra il router |

**Frontend (`frontend/`)**

| File | Responsabilità |
|---|---|
| `lib/api/types.ts`, `lib/api/deck.ts` (nuovo), `lib/api.ts` | tipi e chiamate del deck, `decodePeaks` |
| `lib/deck/grid.ts` (nuovo) | matematica pura: battiti, fase, rate di sync, allineamento, disaccordo di ottava |
| `lib/deck/engine.ts` (nuovo) | `DeckEngine`: grafo Web Audio, rate, master tempo, volume, taglio bassi |
| `lib/audio-analyser.ts` | espone `getAudioContext()` |
| `components/deck/cue-strip.tsx` (nuovo) | chip delle cue, rinomina, elimina, "metti cue", "al battito" |
| `components/deck/deck-waveform.tsx` (nuovo) | wavesurfer + Minimap + Regions + canvas dei battiti |
| `components/deck/deck.tsx` (nuovo) | un deck: blocco a sinistra e colonna waveform |
| `components/deck/deck-dock.tsx` (nuovo) | telaio fisso, stato dei due deck, polling, sync, fase, "nascondi" |
| `components/set-builder/transition-panel.tsx`, `detail-panel.tsx`, `app/sets/manual/page.tsx` | pulsante "Prova il passaggio", stato del dock, convivenza col player docked |
| `lib/i18n/en.ts`, `lib/i18n/it.ts` | blocco `deck` |
| `e2e/deck.spec.ts` (nuovo) | percorso completo contro il backend vero |

---

### Task 1: `beatgrid.fit` — la griglia a tempo costante

**Files:**
- Create: `backend/app/services/beatgrid.py`
- Test: `backend/tests/test_beatgrid.py`

**Interfaces:**
- Produces: `fit(ticks: list[float]) -> Grid` con `Grid(first_beat: float, bpm: float)`; `GridError(code)` con `code` in `{"too_few_beats", "uncertain"}`; `clear(track) -> None` che azzera `grid_first_beat`, `grid_bpm`, `grid_error`.

- [ ] **Step 1: Scrivi i test che falliscono**

```python
# backend/tests/test_beatgrid.py
"""Griglia a tempo costante dai battiti di Essentia (services/beatgrid, puro)."""
import random

import pytest

from app.services.beatgrid import GridError, clear, fit

P128 = 60 / 128


def _regular(n=200, bpm=128.0, first=0.37):
    p = 60 / bpm
    return [first + i * p for i in range(n)]


def test_battiti_regolari_danno_esattamente_bpm_e_primo_battito():
    g = fit(_regular())
    assert abs(g.bpm - 128.0) < 1e-6
    assert abs(g.first_beat - 0.37) < 1e-6
    # Ne' la meta' ne' il doppio: la griglia e' quella misurata, senza piegature.
    assert not (abs(g.bpm - 64.0) < 1.0 or abs(g.bpm - 256.0) < 1.0)


def test_jitter_di_dieci_ms_resta_entro_le_tolleranze():
    rnd = random.Random(7)
    ticks = [t + rnd.uniform(-0.010, 0.010) for t in _regular()]
    g = fit(ticks)
    assert abs(g.bpm - 128.0) < 0.1
    assert abs(g.first_beat - 0.37) < 0.005


def test_battiti_saltati_e_raddoppiati_non_spostano_la_griglia():
    ticks = _regular()
    for i in (40, 90, 150):
        ticks[i] = None  # tre battiti saltati dal tracker
    ticks = [t for t in ticks if t is not None]
    ticks += [0.37 + 20.5 * P128, 0.37 + 60.5 * P128]  # due raddoppiati, a meta' battito
    g = fit(ticks)
    assert abs(g.bpm - 128.0) < 1e-6
    assert abs(g.first_beat - 0.37) < 1e-6


def test_primo_battito_riportato_dentro_il_periodo():
    # Battiti che partono al secondo 3,0: il primo battito della griglia e' il
    # primo DAL FILE, cioe' 3,0 modulo periodo (3.0 - 6*0.46875 = 0.1875).
    g = fit(_regular(first=3.0))
    assert abs(g.first_beat - 0.1875) < 1e-6
    assert 0 <= g.first_beat < P128


def test_meno_di_sedici_battiti():
    with pytest.raises(GridError) as e:
        fit(_regular(n=15))
    assert e.value.code == "too_few_beats"


def test_battiti_casuali_danno_incerta():
    rnd = random.Random(3)
    ticks = sorted(rnd.uniform(0, 100) for _ in range(200))
    with pytest.raises(GridError) as e:
        fit(ticks)
    assert e.value.code == "uncertain"


def test_tempo_che_deriva_oltre_il_due_per_cento_e_incerto():
    # Intervalli alternati 0,45 / 0,49 s: mediana ~0,47, scarto mediano ~0,02 s
    # = 4 % del periodo, oltre la soglia.
    ticks, t = [], 0.0
    for i in range(100):
        ticks.append(t)
        t += 0.45 if i % 2 else 0.49
    with pytest.raises(GridError) as e:
        fit(ticks)
    assert e.value.code == "uncertain"


def test_clear_azzera_le_tre_colonne():
    class T:
        grid_first_beat = 1.0
        grid_bpm = 128.0
        grid_error = "x"
    t = T()
    clear(t)
    assert t.grid_first_beat is None and t.grid_bpm is None and t.grid_error is None
```

- [ ] **Step 2: Esegui i test, devono fallire**

Run: `cd backend && .venv/bin/python -m pytest tests/test_beatgrid.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'app.services.beatgrid'`

- [ ] **Step 3: Scrivi il modulo**

```python
# backend/app/services/beatgrid.py
"""Griglia dei battiti a tempo costante dai battiti di Essentia (spec 2026-10-03).

Modulo puro: niente DB, niente Essentia. `fit` riceve gli istanti dei battiti
in secondi e restituisce due numeri, primo battito e BPM. Serve solo ai deck
del banco: non tocca mai `Track.bpm` ne' la sua provenienza (regola 2 di
CLAUDE.md), esattamente come `energy` e' un derivato e non una fonte."""

from __future__ import annotations

import statistics
from dataclasses import dataclass

MIN_BEATS = 16
# Scarto, in battiti, oltre il quale un intervallo non vale un numero intero di
# battiti (battito saltato o raddoppiato dal tracker): il battito si scarta.
INTERVAL_TOLERANCE = 0.20
# Deviazione mediana assoluta degli intervalli singoli, in frazione del
# periodo, oltre la quale il tempo non e' costante abbastanza per una griglia.
MAX_SPREAD = 0.02


@dataclass(frozen=True)
class Grid:
    first_beat: float  # secondi dall'inizio del file, in [0, periodo)
    bpm: float


class GridError(ValueError):
    """`code` finisce in `Track.grid_error`: too_few_beats | uncertain."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def fit(ticks: list[float]) -> Grid:
    ts = sorted(float(t) for t in ticks)
    if len(ts) < MIN_BEATS:
        raise GridError("too_few_beats")
    intervals = [b - a for a, b in zip(ts, ts[1:])]
    rough = statistics.median(intervals)
    if rough <= 0:
        raise GridError("uncertain")
    # Indici interi di battito ricostruiti un salto alla volta rispetto al
    # periodo grezzo: un battito saltato vale m=2, uno raddoppiato (rapporto
    # ~0,5) si scarta e il successivo si misura dall'ultimo tenuto. Cosi' non
    # c'e' deriva: ogni rapporto copre pochi periodi, mai l'intera traccia.
    kept: list[tuple[int, float]] = [(0, ts[0])]
    k_last, t_last = 0, ts[0]
    for t in ts[1:]:
        ratio = (t - t_last) / rough
        m = round(ratio)
        if m >= 1 and abs(ratio - m) <= INTERVAL_TOLERANCE:
            k_last += m
            t_last = t
            kept.append((k_last, t))
    if len(kept) < MIN_BEATS:
        raise GridError("uncertain")
    singoli = [b - a for (ka, a), (kb, b) in zip(kept, kept[1:]) if kb - ka == 1]
    if len(singoli) < MIN_BEATS - 1:
        raise GridError("uncertain")
    mad = statistics.median(abs(d - rough) for d in singoli)
    if mad > MAX_SPREAD * rough:
        raise GridError("uncertain")
    # Minimi quadrati di t su k: pendenza = periodo, intercetta = ancora.
    n = len(kept)
    mk = sum(k for k, _ in kept) / n
    mt = sum(t for _, t in kept) / n
    sxx = sum((k - mk) ** 2 for k, _ in kept)
    sxy = sum((k - mk) * (t - mt) for k, t in kept)
    period = sxy / sxx
    anchor = mt - period * mk
    first_beat = anchor - (anchor // period) * period  # riportata in [0, periodo)
    return Grid(first_beat=round(first_beat, 4), bpm=round(60.0 / period, 3))


def clear(track) -> None:
    """Azzera le tre colonne della griglia: il file e' cambiato o sparito."""
    track.grid_first_beat = None
    track.grid_bpm = None
    track.grid_error = None
```

- [ ] **Step 4: Esegui i test, devono passare**

Run: `cd backend && .venv/bin/python -m pytest tests/test_beatgrid.py -v`
Expected: 8 passed

- [ ] **Step 5: Prova ogni asserzione rompendo il codice** (regola del repo: niente test verdi per il motivo sbagliato). Cambia `INTERVAL_TOLERANCE` a `0.6`: il test dei raddoppiati deve fallire. Cambia `MAX_SPREAD` a `0.5`: il test della deriva deve fallire. Ripristina.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/beatgrid.py backend/tests/test_beatgrid.py
git commit -m "feat(deck): griglia dei battiti a tempo costante (beatgrid.fit)"
```

---

### Task 2: i battiti escono da Essentia

**Files:**
- Modify: `backend/app/integrations/essentia_engine.py` (dataclass `AnalysisResult`, `analyze`, `analyze_subprocess`)
- Modify: `backend/app/integrations/essentia_worker.py:24-27`
- Test: `backend/tests/test_essentia_engine.py`

**Interfaces:**
- Produces: `AnalysisResult.ticks: list[float]` (secondi, arrotondati a 4 decimali, lista vuota se assenti); il JSON del worker guadagna la chiave `"ticks"`.

- [ ] **Step 1: Aggiungi i test in coda a `tests/test_essentia_engine.py`**

```python
import json
import statistics


def test_analyze_subprocess_legge_i_battiti(monkeypatch):
    class P:
        returncode = 0
        stderr = ""
        stdout = 'rumore di Essentia\n{"bpm": 128.0, "camelot": "8A", "ticks": [0.5, 0.9688]}\n'
    monkeypatch.setattr(eng.subprocess, "run", lambda *a, **k: P())
    res = eng.analyze_subprocess("/x.mp3")
    assert res.bpm == 128.0 and res.ticks == [0.5, 0.9688]


def test_analyze_subprocess_senza_battiti_lista_vuota(monkeypatch):
    """Un worker vecchio (senza `ticks`) non deve rompere il job."""
    class P:
        returncode = 0
        stderr = ""
        stdout = '{"bpm": 128.0, "camelot": "8A"}'
    monkeypatch.setattr(eng.subprocess, "run", lambda *a, **k: P())
    assert eng.analyze_subprocess("/x.mp3").ticks == []


def test_worker_stampa_i_battiti(monkeypatch, capsys):
    from app.integrations import essentia_worker as w
    monkeypatch.setattr(w, "analyze",
                        lambda p: eng.AnalysisResult(bpm=120.0, camelot="1A", ticks=[0.1, 0.6]))
    assert w.main(["w", "/x.wav"]) == 0
    assert json.loads(capsys.readouterr().out) == {"bpm": 120.0, "camelot": "1A", "ticks": [0.1, 0.6]}


@pytest.mark.skipif(not eng.is_available(), reason="Essentia non installata")
def test_analyze_click_track_restituisce_i_battiti(tmp_path):
    p = tmp_path / "click120.wav"
    _click_track_wav(p, bpm=120.0)
    res = eng.analyze(str(p))
    assert len(res.ticks) >= 30
    diffs = [b - a for a, b in zip(res.ticks, res.ticks[1:])]
    assert abs(statistics.median(diffs) - 0.5) < 0.05
```

- [ ] **Step 2: Esegui, devono fallire**

Run: `cd backend && .venv/bin/python -m pytest tests/test_essentia_engine.py -v -k "battiti"`
Expected: FAIL (`AttributeError: 'AnalysisResult' object has no attribute 'ticks'` / `TypeError: unexpected keyword 'ticks'`)

- [ ] **Step 3: Modifica il motore**

In `essentia_engine.py`:

```python
from dataclasses import dataclass, field


@dataclass
class AnalysisResult:
    bpm: float | None
    camelot: str | None
    # Istanti dei battiti in secondi (RhythmExtractor2013): alimentano la
    # griglia dei deck (services/beatgrid). Vuota se il worker non li ha dati.
    ticks: list[float] = field(default_factory=list)
```

In `analyze`, sostituisci le due righe del BPM:

```python
    bpm_raw, ticks, _confidence, _estimates, _intervals = es.RhythmExtractor2013(
        method="multifeature")(audio)
    bpm = round(float(bpm_raw), 2) if float(bpm_raw) > 0 else None
    key, scale, _strength = es.KeyExtractor(profileType="edma")(audio)
    return AnalysisResult(bpm=bpm, camelot=_key_to_camelot(key, scale),
                          ticks=[round(float(t), 4) for t in ticks])
```

In `analyze_subprocess`, l'ultima riga:

```python
    return AnalysisResult(bpm=data["bpm"], camelot=data["camelot"],
                          ticks=[float(t) for t in (data.get("ticks") or [])])
```

In `essentia_worker.py`, nel `main`:

```python
    res = analyze(argv[1])  # propaga su file illeggibile -> rc != 0
    json.dump({"bpm": res.bpm, "camelot": res.camelot, "ticks": res.ticks}, sys.stdout)
```

e aggiorna il docstring del modulo: `JSON {"bpm": float|null, "camelot": str|null, "ticks": [float, ...]}`.

- [ ] **Step 4: Esegui tutto il file, deve passare**

Run: `cd backend && .venv/bin/python -m pytest tests/test_essentia_engine.py -v`
Expected: tutti passed (i due col motore vero girano perche' Essentia e' installata nel venv)

- [ ] **Step 5: Commit**

```bash
git add backend/app/integrations/essentia_engine.py backend/app/integrations/essentia_worker.py backend/tests/test_essentia_engine.py
git commit -m "feat(deck): il worker Essentia restituisce anche i battiti"
```

---

### Task 3: colonne della griglia su `Track`, scritte dal job di analisi

**Files:**
- Modify: `backend/app/models.py` (classe `Track`, dopo `analysis_dismissed_of_camelot`)
- Modify: `backend/app/services/audio_analysis_job.py`
- Test: `backend/tests/test_audio_analysis_job.py`

**Interfaces:**
- Produces: `Track.grid_first_beat: float | None`, `Track.grid_bpm: float | None`, `Track.grid_error: str | None`. Il job scrive queste tre colonne a ogni traccia analizzata, qualunque sia l'esito di apply.
- Consumes: `beatgrid.fit`, `beatgrid.GridError`, `AnalysisResult.ticks`.

- [ ] **Step 1: Aggiorna la fixture e aggiungi i test in `tests/test_audio_analysis_job.py`**

Nella fixture `sync_job`, sostituisci la riga del motore finto:

```python
    monkeypatch.setattr(aj.essentia_engine, "analyze_subprocess",
                        lambda path: AnalysisResult(bpm=128.0, camelot="8A",
                                                    ticks=[0.37 + i * 60 / 128 for i in range(64)]))
```

In coda al file:

```python
def test_griglia_scritta_anche_quando_l_analisi_non_si_applica(sync_job):
    aj, S = sync_job
    _seed(S)
    aj.start_job(scope="all")
    with S() as s:
        piena = s.get(Track, 2)
        assert piena.bpm == 130.0 and piena.bpm_source == "rekordbox"  # canonico intatto
        assert piena.grid_bpm == 128.0
        assert abs(piena.grid_first_beat - 0.37) < 1e-6
        assert piena.grid_error is None


def test_griglia_rifiutata_scrive_grid_error_e_azzera_la_vecchia(sync_job, monkeypatch):
    from app.integrations.essentia_engine import AnalysisResult
    aj, S = sync_job
    _seed(S)
    with S() as s:
        t = s.get(Track, 1)
        t.grid_first_beat, t.grid_bpm = 0.5, 120.0  # griglia precedente
        s.commit()
    monkeypatch.setattr(aj.essentia_engine, "analyze_subprocess",
                        lambda path: AnalysisResult(bpm=128.0, camelot="8A", ticks=[0.1, 0.2]))
    aj.start_job(scope="all")
    with S() as s:
        t = s.get(Track, 1)
        assert t.grid_error == "too_few_beats"
        assert t.grid_bpm is None and t.grid_first_beat is None
        assert t.analysis_error is None and t.analysis_bpm == 128.0  # l'analisi e' riuscita


def test_analisi_fallita_non_tocca_la_griglia(sync_job, monkeypatch):
    aj, S = sync_job
    _seed(S)
    with S() as s:
        t = s.get(Track, 1)
        t.grid_first_beat, t.grid_bpm = 0.5, 120.0
        s.commit()

    def _boom(path):
        raise RuntimeError("file corrotto")
    monkeypatch.setattr(aj.essentia_engine, "analyze_subprocess", _boom)
    aj.start_job(scope="all")
    with S() as s:
        t = s.get(Track, 1)
        assert t.analysis_error == "analysis_decode_failed"
        assert t.grid_bpm == 120.0  # un decode fallito non dice nulla di nuovo
```

- [ ] **Step 2: Esegui, devono fallire**

Run: `cd backend && .venv/bin/python -m pytest tests/test_audio_analysis_job.py -v`
Expected: i tre nuovi FAIL (`grid_bpm` inesistente); i vecchi passano.

- [ ] **Step 3: Colonne sul modello**

In `models.py`, classe `Track`, dopo `analysis_dismissed_of_camelot`:

```python
    # Griglia dei battiti dei deck (spec 2026-10-03): derivato Essentia a tempo
    # costante, primo battito + BPM della griglia. La scrive SOLO il job di
    # analisi; la azzerano l'indicizzazione e il collegamento di un file quando
    # l'audio cambia o sparisce (services/beatgrid.clear). Non tocca mai
    # bpm/camelot_key ne' le loro provenienze (regola 2).
    grid_first_beat: Mapped[float | None] = mapped_column(Float)
    grid_bpm: Mapped[float | None] = mapped_column(Float)
    grid_error: Mapped[str | None] = mapped_column(String)  # too_few_beats | uncertain
```

`ensure_schema` le aggiunge da sola (`_migrate_add_model_columns` deriva le ADD COLUMN dal modello): nessuna migrazione a mano.

- [ ] **Step 4: Il job scrive la griglia**

In `audio_analysis_job.py`:

```python
from app.services import beatgrid
```

e una funzione modulo:

```python
def _write_grid(track: Track, ticks: list[float]) -> None:
    """Griglia dei deck da ogni analisi riuscita, a prescindere da apply/dismiss:
    e' un derivato per i deck, non una proposta sui canonici."""
    try:
        g = beatgrid.fit(ticks)
    except beatgrid.GridError as exc:
        beatgrid.clear(track)
        track.grid_error = exc.code
        return
    track.grid_first_beat, track.grid_bpm, track.grid_error = g.first_beat, g.bpm, None
```

Nel ciclo di `_run_job`, dopo `t.analysis_error = None`:

```python
                _write_grid(t, res.ticks)
```

Aggiorna il docstring del modulo: «Scrive SOLO analysis_* + analyzed_at/analysis_error e le colonne grid_* (griglia dei deck)».

- [ ] **Step 5: Esegui, devono passare**

Run: `cd backend && .venv/bin/python -m pytest tests/test_audio_analysis_job.py tests/test_analysis_router.py -v`
Expected: tutti passed

- [ ] **Step 6: Commit**

```bash
git add backend/app/models.py backend/app/services/audio_analysis_job.py backend/tests/test_audio_analysis_job.py
git commit -m "feat(deck): il job di analisi scrive la griglia dei battiti su Track"
```

---

### Task 4: la griglia si azzera quando il file cambia o sparisce

**Files:**
- Modify: `backend/app/services/library_index.py` (`_own`, `_discard`, ramo `lost` di `riconcilia_possessi`)
- Modify: `backend/app/services/acquisition.py` (`attach_local_file`)
- Test: `backend/tests/test_library_index.py`, `backend/tests/test_acquisition.py`

**Interfaces:**
- Consumes: `beatgrid.clear(track)`.
- Produces: nessuna interfaccia nuova. Punti di scrittura delle colonne `grid_*` dopo questo task: il job (Task 3), `_own`, `_discard`, il ramo `lost`, `attach_local_file`, più `merge_tracks` (Task 6, che scarta la traccia assorbita). Nessun altro.

- [ ] **Step 1: Test in coda a `tests/test_acquisition.py`**

```python
def test_attach_azzera_la_griglia(db, monkeypatch):
    from app.models import Track
    from app.services import acquisition
    monkeypatch.setattr(acquisition, "audio_hash", lambda p: "HNEW")
    t = Track(source_type="spotify", title="T", artist="A",
              grid_first_beat=0.5, grid_bpm=128.0, grid_error=None)
    db.add(t); db.commit()
    out = acquisition.attach_local_file(db, t, path="/x/y.mp3", fmt="mp3", bitrate=320)
    assert out.grid_first_beat is None and out.grid_bpm is None and out.grid_error is None
```

- [ ] **Step 2: Test in coda a `tests/test_library_index.py`**

```python
def test_riaggancio_azzera_la_griglia_del_vecchio_file(db, fake_audio, collega_da_disco):
    """Stesso hash, file ricomparso: la griglia era di un file che non c'e' piu'
    (o e' lo stesso, ma si ricalcola a costo zero alla prossima richiesta)."""
    from app.models import Track

    make, root = fake_audio
    lead = Track(source_type="spotify", title="Song", artist="A", audio_hash="HX",
                 has_local_file=False, grid_first_beat=0.5, grid_bpm=128.0)
    db.add(lead); db.commit()

    make("song.mp3", digest="HX", artist="A", title="Song")
    collega_da_disco(root)

    db.refresh(lead)
    assert lead.has_local_file is True
    assert lead.grid_bpm is None and lead.grid_first_beat is None


def test_riconciliazione_sgancia_e_azzera_la_griglia(db, fake_audio, collega_da_disco, tmp_path):
    from app.models import Playlist, Track
    from app.repositories import add_track_to_playlist

    make, root = fake_audio
    pl = Playlist(platform="spotify", name="P"); db.add(pl)
    sparito = Track(source_type="spotify", title="Gone", artist="A",
                    has_local_file=True, local_path=str(tmp_path / "non-esiste.mp3"),
                    local_format="mp3", audio_hash="HGONE",
                    grid_first_beat=0.5, grid_bpm=128.0, grid_error=None)
    db.add(sparito); db.flush()
    add_track_to_playlist(db, sparito, pl); db.commit()

    make("resta.mp3", digest="HSTAY", artist="B", title="Stay")
    collega_da_disco(root)

    db.refresh(sparito)
    assert sparito.has_local_file is False
    assert sparito.grid_bpm is None and sparito.grid_first_beat is None
```

- [ ] **Step 3: Esegui, devono fallire**

Run: `cd backend && .venv/bin/python -m pytest tests/test_acquisition.py tests/test_library_index.py -v -k griglia`
Expected: 3 FAIL (la griglia resta valorizzata)

- [ ] **Step 4: Azzera nei quattro punti**

`library_index.py`: aggiungi `from app.services import beatgrid` agli import. In `_own`, subito dopo `track.audio_hash = digest`:

```python
    beatgrid.clear(track)  # file nuovo o cambiato: la griglia era di un altro audio
```

In `_discard`, dopo `track.audio_hash = digest`:

```python
    beatgrid.clear(track)
```

Nel ramo `lost` di `riconcilia_possessi`, dopo `track.primary_file_id = None`:

```python
            beatgrid.clear(track)  # senza file non c'e' griglia da conservare
```

`acquisition.py`: aggiungi `from app.services import beatgrid`; in `attach_local_file`, dopo `track.local_bitrate = bitrate`:

```python
    beatgrid.clear(track)  # il file e' nuovo per questa traccia
```

- [ ] **Step 5: Esegui le due suite intere, devono passare**

Run: `cd backend && .venv/bin/python -m pytest tests/test_acquisition.py tests/test_library_index.py tests/test_library_index_incremental.py tests/test_library_index_robustness.py -v`
Expected: tutti passed

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/library_index.py backend/app/services/acquisition.py backend/tests/test_acquisition.py backend/tests/test_library_index.py
git commit -m "feat(deck): la griglia si azzera quando il file locale cambia o sparisce"
```

---

### Task 5: tabelle `track_waveforms` e `track_cues`, decodifica intera e picchi

**Files:**
- Modify: `backend/app/models.py` (import `LargeBinary`; due classi in coda, dopo `SetlistSource`)
- Modify: `backend/app/repositories.py` (`detach_track_dependencies`)
- Modify: `backend/app/integrations/local_files.py` (`ffmpeg_path`, `decode_pcm_full`)
- Create: `backend/app/services/waveform.py`
- Test: `backend/tests/test_waveform.py`

**Interfaces:**
- Produces: `TrackWaveform(track_id PK FK, samples_per_second, duration_seconds, audio_hash, peaks: bytes, created_at)`; `TrackCue(id, track_id FK index, position_seconds, name, created_at)` con `TrackCue.MAX_PER_TRACK = 10`; `local_files.ffmpeg_path() -> str | None`; `local_files.decode_pcm_full(path) -> bytes`; `waveform.peaks_from_pcm(pcm) -> tuple[bytes, float]`; `waveform.is_fresh(wf, track) -> bool`; `waveform.ensure_waveform(db, track) -> TrackWaveform` (solleva `LocalFilesError`, non committa); `waveform.PEAKS_PER_SECOND = 100`.

- [ ] **Step 1: Test**

```python
# backend/tests/test_waveform.py
"""Picchi della waveform dei deck: finestre, quantizzazione, riga per traccia."""
import numpy as np
import pytest

from app.integrations.local_files import LocalFilesError
from app.models import Track, TrackWaveform
from app.services import waveform


def _pcm(*blocks):
    return np.concatenate(blocks).astype("<i2").tobytes()


def test_picchi_finestre_mute_e_piene():
    # 1 s di silenzio, 1 s a piena scala, 0,5 s di silenzio a 22050 Hz.
    peaks, duration = waveform.peaks_from_pcm(
        _pcm(np.zeros(22050), np.full(22050, 32767), np.zeros(11025)))
    assert duration == 2.5
    assert len(peaks) == 250
    assert set(peaks[:100]) == {0}
    assert set(peaks[100:200]) == {255}
    assert set(peaks[200:]) == {0}


def test_picco_negativo_conta_in_valore_assoluto_e_l_ultima_finestra_e_parziale():
    peaks, _ = waveform.peaks_from_pcm(_pcm(np.full(221, -16384)))
    # 221 campioni: finestra 0 = [0, 220), finestra 1 = [220, 221).
    assert len(peaks) == 2
    assert peaks[0] == 128 and peaks[1] == 128  # round(16384/32767*255)


def test_pcm_vuoto_e_pcm_a_byte_dispari():
    assert waveform.peaks_from_pcm(b"") == (b"", 0.0)
    # Review Focus 1: ffmpeg interrotto a meta' campione: il byte orfano si scarta.
    peaks, duration = waveform.peaks_from_pcm(_pcm(np.full(220, 32767)) + b"\x01")
    assert len(peaks) == 1 and peaks[0] == 255 and duration == 220 / 22050


def test_ensure_waveform_calcola_riusa_e_ricalcola_se_stantia(db, monkeypatch):
    calls: list[str] = []

    def fake_decode(path):
        calls.append(str(path))
        return _pcm(np.zeros(22050))
    monkeypatch.setattr(waveform.local_files, "decode_pcm_full", fake_decode)
    t = Track(source_type="spotify", has_local_file=True, local_path="/x/a.mp3", audio_hash="H1")
    db.add(t); db.commit()

    wf = waveform.ensure_waveform(db, t); db.commit()
    assert wf.audio_hash == "H1" and wf.samples_per_second == 100
    assert len(wf.peaks) == 100 and wf.duration_seconds == 1.0
    assert waveform.is_fresh(db.get(TrackWaveform, t.id), t) is True

    waveform.ensure_waveform(db, t)
    assert calls == ["/x/a.mp3"]  # la seconda volta non decodifica

    t.audio_hash = "H2"; db.commit()
    assert waveform.is_fresh(db.get(TrackWaveform, t.id), t) is False
    wf2 = waveform.ensure_waveform(db, t); db.commit()
    assert len(calls) == 2 and wf2.audio_hash == "H2"
    assert db.query(TrackWaveform).count() == 1  # una riga per traccia, aggiornata


def test_ensure_waveform_propaga_l_errore_di_decodifica_senza_salvare(db, monkeypatch):
    def boom(path):
        raise LocalFilesError("ffmpeg non ha potuto decodificare")
    monkeypatch.setattr(waveform.local_files, "decode_pcm_full", boom)
    t = Track(source_type="spotify", has_local_file=True, local_path="/x/a.mp3", audio_hash="H1")
    db.add(t); db.commit()
    with pytest.raises(LocalFilesError):
        waveform.ensure_waveform(db, t)
    assert db.get(TrackWaveform, t.id) is None


def test_cancellare_la_traccia_porta_via_waveform_e_cue(db):
    from app.models import TrackCue
    from app.repositories import detach_track_dependencies
    t = Track(source_type="spotify", title="T"); db.add(t); db.commit()
    db.add(TrackWaveform(track_id=t.id, samples_per_second=100, duration_seconds=1.0,
                         audio_hash="H", peaks=b"\x00" * 100))
    db.add(TrackCue(track_id=t.id, position_seconds=1.0, name=None)); db.commit()
    detach_track_dependencies(db, [t.id])
    db.delete(t); db.commit()
    assert db.query(TrackWaveform).count() == 0 and db.query(TrackCue).count() == 0
```

- [ ] **Step 2: Esegui, devono fallire**

Run: `cd backend && .venv/bin/python -m pytest tests/test_waveform.py -v`
Expected: FAIL (`ImportError: cannot import name 'TrackWaveform'`)

- [ ] **Step 3: Modelli**

In `models.py`, aggiungi `LargeBinary` all'import da `sqlalchemy`, e in coda al file:

```python
class TrackWaveform(Base):
    """Picchi della waveform per i deck del banco (spec 2026-10-03): una riga
    per traccia, cento picchi al secondo a un byte. `audio_hash` e' quello del
    file al momento del calcolo: diverso da `Track.audio_hash` = stantia, e
    `services/waveform.ensure_waveform` la ricalcola."""

    __tablename__ = "track_waveforms"

    track_id: Mapped[int] = mapped_column(ForeignKey("tracks.id"), primary_key=True)
    samples_per_second: Mapped[int] = mapped_column(Integer)
    duration_seconds: Mapped[float] = mapped_column(Float)
    audio_hash: Mapped[str | None] = mapped_column(String)
    peaks: Mapped[bytes] = mapped_column(LargeBinary)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class TrackCue(Base):
    """Memory cue dei deck: per TRACCIA (come in Rekordbox), non per set.
    Create solo dal deck, mai importate ne' esportate (per ora). Il limite
    e' quello delle memory cue Rekordbox, cosi' un export futuro non taglia."""

    __tablename__ = "track_cues"

    MAX_PER_TRACK = 10

    id: Mapped[int] = mapped_column(primary_key=True)
    track_id: Mapped[int] = mapped_column(ForeignKey("tracks.id"), index=True)
    position_seconds: Mapped[float] = mapped_column(Float)
    name: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
```

Nessun `ON DELETE CASCADE`: il repo tiene i figli di `tracks` in un posto solo, `detach_track_dependencies`. In `repositories.py` aggiungi `TrackCue, TrackWaveform` all'import da `app.models` e, in `detach_track_dependencies`, prima del blocco su `AudioFile`:

```python
    # Dati dei deck (spec 2026-10-03): waveform e cue muoiono con la traccia.
    db.execute(delete(TrackCue).where(TrackCue.track_id.in_(ids)),
               execution_options={"synchronize_session": False})
    db.execute(delete(TrackWaveform).where(TrackWaveform.track_id.in_(ids)),
               execution_options={"synchronize_session": False})
```

Aggiorna il docstring della funzione («la prossima tabella che punta a `tracks` va aggiunta in un posto solo» resta vero: e' qui).

- [ ] **Step 4: Decodifica intera in `local_files.py`**

Dopo `decode_pcm_bytes`:

```python
def ffmpeg_path() -> str | None:
    """ffmpeg risolto dal seam unico (`system_probe.resolve_binary`), o None."""
    return system_probe.resolve_binary("ffmpeg")


def decode_pcm_full(path: str | Path) -> bytes:
    """PCM mono 22050 Hz s16le dell'INTERA traccia, via ffmpeg: alimenta i picchi
    della waveform dei deck (services/waveform). Sei minuti = ~16 MB in memoria,
    una volta per traccia. Stesso seam di `decode_pcm_bytes`."""
    ffmpeg = ffmpeg_path()
    if ffmpeg is None:
        raise LocalFilesError("ffmpeg non trovato: necessario per la waveform dei deck.")
    cmd = [ffmpeg, "-v", "error", "-i", str(path), "-ac", "1", "-ar", "22050", "-f", "s16le", "-"]
    try:
        proc = subprocess.run(cmd, capture_output=True, check=True)
    except FileNotFoundError as exc:
        raise LocalFilesError("ffmpeg non trovato: necessario per la waveform dei deck.") from exc
    except subprocess.CalledProcessError as exc:
        raise LocalFilesError(f"ffmpeg non ha potuto decodificare {path}") from exc
    return proc.stdout
```

- [ ] **Step 5: Il servizio dei picchi**

```python
# backend/app/services/waveform.py
"""Picchi della waveform per i deck del banco (spec 2026-10-03).

`peaks_from_pcm` e' puro; `ensure_waveform` legge/scrive la riga `TrackWaveform`
senza committare. Cento picchi al secondo, un byte ciascuno: ~36 KB per sei
minuti, abbastanza fini per lo zoom a 160 px/s."""

from __future__ import annotations

import numpy as np
from sqlalchemy.orm import Session

from app.integrations import local_files
from app.models import Track, TrackWaveform

SAMPLE_RATE = 22050
PEAKS_PER_SECOND = 100


def peaks_from_pcm(pcm: bytes, *, sample_rate: int = SAMPLE_RATE,
                   per_second: int = PEAKS_PER_SECOND) -> tuple[bytes, float]:
    """(picchi uint8, durata in secondi). La finestra i copre i campioni da
    floor(i*sr/ps) a floor((i+1)*sr/ps); il picco e' il massimo del valore
    assoluto, quantizzato a round(max/32767*255). Un byte dispari in coda
    (ffmpeg interrotto a meta' campione) si scarta."""
    usable = len(pcm) - (len(pcm) % 2)
    samples = np.frombuffer(pcm[:usable], dtype="<i2")
    n = int(samples.size)
    count = (n * per_second + sample_rate - 1) // sample_rate if n else 0
    out = np.zeros(count, dtype=np.uint8)
    if n:
        absval = np.abs(samples.astype(np.int32))
        for i in range(count):
            lo = (i * sample_rate) // per_second
            hi = min(((i + 1) * sample_rate) // per_second, n)
            if hi > lo:
                out[i] = round(int(absval[lo:hi].max()) / 32767 * 255)
    return out.tobytes(), n / sample_rate


def is_fresh(wf: TrackWaveform | None, track: Track) -> bool:
    """La riga vale per il file attuale: stesso audio_hash (None == None compreso)."""
    return wf is not None and wf.audio_hash == track.audio_hash


def ensure_waveform(db: Session, track: Track) -> TrackWaveform:
    """La riga della waveform, calcolata se manca o e' stantia. Solleva
    `LocalFilesError` (ffmpeg assente o decodifica fallita) senza scrivere
    nulla. Non committa: lo fa il chiamante."""
    wf = db.get(TrackWaveform, track.id)
    if is_fresh(wf, track):
        return wf
    pcm = local_files.decode_pcm_full(track.local_path)
    peaks, duration = peaks_from_pcm(pcm)
    if wf is None:
        wf = TrackWaveform(track_id=track.id)
        db.add(wf)
    wf.samples_per_second = PEAKS_PER_SECOND
    wf.duration_seconds = duration
    wf.audio_hash = track.audio_hash
    wf.peaks = peaks
    db.flush()
    return wf
```

- [ ] **Step 6: Esegui, devono passare**

Run: `cd backend && .venv/bin/python -m pytest tests/test_waveform.py tests/test_track_merge.py tests/test_library_index.py -v`
Expected: tutti passed

- [ ] **Step 7: Commit**

```bash
git add backend/app/models.py backend/app/repositories.py backend/app/integrations/local_files.py backend/app/services/waveform.py backend/tests/test_waveform.py
git commit -m "feat(deck): tabelle waveform e cue, decodifica intera e picchi"
```

---

### Task 6: regole delle cue e fusione dei duplicati

**Files:**
- Create: `backend/app/services/deck_cues.py`
- Modify: `backend/app/repositories.py` (`merge_tracks`)
- Test: `backend/tests/test_deck_cues.py`, `backend/tests/test_track_merge.py`

**Interfaces:**
- Produces: `deck_cues.list_cues(db, track_id) -> list[TrackCue]` ordinate per posizione; `deck_cues.add_cue(db, track, *, position_seconds, name=None) -> TrackCue`; `deck_cues.update_cue(db, track, cue, fields: dict) -> TrackCue` dove `fields` contiene solo le chiavi da cambiare (`position_seconds`, `name`); `CueLimitError`, `CueOutOfRange`. Nessuna fa commit.
- Consumes: `TrackCue`, `TrackWaveform`.

- [ ] **Step 1: Test delle regole**

```python
# backend/tests/test_deck_cues.py
"""Memory cue dei deck: limite di dieci, bordi, nome, ordine."""
import pytest

from app.models import Track, TrackCue
from app.services.deck_cues import CueLimitError, CueOutOfRange, add_cue, list_cues, update_cue


def _track(db, duration=200):
    t = Track(source_type="spotify", title="T", has_local_file=True, local_path="/x.mp3",
              duration_seconds=duration)
    db.add(t); db.commit()
    return t


def test_undicesima_rifiutata_e_ordine_per_posizione(db):
    t = _track(db)
    for i in range(10):
        add_cue(db, t, position_seconds=100 - i * 5, name=f"c{i}")
    db.commit()
    with pytest.raises(CueLimitError):
        add_cue(db, t, position_seconds=1.0)
    posizioni = [c.position_seconds for c in list_cues(db, t.id)]
    assert posizioni == sorted(posizioni) and len(posizioni) == 10


def test_bordi_con_durata_nota(db):
    t = _track(db, duration=200)
    add_cue(db, t, position_seconds=200.9)  # un secondo di tolleranza: la durata e' intera
    with pytest.raises(CueOutOfRange):
        add_cue(db, t, position_seconds=201.5)
    with pytest.raises(CueOutOfRange):
        add_cue(db, t, position_seconds=-0.1)


def test_senza_durata_vale_solo_il_bordo_inferiore(db):
    t = _track(db, duration=None)
    assert add_cue(db, t, position_seconds=5000.0).position_seconds == 5000.0


def test_nome_ripulito_e_patch_parziale(db):
    t = _track(db)
    c = add_cue(db, t, position_seconds=10.0, name="  intro ")
    assert c.name == "intro"
    update_cue(db, t, c, {"name": None})
    assert c.name is None and c.position_seconds == 10.0
    update_cue(db, t, c, {"position_seconds": 12.5})
    assert c.position_seconds == 12.5
    with pytest.raises(CueOutOfRange):
        update_cue(db, t, c, {"position_seconds": None})
    assert db.query(TrackCue).count() == 1
```

- [ ] **Step 2: Test della fusione, in coda a `tests/test_track_merge.py`**

```python
def test_merge_sposta_le_cue_entro_dieci_e_scarta_la_waveform(db):
    from app.models import TrackCue, TrackWaveform
    keep = Track(source_type="spotify", title="K", artist="X")
    drop = Track(source_type="local_files", title="D", artist="X")
    db.add_all([keep, drop]); db.flush()
    for i in range(9):
        db.add(TrackCue(track_id=keep.id, position_seconds=float(i), name=None))
    for pos in (30.0, 10.0, 20.0):
        db.add(TrackCue(track_id=drop.id, position_seconds=pos, name=f"d{pos}"))
    db.add(TrackWaveform(track_id=drop.id, samples_per_second=100, duration_seconds=1.0,
                         audio_hash="H", peaks=b"\x00" * 100))
    db.commit()

    merge_tracks(db, keep, drop); db.commit()

    mie = db.scalars(select(TrackCue).where(TrackCue.track_id == keep.id)
                     .order_by(TrackCue.position_seconds)).all()
    assert len(mie) == 10
    assert [c.name for c in mie if c.name] == ["d10.0"]  # la prima per posizione; le altre due scartate
    assert db.query(TrackCue).count() == 10
    assert db.query(TrackWaveform).count() == 0
    assert db.get(Track, drop.id) is None
```

- [ ] **Step 3: Esegui, devono fallire**

Run: `cd backend && .venv/bin/python -m pytest tests/test_deck_cues.py tests/test_track_merge.py -v`
Expected: FAIL (`ModuleNotFoundError: app.services.deck_cues`; la fusione va in IntegrityError o lascia le cue su `drop`)

- [ ] **Step 4: Il servizio**

```python
# backend/app/services/deck_cues.py
"""Memory cue dei deck (spec 2026-10-03): regole di scrittura. Nessun commit."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Track, TrackCue


class CueLimitError(Exception):
    """Oltre TrackCue.MAX_PER_TRACK."""


class CueOutOfRange(Exception):
    """Posizione nulla, negativa o oltre la durata + 1 s (la durata e' intera)."""


def list_cues(db: Session, track_id: int) -> list[TrackCue]:
    return list(db.scalars(
        select(TrackCue).where(TrackCue.track_id == track_id)
        .order_by(TrackCue.position_seconds, TrackCue.id)))


def _check_position(track: Track, position: float | None) -> float:
    if position is None or position < 0:
        raise CueOutOfRange(position)
    if track.duration_seconds is not None and position > track.duration_seconds + 1:
        raise CueOutOfRange(position)
    return float(position)


def _clean_name(name: str | None) -> str | None:
    return (name or "").strip() or None


def add_cue(db: Session, track: Track, *, position_seconds: float, name: str | None = None) -> TrackCue:
    position = _check_position(track, position_seconds)
    if len(list_cues(db, track.id)) >= TrackCue.MAX_PER_TRACK:
        raise CueLimitError()
    cue = TrackCue(track_id=track.id, position_seconds=position, name=_clean_name(name))
    db.add(cue)
    db.flush()
    return cue


def update_cue(db: Session, track: Track, cue: TrackCue, fields: dict) -> TrackCue:
    """`fields` porta solo le chiavi da cambiare: `name` a None azzera il nome."""
    if "position_seconds" in fields:
        cue.position_seconds = _check_position(track, fields["position_seconds"])
    if "name" in fields:
        cue.name = _clean_name(fields["name"])
    db.flush()
    return cue
```

- [ ] **Step 5: La fusione**

In `repositories.py`, una funzione modulo prima di `merge_tracks`:

```python
def _merge_deck_data(db: Session, keep: Track, drop: Track) -> None:
    """Dati dei deck (spec 2026-10-03): la waveform di drop si scarta (si
    ricalcola), le cue si spostano su keep finche' c'e' posto, in ordine di
    posizione; le eccedenti cadono."""
    db.execute(delete(TrackWaveform).where(TrackWaveform.track_id == drop.id),
               execution_options={"synchronize_session": False})
    occupate = db.scalar(select(func.count()).select_from(TrackCue)
                         .where(TrackCue.track_id == keep.id)) or 0
    spazio = TrackCue.MAX_PER_TRACK - occupate
    da_spostare = db.scalars(select(TrackCue).where(TrackCue.track_id == drop.id)
                             .order_by(TrackCue.position_seconds, TrackCue.id)).all()
    for i, cue in enumerate(da_spostare):
        if i < spazio:
            cue.track_id = keep.id
        else:
            db.delete(cue)
```

e in `merge_tracks`, subito prima di `db.flush()  # applica gli spostamenti prima di cancellare drop`:

```python
    _merge_deck_data(db, keep, drop)
```

Il docstring di `merge_tracks` guadagna «sposta le cue dei deck e scarta la waveform di drop». Lo strumento `tools/merge_duplicate_tracks.fondi` delega gia' a `merge_tracks`: niente da toccare li'.

- [ ] **Step 6: Esegui, devono passare**

Run: `cd backend && .venv/bin/python -m pytest tests/test_deck_cues.py tests/test_track_merge.py tests/test_merge_duplicate_tracks.py -v`
Expected: tutti passed

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/deck_cues.py backend/app/repositories.py backend/tests/test_deck_cues.py backend/tests/test_track_merge.py
git commit -m "feat(deck): regole delle cue e fusione dei duplicati"
```

---

### Task 7: router `deck.py`

**Files:**
- Modify: `backend/app/schemas.py` (in coda)
- Create: `backend/app/routers/deck.py`
- Modify: `backend/app/main.py` (import e `include_router`)
- Test: `backend/tests/test_deck_router.py`

**Interfaces:**
- Produces: `GET /api/tracks/{id}/deck -> DeckOut`; `POST /api/tracks/{id}/deck/prepare -> DeckPrepareOut` (200 | 202 | 409 `analysis_busy` | 503 `ffmpeg_unavailable` | 500 `waveform_failed`); `POST /api/tracks/{id}/cues -> 201 CueOut` (409 `cue_limit`, 422 `cue_out_of_range`); `PATCH /api/tracks/{id}/cues/{cue_id} -> CueOut`; `DELETE … -> 204`; 404 `track_not_found` / `track_no_local_file` / `cue_not_found`.
- Consumes: `waveform.ensure_waveform`, `waveform.is_fresh`, `deck_cues.*`, `audio_analysis_job.is_running/start_job`, `essentia_engine.is_available`, `local_files.ffmpeg_path`.

- [ ] **Step 1: Test**

```python
# backend/tests/test_deck_router.py
"""Router /api/tracks/{id}/deck, /deck/prepare e /cues (spec 2026-10-03)."""
import base64

import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.integrations.local_files import LocalFilesError
from app.main import app
from app.models import Track, TrackWaveform
from app.routers import deck as deck_router
from app.services import waveform as waveform_service


@pytest.fixture()
def client(monkeypatch):
    e = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(e)
    S = sessionmaker(bind=e, expire_on_commit=False)

    def _get_db():
        db = S()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _get_db
    # Ambiente "tutto presente" di default: ogni test spegne cio' che vuole.
    monkeypatch.setattr(deck_router, "ffmpeg_path", lambda: "/usr/bin/ffmpeg")
    monkeypatch.setattr(waveform_service.local_files, "decode_pcm_full",
                        lambda path: np.zeros(22050, dtype="<i2").tobytes())
    monkeypatch.setattr(deck_router.essentia_engine, "is_available", lambda: True)
    monkeypatch.setattr(deck_router.audio_analysis_job, "is_running", lambda: False)
    started: list[dict] = []
    monkeypatch.setattr(deck_router.audio_analysis_job, "start_job",
                        lambda scope="missing", track_ids=None: started.append({"track_ids": track_ids}))
    yield TestClient(app), S, started
    app.dependency_overrides.clear()


def _seed(S):
    with S() as s:
        s.add(Track(id=1, source_type="spotify", has_local_file=True, local_path="/x/a.mp3",
                    audio_hash="H1", artist="A", title="T", bpm=126.0, camelot_key="8A",
                    duration_seconds=300))
        s.add(Track(id=2, source_type="spotify", has_local_file=False, title="Lead"))
        s.commit()


def test_deck_404_senza_file_e_su_id_ignoto(client):
    c, S, _ = client
    _seed(S)
    assert c.get("/api/tracks/2/deck").json()["detail"]["code"] == "track_no_local_file"
    assert c.get("/api/tracks/99/deck").status_code == 404


def test_deck_fresca_tutto_null(client):
    c, S, _ = client
    _seed(S)
    body = c.get("/api/tracks/1/deck").json()
    assert body["track"] == {"id": 1, "title": "T", "artist": "A", "bpm": 126.0, "camelot_key": "8A",
                             "duration_seconds": 300, "album_art_url": None, "has_local_file": True}
    assert body["grid"] is None and body["grid_error"] is None
    assert body["waveform"] is None and body["cues"] == []


def test_prepare_calcola_i_picchi_e_accoda_la_griglia(client):
    c, S, started = client
    _seed(S)
    r = c.post("/api/tracks/1/deck/prepare")
    assert r.status_code == 202 and r.json() == {"waveform": "ready", "grid": "queued", "reason": None}
    assert started == [{"track_ids": [1]}]
    body = c.get("/api/tracks/1/deck").json()
    wf = body["waveform"]
    assert wf["samples_per_second"] == 100 and wf["duration_seconds"] == 1.0
    assert len(base64.b64decode(wf["peaks"])) == 100


def test_prepare_con_griglia_gia_pronta(client):
    c, S, started = client
    _seed(S)
    with S() as s:
        t = s.get(Track, 1); t.grid_first_beat, t.grid_bpm = 0.37, 128.0; s.commit()
    r = c.post("/api/tracks/1/deck/prepare")
    assert r.status_code == 200 and r.json()["grid"] == "ready" and started == []
    assert c.get("/api/tracks/1/deck").json()["grid"] == {"first_beat": 0.37, "bpm": 128.0}


def test_prepare_con_griglia_rifiutata_non_riaccoda(client):
    c, S, started = client
    _seed(S)
    with S() as s:
        s.get(Track, 1).grid_error = "uncertain"; s.commit()
    r = c.post("/api/tracks/1/deck/prepare")
    assert r.status_code == 200
    assert r.json() == {"waveform": "ready", "grid": "unavailable", "reason": "uncertain"}
    assert started == []


def test_prepare_senza_motore(client, monkeypatch):
    c, S, started = client
    _seed(S)
    monkeypatch.setattr(deck_router.essentia_engine, "is_available", lambda: False)
    r = c.post("/api/tracks/1/deck/prepare")
    assert r.status_code == 200
    assert r.json()["grid"] == "unavailable" and r.json()["reason"] == "analysis_engine_unavailable"
    assert started == []
    assert c.get("/api/tracks/1/deck").json()["waveform"] is not None  # i picchi restano


def test_prepare_con_job_occupato_409_ma_picchi_salvati(client, monkeypatch):
    c, S, started = client
    _seed(S)
    monkeypatch.setattr(deck_router.audio_analysis_job, "is_running", lambda: True)
    r = c.post("/api/tracks/1/deck/prepare")
    assert r.status_code == 409 and r.json()["detail"]["code"] == "analysis_busy"
    assert started == []
    assert c.get("/api/tracks/1/deck").json()["waveform"] is not None


def test_prepare_senza_ffmpeg_503_e_decodifica_fallita_500(client, monkeypatch):
    c, S, _ = client
    _seed(S)
    monkeypatch.setattr(deck_router, "ffmpeg_path", lambda: None)
    r = c.post("/api/tracks/1/deck/prepare")
    assert r.status_code == 503 and r.json()["detail"]["code"] == "ffmpeg_unavailable"

    monkeypatch.setattr(deck_router, "ffmpeg_path", lambda: "/usr/bin/ffmpeg")

    def boom(path):
        raise LocalFilesError("ffmpeg non ha potuto decodificare /x/a.mp3")
    monkeypatch.setattr(waveform_service.local_files, "decode_pcm_full", boom)
    r = c.post("/api/tracks/1/deck/prepare")
    assert r.status_code == 500 and r.json()["detail"]["code"] == "waveform_failed"
    with S() as s:
        assert s.get(TrackWaveform, 1) is None


def test_waveform_stantia_torna_null_e_prepare_la_ricalcola(client):
    c, S, _ = client
    _seed(S)
    with S() as s:
        s.add(TrackWaveform(track_id=1, samples_per_second=100, duration_seconds=9.0,
                            audio_hash="OLD", peaks=b"\x01" * 900)); s.commit()
    assert c.get("/api/tracks/1/deck").json()["waveform"] is None
    c.post("/api/tracks/1/deck/prepare")
    body = c.get("/api/tracks/1/deck").json()
    assert body["waveform"]["duration_seconds"] == 1.0


def test_cue_ciclo_completo(client):
    c, S, _ = client
    _seed(S)
    r = c.post("/api/tracks/1/cues", json={"position_seconds": 12.5, "name": " intro "})
    assert r.status_code == 201
    cue = r.json()
    assert cue["position_seconds"] == 12.5 and cue["name"] == "intro"
    c.post("/api/tracks/1/cues", json={"position_seconds": 3.0})
    assert [x["position_seconds"] for x in c.get("/api/tracks/1/deck").json()["cues"]] == [3.0, 12.5]

    r = c.patch(f"/api/tracks/1/cues/{cue['id']}", json={"name": None})
    assert r.status_code == 200 and r.json()["name"] is None and r.json()["position_seconds"] == 12.5
    r = c.patch(f"/api/tracks/1/cues/{cue['id']}", json={"position_seconds": 20.0})
    assert r.json()["position_seconds"] == 20.0

    assert c.delete(f"/api/tracks/1/cues/{cue['id']}").status_code == 204
    assert len(c.get("/api/tracks/1/deck").json()["cues"]) == 1
    assert c.delete(f"/api/tracks/1/cues/{cue['id']}").status_code == 404
    assert c.patch("/api/tracks/2/cues/1", json={"name": "x"}).status_code == 404


def test_cue_limiti_e_bordi(client):
    c, S, _ = client
    _seed(S)
    for i in range(10):
        assert c.post("/api/tracks/1/cues", json={"position_seconds": float(i)}).status_code == 201
    r = c.post("/api/tracks/1/cues", json={"position_seconds": 50.0})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "cue_limit"
    assert c.post("/api/tracks/1/cues", json={"position_seconds": -1.0}).status_code == 422
    assert c.post("/api/tracks/1/cues", json={"position_seconds": 1.0, "name": "x" * 61}).status_code == 422
    r = c.post("/api/tracks/1/cues", json={"position_seconds": 301.5})  # la durata di _seed e' 300
    assert r.status_code == 422 and r.json()["detail"]["code"] == "cue_out_of_range"
```

- [ ] **Step 2: Esegui, devono fallire**

Run: `cd backend && .venv/bin/python -m pytest tests/test_deck_router.py -v`
Expected: FAIL (`ImportError: cannot import name 'deck' from 'app.routers'`)

- [ ] **Step 3: Schemi, in coda a `schemas.py`**

```python
# --- Deck del banco (spec 2026-10-03) --------------------------------------

class DeckTrackOut(BaseModel):
    id: int
    title: str | None = None
    artist: str | None = None
    bpm: float | None = None
    camelot_key: str | None = None
    duration_seconds: int | None = None
    album_art_url: str | None = None
    has_local_file: bool


class DeckGridOut(BaseModel):
    first_beat: float
    bpm: float


class DeckWaveformOut(BaseModel):
    samples_per_second: int
    duration_seconds: float
    peaks: str  # base64 di byte 0-255, uno per picco


class CueOut(BaseModel):
    id: int
    position_seconds: float
    name: str | None = None


class DeckOut(BaseModel):
    """Tutto cio' che serve a un deck in una chiamata: `null` dove manca."""

    track: DeckTrackOut
    grid: DeckGridOut | None = None
    grid_error: str | None = None
    waveform: DeckWaveformOut | None = None
    cues: list[CueOut] = []


class DeckPrepareOut(BaseModel):
    waveform: Literal["ready"]
    grid: Literal["ready", "queued", "unavailable"]
    reason: str | None = None


class CueIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    position_seconds: float = Field(ge=0)
    name: str | None = Field(default=None, max_length=60)


class CueUpdateIn(BaseModel):
    """PATCH parziale: solo i campi presenti si toccano; `name: null` azzera."""

    model_config = ConfigDict(extra="forbid")

    position_seconds: float | None = Field(default=None, ge=0)
    name: str | None = Field(default=None, max_length=60)
```

- [ ] **Step 4: Il router**

```python
# backend/app/routers/deck.py
"""Router DECK: i dati dei due deck del banco (spec 2026-10-03) — griglia,
waveform e cue di una traccia posseduta. Nessun BPM/key si scrive da qui."""

import base64

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.core.http_errors import api_error
from app.db import get_db
from app.integrations import essentia_engine
from app.integrations.local_files import LocalFilesError, ffmpeg_path
from app.models import Track, TrackCue, TrackWaveform
from app.repositories import get_track
from app.schemas import (CueIn, CueOut, CueUpdateIn, DeckGridOut, DeckOut, DeckPrepareOut,
                         DeckTrackOut, DeckWaveformOut)
from app.services import audio_analysis_job, deck_cues
from app.services import waveform as waveform_service

router = APIRouter(prefix="/api/tracks", tags=["deck"])


def _owned(db: Session, track_id: int) -> Track:
    track = get_track(db, track_id)
    if track is None:
        raise api_error(404, "track_not_found", "Track not found")
    if not track.has_local_file or not track.local_path:
        raise api_error(404, "track_no_local_file", "Track has no local file")
    return track


def _cue_out(cue: TrackCue) -> CueOut:
    return CueOut(id=cue.id, position_seconds=cue.position_seconds, name=cue.name)


def _deck_out(db: Session, track: Track) -> DeckOut:
    wf = db.get(TrackWaveform, track.id)
    if not waveform_service.is_fresh(wf, track):
        wf = None  # stantia: `prepare` la ricalcola
    grid = (DeckGridOut(first_beat=track.grid_first_beat, bpm=track.grid_bpm)
            if track.grid_bpm is not None and track.grid_first_beat is not None else None)
    waveform = (DeckWaveformOut(samples_per_second=wf.samples_per_second,
                                duration_seconds=wf.duration_seconds,
                                peaks=base64.b64encode(wf.peaks).decode("ascii"))
                if wf is not None else None)
    return DeckOut(
        track=DeckTrackOut(id=track.id, title=track.title, artist=track.artist, bpm=track.bpm,
                           camelot_key=track.camelot_key, duration_seconds=track.duration_seconds,
                           album_art_url=track.album_art_url, has_local_file=track.has_local_file),
        grid=grid, grid_error=track.grid_error, waveform=waveform,
        cues=[_cue_out(c) for c in deck_cues.list_cues(db, track.id)],
    )


@router.get("/{track_id}/deck", response_model=DeckOut)
def get_deck(track_id: int, db: Session = Depends(get_db)):
    return _deck_out(db, _owned(db, track_id))


@router.post("/{track_id}/deck/prepare", response_model=DeckPrepareOut)
def prepare_deck(track_id: int, response: Response, db: Session = Depends(get_db)):
    """Picchi subito (ffmpeg in sottoprocesso, il server non si blocca); la
    griglia va al job di analisi, unico e mono-utente, sulla sola traccia."""
    track = _owned(db, track_id)
    if ffmpeg_path() is None:
        raise api_error(503, "ffmpeg_unavailable", "ffmpeg not found: needed to draw the waveform")
    try:
        waveform_service.ensure_waveform(db, track)
    except LocalFilesError as exc:
        db.rollback()
        raise api_error(500, "waveform_failed", f"Waveform failed: {exc}") from exc
    db.commit()
    if track.grid_bpm is not None:
        return DeckPrepareOut(waveform="ready", grid="ready")
    if track.grid_error:
        # Una griglia rifiutata non si ritenta a ogni apertura: si rilancia da Analisi.
        return DeckPrepareOut(waveform="ready", grid="unavailable", reason=track.grid_error)
    if not essentia_engine.is_available():
        return DeckPrepareOut(waveform="ready", grid="unavailable", reason="analysis_engine_unavailable")
    if audio_analysis_job.is_running():
        raise api_error(409, "analysis_busy", "Analysis job already running: retry shortly")
    audio_analysis_job.start_job(track_ids=[track.id])
    response.status_code = 202
    return DeckPrepareOut(waveform="ready", grid="queued")


def _cue_of(db: Session, track: Track, cue_id: int) -> TrackCue:
    cue = db.get(TrackCue, cue_id)
    if cue is None or cue.track_id != track.id:
        raise api_error(404, "cue_not_found", "Cue not found")
    return cue


@router.post("/{track_id}/cues", response_model=CueOut, status_code=201)
def create_cue(track_id: int, payload: CueIn, db: Session = Depends(get_db)):
    track = _owned(db, track_id)
    try:
        cue = deck_cues.add_cue(db, track, position_seconds=payload.position_seconds, name=payload.name)
    except deck_cues.CueLimitError:
        raise api_error(409, "cue_limit", f"At most {TrackCue.MAX_PER_TRACK} cues per track")
    except deck_cues.CueOutOfRange:
        raise api_error(422, "cue_out_of_range", "Cue position outside the track")
    db.commit()
    return _cue_out(cue)


@router.patch("/{track_id}/cues/{cue_id}", response_model=CueOut)
def patch_cue(track_id: int, cue_id: int, payload: CueUpdateIn, db: Session = Depends(get_db)):
    track = _owned(db, track_id)
    cue = _cue_of(db, track, cue_id)
    try:
        deck_cues.update_cue(db, track, cue, payload.model_dump(exclude_unset=True))
    except deck_cues.CueOutOfRange:
        raise api_error(422, "cue_out_of_range", "Cue position outside the track")
    db.commit()
    return _cue_out(cue)


@router.delete("/{track_id}/cues/{cue_id}", status_code=204)
def delete_cue(track_id: int, cue_id: int, db: Session = Depends(get_db)):
    track = _owned(db, track_id)
    db.delete(_cue_of(db, track, cue_id))
    db.commit()
    return Response(status_code=204)
```

In `main.py`: aggiungi `deck` all'import da `app.routers` (ordine alfabetico, accanto a `discovery`) e `app.include_router(deck.router)` dopo `app.include_router(analysis.router)`.

- [ ] **Step 5: Esegui, devono passare**

Run: `cd backend && .venv/bin/python -m pytest tests/test_deck_router.py -v && .venv/bin/python -m pytest tests -q`
Expected: 12 passed nel file; la suite intera verde.

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas.py backend/app/routers/deck.py backend/app/main.py backend/tests/test_deck_router.py
git commit -m "feat(deck): endpoint deck, prepare e cue"
```

---

### Task 8: dipendenza wavesurfer.js, tipi e chiamate API del deck

**Files:**
- Modify: `frontend/package.json` (dipendenza `wavesurfer.js`)
- Modify: `frontend/lib/api/types.ts` (in coda)
- Create: `frontend/lib/api/deck.ts`
- Modify: `frontend/lib/api.ts` (barrel)
- Test: `frontend/tests/deck-api.test.ts`

**Interfaces:**
- Produces: tipi `DeckTrack`, `DeckGrid`, `DeckWaveform`, `TrackCue`, `DeckData`, `DeckPrepare`; funzioni `getDeck(trackId)`, `prepareDeck(trackId)`, `createCue(trackId, body)`, `updateCue(trackId, cueId, body)`, `deleteCue(trackId, cueId)`, `decodePeaks(b64): Float32Array` (valori 0..1).

- [ ] **Step 1: Installa la dipendenza**

Run: `cd frontend && npm install wavesurfer.js@^8.0.1`
Expected: `package.json` guadagna `"wavesurfer.js": "^8.0.1"` fra le `dependencies`; `package-lock.json` aggiornato. Licenza BSD-3-Clause.

- [ ] **Step 2: Test**

```ts
// frontend/tests/deck-api.test.ts
import { describe, expect, it } from "vitest";

import { decodePeaks } from "@/lib/api";

describe("decodePeaks", () => {
  it("un byte per picco, riportato in 0..1", () => {
    const b64 = btoa(String.fromCharCode(0, 255, 128));
    const out = decodePeaks(b64);
    expect(out).toBeInstanceOf(Float32Array);
    expect(Array.from(out)).toEqual([0, 1, 128 / 255]);
  });

  it("stringa vuota: nessun picco", () => {
    expect(decodePeaks("").length).toBe(0);
  });
});
```

- [ ] **Step 3: Esegui, deve fallire**

Run: `cd frontend && npx vitest run tests/deck-api.test.ts`
Expected: FAIL (`decodePeaks` non esportata)

- [ ] **Step 4: Tipi, in coda a `lib/api/types.ts`**

```ts
// --- Deck del banco (spec 2026-10-03) --------------------------------------

export interface DeckTrack {
  id: number;
  title: string | null;
  artist: string | null;
  bpm: number | null;
  camelot_key: string | null;
  duration_seconds: number | null;
  album_art_url: string | null;
  has_local_file: boolean;
}

/** Griglia a tempo costante calcolata da Essentia: primo battito e BPM. */
export interface DeckGrid {
  first_beat: number;
  bpm: number;
}

/** Picchi precalcolati: base64 di byte 0-255, `samples_per_second` per secondo. */
export interface DeckWaveform {
  samples_per_second: number;
  duration_seconds: number;
  peaks: string;
}

export interface TrackCue {
  id: number;
  position_seconds: number;
  name: string | null;
}

export interface DeckData {
  track: DeckTrack;
  grid: DeckGrid | null;
  /** too_few_beats | uncertain | messaggio: la griglia manca e questo e' il perche'. */
  grid_error: string | null;
  waveform: DeckWaveform | null;
  cues: TrackCue[];
}

export interface DeckPrepare {
  waveform: "ready";
  grid: "ready" | "queued" | "unavailable";
  reason: string | null;
}
```

- [ ] **Step 5: Chiamate**

```ts
// frontend/lib/api/deck.ts
import { apiDelete, apiGet, apiPatch, apiPost } from "./client";
import type { DeckData, DeckPrepare, TrackCue } from "./types";

/** Griglia, waveform e cue di una traccia posseduta, in una chiamata. */
export function getDeck(trackId: number) {
  return apiGet<DeckData>(`/api/tracks/${trackId}/deck`);
}

/** Calcola i picchi e accoda la griglia. 409 `analysis_busy` se il job e' occupato. */
export function prepareDeck(trackId: number) {
  return apiPost<DeckPrepare>(`/api/tracks/${trackId}/deck/prepare`);
}

export function createCue(trackId: number, body: { position_seconds: number; name?: string | null }) {
  return apiPost<TrackCue>(`/api/tracks/${trackId}/cues`, body);
}

export function updateCue(trackId: number, cueId: number,
                          body: { position_seconds?: number; name?: string | null }) {
  return apiPatch<TrackCue>(`/api/tracks/${trackId}/cues/${cueId}`, body);
}

export function deleteCue(trackId: number, cueId: number) {
  return apiDelete<void>(`/api/tracks/${trackId}/cues/${cueId}`);
}

/** I picchi del backend sono un byte ciascuno: wavesurfer vuole numeri 0..1. */
export function decodePeaks(b64: string): Float32Array {
  const bin = atob(b64);
  const out = new Float32Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i) / 255;
  return out;
}
```

In `lib/api.ts` aggiungi `export * from "./api/deck";` dopo la riga di `./api/transitions`.

- [ ] **Step 6: Esegui, deve passare; poi lint**

Run: `cd frontend && npx vitest run tests/deck-api.test.ts && npm run lint`
Expected: 2 passed; lint pulito

- [ ] **Step 7: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/lib/api/types.ts frontend/lib/api/deck.ts frontend/lib/api.ts frontend/tests/deck-api.test.ts
git commit -m "feat(deck): dipendenza wavesurfer.js, tipi e chiamate API del deck"
```

---

### Task 9: `lib/deck/grid.ts` — la matematica pura

**Files:**
- Create: `frontend/lib/deck/grid.ts`
- Test: `frontend/tests/deck-grid.test.ts`

**Interfaces:**
- Produces: `type Grid = { firstBeat: number; bpm: number }`; `ZOOM_LEVELS`, `PITCH_RANGES`; `period`, `beatTimes`, `phaseAt`, `nearestBeat`, `wrapHalf`, `syncRate`, `alignShift`, `phaseOffsetMs`, `bpmDisagreement`, `clampRate`, `beatJumpSeconds`, `effectiveBpm`, `pitchPercent`, `toGrid(DeckGrid | null)`.

- [ ] **Step 1: Test**

```ts
// frontend/tests/deck-grid.test.ts
import { describe, expect, it } from "vitest";

import {
  alignShift, beatJumpSeconds, beatTimes, bpmDisagreement, clampRate, effectiveBpm,
  nearestBeat, period, phaseAt, phaseOffsetMs, pitchPercent, syncRate, toGrid, wrapHalf,
} from "@/lib/deck/grid";

const G = { firstBeat: 0.37, bpm: 128 };
const P = 60 / 128; // 0.46875

describe("griglia", () => {
  it("periodo e battiti in finestra, senza indici negativi", () => {
    expect(period(G)).toBeCloseTo(P, 10);
    const beats = beatTimes(G, 0, 2);
    expect(beats.map((b) => +b.toFixed(5))).toEqual([0.37, 0.83875, 1.3075, 1.77625]);
    expect(beatTimes(G, -5, 0.5)).toEqual([0.37]); // niente battiti prima del primo
    expect(beatTimes(G, 3, 2)).toEqual([]);
  });

  it("fase in [0,1) e battito piu' vicino", () => {
    expect(phaseAt(G, G.firstBeat + 0.25 * P)).toBeCloseTo(0.25, 9);
    expect(phaseAt(G, G.firstBeat - 0.25 * P)).toBeCloseTo(0.75, 9);
    expect(nearestBeat(G, 1.0)).toBeCloseTo(0.83875, 9);
    expect(nearestBeat(G, 0.05)).toBeCloseTo(0.37, 9); // mai sotto zero, mai prima del primo
  });

  it("wrapHalf riporta in [-0.5, 0.5]", () => {
    expect(wrapHalf(0.3)).toBeCloseTo(0.3);
    expect(wrapHalf(0.7)).toBeCloseTo(-0.3);
    expect(wrapHalf(-0.6)).toBeCloseTo(0.4);
  });

  it("rate di sync con BPM di griglia o nominali", () => {
    expect(syncRate({ bpm: 126, rate: 1 }, { bpm: 124 })).toBeCloseTo(126 / 124, 12);
    expect(syncRate({ bpm: 128, rate: 1.02 }, { bpm: 128 })).toBeCloseTo(1.02, 12);
  });

  it("alignShift: entro mezzo battito e fase uguale al master (100 casi)", () => {
    let seed = 42;
    const rnd = () => { seed = (seed * 1664525 + 1013904223) % 4294967296; return seed / 4294967296; };
    for (let i = 0; i < 100; i++) {
      const gm = { firstBeat: rnd() * 0.5, bpm: 100 + rnd() * 80 };
      const gs = { firstBeat: rnd() * 0.5, bpm: 100 + rnd() * 80 };
      const tm = rnd() * 300, ts = rnd() * 300;
      const d = alignShift(gm, tm, gs, ts);
      expect(Math.abs(d)).toBeLessThanOrEqual(period(gs) / 2 + 1e-9);
      expect(Math.abs(wrapHalf(phaseAt(gs, ts + d) - phaseAt(gm, tm)))).toBeLessThan(1e-6);
    }
  });

  it("scarto di fase in millisecondi sul periodo in uscita del master", () => {
    // schiavo un quarto di battito avanti, master a 128 BPM rate 1: 0.25 * 468.75 ms
    const ts = G.firstBeat + 0.25 * P;
    expect(phaseOffsetMs(G, G.firstBeat, 1, G, ts)).toBeCloseTo(117.1875, 6);
    // a rate 2 il periodo in uscita si dimezza
    expect(phaseOffsetMs(G, G.firstBeat, 2, G, ts)).toBeCloseTo(58.59375, 6);
  });

  it("disaccordo griglia/nominale piegato di ottava", () => {
    expect(bpmDisagreement(126, 63)).toBe(0);
    expect(bpmDisagreement(64, 128)).toBe(0);
    expect(bpmDisagreement(128, 126)).toBeCloseTo(2 / 126, 12);
  });

  it("rate bloccato nella corsa", () => {
    expect(clampRate(1.2, 8)).toBeCloseTo(1.08);
    expect(clampRate(0.8, 16)).toBeCloseTo(0.84);
    expect(clampRate(1.03, 8)).toBeCloseTo(1.03);
  });

  it("salto di battito, BPM effettivo, percentuale", () => {
    expect(beatJumpSeconds(G, 120)).toBeCloseTo(P);
    expect(beatJumpSeconds(null, 120)).toBeCloseTo(0.5);
    expect(beatJumpSeconds(null, null)).toBeNull();
    expect(effectiveBpm(124, 126 / 124)).toBe(126);
    expect(effectiveBpm(null, 1.1)).toBeNull();
    expect(pitchPercent(1.016)).toBe(1.6);
    expect(pitchPercent(0.92)).toBe(-8);
  });

  it("toGrid converte il formato API", () => {
    expect(toGrid({ first_beat: 0.37, bpm: 128 })).toEqual(G);
    expect(toGrid(null)).toBeNull();
  });
});
```

- [ ] **Step 2: Esegui, deve fallire**

Run: `cd frontend && npx vitest run tests/deck-grid.test.ts`
Expected: FAIL (modulo mancante)

- [ ] **Step 3: Il modulo**

```ts
// frontend/lib/deck/grid.ts
/* Matematica pura dei deck (spec 2026-10-03): battiti, fase, sync, corsa del
   pitch. Niente DOM, niente Web Audio: tutto testabile in vitest. */

import type { DeckGrid } from "@/lib/api";

export type Grid = { firstBeat: number; bpm: number };

export const ZOOM_LEVELS = [20, 40, 80, 160] as const;
export const DEFAULT_ZOOM_INDEX = 2; // 80 px/s
export const PITCH_RANGES = [8, 16] as const;
export type PitchRange = (typeof PITCH_RANGES)[number];

export function toGrid(g: DeckGrid | null | undefined): Grid | null {
  return g ? { firstBeat: g.first_beat, bpm: g.bpm } : null;
}

export function period(g: Grid): number {
  return 60 / g.bpm;
}

/** Istanti dei battiti in [from, to], mai prima del primo battito del file. */
export function beatTimes(g: Grid, from: number, to: number): number[] {
  const p = period(g);
  const out: number[] = [];
  const kFrom = Math.max(0, Math.ceil((from - g.firstBeat) / p - 1e-9));
  const kTo = Math.floor((to - g.firstBeat) / p + 1e-9);
  for (let k = kFrom; k <= kTo; k++) out.push(g.firstBeat + k * p);
  return out;
}

/** Frazione di battito in [0, 1) all'istante t. */
export function phaseAt(g: Grid, t: number): number {
  const x = (t - g.firstBeat) / period(g);
  return x - Math.floor(x);
}

export function nearestBeat(g: Grid, t: number): number {
  const p = period(g);
  const k = Math.max(0, Math.round((t - g.firstBeat) / p));
  return g.firstBeat + k * p;
}

/** x riportato in [-0.5, 0.5]: la differenza di fase piu' corta. */
export function wrapHalf(x: number): number {
  return x - Math.round(x);
}

/** Rate che porta lo schiavo al tempo d'uscita del master. I BPM sono quelli
 *  delle griglie quando entrambe esistono, i nominali altrimenti. */
export function syncRate(master: { bpm: number; rate: number }, slave: { bpm: number }): number {
  return (master.bpm * master.rate) / slave.bpm;
}

/** Spostamento in secondi (tempo traccia dello schiavo), entro ±mezzo
 *  periodo, perche' la fase dello schiavo coincida con quella del master. */
export function alignShift(masterGrid: Grid, masterTime: number, slaveGrid: Grid, slaveTime: number): number {
  return wrapHalf(phaseAt(masterGrid, masterTime) - phaseAt(slaveGrid, slaveTime)) * period(slaveGrid);
}

/** Scarto di fase schiavo − master in millisecondi, misurato sul periodo in
 *  uscita del master. Positivo = lo schiavo e' avanti. */
export function phaseOffsetMs(masterGrid: Grid, masterTime: number, masterRate: number,
                              slaveGrid: Grid, slaveTime: number): number {
  const outPeriod = 60 / (masterGrid.bpm * masterRate);
  return wrapHalf(phaseAt(slaveGrid, slaveTime) - phaseAt(masterGrid, masterTime)) * outPeriod * 1000;
}

/** Scarto relativo minimo fra griglia e nominale, provando anche doppio e meta'. */
export function bpmDisagreement(gridBpm: number, nominalBpm: number): number {
  return Math.min(...[1, 2, 0.5].map((f) => Math.abs(gridBpm * f - nominalBpm) / nominalBpm));
}

export function clampRate(rate: number, rangePercent: number): number {
  const lo = 1 - rangePercent / 100;
  const hi = 1 + rangePercent / 100;
  return Math.min(hi, Math.max(lo, rate));
}

/** Quanto vale "un battito" per i salti: la griglia se c'e', il nominale altrimenti. */
export function beatJumpSeconds(grid: Grid | null, nominalBpm: number | null): number | null {
  if (grid) return period(grid);
  if (nominalBpm) return 60 / nominalBpm;
  return null;
}

/** BPM mostrato: nominale × rate, due decimali (la scala del banco). */
export function effectiveBpm(nominalBpm: number | null, rate: number): number | null {
  return nominalBpm == null ? null : Math.round(nominalBpm * rate * 100) / 100;
}

/** Percentuale di pitch con un decimale, come la mostra il banco. */
export function pitchPercent(rate: number): number {
  return Math.round((rate - 1) * 1000) / 10;
}
```

- [ ] **Step 4: Esegui, deve passare**

Run: `cd frontend && npx vitest run tests/deck-grid.test.ts`
Expected: 10 passed

- [ ] **Step 5: Commit**

```bash
git add frontend/lib/deck/grid.ts frontend/tests/deck-grid.test.ts
git commit -m "feat(deck): matematica pura della griglia e del sync"
```

---

### Task 10: `DeckEngine` — il cablaggio Web Audio

**Files:**
- Modify: `frontend/lib/audio-analyser.ts` (export `getAudioContext`)
- Create: `frontend/lib/deck/engine.ts`
- Test: `frontend/tests/deck-engine.test.ts`

**Interfaces:**
- Produces: `getAudioContext(): AudioContext | null`; `type DeckSide = "A" | "B"`; `setPreservesPitch(el, on): boolean`; `class DeckEngine` con `constructor(elements: Record<DeckSide, HTMLAudioElement>, ctx?: AudioContext | null)`, `load(side, url)`, `play(side): Promise<void>`, `pause(side)`, `seek(side, t)`, `position(side)`, `duration(side)`, `setRate(side, rate, keyLock): boolean`, `setVolume(side, v)`, `setLowCut(side, on)`, `dispose()`.

- [ ] **Step 1: Test**

```ts
// frontend/tests/deck-engine.test.ts
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DeckEngine, setPreservesPitch } from "@/lib/deck/engine";

type AnyNode = { connect: ReturnType<typeof vi.fn>; disconnect: ReturnType<typeof vi.fn> };

function fakeCtx(state: "running" | "suspended" = "running") {
  const node = (): AnyNode => ({ connect: vi.fn(), disconnect: vi.fn() });
  const gains: Array<AnyNode & { gain: { value: number } }> = [];
  const filters: Array<AnyNode & { type: string; frequency: { value: number }; Q: { value: number } }> = [];
  const sources: AnyNode[] = [];
  const ctx = {
    state,
    destination: { kind: "destination" },
    resume: vi.fn(function (this: { state: string }) { this.state = "running"; return Promise.resolve(); }),
    createGain: vi.fn(() => { const g = { ...node(), gain: { value: 1 } }; gains.push(g); return g; }),
    createBiquadFilter: vi.fn(() => { const f = { ...node(), type: "", frequency: { value: 0 }, Q: { value: 1 } }; filters.push(f); return f; }),
    createMediaElementSource: vi.fn(() => { const s = node(); sources.push(s); return s; }),
  };
  return { ctx: ctx as unknown as AudioContext, gains, filters, sources, raw: ctx };
}

function elements() {
  const A = document.createElement("audio");
  const B = document.createElement("audio");
  return { A, B };
}

beforeEach(() => {
  vi.spyOn(HTMLMediaElement.prototype, "play").mockImplementation(function (this: HTMLMediaElement) {
    this.dispatchEvent(new Event("play"));
    return Promise.resolve();
  });
  vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(function (this: HTMLMediaElement) {
    this.dispatchEvent(new Event("pause"));
  });
  vi.spyOn(HTMLMediaElement.prototype, "load").mockImplementation(() => {});
});
afterEach(() => vi.restoreAllMocks());

describe("DeckEngine", () => {
  it("cabla filtro → gain → master → uscita per ogni deck", () => {
    const { ctx, gains, filters, raw } = fakeCtx();
    new DeckEngine(elements(), ctx);
    // 1 master + 2 gain di deck; 2 filtri passa-alto a 10 Hz, Q 0,7
    expect(gains).toHaveLength(3);
    expect(filters).toHaveLength(2);
    for (const f of filters) {
      expect(f.type).toBe("highpass");
      expect(f.frequency.value).toBe(10);
      expect(f.Q.value).toBeCloseTo(0.7);
    }
    expect(gains[0].connect).toHaveBeenCalledWith(raw.destination); // il master
    expect(filters[0].connect).toHaveBeenCalledWith(gains[1]);
    expect(gains[1].connect).toHaveBeenCalledWith(gains[0]);
  });

  it("l'elemento entra nel grafo una sola volta, al primo play", async () => {
    const { ctx, sources, raw, filters } = fakeCtx();
    const els = elements();
    const eng = new DeckEngine(els, ctx);
    await eng.play("A");
    await eng.play("A");
    expect(raw.createMediaElementSource).toHaveBeenCalledTimes(1);
    expect(raw.createMediaElementSource).toHaveBeenCalledWith(els.A);
    expect(sources[0].connect).toHaveBeenCalledWith(filters[0]);
    expect(els.A.crossOrigin).toBe("anonymous");
  });

  it("contesto sospeso: lo riprende prima di suonare", async () => {
    const { ctx, raw } = fakeCtx("suspended");
    const eng = new DeckEngine(elements(), ctx);
    await eng.play("B");
    expect(raw.resume).toHaveBeenCalled();
    expect(raw.createMediaElementSource).toHaveBeenCalledTimes(1);
  });

  it("volume e taglio bassi agiscono sui nodi del deck giusto", () => {
    const { ctx, gains, filters } = fakeCtx();
    const eng = new DeckEngine(elements(), ctx);
    eng.setVolume("B", 0.3);
    expect(gains[2].gain.value).toBeCloseTo(0.3);
    expect(gains[1].gain.value).toBe(1);
    eng.setLowCut("A", true);
    expect(filters[0].frequency.value).toBe(300);
    expect(filters[1].frequency.value).toBe(10);
    eng.setLowCut("A", false);
    expect(filters[0].frequency.value).toBe(10);
  });

  it("rate e master tempo sull'elemento", () => {
    const els = elements();
    Object.defineProperty(els.A, "preservesPitch", { configurable: true, writable: true, value: true });
    const eng = new DeckEngine(els, fakeCtx().ctx);
    expect(eng.setRate("A", 1.04, false)).toBe(true);
    expect(els.A.playbackRate).toBeCloseTo(1.04);
    expect((els.A as HTMLMediaElement & { preservesPitch: boolean }).preservesPitch).toBe(false);
    // B non espone preservesPitch ne' il prefisso webkit: il master tempo non e' supportato
    expect(setPreservesPitch(els.B, true)).toBe(false);
  });

  it("seek mai sotto zero (Review Focus 3) e carica l'URL una volta sola", () => {
    const els = elements();
    const eng = new DeckEngine(els, fakeCtx().ctx);
    eng.load("A", "/api/tracks/5/audio");
    eng.load("A", "/api/tracks/5/audio");
    expect(HTMLMediaElement.prototype.load).toHaveBeenCalledTimes(1);
    Object.defineProperty(els.A, "currentTime", { configurable: true, writable: true, value: 1 });
    eng.seek("A", -0.3);
    expect(els.A.currentTime).toBe(0);
  });

  it("senza Web Audio suona lo stesso: volume sull'elemento", async () => {
    const els = elements();
    const eng = new DeckEngine(els, null);
    await eng.play("A");
    eng.setVolume("A", 0.5);
    expect(els.A.volume).toBeCloseTo(0.5);
    eng.setLowCut("A", true); // non deve lanciare
  });

  it("dispose ferma e scollega tutto", async () => {
    const { ctx, sources, gains } = fakeCtx();
    const els = elements();
    const eng = new DeckEngine(els, ctx);
    await eng.play("A");
    eng.dispose();
    expect(HTMLMediaElement.prototype.pause).toHaveBeenCalled();
    expect(sources[0].disconnect).toHaveBeenCalled();
    expect(gains[0].disconnect).toHaveBeenCalled();
    expect(els.A.getAttribute("src")).toBeNull();
  });
});
```

- [ ] **Step 2: Esegui, deve fallire**

Run: `cd frontend && npx vitest run tests/deck-engine.test.ts`
Expected: FAIL (modulo mancante)

- [ ] **Step 3: Esponi il contesto condiviso**

In `lib/audio-analyser.ts`, dopo `primeOnFirstGesture`:

```ts
/** Il contesto audio condiviso, creato se manca: i deck del banco ci
 *  attaccano i loro elementi invece di aprirne un secondo (un solo
 *  AudioContext per pagina, vedi spec 2026-10-03). Null senza Web Audio. */
export function getAudioContext(): AudioContext | null {
  return ensureGraph()?.ctx ?? null;
}
```

- [ ] **Step 4: Il motore**

```ts
// frontend/lib/deck/engine.ts
/* Cablaggio Web Audio dei due deck (spec 2026-10-03). Imperativo e sottile:
   non conosce React ne' il banco. Per deck: <audio> → passa-alto (taglio
   bassi) → gain (volume) → gain master → uscita. Stessa regola di
   audio-analyser.ts: l'elemento entra nel grafo solo a contesto in esecuzione,
   perche' `createMediaElementSource` e' irreversibile e a contesto sospeso
   azzittirebbe la traccia. Prima di quel momento l'elemento suona da solo. */

import { getAudioContext } from "@/lib/audio-analyser";

export type DeckSide = "A" | "B";
export const SIDES: readonly DeckSide[] = ["A", "B"];

const LOWCUT_OFF_HZ = 10;
const LOWCUT_ON_HZ = 300;
const LOWCUT_Q = 0.7;

type Chain = {
  el: HTMLAudioElement;
  source: MediaElementAudioSourceNode | null;
  filter: BiquadFilterNode | null;
  gain: GainNode | null;
};

/** Master tempo: `preservesPitch`, con ripiego sul prefisso WebKit. Falso se
 *  il browser non espone nessuno dei due (il dock disattiva l'interruttore). */
export function setPreservesPitch(el: HTMLMediaElement, on: boolean): boolean {
  const anyEl = el as HTMLMediaElement & { webkitPreservesPitch?: boolean };
  if ("preservesPitch" in el) {
    el.preservesPitch = on;
    return true;
  }
  if ("webkitPreservesPitch" in anyEl) {
    anyEl.webkitPreservesPitch = on;
    return true;
  }
  return false;
}

export class DeckEngine {
  private readonly ctx: AudioContext | null;
  private master: GainNode | null = null;
  private readonly chains: Record<DeckSide, Chain>;

  constructor(elements: Record<DeckSide, HTMLAudioElement>, ctx: AudioContext | null = getAudioContext()) {
    this.ctx = ctx;
    if (ctx) {
      this.master = ctx.createGain();
      this.master.connect(ctx.destination);
    }
    this.chains = { A: this.chain(elements.A), B: this.chain(elements.B) };
  }

  private chain(el: HTMLAudioElement): Chain {
    // Sorgente sempre nostra (endpoint audio del backend): in Tauri e'
    // cross-origin ma CORS-approvata, e senza questa dichiarazione il grafo
    // riceverebbe silenzio (vedi la nota in audio-analyser.ts).
    el.crossOrigin = "anonymous";
    el.preload = "auto";
    if (!this.ctx || !this.master) return { el, source: null, filter: null, gain: null };
    const filter = this.ctx.createBiquadFilter();
    filter.type = "highpass";
    filter.frequency.value = LOWCUT_OFF_HZ;
    filter.Q.value = LOWCUT_Q;
    const gain = this.ctx.createGain();
    filter.connect(gain);
    gain.connect(this.master);
    return { el, source: null, filter, gain };
  }

  private attach(side: DeckSide): void {
    const c = this.chains[side];
    if (c.source || !this.ctx || !c.filter || this.ctx.state !== "running") return;
    try {
      c.source = this.ctx.createMediaElementSource(c.el);
      c.source.connect(c.filter);
    } catch {
      // Gia' innestato altrove o elemento non innestabile: suona da solo.
    }
  }

  load(side: DeckSide, url: string): void {
    const el = this.chains[side].el;
    if (el.getAttribute("src") === url) return;
    el.setAttribute("src", url);
    el.load();
  }

  async play(side: DeckSide): Promise<void> {
    if (this.ctx && this.ctx.state !== "running") await this.ctx.resume();
    this.attach(side);
    await this.chains[side].el.play();
  }

  pause(side: DeckSide): void {
    this.chains[side].el.pause();
  }

  seek(side: DeckSide, t: number): void {
    this.chains[side].el.currentTime = Math.max(0, t);
  }

  position(side: DeckSide): number {
    return this.chains[side].el.currentTime || 0;
  }

  duration(side: DeckSide): number {
    const d = this.chains[side].el.duration;
    return Number.isFinite(d) ? d : 0;
  }

  /** Ritorna false se il master tempo non e' supportato dal browser. */
  setRate(side: DeckSide, rate: number, keyLock: boolean): boolean {
    const el = this.chains[side].el;
    el.playbackRate = rate;
    return setPreservesPitch(el, keyLock);
  }

  setVolume(side: DeckSide, v: number): void {
    const c = this.chains[side];
    if (c.gain) c.gain.gain.value = v;
    else c.el.volume = v;
  }

  setLowCut(side: DeckSide, on: boolean): void {
    const f = this.chains[side].filter;
    if (f) f.frequency.value = on ? LOWCUT_ON_HZ : LOWCUT_OFF_HZ;
  }

  dispose(): void {
    for (const side of SIDES) {
      const c = this.chains[side];
      c.el.pause();
      c.source?.disconnect();
      c.filter?.disconnect();
      c.gain?.disconnect();
      c.el.removeAttribute("src");
      c.el.load();
    }
    this.master?.disconnect();
  }
}
```

- [ ] **Step 5: Esegui, deve passare; lint**

Run: `cd frontend && npx vitest run tests/deck-engine.test.ts tests/player-transport.test.tsx && npm run lint`
Expected: tutti passed; lint pulito

- [ ] **Step 6: Commit**

```bash
git add frontend/lib/audio-analyser.ts frontend/lib/deck/engine.ts frontend/tests/deck-engine.test.ts
git commit -m "feat(deck): motore Web Audio dei due deck"
```

---

### Task 11: testi `deck` nei due dizionari e `CueStrip`

**Files:**
- Modify: `frontend/lib/i18n/en.ts`, `frontend/lib/i18n/it.ts` (blocco `deck` subito dopo il blocco `player`)
- Create: `frontend/components/deck/cue-strip.tsx`
- Test: `frontend/tests/deck-cue-strip.test.tsx`

**Interfaces:**
- Produces: `t.deck.*` (chiavi sotto); `CueStrip` con props `{ side: DeckSide; cues: TrackCue[]; snapToBeat: boolean; canSnap: boolean; onToggleSnap(): void; onAdd(): void; onJump(cue): void; onRename(cue, name: string | null): void; onDelete(cue): void }`; `MAX_CUES = 10`.

- [ ] **Step 1: Test**

```tsx
// frontend/tests/deck-cue-strip.test.tsx
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CueStrip, MAX_CUES } from "@/components/deck/cue-strip";
import type { TrackCue } from "@/lib/api";

const cues: TrackCue[] = [
  { id: 11, position_seconds: 10, name: "intro" },
  { id: 12, position_seconds: 42.5, name: null },
];

function mount(extra: Partial<Parameters<typeof CueStrip>[0]> = {}) {
  const props = {
    side: "A" as const, cues, snapToBeat: true, canSnap: true,
    onToggleSnap: vi.fn(), onAdd: vi.fn(), onJump: vi.fn(), onRename: vi.fn(), onDelete: vi.fn(),
    ...extra,
  };
  render(<CueStrip {...props} />);
  return props;
}

afterEach(cleanup);

describe("CueStrip", () => {
  it("chip numerate con il nome; il click salta", () => {
    const p = mount();
    fireEvent.click(screen.getByRole("button", { name: "1 intro" }));
    expect(p.onJump).toHaveBeenCalledWith(cues[0]);
    expect(screen.getByRole("button", { name: "2" })).toBeTruthy();
  });

  it("la matita apre la rinomina in linea; Invio salva, vuoto azzera", () => {
    const p = mount();
    fireEvent.click(screen.getAllByTitle("Rinomina la cue")[0]);
    const input = screen.getByPlaceholderText("nome") as HTMLInputElement;
    expect(input.value).toBe("intro");
    fireEvent.change(input, { target: { value: "  break " } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(p.onRename).toHaveBeenCalledWith(cues[0], "break");

    fireEvent.click(screen.getAllByTitle("Rinomina la cue")[1]);
    const input2 = screen.getByPlaceholderText("nome") as HTMLInputElement;
    fireEvent.change(input2, { target: { value: "   " } });
    fireEvent.keyDown(input2, { key: "Enter" });
    expect(p.onRename).toHaveBeenLastCalledWith(cues[1], null);
  });

  it("la × elimina", () => {
    const p = mount();
    fireEvent.click(screen.getAllByTitle("Elimina la cue")[1]);
    expect(p.onDelete).toHaveBeenCalledWith(cues[1]);
  });

  it("metti cue e al battito", () => {
    const p = mount();
    fireEvent.click(screen.getByRole("button", { name: "Metti cue" }));
    expect(p.onAdd).toHaveBeenCalled();
    const snap = screen.getByRole("button", { name: "al battito" });
    expect(snap.getAttribute("aria-pressed")).toBe("true");
    fireEvent.click(snap);
    expect(p.onToggleSnap).toHaveBeenCalled();
  });

  it("senza griglia «al battito» e' spento e disabilitato", () => {
    mount({ canSnap: false, snapToBeat: false });
    const snap = screen.getByRole("button", { name: "al battito" }) as HTMLButtonElement;
    expect(snap.disabled).toBe(true);
    expect(snap.getAttribute("aria-pressed")).toBe("false");
  });

  it("alla decima cue «metti cue» si disabilita", () => {
    const dieci = Array.from({ length: MAX_CUES }, (_, i) => ({ id: i + 1, position_seconds: i * 10, name: null }));
    mount({ cues: dieci });
    const add = screen.getByRole("button", { name: "Metti cue" }) as HTMLButtonElement;
    expect(add.disabled).toBe(true);
    expect(add.title).toBe("Massimo dieci cue per traccia");
  });
});
```

- [ ] **Step 2: Esegui, deve fallire**

Run: `cd frontend && npx vitest run tests/deck-cue-strip.test.tsx`
Expected: FAIL (modulo mancante)

- [ ] **Step 3: Testi, blocco `deck` in `en.ts` subito dopo il blocco `player: { … },`**

```ts
  deck: {
    audition: "Audition the transition",
    auditionNeedsFiles: "Both tracks need a local file",
    title: (side: string) => `Deck ${side}`,
    close: "Close the decks",
    hideControls: "Hide pitch and volume",
    showControls: "Show pitch and volume",
    play: "Play",
    pause: "Pause",
    cueLabel: "cue",
    addCue: "Set cue",
    snapToBeat: "on the beat",
    renameCue: "Rename the cue",
    deleteCue: "Delete the cue",
    cueNamePlaceholder: "name",
    cueLimit: "At most ten cues per track",
    beatBack: "One beat back",
    beatForward: "One beat forward",
    nudgeBack: "−10 ms",
    nudgeForward: "+10 ms",
    pitch: "pitch",
    pitchRange: (r: number) => `±${r} %`,
    resetPitch: "Reset the pitch",
    masterTempo: "Master tempo",
    noMasterTempo: "Master tempo is not supported by this browser",
    sync: (other: string) => `Sync to ${other}`,
    syncRateOnly: "Without a beat grid only the tempo syncs, not the phase",
    realign: "Realign",
    phase: "phase",
    zoom: "zoom",
    zoomIn: "Zoom in",
    zoomOut: "Zoom out",
    volume: "vol",
    lowCut: "bass",
    lowCutTitle: "Low cut",
    usePlayBpm: "Use as “I play it at”",
    nominalBpm: "BPM",
    playBpm: (b: string) => `I play it at ${b}`,
    waveformComputing: "computing the waveform",
    gridComputing: "computing the beat grid",
    analysisBusy: "bulk analysis running, waiting",
    gridUnavailable: (reason: string) => `beat grid unavailable: ${reason}`,
    waveformUnavailable: (reason: string) => `waveform unavailable: ${reason}`,
    reasons: {
      analysis_engine_unavailable: "analysis engine missing",
      uncertain: "uncertain grid",
      too_few_beats: "too few beats",
      ffmpeg_unavailable: "ffmpeg missing",
      waveform_failed: "decoding failed",
      timeout: "analysis did not finish",
      other: "error",
    } as Record<string, string>,
    gridDisagree: (grid: string, nominal: string) => `grid ${grid} BPM, nominal ${nominal}`,
    fileMissing: "file no longer available",
    unsupportedFormat: "Format not playable in the browser",
  },
```

e in `it.ts`, stessa posizione, stesse chiavi:

```ts
  deck: {
    audition: "Prova il passaggio",
    auditionNeedsFiles: "Serve il file locale di entrambe le tracce",
    title: (side: string) => `Deck ${side}`,
    close: "Chiudi i deck",
    hideControls: "Nascondi pitch e volume",
    showControls: "Mostra pitch e volume",
    play: "Riproduci",
    pause: "Pausa",
    cueLabel: "cue",
    addCue: "Metti cue",
    snapToBeat: "al battito",
    renameCue: "Rinomina la cue",
    deleteCue: "Elimina la cue",
    cueNamePlaceholder: "nome",
    cueLimit: "Massimo dieci cue per traccia",
    beatBack: "Un battito indietro",
    beatForward: "Un battito avanti",
    nudgeBack: "−10 ms",
    nudgeForward: "+10 ms",
    pitch: "pitch",
    pitchRange: (r: number) => `±${r} %`,
    resetPitch: "Azzera il pitch",
    masterTempo: "Master tempo",
    noMasterTempo: "Master tempo non supportato da questo browser",
    sync: (other: string) => `Sync su ${other}`,
    syncRateOnly: "Senza griglia si sincronizza solo il tempo, non la fase",
    realign: "Riallinea",
    phase: "fase",
    zoom: "zoom",
    zoomIn: "Avvicina",
    zoomOut: "Allontana",
    volume: "vol",
    lowCut: "bassi",
    lowCutTitle: "Taglio bassi",
    usePlayBpm: "Usa come «la suono a»",
    nominalBpm: "BPM",
    playBpm: (b: string) => `la suono a ${b}`,
    waveformComputing: "waveform in calcolo",
    gridComputing: "griglia in calcolo",
    analysisBusy: "analisi di massa in corso, attendo",
    gridUnavailable: (reason: string) => `griglia non disponibile: ${reason}`,
    waveformUnavailable: (reason: string) => `waveform non disponibile: ${reason}`,
    reasons: {
      analysis_engine_unavailable: "motore di analisi assente",
      uncertain: "griglia incerta",
      too_few_beats: "pochi battiti",
      ffmpeg_unavailable: "ffmpeg assente",
      waveform_failed: "decodifica fallita",
      timeout: "l'analisi non e' finita",
      other: "errore",
    } as Record<string, string>,
    gridDisagree: (grid: string, nominal: string) => `griglia ${grid} BPM, nominale ${nominal}`,
    fileMissing: "file non più disponibile",
    unsupportedFormat: "Formato non riproducibile nel browser",
  },
```

Il test `tests/i18n-*.test.ts` esistente che confronta le chiavi dei due dizionari (se c'e') deve restare verde: `Dictionary = typeof en`, quindi `it.ts` non compila se manca una chiave.

- [ ] **Step 4: Il componente**

```tsx
// frontend/components/deck/cue-strip.tsx
"use client";

import { useState } from "react";
import { Pencil, X } from "lucide-react";

import type { TrackCue } from "@/lib/api";
import type { DeckSide } from "@/lib/deck/engine";
import { useT } from "@/lib/i18n";

export const MAX_CUES = 10;

type Props = {
  side: DeckSide;
  cues: TrackCue[];
  snapToBeat: boolean;
  /** Falso senza griglia: l'interruttore resta spento e disabilitato. */
  canSnap: boolean;
  onToggleSnap: () => void;
  onAdd: () => void;
  onJump: (cue: TrackCue) => void;
  onRename: (cue: TrackCue, name: string | null) => void;
  onDelete: (cue: TrackCue) => void;
};

const chip = "inline-flex items-center gap-1 rounded-full border border-border-strong px-2 py-0.5 text-[11px] text-fg hover:bg-elevated focus-visible:outline focus-visible:outline-1 focus-visible:outline-fg";
const small = "border border-border px-2 py-0.5 text-[11px] text-fg hover:bg-elevated disabled:opacity-40 focus-visible:outline focus-visible:outline-1 focus-visible:outline-fg";

/** Le memory cue di un deck: chip numerate per posizione, rinomina in linea,
 *  elimina, "metti cue" con l'arrotondamento al battito. Non sa niente di
 *  audio: chi la monta decide dove si e' e cosa succede al salto. */
export function CueStrip({ side, cues, snapToBeat, canSnap, onToggleSnap, onAdd, onJump, onRename, onDelete }: Props) {
  const t = useT();
  const [editing, setEditing] = useState<number | null>(null);
  const [draft, setDraft] = useState("");
  const full = cues.length >= MAX_CUES;

  const commit = (cue: TrackCue) => {
    const name = draft.trim() || null;
    setEditing(null);
    if (name !== (cue.name ?? null)) onRename(cue, name);
  };

  return (
    <div className="flex flex-wrap items-center gap-1.5" data-testid={`cue-strip-${side}`}>
      <span className="text-[10px] uppercase tracking-wider text-faint">{t.deck.cueLabel}</span>
      {cues.map((cue, i) =>
        editing === cue.id ? (
          <input
            key={cue.id}
            autoFocus
            value={draft}
            placeholder={t.deck.cueNamePlaceholder}
            maxLength={60}
            onChange={(e) => setDraft(e.target.value)}
            onBlur={() => commit(cue)}
            onKeyDown={(e) => {
              if (e.key === "Enter") commit(cue);
              if (e.key === "Escape") setEditing(null);
            }}
            className="w-24 border border-border-strong bg-surface px-1.5 py-0.5 text-[11px]"
          />
        ) : (
          <span key={cue.id} className="inline-flex items-center gap-0.5">
            <button type="button" className={chip} onClick={() => onJump(cue)}>
              <span className="tnum">{i + 1}</span>
              {cue.name && <span className="max-w-24 truncate">{cue.name}</span>}
            </button>
            <button type="button" title={t.deck.renameCue} className="p-0.5 text-muted hover:text-fg"
              onClick={() => { setDraft(cue.name ?? ""); setEditing(cue.id); }}>
              <Pencil size={11} />
            </button>
            <button type="button" title={t.deck.deleteCue} className="p-0.5 text-muted hover:text-danger"
              onClick={() => onDelete(cue)}>
              <X size={11} />
            </button>
          </span>
        ),
      )}
      <button type="button" className={small} disabled={full} title={full ? t.deck.cueLimit : undefined}
        onClick={onAdd} data-testid={`deck-cue-add-${side}`}>
        + {t.deck.addCue}
      </button>
      <button type="button" aria-pressed={snapToBeat && canSnap} disabled={!canSnap}
        className={`${small} rounded-full aria-pressed:border-fg-strong`} onClick={onToggleSnap}>
        {t.deck.snapToBeat}
      </button>
    </div>
  );
}
```

- [ ] **Step 5: Esegui, deve passare; lint**

Run: `cd frontend && npx vitest run tests/deck-cue-strip.test.tsx tests/i18n-organize.test.ts && npm run lint`
Expected: tutti passed; lint pulito

- [ ] **Step 6: Commit**

```bash
git add frontend/lib/i18n/en.ts frontend/lib/i18n/it.ts frontend/components/deck/cue-strip.tsx frontend/tests/deck-cue-strip.test.tsx
git commit -m "feat(deck): testi del deck e striscia delle cue"
```

---

### Task 12: `DeckWaveform` — wavesurfer, Minimap, Regions, canvas dei battiti

**Files:**
- Create: `frontend/components/deck/deck-waveform.tsx`
- Test: `frontend/tests/deck-waveform.test.tsx`

**Interfaces:**
- Produces: `DeckWaveform` con props `{ side: DeckSide; audioEl: HTMLAudioElement | null; audioUrl: string; waveform: DeckWaveform | null; grid: Grid | null; cues: TrackCue[]; minPxPerSec: number; onSeek(t: number): void; onCueClick(cueId: number): void }`. Testid: `deck-waveform-{side}`, `deck-grid-canvas-{side}`.
- Consumes: `decodePeaks`, `beatTimes`, wavesurfer.js 8 (`WaveSurfer.create({ media, url, peaks, duration, … })`, eventi `scroll`, `zoom`, `ready`, `interaction`), plugin `Regions` (`addRegion({ id, start, content })`, evento `region-clicked`), plugin `Minimap` (`container`).

- [ ] **Step 1: Test**

```tsx
// frontend/tests/deck-waveform.test.tsx
import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const ws = vi.hoisted(() => {
  const handlers: Record<string, (...a: unknown[]) => void> = {};
  const instance = {
    on: vi.fn((ev: string, fn: (...a: unknown[]) => void) => { handlers[ev] = fn; }),
    zoom: vi.fn(),
    destroy: vi.fn(),
  };
  const regions = {
    on: vi.fn((ev: string, fn: (...a: unknown[]) => void) => { handlers[`regions:${ev}`] = fn; }),
    addRegion: vi.fn(),
    clearRegions: vi.fn(),
  };
  return {
    handlers, instance, regions,
    create: vi.fn(() => instance),
    regionsCreate: vi.fn(() => regions),
    minimapCreate: vi.fn(() => ({ kind: "minimap" })),
  };
});
vi.mock("wavesurfer.js", () => ({ default: { create: ws.create } }));
vi.mock("wavesurfer.js/dist/plugins/regions.esm.js", () => ({ default: { create: ws.regionsCreate } }));
vi.mock("wavesurfer.js/dist/plugins/minimap.esm.js", () => ({ default: { create: ws.minimapCreate } }));

import { DeckWaveform } from "@/components/deck/deck-waveform";

const peaks = btoa(String.fromCharCode(0, 255, 128, 64));
const waveform = { samples_per_second: 100, duration_seconds: 0.04, peaks };
const cues = [{ id: 7, position_seconds: 1.5, name: "a" }, { id: 8, position_seconds: 3, name: null }];

afterEach(() => { cleanup(); vi.clearAllMocks(); });

describe("DeckWaveform", () => {
  it("senza picchi non monta wavesurfer", () => {
    render(<DeckWaveform side="A" audioEl={document.createElement("audio")} audioUrl="/a" waveform={null}
      grid={null} cues={[]} minPxPerSec={80} onSeek={() => {}} onCueClick={() => {}} />);
    expect(ws.create).not.toHaveBeenCalled();
  });

  it("monta sull'elemento con i picchi decodificati e la durata; una regione per cue", () => {
    const el = document.createElement("audio");
    const onCueClick = vi.fn();
    const onSeek = vi.fn();
    const { unmount } = render(<DeckWaveform side="A" audioEl={el} audioUrl="/api/tracks/1/audio" waveform={waveform}
      grid={null} cues={cues} minPxPerSec={80} onSeek={onSeek} onCueClick={onCueClick} />);
    const opts = ws.create.mock.calls[0][0] as Record<string, unknown>;
    expect(opts.media).toBe(el);
    expect(opts.url).toBe("/api/tracks/1/audio");
    expect(opts.duration).toBe(0.04);
    expect(opts.minPxPerSec).toBe(80);
    expect(opts.autoCenter).toBe(true);
    expect(Array.from((opts.peaks as Float32Array[])[0])).toEqual([0, 1, 128 / 255, 64 / 255]);
    expect(ws.regions.addRegion).toHaveBeenCalledTimes(2);
    expect(ws.regions.addRegion.mock.calls[0][0]).toMatchObject({ id: "7", start: 1.5, content: "1", drag: false, resize: false });
    expect(ws.regions.addRegion.mock.calls[1][0]).toMatchObject({ id: "8", start: 3, content: "2" });

    ws.handlers["regions:region-clicked"]({ id: "8" }, { stopPropagation: () => {} });
    expect(onCueClick).toHaveBeenCalledWith(8);
    ws.handlers["interaction"](12.25);
    expect(onSeek).toHaveBeenCalledWith(12.25);

    unmount();
    expect(ws.instance.destroy).toHaveBeenCalled();
  });

  it("lo zoom segue la prop senza rimontare", () => {
    const el = document.createElement("audio");
    const { rerender } = render(<DeckWaveform side="B" audioEl={el} audioUrl="/a" waveform={waveform}
      grid={null} cues={[]} minPxPerSec={80} onSeek={() => {}} onCueClick={() => {}} />);
    rerender(<DeckWaveform side="B" audioEl={el} audioUrl="/a" waveform={waveform}
      grid={null} cues={[]} minPxPerSec={160} onSeek={() => {}} onCueClick={() => {}} />);
    expect(ws.create).toHaveBeenCalledTimes(1);
    expect(ws.instance.zoom).toHaveBeenLastCalledWith(160);
  });

  it("cambiano le cue: regioni azzerate e ridisegnate", () => {
    const el = document.createElement("audio");
    const { rerender } = render(<DeckWaveform side="A" audioEl={el} audioUrl="/a" waveform={waveform}
      grid={null} cues={cues} minPxPerSec={80} onSeek={() => {}} onCueClick={() => {}} />);
    rerender(<DeckWaveform side="A" audioEl={el} audioUrl="/a" waveform={waveform}
      grid={null} cues={[cues[1]]} minPxPerSec={80} onSeek={() => {}} onCueClick={() => {}} />);
    expect(ws.regions.clearRegions).toHaveBeenCalled();
    expect(ws.regions.addRegion).toHaveBeenLastCalledWith(expect.objectContaining({ id: "8", content: "1" }));
  });
});
```

- [ ] **Step 2: Esegui, deve fallire**

Run: `cd frontend && npx vitest run tests/deck-waveform.test.tsx`
Expected: FAIL (modulo mancante)

- [ ] **Step 3: Il componente**

```tsx
// frontend/components/deck/deck-waveform.tsx
"use client";

import { useCallback, useEffect, useRef } from "react";
import WaveSurfer from "wavesurfer.js";
import Minimap from "wavesurfer.js/dist/plugins/minimap.esm.js";
import Regions from "wavesurfer.js/dist/plugins/regions.esm.js";

import { decodePeaks, type DeckWaveform as DeckWaveformData, type TrackCue } from "@/lib/api";
import type { DeckSide } from "@/lib/deck/engine";
import { beatTimes, type Grid } from "@/lib/deck/grid";

type Props = {
  side: DeckSide;
  audioEl: HTMLAudioElement | null;
  audioUrl: string;
  waveform: DeckWaveformData | null;
  grid: Grid | null;
  cues: TrackCue[];
  minPxPerSec: number;
  onSeek: (t: number) => void;
  onCueClick: (cueId: number) => void;
};

/** I colori dai token del design system, letti quando servono: cosi' il tema
 *  scuro e quello chiaro passano dalla stessa riga, senza doppio codice. */
function tokens() {
  const s = typeof window === "undefined" ? null : getComputedStyle(document.documentElement);
  const v = (name: string, fallback: string) => (s?.getPropertyValue(name).trim() || fallback);
  return {
    wave: v("--c-muted", "#898989"),
    progress: v("--c-fg-strong", "#ededed"),
    beat: v("--c-faint", "#555555"),
    cue: v("--c-danger", "#d8593f"),
    mini: v("--c-faint", "#555555"),
  };
}

/** Waveform di un deck su wavesurfer.js: `media` e' l'<audio> del deck, i
 *  picchi arrivano gia' calcolati dal backend (niente fetch, niente decode).
 *  Sopra, un canvas con i battiti della griglia nella finestra visibile: tutti
 *  uguali, perche' la battuta uno non e' nota. Non si usano Regions per i
 *  battiti (migliaia di nodi DOM); si usano per le cue, che sono al massimo
 *  dieci. */
export function DeckWaveform({ side, audioEl, audioUrl, waveform, grid, cues, minPxPerSec, onSeek, onCueClick }: Props) {
  const mainRef = useRef<HTMLDivElement>(null);
  const miniRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const wsRef = useRef<WaveSurfer | null>(null);
  const regionsRef = useRef<ReturnType<typeof Regions.create> | null>(null);
  const windowRef = useRef({ from: 0, to: 0 });
  const gridRef = useRef(grid);
  gridRef.current = grid;
  const seekRef = useRef(onSeek);
  seekRef.current = onSeek;
  const cueClickRef = useRef(onCueClick);
  cueClickRef.current = onCueClick;

  const drawBeats = useCallback(() => {
    const c = canvasRef.current;
    const g = gridRef.current;
    const { from, to } = windowRef.current;
    if (!c) return;
    const ctx = c.getContext("2d");
    if (!ctx) return; // jsdom: nessun canvas, nessun disegno
    const w = c.clientWidth;
    const h = c.clientHeight;
    const dpr = window.devicePixelRatio || 1;
    c.width = Math.round(w * dpr);
    c.height = Math.round(h * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    if (!g || to <= from) return;
    ctx.strokeStyle = tokens().beat;
    ctx.lineWidth = 1;
    for (const t of beatTimes(g, from, to)) {
      const x = Math.round(((t - from) / (to - from)) * w) + 0.5;
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x, h);
      ctx.stroke();
    }
  }, []);

  // Montaggio: una sola istanza per elemento+picchi. Si rimonta solo quando
  // cambiano quelli; zoom, griglia e cue passano dagli effetti sotto.
  const peaksKey = waveform?.peaks ?? null;
  useEffect(() => {
    if (!audioEl || !waveform || !peaksKey || !mainRef.current || !miniRef.current) return;
    const col = tokens();
    const regions = Regions.create();
    const ws = WaveSurfer.create({
      container: mainRef.current,
      media: audioEl,
      url: audioUrl,
      peaks: [decodePeaks(peaksKey)],
      duration: waveform.duration_seconds,
      minPxPerSec,
      autoCenter: true,
      autoScroll: true,
      hideScrollbar: true,
      height: 60,
      waveColor: col.wave,
      progressColor: col.progress,
      cursorColor: col.progress,
      cursorWidth: 2,
      plugins: [
        regions,
        Minimap.create({ container: miniRef.current, height: 16, waveColor: col.mini, progressColor: col.progress }),
      ],
    });
    wsRef.current = ws;
    regionsRef.current = regions;
    ws.on("scroll", (from: number, to: number) => { windowRef.current = { from, to }; drawBeats(); });
    ws.on("zoom", () => drawBeats());
    ws.on("ready", () => drawBeats());
    ws.on("interaction", (t: number) => seekRef.current(t));
    regions.on("region-clicked", (region, e) => {
      e.stopPropagation();
      cueClickRef.current(Number(region.id));
    });
    return () => {
      ws.destroy();
      wsRef.current = null;
      regionsRef.current = null;
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps -- minPxPerSec e cues hanno il loro effetto; rimontare qui li duplicherebbe
  }, [audioEl, peaksKey, audioUrl, drawBeats]);

  useEffect(() => { wsRef.current?.zoom(minPxPerSec); }, [minPxPerSec]);
  useEffect(() => { drawBeats(); }, [grid, drawBeats]);
  useEffect(() => {
    const r = regionsRef.current;
    if (!r) return;
    r.clearRegions();
    const col = tokens().cue;
    cues.forEach((c, i) => r.addRegion({
      id: String(c.id), start: c.position_seconds, color: col, drag: false, resize: false, content: String(i + 1),
    }));
  }, [cues, peaksKey]);

  return (
    <div data-testid={`deck-waveform-${side}`} className="relative">
      <div ref={miniRef} className="mb-0.5 h-4 bg-surface" />
      <div className="relative h-[60px] bg-surface">
        <div ref={mainRef} className="absolute inset-0" />
        <canvas ref={canvasRef} data-testid={`deck-grid-canvas-${side}`}
          className="pointer-events-none absolute inset-0 h-full w-full" />
      </div>
    </div>
  );
}
```

Verifica nel browser (Task 13, passo di prova a mano) due punti che il test non copre: che wavesurfer emetta `scroll` al primo render con `peaks`+`duration` (se no, in `ready` calcola la finestra da `ws.getScroll() / minPxPerSec` e dalla larghezza del contenitore) e che con `media` e `url` uguale al `src` gia' impostato l'elemento non ricarichi.

- [ ] **Step 4: Esegui, deve passare; lint**

Run: `cd frontend && npx vitest run tests/deck-waveform.test.tsx && npm run lint`
Expected: 4 passed; lint pulito

- [ ] **Step 5: Commit**

```bash
git add frontend/components/deck/deck-waveform.tsx frontend/tests/deck-waveform.test.tsx
git commit -m "feat(deck): waveform con wavesurfer, cue e canvas dei battiti"
```

---

### Task 13: `Deck` e `DeckDock` — i due deck nel telaio fisso

**Files:**
- Create: `frontend/components/deck/deck.tsx`
- Create: `frontend/components/deck/deck-dock.tsx`
- Test: `frontend/tests/deck-dock.test.tsx`

**Interfaces:**
- Produces: `DeckDock` con props `{ from: ManualRow; to: ManualRow; onClose(): void; onUsePlayBpm(row: ManualRow, bpm: number): void }` (entrambe le righe hanno `track` non nullo con `has_local_file`); `Deck` con `{ view: DeckView; actions: DeckActions; audioEl; audioUrl; minPxPerSec; hideControls }`; tipi esportati `DeckView`, `DeckActions`. Testid: `deck-dock`, `deck-A`/`deck-B`, `deck-audio-A/B`, `deck-status-A/B`, `deck-play-A/B`, `deck-sync-A/B`, `deck-pitch-A/B`, `deck-range-A/B`, `deck-use-playbpm-A/B`, `deck-phase`, `deck-realign`, `deck-hide-controls`, `deck-close`, `deck-zoom-in`, `deck-zoom-out`.
- Consumes: `DeckEngine`, `grid.ts`, `getDeck`/`prepareDeck`/`createCue`/`updateCue`/`deleteCue`, `trackAudioUrl`, `CueStrip`, `DeckWaveform`, `KeyBadge`, `TrackCover`, `t.deck.*`.
- Chiave `localStorage`: `cratory.deck.hideControls` = `"1"` per nascosti.

- [ ] **Step 1: Test**

```tsx
// frontend/tests/deck-dock.test.tsx
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({
  getDeck: vi.fn(),
  prepareDeck: vi.fn(),
  createCue: vi.fn(),
  updateCue: vi.fn(),
  deleteCue: vi.fn(),
}));
vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<object>()),
  ...api,
  trackAudioUrl: (id: number) => `/api/tracks/${id}/audio`,
  trackCoverSrc: () => null,
}));

/* Motore finto: registra le chiamate e simula posizione/durata per deck. */
const engine = vi.hoisted(() => {
  const calls: Array<[string, ...unknown[]]> = [];
  const pos: Record<string, number> = { A: 0, B: 0 };
  class FakeEngine {
    static last: FakeEngine | null = null;
    constructor() { FakeEngine.last = this; }
    load(side: string, url: string) { calls.push(["load", side, url]); }
    async play(side: string) { calls.push(["play", side]); }
    pause(side: string) { calls.push(["pause", side]); }
    seek(side: string, t: number) { calls.push(["seek", side, t]); pos[side] = Math.max(0, t); }
    position(side: string) { return pos[side]; }
    duration() { return 300; }
    setRate(side: string, rate: number, keyLock: boolean) { calls.push(["setRate", side, rate, keyLock]); return true; }
    setVolume(side: string, v: number) { calls.push(["setVolume", side, v]); }
    setLowCut(side: string, on: boolean) { calls.push(["setLowCut", side, on]); }
    dispose() { calls.push(["dispose"]); }
  }
  return { calls, pos, FakeEngine };
});
vi.mock("@/lib/deck/engine", () => ({ DeckEngine: engine.FakeEngine, SIDES: ["A", "B"], setPreservesPitch: () => true }));
vi.mock("@/components/deck/deck-waveform", () => ({
  DeckWaveform: ({ side, waveform }: { side: string; waveform: unknown }) => (
    <div data-testid={`deck-waveform-${side}`} data-has-peaks={waveform ? "1" : "0"} />
  ),
}));

import { DeckDock } from "@/components/deck/deck-dock";
import { ApiError } from "@/lib/api";
import type { ManualRow } from "@/lib/api";

const track = (id: number, extra: Record<string, unknown> = {}) => ({
  id, spotify_id: null, soundcloud_id: null, source_type: "spotify", platform: "spotify",
  title: `Traccia ${id}`, artist: "Artista", album: null, genre: null, year: null,
  duration_seconds: 300, bpm: id === 1 ? 126 : 124, camelot_key: "8A", energy: null,
  label: null, status: "imported", url: null, isrc: null, playlists: [], added_at: null,
  playlist_added_at: null, spotify_url: null, album_art_url: null, has_local_file: true,
  local_path: "/x", local_format: "mp3", local_bitrate: 320, primary_file_id: null,
  genre_from_file: false, album_from_file: false, label_from_file: false, year_from_file: false,
  archived: false, rating: null, last_download_outcome: null, last_download_reason: null,
  last_download_path: null, ...extra,
});
const row = (id: number, trackId: number, play_bpm: number | null = null): ManualRow => ({
  id, block_id: 1, position: id, slot_kind: "track", track: track(trackId) as ManualRow["track"],
  note: null, play_bpm, planned_seconds: null, alternatives: [],
});

const deckData = (id: number, extra: Record<string, unknown> = {}) => ({
  track: { id, title: `Traccia ${id}`, artist: "Artista", bpm: id === 1 ? 126 : 124, camelot_key: "8A",
           duration_seconds: 300, album_art_url: null, has_local_file: true },
  grid: null, grid_error: null, waveform: null, cues: [], ...extra,
});
const WAVE = { samples_per_second: 100, duration_seconds: 300, peaks: btoa("abc") };
const GRID = { first_beat: 0.37, bpm: 128 };

function mount(extra: Partial<Parameters<typeof DeckDock>[0]> = {}) {
  const props = { from: row(10, 1), to: row(11, 2), onClose: vi.fn(), onUsePlayBpm: vi.fn(), ...extra };
  render(<DeckDock {...props} />);
  return props;
}

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  engine.calls.length = 0;
  engine.pos.A = 0; engine.pos.B = 0;
  localStorage.clear();
  api.getDeck.mockImplementation(async (id: number) => deckData(id, { waveform: WAVE, grid: GRID }));
  api.prepareDeck.mockResolvedValue({ waveform: "ready", grid: "ready", reason: null });
  api.createCue.mockImplementation(async (_id: number, b: { position_seconds: number; name: string | null }) =>
    ({ id: 99, position_seconds: b.position_seconds, name: b.name ?? null }));
  api.updateCue.mockResolvedValue({ id: 99, position_seconds: 1, name: "x" });
  api.deleteCue.mockResolvedValue(undefined);
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
  // niente mockReset in beforeEach: i vi.fn() che devono rifiutare vanno ridefiniti caso per caso
});

describe("DeckDock", () => {
  it("due deck dalle righe, audio caricato, rate iniziale da «la suono a»", async () => {
    mount({ from: row(10, 1, 128.52) }); // 128.52 / 126 = 1.02
    expect(within(screen.getByTestId("deck-A")).getByText("Traccia 1")).toBeTruthy();
    expect(within(screen.getByTestId("deck-B")).getByText("Traccia 2")).toBeTruthy();
    expect(engine.calls).toContainEqual(["load", "A", "/api/tracks/1/audio"]);
    expect(engine.calls).toContainEqual(["load", "B", "/api/tracks/2/audio"]);
    const rateA = engine.calls.find((c) => c[0] === "setRate" && c[1] === "A");
    expect(rateA?.[2]).toBeCloseTo(1.02, 6);
    expect(rateA?.[3]).toBe(true); // master tempo acceso
    await waitFor(() => expect(api.getDeck).toHaveBeenCalledWith(1));
    await waitFor(() => expect(screen.getByTestId("deck-waveform-A").getAttribute("data-has-peaks")).toBe("1"));
    expect(screen.queryByTestId("deck-status-A")).toBeNull(); // griglia e waveform pronte: niente testo di stato
  });

  it("stati di attesa: waveform e griglia in calcolo, poi pronte", async () => {
    let n = 0;
    api.getDeck.mockImplementation(async (id: number) => (n++ < 2 ? deckData(id) : deckData(id, { waveform: WAVE, grid: GRID })));
    api.prepareDeck.mockResolvedValue({ waveform: "ready", grid: "queued", reason: null });
    mount();
    await waitFor(() => expect(screen.getByTestId("deck-status-A").textContent).toContain("waveform in calcolo"));
    expect(screen.getByTestId("deck-status-A").textContent).toContain("griglia in calcolo");
    await act(async () => { await vi.advanceTimersByTimeAsync(2100); });
    await waitFor(() => expect(screen.queryByTestId("deck-status-A")).toBeNull());
  });

  it("job occupato: attende e ritenta", async () => {
    api.getDeck.mockImplementation(async (id: number) => deckData(id));
    api.prepareDeck.mockRejectedValue(new ApiError(409, { code: "analysis_busy", message: "busy" }));
    mount();
    await waitFor(() => expect(screen.getByTestId("deck-status-A").textContent).toContain("analisi di massa in corso, attendo"));
    const prima = api.prepareDeck.mock.calls.length;
    await act(async () => { await vi.advanceTimersByTimeAsync(3100); });
    expect(api.prepareDeck.mock.calls.length).toBeGreaterThan(prima);
  });

  it("motore assente: griglia non disponibile ma la waveform arriva", async () => {
    let n = 0;
    api.getDeck.mockImplementation(async (id: number) => (n++ < 2 ? deckData(id) : deckData(id, { waveform: WAVE })));
    api.prepareDeck.mockResolvedValue({ waveform: "ready", grid: "unavailable", reason: "analysis_engine_unavailable" });
    mount();
    await waitFor(() => expect(screen.getByTestId("deck-status-A").textContent)
      .toContain("griglia non disponibile: motore di analisi assente"));
    await act(async () => { await vi.advanceTimersByTimeAsync(2100); });
    await waitFor(() => expect(screen.getByTestId("deck-waveform-A").getAttribute("data-has-peaks")).toBe("1"));
    // Senza griglia il sync e' solo di tempo: lo dice il titolo del pulsante.
    expect(screen.getByTestId("deck-sync-B").getAttribute("title")).toBe("Senza griglia si sincronizza solo il tempo, non la fase");
  });

  it("griglia rifiutata dal backend", async () => {
    api.getDeck.mockImplementation(async (id: number) => deckData(id, { waveform: WAVE, grid_error: "uncertain" }));
    mount();
    await waitFor(() => expect(screen.getByTestId("deck-status-A").textContent).toContain("griglia non disponibile: griglia incerta"));
    expect(api.prepareDeck).not.toHaveBeenCalled(); // niente da chiedere: ha gia' tutto
  });

  it("ffmpeg assente: waveform non disponibile, il resto funziona", async () => {
    api.getDeck.mockImplementation(async (id: number) => deckData(id));
    api.prepareDeck.mockRejectedValue(new ApiError(503, { code: "ffmpeg_unavailable", message: "no ffmpeg" }));
    mount();
    await waitFor(() => expect(screen.getByTestId("deck-status-A").textContent).toContain("waveform non disponibile: ffmpeg assente"));
    fireEvent.click(screen.getByTestId("deck-play-A"));
    await waitFor(() => expect(engine.calls).toContainEqual(["play", "A"]));
  });

  it("waveform con zero picchi vale come assente (Review Focus 5)", async () => {
    api.getDeck.mockImplementation(async (id: number) => deckData(id, { waveform: { ...WAVE, peaks: "" }, grid: GRID }));
    mount();
    await waitFor(() => expect(screen.getByTestId("deck-status-A").textContent).toContain("waveform non disponibile: decodifica fallita"));
    expect(screen.getByTestId("deck-waveform-A").getAttribute("data-has-peaks")).toBe("0");
  });

  it("metti cue: posizione corrente, arrotondata al battito se «al battito» e' acceso", async () => {
    mount();
    await waitFor(() => expect(api.getDeck).toHaveBeenCalledTimes(2));
    engine.pos.A = 12.3;
    fireEvent.click(screen.getByTestId("deck-cue-add-A"));
    await waitFor(() => expect(api.createCue).toHaveBeenCalled());
    // (12.3 - 0.37) / 0.46875 = 25.45 → 25 → 0.37 + 25 * 0.46875 = 12.08875
    expect(api.createCue.mock.calls[0][0]).toBe(1);
    expect(api.createCue.mock.calls[0][1].position_seconds).toBeCloseTo(12.08875, 6);
    fireEvent.click(within(screen.getByTestId("deck-A")).getByRole("button", { name: "al battito" }));
    fireEvent.click(screen.getByTestId("deck-cue-add-A"));
    await waitFor(() => expect(api.createCue).toHaveBeenCalledTimes(2));
    expect(api.createCue.mock.calls[1][1].position_seconds).toBeCloseTo(12.3, 6);
  });

  it("stessa traccia sui due deck: una cue aggiunta su A compare su B (Review Focus 2)", async () => {
    let cues: Array<{ id: number; position_seconds: number; name: string | null }> = [];
    api.getDeck.mockImplementation(async (id: number) => deckData(id, { waveform: WAVE, grid: GRID, cues }));
    api.createCue.mockImplementation(async (_id: number, b: { position_seconds: number }) => {
      cues = [{ id: 5, position_seconds: b.position_seconds, name: null }];
      return cues[0];
    });
    mount({ from: row(10, 1), to: row(11, 1) });
    await waitFor(() => expect(api.getDeck).toHaveBeenCalledTimes(2));
    fireEvent.click(screen.getByTestId("deck-cue-add-A"));
    await waitFor(() => expect(within(screen.getByTestId("deck-B")).getByRole("button", { name: "1" })).toBeTruthy());
  });

  it("salto a una cue, rinomina ed elimina passano dall'API", async () => {
    api.getDeck.mockImplementation(async (id: number) => deckData(id, {
      waveform: WAVE, grid: GRID, cues: [{ id: 7, position_seconds: 30, name: "drop" }],
    }));
    mount();
    const a = () => within(screen.getByTestId("deck-A"));
    await waitFor(() => expect(a().getByRole("button", { name: "1 drop" })).toBeTruthy());
    fireEvent.click(a().getByRole("button", { name: "1 drop" }));
    expect(engine.calls).toContainEqual(["seek", "A", 30]);
    fireEvent.click(a().getByTitle("Rinomina la cue"));
    const input = a().getByPlaceholderText("nome");
    fireEvent.change(input, { target: { value: "break" } });
    fireEvent.keyDown(input, { key: "Enter" });
    await waitFor(() => expect(api.updateCue).toHaveBeenCalledWith(1, 7, { name: "break" }));
    fireEvent.click(a().getByTitle("Elimina la cue"));
    await waitFor(() => expect(api.deleteCue).toHaveBeenCalledWith(1, 7));
  });

  it("sync su A porta B al tempo di A (BPM di griglia) e allinea la fase; poi «la suono a»", async () => {
    api.getDeck.mockImplementation(async (id: number) => deckData(id, {
      waveform: WAVE, grid: id === 1 ? { first_beat: 0.0, bpm: 128 } : { first_beat: 0.0, bpm: 124 },
    }));
    const p = mount();
    await waitFor(() => expect(api.getDeck).toHaveBeenCalledTimes(2));
    engine.pos.A = 10 * (60 / 128);          // A esattamente su un battito
    engine.pos.B = 10 * (60 / 124) + 0.1;    // B un decimo di secondo oltre un battito
    fireEvent.click(screen.getByTestId("deck-sync-B"));
    const rate = engine.calls.filter((c) => c[0] === "setRate" && c[1] === "B").at(-1);
    expect(rate?.[2]).toBeCloseTo(128 / 124, 9);
    const seek = engine.calls.filter((c) => c[0] === "seek" && c[1] === "B").at(-1);
    expect(seek?.[2]).toBeCloseTo(10 * (60 / 124), 6); // torna sul battito
    expect(screen.getByTestId("deck-phase").textContent).toMatch(/ms/);
    fireEvent.click(screen.getByTestId("deck-use-playbpm-B"));
    expect(p.onUsePlayBpm).toHaveBeenCalledWith(expect.objectContaining({ id: 11 }), 128); // 124 * 128/124
  });

  it("cambio corsa da ±16 a ±8 riporta il rate a 1,08 (Review Focus 4)", async () => {
    mount();
    await waitFor(() => expect(api.getDeck).toHaveBeenCalledTimes(2));
    fireEvent.click(screen.getByTestId("deck-range-A")); // → ±16
    fireEvent.change(screen.getByTestId("deck-pitch-A"), { target: { value: "1.12" } });
    expect(engine.calls.filter((c) => c[0] === "setRate" && c[1] === "A").at(-1)?.[2]).toBeCloseTo(1.12);
    fireEvent.click(screen.getByTestId("deck-range-A")); // → ±8
    expect(engine.calls.filter((c) => c[0] === "setRate" && c[1] === "A").at(-1)?.[2]).toBeCloseTo(1.08);
  });

  it("nascondi pitch e volume: via i regolatori, scelta ricordata", async () => {
    mount();
    expect(screen.getByTestId("deck-pitch-A")).toBeTruthy();
    fireEvent.click(screen.getByTestId("deck-hide-controls"));
    expect(screen.queryByTestId("deck-pitch-A")).toBeNull();
    expect(localStorage.getItem("cratory.deck.hideControls")).toBe("1");
    expect(screen.getByTestId("deck-hide-controls").textContent).toContain("Mostra pitch e volume");
  });

  it("chiusura: dispose, altezza azzerata, onClose", async () => {
    const p = mount();
    expect(document.documentElement.style.getPropertyValue("--player-bar-height")).not.toBe("");
    fireEvent.click(screen.getByTestId("deck-close"));
    expect(p.onClose).toHaveBeenCalled();
    cleanup();
    expect(engine.calls).toContainEqual(["dispose"]);
    expect(document.documentElement.style.getPropertyValue("--player-bar-height")).toBe("0px");
  });

  it("errore dell'elemento audio: messaggio sul deck, l'altro resta", async () => {
    mount();
    fireEvent.error(screen.getByTestId("deck-audio-A"));
    expect(within(screen.getByTestId("deck-A")).getByText("Formato non riproducibile nel browser")).toBeTruthy();
    expect(within(screen.getByTestId("deck-B")).queryByText("Formato non riproducibile nel browser")).toBeNull();
  });
});
```

Controlla la firma di `ApiError` in `lib/api/client.ts` prima di scrivere il test: se il costruttore prende `(status, detail)` in un altro ordine, adegua le due righe che lo costruiscono.

- [ ] **Step 2: Esegui, deve fallire**

Run: `cd frontend && npx vitest run tests/deck-dock.test.tsx`
Expected: FAIL (moduli mancanti)

- [ ] **Step 3: `Deck`, il singolo deck**

```tsx
// frontend/components/deck/deck.tsx
"use client";

import { ArrowLeft, ArrowRight, Pause, Play } from "lucide-react";

import type { DeckData, ManualRow, TrackCue } from "@/lib/api";
import { CueStrip } from "@/components/deck/cue-strip";
import { DeckWaveform } from "@/components/deck/deck-waveform";
import { KeyBadge } from "@/components/key-badge";
import { TrackCover } from "@/components/track-cover";
import type { DeckSide } from "@/lib/deck/engine";
import { bpmDisagreement, effectiveBpm, pitchPercent, toGrid, type PitchRange } from "@/lib/deck/grid";
import { useT } from "@/lib/i18n";

export type DeckView = {
  side: DeckSide;
  row: ManualRow;
  data: DeckData | null;
  waveformStatus: "computing" | "ready" | "unavailable";
  waveformReason: string | null;
  gridStatus: "computing" | "busy" | "ready" | "unavailable";
  gridReason: string | null;
  rate: number;
  range: PitchRange;
  keyLock: boolean;
  keyLockSupported: boolean;
  volume: number;
  lowCut: boolean;
  playing: boolean;
  position: number;
  error: "format" | "missing" | null;
  snapToBeat: boolean;
};

export type DeckActions = {
  onPlayPause: () => void;
  onSeek: (t: number) => void;
  onRate: (rate: number) => void;
  onToggleRange: () => void;
  onKeyLock: (on: boolean) => void;
  onVolume: (v: number) => void;
  onLowCut: (on: boolean) => void;
  onSync: () => void;
  onBeatJump: (dir: 1 | -1) => void;
  onNudge: (dir: 1 | -1) => void;
  onAddCue: () => void;
  onJumpCue: (cue: TrackCue) => void;
  onRenameCue: (cue: TrackCue, name: string | null) => void;
  onDeleteCue: (cue: TrackCue) => void;
  onToggleSnap: () => void;
  onUsePlayBpm: () => void;
};

function fmtTime(s: number): string {
  if (!Number.isFinite(s) || s < 0) return "0:00";
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${m}:${String(sec).padStart(2, "0")}`;
}

const btn = "border border-border px-2 py-0.5 text-[11px] text-fg hover:bg-elevated disabled:opacity-40 focus-visible:outline focus-visible:outline-1 focus-visible:outline-fg";
const tog = "rounded-full border border-border px-2 py-0.5 text-[11px] text-fg aria-pressed:border-fg-strong aria-pressed:text-fg-strong disabled:opacity-40";

/** Un deck: a sinistra identita', trasporto, BPM e regolatori; a destra la
 *  waveform, le cue e i salti di battito. Tutto lo stato arriva dal dock. */
export function Deck({ view, actions, audioEl, audioUrl, minPxPerSec, hideControls }: {
  view: DeckView; actions: DeckActions; audioEl: HTMLAudioElement | null; audioUrl: string;
  minPxPerSec: number; hideControls: boolean;
}) {
  const t = useT();
  const { side, row, data } = view;
  const tr = row.track!;
  const other: DeckSide = side === "A" ? "B" : "A";
  const grid = toGrid(data?.grid);
  const nominal = data?.track.bpm ?? tr.bpm;
  const bpmNow = effectiveBpm(nominal, view.rate);
  const duration = data?.waveform?.duration_seconds ?? tr.duration_seconds ?? 0;
  const reason = (code: string | null) => (code && t.deck.reasons[code]) || t.deck.reasons.other;
  const disagree = grid && nominal ? bpmDisagreement(grid.bpm, nominal) > 0.01 : false;

  const status: string[] = [];
  if (view.waveformStatus === "computing") status.push(t.deck.waveformComputing);
  if (view.waveformStatus === "unavailable") status.push(t.deck.waveformUnavailable(reason(view.waveformReason)));
  if (view.gridStatus === "computing") status.push(t.deck.gridComputing);
  if (view.gridStatus === "busy") status.push(t.deck.analysisBusy);
  if (view.gridStatus === "unavailable") status.push(t.deck.gridUnavailable(reason(view.gridReason)));

  return (
    <div data-testid={`deck-${side}`} className="grid gap-3 lg:grid-cols-[270px_minmax(0,1fr)]">
      {/* Blocco a sinistra */}
      <div className="min-w-0 space-y-1.5">
        <div className="flex items-center gap-2">
          <TrackCover track={{ id: tr.id, album_art_url: tr.album_art_url, has_local_file: true }} className="h-8 w-8" iconSize={14} />
          <div className="min-w-0">
            <div className="flex items-baseline gap-2">
              <span className="text-[10px] uppercase tracking-wider text-faint">{t.deck.title(side)}</span>
              <span className="truncate text-sm text-fg-strong">{tr.title}</span>
            </div>
            <div className="flex items-center gap-2 text-xs text-muted">
              <span className="truncate">{tr.artist}</span>
              {tr.camelot_key && <KeyBadge camelot={tr.camelot_key} className="text-[10px]" />}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button type="button" data-testid={`deck-play-${side}`} onClick={actions.onPlayPause}
            aria-label={view.playing ? t.deck.pause : t.deck.play}
            className="grid h-8 w-8 shrink-0 place-items-center border border-border-strong text-fg-strong hover:bg-elevated">
            {view.playing ? <Pause size={15} /> : <Play size={15} />}
          </button>
          <span className="tnum text-xs text-fg">{fmtTime(view.position)}</span>
          <span className="tnum text-xs text-muted">−{fmtTime(Math.max(0, duration - view.position))}</span>
          <span className="ml-auto tnum text-base font-semibold text-fg-strong">{bpmNow ?? "—"}</span>
          <span className="tnum text-xs text-muted">{view.rate === 1 ? "0,0" : pitchPercent(view.rate).toLocaleString("it-IT", { signDisplay: "always" })} %</span>
          <button type="button" aria-pressed={view.keyLock} disabled={!view.keyLockSupported}
            title={view.keyLockSupported ? t.deck.masterTempo : t.deck.noMasterTempo}
            className={tog} onClick={() => actions.onKeyLock(!view.keyLock)}>MT</button>
        </div>
        {row.play_bpm != null && <div className="text-[11px] text-muted">{t.deck.playBpm(String(row.play_bpm))}</div>}
        {disagree && grid && nominal && (
          <div className="text-[11px] text-danger">{t.deck.gridDisagree(grid.bpm.toFixed(1), String(nominal))}</div>
        )}
        {view.error && (
          <div className="text-xs text-muted">{view.error === "format" ? t.deck.unsupportedFormat : t.deck.fileMissing}</div>
        )}
        {!hideControls && (
          <>
            <div className="flex items-center gap-2">
              <span className="w-8 text-[10px] uppercase tracking-wider text-faint">{t.deck.pitch}</span>
              <input type="range" data-testid={`deck-pitch-${side}`} aria-label={t.deck.pitch}
                min={1 - view.range / 100} max={1 + view.range / 100} step={0.0005} value={view.rate}
                onChange={(e) => actions.onRate(Number(e.target.value))}
                onDoubleClick={() => actions.onRate(1)} title={t.deck.resetPitch}
                className="seek-flat min-w-0 flex-1" />
              <button type="button" data-testid={`deck-range-${side}`} className={tog} onClick={actions.onToggleRange}>
                {t.deck.pitchRange(view.range)}
              </button>
            </div>
            <div className="flex items-center gap-2">
              <span className="w-8 text-[10px] uppercase tracking-wider text-faint">{t.deck.volume}</span>
              <input type="range" aria-label={t.deck.volume} min={0} max={1} step={0.01} value={view.volume}
                onChange={(e) => actions.onVolume(Number(e.target.value))} className="seek-flat min-w-0 flex-1" />
              <button type="button" aria-pressed={view.lowCut} title={t.deck.lowCutTitle} className={tog}
                onClick={() => actions.onLowCut(!view.lowCut)}>{t.deck.lowCut}</button>
              <button type="button" data-testid={`deck-sync-${side}`} className={btn} onClick={actions.onSync}
                title={grid ? undefined : t.deck.syncRateOnly}>{t.deck.sync(other)}</button>
            </div>
            <button type="button" data-testid={`deck-use-playbpm-${side}`} className={btn}
              disabled={bpmNow == null} onClick={actions.onUsePlayBpm}>{t.deck.usePlayBpm}</button>
          </>
        )}
      </div>

      {/* Colonna waveform */}
      <div className="min-w-0 space-y-1.5">
        <DeckWaveform side={side} audioEl={audioEl} audioUrl={audioUrl}
          waveform={view.waveformStatus === "ready" ? data?.waveform ?? null : null}
          grid={grid} cues={data?.cues ?? []} minPxPerSec={minPxPerSec}
          onSeek={actions.onSeek} onCueClick={(id) => { const c = data?.cues.find((x) => x.id === id); if (c) actions.onJumpCue(c); }} />
        {status.length > 0 && (
          <div data-testid={`deck-status-${side}`} className="text-[11px] text-muted">{status.join(" · ")}</div>
        )}
        <div className="flex flex-wrap items-center gap-2">
          <CueStrip side={side} cues={data?.cues ?? []} snapToBeat={view.snapToBeat} canSnap={!!grid}
            onToggleSnap={actions.onToggleSnap} onAdd={actions.onAddCue} onJump={actions.onJumpCue}
            onRename={actions.onRenameCue} onDelete={actions.onDeleteCue} />
          <span className="flex-1" />
          <button type="button" className={btn} title={t.deck.beatBack} onClick={() => actions.onBeatJump(-1)}><ArrowLeft size={12} /></button>
          <button type="button" className={btn} title={t.deck.beatForward} onClick={() => actions.onBeatJump(1)}><ArrowRight size={12} /></button>
          <button type="button" className={btn} onClick={() => actions.onNudge(-1)}>{t.deck.nudgeBack}</button>
          <button type="button" className={btn} onClick={() => actions.onNudge(1)}>{t.deck.nudgeForward}</button>
        </div>
      </div>
    </div>
  );
}
```

`seek-flat` non esiste ancora: aggiungi in `app/globals.css`, accanto a `.seek`, una variante in linea (altezza 3 px, pollice 10 px, stessi colori di `.seek`) senza il posizionamento assoluto. Se preferisci riusare `.seek`, togli da li' `absolute inset-x-0 top-0 -translate-y-1/2`, che il trasporto passa via className.

- [ ] **Step 4: `DeckDock`, il telaio e lo stato**

```tsx
// frontend/components/deck/deck-dock.tsx
"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ChevronDown, ChevronUp, Minus, Plus, X } from "lucide-react";

import {
  ApiError, createCue, deleteCue, getDeck, prepareDeck, trackAudioUrl, updateCue,
  type DeckData, type ManualRow, type TrackCue,
} from "@/lib/api";
import { Deck, type DeckActions, type DeckView } from "@/components/deck/deck";
import { DeckEngine, SIDES, type DeckSide } from "@/lib/deck/engine";
import {
  DEFAULT_ZOOM_INDEX, ZOOM_LEVELS, alignShift, beatJumpSeconds, clampRate, effectiveBpm,
  nearestBeat, phaseOffsetMs, syncRate, toGrid, type PitchRange,
} from "@/lib/deck/grid";
import { useT } from "@/lib/i18n";

const HIDE_KEY = "cratory.deck.hideControls";
const POLL_MS = 2000;
const BUSY_MS = 3000;
const MAX_POLLS = 60;
const NUDGE_S = 0.01;

type Props = {
  from: ManualRow;
  to: ManualRow;
  onClose: () => void;
  onUsePlayBpm: (row: ManualRow, bpm: number) => void;
};

function readHide(): boolean {
  try { return localStorage.getItem(HIDE_KEY) === "1"; } catch { return false; }
}

function initialView(side: DeckSide, row: ManualRow): DeckView {
  const nominal = row.track?.bpm ?? null;
  const wanted = row.play_bpm && nominal ? row.play_bpm / nominal : 1;
  const range: PitchRange = Math.abs(wanted - 1) > 0.08 ? 16 : 8;
  return {
    side, row, data: null,
    waveformStatus: "computing", waveformReason: null,
    gridStatus: "computing", gridReason: null,
    rate: clampRate(wanted, range), range, keyLock: true, keyLockSupported: true,
    volume: 1, lowCut: false, playing: false, position: 0, error: null, snapToBeat: true,
  };
}

const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

/** Il pannello fisso con i due deck. Vive sotto il banco, nello stesso telaio
 *  del player docked (stessi confini di colonna, stessa variabile di altezza).
 *  Possiede il motore audio e lo stato dei deck; la pagina decide quando
 *  montarlo e con quali righe. */
export function DeckDock({ from, to, onClose, onUsePlayBpm }: Props) {
  const t = useT();
  const barRef = useRef<HTMLDivElement>(null);
  const audioA = useRef<HTMLAudioElement>(null);
  const audioB = useRef<HTMLAudioElement>(null);
  const engineRef = useRef<DeckEngine | null>(null);
  const genRef = useRef(0);
  const [views, setViews] = useState<Record<DeckSide, DeckView>>({ A: initialView("A", from), B: initialView("B", to) });
  const viewsRef = useRef(views);
  viewsRef.current = views;
  const [hide, setHide] = useState(readHide);
  const [zoomIdx, setZoomIdx] = useState(DEFAULT_ZOOM_INDEX);
  const [slave, setSlave] = useState<DeckSide | null>(null);
  const [phaseMs, setPhaseMs] = useState<number | null>(null);
  const [mounted, setMounted] = useState(false);

  const rowOf = useCallback((side: DeckSide) => (side === "A" ? from : to), [from, to]);
  const trackIdOf = useCallback((side: DeckSide) => rowOf(side).track!.id, [rowOf]);
  const other = (side: DeckSide): DeckSide => (side === "A" ? "B" : "A");
  const update = useCallback((side: DeckSide, patch: Partial<DeckView>) =>
    setViews((v) => ({ ...v, [side]: { ...v[side], ...patch } })), []);

  // Altezza pubblicata come fa il player docked: il banco si tiene il fondo libero.
  useEffect(() => {
    document.documentElement.style.setProperty("--player-bar-height", `${barRef.current?.offsetHeight ?? 0}px`);
  });
  useEffect(() => () => { document.documentElement.style.setProperty("--player-bar-height", "0px"); }, []);

  // Il motore nasce con gli elementi gia' nel DOM e muore col dock.
  useEffect(() => {
    if (!audioA.current || !audioB.current) return;
    const eng = new DeckEngine({ A: audioA.current, B: audioB.current });
    engineRef.current = eng;
    setMounted(true);
    return () => { eng.dispose(); engineRef.current = null; };
  }, []);

  // Eventi reali degli elementi: posizione, play/pausa, errori.
  useEffect(() => {
    const offs: Array<() => void> = [];
    for (const side of SIDES) {
      const el = side === "A" ? audioA.current : audioB.current;
      if (!el) continue;
      const on = (ev: string, fn: () => void) => { el.addEventListener(ev, fn); offs.push(() => el.removeEventListener(ev, fn)); };
      on("play", () => update(side, { playing: true }));
      on("pause", () => update(side, { playing: false }));
      on("ended", () => update(side, { playing: false }));
      on("timeupdate", () => update(side, { position: el.currentTime }));
      on("error", () => update(side, { error: "format", playing: false }));
    }
    return () => offs.forEach((f) => f());
  }, [update]);

  // Caricamento e polling per deck, invalidato dal contatore come fa il player.
  const idA = trackIdOf("A");
  const idB = trackIdOf("B");
  useEffect(() => {
    const eng = engineRef.current;
    if (!eng) return;
    const gen = ++genRef.current;
    const gridDone: Record<DeckSide, boolean> = { A: false, B: false };

    const tick = async (side: DeckSide, delay: number, polls: number) => {
      await sleep(delay);
      if (gen !== genRef.current) return;
      const tid = trackIdOf(side);
      let data: DeckData;
      try {
        data = await getDeck(tid);
      } catch {
        if (gen === genRef.current) update(side, { error: "missing" });
        return;
      }
      if (gen !== genRef.current) return;
      const emptyPeaks = !!data.waveform && data.waveform.peaks.length === 0;
      const haveWave = !!data.waveform && !emptyPeaks;
      update(side, {
        data,
        waveformStatus: haveWave ? "ready" : emptyPeaks ? "unavailable" : "computing",
        waveformReason: emptyPeaks ? "waveform_failed" : null,
        gridStatus: data.grid ? "ready" : data.grid_error || gridDone[side] ? "unavailable" : "computing",
        gridReason: data.grid_error ?? (gridDone[side] ? viewsRef.current[side].gridReason : null),
      });
      const needWave = !data.waveform;
      const needGrid = !data.grid && !data.grid_error && !gridDone[side];
      if (!needWave && !needGrid) return;
      if (polls >= MAX_POLLS) {
        update(side, { gridStatus: "unavailable", gridReason: "timeout" });
        return;
      }
      try {
        const prep = await prepareDeck(tid);
        if (gen !== genRef.current) return;
        if (prep.grid === "unavailable") {
          gridDone[side] = true;
          update(side, { gridStatus: "unavailable", gridReason: prep.reason });
        }
        void tick(side, POLL_MS, polls + 1);
      } catch (e) {
        if (gen !== genRef.current) return;
        if (e instanceof ApiError && e.code === "analysis_busy") {
          update(side, { gridStatus: "busy" });
          void tick(side, BUSY_MS, polls + 1);
          return;
        }
        if (e instanceof ApiError && (e.code === "ffmpeg_unavailable" || e.code === "waveform_failed")) {
          gridDone[side] = true;
          update(side, { waveformStatus: "unavailable", waveformReason: e.code, gridStatus: "unavailable", gridReason: e.code });
          return;
        }
        update(side, { error: "missing" });
      }
    };

    for (const side of SIDES) {
      eng.load(side, trackAudioUrl(trackIdOf(side)));
      const v = viewsRef.current[side];
      const ok = eng.setRate(side, v.rate, v.keyLock);
      if (!ok) update(side, { keyLockSupported: false, keyLock: false });
      void tick(side, 0, 0);
    }
    return () => { genRef.current++; };
  }, [idA, idB, mounted, trackIdOf, update]);

  // Scarto di fase, quattro volte al secondo, finche' c'e' uno schiavo con griglia.
  useEffect(() => {
    if (!slave) { setPhaseMs(null); return; }
    const id = setInterval(() => {
      const eng = engineRef.current;
      const m = viewsRef.current[other(slave)];
      const s = viewsRef.current[slave];
      const gm = toGrid(m.data?.grid);
      const gs = toGrid(s.data?.grid);
      if (!eng || !gm || !gs) { setPhaseMs(null); return; }
      setPhaseMs(phaseOffsetMs(gm, eng.position(other(slave)), m.rate, gs, eng.position(slave)));
    }, 250);
    return () => clearInterval(id);
  }, [slave]);

  const refreshCues = useCallback(async (trackId: number) => {
    const data = await getDeck(trackId);
    for (const side of SIDES) {
      if (trackIdOf(side) === trackId) update(side, { data });
    }
  }, [trackIdOf, update]);

  const applyRate = useCallback((side: DeckSide, rate: number, manual: boolean) => {
    const v = viewsRef.current[side];
    const r = clampRate(rate, v.range);
    engineRef.current?.setRate(side, r, v.keyLock);
    update(side, { rate: r });
    if (manual && slave === side) setSlave(null);
  }, [slave, update]);

  const align = useCallback((side: DeckSide) => {
    const eng = engineRef.current;
    const m = viewsRef.current[other(side)];
    const s = viewsRef.current[side];
    const gm = toGrid(m.data?.grid);
    const gs = toGrid(s.data?.grid);
    if (!eng || !gm || !gs) return false;
    const delta = alignShift(gm, eng.position(other(side)), gs, eng.position(side));
    eng.seek(side, eng.position(side) + delta);
    return true;
  }, []);

  const actionsFor = (side: DeckSide): DeckActions => {
    const eng = () => engineRef.current;
    const v = () => viewsRef.current[side];
    const tid = trackIdOf(side);
    const grid = () => toGrid(v().data?.grid);
    const nominal = () => v().data?.track.bpm ?? rowOf(side).track?.bpm ?? null;
    return {
      onPlayPause: () => { const e = eng(); if (!e) return; if (v().playing) e.pause(side); else void e.play(side); },
      onSeek: (tm) => update(side, { position: tm }),
      onRate: (rate) => applyRate(side, rate, true),
      onToggleRange: () => {
        const range: PitchRange = v().range === 8 ? 16 : 8;
        update(side, { range });
        const r = clampRate(v().rate, range);
        if (r !== v().rate) { eng()?.setRate(side, r, v().keyLock); update(side, { rate: r }); }
      },
      onKeyLock: (on) => { const ok = eng()?.setRate(side, v().rate, on) ?? false; update(side, { keyLock: ok && on, keyLockSupported: ok }); },
      onVolume: (vol) => { eng()?.setVolume(side, vol); update(side, { volume: vol }); },
      onLowCut: (on) => { eng()?.setLowCut(side, on); update(side, { lowCut: on }); },
      onSync: () => {
        const m = viewsRef.current[other(side)];
        const gm = toGrid(m.data?.grid);
        const gs = grid();
        const useGrids = !!(gm && gs);
        const mBpm = useGrids ? gm!.bpm : (m.data?.track.bpm ?? rowOf(other(side)).track?.bpm ?? null);
        const sBpm = useGrids ? gs!.bpm : nominal();
        if (!mBpm || !sBpm) return;
        applyRate(side, syncRate({ bpm: mBpm, rate: m.rate }, { bpm: sBpm }), false);
        if (useGrids) align(side);
        setSlave(side);
      },
      onBeatJump: (dir) => { const e = eng(); const step = beatJumpSeconds(grid(), nominal()); if (e && step) e.seek(side, e.position(side) + dir * step); },
      onNudge: (dir) => { const e = eng(); if (e) e.seek(side, e.position(side) + dir * NUDGE_S); },
      onAddCue: () => {
        const e = eng(); if (!e) return;
        const g = grid();
        const pos = v().snapToBeat && g ? nearestBeat(g, e.position(side)) : e.position(side);
        void createCue(tid, { position_seconds: pos, name: null }).then(() => refreshCues(tid)).catch(() => {});
      },
      onJumpCue: (cue: TrackCue) => eng()?.seek(side, cue.position_seconds),
      onRenameCue: (cue, name) => { void updateCue(tid, cue.id, { name }).then(() => refreshCues(tid)).catch(() => {}); },
      onDeleteCue: (cue) => { void deleteCue(tid, cue.id).then(() => refreshCues(tid)).catch(() => {}); },
      onToggleSnap: () => update(side, { snapToBeat: !v().snapToBeat }),
      onUsePlayBpm: () => { const b = effectiveBpm(nominal(), v().rate); if (b != null) onUsePlayBpm(rowOf(side), b); },
    };
  };

  const toggleHide = () => {
    const next = !hide;
    setHide(next);
    try { localStorage.setItem(HIDE_KEY, next ? "1" : "0"); } catch { /* privato o pieno: pazienza */ }
  };

  return (
    <div ref={barRef} data-testid="deck-dock" style={{ bottom: "var(--jobs-bar-height, 0px)" }}
      className="pointer-events-none fixed left-0 right-0 z-[60] p-2 sm:p-3 lg:left-[180px] lg:right-[var(--content-aside-width,0px)]">
      <div className="player-panel player-in pointer-events-auto relative border border-border-strong bg-elevated p-3 shadow-[var(--c-shadow-float)]">
        <div className="absolute right-2 top-2 flex items-center gap-2">
          <button type="button" data-testid="deck-hide-controls" onClick={toggleHide}
            className="flex items-center gap-1 text-[11px] text-muted hover:text-fg-strong">
            {hide ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
            {hide ? t.deck.showControls : t.deck.hideControls}
          </button>
          <button type="button" data-testid="deck-close" aria-label={t.deck.close} onClick={onClose}
            className="p-1 text-muted hover:text-fg-strong"><X size={15} /></button>
        </div>
        <audio ref={audioA} data-testid="deck-audio-A" className="hidden" />
        <audio ref={audioB} data-testid="deck-audio-B" className="hidden" />
        <div className="space-y-3 pr-40">
          <Deck view={views.A} actions={actionsFor("A")} audioEl={mounted ? audioA.current : null}
            audioUrl={trackAudioUrl(idA)} minPxPerSec={ZOOM_LEVELS[zoomIdx]} hideControls={hide} />
          <div className="h-px bg-border" />
          <Deck view={views.B} actions={actionsFor("B")} audioEl={mounted ? audioB.current : null}
            audioUrl={trackAudioUrl(idB)} minPxPerSec={ZOOM_LEVELS[zoomIdx]} hideControls={hide} />
        </div>
        <div className="mt-3 flex items-center justify-center gap-3 border-t border-border pt-2 text-[11px] text-muted">
          <span className="uppercase tracking-wider text-faint">{t.deck.phase}</span>
          <span data-testid="deck-phase" className="tnum text-base font-semibold text-fg-strong">
            {phaseMs == null ? "—" : `${phaseMs > 0 ? "+" : ""}${Math.round(phaseMs)} ms`}
          </span>
          <button type="button" data-testid="deck-realign" disabled={!slave}
            className="border border-border px-2 py-0.5 text-[11px] text-fg hover:bg-elevated disabled:opacity-40"
            onClick={() => { if (slave) align(slave); }}>{t.deck.realign}</button>
          <span className="ml-3 uppercase tracking-wider text-faint">{t.deck.zoom}</span>
          <button type="button" data-testid="deck-zoom-out" aria-label={t.deck.zoomOut} disabled={zoomIdx === 0}
            className="border border-border p-0.5 disabled:opacity-40" onClick={() => setZoomIdx((i) => Math.max(0, i - 1))}><Minus size={12} /></button>
          <button type="button" data-testid="deck-zoom-in" aria-label={t.deck.zoomIn} disabled={zoomIdx === ZOOM_LEVELS.length - 1}
            className="border border-border p-0.5 disabled:opacity-40" onClick={() => setZoomIdx((i) => Math.min(ZOOM_LEVELS.length - 1, i + 1))}><Plus size={12} /></button>
        </div>
      </div>
    </div>
  );
}
```

Note per chi implementa:
- `pr-40` lascia posto ai due comandi in alto a destra; sotto `lg` i deck impilano gia' le due colonne (`lg:grid-cols-[…]`), e il pannello puo' superare l'altezza utile: il `<main>` del guscio prende il `padding-bottom` dalla variabile, quindi niente resta coperto.
- Il `--player-bar-height` lo pubblicano sia il player docked (quando visibile) sia questo dock: mentre il dock e' aperto il docked non e' visibile (la pagina lo ferma, Task 14), quindi non c'e' contesa. Se il player docked rimonta per un play altrove, la pagina chiude il dock.
- `viewsRef` evita callback stantii nelle azioni e nell'intervallo di fase, senza rigenerare l'engine.
- In jsdom `HTMLMediaElement.play` non esiste: il test lo copre col motore finto; `fireEvent.error` sull'`<audio>` esercita l'ascoltatore reale.

- [ ] **Step 5: Esegui, deve passare; lint; type-check**

Run: `cd frontend && npx vitest run tests/deck-dock.test.tsx && npm run lint && npx tsc --noEmit -p tsconfig.json`
Expected: 15 passed; lint pulito; nessun errore di tipo

- [ ] **Step 6: Prova a mano nel browser dell'app** (il dock non e' ancora raggiungibile dal banco: montalo temporaneamente da una pagina di prova o aspetta la Task 14 e torna qui). Verifica i due punti lasciati aperti nella Task 12 (evento `scroll` iniziale, nessun doppio caricamento dell'elemento) e che il cursore resti centrato durante la riproduzione. Non committare pagine di prova.

- [ ] **Step 7: Commit**

```bash
git add frontend/components/deck/deck.tsx frontend/components/deck/deck-dock.tsx frontend/app/globals.css frontend/tests/deck-dock.test.tsx
git commit -m "feat(deck): i due deck nel pannello fisso, con sync, fase e cue"
```

---

### Task 14: "Prova il passaggio" nel banco e convivenza col player docked

**Files:**
- Modify: `frontend/components/set-builder/transition-panel.tsx`
- Modify: `frontend/components/set-builder/detail-panel.tsx`
- Modify: `frontend/app/sets/manual/page.tsx`
- Test: `frontend/tests/set-builder-deck.test.tsx`

**Interfaces:**
- Produces: `TransitionPanel` accetta `onAudition?: () => void` e `auditionBlockedReason?: string | null`; `DetailPanel` accetta `onAudition?: (tr: ManualTransition) => void` e `auditionBlockedReason?: (tr: ManualTransition) => string | null`; la pagina tiene `audition: { fromId: number; toId: number } | null` e monta `<DeckDock>`.
- Consumes: `DeckDock`, `usePlayer().stop`, `usePlayer().active`, `onSavePlayBpm`.

- [ ] **Step 1: Test**

```tsx
// frontend/tests/set-builder-deck.test.tsx
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";

const api = vi.hoisted(() => ({
  getManualSet: vi.fn(),
  getMaterial: vi.fn(),
  patchRow: vi.fn(),
}));
vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<object>()),
  ...api,
}));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => "/sets/manual",
  useSearchParams: () => new URLSearchParams("id=7"),
}));
/* Il dock vero vuole Web Audio e wavesurfer: qui basta sapere con quali righe
   la pagina lo monta e che i suoi callback arrivano. */
const dock = vi.hoisted(() => ({ props: null as null | Record<string, unknown> }));
vi.mock("@/components/deck/deck-dock", () => ({
  DeckDock: (p: { from: { id: number }; to: { id: number }; onClose: () => void; onUsePlayBpm: (row: unknown, bpm: number) => void }) => {
    dock.props = p;
    return (
      <div data-testid="deck-dock">
        {p.from.id}→{p.to.id}
        <button onClick={p.onClose}>chiudi-dock</button>
        <button onClick={() => p.onUsePlayBpm(p.to, 126)}>usa-bpm</button>
      </div>
    );
  },
}));

import ManualSetPage from "@/app/sets/manual/page";
import { PlayerProvider } from "@/lib/player";

const track = (id: number, extra = {}) => ({
  id, spotify_id: null, soundcloud_id: null, source_type: "spotify", platform: "spotify",
  title: `Traccia ${id}`, artist: "Artista", album: null, genre: null, year: null,
  duration_seconds: 300, bpm: 124, camelot_key: "8A", energy: null,
  label: null, status: "imported", url: null, isrc: null, playlists: [], added_at: null,
  spotify_url: null, album_art_url: null, has_local_file: true, rating: null, ...extra,
});
const rows = (secondOwned = true) => [
  { id: 1, track: track(1) },
  { id: 2, track: track(2, { has_local_file: secondOwned }) },
];
const set = (r = rows()) => ({
  id: 7, name: "Sabato", kind: "manual", revision: 0, sources: [], notes: null,
  track_count: 2, total_file_seconds: 600, can_undo: false, can_redo: false,
  duration: { seconds: 600, incomplete: false, unknown_rows: 0, open_gaps: 0 },
  created_at: "2026-10-03T10:00:00", updated_at: "2026-10-03T10:00:00",
  blocks: [{ id: 1, name: null, placement: "main" as const, position: 1,
    rows: r.map((x, i) => ({ id: x.id, block_id: 1, position: i + 1, slot_kind: "track" as const, track: x.track,
                             note: null, play_bpm: null, planned_seconds: null, alternatives: [] })) }],
  reserve: [],
  transitions: [{ from_row_id: 1, to_row_id: 2, from_track_id: 1, to_track_id: 2, bpm_from: 124, bpm_to: 124,
                  bpm_percent: 0, halftime: false, key_from: "8A", key_to: "8A", key_relation: "same",
                  score: 90, missing: [], note: null }],
});

const mount = () => render(<PlayerProvider><ManualSetPage /></PlayerProvider>);

beforeEach(() => {
  dock.props = null;
  api.getManualSet.mockResolvedValue(set());
  api.getMaterial.mockResolvedValue({ sources: [], items: [{ track: track(1), in_set: true, from_playlist: false, in_reserve: false }] });
  api.patchRow.mockImplementation(async () => set());
  vi.spyOn(HTMLMediaElement.prototype, "play").mockImplementation(function (this: HTMLMediaElement) {
    this.dispatchEvent(new Event("play")); return Promise.resolve();
  });
  vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => {});
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

async function selezionaPrimaRiga() {
  mount();
  await waitFor(() => expect(within(screen.getByTestId("path-panel")).getByText("Traccia 1")).toBeTruthy());
  fireEvent.click(within(screen.getByTestId("path-panel")).getByRole("button", { name: /Traccia 1/ }));
  await waitFor(() => expect(screen.getByTestId("transition-panel-out")).toBeTruthy());
}

describe("banco: prova il passaggio", () => {
  it("il pulsante monta il dock con le due righe del passaggio", async () => {
    await selezionaPrimaRiga();
    fireEvent.click(within(screen.getByTestId("transition-panel-out")).getByRole("button", { name: "Prova il passaggio" }));
    expect(screen.getByTestId("deck-dock").textContent).toContain("1→2");
  });

  it("senza il file di una delle due tracce il pulsante e' disabilitato con il motivo", async () => {
    api.getManualSet.mockResolvedValue(set(rows(false)));
    await selezionaPrimaRiga();
    const b = within(screen.getByTestId("transition-panel-out")).getByRole("button", { name: "Prova il passaggio" }) as HTMLButtonElement;
    expect(b.disabled).toBe(true);
    expect(b.title).toBe("Serve il file locale di entrambe le tracce");
  });

  it("«usa come la suono a» scrive play_bpm della riga d'arrivo", async () => {
    await selezionaPrimaRiga();
    fireEvent.click(within(screen.getByTestId("transition-panel-out")).getByRole("button", { name: "Prova il passaggio" }));
    fireEvent.click(screen.getByText("usa-bpm"));
    await waitFor(() => expect(api.patchRow).toHaveBeenCalledWith(7, 2, { expected_revision: 0, play_bpm: 126 }));
  });

  it("la ✕ chiude; un play altrove chiude anche lui", async () => {
    await selezionaPrimaRiga();
    const apri = () => fireEvent.click(within(screen.getByTestId("transition-panel-out")).getByRole("button", { name: "Prova il passaggio" }));
    apri();
    fireEvent.click(screen.getByText("chiudi-dock"));
    expect(screen.queryByTestId("deck-dock")).toBeNull();
    apri();
    expect(screen.getByTestId("deck-dock")).toBeTruthy();
    // Il play del materiale passa dal player docked: un solo padrone del fondo pagina.
    fireEvent.click(within(screen.getByTestId("material-panel")).getAllByRole("button", { name: "Ascolta" })[0]);
    await waitFor(() => expect(screen.queryByTestId("deck-dock")).toBeNull());
  });
});
```

- [ ] **Step 2: Esegui, deve fallire**

Run: `cd frontend && npx vitest run tests/set-builder-deck.test.tsx`
Expected: FAIL (nessun pulsante "Prova il passaggio")

- [ ] **Step 3: `TransitionPanel`**

Aggiungi `Play` all'import da `lucide-react` e `Button` da `@/components/ui`; alle props:

```ts
  /** Apre i due deck su questo passaggio. Assente = la pagina non lo offre. */
  onAudition?: () => void;
  /** Motivo per cui non si puo' (file locale mancante); null = si puo'. */
  auditionBlockedReason?: string | null;
```

e dopo la `Textarea`:

```tsx
      {onAudition && (
        <Button size="sm" variant="outline" className="mt-2" disabled={!!auditionBlockedReason}
          title={auditionBlockedReason ?? undefined} onClick={onAudition}>
          <Play size={14} /> {t.deck.audition}
        </Button>
      )}
```

- [ ] **Step 4: `DetailPanel`**

Props nuove:

```ts
  onAudition?: (tr: ManualTransition) => void;
  auditionBlockedReason?: (tr: ManualTransition) => string | null;
```

e nei due `TransitionPanel`:

```tsx
      {entrante && (
        <TransitionPanel transition={entrante} variant="in" onSaveNote={onSavePairNote}
          onAudition={onAudition ? () => onAudition(entrante) : undefined}
          auditionBlockedReason={auditionBlockedReason?.(entrante) ?? null} />
      )}
      {uscente && (
        <TransitionPanel transition={uscente} variant="out" onSaveNote={onSavePairNote}
          onAudition={onAudition ? () => onAudition(uscente) : undefined}
          auditionBlockedReason={auditionBlockedReason?.(uscente) ?? null} />
      )}
```

- [ ] **Step 5: La pagina**

Import: `import { DeckDock } from "@/components/deck/deck-dock";` e `import { usePlayer } from "@/lib/player";`. Dentro `ManualSetInner`, dopo `const rows = …` e `const selected = …`:

```tsx
  const player = usePlayer();
  const [audition, setAudition] = useState<{ fromId: number; toId: number } | null>(null);
  const rowsOf = (tr: ManualTransition) => ({
    from: rows.find((r) => r.id === tr.from_row_id) ?? null,
    to: rows.find((r) => r.id === tr.to_row_id) ?? null,
  });
  const auditionBlockedReason = (tr: ManualTransition) => {
    const { from, to } = rowsOf(tr);
    return from?.track?.has_local_file && to?.track?.has_local_file ? null : t.deck.auditionNeedsFiles;
  };
  /** Ferma il docked PRIMA di aprire i deck, nello stesso gesto: cosi' il
   *  render successivo vede `active` nullo e l'effetto qui sotto non richiude
   *  subito il dock appena aperto. */
  const onAudition = (tr: ManualTransition) => {
    const { from, to } = rowsOf(tr);
    if (!from || !to || auditionBlockedReason(tr)) return;
    player.stop();
    setAudition({ fromId: from.id, toId: to.id });
  };
  // Un play altrove (TrackPlayButton) riaccende il docked: un solo padrone del fondo pagina.
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- reagisce a uno stato esterno (il player), come il resto della pagina
    if (player.active) setAudition(null);
  }, [player.active]);
  // Se una delle due righe sparisce dal percorso, il dock non ha piu' senso.
  const auditionRows = audition
    ? { from: rows.find((r) => r.id === audition.fromId) ?? null, to: rows.find((r) => r.id === audition.toId) ?? null }
    : null;
  const deckRows = auditionRows?.from?.track && auditionRows.to?.track ? auditionRows : null;
```

Lo `useState` degli hook va sopra ogni `return` condizionale: `rows`/`selected` sono calcolati dopo i primi hook ma prima del `return`, quindi questa posizione va bene; se la pagina avesse un ritorno anticipato prima di qui, sposta gli hook piu' su.

Nel `DetailPanel`:

```tsx
            <DetailPanel row={selected} transitions={vista.transitions} saveState={saveState}
              …
              onAudition={onAudition} auditionBlockedReason={auditionBlockedReason} />
```

e prima della chiusura di `</PageLayout>`:

```tsx
      {deckRows && (
        <DeckDock from={deckRows.from!} to={deckRows.to!} onClose={() => setAudition(null)}
          onUsePlayBpm={(row, bpm) => void onSavePlayBpm(row, bpm)} />
      )}
```

- [ ] **Step 6: Esegui tutti i test del banco, lint, type-check**

Run: `cd frontend && npx vitest run tests/set-builder-deck.test.tsx tests/set-builder-workbench.test.tsx tests/set-builder-alternatives.test.tsx tests/set-builder-material-order.test.tsx && npm run lint && npx tsc --noEmit -p tsconfig.json`
Expected: tutti passed; lint e tipi puliti

- [ ] **Step 7: Prova nel browser dell'app** (`preview_start` sul dev server del frontend con il backend su :8000): apri un set con due tracce possedute, seleziona una riga, "Prova il passaggio". Controlla: il dock compare, il player docked sparisce, le waveform arrivano, il cursore resta centrato, "Sync su A" porta i BPM a coincidere e la fase sotto ±10 ms, una cue si aggiunge e si vede sul marker, la ✕ chiude. Chiudi anche i due punti lasciati aperti nella Task 12. Annota in PROGRESS.md (Task 16) cio' che non si e' potuto verificare.

- [ ] **Step 8: Commit**

```bash
git add frontend/components/set-builder/transition-panel.tsx frontend/components/set-builder/detail-panel.tsx frontend/app/sets/manual/page.tsx frontend/tests/set-builder-deck.test.tsx
git commit -m "feat(sets): «Prova il passaggio» apre i due deck dal banco"
```

---

### Task 15: end to end contro il backend vero

**Files:**
- Create: `frontend/e2e/deck.spec.ts`

**Interfaces:**
- Consumes: `PATCH /api/settings/config` (`library_root`), `POST /api/playlists/import-manual`, `POST /api/tracks/{id}/link-file`, `POST /api/sets/manual`, `POST /api/sets/{id}/rows`, gli endpoint del deck, i testid del dock. ffmpeg deve essere installato sulla macchina che esegue la suite (lo e' gia' per l'indicizzazione).

- [ ] **Step 1: Il test**

```ts
// frontend/e2e/deck.spec.ts
import { expect, test, type APIRequestContext } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

// I due deck dal banco, contro il backend vero: due WAV di click a 120 e 124
// BPM, collegati a due tracce, in un set con due righe. La cartella sta sotto
// backend/data (gia' in .gitignore) e diventa la libreria del backend di test
// via API, perche' l'endpoint audio serve solo file dentro le radici consentite.

function clickTrackWav(file: string, bpm: number, seconds = 20, sr = 22050) {
  const n = sr * seconds;
  const interval = Math.round((sr * 60) / bpm);
  const pcm = Buffer.alloc(n * 2);
  for (let i = 0; i < n; i++) {
    const click = i % interval < Math.round(sr * 0.01);
    const v = click ? Math.round(0.9 * 32767 * Math.sin((2 * Math.PI * 1000 * i) / sr)) : 0;
    pcm.writeInt16LE(v, i * 2);
  }
  const header = Buffer.alloc(44);
  header.write("RIFF", 0); header.writeUInt32LE(36 + pcm.length, 4); header.write("WAVE", 8);
  header.write("fmt ", 12); header.writeUInt32LE(16, 16); header.writeUInt16LE(1, 20);
  header.writeUInt16LE(1, 22); header.writeUInt32LE(sr, 24); header.writeUInt32LE(sr * 2, 28);
  header.writeUInt16LE(2, 32); header.writeUInt16LE(16, 34);
  header.write("data", 36); header.writeUInt32LE(pcm.length, 40);
  fs.writeFileSync(file, Buffer.concat([header, pcm]));
}

async function seminaTracce(request: APIRequestContext, n: number, prefisso: string) {
  const righe = Array.from({ length: n }, (_, i) => `Artista ${prefisso}${i} - Traccia ${prefisso}${i}`).join("\n");
  const res = await request.post("/api/playlists/import-manual", {
    data: { name: `E2E deck ${prefisso}`, text: righe },
  });
  expect(res.ok()).toBeTruthy();
  const report = await res.json();
  const tracce = await (await request.get(`/api/playlists/${report.playlist_id}/tracks`)).json();
  return { playlistId: report.playlist_id as number, trackIds: tracce.map((t: { id: number }) => t.id) as number[] };
}

test("i due deck si aprono dal passaggio e la cue sopravvive al ricaricamento", async ({ page, request }) => {
  test.setTimeout(180_000);
  const stamp = `${Date.now()}-${Math.random().toString(36).slice(2, 6)}`;
  const libDir = path.resolve(process.cwd(), "../backend/data/e2e-library");
  fs.mkdirSync(libDir, { recursive: true });
  const files = [120, 124].map((bpm, i) => {
    const f = path.join(libDir, `deck-${stamp}-${i}.wav`);
    clickTrackWav(f, bpm);
    return f;
  });
  expect((await request.patch("/api/settings/config", { data: { library_root: libDir } })).ok()).toBeTruthy();

  const { playlistId, trackIds } = await seminaTracce(request, 2, `dk${stamp.slice(-4)}`);
  for (const [i, id] of trackIds.entries()) {
    const r = await request.post(`/api/tracks/${id}/link-file`, { data: { path: files[i] } });
    expect(r.ok()).toBeTruthy();
  }
  const creato = await request.post("/api/sets/manual", { data: { playlist_ids: [playlistId] } });
  expect(creato.ok()).toBeTruthy();
  const set = await creato.json();
  await request.post(`/api/sets/${set.id}/rows`, { data: { expected_revision: 0, track_ids: trackIds } });

  await page.goto(`/sets/manual?id=${set.id}`);
  const path_ = page.getByTestId("path-panel");
  await path_.getByRole("button", { name: new RegExp(`Traccia dk${stamp.slice(-4)}0`) }).click();
  await page.getByTestId("transition-panel-out").getByRole("button", { name: "Prova il passaggio" }).click();

  const dock = page.getByTestId("deck-dock");
  await expect(dock).toBeVisible();
  await expect(dock.getByTestId("deck-A")).toContainText(`Traccia dk${stamp.slice(-4)}0`);
  await expect(dock.getByTestId("deck-B")).toContainText(`Traccia dk${stamp.slice(-4)}1`);
  // wavesurfer disegna in un shadow root: i locator CSS di Playwright lo attraversano.
  await expect(dock.getByTestId("deck-waveform-A").locator("canvas").first()).toBeVisible({ timeout: 30_000 });

  // Lo stato della griglia si confronta con la verita' dell'API: `prepare` dice
  // subito se il motore manca; altrimenti si aspetta griglia o errore.
  const prep = await (await request.post(`/api/tracks/${trackIds[0]}/deck/prepare`)).json();
  let stato = prep.grid === "unavailable" ? "unavailable" : "pending";
  for (let i = 0; i < 90 && stato === "pending"; i++) {
    await page.waitForTimeout(1000);
    const d = await (await request.get(`/api/tracks/${trackIds[0]}/deck`)).json();
    if (d.grid) stato = "grid";
    else if (d.grid_error) stato = "error";
  }
  expect(stato).not.toBe("pending");
  if (stato === "grid") {
    await expect(dock.getByTestId("deck-status-A")).toHaveCount(0, { timeout: 10_000 });
  } else {
    await expect(dock.getByTestId("deck-status-A")).toContainText("griglia non disponibile", { timeout: 10_000 });
  }

  // Una cue sul deck A, poi ricarico e riapro: e' ancora li'.
  await dock.getByTestId("deck-cue-add-A").click();
  await expect(dock.getByTestId("deck-A").getByRole("button", { name: /^1\b/ })).toBeVisible();
  const cues = await (await request.get(`/api/tracks/${trackIds[0]}/deck`)).json();
  expect(cues.cues).toHaveLength(1);
  await page.reload();
  await path_.getByRole("button", { name: new RegExp(`Traccia dk${stamp.slice(-4)}0`) }).click();
  await page.getByTestId("transition-panel-out").getByRole("button", { name: "Prova il passaggio" }).click();
  await expect(page.getByTestId("deck-dock").getByTestId("deck-A").getByRole("button", { name: /^1\b/ })).toBeVisible();

  // La ✕ chiude; un play dal materiale fa tornare il player docked.
  await page.getByTestId("deck-close").click();
  await expect(page.getByTestId("deck-dock")).toHaveCount(0);
  await page.getByTestId("material-panel").getByRole("button", { name: "Ascolta" }).first().click();
  await expect(page.getByTestId("local-audio")).toHaveCount(1);
});
```

- [ ] **Step 2: Esegui**

Run: `cd frontend && npm run test:e2e -- e2e/deck.spec.ts`
Expected: 1 passed. Se Essentia e' nel venv del backend (lo e' sul Mac di sviluppo), il ramo e' `grid`; altrove `unavailable`. Entrambi sono asserzioni esatte. Se fallisce sul primo `toBeVisible` del canvas, controlla con `preview_logs` che il backend abbia trovato ffmpeg.

- [ ] **Step 3: Esegui tutta la suite e2e** per accertare che il cambio di `library_root` a runtime non disturbi gli altri test (girano in parallelo sullo stesso backend).

Run: `cd frontend && npm run test:e2e`
Expected: tutti passed

- [ ] **Step 4: Commit**

```bash
git add frontend/e2e/deck.spec.ts
git commit -m "test(deck): e2e dei due deck dal banco"
```

---

### Task 16: documentazione, lista a orecchio, chiusura

**Files:**
- Modify: `CLAUDE.md`, `README.md`, `docs/ARCHITECTURE.md`, `docs/API.md`, `docs/ROADMAP.md`, `docs/DEPENDENCIES.md`, `PROGRESS.md`

Regola della roadmap: parentesi e "vedi X" si controllano a parte, separatamente dalla frase a cui sono attaccati.

- [ ] **Step 1: `CLAUDE.md`**

Nel paragrafo "Project", sostituisci la frase «The project does not act as a DJ deck (no waveform/cue/queue — that stays with the Set Builder/Rekordbox)» con:

> The project is not a DJ deck and does not replace Rekordbox. One bounded exception, decided 2026-10-03: inside the manual workbench (`/sets/manual`) a passage between two rows can be auditioned on **two decks** (waveform, in-app beat grid from Essentia, pitch with master tempo, tempo/phase sync, volume, low cut, memory cues saved per track in Cratory). The decks open only from a passage, only on owned tracks, and never leave the workbench; cues are neither imported from nor exported to Rekordbox.

Nella regola 2, aggiungi in coda: «La griglia dei battiti dei deck (`grid_first_beat`/`grid_bpm`) è un derivato Essentia che non tocca mai `bpm`/`key` né le provenienze.» Nell'elenco dei router aggiungi `deck`; in quello dei servizi `beatgrid.py`, `waveform.py`, `deck_cues.py`.

- [ ] **Step 2: `README.md`**

La frase «Cratory is not a DJ deck — no waveforms, no cues, no queue; that stays in Rekordbox — and it is not a service.» diventa:

> Cratory is not a DJ deck — it does not replace Rekordbox — and it is not a service. Its one playing feature beyond quick audition is a two-deck audition of a passage inside the set workbench (waveform, in-app beat grid, pitch, sync, memory cues kept in Cratory).

Aggiungi una voce nella sezione delle funzioni del banco, se esiste, con una riga sui deck.

- [ ] **Step 3: `docs/ARCHITECTURE.md`**

- Riga 29: «Beatgrid and cue points are out of scope; there is no live Rekordbox integration.» → «The Rekordbox `TEMPO` node (its beat grid) and its cue points are not imported; the decks compute their own grid from Essentia and keep their own cues (see the deck section). There is no live Rekordbox integration.»
- Riga 54: «Cratory is not a DJ deck — no waveform, no cue, no queue — but it does play the files you own, read-only, through one shared docked player.» → «Cratory does not replace a DJ deck, but it plays the files you own read-only: through one shared docked player, and, inside the set workbench, on two decks that audition a passage (see below).»
- Riga 828, nota di scope dell'import Rekordbox: resta vera; aggiungi «The deck grid is Cratory's own (Essentia), not Rekordbox's.»
- Sezione nuova «Two-deck audition» dopo quella sul player docked: le tre strutture dati (`Track.grid_*`, `track_waveforms`, `track_cues`), chi scrive la griglia e chi la azzera (l'elenco della Task 4), il grafo audio (`<audio>` → passa-alto → gain → master), il rate di sync sui BPM di griglia, la fase misurata e mai corretta da sola, la convivenza col player docked, i limiti (precisione di qualche ms, AIFF non in Chrome).

- [ ] **Step 4: `docs/API.md`**

Sezione «Deck» con i cinque endpoint della Task 7 (metodo, percorso, body, risposta, codici d'errore) e, nella sezione analysis, il campo `ticks` del worker e le colonne `grid_*` scritte dal job.

- [ ] **Step 5: `docs/ROADMAP.md`**

La voce rinviata del 2026-09-17 («Deferred behind it, as its own design cycle … no waveform/cue/loop») diventa lo stato attuale: fatto il 2026-10-xx per la spec `2026-10-03-two-deck-audition-design.md`, con la differenza dichiarata: waveform e cue entrano, la griglia e' solo Essentia e il nodo `TEMPO` resta fuori, nessun import/export di cue. Nel backlog aperto: i seguiti della sezione 12 della spec (export cue in XML con l'import a due passi, scorciatoie, battuta uno).

- [ ] **Step 6: `docs/DEPENDENCIES.md`**

Nella sezione frontend: `wavesurfer.js ^8.0.1 — BSD-3-Clause — waveform, Minimap e Regions dei due deck; nessun fetch ne' decode: riceve i picchi dal backend`.

- [ ] **Step 7: `PROGRESS.md`**

Voce datata: cosa e' entrato, i cinque commit principali, la lista a orecchio con l'esito di ogni punto (fatto / non verificabile a schermo), e i due punti di wavesurfer verificati nel browser.

- [ ] **Step 8: Lista a orecchio** (sezione 8 della spec), nel browser dell'app e in Tauri (vedi la memoria «Verificare un fix nell'app Tauri»): sync entro ±10 ms stabile per due minuti; master tempo udibile; taglio bassi; spinte e salti coerenti con la lettura di fase; cue al battito; convivenza col docked; "nascondi" ricordato. Cio' che si legge a schermo lo chiude chi implementa; cio' che si deve sentire lo chiude l'utente: scrivi in PROGRESS.md quali punti restano a lui.

- [ ] **Step 9: Verifica finale**

Run: `cd backend && .venv/bin/python -m pytest tests -q && cd ../frontend && npm run lint && npx vitest run && npm run build`
Expected: tutto verde; il build Next riesce (wavesurfer e' ESM, Turbopack lo accetta).

- [ ] **Step 10: Commit**

```bash
git add CLAUDE.md README.md docs/ARCHITECTURE.md docs/API.md docs/ROADMAP.md docs/DEPENDENCIES.md PROGRESS.md
git commit -m "docs: i due deck nel banco — architettura, API, roadmap, dipendenze"
```

---

## Autoverifica del piano

**Copertura della spec.** Sezione 1 decisioni → Task 1-3 (griglia Essentia, regola 2), 5-7 (cue solo in Cratory), 8-13 (materiale collaudato, media element), 14 (un solo padrone del fondo pagina). Sezione 2 esperienza → Task 13 (dock, gesti, stati), 14 (apertura). Sezione 3 dati → Task 3, 5, 6. Sezione 4 API → Task 7. Sezione 5 motore → Task 9, 10, 12. Sezione 6 componenti → Task 11-14. Sezione 7 errori → Task 7 (backend), 13 (frontend). Sezione 8 test → ogni task; e2e Task 15; lista a orecchio Task 16. Sezione 9 documentazione → Task 16. Sezione 10 tappe → le cinque tappe sono Task 1-4, 5-7, 8-10, 11-14, 15-16. Sezione 11 criteri → il grep su `bpm_source`/`key_source` e' nel Global Constraints; la precisione di fase e i tempi di apertura sono nella lista a orecchio.

Due scostamenti dichiarati dalla spec: il test dei picchi usa un blocco a piena scala invece di una sinusoide (una sinusoide campionata non tocca 32767 e darebbe 254); l'e2e confronta lo stato della griglia con la risposta di `prepare` e con `/deck`, non con `analysis/overview`, che non espone la presenza del motore.

**Segnaposto.** Nessun TBD/TODO; ogni passo di codice ha il codice.

**Coerenza dei nomi.** `beatgrid.fit/clear/Grid/GridError` (Task 1, usati in 3, 4); `waveform.peaks_from_pcm/is_fresh/ensure_waveform/PEAKS_PER_SECOND` (5, usati in 7); `local_files.ffmpeg_path/decode_pcm_full` (5, usati in 7); `deck_cues.list_cues/add_cue/update_cue/CueLimitError/CueOutOfRange` (6, usati in 7); schemi `DeckOut/DeckPrepareOut/CueIn/CueUpdateIn/CueOut` (7); frontend `getDeck/prepareDeck/createCue/updateCue/deleteCue/decodePeaks` (8, usati in 12, 13); `grid.ts` (9, usato in 12, 13); `DeckEngine/SIDES/DeckSide/setPreservesPitch` (10, usati in 11, 13); `CueStrip/MAX_CUES` (11, usata in 13); `DeckWaveform` (12, usata in 13); `Deck/DeckView/DeckActions`, `DeckDock` (13, usata in 14). Testid: `deck-dock`, `deck-A/B`, `deck-audio-A/B`, `deck-status-*`, `deck-play-*`, `deck-sync-*`, `deck-pitch-*`, `deck-range-*`, `deck-use-playbpm-*`, `deck-cue-add-*`, `deck-waveform-*`, `deck-grid-canvas-*`, `deck-phase`, `deck-realign`, `deck-hide-controls`, `deck-close`, `deck-zoom-in/out`, `transition-panel-in/out` (gia' esistenti).

**Review Focus.** 1 → Task 5 (`test_pcm_vuoto_e_pcm_a_byte_dispari`); 2 → Task 13 (stessa traccia sui due deck); 3 → Task 10 (seek mai sotto zero); 4 → Task 13 (cambio corsa); 5 → Task 13 (zero picchi). Piu' il bordo senza durata, Task 6 (`test_senza_durata_vale_solo_il_bordo_inferiore`).
