"""Oído call-response — escucha y repite (tecla O)."""
import logging

import pygame

from .. import training as training_logic

log = logging.getLogger(__name__)


class EarModeMixin:
    """Estado y acciones del entrenamiento de oído."""

    def _init_ear_state(self):
        self.ear_open = False
        self.ear_level = 1
        self.ear_name = "—"
        self.ear_midi = None
        self.ear_hz = 0.0
        self.ear_hold = 0.0
        self.ear_revealed = False
        self.ear_wait = 0.0
        self.ear_ok = 0
        self.ear_total = 0
        self.ear_msg = ""
        self._ear_sound = None

    def _ear_open(self):
        """Abre el modo oído; suena el objetivo (oculto) al entrar."""
        self.ear_open = True
        self.ear_hold = 0.0
        if self.ear_midi is None:
            self._ear_pick()
        else:
            self._ear_play()

    def _ear_pick(self):
        """Nuevo objetivo oculto: lo elige, lo esconde y lo hace sonar."""
        name = training_logic.pick_target(self.ear_level,
                                          exclude=self.ear_name)
        self.ear_name = name
        self.ear_midi = training_logic.target_midi(name)
        self.ear_hz = self._midi_to_hz(self.ear_midi)
        self.ear_hold = 0.0
        self.ear_revealed = False
        self.ear_wait = 0.0
        self.ear_msg = ""
        self._ear_play()

    def _ear_play(self):
        """Repite el sonido del objetivo sin mostrar su nombre."""
        try:
            if self.ear_hz > 0:
                self._ear_sound = self._build_tone(self.ear_hz)
                self._ear_sound.play()
        except Exception as e:
            log.info(f"[Oído] no puedo sonar: {e}")

    def _ear_set_level(self, lvl: int):
        if lvl in training_logic.LEVELS and lvl != self.ear_level:
            self.ear_level = lvl
            self._ear_pick()

    def _ear_resolve(self, success: bool):
        """Revela la respuesta y programa el siguiente objetivo."""
        self.ear_revealed = True
        self.ear_wait = 1.6
        self.ear_total += 1
        if success:
            self.ear_ok += 1
            self.ear_msg = f"¡Bien! Era {self.ear_name}"
        else:
            self.ear_msg = f"Era {self.ear_name}"

    def _key_ear(self, event) -> bool:
        """Teclado del modo oído (modal)."""
        if event.key in (pygame.K_ESCAPE, pygame.K_o):
            self.ear_open = False
        elif event.key == pygame.K_SPACE:
            self._ear_play()
        elif event.key == pygame.K_n:
            self._ear_resolve(False)
        elif event.key == pygame.K_1:
            self._ear_set_level(1)
        elif event.key == pygame.K_2:
            self._ear_set_level(2)
        elif event.key == pygame.K_3:
            self._ear_set_level(3)
        return True
