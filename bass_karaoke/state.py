"""Estado de la app agrupado en dataclasses explícitas.

``BassKaraoke`` acumulaba cientos de atributos sueltos y cada ``draw_*`` o
mixin leía lo que quería con ``getattr(app, "chord_bar_sel_measure", None)``.
Aquí el estado se agrupa por responsabilidad (barra de acordes, editor de
acordes, editor de alineación, generación de partitura, mixer, pitch,
reproducción…) para que:

* cada grupo tenga un único sitio donde ver sus campos y sus valores por defecto;
* las funciones de dibujo/lógica puedan recibir SOLO el grupo que necesitan
  (``draw_x(app.chord_bar_state)``) en vez de la app entera;
* los tests puedan construir un grupo sin ventana, audio ni pygame.

Compatibilidad: el decorador :func:`with_state` mantiene los nombres antiguos
(``app.chord_bar_sel_measure``) como propiedades que leen/escriben el campo
del grupo, así que el código existente (mixins, ``ui/``, tests con
``FakeApp(BassKaraoke)`` sin ``__init__``) sigue funcionando sin cambios. El
grupo se crea de forma perezosa, por eso un ``FakeApp`` que no llama a
``BassKaraoke.__init__`` también obtiene los valores por defecto.

El nombre antiguo de cada campo es ``prefix + campo``, salvo que el grupo
declare ``rename={campo: nombre_antiguo}`` (útil cuando los atributos
originales no comparten prefijo, como ``mix_song`` y ``muted``).
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import Any, NamedTuple

from .config import BPM_DEFAULT

# ══════════════════════════════════════════════════════════════════════════
#  Grupos de estado
# ══════════════════════════════════════════════════════════════════════════


@dataclass
class ChordBarState:
    """Edición de acordes sobre la tira de compases (clic en la barra)."""

    sel_measure: int | None = None      # compás seleccionado
    typing: bool = False
    buf: str = ""
    target_sec: float | None = None     # inicio del compás editado
    target_end_sec: float | None = None  # inicio del siguiente compás
    msg: str = ""
    sugg_idx: int = -1                  # fila resaltada del desplegable
    sugg_cache: list = field(default_factory=list)  # sugerencias mostradas
    replace: bool = False               # el próximo carácter sustituye


@dataclass
class ChordEditState:
    """Editor modal de acordes (tecla Y)."""

    open: bool = False
    sel: int = 0
    top: int = 0
    typing: bool = False
    buf: str = ""
    msg: str = ""
    dirty: bool = False


@dataclass
class AlignEditorState:
    """Editor de alineación del MP3 con waveform (tecla W)."""

    editor_open: bool = False
    wave: Any = None                    # (col_min, col_max) normalizados a ±1
    wave_n: int = 0
    total_sec: float = 0.0
    view_start: float = 0.0             # ventana visible (zoom/pan), en segundos
    view_span: float = 0.0
    cursor_sec: float = 0.0
    dragging: bool = False              # arrastrando el offset (inicio bajo)
    dragging_start: bool = False        # arrastrando el inicio de canción
    drag_marker: Any = None             # start16 de la marca de tempo arrastrada
    panning: bool = False               # arrastrando con botón central (pan)
    pan_start: tuple = (0, 0)
    pan_view_start: float = 0.0
    playing: bool = False               # reproducción natural del MP3 en el editor
    detecting: bool = False             # análisis librosa en curso
    detected_tempo: Any = None
    onsets: Any = None                  # ticks de onsets (segundos)


@dataclass
class GenerationState:
    """Generación de partitura para canciones solo-audio o .sng (F7)."""

    running: bool = False
    msg: str = ""
    frac: float = 0.0
    result: Any = None
    error: str = ""
    notice: bool = False
    song_dir: Any = None
    from_sng: bool = False
    barlen: int = 3
    bars_per_chord: int = 2


@dataclass
class MixerState:
    """Volúmenes y mutes del mixer (F2): canción / bajo / banda / metrónomo.

    Los atributos antiguos no comparten prefijo (``mix_song``, ``muted``…),
    por eso el grupo se registra con ``rename=MIXER_RENAME``.
    """

    song_vol: float = 1.0     # mix_song:   volumen de la canción (MP3)
    bass_vol: float = 0.6     # mix_bass:   volumen de la línea de bajo
    band_vol: float = 0.6     # mix_band:   volumen de la banda
    click_vol: float = 1.0    # mix_click:  volumen del metrónomo
    song_muted: bool = False  # muted:      mute de la pista Canción
    bass_muted: bool = False  # muted_bass
    band_muted: bool = False  # muted_band
    click_muted: bool = False  # muted_click


MIXER_RENAME = {
    "song_vol": "mix_song", "bass_vol": "mix_bass",
    "band_vol": "mix_band", "click_vol": "mix_click",
    "song_muted": "muted", "bass_muted": "muted_bass",
    "band_muted": "muted_band", "click_muted": "muted_click",
}


@dataclass
class PitchState:
    """Resultado del detector de pitch y su comparación con la nota actual."""

    detected_hz: float = 0.0
    detected_note: str = "—"
    stable_hz: float = 0.0
    stable_note: str = "—"
    note_match: bool | None = None            # True/False/None (esperando)
    detected_fret_str: tuple | None = None    # (traste, cuerda) o None


@dataclass
class HitTimingState:
    """Indicador de timing de la última nota acertada (TARDE/ANTES/OK)."""

    last_hit_delta16: float = 0.0
    last_hit_note_idx: int = -1
    last_hit_alpha: float = 0.0


@dataclass
class CountdownState:
    """Cuenta atrás 4-3-2-1 antes de empezar a tocar."""

    counting_down: bool = False
    countdown_beat: int = 4
    countdown_timer: float = 0.0
    countdown_enabled: bool = True


@dataclass
class PlaybackState:
    """Posición de reproducción, tempo, puntuación y anclas del MP3."""

    bpm: float = BPM_DEFAULT
    playing: bool = False
    note_idx: int = 0
    beat_time: float = 0.0
    score_ok: int = 0
    score_total: int = 0
    mp3_offset_sec: float = 0.0
    song_start_sec: float = 0.0


# ══════════════════════════════════════════════════════════════════════════
#  Delegación: app.<nombre antiguo>  ->  app.<grupo>_state.<campo>
# ══════════════════════════════════════════════════════════════════════════


class StateGroup(NamedTuple):
    """Un grupo: nombre, dataclass, prefijo y renombres opcionales."""

    name: str
    state_cls: type
    prefix: str = ""
    rename: dict | None = None   # {campo: nombre antiguo del atributo}


def _make_field_property(group: str, state_cls: type, field_name: str) -> property:
    key = f"_state_{group}"

    def _state(obj):
        st = obj.__dict__.get(key)
        if st is None:
            st = obj.__dict__[key] = state_cls()
        return st

    def getter(self):
        return getattr(_state(self), field_name)

    def setter(self, value):
        setattr(_state(self), field_name, value)

    return property(getter, setter, doc=f"Delegado en {state_cls.__name__}.{field_name}")


def _make_group_property(group: str, state_cls: type) -> property:
    key = f"_state_{group}"

    def getter(self):
        st = self.__dict__.get(key)
        if st is None:
            st = self.__dict__[key] = state_cls()
        return st

    def setter(self, value):
        self.__dict__[key] = value

    return property(getter, setter, doc=f"Instancia de {state_cls.__name__}")


def legacy_names(group: StateGroup) -> list[str]:
    """Nombres antiguos (``app.xxx``) que un grupo expone como propiedades."""
    rename = group.rename or {}
    return [rename.get(f.name, f"{group.prefix}{f.name}")
            for f in dataclasses.fields(group.state_cls)]


def with_state(*groups: StateGroup):
    """Decorador de clase: expone cada grupo y sus campos como propiedades.

    Por cada ``StateGroup("chord_bar", ChordBarState, "chord_bar_")`` añade:

    * ``cls.chord_bar_state``: la instancia de ``ChordBarState`` (perezosa);
    * ``cls.chord_bar_<campo>`` por cada campo: propiedad de lectura/escritura.

    Falla al importar si algún nombre ya existe en la clase (o en sus mixins):
    así una colisión se detecta al arrancar y no como un bug silencioso.
    """

    def decorate(cls):
        def _add(name: str, prop: property) -> None:
            if hasattr(cls, name):
                raise RuntimeError(
                    f"with_state: {cls.__name__}.{name} ya existe; "
                    "renombra el campo o el atributo en conflicto")
            setattr(cls, name, prop)

        for g in groups:
            _add(f"{g.name}_state", _make_group_property(g.name, g.state_cls))
            rename = g.rename or {}
            for f in dataclasses.fields(g.state_cls):
                legacy = rename.get(f.name, f"{g.prefix}{f.name}")
                _add(legacy, _make_field_property(g.name, g.state_cls, f.name))
        return cls

    return decorate
