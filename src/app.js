// app.js
// ------------------------------------------------------------
// La logica della finestra.
// Per parlare con la parte in Rust (src-tauri/src/lib.rs) usiamo:
//   invoke("nome_comando", { ...dati })  -> chiama un comando
//   listen("nome_evento", funzione)      -> riceve gli aggiornamenti
// ------------------------------------------------------------

const { invoke } = window.__TAURI__.core;
const { listen } = window.__TAURI__.event;

// Scorciatoia per prendere un elemento della pagina
function elemento(id) {
  return document.getElementById(id);
}

// ---------- Stato dell'app ----------
let video = null;              // informazioni del video analizzato
let modalita = "video";        // "video" oppure "audio"
let cartella = "";             // dove salvare
let occupato = false;          // true durante analisi o download
let ultimoFile = null;         // ultimo file scaricato

const suMac = navigator.userAgent.includes("Mac");
const nomeEsplora = suMac ? "Mostra nel Finder" : "Mostra in Esplora file";

const qualitaAudio = [
  { kbps: 320, nome: "320 kbps, massima" },
  { kbps: 256, nome: "256 kbps" },
  { kbps: 192, nome: "192 kbps, consigliata" },
  { kbps: 128, nome: "128 kbps, file più piccolo" },
];

// ---------- Numeri leggibili ----------

// 43000000 -> "41 MB"   1536000 -> "1,5 MB"
function formattaByte(byte) {
  if (!byte) return "";
  const unita = ["B", "KB", "MB", "GB"];
  let valore = byte;
  let i = 0;
  while (valore >= 1024 && i < unita.length - 1) {
    valore = valore / 1024;
    i++;
  }
  const cifre = valore >= 100 || i === 0 ? 0 : 1;
  return valore.toLocaleString("it-IT", { maximumFractionDigits: cifre }) + " " + unita[i];
}

// 212 -> "3 min 32 s"   3725 -> "1 h 2 min"
function formattaDurata(secondi) {
  if (secondi == null) return "";
  secondi = Math.round(secondi);
  const ore = Math.floor(secondi / 3600);
  const minuti = Math.floor((secondi % 3600) / 60);
  const resto = secondi % 60;
  if (ore > 0) return `${ore} h ${minuti} min`;
  if (minuti > 0) return `${minuti} min ${resto} s`;
  return `${resto} s`;
}

// 12345 -> "12.345"
function formattaNumero(numero) {
  return numero.toLocaleString("it-IT");
}

function nomeQualita(altezza) {
  const nomi = { 2160: "4K", 1440: "2K", 1080: "Full HD", 720: "HD" };
  return nomi[altezza] ? `${altezza}p ${nomi[altezza]}` : `${altezza}p`;
}

// "/Users/simone/Downloads" -> "Downloads"
function nomeCartella(percorso) {
  const pezzi = percorso.split(/[\\/]/).filter((p) => p !== "");
  return pezzi[pezzi.length - 1] || percorso;
}

// ---------- Messaggi ----------

function messaggioLink(testo, errore = false) {
  const p = elemento("messaggio-link");
  p.textContent = testo;
  p.classList.toggle("errore", errore);
}

function messaggioPiede(testo, errore = false) {
  const p = elemento("piede-testo");
  p.textContent = testo;
  p.classList.toggle("errore", errore);
  p.classList.toggle("secondario", !errore);
}

function piedeIniziale() {
  messaggioPiede(`Il file andrà nella cartella ${nomeCartella(cartella)}.`);
}

// ---------- Primo avvio: componenti ----------

async function preparaComponenti() {
  const pulsante = elemento("pulsante-prepara");
  pulsante.disabled = true;
  pulsante.textContent = "Scarico i componenti...";
  elemento("traccia-preparazione").hidden = false;
  elemento("testo-preparazione").textContent = "";
  try {
    await invoke("installa_componenti");
    mostraPrincipale();
  } catch (errore) {
    elemento("testo-preparazione").textContent = errore;
    pulsante.disabled = false;
    pulsante.textContent = "Riprova";
  }
}

const nomiComponenti = { "yt-dlp": "yt-dlp", ffmpeg: "FFmpeg", deno: "Deno" };

listen("componenti", (evento) => {
  const percentuale = evento.payload.percentuale;
  const nome = nomiComponenti[evento.payload.nome] || evento.payload.nome;
  elemento("barra-preparazione").style.width = percentuale + "%";
  elemento("testo-preparazione").textContent = `Scarico ${nome}: ${Math.round(percentuale)}%`;
});

// ---------- Analisi del link ----------

async function analizza() {
  const link = elemento("link").value.trim();
  if (occupato) return;
  if (link === "") {
    messaggioLink("Incolla prima il link di un video.", true);
    return;
  }

  occupato = true;
  aggiornaPulsanti();
  messaggioLink("Leggo le informazioni del video...");

  try {
    video = await invoke("analizza", { url: link });
    mostraVideo();
    messaggioLink("");
    piedeIniziale();
  } catch (errore) {
    video = null;
    mostraVideo();
    messaggioLink(errore, true);
  }
  occupato = false;
  aggiornaPulsanti();
}

function mostraVideo() {
  const copertina = elemento("copertina");
  if (video === null) {
    elemento("titolo").textContent = "Nessun video";
    elemento("dettagli").textContent =
      "Incolla un link e premi Analizza: qui vedrai titolo, durata e qualità disponibili.";
    copertina.hidden = true;
    riempiQualita();
    return;
  }

  elemento("titolo").textContent = video.titolo;
  const righe = [];
  if (video.canale) righe.push(video.canale);
  const seconda = [];
  if (video.durata != null) seconda.push(formattaDurata(video.durata));
  if (video.visualizzazioni != null) seconda.push(`${formattaNumero(video.visualizzazioni)} visualizzazioni`);
  if (seconda.length > 0) righe.push(seconda.join(", "));
  elemento("dettagli").innerText = righe.join("\n");

  copertina.src = video.copertina;
  copertina.hidden = false;
  copertina.onerror = () => (copertina.hidden = true);
  riempiQualita();
}

// Riempie il menu "Qualità" in base a Video o Audio
function riempiQualita() {
  const menu = elemento("qualita");
  menu.innerHTML = "";

  if (video === null) {
    menu.add(new Option("Analizza prima un link", ""));
    return;
  }

  if (modalita === "audio") {
    for (const q of qualitaAudio) {
      let testo = q.nome;
      if (video.durata) testo += `, circa ${formattaByte((q.kbps * 1000 * video.durata) / 8)}`;
      menu.add(new Option(testo, q.kbps));
    }
    menu.value = "192";
  } else {
    for (const q of video.qualita) {
      let testo = nomeQualita(q.altezza);
      if (q.dimensione) testo += `, circa ${formattaByte(q.dimensione)}`;
      menu.add(new Option(testo, q.altezza));
    }
    // Di base 1080p (o la piu' alta sotto 1080p)
    const scelta = video.qualita.find((q) => q.altezza <= 1080) || video.qualita[0];
    if (scelta) menu.value = String(scelta.altezza);
  }
}

// ---------- Video / Audio ----------

function scegliModalita(nuova) {
  if (occupato) return;
  modalita = nuova;
  for (const pulsante of document.querySelectorAll(".segmenti button")) {
    pulsante.setAttribute("aria-checked", pulsante.dataset.modalita === nuova ? "true" : "false");
  }
  riempiQualita();
  aggiornaPulsanti();
}

// ---------- Cartella ----------

async function cambiaCartella() {
  if (occupato) return;
  const scelta = await invoke("scegli_cartella", { attuale: cartella });
  if (scelta) {
    cartella = scelta;
    mostraCartella();
    piedeIniziale();
  }
}

function mostraCartella() {
  elemento("nome-cartella").textContent = nomeCartella(cartella);
  elemento("pulsante-cartella").title = cartella;
}

// ---------- Download ----------

async function scarica() {
  if (occupato || video === null) return;

  occupato = true;
  ultimoFile = null;
  elemento("zona-avanzamento").hidden = false;
  aggiornaPulsanti();
  elemento("barra").style.width = "0%";
  elemento("testo-stato").textContent = "Avvio il download...";
  elemento("dettagli-avanzamento").textContent = "";
  messaggioPiede(`Il file andrà nella cartella ${nomeCartella(cartella)}.`);

  try {
    ultimoFile = await invoke("scarica", {
      url: video.url,
      titolo: video.titolo,
      modalita: modalita,
      qualita: Number(elemento("qualita").value),
      cartella: cartella,
    });
    elemento("barra").style.width = "100%";
    elemento("testo-stato").textContent = "Scaricato";
    elemento("dettagli-avanzamento").textContent = "";
    mostraFileScaricato();
  } catch (errore) {
    elemento("zona-avanzamento").hidden = true;
    if (errore === "annullato") {
      messaggioPiede("Download annullato. I file a metà sono stati cancellati.");
    } else {
      messaggioPiede(errore, true);
    }
  }
  occupato = false;
  aggiornaPulsanti();
}

function mostraFileScaricato() {
  const p = elemento("piede-testo");
  const nome = nomeCartella(ultimoFile);
  p.classList.remove("errore");
  p.classList.add("secondario");
  p.textContent = `${nome} `;
  const link = document.createElement("button");
  link.className = "link";
  link.textContent = nomeEsplora;
  link.onclick = () => invoke("mostra_file", { percorso: ultimoFile });
  p.appendChild(link);
}

listen("progresso", (evento) => {
  const p = evento.payload;
  elemento("barra").style.width = p.percentuale + "%";

  let cosa = "Scarico il file";
  if (p.parte === "video") cosa = "Scarico il video";
  if (p.parte === "audio") cosa = modalita === "audio" ? "Scarico l'audio" : "Scarico l'audio del video";
  elemento("testo-stato").textContent = `${cosa}, ${Math.round(p.percentuale)}%`;

  const dettagli = [];
  if (p.totale) dettagli.push(`${formattaByte(p.scaricati)} di ${formattaByte(p.totale)}`);
  if (p.velocita) dettagli.push(`${formattaByte(p.velocita)}/s`);
  if (p.rimasto != null) dettagli.push(`ancora ${formattaDurata(p.rimasto)}`);
  elemento("dettagli-avanzamento").textContent = dettagli.join(", ");
});

listen("conversione", (evento) => {
  elemento("testo-stato").textContent = evento.payload;
  elemento("dettagli-avanzamento").textContent = "";
});

function annulla() {
  invoke("annulla");
  elemento("pulsante-annulla").disabled = true;
  elemento("testo-stato").textContent = "Annullo...";
}

// ---------- Pulsanti attivi o no ----------

function aggiornaPulsanti() {
  elemento("pulsante-scarica").textContent = modalita === "audio" ? "Scarica audio" : "Scarica video";
  elemento("pulsante-scarica").disabled = occupato || video === null;
  elemento("pulsante-analizza").disabled = occupato;
  elemento("link").disabled = occupato;
  elemento("qualita").disabled = occupato || video === null;
  elemento("pulsante-cartella").disabled = occupato;
  elemento("pulsante-cerca").disabled = occupato;
  for (const pulsante of document.querySelectorAll(".segmenti button")) {
    pulsante.disabled = occupato;
  }
  const scaricando = occupato && !elemento("zona-avanzamento").hidden;
  elemento("pulsante-annulla").hidden = !scaricando;
  elemento("pulsante-annulla").disabled = false;
}

// ---------- Aggiornamenti dell'app ----------

let versioneAttuale = "";
let versioneNuova = null; // es. "2.0.1" se c'e' un aggiornamento

// Scrive la riga "Versione" (testo + pulsante a destra)
function mostraVersione(testo, testoPulsante) {
  elemento("testo-versione").textContent = testo;
  const pulsante = elemento("pulsante-cerca");
  pulsante.hidden = testoPulsante === "";
  pulsante.textContent = testoPulsante;
}

// silenzioso = true all'avvio: se non c'e' niente di nuovo non lo dice
async function controllaAggiornamento(silenzioso) {
  mostraVersione(versioneAttuale, "Controllo...");
  elemento("pulsante-cerca").disabled = true;
  try {
    const nuova = await invoke("controlla_aggiornamento");
    if (nuova) {
      versioneNuova = nuova.versione;
      mostraVersione(`${versioneAttuale}, è disponibile la ${nuova.versione}`, "Aggiorna");
      elemento("testo-aggiornamento").textContent =
        `È disponibile la versione ${nuova.versione} (hai la ${versioneAttuale}).`;
      elemento("barra-aggiornamento").hidden = false;
    } else {
      versioneNuova = null;
      mostraVersione(silenzioso ? versioneAttuale : `${versioneAttuale}, è l'ultima`, "Cerca aggiornamenti");
    }
  } catch (errore) {
    // Senza Internet all'avvio non diciamo niente
    if (silenzioso) {
      mostraVersione(versioneAttuale, "Cerca aggiornamenti");
    } else {
      mostraVersione(`${versioneAttuale}, controllo non riuscito`, "Riprova");
    }
  }
  elemento("pulsante-cerca").disabled = occupato;
}

// Il pulsante nella riga "Versione"
function clicVersione() {
  if (occupato) return;
  if (versioneNuova) {
    installaAggiornamento();
  } else {
    controllaAggiornamento(false);
  }
}

async function installaAggiornamento() {
  if (occupato) return;
  occupato = true;
  elemento("barra-aggiornamento").hidden = true;
  elemento("zona-avanzamento").hidden = false;
  aggiornaPulsanti();
  elemento("pulsante-annulla").hidden = true; // l'aggiornamento non si annulla
  elemento("barra").style.width = "0%";
  elemento("testo-stato").textContent = "Scarico l'aggiornamento...";
  elemento("dettagli-avanzamento").textContent = `versione ${versioneNuova}`;
  mostraVersione(`${versioneAttuale}, aggiorno alla ${versioneNuova}`, "");

  try {
    await invoke("installa_aggiornamento"); // alla fine l'app si riavvia da sola
  } catch (errore) {
    elemento("zona-avanzamento").hidden = true;
    messaggioPiede(errore, true);
    occupato = false;
    aggiornaPulsanti();
    mostraVersione(`${versioneAttuale}, aggiornamento non riuscito`, "Aggiorna");
  }
}

listen("aggiornamento", (evento) => {
  const percentuale = evento.payload;
  elemento("barra").style.width = percentuale + "%";
  elemento("testo-stato").textContent = `Scarico l'aggiornamento, ${Math.round(percentuale)}%`;
});

listen("aggiornamento-installo", () => {
  elemento("barra").style.width = "100%";
  elemento("testo-stato").textContent = "Installo l'aggiornamento: l'app si riavvia da sola...";
});

// ---------- Avvio ----------

function mostraPrincipale() {
  elemento("preparazione").hidden = true;
  elemento("principale").hidden = false;
  elemento("link").focus();
  invoke("aggiorna_ytdlp"); // in sottofondo
}

async function avvio() {
  versioneAttuale = await invoke("versione_app");
  mostraVersione(versioneAttuale, "Cerca aggiornamenti");
  cartella = await invoke("cartella_download");
  mostraCartella();
  piedeIniziale();
  mostraVideo();
  aggiornaPulsanti();

  // Collego i pulsanti alle funzioni
  elemento("modulo-link").addEventListener("submit", (e) => {
    e.preventDefault();
    analizza();
  });
  // Se incolli un link nel campo vuoto, lo analizzo subito
  elemento("link").addEventListener("paste", () => {
    const eraVuoto = elemento("link").value.trim() === "";
    setTimeout(() => {
      if (eraVuoto && elemento("link").value.includes("youtu")) analizza();
    }, 50);
  });
  for (const pulsante of document.querySelectorAll(".segmenti button")) {
    pulsante.addEventListener("click", () => scegliModalita(pulsante.dataset.modalita));
  }
  elemento("pulsante-cartella").addEventListener("click", cambiaCartella);
  elemento("pulsante-scarica").addEventListener("click", scarica);
  elemento("pulsante-annulla").addEventListener("click", annulla);
  elemento("pulsante-prepara").addEventListener("click", preparaComponenti);
  elemento("pulsante-aggiorna").addEventListener("click", installaAggiornamento);
  elemento("pulsante-cerca").addEventListener("click", clicVersione);

  const mancanti = await invoke("componenti_mancanti");
  if (mancanti.length > 0) {
    elemento("preparazione").hidden = false;
  } else {
    mostraPrincipale();
  }

  controllaAggiornamento(true);
}

avvio();
