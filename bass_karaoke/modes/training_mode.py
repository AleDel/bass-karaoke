"""Entrenador de notas del mástil (tecla E)."""
import pygame

from .. import training as training_logic


class TrainingModeMixin:
    """Estado y acciones del entrenador de notas."""

    def _init_training_state(self):
        self.training_open = False
        self.tr_level = 1
        self.tr_target_name = "—"
        self.tr_target_midi = None
        self.tr_target_hz = 0.0
        self.tr_hold = 0.0
        self.tr_hold_need = 0.6
        self.tr_ok = 0
        self.tr_total = 0
        self.tr_msg = ""
        self.tr_hint = False

    def _training_open(self):
        """Abre el entrenador; elige objetivo si aún no hay uno."""
        self.training_open = True
        self.tr_hold = 0.0
        if self.tr_target_midi is None:
            self._training_pick()

    def _training_pick(self):
        """Elige una nota objetivo del nivel actual (evita repetir la anterior)."""
        name = training_logic.pick_target(self.tr_level,
                                          exclude=self.tr_target_name)
        self.tr_target_name = name
        self.tr_target_midi = training_logic.target_midi(name)
        self.tr_target_hz = self._midi_to_hz(self.tr_target_midi)
        self.tr_hold = 0.0

    def _training_set_level(self, lvl: int):
        if lvl in training_logic.LEVELS and lvl != self.tr_level:
            self.tr_level = lvl
            self.tr_msg = ""
            self._training_pick()

    def _training_next(self, skipped: bool = True):
        """Pasa a otra nota; si se salta, cuenta como ronda no acertada."""
        if skipped and self.tr_target_midi is not None:
            self.tr_total += 1
            self.tr_msg = f"Saltada: era {self.tr_target_name}"
        self._training_pick()

    def _training_success(self):
        self.tr_ok += 1
        self.tr_total += 1
        self.tr_msg = f"¡Bien! {self.tr_target_name} correcto"
        self._training_pick()

    def _key_training(self, event) -> bool:
        """Teclado del entrenador (modal)."""
        if event.key in (pygame.K_ESCAPE, pygame.K_e):
            self.training_open = False
            self.tr_hint = False
        elif event.key in (pygame.K_n, pygame.K_SPACE):
            self._training_next(skipped=True)
        elif event.key == pygame.K_h:
            self.tr_hint = not self.tr_hint
        elif event.key == pygame.K_1:
            self._training_set_level(1)
        elif event.key == pygame.K_2:
            self._training_set_level(2)
        elif event.key == pygame.K_3:
            self._training_set_level(3)
        return True
