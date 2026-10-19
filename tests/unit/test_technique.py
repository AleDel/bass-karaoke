"""Tests de los patrones de técnica (technique.py) — posiciones puras."""
from bass_karaoke import music, technique


def test_chromatic_pattern_is_sixteen_steps_over_four_strings():
    steps = technique.build_pattern(1, start_fret=5)
    assert len(steps) == 16
    # Cuatro trastes seguidos por cuerda, de la E grave a la G aguda
    assert [s["string"] for s in steps] == [4, 4, 4, 4, 3, 3, 3, 3,
                                            2, 2, 2, 2, 1, 1, 1, 1]


def test_chromatic_pattern_assigns_one_finger_per_fret():
    steps = technique.build_pattern(1, start_fret=5)
    first_string = steps[:4]           # cuerda E, trastes 5-8
    assert [s["fret"] for s in first_string] == [5, 6, 7, 8]
    assert [s["finger"] for s in first_string] == [1, 2, 3, 4]


def test_chromatic_pattern_clamps_start_fret_to_leave_room():
    steps = technique.build_pattern(1, start_fret=100)
    assert max(s["fret"] for s in steps) <= music.MAX_FRET
    assert min(s["fret"] for s in steps) == music.MAX_FRET - 3


def test_crossing_pattern_alternates_fingers_and_returns():
    steps = technique.build_pattern(2, start_fret=5)
    assert [s["string"] for s in steps] == [4, 3, 2, 1, 1, 2, 3, 4] * 2
    assert [s["finger"] for s in steps][:4] == [1, 2, 1, 2]
    assert all(s["fret"] == 5 for s in steps)


def test_step_matches_requires_the_exact_octave():
    step = technique.build_pattern(1, start_fret=5)[0]
    assert technique.step_matches(music.midi_to_hz(step["midi"]), step)
    assert not technique.step_matches(music.midi_to_hz(step["midi"] + 12), step)
    assert not technique.step_matches(0.0, step)
