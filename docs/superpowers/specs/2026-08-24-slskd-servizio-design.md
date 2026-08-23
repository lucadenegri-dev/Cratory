# slskd è un servizio, non un componente di sistema

Data: 2026-08-24. Stato: approvata a voce.

## Problema

Nel bundle i tre componenti esterni viaggiano dentro l'app: il probe li vede
`present`, con `source: "bundle"`. Il passo *Prerequisiti* del wizard — che
esiste per farli installare — mostra a chi ha appena installato Cratory due
righe verdi su cui non c'è niente da fare.

Ma la premessa "sono integrati, quindi non serve configurarli" regge per due dei
tre. **slskd non è un binario da avere: è un servizio da configurare.** Il probe
non ne cerca l'eseguibile, gli chiede `/health`; e prima che risponda servono le
credenziali Soulseek, un file YAML scritto sul disco e un demone avviato.

Sotto, il vero disordine: **slskd è schedato due volte**, come componente di
sistema (`system_probe.REGISTRY`, con `kind: "daemon"`) e come servizio esterno
(`routers/services.py`). È l'unico che sta in entrambe le liste, e ha
un'interfaccia in ciascuna.

## La scoperta che ha cambiato il disegno

Le due interfacce sembravano duplicati. Non lo sono: sono **due metà
complementari**, e nessuna delle due sa fare il percorso intero.

| Passo | Wizard (`component-row.tsx`) | Impostazioni (`services-list.tsx`) |
|---|---|---|
| 1. scarica il binario (`startInstall`) | **solo lui** | — |
| 2. scrive la configurazione (`daemonConfig`) | **solo lui** | — |
| 3. avvia / ferma il demone | avvia | avvia, ferma, sorveglia |
| 4. collega l'app al demone (`slskdConnect`) | — | **solo lui** |

Il wizard possiede ciò che si fa una volta, Impostazioni ciò che si ripete. Per
questo la riga in Impostazioni, quando il binario manca, **rimanda al wizard**:
non è pigrizia, non sa davvero installarlo.

Togliere la riga del wizard non è quindi rimuovere un duplicato: è **unire due
metà**. Senza portarsi dietro i primi due passi, l'app perderebbe la capacità
di installare e configurare slskd.

## Decisioni chiave

- **slskd esce da `system_probe.REGISTRY`.** Non è un binario di sistema come
  ffmpeg: la sua presenza è una risposta HTTP, non un file su `PATH`.
- **Resta dov'è già**: nel manifest dei binari (l'app sa scaricarlo) e nella
  lista dei servizi. `binary_installer` valida le chiavi contro il manifest, non
  contro il registry, quindi `POST /api/setup/install/slskd` continua a
  funzionare senza modifiche.
- **Una riga sola per slskd in tutta l'app**, che copre i quattro passi e vive
  in un componente condiviso, montato sia da Impostazioni sia dal wizard.
- **Il passo Prerequisiti si salta quando non ha niente da chiedere**, cioè
  quando ogni componente è presente e viene dal bundle. Nessun flag nuovo: è il
  probe stesso a dirlo.
- **Il wizard non si svuota mai.** Anche con Prerequisiti saltato restano
  benvenuto, libreria, servizi e riepilogo: la cartella della libreria va
  indicata sempre, in ogni ambiente.

## Ambito

Dentro: la rimozione di slskd dal probe e dei rami `daemon` che ne dipendono, la
riga unificata, i due campi di stato che le servono, il salto del passo nel
bundle, i testi in due lingue, i test.

Fuori, dichiarato: il manifest dei binari, l'avvio/arresto del demone e la
scrittura dello YAML (funzionano e non si toccano — cambia solo chi li chiama);
ffmpeg e fpcalc, che restano componenti; la condivisione della libreria su
Soulseek; qualunque modifica al wizard oltre il passo Prerequisiti.

---

## 1. Il confine

In `backend/app/services/system_probe.py`: via la voce `slskd` da `REGISTRY`,
via `_probe_slskd` e via il ramo `if c.kind == "daemon"` in `_probe_one`. Il
tipo `kind` resta `Literal["system"]` — un solo valore, che è la verità: i
componenti sono binari di sistema.

Resta invariato `_richiedi_slskd_non_in_esecuzione` in `routers/setup.py`: è la
protezione contro il reinstallare sopra un demone che gira, e vale ancora.

In `frontend/components/setup/component-row.tsx` spariscono i cinque rami
`kind === "daemon"`; in `steps/prerequisites.tsx` il filtro `c.kind !== "daemon"`
diventa superfluo; in `steps/summary.tsx` sparisce `daemonKeys`; in
`lib/api/setup.ts` il tipo `kind` perde il valore `"daemon"` e `source` perde
`"daemon"`.

## 2. I due campi che mancano

`GET /api/slskd/daemon/status` risponde oggi `{reachable, owned, pid}`: dice se
il demone è raggiungibile, non a che punto è il percorso. La riga unificata ha
bisogno di sapere anche se il binario c'è e se la configurazione è scritta, e
sono due domande a cui il backend sa già rispondere altrove.

```python
class DaemonStatus(BaseModel):
    reachable: bool
    owned: bool | None
    pid: int | None = None
    installed: bool          # il binario è nella cartella gestita dall'app
    configured: bool         # il file YAML esiste
    username: str | None     # letto da `read_username`, per mostrarlo senza richiederlo
```

Additivo: nessun campo cambia significato, nessun chiamante esistente si rompe.
`installed` riusa il controllo che `slskd_daemon.start` fa già prima di
sollevare `NotInstalled`; `configured` e `username` riusano `default_config_path`
e `read_username`, entrambi già scritti.

## 3. La riga unificata

Un componente nuovo, `frontend/components/slskd-row.tsx`, che riceve lo stato e
mostra **una sola azione: quella che ha senso adesso.**

| Stato | Cosa mostra |
|---|---|
| binario assente | *Scarica slskd*, con l'avanzamento dell'installazione |
| binario presente, YAML assente | i campi delle credenziali Soulseek e *Salva configurazione* |
| configurato, demone fermo | *Avvia* |
| demone attivo, app non collegata | *Collega* |
| collegato | lo stato, *Scollega*, *Ferma* |

È la stessa sequenza che oggi attraversa due schermate, in una riga che la sa
raccontare da sé. `services-list.tsx` lo monta al posto di `SlskdExtra`; il
passo *Servizi* del wizard lo monta aggiungendo `slskd` al suo `ORDINE`. Il
rimando al wizard sparisce da `services-list.tsx`: non c'è più un wizard a cui
rimandare, e adesso la riga sa fare da sé ciò per cui ci rimandava.

Le credenziali Soulseek sono una password, non una chiave API: il campo si
comporta come gli altri campi segreti dell'app (`CredentialField`), e il valore
non torna mai indietro dal backend — `read_username` restituisce l'utente, non
la password.

## 4. Il passo che si salta

`PrerequisitesStep` non si monta quando ogni componente è `present` **e** ha
`source === "bundle"`. La decisione vive nella pagina del wizard
(`frontend/app/setup/page.tsx`), che compone `STEPS` dopo aver letto il probe:
il passo non esiste proprio, così il contatore "passo 2 di 5" resta onesto
invece di saltare da 1 a 3.

Il criterio è la ragion d'essere del passo: esiste per far installare qualcosa,
sparisce quando non c'è niente da installare. Da checkout git, dove ffmpeg
arriva da Homebrew (`source: "path"`), resta intero — e resta anche in un
bundle futuro che non includesse più uno dei due binari.

## 5. Verifica

**Backend.**

- Il probe non contiene più `slskd`: `probe_all()` restituisce due componenti, e
  nessuno ha `kind == "daemon"`.
- `POST /api/setup/install/slskd` **continua a funzionare** — è la prova che
  l'installer valida contro il manifest e non contro il registry, ed è
  esattamente ciò che tiene in piedi la riga nuova.
- `daemon/status` riporta `installed` e `configured` veri e falsi nei quattro
  casi (binario sì/no × YAML sì/no), e `username` letto dal file quando c'è.
- Nessun endpoint di slskd cambia comportamento: gli altri test esistenti
  restano verdi senza modifiche.

**Frontend.**

- La riga mostra **una sola azione per stato**, e per ognuno dei cinque stati è
  quella giusta: provata rompendo la condizione, non solo osservandola.
- Con tutti i componenti `present` e `source: "bundle"` il wizard ha quattro
  passi e non contiene *Prerequisiti*; con un `source: "path"` ne ha cinque.
- `services-list.tsx` non nomina più il wizard da nessuna parte.

**A mano, nel bundle**, perché è il caso che ha originato il lavoro: installare
la 1.0.5 da zero, aprire il wizard e verificare che i passi siano quattro e che
slskd si configuri interamente dal passo *Servizi*.

## 6. Rischi

- **Il caso "aggiornamento", non solo "prima installazione".** Chi ha già un
  `slskd.yml` scritto dalla versione precedente deve trovare la riga nello stato
  giusto, non ricominciare: è il motivo per cui `configured` legge il file vero
  invece di fidarsi di un'impostazione.
- **La riga cresce.** Cinque stati in un componente sono il limite oltre il
  quale conviene spezzarlo; se durante l'implementazione diventano sei, va
  diviso invece di aggiungere un ramo.
- **Un test che oggi passa per il motivo sbagliato.** I test che citano `slskd`
  in `backend/tests/` vanno letti uno per uno: quelli che lo cercano nel probe
  devono fallire dopo questa modifica, e se restano verdi non stavano provando
  quello che dichiarano.
