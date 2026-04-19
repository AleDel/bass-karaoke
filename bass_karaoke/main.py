"""Punto de entrada del paquete bass_karaoke."""
from .app import BassKaraoke


def main():
    app = BassKaraoke()
    app.run()


if __name__ == "__main__":
    main()
