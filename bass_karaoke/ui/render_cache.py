"""Caché de superficies pequeñas que no cambian entre frames.

``draw_tab`` creaba cada frame una superficie SRCALPHA para cada halo, línea
de duración y texto (nombres de cuerda, compases, secciones, trastes…). A 60
FPS eso son cientos de asignaciones por segundo. Aquí se reutilizan por clave
(fuente/texto/color o radio/color/alfa) con un tope para no crecer sin límite.
"""
from __future__ import annotations

import pygame

_TEXT_CACHE: dict = {}
_TEXT_CACHE_MAX = 2048

_HALO_CACHE: dict = {}
_HALO_CACHE_MAX = 256

_LINE_CACHE: dict = {}
_LINE_CACHE_MAX = 512


def _rgb(color) -> tuple:
    return tuple(color[:3])


def render_text(font, text: str, color):
    """``font.render`` cacheado. La superficie devuelta no debe mutarse."""
    key = (font, text, _rgb(color))
    surf = _TEXT_CACHE.get(key)
    if surf is None:
        if len(_TEXT_CACHE) >= _TEXT_CACHE_MAX:
            _TEXT_CACHE.clear()
        surf = font.render(text, True, color)
        _TEXT_CACHE[key] = surf
    return surf


def halo(radius: int, color, alpha: int) -> pygame.Surface:
    """Círculo relleno con alfa, centrado en ``radius``."""
    key = (int(radius), _rgb(color), int(alpha))
    surf = _HALO_CACHE.get(key)
    if surf is None:
        if len(_HALO_CACHE) >= _HALO_CACHE_MAX:
            _HALO_CACHE.clear()
        r = int(radius)
        surf = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
        pygame.draw.circle(surf, (*_rgb(color), int(alpha)), (r, r), r)
        _HALO_CACHE[key] = surf
    return surf


def alpha_line(width: int, height: int, color, alpha: int,
               thickness: int = 3) -> pygame.Surface:
    """Línea horizontal centrada verticalmente, con alfa."""
    key = (int(width), int(height), _rgb(color), int(alpha), int(thickness))
    surf = _LINE_CACHE.get(key)
    if surf is None:
        if len(_LINE_CACHE) >= _LINE_CACHE_MAX:
            _LINE_CACHE.clear()
        w, h = max(1, int(width)), max(1, int(height))
        surf = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.line(surf, (*_rgb(color), int(alpha)),
                         (0, h // 2), (w, h // 2), int(thickness))
        _LINE_CACHE[key] = surf
    return surf


def reset_caches() -> None:
    """Vacía las cachés (tests o cambio de fuentes)."""
    _TEXT_CACHE.clear()
    _HALO_CACHE.clear()
    _LINE_CACHE.clear()
