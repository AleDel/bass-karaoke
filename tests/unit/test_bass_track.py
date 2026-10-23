"""Tests del render offline de la línea de bajo (pista del mixer)."""
import os

import numpy as np
import pytest

from bass_karaoke.audio import bass_track as bt


def test_hz_to_midi_reference_pitches():
    assert bt.hz_to_midi(440.0) == 69
    assert bt.hz_to_midi(41.2034) == 28          # E1, cuerda 4 al aire
    assert bt.hz_to_midi(110.0) == 45            # A2


def test_render_empty_is_silence_with_expected_length():
    sr = 8000
    a = bt.render([], 1.0, sr=sr, engine="synth")
    assert a.shape == (int((1.0 + bt.RELEASE_SEC) * sr), 2)
    assert a.dtype == np.float32
    assert not np.any(a)


def test_render_synth_note_has_energy_after_onset():
    sr = 8000
    a = bt.render([(0.5, 0.3, 40)], 1.2, sr=sr, engine="synth")
    mono = np.abs(a[:, 0])
    before = mono[: int(0.4 * sr)].max()
    during = mono[int(0.55 * sr): int(0.75 * sr)].max()
    assert before < 1e-6
    assert during > 0.05
    assert mono.max() <= 0.9 + 1e-6


def test_render_ignores_invalid_midi():
    sr = 8000
    a = bt.render([(0.0, 0.2, None), (0.0, 0.2, 200)], 0.5, sr=sr, engine="synth")
    assert not np.any(a)


def test_render_sf2_backend_produces_audio():
    if bt.backend() != "sf2":
        pytest.skip("tinysoundfont / SoundFont no disponible")
    sr = 8000
    a = bt.render([(0.2, 0.4, 40)], 1.0, sr=sr)
    assert a.shape[1] == 2
    assert float(np.abs(a).max()) > 0.05


def test_render_sf2_is_smooth_not_noise():
    """Regresión: generate_simple() da float32; mal leído como int16 sonaba
    a ruido. Un tono grave no puede saltar entre muestras."""
    if bt.backend() != "sf2":
        pytest.skip("tinysoundfont / SoundFont no disponible")
    a = bt.render([(0.0, 0.6, 40)], 0.9, sr=bt.SAMPLERATE)
    jumps = np.abs(np.diff(a[:, 0]))
    assert float(jumps.max()) < 0.1
    assert float(np.abs(a).max()) <= 1.0


def test_to_int16_dtype_and_clipping():
    x = np.array([[0.0, 1.0], [-1.0, 2.0]], dtype=np.float32)
    pcm = bt.to_int16(x)
    assert pcm.dtype == np.int16
    assert pcm[0, 1] == 32767
    assert pcm[1, 0] == -32767
    assert pcm.flags["C_CONTIGUOUS"]


def test_soundfont_candidates_includes_bundle_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(bt.sys, "_MEIPASS", str(tmp_path), raising=False)
    cands = bt.soundfont_candidates()
    assert os.path.join(bt.ASSETS_DIR, bt.SOUNDFONT_NAME) in cands
    assert os.path.join(str(tmp_path), "assets", bt.SOUNDFONT_NAME) in cands


def test_jjazzlab_soundfont_preferred(monkeypatch, tmp_path):
    sf = tmp_path / "jjazzlab" / "modules" / "soundfont" / bt.JJAZZLAB_SF_NAME
    sf.parent.mkdir(parents=True)
    sf.write_bytes(b"x")
    monkeypatch.setenv("BASS_KARAOKE_JJAZZLAB", str(tmp_path))
    cands = bt.soundfont_candidates()
    assert cands[0] == str(sf)
    assert cands.index(str(sf)) < cands.index(
        os.path.join(bt.ASSETS_DIR, bt.SOUNDFONT_NAME))


def test_find_soundfont_uses_bundled_copy(monkeypatch, tmp_path):
    monkeypatch.delenv("BASS_KARAOKE_JJAZZLAB", raising=False)
    monkeypatch.delenv("JJAZZLAB_HOME", raising=False)
    monkeypatch.delenv("BASS_KARAOKE_SF2", raising=False)
    monkeypatch.setenv("ProgramFiles", str(tmp_path / "pf"))
    monkeypatch.setenv("ProgramFiles(x86)", str(tmp_path / "pf86"))
    monkeypatch.setattr(bt, "ASSETS_DIR", str(tmp_path / "sin-assets"))
    monkeypatch.setattr(bt.sys, "_MEIPASS", str(tmp_path), raising=False)
    sf = tmp_path / "assets" / bt.SOUNDFONT_NAME
    sf.parent.mkdir()
    sf.write_bytes(b"sf2")
    assert bt.find_soundfont() == str(sf)
