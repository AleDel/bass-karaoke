"""Carga y guardado de la configuración, sin pygame ni ventana.

Antes estas ~90 líneas vivían en ``BassKaraoke._save_config`` /
``_load_config`` y escribían directamente decenas de atributos de la app.
Aquí el fichero JSON se convierte en un :class:`Settings` explícito (con
``MixerState`` dentro) y se valida en un solo sitio, así que se puede probar
con un ``tmp_path`` y reutilizar desde cualquier plataforma.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any

from .config import BPM_DEFAULT, CONFIG_PATH, PITCH_METHODS
from .state import MixerState

log = logging.getLogger(__name__)

SCORE_RENDERERS = ("verovio", "music21")


@dataclass
class Settings:
    """Configuración persistente de la app."""

    bpm: float = float(BPM_DEFAULT)
    mp3_offset_sec: float = 0.0
    song: str = ""
    device_idx: int = 0
    pitch_method: str = "mpm"
    countdown_enabled: bool = True
    score_renderer: str = "verovio"
    gen_barlen: int = 3
    gen_bars_per_chord: int = 2
    mixer: MixerState = field(default_factory=MixerState)
    bpm_map: dict[str, Any] = field(default_factory=dict)
    offset_map: dict[str, Any] = field(default_factory=dict)
    song_start_map: dict[str, Any] = field(default_factory=dict)
    tempo_maps: dict[str, Any] = field(default_factory=dict)


def _as_float(value, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_int(value, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_bool(value, default: bool) -> bool:
    return bool(value) if value is not None else default


def _as_dict(value) -> dict:
    return dict(value) if isinstance(value, dict) else {}


def _clamp01(value) -> float:
    return max(0.0, min(1.0, value))


def parse_settings(cfg: dict, defaults: Settings | None = None, *,
                   device_count: int | None = None,
                   known_songs: list[str] | None = None) -> Settings:
    """Valida un diccionario JSON y devuelve un :class:`Settings`.

    Los valores inválidos caen al valor por defecto en vez de invalidar todo
    el fichero. ``device_count`` y ``known_songs`` permiten descartar índices
    de dispositivo o canciones que ya no existen.
    """
    base = defaults or Settings()
    if not isinstance(cfg, dict):
        return base

    bpm = _as_float(cfg.get("bpm"), base.bpm)
    offset = _as_float(cfg.get("mp3_offset_sec"), base.mp3_offset_sec)

    device_idx = _as_int(cfg.get("device_idx"), base.device_idx)
    if device_count is not None and not (0 <= device_idx < device_count):
        device_idx = base.device_idx

    pitch_method = cfg.get("pitch_method", base.pitch_method)
    if pitch_method not in PITCH_METHODS:
        pitch_method = base.pitch_method

    renderer = cfg.get("score_renderer", base.score_renderer)
    if renderer not in SCORE_RENDERERS:
        renderer = base.score_renderer

    song = cfg.get("song", base.song)
    if not isinstance(song, str):
        song = base.song
    if known_songs is not None and song not in known_songs:
        song = base.song

    m = base.mixer
    mixer = MixerState(
        song_vol=_clamp01(_as_float(cfg.get("mix_song"), m.song_vol)),
        bass_vol=_clamp01(_as_float(cfg.get("mix_bass"), m.bass_vol)),
        band_vol=_clamp01(_as_float(cfg.get("mix_band"), m.band_vol)),
        click_vol=_clamp01(_as_float(cfg.get("mix_click"), m.click_vol)),
        song_muted=_as_bool(cfg.get("muted"), m.song_muted),
        bass_muted=_as_bool(cfg.get("muted_bass"), m.bass_muted),
        band_muted=_as_bool(cfg.get("muted_band"), m.band_muted),
        click_muted=_as_bool(cfg.get("muted_click"), m.click_muted),
    )

    return Settings(
        bpm=bpm,
        mp3_offset_sec=offset,
        song=song,
        device_idx=device_idx,
        pitch_method=pitch_method,
        countdown_enabled=_as_bool(
            cfg.get("countdown_enabled"), base.countdown_enabled),
        score_renderer=renderer,
        gen_barlen=_as_int(cfg.get("gen_barlen"), base.gen_barlen),
        gen_bars_per_chord=_as_int(
            cfg.get("gen_bars_per_chord"), base.gen_bars_per_chord),
        mixer=mixer,
        bpm_map=_as_dict(cfg.get("bpm_map")),
        offset_map=_as_dict(cfg.get("mp3_offset_map")),
        song_start_map=_as_dict(cfg.get("song_start_map")),
        tempo_maps=_as_dict(cfg.get("tempo_maps")),
    )


def settings_to_dict(settings: Settings) -> dict:
    """Serializa :class:`Settings` con el esquema JSON de siempre."""
    m = settings.mixer
    return {
        "bpm":                settings.bpm,
        "bpm_map":            dict(settings.bpm_map),
        "mp3_offset_sec":     settings.mp3_offset_sec,
        "mp3_offset_map":     dict(settings.offset_map),
        "song_start_map":     dict(settings.song_start_map),
        "tempo_maps":         dict(settings.tempo_maps),
        "device_idx":         settings.device_idx,
        "muted":              m.song_muted,
        "mix_song":           round(m.song_vol, 3),
        "mix_bass":           round(m.bass_vol, 3),
        "mix_band":           round(m.band_vol, 3),
        "mix_click":          round(m.click_vol, 3),
        "muted_bass":         m.bass_muted,
        "muted_band":         m.band_muted,
        "muted_click":        m.click_muted,
        "pitch_method":       settings.pitch_method,
        "countdown_enabled":  settings.countdown_enabled,
        "score_renderer":     settings.score_renderer,
        "gen_barlen":         settings.gen_barlen,
        "gen_bars_per_chord": settings.gen_bars_per_chord,
        "song":               settings.song,
    }


def read_settings(path: str = CONFIG_PATH, *,
                  device_count: int | None = None,
                  known_songs: list[str] | None = None) -> Settings:
    """Lee el JSON; si no existe o está roto devuelve los valores por defecto."""
    if not os.path.exists(path):
        return Settings()
    try:
        with open(path, encoding="utf-8") as f:
            cfg = json.load(f)
    except (OSError, ValueError) as exc:
        log.warning(f"[Config WARN] {exc}")
        return Settings()
    return parse_settings(cfg, device_count=device_count,
                          known_songs=known_songs)


def write_settings(settings: Settings, path: str = CONFIG_PATH) -> None:
    """Escribe el JSON (lanza OSError si el destino no se puede escribir)."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(settings_to_dict(settings), f, indent=2)
