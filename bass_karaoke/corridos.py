"""
Bajeo de corridos tumbados en 3/4 — lógica pura (sin pygame).

A diferencia del walking de jazz (negras constantes en 4/4), aquí cada
compás suena UN solo golpe en el tiempo 1 y el resto es silencio
(ahí golpean las guitarras):
  compás de raíz:  T1 = Raíz,  T2-T3 = silencio
  compás de quinta: T1 = 5ª,   T2 = silencio, T3 = adorno (opcional)

La quinta tiene dos moldes geométricos (misma geometría al transportar):
  - "abajo": mismo traste, una cuerda hacia el E (5ª por debajo, -5 st)
  - "arriba": una cuerda hacia el G y dos trastes adelante (+7 st)
El adorno de T3 es una aproximación cromática (±1 st) a la raíz del
compás siguiente, como el T4 del walking pero en tiempo de vals.
"""
import math

# MIDI de las cuerdas al aire (E1=28, A1=33, D2=38, G2=43)
OPEN_MIDI = {4: 28, 3: 33, 2: 38, 1: 43}
NAMES = ["C", "C#", "D", "D#", "E", "F",
         "F#", "G", "G#", "A", "A#", "B"]
MAX_FRET = 15


def midi_to_hz(midi: int) -> float:
    return 440.0 * (2 ** ((int(midi) - 69) / 12.0))


def midi_name(midi: int) -> str:
    midi = int(midi)
    return f"{NAMES[midi % 12]}{(midi // 12) - 1}"


def midi_of(string: int, fret: int) -> int:
    return OPEN_MIDI[string] + int(fret)


def fifth_shapes(string: int, fret: int):
    """Moldes de quinta para una raíz en (cuerda, traste).

    Devuelve {"down": (cuerda, traste) | None, "up": ... | None}:
      down = mismo traste, una cuerda hacia el E (5ª por debajo)
      up   = una cuerda hacia el G y dos trastes adelante (5ª por arriba)
    """
    down = (string + 1, fret) if string < 4 else None
    up = (string - 1, fret + 2) if string > 1 and fret + 2 <= MAX_FRET else None
    return {"down": down, "up": up}


def _approach_pos(next_root_midi: int, ref):
    """Tono a ±1 semitono de la raíz siguiente, cercano a la mano (ref).

    Devuelve ((cuerda, traste), midi). Prefiere el semitono inferior.
    """
    ref_s, ref_f = ref
    best = None
    for m in (next_root_midi - 1, next_root_midi + 1):
        for s in (1, 2, 3, 4):
            f = m - OPEN_MIDI[s]
            if 0 <= f <= MAX_FRET:
                cost = abs(f - ref_f) + (0 if s == ref_s else 3)
                if best is None or cost < best[0]:
                    best = (cost, (s, f), m)
    return best[1], best[2]


def _silence():
    return {"role": "Silencio", "string": None, "fret": None,
            "finger": None, "midi": None, "hz": None, "name": "—"}


def build_bajeo(string: int, fret: int, next_root_midi: int,
                fifth: str = "down", ornament: bool = True):
    """Construye los 2 compases × 3 tiempos del bajeo para un acorde.

    Devuelve [bar_raiz, bar_quinta], cada uno con 3 dicts
    {role, string, fret, finger, midi, hz, name} (None en silencios).
    """
    root_midi = midi_of(string, fret)
    shapes = fifth_shapes(string, fret)
    fpos = shapes.get(fifth) or shapes["down"] or shapes["up"]
    fs, ff = fpos
    fifth_midi = midi_of(fs, ff)

    (sa, fa), appr_midi = _approach_pos(next_root_midi, (fs, ff))

    def _finger(f, anchor=2):
        return max(1, min(4, anchor + (f - fret)))

    def _sounding(role, s, f, midi, finger):
        return {"role": role, "string": s, "fret": f, "finger": finger,
                "midi": midi, "hz": midi_to_hz(midi),
                "name": midi_name(midi)}

    bar_root = [_sounding("Raíz", string, fret, root_midi, 2),
                _silence(), _silence()]
    adorn = (_sounding("Adorno", sa, fa, appr_midi, _finger(fa, 3))
             if ornament else _silence())
    bar_fifth = [_sounding("5ª", fs, ff, fifth_midi, _finger(ff)),
                 _silence(), adorn]
    return [bar_root, bar_fifth]


def bajeo_matches(hz: float, step, next_root_midi: int):
    """¿Lo tocado cumple el paso? Invariante de octava.

    Devuelve None si es silencio (no se puntúa), True/False si suena:
    Raíz/5ª por clase de tono; Adorno a un semitono de la raíz siguiente.
    """
    if step.get("midi") is None:
        return None
    if hz is None or hz <= 0:
        return False
    pc_det = int(round(12 * math.log2(hz / 440.0) + 69)) % 12
    if step["role"] == "Adorno":
        return (pc_det - int(next_root_midi)) % 12 in (1, 11)
    return pc_det == (step["midi"] % 12)


CORRIDO_EXERCISES = [
    {"title": "C – G",
     "bars": [{"name": "C", "string": 3, "fret": 3},
              {"name": "G", "string": 4, "fret": 3}]},
    {"title": "G – D",
     "bars": [{"name": "G", "string": 4, "fret": 3},
              {"name": "D", "string": 3, "fret": 5}]},
    {"title": "A – E",
     "bars": [{"name": "A", "string": 4, "fret": 5},
              {"name": "E", "string": 4, "fret": 0}]},
]


def build_corrido(ex, fifth: str = "down", ornament: bool = True):
    """Acordes → bajeos. Cada acorde ocupa 2 compases (raíz + quinta del
    MISMO acorde); el adorno del compás de quinta apunta a la raíz del
    acorde siguiente (en bucle, como el T4 del walking).
    Devuelve (steps, chord_roots): steps son 2 compases por acorde."""
    bars = ex["bars"]
    n = len(bars)
    chord_roots = [midi_of(b["string"], b["fret"]) for b in bars]
    steps = []
    for i, b in enumerate(bars):
        steps.extend(build_bajeo(b["string"], b["fret"],
                                 chord_roots[(i + 1) % n],
                                 fifth=fifth, ornament=ornament))
    return steps, chord_roots
