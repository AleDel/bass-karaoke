"""
BassKaraoke — clase principal orquestadora.
Importa toda la lógica desde los submódulos del paquete.
"""

import json
import logging
import math
import os
import threading
import time

import pygame

from . import features
from .chords import is_rest_chord, load_song_barlen, load_song_map, save_song_map
from .config import (
    BPM_DEFAULT,
    BPM_ORIGINAL,
    C_ACCENT,
    C_BG,
    C_BLUE,
    C_DGRAY,
    C_ERR,
    C_GRAY,
    C_GREEN,
    C_OK,
    C_PANEL,
    C_RED,
    C_WAIT,
    C_WHITE,
    CONFIG_PATH,
    HEADER_H,
    KARAOKE_H,
    KARAOKE_Y,
    MIN_HZ,
    MUSICXML_PATH,
    NECK_AREA_W,
    NECK_AREA_X,
    NECK_FRETS,
    NECK_H,
    NECK_W,
    NECK_Y,
    PIANO_END_MIDI,
    PIANO_H,
    PIANO_START_MIDI,
    PIANO_W,
    PIANO_X,
    PIANO_Y,
    PITCH_METHODS,
    SAMPLERATE,
    SONGS_DIR,
    STRING_NAMES,
    TG_PATH,
    H,
    W,
)
from .corridos import bajeo_matches
from .parser import parse_grace_notes, parse_musicxml
from .utils import fret_to_hz, hz_to_note_name, notes_match
from .view_state import ViewState
from .walking import beat_matches

features.ensure_on_path()
from .audio import (
    INPUT_AVAILABLE,
    VARSPEED_OK,
    PitchEngine,
    VarispeedPlayer,
    band_available,
    band_midi_available,
    render_band_midi,
    bass_backend,
    enumerate_devices,
    load_mp3_samples,
    render_band,
    render_bass,
    to_int16,
)
from .audio.bass_track import hz_to_midi as _bass_hz_to_midi
from .score import (
    CAIROSVG_OK,
    MUSIC21_OK,
    VEROVIO_OK,
    init_score_surface,
    init_score_surface_music21,
)
from .ui import (
    draw_arp,
    draw_bottom_bar,
    draw_chord_editor_popup,
    draw_corrido_panel,
    draw_countdown,
    draw_device_menu,
    draw_ear,
    draw_feature_menu,
    draw_guitartab,
    draw_help,
    draw_karaoke_strip,
    draw_lab_panel,
    draw_metronome,
    draw_mixer,
    draw_neck,
    draw_note_panel,
    draw_piano,
    draw_pitch_menu,
    draw_pitch_panel,
    draw_scale,
    draw_score,
    draw_song_menu,
    draw_stats_panel,
    draw_tab,
    draw_tech,
    draw_training,
    draw_tuner,
    draw_waveform_strip,
)

FPS = 60

# Nombre en español de cada figura del metrónomo (MusicXML beat-unit)
FIGURE_NAMES = {
    "whole": "redonda", "half": "blanca", "quarter": "negra",
    "eighth": "corchea", "16th": "semicorchea",
    "32nd": "fusa", "64th": "semifusa",
}

# Escalado suave al redimensionar la ventana (SDL2 usa 1 = lineal).
os.environ.setdefault("SDL_RENDER_SCALE_QUALITY", "1")

# ── Lógica de entrenamiento (pura, portable a C++/Flutter) ─────────────
# music.py = teoría · walking.py = moldes · training.py = juego de notas ·
# technique.py / arpeggios.py / scales.py = secuencias.
# app.py solo pone UI + micro + sonido; nunca teoría musical.
from .events import KeyboardMixin, MouseMixin
from .modes import (
    CorridosModeMixin,
    EarModeMixin,
    ModeManagerMixin,
    SequencesModeMixin,
    TrainingModeMixin,
    WalkingLabMixin,
)

log = logging.getLogger(__name__)

# Diseño a resolución fija (W×H) y ventana redimensionable: SDL escala el
# lienzo lógico manteniendo el aspecto (barras negras si hace falta), así que
# todo el dibujo sigue en coordenadas de diseño y el ratón se traduce solo.
_WINDOW_FLAGS = pygame.RESIZABLE | pygame.SCALED

# Atajos clicables de la cabecera: (acción, etiqueta, tecla que la activa).
_HEADER_CHIPS = (
    ("help", "AYUDA", "F1"),
    ("songs", "CANCIONES", "L"),
    ("align", "ALINEAR", "W"),
    ("features", "AJUSTES", "I"),
)
_CHIP_H = 22
_CHIP_PAD = 16
_CHIP_GAP = 6


def _create_window():
    """Crea la ventana con vsync; degrada si el backend no lo soporta."""
    try:
        return pygame.display.set_mode((W, H), _WINDOW_FLAGS, vsync=1)
    except (pygame.error, TypeError):
        pass
    try:
        return pygame.display.set_mode((W, H), _WINDOW_FLAGS)
    except pygame.error:
        log.warning("[Ventana] SCALED no disponible — se usa 1280x860 fijo")
        return pygame.display.set_mode((W, H))


def _wrap_lines(text, font, max_w):
    """Divide texto por palabras para que cada línea quepa en max_w."""
    lines, cur = [], ""
    for word in text.split():
        probe = f"{cur} {word}".strip()
        if cur and font.size(probe)[0] > max_w:
            lines.append(cur)
            cur = word
        else:
            cur = probe
    if cur:
        lines.append(cur)
    return lines


def _fmt_tempo(tmap, scaled_by=1.0, mode="bpm"):
    """Cadena compacta de un mapa de tempo, en BPM o en figuras.
    scaled_by>1 aplica el estirado global (rate = bpm/bpm_original)."""
    if not tmap:
        return ""
    parts = []
    for e in tmap:
        qpm = e[1] * scaled_by
        unit = e[2] if len(e) >= 3 else "quarter"
        if mode == "figura":
            name = FIGURE_NAMES.get(unit, unit)
            parts.append(f"{qpm:g} {name}")
        else:
            parts.append(f"{qpm:g} BPM")
    return " → ".join(parts)


class BassKaraoke(
    TrainingModeMixin,
    WalkingLabMixin,
    CorridosModeMixin,
    EarModeMixin,
    SequencesModeMixin,
    ModeManagerMixin,
    KeyboardMixin,
    MouseMixin,
):

    def __init__(self):
        pygame.init()
        pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
        self.screen = _create_window()
        pygame.display.set_caption("Bass Karaoke v3  –  Feet Don't Fail Me Now")
        self.clock = pygame.time.Clock()
        self.view = ViewState()

        self.font_title = pygame.font.SysFont("consolas", 20, bold=True)
        self.font_huge  = pygame.font.SysFont("consolas", 74, bold=True)
        self.font_big   = pygame.font.SysFont("consolas", 30, bold=True)
        self.font_med   = pygame.font.SysFont("consolas", 19, bold=True)
        self.font_small = pygame.font.SysFont("consolas", 15)
        self.font_tiny  = pygame.font.SysFont("consolas", 12)

        # ── Estado ─────────────────────────────────────────────────────
        self.bpm            = BPM_DEFAULT
        self.playing        = False
        self.muted          = False
        self.note_idx       = 0
        self.beat_time      = 0.0
        self.score_ok       = 0
        self.score_total    = 0
        self.mp3_offset_sec = 0.0
        # Ancla independiente: instante del MP3 donde empieza el compás 1
        # (inicio de canción). El tramo song_start..mp3_offset (silencio/lead-in)
        # se estira sin tocar el resto de la partitura.
        self.song_start_sec = 0.0
        self._t             = 0.0   # tiempo acumulado para animaciones

        # ── Waveform de la vista principal (franja sincronizada) ───────
        self.song_wave       = None   # (min, max) normalizado -1..1
        self.song_wave_n     = 0
        self.song_total_sec  = 0.0

        # ── Countdown ──────────────────────────────────────────────────
        self.counting_down     = False
        self.countdown_beat    = 4
        self.countdown_timer   = 0.0
        self.countdown_enabled = True

        # ── Pitch ──────────────────────────────────────────────────────
        self.detected_hz   = 0.0
        self.detected_note = "—"
        self.stable_hz     = 0.0
        self.stable_note   = "—"
        self.note_match    = None
        self.pitch_lock    = threading.Lock()
        self._pitch_engine = None   # instancia PitchEngine
        self._pitch_last_cb = 0.0   # último on_update (para "SIN SEÑAL")
        self.pitch_engine  = "aubio"  # etiqueta para HUD

        # Indicador de timing
        self.last_hit_delta16  = 0.0
        self.last_hit_note_idx = -1
        self.last_hit_alpha    = 0.0

        # ── Dispositivos ───────────────────────────────────────────────
        self.audio_devices    = enumerate_devices()
        self.device_idx       = 0

        # ── Stats ──────────────────────────────────────────────────────
        self.section_stats = {}

        # ── Tuner ──────────────────────────────────────────────────────

        # ── Ayuda (F1) ───────────────────────────────────────────────────

        # ── Selector de método de pitch ────────────────────────────────
        self.pitch_method    = "mpm"

        # ── Gestor de funcionalidades opcionales (I) ───────────────────
        self.feature_busy      = set()
        self.feature_msg       = {}
        self.feature_log       = []

        # ── Metrónomo ──────────────────────────────────────────────────
        self.metro_beat    = 0
        self.metro_flash   = 0.0
        self.metro_sound   = False  # desactivado por defecto; N para activar
        self.beats_per_bar = 4       # tiempos por compás (del MusicXML; 3 en 3/4)
        self._click_hi, self._click_lo = self._build_clicks()
        # Canal 0 reservado para el bajo y canal 1 para la banda del mixer:
        # los clicks y los previews usan Sound.play() y pygame no toca los
        # canales reservados.
        try:
            pygame.mixer.set_reserved(2)
        except Exception:
            pass

        # ── Mixer (F2): canción / bajo / banda / metrónomo ─────────
        self.mix_song     = 1.0    # volumen de la canción (MP3)
        self.mix_bass     = 0.6    # volumen de la línea de bajo
        self.mix_band     = 0.6    # volumen de la banda (batería/piano/guitarra)
        self.mix_click    = 1.0    # volumen del metrónomo
        self.muted_bass   = False  # self.muted = mute de la pista Canción
        self.muted_band   = False
        self.muted_click  = False
        self._bass_audio  = None   # np.float32 (frames,2) pre-renderizado
        self._bass_key    = None   # clave de caché (canción + anclas + tempo)
        self.bass_midi    = None   # marcador .jjazz.json (MIDI del motor real)
        self._bass_sound  = None   # pygame.Sound actual
        self._bass_pending = None  # Sound preparado, aún sin arrancar
        self._bass_ch     = None   # pygame.Channel de la pista de bajo
        self._bass_render_s = 0.0  # tiempo del último render (diagnóstico)
        self._band_audio  = None   # audio de la banda pre-renderizado
        self._band_key    = None
        self._band_sound  = None
        self._band_pending = None
        self._band_ch     = None
        self._band_render_s = 0.0
        self._band_lock   = threading.Lock()
        self._resync_target = None   # ratio pendiente de re-render (sin VSP)
        self._resync_busy = False
        self._resync_ready = None

        # ── Mástil: mapa de notas de la canción ───────────────────────

        # ── Arrastre con ratón (seek) ─────────────────────────────────

        # ── Guitar Hero: nota detectada por el micrófono ──────────────
        self.detected_fret_str = None   # (fret, string) o None

        # ── Modo aprendizaje: nota pulsada con el ratón ──────────────

        # ── Modos de entrenamiento (E/G/K/O/X/A/V) ─────────────────────
        self._init_training_state()
        self._init_walking_lab_state()
        self._init_corridos_state()
        self._init_ear_state()
        self._init_sequences_state()

        # ── Editor de alineación MP3 (W) ──────────────────────────────
        self.align_editor_open = False
        self.align_wave        = None   # (col_min, col_max) normalizados a ±1
        self.align_wave_n      = 0
        self.align_total_sec   = 0.0
        self.align_view_start  = 0.0    # ventana visible (zoom/pan), en segundos
        self.align_view_span   = 0.0
        self.align_cursor_sec  = 0.0
        self.align_dragging    = False   # arrastrando el offset (inicio bajo)
        self.align_dragging_start = False  # arrastrando el inicio de canción
        self.align_drag_marker = None    # start16 de la marca de tempo arrastrada
        self.align_panning     = False   # arrastrando con botón central (pan)
        self.align_pan_start   = (0, 0)
        self.align_pan_view_start = 0.0
        self.align_playing     = False   # reproducción natural del MP3 en el editor
        self.align_detecting   = False   # análisis librosa en curso
        self.align_detected_tempo = None
        self.align_onsets      = None    # ticks de onsets (segundos)
        self.ed_offset         = 0.0
        self.ed_tempo_map      = []
        self._align_x0 = 60;  self._align_w = W - 120
        self._align_y0 = 150; self._align_h = 220

        # ── Scroll ─────────────────────────────────────────────────────

        # ── MusicXML ───────────────────────────────────────────────────
        self.notes       = []
        self.sections    = []
        self.grace_notes = []
        self.notes_stats = {}   # cobertura del parser {has_tab, total_pitch, …}
        self.measure_starts = []  # [[compás, start16], …] del MusicXML

        # ── Canciones ──────────────────────────────────────────────────
        self.song_idx       = 0
        self.song_name      = ""
        self.musicxml_path  = MUSICXML_PATH
        self.tg_path        = TG_PATH
        self.bpm_original   = BPM_ORIGINAL
        self.tempo_map      = [(0, BPM_ORIGINAL)]
        self.score_tempo_map = [(0, BPM_ORIGINAL)]   # marcas de tempo del MusicXML
        self._bpm_map       = {}
        self._offset_map    = {}
        self._song_start_map = {}
        self._tempo_maps    = {}
        # ── Generación de partitura (canciones solo-audio o .sng, F7) ──
        self.gen_running        = False
        self.gen_msg            = ""
        self.gen_frac           = 0.0
        self.gen_result         = None
        self.gen_error          = ""
        self.gen_notice         = False
        self.gen_song_dir       = None
        self.gen_from_sng       = False
        self.gen_barlen         = 3
        self.gen_bars_per_chord = 2
        self._gen_msg_timer     = 0.0
        self.songs          = self._scan_songs()
        self._piano_keys_list = []

        # ── Karaoke (acordes + letra, J para mostrar/ocultar) ───
        self.chord_events = []  # [(sec, "Sibm")] del <base>.chords.json
        self.lyric_events = []  # [(sec, "línea")] del <base>.chords.json
        self.chord_barlen = 4   # tiempos por compás (del MusicXML o del JSON)
        self.chords_path  = ""

        # ── Editor de acordes (Y) ─────────────────────────────────────
        self.chord_edit_open   = False
        self.chord_edit_sel    = 0
        self.chord_edit_top    = 0
        self.chord_edit_typing = False
        self.chord_edit_buf    = ""
        self.chord_edit_msg    = ""
        self.chord_edit_dirty  = False

        # ── Edición sobre la barra de acordes (clic en la tira) ────────
        self.chord_bar_sel_measure    = None   # compás seleccionado
        self.chord_bar_typing         = False
        self.chord_bar_buf            = ""
        self.chord_bar_target_sec     = None   # inicio del compás editado
        self.chord_bar_target_end_sec = None   # inicio del siguiente compás
        self.chord_bar_msg            = ""
        self.chord_bar_sugg_idx       = -1     # fila resaltada del desplegable
        self.chord_bar_sugg_cache     = []     # sugerencias mostradas
        self.chord_bar_replace        = False  # el próximo carácter sustituye

        # ── Score pre-render ───────────────────────────────────────────
        self.score_renderer  = "verovio"

        # ── Audio MP3 ──────────────────────────────────────────────────
        self._vsp       = VarispeedPlayer() if VARSPEED_OK else None
        self.mp3_path   = None
        self.mid_path   = ""
        self._pgm_loaded = False
        self._use_vsp   = False

        self._load_config()
        self._apply_mix()

        if self.songs:
            self.song_idx = min(self.song_idx, len(self.songs) - 1)
            self._load_song(self.song_idx, caption=True, init_score=False)
        else:
            log.warning("[WARN] No hay canciones en songs/ — usando rutas por defecto")
            self._load_notes()
            self._load_mp3(self._find_mp3())
            self._build_song_waveform()
            pygame.display.set_caption(f"Bass Karaoke v3  –  {self.song_name or 'sin canción'}")

        if self.musicxml_path and self.notes:
            if self.score_renderer == "music21" and MUSIC21_OK:
                self._init_score_music21()
            elif VEROVIO_OK and CAIROSVG_OK:
                self._init_score_verovio()
            elif MUSIC21_OK:
                self.score_renderer = "music21"
                self._init_score_music21()

        if INPUT_AVAILABLE and self.audio_devices:
            self._start_audio()

    # ══════════════════════════════════════════════════════════════════
    #  METRÓNOMO — generación de clicks con numpy
    # ══════════════════════════════════════════════════════════════════
    @staticmethod
    def _build_clicks():
        """Genera dos clicks (beat 1 agudo, beats 2-4 grave) como pygame.Sound."""
        import numpy as np
        SR   = 44100
        dur  = 0.06          # 60 ms
        n    = int(SR * dur)
        t    = np.linspace(0, dur, n, endpoint=False)
        env  = np.exp(-t * 60)   # envolvente de decaimiento rápido

        # Beat 1: tono más agudo (1000 Hz)
        wave_hi = (np.sin(2 * np.pi * 1000 * t) * env * 28000).astype(np.int16)
        stereo_hi = np.column_stack([wave_hi, wave_hi])
        snd_hi  = pygame.sndarray.make_sound(np.ascontiguousarray(stereo_hi))

        # Beats 2-4: tono más grave (600 Hz)
        wave_lo = (np.sin(2 * np.pi * 600 * t) * env * 20000).astype(np.int16)
        stereo_lo = np.column_stack([wave_lo, wave_lo])
        snd_lo  = pygame.sndarray.make_sound(np.ascontiguousarray(stereo_lo))

        return snd_hi, snd_lo

    def _play_click(self, is_beat1: bool, force: bool = False):
        """force=True lo hace sonar aunque metro_sound esté desactivado (countdown)."""
        if not (self.metro_sound or force):
            return
        try:
            snd = self._click_hi if is_beat1 else self._click_lo
            snd.play()
        except Exception:
            pass

    # ══════════════════════════════════════════════════════════════════
    #  CONFIG
    # ══════════════════════════════════════════════════════════════════
    def _save_config(self):
        if not hasattr(self, "_bpm_map") or not self._bpm_map:
            self._bpm_map = {}
        if self.song_name:
            self._bpm_map[self.song_name] = self.bpm
        if not hasattr(self, "_offset_map") or not self._offset_map:
            self._offset_map = {}
        if self.song_name:
            self._offset_map[self.song_name] = self.mp3_offset_sec
        if not hasattr(self, "_song_start_map") or not self._song_start_map:
            self._song_start_map = {}
        if self.song_name:
            self._song_start_map[self.song_name] = self.song_start_sec
        if not hasattr(self, "_tempo_maps") or not self._tempo_maps:
            self._tempo_maps = {}
        if self.song_name:
            self._tempo_maps[self.song_name] = [
                [int(e[0]), round(e[1], 2), (e[2] if len(e) >= 3 else "quarter")]
                for e in self.tempo_map
            ]
        cfg = {
            "bpm":               self.bpm,
            "bpm_map":           self._bpm_map,
            "mp3_offset_sec":    self.mp3_offset_sec,
            "mp3_offset_map":    self._offset_map,
            "song_start_map":    self._song_start_map,
            "tempo_maps":        self._tempo_maps,
            "device_idx":        self.device_idx,
            "muted":             self.muted,
            "mix_song":          round(self.mix_song, 3),
            "mix_bass":          round(self.mix_bass, 3),
            "mix_band":          round(self.mix_band, 3),
            "mix_click":         round(self.mix_click, 3),
            "muted_bass":        self.muted_bass,
            "muted_band":        self.muted_band,
            "muted_click":       self.muted_click,
            "pitch_method":      self.pitch_method,
            "countdown_enabled": self.countdown_enabled,
            "score_renderer":    self.score_renderer,
            "gen_barlen":        self.gen_barlen,
            "gen_bars_per_chord": self.gen_bars_per_chord,
            "song":              self.song_name,
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
            with open(CONFIG_PATH, encoding="utf-8") as f:
                cfg = json.load(f)
            self.bpm            = float(cfg.get("bpm",            self.bpm))
            self.mp3_offset_sec = float(cfg.get("mp3_offset_sec", self.mp3_offset_sec))
            self.muted          = bool( cfg.get("muted",          self.muted))
            self.mix_song       = float(cfg.get("mix_song",       self.mix_song))
            self.mix_bass       = float(cfg.get("mix_bass",       self.mix_bass))
            self.mix_band       = float(cfg.get("mix_band",       self.mix_band))
            self.mix_click      = float(cfg.get("mix_click",      self.mix_click))
            self.muted_bass     = bool( cfg.get("muted_bass",     self.muted_bass))
            self.muted_band     = bool( cfg.get("muted_band",     self.muted_band))
            self.muted_click    = bool( cfg.get("muted_click",    self.muted_click))
            for _v in ("mix_song", "mix_bass", "mix_band", "mix_click"):
                setattr(self, _v, max(0.0, min(1.0, getattr(self, _v))))
            saved_dev           = int(  cfg.get("device_idx",     self.device_idx))
            if 0 <= saved_dev < len(self.audio_devices):
                self.device_idx = saved_dev
            saved_method = cfg.get("pitch_method", self.pitch_method)
            if saved_method in PITCH_METHODS:
                self.pitch_method   = saved_method
                self.view.pitch_menu_sel = PITCH_METHODS.index(saved_method)
            self.countdown_enabled = bool(cfg.get("countdown_enabled", self.countdown_enabled))
            self.gen_barlen         = int(cfg.get("gen_barlen", self.gen_barlen))
            self.gen_bars_per_chord = int(cfg.get("gen_bars_per_chord", self.gen_bars_per_chord))
            saved_renderer = cfg.get("score_renderer", self.score_renderer)
            if saved_renderer in ("verovio", "music21"):
                self.score_renderer = saved_renderer
            saved_song = cfg.get("song")
            if saved_song and self.songs:
                for i, s in enumerate(self.songs):
                    if s["name"] == saved_song:
                        self.song_idx = i
                        break
            self._bpm_map = cfg.get("bpm_map", {}) or {}
            self._offset_map = cfg.get("mp3_offset_map", {}) or {}
            self._song_start_map = cfg.get("song_start_map", {}) or {}
            self._tempo_maps = cfg.get("tempo_maps", {}) or {}
            log.info(f"[Config] cargada  BPM={self.bpm}  offset={self.mp3_offset_sec:+.2f}s  "
                  f"pitch={self.pitch_method}  renderer={self.score_renderer}  "
                  f"song={saved_song}")
        except Exception as e:
            log.warning(f"[Config WARN] {e}")

    # ══════════════════════════════════════════════════════════════════
    #  CANCIONES / NOTAS / MP3
    # ══════════════════════════════════════════════════════════════════
    def _scan_songs(self):
        """Escanea songs/: con MusicXML o solo audio (pendiente de generar)."""
        songs = []
        if not os.path.isdir(SONGS_DIR):
            return songs
        for entry in sorted(os.listdir(SONGS_DIR)):
            folder = os.path.join(SONGS_DIR, entry)
            if not os.path.isdir(folder) or entry.startswith("."):
                continue
            musicxml = self._find_file(folder, ".musicxml")
            audio = None
            for ext in (".mp3", ".wav", ".flac", ".ogg", ".m4a"):
                audio = self._find_file(folder, ext)
                if audio:
                    break
            sng = self._find_file(folder, ".sng")
            if not musicxml and not audio and not sng:
                continue
            name = entry.replace("_", " ").replace("-", " ").title()
            songs.append({
                "name":       name,
                "dir":        folder,
                "musicxml":   musicxml,
                "tg":         self._find_file(folder, ".tg"),
                "mp3":        self._find_file(folder, ".mp3"),
                "mid":        (self._find_file(folder, ".mid")
                               or self._find_file(folder, ".midi")),
                "sng":        sng,
                "jjazz":      self._find_file(folder, ".jjazz.json"),
                "audio":      audio,
                "audio_only": musicxml is None,
            })
            log.info(f"[Canción] {name:24s}  "
                  f"xml={'SÍ' if musicxml else 'NO (F7)'}  "
                  f"audio={'SÍ' if audio else 'no'}  "
                  f"mid={'SÍ' if songs[-1]['mid'] else 'no'}  "
                  f"sng={'SÍ' if sng else 'no'}")
        return songs

    @staticmethod
    def _find_file(folder: str, ext: str):
        """Busca un archivo por extensión; prefiere el que coincide con el nombre de la carpeta."""
        try:
            files = sorted(f for f in os.listdir(folder) if f.lower().endswith(ext))
        except OSError:
            return None
        if not files:
            return None
        base = os.path.basename(folder).lower()
        for f in files:
            if os.path.splitext(f)[0].lower() == base:
                return os.path.join(folder, f)
        return os.path.join(folder, files[0])

    def _load_song(self, idx: int, caption: bool = False, init_score: bool = True):
        """Carga una canción completa: notas, gracia, MP3 y partitura."""
        song = self.songs[idx]
        self.song_idx      = idx
        self.song_name     = song["name"]
        self.musicxml_path = song["musicxml"] or ""
        self.tg_path       = song["tg"] or TG_PATH
        self.mid_path      = song.get("mid") or ""
        self.bass_midi     = None
        marker = song.get("jjazz")
        if marker:
            from . import jjazz as _jjazz
            data = _jjazz.read_marker(marker)
            if data and data.get("midi"):
                mid = os.path.join(song["dir"], data["midi"])
                if os.path.isfile(mid):
                    self.mid_path = mid
                    self.bass_midi = data
        self.gen_notice    = bool(song.get("audio_only"))
        if self.musicxml_path:
            self._load_notes()
        else:
            self.notes          = []
            self.sections       = []
            self.notes_stats    = {}
            self.section_stats  = {}
            self.measure_starts = []
            self.grace_notes    = {}
            self.beats_per_bar  = 4
            self.tempo_map      = [(0, self.bpm, "quarter")]
            self.score_tempo_map = [list(x) for x in self.tempo_map]
            log.info(f"[Gen] {self.song_name}: sin partitura — pulsa F7 para "
                     f"generarla{' desde el .sng' if song.get('sng') else ''}")
        self._load_mp3(song.get("audio") or song["mp3"])
        self._build_song_waveform()
        self.reiniciar()
        # Karaoke (acordes + letra): <base>.chords.json junto al musicxml
        self.chord_events = []
        self.lyric_events = []
        self.chords_path  = ""
        if self.musicxml_path:
            try:
                base, _ = os.path.splitext(self.musicxml_path)
                self.chords_path = base + ".chords.json"
                self.chord_events, self.lyric_events = load_song_map(
                    self.chords_path)
                self.chord_barlen = load_song_barlen(self.chords_path,
                                                     default=self.beats_per_bar)
                if self.chord_events or self.lyric_events:
                    log.info(f"[OK] Karaoke: {len(self.chord_events)} acordes, "
                          f"{len(self.lyric_events)} líneas")
            except Exception as e:
                log.warning(f"[Karaoke WARN] {e}")
        self._prefetch_band()
        self.chord_edit_dirty     = False
        self.chord_bar_sel_measure    = None
        self.chord_bar_typing     = False
        self.chord_bar_buf        = ""
        self.chord_bar_target_sec = None
        self.chord_bar_target_end_sec = None
        self.chord_bar_msg        = ""
        self.chord_bar_sugg_idx   = -1
        self.chord_bar_sugg_cache = []
        self.chord_bar_replace    = False
        # Re-generar partitura y estado dependiente de la canción
        self.view._score_cache    = {}
        self.view._score_surf     = None
        self.view._score_note_xs  = []
        self.view._score_scroll_x = 0.0
        self.view._score_total16  = (
            (self.notes[-1]["start16"] + self.notes[-1]["dur"]) if self.notes else 1
        )
        # Mapa de tempo guardado en la config (si el usuario lo editó con W)
        custom_tmap = (self._tempo_maps or {}).get(self.song_name)
        if custom_tmap:
            self.tempo_map = [
                (int(r[0]), float(r[1]), r[2] if len(r) >= 3 else "quarter")
                for r in custom_tmap
            ]
            if self.tempo_map:
                self.bpm_original = self.tempo_map[0][1]
                self.bpm          = self.tempo_map[0][1]
        saved_bpm = (self._bpm_map or {}).get(self.song_name)
        if saved_bpm is not None:
            self.bpm = float(saved_bpm)
        # Sin offset guardado para esta canción se parte de 0: no heredar el
        # de la canción anterior (evita el "+25.99s fantasma" al cambiar de tema).
        self.mp3_offset_sec = 0.0
        saved_offset = (self._offset_map or {}).get(self.song_name)
        if saved_offset is not None:
            self.mp3_offset_sec = float(saved_offset)
        # Ancla de inicio de canción (compás 1). Sin valor guardado se deduce
        # del tempo de la partitura (equivale al comportamiento de una ancla).
        self.song_start_sec = self.mp3_offset_sec
        saved_start = (self._song_start_map or {}).get(self.song_name)
        if saved_start is not None:
            self.song_start_sec = float(saved_start)
        elif self.notes:
            self.song_start_sec = (self.mp3_offset_sec
                                   - self._song_seconds(self._bass_start16()))
        self._clamp_anchors()
        if caption:
            pygame.display.set_caption(f"Bass Karaoke v3  –  {self.song_name}")
        if init_score and self.notes:
            self._init_score()
        elif not self.notes:
            self.view._score_surf = None
        log.info(f"[OK] Canción cargada: {self.song_name}")

    def _load_notes(self):
        if not os.path.exists(self.musicxml_path):
            log.error(f"[ERROR] MusicXML no encontrado: {self.musicxml_path}")
            return
        try:
            notes, sections, bpm, tempo_map, stats = parse_musicxml(self.musicxml_path)
            self.notes         = notes
            self.sections      = sections
            self.notes_stats   = stats
            self.beats_per_bar = int(stats.get("beats_per_bar", 4) or 4)
            self.measure_starts = stats.get("measure_starts", []) or []
            self.tempo_map     = tempo_map or [(0, bpm, "quarter")]
            self.score_tempo_map = [list(x) for x in self.tempo_map]
            self.bpm           = bpm
            self.bpm_original  = bpm
            self.grace_notes   = parse_grace_notes(self.tg_path, notes)
            self.section_stats = {}
            for n in notes:
                sec = n["section"]
                if sec not in self.section_stats:
                    self.section_stats[sec] = {"ok": 0, "total": 0}
            log.info(f"[OK] MusicXML: {len(notes)} notas, {bpm} BPM  "
                  f"compás={self.beats_per_bar}/4  graces={len(self.grace_notes)}")
        except Exception as e:
            log.error(f"[ERROR] MusicXML: {e}")
            import traceback

            traceback.print_exc()

    def _load_mp3(self, path=None):
        self._stop_mp3()
        self.mp3_path    = path
        self._vsp        = VarispeedPlayer() if VARSPEED_OK else None
        self._pgm_loaded = False
        self._use_vsp    = False
        self._bass_audio = None
        self._bass_key   = None
        self._band_audio = None
        self._band_key   = None
        if self._vsp:
            # El varispeed mezcla las pistas extra en su mismo stream, ya
            # estiradas al tempo actual (misma cuenta de frames que el MP3).
            self._vsp.set_extra_render(self._bass_audio_for)
            self._vsp.set_extra_volume(self._bass_volume())
            self._vsp.set_extra2_render(self._band_audio_for)
            self._vsp.set_extra2_volume(self._band_volume())
        if not self.mp3_path:
            log.info("[Audio] Sin MP3 para esta canción — solo metrónomo/tablatura")
            return
        if self._vsp:
            if not self._vsp.load(self.mp3_path):
                self._vsp = None
        try:
            pygame.mixer.music.load(self.mp3_path)
            self._pgm_loaded = True
            log.info(f"[pygame.mixer] {self.mp3_path}")
        except Exception as e:
            log.warning(f"[WARN] pygame.mixer: {e}")

    # ── Generación de partitura desde audio (F7) ─────────────────────
    def _start_generation(self):
        if self.gen_running:
            return
        song = self.songs[self.song_idx]
        sng = song.get("sng") if not song.get("musicxml") else None
        self.gen_running  = True
        self.gen_msg      = "Preparando…"
        self.gen_frac     = 0.0
        self.gen_error    = ""
        self.gen_result   = None
        self.gen_song_dir = song["dir"]
        self.gen_from_sng = bool(sng)
        self.gen_notice   = False
        if sng:
            log.info(f"[Gen] Generando partitura de {self.song_name} desde "
                     f"{os.path.basename(sng)}…")
        else:
            log.info(f"[Gen] Transcribiendo {self.song_name} "
                     f"(barlen={self.gen_barlen})…")

        def progress(msg, frac=None):
            self.gen_msg = msg
            if frac is not None:
                self.gen_frac = float(frac)

        def worker():
            try:
                if sng:
                    from . import jjazz as _jjazz
                    from .sng import build_song
                    self.gen_msg = ("Generando con el motor de JJazzLab…"
                                    if _jjazz.available()
                                    else "Generando la línea de bajo…")
                    res = build_song(sng, out_dir=song["dir"])
                    self.gen_result = {
                        "notes": len(res["notes"]),
                        "measures": res["song"]["total_bars"],
                        "bpm": res["song"]["tempo"],
                        "suggested_offset": 0.0,
                    }
                    return
                from .transcribe import transcribe_song
                self.gen_result = transcribe_song(
                    self.gen_song_dir,
                    barlen=self.gen_barlen,
                    bars_per_chord=self.gen_bars_per_chord,
                    progress_cb=progress)
            except Exception as e:
                import traceback

                traceback.print_exc()
                self.gen_error = str(e)
            finally:
                self.gen_running = False

        threading.Thread(target=worker, daemon=True).start()

    def _poll_generation(self):
        if self.gen_running or self.gen_result is None:
            return
        res = self.gen_result
        self.gen_result = None
        self.gen_frac = 1.0
        self.songs = self._scan_songs()
        target = os.path.normcase(os.path.normpath(self.gen_song_dir or ""))
        idx = 0
        for i, s in enumerate(self.songs):
            if os.path.normcase(os.path.normpath(s["dir"])) == target:
                idx = i
                break
        self._load_song(idx)
        off = float(res.get("suggested_offset", 0.0) or 0.0)
        self.mp3_offset_sec = off
        self._offset_map[self.song_name] = off
        # Si el inicio de canción no estaba fijado a mano, recolocarlo con el
        # offset nuevo (la partitura regenerada puede tener otro primer s16).
        if (self._song_start_map or {}).get(self.song_name) is None:
            self.song_start_sec = (off
                                   - self._song_seconds(self._bass_start16()))
        self._clamp_anchors()
        self._remember_anchors()
        self._save_config()
        self.gen_msg = (f"Partitura generada: {res.get('notes', 0)} notas · "
                        f"{res.get('measures', 0)} compases · {res.get('bpm', 0)} BPM")
        self._gen_msg_timer = 8.0
        log.info(f"[Gen] {self.gen_msg}  offset={off:+.2f}s")

    def _init_score(self):
        if self.score_renderer == "music21" and MUSIC21_OK:
            self._init_score_music21()
        elif VEROVIO_OK and CAIROSVG_OK:
            self._init_score_verovio()
        elif MUSIC21_OK:
            self.score_renderer = "music21"
            self._init_score_music21()

    def _find_mp3(self):
        """(fallback) Busca cualquier MP3 en la carpeta de la canción actual."""
        if self.song_idx < len(self.songs):
            s = self.songs[self.song_idx]
            return s.get("audio") or s["mp3"]
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        for folder in [os.path.join(base, "songs", "mitab"), base]:
            if os.path.isdir(folder):
                for f in os.listdir(folder):
                    if f.lower().endswith(".mp3"):
                        return os.path.join(folder, f)
        return None

    # ══════════════════════════════════════════════════════════════════
    #  SCORE INIT
    # ══════════════════════════════════════════════════════════════════
    def _init_score_verovio(self):
        if "verovio" in self.view._score_cache:
            self.view._score_surf, self.view._score_note_xs = self.view._score_cache["verovio"]
            log.info("[Verovio] usando caché")
            return
        surf, note_xs = init_score_surface(self.notes, self.musicxml_path)
        self.view._score_surf    = surf
        self.view._score_note_xs = note_xs
        if surf is not None:
            self.view._score_cache["verovio"] = (surf, note_xs)

    def _init_score_music21(self):
        if "music21" in self.view._score_cache:
            self.view._score_surf, self.view._score_note_xs = self.view._score_cache["music21"]
            log.info("[Music21] usando caché")
            return
        surf, note_xs = init_score_surface_music21(self.notes, self.musicxml_path)
        self.view._score_surf    = surf
        self.view._score_note_xs = note_xs
        if surf is not None:
            self.view._score_cache["music21"] = (surf, note_xs)

    # ══════════════════════════════════════════════════════════════════
    #  AUDIO / PITCH
    # ══════════════════════════════════════════════════════════════════
    def _start_audio(self, list_idx=None):
        if self._pitch_engine is not None:
            self._pitch_engine.stop()
            self._pitch_engine = None

        if list_idx is not None:
            self.device_idx = list_idx % len(self.audio_devices)

        dev_id = self.audio_devices[self.device_idx][0]

        def on_update(det_hz, det_note, stb_hz, stb_note):
            with self.pitch_lock:
                self.detected_hz   = det_hz
                self.detected_note = det_note
                self.stable_hz     = stb_hz
                self.stable_note   = stb_note
                self._pitch_last_cb = time.time()

        def on_engine_label(label):
            self.pitch_engine = label

        def on_debug(hz, conf, method):
            if self.view.tuner_open:
                log.debug(f"[tuner-debug] {hz:.1f} Hz  conf={conf:.2f}  ({method})")

        self._pitch_engine = PitchEngine(
            method=self.pitch_method,
            device_id=dev_id,
            on_update=on_update,
            on_engine_label=on_engine_label,
            on_debug=on_debug,
        )
        self._pitch_engine.start()

    def _stop_audio(self):
        if self._pitch_engine is not None:
            self._pitch_engine.stop()
            self._pitch_engine = None

    # ══════════════════════════════════════════════════════════════════
    #  FUNCIONALIDADES OPCIONALES (I)
    # ══════════════════════════════════════════════════════════════════
    def _feature_toggle(self, fid):
        if fid in self.feature_busy:
            return
        self.feature_busy.add(fid)
        self.feature_msg.pop(fid, None)
        self.feature_log.clear()
        if features.installed(fid):
            features.uninstall(fid, on_log=self._feature_log,
                               on_done=self._feature_done)
        else:
            features.install(fid, on_log=self._feature_log,
                             on_done=self._feature_done)

    def _feature_log(self, line):
        self.feature_log.append(line)
        if len(self.feature_log) > 6:
            self.feature_log.pop(0)

    def _feature_done(self, fid, ok, msg):
        self.feature_busy.discard(fid)
        self.feature_msg[fid] = (ok, msg)
        if ok:
            self._config_msg     = msg
            self._config_msg_col = C_WAIT if "Reinicia" in msg else C_OK
            self._config_msg_timer = 4.0
        else:
            self._config_msg     = msg
            self._config_msg_col = C_ERR
            self._config_msg_timer = 4.0

    # ══════════════════════════════════════════════════════════════════
    #  HELPERS
    # ══════════════════════════════════════════════════════════════════
    def px_of(self, beat16):
        return int(beat16 * self.view.px_per_16th)

    def current_note(self):
        if self.note_idx >= len(self.notes):
            return None
        n = self.notes[self.note_idx]
        if self.beat_time < n["start16"] or self.beat_time >= n["start16"] + n["dur"]:
            return None
        return n

    def coverage_warning(self):
        """Aviso persistente sobre la cobertura del parser (o None si todo ok).

        Cubre: canción sin notas de bajo, fallback por pitch con transporte o
        descartes, y falta de MP3. La UI lo muestra en el tab y el panel."""
        st = getattr(self, "notes_stats", {}) or {}
        if not self.notes:
            if st and not st.get("has_tab", True):
                return "Sin notas de bajo: el MusicXML no trae tablatura y nada encaja en el mástil"
            return "Sin notas de bajo en este MusicXML"
        if st and not st.get("has_tab", True):
            total = st.get("total_pitch", 0)
            tra   = st.get("transposed", 0)
            dro   = st.get("dropped", 0)
            if dro > 0 and tra > 0:
                return (f"Sin tablatura: {tra}/{total} notas bajadas de octava, "
                        f"{dro} fuera del mástil")
            if tra > 0:
                return f"Sin tablatura: {tra}/{total} notas bajadas de octava para el bajo"
            if dro > 0:
                return f"Sin tablatura: {dro}/{total} notas fuera del mástil"
        if not self.mp3_path:
            return "Sin MP3: practica con metrónomo/tablatura"
        return None

    def _speed_ratio(self):
        return self.bpm / self.bpm_original

    def _tempo_at(self, beat16, tmap=None):
        """Tempo (negras/min) vigente en la posición beat16 según el mapa."""
        tmap = tmap if tmap is not None else self.tempo_map
        t = self.bpm_original
        for e in tmap:
            s16, qpm = e[0], e[1]
            if s16 <= beat16:
                t = qpm
            else:
                break
        return t

    def _bass_start16(self):
        """Posición (start16) de la PRIMERA nota del bajo. La línea roja del
        editor (offset) marca el instante del MP3 donde suena esta nota."""
        return float(self.notes[0]["start16"]) if self.notes else 0.0

    def grid_phase16(self):
        bar16 = max(4, int(self.beats_per_bar) * 4)
        return int(self._bass_start16()) % bar16

    def _clamp_anchors(self):
        """Mantiene 0 <= inicio_canción <= entrada_bajo - 20 ms."""
        self.mp3_offset_sec = max(0.0, float(getattr(self, "mp3_offset_sec", 0.0)))
        self.song_start_sec = max(0.0, float(getattr(self, "song_start_sec", 0.0)))
        if self.song_start_sec > self.mp3_offset_sec - 0.02:
            self.song_start_sec = max(0.0, self.mp3_offset_sec - 0.02)

    def _remember_anchors(self):
        if self.song_name:
            self._offset_map[self.song_name]     = self.mp3_offset_sec
            self._song_start_map[self.song_name] = self.song_start_sec

    def _anchor_pair(self, bass_sec=None, tmap=None):
        """(inicio_canción, entrada_bajo) efectivos en segundos del MP3."""
        bass = max(0.0, float(self.mp3_offset_sec if bass_sec is None else bass_sec))
        start = max(0.0, float(getattr(self, "song_start_sec", 0.0)))
        start = min(start, max(0.0, bass - 0.02))
        return start, bass

    def _lead_qpm(self, tmap=None):
        """Tempo efectivo del silencio inicial (compás 1 -> primera nota)."""
        s0 = self._bass_start16()
        if s0 <= 0:
            return self._tempo_at(s0, tmap)
        raw_s0 = self._song_seconds(s0, tmap)
        start, bass = self._anchor_pair(tmap=tmap)
        lead = bass - start
        if lead <= 0.02 or raw_s0 <= 1e-9:
            return self._tempo_at(s0, tmap)
        return (s0 / 4.0) * 60.0 / lead

    def _eff_seconds(self, s16, bass_sec=None, tmap=None):
        """Instante del MP3 de una posición de partitura con DOS anclas:
        s16=0 -> song_start_sec y s16=s0 -> mp3_offset_sec. El tramo inicial
        (silencio/lead-in) se estira; el resto conserva el tempo del mapa."""
        tmap = self.tempo_map if tmap is None else tmap
        start, bass = self._anchor_pair(bass_sec, tmap)
        s0 = self._bass_start16()
        raw = self._song_seconds(s16, tmap)
        if s0 <= 1e-9:
            return bass + raw
        raw_s0 = self._song_seconds(s0, tmap)
        if raw_s0 <= 1e-9:
            return bass + raw
        lead = bass - start
        if lead <= 1e-6:
            return start if s16 <= s0 else bass + (raw - raw_s0)
        if s16 <= s0:
            return start + (raw / raw_s0) * lead
        return bass + (raw - raw_s0)

    def _eff_seconds_inverse(self, sec, bass_sec=None, tmap=None):
        """Inverso de _eff_seconds: instante del MP3 -> start16."""
        tmap = self.tempo_map if tmap is None else tmap
        start, bass = self._anchor_pair(bass_sec, tmap)
        s0 = self._bass_start16()
        if s0 <= 1e-9:
            return self._song_seconds_inverse(max(0.0, sec - bass), tmap)
        raw_s0 = self._song_seconds(s0, tmap)
        if raw_s0 <= 1e-9:
            return self._song_seconds_inverse(max(0.0, sec - bass), tmap)
        lead = bass - start
        if lead <= 1e-6:
            if sec <= bass:
                return 0.0
            return self._song_seconds_inverse(raw_s0 + (sec - bass), tmap)
        if sec <= start:
            return 0.0
        if sec <= bass:
            return self._song_seconds_inverse((sec - start) / lead * raw_s0, tmap)
        return self._song_seconds_inverse(raw_s0 + (sec - bass), tmap)

    def _song_seconds(self, beat16, tmap=None):
        """Segundos reales de la canción (a tempo original) desde el inicio
        hasta beat16, respetando los cambios de tempo del mapa.
        El resultado es independiente del ajuste global de BPM (↑/↓)."""
        tmap   = tmap if tmap is not None else self.tempo_map
        total  = 0.0
        prev16 = 0
        prevqpm = (tmap[0][1] if tmap else self.bpm_original)
        for e in tmap:
            s16, qpm = e[0], e[1]
            if s16 >= beat16:
                break
            total   += (s16 - prev16) / 4.0 * (60.0 / prevqpm)
            prev16  = s16
            prevqpm = qpm
        total += (beat16 - prev16) / 4.0 * (60.0 / prevqpm)
        return total

    def _song_seconds_inverse(self, seconds, tmap=None):
        """Inverso de _song_seconds: segundos originales -> start16."""
        tmap    = tmap if tmap is not None else self.tempo_map
        rel     = max(0.0, seconds)
        total   = 0.0
        prev16  = 0
        prevqpm = (tmap[0][1] if tmap else self.bpm_original)
        for e in tmap:
            s16, qpm = e[0], e[1]
            seg_sec = (s16 - prev16) / 4.0 * (60.0 / prevqpm)
            if rel <= total + seg_sec:
                frac = (rel - total) / seg_sec if seg_sec > 0 else 0.0
                return prev16 + frac * (s16 - prev16)
            total   += seg_sec
            prev16  = s16
            prevqpm = qpm
        return prev16 + (rel - total) * 4.0 * prevqpm / 60.0

    def _mp3_sec_of_s16(self, s16, offset=None, tmap=None):
        """Posición MP3 (segundos) de una posición de partitura start16.
        Con dos anclas: s16=0 -> song_start_sec y s16=s0 -> offset (primera
        nota del bajo). El silencio inicial se estira entre ambas."""
        offset = self.mp3_offset_sec if offset is None else offset
        return self._eff_seconds(s16, offset, tmap)

    def _beat16_at_mp3sec(self, mp3_sec, offset=None, tmap=None):
        """Inverso de _mp3_sec_of_s16: instante del MP3 -> start16."""
        offset = self.mp3_offset_sec if offset is None else offset
        return self._eff_seconds_inverse(mp3_sec, offset, tmap)

    # ══════════════════════════════════════════════════════════════════
    #  EDITOR DE ALINEACIÓN MP3 (W)
    # ══════════════════════════════════════════════════════════════════
    def _open_align_editor(self):
        if self.playing:
            self._stop_mp3()
            self.playing = False
        self.ed_offset    = self.mp3_offset_sec
        # Marcas de tempo ancladas al MP3: (mp3_sec, qpm, unidad, start16|None).
        # El 4º campo = posición de partitura si la marca aún sigue "lo que
        # dice la partitura" (se mueve con la línea roja); None = fijada a mano.
        # La línea roja (offset) es independiente y marca la PRIMERA nota del bajo.
        self.ed_tempo_map = [
            [round(self._mp3_sec_of_s16(s16, self.ed_offset, self.tempo_map), 2),
             qpm, unit, float(s16)]
            for s16, qpm, unit in (self._align_entry(e) for e in self.tempo_map)
        ]
        self._align_build_waveform()
        self.align_view_start = 0.0
        self.align_view_span  = self.align_total_sec
        self.align_cursor_sec = self.ed_offset
        self.align_playing    = False
        self.align_dragging_start = False
        self.align_detecting  = False
        self.align_detected_tempo = None
        self.align_onsets     = None
        self.align_editor_open = True

    def _ed_tmap_s16(self):
        """Convierte el mapa del editor (mp3-anchored) a (start16, qpm, unit).
        Las marcas ligadas a la partitura conservan su start16; las fijadas a
        mano se convierten ancladas a la primera nota del bajo (línea roja)."""
        if not self.ed_tempo_map:
            return [(0.0, 60.0, "quarter")]
        S = self._bass_start16()
        entries = []
        for e in self.ed_tempo_map:
            m, q, u = self._align_entry(e)
            entries.append((m, q, u, e[3] if len(e) >= 4 else None))
        entries.sort(key=lambda x: x[0])
        dedup = []
        for m in entries:
            if dedup and abs(m[0] - dedup[-1][0]) <= 1e-3:
                dedup[-1] = m
            else:
                dedup.append(m)
        out, tmap_so_far = [], []
        for mp3, qpm, unit, s16 in dedup:
            if s16 is not None:
                s = float(s16)
            else:
                abs_sec = self._song_seconds(S, tmap_so_far) + (mp3 - self.ed_offset)
                s = self._song_seconds_inverse(abs_sec, tmap_so_far)
            out.append((round(s, 4), qpm, unit))
            tmap_so_far.append((round(s, 4), qpm, unit))
            tmap_so_far.sort(key=lambda x: x[0])
        return self._align_normalize(out)

    def _align_reset_marks(self):
        """Vuelve las marcas de tempo a lo que dice la partitura.
        La línea roja (inicio del bajo) se mantiene."""
        if not self.score_tempo_map:
            return
        self.ed_tempo_map = [
            [round(self._mp3_sec_of_s16(s16, self.ed_offset,
                                        self.score_tempo_map), 2),
             qpm, unit, float(s16)]
            for s16, qpm, unit in (self._align_entry(e) for e in self.score_tempo_map)
        ]
        self.align_cursor_sec = self.ed_offset

    def _align_adopt_score_mark(self, idx, pos):
        """Adopta una referencia de la partitura (cian): crea/mueve una marca
        verde fijada en la posición del ratón."""
        s16, qpm, unit = self._align_entry(self.score_tempo_map[idx])
        sec = round(self._align_sec_of_pos(pos), 2)
        for e in self.ed_tempo_map:
            if abs(e[1] - qpm) <= 1e-3:
                e[0], e[3] = sec, None
                self.align_drag_marker = sec
                self.align_cursor_sec  = sec
                return
        self.ed_tempo_map.append([sec, qpm, unit, None])
        self.align_drag_marker = sec
        self.align_cursor_sec  = sec

    def _close_align_editor(self, apply=True):
        self.align_editor_open = False
        self.align_dragging    = False
        self.align_dragging_start = False
        self.align_drag_marker = None
        if self.align_playing:
            self.align_playing = False
            pygame.mixer.music.stop()
        if not apply:
            return
        self.ed_tempo_map = self._ed_tmap_s16()
        old_initial = self.bpm_original
        new_initial = self.ed_tempo_map[0][1] if self.ed_tempo_map else old_initial
        self.mp3_offset_sec = self.ed_offset
        self.tempo_map      = self.ed_tempo_map
        self.bpm_original   = new_initial
        if abs(self.bpm - old_initial) < 0.01:
            self.bpm = new_initial
        self._clamp_anchors()
        if self.song_name:
            self._offset_map[self.song_name] = self.mp3_offset_sec
            self._song_start_map[self.song_name] = self.song_start_sec
            self._tempo_maps[self.song_name] = [
                [int(e[0]), round(e[1], 2), (e[2] if len(e) >= 3 else "quarter")]
                for e in self.tempo_map
            ]
        self._save_config()
        log.info(f"[Alineación] offset={self.mp3_offset_sec:+.2f}s  "
              f"tempo_map={self.tempo_map}")

    def _build_song_waveform(self):
        """Rejilla fina min/max de TODO el MP3, calculada una sola vez.
        La comparten la franja de waveform de la vista principal y el editor
        de alineación (W)."""
        import numpy as _np
        vsp = self._vsp
        self.song_wave      = None
        self.song_wave_n    = 0
        self.song_total_sec = 0.0
        arr = None
        sr = 0
        if vsp and vsp.loaded and vsp.data_orig is not None:
            arr = vsp.data_orig[:, 0]
            sr = vsp.sr
        elif self.mp3_path:
            arr, sr = load_mp3_samples(self.mp3_path)
        if arr is None or sr <= 0:
            return
        self.song_total_sec = len(arr) / float(sr)
        n = len(arr)
        n_grid = min(20000, max(1, n // 4))
        if n <= n_grid:
            col_min = arr
            col_max = arr
            self.song_wave_n = n
        else:
            step = n // n_grid
            g = arr[: n_grid * step].reshape(n_grid, step)
            col_min = g.min(axis=1)
            col_max = g.max(axis=1)
            self.song_wave_n = n_grid
        peak = max(float(_np.abs(col_max).max()),
                   float(_np.abs(col_min).max()), 1e-9)
        col_min = col_min / peak
        col_max = col_max / peak
        # Realce suave (gamma) para que los ataques del bajo se lean aunque el
        # pico global de la canción sea mucho mayor que el fragmento visible.
        _g = 0.7
        col_min = _np.sign(col_min) * _np.abs(col_min) ** _g
        col_max = _np.sign(col_max) * _np.abs(col_max) ** _g
        self.song_wave = (col_min, col_max)

    def _align_build_waveform(self):
        """Rejilla fina min/max de TODO el MP3, calculada una sola vez.
        El zoom/pan solo recorta qué columnas se dibujan."""
        if getattr(self, "song_wave", None) is None:
            self._build_song_waveform()
        self.align_wave      = self.song_wave
        self.align_wave_n    = self.song_wave_n
        self.align_total_sec = self.song_total_sec

    @staticmethod
    def _align_entry(e):
        """Normaliza una entrada del mapa de tempo a (s16, qpm, unidad)."""
        if len(e) >= 3:
            return (float(e[0]), float(e[1]), e[2] or "quarter")
        return (float(e[0]), float(e[1]), "quarter")

    def _align_normalize(self, tmap):
        out = sorted([self._align_entry(e) for e in tmap])
        merged = []
        for s16, qpm, unit in out:
            if merged and merged[-1][0] == s16:
                merged[-1] = (s16, qpm, unit)
            else:
                merged.append((s16, qpm, unit))
        if not merged:
            return [(0.0, 60.0, "quarter")]
        # Las posiciones s16 son >= 0: si el mapa no arranca en cero, se antepone
        # una entrada en 0. Comparar con > evita la igualdad de floats (S1244).
        if merged[0][0] > 0.0:
            merged.insert(0, (0.0, merged[0][1], merged[0][2]))
        return merged

    def _align_px_of_sec(self, sec):
        if self.align_view_span <= 0:
            return self._align_x0
        frac = (sec - self.align_view_start) / self.align_view_span
        return int(self._align_x0 + frac * self._align_w)

    def _align_mark_px(self, mp3):
        """Pixel X de una marca. Si coincide con la línea roja (inicio del
        bajo), se dibuja 3px a la derecha para distinguirla y poder arrastrarla."""
        x = self._align_px_of_sec(mp3)
        if abs(mp3 - self.ed_offset) < 1.0:
            x = min(x + 3, self._align_x0 + self._align_w)
        return x

    def _align_sec_of_pos(self, pos):
        mx = pos[0]
        frac = (mx - self._align_x0) / max(1, self._align_w)
        return max(0.0, min(self.align_total_sec,
                           self.align_view_start + frac * self.align_view_span))

    def _align_zoom(self, factor, pos=None):
        """factor>1 acerca. Mantiene la posición bajo el puntero fija."""
        total = self.align_total_sec
        if total <= 0:
            return
        sec = self._align_sec_of_pos(pos) if pos else self.align_cursor_sec
        new_span = max(2.0, min(total, self.align_view_span / factor))
        frac = (sec - self.align_view_start) / max(1e-6, self.align_view_span)
        self.align_view_start = max(0.0, min(total - new_span,
                                             sec - frac * new_span))
        self.align_view_span = new_span

    def _align_pan_to(self, mx):
        span = self.align_view_span
        dx = (mx - self.align_pan_start[0]) / max(1, self._align_w) * span
        self.align_view_start = max(0.0, min(self.align_total_sec - span,
                                             self.align_pan_view_start - dx))

    def _align_keep_cursor_visible(self):
        if self.align_view_span <= 0:
            return
        vs = self.align_view_start
        ve = vs + self.align_view_span
        c  = self.align_cursor_sec
        if c < vs:
            self.align_view_start = max(0.0, c - self.align_view_span * 0.1)
        elif c > ve:
            self.align_view_start = min(self.align_total_sec - self.align_view_span,
                                        c - self.align_view_span * 0.9)

    def _align_active_marker_sec(self):
        """mp3_sec del marcador de tempo vigente (último cuya posición ≤ cursor)."""
        c = self.align_cursor_sec
        active = self.ed_offset
        for e in self.ed_tempo_map:
            if e[0] <= c:
                active = e[0]
        return active

    def _align_set_offset_from_mouse(self, pos):
        new_off = max(0.0, round(self._align_sec_of_pos(pos), 2))
        if self.ed_offset != new_off:
            # El inicio de canción no puede quedar después de la entrada.
            if self.song_start_sec > new_off - 0.02:
                self.song_start_sec = max(0.0, new_off - 0.02)
            # Las marcas que aún siguen "lo que dice la partitura" se mueven
            # con la línea roja; las fijadas a mano se quedan donde están.
            for e in self.ed_tempo_map:
                if len(e) >= 4 and e[3] is not None:
                    e[0] = round(self._mp3_sec_of_s16(e[3], new_off,
                                                      self.score_tempo_map), 2)
            self.ed_offset = new_off
        self.align_cursor_sec = self.ed_offset

    def _align_set_song_start_from_mouse(self, pos):
        """Mueve el ancla verde (compás 1); la entrada del bajo no se toca."""
        sec = max(0.0, min(self._align_sec_of_pos(pos),
                           max(0.0, self.ed_offset - 0.02)))
        self.song_start_sec = round(sec, 2)
        s0 = self._bass_start16()
        for e in self.ed_tempo_map:
            if len(e) >= 4 and e[3] is not None and float(e[3]) <= s0:
                e[0] = round(self._mp3_sec_of_s16(float(e[3]), self.ed_offset,
                                                  self.score_tempo_map), 2)
        self.align_cursor_sec = self.song_start_sec

    def _align_add_marker(self, pos):
        if self.align_total_sec <= 0:
            return
        sec = round(self._align_sec_of_pos(pos), 2)
        self.align_cursor_sec = sec
        active = self._align_active_marker_sec()
        qpm  = next((e[1] for e in self.ed_tempo_map if e[0] == active),
                    (self.tempo_map[0][1] if self.tempo_map else 60.0))
        unit = next((e[2] for e in self.ed_tempo_map if e[0] == active),
                    "quarter")
        self.ed_tempo_map.append([sec, qpm, unit, None])

    def _align_adjust_bpm(self, delta):
        active = self._align_active_marker_sec()
        for e in self.ed_tempo_map:
            if e[0] == active:
                e[1] = max(20.0, min(300.0, e[1] + delta))

    def _align_delete_marker(self):
        active = self._align_active_marker_sec()
        if not self.ed_tempo_map or active == self.ed_offset:
            return
        self.ed_tempo_map = [e for e in self.ed_tempo_map if e[0] != active]

    def _align_marker_at_pos(self, pos):
        """mp3_sec de la marca verde de tempo más cercana al pixel (o None)."""
        x = pos[0]
        best = None
        best_d = 12
        for e in self.ed_tempo_map:
            xm = self._align_mark_px(e[0])
            d = abs(x - xm)
            if d < best_d:
                best_d = d
                best = e[0]
        return best

    def _align_redline_at_pos(self, pos):
        """True si el clic cae sobre la línea roja (inicio del bajo)."""
        return abs(pos[0] - self._align_px_of_sec(self.ed_offset)) <= 12

    def _align_pick_at_pos(self, pos):
        """Devuelve (tipo, id) del elemento bajo el ratón:
        ('red', None) línea roja · ('mark', mp3) marca verde ·
        ('ghost', idx) referencia de la partitura (cian) · (None, None).
        En empate, gana la línea roja (el inicio del bajo)."""
        x      = pos[0]
        best   = (None, None)
        best_d = 12
        smap   = self._ed_tmap_s16()
        for e in self.ed_tempo_map:
            d = abs(x - self._align_mark_px(e[0]))
            if d < best_d:
                best_d, best = d, ("mark", e[0])
        for i, e in enumerate(self.score_tempo_map):
            s16 = e[0]
            if s16 <= 0:
                continue
            sec = self._mp3_sec_of_s16(s16, self.ed_offset, smap)
            if any(abs(m[0] - sec) <= 0.5 for m in self.ed_tempo_map):
                continue   # ya hay una marca verde encima
            d = abs(x - self._align_px_of_sec(sec))
            if d < best_d:
                best_d, best = d, ("ghost", i)
        ds = abs(x - self._align_px_of_sec(self.song_start_sec))
        if ds <= best_d and ds <= 12:
            best_d, best = ds, ("start", None)
        dl = abs(x - self._align_px_of_sec(self.ed_offset))
        if dl <= best_d:
            best = ("red", None)
        return best

    def _align_drag_marker_to(self, pos):
        """Mueve la marca arrastrada (por su mp3_sec, sin reordenar).
        Al moverla a mano deja de seguir a la partitura."""
        sec = self._align_sec_of_pos(pos)
        for e in self.ed_tempo_map:
            if e[0] == self.align_drag_marker:
                e[0] = sec
                if len(e) >= 4:
                    e[3] = None
                self.align_drag_marker = sec
                break
        self.align_cursor_sec = sec

    def _align_toggle_play(self):
        if self.align_playing:
            self.align_playing = False
            pygame.mixer.music.stop()
            return
        if not self.mp3_path:
            return
        try:
            pygame.mixer.music.load(self.mp3_path)
            pygame.mixer.music.play(start=max(0.0, self.align_cursor_sec))
            self.align_playing = True
        except Exception as e:
            log.info(f"[Editor] no puedo reproducir: {e}")

    def _align_detect(self):
        if self.align_detecting or self.align_wave is None:
            return
        self.align_detecting = True
        self.align_detected_tempo = None
        threading.Thread(target=self._align_detect_worker, daemon=True).start()

    def _align_detect_worker(self):
        try:
            import librosa as _librosa
            vsp = self._vsp
            y   = vsp.data_orig[:, 0]
            sr  = vsp.sr
            t0  = time.time()
            tempo  = float(_librosa.beat.tempo(y=y, sr=sr)[0])
            onsets = _librosa.onset.onset_detect(y=y, sr=sr, backtrack=True)
            self.align_onsets = list(_librosa.frames_to_time(onsets, sr=sr))
            self.align_detected_tempo = round(tempo, 1)
            log.info(f"[Editor] tempo estimado {tempo:.1f} BPM  "
                  f"onsets={len(self.align_onsets)}  ({time.time()-t0:.1f}s)")
        except Exception as e:
            log.info(f"[Editor] detección falló: {e}")
        finally:
            self.align_detecting = False

    def _hz_to_fret_string(self, hz):
        best = None
        best_diff = 999.0
        m_det = 12 * math.log2(hz / 440) + 69
        for s in range(1, 5):
            for f in range(NECK_FRETS + 1):
                m_note = 12 * math.log2(fret_to_hz(f, s) / 440) + 69
                diff   = abs(m_det - m_note)
                if diff < best_diff:
                    best_diff = diff
                    best = (f, s)
        return best if best_diff < 0.75 else None

    # ══════════════════════════════════════════════════════════════════
    #  MODO APRENDIZAJE — pulsar mástil / piano con el ratón
    # ══════════════════════════════════════════════════════════════════
    @staticmethod
    def _midi_to_hz(midi: int) -> float:
        return 440.0 * (2 ** ((int(midi) - 69) / 12.0))

    @staticmethod
    def _build_tone(hz: float, duration: float = 0.9):
        """Sintetiza un tono de bajo (fundamental + armónicos) como Sound."""
        import numpy as np
        SR = 44100
        hz = max(20.0, min(2000.0, float(hz)))
        n  = max(1, int(SR * duration))
        t  = np.linspace(0, duration, n, endpoint=False)
        # Ataque corto para evitar clic + caída exponencial tipo bajo
        attack = min(n, int(SR * 0.012))
        env = np.exp(-t * 3.2)
        if attack > 0:
            env[:attack] *= np.linspace(0, 1, attack)
        wave = (np.sin(2 * np.pi * hz * t)
                + 0.35 * np.sin(4 * np.pi * hz * t) * np.exp(-t * 2.0)
                + 0.18 * np.sin(6 * np.pi * hz * t) * np.exp(-t * 3.0))
        wave = (wave * env * 22000).astype(np.int16)
        stereo = np.column_stack([wave, wave])
        return pygame.sndarray.make_sound(np.ascontiguousarray(stereo))

    def preview_note(self, hz, name, label, fret_str=None, midi=None):
        """Muestra y hace sonar una nota pulsada (no interfiere con la canción)."""
        try:
            if hz and hz > 0:
                self.view._preview_sound = self._build_tone(hz)
                self.view._preview_sound.play()
        except Exception as e:
            log.info(f"[Preview] no puedo sonar: {e}")
        self.view.preview_hz       = float(hz or 0.0)
        self.view.preview_name     = name or "—"
        self.view.preview_label    = label or ""
        self.view.preview_timer    = 2.5
        self.view.preview_fret_str = fret_str
        self.view.preview_midi     = midi

    def _neck_hit(self, pos):
        """(fret, string) bajo el cursor o None. Replica la geometría de draw_neck."""
        try:
            mx, my = int(pos[0]), int(pos[1])
        except Exception:
            return None
        if not (0 <= mx < NECK_W and NECK_Y <= my < NECK_Y + NECK_H):
            return None
        STR_MARG = 14
        ss = (NECK_H - STR_MARG * 2 - 16) / 3
        str_y = {s: NECK_Y + STR_MARG + ss * (s - 1) for s in range(1, 5)}
        # Cuerda más cercana (tolerancia ~ media distancia entre cuerdas)
        best_s, best_d = None, 1e9
        for s, y in str_y.items():
            d = abs(my - y)
            if d < best_d:
                best_d, best_s = d, s
        if best_s is None or best_d > (ss * 0.6 + 4):
            return None
        if mx < NECK_AREA_X:
            fret = 0
        else:
            fret_space = NECK_AREA_W / max(1, NECK_FRETS)
            fret = int((mx - NECK_AREA_X) // fret_space) + 1
            fret = max(0, min(NECK_FRETS, fret))
        return (fret, best_s)

    def _piano_hit(self, pos):
        """MIDI de la tecla bajo el cursor o None (las negras tienen prioridad)."""
        try:
            mx, my = int(pos[0]), int(pos[1])
        except Exception:
            return None
        if not (PIANO_X <= mx < PIANO_X + PIANO_W
                and PIANO_Y <= my < PIANO_Y + PIANO_H):
            return None
        if not self._piano_keys_list:
            from .ui import build_piano_keys
            self._piano_keys_list = build_piano_keys(
                PIANO_START_MIDI, PIANO_END_MIDI,
                PIANO_X, PIANO_Y, PIANO_W, PIANO_H)
        # Dos pasadas: primero negras (están encima), luego blancas
        for black_first in (True, False):
            for key in self._piano_keys_list:
                if key["black"] != black_first:
                    continue
                if key["rect"].collidepoint(mx, my):
                    return key["midi"]
        return None

    def _preview_from_neck(self, fret, string):
        hz   = fret_to_hz(fret, string)
        name = hz_to_note_name(hz)
        label = f"{name} · traste {fret} · cuerda {STRING_NAMES[string]}"
        # Enlace cruzado: también ilumina la tecla del piano correspondiente
        midi = int(round(12 * math.log2(hz / 440.0) + 69)) if hz > 0 else None
        self.preview_note(hz, name, label,
                          fret_str=(fret, string), midi=midi)

    def _preview_from_piano(self, midi):
        hz   = self._midi_to_hz(midi)
        name = hz_to_note_name(hz)
        label = f"{name} · piano · {hz:.1f} Hz"
        # Enlace cruzado: también ilumina la posición en el mástil (si existe)
        try:
            fret_str = self._hz_to_fret_string(hz) if hz > 0 else None
        except Exception:
            fret_str = None
        self.preview_note(hz, name, label,
                          fret_str=fret_str, midi=int(midi))

    # ══════════════════════════════════════════════════════════════════
    #  CONTROLES
    # ══════════════════════════════════════════════════════════════════
    def _total16(self):
        if not self.notes:
            return 0
        return int(self.notes[-1]["start16"] + self.notes[-1]["dur"])

    def bar_starts16(self):
        """Inicios de compás (start16) para la rejilla visual y el snap.

        Usa los compases reales del MusicXML (respeta anacrusas/cambios de
        compás); si no hay, cae a múltiplos de `beats_per_bar` tiempos.
        """
        if self.measure_starts:
            return sorted({int(s) for _n, s in self.measure_starts})
        bar16 = max(4, int(self.beats_per_bar) * 4)
        return list(range(0, self._total16() + 1, bar16))

    def _measure_starts(self):
        """Devuelve lista ordenada de posiciones start16 del inicio de cada compás."""
        bars = self.bar_starts16()
        if bars:
            return bars
        seen = {}
        for note in self.notes:
            m = note["measure_num"]
            if m not in seen:
                seen[m] = note["start16"]
        return sorted(seen.values())

    def measure_starts_visual(self):
        """Inicios de compás en la rejilla DIBUJADA (desplazada por la fase).

        La tira, el waveform, la tab y la partitura pintan los compases en
        `start16 + grid_phase16()` (la fase alinea la rejilla con la entrada
        del bajo), así que el snap tiene que apuntar ahí: si apunta a la
        rejilla "cruda" el cursor queda una fracción de compás a la izquierda
        de la línea que se ve (p. ej. 1/16 en Ayer Hable Con Dios).
        """
        phase = int(self.grid_phase16())
        out = []
        for s in self._measure_starts():
            s = float(s)
            out.append(s + phase if s > 1e-9 else s)
        return out

    def _snap_measure(self, direction: int):
        """
        Salta al inicio del compás anterior (direction=-1) o siguiente (+1).
        Si ya estamos al inicio del compás actual, retrocede al compás anterior.
        """
        starts = self.measure_starts_visual()
        if not starts:
            return
        cur = self.beat_time
        TOL = 0.5  # tolerancia en 16avos para considerar "ya en el inicio"

        if direction > 0:
            target = None
            for s in starts:
                if s > cur + TOL:
                    target = s
                    break
            if target is None:
                target = starts[-1]
        else:
            target = starts[0]
            for s in starts:
                if s < cur - TOL:
                    target = s
        self._seek_to_beat(target)

    def _seek_to_beat(self, beat16: float):
        """Salta la reproducción a una posición concreta (en 16avos)."""
        beat16 = max(0.0, float(beat16))
        self.beat_time  = beat16
        self.view.viewport_x = max(0.0, float(self.px_of(beat16)))
        self.view.target_x   = self.view.viewport_x

        # Hacer que la partitura salte sin animación (misma base que draw_score)
        from .ui.draw_score import score_img_x
        self.view._score_scroll_x = (score_img_x(self, beat16)
                                     if self.view._score_surf is not None
                                     else 0.0)

        # Actualizar note_idx: primer nota que no haya pasado aún
        self.note_idx = len(self.notes)
        for i, note in enumerate(self.notes):
            if note["start16"] + note["dur"] > beat16:
                self.note_idx = i
                break

        # Seek del audio si está reproduciendo
        if self.playing:
            offset = self._mp3_sec_of_s16(beat16)
            self._stop_mp3()
            self._play_mp3(offset)

    def toggle_play(self):
        if self.counting_down:
            self.counting_down = False
            self._stop_mp3()
            return
        if self.playing:
            self.playing = False
            self._stop_mp3()
        else:
            if self.countdown_enabled:
                self.counting_down  = True
                self.countdown_beat = self.beats_per_bar
                self.countdown_timer = 0.0
            else:
                self._begin_play()

    def _begin_play(self):
        self.playing = True
        # Click del tiempo de arranque si empezamos justo en un tiempo: sin esto
        # el primer click audible sería el tiempo 2 (el 1 no tiene transición).
        q = self.beat_time / 4.0
        if abs(q - round(q)) < 0.15:
            self.metro_beat  = int(round(q)) % self.beats_per_bar
            self.metro_flash = 1.0
            self._play_click(self.metro_beat == 0)
        # La canción muteada sigue sonando a volumen 0: así el playhead y la
        # pista de bajo no se desincronizan al silenciar/escuchar.
        self._play_mp3(self._mp3_sec_of_s16(self.beat_time))

    def _want_vsp(self):
        # Usar time-stretch (varispeed/sounddevice) solo cuando hay un cambio
        # real de tempo; con rate=1 el camino pygame (calibrado) mantiene la
        # misma sincronización en dev y en el standalone.
        return bool(self._vsp and self._vsp.loaded
                    and abs(self._speed_ratio() - 1.0) >= 0.005)

    # ══════════════════════════════════════════════════════════════════
    #  MIXER (F2) — canción / bajo / metrónomo
    # ══════════════════════════════════════════════════════════════════
    MIX_TRACKS = (
        ("song",  "Canción",   "pista del MP3"),
        ("bass",  "Bajo",      "línea de referencia"),
        ("band",  "Banda",     "batería + piano + guitarra"),
        ("click", "Metrónomo", "clicks"),
    )

    def _mix_get(self, tid):
        """(volumen, mute) de una pista del mixer."""
        if tid == "bass":
            return self.mix_bass, self.muted_bass
        if tid == "band":
            return self.mix_band, self.muted_band
        if tid == "click":
            return self.mix_click, self.muted_click
        return self.mix_song, self.muted

    def _mix_set(self, tid, vol=None, mute=None):
        vol  = None if vol is None else max(0.0, min(1.0, float(vol)))
        if tid == "bass":
            if vol is not None:
                self.mix_bass = vol
            if mute is not None:
                self.muted_bass = bool(mute)
        elif tid == "band":
            if vol is not None:
                self.mix_band = vol
            if mute is not None:
                self.muted_band = bool(mute)
        elif tid == "click":
            if vol is not None:
                self.mix_click = vol
            if mute is not None:
                self.muted_click = bool(mute)
        else:
            if vol is not None:
                self.mix_song = vol
            if mute is not None:
                self.muted = bool(mute)
        self._apply_mix()

    def _bass_volume(self):
        return 0.0 if self.muted_bass else self.mix_bass

    def _band_volume(self):
        return 0.0 if self.muted_band else self.mix_band

    def _apply_mix(self):
        """Lleva los niveles del mixer al mixer de pygame (idempotente)."""
        try:
            pygame.mixer.music.set_volume(
                0.0 if self.muted else self.mix_song)
        except Exception:
            pass
        try:
            if self._bass_ch is not None:
                self._bass_ch.set_volume(self._bass_volume())
            if self._band_ch is not None:
                self._band_ch.set_volume(self._band_volume())
        except Exception:
            pass
        if self._vsp is not None:
            try:
                self._vsp.set_volume(0.0 if self.muted else self.mix_song)
                self._vsp.set_extra_volume(self._bass_volume())
                self._vsp.set_extra2_volume(self._band_volume())
            except Exception:
                pass
        click = 0.0 if self.muted_click else self.mix_click
        for snd in (getattr(self, "_click_hi", None),
                    getattr(self, "_click_lo", None)):
            try:
                if snd is not None:
                    snd.set_volume(click)
            except Exception:
                pass

    def _bass_audio_for(self, ratio=1.0):
        """Audio pre-renderizado de la línea de bajo (cacheado por canción,
        anclas y tempo). ``ratio`` < 1 alarga las notas para el varispeed."""
        marker = getattr(self, "bass_midi", None)
        if marker and self.mid_path and os.path.isfile(self.mid_path):
            audio = self._bass_audio_from_midi(ratio, marker)
            if audio is not None:
                return audio
        notes = self.notes
        if not notes:
            return None
        try:
            key = (self.song_name, len(notes), round(float(ratio), 4),
                   round(self.mp3_offset_sec, 4),
                   round(getattr(self, "song_start_sec", 0.0), 4),
                   tuple((int(e[0]), round(float(e[1]), 3))
                         for e in (self.tempo_map or [])))
        except Exception:
            key = (self.song_name, len(notes), round(float(ratio), 4))
        if self._bass_audio is not None and self._bass_key == key:
            return self._bass_audio
        events = []
        inv = 1.0 if abs(ratio - 1.0) < 1e-6 else 1.0 / max(0.1, float(ratio))
        for n in notes:
            hz = float(n.get("hz") or 0.0)
            if hz <= 0.0:
                continue
            s16 = n["start16"]
            t0  = self._mp3_sec_of_s16(s16) * inv
            dur = (self._song_seconds(s16 + n["dur"])
                   - self._song_seconds(s16)) * inv
            events.append((t0, max(0.03, dur), _bass_hz_to_midi(hz)))
        if not events:
            self._bass_audio, self._bass_key = None, key
            return None
        total = max(t + d for t, d, _ in events)
        t_start = time.perf_counter()
        audio = render_bass(events, total)
        self._bass_render_s = time.perf_counter() - t_start
        self._bass_audio, self._bass_key = audio, key
        log.info(f"[Mixer] bajo pre-renderizado: {len(audio) / SAMPLERATE:.1f}s "
                 f"en {self._bass_render_s * 1000:.0f} ms  ({bass_backend()})")
        return audio

    def _bass_audio_from_midi(self, ratio, marker):
        """Bajo renderizado desde el canal de bajo del MIDI de JJazzLab.

        Así suenan el swing, el microtiming y las velocidades reales del
        motor, sin re-cuantizar a 16avos. Devuelve ``None`` para que se use
        el render interno si no hay SoundFont o falla el MIDI.
        """
        try:
            channel = int(marker.get("bass_channel"))
        except (TypeError, ValueError):
            return None
        try:
            mtime = round(os.path.getmtime(self.mid_path), 3)
        except OSError:
            return None
        try:
            key = (self.song_name, self.mid_path, mtime,
                   round(float(ratio), 4), channel)
        except (TypeError, ValueError):
            key = (self.song_name, self.mid_path, mtime, channel)
        if self._bass_audio is not None and self._bass_key == key:
            return self._bass_audio
        t_start = time.perf_counter()
        audio = render_band_midi(self.mid_path, ratio,
                                 only_channels={channel})
        if audio is None:
            return None
        self._bass_render_s = time.perf_counter() - t_start
        self._bass_audio, self._bass_key = audio, key
        log.info(f"[Mixer] bajo JJazzLab (canal {channel}): "
                 f"{len(audio) / SAMPLERATE:.1f}s en "
                 f"{self._bass_render_s * 1000:.0f} ms")
        return audio

    def _prefetch_band(self):
        """Pre-renderiza la banda en segundo plano al cargar la canción."""
        if not (self.chord_events or self.mid_path):
            return
        if self.mid_path:
            if not band_midi_available():
                return
        elif not band_available():
            return

        def work():
            try:
                self._band_audio_for(self._speed_ratio())
            except Exception as e:
                log.warning(f"[Band] prefetch: {e}")

        threading.Thread(target=work, daemon=True).start()

    def _band_audio_for(self, ratio=1.0):
        """Banda (batería/piano/guitarra) pre-renderizada desde el cifrado.

        Sigue el mismo criterio temporal que el bajo: tiempos del MP3
        (``_mp3_sec_of_s16``) y estirado ``1/ratio`` para el varispeed.
        """
        if self.mid_path:
            if not band_midi_available() and not band_available():
                return None
        elif not self.chord_events or not band_available():
            return None
        if not (self.chord_events or self.mid_path):
            return None
        try:
            key = (self.song_name,
                   self.mid_path,
                   round(os.path.getmtime(self.mid_path), 3)
                   if self.mid_path and os.path.isfile(self.mid_path) else 0,
                   (self.bass_midi or {}).get("bass_channel"),
                   tuple((round(float(s), 3), str(n)) for s, n in self.chord_events),
                   round(float(ratio), 4),
                   round(self.mp3_offset_sec, 4),
                   round(getattr(self, "song_start_sec", 0.0), 4),
                   tuple((int(e[0]), round(float(e[1]), 3))
                         for e in (self.tempo_map or [])))
        except Exception:
            key = (self.song_name, len(self.chord_events),
                   round(float(ratio), 4))
        if self._band_audio is not None and self._band_key == key:
            return self._band_audio
        with self._band_lock:
            if self._band_audio is not None and self._band_key == key:
                return self._band_audio
            return self._render_band_locked(key, ratio)

    def _render_band_locked(self, key, ratio):
        t_start = time.perf_counter()
        try:
            audio = None
            if self.mid_path and band_midi_available():
                exclude = None
                marker = getattr(self, "bass_midi", None)
                if marker:
                    try:
                        exclude = {int(marker.get("bass_channel"))}
                    except (TypeError, ValueError):
                        exclude = None
                audio = render_band_midi(self.mid_path, ratio,
                                         exclude_channels=exclude)
                self._band_render_s = time.perf_counter() - t_start
                if audio is not None:
                    self._band_audio, self._band_key = audio, key
                    log.info(f"[Band] MIDI externo {os.path.basename(self.mid_path)}"
                             f"{' (sin bajo)' if exclude else ''}"
                             f": {len(audio) / SAMPLERATE:.1f}s en "
                             f"{self._band_render_s * 1000:.0f} ms")
                    return audio
                log.warning("[Band] el .mid no se pudo renderizar; "
                            "uso la banda generada")
            if not self.chord_events or not band_available():
                self._band_audio, self._band_key = None, key
                return None
            chords = []
            for sec, name in self.chord_events:
                s16 = self._song_seconds_inverse(float(sec))
                chords.append((self._mp3_sec_of_s16(s16), str(name)))
            if self.notes:
                end16 = max(n["start16"] + n["dur"] for n in self.notes)
                total = self._mp3_sec_of_s16(end16)
            else:
                total = chords[-1][0] + 4.0 * 60.0 / max(1.0, self.bpm_original)
            audio = render_band(chords, self.bpm_original,
                                self.beats_per_bar, total, ratio)
            self._band_render_s = time.perf_counter() - t_start
        except Exception as e:
            log.warning(f"[Band] no puedo generar la banda: {e}")
            audio = None
        self._band_audio, self._band_key = audio, key
        if audio is not None:
            log.info(f"[Band] banda pre-renderizada: "
                     f"{len(audio) / SAMPLERATE:.1f}s en "
                     f"{self._band_render_s * 1000:.0f} ms")
        return audio

    def _prepare_band(self, offset_sec=0.0):
        self._band_pending = None
        if self._use_vsp:
            return
        audio = self._band_audio_for(self._speed_ratio())
        if audio is None:
            return
        start = int(max(0.0, float(offset_sec)) * SAMPLERATE)
        if start >= len(audio) - 64:
            return
        try:
            self._band_pending = pygame.sndarray.make_sound(
                to_int16(audio[start:]))
        except Exception as e:
            log.warning(f"[Mixer] no puedo crear el Sound de la banda: {e}")

    def _start_band(self):
        snd, self._band_pending = self._band_pending, None
        if snd is None:
            return
        self._band_sound = snd
        try:
            if self._band_ch is None:
                self._band_ch = pygame.mixer.Channel(1)
            self._band_ch.stop()
            self._band_ch.play(snd)
            self._band_ch.set_volume(self._band_volume())
        except Exception as e:
            log.warning(f"[Mixer] no puedo reproducir la banda: {e}")

    def _prepare_bass(self, offset_sec=0.0):
        """Deja listo (render + pygame.Sound) el tramo de bajo a reproducir.

        Se hace ANTES de arrancar el MP3: el render del SoundFont tarda
        ~100 ms y si se hiciera después el bajo entraría tarde.
        """
        self._bass_pending = None
        if self._use_vsp:
            return                       # lo mezcla VarispeedPlayer
        audio = self._bass_audio_for(self._speed_ratio())
        if audio is None:
            return
        start = int(max(0.0, float(offset_sec)) * SAMPLERATE)
        if start >= len(audio) - 64:
            return
        try:
            self._bass_pending = pygame.sndarray.make_sound(to_int16(audio[start:]))
        except Exception as e:
            log.warning(f"[Mixer] no puedo crear el Sound del bajo: {e}")

    def _start_bass(self):
        """Arranca el Sound preparado en el canal reservado (canal 0)."""
        snd, self._bass_pending = self._bass_pending, None
        if snd is None:
            return
        self._bass_sound = snd
        try:
            if self._bass_ch is None:
                self._bass_ch = pygame.mixer.Channel(0)
            self._bass_ch.stop()
            self._bass_ch.play(snd)
            self._bass_ch.set_volume(self._bass_volume())
        except Exception as e:
            log.warning(f"[Mixer] no puedo reproducir el bajo: {e}")

    def _play_mp3(self, offset_sec=0.0):
        self._use_vsp = self._want_vsp()
        self._prepare_bass(offset_sec)
        self._prepare_band(offset_sec)
        if self._use_vsp:
            self._vsp.set_speed(self._speed_ratio())
            self._vsp.play(offset_sec)
        elif self._pgm_loaded:
            start_ms = max(0, int(offset_sec * 1000))
            pygame.mixer.music.play(start=start_ms / 1000.0)
        self._start_bass()
        self._start_band()
        self._apply_mix()

    def _pause_mp3(self):
        if self._use_vsp:
            self._vsp.pause()
        elif self._pgm_loaded:
            pygame.mixer.music.pause()
        try:
            if self._bass_ch is not None:
                self._bass_ch.pause()
            if self._band_ch is not None:
                self._band_ch.pause()
        except Exception:
            pass

    def _resume_mp3(self):
        if self._use_vsp:
            self._vsp.resume()
        elif self._pgm_loaded:
            pygame.mixer.music.unpause()
        try:
            if self._bass_ch is not None:
                self._bass_ch.unpause()
            if self._band_ch is not None:
                self._band_ch.unpause()
        except Exception:
            pass

    def _stop_mp3(self, fade_ms=0):
        if self._use_vsp:
            self._vsp.stop()
        elif self._pgm_loaded:
            if fade_ms:
                pygame.mixer.music.fadeout(fade_ms)
            else:
                pygame.mixer.music.stop()
        try:
            for ch in (self._bass_ch, self._band_ch):
                if ch is not None:
                    if fade_ms:
                        ch.fadeout(fade_ms)
                    else:
                        ch.stop()
        except Exception:
            pass

    def reiniciar(self):
        self.playing       = False
        self.counting_down = False
        self.note_idx      = 0
        self.beat_time     = 0.0
        self.view.viewport_x    = 0.0
        self.view.target_x      = 0.0
        self.score_ok      = 0
        self.score_total   = 0
        self.note_match    = None
        self.view._score_scroll_x = 0.0
        self._stop_mp3()
        for d in self.section_stats.values():
            d["ok"] = 0; d["total"] = 0

    def ajustar_offset(self, delta):
        """Mueve SOLO la entrada del bajo (línea roja): el inicio de canción
        queda fijo y se estira/encoge el silencio inicial."""
        self.mp3_offset_sec += delta
        self._clamp_anchors()
        if self.playing:
            offset = self._mp3_sec_of_s16(self.beat_time)
            self._stop_mp3()
            self._play_mp3(offset)

    def ajustar_inicio(self, delta):
        """Mueve SOLO el inicio de canción / compás 1 (línea verde)."""
        self.song_start_sec += delta
        self._clamp_anchors()
        if self.playing:
            offset = self._mp3_sec_of_s16(self.beat_time)
            self._stop_mp3()
            self._play_mp3(offset)

    def ajustar_bpm(self, delta):
        before = self._speed_ratio()
        self.bpm = max(40, min(300, self.bpm + delta))
        after = self._speed_ratio()
        if abs(after - before) < 1e-9:
            return
        if self._vsp and self._vsp.loaded:
            self._vsp.set_speed(after)
        if not self.playing:
            return
        if self._use_vsp:
            return                    # el swap del VSP recoloca todo
        if self._vsp and self._vsp.loaded:
            # pygame -> VSP: reiniciar; el hilo de estiramiento ya esta
            # re-renderizando el bajo y la banda al nuevo ratio.
            offset = self._mp3_sec_of_s16(self.beat_time)
            self._stop_mp3()
            self._play_mp3(offset)
            return
        # Sin MP3/VSP el bajo y la banda están pre-renderizados a ritmo fijo:
        # hay que re-renderizarlos al nuevo tempo y re-sincronizar después.
        if abs(after - 1.0) >= 0.005:
            self._resync_target = after

    def _poll_resync(self):
        """Re-renderiza bajo/banda al nuevo tempo (camino sin Varispeed)."""
        if self._resync_ready is not None:
            ratio, self._resync_ready = self._resync_ready, None
            if self.playing and abs(self._speed_ratio() - ratio) < 1e-6:
                offset = self._mp3_sec_of_s16(self.beat_time)
                self._stop_mp3()
                self._play_mp3(offset)
            return
        if self._resync_target is None or self._resync_busy:
            return
        ratio, self._resync_target = self._resync_target, None
        self._resync_busy = True

        def work():
            try:
                self._bass_audio_for(ratio)
                self._band_audio_for(ratio)
            except Exception as e:
                log.warning(f"[Mixer] no puedo re-renderizar al tempo {ratio:.3f}: {e}")
            finally:
                self._resync_busy = False
                self._resync_ready = ratio

        threading.Thread(target=work, daemon=True).start()

    def toggle_mute(self):
        self.muted = not self.muted
        self._apply_mix()

    def cycle_score_renderer(self):
        if self.score_renderer == "verovio" and MUSIC21_OK:
            self.score_renderer  = "music21"
            self.view._score_surf     = None
            self.view._score_note_xs  = []
            self.view._score_scroll_x = 0.0
            self._init_score_music21()
        elif VEROVIO_OK and CAIROSVG_OK:
            self.score_renderer  = "verovio"
            self.view._score_surf     = None
            self.view._score_note_xs  = []
            self.view._score_scroll_x = 0.0
            self._init_score_verovio()

    # ══════════════════════════════════════════════════════════════════
    #  UPDATE
    # ══════════════════════════════════════════════════════════════════
    def update(self, dt):
        self._t += dt
        self._poll_generation()
        self._poll_resync()
        if self._gen_msg_timer > 0:
            self._gen_msg_timer = max(0.0, self._gen_msg_timer - dt)
        if self._config_msg_timer > 0:
            self._config_msg_timer = max(0.0, self._config_msg_timer - dt)
        if self.view.preview_timer > 0:
            self.view.preview_timer = max(0.0, self.view.preview_timer - dt)
            if self.view.preview_timer <= 0:
                self.view.preview_fret_str = None
                self.view.preview_midi     = None

        # ── Editor de alineación: reproducción natural del MP3 ─────────
        if self.align_editor_open:
            if self.align_playing:
                self.align_cursor_sec = min(self.align_total_sec,
                                            self.align_cursor_sec + dt)
                self._align_keep_cursor_visible()
                if (self.align_cursor_sec >= self.align_total_sec
                        or not pygame.mixer.music.get_busy()):
                    self.align_playing = False
                    pygame.mixer.music.stop()
            return

        # ── Nota detectada para Guitar Hero (funciona aunque esté pausado) ──
        with self.pitch_lock:
            _hz = self.stable_hz
        self.detected_fret_str = self._hz_to_fret_string(_hz) if _hz > 0 else None

        # ── Entrenador: validar el objetivo con el micro (pausado o tocando) ──
        if self.training_open and self.tr_target_midi is not None:
            if (_hz > MIN_HZ and self.tr_target_hz > 0
                    and notes_match(_hz, self.tr_target_hz)):
                self.tr_hold += dt
                if self.tr_hold >= self.tr_hold_need:
                    self._training_success()
            else:
                self.tr_hold = max(0.0, self.tr_hold - dt * 2.0)

        # ── Walking Lab: pulso de negras + escucha por tiempo ─────────
        if self.lab_open and self.lab_running and self.lab_steps:
            self.lab_t += dt
            spb = 60.0 / max(20.0, self.lab_bpm)
            total = int(self.lab_t // spb)
            if total != self.lab_last_total:
                if self.lab_last_total >= 0:
                    self._lab_score_beat()
                self.lab_last_total = total
                new_bar = (total // 4) % len(self.lab_steps)
                if new_bar != self.lab_bar:
                    self.lab_bar = new_bar
                    self.lab_beat_res = [None] * 4
                self.lab_beat  = total % 4
                self.lab_heard = False
                self._play_click(self.lab_beat == 0, force=True)
            else:
                bar = self.lab_bar % len(self.lab_steps)
                nxt = self.lab_roots[(bar + 1) % len(self.lab_roots)]
                if (_hz > MIN_HZ
                        and beat_matches(_hz, self.lab_steps[bar],
                                         self.lab_beat % 4, nxt)):
                    self.lab_heard = True

        # ── Corridos: bajeo en 3/4 + escucha por tiempo ──────────
        if self.cor_open and self.cor_running and self.cor_steps:
            self.cor_t += dt
            spb = 60.0 / max(20.0, self.cor_bpm)
            total = int(self.cor_t // spb)
            if total != self.cor_last_total:
                if self.cor_last_total >= 0:
                    self._cor_score_beat()
                self.cor_last_total = total
                new_bar = (total // 3) % len(self.cor_steps)
                if new_bar != self.cor_bar:
                    self.cor_bar = new_bar
                    self.cor_beat_res = [None] * 3
                self.cor_beat  = total % 3
                self.cor_heard = False
                self._play_click(self.cor_beat == 0, force=True)
            else:
                bar = self.cor_bar % len(self.cor_steps)
                st = self.cor_steps[bar][self.cor_beat % 3]
                if st.get("midi") is not None and _hz > MIN_HZ:
                    if bajeo_matches(_hz, st,
                                     self._cor_next_root(bar)) is True:
                        self.cor_heard = True

        # ── Oído: escucha oculta, repite con el bajo ──────────────────
        if self.ear_open and self.ear_midi is not None:
            if self.ear_revealed:
                self.ear_wait -= dt
                if self.ear_wait <= 0:
                    self._ear_pick()
            elif (_hz > MIN_HZ and self.ear_hz > 0
                    and notes_match(_hz, self.ear_hz)):
                self.ear_hold += dt
                if self.ear_hold >= self.tr_hold_need:
                    self._ear_resolve(True)
            else:
                self.ear_hold = max(0.0, self.ear_hold - dt * 2.0)

        # ── Secuencias: avanza al clavar cada paso con el micro ──────
        if self.tx_open:
            self._seq_listen("tx", _hz, dt)
        if self.ar_open:
            self._seq_listen("ar", _hz, dt)
        if self.sc_open:
            self._seq_listen("sc", _hz, dt)

        if self.counting_down:
            self.countdown_timer += dt
            beat_sec = 60.0 / self.bpm
            if self.countdown_timer >= beat_sec:
                self.countdown_timer -= beat_sec
                self.metro_flash = 1.0
                self.metro_beat  = (self.beats_per_bar - self.countdown_beat) % self.beats_per_bar
                self._play_click(self.metro_beat == 0, force=True)  # siempre suena
                self.countdown_beat -= 1
                if self.countdown_beat <= 0:
                    self.counting_down = False
                    self._begin_play()
            return

        if not self.playing:
            return

        # Avance en corcheas 16: sigue el tempo vigente del mapa × ajuste global.
        # En el silencio inicial manda el tempo derivado de las dos anclas.
        s0 = self._bass_start16()
        seg_tempo = self._lead_qpm() if self.beat_time < s0 else self._tempo_at(self.beat_time)
        delta16 = dt * (seg_tempo * self._speed_ratio() / 60.0) * 4.0
        self.beat_time += delta16

        prev_q = int((self.beat_time - delta16) / 4)
        cur_q  = int(self.beat_time / 4)
        if cur_q > prev_q:
            self.metro_beat  = cur_q % self.beats_per_bar
            self.metro_flash = 1.0
            self._play_click(self.metro_beat == 0)
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
        if cur and INPUT_AVAILABLE:
            with self.pitch_lock:
                det = self.stable_hz
            if det > 0 and cur["hz"] > 0:
                match = notes_match(det, cur["hz"])
                sec   = cur["section"]
                self.note_match   = match
                self.score_total += 1
                if match:
                    self.score_ok += 1
                    if self.last_hit_note_idx != self.note_idx:
                        self.last_hit_note_idx = self.note_idx
                        self.last_hit_delta16  = self.beat_time - cur["start16"]
                        self.last_hit_alpha    = 2.0
                if sec in self.section_stats:
                    self.section_stats[sec]["total"] += 1
                    if match:
                        self.section_stats[sec]["ok"] += 1
            else:
                self.note_match = None
        else:
            self.note_match = None

        if self.last_hit_alpha > 0:
            self.last_hit_alpha = max(0.0, self.last_hit_alpha - dt)

        self.view.target_x = max(0, self.px_of(self.beat_time))
        self.view.viewport_x += (self.view.target_x - self.view.viewport_x) * min(1.0, dt * 9)

        if self.note_idx >= len(self.notes):
            self.playing = False
            self._stop_mp3(fade_ms=200)

    # ══════════════════════════════════════════════════════════════════
    #  DRAW
    # ══════════════════════════════════════════════════════════════════
    def draw(self):
        self.screen.fill(C_BG)
        self._draw_header()
        if self.view.chords_on and (self.chord_events or self.lyric_events):
            draw_karaoke_strip(self)
        draw_waveform_strip(self)
        draw_tab(self)
        draw_score(self)
        draw_guitartab(self)
        draw_neck(self)
        draw_piano(self)
        draw_note_panel(self)
        draw_metronome(self)
        draw_pitch_panel(self)
        draw_stats_panel(self)
        draw_bottom_bar(self)
        draw_chord_editor_popup(self)
        if self.counting_down:
            draw_countdown(self)
        if self.view.device_menu_open:
            draw_device_menu(self)
        if self.view.pitch_menu_open:
            draw_pitch_menu(self)
        if self.view.song_menu_open:
            draw_song_menu(self)
        if self.view.feature_menu_open:
            draw_feature_menu(self)
        if self.view.mixer_open:
            draw_mixer(self)
        if self.view.tuner_open:
            draw_tuner(self)
        if self.training_open:
            draw_training(self)
        if self.lab_open:
            draw_lab_panel(self)
        if self.cor_open:
            draw_corrido_panel(self)
        if self.ear_open:
            draw_ear(self)
        if self.tx_open:
            draw_tech(self)
        if self.ar_open:
            draw_arp(self)
        if self.sc_open:
            draw_scale(self)
        if self.view.help_open:
            draw_help(self)
        if self.align_editor_open:
            self._draw_align_editor()
        if self.chord_edit_open:
            self._draw_chord_editor()
        self._draw_gen_overlay()
        pygame.display.flip()

    def _draw_gen_overlay(self):
        cx = W // 2
        if self.gen_running or self.gen_error:
            overlay = pygame.Surface((W, H), pygame.SRCALPHA)
            overlay.fill((8, 10, 16, 225))
            self.screen.blit(overlay, (0, 0))
        if self.gen_running:
            t = self.font_big.render(
                "Generando partitura desde el .sng…"
                if getattr(self, "gen_from_sng", False)
                else "Generando partitura desde el audio…",
                True, C_ACCENT)
            self.screen.blit(t, t.get_rect(center=(cx, H // 2 - 70)))
            sub = self.font_med.render(self.song_name, True, C_GRAY)
            self.screen.blit(sub, sub.get_rect(center=(cx, H // 2 - 30)))
            msg = self.font_med.render(self.gen_msg, True, (235, 235, 240))
            self.screen.blit(msg, msg.get_rect(center=(cx, H // 2 + 15)))
            bw, bh = 540, 14
            bx, by = cx - bw // 2, H // 2 + 55
            pygame.draw.rect(self.screen, (40, 44, 54),
                             (bx, by, bw, bh), border_radius=7)
            fw = int(bw * max(0.0, min(1.0, self.gen_frac)))
            if fw > 0:
                pygame.draw.rect(self.screen, C_ACCENT,
                                 (bx, by, fw, bh), border_radius=7)
            hint = self.font_small.render("No cierres la app…", True, C_GRAY)
            self.screen.blit(hint, hint.get_rect(center=(cx, by + bh + 24)))
        elif self.gen_error:
            t = self.font_big.render("No se pudo generar la partitura",
                                     True, C_ERR)
            self.screen.blit(t, t.get_rect(center=(cx, H // 2 - 50)))
            msg = self.font_med.render(self.gen_error[:110],
                                       True, (255, 170, 170))
            self.screen.blit(msg, msg.get_rect(center=(cx, H // 2 + 5)))
            hint = self.font_small.render(
                "Pulsa cualquier tecla para continuar", True, C_GRAY)
            self.screen.blit(hint, hint.get_rect(center=(cx, H // 2 + 45)))
        elif self._gen_msg_timer > 0:
            box = pygame.Rect(0, 0, 720, 44)
            box.center = (cx, H - 46)
            bg = pygame.Surface(box.size, pygame.SRCALPHA)
            bg.fill((24, 70, 44, 230))
            self.screen.blit(bg, box.topleft)
            pygame.draw.rect(self.screen, (70, 210, 130), box, 2,
                             border_radius=8)
            msg = self.font_med.render(self.gen_msg, True, (220, 255, 230))
            self.screen.blit(msg, msg.get_rect(center=box.center))
        elif self.gen_notice and not self.notes:
            box = pygame.Rect(0, 0, 780, 46)
            box.center = (cx, H - 48)
            bg = pygame.Surface(box.size, pygame.SRCALPHA)
            bg.fill((60, 48, 16, 230))
            self.screen.blit(bg, box.topleft)
            pygame.draw.rect(self.screen, (235, 200, 90), box, 2,
                             border_radius=8)
            song = (self.songs[self.song_idx]
                    if 0 <= self.song_idx < len(self.songs) else {})
            if song.get("sng"):
                notice = "Canción .sng sin convertir — F7 genera la partitura"
            else:
                notice = (f"Canción sin partitura — F7 generar ({self.gen_barlen}/4) · "
                          f"F8 cambiar compás")
            msg = self.font_med.render(notice, True, (255, 240, 180))
            self.screen.blit(msg, msg.get_rect(center=box.center))

    def _draw_align_editor(self):
        x0, w = self._align_x0, self._align_w
        y0, h = self._align_y0, self._align_h
        cy = y0 + h // 2
        amp = h / 2 - 8

        overlay = pygame.Surface((W, H), pygame.SRCALPHA)
        overlay.fill((10, 10, 14, 235))
        self.screen.blit(overlay, (0, 0))

        title = self.font_big.render("Editor de alineación (MP3)", True, C_ACCENT)
        self.screen.blit(title, (x0, 30))
        help_txt = (
            "SPACE=play/pausa   F=analizar tempo (librosa)   "
            "rueda=zoom   botón central=pan   "
            "clic=mueve cursor   arrastra roja=inicio bajo   "
            "arrastra verde gruesa=compás 1   verde fina=tempo   "
            "click der=añade marca   ↑/↓=BPM tramo   "
            "←/→=cursor ±1s   Supr=quitar   R=reset a la partitura   W/ESC=guardar")
        legend_txt = (
            "Leyenda:  banda verde = zona de transcripción   "
            "verde gruesa = inicio de canción (compás 1)   "
            "roja = primera nota del bajo (independiente)   "
            "verde fina = marcas de tempo (arrástralas a donde suenan)   "
            "cian Σ = donde indica la partitura (aparece al mover una marca)")
        lh = self.font_small.get_linesize()
        y = 70
        for line in _wrap_lines(help_txt, self.font_small, w):
            self.screen.blit(
                self.font_small.render(line, True, C_GRAY), (x0, y))
            y += lh
        y += 4
        for line in _wrap_lines(legend_txt, self.font_small, w):
            self.screen.blit(
                self.font_small.render(line, True, (120, 170, 140)), (x0, y))
            y += lh

        if self.align_wave is None:
            msg = self.font_med.render("Sin MP3 o waveform no disponible", True, C_ERR)
            self.screen.blit(msg, (x0, cy))
            return

        pygame.draw.rect(self.screen, (18, 20, 28), (x0 - 4, y0 - 4, w + 8, h + 8))
        pygame.draw.line(self.screen, C_DGRAY, (x0, cy), (x0 + w, cy), 1)

        col_min, col_max = self.align_wave
        n = self.align_wave_n
        total = self.align_total_sec
        v0 = self.align_view_start
        span = self.align_view_span
        for i in range(w):
            t = v0 + (i + 0.5) / w * span
            gi = min(n - 1, int(t / max(1e-9, total) * n))
            x = int(x0 + i)
            y_top = cy - int(col_max[gi] * amp)
            y_bot = cy - int(col_min[gi] * amp)
            pygame.draw.line(self.screen, (110, 130, 170), (x, y_top), (x, y_bot))

        # Onsets detectados (librosa, tecla F)
        if self.align_onsets:
            for os_sec in self.align_onsets:
                xo = self._align_px_of_sec(os_sec)
                pygame.draw.line(self.screen, (80, 90, 70),
                                 (xo, y0 + h - 6), (xo, y0 + h - 1))

        total16 = (self.notes[-1]["start16"] + self.notes[-1]["dur"]
                   if self.notes else 0)
        smap = self._ed_tmap_s16()   # mapa del editor en corcheas (para la partitura)
        t_end = self._mp3_sec_of_s16(total16, self.ed_offset, smap)
        x_start = self._align_px_of_sec(self.ed_offset)
        x_end   = self._align_px_of_sec(t_end)
        band = pygame.Surface((max(0, x_end - x_start), h), pygame.SRCALPHA)
        band.fill((50, 190, 90, 30))
        self.screen.blit(band, (x_start, y0))

        # Compases e info de la partitura (secciones) sobre el waveform
        m_starts = self._measure_starts()
        for s16 in m_starts:
            sec = self._mp3_sec_of_s16(s16, self.ed_offset, smap)
            xm = self._align_px_of_sec(sec)
            pygame.draw.line(self.screen, (70, 78, 90),
                             (xm, y0), (xm, y0 + 8), 1)
        for label, s16 in self.sections:
            sec = self._mp3_sec_of_s16(s16, self.ed_offset, smap)
            xl = self._align_px_of_sec(sec)
            pygame.draw.line(self.screen, (230, 200, 80),
                             (xl, y0), (xl, y0 + h), 1)
            lbl = self.font_tiny.render(label, True, (230, 200, 80))
            self.screen.blit(lbl, (xl + 3, y0 + h - 18))

        active = self._align_active_marker_sec()
        for e in self.ed_tempo_map:
            if len(e) >= 4 and e[3] is not None and float(e[3]) <= 0.0:
                continue   # el compás 1 lo representa la línea verde "inicio"
            mp3, qpm = e[0], e[1]
            x = self._align_mark_px(mp3)
            col = C_GREEN if mp3 == active else (40, 200, 40)
            pygame.draw.line(self.screen, col, (x, y0), (x, y0 + h), 2)
            lbl = self.font_tiny.render(f"{qpm:.0f}", True, col)
            self.screen.blit(lbl, (x + 3, y0 + 3))

        # Referencias de la partitura (cián): dónde indica el MusicXML cada
        # cambio. Solo se dibujan si no hay una marca verde encima (es decir,
        # cuando el usuario ya ha movido esa marca).
        for e in self.score_tempo_map:
            s16, qpm = e[0], e[1]
            if s16 <= 0:
                continue
            sec = self._mp3_sec_of_s16(s16, self.ed_offset, smap)
            if any(abs(m[0] - sec) <= 0.5 for m in self.ed_tempo_map):
                continue
            xr = self._align_px_of_sec(sec)
            for off in (0, 4, 8):
                pygame.draw.line(self.screen, (60, 220, 230),
                                 (xr + off, y0), (xr + off, y0 + h), 1)
            lbl = self.font_tiny.render(f"Σ {qpm:.0f}", True, (60, 220, 230))
            self.screen.blit(lbl, (xr + 3, y0 + 18))

        xc = self._align_px_of_sec(self.align_cursor_sec)
        pygame.draw.line(self.screen, C_WHITE, (xc, y0), (xc, y0 + h), 1)

        xstart = self._align_px_of_sec(self.song_start_sec)
        pygame.draw.line(self.screen, (70, 220, 120),
                         (xstart, y0), (xstart, y0 + h), 3)
        pygame.draw.polygon(self.screen, (70, 220, 120), [
            (xstart - 5, y0 + 1), (xstart + 5, y0 + 1), (xstart, y0 + 8)])
        self.screen.blit(
            self.font_tiny.render(f"inicio {self.song_start_sec:.2f}s",
                                  True, (70, 220, 120)),
            (xstart + 5, y0 + 3))

        xr = self._align_px_of_sec(self.ed_offset)
        pygame.draw.line(self.screen, C_RED, (xr, y0), (xr, y0 + h), 3)

        cur_b = self._beat16_at_mp3sec(self.align_cursor_sec, self.ed_offset,
                                       smap)
        if self.align_detecting:
            det_str = "analizando…"
        elif self.align_detected_tempo:
            det_str = f"tempo est. {self.align_detected_tempo:.0f} BPM"
        else:
            det_str = "F=analizar"
        play_str = ">> reproduciendo" if self.align_playing else "SPACE=play"
        score_init = self.score_tempo_map[0][1] if self.score_tempo_map else 0
        zoom_str = (f"zoom x{self.align_total_sec / max(1e-6, self.align_view_span):.1f}"
                    if self.align_view_span < self.align_total_sec else "vista completa")
        info = self.font_small.render(
            f"inicio canción: {self.song_start_sec:.2f}s"
            f"   inicio bajo: {self.ed_offset:+.2f}s   cursor: {self.align_cursor_sec:.2f}s"
            f"   tempo activo: {self._tempo_at(cur_b, smap):.0f} BPM"
            f"   partitura: {score_init:.0f} BPM"
            f"   {zoom_str}   {det_str}   {play_str}",
            True, C_GRAY)
        self.screen.blit(info, (x0, y0 + h + 16))

    def _draw_header(self):
        pygame.draw.rect(self.screen, C_PANEL, (0, 0, W, HEADER_H))
        pygame.draw.line(self.screen, C_ACCENT, (0, HEADER_H), (W, HEADER_H), 2)

        ratio = self._speed_ratio()
        speed_scaled = abs(ratio - 1.0) > 1e-6
        scaled = ratio if speed_scaled else 1.0
        mode_str = "BPM" if self.view.tempo_display_mode == "bpm" else "figuras"
        bpm_t = self.font_med.render(
            _fmt_tempo(self.tempo_map, scaled, self.view.tempo_display_mode),
            True, C_ACCENT)
        bpm_x = W - bpm_t.get_width() - 12

        sc = None
        sc_x = bpm_x
        if self.score_total > 0:
            pct = int(100 * self.score_ok / self.score_total)
            col = C_GREEN if pct > 70 else C_RED if pct < 40 else C_ACCENT
            sc  = self.font_med.render(f"{pct}% ok", True, col)
            sc_x = bpm_x - sc.get_width() - 18

        chips, chips_left = self._header_chips_layout()
        for action, text, rect in chips:
            hot = action == self.view.chip_hover
            bg = C_ACCENT if hot else C_DGRAY
            fg = C_BG    if hot else C_WHITE
            pygame.draw.rect(self.screen, bg, rect, border_radius=5)
            ct = self.font_tiny.render(text, True, fg)
            self.screen.blit(ct, (rect.centerx - ct.get_width() // 2,
                                  rect.centery - ct.get_height() // 2))

        title_text = f"Bass Karaoke  –  {self.song_name or 'sin canción'}"
        title = self.font_title.render(title_text, True, C_WHITE)
        budget = chips_left - 24
        while title.get_width() > budget and len(title_text) > 14:
            title_text = title_text[:-2] + "…"
            title = self.font_title.render(title_text, True, C_WHITE)
        self.screen.blit(title, (12, 8))
        self.screen.blit(bpm_t, (bpm_x, 8))
        if sc:
            self.screen.blit(sc, (sc_x, 8))

        state = (">> TOCANDO" if self.playing else
                 "|| PAUSA"   if self.score_total > 0 else "[] STOP")
        st = self.font_tiny.render(state, True,
                                   C_GREEN if self.playing else C_GRAY)
        st_x = W - st.get_width() - 12
        self.screen.blit(st, (st_x, 36))

        if speed_scaled:
            sub_str = (f"original: {_fmt_tempo(self.tempo_map, 1.0, self.view.tempo_display_mode)}"
                       f"   x{ratio:.2f}")
        else:
            sub_str = f"original del tema   x{ratio:.2f}"
        sub_t = self.font_tiny.render(
            f"{sub_str}   [{mode_str}  B=alternar]", True, C_GRAY)
        self.screen.blit(sub_t, (max(12, st_x - sub_t.get_width() - 14), 30))

        off_col    = C_GRAY if self.mp3_offset_sec == 0 else C_BLUE
        speed_str  = ""
        if self._vsp and self._vsp.loaded:
            stretch_lbl = "  (estirando…)" if self._vsp.stretching else ""
            speed_str   = f"  x{self._speed_ratio():.2f}{stretch_lbl}"
        engine_str = f"  [{getattr(self, 'pitch_engine', 'aubio')}]"
        # Estados con su tecla: se ve qué está activo y cómo cambiarlo.
        cd_str = "C:countdown ON" if self.countdown_enabled else "C:countdown OFF"
        metro_str = "N:metro ON" if self.metro_sound else "N:metro OFF"
        mute_str = " · M:MUTE" if self.muted else ""
        bass_str = " · bajo:OFF" if self.muted_bass else ""
        band_str = " · banda:OFF" if self.muted_band else ""
        off_t      = self.font_tiny.render(
            f"offset: {self.mp3_offset_sec:+.2f}s{speed_str}{engine_str}"
            f"   {cd_str} · {metro_str}{mute_str}{bass_str}{band_str}   F2:mixer",
            True, off_col)
        self.screen.blit(off_t, (12, 36))

    def _header_chips_layout(self):
        """Chips alineados a la derecha, justo antes del tempo y del score."""
        ratio = self._speed_ratio()
        scaled = ratio if abs(ratio - 1.0) > 1e-6 else 1.0
        bpm_w = self.font_med.size(
            _fmt_tempo(self.tempo_map, scaled,
                       self.view.tempo_display_mode))[0]
        right = W - bpm_w - 12 - 18
        if self.score_total > 0:
            pct = int(100 * self.score_ok / self.score_total)
            right -= self.font_med.size(f"{pct}% ok")[0] + 18
        items = []
        x = right
        for action, label, key in reversed(_HEADER_CHIPS):
            text = f"{label} {key}"
            w = self.font_tiny.size(text)[0] + _CHIP_PAD
            x -= w
            items.append((action, text, pygame.Rect(x, 5, w, _CHIP_H)))
            x -= _CHIP_GAP
        items.reverse()
        return items, x

    def _header_chip_click(self, pos):
        if not 0 <= pos[1] <= HEADER_H:
            return False
        for action, _text, rect in self._header_chips_layout()[0]:
            if rect.collidepoint(pos):
                self._header_chip_action(action)
                return True
        return False

    def _header_chip_action(self, action):
        if action != "help" and (self.training_open or self.lab_open
                                 or self.cor_open or self.ear_open
                                 or self.tx_open or self.ar_open or self.sc_open):
            self._close_modes()
        if action == "help":
            self.view.help_open = not self.view.help_open
        elif action == "songs":
            self.view.song_menu_open = not self.view.song_menu_open
            self.view.song_menu_sel = self.song_idx
        elif action == "align":
            if self.align_editor_open:
                self._close_align_editor(True)
            else:
                self._open_align_editor()
        elif action == "features":
            self.view.feature_menu_open = not self.view.feature_menu_open
            self.feature_msg.clear()
            self.feature_log.clear()

    # ══════════════════════════════════════════════════════════════════
    #  EDITOR DE ACORDES (Y) — corregir acordes por compás y guardar
    # ══════════════════════════════════════════════════════════════════
    def _chord_edit_rows(self):
        """[(nº de compás, start16)] para el editor; cae a compases del mapa."""
        rows = list(self.measure_starts or [])
        if rows:
            return rows
        bar16 = max(4, int(self.beats_per_bar or 4) * 4)
        n = max(1, (int(self.view._score_total16 or 1) + bar16 - 1) // bar16)
        return [[i + 1, i * bar16] for i in range(n)]

    def _chord_edit_sec(self, s16):
        try:
            return round(float(self._song_seconds(float(s16))), 2)
        except Exception:
            return 0.0

    def _chord_edit_name_at(self, sec, default="—"):
        name = default
        for s, n in self.chord_events:
            if float(s) <= sec + 1e-6:
                name = n
            else:
                break
        return "—" if is_rest_chord(name) else name

    def _chord_edit_index_at(self, sec, tol=0.06):
        for i, (s, _n) in enumerate(self.chord_events):
            if abs(float(s) - sec) <= tol:
                return i
        return -1

    def _chord_edit_apply(self, s16, name):
        """Fija el acorde del compás; vacío deja hueco (sin acorde)."""
        sec  = self._chord_edit_sec(s16)
        name = (name or "").strip()
        if not name:
            self._chord_bar_rest(sec)
        else:
            self._chord_bar_store(sec, name)

    def _toggle_chord_editor(self):
        self.chord_edit_open = not self.chord_edit_open
        if not self.chord_edit_open:
            self.chord_edit_typing = False
            return
        self._close_modes()
        self.view.help_open = False
        self.view.device_menu_open = self.view.pitch_menu_open = False
        self.view.song_menu_open = self.view.feature_menu_open = self.view.tuner_open = False
        self.chord_edit_typing = False
        self.chord_edit_buf    = ""
        self.chord_edit_msg    = ""
        self._chord_bar_clear()
        self.chord_bar_msg     = ""
        rows = self._chord_edit_rows()
        sel  = 0
        for i, (_num, s16) in enumerate(rows):
            if s16 <= self.beat_time:
                sel = i
            else:
                break
        self.chord_edit_sel = max(0, min(sel, len(rows) - 1))
        self.chord_edit_top = max(0, self.chord_edit_sel - 8)

    def _chords_from_score(self):
        """Deduce los acordes de las notas de la partitura y los reemplaza.

        Útil cuando el .chords.json falta o está mal: usa las notas del
        MusicXML (no el audio) con la misma lógica que la transcripción.
        Los acordes quedan sin guardar hasta Ctrl+S.
        """
        from .chords import chords_from_notes

        if not self.notes:
            msg = "Sin partitura: no hay notas para deducir acordes"
            self.chord_edit_msg = self.chord_bar_msg = msg
            return 0
        barlen = int(self.beats_per_bar or self.chord_barlen or 4)
        segs = chords_from_notes(self.notes, barlen=barlen, bars_per_chord=1)
        if not segs:
            msg = "No se pudo deducir ningún acorde de la partitura"
            self.chord_edit_msg = self.chord_bar_msg = msg
            return 0
        self.chord_events = [[float(self._song_seconds(s16)), name]
                             for s16, name in segs]
        self.chord_edit_dirty = True
        msg = (f"Partitura: {len(segs)} acordes · Ctrl+S para guardar")
        self.chord_edit_msg = self.chord_bar_msg = msg
        log.info(f"[Acordes] {msg}")
        return len(segs)

    def _save_chords(self):
        """Escribe <base>.chords.json (con .bak). Devuelve (ok, mensaje)."""
        path = self.chords_path
        if not path:
            return False, "No hay ruta .chords.json"
        try:
            if os.path.exists(path):
                with open(path, "rb") as fsrc:
                    data = fsrc.read()
                with open(path + ".bak", "wb") as fdst:
                    fdst.write(data)
            save_song_map(path, self.chord_events, self.lyric_events,
                          self.chord_barlen)
            self.chord_edit_dirty = False
            log.info(f"[Acordes] guardado {path}")
            return True, f"Guardado: {os.path.basename(path)}"
        except Exception as e:
            return False, f"Error al guardar: {e}"

    def _chord_edit_save(self):
        _ok, msg = self._save_chords()
        self.chord_edit_msg = msg

    # ══════════════════════════════════════════════════════════════════
    #  EDICIÓN POR COMPÁS EN LA BARRA DE ACORDES (clic → Enter/Supr)
    # ══════════════════════════════════════════════════════════════════
    def _chord_bar_cells(self):
        from .ui.draw_karaoke import chord_measure_cells, snapped_chord_events
        # Mismos acordes que pinta la tira (alineados a la rejilla): si no,
        # el compás que se ve con acorde se editaría como si estuviera vacío.
        return chord_measure_cells(self, snapped_chord_events(self))

    def _chord_bar_snapshot(self):
        return [(float(s), str(n)) for s, n in self.chord_events]

    def _chord_bar_index_at(self, sec, tol=0.05, snap_tol=0.30):
        """Evento guardado que la tira muestra en `sec` (inicio de compás).

        Si el evento está algo desplazado (guardado con el offset del MP3),
        se acepta el más cercano dentro de la tolerancia de alineación.
        """
        sec  = float(sec)
        best = None
        best_d = None
        for i, (s, _n) in enumerate(self.chord_events):
            d = abs(float(s) - sec)
            if d <= tol:
                return i
            if d <= snap_tol and (best_d is None or d < best_d):
                best, best_d = i, d
        return best

    def _chord_bar_prev_name(self, sec):
        """Acorde vigente justo ANTES del inicio del compás."""
        name = ""
        for s, n in self.chord_events:
            if float(s) < float(sec) - 0.05:
                name = str(n)
            else:
                break
        return name

    def _chord_bar_store(self, sec, name):
        """Pone [sec, name] en el compás, sustituyendo el evento que hubiera."""
        before = self._chord_bar_snapshot()
        idx    = self._chord_bar_index_at(sec)
        if idx is None:
            self.chord_events.append([float(sec), str(name)])
            self.chord_events.sort(key=lambda e: float(e[0]))
        else:
            self.chord_events[idx] = [float(sec), str(name)]
        if self._chord_bar_snapshot() != before:
            self.chord_edit_dirty = True
        return idx is None

    def _chord_bar_rest(self, sec):
        """Deja el compás sin acorde (hueco) en vez de heredar el anterior.

        Un acorde dura hasta el siguiente cambio, así que para que al
        borrarlo quede un hueco de verdad hay que guardar un evento vacío en
        ese compás. Si el hueco ya era propio, lo quita y vuelve a heredar.
        Devuelve "set" (dejó hueco) o "removed" (lo quitó).
        """
        idx = self._chord_bar_index_at(sec)
        if idx is not None and is_rest_chord(str(self.chord_events[idx][1])):
            before = self._chord_bar_snapshot()
            del self.chord_events[idx]
            if self._chord_bar_snapshot() != before:
                self.chord_edit_dirty = True
            return "removed"
        self._chord_bar_store(sec, "")
        return "set"

    def _chord_bar_clear(self):
        self.chord_bar_sel_measure    = None
        self.chord_bar_typing         = False
        self.chord_bar_buf            = ""
        self.chord_bar_target_sec     = None
        self.chord_bar_target_end_sec = None
        self.chord_bar_sugg_idx       = -1
        self.chord_bar_sugg_cache     = []
        self.chord_bar_replace        = False

    def _chord_bar_selected_cell(self):
        cells = self._chord_bar_cells()
        idx = self.chord_bar_sel_measure
        if idx is None or not (0 <= idx < len(cells)):
            return None
        return cells[idx]

    def _chord_bar_suggestions(self):
        """Sugerencias para lo escrito en la barra (primero los de la canción)."""
        from .chords import suggest_chords
        used = [str(n) for _s, n in self.chord_events]
        return suggest_chords(self.chord_bar_buf, used, limit=6)

    def _chord_bar_sugg_reset(self):
        """Recalcula el desplegable (al teclear, borrar o abrir la edición)."""
        self.chord_bar_sugg_cache = self._chord_bar_suggestions()
        self.chord_bar_sugg_idx   = -1

    def chord_bar_sugg_layout(self):
        """[(nombre, rect)] del desplegable de acordes sobre la barra."""
        from .ui.draw_karaoke import CURSOR_X
        cell = self._chord_bar_selected_cell()
        sugg = list(self.chord_bar_sugg_cache or ())
        if cell is None or not sugg:
            return []
        _i, _num, _raw, v0, _v1, _s0, _s1, _name, _ch = cell
        x = int(self.px_of(v0) - self.view.viewport_x + CURSOR_X)
        x = max(6, min(x, W - 190))
        y = KARAOKE_Y + KARAOKE_H
        return [(name, pygame.Rect(x, y + k * 20, 184, 20))
                for k, name in enumerate(sugg)]

    def _chord_bar_edit_selected(self):
        """Empieza a editar el acorde vigente del compás seleccionado."""
        cell = self._chord_bar_selected_cell()
        if cell is None:
            self.chord_bar_msg = "Selecciona un compás primero"
            return
        _i, _num, _raw, _v0, _v1, sec0, sec1, name, _ch = cell
        self.chord_bar_typing         = True
        self.chord_bar_buf            = name
        self.chord_bar_target_sec     = float(sec0)
        self.chord_bar_target_end_sec = float(sec1)
        self.chord_bar_msg            = ""
        self.chord_bar_replace        = True   # teclear sustituye el nombre actual
        self._chord_bar_sugg_reset()

    def _chord_bar_commit(self):
        """Aplica el nombre al compás: alinea el cambio al inicio del compás
        y limpia los eventos que caían a mitad de compás."""
        sec0 = self.chord_bar_target_sec
        sec1 = self.chord_bar_target_end_sec
        before = self._chord_bar_snapshot()
        if sec0 is not None:
            name = (self.chord_bar_buf or "").strip()
            prev = self._chord_bar_prev_name(sec0)
            if sec1 is not None and sec1 > sec0:
                self.chord_events = [
                    e for e in self.chord_events
                    if not (sec0 + 0.05 < float(e[0]) < sec1 - 0.05)]
            if not name:
                self._chord_bar_rest(sec0)
            elif name == prev:
                i = self._chord_bar_index_at(sec0)
                if i is not None:
                    del self.chord_events[i]
            else:
                self._chord_bar_store(sec0, name)
        if self._chord_bar_snapshot() != before:
            self.chord_edit_dirty = True
        self.chord_bar_typing         = False
        self.chord_bar_buf            = ""
        self.chord_bar_target_sec     = None
        self.chord_bar_target_end_sec = None
        self.chord_bar_sugg_idx       = -1
        self.chord_bar_sugg_cache     = []
        self.chord_bar_replace        = False

    def _chord_bar_cancel(self):
        self.chord_bar_typing         = False
        self.chord_bar_buf            = ""
        self.chord_bar_target_sec     = None
        self.chord_bar_target_end_sec = None
        self.chord_bar_sugg_idx       = -1
        self.chord_bar_sugg_cache     = []
        self.chord_bar_replace        = False

    def _chord_bar_delete(self):
        """Supr: deja el compás sin acorde (hueco) en vez de heredar.

        Si el compás ya tenía su propio hueco, Supr lo quita y vuelve a
        heredar el acorde anterior.
        """
        cell = self._chord_bar_selected_cell()
        if cell is None:
            self.chord_bar_msg = "Selecciona un compás primero"
            return
        _i, num, _raw, _v0, _v1, sec0, _s1, name, is_change = cell
        if not is_change and is_rest_chord(name):
            self.chord_bar_msg = f"Compás {num}: ya está sin acorde"
            return
        what = self._chord_bar_rest(sec0)
        self.chord_bar_msg = (f"Compás {num}: sin acorde (hueco)"
                              if what == "set"
                              else f"Compás {num}: vuelve a heredar")

    def _chord_bar_click(self, pos):
        """Clic en la tira: selecciona el compás bajo el cursor."""
        from .ui.draw_karaoke import chord_measure_hit_test
        hit = chord_measure_hit_test(self, pos)
        if hit is None:
            self._chord_bar_clear()
            self.chord_bar_msg = ""
            return False
        idx, _cell = hit
        self.chord_bar_typing         = False
        self.chord_bar_buf            = ""
        self.chord_bar_target_sec     = None
        self.chord_bar_target_end_sec = None
        self.chord_bar_sugg_idx       = -1
        self.chord_bar_sugg_cache     = []
        self.chord_bar_replace        = False
        self.chord_bar_sel_measure    = idx
        self.chord_bar_msg            = ""
        return True

    def _draw_chord_editor(self):
        ov = pygame.Surface((W, H), pygame.SRCALPHA)
        ov.fill((8, 10, 16, 225))
        self.screen.blit(ov, (0, 0))

        mx, my, mw, mh = 70, 60, W - 140, H - 140
        pygame.draw.rect(self.screen, C_PANEL, (mx, my, mw, mh),
                         border_radius=12)
        pygame.draw.rect(self.screen, C_ACCENT, (mx, my, mw, mh), 2,
                         border_radius=12)

        title = self.font_med.render("EDITOR DE ACORDES", True, C_ACCENT)
        self.screen.blit(title, (mx + mw // 2 - title.get_width() // 2,
                                 my + 12))
        sub = ("↑/↓ compás  ·  Enter/T editar  ·  Supr sin acorde  ·  "
               "D deducir de la partitura  ·  Ctrl+S guardar  ·  Esc cerrar")
        st = self.font_tiny.render(sub, True, C_GRAY)
        self.screen.blit(st, (mx + 16, my + 42))
        if self.chord_edit_dirty:
            d = self.font_tiny.render("● cambios sin guardar", True, C_RED)
            self.screen.blit(d, (mx + mw - d.get_width() - 16, my + 12))

        rows   = self._chord_edit_rows()
        rowh   = 22
        list_y = my + 68
        list_h = mh - 122
        nrows  = max(1, list_h // rowh)
        sel    = max(0, min(self.chord_edit_sel, len(rows) - 1))
        self.chord_edit_sel = sel
        if sel < self.chord_edit_top:
            self.chord_edit_top = sel
        tmax = max(0, len(rows) - nrows)
        if sel >= self.chord_edit_top + nrows:
            self.chord_edit_top = sel - nrows + 1
        self.chord_edit_top = max(0, min(self.chord_edit_top, tmax))

        clip = pygame.Rect(mx + 10, list_y, mw - 20, list_h)
        self.screen.set_clip(clip)
        for k in range(nrows):
            i = self.chord_edit_top + k
            if i >= len(rows):
                break
            num, s16 = rows[i]
            sec   = self._chord_edit_sec(s16)
            name  = self._chord_edit_name_at(sec)
            start = self._chord_edit_index_at(sec) >= 0
            y     = list_y + k * rowh
            if i == sel:
                pygame.draw.rect(self.screen, (40, 44, 70),
                                 (clip.x, y, clip.w, rowh - 2),
                                 border_radius=4)
            if i == sel and self.chord_edit_typing:
                label = f"C{num:>3}  {sec:7.2f}s   [ {self.chord_edit_buf} ]"
            else:
                label = f"C{num:>3}  {sec:7.2f}s   {name}"
                if start:
                    label += "   •"
            col = C_ACCENT if i == sel else C_WHITE
            self.screen.blit(self.font_small.render(label, True, col),
                             (mx + 22, y + 3))
        self.screen.set_clip(None)

        if self.chord_edit_msg:
            m = self.font_small.render(self.chord_edit_msg, True, C_GREEN)
            self.screen.blit(m, (mx + 16, my + mh - 30))

    # ══════════════════════════════════════════════════════════════════
    #  EVENT HANDLING
    # ══════════════════════════════════════════════════════════════════
    def handle_event(self, event):
        """Reparte el evento por tipo y delega en el mixin correspondiente.

        Devuelve ``False`` solo cuando toca salir (QUIT, o Escape en la vista
        principal). El teclado y el ratón viven en `bass_karaoke/events/`;
        ningún gesto de ratón cierra la app.
        """
        if event.type == pygame.QUIT:
            return False
        if event.type == pygame.KEYDOWN:
            return self._on_keydown(event)
        if event.type == pygame.MOUSEBUTTONDOWN:
            self._on_mouse_down(event)
        elif event.type == pygame.MOUSEBUTTONUP:
            self._on_mouse_up(event)
        elif event.type == pygame.MOUSEWHEEL:
            self._on_wheel(event)
        elif event.type == pygame.MOUSEMOTION:
            self._on_mouse_motion(event)
        return True

    # ══════════════════════════════════════════════════════════════════
    #  MAIN LOOP
    # ══════════════════════════════════════════════════════════════════
    def run(self):
        running = True
        while running:
            dt = self.clock.tick(FPS) / 1000.0
            for event in pygame.event.get():
                if not self.handle_event(event):
                    running = False
                    break
            self.update(dt)
            self.draw()
        self._stop_mp3()
        self._stop_audio()
        pygame.quit()
