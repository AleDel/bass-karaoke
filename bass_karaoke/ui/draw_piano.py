"""
Dibuja el teclado de piano (zona PIANO).
"""
import math
import pygame

from ..config import (
    PIANO_X, PIANO_Y, PIANO_W, PIANO_H,
    PIANO_START_MIDI, PIANO_END_MIDI,
    C_BG, C_DGRAY, C_GRAY, C_BLUE, C_OK, C_ERR, C_WAIT, C_ACCENT,
    MIN_HZ,
)
from .widgets import build_piano_keys


def draw_piano(app) -> None:
    px, py, pw, ph = PIANO_X, PIANO_Y, PIANO_W, PIANO_H

    if not app._piano_keys_list:
        app._piano_keys_list = build_piano_keys(
            PIANO_START_MIDI, PIANO_END_MIDI, px, py, pw, ph)

    pygame.draw.rect(app.screen, (12, 12, 20), (px, py, pw, ph))

    cur = app.current_note()
    cur_midi = int(round(12 * math.log2(cur["hz"] / 440) + 69)) if cur else -999

    with app.pitch_lock:
        det_hz = app.stable_hz
    det_midi = int(round(12 * math.log2(det_hz / 440) + 69)) if det_hz > MIN_HZ else -999

    col_cur = (C_OK  if app.note_match is True  else
               C_ERR if app.note_match is False else C_WAIT)

    prev_midi = getattr(app, "preview_midi", None)
    prev_on = prev_midi is not None and getattr(app, "preview_timer", 0) > 0

    for key in app._piano_keys_list:
        midi  = key["midi"]
        rect  = key["rect"]
        black = key["black"]
        is_cur = (midi == cur_midi)
        is_det = (midi == det_midi) and det_hz > MIN_HZ
        is_prev = prev_on and (midi == prev_midi)

        if is_prev:
            color = C_ACCENT
        elif is_cur:
            color = col_cur
        elif is_det:
            color = C_BLUE
        elif black:
            color = (20, 20, 30)
        else:
            color = (215, 215, 225)

        pygame.draw.rect(app.screen, color, rect)
        border = C_ACCENT if is_prev else (40, 40, 60) if black else (85, 85, 105)
        pygame.draw.rect(app.screen, border, rect, 2 if is_prev else 1)

        if not black and midi % 12 == 0:
            oct_n = midi // 12 - 1
            lbl   = app.font_tiny.render(f"C{oct_n}", True,
                                          (10, 10, 18) if (is_cur or is_det) else C_DGRAY)
            app.screen.blit(lbl, (rect.x + 1, rect.bottom - 14))

    pygame.draw.rect(app.screen, C_DGRAY, (px, py, pw, ph), 1)
    if prev_on:
        lbl_p = app.font_small.render(
            f"{app.preview_name}  ·  {app.preview_label}  (clic otra tecla)",
            True, C_ACCENT)
    else:
        lbl_p = app.font_tiny.render(
            f"PIANO  E1–Eb4  (midi {PIANO_START_MIDI}–{PIANO_END_MIDI} · clic = oír nota)",
            True, C_GRAY)
    app.screen.blit(lbl_p, (px + 4, py - 13))
