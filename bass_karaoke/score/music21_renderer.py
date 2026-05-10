"""
Renderizador de partitura usando music21 (con MuseScore o dibujo manual con pygame).
"""
import os
import pygame

from ..config import MUSICXML_PATH, SCORE_H, W

MUSIC21_OK = False
try:
    import music21 as _music21_mod
    MUSIC21_OK = True
except ImportError:
    print("[WARN] music21 no encontrado — pip install music21")

# Mapeo step → diatónico relativo (C=0, D=1, ..., B=6)
_STEP_DIA7 = {'C': 0, 'D': 1, 'E': 2, 'F': 3, 'G': 4, 'A': 5, 'B': 6}


def init_score_surface_music21(notes: list):
    """
    Renderiza el MusicXML con music21.
    Obtiene la clave y compás de music21, luego dibuja la tira con
    las notas de la app (garantiza alineación perfecta con note_xs).

    Devuelve (surface, note_xs).
    """
    if not MUSIC21_OK or not notes:
        return None, []

    try:
        import music21 as m21

        score = m21.converter.parse(MUSICXML_PATH)

        target_part = None
        for part in score.parts:
            clefs_in = list(part.flatten().getElementsByClass('Clef'))
            if not any(isinstance(c, m21.clef.TabClef) for c in clefs_in):
                target_part = part
                break
        if target_part is None:
            target_part = score.parts[0] if score.parts else score

        first_clef = next(target_part.flatten().getElementsByClass('Clef'), None)
        if first_clef is not None:
            sign          = getattr(first_clef, 'sign', 'F') or 'F'
            octave_change = int(getattr(first_clef, 'octaveChange', 0) or 0)
        else:
            sign          = 'F'
            octave_change = -1

        bottom_diatonic = 19 if sign == 'F' else 31
        diatonic_offset = int(-octave_change * 7)

        time_sigs = list(target_part.flatten().getElementsByClass('TimeSignature'))
        bar_ql = float(time_sigs[0].barDuration.quarterLength) if time_sigs else 4.0

        # Dibujar con app.notes → alineación perfecta con note_xs
        surf, note_xs = _draw_score_m21_strip(
            notes, bar_ql, bottom_diatonic, diatonic_offset)

        print(f"[Music21] {surf.get_width()}×{surf.get_height()}px  "
              f"notas={len(notes)}  render=manual")
        return surf, note_xs

    except Exception as _e:
        print(f"[Music21 ERROR] {_e}")
        import traceback
        traceback.print_exc()
        return None, []


def _draw_score_m21_strip(notes, bar_ql, bottom_diatonic, diatonic_offset):
    """
    Dibuja una tira de pentagrama con pygame puro usando app.notes.
    Devuelve (surf, note_xs) donde note_xs es [(start16, pixel_x), ...].
    El pixel_x de dibujo y el de note_xs son idénticos → alineación exacta.
    """
    PX_PER_16 = 30           # 30 px por figura de semicorchea
    total16   = (notes[-1]['start16'] + notes[-1]['dur']) if notes else 1
    img_w     = max(W * 4, total16 * PX_PER_16, 3000)
    img_h     = SCORE_H - 4

    surf = pygame.Surface((img_w, img_h))
    surf.fill((0, 0, 0))

    if not notes or total16 <= 0:
        return surf, []

    half_sp  = 8.0
    line_sp  = half_sp * 2
    y_bottom = img_h * 0.72         # línea inferior del pentagrama
    y_lines  = [y_bottom - i * line_sp for i in range(5)]

    # Líneas del pentagrama
    C_STAFF = (65, 65, 85)
    for y_line in y_lines:
        pygame.draw.line(surf, C_STAFF,
                         (0, int(y_line)), (img_w, int(y_line)), 1)

    # Líneas de compás desde measure_num de las notas
    C_BAR = (45, 45, 65)
    seen_m: dict = {}
    for n in notes:
        m = n.get('measure_num', 0)
        if m not in seen_m:
            seen_m[m] = n['start16']
    for s16 in seen_m.values():
        xb = int(s16 * PX_PER_16)
        pygame.draw.line(surf, C_BAR,
                         (xb, int(y_lines[0])), (xb, int(y_lines[-1])), 1)

    r_note   = max(3, int(half_sp * 0.85))   # ≈ 6 px
    C_NOTE   = (188, 188, 210)
    C_LEDGER = (95, 95, 115)
    note_xs  = []

    for n in notes:
        x = int(n['start16'] * PX_PER_16)
        note_xs.append((n['start16'], float(x)))

        step   = (n.get('step') or 'C').upper()
        octave = n.get('octave') or 3
        dia    = (octave - 1) * 7 + _STEP_DIA7.get(step, 0) + 1
        steps  = (dia + diatonic_offset) - bottom_diatonic
        y_note = int(y_bottom - steps * half_sp)

        # Líneas adicionales (ledger lines)
        ledger_w = r_note * 3
        if steps < 0:
            s = -2
            while s >= steps:
                pygame.draw.line(surf, C_LEDGER,
                    (x - ledger_w, int(y_bottom - s * half_sp)),
                    (x + ledger_w, int(y_bottom - s * half_sp)), 1)
                s -= 2
        elif steps > 8:
            s = 10
            while s <= steps:
                pygame.draw.line(surf, C_LEDGER,
                    (x - ledger_w, int(y_bottom - s * half_sp)),
                    (x + ledger_w, int(y_bottom - s * half_sp)), 1)
                s += 2

        dur_ql = n.get('dur', 4) / 4.0     # convertir 16th → quarter
        rx, ry = r_note, max(2, int(r_note * 0.68))
        rect   = (x - rx, y_note - ry, rx * 2, ry * 2)
        if dur_ql >= 2.0:
            pygame.draw.ellipse(surf, C_NOTE, rect, 1)   # blanca
        else:
            pygame.draw.ellipse(surf, C_NOTE, rect)       # negra

        if dur_ql < 4.0:                                  # plica
            stem_up  = steps < 4
            stem_x   = x + rx if stem_up else x - rx
            stem_end = (y_note - int(line_sp * 3) if stem_up
                        else y_note + int(line_sp * 3))
            pygame.draw.line(surf, C_NOTE,
                             (stem_x, y_note), (stem_x, stem_end), 1)

    return surf, note_xs

