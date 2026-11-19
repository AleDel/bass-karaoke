"""
Carril de audio sincronizado dentro de la tarjeta de partitura.

Sustituye la franja grande anterior: la envolvente del MP3 scrollea con el
mismo reloj que partitura y tablatura. Sin MP3 solo queda una etiqueta
tenue, que es el caso del modo metrónomo.
"""
import pygame

from . import theme as T
from .theme import ACCENT, TEXT, TEXT_MUTED

_PAST = (86, 198, 190)
_FUTURE = (64, 82, 118)
_START = (74, 214, 124)
_BASS = (232, 92, 92)


def draw_waveform_strip(app):
    L = app.layout
    r = L.audio
    CURSOR_X = L.cursor_x
    f = T.font(L.fs(9))

    wave = getattr(app, "song_wave", None)
    n = int(getattr(app, "song_wave_n", 0) or 0)
    total = float(getattr(app, "song_total_sec", 0.0) or 0.0)

    if not wave or n <= 0 or total <= 0.0:
        T.text(app.screen, f, "AUDIO  ·  sin MP3", (76, 82, 92),
               (r.x + int(6 * L.s), r.centery), "midleft")
        pygame.draw.line(app.screen, (38, 40, 43),
                         (r.x, r.bottom - 1), (r.right, r.bottom - 1), 1)
        return

    cy = r.centery
    amp = max(2, r.h // 2 - 2)
    vx = app.view.viewport_x
    ppt = app.view.px_per_16th or 1.0
    wmin, wmax = wave
    offset = float(app.mp3_offset_sec)
    start = float(getattr(app, "song_start_sec", 0.0))
    s0 = app._bass_start16()

    prev_clip = app.screen.get_clip()
    app.screen.set_clip(r)

    # Rejilla de compases
    phase = app.grid_phase16()
    for s16 in app.bar_starts16():
        if s16 > 0:
            s16 += phase
        if s16 <= 0:
            continue
        bx = app.px_of(s16) - vx + CURSOR_X
        if r.x <= bx < r.right:
            pygame.draw.line(app.screen, (40, 42, 45),
                             (bx, r.y + 1), (bx, r.bottom - 1), 1)

    # Envolvente
    for x in range(int(r.x), int(r.right)):
        s16 = (x - CURSOR_X + vx) / ppt
        if s16 < 0.0:
            continue
        mp3 = app._eff_seconds(s16, offset)
        if mp3 < 0.0 or mp3 > total:
            continue
        gi = min(n - 1, int(mp3 / total * n))
        y1 = cy - int(wmax[gi] * amp)
        y2 = cy - int(wmin[gi] * amp)
        if y2 - y1 < 1:
            y2 = y1 + 1
        col = _PAST if x < CURSOR_X else _FUTURE
        pygame.draw.line(app.screen, col, (x, y1), (x, y2))

    # Anclas
    xs = app.px_of(0) - vx + CURSOR_X
    if abs(xs - CURSOR_X) < 3:
        xs -= 2
    if r.x - 1 <= xs < r.right + 1:
        pygame.draw.line(app.screen, _START, (xs, r.y + 1), (xs, r.bottom - 1), 1)
    mx = app.px_of(s0) - vx + CURSOR_X
    if r.x - 1 <= mx < r.right + 1:
        pygame.draw.line(app.screen, _BASS, (mx, r.y + 1), (mx, r.bottom - 1), 1)

    # Playhead
    pygame.draw.line(app.screen, ACCENT, (CURSOR_X, r.y), (CURSOR_X, r.bottom), 1)

    app.screen.set_clip(prev_clip)

    # Etiquetas de anclas (solo dentro del carril)
    T.text(app.screen, f, "AUDIO", (76, 82, 92),
           (r.x + int(4 * L.s), r.y + 1), "topleft")
    if r.x < xs < r.right:
        T.text(app.screen, f, "inicio", _START, (int(xs) + 3, r.y + 1), "topleft")
    if r.x < mx < r.right:
        T.text(app.screen, f, "bajo", _BASS, (int(mx) + 3, r.y + 1), "topleft")
    T.text(app.screen, f, f"{offset:+.2f}s", TEXT_MUTED,
           (r.right - int(4 * L.s), r.y + 1), "topright")
