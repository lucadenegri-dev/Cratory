# Versione dell'app e controllo degli aggiornamenti

Data: 2026-08-22. Stato: approvata a voce.

## Problema

Cratory non sa dire che versione è. L'unico numero è `0.9.0` in
`frontend/package.json`; il backend non ne ha nessuno, il repository non ha mai
pubblicato un tag né una release, e in Impostazioni non compare da nessuna
parte. Non esiste quindi né un "io sono la versione X" né un "l'ultima è la Y":
la domanda "ci sono aggiornamenti?" oggi non ha due termini da confrontare.

Serve in vista di Tauri: il suo updater confronta la versione dell'app con un
manifesto pubblicato, e nessuna delle due cose esiste.

## Decisioni chiave

- **Una sola fonte per la versione**: un file `VERSION` nella radice del
  repository. Backend e frontend la derivano da lì, e un test impedisce a
  `frontend/package.json` di divergere.
- **Un rilascio è un tag più una release su GitHub**, creata a mano. Oggi senza
  allegati — non esiste ancora un artefatto installabile; con Tauri gli
  artefatti finiranno nella stessa release.
- **Il bottone controlla e informa, non scarica.** Finché Cratory è un checkout
  git non c'è niente da scaricare. Lo scaricamento arriva con Tauri, che usa lo
  stesso manifesto: nulla di ciò che si costruisce ora va rifatto.
- **"Non lo so" resta distinto da "sei aggiornato".** Un controllo fallito non
  deve mai assomigliare a un esito positivo.
- **Nessun controllo automatico all'avvio.** È stato chiesto un bottone; una
  chiamata di rete silenziosa a ogni avvio non l'ha chiesta nessuno.
- **Il repository di Cratory diventa pubblico.** È la condizione perché l'API
  delle release risponda senza credenziali, ed evita di portare un token dentro
  l'app.

## Ambito

Dentro: il file `VERSION` e la sua lettura, l'esposizione della versione via
API, il confronto semantico con l'ultima release, l'endpoint di controllo, il
bottone e i tre esiti in Impostazioni.

Fuori, dichiarato: scaricare o installare alcunché, il controllo automatico
all'avvio, l'updater di Tauri (arriverà con Tauri), l'automazione del processo
di rilascio, le note di rilascio generate da sole.

Nessuna dipendenza nuova: `httpx` c'è già e il confronto di versioni è una
manciata di righe.

---

## 1. La versione

File `VERSION` nella radice, contenente `0.9.0` e nient'altro.

Il backend la legge con la stessa forma del seam dei binari, e per lo stesso
motivo:

```python
def app_version() -> str:
    """Versione dell'app. `CRATORY_VERSION` ha la precedenza sul file: in un
    bundle Tauri la radice del repository non esiste, e il packager passa il
    numero dall'ambiente."""
```

Ordine: variabile d'ambiente `CRATORY_VERSION` → file `VERSION` → `"0.0.0-dev"`
se manca (un checkout incompleto non deve far fallire l'avvio).

Esposta da `GET /api/version` → `{"version": "0.9.0"}`.

`frontend/package.json` conserva il suo campo `version` — npm lo pretende — ma
un test lo confronta con `VERSION` e fallisce se divergono. Due numeri che
raccontano cose diverse sono peggio di un numero solo.

## 2. Il rilascio

Un tag `v0.10.0` e una release su GitHub con le note, create a mano quando lo si
decide. Il tag porta la `v` iniziale per convenzione; il file `VERSION` no.
Chi confronta le due cose deve saperlo, ed è l'unico punto in cui il prefisso
conta.

Le release non hanno allegati finché non esiste un artefatto installabile.

## 3. Il controllo

`GET /api/updates/check` interroga l'API pubblica delle release di GitHub per
`lucadenegri-dev/Cratory` e confronta con la versione locale.

```python
class UpdateCheck(BaseModel):
    current: str
    latest: str | None
    update_available: bool
    url: str | None       # la pagina della release
    notes: str | None     # il corpo della release, mostrato all'utente
```

Tre esiti, e restano tre:

| Situazione | Risposta |
|---|---|
| Nessuna release più recente | `200`, `update_available: false` |
| Ce n'è una | `200`, `update_available: true` con `latest`, `url`, `notes` |
| Non è stato possibile controllare | `502`, codice `update_check_failed` |

L'ultima riga è la ragione per cui non si usa un booleano solo: una rete assente,
un rate limit o un repository ancora privato non devono somigliare a "sei
aggiornato".

**Il `404` è ambiguo, e va risolto dalla parte sicura.** GitHub risponde `404`
sia quando il repository non è raggiungibile (privato, o inesistente) sia quando
è pubblico ma non ha ancora nessuna release — e le due cose non si distinguono
dalla risposta. Sono entrambe lo stato di oggi. Trattarlo come "nessun
aggiornamento" significherebbe dire "sei aggiornato" a un'app che non ha potuto
verificare niente, che è esattamente l'errore che questa distinzione esiste per
impedire. Quindi il `404` cade nel terzo esito, col suo codice: *nessuna release
pubblicata, oppure repository non raggiungibile*. Finché non esiste la prima
release, il bottone dirà onestamente che non può stabilirlo.

Il repository interrogato è una costante del modulo (`lucadenegri-dev/Cratory`),
non una configurazione: cambiarlo è un cambio di codice, e nei test l'URL non
viene mai raggiunto davvero.

**Il confronto è semantico, non testuale.** `0.10.0` è più recente di `0.9.0`,
mentre un confronto fra stringhe direbbe il contrario — è il difetto classico di
questa funzione e va scritto un test che lo dimostri. Un tag malformato non fa
esplodere niente: vale come "nessuna release utile".

Timeout breve e nessun ritentativo: è un bottone, chi lo preme può ripremerlo.

## 4. L'interfaccia

In Impostazioni, una riga che mostra la versione in uso e un bottone
"Controlla aggiornamenti". Dopo il clic, uno dei tre esiti; quando c'è una
versione nuova, il numero, le note e il link alla release.

Le note arrivano dalla release e sono testo di GitHub, non prosa nostra: sono
l'unica eccezione alla regola per cui nessun testo user-facing nasce dal
backend, ed è la stessa eccezione già concessa alla coda del log di slskd.
Vanno mostrate come contenuto di terzi, non come messaggio dell'app.

## 5. Cosa eredita Tauri

Il file `VERSION` diventa la fonte anche per `tauri.conf.json`, invece di un
terzo numero. Le release già esistono e già contengono le note; ci si aggiungono
gli artefatti firmati. L'updater di Tauri legge un manifesto che descrive
l'ultima versione: lo si pubblica come allegato della stessa release che il
bottone già interroga.

Il seam `CRATORY_VERSION` esiste per quel momento: nel bundle non c'è nessuna
radice di repository da cui leggere un file.

## 6. Verifica

- `CRATORY_VERSION` vince sul file; senza né l'una né l'altro si ottiene il
  default e **l'avvio non fallisce**.
- **`0.10.0` risulta più recente di `0.9.0`** — il test che sorveglia il difetto
  del confronto fra stringhe.
- Versione uguale → nessun aggiornamento; tag malformato → nessun aggiornamento
  e nessuna eccezione.
- Il prefisso `v` del tag viene tolto prima del confronto.
- Errore di rete e `404` → `502` con `update_check_failed`, **mai**
  `update_available: false`.
- `frontend/package.json` e `VERSION` dicono lo stesso numero.
- Nessun test tocca la rete vera: le risposte di GitHub si simulano con
  `httpx.MockTransport`.

## 7. Una dipendenza esterna

La funzione non è collaudabile sul campo finché il repository resta privato:
l'API risponde `404` a chi non è autenticato. Si costruisce e si verifica contro
risposte simulate; la prova reale aspetta il passaggio a pubblico.

Prima di renderlo pubblico: la cronologia è stata controllata e **non contiene
segreti** — `.env` non è mai stato committato, non ci sono chiavi API, e le
stringhe lunghe che sembravano tali sono gli hash `integrity` di
`package-lock.json`. Resta una questione di privacy, non di sicurezza: **36 file
di documentazione contengono il percorso `/Users/lucadenegri/…`**, quindi nome
utente e struttura delle cartelle diventerebbero leggibili. Ripulirli è una
decisione a parte da questa funzione.
