"""Gestión transversal de los modos: solo uno activo a la vez."""


class ModeManagerMixin:
    """Cierra el modo activo antes de abrir otro."""

    def _close_modes(self):
        """Cierra todos los modos de entrenamiento (solo uno a la vez)."""
        self.training_open = False
        self.tr_hint = False
        self.lab_open = False
        self.lab_running = False
        self.cor_open = False
        self.cor_running = False
        self.ear_open = False
        self.tx_open = self.ar_open = self.sc_open = False
        self.seq_pos, self.seq_midi, self.seq_label = None, None, ""
