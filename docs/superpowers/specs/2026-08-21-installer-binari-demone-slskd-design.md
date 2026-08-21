# Installer dei binari esterni e gestione del demone slskd

Data: 2026-08-21. Stato: approvata a voce.

## Problema

Il wizard di configurazione (`/setup`, spec del 2026-08-18) rileva i componenti
esterni ma non ne installa nessuno di quelli che contano: mostra un comando da
copiare e si ferma lì. Peggio, il comando presuppone Homebrew su macOS, che non
è preinstallato: chi parte da una macchina pulita — cioè esattamente la persona
per cui il wizard esiste — riceve un'istruzione che non può eseguire.

Gli unici componenti oggi auto-installabili sono `yt-dlp` ed `essentia`, ma
**sono entrambi dichiarati in `backend/requirements.txt`** (righe 19 e 28):
`pip install -r requirements.txt` li installa già, e la loro assenza si fa
sentire dove serve (la pagina Analisi mostra un messaggio dedicato sul `503`
`analysis_engine_unavailable`, le funzioni SoundCloud falliscono). Non sono
affari del wizard. Tolti quei due, l'installer resta senza niente da installare.

I componenti che davvero non arrivano da `requirements.txt` sono tre binari:
**ffmpeg**, **fpcalc** e **slskd**.

## Decisioni chiave

- **Una cartella dell'app contiene i binari**, e non è un meccanismo nuovo:
  `CRATORY_BIN_DIR` — già consultato prima del `PATH` da probe, AcoustID,
  download e Shazam — riceve semplicemente un default, `backend/data/bin`.
  Tauri continuerà a sovrascrivere la variabile puntando al bundle.
- **Si scarica solo ciò che manca.** Se il sistema ha già un componente, la riga
  dice "trovato" e non offre nulla: il conflitto di precedenza non nasce perché
  non installiamo doppioni.
- **Versione e SHA256 fissati nel codice.** Stiamo scaricando ed eseguendo
  binari: l'hash pinnato è ciò che impedisce a una release manomessa a monte di
  entrare. Nessun "prendi l'ultima release".
- **L'installazione riesce solo se il binario parte.** Download, verifica ed
  estrazione non bastano — la prova è eseguirlo.
- **slskd viene scaricato, configurato e avviato da Cratory**, come processo
  indipendente che sopravvive alla chiusura dell'app. È una deroga consapevole
  al confine "slskd è un servizio esterno raggiunto via HTTP".
- **Fermiamo solo i demoni che abbiamo acceso noi.**
- Le **credenziali Soulseek** le chiede il wizard e finiscono solo nel
  `slskd.yml`, senza copia nel nostro database.

## Ambito

Dentro: cartella gestita dei binari, manifesto pinnato, installer con verifica,
riduzione del registry del probe a tre voci, configurazione e ciclo di vita del
demone slskd, interfaccia nel passo 1 e nel passo slskd, comandi anche in
Impostazioni.

Fuori, dichiarato: aggiornamento automatico dei binari installati, controllo di
versioni più nuove di quella pinnata, registrazione in `launchd`/`systemd`,
bottone di disinstallazione (si cancella la cartella), gestione di `yt-dlp` ed
`essentia` (sono dipendenze dichiarate, le installa pip).

Nessuna dipendenza nuova: `httpx`, `tarfile`, `zipfile`, `hashlib`, `subprocess`
sono già disponibili.

---

## 1. La cartella gestita

`Settings` guadagna `bin_dir: str = "./data/bin"`, accanto a `cover_cache_dir` e
`thumb_cache_dir` che seguono già questo schema. `system_probe.resolve_binary`
non cambia forma: legge `CRATORY_BIN_DIR` dall'ambiente e, se non c'è, usa
`settings.bin_dir`. Non serve una nuova regola di precedenza né un nuovo passo
di ricerca — la cartella gestita **è** il seam che esiste già.

Conseguenze accettate: ogni git worktree ha la sua copia dei binari, e
`git clean -fdx` la cancella (recuperabile con un clic dal wizard).

Un caso residuo resta aperto per scelta: se l'utente installa ffmpeg via brew
**dopo** che ne abbiamo scaricato uno nostro, il nostro continua a vincere e
potrebbe essere più vecchio. Il probe già distingue la provenienza (`source`) e
la riga mostra "Incluso nell'app": va esteso a dire, in quel caso, che esiste
anche una copia di sistema che stiamo scavalcando.

## 2. Il registry si riduce a tre binari

`services/system_probe.py` perde `yt-dlp` ed `essentia`, e con loro il
rilevamento per import (`python_module`, `_probe_python_module`,
`_import_version`), che esisteva solo per quei due.

Sopravvive la guardia sul codice di uscita in `_run_version`: era la correzione
del falso verde (lo stderr di un fallimento veniva letto come versione) e vale
per tutti i binari. Sopravvivono il campo `docs`, l'avviso su Homebrew e la nota
per i componenti senza ricetta: i tre superstiti sono binari che ne hanno
bisogno.

## 3. Il manifesto

`services/binary_manifest.py`, separato dal registry del probe: sono dati puri
che cambiano con la cadenza dei bump di versione, mentre il registry descrive
comportamento.

```python
@dataclass(frozen=True)
class Download:
    version: str
    url: str
    sha256: str
    member: str          # il file da estrarre dall'archivio
    archive: Literal["tar.gz", "tar.xz", "zip"]
```

Chiave: componente → tag di piattaforma, costruito da `sys.platform` e
`platform.machine()` (`darwin-arm64`, `darwin-x86_64`, `linux-x86_64`,
`linux-arm64`, `win32-x86_64`).

**fpcalc** è il caso pulito: Chromaprint pubblica binari ufficiali per ogni
piattaforma, ~2 MB, e GitHub dichiara il digest SHA256 nella sua API — comodo
per **compilare** il manifesto, non per fidarsene al momento del download: il
valore atteso resta quello fissato nel nostro codice. La build
`macos-universal` copre entrambe le architetture Apple con una voce sola.
Verificato sul campo: checksum combaciante, firma ad-hoc del linker, esecuzione
riuscita.

**slskd** pubblica zip self-contained per piattaforma nelle sue release GitHub.

**ffmpeg** è il punto debole, e la decisione è esplicita:

- **Linux e Windows**: `BtbN/FFmpeg-Builds` pubblica release datate
  (`autobuild-YYYY-MM-DD-HH-MM`) con nomi file versionati e immutabili —
  pinnabili, ospitate su GitHub, stesso modello di fiducia di Chromaprint.
  Coprono `linux64`, `linuxarm64`, `win64`. Si pinna una release datata, **mai**
  il tag `latest`, i cui asset vengono sovrascritti e renderebbero impossibile
  fissare un hash.
- **macOS: nessuna voce nel manifesto.** Non esiste una build statica arm64
  nativa da una fonte che pubblichi checksum: BtbN non produce asset macOS
  (verificato: zero), ed `evermeet.cx` distribuisce firme GPG anziché SHA256 e
  non dichiara l'architettura (storicamente Intel, che su Apple Silicon
  girerebbe solo con Rosetta). Spedire un binario Intel dipendente da Rosetta
  come componente **necessario** sulla piattaforma principale dell'utente è
  peggio di un buco dichiarato: su macOS ffmpeg ricade sul comando manuale
  (`brew install ffmpeg`) e sul link, che esistono già. La decisione si
  ribalta il giorno in cui compare una build arm64 nativa con checksum
  pubblicato: è una riga di dati in più, nessun codice.

Una piattaforma senza voce non è un errore: la riga lo dice e mostra il comando
manuale.

## 4. L'installer

`services/binary_installer.py` prende il posto delle ricette `pip` di
`component_installer.py`. La meccanica esistente resta: job in background a
istanza singola, log riga per riga, lucchetto uno-alla-volta, polling. Cambia
cosa fa il job:

1. **Scarica** in streaming su file temporaneo, calcolando lo SHA256 mentre
   scorre (nessun file intero in memoria).
2. **Verifica** l'hash contro il manifesto. Se non torna, si ferma.
3. **Estrae** con `filter="data"` per i tar (disponibile su Python 3.11.15) e
   con validazione esplicita dei nomi per gli zip, che quel filtro non ce
   l'hanno: un membro assoluto o con `..` fa fallire l'estrazione.
4. **Rende eseguibile** e **lo esegue** (`-version`).

Tutto avviene in una directory temporanea; nella cartella gestita si sposta solo
alla fine, quando tutti e quattro i passi sono andati. Un'installazione
interrotta non lascia mezzo binario in giro.

Il log emette una riga per fase, comprese le percentuali del download: è
l'avanzamento reale, senza nuova UI.

## 5. Il demone slskd

`services/slskd_daemon.py`.

**Il caso normale è che slskd ci sia già.** Il probe lo interroga via HTTP: se
qualcosa risponde all'URL configurato, non si scarica e non si avvia niente.

**Configurazione senza distruggere quella esistente.** Se un `slskd.yml` c'è,
non viene riscritto: si toccano solo le chiavi necessarie, come fa già
`slskd_shares.edit_shares_yaml` per la condivisione. Si genera da zero solo se
manca del tutto. Le chiavi scritte sono quattro: username e password Soulseek,
la porta coerente con `slskd_url()`, la cartella di download coerente con
`slskd_download_dir()`. Quando quei due valori sono vuoti — installazione da
zero — si usano i default di slskd (porta `5030`) e la cartella di download già
proposta dal wizard, e li si scrive **anche** nelle impostazioni di Cratory, così
le due configurazioni nascono già allineate invece di divergere al primo avvio.
Il resto del file resta intatto.

**Avvio staccato con verifica.** `subprocess.Popen(..., start_new_session=True)`
così sopravvive alla chiusura di Cratory; lo stdout va in un file di log sotto
`backend/data`. Dopo lo spawn si interroga `/health` per qualche secondo: se non
risponde mai, l'avvio è fallito e si mostra la coda del log — è lì che si legge
una porta occupata o una password errata.

**Si ferma solo ciò che abbiamo acceso noi.** Il PID va in
`backend/data/slskd.pid`, e quel file è l'unica cosa che autorizza il bottone
Ferma. Prima di agire su un PID si valida che il processo esista **e** che la
sua riga di comando sia davvero slskd: un PID può essere stato riassegnato a
tutt'altro. Se non combacia, il file è stantio e va cancellato.

**Le credenziali si comportano come gli altri segreti**: nessuna copia da noi,
campo password mai pre-riempito né rileggibile. L'username sì, si rilegge dal
`slskd.yml`.

Endpoint sotto `/api/slskd/daemon/*` (`start`, `stop`, `status`), non sotto
`/api/setup`: accendere e spegnere serve anche a regime, e quel router possiede
già `connect` e `disconnect`.

## 6. Interfaccia

**Passo 1**: tre righe e, in cima, un bottone "Installa quello che manca", che
installa in sequenza i componenti mancanti **che hanno una voce nel manifesto
per questa piattaforma**, riusando il lucchetto esistente. Su macOS, quindi,
installa fpcalc e lascia a ffmpeg il comando manuale: il bottone non promette
ciò che non può mantenere, e la riga di ffmpeg continua a spiegare perché. Il
bottone è spento quando non c'è niente di installabile. Ogni riga conserva il
suo bottone singolo.

**slskd fa eccezione in quel bottone**: senza credenziali non si può installare
alla cieca, quindi la sua riga porta un "Configura" che manda al passo slskd.

**Passo slskd**: se qualcosa risponde all'URL, dice "già in esecuzione" e
finisce lì. Altrimenti username, password, cartella di download e un bottone
solo — scarica, configura e avvia. A demone acceso, stato e bottone Ferma,
quest'ultimo solo se il PID è nostro. Gli stessi comandi compaiono nella riga
slskd di Impostazioni.

## 7. Errori

Trattarli tutti allo stesso modo sarebbe il difetto peggiore: richiedono azioni
diverse.

| Cosa fallisce | Cosa vede l'utente |
|---|---|
| Nessuna build per la piattaforma | Lo dice, con comando manuale e link |
| Download interrotto o 404 | Errore di rete, ritentabile — o il pin è marcito |
| **Hash diverso** | Messaggio a sé: il file non è quello atteso. È un allarme, non un intoppo |
| Archivio con percorsi fuori cartella | Rifiutato, stesso registro dell'hash |
| Installato ma non parte | Firma o architettura: ripiego sul comando manuale |
| slskd non risponde dopo l'avvio | La coda del suo log |

In ogni caso ricompaiono il comando manuale e il link alla documentazione.

## 8. Verifica

I test che contano sono sugli invarianti, non sui valori di ritorno:

- **hash diverso → nella cartella gestita non entra niente** (asserzione sulla
  cartella, non sul valore ritornato);
- **archivio con un membro `../` o assoluto → non si scrive fuori**, per tar e
  per zip separatamente (il `data_filter` copre i primi, non i secondi);
- **binario che esce non-zero alla prova → installazione fallita**, anche se il
  file esiste;
- piattaforma senza voce nel manifesto → errore chiaro e **nessuna rete
  toccata**;
- **PID stantio** (processo inesistente, o riga di comando che non è slskd) →
  stato "non in esecuzione", stop rifiutato, file rimosso;
- **slskd già in ascolto → start non lancia un secondo processo**;
- **`slskd.yml` esistente: dopo la scrittura, le chiavi non nostre sono ancora
  tutte lì**, verificato sul contenuto integrale del file e non sulle quattro
  che tocchiamo. È l'invariante che protegge la configurazione dell'utente.

Nessun test tocca la rete vera: il download si prova con `httpx.MockTransport`.
Esiste già il marcatore `network`, escluso di default in `pytest.ini`.

## 9. Documentazione da aggiornare

`docs/ARCHITECTURE.md` descrive slskd come servizio esterno raggiunto via HTTP.
Da qui in poi Cratory lo scarica, lo configura e lo avvia: il confine si sposta,
per decisione esplicita, e la documentazione va aggiornata a dirlo — altrimenti
resta un'affermazione non più vera. Vanno documentati anche la cartella gestita,
il manifesto pinnato e il motivo per cui macOS non ha una voce per ffmpeg.

`docs/API.md` guadagna gli endpoint del demone. `docs/DEPENDENCIES.md` va
allineato sul fatto che ffmpeg e fpcalc possono ora arrivare dall'app.
