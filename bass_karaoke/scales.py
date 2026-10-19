"""
Escalas por cajas — tónica móvil con geometría de posición (lógica pura).

Cada escala sube sus grados y baja (sin repetir la cima): p. ej. la
mayor son 8 + 7 = 15 pasos. Las posiciones se eligen codiciosas dentro
de la ventana de una posición ([F-1, F+4]), prefiriendo no saltar de
cuerda: el resultado es la "caja" clásica, desplazable por el mástil.
La validación es por clase de tono (vale cualquier octava).
"""
from .music import (
    MAX_FRET,
    OPEN_MIDI,
    midi_name,
    midi_of,
    midi_to_hz,
    pc_match,
)

SCALES = {
    1: {"title": "Mayor",             "iv": [0, 2, 4, 5, 7, 9, 11, 12]},
    2: {"title": "Menor natural",     "iv": [0, 2, 3, 5, 7, 8, 10, 12]},
    3: {"title": "Pentatónica menor", "iv": [0, 3, 5, 7, 10, 12]},
}
ROOT_STRING = 3  # cuerda A


def _box_pos(target_midi: int, ref, lo: int, hi: int):
    """Mejor (cuerda, traste) para target_midi cerca de ref=(s,f).

    Prefiere la ventana de posición [lo, hi]; si el tono no existe ahí,
    cae a la posición más cercana en cualquier cuerda.
    """
    ref_s, ref_f = ref
    best, fallback = None, None
    for s in (1, 2, 3, 4):
        f = target_midi - OPEN_MIDI[s]
        if not (0 <= f <= MAX_FRET):
            continue
        cost = abs(f - ref_f) + (0 if s == ref_s else 3)
        if fallback is None or cost < fallback[0]:
            fallback = (cost, (s, f))
        if lo <= f <= hi and (best is None or cost < best[0]):
            best = (cost, (s, f))
    return (best or fallback)[1]


def build_scale(sid: int, root_fret: int) -> list:
    """Pasos de la escala (subida + bajada) con tónica en (A, root_fret)."""
    sc = SCALES.get(sid, SCALES[1])
    f = max(0, min(12, int(root_fret)))
    root_midi = midi_of(ROOT_STRING, f)
    lo, hi = f - 1, f + 4

    up = [{"degree": i + 1, "pos": None, "midi": root_midi + iv}
          for i, iv in enumerate(sc["iv"])]
    ref = (ROOT_STRING, f)
    for st in up:
        st["pos"] = _box_pos(st["midi"], ref, lo, hi)
        ref = st["pos"]
    down = [{"degree": st["degree"], "pos": st["pos"], "midi": st["midi"]}
            for st in reversed(up[:-1])]

    steps = []
    for st in up + down:
        s, ff = st["pos"]
        steps.append({"degree": st["degree"], "string": s, "fret": ff,
                      "finger": max(1, min(4, (ff - f) + 1)),
                      "midi": midi_of(s, ff)})
    for st in steps:
        st["hz"] = midi_to_hz(st["midi"])
        st["name"] = midi_name(st["midi"])
    return steps


def step_matches(hz: float, step: dict) -> bool:
    return pc_match(hz, step["midi"])
