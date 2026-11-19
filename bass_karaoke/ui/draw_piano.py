"""
Teclado de piano de la tarjeta inferior central.

Rango E1–Eb4 (el del bajo). La nota actual se enciende en cian, la
detectada se marca en azul y la pulsada con el ratón lleva borde de acento.
"""
import math

import pygame

from ..config import (
    MIN_HZ,
    PIANO_END_MIDI,
    PIANO_START_MIDI,
)
from . import theme as T
from .theme import ACCENT, TEXT, TEXT_MUTED
from .widgets import build_piano_keys


def _keys(app):
    L = app.layout
    rect = L.piano_keys
    if (not app._piano_keys_list
            or getattr(app, "_piano_keys_rect", None) != tuple(rect)):
        app._piano_keys_list = build_piano_keys(
            PIANO_START_MIDI, PIANO_END_MIDI,
            rect.x, rect.y, rect.w, rect.h)
        app._piano_keys_rect = tuple(rect)
    return app._piano_keys_list


def draw_piano(app) -> None:
    L = app.layout
    card = L.piano

    rect = L.piano_keys
    T.inset(app.screen, rect, radius=max(4, int(6 * L.s)),
            color=T.INSET_DEEP)

    cur = app.current_note()
    cur_midi = (int(round(12 * math.log2(cur["hz"] / 440) + 69))
                if cur and cur.get("hz", 0) > 0 else 36)  # C2 como en la referencia

    with app.pitch_lock:
        det_hz = app.stable_hz
    det_midi = (int(round(12 * math.log2(det_hz / 440) + 69))
                if det_hz > MIN_HZ else -999)

    col_cur = (T.GREEN if app.note_match is True else
               T.RED if app.note_match is False else ACCENT)

    prev_midi = getattr(app.view, "preview_midi", None)
    prev_on = prev_midi is not None and getattr(app.view, "preview_timer", 0) > 0

    prev_clip = app.screen.get_clip()
    app.screen.set_clip(rect)

    for key in _keys(app):
        midi = key["midi"]
        r = key["rect"]
        black = key["black"]
        is_cur = (midi == cur_midi)
        is_det = (midi == det_midi) and det_hz > MIN_HZ
        is_prev = prev_on and (midi == prev_midi)

        if is_cur:
            fill = col_cur
            edge = (180, 245, 255)
        elif is_prev:
            fill = ACCENT
            edge = ACCENT
        elif black:
            fill = (22, 25, 30)
            edge = (44, 50, 60)
        else:
            fill = (235, 238, 244)
            edge = (206, 212, 222)

        radius = max(2, int(4 * L.s)) if not black else max(1, int(2 * L.s))
        pygame.draw.rect(app.screen, fill, r, border_radius=radius)
        pygame.draw.rect(app.screen, edge[:3], r, 1, border_radius=radius)

        if is_det and not is_cur:
            pygame.draw.rect(app.screen, (60, 140, 220), r.inflate(-2, -2), 2,
                             border_radius=radius)

        # Etiquetas en teclas blancas: nota actual en cian, octavas clave en gris
        if not black:
            if is_cur:
                note_name = cur.get("note_name", "C2") if cur else "C2"
                T.text(app.screen, T.font(L.fs(9), bold=True), note_name, (10, 26, 32),
                       (r.centerx, r.bottom - int(4 * L.s)), "midbottom")
            elif midi in (28, 36, 48, 60, 63):
                # Etiquetas E1, C2, C3, C4 + Eb4 de referencia
                names = {28: "E1", 36: "C2", 48: "C3", 60: "C4", 63: "Eb4"}
                T.text(app.screen, T.font(L.fs(8)), names[midi], (100, 106, 116),
                       (r.centerx, r.bottom - int(3 * L.s)), "midbottom")
    app.screen.set_clip(prev_clip)

    pygame.draw.rect(app.screen, (48, 50, 53), rect, 1,
                     border_radius=max(4, int(6 * L.s)))

    # Nombre de la nota pulsada
    if prev_on:
        lbl = f"{app.view.preview_name}  ·  {app.view.preview_label}"
        T.text(app.screen, T.font(L.fs(9), bold=True),
               T.fit(T.font(L.fs(9)), lbl, card.w - int(24 * L.s)), ACCENT,
               (card.centerx, card.bottom - int(6 * L.s)), "midbottom")
