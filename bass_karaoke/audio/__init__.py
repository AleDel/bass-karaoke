from .bass_track import backend as bass_backend
from .bass_track import find_soundfont, render as render_bass, to_int16
from .pitch_engine import (
    PA_OK,
    PITCH_AVAILABLE,
    PitchEngine,
    clean_device_name,
    device_name_warning,
    enumerate_devices,
)
from .player import SOUNDFILE_OK, VARSPEED_OK, VarispeedPlayer, load_mp3_samples

try:
    from .band import available as band_available
    from .band import midi_available as band_midi_available
    from .band import render as render_band
    from .band import render_midi as render_band_midi
    from .band import source_name as band_source
except Exception:
    def band_available():
        return False

    def render_band(*_a, **_k):
        return None

    def band_midi_available():
        return False

    def render_band_midi(*_a, **_k):
        return None

    def band_source():
        return ""

INPUT_AVAILABLE = bool(PA_OK)

__all__ = [
    "VarispeedPlayer", "VARSPEED_OK", "SOUNDFILE_OK", "load_mp3_samples",
    "PitchEngine", "PITCH_AVAILABLE", "enumerate_devices",
    "device_name_warning", "clean_device_name", "PA_OK",
    "INPUT_AVAILABLE",
    "render_bass", "to_int16", "bass_backend", "find_soundfont",
    "render_band", "band_available", "band_source",
    "render_band_midi", "band_midi_available",
]
