"""
Núcleo portable de teoría musical (sin pygame, sin numpy, solo math).

Es el único sitio donde vive conocimiento musical: notas, cuerdas,
conversiones y búsqueda de posiciones. Todo lo demás (walking.py,
training.py, technique.py, arpeggios.py, scales.py) construye sobre esto.
Para portar a C++/Dart, este fichero se traduce casi línea por línea.
"""
import math

# MIDI de las cuerdas al aire del bajo 4 cuerdas (E1=28 … G2=43)
OPEN_MIDI = {4: 28, 3: 33, 2: 38, 1: 43}
STRING_NAMES = {4: "E", 3: "A", 2: "D", 1: "G"}
NAMES = ["C", "C#", "D", "D#", "E", "F",
         "F#", "G", "G#", "A", "A#", "B"]
NOTE_PC = {name: i for i, name in enumerate(NAMES)}
MAX_FRET = 15


def midi_to_hz(midi: int) -> float:
    return 440.0 * (2 ** ((int(midi) - 69) / 12.0))


def midi_name(midi: int) -> str:
    midi = int(midi)
    return f"{NAMES[midi % 12]}{(midi // 12) - 1}"


def midi_of(string: int, fret: int) -> int:
    return OPEN_MIDI[string] + int(fret)


def pc_of_hz(hz: float) -> int | None:
    """Clase de tono (0-11) de una frecuencia, o None si no hay señal."""
    if hz is None or hz <= 0:
        return None
    return int(round(12 * math.log2(hz / 440.0) + 69)) % 12


def pc_match(hz: float, midi: int) -> bool:
    """¿La frecuencia es esa clase de tono (cualquier octava)?"""
    pc = pc_of_hz(hz)
    return pc is not None and pc == (int(midi) % 12)


def exact_match(hz: float, midi: int, tol: float = 0.4) -> bool:
    """¿La frecuencia es ese MIDI (misma octava), con tolerancia en semitonos?"""
    if hz is None or hz <= 0:
        return False
    det = 12 * math.log2(hz / 440.0) + 69
    return abs(det - int(midi)) < tol


def tone_pos(string: int, fret: int, interval: int,
             max_fret: int = MAX_FRET):
    """Posición (cuerda, traste) para un intervalo sobre una raíz.

    Orden: cuerda adyacente aguda (molde estándar de bajo) → misma
    cuerda → cuerda adyacente grave → cualquier posición con ese tono.
    """
    target = midi_of(string, fret) + interval
    for s, f in ((string - 1, fret + interval - 5),
                 (string, fret + interval),
                 (string + 1, fret + interval + 5)):
        if 1 <= s <= 4 and 0 <= f <= max_fret and midi_of(s, f) == target:
            return (s, f)
    for s in (string - 1, string, string + 1, 4, 3, 2, 1):
        if 1 <= s <= 4:
            f = target - OPEN_MIDI[s]
            if 0 <= f <= max_fret:
                return (s, f)
    return (string, fret)  # último recurso (no debería pasar)
