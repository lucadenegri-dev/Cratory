# ④ Rilascio: artefatto, licenza, aggiornamenti

Data: 2026-08-22. Stato: **decisioni prese da Claude in assenza del committente,
su sua richiesta di procedere. Da rivedere.**
Contesto d'insieme: `2026-08-22-tauri-decomposizione-design.md`.

## Problema

Il ③ produce un `Cratory.app` che funziona. Non produce qualcosa che si possa
dare a qualcuno: non c'è una licenza (e il bundle contiene codice AGPL-3.0),
non c'è un artefatto pensato per essere spedito, e chi lo riceve incontra
Gatekeeper senza sapere cosa fare.

## Decisioni chiave

- **`LICENSE` AGPL-3.0.** Non è una scelta di stile: il bundle contiene
  `essentia`, che è AGPL-3.0, e distribuirlo vincola l'opera combinata. La
  decisione è stata presa all'inizio del lavoro, consapevolmente, scegliendo
  di mettere tutto dentro il bundle. Va anche corretta la riga del README che
  dice «No license file is included».
- **Il `.dmg` diventa l'artefatto, e smette di essere un effetto collaterale.**
  Oggi esce da `targets: "all"` senza che nessuno l'abbia chiesto. Diventa
  esplicito.
- **Niente notarizzazione, e lo si dice.** Senza account Apple Developer non è
  possibile. Chi riceve il `.dmg` vede un messaggio che dice «danneggiato» —
  la formulazione peggiore possibile, perché il file è integro. Serve una
  spiegazione scritta, breve e trovabile.
- **L'updater automatico si rimanda, dichiarandolo.** L'updater di Tauri vuole
  una coppia di chiavi, un manifesto pubblicato e almeno una release che
  esista. Il repository non è ancora pubblico e non ha release: si
  configurerebbe qualcosa che non si può provare, e configurazione non provata
  in un percorso di aggiornamento automatico è peggio della sua assenza. Il
  bottone «Controlla aggiornamenti» che già esiste continua a informare; il
  passo da compiere resta manuale. **Questo è il pezzo di ④ che resta aperto.**

## Ambito

Dentro: il `LICENSE`, la correzione del README, il `.dmg` come artefatto
dichiarato, le istruzioni per chi lo riceve, e la procedura di rilascio scritta.

Fuori, dichiarato: l'updater automatico (sopra), la firma Apple e la
notarizzazione (serve l'account), Windows e Linux.

Il consegnabile è **un `.dmg` che si può mandare a qualcuno, con accanto le
istruzioni che gli servono per aprirlo.**

---

## 1. La licenza

`LICENSE` con il testo integrale della AGPL-3.0 nella radice. Il README dice
oggi «No license file is included; this is a personal tool, not a package to
depend on»: la prima metà diventa falsa, la seconda resta vera e va tenuta.

Va anche detto **perché**: chi legge deve capire che la licenza discende da
essentia e dalla scelta di spedirla, non da una preferenza ideologica. E che
distribuire il `.dmg` comporta rendere disponibili i sorgenti.

## 2. L'artefatto

`bundle.targets` passa da `"all"` a `["dmg"]`. `"all"` su macOS produce sia il
`.app` sia il `.dmg`, più il rumore delle piattaforme che non ci interessano;
dichiarare `dmg` dice cosa si sta costruendo e perché.

Il nome che Tauri genera — `Cratory_0.9.0_aarch64.dmg` — va bene così: porta
la versione e l'architettura, che sono le due cose che chi lo riceve deve
sapere.

## 3. Gatekeeper, e cosa dire a chi riceve il file

Il `.dmg` non è firmato da un certificato Apple né notarizzato. Su un altro Mac
il primo tentativo di apertura fallisce, e **il messaggio dice «danneggiato»,
non «non firmato»** — chi lo legge pensa a un download corrotto e riprova, o
lo butta.

Le istruzioni vanno nel README, e devono dire tre cose: che succederà, che il
file non è rotto, e i passi esatti (Impostazioni di Sistema → Privacy e
sicurezza → «Apri comunque»). Su macOS recenti il vecchio trucco del clic
destro → Apri non basta più.

**Non si suggerisce `xattr -dr com.apple.quarantine`.** Funziona, ma è un
comando che disattiva un controllo di sicurezza, e insegnarlo a qualcuno che
non sa cosa fa è un cattivo servizio: la prossima volta lo userà su qualcosa
che non viene da te.

## 4. La procedura di rilascio

Scritta nel README, accanto alla sezione «Releases» che già esiste e che oggi
descrive solo il bump di versione e il tag. Va estesa con: costruire il
bundle, dove esce il `.dmg`, e allegarlo alla release GitHub — la stessa che
il bottone «Controlla aggiornamenti» già interroga.

## 5. Verifica

- `LICENSE` esiste, il README non afferma più il contrario, e la ragione è
  scritta.
- Il build produce un `.dmg` e **non** più i target che non servono.
- Il `.dmg` si monta, contiene `Cratory.app`, e l'app copiata in `/Applicazioni`
  si apre.
- Le istruzioni per Gatekeeper sono verificate su un file **in quarantena
  vera** — cioè con l'attributo che il browser applica ai download — non su una
  copia locale che non ce l'ha mai avuta.
