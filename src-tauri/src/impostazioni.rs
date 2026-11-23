// impostazioni.rs
// ------------------------------------------------------------
// Le impostazioni dell'app, salvate nel file impostazioni.json
// nella cartella di configurazione dell'app.
// Le usano sia la finestra principale sia la finestra Impostazioni.
// ------------------------------------------------------------

use serde::{Deserialize, Serialize};
use std::fs;
use std::path::PathBuf;
use tauri::{AppHandle, Manager};

#[derive(Serialize, Deserialize, Clone, Debug, PartialEq)]
#[serde(default)] // se nel file manca qualcosa, usa il valore di partenza
pub struct Impostazioni {
    /// "automatico", "chiaro" oppure "scuro"
    pub tema: String,
    /// Avviso del sistema quando finisce un download
    pub notifiche: bool,
    /// Controllare gli aggiornamenti dell'app all'avvio
    pub controlla_aggiornamenti: bool,
    /// Cartella dove salvare ("" = Download)
    pub cartella: String,
    /// "video" oppure "audio": quello scelto quando apri l'app
    pub formato: String,
    /// Altezza video preferita (es. 1080)
    pub qualita_video: u64,
    /// Qualita' MP3 in kbps (es. 192)
    pub qualita_audio: u64,
    /// "titolo", "canale-titolo" oppure "data-titolo"
    pub nome_file: String,
    /// "copia" (crea Titolo (2)) oppure "sostituisci"
    pub se_esiste: String,
    /// Aggiornare yt-dlp a ogni avvio
    pub aggiorna_ytdlp: bool,
    /// Quando yt-dlp e' stato controllato l'ultima volta (secondi dal 1970)
    pub ultimo_controllo_ytdlp: Option<u64>,
}

impl Default for Impostazioni {
    fn default() -> Self {
        Impostazioni {
            tema: "automatico".into(),
            notifiche: true,
            controlla_aggiornamenti: true,
            cartella: String::new(),
            formato: "video".into(),
            qualita_video: 1080,
            qualita_audio: 192,
            nome_file: "titolo".into(),
            se_esiste: "copia".into(),
            aggiorna_ytdlp: true,
            ultimo_controllo_ytdlp: None,
        }
    }
}

fn percorso_file(app: &AppHandle) -> PathBuf {
    app.path()
        .app_config_dir()
        .unwrap_or_else(|_| std::env::temp_dir().join("video-downloader"))
        .join("impostazioni.json")
}

/// Legge le impostazioni. Se il file non c'e' o e' rovinato, usa quelle di partenza.
pub fn leggi(app: &AppHandle) -> Impostazioni {
    match fs::read_to_string(percorso_file(app)) {
        Ok(testo) => serde_json::from_str(&testo).unwrap_or_default(),
        Err(_) => Impostazioni::default(),
    }
}

/// Salva le impostazioni nel file
pub fn salva(app: &AppHandle, impostazioni: &Impostazioni) -> Result<(), String> {
    let percorso = percorso_file(app);
    if let Some(cartella) = percorso.parent() {
        fs::create_dir_all(cartella).map_err(|e| e.to_string())?;
    }
    let testo = serde_json::to_string_pretty(impostazioni).map_err(|e| e.to_string())?;
    fs::write(percorso, testo).map_err(|_| "Non riesco a salvare le impostazioni.".to_string())
}

#[cfg(test)]
mod test {
    use super::*;

    #[test]
    fn valori_di_partenza() {
        let i = Impostazioni::default();
        assert_eq!(i.tema, "automatico");
        assert_eq!(i.qualita_video, 1080);
        assert_eq!(i.qualita_audio, 192);
        assert!(i.notifiche && i.aggiorna_ytdlp && i.controlla_aggiornamenti);
    }

    #[test]
    fn file_vecchio_o_incompleto() {
        // Un file con solo alcune impostazioni: le altre prendono il valore di partenza
        let i: Impostazioni = serde_json::from_str(r#"{"tema":"scuro","qualita_video":720}"#).unwrap();
        assert_eq!(i.tema, "scuro");
        assert_eq!(i.qualita_video, 720);
        assert_eq!(i.formato, "video");
        // Un file rovinato non blocca l'app
        let rovinato: Impostazioni = serde_json::from_str("{ciao").unwrap_or_default();
        assert_eq!(rovinato, Impostazioni::default());
    }
}
