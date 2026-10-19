"""Tests del núcleo de teoría musical (music.py) — puro, sin pygame."""
import math

import pytest

from bass_karaoke import music


def test_open_midi_matches_standard_bass_tuning():
    assert music.OPEN_MIDI == {4: 28, 3: 33, 2: 38, 1: 43}


def test_midi_to_hz_reference_pitches():
    assert music.midi_to_hz(69) == pytest.approx(440.0)
    assert music.midi_to_hz(28) == pytest.approx(41.2034, abs=1e-3)


def test_midi_to_hz_octave_is_doubling():
    assert music.midi_to_hz(40) == pytest.approx(2 * music.midi_to_hz(28))


@pytest.mark.parametrize(
    "midi,expected",
    [(28, "E1"), (33, "A1"), (38, "D2"), (43, "G2"), (69, "A4"), (60, "C4")],
)
def test_midi_name(midi, expected):
    assert music.midi_name(midi) == expected


def test_midi_of_offsets_from_open_string():
    assert music.midi_of(4, 0) == 28
    assert music.midi_of(4, 3) == 31
    assert music.midi_of(3, 3) == 36


def test_pc_of_hz_maps_to_pitch_class():
    assert music.pc_of_hz(440.0) == 9      # A
    assert music.pc_of_hz(880.0) == 9      # octava no cambia la clase de tono
    assert music.pc_of_hz(music.midi_to_hz(36)) == 0  # C


def test_pc_of_hz_no_signal_returns_none():
    assert music.pc_of_hz(0) is None
    assert music.pc_of_hz(-1) is None
    assert music.pc_of_hz(None) is None


def test_pc_match_is_octave_invariant():
    assert music.pc_match(440.0, 57)   # A3 vs A4 → misma clase
    assert not music.pc_match(440.0, 60)  # C4 → distinta clase
    assert not music.pc_match(0, 60)


def test_exact_match_requires_same_octave():
    assert music.exact_match(440.0, 69)
    assert not music.exact_match(440.0, 57)   # mismo nombre, octava distinta
    assert not music.exact_match(440.0, 69, tol=0.0)
    assert not music.exact_match(0, 69)


def test_tone_pos_prefers_adjacent_higher_string():
    # Sobre C en (cuerda A, traste 3): la 3ª mayor (4 st) cae en D(midi 40)
    assert music.tone_pos(3, 3, 4) == (2, 2)
    # La 5ª (7 st) cae en G(midi 43)
    assert music.tone_pos(3, 3, 7) == (2, 5)


def test_tone_pos_returns_position_on_target_tonality():
    s, f = music.tone_pos(4, 0, 12)  # octava sobre E1
    assert music.midi_of(s, f) == music.midi_of(4, 0) + 12


def test_tone_pos_all_intervals_land_on_the_right_pitch():
    root_s, root_f = 3, 5
    root_midi = music.midi_of(root_s, root_f)
    for interval in range(0, 13):
        s, f = music.tone_pos(root_s, root_f, interval)
        assert music.midi_of(s, f) == root_midi + interval
