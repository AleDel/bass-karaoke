"""
Panel del entrenador de notas (tecla E) — estilo Walking Lab.

Ocupa la zona del tab (el mástil y el piano quedan visibles) y muestra
la nota objetivo en letra y en pentagrama (clave de fa). La validación
vive en BassKaraoke.update.
"""
import pygame

from ..config import (
    TAB_Y, NECK_Y, W,
    C_ACCENT, C_DGRAY, C_GRAY, C_WHITE,
    C_BLUE, C_GREEN, C_RED,
)
from ..training import LEVELS, accuracy
from .staff import draw_mini_staff

STAFF_W = 200


def draw_training(app) -> None:
    y0, h = TAB_Y, NECK_Y - TAB_Y

    pygame.draw.rect(app.screen, (13, 13, 24), (0, y0, W, h))
    pygame.draw.line(app.screen, C_ACCENT, (0, y0), (W, y0), 2)
    pygame.draw.line(app.screen, C_DGRAY, (0, y0 + h - 1), (W, y0 + h - 1), 1)

    lvl = LEVELS.get(app.tr_level, LEVELS[1])
    title = app.font_med.render("ENTRENADOR · ENCUENTRA LA NOTA", True, C_ACCENT)
    app.screen.blit(title, (12, y0 + 8))
    lvl_t = app.font_small.render(
        f"Nivel {app.tr_level} · {lvl['title']}   (1/2/3 cambian)",
        True, C_GRAY)
    app.screen.blit(lvl_t, (12, y0 + 38))

    big = app.font_huge.render(app.tr_target_name, True, C_WHITE)
    app.screen.blit(big, (12, y0 + 66))
    sub = app.font_small.render("Tócala en cualquier cuerda y traste",
                                True, C_GRAY)
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
    frac = min(1.0, app.tr_hold / max(0.01, app.tr_hold_need))
    if frac > 0:
        pygame.draw.rect(app.screen, C_GREEN,
                         (bx, by, int(bw * frac), bh), border_radius=5)

    tot, ok = app.tr_total, app.tr_ok
    if tot > 0:
        pct = accuracy(ok, tot)
        scol = C_GREEN if pct >= 70 else C_RED if pct < 40 else C_ACCENT
        sc = app.font_med.render(f"{ok}/{tot}  ({pct}%)", True, scol)
    else:
        sc = app.font_med.render("toca la nota para empezar", True, C_GRAY)
    app.screen.blit(sc, (12, y0 + 244))

    if app.tr_msg:
        msg = app.font_small.render(app.tr_msg[:60], True, C_GRAY)
        app.screen.blit(msg, (12, y0 + 276))

    hints = app.font_tiny.render(
        "N=otra · H=pista en piano · 1/2/3 nivel · E salir", True, C_GRAY)
    app.screen.blit(hints, (12, y0 + h - 22))

    # ── Pentagrama (derecha): la objetivo, octava de bajo ──────────
    sx = W - STAFF_W - 16
    sy = y0 + 30
    disp = (app.tr_target_midi - 12
            if app.tr_target_midi is not None else None)
    draw_mini_staff(app, sx, sy, STAFF_W, disp)
    if app.tr_hint:
        hint_t = app.font_tiny.render("pista: clase de tono en el piano",
                                      True, C_GRAY)
        app.screen.blit(hint_t, (sx, sy - 18))
