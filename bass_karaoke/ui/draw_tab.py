"""
Dibuja la tablatura scrolleable (zona TAB).
"""
import math
import time
import pygame

from ..config import (
    W, TAB_Y, TAB_H, STRING_NAMES, STRING_COLORS, STRING_THICK,
    C_BG2, C_ACCENT, C_DGRAY, C_SECTION, C_WHITE, C_GRAY,
    C_OK, C_ERR, C_WAIT, C_GREEN, C_RED,
)


def draw_tab(app) -> None:
    CURSOR_X = W // 3

    STR_MARGIN  = 8
    STR_SPACING = (TAB_H - STR_MARGIN * 2) / 3
    STR_Y = {
        1: TAB_Y + STR_MARGIN,
        2: TAB_Y + STR_MARGIN + STR_SPACING,
        3: TAB_Y + STR_MARGIN + STR_SPACING * 2,
        4: TAB_Y + STR_MARGIN + STR_SPACING * 3,
    }

    pygame.draw.rect(app.screen, C_BG2, (0, TAB_Y, W, TAB_H))

    for s, y in STR_Y.items():
        lbl = app.font_small.render(STRING_NAMES[s], True, STRING_COLORS[s])
        app.screen.blit(lbl, (4, int(y) - lbl.get_height() // 2))
        pygame.draw.line(app.screen, STRING_COLORS[s],
                         (28, int(y)), (W, int(y)), STRING_THICK[s])

    # Cursor
    pygame.draw.line(app.screen, C_ACCENT,
                     (CURSOR_X, TAB_Y + 2), (CURSOR_X, TAB_Y + TAB_H - 2), 2)
    pygame.draw.polygon(app.screen, C_ACCENT, [
        (CURSOR_X - 6, TAB_Y + 2),
        (CURSOR_X + 6, TAB_Y + 2),
        (CURSOR_X, TAB_Y + 14)])

    # Indicador de timing
    if app.last_hit_alpha > 0:
        fade      = min(1.0, app.last_hit_alpha)
        alpha_int = int(fade * 255)
        offset_px = int(-app.last_hit_delta16 * app.px_per_16th)
        offset_px = max(-160, min(160, offset_px))
        hit_x     = CURSOR_X + offset_px

        delta_ms = app.last_hit_delta16 / 4.0 * (60000.0 / max(1, app.bpm))
        if abs(delta_ms) < 80:
            base_col = C_OK
        elif abs(delta_ms) < 200:
            base_col = C_ACCENT
        else:
            base_col = C_ERR

        ty = TAB_Y + TAB_H - 3
        surf_line = pygame.Surface((abs(offset_px) + 2, 3), pygame.SRCALPHA)
        pygame.draw.line(surf_line, (*base_col, alpha_int),
                         (0, 1), (abs(offset_px), 1), 2)
        app.screen.blit(surf_line, (min(CURSOR_X, hit_x), ty - 10))
        dot_s = pygame.Surface((10, 10), pygame.SRCALPHA)
        pygame.draw.circle(dot_s, (*base_col, alpha_int), (5, 5), 5)
        app.screen.blit(dot_s, (hit_x - 5, ty - 15))
        sign  = "TARDE" if delta_ms > 20 else ("ANTES" if delta_ms < -20 else "OK")
        t_str = f"{sign} {delta_ms:+.0f}ms"
        txt   = app.font_tiny.render(t_str, True, base_col)
        txt_s = pygame.Surface((txt.get_width(), txt.get_height()), pygame.SRCALPHA)
        txt_s.blit(txt, (0, 0))
        txt_s.set_alpha(alpha_int)
        app.screen.blit(txt_s, (CURSOR_X - txt.get_width() // 2, ty - 28))

    vx      = int(app.viewport_x)
    total16 = (app.notes[-1]["start16"] + app.notes[-1]["dur"]
               if app.notes else 0)

    prev_meas = -1
    for note in app.notes:
        nx = app.px_of(note["start16"]) - vx + CURSOR_X
        if 30 < nx < W and note["measure_num"] != prev_meas:
            prev_meas = note["measure_num"]
            m = app.font_tiny.render(str(note["measure_num"]), True, C_DGRAY)
            app.screen.blit(m, (nx - m.get_width() // 2, TAB_Y + 2))

    for b in range(0, total16 + 16, 16):
        bx = app.px_of(b) - vx + CURSOR_X
        if 30 < bx < W:
            pygame.draw.line(app.screen, C_DGRAY,
                             (bx, TAB_Y + 6), (bx, TAB_Y + TAB_H - 6), 1)

    for label, b16 in app.sections:
        sx = app.px_of(b16) - vx + CURSOR_X
        if 30 < sx < W:
            pygame.draw.line(app.screen, C_SECTION, (sx, TAB_Y), (sx, TAB_Y + TAB_H), 1)
            app.screen.blit(
                app.font_tiny.render(f"[{label}]", True, C_SECTION),
                (sx + 3, TAB_Y + 3))

    R_CUR  = 14
    R_NORM = 11
    R_PAST = 11   # mismo tamaño que futuras, solo cambia el color

    for i, note in enumerate(app.notes):
        nx = app.px_of(note["start16"]) - vx + CURSOR_X
        if nx < 10 or nx > W + 60:
            continue
        ny      = int(STR_Y[note["string"]])
        is_cur  = (i == app.note_idx)
        is_past = (i < app.note_idx)

        if is_cur:
            col = (C_OK  if app.note_match is True  else
                   C_ERR if app.note_match is False else C_WAIT)
            r   = R_CUR
            pulse = 0.5 + 0.5 * math.sin(time.time() * 9)
            hr    = int(r + 6 + pulse * 3)
            hs    = pygame.Surface((hr * 2, hr * 2), pygame.SRCALPHA)
            pygame.draw.circle(hs, (*col, 45), (hr, hr), hr)
            app.screen.blit(hs, (nx - hr, ny - hr))
        elif is_past:
            col = (75, 75, 95)   # gris para notas pasadas
            r   = R_PAST
        else:
            col = STRING_COLORS[note["string"]]
            r   = R_NORM

        dur_px = int(note["dur"] * app.px_per_16th) - 2
        if dur_px > r * 2 + 4 and not is_past:
            if is_cur:
                pygame.draw.line(app.screen, col, (nx, ny), (nx + dur_px, ny), 3)
            else:
                s = pygame.Surface((dur_px, 3), pygame.SRCALPHA)
                pygame.draw.line(s, (*col, 90), (0, 1), (dur_px, 1), 3)
                app.screen.blit(s, (nx, ny - 1))

        pygame.draw.circle(app.screen, col, (nx, ny), r)
        pygame.draw.circle(app.screen, (10, 10, 18), (nx, ny), r - 3)

        f       = app.font_med if is_cur else app.font_small
        txt_col = (195, 195, 215) if is_past else C_WHITE
        txt = f.render(str(note["fret"]), True, txt_col)
        app.screen.blit(txt, (nx - txt.get_width() // 2,
                               ny - txt.get_height() // 2))

    # ── Guitar Hero: nota detectada por el micrófono ─────────────────────────
    det    = getattr(app, 'detected_fret_str', None)
    det_hz = getattr(app, 'stable_hz', 0.0)
    if det is not None and det_hz > 0:
        det_fret, det_str = det
        ny = int(STR_Y[det_str])
        cur = app.current_note()

        # Calcular desviación en cents respecto a la nota esperada
        cents = None
        if cur is not None and cur.get('hz', 0) > 0:
            try:
                cents = 1200.0 * math.log2(det_hz / cur['hz'])
            except Exception:
                cents = None

        if cents is not None:
            ac     = abs(cents)
            gh_col = C_OK if ac < 25 else (C_ACCENT if ac < 80 else C_ERR)
        else:
            gh_col = STRING_COLORS[det_str]

        # Halo pulsante de la nota detectada
        pulse = 0.5 + 0.5 * math.sin(time.time() * 10)
        hr = int(16 + pulse * 5)
        hs = pygame.Surface((hr * 2, hr * 2), pygame.SRCALPHA)
        pygame.draw.circle(hs, (*gh_col, 65), (hr, hr), hr)
        app.screen.blit(hs, (CURSOR_X - hr, ny - hr))

        # Círculo sólido de la nota detectada (más pequeño que el esperado)
        pygame.draw.circle(app.screen, gh_col, (CURSOR_X, ny), 9)
        pygame.draw.circle(app.screen, (220, 220, 255), (CURSOR_X, ny), 9, 2)
        f_t = app.font_tiny.render(str(det_fret), True, (10, 10, 18))
        app.screen.blit(f_t, (CURSOR_X - f_t.get_width() // 2,
                               ny - f_t.get_height() // 2))

        # Etiqueta con nombre de nota + cents (a la derecha del cursor)
        note_lbl  = getattr(app, 'stable_note', '?')
        cents_lbl = f" {int(cents):+d}¢" if cents is not None else ""
        lbl_surf  = app.font_tiny.render(f"{note_lbl}{cents_lbl}", True, gh_col)
        lx = CURSOR_X + 18
        ly = ny - lbl_surf.get_height() // 2
        ly = max(TAB_Y + 2, min(ly, TAB_Y + TAB_H - lbl_surf.get_height() - 2))
        pygame.draw.rect(app.screen, (10, 10, 18),
                         (lx - 1, ly - 1, lbl_surf.get_width() + 4,
                          lbl_surf.get_height() + 2))
        app.screen.blit(lbl_surf, (lx, ly))

        # Barra de afinación (cents) justo debajo del círculo
        if cents is not None:
            BAR_W, BAR_H = 50, 4
            by = ny + 14
            if TAB_Y + 6 < by < TAB_Y + TAB_H - 8:
                bx = CURSOR_X - BAR_W // 2
                pygame.draw.rect(app.screen, (35, 35, 55), (bx, by, BAR_W, BAR_H))
                pygame.draw.line(app.screen, (110, 110, 130),
                                 (CURSOR_X, by - 1), (CURSOR_X, by + BAR_H + 1), 1)
                fill = min(BAR_W // 2, int(abs(cents) / 200.0 * BAR_W // 2))
                if cents >= 0:
                    pygame.draw.rect(app.screen, gh_col, (CURSOR_X, by, fill, BAR_H))
                else:
                    pygame.draw.rect(app.screen, gh_col,
                                     (CURSOR_X - fill, by, fill, BAR_H))

    pygame.draw.line(app.screen, C_DGRAY,
                     (0, TAB_Y + TAB_H), (W, TAB_Y + TAB_H), 1)
