"""Estado de presentación de la UI, separado de la lógica de audio/canción.

``BassKaraoke`` conserva el estado del dominio (canción, reproducción, pitch,
generación…) y delega en ``self.view`` todo lo que solo afecta a cómo se ve o
se navega la interfaz: zoom/scroll, modales y menús, selección visual, caches
de render y realimentación (preview/arrastres). Así los módulos ``ui/`` leen
``app.view.*`` y queda explícito que no tocan lógica musical.
"""
from dataclasses import dataclass, field
from typing import Any

from .config import PITCH_METHODS


@dataclass
class ViewState:
    """Estado efímero de la vista (no se persiste en configuración)."""

    # ── Zoom y desplazamiento horizontal ────────────────────────────────
    px_per_16th: int = 30
    viewport_x: float = 0.0
    target_x: float = 0.0

    # ── Opciones de visualización ───────────────────────────────────────
    tempo_display_mode: str = "figura"
    neck_map: bool = False
    chords_on: bool = True

    # ── Modales y menús ─────────────────────────────────────────────────
    tuner_open: bool = False
    help_open: bool = False
    device_menu_open: bool = False
    device_menu_sel: int = 0
    pitch_menu_open: bool = False
    pitch_menu_sel: int = PITCH_METHODS.index("crepe-tiny")
    feature_menu_open: bool = False
    feature_menu_sel: int = 0
    song_menu_open: bool = False
    song_menu_sel: int = 0
    mixer_open: bool = False
    mixer_sel: int = 0

    # ── Arrastre de la onda / búsqueda ──────────────────────────────────
    _wave_dragging: bool = False
    _wave_drag_mx: int = 0
    _wave_drag_off: float = 0.0
    _wave_drag_start: float = 0.0
    _wave_drag_acc: float = 0.0
    _anchor_drag: str | None = None      # "bass" | "start" | None
    _anchor_drag_mx: int = 0
    _drag_seeking: bool = False
    _drag_start_beat: float = 0.0
    _drag_start_mx: int = 0

    # ── Chips clicables de la cabecera ──────────────────────────────────
    chip_hover: str = ""

    # ── Realimentación visual (preview de nota/cuerda) ──────────────────
    preview_hz: float = 0.0
    preview_name: str = "—"
    preview_label: str = ""
    preview_timer: float = 0.0
    preview_fret_str: tuple[int, int] | None = None
    preview_midi: int | None = None
    _preview_sound: Any = None

    # ── Cache de la partitura renderizada ───────────────────────────────
    _score_loading: bool = False
    _score_surf: Any = None
    _score_note_xs: list = field(default_factory=list)
    _score_scroll_x: float = 0.0
    _score_cache: dict = field(default_factory=dict)
    _score_total16: int = 1
