# Discovery dig — il motore: pescare dove c'è pesce

Data: 2026-07-16
Stato: design approvato, pronto per il piano di implementazione.
Precede: `2026-07-16-discovery-riga-di-scavo-design.md` (la UI, da rivedere dopo questo).

## Obiettivo

Rendere il dig capace di fare ciò che promette: **trovare musica che piace all'utente e
che non ha**. Oggi fa parzialmente la seconda metà e sostanzialmente fallisce la prima.

## La diagnosi, con i numeri

Misurati contro l'API Discogs reale su `style=Acid House` (43.345 release).

### 1. Il bacino è un campione arbitrario dello 0,69%

`search_releases` non passa **nessun parametro `sort`** (`integrations/discogs.py:56-101`).
Con una query a soli filtri e senza termine di ricerca, l'ordine di default non è
"le migliori": è arbitrario. Il dig ne scarica 300 (`SEARCH_PER_PAGE=100` ×
`SEARCH_MAX_PAGES=3`) e ordina quelle.

Il bacino reale che riceve il codice oggi:

| misura | valore |
|---|---|
| release raggiungibili | 300 / 43.345 = **0,69%** |
| release con `have > 1000` | **0 / 300** |
| release con `have ≤ 5` | 138 / 300 = **46%** |
| `have` mediano | 8 |
| `want` mediano | 28 |

Underground Resistance, Bobby Konders, Armando, Adonis, Fast Eddie, Josh Wink, Dream 2
Science: **nessuno raggiungibile**. L'unico "Acid Tracks" nel bacino è *DJ Nerdiboy —
Acid Tracks 001*, non il disco dei Phuture che ha inventato il genere.

Con `sort=want&sort_order=desc` la prima pagina è il canone: Dream 2 Science, Bobby
Konders, Phuture — Acid Tracks, Josh Wink, Underground Resistance. (`sort=have` dà invece
Daft Punk e Jamiroquai: mainstream, non è ciò che serve.)

### 2. Il punteggio è tarato per un bacino che la query non consegna

`_HAVE_CAP = 5000` e `REASON_DEEP_CUT_MAX_HAVE = 50` hanno senso contro una pila ordinata
per domanda (`have` da ~6.000 in cima a ~100 in fondo). Contro il bacino reale, dove il
`have` mediano è 8, non significano nulla:

- **`novelty` è una costante**: mediana 0,997, escursione **0,161 sull'intera pagina**.
  `discovery = 0.5*novelty + 0.5*demand` (`discovery_dig.py:247-249`) è di fatto solo
  `demand`.
- **`deep_cut` scatta sul 63% dei lead**. Un badge su due terzi della lista non informa.

### 3. Il gusto non tocca mai la query

Non esiste percorso dalla libreria a ciò che si chiede a Discogs. `TasteProfile` riordina
un campione estratto senza riguardo per l'utente: "musica che ti piace" significa oggi
*di questi 300 dischi presi a caso, i meno lontani dal tuo gusto*.

Tre dei quattro segnali di gusto sono quasi costanti in condizioni reali:

- **`style_affinity`** (`:180-181`) fa match su **un solo token condiviso**: `Deep House`
  → `{deep, house}`. Per un DJ house, `house` è in libreria → vale 1.0 per quasi tutto.
  `W_STYLE = 0.2` è peso morto. In più usa solo `_first(item.get("style"))`, ignorando
  gli altri style della release.
- **`label_affinity`** (`:177-178`) su un dig per etichetta vale 1.0 per **tutti** i lead
  per costruzione (condividono l'etichetta del seme) → `W_LABEL = 0.3` è una costante.
- **`familiarity`** (`:174-175`) è l'unico che discrimina, ma **su il 17% dei lead non
  può funzionare** (vedi sotto).

### 4. La normalizzazione ignora la grammatica di Discogs

`_norm` è `strip().lower()` (`services/discovery.py:98`). Discogs disambigua gli omonimi
con suffissi: `Tyree*`, `Gravity Zero (4)`. E mette più artisti in un campo:
`Nail* / Einzelkind`, `OPTML, Gravity Zero (4) & RADD (3)`.

Misurato su 87 lead superstiti dai filtri anti-rumore:

| problema | quota |
|---|---|
| artisti con cruft (`*` o `(N)`) | 13% |
| campi con più artisti (`/`, `&`, `,`) | 8% |
| **lead il cui artista non può matchare la libreria** | **17%** |

`W_ARTIST = 0.5` è metà del gusto: su quei lead il gusto nasce dimezzato. E la stessa
`_norm` alimenta `owned_keys` (`:311`): un disco di `Tyree*` che **possiedi** non viene
riconosciuto e ti viene riproposto.

### 5. Il possesso confronta titoli di release con titoli di traccia

`owned_keys` (`:311`) confronta il titolo della release Discogs con `Track.title`, che è
un titolo di traccia. Sono cose diverse: il 9% dei titoli nel bacino è un nome di EP
(`Piercing Love EP`), il 2% sono due tracce in un campo (`Sentipede / 808 Rhythm Traxx
3`). Funziona per i 12" in cui la release prende il nome del lato A, cioè per caso.
`Track.album` esiste (`models.py:80`) e non viene usato.

### 6. Il bonus recency è una spinta occulta verso il nuovo

`+ 0.2 * recency` (`:256`) è **fuori** dalla combinazione convessa: c'è sempre, a
qualunque `adventurousness`, e vale fino al 17% del punteggio massimo. Un disco senza
anno su Discogs prende 0. In uno strumento di crate digging è un bias sistematico contro
i dischi vecchi.

## Il ribaltamento

Il motore impasta due domande diverse in un unico numero:

1. **Dove pescare** — in che punto della pila mettere le mani.
2. **Come ordinare ciò che si è pescato** — gusto o rarità.

`adventurousness` oggi fa solo la seconda, su un mucchio raccolto a caso. Farà solo la
**prima**, e il gusto sarà **sempre acceso**.

Il gusto non deve essere una modalità: non esiste un momento in cui l'utente vuole *meno*
musica che gli piace. "Avventuroso" non significa "dammi roba che non mi piace", significa
"portami più lontano dai dischi ovvi". Sono due cose, e il codice le tratta come una.

```
  PROFONDITÀ  →  sceglie la finestra nella pila ordinata per domanda
  GUSTO       →  ordina SEMPRE dentro quella finestra
  POSSESSO    →  toglie SEMPRE ciò che si ha già
```

### La pila è buona per tutta la sua lunghezza

Misurato su `style=Acid House&sort=want&sort_order=desc`:

| pagina | rango `want` | `have` med | `want` med | `want < 5` |
|---|---|---|---|---|
| 1 | 1–100 | 1037 | 1954 | 0/100 |
| 30 | 2901–3000 | 176 | 287 | 0/100 |
| 60 | 5901–6000 | 118 | 158 | 0/100 |
| 100 | 9901–10000 | 99 | 89 | **0/100** |

**A nessuna profondità esiste un solo disco con `want < 5`.** Il rumore che oggi riempie
il bacino sta sotto il rango ~40.000, irraggiungibile. Pagina 101 → 404: il tetto di
paginazione Discogs è esattamente 10.000 release, e la profondità massima ci arriva.

Anche le etichette hanno profondità: `label=Trax Records` → 10.096 release, 100 pagine.

### Dentro una finestra la domanda è costante

Pagina 30: `want` mediano 287, **minimo 284**. Dentro una pagina il `want` non varia. Una
finestra di 3 pagine ha quindi domanda ~costante: `demand` non ordina nulla al suo interno,
la finestra la codifica già. **Il termine `discovery` sparisce, e il punteggio diventa
solo gusto.**

Questo elimina `novelty`, `_HAVE_CAP`, `_demand` dallo score e il bisogno di tararli.

## Design

### `depth` sostituisce `adventurousness`

Rinominato nel contratto API: il nome deve dire cosa fa. Float [0,1], default 0.0.
Nessun client esterno (app personale single-user).

```python
PAGES_PER_DIG = 3          # invariato: 3 richieste di contenuto per dig
DISCOGS_MAX_PAGES = 100    # tetto duro di Discogs (10.000 release); pagina 101 -> 404

def _window(depth: float, total_items: int) -> list[int]:
    """Le pagine da scaricare: depth 0 = il canone, depth 1 = il fondo della pila."""
    usable = min(math.ceil(total_items / SEARCH_PER_PAGE), DISCOGS_MAX_PAGES)
    start = 1 + round(depth * max(0, usable - PAGES_PER_DIG))
    return list(range(start, min(start + PAGES_PER_DIG - 1, usable) + 1))
```

Il `- 1` non è cosmetico: senza, la finestra è di 4 pagine e ogni dig spende una
richiesta di troppo. Verificato eseguendo la funzione, non a occhio.

Gradiente risultante su un seme grande (43.345 release → 100 pagine utili):

| `depth` | pagine | rango `want` | cosa trovi |
|---|---|---|---|
| 0.0 | 1–3 | 1–300 | i classici del genere/etichetta (che non hai) |
| 0.5 | 49–51 | 4801–5100 | `want` ~190: oscuri ma ancora cercati |
| 1.0 | 98–100 | 9701–10000 | `want` ~89: il fondo della cassa |

**Semi piccoli**: se `usable <= PAGES_PER_DIG`, la finestra è l'intera pila e `depth` non
ha effetto. È corretto e va detto in UI: su un'etichetta con 40 release non c'è profondità
da scegliere.

### La sonda

Per scegliere la finestra serve `pagination.items` **prima** di scaricare. Sonda con
`per_page=1`, poi le pagine vere: **4 richieste per dig** (oggi 3, o 6 col fallback
style→genre). Dentro il budget Discogs (~25/min senza token, ~60 col token).

`search_releases` guadagna i parametri `sort`, `sort_order`, `page`; il loop di
paginazione interno viene sostituito da una lista di pagine esplicita. Nuovo metodo
`count_releases(**filtri) -> int` per la sonda.

**Errori**: invariato nella sostanza — la sonda o la prima pagina che fallisce solleva
`DiscogsError` (il router la traduce in 502 esplicito, `routers/discovery.py:255-257`);
una pagina successiva in errore degrada ai risultati già raccolti.

### Il punteggio: solo gusto

```python
def _score(lead, profile, seed_type) -> float:
    w = _weights(seed_type)       # i segnali costanti per costruzione escono
    return (
        w.artist * profile.familiarity(lead.artist)
        + w.label * profile.label_affinity(lead.label)
        + w.style * profile.style_affinity(lead.styles)
    )
```

Niente `novelty`, niente `demand`, niente `recency`. `adventurousness` non entra più
nello score: sceglie il bacino, non l'ordine.

**Ordinamento stabile.** `sorted(..., key=score, reverse=True)` è stabile in Python: a
parità di punteggio l'ordine di inserimento — cioè **l'ordine per domanda della pila** —
è preservato. Questo dà il fallback giusto e gratuito: libreria vuota o gusto piatto → la
lista resta ordinata per desiderabilità. Va scritto come commento nel codice: è un
comportamento voluto che dipende da una garanzia del linguaggio.

### I pesi escludono i segnali costanti per costruzione

Su un dig per etichetta, `label_affinity` vale 1.0 per tutti i lead: è una costante
additiva, non ordina. Peggio, ne dilava gli altri segnali e fa comparire il badge
"etichetta che segui" su ogni card, informando zero.

```python
W_ARTIST, W_LABEL, W_STYLE = 0.5, 0.3, 0.2

def _weights(seed_type: str) -> Weights:
    """I segnali costanti per costruzione escono, e il peso si redistribuisce."""
    if seed_type == "label":
        # tutti i lead condividono l'etichetta del seme: segnale nullo
        return Weights(artist=W_ARTIST / 0.7, label=0.0, style=W_STYLE / 0.7)
    return Weights(artist=W_ARTIST, label=W_LABEL, style=W_STYLE)
```

Il seme `genre` **non** viene trattato allo stesso modo — ma non perché lo style del
seme non sia l'unico sulla release. `style_affinity` è una Jaccard **massima** su (style
della release × generi della libreria, vedi sotto), e ogni release del dig contiene lo
style del seme per costruzione (è il filtro `style=value` della ricerca Discogs): il
seme impone quindi un **pavimento uguale per tutti i lead**, e gli altri style possono
solo alzare quel max, mai abbassare il pavimento. Se la libreria ha alla lettera il
genere del seme, il pavimento è 1.0 e `style_affinity` è una costante esatta — la stessa
malattia che qui sopra si cura per `label`. **Caso noto, non ancora deciso**: è una scelta
di prodotto da misurare, non un bug silenzioso da correggere qui.

Coerentemente, il reason `label_followed` non viene emesso su un dig per etichetta.

### `style_affinity` graduata

Due difetti oggi: match su un solo token condiviso, e solo il primo style della release.

```python
@dataclass
class TasteProfile:
    artist_counts: dict[str, int]
    owned_labels: set[str]
    genre_sets: list[set[str]]        # un set di token PER genere distinto, non un'unione

    def style_affinity(self, styles: list[str]) -> float:
        """Jaccard massima tra gli style della release e i generi della libreria."""
        best = 0.0
        for s in map(_style_tokens, styles or []):
            for g in self.genre_sets:
                if s and g:
                    best = max(best, len(s & g) / len(s | g))
        return best
```

`genre_tokens` era un'**unione** di tutti i token della libreria: `{house, techno, deep,
acid, electronic, ...}`. Confrontare contro quel sacco unico è la ragione per cui bastava
`house` per valere 1.0. Confrontando contro **ogni genere distinto** e prendendo la
Jaccard massima si ottiene un valore graduato che discrimina:

- `Deep House` vs libreria che ha `Deep House` → 1.0
- `Deep House` vs libreria che ha solo `Acid House` → `{house}` / `{deep, house, acid}` = 0.33
- `Deep House` vs libreria che ha solo `Drum n Bass` → 0.0

`DiscoveryLead.style` (singolo) diventa `styles: list[str]` (tutti quelli della release).
Il DTO espone il primo per il badge in UI, come oggi: nessun cambiamento al frontend.

### Normalizzazione: la grammatica di Discogs

Pulizia **all'ingestione**, in `_lead_from_release`, non dentro `_norm`. Due ragioni:
`_norm` è condivisa con il flusso expand (Last.fm/Spotify), dove questa grammatica non
esiste; e un artista pulito serve anche alla **UI**, che oggi mostra `Tyree*` sulla card.

```python
_DISCOGS_SUFFIX_RE = re.compile(r"\s*(\*|\(\d+\))\s*$")   # Tyree* , Gravity Zero (4)
_ARTIST_SPLIT_RE = re.compile(r"\s+(?:/|&|\bfeat\.?\b|\bvs\.?\b)\s+|,\s+")

def _clean_artist(raw: str) -> tuple[str, list[str]]:
    """(stringa da mostrare, artisti atomici per il match). 'Nail* / Einzelkind' ->
    ('Nail / Einzelkind', ['nail', 'einzelkind'])."""
```

`DiscoveryLead` guadagna `artist_keys: list[str]` (normalizzati, per il match) accanto ad
`artist` (per la UI). **Non esposto nel DTO**: serve solo al motore.

`familiarity` prende la **massima** familiarità tra gli artisti atomici: su uno split
`Nail / Einzelkind`, se collezioni Einzelkind il lead è rilevante.

Il cap `_MAX_PER_ARTIST = 2` (`:284`) usa il **primo** `artist_key`: su uno split è
l'artista principale, ed è il comportamento voluto (non deve monopolizzare).

### Il possesso: release contro tracce

`owned_keys` diventa due indici distinti, costruiti una volta dalla libreria:

```python
owned_tracks = {(artist_key, dedup_title(t.title))  for t in library}
owned_albums = {(artist_key, dedup_title(t.album))  for t in library if t.album}
```

Un lead è posseduto se **una qualsiasi** delle sue chiavi candidate è in **uno dei due**
indici. Le chiavi candidate di un lead sono il prodotto dei suoi `artist_keys` per i suoi
titoli candidati:

- il titolo della release così com'è;
- ogni lato di uno split (`Sentipede / 808 Rhythm Traxx 3` → due titoli);
- il titolo senza il suffisso di formato.

```python
_FORMAT_SUFFIX_RE = re.compile(r"\s+(ep|lp|12\"|single)\s*$", re.IGNORECASE)
```

`_dedup_title` continua a togliere i suffissi di variante (`(Original Mix)`), e ora anche
quelli di formato. La ricorsione esistente (`:126-133`) gestisce già la combinazione
`Foo EP (Remastered)`.

**Falsi positivi**: un titolo di release generico (`Untitled`) potrebbe collidere con una
traccia omonima di un artista che possiedi. È accettabile: il costo è un lead in meno, non
un duplicato mostrato. L'errore opposto — riproporre un disco che hai — è quello che
stiamo correggendo, ed è quello che l'utente vede.

### I reason

Sopravvivono, con tre correzioni. Restano **badge a soglia post-hoc**, non i fattori del
punteggio: il microcopy non deve dire che spiegano la posizione.

| code | oggi | domani |
|---|---|---|
| `rare_wanted` | `want>=10` e domanda `>=0.5` | invariato |
| `deep_cut` | `have<=50` → **63% dei lead** | `have<=50` **e** `want>=5` (`REASON_DEEP_CUT_MIN_WANT`) |
| `label_followed` | sempre | **non emesso** su dig per etichetta (costante) |
| `artist_collected` | `count>0` | invariato, ma sugli `artist_keys` puliti |
| `style_match` | un token condiviso | `style_affinity >= 0.5` (soglia sulla Jaccard) |
| `recent` | `recency>=0.8` | **invariato come badge**; esce dal punteggio |

`_recency` resta, usata solo da `_reasons`.

## Contratto API

`POST /api/discovery/dig` (`schemas.py:527-543`):

- `adventurousness: float = 0.4` → **`depth: float = 0.0`**. Il default cambia significato:
  0.0 = i classici del seme. È il default giusto per chi apre Discovery la prima volta.
- Tutto il resto invariato: `seed_type`, `value`, `taste_playlist_id`, `limit`.
- `DiscoveryLeadOut` invariato (`styles` resta interno; il DTO espone `style` singolo).

`DiscoveryDigResponse` guadagna **`pile_pages: int`** — quante pagine utili ha la pila del
seme (`usable` in `_window`). Serve alla UI: se `pile_pages <= PAGES_PER_DIG` la finestra
è l'intera pila e `depth` **non ha effetto**, e l'utente deve poterlo sapere invece di
armeggiare con un controllo inerte. È l'unico modo che ha il frontend per accorgersene, e
solo **dopo** il dig: la lunghezza della pila si conosce dalla sonda, non prima. `DigResult`
lo trasporta dal servizio al router.

Il frontend passa oggi sempre il valore (`page.tsx:116`): il disallineamento del default
frontend/backend segnalato nella spec UI si estingue da sé.

## Ricaduta sulla spec della UI

`2026-07-16-discovery-riga-di-scavo-design.md` va rivista dopo l'implementazione di
questa. In particolare:

- **"Profondità" non è più una label bugiarda da rinominare**: descrive letteralmente il
  meccanismo. Le rinomine "Ordina per" / "Il mio gusto · Bilanciato · Rarità" **decadono**.
  I preset diventano profondità di pesca (`depth` 0.0 / 0.5 / 1.0) e il registro può essere
  quello del crate digging, coerente con `DESIGN.md` §"Experimental energy".
- **Il popover annidato decade**. Era la risposta a un sotto-parametro che a "Avventuroso"
  pesava il 15%. Col gusto sempre attivo, "Gusto misurato su" conta sempre: torna un pari
  grado sulla riga, non un figlio nascosto.
- Il resto della spec UI (combobox unificato genere+etichetta, blocco a due righe,
  primitive `Popover`/`Combobox`/`SegmentedControl`/`Chip`) **regge invariato**.
- Il fix `deep_cut` migra qui: va tolto da quella spec per non implementarlo due volte.

## Test

`_window` e i pesi sono pura aritmetica: test senza rete, come il resto del modulo
(`search_releases` è già iniettata, `discovery_dig.py:12`).

**`_window`**
- `depth=0.0` → `[1,2,3]`; `depth=1.0`, 100 pagine utili → `[98,99,100]`.
- **la finestra è sempre lunga `PAGES_PER_DIG`** (o meno solo se la pila è più corta):
  è l'off-by-one che rende ogni dig più caro di una richiesta.
- seme piccolo (2 pagine): qualunque `depth` → `[1,2]`.
- seme minuscolo (40 release): qualunque `depth` → `[1]`.
- seme grande: `usable` non supera mai `DISCOGS_MAX_PAGES=100` (pagina 101 → 404).
- monotonia: `depth` crescente → `start` non decrescente (`[1, 16, 49, 83, 98]` per
  `depth` `[0, .15, .5, .85, 1]` su 43.345 release).

**Normalizzazione**
- `Tyree*` → key `tyree`; `Gravity Zero (4)` → `gravity zero`.
- `Nail* / Einzelkind` → display `Nail / Einzelkind`, keys `[nail, einzelkind]`.
- `familiarity` prende la massima tra gli artisti atomici.

**Possesso**
- libreria con traccia `Tyree — Acid Crash` → lead `Tyree* — Acid Crash` **escluso**
  (regressione che stiamo correggendo).
- libreria con `album = "Piercing Love EP"` → lead `— Piercing Love EP` escluso.
- libreria con traccia `Sentipede` → lead `Sentipede / 808 Rhythm Traxx 3` escluso.
- lead non posseduto → **non** escluso (niente over-matching).

**Punteggio**
- `style_affinity`: `Deep House` vs `{Deep House}` = 1.0; vs `{Acid House}` ≈ 0.33; vs
  `{Drum n Bass}` = 0.0.
- dig per etichetta: `label` esce dai pesi; `label_followed` non emesso.
- gusto piatto (libreria vuota) → l'ordine dei lead è **identico** all'ordine della pila
  (stabilità del sort).
- l'anno di un lead non influenza più l'ordine; il badge `recent` c'è ancora.

**Regressione end-to-end** (con `search_releases` finta): stessa pila, `depth` diverse →
finestre diverse; stessa `depth`, libreria diversa → ordine diverso.

## Fuori scope

- Unificazione expand/dig (backlog, cfr. spec 2026-06-28).
- `_norm` del flusso expand: la pulizia Discogs sta all'ingestione del dig, l'expand non
  la vede.
- ~~Esporre `limit` in UI (cfr. spec UI).~~ **Superato**: `limit` viene *rimosso*, non
  esposto — vedi `2026-07-16-discovery-quanti-lead-e-suggeritore-completo-design.md`. La
  giustificazione data qui e nella spec UI («il default 80 non viene quasi mai raggiunto»)
  era vera del bacino **vecchio**, dove il rumore lasciava 30-60 candidati. Col bacino
  ordinato per domanda ne sopravvivono 244 su 300 e **il tetto morde a ogni dig**: aggiustare
  il bacino ha reso vincolante un tetto che questa spec dichiarava irrilevante.
- Cache dei risultati Discogs: 4 richieste per dig restano dentro il budget.
- Usare `q` (ricerca testuale) per portare il gusto dentro la query — es. cercare gli
  artisti che collezioni. È la naturale evoluzione ("il gusto sceglie il bacino, non solo
  l'ordine") ma moltiplica le chiamate e va progettata a parte.
