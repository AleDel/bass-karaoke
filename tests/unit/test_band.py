"""Tests de la banda jjSwing (batería, piano y guitarra del mixer)."""
import numpy as np
import pytest

from bass_karaoke.audio import band


def test_parse_chord_spanish_and_english():
    assert band.parse_chord("Famaj7") == (5, [5, 9, 0, 4])
    assert band.parse_chord("Rem7") == (2, [2, 5, 9, 0])
    assert band.parse_chord("Lab7") == (8, [8, 0, 3, 6])
    assert band.parse_chord("Cm7") == (0, [0, 3, 7, 10])
    assert band.parse_chord("G7b9")[0] == 7
    assert band.parse_chord("Bb69") == (10, [10, 2, 5, 7, 0])
    assert band.parse_chord("") is None


def test_parse_chord_unrecognised_returns_none():
    assert band.parse_chord("N.C.") is None


def test_fit_pitch_keeps_chord_tones():
    src = [0, 4, 7, 11]
    dst = [5, 9, 0, 4]              # Fmaj7
    assert band._fit_pitch(64, src, dst) == 69      # E (3ª de C) -> A (3ª de F)
    assert band._fit_pitch(59, src, dst) == 64      # B (7ª de C) -> E (7ª de F)
    assert band._fit_pitch(67, src, dst) == 72      # G (5ª de C) -> C (5ª de F)


@pytest.fixture()
def fake_data(monkeypatch):
    drums = {"BRUSHES_1": {"std": [[(0, 36, 80)]],
                           "fill": [[(0, 38, 90)]]}}
    yjz = {
        "Main A-1": {
            "Piano_Chord1": {"CM7": [(0.0, 1.0, 64, 80)]},
            "Guit_Chord2": {"CM7": [(2.0, 0.5, 67, 70)]},
        },
    }
    monkeypatch.setitem(band._CACHE, "data", (yjz, 960, drums, 480))
    return drums, yjz


def test_build_events_tiles_drums_and_fills(fake_data):
    chords = [(0.0, "C"), (1.0, "F"), (2.0, "C"), (3.0, "F")]
    ev = band.build_events(chords, bpm=240, barlen=4, total_sec=8.0)
    assert ev is not None
    times = [round(t, 3) for t, *_ in ev["drums"]]
    assert times.count(0.0) >= 1
    assert any(abs(t - 7.0) < 0.2 for t in times)
    kicks = [e for e in ev["drums"] if e[2] == 36]
    fills = [e for e in ev["drums"] if e[2] == 38]
    assert kicks and fills


def test_build_events_comping_uses_chord_tones(fake_data):
    chords = [(0.0, "Fmaj7")]
    ev = band.build_events(chords, bpm=120, barlen=4, total_sec=4.0)
    pcs = {e[2] % 12 for e in ev["piano"] + ev["guitar"]}
    assert pcs
    assert pcs <= {5, 9, 0, 4}


def test_build_events_without_data_returns_none(monkeypatch):
    monkeypatch.setitem(band._CACHE, "data", None)
    assert band.build_events([(0.0, "C")], 120, 4, 4.0) is None


def test_available_respects_disable_flag(monkeypatch):
    monkeypatch.setenv("BASS_KARAOKE_NO_BAND", "1")
    assert band.available() is False


def test_render_returns_none_without_data(monkeypatch):
    monkeypatch.setitem(band._CACHE, "data", None)
    assert band.render([(0.0, "C")], 120, 4, 4.0) is None


@pytest.mark.skipif(not band.available(), reason="JJazzLab no instalado")
def test_render_real_band_is_audible_and_aligned():
    a = band.render([(0.0, "Famaj7"), (1.0, "Lab7")], 180, 4, 4.0)
    assert a is not None
    assert a.dtype == np.float32 and a.shape[1] == 2
    assert float(np.abs(a).max()) > 0.2
    assert float(np.sqrt((a ** 2).mean())) > 0.02


def test_scaled_events_follows_tempo_ratio(fake_data):
    chords = [(0.0, "Cm7"), (8.0, "Cm7")]
    slow = band._scaled_events(chords, 120, 4, 16.0, 1.0)
    fast = band._scaled_events(chords, 120, 4, 16.0, 2.0)
    t_slow = [t for t, *_ in slow["drums"]]
    t_fast = [t for t, *_ in fast["drums"]]
    assert len(t_fast) >= len(t_slow)          # mismos compases, no truncado
    for a, b in zip(t_slow[:6], t_fast[:6], strict=False):
        assert abs(b - a / 2.0) < 0.01


# ── línea de bajo con frases de jjSwing ─────────────────────────────────────
@pytest.fixture()
def fake_bass_data(monkeypatch):
    yjz = {
        "Main A-1": {"Bass": {"CM7": [(0.0, 1.9, 36, 80), (2.0, 1.9, 48, 76)]}},
        "Main C-1": {"Bass": {"CM7": [(0.0, 0.9, 36, 80), (1.0, 0.9, 40, 78)],
                              "Cm7": [(0.0, 0.9, 36, 80), (1.0, 0.9, 39, 78)]}},
    }
    monkeypatch.setitem(band._CACHE, "data", (yjz, 960, {}, 480))
    return yjz


def test_bass_events_follows_chord_root(fake_bass_data):
    ev = band.bass_events([(0.0, "Fmaj7")], 120, 4, 16.0,
                          [(0, 8, "Main A-1")])
    assert ev is not None
    assert [round(t, 2) for t, *_ in ev] == [0.0, 1.0]
    assert {p % 12 for _, _, p, _ in ev} == {5}     # F en las dos octavas
    assert all(28 <= p <= 58 for _, _, p, _ in ev)


def test_bass_events_uses_minor_phrase(fake_bass_data):
    ev = band.bass_events([(0.0, "Cm7")], 120, 4, 8.0, [(0, 8, "Main C-1")])
    pcs = [p % 12 for _, _, p, _ in ev]
    assert pcs[:2] == [0, 3]        # C, Eb (frase Cm7, no E natural)


def test_bass_events_keeps_register(fake_bass_data, monkeypatch):
    yjz = {"Main A-1": {"Bass": {"CM7": [(0.0, 1.0, 58, 80)]}}}
    monkeypatch.setitem(band._CACHE, "data", (yjz, 960, {}, 480))
    ev = band.bass_events([(0.0, "F#maj7")], 120, 4, 8.0,
                          [(0, 8, "Main A-1")])
    assert ev is not None
    assert 28 <= ev[0][2] <= 58


def test_bass_events_without_data_returns_none(monkeypatch):
    monkeypatch.setitem(band._CACHE, "data", None)
    assert band.bass_events([(0.0, "C")], 120, 4, 4.0) is None


def test_bass_events_cycles_variations_without_sections(fake_bass_data):
    chords = [(t, "Cm7") for t in range(0, 48, 1)]
    ev = band.bass_events(chords, 120, 4, 48.0)
    assert ev and len(ev) >= 4


# ── MIDI externo ────────────────────────────────────────────────────────────
def _write_midi(path, ticks_per_beat=480):
    import mido
    mid = mido.MidiFile(ticks_per_beat=ticks_per_beat)
    track = mido.MidiTrack()
    mid.tracks.append(track)
    track.append(mido.MetaMessage("set_tempo", tempo=500000, time=0))
    track.append(mido.Message("program_change", channel=0, program=33, time=0))
    track.append(mido.Message("control_change", channel=0, control=7,
                              value=80, time=0))
    track.append(mido.Message("note_on", channel=0, note=40, velocity=90,
                              time=0))
    track.append(mido.Message("note_off", channel=0, note=40, velocity=0,
                              time=480))
    track.append(mido.MetaMessage("set_tempo", tempo=250000, time=0))
    track.append(mido.Message("note_on", channel=0, note=45, velocity=70,
                              time=0))
    track.append(mido.Message("note_off", channel=0, note=45, velocity=0,
                              time=480))
    track.append(mido.Message("program_change", channel=9, program=40, time=0))
    track.append(mido.Message("note_on", channel=9, note=38, velocity=100,
                              time=0))
    track.append(mido.Message("note_off", channel=9, note=38, velocity=0,
                              time=240))
    mid.save(path)
    return path


def test_midi_channels_reads_program_volume_and_tempo(tmp_path):
    path = _write_midi(str(tmp_path / "x.mid"))
    chans = band._midi_channels(path)
    assert set(chans) == {0, 9}
    mel = chans[0]
    assert mel["preset"] == 33 and mel["vol"] == 80
    assert len(mel["notes"]) == 2
    assert mel["notes"][0] == (0.0, 0.5, 40, 90)
    second = mel["notes"][1]
    assert abs(second[0] - 0.5) < 1e-6
    assert abs(second[1] - 0.25) < 1e-6
    assert chans[9]["preset"] == 40


def test_render_midi_missing_file_returns_none():
    assert band.render_midi("no_existe.mid") is None


@pytest.mark.skipif(not band.midi_available(), reason="sin SoundFont")
def test_render_midi_is_audible(tmp_path):
    path = _write_midi(str(tmp_path / "b.mid"))
    audio = band.render_midi(path)
    assert audio is not None
    assert audio.dtype == np.float32 and audio.shape[1] == 2
    assert float(np.abs(audio).max()) > 0.2
    assert abs(len(audio) / 44100 - 1.875) < 0.2


@pytest.mark.skipif(not band.midi_available(), reason="sin SoundFont")
def test_render_midi_scales_with_ratio(tmp_path):
    path = _write_midi(str(tmp_path / "c.mid"))
    fast = band.render_midi(path, 0.5)
    slow = band.render_midi(path, 1.0)
    assert len(fast) > len(slow) * 1.8


@pytest.mark.skipif(not band.midi_available(), reason="sin SoundFont")
def test_render_midi_channel_filters(tmp_path):
    """El bajo se puede aislar del resto de pistas del MIDI de JJazzLab."""
    path = _write_midi(str(tmp_path / "d.mid"))
    only_bass = band.render_midi(path, only_channels={0})
    no_bass = band.render_midi(path, exclude_channels={0})
    assert only_bass is not None and no_bass is not None
    assert float(np.abs(only_bass).max()) > 0.05
    assert float(np.abs(no_bass).max()) > 0.05
    # el bajo suena en 0..0.75 s; la batería entra después: cada filtro deja
    # la otra mitad en silencio (separación real de pistas)
    head = int(0.7 * 44100)
    assert float(np.abs(only_bass[:head]).max()) > 0.05
    assert float(np.abs(no_bass[:head]).max()) < 0.01
    # sin ningún canal no hay nada que renderizar
    assert band.render_midi(path, only_channels={7}) is None
