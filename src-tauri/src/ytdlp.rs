// ytdlp.rs
// ------------------------------------------------------------
// Tutto quello che riguarda yt-dlp:
//   - controllare il link
//   - leggere le informazioni del video (analizza)
//   - scaricare con l'avanzamento in tempo reale (scarica)
//   - annullare e cancellare i file a metà
//   - trasformare gli errori in messaggi chiari in italiano
// ------------------------------------------------------------

use regex::Regex;
use serde::Serialize;
use serde_json::Value;
use std::fs;
use std::io::{BufRead, BufReader};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};

/// I percorsi dei tre programmi
pub struct Strumenti {
    pub ytdlp: PathBuf,
    pub ffmpeg: PathBuf,
    pub deno: PathBuf,
}

/// Una qualità video disponibile (es. 1080p, circa 41 MB)
#[derive(Serialize, Debug, PartialEq)]
pub struct Qualita {
    pub altezza: u64,
    pub dimensione: Option<u64>,
}

/// Le informazioni che mostriamo nella finestra
#[derive(Serialize, Debug)]
pub struct InfoVideo {
    pub url: String,
    pub titolo: String,
    pub canale: String,
    pub durata: Option<f64>,
    pub visualizzazioni: Option<u64>,
    pub copertina: String,
    pub qualita: Vec<Qualita>,
}

/// Una riga scritta da yt-dlp durante il download
#[derive(Serialize, Debug, PartialEq, Clone)]
pub struct Progresso {
    pub percentuale: f64,
    pub scaricati: f64,
    pub totale: Option<f64>,
    pub velocita: Option<f64>,
    pub rimasto: Option<f64>,
    /// "video", "audio" oppure "" (file unico)
    pub parte: String,
}

#[derive(Debug, PartialEq)]
pub enum Riga {
    Progresso(Progresso),
    Conversione(String),
    File(String),
    Altro,
}

// ------------------------------------------------------------
// Controlli e nomi dei file
// ------------------------------------------------------------

/// true se il testo sembra un link di un video YouTube
pub fn url_valido(url: &str) -> bool {
    let regola = Regex::new(
        r"^(https?://)?(www\.|m\.|music\.)?(youtube\.com/(watch\?(.*&)?v=|shorts/|live/|embed/)|youtu\.be/)[A-Za-z0-9_-]{11}",
    )
    .unwrap();
    regola.is_match(url.trim())
}

/// Toglie dal titolo i caratteri che non vanno bene nei nomi dei file
/// (su Mac e Windows) e lo accorcia se è troppo lungo.
pub fn pulisci_nome(titolo: &str) -> String {
    let mut nome = String::new();
    for carattere in titolo.chars() {
        if "/\\:*?\"<>|".contains(carattere) {
            nome.push('-');
        } else if !carattere.is_control() {
            nome.push(carattere);
        }
    }
    let mut nome: String = nome.trim().trim_matches('.').trim().to_string();
    if nome.chars().count() > 150 {
        nome = nome.chars().take(150).collect::<String>().trim().to_string();
    }
    if nome.is_empty() {
        nome = "video".to_string();
    }
    nome
}

/// Trova un nome che non esiste ancora: "Canzone.mp3" -> "Canzone (2).mp3"
pub fn nome_file_libero(cartella: &Path, nome: &str, estensione: &str) -> PathBuf {
    let mut percorso = cartella.join(format!("{nome}.{estensione}"));
    let mut numero = 2;
    while percorso.exists() {
        percorso = cartella.join(format!("{nome} ({numero}).{estensione}"));
        numero += 1;
    }
    percorso
}

/// Controlla che si possa salvare nella cartella
pub fn controlla_cartella(cartella: &Path) -> Result<(), String> {
    if !cartella.exists() {
        return Err(format!("La cartella non esiste:\n{}", cartella.display()));
    }
    if !cartella.is_dir() {
        return Err("Il percorso scelto non è una cartella.".to_string());
    }
    // Proviamo a creare un file vuoto per vedere se abbiamo i permessi
    let prova = cartella.join(".video-downloader-prova");
    match fs::write(&prova, b"") {
        Ok(_) => {
            let _ = fs::remove_file(&prova);
            Ok(())
        }
        Err(_) => Err("Non hai i permessi per salvare in questa cartella. Scegline un'altra.".to_string()),
    }
}

// ------------------------------------------------------------
// Messaggi di errore
// ------------------------------------------------------------

/// Trasforma un errore di yt-dlp in un messaggio chiaro
pub fn messaggio_errore(testo: &str) -> String {
    let t = testo.to_lowercase();
    let contiene = |parole: &[&str]| parole.iter().any(|p| t.contains(p));

    if contiene(&["private video"]) {
        return "Questo video è privato: non si può scaricare.".into();
    }
    if contiene(&["sign in to confirm your age", "age-restricted"]) {
        return "Questo video ha limiti di età e richiede l'accesso: non si può scaricare.".into();
    }
    if contiene(&["members-only", "join this channel"]) {
        return "Questo video è riservato ai membri del canale.".into();
    }
    if contiene(&["premieres in", "this live event will begin"]) {
        return "Il video non è ancora disponibile: la prima o la diretta non è iniziata.".into();
    }
    if contiene(&["not available in your country"]) {
        return "Questo video non è disponibile nel tuo paese.".into();
    }
    if contiene(&["copyright"]) {
        return "Il video è stato rimosso per motivi di copyright.".into();
    }
    if contiene(&["video unavailable", "this video is not available"]) {
        return "Il video non è disponibile: è stato rimosso oppure il link è sbagliato.".into();
    }
    if t.contains("sign in to confirm you") && t.contains("bot") {
        return "YouTube ha bloccato la richiesta per un momento. Riprova tra qualche minuto.".into();
    }
    if contiene(&["http error 403"]) {
        return "YouTube ha rifiutato il download. Chiudi e riapri l'app: yt-dlp si aggiorna da solo.".into();
    }
    if contiene(&["http error 429", "too many requests"]) {
        return "Troppe richieste a YouTube. Aspetta qualche minuto e riprova.".into();
    }
    if contiene(&["requested format is not available"]) {
        return "La qualità scelta non è disponibile. Scegline un'altra.".into();
    }
    if contiene(&["no space left"]) {
        return "Spazio su disco esaurito. Libera spazio e riprova.".into();
    }
    if contiene(&["permission denied", "operation not permitted"]) {
        return "Non hai i permessi per salvare in questa cartella. Scegline un'altra.".into();
    }
    if contiene(&[
        "getaddrinfo", "nodename nor servname", "name or service not known",
        "network is unreachable", "connection", "timed out",
    ]) {
        return "Connessione a Internet assente o interrotta. Controlla la rete e riprova.".into();
    }
    if contiene(&["unsupported url", "is not a valid url"]) {
        return "Il link non è supportato. Controlla di aver copiato un link di YouTube.".into();
    }
    let ultima = testo.trim().lines().last().unwrap_or("Errore sconosciuto.").replace("ERROR: ", "");
    format!("Qualcosa non ha funzionato: {ultima}")
}

// ------------------------------------------------------------
// Avvio di yt-dlp
// ------------------------------------------------------------

/// Prepara il comando yt-dlp con le opzioni comuni
fn comando(strumenti: &Strumenti) -> Command {
    let mut cmd = Command::new(&strumenti.ytdlp);
    cmd.arg("--no-playlist")
        .arg("--no-colors")
        .arg("--ffmpeg-location")
        .arg(&strumenti.ffmpeg)
        .arg("--js-runtimes")
        .arg(format!("deno:{}", strumenti.deno.display()));
    nascondi_finestra(&mut cmd);
    cmd
}

/// Su Windows evita che si apra una finestra nera per ogni comando
#[allow(unused_variables)]
pub fn nascondi_finestra(cmd: &mut Command) {
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        cmd.creation_flags(0x0800_0000); // CREATE_NO_WINDOW
    }
}

/// Legge le informazioni del video senza scaricarlo
pub fn analizza(strumenti: &Strumenti, url: &str) -> Result<InfoVideo, String> {
    let url = url.trim();
    if !url_valido(url) {
        return Err("Il link non sembra un video di YouTube. Esempio: https://www.youtube.com/watch?v=...".into());
    }
    let uscita = comando(strumenti)
        .args(["-J", "--no-warnings", url])
        .output()
        .map_err(|_| "Non riesco ad avviare yt-dlp.".to_string())?;
    if !uscita.status.success() {
        let errore = String::from_utf8_lossy(&uscita.stderr);
        return Err(messaggio_errore(&errore));
    }
    let json: Value = serde_json::from_slice(&uscita.stdout)
        .map_err(|_| "yt-dlp ha risposto in modo strano. Riprova.".to_string())?;
    if json["is_live"].as_bool() == Some(true) {
        return Err("Le dirette in corso non si possono scaricare. Riprova quando la diretta è finita.".into());
    }
    Ok(leggi_info(&json))
}

/// Prende dal JSON di yt-dlp solo quello che ci serve
pub fn leggi_info(json: &Value) -> InfoVideo {
    let testo = |chiave: &str| json[chiave].as_str().unwrap_or("").to_string();
    let id = testo("id");
    let mut canale = testo("uploader");
    if canale.is_empty() {
        canale = testo("channel");
    }

    InfoVideo {
        url: json["webpage_url"].as_str().unwrap_or("").to_string(),
        titolo: if testo("title").is_empty() { "Senza titolo".into() } else { testo("title") },
        canale,
        durata: json["duration"].as_f64(),
        visualizzazioni: json["view_count"].as_u64(),
        // mqdefault è già in 16:9, senza bande nere
        copertina: format!("https://i.ytimg.com/vi/{id}/mqdefault.jpg"),
        qualita: qualita_disponibili(json),
    }
}

/// Le altezze video disponibili, dalla più alta, con la dimensione stimata
pub fn qualita_disponibili(json: &Value) -> Vec<Qualita> {
    let vuoto = vec![];
    let formati = json["formats"].as_array().unwrap_or(&vuoto);

    // La traccia audio migliore (serve per stimare la dimensione totale)
    let mut audio: u64 = 0;
    for f in formati {
        if f["vcodec"].as_str() == Some("none") && f["acodec"].as_str() != Some("none") {
            audio = audio.max(dimensione(f));
        }
    }

    let mut lista: Vec<Qualita> = Vec::new();
    for f in formati {
        let altezza = f["height"].as_u64().unwrap_or(0);
        if altezza == 0 || f["vcodec"].as_str() == Some("none") || f["ext"].as_str() == Some("mhtml") {
            continue;
        }
        let peso = dimensione(f);
        match lista.iter_mut().find(|q| q.altezza == altezza) {
            Some(esistente) => {
                if peso > 0 {
                    esistente.dimensione = Some(esistente.dimensione.unwrap_or(0).max(peso + audio));
                }
            }
            None => lista.push(Qualita {
                altezza,
                dimensione: if peso > 0 { Some(peso + audio) } else { None },
            }),
        }
    }
    lista.sort_by_key(|q| std::cmp::Reverse(q.altezza));
    lista
}

fn dimensione(formato: &Value) -> u64 {
    formato["filesize"]
        .as_u64()
        .or_else(|| formato["filesize_approx"].as_u64())
        .unwrap_or(0)
}

// ------------------------------------------------------------
// Download
// ------------------------------------------------------------

/// Le opzioni di yt-dlp per il formato scelto
pub fn argomenti_formato(modalita: &str, qualita: u64) -> Vec<String> {
    if modalita == "audio" {
        vec![
            "-f".into(), "bestaudio/best".into(),
            "-x".into(), "--audio-format".into(), "mp3".into(),
            "--audio-quality".into(), format!("{qualita}K"),
        ]
    } else {
        // Prima la risoluzione scelta, poi MP4, poi H.264 (il più compatibile)
        vec![
            "-f".into(), "bv*+ba/b".into(),
            "-S".into(), format!("res:{qualita},ext:mp4:m4a,vcodec:h264"),
            "--merge-output-format".into(), "mp4".into(),
        ]
    }
}

/// Capisce cosa dice una riga scritta da yt-dlp
pub fn leggi_riga(riga: &str) -> Riga {
    let numero = |testo: &str| -> Option<f64> { testo.trim().parse::<f64>().ok() };

    if let Some(resto) = riga.strip_prefix("VDPROG|") {
        let pezzi: Vec<&str> = resto.split('|').collect();
        if pezzi.len() < 7 {
            return Riga::Altro;
        }
        let scaricati = numero(pezzi[0]).unwrap_or(0.0);
        let totale = numero(pezzi[1]).or(numero(pezzi[2]));
        let percentuale = match totale {
            Some(t) if t > 0.0 => (scaricati / t * 100.0).min(100.0),
            _ => 0.0,
        };
        let parte = if pezzi[5] == "none" {
            "audio"
        } else if pezzi[6] == "none" {
            "video"
        } else {
            ""
        };
        return Riga::Progresso(Progresso {
            percentuale,
            scaricati,
            totale,
            velocita: numero(pezzi[3]),
            rimasto: numero(pezzi[4]),
            parte: parte.to_string(),
        });
    }
    if let Some(resto) = riga.strip_prefix("VDPOST|") {
        let pezzi: Vec<&str> = resto.split('|').collect();
        if pezzi.len() == 2 && pezzi[1] == "started" {
            let testo = match pezzi[0] {
                "Merger" => "Unisco video e audio...",
                "ExtractAudio" => "Creo il file MP3...",
                "MoveFiles" => return Riga::Altro,
                _ => "Preparo il file...",
            };
            return Riga::Conversione(testo.to_string());
        }
        return Riga::Altro;
    }
    if let Some(percorso) = riga.strip_prefix("VDFILE|") {
        return Riga::File(percorso.trim().to_string());
    }
    Riga::Altro
}

/// Scarica il video o l'audio. Restituisce il percorso del file creato.
#[allow(clippy::too_many_arguments)]
pub fn scarica(
    strumenti: &Strumenti,
    url: &str,
    titolo: &str,
    modalita: &str,
    qualita: u64,
    cartella: &Path,
    processo: Arc<Mutex<Option<Child>>>,
    annullato: Arc<AtomicBool>,
    avvisa: Arc<dyn Fn(Riga) + Send + Sync>,
) -> Result<PathBuf, String> {
    controlla_cartella(cartella)?;
    annullato.store(false, Ordering::SeqCst);

    // Nome del file finale, senza sovrascrivere quelli che ci sono già
    let estensione = if modalita == "audio" { "mp3" } else { "mp4" };
    let previsto = nome_file_libero(cartella, &pulisci_nome(titolo), estensione);
    let base = previsto.file_stem().unwrap().to_string_lossy().to_string();
    // Il simbolo % per yt-dlp ha un significato speciale: va raddoppiato
    let modello = cartella.join(format!("{}.%(ext)s", base.replace('%', "%%")));

    let mut cmd = comando(strumenti);
    cmd.args(argomenti_formato(modalita, qualita))
        .args(["--newline", "--quiet", "--progress", "--no-warnings"])
        .arg("--progress-template")
        .arg("download:VDPROG|%(progress.downloaded_bytes)s|%(progress.total_bytes)s|%(progress.total_bytes_estimate)s|%(progress.speed)s|%(progress.eta)s|%(info.vcodec)s|%(info.acodec)s")
        .arg("--progress-template")
        .arg("postprocess:VDPOST|%(progress.postprocessor)s|%(progress.status)s")
        .arg("--print")
        .arg("after_move:VDFILE|%(filepath)s")
        .arg("-o")
        .arg(&modello)
        .arg(url)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());

    let mut figlio = cmd.spawn().map_err(|_| "Non riesco ad avviare yt-dlp.".to_string())?;
    let uscita = figlio.stdout.take().unwrap();
    let errori = figlio.stderr.take().unwrap();
    *processo.lock().unwrap() = Some(figlio);

    // stderr: conversioni con FFmpeg e messaggi di errore (in un altro thread)
    let righe_errore: Arc<Mutex<Vec<String>>> = Arc::new(Mutex::new(Vec::new()));
    let copia_errori = righe_errore.clone();
    let avvisa_errori = avvisa.clone();
    let lettore_errori = std::thread::spawn(move || {
        for riga in BufReader::new(errori).lines().map_while(Result::ok) {
            match leggi_riga(&riga) {
                Riga::Conversione(testo) => avvisa_errori(Riga::Conversione(testo)),
                _ => copia_errori.lock().unwrap().push(riga),
            }
        }
    });

    // stdout: avanzamento e percorso del file finale
    let mut file_finale: Option<PathBuf> = None;
    for riga in BufReader::new(uscita).lines().map_while(Result::ok) {
        match leggi_riga(&riga) {
            Riga::File(percorso) => file_finale = Some(PathBuf::from(percorso)),
            Riga::Altro => {}
            altra => avvisa(altra),
        }
    }

    let _ = lettore_errori.join();

    let stato = processo.lock().unwrap().take().map(|mut f| f.wait());

    if annullato.load(Ordering::SeqCst) {
        elimina_parziali(cartella, &base);
        return Err("annullato".into());
    }
    let riuscito = matches!(stato, Some(Ok(s)) if s.success());
    if !riuscito {
        elimina_parziali(cartella, &base);
        let righe = righe_errore.lock().unwrap();
        let errore = righe.iter().rev().find(|r| r.contains("ERROR")).cloned().unwrap_or(righe.join("\n"));
        return Err(messaggio_errore(&errore));
    }

    match file_finale {
        Some(percorso) if percorso.exists() => Ok(percorso),
        _ => Ok(previsto),
    }
}

/// Ferma il download in corso
pub fn annulla(processo: &Arc<Mutex<Option<Child>>>, annullato: &Arc<AtomicBool>) {
    annullato.store(true, Ordering::SeqCst);
    if let Some(figlio) = processo.lock().unwrap().as_mut() {
        let _ = figlio.kill();
    }
}

/// Cancella i file a metà (es. "Titolo.f137.mp4.part")
pub fn elimina_parziali(cartella: &Path, base: &str) {
    let inizio = format!("{base}.");
    if let Ok(voci) = fs::read_dir(cartella) {
        for voce in voci.flatten() {
            let nome = voce.file_name().to_string_lossy().to_string();
            if nome.starts_with(&inizio) {
                let _ = fs::remove_file(voce.path());
            }
        }
    }
}

// ------------------------------------------------------------
// Test
// ------------------------------------------------------------

#[cfg(test)]
mod test {
    use super::*;
    use serde_json::json;

    #[test]
    fn link_validi() {
        for link in [
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "https://youtube.com/watch?v=dQw4w9WgXcQ&t=42s",
            "https://www.youtube.com/watch?feature=share&v=dQw4w9WgXcQ",
            "https://youtu.be/dQw4w9WgXcQ?si=abc",
            "https://www.youtube.com/shorts/dQw4w9WgXcQ",
            "https://m.youtube.com/watch?v=dQw4w9WgXcQ",
            "https://music.youtube.com/watch?v=dQw4w9WgXcQ",
            "www.youtube.com/watch?v=dQw4w9WgXcQ",
            "  https://youtu.be/dQw4w9WgXcQ  ",
        ] {
            assert!(url_valido(link), "{link}");
        }
    }

    #[test]
    fn link_non_validi() {
        for link in [
            "", "ciao", "https://www.google.com", "https://vimeo.com/123456",
            "https://www.youtube.com/", "https://www.youtube.com/watch?v=corto",
            "https://www.youtube.com/playlist?list=PL123",
            "https://notyoutube.com/watch?v=dQw4w9WgXcQ",
        ] {
            assert!(!url_valido(link), "{link}");
        }
    }

    #[test]
    fn nomi_dei_file() {
        assert_eq!(pulisci_nome("AC/DC: Back in Black?"), "AC-DC- Back in Black-");
        assert_eq!(pulisci_nome("   "), "video");
        assert_eq!(pulisci_nome("...ciao..."), "ciao");
        assert!(pulisci_nome(&"a".repeat(400)).chars().count() <= 150);
    }

    #[test]
    fn niente_duplicati() {
        let cartella = std::env::temp_dir().join("vd-test-duplicati");
        let _ = fs::remove_dir_all(&cartella);
        fs::create_dir_all(&cartella).unwrap();
        let primo = nome_file_libero(&cartella, "Canzone", "mp3");
        assert!(primo.ends_with("Canzone.mp3"));
        fs::write(&primo, b"x").unwrap();
        let secondo = nome_file_libero(&cartella, "Canzone", "mp3");
        assert!(secondo.ends_with("Canzone (2).mp3"));
        fs::remove_dir_all(&cartella).unwrap();
    }

    #[test]
    fn cartelle() {
        assert!(controlla_cartella(&std::env::temp_dir()).is_ok());
        assert!(controlla_cartella(Path::new("/cartella/che/non/esiste")).is_err());
    }

    #[test]
    fn errori_in_italiano() {
        assert!(messaggio_errore("ERROR: [youtube] x: Private video").contains("privato"));
        assert!(messaggio_errore("ERROR: Video unavailable").contains("non è disponibile"));
        assert!(messaggio_errore("HTTP Error 429: Too Many Requests").contains("Troppe richieste"));
        assert!(messaggio_errore("[Errno 8] nodename nor servname provided").contains("Connessione"));
        assert!(messaggio_errore("ERROR: qualcosa di strano").contains("qualcosa di strano"));
    }

    #[test]
    fn qualita_e_dimensioni() {
        let json = json!({
            "id": "abcdefghijk", "title": "Prova", "uploader": "DroneTicino",
            "duration": 212.0, "view_count": 12345, "webpage_url": "https://youtu.be/abcdefghijk",
            "formats": [
                {"ext": "mhtml", "height": 90, "vcodec": "none", "acodec": "none"},
                {"ext": "m4a", "vcodec": "none", "acodec": "mp4a", "filesize": 3_000_000},
                {"ext": "mp4", "height": 360, "vcodec": "avc1", "acodec": "mp4a"},
                {"ext": "mp4", "height": 1080, "vcodec": "avc1", "acodec": "none", "filesize_approx": 40_000_000},
                {"ext": "webm", "height": 1080, "vcodec": "vp9", "acodec": "none", "filesize": 30_000_000},
                {"ext": "webm", "height": 2160, "vcodec": "vp9", "acodec": "none"}
            ]
        });
        let info = leggi_info(&json);
        assert_eq!(info.canale, "DroneTicino");
        assert_eq!(info.copertina, "https://i.ytimg.com/vi/abcdefghijk/mqdefault.jpg");
        let altezze: Vec<u64> = info.qualita.iter().map(|q| q.altezza).collect();
        assert_eq!(altezze, vec![2160, 1080, 360]);
        assert_eq!(info.qualita[1].dimensione, Some(43_000_000));
        assert_eq!(info.qualita[0].dimensione, None);
    }

    #[test]
    fn righe_di_yt_dlp() {
        match leggi_riga("VDPROG|500|1000|NA|2048.5|3|avc1|none") {
            Riga::Progresso(p) => {
                assert_eq!(p.percentuale, 50.0);
                assert_eq!(p.velocita, Some(2048.5));
                assert_eq!(p.parte, "video");
            }
            altro => panic!("{altro:?}"),
        }
        match leggi_riga("VDPROG|10|NA|100|NA|NA|none|mp4a") {
            Riga::Progresso(p) => {
                assert_eq!(p.percentuale, 10.0);
                assert_eq!(p.parte, "audio");
            }
            altro => panic!("{altro:?}"),
        }
        assert_eq!(leggi_riga("VDPOST|ExtractAudio|started"), Riga::Conversione("Creo il file MP3...".into()));
        assert_eq!(leggi_riga("VDPOST|Merger|finished"), Riga::Altro);
        assert_eq!(leggi_riga("VDFILE|/x/Prova.mp3"), Riga::File("/x/Prova.mp3".into()));
        assert_eq!(leggi_riga("ciao"), Riga::Altro);
    }

    #[test]
    fn formati() {
        let video = argomenti_formato("video", 1080).join(" ");
        assert!(video.contains("res:1080,ext:mp4:m4a,vcodec:h264"));
        assert!(video.contains("--merge-output-format mp4"));
        let audio = argomenti_formato("audio", 192).join(" ");
        assert!(audio.contains("--audio-format mp3"));
        assert!(audio.contains("--audio-quality 192K"));
    }
    // ---------- Test con download veri (yt-dlp + FFmpeg + Deno) ----------
    // Partono solo se le variabili VD_YTDLP, VD_FFMPEG e VD_DENO indicano
    // dove sono i tre programmi. Usano un piccolo server locale: niente Internet.

    fn strumenti_di_prova() -> Option<Strumenti> {
        Some(Strumenti {
            ytdlp: PathBuf::from(std::env::var("VD_YTDLP").ok()?),
            ffmpeg: PathBuf::from(std::env::var("VD_FFMPEG").ok()?),
            deno: PathBuf::from(std::env::var("VD_DENO").ok()?),
        })
    }

    /// Server HTTP minimo che manda sempre lo stesso file video
    fn server_locale(video: Vec<u8>) -> String {
        use std::io::{Read, Write};
        let ascolta = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
        let porta = ascolta.local_addr().unwrap().port();
        std::thread::spawn(move || {
            for connessione in ascolta.incoming().flatten() {
                let video = video.clone();
                std::thread::spawn(move || {
                    let mut c = connessione;
                    let mut richiesta = [0u8; 4096];
                    let letti = c.read(&mut richiesta).unwrap_or(0);
                    let testo = String::from_utf8_lossy(&richiesta[..letti]);
                    let intestazione = format!(
                        "HTTP/1.1 200 OK\r\nContent-Type: video/mp4\r\nContent-Length: {}\r\nConnection: close\r\n\r\n",
                        video.len()
                    );
                    let _ = c.write_all(intestazione.as_bytes());
                    if !testo.starts_with("HEAD") {
                        // a pezzi e piano, così il test di annullamento fa in tempo
                        for pezzo in video.chunks(64 * 1024) {
                            if c.write_all(pezzo).is_err() {
                                break;
                            }
                            std::thread::sleep(std::time::Duration::from_millis(20));
                        }
                    }
                });
            }
        });
        format!("http://127.0.0.1:{porta}/prova.mp4")
    }

    fn video_di_prova(strumenti: &Strumenti, cartella: &Path) -> Vec<u8> {
        let file = cartella.join("sorgente.mp4");
        let stato = Command::new(&strumenti.ffmpeg)
            .args(["-loglevel", "error", "-y", "-f", "lavfi", "-i", "testsrc=duration=8:size=640x360:rate=25",
                   "-f", "lavfi", "-i", "sine=duration=8", "-c:v", "libx264", "-preset", "ultrafast",
                   "-b:v", "3M", "-c:a", "aac", "-shortest"])
            .arg(&file)
            .status()
            .unwrap();
        assert!(stato.success());
        let dati = fs::read(&file).unwrap();
        fs::remove_file(&file).unwrap();
        dati
    }

    fn nuova_cartella(nome: &str) -> PathBuf {
        let cartella = std::env::temp_dir().join(nome);
        let _ = fs::remove_dir_all(&cartella);
        fs::create_dir_all(&cartella).unwrap();
        cartella
    }

    #[test]
    fn download_veri() {
        let Some(strumenti) = strumenti_di_prova() else {
            eprintln!("test saltato: imposta VD_YTDLP, VD_FFMPEG e VD_DENO");
            return;
        };
        std::env::set_var("NO_PROXY", "127.0.0.1");
        std::env::set_var("no_proxy", "127.0.0.1");
        let cartella = nuova_cartella("vd-test-download");
        let url = server_locale(video_di_prova(&strumenti, &cartella));
        let processo = Arc::new(Mutex::new(None));
        let annullato = Arc::new(AtomicBool::new(false));

        // 1) Video MP4, con avanzamento
        let righe: Arc<Mutex<Vec<Riga>>> = Arc::new(Mutex::new(Vec::new()));
        let copia = righe.clone();
        let avvisa: Arc<dyn Fn(Riga) + Send + Sync> = Arc::new(move |r| copia.lock().unwrap().push(r));
        let primo = scarica(&strumenti, &url, "Prova: 100% video", "video", 360,
                            &cartella, processo.clone(), annullato.clone(), avvisa.clone()).unwrap();
        assert!(primo.exists());
        assert!(primo.to_string_lossy().ends_with("Prova- 100% video.mp4"));
        let ultima = righe.lock().unwrap().iter().filter_map(|r| match r {
            Riga::Progresso(p) => Some(p.percentuale), _ => None }).last().unwrap();
        assert!(ultima > 99.0);

        // 2) Stesso video di nuovo: non deve sovrascrivere
        let secondo = scarica(&strumenti, &url, "Prova: 100% video", "video", 360,
                              &cartella, processo.clone(), annullato.clone(), avvisa.clone()).unwrap();
        assert!(secondo.to_string_lossy().ends_with("Prova- 100% video (2).mp4"));

        // 3) Audio MP3, con il messaggio di conversione
        righe.lock().unwrap().clear();
        let mp3 = scarica(&strumenti, &url, "Canzone", "audio", 128,
                          &cartella, processo.clone(), annullato.clone(), avvisa.clone()).unwrap();
        assert!(mp3.to_string_lossy().ends_with("Canzone.mp3"));
        assert!(righe.lock().unwrap().contains(&Riga::Conversione("Creo il file MP3...".into())));

        // Restano solo i tre file finali, nessun file intermedio
        let mut nomi: Vec<String> = fs::read_dir(&cartella).unwrap()
            .map(|v| v.unwrap().file_name().to_string_lossy().to_string()).collect();
        nomi.sort();
        assert_eq!(nomi, vec!["Canzone.mp3", "Prova- 100% video (2).mp4", "Prova- 100% video.mp4"]);
        fs::remove_dir_all(&cartella).unwrap();
    }

    #[test]
    fn annullamento() {
        let Some(strumenti) = strumenti_di_prova() else { return; };
        std::env::set_var("NO_PROXY", "127.0.0.1");
        std::env::set_var("no_proxy", "127.0.0.1");
        let cartella = nuova_cartella("vd-test-annulla");
        let url = server_locale(video_di_prova(&strumenti, &cartella));
        let processo = Arc::new(Mutex::new(None));
        let annullato = Arc::new(AtomicBool::new(false));

        // Al primo avanzamento premiamo "Annulla"
        let p2 = processo.clone();
        let a2 = annullato.clone();
        let avvisa: Arc<dyn Fn(Riga) + Send + Sync> = Arc::new(move |r| {
            if let Riga::Progresso(_) = r {
                annulla(&p2, &a2);
            }
        });
        let risultato = scarica(&strumenti, &url, "Da annullare", "video", 360,
                                &cartella, processo, annullato, avvisa);
        assert_eq!(risultato, Err("annullato".to_string()));
        // Nessun file a metà deve restare
        assert_eq!(fs::read_dir(&cartella).unwrap().count(), 0);
        fs::remove_dir_all(&cartella).unwrap();
    }
}
