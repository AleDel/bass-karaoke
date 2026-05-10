"""
Dibuja la tablatura estilo TuxGuitar (zona GUITARTAB) debajo de la partitura.
Muestra 4 líneas horizontales con los números de traste sobre ellas.
  - Nota actual     → fondo dorado, número negro (destacado)
  - Notas pasadas   → número gris claro sobre fondo oscuro (el traste sigue visible)
  - Notas futuras   → número en color de la cuerda
"""
import pygame

from ..config import (
    W, GUITARTAB_Y, GUITARTAB_H,
    STRING_NAMES, STRING_COLORS,
    C_BG2, C_ACCENT, C_DGRAY, C_GRAY, C_WHITE,
)

_BG = (16, 16, 30)   # fondo (igual que C_BG2)
_LINE_COL = (55, 55, 72)  # color de las líneas de cuerda


def draw_guitartab(app) -> None:
    CURSOR_X = W // 3
    GTY = GUITARTAB_Y
    GTH = GUITARTAB_H

    STR_MARGIN  = 10
    STR_SPACING = (GTH - STR_MARGIN * 2) / 3

    # string 1=G arriba, 4=E abajo
    STR_Y = {
        s: GTY + STR_MARGIN + (s - 1) * STR_SPACING
        for s in range(1, 5)
    }

    # ── Fondo ────────────────────────────────────────────────────────────────
    pygame.draw.rect(app.screen, _BG, (0, GTY, W, GTH))

    # Etiqueta "TAB"
    lbl = app.font_tiny.render("TAB", True, C_GRAY)
    app.screen.blit(lbl, (4, GTY + 2))

    # ── Líneas de cuerdas + etiquetas ────────────────────────────────────────
    for s, y in STR_Y.items():
        iy = int(y)
        sl = app.font_tiny.render(STRING_NAMES[s], True, STRING_COLORS[s])
        app.screen.blit(sl, (22, iy - sl.get_height() // 2))
        pygame.draw.line(app.screen, _LINE_COL, (42, iy), (W - 2, iy), 1)

    # ── Línea de cursor ───────────────────────────────────────────────────────
    pygame.draw.line(app.screen, C_ACCENT,
                     (CURSOR_X, GTY + 2), (CURSOR_X, GTY + GTH - 2), 1)

    if not app.notes:
        return

    # ── Función de mapeo beat→screen_x, sincronizada con la partitura ─────────
    # Si hay datos de Verovio (_score_note_xs) usa sus posiciones reales;
    # si no, cae de vuelta al espaciado lineal del tab grande.
    xs       = app._score_note_xs          # lista de (b16, img_x)
    blit_x   = CURSOR_X - int(app._score_scroll_x)  # misma base que draw_score

    def note_screen_x(b16):
        if xs:
            if b16 <= xs[0][0]:  return blit_x + xs[0][1]
            if b16 >= xs[-1][0]: return blit_x + xs[-1][1]
            for k in range(len(xs) - 1):
                b0, x0 = xs[k]; b1, x1 = xs[k + 1]
                if b0 <= b16 <= b1:
                    t = (b16 - b0) / (b1 - b0) if b1 > b0 else 0.0
                    return blit_x + x0 + t * (x1 - x0)
        # fallback lineal
        return app.px_of(b16) - int(app.viewport_x) + CURSOR_X

    total16 = app.notes[-1]["start16"] + app.notes[-1]["dur"]
    vx      = int(app.viewport_x)

    # ── Líneas de compás (usa coordenadas del score si hay xs) ───────────────
    # Detectar inicio de cada compás a partir de las notas
    seen_measures = {}
    for note in app.notes:
        m = note["measure_num"]
        if m not in seen_measures:
            seen_measures[m] = note["start16"]
    for s16 in seen_measures.values():
        bx = int(note_screen_x(s16))
        if 42 < bx < W:
            pygame.draw.line(app.screen, C_DGRAY,
                             (bx, GTY + 3), (bx, GTY + GTH - 3), 1)

    # ── Notas (números sobre las líneas) ──────────────────────────────────────
    for i, note in enumerate(app.notes):
        nx = int(note_screen_x(note["start16"]))
        if nx < 20 or nx > W + 40:
            continue

        ny      = int(STR_Y[note["string"]])
        is_cur  = (i == app.note_idx)
        is_past = (i < app.note_idx)

        fret_str = str(note["fret"])

        if is_cur:
            font    = app.font_small
            txt_col = (10, 10, 18)
            bg_col  = C_ACCENT
            border  = True
        elif is_past:
            font    = app.font_small   # mismo tamaño que futuras, solo color gris
            txt_col = (150, 150, 170)
            bg_col  = _BG
            border  = False
        else:
            font    = app.font_small
            txt_col = STRING_COLORS[note["string"]]
            bg_col  = _BG
            border  = False

        txt = font.render(fret_str, True, txt_col)
        tw, th = txt.get_width(), txt.get_height()
        pad_x, pad_y = 3, 1
        rx = nx - tw // 2 - pad_x
        ry = ny - th // 2 - pad_y
        rw = tw + pad_x * 2
        rh = th + pad_y * 2

        # Rectángulo de fondo (corta la línea de cuerda)
        pygame.draw.rect(app.screen, bg_col, (rx, ry, rw, rh))
        if border:
            pygame.draw.rect(app.screen, C_ACCENT, (rx, ry, rw, rh), 1)

        app.screen.blit(txt, (nx - tw // 2, ny - th // 2))

    # ── Notas de gracia (pequeñas, a la izquierda de la nota principal) ───────
    GRACE_OFFSET = 14   # píxeles a la izquierda de la nota principal
    for gn in getattr(app, 'grace_notes', []):
        main_idx = gn['main_note_idx']
        if main_idx < 0 or main_idx >= len(app.notes):
            continue
        main_note = app.notes[main_idx]
        main_nx = int(note_screen_x(main_note['start16']))
        gnx = main_nx - GRACE_OFFSET
        if gnx < 42 or gnx > W + 40:
            continue
        s = gn['string']
        ny = int(STR_Y[s])
        col = STRING_COLORS[s]
        fret_str = str(gn['fret'])
        gtxt = app.font_tiny.render(fret_str, True, col)
        gtw, gth = gtxt.get_width(), gtxt.get_height()
        # Borrar fondo sobre la línea de cuerda
        pygame.draw.rect(app.screen, _BG,
                         (gnx - gtw // 2 - 1, ny - gth // 2 - 1,
                          gtw + 2, gth + 2))
        app.screen.blit(gtxt, (gnx - gtw // 2, ny - gth // 2))
        # Línea de slide/glissando entre gracia y nota principal
        if gn['transition'] in ('slide', 'hammer', 'legato'):
            lx0 = gnx + gtw // 2 + 2
            lx1 = main_nx - 8
            if lx0 < lx1:
                pygame.draw.line(app.screen, col,
                                 (lx0, ny - 3), (lx1, ny - 1), 1)

    # ── Línea separadora inferior ─────────────────────────────────────────────
    pygame.draw.line(app.screen, C_DGRAY,
                     (0, GTY + GTH - 1), (W, GTY + GTH - 1), 1)
