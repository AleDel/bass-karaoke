"""
Pentagrama en clave de fa — dibujo puro con pygame (sin estado).

draw_mini_staff(app, x, y, w, midi) pinta un pentagrama pequeño con la
nota MIDI indicada (o un silencio si midi es None). Las líneas, de abajo
a arriba: Sol2–Si2–Re3–Fa3–La3. Incluye sostenidos y líneas auxiliares.
"""
import pygame

from ..config import C_DGRAY, C_GRAY, C_WHITE

_LINE_SP = 11          # píxeles entre líneas
_LEDGER = 16          # semiancho de línea auxiliar / nota
_PC_DEG = {0: 0, 2: 1, 4: 2, 5: 3, 7: 4, 9: 5, 11: 6}  # C D E F G A B
_PC_SHARP = {1, 3, 6, 8, 10}

# MIDI de la línea inferior (Sol2)
_BOTTOM_MIDI = 43


def _dia(midi: int) -> tuple:
    """(índice diatónico absoluto, es_sostenido) para un MIDI."""
    midi = int(midi)
    pc = midi % 12
    octv = midi // 12 - 1
    if pc in _PC_SHARP:
        return octv * 7 + _PC_DEG[pc - 1], True
    return octv * 7 + _PC_DEG[pc], False


def staff_height(px_above: int = 3, px_below: int = 3) -> int:
    """Alto total necesario (líneas + auxiliares + etiquetas)."""
    return int(4 * _LINE_SP + (px_above + px_below) * _LINE_SP + 26)


def draw_mini_staff(app, x: int, y: int, w: int, midi,
                    label: str = "clave de fa") -> int:
    """Dibuja el pentagrama en (x, y). Devuelve el alto ocupado.

    midi=None → pentagrama vacío con interrogante (nota oculta).
    """
    half = _LINE_SP / 2.0
    # Reservamos 3 auxiliares arriba y abajo
    top_y = y + 3 * _LINE_SP + 6
    bot_y = top_y + 4 * _LINE_SP
    base_dia = _dia(_BOTTOM_MIDI)[0]

    pygame.draw.rect(app.screen, (16, 16, 28), (x, y, w,
                     staff_height()))
    for i in range(5):
        ly = top_y + i * _LINE_SP
        pygame.draw.line(app.screen, C_DGRAY,
                         (x + 8, ly), (x + w - 8, ly), 1)
    # Dos puntos de la clave de fa alrededor de la línea de Fa3 (4ª línea)
    fa_y = top_y + 3 * _LINE_SP
    pygame.draw.circle(app.screen, C_GRAY, (x + 16, int(fa_y - 6)), 2)
    pygame.draw.circle(app.screen, C_GRAY, (x + 16, int(fa_y + 6)), 2)

    if midi is None:
        q = app.font_big.render("?", True, C_GRAY)
        app.screen.blit(q, (x + w // 2 - q.get_width() // 2,
                            top_y - 6))
    else:
        dia, sharp = _dia(midi)
        ny = bot_y - (dia - base_dia) * half
        # Líneas auxiliares: pares de pasos diatónicos más allá del
        # pentagrama (arriba desde base+10, abajo desde base-2).
        grown = 0
        L = base_dia + 10
        while L <= dia and grown < 8:
            ly = bot_y - (L - base_dia) * half
            pygame.draw.line(app.screen, C_GRAY,
                             (x + w // 2 - _LEDGER, ly),
                             (x + w // 2 + _LEDGER, ly), 1)
            L += 2
            grown += 1
        L = base_dia - 2
        while L >= dia and grown < 8:
            ly = bot_y - (L - base_dia) * half
            pygame.draw.line(app.screen, C_GRAY,
                             (x + w // 2 - _LEDGER, ly),
                             (x + w // 2 + _LEDGER, ly), 1)
            L -= 2
            grown += 1
        if sharp:
            acc = app.font_med.render("#", True, C_WHITE)
            app.screen.blit(acc, (x + w // 2 - _LEDGER - 16, ny - 12))
        pygame.draw.ellipse(app.screen, C_WHITE,
                            (x + w // 2 - 8, ny - 6, 16, 12))
        # Plica: arriba si la nota está bajo la mitad, abajo si no
        mid_y = top_y + 2 * _LINE_SP
        if ny >= mid_y:
            pygame.draw.line(app.screen, C_WHITE,
                             (x + w // 2 + 7, ny - 5),
                             (x + w // 2 + 7, ny - 38), 2)
        else:
            pygame.draw.line(app.screen, C_WHITE,
                             (x + w // 2 - 7, ny + 5),
                             (x + w // 2 - 7, ny + 38), 2)

    lbl = app.font_tiny.render(label, True, C_GRAY)
    app.screen.blit(lbl, (x + 4, y + staff_height() - 16))
    return staff_height()
