"""Ratón: clics, arrastres y rueda sobre la onda, el mástil y los paneles.

Ningún gesto de ratón cierra la aplicación: estos handlers no devuelven valor
y `app.handle_event` responde ``True`` por ellos.
"""
import pygame

from ..config import HEADER_H

class MouseMixin:
    """Reparto del ratón entre los paneles y la navegación de la onda."""

    def _overlay_open(self):
        """¿Hay algún panel modal tapando las zonas de juego?"""
        view = self.view
        return bool(view.device_menu_open or view.pitch_menu_open
                    or view.song_menu_open or view.feature_menu_open
                    or view.tuner_open or view.help_open
                    or self.training_open or self.lab_open
                    or self.cor_open or self.ear_open)

    def _in_waveform(self, pos):
        """Carril de audio dentro de la tarjeta de partitura."""
        return self.layout.audio.collidepoint(pos)

    # ── botón pulsado ──────────────────────────────────────────────────
    def _on_mouse_down(self, event):
        if not self._mouse_down_modal(event):
            self._mouse_down_zone(event)

    def _transport_click(self, pos):
        """Barra de transporte: play, reinicio, tempo y metrónomo."""
        L = self.layout
        if not L.transport.collidepoint(pos):
            return False
        b = L.buttons
        if b["play"].collidepoint(pos):
            self.toggle_play()
        elif b["restart"].collidepoint(pos):
            self.reiniciar()
        elif b["metro"].collidepoint(pos):
            self._toggle_metro()
        elif b["bpm"].collidepoint(pos):
            self.ajustar_bpm(+5)
        return True

    def _mouse_down_modal(self, event):
        """Paneles que se comen el clic; True si el evento queda consumido."""
        if self.chord_edit_open:
            return True
        if self.chord_bar_typing:
            if event.button == 1:
                self._chord_bar_sugg_click(event.pos)
            return True
        if event.button == 1 and self._header_chip_click(event.pos):
            return True
        return self._click_strip(event)

    def _click_strip(self, event):
        """Tarjeta de acordes: selecciona el compás que suena para editarlo."""
        if self.layout.chords.collidepoint(event.pos):
            if event.button == 1:
                self._chord_bar_select_current()
            return True
        if event.button == 1:
            self._chord_bar_clear()
            self.chord_bar_msg = ""
        return False

    def _chord_bar_sugg_click(self, pos):
        """Elegir una sugerencia de acorde con el ratón."""
        for name, rect in self.chord_bar_sugg_layout():
            if rect.collidepoint(pos):
                self.chord_bar_buf = name
                self._chord_bar_commit()
                break

    def _mouse_down_zone(self, event):
        """Clic en el área de juego: alineación, transporte, onda o mástil."""
        if self.align_editor_open:
            self._mouse_down_align(event)
        elif event.button == 1:
            if self._transport_click(event.pos):
                return
            self._mouse_down_playback(event)
        elif event.button in (2, 3):
            self._mouse_down_wave(event)

    def _mouse_down_align(self, event):
        """Clics del editor de alineación: anclas, marcas, zoom y paneo."""
        if event.button == 1:
            kind, id_ = self._align_pick_at_pos(event.pos)
            if kind == "red":
                self.align_dragging = True
                self._align_set_offset_from_mouse(event.pos)
            elif kind == "start":
                self.align_dragging_start = True
                self._align_set_song_start_from_mouse(event.pos)
            elif kind == "mark":
                self.align_drag_marker = id_
                self.align_cursor_sec = id_
            elif kind == "ghost":
                self._align_adopt_score_mark(id_, event.pos)
            else:
                self.align_cursor_sec = self._align_sec_of_pos(event.pos)
        elif event.button == 2:
            self.align_panning = True
            self.align_pan_start = event.pos
            self.align_pan_view_start = self.align_view_start
        elif event.button == 3:
            self._align_add_marker(event.pos)
        elif event.button == 4:
            self._align_zoom(1.3, event.pos)
        elif event.button == 5:
            self._align_zoom(1 / 1.3, event.pos)

    def _mouse_down_playback(self, event):
        """Clic izquierdo: onda, mástil/piano y arrastre de la partitura."""
        if not self._overlay_open():
            on_wave = (self._in_waveform(event.pos)
                       and getattr(self, "song_wave", None) is not None)
            if on_wave:
                self._mouse_down_anchor_or_seek(event)
            elif not self._preview_hit(event.pos):
                mx, my = event.pos
                L = self.layout
                if L.score.collidepoint(mx, my):
                    self._start_seek_drag(mx)

    def _preview_hit(self, pos):
        """Mástil o piano: True si el clic cayó en un instrumento."""
        midi = self._piano_hit(pos)
        if midi is not None:
            self._preview_from_piano(midi)
            return True
        fret_string = self._neck_hit(pos)
        if fret_string is not None:
            self._preview_from_neck(*fret_string)
            return True
        return False

    def _mouse_down_anchor_or_seek(self, event):
        """Cerca de la línea verde/roja se agarra el ancla; si no, se busca."""
        mx = event.pos[0]
        vx = self.view.viewport_x
        cx = self.layout.cursor_x
        s0 = self._bass_start16()
        xb = self.px_of(s0) - vx + cx
        xs = cx - vx
        db = abs(mx - xb) if -1 <= xb < self.layout.w + 1 else 999
        ds = abs(mx - xs) if -1 <= xs < self.layout.w + 1 else 999
        if min(db, ds) <= 9:
            self.view._anchor_drag = ("bass" if db <= ds else "start")
            self.view._anchor_drag_mx = mx
        else:
            self._start_seek_drag(mx)

    def _start_seek_drag(self, mx):
        self.view._drag_seeking = True
        self.view._drag_start_beat = self.beat_time
        self.view._drag_start_mx = mx

    def _mouse_down_wave(self, event):
        """Botón central/derecho sobre la onda: mover el audio o navegar."""
        if (not self._overlay_open() and self._in_waveform(event.pos)
                and getattr(self, "song_wave", None) is not None):
            if event.button == 3:      # derecha = navegar (como el tab)
                self._start_seek_drag(event.pos[0])
            else:                      # central = mover el audio (ambas anclas)
                self._begin_wave_drag(event.pos[0])

    def _begin_wave_drag(self, mx):
        self.view._wave_dragging = True
        self.view._wave_drag_mx = mx
        self.view._wave_drag_off = self.mp3_offset_sec
        self.view._wave_drag_start = self.song_start_sec
        self.view._wave_drag_acc = 0.0

    # ── botón soltado ──────────────────────────────────────────────────
    def _on_mouse_up(self, event):
        if self.align_editor_open:
            self._reset_align_drag()
        elif not self.chord_edit_open:
            self._end_drag(event)

    def _reset_align_drag(self):
        self.align_dragging = False
        self.align_dragging_start = False
        self.align_drag_marker = None
        self.align_panning = False

    def _end_drag(self, event):
        if event.button in (1, 3):
            self.view._drag_seeking = False
            if self.view._anchor_drag:
                self.view._anchor_drag = None
                self._remember_anchors()
        if event.button == 2:
            self.view._wave_dragging = False
            self._remember_anchors()

    # ── rueda ──────────────────────────────────────────────────────────
    def _on_wheel(self, event):
        if self.chord_edit_open:
            self._chord_edit_select(-int(event.y))
        elif not self.chord_bar_typing and self.align_editor_open:
            pos = getattr(event, "pos", None) or pygame.mouse.get_pos()
            self._align_zoom(1.3 if event.y > 0 else 1 / 1.3, pos)

    # ── movimiento ─────────────────────────────────────────────────────
    def _on_mouse_motion(self, event):
        if not (self.chord_edit_open or self.chord_bar_typing):
            self._update_chip_hover(event.pos)
            self._mouse_motion_drag(event)

    def _update_chip_hover(self, pos):
        """Resalta el chip de la cabecera o la barra de transporte."""
        self.view.chip_hover = ""
        if 0 <= pos[1] <= self.layout.header.h:
            for action, _text, rect in self._header_chips_layout()[0]:
                if rect.collidepoint(pos):
                    self.view.chip_hover = action
                    break
        elif self.layout.buttons["play"].collidepoint(pos):
            self.view.chip_hover = "play"

    def _mouse_motion_drag(self, event):
        if self.align_editor_open:
            self._mouse_motion_align(event)
        elif self.view._anchor_drag:
            self._mouse_motion_anchor(event)
        elif self.view._wave_dragging:
            self._mouse_motion_wave(event)
        elif self.view._drag_seeking:
            self._mouse_motion_seek(event)

    def _mouse_motion_align(self, event):
        if self.align_drag_marker is not None:
            self._align_drag_marker_to(event.pos)
        elif self.align_dragging:
            self._align_set_offset_from_mouse(event.pos)
        elif self.align_dragging_start:
            self._align_set_song_start_from_mouse(event.pos)
        elif self.align_panning:
            self._align_pan_to(event.pos[0])

    def _mouse_motion_anchor(self, event):
        """Arrastrar un ancla: px → dieciseisavos → segundos."""
        mx = event.pos[0]
        dx = mx - self.view._anchor_drag_mx
        if dx:
            qpm = (self._tempo_at(self._bass_start16())
                   if self.view._anchor_drag == "bass" else self._lead_qpm())
            dsec = self._px_to_sec(dx, qpm)
            if self.view._anchor_drag == "bass":
                self.mp3_offset_sec += dsec
            else:
                self.song_start_sec += dsec
            self._clamp_anchors()
            self.view._anchor_drag_mx = mx

    def _mouse_motion_wave(self, event):
        """Agarrar la onda: a la derecha el ataque suena más tarde (bajan anclas)."""
        mx = event.pos[0]
        dx = mx - self.view._wave_drag_mx
        if dx:
            qpm = self._tempo_at(self._bass_start16())
            self.view._wave_drag_acc += self._px_to_sec(dx, qpm)
            shift = min(self.view._wave_drag_acc, self.view._wave_drag_start)
            self.mp3_offset_sec = max(0.0, self.view._wave_drag_off - shift)
            self.song_start_sec = max(0.0, self.view._wave_drag_start - shift)
            self.view._wave_drag_mx = mx

    def _mouse_motion_seek(self, event):
        mx = event.pos[0]
        delta_px = mx - self.view._drag_start_mx
        new_beat = max(
            0.0, self.view._drag_start_beat - delta_px / self.view.px_per_16th)
        self._seek_to_beat(new_beat)
        self.view._drag_start_beat = new_beat
        self.view._drag_start_mx = mx

    def _px_to_sec(self, dx, qpm):
        """Píxeles de la vista → segundos, con el tempo efectivo."""
        ppt = self.view.px_per_16th or 1.0
        return (dx / ppt) / 4.0 * 60.0 / max(1e-6, qpm)
