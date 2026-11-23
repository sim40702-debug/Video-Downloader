// componenti.rs
// ------------------------------------------------------------
// L'app usa tre programmi gratuiti:
//   - yt-dlp  -> legge i video e li scarica
//   - FFmpeg  -> unisce video + audio e crea gli MP3
//   - Deno    -> serve a yt-dlp per leggere YouTube
//
// Al primo avvio l'app li scarica da GitHub nella sua cartella dati.
// yt-dlp usa sempre la copia dell'app, così si può aggiornare da solo
// (yt-dlp -U) quando YouTube cambia qualcosa.
// FFmpeg e Deno, se sono già installati sul computer (es. con Homebrew),
// vengono usati quelli.
// ------------------------------------------------------------

use std::fs;
use std::io::{Read, Write};
use std::path::{Path, PathBuf};
use std::process::Command;

pub const YTDLP: &str = "yt-dlp";
pub const FFMPEG: &str = "ffmpeg";
pub const DENO: &str = "deno";

/// Nome del file sul disco: su Windows ha ".exe"
pub fn nome_file(programma: &str) -> String {
    if cfg!(windows) {
        format!("{programma}.exe")
    } else {
        programma.to_string()
    }
}

/// Indirizzo da cui scaricare un programma per questo sistema.
/// sistema: "macos", "windows" o "linux"   processore: "aarch64" o "x86_64"
pub fn indirizzo(programma: &str, sistema: &str, processore: &str) -> Option<String> {
    let arm = processore == "aarch64";
    let testo = match (programma, sistema) {
        (YTDLP, "macos") => "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp_macos".to_string(),
        (YTDLP, "windows") => "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe".to_string(),
        (YTDLP, "linux") => "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp_linux".to_string(),

        (FFMPEG, "macos") => {
            let nome = if arm { "darwin-arm64" } else { "darwin-x64" };
            format!("https://github.com/eugeneware/ffmpeg-static/releases/download/b6.0/ffmpeg-{nome}.gz")
        }
        (FFMPEG, "windows") => "https://github.com/eugeneware/ffmpeg-static/releases/download/b6.0/ffmpeg-win32-x64.gz".to_string(),
        (FFMPEG, "linux") => "https://github.com/eugeneware/ffmpeg-static/releases/download/b6.0/ffmpeg-linux-x64.gz".to_string(),

        (DENO, "macos") => {
            let nome = if arm { "aarch64-apple-darwin" } else { "x86_64-apple-darwin" };
            format!("https://github.com/denoland/deno/releases/latest/download/deno-{nome}.zip")
        }
        (DENO, "windows") => "https://github.com/denoland/deno/releases/latest/download/deno-x86_64-pc-windows-msvc.zip".to_string(),
        (DENO, "linux") => "https://github.com/denoland/deno/releases/latest/download/deno-x86_64-unknown-linux-gnu.zip".to_string(),

        _ => return None,
    };
    Some(testo)
}

/// Cartelle dove di solito ci sono i programmi installati a mano
/// (quando l'app parte con un doppio clic spesso non sono nel PATH)
fn cartelle_di_sistema() -> Vec<PathBuf> {
    let mut cartelle: Vec<PathBuf> = Vec::new();
    if let Some(path) = std::env::var_os("PATH") {
        cartelle.extend(std::env::split_paths(&path));
    }
    if cfg!(target_os = "macos") {
        cartelle.push(PathBuf::from("/opt/homebrew/bin")); // Homebrew su Apple Silicon
        cartelle.push(PathBuf::from("/usr/local/bin")); // Homebrew su Intel
    }
    if cfg!(windows) {
        if let Some(locale) = dirs::data_local_dir() {
            cartelle.push(locale.join("Microsoft").join("WinGet").join("Links")); // winget
        }
    }
    if let Some(casa) = dirs::home_dir() {
        cartelle.push(casa.join(".deno").join("bin"));
    }
    cartelle
}

/// Cerca un programma: prima nella cartella dell'app, poi nel sistema
/// (tranne yt-dlp, che usa sempre la copia dell'app).
pub fn trova(programma: &str, cartella_app: &Path) -> Option<PathBuf> {
    let file = nome_file(programma);
    let mio = cartella_app.join(&file);
    if mio.is_file() {
        return Some(mio);
    }
    if programma == YTDLP {
        return None;
    }
    for cartella in cartelle_di_sistema() {
        let possibile = cartella.join(&file);
        if possibile.is_file() {
            return Some(possibile);
        }
    }
    None
}

/// Versione di un programma, letta dalla sua prima riga (es. "ffmpeg version 6.0 ...")
pub fn versione(programma: &str, percorso: &Path) -> String {
    let opzione = if programma == FFMPEG { "-version" } else { "--version" };
    let mut cmd = Command::new(percorso);
    cmd.arg(opzione);
    crate::ytdlp::nascondi_finestra(&mut cmd);
    match cmd.output() {
        Ok(uscita) => {
            let testo = String::from_utf8_lossy(&uscita.stdout).to_string();
            versione_da_testo(programma, &testo)
        }
        Err(_) => "non funziona".into(),
    }
}

/// Prende solo il numero di versione dal testo scritto dal programma
pub fn versione_da_testo(programma: &str, testo: &str) -> String {
    let prima = testo.lines().next().unwrap_or("").trim();
    let pezzi: Vec<&str> = prima.split_whitespace().collect();
    let numero = match programma {
        FFMPEG => pezzi.get(2).copied(),   // "ffmpeg version 6.0 ..."
        DENO => pezzi.get(1).copied(),     // "deno 2.5.6 (stable, ...)"
        _ => pezzi.first().copied(),       // "2026.11.12"
    };
    let numero = numero.unwrap_or("?");
    // Le versioni di FFmpeg a volte sono lunghissime: teniamo la parte iniziale
    numero.split('-').next().unwrap_or(numero).to_string()
}

/// Da dove arriva il programma: dall'app, da Homebrew, da winget...
pub fn origine(percorso: &Path, cartella_app: &Path) -> String {
    let testo = percorso.to_string_lossy().to_lowercase();
    if percorso.starts_with(cartella_app) {
        "dell'app".into()
    } else if testo.contains("homebrew") || testo.starts_with("/usr/local/") {
        "da Homebrew".into()
    } else if testo.contains("winget") {
        "da winget".into()
    } else {
        "dal sistema".into()
    }
}

/// Scarica un programma nella cartella dell'app.
/// avvisa(percentuale) viene chiamata durante il download.
pub fn installa(programma: &str, cartella_app: &Path, avvisa: &dyn Fn(f64)) -> Result<PathBuf, String> {
    let sistema = std::env::consts::OS;
    let processore = std::env::consts::ARCH;
    let url = indirizzo(programma, sistema, processore)
        .ok_or(format!("{programma} non è disponibile per questo sistema."))?;

    fs::create_dir_all(cartella_app).map_err(|e| format!("Non riesco a creare la cartella: {e}"))?;

    // 1) Download in un file temporaneo
    let temporaneo = cartella_app.join(format!("{programma}.download"));
    let risultato = scarica_file(&url, &temporaneo, avvisa);
    if let Err(errore) = risultato {
        let _ = fs::remove_file(&temporaneo);
        return Err(errore);
    }

    // 2) Estrazione (zip o gz) oppure semplice rinomina
    let destinazione = cartella_app.join(nome_file(programma));
    let estratto = if url.ends_with(".zip") {
        estrai_da_zip(&temporaneo, &nome_file(programma), &destinazione)
    } else if url.ends_with(".gz") {
        estrai_gz(&temporaneo, &destinazione)
    } else {
        fs::rename(&temporaneo, &destinazione).map_err(|e| e.to_string())
    };
    let _ = fs::remove_file(&temporaneo);
    estratto?;

    prepara_eseguibile(&destinazione);
    Ok(destinazione)
}

fn scarica_file(url: &str, destinazione: &Path, avvisa: &dyn Fn(f64)) -> Result<(), String> {
    let client = reqwest::blocking::Client::builder()
        .user_agent("Video-Downloader")
        .timeout(None)
        .build()
        .map_err(|e| e.to_string())?;
    let mut risposta = client
        .get(url)
        .send()
        .map_err(|_| "Download non riuscito: controlla la connessione a Internet.".to_string())?;
    if !risposta.status().is_success() {
        return Err(format!("Download non riuscito (errore {}).", risposta.status().as_u16()));
    }
    let totale = risposta.content_length().unwrap_or(0);
    let mut file = fs::File::create(destinazione).map_err(|e| e.to_string())?;
    let mut buffer = vec![0u8; 256 * 1024];
    let mut scaricati: u64 = 0;
    loop {
        let letti = risposta
            .read(&mut buffer)
            .map_err(|_| "Connessione interrotta durante il download.".to_string())?;
        if letti == 0 {
            break;
        }
        file.write_all(&buffer[..letti]).map_err(|e| e.to_string())?;
        scaricati += letti as u64;
        if totale > 0 {
            avvisa(scaricati as f64 / totale as f64 * 100.0);
        }
    }
    Ok(())
}

fn estrai_gz(origine: &Path, destinazione: &Path) -> Result<(), String> {
    let file = fs::File::open(origine).map_err(|e| e.to_string())?;
    let mut lettore = flate2::read::GzDecoder::new(file);
    let mut uscita = fs::File::create(destinazione).map_err(|e| e.to_string())?;
    std::io::copy(&mut lettore, &mut uscita).map_err(|_| "File scaricato non valido.".to_string())?;
    Ok(())
}

fn estrai_da_zip(origine: &Path, nome: &str, destinazione: &Path) -> Result<(), String> {
    let file = fs::File::open(origine).map_err(|e| e.to_string())?;
    let mut archivio = zip::ZipArchive::new(file).map_err(|_| "File scaricato non valido.".to_string())?;
    let mut interno = archivio
        .by_name(nome)
        .map_err(|_| format!("Nello zip non c'è {nome}."))?;
    let mut uscita = fs::File::create(destinazione).map_err(|e| e.to_string())?;
    std::io::copy(&mut interno, &mut uscita).map_err(|e| e.to_string())?;
    Ok(())
}

/// Rende il file eseguibile (Mac e Linux) e toglie il blocco di macOS
fn prepara_eseguibile(percorso: &Path) {
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        let _ = fs::set_permissions(percorso, fs::Permissions::from_mode(0o755));
    }
    if cfg!(target_os = "macos") {
        let _ = Command::new("xattr").args(["-d", "com.apple.quarantine"]).arg(percorso).output();
        // Sui Mac Apple Silicon ogni programma deve avere almeno una firma "ad-hoc"
        let _ = Command::new("codesign").args(["--force", "--sign", "-"]).arg(percorso).output();
    }
}

#[cfg(test)]
mod test {
    use super::*;

    #[test]
    fn indirizzi_per_ogni_sistema() {
        for sistema in ["macos", "windows", "linux"] {
            for programma in [YTDLP, FFMPEG, DENO] {
                let url = indirizzo(programma, sistema, "x86_64").unwrap();
                assert!(url.starts_with("https://github.com/"), "{url}");
            }
        }
        assert!(indirizzo(FFMPEG, "macos", "aarch64").unwrap().contains("darwin-arm64"));
        assert!(indirizzo(DENO, "macos", "aarch64").unwrap().contains("aarch64-apple-darwin"));
        assert!(indirizzo(DENO, "macos", "x86_64").unwrap().contains("x86_64-apple-darwin"));
        assert!(indirizzo(YTDLP, "android", "x86_64").is_none());
    }

    #[test]
    fn versioni_lette_bene() {
        assert_eq!(versione_da_testo(YTDLP, "2026.11.12\n"), "2026.11.12");
        assert_eq!(versione_da_testo(FFMPEG, "ffmpeg version 6.0-static https://x Copyright"), "6.0");
        assert_eq!(versione_da_testo(DENO, "deno 2.5.6 (stable, release, aarch64-apple-darwin)\nv8 13"), "2.5.6");
        assert_eq!(versione_da_testo(DENO, ""), "?");
    }

    #[test]
    fn origini() {
        let app = Path::new("/Users/s/Library/Application Support/x/programmi");
        assert_eq!(origine(&app.join("ffmpeg"), app), "dell'app");
        assert_eq!(origine(Path::new("/opt/homebrew/bin/deno"), app), "da Homebrew");
        assert_eq!(origine(Path::new("/usr/local/bin/deno"), app), "da Homebrew");
        assert_eq!(origine(Path::new("C:\\Users\\s\\AppData\\Local\\Microsoft\\WinGet\\Links\\deno.exe"), app), "da winget");
    }

    #[test]
    fn ytdlp_solo_dalla_cartella_app() {
        let vuota = std::env::temp_dir().join("vd-test-vuota");
        let _ = fs::create_dir_all(&vuota);
        assert!(trova(YTDLP, &vuota).is_none());
    }
    /// Scarica davvero FFmpeg e Deno da GitHub (parte solo con VD_TEST_RETE=1)
    #[test]
    fn scaricamento_vero() {
        if std::env::var("VD_TEST_RETE").is_err() {
            return;
        }
        let cartella = std::env::temp_dir().join("vd-test-componenti");
        let _ = fs::remove_dir_all(&cartella);
        for programma in [FFMPEG, DENO] {
            let percorso = installa(programma, &cartella, &|_| {}).unwrap();
            let uscita = Command::new(&percorso).arg(if programma == FFMPEG { "-version" } else { "--version" }).output().unwrap();
            assert!(uscita.status.success(), "{programma} non parte");
        }
        // Non restano file temporanei
        let mut nomi: Vec<String> = fs::read_dir(&cartella).unwrap()
            .map(|v| v.unwrap().file_name().to_string_lossy().to_string()).collect();
        nomi.sort();
        assert_eq!(nomi, vec![nome_file(DENO), nome_file(FFMPEG)]);
        fs::remove_dir_all(&cartella).unwrap();
    }
}
