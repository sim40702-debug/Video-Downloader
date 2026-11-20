"""
Test della logica di download (downloader.py).
Avvio: .venv/bin/python -m unittest discover -s tests -v

I test d'integrazione usano un piccolo server locale e FFmpeg:
non serve Internet e non toccano YouTube.
"""

import functools
import http.server
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

# Per poter importare downloader.py dalla cartella principale
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import downloader as dl  # noqa: E402


class TestLink(unittest.TestCase):

    def test_link_validi(self):
        validi = [
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "https://youtube.com/watch?v=dQw4w9WgXcQ&t=42s",
            "https://www.youtube.com/watch?feature=share&v=dQw4w9WgXcQ",
            "https://youtu.be/dQw4w9WgXcQ",
            "https://youtu.be/dQw4w9WgXcQ?si=abc",
            "https://www.youtube.com/shorts/dQw4w9WgXcQ",
            "https://m.youtube.com/watch?v=dQw4w9WgXcQ",
            "https://music.youtube.com/watch?v=dQw4w9WgXcQ",
            "https://www.youtube.com/live/dQw4w9WgXcQ",
            "www.youtube.com/watch?v=dQw4w9WgXcQ",
            "   https://youtu.be/dQw4w9WgXcQ   ",
        ]
        for link in validi:
            with self.subTest(link=link):
                self.assertTrue(dl.url_valido(link))

    def test_link_non_validi(self):
        non_validi = [
            "", None, "ciao", "https://www.google.com",
            "https://vimeo.com/123456",
            "https://www.youtube.com/",
            "https://www.youtube.com/watch?v=corto",
            "https://www.youtube.com/playlist?list=PL123",
            "https://notyoutube.com/watch?v=dQw4w9WgXcQ",
        ]
        for link in non_validi:
            with self.subTest(link=link):
                self.assertFalse(dl.url_valido(link))


class TestFormattazione(unittest.TestCase):

    def test_byte(self):
        self.assertEqual(dl.formatta_byte(None), "—")
        self.assertEqual(dl.formatta_byte(500), "500 B")
        self.assertEqual(dl.formatta_byte(1536), "1.5 KB")
        self.assertEqual(dl.formatta_byte(5 * 1024 * 1024), "5.0 MB")
        self.assertEqual(dl.formatta_byte(3 * 1024 ** 3), "3.0 GB")

    def test_velocita(self):
        self.assertEqual(dl.formatta_velocita(None), "—")
        self.assertEqual(dl.formatta_velocita(2 * 1024 * 1024), "2.0 MB/s")

    def test_durata(self):
        self.assertEqual(dl.formatta_durata(None), "—")
        self.assertEqual(dl.formatta_durata(5), "0:05")
        self.assertEqual(dl.formatta_durata(185), "3:05")
        self.assertEqual(dl.formatta_durata(3725), "1:02:05")

    def test_numero(self):
        self.assertEqual(dl.formatta_numero(1234567), "1.234.567")
        self.assertEqual(dl.formatta_numero(None), "—")

    def test_nome_qualita(self):
        self.assertEqual(dl.nome_qualita(2160), "2160p (4K)")
        self.assertEqual(dl.nome_qualita(1080), "1080p (Full HD)")
        self.assertEqual(dl.nome_qualita(480), "480p")


# Informazioni finte, simili a quelle che restituisce yt-dlp
INFO_FINTA = {
    "id": "dQw4w9WgXcQ",
    "title": "Video di prova",
    "duration": 212,
    "formats": [
        {"format_id": "sb0", "ext": "mhtml", "height": 90, "vcodec": "none", "acodec": "none"},
        {"format_id": "140", "ext": "m4a", "vcodec": "none", "acodec": "mp4a", "filesize": 3_000_000},
        {"format_id": "18", "ext": "mp4", "height": 360, "vcodec": "avc1", "acodec": "mp4a"},
        {"format_id": "136", "ext": "mp4", "height": 720, "vcodec": "avc1", "acodec": "none", "filesize": 20_000_000},
        {"format_id": "137", "ext": "mp4", "height": 1080, "vcodec": "avc1", "acodec": "none", "filesize_approx": 40_000_000},
        {"format_id": "271", "ext": "webm", "height": 1440, "vcodec": "vp9", "acodec": "none"},
        {"format_id": "313", "ext": "webm", "height": 2160, "vcodec": "vp9", "acodec": "none"},
    ],
}


class TestQualita(unittest.TestCase):

    def test_qualita_con_ffmpeg(self):
        self.assertEqual(dl.qualita_video_disponibili(INFO_FINTA, True),
                         [2160, 1440, 1080, 720, 360])

    def test_qualita_senza_ffmpeg(self):
        # Senza FFmpeg solo i formati con audio e video insieme
        self.assertEqual(dl.qualita_video_disponibili(INFO_FINTA, False), [360])

    def test_qualita_info_vuota(self):
        self.assertEqual(dl.qualita_video_disponibili({}), [])

    def test_opzioni_video(self):
        opzioni = dl.opzioni_formato_video(1080, True)
        self.assertEqual(opzioni["format"], "bv*+ba/b")
        self.assertEqual(opzioni["format_sort"][0], "res:1080")
        self.assertIn("ext:mp4:m4a", opzioni["format_sort"])
        self.assertEqual(opzioni["merge_output_format"], "mp4")
        senza = dl.opzioni_formato_video(360, False)
        self.assertEqual(senza["format"], "b")
        self.assertNotIn("merge_output_format", senza)

    def test_opzioni_audio(self):
        opzioni = dl.opzioni_formato_audio("320")
        convertitore = opzioni["postprocessors"][0]
        self.assertEqual(convertitore["key"], "FFmpegExtractAudio")
        self.assertEqual(convertitore["preferredcodec"], "mp3")
        self.assertEqual(convertitore["preferredquality"], "320")

    def test_dimensione_stimata(self):
        self.assertEqual(dl.dimensione_stimata(INFO_FINTA, 720), 23_000_000)
        self.assertEqual(dl.dimensione_stimata(INFO_FINTA, 1080), 43_000_000)
        self.assertIsNone(dl.dimensione_stimata(INFO_FINTA, 1440))
        self.assertEqual(dl.dimensione_stimata(INFO_FINTA), 3_000_000)


class TestFile(unittest.TestCase):

    def test_nome_file_libero(self):
        with tempfile.TemporaryDirectory() as cartella:
            primo = dl.nome_file_libero(cartella, "Canzone", "mp3")
            self.assertEqual(primo.name, "Canzone.mp3")
            primo.touch()
            secondo = dl.nome_file_libero(cartella, "Canzone", "mp3")
            self.assertEqual(secondo.name, "Canzone (2).mp3")
            secondo.touch()
            self.assertEqual(dl.nome_file_libero(cartella, "Canzone", "mp3").name,
                             "Canzone (3).mp3")

    def test_pulisci_nome(self):
        self.assertNotIn("/", dl.pulisci_nome("AC/DC - Back in Black"))
        self.assertEqual(dl.pulisci_nome(""), "video")
        self.assertEqual(dl.pulisci_nome(None), "video")
        self.assertLessEqual(len(dl.pulisci_nome("a" * 400)), dl.LUNGHEZZA_MAX_NOME)

    def test_controlla_cartella(self):
        with tempfile.TemporaryDirectory() as cartella:
            self.assertIsNone(dl.controlla_cartella(cartella))
            self.assertIn("non esiste", dl.controlla_cartella(os.path.join(cartella, "nulla")))
            file = Path(cartella) / "file.txt"
            file.touch()
            self.assertIn("non e' una cartella", dl.controlla_cartella(file))
            if os.geteuid() != 0:  # root puo' scrivere ovunque
                bloccata = Path(cartella) / "bloccata"
                bloccata.mkdir()
                bloccata.chmod(0o500)
                self.assertIn("permessi", dl.controlla_cartella(bloccata))
                bloccata.chmod(0o700)


class TestErrori(unittest.TestCase):

    def test_messaggi(self):
        casi = {
            "ERROR: [youtube] abc: Private video. Sign in": "privato",
            "ERROR: [youtube] abc: Video unavailable": "non e' disponibile",
            "ERROR: Sign in to confirm your age": "eta'",
            "HTTP Error 403: Forbidden": "403",
            "HTTP Error 429: Too Many Requests": "Troppe richieste",
            "<urlopen error [Errno 8] nodename nor servname provided>": "Connessione",
            "Requested format is not available": "qualita'",
            "[Errno 28] No space left on device": "Spazio",
            "[Errno 13] Permission denied: '/x'": "permessi",
            "qualcosa di strano": "qualcosa di strano",
        }
        for testo, atteso in casi.items():
            with self.subTest(testo=testo):
                self.assertIn(atteso, dl.messaggio_errore(Exception(testo)))
        self.assertEqual(dl.messaggio_errore(dl.DownloadAnnullato()), "Download annullato.")

    def test_comando_installazione(self):
        with mock.patch.object(dl, "SU_WINDOWS", True):
            self.assertEqual(dl.comando_installazione("ffmpeg"), "winget install Gyan.FFmpeg")
            self.assertEqual(dl.comando_installazione("deno"), "winget install DenoLand.Deno")
        with mock.patch.object(dl, "SU_WINDOWS", False), mock.patch.object(dl, "SU_MAC", True):
            self.assertEqual(dl.comando_installazione("ffmpeg"), "brew install ffmpeg")

    def test_link_sbagliato_in_analisi(self):
        with self.assertRaises(ValueError):
            dl.Downloader().analizza("https://www.google.com")


# ------------------------------------------------------------------
# Test d'integrazione: download veri da un server locale
# ------------------------------------------------------------------

class GestoreSilenzioso(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *argomenti):
        pass


class ServerSilenzioso(http.server.ThreadingHTTPServer):
    # Quando annulliamo un download la connessione si chiude a meta': e' normale
    def handle_error(self, richiesta, indirizzo):
        pass


@unittest.skipUnless(dl.trova_ffmpeg(), "FFmpeg non installato")
class TestDownloadLocale(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        os.environ["no_proxy"] = os.environ["NO_PROXY"] = "127.0.0.1,localhost"
        cls.cartella_server = tempfile.TemporaryDirectory()
        # Video di prova di 8 secondi creato con FFmpeg
        cls.video = Path(cls.cartella_server.name) / "prova.mp4"
        subprocess.run(
            [dl.trova_ffmpeg(), "-loglevel", "error", "-y",
             "-f", "lavfi", "-i", "testsrc=duration=8:size=640x360:rate=25",
             "-f", "lavfi", "-i", "sine=frequency=440:duration=8",
             "-c:v", "libx264", "-preset", "ultrafast", "-b:v", "2M",
             "-c:a", "aac", "-shortest", str(cls.video)],
            check=True)
        gestore = functools.partial(GestoreSilenzioso, directory=cls.cartella_server.name)
        cls.server = ServerSilenzioso(("127.0.0.1", 0), gestore)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.url = f"http://127.0.0.1:{cls.server.server_address[1]}/prova.mp4"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.cartella_server.cleanup()

    def setUp(self):
        self.cartella = tempfile.TemporaryDirectory()
        self.info = {"title": "Prova: test/1", "webpage_url": self.url}

    def tearDown(self):
        self.cartella.cleanup()

    def test_download_video_e_duplicati(self):
        downloader = dl.Downloader()
        avanzamenti = []
        primo = downloader.scarica(self.info, "VIDEO", 360, self.cartella.name,
                                   al_progresso=avanzamenti.append)
        self.assertTrue(primo.exists())
        self.assertEqual(primo.suffix, ".mp4")
        self.assertGreater(primo.stat().st_size, 10_000)
        self.assertTrue(avanzamenti, "nessun aggiornamento di avanzamento")
        self.assertGreater(avanzamenti[-1]["percentuale"], 99)

        # Secondo download dello stesso video: non deve sovrascrivere
        secondo = downloader.scarica(self.info, "VIDEO", 360, self.cartella.name)
        self.assertNotEqual(primo, secondo)
        self.assertIn("(2)", secondo.name)
        self.assertEqual(len(list(Path(self.cartella.name).iterdir())), 2)

    def test_download_audio_mp3(self):
        downloader = dl.Downloader()
        stati = []
        file = downloader.scarica(self.info, "AUDIO", "128", self.cartella.name,
                                  al_cambio_stato=stati.append)
        self.assertEqual(file.suffix, ".mp3")
        self.assertTrue(file.exists())
        self.assertTrue(any("MP3" in s for s in stati))
        # Deve restare solo l'MP3, nessun file intermedio
        self.assertEqual([f.name for f in Path(self.cartella.name).iterdir()], [file.name])

    def test_annulla(self):
        downloader = dl.Downloader()
        with self.assertRaises(dl.DownloadAnnullato):
            downloader.scarica(self.info, "VIDEO", 360, self.cartella.name,
                               al_progresso=lambda dati: downloader.annulla())
        # Dopo l'annullamento non devono restare file a meta'
        self.assertEqual(list(Path(self.cartella.name).iterdir()), [])

    def test_cartella_non_valida(self):
        with self.assertRaises(ValueError):
            dl.Downloader().scarica(self.info, "VIDEO", 360, "/cartella/che/non/esiste")


if __name__ == "__main__":
    unittest.main()
