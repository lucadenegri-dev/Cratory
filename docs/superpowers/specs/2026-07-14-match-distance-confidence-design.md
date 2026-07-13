# Confidenza graduata via distanza pesata — design

**Data:** 2026-07-14
**Stato:** approvato (brainstorming) → pronto per il piano di implementazione
**Ispirazione:** motore di matching di *beets* (`beets/autotag/distance.py`), adattato al modello per-traccia di Sortory.

## Contesto e problema

Oggi la confidenza di un suggerimento provider è **binaria** ([`text_providers.py:36`](../../../backend/app/services/text_providers.py)):

```python
conf = "high" if (mb_res.get("confidence") or 0) >= 95 else "text"
```

cioè si fida dello `score` opaco restituito dalla search di MusicBrainz e applica una soglia secca. Conseguenza: **tutti** i match testuali finiscono nel bucket `text` ("rivedi tutto"), senza distinguere un match testuale che concorda benissimo coi tag del file da uno che diverge molto.

Vogliamo una confidenza **graduata** su 3 livelli, calcolata da un confronto vero campo-per-campo, così da:

- dare un segnale più fine nella pagina Issues (badge a 3 stati, ordinabile/filtrabile);
- restringere il rumore del bucket "rivedi tutto";
- mantenere l'azione di massa "accetta i sicuri" ancorata al grado più affidabile.

Non è nato da un'esigenza specifica: è un miglioramento di solidità della feature esistente.

## Scope

**In scope.** Sostituire la stringa `confidence` prodotta da `text_providers.resolve` con un grado calcolato localmente su tre valori: `strong` / `medium` / `weak`. Adeguare i consumatori (contatori rescan, endpoint accept di massa, badge UI, i18n).

**Fuori scope (deciso in brainstorming).**

- **Nessun gap-guard.** Non si recuperano i top-N candidati da MusicBrainz per misurare l'ambiguità tra il 1° e il 2°. Si continua a usare il **solo candidato migliore** che `_best_recording` già restituisce. Il layer di integrazione MusicBrainz **non si tocca**.
- Nessuna nuova dipendenza (si usa `difflib` della stdlib, non `jellyfish`).
- Nessuna migrazione del DB (retrocompatibilità gestita a lettura).
- Nessun cambiamento alla forma della pipeline: `resolve → provider_rescan → Issues → accept → PLAN` resta identica; cambia solo *quale stringa* finisce in `confidence`.

## Architettura

Nuovo modulo **puro e testabile** `backend/app/services/match_distance.py` (niente I/O, niente rete, sullo stile di `dedup.py`). API:

```python
def grade_confidence(file, canonical: dict, *, exact: bool) -> str:
    """Ritorna "strong" | "medium" | "weak"."""
```

- `file`: l'`AudioFile` con i suoi tag correnti (`artist`, `title`, `album`, `year`, `label`).
- `canonical`: i valori canonici tornati dal provider per lo stesso match (`canonical_artist`, `canonical_title`, `canonical_album`, `release_date`/`year`, `label`).
- `exact`: `True` se il match è arrivato per identità certa (MBID o ISRC).

Punto d'innesto unico: [`text_providers.resolve`](../../../backend/app/services/text_providers.py), dove la riga binaria diventa

```python
conf = grade_confidence(file, mb_res, exact=(mb_res.get("confidence") or 0) >= 95)
```

I layer restano separati: integrazione MB intatta, logica in `services/`, forma HTTP in `routers/` + `schemas.py`.

## Il modello di distanza

Due regole, in ordine.

### Regola A — Identità certa → `strong` (bypassa la distanza)

Se il match è arrivato per **MBID o ISRC** (oggi corrisponde a `mb_res["confidence"] >= 95`, impostato con `exact=True` in [`musicbrainz.py:192`](../../../backend/app/integrations/musicbrainz.py)), la confidenza è **`strong`** a prescindere dai tag del file: l'identità è certa anche se i tag sono sporchi. Questo preserva il comportamento fingerprint/ISRC odierno (era `high`).

### Regola B — Match testuale → distanza pesata → grado

Solo quando **non** c'è identità certa, si confrontano i campi che il file **già dichiara** con i canonici del candidato:

| Campo  | Peso | Note |
|--------|------|------|
| artist | 3.0  | ancora principale |
| title  | 3.0  | ancora principale |
| album  | 3.0  | contribuisce **solo se presente su entrambi**; se assente sul file → nessuna penalità |
| year   | 1.0  | idem (solo se presente su entrambi) |
| label  | 0.5  | idem (solo se presente su entrambi) |

**String-distance per campo** (stile beets, versione compatta):

1. **Normalizzazione** prima del confronto: `casefold`, rimozione di `feat.`/`ft.`/`featuring …`, rimozione dell'articolo iniziale `the`, rimozione della punteggiatura, squeeze degli spazi.
2. **Distanza** = `1 - difflib.SequenceMatcher(None, a, b).ratio()` (stdlib, **nessuna dipendenza nuova**). Valore in `[0, 1]`.

**Aggregazione.** Solo i campi *comparabili* (presenti su entrambi) partecipano. Distanza pesata normalizzata:

```
D = sum(weight_f * dist_f  for f in comparabili) / sum(weight_f for f in comparabili)
```

Se nessun campo è comparabile (caso limite: file senza artist né title), fallback a `weak`.

**Soglie → grado** (⚠️ **provvisorie**, da calibrare via TDD — il metrico è diverso da quello di beets, i suoi `0.04`/`0.25` non si trasferiscono):

| Distanza `D` | Grado |
|--------------|--------|
| `D ≤ 0.15`   | `strong` |
| `D ≤ 0.40`   | `medium` |
| `D > 0.40`   | `weak` |

Le soglie vengono fissate dai test su casi realistici (§ Testing) e sono costanti di modulo (hardcoded v1; niente Settings).

**Campi da Discogs.** Discogs riempie solo i buchi (`label`/`genre`/`year`) come gap-fill testuale, senza un candidato scorabile: quei campi restano **`weak`** come oggi. La distanza pesata governa **solo** il match MusicBrainz.

### Effetto atteso

Oggi ogni match testuale → `text`. Con il nuovo modello, un match testuale i cui canonici concordano bene coi tag del file sale a `medium`/`strong`, riducendo il bucket "rivedi tutto" e migliorando il segnale. Un match testuale che diverge molto resta `weak` (giusto: va rivisto, potrebbe essere il brano sbagliato).

## Consumatori e retrocompatibilità

### Azione di massa (accept)

[`accept_high_overrides`](../../../backend/app/routers/issues.py) oggi accetta gli override con `confidence == "high"`. Diventa **"accetta tutti gli `strong`"**: la bulk-accept resta ancorata al solo grado più sicuro (i `medium` si rivedono a mano — è il senso del grado intermedio).

- Rotta rinominata `POST /api/issues/provider-override/accept-high` → `/accept-strong` (nessun consumatore esterno: è un tool personale).
- La label utente del bottone resta invariata ("✓ Accetta tutte le alta-confidenza"); cambia solo *cosa* seleziona.
- **Tolleranza legacy:** l'endpoint accetta sia `"strong"` sia il vecchio `"high"` presente nei dati non ancora ri-scansionati.

### Contatori

`proposed_high` / `proposed_text` → `proposed_strong` / `proposed_medium` / `proposed_weak`, in:

- il dict risultato di [`provider_rescan.rescan`](../../../backend/app/services/provider_rescan.py);
- lo schema `RescanResult` in `schemas.py`;
- il tipo in `frontend/lib/api.ts`;
- la stringa `rescanNote` in `en.ts`/`it.ts` (aggiunge il terzo numero).

### Badge UI

[`issues-table.tsx`](../../../frontend/components/issues-table.tsx) passa da 2 a 3 stati con 3 colori (strong = verde, medium = ambra, weak = grigio) e 3 chiavi i18n `confStrong` / `confMedium` / `confWeak`. Il badge **mappa i valori legacy**: `high` → stile `strong`, `text` → stile `weak`.

### Retrocompatibilità dati — nessuna migrazione

Gli Issue-override già nel DB portano `high`/`text`. Invece di migrare, si rendono **tolleranti i due lettori** (badge + endpoint accept). I valori si **auto-guariscono al primo rescan**. Zero script, zero rischio.

### Da verificare in implementazione (basso rischio)

[`covers.py`](../../../backend/app/services/covers.py) usa `resolved.confidence` (l'overall): è una stringa passata avanti e dovrebbe reggere i nuovi valori, ma va controllato che non ci sia un `== "high"` nascosto lato cover.

## Testing (TDD)

Nuovo `backend/tests/test_match_distance.py`. I casi **fissano le soglie provvisorie** su dati realistici (tracce reali dell'utente):

- `exact=True` → `strong` anche con tag del file divergenti (identità certa).
- match testuale, canonici == tag file → `strong`.
- divergenza moderata → `medium`; divergenza forte → `weak`.
- normalizzazione: `The Prodigy` ≈ `Prodigy`; `Artist feat. X` ≈ `Artist` non penalizzati; punteggiatura/maiuscole ininfluenti.
- album/year/label assenti sul file → nessuna penalità (restano artist+title come ancore).
- nessun campo comparabile → `weak`.
- campi da Discogs → `weak`.

Integrazione:

- `resolve` emette i 3 gradi (non più `high`/`text`).
- i contatori `rescan` contano 3 bucket.
- `accept-strong` accetta solo `strong` **e** tollera il legacy `high`.

Regressione:

- i ~322 test esistenti restano verdi; si aggiornano quelli che asseriscono le stringhe `"high"`/`"text"` al nuovo vocabolario.
- `pytest.ini` `filterwarnings = error` resta soddisfatto (difflib è stdlib, nessun warning nuovo).

## Decisioni prese (log)

1. **Solo distanza pesata, niente gap-guard** — layer MusicBrainz intatto, si usa il solo candidato migliore.
2. **3 gradi visibili** `strong`/`medium`/`weak` (non binario invisibile).
3. **Identità certa (MBID/ISRC) → `strong`**, bypassa la distanza.
4. **`difflib` stdlib**, niente `jellyfish` / nuove dipendenze.
5. **Soglie hardcoded e provvisorie**, calibrate via test; niente esposizione in Settings (v1).
6. **Nessuna migrazione DB**; retrocompatibilità a lettura, auto-guarigione al rescan.
7. **Bulk-accept ancorata a `strong`**; rotta rinominata `/accept-strong`, tollera legacy `high`.
