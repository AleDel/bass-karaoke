"""Reparto de eventos (bass_karaoke/events/): teclado y ratón.

Son tests de caracterización: fijan qué acción dispara cada tecla y que los
paneles modales tengan prioridad sobre los atajos globales. Se ejecutan sin
ventana: se instancia `BassKaraoke` sin `__init__` y se espían las acciones.
"""
from types import SimpleNamespace

import pygame
import pytest

from bass_karaoke.app import BassKaraoke
from bass_karaoke.config import KARAOKE_Y


def _view():
    return SimpleNamespace(
        tempo_display_mode="bpm", chip_hover="",
        feature_menu_open=False, feature_menu_sel=0,
        device_menu_open=False, device_menu_sel=0,
        pitch_menu_open=False, pitch_menu_sel=0,
        song_menu_open=False, song_menu_sel=0,
        mixer_open=False, mixer_sel=0,
        tuner_open=False, help_open=False,
        neck_map=False, chords_on=True,
        viewport_x=0.0, px_per_16th=10.0,
        _anchor_drag=None, _anchor_drag_mx=0,
        _wave_dragging=False, _wave_drag_mx=0, _wave_drag_off=0.0,
        _wave_drag_start=0.0, _wave_drag_acc=0.0,
        _drag_seeking=False, _drag_start_beat=0.0, _drag_start_mx=0,
    )


class FakeApp(BassKaraoke):
    """BassKaraoke sin ventana ni audio, con las acciones espiadas."""

    def __init__(self):
        self.calls = []
        self.view = _view()
        self.songs = []
        self.song_idx = 0
        self.audio_devices = []
        self.device_idx = 0
        self.gen_running = False
        self.gen_error = ""
        self.gen_notice = False
        self.gen_barlen = 4
        self.chord_edit_open = False
        self.chord_edit_typing = False
        self.chord_edit_buf = ""
        self.chord_edit_sel = 0
        self.chord_edit_msg = ""
        self.chord_edit_dirty = False
        self.chord_bar_typing = False
        self.chord_bar_buf = ""
        self.chord_bar_sugg_cache = []
        self.chord_bar_sugg_idx = -1
        self.chord_bar_replace = False
        self.chord_bar_sel_measure = None
        self.chord_bar_msg = ""
        self.align_editor_open = False
        self.align_cursor_sec = 0.0
        self.align_total_sec = 100.0
        self.training_open = self.lab_open = self.cor_open = self.ear_open = False
        self.tx_open = self.ar_open = self.sc_open = False
        self.chord_events = []
        self.lyric_events = []
        self.countdown_enabled = False
        self.metro_sound = False
        self.pitch_method = "aubio"
        self.beat_time = 0.0
        self.mp3_offset_sec = 0.0
        self.song_start_sec = 0.0
        self._header_chips_layout = lambda: ([], 0)
        self._header_chip_click = lambda pos: False
        self._chord_bar_clear = lambda: self._spy_call("_chord_bar_clear")

    def _spy_call(self, name, *args):
        self.calls.append((name, args))

    def spy(self, *names, ret=None):
        for name in names:
            setattr(self, name, (lambda n, r: lambda *a, **k: (
                self._spy_call(n, *a), r)[1])(name, ret))
        return self

    def key(self, key, unicode=""):
        return self.handle_event(
            pygame.event.Event(pygame.KEYDOWN, key=key, unicode=unicode))


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setattr(pygame.key, "get_mods", lambda: 0)
    return FakeApp().spy(
        "toggle_play", "reiniciar", "toggle_mute", "ajustar_bpm",
        "ajustar_offset", "ajustar_inicio", "_snap_measure",
        "_training_open", "_lab_open", "_cor_open", "_ear_open",
        "_seq_open", "_start_generation", "_chords_from_score",
        "_toggle_chord_editor", "_open_align_editor",
        "_chord_edit_rows", "_chord_edit_apply", "_chord_edit_save",
        "_chord_bar_edit_selected", "_chord_bar_delete",
        "_chord_bar_commit", "_chord_bar_cancel",
        "_close_align_editor", "_align_toggle_play", "_align_adjust_bpm",
        "_align_delete_marker", "_align_reset_marks",
        "_align_keep_cursor_visible", "_seek_to_beat",
    )


# ── salida y teclas globales ────────────────────────────────────────────
def test_quit_devuelve_false(app):
    assert app.handle_event(pygame.event.Event(pygame.QUIT)) is False


def test_evento_desconocido_se_ignora(app):
    assert app.handle_event(pygame.event.Event(pygame.USEREVENT)) is True


def test_escape_en_la_vista_principal_cierra(app):
    assert app.key(pygame.K_ESCAPE) is False


def test_tecla_sin_accion_no_hace_nada(app):
    assert app.key(pygame.K_z) is True
    assert app.calls == []


@pytest.mark.parametrize("key,accion", [
    (pygame.K_SPACE, "toggle_play"),
    (pygame.K_r, "reiniciar"),
    (pygame.K_m, "toggle_mute"),
    (pygame.K_e, "_training_open"),
    (pygame.K_g, "_lab_open"),
    (pygame.K_k, "_cor_open"),
    (pygame.K_o, "_ear_open"),
    (pygame.K_F7, "_start_generation"),
    (pygame.K_F9, "_chords_from_score"),
    (pygame.K_y, "_toggle_chord_editor"),
    (pygame.K_w, "_open_align_editor"),
])
def test_atajos_globales(app, key, accion):
    assert app.key(key) is True
    assert [c[0] for c in app.calls] == [accion]


@pytest.mark.parametrize("key,arg", [
    (pygame.K_UP, 5), (pygame.K_DOWN, -5),
    (pygame.K_LEFT, -1), (pygame.K_RIGHT, 1),
])
def test_tempo_y_compas(app, key, arg):
    app.key(key)
    nombre = "_snap_measure" if abs(arg) == 1 else "ajustar_bpm"
    assert app.calls == [(nombre, (arg,))]


@pytest.mark.parametrize("key,objetivo", [
    (pygame.K_COMMA, "ajustar_offset"),
    (pygame.K_PERIOD, "ajustar_offset"),
    (pygame.K_LEFTBRACKET, "ajustar_inicio"),
    (pygame.K_RIGHTBRACKET, "ajustar_inicio"),
])
@pytest.mark.parametrize("mods,esperado", [
    (0, 0.05), (pygame.KMOD_SHIFT, 0.5), (pygame.KMOD_CTRL, 5.0),
])
def test_los_modificadores_cambian_el_paso(app, monkeypatch, key, objetivo,
                                           mods, esperado):
    monkeypatch.setattr(pygame.key, "get_mods", lambda: mods)
    app.key(key)
    nombre, args = app.calls[0]
    assert nombre == objetivo
    assert abs(abs(args[0]) - esperado) < 1e-9


def test_los_toggles_de_vista_cambian_el_estado(app):
    app.key(pygame.K_b)
    assert app.view.tempo_display_mode == "figura"
    app.key(pygame.K_c)
    app.key(pygame.K_n)
    app.key(pygame.K_h)
    app.key(pygame.K_j)
    assert app.countdown_enabled is True
    assert app.metro_sound is True
    assert app.view.neck_map is True
    assert app.view.chords_on is False


def test_ctrl_s_guarda_config_si_no_hay_acordes_pendientes(app, monkeypatch):
    app.spy("_save_config", "_save_chords")
    monkeypatch.setattr(pygame.key, "get_mods", lambda: pygame.KMOD_CTRL)
    app.key(pygame.K_s)
    assert app.calls == [("_save_config", ())]


def test_ctrl_s_guarda_acordes_si_hay_cambios(app, monkeypatch):
    app.spy("_save_config", "_save_chords", ret=(True, "guardado"))
    app.chord_edit_dirty = True
    monkeypatch.setattr(pygame.key, "get_mods", lambda: pygame.KMOD_CTRL)
    app.key(pygame.K_s)
    assert [c[0] for c in app.calls] == ["_save_chords"]
    assert app.chord_bar_msg == "guardado"


# ── prioridad de los paneles ────────────────────────────────────────────
def test_menu_de_ayuda_tapa_los_atajos(app):
    app.view.help_open = True
    app.key(pygame.K_SPACE)
    assert app.calls == []          # no arranca la reproducción
    assert app.key(pygame.K_ESCAPE) is True
    assert app.view.help_open is False


def test_el_modo_abierto_recibe_la_tecla(app):
    app.training_open = True
    app.spy("_key_training", ret=True)
    app.key(pygame.K_SPACE)
    assert [c[0] for c in app.calls] == ["_key_training"]


def test_el_menu_de_canciones_cambia_la_seleccion(app):
    app.view.song_menu_open = True
    app.songs = [{"name": "a"}, {"name": "b"}]
    app.key(pygame.K_DOWN)
    assert app.view.song_menu_sel == 1


def test_editor_de_acordes_prioritario(app):
    app.chord_edit_open = True
    app.spy("_key_chord_edit_typing", ret=True)
    app.chord_edit_typing = True
    app.key(pygame.K_SPACE)
    assert [c[0] for c in app.calls] == ["_key_chord_edit_typing"]


def test_escribir_acorde_en_la_barra(app):
    app.chord_bar_typing = True
    app.key(pygame.K_a, unicode="A")
    assert app.chord_bar_buf == "A"
    assert app.calls == []          # no dispara atajos


def test_escape_cancela_la_edicion_de_acorde(app):
    app.chord_bar_typing = True
    app.key(pygame.K_ESCAPE)
    assert [c[0] for c in app.calls] == ["_chord_bar_cancel"]


def test_celda_de_acorde_seleccionada_captura_enter_y_supr(app):
    app.chord_bar_sel_measure = 2
    app.key(pygame.K_RETURN)
    app.key(pygame.K_DELETE)
    assert [c[0] for c in app.calls] == ["_chord_bar_edit_selected",
                                         "_chord_bar_delete"]


def test_escape_limpia_la_celda_antes_de_salir(app):
    app.chord_bar_sel_measure = 2
    assert app.key(pygame.K_ESCAPE) is True
    assert [c[0] for c in app.calls] == ["_chord_bar_clear"]


def test_editor_de_alineacion_atrapa_el_teclado(app):
    app.align_editor_open = True
    app.key(pygame.K_SPACE)
    app.key(pygame.K_UP)
    app.key(pygame.K_w)
    assert [c[0] for c in app.calls] == ["_align_toggle_play",
                                         "_align_adjust_bpm",
                                         "_close_align_editor"]


def test_flechas_del_editor_mueven_el_cursor(app, monkeypatch):
    app.align_editor_open = True
    monkeypatch.setattr(pygame.key, "get_mods", lambda: pygame.KMOD_CTRL)
    app.key(pygame.K_RIGHT)
    assert app.align_cursor_sec == 5.0


# ── ratón ───────────────────────────────────────────────────────────────
def test_clic_en_la_tira_de_acordes(app):
    app.spy("_chord_bar_click")
    app.chord_events = [[0, "C"]]
    pos = (100, KARAOKE_Y + 5)
    assert app.handle_event(
        pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=pos)) is True
    assert [c[0] for c in app.calls] == ["_chord_bar_click"]


def test_el_clic_en_la_tira_se_procesa_aunque_haya_un_panel(app):
    """Comportamiento histórico: la tira no mira si hay un panel encima.

    El resto de zonas (onda, mástil, partitura) sí se bloquean con
    `_overlay_open()`; la tira de acordes no. Se deja igual al extraer el
    código, pero queda fijado por si se decide unificar.
    """
    app.spy("_chord_bar_click")
    app.view.help_open = True
    app.chord_events = [[0, "C"]]
    app.handle_event(pygame.event.Event(
        pygame.MOUSEBUTTONDOWN, button=1, pos=(100, KARAOKE_Y + 5)))
    assert [c[0] for c in app.calls] == ["_chord_bar_click"]


def test_soltar_el_boton_corta_el_arrastre(app):
    app.view._drag_seeking = True
    app.handle_event(pygame.event.Event(
        pygame.MOUSEBUTTONUP, button=1, pos=(10, 10)))
    assert app.view._drag_seeking is False


def test_rueda_desplaza_la_seleccion_del_editor(app):
    app.chord_edit_open = True
    app._chord_edit_rows = lambda: [[0, 0], [0, 16], [0, 32]]
    app.chord_edit_sel = 2
    app.handle_event(pygame.event.Event(pygame.MOUSEWHEEL, y=1, x=0))
    assert app.chord_edit_sel == 1


def test_mover_el_raton_marca_el_chip_bajo_el_cursor(app):
    app.view.chip_hover = "algo"
    app.handle_event(pygame.event.Event(
        pygame.MOUSEMOTION, pos=(10, 10), rel=(0, 0), buttons=(0, 0, 0)))
    assert app.view.chip_hover == ""      # sin chips, se limpia el hover
