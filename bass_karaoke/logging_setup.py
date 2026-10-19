"""Configuración central de logging para Bass Karaoke.

Un único punto de entrada (`setup_logging`) instala:
  · consola (nivel INFO por defecto, formato compacto),
  · fichero rotativo en ``logs/bass_karaoke.log`` (nivel DEBUG),
  · silenciado de librerías ruidosas (librosa/numba/torch/…).

El nivel de consola se puede subir/bajar con la variable de entorno
``BK_LOG_LEVEL`` (p. ej. ``BK_LOG_LEVEL=DEBUG``). Es idempotente: llamarla
varias veces no duplica handlers.
"""
from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

_ROOT_NAME = "bass_karaoke"
_CONSOLE_FMT = "%(levelname)-7s %(name)s: %(message)s"
_FILE_FMT = "%(asctime)s %(levelname)-7s %(name)s:%(lineno)d — %(message)s"
_MAX_BYTES = 2 * 1024 * 1024
_BACKUPS = 3

_NOISY = (
    "librosa",
    "numba",
    "matplotlib",
    "PIL",
    "torch",
    "tensorflow",
    "urllib3",
    "httpx",
    "numba.core",
)


def _log_dir() -> Path:
    """Carpeta de logs junto a la config (raíz del proyecto o del .exe)."""
    try:
        from .config import CONFIG_PATH

        return Path(CONFIG_PATH).parent / "logs"
    except Exception:
        return Path.cwd() / "logs"


def _level_from_env(default: int = logging.INFO) -> int:
    raw = os.environ.get("BK_LOG_LEVEL", "").strip().upper()
    if not raw:
        return default
    return getattr(logging, raw, default)


def setup_logging(level: int | None = None, log_to_file: bool = True) -> logging.Logger:
    """Instala los handlers una sola vez y devuelve el logger raíz del paquete."""
    logger = logging.getLogger(_ROOT_NAME)
    if getattr(logger, "_bk_configured", False):
        return logger

    console_level = level if level is not None else _level_from_env()
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    console = logging.StreamHandler()
    console.setLevel(console_level)
    console.setFormatter(logging.Formatter(_CONSOLE_FMT))
    logger.addHandler(console)

    if log_to_file:
        try:
            directory = _log_dir()
            directory.mkdir(parents=True, exist_ok=True)
            file_handler = RotatingFileHandler(
                directory / "bass_karaoke.log",
                maxBytes=_MAX_BYTES,
                backupCount=_BACKUPS,
                encoding="utf-8",
            )
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(logging.Formatter(_FILE_FMT))
            logger.addHandler(file_handler)
        except OSError as exc:  # disco lleno, permisos, ruta de solo lectura…
            logger.warning("no se pudo abrir el log en fichero: %s", exc)

    for name in _NOISY:
        logging.getLogger(name).setLevel(logging.WARNING)

    logger._bk_configured = True  # type: ignore[attr-defined]
    logger.debug("logging inicializado (consola=%s)", logging.getLevelName(console_level))
    return logger


def get_logger(name: str) -> logging.Logger:
    """Logger hijo del paquete, con el nombre normalizado."""
    if name.startswith(_ROOT_NAME + "."):
        return logging.getLogger(name)
    return logging.getLogger(f"{_ROOT_NAME}.{name}")
