"""
Técnica y dedos — secuencias de posiciones puras (sin pygame).

Patrones:
  1 "Cromático 1-2-3-4": cuatro trastes seguidos en cada cuerda,
     de grave a aguda (16 pasos). Un dedo por traste.
  2 "Cruce de cuerdas": mismo traste cruzando las 4 cuerdas ida y
     vuelta, alternando dedos 1-2 (16 pasos).

Cada paso es {string, fret, finger, midi, hz, name, label}.
La validación usa altura exacta (misma octava): aquí importa la
posición, no solo la clase de tono.
"""
from .music import (
    OPEN_MIDI, MAX_FRET, STRING_NAMES,
    midi_to_hz, midi_name, midi_of, exact_match,
)

PATTERNS = {
    1: {"title": "Cromático 1-2-3-4"},
    2: {"title": "Cruce de cuerdas"},
}


def _step(string: int, fret: int, finger: int, label: str = "") -> dict:
    midi = midi_of(string, fret)
    return {"string": string, "fret": fret, "finger": finger,
            "midi": midi, "hz": midi_to_hz(midi),
            "name": midi_name(midi), "label": label}


def build_pattern(pid: int, start_fret: int = 5) -> list:
    """Construye los pasos del patrón anclado en start_fret."""
    if pid == 2:
        f = max(0, min(MAX_FRET, int(start_fret)))
        strings = [4, 3, 2, 1, 1, 2, 3, 4] * 2
        return [_step(s, f, 1 + (i % 2),
                      f"cuerda {STRING_NAMES[s]} · dedo {1 + (i % 2)}")
                for i, s in enumerate(strings)]
    # Patrón 1 por defecto: necesita 4 trastes (F..F+3)
    f = max(0, min(MAX_FRET - 3, int(start_fret)))
    steps = []
    for s in (4, 3, 2, 1):
        for k in range(4):
            steps.append(_step(s, f + k, k + 1,
                               f"traste {f + k} · dedo {k + 1}"))
    return steps


def step_matches(hz: float, step: dict) -> bool:
    """¿La frecuencia es exactamente ese paso (misma octava)?"""
    return exact_match(hz, step["midi"], tol=0.45)
