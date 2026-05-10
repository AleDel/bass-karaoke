"""Punto de entrada del paquete bass_karaoke."""
import ctypes
import sys

# ── DPI awareness: evita que Windows escale la ventana al 125 % / 150 %,
#    lo que recortaría la app en pantallas de 1080p con escala activada.
try:
    if sys.platform == "win32":
        # Per-monitor DPI v2 (Windows 10 1703+); fallback a SetProcessDPIAware
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

from .app import BassKaraoke


def main():
    app = BassKaraoke()
    app.run()


if __name__ == "__main__":
    main()
