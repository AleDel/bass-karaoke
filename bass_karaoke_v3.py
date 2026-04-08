"""
╔══════════════════════════════════════════════════════════════════╗
║         BASS KARAOKE v3 — Feet Don't Fail Me Now               ║
║         Joy Crookes | Bass: Dayna Fisher                        ║
║         MusicXML · PyAudio + aubio · varispeed (librosa)        ║
╚══════════════════════════════════════════════════════════════════╝

INSTALACIÓN:
  pip install pygame aubio pyaudio numpy sounddevice librosa

CONTROLES:
  ESPACIO         → Play / Pausa (con countdown 4-3-2-1)
  R               → Reiniciar
  ↑ / ↓          → Tempo ±5 BPM
  , / .           → Offset MP3 ±0.05 s  (fino)
  Shift + , / .   → Offset MP3 ±0.5 s   (grueso)
  D               → Abrir/cerrar selector de dispositivo de audio
  ↑ / ↓          → (dentro del menú) navegar lista
  ENTER           → (dentro del menú) confirmar dispositivo
  M               → Silenciar/activar MP3
  ESC             → Salir / cerrar menú
"""

import pygame
import numpy as np
import threading
import time
import os
import math
import json
import xml.etree.ElementTree as ET

# ─── Imports core opcionales ──────────────────────────────────────────────────
try:
    import aubio
    AUBIO_OK = True
except ImportError:
    AUBIO_OK = False
    print("[WARN] aubio no encontrado")

try:
    import pyaudio
    PA_OK = True
except ImportError:
    PA_OK = False
    print("[WARN] pyaudio no encontrado")

PITCH_AVAILABLE = AUBIO_OK and PA_OK

# ─── Varispeed: librosa + sounddevice ────────────────────────────────────────
try:
    import librosa
    import sounddevice as sd
    VARSPEED_OK = True
except ImportError:
    VARSPEED_OK = False
    print("[WARN] librosa/sounddevice no encontrados — tempo MP3 fijo")

# ═══════════════════════════════════════════════════════════════════════════════
#  PARÁMETROS DE AUDIO (bajo eléctrico)
# ═══════════════════════════════════════════════════════════════════════════════
SAMPLERATE        = 44100
CHUNK_SIZE        = 2048
WIN_S             = 8192    # ventana grande → periodo completo en notas graves (E1≈41 Hz)
HOP_S             = CHUNK_SIZE
CONF_THRESH       = 0.4     # más permisivo; notas graves tienen confianza baja
PITCH_HOLD_FRAMES = 8       # frames sin señal antes de resetear (≈370 ms)
MIN_HZ            = 28.0
MAX_HZ            = 400.0

# ═══════════════════════════════════════════════════════════════════════════════
#  CUERDAS DEL BAJO  (string 1=G, 2=D, 3=A, 4=E — convención MusicXML)
# ═══════════════════════════════════════════════════════════════════════════════
STRING_OPEN_HZ = {4: 41.20, 3: 55.00, 2: 73.42, 1: 98.00}
STRING_NAMES   = {4: "E", 3: "A", 2: "D", 1: "G"}
STRING_COLORS  = {
    4: (255,  90,  90),
    3: (255, 200,  70),
    2: ( 80, 185, 255),
    1: (120, 255, 140),
}
STRING_THICK = {4: 3, 3: 2, 2: 1, 1: 1}


def fret_to_hz(fret, string):
    return STRING_OPEN_HZ[string] * (2 ** (fret / 12.0))


def hz_to_note_name(hz):
    if hz < 10:
        return "—"
    midi  = 12 * np.log2(hz / 440.0) + 69
    midi  = int(np.round(midi))
    names = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
    return f"{names[midi % 12]}{(midi // 12) - 1}"


def notes_match(detected_hz, expected_hz):
    """Compara por pitch class (octava invariante)."""
    if detected_hz < MIN_HZ or detected_hz > MAX_HZ or expected_hz <= 0:
        return False
    midi_det = 12 * math.log2(detected_hz / 440.0) + 69
    midi_exp = 12 * math.log2(expected_hz / 440.0) + 69
    if int(round(midi_det)) % 12 == int(round(midi_exp)) % 12:
        return True
    diff_mod = abs(midi_det - midi_exp) % 12
    cents    = min(diff_mod, 12 - diff_mod) * 100
    return cents < 50


# ═══════════════════════════════════════════════════════════════════════════════
#  REPRODUCTOR VARISPEED  (librosa + sounddevice)
# ═══════════════════════════════════════════════════════════════════════════════
class VarispeedPlayer:
    """
    Carga el MP3 con librosa y lo reproduce a través de sounddevice
    con velocidad variable. Cambiar speed TAMBIÉN cambia el pitch
    (varispeed clásico), que para práctica de bajo es completamente aceptable.
    """
    def __init__(self):
        self.data      = None   # shape (frames, 2) float32
        self.sr        = SAMPLERATE
        self.pos       = 0.0   # posición flotante en frames
        self.speed     = 1.0
        self.volume    = 1.0
        self._playing  = False
        self._lock     = threading.Lock()
        self._stream   = None
        self._loaded   = False

    def load(self, path):
        if not VARSPEED_OK:
            return False
        try:
            y, sr = librosa.load(path, sr=SAMPLERATE, mono=False)
            # librosa devuelve (channels, frames) o (frames,) para mono
            if y.ndim == 1:
                y = np.stack([y, y], axis=1)
            else:
                y = y.T                           # (ch, frames) → (frames, ch)
            self.data    = y.astype(np.float32)
            self.sr      = SAMPLERATE
            self._loaded = True
            dur          = len(self.data) / SAMPLERATE
            print(f"[Varispeed] {os.path.basename(path)}  {dur:.1f}s  frames={len(self.data)}")
            return True
        except Exception as e:
            print(f"[Varispeed ERROR] {e}")
            return False

    def _callback(self, outdata, frames, time_info, status):
        with self._lock:
            if not self._playing or self.data is None:
                outdata[:] = 0
                return
            src_frames = frames * self.speed
            start      = int(self.pos)
            end        = int(self.pos + src_frames)
            if start >= len(self.data):
                outdata[:] = 0
                self._playing = False
                return
            end   = min(end, len(self.data))
            chunk = self.data[start:end]
            if len(chunk) == 0:
                outdata[:] = 0
            elif len(chunk) == frames:
                out = chunk
            else:
                idx = np.linspace(0, len(chunk) - 1, frames)
                out = np.zeros((frames, 2), dtype=np.float32)
                for ch in range(2):
                    out[:, ch] = np.interp(idx, np.arange(len(chunk)), chunk[:, ch])
            outdata[:] = (out * self.volume).reshape(outdata.shape)
            self.pos += src_frames

    def play(self, offset_sec=0.0):
        if not self._loaded:
            return
        self.stop()
        with self._lock:
            self.pos      = max(0.0, offset_sec * self.sr)
            self._playing = True
        self._stream = sd.OutputStream(
            samplerate=self.sr, channels=2,
            dtype='float32', blocksize=512,
            callback=self._callback)
        self._stream.start()

    def pause(self):
        with self._lock:
            self._playing = False

    def resume(self):
        with self._lock:
            self._playing = True
        if self._stream is None or not self._stream.active:
            self._stream = sd.OutputStream(
                samplerate=self.sr, channels=2,
                dtype='float32', blocksize=512,
                callback=self._callback)
            self._stream.start()

    def stop(self):
        with self._lock:
            self._playing = False
        if self._stream:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None
        with self._lock:
            self.pos = 0.0

    def set_speed(self, ratio):
        with self._lock:
            self.speed = max(0.3, min(2.5, float(ratio)))

    def set_volume(self, v):
        with self._lock:
            self.volume = max(0.0, min(1.0, float(v)))

    @property
    def loaded(self):
        return self._loaded

    @property
    def is_playing(self):
        with self._lock:
            return self._playing


# ═══════════════════════════════════════════════════════════════════════════════
#  PARSER MusicXML
# ═══════════════════════════════════════════════════════════════════════════════
def parse_musicxml(filepath):
    tree = ET.parse(filepath)
    root = tree.getroot()
    bpm  = 113.0
    notes   = []
    sections = []

    for part in root.findall("part"):
        divs        = 960
        measure_abs = 0

        for measure in part.findall("measure"):
            measure_num = int(measure.get("number", "0"))
            cur_pos     = 0

            attr = measure.find("attributes")
            if attr is not None:
                d = attr.find("divisions")
                if d is not None:
                    divs = int(d.text)

            for direction in measure.findall("direction"):
                for metro in direction.findall(".//metronome"):
                    pm = metro.find("per-minute")
                    if pm is not None:
                        bpm = float(pm.text)
                for reh in direction.findall(".//rehearsal"):
                    if reh.text:
                        s16 = round((measure_abs + cur_pos) / divs * 4)
                        sections.append((reh.text.strip(), s16))

            for child in list(measure):
                tag = child.tag
                if tag == "backup":
                    cur_pos -= int(child.find("duration").text)
                elif tag == "forward":
                    cur_pos += int(child.find("duration").text)
                elif tag == "note":
                    is_chord  = child.find("chord") is not None
                    staff_el  = child.find("staff")
                    staff     = int(staff_el.text) if staff_el is not None else 1
                    dur_el    = child.find("duration")
                    dur_divs  = int(dur_el.text) if dur_el is not None else 0
                    is_rest   = child.find("rest") is not None
                    fret_el   = child.find(".//notations/technical/fret")
                    string_el = child.find(".//notations/technical/string")

                    if (staff == 2 and not is_rest and not is_chord
                            and fret_el is not None and string_el is not None):
                        fret    = int(fret_el.text)
                        string  = int(string_el.text)
                        hz      = fret_to_hz(fret, string)
                        start16 = round((measure_abs + cur_pos) / divs * 4)
                        dur16   = max(1, round(dur_divs / divs * 4))
                        notes.append({
                            "fret": fret, "string": string,
                            "dur": dur16, "start16": start16,
                            "hz": hz, "note_name": hz_to_note_name(hz),
                            "measure_num": measure_num,
                            "section": f"Compás {measure_num}",
                        })
                    if not is_chord:
                        cur_pos += dur_divs

            time_el = measure.find("attributes/time")
            if time_el is not None:
                beats     = int(time_el.find("beats").text)
                beat_type = int(time_el.find("beat-type").text)
                measure_abs += int(divs * beats * (4 / beat_type))
            else:
                measure_abs += max(cur_pos, divs * 4)

    if sections:
        sec_idx = 0
        for note in notes:
            while (sec_idx + 1 < len(sections)
                   and note["start16"] >= sections[sec_idx + 1][1]):
                sec_idx += 1
            note["section"] = sections[sec_idx][0]

    return notes, sections, bpm


# ═══════════════════════════════════════════════════════════════════════════════
#  PIANO — construir lista de teclas
# ═══════════════════════════════════════════════════════════════════════════════
_IS_BLACK_KEY = [False,True,False,True,False,False,True,False,True,False,True,False]


def build_piano_keys(start_midi, end_midi, px, py, pw, ph):
    """Devuelve lista de dicts {midi, black, rect} para dibujar el piano."""
    white_count = sum(1 for m in range(start_midi, end_midi + 1)
                      if not _IS_BLACK_KEY[m % 12])
    if white_count == 0:
        return []
    ww = pw / white_count
    bw = max(5, ww * 0.58)
    wh = ph - 4
    bh = int(ph * 0.62)

    # X de cada tecla blanca
    white_x = {}
    wi = 0
    for midi in range(start_midi, end_midi + 1):
        if not _IS_BLACK_KEY[midi % 12]:
            white_x[midi] = px + wi * ww
            wi += 1

    keys_white = []
    keys_black = []

    for midi in range(start_midi, end_midi + 1):
        s = midi % 12
        if not _IS_BLACK_KEY[s]:
            keys_white.append({
                "midi": midi, "black": False,
                "rect": pygame.Rect(int(white_x[midi]), py + 2,
                                    max(1, int(ww) - 1), wh),
            })
        else:
            left_white = midi - 1   # sempre una tecla blanca (ver tabla de semitonos)
            if left_white in white_x:
                bx = white_x[left_white] + ww * 0.65 - bw / 2
                keys_black.append({
                    "midi": midi, "black": True,
                    "rect": pygame.Rect(int(bx), py + 2, max(1, int(bw)), bh),
                })

    return keys_white + keys_black   # blancas primero, negras encima (clipping)


# ═══════════════════════════════════════════════════════════════════════════════
#  CONSTANTES DE UI
# ═══════════════════════════════════════════════════════════════════════════════
W, H          = 1280, 800
FPS           = 60
BPM_DEFAULT   = 113
BPM_ORIGINAL  = 113.0   # tempo nativo del MP3 / MusicXML

HEADER_H  = 55
TAB_Y     = HEADER_H + 3
TAB_H     = 252

NECK_Y    = TAB_Y + TAB_H + 3
NECK_H    = 108
NECK_W    = 726

PIANO_X   = NECK_W + 6
PIANO_Y   = NECK_Y
PIANO_H   = NECK_H
PIANO_W   = W - PIANO_X - 2

LOWER_Y   = NECK_Y + NECK_H + 4
LOWER_H   = 196

BOTTOM_Y  = H - 52

# Rango del piano (bass guitar range)
PIANO_START_MIDI = 28   # E1
PIANO_END_MIDI   = 63   # Eb4

# Mástil
NECK_FRETS    = 15
NECK_LABEL_W  = 26
NECK_NUT_X    = NECK_LABEL_W + 6
NECK_AREA_X   = NECK_NUT_X + 10
NECK_AREA_W   = NECK_W - NECK_AREA_X - 6
NECK_DOT_FRETS  = {3, 5, 7, 9, 15}
NECK_OCT_FRETS  = {12}

# Colores
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

MUSICXML_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "cancion", "mitab.musicxml")
CONFIG_PATH   = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "bass_karaoke_config.json")


# ═══════════════════════════════════════════════════════════════════════════════
class BassKaraoke:

    def __init__(self):
        pygame.init()
        pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
        self.screen = pygame.display.set_mode((W, H))
        pygame.display.set_caption("Bass Karaoke v3  –  Feet Don't Fail Me Now")
        self.clock  = pygame.time.Clock()

        self.font_title = pygame.font.SysFont("consolas", 20, bold=True)
        self.font_huge  = pygame.font.SysFont("consolas", 74, bold=True)
        self.font_big   = pygame.font.SysFont("consolas", 30, bold=True)
        self.font_med   = pygame.font.SysFont("consolas", 19, bold=True)
        self.font_small = pygame.font.SysFont("consolas", 15)
        self.font_tiny  = pygame.font.SysFont("consolas", 12)

        # ── Estado ─────────────────────────────────────────────────────
        self.bpm          = BPM_DEFAULT
        self.playing      = False
        self.muted        = False
        self.note_idx     = 0
        self.beat_time    = 0.0
        self.score_ok     = 0
        self.score_total  = 0
        self.mp3_offset_sec = 0.0

        # ── Countdown ──────────────────────────────────────────────────
        self.counting_down   = False
        self.countdown_beat  = 4
        self.countdown_timer = 0.0

        # ── Pitch ──────────────────────────────────────────────────────
        self.detected_hz   = 0.0
        self.detected_note = "—"
        self.stable_hz     = 0.0
        self.stable_note   = "—"
        self.note_match    = None
        self.pitch_lock    = threading.Lock()
        self.audio_running = False
        self.audio_thread  = None

        # ── Dispositivos ───────────────────────────────────────────────
        self.audio_devices    = []
        self.device_idx       = 0
        self.device_menu_open = False
        self.device_menu_sel  = 0
        self._enumerate_devices()

        # ── Stats ──────────────────────────────────────────────────────
        self.section_stats = {}

        # ── Tuner ──────────────────────────────────────────────────────
        self.tuner_open   = False
        self.pitch_engine = "aubio"   # se sobreescribe al arrancar _audio_loop

        # ── Metrónomo ──────────────────────────────────────────────────
        self.metro_beat  = 0
        self.metro_flash = 0.0

        # ── Scroll ─────────────────────────────────────────────────────
        self.px_per_16th = 30
        self.viewport_x  = 0.0
        self.target_x    = 0.0

        # ── MusicXML ───────────────────────────────────────────────────
        self.notes    = []
        self.sections = []
        self._load_notes()

        # ── Piano (precalcular) ─────────────────────────────────────────
        self._piano_keys_list = []   # se rellena en draw (necesita pygame.Rect)

        # ── Audio MP3 ──────────────────────────────────────────────────
        self._vsp      = VarispeedPlayer() if VARSPEED_OK else None
        self.mp3_path  = self._find_mp3()

        if self.mp3_path and self._vsp:
            if not self._vsp.load(self.mp3_path):
                self._vsp = None

        self._pgm_loaded = False
        if self.mp3_path and not (self._vsp and self._vsp.loaded):
            try:
                pygame.mixer.music.load(self.mp3_path)
                self._pgm_loaded = True
                print(f"[pygame.mixer] {self.mp3_path}")
            except Exception as e:
                print(f"[WARN] pygame.mixer: {e}")

        if PITCH_AVAILABLE and self.audio_devices:
            self._start_audio()

        # Cargar config guardada si existe
        self._load_config()

    # ── Config save / load ─────────────────────────────────────────────
    def _save_config(self):
        cfg = {
            "bpm":            self.bpm,
            "mp3_offset_sec": self.mp3_offset_sec,
            "device_idx":     self.device_idx,
            "muted":          self.muted,
        }
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2)
            self._config_msg     = "Config guardada"
            self._config_msg_col = (50, 230, 110)
        except Exception as e:
            self._config_msg     = f"Error al guardar: {e}"
            self._config_msg_col = (255, 70, 70)
        self._config_msg_timer = 2.5

    def _load_config(self):
        self._config_msg       = ""
        self._config_msg_col   = C_GRAY
        self._config_msg_timer = 0.0
        if not os.path.exists(CONFIG_PATH):
            return
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            self.bpm            = float(cfg.get("bpm",            self.bpm))
            self.mp3_offset_sec = float(cfg.get("mp3_offset_sec", self.mp3_offset_sec))
            self.muted          = bool( cfg.get("muted",          self.muted))
            saved_dev           = int(  cfg.get("device_idx",     self.device_idx))
            if 0 <= saved_dev < len(self.audio_devices):
                self.device_idx = saved_dev
            print(f"[Config] cargada  BPM={self.bpm}  offset={self.mp3_offset_sec:+.2f}s")
        except Exception as e:
            print(f"[Config WARN] {e}")

    # ── Notas ──────────────────────────────────────────────────────────
    def _load_notes(self):
        if not os.path.exists(MUSICXML_PATH):
            print(f"[ERROR] MusicXML no encontrado: {MUSICXML_PATH}")
            return
        try:
            notes, sections, bpm = parse_musicxml(MUSICXML_PATH)
            self.notes    = notes
            self.sections = sections
            self.bpm      = bpm
            for n in notes:
                sec = n["section"]
                if sec not in self.section_stats:
                    self.section_stats[sec] = {"ok": 0, "total": 0}
            print(f"[OK] MusicXML: {len(notes)} notas, {bpm} BPM")
        except Exception as e:
            print(f"[ERROR] MusicXML: {e}")
            import traceback; traceback.print_exc()

    def _find_mp3(self):
        base = os.path.dirname(os.path.abspath(__file__))
        for folder in [os.path.join(base, "cancion"), base]:
            if os.path.isdir(folder):
                for f in os.listdir(folder):
                    if f.lower().endswith(".mp3"):
                        return os.path.join(folder, f)
        return None

    # ── Audio / Pitch ───────────────────────────────────────────────────
    def _enumerate_devices(self):
        if not PA_OK:
            return
        p = pyaudio.PyAudio()
        for i in range(p.get_device_count()):
            info = p.get_device_info_by_index(i)
            if info.get("maxInputChannels", 0) > 0:
                self.audio_devices.append((i, info["name"]))
        p.terminate()

    def _start_audio(self, list_idx=None):
        self.audio_running = False
        if self.audio_thread and self.audio_thread.is_alive():
            self.audio_thread.join(timeout=1.5)
        if list_idx is not None:
            self.device_idx = list_idx % len(self.audio_devices)
        self.audio_running = True
        self.audio_thread  = threading.Thread(target=self._audio_loop, daemon=True)
        self.audio_thread.start()

    def _audio_loop(self):
        from collections import deque

        # ── Intentar cargar torchcrepe (IA); si falla, usar aubio ──────
        _use_crepe = False
        _tc        = None
        _torch     = None
        _device    = "cpu"
        try:
            import torch as _torch
            import torchcrepe as _tc
            _use_crepe = True
            _device    = "cuda" if _torch.cuda.is_available() else "cpu"
            print(f"[pitch] torchcrepe CREPE-tiny ({_device})")
            self.pitch_engine = f"CREPE ({_device.upper()})"
        except ImportError:
            print("[pitch] torchcrepe no disponible → aubio yinfast")
            self.pitch_engine = "aubio YINfast"

        dev_id  = self.audio_devices[self.device_idx][0]

        # Buffer rodante de audio (WIN_S muestras = ~186 ms a 44100 Hz)
        audio_buf = np.zeros(WIN_S, dtype=np.float32)

        # Umbral de confianza adaptado a cada motor:
        # CREPE periodicity: graves ~0.1-0.6; se sube para reducir armónicos falsos
        _crepe_thresh = 0.18
        _aubio_thresh = CONF_THRESH
        # Umbral de RMS mínimo — por debajo es silencio / ruido de fondo
        _rms_gate = 0.008

        # Aubio (fallback)
        _pitch_o = None
        if not _use_crepe:
            _pitch_o = aubio.pitch("yinfast", WIN_S, HOP_S, SAMPLERATE)
            _pitch_o.set_unit("Hz")
            _pitch_o.set_tolerance(0.8)

        p          = pyaudio.PyAudio()
        pitch_buf  = deque(maxlen=9)   # mediana de más frames → más estable ante armónicos
        hold_count = 0

        try:
            stream = p.open(format=pyaudio.paFloat32, channels=1, rate=SAMPLERATE,
                            input=True, input_device_index=dev_id,
                            frames_per_buffer=CHUNK_SIZE)
            while self.audio_running:
                try:
                    data    = stream.read(CHUNK_SIZE, exception_on_overflow=False)
                    samples = np.frombuffer(data, dtype=np.float32).copy()

                    # Actualizar buffer rodante (shift + append)
                    audio_buf[:-CHUNK_SIZE] = audio_buf[CHUNK_SIZE:]
                    audio_buf[-CHUNK_SIZE:] = samples

                    if _use_crepe:
                        # Gate de RMS: descarta silencio antes de llamar a CREPE
                        rms = float(np.sqrt(np.mean(audio_buf ** 2)))
                        if rms < _rms_gate:
                            hold_count += 1
                            with self.pitch_lock:
                                if hold_count >= PITCH_HOLD_FRAMES:
                                    pitch_buf.clear()
                                    self.detected_hz   = 0.0
                                    self.detected_note = "—"
                            continue

                        audio_t = _torch.from_numpy(audio_buf).unsqueeze(0)
                        with _torch.no_grad():
                            freq, period = _tc.predict(
                                audio_t, SAMPLERATE,
                                hop_length=512,
                                fmin=32.70, fmax=MAX_HZ,
                                model="tiny",
                                decoder=_tc.decode.weighted_argmax,
                                return_periodicity=True,
                                device=_device,
                                pad=True,
                            )
                        pitch = float(freq[0, -1].cpu())
                        conf  = float(period[0, -1].cpu())
                        thresh = _crepe_thresh
                    else:
                        pitch  = float(_pitch_o(samples)[0])
                        conf   = float(_pitch_o.get_confidence())
                        thresh = _aubio_thresh

                    if conf > thresh and MIN_HZ <= pitch <= MAX_HZ:
                        pitch_buf.append(pitch)
                        hold_count = 0
                    else:
                        hold_count += 1

                    with self.pitch_lock:
                        if pitch_buf and hold_count < PITCH_HOLD_FRAMES:
                            smoothed = float(np.median(list(pitch_buf)))
                            # Anti-armónico: si la mediana es ~3x o ~2x una lectura
                            # grave reciente, preferir la grave (fundamental real del bajo)
                            graves = [h for h in pitch_buf if h < smoothed * 0.6]
                            if len(graves) >= 2:
                                smoothed = float(np.median(graves))
                            self.detected_hz   = smoothed
                            self.detected_note = hz_to_note_name(smoothed)

                            # ── Nota estable por mayoría (para el juego) ──
                            # Convertir buffer a MIDI redondeado y elegir el más votado
                            from collections import Counter
                            midi_votes = [int(round(12 * math.log2(h / 440) + 69))
                                          for h in pitch_buf if h > MIN_HZ]
                            if midi_votes:
                                counts     = Counter(midi_votes)
                                top_midi, top_count = counts.most_common(1)[0]
                                # Necesita >55% del buffer para "comprometerse"
                                if top_count >= len(pitch_buf) * 0.55:
                                    matching = [h for h in pitch_buf
                                                if int(round(12 * math.log2(h / 440) + 69)) == top_midi]
                                    self.stable_hz   = float(np.median(matching))
                                    self.stable_note = hz_to_note_name(self.stable_hz)
                                # Si no hay mayoría clara, la stable_hz queda como estaba
                        else:
                            pitch_buf.clear()
                            self.detected_hz   = 0.0
                            self.detected_note = "—"
                            self.stable_hz     = 0.0
                            self.stable_note   = "—"
                except Exception as _e:
                    print(f"[audio loop] {_e}")
        finally:
            try:
                stream.stop_stream(); stream.close()
            except Exception:
                pass
            p.terminate()


    # ── Helpers ─────────────────────────────────────────────────────────
    def px_of(self, beat16):
        return int(beat16 * self.px_per_16th)

    def current_note(self):
        return self.notes[self.note_idx] if self.note_idx < len(self.notes) else None

    def _speed_ratio(self):
        return self.bpm / BPM_ORIGINAL

    def _hz_to_fret_string(self, hz):
        """Fret y cuerda más probable para una hz detectada (por frecuencia exacta)."""
        best = None
        best_diff = 999.0
        m_det = 12 * math.log2(hz / 440) + 69
        for s in range(1, 5):
            for f in range(NECK_FRETS + 1):
                m_note = 12 * math.log2(fret_to_hz(f, s) / 440) + 69
                diff   = abs(m_det - m_note)   # distancia MIDI real, sin módulo octava
                if diff < best_diff:
                    best_diff = diff
                    best = (f, s)
        return best if best_diff < 0.75 else None

    # ── Update ──────────────────────────────────────────────────────────
    def update(self, dt):
        if self.counting_down:
            self.countdown_timer += dt
            beat_sec = 60.0 / self.bpm
            if self.countdown_timer >= beat_sec:
                self.countdown_timer -= beat_sec
                self.metro_flash = 1.0
                self.metro_beat  = (4 - self.countdown_beat) % 4
                self.countdown_beat -= 1
                if self.countdown_beat <= 0:
                    self.counting_down = False
                    self._begin_play()
            return

        if not self.playing:
            return

        delta16 = dt * (self.bpm / 60.0) * 4.0
        self.beat_time += delta16

        prev_q = int((self.beat_time - delta16) / 4)
        cur_q  = int(self.beat_time / 4)
        if cur_q > prev_q:
            self.metro_beat  = cur_q % 4
            self.metro_flash = 1.0
        self.metro_flash = max(0.0, self.metro_flash - dt * 5)

        if self.beat_time < 0:
            return

        while self.note_idx < len(self.notes):
            n = self.notes[self.note_idx]
            if self.beat_time >= n["start16"] + n["dur"]:
                self.note_idx += 1
            else:
                break

        cur = self.current_note()
        if cur and PITCH_AVAILABLE:
            with self.pitch_lock:
                det = self.stable_hz   # juego usa la nota estable
            if det > 0 and cur["hz"] > 0:
                match = notes_match(det, cur["hz"])
                sec   = cur["section"]
                self.note_match   = match
                self.score_total += 1
                if match:
                    self.score_ok += 1
                if sec in self.section_stats:
                    self.section_stats[sec]["total"] += 1
                    if match:
                        self.section_stats[sec]["ok"] += 1
            else:
                self.note_match = None
        else:
            self.note_match = None

        CURSOR_X = W // 3
        if cur:
            want_x      = self.px_of(cur["start16"]) - CURSOR_X
            self.target_x = max(0, want_x)
        self.viewport_x += (self.target_x - self.viewport_x) * min(1.0, dt * 9)

        if self.note_idx >= len(self.notes):
            self.playing = False

    # ════════════════════════════════════════════════════════════════════
    #  DRAW
    # ════════════════════════════════════════════════════════════════════
    def draw(self):
        self.screen.fill(C_BG)
        self._draw_header()
        self._draw_tab()
        self._draw_neck()
        self._draw_piano()
        self._draw_note_panel()
        self._draw_metronome()
        self._draw_pitch_panel()
        self._draw_stats_panel()
        self._draw_bottom_bar()
        if self.counting_down:
            self._draw_countdown()
        if self.device_menu_open:
            self._draw_device_menu()
        if self.tuner_open:
            self._draw_tuner()
        pygame.display.flip()

    # ── Header ──────────────────────────────────────────────────────────
    def _draw_header(self):
        pygame.draw.rect(self.screen, C_PANEL, (0, 0, W, HEADER_H))
        pygame.draw.line(self.screen, C_ACCENT, (0, HEADER_H), (W, HEADER_H), 2)

        title = self.font_title.render(
            "Bass Karaoke  –  Feet Don't Fail Me Now  |  Joy Crookes",
            True, C_WHITE)
        self.screen.blit(title, (12, 8))

        bpm_t = self.font_med.render(f"♩ {self.bpm:.0f} BPM", True, C_ACCENT)
        self.screen.blit(bpm_t, (W - 155, 8))

        if self.score_total > 0:
            pct = int(100 * self.score_ok / self.score_total)
            col = C_GREEN if pct > 70 else C_RED if pct < 40 else C_ACCENT
            sc  = self.font_med.render(f"{pct}% ok", True, col)
            self.screen.blit(sc, (W - 320, 8))

        off_col = C_GRAY if self.mp3_offset_sec == 0 else C_BLUE
        speed_str = ""
        if self._vsp and self._vsp.loaded:
            speed_str = f"  x{self._speed_ratio():.2f}"
        engine_str = f"  [{getattr(self, 'pitch_engine', 'aubio')}]"
        off_t = self.font_tiny.render(
            f"offset: {self.mp3_offset_sec:+.2f}s{speed_str}{engine_str}   [ ,/. fino  Shift+,/. grueso ]",
            True, off_col)
        self.screen.blit(off_t, (12, 36))

        state = ("▶ TOCANDO" if self.playing else
                 "⏸ PAUSA"   if self.score_total > 0 else "⏹ STOP")
        st = self.font_tiny.render(state, True,
                                   C_GREEN if self.playing else C_GRAY)
        self.screen.blit(st, (W - 155, 36))

    # ── Tablatura ───────────────────────────────────────────────────────
    def _draw_tab(self):
        CURSOR_X = W // 3

        STR_MARGIN  = 8
        STR_SPACING = (TAB_H - STR_MARGIN * 2) / 3
        STR_Y = {
            1: TAB_Y + STR_MARGIN,
            2: TAB_Y + STR_MARGIN + STR_SPACING,
            3: TAB_Y + STR_MARGIN + STR_SPACING * 2,
            4: TAB_Y + STR_MARGIN + STR_SPACING * 3,
        }

        pygame.draw.rect(self.screen, C_BG2, (0, TAB_Y, W, TAB_H))

        for s, y in STR_Y.items():
            lbl = self.font_small.render(STRING_NAMES[s], True, STRING_COLORS[s])
            self.screen.blit(lbl, (4, int(y) - lbl.get_height() // 2))
            pygame.draw.line(self.screen, STRING_COLORS[s],
                             (28, int(y)), (W, int(y)), STRING_THICK[s])

        # Cursor
        pygame.draw.line(self.screen, C_ACCENT,
                         (CURSOR_X, TAB_Y + 2), (CURSOR_X, TAB_Y + TAB_H - 2), 2)
        pygame.draw.polygon(self.screen, C_ACCENT, [
            (CURSOR_X - 6, TAB_Y + 2),
            (CURSOR_X + 6, TAB_Y + 2),
            (CURSOR_X, TAB_Y + 14)])

        vx       = int(self.viewport_x)
        total16  = (self.notes[-1]["start16"] + self.notes[-1]["dur"]
                    if self.notes else 0)

        prev_meas = -1
        for note in self.notes:
            nx = self.px_of(note["start16"]) - vx + CURSOR_X
            if 30 < nx < W and note["measure_num"] != prev_meas:
                prev_meas = note["measure_num"]
                m = self.font_tiny.render(str(note["measure_num"]), True, C_DGRAY)
                self.screen.blit(m, (nx - m.get_width() // 2, TAB_Y + 2))

        for b in range(0, total16 + 16, 16):
            bx = self.px_of(b) - vx + CURSOR_X
            if 30 < bx < W:
                pygame.draw.line(self.screen, C_DGRAY,
                                 (bx, TAB_Y + 6), (bx, TAB_Y + TAB_H - 6), 1)

        for label, b16 in self.sections:
            sx = self.px_of(b16) - vx + CURSOR_X
            if 30 < sx < W:
                pygame.draw.line(self.screen, C_SECTION, (sx, TAB_Y), (sx, TAB_Y + TAB_H), 1)
                self.screen.blit(
                    self.font_tiny.render(f"[{label}]", True, C_SECTION),
                    (sx + 3, TAB_Y + 3))

        R_CUR  = 14
        R_NORM = 11
        R_PAST = 8

        for i, note in enumerate(self.notes):
            nx = self.px_of(note["start16"]) - vx + CURSOR_X
            if nx < 10 or nx > W + 60:
                continue
            ny      = int(STR_Y[note["string"]])
            is_cur  = (i == self.note_idx)
            is_past = (i < self.note_idx)

            if is_cur:
                col = (C_OK  if self.note_match is True  else
                       C_ERR if self.note_match is False else C_WAIT)
                r   = R_CUR
                pulse = 0.5 + 0.5 * math.sin(time.time() * 9)
                hr    = int(r + 6 + pulse * 3)
                hs    = pygame.Surface((hr * 2, hr * 2), pygame.SRCALPHA)
                pygame.draw.circle(hs, (*col, 45), (hr, hr), hr)
                self.screen.blit(hs, (nx - hr, ny - hr))
            elif is_past:
                col = (38, 38, 60)
                r   = R_PAST
            else:
                col = STRING_COLORS[note["string"]]
                r   = R_NORM

            dur_px = int(note["dur"] * self.px_per_16th) - 2
            if dur_px > r * 2 + 4 and not is_past:
                if is_cur:
                    pygame.draw.line(self.screen, col, (nx, ny), (nx + dur_px, ny), 3)
                else:
                    s = pygame.Surface((dur_px, 3), pygame.SRCALPHA)
                    pygame.draw.line(s, (*col, 90), (0, 1), (dur_px, 1), 3)
                    self.screen.blit(s, (nx, ny - 1))

            pygame.draw.circle(self.screen, col, (nx, ny), r)
            if not is_past:
                pygame.draw.circle(self.screen, C_BG, (nx, ny), r - 3)

            f   = (self.font_med   if is_cur  else
                   self.font_small if not is_past else self.font_tiny)
            txt = f.render(str(note["fret"]), True,
                           col if is_past else C_WHITE)
            self.screen.blit(txt, (nx - txt.get_width() // 2,
                                   ny - txt.get_height() // 2))

        pygame.draw.line(self.screen, C_DGRAY,
                         (0, TAB_Y + TAB_H), (W, TAB_Y + TAB_H), 1)

    # ── Mástil del bajo ─────────────────────────────────────────────────
    def _draw_neck(self):
        nx0 = 0
        nw, nh = NECK_W, NECK_H
        ny = NECK_Y

        # Fondo madera
        pygame.draw.rect(self.screen, C_WOOD, (nx0, ny, nw, nh))
        for i in range(5):
            yx = ny + 8 + i * 18
            pygame.draw.line(self.screen, C_WOOD2, (nx0, yx), (nx0 + nw, yx), 1)

        # Posición Y de las cuerdas (G=top, E=bottom)
        STR_MARG = 14
        ss = (nh - STR_MARG * 2 - 16) / 3   # separación entre cuerdas
        STR_Y = {
            1: ny + STR_MARG,
            2: ny + STR_MARG + ss,
            3: ny + STR_MARG + ss * 2,
            4: ny + STR_MARG + ss * 3,
        }

        fret_space = NECK_AREA_W / NECK_FRETS

        def fret_bar_x(fret):
            return NECK_AREA_X + (fret - 1) * fret_space + fret_space

        def note_x(fret):
            if fret == 0:
                return NECK_NUT_X - 9
            return NECK_AREA_X + (fret - 1) * fret_space + fret_space * 0.5

        # Etiquetas de cuerda
        for s in range(1, 5):
            y   = int(STR_Y[s])
            lbl = self.font_tiny.render(STRING_NAMES[s], True, STRING_COLORS[s])
            self.screen.blit(lbl, (4, y - lbl.get_height() // 2))

        # Cejilla
        pygame.draw.rect(self.screen, C_NUT, (NECK_NUT_X, ny + 4, 5, nh - 8))

        # Barras de traste
        for fret in range(1, NECK_FRETS + 1):
            fx = fret_bar_x(fret)
            if fx <= nx0 + nw:
                pygame.draw.line(self.screen, C_FRET,
                                 (int(fx), ny + 4), (int(fx), ny + nh - 18), 2)

        # Números de traste (abajo del mástil)
        num_y = ny + nh - 12
        for fret in range(0, NECK_FRETS + 1):
            xc = int(note_x(fret))
            if xc < nx0 + nw - 4:
                lbl = self.font_tiny.render(str(fret), True, C_FRET)
                self.screen.blit(lbl, (xc - lbl.get_width() // 2, num_y))

        # Puntos de posición
        for fret in NECK_DOT_FRETS:
            xc = int(note_x(fret))
            yc = int((STR_Y[2] + STR_Y[3]) / 2)
            if xc < nx0 + nw - 4:
                pygame.draw.circle(self.screen, C_DOT, (xc, yc), 5)
        for fret in NECK_OCT_FRETS:
            xc = int(note_x(fret))
            y1 = int((STR_Y[1] + STR_Y[2]) / 2)
            y2 = int((STR_Y[3] + STR_Y[4]) / 2)
            if xc < nx0 + nw - 4:
                pygame.draw.circle(self.screen, C_DOT, (xc, y1), 5)
                pygame.draw.circle(self.screen, C_DOT, (xc, y2), 5)

        # Cuerdas (líneas)
        for s in range(1, 5):
            y    = int(STR_Y[s])
            col  = STRING_COLORS[s]
            tick = STRING_THICK[s]
            pygame.draw.line(self.screen, col,
                             (NECK_NUT_X + 5, y), (nx0 + nw - 6, y), tick)
            pygame.draw.line(self.screen, col,
                             (nx0 + NECK_LABEL_W, y), (NECK_NUT_X, y), tick)

        # ── Nota esperada (rellena) ────────────────────────────────────
        cur = self.current_note()
        if cur:
            xc = int(note_x(cur["fret"]))
            yc = int(STR_Y[cur["string"]])
            if xc <= nx0 + nw - 4:
                col_c = (C_OK  if self.note_match is True  else
                         C_ERR if self.note_match is False else C_WAIT)
                pulse = 0.5 + 0.5 * math.sin(time.time() * 8)
                hr    = int(11 + pulse * 4)
                hs    = pygame.Surface((hr * 2, hr * 2), pygame.SRCALPHA)
                pygame.draw.circle(hs, (*col_c, 75), (hr, hr), hr)
                self.screen.blit(hs, (xc - hr, yc - hr))
                pygame.draw.circle(self.screen, col_c, (xc, yc), 11)
                txt = self.font_small.render(str(cur["fret"]), True, C_BG)
                self.screen.blit(txt, (xc - txt.get_width() // 2,
                                       yc - txt.get_height() // 2))

        # ── Nota detectada (contorno azul) ─────────────────────────────
        with self.pitch_lock:
            det_hz = self.stable_hz   # mástil usa nota estable
        if det_hz > MIN_HZ:
            best = self._hz_to_fret_string(det_hz)
            if best:
                df, ds = best
                xc = int(note_x(df))
                yc = int(STR_Y[ds])
                if xc <= nx0 + nw - 4:
                    pygame.draw.circle(self.screen, C_BLUE, (xc, yc), 9, 2)

        pygame.draw.rect(self.screen, C_DGRAY, (nx0, ny, nw, nh), 1)

        # Título del panel
        lbl_n = self.font_tiny.render("MASTIL DEL BAJO  (trastes 0–15)", True, C_GRAY)
        self.screen.blit(lbl_n, (nx0 + 4, ny - 13))

    # ── Piano ───────────────────────────────────────────────────────────
    def _draw_piano(self):
        px, py, pw, ph = PIANO_X, PIANO_Y, PIANO_W, PIANO_H

        if not self._piano_keys_list:
            self._piano_keys_list = build_piano_keys(
                PIANO_START_MIDI, PIANO_END_MIDI, px, py, pw, ph)

        pygame.draw.rect(self.screen, (12, 12, 20), (px, py, pw, ph))

        cur = self.current_note()
        cur_pc  = int(round(12 * math.log2(cur["hz"] / 440) + 69)) % 12 if cur else -1

        with self.pitch_lock:
            det_hz = self.stable_hz   # mástil usa nota estable
        # MIDI exacto para la nota detectada → octava correcta en el piano
        det_midi = int(round(12 * math.log2(det_hz / 440) + 69)) if det_hz > MIN_HZ else -999

        col_cur = (C_OK  if self.note_match is True  else
                   C_ERR if self.note_match is False else C_WAIT)

        for key in self._piano_keys_list:
            midi  = key["midi"]
            rect  = key["rect"]
            black = key["black"]
            pc    = midi % 12
            is_cur = (pc == cur_pc) and cur is not None
            is_det = (midi == det_midi) and det_hz > MIN_HZ

            if is_cur:
                color = col_cur
            elif is_det:
                color = C_BLUE
            elif black:
                color = (20, 20, 30)
            else:
                color = (215, 215, 225)

            pygame.draw.rect(self.screen, color, rect)
            border = (40, 40, 60) if black else (85, 85, 105)
            pygame.draw.rect(self.screen, border, rect, 1)

            # Etiqueta C en cada octava (tecla blanca)
            if not black and midi % 12 == 0:
                oct_n = midi // 12 - 1
                lbl   = self.font_tiny.render(f"C{oct_n}", True,
                                              C_BG if (is_cur or is_det) else C_DGRAY)
                self.screen.blit(lbl, (rect.x + 1, rect.bottom - 14))

        pygame.draw.rect(self.screen, C_DGRAY, (px, py, pw, ph), 1)
        lbl_p = self.font_tiny.render(
            f"PIANO  E1–Eb4  (midi {PIANO_START_MIDI}–{PIANO_END_MIDI})",
            True, C_GRAY)
        self.screen.blit(lbl_p, (px + 4, py - 13))

    # ── Panel nota actual ────────────────────────────────────────────────
    def _draw_note_panel(self):
        px, py, pw, ph = 8, LOWER_Y, 205, LOWER_H
        pygame.draw.rect(self.screen, C_PANEL, (px, py, pw, ph), border_radius=10)
        pygame.draw.rect(self.screen, C_ACCENT, (px, py, pw, ph), 2, border_radius=10)

        hdr = self.font_tiny.render("SIGUIENTE NOTA", True, C_GRAY)
        self.screen.blit(hdr, (px + pw // 2 - hdr.get_width() // 2, py + 6))

        cur = self.current_note()
        if not cur:
            t = self.font_big.render("FIN!", True, C_GREEN)
            self.screen.blit(t, (px + pw // 2 - t.get_width() // 2,
                                 py + ph // 2 - 20))
            return

        fret_big = self.font_huge.render(str(cur["fret"]), True, C_ACCENT)
        self.screen.blit(fret_big, (px + pw // 2 - fret_big.get_width() // 2, py + 16))

        scol  = STRING_COLORS[cur["string"]]
        s_lbl = self.font_med.render(
            f"Cuerda {STRING_NAMES[cur['string']]}", True, scol)
        self.screen.blit(s_lbl, (px + pw // 2 - s_lbl.get_width() // 2, py + 102))

        n_lbl = self.font_small.render(cur["note_name"], True, C_BLUE)
        self.screen.blit(n_lbl, (px + pw // 2 - n_lbl.get_width() // 2, py + 128))

        sec = self.font_tiny.render(cur["section"], True, C_GRAY)
        self.screen.blit(sec, (px + pw // 2 - sec.get_width() // 2, py + 152))

    # ── Metrónomo ────────────────────────────────────────────────────────
    def _draw_metronome(self):
        mx, my, bw = 220, LOWER_Y + 4, 42
        lbl = self.font_tiny.render("METRO", True, C_GRAY)
        self.screen.blit(lbl, (mx, my - 13))
        for b in range(4):
            bx      = mx + b * (bw + 4)
            active  = (self.playing or self.counting_down) and (b == self.metro_beat)
            c = C_ACCENT if (active and b == 0) else C_WHITE if active else C_DGRAY
            pygame.draw.rect(self.screen, c, (bx, my, bw, 28), border_radius=5)
            if b == 0:
                pygame.draw.rect(self.screen, C_ACCENT, (bx, my, bw, 28), 2, border_radius=5)
            n = self.font_med.render(str(b + 1), True, C_BG if active else C_GRAY)
            self.screen.blit(n, (bx + bw // 2 - n.get_width() // 2, my + 4))

    # ── Panel pitch ──────────────────────────────────────────────────────
    def _draw_pitch_panel(self):
        px, py, pw, ph = 220, LOWER_Y + 38, 634, 154
        pygame.draw.rect(self.screen, C_PANEL, (px, py, pw, ph), border_radius=10)

        with self.pitch_lock:
            det_hz   = self.detected_hz    # crudo para panel de pitch
            det_note = self.detected_note
            stb_hz   = self.stable_hz      # estable para juego / display principal
            stb_note = self.stable_note
        cur = self.current_note()

        if PITCH_AVAILABLE and self.audio_devices:
            dev_name = self.audio_devices[self.device_idx][1][:44]
            t = self.font_tiny.render(
                f"ENTRADA [{self.device_idx}]: {dev_name}  |  D=cambiar",
                True, C_GRAY)
        else:
            t = self.font_tiny.render("pip install pyaudio aubio", True, C_RED)
        self.screen.blit(t, (px + 10, py + 8))

        col  = (C_OK  if self.note_match is True  else
                C_ERR if self.note_match is False else C_GRAY)
        # Nota estable (grande) — es la que usa el juego
        big  = self.font_big.render(stb_note, True, col)
        self.screen.blit(big, (px + 10, py + 24))
        # Nota cruda (pequeña, gris) — sólo informativa
        if det_hz > 0 and det_note != stb_note:
            raw_t = self.font_tiny.render(f"crudo: {det_note}", True, C_DGRAY)
            self.screen.blit(raw_t, (px + 10, py + 62))

        if stb_hz > 0:
            hz_t = self.font_small.render(f"{stb_hz:.1f} Hz", True, C_GRAY)
            self.screen.blit(hz_t, (px + 10, py + 72))

        if cur:
            exp = self.font_small.render(
                f"Esperada: {cur['note_name']}  (tr.{cur['fret']} Cuerda {STRING_NAMES[cur['string']]})",
                True, C_WHITE)
            self.screen.blit(exp, (px + 10, py + 116))

        if self.note_match is True:
            self.screen.blit(self.font_big.render("OK!", True, C_OK),
                             (px + 160, py + 28))
        elif self.note_match is False:
            self.screen.blit(self.font_big.render("Ajusta",True, C_ERR),
                             (px + 160, py + 28))

        if PITCH_AVAILABLE and cur and stb_hz > 0 and cur["hz"] > 0:
            ratio = stb_hz / cur["hz"]
            if ratio > 0:
                cents = 1200 * math.log2(ratio)
                while cents >  600: cents -= 1200
                while cents < -600: cents += 1200
                cents_c = max(-120, min(120, cents))
                bx, by2, bw2, bh = px + 160, py + 75, 450, 13
                pygame.draw.rect(self.screen, C_DGRAY, (bx, by2, bw2, bh), border_radius=3)
                cx = bx + bw2 // 2
                mk = cx + int(cents_c / 120 * (bw2 // 2))
                bc = C_OK if abs(cents) < 20 else C_ACCENT if abs(cents) < 60 else C_ERR
                if mk != cx:
                    pygame.draw.rect(self.screen, bc,
                                     (min(cx, mk), by2 + 2, abs(mk - cx) + 2, bh - 4),
                                     border_radius=2)
                pygame.draw.line(self.screen, C_WHITE, (cx, by2), (cx, by2 + bh), 2)
                self.screen.blit(
                    self.font_tiny.render(f"{cents:+.0f} cents", True, C_GRAY),
                    (bx, by2 + bh + 3))

    # ── Stats por sección ────────────────────────────────────────────────
    def _draw_stats_panel(self):
        px, py, pw, ph = 860, LOWER_Y, 412, LOWER_H
        pygame.draw.rect(self.screen, C_PANEL, (px, py, pw, ph), border_radius=10)

        hdr = self.font_tiny.render("ACIERTOS POR SECCION", True, C_GRAY)
        self.screen.blit(hdr, (px + 8, py + 6))

        with_data = [(s, d) for s, d in self.section_stats.items() if d["total"] > 0]
        if not with_data:
            with_data = list(self.section_stats.items())[:10]

        max_vis = 10
        with_data = with_data[-max_vis:]
        row_h    = max(14, min(18, (ph - 26) // max(len(with_data), 1)))

        for idx, (sec, d) in enumerate(with_data):
            ry = py + 22 + idx * row_h
            lbl = self.font_tiny.render(sec[:18], True, C_GRAY)
            self.screen.blit(lbl, (px + 6, ry))
            bx, bw2, bh = px + 148, 196, 9
            pygame.draw.rect(self.screen, C_DGRAY, (bx, ry + 2, bw2, bh), border_radius=2)
            if d["total"] > 0:
                pct    = d["ok"] / d["total"]
                fw     = int(bw2 * pct)
                bc     = C_GREEN if pct > 0.70 else C_ACCENT if pct > 0.40 else C_RED
                if fw > 0:
                    pygame.draw.rect(self.screen, bc,
                                     (bx, ry + 2, fw, bh), border_radius=2)
                self.screen.blit(
                    self.font_tiny.render(f"{int(pct*100):3d}%", True, bc),
                    (bx + bw2 + 4, ry))

    # ── Bottom bar ───────────────────────────────────────────────────────
    def _draw_bottom_bar(self):
        pygame.draw.rect(self.screen, C_PANEL, (0, BOTTOM_Y, W, H - BOTTOM_Y))
        pygame.draw.line(self.screen, C_DGRAY, (0, BOTTOM_Y), (W, BOTTOM_Y), 1)

        hints = [
            ("SPC", "Play"), ("R","Reinicio"), ("↑↓","Tempo"),
            (",.", "offset±0.05"), ("S+,.","offset±0.5"),
            ("D","Disp"), ("T","Tuner"), ("M","Mute"),
            ("F5","Guardar"), ("F6","Cargar"), ("ESC","Salir"),
        ]
        x = 8
        for key, desc in hints:
            k = self.font_small.render(key, True, C_ACCENT)
            d = self.font_small.render(f" {desc}  ", True, C_GRAY)
            self.screen.blit(k, (x, BOTTOM_Y + 7))
            x += k.get_width()
            self.screen.blit(d, (x, BOTTOM_Y + 7))
            x += d.get_width()

        if self.mp3_path:
            engine = " [varispeed]" if (self._vsp and self._vsp.loaded) else " [fixed]"
            sfx    = " [MUTE]" if self.muted else " ♫"
            col    = C_GREEN if not self.muted else C_GRAY
            mp3s   = os.path.basename(self.mp3_path) + sfx + engine
        else:
            col  = C_RED
            mp3s = "MP3 no encontrado"
        self.screen.blit(self.font_small.render(mp3s, True, col), (8, BOTTOM_Y + 30))

        src = self.font_tiny.render(
            f"MusicXML: {len(self.notes)} notas",
            True, C_GRAY if self.notes else C_RED)
        self.screen.blit(src, (W - src.get_width() - 8, BOTTOM_Y + 34))

        # Mensaje temporal de config guardada/cargada
        if getattr(self, '_config_msg_timer', 0) > 0:
            msg = self.font_med.render(self._config_msg, True, self._config_msg_col)
            self.screen.blit(msg,
                             (W // 2 - msg.get_width() // 2, BOTTOM_Y + 14))

    # ── Tuner ────────────────────────────────────────────────────────────
    def _draw_tuner(self):
        """
        Afinador cromático a pantalla completa (overlay):
        - Nota detectada grande en el centro
        - Barra de cents con zona verde ±15 cents
        - Las 4 notas al aire del bajo como referencia rápida
        """
        ov = pygame.Surface((W, H), pygame.SRCALPHA)
        ov.fill((5, 5, 18, 235))
        self.screen.blit(ov, (0, 0))

        # Título
        t = self.font_med.render("AFINADOR  —  T para cerrar", True, C_GRAY)
        self.screen.blit(t, (W // 2 - t.get_width() // 2, 30))

        with self.pitch_lock:
            det_hz   = self.detected_hz
            det_note = self.detected_note

        # ── Calcular cents respecto a la nota temperada más cercana ──
        cents    = 0.0
        ref_note = "—"
        ref_hz   = 0.0
        in_tune  = False
        if det_hz > MIN_HZ:
            midi_f   = 12 * math.log2(det_hz / 440.0) + 69
            midi_r   = round(midi_f)
            cents    = (midi_f - midi_r) * 100
            ref_hz   = 440.0 * (2 ** ((midi_r - 69) / 12))
            names    = ['C','C#','D','D#','E','F','F#','G','G#','A','A#','B']
            ref_note = f"{names[midi_r % 12]}{midi_r // 12 - 1}"
            in_tune  = abs(cents) < 15

        # ── Nota grande ──────────────────────────────────────────────
        col_note = C_GREEN if in_tune else C_ACCENT if det_hz > MIN_HZ else C_DGRAY
        big = pygame.font.SysFont("consolas", 130, bold=True).render(
            ref_note if det_hz > MIN_HZ else "—", True, col_note)
        self.screen.blit(big, (W // 2 - big.get_width() // 2, H // 2 - 130))

        if det_hz > MIN_HZ:
            hz_s = self.font_small.render(f"{det_hz:.2f} Hz", True, C_GRAY)
            self.screen.blit(hz_s, (W // 2 - hz_s.get_width() // 2, H // 2 + 20))

        # ── Barra de cents ────────────────────────────────────────────
        bw, bh  = 600, 22
        bx      = W // 2 - bw // 2
        by      = H // 2 + 60
        pygame.draw.rect(self.screen, C_DGRAY, (bx, by, bw, bh), border_radius=5)

        # Zona verde central (±15 cents → ±15/100*bw/2 px)
        green_half = int(bw / 2 * 15 / 100)
        pygame.draw.rect(self.screen, (20, 80, 30),
                         (bx + bw // 2 - green_half, by, green_half * 2, bh),
                         border_radius=3)

        # Línea central
        pygame.draw.line(self.screen, C_WHITE,
                         (bx + bw // 2, by), (bx + bw // 2, by + bh), 2)

        if det_hz > MIN_HZ:
            # Aguja (cents va de -50 a +50)
            c_clip   = max(-50, min(50, cents))
            needle_x = bx + bw // 2 + int(c_clip / 50 * (bw // 2))
            n_col    = C_GREEN if in_tune else C_ERR
            pygame.draw.rect(self.screen, n_col,
                             (needle_x - 4, by - 4, 8, bh + 8), border_radius=3)
            cents_s = self.font_med.render(f"{cents:+.1f} cents", True, n_col)
            self.screen.blit(cents_s, (W // 2 - cents_s.get_width() // 2, by + bh + 8))

        # Etiquetas -50 / 0 / +50
        for label, rx in [("-50", bx + 4), ("0", bx + bw // 2 - 8), ("+50", bx + bw - 26)]:
            self.screen.blit(self.font_tiny.render(label, True, C_GRAY), (rx, by + bh + 2))

        # ── Cuerdas al aire del bajo como referencia ──────────────────
        ref_y = by + bh + 40
        self.screen.blit(
            self.font_small.render("Referencia cuerdas al aire:", True, C_GRAY),
            (W // 2 - 140, ref_y))
        open_notes = [(4, "E1", 41.20), (3, "A1", 55.00), (2, "D2", 73.42), (1, "G2", 98.00)]
        spacing    = 130
        start_x    = W // 2 - spacing * 3 // 2 - 30
        for i, (s, name, hz) in enumerate(open_notes):
            sx  = start_x + i * spacing
            sy  = ref_y + 22
            col = STRING_COLORS[s]
            pygame.draw.rect(self.screen, C_PANEL, (sx - 2, sy - 2, 100, 46), border_radius=6)
            pygame.draw.rect(self.screen, col,     (sx - 2, sy - 2, 100, 46), 2, border_radius=6)
            n_lbl = self.font_big.render(name, True, col)
            self.screen.blit(n_lbl, (sx + 50 - n_lbl.get_width() // 2, sy + 2))
            h_lbl = self.font_tiny.render(f"{hz:.2f} Hz", True, C_GRAY)
            self.screen.blit(h_lbl, (sx + 50 - h_lbl.get_width() // 2, sy + 32))

    # ── Countdown ────────────────────────────────────────────────────────
    def _draw_countdown(self):
        ov = pygame.Surface((W, H), pygame.SRCALPHA)
        ov.fill((0, 0, 0, 140))
        self.screen.blit(ov, (0, 0))
        num = self.font_huge.render(str(self.countdown_beat), True, C_ACCENT)
        self.screen.blit(num, (W // 2 - num.get_width() // 2,
                                H // 2 - num.get_height() // 2 - 20))
        sub = self.font_med.render("preparado...", True, C_GRAY)
        self.screen.blit(sub, (W // 2 - sub.get_width() // 2,
                                H // 2 + num.get_height() // 2 - 10))

    # ── Menú dispositivos ────────────────────────────────────────────────
    def _draw_device_menu(self):
        mw, mh = 680, 360
        mx, my = W // 2 - mw // 2, H // 2 - mh // 2

        ov = pygame.Surface((W, H), pygame.SRCALPHA)
        ov.fill(C_OVERLAY)
        self.screen.blit(ov, (0, 0))

        pygame.draw.rect(self.screen, C_PANEL,  (mx, my, mw, mh), border_radius=12)
        pygame.draw.rect(self.screen, C_ACCENT, (mx, my, mw, mh), 2, border_radius=12)

        hdr = self.font_med.render("SELECCIONA DISPOSITIVO DE ENTRADA", True, C_ACCENT)
        self.screen.blit(hdr, (mx + mw // 2 - hdr.get_width() // 2, my + 14))
        pygame.draw.line(self.screen, C_DGRAY,
                         (mx + 10, my + 42), (mx + mw - 10, my + 42), 1)

        if not self.audio_devices:
            self.screen.blit(
                self.font_med.render("No se encontraron dispositivos", True, C_RED),
                (mx + 20, my + 80))
        else:
            row_h    = 28
            max_rows = (mh - 78) // row_h
            start    = max(0, self.device_menu_sel - max_rows + 1)
            for i, (_, name) in enumerate(self.audio_devices):
                if i < start: continue
                if i - start >= max_rows: break
                ry     = my + 50 + (i - start) * row_h
                is_sel = (i == self.device_menu_sel)
                is_cur = (i == self.device_idx)
                if is_sel:
                    pygame.draw.rect(self.screen, C_DGRAY,
                                     (mx + 6, ry - 2, mw - 12, row_h - 2),
                                     border_radius=4)
                col = C_GREEN if is_cur else C_WHITE if is_sel else C_GRAY
                lbl = self.font_small.render(
                    f"{'●' if is_cur else ' '} [{i}] {name[:56]}", True, col)
                self.screen.blit(lbl, (mx + 12, ry))

        hint = self.font_tiny.render(
            "↑↓ navegar    ENTER confirmar    ESC / D  cerrar",
            True, C_GRAY)
        self.screen.blit(hint, (mx + mw // 2 - hint.get_width() // 2, my + mh - 22))

    # ════════════════════════════════════════════════════════════════════
    #  CONTROLES
    # ════════════════════════════════════════════════════════════════════
    def toggle_play(self):
        if self.counting_down:
            self.counting_down = False
            return
        if self.playing:
            self.playing = False
            self._music_pause()
        else:
            self.counting_down   = True
            self.countdown_beat  = 4
            self.countdown_timer = 0.0
            self.metro_beat      = 0

    def _begin_play(self):
        self.playing   = True
        offset_sec     = self.mp3_offset_sec
        self.beat_time = -(offset_sec * (self.bpm / 60.0) * 4.0)
        is_fresh       = (self.note_idx == 0 and self.score_total == 0)

        if self._vsp and self._vsp.loaded:
            self._vsp.set_speed(self._speed_ratio())
            if is_fresh:
                self._vsp.play(offset_sec=max(0.0, offset_sec))
            else:
                self._vsp.resume()
        elif self._pgm_loaded:
            if is_fresh:
                pygame.mixer.music.play()
            else:
                try:
                    pygame.mixer.music.unpause()
                except Exception:
                    pygame.mixer.music.play()

    def _music_pause(self):
        if self._vsp and self._vsp.loaded:
            self._vsp.pause()
        elif self._pgm_loaded:
            pygame.mixer.music.pause()

    def _music_stop(self):
        if self._vsp and self._vsp.loaded:
            self._vsp.stop()
        elif self._pgm_loaded:
            pygame.mixer.music.stop()

    def restart(self):
        self.playing        = False
        self.counting_down  = False
        self.note_idx       = 0
        self.beat_time      = 0.0
        self.viewport_x     = 0.0
        self.target_x       = 0.0
        self.score_ok       = 0
        self.score_total    = 0
        self.note_match     = None
        self.metro_beat     = 0
        self.metro_flash    = 0.0
        for sec in self.section_stats:
            self.section_stats[sec] = {"ok": 0, "total": 0}
        self._music_stop()

    def change_bpm(self, d):
        self.bpm = max(40, min(220, self.bpm + d))
        if self._vsp and self._vsp.loaded and self._vsp.is_playing:
            self._vsp.set_speed(self._speed_ratio())

    def change_offset(self, d):
        self.mp3_offset_sec = round(self.mp3_offset_sec + d, 3)

    def toggle_mute(self):
        self.muted = not self.muted
        vol = 0.0 if self.muted else 1.0
        if self._vsp and self._vsp.loaded:
            self._vsp.set_volume(vol)
        elif self._pgm_loaded:
            pygame.mixer.music.set_volume(vol)

    def open_device_menu(self):
        self.device_menu_open = True
        self.device_menu_sel  = self.device_idx

    def close_device_menu(self):
        self.device_menu_open = False

    def confirm_device(self):
        if not self.audio_devices:
            return
        if PITCH_AVAILABLE:
            self._start_audio(self.device_menu_sel)
        self.close_device_menu()

    # ════════════════════════════════════════════════════════════════════
    #  LOOP PRINCIPAL
    # ════════════════════════════════════════════════════════════════════
    def run(self):
        last    = time.time()
        running = True

        while running:
            now  = time.time()
            dt   = min(now - last, 0.05)
            last = now

            mods  = pygame.key.get_mods()
            shift = bool(mods & pygame.KMOD_SHIFT)

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False

                elif event.type == pygame.KEYDOWN:
                    k = event.key

                    # ── Menú dispositivos ─────────────────────────────
                    if self.device_menu_open:
                        if k in (pygame.K_ESCAPE, pygame.K_d):
                            self.close_device_menu()
                        elif k == pygame.K_UP:
                            self.device_menu_sel = max(0, self.device_menu_sel - 1)
                        elif k == pygame.K_DOWN:
                            self.device_menu_sel = min(
                                len(self.audio_devices) - 1,
                                self.device_menu_sel + 1)
                        elif k in (pygame.K_RETURN, pygame.K_KP_ENTER):
                            self.confirm_device()
                        continue

                    # ── Controles principales ─────────────────────────
                    if   k == pygame.K_ESCAPE:
                        if self.tuner_open:
                            self.tuner_open = False
                        else:
                            running = False
                    elif k == pygame.K_SPACE:  self.toggle_play()
                    elif k == pygame.K_r:      self.restart()
                    elif k == pygame.K_UP:     self.change_bpm(+5)
                    elif k == pygame.K_DOWN:   self.change_bpm(-5)
                    elif k == pygame.K_m:      self.toggle_mute()
                    elif k == pygame.K_d:      self.open_device_menu()
                    elif k == pygame.K_t:      self.tuner_open = not self.tuner_open
                    elif k == pygame.K_F5:     self._save_config()
                    elif k == pygame.K_F6:
                        self._load_config()
                        self._config_msg       = "Config cargada"
                        self._config_msg_col   = C_BLUE
                        self._config_msg_timer = 2.5

                    # ── Offset fino / grueso ──────────────────────────
                    elif k in (pygame.K_COMMA, pygame.K_LESS):
                        self.change_offset(-0.5 if shift else -0.05)
                    elif k in (pygame.K_PERIOD, pygame.K_GREATER):
                        self.change_offset(+0.5 if shift else +0.05)

            # Tick del mensaje de config
            if getattr(self, '_config_msg_timer', 0) > 0:
                self._config_msg_timer = max(0.0, self._config_msg_timer - dt)

            self.update(dt)
            self.draw()
            self.clock.tick(FPS)

        self.audio_running = False
        if self._vsp and self._vsp.loaded:
            self._vsp.stop()
        pygame.quit()


# ═══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("=" * 64)
    print("  BASS KARAOKE v3  –  Feet Don't Fail Me Now | Joy Crookes")
    print("=" * 64)
    print(f"  PyAudio   : {'OK' if PA_OK    else 'NO  pip install pyaudio'}")
    print(f"  Aubio     : {'OK' if AUBIO_OK else 'NO  pip install aubio'}")
    print(f"  Varispeed : {'OK (librosa+sounddevice)' if VARSPEED_OK else 'NO (tempo MP3 fijo)'}")
    print(f"  MusicXML  : {MUSICXML_PATH}")
    print("=" * 64)
    BassKaraoke().run()
