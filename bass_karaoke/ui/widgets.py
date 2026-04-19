"""
Widgets de bajo nivel reutilizables: piano, etc.
"""
import pygame

from ..config import _IS_BLACK_KEY


def build_piano_keys(start_midi: int, end_midi: int,
                     px: int, py: int, pw: int, ph: int) -> list:
    """
    Construye la lista de teclas del piano para el rango MIDI dado.

    Devuelve lista de dicts {midi, black, rect}.
    Las teclas blancas van primero, las negras al final (para dibujarlas encima).
    """
    white_count = sum(1 for m in range(start_midi, end_midi + 1)
                      if not _IS_BLACK_KEY[m % 12])
    if white_count == 0:
        return []

    ww = pw / white_count
    bw = max(5, ww * 0.58)
    wh = ph - 4
    bh = int(ph * 0.62)

    white_x = {}
    wi = 0
    for midi in range(start_midi, end_midi + 1):
        if not _IS_BLACK_KEY[midi % 12]:
            white_x[midi] = px + wi * ww
            wi += 1

    keys_white = []
    keys_black = []

    for midi in range(start_midi, end_midi + 1):
        s = midi % 12
        if not _IS_BLACK_KEY[s]:
            keys_white.append({
                "midi": midi, "black": False,
                "rect": pygame.Rect(int(white_x[midi]), py + 2,
                                    max(1, int(ww) - 1), wh),
            })
        else:
            left_white = midi - 1
            if left_white in white_x:
                bx = white_x[left_white] + ww * 0.65 - bw / 2
                keys_black.append({
                    "midi": midi, "black": True,
                    "rect": pygame.Rect(int(bx), py + 2, max(1, int(bw)), bh),
                })

    return keys_white + keys_black
