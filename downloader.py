"""
downloader.py
-------------
Tutta la logica per leggere le informazioni e scaricare i contenuti.
Qui NON c'e' grafica: l'interfaccia (interface.py) chiama queste funzioni.

Strumenti usati:
- yt-dlp  -> legge le informazioni del video e lo scarica
- FFmpeg  -> unisce video + audio e converte in MP3
- Deno    -> serve a yt-dlp per leggere correttamente YouTube

Funziona su macOS e su Windows.
"""

import os
import re
import shutil
import sys
import threading
from pathlib import Path

import yt_dlp
from yt_dlp.utils import sanitize_filename


SU_WINDOWS = sys.platform == "win32"
SU_MAC = sys.platform == "darwin"

# Cartelle dove di solito si trovano FFmpeg e Deno.
# Quando l'app parte con un doppio clic queste cartelle spesso
# NON sono nel PATH, quindi le aggiungiamo noi.
if SU_WINDOWS:
    _utente = os.environ.get("USERPROFILE", "")
    _locale = os.environ.get("LOCALAPPDATA", "")
    CARTELLE_PROGRAMMI = [
        os.path.join(_locale, "Microsoft", "WinGet", "Links"),  # programmi installati con winget
        os.path.join(_utente, ".deno", "bin"),                  # Deno installato a mano
        r"C:\ffmpeg\bin",                                      # FFmpeg copiato a mano
    ]
else:
    CARTELLE_PROGRAMMI = [
        "/opt/homebrew/bin",  # Homebrew su Mac Apple Silicon (M1, M2, M3, M4...)
        "/usr/local/bin",     # Homebrew su Mac Intel
        "/opt/local/bin",     # MacPorts
    ]

# Nome dello script di installazione per questo sistema
SCRIPT_INSTALLAZIONE = "install_windows.bat" if SU_WINDOWS else "install.sh"

# Qualita' audio MP3 disponibili (in kbps)
QUALITA_AUDIO = ["320", "256", "192", "128"]
QUALITA_AUDIO_PREDEFINITA = "192"

# Riconosce i link di YouTube: watch, shorts, live, embed, youtu.be e music
REGEX_YOUTUBE = re.compile(
    r"^(https?://)?(www\.|m\.|music\.)?"
    r"(youtube\.com/(watch\?(.*&)?v=|shorts/|live/|embed/)|youtu\.be/)"
    r"[A-Za-z0-9_-]{11}"
)

# Lunghezza massima del nome del file (macOS accetta max 255 byte)
LUNGHEZZA_MAX_NOME = 150


class DownloadAnnullato(Exception):
    """Errore usato quando l'utente preme Annulla."""
    pass


# ------------------------------------------------------------------
# Controllo dei programmi esterni
# ------------------------------------------------------------------

def aggiungi_cartelle_al_path():
    """Aggiunge le cartelle di Homebrew al PATH, se mancano."""
    percorsi = os.environ.get("PATH", "").split(os.pathsep)
    for cartella in CARTELLE_PROGRAMMI:
        if cartella not in percorsi and os.path.isdir(cartella):
            percorsi.append(cartella)
    os.environ["PATH"] = os.pathsep.join(percorsi)


def trova_programma(nome):
    """Restituisce il percorso di un programma (es. 'ffmpeg') oppure None."""
    percorso = shutil.which(nome)
    if percorso:
        return percorso
    if SU_WINDOWS:
        nome = nome + ".exe"
    for cartella in CARTELLE_PROGRAMMI:
        possibile = os.path.join(cartella, nome)
        if os.path.isfile(possibile) and os.access(possibile, os.X_OK):
            return possibile
    return None


def comando_installazione(programma):
    """Il comando da scrivere nel terminale per installare un programma."""
    if SU_WINDOWS:
        nomi_winget = {"ffmpeg": "Gyan.FFmpeg", "deno": "DenoLand.Deno"}
        return f"winget install {nomi_winget.get(programma, programma)}"
    if SU_MAC:
        return f"brew install {programma}"
    return f"sudo apt install {programma}"


def trova_ffmpeg():
    return trova_programma("ffmpeg")


def trova_deno():
    return trova_programma("deno")


# ------------------------------------------------------------------
# Controlli sull'input dell'utente
# ------------------------------------------------------------------

def url_valido(url):
    """True se il testo sembra un link di un video YouTube."""
    if not url:
        return False
    return bool(REGEX_YOUTUBE.match(url.strip()))


def controlla_cartella(cartella):
    """
    Controlla che si possa salvare nella cartella.
    Restituisce None se va tutto bene, altrimenti un messaggio di errore.
    """
    percorso = Path(cartella).expanduser()
    if not percorso.exists():
        return f"La cartella non esiste:\n{percorso}"
    if not percorso.is_dir():
        return f"Il percorso scelto non e' una cartella:\n{percorso}"
    if not os.access(percorso, os.W_OK):
        return ("Non hai i permessi per salvare in questa cartella.\n"
                "Scegline un'altra con 'Cambia cartella'.")
    return None


def nome_file_libero(cartella, nome, estensione):
    """
    Trova un nome di file che non esiste ancora, per non sovrascrivere.
    Esempio: 'Canzone.mp3' esiste gia' -> 'Canzone (2).mp3'
    """
    cartella = Path(cartella)
    percorso = cartella / f"{nome}.{estensione}"
    numero = 2
    while percorso.exists():
        percorso = cartella / f"{nome} ({numero}).{estensione}"
        numero += 1
    return percorso


def pulisci_nome(titolo):
    """Toglie dal titolo i caratteri che non vanno bene nei nomi dei file."""
    nome = sanitize_filename(titolo or "video", restricted=False)
    nome = nome.replace(":", "-").strip(" .")
    if len(nome) > LUNGHEZZA_MAX_NOME:
        nome = nome[:LUNGHEZZA_MAX_NOME].strip()
    return nome or "video"


# ------------------------------------------------------------------
# Funzioni per mostrare i numeri in modo leggibile
# ------------------------------------------------------------------

def formatta_byte(numero):
    """1536000 -> '1.5 MB'"""
    if not numero:
        return "—"
    unita = ["B", "KB", "MB", "GB", "TB"]
    valore = float(numero)
    i = 0
    while valore >= 1024 and i < len(unita) - 1:
        valore = valore / 1024
        i += 1
    if i == 0:
        return f"{int(valore)} B"
    return f"{valore:.1f} {unita[i]}"


def formatta_velocita(byte_al_secondo):
    """2048000 -> '2.0 MB/s'"""
    if not byte_al_secondo:
        return "—"
    return formatta_byte(byte_al_secondo) + "/s"


def formatta_durata(secondi):
    """3725 -> '1:02:05'   185 -> '3:05'"""
    if secondi is None:
        return "—"
    secondi = int(secondi)
    ore = secondi // 3600
    minuti = (secondi % 3600) // 60
    sec = secondi % 60
    if ore > 0:
        return f"{ore}:{minuti:02d}:{sec:02d}"
    return f"{minuti}:{sec:02d}"


def formatta_numero(numero):
    """1234567 -> '1.234.567'"""
    if numero is None:
        return "—"
    return f"{int(numero):,}".replace(",", ".")


def nome_qualita(altezza):
    """1080 -> '1080p (Full HD)'"""
    nomi = {2160: "4K", 1440: "2K", 1080: "Full HD", 720: "HD"}
    if altezza in nomi:
        return f"{altezza}p ({nomi[altezza]})"
    return f"{altezza}p"


# ------------------------------------------------------------------
# Qualita' e formati
# ------------------------------------------------------------------

def qualita_video_disponibili(info, con_ffmpeg=True):
    """
    Restituisce le altezze (es. [1080, 720, 360]) disponibili per il video.
    Senza FFmpeg si possono usare solo i formati che hanno gia'
    video e audio insieme (di solito massimo 360p).
    """
    altezze = set()
    for formato in info.get("formats") or []:
        altezza = formato.get("height")
        video = formato.get("vcodec")
        audio = formato.get("acodec")
        if not altezza or video == "none" or formato.get("ext") == "mhtml":
            continue
        if not con_ffmpeg and audio == "none":
            continue
        altezze.add(int(altezza))
    return sorted(altezze, reverse=True)


def opzioni_formato_video(altezza, con_ffmpeg=True):
    """
    Opzioni di yt-dlp per scaricare il video alla qualita' scelta.
    'format_sort' dice: prima la risoluzione (fino ad 'altezza'),
    poi preferisci MP4, poi il codec H.264 (il piu' compatibile su Mac).
    """
    ordine = [f"res:{altezza}", "ext:mp4:m4a", "vcodec:h264"]
    if con_ffmpeg:
        return {
            "format": "bv*+ba/b",
            "format_sort": ordine,
            "merge_output_format": "mp4",
        }
    # Senza FFmpeg: solo file che hanno gia' video e audio insieme
    return {
        "format": "b",
        "format_sort": ordine,
    }


def opzioni_formato_audio(qualita):
    """Opzioni di yt-dlp per estrarre l'audio in MP3."""
    return {
        "format": "bestaudio/best",
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": str(qualita),
        }],
    }


def dimensione_stimata(info, altezza=None):
    """Prova a stimare la dimensione del file (in byte). Puo' restituire None."""
    totale_video = 0
    totale_audio = 0
    for formato in info.get("formats") or []:
        dimensione = formato.get("filesize") or formato.get("filesize_approx")
        if not dimensione:
            continue
        if formato.get("vcodec") == "none" and formato.get("acodec") != "none":
            totale_audio = max(totale_audio, dimensione)
        elif altezza and formato.get("height") == altezza:
            totale_video = max(totale_video, dimensione)
    if altezza is None:
        return totale_audio or None
    if totale_video:
        return totale_video + totale_audio
    return None


# ------------------------------------------------------------------
# Messaggi di errore comprensibili
# ------------------------------------------------------------------

def messaggio_errore(errore):
    """Trasforma un errore tecnico in un messaggio chiaro in italiano."""
    testo = str(errore)
    t = testo.lower()

    if isinstance(errore, DownloadAnnullato):
        return "Download annullato."
    if "private video" in t:
        return "Questo video e' privato: non puo' essere scaricato."
    if "sign in to confirm your age" in t or "age-restricted" in t:
        return "Questo video ha limiti di eta' e richiede l'accesso: non puo' essere scaricato."
    if "members-only" in t or "join this channel" in t:
        return "Questo video e' riservato ai membri del canale."
    if "premieres in" in t or "this live event will begin" in t:
        return "Il video non e' ancora disponibile (prima o diretta non iniziata)."
    if "not available in your country" in t or "geo" in t and "restrict" in t:
        return "Questo video non e' disponibile nel tuo paese."
    if "copyright" in t:
        return "Il video e' stato rimosso per motivi di copyright."
    if "video unavailable" in t or "this video is not available" in t:
        return "Il video non e' disponibile (rimosso o link sbagliato)."
    if "sign in to confirm you" in t and "bot" in t:
        return ("YouTube ha bloccato temporaneamente la richiesta.\n"
                "Riprova tra qualche minuto.")
    if "ffmpeg" in t and ("not found" in t or "not installed" in t):
        return ("FFmpeg non e' installato.\n"
                f"Apri il terminale e scrivi: {comando_installazione('ffmpeg')}")
    if "certificate_verify_failed" in t or "certificate verify failed" in t:
        return ("Problema con i certificati di sicurezza di Python.\n"
                f"Riesegui {SCRIPT_INSTALLAZIONE} per sistemarli.")
    if "http error 403" in t:
        return ("YouTube ha rifiutato il download (errore 403).\n"
                f"Prova ad aggiornare yt-dlp rieseguendo {SCRIPT_INSTALLAZIONE}.")
    if "http error 429" in t or "too many requests" in t:
        return "Troppe richieste a YouTube. Aspetta qualche minuto e riprova."
    if "requested format is not available" in t:
        return "La qualita' scelta non e' disponibile. Scegline un'altra."
    if ("getaddrinfo" in t or "nodename nor servname" in t
            or "name or service not known" in t or "network is unreachable" in t
            or "connection" in t or "timed out" in t):
        return ("Connessione a Internet assente o interrotta.\n"
                "Controlla la rete e riprova: il download riprendera' da dove si era fermato.")
    if "no space left" in t:
        return "Spazio su disco esaurito. Libera spazio e riprova."
    if "permission denied" in t or "operation not permitted" in t:
        return "Non hai i permessi per salvare in questa cartella. Scegline un'altra."
    if "unsupported url" in t or "is not a valid url" in t:
        return "Il link non e' supportato. Controlla di aver copiato un link di YouTube."

    # Errore sconosciuto: mostriamo l'ultima riga, senza la parola ERROR
    ultima_riga = testo.strip().splitlines()[-1] if testo.strip() else "Errore sconosciuto."
    ultima_riga = ultima_riga.replace("ERROR: ", "")
    return f"Si e' verificato un errore:\n{ultima_riga}"


# ------------------------------------------------------------------
# Logger silenzioso: yt-dlp non scrive nulla nel terminale
# ------------------------------------------------------------------

class LoggerSilenzioso:
    def __init__(self):
        self.avvisi = []

    def debug(self, messaggio):
        pass

    def info(self, messaggio):
        pass

    def warning(self, messaggio):
        self.avvisi.append(messaggio)

    def error(self, messaggio):
        pass


# ------------------------------------------------------------------
# Classe principale
# ------------------------------------------------------------------

class Downloader:
    """
    Gestisce analisi e download.
    Le funzioni 'analizza' e 'scarica' sono lente: l'interfaccia
    le chiama in un thread separato, cosi' la finestra non si blocca.
    """

    def __init__(self):
        aggiungi_cartelle_al_path()
        self.ffmpeg = trova_ffmpeg()
        self.deno = trova_deno()
        self.evento_annulla = threading.Event()
        self.file_creati = set()
        self.al_progresso = None
        self.al_cambio_stato = None

    # --- opzioni comuni a tutte le richieste ---
    def _opzioni_base(self):
        opzioni = {
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            "noplaylist": True,       # scarica solo il video, non la playlist
            "logger": LoggerSilenzioso(),
            "retries": 10,            # riprova se la connessione cade
            "fragment_retries": 10,
            "continuedl": True,       # riprende i download interrotti
            "socket_timeout": 20,
        }
        if self.ffmpeg:
            opzioni["ffmpeg_location"] = self.ffmpeg
        return opzioni

    # --- 1) Analisi del link ---
    def analizza(self, url):
        """Legge le informazioni del video senza scaricarlo."""
        if not url_valido(url):
            raise ValueError("Il link non sembra un video di YouTube.\n"
                             "Esempio: https://www.youtube.com/watch?v=...")
        opzioni = self._opzioni_base()
        opzioni["skip_download"] = True
        with yt_dlp.YoutubeDL(opzioni) as ydl:
            info = ydl.extract_info(url.strip(), download=False)
        if info is None:
            raise ValueError("Impossibile leggere le informazioni del video.")
        if info.get("is_live"):
            raise ValueError("Le dirette in corso non possono essere scaricate.\n"
                             "Riprova quando la diretta e' finita.")
        return info

    # --- 2) Download ---
    def annulla(self):
        """Chiamata dal pulsante Annulla."""
        self.evento_annulla.set()

    def scarica(self, info, modalita, qualita, cartella,
                al_progresso=None, al_cambio_stato=None):
        """
        Scarica il contenuto.
        modalita: "VIDEO" oppure "AUDIO"
        qualita:  altezza (es. 1080) per il video, kbps (es. "192") per l'audio
        Restituisce il percorso del file creato.
        """
        self.evento_annulla.clear()
        self.file_creati = set()
        self.al_progresso = al_progresso
        self.al_cambio_stato = al_cambio_stato

        errore_cartella = controlla_cartella(cartella)
        if errore_cartella:
            raise ValueError(errore_cartella)

        if modalita == "AUDIO" and not self.ffmpeg:
            raise ValueError("Per creare file MP3 serve FFmpeg.\n"
                             f"Apri il terminale e scrivi: {comando_installazione('ffmpeg')}")

        # Nome del file finale, senza sovrascrivere file gia' esistenti
        estensione = "mp3" if modalita == "AUDIO" else "mp4"
        nome = pulisci_nome(info.get("title"))
        percorso_finale = nome_file_libero(Path(cartella).expanduser(), nome, estensione)
        # Il simbolo % ha un significato speciale per yt-dlp: va raddoppiato
        base = str(percorso_finale.with_suffix("")).replace("%", "%%")

        opzioni = self._opzioni_base()
        opzioni["outtmpl"] = base + ".%(ext)s"
        opzioni["progress_hooks"] = [self._hook_download]
        opzioni["postprocessor_hooks"] = [self._hook_conversione]
        if modalita == "AUDIO":
            opzioni.update(opzioni_formato_audio(qualita))
        else:
            opzioni.update(opzioni_formato_video(int(qualita), bool(self.ffmpeg)))

        self._stato("Avvio del download...")
        url = info.get("webpage_url") or info.get("original_url")

        try:
            with yt_dlp.YoutubeDL(opzioni) as ydl:
                risultato = ydl.extract_info(url, download=True)
        except Exception as errore:
            # Se l'utente ha premuto Annulla, l'errore e' "voluto"
            self._elimina_file_parziali()
            if self.evento_annulla.is_set():
                raise DownloadAnnullato()
            raise errore

        if self.evento_annulla.is_set():
            self._elimina_file_parziali()
            raise DownloadAnnullato()

        return self._percorso_file_scaricato(risultato, percorso_finale)

    # --- funzioni interne ---
    def _stato(self, testo):
        if self.al_cambio_stato:
            self.al_cambio_stato(testo)

    def _hook_download(self, dati):
        """yt-dlp chiama questa funzione tante volte durante il download."""
        if self.evento_annulla.is_set():
            raise DownloadAnnullato()

        for chiave in ("tmpfilename", "filename"):
            if dati.get(chiave):
                self.file_creati.add(dati[chiave])

        if dati.get("status") == "downloading":
            scaricati = dati.get("downloaded_bytes") or 0
            totale = dati.get("total_bytes") or dati.get("total_bytes_estimate")
            percentuale = (scaricati / totale * 100) if totale else 0
            if self.al_progresso:
                self.al_progresso({
                    "percentuale": min(percentuale, 100),
                    "scaricati": scaricati,
                    "totale": totale,
                    "velocita": dati.get("speed"),
                    "tempo_rimasto": dati.get("eta"),
                    "parte": self._nome_parte(dati),
                })
        elif dati.get("status") == "finished":
            self._stato("Parte scaricata, preparo il file...")

    def _nome_parte(self, dati):
        """Dice se stiamo scaricando la traccia video o quella audio."""
        formato = dati.get("info_dict") or {}
        if formato.get("vcodec") == "none":
            return "audio"
        if formato.get("acodec") == "none":
            return "video"
        return ""

    def _hook_conversione(self, dati):
        """Chiamata quando FFmpeg unisce o converte il file."""
        if self.evento_annulla.is_set():
            raise DownloadAnnullato()
        if dati.get("status") == "started":
            nome = dati.get("postprocessor", "")
            if "ExtractAudio" in nome:
                self._stato("Conversione in MP3 con FFmpeg...")
            elif "Merger" in nome:
                self._stato("Unione di video e audio con FFmpeg...")
            else:
                self._stato("Elaborazione del file...")

    def _elimina_file_parziali(self):
        """Dopo un errore o un annullamento cancella i file a meta'."""
        for nome in list(self.file_creati):
            for percorso in (nome, nome + ".part", nome + ".ytdl"):
                try:
                    if os.path.isfile(percorso):
                        os.remove(percorso)
                except OSError:
                    pass
        self.file_creati = set()

    def _percorso_file_scaricato(self, risultato, percorso_previsto):
        """Trova il percorso vero del file finale."""
        if risultato:
            for scaricato in risultato.get("requested_downloads") or []:
                percorso = scaricato.get("filepath")
                if percorso and os.path.isfile(percorso):
                    return Path(percorso)
        if percorso_previsto.exists():
            return percorso_previsto
        # Senza FFmpeg il video potrebbe avere un'altra estensione (es. .webm)
        for file in percorso_previsto.parent.glob(percorso_previsto.stem + ".*"):
            if file.suffix not in (".part", ".ytdl"):
                return file
        return percorso_previsto
