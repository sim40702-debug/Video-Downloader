"""
pubblica_release.py
-------------------
Carica lo zip compilato (dist/...) nella release su Gitea.
Lo usano rilascia.sh (Mac) e rilascia.bat (Windows): di solito
non serve avviarlo a mano.

Uso: python pubblica_release.py ["note della versione"]

- Se la release della versione attuale non esiste, la crea.
- Se lo zip per questo sistema c'e' gia', lo sostituisce.

Serve un token di Gitea (Impostazioni -> Applicazioni -> Genera token,
permesso "repository: lettura e scrittura"). Mettilo nel file
.gitea-token nella cartella del progetto (git lo ignora).
"""

import os
import sys
from pathlib import Path

import requests

import aggiornamenti as agg

CARTELLA = Path(__file__).resolve().parent
FILE_TOKEN = CARTELLA / ".gitea-token"


def leggi_token():
    token = os.environ.get("GITEA_TOKEN", "").strip()
    if not token and FILE_TOKEN.exists():
        token = FILE_TOKEN.read_text(encoding="utf-8").strip()
    if not token:
        print("Manca il token di Gitea.")
        print("Crealo su Gitea: Impostazioni -> Applicazioni -> Genera token")
        print("(permesso repository: lettura e scrittura) e salvalo nel file:")
        print(f"  {FILE_TOKEN}")
        sys.exit(1)
    return token


def main():
    note = sys.argv[1] if len(sys.argv) > 1 else ""
    versione = agg.VERSIONE
    tag = f"v{versione}"
    file_zip = CARTELLA / "dist" / agg.nome_zip()

    if not file_zip.exists():
        print(f"Non trovo {file_zip}")
        print("Compila prima l'app (build_mac.sh oppure build_windows.bat).")
        sys.exit(1)

    token = leggi_token()

    print("Cerco il server Gitea (prima 192.168.1.118, poi 192.168.1.153)...")
    server = agg.trova_server()
    if server is None:
        print("Nessun server Gitea risponde. Sei collegato alla rete di casa?")
        sys.exit(1)
    print(f"Uso il server: {server}")

    api = f"{server}/api/v1/repos/{agg.REPOSITORY}"
    intestazioni = {"Authorization": f"token {token}"}

    # 1) Cerco la release di questa versione, se non c'e' la creo
    risposta = requests.get(f"{api}/releases/tags/{tag}", headers=intestazioni, timeout=15)
    if risposta.status_code == 404:
        print(f"Creo la release {tag}...")
        risposta = requests.post(f"{api}/releases", headers=intestazioni, timeout=15, json={
            "tag_name": tag,
            "name": f"Video Downloader {versione}",
            "body": note or f"Versione {versione}",
            "target_commitish": "main",
        })
    if risposta.status_code == 401:
        print("Token non valido: controlla il file .gitea-token")
        sys.exit(1)
    if risposta.status_code >= 300:
        print(f"Errore da Gitea ({risposta.status_code}): {risposta.text[:300]}")
        sys.exit(1)
    release = risposta.json()

    # 2) Se lo zip c'e' gia' (es. ricompilato), tolgo quello vecchio
    for asset in release.get("assets") or []:
        if asset.get("name") == file_zip.name:
            print(f"Sostituisco il vecchio {file_zip.name}...")
            requests.delete(f"{api}/releases/{release['id']}/assets/{asset['id']}",
                            headers=intestazioni, timeout=15)

    # 3) Carico lo zip
    dimensione = file_zip.stat().st_size / (1024 * 1024)
    print(f"Carico {file_zip.name} ({dimensione:.0f} MB)...")
    with open(file_zip, "rb") as file:
        risposta = requests.post(
            f"{api}/releases/{release['id']}/assets",
            headers=intestazioni, params={"name": file_zip.name},
            files={"attachment": (file_zip.name, file, "application/zip")},
            timeout=600)
    if risposta.status_code >= 300:
        print(f"Caricamento non riuscito ({risposta.status_code}): {risposta.text[:300]}")
        sys.exit(1)

    print(f"[OK] {file_zip.name} pubblicato nella release {tag} su {server}")


if __name__ == "__main__":
    main()
