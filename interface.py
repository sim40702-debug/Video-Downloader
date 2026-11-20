"""
interface.py
------------
La finestra dell'app, fatta con CustomTkinter.

Regola importante di Tkinter: la grafica si puo' modificare SOLO dal
thread principale. Per questo i thread che lavorano (analisi e download)
non toccano mai i widget: mettono dei messaggi in una "coda" e la
finestra li legge ogni 100 millisecondi (funzione _leggi_coda).
"""

import io
import os
import queue
import ssl
import subprocess
import threading
import urllib.request
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

import aggiornamenti as agg
import downloader as dl

try:
    from PIL import Image
except ImportError:  # senza Pillow l'app funziona lo stesso, solo senza copertina
    Image = None

try:
    import certifi
except ImportError:
    certifi = None


# ------------------------------------------------------------------
# Colori (ispirati al tema scuro di macOS)
# ------------------------------------------------------------------
SFONDO = "#1c1c1e"
CARD = "#2c2c2e"
CARD_BORDO = "#3a3a3c"
TESTO = "#f5f5f7"
TESTO_SPENTO = "#8e8e93"
ROSSO = "#ff3b30"
ROSSO_SCURO = "#d70015"
ROSSO_SPENTO = "#6e2420"
BLU = "#0a84ff"
BLU_SCURO = "#0060df"
VERDE = "#30d158"
ARANCIONE = "#ff9f0a"
GRIGIO_PULSANTE = "#3a3a3c"
GRIGIO_PULSANTE_HOVER = "#48484a"

ETICHETTE_AUDIO = {
    "320": "320 kbps (massima)",
    "256": "256 kbps",
    "192": "192 kbps (consigliata)",
    "128": "128 kbps (file piu' piccolo)",
}


class App(ctk.CTk):

    def __init__(self, controlla_aggiornamenti=True):
        super().__init__()

        ctk.set_appearance_mode("dark")

        self.title("Video Downloader")
        self.geometry("760x900")
        self.minsize(680, 820)
        self.configure(fg_color=SFONDO)

        # Stato dell'app
        self.downloader = dl.Downloader()
        self.coda = queue.Queue()
        self.info = None                 # informazioni del video analizzato
        self.cartella = Path.home() / "Downloads"
        self.ultimo_file = None
        self.occupato = False
        self.mappa_qualita = {}          # testo nel menu -> valore vero
        self.progresso_attuale = 0.0     # per l'animazione della barra
        self.progresso_obiettivo = 0.0
        self.pulsazione_accesa = False
        self.immagine_copertina = None
        self.aggiornamento = None        # versione nuova trovata su Gitea

        # Font
        self.font_titolo = ctk.CTkFont(size=22, weight="bold")
        self.font_sezione = ctk.CTkFont(size=13, weight="bold")
        self.font_normale = ctk.CTkFont(size=13)
        self.font_piccolo = ctk.CTkFont(size=12)
        self.font_info_titolo = ctk.CTkFont(size=15, weight="bold")
        self.font_grande = ctk.CTkFont(size=17, weight="bold")

        self._crea_header()
        self._crea_sezione_url()
        self._crea_sezione_anteprima()
        self._crea_sezione_formato()
        self._crea_sezione_cartella()
        self._crea_sezione_download()

        self._aggiorna_menu_qualita()
        self._controlla_programmi()

        self.bind("<Return>", lambda evento: self.analizza())
        self.protocol("WM_DELETE_WINDOW", self.chiudi)

        # Cicli che si ripetono: lettura della coda e animazione barra.
        # Salviamo gli id dei timer per fermarli quando la finestra si chiude.
        self.timer = {}
        self.timer["coda"] = self.after(100, self._leggi_coda)
        self.timer["barra"] = self.after(30, self._anima_barra)

        # Controllo degli aggiornamenti all'avvio, senza disturbare
        if controlla_aggiornamenti:
            self.timer["aggiornamenti"] = self.after(
                1500, lambda: self.controlla_aggiornamenti(silenzioso=True))

    # ==============================================================
    # COSTRUZIONE DELLA GRAFICA
    # ==============================================================

    def _card(self):
        """Crea un riquadro con angoli arrotondati."""
        card = ctk.CTkFrame(self, fg_color=CARD, corner_radius=14,
                            border_width=1, border_color=CARD_BORDO)
        card.pack(fill="x", padx=24, pady=(0, 14))
        return card

    def _crea_header(self):
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=24, pady=(22, 18))

        # Icona minimalista: quadrato rosso arrotondato con il "play"
        icona = ctk.CTkFrame(header, width=44, height=44, corner_radius=12,
                             fg_color=ROSSO)
        icona.pack(side="left")
        icona.pack_propagate(False)
        ctk.CTkLabel(icona, text="▶", text_color="white",
                     font=ctk.CTkFont(size=18)).place(relx=0.54, rely=0.5, anchor="center")

        testi = ctk.CTkFrame(header, fg_color="transparent")
        testi.pack(side="left", padx=14)
        ctk.CTkLabel(testi, text="Video Downloader", font=self.font_titolo,
                     text_color=TESTO).pack(anchor="w")
        ctk.CTkLabel(testi, text=f"Video MP4 e audio MP3  ·  v{agg.VERSIONE}",
                     font=self.font_piccolo,
                     text_color=TESTO_SPENTO).pack(anchor="w")

        # Indicatore di stato (pallino + testo)
        stato = ctk.CTkFrame(header, fg_color=CARD, corner_radius=14,
                             border_width=1, border_color=CARD_BORDO)
        stato.pack(side="right")
        self.pallino = ctk.CTkLabel(stato, text="●", text_color=VERDE,
                                    font=ctk.CTkFont(size=14))
        self.pallino.pack(side="left", padx=(12, 4), pady=6)
        self.testo_stato_app = ctk.CTkLabel(stato, text="Pronto",
                                            font=self.font_piccolo, text_color=TESTO)
        self.testo_stato_app.pack(side="left", padx=(0, 14), pady=6)

        # Pulsante aggiornamenti (diventa blu se c'e' una versione nuova)
        self.pulsante_aggiorna = ctk.CTkButton(
            header, text="Aggiornamenti", width=120, height=30, corner_radius=14,
            fg_color=GRIGIO_PULSANTE, hover_color=GRIGIO_PULSANTE_HOVER,
            font=self.font_piccolo, command=self.clic_aggiornamenti)
        self.pulsante_aggiorna.pack(side="right", padx=(0, 10))

    def _crea_sezione_url(self):
        card = self._card()
        ctk.CTkLabel(card, text="Link del video", font=self.font_sezione,
                     text_color=TESTO).pack(anchor="w", padx=18, pady=(14, 8))

        riga = ctk.CTkFrame(card, fg_color="transparent")
        riga.pack(fill="x", padx=18, pady=(0, 6))

        self.campo_url = ctk.CTkEntry(
            riga, height=40, corner_radius=10, font=self.font_normale,
            placeholder_text="Incolla qui il link di YouTube...",
            fg_color=SFONDO, border_color=CARD_BORDO, text_color=TESTO)
        self.campo_url.pack(side="left", fill="x", expand=True)

        self.pulsante_incolla = ctk.CTkButton(
            riga, text="Incolla", width=80, height=40, corner_radius=10,
            fg_color=GRIGIO_PULSANTE, hover_color=GRIGIO_PULSANTE_HOVER,
            font=self.font_normale, command=self.incolla)
        self.pulsante_incolla.pack(side="left", padx=(8, 0))

        self.pulsante_analizza = ctk.CTkButton(
            riga, text="Analizza URL", width=120, height=40, corner_radius=10,
            fg_color=BLU, hover_color=BLU_SCURO, font=self.font_sezione,
            command=self.analizza)
        self.pulsante_analizza.pack(side="left", padx=(8, 0))

        self.messaggio_url = ctk.CTkLabel(card, text="", font=self.font_piccolo,
                                          text_color=TESTO_SPENTO, anchor="w")
        self.messaggio_url.pack(fill="x", padx=18, pady=(0, 10))

    def _crea_sezione_anteprima(self):
        card = self._card()
        contenuto = ctk.CTkFrame(card, fg_color="transparent")
        contenuto.pack(fill="x", padx=14, pady=14)

        # Riquadro per la copertina (16:9)
        self.copertina = ctk.CTkLabel(contenuto, text="", width=176, height=99,
                                      fg_color=SFONDO, corner_radius=10)
        self.copertina.pack(side="left")

        testi = ctk.CTkFrame(contenuto, fg_color="transparent")
        testi.pack(side="left", fill="both", expand=True, padx=(14, 0))

        self.info_titolo = ctk.CTkLabel(
            testi, text="Nessun contenuto analizzato", font=self.font_info_titolo,
            text_color=TESTO, anchor="w", justify="left", wraplength=440)
        self.info_titolo.pack(fill="x", anchor="w")

        self.info_canale = ctk.CTkLabel(
            testi, text="Incolla un link e premi \"Analizza URL\"",
            font=self.font_normale, text_color=TESTO_SPENTO, anchor="w")
        self.info_canale.pack(fill="x", anchor="w", pady=(4, 0))

        self.info_dettagli = ctk.CTkLabel(testi, text="", font=self.font_piccolo,
                                          text_color=TESTO_SPENTO, anchor="w")
        self.info_dettagli.pack(fill="x", anchor="w", pady=(4, 0))

    def _crea_sezione_formato(self):
        card = self._card()
        riga = ctk.CTkFrame(card, fg_color="transparent")
        riga.pack(fill="x", padx=18, pady=16)

        colonna1 = ctk.CTkFrame(riga, fg_color="transparent")
        colonna1.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(colonna1, text="Formato", font=self.font_sezione,
                     text_color=TESTO).pack(anchor="w", pady=(0, 8))
        self.selettore_modalita = ctk.CTkSegmentedButton(
            colonna1, values=["VIDEO", "AUDIO"], height=36, corner_radius=10,
            font=self.font_sezione, selected_color=BLU, selected_hover_color=BLU_SCURO,
            unselected_color=SFONDO, unselected_hover_color=GRIGIO_PULSANTE,
            fg_color=SFONDO, command=lambda valore: self._aggiorna_menu_qualita())
        self.selettore_modalita.set("VIDEO")
        self.selettore_modalita.pack(anchor="w", fill="x", padx=(0, 16))

        colonna2 = ctk.CTkFrame(riga, fg_color="transparent")
        colonna2.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(colonna2, text="Qualita'", font=self.font_sezione,
                     text_color=TESTO).pack(anchor="w", pady=(0, 8))
        self.menu_qualita = ctk.CTkOptionMenu(
            colonna2, values=["—"], height=36, corner_radius=10,
            font=self.font_normale, fg_color=SFONDO, button_color=GRIGIO_PULSANTE,
            button_hover_color=GRIGIO_PULSANTE_HOVER, dropdown_font=self.font_normale,
            command=lambda valore: self._aggiorna_dimensione())
        self.menu_qualita.pack(anchor="w", fill="x")

        self.messaggio_formato = ctk.CTkLabel(card, text="", font=self.font_piccolo,
                                              text_color=TESTO_SPENTO, anchor="w",
                                              justify="left")
        self.messaggio_formato.pack(fill="x", padx=18, pady=(0, 12))

    def _crea_sezione_cartella(self):
        card = self._card()
        riga = ctk.CTkFrame(card, fg_color="transparent")
        riga.pack(fill="x", padx=18, pady=14)

        testi = ctk.CTkFrame(riga, fg_color="transparent")
        testi.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(testi, text="Salva in", font=self.font_sezione,
                     text_color=TESTO).pack(anchor="w")
        self.etichetta_cartella = ctk.CTkLabel(
            testi, text=self._percorso_corto(self.cartella), font=self.font_piccolo,
            text_color=TESTO_SPENTO, anchor="w")
        self.etichetta_cartella.pack(anchor="w", fill="x")

        self.pulsante_cartella = ctk.CTkButton(
            riga, text="Cambia cartella", width=140, height=36, corner_radius=10,
            fg_color=GRIGIO_PULSANTE, hover_color=GRIGIO_PULSANTE_HOVER,
            font=self.font_normale, command=self.cambia_cartella)
        self.pulsante_cartella.pack(side="right")

    def _crea_sezione_download(self):
        zona = ctk.CTkFrame(self, fg_color="transparent")
        zona.pack(fill="x", padx=24, pady=(4, 20))

        riga_pulsanti = ctk.CTkFrame(zona, fg_color="transparent")
        riga_pulsanti.pack(fill="x")

        self.pulsante_scarica = ctk.CTkButton(
            riga_pulsanti, text="SCARICA", height=54, corner_radius=14,
            fg_color=ROSSO, hover_color=ROSSO_SCURO, font=self.font_grande,
            text_color_disabled="#c7c7cc", command=self.scarica)
        self.pulsante_scarica.pack(side="left", fill="x", expand=True)

        self.pulsante_annulla = ctk.CTkButton(
            riga_pulsanti, text="Annulla", width=110, height=54, corner_radius=14,
            fg_color=GRIGIO_PULSANTE, hover_color=GRIGIO_PULSANTE_HOVER,
            font=self.font_sezione, state="disabled", command=self.annulla)
        self.pulsante_annulla.pack(side="left", padx=(10, 0))

        self.barra = ctk.CTkProgressBar(zona, height=10, corner_radius=5,
                                        progress_color=BLU, fg_color=CARD)
        self.barra.set(0)
        self.barra.pack(fill="x", pady=(18, 8))

        riga_numeri = ctk.CTkFrame(zona, fg_color="transparent")
        riga_numeri.pack(fill="x")
        self.testo_percentuale = ctk.CTkLabel(riga_numeri, text="0%",
                                              font=self.font_sezione, text_color=TESTO)
        self.testo_percentuale.pack(side="left")
        self.testo_velocita = ctk.CTkLabel(riga_numeri, text="", font=self.font_piccolo,
                                           text_color=TESTO_SPENTO)
        self.testo_velocita.pack(side="right")

        self.testo_stato = ctk.CTkLabel(zona, text="In attesa di un link.",
                                        font=self.font_normale, text_color=TESTO_SPENTO,
                                        anchor="w", justify="left", wraplength=700)
        self.testo_stato.pack(fill="x", pady=(6, 10))

        self.pulsante_apri = ctk.CTkButton(
            zona, text="Apri cartella nel Finder" if dl.SU_MAC else "Apri cartella",
            height=38, corner_radius=10,
            fg_color=GRIGIO_PULSANTE, hover_color=GRIGIO_PULSANTE_HOVER,
            font=self.font_normale, command=self.apri_cartella)
        self.pulsante_apri.pack(fill="x")

    # ==============================================================
    # AZIONI DEI PULSANTI
    # ==============================================================

    def incolla(self):
        """Incolla il testo copiato nel campo del link."""
        try:
            testo = self.clipboard_get().strip()
        except Exception:
            testo = ""
        if testo:
            self.campo_url.delete(0, "end")
            self.campo_url.insert(0, testo)
            self.messaggio_url.configure(text="", text_color=TESTO_SPENTO)

    def analizza(self):
        if self.occupato:
            return
        url = self.campo_url.get().strip()
        if not url:
            self._messaggio_url("Incolla prima un link di YouTube.", ARANCIONE)
            return
        if not dl.url_valido(url):
            self._messaggio_url("Il link non e' valido. Esempio: "
                                "https://www.youtube.com/watch?v=...", ROSSO)
            return

        self._messaggio_url("Analisi in corso...", TESTO_SPENTO)
        self._imposta_occupato(True, "Analisi...")
        self.info = None
        self._aggiorna_menu_qualita()

        thread = threading.Thread(target=self._lavoro_analisi, args=(url,), daemon=True)
        thread.start()

    def scarica(self):
        if self.occupato:
            return
        if self.info is None:
            # Se l'utente non ha premuto Analizza, lo facciamo noi
            self._messaggio_url("Prima premi \"Analizza URL\".", ARANCIONE)
            return

        errore = dl.controlla_cartella(self.cartella)
        if errore:
            messagebox.showerror("Cartella non valida", errore)
            return

        testo_qualita = self.menu_qualita.get()
        if testo_qualita not in self.mappa_qualita:
            messagebox.showerror("Qualita'", "Scegli una qualita' dal menu.")
            return

        modalita = self.selettore_modalita.get()
        qualita = self.mappa_qualita[testo_qualita]

        self.ultimo_file = None
        self.progresso_attuale = 0
        self.progresso_obiettivo = 0
        self.barra.set(0)
        self.barra.configure(progress_color=BLU)
        self.testo_percentuale.configure(text="0%")
        self.testo_velocita.configure(text="")
        self._imposta_occupato(True, "Download...")
        self.pulsante_annulla.configure(state="normal")
        self._stato_download("Preparazione...", TESTO)

        thread = threading.Thread(
            target=self._lavoro_download,
            args=(self.info, modalita, qualita, self.cartella),
            daemon=True)
        thread.start()

    def annulla(self):
        if self.occupato:
            self.downloader.annulla()
            self.pulsante_annulla.configure(state="disabled")
            self._stato_download("Annullamento in corso...", ARANCIONE)

    def cambia_cartella(self):
        nuova = filedialog.askdirectory(initialdir=str(self.cartella),
                                        title="Scegli dove salvare i file")
        if not nuova:
            return  # l'utente ha premuto Annulla
        errore = dl.controlla_cartella(nuova)
        if errore:
            messagebox.showerror("Cartella non valida", errore)
            return
        self.cartella = Path(nuova)
        self.etichetta_cartella.configure(text=self._percorso_corto(self.cartella))

    def apri_cartella(self):
        """
        Apre la cartella (Finder su Mac, Esplora file su Windows).
        Se c'e' un file appena scaricato, lo seleziona.
        """
        file = self.ultimo_file if self.ultimo_file and Path(self.ultimo_file).exists() else None
        try:
            if dl.SU_WINDOWS:
                if file:
                    subprocess.run(f'explorer /select,"{file}"', check=False)
                else:
                    os.startfile(str(self.cartella))
            elif dl.SU_MAC:
                if file:
                    subprocess.run(["open", "-R", str(file)], check=False)
                else:
                    subprocess.run(["open", str(self.cartella)], check=False)
            else:
                subprocess.run(["xdg-open", str(self.cartella)], check=False)
        except (FileNotFoundError, OSError):
            messagebox.showinfo("Cartella", f"I file sono in:\n{self.cartella}")

    def clic_aggiornamenti(self):
        if self.occupato:
            return
        if self.aggiornamento is None:
            self.controlla_aggiornamenti(silenzioso=False)
        else:
            self._chiedi_se_aggiornare()

    def controlla_aggiornamenti(self, silenzioso):
        """silenzioso=True: all'avvio, avvisa solo se c'e' una versione nuova."""
        if not silenzioso:
            self.pulsante_aggiorna.configure(text="Controllo...", state="disabled")
        thread = threading.Thread(target=self._lavoro_controllo, args=(silenzioso,),
                                  daemon=True)
        thread.start()

    def _chiedi_se_aggiornare(self):
        nuova = self.aggiornamento
        note = nuova["note"][:600] or "Nessuna nota."
        server = nuova["server"].replace("http://", "")
        domanda = (f"E' disponibile la versione {nuova['versione']} "
                   f"(tu hai la {agg.VERSIONE}).\n\nNovita':\n{note}\n\n"
                   f"Server usato: {server}\n\n"
                   "Vuoi aggiornare adesso?")
        if not messagebox.askyesno("Aggiornamento disponibile", domanda):
            return
        self._imposta_occupato(True, "Aggiornamento...")
        self.pulsante_aggiorna.configure(state="disabled")
        self.progresso_obiettivo = 0
        self.barra.configure(progress_color=BLU)
        self._stato_download(f"Scarico l'aggiornamento da {server}...", TESTO)
        thread = threading.Thread(target=self._lavoro_aggiornamento, args=(nuova,),
                                  daemon=True)
        thread.start()

    def chiudi(self):
        if self.occupato:
            vuoi_chiudere = messagebox.askyesno(
                "Download in corso",
                "C'e' un'operazione in corso. Vuoi annullarla e chiudere l'app?")
            if not vuoi_chiudere:
                return
            self.downloader.annulla()
        self.destroy()

    def destroy(self):
        """Ferma i timer prima di chiudere, per non avere errori."""
        for id_timer in self.timer.values():
            try:
                self.after_cancel(id_timer)
            except Exception:
                pass
        super().destroy()

    # ==============================================================
    # LAVORI NEI THREAD (non toccano mai la grafica!)
    # ==============================================================

    def _lavoro_analisi(self, url):
        try:
            info = self.downloader.analizza(url)
            self.coda.put(("analisi_ok", info))
            immagine = self._scarica_copertina(info)
            if immagine is not None:
                self.coda.put(("copertina", immagine))
        except ValueError as errore:
            self.coda.put(("analisi_errore", str(errore)))
        except Exception as errore:
            self.coda.put(("analisi_errore", dl.messaggio_errore(errore)))

    def _lavoro_download(self, info, modalita, qualita, cartella):
        try:
            percorso = self.downloader.scarica(
                info, modalita, qualita, cartella,
                al_progresso=lambda dati: self.coda.put(("progresso", dati)),
                al_cambio_stato=lambda testo: self.coda.put(("stato", testo)))
            self.coda.put(("download_ok", percorso))
        except dl.DownloadAnnullato:
            self.coda.put(("download_annullato", None))
        except ValueError as errore:
            self.coda.put(("download_errore", str(errore)))
        except Exception as errore:
            self.coda.put(("download_errore", dl.messaggio_errore(errore)))

    def _lavoro_controllo(self, silenzioso):
        try:
            nuova = agg.controlla()
            self.coda.put(("agg_controllo", (nuova, silenzioso)))
        except Exception as errore:
            self.coda.put(("agg_errore_controllo", (str(errore), silenzioso)))

    def _lavoro_aggiornamento(self, nuova):
        try:
            if agg.e_app_compilata():
                preparato = agg.scarica_e_prepara(
                    nuova, al_progresso=lambda p: self.coda.put(("agg_progresso", p)))
                self.coda.put(("agg_riavvia", preparato))
            else:
                self.coda.put(("agg_progresso", 50))
                messaggio = agg.aggiorna_codice()
                self.coda.put(("agg_codice_ok", messaggio))
        except Exception as errore:
            self.coda.put(("agg_errore", str(errore)))

    def _scarica_copertina(self, info):
        """Scarica la miniatura del video. Se non riesce, pazienza."""
        if Image is None or not info.get("id"):
            return None
        indirizzo = f"https://i.ytimg.com/vi/{info['id']}/hqdefault.jpg"
        try:
            if certifi:
                contesto = ssl.create_default_context(cafile=certifi.where())
            else:
                contesto = ssl.create_default_context()
            with urllib.request.urlopen(indirizzo, timeout=10, context=contesto) as risposta:
                dati = risposta.read()
            immagine = Image.open(io.BytesIO(dati)).convert("RGB")
            # hqdefault e' 4:3 con bande nere: tagliamo al centro in 16:9
            larghezza, altezza = immagine.size
            nuova_altezza = int(larghezza * 9 / 16)
            sopra = (altezza - nuova_altezza) // 2
            return immagine.crop((0, sopra, larghezza, sopra + nuova_altezza))
        except Exception:
            return None

    # ==============================================================
    # LETTURA DELLA CODA (gira nel thread principale)
    # ==============================================================

    def _leggi_coda(self):
        try:
            while True:
                tipo, dati = self.coda.get_nowait()
                self._gestisci_messaggio(tipo, dati)
        except queue.Empty:
            pass
        self.timer["coda"] = self.after(100, self._leggi_coda)

    def _gestisci_messaggio(self, tipo, dati):
        if tipo == "analisi_ok":
            self.info = dati
            self._mostra_info(dati)
            self._aggiorna_menu_qualita()
            self._imposta_occupato(False)
            self._messaggio_url("Link valido.", VERDE)
            self._stato_download("Pronto per il download.", TESTO_SPENTO)

        elif tipo == "copertina":
            self.immagine_copertina = ctk.CTkImage(dark_image=dati, light_image=dati,
                                                   size=(176, 99))
            self.copertina.configure(image=self.immagine_copertina, fg_color="transparent")

        elif tipo == "analisi_errore":
            self._imposta_occupato(False)
            self._messaggio_url(dati.splitlines()[0], ROSSO)
            self._mostra_info(None)
            self._stato_download(dati, ROSSO)

        elif tipo == "progresso":
            percentuale = dati["percentuale"]
            self.progresso_obiettivo = percentuale / 100
            self.testo_percentuale.configure(text=f"{percentuale:.0f}%")
            pezzi = [dl.formatta_velocita(dati["velocita"])]
            if dati["totale"]:
                pezzi.append(f"{dl.formatta_byte(dati['scaricati'])} di "
                             f"{dl.formatta_byte(dati['totale'])}")
            if dati["tempo_rimasto"] is not None:
                pezzi.append(f"{dl.formatta_durata(dati['tempo_rimasto'])} rimasti")
            self.testo_velocita.configure(text="   ·   ".join(pezzi))
            parte = {"video": "traccia video", "audio": "traccia audio"}.get(dati["parte"], "file")
            self._stato_download(f"Download {parte} in corso...", TESTO)

        elif tipo == "stato":
            self._stato_download(dati, TESTO)

        elif tipo == "download_ok":
            self.ultimo_file = dati
            self.progresso_obiettivo = 1
            self.barra.configure(progress_color=VERDE)
            self.testo_percentuale.configure(text="100%")
            self.testo_velocita.configure(text="")
            self._imposta_occupato(False)
            self.pulsante_annulla.configure(state="disabled")
            nome = Path(dati).name if dati else ""
            self._stato_download(f"Completato: {nome}", VERDE)

        elif tipo == "download_annullato":
            self._fine_con_problema("Download annullato. I file parziali sono stati eliminati.",
                                    ARANCIONE)

        elif tipo == "download_errore":
            self._fine_con_problema(dati, ROSSO)

        # --- messaggi degli aggiornamenti ---
        elif tipo == "agg_controllo":
            risultato, silenzioso = dati
            server = risultato["server"].replace("http://", "")
            nuova = risultato if risultato["disponibile"] else None
            self.aggiornamento = nuova
            self.pulsante_aggiorna.configure(state="normal")
            if nuova:
                self.pulsante_aggiorna.configure(
                    text=f"Aggiorna a v{nuova['versione']}",
                    fg_color=BLU, hover_color=BLU_SCURO)
                if not silenzioso:
                    self._chiedi_se_aggiornare()
            else:
                self.pulsante_aggiorna.configure(text="Aggiornamenti")
                if not silenzioso:
                    messagebox.showinfo("Aggiornamenti",
                                        f"Hai gia' l'ultima versione (v{agg.VERSIONE}).\n\n"
                                        f"Server usato: {server}")

        elif tipo == "agg_errore_controllo":
            testo, silenzioso = dati
            self.pulsante_aggiorna.configure(text="Aggiornamenti", state="normal")
            if not silenzioso:
                messagebox.showerror("Aggiornamenti", testo)

        elif tipo == "agg_progresso":
            self.progresso_obiettivo = dati / 100
            self.testo_percentuale.configure(text=f"{dati:.0f}%")

        elif tipo == "agg_riavvia":
            self.progresso_obiettivo = 1
            self._stato_download("Aggiornamento pronto: l'app si riapre da sola...", VERDE)
            self.update()
            agg.avvia_sostituzione(dati)
            self.after(800, self.destroy)

        elif tipo == "agg_codice_ok":
            self.progresso_obiettivo = 1
            self._imposta_occupato(False)
            self.pulsante_aggiorna.configure(text="Aggiornamenti", state="normal",
                                             fg_color=GRIGIO_PULSANTE,
                                             hover_color=GRIGIO_PULSANTE_HOVER)
            self.aggiornamento = None
            self._stato_download(dati, VERDE)
            messagebox.showinfo("Aggiornamento", dati)

        elif tipo == "agg_errore":
            self.pulsante_aggiorna.configure(state="normal")
            self._fine_con_problema(dati, ROSSO)

    def _fine_con_problema(self, testo, colore):
        self.progresso_obiettivo = 0
        self.testo_percentuale.configure(text="0%")
        self.testo_velocita.configure(text="")
        self._imposta_occupato(False)
        self.pulsante_annulla.configure(state="disabled")
        self._stato_download(testo, colore)

    # ==============================================================
    # AGGIORNAMENTI DELLA GRAFICA
    # ==============================================================

    def _mostra_info(self, info):
        if info is None:
            self.info_titolo.configure(text="Nessun contenuto analizzato")
            self.info_canale.configure(text="Incolla un link e premi \"Analizza URL\"")
            self.info_dettagli.configure(text="")
            self.copertina.configure(image=None, fg_color=SFONDO)
            self.immagine_copertina = None
            return
        self.info_titolo.configure(text=info.get("title") or "Senza titolo")
        self.info_canale.configure(text=info.get("uploader") or info.get("channel") or "")
        dettagli = [f"Durata {dl.formatta_durata(info.get('duration'))}"]
        if info.get("view_count") is not None:
            dettagli.append(f"{dl.formatta_numero(info['view_count'])} visualizzazioni")
        data = info.get("upload_date")  # formato AAAAMMGG
        if data and len(data) == 8:
            dettagli.append(f"{data[6:8]}/{data[4:6]}/{data[0:4]}")
        self.info_dettagli.configure(text="   ·   ".join(dettagli))

    def _aggiorna_menu_qualita(self):
        """Riempie il menu delle qualita' in base a VIDEO o AUDIO."""
        modalita = self.selettore_modalita.get()
        self.mappa_qualita = {}

        if modalita == "AUDIO":
            for valore in dl.QUALITA_AUDIO:
                self.mappa_qualita[ETICHETTE_AUDIO[valore]] = valore
            predefinita = ETICHETTE_AUDIO[dl.QUALITA_AUDIO_PREDEFINITA]
        elif self.info is not None:
            for altezza in dl.qualita_video_disponibili(self.info, bool(self.downloader.ffmpeg)):
                self.mappa_qualita[dl.nome_qualita(altezza)] = altezza
            predefinita = None
            # Di default 1080p se c'e', altrimenti la migliore
            for testo, altezza in self.mappa_qualita.items():
                if altezza <= 1080:
                    predefinita = testo
                    break
            if predefinita is None and self.mappa_qualita:
                predefinita = list(self.mappa_qualita)[0]
        else:
            predefinita = None

        valori = list(self.mappa_qualita) or ["Analizza prima un link"]
        self.menu_qualita.configure(values=valori)
        self.menu_qualita.set(predefinita or valori[0])
        self._aggiorna_dimensione()

    def _aggiorna_dimensione(self):
        """Mostra sotto al menu la dimensione stimata del file."""
        testo = ""
        if self.info is not None and self.menu_qualita.get() in self.mappa_qualita:
            valore = self.mappa_qualita[self.menu_qualita.get()]
            if self.selettore_modalita.get() == "AUDIO":
                durata = self.info.get("duration")
                if durata:
                    # MP3: kbps * secondi / 8 = byte (circa)
                    testo = f"Dimensione stimata: {dl.formatta_byte(int(valore) * 1000 * durata / 8)}"
            else:
                stima = dl.dimensione_stimata(self.info, valore)
                if stima:
                    testo = f"Dimensione stimata: {dl.formatta_byte(stima)}"
        if not self.downloader.ffmpeg:
            avviso = "FFmpeg non trovato: niente MP3 e video solo in bassa qualita'."
            testo = f"{testo}\n{avviso}" if testo else avviso
            self.messaggio_formato.configure(text=testo, text_color=ARANCIONE)
        else:
            self.messaggio_formato.configure(text=testo, text_color=TESTO_SPENTO)

    def _imposta_occupato(self, occupato, testo=""):
        """Blocca/sblocca i pulsanti e cambia l'indicatore di stato."""
        self.occupato = occupato
        stato = "disabled" if occupato else "normal"
        for widget in (self.pulsante_analizza, self.pulsante_scarica,
                       self.pulsante_cartella, self.pulsante_incolla,
                       self.selettore_modalita, self.menu_qualita):
            widget.configure(state=stato)
        self.campo_url.configure(state=stato)
        # Il pulsante SCARICA diventa piu' scuro quando non si puo' premere
        self.pulsante_scarica.configure(fg_color=ROSSO_SPENTO if occupato else ROSSO)

        if occupato:
            self.testo_stato_app.configure(text=testo)
            if not self.pulsazione_accesa:
                self.pulsazione_accesa = True
                self._pulsa(True)
        else:
            self.pulsazione_accesa = False
            self.pallino.configure(text_color=VERDE)
            self.testo_stato_app.configure(text="Pronto")

    def _pulsa(self, acceso):
        """Animazione leggera: il pallino lampeggia mentre l'app lavora."""
        if not self.pulsazione_accesa:
            return
        self.pallino.configure(text_color=ARANCIONE if acceso else "#7a4c05")
        self.timer["pulsa"] = self.after(500, lambda: self._pulsa(not acceso))

    def _anima_barra(self):
        """Animazione leggera: la barra si muove in modo fluido."""
        differenza = self.progresso_obiettivo - self.progresso_attuale
        if abs(differenza) > 0.001:
            self.progresso_attuale += differenza * 0.2
            self.barra.set(self.progresso_attuale)
        self.timer["barra"] = self.after(30, self._anima_barra)

    def _messaggio_url(self, testo, colore):
        self.messaggio_url.configure(text=testo, text_color=colore)

    def _stato_download(self, testo, colore):
        self.testo_stato.configure(text=testo, text_color=colore)

    def _controlla_programmi(self):
        """All'avvio avvisa se mancano FFmpeg o Deno."""
        mancanti = []
        if not self.downloader.ffmpeg:
            mancanti.append(f"FFmpeg ({dl.comando_installazione('ffmpeg')})")
        if not self.downloader.deno:
            mancanti.append(f"Deno ({dl.comando_installazione('deno')})")
        if mancanti:
            self._stato_download(
                "Attenzione, mancano: " + ", ".join(mancanti) +
                f".\nEsegui {dl.SCRIPT_INSTALLAZIONE} per installarli.", ARANCIONE)

    def _percorso_corto(self, percorso):
        """/Users/simone/Downloads -> ~/Downloads"""
        percorso = Path(percorso)
        try:
            relativo = percorso.relative_to(Path.home())
            return "~" if str(relativo) == "." else "~/" + str(relativo)
        except ValueError:
            return str(percorso)


def avvia():
    app = App()
    app.mainloop()
