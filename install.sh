#!/bin/bash
# ------------------------------------------------------------
# install.sh
# Installa tutto quello che serve per Video Downloader su Mac.
# Uso: apri il Terminale nella cartella del progetto e scrivi
#      ./install.sh
# Si puo' rieseguire quando vuoi: aggiorna anche yt-dlp.
# ------------------------------------------------------------

set -e
cd "$(dirname "$0")"

VERDE="\033[0;32m"
GIALLO="\033[0;33m"
ROSSO="\033[0;31m"
NORMALE="\033[0m"

ok()     { echo -e "${VERDE}✓${NORMALE} $1"; }
avviso() { echo -e "${GIALLO}!${NORMALE} $1"; }
errore() { echo -e "${ROSSO}✗${NORMALE} $1"; }

echo ""
echo "=== Installazione di Video Downloader ==="
echo ""

# 1) Controllo del sistema operativo
if [ "$(uname)" != "Darwin" ]; then
    avviso "Questo script e' pensato per macOS."
fi
echo "Processore: $(uname -m)"

# Aggiungiamo le cartelle di Homebrew al PATH (Apple Silicon e Intel)
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"

# 2) Homebrew (serve per installare Python, FFmpeg e Deno)
if command -v brew >/dev/null 2>&1; then
    ok "Homebrew trovato"
    HA_BREW=1
else
    avviso "Homebrew non trovato. Lo consiglio per installare FFmpeg e Deno."
    echo "   Per installarlo incolla nel Terminale il comando che trovi su https://brew.sh"
    HA_BREW=0
fi

# 3) Python 3.10 o piu' recente, con tkinter
PYTHON=""
for candidato in python3.13 python3.12 python3.11 python3.10 python3; do
    if command -v "$candidato" >/dev/null 2>&1; then
        if "$candidato" -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" 2>/dev/null; then
            PYTHON="$(command -v "$candidato")"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    if [ "$HA_BREW" = "1" ]; then
        avviso "Python 3.10+ non trovato: lo installo con Homebrew..."
        brew install python python-tk
        PYTHON="$(command -v python3)"
    else
        errore "Serve Python 3.10 o piu' recente. Scaricalo da https://www.python.org"
        exit 1
    fi
fi
ok "Python: $("$PYTHON" --version) ($PYTHON)"

if ! "$PYTHON" -c "import tkinter" 2>/dev/null; then
    if [ "$HA_BREW" = "1" ]; then
        avviso "Manca tkinter (la grafica di Python): lo installo..."
        VERSIONE=$("$PYTHON" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
        brew install "python-tk@$VERSIONE" || brew install python-tk || true
    fi
    if ! "$PYTHON" -c "import tkinter" 2>/dev/null; then
        errore "tkinter non disponibile. Installa Python da https://www.python.org (lo include gia')."
        exit 1
    fi
fi
ok "tkinter presente"

# 4) Ambiente virtuale (.venv) con le librerie del progetto
if [ ! -d ".venv" ]; then
    echo "Creo l'ambiente virtuale .venv ..."
    "$PYTHON" -m venv .venv
fi
.venv/bin/python -m pip install --upgrade pip --quiet
echo "Installo/aggiorno le librerie (customtkinter, yt-dlp, pillow, requests)..."
.venv/bin/python -m pip install --upgrade -r requirements.txt --quiet
ok "Librerie Python installate"

# 5) FFmpeg (per unire video+audio e creare MP3)
installa_con_brew() {
    # $1 = nome del programma
    if [ "$HA_BREW" = "1" ]; then
        read -r -p "   Vuoi installare $1 adesso con Homebrew? [S/n] " risposta
        case "$risposta" in
            [nN]*) avviso "$1 non installato." ;;
            *) brew install "$1" || avviso "Installazione di $1 non riuscita." ;;
        esac
    else
        avviso "Installa Homebrew e poi scrivi: brew install $1"
    fi
}

if command -v ffmpeg >/dev/null 2>&1; then
    ok "FFmpeg trovato: $(command -v ffmpeg)"
else
    avviso "FFmpeg non trovato: senza FFmpeg niente MP3 e video solo in bassa qualita'."
    installa_con_brew ffmpeg
fi

# 6) Deno (serve a yt-dlp per leggere YouTube)
if command -v deno >/dev/null 2>&1; then
    ok "Deno trovato: $(command -v deno)"
else
    avviso "Deno non trovato: senza Deno molti video di YouTube non si scaricano."
    installa_con_brew deno
fi

# 7) Permessi di esecuzione e rimozione del blocco di macOS (Gatekeeper)
chmod +x install.sh build_mac.sh "Avvia Video Downloader.command" 2>/dev/null || true
xattr -dr com.apple.quarantine . 2>/dev/null || true
ok "Permessi sistemati"

# 8) Test veloci
echo "Eseguo i test..."
if .venv/bin/python -m unittest discover -s tests -q 2>&1 | tail -3; then
    ok "Test completati"
fi
# I test non devono lasciare file in giro
find . -name "__pycache__" -type d -prune -exec rm -rf {} + 2>/dev/null || true

echo ""
ok "Installazione finita!"
echo ""
echo "Per avviare l'app:"
echo "  - doppio clic su \"Avvia Video Downloader.command\""
echo "  - oppure compila l'app vera con: ./build_mac.sh"
echo ""
