"""Teclado: un handler por panel modal y una tabla para las teclas globales."""
import logging

import pygame

from .. import features
from ..audio import INPUT_AVAILABLE
from ..config import PITCH_METHODS

log = logging.getLogger(__name__)


def _offset_step(sign, shift, ctrl):
    """Paso de offset/inicio: fino (0.05), medio con Shift (0.5) o grueso (5.0)."""
    return sign * (5.0 if ctrl else 0.5 if shift else 0.05)


# Teclas globales sin argumentos: tecla -> método del host.
_SIMPLE_KEYS = {
    pygame.K_SPACE: "toggle_play",
    pygame.K_r: "reiniciar",
    pygame.K_a: "_open_arp",
    pygame.K_b: "_toggle_tempo_mode",
    pygame.K_c: "_toggle_countdown",
    pygame.K_d: "_toggle_device_menu",
    pygame.K_e: "_training_open",
    pygame.K_g: "_lab_open",
    pygame.K_h: "_toggle_neck_map",
    pygame.K_i: "_toggle_feature_menu",
    pygame.K_j: "_toggle_chords_on",
    pygame.K_k: "_cor_open",
    pygame.K_l: "_toggle_song_menu",
    pygame.K_m: "toggle_mute",
    pygame.K_n: "_toggle_metro",
    pygame.K_o: "_ear_open",
    pygame.K_p: "_toggle_pitch_menu",
    pygame.K_s: "cycle_score_renderer",
    pygame.K_t: "_toggle_tuner",
    pygame.K_v: "_open_scale",
    pygame.K_w: "_toggle_align_editor",
    pygame.K_x: "_open_tech",
    pygame.K_y: "_toggle_chord_editor",
    pygame.K_F1: "_toggle_help",
    pygame.K_F2: "_toggle_mixer",
    pygame.K_F5: "_save_config",
    pygame.K_F6: "_reload_config",
    pygame.K_F7: "_start_generation",
    pygame.K_F8: "_toggle_gen_barlen",
    pygame.K_F9: "_chords_from_score",
}

# Navegación del editor de acordes (Y): tecla -> (delta, absoluto).
_CHORD_EDITOR_MOVES = {
    pygame.K_UP: (-1, None),
    pygame.K_DOWN: (+1, None),
    pygame.K_PAGEUP: (-10, None),
    pygame.K_PAGEDOWN: (+10, None),
    pygame.K_HOME: (None, 0),
    pygame.K_END: (None, -1),
    pygame.K_LEFT: (-1, None),
    pygame.K_RIGHT: (+1, None),
}

# Teclas que dependen de Shift/Ctrl: (host, shift, ctrl) -> acción.
_MOD_KEYS = {
    pygame.K_UP: lambda app, s, c: app.ajustar_bpm(+5),
    pygame.K_DOWN: lambda app, s, c: app.ajustar_bpm(-5),
    pygame.K_COMMA: lambda app, s, c: app.ajustar_offset(
        _offset_step(-1, s, c)),
    pygame.K_PERIOD: lambda app, s, c: app.ajustar_offset(
        _offset_step(+1, s, c)),
    pygame.K_LEFTBRACKET: lambda app, s, c: app.ajustar_inicio(
        _offset_step(-1, s, c)),
    pygame.K_RIGHTBRACKET: lambda app, s, c: app.ajustar_inicio(
        _offset_step(+1, s, c)),
    pygame.K_LEFT: lambda app, s, c: app._snap_measure(-1),
    pygame.K_RIGHT: lambda app, s, c: app._snap_measure(+1),
}


class KeyboardMixin:
    """Reparto del teclado entre los paneles y los atajos globales."""

    # ── reparto ────────────────────────────────────────────────────────
    def _on_keydown(self, event):
        """Recorre los paneles abiertos de arriba a abajo y cae en las globales."""
        if self.gen_running:
            return True
        if self.gen_error:
            self.gen_error = ""
            if self.songs:
                self.gen_notice = bool(
                    self.songs[self.song_idx].get("audio_only"))
            return True

        handlers = (
            self._key_chord_editor,
            self._key_chord_bar_typing,
            self._key_feature_menu,
            self._key_device_menu,
            self._key_pitch_menu,
            self._key_song_menu,
            self._key_mixer,
            self._key_tuner,
            self._key_modes,
            self._key_help,
            self._key_align,
        )
        for handler in handlers:
            result = handler(event)
            if result is not None:
                return result
        return self._key_main(event)

    def _key_modes(self, event):
        """Modos con teclado propio (E/G/K/O/X/A/V)."""
        if self.training_open:
            return self._key_training(event)
        if self.lab_open:
            return self._key_lab(event)
        if self.cor_open:
            return self._key_cor(event)
        if self.ear_open:
            return self._key_ear(event)
        if self.tx_open:
            return self._key_seq("tx", event)
        if self.ar_open:
            return self._key_seq("ar", event)
        if self.sc_open:
            return self._key_seq("sc", event)
        return None

    def _key_main(self, event):
        """Teclas globales: transporte, paneles y atajos (sin modales)."""
        mods = pygame.key.get_mods()
        shift = mods & pygame.KMOD_SHIFT
        ctrl = mods & pygame.KMOD_CTRL

        if event.key == pygame.K_s and ctrl:
            self._save_chords_or_config()
            return True
        if self._chord_bar_key(event.key):
            return True

        name = _SIMPLE_KEYS.get(event.key)
        if name is not None:
            getattr(self, name)()
            return True
        action = _MOD_KEYS.get(event.key)
        if action is not None:
            action(self, shift, ctrl)
            return True
        return event.key != pygame.K_ESCAPE

    def _chord_bar_key(self, key):
        """Atajos de la celda de acorde seleccionada; False si no aplica."""
        if self.chord_bar_sel_measure is None:
            return False
        if key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            self._chord_bar_edit_selected()
        elif key in (pygame.K_DELETE, pygame.K_BACKSPACE):
            self._chord_bar_delete()
        elif key == pygame.K_ESCAPE:
            self._chord_bar_clear()
            self.chord_bar_msg = ""
        else:
            return False
        return True

    def _save_chords_or_config(self):
        """Ctrl+S: guarda los acordes si hay cambios pendientes, si no el config."""
        if not self.chord_edit_dirty:
            self._save_config()
            return
        ok, msg = self._save_chords()
        self.chord_bar_msg = ("" if ok else "Error: ") + msg

    # ── paneles con teclado propio ─────────────────────────────────────
    def _key_chord_editor(self, event):
        """Editor de acordes (Y): intercepta todo el teclado."""
        if not self.chord_edit_open:
            return None
        if self.chord_edit_typing:
            return self._key_chord_edit_typing(event)

        key = event.key
        move = _CHORD_EDITOR_MOVES.get(key)
        if key in (pygame.K_ESCAPE, pygame.K_y):
            self.chord_edit_open = False
        elif move is not None:
            self._chord_edit_select(move[0], absolute=move[1])
        elif key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_t):
            self._chord_edit_begin_typing()
        elif key == pygame.K_DELETE:
            self._chord_edit_delete()
        elif key == pygame.K_d:
            self._chords_from_score()
        elif key == pygame.K_s and (pygame.key.get_mods() & pygame.KMOD_CTRL):
            self._chord_edit_save()
        return True

    def _key_chord_edit_typing(self, event):
        """Captura de texto de un acorde en el editor (Y)."""
        if event.key == pygame.K_ESCAPE:
            self.chord_edit_typing = False
            self.chord_edit_buf = ""
        elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            rows = self._chord_edit_rows()
            if rows:
                self._chord_edit_apply(rows[self.chord_edit_sel][1],
                                       self.chord_edit_buf)
            self.chord_edit_typing = False
            self.chord_edit_msg = ""
        elif event.key == pygame.K_BACKSPACE:
            self.chord_edit_buf = self.chord_edit_buf[:-1]
        else:
            ch = event.unicode
            if ch and ch.isprintable() and len(self.chord_edit_buf) < 8:
                self.chord_edit_buf += ch
        return True

    def _chord_edit_select(self, delta, absolute=None):
        """Mueve la selección del editor de acordes, acotada a las filas."""
        rows = self._chord_edit_rows()
        last = len(rows) - 1
        if absolute is not None:
            target = last if absolute < 0 else absolute
        else:
            target = self.chord_edit_sel + delta
        self.chord_edit_sel = max(0, min(last, target))

    def _chord_edit_begin_typing(self):
        """Abre la captura de texto con el acorde actual como borrador."""
        rows = self._chord_edit_rows()
        if not rows:
            return
        self.chord_edit_typing = True
        self.chord_edit_buf = self._chord_edit_name_at(
            self._chord_edit_sec(rows[self.chord_edit_sel][1]))
        if self.chord_edit_buf == "—":
            self.chord_edit_buf = ""

    def _chord_edit_delete(self):
        """Vacía el acorde de la fila seleccionada."""
        rows = self._chord_edit_rows()
        if rows:
            self._chord_edit_apply(rows[self.chord_edit_sel][1], "")

    def _key_chord_bar_typing(self, event):
        """Edición de acorde sobre la barra (texto + sugerencias)."""
        if not self.chord_bar_typing:
            return None
        if event.key == pygame.K_ESCAPE:
            self._chord_bar_cancel()
        elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            self._chord_bar_commit()
        elif event.key == pygame.K_TAB:
            self._chord_bar_sugg_move(None)
        elif event.key in (pygame.K_UP, pygame.K_DOWN):
            self._chord_bar_sugg_move(-1 if event.key == pygame.K_UP else +1)
        elif event.key == pygame.K_BACKSPACE:
            self.chord_bar_buf = self.chord_bar_buf[:-1]
            self.chord_bar_replace = False
            self._chord_bar_sugg_reset()
        else:
            ch = event.unicode
            if ch and ch.isprintable():
                if self.chord_bar_replace:
                    self.chord_bar_buf = ch
                elif len(self.chord_bar_buf) < 8:
                    self.chord_bar_buf += ch
                self.chord_bar_replace = False
                self._chord_bar_sugg_reset()
        return True

    def _chord_bar_sugg_move(self, step):
        """Elige sugerencia: Tab la acepta, flechas recorren la lista."""
        sugg = self.chord_bar_sugg_cache or []
        if not sugg:
            return
        idx = self.chord_bar_sugg_idx
        if step is None:
            self.chord_bar_buf = sugg[idx] if 0 <= idx < len(sugg) else sugg[0]
        else:
            idx = 0 if idx < 0 else max(0, min(len(sugg) - 1, idx + step))
            self.chord_bar_sugg_idx = idx
            self.chord_bar_buf = sugg[idx]
        self.chord_bar_replace = False

    def _key_feature_menu(self, event):
        if not self.view.feature_menu_open:
            return None
        feats = features.FEATURES
        if event.key == pygame.K_UP:
            self.view.feature_menu_sel = max(0, self.view.feature_menu_sel - 1)
        elif event.key == pygame.K_DOWN:
            self.view.feature_menu_sel = min(len(feats) - 1,
                                             self.view.feature_menu_sel + 1)
        elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            self._feature_toggle(feats[self.view.feature_menu_sel]["id"])
        elif event.key in (pygame.K_ESCAPE, pygame.K_i):
            self.view.feature_menu_open = False
        return True

    def _key_device_menu(self, event):
        if not self.view.device_menu_open:
            return None
        if event.key == pygame.K_UP:
            self.view.device_menu_sel = max(0, self.view.device_menu_sel - 1)
        elif event.key == pygame.K_DOWN:
            self.view.device_menu_sel = min(len(self.audio_devices) - 1,
                                            self.view.device_menu_sel + 1)
        elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            self._start_audio(self.view.device_menu_sel)
            self.view.device_menu_open = False
        elif event.key in (pygame.K_ESCAPE, pygame.K_d):
            self.view.device_menu_open = False
        return True

    def _key_pitch_menu(self, event):
        if not self.view.pitch_menu_open:
            return None
        if event.key == pygame.K_UP:
            self.view.pitch_menu_sel = max(0, self.view.pitch_menu_sel - 1)
        elif event.key == pygame.K_DOWN:
            self.view.pitch_menu_sel = min(len(PITCH_METHODS) - 1,
                                           self.view.pitch_menu_sel + 1)
        elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            self.pitch_method = PITCH_METHODS[self.view.pitch_menu_sel]
            self.view.pitch_menu_open = False
            self._start_audio()
        elif event.key in (pygame.K_ESCAPE, pygame.K_p):
            self.view.pitch_menu_open = False
        return True

    def _key_song_menu(self, event):
        if not self.view.song_menu_open:
            return None
        if event.key == pygame.K_UP:
            self.view.song_menu_sel = max(0, self.view.song_menu_sel - 1)
        elif event.key == pygame.K_DOWN:
            self.view.song_menu_sel = min(len(self.songs) - 1,
                                          self.view.song_menu_sel + 1)
        elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            self._load_song(self.view.song_menu_sel, caption=True)
            self.view.song_menu_open = False
        elif event.key in (pygame.K_ESCAPE, pygame.K_l):
            self.view.song_menu_open = False
        return True

    def _key_mixer(self, event):
        """Mixer (F2): volumen y mute por pista."""
        if not self.view.mixer_open:
            return None
        tracks = self.MIX_TRACKS
        tid = tracks[self.view.mixer_sel][0]
        vol, _ = self._mix_get(tid)
        if event.key == pygame.K_UP:
            self.view.mixer_sel = max(0, self.view.mixer_sel - 1)
        elif event.key == pygame.K_DOWN:
            self.view.mixer_sel = min(len(tracks) - 1, self.view.mixer_sel + 1)
        elif event.key == pygame.K_LEFT:
            self._mix_set(tid, vol=vol - 0.05)
        elif event.key == pygame.K_RIGHT:
            self._mix_set(tid, vol=vol + 0.05)
        elif event.key == pygame.K_m:
            _, mute = self._mix_get(tid)
            self._mix_set(tid, mute=not mute)
        elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER,
                           pygame.K_ESCAPE, pygame.K_F2):
            self.view.mixer_open = False
        return True

    def _key_tuner(self, event):
        if not self.view.tuner_open:
            return None
        if event.key in (pygame.K_ESCAPE, pygame.K_t):
            self.view.tuner_open = False
        return True

    def _key_help(self, event):
        if not self.view.help_open:
            return None
        if event.key in (pygame.K_ESCAPE, pygame.K_F1):
            self.view.help_open = False
        return True

    def _key_align(self, event):
        """Editor de alineación (W): marcas de tempo sobre la onda."""
        if not self.align_editor_open:
            return None
        ctrl = pygame.key.get_mods() & pygame.KMOD_CTRL
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
            self._align_cursor(-(5.0 if ctrl else 1.0))
        elif event.key == pygame.K_RIGHT:
            self._align_cursor(+5.0 if ctrl else +1.0)
        elif event.key in (pygame.K_DELETE, pygame.K_BACKSPACE):
            self._align_delete_marker()
        elif event.key == pygame.K_r:
            self._align_reset_marks()
        return True

    def _align_cursor(self, delta_sec):
        """Mueve el cursor del editor de alineación dentro de la onda."""
        self.align_cursor_sec = max(
            0.0, min(self.align_total_sec, self.align_cursor_sec + delta_sec))
        self._align_keep_cursor_visible()

    # ── acciones de las teclas globales ────────────────────────────────
    def _toggle_tempo_mode(self):
        """B: alterna el tempo mostrado entre BPM y figuras."""
        self.view.tempo_display_mode = (
            "bpm" if self.view.tempo_display_mode == "figura" else "figura")

    def _toggle_device_menu(self):
        if not (INPUT_AVAILABLE and self.audio_devices):
            return
        self.view.device_menu_open = not self.view.device_menu_open
        self.view.device_menu_sel = self.device_idx

    def _toggle_pitch_menu(self):
        self.view.pitch_menu_open = not self.view.pitch_menu_open

    def _toggle_feature_menu(self):
        self.view.feature_menu_open = not self.view.feature_menu_open
        self.feature_msg.clear()
        self.feature_log.clear()

    def _toggle_song_menu(self):
        self.view.song_menu_open = not self.view.song_menu_open
        self.view.song_menu_sel = self.song_idx

    def _toggle_tuner(self):
        self.view.tuner_open = not self.view.tuner_open

    def _toggle_help(self):
        self.view.help_open = not self.view.help_open

    def _toggle_mixer(self):
        self.view.mixer_open = not self.view.mixer_open
        self.view.mixer_sel = 0

    def _toggle_countdown(self):
        self.countdown_enabled = not self.countdown_enabled

    def _toggle_metro(self):
        self.metro_sound = not self.metro_sound

    def _toggle_neck_map(self):
        self.view.neck_map = not self.view.neck_map

    def _toggle_chords_on(self):
        self.view.chords_on = not self.view.chords_on

    def _toggle_align_editor(self):
        if self.align_editor_open:
            self._close_align_editor(True)
        else:
            self._open_align_editor()

    def _toggle_gen_barlen(self):
        """F8: compás de la generación de partitura (3/4 ↔ 4/4)."""
        self.gen_barlen = 4 if self.gen_barlen == 3 else 3
        log.info(f"[Gen] Compás para generar: {self.gen_barlen}/4")

    def _reload_config(self):
        self._load_config()
        self._apply_mix()

    def _open_tech(self):
        self._seq_open("tx")

    def _open_arp(self):
        self._seq_open("ar")

    def _open_scale(self):
        self._seq_open("sc")
