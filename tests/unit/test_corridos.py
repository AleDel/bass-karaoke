"""Tests del bajeo de corridos tumbados (corridos.py) — 3/4 puro."""
from bass_karaoke import corridos, music


def test_fifth_shapes_for_middle_string():
    assert corridos.fifth_shapes(3, 3) == {"down": (4, 3), "up": (2, 5)}


def test_fifth_shapes_degrade_at_neck_edges():
    # En la cuerda E (4) no hay quinta "abajo"
    assert corridos.fifth_shapes(4, 0)["down"] is None
    assert corridos.fifth_shapes(4, 0)["up"] == (3, 2)
    # En la cuerda G (1) no hay quinta "arriba"
    assert corridos.fifth_shapes(1, 5)["up"] is None
    assert corridos.fifth_shapes(1, 5)["down"] == (2, 5)


def test_build_bajeo_structure_two_bars_of_three_beats():
    bars = corridos.build_bajeo(3, 3, next_root_midi=31)
    assert len(bars) == 2
    assert all(len(bar) == 3 for bar in bars)


def test_bar_root_plays_only_beat_one():
    bar_root = corridos.build_bajeo(3, 3, next_root_midi=31)[0]
    assert bar_root[0]["role"] == "Raíz"
    assert bar_root[0]["midi"] == music.midi_of(3, 3)
    assert bar_root[1]["midi"] is None      # silencio
    assert bar_root[2]["midi"] is None      # silencio


def test_bar_fifth_plays_fifth_and_optional_ornament():
    bar_fifth = corridos.build_bajeo(3, 3, next_root_midi=31)[1]
    assert bar_fifth[0]["role"] == "5ª"
    assert bar_fifth[0]["midi"] == music.midi_of(4, 3)   # quinta abajo
    assert bar_fifth[1]["midi"] is None
    assert bar_fifth[2]["role"] == "Adorno"


def test_ornament_can_be_disabled():
    bar_fifth = corridos.build_bajeo(3, 3, next_root_midi=31, ornament=False)[1]
    assert bar_fifth[2]["midi"] is None


def test_fifth_up_shape_selected_when_requested():
    bar_fifth = corridos.build_bajeo(3, 3, next_root_midi=31, fifth="up")[1]
    assert bar_fifth[0]["midi"] == music.midi_of(2, 5)


def test_bajeo_matches_scores_root_and_fifth_rows():
    bars = corridos.build_bajeo(3, 3, next_root_midi=31)
    root = bars[0][0]
    fifth = bars[1][0]
    assert corridos.bajeo_matches(music.midi_to_hz(root["midi"]), root, 31)
    assert corridos.bajeo_matches(music.midi_to_hz(fifth["midi"]), fifth, 31)
    # octava distinta sigue valiendo (invariante de octava)
    assert corridos.bajeo_matches(music.midi_to_hz(root["midi"] + 12), root, 31)


def test_bajeo_matches_ornament_is_chromatic_to_next_root():
    bar_fifth = corridos.build_bajeo(3, 3, next_root_midi=31)[1]
    adorn = bar_fifth[2]
    assert corridos.bajeo_matches(music.midi_to_hz(adorn["midi"]), adorn, 31)


def test_bajeo_matches_returns_none_on_silence():
    bar_root = corridos.build_bajeo(3, 3, next_root_midi=31)[0]
    assert corridos.bajeo_matches(0.0, bar_root[1], 31) is None


def test_build_corrido_emits_two_bars_per_chord():
    ex = corridos.CORRIDO_EXERCISES[0]
    steps, roots = corridos.build_corrido(ex)
    assert len(steps) == 2 * len(ex["bars"])
    assert len(roots) == len(ex["bars"])
    assert all(len(bar) == 3 for bar in steps)
