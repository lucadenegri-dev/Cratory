//! L'aggiornamento in-place del guscio desktop.
//!
//! La sequenza (scarica -> termina il backend -> installa -> riavvia) vive
//! qui e non nella pagina: il backend Python gira DA DENTRO il bundle che si
//! sta per sostituire, e un interprete vivo che importa moduli da un `.app`
//! scambiato sotto i piedi fallisce in modi intermittenti e illeggibili.
//! `download` e `install` esistono separati apposta per poter infilare la
//! terminazione in mezzo; `download_and_install`, la scorciatoia documentata,
//! non lascia quello spazio.

use std::path::{Path, PathBuf};

use serde::Serialize;
use tauri::{AppHandle, Emitter};
use tauri_plugin_updater::{Update, UpdaterExt};

use crate::backend;

pub const EVENTO_PROGRESSO: &str = "aggiornamento://progresso";
pub const EVENTO_INSTALLAZIONE: &str = "aggiornamento://installazione";

#[derive(Serialize, Clone)]
pub struct InfoAggiornamento {
    pub versione: String,
    pub note: Option<String>,
    pub data: Option<String>,
}

#[derive(Serialize, Clone)]
struct Progresso {
    scaricati: u64,
    totale: Option<u64>,
}

/// Il codice e' la FASE in cui si e' fallito, non la causa indovinata: le
/// varianti di `tauri_plugin_updater::Error` non sono un contratto stabile, la
/// fase si'. La frase la scrivono i dizionari del frontend, in due lingue; qui
/// viaggiano solo il codice e il dettaglio tecnico.
#[derive(Serialize)]
pub struct ErroreAggiornamento {
    pub codice: &'static str,
    pub dettaglio: String,
}

impl ErroreAggiornamento {
    fn nuovo(codice: &'static str, dettaglio: impl std::fmt::Display) -> Self {
        Self { codice, dettaglio: dettaglio.to_string() }
    }
}

async fn cerca(app: &AppHandle) -> Result<Option<Update>, ErroreAggiornamento> {
    let updater = app
        .updater()
        .map_err(|e| ErroreAggiornamento::nuovo("controllo", e))?;
    updater
        .check()
        .await
        .map_err(|e| ErroreAggiornamento::nuovo("controllo", e))
}

/// `Ok(None)` e' "sei aggiornato", `Err` e' "non ho potuto controllare". Sono
/// due cose diverse e devono restare tali fino allo schermo.
#[tauri::command]
pub async fn controlla_aggiornamento(
    app: AppHandle,
) -> Result<Option<InfoAggiornamento>, ErroreAggiornamento> {
    Ok(cerca(&app).await?.map(|u| InfoAggiornamento {
        versione: u.version.clone(),
        note: u.body.clone(),
        data: u.date.map(|d| d.to_string()),
    }))
}

#[tauri::command]
pub async fn installa_aggiornamento(app: AppHandle) -> Result<(), ErroreAggiornamento> {
    // Prima di ogni altra cosa: se la cartella che contiene il bundle non e'
    // scrivibile, l'installazione fallirebbe DOPO 172 MB di download inutile.
    if let Some(cartella) = cartella_del_bundle() {
        if !scrivibile(&cartella) {
            return Err(ErroreAggiornamento::nuovo("permessi", cartella.display()));
        }
    }

    // Si ricontrolla: l'`Update` non sopravvive fra una chiamata e l'altra e
    // riprenderlo costa una GET del manifesto. Se nel frattempo non c'e' piu'
    // niente da installare, non si inventa un aggiornamento perche' la pagina
    // ne aveva visto uno un minuto prima.
    let Some(aggiornamento) = cerca(&app).await? else {
        return Ok(());
    };

    let mut scaricati: u64 = 0;
    let eco = app.clone();
    let fine = app.clone();
    let byte = aggiornamento
        .download(
            move |pezzo, totale| {
                scaricati += pezzo as u64;
                let _ = eco.emit(EVENTO_PROGRESSO, Progresso { scaricati, totale });
            },
            move || {
                let _ = fine.emit(EVENTO_INSTALLAZIONE, ());
            },
        )
        .await
        .map_err(|e| ErroreAggiornamento::nuovo("scaricamento", e))?;

    // L'ordine e' la ragione d'essere di questo modulo: il backend muore PRIMA
    // che il bundle da cui sta leggendo venga sostituito.
    backend::termina(&app);

    aggiornamento
        .install(byte)
        .map_err(|e| ErroreAggiornamento::nuovo("installazione", e))?;

    // Su macOS l'installazione non riavvia niente da sola.
    app.restart();
}

/// La via d'uscita quando l'installazione fallisce: a quel punto il backend e'
/// gia' stato terminato e l'app e' un guscio vuoto, e solo un riavvio la
/// rimette in piedi.
#[tauri::command]
pub fn riavvia_app(app: AppHandle) {
    app.restart();
}

/// La cartella dentro cui l'updater deve poter scrivere per sostituire il
/// bundle. Il binario sta in `Cratory.app/Contents/MacOS/cratory`: tre livelli
/// sopra c'e' il `.app`, e sopra di lui la cartella che lo contiene.
#[cfg(target_os = "macos")]
fn cartella_del_bundle() -> Option<PathBuf> {
    let exe = std::env::current_exe().ok()?;
    let bundle = exe.parent()?.parent()?.parent()?;
    Some(bundle.parent()?.to_path_buf())
}

#[cfg(not(target_os = "macos"))]
fn cartella_del_bundle() -> Option<PathBuf> {
    None
}

/// Scrivibile dall'utente che sta eseguendo l'app.
///
/// Non `Permissions::readonly()`: su Unix quello guarda i bit del proprietario
/// e mente quando il proprietario e' qualcun altro -- una `/Applications` di
/// un Mac gestito, o un volume montato in sola lettura come il `.dmg` da cui
/// qualcuno potrebbe aver lanciato l'app senza copiarla.
#[cfg(unix)]
fn scrivibile(percorso: &Path) -> bool {
    use std::os::unix::ffi::OsStrExt;
    let Ok(c) = std::ffi::CString::new(percorso.as_os_str().as_bytes()) else {
        return false;
    };
    // SAFETY: `c` e' una CString valida e viva per tutta la chiamata;
    // access(2) legge il puntatore e non ne prende possesso.
    unsafe { libc::access(c.as_ptr(), libc::W_OK) == 0 }
}

#[cfg(not(unix))]
fn scrivibile(_percorso: &Path) -> bool {
    true
}

#[cfg(all(test, unix))]
mod test {
    use super::scrivibile;
    use std::fs;
    use std::os::unix::fs::PermissionsExt;

    // Nota: da root W_OK e' vero ovunque e il secondo test fallirebbe.
    // `cargo test` non va lanciato con sudo.

    #[test]
    fn una_cartella_normale_e_scrivibile() {
        let dir = std::env::temp_dir().join("cratory-scrivibile-si");
        let _ = fs::remove_dir_all(&dir);
        fs::create_dir_all(&dir).unwrap();
        assert!(scrivibile(&dir));
        fs::remove_dir_all(&dir).unwrap();
    }

    #[test]
    fn una_cartella_in_sola_lettura_non_lo_e() {
        let dir = std::env::temp_dir().join("cratory-scrivibile-no");
        let _ = fs::remove_dir_all(&dir);
        fs::create_dir_all(&dir).unwrap();
        fs::set_permissions(&dir, fs::Permissions::from_mode(0o555)).unwrap();
        assert!(!scrivibile(&dir));
        fs::set_permissions(&dir, fs::Permissions::from_mode(0o755)).unwrap();
        fs::remove_dir_all(&dir).unwrap();
    }

    #[test]
    fn un_percorso_inesistente_non_e_scrivibile() {
        assert!(!scrivibile(std::path::Path::new("/cratory-non-esiste/mai")));
    }
}
