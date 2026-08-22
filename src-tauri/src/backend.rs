//! Il ciclo di vita del backend Python: avvio, attesa che risponda, e
//! terminazione alla chiusura dell'app.
//!
//! Tutto qui gira su un thread di sistema dedicato (non su quello di
//! `setup`, non sul runtime async di Tauri): la guida ufficiale del
//! meccanismo di splashscreen raccomanda esplicitamente di non bloccare
//! l'hook di `setup` con lavoro di rete, perche' l'event loop dell'app deve
//! poter partire subito. Qui in piu' c'e' un motivo concreto: se il dialogo
//! d'errore (Behaviour 1/3, sotto) venisse mostrato PRIMA che l'event loop
//! sia partito, non ci sarebbe alcun run loop a pompare gli eventi della
//! finestra nativa del dialogo. Farlo da un thread avviato da un `setup` che
//! ritorna subito garantisce che l'event loop sia gia' vivo.

use std::collections::VecDeque;
use std::io::{BufRead, BufReader, Read};
use std::net::TcpListener;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use tauri::{AppHandle, Manager};
use tauri_plugin_dialog::{DialogExt, MessageDialogKind};

/// La porta e' fissa e NON va sostituita con una scansione di porte libere.
/// `spotify_redirect_uri` in `backend/app/core/config.py` (default
/// `http://127.0.0.1:8000/api/spotify/callback`) e' la URI registrata
/// sull'app Spotify: e' una stringa fissata lato Spotify, non qualcosa che
/// Cratory possa rinegoziare a runtime. Se il backend nascesse su un'altra
/// porta, l'intero flusso OAuth Spotify si romperebbe in silenzio (redirect
/// verso un server che non ascolta), ed e' un bug molto piu' difficile da
/// diagnosticare di un errore esplicito "porta 8000 occupata" all'avvio.
const BACKEND_PORT: u16 = 8000;
const BACKEND_HOST: &str = "127.0.0.1";

/// Quanto aspettare che uvicorn risponda prima di arrendersi. Generoso perche'
/// il primo avvio importa moduli pesanti (SQLAlchemy, essentia) e crea lo
/// schema del DB; un'attesa troppo corta trasformerebbe un avvio lento ma
/// sano in un falso errore.
const READY_TIMEOUT: Duration = Duration::from_secs(30);
const READY_POLL_INTERVAL: Duration = Duration::from_millis(300);

/// Righe di stdout/stderr del backend tenute in memoria, per poterle mostrare
/// se l'avvio scade: senza, un timeout sarebbe un messaggio muto ("non e'
/// partito") senza alcun indizio sul perche'.
const MAX_LOG_LINES: usize = 40;

/// Quante di quelle righe finiscono nel dialogo d'errore. Poche di proposito:
/// un alert di macOS non scorre e cresce in altezza, quindi un messaggio lungo
/// spinge il bottone OK fuori dallo schermo. Il log dell'app le ha tutte.
const RIGHE_NEL_DIALOGO: usize = 8;

/// Taglio per singola riga, per la stessa ragione in orizzontale.
const MAX_CARATTERI_PER_RIGA: usize = 160;

/// Stato condiviso fra il thread che avvia il backend e l'handler
/// `RunEvent::Exit` in `lib.rs` che lo termina. Un `Mutex` perche' i due lati
/// vivono su thread diversi; il processo e' `None` finche' non e' stato
/// lanciato con successo, cosi' l'handler di uscita non tenta mai di
/// terminare un figlio inesistente.
pub struct BackendProcess(pub Mutex<Option<Child>>);

impl BackendProcess {
    pub fn empty() -> Self {
        BackendProcess(Mutex::new(None))
    }
}

enum PortCheck {
    Libera,
    OccupataDaCratory,
    OccupataDaAltro,
}

/// Behaviour 1: prima di tutto, lo stato della porta 8000.
///
/// Si prova a distinguere "c'e' gia' un Cratory aperto" da "un altro
/// programma occupa la porta" interrogando la stessa rotta che il passo 3
/// usa per capire che il backend e' pronto: se qualcosa risponde li' entro
/// 2 secondi con la forma esatta che solo il nostro backend produce
/// (`{"completed": <bool>}`), e' un Cratory. Ma l'assenza di quella risposta
/// entro 2 secondi non prova il contrario -- potrebbe anche essere un
/// Cratory insolitamente lento a rispondere -- quindi `OccupataDaAltro` e'
/// la spiegazione piu' probabile, non una certezza, e il messaggio mostrato
/// all'utente lo dice in quei termini invece di affermarlo come un fatto.
fn check_port(client: &reqwest::blocking::Client) -> PortCheck {
    // Bind-e-rilascia-subito: se il bind riesce la porta era libera davvero,
    // e va rilasciata immediatamente perche' e' uvicorn (il prossimo bind,
    // fatto dal processo figlio) a doverla tenere lui.
    if TcpListener::bind((BACKEND_HOST, BACKEND_PORT)).is_ok() {
        return PortCheck::Libera;
    }

    match http_get(client, &setup_state_url(), Duration::from_secs(2)) {
        Some(body) if e_uno_stato_di_setup(&body) => PortCheck::OccupataDaCratory,
        _ => PortCheck::OccupataDaAltro,
    }
}

fn setup_state_url() -> String {
    format!("http://{BACKEND_HOST}:{BACKEND_PORT}/api/setup/state")
}

/// Vero solo se il corpo e' un oggetto JSON con la chiave booleana
/// `completed`: e' la forma esatta di `SetupState` in
/// `backend/app/routers/setup.py`, improbabile che un programma qualunque la
/// riproduca per caso.
fn e_uno_stato_di_setup(body: &str) -> bool {
    serde_json::from_str::<serde_json::Value>(body)
        .ok()
        .and_then(|v| v.get("completed").map(|c| c.is_boolean()))
        .unwrap_or(false)
}

/// Il timeout e' per-richiesta (non sul client) perche' i due chiamanti ne
/// vogliono uno diverso: 2s per il probe una tantum di `check_port`, 500ms
/// per ogni giro del poll di `wait_until_ready`. Il client stesso e'
/// costruito una volta sola dal chiamante e riusato: costruirne uno nuovo ad
/// ogni chiamata (come faceva questa funzione prima) crea un intero runtime
/// tokio e un thread ogni volta -- un centinaio di volte nell'arco di un
/// timeout di 30 secondi, per delle richieste bloccanti verso localhost.
fn http_get(client: &reqwest::blocking::Client, url: &str, timeout: Duration) -> Option<String> {
    let resp = client.get(url).timeout(timeout).send().ok()?;
    if !resp.status().is_success() {
        return None;
    }
    resp.text().ok()
}

/// Comando python3 e cartella del backend.
///
/// In un bundle vero (Task 5) questi vivono sotto la resource dir del
/// bundle: `<resource_dir>/python/bin/python3` (il runtime rilocabile
/// costruito da `scripts/costruisci_runtime.py`) e `<resource_dir>/backend`
/// (il sorgente copiato li' dentro), risolti con
/// `app.path().resource_dir()`. Qui, senza un bundle da assemblare, l'unico
/// python3 disponibile e' quello di sviluppo (PATH, o il venv attivato nella
/// shell da cui parte `tauri dev`) e il backend e' la cartella sorgente
/// accanto a `src-tauri`, risolta a compile-time. Il meccanismo -- comando,
/// cwd, variabili d'ambiente sul processo figlio -- e' gia' tutto qui: il
/// Task 5 cambia solo da dove arrivano questi due valori, non la forma del
/// resto di questo modulo.
/// In sviluppo non c'e' nessun runtime assemblato. Si preferisce il venv del
/// progetto, e solo in sua assenza il `python3` del PATH.
///
/// L'ordine non e' una comodita': `tauri dev` non eredita il venv attivato in
/// una shell, quindi senza questo controllo prende il python3 di sistema (il
/// 3.9 su macOS), che non ha uvicorn — e l'avvio muore con un traceback di
/// `click` che non dice niente a chi lo legge. E' successo davvero.
#[cfg(debug_assertions)]
fn python_command(_app: &AppHandle, backend_dir: &Path) -> PathBuf {
    let del_venv = backend_dir.join(".venv/bin/python3");
    if del_venv.is_file() {
        del_venv
    } else {
        PathBuf::from("python3")
    }
}

/// Nel bundle si usa l'interprete che il bundle si porta dietro, MAI il
/// `python3` del PATH.
///
/// Un'app lanciata dal Finder non eredita l'ambiente di una shell: il suo
/// PATH e' quello minimo di `launchd`, dove `python3` e' il Python di
/// sistema (3.9 su questa macchina) che non ha ne' fastapi ne' uvicorn.
/// Spedire 195 MB di runtime e poi invocarne un altro e' esattamente il
/// difetto che questa funzione esiste per impedire, e si manifesta come un
/// backend che non parte senza dire perche'.
///
/// `resource_dir` qui non puo' essere `None`: `spawn_backend` viene chiamata
/// solo dopo che `backend_dir` (che la risolve dalla stessa fonte) ha dato
/// `Some`. Se lo diventasse sarebbe un bug nostro, quindi si segnala invece
/// di ripiegare in silenzio su un interprete sbagliato.
#[cfg(not(debug_assertions))]
fn python_command(app: &AppHandle, _backend_dir: &Path) -> PathBuf {
    match resource_dir(app) {
        Some(r) => r.join("python/bin/python3"),
        None => {
            log::error!(
                "resource_dir() non risolvibile al momento dello spawn: \
                 ripiego sul python3 di sistema, che quasi certamente non ha uvicorn."
            );
            PathBuf::from("python3")
        }
    }
}

/// `None` finche' non c'e' una cartella backend valida da cui partire:
/// in sviluppo c'e' sempre (la sorgente accanto a `src-tauri`), in una
/// build di release solo se `resource_dir()` si risolve (vedi sotto).
/// `Option` invece di un valore inventato (es. una `PathBuf` vuota) cosi' il
/// chiamante puo' distinguere "risorse del bundle mancanti/non risolvibili"
/// da un errore di spawn qualunque, e mostrare il messaggio giusto invece di
/// uno fuorviante tipo "python3 non installato?" per un problema che non ha
/// niente a che fare con python3.
///
/// `#[cfg(debug_assertions)]`, non un `if` a runtime: cosi' `env!` non
/// viene nemmeno valutata in una build di release, e il percorso di
/// sviluppo (che in un bundle non esiste) non resta comunque cucito
/// dentro al binario distribuito.
#[cfg(debug_assertions)]
fn backend_dir(_app: &AppHandle) -> Option<PathBuf> {
    Some(PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../backend"))
}

/// Task 5: `<resource_dir>/backend`, dove `scripts/assembla.py` ha copiato
/// `backend/app` e `backend/requirements.txt` (vedi `bundle.resources` in
/// tauri.conf.json). Delega a `resource_dir` sotto per il percorso base;
/// `None` si propaga da li' se il bundle non e' risolvibile.
#[cfg(not(debug_assertions))]
fn backend_dir(app: &AppHandle) -> Option<PathBuf> {
    resource_dir(app).map(|r| r.join("backend"))
}

/// La cartella delle risorse del bundle (`Contents/Resources` dentro il
/// `.app` su macOS -- vedi la doc di `PathResolver::resource_dir` di Tauri
/// 2.11.5, letta da sorgente in
/// `~/.cargo/registry/src/.../tauri-2.11.5/src/path/desktop.rs`). Solo in
/// release: in sviluppo `resource_dir()` risolverebbe comunque a qualcosa
/// (la cartella dell'eseguibile Cargo, `target/debug/`, per via del
/// controllo "sto girando da un output di Cargo?" che la funzione fa da
/// sola), ma mai a un posto che ha ricevuto le copie di `assembla.py` --
/// per questo `backend_dir` in sviluppo (sopra) non la chiama nemmeno.
///
/// `Result` -> `Option` con un log: un `resource_dir()` che fallisce in
/// release e' un bundle rotto (eseguibile fuori da una struttura `.app`
/// valida), non un caso normale da passare sotto silenzio come il ramo
/// "sviluppo" di `bin_dir`/`data_dir` sotto.
#[cfg(not(debug_assertions))]
fn resource_dir(app: &AppHandle) -> Option<PathBuf> {
    match app.path().resource_dir() {
        Ok(dir) => Some(dir),
        Err(err) => {
            log::error!("resource_dir() non risolvibile: {err}");
            None
        }
    }
}

/// `CRATORY_BIN_DIR`: `<resource_dir>/bin`, dove `costruisci_binari.py` (via
/// `assembla.py`) ha messo fpcalc/ffmpeg/slskd. Stringa vuota in sviluppo --
/// vedi `env_value` sotto per come i due casi confluiscono nello stesso
/// valore che il backend gia' sa interpretare come "assente" (vedi
/// `resolve_binary` in `backend/app/services/system_probe.py`): qui
/// l'assenza e' il comportamento normale di sempre, non un errore da
/// segnalare come fa `backend_dir` con l'avvio mancato.
#[cfg(debug_assertions)]
fn bin_dir(_app: &AppHandle) -> Option<PathBuf> {
    None
}

#[cfg(not(debug_assertions))]
fn bin_dir(app: &AppHandle) -> Option<PathBuf> {
    resource_dir(app).map(|r| r.join("bin"))
}

/// `CRATORY_DATA_DIR`: dall'API di Tauri per le directory dell'app
/// (`app.path().app_data_dir()`), MAI composta a mano concatenando `$HOME`
/// -- e' esattamente per questo che quell'API esiste (se in futuro cambia
/// qualcosa nel sandboxing o nella risoluzione della home, questa riga
/// continua a valere senza modifiche). Su macOS risolve a
/// `~/Library/Application Support/<identifier>`: l'`identifier` di
/// tauri.conf.json ("com.cratory.app"), non il `productName` ("Cratory") --
/// stessa convenzione, letta dalla stessa sorgente, di `app_config_dir` e
/// `app_log_dir` nella libreria (`dir.join(&self.0.config().identifier)`).
/// Stringa vuota in sviluppo, stessa ragione di `bin_dir` sopra:
/// `backend/app/core/paths.py` tratta l'assenza come `= BACKEND_DIR`, il
/// comportamento di sempre.
#[cfg(debug_assertions)]
fn data_dir(_app: &AppHandle) -> Option<PathBuf> {
    None
}

#[cfg(not(debug_assertions))]
fn data_dir(app: &AppHandle) -> Option<PathBuf> {
    match app.path().app_data_dir() {
        Ok(dir) => Some(dir),
        Err(err) => {
            log::error!("app_data_dir() non risolvibile: {err}");
            None
        }
    }
}

/// `Some(path)` -> il percorso come stringa; `None` -> stringa vuota, che
/// per il backend equivale a "variabile non impostata" (vedi
/// `risolvi_data_dir` in `paths.py` e `resolve_binary` in `system_probe.py`:
/// entrambi trattano un valore vuoto/di soli spazi come assente, non come un
/// percorso letterale). Questo e' il punto di confluenza fra i due rami di
/// `bin_dir`/`data_dir`: il chiamante (`spawn_backend`) non deve sapere se
/// la stringa vuota viene dal ramo di sviluppo o da un fallimento di
/// risoluzione in release.
fn env_value(path: Option<PathBuf>) -> String {
    path.map(|p| p.display().to_string()).unwrap_or_default()
}

/// Behaviour 2: avvia uvicorn come processo figlio.
///
/// MAI `bin/uvicorn`: negli script sotto `bin/` di un venv (o del runtime
/// rilocabile costruito da `costruisci_runtime.py`) lo shebang porta il
/// percorso assoluto dell'interprete della macchina che li ha creati. Su una
/// macchina diversa (o semplicemente in una cartella diversa) quello
/// shebang punta a un file che non esiste, e lo script non parte. Invocare
/// sempre l'interprete con `-m` evita il problema perche' non passa mai da
/// uno script con uno shebang cucito addosso.
fn spawn_backend(app: &AppHandle, backend_dir: &Path) -> std::io::Result<Child> {
    Command::new(python_command(app, backend_dir))
        .args([
            "-m",
            "uvicorn",
            "app.main:app",
            "--port",
            &BACKEND_PORT.to_string(),
            "--host",
            BACKEND_HOST,
        ])
        .current_dir(backend_dir)
        // Il processo figlio eredita per default TUTTO l'ambiente del
        // genitore, non solo le tre env sotto: se la shell che lancia
        // l'app.bundle (o l'utente stesso, in ~/.zshrc etc.) ha PYTHONHOME o
        // PYTHONPATH esportate -- capita con altri progetti Python, altri
        // venv attivati a mano, tool tipo pyenv -- l'interprete rilocabile
        // del bundle le userebbe al posto della sua stdlib bundlata,
        // rompendosi con un errore criptico (moduli non trovati, versione
        // sbagliata) invece di partire pulito con solo cio' che ha portato
        // con se'. Il seam CRATORY_BIN_DIR esiste apposta perche' il backend
        // non debba dipendere dall'ambiente della shell che lo lancia: le
        // stesse due variabili nel processo, ereditate senza controllo,
        // sarebbero la stessa trappola da un'altra porta.
        .env_remove("PYTHONHOME")
        .env_remove("PYTHONPATH")
        // Le tre env che il backend sa leggere (vedi backend/app/core/paths.py
        // e backend/app/services/system_probe.py). CRATORY_DATA_DIR e
        // CRATORY_BIN_DIR sono vuote in sviluppo (default = cartella del
        // backend / PATH, il comportamento di sempre) e risolte dalle API di
        // Tauri in release -- vedi `data_dir`/`bin_dir` sopra. CRATORY_VERSION
        // arriva gia' incorporata a build time: `package_info().version` e'
        // quello che `tauri::generate_context!()` legge da `version` in
        // tauri.conf.json (che punta a frontend/package.json, tenuto
        // allineato al file VERSION della radice da un test backend) --
        // niente di tutto questo esiste piu' a runtime in un bundle, ma qui
        // non serve: e' gia' stato risolto in fase di compilazione.
        .env("CRATORY_DATA_DIR", env_value(data_dir(app)))
        .env("CRATORY_BIN_DIR", env_value(bin_dir(app)))
        .env(
            "CRATORY_VERSION",
            app.package_info().version.to_string(),
        )
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
}

/// Esito dell'attesa: non un semplice bool, perche' "non e' ancora pronto"
/// e "non sara' mai pronto perche' e' gia' morto" sono due problemi diversi
/// e vogliono due messaggi diversi (vedi sotto).
enum Esito {
    Pronto,
    Timeout,
    ProcessoMorto(std::process::ExitStatus),
}

/// Behaviour 3: aspetta che il backend risponda, entro un limite di tempo.
///
/// Ad ogni giro, oltre al poll HTTP, si controlla anche che il processo sia
/// ancora vivo (`try_wait` sul figlio gia' tracciato in `process`, vedi
/// `avvia_e_attendi`). Il fallimento piu' probabile in sviluppo -- un
/// python3 senza uvicorn installato -- fa uscire il processo all'istante:
/// senza questo controllo l'utente si troverebbe 30 secondi di finestra
/// nascosta e nessun indizio prima del dialogo finale, per un problema che
/// in realta' e' visibile fin dal primo giro del poll.
fn wait_until_ready(client: &reqwest::blocking::Client, process: &BackendProcess) -> Esito {
    let deadline = Instant::now() + READY_TIMEOUT;
    let url = setup_state_url();
    while Instant::now() < deadline {
        if http_get(client, &url, Duration::from_millis(500)).is_some() {
            return Esito::Pronto;
        }
        {
            let mut guard = process.0.lock().expect("BackendProcess mutex avvelenato");
            if let Some(child) = guard.as_mut() {
                if let Ok(Some(status)) = child.try_wait() {
                    return Esito::ProcessoMorto(status);
                }
            }
        }
        std::thread::sleep(READY_POLL_INTERVAL);
    }
    Esito::Timeout
}

/// Legge uno stream riga per riga e la accoda a un buffer condiviso, con un
/// tetto massimo di righe (le piu' vecchie cadono): serve solo a poter
/// mostrare "le ultime righe" se l'avvio scade, non a tenere un log completo.
fn spawn_line_reader<R: Read + Send + 'static>(
    stream: Option<R>,
    log: Arc<Mutex<VecDeque<String>>>,
) {
    let Some(stream) = stream else { return };
    std::thread::spawn(move || {
        let reader = BufReader::new(stream);
        for line in reader.lines().map_while(Result::ok) {
            let mut buf = log.lock().expect("output_log mutex avvelenato");
            if buf.len() >= MAX_LOG_LINES {
                buf.pop_front();
            }
            buf.push_back(line);
        }
    });
}

/// Le ultime righe accodate da `spawn_line_reader`, pronte per un messaggio
/// d'errore: fattorizzata perche' serve identica sia per il timeout sia per
/// il caso "il processo e' morto da solo" (vedi `Esito` sopra).
fn ultime_righe(output_log: &Mutex<VecDeque<String>>) -> String {
    let tutte: Vec<String> = output_log
        .lock()
        .expect("output_log mutex avvelenato")
        .iter()
        .cloned()
        .collect();
    if tutte.is_empty() {
        return "(nessun output)".to_string();
    }
    // Nel dialogo entrano poche righe, non tutte le MAX_LOG_LINES del buffer.
    // Un alert di macOS cresce in altezza col testo e non scorre: con quaranta
    // righe di traceback il bottone OK finisce sotto il bordo dello schermo e
    // il dialogo diventa impossibile da chiudere. Il buffer resta pieno perche'
    // `fatal_error` scrive comunque il messaggio completo nel log.
    let scartate = tutte.len().saturating_sub(RIGHE_NEL_DIALOGO);
    let mut corpo: Vec<String> = tutte[scartate..]
        .iter()
        // Anche una riga sola puo' essere lunghissima e allargare il dialogo:
        // si taglia, il log conserva l'originale.
        .map(|r| {
            if r.chars().count() > MAX_CARATTERI_PER_RIGA {
                let tagliata: String = r.chars().take(MAX_CARATTERI_PER_RIGA).collect();
                format!("{tagliata}...")
            } else {
                r.clone()
            }
        })
        .collect();
    if scartate > 0 {
        corpo.insert(0, format!("(altre {scartate} righe nel log dell'app)"));
    }
    corpo.join("\n")
}

fn fatal_error(app: &AppHandle, title: &str, message: &str) {
    log::error!("{title}: {message}");
    // `blocking_show` prima di `app.exit`: senza aspettare che l'utente abbia
    // letto e chiuso il dialogo, `exit` distruggerebbe il dialogo insieme al
    // resto dell'app nello stesso istante in cui compare.
    app.dialog()
        .message(message)
        .kind(MessageDialogKind::Error)
        .title(title)
        .blocking_show();
    app.exit(1);
}

/// Punto d'ingresso chiamato da `setup`, su un thread dedicato. Esegue i
/// comportamenti 1-3 in ordine e, se tutto va bene, mostra la finestra
/// principale. Il comportamento 4 (terminare il figlio) vive nell'handler
/// `RunEvent::Exit` di `lib.rs`: usa lo stesso `BackendProcess` gestito qui.
pub fn avvia_e_attendi(app: AppHandle) {
    // Un solo client HTTP, costruito qui e passato per riferimento a
    // `check_port` e `wait_until_ready`: vedi il commento su `http_get` per
    // il perche' (altrimenti se ne costruirebbe uno nuovo -- runtime tokio e
    // thread compresi -- ad ogni singolo poll).
    let http_client = reqwest::blocking::Client::new();

    match check_port(&http_client) {
        PortCheck::OccupataDaCratory => {
            fatal_error(
                &app,
                "Cratory e' gia' aperto",
                &format!(
                    "Un'altra istanza di Cratory sta gia' rispondendo su \
                     {}. Chiudi quella finestra (o il suo backend, se e' \
                     rimasto in esecuzione da solo) prima di riaprire l'app.",
                    setup_state_url()
                ),
            );
            return;
        }
        PortCheck::OccupataDaAltro => {
            fatal_error(
                &app,
                "Porta 8000 occupata",
                &format!(
                    "La porta {BACKEND_PORT} e' occupata, ma chi risponde \
                     non ha la forma di un Cratory pronto entro 2 secondi: \
                     puo' essere un altro programma, oppure un'istanza di \
                     Cratory insolitamente lenta a rispondere. Cratory non \
                     puo' comunque cercare una porta alternativa: la \
                     redirect URI di Spotify e' registrata proprio su \
                     questo numero, e su una porta diversa l'accesso a \
                     Spotify smetterebbe di funzionare. Libera la porta \
                     {BACKEND_PORT} (o attendi che risponda, se e' \
                     Cratory) e riapri l'app."
                ),
            );
            return;
        }
        PortCheck::Libera => {}
    }

    let backend_dir = match backend_dir(&app) {
        Some(dir) => dir,
        None => {
            // Non un errore di spawn qualunque: senza questo ramo separato,
            // in una build di release con una resource dir non risolvibile,
            // l'unico messaggio che l'utente vedrebbe sarebbe quello di
            // `spawn_backend` piu' sotto ("python3 non installato?"),
            // fuorviante per un problema che non ha niente a che fare con
            // python3.
            fatal_error(
                &app,
                "Risorse del bundle mancanti",
                "La cartella delle risorse del bundle (backend + runtime \
                 Python) non e' risolvibile in questa build. Se questo e' \
                 un bundle assemblato con scripts/assembla.py, verificare \
                 che 'bundle.resources' in tauri.conf.json e lo staging \
                 siano presenti; questa build non puo' avviare il backend.",
            );
            return;
        }
    };

    let mut child = match spawn_backend(&app, &backend_dir) {
        Ok(child) => child,
        Err(err) => {
            fatal_error(
                &app,
                "Backend non avviato",
                // Il suggerimento non nomina il PATH: in un bundle
                // l'interprete e' quello dentro Resources, e mandare l'utente
                // a controllare il PATH lo manderebbe a cercare la cosa
                // sbagliata. Il percorso stampato dice gia' quale dei due e'.
                &format!(
                    "Impossibile lanciare '{} -m uvicorn': {err}",
                    python_command(&app, &backend_dir).display()
                ),
            );
            return;
        }
    };

    let output_log: Arc<Mutex<VecDeque<String>>> = Arc::new(Mutex::new(VecDeque::new()));
    spawn_line_reader(child.stdout.take(), Arc::clone(&output_log));
    spawn_line_reader(child.stderr.take(), Arc::clone(&output_log));

    // Il figlio va tracciato nello stato condiviso PRIMA di aspettare, non
    // dopo. `wait_until_ready` dura 5-6 secondi in un avvio normale e fino a
    // READY_TIMEOUT (30s) in uno lento, e per tutta quella finestra l'app e'
    // gia' viva: icona nel Dock, voce "Esci" raggiungibile. Se l'utente
    // chiudesse l'app in quella finestra mentre questo stato e' ancora
    // `None`, l'handler di `RunEvent::Exit` (`termina`, sotto) non
    // troverebbe nessun figlio da terminare, e uvicorn resterebbe orfano
    // attaccato alla porta 8000 -- esattamente il caso che `check_port`
    // intercetterebbe al prossimo avvio, scambiandolo per "un altro
    // programma occupa la porta" (o "Cratory e' gia' aperto"): un bug
    // nostro spacciato per un problema dell'utente. Tracciare il figlio qui,
    // prima della chiamata che puo' durare fino a 30 secondi, chiude questa
    // finestra invece di limitarsi a coprire il caso del timeout.
    let state = app.state::<BackendProcess>();
    *state.0.lock().expect("BackendProcess mutex avvelenato") = Some(child);

    let esito = wait_until_ready(&http_client, state.inner());

    if let Esito::Timeout = esito {
        fatal_error(
            &app,
            "Il backend non e' partito",
            &format!(
                "Nessuna risposta da {} entro {} secondi.\n\nUltime righe di output:\n{}",
                setup_state_url(),
                READY_TIMEOUT.as_secs(),
                ultime_righe(&output_log)
            ),
        );
        return;
    }
    if let Esito::ProcessoMorto(status) = esito {
        // Diverso dal timeout apposta: qui il processo e' morto subito (il
        // caso tipico in sviluppo e' un python3 senza uvicorn installato),
        // non sta ancora avviandosi. Dirlo chiaramente evita 30 secondi di
        // attesa inutile e un messaggio che parla di "nessuna risposta"
        // quando in realta' non c'e' nessun processo a rispondere.
        fatal_error(
            &app,
            "Il backend si e' fermato",
            &format!(
                "Il processo del backend e' uscito da solo ({status}) prima \
                 di rispondere: non e' un timeout, e' morto subito. La \
                 causa piu' comune in sviluppo e' un python3 senza uvicorn \
                 installato.\n\nUltime righe di output:\n{}",
                ultime_righe(&output_log)
            ),
        );
        return;
    }

    match app.get_webview_window("main") {
        Some(window) => {
            // Ricarica PRIMA di mostrare, e non e' un ritocco cosmetico.
            //
            // La finestra e' dichiarata in tauri.conf.json, quindi il webview
            // esiste e carica la pagina all'avvio del processo -- cioe' mentre
            // il backend sta ancora salendo. Le chiamate che la pagina fa in
            // quel momento trovano la porta chiusa e falliscono con "Load
            // failed". Chi ripete (il polling dei job) si riprende da solo;
            // chi chiede una volta sola in un useEffect (le statistiche della
            // home, l'elenco dei set) resta con l'errore in pagina per sempre,
            // e l'utente vede un'app appena aperta che dichiara il backend
            // spento mentre il backend risponde.
            //
            // Nascondere la finestra non basta: nasconde il sintomo, non
            // impedisce le chiamate. Ricaricare qui e' il punto in cui il
            // backend ha appena risposto, quindi la pagina riparte contro un
            // backend vivo.
            let _ = window.eval("window.location.reload()");
            let _ = window.show();
            // Senza `set_focus`, se l'utente ha cambiato app durante
            // l'attesa (fino a READY_TIMEOUT secondi) la finestra compare
            // dietro quella su cui si trova, e sembra che l'avvio non sia
            // riuscito.
            let _ = window.set_focus();
        }
        None => {
            // Non dovrebbe poter succedere (la finestra "main" e' definita
            // in tauri.conf.json), ma se succedesse l'app resterebbe viva
            // per sempre e invisibile, con un backend gia' in esecuzione, e
            // senza questo log non ci sarebbe nemmeno una riga a dirlo.
            log::error!(
                "finestra 'main' non trovata dopo l'avvio riuscito del \
                 backend: l'app resta invisibile con un backend gia' vivo"
            );
        }
    }
}

/// Quanto aspettare dopo il SIGTERM prima di passare al SIGKILL di riserva.
/// Basta a lasciar girare lo shutdown del lifespan di FastAPI (vedi
/// `termina_processo` sotto) senza far percepire all'utente un ritardo
/// fastidioso alla chiusura dell'app.
const GRACEFUL_SHUTDOWN_TIMEOUT: Duration = Duration::from_secs(3);
const GRACEFUL_SHUTDOWN_POLL_INTERVAL: Duration = Duration::from_millis(50);

/// Behaviour 4: termina il figlio alla chiusura. Chiamata dall'handler
/// `RunEvent::Exit` in `lib.rs`.
///
/// Un backend orfano rimasto attaccato alla porta 8000 e' esattamente il
/// caso che `check_port` intercetterebbe al prossimo avvio -- ma lo
/// segnalerebbe come "un altro programma occupa la porta" (o, se risponde
/// ancora, "Cratory e' gia' aperto"), scambiando un bug nostro per un
/// problema dell'utente. La terminazione vera e propria e' in
/// `termina_processo`, sotto.
pub fn termina(app: &AppHandle) {
    let Some(state) = app.try_state::<BackendProcess>() else {
        return;
    };
    let mut guard = state.0.lock().expect("BackendProcess mutex avvelenato");
    if let Some(mut child) = guard.take() {
        termina_processo(&mut child);
    }
}

/// SIGTERM prima, SIGKILL come riserva -- non SIGKILL diretto.
///
/// uvicorn NON e' "un solo processo senza stato da salvare": il lifespan
/// shutdown in `backend/app/main.py` (intorno alle righe 94-96) chiama
/// `download_dispatcher.stop_retry_loop()` proprio per evitare che il
/// dispatcher dei download, un thread daemon, si svegli durante lo
/// shutdown e rivendichi (`running`) un item che poi non finirebbe mai di
/// lavorare -- e un lifespan shutdown gira solo se il processo riceve un
/// segnale che puo' gestire, non un SIGKILL. Un SIGKILL diretto salterebbe
/// quel passaggio ogni singola volta che l'utente chiude l'app.
///
/// Questo non e' perdita di dati -- il dispatcher si riallinea da solo al
/// prossimo avvio (`download_dispatcher.boot()`) -- ma il commento che
/// c'era qui prima ("nessuno stato da salvare") era semplicemente falso, e
/// un commento falso e' peggio di nessun commento perche' qualcuno ci
/// crede.
///
/// C'e' anche un secondo processo di cui tenere conto, ma che ne' il
/// SIGTERM ne' il SIGKILL a questo `child` possono raggiungere:
/// `slskd_daemon.py` (intorno alla riga 444) avvia slskd con
/// `start_new_session=True`, un processo nipote deliberatamente separato
/// dal gruppo di uvicorn, per sopravvivere ai riavvii col `--reload` di
/// sviluppo. Anche questo si autoripara: il reclaim del pid file intorno a
/// `slskd_daemon.py:482` lo ritrova al prossimo avvio. Niente di tutto
/// questo e' raggiungibile da qui, ed e' per progetto cosi'.
///
/// Il SIGKILL resta come rete di sicurezza per un processo incastrato che
/// non reagisce al SIGTERM entro `GRACEFUL_SHUTDOWN_TIMEOUT`, cosi' la
/// chiusura dell'app non puo' restare bloccata all'infinito.
#[cfg(unix)]
fn termina_processo(child: &mut Child) {
    let pid = child.id() as libc::pid_t;
    // SAFETY: `pid` e' il pid del nostro stesso figlio diretto, ottenuto da
    // `Child::id()`; mandargli SIGTERM e' l'equivalente sicuro di
    // `child.kill()` (che su Unix manda SIGKILL) con un segnale diverso --
    // `std::process::Child` non espone un modo per scegliere il segnale.
    unsafe {
        libc::kill(pid, libc::SIGTERM);
    }
    let deadline = Instant::now() + GRACEFUL_SHUTDOWN_TIMEOUT;
    while Instant::now() < deadline {
        match child.try_wait() {
            Ok(Some(_)) => return,
            Ok(None) => std::thread::sleep(GRACEFUL_SHUTDOWN_POLL_INTERVAL),
            Err(_) => break,
        }
    }
    let _ = child.kill();
    let _ = child.wait();
}

/// Su piattaforme non-Unix non c'e', tramite `std`/`libc`, un equivalente
/// diretto e portabile di SIGTERM per un processo figlio qualunque: questo
/// fix (vedi Important 2 della review del Task 4) e' scritto pensando a
/// Unix, dove gira oggi lo sviluppo. Se in futuro Cratory viene distribuito
/// anche su Windows, questo ramo va rivisto con un meccanismo di chiusura
/// educata nativo di quella piattaforma invece del kill diretto qui sotto.
#[cfg(not(unix))]
fn termina_processo(child: &mut Child) {
    let _ = child.kill();
    let _ = child.wait();
}
