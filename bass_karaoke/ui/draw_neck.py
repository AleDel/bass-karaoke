"""
Dibuja el mástil del bajo (zona NECK).
"""
import math
import pygame

from ..config import (
    NECK_Y, NECK_H, NECK_W, NECK_AREA_X, NECK_AREA_W, NECK_NUT_X, NECK_LABEL_W,
    NECK_FRETS, NECK_DOT_FRETS, NECK_OCT_FRETS,
    STRING_NAMES, STRING_COLORS, STRING_THICK,
    C_BG, C_DGRAY, C_GRAY, C_BLUE, C_OK, C_ERR, C_WAIT,
    C_WOOD, C_WOOD2, C_NUT, C_FRET, C_DOT,
    MIN_HZ,
)


def draw_neck(app) -> None:
    nx0 = 0
    nw, nh = NECK_W, NECK_H
    ny = NECK_Y

    pygame.draw.rect(app.screen, C_WOOD, (nx0, ny, nw, nh))
    for i in range(5):
        yx = ny + 8 + i * 18
        pygame.draw.line(app.screen, C_WOOD2, (nx0, yx), (nx0 + nw, yx), 1)

    STR_MARG = 14
    ss = (nh - STR_MARG * 2 - 16) / 3
    STR_Y = {
        1: ny + STR_MARG,
        2: ny + STR_MARG + ss,
        3: ny + STR_MARG + ss * 2,
        4: ny + STR_MARG + ss * 3,
    }

    fret_space = NECK_AREA_W / NECK_FRETS

    def fret_bar_x(fret):
        return NECK_AREA_X + (fret - 1) * fret_space + fret_space

    def note_x(fret):
        if fret == 0:
            return NECK_NUT_X - 9
        return NECK_AREA_X + (fret - 1) * fret_space + fret_space * 0.5

    for s in range(1, 5):
        y   = int(STR_Y[s])
        lbl = app.font_tiny.render(STRING_NAMES[s], True, STRING_COLORS[s])
        app.screen.blit(lbl, (4, y - lbl.get_height() // 2))

    pygame.draw.rect(app.screen, C_NUT, (NECK_NUT_X, ny + 4, 5, nh - 8))

    for fret in range(1, NECK_FRETS + 1):
        fx = fret_bar_x(fret)
        if fx <= nx0 + nw:
            pygame.draw.line(app.screen, C_FRET,
                             (int(fx), ny + 4), (int(fx), ny + nh - 18), 2)

    num_y = ny + nh - 12
    for fret in range(0, NECK_FRETS + 1):
        xc = int(note_x(fret))
        if xc < nx0 + nw - 4:
            lbl = app.font_tiny.render(str(fret), True, C_FRET)
            app.screen.blit(lbl, (xc - lbl.get_width() // 2, num_y))

    for fret in NECK_DOT_FRETS:
        xc = int(note_x(fret))
        yc = int((STR_Y[2] + STR_Y[3]) / 2)
        if xc < nx0 + nw - 4:
            pygame.draw.circle(app.screen, C_DOT, (xc, yc), 5)
    for fret in NECK_OCT_FRETS:
        xc = int(note_x(fret))
        y1 = int((STR_Y[1] + STR_Y[2]) / 2)
        y2 = int((STR_Y[3] + STR_Y[4]) / 2)
        if xc < nx0 + nw - 4:
            pygame.draw.circle(app.screen, C_DOT, (xc, y1), 5)
            pygame.draw.circle(app.screen, C_DOT, (xc, y2), 5)

    for s in range(1, 5):
        y    = int(STR_Y[s])
        col  = STRING_COLORS[s]
        tick = STRING_THICK[s]
        pygame.draw.line(app.screen, col,
                         (NECK_NUT_X + 5, y), (nx0 + nw - 6, y), tick)
        pygame.draw.line(app.screen, col,
                         (nx0 + NECK_LABEL_W, y), (NECK_NUT_X, y), tick)

    cur = app.current_note()
    if cur:
        xc = int(note_x(cur["fret"]))
        yc = int(STR_Y[cur["string"]])
        if xc <= nx0 + nw - 4:
            col_c = (C_OK  if app.note_match is True  else
                     C_ERR if app.note_match is False else C_WAIT)
            pulse = 0.5 + 0.5 * math.sin(app._t * 8)
            hr    = int(11 + pulse * 4)
            hs    = pygame.Surface((hr * 2, hr * 2), pygame.SRCALPHA)
            pygame.draw.circle(hs, (*col_c, 75), (hr, hr), hr)
            app.screen.blit(hs, (xc - hr, yc - hr))
            pygame.draw.circle(app.screen, col_c, (xc, yc), 11)
            txt = app.font_small.render(str(cur["fret"]), True, (10, 10, 18))
            app.screen.blit(txt, (xc - txt.get_width() // 2,
                                   yc - txt.get_height() // 2))

    with app.pitch_lock:
        det_hz = app.stable_hz
    if det_hz > MIN_HZ:
        best = app._hz_to_fret_string(det_hz)
        if best:
            df, ds = best
            xc = int(note_x(df))
            yc = int(STR_Y[ds])
            if xc <= nx0 + nw - 4:
                pygame.draw.circle(app.screen, C_BLUE, (xc, yc), 9, 2)

    pygame.draw.rect(app.screen, C_DGRAY, (nx0, ny, nw, nh), 1)
    lbl_n = app.font_tiny.render("MASTIL DEL BAJO  (trastes 0–15)", True, C_GRAY)
    app.screen.blit(lbl_n, (nx0 + 4, ny - 13))

    # ── Mapa de notas de la canción (H para activar) ──────────────────────────
    if getattr(app, 'neck_map', False) and app.notes:
        # Calcular qué (fret, string) aparecen en la canción y cuántas veces
        from collections import Counter
        freq = Counter((n['fret'], n['string']) for n in app.notes)
        max_freq = max(freq.values()) if freq else 1

        # Overlay semitransparente
        ov = pygame.Surface((nw, nh), pygame.SRCALPHA)
        ov.fill((0, 0, 0, 140))
        app.screen.blit(ov, (nx0, ny))

        # Redibujar las líneas de cuerdas encima del overlay
        for s in range(1, 5):
            y   = int(STR_Y[s])
            col = STRING_COLORS[s]
            tick = STRING_THICK[s]
            pygame.draw.line(app.screen, col,
                             (NECK_NUT_X + 5, y), (nx0 + nw - 6, y), tick)
            pygame.draw.line(app.screen, col,
                             (nx0 + NECK_LABEL_W, y), (NECK_NUT_X, y), tick)

        # Dibujar círculos para cada (fret, string) usado
        for (fret, string), cnt in freq.items():
            xc = int(note_x(fret))
            yc = int(STR_Y[string])
            if xc > nx0 + nw - 4:
                continue
            # Radio proporcional a la frecuencia (mín 7, máx 13)
            r = int(7 + 6 * (cnt / max_freq))
            col = STRING_COLORS[string]
            # Fondo opaco para que sea visible
            pygame.draw.circle(app.screen, (20, 20, 35), (xc, yc), r)
            pygame.draw.circle(app.screen, col, (xc, yc), r, 2)
            # Número de traste
            lbl = app.font_tiny.render(str(fret), True, col)
            app.screen.blit(lbl, (xc - lbl.get_width() // 2,
                                   yc - lbl.get_height() // 2))

        # Etiqueta
        lbl_m = app.font_tiny.render("MAPA CANCIÓN  (H=ocultar)", True, C_GRAY)
        app.screen.blit(lbl_m, (nx0 + 4, ny - 13))
    else:
        # Etiqueta normal con sugerencia
        lbl_n2 = app.font_tiny.render("  H=Mapa", True, C_DGRAY)
        app.screen.blit(lbl_n2, (nx0 + 4 + lbl_n.get_width(), ny - 13))
