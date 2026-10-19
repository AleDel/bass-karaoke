"""Tests del entrenador de notas (training.py) — puro y determinista."""
import random

from bass_karaoke import music, training


def test_levels_are_ordered_by_difficulty():
    assert training.LEVELS[1]["notes"] == ["E", "A", "D", "G"]
    assert len(training.LEVELS[2]["notes"]) == 7
    assert len(training.LEVELS[3]["notes"]) == 12


def test_target_midi_uses_reference_octave():
    assert training.target_midi("C") == training.REF_OCTAVE
    assert training.target_midi("E") == training.REF_OCTAVE + music.NOTE_PC["E"]


def test_pick_target_stays_inside_the_level_pool():
    rng = random.Random(1234)
    for _ in range(100):
        assert training.pick_target(1, rng=rng) in training.LEVELS[1]["notes"]


def test_pick_target_avoids_repeating_previous_note():
    rng = random.Random(99)
    for _ in range(100):
        n = training.pick_target(3, exclude="C", rng=rng)
        assert n != "C"


def test_pick_target_unknown_level_falls_back_to_level_one():
    rng = random.Random(7)
    assert training.pick_target(99, rng=rng) in training.LEVELS[1]["notes"]


def test_accuracy_percentage_and_zero_guard():
    assert training.accuracy(3, 4) == 75
    assert training.accuracy(4, 4) == 100
    assert training.accuracy(0, 0) == 0
