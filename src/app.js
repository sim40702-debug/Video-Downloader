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
let analizzando = false;       // true mentre legge un link
let aggiornando = false;       // true mentre installa un aggiornamento

// La coda dei download
let coda = [];                 // elenco delle voci (vedi aggiungiAllaCoda)
let voceCorrente = null;       // la voce che sta scaricando adesso
let codaAttiva = false;        // true finche' ci sono download da fare
let prossimoNumero = 1;        // per dare un numero unico a ogni voce

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
  messaggioPiede(`I file andranno nella cartella ${nomeCartella(cartella)}.`);
}

// ---------- Impostazioni ricordate ----------
// Restano salvate anche quando chiudi l'app (localStorage)

function salvaImpostazione(nome, valore) {
  try {
    localStorage.setItem(nome, valore);
  } catch (errore) {
    // se non si puo' salvare, pazienza: l'app funziona lo stesso
  }
}

function leggiImpostazione(nome) {
  try {
    return localStorage.getItem(nome);
  } catch (errore) {
    return null;
  }
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
  if (analizzando || aggiornando) return;
  if (link === "") {
    messaggioLink("Incolla prima il link di un video.", true);
    return;
  }

  analizzando = true;
  aggiornaPulsanti();
  messaggioLink("Leggo le informazioni del video...");

  try {
    video = await invoke("analizza", { url: link });
    mostraVideo();
    messaggioLink("");
  } catch (errore) {
    video = null;
    mostraVideo();
    messaggioLink(errore, true);
  }
  analizzando = false;
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
  if (aggiornando) return;
  modalita = nuova;
  salvaImpostazione("modalita", nuova);
  for (const pulsante of document.querySelectorAll(".segmenti button")) {
    pulsante.setAttribute("aria-checked", pulsante.dataset.modalita === nuova ? "true" : "false");
  }
  riempiQualita();
  aggiornaPulsanti();
}

// ---------- Cartella ----------

async function cambiaCartella() {
  if (aggiornando) return;
  const scelta = await invoke("scegli_cartella", { attuale: cartella });
  if (scelta) {
    cartella = scelta;
    salvaImpostazione("cartella", scelta);
    mostraCartella();
    piedeIniziale();
  }
}

function mostraCartella() {
  elemento("nome-cartella").textContent = nomeCartella(cartella);
  elemento("pulsante-cartella").title = cartella;
}

// ---------- Coda dei download ----------

// Mette un download nella coda e, se non sta gia' scaricando, parte
function aggiungiAllaCoda(dati) {
  const giaPresente = coda.find(
    (v) => v.url === dati.url && v.modalita === dati.modalita &&
      (v.stato === "attesa" || v.stato === "analisi" || v.stato === "download")
  );
  if (giaPresente) {
    messaggioLink("Questo video è già nell'elenco dei download.", true);
    return false;
  }

  const voce = {
    id: prossimoNumero,
    url: dati.url,
    titolo: dati.titolo,
    copertina: dati.copertina || "",
    analizzato: dati.analizzato,
    modalita: dati.modalita,
    qualita: dati.qualita,
    cartella: cartella,
    stato: "attesa",        // attesa, analisi, download, fatto, errore, annullato
    testo: "In coda",
    percentuale: 0,
    file: null,
    annullata: false,
  };
  prossimoNumero++;
  coda.push(voce);
  creaVoce(voce);
  avviaCoda();
  return true;
}

// Prende le voci "in coda" una alla volta e le scarica
async function avviaCoda() {
  if (codaAttiva) return;
  codaAttiva = true;
  aggiornaPulsanti();

  let voce = coda.find((v) => v.stato === "attesa");
  while (voce) {
    await scaricaVoce(voce);
    voce = coda.find((v) => v.stato === "attesa");
  }

  codaAttiva = false;
  aggiornaPulsanti();
}

async function scaricaVoce(voce) {
  voceCorrente = voce;
  try {
    // I link incollati in gruppo non sono ancora stati analizzati
    if (!voce.analizzato) {
      cambiaStato(voce, "analisi", "Leggo le informazioni...");
      const info = await invoke("analizza", { url: voce.url });
      voce.url = info.url;
      voce.titolo = info.titolo;
      voce.copertina = info.copertina;
      voce.analizzato = true;
      mostraCopertinaVoce(voce);
    }
    if (voce.annullata) throw "annullato";

    cambiaStato(voce, "download", "Avvio il download...");
    voce.elementi.riga.scrollIntoView({ block: "nearest" }); // resta in vista
    voce.file = await invoke("scarica", {
      url: voce.url,
      titolo: voce.titolo,
      modalita: voce.modalita,
      qualita: voce.qualita,
      cartella: voce.cartella,
    });
    voce.percentuale = 100;
    cambiaStato(voce, "fatto", `Scaricato in ${nomeCartella(voce.cartella)}`);
    avvisaSeInSottofondo("Scaricato", voce.titolo);
  } catch (errore) {
    if (errore === "annullato" || voce.annullata) {
      cambiaStato(voce, "annullato", "Annullato");
    } else {
      cambiaStato(voce, "errore", errore);
      avvisaSeInSottofondo("Download non riuscito", voce.titolo);
    }
  }
  voceCorrente = null;
}

// Notifica del sistema, solo se stai usando un'altra app
function avvisaSeInSottofondo(titolo, testo) {
  if (!document.hasFocus()) {
    invoke("notifica", { titolo: titolo, testo: testo });
  }
}

// Il pulsante tondo a destra di ogni voce
function clicPulsanteVoce(voce) {
  if (voce.stato === "fatto") {
    invoke("mostra_file", { percorso: voce.file });
  } else if (voce.stato === "attesa") {
    togliVoce(voce);
  } else if (voce.stato === "analisi" || voce.stato === "download") {
    voce.annullata = true;
    voce.elementi.pulsante.disabled = true;
    cambiaStato(voce, voce.stato, "Annullo...");
    if (voce.stato === "download") invoke("annulla");
  } else {
    togliVoce(voce); // errore o annullato
  }
}

function togliVoce(voce) {
  coda = coda.filter((v) => v !== voce);
  voce.elementi.riga.remove();
  aggiornaElenco();
}

function togliCompletati() {
  for (const voce of [...coda]) {
    if (voce.stato === "fatto" || voce.stato === "errore" || voce.stato === "annullato") {
      togliVoce(voce);
    }
  }
}

// ---------- Disegno dell'elenco ----------

const iconaFerma =
  '<svg width="8" height="8" viewBox="0 0 8 8" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><path d="M1 1l6 6M7 1L1 7"/></svg>';
const iconaMostra =
  '<svg width="11" height="11" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><circle cx="5" cy="5" r="3.6"/><path d="M7.7 7.7L11 11"/></svg>';

// Crea la riga di una voce nell'elenco
function creaVoce(voce) {
  const riga = document.createElement("li");
  riga.className = "voce";

  const mini = document.createElement("img");
  mini.className = "mini";
  mini.alt = "";

  const testi = document.createElement("div");
  testi.className = "testi-voce";
  const titolo = document.createElement("div");
  titolo.className = "titolo-voce";
  const traccia = document.createElement("div");
  traccia.className = "traccia";
  const barra = document.createElement("i");
  traccia.appendChild(barra);
  const stato = document.createElement("div");
  stato.className = "stato-voce";
  testi.append(titolo, traccia, stato);

  const pulsante = document.createElement("button");
  pulsante.type = "button";
  pulsante.className = "tondo";
  pulsante.addEventListener("click", () => clicPulsanteVoce(voce));

  riga.append(mini, testi, pulsante);
  elemento("elenco-coda").appendChild(riga);

  voce.elementi = { riga, mini, titolo, traccia, barra, stato, pulsante };
  mostraCopertinaVoce(voce);
  disegnaVoce(voce);
  aggiornaElenco();
}

// Immagine trasparente: si vede il riquadro grigio finche' non c'e' la copertina
const immagineVuota = "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7";

function mostraCopertinaVoce(voce) {
  const mini = voce.elementi.mini;
  mini.src = immagineVuota;
  if (voce.copertina) {
    mini.src = voce.copertina;
    mini.style.visibility = "visible";
    mini.onerror = () => (mini.style.visibility = "hidden");
  }
  voce.elementi.titolo.textContent = voce.titolo;
}

function cambiaStato(voce, stato, testo) {
  voce.stato = stato;
  voce.testo = testo;
  disegnaVoce(voce);
  aggiornaElenco();
}

// Aggiorna testi, barra e pulsante di una voce
function disegnaVoce(voce) {
  const e = voce.elementi;
  e.titolo.textContent = voce.titolo;
  e.stato.textContent = voce.testo;
  e.stato.classList.toggle("errore", voce.stato === "errore");
  e.traccia.hidden = voce.stato !== "download";
  e.barra.style.width = voce.percentuale + "%";

  if (voce.stato === "fatto") {
    e.pulsante.innerHTML = iconaMostra;
    e.pulsante.title = nomeEsplora;
    e.pulsante.disabled = false;
  } else {
    e.pulsante.innerHTML = iconaFerma;
    if (voce.stato === "attesa") e.pulsante.title = "Togli dall'elenco";
    else if (voce.stato === "errore" || voce.stato === "annullato") e.pulsante.title = "Togli dall'elenco";
    else e.pulsante.title = "Ferma";
    if (voce.stato !== "analisi" && voce.stato !== "download") e.pulsante.disabled = false;
  }
}

// Mostra o nasconde l'elenco e il link "Togli i completati"
function aggiornaElenco() {
  elemento("coda").hidden = coda.length === 0;
  const finiti = coda.some((v) => v.stato === "fatto" || v.stato === "errore" || v.stato === "annullato");
  elemento("pulsante-pulisci").hidden = !finiti;
}

listen("progresso", (evento) => {
  const voce = voceCorrente;
  if (voce === null || voce.annullata) return;
  const p = evento.payload;
  voce.percentuale = p.percentuale;

  let cosa = "Scarico il file";
  if (p.parte === "video") cosa = "Scarico il video";
  if (p.parte === "audio") cosa = voce.modalita === "audio" ? "Scarico l'audio" : "Scarico l'audio del video";

  const pezzi = [`${cosa}, ${Math.round(p.percentuale)}%`];
  if (p.totale) pezzi.push(`${formattaByte(p.scaricati)} di ${formattaByte(p.totale)}`);
  if (p.velocita) pezzi.push(`${formattaByte(p.velocita)}/s`);
  if (p.rimasto != null) pezzi.push(`ancora ${formattaDurata(p.rimasto)}`);
  cambiaStato(voce, "download", pezzi.join(", "));
});

listen("conversione", (evento) => {
  const voce = voceCorrente;
  if (voce === null || voce.annullata) return;
  voce.percentuale = 100;
  cambiaStato(voce, "download", evento.payload);
});

// ---------- Pulsante principale ----------

function scarica() {
  if (video === null || aggiornando) return;
  const aggiunto = aggiungiAllaCoda({
    url: video.url,
    titolo: video.titolo,
    copertina: video.copertina,
    analizzato: true,
    modalita: modalita,
    qualita: Number(elemento("qualita").value),
  });
  if (aggiunto) {
    // Pronto per il prossimo link
    video = null;
    mostraVideo();
    elemento("link").value = "";
    messaggioLink("");
    elemento("link").focus();
    aggiornaPulsanti();
  }
}

// Se incolli piu' link insieme, li mette tutti nella coda
function linkNelTesto(testo) {
  const trovati = testo.match(/(https?:\/\/)?(www\.|m\.|music\.)?(youtube\.com|youtu\.be)\/[^\s,;]+/g);
  return trovati || [];
}

function incollaPiuLink(link) {
  // Senza analisi non conosciamo le qualita': usiamo la scelta attuale o quella consigliata
  let qualita = Number(elemento("qualita").value);
  if (!qualita) qualita = modalita === "audio" ? 192 : 1080;
  let aggiunti = 0;
  for (const url of link) {
    const ok = aggiungiAllaCoda({
      url: url,
      titolo: url.replace(/^https?:\/\/(www\.)?/, ""), // finche' non sappiamo il titolo vero
      analizzato: false,
      modalita: modalita,
      qualita: qualita,
    });
    if (ok) aggiunti++;
  }
  const cosa = modalita === "audio" ? "MP3" : "video";
  messaggioLink(`Aggiunti ${aggiunti} link all'elenco dei download (${cosa}).`);
}

// ---------- Pulsanti attivi o no ----------

function aggiornaPulsanti() {
  const scarica = elemento("pulsante-scarica");
  if (codaAttiva) {
    scarica.textContent = "Aggiungi ai download";
  } else {
    scarica.textContent = modalita === "audio" ? "Scarica audio" : "Scarica video";
  }
  scarica.disabled = aggiornando || analizzando || video === null;

  elemento("pulsante-analizza").disabled = analizzando || aggiornando;
  elemento("link").disabled = analizzando || aggiornando;
  elemento("qualita").disabled = aggiornando || video === null;
  elemento("pulsante-cartella").disabled = aggiornando;
  elemento("pulsante-cerca").disabled = aggiornando;
  for (const pulsante of document.querySelectorAll(".segmenti button")) {
    pulsante.disabled = aggiornando;
  }
}

// ---------- Aggiornamenti dell'app ----------

let versioneAttuale = "";
let versioneNuova = null; // es. "0.1.1" se c'e' un aggiornamento

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
  elemento("pulsante-cerca").disabled = aggiornando;
}

// Il pulsante nella riga "Versione"
function clicVersione() {
  if (aggiornando) return;
  if (versioneNuova) {
    installaAggiornamento();
  } else {
    controllaAggiornamento(false);
  }
}

async function installaAggiornamento() {
  if (aggiornando) return;
  if (codaAttiva) {
    messaggioPiede("Aspetta che finiscano i download, poi aggiorna l'app.", true);
    return;
  }
  aggiornando = true;
  aggiornaPulsanti();
  elemento("barra-aggiornamento").hidden = true;
  elemento("zona-avanzamento").hidden = false;
  elemento("barra").style.width = "0%";
  elemento("testo-stato").textContent = "Scarico l'aggiornamento...";
  elemento("dettagli-avanzamento").textContent = `versione ${versioneNuova}`;
  mostraVersione(`${versioneAttuale}, aggiorno alla ${versioneNuova}`, "");

  try {
    await invoke("installa_aggiornamento"); // alla fine l'app si riavvia da sola
  } catch (errore) {
    elemento("zona-avanzamento").hidden = true;
    messaggioPiede(errore, true);
    aggiornando = false;
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

  // La cartella dell'ultima volta, se esiste ancora; altrimenti Download
  const salvata = leggiImpostazione("cartella");
  if (salvata && (await invoke("esiste_cartella", { percorso: salvata }))) {
    cartella = salvata;
  } else {
    cartella = await invoke("cartella_download");
  }
  mostraCartella();
  piedeIniziale();

  // Video o Audio, come l'ultima volta
  if (leggiImpostazione("modalita") === "audio") scegliModalita("audio");

  mostraVideo();
  aggiornaPulsanti();

  // Collego i pulsanti alle funzioni
  elemento("modulo-link").addEventListener("submit", (e) => {
    e.preventDefault();
    analizza();
  });
  elemento("link").addEventListener("paste", (e) => {
    const testo = (e.clipboardData || window.clipboardData).getData("text");
    const link = linkNelTesto(testo);
    if (link.length > 1) {
      // Piu' link insieme: vanno tutti nell'elenco dei download
      e.preventDefault();
      incollaPiuLink(link);
      return;
    }
    // Un solo link nel campo vuoto: lo analizzo subito
    const eraVuoto = elemento("link").value.trim() === "";
    setTimeout(() => {
      if (eraVuoto && link.length === 1) analizza();
    }, 50);
  });
  for (const pulsante of document.querySelectorAll(".segmenti button")) {
    pulsante.addEventListener("click", () => scegliModalita(pulsante.dataset.modalita));
  }
  elemento("pulsante-cartella").addEventListener("click", cambiaCartella);
  elemento("pulsante-scarica").addEventListener("click", scarica);
  elemento("pulsante-pulisci").addEventListener("click", togliCompletati);
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
