"""
Bass Karaoke v3 — punto de entrada.
El código vive en el paquete bass_karaoke/.

CONTROLES:
  ESPACIO         → Play / Pausa (con countdown 4-3-2-1)
  C               → Activar/desactivar countdown
  R               → Reiniciar
  ← / →           → Compás anterior / siguiente (snap)
  ↑ / ↓           → Tempo ±5 BPM
  , / .           → Offset MP3 ±0.05 s  (fino)
  Shift + , / .   → Offset MP3 ±0.5 s   (grueso)
  D               → Selector de dispositivo de audio
  P               → Selector de método de pitch
  S               → Cambiar renderer partitura (Verovio ↔ Music21)
  M               → Silenciar/activar MP3
  T               → Afinador
  F5              → Guardar config
  ESC             → Salir
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if __name__ == "__main__":
    from bass_karaoke.main import main
    main()
