"""Smoke test del header (app.py) sin ventana.

`_draw_header` mezcla estado y pintado: comprobamos que dibuja con y sin
varispeed y que el subtítulo cambia. Se pinta sobre un Surface normal, así que
no hace falta `pygame.display` (solo `font.init`).
"""
import pygame
import pytest

from bass_karaoke.app import BassKaraoke
from bass_karaoke.config import HEADER_H, W


@pytest.fixture(autouse=True, scope="module")
def _fonts():
    pygame.font.init()
    yield


class FakeView:
    tempo_display_mode = "bpm"
    chip_hover = None


class FakeVsp:
    loaded = False
    stretching = False


class FakeApp(BassKaraoke):
    """BassKaraoke sin __init__: solo el estado que usa el header."""

    def __init__(self, ratio):
        self._ratio = ratio
        self.screen = pygame.Surface((W, HEADER_H))
        self.view = FakeView()
        self.tempo_map = [(0, 120, "quarter")]
        self.score_total = 0
        self.score_ok = 0
        self.song_name = "test"
        self.playing = False
        self.mp3_offset_sec = 0.0
        self._vsp = FakeVsp()
        self.pitch_engine = "aubio"
        self.countdown_enabled = True
        self.metro_sound = False
        self.muted = False
        self.muted_bass = False
        self.muted_band = False
        self.font_tiny = pygame.font.Font(None, 14)
        self.font_med = pygame.font.Font(None, 18)
        self.font_title = pygame.font.Font(None, 20)

    def _speed_ratio(self):
        return self._ratio


def _pixels(app):
    return pygame.surfarray.array3d(app.screen).tobytes()


def test_dibuja_a_tempo_original():
    app = FakeApp(1.0)
    app._draw_header()
    assert app.screen.get_at((0, 0))[3] == 255      # el header se pintó


def test_el_subtitulo_cambia_al_estirar_el_tempo():
    original, estirado = FakeApp(1.0), FakeApp(1.25)
    original._draw_header()
    estirado._draw_header()
    assert _pixels(original) != _pixels(estirado)


def test_vsp_cargado_anade_el_factor_de_velocidad():
    quieto, sonando = FakeApp(1.0), FakeApp(1.0)
    sonando._vsp.loaded = True
    quieto._draw_header()
    sonando._draw_header()
    assert _pixels(quieto) != _pixels(sonando)
