"""
Test dell'interfaccia: apre la finestra senza mostrarla e prova
i pulsanti principali simulando i messaggi dei thread.
Viene saltato se non c'e' uno schermo disponibile.
"""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    import tkinter
    tkinter.Tk().destroy()
    SCHERMO_DISPONIBILE = True
except Exception:
    SCHERMO_DISPONIBILE = False

from test_downloader import INFO_FINTA  # noqa: E402


@unittest.skipUnless(SCHERMO_DISPONIBILE, "nessuno schermo disponibile")
class TestInterfaccia(unittest.TestCase):

    def setUp(self):
        import interface
        self.interface = interface
        self.app = interface.App(controlla_aggiornamenti=False)
        self.app.withdraw()
        self.app.update()

    def tearDown(self):
        self.app.destroy()

    def test_avvio(self):
        self.assertEqual(self.app.selettore_modalita.get(), "VIDEO")
        self.assertEqual(self.app.cartella, Path.home() / "Downloads")
        self.assertFalse(self.app.occupato)

    def test_link_non_valido(self):
        self.app.campo_url.insert(0, "ciao")
        self.app.analizza()
        self.assertIn("non e' valido", self.app.messaggio_url.cget("text"))
        self.assertFalse(self.app.occupato)

    def test_analisi_e_qualita(self):
        self.app._gestisci_messaggio("analisi_ok", INFO_FINTA)
        self.assertEqual(self.app.info_titolo.cget("text"), "Video di prova")
        # Con FFmpeg la qualita' predefinita e' 1080p
        if self.app.downloader.ffmpeg:
            self.assertEqual(self.app.menu_qualita.get(), "1080p (Full HD)")
        self.app.selettore_modalita.set("AUDIO")
        self.app._aggiorna_menu_qualita()
        self.assertEqual(self.app.menu_qualita.get(), "192 kbps (consigliata)")

    def test_progresso_e_fine(self):
        self.app._imposta_occupato(True, "Download...")
        self.assertEqual(self.app.pulsante_scarica.cget("state"), "disabled")
        self.app._gestisci_messaggio("progresso", {
            "percentuale": 42.0, "scaricati": 4_200_000, "totale": 10_000_000,
            "velocita": 2_097_152, "tempo_rimasto": 6, "parte": "video"})
        self.assertEqual(self.app.testo_percentuale.cget("text"), "42%")
        self.assertIn("MB/s", self.app.testo_velocita.cget("text"))
        with tempfile.NamedTemporaryFile(suffix=".mp4") as file:
            self.app._gestisci_messaggio("download_ok", Path(file.name))
        self.assertFalse(self.app.occupato)
        self.assertIn("Completato", self.app.testo_stato.cget("text"))

    def test_errore_e_annullamento(self):
        self.app._imposta_occupato(True, "Download...")
        self.app._gestisci_messaggio("download_errore", "Connessione assente")
        self.assertFalse(self.app.occupato)
        self.assertEqual(self.app.testo_stato.cget("text"), "Connessione assente")
        self.app._gestisci_messaggio("download_annullato", None)
        self.assertIn("annullato", self.app.testo_stato.cget("text"))

    def test_aggiornamento_trovato(self):
        self.app._gestisci_messaggio("agg_controllo", ({
            "disponibile": True, "versione": "9.9.9", "note": "",
            "server": "http://192.168.1.118:3000", "file": None}, True))
        self.assertEqual(self.app.pulsante_aggiorna.cget("text"), "Aggiorna a v9.9.9")
        self.assertIsNotNone(self.app.aggiornamento)

    def test_nessun_aggiornamento(self):
        self.app._gestisci_messaggio("agg_controllo", ({
            "disponibile": False, "versione": "1.0.0", "note": "",
            "server": "http://192.168.1.118:3000", "file": None}, True))
        self.assertEqual(self.app.pulsante_aggiorna.cget("text"), "Aggiornamenti")
        self.assertIsNone(self.app.aggiornamento)

    def test_scarica_senza_analisi(self):
        self.app.scarica()
        self.assertIn("Analizza", self.app.messaggio_url.cget("text"))
        self.assertFalse(self.app.occupato)


if __name__ == "__main__":
    unittest.main()
