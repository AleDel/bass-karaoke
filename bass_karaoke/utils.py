"""
Funciones de utilidad: conversión Hz↔nota, cálculo de trastes, comparación de notas.
"""
import math

import numpy as np

from .config import MAX_HZ, MIN_HZ, STRING_OPEN_HZ


def fret_to_hz(fret: int, string: int) -> float:
    """Frecuencia en Hz para un traste y cuerda dados."""
    return STRING_OPEN_HZ[string] * (2 ** (fret / 12.0))


def hz_to_midi(hz: float) -> float:
    """Número de nota MIDI (con decimales) para una frecuencia en Hz."""
    return 12 * math.log2(hz / 440.0) + 69


def midi_to_hz(midi: float) -> float:
    """Frecuencia en Hz para un número de nota MIDI (con decimales)."""
    return 440.0 * 2 ** ((midi - 69.0) / 12.0)


def hz_to_note_name(hz: float) -> str:
    """Nombre de nota (p.ej. 'E2') para una frecuencia en Hz."""
    if hz < 10:
        return "—"
    midi  = int(np.round(hz_to_midi(hz)))
    names = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
    return f"{names[midi % 12]}{(midi // 12) - 1}"


def notes_match(detected_hz: float, expected_hz: float) -> bool:
    """Compara por pitch class (octava invariante), tolerancia ±50 cents."""
    if detected_hz < MIN_HZ or detected_hz > MAX_HZ or expected_hz <= 0:
        return False
    midi_det = hz_to_midi(detected_hz)
    midi_exp = hz_to_midi(expected_hz)
    if int(round(midi_det)) % 12 == int(round(midi_exp)) % 12:
        return True
    diff_mod = abs(midi_det - midi_exp) % 12
    cents    = min(diff_mod, 12 - diff_mod) * 100
    return cents < 50
