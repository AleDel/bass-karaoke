"""Grupos de estado (bass_karaoke/state.py): delegación y valores por defecto."""
import pytest

from bass_karaoke.state import (
    AlignEditorState,
    ChordBarState,
    ChordEditState,
    GenerationState,
    StateGroup,
    with_state,
)


@with_state(StateGroup("chord_bar", ChordBarState, "chord_bar_"))
class Host:
    """Clase mínima que imita a BassKaraoke sin llamar a __init__."""


def test_defaults_sin_init():
    h = Host()
    assert h.chord_bar_sel_measure is None
    assert h.chord_bar_typing is False
    assert h.chord_bar_buf == ""
    assert h.chord_bar_sugg_idx == -1
    assert h.chord_bar_sugg_cache == []


def test_la_propiedad_lee_y_escribe_en_el_grupo():
    h = Host()
    h.chord_bar_sel_measure = 4
    assert h.chord_bar_state.sel_measure == 4
    h.chord_bar_state.buf = "Am7"
    assert h.chord_bar_buf == "Am7"


def test_las_instancias_no_comparten_listas():
    a, b = Host(), Host()
    a.chord_bar_sugg_cache.append("C")
    assert b.chord_bar_sugg_cache == []


def test_se_puede_sustituir_el_grupo_entero():
    h = Host()
    h.chord_bar_state = ChordBarState(buf="G", typing=True)
    assert (h.chord_bar_buf, h.chord_bar_typing) == ("G", True)


def test_un_nombre_existente_falla_al_importar():
    with pytest.raises(RuntimeError, match="ya existe"):
        @with_state(StateGroup("chord_bar", ChordBarState, "chord_bar_"))
        class Clash:
            chord_bar_msg = "ya estaba"


def test_prefijos_de_los_demas_grupos():
    @with_state(
        StateGroup("chord_edit", ChordEditState, "chord_edit_"),
        StateGroup("align", AlignEditorState, "align_"),
        StateGroup("gen", GenerationState, "gen_"),
    )
    class Many:
        pass

    m = Many()
    assert m.chord_edit_open is False and m.chord_edit_dirty is False
    assert m.align_editor_open is False and m.align_pan_start == (0, 0)
    assert m.gen_barlen == 3 and m.gen_bars_per_chord == 2
    m.gen_running = True
    assert m.gen_state.running is True


def test_basskaraoke_sin_init_tiene_los_defaults():
    """Los FakeApp(BassKaraoke) de los tests no llaman a __init__."""
    from bass_karaoke.app import BassKaraoke

    class Fake(BassKaraoke):
        def __init__(self):
            pass

    f = Fake()
    assert f.chord_bar_sel_measure is None
    assert f.chord_edit_sel == 0
    assert f.align_editor_open is False
    assert f.gen_running is False
    f.chord_bar_buf = "C"
    assert f.chord_bar_state.buf == "C"
