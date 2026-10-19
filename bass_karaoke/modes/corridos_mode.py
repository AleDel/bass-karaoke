"""Corridos tumbados — bajeo en 3/4 (tecla K)."""
import pygame

from ..corridos import CORRIDO_EXERCISES, build_corrido


class CorridosModeMixin:
    """Estado y acciones del modo corridos."""

    def _init_corridos_state(self):
        self.cor_open = False
        self.cor_running = False
        self.cor_idx = 0
        self.cor_title = ""
        self.cor_bars = []
        self.cor_steps = []
        self.cor_roots = []
        self.cor_fifth = "down"
        self.cor_ornament = True
        self.cor_bpm = 90.0
        self.cor_t = 0.0
        self.cor_last_total = -1
        self.cor_beat = 0
        self.cor_bar = 0
        self.cor_heard = False
        self.cor_ok = 0
        self.cor_total = 0
        self.cor_role_ok = [0, 0, 0]
        self.cor_role_total = [0, 0, 0]
        self.cor_beat_res = [None] * 3
        self.cor_last_msg = ""

    def _cor_open(self):
        self._close_modes()
        self.cor_open = True
        if not self.cor_steps:
            self._cor_load(self.cor_idx)

    def _cor_load(self, idx: int):
        idx = int(idx) % len(CORRIDO_EXERCISES)
        self.cor_idx = idx
        ex = CORRIDO_EXERCISES[idx]
        self.cor_title = ex["title"]
        self.cor_steps, self.cor_roots = build_corrido(
            ex, fifth=self.cor_fifth, ornament=self.cor_ornament)
        self.cor_bars = []
        for b in ex["bars"]:
            self.cor_bars += [f"{b['name']} R", f"{b['name']} 5ª"]
        self.cor_t = 0.0
        self.cor_last_total = -1
        self.cor_beat = 0
        self.cor_bar = 0
        self.cor_heard = False
        self.cor_ok = 0
        self.cor_total = 0
        self.cor_role_ok = [0, 0, 0]
        self.cor_role_total = [0, 0, 0]
        self.cor_beat_res = [None] * 3
        self.cor_last_msg = ""

    def _cor_toggle_run(self):
        if not self.cor_steps:
            self._cor_load(self.cor_idx)
        self.cor_running = not self.cor_running
        self.cor_t = 0.0
        self.cor_last_total = -1
        self.cor_beat = 0
        self.cor_bar = 0
        self.cor_heard = False
        self.cor_beat_res = [None] * 3

    def _cor_tempo(self, delta: float):
        self.cor_bpm = max(40.0, min(180.0, self.cor_bpm + delta))

    def _cor_next_root(self, bar: int):
        """Raíz del acorde siguiente (objetivo del adorno)."""
        nch = max(1, len(self.cor_roots))
        return self.cor_roots[((bar // 2) + 1) % nch] if self.cor_roots else 0

    def _cor_score_beat(self):
        """Puntúa el tiempo recién terminado. Los silencios no puntúan."""
        if not self.cor_steps:
            return
        bar = self.cor_bar % len(self.cor_steps)
        beat = self.cor_beat % 3
        st = self.cor_steps[bar][beat]
        if st.get("midi") is None:
            return
        ok = bool(self.cor_heard)
        self.cor_total += 1
        self.cor_role_total[beat] += 1
        if ok:
            self.cor_ok += 1
            self.cor_role_ok[beat] += 1
        if beat < len(self.cor_beat_res):
            self.cor_beat_res[beat] = ok
        self.cor_last_msg = (f"T{beat + 1} {st['role']} {st['name']}  [OK]" if ok
                             else f"T{beat + 1} {st['role']}  [X] (toca {st['name']})")

    def _key_cor(self, event) -> bool:
        """Teclado de corridos (modal)."""
        if event.key in (pygame.K_ESCAPE, pygame.K_k):
            self.cor_open = False
            self.cor_running = False
        elif event.key == pygame.K_SPACE:
            self._cor_toggle_run()
        elif event.key == pygame.K_n:
            self._cor_load(self.cor_idx + 1)
        elif event.key == pygame.K_q:
            self.cor_fifth = ("up" if self.cor_fifth == "down" else "down")
            self._cor_load(self.cor_idx)
        elif event.key == pygame.K_f:
            self.cor_ornament = not self.cor_ornament
            self._cor_load(self.cor_idx)
        elif event.key == pygame.K_UP:
            self._cor_tempo(+5)
        elif event.key == pygame.K_DOWN:
            self._cor_tempo(-5)
        return True
