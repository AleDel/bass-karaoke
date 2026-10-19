"""
Panel del oído call-response (tecla O) — estilo Walking Lab.

Ocupa la zona del tab (mástil y piano visibles). La nota suena oculta
("?"); al acertar o saltar se revela en letra y en pentagrama.
"""
import pygame

from ..config import (
    C_ACCENT,
    C_BLUE,
    C_DGRAY,
    C_GRAY,
    C_GREEN,
    C_RED,
    C_WHITE,
    NECK_Y,
    TAB_Y,
    W,
)
from ..training import LEVELS, accuracy
from .staff import draw_mini_staff

STAFF_W = 200


def draw_ear(app) -> None:
    y0, h = TAB_Y, NECK_Y - TAB_Y

    pygame.draw.rect(app.screen, (13, 13, 24), (0, y0, W, h))
    pygame.draw.line(app.screen, C_ACCENT, (0, y0), (W, y0), 2)
    pygame.draw.line(app.screen, C_DGRAY, (0, y0 + h - 1), (W, y0 + h - 1), 1)

    lvl = LEVELS.get(app.ear_level, LEVELS[1])
    title = app.font_med.render("OÍDO · ESCUCHA Y REPITE", True, C_ACCENT)
    app.screen.blit(title, (12, y0 + 8))
    lvl_t = app.font_small.render(
        f"Nivel {app.ear_level} · {lvl['title']}   (1/2/3 cambian)",
        True, C_GRAY)
    app.screen.blit(lvl_t, (12, y0 + 38))

    shown = app.ear_name if app.ear_revealed else "?"
    big = app.font_huge.render(shown, True, C_WHITE)
    app.screen.blit(big, (12, y0 + 66))
    sub = app.font_small.render(
        "Escucha la nota y tócala en el bajo" if not app.ear_revealed
        else "Sonando la siguiente…", True, C_GRAY)
    app.screen.blit(sub, (14, y0 + 152))

    with app.pitch_lock:
        det_note = app.stable_note
        det_hz   = app.stable_hz
    oigo_col = C_BLUE if det_hz > 0 else C_GRAY
    oigo = app.font_med.render(f"Oigo: {det_note}", True, oigo_col)
    app.screen.blit(oigo, (12, y0 + 182))

    bw, bh = 300, 14
    bx, by = 12, y0 + 220
    pygame.draw.rect(app.screen, C_DGRAY, (bx, by, bw, bh), border_radius=5)
    frac = min(1.0, app.ear_hold / max(0.01, app.tr_hold_need))
    if frac > 0 and not app.ear_revealed:
        pygame.draw.rect(app.screen, C_GREEN,
                         (bx, by, int(bw * frac), bh), border_radius=5)

    tot, ok = app.ear_total, app.ear_ok
    if tot > 0:
        pct = accuracy(ok, tot)
        scol = C_GREEN if pct >= 70 else C_RED if pct < 40 else C_ACCENT
        sc = app.font_med.render(f"{ok}/{tot}  ({pct}%)", True, scol)
    else:
        sc = app.font_med.render("escucha y repite para empezar", True, C_GRAY)
    app.screen.blit(sc, (12, y0 + 244))

    if app.ear_msg:
        msg = app.font_small.render(app.ear_msg[:60], True, C_GRAY)
        app.screen.blit(msg, (12, y0 + 276))

    hints = app.font_tiny.render(
        "SPACE=repetir · N=otra · 1/2/3 nivel · O salir", True, C_GRAY)
    app.screen.blit(hints, (12, y0 + h - 22))

    # ── Pentagrama (derecha): oculto hasta revelar ─────────────────
    sx = W - STAFF_W - 16
    sy = y0 + 30
    disp = None
    if app.ear_revealed and app.ear_midi is not None:
        disp = app.ear_midi - 12
    draw_mini_staff(app, sx, sy, STAFF_W, disp)
