"""Caché de superficies de texto/halos/líneas (sin ventana)."""
import pygame
import pytest

from bass_karaoke.ui.render_cache import (
    alpha_line,
    halo,
    render_text,
    reset_caches,
)


@pytest.fixture(autouse=True)
def _clean_caches():
    pygame.font.init()
    reset_caches()
    yield
    reset_caches()


def test_render_text_reuses_the_same_surface():
    font = pygame.font.Font(None, 16)

    first = render_text(font, "A1", (255, 200, 70))
    second = render_text(font, "A1", (255, 200, 70))
    other = render_text(font, "A1", (80, 185, 255))

    assert first is second
    assert first is not other
    assert first.get_size() == second.get_size()


def test_halo_size_and_alpha_are_cached():
    first = halo(7, (50, 230, 110), 45)
    second = halo(7, (50, 230, 110), 45)
    bigger = halo(9, (50, 230, 110), 45)

    assert first is second
    assert first is not bigger
    assert first.get_size() == (14, 14)
    assert bigger.get_size() == (18, 18)
    assert first.get_at((7, 7))[3] == 45


def test_alpha_line_size_and_alpha():
    line = alpha_line(40, 3, (255, 90, 90), 90)

    assert line.get_size() == (40, 3)
    assert line.get_at((20, 1))[3] == 90
    assert alpha_line(40, 3, (255, 90, 90), 90) is line


def test_reset_caches_forces_new_surfaces():
    before = halo(5, (255, 70, 70), 200)
    reset_caches()
    after = halo(5, (255, 70, 70), 200)

    assert before is not after
    assert before.get_size() == after.get_size()
