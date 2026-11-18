"""Detectores de pitch con señales sintéticas, sin micrófono.

Cada bajo se simula como fundamental + armónicos decrecientes: es la señal
que más se parece a una cuerda pulsada y la que históricamente hacía que los
detectores se fueran una octava arriba.
"""
import math

import numpy as np
import pytest

from bass_karaoke.audio.detectors import (
    MPMDetector,
    PitchReading,
    _mpm_pitch,
    _octave_to_bass_range,
)
from bass_karaoke.audio.pitch_engine import PitchStabilizer
from bass_karaoke.config import (
    CHUNK_SIZE,
    MAX_HZ,
    MIN_HZ,
    MPM_THRESHOLD,
    MPM_WIN,
    SAMPLERATE,
)
from bass_karaoke.utils import hz_to_midi, hz_to_note_name, midi_to_hz

OPEN_STRINGS = {"E1": 41.20, "A1": 55.00, "D2": 73.42, "G2": 98.00}


def bass_tone(hz: float, n: int, harmonics: int = 4) -> np.ndarray:
    """Seno con armónicos decrecientes, normalizado a ±0.3."""
    t = np.arange(n) / SAMPLERATE
    signal = np.zeros(n)
    for k in range(1, harmonics + 1):
        signal += (0.6 ** (k - 1)) * np.sin(2 * np.pi * hz * k * t)
    signal *= 0.3 / np.max(np.abs(signal))
    return signal.astype(np.float32)


@pytest.mark.parametrize("name,hz", OPEN_STRINGS.items())
def test_mpm_detects_open_strings(name, hz):
    f0, clarity = _mpm_pitch(
        bass_tone(hz, MPM_WIN), SAMPLERATE, MIN_HZ, MAX_HZ, MPM_THRESHOLD)

    assert f0 > 0
    assert clarity >= MPM_THRESHOLD
    cents = 1200 * math.log2(f0 / hz)
    assert abs(cents) < 20, f"{name}: {f0:.2f} Hz ({cents:+.1f} cents)"
    assert hz_to_note_name(f0) == name


def test_mpm_returns_zero_on_silence():
    silence = np.zeros(MPM_WIN, dtype=np.float32)
    assert _mpm_pitch(silence, SAMPLERATE, MIN_HZ, MAX_HZ, MPM_THRESHOLD) == (0.0, 0.0)


def test_mpm_detector_survives_chunked_streaming():
    """El buffer interno debe desplazarse igual que el bucle real."""
    detector = MPMDetector()
    signal = bass_tone(OPEN_STRINGS["A1"], CHUNK_SIZE * 3)

    reading = None
    for i in range(3):
        reading = detector.detect(signal[i * CHUNK_SIZE:(i + 1) * CHUNK_SIZE])

    assert isinstance(reading, PitchReading)
    assert abs(1200 * math.log2(reading.hz / OPEN_STRINGS["A1"])) < 20
    assert reading.conf >= MPM_THRESHOLD


@pytest.mark.parametrize("hz,expected", [
    (20.0, 40.0),      # sub-armónico: sube una octava
    (600.0, 300.0),    # armónico: baja a la fundamental
    (82.41, 82.41),    # nota real del bajo: no se toca
    (0.0, 0.0),
])
def test_octave_folding_is_conservative(hz, expected):
    assert _octave_to_bass_range(hz) == pytest.approx(expected)


def test_stabilizer_commits_note_with_two_of_three_votes():
    stabilizer = PitchStabilizer()

    first = stabilizer.feed(55.0, 1.0, 0.0)
    assert first[0] == pytest.approx(55.0)
    assert first[2] == 0.0          # aún no hay 2 votos

    second = stabilizer.feed(55.2, 1.0, 0.0)
    assert second[2] == pytest.approx(55.0, abs=0.2)
    assert second[3] == "A1"


def test_stabilizer_holds_then_releases_after_silence():
    stabilizer = PitchStabilizer(hold_frames=3)
    stabilizer.feed(55.0, 1.0, 0.0)

    assert stabilizer.on_silence() is None
    assert stabilizer.on_silence() is None
    assert stabilizer.on_silence() == (0.0, "—", 0.0, "—")
    assert stabilizer.hold_count == 3


def test_stabilizer_rejects_low_confidence():
    stabilizer = PitchStabilizer(hold_frames=2)
    assert stabilizer.feed(55.0, 0.05, 0.20) == (0.0, "—", 0.0, "—")


def test_midi_hz_roundtrip():
    for hz in OPEN_STRINGS.values():
        assert midi_to_hz(hz_to_midi(hz)) == pytest.approx(hz)
