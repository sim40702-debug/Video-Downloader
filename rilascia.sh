#!/bin/bash
# ------------------------------------------------------------
# rilascia.sh  (Mac)
#
# NUOVA VERSIONE:
#   ./rilascia.sh 1.0.1 "Cosa c'e' di nuovo"
#   1. scarica le ultime modifiche da GitHub (git pull)
#   2. scrive 1.0.1 in aggiornamenti.py
#   3. commit + push su GitHub, crea il tag v1.0.1
#   4. manda codice e tag anche su Gitea
#   5. compila l'app per Mac (build_mac.sh)
#   6. carica lo zip nella release v1.0.1 su Gitea
#
# PRIMA RELEASE (1.0.0), oppure SOLO RICOMPILARE la versione attuale:
#   ./rilascia.sh
#
# Dopo, sul PC Windows basta lanciare rilascia.bat per aggiungere
# alla stessa release anche la versione Windows.
# ------------------------------------------------------------

set -e
cd "$(dirname "$0")"
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"

# Repository su Gitea (prima il .118 a cavo, poi il .153)
GITEA_118="http://192.168.1.118:3000/Simone/Video-Downloader.git"
GITEA_153="http://192.168.1.153:3000/Simone/Video-Downloader.git"

NUOVA="$1"
NOTE="$2"

if [ ! -x ".venv/bin/python" ]; then
    echo "Ambiente virtuale non trovato: eseguo prima install.sh"
    ./install.sh
fi

manda_su_gitea() {
    # $@ = cosa mandare (es. main v1.0.1)
    echo "Mando su Gitea: provo 192.168.1.118..."
    if git push "$GITEA_118" "$@"; then
        echo "Usato il server 192.168.1.118"
    else
        echo "Il .118 non risponde: provo 192.168.1.153..."
        git push "$GITEA_153" "$@"
        echo "Usato il server 192.168.1.153"
    fi
}

if [ -n "$NUOVA" ]; then
    # Controllo del formato: tre numeri separati da punti (es. 1.0.1)
    if [[ ! "$NUOVA" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
        echo "Uso: ./rilascia.sh 1.0.1 \"note\"   oppure   ./rilascia.sh"
        exit 1
    fi

    ATTUALE=$(grep '^VERSIONE = ' aggiornamenti.py | cut -d'"' -f2)
    echo "Versione attuale: $ATTUALE  ->  nuova: $NUOVA"

    PIU_ALTA=$(printf '%s\n%s\n' "$ATTUALE" "$NUOVA" | sort -t. -k1,1n -k2,2n -k3,3n | tail -1)
    if [ "$NUOVA" = "$ATTUALE" ] || [ "$PIU_ALTA" != "$NUOVA" ]; then
        echo "La versione deve essere piu' alta di $ATTUALE."
        exit 1
    fi
    if git rev-parse "v$NUOVA" >/dev/null 2>&1; then
        echo "Il tag v$NUOVA esiste gia'."
        exit 1
    fi

    echo ""
    echo "1) Scarico le ultime modifiche da GitHub..."
    git pull --no-rebase --no-edit

    echo "2) Scrivo la versione $NUOVA..."
    perl -pi -e "s/^VERSIONE = \".*\"/VERSIONE = \"$NUOVA\"/" aggiornamenti.py

    echo "3) Commit, push e tag su GitHub..."
    git add -A
    git commit -m "Versione $NUOVA"
    git push
    git tag "v$NUOVA"
    git push origin "v$NUOVA"

    echo "4) Codice e tag su Gitea..."
    manda_su_gitea main "v$NUOVA"
else
    ATTUALE=$(grep '^VERSIONE = ' aggiornamenti.py | cut -d'"' -f2)
    echo "Nessuna versione indicata: ricompilo e ricarico la $ATTUALE."
    # Prima release: il tag non esiste ancora, lo creiamo adesso
    if ! git rev-parse "v$ATTUALE" >/dev/null 2>&1; then
        echo "Creo il tag v$ATTUALE e lo mando su GitHub..."
        git tag "v$ATTUALE"
        git push origin "v$ATTUALE"
    fi
    echo "Codice e tag su Gitea..."
    manda_su_gitea main "v$ATTUALE"
fi

echo ""
echo "5) Compilo l'app per Mac..."
./build_mac.sh

echo "6) Carico su Gitea..."
.venv/bin/python pubblica_release.py "$NOTE"

echo ""
echo "✓ Rilascio Mac completato."
echo "  Per aggiungere la versione Windows: sul PC lancia rilascia.bat"
