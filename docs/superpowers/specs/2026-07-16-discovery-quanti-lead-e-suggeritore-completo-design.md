# Discovery — quanti lead vedere, suggeritore completo, gusto senza manopola

Data: 2026-07-16
Stato: design approvato, pronto per il piano di implementazione.
Segue: `2026-07-16-discovery-dig-motore-design.md` e `2026-07-16-discovery-riga-di-scavo-design.md`,
già implementate sul branch `feat/discovery-dig-riprogettato`.

## Obiettivo

Tre correzioni emerse **usando** il dig ridisegnato, tutte misurate:

1. Vedi sempre e solo 80 lead su 240 e non lo sai.
2. Il suggeritore si ferma a 12 voci su 319.
3. Il selettore del gusto azzera l'ordinamento in silenzio su 7 playlist su 10.

Ognuna **toglie** un parametro o un tetto invece di aggiungere una manopola.

## 1. Quanti lead vedere

### La diagnosi

`DEFAULT_DIG_LIMIT = 80` è un tetto duro. L'imbuto misurato su `style=Acid House`, depth 0:

```
  300  release scaricate (3 pagine)
 -24   titolo non parsabile, Various, compilation/DJ mix
 -29   duplicati e varianti della stessa incisione
  -3   già in libreria
 ────
  244  lead validi
   -4  persi per il cap di 2 dischi per artista
 ────
  240  candidati
   80  mostrati            ← 160 buttati, e nulla lo dice
```

I 160 scartati sono la coda meno affine (`_select` ordina per gusto **prima** di troncare),
quindi il taglio non è casuale. Ma è invisibile, e l'utente non può spostarlo.

**La spec del motore sbagliava su questo**, e la correzione va registrata: diceva che
esporre `limit` era fuori scope perché *«con `_MAX_PER_ARTIST = 2` e un budget di 300
release a monte, il default 80 non viene quasi mai raggiunto»*. Vero del bacino **vecchio**,
dove il rumore falcidiava i candidati e ne restavano 30-60. Il bacino nuovo è ordinato per
domanda ed è pulito: su 300 release ne sopravvivono 244, e **il tetto morde a ogni dig**.
Aggiustare il bacino ha reso vincolante un tetto dichiarato irrilevante.

### Il design: `limit` esce dall'API

Non si espone: si toglie. Tre ragioni:

- **Non può fare il suo lavoro**: `limit: int = Field(default=80, ge=1, le=200)` ha un
  massimo di 200 e i candidati sono 240. Oggi l'API **non può** restituirli tutti.
- **La finestra è già il limite**: 3 pagine × 100 = 300 release grezze, quindi ≤300 lead
  per costruzione. Un secondo tetto non protegge da niente.
- **Il taglio non è un parametro del dig**: è una lente sui risultati già scaricati, come
  formato e ordinamento. Metterlo nella richiesta significherebbe rilanciare la ricerca
  (4-5 richieste a Discogs) per una cosa che si fa in memoria.

Payload: 240 lead ≈ **142 KB** (misurato: 604 B/lead). Su uno strumento locale è nulla.

- `DiscoveryDigRequest.limit` **rimosso**. `dig(..., limit=...)` e `DEFAULT_DIG_LIMIT`
  rimossi. `_select` conserva il cap per artista e **smette di troncare**.
- `_select(leads)` perde il parametro `limit`: la firma dice il vero.

### Il design: la lente in UI

Nella riga della risposta, accanto a formato e ordinamento:

```
 80 di 240   MOSTRA ▪40 ▹80 ▹tutti   FORMATO ...   ORDINE ...
```

- `SegmentedControl` a tre voci: `40` / `80` (default) / `tutti`. Stato **locale**, fuori
  dall'URL: è una lente, non un parametro del dig — metterlo nell'URL rilancerebbe il
  `useEffect` su `paramsKey` e rifarebbe la chiamata a Discogs.
- Il default resta 80: la pagina non parte pesante e il comportamento non cambia sotto i
  piedi.
- **Il conteggio diventa "80 di 240"** quando il taglio morde, "240 lead" quando mostra
  tutto. È la parte che informa: oggi l'utente non sa che esistono altri 160.
- Il taglio si applica **dopo** il filtro di formato: "80 di 240" conta i lead che hanno
  passato il formato, non quelli scaricati. Altrimenti con un formato selezionato i numeri
  mentirebbero.
- `.tnum` su entrambi i numeri (The Tabular Rule).

## 2. Il suggeritore scorre tutto

### La diagnosi

`Combobox` ha `cap = 12` e fa `hit.slice(0, cap)`. Ma la lista ha già
`max-h-64 overflow-y-auto`: **scorre di suo**. Il tetto la contraddice.

Il `cap` è un residuo dell'epoca delle chip, quando `CHIP_CAP = 12` e i bottoni "+N altre"
servivano perché non c'era niente da scorrere. Con una listbox scrollabile è solo un blocco.

Le voci vere: **319** — 66 generi di libreria, 228 etichette, 25 stili curati.

### Il design

- **`cap` rimosso** dal `Combobox` (parametro e `slice`). La lista scorre.
- **`scrollIntoView` sull'opzione attiva**, ed è obbligatorio, non un extra: oggi non c'è
  (verificato: zero occorrenze), e con 12 voci in una box da 256px se ne vedono ~7 — quindi
  la freccia giù porta già l'evidenziazione fuori schermo. Con 319 voci diventerebbe
  navigazione cieca. **Togliere il cap senza questo peggiora un difetto esistente.**
  - `block: "nearest"`: porta in vista senza saltare la lista quando l'opzione è già
    visibile.
  - **Va chiamato dentro `onKeyDown`**, sul nuovo indice appena calcolato — non in un
    `useEffect` su `active`. Ragione: `active` cambia anche col mouse (`onMouseEnter`), e
    lì lo scroll non deve scattare — l'utente sta già guardando l'opzione che tocca, e
    farle saltare la lista sotto il cursore è peggio del difetto che si cura. Legarlo al
    `keydown` limita lo scroll all'unico caso in cui serve, senza dover distinguere
    l'origine del cambio dentro un effect.
- Nessun cambiamento a `DiscoveryDigBar`: compone già tutte e 319 le opzioni e le passa
  ordinate (generi di libreria → etichette → stili curati). Il `Combobox` filtra soltanto.
- Performance: 319 `<li>` nel DOM quando il campo è vuoto. Trascurabile; nessuna
  virtualizzazione (YAGNI, e sarebbe una dipendenza nuova).

## 3. Il gusto perde la manopola, tiene il segnale

### La diagnosi

Misurato sullo stesso dig, contando i lead che il gusto **non aggancia** (punteggio 0):

| riferimento | lead a punteggio 0 | primi cinque |
|---|---|---|
| Tutta la libreria (default) | **0 / 80** | Orbital, Daft Punk, Blawan, Daft Punk, Luke Vibert |
| Spotify Likes (105 tracce) | **0 / 80** | Orbital, Luke Vibert, Bobby Konders, Phuture, Wink |
| Wallis b2b Blawan (10 tracce) | **80 / 80** | Dream 2 Science, Bobby Konders, Phuture, Wink, UR |

Il segnale **funziona**: con la libreria intera ordina tutto, e cambiando riferimento
l'ordine cambia davvero. È **il controllo** a essere fragile: con una playlist magra il
gusto si spegne del tutto e la lista ricade sull'ordine della pila — senza che nulla lo
dica.

Perché: il profilo sono tre segnali (artisti, etichette, generi) e **etichetta e genere
arrivano dai tag dei file**, che esistono solo sulle tracce possedute. Una playlist di lead
da streaming è un profilo quasi vuoto **per costruzione**. Sulle 10 playlist dell'utente:

| | tracce | artisti con ≥3 | etichette | generi |
|---|---|---|---|---|
| Spotify Likes | 105 | 8 | 63 | 33 |
| muoviti senza aprire gli occhi | 88 | 4 | 60 | 28 |
| **Wallis b2b Blawan** | 10 | 0 | **0** | **0** |
| **Scoperte** | 14 | 1 | **0** | **0** |
| Tutta la libreria | 465 | 30 | 228 | 66 |

Due playlist su dieci hanno **zero etichette e zero generi**: due dei tre segnali non
esistono. Solo due o tre sono abbastanza dense da ordinare qualcosa.

### Il design

Il gusto resta **sempre acceso su tutta la libreria**. Sparisce il controllo:

- `DiscoveryDigBar`: via il `Select` del gusto, la sua label, il suo hint, e le prop
  `tasteRef`/`onTasteRefChange`. `options.playlists` non serve più.
- `page.tsx`: via lo stato `tasteRef`, il parametro d'URL `taste`, e la chiamata a
  `listImportedPlaylists()` se non serve ad altro (**verificare**, non assumere).
- API: `DiscoveryDigRequest.taste_playlist_id` rimosso; il router smette di caricare
  `tracks_for_playlist`.
- Servizio: `dig(..., taste_tracks=...)` rimosso. Il profilo si costruisce sempre da
  `library`, che è già il parametro iniettato dai test. Sparisce anche la distinzione tra
  "riferimento del gusto" e "libreria per il possesso": ora sono la stessa cosa, e il
  codice lo dice.
- i18n: `affinityLabel`, `affinityHint`, `wholeLibraryOption` diventano chiavi morte →
  rimosse da `it.ts` e `en.ts`.

La riga scende a **due zone più l'azione**:

```
 SCAVA [ ⌗ Trax Records                    ]  PROFONDITÀ ▪superficie ▹metà ▹fondo   (SCAVA)
```

**Cosa si perde, dichiarato**: con "Spotify Likes" il riferimento riordinava davvero
(Bobby Konders e Phuture salivano). Quel caso sparisce. È accettabile perché funziona su 2-3
playlist su 10 e sulle altre mente; se lo si rimette, va rimesso con un avviso quando il
profilo è troppo magro per ordinare — cioè come **feature progettata**, non come manopola
che tace.

## Fuori scope

- **L'artista come terzo seme** (`seed_type="artist"`). Verificato che Discogs lo supporta
  (`artist=Blawan` → 65 release, ordinabile per `want`), e che le pile degli artisti sono
  corte (Blawan 65 = 1 pagina, Orbital 1.114 = 12), quindi la profondità sarebbe quasi
  sempre inerte e il messaggio "pila corta: tutta qui" scatterebbe corretto. **Rimandato su
  richiesta del committente**, da riprendere dopo l'uso sul campo.
  - Nota per quando si riprenderà: va insieme alla **catena di sonde `style → genre →
    artist`**. Oggi il testo libero è trattato come genere, quindi digitare "Autechre"
    darebbe *«Discogs non conosce questo seme»* — falso, Discogs ne ha oltre mille release.
    Aggiungere l'artista senza la catena renderebbe bugiardo il messaggio onesto appena
    costruito.
- `style_match`/`W_STYLE` costanti sul seme `genre` (follow-up di punta già registrato).
- `Combobox`: id DOM cablati (`useId()`), già nei follow-up.

## Test

**Backend**
- `_select(leads)` non tronca: 240 candidati → 240 lead. Il cap per artista resta.
- `dig()` non accetta più `limit` né `taste_tracks`; il profilo viene da `library`.
- `DiscoveryDigRequest` rifiuta `limit` e `taste_playlist_id` (campi sconosciuti) — oppure
  li ignora, a seconda della config Pydantic del progetto: **verificare il comportamento
  reale e testare quello**, non quello atteso.
- I test esistenti che passano `limit=`/`taste_playlist_id=` vanno riscritti
  semanticamente, non solo ripuliti: se un test asserisce il troncamento, ora asserisce
  che **non** avviene.

**Frontend**
- `Combobox`: con 319 opzioni e campo vuoto le rende tutte (nessun `slice`); `ArrowDown`
  oltre l'area visibile chiama `scrollIntoView` sull'opzione attiva; `onMouseEnter` **non**
  lo chiama.
- Riga della risposta: `MOSTRA 40` con 240 lead → 40 card e conteggio "40 di 240";
  `MOSTRA tutti` → 240 card e conteggio "240 lead"; con un formato selezionato il "di N"
  conta i lead **dopo** il filtro.
- `DiscoveryDigBar`: il controllo del gusto non esiste più (test di regressione: la
  presenza di playlist non fa comparire nulla).
