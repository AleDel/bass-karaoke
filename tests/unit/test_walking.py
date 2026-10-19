"""Tests del Walking Lab (walking.py) — lógica pura de moldes."""
from bass_karaoke import music, walking


def test_build_mold_has_the_four_expected_roles():
    steps = walking.build_mold(3, 3, "maj", next_root_midi=music.midi_of(3, 5))
    assert [s["role"] for s in steps] == ["Raíz", "3ª", "5ª", "Aprox."]
    assert all({"string", "fret", "finger", "midi", "hz", "name"} <= s.keys()
               for s in steps)


def test_build_mold_chord_tones_are_correct():
    steps = walking.build_mold(3, 3, "maj", next_root_midi=38)
    assert steps[0]["midi"] == music.midi_of(3, 3)   # raíz C2
    assert steps[1]["midi"] == music.midi_of(2, 2)   # 3ª mayor E2
    assert steps[2]["midi"] == music.midi_of(2, 5)   # 5ª justa G2
    assert steps[0]["finger"] == walking.ROOT_FINGER["maj"]


def test_build_mold_third_follows_quality():
    major = walking.build_mold(3, 3, "maj", 38)[1]["midi"]
    minor = walking.build_mold(3, 3, "min", 38)[1]["midi"]
    assert major - music.midi_of(3, 3) == 4
    assert minor - music.midi_of(3, 3) == 3


def test_build_mold_unknown_quality_falls_back_to_major():
    weird = walking.build_mold(3, 3, "banana", 38)
    major = walking.build_mold(3, 3, "maj", 38)
    assert [s["midi"] for s in weird] == [s["midi"] for s in major]


def test_approach_note_is_one_semitone_from_next_root():
    next_root = 38
    steps = walking.build_mold(3, 3, "maj", next_root)
    assert abs(steps[3]["midi"] - next_root) == 1


def test_beat_matches_chord_tones_by_pitch_class():
    steps = walking.build_mold(3, 3, "maj", 38)
    root_hz = music.midi_to_hz(steps[0]["midi"])
    assert walking.beat_matches(root_hz, steps, 0, 38)
    # otra octava de la raíz sigue cumpliendo
    assert walking.beat_matches(root_hz * 2, steps, 0, 38)
    assert not walking.beat_matches(music.midi_to_hz(41), steps, 0, 38)


def test_beat_matches_approach_uses_neighbour_pitch_class():
    steps = walking.build_mold(3, 3, "maj", 38)
    # vecino cromático de la raíz siguiente (38 → Re): Do# (pc 1) vale
    assert walking.beat_matches(music.midi_to_hz(49), steps, 3, 38)   # C#3
    assert not walking.beat_matches(music.midi_to_hz(45), steps, 3, 38)  # A2 lejos


def test_beat_matches_rejects_silence():
    steps = walking.build_mold(3, 3, "maj", 38)
    assert not walking.beat_matches(0.0, steps, 0, 38)


def test_build_exercise_loops_the_approach_to_next_bar_root():
    molds = walking.build_exercise(walking.EXERCISES[0])
    assert len(molds) == 2
    roots = [music.midi_of(b["string"], b["fret"])
             for b in walking.EXERCISES[0]["bars"]]
    # El tiempo 4 del compás 1 aproxima la raíz del compás 2 (y viceversa)
    assert abs(molds[0][3]["midi"] - roots[1]) == 1
    assert abs(molds[1][3]["midi"] - roots[0]) == 1
