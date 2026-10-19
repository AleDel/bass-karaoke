"""Secuencias paso a paso — técnica (X), arpegios (A), escalas (V)."""
import pygame

from .. import arpeggios as arp_logic
from .. import scales as scale_logic
from .. import technique as tech_logic
from ..config import MIN_HZ

_BUILDERS = {
    "tx": lambda self: tech_logic.build_pattern(self.tx_sel, self.tx_pos),
    "ar": lambda self: arp_logic.build_arpeggio(self.ar_sel, self.ar_pos),
    "sc": lambda self: scale_logic.build_scale(self.sc_sel, self.sc_pos),
}

_MATCHERS = {
    "tx": tech_logic.step_matches,
    "ar": arp_logic.step_matches,
    "sc": scale_logic.step_matches,
}

# Opciones de variante válidas por modo (teclas 1..3).
_SELECTIONS = {"tx": (1, 2), "ar": (1, 2, 3), "sc": (1, 2, 3)}

# Tecla que abre/cierra cada modo.
_TOGGLES = {"tx": pygame.K_x, "ar": pygame.K_a, "sc": pygame.K_v}


class SequencesModeMixin:
    """Estado y acciones de las secuencias de técnica/arpegios/escalas."""

    def _init_sequences_state(self):
        self.tx_open = False
        self.tx_sel = 1      # 1 cromático · 2 cruce
        self.tx_pos = 5      # traste de inicio
        self.ar_open = False
        self.ar_sel = 2      # 1 maj7 · 2 min7 · 3 dom7
        self.ar_pos = 5      # traste de la tónica (cuerda A)
        self.sc_open = False
        self.sc_sel = 1      # 1 mayor · 2 menor · 3 pentatónica
        self.sc_pos = 3      # traste de la tónica (cuerda A)
        for p in ("tx", "ar", "sc"):
            setattr(self, f"{p}_steps", [])
            setattr(self, f"{p}_step", 0)
            setattr(self, f"{p}_hold", 0.0)
            setattr(self, f"{p}_ok", 0)
            setattr(self, f"{p}_total", 0)
            setattr(self, f"{p}_loops", 0)
            setattr(self, f"{p}_msg", "")
        self.seq_pos = None   # (fret, string)
        self.seq_midi = None
        self.seq_label = ""

    def _seq_show(self, p: str):
        """Publica el paso actual como objetivo visible en el mástil."""
        steps = getattr(self, f"{p}_steps")
        i = getattr(self, f"{p}_step", 0) % max(1, len(steps))
        st = steps[i]
        self.seq_pos = (st["fret"], st["string"])
        self.seq_midi = st["midi"]
        self.seq_label = f"{i + 1}/{len(steps)}"

    def _seq_rebuild(self, p: str):
        setattr(self, f"{p}_steps", _BUILDERS[p](self))
        setattr(self, f"{p}_step", 0)
        setattr(self, f"{p}_hold", 0.0)
        setattr(self, f"{p}_msg", "")
        self._seq_show(p)

    def _seq_open(self, p: str):
        self._close_modes()
        setattr(self, f"{p}_open", True)
        if not getattr(self, f"{p}_steps"):
            self._seq_rebuild(p)
        else:
            self._seq_show(p)

    def _seq_advance(self, p: str):
        """Puntúa el paso actual y avanza (al final, vuelta completa)."""
        steps = getattr(self, f"{p}_steps")
        i = getattr(self, f"{p}_step", 0)
        setattr(self, f"{p}_ok", getattr(self, f"{p}_ok") + 1)
        setattr(self, f"{p}_total", getattr(self, f"{p}_total") + 1)
        setattr(self, f"{p}_hold", 0.0)
        if i + 1 >= len(steps):
            setattr(self, f"{p}_step", 0)
            setattr(self, f"{p}_loops", getattr(self, f"{p}_loops") + 1)
            setattr(self, f"{p}_msg", "¡Vuelta completa!")
        else:
            setattr(self, f"{p}_step", i + 1)
            setattr(self, f"{p}_msg", "")
        self._seq_show(p)

    def _seq_listen(self, p: str, hz: float, dt: float):
        steps = getattr(self, f"{p}_steps")
        if not steps:
            return
        st = steps[getattr(self, f"{p}_step", 0) % len(steps)]
        if hz > MIN_HZ and _MATCHERS[p](hz, st):
            hold = getattr(self, f"{p}_hold") + dt
            setattr(self, f"{p}_hold", hold)
            if hold >= self.tr_hold_need:
                self._seq_advance(p)
        else:
            setattr(self, f"{p}_hold",
                    max(0.0, getattr(self, f"{p}_hold") - dt * 2.0))

    def _key_seq(self, p: str, event) -> bool:
        """Teclado de una secuencia (modal)."""
        if event.key in (pygame.K_ESCAPE, _TOGGLES[p]):
            self._close_modes()
        elif event.key == pygame.K_n:
            setattr(self, f"{p}_step", 0)
            setattr(self, f"{p}_hold", 0.0)
            setattr(self, f"{p}_msg", "")
            self._seq_show(p)
        elif event.key in (pygame.K_1, pygame.K_2, pygame.K_3):
            sel = {pygame.K_1: 1, pygame.K_2: 2, pygame.K_3: 3}[event.key]
            if sel in _SELECTIONS[p]:
                setattr(self, f"{p}_sel", sel)
                self._seq_rebuild(p)
        elif event.key == pygame.K_UP:
            setattr(self, f"{p}_pos", min(12, getattr(self, f"{p}_pos") + 1))
            self._seq_rebuild(p)
        elif event.key == pygame.K_DOWN:
            setattr(self, f"{p}_pos", max(0, getattr(self, f"{p}_pos") - 1))
            self._seq_rebuild(p)
        return True
