// rilascia.js
// ------------------------------------------------------------
// Pubblica una nuova versione dell'app su GitHub.
//
//   npm run rilascia          -> nuova versione (es. 2.0.0 -> 2.0.1)
//   npm run rilascia 2.1.0    -> nuova versione 2.1.0
//
// Cambia il numero di versione, fa commit, push e tag.
// Poi GitHub (.github/workflows/release.yml) compila l'app per
// Mac e Windows e crea la release da solo. L'app trova la
// versione nuova da sola e propone di aggiornarsi.
// ------------------------------------------------------------

const { execSync } = require("child_process");
const fs = require("fs");
const path = require("path");

const cartella = __dirname;
const fileConfigurazione = path.join(cartella, "src-tauri", "tauri.conf.json");
const fileCargo = path.join(cartella, "src-tauri", "Cargo.toml");
const fileCargoLock = path.join(cartella, "src-tauri", "Cargo.lock");

// Esegue un comando e mostra quello che scrive
function esegui(comando) {
  console.log("> " + comando);
  execSync(comando, { cwd: cartella, stdio: "inherit" });
}

function ferma(messaggio) {
  console.log("\n[X] " + messaggio);
  process.exit(1);
}

// La versione "vera" e' quella in tauri.conf.json
function leggiVersione() {
  const configurazione = JSON.parse(fs.readFileSync(fileConfigurazione, "utf8"));
  return configurazione.version;
}

// Scrive la versione nei tre file che la contengono
function scriviVersione(versione) {
  const configurazione = JSON.parse(fs.readFileSync(fileConfigurazione, "utf8"));
  configurazione.version = versione;
  fs.writeFileSync(fileConfigurazione, JSON.stringify(configurazione, null, 2) + "\n");

  const cargo = fs.readFileSync(fileCargo, "utf8");
  fs.writeFileSync(fileCargo, cargo.replace(/^version = ".*"/m, `version = "${versione}"`));

  if (fs.existsSync(fileCargoLock)) {
    const lock = fs.readFileSync(fileCargoLock, "utf8");
    const nuovo = lock.replace(
      /(name = "video-downloader"\r?\nversion = )".*"/,
      `$1"${versione}"`
    );
    fs.writeFileSync(fileCargoLock, nuovo);
  }
}

// "2.0.9" -> "2.0.10"
function versioneSuccessiva(versione) {
  const numeri = versione.split(".").map(Number);
  return `${numeri[0]}.${numeri[1]}.${numeri[2] + 1}`;
}

// true se a e' piu' alta di b (es. "2.10.0" > "2.9.0")
function piuAlta(a, b) {
  const numeriA = a.split(".").map(Number);
  const numeriB = b.split(".").map(Number);
  for (let i = 0; i < 3; i++) {
    if (numeriA[i] > numeriB[i]) return true;
    if (numeriA[i] < numeriB[i]) return false;
  }
  return false;
}

// ---------- avvio ----------

console.log("1) Scarico le ultime modifiche...");
esegui("git pull --no-rebase --no-edit");

const attuale = leggiVersione();
const nuova = process.argv[2] || versioneSuccessiva(attuale);

if (!/^\d+\.\d+\.\d+$/.test(nuova)) {
  ferma("Uso: npm run rilascia   oppure   npm run rilascia 2.1.0");
}
if (!piuAlta(nuova, attuale)) {
  ferma(`La versione ${nuova} deve essere più alta di ${attuale}.`);
}

console.log(`\n=== Nuova versione: ${attuale} -> ${nuova} ===`);

console.log("\n2) Scrivo la nuova versione...");
scriviVersione(nuova);

console.log("\n3) Commit, push e tag su GitHub...");
esegui("git add -A");
esegui(`git commit -m "Versione ${nuova}"`);
esegui("git push");
esegui(`git tag v${nuova}`);
esegui(`git push origin v${nuova}`);

console.log(`\n[OK] Versione ${nuova} mandata su GitHub.`);
console.log("GitHub ora compila Mac e Windows e crea la release (circa 15-20 minuti).");
console.log("La segui nella scheda Actions della repository.");
