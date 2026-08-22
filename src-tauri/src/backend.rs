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
use std::path::PathBuf;
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
/// Si distingue "c'e' gia' un Cratory aperto" da "un altro programma occupa
/// la porta" interrogando la stessa rotta che il passo 3 usa per capire che
/// il backend e' pronto: se qualcosa risponde li' con la forma esatta che
/// solo il nostro backend produce (`{"completed": <bool>}`), e' un Cratory;
/// altrimenti e' un programma qualunque che ha preso la porta prima di noi.
/// Le due situazioni chiedono all'utente azioni diverse (chiudere l'altra
/// finestra di Cratory, oppure liberare la porta da un programma estraneo),
/// quindi meritano due messaggi diversi.
fn check_port() -> PortCheck {
    // Bind-e-rilascia-subito: se il bind riesce la porta era libera davvero,
    // e va rilasciata immediatamente perche' e' uvicorn (il prossimo bind,
    // fatto dal processo figlio) a doverla tenere lui.
    if TcpListener::bind((BACKEND_HOST, BACKEND_PORT)).is_ok() {
        return PortCheck::Libera;
    }

    match http_get(&setup_state_url(), Duration::from_secs(2)) {
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

fn http_get(url: &str, timeout: Duration) -> Option<String> {
    let client = reqwest::blocking::Client::builder()
        .timeout(timeout)
        .build()
        .ok()?;
    let resp = client.get(url).send().ok()?;
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
fn python_command() -> &'static str {
    "python3"
}

fn backend_dir() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../backend")
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
fn spawn_backend(app: &AppHandle) -> std::io::Result<Child> {
    Command::new(python_command())
        .args([
            "-m",
            "uvicorn",
            "app.main:app",
            "--port",
            &BACKEND_PORT.to_string(),
            "--host",
            BACKEND_HOST,
        ])
        .current_dir(backend_dir())
        // Le tre env che il backend sa leggere (vedi backend/app/core/paths.py
        // e backend/app/services/system_probe.py). Il meccanismo e' qui;
        // CRATORY_DATA_DIR e CRATORY_BIN_DIR restano vuote finche' il Task 5
        // non decide dove vive la cartella dati scrivibile del bundle (fuori
        // dal .app firmato) e dove i binari esterni sono stati installati:
        // vuote equivale al comportamento di oggi (default = cartella del
        // backend), quindi lo sviluppo non cambia sotto i piedi.
        .env("CRATORY_DATA_DIR", "")
        .env("CRATORY_BIN_DIR", "")
        .env(
            "CRATORY_VERSION",
            app.package_info().version.to_string(),
        )
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
}

/// Behaviour 3: aspetta che il backend risponda, entro un limite di tempo.
fn wait_until_ready() -> bool {
    let deadline = Instant::now() + READY_TIMEOUT;
    let url = setup_state_url();
    while Instant::now() < deadline {
        if http_get(&url, Duration::from_millis(500)).is_some() {
            return true;
        }
        std::thread::sleep(READY_POLL_INTERVAL);
    }
    false
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
    match check_port() {
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
                    "La porta {BACKEND_PORT} e' occupata da un altro \
                     programma, non da Cratory. Cratory non puo' cercare \
                     una porta alternativa: la redirect URI di Spotify e' \
                     registrata proprio su questo numero, e su una porta \
                     diversa l'accesso a Spotify smetterebbe di funzionare. \
                     Libera la porta {BACKEND_PORT} e riapri l'app."
                ),
            );
            return;
        }
        PortCheck::Libera => {}
    }

    let mut child = match spawn_backend(&app) {
        Ok(child) => child,
        Err(err) => {
            fatal_error(
                &app,
                "Backend non avviato",
                &format!(
                    "Impossibile lanciare '{} -m uvicorn': {err}. \
                     E' installato e disponibile nel PATH?",
                    python_command()
                ),
            );
            return;
        }
    };

    let output_log: Arc<Mutex<VecDeque<String>>> = Arc::new(Mutex::new(VecDeque::new()));
    spawn_line_reader(child.stdout.take(), Arc::clone(&output_log));
    spawn_line_reader(child.stderr.take(), Arc::clone(&output_log));

    let pronto = wait_until_ready();

    // Da qui in poi il figlio va tracciato nello stato condiviso in ogni
    // caso, che l'avvio sia riuscito o no: se scade il timeout il processo
    // potrebbe comunque partire un attimo dopo, e senza tracciarlo qui
    // resterebbe un orfano attaccato alla porta che nessuno termina piu'.
    let state = app.state::<BackendProcess>();
    *state.0.lock().expect("BackendProcess mutex avvelenato") = Some(child);

    if !pronto {
        let ultime_righe = output_log
            .lock()
            .expect("output_log mutex avvelenato")
            .iter()
            .cloned()
            .collect::<Vec<_>>()
            .join("\n");
        fatal_error(
            &app,
            "Il backend non e' partito",
            &format!(
                "Nessuna risposta da {} entro {} secondi.\n\nUltime righe di output:\n{}",
                setup_state_url(),
                READY_TIMEOUT.as_secs(),
                if ultime_righe.is_empty() {
                    "(nessun output)".to_string()
                } else {
                    ultime_righe
                }
            ),
        );
        return;
    }

    if let Some(window) = app.get_webview_window("main") {
        let _ = window.show();
    }
}

/// Behaviour 4: termina il figlio alla chiusura. Chiamata dall'handler
/// `RunEvent::Exit` in `lib.rs`.
///
/// Un backend orfano rimasto attaccato alla porta 8000 e' esattamente il
/// caso che `check_port` intercetterebbe al prossimo avvio -- ma lo
/// segnalerebbe come "un altro programma occupa la porta" (o, se risponde
/// ancora, "Cratory e' gia' aperto"), scambiando un bug nostro per un
/// problema dell'utente. `kill` (SIGKILL su Unix) e' brutale ma va bene qui:
/// uvicorn senza `--reload` e' un solo processo senza stato da salvare, e la
/// `wait()` successiva serve solo ad essere certi che sia morto per davvero
/// prima di considerare la porta libera per il prossimo avvio.
pub fn termina(app: &AppHandle) {
    let Some(state) = app.try_state::<BackendProcess>() else {
        return;
    };
    let mut guard = state.0.lock().expect("BackendProcess mutex avvelenato");
    if let Some(mut child) = guard.take() {
        let _ = child.kill();
        let _ = child.wait();
    }
}
