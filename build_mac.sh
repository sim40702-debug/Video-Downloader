#!/bin/bash
# ------------------------------------------------------------
# build_mac.sh
# Compila l'app per Mac: "Video Downloader.app".
# Uso: ./build_mac.sh
# Risultato in dist/:
#   - Video Downloader.app                    (da trascinare in Applicazioni)
#   - Video-Downloader-macOS-apple-silicon.zip (da caricare su Gitea)
#     oppure ...-macOS-intel.zip se compili su un Mac Intel
# ------------------------------------------------------------

set -e
cd "$(dirname "$0")"
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"

NOME_APP="Video Downloader"
CARTELLA_TEMP="build_temp"

echo "=== Compilazione di $NOME_APP.app ($(uname -m)) ==="

# 1) Serve l'ambiente virtuale creato da install.sh
if [ ! -x ".venv/bin/python" ]; then
    echo "Ambiente virtuale non trovato: eseguo prima install.sh"
    ./install.sh
fi

echo "Installo/aggiorno PyInstaller..."
.venv/bin/python -m pip install --upgrade pyinstaller --quiet

NOME_ZIP=$(.venv/bin/python -c "import aggiornamenti; print(aggiornamenti.nome_zip())")

# Puliamo eventuali build vecchie
rm -rf "$CARTELLA_TEMP" build "dist/$NOME_APP.app" "dist/$NOME_APP" "dist/$NOME_ZIP"
mkdir -p "$CARTELLA_TEMP"

# 2) Icona
.venv/bin/python crea_icona.py "$CARTELLA_TEMP"
ICONA_OPZIONE=()   # lista vuota: senza icona se iconutil manca
if command -v iconutil >/dev/null 2>&1 && command -v sips >/dev/null 2>&1; then
    ICONSET="$CARTELLA_TEMP/icona.iconset"
    mkdir -p "$ICONSET"
    for dimensione in 16 32 128 256 512; do
        doppia=$((dimensione * 2))
        sips -z $dimensione $dimensione "$CARTELLA_TEMP/icona.png" --out "$ICONSET/icon_${dimensione}x${dimensione}.png" >/dev/null
        sips -z $doppia $doppia "$CARTELLA_TEMP/icona.png" --out "$ICONSET/icon_${dimensione}x${dimensione}@2x.png" >/dev/null
    done
    iconutil -c icns "$ICONSET" -o "$CARTELLA_TEMP/icona.icns"
    ICONA_OPZIONE=(--icon "$PWD/$CARTELLA_TEMP/icona.icns")
fi

# 3) Compilazione
echo "Compilo con PyInstaller (ci vuole qualche minuto)..."
.venv/bin/python -m PyInstaller \
    --noconfirm \
    --windowed \
    --name "$NOME_APP" \
    --osx-bundle-identifier "ch.simone.videodownloader" \
    "${ICONA_OPZIONE[@]}" \
    --collect-all customtkinter \
    --collect-all yt_dlp_ejs \
    --collect-data certifi \
    --workpath "$CARTELLA_TEMP/work" \
    --specpath "$CARTELLA_TEMP" \
    --distpath dist \
    main.py

# 4) Zip per Gitea (ditto mantiene permessi e collegamenti dell'app)
echo "Creo lo zip $NOME_ZIP..."
ditto -c -k --keepParent "dist/$NOME_APP.app" "dist/$NOME_ZIP"

# 5) Pulizia dei file temporanei (restano solo l'app e lo zip in dist/)
rm -rf "$CARTELLA_TEMP" build "dist/$NOME_APP"
find . -name "__pycache__" -type d -not -path "./.venv/*" -prune -exec rm -rf {} + 2>/dev/null || true

echo ""
echo "✓ Fatto!"
echo "  App:  dist/$NOME_APP.app"
echo "  Zip:  dist/$NOME_ZIP"
echo ""
echo "Per installarla: trascina l'app in Applicazioni, oppure scrivi"
echo "  cp -R \"dist/$NOME_APP.app\" /Applications/"
