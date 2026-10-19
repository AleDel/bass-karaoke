"""
Panel del bajeo de corridos tumbados (tecla K) — mismo estilo que el
Walking Lab pero en 3/4: T1 suena (raíz/5ª/adorno), T2-T3 callan.

Ocupa la zona del tab (mástil y piano visibles): compases del bucle
(2 por acorde), pulso de vals con fuerte en el 1, nota esperada en
letra y pentagrama, y marcador. El molde se dibuja en draw_neck.
"""
import pygame

from ..config import (
    C_ACCENT,
    C_DGRAY,
    C_ERR,
    C_GRAY,
    C_GREEN,
    C_OK,
    C_RED,
    C_WHITE,
    NECK_Y,
    STRING_NAMES,
    TAB_Y,
    W,
)
from .staff import draw_mini_staff

STAFF_W = 200


def draw_corrido_panel(app) -> None:
    y0, h = TAB_Y, NECK_Y - TAB_Y

    pygame.draw.rect(app.screen, (13, 13, 24), (0, y0, W, h))
    pygame.draw.line(app.screen, C_ACCENT, (0, y0), (W, y0), 2)
    pygame.draw.line(app.screen, C_DGRAY, (0, y0 + h - 1), (W, y0 + h - 1), 1)

    state = ">> BAJEO" if app.cor_running else "|| PARADO (SPACE para andar)"
    scol = C_GREEN if app.cor_running else C_GRAY
    title = app.font_med.render(
        f"CORRIDO · {app.cor_title} · {app.cor_bpm:.0f} BPM · 3/4",
        True, C_ACCENT)
    app.screen.blit(title, (12, y0 + 8))
    st = app.font_small.render(state, True, scol)
    app.screen.blit(st, (W - st.get_width() - STAFF_W - 28, y0 + 10))
    sub = app.font_tiny.render(
        f"quinta {app.cor_fifth} (Q) · "
        f"adorno {'sí' if app.cor_ornament else 'no'} (F)",
        True, C_GRAY)
    app.screen.blit(sub, (12, y0 + 34))

    # ── Compases del bucle (2 por acorde) ──────────────────────────
    x = 12
    cy = y0 + 56
    for bi, name in enumerate(app.cor_bars):
        cur_bar = (bi == app.cor_bar % max(1, len(app.cor_bars)))
        pill_w = 92
        bg = (45, 45, 70) if cur_bar else (25, 25, 40)
        bd = C_ACCENT if cur_bar else C_DGRAY
        pygame.draw.rect(app.screen, bg, (x, cy, pill_w, 30), border_radius=6)
        pygame.draw.rect(app.screen, bd, (x, cy, pill_w, 30), 2, border_radius=6)
        lbl = app.font_small.render(f"{bi + 1}· {name}", True,
                                    C_WHITE if cur_bar else C_GRAY)
        app.screen.blit(lbl, (x + pill_w // 2 - lbl.get_width() // 2, cy + 6))
        x += pill_w + 8

    # ── Puntos de vals 1-2-3 (fuerte en el 1) ───────────────────────
    dot_x = x + 10
    for b in range(3):
        active = app.cor_running and (b == app.cor_beat % 3)
        res = (app.cor_beat_res[b] if b < len(app.cor_beat_res) else None)
        if active:
            c = C_ACCENT
        elif res is True:
            c = C_OK
        elif res is False:
            c = C_ERR
        else:
            c = C_DGRAY
        rad = 15 if b == 0 else 12
        pygame.draw.circle(app.screen, c, (dot_x + b * 44, cy + 15), rad,
                           0 if active or res is not None else 2)
        n = app.font_small.render(str(b + 1), True,
                                  (10, 10, 18) if (active or res is not None)
                                  else C_GRAY)
        app.screen.blit(n, (dot_x + b * 44 - n.get_width() // 2, cy + 6))

    # ── Lo esperado en este tiempo ──────────────────────────────────
    staff_midi = None
    if app.cor_steps:
        bar = app.cor_bar % len(app.cor_steps)
        beat = app.cor_beat % 3
        stp = app.cor_steps[bar][beat]
        if stp.get("midi") is None:
            exp = app.font_big.render(
                f"T{beat + 1} — silencio  (guitarras)", True, C_GRAY)
        else:
            staff_midi = stp["midi"]
            exp = app.font_big.render(
                f"T{beat + 1} {stp['role']} → {stp['name']}  "
                f"(tr.{stp['fret']} {STRING_NAMES[stp['string']]}"
                f" · dedo {stp['finger']})",
                True, C_WHITE)
        app.screen.blit(exp, (12, y0 + 104))
        if app.cor_last_msg:
            mcol = C_OK if "[OK]" in app.cor_last_msg else C_RED
            msg = app.font_small.render(app.cor_last_msg[:70], True, mcol)
            app.screen.blit(msg, (12, y0 + 144))

    # ── Columna derecha: pentagrama + marcador ──────────────────────
    sx = W - STAFF_W - 16
    draw_mini_staff(app, sx, y0 + 46, STAFF_W, staff_midi)
    tot, ok = app.cor_total, app.cor_ok
    if tot > 0:
        pct = int(100 * ok / tot)
        pcol = C_GREEN if pct >= 70 else C_RED if pct < 40 else C_ACCENT
        sc = app.font_med.render(f"{ok}/{tot} ({pct}%)", True, pcol)
    else:
        sc = app.font_med.render("—/—", True, C_GRAY)
    app.screen.blit(sc, (sx, y0 + 222))
    roles = []
    for i in range(3):
        t, o = app.cor_role_total[i], app.cor_role_ok[i]
        roles.append(f"T{i + 1} {o}/{t}")
    rl = app.font_tiny.render("   ".join(roles), True, C_GRAY)
    app.screen.blit(rl, (sx, y0 + 250))

    hints = app.font_tiny.render(
        "SPACE bajeo/para · N ejercicio · Q quinta · F adornos · "
        "↑/↓ tempo · K salir",
        True, C_GRAY)
    app.screen.blit(hints, (12, y0 + h - 22))
