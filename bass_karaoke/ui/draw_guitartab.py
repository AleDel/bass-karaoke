"""
Tablatura numérica sincronizada, dentro de la tarjeta de partitura.

Cuatro líneas (G D A E) con el traste de cada nota encima. La nota actual
se marca con una píldora cian, las pasadas en gris y las futuras con el
color de su cuerda.
"""
import pygame

from ..config import STRING_NAMES
from . import theme as T
from .theme import ACCENT, TEXT, TEXT_DIM, TEXT_MUTED
from .draw_shell import string_color


def draw_guitartab(app) -> None:
    L = app.layout
    r = L.tab
    CURSOR_X = L.cursor_x
    if r.h < 12:
        return

    STR_MARGIN = max(4, int(6 * L.s))
    STR_SPACING = (r.h - STR_MARGIN * 2) / 3
    STR_Y = {s: r.y + STR_MARGIN + (s - 1) * STR_SPACING for s in range(1, 5)}

    f_tab = T.font(L.fs(8), bold=True)
    # Letras de las cuerdas a la izquierda (G / D / A / E)
    for s, y in STR_Y.items():
        iy = int(y)
        T.text(app.screen, f_tab, STRING_NAMES[s], (118, 126, 140),
               (r.x + int(7 * L.s), iy), "center")
        # Línea de tablatura apagada, con un deje del color de la cuerda
        pygame.draw.line(app.screen,
                         T.blend(string_color(s), (110, 118, 132), 0.55),
                         (r.x + int(18 * L.s), iy), (r.right, iy), 1)

    # Cursor
    pygame.draw.line(app.screen, ACCENT, (CURSOR_X, r.y), (CURSOR_X, r.bottom),
                     1)
    cur_note = app.current_note()
    if cur_note and cur_note.get("string") in STR_Y:
        T.dot(app.screen, (CURSOR_X, STR_Y[cur_note["string"]]),
              max(3.0, 4.0 * L.s), ACCENT, glow=12, glow_alpha=90)

    if not app.notes:
        return

    xs = app.view._score_note_xs
    blit_x = CURSOR_X - int(app.view._score_scroll_x)

    def note_screen_x(b16):
        if xs:
            if b16 <= xs[0][0]:
                return blit_x + xs[0][1]
            if b16 >= xs[-1][0]:
                return blit_x + xs[-1][1]
            for k in range(len(xs) - 1):
                b0, x0 = xs[k]
                b1, x1 = xs[k + 1]
                if b0 <= b16 <= b1:
                    t = (b16 - b0) / (b1 - b0) if b1 > b0 else 0.0
                    return blit_x + x0 + t * (x1 - x0)
        return app.px_of(b16) - int(app.view.viewport_x) + CURSOR_X

    # Rejilla de compases
    phase = app.grid_phase16()
    for s16 in app.bar_starts16():
        bx = int(note_screen_x(s16 + phase if s16 > 0 else s16))
        if r.x + 18 < bx < r.right:
            pygame.draw.line(app.screen, (40, 42, 45),
                             (bx, r.y + 2), (bx, r.bottom - 2), 1)

    f_num = T.font(L.fs(10), mono=True)
    f_cur = T.font(L.fs(10), bold=True, mono=True)

    prev_clip = app.screen.get_clip()
    app.screen.set_clip(r)
    for i, note in enumerate(app.notes):
        nx = int(note_screen_x(note["start16"]))
        if nx < r.x - 30 or nx > r.right + 30:
            continue
        ny = int(STR_Y[note["string"]])
        is_cur = (i == app.note_idx and app.beat_time >= note["start16"])
        is_past = (i < app.note_idx)
        fret_str = str(note["fret"])

        if is_cur:
            txt = f_cur.render(fret_str, True, (10, 26, 30))
            box = txt.get_rect(center=(nx, ny)).inflate(
                int(10 * L.s), int(3 * L.s))
            pygame.draw.rect(app.screen, ACCENT, box,
                             border_radius=box.h // 2)
            app.screen.blit(txt, txt.get_rect(center=(nx, ny)))
        else:
            base = string_color(note["string"])
            col = ((86, 92, 102) if is_past
                   else T.blend(base, (190, 198, 210), 0.55))
            txt = f_num.render(fret_str, True, col)
            bg = txt.get_rect(center=(nx, ny)).inflate(
                int(7 * L.s), int(1 * L.s))
            pygame.draw.rect(app.screen, (17, 20, 25), bg)
            app.screen.blit(txt, txt.get_rect(center=(nx, ny)))
    app.screen.set_clip(prev_clip)

    # Notas de gracia
    GRACE_OFFSET = int(14 * L.s)
    for gn in getattr(app, "grace_notes", []):
        main_idx = gn["main_note_idx"]
        if main_idx < 0 or main_idx >= len(app.notes):
            continue
        main_nx = int(note_screen_x(app.notes[main_idx]["start16"]))
        gnx = main_nx - GRACE_OFFSET
        if gnx < r.x + 18 or gnx > r.right:
            continue
        s = gn["string"]
        ny = int(STR_Y[s])
        col = string_color(s)
        gtxt = T.font(L.fs(9)).render(str(gn["fret"]), True, col)
        rect = gtxt.get_rect(center=(gnx, ny))
        pygame.draw.rect(app.screen, T.INSET_DEEP, rect.inflate(2, 0))
        app.screen.blit(gtxt, rect)
        if gn["transition"] in ("slide", "hammer", "legato"):
            lx0 = gnx + gtxt.get_width() // 2 + 2
            lx1 = main_nx - 8
            if lx0 < lx1:
                pygame.draw.line(app.screen, col,
                                 (lx0, ny - 3), (lx1, ny - 1), 1)
