"""
Test degli aggiornamenti (aggiornamenti.py).
Non contattano GitHub: usano dati finti.
"""

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import aggiornamenti as agg  # noqa: E402

RELEASE_FINTA = {
    "tag_name": "v9.9.9",
    "body": "Novita' di prova",
    "assets": [
        {"name": "Video-Downloader-macOS-apple-silicon.zip", "size": 10,
         "browser_download_url": "https://github.com/sim40702-debug/YouTube-Downloader/releases/download/v9.9.9/Video-Downloader-macOS-apple-silicon.zip"},
        {"name": "Video-Downloader-windows.zip", "size": 10,
         "browser_download_url": "https://github.com/sim40702-debug/YouTube-Downloader/releases/download/v9.9.9/Video-Downloader-windows.zip"},
    ],
}


class TestVersioni(unittest.TestCase):

    def test_numeri_versione(self):
        self.assertEqual(agg.numeri_versione("v1.2.3"), (1, 2, 3))
        self.assertEqual(agg.numeri_versione("1.10"), (1, 10, 0))
        self.assertEqual(agg.numeri_versione("2.0.0-beta"), (2, 0, 0))

    def test_confronto(self):
        self.assertTrue(agg.e_piu_nuova("v1.0.1", "1.0.0"))
        self.assertTrue(agg.e_piu_nuova("1.10.0", "1.9.9"))   # 10 > 9
        self.assertFalse(agg.e_piu_nuova("v1.0.0", "1.0.0"))
        self.assertFalse(agg.e_piu_nuova("0.9.0", "1.0.0"))

    def test_versione_scritta_bene(self):
        # rilascia.js e release.yml leggono questa riga: deve avere questo formato
        testo = Path(agg.__file__).read_text(encoding="utf-8")
        self.assertIn(f'\nVERSIONE = "{agg.VERSIONE}"\n', testo)


class TestFileGiusto(unittest.TestCase):

    def test_nomi_zip(self):
        self.assertEqual(agg.nome_zip("windows"), "Video-Downloader-windows.zip")
        self.assertEqual(agg.nome_zip("intel"), "Video-Downloader-macOS-intel.zip")

    def test_scegli_file(self):
        self.assertIn("apple-silicon", agg.scegli_file(RELEASE_FINTA, "apple-silicon")["name"])
        self.assertIn("windows", agg.scegli_file(RELEASE_FINTA, "windows")["name"])
        # Per il Mac Intel nella release finta non c'e' il file
        self.assertIsNone(agg.scegli_file(RELEASE_FINTA, "intel"))

    def test_tipo_di_sistema(self):
        with mock.patch.object(agg, "SU_WINDOWS", False):
            with mock.patch("platform.machine", return_value="arm64"):
                self.assertEqual(agg.tipo_di_sistema(), "apple-silicon")
            with mock.patch("platform.machine", return_value="x86_64"):
                self.assertEqual(agg.tipo_di_sistema(), "intel")
        with mock.patch.object(agg, "SU_WINDOWS", True):
            self.assertEqual(agg.tipo_di_sistema(), "windows")



class RispostaFinta:
    def __init__(self, dati):
        self.dati = dati

    def read(self):
        return json.dumps(self.dati).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *argomenti):
        return False


class TestControllo(unittest.TestCase):

    def test_chiede_a_github(self):
        indirizzi = []

        def finto(richiesta, timeout=None, context=None):
            indirizzi.append(richiesta.full_url)
            return RispostaFinta(RELEASE_FINTA)

        with mock.patch("urllib.request.urlopen", finto):
            risultato = agg.controlla()
        self.assertEqual(indirizzi, [
            "https://api.github.com/repos/sim40702-debug/YouTube-Downloader/releases/latest"])
        self.assertTrue(risultato["disponibile"])
        self.assertEqual(risultato["versione"], "9.9.9")

    def test_gia_aggiornato(self):
        release = dict(RELEASE_FINTA, tag_name=f"v{agg.VERSIONE}")
        with mock.patch("urllib.request.urlopen", return_value=RispostaFinta(release)):
            self.assertFalse(agg.controlla()["disponibile"])

    def test_senza_internet(self):
        with mock.patch("urllib.request.urlopen", side_effect=OSError("offline")):
            with self.assertRaises(RuntimeError):
                agg.controlla()


def prepara_cartelle(base, nome_vecchia, nome_nuova):
    vecchia = base / "Applicazioni" / nome_vecchia
    vecchia.mkdir(parents=True)
    (vecchia / "versione.txt").write_text("vecchia")
    (vecchia / "solo-vecchia.txt").write_text("x")
    temp = base / "temp"
    nuova = temp / "nuova" / nome_nuova
    nuova.mkdir(parents=True)
    (nuova / "versione.txt").write_text("nuova")
    return vecchia, nuova, temp


def pid_terminato():
    """PID di un processo gia' finito: lo script non deve aspettare."""
    processo = subprocess.Popen([sys.executable, "-c", "pass"])
    processo.wait()
    return str(processo.pid)


class TestSostituzione(unittest.TestCase):

    @unittest.skipIf(sys.platform == "win32" or not shutil.which("bash"), "solo Mac/Linux")
    def test_script_mac(self):
        with tempfile.TemporaryDirectory() as base:
            vecchia, nuova, temp = prepara_cartelle(Path(base), "Video Downloader.app",
                                                    "Video Downloader.app")
            script = agg.crea_script_sostituzione(temp, "mac")
            subprocess.run(["bash", str(script), pid_terminato(), str(vecchia), str(nuova),
                            str(temp), "senza-riapertura"], capture_output=True, timeout=30)
            self.assertEqual((vecchia / "versione.txt").read_text(), "nuova")
            self.assertFalse((vecchia / "solo-vecchia.txt").exists())
            self.assertFalse(temp.exists(), "la cartella temporanea deve sparire")

    @unittest.skipUnless(sys.platform == "win32", "solo Windows")
    def test_script_windows(self):
        with tempfile.TemporaryDirectory() as base:
            vecchia, nuova, temp = prepara_cartelle(Path(base), "Video Downloader",
                                                    "Video Downloader")
            script = agg.crea_script_sostituzione(temp, "windows")
            subprocess.run(["cmd", "/c", str(script), pid_terminato(), str(vecchia),
                            str(nuova), str(temp), "senza-riapertura"],
                           capture_output=True, timeout=60)
            self.assertEqual((vecchia / "versione.txt").read_text(), "nuova")
            self.assertFalse((vecchia / "solo-vecchia.txt").exists())

    def test_script_windows_scritto_bene(self):
        """Controlla il contenuto del .bat anche se non siamo su Windows."""
        with tempfile.TemporaryDirectory() as base:
            script = agg.crea_script_sostituzione(base, "windows")
            testo = script.read_bytes().decode("utf-8")
            self.assertIn("\r\n", testo)  # i .bat vogliono CRLF
            self.assertIn("robocopy", testo)
            self.assertIn("Video Downloader.exe", testo)


if __name__ == "__main__":
    unittest.main()
