# Pipeline di orientamento — design

**Data:** 2026-07-02
**Stato:** approvato

## Problema

Cratory è funzionalmente completo ma non racconta il proprio flusso d'uso: le 8 voci
di menu sono piatte e sullo stesso piano, non si capisce cosa viene prima e cosa dopo,
e il ciclo che attraversa le altre app (inbox → DJPlayer → DjOrganizer → re-index) è
invisibile dall'interno di Cratory. La confusione riguarda sia il primo avvio sia
l'uso quotidiano ("da dove riprendo?"). L'uso reale è misto: un flusso di fondo
continuo (discovery, download) più momenti-obiettivo (preparare un set).

La card "Prossimo passo" in dashboard è un embrione di soluzione: un solo suggerimento
puntuale, che non sa nulla di inbox, download attivi o indicizzazione.

## Soluzione (approcci A+B, niente wizard)

Due livelli complementari:

- **Stato** → una pipeline visibile in dashboard: "cosa c'è da fare ora, e dove".
- **Narrazione** → il menu raggruppato per fasi: "com'è fatto il flusso".

I flussi guidati/wizard (approccio C) sono esclusi: combattono l'uso misto e il
Set Builder copre già il momento-obiettivo.

## 1. Pipeline in dashboard

Striscia orizzontale in cima alla dashboard, sopra le statistiche attuali: sei fasi
cliccabili, ognuna con un numero vivo. Le fasi con lavoro pendente si "accendono"
(accento visivo); le altre restano quiete.

| Fase | Numero mostrato | Fonte dato | Click |
|---|---|---|---|
| Scopri | playlist importate | stats esistente | `/playlists` |
| Arricchisci | tracce senza BPM/key | stats esistente | `/library` filtrata |
| Acquisisci | wishlist senza file + download attivi | stats + `/downloads/status` | `/downloads` |
| Organizza ⤴ | file audio in `inbox/` | **nuovo**: conteggio di `SLSKD_DOWNLOAD_DIR` | pannello con path e link "Apri DjOrganizer" |
| Indicizza | data ultima scansione + disallineamento | **nuovo**: persistenza + confronto disco/DB | bottone "Scansiona ora" → `POST /api/library/index` |
| Suona | tracce pronte per set | stats esistente | `/set-builder` |

**Organizza** è marcata visivamente come fase esterna (sottotitolo "DJPlayer →
DjOrganizer"): il passaggio tra app diventa un gradino visibile con un numero sopra.
Il link usa un nuovo setting opzionale `organizer_url` (vuoto = link non mostrato).

**Euristica di accensione** — deterministica, niente magia:

- Fasi con conteggio: si accendono se il conteggio pendente è > 0.
- **Indicizza**: l'endpoint conta i file audio sotto `LIBRARY_ROOT` (walk senza
  hashing, veloce) e confronta con `with_local_file` nel DB; se divergono, la fase
  si accende ("il disco è cambiato, riscansiona"). Si accende anche se non è mai
  stata eseguita una scansione.

**Persistenza**: nuova mini-tabella chiave-valore `app_state` per `last_index_at`
(oggi lo stato del job di indicizzazione è solo in memoria e si perde al riavvio).

**API**: nuovo `GET /api/pipeline` che restituisce tutto in una chiamata:
`inbox_files`, `files_on_disk`, `last_index_at`, download attivi, più i conteggi
già esposti da stats necessari alle fasi. Se `SLSKD_DOWNLOAD_DIR` o `LIBRARY_ROOT`
non sono configurati, i campi relativi sono `null` e la fase corrispondente appare
neutra (non accesa, non in errore).

## 2. Menu raggruppato per fasi

Le voci restano le stesse; il menu racconta la sequenza con intestazioni non
cliccabili:

- **Dashboard** (fuori gruppo, in cima)
- **SCOPRI** — Playlist · Discovery · Shazam · Etichette
- **COLLEZIONA** — Libreria · Download
- **SUONA** — Set

Su mobile (lista orizzontale scrollabile) i gruppi diventano separatori sottili,
stesso ordine. Impostazioni resta in fondo com'è.

## 3. "Prossimo passo" potenziato

`recommend()` in `frontend/app/page.tsx` riceve anche i dati della pipeline e la
priorità diventa (dal più a valle al più a monte):

1. File in inbox → "N file aspettano di essere organizzati: apri DjOrganizer"
2. Disallineamento disco/DB → "La Libreria è cambiata: lancia una scansione"
3. Tracce senza key (< 60%) → arricchisci (come oggi)
4. Tracce pronte per set → Set Builder (come oggi)
5. Altrimenti → Discovery (come oggi)

L'empty state attuale (nessuna traccia → importa una playlist) resta invariato.

## 4. Fuori scope

- Niente wizard, sessioni guidate o tour di onboarding.
- Nessuna modifica a DjOrganizer o DJPlayer.
- Nessuna chiamata da Cratory verso DjOrganizer: solo conteggi su disco + un link.
  Il bridge esistente resta com'è (è DjOrganizer che interroga Cratory).

## Test

Unit test backend per `GET /api/pipeline`: conteggio inbox (dir mancante/vuota/con
file non-audio), euristica di disallineamento disco/DB, persistenza `app_state` di
`last_index_at` attraverso una scansione. Sui pattern dei test esistenti (348 verdi).
