// rilascia.js
// ------------------------------------------------------------
// Pubblica una nuova versione dell'app. Funziona su Mac e su Windows.
//
//   npm run rilascia git          -> nuova versione su GitHub (es. 1.0.0 -> 1.0.1)
//   npm run rilascia git 1.2.0    -> nuova versione 1.2.0 su GitHub
//   npm run rilascia              -> carica su Gitea la versione attuale
//
// GitHub: cambia il numero di versione, fa commit e push.
//         Poi GitHub (release.yml) compila Mac + Windows e fa la release da solo.
// Gitea:  scarica le ultime modifiche, compila l'app su QUESTO computer
//         e carica lo zip nella release su Gitea.
//         Sul Mac carica la versione Mac, sul PC Windows quella Windows.
//
// Di solito: prima "npm run rilascia git", poi "npm run rilascia"
// sul Mac e sul PC Windows.
// ------------------------------------------------------------

const { execSync } = require("child_process");
const fs = require("fs");
const path = require("path");

const cartella = __dirname;
const fileVersione = path.join(cartella, "aggiornamenti.py");
const suWindows = process.platform === "win32";

// Python dell'ambiente virtuale (creato dallo script di installazione)
const python = suWindows ? ".venv\\Scripts\\python.exe" : ".venv/bin/python";

// Repository su Gitea: prima il .118 (a cavo), poi il .153
const serverGitea = [
  "http://192.168.1.118:3000/Simone/Video-Downloader.git",
  "http://192.168.1.153:3000/Simone/Video-Downloader.git",
];

// ---------- funzioni di aiuto ----------

// Esegue un comando e mostra quello che scrive
function esegui(comando) {
  console.log("> " + comando);
  execSync(comando, { cwd: cartella, stdio: "inherit" });
}

// Esegue un comando senza mostrare niente: true se e' andato bene
function provaComando(comando) {
  try {
    execSync(comando, { cwd: cartella, stdio: "ignore" });
    return true;
  } catch (errore) {
    return false;
  }
}

// Legge VERSIONE = "1.0.0" da aggiornamenti.py
function leggiVersione() {
  const testo = fs.readFileSync(fileVersione, "utf8");
  const trovata = testo.match(/^VERSIONE = "(.*)"/m);
  return trovata[1];
}

// Scrive la nuova versione in aggiornamenti.py
function scriviVersione(versione) {
  const testo = fs.readFileSync(fileVersione, "utf8");
  const nuovo = testo.replace(/^VERSIONE = ".*"/m, `VERSIONE = "${versione}"`);
  fs.writeFileSync(fileVersione, nuovo, "utf8");
}

// "1.0.9" -> "1.0.10"
function versioneSuccessiva(versione) {
  const numeri = versione.split(".").map(Number);
  return `${numeri[0]}.${numeri[1]}.${numeri[2] + 1}`;
}

// true se a e' piu' alta di b (es. "1.10.0" > "1.9.0")
function piuAlta(a, b) {
  const numeriA = a.split(".").map(Number);
  const numeriB = b.split(".").map(Number);
  for (let i = 0; i < 3; i++) {
    if (numeriA[i] > numeriB[i]) return true;
    if (numeriA[i] < numeriB[i]) return false;
  }
  return false;
}

function ferma(messaggio) {
  console.log("\n[X] " + messaggio);
  process.exit(1);
}

// Se manca l'ambiente virtuale lancia l'installazione
function controllaInstallazione() {
  if (!fs.existsSync(path.join(cartella, python))) {
    console.log("Ambiente virtuale non trovato: eseguo l'installazione...");
    esegui(suWindows ? "install_windows.bat senza-pausa" : "./install.sh");
  }
}

// ---------- GitHub ----------

function rilasciaSuGitHub(versioneScelta) {
  const attuale = leggiVersione();
  const nuova = versioneScelta || versioneSuccessiva(attuale);

  if (!/^\d+\.\d+\.\d+$/.test(nuova)) {
    ferma("La versione deve essere tipo 1.2.0");
  }
  if (!piuAlta(nuova, attuale)) {
    ferma(`La versione ${nuova} deve essere piu' alta di ${attuale}.`);
  }

  console.log(`\n=== Nuova versione su GitHub: ${attuale} -> ${nuova} ===\n`);

  console.log("1) Scarico le ultime modifiche...");
  esegui("git pull --no-rebase --no-edit");

  console.log("\n2) Scrivo la nuova versione...");
  scriviVersione(nuova);

  console.log("\n3) Commit e push su GitHub...");
  esegui("git add -A");
  esegui(`git commit -m "Versione ${nuova}"`);
  esegui("git push");
  esegui(`git tag v${nuova}`);
  esegui(`git push origin v${nuova}`);

  console.log(`\n[OK] Versione ${nuova} mandata su GitHub.`);
  console.log("GitHub ora compila Mac e Windows e crea la release (circa 15 minuti).");
  console.log("La segui nella scheda Actions della repository.");
  console.log("Per Gitea: npm run rilascia (sul Mac e sul PC Windows)");
}

// ---------- Gitea ----------

function mandaSuGitea(versione) {
  for (const indirizzo of serverGitea) {
    console.log("Provo " + indirizzo + " ...");
    if (provaComando(`git push "${indirizzo}" main v${versione}`)) {
      console.log("Usato il server: " + indirizzo);
      return;
    }
  }
  console.log("[!] Non riesco a mandare il codice su Gitea: continuo lo stesso.");
}

function rilasciaSuGitea() {
  controllaInstallazione();

  console.log("\n1) Scarico le ultime modifiche...");
  esegui("git pull --no-rebase --no-edit");

  const versione = leggiVersione();
  console.log(`\n=== Versione ${versione} su Gitea ===`);

  // Il tag serve a Gitea per creare la release
  if (!provaComando(`git rev-parse v${versione}`)) {
    console.log(`\nIl tag v${versione} non c'e': lo creo e lo mando su GitHub...`);
    esegui(`git tag v${versione}`);
    esegui(`git push origin v${versione}`);
  }

  console.log("\n2) Mando codice e tag su Gitea...");
  mandaSuGitea(versione);

  console.log("\n3) Compilo l'app per questo computer...");
  esegui(suWindows ? "build_windows.bat" : "./build_mac.sh");

  console.log("\n4) Carico lo zip su Gitea...");
  esegui(`"${python}" pubblica_release.py`);

  console.log(`\n[OK] Versione ${versione} pubblicata su Gitea.`);
}

// ---------- avvio ----------

const dove = process.argv[2];
if (dove === "git" || dove === "github") {
  rilasciaSuGitHub(process.argv[3]);
} else if (dove === undefined) {
  rilasciaSuGitea();
} else {
  ferma("Uso: npm run rilascia   oppure   npm run rilascia git [versione]");
}
