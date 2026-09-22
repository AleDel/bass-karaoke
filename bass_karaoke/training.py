"""
Entrenador de notas — lógica pura (sin pygame).

Todo lo que decide el juego (niveles, objetivo, aciertos) vive aquí para
poder reutilizarlo en otros frontends (C++, Flutter...). La app solo pone
la UI (overlay), el micro y el sonido.
"""
import random

from .music import NOTE_PC

LEVELS = {
    1: {"title": "Cuerdas al aire", "notes": ["E", "A", "D", "G"]},
    2: {"title": "Naturales",      "notes": ["C", "D", "E", "F", "G", "A", "B"]},
    3: {"title": "Cromático",      "notes": ["C", "C#", "D", "D#", "E", "F",
                                             "F#", "G", "G#", "A", "A#", "B"]},
}

# MIDI de referencia (4ª octava) para cada nombre; la validación es
# invariante de octava, así que vale cualquier altura.
REF_OCTAVE = 60  # C4


def target_midi(name: str) -> int:
    return REF_OCTAVE + NOTE_PC[name]


def pick_target(level: int, exclude: str | None = None,
                rng: random.Random | None = None) -> str:
    """Nota objetivo del nivel, evitando repetir la anterior."""
    rng = rng or random
    pool = LEVELS.get(level, LEVELS[1])["notes"]
    choices = [n for n in pool if n != exclude] or pool
    return rng.choice(choices)


def accuracy(ok: int, total: int) -> int:
    return int(100 * ok / total) if total > 0 else 0
