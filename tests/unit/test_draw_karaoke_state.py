"""draw_chord_editor_popup lee del grupo ChordBarState (sin app completa)."""
from types import SimpleNamespace

import pygame
import pytest

from bass_karaoke.config import C_ACCENT, C_DGRAY
from bass_karaoke.state import ChordBarState
from bass_karaoke.ui import draw_karaoke


@pytest.fixture(scope="module", autouse=True)
def _font():
    pygame.font.init()
    yield


def _app(bar, rects):
    return SimpleNamespace(
        chord_bar_state=bar,
        screen=pygame.Surface((200, 100)),
        font_small=pygame.font.Font(None, 15),
        chord_bar_sugg_layout=lambda: rects,
    )


def test_sin_escribir_no_dibuja_nada():
    rects = [("Am", pygame.Rect(10, 10, 60, 20))]
    app = _app(ChordBarState(typing=False), rects)
    before = pygame.image.tobytes(app.screen, "RGB")
    draw_karaoke.draw_chord_editor_popup(app)
    assert pygame.image.tobytes(app.screen, "RGB") == before


def test_la_fila_seleccionada_usa_el_color_de_acento():
    rects = [("Am", pygame.Rect(10, 10, 60, 20)),
             ("Am7", pygame.Rect(10, 40, 60, 20))]
    app = _app(ChordBarState(typing=True, sugg_idx=0), rects)
    draw_karaoke.draw_chord_editor_popup(app)
    top_mid_sel = app.screen.get_at((40, 10))[:3]
    top_mid_other = app.screen.get_at((40, 40))[:3]
    assert top_mid_sel == tuple(C_ACCENT)
    assert top_mid_other == tuple(C_DGRAY)
