# Miglioramenti di solidità ispirati a beets — design

**Data:** 2026-07-14
**Stato:** approvato (brainstorming) → pronto per il piano di implementazione
**Ispirazione:** [beets](https://github.com/beetbox/beets) — motore di matching (`autotag/distance.py`) e plugin `badfiles`, adattati al modello per-traccia e locale di Sortory.

## Panoramica

Due miglioramenti **indipendenti** (nessun codice condiviso), raccolti in un unico spec per produrre **un solo piano di implementazione**. Possono essere realizzati in due tracce separate.

- **Parte 1 — Confidenza graduata via distanza pesata.** Sostituisce il binario `high`/`text` dei suggerimenti provider con 3 gradi `strong`/`medium`/`weak` calcolati da una distanza pesata locale.
- **Parte 2 — Controllo integrità file (badfiles).** Job on-demand che decodifica ogni file con ffmpeg per trovare i corrotti/troncati e proporli per la quarantena; include una riorganizzazione della zona azioni della pagina Issues.

Nessuna delle due cambia la **forma** della pipeline (`Sources → scan → Issues → Duplicates → Plan → Apply → History`): sono additive dentro fasi esistenti.

---

# Parte 1 — Confidenza graduata via distanza pesata

## Contesto e problema

Oggi la confidenza di un suggerimento provider è **binaria** ([`text_providers.py:36`](../../../backend/app/services/text_providers.py)):

```python
conf = "high" if (mb_res.get("confidence") or 0) >= 95 else "text"
```

cioè si fida dello `score` opaco restituito dalla search di MusicBrainz e applica una soglia secca. Conseguenza: **tutti** i match testuali finiscono nel bucket `text` ("rivedi tutto"), senza distinguere un match testuale che concorda benissimo coi tag del file da uno che diverge molto.

Vogliamo una confidenza **graduata** su 3 livelli, calcolata da un confronto vero campo-per-campo, così da dare un segnale più fine nella pagina Issues (badge a 3 stati), restringere il rumore del bucket "rivedi tutto", e mantenere l'azione di massa "accetta i sicuri" ancorata al grado più affidabile. Non nasce da un'esigenza specifica: è un miglioramento di solidità della feature esistente.

## Scope

**In scope.** Sostituire la stringa `confidence` prodotta da `text_providers.resolve` con un grado `strong`/`medium`/`weak` calcolato localmente. Adeguare i consumatori (contatori rescan, endpoint accept di massa, badge UI, i18n).

**Fuori scope (deciso in brainstorming).**

- **Nessun gap-guard.** Non si recuperano i top-N candidati da MusicBrainz per misurare l'ambiguità tra 1° e 2°: si continua a usare il **solo candidato migliore** che `_best_recording` già restituisce. Il layer di integrazione MusicBrainz **non si tocca**.
- Nessuna nuova dipendenza (si usa `difflib` della stdlib, non `jellyfish`).
- Nessuna migrazione del DB (retrocompatibilità a lettura).

## Architettura

Nuovo modulo **puro e testabile** `backend/app/services/match_distance.py` (niente I/O, niente rete, stile `dedup.py`):

```python
def grade_confidence(file, canonical: dict, *, exact: bool) -> str:
    """Ritorna "strong" | "medium" | "weak"."""
```

Punto d'innesto unico: [`text_providers.resolve`](../../../backend/app/services/text_providers.py), dove la riga binaria diventa

```python
conf = grade_confidence(file, mb_res, exact=(mb_res.get("confidence") or 0) >= 95)
```

I layer restano separati: integrazione MB intatta, logica in `services/`, forma HTTP in `routers/` + `schemas.py`.

## Il modello di distanza

### Regola A — Identità certa → `strong` (bypassa la distanza)

Se il match è arrivato per **MBID o ISRC** (oggi = `mb_res["confidence"] >= 95`, impostato con `exact=True` in [`musicbrainz.py:192`](../../../backend/app/integrations/musicbrainz.py)), la confidenza è **`strong`** a prescindere dai tag del file: l'identità è certa anche se i tag sono sporchi. Preserva il comportamento fingerprint/ISRC odierno.

### Regola B — Match testuale → distanza pesata → grado

Solo quando **non** c'è identità certa, si confrontano i campi che il file **già dichiara** con i canonici del candidato:

| Campo  | Peso | Note |
|--------|------|------|
| artist | 3.0  | ancora principale |
| title  | 3.0  | ancora principale |
| album  | 3.0  | contribuisce **solo se presente su entrambi**; assente sul file → nessuna penalità |
| year   | 1.0  | idem |
| label  | 0.5  | idem |

**String-distance per campo** (stile beets, compatto):

1. **Normalizzazione**: `casefold`, rimozione di `feat.`/`ft.`/`featuring …`, dell'articolo iniziale `the`, della punteggiatura, squeeze degli spazi.
2. **Distanza** = `1 - difflib.SequenceMatcher(None, a, b).ratio()` (stdlib, **nessuna dipendenza nuova**). Valore in `[0, 1]`.

**Aggregazione** (solo campi comparabili, presenti su entrambi):

```
D = sum(weight_f * dist_f for f in comparabili) / sum(weight_f for f in comparabili)
```

Se nessun campo è comparabile → fallback `weak`.

**Soglie → grado** (⚠️ **provvisorie**, calibrate via TDD — il metrico differisce da beets, i suoi `0.04`/`0.25` non si trasferiscono):

| Distanza `D` | Grado |
|--------------|--------|
| `D ≤ 0.15`   | `strong` |
| `D ≤ 0.40`   | `medium` |
| `D > 0.40`   | `weak` |

Costanti di modulo (hardcoded v1; niente Settings).

**Campi da Discogs.** Gap-fill testuale senza candidato scorabile → restano **`weak`**. La distanza pesata governa **solo** il match MusicBrainz.

### Effetto atteso

Oggi ogni match testuale → `text`. Ora un match testuale i cui canonici concordano bene coi tag del file sale a `medium`/`strong`, riducendo il bucket "rivedi tutto". Un match che diverge molto resta `weak` (giusto: va rivisto, potrebbe essere il brano sbagliato).

## Consumatori e retrocompatibilità

**Azione di massa.** [`accept_high_overrides`](../../../backend/app/routers/issues.py) (oggi accetta `confidence == "high"`) diventa **"accetta tutti gli `strong`"** — bulk ancorata al solo grado più sicuro.
- Rotta `POST /api/issues/provider-override/accept-high` → `/accept-strong` (nessun consumatore esterno).
- Label utente del bottone invariata ("✓ Accetta tutte le alta-confidenza"); cambia solo *cosa* seleziona.
- **Tolleranza legacy:** accetta sia `"strong"` sia il vecchio `"high"`.

**Contatori.** `proposed_high`/`proposed_text` → `proposed_strong`/`proposed_medium`/`proposed_weak`, in: dict di [`provider_rescan.rescan`](../../../backend/app/services/provider_rescan.py), schema `RescanResult`, tipo in `frontend/lib/api.ts`, stringa `rescanNote` (en/it).

**Badge UI.** [`issues-table.tsx`](../../../frontend/components/issues-table.tsx) da 2 a 3 stati con 3 colori (strong = verde, medium = ambra, weak = grigio) e chiavi i18n `confStrong`/`confMedium`/`confWeak`. Mappa i valori legacy: `high` → stile `strong`, `text` → stile `weak`.

**Retrocompatibilità dati — nessuna migrazione.** Gli override nel DB portano `high`/`text`; i due lettori (badge + endpoint accept) restano **tolleranti**, i valori si **auto-guariscono al primo rescan**.

**Da verificare in impl. (basso rischio):** [`covers.py`](../../../backend/app/services/covers.py) usa `resolved.confidence` (overall) — stringa passata avanti, dovrebbe reggere i nuovi valori; controllare che non ci sia un `== "high"` nascosto sulle cover.

## Testing (Parte 1)

Nuovo `backend/tests/test_match_distance.py`, casi che **fissano le soglie** su dati realistici:

- `exact=True` → `strong` anche con tag divergenti.
- testuale, canonici == file → `strong`; divergenza moderata → `medium`; forte → `weak`.
- normalizzazione: `The Prodigy` ≈ `Prodigy`; `Artist feat. X` ≈ `Artist`; punteggiatura/maiuscole ininfluenti.
- album/year/label assenti sul file → nessuna penalità; nessun campo comparabile → `weak`.
- campi Discogs → `weak`.

Integrazione: `resolve` emette i 3 gradi; contatori a 3 bucket; `accept-strong` accetta solo `strong` (+ tollera legacy `high`). I ~322 test esistenti restano verdi (aggiornare quelli che asseriscono `"high"`/`"text"`); `filterwarnings = error` a posto (difflib è stdlib).

---

# Parte 2 — Controllo integrità file (badfiles)

## Contesto e problema

Oggi [`inspector.py`](../../../backend/app/services/inspector.py) fa solo check statici sui tag (bitrate basso, durata sospetta): **non apre mai il file** per verificarne l'integrità. Per un tool che prepara le tracce *prima del set*, un FLAC troncato o un MP3 corrotto scoperto sul CDJ a metà serata è il rischio classico. Aggiungiamo un controllo di integrità sul contenuto audio, sul modello del plugin `badfiles` di beets.

## Scope e decisioni

- **Rilevamento con ffmpeg** (già installato; `flac`/`mp3val` no). Decode completo → cattura anche la corruzione a metà file (non solo header). Un solo tool per tutti i formati (MP3/FLAC/WAV/AIFF).
- **Job on-demand + cache incrementale** (non dentro lo scan: la decodifica è troppo cara per legarla a ogni scan).
- **Corrotto → quarantena** riusando la macchina esistente `removals` → `DELETE` → quarantena + undo journal.
- Fuori scope: check strutturale leggero (mutagen) e tool per-formato alla beets.

## Sezione 1 — Rilevamento (adapter I/O)

Nuovo adapter `backend/app/integrations/integrity.py`:

```python
def check_file(path: str) -> IntegrityResult   # (ok: bool, detail: str | None)
```

- Comando: `ffmpeg -v error -xerror -i <path> -f null -` → decodifica l'intero stream, errori su stderr.
- `ok = (returncode == 0 and stderr vuoto)`; se non ok, `detail` = primi ~200 char di stderr.
- **Timeout per file** (es. 60s) → `ok=False`, detail `"timeout"`.
- **Degrada pulito:** `ffmpeg` assente dal PATH (`shutil.which`) → adapter "non disponibile", job/bottone inattivi, nessun crash.

## Sezione 2 — Quando gira + modello dati

- `services/integrity.py` (orchestrazione, checker **iniettabile** → testabile senza ffmpeg): itera i file `present`, **salta gli invariati** già controllati (`integrity_checked_hash == content_hash`), chiama il checker, salva il risultato; opzione `force` per ricontrollare tutto.
- `services/integrity_job.py` (job in background con barra di progresso, pattern `*_job.py`, commit per-file come il rescan).
- **3 colonne additive nullable su `AudioFile`** (gestite da `ensure_schema`, **nessuna migrazione**): `integrity_ok: bool|None` (None = mai controllato), `integrity_checked_hash: str|None`, `integrity_detail: str|None`.
- Endpoint `POST /api/issues/integrity-check` che lancia il job; incrementale di default, `force` opzionale.

## Sezione 3 — Corrotto → Issue → quarantena

- `inspector.py`: se `f.integrity_ok is False` → emette Issue **`corrupt_file`** (severity `error`), `detail` = `integrity_detail`, `suggested_fix_json = {"action": "quarantine"}`. Idempotente, nasce dal campo salvato; file con `integrity_ok = None` non generano issue.
- **Azione:** l'utente **accetta** l'issue (o la dismette). Le accettate confluiscono nei `removals`: in [`planning.py`](../../../backend/app/services/planning.py) il set diventa `duplicati ∪ {file_id delle corrupt_file accettate}` → op `DELETE` → **quarantena** con la macchina esistente ([`apply.py`](../../../backend/app/services/apply.py) via `fsops.quarantine_path_for`). Reversibile via undo journal.
- Principio di sicurezza rispettato: **niente esce da Library senza Plan approvato + Apply**.

## Sezione 4 — Riorganizzazione UI (toggle Arricchisci/Manutenzione)

In cima alla zona "ENRICH PROPOSALS" ([`app/issues/page.tsx`](../../../frontend/app/issues/page.tsx)) un **segmented control a due stati**, default `Arricchisci` a ogni visita (nessuno stato memorizzato):

- **`Arricchisci`** (default): `FETCH ARTIST/TITLE WITH AI`, `FETCH GENRE WITH AI`, `IMPORT MISSING METADATA FROM PROVIDER`.
- **`Manutenzione`**: `FETCH COVERS`, `DETECT STAR RATINGS`, il nuovo **`CONTROLLA INTEGRITÀ`**, e la sezione `FORCE PROVIDER LOOKUP`.

Il nuovo bottone porta un tag `FFMPEG` e una riga guida (*"Decodifica ogni file con ffmpeg per trovare i corrotti/troncati — i corrotti si propongono per la quarantena."*). Se ffmpeg manca → **inattivo** con nota esplicativa.

**Tabella Issues:** l'issue `corrupt_file` compare come severity `error` (incrementa il contatore `err`), nella colonna FIX mostra **"→ quarantena"** invece di un valore, e ✓ la accetta. **Niente bulk-accept per i corrotti** (non entra in "ACCEPT ALL FIXABLE" né in un nuovo bottone di massa): si revisiona uno per uno.

## Testing (Parte 2)

Test **ermetici, senza richiedere ffmpeg** (CI potrebbe non averlo): orchestrazione con checker iniettato; parsing dell'adapter testato con output ffmpeg finti.

- `tests/test_integrity.py`: salto incrementale (`checked_hash == content_hash` → skip; hash cambiato → ricontrolla); `force` ricontrolla tutto; scrive `integrity_ok`/`detail`; processa solo `present`.
- adapter: parsing di output canonici (valido → ok; "Invalid data found"/exit≠0 → corrotto; timeout → corrotto).
- inspector: `integrity_ok is False` → `corrupt_file` (error, action quarantine); `None` → nessuna issue.
- planning/apply: `corrupt_file` accettata → file nei `removals` → `DELETE` → quarantena (riusa i test quarantena esistenti).
- degradazione: ffmpeg assente → job inattivo.
- ~322 test esistenti verdi (colonne additive via `ensure_schema`); `filterwarnings = error` a posto.

---

## Log delle decisioni

**Parte 1**
1. Solo distanza pesata, **niente gap-guard** — layer MusicBrainz intatto, solo candidato migliore.
2. **3 gradi visibili** `strong`/`medium`/`weak`.
3. Identità certa (MBID/ISRC) → `strong`, bypassa la distanza.
4. `difflib` stdlib, niente nuove dipendenze.
5. Soglie hardcoded e provvisorie, calibrate via test; niente Settings (v1).
6. Nessuna migrazione DB; retrocompatibilità a lettura, auto-guarigione al rescan.
7. Bulk-accept ancorata a `strong`; rotta `/accept-strong`, tollera legacy `high`.

**Parte 2**
8. Rilevamento **ffmpeg** (già installato), decode completo; no mutagen-light, no flac/mp3val.
9. **Job on-demand** + cache incrementale su `content_hash`; non dentro lo scan.
10. Corrotto → `corrupt_file` (error) → accettazione → `removals` → **quarantena** (macchina esistente).
11. UI: toggle **`Arricchisci` ↔ `Manutenzione`**, default `Arricchisci`, non persistente; badfiles nel gruppo Manutenzione.
12. **Nessun bulk-accept** per i corrotti (revisione uno-a-uno).
13. ffmpeg dipendenza **opzionale** (degrada pulito), documentata in `DEPENDENCIES.md`.
