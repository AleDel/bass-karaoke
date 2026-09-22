"""
Walking Lab — lógica pura (sin pygame) para construir moldes de walking bass.

Regla por compás (4/4 en negras):
  T1 raíz · T2 3ª · T3 5ª · T4 aproximación cromática (±1 semitono
  de la raíz del compás siguiente).

La geometría es relativa: 3ª y 5ª se buscan en la cuerda adyacente
aguda (5 semitonos más alta), así el molde se desplaza intacto por
el mástil al cambiar de tonalidad. Los dedos son sugeridos, con el
índice/medio anclados en la raíz según la cualidad.
"""
import math

# MIDI de las cuerdas al aire (E1=28, A1=33, D2=38, G2=43)
OPEN_MIDI = {4: 28, 3: 33, 2: 38, 1: 43}
STRING_NAMES = {4: "E", 3: "A", 2: "D", 1: "G"}
NAMES = ["C", "C#", "D", "D#", "E", "F",
         "F#", "G", "G#", "A", "A#", "B"]
MAX_FRET = 15

# Semitonos de la 3ª según la cualidad del acorde
THIRDS = {"maj": 4, "6": 4, "dom": 4, "7": 4, "min": 3, "m7": 3, "m": 3}

# Dedo ancla sobre la raíz (sugerido)
ROOT_FINGER = {"maj": 2, "6": 2, "dom": 2, "7": 2, "min": 1, "m7": 1, "m": 1}


def midi_to_hz(midi: int) -> float:
    return 440.0 * (2 ** ((int(midi) - 69) / 12.0))


def midi_name(midi: int) -> str:
    midi = int(midi)
    return f"{NAMES[midi % 12]}{(midi // 12) - 1}"


def midi_of(string: int, fret: int) -> int:
    return OPEN_MIDI[string] + int(fret)


def _in_range(string: int, fret: int) -> bool:
    return 1 <= string <= 4 and 0 <= fret <= MAX_FRET


def _chord_tone_pos(string: int, fret: int, interval: int):
    """Posición (cuerda, traste) para un intervalo sobre la raíz.

    Orden: cuerda adyacente aguda (molde estándar) → misma cuerda →
    cuerda adyacente grave → cualquier posición con ese tono.
    """
    target = midi_of(string, fret) + interval
    ordered = [(string - 1, fret + interval - 5),
               (string, fret + interval),
               (string + 1, fret + interval + 5)]
    for s, f in ordered:
        if _in_range(s, f) and midi_of(s, f) == target:
            return (s, f)
    for s in (string - 1, string, string + 1, 4, 3, 2, 1):
        if 1 <= s <= 4:
            f = target - OPEN_MIDI[s]
            if 0 <= f <= MAX_FRET:
                return (s, f)
    return (string, fret)  # último recurso (no debería pasar)


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


def build_mold(string: int, fret: int, quality: str, next_root_midi: int):
    """Construye los 4 pasos del molde para un compás.

    Devuelve lista de dicts {role, string, fret, finger, midi, hz, name}.
    """
    quality = quality if quality in THIRDS else "maj"
    root_midi = midi_of(string, fret)
    s3, f3 = _chord_tone_pos(string, fret, THIRDS[quality])
    s5, f5 = _chord_tone_pos(string, fret, 7)
    (sa, fa), appr_midi = _approach_pos(next_root_midi, (s5, f5))

    anchor = ROOT_FINGER[quality]

    def _finger(f):
        return max(1, min(4, anchor + (f - fret)))

    steps = [
        {"role": "Raíz",  "string": string, "fret": fret,
         "finger": anchor,    "midi": root_midi},
        {"role": "3ª",    "string": s3,     "fret": f3,
         "finger": _finger(f3), "midi": midi_of(s3, f3)},
        {"role": "5ª",    "string": s5,     "fret": f5,
         "finger": _finger(f5), "midi": midi_of(s5, f5)},
        {"role": "Aprox.", "string": sa,    "fret": fa,
         "finger": _finger(fa), "midi": appr_midi},
    ]
    for st in steps:
        st["hz"] = midi_to_hz(st["midi"])
        st["name"] = midi_name(st["midi"])
    return steps


def beat_matches(hz: float, bar_steps, beat: int, next_root_midi: int) -> bool:
    """¿La frecuencia tocada cumple el rol del tiempo? (invariante de octava).

    T1–T3: misma clase de tono que la esperada. T4: a un semitono
    (clase de tono vecina) de la raíz del compás siguiente.
    """
    if hz <= 0:
        return False
    pc_det = int(round(12 * math.log2(hz / 440.0) + 69)) % 12
    if beat < 3:
        return pc_det == (bar_steps[beat]["midi"] % 12)
    pc_next = int(next_root_midi) % 12
    return (pc_det - pc_next) % 12 in (1, 11)


EXERCISES = [
    {"title": "C6 → Dm7",
     "bars": [{"name": "C6",  "string": 3, "fret": 3, "quality": "maj"},
              {"name": "Dm7", "string": 3, "fret": 5, "quality": "min"}]},
    {"title": "ii–V–I en C",
     "bars": [{"name": "Dm7",   "string": 3, "fret": 5, "quality": "min"},
              {"name": "G7",    "string": 4, "fret": 3, "quality": "dom"},
              {"name": "Cmaj7", "string": 3, "fret": 3, "quality": "maj"}]},
]


def build_exercise(ex):
    """Compases → moldes. Cada T4 apunta a la raíz del compás siguiente."""
    bars = ex["bars"]
    roots = [midi_of(b["string"], b["fret"]) for b in bars]
    return [build_mold(b["string"], b["fret"], b["quality"],
                       roots[(i + 1) % len(bars)])
            for i, b in enumerate(bars)]
