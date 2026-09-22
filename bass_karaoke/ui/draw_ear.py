"""
Overlay del oído call-response (tecla O).

La app hace sonar una nota oculta; el usuario la repite con el bajo.
Al acertar (o al saltar con N) se revela el nombre y suena la siguiente.
"""
import pygame

from ..config import (
    W, H, C_ACCENT, C_DGRAY, C_GRAY, C_WHITE,
    C_PANEL, C_BLUE, C_GREEN, C_RED, C_OVERLAY, MIN_HZ,
)
from ..training import LEVELS, accuracy


def draw_ear(app) -> None:
    mw, mh = 620, 400
    mx, my = W // 2 - mw // 2, H // 2 - mh // 2

    ov = pygame.Surface((W, H), pygame.SRCALPHA)
    ov.fill(C_OVERLAY)
    app.screen.blit(ov, (0, 0))

    pygame.draw.rect(app.screen, C_PANEL,  (mx, my, mw, mh), border_radius=12)
    pygame.draw.rect(app.screen, C_ACCENT, (mx, my, mw, mh), 2, border_radius=12)

    hdr = app.font_med.render("OÍDO · ESCUCHA Y REPITE", True, C_ACCENT)
    app.screen.blit(hdr, (mx + mw // 2 - hdr.get_width() // 2, my + 14))
    pygame.draw.line(app.screen, C_DGRAY,
                     (mx + 10, my + 44), (mx + mw - 10, my + 44), 1)

    lvl = LEVELS.get(app.ear_level, LEVELS[1])
    lvl_t = app.font_small.render(
        f"Nivel {app.ear_level} · {lvl['title']}   (1/2/3 cambian)",
        True, C_GRAY)
    app.screen.blit(lvl_t, (mx + mw // 2 - lvl_t.get_width() // 2, my + 52))

    shown = app.ear_name if app.ear_revealed else "?"
    big = app.font_huge.render(shown, True, C_WHITE)
    app.screen.blit(big, (mx + mw // 2 - big.get_width() // 2, my + 78))

    sub = app.font_small.render(
        "Escucha la nota y tócala en el bajo" if not app.ear_revealed
        else "Sonando la siguiente…", True, C_GRAY)
    app.screen.blit(sub, (mx + mw // 2 - sub.get_width() // 2, my + 162))

    with app.pitch_lock:
        det_note = app.stable_note
        det_hz   = app.stable_hz
    oigo_col = C_BLUE if det_hz > MIN_HZ else C_GRAY
    oigo = app.font_med.render(f"Oigo: {det_note}", True, oigo_col)
    app.screen.blit(oigo, (mx + mw // 2 - oigo.get_width() // 2, my + 190))

    bw, bh = 340, 14
    bx = mx + mw // 2 - bw // 2
    by = my + 226
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
    app.screen.blit(sc, (mx + mw // 2 - sc.get_width() // 2, my + 250))

    if app.ear_msg:
        msg = app.font_small.render(app.ear_msg[:60], True, C_GRAY)
        app.screen.blit(msg, (mx + mw // 2 - msg.get_width() // 2, my + 282))

    hint = app.font_tiny.render(
        "SPACE=repetir · N=otra · 1/2/3 nivel · O salir", True, C_GRAY)
    app.screen.blit(hint, (mx + mw // 2 - hint.get_width() // 2, my + mh - 24))
