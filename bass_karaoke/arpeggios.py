"""
Arpegios — tríadas/cuatríadas con tónica móvil (lógica pura).

Cualidades: maj7 (R-3-5-7), min7 (R-b3-5-b7), dom7 (R-3-5-b7).
Cada ejercicio sube y baja: R–3–5–7–5–3–R (7 pasos).
La tónica se mueve por la cuerda A; la geometría es relativa
(ver music.tone_pos), así el molde se desplaza intacto.
La validación es por clase de tono (vale cualquier octava).
"""
from .music import (
    midi_name,
    midi_of,
    midi_to_hz,
    pc_match,
    tone_pos,
)

QUALITIES = {
    1: {"id": "maj7", "title": "maj7", "iv": [0, 4, 7, 11], "anchor": 2},
    2: {"id": "min7", "title": "min7", "iv": [0, 3, 7, 10], "anchor": 1},
    3: {"id": "dom7", "title": "7",    "iv": [0, 4, 7, 10], "anchor": 2},
}
DEGREES = ["R", "3ª", "5ª", "7ª", "5ª", "3ª", "R"]
ROOT_STRING = 3  # cuerda A


def build_arpeggio(qid: int, root_fret: int) -> list:
    """Pasos del arpegio con tónica en (cuerda A, root_fret)."""
    q = QUALITIES.get(qid, QUALITIES[1])
    f = max(0, min(12, int(root_fret)))
    anchor = q["anchor"]
    up = []
    for iv, deg in zip(q["iv"], DEGREES[:4], strict=False):
        # La tónica se queda donde la puso el usuario; el resto usa el molde
        s, ff = (ROOT_STRING, f) if iv == 0 else tone_pos(ROOT_STRING, f, iv)
        up.append({"role": deg, "string": s, "fret": ff,
                   "finger": max(1, min(4, anchor + (ff - f))),
                   "midi": midi_of(s, ff)})
    # Bajada: 5ª, 3ª, R (reutiliza posiciones de subida)
    down = [{"role": deg, **up[i]}
            for deg, i in (("5ª", 2), ("3ª", 1), ("R", 0))]
    steps = up + down
    for st in steps:
        st["hz"] = midi_to_hz(st["midi"])
        st["name"] = midi_name(st["midi"])
    return steps


def step_matches(hz: float, step: dict) -> bool:
    return pc_match(hz, step["midi"])
