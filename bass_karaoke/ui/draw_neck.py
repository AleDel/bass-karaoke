"""
Dibuja el mástil del bajo (zona NECK).
"""
import math
import pygame

from ..config import (
    NECK_Y, NECK_H, NECK_W, NECK_AREA_X, NECK_AREA_W, NECK_NUT_X, NECK_LABEL_W,
    NECK_FRETS, NECK_DOT_FRETS, NECK_OCT_FRETS,
    STRING_NAMES, STRING_COLORS, STRING_THICK,
    C_BG, C_DGRAY, C_GRAY, C_BLUE, C_OK, C_ERR, C_WAIT, C_WHITE,
    C_WOOD, C_WOOD2, C_NUT, C_FRET, C_DOT, C_ACCENT,
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
    lbl_n = app.font_tiny.render("MASTIL DEL BAJO  (trastes 0–15 · clic = oír nota)", True, C_GRAY)
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

    # ── Walking Lab: molde del compás actual (círculos 1-4) ──────────
    if getattr(app, "lab_open", False) and getattr(app, "lab_steps", None):
        bar = app.lab_bar % len(app.lab_steps)
        res = getattr(app, "lab_beat_res", [None] * 4)
        running = getattr(app, "lab_running", False)
        for i, stp in enumerate(app.lab_steps[bar]):
            xc = int(note_x(stp["fret"]))
            yc = int(STR_Y.get(stp["string"], 0))
            if xc > nx0 + nw - 4 or stp["string"] not in STR_Y:
                continue
            cur = running and (i == app.lab_beat % 4)
            r = res[i] if i < len(res) else None
            if cur:
                col, rad, wdt = C_ACCENT, 13, 3
            elif r is True:
                col, rad, wdt = C_OK, 11, 2
            elif r is False:
                col, rad, wdt = C_ERR, 11, 2
            else:
                col, rad, wdt = C_GRAY, 10, 2
            pygame.draw.circle(app.screen, (20, 20, 35), (xc, yc), rad)
            pygame.draw.circle(app.screen, col, (xc, yc), rad, wdt)
            num = app.font_small.render(str(i + 1), True, col)
            app.screen.blit(num, (xc - num.get_width() // 2,
                                   yc - num.get_height() // 2))
            if cur:
                nm = app.font_tiny.render(stp["name"], True, C_ACCENT)
                app.screen.blit(nm, (xc - nm.get_width() // 2, yc - 28))
    # ── Corridos: bajeo del compás actual (tiempos 1-2-3) ──────────
    if getattr(app, "cor_open", False) and getattr(app, "cor_steps", None):
        bar = app.cor_bar % len(app.cor_steps)
        res = getattr(app, "cor_beat_res", [None] * 3)
        running = getattr(app, "cor_running", False)
        for i, stp in enumerate(app.cor_steps[bar]):
            if stp.get("fret") is None or stp.get("string") is None:
                continue
            xc = int(note_x(stp["fret"]))
            yc = int(STR_Y.get(stp["string"], 0))
            if xc > nx0 + nw - 4 or stp["string"] not in STR_Y:
                continue
            cur = running and (i == app.cor_beat % 3)
            r = res[i] if i < len(res) else None
            if cur:
                col, rad, wdt = C_ACCENT, 13, 3
            elif r is True:
                col, rad, wdt = C_OK, 11, 2
            elif r is False:
                col, rad, wdt = C_ERR, 11, 2
            else:
                col, rad, wdt = C_GRAY, 10, 2
            pygame.draw.circle(app.screen, (20, 20, 35), (xc, yc), rad)
            pygame.draw.circle(app.screen, col, (xc, yc), rad, wdt)
            num = app.font_small.render(str(i + 1), True, col)
            app.screen.blit(num, (xc - num.get_width() // 2,
                                   yc - num.get_height() // 2))
            if cur:
                nm = app.font_tiny.render(stp["name"], True, C_ACCENT)
                app.screen.blit(nm, (xc - nm.get_width() // 2, yc - 28))
    # ── Secuencias (X/A/V): objetivo actual en el mástil ──────────────
    sp = getattr(app, "seq_pos", None)
    if sp:
        xc = int(note_x(sp[0]))
        yc = int(STR_Y.get(sp[1], 0))
        if xc <= nx0 + nw - 4 and sp[1] in STR_Y:
            pygame.draw.circle(app.screen, (20, 20, 35), (xc, yc), 12)
            pygame.draw.circle(app.screen, C_WHITE, (xc, yc), 12, 2)
            lb = app.font_tiny.render(getattr(app, "seq_label", ""),
                                      True, C_WHITE)
            app.screen.blit(lb, (xc - lb.get_width() // 2, yc - 28))

    # ── Modo aprendizaje: nota pulsada con el ratón (encima de todo) ──
    prev = getattr(app, "preview_fret_str", None)
    if prev and getattr(app, "preview_timer", 0) > 0:
        pf, ps = prev
        xc = int(note_x(pf))
        yc = int(STR_Y.get(ps, 0))
        if xc <= nx0 + nw - 4 and ps in STR_Y:
            pygame.draw.circle(app.screen, C_ACCENT, (xc, yc), 13, 3)
            pygame.draw.circle(app.screen, (20, 20, 35), (xc, yc), 10)
            pygame.draw.circle(app.screen, C_ACCENT, (xc, yc), 10, 1)
            nm = app.font_small.render(getattr(app, "preview_name", ""),
                                        True, C_ACCENT)
            app.screen.blit(nm, (xc - nm.get_width() // 2, yc - 30))
            # Etiqueta completa (nota + traste + cuerda + Hz)
            hz = getattr(app, "preview_hz", 0.0) or 0.0
            full = f"{app.preview_label}  {hz:.1f} Hz" if hz else app.preview_label
            fl = app.font_small.render(full, True, C_ACCENT)
            bx = min(max(xc - fl.get_width() // 2, nx0 + 4), nx0 + nw - fl.get_width() - 4)
            bg = pygame.Surface((fl.get_width() + 12, fl.get_height() + 6))
            bg.fill((20, 20, 35))
            app.screen.blit(bg, (bx - 6, ny - 34))
            pygame.draw.rect(app.screen, C_ACCENT, (bx - 6, ny - 34,
                             fl.get_width() + 12, fl.get_height() + 6), 1)
            app.screen.blit(fl, (bx, ny - 31))
