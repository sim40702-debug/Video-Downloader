// impostazioni.js
// ------------------------------------------------------------
// La finestra Impostazioni. Ogni volta che cambi qualcosa lo salva
// subito (non c'e' un pulsante "Salva", come sul Mac).
// La parte Rust avvisa anche la finestra principale con l'evento
// "impostazioni", cosi' le due finestre restano allineate.
// ------------------------------------------------------------

const { invoke } = window.__TAURI__.core;
const { listen, emit } = window.__TAURI__.event;
const { getCurrentWindow } = window.__TAURI__.window;

function elemento(id) {
  return document.getElementById(id);
}

let imp = null;              // le impostazioni attuali
let cartellaDownload = "";   // la cartella Download del computer
let nuovaVersione = null;    // es. "0.1.3" se c'e' un aggiornamento

// ---------- Salvataggio ----------

async function salva() {
  try {
    await invoke("salva_impostazioni", { impostazioni: imp });
  } catch (errore) {
    console.error(errore); // capita solo se il disco è pieno o protetto
  }
}

// ---------- Mostrare le impostazioni nei controlli ----------

function nomeCartella(percorso) {
  const pezzi = percorso.split(/[\\/]/).filter((p) => p !== "");
  return pezzi[pezzi.length - 1] || percorso;
}

function scegliPulsante(selettore, attributo, valore) {
  for (const pulsante of document.querySelectorAll(selettore)) {
    pulsante.setAttribute("aria-checked", pulsante.dataset[attributo] === valore ? "true" : "false");
  }
}

function mostra() {
  document.documentElement.dataset.tema = imp.tema;
  scegliPulsante("[data-tema]", "tema", imp.tema);
  elemento("notifiche").checked = imp.notifiche;
  elemento("controlla-aggiornamenti").checked = imp.controlla_aggiornamenti;

  const cartella = imp.cartella || cartellaDownload;
  elemento("nome-cartella").textContent = nomeCartella(cartella);
  elemento("cartella").title = cartella;
  scegliPulsante("[data-formato]", "formato", imp.formato);
  elemento("qualita-video").value = String(imp.qualita_video);
  elemento("qualita-audio").value = String(imp.qualita_audio);
  elemento("nome-file").value = imp.nome_file;
  elemento("se-esiste").value = imp.se_esiste;

  elemento("aggiorna-ytdlp").checked = imp.aggiorna_ytdlp;
  elemento("ultimo-controllo").textContent = "Ultimo controllo: " + quando(imp.ultimo_controllo_ytdlp);
}

// 1732345920 -> "oggi alle 07:52"
function quando(secondi) {
  if (!secondi) return "mai";
  const data = new Date(secondi * 1000);
  const ora = data.toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" });
  const oggi = new Date();
  const ieri = new Date();
  ieri.setDate(oggi.getDate() - 1);
  if (data.toDateString() === oggi.toDateString()) return `oggi alle ${ora}`;
  if (data.toDateString() === ieri.toDateString()) return `ieri alle ${ora}`;
  return `il ${data.toLocaleDateString("it-IT", { day: "2-digit", month: "2-digit" })} alle ${ora}`;
}

// ---------- Schede ----------

const titoliSchede = { generali: "Generali", download: "Download", componenti: "Componenti" };

function apriScheda(nome) {
  for (const scheda of document.querySelectorAll(".scheda")) {
    scheda.setAttribute("aria-selected", scheda.dataset.scheda === nome ? "true" : "false");
  }
  for (const pannello of document.querySelectorAll(".pannello")) {
    pannello.hidden = pannello.id !== "pannello-" + nome;
  }
  getCurrentWindow().setTitle(titoliSchede[nome]);
  if (nome === "componenti") caricaVersioni();
}

// ---------- Generali ----------

async function cercaAggiornamenti() {
  if (nuovaVersione) {
    // Lo installa la finestra principale, che mostra la barra di avanzamento
    emit("avvia-aggiornamento");
    elemento("stato-versione").textContent = "aggiorno...";
    elemento("pulsante-versione").disabled = true;
    return;
  }
  elemento("stato-versione").textContent = "controllo...";
  elemento("pulsante-versione").disabled = true;
  try {
    const nuova = await invoke("controlla_aggiornamento");
    if (nuova) {
      nuovaVersione = nuova.versione;
      elemento("stato-versione").textContent = `è disponibile la ${nuova.versione}`;
      elemento("pulsante-versione").textContent = "Aggiorna";
    } else {
      elemento("stato-versione").textContent = "è l'ultima";
    }
  } catch (errore) {
    elemento("stato-versione").textContent = "controllo non riuscito";
  }
  elemento("pulsante-versione").disabled = false;
}

// ---------- Download ----------

async function cambiaCartella() {
  const scelta = await invoke("scegli_cartella", { attuale: imp.cartella || cartellaDownload });
  if (scelta) {
    imp.cartella = scelta;
    mostra();
    salva();
  }
}

// ---------- Componenti ----------

async function caricaVersioni() {
  const lista = await invoke("versioni_componenti");
  for (const c of lista) {
    let testo = c.versione;
    // per yt-dlp la provenienza e' sempre "dell'app": non serve scriverla
    if (c.origine && c.nome !== "yt-dlp") testo += `, ${c.origine}`;
    elemento("versione-" + c.nome).textContent = testo;
  }
}

async function aggiornaYtdlp() {
  const pulsante = elemento("pulsante-aggiorna-ytdlp");
  pulsante.disabled = true;
  pulsante.textContent = "Aggiorno...";
  try {
    await invoke("aggiorna_ytdlp");
    await caricaVersioni();
  } catch (errore) {
    elemento("ultimo-controllo").textContent = errore;
  }
  pulsante.disabled = false;
  pulsante.textContent = "Aggiorna adesso";
}

// Ripristina chiede conferma: il primo clic cambia il pulsante, il secondo ripristina
let attesaConferma = null;

async function ripristina() {
  const pulsante = elemento("pulsante-ripristina");
  if (attesaConferma === null) {
    pulsante.textContent = "Sì, ripristina";
    pulsante.classList.add("pericolo");
    attesaConferma = setTimeout(() => {
      pulsante.textContent = "Ripristina";
      pulsante.classList.remove("pericolo");
      attesaConferma = null;
    }, 4000);
    return;
  }
  clearTimeout(attesaConferma);
  attesaConferma = null;
  pulsante.textContent = "Ripristina";
  pulsante.classList.remove("pericolo");
  imp = await invoke("ripristina_impostazioni");
  mostra();
}

// ---------- Avvio ----------

async function avvio() {
  cartellaDownload = await invoke("cartella_download");
  imp = await invoke("leggi_impostazioni");
  mostra();
  elemento("testo-versione").textContent = "Versione " + (await invoke("versione_app"));

  // Schede
  for (const scheda of document.querySelectorAll(".scheda")) {
    scheda.addEventListener("click", () => apriScheda(scheda.dataset.scheda));
  }

  // Generali
  for (const pulsante of document.querySelectorAll("[data-tema]")) {
    pulsante.addEventListener("click", () => {
      imp.tema = pulsante.dataset.tema;
      mostra();
      salva();
    });
  }
  elemento("notifiche").addEventListener("change", (e) => {
    imp.notifiche = e.target.checked;
    salva();
  });
  elemento("controlla-aggiornamenti").addEventListener("change", (e) => {
    imp.controlla_aggiornamenti = e.target.checked;
    salva();
  });
  elemento("pulsante-versione").addEventListener("click", cercaAggiornamenti);

  // Download
  elemento("pulsante-cartella").addEventListener("click", cambiaCartella);
  for (const pulsante of document.querySelectorAll("[data-formato]")) {
    pulsante.addEventListener("click", () => {
      imp.formato = pulsante.dataset.formato;
      mostra();
      salva();
    });
  }
  elemento("qualita-video").addEventListener("change", (e) => {
    imp.qualita_video = Number(e.target.value);
    salva();
  });
  elemento("qualita-audio").addEventListener("change", (e) => {
    imp.qualita_audio = Number(e.target.value);
    salva();
  });
  elemento("nome-file").addEventListener("change", (e) => {
    imp.nome_file = e.target.value;
    salva();
  });
  elemento("se-esiste").addEventListener("change", (e) => {
    imp.se_esiste = e.target.value;
    salva();
  });

  // Componenti
  elemento("aggiorna-ytdlp").addEventListener("change", (e) => {
    imp.aggiorna_ytdlp = e.target.checked;
    salva();
  });
  elemento("pulsante-aggiorna-ytdlp").addEventListener("click", aggiornaYtdlp);
  elemento("pulsante-ripristina").addEventListener("click", ripristina);

  // Se le impostazioni cambiano dalla finestra principale (es. la cartella)
  listen("impostazioni", (evento) => {
    imp = evento.payload;
    mostra();
  });
}

avvio();
