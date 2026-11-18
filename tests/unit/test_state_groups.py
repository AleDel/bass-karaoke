"""Fase 2 del estado agrupado: mixer (con rename), pitch, timing, countdown,
reproducción. Requiere haber aplicado scripts/apply_state_phase2.py."""
import threading

import pytest

from bass_karaoke.config import BPM_DEFAULT
from bass_karaoke.state import (
    MIXER_RENAME,
    CountdownState,
    HitTimingState,
    MixerState,
    PitchState,
    PlaybackState,
    StateGroup,
    legacy_names,
    with_state,
)


@with_state(
    StateGroup("mixer", MixerState, rename=MIXER_RENAME),
    StateGroup("pitch", PitchState),
    StateGroup("hit", HitTimingState),
    StateGroup("countdown", CountdownState),
    StateGroup("playback", PlaybackState),
)
class Host:
    pass


def test_mixer_conserva_los_nombres_antiguos():
    h = Host()
    assert (h.mix_song, h.mix_bass, h.mix_band, h.mix_click) == (1.0, 0.6, 0.6, 1.0)
    assert h.muted is False and h.muted_bass is False
    h.mix_bass = 0.25
    h.muted = True
    assert h.mixer_state.bass_vol == 0.25
    assert h.mixer_state.song_muted is True


def test_el_mute_de_la_cancion_no_afecta_al_de_la_banda():
    h = Host()
    h.muted_band = True
    assert h.muted is False
    assert h.mixer_state.band_muted is True


def test_rename_cubre_todos_los_campos_del_mixer():
    assert set(MIXER_RENAME) == {f for f in MixerState.__dataclass_fields__}
    assert len(set(MIXER_RENAME.values())) == len(MIXER_RENAME)


def test_defaults_de_pitch_y_timing():
    h = Host()
    assert (h.detected_hz, h.detected_note) == (0.0, "—")
    assert (h.stable_hz, h.stable_note) == (0.0, "—")
    assert h.note_match is None and h.detected_fret_str is None
    assert h.last_hit_delta16 == 0.0
    assert h.last_hit_note_idx == -1
    assert h.last_hit_alpha == 0.0


def test_defaults_de_countdown_y_reproduccion():
    h = Host()
    assert (h.counting_down, h.countdown_beat, h.countdown_timer,
            h.countdown_enabled) == (False, 4, 0.0, True)
    assert h.bpm == BPM_DEFAULT
    assert (h.playing, h.note_idx, h.beat_time) == (False, 0, 0.0)
    assert (h.score_ok, h.score_total) == (0, 0)
    assert (h.mp3_offset_sec, h.song_start_sec) == (0.0, 0.0)


def test_escritura_desde_otro_hilo_se_ve_en_el_grupo():
    """El hilo del micro escribe detected_*; el hilo de UI lee el grupo."""
    h = Host()

    def worker():
        h.stable_hz = 55.0
        h.stable_note = "A1"

    t = threading.Thread(target=worker)
    t.start()
    t.join()
    assert (h.pitch_state.stable_hz, h.pitch_state.stable_note) == (55.0, "A1")


def test_legacy_names_no_se_repiten_entre_grupos():
    groups = [
        StateGroup("mixer", MixerState, rename=MIXER_RENAME),
        StateGroup("pitch", PitchState),
        StateGroup("hit", HitTimingState),
        StateGroup("countdown", CountdownState),
        StateGroup("playback", PlaybackState),
    ]
    names = [n for g in groups for n in legacy_names(g)]
    assert len(names) == len(set(names)) == 29


def test_basskaraoke_sin_init_tiene_los_defaults_de_la_fase_2():
    from bass_karaoke.app import BassKaraoke

    class Fake(BassKaraoke):
        def __init__(self):
            pass

    f = Fake()
    assert f.bpm == BPM_DEFAULT
    assert f.playing is False and f.beat_time == 0.0
    assert f.mix_bass == 0.6 and f.muted is False
    assert f.detected_note == "—" and f.note_match is None
    assert f.countdown_enabled is True
    f.beat_time = 12.5
    assert f.playback_state.beat_time == 12.5


def test_un_choque_de_nombres_sigue_fallando():
    with pytest.raises(RuntimeError, match="ya existe"):
        @with_state(StateGroup("playback", PlaybackState))
        class Clash:
            bpm = 120
