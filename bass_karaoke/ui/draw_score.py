"""
Dibuja la partitura scrolleable (zona SCORE).
"""
import math
import time
import pygame

from ..config import (
    W, TAB_Y, TAB_H, SCORE_H, C_BG, C_ACCENT, C_DGRAY, C_GRAY,
    C_WHITE, C_OK, C_ERR, C_WAIT,
    STRING_COLORS,
)

SY = TAB_Y + TAB_H + 8


def draw_score(app) -> None:
    CURSOR_X = W // 3
    pygame.draw.rect(app.screen, (13, 13, 22), (0, SY, W, SCORE_H))

    if app._score_surf is not None:
        xs = app._score_note_xs

        def beat_to_img_x(b16):
            if not xs:
                total  = getattr(app, '_score_total16', None) or 1
                margin = app._score_surf.get_width() * 0.04
                return margin + max(0, b16) / total * (app._score_surf.get_width() - margin)
            if b16 <= xs[0][0]:
                return xs[0][1]
            if b16 >= xs[-1][0]:
                return xs[-1][1]
            for i in range(len(xs) - 1):
                b0, x0 = xs[i]
                b1, x1 = xs[i + 1]
                if b0 <= b16 <= b1:
                    t = (b16 - b0) / (b1 - b0) if b1 > b0 else 0.0
                    return x0 + t * (x1 - x0)
            return xs[-1][1]

        target_x = beat_to_img_x(app.beat_time)
        app._score_scroll_x += (target_x - app._score_scroll_x) * 0.15
        blit_x = CURSOR_X - int(app._score_scroll_x)

        NAME_H = 14   # altura de la tira de nombres de nota
        clip = pygame.Rect(0, SY, W, SCORE_H)
        app.screen.set_clip(clip)
        app.screen.blit(app._score_surf, (blit_x, SY + NAME_H + 1))
        app.screen.set_clip(None)

        # ── tira de nombres de nota ──────────────────────────────────────────
        pygame.draw.rect(app.screen, (8, 8, 18), (0, SY, W, NAME_H))
        last_nx   = -999
        MIN_GAP   = 26          # px mínimos entre etiquetas
        LABEL_X0  = 90          # dejar espacio para la etiqueta "PARTITURA"
        for note in app.notes:
            img_x  = beat_to_img_x(note["start16"])
            nx     = blit_x + int(img_x)
            if nx < LABEL_X0 or nx > W:
                continue
            if nx - last_nx < MIN_GAP:
                continue
            last_nx = nx
            # color según si es nota pasada, actual o futura
            is_past = note["start16"] < app.beat_time - 1
            is_cur  = abs(note["start16"] - app.beat_time) <= 2
            if is_cur:
                col = C_ACCENT
            elif is_past:
                col = (90, 90, 110)
            else:
                col = (170, 170, 190)
            name = note.get("note_name", "?")
            surf_n = app.font_tiny.render(name, True, col)
            tx = nx - surf_n.get_width() // 2
            tx = max(LABEL_X0, min(tx, W - surf_n.get_width() - 2))
            app.screen.blit(surf_n, (tx, SY + 1))
        # ────────────────────────────────────────────────────────────────────

        pygame.draw.line(app.screen, C_ACCENT,
                         (CURSOR_X, SY + NAME_H + 1), (CURSOR_X, SY + SCORE_H - 6), 2)
        pygame.draw.polygon(app.screen, C_ACCENT, [
            (CURSOR_X - 5, SY + SCORE_H - 6),
            (CURSOR_X + 5, SY + SCORE_H - 6),
            (CURSOR_X,     SY + SCORE_H - 14)])

        lbl = app.font_tiny.render(
            f"PARTITURA  ({app.score_renderer.capitalize()})", True, C_GRAY)
        app.screen.blit(lbl, (4, SY + 1))

    else:
        _draw_score_manual(app, SY, CURSOR_X)

    pygame.draw.line(app.screen, C_DGRAY,
                     (0, SY + SCORE_H - 1), (W, SY + SCORE_H - 1), 1)


def _draw_score_manual(app, SY, CURSOR_X):
    SH       = SCORE_H
    LINE_SEP = 9
    LINES    = 5
    staff_h  = (LINES - 1) * LINE_SEP
    staff_y0 = SY + (SH - staff_h) // 2
    CLEF_W   = 38

    clef_font = pygame.font.SysFont("segoe ui symbol,dejavu sans,arial", 42)
    clef_surf = clef_font.render("𝄢", True, C_GRAY)
    app.screen.blit(clef_surf, (4, staff_y0 - 6))
    for li in range(LINES):
        pygame.draw.line(app.screen, C_DGRAY,
                         (0, staff_y0 + li * LINE_SEP),
                         (W, staff_y0 + li * LINE_SEP), 1)

    STEP_IDX     = {"C": 0, "D": 1, "E": 2, "F": 3, "G": 4, "A": 5, "B": 6}
    REF_DIATONIC = 2 * 7 + 6
    REF_LINE_Y   = staff_y0 + LINE_SEP

    def note_y(step, octave):
        d    = octave * 7 + STEP_IDX[step]
        diff = d - REF_DIATONIC
        return REF_LINE_Y - diff * (LINE_SEP / 2)

    def ledger_lines(ny_pos):
        lines = []
        top_y = staff_y0
        bot_y = staff_y0 + (LINES - 1) * LINE_SEP
        half  = LINE_SEP / 2
        y = top_y - LINE_SEP
        while y >= ny_pos - half + 1:
            lines.append(int(y)); y -= LINE_SEP
        y = bot_y + LINE_SEP
        while y <= ny_pos + half - 1:
            lines.append(int(y)); y += LINE_SEP
        return lines

    vx = int(app.viewport_x)
    prev_meas = -1
    for note in app.notes:
        if note["measure_num"] != prev_meas:
            prev_meas = note["measure_num"]
            mx2 = app.px_of(note["start16"]) - vx + CURSOR_X
            if 30 < mx2 < W:
                pygame.draw.line(app.screen, (55, 55, 80),
                                 (mx2 - 2, staff_y0),
                                 (mx2 - 2, staff_y0 + staff_h), 1)

    for i, note in enumerate(app.notes):
        nx2 = app.px_of(note["start16"]) - vx + CURSOR_X
        if nx2 < -20 or nx2 > W + 20:
            continue
        is_cur   = (i == app.note_idx)
        is_past  = (i < app.note_idx)
        step     = note.get("step", "C")
        octave   = note.get("octave", 3)
        alter    = note.get("alter", 0)
        dur_type = note.get("dur_type", "quarter")
        ny_pos   = note_y(step, octave)
        col = (C_OK  if app.note_match is True  else
               C_ERR if app.note_match is False else C_WAIT) if is_cur else (
              (38, 38, 60) if is_past else STRING_COLORS[note["string"]])

        for ll_y in ledger_lines(ny_pos):
            lc = (55, 55, 80) if is_past else C_DGRAY
            pygame.draw.line(app.screen, lc,
                             (nx2 - 9, ll_y), (nx2 + 9, ll_y), 1)

        hw, hh   = 8, 6
        head_r   = pygame.Rect(nx2 - hw // 2, int(ny_pos) - hh // 2, hw, hh)
        hollow   = dur_type in ("half", "whole")
        if hollow:
            pygame.draw.ellipse(app.screen, col, head_r, 2)
        else:
            pygame.draw.ellipse(app.screen, col, head_r)
        if dur_type != "whole":
            sl  = LINE_SEP * 3
            mid = staff_y0 + staff_h / 2
            if ny_pos >= mid:
                pygame.draw.line(app.screen, col,
                                 (nx2 + hw // 2 - 1, int(ny_pos)),
                                 (nx2 + hw // 2 - 1, int(ny_pos) - sl), 1)
            else:
                pygame.draw.line(app.screen, col,
                                 (nx2 - hw // 2 + 1, int(ny_pos)),
                                 (nx2 - hw // 2 + 1, int(ny_pos) + sl), 1)
        if alter != 0 and not is_past:
            acc = app.font_tiny.render("#" if alter > 0 else "b", True, col)
            app.screen.blit(acc, (nx2 - hw // 2 - acc.get_width() - 1,
                                   int(ny_pos) - acc.get_height() // 2))
        if is_cur:
            pulse = 0.5 + 0.5 * math.sin(time.time() * 9)
            hr    = int(9 + pulse * 3)
            hs    = pygame.Surface((hr * 2, hr * 2), pygame.SRCALPHA)
            pygame.draw.circle(hs, (*col, 40), (hr, hr), hr)
            app.screen.blit(hs, (nx2 - hr, int(ny_pos) - hr))

    lbl_s = app.font_tiny.render("PARTITURA  (clave de Fa — manual)", True, C_GRAY)
    app.screen.blit(lbl_s, (CLEF_W + 4, SY + 2))
