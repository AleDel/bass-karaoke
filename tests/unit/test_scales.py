"""Tests de escalas por cajas (scales.py) — geometría pura."""
from bass_karaoke import music, scales


def test_major_scale_has_eight_up_and_seven_down_steps():
    steps = scales.build_scale(1, root_fret=3)
    assert len(steps) == 15
    assert [s["degree"] for s in steps] == [1, 2, 3, 4, 5, 6, 7, 8,
                                            7, 6, 5, 4, 3, 2, 1]


def test_scale_starts_on_the_requested_root():
    steps = scales.build_scale(1, root_fret=3)
    assert steps[0]["string"] == scales.ROOT_STRING
    assert steps[0]["fret"] == 3
    assert steps[0]["midi"] == music.midi_of(scales.ROOT_STRING, 3)


def test_scale_intervals_match_the_definition():
    steps = scales.build_scale(1, root_fret=3)
    root = steps[0]["midi"]
    assert [s["midi"] - root for s in steps[:8]] == scales.SCALES[1]["iv"]


def test_pentatonic_is_shorter_than_major():
    assert len(scales.build_scale(3, 3)) == len(scales.SCALES[3]["iv"]) * 2 - 1


def test_scale_positions_stay_inside_the_neck():
    steps = scales.build_scale(1, root_fret=3)
    assert all(0 <= s["fret"] <= music.MAX_FRET for s in steps)
    assert all(1 <= s["string"] <= 4 for s in steps)


def test_root_fret_is_clamped():
    steps = scales.build_scale(1, root_fret=999)
    assert steps[0]["fret"] == 12


def test_step_matches_is_octave_invariant_here():
    step = scales.build_scale(1, root_fret=3)[0]
    assert scales.step_matches(music.midi_to_hz(step["midi"]), step)
    assert scales.step_matches(music.midi_to_hz(step["midi"] + 12), step)
    assert not scales.step_matches(0.0, step)
