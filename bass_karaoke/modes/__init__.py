"""Modos de entrenamiento de Bass Karaoke, como mixins de ``BassKaraoke``.

Cada mixin agrupa el estado y las acciones de un modo (tecla E/G/K/O/X/A/V)
en su propio módulo. Siguen operando sobre ``self`` (el host), pero dejan de
vivir amontonados en ``app.py``: la app solo elige qué modo está activo y
delega. Las reglas musicales puras siguen en ``training``, ``walking``,
``corridos``, ``technique``, ``arpeggios`` y ``scales``.
"""
from .corridos_mode import CorridosModeMixin
from .ear_mode import EarModeMixin
from .manager import ModeManagerMixin
from .sequences import SequencesModeMixin
from .training_mode import TrainingModeMixin
from .walking_lab import WalkingLabMixin

__all__ = [
    "CorridosModeMixin",
    "EarModeMixin",
    "ModeManagerMixin",
    "SequencesModeMixin",
    "TrainingModeMixin",
    "WalkingLabMixin",
]
