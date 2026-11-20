"""
aggiornamenti.py
----------------
Controlla se su GitHub c'e' una versione nuova e la installa.
Le release sono qui: https://github.com/sim40702-debug/YouTube-Downloader/releases

Come funziona:
1. Chiede a GitHub l'ultima release (funziona ovunque, anche fuori casa).
2. La confronta con VERSIONE.
3. Se e' piu' nuova:
   - app compilata (Mac .app o Windows .exe) -> scarica lo zip giusto per
     questo computer, chiude l'app, sostituisce la vecchia e la riapre;
   - da codice (main.py) -> fa "git pull" e aggiorna le librerie.

VERSIONE la cambia "npm run rilascia git": non serve toccarla a mano.
"""

import json
import os
import platform
import shutil
import ssl
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

try:
    import certifi
except ImportError:
    certifi = None


VERSIONE = "1.0.0"

# Repository su GitHub da cui prendere gli aggiornamenti: "utente/nome"
REPOSITORY_GITHUB = "sim40702-debug/YouTube-Downloader"
INDIRIZZO_API = f"https://api.github.com/repos/{REPOSITORY_GITHUB}/releases/latest"

NOME_APP = "Video Downloader"
SU_WINDOWS = sys.platform == "win32"
CARTELLA_PROGETTO = Path(__file__).resolve().parent


# ------------------------------------------------------------------
# Funzioni semplici (testate in tests/test_aggiornamenti.py)
# ------------------------------------------------------------------

def numeri_versione(testo):
    """'v1.2.3' -> (1, 2, 3)"""
    testo = str(testo).strip().lstrip("vV")
    numeri = []
    for pezzo in testo.split("."):
        cifre = ""
        for carattere in pezzo:
            if carattere.isdigit():
                cifre += carattere
            else:
                break
        numeri.append(int(cifre) if cifre else 0)
    while len(numeri) < 3:
        numeri.append(0)
    return tuple(numeri)


def e_piu_nuova(versione_remota, versione_attuale=VERSIONE):
    """True se la versione sul server e' piu' recente di quella installata."""
    return numeri_versione(versione_remota) > numeri_versione(versione_attuale)


def tipo_di_sistema():
    """
    'windows', 'apple-silicon' oppure 'intel'.
    Sono le stesse parole che ci sono nei nomi degli zip della release.
    """
    if SU_WINDOWS:
        return "windows"
    if platform.machine() == "arm64":
        return "apple-silicon"
    return "intel"


def nome_zip(tipo=None):
    """Nome dello zip per un sistema, es. 'Video-Downloader-windows.zip'."""
    tipo = tipo or tipo_di_sistema()
    if tipo == "windows":
        return "Video-Downloader-windows.zip"
    return f"Video-Downloader-macOS-{tipo}.zip"


def scegli_file(release, tipo=None):
    """Trova nella release lo zip adatto a questo computer. Restituisce l'asset o None."""
    nome_cercato = nome_zip(tipo)
    for asset in release.get("assets") or []:
        if asset.get("name") == nome_cercato:
            return asset
    return None


def e_app_compilata():
    """True se stiamo girando nell'app compilata con PyInstaller."""
    return getattr(sys, "frozen", False)


def cartella_app():
    """
    Mac:     .../Video Downloader.app   (sys.executable e' in Contents/MacOS)
    Windows: ...\\Video Downloader       (cartella che contiene il .exe)
    """
    eseguibile = Path(sys.executable).resolve()
    if SU_WINDOWS:
        return eseguibile.parent
    for genitore in eseguibile.parents:
        if genitore.suffix == ".app":
            return genitore
    return None


def _contesto_ssl():
    if certifi:
        return ssl.create_default_context(cafile=certifi.where())
    return ssl.create_default_context()


def _leggi_json(indirizzo, timeout):
    richiesta = urllib.request.Request(indirizzo, headers={
        "Accept": "application/vnd.github+json", "User-Agent": "Video-Downloader"})
    with urllib.request.urlopen(richiesta, timeout=timeout, context=_contesto_ssl()) as risposta:
        return json.loads(risposta.read().decode("utf-8"))


# ------------------------------------------------------------------
# 1) Controllo
# ------------------------------------------------------------------

def controlla():
    """
    Chiede a GitHub l'ultima release.
    Restituisce un dizionario: "disponibile" e' True se c'e' una versione nuova.
    Se GitHub non risponde solleva RuntimeError.
    """
    try:
        release = _leggi_json(INDIRIZZO_API, timeout=10)
    except urllib.error.HTTPError as errore:
        if errore.code == 404:
            raise RuntimeError("Su GitHub non c'e' ancora nessuna release.")
        if errore.code == 403:
            raise RuntimeError("Troppi controlli in poco tempo: riprova tra un'ora.")
        raise RuntimeError(f"GitHub ha risposto con l'errore {errore.code}.")
    except Exception:
        raise RuntimeError("Impossibile contattare GitHub. Controlla la connessione.")

    versione = release.get("tag_name", "")
    return {
        "disponibile": e_piu_nuova(versione),
        "versione": versione.lstrip("vV"),
        "note": (release.get("body") or "").strip(),
        "pagina": release.get("html_url"),
        "file": scegli_file(release),
    }


# ------------------------------------------------------------------
# 2) Installazione nell'app compilata
# ------------------------------------------------------------------

def scarica_e_prepara(aggiornamento, al_progresso=None):
    """
    Scarica lo zip, lo estrae e prepara lo script che sostituira'
    l'app quando si chiude. Restituisce cosa serve per avviarlo.
    """
    app_attuale = cartella_app()
    if app_attuale is None:
        raise RuntimeError("Non trovo la cartella dell'app.")
    if not os.access(app_attuale.parent, os.W_OK) or not os.access(app_attuale, os.W_OK):
        raise RuntimeError(
            f"Non ho i permessi per modificare:\n{app_attuale}\n"
            "Scarica la nuova versione da GitHub e sostituisci l'app a mano.")

    asset = aggiornamento.get("file")
    if not asset:
        raise RuntimeError(
            f"Nella release {aggiornamento['versione']} non c'e' il file per questo "
            f"computer ({nome_zip()}).")

    cartella_temp = Path(tempfile.mkdtemp(prefix="ytd-aggiornamento-"))
    file_zip = cartella_temp / "app.zip"
    indirizzo = asset["browser_download_url"]

    # Download dello zip, a pezzi, per mostrare l'avanzamento
    try:
        richiesta = urllib.request.Request(indirizzo, headers={"User-Agent": "Video-Downloader"})
        with urllib.request.urlopen(richiesta, timeout=30, context=_contesto_ssl()) as risposta:
            totale = int(risposta.headers.get("Content-Length") or asset.get("size") or 0)
            scaricati = 0
            with open(file_zip, "wb") as file:
                while True:
                    pezzo = risposta.read(256 * 1024)
                    if not pezzo:
                        break
                    file.write(pezzo)
                    scaricati += len(pezzo)
                    if al_progresso and totale:
                        al_progresso(min(scaricati / totale * 100, 100))
    except Exception:
        shutil.rmtree(cartella_temp, ignore_errors=True)
        raise RuntimeError("Download dell'aggiornamento non riuscito. Riprova.")

    # Estrazione dello zip
    cartella_estratta = cartella_temp / "nuova"
    try:
        estrai_zip(file_zip, cartella_estratta)
    except Exception:
        shutil.rmtree(cartella_temp, ignore_errors=True)
        raise RuntimeError("Il file scaricato non e' valido.")
    file_zip.unlink()

    nuova_app = trova_app_estratta(cartella_estratta)
    if nuova_app is None:
        shutil.rmtree(cartella_temp, ignore_errors=True)
        raise RuntimeError("Nello zip non c'e' l'app.")

    script = crea_script_sostituzione(cartella_temp)
    return {
        "script": script,
        "argomenti": [str(os.getpid()), str(app_attuale), str(nuova_app), str(cartella_temp)],
    }


def estrai_zip(file_zip, destinazione):
    if SU_WINDOWS:
        with zipfile.ZipFile(file_zip) as archivio:
            archivio.extractall(destinazione)
    else:
        # Su Mac usiamo ditto: mantiene permessi e collegamenti dentro l'app
        subprocess.run(["ditto", "-x", "-k", str(file_zip), str(destinazione)], check=True)
        subprocess.run(["xattr", "-dr", "com.apple.quarantine", str(destinazione)],
                       capture_output=True)


def trova_app_estratta(cartella):
    """Mac: la cartella .app.  Windows: la cartella che contiene il .exe."""
    if SU_WINDOWS:
        for exe in Path(cartella).rglob(f"{NOME_APP}.exe"):
            return exe.parent
        return None
    app = list(Path(cartella).glob("*.app"))
    return app[0] if app else None


def crea_script_sostituzione(cartella, sistema=None):
    """
    Scrive lo script che aspetta la chiusura dell'app, sostituisce la
    vecchia con la nuova e la riapre. Restituisce il percorso dello script.
    Argomenti dello script: PID, app vecchia, app nuova, cartella temporanea,
    e un quinto argomento facoltativo "senza-riapertura" (usato nei test).
    """
    sistema = sistema or ("windows" if SU_WINDOWS else "mac")
    if sistema == "windows":
        script = Path(cartella) / "sostituisci.bat"
        script.write_text(
            "@echo off\r\n"
            "set PID=%1\r\n"
            "set VECCHIA=%~2\r\n"
            "set NUOVA=%~3\r\n"
            "set TEMPORANEA=%~4\r\n"
            "rem Aspetta che l'app si chiuda\r\n"
            ":attesa\r\n"
            "tasklist /FI \"PID eq %PID%\" 2>nul | find \"%PID%\" >nul\r\n"
            "if not errorlevel 1 (\r\n"
            "    timeout /t 1 /nobreak >nul\r\n"
            "    goto attesa\r\n"
            ")\r\n"
            "rem Copia la nuova versione sopra la vecchia\r\n"
            "robocopy \"%NUOVA%\" \"%VECCHIA%\" /MIR /NFL /NDL /NJH /NJS /NP >nul\r\n"
            f"if not \"%~5\"==\"senza-riapertura\" start \"\" \"%VECCHIA%\\{NOME_APP}.exe\"\r\n"
            "rmdir /s /q \"%TEMPORANEA%\"\r\n",
            encoding="utf-8")
    else:
        script = Path(cartella) / "sostituisci.sh"
        script.write_text(
            "#!/bin/bash\n"
            "PID=\"$1\"; VECCHIA=\"$2\"; NUOVA=\"$3\"; TEMP=\"$4\"\n"
            "# Aspetta che l'app si chiuda\n"
            "while kill -0 \"$PID\" 2>/dev/null; do sleep 0.5; done\n"
            "# Sposta la vecchia app da parte; se qualcosa va storto la rimette\n"
            "if mv \"$VECCHIA\" \"$TEMP/vecchia.app\"; then\n"
            "    if ! mv \"$NUOVA\" \"$VECCHIA\"; then\n"
            "        mv \"$TEMP/vecchia.app\" \"$VECCHIA\"\n"
            "    fi\n"
            "fi\n"
            "if [ \"$5\" != \"senza-riapertura\" ]; then open \"$VECCHIA\"; fi\n"
            "rm -rf \"$TEMP\"\n",
            encoding="utf-8")
    return script


def avvia_sostituzione(preparato):
    """Avvia lo script in modo indipendente: continua anche dopo che l'app si chiude."""
    if SU_WINDOWS:
        separato = getattr(subprocess, "DETACHED_PROCESS", 0) | \
            getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        subprocess.Popen(["cmd", "/c", str(preparato["script"])] + preparato["argomenti"],
                         creationflags=separato, close_fds=True)
    else:
        subprocess.Popen(["/bin/bash", str(preparato["script"])] + preparato["argomenti"],
                         start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


# ------------------------------------------------------------------
# 3) Aggiornamento quando si usa il codice (main.py)
# ------------------------------------------------------------------

def aggiorna_codice():
    """git pull + aggiornamento librerie. Restituisce un messaggio da mostrare."""
    if not (CARTELLA_PROGETTO / ".git").exists():
        raise RuntimeError("Questa cartella non e' collegata a git (manca .git).\n"
                           "Scarica la nuova versione da GitHub.")
    risultato = subprocess.run(["git", "pull", "--no-rebase", "--no-edit"],
                               cwd=CARTELLA_PROGETTO, capture_output=True, text=True)
    if risultato.returncode != 0:
        raise RuntimeError("git pull non riuscito:\n" + risultato.stderr.strip()[-300:])
    subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade", "--quiet",
                    "-r", str(CARTELLA_PROGETTO / "requirements.txt")],
                   cwd=CARTELLA_PROGETTO, capture_output=True)
    return "Codice aggiornato. Chiudi e riapri l'app per usare la nuova versione."
