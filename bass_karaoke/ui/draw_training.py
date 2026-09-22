"""
Overlay del entrenador de notas del mástil (tecla E).

Muestra la nota objetivo, lo que oye el micro, una barra de
"mantén la nota" y el marcador. La validación vive en BassKaraoke.update.
"""
import pygame

from ..config import (
    W, H, C_ACCENT, C_DGRAY, C_GRAY, C_WHITE,
    C_PANEL, C_BLUE, C_GREEN, C_RED, C_OVERLAY, MIN_HZ,
)


def draw_training(app) -> None:
    from ..app import TR_LEVELS

    mw, mh = 620, 400
    mx, my = W // 2 - mw // 2, H // 2 - mh // 2

    ov = pygame.Surface((W, H), pygame.SRCALPHA)
    ov.fill(C_OVERLAY)
    app.screen.blit(ov, (0, 0))

    pygame.draw.rect(app.screen, C_PANEL,  (mx, my, mw, mh), border_radius=12)
    pygame.draw.rect(app.screen, C_ACCENT, (mx, my, mw, mh), 2, border_radius=12)

    hdr = app.font_med.render("ENTRENADOR · ENCUENTRA LA NOTA", True, C_ACCENT)
    app.screen.blit(hdr, (mx + mw // 2 - hdr.get_width() // 2, my + 14))
    pygame.draw.line(app.screen, C_DGRAY,
                     (mx + 10, my + 44), (mx + mw - 10, my + 44), 1)

    lvl = TR_LEVELS.get(app.tr_level, TR_LEVELS[1])
    lvl_t = app.font_small.render(
        f"Nivel {app.tr_level} · {lvl['title']}   (1/2/3 cambian)",
        True, C_GRAY)
    app.screen.blit(lvl_t, (mx + mw // 2 - lvl_t.get_width() // 2, my + 52))

    big = app.font_huge.render(app.tr_target_name, True, C_WHITE)
    app.screen.blit(big, (mx + mw // 2 - big.get_width() // 2, my + 78))

    sub = app.font_small.render("Tócala en cualquier cuerda y traste",
                                True, C_GRAY)
    app.screen.blit(sub, (mx + mw // 2 - sub.get_width() // 2, my + 162))

    with app.pitch_lock:
        det_note = app.stable_note
        det_hz   = app.stable_hz
    oigo_col = C_BLUE if det_hz > MIN_HZ else C_GRAY
    oigo = app.font_med.render(f"Oigo: {det_note}", True, oigo_col)
    app.screen.blit(oigo, (mx + mw // 2 - oigo.get_width() // 2, my + 190))

    # Barra de "mantén la nota" (progreso hacia tr_hold_need)
    bw, bh = 340, 14
    bx = mx + mw // 2 - bw // 2
    by = my + 226
    pygame.draw.rect(app.screen, C_DGRAY, (bx, by, bw, bh), border_radius=5)
    frac = min(1.0, app.tr_hold / max(0.01, app.tr_hold_need))
    if frac > 0:
        pygame.draw.rect(app.screen, C_GREEN,
                         (bx, by, int(bw * frac), bh), border_radius=5)

    tot, ok = app.tr_total, app.tr_ok
    if tot > 0:
        pct = int(100 * ok / tot)
        scol = C_GREEN if pct >= 70 else C_RED if pct < 40 else C_ACCENT
        sc = app.font_med.render(f"{ok}/{tot}  ({pct}%)", True, scol)
    else:
        sc = app.font_med.render("toca la nota para empezar", True, C_GRAY)
    app.screen.blit(sc, (mx + mw // 2 - sc.get_width() // 2, my + 250))

    if app.tr_msg:
        msg = app.font_small.render(app.tr_msg[:60], True, C_GRAY)
        app.screen.blit(msg, (mx + mw // 2 - msg.get_width() // 2, my + 282))

    hint_txt = "N/Espacio=otra · H=pista en piano · 1/2/3 nivel · E salir"
    if app.tr_hint:
        hint_txt = "Pista: clase de tono iluminada en el piano · " + hint_txt
    hint = app.font_tiny.render(hint_txt, True, C_GRAY)
    app.screen.blit(hint, (mx + mw // 2 - hint.get_width() // 2, my + mh - 24))
