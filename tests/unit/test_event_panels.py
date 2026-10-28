"""Paneles del teclado y zonas del ratón (bass_karaoke/events/).

Complementa `test_event_dispatch.py`: aquí se recorren los menús (I, D, P, L,
F2), el editor de acordes (Y), la barra de acordes y el editor de alineación
(W), más cada zona del ratón. Todo sin ventana.
"""
from types import SimpleNamespace

import pygame
import pytest

from bass_karaoke.app import BassKaraoke
from bass_karaoke.config import (
    KARAOKE_Y,
    NECK_Y,
    PITCH_METHODS,
    TAB_Y,
    WAVEFORM_Y,
    W,
)


def _view():
    return SimpleNamespace(
        tempo_display_mode="bpm", chip_hover="",
        feature_menu_open=False, feature_menu_sel=0,
        device_menu_open=False, device_menu_sel=0,
        pitch_menu_open=False, pitch_menu_sel=0,
        song_menu_open=False, song_menu_sel=0,
        mixer_open=False, mixer_sel=0,
        tuner_open=False, help_open=False,
        neck_map=False, chords_on=True, viewport_x=0.0, px_per_16th=10.0,
        _anchor_drag=None, _anchor_drag_mx=0, _wave_dragging=False,
        _wave_drag_mx=0, _wave_drag_off=0.0, _wave_drag_start=0.0,
        _wave_drag_acc=0.0, _drag_seeking=False, _drag_start_beat=0.0,
        _drag_start_mx=0,
    )


class FakeApp(BassKaraoke):
    """BassKaraoke sin ventana, con acciones espiadas y estado mínimo."""

    def __init__(self):
        self.calls = []
        self.view = _view()
        self.rows = [[i, i * 16] for i in range(30)]
        self.songs = [{"name": "a"}, {"name": "b"}, {"name": "c"}]
        self.song_idx = 0
        self.audio_devices = ["dev0", "dev1"]
        self.device_idx = 1
        self.pitch_method = "aubio"
        self.gen_running = False
        self.gen_error = ""
        self.gen_notice = False
        self.feature_msg = []
        self.feature_log = []
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
        self.align_dragging = False
        self.align_dragging_start = False
        self.align_drag_marker = None
        self.align_panning = False
        self.align_pan_start = (0, 0)
        self.align_view_start = 0.0
        self.training_open = self.lab_open = self.cor_open = self.ear_open = False
        self.tx_open = self.ar_open = self.sc_open = False
        self.chord_events = []
        self.lyric_events = []
        self.beat_time = 0.0
        self.mp3_offset_sec = 0.0
        self.song_start_sec = 0.0
        self.countdown_enabled = False
        self.metro_sound = False
        self.song_wave = None

        # stubs de apoyo (los tests los sustituyen cuando importa el detalle)
        self._chord_edit_rows = lambda: self.rows
        self._header_chips_layout = lambda: ([], 0)
        self._header_chip_click = lambda pos: False
        self._chord_bar_clear = lambda: None
        self._chord_bar_commit = lambda: None
        self._chord_bar_cancel = lambda: None
        self._piano_hit = lambda pos: None
        self._neck_hit = lambda pos: None
        self._seek_to_beat = lambda b: None
        self._remember_anchors = lambda: None
        self._clamp_anchors = lambda: None
        self._tempo_at = lambda s16: 120.0
        self._lead_qpm = lambda: 120.0
        self._bass_start16 = lambda: 0
        self.px_of = lambda s16: 0.0

    def rec(self, name, *args):
        self.calls.append((name, args))

    def spy(self, *names, ret=None):
        for name in names:
            setattr(self, name, (lambda n, r: lambda *a, **k: (
                self.rec(n, *a), r)[1])(name, ret))
        return self

    def names(self):
        return [c[0] for c in self.calls]

    def key(self, k, unicode=""):
        return self.handle_event(
            pygame.event.Event(pygame.KEYDOWN, key=k, unicode=unicode))

    def down(self, pos, button=1):
        return self.handle_event(
            pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=button, pos=pos))

    def up(self, pos=(0, 0), button=1):
        return self.handle_event(
            pygame.event.Event(pygame.MOUSEBUTTONUP, button=button, pos=pos))

    def wheel(self, y, pos=(10, 10)):
        event = pygame.event.Event(pygame.MOUSEWHEEL, x=0, y=y)
        event.pos = pos
        return self.handle_event(event)

    def move(self, pos):
        return self.handle_event(pygame.event.Event(
            pygame.MOUSEMOTION, pos=pos, rel=(0, 0), buttons=(0, 0, 0)))


@pytest.fixture(autouse=True)
def _mods(monkeypatch):
    monkeypatch.setattr(pygame.key, "get_mods", lambda: 0)


@pytest.fixture
def app():
    return FakeApp()


# ── menús ───────────────────────────────────────────────────────────────
def test_menu_de_funcionalidades_recorre_y_alterna(app):
    app.view.feature_menu_open = True
    app.spy("_feature_toggle")
    app.key(pygame.K_DOWN)
    assert app.view.feature_menu_sel == 1
    app.key(pygame.K_UP)
    assert app.view.feature_menu_sel == 0
    app.key(pygame.K_UP)                    # se queda en el primero
    assert app.view.feature_menu_sel == 0
    app.key(pygame.K_RETURN)
    assert app.names() == ["_feature_toggle"]
    app.key(pygame.K_i)
    assert app.view.feature_menu_open is False


def test_menu_de_dispositivos_arranca_el_elegido(app):
    app.view.device_menu_open = True
    app.view.device_menu_sel = 1
    app.spy("_start_audio")
    app.key(pygame.K_RETURN)
    assert app.calls == [("_start_audio", (1,))]
    assert app.view.device_menu_open is False


def test_menu_de_pitch_cambia_el_metodo_y_reinicia_audio(app):
    app.view.pitch_menu_open = True
    app.view.pitch_menu_sel = 0
    app.spy("_start_audio")
    app.key(pygame.K_RETURN)
    assert app.pitch_method == PITCH_METHODS[0]
    assert app.names() == ["_start_audio"]
    assert app.view.pitch_menu_open is False


def test_menu_de_canciones_carga_la_elegida(app):
    app.view.song_menu_open = True
    app.view.song_menu_sel = 2
    app.spy("_load_song")
    app.key(pygame.K_RETURN)
    assert app.calls == [("_load_song", (2,))]
    assert app.view.song_menu_open is False


def test_mixer_ajusta_volumen_y_mute(app):
    app.view.mixer_open = True
    app.view.mixer_sel = 0
    app._mix_get = lambda tid: (0.5, False)
    app.spy("_mix_set")
    app.key(pygame.K_RIGHT)
    app.key(pygame.K_LEFT)
    app.key(pygame.K_m)
    assert app.calls == [
        ("_mix_set", ("song",)), ("_mix_set", ("song",)),
        ("_mix_set", ("song",)),
    ]
    app.key(pygame.K_F2)
    assert app.view.mixer_open is False


def test_tuner_se_cierra_con_escape(app):
    app.view.tuner_open = True
    app.key(pygame.K_ESCAPE)
    assert app.view.tuner_open is False


# ── editor de acordes (Y) ───────────────────────────────────────────────
def test_navegacion_del_editor_de_acordes(app):
    app.chord_edit_open = True
    app.chord_edit_sel = 25
    app.key(pygame.K_PAGEUP)
    assert app.chord_edit_sel == 15
    app.key(pygame.K_PAGEDOWN)
    assert app.chord_edit_sel == 25
    app.key(pygame.K_DOWN)
    assert app.chord_edit_sel == 26
    app.key(pygame.K_END)
    assert app.chord_edit_sel == 29
    app.key(pygame.K_DOWN)                  # no pasa del final
    assert app.chord_edit_sel == 29
    app.key(pygame.K_HOME)
    assert app.chord_edit_sel == 0
    app.key(pygame.K_UP)                    # ni baja de cero
    assert app.chord_edit_sel == 0
    app.key(pygame.K_RIGHT)
    assert app.chord_edit_sel == 1


def test_borrar_acorde_del_editor(app):
    app.chord_edit_open = True
    app.chord_edit_sel = 3
    app.spy("_chord_edit_apply")
    app.key(pygame.K_DELETE)
    assert app.calls == [("_chord_edit_apply", (app.rows[3][1], ""))]


def test_escribir_acorde_en_el_editor(app):
    app.chord_edit_open = True
    app._chord_edit_name_at = lambda sec: "Am"
    app.spy("_chord_edit_apply")
    app.key(pygame.K_RETURN)
    assert app.chord_edit_typing is True
    assert app.chord_edit_buf == "Am"
    app.key(pygame.K_BACKSPACE)
    assert app.chord_edit_buf == "A"
    app.key(pygame.K_m, unicode="m")        # ya hay 1 carácter tras el borrado
    assert app.chord_edit_buf == "Am"
    app.key(pygame.K_RETURN)
    assert app.names() == ["_chord_edit_apply"]
    assert app.chord_edit_typing is False


def test_borrador_vacio_si_el_acorde_es_un_guion(app):
    app.chord_edit_open = True
    app._chord_edit_name_at = lambda sec: "—"
    app.key(pygame.K_t)
    assert app.chord_edit_buf == ""
    assert app.chord_edit_typing is True


def test_escape_cancela_la_captura_de_texto(app):
    app.chord_edit_open = True
    app.chord_edit_typing = True
    app.chord_edit_buf = "C"
    app.key(pygame.K_ESCAPE)
    assert app.chord_edit_buf == ""
    assert app.chord_edit_typing is False
    assert app.chord_edit_open is True


def test_atajos_del_editor_de_acordes(app):
    app.chord_edit_open = True
    app.spy("_chords_from_score", "_chord_edit_save")
    app.key(pygame.K_d)
    app.key(pygame.K_s)                     # sin Ctrl no guarda
    assert app.names() == ["_chords_from_score"]
    assert app.key(pygame.K_y) is True
    assert app.chord_edit_open is False


# ── barra de acordes ────────────────────────────────────────────────────
def test_tab_acepta_la_primera_sugerencia(app):
    app.chord_bar_typing = True
    app.chord_bar_sugg_cache = ["C", "Cm"]
    app.key(pygame.K_TAB)
    assert app.chord_bar_buf == "C"


def test_flechas_recorren_las_sugerencias(app):
    app.chord_bar_typing = True
    app.chord_bar_sugg_cache = ["C", "Cm", "C7"]
    app.key(pygame.K_DOWN)
    assert (app.chord_bar_sugg_idx, app.chord_bar_buf) == (0, "C")
    app.key(pygame.K_DOWN)
    assert (app.chord_bar_sugg_idx, app.chord_bar_buf) == (1, "Cm")
    app.key(pygame.K_UP)
    assert (app.chord_bar_sugg_idx, app.chord_bar_buf) == (0, "C")


def test_retroceso_y_enter_en_la_barra(app):
    app.chord_bar_typing = True
    app.chord_bar_buf = "Cm7"
    app.spy("_chord_bar_commit")
    app.key(pygame.K_BACKSPACE)
    assert app.chord_bar_buf == "Cm"
    app.key(pygame.K_RETURN)
    assert app.names() == ["_chord_bar_commit"]


def test_escribir_reemplaza_si_toca(app):
    app.chord_bar_typing = True
    app.chord_bar_buf = "Cmaj7"
    app.chord_bar_replace = True
    app.key(pygame.K_g, unicode="G")
    assert app.chord_bar_buf == "G"
    assert app.chord_bar_replace is False


# ── modos y overlays ────────────────────────────────────────────────────
@pytest.mark.parametrize("bandera,esperado", [
    ("training_open", "_key_training"),
    ("lab_open", "_key_lab"),
    ("cor_open", "_key_cor"),
    ("ear_open", "_key_ear"),
])
def test_cada_modo_recibe_su_teclado(app, bandera, esperado):
    setattr(app, bandera, True)
    app.spy(esperado, ret=True)
    app.key(pygame.K_SPACE)
    assert app.names() == [esperado]


@pytest.mark.parametrize("bandera,modo", [
    ("tx_open", "tx"), ("ar_open", "ar"), ("sc_open", "sc"),
])
def test_secuencias_pasan_su_nombre(app, bandera, modo):
    setattr(app, bandera, True)
    app.spy("_key_seq", ret=True)
    app.key(pygame.K_SPACE)
    assert app.calls[0][0] == "_key_seq"
    assert app.calls[0][1][0] == modo


def test_generacion_en_curso_se_coma_las_teclas(app):
    app.gen_running = True
    app.spy("toggle_play")
    assert app.key(pygame.K_SPACE) is True
    assert app.calls == []


def test_el_aviso_de_generacion_se_cierra_con_una_tecla(app):
    app.gen_error = "falló"
    app.songs = [{"audio_only": True}]
    assert app.key(pygame.K_SPACE) is True
    assert app.gen_error == ""
    assert app.gen_notice is True


# ── ratón: paneles ──────────────────────────────────────────────────────
def test_editor_de_acordes_se_come_el_clic(app):
    app.chord_edit_open = True
    app.spy("_chord_bar_click")
    app.down((100, KARAOKE_Y + 5))
    assert app.calls == []


def test_clic_en_una_sugerencia_la_aplica(app):
    app.chord_bar_typing = True
    app.chord_bar_sugg_layout = lambda: [("Cm", pygame.Rect(0, 0, 40, 20))]
    app.spy("_chord_bar_commit")
    app.down((10, 10))
    assert app.chord_bar_buf == "Cm"
    assert app.names() == ["_chord_bar_commit"]


def test_chip_del_header_consume_el_clic(app):
    app._header_chip_click = lambda pos: True
    app.spy("_chord_bar_click")
    app.down((5, 5))
    assert app.calls == []


def test_clic_fuera_de_la_tira_deselecciona(app):
    app.spy("_chord_bar_clear")
    app.down((100, KARAOKE_Y + 200))
    assert app.names() == ["_chord_bar_clear"]


# ── ratón: editor de alineación ─────────────────────────────────────────
@pytest.mark.parametrize("kind,bandera", [
    ("red", "align_dragging"),
    ("start", "align_dragging_start"),
])
def test_arrastrar_anclas_en_el_editor(app, kind, bandera):
    app.align_editor_open = True
    app._align_pick_at_pos = lambda pos: (kind, 0.0)
    app.spy("_align_set_offset_from_mouse", "_align_set_song_start_from_mouse")
    app.down((100, 100))
    assert getattr(app, bandera) is True


def test_clic_en_una_marca_la_selecciona(app):
    app.align_editor_open = True
    app._align_pick_at_pos = lambda pos: ("mark", 7.5)
    app.down((100, 100))
    assert app.align_drag_marker == 7.5
    assert app.align_cursor_sec == 7.5


def test_clic_en_marca_fantasma_la_adopta(app):
    app.align_editor_open = True
    app._align_pick_at_pos = lambda pos: ("ghost", 3)
    app.spy("_align_adopt_score_mark")
    app.down((100, 100))
    assert app.names() == ["_align_adopt_score_mark"]


def test_clic_libre_mueve_el_cursor(app):
    app.align_editor_open = True
    app._align_pick_at_pos = lambda pos: (None, None)
    app._align_sec_of_pos = lambda pos: 12.0
    app.down((100, 100))
    assert app.align_cursor_sec == 12.0


def test_botones_del_editor_alineacion(app):
    app.align_editor_open = True
    app.spy("_align_add_marker", "_align_zoom")
    app.down((50, 50), button=2)
    assert app.align_panning is True
    app.down((50, 50), button=3)
    app.down((50, 50), button=4)
    app.down((50, 50), button=5)
    assert app.names() == ["_align_add_marker", "_align_zoom", "_align_zoom"]


def test_soltar_en_el_editor_corta_los_arrastres(app):
    app.align_editor_open = True
    app.align_dragging = True
    app.align_drag_marker = 4
    app.up()
    assert app.align_dragging is False
    assert app.align_drag_marker is None


# ── ratón: reproducción ─────────────────────────────────────────────────
def test_clic_junto_a_la_linea_agarra_el_ancla(app):
    app.song_wave = object()
    app.px_of = lambda s16: 0.0
    app.down((W // 3, WAVEFORM_Y + 2))
    assert app.view._anchor_drag == "bass"


def test_clic_lejos_de_las_anclas_busca(app):
    app.song_wave = object()
    app.px_of = lambda s16: 0.0
    app.beat_time = 3.0
    app.down((W // 3 + 200, WAVEFORM_Y + 2))
    assert app.view._drag_seeking is True
    assert app.view._drag_start_beat == 3.0


def test_clic_en_el_piano_y_en_el_mastil_previsualiza(app):
    app._piano_hit = lambda pos: 45
    app._neck_hit = lambda pos: (2, 1)
    app.spy("_preview_from_piano", "_preview_from_neck")
    app.down((10, NECK_Y - 5))
    assert app.calls == [("_preview_from_piano", (45,))]
    app._piano_hit = lambda pos: None
    app.down((10, NECK_Y - 5))
    assert app.names() == ["_preview_from_piano", "_preview_from_neck"]


def test_arrastrar_la_partitura_busca(app):
    app.beat_time = 1.5
    app.down((10, TAB_Y + 2))
    assert app.view._drag_seeking is True
    assert app.view._drag_start_beat == 1.5


def test_con_panel_abierto_la_onda_no_responde(app):
    app.view.help_open = True
    app.song_wave = object()
    app.down((10, WAVEFORM_Y + 2))
    assert app.view._drag_seeking is False


def test_boton_derecho_sobre_la_onda_navega(app):
    app.song_wave = object()
    app.down((10, WAVEFORM_Y + 2), button=3)
    assert app.view._drag_seeking is True


def test_boton_central_sobre_la_onda_mueve_el_audio(app):
    app.song_wave = object()
    app.mp3_offset_sec = 2.0
    app.song_start_sec = 1.0
    app.down((10, WAVEFORM_Y + 2), button=2)
    assert app.view._wave_dragging is True
    assert app.view._wave_drag_off == 2.0
    assert app.view._wave_drag_start == 1.0


def test_soltar_recuerda_las_anclas(app):
    app.view._anchor_drag = "bass"
    app.spy("_remember_anchors")
    app.up(button=1)
    assert app.view._anchor_drag is None
    assert app.names() == ["_remember_anchors"]


def test_soltar_el_central_termina_el_arrastre_de_onda(app):
    app.view._wave_dragging = True
    app.up(button=2)
    assert app.view._wave_dragging is False


# ── rueda y movimiento ──────────────────────────────────────────────────
def test_rueda_en_el_editor_de_acordes(app):
    app.chord_edit_open = True
    app.chord_edit_sel = 5
    app.wheel(y=2)
    assert app.chord_edit_sel == 3


def test_rueda_zoom_en_el_editor_de_alineacion(app):
    app.align_editor_open = True
    app.spy("_align_zoom")
    app.wheel(y=1)
    assert app.names() == ["_align_zoom"]


def test_hover_de_chips(app):
    app._header_chips_layout = lambda: (
        [("ayuda", "Ayuda F1", pygame.Rect(0, 0, 60, 20))], 0)
    app.move((5, 5))
    assert app.view.chip_hover == "ayuda"
    app.move((500, 400))
    assert app.view.chip_hover == ""


def test_arrastrar_ancla_mueve_el_offset(app):
    app.view._anchor_drag = "bass"
    app.view._anchor_drag_mx = 0
    app.spy("_clamp_anchors")
    app.move((10, 300))
    assert abs(app.mp3_offset_sec - 0.125) < 1e-9
    assert app.names() == ["_clamp_anchors"]


def test_arrastrar_ancla_de_inicio_mueve_el_arranque(app):
    app.view._anchor_drag = "start"
    app.view._anchor_drag_mx = 0
    app.move((10, 300))
    assert abs(app.song_start_sec - 0.125) < 1e-9


def test_arrastrar_la_onda_desplaza_ambas_anclas(app):
    app.view._wave_dragging = True
    app.view._wave_drag_mx = 0
    app.view._wave_drag_off = 1.0
    app.view._wave_drag_start = 1.0
    app.move((10, 300))
    assert abs(app.mp3_offset_sec - 0.875) < 1e-9
    assert abs(app.song_start_sec - 0.875) < 1e-9


def test_arrastrar_en_la_partitura_busca(app):
    app.view._drag_seeking = True
    app.view._drag_start_mx = 0
    app.spy("_seek_to_beat")
    app.move((20, 300))
    assert app.names() == ["_seek_to_beat"]


def test_mover_en_el_editor_de_alineacion_dibuja_arrastre(app):
    app.align_editor_open = True
    app.align_dragging = True
    app.spy("_align_set_offset_from_mouse")
    app.move((40, 40))
    assert app.names() == ["_align_set_offset_from_mouse"]
