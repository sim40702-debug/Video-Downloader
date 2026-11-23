// lib.rs
// ------------------------------------------------------------
// Qui ci sono i "comandi": le funzioni che la grafica (src/app.js)
// chiama con invoke("nome_comando", { ... }).
// I lavori lunghi girano in un thread separato, così la finestra
// non si blocca mai.
// ------------------------------------------------------------

mod componenti;
mod impostazioni;
mod ytdlp;

use impostazioni::Impostazioni;
use serde::Serialize;
use std::path::PathBuf;
use std::process::{Child, Command};
use std::sync::atomic::AtomicBool;
use std::sync::{Arc, Mutex};
use tauri::{AppHandle, Emitter, Manager, State};
use tauri_plugin_dialog::DialogExt;
use tauri_plugin_notification::NotificationExt;
use tauri_plugin_updater::UpdaterExt;

/// Stato dell'app: il download in corso (per poterlo annullare)
struct Stato {
    processo: Arc<Mutex<Option<Child>>>,
    annullato: Arc<AtomicBool>,
}

/// Cartella dove l'app tiene yt-dlp, FFmpeg e Deno
fn cartella_programmi(app: &AppHandle) -> PathBuf {
    app.path()
        .app_local_data_dir()
        .unwrap_or_else(|_| std::env::temp_dir().join("video-downloader"))
        .join("programmi")
}

fn strumenti(app: &AppHandle) -> Result<ytdlp::Strumenti, String> {
    let cartella = cartella_programmi(app);
    let manca = "Mancano dei componenti: chiudi e riapri l'app per installarli.".to_string();
    Ok(ytdlp::Strumenti {
        ytdlp: componenti::trova(componenti::YTDLP, &cartella).ok_or(manca.clone())?,
        ffmpeg: componenti::trova(componenti::FFMPEG, &cartella).ok_or(manca.clone())?,
        deno: componenti::trova(componenti::DENO, &cartella).ok_or(manca)?,
    })
}

// ---------------- componenti ----------------

/// Quali componenti mancano (lista vuota = tutto pronto)
#[tauri::command]
fn componenti_mancanti(app: AppHandle) -> Vec<String> {
    let cartella = cartella_programmi(&app);
    let mut mancanti = Vec::new();
    for nome in [componenti::YTDLP, componenti::FFMPEG, componenti::DENO] {
        if componenti::trova(nome, &cartella).is_none() {
            mancanti.push(nome.to_string());
        }
    }
    mancanti
}

#[derive(Clone, Serialize)]
struct AvanzamentoComponente {
    nome: String,
    percentuale: f64,
}

/// Scarica i componenti che mancano (avvisa la grafica con l'evento "componenti")
#[tauri::command]
async fn installa_componenti(app: AppHandle) -> Result<(), String> {
    let mancanti = componenti_mancanti(app.clone());
    let cartella = cartella_programmi(&app);
    tauri::async_runtime::spawn_blocking(move || {
        for nome in mancanti {
            let avvisa = |percentuale: f64| {
                let _ = app.emit("componenti", AvanzamentoComponente { nome: nome.clone(), percentuale });
            };
            componenti::installa(&nome, &cartella, &avvisa)?;
        }
        Ok(())
    })
    .await
    .map_err(|e| e.to_string())?
}

/// Aggiorna yt-dlp: così segue i cambiamenti di YouTube.
/// Restituisce la versione dopo l'aggiornamento e ricorda quando è stato fatto.
#[tauri::command]
async fn aggiorna_ytdlp(app: AppHandle) -> Result<String, String> {
    let cartella = cartella_programmi(&app);
    let versione = tauri::async_runtime::spawn_blocking(move || {
        let ytdlp = componenti::trova(componenti::YTDLP, &cartella).ok_or("yt-dlp non c'è.")?;
        let mut cmd = Command::new(&ytdlp);
        cmd.arg("-U");
        ytdlp::nascondi_finestra(&mut cmd);
        let _ = cmd.output();
        Ok::<String, String>(componenti::versione(componenti::YTDLP, &ytdlp))
    })
    .await
    .map_err(|e| e.to_string())??;

    let mut imp = impostazioni::leggi(&app);
    imp.ultimo_controllo_ytdlp = Some(adesso());
    let _ = impostazioni::salva(&app, &imp);
    let _ = app.emit("impostazioni", imp);
    Ok(versione)
}

/// Secondi passati dal 1970 (per ricordare quando è stato fatto qualcosa)
fn adesso() -> u64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0)
}

// ---------------- analisi e download ----------------

#[tauri::command]
async fn analizza(app: AppHandle, url: String) -> Result<ytdlp::InfoVideo, String> {
    let strumenti = strumenti(&app)?;
    tauri::async_runtime::spawn_blocking(move || ytdlp::analizza(&strumenti, &url))
        .await
        .map_err(|e| e.to_string())?
}

#[tauri::command]
async fn scarica(
    app: AppHandle,
    stato: State<'_, Stato>,
    url: String,
    titolo: String,
    modalita: String,
    qualita: u64,
    cartella: String,
) -> Result<String, String> {
    let strumenti = strumenti(&app)?;
    let sostituisci = impostazioni::leggi(&app).se_esiste == "sostituisci";
    let processo = stato.processo.clone();
    let annullato = stato.annullato.clone();
    let finestra = app.clone();

    // Ogni riga di yt-dlp diventa un evento per la grafica
    let avvisa: Arc<dyn Fn(ytdlp::Riga) + Send + Sync> = Arc::new(move |riga| match riga {
        ytdlp::Riga::Progresso(p) => {
            let _ = finestra.emit("progresso", p);
        }
        ytdlp::Riga::Conversione(testo) => {
            let _ = finestra.emit("conversione", testo);
        }
        _ => {}
    });

    tauri::async_runtime::spawn_blocking(move || {
        ytdlp::scarica(
            &strumenti, &url, &titolo, &modalita, qualita,
            &PathBuf::from(cartella), sostituisci, processo, annullato, avvisa,
        )
        .map(|percorso| percorso.to_string_lossy().to_string())
    })
    .await
    .map_err(|e| e.to_string())?
}

#[tauri::command]
fn annulla(stato: State<'_, Stato>) {
    ytdlp::annulla(&stato.processo, &stato.annullato);
}

// ---------------- cartelle ----------------

#[tauri::command]
fn cartella_download() -> String {
    dirs::download_dir()
        .or_else(dirs::home_dir)
        .unwrap_or_default()
        .to_string_lossy()
        .to_string()
}

/// Apre la finestra del sistema per scegliere una cartella
#[tauri::command]
async fn scegli_cartella(app: AppHandle, attuale: String) -> Option<String> {
    app.dialog()
        .file()
        .set_title("Scegli dove salvare i file")
        .set_directory(attuale)
        .blocking_pick_folder()
        .and_then(|scelta| scelta.into_path().ok())
        .map(|percorso| percorso.to_string_lossy().to_string())
}

/// Mostra il file nel Finder (Mac) o in Esplora file (Windows)
#[tauri::command]
fn mostra_file(percorso: String) {
    #[cfg(target_os = "macos")]
    {
        let _ = Command::new("open").arg("-R").arg(&percorso).spawn();
    }
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        let _ = Command::new("explorer").raw_arg(format!("/select,\"{percorso}\"")).spawn();
    }
    #[cfg(target_os = "linux")]
    {
        let cartella = PathBuf::from(&percorso).parent().map(|p| p.to_path_buf()).unwrap_or_default();
        let _ = Command::new("xdg-open").arg(cartella).spawn();
    }
}

/// Controlla che una cartella esista ancora (es. quella salvata l'ultima volta)
#[tauri::command]
fn esiste_cartella(percorso: String) -> bool {
    PathBuf::from(percorso).is_dir()
}

/// Mostra l'avviso del sistema (Centro notifiche su Mac, notifiche su Windows)
#[tauri::command]
fn notifica(app: AppHandle, titolo: String, testo: String) {
    let _ = app.notification().builder().title(titolo).body(testo).show();
}

// ---------------- impostazioni ----------------

#[tauri::command]
fn leggi_impostazioni(app: AppHandle) -> Impostazioni {
    impostazioni::leggi(&app)
}

/// Salva le impostazioni e avvisa tutte le finestre (evento "impostazioni")
#[tauri::command]
fn salva_impostazioni(app: AppHandle, impostazioni: Impostazioni) -> Result<(), String> {
    impostazioni::salva(&app, &impostazioni)?;
    applica_tema(&app, &impostazioni.tema);
    let _ = app.emit("impostazioni", impostazioni);
    Ok(())
}

/// Torna alle impostazioni di partenza
#[tauri::command]
fn ripristina_impostazioni(app: AppHandle) -> Result<Impostazioni, String> {
    let nuove = Impostazioni {
        // l'ora dell'ultimo controllo di yt-dlp non è una scelta: la teniamo
        ultimo_controllo_ytdlp: impostazioni::leggi(&app).ultimo_controllo_ytdlp,
        ..Impostazioni::default()
    };
    salva_impostazioni(app, nuove.clone())?;
    Ok(nuove)
}

/// Chiaro, scuro o come il sistema, per tutte le finestre aperte
fn applica_tema(app: &AppHandle, tema: &str) {
    let scelta = match tema {
        "chiaro" => Some(tauri::Theme::Light),
        "scuro" => Some(tauri::Theme::Dark),
        _ => None, // automatico
    };
    for finestra in app.webview_windows().values() {
        let _ = finestra.set_theme(scelta);
    }
}

#[derive(Serialize)]
struct InfoComponente {
    nome: String,
    versione: String,
    origine: String,
}

/// Versione e provenienza di yt-dlp, FFmpeg e Deno (scheda Componenti)
#[tauri::command]
async fn versioni_componenti(app: AppHandle) -> Vec<InfoComponente> {
    let cartella = cartella_programmi(&app);
    tauri::async_runtime::spawn_blocking(move || {
        let mut lista = Vec::new();
        for nome in [componenti::YTDLP, componenti::FFMPEG, componenti::DENO] {
            match componenti::trova(nome, &cartella) {
                Some(percorso) => lista.push(InfoComponente {
                    nome: nome.to_string(),
                    versione: componenti::versione(nome, &percorso),
                    origine: componenti::origine(&percorso, &cartella),
                }),
                None => lista.push(InfoComponente {
                    nome: nome.to_string(),
                    versione: "manca".into(),
                    origine: String::new(),
                }),
            }
        }
        lista
    })
    .await
    .unwrap_or_default()
}

/// Apre la cartella dove l'app tiene yt-dlp, FFmpeg e Deno
#[tauri::command]
fn mostra_cartella_programmi(app: AppHandle) {
    let cartella = cartella_programmi(&app);
    let _ = std::fs::create_dir_all(&cartella);
    #[cfg(target_os = "macos")]
    let comando = "open";
    #[cfg(windows)]
    let comando = "explorer";
    #[cfg(target_os = "linux")]
    let comando = "xdg-open";
    let _ = Command::new(comando).arg(&cartella).spawn();
}

/// Apre la finestra Impostazioni (o la porta davanti se è già aperta)
#[tauri::command]
async fn apri_impostazioni(app: AppHandle) {
    apri_finestra_impostazioni(&app);
}

fn apri_finestra_impostazioni(app: &AppHandle) {
    if let Some(finestra) = app.get_webview_window("impostazioni") {
        let _ = finestra.show();
        let _ = finestra.set_focus();
        return;
    }
    let finestra = tauri::WebviewWindowBuilder::new(
        app,
        "impostazioni",
        tauri::WebviewUrl::App("impostazioni.html".into()),
    )
    .title("Generali")
    .inner_size(560.0, 520.0)
    .resizable(false)
    .minimizable(false)
    .build();
    if let Ok(finestra) = finestra {
        let tema = impostazioni::leggi(app).tema;
        let scelta = match tema.as_str() {
            "chiaro" => Some(tauri::Theme::Light),
            "scuro" => Some(tauri::Theme::Dark),
            _ => None,
        };
        let _ = finestra.set_theme(scelta);
    }
}

/// Menu del Mac, con "Impostazioni..." e la scorciatoia ⌘,
#[cfg(target_os = "macos")]
fn crea_menu(app: &AppHandle) -> tauri::Result<tauri::menu::Menu<tauri::Wry>> {
    use tauri::menu::{Menu, MenuItem, PredefinedMenuItem, Submenu};
    let impostazioni = MenuItem::with_id(app, "impostazioni", "Impostazioni…", true, Some("CmdOrCtrl+,"))?;
    let menu_app = Submenu::with_items(app, "Video Downloader", true, &[
        &PredefinedMenuItem::about(app, Some("Informazioni su Video Downloader"), None)?,
        &PredefinedMenuItem::separator(app)?,
        &impostazioni,
        &PredefinedMenuItem::separator(app)?,
        &PredefinedMenuItem::hide(app, Some("Nascondi Video Downloader"))?,
        &PredefinedMenuItem::hide_others(app, Some("Nascondi altre"))?,
        &PredefinedMenuItem::show_all(app, Some("Mostra tutte"))?,
        &PredefinedMenuItem::separator(app)?,
        &PredefinedMenuItem::quit(app, Some("Esci da Video Downloader"))?,
    ])?;
    // Senza il menu Modifica, Cmd+C e Cmd+V non funzionano nei campi di testo
    let menu_modifica = Submenu::with_items(app, "Modifica", true, &[
        &PredefinedMenuItem::undo(app, Some("Annulla"))?,
        &PredefinedMenuItem::redo(app, Some("Ripeti"))?,
        &PredefinedMenuItem::separator(app)?,
        &PredefinedMenuItem::cut(app, Some("Taglia"))?,
        &PredefinedMenuItem::copy(app, Some("Copia"))?,
        &PredefinedMenuItem::paste(app, Some("Incolla"))?,
        &PredefinedMenuItem::select_all(app, Some("Seleziona tutto"))?,
    ])?;
    let menu_finestra = Submenu::with_items(app, "Finestra", true, &[
        &PredefinedMenuItem::minimize(app, Some("Contrai"))?,
        &PredefinedMenuItem::close_window(app, Some("Chiudi"))?,
    ])?;
    Menu::with_items(app, &[&menu_app, &menu_modifica, &menu_finestra])
}

// ---------------- aggiornamenti dell'app ----------------

#[derive(Serialize)]
struct NuovaVersione {
    versione: String,
    note: String,
}

/// Chiede a GitHub se c'è una versione nuova dell'app
#[tauri::command]
async fn controlla_aggiornamento(app: AppHandle) -> Result<Option<NuovaVersione>, String> {
    let aggiornamento = app
        .updater()
        .map_err(|e| e.to_string())?
        .check()
        .await
        .map_err(|_| "Non riesco a controllare gli aggiornamenti.".to_string())?;
    Ok(aggiornamento.map(|a| NuovaVersione {
        versione: a.version.clone(),
        note: a.body.clone().unwrap_or_default(),
    }))
}

/// Scarica e installa la nuova versione, poi riavvia l'app
#[tauri::command]
async fn installa_aggiornamento(app: AppHandle) -> Result<(), String> {
    let aggiornamento = app
        .updater()
        .map_err(|e| e.to_string())?
        .check()
        .await
        .map_err(|e| e.to_string())?
        .ok_or("Nessun aggiornamento disponibile.")?;

    let finestra = app.clone();
    let finestra_fine = app.clone();
    let mut scaricati: u64 = 0;
    aggiornamento
        .download_and_install(
            move |pezzo, totale| {
                scaricati += pezzo as u64;
                if let Some(totale) = totale {
                    let _ = finestra.emit("aggiornamento", scaricati as f64 / totale as f64 * 100.0);
                }
            },
            // Download finito: ora lo installa
            move || {
                let _ = finestra_fine.emit("aggiornamento-installo", ());
            },
        )
        .await
        .map_err(|_| "Aggiornamento non riuscito. Riprova più tardi.".to_string())?;
    app.restart();
}

#[tauri::command]
fn versione_app(app: AppHandle) -> String {
    app.package_info().version.to_string()
}

// ---------------- avvio ----------------

pub fn avvia() {
    let costruttore = tauri::Builder::default();

    // Sul Mac c'è la barra dei menu con "Impostazioni..." (⌘,)
    #[cfg(target_os = "macos")]
    let costruttore = costruttore.menu(crea_menu).on_menu_event(|app, evento| {
        if evento.id().as_ref() == "impostazioni" {
            apri_finestra_impostazioni(app);
        }
    });

    costruttore
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_updater::Builder::new().build())
        .plugin(tauri_plugin_notification::init())
        .manage(Stato {
            processo: Arc::new(Mutex::new(None)),
            annullato: Arc::new(AtomicBool::new(false)),
        })
        // All'avvio: tema scelto nelle impostazioni
        .setup(|app| {
            let tema = impostazioni::leggi(app.handle()).tema;
            applica_tema(app.handle(), &tema);
            Ok(())
        })
        // Se chiudi la finestra principale: fermiamo il download e chiudiamo tutto
        // (chiudere la finestra Impostazioni invece non ferma niente)
        .on_window_event(|finestra, evento| {
            if let tauri::WindowEvent::Destroyed = evento {
                if finestra.label() == "main" {
                    let stato = finestra.state::<Stato>();
                    ytdlp::annulla(&stato.processo, &stato.annullato);
                    finestra.app_handle().exit(0);
                }
            }
        })
        .invoke_handler(tauri::generate_handler![
            componenti_mancanti,
            installa_componenti,
            aggiorna_ytdlp,
            analizza,
            scarica,
            annulla,
            cartella_download,
            scegli_cartella,
            mostra_file,
            esiste_cartella,
            notifica,
            controlla_aggiornamento,
            installa_aggiornamento,
            versione_app,
            leggi_impostazioni,
            salva_impostazioni,
            ripristina_impostazioni,
            versioni_componenti,
            mostra_cartella_programmi,
            apri_impostazioni,
        ])
        .run(tauri::generate_context!())
        .expect("errore all'avvio dell'app");
}
