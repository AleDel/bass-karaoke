"""
Franja de waveform sincronizada (vista principal).

Representa DÓNDE VA EL AUDIO: la envolvente del MP3 scrollea con el mismo
reloj que la tira de acordes, la tablatura y la partitura (viewport_x +
CURSOR_X), y el tramo ya reproducido (izquierda del playhead) se resalta.

- La línea verde marca el inicio de canción (compás 1): song_start_sec.
- La línea roja marca el inicio del bajo: el instante del MP3
  (mp3_offset_sec) donde suena la PRIMERA nota del bajo.
  El silencio entre ambas se estira sin mover el resto de la partitura.
- Interacción (ver app.handle_event):
    · botón izquierdo / derecho  → desplazarse por la canción (como el tab)
    · arrastrar cerca de verde/roja → mover cada ancla por separado
    · botón central              → mover el audio (ambas anclas a la vez)
"""

import pygame

from ..config import (
    W, WAVEFORM_Y, WAVEFORM_H,
    C_BG2, C_ACCENT, C_RED, C_GRAY, C_PANEL,
)

CURSOR_X   = W // 3
_WAVE_PAST = (96, 200, 190)    # tramo ya reproducido (teal, como el karaoke)
_WAVE_FUTR = (72, 92, 140)     # tramo por venir (azul tenue)
_TICK_COL  = (40, 40, 62)
_START_COL = (70, 220, 120)    # ancla de inicio de canción (verde)


def draw_waveform_strip(app):
    y0, h = WAVEFORM_Y, WAVEFORM_H
    screen = app.screen
    pygame.draw.rect(screen, C_BG2, (0, y0, W, h))

    wave  = getattr(app, "song_wave", None)
    n     = int(getattr(app, "song_wave_n", 0) or 0)
    total = float(getattr(app, "song_total_sec", 0.0) or 0.0)

    if not wave or n <= 0 or total <= 0.0:
        screen.blit(app.font_small.render("waveform: sin MP3", True, C_GRAY),
                    (10, y0 + h // 2 - 8))
        pygame.draw.line(screen, C_PANEL, (0, y0), (W, y0), 1)
        return

    cy  = y0 + h // 2
    amp = max(2, h // 2 - 8)
    vx  = app.viewport_x
    ppt = app.px_per_16th or 1.0
    wmin, wmax = wave

    offset = float(app.mp3_offset_sec)
    s0     = app._bass_start16()
    start  = float(getattr(app, "song_start_sec", 0.0))
    sec_at = lambda s16: app._eff_seconds(s16, offset)

    phase = app.grid_phase16()
    for s16 in app.bar_starts16():
        if s16 > 0:
            s16 += phase
        if s16 <= 0:
            continue
        bx = app.px_of(s16) - vx + CURSOR_X
        if 0 <= bx < W:
            pygame.draw.line(screen, _TICK_COL, (bx, y0 + 3), (bx, y0 + h - 3), 1)

    # ── Envolvente: pasado (resaltado) / futuro (tenue) ───────────────
    for x in range(W):
        s16 = (x - CURSOR_X + vx) / ppt
        if s16 < 0.0:
            continue
        mp3 = sec_at(s16)
        if mp3 < 0.0 or mp3 > total:
            continue
        gi = int(mp3 / total * n)
        if gi >= n:
            gi = n - 1
        y1 = cy - int(wmax[gi] * amp)
        y2 = cy - int(wmin[gi] * amp)
        if y2 - y1 < 1:
            y2 = y1 + 1
        col = _WAVE_PAST if x < CURSOR_X else _WAVE_FUTR
        pygame.draw.line(screen, col, (x, y1), (x, y2))

    pygame.draw.line(screen, (60, 60, 90), (0, cy), (W, cy), 1)

    # ── Ancla de inicio de canción / compás 1 (verde) ─────────────────
    xs = app.px_of(0) - vx + CURSOR_X
    if abs(xs - CURSOR_X) < 3:
        xs -= 2   # no tapar el playhead cuando la partitura empieza en él
    if -1 <= xs < W + 1:
        pygame.draw.line(screen, _START_COL, (xs, y0 + 1), (xs, y0 + h - 1), 2)
        pygame.draw.polygon(screen, _START_COL, [
            (xs - 5, y0 + 1), (xs + 5, y0 + 1), (xs, y0 + 8)])
        screen.blit(app.font_tiny.render("inicio", True, _START_COL),
                    (max(2, xs - 52), y0 + 2))

    # ── Marca del inicio del bajo (offset) ────────────────────────────
    mx = app.px_of(s0) - vx + CURSOR_X
    if -1 <= mx < W + 1:
        pygame.draw.line(screen, C_RED, (mx, y0 + 1), (mx, y0 + h - 1), 2)
        pygame.draw.polygon(screen, C_RED, [
            (mx - 5, y0 + 1), (mx + 5, y0 + 1), (mx, y0 + 8)])
        screen.blit(app.font_tiny.render("bajo", True, C_RED), (mx + 5, y0 + 2))

    # ── Playhead ──────────────────────────────────────────────────────
    pygame.draw.line(screen, C_ACCENT, (CURSOR_X, y0 + 1), (CURSOR_X, y0 + h - 1), 2)

    # ── Etiquetas ─────────────────────────────────────────────────────
    screen.blit(app.font_tiny.render("AUDIO", True, C_GRAY), (6, y0 + 3))
    info = (f"central = mover audio ({offset:+.2f}s)   "
            f"inicio {start:.2f}s   "
            f"arrastra verde/roja = inicio/bajo   "
            f"izq/der = navegar   Ctrl+S = guardar")
    it = app.font_tiny.render(info, True, C_GRAY)
    screen.blit(it, (W - it.get_width() - 8, y0 + h - 14))

    pygame.draw.line(screen, C_PANEL, (0, y0), (W, y0), 1)
    pygame.draw.line(screen, C_PANEL, (0, y0 + h - 1), (W, y0 + h - 1), 1)
