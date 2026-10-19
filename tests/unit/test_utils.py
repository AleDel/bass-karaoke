"""Tests de utilidades de conversión y comparación de notas (utils.py)."""
import pytest

from bass_karaoke import utils
from bass_karaoke.config import STRING_OPEN_HZ


def test_fret_to_hz_open_string_is_nominal():
    for string, hz in STRING_OPEN_HZ.items():
        assert utils.fret_to_hz(0, string) == pytest.approx(hz)


def test_fret_to_hz_one_octave_is_twelve_frets():
    assert utils.fret_to_hz(12, 4) == pytest.approx(2 * utils.fret_to_hz(0, 4))


def test_hz_to_note_name_known_values():
    assert utils.hz_to_note_name(440.0) == "A4"
    assert utils.hz_to_note_name(STRING_OPEN_HZ[4]) == "E1"


def test_hz_to_note_name_silence_returns_dash():
    assert utils.hz_to_note_name(0.0) == "—"
    assert utils.hz_to_note_name(9.9) == "—"


def test_notes_match_octave_invariant():
    e1 = STRING_OPEN_HZ[4]
    assert utils.notes_match(e1, 2 * e1)      # misma clase de tono
    assert utils.notes_match(e1, e1)


def test_notes_match_rejects_out_of_range_or_wrong_note():
    e1 = STRING_OPEN_HZ[4]
    assert not utils.notes_match(0.0, e1)      # sin señal
    assert not utils.notes_match(1e9, e1)      # fuera de MAX_HZ
    assert not utils.notes_match(e1, 0.0)      # objetivo inválido
    assert not utils.notes_match(utils.fret_to_hz(1, 4), e1)  # E vs F


def test_notes_match_fifty_cent_tolerance_boundary():
    e1 = STRING_OPEN_HZ[4]
    # 40 cents por encima: dentro de tolerancia (±50 cents)
    assert utils.notes_match(e1 * 2 ** (40 / 1200), e1)
