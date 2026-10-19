"""ViewState: valores por defecto y aislamiento entre instancias."""
from bass_karaoke.config import PITCH_METHODS
from bass_karaoke.view_state import ViewState


def test_defaults():
    v = ViewState()
    assert v.px_per_16th == 30
    assert v.viewport_x == 0.0 and v.target_x == 0.0
    assert v.tempo_display_mode == "figura"
    assert v.chords_on is True and v.neck_map is False
    assert v.pitch_menu_sel == PITCH_METHODS.index("crepe-tiny")
    assert v._score_total16 == 1
    assert v._score_surf is None and v._preview_sound is None


def test_mutable_fields_are_isolated():
    a, b = ViewState(), ViewState()
    a._score_cache["x"] = 1
    a._score_note_xs.append(1)
    a.preview_name = "A"
    assert b._score_cache == {}
    assert b._score_note_xs == []
    assert b.preview_name == "—"
