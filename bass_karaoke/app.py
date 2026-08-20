"""
BassKaraoke — clase principal orquestadora.
Importa toda la lógica desde los submódulos del paquete.
"""
import os
import json
import math
import time
import threading

import pygame

from .config import (
    W, H, HEADER_H, TAB_Y, TAB_H, SCORE_H, NECK_Y, NECK_H, NECK_W,
    PIANO_X, PIANO_Y, PIANO_W, PIANO_H, LOWER_Y, LOWER_H, BOTTOM_Y,
    PIANO_START_MIDI, PIANO_END_MIDI,
    NECK_FRETS, NECK_DOT_FRETS, NECK_OCT_FRETS,
    NECK_AREA_X, NECK_AREA_W, NECK_NUT_X, NECK_LABEL_W,
    STRING_NAMES, STRING_COLORS, STRING_THICK,
    BPM_DEFAULT, BPM_ORIGINAL, PITCH_METHODS, SONGS_DIR,
    MUSICXML_PATH, TG_PATH, CONFIG_PATH,
    C_BG, C_BG2, C_PANEL, C_DGRAY, C_ACCENT, C_GREEN, C_RED,
    C_BLUE, C_WHITE, C_GRAY, C_OK, C_ERR, C_WAIT,
    MIN_HZ, MAX_HZ,
)
from .utils import fret_to_hz, hz_to_note_name, notes_match
from .parser import parse_musicxml, parse_grace_notes
from . import features
features.ensure_on_path()
from .audio import (
    VarispeedPlayer, VARSPEED_OK, PitchEngine, PITCH_AVAILABLE,
    enumerate_devices, INPUT_AVAILABLE, load_mp3_samples,
)
from .score import (
    init_score_surface, VEROVIO_OK, CAIROSVG_OK,
    init_score_surface_music21, MUSIC21_OK,
)
from .ui import (
    draw_tab, draw_score, draw_guitartab, draw_neck, draw_piano,
    draw_note_panel, draw_metronome, draw_pitch_panel,
    draw_stats_panel, draw_bottom_bar,
    draw_tuner, draw_countdown, draw_device_menu, draw_pitch_menu,
    draw_song_menu, draw_feature_menu,
)

FPS = 60

# Nombre en español de cada figura del metrónomo (MusicXML beat-unit)
FIGURE_NAMES = {
    "whole": "redonda", "half": "blanca", "quarter": "negra",
    "eighth": "corchea", "16th": "semicorchea", "32nd": "fusa",
    "64th": "semifusa",
}


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


class BassKaraoke:

    def __init__(self):
        pygame.init()
        pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
        self.screen = pygame.display.set_mode((W, H))
        pygame.display.set_caption("Bass Karaoke v3  –  Feet Don't Fail Me Now")
        self.clock = pygame.time.Clock()

        self.font_title = pygame.font.SysFont("consolas", 20, bold=True)
        self.font_huge  = pygame.font.SysFont("consolas", 74, bold=True)
        self.font_big   = pygame.font.SysFont("consolas", 30, bold=True)
        self.font_med   = pygame.font.SysFont("consolas", 19, bold=True)
        self.font_small = pygame.font.SysFont("consolas", 15)
        self.font_tiny  = pygame.font.SysFont("consolas", 12)

        # ── Estado ─────────────────────────────────────────────────────
        self.bpm            = BPM_DEFAULT
        self.tempo_display_mode = "figura"   # "figura" | "bpm"
        self.playing        = False
        self.muted          = False
        self.note_idx       = 0
        self.beat_time      = 0.0
        self.score_ok       = 0
        self.score_total    = 0
        self.mp3_offset_sec = 0.0
        self._t             = 0.0   # tiempo acumulado para animaciones

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
        self.pitch_engine  = "aubio"  # etiqueta para HUD

        # Indicador de timing
        self.last_hit_delta16  = 0.0
        self.last_hit_note_idx = -1
        self.last_hit_alpha    = 0.0

        # ── Dispositivos ───────────────────────────────────────────────
        self.audio_devices    = enumerate_devices()
        self.device_idx       = 0
        self.device_menu_open = False
        self.device_menu_sel  = 0

        # ── Stats ──────────────────────────────────────────────────────
        self.section_stats = {}

        # ── Tuner ──────────────────────────────────────────────────────
        self.tuner_open = False

        # ── Selector de método de pitch ────────────────────────────────
        self.pitch_method    = "mpm"
        self.pitch_menu_open = False
        self.pitch_menu_sel  = PITCH_METHODS.index("crepe-tiny")

        # ── Gestor de funcionalidades opcionales (I) ───────────────────
        self.feature_menu_open = False
        self.feature_menu_sel  = 0
        self.feature_busy      = set()
        self.feature_msg       = {}
        self.feature_log       = []

        # ── Metrónomo ──────────────────────────────────────────────────
        self.metro_beat    = 0
        self.metro_flash   = 0.0
        self.metro_sound   = False  # desactivado por defecto; N para activar
        self._click_hi, self._click_lo = self._build_clicks()

        # ── Mástil: mapa de notas de la canción ───────────────────────
        self.neck_map = False  # H para mostrar/ocultar

        # ── Arrastre con ratón (seek) ─────────────────────────────────
        self._drag_seeking    = False
        self._drag_start_beat = 0.0
        self._drag_start_mx   = 0

        # ── Guitar Hero: nota detectada por el micrófono ──────────────
        self.detected_fret_str = None   # (fret, string) o None

        # ── Editor de alineación MP3 (W) ──────────────────────────────
        self.align_editor_open = False
        self.align_wave        = None   # (col_min, col_max) normalizados a ±1
        self.align_wave_n      = 0
        self.align_total_sec   = 0.0
        self.align_view_start  = 0.0    # ventana visible (zoom/pan), en segundos
        self.align_view_span   = 0.0
        self.align_cursor_sec  = 0.0
        self.align_dragging    = False   # arrastrando el offset (inicio bajo)
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
        self.px_per_16th = 30
        self.viewport_x  = 0.0
        self.target_x    = 0.0

        # ── MusicXML ───────────────────────────────────────────────────
        self.notes       = []
        self.sections    = []
        self.grace_notes = []

        # ── Canciones ──────────────────────────────────────────────────
        self.song_menu_open = False
        self.song_menu_sel  = 0
        self.song_idx       = 0
        self.song_name      = ""
        self.musicxml_path  = MUSICXML_PATH
        self.tg_path        = TG_PATH
        self.bpm_original   = BPM_ORIGINAL
        self.tempo_map      = [(0, BPM_ORIGINAL)]
        self.score_tempo_map = [(0, BPM_ORIGINAL)]   # marcas de tempo del MusicXML
        self._bpm_map       = {}
        self._offset_map    = {}
        self._tempo_maps    = {}
        self.songs          = self._scan_songs()
        self._piano_keys_list = []

        # ── Score pre-render ───────────────────────────────────────────
        self.score_renderer  = "verovio"
        self._score_loading  = False
        self._score_surf     = None
        self._score_note_xs  = []
        self._score_scroll_x = 0.0
        self._score_cache    = {}   # {renderer: (surf, note_xs)} para no re-renderizar
        self._score_total16  = 1

        # ── Audio MP3 ──────────────────────────────────────────────────
        self._vsp       = VarispeedPlayer() if VARSPEED_OK else None
        self.mp3_path   = None
        self._pgm_loaded = False

        self._load_config()

        if self.songs:
            self.song_idx = min(self.song_idx, len(self.songs) - 1)
            self._load_song(self.song_idx, caption=True, init_score=False)
        else:
            print("[WARN] No hay canciones en songs/ — usando rutas por defecto")
            self._load_notes()
            self._load_mp3(self._find_mp3())
            pygame.display.set_caption(f"Bass Karaoke v3  –  {self.song_name or 'sin canción'}")

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
            "tempo_maps":        self._tempo_maps,
            "device_idx":        self.device_idx,
            "muted":             self.muted,
            "pitch_method":      self.pitch_method,
            "countdown_enabled": self.countdown_enabled,
            "score_renderer":    self.score_renderer,
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
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            self.bpm            = float(cfg.get("bpm",            self.bpm))
            self.mp3_offset_sec = float(cfg.get("mp3_offset_sec", self.mp3_offset_sec))
            self.muted          = bool( cfg.get("muted",          self.muted))
            saved_dev           = int(  cfg.get("device_idx",     self.device_idx))
            if 0 <= saved_dev < len(self.audio_devices):
                self.device_idx = saved_dev
            saved_method = cfg.get("pitch_method", self.pitch_method)
            if saved_method in PITCH_METHODS:
                self.pitch_method   = saved_method
                self.pitch_menu_sel = PITCH_METHODS.index(saved_method)
            self.countdown_enabled = bool(cfg.get("countdown_enabled", self.countdown_enabled))
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
            self._tempo_maps = cfg.get("tempo_maps", {}) or {}
            print(f"[Config] cargada  BPM={self.bpm}  offset={self.mp3_offset_sec:+.2f}s  "
                  f"pitch={self.pitch_method}  renderer={self.score_renderer}  "
                  f"song={saved_song}")
        except Exception as e:
            print(f"[Config WARN] {e}")

    # ══════════════════════════════════════════════════════════════════
    #  CANCIONES / NOTAS / MP3
    # ══════════════════════════════════════════════════════════════════
    def _scan_songs(self):
        """Escanea songs/ y devuelve lista de canciones con musicxml."""
        songs = []
        if not os.path.isdir(SONGS_DIR):
            return songs
        for entry in sorted(os.listdir(SONGS_DIR)):
            folder = os.path.join(SONGS_DIR, entry)
            if not os.path.isdir(folder) or entry.startswith("."):
                continue
            musicxml = self._find_file(folder, ".musicxml")
            if not musicxml:
                continue
            name = entry.replace("_", " ").replace("-", " ").title()
            songs.append({
                "name":     name,
                "dir":      folder,
                "musicxml": musicxml,
                "tg":       self._find_file(folder, ".tg"),
                "mp3":      self._find_file(folder, ".mp3"),
            })
            print(f"[Canción] {name:24s}  {os.path.basename(musicxml)}  "
                  f"mp3={'SÍ' if songs[-1]['mp3'] else 'no'}")
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
        self.musicxml_path = song["musicxml"]
        self.tg_path       = song["tg"] or TG_PATH
        self._load_notes()
        self._load_mp3(song["mp3"])
        self.reiniciar()
        # Re-generar partitura y estado dependiente de la canción
        self._score_cache    = {}
        self._score_surf     = None
        self._score_note_xs  = []
        self._score_scroll_x = 0.0
        self._score_total16  = (
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
        saved_offset = (self._offset_map or {}).get(self.song_name)
        if saved_offset is not None:
            self.mp3_offset_sec = float(saved_offset)
        if caption:
            pygame.display.set_caption(f"Bass Karaoke v3  –  {self.song_name}")
        if init_score:
            self._init_score()
        print(f"[OK] Canción cargada: {self.song_name}")

    def _load_notes(self):
        if not os.path.exists(self.musicxml_path):
            print(f"[ERROR] MusicXML no encontrado: {self.musicxml_path}")
            return
        try:
            notes, sections, bpm, tempo_map = parse_musicxml(self.musicxml_path)
            self.notes         = notes
            self.sections      = sections
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
            print(f"[OK] MusicXML: {len(notes)} notas, {bpm} BPM  "
                  f"graces={len(self.grace_notes)}")
        except Exception as e:
            print(f"[ERROR] MusicXML: {e}")
            import traceback; traceback.print_exc()

    def _load_mp3(self, path=None):
        self._stop_mp3()
        self.mp3_path    = path
        self._vsp        = VarispeedPlayer() if VARSPEED_OK else None
        self._pgm_loaded = False
        if not self.mp3_path:
            print("[Audio] Sin MP3 para esta canción — solo metrónomo/tablatura")
            return
        if self._vsp:
            if not self._vsp.load(self.mp3_path):
                self._vsp = None
        if not (self._vsp and self._vsp.loaded):
            try:
                pygame.mixer.music.load(self.mp3_path)
                self._pgm_loaded = True
                print(f"[pygame.mixer] {self.mp3_path}")
            except Exception as e:
                print(f"[WARN] pygame.mixer: {e}")

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
            return self.songs[self.song_idx]["mp3"]
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
        if "verovio" in self._score_cache:
            self._score_surf, self._score_note_xs = self._score_cache["verovio"]
            print("[Verovio] usando caché")
            return
        surf, note_xs = init_score_surface(self.notes, self.musicxml_path)
        self._score_surf    = surf
        self._score_note_xs = note_xs
        if surf is not None:
            self._score_cache["verovio"] = (surf, note_xs)

    def _init_score_music21(self):
        if "music21" in self._score_cache:
            self._score_surf, self._score_note_xs = self._score_cache["music21"]
            print("[Music21] usando caché")
            return
        surf, note_xs = init_score_surface_music21(self.notes, self.musicxml_path)
        self._score_surf    = surf
        self._score_note_xs = note_xs
        if surf is not None:
            self._score_cache["music21"] = (surf, note_xs)

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

        def on_engine_label(label):
            self.pitch_engine = label

        def on_debug(hz, conf, method):
            if self.tuner_open and hz > 0:
                print(f"[tuner-debug] {hz:.1f} Hz  conf={conf:.2f}  ({method})")

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
        return int(beat16 * self.px_per_16th)

    def current_note(self):
        return self.notes[self.note_idx] if self.note_idx < len(self.notes) else None

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
        La línea roja (offset) = PRIMERA nota del bajo."""
        offset = self.mp3_offset_sec if offset is None else offset
        tmap   = tmap if tmap is not None else self.tempo_map
        return (offset + self._song_seconds(s16, tmap)
                - self._song_seconds(self._bass_start16(), tmap))

    def _beat16_at_mp3sec(self, mp3_sec, offset=None, tmap=None):
        """Inverso de _mp3_sec_of_s16: instante del MP3 -> start16.
        Anclado a la primera nota del bajo (línea roja = offset)."""
        offset  = self.ed_offset if offset is None else offset
        tmap    = tmap if tmap is not None else self.tempo_map
        S       = self._bass_start16()
        abs_sec = self._song_seconds(S, tmap) + (mp3_sec - offset)
        return self._song_seconds_inverse(abs_sec, tmap)

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
        if self.song_name:
            self._offset_map[self.song_name] = self.mp3_offset_sec
            self._tempo_maps[self.song_name] = [
                [int(e[0]), round(e[1], 2), (e[2] if len(e) >= 3 else "quarter")]
                for e in self.tempo_map
            ]
        self._save_config()
        print(f"[Alineación] offset={self.mp3_offset_sec:+.2f}s  "
              f"tempo_map={self.tempo_map}")

    def _align_build_waveform(self):
        """Rejilla fina min/max de TODO el MP3, calculada una sola vez.
        El zoom/pan solo recorta qué columnas se dibujan."""
        import numpy as _np
        vsp = self._vsp
        self.align_wave = None
        self.align_wave_n = 0
        self.align_total_sec = 0.0
        arr = None
        sr = 0
        if vsp and vsp.loaded and vsp.data_orig is not None:
            arr = vsp.data_orig[:, 0]
            sr = vsp.sr
        elif self.mp3_path:
            arr, sr = load_mp3_samples(self.mp3_path)
        if arr is None or sr <= 0:
            return
        self.align_total_sec = len(arr) / float(sr)
        n = len(arr)
        n_grid = min(20000, max(1, n // 4))
        if n <= n_grid:
            col_min = arr
            col_max = arr
            self.align_wave_n = n
        else:
            step = n // n_grid
            g = arr[: n_grid * step].reshape(n_grid, step)
            col_min = g.min(axis=1)
            col_max = g.max(axis=1)
            self.align_wave_n = n_grid
        peak = max(float(_np.abs(col_max).max()),
                   float(_np.abs(col_min).max()), 1e-9)
        self.align_wave = (col_min / peak, col_max / peak)

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
        if merged[0][0] != 0.0:
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
        new_off = round(self._align_sec_of_pos(pos), 2)
        if self.ed_offset != new_off:
            # Las marcas que aún siguen "lo que dice la partitura" se mueven
            # con la línea roja; las fijadas a mano se quedan donde están.
            for e in self.ed_tempo_map:
                if len(e) >= 4 and e[3] is not None:
                    e[0] = round(self._mp3_sec_of_s16(e[3], new_off,
                                                      self.score_tempo_map), 2)
            self.ed_offset = new_off
        self.align_cursor_sec = self.ed_offset

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
            print(f"[Editor] no puedo reproducir: {e}")

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
            print(f"[Editor] tempo estimado {tempo:.1f} BPM  "
                  f"onsets={len(self.align_onsets)}  ({time.time()-t0:.1f}s)")
        except Exception as e:
            print(f"[Editor] detección falló: {e}")
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
    #  CONTROLES
    # ══════════════════════════════════════════════════════════════════
    def _measure_starts(self):
        """Devuelve lista ordenada de posiciones start16 del inicio de cada compás."""
        seen = {}
        for note in self.notes:
            m = note["measure_num"]
            if m not in seen:
                seen[m] = note["start16"]
        return sorted(seen.values())

    def _snap_measure(self, direction: int):
        """
        Salta al inicio del compás anterior (direction=-1) o siguiente (+1).
        Si ya estamos al inicio del compás actual, retrocede al compás anterior.
        """
        starts = self._measure_starts()
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
        self.viewport_x = max(0.0, float(self.px_of(beat16)))
        self.target_x   = self.viewport_x

        # Hacer que la partitura salte sin animación
        self._score_scroll_x = self.viewport_x * (
            (self._score_surf.get_width() if self._score_surf else 1)
            / max(1, self._score_total16 * self.px_per_16th)
        )

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
                self.countdown_beat = 4
                self.countdown_timer = 0.0
            else:
                self._begin_play()

    def _begin_play(self):
        self.playing = True
        if not self.muted:
            offset = self._mp3_sec_of_s16(self.beat_time)
            self._play_mp3(offset)

    def _play_mp3(self, offset_sec=0.0):
        if self._vsp and self._vsp.loaded:
            self._vsp.set_speed(self._speed_ratio())
            self._vsp.play(offset_sec)
        elif self._pgm_loaded:
            start_ms = max(0, int(offset_sec * 1000))
            pygame.mixer.music.play(start=start_ms / 1000.0)

    def _pause_mp3(self):
        if self._vsp and self._vsp.loaded:
            self._vsp.pause()
        elif self._pgm_loaded:
            pygame.mixer.music.pause()

    def _resume_mp3(self):
        if self._vsp and self._vsp.loaded:
            self._vsp.resume()
        elif self._pgm_loaded:
            pygame.mixer.music.unpause()

    def _stop_mp3(self):
        if self._vsp and self._vsp.loaded:
            self._vsp.stop()
        elif self._pgm_loaded:
            pygame.mixer.music.stop()

    def reiniciar(self):
        self.playing       = False
        self.counting_down = False
        self.note_idx      = 0
        self.beat_time     = 0.0
        self.viewport_x    = 0.0
        self.target_x      = 0.0
        self.score_ok      = 0
        self.score_total   = 0
        self.note_match    = None
        self._score_scroll_x = 0.0
        self._stop_mp3()
        for d in self.section_stats.values():
            d["ok"] = 0; d["total"] = 0

    def ajustar_offset(self, delta):
        self.mp3_offset_sec += delta
        if self.playing:
            offset = self._mp3_sec_of_s16(self.beat_time)
            self._stop_mp3()
            self._play_mp3(offset)

    def ajustar_bpm(self, delta):
        self.bpm = max(40, min(300, self.bpm + delta))
        if self._vsp and self._vsp.loaded:
            self._vsp.set_speed(self._speed_ratio())

    def toggle_mute(self):
        self.muted = not self.muted
        if self.playing:
            if self.muted:
                self._stop_mp3()
            else:
                offset = self._mp3_sec_of_s16(self.beat_time)
                self._play_mp3(offset)

    def cycle_score_renderer(self):
        if self.score_renderer == "verovio" and MUSIC21_OK:
            self.score_renderer  = "music21"
            self._score_surf     = None
            self._score_note_xs  = []
            self._score_scroll_x = 0.0
            self._init_score_music21()
        elif VEROVIO_OK and CAIROSVG_OK:
            self.score_renderer  = "verovio"
            self._score_surf     = None
            self._score_note_xs  = []
            self._score_scroll_x = 0.0
            self._init_score_verovio()

    # ══════════════════════════════════════════════════════════════════
    #  UPDATE
    # ══════════════════════════════════════════════════════════════════
    def update(self, dt):
        self._t += dt
        if self._config_msg_timer > 0:
            self._config_msg_timer = max(0.0, self._config_msg_timer - dt)

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

        if self.counting_down:
            self.countdown_timer += dt
            beat_sec = 60.0 / self.bpm
            if self.countdown_timer >= beat_sec:
                self.countdown_timer -= beat_sec
                self.metro_flash = 1.0
                self.metro_beat  = (4 - self.countdown_beat) % 4
                self._play_click(self.metro_beat == 0, force=True)  # siempre suena
                self.countdown_beat -= 1
                if self.countdown_beat <= 0:
                    self.counting_down = False
                    self._begin_play()
            return

        if not self.playing:
            return

        # Avance en corcheas 16: sigue el tempo vigente del mapa × ajuste global
        seg_tempo = self._tempo_at(self.beat_time)
        delta16 = dt * (seg_tempo * self._speed_ratio() / 60.0) * 4.0
        self.beat_time += delta16

        prev_q = int((self.beat_time - delta16) / 4)
        cur_q  = int(self.beat_time / 4)
        if cur_q > prev_q:
            self.metro_beat  = cur_q % 4
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

        self.target_x = max(0, self.px_of(self.beat_time))
        self.viewport_x += (self.target_x - self.viewport_x) * min(1.0, dt * 9)

        if self.note_idx >= len(self.notes):
            self.playing = False

    # ══════════════════════════════════════════════════════════════════
    #  DRAW
    # ══════════════════════════════════════════════════════════════════
    def draw(self):
        self.screen.fill(C_BG)
        self._draw_header()
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
        if self.counting_down:
            draw_countdown(self)
        if self.device_menu_open:
            draw_device_menu(self)
        if self.pitch_menu_open:
            draw_pitch_menu(self)
        if self.song_menu_open:
            draw_song_menu(self)
        if self.feature_menu_open:
            draw_feature_menu(self)
        if self.tuner_open:
            draw_tuner(self)
        if self.align_editor_open:
            self._draw_align_editor()
        pygame.display.flip()

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
        help_t = self.font_small.render(
            "SPACE=play/pausa   F=analizar tempo (librosa)   "
            "rueda=zoom   botón central=pan   "
            "clic=mueve cursor   arrastra roja=inicio bajo   "
            "arrastra verde=tempo (no mueve el inicio)   "
            "click der=añade marca   ↑/↓=BPM tramo   "
            "←/→=cursor ±1s   Supr=quitar   R=reset a la partitura   W/ESC=guardar",
            True, C_GRAY)
        self.screen.blit(help_t, (x0, 70))
        legend_t = self.font_small.render(
            "Leyenda:  banda verde = zona de transcripción   "
            "roja = primera nota del bajo (se mueve con las marcas de partitura)   "
            "verde = marcas de tempo (arrástralas a donde suenan)   "
            "cian Σ = donde indica la partitura (aparece al mover una marca)",
            True, (120, 170, 140))
        self.screen.blit(legend_t, (x0, 90))

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
            f"inicio bajo: {self.ed_offset:+.2f}s   cursor: {self.align_cursor_sec:.2f}s"
            f"   tempo activo: {self._tempo_at(cur_b, smap):.0f} BPM"
            f"   partitura: {score_init:.0f} BPM"
            f"   {zoom_str}   {det_str}   {play_str}",
            True, C_GRAY)
        self.screen.blit(info, (x0, y0 + h + 16))

    def _draw_header(self):
        pygame.draw.rect(self.screen, C_PANEL, (0, 0, W, HEADER_H))
        pygame.draw.line(self.screen, C_ACCENT, (0, HEADER_H), (W, HEADER_H), 2)

        title = self.font_title.render(
            f"Bass Karaoke  –  {self.song_name or 'sin canción'}",
            True, C_WHITE)
        self.screen.blit(title, (12, 8))

        ratio = self._speed_ratio()
        scaled = ratio if abs(ratio - 1.0) > 1e-6 else 1.0
        mode_str = "BPM" if self.tempo_display_mode == "bpm" else "figuras"
        bpm_t = self.font_med.render(
            _fmt_tempo(self.tempo_map, scaled, self.tempo_display_mode),
            True, C_ACCENT)
        self.screen.blit(bpm_t, (W - bpm_t.get_width() - 12, 8))
        if scaled != 1.0:
            sub_str = (f"original: {_fmt_tempo(self.tempo_map, 1.0, self.tempo_display_mode)}"
                       f"   x{ratio:.2f}")
        else:
            sub_str = f"original del tema   x{ratio:.2f}"
        sub_t = self.font_tiny.render(
            f"{sub_str}   [{mode_str}  B=alternar]", True, C_GRAY)
        self.screen.blit(sub_t, (W - sub_t.get_width() - 12, 30))

        if self.score_total > 0:
            pct = int(100 * self.score_ok / self.score_total)
            col = C_GREEN if pct > 70 else C_RED if pct < 40 else C_ACCENT
            sc  = self.font_med.render(f"{pct}% ok", True, col)
            self.screen.blit(sc, (W - 320, 8))

        off_col    = C_GRAY if self.mp3_offset_sec == 0 else C_BLUE
        speed_str  = ""
        if self._vsp and self._vsp.loaded:
            stretch_lbl = "  (estirando…)" if self._vsp.stretching else ""
            speed_str   = f"  x{self._speed_ratio():.2f}{stretch_lbl}"
        engine_str = f"  [{getattr(self, 'pitch_engine', 'aubio')}]"
        off_t      = self.font_tiny.render(
            f"offset: {self.mp3_offset_sec:+.2f}s{speed_str}{engine_str}"
            f"   [ ,/. fino  Shift+,/. grueso   P=pitch   "
            f"C=countdown({'ON' if self.countdown_enabled else 'OFF'}) ]",
            True, off_col)
        self.screen.blit(off_t, (12, 36))

        state = (">> TOCANDO" if self.playing else
                 "|| PAUSA"   if self.score_total > 0 else "[] STOP")
        st = self.font_tiny.render(state, True,
                                   C_GREEN if self.playing else C_GRAY)
        self.screen.blit(st, (W - 155, 36))

    # ══════════════════════════════════════════════════════════════════
    #  EVENT HANDLING
    # ══════════════════════════════════════════════════════════════════
    def handle_event(self, event):
        if event.type == pygame.QUIT:
            return False

        if event.type == pygame.KEYDOWN:
            # ── Menú funcionalidades opcionales ────────────────────────
            if self.feature_menu_open:
                feats = features.FEATURES
                if event.key == pygame.K_UP:
                    self.feature_menu_sel = max(0, self.feature_menu_sel - 1)
                elif event.key == pygame.K_DOWN:
                    self.feature_menu_sel = min(len(feats) - 1,
                                                self.feature_menu_sel + 1)
                elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    self._feature_toggle(feats[self.feature_menu_sel]["id"])
                elif event.key in (pygame.K_ESCAPE, pygame.K_i):
                    self.feature_menu_open = False
                return True

            # ── Menú dispositivos ──────────────────────────────────────
            if self.device_menu_open:
                if event.key == pygame.K_UP:
                    self.device_menu_sel = max(0, self.device_menu_sel - 1)
                elif event.key == pygame.K_DOWN:
                    self.device_menu_sel = min(len(self.audio_devices) - 1,
                                               self.device_menu_sel + 1)
                elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    self._start_audio(self.device_menu_sel)
                    self.device_menu_open = False
                elif event.key in (pygame.K_ESCAPE, pygame.K_d):
                    self.device_menu_open = False
                return True

            # ── Menú método de pitch ───────────────────────────────────
            if self.pitch_menu_open:
                if event.key == pygame.K_UP:
                    self.pitch_menu_sel = max(0, self.pitch_menu_sel - 1)
                elif event.key == pygame.K_DOWN:
                    self.pitch_menu_sel = min(len(PITCH_METHODS) - 1,
                                              self.pitch_menu_sel + 1)
                elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    self.pitch_method  = PITCH_METHODS[self.pitch_menu_sel]
                    self.pitch_menu_open = False
                    self._start_audio()
                elif event.key in (pygame.K_ESCAPE, pygame.K_p):
                    self.pitch_menu_open = False
                return True

            # ── Menú canciones ─────────────────────────────────────────
            if self.song_menu_open:
                if event.key == pygame.K_UP:
                    self.song_menu_sel = max(0, self.song_menu_sel - 1)
                elif event.key == pygame.K_DOWN:
                    self.song_menu_sel = min(len(self.songs) - 1,
                                             self.song_menu_sel + 1)
                elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    self._load_song(self.song_menu_sel, caption=True)
                    self.song_menu_open = False
                elif event.key in (pygame.K_ESCAPE, pygame.K_l):
                    self.song_menu_open = False
                return True

            # ── Tuner ──────────────────────────────────────────────────
            if self.tuner_open:
                if event.key in (pygame.K_ESCAPE, pygame.K_t):
                    self.tuner_open = False
                return True

            # ── Editor de alineación (W) ───────────────────────────────
            if self.align_editor_open:
                mods_e = pygame.key.get_mods()
                ctrl_e = mods_e & pygame.KMOD_CTRL
                if event.key in (pygame.K_w, pygame.K_ESCAPE):
                    self._close_align_editor(True)
                elif event.key == pygame.K_SPACE:
                    self._align_toggle_play()
                elif event.key == pygame.K_f:
                    self._align_detect()
                elif event.key == pygame.K_UP:
                    self._align_adjust_bpm(+1)
                elif event.key == pygame.K_DOWN:
                    self._align_adjust_bpm(-1)
                elif event.key == pygame.K_LEFT:
                    self.align_cursor_sec = max(
                        0.0, self.align_cursor_sec - (5.0 if ctrl_e else 1.0))
                    self._align_keep_cursor_visible()
                elif event.key == pygame.K_RIGHT:
                    self.align_cursor_sec = min(
                        self.align_total_sec,
                        self.align_cursor_sec + (5.0 if ctrl_e else 1.0))
                    self._align_keep_cursor_visible()
                elif event.key in (pygame.K_DELETE, pygame.K_BACKSPACE):
                    self._align_delete_marker()
                elif event.key == pygame.K_r:
                    self._align_reset_marks()
                return True

            # ── Controles principales ──────────────────────────────────
            mods = pygame.key.get_mods()
            shift = mods & pygame.KMOD_SHIFT
            ctrl  = mods & pygame.KMOD_CTRL

            if event.key == pygame.K_SPACE:
                self.toggle_play()
            elif event.key == pygame.K_r:
                self.reiniciar()
            elif event.key == pygame.K_UP:
                self.ajustar_bpm(+5)
            elif event.key == pygame.K_DOWN:
                self.ajustar_bpm(-5)
            elif event.key == pygame.K_COMMA:
                self.ajustar_offset(-5.0 if ctrl else (-0.5 if shift else -0.05))
            elif event.key == pygame.K_PERIOD:
                self.ajustar_offset(+5.0 if ctrl else (+0.5 if shift else +0.05))
            elif event.key == pygame.K_LEFT:
                self._snap_measure(-1)
            elif event.key == pygame.K_RIGHT:
                self._snap_measure(+1)
            elif event.key == pygame.K_m:
                self.toggle_mute()
            elif event.key == pygame.K_b:
                self.tempo_display_mode = (
                    "bpm" if self.tempo_display_mode == "figura" else "figura")
            elif event.key == pygame.K_d:
                if INPUT_AVAILABLE and self.audio_devices:
                    self.device_menu_open = not self.device_menu_open
                    self.device_menu_sel  = self.device_idx
            elif event.key == pygame.K_p:
                self.pitch_menu_open = not self.pitch_menu_open
            elif event.key == pygame.K_i:
                self.feature_menu_open = not self.feature_menu_open
                self.feature_msg.clear()
                self.feature_log.clear()
            elif event.key == pygame.K_l:
                self.song_menu_open = not self.song_menu_open
                self.song_menu_sel  = self.song_idx
            elif event.key == pygame.K_t:
                self.tuner_open = not self.tuner_open
            elif event.key == pygame.K_w:
                if self.align_editor_open:
                    self._close_align_editor(True)
                else:
                    self._open_align_editor()
            elif event.key == pygame.K_s:
                self.cycle_score_renderer()
            elif event.key == pygame.K_c:
                self.countdown_enabled = not self.countdown_enabled
            elif event.key == pygame.K_n:
                self.metro_sound = not self.metro_sound
            elif event.key == pygame.K_h:
                self.neck_map = not self.neck_map
            elif event.key == pygame.K_F5:
                self._save_config()
            elif event.key == pygame.K_F6:
                self._load_config()
            elif event.key == pygame.K_ESCAPE:
                return False

        # ── Ratón: editor de alineación ────────────────────────────────
        elif event.type == pygame.MOUSEBUTTONDOWN:
            if self.align_editor_open:
                if event.button == 1:
                    kind, id_ = self._align_pick_at_pos(event.pos)
                    if kind == "red":
                        self.align_dragging = True
                        self._align_set_offset_from_mouse(event.pos)
                    elif kind == "mark":
                        self.align_drag_marker = id_
                        self.align_cursor_sec  = id_
                    elif kind == "ghost":
                        self._align_adopt_score_mark(id_, event.pos)
                    else:
                        self.align_cursor_sec = self._align_sec_of_pos(event.pos)
                elif event.button == 2:
                    self.align_panning         = True
                    self.align_pan_start       = event.pos
                    self.align_pan_view_start  = self.align_view_start
                elif event.button == 3:
                    self._align_add_marker(event.pos)
                elif event.button == 4:
                    self._align_zoom(1.3, event.pos)
                elif event.button == 5:
                    self._align_zoom(1 / 1.3, event.pos)
                return True
            if event.button == 1:
                mx, my = event.pos
                if (TAB_Y <= my < NECK_Y
                        and not self.device_menu_open
                        and not self.pitch_menu_open
                        and not self.tuner_open):
                    self._drag_seeking    = True
                    self._drag_start_beat = self.beat_time
                    self._drag_start_mx   = mx

        elif event.type == pygame.MOUSEWHEEL:
            if self.align_editor_open:
                pos = getattr(event, "pos", None) or pygame.mouse.get_pos()
                self._align_zoom(1.3 if event.y > 0 else 1 / 1.3, pos)
                return True

        elif event.type == pygame.MOUSEBUTTONUP:
            if self.align_editor_open:
                self.align_dragging    = False
                self.align_drag_marker = None
                self.align_panning     = False
                return True
            if event.button == 1:
                self._drag_seeking = False

        elif event.type == pygame.MOUSEMOTION:
            if self.align_editor_open:
                if self.align_drag_marker is not None:
                    self._align_drag_marker_to(event.pos)
                elif self.align_dragging:
                    self._align_set_offset_from_mouse(event.pos)
                elif self.align_panning:
                    self._align_pan_to(event.pos[0])
                return True
            if self._drag_seeking:
                mx, _ = event.pos
                delta_px = mx - self._drag_start_mx
                new_beat = max(0.0, self._drag_start_beat - delta_px / self.px_per_16th)
                self._seek_to_beat(new_beat)
                self._drag_start_beat = new_beat
                self._drag_start_mx   = mx

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
