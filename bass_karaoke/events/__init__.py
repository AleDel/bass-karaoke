"""Eventos de entrada de Bass Karaoke, separados por dispositivo.

`app.handle_event` queda como reparto por tipo de evento y delega aquí:
`KeyboardMixin` interpreta el teclado y `MouseMixin` el ratón y la rueda.

Protocolo de los handlers de modal: devuelven ``True``/``False`` si el panel
estaba abierto y consumió el evento (``False`` = salir), y ``None`` si no
aplican, para que siga la cadena.
"""
from .keyboard import KeyboardMixin
from .mouse import MouseMixin

__all__ = ["KeyboardMixin", "MouseMixin"]
