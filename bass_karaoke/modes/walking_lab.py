"""Walking Lab — moldes Mayor/menor en bucle (tecla G)."""
import pygame

from ..music import midi_of
from ..walking import EXERCISES, build_exercise


class WalkingLabMixin:
    """Estado y acciones del Walking Lab."""

    def _init_walking_lab_state(self):
        self.lab_open = False
        self.lab_running = False
        self.lab_idx = 0
        self.lab_title = ""
        self.lab_bars = []
        self.lab_steps = []
        self.lab_roots = []
        self.lab_bpm = 80.0
        self.lab_t = 0.0
        self.lab_last_total = -1
        self.lab_beat = 0
        self.lab_bar = 0
        self.lab_heard = False
        self.lab_ok = 0
        self.lab_total = 0
        self.lab_role_ok = [0, 0, 0, 0]
        self.lab_role_total = [0, 0, 0, 0]
        self.lab_beat_res = [None] * 4
        self.lab_last_msg = ""

    def _lab_open(self):
        self.lab_open = True
        if not self.lab_steps:
            self._lab_load(self.lab_idx)

    def _lab_load(self, idx: int):
        idx = int(idx) % len(EXERCISES)
        self.lab_idx = idx
        ex = EXERCISES[idx]
        self.lab_title = ex["title"]
        self.lab_bars = [b["name"] for b in ex["bars"]]
        self.lab_steps = build_exercise(ex)
        self.lab_roots = [midi_of(b["string"], b["fret"]) for b in ex["bars"]]
        self.lab_t = 0.0
        self.lab_last_total = -1
        self.lab_beat = 0
        self.lab_bar = 0
        self.lab_heard = False
        self.lab_ok = 0
        self.lab_total = 0
        self.lab_role_ok = [0, 0, 0, 0]
        self.lab_role_total = [0, 0, 0, 0]
        self.lab_beat_res = [None] * 4
        self.lab_last_msg = ""

    def _lab_toggle_run(self):
        if not self.lab_steps:
            self._lab_load(self.lab_idx)
        self.lab_running = not self.lab_running
        self.lab_t = 0.0
        self.lab_last_total = -1
        self.lab_beat = 0
        self.lab_bar = 0
        self.lab_heard = False
        self.lab_beat_res = [None] * 4

    def _lab_tempo(self, delta: float):
        self.lab_bpm = max(40.0, min(180.0, self.lab_bpm + delta))

    def _lab_score_beat(self):
        """Puntúa el tiempo recién terminado (según el latch lab_heard)."""
        if not self.lab_steps:
            return
        bar = self.lab_bar % len(self.lab_steps)
        beat = self.lab_beat % 4
        ok = bool(self.lab_heard)
        self.lab_total += 1
        self.lab_role_total[beat] += 1
        if ok:
            self.lab_ok += 1
            self.lab_role_ok[beat] += 1
        if beat < len(self.lab_beat_res):
            self.lab_beat_res[beat] = ok
        st = self.lab_steps[bar][beat]
        self.lab_last_msg = (f"T{beat + 1} {st['role']} {st['name']} ✓" if ok
                             else f"T{beat + 1} ✗ (toca {st['name']})")

    def _key_lab(self, event) -> bool:
        """Teclado del Walking Lab (modal)."""
        if event.key in (pygame.K_ESCAPE, pygame.K_g):
            self.lab_open = False
            self.lab_running = False
        elif event.key == pygame.K_SPACE:
            self._lab_toggle_run()
        elif event.key == pygame.K_n:
            self._lab_load(self.lab_idx + 1)
        elif event.key == pygame.K_UP:
            self._lab_tempo(+5)
        elif event.key == pygame.K_DOWN:
            self._lab_tempo(-5)
        return True
