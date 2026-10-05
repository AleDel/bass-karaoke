"""
Todas las constantes de configuración, audio, UI y rutas de Bass Karaoke.
"""
import os
import sys
from pathlib import Path

# ─── Rutas del proyecto ───────────────────────────────────────────────────────
if getattr(sys, "frozen", False):
    # App empaquetada (PyInstaller): carpetas junto al .exe
    _BASE_DIR = Path(sys.executable).parent
else:
    _BASE_DIR = Path(__file__).parent.parent   # carpeta raíz del proyecto

SONGS_DIR     = str(_BASE_DIR / "songs")

# Canción por defecto (fallback cuando no hay configuración guardada)
MUSICXML_PATH = str(_BASE_DIR / "songs" / "mitab" / "mitab.musicxml")
TG_PATH       = str(_BASE_DIR / "songs" / "mitab" / "mitab.tg")
CONFIG_PATH   = str(_BASE_DIR / "bass_karaoke_config.json")

# ─── Audio ────────────────────────────────────────────────────────────────────
SAMPLERATE        = 44100
CHUNK_SIZE        = 2048
WIN_S             = 4096    # ventana ~93 ms — buen compromiso latencia/precision en graves
HOP_S             = CHUNK_SIZE
CONF_THRESH       = 0.4     # más permisivo; notas graves tienen confianza baja
PITCH_HOLD_FRAMES = 8       # frames sin señal antes de resetear (≈370 ms)
MIN_HZ            = 28.0
MAX_HZ            = 400.0

# ─── Pre-filtrado del audio antes del detector ───────────────────────────────
# El bajo es dominante en armónicos: un low-pass que corte los armónicos evita
# que YIN/CREPE/PESTO se enclaven una octava arriba de la fundamental.
LOWPASS_HZ        = 700.0   # corta armónicos > ~700 Hz (fundamental del bajo ≤ ~275 Hz)
HIGHPASS_HZ       = 20.0    # elimina DC y rumble < B0 (30.87 Hz) que ensucia la autocorrelación

# ─── Motor aubio ─────────────────────────────────────────────────────────────
# yinfft (no yinfast) con ventana 8192 (~186 ms ⇒ >4 periodos a E1=41 Hz).
# tolerance 0.15 es el default estricto de YIN: con un bajo por micrófono
# declara "sin pitch" demasiado seguido, así que lo subimos a 0.3.
# La confianza de YIN en graves es baja por naturaleza → umbral propio 0.15.
AUBIO_METHOD      = "yinfft"
AUBIO_FFTSIZE     = 8192
AUBIO_TOLERANCE   = 0.3
AUBIO_CONF_THRESH = 0.15
AUBIO_SILENCE_DB  = -80.0

# Rango fundamental máximo del bajo (traste 15 en G = ~275 Hz + margen).
# Se usa para plegar armónicos a la fundamental sin tocar notas reales.
BASS_MAX_HZ       = 300.0

# ── Métodos de detección de pitch disponibles ─────────────────────────────────
PITCH_METHODS = [
    "mpm",            # McLeod Pitch Method — afinador monofónico, excelente en graves, CPU
    "aubio",          # aubio yinfft — sin GPU, mínima latencia, bueno en graves
    "crepe-tiny",     # CREPE tiny     — rápido en GPU
    "crepe-full",     # CREPE full     — más preciso, más lento
    "pesto",          # PESTO streaming (PyTorch)
    "pesto-onnx",     # PESTO ONNX     — sin PyTorch en inferencia
    "basic-pitch",    # Spotify Basic Pitch — buffer deslizante 1.5s
]

# ─── MPM (McLeod Pitch Method) ────────────────────────────────────────────────
MPM_WIN       = 4096    # ventana ~93 ms — ~4 periodos a E1 (41 Hz)
MPM_THRESHOLD = 0.80    # claridad NSDF mínima para aceptar la nota (0-1)

# Ruta del modelo ONNX de PESTO (exportado con SR=44100, chunk=512)
PESTO_ONNX_PATH = str(_BASE_DIR / "models" / "mir-1k_g7_44100_512.onnx")

# ─── Cuerdas del bajo ─────────────────────────────────────────────────────────
# String 1=G, 2=D, 3=A, 4=E — convención MusicXML
STRING_OPEN_HZ = {4: 41.20, 3: 55.00, 2: 73.42, 1: 98.00}
STRING_NAMES   = {4: "E", 3: "A", 2: "D", 1: "G"}
STRING_COLORS  = {
    4: (255,  90,  90),
    3: (255, 200,  70),
    2: ( 80, 185, 255),
    1: (120, 255, 140),
}
STRING_THICK = {4: 3, 3: 2, 2: 1, 1: 1}

# ─── Tempo ────────────────────────────────────────────────────────────────────
BPM_DEFAULT  = 113
BPM_ORIGINAL = 113.0   # tempo nativo del MP3 / MusicXML

# ─── Mástil ───────────────────────────────────────────────────────────────────
NECK_FRETS      = 15
NECK_DOT_FRETS  = {3, 5, 7, 9, 15}
NECK_OCT_FRETS  = {12}

# ─── UI: dimensiones principales ─────────────────────────────────────────────
W, H = 1280, 860
FPS  = 60

HEADER_H  = 55
KARAOKE_Y = HEADER_H + 3   # tira de acordes + letra (J para mostrar/ocultar)
KARAOKE_H = 44
TAB_Y     = KARAOKE_Y + KARAOKE_H
TAB_H     = 208
SCORE_H   = 140   # altura de la sub-zona de partitura dentro de TAB
GUITARTAB_H = 60  # tablatura estilo TuxGuitar debajo de la partitura
GUITARTAB_Y = TAB_Y + TAB_H + 8 + SCORE_H + 2   # = 460
TAB_TOTAL = TAB_H + SCORE_H + GUITARTAB_H + 8    # = 460

NECK_Y    = TAB_Y + TAB_TOTAL + 16   # = 534
NECK_H    = 108
NECK_W    = 726

NECK_LABEL_W  = 26
NECK_NUT_X    = NECK_LABEL_W + 6
NECK_AREA_X   = NECK_NUT_X + 10
NECK_AREA_W   = NECK_W - NECK_AREA_X - 6

PIANO_X   = NECK_W + 6
PIANO_Y   = NECK_Y
PIANO_H   = NECK_H
PIANO_W   = W - PIANO_X - 2

LOWER_Y   = NECK_Y + NECK_H + 14   # = 656
LOWER_H   = 148                     # ajustado a H=860 (BOTTOM_Y=808)

BOTTOM_Y  = H - 52

# Piano range (bass guitar range)
PIANO_START_MIDI = 28   # E1
PIANO_END_MIDI   = 63   # Eb4

# ─── Paleta de colores ────────────────────────────────────────────────────────
C_BG      = ( 10,  10,  18)
C_BG2     = ( 16,  16,  30)
C_PANEL   = ( 22,  22,  42)
C_DGRAY   = ( 35,  35,  55)
C_ACCENT  = (255, 185,   0)
C_GREEN   = ( 50, 230, 110)
C_RED     = (255,  70,  70)
C_BLUE    = ( 80, 170, 255)
C_WHITE   = (235, 235, 250)
C_GRAY    = ( 95,  95, 115)
C_SECTION = (255, 120,  50)
C_OK      = ( 50, 230, 110)
C_ERR     = (255,  70,  70)
C_WAIT    = (255, 185,   0)
C_OVERLAY = ( 10,  10,  25, 210)
C_WOOD    = ( 42,  26,   8)
C_WOOD2   = ( 68,  42,  14)
C_NUT     = (215, 195, 155)
C_FRET    = (155, 155, 135)
C_DOT     = ( 68,  68,  55)

# ─── Teclas negras del piano (por índice dentro de la octava) ─────────────────
_IS_BLACK_KEY = [False, True, False, True, False, False,
                 True, False, True, False, True, False]
