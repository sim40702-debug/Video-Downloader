# Video Downloader

App desktop per **Mac** (Apple Silicon e Intel) e **Windows** per scaricare **video MP4** e **audio MP3** da link di YouTube, quando il download è consentito.

Fatta con **Tauri**: la grafica è in HTML, CSS e JavaScript, la parte che lavora "sotto" è in Rust. Per scaricare usa tre programmi gratuiti (yt-dlp, FFmpeg e Deno) che l'app scarica da sola al primo avvio. Si aggiorna da sola prendendo le nuove versioni dalle release di GitHub.

> Usala solo per contenuti che hai il diritto di scaricare: video tuoi, con licenza Creative Commons, o per cui l'autore lo permette. Rispetta i Termini di servizio di YouTube e il diritto d'autore.

---

## Cosa fa

- Incolli il link (se il campo è vuoto parte da solo) e vedi copertina, titolo, canale, durata e visualizzazioni.
- Scegli **Video** (MP4, fino al 4K) oppure **Audio** (MP3 da 128 a 320 kbps), con la dimensione stimata del file.
- Scegli la cartella (di base `Download`).
- **Scarica**: il video va nell'elenco **Download**, con percentuale, MB scaricati, velocità e tempo rimasto.
- **Più download insieme**: mentre uno scarica puoi analizzare altri link e premere **Aggiungi ai download**; vengono scaricati uno dopo l'altro. Se incolli più link in una volta, finiscono tutti nell'elenco con il formato e la qualità scelti.
- Il pulsante tondo a destra di ogni download lo **ferma** (i file a metà vengono cancellati) o, quando è finito, lo **mostra nel Finder**. **Togli i completati** pulisce l'elenco.
- Se stai usando un'altra app, a fine download arriva la **notifica** del sistema.
- **Impostazioni** (pulsante accanto ad Analizza, oppure ⌘, sul Mac e Ctrl+, su Windows):
  - *Generali*: tema automatico, chiaro o scuro; notifiche; controllo degli aggiornamenti.
  - *Download*: cartella, formato e qualità con cui parte l'app, nome del file (titolo, canale - titolo, data - titolo), cosa fare se il file esiste già (copia o sostituisci).
  - *Componenti*: versioni di yt-dlp, FFmpeg e Deno, aggiornamento di yt-dlp, ripristino delle impostazioni.
- Se il file esiste già non lo sovrascrive: crea `Titolo (2).mp4`.
- Grafica chiara o scura, segue da sola il sistema.
- Quando esce una versione nuova compare un avviso in alto: **Aggiorna**, e l'app si aggiorna e si riavvia.
- yt-dlp si aggiorna da solo a ogni avvio, così segue i cambiamenti di YouTube senza bisogno di una nuova versione dell'app.

---

## Installare l'app

Scarica il file dalla pagina **Releases** del repository:

- **Mac**: `Video.Downloader_X.Y.Z_universal.dmg` (va su Apple Silicon e su Intel). Aprilo e trascina l'app in Applicazioni.
- **Windows**: `Video.Downloader_X.Y.Z_x64-setup.exe`. Si installa per il tuo utente, senza permessi da amministratore.

L'app non è firmata da Apple o Microsoft, quindi la prima volta il sistema chiede conferma:

- **Mac**: apri l'app, chiudi l'avviso, poi vai in **Impostazioni di Sistema → Privacy e sicurezza** e premi **Apri comunque**. Oppure, nel Terminale:
  `xattr -dr com.apple.quarantine "/Applications/Video Downloader.app"`
- **Windows**: se compare "PC protetto", clicca **Ulteriori informazioni → Esegui comunque**.

Al primo avvio l'app scarica yt-dlp, FFmpeg e Deno (circa 140 MB, solo la prima volta). Se FFmpeg o Deno sono già installati sul computer (per esempio con Homebrew), usa quelli.

---

## Sviluppare e compilare sul Mac

### Una volta sola

1. Installa **Rust**:
   ```bash
   curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
   ```
   Chiudi e riapri il Terminale.
2. Installa **Node.js** (se non ce l'hai già): `brew install node`
3. Installa gli strumenti di Apple (se non li hai già): `xcode-select --install`
4. Nella cartella del progetto:
   ```bash
   npm install
   ```

### Provare l'app mentre la modifichi

```bash
npm run dev
```

Si apre l'app. Se cambi un file in `src/` (grafica) basta ricaricare con Cmd+R; se cambi un file in `src-tauri/` (Rust) si ricompila da sola.

### Compilare l'app vera

```bash
npm run build
```

La prima volta ci mette qualche minuto. Il risultato è in:

- `src-tauri/target/release/bundle/macos/Video Downloader.app`: trascinala in Applicazioni
- `src-tauri/target/release/bundle/dmg/`: il file `.dmg`

Così compili per il tuo Mac (Apple Silicon). La versione che va su tutti i Mac (universale) e quella per Windows le compila GitHub.

### Test

```bash
cd src-tauri
cargo test
```

I test controllano i link, i nomi dei file, le qualità, gli errori e la lettura dell'avanzamento. Ci sono anche test con **download veri** da un piccolo server locale (video, MP3, annullamento): partono solo se indichi dove sono i tre programmi, per esempio:

```bash
VD_YTDLP=~/Library/Application\ Support/ch.simone.videodownloader/programmi/yt-dlp \
VD_FFMPEG=$(which ffmpeg) VD_DENO=$(which deno) cargo test
```

---

## Pubblicare una nuova versione

```bash
npm run rilascia
```

Aumenta la versione da sola (es. 2.0.0 → 2.0.1), fa commit, push e tag su GitHub. Poi GitHub compila l'app per Mac e Windows e crea la release (circa 15-20 minuti, la segui nella scheda **Actions**). Chi ha già l'app riceve l'avviso **Aggiorna**.

Per scegliere tu il numero: `npm run rilascia 2.1.0`

### La chiave per firmare gli aggiornamenti (una volta sola)

Gli aggiornamenti sono firmati: così l'app installa solo versioni create da te. Serve un segreto su GitHub:

```bash
gh secret set TAURI_SIGNING_PRIVATE_KEY --repo sim40702-debug/Video-Downloader < video-downloader.key
```

Il file `video-downloader.key` tienilo al sicuro (per esempio in `~/.tauri/`) e **non metterlo mai nel repository**: chi ce l'ha potrebbe firmare aggiornamenti al posto tuo. Se lo perdi, le app già installate non potranno più aggiornarsi da sole.

---

## Struttura del progetto

```
Video-Downloader/
├── src/                         la grafica
│   ├── index.html               com'è fatta la finestra
│   ├── style.css                colori e stile (chiaro e scuro)
│   ├── app.js                   cosa succede quando premi i pulsanti
│   ├── impostazioni.html        la finestra Impostazioni
│   ├── impostazioni.js          la logica della finestra Impostazioni
│   └── icona.png                icona per la schermata del primo avvio
├── src-tauri/                   la parte in Rust
│   ├── src/main.rs              avvio
│   ├── src/lib.rs               i comandi che la grafica chiama con invoke()
│   ├── src/ytdlp.rs             analisi, download, annullamento, errori in italiano
│   ├── src/componenti.rs        trova o scarica yt-dlp, FFmpeg e Deno
│   ├── src/impostazioni.rs      salva e legge le impostazioni (impostazioni.json)
│   ├── tauri.conf.json          nome, versione, finestra, aggiornamenti
│   ├── tauri.release.conf.json  in più per le release (file per gli aggiornamenti)
│   ├── capabilities/            permessi della finestra
│   ├── icons/                   icone dell'app
│   └── Cargo.toml               librerie Rust
├── rilascia.js                  npm run rilascia
├── package.json                 comandi npm
└── .github/workflows/release.yml  release automatica su GitHub
```

Come funziona dentro, in breve:

- La grafica chiama la parte Rust con `invoke("analizza", { url })`, `invoke("scarica", {...})` e così via.
- Rust avvia yt-dlp e legge riga per riga quello che scrive; ogni riga di avanzamento diventa un evento (`progresso`) che la grafica ascolta con `listen()`.
- I lavori lunghi girano in un thread separato, quindi la finestra non si blocca mai.
- **Annulla** ferma yt-dlp e cancella i file che iniziano con il nome del download.

---

## Problemi comuni

| Problema | Soluzione |
|---|---|
| "YouTube ha rifiutato il download" | Chiudi e riapri l'app: yt-dlp si aggiorna da solo all'avvio |
| "Connessione a Internet assente" | Controlla la rete |
| Il Mac dice che l'app è danneggiata o non si può aprire | Vedi "Installare l'app": Apri comunque, oppure il comando `xattr` |
| Windows dice "PC protetto" | Ulteriori informazioni → Esegui comunque |
| La release su GitHub fallisce al passaggio di firma | Manca il segreto `TAURI_SIGNING_PRIVATE_KEY` (vedi sopra) |
| Un video 4K non si apre con QuickTime | Il 4K di YouTube usa codec che QuickTime non sempre legge: usa VLC o IINA |
| Video privati, con limite d'età o solo per membri | Non si possono scaricare: l'app lo dice con un messaggio |
