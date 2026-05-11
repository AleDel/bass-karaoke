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
    BPM_DEFAULT, BPM_ORIGINAL, PITCH_METHODS, MUSICXML_PATH, TG_PATH, CONFIG_PATH,
    C_BG, C_BG2, C_PANEL, C_DGRAY, C_ACCENT, C_GREEN, C_RED,
    C_BLUE, C_WHITE, C_GRAY, C_OK, C_ERR, C_WAIT,
    MIN_HZ, MAX_HZ,
)
from .utils import fret_to_hz, hz_to_note_name, notes_match
from .parser import parse_musicxml, parse_grace_notes
from .audio import VarispeedPlayer, VARSPEED_OK, PitchEngine, PITCH_AVAILABLE, enumerate_devices
from .score import (
    init_score_surface, VEROVIO_OK, CAIROSVG_OK,
    init_score_surface_music21, MUSIC21_OK,
)
from .ui import (
    draw_tab, draw_score, draw_guitartab, draw_neck, draw_piano,
    draw_note_panel, draw_metronome, draw_pitch_panel,
    draw_stats_panel, draw_bottom_bar,
    draw_tuner, draw_countdown, draw_device_menu, draw_pitch_menu,
)

FPS = 60


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
        self.pitch_method    = "crepe-tiny"
        self.pitch_menu_open = False
        self.pitch_menu_sel  = PITCH_METHODS.index("crepe-tiny")

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

        # ── Scroll ─────────────────────────────────────────────────────
        self.px_per_16th = 30
        self.viewport_x  = 0.0
        self.target_x    = 0.0

        # ── MusicXML ───────────────────────────────────────────────────
        self.notes       = []
        self.sections    = []
        self.grace_notes = []
        self._load_notes()

        # ── Score pre-render ───────────────────────────────────────────
        self.score_renderer  = "verovio"
        self._score_loading  = False
        self._score_surf     = None
        self._score_note_xs  = []
        self._score_scroll_x = 0.0
        self._score_cache    = {}   # {renderer: (surf, note_xs)} para no re-renderizar
        self._score_total16  = (
            (self.notes[-1]["start16"] + self.notes[-1]["dur"]) if self.notes else 1
        )

        # ── Piano ──────────────────────────────────────────────────────
        self._piano_keys_list = []

        # ── Audio MP3 ──────────────────────────────────────────────────
        self._vsp     = VarispeedPlayer() if VARSPEED_OK else None
        self.mp3_path = self._find_mp3()

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

        self._load_config()

        if self.score_renderer == "music21" and MUSIC21_OK:
            self._init_score_music21()
        elif VEROVIO_OK and CAIROSVG_OK:
            self._init_score_verovio()
        elif MUSIC21_OK:
            self.score_renderer = "music21"
            self._init_score_music21()

        if PITCH_AVAILABLE and self.audio_devices:
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
        cfg = {
            "bpm":               self.bpm,
            "mp3_offset_sec":    self.mp3_offset_sec,
            "device_idx":        self.device_idx,
            "muted":             self.muted,
            "pitch_method":      self.pitch_method,
            "countdown_enabled": self.countdown_enabled,
            "score_renderer":    self.score_renderer,
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
            print(f"[Config] cargada  BPM={self.bpm}  offset={self.mp3_offset_sec:+.2f}s  "
                  f"pitch={self.pitch_method}  renderer={self.score_renderer}")
        except Exception as e:
            print(f"[Config WARN] {e}")

    # ══════════════════════════════════════════════════════════════════
    #  NOTAS / MP3
    # ══════════════════════════════════════════════════════════════════
    def _load_notes(self):
        if not os.path.exists(MUSICXML_PATH):
            print(f"[ERROR] MusicXML no encontrado: {MUSICXML_PATH}")
            return
        try:
            notes, sections, bpm = parse_musicxml(MUSICXML_PATH)
            self.notes       = notes
            self.sections    = sections
            self.bpm         = bpm
            self.grace_notes = parse_grace_notes(TG_PATH, notes)
            for n in notes:
                sec = n["section"]
                if sec not in self.section_stats:
                    self.section_stats[sec] = {"ok": 0, "total": 0}
            print(f"[OK] MusicXML: {len(notes)} notas, {bpm} BPM  graces={len(self.grace_notes)}")
        except Exception as e:
            print(f"[ERROR] MusicXML: {e}")
            import traceback; traceback.print_exc()

    def _find_mp3(self):
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # Ensayos/
        for folder in [os.path.join(base, "cancion"), base]:
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
        surf, note_xs = init_score_surface(self.notes)
        self._score_surf    = surf
        self._score_note_xs = note_xs
        if surf is not None:
            self._score_cache["verovio"] = (surf, note_xs)

    def _init_score_music21(self):
        if "music21" in self._score_cache:
            self._score_surf, self._score_note_xs = self._score_cache["music21"]
            print("[Music21] usando caché")
            return
        surf, note_xs = init_score_surface_music21(self.notes)
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

        self._pitch_engine = PitchEngine(
            method=self.pitch_method,
            device_id=dev_id,
            on_update=on_update,
            on_engine_label=on_engine_label,
        )
        self._pitch_engine.start()

    def _stop_audio(self):
        if self._pitch_engine is not None:
            self._pitch_engine.stop()
            self._pitch_engine = None

    # ══════════════════════════════════════════════════════════════════
    #  HELPERS
    # ══════════════════════════════════════════════════════════════════
    def px_of(self, beat16):
        return int(beat16 * self.px_per_16th)

    def current_note(self):
        return self.notes[self.note_idx] if self.note_idx < len(self.notes) else None

    def _speed_ratio(self):
        return self.bpm / BPM_ORIGINAL

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
            offset = (beat16 / 4.0) * (60.0 / self.bpm) + self.mp3_offset_sec
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
            offset = (self.beat_time / 4.0) * (60.0 / self.bpm) + self.mp3_offset_sec
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
            offset = (self.beat_time / 4.0) * (60.0 / self.bpm) + self.mp3_offset_sec
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
                offset = (self.beat_time / 4.0) * (60.0 / self.bpm) + self.mp3_offset_sec
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

        delta16 = dt * (self.bpm / 60.0) * 4.0
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
        if cur and PITCH_AVAILABLE:
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
        if self.tuner_open:
            draw_tuner(self)
        pygame.display.flip()

    def _draw_header(self):
        pygame.draw.rect(self.screen, C_PANEL, (0, 0, W, HEADER_H))
        pygame.draw.line(self.screen, C_ACCENT, (0, HEADER_H), (W, HEADER_H), 2)

        title = self.font_title.render(
            "Bass Karaoke  –  Feet Don't Fail Me Now  |  Joy Crookes",
            True, C_WHITE)
        self.screen.blit(title, (12, 8))

        bpm_t = self.font_med.render(f"{self.bpm:.0f} BPM", True, C_ACCENT)
        self.screen.blit(bpm_t, (W - 155, 8))

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

            # ── Tuner ──────────────────────────────────────────────────
            if self.tuner_open:
                if event.key in (pygame.K_ESCAPE, pygame.K_t):
                    self.tuner_open = False
                return True

            # ── Controles principales ──────────────────────────────────
            mods = pygame.key.get_mods()
            shift = mods & pygame.KMOD_SHIFT

            if event.key == pygame.K_SPACE:
                self.toggle_play()
            elif event.key == pygame.K_r:
                self.reiniciar()
            elif event.key == pygame.K_UP:
                self.ajustar_bpm(+5)
            elif event.key == pygame.K_DOWN:
                self.ajustar_bpm(-5)
            elif event.key == pygame.K_COMMA:
                self.ajustar_offset(-0.5 if shift else -0.05)
            elif event.key == pygame.K_PERIOD:
                self.ajustar_offset(+0.5 if shift else +0.05)
            elif event.key == pygame.K_LEFT:
                self._snap_measure(-1)
            elif event.key == pygame.K_RIGHT:
                self._snap_measure(+1)
            elif event.key == pygame.K_m:
                self.toggle_mute()
            elif event.key == pygame.K_d:
                if PITCH_AVAILABLE and self.audio_devices:
                    self.device_menu_open = not self.device_menu_open
                    self.device_menu_sel  = self.device_idx
            elif event.key == pygame.K_p:
                self.pitch_menu_open = not self.pitch_menu_open
            elif event.key == pygame.K_t:
                self.tuner_open = not self.tuner_open
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

        # ── Ratón: arrastrar para seek ────────────────────────────────
        elif event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1:
                mx, my = event.pos
                if (TAB_Y <= my < NECK_Y
                        and not self.device_menu_open
                        and not self.pitch_menu_open
                        and not self.tuner_open):
                    self._drag_seeking    = True
                    self._drag_start_beat = self.beat_time
                    self._drag_start_mx   = mx

        elif event.type == pygame.MOUSEBUTTONUP:
            if event.button == 1:
                self._drag_seeking = False

        elif event.type == pygame.MOUSEMOTION:
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
