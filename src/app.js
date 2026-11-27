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
let imp = null;                // le impostazioni (finestra Impostazioni)
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

// Sopra il pulsante: quanti download ci sono, oppure dove vanno i file
function piedeIniziale() {
  const inCorso = coda.filter((v) => v.stato === "analisi" || v.stato === "download").length;
  const inCoda = coda.filter((v) => v.stato === "attesa").length;
  const inLista = contaLista();
  if (inCorso + inCoda + inLista > 0) {
    const pezzi = [];
    if (inCorso > 0) pezzi.push(`${inCorso} in download`);
    if (inCoda > 0) pezzi.push(`${inCoda} in coda`);
    if (inLista > 0) pezzi.push(`${inLista} in lista`);
    messaggioPiede(pezzi.join(", "));
  } else {
    messaggioPiede(`I file andranno nella cartella ${nomeCartella(cartella)}.`);
  }
}

// ---------- Impostazioni ----------
// Sono salvate dalla parte Rust (impostazioni.json) e condivise
// con la finestra Impostazioni.

async function salvaImpostazioni() {
  try {
    await invoke("salva_impostazioni", { impostazioni: imp });
  } catch (errore) {
    console.error(errore);
  }
}

function applicaTema() {
  document.documentElement.dataset.tema = imp.tema;
}

// Nome del file secondo Impostazioni > Download > Nome del file
function nomeFile(voce) {
  if (imp.nome_file === "canale-titolo" && voce.canale) return `${voce.canale} - ${voce.titolo}`;
  if (imp.nome_file === "data-titolo" && voce.data) return `${voce.data} - ${voce.titolo}`;
  return voce.titolo;
}

// Mette nel pannello a destra i valori delle impostazioni
function mostraImpostazioniPannello() {
  elemento("nome-file").value = imp.nome_file;
  elemento("notifiche").checked = imp.notifiche;
  elemento("aggiorna-ytdlp").checked = imp.aggiorna_ytdlp;
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
    copertina.hidden = true;
    elemento("anteprima-vuota").hidden = false;
    elemento("titolo").hidden = true;
    elemento("dettagli").hidden = true;
    elemento("chip-qualita").hidden = true;
    elemento("chip-canale").hidden = true;
    elemento("chip-durata").hidden = true;
    riempiQualita();
    return;
  }

  elemento("anteprima-vuota").hidden = true;
  copertina.src = video.copertina;
  copertina.hidden = false;
  copertina.onerror = () => (copertina.hidden = true);

  elemento("titolo").textContent = video.titolo;
  elemento("titolo").hidden = false;

  // Sotto il titolo: visualizzazioni e data
  const pezzi = [];
  if (video.visualizzazioni != null) pezzi.push(`${formattaNumero(video.visualizzazioni)} visualizzazioni`);
  if (video.data) pezzi.push(`pubblicato il ${dataLeggibile(video.data)}`);
  elemento("dettagli").textContent = pezzi.join(", ");
  elemento("dettagli").hidden = pezzi.length === 0;

  // Etichette sopra l'immagine
  mostraEtichetta("chip-qualita", qualitaMassima());
  mostraEtichetta("chip-durata", durataCorta(video.durata));
  const canale = elemento("chip-canale");
  canale.hidden = !video.canale;
  canale.innerHTML = '<i class="chip-pallino"></i>';
  canale.append(video.canale || "");

  riempiQualita();
}

function mostraEtichetta(id, testo) {
  elemento(id).textContent = testo;
  elemento(id).hidden = !testo;
}

// "Fino a 4K" in base alla qualita' piu' alta del video
function qualitaMassima() {
  if (!video.qualita || video.qualita.length === 0) return "";
  const altezza = Math.max(...video.qualita.map((q) => q.altezza));
  const nomi = { 2160: "4K", 1440: "2K", 1080: "Full HD", 720: "HD" };
  return "Fino a " + (nomi[altezza] || altezza + "p");
}

// 212 -> "3:32"   3725 -> "1:02:05"
function durataCorta(secondi) {
  if (secondi == null) return "";
  secondi = Math.round(secondi);
  const ore = Math.floor(secondi / 3600);
  const minuti = Math.floor((secondi % 3600) / 60);
  const resto = String(secondi % 60).padStart(2, "0");
  if (ore > 0) return `${ore}:${String(minuti).padStart(2, "0")}:${resto}`;
  return `${minuti}:${resto}`;
}

// "2026-11-15" -> "15 novembre 2026"
function dataLeggibile(testo) {
  const mesi = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
    "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre"];
  const pezzi = testo.split("-");
  if (pezzi.length !== 3) return testo;
  return `${Number(pezzi[2])} ${mesi[Number(pezzi[1]) - 1]} ${pezzi[0]}`;
}

// Riempie il menu "Qualità" in base a Video o Audio
function riempiQualita() {
  const menu = elemento("qualita");
  menu.innerHTML = "";

  // Senza video analizzato: qualita' generiche, valgono per la lista
  if (video === null) {
    if (modalita === "audio") {
      for (const q of qualitaAudio) menu.add(new Option(q.nome, q.kbps));
      menu.value = String(imp.qualita_audio);
    } else {
      for (const altezza of [2160, 1440, 1080, 720, 480]) {
        menu.add(new Option("Fino a " + nomeQualita(altezza), altezza));
      }
      menu.value = String(imp.qualita_video);
    }
    mostraDimensione();
    return;
  }

  if (modalita === "audio") {
    for (const q of qualitaAudio) {
      menu.add(new Option(q.nome, q.kbps));
    }
    menu.value = String(imp.qualita_audio);
  } else {
    for (const q of video.qualita) {
      menu.add(new Option(nomeQualita(q.altezza), q.altezza));
    }
    // Di base la qualita' delle Impostazioni (o la migliore piu' bassa)
    const scelta =
      video.qualita.find((q) => q.altezza <= imp.qualita_video) || video.qualita[video.qualita.length - 1];
    if (scelta) menu.value = String(scelta.altezza);
  }
  mostraDimensione();
}

// Riga "Dimensione": quanto pesera' piu' o meno il file
function mostraDimensione() {
  let byte = 0;
  if (video !== null) {
    const scelta = Number(elemento("qualita").value);
    if (modalita === "audio") {
      if (video.durata) byte = (scelta * 1000 * video.durata) / 8;
    } else {
      const q = video.qualita.find((q) => q.altezza === scelta);
      if (q && q.dimensione) byte = q.dimensione;
    }
  }
  elemento("dimensione").textContent = byte ? `circa ${formattaByte(byte)}` : "-";
}

// ---------- Video / Audio ----------

function scegliModalita(nuova) {
  if (aggiornando) return;
  modalita = nuova;
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
    imp.cartella = scelta;
    salvaImpostazioni();
    mostraCartella();
    piedeIniziale();
  }
}

function mostraCartella() {
  elemento("nome-cartella").textContent = nomeCartella(cartella);
  elemento("nome-cartella").title = cartella;
}

// ---------- Coda dei download ----------

// Mette un download nella coda e, se non sta gia' scaricando, parte.
// Con subito = false va solo nella lista: parte quando premi "Scarica".
function aggiungiAllaCoda(dati, subito = true) {
  const giaPresente = coda.find(
    (v) => v.url === dati.url &&
      (v.stato === "lista" ||
        (v.modalita === dati.modalita && (v.stato === "attesa" || v.stato === "analisi" || v.stato === "download")))
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
    canale: dati.canale || "",
    data: dati.data || "",
    analizzato: dati.analizzato,
    modalita: dati.modalita,
    qualita: dati.qualita,
    cartella: cartella,
    stato: subito ? "attesa" : "lista", // lista, attesa, analisi, download, fatto, errore, annullato
    testo: subito ? "In coda" : "In lista",
    percentuale: 0,
    file: null,
    annullata: false,
  };
  prossimoNumero++;
  coda.push(voce);
  creaVoce(voce);
  if (subito) {
    avviaCoda();
  } else {
    leggiTitoli();
  }
  return true;
}

// ---------- Lista ----------
// Metti tanti link nella lista, poi scegli Video o Audio e premi Scarica:
// partono tutti, uno alla volta.

function contaLista() {
  return coda.filter((v) => v.stato === "lista").length;
}

// Pulsante "Aggiungi alla lista": il video analizzato o i link nel campo
function aggiungiAllaLista() {
  if (aggiornando) return;
  if (video !== null) {
    const ok = aggiungiAllaCoda({
      url: video.url,
      titolo: video.titolo,
      copertina: video.copertina,
      canale: video.canale,
      data: video.data || "",
      analizzato: true,
      modalita: modalita,
      qualita: 0,
    }, false);
    if (ok) {
      video = null;
      mostraVideo();
      elemento("link").value = "";
      messaggioLink("Aggiunto alla lista. Incolla il prossimo link.");
    }
  } else {
    const link = linkNelTesto(elemento("link").value);
    if (link.length === 0) {
      messaggioLink("Incolla prima il link di un video.", true);
      return;
    }
    incollaPiuLink(link);
    elemento("link").value = "";
  }
  elemento("link").focus();
  aggiornaPulsanti();
}

// Pulsante "Scarica" senza video analizzato: parte tutta la lista
function scaricaLista() {
  let qualita = Number(elemento("qualita").value);
  if (!qualita) qualita = modalita === "audio" ? imp.qualita_audio : imp.qualita_video;
  for (const voce of coda) {
    if (voce.stato === "lista") {
      voce.modalita = modalita;
      voce.qualita = qualita;
      voce.cartella = cartella;
      cambiaStato(voce, "attesa", "In coda");
    }
  }
  messaggioLink("");
  avviaCoda();
}

// In sottofondo legge titolo e copertina dei link nella lista, uno alla volta
let leggendoTitoli = false;

async function leggiTitoli() {
  if (leggendoTitoli) return;
  leggendoTitoli = true;
  let voce = coda.find((v) => v.stato === "lista" && !v.analizzato && !v.illeggibile);
  while (voce) {
    try {
      const info = await invoke("analizza", { url: voce.url });
      if (!voce.analizzato) {
        voce.url = info.url;
        voce.titolo = info.titolo;
        voce.copertina = info.copertina;
        voce.canale = info.canale;
        voce.data = info.data || "";
        voce.analizzato = true;
        mostraCopertinaVoce(voce);
      }
    } catch (errore) {
      voce.illeggibile = true; // ci riprova quando lo scarica
    }
    voce = coda.find((v) => v.stato === "lista" && !v.analizzato && !v.illeggibile);
  }
  leggendoTitoli = false;
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
      voce.canale = info.canale;
      voce.data = info.data || "";
      voce.analizzato = true;
      mostraCopertinaVoce(voce);
    }
    if (voce.annullata) throw "annullato";

    cambiaStato(voce, "download", "Avvio il download...");
    voce.elementi.riga.scrollIntoView({ block: "nearest" }); // resta in vista
    voce.file = await invoke("scarica", {
      url: voce.url,
      titolo: nomeFile(voce),
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
  if (imp.notifiche && !document.hasFocus()) {
    invoke("notifica", { titolo: titolo, testo: testo });
  }
}

// Il pulsante tondo a destra di ogni voce
function clicPulsanteVoce(voce) {
  if (voce.stato === "fatto") {
    invoke("mostra_file", { percorso: voce.file });
  } else if (voce.stato === "attesa" || voce.stato === "lista") {
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
    if (voce.stato === "lista") e.pulsante.title = "Togli dalla lista";
    else if (voce.stato === "attesa") e.pulsante.title = "Togli dall'elenco";
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

  // In alto: quanti download ci sono nell'elenco
  elemento("conteggio").textContent =
    coda.length === 0 ? "" : coda.length === 1 ? "1 download" : `${coda.length} download`;

  piedeIniziale();
  aggiornaPulsanti();
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
  if (aggiornando) return;
  if (video === null) {
    if (contaLista() > 0) scaricaLista();
    return;
  }
  const aggiunto = aggiungiAllaCoda({
    url: video.url,
    titolo: video.titolo,
    copertina: video.copertina,
    canale: video.canale,
    data: video.data || "",
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
  if (!qualita) qualita = modalita === "audio" ? imp.qualita_audio : imp.qualita_video;
  let aggiunti = 0;
  for (const url of link) {
    const ok = aggiungiAllaCoda({
      url: url,
      titolo: url.replace(/^https?:\/\/(www\.)?/, ""), // finche' non sappiamo il titolo vero
      analizzato: false,
      modalita: modalita,
      qualita: qualita,
    }, false);
    if (ok) aggiunti++;
  }
  if (aggiunti === 1) {
    messaggioLink("Aggiunto 1 link alla lista. Quando hai finito, scegli Video o Audio e premi Scarica.");
  } else if (aggiunti > 1) {
    messaggioLink(`Aggiunti ${aggiunti} link alla lista. Quando hai finito, scegli Video o Audio e premi Scarica.`);
  }
}

// ---------- Pulsanti attivi o no ----------

function aggiornaPulsanti() {
  const scarica = elemento("pulsante-scarica");
  const inLista = contaLista();
  const cosa = modalita === "audio" ? "audio" : "video";
  if (video === null && inLista > 0) {
    // Nessun video aperto: il pulsante scarica tutta la lista
    scarica.textContent = inLista === 1 ? `Scarica 1 ${cosa}` : `Scarica ${inLista} ${cosa}`;
  } else if (codaAttiva) {
    scarica.textContent = "Aggiungi ai download";
  } else {
    scarica.textContent = `Scarica ${cosa}`;
  }
  scarica.disabled = aggiornando || analizzando || (video === null && inLista === 0);
  elemento("pulsante-lista").disabled = aggiornando || analizzando;

  elemento("pulsante-analizza").disabled = analizzando || aggiornando;
  elemento("link").disabled = analizzando || aggiornando;
  elemento("qualita").disabled = aggiornando;
  elemento("nome-file").disabled = aggiornando;
  elemento("pulsante-cartella").disabled = aggiornando;
  for (const pulsante of document.querySelectorAll(".segmenti button")) {
    pulsante.disabled = aggiornando;
  }
}

// ---------- Aggiornamenti dell'app ----------

let versioneAttuale = "";
let versioneNuova = null; // es. "0.1.3" se c'e' un aggiornamento

// Chiede a GitHub se c'e' una versione nuova: se si', mostra l'avviso in alto
async function controllaAggiornamento() {
  try {
    const nuova = await invoke("controlla_aggiornamento");
    if (nuova) {
      versioneNuova = nuova.versione;
      elemento("testo-aggiornamento").textContent =
        `È disponibile la versione ${nuova.versione} (hai la ${versioneAttuale}).`;
      elemento("barra-aggiornamento").hidden = false;
    }
  } catch (errore) {
    // Senza Internet non diciamo niente: riproveremo al prossimo avvio
  }
}

async function installaAggiornamento() {
  if (aggiornando) return;
  if (codaAttiva) {
    messaggioPiede("Aspetta che finiscano i download, poi aggiorna l'app.", true);
    return;
  }
  if (versioneNuova === null) await controllaAggiornamento();
  if (versioneNuova === null) return;

  aggiornando = true;
  aggiornaPulsanti();
  elemento("barra-aggiornamento").hidden = true;
  elemento("zona-avanzamento").hidden = false;
  elemento("barra").style.width = "0%";
  elemento("testo-stato").textContent = "Scarico l'aggiornamento...";
  elemento("dettagli-avanzamento").textContent = `versione ${versioneNuova}`;

  try {
    await invoke("installa_aggiornamento"); // alla fine l'app si riavvia da sola
  } catch (errore) {
    elemento("zona-avanzamento").hidden = true;
    messaggioPiede(errore, true);
    aggiornando = false;
    aggiornaPulsanti();
    elemento("barra-aggiornamento").hidden = false;
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
  // In sottofondo: yt-dlp si aggiorna da solo (Impostazioni > Componenti)
  if (imp.aggiorna_ytdlp) invoke("aggiorna_ytdlp").catch(() => {});
}

function apriImpostazioni() {
  invoke("apri_impostazioni");
}

async function avvio() {
  versioneAttuale = await invoke("versione_app");
  imp = await invoke("leggi_impostazioni");
  applicaTema();
  mostraImpostazioniPannello();

  // Chi aveva gia' scelto una cartella con la versione 0.1.1 la ritrova
  let vecchiaCartella = null;
  try {
    vecchiaCartella = localStorage.getItem("cartella");
  } catch (errore) {}
  if (!imp.cartella && vecchiaCartella) {
    imp.cartella = vecchiaCartella;
    salvaImpostazioni();
  }

  // La cartella delle Impostazioni, se esiste ancora; altrimenti Download
  if (imp.cartella && (await invoke("esiste_cartella", { percorso: imp.cartella }))) {
    cartella = imp.cartella;
  } else {
    cartella = await invoke("cartella_download");
  }
  mostraCartella();
  piedeIniziale();

  // Video o Audio, come in Impostazioni > Quando apri l'app
  scegliModalita(imp.formato === "audio" ? "audio" : "video");

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
  elemento("qualita").addEventListener("change", mostraDimensione);
  elemento("nome-file").addEventListener("change", (e) => {
    imp.nome_file = e.target.value;
    salvaImpostazioni();
  });
  elemento("notifiche").addEventListener("change", (e) => {
    imp.notifiche = e.target.checked;
    salvaImpostazioni();
  });
  elemento("aggiorna-ytdlp").addEventListener("change", (e) => {
    imp.aggiorna_ytdlp = e.target.checked;
    salvaImpostazioni();
  });
  elemento("pulsante-scarica").addEventListener("click", scarica);
  elemento("pulsante-lista").addEventListener("click", aggiungiAllaLista);
  elemento("pulsante-pulisci").addEventListener("click", togliCompletati);
  elemento("pulsante-prepara").addEventListener("click", preparaComponenti);
  elemento("pulsante-aggiorna").addEventListener("click", installaAggiornamento);
  elemento("pulsante-impostazioni").addEventListener("click", apriImpostazioni);

  // Ctrl+, (Windows) apre le Impostazioni; sul Mac ⌘, lo fa il menu
  document.addEventListener("keydown", (e) => {
    if (e.ctrlKey && e.key === ",") apriImpostazioni();
  });

  // Quando cambi qualcosa nella finestra Impostazioni
  listen("impostazioni", async (evento) => {
    imp = evento.payload;
    applicaTema();
    mostraImpostazioniPannello();
    const nuova = imp.cartella || (await invoke("cartella_download"));
    if (nuova !== cartella) {
      cartella = nuova;
      mostraCartella();
      piedeIniziale();
    }
    if (video !== null) riempiQualita();
  });
  // "Aggiorna" premuto nella finestra Impostazioni
  listen("avvia-aggiornamento", () => installaAggiornamento());

  const mancanti = await invoke("componenti_mancanti");
  if (mancanti.length > 0) {
    elemento("preparazione").hidden = false;
  } else {
    mostraPrincipale();
  }

  if (imp.controlla_aggiornamenti) controllaAggiornamento();
}

avvio();
