"""bass_karaoke package — exports públicos (carga perezosa).

Importar un submódulo puro (``bass_karaoke.parser``, ``bass_karaoke.walking``…)
NO debe arrastrar pygame, audio ni el renderizador de partitura. Por eso los
exports de conveniencia (``BassKaraoke``, ``main``) se resuelven bajo demanda
con ``__getattr__`` (PEP 562) en vez de importarse en el nivel del paquete.
"""
from __future__ import annotations

__all__ = ["BassKaraoke", "main"]

_LAZY = {
    "BassKaraoke": ("bass_karaoke.app", "BassKaraoke"),
    "main": ("bass_karaoke.main", "main"),
}


def __getattr__(name: str):
    if name in _LAZY:
        import importlib

        module_name, attr = _LAZY[name]
        module = importlib.import_module(module_name)
        value = getattr(module, attr)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__():
    return sorted([*globals(), *_LAZY])
