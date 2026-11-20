#!/bin/bash
# Doppio clic su questo file per avviare Video Downloader.
# La prima volta installa automaticamente tutto quello che serve.

cd "$(dirname "$0")"
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"

if [ ! -x ".venv/bin/python" ]; then
    echo "Prima esecuzione: installo le dipendenze..."
    ./install.sh || { echo "Installazione non riuscita."; read -r -p "Premi Invio per chiudere..."; exit 1; }
fi

# Avvia l'app; il Terminale si chiude da solo quando chiudi la finestra
nohup .venv/bin/python main.py >/dev/null 2>&1 &
exit 0
