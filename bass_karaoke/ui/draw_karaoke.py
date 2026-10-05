"""
Tira karaoke (J): acordes + bajo objetivo + letra, sincronizados.

Ocupa KARAOKE_Y..TAB_Y (44 px): fila de acordes con el vigente en
grande y el siguiente atenuado, insignia con la tónica para el bajo,
y la línea de letra vigente centrada. El tiempo sale de
_song_seconds(beat_time), el mismo reloj que el audio.
"""
import pygame

from ..config import (
    KARAOKE_Y, KARAOKE_H, W,
    C_BG2, C_ACCENT, C_DGRAY, C_GRAY, C_WHITE, C_GREEN,
)
from ..chords import chord_at, lyric_at


def _bass_root(chord_name: str) -> str:
    """Tónica para el bajo (raíz del acorde, sin la 'm' de menor)."""
    n = (chord_name or "").strip()
    if n.endswith("m") and len(n) > 1:
        n = n[:-1]
    return n or "—"


def draw_karaoke_strip(app) -> None:
    y0, h = KARAOKE_Y, KARAOKE_H
    pygame.draw.rect(app.screen, C_BG2, (0, y0, W, h))
    pygame.draw.line(app.screen, C_DGRAY, (0, y0 + h - 1), (W, y0 + h - 1), 1)

    sec = 0.0
    try:
        sec = float(app._song_seconds(app.beat_time))
    except Exception:
        pass

    cur = chord_at(app.chord_events, sec)
    nxt = None
    for s, n in app.chord_events:
        if s > sec:
            nxt = n
            break
    line = lyric_at(app.lyric_events, sec)

    # Acorde vigente + siguiente
    big = app.font_med.render(cur, True, C_ACCENT)
    app.screen.blit(big, (12, y0 + 2))
    if nxt:
        nx = app.font_small.render(f"→ {nxt}", True, C_GRAY)
        app.screen.blit(nx, (14 + big.get_width(), y0 + 8))

    # Insignia: lo que toca el bajo (tónica del acorde)
    root = _bass_root(cur)
    badge = f"Bajo: {root}"
    bt = app.font_small.render(badge, True, C_GREEN)
    bx = 150
    pygame.draw.rect(app.screen, (10, 30, 18),
                     (bx - 6, y0 + 4, bt.get_width() + 12, 22),
                     border_radius=6)
    pygame.draw.rect(app.screen, C_GREEN,
                     (bx - 6, y0 + 4, bt.get_width() + 12, 22), 1,
                     border_radius=6)
    app.screen.blit(bt, (bx, y0 + 7))

    # Letra vigente (centrada, con hueco para no pisar el acorde)
    if line:
        lt = app.font_small.render(line[:90], True, C_WHITE)
        lx = max(300, W // 2 - lt.get_width() // 2)
        app.screen.blit(lt, (lx, y0 + h - 20))
    else:
        lt = app.font_tiny.render("J = acordes + letra", True, C_DGRAY)
        app.screen.blit(lt, (W - lt.get_width() - 10, y0 + h - 18))
