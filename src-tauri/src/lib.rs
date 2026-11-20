// lib.rs
// ------------------------------------------------------------
// Qui ci sono i "comandi": le funzioni che la grafica (src/app.js)
// chiama con invoke("nome_comando", { ... }).
// I lavori lunghi girano in un thread separato, così la finestra
// non si blocca mai.
// ------------------------------------------------------------

mod componenti;
mod ytdlp;

use serde::Serialize;
use std::path::PathBuf;
use std::process::{Child, Command};
use std::sync::atomic::AtomicBool;
use std::sync::{Arc, Mutex};
use tauri::{AppHandle, Emitter, Manager, State};
use tauri_plugin_dialog::DialogExt;
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

/// Aggiorna yt-dlp (all'avvio, in sottofondo): così segue i cambiamenti di YouTube
#[tauri::command]
async fn aggiorna_ytdlp(app: AppHandle) {
    let cartella = cartella_programmi(&app);
    let _ = tauri::async_runtime::spawn_blocking(move || {
        if let Some(ytdlp) = componenti::trova(componenti::YTDLP, &cartella) {
            let mut cmd = Command::new(ytdlp);
            cmd.arg("-U");
            ytdlp::nascondi_finestra(&mut cmd);
            let _ = cmd.output();
        }
    })
    .await;
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
            &PathBuf::from(cartella), processo, annullato, avvisa,
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
    let mut scaricati: u64 = 0;
    aggiornamento
        .download_and_install(
            move |pezzo, totale| {
                scaricati += pezzo as u64;
                if let Some(totale) = totale {
                    let _ = finestra.emit("aggiornamento", scaricati as f64 / totale as f64 * 100.0);
                }
            },
            || {},
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
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_updater::Builder::new().build())
        .manage(Stato {
            processo: Arc::new(Mutex::new(None)),
            annullato: Arc::new(AtomicBool::new(false)),
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
            controlla_aggiornamento,
            installa_aggiornamento,
            versione_app,
        ])
        .run(tauri::generate_context!())
        .expect("errore all'avvio dell'app");
}
