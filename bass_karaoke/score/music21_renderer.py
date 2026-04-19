"""
Renderizador de partitura usando music21 (con MuseScore o dibujo manual con pygame).
"""
import os
import pygame

from ..config import MUSICXML_PATH, SCORE_H

MUSIC21_OK = False
try:
    import music21 as _music21_mod
    MUSIC21_OK = True
except ImportError:
    print("[WARN] music21 no encontrado — pip install music21")


def init_score_surface_music21(notes: list):
    """
    Renderiza el MusicXML con music21.
    Intenta MuseScore si está instalado; si no, dibuja una tira de
    pentagrama con pygame directamente.

    Devuelve (surface, note_xs).
    """
    if not MUSIC21_OK:
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

        first_clef = None
        for c in target_part.flatten().getElementsByClass('Clef'):
            first_clef = c
            break
        if first_clef is not None:
            sign         = getattr(first_clef, 'sign', 'F') or 'F'
            octave_change = int(getattr(first_clef, 'octaveChange', 0) or 0)
        else:
            sign          = 'F'
            octave_change = -1

        bottom_diatonic = 19 if sign == 'F' else 31
        diatonic_offset = int(-octave_change * 7)

        total_ql = float(target_part.duration.quarterLength)
        time_sigs = list(target_part.flatten().getElementsByClass('TimeSignature'))
        bar_ql = float(time_sigs[0].barDuration.quarterLength) if time_sigs else 4.0

        m21_notes = []
        for elem in target_part.flatten().notesAndRests:
            if isinstance(elem, m21.note.Rest):
                continue
            pitches = (elem.pitches
                       if isinstance(elem, m21.chord.Chord)
                       else [elem.pitch])
            offset_ql = float(elem.offset)
            dur_ql    = float(elem.duration.quarterLength)
            for p in pitches:
                m21_notes.append({
                    'offset_ql':   offset_ql,
                    'duration_ql': dur_ql,
                    'diatonic':    p.diatonicNoteNum,
                })
        m21_notes.sort(key=lambda x: (x['offset_ql'], x['diatonic']))

        # Intentar MuseScore
        rendered_ok = False
        surf = None
        try:
            import tempfile, shutil as _sh, glob as _glob
            tmp_dir  = tempfile.mkdtemp()
            tmp_base = os.path.join(tmp_dir, 'score.png')
            target_part.write('musicxml.png', fp=tmp_base)
            pngs = sorted(_glob.glob(os.path.join(tmp_dir, '*.png')))
            if pngs:
                raw = pygame.image.load(pngs[0]).convert()
                arr = pygame.surfarray.pixels3d(raw)
                ink = (arr[:, :, 0].astype('int32')
                       + arr[:, :, 1] + arr[:, :, 2]) < 400
                arr[ink]  = [188, 188, 210]
                arr[~ink] = [0, 0, 0]
                del arr
                target_h = SCORE_H - 4
                w_new = int(raw.get_width() * target_h / max(raw.get_height(), 1))
                surf = pygame.transform.smoothscale(raw, (max(w_new, 1), target_h))
                rendered_ok = True
            _sh.rmtree(tmp_dir, ignore_errors=True)
        except Exception as ex_ms:
            print(f"[Music21] MuseScore no disponible "
                  f"({type(ex_ms).__name__}: {ex_ms})  →  dibujo manual")

        if not rendered_ok:
            surf = _draw_score_m21_strip(
                m21_notes, total_ql, bar_ql,
                bottom_diatonic, diatonic_offset)

        img_w = surf.get_width()
        if total_ql > 0 and notes:
            note_xs = [
                (n['start16'], n['start16'] / (total_ql * 4.0) * img_w)
                for n in notes
            ]
        else:
            note_xs = []

        rname = 'MuseScore' if rendered_ok else 'manual'
        print(f"[Music21] {surf.get_width()}×{surf.get_height()}px  "
              f"notas={len(m21_notes)}  render={rname}")
        return surf, note_xs

    except Exception as _e:
        print(f"[Music21 ERROR] {_e}")
        import traceback; traceback.print_exc()
        return None, []


def _draw_score_m21_strip(m21_notes, total_ql, bar_ql,
                           bottom_diatonic, diatonic_offset):
    """Dibuja una tira de pentagrama con pygame puro (sin dependencias externas)."""
    PPQ   = 120
    img_w = max(1280 * 6, int(total_ql * PPQ), 6000)
    img_h = SCORE_H - 4
    surf  = pygame.Surface((img_w, img_h))
    surf.fill((0, 0, 0))

    if not m21_notes or total_ql <= 0:
        return surf

    MARGIN_Y = img_h * 0.16
    staff_h  = img_h - 2 * MARGIN_Y
    line_sp  = staff_h / 4.0
    half_sp  = line_sp / 2.0
    y_bottom = MARGIN_Y + staff_h
    y_lines  = [y_bottom - i * line_sp for i in range(5)]

    C_STAFF = (65, 65, 85)
    for y_line in y_lines:
        pygame.draw.line(surf, C_STAFF,
                         (0, int(y_line)), (img_w, int(y_line)), 1)

    C_BAR   = (45, 45, 65)
    bar_cnt = int(total_ql / max(bar_ql, 0.01)) + 2
    for i in range(bar_cnt + 1):
        x_bar = int(i * bar_ql / total_ql * img_w)
        pygame.draw.line(surf, C_BAR,
                         (x_bar, int(y_lines[0])),
                         (x_bar, int(y_lines[-1])), 1)

    r_note   = max(3, int(half_sp * 0.85))
    C_NOTE   = (188, 188, 210)
    C_LEDGER = (95, 95, 115)

    for n in m21_notes:
        x      = int(n['offset_ql'] / total_ql * img_w)
        steps  = (n['diatonic'] + diatonic_offset) - bottom_diatonic
        y_note = int(y_bottom - steps * half_sp)

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

        dur  = n['duration_ql']
        rx, ry = r_note, max(2, int(r_note * 0.68))
        rect   = (x - rx, y_note - ry, rx * 2, ry * 2)
        if dur >= 2.0:
            pygame.draw.ellipse(surf, C_NOTE, rect, 1)
        else:
            pygame.draw.ellipse(surf, C_NOTE, rect)

        if dur < 4.0:
            stem_up  = steps < 4
            stem_x   = x + rx if stem_up else x - rx
            stem_end = (y_note - int(line_sp * 3) if stem_up
                        else y_note + int(line_sp * 3))
            pygame.draw.line(surf, C_NOTE,
                             (stem_x, y_note), (stem_x, stem_end), 1)

    return surf
