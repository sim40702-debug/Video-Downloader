"""
crea_icona.py
-------------
Disegna l'icona dell'app (quadrato rosso arrotondato con il "play").
La usano build_mac.sh e build_windows.bat.

Uso: python crea_icona.py CARTELLA
Crea: CARTELLA/icona.png (per il Mac) e CARTELLA/icona.ico (per Windows)
"""

import sys
from pathlib import Path

from PIL import Image, ImageDraw


def disegna(lato=1024):
    icona = Image.new("RGBA", (lato, lato), (0, 0, 0, 0))
    disegno = ImageDraw.Draw(icona)
    # Sfondo rosso con angoli arrotondati
    margine = lato * 0.1
    disegno.rounded_rectangle((margine, margine, lato - margine, lato - margine),
                              radius=lato * 0.18, fill=(255, 59, 48, 255))
    # Triangolo bianco del "play"
    centro_x = lato / 2 + lato * 0.025
    centro_y = lato / 2
    d = lato * 0.185
    disegno.polygon([(centro_x - d * 0.85, centro_y - d),
                     (centro_x - d * 0.85, centro_y + d),
                     (centro_x + d, centro_y)], fill=(255, 255, 255, 255))
    return icona


if __name__ == "__main__":
    cartella = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    cartella.mkdir(parents=True, exist_ok=True)
    immagine = disegna()
    immagine.save(cartella / "icona.png")
    immagine.save(cartella / "icona.ico",
                  sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print(f"Icona creata in {cartella}")
