"""
Panel del Walking Lab (tecla G).

Cubre la zona del tab con la info del ejercicio en bucle: compases,
pulso de negras, nota esperada del tiempo actual y marcador por rol.
El molde (círculos 1-4) se dibuja sobre el mástil en draw_neck.
"""
import pygame

from ..config import (
    TAB_Y, NECK_Y, W,
    STRING_NAMES,
    C_ACCENT, C_DGRAY, C_GRAY, C_WHITE, C_GREEN, C_RED,
    C_OK, C_ERR,
)


def draw_lab_panel(app) -> None:
    y0, h = TAB_Y, NECK_Y - TAB_Y

    pygame.draw.rect(app.screen, (13, 13, 24), (0, y0, W, h))
    pygame.draw.line(app.screen, C_ACCENT, (0, y0), (W, y0), 2)
    pygame.draw.line(app.screen, C_DGRAY, (0, y0 + h - 1), (W, y0 + h - 1), 1)

    state = "▶ ANDANDO" if app.lab_running else "❚❚ PARADO (SPACE para andar)"
    scol = C_GREEN if app.lab_running else C_GRAY
    title = app.font_med.render(
        f"WALKING LAB · {app.lab_title} · {app.lab_bpm:.0f} BPM", True, C_ACCENT)
    app.screen.blit(title, (12, y0 + 8))
    st = app.font_small.render(state, True, scol)
    app.screen.blit(st, (W - st.get_width() - 12, y0 + 10))

    # ── Compases del bucle ──────────────────────────────────────────
    x = 12
    cy = y0 + 44
    for bi, name in enumerate(app.lab_bars):
        cur_bar = (bi == app.lab_bar % max(1, len(app.lab_bars)))
        pill_w = 110
        bg = (45, 45, 70) if cur_bar else (25, 25, 40)
        bd = C_ACCENT if cur_bar else C_DGRAY
        pygame.draw.rect(app.screen, bg, (x, cy, pill_w, 30), border_radius=6)
        pygame.draw.rect(app.screen, bd, (x, cy, pill_w, 30), 2, border_radius=6)
        lbl = app.font_small.render(f"{bi + 1}· {name}", True,
                                    C_WHITE if cur_bar else C_GRAY)
        app.screen.blit(lbl, (x + pill_w // 2 - lbl.get_width() // 2, cy + 6))
        x += pill_w + 8

    # ── Puntos de negra 1-2-3-4 ─────────────────────────────────────
    dot_x = x + 10
    for b in range(4):
        active = app.lab_running and (b == app.lab_beat % 4)
        res = (app.lab_beat_res[b] if b < len(app.lab_beat_res) else None)
        if active:
            c = C_ACCENT
        elif res is True:
            c = C_OK
        elif res is False:
            c = C_ERR
        else:
            c = C_DGRAY
        pygame.draw.circle(app.screen, c, (dot_x + b * 44, cy + 15), 13,
                           0 if active or res is not None else 2)
        n = app.font_small.render(str(b + 1), True,
                                  (10, 10, 18) if (active or res is not None)
                                  else C_GRAY)
        app.screen.blit(n, (dot_x + b * 44 - n.get_width() // 2, cy + 6))

    # ── Nota esperada del tiempo actual ─────────────────────────────
    if app.lab_steps:
        bar = app.lab_bar % len(app.lab_steps)
        beat = app.lab_beat % 4
        stp = app.lab_steps[bar][beat]
        exp = app.font_big.render(
            f"T{beat + 1} {stp['role']} → {stp['name']}  "
            f"(tr.{stp['fret']} {STRING_NAMES[stp['string']]} · dedo {stp['finger']})",
            True, C_WHITE)
        app.screen.blit(exp, (12, y0 + 92))
        if app.lab_last_msg:
            mcol = C_OK if "✓" in app.lab_last_msg else C_RED
            msg = app.font_small.render(app.lab_last_msg[:70], True, mcol)
            app.screen.blit(msg, (12, y0 + 132))

    # ── Marcador global + por rol ───────────────────────────────────
    tot, ok = app.lab_total, app.lab_ok
    if tot > 0:
        pct = int(100 * ok / tot)
        pcol = C_GREEN if pct >= 70 else C_RED if pct < 40 else C_ACCENT
        sc = app.font_med.render(f"{ok}/{tot} ({pct}%)", True, pcol)
    else:
        sc = app.font_med.render("—/—", True, C_GRAY)
    app.screen.blit(sc, (W - sc.get_width() - 12, y0 + 92))
    roles = []
    for i in range(4):
        t, o = app.lab_role_total[i], app.lab_role_ok[i]
        roles.append(f"T{i + 1} {o}/{t}")
    rl = app.font_tiny.render("   ".join(roles), True, C_GRAY)
    app.screen.blit(rl, (W - rl.get_width() - 12, y0 + 126))

    hints = app.font_tiny.render(
        "SPACE anda/para · N ejercicio · ↑/↓ tempo · G salir",
        True, C_GRAY)
    app.screen.blit(hints, (12, y0 + h - 22))
