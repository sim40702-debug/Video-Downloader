# Video Downloader

App desktop per **macOS** (Apple Silicon e Intel) e **Windows** per scaricare **video MP4** e **audio MP3** da link di YouTube, quando il download è consentito.

Fatta in Python con CustomTkinter (grafica), yt-dlp (download) e FFmpeg (conversioni). Si aggiorna da sola prendendo le nuove versioni dal server **Gitea di casa**.

> Usala solo per contenuti che hai il diritto di scaricare: video tuoi, con licenza Creative Commons, o per cui l'autore lo permette. Rispetta i Termini di servizio di YouTube e il diritto d'autore.

---

## Cosa fa

- Incolli il link, premi **Analizza URL** e vedi copertina, titolo, canale, durata e visualizzazioni.
- Scegli **VIDEO** (MP4, fino al 4K) oppure **AUDIO** (MP3 da 128 a 320 kbps).
- Scegli la cartella (di base `Downloads`).
- Premi **SCARICA**: vedi percentuale, velocità, MB scaricati e tempo rimasto.
- Puoi **annullare** in ogni momento: i file a metà vengono cancellati.
- Se il file esiste già non lo sovrascrive: crea `Titolo (2).mp4`.
- **Apri cartella** ti mostra il file scaricato.
- Pulsante **Aggiornamenti**: controlla su Gitea se c'è una versione nuova e la installa da solo.

---

## 1. Installazione sul Mac

Serve **Homebrew** (https://brew.sh). Poi nel Terminale:

```bash
cd ~/Documents/Video-Downloader     # la cartella del progetto
chmod +x install.sh
./install.sh
```

Lo script controlla Python e tkinter, crea `.venv`, installa le librerie, ti chiede se installare **FFmpeg** e **Deno** con Homebrew (rispondi `S`) ed esegue i test.

Avvio: doppio clic su **`Avvia Video Downloader.command`** (la prima volta: clic destro → Apri).

## 2. Installazione su Windows

Serve **Python 3.10+**: `winget install Python.Python.3.12` oppure da python.org (spunta "Add python.exe to PATH").

Doppio clic su **`install_windows.bat`**: crea `.venv`, installa le librerie e ti chiede se installare **FFmpeg** e **Deno** con winget (rispondi `S`).

Avvio: doppio clic su **`Avvia Video Downloader.bat`**.

Perché servono FFmpeg e Deno:

- **FFmpeg** unisce video e audio (YouTube li manda separati sopra i 360p) e crea gli MP3.
- **Deno** serve a yt-dlp per leggere YouTube: dalla fine del 2025 senza Deno molti video non si scaricano.

Se un giorno i download smettono di funzionare, **riesegui lo script di installazione**: aggiorna yt-dlp.

---

## 3. Compilare l'app dal Mac

```bash
./build_mac.sh
```

Dopo qualche minuto in `dist/` trovi:

- `Video Downloader.app`: trascinala in **Applicazioni** (oppure `cp -R "dist/Video Downloader.app" /Applications/`)
- `Video-Downloader-macOS-apple-silicon.zip`: lo zip da caricare su Gitea

L'app compilata funziona sul tipo di Mac dove la compili: sul MacBook Air M2 viene la versione **Apple Silicon**. La prima apertura: **clic destro → Apri**.

FFmpeg e Deno non sono dentro l'app: restano installati con Homebrew e l'app li trova da sola.

## 4. Compilare l'app su Windows

Doppio clic su **`build_windows.bat`**. In `dist\` trovi:

- `Video Downloader\Video Downloader.exe`: l'app
- `Video-Downloader-windows.zip`: lo zip da caricare su Gitea

Copia la cartella `dist\Video Downloader` in `%LOCALAPPDATA%\Programs\` e crea un collegamento al `.exe` sul Desktop. Lì l'app si può aggiornare da sola (in "Programmi" no, servono i permessi da amministratore).

---

## 5. Gitea: preparazione (una volta sola)

1. Su Gitea (`http://192.168.1.118:3000`) crea il repository **`Simone/Video-Downloader`**, **pubblico** e **vuoto** (senza README). Pubblico serve perché l'app possa leggere le release senza password.
2. Crea un token: **Impostazioni → Applicazioni → Genera token**, permesso *repository: lettura e scrittura*.
3. Salva il token nel file **`.gitea-token`** nella cartella del progetto (sia sul Mac sia sul PC Windows). Git lo ignora: non finisce mai su GitHub.

La prima volta che `rilascia.sh` manda il codice a Gitea, git ti chiede utente e password: usa **Simone** e come password il **token**. Il Mac lo ricorda nel Portachiavi.

## 6. Pubblicare una nuova versione

Il codice sta su **GitHub**; le versioni compilate vanno su **Gitea**.

**Sul Mac:**

```bash
./rilascia.sh 1.0.1 "Cosa c'è di nuovo"
```

Fa tutto da solo: `git pull`, scrive la versione in `aggiornamenti.py`, commit e push su GitHub, crea il tag, manda codice e tag su Gitea (prima il .118, poi il .153), compila l'app per Mac e carica lo zip nella release su Gitea.

**Poi sul PC Windows:**

```
rilascia.bat
```

Fa `git pull`, compila la versione Windows e la aggiunge alla stessa release su Gitea.

Per ricompilare e ricaricare la versione attuale senza cambiare numero: `./rilascia.sh` (senza versione).

Per la **prima release** (versione 1.0.0, già scritta nel codice): esegui `./rilascia.sh` senza versione. Crea il tag v1.0.0, manda codice e tag su GitHub e su Gitea, compila e carica.

## 7. Come funzionano gli aggiornamenti

All'avvio l'app chiede a Gitea l'ultima release: prova prima **192.168.1.118** (cavo) e poi **192.168.1.153**, e nel messaggio dice quale server ha usato. Fuori casa nessuno dei due risponde e l'app non dice niente.

Se c'è una versione nuova il pulsante diventa blu (**Aggiorna a v1.0.1**). Cliccandolo:

- **app compilata**: scarica lo zip giusto per il computer (Windows, Mac Apple Silicon o Mac Intel), chiude l'app, sostituisce la vecchia e la riapre;
- **avviata dal codice** (`main.py`): fa `git pull` e aggiorna le librerie.

Su un Mac Intel l'aggiornamento automatico funziona solo se nella release c'è lo zip `...-macOS-intel.zip`. La GitHub Action lo compila (vedi sotto): puoi scaricarlo dalla release di GitHub e caricarlo a mano su Gitea.

## 8. Release su GitHub (automatica)

Non serve fare niente a mano: a ogni push su `main` la GitHub Action (`.github/workflows/release.yml`) legge `VERSIONE` in `aggiornamenti.py`.

- Se su GitHub **non esiste ancora** la release con quel numero, compila l'app per **Mac Apple Silicon, Mac Intel e Windows** e crea la release da sola (circa 15 minuti, la segui nella scheda **Actions**).
- Se esiste già, non fa niente.

Quindi per una nuova versione su GitHub basta cambiare il numero (lo fa `./rilascia.sh 1.0.1`) e fare push. Si può anche avviare a mano: scheda **Actions** → **Release** → **Run workflow**.

---

## Test

```bash
.venv/bin/python -m unittest discover -s tests -v          # Mac
.venv\Scripts\python -m unittest discover -s tests -v      # Windows
```

- `test_downloader.py`: link, numeri, qualità, nomi dei file, errori, cartelle; più **download veri** da un server locale (MP4, MP3, annullamento). Non serve Internet.
- `test_aggiornamenti.py`: versioni, file giusto per ogni sistema, scelta del server .118/.153, script che sostituisce l'app.
- `test_interfaccia.py`: apre la finestra senza mostrarla e prova i pulsanti.

---

## Struttura del progetto

```
Video-Downloader/
├── main.py                           avvio: controlla le librerie e apre la finestra
├── interface.py                      grafica (CustomTkinter)
├── downloader.py                     logica di download (yt-dlp + FFmpeg)
├── aggiornamenti.py                  versione dell'app e aggiornamenti da Gitea
├── pubblica_release.py               carica lo zip nella release su Gitea
├── crea_icona.py                     disegna l'icona per Mac e Windows
├── requirements.txt                  librerie Python
├── install.sh / install_windows.bat  installazione automatica
├── build_mac.sh / build_windows.bat  compilazione dell'app
├── rilascia.sh / rilascia.bat        pubblicazione di una nuova versione
├── Avvia Video Downloader.command  avvio con doppio clic (Mac)
├── Avvia Video Downloader.bat      avvio con doppio clic (Windows)
├── tests/                            test automatici
└── .github/workflows/release.yml     release automatica su GitHub
```

Come funziona dentro, in breve:

- `downloader.py` non sa niente della grafica: si può usare e testare da solo.
- I lavori lenti (analisi, download, aggiornamenti) girano in un **thread separato**, così la finestra non si blocca.
- Il thread non tocca mai la grafica: manda messaggi in una **coda**, e la finestra li legge ogni 100 ms.
- Per annullare, il pulsante accende un "semaforo" (`threading.Event`); yt-dlp lo controlla a ogni pezzo scaricato e si ferma.

---

## Problemi comuni

| Problema | Soluzione |
|---|---|
| "Errore 403" o i video non si scaricano più | Riesegui lo script di installazione per aggiornare yt-dlp. Controlla che Deno sia installato: `deno --version` |
| Vedi solo la qualità 360p | Manca FFmpeg: `brew install ffmpeg` (Mac) o `winget install Gyan.FFmpeg` (Windows) |
| "Manca tkinter" | Mac: `brew install python-tk`. Windows: reinstalla Python da python.org |
| macOS blocca l'app | Clic destro → Apri, oppure `xattr -dr com.apple.quarantine "dist/Video Downloader.app"` |
| Windows dice "PC protetto" | Clicca "Ulteriori informazioni" → "Esegui comunque" |
| "Il server Gitea di casa non risponde" | Sei fuori casa o il Lenovo è spento |
| "Nessuna release (o repository non pubblico)" | Rendi pubblico il repository su Gitea, oppure pubblica la prima release |
| "Token non valido" | Rigenera il token su Gitea e rimettilo in `.gitea-token` |
| Un video 4K non si apre con QuickTime | Il 4K di YouTube usa codec che QuickTime non sempre legge: usa VLC o IINA |
