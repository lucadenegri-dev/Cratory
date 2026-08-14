# Discovery dig — segnali di gusto + spiegazioni

Data: 2026-06-28
Stato: design approvato, pronto per il piano di implementazione.

## Obiettivo

Chiudere il punto 1 della ROADMAP ("Miglioramento Discovery") con uno slice
focalizzato sul flusso **dig** ("Scava", `discovery_dig.py`). Lo slice copre tre dei
quattro sotto-temi del punto: **qualità dei lead**, **più segnali di gusto** e
**spiegazioni**. L'**unificazione expand/dig resta esplicitamente fuori scope**
(rimane nel backlog tecnico).

## Motivazione

Oggi i due flussi Discovery sono asimmetrici:

- **Expand** (`discovery.py`, Last.fm → resolver Spotify) ha spiegazioni AI e un
  segnale-etichetta basato sulle etichette possedute.
- **Dig** (`discovery_dig.py`, Discogs genere/etichetta) produce molti lead ma:
  - la **familiarità è binaria** (`owned_artist` sì/no);
  - **ignora del tutto le etichette possedute** (`owned_labels`), che invece l'expand
    già sfrutta;
  - **non ha affinità di stile/genere** rispetto al gusto reale della libreria;
  - **non spiega il "perché"**: l'utente vede solo un numero di score.

Lo score del dig oggi premia soprattutto la rarità (novità + domanda), non davvero il
gusto. I dati necessari per migliorarlo sono **già in mano senza rete**: artisti,
etichette (`Track.label`) e generi (`Track.genre`) della libreria, più `style`/`label`
nel result Discogs.

## Vincoli (dalle regole non negoziabili del progetto)

- Motore **deterministico**, nessuna AI in questo slice.
- Nessuna nuova dipendenza esterna; nessuna nuova chiamata di rete nel dig.
- BPM/key/feature di mixing fuori scope: il dig lavora **per gusto**, non per
  compatibilità tecnica (quella resta del Set Builder).
- Le stringhe di presentazione dei chip stanno nella UI, non nel core: il backend
  emette **reason code + payload**, non testo già composto (i18n-friendly).

## Componenti

### 1. `TasteProfile` (nuovo, in `discovery_dig.py`)

Riassunto deterministico del gusto di un **riferimento** scelto, costruito da una lista
di `Track`:

- `artist_counts: dict[str, int]` — chiavi normalizzate (`_norm`), per la familiarità
  graduata.
- `owned_labels: set[str]` — etichette normalizzate (`Track.label`), per il boost
  etichetta.
- `genre_tokens: set[str]` — token normalizzati dei generi della libreria
  (`Track.genre`), per l'affinità di stile.

Costruttore: `TasteProfile.from_tracks(tracks: list[Track]) -> TasteProfile`.

Il riferimento è:

- **tutta la libreria** (default), oppure
- le **tracce di una playlist** specifica.

### 2. Separazione dedup vs affinità

Invariante da mantenere:

- **Dedup**: sempre su **tutta la libreria** (`owned_keys` via `_dedup_key`, e gli ISRC
  library-wide). Non si deve mai proporre qualcosa già posseduto, ovunque sia.
- **Affinità**: calcolata sul **`TasteProfile` del riferimento scelto**.

Queste due cose restano indipendenti: scegliere una playlist come riferimento di gusto
**non** allarga né restringe la dedup.

### 3. Scoring esteso (`_score`)

Si mantiene la forma esistente:

```
score = adv · discovery + (1 - adv) · taste + 0.2 · recency
```

dove:

- `discovery = 0.5 · novelty + 0.5 · demand` (invariato).
- `recency` (invariato).
- `taste` passa dal binario a una combinazione pesata:
  - `familiarity` graduata: da `artist_counts`, es. `min(count / FAMILIARITY_FULL_AT, 1.0)`.
  - `label_affinity`: `1.0` se `_norm(lead.label)` ∈ `owned_labels`, altrimenti `0.0`.
  - `style_affinity`: overlap tra i token di `lead.style` e `genre_tokens`
    (normalizzati). Definizione: `1.0` se c'è almeno un token in comune, altrimenti
    `0.0` (semplice e robusto; soglia graduale rimandata se servirà).
  - `taste = W_ARTIST · familiarity + W_LABEL · label_affinity + W_STYLE · style_affinity`.

Pesi iniziali (costanti dichiarate in testa al modulo, come i cap esistenti; tarabili):

```
W_ARTIST = 0.5
W_LABEL  = 0.3
W_STYLE  = 0.2   # somma = 1.0
FAMILIARITY_FULL_AT = 3   # 3+ release dell'artista nel riferimento ⇒ familiarità piena
```

`taste` resta in `[0, 1]` (pesi normalizzati a somma 1, ogni componente in `[0, 1]`).

### 4. Reason codes

Ogni `DiscoveryLead` guadagna `reasons: list[Reason]`, dove `Reason` è un dato
strutturato `code: str` + payload tipizzato. Emessi deterministicamente quando il
relativo contributo supera una soglia:

| code | quando | payload |
|---|---|---|
| `rare_wanted` | `demand` alta (soglia su `want` e rapporto want/have) | `have`, `want` |
| `deep_cut` | `have` molto basso (sotto soglia) | `have` |
| `label_followed` | `label_affinity > 0` | `label` |
| `artist_collected` | `familiarity > 0` | `artist`, `count` |
| `style_match` | `style_affinity > 0` | `style` |
| `recent` | `recency` sopra soglia | `year` |

Le soglie sono costanti dichiarate. Il backend ritorna **codice + payload**; la UI
compone la stringa del chip (testo localizzabile).

### 5. API e serializzazione

- `POST /api/discovery/dig` accetta un campo opzionale `taste_playlist_id: int | None`
  (default `None` ⇒ riferimento = tutta la libreria). Aggiunto a
  `DiscoveryDigRequest`.
- `dig(...)` accetta il riferimento di gusto (lista tracce o profilo) come parametro,
  mantenendo la firma testabile (dipendenze iniettate).
- `DiscoveryLeadOut` guadagna `reasons` (i campi a supporto — `have`, `want`, `label`,
  `style`, `year` — già esistono). `_lead_out` mappa `lead.reasons`.

### 6. UI (frontend)

- Selettore del **riferimento di gusto**: "Tutta la libreria" (default) | una playlist.
- Rendering dei **chip** per lead a partire dai reason code + payload.
- Nessun cambiamento ai due modi di seme esistenti (Genere | Etichetta) né ai preset
  Familiare/Bilanciato/Avventuroso.

## Test

Il dig è già deterministico con `search_releases` iniettata. Nuovi test:

- il boost etichetta posseduta cambia l'ordinamento dei lead;
- l'affinità di stile cambia l'ordinamento;
- la familiarità graduata (1 vs 3+ release) pesa diversamente;
- i reason code vengono emessi esattamente quando le soglie sono superate (e non
  altrimenti), con il payload corretto;
- riferimento di gusto = playlist vs = libreria producono profili/ranking diversi;
- la **dedup resta library-wide** anche quando il riferimento è una playlist (un lead
  già posseduto fuori dalla playlist viene comunque scartato).

## Fuori scope

- Unificazione expand/dig (backlog).
- Last.fm tag come 2ª sorgente del dig e tracklist per-release (backlog).
- Spiegazioni AI nel dig (restano deterministiche).
- Affinità rispetto a etichetta/genere come riferimento separato: ridondante col seme
  del dig e coi segnali label/style già aggiunti.

## Decisioni consolidate

- Default riferimento di gusto = tutta la libreria.
- Pesi taste iniziali fissati (W_ARTIST 0.5 / W_LABEL 0.3 / W_STYLE 0.2), tarabili.
- Dedup sempre library-wide, indipendente dal riferimento di gusto.
- Reason code + payload dal backend; testo dei chip nella UI.
