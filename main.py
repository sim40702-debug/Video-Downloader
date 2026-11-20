"""
main.py
-------
Punto di partenza dell'app Video Downloader.
Controlla che le librerie siano installate e poi apre la finestra.

Avvio da Terminale:   .venv/bin/python main.py
Avvio con doppio clic: "Avvia Video Downloader.command"
"""

import sys


def mostra_errore(titolo, testo):
    """Mostra un errore in una finestra (se possibile) e nel terminale."""
    print(f"{titolo}: {testo}", file=sys.stderr)
    try:
        import tkinter
        from tkinter import messagebox
        finestra = tkinter.Tk()
        finestra.withdraw()
        messagebox.showerror(titolo, testo)
        finestra.destroy()
    except Exception:
        pass


def controlla_librerie():
    """Restituisce la lista delle librerie che mancano."""
    mancanti = []
    try:
        import tkinter  # noqa: F401
    except ImportError:
        print("Manca tkinter. Su Mac con Homebrew: brew install python-tk", file=sys.stderr)
        sys.exit(1)
    for nome_import, nome_pip in [("customtkinter", "customtkinter"),
                                  ("yt_dlp", "yt-dlp"),
                                  ("PIL", "pillow")]:
        try:
            __import__(nome_import)
        except ImportError:
            mancanti.append(nome_pip)
    return mancanti


def main():
    if sys.version_info < (3, 10):
        mostra_errore("Python troppo vecchio",
                      "Serve Python 3.10 o piu' recente.\n"
                      "Installa Python da python.org oppure con: brew install python")
        sys.exit(1)

    mancanti = controlla_librerie()
    if mancanti:
        mostra_errore("Librerie mancanti",
                      "Mancano queste librerie: " + ", ".join(mancanti) +
                      "\n\nApri il Terminale nella cartella del progetto e scrivi:\n"
                      "./install.sh")
        sys.exit(1)

    from interface import avvia
    avvia()


if __name__ == "__main__":
    main()
